# Agent: Workplan Agent

**Stage:** 2 — Planning  
**Model:** Claude Sonnet  
**Calls:** 1 structured call (generate_workplan) + 1 stream (presentation)  
**Session state:** `workplan: {…}` — activated after intent phase completed

---

## What It Does

The Workplan Agent takes the completed brief and translates it into a production plan — confirming every block the user provided, setting the word count target, and listing the downstream steps the system will take before any writing begins.

---

## Input — What the Workplan Agent Receives

```json
{
  "blocks": {
    "topic": "How to find competitor keywords and close visibility gaps",
    "goal": ["educate", "increase_organic_traffic"],
    "audience": "SEO practitioners, digital marketers, content strategists",
    "content_type": "listicle",
    "length": "concise",
    "primary_keyword": "competitor keywords",
    "secondary_keywords": [
      "find competitor keywords", "visibility gaps", "keyword gap analysis",
      "SEO competitor analysis", "close visibility gaps"
    ],
    "guardrails": null,
    "competitive_refs": ["https://www.semrush.com/blog/competitor-keywords/"],
    "sources": [],
    "prompts": null
  },
  "brand_voice": "Analytical, Technical",
  "ruleset": "default-generic-v1"
}
```

---

## Structured Output — Internal Plan Object

```json
{
  "summary": {
    "topic": "How to find competitor keywords and close visibility gaps",
    "goal": ["educate", "increase_organic_traffic"],
    "audience": "SEO practitioners, digital marketers, content strategists",
    "content_type": "listicle",
    "length": "concise",
    "primary_keyword": "competitor keywords",
    "secondary_keywords": [
      "find competitor keywords", "visibility gaps", "keyword gap analysis",
      "SEO competitor analysis", "close visibility gaps"
    ],
    "competitive_refs": ["https://www.semrush.com/blog/competitor-keywords/"],
    "guardrails": null,
    "sources": [],
    "brand_voice": "Analytical, Technical"
  },
  "agent_steps": [
    "INSIGHTS INGESTION — Parse all input blocks: register primary keyword ('competitor keywords'), five secondary keywords, dual goals (educate + increase_organic_traffic), audience profile (SEO practitioners, digital marketers, content strategists), content type (listicle), concise length target, no optimization flag, null prompts/guardrails/sources, and brand voice (Analytical, Technical).",
    "REFERENCE GRADING — Fetch and score the competitive reference (https://www.semrush.com/blog/competitor-keywords/): audit its structure, keyword usage and density, internal/external linking patterns, media usage, estimated word count, and content depth. Identify what it covers well and where gaps exist that the new piece can exploit.",
    "AUTHORITY RESEARCH — Scrape the top organic SERP results for 'competitor keywords' and 'keyword gap analysis': extract common subtopics, recurring list items, featured-snippet formats, and PAA questions. Surface differentiating angles a concise listicle can own.",
    "GOAL & TYPE INTERPRETATION — Map dual goals to content requirements: 'educate' demands clear definitions, structured methodology, and actionable list items; 'increase_organic_traffic' requires strategic keyword placement (primary in title, H1, first 100 words; secondary keywords distributed across list-item headers and body), scannable listicle format, and a concise length (~800–1,100 words).",
    "RULESET APPLICATION — Apply default-generic-v1 ruleset: enforce single H1 containing primary keyword, secondary keywords mapped to H2/H3 list-item headers, no keyword stuffing, intro hook within first 50 words, each list item structured as [Header → Context → Action → Outcome], analytical and technical brand voice maintained throughout, CTA or next-step closer aligned with organic traffic goal."
  ],
  "estimated_word_count": 950,
  "applied_ruleset": "default-generic-v1"
}
```

---

## What the User Would See (workplan presentation stream)

> *"Here's what we're building and how we're going to get there.*
>
> *The brief is locked: a concise listicle targeting SEO practitioners and digital marketers, anchored on 'competitor keywords' as the primary keyword with five secondary terms covering gap analysis and SEO competitor research. Dual goals — educate and drive organic traffic — so the structure needs to be both methodologically clear and search-optimised.*
>
> *Before writing, I'll grade the SEMrush reference you provided to understand the existing bar, and run authority research to surface angles it misses. The outline will follow the standard listicle sequence: definition → why it matters → core principles → step-by-step process → examples → measurement → FAQ.*
>
> *Brand voice stays analytical and technical throughout — no fluff, no vague generalisations.*
>
> *Does this feel right? Approve and I'll generate the outline — or adjust anything you'd like to change first."*

---

## From the Insights Bucket — Failing Prompts

`prompts: null` — no failing prompts were submitted or injected for this session. The Outline Agent relied on the topic and competitive research alone.

---

## Cost

| Call | Tokens | Cost |
|------|--------|------|
| Structured generate_workplan | in=~900 out=~450 | ~$0.010 |
| Stream workplan presentation (~600 tokens) | in=~2,400 out=~600 | ~$0.016 |
| **Total** | | **~$0.026** |
