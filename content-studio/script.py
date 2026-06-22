#!/usr/bin/env python3
"""
Content Studio — prototype V2 (company-agnostic)
================================================

Implements the V2.0 flow:

    intent  ->  workplan  ->  outline  ->  draft (+validate)  ->  editor  ->  done

The point of this version
-------------------------
The Gravton SOP / rubric / FAQ guidelines are treated as ONE INSTANCE of a
generic, company-agnostic rule system. Nothing about Gravton, GEO, or blogs is
hard-coded into the engine. Three layers carry all brand/industry specifics:

  1. BrandKit          - what the brand sounds like and serves (prose the model
                         interprets). Mirrors the Django `Brandkit` model.
  2. ProductVertical   - product + buyer-language signals. Mirrors the Django
                         `ProductVertical` model.
  3. ContentRuleset    - the mechanical writing rules abstracted out of the SOP:
                         structure sequence, word targets, heading format,
                         keyword placement, banned phrases, FAQ rules, meta/limits.

Source-of-truth decision: the ContentRuleset drives BOTH generation and
validation. The "quality rubric" is simply the ruleset evaluated as checks, so
the two can never drift. Deterministic rules run as code; subjective rules
(voice, active voice, quotable phrasing, uniqueness) run as model calls.

Run
---
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 content_studio_v2.py            # http://127.0.0.1:8000

Offline self-test (no key / no network)
---------------------------------------
    python3 content_studio_v2.py --selftest
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional


def _load_dotenv() -> None:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v

_load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("content_studio")

# ============================================================================
# SECTION 1 — CONFIGURATION / INPUTS   (edit these)
# ============================================================================

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# --- Model routing ----------------------------------------------------------
# PRD names map to real callable strings. Re-route any task here.
#   Opus 4.8 -> legal/citation/evidence gates   (MODEL_VERIFY)
#   Opus 4.7 -> briefs, drafts, brand voice      (MODEL_DRAFT)
#   Opus 4.6 -> general work                      (MODEL_GENERAL)
MODEL_DRAFT = "claude-opus-4-8"
MODEL_VERIFY = "claude-opus-4-8"
MODEL_GENERAL = "claude-sonnet-4-6"

MAX_TOKENS_REPLY = 1024
MAX_TOKENS_STRUCT = 2048
MAX_TOKENS_DRAFT = 8192
MAX_TOKENS_CHECK = 1536

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DRAFTS_DIR = os.path.join(DATA_DIR, "drafts")
PIPELINE_LOG_PATH = os.path.join(DATA_DIR, "pipeline.log")

MAX_SOURCE_URLS = 5
URL_FETCH_TIMEOUT = 12
BACKGROUND_GRADER_TIMEOUT = 45
WORD_COUNT_TOLERANCE = 0.25  # +/- 25% of target counts as "on target"

CONTENT_TYPES = [
    "blog", "guide", "listicle", "technical_article",
    "press_release", "product_review", "product_description",
]
LENGTHS = {"snapshot": 400, "concise": 800, "structured": 1200,
           "researched": 2000, "report": 3000}

# Blocks the intent agent collects. Required gate the workplan; soft ones are
# marked complete after one attempt so the flow never loops.
REQUIRED_BLOCKS = ["topic", "goal", "audience", "content_type", "length", "primary_keyword"]
SOFT_BLOCKS = ["secondary_keywords", "prompts", "guardrails", "sources", "competitive_refs"]
BLOCK_ORDER = REQUIRED_BLOCKS + SOFT_BLOCKS

PHASES = ["intent", "workplan", "outline", "draft", "editor", "done"]

PERSONA_SYSTEM = (
    "You are Aqiira, a trusted content advisor with deep expertise in content strategy. "
    "Your manner: warm and genuinely curious, patient, probing — you ask one thoughtful question "
    "at a time and never overwhelm. Confident and clear without being prescriptive. You occasionally "
    "surface angles the user hasn't considered. You speak like a smart, engaged colleague — never "
    "robotic, never repetitive, never give the same phrasing twice. Each conversation feels like "
    "a real collaboration, not a form-filling exercise."
)


# ============================================================================
# SECTION 1.5 — AUTH + USER PATHS
# ============================================================================

def _parse_users(raw: str) -> dict:
    result: dict = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if ":" in entry:
            u, p = entry.split(":", 1)
            if u.strip():
                result[u.strip()] = p.strip()
    return result


USERS_MAP: dict = _parse_users(os.environ.get("USERS", ""))
JWT_SECRET: str = os.environ.get("JWT_SECRET", uuid.uuid4().hex)
_CORS_RAW: str = os.environ.get("CORS_ORIGIN", "*")
# Support comma-separated list: "https://a.vercel.app,https://b.onrender.com"
_CORS_ORIGINS: set = {o.strip() for o in _CORS_RAW.split(",") if o.strip()}


def make_token(username: str) -> str:
    exp = int(time.time()) + 86400 * 30
    payload = f"{username}|{exp}"
    sig = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode().rstrip("=")


def verify_token(token: str) -> Optional[str]:
    try:
        padded = token + "=" * (4 - len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        parts = decoded.split("|")
        if len(parts) != 3:
            return None
        username, exp_str, sig = parts
        if time.time() > int(exp_str):
            return None
        payload = f"{username}|{exp_str}"
        expected = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        if username not in USERS_MAP:
            return None
        return username
    except Exception:
        return None


def _user_sessions_dir(username: str) -> str:
    return os.path.join(DATA_DIR, "users", username, "sessions")


def _session_root(username: str, session_id: str) -> str:
    return os.path.join(_user_sessions_dir(username), session_id)


def _session_exists(username: str, session_id: str) -> bool:
    return os.path.exists(os.path.join(_session_root(username, session_id), "session.json"))


def list_sessions(username: str) -> list:
    sdir = _user_sessions_dir(username)
    if not os.path.exists(sdir):
        return []
    result = []
    for sid in os.listdir(sdir):
        sf = os.path.join(sdir, sid, "session.json")
        if not os.path.exists(sf):
            continue
        try:
            with open(sf, encoding="utf-8") as f:
                state = json.load(f)
            topic = (state.get("blocks") or {}).get("topic") or ""
            result.append({
                "id": sid,
                "title": topic or "New session",
                "phase": state.get("phase", "intent"),
                "created_at": (state.get("meta") or {}).get("created_at"),
                "updated_at": (state.get("meta") or {}).get("updated_at"),
            })
        except Exception:
            pass
    result.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return result


# ============================================================================
# SECTION 2 — STORAGE (files as database)
# ============================================================================

class FileStore:
    """JSON key/value store, one file per key, atomic writes (temp + replace)."""

    def __init__(self, root: str):
        self.root = root
        self.drafts_dir = os.path.join(root, "drafts")
        os.makedirs(root, exist_ok=True)
        os.makedirs(self.drafts_dir, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(self.root, f"{key}.json")

    def get(self, key: str, default: Any = None) -> Any:
        path = self._path(key)
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def set(self, key: str, value: Any) -> None:
        path = self._path(key)
        tmp = f"{path}.{uuid.uuid4().hex}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)


class SessionStore:
    """Single session guarded by a re-entrant lock (request + worker threads)."""

    def __init__(self, store: FileStore):
        self.store = store
        self.lock = threading.RLock()

    def read(self) -> dict:
        with self.lock:
            state = self.store.get("session")
            if state is None:
                state = initial_state()
                self.store.set("session", state)
            return state

    def update(self, fn: Callable[[dict], None]) -> dict:
        with self.lock:
            state = self.store.get("session") or initial_state()
            fn(state)
            state["meta"]["updated_at"] = now_iso()
            self.store.set("session", state)
            return state

    def reset(self) -> dict:
        with self.lock:
            state = initial_state()
            self.store.set("session", state)
            for key in ("reference_pack", "authority", "current_draft"):
                self.store.delete(key)
            return state


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ============================================================================
# SECTION 3 — BRAND LAYER + GENERIC RULESET
# ============================================================================
# These three artifacts hold ALL company/industry specifics. The engine reads
# them; it knows nothing about any particular brand.

def default_brandkit() -> dict:
    """Gravton brandkit — default for all new sessions."""
    return {
        "domain": "gravton.ai",
        "description": (
            "Gravton Labs provides an AI visibility and optimization platform designed to help "
            "businesses track and improve their presence across generative AI engines. The company "
            "offers tools for search visibility, content optimization, and journey analytics to "
            "connect AI-driven discovery with onsite conversion outcomes."
        ),
        "market_segment": "Enterprise Marketing, AI Strategy",
        "brand_voice": "Analytical, Technical",
        "buyer": "Marketing and AI Strategy Professionals",
        "sector": "AI Visibility and Optimization",
        "version": 1,
    }


def default_product_vertical() -> dict:
    """Gravton product vertical — default for all new sessions."""
    return {
        "product_vertical": "AI Visibility & Generative Engine Optimization (GEO)",
        "product_businesses_services": (
            "AI Search Visibility Monitoring, GEO (Generative Engine Optimization), "
            "Buyer Prompt Intelligence, AI Share of Voice Tracking, "
            "Competitive AI Visibility Analysis, Citation & Source Influence Analysis, "
            "AI Content Strategy, Opportunity Discovery Engine, "
            "AI-Ready Content Recommendations, Brand Narrative Monitoring, "
            "AI Search Analytics, Visibility Governance"
        ),
        "source_discovery": {
            "linkedin": True,
            "g2": False,
            "capterra": False,
            "industry_publications": True,
            "customer_reviews": False,
            "ai_search_engines": True,
            "search_engines": True,
        },
        "is_active": True,
    }


def default_content_ruleset() -> dict:
    """
    The GENERIC, company-agnostic abstraction of an SOP. Gravton's SOP is one
    instance of this shape. Every value here is a default a brand may override;
    the engine never assumes any of it. Set a rule to null/false to disable it.

    Split of responsibility:
      * BrandKit.brand_voice  -> WHAT the brand sounds like (prose).
      * voice_rules below     -> mechanical writing rules (toggles + lists) that
                                 are broadly applicable to good writing.
    """
    return {
        "name": "default-generic-v1",

        # Word target by length bucket (the SOP's "blog~1200 / guide~2000" idea,
        # generalised). Drives generation + the word-count rubric check.
        "word_targets": dict(LENGTHS),

        # Ordered section template. The SOP's "what it is -> why it matters ->
        # ... -> FAQs" is one instance. Empty list = no enforced sequence.
        "section_sequence": [
            "what_it_is", "why_it_matters", "core_principles",
            "strategies", "case_studies", "measuring_performance", "faqs",
        ],

        "heading_rules": {
            "h2_interrogative": True,                 # H2s phrased as questions
            "h2_question_words": ["What", "Why", "How", "When", "Where", "Who"],
            "title_case_headings": True,
            "max_h1_chars": 60,
            "one_h1_only": True,
        },

        # SEO/keyword placement. enabled=False for brands that don't care.
        "keyword_rules": {
            "enabled": True,
            "primary_count": 1,
            "secondary_max": 3,
            "primary_placements": [
                "h1", "url_slug", "first_100_words", "meta_title",
                "meta_description", "image_alt", "at_least_one_h2",
            ],
            "density_min": 1.0,
            "density_max": 1.5,
            "no_keyword_in_parentheses": True,
        },

        "voice_rules": {
            "active_voice": True,
            "second_person": True,                    # address the reader as "you"
            "define_acronyms_first_use": True,
            "number_style": "spell_under_10",         # one-nine words, 10+ numerals
            "banned_phrases": [                        # hype words
                "game-changer", "revolutionary", "cutting-edge",
                "unleash the power of", "world-class", "best-in-class",
            ],
            "banned_openers": [                        # filler intros
                "In today's digital landscape", "Now more than ever",
                "It goes without saying", "In the world of",
            ],
        },

        "faq_rules": {
            "enabled": True,
            "min": 5, "max": 8,
            "interrogative": True,
            "answer_max_words": 100,
            "tied_to_primary_keyword": True,
            "no_keyword_in_parentheses": True,
        },

        "linking_rules": {
            "internal_min": 5, "internal_max": 8,
            "external_min": 2, "external_max": 4,
            "no_bare_click_here": True,
        },

        "meta_rules": {
            "meta_title_min": 55, "meta_title_max": 60,
            "meta_desc_min": 140, "meta_desc_max": 155,
            "url_slug_max": 60,
        },

        # Engagement / quality floor (SOP: "at least one table/stat/example/quote").
        "engagement_rules": {
            "require_one_of": ["table", "statistic", "example", "quote"],
            "paragraph_max_sentences": 4,
        },
    }


def seed_config(store: FileStore) -> None:
    if store.get("brandkit") is None:
        store.set("brandkit", default_brandkit())
    if store.get("product_vertical") is None:
        store.set("product_vertical", default_product_vertical())
    if store.get("content_ruleset") is None:
        store.set("content_ruleset", default_content_ruleset())
    if store.get("insights") is None:
        store.set("insights", {"failing_prompts": []})


# ============================================================================
# SECTION 4 — SESSION SCHEMA
# ============================================================================

def initial_state() -> dict:
    return {
        "session_id": uuid.uuid4().hex,
        "phase": "intent",
        "blocks": {
            "topic": None,
            "goal": None,                 # list[str]
            "audience": None,
            "content_type": None,         # one of CONTENT_TYPES
            "is_optimization": False,
            "length": None,               # one of LENGTHS
            "primary_keyword": None,
            "secondary_keywords": None,   # list[str]
            "prompts": None,              # list[str] from Insights Bucket
            "competitive_refs": None,     # list[str]
            "guardrails": None,           # str
            "sources": [],                # list[str] URLs
        },
        "completed_blocks": [],
        "pending_soft_block": None,      # soft block asked last turn; marked complete on next response
        "pending_required_block": None,  # required block agent asked about last turn; gates _intent_complete
        "pending_question": False,       # workplan/outline agent asked a question last turn
        "history": [],
        "workplan": None,
        "outline": None,
        "background": {
            "reference_grader": "idle",
            "authority_sources": "idle",
            "draft_builder": "idle",
            "messages": [],
        },
        "meta": {
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "completed_at": None,
        },
    }


# ============================================================================
# SECTION 5 — ANTHROPIC CLIENT
# ============================================================================

class LLM:
    """Wrapper over the SDK: text + forced tool-use, retries, model routing.
    Injected into agents so tests can pass a fake (no key/network)."""

    # $/1M tokens — (input, output)
    _PRICING: dict[str, tuple[float, float]] = {
        "claude-opus-4-8": (5.00, 25.00),
        "claude-opus-4-7": (5.00, 25.00),
        "claude-opus-4-6": (5.00, 25.00),
        "claude-sonnet-4-6": (3.00, 15.00),
        "claude-haiku-4-5": (1.00, 5.00),
    }

    def __init__(self, api_key: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cost_usd: float = 0.0

    def text(self, model: str, system: str, messages: list,
             max_tokens: int = MAX_TOKENS_REPLY, tools: Optional[list] = None) -> str:
        kwargs: dict = dict(model=model, system=system, messages=messages,
                            max_tokens=max_tokens)
        if tools:
            kwargs["tools"] = tools
        resp = self._retry(lambda: self.client.messages.create(**kwargs))
        self._log_usage(model, resp.usage, "text")
        return "".join(b.text for b in resp.content
                       if getattr(b, "type", "") == "text").strip()

    def structured(self, model: str, system: str, messages: list,
                   tool_name: str, schema: dict,
                   max_tokens: int = MAX_TOKENS_STRUCT) -> dict:
        tools = [{"name": tool_name, "description": f"Return a {tool_name} object.",
                  "input_schema": schema}]
        resp = self._retry(lambda: self.client.messages.create(
            model=model, system=system, messages=messages, max_tokens=max_tokens,
            tools=tools, tool_choice={"type": "tool", "name": tool_name}))
        self._log_usage(model, resp.usage, f"structured:{tool_name}")
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use" and block.name == tool_name:
                return dict(block.input)
        return {}

    def _log_usage(self, model: str, usage: Any, call_type: str) -> None:
        in_tok = getattr(usage, "input_tokens", 0) or 0
        out_tok = getattr(usage, "output_tokens", 0) or 0
        price_in, price_out = self._PRICING.get(model, (5.00, 25.00))
        call_cost = (in_tok * price_in + out_tok * price_out) / 1_000_000
        self.total_input_tokens += in_tok
        self.total_output_tokens += out_tok
        self.total_cost_usd += call_cost
        print(
            f"[tokens] {call_type} | model={model} | "
            f"in={in_tok:,} out={out_tok:,} | "
            f"call=${call_cost:.4f} | session_total=${self.total_cost_usd:.4f}"
        )

    def _retry(self, call: Callable[[], Any], attempts: int = 3):
        delay, last = 1.0, None
        for _ in range(attempts):
            try:
                return call()
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(delay)
                delay *= 2
        raise last  # type: ignore[misc]

    def stream_text(self, model: str, system: str, messages: list,
                    max_tokens: int, on_token: Callable[[str], None]) -> str:
        """Stream text tokens via on_token callback. Returns the full accumulated text."""
        full = ""
        with self.client.messages.stream(
            model=model, system=system, messages=messages, max_tokens=max_tokens
        ) as stream:
            for token in stream.text_stream:
                on_token(token)
                full += token
            self._log_usage(model, stream.get_final_message().usage, "stream")
        return full


# ============================================================================
# SECTION 6 — DETERMINISTIC RULE ENGINE  (the rubric, evaluated as code)
# ============================================================================
# Pure functions. No LLM, no network. These are the cheap, reliable half of
# validation and are fully unit-tested in --selftest.

def is_faq_heading(text: str) -> bool:
    t = text.lower()
    return "faq" in t or "frequently asked" in t


def parse_markdown(md: str) -> dict:
    """Light structural parse of a draft body."""
    lines = md.splitlines()
    h1 = next((l[2:].strip() for l in lines if l.startswith("# ")), "")
    h2s = [l[3:].strip() for l in lines if l.startswith("## ")]
    # crude FAQ block extraction: lines under the FAQ heading that end with "?"
    faqs = []
    in_faq = False
    for l in lines:
        if l.startswith("## "):
            in_faq = is_faq_heading(l)
            continue
        if in_faq and l.strip().endswith("?"):
            faqs.append(l.strip().lstrip("#*-> ").strip())
    return {"h1": h1, "h2s": h2s, "faq_questions": faqs}


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _check(cid: str, category: str, rule: str, ok: Optional[bool],
           detail: str = "", severity: str = "warning") -> dict:
    result = "na" if ok is None else ("pass" if ok else "fail")
    return {"id": cid, "category": category, "rule": rule,
            "result": result, "detail": detail,
            "severity": "info" if result == "pass" else severity}


class RuleEngine:
    """Evaluates a ContentRuleset against a draft deterministically."""

    def run(self, draft: dict, ruleset: dict) -> list:
        md = draft.get("markdown", "")
        struct = parse_markdown(md)
        pk = (draft.get("primary_keyword") or "").strip()
        checks: list = []
        log.debug("RuleEngine.run — ruleset=%r primary_keyword=%r", ruleset.get("name"), pk)

        # --- word count -----------------------------------------------------
        target = draft.get("target_words") or 0
        wc = draft.get("word_count") or word_count(md)
        if target:
            lo, hi = target * (1 - WORD_COUNT_TOLERANCE), target * (1 + WORD_COUNT_TOLERANCE)
            checks.append(_check(
                "word_count", "structure",
                f"Word count near target ({target})",
                lo <= wc <= hi, f"{wc} words (target {target})"))

        # --- meta lengths ---------------------------------------------------
        mr = ruleset.get("meta_rules", {})
        mt = draft.get("meta_title", "")
        md_desc = draft.get("meta_description", "")
        slug = draft.get("url_slug", "")
        if mt:
            checks.append(_check("meta_title_len", "seo",
                f"Meta title {mr.get('meta_title_min')}–{mr.get('meta_title_max')} chars",
                mr.get("meta_title_min", 0) <= len(mt) <= mr.get("meta_title_max", 999),
                f"{len(mt)} chars"))
        if md_desc:
            checks.append(_check("meta_desc_len", "seo",
                f"Meta description {mr.get('meta_desc_min')}–{mr.get('meta_desc_max')} chars",
                mr.get("meta_desc_min", 0) <= len(md_desc) <= mr.get("meta_desc_max", 999),
                f"{len(md_desc)} chars"))
        if slug:
            checks.append(_check("url_len", "seo",
                f"URL slug ≤ {mr.get('url_slug_max')} chars, lowercase, hyphenated",
                len(slug) <= mr.get("url_slug_max", 999)
                and slug == slug.lower() and " " not in slug,
                f"'{slug}'"))

        # --- keyword rules --------------------------------------------------
        kr = ruleset.get("keyword_rules", {})
        if kr.get("enabled") and pk:
            first100 = " ".join(md.split()[:100]).lower()
            checks.append(_check("kw_first_100", "seo",
                "Primary keyword in first 100 words",
                pk.lower() in first100))
            checks.append(_check("kw_in_h1", "seo",
                "Primary keyword in H1",
                pk.lower() in struct["h1"].lower()))
            checks.append(_check("kw_in_h2", "seo",
                "Primary keyword in at least one H2",
                any(pk.lower() in h.lower() for h in struct["h2s"])))
            if kr.get("no_keyword_in_parentheses"):
                in_parens = re.findall(r"\(([^)]*)\)", md)
                bad = any(pk.lower() in seg.lower() for seg in in_parens)
                checks.append(_check("kw_no_parens", "seo",
                    "Primary keyword never inside parentheses",
                    not bad))
            # density
            if wc:
                occ = len(re.findall(re.escape(pk), md, flags=re.I))
                density = 100.0 * occ / wc
                checks.append(_check("kw_density", "seo",
                    f"Keyword density {kr.get('density_min')}–{kr.get('density_max')}%",
                    kr.get("density_min", 0) <= density <= kr.get("density_max", 100),
                    f"{density:.2f}%"))

        # --- heading rules --------------------------------------------------
        hr = ruleset.get("heading_rules", {})
        if hr.get("h2_interrogative") and struct["h2s"]:
            qwords = tuple(w.lower() for w in hr.get("h2_question_words", []))
            non_q = [h for h in struct["h2s"]
                     if not h.lower().lstrip("#* ").startswith(qwords)
                     and not is_faq_heading(h)]
            checks.append(_check("h2_interrogative", "structure",
                "H2 headings use question words",
                len(non_q) == 0,
                f"{len(non_q)} non-question H2(s)" if non_q else "all interrogative"))
        if hr.get("max_h1_chars") and struct["h1"]:
            checks.append(_check("h1_len", "structure",
                f"H1 ≤ {hr['max_h1_chars']} chars",
                len(struct["h1"]) <= hr["max_h1_chars"], f"{len(struct['h1'])} chars"))

        # --- voice rules (deterministic subset) -----------------------------
        vr = ruleset.get("voice_rules", {})
        low = md.lower()
        banned_hit = [p for p in vr.get("banned_phrases", []) if p.lower() in low]
        checks.append(_check("no_hype", "voice",
            "No hype / banned phrases",
            len(banned_hit) == 0,
            ("found: " + ", ".join(banned_hit)) if banned_hit else "none"))
        opener_hit = [o for o in vr.get("banned_openers", []) if o.lower() in low[:400]]
        checks.append(_check("no_filler_openers", "voice",
            "No filler openers",
            len(opener_hit) == 0,
            ("found: " + ", ".join(opener_hit)) if opener_hit else "none"))
        if vr.get("number_style") == "spell_under_10":
            # advisory: standalone digits 1-9 in prose (not %, not list markers)
            viol = re.findall(r"(?<![\d$%.])\b[1-9]\b(?!\s*[%)\.])", md)
            checks.append(_check("number_style", "voice",
                "Spell out one–nine; numerals for 10+",
                len(viol) == 0,
                f"{len(viol)} bare single digit(s)" if viol else "ok",
                severity="info"))

        # --- FAQ rules ------------------------------------------------------
        fr = ruleset.get("faq_rules", {})
        if fr.get("enabled"):
            n = len(struct["faq_questions"])
            checks.append(_check("faq_count", "faq",
                f"FAQ has {fr.get('min')}–{fr.get('max')} questions",
                fr.get("min", 0) <= n <= fr.get("max", 999), f"{n} question(s)"))
            if fr.get("interrogative") and struct["faq_questions"]:
                non_q = [q for q in struct["faq_questions"] if not q.endswith("?")]
                checks.append(_check("faq_interrogative", "faq",
                    "FAQ questions are interrogative",
                    len(non_q) == 0))

        passed = sum(1 for c in checks if c["result"] == "pass")
        failed = sum(1 for c in checks if c["result"] == "fail")
        log.info("RuleEngine.run — %d checks: %d passed, %d failed", len(checks), passed, failed)
        for c in checks:
            log.debug("  [%s] %s — %s %s", c["result"].upper(), c["id"], c["rule"], c.get("detail", ""))
        return checks


# ============================================================================
# SECTION 7 — BACKGROUND AGENTS
# ============================================================================

def fetch_url(url: str, timeout: int = URL_FETCH_TIMEOUT) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ContentStudio/0.2"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            raw = resp.read(400_000).decode("utf-8", errors="ignore")
            return {"ok": status == 200, "status": status, "text": strip_html(raw)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "text": "", "error": str(exc)}


def strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


class ReferenceGrader:
    """B3 — fetch + classify each attached URL. Inaccessible URLs are skipped."""

    SCHEMA = {
        "type": "object",
        "properties": {
            "classification": {"type": "string",
                               "enum": ["earned_media", "brand_owned", "community"]},
            "quality_score": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["classification", "quality_score"],
    }

    def __init__(self, llm: LLM):
        self.llm = llm

    def grade_one(self, url: str) -> dict:
        f = fetch_url(url)
        if not f["ok"]:
            return {"url": url, "crawlable": False, "skipped": True,
                    "classification": None, "quality_score": 0.0,
                    "error": f.get("error")}
        out = self.llm.structured(
            MODEL_GENERAL,
            "Classify a web page as a content reference: earned_media (peer "
            "review, analyst, independent press), brand_owned (a company's own "
            "blog/PR/product page), or community (forum/Q&A). Score quality 0-1.",
            [{"role": "user", "content": f"URL: {url}\n\n{f['text'][:6000]}"}],
            "grade_reference", self.SCHEMA, MAX_TOKENS_CHECK)
        return {"url": url, "crawlable": True, "skipped": False,
                "classification": out.get("classification"),
                "quality_score": round(float(out.get("quality_score", 0.0)), 2),
                "reason": out.get("reason", "")}

    def run(self, urls: list) -> dict:
        graded: list = []
        if urls:
            with ThreadPoolExecutor(max_workers=4) as pool:
                for fut in as_completed({pool.submit(self.grade_one, u): u for u in urls}):
                    graded.append(fut.result())
        return {"graded": graded,
                "citable": [g for g in graded if g.get("classification") == "earned_media"],
                "graded_at": now_iso()}


class AuthoritySources:
    """B2 — web research for context. Degrades gracefully if web_search is off."""

    def __init__(self, llm: LLM):
        self.llm = llm

    def run(self, topic: str, prompts: list) -> dict:
        query = topic or " ".join(prompts or []) or "industry overview"
        try:
            summary = self.llm.text(
                MODEL_GENERAL,
                "Research authoritative context for the topic. Summarise what "
                "analysts, press and communities say. Cite source names inline. "
                "Under 250 words.",
                [{"role": "user", "content": f"Topic: {query}"}],
                MAX_TOKENS_CHECK,
                tools=[{"type": "web_search_20250305", "name": "web_search"}])
            return {"summary": summary, "query": query, "ok": True, "at": now_iso()}
        except Exception as exc:  # noqa: BLE001
            return {"summary": "", "query": query, "ok": False, "error": str(exc),
                    "at": now_iso()}


class DraftBuilder:
    """
    Builds the draft against the six PRD inputs (outline, workplan, insights,
    building rules = ruleset, guardrails, source SOP = ruleset), then runs the
    full validation pass: deterministic rubric + subjective LLM checks +
    AI-signal callout.
    """

    META_SCHEMA = {
        "type": "object",
        "properties": {
            "subtitle": {"type": "string"},
            "meta_title": {"type": "string"},
            "meta_description": {"type": "string"},
            "url_slug": {"type": "string"},
        },
        "required": ["meta_title", "meta_description", "url_slug"],
    }
    LLM_CHECK_SCHEMA = {
        "type": "object",
        "properties": {"flags": {"type": "array", "items": {
            "type": "object",
            "properties": {"quote": {"type": "string"}, "issue": {"type": "string"},
                           "severity": {"type": "string",
                                        "enum": ["info", "warning", "blocker"]}},
            "required": ["issue"]}}},
        "required": ["flags"],
    }
    AI_SIGNAL_SCHEMA = {
        "type": "object",
        "properties": {"signals": {"type": "array", "items": {
            "type": "object",
            "properties": {"signal": {"type": "string"}, "example": {"type": "string"},
                           "fix": {"type": "string"}},
            "required": ["signal"]}}},
        "required": ["signals"],
    }

    def __init__(self, llm: LLM, rule_engine: RuleEngine):
        self.llm = llm
        self.rules = rule_engine

    def build(self, outline: dict, blocks: dict, ruleset: dict, brandkit: dict,
              product: dict, reference_pack: dict, authority: dict,
              insights: dict, prior_annotations: Optional[list] = None) -> dict:
        target = ruleset.get("word_targets", {}).get(blocks.get("length") or "structured", 1200)
        citable = [c["url"] for c in (reference_pack or {}).get("citable", [])]

        system = self._gen_system(blocks, ruleset, brandkit, product, citable, authority, target, prior_annotations)
        body = self.llm.text(MODEL_DRAFT, system,
                             [{"role": "user", "content": "Outline:\n" + json.dumps(outline, indent=2)}],
                             MAX_TOKENS_DRAFT)
        if not body.strip():
            raise RuntimeError("empty draft body")

        meta = self.llm.structured(
            MODEL_GENERAL,
            "Produce SEO metadata for the article. Respect lengths: meta_title "
            f"{ruleset['meta_rules']['meta_title_min']}-{ruleset['meta_rules']['meta_title_max']} chars; "
            f"meta_description {ruleset['meta_rules']['meta_desc_min']}-{ruleset['meta_rules']['meta_desc_max']} chars; "
            f"url_slug lowercase hyphenated <= {ruleset['meta_rules']['url_slug_max']} chars. "
            f"Include the primary keyword '{blocks.get('primary_keyword')}' in each.",
            [{"role": "user", "content": body[:4000]}],
            "make_meta", self.META_SCHEMA, MAX_TOKENS_CHECK)

        draft = {
            "primary_keyword": blocks.get("primary_keyword"),
            "secondary_keywords": blocks.get("secondary_keywords") or [],
            "title": parse_markdown(body)["h1"] or outline.get("title", "Untitled"),
            "subtitle": meta.get("subtitle", ""),
            "meta_title": meta.get("meta_title", ""),
            "meta_description": meta.get("meta_description", ""),
            "url_slug": meta.get("url_slug", ""),
            "markdown": body,
            "target_words": target,
            "word_count": word_count(body),
            "built_at": now_iso(),
        }

        # validation: deterministic + subjective in parallel
        log.info("DraftBuilder.build — running deterministic rule checks (ruleset=%r)", ruleset.get("name"))
        det = self.rules.run(draft, ruleset)
        log.info("DraftBuilder.build — running LLM guardrail checks")
        subjective, ai_signals = self._validate_llm(body, blocks, ruleset, brandkit,
                                                    reference_pack, insights)
        draft["rubric"] = self._score(det + subjective)
        draft["ai_signals"] = ai_signals
        # Deterministic fails are already single entries; LLM check fails carry
        # per-flag detail in "flags" — expand those into individual annotation rows
        # so prior_annotations and the UI still see the full issue list.
        annotations = [c for c in det if c["result"] == "fail"]
        for c in subjective:
            if c["result"] == "fail":
                for f in (c.get("flags") or []):
                    annotations.append({
                        "id": c["id"], "category": c["category"], "rule": c["rule"],
                        "result": "fail",
                        "severity": f.get("severity", "warning"),
                        "detail": f.get("issue", ""), "quote": f.get("quote", ""),
                    })
        draft["annotations"] = annotations
        log.info(
            "DraftBuilder.build — rubric scored: %d/%d (%.1f%%) | %d annotation(s) | %d AI signal(s)",
            draft["rubric"]["passed"], draft["rubric"]["total"], draft["rubric"]["pct"],
            len(draft["annotations"]), len(ai_signals),
        )
        return draft

    def _gen_system(self, blocks, ruleset, brandkit, product, citable, authority, target,
                    prior_annotations=None) -> str:
        log.debug(
            "DraftBuilder._gen_system — ruleset=%r target_words=%d citable_urls=%d",
            ruleset.get("name"), target, len(citable or []),
        )
        vr = ruleset.get("voice_rules", {})
        seq = " -> ".join(ruleset.get("section_sequence", []))
        prompt = (
            "You are Content Studio's draft builder. Write a complete first draft "
            "in Markdown from the approved outline.\n\n"
            "BRAND CONTEXT (interpret, do not quote):\n"
            f"- Description: {brandkit.get('description')}\n"
            f"- Market segment: {brandkit.get('market_segment')}\n"
            f"- Buyer: {brandkit.get('buyer')} | Sector: {brandkit.get('sector')}\n"
            f"- Brand voice: {brandkit.get('brand_voice')}\n"
            f"- Product / services: {product.get('product_businesses_services')}\n\n"
            "WRITING RULES (from the content ruleset):\n"
            f"- Target length ~{target} words.\n"
            f"- Section sequence: {seq}\n"
            f"- H2s as questions using {ruleset['heading_rules'].get('h2_question_words')}.\n"
            f"- {'Active voice. ' if vr.get('active_voice') else ''}"
            f"{'Address the reader as you. ' if vr.get('second_person') else ''}"
            f"{'Define acronyms on first use. ' if vr.get('define_acronyms_first_use') else ''}\n"
            f"- Never use: {vr.get('banned_phrases')}\n"
            f"- Never open with: {vr.get('banned_openers')}\n"
            f"- Numbers: {vr.get('number_style')}\n"
            f"- Primary keyword: '{blocks.get('primary_keyword')}'. Place it in the H1, "
            "first 100 words, and at least one H2. Never inside parentheses.\n"
            f"- FAQ: {ruleset['faq_rules'].get('min')}-{ruleset['faq_rules'].get('max')} "
            "interrogative questions tied to the primary keyword, answers under "
            f"{ruleset['faq_rules'].get('answer_max_words')} words. Put them under a '## ...FAQ...' heading.\n"
            "- Include at least one comparison table, statistic, example, or quote.\n\n"
            "EVIDENCE: quantitative claims may cite ONLY these earned-media URLs: "
            f"{json.dumps(citable)}. Never reproduce competitor content.\n"
            f"AUTHORITY CONTEXT: {(authority or {}).get('summary', '')[:800]}\n\n"
            "Start with a single '# H1' title. Use '## ' for sections."
        )
        if prior_annotations:
            failing = [a for a in prior_annotations if a.get("result") == "fail"]
            if failing:
                lines = "\n".join(
                    f"  - [{a['category']}] {a['rule']}"
                    + (f": {a['detail']}" if a.get("detail") else "")
                    for a in failing
                )
                prompt += f"\n\nFIX THESE RUBRIC FAILURES FROM YOUR PREVIOUS DRAFT:\n{lines}"
        return prompt

    def _validate_llm(self, body, blocks, ruleset, brandkit, reference_pack, insights):
        checks = {
            "voice": (MODEL_GENERAL, "voice",
                      "Judge whether the draft matches this brand voice and flag "
                      f"deviations: {brandkit.get('brand_voice') or 'clear, precise, direct'}."),
            "active_voice": (MODEL_GENERAL, "voice",
                             "Flag sentences written in the passive voice."),
            "quotable": (MODEL_GENERAL, "geo",
                         "Flag vague or hedging passages that would not be quoted "
                         "cleanly by an AI answer engine (e.g. 'might possibly')."),
            "uniqueness": (MODEL_GENERAL, "uniqueness",
                           "Flag passages that duplicate already-published content: "
                           f"{json.dumps(insights.get('published_index', []))}."),
            "evidence": (MODEL_VERIFY, "evidence",
                         "Flag every quantitative claim not backed by these earned-"
                         f"media URLs: {json.dumps([c['url'] for c in (reference_pack or {}).get('citable', [])])}."),
            "legal": (MODEL_VERIFY, "legal",
                      f"Flag legal/compliance risks given guardrails: {blocks.get('guardrails') or 'none'}."),
        }
        results: list = []

        def run_check(name, model, category, instruction):
            log.debug("_validate_llm — starting check=%r model=%r", name, model)
            out = self.llm.structured(
                model, "You are a content guardrail checker. " + instruction,
                [{"role": "user", "content": body[:12000]}],
                "report_flags", self.LLM_CHECK_SCHEMA, MAX_TOKENS_CHECK)
            flags = out.get("flags", [])
            log.info("_validate_llm — check=%r result=%s flags=%d", name, "pass" if not flags else "fail", len(flags))
            # One entry per check type regardless of flag count — keeps denominator stable.
            # Raw flags are stored on the entry so build() can expand them into annotations.
            entry = _check(name, category, instruction.split('.')[0],
                           len(flags) == 0,
                           f"{len(flags)} issue(s)" if flags else "no issues")
            entry["flags"] = flags
            return entry

        ai_signals: list = []

        def run_ai_signal():
            out = self.llm.structured(
                MODEL_VERIFY,
                "Identify passages that read as AI-generated (uniform sentence "
                "rhythm, empty transitions, over-hedging, listy sameness, em-dash "
                "overuse). For each give the signal, an example, and a fix.",
                [{"role": "user", "content": body[:12000]}],
                "ai_signals", self.AI_SIGNAL_SCHEMA, MAX_TOKENS_CHECK)
            return out.get("signals", [])

        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = {pool.submit(run_check, n, m, c, i): n for n, (m, c, i) in checks.items()}
            ai_fut = pool.submit(run_ai_signal)
            for fut in as_completed(list(futs) + [ai_fut]):
                try:
                    if fut is ai_fut:
                        ai_signals = fut.result()
                    else:
                        results.append(fut.result())
                except Exception as exc:  # noqa: BLE001
                    results.append(_check(futs.get(fut, "check"), "system",
                                          "guardrail check", False, str(exc), "info"))
        return results, ai_signals

    @staticmethod
    def _score(checks: list) -> dict:
        graded = [c for c in checks if c["result"] in ("pass", "fail")]
        passed = sum(1 for c in graded if c["result"] == "pass")
        total = len(graded)
        pct = round(100.0 * passed / total, 1) if total else 100.0
        log.info("_score — rubric result: %d/%d checks passed (%.1f%%)", passed, total, pct)
        return {"passed": passed, "total": total, "pct": pct, "checks": checks}


# ============================================================================
# SECTION 8 — USER-FACING AGENTS
# ============================================================================

class IntentAgent:
    PARSE_SCHEMA = {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "goal": {"type": "array", "items": {"type": "string"}},
            "audience": {"type": "string"},
            "content_type": {"type": "string", "enum": CONTENT_TYPES},
            "is_optimization": {"type": "boolean"},
            "length": {"type": "string", "enum": list(LENGTHS.keys())},
            "primary_keyword": {"type": "string"},
            "secondary_keywords": {"type": "array", "items": {"type": "string"}},
            "guardrails": {"type": "string"},
            "competitive_refs": {"type": "array", "items": {"type": "string"}},
            "low_confidence_blocks": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Names of ALL blocks (required or soft) whose values you inferred "
                    "from context rather than read explicitly from the user's message. "
                    "Any inferred value must be confirmed before it is treated as final."
                ),
            },
        },
    }

    def __init__(self, llm: LLM):
        self.llm = llm

    def run(self, message: str, state: dict, prev_pending_req: Optional[str] = None,
            brandkit: Optional[dict] = None, product: Optional[dict] = None) -> dict:
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_parse = pool.submit(self._parse, message, state, prev_pending_req)
            f_reply = pool.submit(self._reply, message, state, brandkit or {}, product or {})
            parsed = f_parse.result()
            return {"updates": parsed["updates"],
                    "low_confidence": parsed["low_confidence"],
                    "reply": f_reply.result()}

    def _parse(self, message: str, state: dict, prev_pending_req: Optional[str] = None) -> dict:
        # Confirmed blocks are authoritative — never re-extract them.
        # Tentative blocks (in blocks but not completed_blocks) can be re-extracted
        # if the user is confirming or correcting them this turn.
        confirmed = {k: v for k, v in state["blocks"].items()
                     if k in state["completed_blocks"]}
        tentative = {k: v for k, v in state["blocks"].items()
                     if k not in state["completed_blocks"]}
        system = (
            "Extract content-block values from the user's message.\n"
            "HIGH-CONFIDENCE: extract values the user stated explicitly.\n"
            "INFERRED: extract values you can confidently derive from context "
            "(e.g. 'drive demo sign-ups' → goal=['generate_leads']). List inferred "
            "REQUIRED block names in `low_confidence_blocks` so they can be confirmed.\n"
            "Already confirmed (do not re-extract): " + json.dumps(confirmed)
        )
        if tentative:
            system += (
                "\nCurrently tentative — re-extract if the user confirms or corrects: "
                + json.dumps(tentative)
            )
        out = self.llm.structured(
            MODEL_GENERAL, system,
            [{"role": "user", "content": message}],
            "extract_blocks", self.PARSE_SCHEMA, MAX_TOKENS_CHECK)
        low_conf = [b for b in (out.pop("low_confidence_blocks", []) or [])
                    if b in REQUIRED_BLOCKS + SOFT_BLOCKS]
        updates = {k: v for k, v in out.items() if v not in (None, "", [])}

        # Structural guard: if the LLM extracted a value for a block that the user
        # didn't actually say in this message, it's an inference — force it into
        # low_confidence so it stays tentative and must be confirmed.
        # Exception: if the agent was specifically asking about this block last turn
        # (prev_pending_req), any reply from the user (including "yes") counts as
        # confirmation, so we trust the extracted value.
        message_lower = message.lower()
        for block in list(updates.keys()):
            if block in low_conf or block in confirmed:
                continue
            if block == prev_pending_req:
                # Agent asked about this block last turn — user is now confirming
                continue
            value = updates[block]
            value_in_message = False
            if isinstance(value, str):
                value_in_message = value.lower() in message_lower
            elif isinstance(value, list):
                value_in_message = any(
                    str(item).lower() in message_lower for item in (value or []))
            if not value_in_message:
                low_conf.append(block)

        return {"updates": updates, "low_confidence": [b for b in low_conf if b in updates]}

    def _reply(self, message: str, state: dict,
               brandkit: Optional[dict] = None, product: Optional[dict] = None) -> str:
        brandkit = brandkit or {}
        product = product or {}
        confirmed_blocks = {k: v for k, v in state["blocks"].items()
                            if k in state["completed_blocks"]}
        tentative_blocks = {k: v for k, v in state["blocks"].items()
                            if k not in state["completed_blocks"]}
        missing = [b for b in BLOCK_ORDER if b not in state["completed_blocks"]
                   and b not in tentative_blocks]
        nxt = missing[0] if missing else None
        system = (
            "You are Content Studio's intent agent. Collect the content brief "
            "conversationally — no bullet-form interrogations.\n"
            f"Brand: {brandkit.get('domain', '')} — {brandkit.get('description', '')}\n"
            f"Sector: {brandkit.get('sector', '')} | Buyer: {brandkit.get('buyer', '')}\n"
            f"Products/services: {product.get('product_businesses_services', '')}\n"
            f"Confirmed: {json.dumps(confirmed_blocks)}\n"
            f"Tentative (inferred last turn, not yet confirmed): {json.dumps(tentative_blocks)}\n"
            f"Still missing: {missing}\nNext to ask about: {nxt}\n"
            f"Required blocks: {REQUIRED_BLOCKS}. "
            f"Optional blocks (user may skip): {SOFT_BLOCKS}.\n"
            "RULES:\n"
            "1. Read the current message. If it clearly states multiple block values, "
            "   acknowledge ALL of them in one concise line before moving on "
            "   (e.g. 'Got it — topic: ..., audience: ..., content type: blog.').\n"
            "2. ALWAYS confirm inferences: if you derived ANY block value from context "
            "   rather than the user stating it explicitly, you MUST ask: "
            "   'I'm reading [block] as [value] — is that right?' "
            "   Never silently store an inferred value for any field.\n"
            "3. If there are tentative blocks and the user just confirmed them "
            "   (said 'yes', 'correct', 'that's right', etc.), acknowledge the confirmation.\n"
            "4. After handling the above, ask exactly ONE question for the next "
            "   genuinely missing block (not tentative, not confirmed).\n"
            "5. RECOMMENDATIONS: when asking about a missing block, offer a concrete "
            "   recommendation with brief reasoning rather than a blank question. Examples:\n"
            "   - content_type: 'Given your goal of [X] and [audience], I'd suggest a guide — "
            "     it ranks well for educational queries. Does that work, or would you prefer a blog/listicle?'\n"
            "   - length: 'For a [content_type] on this topic, structured (~1200 words) is a solid default; "
            "     researched (~2000 words) if you want deeper coverage. What suits your timeline?'\n"
            "   - primary_keyword: 'Based on your topic, \"[suggested term]\" looks like the most "
            "     searchable angle — would that be your primary keyword?'\n"
            "   - secondary_keywords: suggest 2-3 semantically related terms derived from the topic/audience.\n"
            "   Always frame recommendations as questions so the user can redirect.\n"
            "6. For optional blocks, let the user know they can skip.\n"
            "7. When all required blocks are confirmed and each optional block has "
            "   been asked once, give a one-paragraph brief summary and say the "
            "   brief is ready for the workplan.\n"
            f"content_type one of {CONTENT_TYPES}; length one of {list(LENGTHS)}; "
            "primary_keyword = the main search term; prompts = failing prompts "
            "from the brand's Insights; guardrails = legal/brand constraints."
        )
        return self.llm.text(MODEL_GENERAL, system,
                             state["history"] + [{"role": "user", "content": message}],
                             MAX_TOKENS_REPLY)


class WorkplanAgent:
    SCHEMA = {
        "type": "object",
        "properties": {
            "summary": {"type": "object"},
            "agent_steps": {"type": "array", "items": {"type": "string"}},
            "estimated_word_count": {"type": "integer"},
            "applied_ruleset": {"type": "string"},
        },
        "required": ["summary", "agent_steps", "estimated_word_count"],
    }

    def __init__(self, llm: LLM):
        self.llm = llm

    def run(self, state: dict, ruleset: dict, brandkit: dict,
            product: Optional[dict] = None) -> dict:
        product = product or {}
        out = self.llm.structured(
            MODEL_GENERAL,
            "Produce a content workplan. `summary` restates every block the user "
            "provided plus the brand voice. `agent_steps` lists the steps to build "
            "the outline (insights ingestion, reference grading, authority research, "
            "goal/type interpretation, ruleset application).",
            [{"role": "user", "content": json.dumps(
                {"blocks": state["blocks"],
                 "brand": {
                     "domain": brandkit.get("domain"),
                     "description": brandkit.get("description"),
                     "brand_voice": brandkit.get("brand_voice"),
                     "market_segment": brandkit.get("market_segment"),
                     "buyer": brandkit.get("buyer"),
                     "sector": brandkit.get("sector"),
                 },
                 "products_services": product.get("product_businesses_services"),
                 "ruleset": ruleset.get("name")}, indent=2)}],
            "generate_workplan", self.SCHEMA)
        out.setdefault("summary", state["blocks"])
        out.setdefault("agent_steps", [])
        out.setdefault("estimated_word_count",
                       ruleset.get("word_targets", {}).get(state["blocks"].get("length") or "structured", 1200))
        out["applied_ruleset"] = ruleset.get("name")
        return out


class OutlineAgent:
    SCHEMA = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content_type": {"type": "string"},
            "sections": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "type": {"type": "string", "enum": ["paragraph", "listicle", "table"]},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "estimated_words": {"type": "integer"}},
                "required": ["heading", "type", "key_points"]}}},
        "required": ["title", "sections"],
    }

    def __init__(self, llm: LLM):
        self.llm = llm

    def _system(self, state, ruleset, insights, reference_pack,
                brandkit: Optional[dict] = None, product: Optional[dict] = None) -> str:
        brandkit = brandkit or {}
        product = product or {}
        return (
            "Generate a content outline from the workplan, grounded in the inputs.\n"
            f"Brand: {brandkit.get('domain', '')} — {brandkit.get('description', '')}\n"
            f"Sector: {brandkit.get('sector', '')} | Buyer: {brandkit.get('buyer', '')}\n"
            f"Brand voice: {brandkit.get('brand_voice', '')}\n"
            f"Products/services: {product.get('product_businesses_services', '')}\n"
            f"Blocks: {json.dumps(state['blocks'])}\n"
            f"Section sequence to follow: {ruleset.get('section_sequence')}\n"
            f"H2s as questions: {ruleset['heading_rules'].get('h2_question_words')}\n"
            f"Target prompts: {json.dumps(state['blocks'].get('prompts'))}\n"
            f"Insights failing prompts: {json.dumps(insights.get('failing_prompts', []))}\n"
            f"Citable sources: {json.dumps([c['url'] for c in (reference_pack or {}).get('citable', [])])}\n"
            "Produce a title, content_type, and one section per sequence step "
            "(plus an FAQ section). Each section: type, key_points, estimated_words."
        )

    def run(self, state, ruleset, insights, reference_pack,
            brandkit: Optional[dict] = None, product: Optional[dict] = None) -> dict:
        return self.llm.structured(MODEL_DRAFT,
            self._system(state, ruleset, insights, reference_pack, brandkit, product),
            [{"role": "user", "content": "Generate the outline."}],
            "generate_outline", self.SCHEMA)

    def revise(self, state, instruction, ruleset, insights, reference_pack,
               brandkit: Optional[dict] = None, product: Optional[dict] = None) -> dict:
        return self.llm.structured(MODEL_DRAFT,
            self._system(state, ruleset, insights, reference_pack, brandkit, product)
            + "\nRevise the CURRENT outline per the instruction. Keep everything "
              "not mentioned.",
            [{"role": "user", "content":
              f"Current:\n{json.dumps(state['outline'], indent=2)}\n\nInstruction: {instruction}"}],
            "generate_outline", self.SCHEMA)


class EditAgent:
    def __init__(self, llm: LLM):
        self.llm = llm

    def edit_whole(self, draft_md: str, instruction: str,
                   brandkit: dict, product: Optional[dict] = None) -> str:
        product = product or {}
        return self.llm.text(MODEL_GENERAL,
            "Edit the draft. "
            f"Brand voice: {brandkit.get('brand_voice') or 'clear, precise'}. "
            f"Brand: {brandkit.get('domain', '')} — {brandkit.get('description', '')}. "
            f"Sector: {brandkit.get('sector', '')} | Buyer: {brandkit.get('buyer', '')}. "
            f"Products/services: {product.get('product_businesses_services', '')}. "
            "Apply the instruction and return the full revised Markdown.",
            [{"role": "user", "content": f"Draft:\n{draft_md}\n\nInstruction: {instruction}"}],
            MAX_TOKENS_DRAFT)


# ============================================================================
# SECTION 9 — ORCHESTRATOR
# ============================================================================

def _format_outline(outline: dict) -> str:
    """Return a human-readable outline for display in the chat."""
    title = outline.get("title", "Untitled")
    lines = [f"**{title}**\n"]
    for i, sec in enumerate(outline.get("sections") or [], 1):
        heading = sec.get("heading", "")
        est = sec.get("estimated_words", "")
        line = f"{i}. **{heading}**"
        if est:
            line += f" (~{est} words)"
        lines.append(line)
        for pt in (sec.get("key_points") or [])[:3]:
            lines.append(f"   • {pt}")
    lines.append("\nTweak it with instructions, or click **Accept outline** to start drafting.")
    return "\n".join(lines)

class Orchestrator:
    def __init__(self, llm: LLM, store: FileStore, sessions: SessionStore):
        self.llm = llm
        self.store = store
        self.sessions = sessions
        self.rule_engine = RuleEngine()
        self.intent = IntentAgent(llm)
        self.workplan = WorkplanAgent(llm)
        self.outline = OutlineAgent(llm)
        self.editor = EditAgent(llm)
        self.grader = ReferenceGrader(llm)
        self.authority = AuthoritySources(llm)
        self.draft_builder = DraftBuilder(llm, self.rule_engine)
        self.pool = ThreadPoolExecutor(max_workers=4)
        self._pipeline_log_lock = threading.Lock()

    # --- config getters -----------------------------------------------------
    def _ruleset(self): return self.store.get("content_ruleset", default_content_ruleset())
    def _brandkit(self): return self.store.get("brandkit", default_brandkit())
    def _product(self): return self.store.get("product_vertical", default_product_vertical())
    def _insights(self): return self.store.get("insights", {"failing_prompts": []})

    def _log(self, state, msg):
        state["background"]["messages"].append(f"[{now_iso()}] {msg}")
        state["background"]["messages"] = state["background"]["messages"][-20:]
        self._pipeline_log(msg)

    def _pipeline_log(self, msg: str) -> None:
        line = f"[{now_iso()}] {msg}\n"
        with self._pipeline_log_lock:
            with open(PIPELINE_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(line)

    # --- free-text router ---------------------------------------------------
    def handle_message(self, text: str, urls: Optional[list] = None) -> dict:
        """Non-streaming wrapper — used by tests and the selftest harness."""
        events: list = []
        self.handle_message_stream(text, urls or [], events.append)
        done = next((e for e in reversed(events) if e.get("type") == "done"), {})
        return {
            "reply": "".join(e.get("text", "") for e in events if e.get("type") == "delta"),
            "state": done.get("state"),
            "workplan": (done.get("state") or {}).get("workplan"),
        }

    def _intent(self, text: str, urls: list) -> dict:
        state = self.sessions.read()

        # Capture what required block the agent was waiting on from last turn.
        # Any user reply counts as an answer to it, so we clear the gate now and
        # pass the value to _parse so "yes"-style confirmations are handled correctly.
        prev_pending_req = state.get("pending_required_block")

        # Any response from the user counts as answering the soft block we asked
        # about last turn — even "none" or "skip". Always clear the gate so
        # _intent_complete can re-evaluate fresh this turn.
        pending_soft = state.get("pending_soft_block")
        if prev_pending_req or pending_soft:
            def clear_pending(s):
                s["pending_required_block"] = None
                if pending_soft and pending_soft not in s["completed_blocks"]:
                    s["completed_blocks"].append(pending_soft)
                s["pending_soft_block"] = None
            self.sessions.update(clear_pending)

        accepted, rejected = self._validate_urls(urls)

        # Capture the next missing block AFTER clearing pending so we know which
        # block the LLM reply is going to ask about. If parse fills it in the same
        # round-trip, we still defer workplan until the user's next reply.
        cur_state = self.sessions.read()
        pre_run_missing = [b for b in BLOCK_ORDER if b not in cur_state["completed_blocks"]]
        pre_run_nxt = pre_run_missing[0] if pre_run_missing else None

        result = self.intent.run(text, cur_state, prev_pending_req=prev_pending_req,
                                 brandkit=self._brandkit(), product=self._product())

        low_conf = set(result.get("low_confidence", []))

        def mut(s):
            s["history"] += [{"role": "user", "content": text},
                             {"role": "assistant", "content": result["reply"]}]
            for k, v in result["updates"].items():
                s["blocks"][k] = v
                # Low-confidence blocks are stored tentatively: the value lands in
                # blocks so the reply can reference it, but the block is NOT added
                # to completed_blocks until the user explicitly confirms it.
                if k not in s["completed_blocks"] and k not in low_conf:
                    s["completed_blocks"].append(k)
            if accepted:
                s["blocks"]["sources"] = (s["blocks"]["sources"] + accepted)[:MAX_SOURCE_URLS]
            # Set pending_required_block to the first still-missing required block.
            # This gates _intent_complete: even if _parse somehow marked everything
            # complete, we won't generate the workplan in the same turn the agent
            # asked the question — the user must reply first.
            missing_required = [b for b in REQUIRED_BLOCKS if b not in s["completed_blocks"]]
            s["pending_required_block"] = missing_required[0] if missing_required else None
            # Set pending_soft_block to what the LLM just asked about (pre_run_nxt).
            # If parse filled that block in the same round-trip, we still hold the
            # gate open — the user must reply before workplan can advance.
            if pre_run_nxt and pre_run_nxt in SOFT_BLOCKS:
                s["pending_soft_block"] = pre_run_nxt
            else:
                missing_now = [b for b in BLOCK_ORDER if b not in s["completed_blocks"]]
                nxt_now = missing_now[0] if missing_now else None
                s["pending_soft_block"] = nxt_now if nxt_now in SOFT_BLOCKS else None
            if self._intent_complete(s):
                s["phase"] = "workplan"
        state = self.sessions.update(mut)

        reply = result["reply"]
        if rejected:
            reply += f"\n\n(Skipped invalid URL(s): {', '.join(rejected)})"
        if state["phase"] == "workplan":
            return self._gen_workplan()
        return {"reply": reply, "state": self._public(state)}

    def _intent_complete(self, s) -> bool:
        # Every block — required and optional — must have been explicitly asked
        # and responded to before we move on. Soft blocks are marked complete by
        # the pending_soft_block mechanism when the user replies to each question.
        # pending_required_block being set means the agent just asked a required
        # question this turn and the user hasn't answered yet.
        # pending_soft_block being set means the LLM asked about a soft block this
        # turn — even if parse filled it in the same round-trip, we wait for the
        # user to reply before advancing to the workplan.
        if s.get("pending_required_block"):
            return False
        if s.get("pending_soft_block"):
            return False
        return all(b in s["completed_blocks"] for b in BLOCK_ORDER)

    def _gen_workplan(self) -> dict:
        wp = self.workplan.run(self.sessions.read(), self._ruleset(), self._brandkit(), self._product())
        state = self.sessions.update(lambda s: s.update({"workplan": wp}))
        b = state["blocks"]

        lines = ["Your brief is complete! Here's the workplan:\n"]
        if b.get("topic"):
            lines.append(f"**Topic:** {b['topic']}")
        goals = b.get("goal")
        if goals:
            lines.append(f"**Goal:** {', '.join(goals) if isinstance(goals, list) else goals}")
        if b.get("audience"):
            lines.append(f"**Audience:** {b['audience']}")
        ct = b.get("content_type")
        if ct:
            lines.append(f"**Type:** {ct.replace('_', ' ').title()}")
        wc = wp.get("estimated_word_count")
        if wc:
            lines.append(f"**Target length:** ~{wc:,} words")
        if b.get("primary_keyword"):
            lines.append(f"**Primary keyword:** {b['primary_keyword']}")
        kws = b.get("secondary_keywords")
        if kws:
            lines.append(f"**Secondary keywords:** {', '.join(kws)}")
        refs = b.get("competitive_refs")
        if refs:
            lines.append(f"**Competitive references:** {', '.join(refs)}")
        if b.get("guardrails"):
            lines.append(f"**Guardrails:** {b['guardrails']}")
        steps = wp.get("agent_steps") or []
        if steps:
            lines.append("\n**Planned steps:**")
            for i, step in enumerate(steps, 1):
                lines.append(f"{i}. {step}")
        lines.append("\nClick **Approve workplan** to generate the outline.")

        return {"reply": "\n".join(lines), "state": self._public(state), "workplan": wp}

    def _revise_outline(self, instruction: str) -> dict:
        revised = self.outline.revise(self.sessions.read(), instruction, self._ruleset(),
                                      self._insights(), self.store.get("reference_pack", {}),
                                      self._brandkit(), self._product())

        def mut(s):
            s["outline"] = revised
            s["history"] += [{"role": "user", "content": instruction},
                             {"role": "assistant", "content": "Outline updated."}]
        state = self.sessions.update(mut)
        reply = "Here's the updated outline:\n\n" + _format_outline(revised)
        return {"reply": reply, "state": self._public(state), "outline": revised}

    def _edit(self, instruction: str) -> dict:
        draft = self.store.get("current_draft")
        if not draft:
            return self._reply("No draft is loaded yet.")
        log.info("_edit — applying edit instruction, will re-score deterministic rubric")
        revised = self.editor.edit_whole(draft["markdown"], instruction, self._brandkit(), self._product())
        draft["markdown"] = revised
        draft["word_count"] = word_count(revised)
        draft["rubric"] = self.draft_builder._score(self.rule_engine.run(draft, self._ruleset()))
        log.info("_edit — post-edit rubric: %d/%d (%.1f%%)", draft["rubric"]["passed"], draft["rubric"]["total"], draft["rubric"]["pct"])
        self.store.set("current_draft", draft)
        state = self.sessions.update(lambda s: s["history"].extend(
            [{"role": "user", "content": instruction},
             {"role": "assistant", "content": "Applied your edit."}]))
        return {"reply": "Applied your edit. Re-ran the deterministic rubric.",
                "state": self._public(state), "draft": draft}

    # --- actions ------------------------------------------------------------
    def handle_action(self, action: str) -> dict:
        phase = self.sessions.read()["phase"]
        if action == "approve_workplan" and phase == "workplan":
            return self._approve_workplan()
        if action == "accept_outline" and phase == "outline":
            return self._accept_outline()
        if action == "mark_done" and phase == "editor":
            state = self.sessions.update(lambda s: (s.update({"phase": "done"}),
                                                    s["meta"].update({"completed_at": now_iso()})))
            return {"reply": "Marked done. The editor is read-only.",
                    "state": self._public(state)}
        return self._reply(f"Action '{action}' is not valid in phase '{phase}'.")

    def _approve_workplan(self) -> dict:
        def mut(s):
            s["phase"] = "outline"
            s["background"]["reference_grader"] = "running"
            s["background"]["authority_sources"] = "running"
            self._log(s, "Workplan approved — grading references + researching authority.")
        self.sessions.update(mut)
        self.pool.submit(self._grader_job)
        self.pool.submit(self._authority_job)
        self._await_grader(BACKGROUND_GRADER_TIMEOUT)

        outline = self.outline.run(self.sessions.read(), self._ruleset(),
                                   self._insights(), self.store.get("reference_pack", {}),
                                   self._brandkit(), self._product())
        state = self.sessions.update(lambda s: s.update({"outline": outline}))
        reply = "Workplan approved! Here's your content outline:\n\n" + _format_outline(outline)
        return {"reply": reply, "state": self._public(state), "outline": outline}

    def _accept_outline(self) -> dict:
        def mut(s):
            s["phase"] = "draft"
            s["background"]["draft_builder"] = "running"
            self._log(s, "Outline accepted — building + validating draft.")
        state = self.sessions.update(mut)
        self.pool.submit(self._draft_job)
        return {"reply": "Building your draft and running the rubric. The editor opens "
                         "automatically when it's ready.", "state": self._public(state)}

    # --- background jobs ----------------------------------------------------
    def _grader_job(self):
        try:
            pack = self.grader.run(self.sessions.read()["blocks"].get("sources", []))
            self.store.set("reference_pack", pack)
            self.sessions.update(lambda s: (s["background"].__setitem__("reference_grader", "complete"),
                self._log(s, f"Grader complete: {len(pack['graded'])} URL(s), {len(pack['citable'])} citable.")))
        except Exception as exc:  # noqa: BLE001
            self.sessions.update(lambda s: (s["background"].__setitem__("reference_grader", "failed"),
                self._log(s, f"Grader failed: {exc}")))

    def _authority_job(self):
        try:
            b = self.sessions.read()["blocks"]
            res = self.authority.run(b.get("topic"), b.get("prompts") or [])
            self.store.set("authority", res)
            st = "complete" if res.get("ok") else "failed"
            self.sessions.update(lambda s: (s["background"].__setitem__("authority_sources", st),
                self._log(s, f"Authority sources {st}.")))
        except Exception as exc:  # noqa: BLE001
            self.sessions.update(lambda s: (s["background"].__setitem__("authority_sources", "failed"),
                self._log(s, f"Authority failed: {exc}")))

    def _draft_job(self):
        RUBRIC_TARGET = 90.0
        MAX_ATTEMPTS = 3
        try:
            s0 = self.sessions.read()
            best_draft: Optional[dict] = None

            for attempt in range(1, MAX_ATTEMPTS + 1):
                prior = best_draft["annotations"] if best_draft else None
                draft = self.draft_builder.build(
                    s0["outline"], s0["blocks"], self._ruleset(), self._brandkit(),
                    self._product(), self.store.get("reference_pack", {}),
                    self.store.get("authority", {}), self._insights(),
                    prior_annotations=prior)
                pct = draft["rubric"]["pct"]
                log.info("_draft_job — attempt %d/%d: rubric %.1f%%", attempt, MAX_ATTEMPTS, pct)
                attempt_msg = (
                    f"Draft attempt {attempt}/{MAX_ATTEMPTS}: rubric {pct:.1f}% "
                    f"({draft['rubric']['passed']}/{draft['rubric']['total']} checks)."
                )
                self.sessions.update(lambda s, m=attempt_msg: self._log(s, m))
                for fc in [c for c in draft["rubric"].get("checks", []) if c["result"] == "fail"]:
                    detail = fc.get("detail", "")
                    self._pipeline_log(
                        f"  RUBRIC FAIL [{fc['category'].upper()}] {fc['rule']}"
                        + (f" — {detail}" if detail else "")
                    )
                passing = [c["rule"] for c in draft["rubric"].get("checks", []) if c["result"] == "pass"]
                if passing:
                    self._pipeline_log(f"  RUBRIC PASS — {', '.join(passing)}")
                if best_draft is None or pct > best_draft["rubric"]["pct"]:
                    best_draft = draft
                if pct >= RUBRIC_TARGET:
                    log.info("_draft_job — rubric ≥%.0f%% reached on attempt %d.", RUBRIC_TARGET, attempt)
                    break
                if attempt < MAX_ATTEMPTS:
                    log.info("_draft_job — rubric %.1f%% < %.0f%%; retrying with annotation guidance.",
                             pct, RUBRIC_TARGET)

            draft = best_draft
            self.store.set("current_draft", draft)
            fname = f"draft_{s0['session_id'][:8]}_{int(time.time())}.md"
            with open(os.path.join(self.store.drafts_dir, fname), "w", encoding="utf-8") as fh:
                fh.write(draft["markdown"])
            self.sessions.update(lambda s: (s["background"].__setitem__("draft_builder", "complete"),
                s.update({"phase": "editor"}),
                self._log(s, f"Draft built: {draft['word_count']} words, rubric "
                             f"{draft['rubric']['passed']}/{draft['rubric']['total']} "
                             f"({draft['rubric']['pct']}%), {len(draft['ai_signals'])} AI-signal note(s).")))
        except Exception as exc:  # noqa: BLE001
            self.store.delete("current_draft")
            self.sessions.update(lambda s: (s["background"].__setitem__("draft_builder", "failed"),
                s.update({"phase": "outline"}),
                self._log(s, f"Draft failed, reverted to outline: {exc}")))

    def _await_grader(self, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.sessions.read()["background"]["reference_grader"] in ("complete", "failed", "idle"):
                return
            time.sleep(0.5)

    # --- export -------------------------------------------------------------
    def export(self, fmt: str) -> tuple:
        draft = self.store.get("current_draft")
        if not draft:
            return "text/plain", b"no draft", "none.txt"
        md = draft["markdown"]
        slug = draft.get("url_slug") or "draft"
        if fmt == "md":
            return "text/markdown", md.encode(), f"{slug}.md"
        if fmt == "txt":
            return "text/plain", re.sub(r"[#*`>]", "", md).encode(), f"{slug}.txt"
        if fmt == "html":
            body = html.escape(md)
            page = f"<!doctype html><meta charset=utf-8><title>{html.escape(draft['title'])}</title><pre>{body}</pre>"
            return "text/html", page.encode(), f"{slug}.html"
        # DOCX / PDF would need python-docx / reportlab — out of stdlib scope here.
        return "text/plain", b"unsupported format (md/txt/html only in this prototype)", "err.txt"

    # --- streaming infrastructure -------------------------------------------
    def _stream_llm(self, model: str, system: str, messages: list,
                    max_tokens: int, send_event: Callable) -> str:
        def on_token(tok):
            send_event({"type": "delta", "text": tok})
        return self.llm.stream_text(model, system, messages, max_tokens, on_token)

    def _classify_intent(self, text: str, context: str) -> str:
        """Lightweight intent classification: APPROVE, REVISE, or DISCUSS."""
        result = self.llm.text(
            MODEL_GENERAL,
            f"Classify this user message given the context: {context}. "
            "Reply with exactly one word — APPROVE (they want to proceed), "
            "REVISE (they want changes), or DISCUSS (questions/unclear).",
            [{"role": "user", "content": text[:500]}],
            max_tokens=10)
        r = result.strip().upper().split()[0] if result.strip() else "DISCUSS"
        return r if r in ("APPROVE", "REVISE") else "DISCUSS"

    # --- streaming message handler ------------------------------------------
    def handle_message_stream(self, text: str, urls: Optional[list],
                              send_event: Callable) -> None:
        try:
            phase = self.sessions.read()["phase"]
            if phase == "intent":
                self._stream_intent(text, urls or [], send_event)
            elif phase == "workplan":
                self._stream_workplan_phase(text, send_event)
            elif phase == "outline":
                self._stream_outline_phase(text, send_event)
            elif phase == "editor":
                self._stream_editor_phase(text, send_event)
            elif phase == "draft":
                self._stream_llm(MODEL_GENERAL,
                    PERSONA_SYSTEM + " The draft is being built in the background. "
                    "Reassure the user warmly and briefly.",
                    [{"role": "user", "content": text}], 150, send_event)
            elif phase == "done":
                self._stream_llm(MODEL_GENERAL,
                    PERSONA_SYSTEM + " This content session is complete and read-only. "
                    "Respond warmly and briefly.",
                    [{"role": "user", "content": text}], 150, send_event)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            send_event({"type": "delta", "text": f"\n\n*(Something went wrong: {exc})*"})
        finally:
            send_event({"type": "done", "state": self._public(self.sessions.read())})

    def _stream_intent(self, text: str, urls: list, send_event: Callable) -> None:
        # Mark the soft block asked last turn as complete (any response counts)
        state = self.sessions.read()
        # Capture which required block the agent asked about last turn so _parse
        # can treat a "yes"-style reply as an explicit confirmation of that block.
        prev_pending_req = state.get("pending_required_block")
        pending = state.get("pending_soft_block")
        # Always clear pending_soft_block on any user reply — even if the block was
        # already filled by parse last turn (we still held the gate open there).
        if pending:
            def mark_pending(s):
                if pending not in s["completed_blocks"]:
                    s["completed_blocks"].append(pending)
                s["pending_soft_block"] = None
            self.sessions.update(mark_pending)

        accepted, rejected = self._validate_urls(urls)
        state = self.sessions.read()
        missing = [b for b in BLOCK_ORDER if b not in state["completed_blocks"]]
        nxt = missing[0] if missing else None

        bk = self._brandkit()
        pv = self._product()
        system = (
            PERSONA_SYSTEM + "\n\n"
            "You are collecting a content brief, one block at a time.\n"
            f"Brand: {bk.get('domain', '')} — {bk.get('description', '')}\n"
            f"Sector: {bk.get('sector', '')} | Buyer: {bk.get('buyer', '')}\n"
            f"Products/services: {pv.get('product_businesses_services', '')}\n"
            f"Already collected: {json.dumps(state['blocks'])}\n"
            f"Still missing: {missing}\n"
            f"Next block to ask about: {nxt}\n"
            f"Required blocks: {REQUIRED_BLOCKS}\n"
            f"Optional blocks (user may skip): {SOFT_BLOCKS}\n"
            "Rules:\n"
            "1. Acknowledge what the user just said warmly and naturally.\n"
            "2. ALWAYS confirm inferences: if you derived ANY block value from context rather "
            "   than the user stating it explicitly, ask 'I'm reading [block] as [value] — "
            "   is that right?' before treating it as confirmed. Never silently accept an inference.\n"
            "3. Ask exactly ONE question about the next missing block. Never ask multiple at once.\n"
            "4. RECOMMENDATIONS: instead of blank open-ended questions, offer a context-aware "
            "   recommendation with brief reasoning and let the user redirect. Examples:\n"
            "   - content_type: 'For a B2B audience focused on leads, a guide typically works well — "
            "     or would you prefer a blog post or listicle?'\n"
            "   - length: 'Structured (~1,200 words) is usually right for a guide like this; "
            "     I could go deeper at researched (~2,000). Which fits your timeline?'\n"
            "   - primary_keyword: 'Based on your topic, \"[term]\" seems like the most searchable "
            "     angle — does that match what you're targeting?'\n"
            "   - secondary_keywords: suggest 2-3 semantically related terms with a brief rationale.\n"
            "   Always phrase recommendations as questions so the user stays in control.\n"
            "5. For optional blocks, make clear they can say 'skip'.\n"
            "6. When nothing is missing, give a warm 1-paragraph summary of the full brief.\n"
            f"content_type options: {CONTENT_TYPES}. length options: {list(LENGTHS)}. "
            "primary_keyword = the main SEO search term. "
            "guardrails = legal or brand constraints."
        )
        messages = state["history"] + [{"role": "user", "content": text}]

        # Parse blocks and stream reply in parallel
        with ThreadPoolExecutor(max_workers=1) as pool:
            parse_fut = pool.submit(self.intent._parse, text, state, prev_pending_req)
            reply_text = self._stream_llm(MODEL_GENERAL, system, messages,
                                          MAX_TOKENS_REPLY, send_event)
            parse_result = parse_fut.result()  # {"updates": {...}, "low_confidence": [...]}

        if rejected:
            send_event({"type": "delta",
                        "text": f"\n\n*(Skipped invalid URLs: {', '.join(rejected)})*"})

        def mut(s):
            s["history"] += [{"role": "user", "content": text},
                             {"role": "assistant", "content": reply_text}]
            block_updates = parse_result.get("updates", {})
            low_conf = set(parse_result.get("low_confidence", []))
            for k, v in block_updates.items():
                s["blocks"][k] = v
                if k not in s["completed_blocks"] and k not in low_conf:
                    s["completed_blocks"].append(k)
            if accepted:
                s["blocks"]["sources"] = (s["blocks"]["sources"] + accepted)[:MAX_SOURCE_URLS]
            missing_now = [b for b in BLOCK_ORDER if b not in s["completed_blocks"]]
            nxt_now = missing_now[0] if missing_now else None
            # If the LLM asked about a soft block this turn (nxt), keep that gate
            # open even if parse filled it in the same round-trip. Workplan must
            # wait until the user replies on the next turn.
            if nxt is not None and nxt in SOFT_BLOCKS:
                s["pending_soft_block"] = nxt
            else:
                s["pending_soft_block"] = nxt_now if nxt_now in SOFT_BLOCKS else None
            # Track which required block is still pending so the next turn's _parse
            # knows to trust a "yes"-style confirmation for that specific block.
            missing_req = [b for b in REQUIRED_BLOCKS if b not in s["completed_blocks"]]
            s["pending_required_block"] = missing_req[0] if missing_req else None
            if self._intent_complete(s):
                s["phase"] = "workplan"
        state = self.sessions.update(mut)

        if state["phase"] == "workplan":
            self._stream_gen_workplan(send_event, state["history"])

    def _stream_gen_workplan(self, send_event: Callable, history: list) -> None:
        state = self.sessions.read()
        wp = self.workplan.run(state, self._ruleset(), self._brandkit(), self._product())
        self.sessions.update(lambda s: s.update({"workplan": wp}))
        state = self.sessions.read()

        system = (
            PERSONA_SYSTEM + "\n\n"
            "The user has finished giving you their content brief. You have an internal workplan. "
            "Present it naturally — not as a form dump. Walk through what you'll create and why. "
            "Show all key details so the user can verify them. Make it feel like a real strategic "
            "moment. End with a genuine invitation to approve or suggest changes. "
            "Vary your phrasing every time — never use the same opener twice."
        )
        wp_data = {
            "blocks": state["blocks"],
            "estimated_word_count": wp.get("estimated_word_count"),
            "planned_steps": wp.get("agent_steps", []),
            "ruleset": wp.get("applied_ruleset"),
        }
        messages = history[-6:] + [{"role": "user",
            "content": f"Here is the brief and workplan data:\n{json.dumps(wp_data, indent=2)}"}]
        send_event({"type": "separator"})
        self._stream_llm(MODEL_GENERAL, system, messages, MAX_TOKENS_REPLY * 2, send_event)

    def _stream_workplan_phase(self, text: str, send_event: Callable) -> None:
        state = self.sessions.read()
        pending_q = state.get("pending_question", False)

        with ThreadPoolExecutor(max_workers=1) as pool:
            intent_fut = pool.submit(self._classify_intent, text,
                                     "user reviewing a content workplan")
            if pending_q:
                system = (
                    PERSONA_SYSTEM + "\n\n"
                    f"Workplan context: {json.dumps(state.get('workplan', {}))}\n"
                    "You asked the user a clarifying question last turn and they are now answering it. "
                    "Acknowledge their answer naturally. Do NOT say you are generating the outline yet — "
                    "ask if they are happy with the workplan or would like to change anything."
                )
            else:
                system = (
                    PERSONA_SYSTEM + "\n\n"
                    f"Workplan context: {json.dumps(state.get('workplan', {}))}\n"
                    "The user is responding to the workplan you presented. "
                    "If they're approving, respond with warm enthusiasm and say you're generating the outline. "
                    "If they want changes, acknowledge thoughtfully and say what you'd need to know. "
                    "Keep this response brief — you're about to show them the outcome."
                )
            messages = state["history"][-4:] + [{"role": "user", "content": text}]
            self._stream_llm(MODEL_GENERAL, system, messages, 200, send_event)
            intent = intent_fut.result()

        if pending_q:
            # Answer received — clear flag; user must explicitly re-confirm before proceeding.
            self.sessions.update(lambda s: s.update({"pending_question": False}))
            return

        if intent == "APPROVE":
            self._do_approve_workplan(send_event)
        elif intent == "DISCUSS":
            self.sessions.update(lambda s: s.update({"pending_question": True}))

    def _do_approve_workplan(self, send_event: Callable) -> None:
        def mut(s):
            s["phase"] = "outline"
            s["background"]["reference_grader"] = "running"
            s["background"]["authority_sources"] = "running"
            self._log(s, "Workplan approved — grading references + researching authority.")
        self.sessions.update(mut)
        self.pool.submit(self._grader_job)
        self.pool.submit(self._authority_job)

        send_event({"type": "delta", "text": "\n\n*(Researching sources and grading references…)*"})
        self._await_grader(BACKGROUND_GRADER_TIMEOUT)

        outline = self.outline.run(self.sessions.read(), self._ruleset(),
                                   self._insights(), self.store.get("reference_pack", {}),
                                   self._brandkit(), self._product())
        self.sessions.update(lambda s: s.update({"outline": outline}))

        system = (
            PERSONA_SYSTEM + "\n\n"
            "You just generated a content outline. Present ONLY the outline itself — do NOT "
            "repeat anything already confirmed in the workplan (topic, goal, audience, keyword, "
            "content type, length, guardrails). The user already knows all of that. Jump straight "
            "to the structure. Walk through each section with a brief editorial note on why it "
            "sits where it does. Mention 1-2 interesting structural choices. Show every section "
            "with its heading, key points, and estimated word count. End with a genuine invitation "
            "to refine any section or proceed when ready. Vary your opening — never the same twice."
        )
        messages = [{"role": "user",
            "content": f"Generated outline:\n{json.dumps(outline, indent=2)}"}]
        send_event({"type": "separator"})
        self._stream_llm(MODEL_DRAFT, system, messages, MAX_TOKENS_REPLY * 2, send_event)

    def _stream_outline_phase(self, text: str, send_event: Callable) -> None:
        state = self.sessions.read()
        pending_q = state.get("pending_question", False)

        with ThreadPoolExecutor(max_workers=1) as pool:
            intent_fut = pool.submit(self._classify_intent, text,
                                     "user reviewing a content outline")
            if pending_q:
                system = (
                    PERSONA_SYSTEM + "\n\n"
                    f"Current outline: {json.dumps(state.get('outline', {}))}\n"
                    "You asked the user a clarifying question last turn and they are now answering it. "
                    "Acknowledge their answer naturally. If they've asked for a change, note it briefly. "
                    "Do NOT say you are building the draft — end by asking if they are ready to proceed "
                    "or if there's anything else they'd like to tweak."
                )
            else:
                system = (
                    PERSONA_SYSTEM + "\n\n"
                    f"Current outline: {json.dumps(state.get('outline', {}))}\n"
                    "The user is responding to the content outline. "
                    "If they're approving, say you're building the draft now (it takes a moment). "
                    "If they want changes, acknowledge and say you're revising. "
                    "If unclear, ask one clarifying question."
                )
            messages = state["history"][-4:] + [{"role": "user", "content": text}]
            self._stream_llm(MODEL_GENERAL, system, messages, 200, send_event)
            intent = intent_fut.result()

        if pending_q:
            # Answer received — clear flag and apply any revisions, but don't advance to
            # draft yet. The user must explicitly confirm again on the next turn.
            self.sessions.update(lambda s: s.update({"pending_question": False}))
            if intent == "REVISE":
                revised = self.outline.revise(state, text, self._ruleset(),
                                              self._insights(), self.store.get("reference_pack", {}),
                                              self._brandkit(), self._product())
                self.sessions.update(lambda s: s.update({"outline": revised}))
                send_event({"type": "separator"})
                send_event({"type": "delta",
                            "text": "Updated the outline:\n\n" + _format_outline(revised)})
            return

        if intent == "APPROVE":
            def mut(s):
                s["phase"] = "draft"
                s["background"]["draft_builder"] = "running"
                self._log(s, "Outline accepted — building + validating draft.")
            self.sessions.update(mut)
            self.pool.submit(self._draft_job)
        elif intent == "REVISE":
            revised = self.outline.revise(state, text, self._ruleset(),
                                          self._insights(), self.store.get("reference_pack", {}),
                                          self._brandkit(), self._product())
            self.sessions.update(lambda s: s.update({"outline": revised}))
            send_event({"type": "separator"})
            send_event({"type": "delta",
                        "text": "Here's the updated outline:\n\n" + _format_outline(revised)})
        else:  # DISCUSS — agent asked a clarifying question
            self.sessions.update(lambda s: s.update({"pending_question": True}))

    def _stream_editor_phase(self, text: str, send_event: Callable) -> None:
        done_signals = {"done", "finished", "complete", "publish", "ship",
                        "all good", "looks good", "perfect", "mark done", "that's it"}
        is_done = any(sig in text.lower() for sig in done_signals)

        draft = self.store.get("current_draft")
        if not draft:
            self._stream_llm(MODEL_GENERAL,
                PERSONA_SYSTEM + " There is no draft loaded yet.",
                [{"role": "user", "content": text}], 150, send_event)
            return

        if is_done:
            self.sessions.update(lambda s: (s.update({"phase": "done"}),
                                            s["meta"].update({"completed_at": now_iso()})))
            self._stream_llm(MODEL_GENERAL,
                PERSONA_SYSTEM + " The user has just finished their content piece. "
                "Congratulate them warmly and briefly. Mention the export options available.",
                [{"role": "user", "content": text}], 200, send_event)
        else:
            revised_md = self.editor.edit_whole(draft["markdown"], text, self._brandkit(), self._product())
            draft["markdown"] = revised_md
            draft["word_count"] = word_count(revised_md)
            draft["rubric"] = self.draft_builder._score(
                self.rule_engine.run(draft, self._ruleset()))
            self.store.set("current_draft", draft)
            system = (
                PERSONA_SYSTEM + "\n\n"
                f"You just applied an edit to the draft. New word count: {draft['word_count']}. "
                "In 1-2 sentences, acknowledge the change warmly. Do not reproduce the draft."
            )
            self._stream_llm(MODEL_GENERAL, system,
                             [{"role": "user", "content": text}], 150, send_event)
            send_event({"type": "separator"})
            send_event({"type": "delta",
                        "text": f"**Updated draft** · {draft['word_count']} words\n\n{revised_md}"})

    # --- helpers ------------------------------------------------------------
    def _validate_urls(self, urls):
        ok, bad = [], []
        for u in urls:
            u = (u or "").strip()
            if not u:
                continue
            (ok if re.match(r"^https?://[^\s]+\.[^\s]+", u) else bad).append(u)
        return ok, bad

    def _reply(self, msg): return {"reply": msg, "state": self._public(self.sessions.read())}

    def _public(self, state):
        pub = dict(state)
        pub["history"] = state["history"][-20:]
        pub["current_draft"] = self.store.get("current_draft")
        pub["ruleset_name"] = self._ruleset().get("name")
        return pub


# ============================================================================
# SECTION 10 — HTTP SERVER + UI
# ============================================================================

INDEX_HTML = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Content Studio</title>
<style>
 :root{--bg:#0e1014;--panel:#15181f;--line:#242833;--ink:#e8eaf0;--dim:#8b93a5;
   --acc:#c8a24a;--ok:#74d39a;--warn:#e6b450;--fail:#e8857a;}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
   font:15px/1.55 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif}
 .wrap{display:grid;grid-template-columns:1fr 340px;height:100vh}
 .chat{display:flex;flex-direction:column;border-right:1px solid var(--line)}
 .hd{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;
   align-items:baseline;gap:12px}
 .hd h1{font:600 16px/1 ui-serif,Georgia,serif;margin:0;letter-spacing:.2px}
 .hd small{color:var(--dim)}
 .log{flex:1;overflow:auto;padding:20px}
 .msg{margin:0 0 12px;max-width:78%;padding:9px 13px;border-radius:13px;white-space:pre-wrap}
 .user{margin-left:auto;background:#283150} .bot{background:#191d27}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
   padding:12px 14px;margin:0 0 12px}
 .card h4{margin:0 0 8px;font:600 11px/1 ui-sans-serif;letter-spacing:.08em;
   text-transform:uppercase;color:var(--dim)}
 .card pre{margin:0;white-space:pre-wrap;font:13px/1.5 ui-monospace,monospace}
 .composer{display:flex;gap:8px;padding:14px;border-top:1px solid var(--line)}
 .composer input{flex:1;padding:11px 13px;border-radius:9px;border:1px solid #2a3040;
   background:#0b0d12;color:var(--ink)} .composer input:focus{outline:2px solid var(--acc)}
 button{padding:10px 14px;border-radius:9px;border:1px solid #36405c;background:#1d2436;
   color:#dce3f5;cursor:pointer;font:inherit} button:hover{background:#27314a}
 button:focus-visible{outline:2px solid var(--acc)}
 .side{padding:18px;overflow:auto}
 .side h3{margin:18px 0 8px;font:600 11px/1;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
 .side h3:first-child{margin-top:0}
 .rail{display:flex;flex-direction:column;gap:2px}
 .step{display:flex;align-items:center;gap:9px;padding:5px 0;color:var(--dim);font-size:13px}
 .step .dot{width:9px;height:9px;border-radius:50%;background:#2c3342;flex:none}
 .step.on{color:var(--ink)} .step.on .dot{background:var(--acc);box-shadow:0 0 0 3px #c8a24a22}
 .step.done .dot{background:var(--ok)}
 .blk div{font-size:13px;padding:3px 0;border-bottom:1px solid #1b1f29}
 .blk b{color:var(--dim);font-weight:500}
 .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;margin:0 6px 6px 0;border:1px solid #2a3040}
 .pill.ok{color:var(--ok)} .pill.run{color:var(--warn)} .pill.fail{color:var(--fail)}
 .score{font:600 22px/1 ui-serif,Georgia,serif}
 .annot{font-size:12px;border-left:3px solid var(--warn);padding:4px 9px;margin:4px 0;background:#1b1a12}
 .annot.blocker{border-color:var(--fail)}
 .aisig{font-size:12px;border-left:3px solid #6b8cce;padding:4px 9px;margin:4px 0;background:#141823}
 .act button{width:100%;margin:6px 0} small{color:var(--dim)}
 .exp{display:flex;gap:6px;flex-wrap:wrap} .exp a{font-size:12px;color:#9fb2e0;text-decoration:none;
   border:1px solid #2a3040;padding:4px 8px;border-radius:7px}
 .thinking{display:inline-flex;gap:5px;padding:4px 2px}
 .thinking span{width:7px;height:7px;border-radius:50%;background:var(--dim);animation:throb 1.2s infinite}
 .thinking span:nth-child(2){animation-delay:.2s}
 .thinking span:nth-child(3){animation-delay:.4s}
 @keyframes throb{0%,80%,100%{transform:scale(.6);opacity:.4}40%{transform:scale(1);opacity:1}}
</style></head><body><div class=wrap>
 <div class=chat>
  <div class=hd><h1>Content Studio</h1><small id=rs>—</small></div>
  <div class=log id=log></div>
  <div class=composer>
   <input id=t placeholder="Write a message. In intent, add URLs after | comma-separated">
   <button onclick=send()>Send</button>
  </div>
 </div>
 <div class=side>
  <h3>Stage</h3>
  <div class=rail id=rail></div>
  <h3>Brief</h3><div class=blk id=blk></div>
  <h3>Background</h3><div id=bg></div>
  <h3>Rubric</h3><div id=rub><small>Runs after the draft is built.</small></div>
  <h3>Export</h3><div class=exp id=exp><small>Available after draft.</small></div>
  <h3>Log</h3><div id=lg><small>—</small></div>
  <button onclick=reset() style=margin-top:16px>Reset session</button>
 </div></div>
<script>
const PH=["intent","workplan","outline","draft","editor","done"];
let busy=false,shownDraft=null;
const el=id=>document.getElementById(id);
function mdToHtml(t){return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/\*(.+?)\*/g,'<em>$1</em>').replace(/\n/g,'<br>');}
function makeBubble(r){const d=document.createElement('div');d.className='msg '+(r==='user'?'user':'bot');el('log').appendChild(d);el('log').scrollTop=1e9;return d;}
function bubble(r,x){const d=makeBubble(r);if(r==='bot')d.innerHTML=mdToHtml(x);else d.textContent=x;return d;}
function card(t,b){const d=document.createElement('div');d.className='card';const h=document.createElement('h4');h.textContent=t;const p=document.createElement('pre');p.textContent=b;d.append(h,p);el('log').appendChild(d);el('log').scrollTop=1e9;}
async function api(p,b){const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});return r.json();}
async function send(){
  if(busy)return;
  const raw=el('t').value.trim();if(!raw)return;
  let text=raw,urls=[];
  if(raw.includes('|')){const[a,b]=raw.split('|');text=a.trim();urls=b.split(',').map(s=>s.trim()).filter(Boolean);}
  el('t').value='';bubble('user',raw);busy=true;
  // Show thinking indicator immediately
  const thinkEl=makeBubble('bot');
  thinkEl.innerHTML='<div class="thinking"><span></span><span></span><span></span></div>';
  el('log').scrollTop=1e9;
  let botDiv=null,fullText='',usedThink=false,streamDone=false;
  try{
    const resp=await fetch('/api/message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,urls})});
    const reader=resp.body.getReader();
    const dec=new TextDecoder();
    let buf='';
    while(!streamDone){
      const{done,value}=await reader.read();
      if(done)break;
      buf+=dec.decode(value,{stream:true});
      const parts=buf.split('\n\n');buf=parts.pop();
      for(const part of parts){
        if(!part.startsWith('data: '))continue;
        try{
          const ev=JSON.parse(part.slice(6));
          if(ev.type==='delta'){
            if(!usedThink&&!botDiv){usedThink=true;thinkEl.innerHTML='';botDiv=thinkEl;}
            else if(!botDiv){botDiv=makeBubble('bot');}
            fullText+=ev.text;
            botDiv.innerHTML=mdToHtml(fullText);
            el('log').scrollTop=1e9;
          }else if(ev.type==='separator'){
            botDiv=null;fullText='';
          }else if(ev.type==='done'){
            render(ev.state);
            streamDone=true;  // stop reading — server is done
          }
        }catch(e){}
      }
    }
    // If no tokens arrived, remove thinking bubble
    if(!usedThink)thinkEl.remove();
  }catch(e){thinkEl.innerHTML=mdToHtml('*(Connection error: '+e+')*');}
  busy=false;
}
function reset(){api('/api/reset').then(r=>{el('log').innerHTML='';shownDraft=null;render(r.state);bubble('bot','What would you like to create today?');});}
el('t').addEventListener('keydown',e=>{if(e.key==='Enter')send();});
function render(s){if(!s)return;
 el('rs').textContent='ruleset: '+(s.ruleset_name||'—');
 const i=PH.indexOf(s.phase);
 el('rail').innerHTML=PH.map((p,n)=>`<div class="step ${n<i?'done':n===i?'on':''}"><span class=dot></span>${p}</div>`).join('');
 const b=s.blocks||{};const upd=(b.updates&&typeof b.updates==='object')?b.updates:{};const done=new Set(s.completed_blocks||[]);const BK=['topic','goal','audience','content_type','length','primary_keyword','secondary_keywords','prompts','guardrails','sources','competitive_refs'];const BL={topic:'Topic',goal:'Goal',audience:'Audience',content_type:'Content type',length:'Length',primary_keyword:'Primary keyword',secondary_keywords:'Secondary keywords',prompts:'Target prompts',guardrails:'Guardrails',sources:'Sources',competitive_refs:'Competitive refs'};el('blk').innerHTML=BK.map(k=>{let v=b[k]!=null?b[k]:upd[k];if(v===null||v===undefined||v===''||v===false)return null;if(Array.isArray(v)){if(!v.length)return null;v=v.join(', ');}const c=done.has(k)?'var(--ok)':'var(--acc)';return `<div style="padding:4px 0;border-bottom:1px solid #1b1f29"><b style="color:${c}">${BL[k]}:</b> ${v}</div>`;}).filter(Boolean).join('')||'<small style="color:var(--dim)">No brief filled yet.</small>';
 const g=s.background;el('bg').innerHTML=['reference_grader','authority_sources','draft_builder'].map(k=>{const st=g[k],c=st==='complete'?'ok':st==='failed'?'fail':st==='running'?'run':'';return `<span class="pill ${c}">${k.replace(/_/g,' ')}: ${st}</span>`;}).join('');
 el('lg').innerHTML=(g.messages||[]).slice(-6).map(m=>`<small>${m}</small>`).join('<br>')||'<small>—</small>';
 const d=s.current_draft;
 if(d){
  el('exp').innerHTML=['md','html','txt'].map(f=>`<a href="/api/export?fmt=${f}" download>${f.toUpperCase()}</a>`).join('');
  const r=d.rubric||{};
  el('rub').innerHTML=`<div class=score>${r.pct!=null?r.pct+'%':'—'}</div><small>${r.passed||0}/${r.total||0} checks passed</small>`
    +(d.rubric&&d.rubric.checks?'<div style="margin-top:8px">'+d.rubric.checks.filter(c=>c.result==='fail').slice(0,8).map(c=>`<div class="annot ${c.severity}">${c.category}: ${c.rule}${c.detail?(' — '+c.detail):''}</div>`).join('')+'</div>':'');
  if(shownDraft!==d.built_at){shownDraft=d.built_at;
   card('Draft · '+d.word_count+' words · '+(d.title||''),d.markdown);
   if((d.ai_signals||[]).length){const w=document.createElement('div');w.className='card';
    w.innerHTML='<h4>AI-signal review — check before publishing</h4>'+d.ai_signals.map(a=>`<div class=aisig><b>${a.signal||''}</b>${a.example?(' — "'+a.example+'"'):''}${a.fix?('<br><small>fix: '+a.fix+'</small>'):''}</div>`).join('');
    el('log').appendChild(w);el('log').scrollTop=1e9;}
  }
 }
}
async function poll(){try{const r=await fetch('/api/state');render(await r.json());}catch(e){}}
setInterval(poll,2500);
fetch('/api/state').then(r=>r.json()).then(s=>{render(s);bubble('bot','What would you like to create today?');});
</script></body></html>"""


