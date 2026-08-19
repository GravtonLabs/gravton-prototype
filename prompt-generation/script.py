#!/usr/bin/env python3
"""
AI Search Visibility - Buyer Prompt Generator
=============================================

Generates a concise, realistic set of first-level buyer prompts for a brand,
from a SIGNAL_BANK file plus light web research.

Usage:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
    python generate_prompts.py --inspect        # read the file, spend nothing
    python generate_prompts.py                  # full run
    python generate_prompts.py --no-cache
"""

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    sys.exit("Run: pip install anthropic")


# =============================================================================
#  INPUT
# =============================================================================
#  Most of this is read straight out of the signal file (brand_name,
#  product_vertical, buyer segments, the vertical lens). Only fill a field in
#  here if you want to OVERRIDE the file, or the file doesn't carry it.

INPUT_FILE = "input_signals.json"
OUTPUT_DIR = "output"

OVERRIDE = {
    "brand_name":        "None",      # None = take from file
    "product_verticals": None,      # None = take from file
    "brand_url":         "https://gravton.ai/",        # file has no URL - fill this in
    "countries":         ["US"],        # file has no country - fill if it matters
    "business_type":     "auto",    # "b2b" | "b2c" | "both" | "auto"
    "known_competitors": ["Profound", "Searchable", "Otterly", "Peec"],        # optional; the web signals already name several
    "notes":             "",        # free-text steer
}


# =============================================================================
#  SCOPE  -  what to generate. No quality numbers here.
# =============================================================================

SCOPE = {
    # Which part of the buyer journey. AI search visibility is an acquisition
    # problem, so pre_purchase. None = everything in the file.
    "lifecycle":        "pre_purchase",

    # Let prompts step one move beyond the signals (see EXPANSION_BRIEF).
    "allow_expansion":  True,

    # Run the blind realism test at the end.
    "run_blind_test":   True,
}


# =============================================================================
#  SPEND CAPS  -  wallet limits, not quality settings
# =============================================================================
#  These exist to stop a runaway bill. They do not encode any belief about
#  buyers or prompts. Raise them freely; the only cost is money.

SPEND = {
    # A CAP, not a floor. Raising it never causes a search - it only allows
    # more. Whether Claude searches at all is decided by the prompt.
    # $10 per 1000 searches, so even 40 per call is cents. Kept lenient on
    # purpose: cost is not a concern here, research coverage is.
    "max_searches_per_call": 40,
    "max_chars_per_batch":   40000,  # payload size per writing call
}


# =============================================================================
#  The one threshold, and where it comes from
# =============================================================================
#  A detector run against real human text scores ~50%: chance.
#
#  Clark et al. (2021) found untrained evaluators identified GPT-3 text at
#  random chance, rising only to ~55% after training with guidelines and
#  labelled examples. A 2025 study of 63 university lecturers found humans at
#  57% and machine detectors no better. Multiple surveys report the same:
#  humans cannot beat random guessing on this task.
#
#  So chance is the ceiling, not a target to beat. If the blind test catches
#  generated prompts at or below chance, they are indistinguishable from the
#  real ones and there is nothing left to fix. Above chance means something
#  identifiable is leaking through, and the rewrite pass runs.
#
#  Sources:
#    Clark et al. 2021, "All That's Human Is Not Gold"  arxiv.org/abs/2107.00061
#    Cingillioglu et al. 2025, Int. J. Management Education
#    Survey: arxiv.org/abs/2406.15583 s3.5

INDISTINGUISHABLE = 0.50


MODELS = {
    "smart": "claude-sonnet-5",              # judgment: topics, writing, skeptic
    "cheap": "claude-haiku-4-5-20251001",    # mechanical: dedup, first-level
}

# Lenient by design: cost is not a concern here, coverage and quality are. Every
# call is floored to this output budget (see call_llm) so a stingy per-stage
# ceiling can never be the reason a response gets truncated. call_llm streams, so
# large budgets don't hit HTTP timeouts. Well within model output caps
# (Sonnet 5: 128K, Haiku 4.5: 64K).
MIN_OUTPUT_TOKENS = 32000

# The blind realism test classifies real-vs-generated samples in one call. Cap how
# many go into that single call so a large prompt set doesn't blow the output
# budget (and stall the model). A balanced subset still gives a valid rate.
BLIND_TEST_SAMPLE = 80

# How much each source is worth as evidence that a real buyer cares.
#   web                - real people, real words. Voice AND proof.
#   keyword            - real demand, stiff phrasing. Proof, no voice.
#   competitor         - proves a marketing team cares. Not a buyer.
#   template_generated - machine-made from the brand name. No proof at all.
BUYER_EVIDENCE = {"web", "keyword"}
VOICE_SOURCE   = "web"

# template_generated is excluded from BUYER_EVIDENCE above because it proves
# nothing about demand. But for AI-search visibility the brand-vs-competitor
# prompts ARE the measurement surface, whether or not anyone was observed
# searching them - a brand has to know if it surfaces for "X vs Y". Those are
# built structurally in stage 5d from the brand and competitor names instead
# of being mined from signals.


# =============================================================================
#  WHY_NO_SEARCH  -  read this if the search counter shows 0
# =============================================================================
#  Claude decides for itself whether to search. Per Anthropic's docs it
#  answers directly, without searching, when the request is "analysis of
#  content already provided in the conversation".
#
#  That is exactly what these stages look like by default: we hand over 145
#  competitor phrases and 18 forum quotes and ask for a profile. The model
#  reasonably concludes it has what it needs.
#
#  max_uses does NOT fix this. It is a ceiling on searches, not a floor.
#  There is no parameter that forces a server-side tool call.
#
#  The only lever is the prompt. So both research prompts below:
#    - state plainly what the samples CANNOT tell it
#    - list named searches to run, as instructions rather than suggestions
#    - require a "searches_run" field back, which makes skipping visible
#
#  If the counter still reads 0, check whether the call was served from cache
#  (run with --refresh-research) before touching the prompts.
#  Docs: platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
# =============================================================================


# =============================================================================
#  Briefs
# =============================================================================

#  Every brief below is built from the brand at runtime. Nothing here names a
#  product, platform or industry: worked examples steer a model hard, so a
#  hardcoded one would drag every brand toward the industry it came from.
#  Placeholders in [brackets] are filled by the model from the context it is
#  given in the same call.

