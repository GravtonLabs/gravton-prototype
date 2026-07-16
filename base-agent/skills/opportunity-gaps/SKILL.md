---
name: opportunity-gaps
description: Gap detection and action planning for AI visibility — looks at where the brand is underperforming across prompts and recommends what to do about it. Load when the user asks things like "where are my gaps?", "what should I fix?", "where am I losing?", "what opportunities exist?", "where am I missing from AI answers?", "where is a competitor overtaking me?", or any variation of "what do I need to act on?". Produces a ranked, presentable report of gaps with recommended action types and next steps.
---

# Opportunity Gaps — Assess and Act

Your job is to look at the brand's data, form your own assessment of where it is underperforming, and recommend what to do. Do not apply fixed rules or predetermined categories. Read the data, reason about what it means, and surface the gaps that genuinely matter.

---

## What data is available

### Pre-computed pipeline output

The platform runs a continuous pipeline that already detects and clusters opportunities. Check these tables first — they represent the most complete analysis:

**`opportunity_opportunitycluster`** — grouped opportunities, one row per theme  
Key fields: `cluster_name`, `impact` (High/Medium/Low), `impact_score` (numeric), `status` (to_do / in_progress / done), `execution_paths` (JSON tactical playbook), `prompts` (M2M to prompts), `domain_id`

**`opportunity_opportunity`** — individual gap recommendations, linked to a single prompt  
Key fields: `gap_title`, `checkpoint` (which metric triggered it), `intent`, `action_type` (Create/Optimize/Community/Outreach), `target_venue`, `rationale`, `action_items` (JSON list of steps), `prompt_id`

**`opportunity_checkpointstatev2`** — per-prompt, per-model monitoring state  
Key fields: `prompt_id`, `model_id`, `status` (active / triggered), `trigger_fired` (absence / decline / competitor_emergence), `triggered_checkpoint` (which metric caused it), `triggered_at`, `triggered_run_id`

**`opportunity_checkpointslotv2`** — one row per prompt × model × run, recording which checkpoint failed  
Key fields: `prompt_id`, `model_id`, `run_id`, `value` (mention / cited / sov / position / sentiment / consistency / passed), `metric_value`

---

### Live metric tables

Use these to validate and extend the pipeline output, or to derive gaps independently when pre-computed data is absent or stale.

**`insight_metrics_promptmetric`** (or similar — confirm against live schema) — per-prompt metrics per run  
Key fields: `prompt_id`, `run_id`, `brand_id`, `brand_present_count`, `visibility_score`, `sov`, `sov_median`, `position_rank`, `sentiment_score`, `consistency_score`

**`insight_metrics_topicmetric`** (or similar) — cluster-level rollups  
Key fields: `cluster_id`, `run_id`, `brand_id`, `visibility_score`, `sov`, `sentiment_score`, `position_rank`

**`insight_metrics_generationbrandmetric`** (or similar) — per-generation brand signals  
Key fields: `prompt_id`, `run_id`, `brand_id`, `model_id`, `is_present`, `sentiment_positive_signals`, `sentiment_negative_signals`

**`citation_promptcitation`** (or similar) — citations appearing in AI answers  
Key fields: `prompt_id`, `run_id`, `brand_id`, `page_url`, `domain`, `normalized_domain`, `attribution_type` (owned / community / earned_media), `citation_mass_weight`

---

### Prompt and cluster context

**`intent_core_syntheticprompt`** (or similar) — the prompts being tracked  
Key fields: `id`, `text` (the query), `funnel` (Top / Mid / Bottom / Post-Purchase), `cluster_id`, `w_p` (prompt weight), `is_active`

**`intent_core_intentcluster`** (or similar) — topic clusters  
Key fields: `id`, `name`, `domain_id`

**`insight_core_insightrun`** (or similar) — a versioned analysis run  
Key fields: `id`, `run_id`, `run_version`, `cluster_id`, `model_id`, `created_at`

---

### Demand context (for prioritisation)

**`keywords_keywordlibrary`** (or similar) — search volume and demand  
Key fields: `cluster_id`, `ai_demand`, `sv` (search volume), `asv`

---

## What the metrics mean

Use these as context when interpreting numbers — not as rules:

- **`brand_present_count`** — how many times the brand appears across AI responses for this prompt/run. Zero means invisible. A low count relative to how many responses were sampled is worth flagging even if not exactly zero.
- **`visibility_score`** — composite presence score; higher is better.
- **`sov`** (Share of Voice) — the brand's share of total brand mentions on this prompt. `sov_median` is the brand's own historical baseline — compare the two to sense direction.
- **`position_rank`** — lower is better. Context matters: rank 4 of 5 brands is different from rank 4 of 20.
- **`sentiment_score`** — how positively the brand is described. The raw number matters less than whether it's dropping or inconsistent.
- **`consistency_score`** — how consistently the brand is described across model responses. Relevant mainly for post-purchase prompts where coherence of support/returns/setup answers matters.
- **`attribution_type`** — `owned` means the AI cited a brand page; `community` means a forum/Reddit/Quora thread; `earned_media` means a third-party article. For pre-purchase prompts, any citation is useful. For post-purchase prompts, owned citations matter most.

---

## What good looks like

Pre-purchase and post-purchase prompts have different success definitions:

**Pre-purchase** — the brand should be present, cited, ranking well among competitors, and described positively. Gaps here are primarily about winning the prompt.

**Post-purchase** — success is not "winning" but accuracy: the AI should give coherent answers about returns, setup, and support, citing the brand's own pages rather than third-party sources. Consistency across model responses matters more than position rank.

