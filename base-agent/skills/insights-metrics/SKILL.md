---
name: insights-metrics
description: Authoritative computation spec for every visibility metric — presence/visibility, share of voice, position, sentiment (buckets + scoring methodology), citation attribution/weighting/damping/aggregation, and consistency — with exact formulas, thresholds, bucket boundaries, system guarantees, invariants, and known limitations. Load this for ANY metric interpretation, threshold check, bucket boundary, citation-attribution rule, or "why did metric X change" analysis. This is the source of truth and overrides any summary.
visibility: internal
---

# Overview

# Insights Engine Metrics Computation

This document highlights the computational formulas for the insights engine - calculating metrics value for brands' AI visibility, in terms of their presence, position, share of voice, citations and sentiments.

# Purpose and Problem Statement

Large Language Model (LLM) answers behave as a new distribution channel for user discovery. Unlike classical web search where ranking is visible and link-based, LLM responses contain implicit rankings (ordering of entities in text), implicit prominence (early vs late mention), implicit sentiment toward brands, and sometimes citations (or other authority signals).

The goal of this Insights Engine is to compute robust, interpretable, and comparable metrics that quantify a brand's AI Visibility relative to competitors across:

* a prompt library representing real user intents,
* multiple LLM platforms/models,
* repeated generations per prompt (to reduce sampling noise),
* time windows for trending and smoothing.

We define a core **Presence score** along with supporting diagnostics: Presence Rank, Share of Voice (SoV), Position metrics, Sentiment metrics, and Citation Share. We also specify an optional cross-channel composite visibility that extends beyond LLM answers into broader sources (e.g., search, social, news) using prominence and recency decay.

# Objective

Defining the theoretical grounding and computational logic for a unified system measuring

1. Presence
2. Share of Voice
3. Position
4. Sentiment
5. Citation Share
6. Cross-Model Visibility

## Summary Table

| Metric | Core Formula |
| ----- | ----- |
| Visibility | Weighted sum of MentionScore |
| Presence Rank | Dense Rank by Visibility |
| Share of Voice | Visibility Share of brand across its Competitors |
| Position | Weighted average of PositionScore |
| Position Rank | Rank by AvgPos |
| Sentiment % | Weighted positive / total |
| Citation Share | Citation_b / Total citations |
| Citation Rank | Rank by CitationShare |
| Visibility Across Models | Model-weighted aggregation |

# 1. Core Data Model & Notation

## Assumptions

We have defined the following assumptions for our computation.

1. Intent Clusters or Key Topic **H** | H = { h1 , …, h|H| }
2. Prompt library **P** | P = { p1 , …, p|P| }
3. LLM models **M**  | M = { m1 , …, m|M| }
4. A defined brand set **B**  | B = { b1 , …, b|P| }  (brand entities, includes focal brand & competitors)
5. Responses are stored with extracted mentions, token indices, sentiment, and citations
6. All metrics computed over a fixed time window **T**

**Why do we need K generations?**
LLM outputs are stochastic (temperature, sampling, retrieval variance). Running K ≥ 1 generations for each (p, m) allows estimating expected metrics and reducing variance.

## Sets, Indices and Time Window

Let

* **h∈H** = Topic						(1)
* **p∈P** = Prompt 					(2)
* **m∈M** = Model						(3)
* **b∈B** = Brand						(4)
* **G** = { 1, …., K}  Generation Index			(5)
* **T** = [tmin , tmax ] (analysis time window)		(6)

## Weights [TBD, assign equal]

We introduce two weight families.

### Prompt Weight, wp

		wp ≥ 0 ∀p ∈ P.

wp captures the real-world importance of prompt p (e.g., estimated user prompt volume, business priority, or market size). If prompt volumes are unknown, set wp = 1 initially.

### Model Weight, αm

αm ≥ 0 ∀m ∈ M, ​Σ p∈P​ αm = 1

αm captures exposure probability or strategic importance of model m. Two common constructions:

* **Market-share weighting**: αm proportional to estimated global usage share.
* **Client-traffic weighting**: αm proportional to observed AI-referral traffic from model m.

## Per Generation Extracted Variables.

For each Topic prompt, p∈P, model m∈M, generation g∈G with response text Rp,m,g generated within the time window T, we can compute per brand b∈B:

### Binary Presence Indicator

Presb,p,h,m∈{0,1}

Where Presb,p,h,m,g = 1 iff brand b is mentioned at least once in Rh,p,m,g after entity resolution

### Mention Index

Let Th,p,m,g be the total token count of the response: Th,p,m,g ∈ Z>0

We get, 	indexb,h,p,m,g ∈ { 1, …, Th,p,m,g} if Presb,p,h,m = 1,

As the index of the first token where the canonical mention of the brand b occurs. If absent, position is 0.

### Entity Position (Order Among Brands)