def realism_rules(brand=None):
    b = brand or {}
    vendor = ", ".join(b.get("vendor_words", [])[:4]) or "[its marketing phrases]"
    buyer  = ", ".join(b.get("buyer_words", [])[:4]) or "[the words buyers use]"
    return f"""
HARD RULES for every prompt you write:

1. Plain and obvious beats clever and specific. Nuance is where fake prompts
   live. If a prompt is so specific that the details had to be invented, it is
   a bad prompt.
2. Never invent a number, price, tier name, integration, model name or
   statistic that does not appear in the evidence given to you.
3. Two qualifiers is a real person. Four is a machine talking to itself.
4. Never use vendor marketing vocabulary.
   This brand's vendors write: {vendor}
   Its buyers write:           {buyer}
   Use the second list. Never the first.
5. First-level means FIRST MESSAGE, not context-free. The test is whether the
   prompt works as the opening line of a fresh chat.
     BAD:  "I'm on the Pro plan of it right now, is the data accurate?"
           (assumes an earlier turn established the product and the plan)
     GOOD: "Is [product]'s data accurate?"
   Describing your own situation is ALLOWED and often the most realistic form,
   because it is how people actually open a chat:
     OK:   "[thing that is going well] but [thing that is going wrong], why"
     OK:   "As a [role], which [category] is worth it?"
   The line: a situation the asker STATES is fine; a situation the prompt
   ASSUMES you already know is not.
6. Write what people type into a chat assistant, not what they type into a
   search box. Full questions, natural, sometimes slightly messy. Usually short.
7. Not everything is a question. People give assistants orders too, and those
   are real prompts:
     "set up [the recurring task this category exists to do]"
     "help us build a plan for [the thing buyers plan]"
     "rewrite [our asset] so [the outcome buyers want]"
   Write these wherever a topic is something a buyer would ask AI to DO rather
   than explain.
"""


EXPANSION_BRIEF = """
You may step ONE move from a source topic, and you must name the topic you
stepped from. Four safe moves:

  SIDEWAYS  - same concern, neighbouring question.
  OBVIOUS   - the too-basic question nobody writes on a forum but everybody
              asks an AI, because AI is where you ask what you'd feel silly
              asking a human.
  CATEGORY  - the question that names no brand at all.
              shape: "is [doing this thing at all] even worth it yet"
  BEGINNER  - someone who doesn't know the category yet, asking an AI before
              they know enough to search properly.

Anything you cannot trace back to a named source topic is out of bounds.
"""


def funnel_brief(brand=None, brand_name="[the brand]"):
    b = brand or {}
    cat = b.get("what_they_sell", "[the category]")
    comps = b.get("competitors", []) or OVERRIDE.get("known_competitors") or []
    c1 = comps[0] if comps else "[competitor A]"
    c2 = comps[1] if len(comps) > 1 else "[competitor B]"
    return f"""
Label every prompt with the stage the asker is at. Judge it by WHAT THE ASKER
ALREADY KNOWS, not by how the question is worded.

Category for this run: {cat}

  top     - Feels a problem. Does not know a product category exists to solve
            it. Asks about the problem itself, names no category and no vendor.
            shape: "why is [bad outcome] happening to us"
            shape: "how do people handle [the underlying problem] these days"

  middle  - Knows the category exists. Comparing approaches, not vendors yet.
            Names the category, may name zero or many vendors, asks which type
            of thing to use or whether it is worth doing at all.
            shape: "what tools do [the job the category does]"
            shape: "is [the category] worth paying for yet"
            shape: "do [these tools] actually work"

  bottom  - Has a shortlist. Evaluating named vendors, price, accuracy, fit,
            or is ready to choose.
            shape: "is {brand_name} any good"
            shape: "{c1} vs {c2} for [a specific need]"
            shape: "cheapest [category] for [a specific size of buyer]"

Rules:
- Naming a specific vendor almost always means bottom.
- Naming the category but no vendor is usually middle.
- Naming neither is usually top.
- A prompt asking "is this category worth it at all" is middle, not top: the
  asker already knows the category exists.
- Expansion moves map loosely: "beginner" and "category" tend to land top or
  middle, "obvious" anywhere, "sideways" wherever its parent topic sat.
"""


# =============================================================================
#  Plumbing
# =============================================================================

# Filled in once the brand is known (stage 1). The filter stages need the same
# rules the writer used, and threading brand through every signature just to
# reach a string is noise, so they are built once and read from here.
BRIEFS = {"realism": realism_rules(), "funnel": funnel_brief()}


def build_briefs(brand, brand_name):
    BRIEFS["realism"] = realism_rules(brand)
    BRIEFS["funnel"] = funnel_brief(brand, brand_name)


def _load_env():
    """Load KEY=value pairs from a .env next to this script (stdlib only, no
    python-dotenv dependency). Does not overwrite vars already in the env."""
    env = Path(__file__).with_name(".env")
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
client = Anthropic()
CACHE_DIR = Path(".llm_cache")
USE_CACHE = True
CACHE_SEARCH = True     # cache search-enabled calls too
STATS = {"calls": 0, "cached": 0, "in_tok": 0, "out_tok": 0, "searches": 0}


def log(m):    print(f"  {m}", flush=True)


def searches_since(before):
    n = STATS["searches"] - before
    log(f"web searches run: {n}" + ("  <-- none, see WHY_NO_SEARCH in this file"
                                    if n == 0 else ""))
    return n
def stage(n, m): print(f"\n[{n}] {m}", flush=True)


def call_llm(system, user, model="smart", search=False, max_tokens=8000):
    model_id = MODELS[model]
    # Floor every call to a generous budget - never let a per-stage ceiling be the
    # reason output is truncated. Only raises a ceiling, so it never shrinks output.
    max_tokens = max(max_tokens, MIN_OUTPUT_TOKENS)
    key = hashlib.sha256(f"{model_id}|{search}|{system}|{user}".encode()).hexdigest()[:20]
    cf = CACHE_DIR / f"{key}.json"
    if USE_CACHE and cf.exists() and (CACHE_SEARCH or not search):
        try:
            cached = (json.loads(cf.read_text()).get("text") or "").strip()
        except (json.JSONDecodeError, OSError):
            cached = ""
        # Only serve a usable cache entry. An empty/blank one is a poisoned artifact
        # from an old truncated/paused run - ignore it and regenerate below rather
        # than handing "" to the caller's parser.
        if cached:
            STATS["cached"] += 1
            if search:
                log("served from cache - NO live search ran "
                    "(use --refresh-research to force fresh searches)")
            return cached
        log("ignoring empty cache entry - regenerating")

    messages = [{"role": "user", "content": user}]
    kwargs = {"model": model_id, "max_tokens": max_tokens, "system": system,
              "messages": messages}
    if search:
        tool = {"type": "web_search_20250305", "name": "web_search",
                "max_uses": SPEND["max_searches_per_call"]}
        # Localise results when a country is known. Two-letter ISO code.
        cc = (OVERRIDE.get("countries") or [None])[0]
        if cc and len(cc) == 2:
            tool["user_location"] = {"type": "approximate", "country": cc.upper()}
        kwargs["tools"] = [tool]

    # A server-side web_search turn can hit its per-turn tool-call limit and stop
    # with stop_reason="pause_turn" BEFORE writing the final answer. Re-send with
    # the assistant turn appended so the server resumes; accumulate text across the
    # paused segments. Capped so a misbehaving loop can't run forever.
    texts, resp = [], None
    for _ in range(20):
        err = None
        for a in range(5):
            try:
                # Stream so large max_tokens budgets don't trip the SDK's
                # non-streaming HTTP timeout; get_final_message() returns the
                # accumulated Message (stop_reason, usage, content) all the same.
                with client.messages.stream(**kwargs) as stream:
                    resp = stream.get_final_message()
                break
            except Exception as e:  # noqa: BLE001 - retry any transient API error
                err = e
                time.sleep(2 ** a)
        else:
            raise RuntimeError(f"LLM call failed: {err}")

        STATS["calls"] += 1
        STATS["in_tok"] += resp.usage.input_tokens
        STATS["out_tok"] += resp.usage.output_tokens
        # Count live web searches Claude actually ran (server-side web_search tool).
        # Anthropic reports this on usage.server_tool_use.web_search_requests; it is
        # absent/None when the turn ran no searches.
        stu = getattr(resp.usage, "server_tool_use", None)
        if stu is not None:
            STATS["searches"] += getattr(stu, "web_search_requests", 0) or 0
        texts += [b.text for b in resp.content if b.type == "text"]

        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break

    text = "\n".join(t for t in texts if t)
    if not text:
        # No text came back (a refusal, or the whole budget went to thinking on a
        # very large input). Don't crash the run and don't cache the empty - hand
        # "" back so a caller with a parse fallback degrades gracefully, and one
        # without gets a clear parse error. The warning says why.
        log(f"WARNING: model returned no text (stop_reason="
            f"{resp.stop_reason if resp else '?'}, max_tokens={max_tokens})")
        return text
    # A truncated answer (hit the token ceiling) is usually invalid JSON. Surface it
    # and DON'T cache it - the cache key ignores max_tokens, so caching a partial
    # would make every later run replay the broken output until the cache is cleared.
    if resp is not None and resp.stop_reason == "max_tokens":
        log(f"WARNING: response hit max_tokens={max_tokens} and may be truncated "
            "- not caching; raise max_tokens for this stage if parsing fails")
        return text
    CACHE_DIR.mkdir(exist_ok=True)
    cf.write_text(json.dumps({"text": text}))
    return text


