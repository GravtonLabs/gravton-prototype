#!/usr/bin/env python3
"""
gravton_agent.py — a read-only CONVERSATIONAL analytics agent for ONE Gravton client org.

Conversational: it remembers the conversation across turns, so follow-ups work
("...and why?", "compare that to last month", "what about Salesforce?"). Type 'reset' to
clear context, 'exit' to quit.

Agentic: to answer one question it generates SQL on the fly and CHAINS multiple read-only
queries (e.g. spot a drop in topic_metric -> drill into generation_brand_metric phrases ->
confirm with brand_signal_metric -> check citation mix), showing its reasoning and every query.

Database
  Connects to YOUR Postgres. The live schema is introspected on connect, so the agent adapts to
  your real table/column names -- map by meaning, no fixed schema assumed.
      python gravton_agent.py --pg "postgresql://user:pass@host:5432/db" --domain-id 12
  The DSN may also come from the DATABASE_URL or GRAVTON_PG_DSN environment variable.

Knowledge-only mode (no database)
  Answer purely from the reference skills -- metric definitions, the data model, how the platform
  works, methodology -- with no SQL and no live numbers. Needs only ANTHROPIC_API_KEY.
      python gravton_agent.py --docs-only
      python gravton_agent.py --docs-only --ask "how is share of voice different from presence?"

Reference skills (the four Gravton documents, kept full and separate)
  Each source document lives at  skills/<name>/SKILL.md  with a short header. The agent sees only
  a one-line index of them and loads a full document on demand (load_skill) when a question needs
  it -- progressive disclosure, nothing consolidated. The 'insights-metrics' skill is the
  authoritative source for metric formulas/thresholds/buckets.
      python gravton_agent.py --list-skills          # see what's available (no API key)
      python gravton_agent.py --skills-dir PATH ...   # point at a different skills folder

Other flags:  --ask "question"   --org-id N   --domain-id N   --model NAME   --max-steps N
              --docs-only (answer from skills, no database)
              --show-schema (connect, print live schema, exit)   --selftest (offline guard checks)

Requirements:  pip install anthropic "psycopg[binary]"   (Claude models)
               pip install openai "psycopg[binary]"      (GPT models)
               export ANTHROPIC_API_KEY=sk-...           (Claude)
               export OPENAI_API_KEY=sk-...              (GPT)
"""

import argparse, glob, json, os, re, sys, textwrap, urllib.parse, urllib.request, urllib.error

DEFAULT_MODEL = "claude-sonnet-4-6"
SKILLS_DIR = "skills"

# Input $/MTok, Output $/MTok — for cost display only, not billing
PRICING = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8":   (5.00, 25.00),
    "claude-haiku-4-5":  (1.00,  5.00),
    "gpt-4o":            (2.50, 10.00),
    "gpt-4o-mini":       (0.15,  0.60),
    "o1":                (15.00, 60.00),
    "o1-mini":           (1.10,  4.40),
    "o3":                (10.00, 40.00),
    "o3-mini":           (1.10,  4.40),
}


def _provider(model):
    return "openai" if model.startswith(("gpt-", "o1", "o3", "o4")) else "anthropic"


def _to_openai_tool(t):
    return {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t["input_schema"],
        },
    }

# ---------------------------------------------------------------------------------------
# Read-only guard + DB wrapper
# ---------------------------------------------------------------------------------------
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|attach|"
                        r"detach|replace|merge|vacuum|reindex|pragma|copy|call|do|begin|commit|rollback)\b", re.I)


def assert_read_only(sql):
    s = sql.strip().rstrip(";").strip()
    if not s: raise ValueError("Empty query.")
    if ";" in s: raise ValueError("Multiple statements are not allowed; send a single SELECT.")
    # Strip leading SQL line comments (-- ...) before checking the query type
    uncommented = re.sub(r"(^|\n)\s*--[^\n]*", "", s).strip()
    if not re.match(r"^(select|with)\b", uncommented, re.I): raise ValueError("Only SELECT / WITH queries are permitted.")
    if _FORBIDDEN.search(s): raise ValueError("Query contains a forbidden (write/DDL) keyword.")
    return s


