# Agent: Outline Agent

**Stage:** 3 — Structure  
**Model:** Claude Opus  
**Calls:** 1 structured call (generate_outline) + 1 per revision  
**Session state:** `outline: {…}` — activated after workplan approved

---

## What It Does

The Outline Agent builds the article's section-by-section skeleton before any body copy is written. It applies the ruleset's section sequence, heading format rules, and keyword placement constraints — then presents the structure to the user for review and revision.

---

## From This Session

The user approved the workplan and the Outline Agent produced a 7-section listicle structure. Background agents (Reference Grader + Authority Sources) fired simultaneously.

---

## Structured Output — Outline Object

```json
{
  "title": "How to Find Competitor Keywords and Close Visibility Gaps: A Practical Guide",
  "content_type": "listicle",
  "sections": [
    {
      "heading": "What Are Competitor Keywords?",
      "type": "paragraph",
      "key_points": [
        "Define competitor keywords as the search terms competitors rank for that drive their organic traffic",
        "Explain the difference between shared keywords, missing keywords, and untapped opportunities",
        "Introduce keyword gap analysis as a way to surface terms you don't yet target",
        "Clarify how competitor keywords differ from standard keyword research starting from scratch",
        "Set expectations: finding competitor keywords is the first step toward closing visibility gaps"
      ],
      "estimated_words": 160
    },
    {
      "heading": "Why Does Finding Competitor Keywords Matter?",
      "type": "paragraph",
      "key_points": [
        "Reveals demand you are missing and where rivals capture organic traffic you could win",
        "Helps prioritize content investment based on proven, ranking search terms",
        "Exposes visibility gaps that quietly cede market share to competitors in the SERPs",
        "Speeds up strategy by learning from competitors' wins instead of guessing",
        "Connects SEO competitor analysis directly to organic traffic and revenue growth goals"
      ],
      "estimated_words": 160
    },
    {
      "heading": "What Core Principles Guide Effective Competitor Keyword Analysis?",
      "type": "listicle",
      "key_points": [
        "Identify true SERP competitors, not just direct business competitors",
        "Focus on relevance and intent match, not just high-volume terms",
        "Prioritize keywords where competitors rank but you don't (the gap)",
        "Balance quick wins (low difficulty) with strategic long-term targets",
        "Use multiple competitors to triangulate the most valuable shared opportunities"
      ],
      "estimated_words": 180
    },
    {
      "heading": "How Do You Find Competitor Keywords and Close Visibility Gaps?",
      "type": "listicle",
      "key_points": [
        "Step 1: Identify your top organic competitors using SERP overlap and domain analysis",
        "Step 2: Run a keyword gap analysis to find terms competitors rank for that you don't",
        "Step 3: Pull competitor keyword lists and filter by intent, volume, and difficulty",
        "Step 4: Cluster keywords into topics to spot content and visibility gaps",
        "Step 5: Map gaps to existing pages or new content briefs to close them",
        "Step 6: Build or optimize content targeting prioritized gap keywords",
        "Step 7: Earn internal links and authority signals to compete for higher rankings"
      ],
      "estimated_words": 320
    },
    {
      "heading": "What Do Real Keyword Gap Analyses Look Like in Practice?",
      "type": "listicle",
      "key_points": [
        "Walk through a hypothetical example comparing your domain against two competitors",
        "Show how a missing topic cluster represents a recoverable visibility gap",
        "Illustrate prioritizing low-difficulty, high-intent keywords for fast wins",
        "Demonstrate turning a competitor's ranking page into a better, more comprehensive asset",
        "Note that results compound as gaps close across an entire topic area"
      ],
      "estimated_words": 200
    },
    {
      "heading": "How Do You Measure Progress on Closing Visibility Gaps?",
      "type": "table",
      "key_points": [
        "Track keyword overlap percentage with key competitors over time",
        "Monitor share of voice and SERP visibility for target topic clusters",
        "Measure organic traffic and rankings gained on previously missing keywords",
        "Watch position changes for newly published or optimized gap-targeting pages",
        "Review the table of metrics, what they indicate, and recommended tracking cadence"
      ],
      "estimated_words": 180
    },
    {
      "heading": "Frequently Asked Questions About Competitor Keywords",
      "type": "listicle",
      "key_points": [
        "How often should I run a competitor keyword and gap analysis?",
        "How many competitors should I include in a keyword gap analysis?",
        "What tools can I use to find competitor keywords?",
        "How do I prioritize which visibility gaps to close first?",
        "How long does it take to see results after closing keyword gaps?"
      ],
      "estimated_words": 200
    }
  ]
}
```

**Total estimated words:** 1,200 (exceeds the "concise" bucket target of ~950; the Draft Builder trims during generation)

---

### Ruleset Notes

The outline uses question-format H2 headings throughout — consistent with `h2_interrogative: true` in `default-generic-v1`. The final draft came in at 964 words (within the ±25% tolerance on 950). The "table" type in section 6 (measurement metrics) was correctly produced as a markdown table in the draft.

---

## Cost

| Call | Model | Tokens | Cost |
|------|-------|--------|------|
| generate_outline (initial) | Opus | in=~2,000 out=~550 | ~$0.024 |
| Stream outline presentation | Sonnet | in=~1,600 out=~380 | ~$0.010 |
| revise (none in this session) | — | — | — |
| **Total** | | | **~$0.034** |
