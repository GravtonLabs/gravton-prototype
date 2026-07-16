---
name: backend-models
description: Backend data-model reference — every Django model, its fields, types, and relationships, organised by app (user, client, brandkit, intent_core, keywords, workflow, citations, insight_metrics, opportunity, l2_opportunity, technical_seo, gsc, reddit, quora, crawl, share, feature_flags), plus the end-to-end data flow and key design patterns (Domain hub-and-spoke, run_id correlation, brand-resolution cascade, checkpoints). Load to map a concept to the exact table/column/foreign key to query, or to understand how records relate.
visibility: internal
---

# Gravton Console — Backend Models Reference

> **Platform purpose:** GEO (Generative Engine Optimization) — helps brands understand and improve their visibility in AI-generated responses (ChatGPT, Perplexity, Gemini, etc.)

---

## Table of Contents

1. Abstract Base Models
2. User & Auth
3. Client / Organization
4. Brandkit — Brand Identity Layer
5. Intent Core — Prompt Universe
6. Keywords
7. Workflow — Pipeline Orchestration
8. Citations — AI Citation Tracking
9. Insight Metrics — Brand Visibility Scoring
10. Opportunity — Gap & Action Engine
11. L2 Opportunity — Guided Session
12. Technical SEO
13. GSC — Google Search Console
14. Reddit Intelligence
15. Quora Intelligence
16. Crawl
17. Share
18. Feature Flags
19. End-to-End Data Flow
20. Key Design Patterns

---

## 1. Abstract Base Models

**File:** `backend_src/apps/base/abstract_models.py`

All concrete models inherit from one of these. They are never stored as their own tables.

| Model | Fields | Purpose |
|---|---|---|
| `TimeAuditModel` | `created_at`, `updated_at` | Timestamps on every record |
| `UserAuditModel` | `created_by → CustomUser`, `updated_by → CustomUser` | Who created/modified |
| `BaseModel` | Inherits both above | Full audit trail (used for user-facing entities) |

> Most models use `TimeAuditModel`. Models that need user accountability (Organization, Workflow, etc.) use `BaseModel`.

---

## 2. User & Auth

**App:** `backend_src.apps.user`

### `CustomUser` (extends `AbstractUser`, `TimeAuditModel`)

The central auth entity. Every action in the system traces back here.

| Field | Type | Notes |
|---|---|---|
| `username` | CharField (unique) | Primary login identifier |
| `email` | EmailField (unique, nullable) | Also used for login |
| `first_name`, `last_name` | From AbstractUser | Normalized on save |

**Key methods:**
- `token` — returns a `LoginTrackingAccessToken` (JWT)
- `generate_magic_link_token()` — creates a short-lived refresh token for passwordless login
- `send_otp(via)` — sends OTP via email or SMS
- `check_otp(raw_otp)` — verifies OTP

---

## 3. Client / Organization

**App:** `backend_src.apps.client`

### `Organization` (extends `BaseModel`)

The top-level tenant. Every domain, workflow, and metric belongs to an organization.

| Field | Type | Notes |
|---|---|---|
| `name` | CharField | Company name |
| `brand_name` | CharField (nullable) | Display name |
| `domain` | URLField | Primary website |
| `size` | PositiveIntegerField | Bucketed (ORGANIZATION_SIZE_CATEGORY) |
| `region` | CharField | APAC / Americas / EMEA |
| `status` | BooleanField | Active/inactive |

**Key properties:**
- `default_preference` — first active `OrganizationPreference`
- `is_subscribed` — checks active subscriptions or preference metadata
- `has_reports` — checks subscriptions or preference metadata

---

### `OrganizationUser` (extends `BaseModel`)

Links a `CustomUser` to an `Organization`. One user → one org (OneToOne on user).

| Field | Type | Notes |
|---|---|---|
| `organization` | FK → Organization | Which org |
| `user` | OneToOneField → CustomUser | One user per org |
| `role` | CharField | `owner` or `member` |
| `status` | BooleanField | Active/inactive |

---

## 4. Brandkit — Brand Identity Layer

**App:** `backend_src.apps.brandkit`

This app defines the brand's competitive landscape — what domains they own, who their competitors are, and what product lines exist.

### `Domain` (extends `BaseModel`)

A tracked website belonging to an organization. The central FK that most other models point to.

| Field | Type | Notes |
|---|---|---|
| `organization` | FK → Organization | Owner |
| `name` | CharField | Human label |
| `url` | URLField | The website URL |
| `target_locations` | JSONField | Geo targets for analysis |
| `topic_extraction_snapshot` | JSONField | Cached topic snapshot |
| `competitors_initialized` | BooleanField | Whether competitor seeding ran |

> `Domain` is the **hub** of the data model. Nearly every other model has a FK back to `Domain`.

---

### `Competitor` (extends `TimeAuditModel`)

A brand that competes with the domain. Includes both user-added and AI-discovered competitors.

