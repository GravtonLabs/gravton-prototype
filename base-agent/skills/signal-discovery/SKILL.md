---
name: signal-discovery
description: A methodology for proposing NEW signals, metrics, or data points the client should start capturing to unlock more variety of insight. Load when the user asks things like "what new signals should we track?", "what else could we measure / store?", "what data points are we missing?", "how do we get more insights out of this data?", or wants ideas for new derived metrics, leading indicators, or columns/tables to add. Guides the agent to audit what is already stored, find measurement whitespace, prototype each candidate signal with a read-only query over existing rows, and return a prioritized, concrete proposal (definition, source fields, where to store it, value vs. effort).
---

# Signal Discovery — proposing new data points to capture

This skill is a working method, not a reference doc. Use it when the user wants ideas for **new
signals to store** so the platform can surface a wider variety of insight. The goal of every
response is a short, prioritized list of concrete, buildable signals — each one grounded in the
data that actually exists in *this* database.

A "signal" here means a derived, insight-bearing data point — something computed from raw rows
that answers a question on its own (the same spirit as the existing `brand_signal_metric` and
`reddit_insight_signal` / `quora_insight_signal` tables). New signals usually come from one of
three moves: (1) compute something the raw data already supports but nobody persists, (2) measure
an existing thing along a new dimension (time, model, persona, funnel, competitor), or (3) join
two sources that are currently analysed in isolation.

## Important: you are read-only

You cannot create columns or tables. So your output is a **recommendation plus a working proof**:
for each proposed signal, also write the read-only SQL that computes it *today* from existing
rows. That shows the insight is real and gives the engineering team a ready-made definition to
persist. Frame it as "here's the signal, here's what it reveals right now, here's what to store
to make it first-class."

## Method (follow in order)

1. **Ground in the schema.** Use the live schema already in your system prompt. If you need the
   precise meaning of a field or table, load the `backend-models` skill (data model) and the
   `insights-metrics` skill (authoritative formulas). Do not invent fields — map every proposal to
   columns that exist here.
2. **Inventory what's already measured.** List the signals the system already produces so you do
   not re-propose them: visibility, share of voice, position, sentiment, consistency, citation
   attribution/share, untapped topics, opportunities, brand signals, social insight signals,
   technical-SEO scores, GSC performance. Anything you suggest must be *new* relative to these.
3. **Probe data density before proposing.** A signal is only useful if its source data is present
   and populated. Run small read-only checks: row counts per candidate source table, how many
   distinct `run_version`s exist (needed for any trend/velocity signal), null-rates on key
   columns, distinct models, whether `fanout_query` / social / citation tables have rows. Drop or
   down-rank candidates whose inputs are empty or too sparse.
4. **Find the whitespace.** Walk the signal families below against what exists, and pick the gaps
   that this database can actually support.
5. **Prototype each candidate.** Write one read-only query that computes the signal from current
   rows and run it. Keep the proposals that produce a meaningful, non-trivial result.
6. **Prioritize and present.** Return a ranked shortlist (see output format). Lead with the
   highest value-to-effort signals. Don't dump the whole catalog — propose the 5–8 best for *this*
   data, each justified by what the prototype query showed.

## Signal families and candidate signals

Treat these as a prompt for ideas, not a checklist to output wholesale. For each, the pattern is
**what it unlocks / from which existing fields / what to store**.

### A. Temporal & momentum (needs ≥2 `insight_run.run_version` per cluster+model)
- **Visibility velocity** — week-over-week and multi-week slope of `visibility_score`. Unlocks "who is rising/falling fastest," not just current standing. From: `topic_metric`/`prompt_metric` joined across `insight_run.run_version`. Store: `visibility_delta`, `visibility_slope` per brand/cluster/run.
- **Sentiment momentum** — direction and rate of `sentiment_score` change. Unlocks early warning before a level looks bad. From: `topic_metric.sentiment_score` across versions.
- **Volatility / stability** — std-dev of a metric across recent runs. Unlocks "is this number trustworthy or noisy." From: any metric across `run_version`.
- **Weeks-since-peak / trough** — how long since the brand's best/worst on a cluster. Unlocks decay and recovery tracking.

### B. Competitive dynamics
- **Share shift** — change in `sov` per brand between runs; who is taking share from whom. Unlocks a zero-sum view of the category.
- **Head-to-head win rate** — fraction of prompts where focal outranks a specific competitor (`position_rank` / `visibility_score`). Unlocks per-rival scorecards.
- **Displacement events** — a prompt where a competitor overtook the focal brand between runs. Unlocks a feed of concrete losses to act on. From: `prompt_metric` across versions.
- **Competitive gap** — focal metric minus best competitor's on each cluster. Unlocks "how far behind/ahead, and where."
- **New-entrant detection** — a `brand_id` appearing in `generation_brand_metric` that wasn't present in prior runs. Unlocks early competitor discovery.

### C. Consistency & model agreement
- **Cross-model divergence** — variance of a brand's metric across `model_id` for the same prompt. Unlocks "ChatGPT loves us, Gemini ignores us." From: `prompt_metric`/`generation_brand_metric` grouped by model.
- **Answer drift** — consistency of presence/sentiment for the same prompt across runs over time (distinct from within-run consistency). Unlocks longitudinal reliability.