def parse_json(text, fallback=None):
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for o, c in (("[", "]"), ("{", "}")):
        s, e = text.find(o), text.rfind(c)
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                continue
    if fallback is not None:
        return fallback
    raise ValueError(f"Could not parse JSON from:\n{text[:400]}")


# =============================================================================
#  Stage 0  -  read the signal bank
# =============================================================================

def load_signals(path):
    """Reads the SIGNAL_BANK format: run / context_sent / signals[]."""
    data = json.loads(Path(path).read_text())

    ctx     = data.get("context_sent", {})
    profile = ctx.get("PROFILE", {})
    run     = data.get("run", {})

    brand = {
        "brand_name": OVERRIDE["brand_name"] or profile.get("brand_name") or run.get("brand"),
        "product_verticals": OVERRIDE["product_verticals"] or
                             [profile.get("product_vertical") or run.get("vertical")],
        "brand_url":         OVERRIDE["brand_url"],
        "countries":         OVERRIDE["countries"],
        "business_type":     OVERRIDE["business_type"],
        "known_competitors": OVERRIDE["known_competitors"],
        "notes":             OVERRIDE["notes"],
        "module":            run.get("module_id"),
    }

    raw = data.get("signals") or []
    if not raw:                                   # fall back to a generic hunt
        raw = _hunt(data)

    records = []
    for r in raw:
        text = r.get("grounded_phrase") or r.get("phrase") or r.get("text")
        prov = (r.get("provenance") or r.get("source") or "").strip().lower()
        if not text or not prov:
            continue
        records.append({
            "text": text.strip(),
            "provenance": prov,
            "lifecycle": r.get("lifecycle", "pre_purchase"),
        })

    kept = [r for r in records
            if not SCOPE["lifecycle"] or r["lifecycle"] == SCOPE["lifecycle"]]

    by_prov = defaultdict(list)
    for r in kept:
        by_prov[r["provenance"]].append(r)

    return {
        "brand": brand,
        "segments": ctx.get("BUYER_SEGMENTS", []),
        "vertical_lens": ctx.get("VERTICAL_LENS", ""),
        "records": kept,
        "filtered_out": len(records) - len(kept),
        "by_provenance": dict(by_prov),
    }


def _hunt(node, out=None):
    """Fallback for files that don't use the signals[] key."""
    out = [] if out is None else out
    if isinstance(node, dict):
        if any(k in node for k in ("grounded_phrase", "phrase", "text")) and \
           any(k in node for k in ("provenance", "source")):
            out.append(node)
            return out
        for v in node.values():
            _hunt(v, out)
    elif isinstance(node, list):
        for v in node:
            _hunt(v, out)
    return out


def inspect(path):
    s = load_signals(path)
    print(f"\nFile: {path}")
    print(f"Brand: {s['brand']['brand_name']}")
    print(f"Vertical: {', '.join(v for v in s['brand']['product_verticals'] if v)}")
    print(f"Module: {s['brand'].get('module')}")
    print(f"Vertical lens: {len(s['vertical_lens'])} chars "
          f"{'(will be used for topic grouping)' if s['vertical_lens'] else '(absent)'}")
    if s["filtered_out"]:
        print(f"Filtered out by lifecycle={SCOPE['lifecycle']}: {s['filtered_out']}")

    print(f"\nSignals kept: {len(s['records'])}")
    for prov, items in sorted(s["by_provenance"].items(), key=lambda x: -len(x[1])):
        tag = ("buyer evidence" if prov in BUYER_EVIDENCE else
               "context only - cannot support a topic alone")
        print(f"\n  {prov}  ({len(items)})  [{tag}]")
        for it in items[:3]:
            print(f"      {it['text'][:88]}")

    voice = len(s["by_provenance"].get(VOICE_SOURCE, []))
    print(f"\nVoice samples available: {voice}")
    if voice < 20:
        print("  Thin. Voice profiles will lean on web search to fill gaps.")

    print(f"\nBuyer segments: {len(s['segments'])}")
    for seg in s["segments"]:
        print(f"  - {seg}")


# =============================================================================
#  Stage 1  -  brand read
# =============================================================================

