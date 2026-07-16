---
name: change-deep-dive
description: Flow 2 of the Opportunity Engine — an on-demand deep analysis of ONE thing (a prompt, metric, category/cluster, or competitor), drawing on everything connected to it. Load when the user asks a pointed "why / what happened / history" question such as "why has this prompt declined?", "why has citation share in category X dropped?", "why is my presence falling?", "what's happening with my share of voice and how has it trended over the last two months?", or "are there new competitors in this category?". Produces a focused, multi-angle explanation: what changed, since when, the trend, the likely cause, related signals that moved with it, and why it matters — up to two or three pages when the user wants the full picture.
---

# Flow 2 — Deep dive into a change

On demand. The user points at one thing — a prompt, a metric, a category/cluster, or a competitor —
and asks what happened and why. You behave like a deep-analysis agent: chain multiple read-only
queries from several angles and assemble one clear narrative. It can run long (two to three pages)
when the user wants the full picture; match the depth to the ask.

## Input
A pointed question about a single item, started by selecting it or typing it. Resolve what the item
is first (which prompt / cluster / metric / competitor) before analysing.

## Output
A focused answer drawn from everything connected to that item:
- **What changed** — the metric and the size of the move.
- **Since when** — the run/date it started (`insight_run.run_version` / timestamps).
- **The trend** — the trajectory across runs, not just the latest delta.
- **The likely cause** — evidence-backed, not guessed.
- **Related signals that moved with it** — citations lost, a competitor's new page cited, a new
  negative theme, a position slip on neighbouring prompts.
- **Why it matters** — sized by volume and funnel weight so a drop on a large category reads as more
  urgent than one on a small niche.

## Method (chain these angles; show your reasoning and queries)
1. **Resolve and quantify.** Pin the item, then measure the change across `run_version`s
   (`topic_metric` for cluster-level, `prompt_metric` for prompt-level). State magnitude and onset.
2. **Trend, not snapshot.** Pull the metric across all available runs/weeks for the trajectory; if
   the user asks for "the last two months," map that to the relevant run versions.
3. **Hunt the cause from multiple angles** — keep going until the evidence converges:
   - *Citations* — did owned citations drop or a competitor's page start winning? Inspect
     `prompt_citation` (`attribution_type`/`source_bucket`, `normalized_domain`, `page_url`,
     `citation_mass_weight`) across the two runs.
   - *Sentiment* — read `generation_brand_metric.sentiment_negative_signals` / `_positive_signals`
     (actual phrases) and `brand_signal_metric` (recurring themes + `mention_count`, with direction).
   - *Presence/position* — did the brand fall out of answers, or just slip in order? Check
     `is_present` and `rank` in `generation_brand_metric`, `position_rank` in `prompt_metric`.
   - *Competitor* — who gained the share/citation/position the focal brand lost? Compare brands
     within the same runs.
   - *Model split* — is it one model or all of them? Group by `model_id`.
   - *Neighbours* — did related prompts in the same cluster move together?
4. **New competitors** — brands/domains newly present in `generation_brand_metric` or
   `prompt_citation` versus prior runs (and `citation_competitor_candidate` if present).
5. **Size the impact.** Rank "why it matters" by the cluster's volume (`keyword_library.ai_demand`,
   `untapped_topic.estimated_volume`, `demand_score`, `gsc_query.impressions`) and funnel weight
   (`synthetic_prompt.funnel`, bottom-funnel highest) — the same importance lens as the
   `key-changes-briefing` skill.
6. **Assemble the narrative** in the output order above. Cite the specific prompts, URLs, phrases,
   and numbers you found.

## Guardrails
- Read-only and evidence-based. Every claim ("a competitor page now wins the citation") must trace
  to rows you actually queried — show the query. Don't speculate beyond the data; if the cause is
  unclear, say what the data supports and what it doesn't.
- For metric meaning, thresholds, and buckets, defer to `insights-metrics`; for joins/field meaning,
  `backend-models` / `org-knowledge-base`.
- Match length to the request — a one-line "why" gets a tight answer; "give me the full history"
  earns the multi-page treatment.
- This is analysis, not action. If the user shifts to "so how do I fix it," hand off to Flow 3
  (`fix-prompts`).

## Example
The user opens the **Cloud Security** drop. The deep dive shows presence fell over the last three
runs; the likely cause is a competitor comparison page that now wins the citation on four related
prompts; position slipped on those same prompts; sentiment is steady, so this is a citation story,
not a tone story; and it matters because Cloud Security is the largest category the brand competes
in by AI demand — each claim backed by the rows queried.
