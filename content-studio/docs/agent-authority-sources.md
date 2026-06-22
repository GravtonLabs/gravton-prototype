# Agent: Authority Sources

**Stage:** Background — fires in parallel with Reference Grader on workplan approval  
**Model:** Claude Sonnet (with live web search)  
**Calls:** 1 text call with web_search tool enabled

---

## What It Does

The Authority Sources agent researches what analysts, press, and communities currently say about the article's topic. It produces a concise cited summary — under 250 words — that the Draft Builder uses as background context when writing.

No guardrails were submitted for this session, and no `prompts` were injected from the Insights bucket. The agent used the topic and primary keyword directly.

---

## From This Session — Competitor Keywords Brief

**Input to the agent:**
```
topic: "How to find competitor keywords and close visibility gaps"
prompts: null
```

**Query constructed:** `"competitor keyword analysis keyword gap analysis best practices"` and `"find competitor keywords SEO visibility gap"`

---

### The Model Call

```
System: "Research authoritative context for the topic. Summarise what analysts,
press and communities say. Cite source names inline. Under 250 words."

User: "Topic: How to find competitor keywords and close visibility gaps"

Tools: [{ "type": "web_search_20250305", "name": "web_search" }]
```

The model ran two searches:
1. `"keyword gap analysis SEO process competitor keywords 2025"`
2. `"closing visibility gaps organic search strategy"`

---

### Output — Authority Summary (stored, passed to Draft Builder)

```json
{
  "summary": "Keyword gap analysis is an established component of technical SEO, used to identify search terms that competitor domains rank for while the analysing domain does not. Industry practitioners — including coverage in Search Engine Journal, Ahrefs Blog, and Moz — consistently frame competitor keyword research as a three-step process: identify SERP competitors (which may differ from direct business rivals), extract their ranking keyword profiles, and filter by intent and difficulty to find actionable gaps. The distinction between 'missing' keywords (competitor ranks, you don't) and 'shared' keywords (both rank) is standard in the gap analysis framework. Research indicates that topic-cluster-level gap analysis — grouping related gap terms into clusters before assignment — is more efficient than term-by-term prioritisation. Visibility gap measurement is typically tracked through keyword overlap percentage, share of voice by cluster, and rankings gained on previously missing terms. Lower-difficulty gap terms generally show position movement within 60–90 days; higher-difficulty terms require sustained authority signals. No single tool is required — the underlying data (SERP overlap, ranking profiles, difficulty scores) is available across multiple platforms.",
  "query": "competitor keyword analysis keyword gap analysis",
  "ok": true,
  "at": "2026-06-18T15:09:47Z"
}
```

---

### How the Draft Builder Uses This

The authority summary is injected into the Draft Builder's system prompt as background context. The draft's precision — e.g., the explicit distinction between shared/missing/untapped keywords, the topic-cluster grouping step, and the measurement table cadences — traces to this summary.

---

## Cost

| Item | Tokens | Cost |
|------|--------|------|
| Web search + synthesis | in=~700 out=~280 | ~$0.006 |
| **Total** | | **~$0.006** |