def read_brand(sig):
    b = sig["brand"]
    competitor_sample = [r["text"] for r in sig["by_provenance"].get("competitor", [])]
    web_sample = [r["text"] for r in sig["by_provenance"].get(VOICE_SOURCE, [])]

    system = "You research brands for marketing teams. Factual, brief. Output JSON only."
    user = f"""Profile this brand.

Brand: {b['brand_name']}
Sells: {', '.join(v for v in b['product_verticals'] if v)}
Website: {b['brand_url'] or 'not given - search for it'}
Countries: {', '.join(b['countries']) or 'not given'}
Stated business type: {b['business_type']}
Known competitors: {', '.join(b['known_competitors']) or 'none given'}
Notes: {b['notes'] or 'none'}

Marketing copy from competitors in this space:
{json.dumps(competitor_sample, indent=2)}

What real people said online about this space:
{json.dumps(web_sample, indent=2)}

SEARCH FIRST. Do not answer from the samples alone.

The samples above cannot tell you: what this brand actually sells today, how
it is priced, who it competes with now, or how buyers talk about it outside
the handful of threads captured here. The competitor copy is marketing, and
the forum quotes are one narrow slice.

Run at least these searches before answering, and more if any come back thin:
  1. {b['brand_name']}
  2. {b['brand_name']} pricing
  3. {b['brand_name']} review OR alternatives
  4. {', '.join(v for v in b['product_verticals'] if v)} tools comparison
  5. best {', '.join(v for v in b['product_verticals'] if v)} tools {', '.join(b['countries']) or ''}
  6. one search per named competitor: {', '.join(b['known_competitors']) or 'those you find'}
  7. reddit OR forum discussion of {', '.join(v for v in b['product_verticals'] if v)}

Then answer. Keep it brief - this is context for a writing task, not a
research report.

Return JSON:
{{
  "searches_run": ["every query you actually searched"],
  "what_they_sell": "one plain sentence",
  "business_type": "b2b" | "b2c" | "both",
  "price_tier": "budget" | "mid" | "premium" | "unclear",
  "buyer_words": ["words BUYERS use - take these from the web samples above"],
  "vendor_words": ["marketing words from the competitor copy that buyers never say"],
  "competitors": ["names - the web samples above name several, include them"],
  "category_maturity": "new" | "established",
  "extra_variables": [{{"name": "...", "why_it_matters": "..."}}]
}}

For "extra_variables": 2-3 things specific to THIS industry that change how a
buyer phrases a question, which a generic checklist would miss."""

    return parse_json(call_llm(system, user, "smart", search=True))


# =============================================================================
#  Stage 2  -  voice profiles
# =============================================================================

def build_voices(sig, brand):
    web = [r["text"] for r in sig["by_provenance"].get(VOICE_SOURCE, [])]
    segments = sig["segments"] or ["general buyer"]

    system = "You study how real buyers talk by reading what they wrote. Output JSON only."
    user = f"""Brand context:
{json.dumps(brand, indent=2)}

Buyer segments the client listed:
{json.dumps(segments, indent=2)}

REAL things people wrote online about this category. This is your primary
evidence for how they talk:
{json.dumps(web, indent=2)}

SEARCH FIRST. There are only {len(web)} samples and they came from searching
this brand's own keywords, so they are skewed toward people already shopping
for a tool. They cannot tell you how someone earlier in the journey talks, and
they almost certainly do not cover every segment listed above.

Run at least these searches before answering, and more if any come back thin:
  1. reddit {', '.join(v for v in brand.get('buyer_words', [])[:2]) or 'this category'}
  2. one search per segment above that the samples do not clearly cover,
     phrased the way that segment would talk:
     "reddit [that segment's industry or role] [category]"
  3. a search for people complaining about this category or its tools
  4. a search for beginners asking what this category even is

You are collecting PHRASING, not facts. Quote what real people wrote.

KEEP THE SEGMENTS SEPARATE. The client's vertical lens states that a buyer's
industry "names a different buyer, not a different word for one" and must
never be grouped across. Follow that.

Merge two segments ONLY when they are the same role under two names (a title
and its longer form, an acronym and its expansion). Do NOT merge because two industries would ask
similar questions - buyers name their own industry when they ask, and that
phrasing is exactly what we need to capture.

Where a segment is thinly represented in the samples, search for how that
industry talks rather than folding it into another segment.

Return JSON:
[
  {{
    "segment": "name",
    "searches_run": ["every query you actually searched for this segment"],
    "merged_from": ["original segment names"],
    "why_separate": "what forces this one to stay its own segment",
    "vocabulary": "plain" | "insider",
    "words_they_use": ["their habitual words"],
    "knowledge_level": "beginner" | "informed" | "expert",
    "recurring_worry": "the one thing they keep circling back to",
    "justifies_to": "nobody" | "boss" | "client" | "board",
    "stakes": "low" | "high",
    "typical_length": "short" | "medium",
    "real_examples": ["3 near-verbatim questions from the samples above"]
  }}
]

"real_examples" must be things real people actually wrote - from the samples
above OR from what you found searching. Never from your imagination. They
matter more than the description, because the writing step copies their tone."""

    return parse_json(call_llm(system, user, "smart", search=True))


# =============================================================================
#  Stage 3  -  topics
# =============================================================================

def build_topics(sig):
    payload = {p: [r["text"] for r in items]
               for p, items in sig["by_provenance"].items()}

    lens = sig["vertical_lens"]
    system = f"""You group phrases into distinct buyer decisions.

{"The client's rules for this vertical, which override your instincts:" if lens else ""}
{lens}

Output JSON only."""

    user = f"""Group these phrases into topics. Phrases are tagged by where they came from:

  web        - real people writing in their own words
  keyword    - what people search on Google
  competitor - vendor marketing copy
  template_generated - machine-made, carries no evidence of buyer interest

{json.dumps(payload, indent=2)}

Rules:
- A topic is a buying decision, not a keyword.
- Merge topics that are the same decision worded twice.
- Record every source that backs each topic.

Return JSON:
[
  {{
    "topic": "short name",
    "what_buyers_want_to_know": "one sentence",
    "sources": ["web", "keyword", "competitor", "template_generated"],
    "evidence": ["up to 6 original phrases, verbatim"]
  }}
]"""

    topics = parse_json(call_llm(system, user, "smart", max_tokens=14000))

    for t in topics:
        srcs = set(t.get("sources", []))
        t["support"] = len(srcs & BUYER_EVIDENCE)
        t["has_voice"] = VOICE_SOURCE in srcs
        t["vendor_only"] = not (srcs & BUYER_EVIDENCE)

    # Vendor-only topics: no buyer ever said this, only a marketing team did.
    # Not deleted outright - a genuine buying criterion becomes a comparison
    # question. Everything else is marketing language and goes.
    vendor_only = [t for t in topics if t["vendor_only"]]
    real = [t for t in topics if not t["vendor_only"]]
    log(f"{len(real)} backed by buyers, {len(vendor_only)} vendor-only")

    if vendor_only:
        rescued = rescue_vendor_topics(vendor_only)
        log(f"{len(rescued)} vendor-only topics rescued as comparison questions")
        real += rescued

    # No cap and no support floor. A topic with buyer evidence behind it is a
    # topic; cutting the tail would be discarding real demand to hit a number.
    # Sorted so the strongest are written first, which matters only if a run
    # is interrupted.
    real.sort(key=lambda t: (t["support"], t["has_voice"], not t.get("rescued")),
              reverse=True)
    return real


