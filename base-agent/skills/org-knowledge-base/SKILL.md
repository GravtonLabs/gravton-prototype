---
name: org-knowledge-base
description: Plain-English data dictionary written specifically for an AI agent answering questions about a client's data — what each concept means, why it exists, what the key fields mean in business terms, how they connect, and a "which data answers which question" quick-reference table at the end. Load to translate raw query results into business language, or to decide what data answers a user's question.
visibility: internal
---

# Organization Knowledge Base

**What this document is:** A plain-English reference for every type of data the Gravton Platform stores for a client organisation. It is written for an AI agent that answers questions about a client's data. Each section defines what a concept is, why it exists, what the key fields mean, and how it connects to other data.

**How to use it:** When a user asks something like "What competitors are we tracking?" or "Why did our visibility score drop?", use this document to understand what data to look for, what the fields mean, and how to interpret an answer in business terms.

---

## The Shape of an Organisation's Data

Every piece of data on the platform is owned by an **Organisation** and scoped to one of its **Domains**. Think of the Organisation as the company account, and the Domain as the specific website being analysed. Almost every question you answer will start by identifying the right Organisation and then the right Domain.

The data then falls into these broad categories:

1. **Brand Identity** — who the client is and who they compete with
2. **The Prompt Universe** — the questions we believe real buyers ask AI models
3. **AI Visibility Measurements** — what happened when we ran those questions through AI models
4. **Citation Data** — which URLs the AI actually referenced
5. **Brand Scores** — aggregated metrics derived from the measurements
6. **Social Intelligence** — what people say on Reddit and Quora
7. **Opportunities** — gaps identified and actions recommended
8. **Technical SEO** — how AI-ready the client's own website is
9. **Search Data** — traditional Google Search Console performance
10. **System Operations** — pipeline runs and workflow state

---

## 1. Organisation

The Organisation is the top-level client account. Everything on the platform belongs to an Organisation.

**What we store:**
- **Name and brand name** — the company name and the display name used in the product
- **Primary domain** — their main website URL (not to be confused with the `Domain` object, which is the tracked website for analysis)
- **Size** — a bucketed company size category
- **Region** — APAC, Americas, or EMEA — sets the geographic context for all analysis
- **Status** — whether the account is active

**What it tells you:** When someone says "the client," they mean an Organisation. Everything else — domains, competitors, prompts, scores — traces back here.

---

## 2. Domain

A Domain is a specific website the client has added for tracking and analysis. Most clients have one domain (their main website), but large organisations may have several.

**What we store:**
- **URL** — the website address being tracked (e.g., `hubspot.com`)
- **Name** — a human-readable label for the domain
- **Target locations** — the geographic markets the client cares about (e.g., US, UK, India)
- **Topic extraction snapshot** — a cached summary of topics found on the website, used during initial setup
- **Competitors initialised flag** — whether the system has already seeded an initial competitor list for this domain

**What it tells you:** The Domain is the unit of analysis. Every prompt we track, every AI response we measure, every competitor we monitor — it all belongs to a Domain. When a user asks about "our data," they almost always mean "data for this Domain."

> A Domain is not the same as the Organisation's primary domain field. The `Domain` object is the analysis unit; the Organisation's domain field is just contact information.

---

## 3. Brand Identity

### Organisation Users

Each person with access to the account is stored as an Organisation User. They belong to one Organisation and have a role of either **owner** or **member**.

**What we store:** The user account, their profile picture, their role, and whether their access is active.

---

### Brand Kit

The Brand Kit is an AI-generated profile of the client's brand. It is created automatically during onboarding by crawling the client's website.

**What we store:**
- **Description** — what the company does, in plain language
- **Market segment** — which segment of the market they serve
- **Brand voice** — the tone and style the company uses in its communications
- **Buyer description** — who their typical buyer is
- **Sector** — the industry they operate in
- **Which AI model generated it** and which version of the brand kit this is

**What it tells you:** The Brand Kit captures Gravton's understanding of the client's identity. If a user asks "how does Gravton describe us?" — this is the answer. The client can edit all fields. Multiple versions may exist for different parts of the site (different domains) or different competitor comparisons.

---

### Competitors (including the Focal Brand)

