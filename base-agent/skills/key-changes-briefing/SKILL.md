---
name: key-changes-briefing
description: Flow 1 of the Opportunity Engine — the auto-generated, CMO-level briefing of the few most important changes in the brand's AI position, with no input from the user. Load when the user opens a dashboard/home view or asks broad, unpointed questions like "what changed recently?", "did anything decline or grow?", "how are my metrics trending?", "which metrics are under risk?", "are any new competitors emerging in my citations?", or "is there anything important I should know?". Produces a short ranked briefing (a handful of one-line callouts, each with its metric and who moved), keeping smaller changes quiet but reachable.
---

# Flow 1 — Key changes (callouts)

The CMO briefing. The user gives nothing; you surface, on their behalf, the handful of moves that
matter most. The output is short by design: a few one-line callouts, each stating the change, the
metric, and who moved — then a "view more" affordance for the quieter changes. Never flood the
page; depth lives in Flow 2 (the deep dive).

## Input
Nothing from the user. You run over the latest prompt-run results and key metrics, ranked by how
much each change matters. Stay high level.

## Output
A short briefing of the few most important moves. Each is one insightful line with the metric
attached, ideally naming the competitor involved, e.g.:
> *"Wiz slipped out of answers for 'what is a CNAPP' over the last two runs, and Palo Alto now appears in its place."*
End with a one-line "more changes available — ask to see the rest" pointer. Do not explain causes
here; that's the deep dive. Keep it to roughly 3–6 callouts.

## Method
1. **Establish the comparison window.** Find the two most recent `insight_run.run_version`s per
   cluster+model (higher version = newer). If there's only one run, say there's no prior run to
   compare yet and report current standing instead.
2. **Detect changes at the prompt level, then roll up to clusters** so the page doesn't flood.
   Look across runs for: visibility/SoV/position/sentiment moving on a cluster (`topic_metric`,
   `prompt_metric`); the focal brand falling out of answers it used to win (presence/`is_present`
   in `generation_brand_metric` going to zero); a competitor newly appearing or gaining share; a
   new negative `brand_signal_metric` theme; owned-citation share dropping (`prompt_citation`
   `attribution_type`/`source_bucket`). If `checkpoint_state` rows exist, treat fired triggers
   (absence / decline / competitor_emergence) as ready-made candidates.
3. **New competitors in citations** — brands/domains appearing in `prompt_citation` (or
   `citation_competitor_candidate` / `owned_domain_suggestion`) this run that were absent before.
4. **Rank by importance, then cut to the top few.** Importance combines the *magnitude* of the
   change with *volume* and *funnel weight* (see below). Show only the top handful; everything else
   is "view more."
5. **Write each callout as one line** — the change + the metric + who moved. Lead with the single
   most important.

## How importance is ranked (sensible default; the product team may configure this)
Anchor on **volume × business weight × magnitude**, rolled up from prompt to cluster:
- **Volume** — search/AI demand for the affected cluster: `keyword_library.ai_demand` (or `sv`/
  `asv`), `untapped_topic.estimated_volume`, `demand_universe_prompt_label.demand_score`,
  `synthetic_prompt.w_p`, or `gsc_query.impressions`. Bigger demand ⇒ more important.
- **Funnel weight** — from `synthetic_prompt.funnel`. **Bottom-funnel carries the most weight**,
  then Mid, then Top (Post-Purchase matters for adoption health). A drop on a decision-stage prompt
  outranks the same drop on an awareness prompt.
- **Magnitude** — size of the metric delta between runs, and whether it crossed a meaningful line
  (e.g. fell out of answers entirely, lost the top citation).
Do not over-engineer the exact formula; be transparent that ranking favours high-volume,
bottom-funnel, large moves, and note it's configurable.

## Guardrails
- Read-only. You report; you don't change anything.
- Keep it short — a handful of callouts. Resist listing every move; that's what "view more" and the
  deep dive are for.
- Each callout must carry a concrete metric and, where possible, the competitor who moved.
- Don't diagnose causes here. If the user asks "why," that's Flow 2 (`change-deep-dive`).
- Confirm field/join names against the live schema; load `backend-models` if unsure and
  `insights-metrics` for what a metric move means.

## Example
> **Your top moves this week**
> - Presence on **Cloud Security** (your largest category) fell for the 3rd run running; **Palo Alto** gained the citation you lost.
> - **Share of voice** on "CNAPP pricing" dropped 14 pts — a bottom-funnel prompt, so this one matters.
> - New competitor **Orca** appeared in citations across 3 prompts where you used to stand alone.
>
> *5 smaller changes are quiet — ask "show me the rest" to see them, or "why did Cloud Security drop?" to dig in.*