| Field | Type | Notes |
|---|---|---|
| `organization` | FK → Organization | |
| `domain` | FK → Domain | Which domain this competitor is for |
| `name` | CharField | Brand name |
| `url` | URLField | Competitor website |
| `is_focal` | BooleanField | Is this the client's own brand? |
| `pool_rank` | IntegerField | Relative importance rank |
| `source` | CharField | `user_added` / `suggested` / `discovered` |
| `is_active` | BooleanField | |

**Business logic:** The `is_focal=True` competitor represents the client's own brand. All metrics compare the focal brand against others.

---

### `BrandAlias` (extends `TimeAuditModel`)

Alternate names for a competitor (e.g., "Google" vs "Alphabet").

| Field | Type | Notes |
|---|---|---|
| `competitor` | FK → Competitor | |
| `alias_name` | CharField | Alternate name |
| `is_canonical` | BooleanField | The primary name |
| `source` | CharField | `ai` or `user_added` |

---

### `CompetitorDomainAlias` (extends `TimeAuditModel`)

Alternate domains for a competitor (e.g., `google.com` and `google.co.in`).

| Field | Type | Notes |
|---|---|---|
| `competitor` | FK → Competitor | |
| `domain` | CharField | Domain string (normalized) |
| `is_primary` | BooleanField | |
| `source` | CharField | `user_added` / `ai` / `inferred` / `system_auto` |

**Used in:** Citation attribution — when an AI cites `google.co.uk`, it resolves to the Google competitor via this table.

---

### `OwnedDomainSuggestion` (extends `TimeAuditModel`)

When citation analysis discovers a domain that might be owned by a known competitor but isn't confirmed yet.

| Field | Type | Notes |
|---|---|---|
| `competitor` | FK → Competitor | Probable owner |
| `suggested_domain` | CharField | Raw domain from citations |
| `normalized_domain` | CharField | Cleaned domain |
| `status` | CharField | `needs_review` → `linked` / `rejected` / `revoked` |
| `citation_count` | IntegerField | How often this domain was cited |
| `reviewed_by` | FK → CustomUser | Who reviewed it |

---

### `ProductVertical` (extends `TimeAuditModel`)

A product line or business segment that a competitor (or the focal brand) operates in.

| Field | Type | Notes |
|---|---|---|
| `domain` | FK → Domain | |
| `product_vertical` | CharField | e.g. "CRM", "Analytics" |
| `competitor` | FK → Competitor (nullable) | If null, belongs to focal brand |
| `is_active` | BooleanField | |

---

### `Persona` (extends `TimeAuditModel`)

Target buyer roles for a domain. Used to categorize prompts.

| Field | Type | Notes |
|---|---|---|
| `domain` | FK → Domain | |
| `persona` | CharField | `Decision Maker` / `Influencer` / `User` |

---

### `Brandkit` (extends `BaseModel`)

AI-generated brand narrative for a domain (or competitor). Captures brand voice, market segment, buyer personas.

| Field | Type | Notes |
|---|---|---|
| `domain` | FK → Domain | |
| `competitor` | FK → Competitor (nullable) | If analyzing a competitor |
| `cluster` | FK → IntentCluster (nullable) | Cluster-specific brandkit |
| `description`, `market_segment`, `brand_voice` | TextField | LLM-generated content |
| `model_used` | TextField | Which LLM generated this |
| `version` | IntegerField | Iteration number |

---

## 5. Intent Core — Prompt Universe

**App:** `backend_src.apps.intent_core`

This is the **brain** of the platform. It models the universe of AI prompts a potential buyer might ask.

### `IntentCluster` (extends `TimeAuditModel`)

A topic cluster — a group of related prompts (e.g., "CRM for enterprise", "sales automation").

| Field | Type | Notes |
|---|---|---|
| `domain` | FK → Domain | |
| `label` | TextField | Cluster name |
| `target_locations` | JSONField | Geo filter |
| `target_categories` | JSONField | Category filter |
| `product_vertical` | FK → ProductVertical (nullable) | Product alignment |
| `source` | CharField | `suggested` / `user_added` / `L3_source` |
| `l3_workflow` | FK → Workflow (nullable) | If auto-generated by L3 |
| `is_active` | BooleanField | |

---

### `SyntheticPrompt` (extends `TimeAuditModel`)

A single AI prompt (question/query) that a potential buyer might type into an AI. The **atomic unit** of analysis.

| Field | Type | Notes |
|---|---|---|
| `cluster` | FK → IntentCluster | Parent cluster |
| `text` | TextField | The actual prompt text |
| `location` | CharField | Geo context |
| `category` | CharField | Category context |
| `funnel` | CharField | `Top` / `Mid` / `Bottom` / `Post-Purchase` |
| `prompt_type` | CharField | `Breadth` or `Depth` |
| `persona` | FK → Persona (nullable) | Target buyer role |
| `w_p` | FloatField | Weight/priority for execution scheduling |
| `execution_count` | IntegerField | How many times this prompt was run |
| `source` | CharField | `suggested` / `user_added` / `group_a` / `group_b` / `l3_group_a` / `l3_group_b` |
| `is_active` | BooleanField | |
| `is_branded` | BooleanField | Does it mention a brand explicitly? |
| `matched_brands` | JSONField | Which brands appear in the prompt text |