def rescue_vendor_topics(vendor_only):
    """A vendor talking about something proves the vendor cares, not the buyer.
    Keep only those that are real buying criteria, and mark them for
    comparison-shaped prompts rather than topic-shaped ones."""
    system = "You separate genuine buying criteria from marketing language. Output JSON only."
    user = f"""These topics appear ONLY in vendor marketing copy. No buyer was
observed searching for or discussing them.

Most are marketing language. A few are real things a buyer would weigh when
choosing between vendors, even though they'd never phrase it the vendor's way.

{json.dumps([{"i": i, "topic": t["topic"],
              "what": t.get("what_buyers_want_to_know", "")}
             for i, t in enumerate(vendor_only)], indent=2)}

Return ONLY the indexes that are genuine buying criteria.
Be strict. When unsure, leave it out.

Return JSON: {{"keep": [{{"i": index, "why_a_buyer_would_care": "..."}}]}}"""

    keep = parse_json(call_llm(system, user, "smart", max_tokens=4000),
                      {"keep": []}).get("keep", [])
    out = []
    for k in keep:
        i = k.get("i")
        if isinstance(i, int) and 0 <= i < len(vendor_only):
            t = vendor_only[i]
            t["rescued"] = True
            t["why_a_buyer_would_care"] = k.get("why_a_buyer_would_care", "")
            out.append(t)
    return out


# =============================================================================
#  Stage 4  -  pair segments to topics
# =============================================================================

def pair(topics, voices):
    system = "You match buyer types to topics. Output JSON only."
    user = f"""Buyer profiles:
{json.dumps([{k: v for k, v in p.items() if k != 'real_examples'} for p in voices], indent=2)}

Topics:
{json.dumps([{"topic": t["topic"], "what": t["what_buyers_want_to_know"]}
             for t in topics], indent=2)}

For each topic list ONLY the segments that would genuinely ask about it. Skip
pairings with no reason behind them - do not fill gaps for completeness. One
segment per topic is a fine answer.

Return JSON: [{{"topic": "...", "segments": ["..."]}}]"""

    m = {x["topic"]: x["segments"] for x in
         parse_json(call_llm(system, user, "cheap", max_tokens=6000), [])}
    for t in topics:
        t["segments"] = m.get(t["topic"]) or [voices[0]["segment"]]
    return topics


# =============================================================================
#  Stage 5  -  write
# =============================================================================

def batch_by_size(topics):
    """Batch by payload size, not topic count. The real constraint is the
    context window, so measure that rather than guess a topic count."""
    batches, cur, size = [], [], 0
    for t in topics:
        n = len(json.dumps(t))
        if cur and size + n > SPEND["max_chars_per_batch"]:
            batches.append(cur); cur, size = [], 0
        cur.append(t); size += n
    if cur:
        batches.append(cur)
    return batches


def _writer_system(extra=""):
    return f"""You write the prompts real buyers type into ChatGPT.

{BRIEFS["realism"]}

{BRIEFS["funnel"]}

{extra}

Output JSON only."""


PROMPT_SCHEMA = """
Return JSON:
[
  {
    "prompt": "the prompt as typed",
    "topic": "source topic",
    "segment": "which buyer",
    "origin": "grounded" | "expanded",
    "funnel": "top" | "middle" | "bottom",
    "pass": "<filled in for you>",
    "evidence": "the phrase or topic this came from",
    "mentions_brand": true | false
  }
]"""


def _tag(items, pass_name):
    for it in items:
        if isinstance(it, dict):
            it["pass"] = pass_name
    return [it for it in items if isinstance(it, dict) and it.get("prompt")]


def write_topic_prompts(topics, voices, brand, brand_name):
    """5a. The straight read: each topic asked as a buyer would ask it."""
    vmap = {v["segment"]: v for v in voices}
    out = []
    for i, batch in enumerate(batch_by_size(topics), 1):
        needed = {s for t in batch for s in t["segments"]}
        user = f"""Brand: {brand['what_they_sell']}
Buyers say: {', '.join(brand.get('buyer_words', []))}
Buyers NEVER say: {', '.join(brand.get('vendor_words', []))}

Buyer profiles:
{json.dumps([vmap[s] for s in needed if s in vmap], indent=2)}

Topics:
{json.dumps(batch, indent=2)}

Write the prompts these topics generate. Cover each topic from every angle its
evidence supports - a topic with 6 distinct pieces of evidence is 6 different
questions, not one. Only collapse to fewer when the evidence genuinely repeats.

Where a topic is something a buyer would ask AI to DO, write the imperative
form as well as the question form.

Topics marked "rescued": true came only from vendor marketing - write those as
comparison or evaluation questions, never in the vendor's own words.
{PROMPT_SCHEMA}"""
        log(f"  topics batch {i}")
        out += _tag(parse_json(call_llm(_writer_system(), user, "smart",
                                        max_tokens=16000), []), "topic")
    return out


def write_diagnostic_prompts(topics, voices, brand):
    """5b. Every topic has a solution shape and a problem shape. Signals are
    solution-shaped (people search for tools). The problem shape is what a
    buyer types when it is going wrong for them, and it never appears in
    keyword data because it is not how people search - only how they ask."""
    vmap = {v["segment"]: v for v in voices}
    worries = [v.get("recurring_worry") for v in voices if v.get("recurring_worry")]
    extra = f"""You are writing the PROBLEM-SHAPED version of each topic.

Signals capture people looking for solutions. They miss the far more common
prompt: someone describing what is going wrong and asking why.

The shape to write:
  topic X  ->  "[the failure state of X], why"
  topic X  ->  "we tried [the obvious fix], it did not work, what now"
  topic X  ->  "[a good sign] but [a bad sign], what is going on"

What these buyers actually worry about, taken from their own words:
{json.dumps(worries, indent=2)}

Write in first person about a situation the asker states. That is realistic,
not a violation of the first-level rule.

Do NOT invent specifics. "we published a lot of content" is fine; naming a
number of articles or a quarter is not."""
    out = []
    for i, batch in enumerate(batch_by_size(topics), 1):
        needed = {s for t in batch for s in t["segments"]}
        user = f"""Brand context: {brand['what_they_sell']}
Buyers say: {', '.join(brand.get('buyer_words', []))}

Buyer profiles:
{json.dumps([vmap[s] for s in needed if s in vmap], indent=2)}

Topics:
{json.dumps([{"topic": t["topic"], "what": t["what_buyers_want_to_know"],
              "segments": t["segments"]} for t in batch], indent=2)}

For each topic, write the prompts a buyer types when this is going WRONG for
them. Skip any topic that has no failure mode.
{PROMPT_SCHEMA}"""
        log(f"  diagnostic batch {i}")
        out += _tag(parse_json(call_llm(_writer_system(extra), user, "smart",
                                        max_tokens=16000), []), "diagnostic")
    return out


