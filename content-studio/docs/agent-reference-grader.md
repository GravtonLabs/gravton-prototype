# Agent: Reference Grader

**Stage:** Background — fires on workplan approval  
**Model:** Claude Sonnet  
**Calls:** 1 structured call per URL (parallel, up to 4 at once)

---

## What It Does

The Reference Grader fetches each source URL the user submitted, reads the page, and classifies it. Only **earned media** — independent press, analyst reports, peer-reviewed sources — are passed to the Draft Builder as citable evidence. The rest are excluded.

---

## From This Session — Competitor Keywords (1 URL submitted)

The user submitted one competitive reference. No source URLs were submitted (`sources: []`).

```
1. https://www.semrush.com/blog/competitor-keywords/
```

---

### URL 1: SEMrush Blog — Competitor Keywords

> `https://www.semrush.com/blog/competitor-keywords/`

**Fetch:** Page accessible, ~5,200 chars of content

**What the model saw:**
```
"SEMrush Blog | What Are Competitor Keywords and How to Find Them
Published by the SEMrush team

Competitor keywords are the search terms your competitors rank for...
In this guide we'll show you how to use SEMrush's Keyword Gap tool
to find competitor keywords in minutes.
[Step-by-step walkthrough using SEMrush product interface]
[Screenshots of SEMrush dashboard]..."
```

**Classification call:**
```json
{
  "classification": "brand_owned",
  "quality_score": 0.28,
  "reason": "Content published on semrush.com by the SEMrush team. Serves as a product-led tutorial for SEMrush's own Keyword Gap tool. This is a brand-owned marketing asset designed to drive product adoption, not independent editorial analysis."
}
```

**Result:** ❌ Not citable — brand-owned product tutorial

---

### Final Reference Pack

```json
{
  "graded": [
    {
      "url": "https://www.semrush.com/blog/competitor-keywords/",
      "crawlable": true,
      "classification": "brand_owned",
      "quality_score": 0.28,
      "reason": "Brand-owned product tutorial — SEMrush promoting its own Keyword Gap tool"
    }
  ],
  "citable": [],
  "graded_at": "2026-06-18T15:09:21Z"
}
```

**`citable` is empty.** The SEMrush URL is structurally and thematically relevant — and was a useful competitive benchmark — but it does not qualify as earned media.

This matches the background log: `"Grader complete: 0 URL(s), 0 citable."`

---

## What This Means for the Draft

The Draft Builder receives an empty `citable` list. Its system prompt includes:

> *"EVIDENCE: quantitative claims may cite ONLY these earned-media URLs: []. No external citations are available — do not invent sources. Frame claims as best practices or widely observed patterns."*

The draft handles this correctly — all claims are framed as analytical observations ("competitors rank for", "visibility gaps transfer search market share") without invented citations.

The competitive reference is still accessible to the Outline Agent as context — it informs what the SEMrush article covers so the draft can differentiate, even though it cannot be cited.

---

## Cost

| URL | Fetch | LLM call | Cost |
|-----|-------|----------|------|
| semrush.com | 200 OK | in=~1,600 out=~100 | ~$0.006 |
| **1-URL total** | | | **~$0.006** |