class SessionRegistry:
    """Per-session Orchestrator cache, keyed by username/session_id."""

    def __init__(self, llm: LLM):
        self._llm = llm
        self._map: dict = {}
        self._lock = threading.Lock()

    def get(self, username: str, session_id: str) -> Orchestrator:
        key = f"{username}/{session_id}"
        with self._lock:
            if key not in self._map:
                root = _session_root(username, session_id)
                store = FileStore(root)
                seed_config(store)
                ss = SessionStore(store)
                self._map[key] = Orchestrator(self._llm, store, ss)
            return self._map[key]


class Handler(BaseHTTPRequestHandler):
    registry: SessionRegistry = None  # set in serve()

    def log_message(self, *a):
        pass

    # --- response helpers ---------------------------------------------------
    def _cors(self):
        origin = self.headers.get("Origin", "")
        if "*" in _CORS_ORIGINS:
            allowed = "*"
        elif origin in _CORS_ORIGINS:
            allowed = origin
            self.send_header("Vary", "Origin")
        else:
            allowed = next(iter(_CORS_ORIGINS), "*")
        self.send_header("Access-Control-Allow-Origin", allowed)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode())

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n).decode() or "{}") if n else {}

    # --- auth ---------------------------------------------------------------
    def _auth(self) -> Optional[str]:
        hdr = self.headers.get("Authorization", "")
        if hdr.startswith("Bearer "):
            return verify_token(hdr[7:])
        return None

    # --- routing helpers ----------------------------------------------------
    @staticmethod
    def _session_route(path: str):
        m = re.match(r"^/api/sessions/([^/]+)(?:/(.+))?$", path)
        return (m.group(1), m.group(2) or "") if m else (None, "")

    # --- HTTP verbs ---------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/api/sessions":
            u = self._auth()
            if not u:
                return self._json(401, {"error": "unauthorized"})
            return self._json(200, list_sessions(u))

        sid, action = self._session_route(path)
        if sid:
            u = self._auth()
            if not u:
                return self._json(401, {"error": "unauthorized"})
            if action == "state":
                if not _session_exists(u, sid):
                    return self._json(404, {"error": "not found"})
                orch = self.registry.get(u, sid)
                return self._json(200, orch._public(orch.sessions.read()))
            if action == "export":
                if not _session_exists(u, sid):
                    return self._json(404, {"error": "not found"})
                orch = self.registry.get(u, sid)
                fmt = "md"
                m = re.search(r"fmt=(\w+)", self.path)
                if m:
                    fmt = m.group(1)
                ctype, data, fname = orch.export(fmt)
                return self._send(200, data, ctype,
                                  {"Content-Disposition": f'attachment; filename="{fname}"'})

        return self._send(404, b"not found", "text/plain")

    def do_POST(self):
        try:
            path = self.path.split("?")[0]
            body = self._body()

            # Login — no auth required
            if path == "/api/login":
                uname = body.get("username", "")
                pw = body.get("password", "")
                if uname and USERS_MAP.get(uname) == pw:
                    return self._json(200, {"token": make_token(uname), "username": uname})
                return self._json(401, {"error": "invalid credentials"})

            # Create session
            if path == "/api/sessions":
                u = self._auth()
                if not u:
                    return self._json(401, {"error": "unauthorized"})
                sid = uuid.uuid4().hex
                orch = self.registry.get(u, sid)
                orch.sessions.read()  # creates session.json
                return self._json(200, {"session_id": sid})

            # Session-scoped endpoints
            sid, action = self._session_route(path)
            if sid:
                u = self._auth()
                if not u:
                    return self._json(401, {"error": "unauthorized"})
                if not _session_exists(u, sid):
                    return self._json(404, {"error": "not found"})
                orch = self.registry.get(u, sid)

                if action == "message":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("X-Accel-Buffering", "no")
                    self.send_header("Connection", "close")
                    self._cors()
                    self.end_headers()
                    self.close_connection = True

                    def send_event(data):
                        try:
                            self.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            pass

                    orch.handle_message_stream(
                        body.get("text", ""), body.get("urls", []), send_event)
                    return

                if action == "action":
                    return self._json(200, orch.handle_action(body.get("action", "")))

                if action == "reset":
                    return self._json(200, {"state": orch._public(orch.sessions.reset())})

            return self._send(404, b"not found", "text/plain")

        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._json(500, {"reply": f"Server error: {exc}", "error": True})