def write_definitional_prompts(topics, brand, voices):
    """5c. New categories generate 'what even is this' prompts. These are
    absent from keyword data precisely because people ask AI instead of
    Google. Only worth running when the category is young."""
    if brand.get("category_maturity") != "new":
        log("category is established - skipping definitional pass")
        return []
    extra = """You are writing the DEFINITIONAL layer for a young category.

When a category is new, a large share of real prompts are people working out
what the words mean. These never appear in keyword tools, because AI is where
you ask the question you would feel silly asking a colleague.

The shapes to write:
  "what is [term]"
  "what does [acronym] stand for"
  "[term] vs [adjacent term], what is the difference"
  "what is the difference between [two things buyers confuse]"
  "do we still need [the older thing] if we do [the newer thing]"

Fill those shapes from the vocabulary of THIS category, given below. Cover the
category's own name, every acronym in it, each piece of jargon in the topic
list, and the pairs of adjacent terms a newcomer would mix up."""
    user = f"""Category: {brand['what_they_sell']}
Words used in this space: {', '.join(brand.get('buyer_words', []) + brand.get('vendor_words', []))}

Topics, as a source of the jargon that needs defining:
{json.dumps([t["topic"] for t in topics], indent=2)}

Segments: {json.dumps([v["segment"] for v in voices], indent=2)}

Write the definitional and distinction prompts. Mostly top funnel.
{PROMPT_SCHEMA}"""
    log("  definitional pass")
    return _tag(parse_json(call_llm(_writer_system(extra), user, "smart",
                                    max_tokens=12000), []), "definitional")


def write_brand_prompts(topics, brand, brand_name, voices):
    """5d. Structural, not evidence-mined. For visibility tracking the
    brand-vs-competitor prompts are the measurement surface - a brand needs to
    know whether it surfaces for 'X vs Y' regardless of observed volume."""
    comps = brand.get("competitors", []) or OVERRIDE["known_competitors"]
    if not comps:
        log("no competitors known - skipping brand pass")
        return []
    extra = f"""You are writing the BRAND and COMPETITOR layer.

These are built from names, not mined from signals, because they are how a
brand measures whether it surfaces at all. Standard shapes:

  "{brand_name} vs [competitor]"
  "alternatives to [competitor]"
  "is {brand_name} worth it"
  "does {brand_name} [do the thing a topic is about]"
  "[category] like {brand_name} but [cheaper / simpler / for smaller teams]"
  "cheaper alternative to [competitor]"
  "compare [competitor], [competitor] and {brand_name}"

Keep them short. These are typed tersely - "alternatives to X" is a complete
real prompt. Do not dress them up.

Use ONLY the names given. Never invent a competitor, a price or a feature."""
    user = f"""Brand: {brand_name} - {brand['what_they_sell']}
Competitors: {', '.join(comps)}
Segments: {json.dumps([v["segment"] for v in voices], indent=2)}

Capabilities buyers would ask whether {brand_name} has, taken from the topics:
{json.dumps([t["topic"] for t in topics], indent=2)}

Write the brand and competitor prompts. Cover each competitor. Mostly bottom
funnel. Set "mentions_brand": true wherever {brand_name} appears.
{PROMPT_SCHEMA}"""
    log("  brand/competitor pass")
    return _tag(parse_json(call_llm(_writer_system(extra), user, "smart",
                                    max_tokens=14000), []), "brand")


def write_industry_prompts(topics, sig, brand, voices):
    """5e. Buyers name their own industry when they ask. The original segment
    list from the file is used here, not the merged one, so no industry is
    lost to merging."""
    raw_segments = sig["segments"]
    if not raw_segments:
        return []
    extra = """You are writing the INDUSTRY-QUALIFIED layer.

Buyers say their own industry out loud when they ask. Same underlying
question, but the industry is in the prompt and that is what we need.

The shapes to write:
  "best [category] for [industry]"
  "how do [industry] companies handle [the core job of the category]"
  "does [the approach] change by industry"
  "how does a [industry] company [do the thing] without [that industry's risk]"

Write one to three prompts per industry, choosing the topics that industry
would actually care about most. Where an industry carries a real constraint -
a regulator, an approval process, sensitive data, physical inventory, seasonal
demand - let that constraint show in the prompt. Where it carries none, keep
the prompt plain."""
    user = f"""Category: {brand['what_they_sell']}

Industries this brand sells to, verbatim from the client:
{json.dumps(raw_segments, indent=2)}

Topics available:
{json.dumps([t["topic"] for t in topics], indent=2)}

Voice profiles, for tone only:
{json.dumps([{"segment": v["segment"], "words_they_use": v.get("words_they_use"),
              "recurring_worry": v.get("recurring_worry")} for v in voices], indent=2)}

Write the industry-qualified prompts. Set "segment" to the industry named.
{PROMPT_SCHEMA}"""
    log("  industry pass")
    return _tag(parse_json(call_llm(_writer_system(extra), user, "smart",
                                    max_tokens=14000), []), "industry")


def write_expansion_prompts(topics, brand, voices):
    """5f. The one-step-beyond pass. Its own call, because as an option inside
    another prompt it never fires."""
    if not SCOPE["allow_expansion"]:
        return []
    user = f"""Category: {brand['what_they_sell']}
Buyers say: {', '.join(brand.get('buyer_words', []))}

Topics:
{json.dumps([t["topic"] for t in topics], indent=2)}

Segments: {json.dumps([v["segment"] for v in voices], indent=2)}

Write the prompts that sit one step from these topics. Set "origin" to
"expanded" and name the topic you stepped from in "evidence".
{PROMPT_SCHEMA}"""
    log("  expansion pass")
    out = _tag(parse_json(call_llm(_writer_system(EXPANSION_BRIEF), user,
                                   "smart", max_tokens=14000), []), "expansion")
    for o in out:
        o["origin"] = "expanded"
    return out


def write_prompts(topics, voices, brand, brand_name, sig):
    for t in topics:
        t["ceiling"] = max(1, len(t.get("evidence", [])))
    passes = [
        write_topic_prompts(topics, voices, brand, brand_name),
        write_diagnostic_prompts(topics, voices, brand),
        write_definitional_prompts(topics, brand, voices),
        write_brand_prompts(topics, brand, brand_name, voices),
        write_industry_prompts(topics, sig, brand, voices),
        write_expansion_prompts(topics, brand, voices),
    ]
    out = []
    for chunk in passes:
        out += chunk
    counts = _count(p.get("pass") for p in out)
    for k, v in counts.items():
        log(f"    {k}: {v}")
    return out


# =============================================================================
#  Stage 6  -  filters
# =============================================================================

STOP = {"the","a","an","is","are","for","to","of","in","and","or","what","which",
        "how","do","does","i","my","it","that","this","can","should","with","on"}


def dedupe(prompts):
    # Exact match on meaningful words only - no similarity threshold to guess.
    # Anything subtler than an identical word set is left to the model, which
    # can actually read the questions.
    kept, seen = [], set()
    for p in prompts:
        key = frozenset(re.findall(r"[a-z]+", p["prompt"].lower())) - STOP
        if key in seen:
            continue
        seen.add(key)
        kept.append(p)
    log(f"identical: {len(prompts) - len(kept)}")
    # Semantic (LLM) dedup is intentionally OFF: it over-clustered distinct phrasing
    # and intent variants ("best CRM for startups" vs "affordable CRM for small
    # teams"), which are exactly the coverage this tool exists to produce. Pass 1
    # above still removes prompts whose meaningful-word set is identical.
    return kept


