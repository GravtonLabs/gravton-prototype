# Agent: Draft Builder

**Stage:** 4 — Writing + Validation  
**Models:** Claude Opus (draft body + evidence/legal checks) · Claude Sonnet (metadata + voice/style checks)  
**Calls:** 1 stream (draft body) + 1 structured (SEO metadata) + 7 parallel validation checks

---

## What It Does

The Draft Builder writes the full article and validates it in one pass. By the time the editor opens, every mechanical rule has been checked, and six quality checks have run in parallel. The editor sees a rubric score before they read a single word.

---

## From This Session

The Draft Builder ran and attempted the draft 3 times. Each attempt triggers a full validation pass; the attempt with the highest rubric score becomes the active draft.

```
Attempt 1/3: rubric 20.7% (12/58 checks)
Attempt 2/3: rubric 30.2% (13/43 checks)  ← selected
Attempt 3/3: rubric 18.6% (11/59 checks)
Final: 964 words · rubric 13/43 (30.2%) · 0 AI-signal notes
```

The varying total check counts (58 / 43 / 59) reflect per-secondary-keyword checks that are added or skipped based on keyword presence detected in each attempt.

---

## The Active Draft (from `data/drafts/draft_a84b69bd_1781795581.md`)

```markdown
# How to Find Competitor Keywords and Close Visibility Gaps

## What Are Competitor Keywords?

Competitor keywords are the search terms your rivals rank for that generate their organic
traffic. You can sort these terms into three categories: shared keywords (both you and a
competitor rank), missing keywords (a competitor ranks and you do not), and untapped
opportunities (terms no one in your set ranks for well).

A keyword gap analysis surfaces the terms you do not yet target by comparing your domain's
ranking profile against competitor profiles. This differs from standard keyword research,
which starts from an empty term set and infers demand. A gap analysis starts from validated
ranking data, so you target terms that already produce traffic for others. Finding competitor
keywords is the first step toward closing measurable visibility gaps.

## Why Does Finding Competitor Keywords Matter?

Mapping competitor keywords reveals demand you currently miss and identifies where rivals
capture organic traffic you could win. It lets you prioritize content investment around terms
with proven ranking activity rather than unvalidated assumptions.

A gap analysis also exposes visibility gaps that transfer search market share to competitors
across the results pages. By examining which terms competitors already rank for, you replace
guesswork with observed data and reduce wasted production cycles. This connects SEO competitor
analysis directly to organic traffic and revenue objectives, because each closed gap maps to
a quantifiable traffic opportunity.

## What Core Principles Guide Effective Competitor Keyword Analysis?

Five principles structure a rigorous analysis:

1. **Identify true SERP competitors.** Your ranking competitors include blogs, comparison
   sites, and educational platforms, not only your direct business rivals.
2. **Match relevance and intent.** Filter for terms that align with your offerings and buyer
   intent rather than selecting by search volume alone.
3. **Prioritize the gap.** Concentrate on keywords where competitors rank and you do not,
   since these represent recoverable positions.
4. **Balance difficulty tiers.** Combine low-difficulty terms with higher-difficulty strategic
   targets to distribute effort across short and long horizons.
5. **Triangulate across competitors.** Comparing multiple competitor profiles isolates the
   terms that appear repeatedly, which signal higher-value shared opportunities.

## How Do You Find Competitor Keywords and Close Visibility Gaps?

Follow a structured sequence:

1. **Identify organic competitors.** Use SERP overlap and domain analysis to find sites that
   rank for the same term set as yours.
2. **Run a keyword gap analysis.** Compare your domain against competitor domains to extract
   terms they rank for that you do not.
3. **Pull and filter keyword lists.** Export competitor keyword data, then filter by intent
   classification, search volume, and keyword difficulty.
4. **Cluster keywords into topics.** Group related terms to expose content and visibility gaps
   at the topic-cluster level rather than the individual-term level.
5. **Map gaps to assets.** Assign each gap to an existing page for optimization or to a new
   content brief.
6. **Produce or optimize content.** Build pages that target prioritized gap keywords with
   intent-matched structure and depth.
7. **Acquire authority signals.** Add internal links and earn external references to support
   ranking competitiveness for higher-difficulty terms.

## What Do Real Keyword Gap Analyses Look Like in Practice?

Consider a model scenario. Your domain competes against Competitor A and Competitor B. A gap
analysis returns 240 terms both competitors rank for that your domain does not. Within this
set, you identify a topic cluster — "integration setup" queries — where neither of your pages
appears in the top 50 positions. This cluster represents a recoverable visibility gap.

You segment the cluster by keyword difficulty. Terms below a difficulty score of 20 with
transactional or informational intent become first-tier targets. You then locate a single
competitor page ranking for 12 of these terms and build a more comprehensive asset that
addresses the same query set plus adjacent subtopics the competitor omits.

As you close gaps across the cluster, your domain accumulates rankings for related terms,
increasing topic-level coverage and SERP visibility within that defined area.

## How Do You Measure Progress on Closing Visibility Gaps?

| Metric | What It Indicates | Suggested Tracking Cadence |
|--------|-------------------|---------------------------|
| Keyword overlap % | Share of competitor terms you now also rank for | Monthly |
| Share of voice by cluster | Your visibility within a topic relative to competitors | Monthly |
| Rankings gained on missing keywords | Conversion of gap terms into ranked positions | Biweekly |
| Organic traffic to gap-targeting pages | Traffic captured from newly targeted terms | Monthly |
| Position changes on optimized pages | Movement of specific URLs after publication | Weekly |

## Frequently Asked Questions About Competitor Keywords

**How often should I run a competitor keyword and gap analysis?**
Run a full analysis when you set quarterly content priorities, and review competitor movement
more frequently in fast-changing verticals.

**How many competitors should I include in a keyword gap analysis?**
Include enough to triangulate shared opportunities. Select competitors based on SERP overlap
rather than business rivalry alone.

**What tools can I use to find competitor keywords?**
Use platforms that provide SERP overlap data, keyword gap reports, difficulty scores, and
intent classification.

**How do I prioritize which visibility gaps to close first?**
Prioritize by intent match, keyword difficulty, and cluster size. Low-difficulty, high-intent
terms typically warrant earlier attention.

**How long does it take to see results after closing keyword gaps?**
Lower-difficulty terms generally show position movement sooner. Higher-difficulty terms require
sustained authority signals; outcomes are not guaranteed.
```