class DB:
    def __init__(self, kind, conn): self.kind, self.conn = kind, conn

    @classmethod
    def postgres(cls, dsn):
        try: import psycopg
        except ImportError: sys.exit('Postgres mode needs:  pip install "psycopg[binary]"')
        conn = psycopg.connect(dsn, autocommit=True); conn.read_only = True
        return cls("postgres", conn)

    def query(self, sql, limit=200):
        cur = self.conn.cursor(); cur.execute(assert_read_only(sql))
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(limit); cur.close()
        return cols, [dict(zip(cols, r)) for r in rows]

    def introspect(self):
        cur = self.conn.cursor()
        # Columns with table and column comments
        cur.execute("""
            SELECT c.table_name, c.column_name, c.data_type,
                   obj_description(pgc.oid, 'pg_class') AS table_comment,
                   col_description(pgc.oid, c.ordinal_position) AS col_comment
            FROM information_schema.columns c
            JOIN pg_class pgc ON pgc.relname = c.table_name
            JOIN pg_namespace pgn ON pgn.oid = pgc.relnamespace
            WHERE c.table_schema = 'public' AND pgn.nspname = 'public'
            ORDER BY c.table_name, c.ordinal_position
        """)
        by = {}
        for tab, col, typ, tcomment, ccomment in cur.fetchall():
            if tab not in by:
                by[tab] = {"cols": [], "comment": tcomment}
            note = f"  -- {ccomment}" if ccomment else ""
            by[tab]["cols"].append(f"{col} {typ}{note}")
        # Foreign keys
        cur.execute("""
            SELECT kcu.table_name, kcu.column_name,
                   ccu.table_name AS ref_table, ccu.column_name AS ref_col
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
        """)
        fks = {}
        for tab, col, ref_tab, ref_col in cur.fetchall():
            fks.setdefault(tab, []).append(f"  -- FK: {col} -> {ref_tab}.{ref_col}")
        cur.close()
        lines = []
        for t in sorted(by):
            header = t + (f"  -- {by[t]['comment']}" if by[t]["comment"] else "")
            body = ",\n  ".join(by[t]["cols"])
            if t in fks:
                body += "\n" + "\n".join(fks[t])
            lines.append(f"{header}(\n  {body}\n)")
        return "\n\n".join(lines)

    def introspect_stats(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT relname, reltuples::bigint
            FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE nspname = 'public' AND relkind = 'r'
            ORDER BY reltuples DESC
        """)
        rows = cur.fetchall(); cur.close()
        return "\n".join(f"  {name}: ~{count:,} rows" for name, count in rows if count > 0)


# ---------------------------------------------------------------------------------------
# SKILLS: each source document Gravton provided is kept FULL and SEPARATE as
# skills/<name>/SKILL.md (never consolidated). The agent sees only the index (name +
# description) and pulls the complete document on demand via the load_skill tool --
# progressive disclosure, exactly like Claude's own skills.
# ---------------------------------------------------------------------------------------
def _parse_frontmatter(text, fallback_name):
    name, desc, body, visibility = fallback_name, "", text, "external"
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if m:
        head, body = m.group(1), m.group(2)
        for line in head.splitlines():
            if ":" not in line: continue
            key, val = line.split(":", 1); key, val = key.strip().lower(), val.strip()
            if key == "name" and val: name = val
            elif key == "description" and val: desc = val
            elif key == "visibility" and val: visibility = val
    return name, desc, body.strip(), visibility


def discover_skills(skills_dir):
    """Return {name: {description, body, path}} for every skills/*/SKILL.md found.
    Looks relative to CWD first, then next to this script. Missing dir -> {}."""
    here = os.path.dirname(os.path.abspath(__file__))
    base = next((d for d in (skills_dir, os.path.join(here, skills_dir)) if os.path.isdir(d)), None)
    skills = {}
    if not base: return skills
    for path in sorted(glob.glob(os.path.join(base, "*", "SKILL.md"))):
        try: text = open(path, encoding="utf-8").read()
        except Exception: continue
        name, desc, body, visibility = _parse_frontmatter(text, os.path.basename(os.path.dirname(path)))
        skills[name] = {"description": desc, "body": body, "path": path, "visibility": visibility}
    return skills


# ---------------------------------------------------------------------------------------
INTERPRETATION_GUIDE = """\
QUICK ORIENTATION (the loadable 'insights-metrics' skill is the AUTHORITATIVE source for every
formula, threshold and bucket boundary -- load it before you interpret or explain any metric):

- Brand set B = {focal brand} U {active competitors}; the focal brand is competitor.is_focal = 1.
  In THIS database's metric tables, brand_id holds the brand's DISPLAY NAME (= competitor.name);
  join competitor only to learn is_focal.
- visibility_score: higher is better. sov: share within B (sums ~1). position_rank: LOWER is better.
- sentiment_score in [-1,1]; to explain WHY it moved, read generation_brand_metric
  sentiment_negative_signals / _positive_signals (phrases) and brand_signal_metric (themes + counts).
- Citations are attributed by DOMAIN OWNERSHIP, not text; source_bucket = owned / community / earned_media.
- Trends: compare insight_run.run_version for the same cluster+model (higher version = newer).

For anything beyond this orientation -- exact sentiment/consistency buckets, the consistency
formula, citation damping/weighting/attribution, SoV math, what a table or field means, the data
model, or business framing -- LOAD THE RELEVANT SKILL instead of guessing.
"""

PERSONA = """\
VOICE AND STYLE
You are a sharp colleague who respects the user's time. Say the useful thing, say it simply, then stop.

Five non-negotiable rules:
1. Lead with the answer or recommendation. Reason follows, briefly.
2. Use numbers over adjectives. "3 of 20 prompts" beats "most prompts."
3. One idea per sentence. Active voice.
4. If you don't know or the data isn't there, say so in plain words and offer the next step.
5. Short by default. Expand only when a decision genuinely needs the extra context.

Never do:
- Filler openers ("Great question", "I'd be happy to", "Certainly")
- Hype words, AI clichés, or flattery
- Emoji or exclamation marks
- Hedging stacks ("it's possible that perhaps the data might suggest") — state the finding or admit the gap
- Over-explaining; show your work only if asked
- Ask more than one clarifying question, and only when you truly cannot proceed

"""

SYSTEM_TEMPLATE = """\
You are Gravton's read-only analyst for the client "{org}" (brand "{brand}", domain "{domain}").
You answer marketing-team questions by querying a {dialect} database. This is a CONVERSATION:
resolve follow-ups and pronouns against earlier turns.

{persona}RULES
- Read only. Use run_investigation to query the database. Scope every query to THIS client.
- Think in investigation rounds (max 8). Each round: declare your plan and submit ALL queries
  for that round at once inside a single run_investigation call. Analyze the full batch of results
  before deciding if another round is needed. Never call run_investigation once per query.
- Round structure:
    Round 1 — baseline: aggregates, totals, trends across recent versions.
    Round 2 — drill: follow specific anomalies (per-model, per-prompt, phrase-level signals).
    Round 3 — confirm: row-level evidence to confirm or refute the round-2 hypothesis.
    Rounds 4–8 — deepen: pursue additional unanswered questions, competitor comparisons,
    citation patterns, or any thread from prior rounds that warrants further investigation.
  Skip rounds you don't need. Start a new round only when the results raise a specific
  unanswered question that requires more data.
- After receiving results, cite concrete evidence and translate into plain business language.
  If the data cannot answer, say so plainly.
{scope}
{skills_block}The schema below is the LIVE database. In a real Gravton (Django) deployment tables are named
<app>_<model> (e.g. client_organization, brandkit_competitor, intent_core_syntheticprompt,
insight_metrics_promptmetric, citations_promptcitation). The concept names in the interpretation
guide may map to differently-named tables/columns here — map by MEANING to the schema shown
below, and run a small exploratory query (e.g. SELECT * ... LIMIT 5) if you're unsure which
table or column holds something.

DATABASE SCHEMA ({dialect}):
{schema}

TABLE SIZES (approximate, from pg_class; use to avoid expensive scans and to prefer smaller lookup tables):
{stats}

{guide}
"""

DOCS_ONLY_SYSTEM_TEMPLATE = """\
You are Gravton's knowledge assistant. You answer ONLY from the reference skills below (Gravton's
own documentation): what metrics mean and how they're computed, how the platform and data pipeline
work, the data model, business context, and methodology. This is a CONVERSATION; resolve follow-ups
against earlier turns.

{persona}KNOWLEDGE-ONLY MODE: you are NOT connected to any database. You cannot look up the client's
actual numbers, run queries, or report current standings or recent changes. If asked for live data,
say plainly that no database is connected and offer the concept or method instead — note they can
re-run with --pg to query real data.

{skills_block}Load the relevant skill with load_skill before explaining a metric, the data model, or how
something works. Rely on the skill rather than assumptions. 'insights-metrics' is the authoritative
source for every metric formula, threshold, and bucket.

{guide}
"""

INVESTIGATION_TOOL = {
    "name": "run_investigation",
    "description": (
        "Execute one investigation round. State your plan, declare every piece of data you need, "
        "and submit ALL queries for this round at once — they run in batch and results are returned "
        "together. One LLM turn per round, not per query. Max 8 rounds total.\n"
        "Round 1: baseline — aggregates, totals, recent trends.\n"
        "Round 2: drill — follow anomalies found in round 1 (signals, per-model breakdown, phrases).\n"
        "Round 3: confirm — row-level evidence to confirm or refute the round-2 hypothesis.\n"
        "Rounds 4–8: deepen — pursue competitor comparisons, citation patterns, or any thread "
        "from prior rounds that warrants further investigation.\n"
        "Only start a new round if the previous results raise a specific unanswered question."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "investigation_plan": {
                "type": "string",
                "description": "What this round is trying to establish and why (1-3 sentences)."
            },
            "information_requirements": {
                "type": "array",
                "description": "Every query needed for this round. All run together; include all you need now.",
                "items": {
                    "type": "object",
                    "properties": {
                        "purpose": {"type": "string", "description": "One line: what this query checks."},
                        "sql":     {"type": "string", "description": "A single SELECT/WITH statement."}
                    },
                    "required": ["purpose", "sql"]
                }
            }
        },
        "required": ["investigation_plan", "information_requirements"]
    }
}

LOAD_SKILL_TOOL = {"name": "load_skill",
                   "description": "Load the FULL text of one reference skill (a Gravton source document) by name, "
                                  "chosen from the skills index in the system prompt. Call it before interpreting a "
                                  "metric, mapping a concept to tables/columns, or explaining how the platform works.",
                   "input_schema": {"type": "object",
                                    "properties": {"name": {"type": "string",
                                                            "description": "Exact skill name from the index."}},
                                    "required": ["name"]}}

WEB_SEARCH_TOOL = {"name": "web_search",
                   "description": "Search the web to find existing pages, content, or competitor presence for a given topic. "
                                  "Use 'site:brand-domain keywords' to check if the brand already has a page on that topic "
                                  "(determines Create vs Optimize). Use plain keywords to see what currently wins a prompt. "
                                  "Requires BRAVE_API_KEY environment variable.",
                   "input_schema": {"type": "object",
                                    "properties": {
                                        "query": {"type": "string", "description": "Search query. Use 'site:domain.com keywords' to check a specific domain, or plain keywords to see what's winning."},
                                        "purpose": {"type": "string", "description": "One line: what you're checking for."}},
                                    "required": ["query"]}}

CHECK_URL_TOOL = {"name": "check_url",
                  "description": "Check whether a specific URL exists and is accessible. Returns HTTP status and page title. "
                                 "Use to verify if a specific brand page exists before recommending Create vs Optimize.",
                  "input_schema": {"type": "object",
                                   "properties": {
                                       "url": {"type": "string", "description": "Full URL to check (must start with https://)."},
                                       "purpose": {"type": "string", "description": "One line: what page you're checking for."}},
                                   "required": ["url"]}}


def _run_web_search(query: str, count: int = 5) -> str:
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "BRAVE_API_KEY not set. Set it in .env to enable web search. Proceeding without web validation."})
    url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}&count={count}&safesearch=off"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": api_key})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        results = [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": (x.get("description") or "")[:250]}
                   for x in data.get("web", {}).get("results", [])]
        return json.dumps({"results": results, "count": len(results)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _run_check_url(url: str) -> str:
    if not url.startswith("http"):
        return json.dumps({"url": url, "exists": False, "error": "URL must start with https://"})
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 Gravton-Agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            title = ""
            ct = r.headers.get("Content-Type", "")
            return json.dumps({"url": url, "exists": True, "status": r.status, "content_type": ct})
    except urllib.error.HTTPError as e:
        return json.dumps({"url": url, "exists": e.code < 400, "status": e.code})
    except Exception as e:
        # Fallback: try GET for servers that reject HEAD
        try:
            req2 = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Gravton-Agent/1.0"})
            with urllib.request.urlopen(req2, timeout=10) as r:
                html = r.read(4096).decode("utf-8", errors="replace")
                m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
                title = m.group(1).strip() if m else ""
                return json.dumps({"url": url, "exists": True, "status": r.status, "title": title})
        except Exception as e2:
            return json.dumps({"url": url, "exists": False, "error": str(e2)})


class Agent:
    def __init__(self, db, model=DEFAULT_MODEL, max_steps=8, org_id=None, domain_id=None, skills_dir=SKILLS_DIR):
        self.provider = _provider(model)
        if self.provider == "openai":
            try: import openai
            except ImportError: sys.exit("GPT models need:  pip install openai")
            if not os.environ.get("OPENAI_API_KEY"): sys.exit("Set OPENAI_API_KEY.")
            self.client = openai.OpenAI()
        else:
            try: import anthropic
            except ImportError: sys.exit("Asking questions needs:  pip install anthropic")
            if not os.environ.get("ANTHROPIC_API_KEY"): sys.exit("Set ANTHROPIC_API_KEY.")
            self.client = anthropic.Anthropic()

        self.db = db; self.model = model; self.max_steps = max_steps
        self.org_id = org_id; self.domain_id = domain_id
        self.messages = []  # persisted across turns -> conversational
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.skills = discover_skills(skills_dir)
        self.docs_only = db is None
        self.tools = ([] if self.docs_only else [INVESTIGATION_TOOL]) + ([LOAD_SKILL_TOOL] if self.skills else []) + [WEB_SEARCH_TOOL, CHECK_URL_TOOL]
        if self.provider == "openai":
            self.openai_tools = [_to_openai_tool(t) for t in self.tools]
        skills_block = ""
        if self.skills:
            idx = "\n".join(f"  - {n}: {s['description']}" for n, s in self.skills.items())
            skills_block = ("REFERENCE SKILLS (full Gravton source documents; load the complete text on demand\n"
                            "with load_skill, then rely on it instead of assumptions):\n" + idx + "\n"
                            "Load the relevant skill BEFORE interpreting a metric, mapping a concept to "
                            "tables/columns, or explaining how the platform works. 'insights-metrics' is the "
                            "authoritative source for every metric formula, threshold and bucket.\n\n")
        if self.docs_only:
            self.org, self.brand, self.domain = "", "", ""
            sys_text = DOCS_ONLY_SYSTEM_TEMPLATE.format(skills_block=skills_block, guide=INTERPRETATION_GUIDE, persona=PERSONA)
        else:
            self.org, self.brand, self.domain = self._org_context()
            scope = ""
            if org_id is not None or domain_id is not None:
                parts = []
                if org_id is not None: parts.append(f"organization id = {org_id}")
                if domain_id is not None: parts.append(f"domain id = {domain_id}")
                scope = ("\nTENANCY SCOPE: this database may hold multiple clients. EVERY query MUST be "
                         "filtered to " + " and ".join(parts) + " (follow foreign keys back to that "
                         "org/domain). Never return another client's data.\n")
            sys_text = SYSTEM_TEMPLATE.format(org=self.org, brand=self.brand, domain=self.domain,
                                              dialect=db.kind, schema=db.introspect(),
                                              stats=db.introspect_stats(),
                                              guide=INTERPRETATION_GUIDE, scope=scope, skills_block=skills_block,
                                              persona=PERSONA)
        if self.provider == "openai":
            self.system_text = sys_text  # plain string; prepended as system message each call
        else:
            self.system_prompt = [{"type": "text", "text": sys_text, "cache_control": {"type": "ephemeral"}}]

    def _org_context(self):
        """Find the org row without assuming a table name (seed uses 'organization';
        real Django uses 'client_organization'). Best-effort; never fatal."""
        for tbl in ("organization", "client_organization", "clients_organization", "client_client"):
            try: rows = self.db.query(f"SELECT * FROM {tbl} LIMIT 25")[1]
            except Exception: continue
            if not rows: continue
            row = rows[0]
            if self.org_id is not None:
                row = next((r for r in rows if str(r.get("id")) == str(self.org_id)), row)
            name = row.get("name") or row.get("brand_name") or "(client)"
            return name, (row.get("brand_name") or row.get("brand") or name), (row.get("domain") or "")
        return "(this client)", "", ""

    def reset(self): self.messages = []

    def _summarize_result(self, cols, rows, purpose):
        if len(rows) <= 50:
            return {"purpose": purpose, "columns": cols, "rows": rows, "row_count": len(rows)}
        numeric_cols = [c for c in cols if any(isinstance(r.get(c), (int, float)) for r in rows[:10])]
        stats = {}
        for c in numeric_cols:
            vals = [r[c] for r in rows if r.get(c) is not None and isinstance(r.get(c), (int, float))]
            if vals:
                stats[c] = {"min": min(vals), "max": max(vals),
                            "avg": round(sum(vals) / len(vals), 2), "count": len(vals)}
        return {
            "purpose": purpose,
            "row_count": len(rows),
            "note": f"Large result: showing 50 of {len(rows)} rows. Numeric stats computed over all rows.",
            "sample_rows": rows[:50],
            "numeric_stats": stats,
        }

    def _maybe_compress_history(self):
        if len(self.messages) < 12:
            return
        to_summarize = self.messages[:-4]
        compress_prompt = ("Summarize the following conversation turns concisely: "
                           "key findings, numbers, and conclusions only. Under 200 words.")
        try:
            if self.provider == "openai":
                resp = self.client.chat.completions.create(
                    model=self.model, max_completion_tokens=512,
                    messages=[{"role": "system", "content": compress_prompt}] + to_summarize
                )
                summary = resp.choices[0].message.content or ""
            else:
                resp = self.client.messages.create(
                    model=self.model, max_tokens=512,
                    system=compress_prompt,
                    messages=to_summarize
                )
                summary = resp.content[0].text
        except Exception:
            return  # skip compression on error; non-fatal
        self.messages = (
            [{"role": "user", "content": f"[Earlier conversation summary]\n{summary}"},
             {"role": "assistant", "content": "Understood."}]
            + self.messages[-4:]
        )
        print("  (conversation history compressed)")

    def ask(self, question):
        if self.provider == "openai":
            return self._ask_openai(question)
        return self._ask_anthropic(question)

    def _ask_anthropic(self, question):
        self._maybe_compress_history()
        self.messages.append({"role": "user", "content": question})
        chat_input = 0; chat_output = 0; chat_cache_read = 0; chat_cache_write = 0
        answer = "(Stopped: hit the max investigation-round limit.)"

        for round_num in range(self.max_steps):
            # Extended thinking on round 1 only, for models that support it
            use_thinking = (round_num == 0 and not self.docs_only
                            and self.model in ("claude-sonnet-4-6", "claude-opus-4-8"))
            kwargs = dict(model=self.model,
                          max_tokens=6000 if use_thinking else 4096,
                          system=self.system_prompt,
                          tools=self.tools,
                          messages=self.messages)
            if use_thinking:
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": 2000}
                print("\n  \U0001f9e0 thinking...", flush=True)

            # Stream text tokens as they arrive; collect full message for tool handling
            has_text = False
            with self.client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    if not has_text:
                        print("\n  \U0001f4ad ", end="", flush=True)
                        has_text = True
                    print(text, end="", flush=True)
                if has_text:
                    print()
                resp = stream.get_final_message()

            chat_input += resp.usage.input_tokens
            chat_output += resp.usage.output_tokens
            chat_cache_read += getattr(resp.usage, "cache_read_input_tokens", 0) or 0
            chat_cache_write += getattr(resp.usage, "cache_creation_input_tokens", 0) or 0
            self.messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use":
                answer = "".join(b.text for b in resp.content if b.type == "text").strip()
                break

            results = []
            for tu in [b for b in resp.content if b.type == "tool_use"]:
                payload = self._dispatch_tool(tu.name, tu.input, round_num)
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": payload})
            self.messages.append({"role": "user", "content": results})

        self.session_input_tokens += chat_input
        self.session_output_tokens += chat_output
        in_p, out_p = PRICING.get(self.model, (3.00, 15.00))
        # input_tokens = non-cached; cache_write at 1.25x; cache_read at 0.1x
        chat_cost = (chat_input * in_p + chat_cache_write * in_p * 1.25
                     + chat_cache_read * in_p * 0.1 + chat_output * out_p) / 1_000_000
        sess_cost = (self.session_input_tokens * in_p + self.session_output_tokens * out_p) / 1_000_000
        cache_note = (f"  | cache: {chat_cache_read:,} read / {chat_cache_write:,} write"
                      if chat_cache_read or chat_cache_write else "")
        print(f"\n  \U0001f4b0 turn: {chat_input:,} in + {chat_output:,} out = ${chat_cost:.4f}"
              f"  |  session: ${sess_cost:.4f}{cache_note}")
        return answer

    def _ask_openai(self, question):
        self._maybe_compress_history()
        self.messages.append({"role": "user", "content": question})
        chat_input = 0; chat_output = 0
        answer = "(Stopped: hit the max investigation-round limit.)"

        for round_num in range(self.max_steps):
            all_messages = [{"role": "system", "content": self.system_text}] + self.messages
            tools_param = self.openai_tools if self.openai_tools else None

            # Stream text; accumulate tool call deltas
            has_text = False
            full_text = ""
            tool_calls_acc = {}  # index -> {id, name, arguments}
            finish_reason = "stop"

            stream = self.client.chat.completions.create(
                model=self.model,
                messages=all_messages,
                tools=tools_param,
                stream=True,
                stream_options={"include_usage": True},
                max_completion_tokens=4096,
            )
            for chunk in stream:
                if chunk.usage:
                    chat_input += chunk.usage.prompt_tokens or 0
                    chat_output += chunk.usage.completion_tokens or 0
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                if delta.content:
                    if not has_text:
                        print("\n  \U0001f4ad ", end="", flush=True)
                        has_text = True
                    print(delta.content, end="", flush=True)
                    full_text += delta.content
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        i = tc.index
                        if i not in tool_calls_acc:
                            tool_calls_acc[i] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_acc[i]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[i]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[i]["arguments"] += tc.function.arguments
            if has_text:
                print()

            tool_calls_list = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
            assistant_msg = {"role": "assistant", "content": full_text or None}
            if tool_calls_list:
                assistant_msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for tc in tool_calls_list
                ]
            self.messages.append(assistant_msg)

            if finish_reason != "tool_calls":
                answer = (full_text or "").strip()
                break

            for tc in tool_calls_list:
                try: args = json.loads(tc["arguments"])
                except Exception: args = {}
                payload = self._dispatch_tool(tc["name"], args, round_num)
                self.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": payload})

        self.session_input_tokens += chat_input
        self.session_output_tokens += chat_output
        in_p, out_p = PRICING.get(self.model, (2.50, 10.00))
        chat_cost = (chat_input * in_p + chat_output * out_p) / 1_000_000
        sess_cost = (self.session_input_tokens * in_p + self.session_output_tokens * out_p) / 1_000_000
        print(f"\n  \U0001f4b0 turn: {chat_input:,} in + {chat_output:,} out = ${chat_cost:.4f}"
              f"  |  session: ${sess_cost:.4f}")
        return answer

    def _dispatch_tool(self, name, args, round_num):
        """Execute a tool call and return its string payload. Shared by both providers."""
        if name == "load_skill":
            nm = (args.get("name") or "").strip()
            sk = self.skills.get(nm)
            if sk:
                print(f"\n  \U0001f4d6 reading skill: {nm}")
                return sk["body"][:200000]
            print(f"\n  \U0001f4d6 skill not found: {nm}")
            return f"ERROR: no skill named '{nm}'. Available: {', '.join(self.skills) or '(none)'}"
        if name == "web_search":
            q = args.get("query", ""); purpose = args.get("purpose", "")
            print(f"\n  \U0001f310 web search: {purpose or q}")
            return _run_web_search(q)
        if name == "check_url":
            url = args.get("url", ""); purpose = args.get("purpose", "")
            print(f"\n  \U0001f517 check url: {url}")
            return _run_check_url(url)
        if name == "run_investigation":
            if self.db is None:
                return "ERROR: knowledge-only mode; no database connected."
            plan = args.get("investigation_plan", "")
            reqs = args.get("information_requirements", [])
            print(f"\n  \U0001f4cb Round {round_num + 1} plan: {plan}")
            batch = []
            for req in reqs:
                sql = req.get("sql", ""); purpose = req.get("purpose", "")
                print(f"\n  \U0001f50d {purpose}" if purpose else "\n  \U0001f50d query")
                print("     " + "\n     ".join(textwrap.wrap(sql, 110)))
                try:
                    cols, rows = self.db.query(sql); print(f"     -> {len(rows)} row(s)")
                    batch.append(self._summarize_result(cols, rows, purpose))
                except Exception as e:
                    print(f"     ! {e}")
                    batch.append({"purpose": purpose, "error": str(e), "sql_attempted": sql,
                                  "retry_hint": "This query failed. Fix the SQL error and retry it in the next run_investigation call."})
            return json.dumps(batch, default=str)[:24000]
        return f"ERROR: unknown tool '{name}'"


# ---------------------------------------------------------------------------------------
def run_selftest():
    """Offline checks only -- no DB and no API key needed. Verifies the read-only SQL guard
    and that the reference skills are discoverable."""
    print("Read-only SQL guard -- should ALLOW:")
    for ok in ["SELECT 1",
               "WITH x AS (SELECT 1 AS n) SELECT n FROM x",
               "select id, name from competitor where is_focal = 1"]:
        try: assert_read_only(ok); print(f"   ok allowed: {ok!r}")
        except ValueError as e: print(f"   x WRONGLY blocked: {ok!r} ({e})")
    print("\nRead-only SQL guard -- should BLOCK:")
    for bad in ["DELETE FROM competitor", "DROP TABLE domain", "UPDATE competitor SET name='x'",
                "INSERT INTO domain VALUES (1)", "SELECT 1; DROP TABLE domain",
                "GRANT ALL ON competitor TO bob", ""]:
        try: assert_read_only(bad); print(f"   x NOT blocked: {bad!r}")
        except ValueError: print(f"   ok blocked: {bad!r}")
    print("\nSkills discovered:", ", ".join(discover_skills(SKILLS_DIR)) or "(none found)")
    print("\nSelftest OK.")


def main():
    ap = argparse.ArgumentParser(description="Read-only conversational Gravton analytics agent over your Postgres DB.")
    ap.add_argument("--pg", metavar="DSN",
                    help="Postgres DSN, e.g. postgresql://user:pass@host:5432/db. "
                         "Falls back to env DATABASE_URL or GRAVTON_PG_DSN.")
    ap.add_argument("--ask", metavar="Q")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="Model name. Claude: claude-sonnet-4-6 (default), claude-opus-4-8, claude-haiku-4-5. "
                         "GPT (needs OPENAI_API_KEY): gpt-4o, gpt-4o-mini, o1, o3-mini.")
    ap.add_argument("--max-steps", type=int, default=8,
                    help="Max investigation rounds (default 8). Each round batches all queries for that phase.")
    ap.add_argument("--org-id", type=int, help="Scope every query to this organization id (multi-tenant DB).")
    ap.add_argument("--domain-id", type=int, help="Scope every query to this domain id.")
    ap.add_argument("--show-schema", action="store_true",
                    help="Connect, print the live DB schema, and exit (no API key needed).")
    ap.add_argument("--skills-dir", default=SKILLS_DIR, metavar="DIR",
                    help="Folder of reference skills as <DIR>/<name>/SKILL.md (default: skills).")
    ap.add_argument("--list-skills", action="store_true",
                    help="List the discovered reference skills and exit (no DB or API key needed).")
    ap.add_argument("--docs-only", action="store_true",
                    help="Knowledge-only mode: answer from the reference skills with NO database "
                         "(no SQL, no live numbers). Still needs ANTHROPIC_API_KEY.")
    ap.add_argument("--selftest", action="store_true",
                    help="Run offline checks (read-only SQL guard + skill discovery); no DB or API key needed.")
    a = ap.parse_args()

    if a.selftest: run_selftest(); return
    if a.list_skills:
        sk = discover_skills(a.skills_dir)
        if not sk:
            print(f"No skills found. Expected files at '{a.skills_dir}/<name>/SKILL.md'."); return
        print(f"Reference skills discovered under '{a.skills_dir}/':\n")
        for n, s in sk.items():
            body_lines = s["body"].count("\n") + 1
            print(f"  {n}  ({len(s['body']):,} chars, ~{body_lines} lines)\n    {s['description']}\n")
        return

    if a.docs_only:
        agent = Agent(None, model=a.model, max_steps=a.max_steps, skills_dir=a.skills_dir)
        print("Knowledge-only mode — no database connected. Answering from the reference skills.")
    else:
        dsn = a.pg or os.environ.get("DATABASE_URL") or os.environ.get("GRAVTON_PG_DSN")
        if not dsn:
            sys.exit('No database given. Pass --pg "postgresql://user:pass@host:5432/db" '
                     "(or set DATABASE_URL / GRAVTON_PG_DSN), or use --docs-only to answer from the "
                     "reference skills without a database.")
        db = DB.postgres(dsn); print("Connected to Postgres (read-only).")
        if a.show_schema:
            print("\n-- Live schema --\n"); print(db.introspect()); return
        agent = Agent(db, model=a.model, max_steps=a.max_steps, org_id=a.org_id, domain_id=a.domain_id,
                      skills_dir=a.skills_dir)

    skills_note = f" | skills: {', '.join(agent.skills)}" if agent.skills else " | skills: none found"
    print(f"Client: {agent.org or '(knowledge-only)'} | brand: {agent.brand} | model: {agent.model}{skills_note}\n")
    if a.ask:
        print(f"? {a.ask}\n"); agent.ask(a.ask); print(); return

    print("Conversational — follow-ups welcome. 'reset' clears context, 'exit' quits. Try:")
    if agent.docs_only:
        print("  - What is share of voice, and how is it different from presence?")
        print("  - How are citations attributed to a brand?")
        print("  - Walk me through the data model for prompts and clusters.")
        print("  - What new signals could we track to get more insight?\n")
    else:
        print("  - How do we compare to competitors on our top topics?")
        print("  - Why did our sentiment drop recently?   (then:)  is it on every model?")
        print("  - Which URLs is AI citing for us — owned vs community vs earned?")
        print("  - What are the biggest untapped opportunities right now?\n")
    while True:
        try: q = input("? ").strip()
        except (EOFError, KeyboardInterrupt): print(); break
        if q.lower() in {"exit", "quit", ""}: break
        if q.lower() == "reset": agent.reset(); print("(context cleared)\n"); continue
        agent.ask(q); print()


if __name__ == "__main__":
    main()