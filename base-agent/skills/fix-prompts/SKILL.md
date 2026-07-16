---
name: fix-prompts
description: Flow 3 of the Opportunity Engine — on-demand, targeted guidance on how to WIN a specific prompt, cluster, or metric the user picks. Load when the user asks "I'm trying to win this prompt / these prompts, what should I do differently?", "what am I missing in my content strategy to win this topic cluster?", "how can I raise my SOV (or any metric) here?", or selects weak/missing prompts and asks how to win them. Produces a concrete action plan: what is winning those prompts today, how competitors are doing better, the recommended actions to close the gap (create/optimize/community/outreach), and the references the user needs to act.
---

# Flow 3 — Fix specific prompts

On demand and reactive: the user points at where they're weak or missing — a prompt, a set of
prompts, a cluster, or a metric — and asks how to win. You analyse what's winning there today and
propose the actions that would close the gap, packaged so the customer can act immediately. This is
the reactive engine: the user picks the target, you work exactly that target.

## Input
A "how do I win this" question anchored to a prompt, cluster, or metric the user selects or names.

## Output
- **What's winning today** — the brands, pages, and source types that own those prompts now.
- **How competitors are doing better** — the specific edge (owned page, comparison content, a cited
  community thread, stronger sentiment).
- **Recommended actions to close the gap** — concrete, prioritised, each tagged by type:
  *Create* (new page), *Optimize* (improve an existing one), *Community* (seed/engage a thread), or
  *Outreach* (get cited by the sources that win). Mirror the existing `opportunity.action_type`
  vocabulary.
- **References to act on** — the exact cited URLs, competitor pages, and prompts, so the user can
  move without re-digging.

## Method
1. **Resolve the target.** Identify the prompt ids / cluster / metric. For a cluster or metric,
   first find the specific underperforming prompts within it (low/zero `visibility_score`,
   `is_present`=0, weak `sov` or high `position_rank` in `prompt_metric` / `generation_brand_metric`).
2. **See what's winning each target prompt today:**
   - *Who* — top brands by visibility/SoV/position on that prompt across recent runs.
   - *What pages* — the URLs winning the citations: `prompt_citation` ordered by
     `citation_mass_weight`, with `attribution_type`/`source_bucket` (owned vs community vs earned)
     and `normalized_domain`. Note whether third-party listicles, a competitor's owned page, or
     community threads dominate.
   - *Why* — competitor sentiment/positioning from `generation_brand_metric` and `brand_signal_metric`.
3. **Diagnose the gap** for the focal brand on each prompt: absent entirely, present but low
   position, present but losing the citation, or present but negative sentiment — each implies a
   different fix.
4. **Reuse existing recommendations if present.** Check `opportunity` / `opportunity_cluster` rows
   tied to these prompts (`gap_title`, `priority` = Quick Win / Big Bet / Filler, `action_type`,
   `action_items`, `target_venue`, `rationale`, `execution_paths`) and build on them rather than
   inventing from scratch.
5. **Propose the action plan**, matched to the gap and the winning pattern:
   - third-party listicles win ⇒ *owned page* + *outreach* to the cited sources.
   - a competitor's owned page wins ⇒ *create/optimize* a stronger, better-structured equivalent.
   - community threads win ⇒ *community* seeding/engagement on the cited venues.
   Prioritise by gap size × prompt volume × funnel weight (bottom-funnel first).
6. **Hand over the references** — list the winning URLs, competitor pages, and the exact prompts, so
   the plan is actionable.

## Guardrails
- Read-only: you produce a plan and references, you don't publish or change anything.
- Ground every "what's winning" claim in queried rows (the cited URLs and brands), not assumptions.
- Recommend content that fits the brand; don't suggest tactics that conflict with owning the answer
  honestly (no manipulation of review sites, no fake community posts).
- For metric meaning, defer to `insights-metrics`; for fields/joins, `backend-models`.
- This is action. If the user asks *why* something dropped first, that's Flow 2
  (`change-deep-dive`); if they ask what a metric means, Flow 4 (`metric-explainer`).

## Example
The user selects three prompts where the brand is absent, including *"best tools to detect malicious
activity from AI agents."* You find third-party listicles win all three (citations are `earned_media`
to review sites, no owned pages cited) and a competitor ranks first with a dedicated comparison page.
You propose: an owned, well-structured page targeting that intent, plus outreach to the specific
listicle domains that get cited, and note the competitor's sentiment edge ("clearer pricing"). You
hand back the exact winning URLs and the three prompt texts so the team can act.