A Competitor is any brand being tracked alongside the client. This includes the client's own brand — which is stored as a competitor with the special flag `is_focal = True`.

**What we store:**
- **Name** — the brand name (e.g., "Salesforce")
- **URL** — the competitor's primary website
- **Is focal** — whether this is the client's own brand
- **Pool rank** — a rough importance rank among competitors
- **Source** — whether this competitor was `user_added` (manually entered), `suggested` (recommended by the system), or `discovered` (found through citation analysis)
- **Is active** — whether this competitor is currently being tracked

**What it tells you:** When we measure AI visibility, we always measure it for every tracked brand — the client's own brand (the focal brand) and all competitors. This lets us answer "how does the client compare to Salesforce?" A competitor with `is_focal=True` is the client. Never call the focal brand "the client" in metric lookups — the data is stored as a competitor, just like the others.

---

### Brand Aliases

A Brand Alias is an alternate name for a competitor. Salesforce might also appear in AI responses as "SFDC" or "Salesforce CRM." We store all known aliases.

**What we store:** The alias text, which competitor it belongs to, whether it is the canonical (primary) name, and whether a human or AI discovered it.

**What it tells you:** When we scan AI responses for brand mentions, we look for all aliases, not just the primary name. If someone asks "are we picking up all mentions of our brand?", brand aliases determine the answer.

---

### Competitor Domain Aliases

A Competitor Domain Alias is an additional website that belongs to the same competitor. For example, `google.com`, `google.co.uk`, and `google.in` all belong to Google.

**What we store:** The domain string (e.g., `google.co.uk`), which competitor it belongs to, whether it is the primary domain, and how it was discovered (`user_added`, `ai`, `inferred`, or `system_auto`).

**What it tells you:** When an AI cites `google.co.uk`, the system needs to attribute that citation to the Google competitor. Domain aliases make that attribution possible. If visibility data seems to undercount a competitor, missing domain aliases are often the reason.

---

### Owned Domain Suggestions

An Owned Domain Suggestion is a domain that appeared frequently in AI citations but has not yet been confirmed as belonging to any tracked competitor. The system flags it for human review.

**What we store:** The suggested domain, which competitor it might belong to, how many times it was cited, how it was discovered, and its review status: `needs_review`, `auto_linked`, `linked`, `rejected`, or `revoked`.

**What it tells you:** This is the pipeline for discovering new competitor properties. If a domain keeps appearing in citations but isn't attributed to any brand, it ends up here until a human decides what to do with it.

---

### Product Verticals

A Product Vertical is a distinct line of business within a domain — for example, "Zoho CRM" and "Zoho Books" are two separate product verticals under Zoho.

**What we store:** The vertical name, a description of the products/services in it, which domain it belongs to, and optionally which competitor it is associated with (for mapping competitor product lines).

**What it tells you:** Verticals allow the platform to separate the analysis for different product areas. A prompt about "expense management software" should be measured differently from a prompt about "payroll software," even if both belong to the same company. Vertical-level segmentation is the foundation of all deeper analysis.

---

### Personas

A Persona is a buyer role that uses the client's product. The platform supports three: **Decision Maker**, **Influencer**, and **User**.

**What we store:** Which persona type, and which domain it belongs to. One record per persona type per domain.

**What it tells you:** Personas tag prompts — a question that a CFO asks is different from a question that a sales rep asks, even if both are about CRM software. Persona-tagged data allows filtering the entire analysis by who is asking.

---

## 4. The Prompt Universe

### Intent Clusters

An Intent Cluster is a named group of related prompts. Think of it as a topic — all the different ways someone might ask about "enterprise CRM pricing" grouped together under one label.

**What we store:**
- **Label** — the cluster name (e.g., "CRM for enterprise sales teams")
- **Target locations** — geographic filter for this cluster
- **Target categories** — category filter
- **Product vertical** — which line of business this topic belongs to
- **Source** — whether this cluster was `suggested` by the system, `user_added`, or generated by an automated L3 workflow
- **Is active** — whether prompts in this cluster are being run

**What it tells you:** Every metric on the platform rolls up from prompt-level to cluster-level. If a user asks "how are we performing on CRM topics?", the cluster is the right unit of analysis.