Define posh,b,p,m,g ∈ {1, 2, . . . } when present. A robust definition is:
		posb,h,p,m,g := 1 + #{b′ ∈ B : Presb,h,p,m,g = 1 ∧ indexb,h,p,m,g < indexb,h,p,m,g}.

Thus position is determined by earliest appearance. This is stable across formats (lists, paragraphs) and aligns with the intuitive idea of prominence.

### Aspect-based Sentiment

Let Sb,h,p,m,g ∈ [−1, 1] be sentiment toward brand b in context of prompt p and response R_p,m,g. We emphasize aspect-based sentiment: sentiment toward the brand, not global tone.

Sentiment buckets

- 0 to 0.3 (negative)
- 0.3 to 0.6 (neutral)
- 0.6 to 1 (positive)

* indexb,p,m = first token index
* Tp,m = total tokens
* Freqb,p,m = mention count
* Sb,p,m ∈[-1,1] = sentiment score
* Cb,p,m = number of citations

### Citations

Let Cb,h,p,m,g ∈ Z≥0 be the number of citations in Rh,p,m,g attributed to brand b.
Attribution requires a rule, e.g.:

# 2. Presence & Visibility

| Term | Definition |
| :---- | :---- |
| Presence | Whether a brand/entity is mentioned at all within an AI response (binary or percentage-based). |
| Mentions | Count (Mention Count) or percentage (Mention%) indicating how often an entity appears in AI responses. |

### 2.1 Presence Score

We define Presence score as.
		PSb,h,p,m​=Presb,h,p,m

### For Prompt-Level Aggregation across Generation

As we run K generations per (h,p,m), we first aggregate per prompt, topic and model to reduce stochastic noise.

### 2.2 Prompt-Level Visibility

We define the expected presence score:
		PS'b,h,p,m = ​1/K Σ g=1 to K​ PSb,h,p,m

### 2.3 Topic-Level Visibility

We defined Topic-level visibility contribution for a brand b under topic h and model m:
		Visb,h,m​ := 1/ P Σ p∈P wp · PS'b,h,p,m
		Visb,m​ := 1/ h Σ h∈H wp · PS'b,h,m

### 2.4 Model-Level Visibility

We defined Topic-level visibility contribution for a brand b under topic h and model m:
Visb​ := 1/m Σ h∈H Visb,,m

**2.6 Visibility Score (Cross Model Visibility)**
Visb ​:= 100 · Σ m∈M Visb,h,m

### 2.7 Temporal Smoothening

### Visbfinal  ​:= Σ k=1 to K Visb

### 2.8 Presence Rank

Compute ranks based on Visbfinal descending. Define dense rank:

Rankpresenceb,t := 1 + #{k ∈ B : Visfinal k,t > Visfinalb,t }

Dense ranking ensures ties share rank without gaps.

# 3. Share of Voice (SoV) Score

| Term | Definition |
| :---- | :---- |
| Share of Voice (SoV) | Relative distribution of mentions or presence across competitors within AI responses. |

### 3.1 SoV Definition

SoV is brands' share of total visibility mass within the competitor set. We define it as:

For
TotVisfinal  ​:= Σ k∈B Viskfinal

Share of Voice is:
		SoVb = Visbfinal /  TotVisfinal + ε

### 3.2 SoV Rank (Dense)

RankSoVb := 1 + #{k ∈ B : SoVk > SoVb}.

# 4. Position & Coverage

| Term | Definition |
| :---- | :---- |
| Position | The relative ordering or prominence of a brand/entity within an AI-generated response. |
| Coverage  | The presence of the brand across total prompt generations.  Eg. if the brand is present in 5 out of 10 prompts then, the coverage is 5/10.  |
| Citations Coverage | presence/coverage metric: Responses citing focal brand / responses having attributable citations |

### 4.1 Conditioned Average of Position

pos'b,h,p,m := Σ g=1 to K posb,h,p,m · Presb,h,p,m / Σ g=1 to K Presb,h,p,m + ε

### 4.2 Per Prompt - Position

		Posb,h,m := Σ k=1 to G wp· posb,h,p,m · 1{brand present for (b,p,h,m)} / Σ g=1 to K wp· 1{brand present for (b,p,h,m)}  + ε

### 4.3 Per Topic - Position

Posb,m := Σ g=1 to K Posb,h,m

### 4.4 Overall Position (Cross Model Average Position)

		Posb := Σ g=1 to K αm· Posb,m

### 4.5 Position Rank

Rankposb := 1 + #{k ∈ B : Posk < Posb}

Lower Rank is better

### 4.6 Coverage

Covb = Prompts (Pres=1) / Total Prompts

# 5. Sentiment

# Sentiment Computation.

**Sentiment (0-10 Score)** of mentions classified into sentiment buckets (Positive, Neutral, Negative). Optionally provide a single aggregated sentiment index.

**Buckets**