**Business logic:** Every citation, metric, and opportunity anchors to a `SyntheticPrompt`. The `w_p` weight governs which prompts get executed first in a run.

---

### `SyntheticPromptKeyword` (no base model)

Many-to-many bridge: a prompt can be derived from multiple keywords in the library.

| Field | Type |
|---|---|
| `synthetic_prompt` | FK → SyntheticPrompt |
| `k_lib` | FK → KeywordLibrary |

---

### `PromptSocialArtifact` (extends `TimeAuditModel`)

A social post (Reddit thread, Quora question, YouTube video) that is associated with a specific prompt via keyword matching.

| Field | Type | Notes |
|---|---|---|
| `domain` | FK → Domain | |
| `prompt` | FK → SyntheticPrompt | |
| `keyword` | CharField | The keyword that linked them |
| `platform` | CharField | `reddit` / `quora` / `youtube` |
| `artifact_type` | CharField | `thread` / `question` / `video` |
| `external_id` | CharField | Platform's native ID |
| `metadata` | JSONField | Platform-specific data |

---

### `Case2DemandRun` (extends `TimeAuditModel`)

A completed demand-universe computation run (pipeline job that discovers the prompt universe).

| Field | Type | Notes |
|---|---|---|
| `domain` | FK → Domain | |
| `case2_run_id` | CharField | External pipeline run ID |
| `result_payload` | JSONField | Raw output |

---

### `PromptSocialIngestionRun` (extends `TimeAuditModel`)

Tracks a batch ingestion of social content (Reddit/Quora/YouTube) into `PromptSocialArtifact`.

| Field | Type | Notes |
|---|---|---|
| `domain` | FK → Domain | |
| `workflow_run_id` | CharField | External run ID |
| `status` | CharField | `running` / `completed` / `failed` |
| `stats` | JSONField | Counts of ingested items |

---

## 6. Keywords

**App:** `backend_src.apps.keywords`

### `KeywordLibrary` (extends `TimeAuditModel`)

A keyword belonging to a domain's research library — sourced from GSC, CSV upload, or AI discovery.

| Field | Type | Notes |
|---|---|---|
| `domain` | FK → Domain | |
| `gsc_query` | FK → GSCQuery (nullable) | If sourced from GSC |
| `gsc_upload` | FK → GSCUpload (nullable) | If sourced from CSV |
| `intent_cluster` | FK → IntentCluster (nullable) | Cluster assignment |
| `l3_workflow` | FK → Workflow (nullable) | If generated by L3 workflow |
| `source` | CharField | `gsc` / `upload` / `brand` / `L3_source` |
| `keyword` | CharField | The keyword string |
| `sv` | IntegerField | Traditional search volume |
| `asv` | IntegerField | AI search volume |
| `ai_demand` | IntegerField | Bayesian fused demand signal |
| `score` | FloatField | Relevance score |

---

## 7. Workflow — Pipeline Orchestration

**App:** `backend_src.apps.workflow`

### `Config` (extends `BaseModel`)

Named configuration blobs for workflows. Stores arbitrary JSON settings.

| Field | Type |
|---|---|
| `name` | CharField |
| `config` | JSONField |

---

### `Workflow` (extends `BaseModel`)

Represents a single execution run of an external pipeline (Airflow DAG or similar).

| Field | Type | Notes |
|---|---|---|
| `organization` | FK → Organization | |
| `domain` | FK → Domain (nullable) | |
| `config` | FK → Config (nullable) | |
| `run_id` | CharField | External pipeline run ID |
| `dag_id` | CharField | DAG identifier |
| `run_status` | CharField | `QUEUED` / `RUNNING` / `SUCCESS` / `FAILED` / `STALLED` |
| `run_status_message` | TextField | Error or status detail |
| `run_started_at` | DateTimeField | |
| `run_completed_at` | DateTimeField | |

**Business logic:** `STALLED` = the workflow was triggered but never actually started (useful for detecting silent pipeline failures).

---

## 8. Citations — AI Citation Tracking

**App:** `backend_src.apps.citations`

This app records the raw output of running prompts through AI models — specifically, which URLs and brands the AI cited.

### `PipelineRun` (no base model)

A top-level run of the citation-generation pipeline across all prompts for a domain.

| Field | Type | Notes |
|---|---|---|
| `run_id` | CharField (unique) | External run identifier |
| `domain_id` | IntegerField | Raw FK (not ORM relation) |
| `org_id` | IntegerField | Raw FK |
| `status` | CharField | `queued` / `running` / `completed` / `failed` |
| `stage` | CharField | Current pipeline stage |
| `started_at` / `completed_at` | DateTimeField | |

---

### `GenerationMetric` (no base model)

One AI model call for one prompt — the metadata record of a single generation.