---

### Synthetic Prompts

A Synthetic Prompt is one specific question that a real buyer might type into an AI model. It is the atomic unit of analysis — every AI response, every citation, and every metric starts here.

**What we store:**
- **Text** — the actual question (e.g., "What is the best CRM for a 50-person sales team?")
- **Cluster** — which topic group it belongs to
- **Funnel stage** — where in the buyer journey this question fits: `Top` (awareness), `Mid` (evaluation), `Bottom` (decision), or `Post-Purchase` (existing customer questions)
- **Prompt type** — `Breadth` (covering wide ground across a topic) or `Depth` (focused follow-up questions)
- **Persona** — which buyer role is most likely to ask this
- **Location** and **category** — geographic and topical context
- **Prompt weight (w_p)** — how important this prompt is relative to others in its cluster; higher-volume prompts get higher weight
- **Execution count** — how many times this prompt has been run through AI models
- **Source** — how it was created
- **Is active** — whether it is currently being run
- **Is branded** — whether the prompt text itself mentions a brand name
- **Matched brands** — which brands appear directly in the prompt text

**What it tells you:** When someone asks "what questions are we tracking?", synthetic prompts are the answer. Every prompt that goes active has been reviewed and approved by a human — no prompt runs automatically without approval. The `execution_count` tells you how much data exists for a given question.

---

### Keyword Library

The Keyword Library is the collection of search keywords connected to a domain. Keywords come from Google Search Console, CSV uploads, or AI-powered research.

**What we store:**
- **Keyword** — the keyword text
- **Search Volume (sv)** — traditional Google search volume
- **AI Search Volume (asv)** — estimated volume for this keyword in AI-mediated searches
- **AI Demand (ai_demand)** — a Bayesian-fused estimate combining both signals; the most reliable volume indicator
- **Source** — `gsc` (from Google Search Console), `upload` (from a CSV file), `brand`, or `L3_source` (from an automated pipeline)
- **Intent cluster** — which cluster this keyword has been mapped to
- **Score** — relevance score

**What it tells you:** Keywords ground the prompt universe in real search data. They answer "are the prompts we're tracking actually based on real demand?". The `ai_demand` field is the most actionable signal for prioritisation.

---

## 5. AI Visibility Measurements

### Workflows

A Workflow is a record of one pipeline job that was triggered from the platform. Every time we run prompts through AI models, crawl a website, or compute metrics — a Workflow record tracks it.

**What we store:** Which organisation and domain it ran for, the pipeline identifier (`dag_id`), the external run identifier (`run_id`), the status (`QUEUED`, `RUNNING`, `SUCCESS`, `FAILED`, `STALLED`), status message, and timestamps for when it started and completed.

**What it tells you:** If a user asks "when did we last run our analysis?", Workflow records answer that. `STALLED` means the job was triggered but never started — useful for diagnosing silent pipeline failures.

---

### Insight Runs

An Insight Run is a versioned analysis cycle for one topic cluster on one AI model. It groups all the AI responses produced in a single sweep.

**What we store:** The run identifier, which cluster it analysed, which AI model (`model_id`, e.g., `google/gemini-2.5-flash`, `openai/gpt-4o`), and a version number that increments with each new run.

**What it tells you:** Insight Runs are the containers for historical data. Each new run creates a new snapshot. When you compare "this week vs last week," you are comparing two different Insight Runs. The version number lets you identify which run is more recent.

---

### Generations

A Generation is one AI model response — the result of running one specific prompt through one specific AI model, one time.

**What we store:**
- **Generation ID** — unique identifier
- **Which prompt, cluster, domain, and organisation** this belongs to
- **Which AI model** produced it
- **Generation K** — the repetition index; if we run the same prompt twice (k=0 and k=1), this tells you which repetition
- **Response excerpt** — the first 320 characters of the response (for previews)
- **Full response** — stored in S3, not in the database
- **Brands list** — which brands were detected in the response
- **Brands mentioned count** — how many brands appeared
- **Focal brand present** — whether the client's own brand appeared in this response

**What it tells you:** A Generation is the raw evidence. Every score, every metric, every citation is derived from Generations. If a user asks "did GPT-4o mention us in response to this question?", you look at the Generation.