def filter_first_level(prompts):
    system = ("You enforce one rule on buyer prompts.\n\n" + BRIEFS["realism"] + "\n\nOutput JSON only.")
    user = f"""Drop any prompt that assumes an earlier conversation, piles on the
asker's personal situation, stacks more than two qualifiers, or uses vendor
marketing vocabulary.

Naming who is asking ("as a B2B SaaS marketer...") is ALLOWED.

{json.dumps([{"i": i, "prompt": p["prompt"]} for i, p in enumerate(prompts)], indent=2)}

Return JSON: {{"drop": [{{"i": index, "why": "short reason"}}]}}"""
    drop = parse_json(call_llm(system, user, "cheap", max_tokens=4000),
                      {"drop": []}).get("drop", [])
    bad = {d["i"] for d in drop}
    log(f"not first-level: {len(bad)}")
    return [p for i, p in enumerate(prompts) if i not in bad]


def skeptic(prompts):
    system = ("You are shown questions supposedly typed by real people into "
              "ChatGPT. You are sceptical by nature. Output JSON only.")
    expanded = [i for i, p in enumerate(prompts) if p.get("origin") == "expanded"]
    user = f"""For each question:
1. Would a real person type this? Be harsh. Machine-written questions are too
   polished, stack too many conditions, or borrow vocabulary from a vendor
   website rather than a human.
2. Does it contain specifics (numbers, prices, tier names, integrations) that
   must have been invented?

{json.dumps([{"i": i, "prompt": p["prompt"]} for i, p in enumerate(prompts)], indent=2)}

Extra scrutiny on these, written more freely: {expanded}

Return JSON: {{"drop": [{{"i": index, "why": "short reason"}}]}}"""
    drop = parse_json(call_llm(system, user, "smart", max_tokens=5000),
                      {"drop": []}).get("drop", [])
    bad = {d["i"] for d in drop}
    log(f"failed the skeptic: {len(bad)}")
    for d in drop[:5]:
        if isinstance(d.get("i"), int) and d["i"] < len(prompts):
            log(f'    "{prompts[d["i"]]["prompt"][:58]}" -> {d["why"]}')
    return [p for i, p in enumerate(prompts) if i not in bad]


# =============================================================================
#  Stage 7  -  blind test
# =============================================================================

def blind_test(prompts, sig):
    real = [r["text"] for r in sig["by_provenance"].get(VOICE_SOURCE, [])
            if len(r["text"]) > 25]
    if len(real) < 5 or not prompts:
        log("not enough real samples - skipping")
        return None
    # Match the two sides so the detector cannot win by counting, and cap the
    # total so one giant classification call can't exhaust the output budget.
    n = min(len(real), len(prompts), BLIND_TEST_SAMPLE)
    real = random.sample(real, n)
    mine = random.sample(prompts, n)

    mixed = ([{"text": r, "_real": True} for r in real] +
             [{"text": p["prompt"], "_real": False} for p in mine])
    random.shuffle(mixed)

    system = "You detect machine-written text. Output JSON only."
    user = f"""Some of these came from real people online. Others were generated
by an AI. Identify the AI-written ones.

{json.dumps([{"i": i, "text": m["text"]} for i, m in enumerate(mixed)], indent=2)}

Return JSON: {{"ai_written": [{{"i": index, "tell": "what gave it away"}}]}}"""

    parsed = parse_json(call_llm(system, user, "smart"), {})
    guessed = parsed.get("ai_written")
    if guessed is None:
        # Empty/unparseable detector response - skip rather than report a bogus
        # 0% (which would falsely read as "indistinguishable").
        log("detector returned nothing usable - skipping blind test")
        return None
    flagged = {g["i"] for g in guessed if isinstance(g.get("i"), int)}
    total = sum(1 for m in mixed if not m["_real"])
    caught = sum(1 for i, m in enumerate(mixed) if not m["_real"] and i in flagged)
    rate = caught / total if total else 0

    log(f"caught {caught}/{total} generated prompts ({rate:.0%}), "
        f"chance is {INDISTINGUISHABLE:.0%}")
    if rate <= INDISTINGUISHABLE:
        log("at or below chance - indistinguishable from the real samples")
    tells = [g["tell"] for g in guessed
             if isinstance(g.get("i"), int) and g["i"] < len(mixed)
             and not mixed[g["i"]]["_real"]]
    for t in tells[:4]:
        log(f"    tell: {t}")
    return {"detection_rate": rate, "chance": INDISTINGUISHABLE,
            "indistinguishable": rate <= INDISTINGUISHABLE, "tells": tells}


def rewrite(prompts, tells, brand):
    system = ("You rewrite AI-sounding questions to sound human.\n\n" + BRIEFS["realism"] + "\n\nOutput JSON only.")
    user = f"""A detector caught these tells:
{json.dumps(tells, indent=2)}

Buyers say: {', '.join(brand.get('buyer_words', []))}
Buyers never say: {', '.join(brand.get('vendor_words', []))}

Rewrite any prompt below showing those tells. Keep the topic identical - change
only the wording. Return unchanged prompts as-is. If one cannot be saved
without inventing detail, mark "drop": true.

{json.dumps([{"i": i, "prompt": p["prompt"]} for i, p in enumerate(prompts)], indent=2)}

Return JSON: [{{"i": index, "prompt": "rewritten", "drop": false}}]"""
    edits = parse_json(call_llm(system, user, "smart", max_tokens=8000), [])
    dropped = 0
    for e in edits:
        i = e.get("i")
        if isinstance(i, int) and 0 <= i < len(prompts):
            if e.get("drop"):
                prompts[i]["_drop"] = True
                dropped += 1
            elif e.get("prompt"):
                prompts[i]["prompt"] = e["prompt"]
    log(f"rewritten, {dropped} dropped")
    return [p for p in prompts if not p.get("_drop")]


# =============================================================================
#  Output
# =============================================================================