| No | Label | TONE | Snippet Copy |
| :---- | :---- | :---- | :---- |
| **0, 1, 2** | Negative | The AI consistently frames your brand with problems, caveats, or unfavourable comparisons. | "Your brand is being described negatively on this topic." |
| **3, 4** | Mixed | Negatives outweigh positives.  The AI mentions your brand with qualifications and reservations. | "Your brand gets mixed signals — more caution than confidence on this topic." |
| **5, 6** | Neutral | The AI mentions your brand as a factual option with no clear positive or negative lean. | "Your brand is presented as a balanced option — neither endorsed nor questioned." |
| **7, 8** | Positive | The AI favours your brand — strengths and advantages come through consistently. | "Your brand is being presented positively — AI models highlight your strengths on this topic." |
| **9, 10** | Strong | The AI actively recommends your brand — you are the clear, preferred answer on this topic. | "Your brand is the AI's preferred choice here — sentiment is as strong as it gets." |

**Bucket Collection**
Positive -> Positive, Strong
Neutral -> Neutral
Negative -> Mixed, Negative

## Global Definition

Let

* p∈P = prompt
* m∈M = Model
* b∈B = Brand
* wp = prompt weight (higher for higher prompt volume)
* W = ​Σ p∈P​​ wp​
* αm = model weight
* k = Number of Generations per prompt

For each response

* Presenceb,p,m∈{0,1} – its either 1, 0 binary.
* Posb,p,m = first token index
* Tp,m = total tokens
* Freqb,p,m = mention count
* Sb,p,m ∈[-1,1] = sentiment score
* Cb,p,m = number of citations

# Sentiment %

* Sb,p,m ∈[-1,1] = sentiment score
  Where
  -1 -> strongly negative towards brand
  0 -> neutral and factual
  1 -> strongly positive

### Methodology for Sentiment Scoring

1. **Extraction of Mention Context**
   We extract a context window around the mention
- Sentence containing the mention
- +- 1 sentence window or 50-token sliding window

	Lets call this,   Contextb , p , m

2. **Scoring Method**

	I am suggesting a two-fold scoring method - where primary is a Fine-tuned transformer classifier, and secondary fallback is LLM scoring for ambiguous cases.

1. Fine Tuned Transformer Classifer
   This method is cheap, fast and deterministic but less nuanced than LLM and needs domain fine-tuning.

   RoBERTa / DeBERTa fine-tuned on aspect-based sentiment data

Converting Probablity distribution of P(pos),P(neu),P(neg) into Scalar
S = P(pos) - P(neg), range [-1,1]

2. LLM Based Classification
   This method has best contextual understanding, handles subtle tone and detects comparison based sentiment.

   Example prompt -
   "Evaluate sentiment toward BRAND in the following text.
   Return a number between -1 and 1.
   Only evaluate sentiment toward BRAND, not overall tone. Return a scalar value."

## Aggregating Sentiment Across Prompts

Sentimentb = Σ p∈P wp x sb,p,m / Σ p∈P wp

## Sentiment Percent

Positive Sentiment
Positive%b = Σ p∈P wp * 1 (sb,p,m >0)/ Σ p∈P wp

Negative Sentiment
Negative%b = Σ p∈P wp * 1 (sb,p,m <0)/ Σ p∈P wp

Neutral
Neutral% = 1−Positive%−Negative%

## Sentiment Opportunities

* We create a Phrase-Mention table, where we store the categories of the sentiments derived from the responses, and the number of mentions of such categories.
* We then list out the top-5 highest mentioned Sentiments and the top-5 lowest performing Sentiments as (Growth & Improvements)

# 6. Citation

**Citation Insights System**

**1. Overview**

The Insights Engine measures a brand's AI Visibility: how prominently, how often, and with what authority a brand appears in LLM-generated responses across a tracked prompt library and competitor set.

**Three Signal Classes**

The system tracks three distinct signals that must not be conflated:

| Signal | What It Measures | Driving Field |
| :---- | :---- | :---- |
| Visibility | Whether a brand is mentioned and how prominently — computed from binary presence, mention rank, and mention frequency across prompts, models, and generation runs. | brand mentions in response text |
| Citations | Authoritative references — URLs or domains the model surfaces as source material. Measures the ecosystem of source trust around a brand, not its mention rate. | brand_id (domain ownership) |
| Mentions | Raw text occurrences of a brand name or alias within a response. Drives visibility computation, separate from citation attribution. | supported_brand_id (content proximity) |

The critical distinction: a response can mention a brand without citing its domain. A response can cite a domain belonging to a competitor with no mention of the focal brand at all. These are separate signals and must be aggregated and reported separately.

**2. Core Data Model**

**Brand Set**

Every competitive metric — share, rank, brands_mentioned counts — is computed within a brand set B:

B = { focal_brand } ∪ { active competitors }

B is scoped per domain_id. The focal brand is the single brand associated with the client's registered domain. Competitors are those with status = active in the competitors table.