---

### Response Execution Progress

This tracks the status of each individual AI call within a pipeline run — useful for understanding why a run might be slow or incomplete.

**What we store:** Which run, prompt, model, and repetition index; progress percentage (0–100); attempt count (for retries); the Celery task ID; and an error code if it failed.

---

## 6. Citation Data

### Pipeline Runs

A Pipeline Run is a separate tracking record for the citation extraction phase — the process that reads AI responses and identifies which URLs were cited.

**What we store:** A run identifier, which domain and organisation it processed, the current status (`queued`, `running`, `completed`, `failed`), the current stage within the pipeline, and timestamps.

**What it tells you:** When a user asks "have our citation numbers been updated recently?", a Pipeline Run tells you when that computation last completed.

---

### Prompt Citations

A Prompt Citation is a single URL that appeared in an AI response. It is the most granular record of what the AI actually referenced.

**What we store:**
- **Which AI response (Generation)** it came from
- **Which prompt** was being run
- **The page URL** that was cited
- **The domain** extracted from that URL
- **Which competitor brand** this URL belongs to (after attribution)
- **Attribution type** — `owned` (the client's own pages), `community` (Reddit, G2, review sites, forums), or `earned_media` (third-party publications, press, PR)
- **Citation mass weight** — how much this citation counts, accounting for how often the same domain appears and a damping factor for repeated citations
- **Damping factor** — a decay applied when the same domain is cited multiple times in one response
- **Claim text** — the specific claim the AI was citing this URL to support
- **Confidence** — how confident the extraction was
- **Included in metrics** — whether this citation feeds into aggregated scores

**What it tells you:** Citations answer "which URLs does the AI recommend when people ask questions in our category?". The `attribution_type` tells you whether those URLs are the client's own content, community content, or editorial coverage. Tracking how this distribution shifts over time is the core of Adoption Health monitoring.

---

### Generation Metric

A Generation Metric records the metadata of one AI model call — which model, which prompt, how many times it ran, and a response excerpt. It is a companion to the Generation record, used by the citation pipeline.

---

### Citation Competitor Candidates

A Citation Competitor Candidate is a domain that keeps appearing in AI citations but is not yet linked to any tracked competitor. These are surfaced for human review to potentially add as new competitors or link to existing ones.

**What we store:** The domain, which pipeline run found it, and how many times it was cited.

**What it tells you:** These are hints that the client's competitive landscape may have gaps. If a domain is being frequently cited by AI but the client doesn't know who owns it, this is where that signal surfaces.

---

## 7. Brand Scores

### Prompt Metrics

A Prompt Metric is the aggregated score for one brand, on one prompt, in one Insight Run. This is the primary analytics record — the number that shows up in dashboards.

**What we store:**
- **Which run, prompt, and brand** this is for
- **Execution count** — how many AI responses contributed to this score
- **Visibility score** — a normalized composite score representing how visible this brand is when AI answers this question
- **Share of Voice (SOV)** — what proportion of all brand mentions in AI responses belong to this brand
- **Position rank** — the average position at which this brand is mentioned (1 = first mentioned)
- **Presence rank** — ranking by how often the brand appears at all
- **Sentiment score** — a signed number from –1 to +1; positive means the AI talks about this brand positively
- **Consistency score** — how uniform the AI responses are about this brand across multiple runs of the same prompt; high consistency means the AI says the same things every time
- **Consistency bucket** — a categorical version of the consistency score (low, medium, high)
- **Brand present count** — how many of the AI responses included this brand at all
- **Presence suppressed** — if there are too few responses to compute a reliable score, this flag is set and the score is hidden from the UI

**What it tells you:** Prompt Metrics answer specific questions like "Is our brand mentioned when people ask about enterprise CRM pricing?" and "How do we compare to Salesforce on that question?". The four key numbers are: visibility score, SOV, sentiment score, and position rank.

---

### Brand Metrics

Brand Metrics are a leaner set of scores per brand, per prompt, per run. They are used in comparison tables and side-by-side views.

**What we store:** Presence rate, presence rank, position rank, position score, visibility score, SOV, SOV rank, sentiment score, and sentiment rank.

---

### Topic Metrics

A Topic Metric aggregates all prompt-level scores for one brand across an entire Intent Cluster (topic group) in one run.

**What we store:**
- **Which run, domain, cluster, and brand** this covers
- **Is focal** — whether this is the client's own brand
- **Summed values** for sentiment, SOV, presence, and position — these are raw sums that get divided by the count for averaging
- **Prompt count** — how many prompts contributed
- **Social mention count** — brand mentions from Reddit/Quora for this topic
- **Social sentiment score** — sentiment from social sources
- **Social authority score** — how authoritative the social sources mentioning this brand are

**What it tells you:** Topic Metrics answer cluster-level questions: "Overall, how well does our brand perform on CRM evaluation topics?". They are the rollup of all individual prompt scores within a topic.

> There is also a `TopicMetricUnbranded` variant that covers the same fields but only for prompts that do not explicitly mention any brand name.

---

### Generation Brand Metrics

A Generation Brand Metric is the raw per-response data for one brand in one AI response, before any aggregation.

**What we store:**
- **Which Generation (AI response)** this is for
- **Which brand**
- **Is present** — did this brand appear in the response?
- **Mention count** — how many times it was mentioned
- **Rank** — position at which it first appeared
- **Sentiment score** and **sentiment bucket** — `positive`, `negative`, or `neutral`
- **Positive signals** — the specific phrases from the response that indicate positive sentiment
- **Negative signals** — the specific phrases indicating negative sentiment
- **Framing summary** — a short description of how the brand was framed

**What it tells you:** These are the granular evidence behind any prompt-level or topic-level score. If a user asks "why is our sentiment score negative?", you look at Generation Brand Metrics to find the specific phrases that drove it.

---

### Brand Signal Metrics

A Brand Signal Metric is a recurring theme — a specific positive or negative statement that AI models make about a brand, found across multiple responses in a run.

**What we store:** Which run and domain, which brand, the direction (`positive` or `negative`), the signal text (the recurring phrase or theme), and how many times it appeared.

**What it tells you:** These are the "what does the AI say about us?" signal. The platform surfaces the top two positive and top two negative signals per brand per domain. If a user asks "what are AI models saying about us?", Brand Signals are the answer.

---

### Demand Universe Runs

A Demand Universe Run is a completed computation that scores every prompt in the universe by how much market demand it represents and how well each brand is performing on it.

**What we store:** Which domain, the run identifier, a volume threshold (minimum demand to include), segment-level volume totals, and total untapped volume.

---

### Demand Universe Prompt Labels

For each prompt in a Demand Universe Run, a label is computed for each brand.

**What we store:** The demand score (0–100) for this brand on this prompt, whether the focal brand is cited, position rank, SOV, prompt volume, and visibility score.

**What it tells you:** These scores drive the prioritisation of opportunities. A high demand score with low visibility = the most important opportunity.

---

### Untapped Topics

An Untapped Topic is a subject area with real market demand where the client's brand is largely absent from AI responses.

**What we store:**
- **Label** — the topic name
- **Domain area** — the product or business area it belongs to
- **Estimated volume** — the demand estimate for this topic
- **Signal sources** — where the evidence of demand came from (citations, GSC, social, etc.)
- **Rationale** — why the system identified this as an untapped opportunity
- **Status** — `suggested` (new) or `archived` (dismissed)

**What it tells you:** Untapped Topics are the platform's answer to "where should we invest?". They are areas where the market is searching, competitors are getting cited, but the client is not.

---

### Fanout Queries

A Fanout Query is a follow-up or sub-question that an AI model generates alongside its main response. Some AI systems (like Perplexity) issue multiple search queries as part of answering one prompt.

**What we store:** Which Generation it came from, the main query text, a list of sub-queries, and the sources the AI fetched.

**What it tells you:** Fanout Queries reveal how AI models research a topic. If the AI consistently searches for competitor information when answering a client's prompt, that shows up here as a signal.

---

## 8. Opportunities

### Checkpoint Slots and Checkpoint States

The checkpoint system watches a prompt's key metrics over time and fires an alert when something significant changes.

A **Checkpoint Slot** is a snapshot of one metric value (e.g., SOV, sentiment, presence) for a prompt at a specific run.

A **Checkpoint State** monitors those snapshots over time. When it detects a significant change, it fires a trigger.

**Triggers:**
- **Absence** — the client's brand has disappeared from AI responses for this prompt
- **Decline** — a metric has dropped significantly
- **Competitor emergence** — a new competitor has appeared and is gaining share

**What it tells you:** These are the alert records. If a user asks "why did we get an alert for this prompt?", the Checkpoint State holds the answer — which trigger fired and when.

---

### Opportunities

An Opportunity is a single recommended action generated from a metric gap.

**What we store:**
- **Which prompt** triggered this opportunity
- **Which checkpoint** metric identified the gap
- **Gap title** — a short description of what the problem is
- **Priority** — `Quick Win` (easy, high impact), `Big Bet` (harder, high strategic value), or `Filler` (low effort, low impact)
- **Action type** — `Create` (create new content), `Optimize` (improve existing content), `Community` (engage in online communities), or `Outreach` (PR and link-building)
- **Action items** — a list of concrete steps to take
- **Target venue** — where the action should happen (e.g., "brand website", "Reddit")
- **Rationale** — why this opportunity exists
- **Goal** and **Objective** — what success looks like

**What it tells you:** Opportunities are the actionable output of the platform. They answer "what should we do about this gap?". Priority and action type help the client decide where to start.

---

### Opportunity Clusters

An Opportunity Cluster groups related individual opportunities into a unified campaign theme.

**What we store:** The cluster name, domain, a unified goal and rationale, the impact score and level (`High`, `Medium`, `Low`), execution paths (the tactical playbook), and status (`to_do`, `in_progress`, `done`).

**What it tells you:** Where individual opportunities are granular, clusters give the strategic view. "We need to create 5 pieces of content about enterprise CRM pricing" might be one cluster made up of 5 individual opportunities across different prompts.

---

### L2 Opportunity Sessions (Guided Wizard)

An L2 Session is a conversational, guided experience where the platform helps the user build a personalised opportunity plan step by step.

**What we store:**
- The session state (current step, status)
- The user's stated goal
- Conversation history (all messages)
- Brand directives the user provided
- Data collected at each step
- Whether the final plan was confirmed

Each session includes **Prompt Selections** (which prompts were chosen for the plan) and **User Sources** (URLs, documents, or notes the user provided as context).

**What it tells you:** If a user has gone through the guided planning experience, all the context from that conversation is stored here — including their goals, the AI-generated plan, and the specific prompts selected.

---

## 9. Social Intelligence

The platform tracks brand mentions on Reddit and Quora. The data hierarchy is the same for both platforms.

### Reddit

**Subreddits** — communities on Reddit that are relevant to the client's domain. We track subscriber count, engagement level, whether AI models cite threads from it, and an authority score.

**Threads** — individual Reddit posts. We store the title, content, score, upvote ratio, comment count, when it was posted, and which AI models have cited it.

**Comments** — individual comments on threads. We store the text, score, depth (top-level or reply), and sentiment.

**Mentions** — a specific brand mention detected within a thread or comment. We store exactly which text matched, at which character position, which brand was mentioned, how confident the match was, and the sentiment of that mention.

**Classifications** — for each thread or comment chunk, we store which product vertical it relates to, which funnel stage it represents, and which persona the author appears to be.

**Subreddit Authority** — a composite score for each subreddit: subscriber score, engagement, content quality, topical relevance, and whether AI models actively cite threads from it.

**Insight Signals** — aggregated signals per domain: mention frequency trends, competitor gaps, sentiment trends, rising threads, opportunities to engage in underserved subreddits.

**Sync Runs** — records of each Reddit data sync (daily, weekly, or backfill).

---

### Quora

The Quora data follows the same structure as Reddit, adapted for Quora's format:

**Topics** — Quora topic pages relevant to the domain (e.g., "Customer Relationship Management").

**Spaces** — Quora Spaces (curated communities) relevant to the domain.

**Questions** — individual Quora questions. We store the question text, follower count, answer count, view count, and whether AI models have cited this question.

**Answer Chunks** — the text of answers (chunked for analysis), with author and upvote data.

**Mentions** — brand mentions within questions or answers, with sentiment and character-level position.

**Classifications** — topic, funnel, and persona labels.

**Question Authority** — a composite score: answer count, follower count, view count, top answer quality, whether AI cites it, topical relevance, and recency.

**Insight Signals** — same signal types as Reddit, adapted for Quora's structure.

---

## 10. Technical SEO

The Technical SEO module analyses whether the client's website is optimised for AI systems to crawl, read, and cite it.

### SEO Scans

A Scan is one complete technical audit of a domain. Scans run periodically and each produces a health score.

**What we store:**
- **Status** — `pending`, `running`, `completed`, `failed`, `cancelled`
- **Phase** — the current stage: `queued`, `resolving`, `rendering`, `analyzing`, `scoring`, `completed`
- **Progress** — 0–100 percentage
- **Health score** — the overall score from 0 to 100
- **Score delta** — how the score changed from the previous scan
- **Dimension scores** — separate scores for: bot access (can AI crawlers reach the pages?), rendering (does JavaScript hide content?), readability (is the content clear and structured?), schema markup, mobile friendliness, page speed, redirects, and content freshness
- **Issue counts** — P0 (critical), P1 (important), P2 (minor)
- **Robots.txt state** — `ok`, `missing`, or `error`
- **Sitemap state** — `ok`, `missing`, or `error`
- **Pages scanned** — how many pages were audited

**Sub-records per scan:**
- **Bot Access Results** — for each page template and each bot (Googlebot, GPTBot, PerplexityBot, etc.), whether access is allowed, blocked, or unknown
- **Page Check Results** — a full technical audit per page: indexability, JavaScript dependency, readability grade, heading structure, structured data, page speed, mobile issues, and more
- **Schema Check Results** — whether the page's structured data (FAQ, HowTo, Product, etc.) is valid and complete
- **Sitemap URLs** — all URLs found in the sitemap, with crawl selection data
- **Findings** — specific issues: what the problem is, how severe it is, which pages are affected, and how to fix it

**What it tells you:** Technical SEO answers "can AI systems actually read our content?". A high bot access score means AI crawlers can reach the pages. A high rendering score means JavaScript isn't hiding content. A high readability score means the content is structured in a way AI systems can extract and cite.

### Page Templates

A Page Template is a representative URL for a category of page (e.g., the homepage, a product page, a blog post). Scans use page templates to efficiently cover the whole site without scanning every single URL.

### SEO Scan Credit Transactions

Credits are consumed when scans run. This table tracks every credit grant, spend, refund, and adjustment for the organisation.

---

## 11. Search Data (Google Search Console)

### GSC Properties

A GSC Property is a website that the client has connected to the platform via their Google account (OAuth). It gives us access to their actual Google Search data.

**What we store:** The site URL, whether it's verified, OAuth tokens (encrypted), and the date range of the last data fetch.

### GSC Uploads

A GSC Upload is a CSV file the client uploaded manually, for cases where OAuth isn't available or they want to import historical data.

**What we store:** The date range, processing status, whether to replace or append existing data, the file paths, and row counts.

### GSC Queries

A GSC Query is one row of search performance data — one keyword — from either a connected GSC Property or a CSV upload.

**What we store:** The keyword text, clicks, impressions, CTR, average position, the date range it covers, and when it was fetched.

### GSC Pages

A GSC Page is the same data but at the page level instead of the keyword level — how a specific URL performed in Google Search.

**What it tells you:** GSC data shows what people are searching for in traditional Google search and how the client's pages rank. This data feeds the Keyword Library and informs which prompts we generate for AI analysis.

---

## 12. Crawl

The Crawl module manages the discovery and storage of the client's own web pages.

### Crawled URLs

A Crawled URL is a page discovered on the client's website.

**What we store:** The canonical URL, HTTP status code, crawl depth (how many clicks from the homepage), how it was discovered (`sitemap`, `discovery`, `gsc`, `curated`), when it was last crawled, and whether it's still considered active.

### Page Snapshots

A Page Snapshot is a point-in-time capture of a page — both the raw HTML and the JavaScript-rendered HTML, stored in S3.

**What we store:** The URL, which version of the rendering engine was used, S3 keys for the raw and rendered HTML, HTTP status, redirect chain, time to first byte, when it was fetched, and a content hash for change detection.

**What it tells you:** Snapshots let the platform track whether page content has changed. A content hash change means the page was updated, which may affect whether it continues to be cited by AI models.

### Domain Crawl Metrics

A single summary record per domain covering the overall crawl health: robots.txt state, sitemap state, URL counts, total pages discovered, and when the last crawl ran.

---

## 13. Sharing

### Dashboard Share Links

A Share Link allows someone to view the client's dashboard without logging in. It is time-limited and can be revoked.

**What we store:** A UUID identifier, which domain the link gives access to, a secure token hash (the actual token is never stored — only its hash), who created the link, the expiry time, and if/when it was revoked.

---

## 14. Feature Flags

### Feature Flags

A Feature Flag controls whether a feature is available. It can be turned on globally, on for a percentage of organisations (gradual rollout), or on for specific organisations via an override.

**What we store:** The flag key (identifier), a description, the flag type (`boolean` or `multivariate`), whether it's on globally, the value when on, and the rollout percentage.

### Feature Flag Overrides

An Override enables or customises a feature flag for a specific organisation — used for early access programs or organisation-specific settings.

---

## How All the Data Connects

Understanding how data flows helps answer multi-step questions like "why did our visibility drop this week?"

```
Organisation
    └── Domain (the website being analysed)
          ├── Competitors (who we track, including the client = focal brand)
          │     ├── Brand Aliases (alternate names for citation matching)
          │     └── Competitor Domain Aliases (alternate URLs for attribution)
          │
          ├── Product Verticals (lines of business)
          │
          ├── Intent Clusters (topic groups)
          │     └── Synthetic Prompts (the individual questions)
          │           └── Keyword Library (grounding in real search demand)
          │
          ├── Workflow → triggers pipeline runs
          │
          ├── Insight Run (one analysis cycle for a cluster + model)
          │     └── Generation (one AI response per prompt × model × repetition)
          │           ├── Generation Brand Metric (raw brand data per response)
          │           ├── Prompt Citation (URLs cited in the response)
          │           └── Fanout Query (sub-queries the AI issued)
          │
          ├── Prompt Metric (aggregated score per brand × prompt × run)
          ├── Topic Metric (aggregated score per brand × cluster × run)
          ├── Brand Signal Metric (recurring sentiment themes)
          │
          ├── Demand Universe Run
          │     ├── Demand Universe Prompt Labels (demand + visibility per prompt)
          │     └── Untapped Topics (whitespace opportunities)
          │
          ├── Checkpoint States → Opportunities → Opportunity Clusters
          │
          ├── Reddit and Quora data (social intelligence)
          │
          ├── Technical SEO Scans
          │
          └── GSC Properties / Uploads → GSC Queries → Keyword Library
```

---

## Quick Reference: What Data Answers Which Question

| Question | Where to look |
|---|---|
| Who are the tracked competitors? | `Competitor` records for this domain |
| What is the client's own brand data? | `Competitor` where `is_focal=True` |
| What prompts are we tracking? | `SyntheticPrompt` records for this domain |
| How many AI responses do we have? | `Generation` records for this domain |
| Was our brand mentioned in response to a specific question? | `GenerationBrandMetric.is_present` for that prompt |
| What is our visibility score on a topic? | `PromptMetric.visibility_score` per prompt, or `TopicMetric` for the cluster |
| What does AI say about us positively/negatively? | `BrandSignalMetric` for this domain |
| Which URLs is AI citing for our category? | `PromptCitation` for this domain |
| Are our own pages being cited, or community/editorial sites? | `PromptCitation.attribution_type` breakdown |
| What are our untapped opportunities? | `UntappedTopic` and `DemandUniversePromptLabel` |
| What actions should we take? | `Opportunity` and `OpportunityCluster` |
| What are people saying about us on Reddit? | `RedditMention` and `RedditInsightSignal` |
| When did we last run an analysis? | `Workflow` and `InsightRun` records |
| How healthy is our website for AI crawlers? | `TechnicalSeoScan.health_score` and `Finding` records |
| What keywords are we ranking for in Google? | `GSCQuery` records |