| Field | Type | Notes |
|---|---|---|
| `generation_id` | CharField (unique) | Matches `Generation.generation_id` |
| `run_id` | CharField | Parent pipeline run |
| `domain` | FK → Domain | |
| `prompt` | FK → SyntheticPrompt | |
| `cluster` | FK → IntentCluster | |
| `model_id` | CharField | e.g. `gpt-4o`, `claude-3-5-sonnet` |
| `generation_k` | IntegerField | Which repetition (k-th run of same prompt) |
| `response_excerpt` | TextField | Snippet of the AI response |
| `generated_at` | DateTimeField | |

---

### `PromptCitation` (no base model)

A single URL citation extracted from an AI response. The **most granular citation record**.

| Field | Type | Notes |
|---|---|---|
| `run_id` | CharField | Parent pipeline run |
| `response_id` | CharField | Which specific response |
| `source_domain` | FK → Domain | Which domain's prompts were run |
| `prompt` | FK → SyntheticPrompt | |
| `cluster` | FK → IntentCluster | |
| `model_id` | CharField | AI model used |
| `page_url` | TextField | Cited URL |
| `normalized_domain` | CharField | Domain extracted from URL |
| `brand` | FK → Competitor | Resolved brand (exact match) |
| `aggregate_brand` | FK → Competitor | Resolved after domain-alias aggregation |
| `supported_brand` | FK → Competitor | Brand the citation supports |
| `citation_mass_weight` | FloatField | Weighted importance of this citation |
| `damping_factor` | FloatField | Position-based decay |
| `extraction_source` | CharField | `legacy` or newer extraction method |
| `claim_text` | TextField | The claim being cited |
| `confidence` | FloatField | Extraction confidence |
| `included_in_metrics` | BooleanField | Whether this feeds into aggregated metrics |

**Business logic:** Brand resolution cascade: raw `domain` → `CompetitorDomainAlias` lookup → `brand` → `aggregate_brand`. This is how `google.co.uk` citations roll up to the Google competitor.

---

### `CitationCompetitorCandidate` (no base model)

Domains frequently cited but not yet associated with any known competitor. Seeds `OwnedDomainSuggestion`.

| Field | Type |
|---|---|
| `run_id` | CharField |
| `domain_id` | IntegerField |
| `candidate_domain` | CharField |
| `citation_count` | IntegerField |

---

## 9. Insight Metrics — Brand Visibility Scoring

**App:** `backend_src.apps.insight_metrics`

Takes the raw citations and computes aggregated brand visibility scores at multiple granularities.

### `Generation` (extends `TimeAuditModel`, PK = `generation_id`)

One execution of one prompt against one AI model. The source of all metrics.

| Field | Type | Notes |
|---|---|---|
| `generation_id` | CharField (PK) | Unique generation ID |
| `run_id` | CharField | Parent run |
| `domain` | FK → Domain | |
| `cluster` | FK → IntentCluster | |
| `prompt` | FK → SyntheticPrompt | |
| `model_id` | CharField | AI model |
| `generation_k` | IntegerField | k-th repetition |
| `s3_key` | TextField | Full response stored in S3 |
| `brands` | JSONField | List of brands detected |
| `brands_mentioned` | IntegerField | Count |
| `focal_brand_present` | BooleanField | Was the client's brand in the response? |

---

### `InsightRun` (extends `TimeAuditModel`)

A versioned compute run that aggregates all `Generation` records for a cluster+model combination into metrics.

| Field | Type | Notes |
|---|---|---|
| `run_id` | CharField | External run ID |
| `cluster` | FK → IntentCluster | |
| `model_id` | CharField | |
| `run_version` | IntegerField | Monotonically increasing |

**Business logic:** Each new `InsightRun` for a cluster/model pair creates a new snapshot. Historical versions are preserved for trend analysis.

---

### `PromptMetric` (extends `TimeAuditModel`)

Aggregated metrics for one brand, one prompt, one run. The **prompt-level score**.

| Field | Type | Notes |
|---|---|---|
| `run` | FK → InsightRun | |
| `prompt` | FK → SyntheticPrompt | |
| `brand_id` | CharField | Which brand |
| `execution_count` | IntegerField | Prompt runs included |
| `sov` | FloatField | Share of Voice (0-1) |
| `position_rank` | IntegerField | Average rank in responses |
| `presence_rank` | IntegerField | |
| `visibility_score` | FloatField | Composite score |
| `sentiment_score` | FloatField | -1 to +1 |
| `consistency_score` | FloatField | Variance in presence |
| `consistency_bucket` | IntegerField | Bucketed consistency |
| `presence_suppressed` | BooleanField | Low sample, suppressed from display |

---

### `BrandMetric` (extends `TimeAuditModel`)

Per-prompt brand-level scores (a leaner companion to `PromptMetric`, used in UI tables).

| Field | Type |
|---|---|
| `run` | FK → InsightRun |
| `prompt` | FK → SyntheticPrompt |
| `brand_id` | CharField |
| `presence` | FloatField |
| `sov` | FloatField |
| `visibility_score` | FloatField |
| `sentiment_score` | FloatField |