**Primary Fields**

| Field | Definition | Example |
| :---- | :---- | :---- |
| brand_id | UUID of the brand that owns the cited domain. Set when normalized_domain_key matches a registered domain for any brand in B. Source of source_mass. | stripe.com → Stripe's brand UUID |
| supported_brand_id | UUID of a brand mentioned in the page snippet of a citation where brand_id IS NULL. Source of support_mass. Requires LLM enrichment above confidence thresholds. | A Forbes article about Stripe → Stripe's UUID |
| attribution_type | 5-value enum assigned based solely on domain ownership at pipeline time. Never derived from response text. | brand_owned, competitor_owned, platform, earned_media, unresolved |
| normalized_domain | The registrable eTLD+1 root domain of a citation URL. All attribution logic and domain-level aggregation uses this form. | docs.stripe.com → stripe.com |

**Deduplication**

Multiple references to the same URL within one response count as one citation. The prompt_citations table enforces a UNIQUE(response_id, page_url) constraint at insert time. Two distinct pages on the same domain within one response are two separate citations — deduplication is URL-level, not domain-level.

**3. Attribution System**

**Full Attribution Logic**

Attribution type is assigned in citation_pipeline.py after domain normalization. The order of evaluation is fixed and deterministic:

```
if normalized_domain_key in focal_domains:
    attribution_type = "brand_owned"
elif normalized_domain_key in competitor_domains:
    attribution_type = "competitor_owned"
elif is_platform_domain(normalized_domain_key):
    attribution_type = "platform"
elif normalized_domain_key in REVIEW_SITE_DOMAINS:
    attribution_type = "earned_media"
elif not normalized_domain_key:
    attribution_type = "unresolved"
else:
    attribution_type = "earned_media"
```

**Platform Domain Classification**

A domain is classified as platform if it matches one of two conditions:

* Exact or subdomain match against PLATFORM_DOMAINS: linkedin.com, reddit.com, ycombinator.com, stackoverflow.com, dev.to, lobste.rs, medium.com, substack.com, twitter.com, x.com, youtube.com, youtu.be, facebook.com, instagram.com, tiktok.com, pinterest.com, discord.com, quora.com, threads.net, snapchat.com, t.me, whatsapp.com, github.com, gitlab.com, bitbucket.org, hashnode.com, producthunt.com, hackernoon.com, devhunt.org.

* Hosting provider suffix match against HOSTING_DOMAINS: pages.dev, github.io, vercel.app, netlify.app, web.app, firebaseapp.com, fly.dev, railway.app, workers.dev, onrender.com. The suffix-only match means foo.pages.dev is platform but pages.dev itself is not.

Review sites classified as earned_media by explicit rule: trustpilot.com, g2.com, capterra.com, softwareadvice.com, getapp.com.

**Why the Fallback Is earned_media**

Any domain that passes normalization — is not owned by any brand in B, not a platform, and not a review site — is third-party content. Third-party coverage is the definition of earned media in citation analytics. The fallback is not a catch-all for noise: SKIP_DOMAINS and NOISE_DOMAINS are filtered before this classification runs.

**When unresolved Is Used**

unresolved is assigned only when normalize_domain returns None or an empty string — meaning the URL failed to produce a valid eTLD+1. This occurs for malformed URLs, bare IP addresses, localhost, or bare suffixes. A high unresolved count indicates a domain normalization failure or data quality issue. Unresolved citations are bucketed into earned_media in source distribution, which inflates earned media share inaccurately.

**Attribution Is Domain-Based, Not Text-Based**

attribution_type is determined entirely by the domain registry at pipeline time. It does not depend on whether the response text mentions any brand. A citation to competitor.com is competitor_owned regardless of what the response discusses. Text-based brand association is captured separately via supported_brand_id in meta.support_attribution, populated during LLM enrichment. These answer different questions and must not be conflated in aggregations.

**4. Domain Normalization**

**What normalize_domain Does**

normalize_domain(url) extracts the eTLD+1 registrable root domain from any input URL, returning a lowercase string or None on failure. Implemented via tldextract.TLDExtract with no runtime suffix list fetches.

**eTLD+1 Explained**

An eTLD (effective top-level domain) is a public suffix like .com, .co.uk, or .github.io. The eTLD+1 is the registrable domain one level above it — the part a registrant actually controls. tldextract uses the Public Suffix List to determine eTLD boundaries, which is why pages.dev is treated as a suffix and foo.pages.dev normalizes to itself rather than pages.dev.

| Input URL | Normalized Output | Notes |
| :---- | :---- | :---- |
| https://docs.stripe.com/api | stripe.com | Subdomain stripped |
| https://www.wise.com/help | wise.com | www stripped |
| developer.paypal.com | paypal.com | Subdomain stripped |
| foo.pages.dev | foo.pages.dev | pages.dev is a PSL suffix; foo is the registrant |
| localhost | None | Not a valid eTLD+1 |
| 192.168.1.1 | None | IP addresses return None |
| schema.org | None | Bare suffix — filtered by NOISE_DOMAINS |