Funnel stage changes urgency: a gap on a Bottom-funnel or Post-Purchase prompt affects purchase decisions directly. A Top-funnel gap affects awareness. All gaps matter but not equally.

---

## What a trigger means (when checkpoint state data exists)

The pipeline records three trigger types when it fires an alert:

- **absence** — the brand has been missing from this prompt across recent runs. Not a one-off, but a sustained pattern.
- **decline** — the brand was performing but metrics have slipped over time. Could be content going stale, a competitor improving, or the brand's own page losing authority.
- **competitor_emergence** — a competitor has gained share on this prompt, whether or not the brand's own numbers changed. An existing competitor grew, or a new one appeared.

The triggered checkpoint (`triggered_checkpoint`) tells you *where in the funnel* the failure is: mention, cited, sov, position, sentiment, or consistency.

---

## What action types mean

**Create** — the brand has no content the AI can use for this prompt. Something needs to be built.  
**Optimize** — the brand has content but it's not strong enough. Optimize has three angles: (1) *Content* — rewrite for depth, accuracy, and AI readability; (2) *Structure* — add headings, comparison blocks, tables; (3) *Freshness* — update stale sections.  
**Community** — a third-party platform (Reddit, Quora, YouTube, LinkedIn) is winning the prompt. The brand needs a presence there.  
**Outreach** — third-party listicles or publications dominate. The brand needs to be cited by those sources.

A single gap can need more than one action. Only add a second action if it genuinely addresses a different part of the problem. Don't pad.

---

## Checking whether a page exists

Before recommending Create or Optimize, use the `web_search` and `check_url` tools to find out whether the brand already has relevant content:

- Search `site:<brand-domain> <gap-topic>` to find existing pages
- Call `check_url` on any candidate URLs to confirm they're live
- If the page exists but is thin or off-topic, that's still an Optimize — not Create

If `BRAVE_API_KEY` is not set, `web_search` will return an error. In that case, use the citation data in the database (`prompt_citation` where `attribution_type = 'owned'`) as a proxy — if the brand has no owned citations on this prompt, it likely has no relevant page.

---

## In-progress work

Do not resurface opportunities the customer is already working on. When pulling from `opportunity_opportunitycluster`, filter out rows where `status = 'in_progress'`. Surface `to_do` items first; mention `done` items only if directly relevant to context.

---

## How to approach this

1. **Start with the pre-computed output.** Query `opportunity_opportunitycluster` and `opportunity_opportunity` for this domain. These are the richest signal — the pipeline has already done deep analysis. Filter to `status != 'in_progress'`.

2. **Read the checkpoint state.** Pull `opportunity_checkpointstatev2` rows with `status = 'triggered'` to see what the system already detected and which checkpoint failed first.

3. **Look at the live metrics.** Use the metric tables to understand current standing — not to apply thresholds, but to read the picture. Is the brand declining, flat, or recovering? Where is it completely absent? Where are competitors pulling ahead? Which prompts have no owned citations at all?

4. **Form your own view.** From what you've read, assess: where is the brand genuinely exposed? Which gaps are symptoms of the same underlying problem? Which are isolated? Which matter most given funnel stage and volume?

5. **Verify web presence for each gap.** Before finalising action type, check whether a relevant page exists on the brand's domain.

6. **Prioritise by what matters most to the business.** Bottom and Post-Purchase funnel, high-volume clusters, and gaps with a clear fix path rank highest. Use demand data if available.

7. **Recommend actions that are grounded.** Every recommended action should trace back to something you found in the data — a specific prompt, a competing brand, a missing citation, a triggered checkpoint. Don't generalise.

---

## Output format

Present findings as a **Gap Report**:

### Summary
2–3 sentences: how many gaps, what the dominant pattern is, and the single highest-priority cluster to act on first.

### Gap cards (ranked)
One card per distinct gap, in priority order. Format each like this:

```
## [Gap type you identified] — [Topic or cluster name]

**Priority:** High / Medium / Low  
**Funnel:** Top / Mid / Bottom / Post-Purchase  
**What's happening:** One sentence describing the situation in plain language.  
**Evidence:** The specific metrics or rows that show this (prompt text, metric values, trigger type, competing brands).  
**Web presence:** What you found when checking for existing content.  
**Action:** Create / Optimize / Community / Outreach (and why — one clause).  
**If Optimize:** Which type — Content / Structure / Freshness — and what specifically to change.  
**Next steps:** 2–4 concrete actions the team can take immediately.  
```

Show at most 8 cards. If there are more, say so and offer to show the rest.

### Cluster table (if pre-computed clusters exist)
| Cluster | Gaps | Impact | Status | Action |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

### Starting point
End with one sentence: which single gap to act on first and why — grounded in what you found.

---

## Guardrails

- Every gap must trace back to data you queried. No invented gaps.
- Never apply a fixed threshold without checking if it makes sense in context.
- Filter `in_progress` opportunities out of what you surface.
- For metric meaning and formulas, load `insights-metrics`. For table and field names, load `backend-models`.
- Scope every query to the tenancy context in your system prompt.
- If the pre-computed pipeline data is recent and comprehensive, anchor to it. Derive from raw metrics to fill gaps or validate recency, not to replace it.

---

## Web search setup

`web_search` requires a Brave Search API key. Add `BRAVE_API_KEY=your-key` to `.env` (free tier: 2,000 queries/month).  
`check_url` works without any key.