---

### `GenerationBrandMetric` (extends `TimeAuditModel`)

Per-generation (single AI call) brand-level data — the raw signal before aggregation.

| Field | Type | Notes |
|---|---|---|
| `generation` | FK → Generation | |
| `brand_id` | CharField | |
| `is_present` | BooleanField | |
| `mention_count` | IntegerField | |
| `rank` | IntegerField | Order of first appearance |
| `sentiment_score` | FloatField | |
| `sentiment_bucket` | CharField | `positive` / `negative` / `neutral` |
| `sentiment_positive_signals` | JSONField | Supporting phrases |
| `sentiment_negative_signals` | JSONField | |

---

### `BrandSignalMetric` + `BrandSignalMember`

Aggregated sentiment signals — groups of phrases across generations that consistently express a positive or negative sentiment about a brand.

`BrandSignalMetric` — the grouped signal:
- `run`, `domain`, `brand_id`, `direction` (`positive`/`negative`), `signal` (the phrase group), `mention_count`

`BrandSignalMember` — individual contributing phrases:
- `signal` → FK to `BrandSignalMetric`
- `generation_brand_metric` → FK to `GenerationBrandMetric`
- `phrase` — the actual text

---

### `TopicMetric` / `TopicMetricUnbranded`

Cluster-level aggregations. Rolls up all prompt-level metrics to give a topic-level brand score.

| Field | Notes |
|---|---|
| `run`, `domain`, `cluster`, `brand` | Composite PK |
| `sentiment_sum`, `sov_sum`, `presence_sum`, `position_sum` | Raw sums for averaging |
| `prompt_ct` | Number of prompts contributing |
| `social_mention_count` | Social signals included |

`TopicMetricUnbranded` — same structure but for unbranded prompt universe only.

---

### `DemandUniverseRun` + `DemandUniversePromptLabel`

Computes the full **demand universe** — which prompts have market volume and which brands are winning/losing.

`DemandUniverseRun`:
- `metrics_run_id`, `case2_run_id` — source runs
- `volume_threshold` — minimum search volume to include
- `untapped_volume_total` — total volume in whitespace opportunities

`DemandUniversePromptLabel`:
- `demand_score` (0-100) — composite demand score
- `cited` — is the focal brand cited for this prompt?
- `sov`, `position_rank`, `visibility_score` — brand performance on this prompt

---

### `UntappedTopic` + `UntappedPrompt`

AI-identified topics that have market demand but the focal brand is absent from AI responses.

`UntappedTopic`:
- `label` — topic name
- `estimated_volume` — demand volume
- `signal_sources` — supporting evidence (citations, GSC, etc.)
- `status` — `suggested` or `archived`

`UntappedPrompt` — specific prompt examples for an untapped topic.

---

### `FanoutQuery`