**5. Citation Weighting**

**Base Weight**

Each citation receives a base_weight based on the domain type of its normalized domain:

| domain_type | Condition | base_weight |
| :---- | :---- | :---- |
| official | Domain is registered to any brand in B | 1.2 |
| unknown | All other domains | 0.8 |
| aggregator | reddit.com, stackoverflow.com, news.ycombinator.com | 0.5 |
| social | youtube.com, youtu.be, twitter.com, x.com | 0.4 |
| editorial | Reserved — not currently active | 1.0 |

Source: citation_policy.py:DOMAIN_WEIGHTS and citation_policy.py:classify_domain.

**Damping Factor**

Within a single response, if the same normalized domain appears n times, each citation's contribution is reduced:

damping_factor = 1 / sqrt(n)

Where n = number of occurrences of the same normalized_domain_key within a single response_id, computed over all citations before weighting.

| n (citations to same domain) | damping_factor | Mass reduction |
| :---- | :---- | :---- |
| 1 | 1.000 | None |
| 2 | 0.707 | 29% |
| 4 | 0.500 | 50% |
| 9 | 0.333 | 67% |

**Why Damping Exists**

Without damping, a model citing stripe.com 60 times in a run would assign it 60 units of mass regardless of domain diversity. Damping is sublinear: mass grows proportional to sqrt(n), not n. A domain cited 9 times per response is still 3× stronger than a singleton — frequency advantage is attenuated, not eliminated. The ordering of domains by share is preserved after damping; only magnitudes change.

**Final Citation Mass Weight**

citation_mass_weight = base_weight × (1 / sqrt(n))

This value is computed per citation row in citation_pipeline.py and stored in meta.citation_mass_weight. Citations in SKIP_DOMAINS (youtube.com, youtu.be, facebook.com, linkedin.com, twitter.com, x.com, bit.ly, t.co, instagram.com) and NOISE_DOMAINS are excluded entirely: their citation_mass_weight is 0 and they do not appear in aggregation. Citations where included_in_metrics = False also contribute 0.

**6. Aggregation Logic**

**Source Mass**

The total weighted citation authority accumulated by a brand from citations directly attributed to it:

```
source_mass(brand_id) = Σ citation_mass_weight
                         for all rows where brand_id = target
                         and created_at ∈ [window_start, window_end]
```

Only rows with brand_id IS NOT NULL contribute. Each row's mass weight is already damped at write time. Computed in scoring/source_mass.py:compute_all_source_mass.

**Support Mass**

Fractional citation authority contributed by third-party pages that mention a brand without being owned by it. Requires LLM enrichment:

```
support_mass(brand_id) = Σ response_capped_contribution(response_id, brand_id)

response_capped_contribution(r, b) = min(
    Σ contribution(row) for rows with (response_id=r, supported_brand_id=b),
    MAX_SUPPORT_PER_RESPONSE_PER_BRAND   -- currently None (no cap)
)

contribution(row) = citation_mass_weight × confidence
```

Eligibility filters for a row to contribute support mass:

* brand_id IS NULL (not a directly-attributed citation)
* meta.support_attribution.supported_brand_id IS NOT NULL
* confidence ≥ 0.40 (SUPPORT_MIN_CONFIDENCE)
* top_margin ≥ 0.15 (SUPPORT_MIN_TOP_MARGIN — winning candidate must beat second by at least 15 pp)
* citation_mass_weight > 0

**Final Score**

```
final_score(brand_id) = α × source_mass(brand_id) + β × support_mass(brand_id)
α = 1.0
β = 0.35
```

Support mass is discounted to 0.35 because it is inferred via LLM enrichment rather than resolved directly from domain ownership. Direct attribution (source_mass) is the primary signal.

**Citation Share**

Normalized share across all brands in B:

```
normalized_share(brand_id) = final_score(brand_id)
                             ─────────────────────────────────────
                             Σ final_score(k) for all k in B + ε
```

ε = 1e-9  (prevents division by zero)

This is the normalized_share column in brand_citation_scores. It represents a brand's fraction of total citation authority mass across all brands in B within the time window. The /share endpoint uses a simpler per-run variant: sum of brand's citation_mass_weight divided by sum of all rows with brand_id IS NOT NULL in the run.

**Domain-Level Citation Share**

```
domain_citation_share(domain) = Σ citation_mass_weight for domain
                                ──────────────────────────────────────
                                Σ citation_mass_weight for all domains in run
```

Used in /domains and /performance?view=domain endpoints.

**7. Source Distribution**

Source distribution collapses attribution_type into three reporting buckets. The mapping is computed in insights_citations.py:_attribution_type_to_bucket and is the single source of truth for source distribution analytics:

| attribution_type | source_distribution bucket |
| :---- | :---- |
| brand_owned | owned |
| platform | community |
| competitor_owned | earned_media |
| earned_media | earned_media |
| unresolved | earned_media |

Note: competitor_owned citations fall into earned_media, not a separate competitor bucket. unresolved citations also land in earned_media, which inflates that bucket inaccurately when normalization failures are high.

Source distribution is computed over citation counts (not mass) within a run_id:

```
owned_pct     = count(attribution_type = "brand_owned") / total_citations × 100
community_pct = count(attribution_type = "platform") / total_citations × 100
earned_pct    = count(others) / total_citations × 100
```

Domain-based heuristics from classify_source in source_classifier.py are deprecated for source distribution analytics and used only for per-row category labels in the domain performance table view.

**8. Domain vs Page Metrics**

**Domain-Level Metrics**

Endpoints: GET /insights/citations/domains and GET /insights/citations/performance?view=domain

| Field | Definition |
| :---- | :---- |
| citation_share | domain_citation_mass / total_citation_mass for run, as a percentage |
| citation_count | Count of distinct citation rows for this domain in the run |
| domain_mass | Raw Σ citation_mass_weight for this domain in the run |
| rank | Dense rank by domain_mass DESC, then citation_count DESC, then domain string ASC |
| attribution_type | Assigned in pipeline; determines source bucket |
| brands_mentioned | Count of brands in B with supported_brand_id on citations in this domain — filtered to B |
| brand_rank | Rank within B of the dominant brand (highest citation mass) owning citations in this domain |

**Page-Level Metrics**

Endpoint: GET /insights/citations/performance?view=pages

| Field | Definition |
| :---- | :---- |
| citation_share | page_citation_mass / total_citation_mass for run, as a percentage |
| citation_frequency | Count of distinct responses that cited this page URL |
| brands_mentioned | Count of brands b ∈ B with supported_brand_id = b on citations for this page_url — filtered to B |
| brand_rank | Rank within B of the dominant brand owning citations to this page URL |
| rank | Dense rank by citation_share DESC, then citation_frequency DESC, then page_url ASC |
| category | Content type classification: Educational, Instructional, Comparative, Reviews, Product |

brands_mentioned filtering (critical): supported_brand_id values are intersected with brand_set_B before counting. Only brands in B contribute to brands_mentioned. This prevents third-party brand mentions from inflating the count for untracked brands.

citation_frequency (page level) counts distinct responses. citation_count (domain level) counts distinct citation rows. They diverge when the same URL appears across multiple responses, which is normal for popular pages.

**9. System Guarantees**

* Deterministic attribution: Given the same normalized_domain_key and the same brand registry state, attribution_type is always the same value. No randomness, no runtime external calls. Brand registry changes take effect on the next pipeline run, not retroactively.

* No double counting: The UNIQUE(response_id, page_url) constraint enforces deduplication at insert time. Applications computing citation counts from prompt_citations do not need to deduplicate.

* Correct fallback behavior: unresolved is used only for genuine normalization failures (None or empty string). Valid domains that match no brand, platform, or review site default to earned_media. The system does not use unresolved as a catch-all.

* Share stability: normalized_share sums to 1.0 across all brands in B (modulo ε). Adding a new competitor to B reduces all existing shares proportionally. Removing one redistributes mass upward proportionally.

* Ranking invariance to attribution changes: Citation rank uses citation_mass_weight aggregated by brand_id. Attribution type does not enter the ranking computation. Reclassifying a domain changes source distribution percentages but does not change any brand's citation mass or rank.

# 10. Known Limitations

**Long-Tail Inflation**

Singleton domains (n=1) receive damping_factor = 1.0 — no reduction at all. In the validation dataset, 45 distinct singleton domains collectively held 39.8% of total citation mass, exceeding any individual mid-frequency domain. This inflates the denominator (total_mass) and deflates individual brand shares. The long tail is an artifact of aggregation, not a signal of broad authority. Diverse citation patterns (many distinct pages) are mathematically rewarded over concentrated ones (same domain repeatedly).

**Frequency Bias**

Sqrt damping reduces but does not eliminate frequency advantage. A domain cited 9 times per response retains a 3× mass advantage over a singleton (sqrt(9)/sqrt(1) = 3.0). A domain cited 25 times retains a 5× advantage. A brand consistently cited as the primary source across all prompts will dominate citation share even with damping. Additionally, cross-response presence is uncapped: a domain cited once per response across 50 responses accumulates full weight for each occurrence with no inter-response penalty.

**Platform Detection Gaps (not important)**

The PLATFORM_DOMAINS list is static. New platforms not on the list receive attribution_type = "earned_media" by the fallback rule. Community forums, new social platforms, and developer aggregators emerging after a deployment will inflate the earned media bucket until the list is updated and a new pipeline run executes.