### D. Citation & authority depth
- **Owned-citation share trend** — `source_bucket='owned'` share of `citation_mass_weight` over time. Unlocks the core adoption-health signal as a trend, not a snapshot.
- **Citation diversity / concentration** — count of distinct `normalized_domain`s, or an HHI over domain shares, per cluster. Unlocks "are we cited broadly or via one page."
- **Earned-to-owned ratio** — balance of `earned_media` vs `owned` citations. Unlocks dependence-on-third-parties risk.
- **Citation coverage** — fraction of prompts where the focal brand earns ≥1 owned citation. Unlocks whitespace where AI cites others' sources for our topics.
- **Competitor-owned leakage** — citations attributed `competitor_owned` on the focal brand's own prompts. Unlocks "AI sends our buyers to a rival's page."

### E. Sentiment richness
- **Aspect-level sentiment** — sentiment split by theme (pricing, support, features) mined from `generation_brand_metric.sentiment_positive_signals` / `_negative_signals` and `brand_signal_metric.signal`. Unlocks "negative on price, positive on reporting."
- **Negative-signal emergence** — first run a given negative `brand_signal_metric.signal` appears, and its `mention_count` trajectory. Unlocks catching a narrative as it forms.
- **Sentiment↔visibility coupling** — correlation between sentiment change and visibility change per cluster. Unlocks whether tone is actually moving presence.

### F. Funnel & persona coverage
- **Funnel-stage coverage** — visibility weighted by `synthetic_prompt.funnel`; flag strong Top-funnel but weak Bottom-funnel. Unlocks "visible in awareness, invisible at decision."
- **Persona-weighted visibility** — visibility grouped by `synthetic_prompt.persona`. Unlocks "strong with Users, weak with Decision Makers."
- **Post-purchase health index** — a composite over Post-Purchase prompts (consistency + owned-citation share + sentiment). Unlocks a single retention-risk number.

### G. Demand & opportunity economics
- **Demand-weighted visibility gap** — gap on a cluster × its `keyword_library.ai_demand` / `untapped_topic.estimated_volume`. Unlocks prioritising gaps by money, not size.
- **Opportunity aging** — how long an `opportunity` / `untapped_topic` has stayed open (`status`, timestamps). Unlocks a staleness/SLA view.
- **Capture rate** — share of high-demand prompts where the focal brand is present. Unlocks a single "are we winning where it matters" number.

### H. Cross-source corroboration (the highest-variety move)
- **AI ↔ social alignment** — compare LLM sentiment (`topic_metric`/`generation_brand_metric`) with `reddit_mention` / `quora` sentiment for the same brand/topic. Unlocks "the community already turned before the models did."
- **Social as leading indicator** — does a shift in `reddit_insight_signal` (e.g. `sentiment_trend`) precede a later LLM sentiment move? Unlocks predictive early-warning.
- **GSC ↔ AI divergence** — keywords ranking well in `gsc_query` (low `position`) but with low AI visibility on the matching cluster. Unlocks "we win Google here but lose the AI answer."
- **Tech-SEO ↔ citation linkage** — pages/templates with bot-access or readability problems (`technical_seo_scan`, findings) that sit on high-demand, low-owned-citation clusters. Unlocks a fixable, revenue-linked checklist.
- **Fanout intent** — recurring sub-queries in `fanout_query.subqueries` the models issue while answering. Unlocks "what the AI actually researches about us" — often net-new topic demand.

### I. Anomaly & event signals
- **Threshold-breach events** — a metric crossing a configurable floor/ceiling between runs (e.g. owned-citation share drops below X for 2 runs). Unlocks an alert feed and pairs with the existing checkpoint system.
- **Z-score spikes** — a run where a metric deviates sharply from its own recent mean. Unlocks "something happened this week."

## How to prioritize

Rank candidates by **value × feasibility**:
- *Value* — does it answer a question none of the current signals answer? Does it span a new
  dimension (time/model/persona/funnel/competitor) or a new source join? Cross-source signals
  (family H) usually create the most "variety of insight."
- *Feasibility* — is the source data present and populated *now* (from your density probe)?
  Trend/velocity signals need multiple `run_version`s; social/fanout signals need those tables to
  have rows. A brilliant signal with no input data ranks low until the data exists.

## Output format

Give a short intro sentence, then a ranked list. For each proposed signal:

- **Name** — short, memorable.
- **What it unlocks** — the new question it answers, in one line of business language.
- **Computed from** — the existing tables/columns (real names from this DB).
- **What to store** — the concrete new column(s) or table to persist, and at what grain
  (per brand / cluster / run / prompt) and cadence.
- **Proof** — the read-only query you ran and a one-line summary of what it showed on this data.
- **Value / effort** — High/Med/Low each, with a one-clause reason.

End with a single recommended "start here" pick and offer to draft the exact column/table
definition or the persistence query for whichever signals the user wants to build first.

## Guardrails

- Propose only signals whose inputs exist in this database; verify with a probe query first.
- Never re-propose a signal the platform already computes (see the inventory step).
- Map every field name to the live schema — if unsure what a column means, load `backend-models`
  or `insights-metrics` rather than guessing.
- You cannot write to the database; deliver definitions + read-only proofs, not migrations.
- Keep it to the best 5–8 for this dataset; depth on a few beats a long undifferentiated list.