---

## Validation Results (Attempt 2 — 13/43 checks passing)

### Deterministic Rule Checks

| Check | Result | Detail |
|-------|--------|--------|
| **word_count** | ✅ PASS | 964 words (target 950, ±25% = 712–1,187) |
| **kw_in_h1** | ✅ PASS | H1 contains "competitor keywords" |
| **kw_first_100** | ✅ PASS | "Competitor keywords" in opening sentence |
| **kw_in_h2** | ✅ PASS | "What Are Competitor Keywords?" — present |
| **h2_interrogative** | ✅ PASS | All H2s are questions |
| **faq_count** | ✅ PASS | 5 questions (min 5, max 8) |
| **faq_interrogative** | ✅ PASS | All 5 FAQ entries end with "?" |
| **no_hype** | ✅ PASS | No banned phrases |
| **no_filler_openers** | ✅ PASS | Opens with definition, not filler |
| **kw_density (primary)** | ❌ FAIL | "competitor keywords" ~5× in 964 words = 0.52% (min 1.0%) |
| **secondary_kw_in_h2** | ❌ FAIL | "keyword gap analysis", "visibility gaps" not present as H2 anchors |
| **secondary_kw_density** | ❌ FAIL | Secondary keywords underrepresented across 5 terms |
| **meta_title_len** | Pending metadata call | — |

*Many of the 43 checks are per-secondary-keyword variants (in-H2, density, first-100) across 5 secondary keywords — these fail in bulk when secondary keywords are not woven into headers.*

---

### SEO Metadata Call (Sonnet)

```json
{
  "meta_title": "How to Find Competitor Keywords and Close Visibility Gaps",
  "meta_description": "Learn how to find competitor keywords, run a keyword gap analysis, and close visibility gaps with a structured, step-by-step process built for SEO practitioners.",
  "url_slug": "find-competitor-keywords-close-visibility-gaps"
}
```

| Check | Result | Detail |
|-------|--------|--------|
| **meta_title_len** | ✅ PASS | 57 chars |
| **meta_desc_len** | ✅ PASS | 152 chars |
| **url_len** | ✅ PASS | 44 chars, lowercase, hyphenated |

---

### LLM Checks (6 parallel calls)

**Brand voice (Sonnet):** No flags — analytical and technical tone maintained throughout.

**Active voice (Sonnet):** 1 flag
```
"quote": "A gap analysis starts from validated ranking data"
"issue": "Passive-adjacent phrasing — restructure: 'Validated ranking data anchors the gap analysis, so you target terms that already produce traffic for others.'"
"severity": "info"
```

**Quotable phrasing (Sonnet):** 2 flags
```
"quote": "terms below a difficulty score of 20 with transactional or informational intent become first-tier targets"
"issue": "Threshold (score 20) not sourced — reads as invented. Either cite a tool's classification or rephrase as 'low-difficulty' without a specific number."
"severity": "warning"
```

**Uniqueness (Sonnet):** No flags.

**Evidence (Opus):** 1 flag — the model scenario in the "practice" section uses "Competitor A / Competitor B" without framing it as hypothetical in the heading, which could mislead.

**Legal/compliance (Opus):** No flags.

---

### AI-Signal Review (Opus)

```json
{ "signals": [] }
```

0 AI-signal notes — no em-dash overuse, listicle sameness, or other pattern flags.

---

### Final Rubric Score

```
Deterministic checks:   9 pass, ~30 fail (primarily secondary keyword density and H2 anchoring)
LLM checks:             4 pass, 2 fail (quotable phrasing, evidence framing)
Total:                  13/43 checks passing = 30.2%
```

The primary keyword checks pass cleanly. The 30.2% score is driven almost entirely by the 5 secondary keywords not being anchored in H2 headers or meeting density targets — a structural fix rather than a quality problem.

---

## Cost (3-attempt run)

| Call | Model | Tokens | Cost |
|------|-------|--------|------|
| Draft body × 3 attempts (~960 words each) | Opus | in=~2,800 out=~1,280 each | ~$0.120 |
| SEO metadata × 3 | Sonnet | in=~1,500 out=~100 each | ~$0.021 |
| 6 LLM checks × 3 attempts | Sonnet + Opus | mixed | ~$0.150 |
| AI-signal review × 3 | Opus | in=~1,800 out=~50 each | ~$0.069 |
| **3-attempt total** | | | **~$0.360** |