**Other Structural Limitations**

* No upper bound on source_mass: a brand cited in every response of every prompt accumulates mass proportional to run size. Raw source_mass is not stable across runs of different sizes; use normalized_share for cross-window comparisons.

* Competitor domain collisions: if two registered competitors share the same normalized domain, the registry assigns the citation to both, inflating total citation mass and distorting share. Callers must ensure no unintended duplicate normalized domains in the brand registry.

* citation_mass_weight = 0 rows: unresolved and excluded citations are written to prompt_citations with zero mass. Raw citation counts from this table will appear higher than effective mass counts suggest.

**11. Key Invariants**

These rules must hold throughout all aggregation, reporting, and API logic:

| Strict Invariants — Must Not Be Violated |
| :---- |
| 1.  supported_brand_id ∈ B: Only brands in the active competitor set can be assigned as supported_brand_id. Third-party brand mentions outside B are not counted. |
| 2.  Citation share uses ONLY brand_id: normalized_share and the /share endpoint compute shares using source_mass, which derives only from rows where brand_id IS NOT NULL. supported_brand_id contributes to support_mass with coefficient β=0.35, not to the primary share numerator. |
| 3.  Attribution is domain-based: attribution_type is always determined from the normalized_domain_key and brand registry — never from response text content. |
| 4.  Fallback is earned_media: any valid URL that clears SKIP/NOISE filtering and matches no brand, platform, or review site is earned_media. The unresolved type is reserved exclusively for normalization failures. |
| 5.  Deduplication is URL-level per response: UNIQUE(response_id, page_url) prevents the same URL appearing twice in the same response. Domain-level deduplication is not enforced and not expected. |
| 6.  Damping is scoped per response: n in damping_factor = 1/sqrt(n) counts occurrences within a single response_id only. Cross-response repetition receives no damping. |

**Appendix: Notation Alignment**

This document uses implementation-level notation. The table below aligns with the Insights Engine Mathematical Specification:

| Implementation Field | Math Spec Notation | Description |
| :---- | :---- | :---- |
| brand_id (citation row) | C_{b,p,m,g} | Attribution via domain ownership |
| citation_mass_weight | Weighted C per citation row | base_weight × 1/sqrt(n) |
| source_mass(b) | Cit_{b,m} | Model-level citation mass |
| normalized_share(b) | CitShare_b | Share within B |
| supported_brand_id | C_{b,p,m,g} via content proximity | Support attribution |
| Vis_{b,m} | Model-level visibility | Σ w_p × mention_score |
| SoV_b | 100 × Vis_raw_b / TotVis_raw | Share of voice |

Note: support_mass is a production extension not present in the base mathematical specification. It allows citations not directly attributed to a brand (brand_id IS NULL) to contribute fractional mass when LLM enrichment resolves a high-confidence supported_brand_id.

# Citation Attribution — Exact Definitions

### 1. Citation
A citation is any URL that appears as a reference, source, or link in a piece of content, search result, or AI-generated response.

### 2. Attribution
Attribution is the act of assigning a citation to the entity that owns the domain on which that citation lives, not the entity that is mentioned or discussed within it.

### 3. Attributed Citation
A citation is attributed when the domain of the URL is verifiably owned by a known entity, and that entity has been recorded as the owner of that citation in the attribution registry.

### 4. Brand Attribution
A citation is attributed to a Brand when the domain of the URL is registered and owned by that brand. The brand must be the publisher of the page, not merely the subject of it.

### 5. Competitor Attribution
A citation is attributed to a Competitor when the domain is a clean brand-owned domain belonging to a brand other than the one being tracked. The citation belongs to that competitor, not the tracked brand.

### 6. Platform Attribution
A citation is attributed to a Platform when the domain is a known aggregator or hosting service such as Reddit, Medium, or Substack, and no outbound link to a brand-owned domain exists within that citation. The platform is the attributed entity.

### 7. Unresolved Citation
A citation is Unresolved when its domain cannot be matched to any known entity through domain lookup, WHOIS, or brand registry. WHOIS is a public internet lookup protocol that returns the registered ownership record of any domain, including the legal entity that owns it, their contact email, and registration date. An unresolved citation must be held in a pending state and verified via WHOIS before being entered into the attribution registry.

### 8. Earned Media Citation
A citation is classified as Earned Media when a third-party publisher — a domain owner who creates and owns original content such as articles, blogs, or reports — writes about the focal brand, mentions the brand in the URL slug, title, or content, but owns the domain themselves. The citation is attributed to that publisher as the domain owner. The focal brand receives a mention record against that citation, not an attribution record.

### Revised Definition: Earned Media Citation
An Earned Media Citation is a citation that appears on a domain owned by an independent, authoritative third party — such as a media publication, industry analyst, journalist, or subject matter expert — who has published a point of view, coverage, or analysis about the focal brand, its product, or its market. The domain owner is not a competitor, not a platform, and not affiliated with the focal brand. Their authority comes from their position in the industry as an independent voice — not from being in the same business.

