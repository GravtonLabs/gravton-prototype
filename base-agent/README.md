# Gravton analytics agent

A read-only, conversational analytics agent for a Gravton GEO ("generative engine optimization")
client. It answers marketing-team questions about a brand's position in AI answers by generating
SQL on the fly, chaining read-only queries, and explaining what it finds in plain language. It
ships with a set of **reference skills** — full Gravton documentation the agent loads on demand —
and runs in three modes.

## Quick start

```bash
pip install anthropic "psycopg[binary]" rich prompt_toolkit
export ANTHROPIC_API_KEY=sk-...

# 1) Live database (read-only) — the normal mode
python gravton_agent.py --pg "postgresql://user:pass@host:5432/db" --domain-id 12

# 2) Knowledge-only — answer from the reference skills, no database, no SQL
python gravton_agent.py --docs-only

# 3) Offline utilities — no database and no API key needed
python gravton_agent.py --list-skills
python gravton_agent.py --selftest
```

The DSN can also come from the `DATABASE_URL` or `GRAVTON_PG_DSN` environment variable, so
`python gravton_agent.py` alone works once that is set.

## Install as a command (optional)

From this folder:

```bash
pip install .            # base
pip install ".[all]"     # + postgres + the rich terminal UI
gravton --docs-only
```

`gravton` looks for the `skills/` folder in the current directory first, then next to the module.
If you run it from elsewhere, point it at the skills with `--skills-dir PATH` or set
`GRAVTON_SKILLS_DIR=/path/to/skills`.

## The terminal experience

With `rich` and `prompt_toolkit` installed you get a banner, dim reasoning lines, syntax-highlighted
SQL panels, a live "thinking" spinner, and Markdown-rendered answers — plus an input line with
history and editing. Without those libraries it degrades automatically to clean plain text (use
`--no-color`, or set `NO_COLOR`, to force plain).

In the chat, besides asking questions, you can use slash commands:

```
/help     show commands              /schema   show the live DB schema
/skills   list the reference skills  /reset    clear conversation memory
/clear    clear the screen           /exit     quit
```

## Reference skills

Each document lives at `skills/<name>/SKILL.md` with a short header (a name and a one-line "load
when" description). The agent only carries that index in context and pulls a full document in on
demand via a `load_skill` tool — progressive disclosure, nothing consolidated. `insights-metrics`
is the authoritative source for every metric formula, threshold, and bucket.

Run `python gravton_agent.py --list-skills` to see them all.

## Safety

- Every database query is forced to a single read-only `SELECT`/`WITH`; DML/DDL and stacked
  statements are rejected, and the Postgres session is opened read-only.
- `--org-id` / `--domain-id` scope every query to one tenant. For production, back this with a
  read-only, row-scoped database role.

## Flags

```
--pg DSN            Postgres connection (or DATABASE_URL / GRAVTON_PG_DSN)
--docs-only         knowledge-only mode: skills only, no database
--ask "Q"           one-shot question, then exit
--org-id N          scope queries to an organization id
--domain-id N       scope queries to a domain id
--model NAME        Claude model (default: claude-sonnet-4-6)
--max-steps N       max chained queries per question (default: 12)
--skills-dir DIR    where to find skills/<name>/SKILL.md (default: skills)
--show-schema       connect, print the live schema, exit
--list-skills       list reference skills, exit (no DB/API key)
--selftest          offline guard + discovery checks (no DB/API key)
--no-color          plain text output
--version
```