When an AI model issues follow-up sub-queries as part of answering a prompt (e.g., Perplexity's search fanout), these are captured here.

| Field | Notes |
|---|---|
| `generation` | FK → Generation |
| `query_text` | The fanout query text |
| `subqueries` | JSONField — nested queries |
| `sources` | JSONField — sources fetched |

---

### `ResponseExecutionProgress`

Job-level progress tracking for each (prompt, model, k) generation task in a run.

| Field | Notes |
|---|---|
| `run_id`, `prompt_id`, `model_id`, `k_index` | Composite unique key |
| `progress_pct` | 0-100 |
| `attempt_count` | Retries |
| `celery_task_id` | Async task reference |
| `error_code` | On failure |

---

## 10. Opportunity — Gap & Action Engine

**App:** `backend_src.apps.opportunity`

Converts metric gaps into actionable recommendations.

### `CheckpointSlot` / `CheckpointSlotV2`

A **metric snapshot** for a prompt at a specific run — used to detect future changes.

| Field | Notes |
|---|---|
| `prompt` | FK → SyntheticPrompt |
| `run` | FK → InsightRun |
| `value` | `mention` / `cited` / `rank` / `sentiment` / `consistency` / `position` / `sov` / `passed` |
| `metric_value` | The numeric value at this checkpoint |

V2 adds `model_id` for model-specific tracking.

---

### `CheckpointState` / `CheckpointStateV2`

Monitors a prompt's metrics over time. Fires when a threshold is crossed.

| Field | Notes |
|---|---|
| `prompt` | OneToOne → SyntheticPrompt (V1) / FK (V2) |
| `status` | `active` or `triggered` |
| `trigger_fired` | `absence` / `decline` / `competitor_emergence` |
| `triggered_at` | When the trigger fired |

**Business logic:** The checkpoint system watches KPIs. If the focal brand disappears from a prompt (`absence`), drops significantly (`decline`), or a new competitor surges (`competitor_emergence`), it triggers an alert.

---

### `Opportunity`

A single recommended action derived from a metric gap for a prompt.

| Field | Notes |
|---|---|
| `prompt` | FK → SyntheticPrompt |
| `checkpoint` | Which KPI triggered this |
| `intent` | Topic area |
| `gap_title` | Short description of the gap |
| `priority` | `Quick Win` / `Big Bet` / `Filler` |
| `action_type` | `Create` / `Optimize` / `Community` / `Outreach` |
| `action_items` | JSONField — step-by-step actions |
| `target_venue` | Where to act (e.g., "brand website", "Reddit") |
| `rationale` | Why this opportunity exists |

---

### `OpportunityCluster`

Groups related `Opportunity` records into a unified campaign theme.

| Field | Notes |
|---|---|
| `domain` | FK → Domain |
| `cluster_name` | Theme name |
| `impact` | `High` / `Medium` / `Low` |
| `impact_score` | Numeric score |
| `status` | `to_do` / `in_progress` / `done` |
| `opportunities` | M2M → Opportunity |
| `prompts` | M2M → SyntheticPrompt |
| `execution_paths` | JSONField — tactical playbook |

---

## 11. L2 Opportunity — Guided Session

**App:** `backend_src.apps.l2_opportunity`

A conversational, multi-step wizard that guides a user through building a personalized opportunity plan.

### `L2OpportunitySession`

The session state machine.

| Field | Notes |
|---|---|
| `domain` | FK → Domain |
| `user` | FK → CustomUser |
| `goal_type` | The user's stated goal |
| `current_step` | Which step they're on |
| `status` | `draft` or completed states |
| `messages` | JSONField — conversation history |
| `brand_directives` | JSONField — user's brand inputs |
| `step_data` | JSONField — per-step collected data |
| `review_plan_confirmed` | BooleanField — user approved the plan |

---

### `L2SessionPromptSelection`

Which prompts were selected for this session's opportunity plan, with synthesis results.

| Field | Notes |
|---|---|
| `session` | FK → L2OpportunitySession |
| `prompt` | FK → SyntheticPrompt |
| `rank_score` | Priority score |
| `gap_snapshot` | JSONField — metric state at selection time |
| `synthesis_status` | `pending` / `done` / `failed` |
| `synthesis_payload` | JSONField — LLM-generated plan |

---

### `L2SessionUserSource`

User-provided context (URLs, documents, notes) attached to a session.

| Field | Notes |
|---|---|
| `session` | FK → L2OpportunitySession |
| `source_type` | `url` / `document` / `note` |
| `url`, `document_ref`, `notes` | The content |

---

## 12. Technical SEO

**App:** `backend_src.apps.technical_seo`

Automated crawl-and-analyze pipeline for AI-readability of a domain's pages.

### `PageTemplate`

A representative URL for a page type (e.g., homepage, product page, blog post).

| Field | Notes |
|---|---|
| `domain` | FK → Domain |
| `url` | The page URL |
| `template_name` | Human label |
| `source` | `manual` / `gsc_top` / `user_defined` |

---

### `TechnicalSeoScan`

The top-level scan record. Tracks progress and aggregated health scores.

| Field | Notes |
|---|---|
| `status` | `pending` → `running` → `completed` / `failed` |
| `phase` | Granular stage: `queued` / `resolving` / `rendering` / `analyzing` / `scoring` / `completed` |
| `health_score` | 0-100 overall score |
| `score_delta` | Change from previous scan |
| `bot_access_score`, `rendering_score`, `readability_score`, `schema_score`, `mobile_score`, `speed_score` | Dimension scores |
| `p0_count`, `p1_count`, `p2_count` | Issues by severity |
| `robots_state` | `ok` / `missing` / `error` |
| `sitemap_state` | `ok` / `missing` / `error` |
| `apify_run_id` | External crawler job ID |

---

### Sub-models of `TechnicalSeoScan`

| Model | What it stores |
|---|---|
| `BotAccessResult` | Per-bot (Googlebot, GPTBot, etc.) access result per page template |
| `PageCheckResult` | Full page audit: indexability, JS dependency, readability grade, schema, speed, mobile |
| `SchemaCheckResult` | Structured data validation per schema type per page |
| `SitemapUrl` | Each URL from the sitemap, with selection reason and page template linkage |
| `Finding` | A specific issue: type, severity (`p0`/`p1`/`p2`), affected pages, fix hint |

---

### `SeoScanCreditTxn`

Tracks credits consumed or granted for SEO scans (billing/quota management).

| Field | Notes |
|---|---|
| `organization` | FK → Organization |
| `amount` | Signed integer (positive = grant, negative = spend) |
| `reason` | `grant` / `scan_spend` / `refund` / `adjustment` |
| `scan` | FK → TechnicalSeoScan (nullable) |

---

## 13. GSC — Google Search Console

**App:** `backend_src.apps.gsc`

Ingests traditional SEO performance data from Google Search Console.

### `GSCProperty`

OAuth-connected GSC property (website verified in GSC).

| Field | Notes |
|---|---|
| `domain` | FK → Domain |
| `authorized_by` | FK → CustomUser |
| `site_url` | The GSC property URL |
| `access_token`, `refresh_token` | OAuth tokens |
| `last_queried_start` / `last_queried_end` | Date range of last fetch |

---

### `GSCUpload`

A CSV upload of GSC data when OAuth isn't available.

| Field | Notes |
|---|---|
| `domain` | FK → Domain |
| `uploaded_by` | FK → CustomUser |
| `start_date`, `end_date` | Date range covered |
| `status` | `pending` → `processing` → `completed` / `failed` |
| `overlap_preference` | `replace` / `keep_existing` / `append` |

---

### `GSCQuery` / `GSCPage`

Individual rows of GSC data (queries or pages) with clicks, impressions, CTR, and position.

Both can come from either `GSCProperty` (API) or `GSCUpload` (CSV). They feed into `KeywordLibrary`.

---

## 14. Reddit Intelligence

**App:** `backend_src.apps.reddit`

Monitors Reddit for brand mentions and competitive signals.

### Data hierarchy

```
Domain
 └── RedditSubreddit (a subreddit tracked for this domain)
      └── RedditThread (a post in that subreddit)
           ├── RedditPostChunk (chunked text for analysis)
           ├── RedditThreadStructure (structural metadata)
           ├── RedditThreadIntelligence (quality scores)
           ├── RedditClassification (topic/funnel/persona labels)
           ├── RedditMention (brand mention within the thread)
           └── RedditComment
                ├── RedditCommentMention (brand mention in comment)
                └── RedditCommentClassification
```

### Key models

**`RedditSubreddit`** — a subreddit tracked for a domain. Includes `authority_score`, sync cursor for incremental fetching, `citation_confirmed` (whether AI models cite threads from it).

**`RedditThread`** — a post. Tracks `score`, `upvote_ratio`, `created_utc`, `cited_by_models` (which AI models have cited this thread).

**`RedditMention`** — a brand mention within a thread or chunk. Includes:
- `competitor` — which brand was mentioned
- `match_method` — `alias` / `flashtext` / `llm`
- `sentiment_bucket` + `sentiment_score`
- `char_start` / `char_end` — character offset for highlight display

**`RedditSubredditAuthority`** — composite authority score per subreddit: `subscriber_score`, `engagement_score`, `content_quality_score`, `topical_score`, `citation_score`.

**`RedditInsightSignal`** — computed signals per domain: `mention_frequency`, `competitor_gap`, `sentiment_trend`, `rising_thread`, `subreddit_optimization`, `missing_brand_prompt`.

**`RedditSyncRun`** — tracks each sync run: `sync_mode` (`daily`/`weekly`/`backfill`), `api_requests_used`, `stats`.

---

## 15. Quora Intelligence

**App:** `backend_src.apps.quora`

Same pattern as Reddit, adapted for Quora's topic/question structure.

### Data hierarchy

```
Domain
 ├── QuoraTopic (a Quora topic tracked for this domain)
 │    └── QuoraQuestion (a question in that topic)
 └── QuoraSpace (a Quora Space tracked for this domain)
      └── QuoraQuestion (questions from the space)
           ├── QuoraAnswerChunk (chunked answer text)
           ├── QuoraMention (brand mention)
           ├── QuoraClassification (topic/funnel/persona)
           └── QuoraQuestionAuthority (quality score)
```

**`QuoraQuestionAuthority`** — composite score: `answer_count_score`, `follower_score`, `view_score`, `top_answer_upvotes_score`, `citation_score`, `topical_score`, `recency_score`.

**`QuoraInsightSignal`** — same signal types as Reddit, adapted for Quora entities (question, topic, competitor, domain).

---

## 16. Crawl

**App:** `backend_src.apps.crawl`

Manages the domain's own web crawl for page content and freshness tracking.

### `CrawledUrl`

A URL discovered and crawled for a domain.

| Field | Notes |
|---|---|
| `domain` | FK → Domain |
| `canonical_url` | The final URL after redirects |
| `http_status` | HTTP response code |
| `depth` | Crawl depth from root |
| `source` | `sitemap` / `discovery` / `gsc` / `curated` |
| `is_active` | Still relevant |

---

### `PageSnapshot`

A point-in-time capture of a page (both raw HTML and rendered HTML stored in S3).

| Field | Notes |
|---|---|
| `domain` | FK → Domain |
| `canonical_url` | |
| `render_version` | Rendering version for cache invalidation |
| `raw_html_s3_key` | S3 key for raw HTML |
| `rendered_html_s3_key` | S3 key for JS-rendered HTML |
| `content_hash` | For change detection |
| `ttfb_ms` | Time to first byte |

---

### `DomainCrawlMetrics`

OneToOne with `Domain` — aggregate crawl health for the domain.

| Field | Notes |
|---|---|
| `robots_state` | `ok` / `missing` / `unknown` |
| `sitemap_state` | `ok` / `missing` / `unknown` |
| `sitemap_url_count` | Total URLs in sitemap |
| `pages_discovered` | Total pages found |
| `last_crawl_at` | When the last crawl completed |

---

## 17. Share

**App:** `backend_src.apps.share`

### `DashboardShareLink`

Token-based shareable links for read-only dashboard access.

| Field | Notes |
|---|---|
| `id` | UUID (PK) |
| `organization` | FK → Organization |
| `domain` | FK → Domain |
| `token_hash` | SHA-256 hash of the share token |
| `created_by` | FK → CustomUser |
| `expires_at` | Optional expiry |
| `revoked_at` | Optional revocation |

**Key property:** `is_active` — True if neither revoked nor expired.

---

## 18. Feature Flags

**App:** `backend_src.apps.feature_flags`

### `FeatureFlag`

System-wide feature toggles.

| Field | Notes |
|---|---|
| `key` | SlugField — the flag identifier |
| `flag_type` | `boolean` or `multivariate` |
| `is_active` | Global on/off |
| `on_value` | JSONField — value when on |
| `rollout_percentage` | % of users who see this enabled |

**Signals:** `post_save` and `post_delete` invalidate the `FLAGS_CACHE`.

### `FeatureFlagOverride`

Per-organization flag value override — enables gradual rollouts or early access for specific orgs.

---

## 19. End-to-End Data Flow

```
1. ONBOARDING
   CustomUser → Organization → OrganizationUser
                    └── Domain
                          ├── Competitor (+ BrandAlias, CompetitorDomainAlias)
                          ├── ProductVertical
                          └── Persona

2. INTENT MAPPING
   Domain → IntentCluster → SyntheticPrompt
   KeywordLibrary → SyntheticPromptKeyword → SyntheticPrompt

3. PIPELINE EXECUTION
   Workflow (triggered) → PipelineRun
       └── ResponseExecutionProgress (tracks each job)
       └── Generation (one per prompt × model × k)
           └── GenerationBrandMetric (brands in that response)
           └── FanoutQuery (AI sub-queries)

4. CITATION ANALYSIS
   Generation → PromptCitation (URL-level citations)
       └── normalized_domain → CompetitorDomainAlias → Competitor
       └── CitationCompetitorCandidate → OwnedDomainSuggestion (review queue)

5. METRICS AGGREGATION
   InsightRun aggregates Generation records →
       PromptMetric (prompt-level scores)
       BrandMetric (brand-level scores)
       TopicMetric (cluster-level scores)
       BrandSignalMetric (sentiment signal phrases)

6. DEMAND UNIVERSE
   DemandUniverseRun →
       DemandUniversePromptLabel (prompt × brand scores)
       UntappedTopic → UntappedPrompt (whitespace opportunities)

7. OPPORTUNITY GENERATION
   CheckpointSlot (snapshots) → CheckpointState (trigger detection)
   Opportunity (single action) → OpportunityCluster (themed campaign)
   L2OpportunitySession (guided wizard) → L2SessionPromptSelection (AI synthesis)

8. SOCIAL SIGNALS (parallel pipeline)
   Reddit: Subreddit → Thread → Chunk → Mention / Classification
   Quora:  Topic → Question → AnswerChunk → Mention / Classification
   → PromptSocialArtifact (links social content back to SyntheticPrompt)
   → RedditInsightSignal / QuoraInsightSignal

9. TECHNICAL SEO (separate pipeline)
   TechnicalSeoScan → BotAccessResult / PageCheckResult / SchemaCheckResult / Finding

10. DATA INPUTS
    GSCProperty (OAuth) → GSCQuery / GSCPage → KeywordLibrary
    GSCUpload (CSV)     ↗
    CrawledUrl / PageSnapshot → DomainCrawlMetrics
```

---

## 20. Key Design Patterns

### Hub-and-spoke on `Domain`
Almost every model has a FK to `Domain`. Domain is the natural tenant unit — an organization may have multiple domains, each with its own prompt universe, metrics, and social intelligence.

### `run_id` as external correlation key
Many models (especially in `citations` and `insight_metrics`) store a `run_id` CharField rather than a FK to `Workflow`. This decouples the metrics pipeline from the Django ORM and allows the pipeline to run independently while still being queryable from the app.

### Brand resolution cascade
`PromptCitation.domain` (raw string) → `CompetitorDomainAlias` lookup → `PromptCitation.brand` → `PromptCitation.aggregate_brand`. This multi-step resolution handles edge cases like subdomains, ccTLDs, and branded content networks.

### Checkpoint system
V1 uses OneToOne (one checkpoint state per prompt). V2 adds `model_id` to track state per model, enabling model-comparative drift detection.

### JSON fields for extensibility
`metadata`, `config`, `stats`, `extra`, `step_data`, `report_json` — used heavily to avoid migrations for rapidly evolving pipeline outputs. The stable relational columns are queryable; everything else goes in JSON.

### No soft-delete pattern
The codebase uses `is_active` BooleanFields rather than `deleted_at` timestamps. Deletion is logical, not physical, for most user-facing entities.

### Signals for cache invalidation
Only `FeatureFlag` uses Django signals. Everything else coordinates through explicit service calls or Celery tasks.