# ============================================================================
# SECTION 11 — MAIN + SELFTEST
# ============================================================================

def serve():
    if not ANTHROPIC_API_KEY:
        print("ERROR: set ANTHROPIC_API_KEY first.", file=sys.stderr)
        sys.exit(1)
    if not USERS_MAP:
        print("WARNING: No USERS configured. Set USERS=alice:pass123,bob:pass456",
              file=sys.stderr)
    llm = LLM(ANTHROPIC_API_KEY)
    Handler.registry = SessionRegistry(llm)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Content Studio at http://{HOST}:{PORT}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()


def selftest():
    """Unit-tests the deterministic rule engine + the state machine (fake LLM)."""
    global DATA_DIR, DRAFTS_DIR
    import tempfile
    DATA_DIR = tempfile.mkdtemp(prefix="cs2_")
    DRAFTS_DIR = os.path.join(DATA_DIR, "drafts")

    # ---- deterministic rule engine ----
    rules = default_content_ruleset()
    eng = RuleEngine()
    good = {
        "primary_keyword": "ai visibility",
        "markdown": ("# What Is AI Visibility For Brands\n\n"
                     "AI visibility decides whether your brand appears in AI answers. "
                     + ("word " * 120) +
                     "\n\n## Why Does AI Visibility Matter\n\nBecause buyers ask AI first.\n\n"
                     "## How Do You Improve AI Visibility\n\nDo the work.\n\n"
                     "## Frequently Asked Questions\n\n"
                     "What is AI visibility?\nWhy does it matter?\nHow is it measured?\n"
                     "When should you start?\nWho owns it?\n"),
        "meta_title": "What Is AI Visibility For Brands And Why It Matters Now",
        "meta_description": ("AI visibility decides whether your brand shows up in AI answers. "
                             "Learn what it is, why it matters, and how to measure it well today."),
        "url_slug": "what-is-ai-visibility",
        "target_words": 1200, "word_count": 140,
    }
    cg = {c["id"]: c for c in eng.run(good, rules)}
    assert cg["kw_in_h1"]["result"] == "pass", cg["kw_in_h1"]
    assert cg["kw_first_100"]["result"] == "pass"
    assert cg["faq_count"]["result"] == "pass", cg["faq_count"]
    assert cg["h2_interrogative"]["result"] == "pass", cg["h2_interrogative"]

    bad = dict(good,
               markdown="# Our Revolutionary Game-Changer\n\nIn today's digital landscape, stuff.\n\n## Overview\n\ntext.",
               meta_title="too short", primary_keyword="ai visibility")
    cb = {c["id"]: c for c in eng.run(bad, rules)}
    assert cb["no_hype"]["result"] == "fail", "should catch hype words"
    assert cb["no_filler_openers"]["result"] == "fail", "should catch filler opener"
    assert cb["kw_in_h1"]["result"] == "fail"
    assert cb["h2_interrogative"]["result"] == "fail", "non-question H2"
    print("RULE ENGINE OK — keyword, FAQ, heading, hype, filler checks all fire correctly.")

    # ---- state machine with a fake LLM ----
    class Fake:
        def text(self, model, system, messages, max_tokens=0, tools=None):
            return "Got it — what's the goal?" if "intent agent" in system else "ok"

        def stream_text(self, model, system, messages, max_tokens, on_token):
            text = self.text(model, system, messages, max_tokens)
            for ch in text:
                on_token(ch)
            return text

        def structured(self, model, system, messages, tool_name, schema, max_tokens=0):
            return {
                "extract_blocks": {"topic": "AI visibility", "goal": ["leads"],
                                   "audience": "marketers", "content_type": "guide",
                                   "length": "researched", "primary_keyword": "ai visibility"},
                "generate_workplan": {"summary": {"topic": "AI visibility"},
                                      "agent_steps": ["ingest"], "estimated_word_count": 2000},
                "generate_outline": {"title": "AI Visibility Guide", "content_type": "guide",
                                     "sections": [{"heading": "What Is It", "type": "paragraph",
                                                   "key_points": ["x"], "estimated_words": 200}]},
            }.get(tool_name, {})

    store = FileStore(DATA_DIR)
    seed_config(store)
    sessions = SessionStore(store)
    orch = Orchestrator(Fake(), store, sessions)

    store.set("k", {"a": 1}); assert store.get("k") == {"a": 1}  # atomic round-trip

    # First message fills all required blocks. Soft blocks each need their own
    # turn — the pending_soft_block mechanism marks each complete when user replies.
    orch.handle_message("Researched guide on AI visibility for marketers, leads, keyword ai visibility")
    assert sessions.read()["phase"] == "intent", "should still be collecting soft blocks"
    for _ in range(len(SOFT_BLOCKS)):
        if sessions.read()["phase"] != "intent":
            break
        orch.handle_message("none")
    st = sessions.read()
    assert st["phase"] == "workplan", st["phase"]
    assert st.get("workplan")

    orch.handle_action("approve_workplan")
    assert sessions.read()["phase"] == "outline"
    assert sessions.read()["outline"]["title"] == "AI Visibility Guide"

    assert "not valid" in orch.handle_action("mark_done")["reply"]
    print("STATE MACHINE OK — intent -> workplan -> outline, guards enforced.")
    print(f"SELFTEST PASSED (temp dir: {DATA_DIR})")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        serve()