### 9. Catch-All Attribution Rule
A Catch-All Citation is any citation that does not qualify as a Focal Brand Citation (Owned), Platform Citation (Community), or Earned Media Citation. It is attributed to the Catch-All as Source. Every possible attribute of the citation is captured at ingestion — including domain, URL structure, page title, author, publish date, topic category, industry vertical, content type, brand mentions, outbound links, and structured metadata — so that the citation can be reclassified into a more specific type at any future point without needing to re-crawl. If its state is still unresolved, it needs crawling.

### 10. Primary Attribution Rule
Every citation must be attributed to the entity that owns the domain it lives on. A brand name appearing within a URL, title, or content of a citation does not constitute attribution to that brand. Only domain ownership constitutes attribution. No citation exits the attribution process without an assigned owner.

# 7. Consistency

# Consistency.

For a post-purchase prompt, **Consistency (0-100% Score)** captures how much the meaning of the AI's answer stays the same across repeated runs. It relays whether a customer asking the same question twice gets the same story.

**Buckets**

| No | Label | Cause | Customer Experience |
| :---- | :---- | :---- | :---- |
| **0, 1, 2** | Unrealiable | The AI gives a different answer nearly every time this question is asked. | - Customers are likely getting conflicting information. - Trust in your post-purchase experience is at risk. |
| **3, 4,5** | Inconsistent | Answers vary more often than they align. A pattern exists but it frequently breaks. | Customers who ask twice or check again may get a different story. - Erodes confidence in your brand. |
| **6,7,8** | Reliable | The AI gives the same answer the large majority of the time with rare variation only. | Customers consistently get the same story. - Trust in your post-purchase messaging is well supported. |
| **9,10** | Consistent | The AI gives the same answer every time.  No meaningful variation across runs. | Every customer asking this question gets the same clear answer. Brand's post-purchase message is landing as intended. |

## Definitions - Semantic + Structure Signals

Consistency is calculated by semantic & structured signals (presence & sentiments)
Semantic embedding similarity is the primary signal, as it captures most of the changes when there is a shift in the brand-related performance indices over the response (presence and sentiments). The structured signals (presence and sentiment) add precision where embeddings are weak—specifically, subtle presence gaps that don't shift the rest of the response much and tone flips that are too small to move cosine distance significantly.

### 7.1 Semantic Base

For K runs per prompt-model pair, compute all pairwise cosine similarities across the K response embeddings. The number of unique pairs generalizes naturally as `C(K,2) = K(K-1)/2`.

**SemanticCons(p,m,K) = [2 / K(K-1)] × Σᵢ₌₁ᴷ Σⱼ₌ᵢ₊₁ᴷ cos(eᵢ, eⱼ)**

Where `eᵢ` is the unit-normalized embedding of generation `i`, and `cos(eᵢ,eⱼ)` is cosine similarity bounded to `[0,1]`.

### 7.2 Presence Stability

Presence is Bernoulli. Its variance is maximized at `μ = 0.5` (brand present half the runs) and is zero when all runs agree. The normalized Bernoulli variance gives a clean `[0,1]` stability measure:

**μ_pres = (1/K) × Σᵍ Pres(b,p,m,g)**

**PresStability(b,p,m,K) = 1 − 4 × μ_pres × (1 − μ_pres)**

Note: The consistently absent edge case. If the brand appears in 0 of K runs, `PresStability = 1.0`. This is technically correct, but it's a visibility problem, not a consistency problem.
Flag—If `μ_pres = 0`, suppress the consistency score for this prompt and show `"—"` with a tooltip saying the brand was not present in any run. The visibility gap should not inflate the consistency score.

### 7.3 Sentiment Stability

Computed only on runs where the brand is present.
Let `n_pres` = count of runs where `Pres = 1`.

Since `S ∈ [-1, 1]`, the maximum possible `σₛ ≈ 1.0` (when sentiment splits perfectly between -1 and +1). So `SentStability` stays in `[0, 1]` naturally.

### 7.4 Consistency Per Prompt

```
Cons(b,p,m,K) = 0.60 × SemanticCons(p,m,K)
              + 0.30 × PresStability(b,p,m,K)
              + 0.10 × SentStability(b,p,m,K)
```

### Weightage - Semantic 0.60, PresenceStability 0.30, SentimentStability 0.10

### 7.5 Aggregation

Using the existing prompt weights `wₚ` and model weights `αₘ` from your core spec:

```
Cons(b,m) = Σₚ [wₚ × Cons(b,p,m,K)] / Σₚ wₚ
Cons(b)   = Σₘ αₘ × Cons(b,m)
Consistency_b = Cons(b)
```

**Consistency is represented by the bucket values, mentioned above.**
