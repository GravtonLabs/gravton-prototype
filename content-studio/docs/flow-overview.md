# Content Studio — Full Flow Overview

**Session recorded:** June 2026 · `session_id: a84b69bd6488425aac728ff39d7c17c8`

---

## What It Does

Content Studio takes a content idea from a raw request to a publish-ready article. A team of specialised AI agents — each responsible for one stage — ensures the output is structured, brand-consistent, and quality-checked before it ever reaches an editor.

---

## The Six Stages

```
User types first message
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ 1. INTENT                                               │
│    Aqiira collects the brief — one question at a time.  │
│    Per user turn: 1 stream reply + 1 silent extract    │
│    (run in parallel)                                    │
│    Phase ends when all blocks are confirmed.            │
└────────────────────────┬────────────────────────────────┘
                         │ All blocks confirmed
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 2. WORKPLAN                                             │
│    Translates brief into production plan.               │
│    Shows word count, steps, ruleset applied.            │
│    User reviews and approves.                           │
└────────────────────────┬────────────────────────────────┘
                         │ Workplan approved
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 3. OUTLINE                                              │
│    Builds article section-by-section in Opus.           │
│    ┌──────────────────────────────────────────────┐     │
│    │ BACKGROUND (fires simultaneously):           │     │
│    │  • Reference Grader: grades source URLs      │     │
│    │  • Authority Sources: researches the topic   │     │
│    └──────────────────────────────────────────────┘     │
│    User can revise before accepting.                    │
└────────────────────────┬────────────────────────────────┘
                         │ Outline accepted
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 4. DRAFT                                                │
│    Opus writes full article, then 7 checks fire:        │
│    • Deterministic rule engine (no LLM)                 │
│    • 6 LLM checks in parallel: voice, active voice,    │
│      quotable phrasing, uniqueness, evidence, legal     │
│    • AI-signal review                                   │
└────────────────────────┬────────────────────────────────┘
                         │ Draft ready
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 5. EDITOR                                               │
│    Human types instructions; AI rewrites the draft.     │
│    Rule checks re-run and rubric score updates          │
│    after every edit.                                    │
└────────────────────────┬────────────────────────────────┘
                         │ User says "done"
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 6. DONE — Export: Markdown / HTML / plain text          │
└─────────────────────────────────────────────────────────┘
```

---

## Agents at a Glance

| Agent | Stage | Role | Model |
|-------|-------|------|-------|
| Aqiira (Intent) | Brief | Conversational brief collector | Sonnet |
| Workplan | Plan | Translates brief to production plan | Sonnet |
| Reference Grader | Background | Grades and classifies source URLs | Sonnet |
| Authority Sources | Background | Researches topic from the live web | Sonnet |
| Outline | Structure | Builds section skeleton, enforces ruleset | Opus |
| Draft Builder | Content | Writes full draft + runs 7 validation checks | Opus + Sonnet |
| Editor | Revision | Applies human edits, re-runs rule checks live | Sonnet |

---

## What the Recorded Session Actually Produced

**Session file:** `data/session.json` · **Phase at close:** `editor` · **Full pipeline ran**

The session went through all stages — intent, workplan, outline, background research, draft (3 attempts), and into the editor.

### Competitor Keywords Listicle

| Block | Value |
|-------|-------|
| Topic | How to find competitor keywords and close visibility gaps |
| Goal | Educate, increase organic traffic |
| Audience | SEO practitioners, digital marketers, content strategists |
| Content type | listicle |
| Length | concise |
| Primary keyword | competitor keywords |
| Secondary keywords | find competitor keywords, visibility gaps, keyword gap analysis, SEO competitor analysis, close visibility gaps |
| Guardrails | None |
| Competitive ref | semrush.com/blog/competitor-keywords/ |
| Sources submitted | None |
| Brand voice | Analytical, Technical |

**Draft state:** 964 words · rubric 13/43 (30.2%) · 0 AI-signal flags · currently in editor for rubric fixes.

---

## Full-Session Cost (this pipeline run)

| Stage | Est. cost |
|-------|-----------|
| Intent (~11 turns) | ~$0.15 |
| Workplan | ~$0.026 |
| Reference Grader (1 URL, 0 citable) | ~$0.006 |
| Authority Sources | ~$0.006 |
| Outline | ~$0.059 |
| Draft Builder (3 attempts × Opus) | ~$0.36 |
| Editor — ongoing | ~$0.07+ |
| **Running total** | **~$0.68** |
