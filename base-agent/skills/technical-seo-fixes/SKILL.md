---
name: technical-seo-fixes
description: Flow 5 of the Opportunity Engine — explaining technical-SEO / AI-readiness audit findings and how to act on them, using audit data already in the database. Load when the user asks about a technical recommendation or audit issue, e.g. "what does this technical SEO recommendation mean?", "what is schema?", "are these schema changes hard to make?", "why does this matter?", "how important is fixing A versus B?", or "any resources for how to address it?". Produces an explanation of what the recommendation means, why it matters for AI reach/readability/trust, how hard it is, which issues to prioritise, and outside resources for fixing it.
---

# Flow 5 — Find and fix technical issues

On demand, over audit data already stored. Good content doesn't get cited if the page underneath is
broken. The audit already finds the technical problems that stop AI from reaching, reading, and
trusting the site. This flow explains a finding in plain language, says why it matters, how hard it
is to fix, how it ranks against other issues, and points to outside resources.

## Input
A question about a recommendation or audit issue, started from an audit finding or typed in chat.
Runs on audit data already in the database — you don't re-crawl.

## Output
For the issue in question:
- **What it means** — the recommendation in plain language.
- **Why it matters** — tied to AI being able to reach, read, or trust the page (and ultimately cite
  it).
- **How hard it is** — a realistic effort read (config/dev/content).
- **Priority** — which issues to fix first and why (severity × how many pages × whether those pages
  sit on high-demand clusters).
- **Resources** — pointers to standard external docs for the fix (e.g. schema.org, search/AI crawler
  documentation), described generally.

## Method
1. **Read the audit from the database.** Use the latest `technical_seo_scan` and its children:
   `finding` (type, severity `p0`/`p1`/`p2`, affected pages, fix hint), `page_check_result`
   (indexability, JS-rendering dependency, readability, schema, speed, mobile), `schema_check_result`,
   `bot_access_result` (per-bot reach, e.g. GPTBot / ClaudeBot / Googlebot), `sitemap_url`, and the
   dimension scores (`bot_access_score`, `rendering_score`, `readability_score`, `schema_score`,
   `mobile_score`, `speed_score`, `health_score`, `score_delta`, `robots_state`, `sitemap_state`).
   Confirm field names against the live schema; load `backend-models` for the exact model.
2. **Explain the specific finding** the user pointed at, plainly. Examples of meaning:
   - *Bot access blocked* — an AI crawler can't fetch the page, so it can never be cited.
   - *Rendering dependency* — content only appears after client-side JS, which crawlers may not run,
     so the page reads as empty.
   - *Schema mismatch / missing structured data* — the page doesn't describe itself in a machine
     form, weakening how confidently AI can use it.
   - *Stale content* — past a freshness threshold, so AI may treat it as outdated and prefer others.
   - *Broken links* — erode trust and crawlability.
3. **Say why it matters** in reach/read/trust terms, and connect it to visibility where you can:
   if a broken/blocked/stale page sits on a high-demand cluster (`keyword_library.ai_demand`) or one
   where the brand under-earns owned citations, that raises the stakes.
4. **Gauge difficulty** honestly: robots.txt/config changes are quick; schema additions are moderate
   and templated; re-rendering strategy or large content refreshes are heavier.
5. **Prioritise** by severity (`p0` > `p1` > `p2`) × number of affected pages × business value of the
   pages affected. When the user asks "A vs B," compare on those axes and give a clear order.
6. **Point to resources** — standard external documentation for the fix type (structured-data guides,
   crawler-access docs, rendering best practices), described in general terms.

## Guardrails
- Use only audit data already stored; don't claim to crawl or fetch live pages.
- Read-only — explain and prioritise; you don't change the site.
- Keep explanations jargon-light; define terms like "schema" when asked.
- Be honest about effort and don't overstate certainty on impact.
- For what a metric means, defer to `metric-explainer` / `insights-metrics`; for field/model names,
  `backend-models`.

## Example
The audit marks the site **Partially Ready**: 29 pages stale past 180 days, schema mismatches on the
Article template across 20 fields with 8 broken links, and 9 pages with no structured data — while
confirming GPTBot and ClaudeBot can reach the site. The user opens the freshness issue; you show the
exact stale pages from the audit, explain that refreshing them helps AI treat the content as current
and cite it, note it's a content-effort fix, and rank it against the schema gaps by how many
high-demand pages each touches.