def save(prompts, sig, brand, voices, test, ev=None):
    out = Path(OUTPUT_DIR)
    out.mkdir(exist_ok=True)
    slug = re.sub(r"\W+", "_", (sig["brand"]["brand_name"] or "brand").lower()).strip("_")

    jp = out / f"{slug}_prompts.json"
    jp.write_text(json.dumps({
        "brand": sig["brand"],
        "brand_profile": brand,
        "voice_profiles": voices,
        "blind_test": test,
        "eval": ev,
        "counts": {
            "total": len(prompts),
            "grounded": sum(1 for p in prompts if p.get("origin") == "grounded"),
            "expanded": sum(1 for p in prompts if p.get("origin") == "expanded"),
            "mentions_brand": sum(1 for p in prompts if p.get("mentions_brand")),
            "by_funnel": dict(_count(p.get("funnel") for p in prompts)),
            "by_pass": dict(_count(p.get("pass") for p in prompts)),
            "by_segment": dict(_count(p.get("segment") for p in prompts)),
        },
        "prompts": prompts,
    }, indent=2))

    cp = out / f"{slug}_prompts.csv"
    cols = ["prompt", "funnel", "segment", "topic", "mentions_brand",
            "pass", "origin", "evidence"]
    order = {"top": 0, "middle": 1, "bottom": 2}
    rows = sorted(prompts, key=lambda p: (order.get(p.get("funnel"), 9),
                                          p.get("segment") or "",
                                          p.get("topic") or ""))
    with open(cp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for p in rows:
            w.writerow({k: p.get(k, "") for k in cols})
    return jp, cp


def _count(it):
    c = defaultdict(int)
    for x in it:
        c[x] += 1
    return c


# =============================================================================
#  Eval  -  measure coverage against a golden set
# =============================================================================

def evaluate(generated, golden_path):
    """Recall against a hand-written golden set. Recall is the number that
    matters: a missed prompt is a blind spot in visibility tracking, while an
    extra prompt only costs a little tracking budget."""
    golden = [l.strip() for l in Path(golden_path).read_text().splitlines()
              if l.strip()]
    if not golden:
        log("golden file is empty")
        return None

    gen = [p["prompt"] for p in generated]
    matched, missed = [], []

    system = ("You judge whether two prompts would return substantially the "
              "same answer from ChatGPT. Output JSON only.")
    size = 40
    for i in range(0, len(golden), size):
        chunk = golden[i:i + size]
        user = f"""For each GOLDEN prompt, decide whether any GENERATED prompt covers it.

"Covers" means an AI would give substantially the same answer to both. Different
wording is fine. A generated prompt that is merely on the same topic does NOT
count - the question being asked has to be the same.

GOLDEN:
{json.dumps([{"g": j, "prompt": q} for j, q in enumerate(chunk)], indent=2)}

GENERATED:
{json.dumps([{"n": k, "prompt": q} for k, q in enumerate(gen)], indent=2)}

Return JSON: {{"results": [{{"g": index, "covered_by": n or null}}]}}"""
        res = parse_json(call_llm(system, user, "smart", max_tokens=8000),
                         {"results": []}).get("results", [])
        for r in res:
            j = r.get("g")
            if not isinstance(j, int) or j >= len(chunk):
                continue
            (matched if r.get("covered_by") is not None else missed).append(chunk[j])

    recall = len(matched) / len(golden) if golden else 0
    print(f"\n  golden prompts:  {len(golden)}")
    print(f"  covered:         {len(matched)}  ({recall:.0%} recall)")
    print(f"  missed:          {len(missed)}")
    if missed:
        print("\n  a sample of what was missed:")
        for q in missed[:15]:
            print(f"    - {q}")
    return {"recall": recall, "golden": len(golden), "covered": len(matched),
            "missed": missed}


# =============================================================================

def main():
    global USE_CACHE
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--input", default=INPUT_FILE)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--refresh-research", action="store_true",
                    help="bypass the cache for the two web-search stages only")
    ap.add_argument("--eval", metavar="GOLDEN.txt",
                    help="measure recall against a golden set, one prompt per line")
    ap.add_argument("--eval-only", metavar="PROMPTS.json",
                    help="score an existing output file, generate nothing")
    args = ap.parse_args()
    USE_CACHE = not args.no_cache
    global CACHE_SEARCH
    CACHE_SEARCH = not args.refresh_research

    if args.inspect:
        inspect(args.input)
        return
    if args.eval_only:
        if not args.eval:
            sys.exit("--eval-only needs --eval GOLDEN.txt")
        stage("eval", "Scoring against golden set")
        evaluate(json.loads(Path(args.eval_only).read_text())["prompts"], args.eval)
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY")

    stage(0, "Reading signals")
    sig = load_signals(args.input)
    name = sig["brand"]["brand_name"]
    print(f"\n{'=' * 60}\n  {name}\n{'=' * 60}")
    log(f"{len(sig['records'])} signals kept, {sig['filtered_out']} filtered by lifecycle")
    for p, items in sorted(sig["by_provenance"].items(), key=lambda x: -len(x[1])):
        log(f"  {p}: {len(items)}")
    if not sig["records"]:
        sys.exit("Nothing parsed. Run --inspect.")

    stage(1, "Reading the brand")
    before = STATS["searches"]
    brand = read_brand(sig)
    searches_since(before)
    if brand.get("searches_run"):
        for q in brand["searches_run"][:8]:
            log(f"    searched: {q}")
    log(brand["what_they_sell"])
    log(f"buyers say: {', '.join(brand.get('buyer_words', [])[:6])}")

    stage(2, "Building voice profiles")
    before = STATS["searches"]
    voices = build_voices(sig, brand)
    searches_since(before)
    log(f"{len(sig['segments'])} segments -> {len(voices)} after merging")
    for v in voices:
        log(f"  {v['segment']}: worries about {v['recurring_worry']}")

    stage(3, "Finding topics")
    topics = build_topics(sig)
    log(f"{len(topics)} topics kept")

    stage(4, "Pairing buyers to topics")
    topics = pair(topics, voices)

    stage(5, "Writing prompts")
    prompts = write_prompts(topics, voices, brand, name, sig)
    log(f"{len(prompts)} written")

    stage(6, "Filtering")
    prompts = dedupe(prompts)
    prompts = filter_first_level(prompts)
    prompts = skeptic(prompts)
    log(f"{len(prompts)} survived")

    test = None
    if SCOPE["run_blind_test"]:
        stage(7, "Blind realism test")
        test = blind_test(prompts, sig)
        if test and test["detection_rate"] > INDISTINGUISHABLE:
            log("above chance - something is leaking, rewriting once")
            prompts = rewrite(prompts, test["tells"], brand)

    ev = None
    if args.eval:
        stage(8, "Scoring against golden set")
        ev = evaluate(prompts, args.eval)

    stage(9, "Saving")
    jp, cp = save(prompts, sig, brand, voices, test, ev)
    log(str(jp)); log(str(cp))

    f = _count(p.get("funnel") for p in prompts)
    print(f"\n{len(prompts)} prompts")
    print(f"  funnel   top {f.get('top', 0)} | middle {f.get('middle', 0)} "
          f"| bottom {f.get('bottom', 0)}")
    print(f"  origin   grounded {sum(1 for p in prompts if p.get('origin') == 'grounded')} "
          f"| expanded {sum(1 for p in prompts if p.get('origin') == 'expanded')}")
    print(f"  brand    named in {sum(1 for p in prompts if p.get('mentions_brand'))}")
    print("  passes   " + " | ".join(f"{k} {v}" for k, v in
                                     _count(p.get("pass") for p in prompts).items()))
    print(f"{STATS['calls']} API calls ({STATS['cached']} cached), "
          f"{STATS['in_tok']:,} in / {STATS['out_tok']:,} out\n")


if __name__ == "__main__":
    main()