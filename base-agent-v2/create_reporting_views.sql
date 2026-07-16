-- =============================================================================
-- Gravton reporting views — derived from gravton-console Django models
--
-- Run against your DB:  psql $GRAVTON_DSN -f create_reporting_views.sql
--
-- Verify real column names with \d <tablename> before running.
-- Views that need a join to reach domain_id are marked [JOIN].
-- Views where domain_id is already on the source table are marked [DIRECT].
--
-- Table name map (Django db_table → used here):
--   insight_metrics.InsightRun     → runs
--   intent_core.IntentCluster      → intent_cluster
--   intent_core.SyntheticPrompt    → synthetic_prompt
--   insight_metrics.PromptMetric   → prompt_metrics
--   citations.PromptCitation       → prompt_citations
--   insight_metrics.TopicMetric    → topic_metrics
--   insight_metrics.BrandSignalMetric → brand_signal_metrics
--   technical_seo.TechnicalSeoScan → technical_seo_scan
--   technical_seo.Finding          → seo_finding
--   opportunity.Opportunity        → opportunities
--   brandkit.Competitor            → competitor
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. v_prompt_citation  [DIRECT — source_domain_id on prompt_citations]
--    Joins competitor for brand name, intent_cluster for topic label.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_prompt_citation;

CREATE VIEW v_prompt_citation AS
SELECT
    pc.id,
    pc.source_domain_id              AS domain_id,
    co.name                          AS brand,
    ic.label                         AS topic,
    sp.text                          AS prompt_text,
    pc.page_url,
    pc.normalized_domain,
    pc.citation_mass_weight,
    pc.damping_factor,
    pc.model_id,
    pc.attribution_type,
    pc.created_at                    AS week_of
FROM prompt_citations pc
LEFT JOIN competitor co              ON co.id  = pc.aggregate_brand_id
LEFT JOIN synthetic_prompt sp        ON sp.id  = pc.prompt_id
LEFT JOIN intent_cluster ic          ON ic.id  = pc.cluster_id;

COMMENT ON VIEW   v_prompt_citation IS
  'gravton_table: {"description":"URL citations from AI responses, attributed to a brand and intent topic"}';
COMMENT ON COLUMN v_prompt_citation.domain_id              IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_prompt_citation.brand                  IS 'gravton: {"role":"dimension","description":"Brand name (from aggregate_brand)"}';
COMMENT ON COLUMN v_prompt_citation.topic                  IS 'gravton: {"role":"dimension","description":"Intent cluster / topic label"}';
COMMENT ON COLUMN v_prompt_citation.week_of                IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_prompt_citation.citation_mass_weight   IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Weighted importance of this citation"}';
COMMENT ON COLUMN v_prompt_citation.damping_factor         IS 'gravton: {"role":"metric","higher_is_better":false,"description":"Citation damping factor (lower = more weight retained)"}';
COMMENT ON COLUMN v_prompt_citation.normalized_domain      IS 'gravton: {"role":"dimension","description":"Registrable root domain of the cited URL"}';
COMMENT ON COLUMN v_prompt_citation.attribution_type       IS 'gravton: {"role":"dimension","description":"How the citation was attributed"}';


-- ---------------------------------------------------------------------------
-- 2. v_prompt_metric  [JOIN — no domain_id on prompt_metrics]
--    prompt_metrics → synthetic_prompt → intent_cluster.domain_id
--    prompt_metrics → runs.created_at  (for timestamp)
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_prompt_metric;

CREATE VIEW v_prompt_metric AS
SELECT
    pm.id,
    ic.domain_id,
    ic.label                         AS topic,
    sp.text                          AS prompt_text,
    pm.brand_id                      AS brand,
    pm.model_id,
    ir.created_at                    AS week_of,
    pm.sov,
    pm.sov_rank,
    pm.sov_median,
    pm.visibility_score,
    pm.sentiment_score,
    pm.consistency_score,
    pm.position_rank,
    pm.presence_rank,
    pm.execution_count,
    pm.brands_mentioned,
    pm.brand_present_count,
    pm.presence_suppressed,
    pm.sentiment_insufficient
FROM prompt_metrics pm
JOIN synthetic_prompt sp             ON sp.id  = pm.prompt_id
JOIN intent_cluster ic               ON ic.id  = sp.cluster_id
JOIN runs ir                         ON ir.id  = pm.run_id;

COMMENT ON VIEW   v_prompt_metric IS
  'gravton_table: {"description":"Per-prompt AI visibility metrics per brand, joined to domain via intent cluster"}';
COMMENT ON COLUMN v_prompt_metric.domain_id          IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_prompt_metric.topic              IS 'gravton: {"role":"dimension","description":"Intent cluster / topic label"}';
COMMENT ON COLUMN v_prompt_metric.brand              IS 'gravton: {"role":"dimension","description":"Brand identifier (brand_id string)"}';
COMMENT ON COLUMN v_prompt_metric.model_id           IS 'gravton: {"role":"dimension","description":"AI model used for scoring"}';
COMMENT ON COLUMN v_prompt_metric.week_of            IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_prompt_metric.sov                IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Share of Voice (0–1)"}';
COMMENT ON COLUMN v_prompt_metric.sov_rank           IS 'gravton: {"role":"metric","higher_is_better":false,"description":"SOV rank among brands on this prompt (lower = better)"}';
COMMENT ON COLUMN v_prompt_metric.sov_median         IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Median SOV across execution runs for this prompt+brand"}';
COMMENT ON COLUMN v_prompt_metric.visibility_score   IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Composite visibility score"}';
COMMENT ON COLUMN v_prompt_metric.sentiment_score    IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Sentiment score, -1 to 1"}';
COMMENT ON COLUMN v_prompt_metric.consistency_score  IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Answer consistency score across executions"}';
COMMENT ON COLUMN v_prompt_metric.position_rank      IS 'gravton: {"role":"metric","higher_is_better":false,"description":"Brand mention position rank (lower = earlier = better)"}';
COMMENT ON COLUMN v_prompt_metric.presence_rank      IS 'gravton: {"role":"metric","higher_is_better":false,"description":"Presence rank among brands (lower = better)"}';


-- ---------------------------------------------------------------------------
-- 3. v_topic_metric  [DIRECT — domain_id on topic_metrics]
--    Joins intent_cluster for label, competitor for brand name, runs for timestamp.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_topic_metric;

CREATE VIEW v_topic_metric AS
SELECT
    tm.id,
    tm.domain_id,
    ic.label                         AS topic,
    co.name                          AS brand,
    co.is_focal,
    ir.created_at                    AS week_of,
    tm.sov_sum,
    tm.sentiment_sum,
    tm.presence_sum,
    tm.position_sum,
    tm.prompt_ct,
    tm.sov_non_null_ct,
    tm.sentiment_non_null_ct,
    tm.presence_non_null_ct,
    tm.position_non_null_ct,
    tm.social_mention_count,
    tm.social_sentiment_score,
    tm.social_authority_score
FROM topic_metrics tm
JOIN intent_cluster ic               ON ic.id  = tm.cluster_id
JOIN competitor co                   ON co.id  = tm.brand_id
JOIN runs ir                         ON ir.id  = tm.run_id;

COMMENT ON VIEW   v_topic_metric IS
  'gravton_table: {"description":"Aggregated AI visibility metrics per brand per intent topic, one row per run"}';
COMMENT ON COLUMN v_topic_metric.domain_id         IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_topic_metric.topic             IS 'gravton: {"role":"dimension","description":"Intent cluster / topic label"}';
COMMENT ON COLUMN v_topic_metric.brand             IS 'gravton: {"role":"dimension","description":"Brand name"}';
COMMENT ON COLUMN v_topic_metric.is_focal          IS 'gravton: {"role":"flag","description":"True when this brand is the focal (own) brand for the domain"}';
COMMENT ON COLUMN v_topic_metric.week_of           IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_topic_metric.sov_sum           IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Sum of SOV across all prompts in this topic"}';
COMMENT ON COLUMN v_topic_metric.sentiment_sum     IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Sum of sentiment scores across prompts"}';
COMMENT ON COLUMN v_topic_metric.presence_sum      IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Sum of presence scores across prompts"}';
COMMENT ON COLUMN v_topic_metric.position_sum      IS 'gravton: {"role":"metric","higher_is_better":false,"description":"Sum of position ranks (lower total = consistently earlier)"}';
COMMENT ON COLUMN v_topic_metric.prompt_ct         IS 'gravton: {"role":"metric","higher_is_better":null,"description":"Number of prompts scored in this topic"}';
COMMENT ON COLUMN v_topic_metric.social_mention_count    IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Social media mention count for this brand/topic"}';
COMMENT ON COLUMN v_topic_metric.social_sentiment_score  IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Social sentiment score, -1 to 1"}';
COMMENT ON COLUMN v_topic_metric.social_authority_score  IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Social authority score for this brand/topic"}';


-- ---------------------------------------------------------------------------
-- 4. v_brand_signal_metric  [DIRECT — domain_id on brand_signal_metrics]
--    Joins runs for the week_of timestamp.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_brand_signal_metric;

CREATE VIEW v_brand_signal_metric AS
SELECT
    bsm.id,
    bsm.domain_id,
    bsm.brand_name                   AS brand,
    bsm.brand_id,
    bsm.direction,
    bsm.signal,
    bsm.mention_count,
    ir.created_at                    AS week_of
FROM brand_signal_metrics bsm
JOIN runs ir                         ON ir.id  = bsm.run_id;

COMMENT ON VIEW   v_brand_signal_metric IS
  'gravton_table: {"description":"Canonical sentiment signals per brand aggregated per run — positive, negative, and neutral themes extracted from AI responses"}';
COMMENT ON COLUMN v_brand_signal_metric.domain_id     IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_brand_signal_metric.brand         IS 'gravton: {"role":"dimension","description":"Brand name"}';
COMMENT ON COLUMN v_brand_signal_metric.direction     IS 'gravton: {"role":"dimension","description":"Signal direction: positive, negative, or neutral"}';
COMMENT ON COLUMN v_brand_signal_metric.signal        IS 'gravton: {"role":"dimension","description":"Canonical signal phrase / theme text"}';
COMMENT ON COLUMN v_brand_signal_metric.week_of       IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_brand_signal_metric.mention_count IS 'gravton: {"role":"metric","higher_is_better":null,"description":"Number of response occurrences of this signal cluster"}';


-- ---------------------------------------------------------------------------
-- 5. v_technical_seo_scan  [DIRECT — domain_id on technical_seo_scan]
--    Completed scans only; partial/failed rows have null scores.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_technical_seo_scan;

CREATE VIEW v_technical_seo_scan AS
SELECT
    ts.id,
    ts.domain_id,
    ts.health_score,
    ts.bot_access_score,
    ts.rendering_score,
    ts.readability_score,
    ts.schema_score,
    ts.mobile_score,
    ts.speed_score,
    ts.redirect_score,
    ts.freshness_score,
    ts.pages_scanned,
    ts.p0_count,
    ts.p1_count,
    ts.p2_count,
    ts.blocked_discovery_bot_count,
    ts.js_dependent_page_count,
    ts.schema_mismatch_count,
    ts.coverage,
    ts.score_delta,
    ts.scanned_at                    AS week_of
FROM technical_seo_scan ts
WHERE ts.status = 'completed';

COMMENT ON VIEW   v_technical_seo_scan IS
  'gravton_table: {"description":"Completed technical SEO audit scans with health sub-scores per domain"}';
COMMENT ON COLUMN v_technical_seo_scan.domain_id                  IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_technical_seo_scan.week_of                    IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_technical_seo_scan.health_score               IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Overall SEO health score 0–100"}';
COMMENT ON COLUMN v_technical_seo_scan.bot_access_score           IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Bot/crawler access sub-score"}';
COMMENT ON COLUMN v_technical_seo_scan.rendering_score            IS 'gravton: {"role":"metric","higher_is_better":true,"description":"JS rendering sub-score"}';
COMMENT ON COLUMN v_technical_seo_scan.readability_score          IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Content readability sub-score"}';
COMMENT ON COLUMN v_technical_seo_scan.schema_score               IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Structured data schema sub-score"}';
COMMENT ON COLUMN v_technical_seo_scan.mobile_score               IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Mobile-friendliness sub-score"}';
COMMENT ON COLUMN v_technical_seo_scan.speed_score                IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Page speed sub-score"}';
COMMENT ON COLUMN v_technical_seo_scan.redirect_score             IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Redirect chain health sub-score"}';
COMMENT ON COLUMN v_technical_seo_scan.freshness_score            IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Content freshness sub-score"}';
COMMENT ON COLUMN v_technical_seo_scan.p0_count                   IS 'gravton: {"role":"metric","higher_is_better":false,"description":"Count of critical (P0) issues found"}';
COMMENT ON COLUMN v_technical_seo_scan.p1_count                   IS 'gravton: {"role":"metric","higher_is_better":false,"description":"Count of high-priority (P1) issues found"}';
COMMENT ON COLUMN v_technical_seo_scan.p2_count                   IS 'gravton: {"role":"metric","higher_is_better":false,"description":"Count of medium-priority (P2) issues found"}';
COMMENT ON COLUMN v_technical_seo_scan.score_delta                IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Health score change vs. previous scan"}';
COMMENT ON COLUMN v_technical_seo_scan.blocked_discovery_bot_count IS 'gravton: {"role":"metric","higher_is_better":false,"description":"Number of AI discovery bots blocked by robots.txt"}';


-- ---------------------------------------------------------------------------
-- 6. v_seo_finding  [JOIN — no domain_id on seo_finding]
--    seo_finding → technical_seo_scan.domain_id
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_seo_finding;

CREATE VIEW v_seo_finding AS
SELECT
    f.id,
    ts.domain_id,
    f.type,
    f.dimension,
    f.check_key,
    f.scope,
    f.status,
    f.impact,
    f.category,
    f.title,
    f.reason,
    f.fix_hint,
    f.rules_version,
    ts.scanned_at                    AS week_of
FROM seo_finding f
JOIN technical_seo_scan ts           ON ts.id  = f.scan_id;

COMMENT ON VIEW   v_seo_finding IS
  'gravton_table: {"description":"Individual SEO audit findings per domain, joined via scan → technical_seo_scan"}';
COMMENT ON COLUMN v_seo_finding.domain_id   IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_seo_finding.week_of     IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_seo_finding.dimension   IS 'gravton: {"role":"dimension","description":"Audit dimension: foundations, schema_health, readability, rendering, etc."}';
COMMENT ON COLUMN v_seo_finding.impact      IS 'gravton: {"role":"dimension","description":"Issue severity: critical, high, medium, quick_win"}';
COMMENT ON COLUMN v_seo_finding.status      IS 'gravton: {"role":"dimension","description":"Finding outcome: ok, warning, info, or fail"}';
COMMENT ON COLUMN v_seo_finding.scope       IS 'gravton: {"role":"dimension","description":"Whether this finding is site_wide or page-level"}';
COMMENT ON COLUMN v_seo_finding.type        IS 'gravton: {"role":"dimension","description":"Finding type key, e.g. canonical_mismatch or schema_broken_url:Organization"}';
COMMENT ON COLUMN v_seo_finding.category    IS 'gravton: {"role":"dimension","description":"Display category grouping this finding"}';


-- ---------------------------------------------------------------------------
-- 7. v_opportunity  [JOIN — no domain_id on opportunities]
--    opportunities → synthetic_prompt → intent_cluster.domain_id
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_opportunity;

CREATE VIEW v_opportunity AS
SELECT
    o.id,
    ic.domain_id,
    ic.label                         AS topic,
    sp.text                          AS prompt_text,
    o.model_id,
    o.checkpoint,
    o.priority,
    o.action_type,
    o.gap_title,
    o.opportunity_name,
    o.rationale,
    o.target_venue,
    o.intent,
    o.created_at                     AS week_of
FROM opportunities o
JOIN synthetic_prompt sp             ON sp.id  = o.prompt_id
JOIN intent_cluster ic               ON ic.id  = sp.cluster_id;

COMMENT ON VIEW   v_opportunity IS
  'gravton_table: {"description":"Content and optimization opportunities per domain, resolved to domain via prompt → intent cluster"}';
COMMENT ON COLUMN v_opportunity.domain_id        IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_opportunity.topic            IS 'gravton: {"role":"dimension","description":"Intent cluster / topic label"}';
COMMENT ON COLUMN v_opportunity.priority         IS 'gravton: {"role":"dimension","description":"Opportunity tier: Quick Win, Big Bet, or Filler"}';
COMMENT ON COLUMN v_opportunity.action_type      IS 'gravton: {"role":"dimension","description":"Action category: Create, Optimize, Community, or Outreach"}';
COMMENT ON COLUMN v_opportunity.checkpoint       IS 'gravton: {"role":"dimension","description":"The metric checkpoint that surfaced this opportunity"}';
COMMENT ON COLUMN v_opportunity.intent           IS 'gravton: {"role":"dimension","description":"Intent label for the opportunity cluster"}';
COMMENT ON COLUMN v_opportunity.target_venue     IS 'gravton: {"role":"dimension","description":"Target channel or venue for the action"}';
COMMENT ON COLUMN v_opportunity.week_of          IS 'gravton: {"role":"time"}';


-- ---------------------------------------------------------------------------
-- 8. v_topic_metric_unbranded  [DIRECT — domain_id on topic_metrics_unbranded]
--    Same shape as v_topic_metric but sourced from unbranded query runs.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_topic_metric_unbranded;

CREATE VIEW v_topic_metric_unbranded AS
SELECT
    tm.id,
    tm.domain_id,
    ic.label                         AS topic,
    co.name                          AS brand,
    co.is_focal,
    ir.created_at                    AS week_of,
    tm.sov_sum,
    tm.sentiment_sum,
    tm.presence_sum,
    tm.position_sum,
    tm.prompt_ct,
    tm.sov_non_null_ct,
    tm.sentiment_non_null_ct,
    tm.presence_non_null_ct,
    tm.position_non_null_ct,
    tm.social_mention_count,
    tm.social_sentiment_score,
    tm.social_authority_score
FROM topic_metrics_unbranded tm
JOIN intent_cluster ic               ON ic.id  = tm.cluster_id
JOIN competitor co                   ON co.id  = tm.brand_id
JOIN runs ir                         ON ir.id  = tm.run_id;

COMMENT ON VIEW   v_topic_metric_unbranded IS
  'gravton_table: {"description":"Aggregated AI visibility metrics per brand per topic for unbranded query runs"}';
COMMENT ON COLUMN v_topic_metric_unbranded.domain_id     IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_topic_metric_unbranded.topic         IS 'gravton: {"role":"dimension","description":"Intent cluster / topic label"}';
COMMENT ON COLUMN v_topic_metric_unbranded.brand         IS 'gravton: {"role":"dimension","description":"Brand name"}';
COMMENT ON COLUMN v_topic_metric_unbranded.is_focal      IS 'gravton: {"role":"flag","description":"True when this brand is the focal brand for the domain"}';
COMMENT ON COLUMN v_topic_metric_unbranded.week_of       IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_topic_metric_unbranded.sov_sum       IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Sum of SOV across unbranded prompts in this topic"}';
COMMENT ON COLUMN v_topic_metric_unbranded.sentiment_sum IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Sum of sentiment scores across unbranded prompts"}';
COMMENT ON COLUMN v_topic_metric_unbranded.presence_sum  IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Sum of presence scores across unbranded prompts"}';


-- ---------------------------------------------------------------------------
-- 10. v_gsc_query  [JOIN — no domain_id on gsc_query]
--    gsc_query.property_id → gsc_property.domain_id  (API source)
--    gsc_query.upload_id   → gsc_upload.domain_id    (CSV source)
--    One of the two FKs is always set; COALESCE picks whichever is non-null.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_gsc_query;

CREATE VIEW v_gsc_query AS
SELECT
    q.id,
    COALESCE(p.domain_id, u.domain_id) AS domain_id,
    q.query,
    q.clicks,
    q.impressions,
    q.ctr,
    q.position,
    q.source,
    q.start_date                         AS week_of
FROM gsc_query q
LEFT JOIN gsc_property p                 ON p.id = q.property_id
LEFT JOIN gsc_upload   u                 ON u.id = q.upload_id
WHERE COALESCE(p.domain_id, u.domain_id) IS NOT NULL;

COMMENT ON VIEW   v_gsc_query IS
  'gravton_table: {"description":"Google Search Console query-level search performance (clicks, impressions, CTR, position) per domain"}';
COMMENT ON COLUMN v_gsc_query.domain_id    IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_gsc_query.query        IS 'gravton: {"role":"dimension","description":"Search query string"}';
COMMENT ON COLUMN v_gsc_query.source       IS 'gravton: {"role":"dimension","description":"Data source: api or csv"}';
COMMENT ON COLUMN v_gsc_query.week_of      IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_gsc_query.clicks       IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Click count for this query in the date range"}';
COMMENT ON COLUMN v_gsc_query.impressions  IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Impression count for this query"}';
COMMENT ON COLUMN v_gsc_query.ctr          IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Click-through rate (0–1)"}';
COMMENT ON COLUMN v_gsc_query.position     IS 'gravton: {"role":"metric","higher_is_better":false,"description":"Average search position (lower = better)"}';


-- ---------------------------------------------------------------------------
-- 11. v_gsc_page  [JOIN — no domain_id on gsc_page]
--    Same COALESCE pattern as v_gsc_query.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_gsc_page;

CREATE VIEW v_gsc_page AS
SELECT
    pg.id,
    COALESCE(p.domain_id, u.domain_id)  AS domain_id,
    pg.page_url,
    pg.clicks,
    pg.impressions,
    pg.ctr,
    pg.position,
    pg.source,
    pg.start_date                         AS week_of
FROM gsc_page pg
LEFT JOIN gsc_property p                  ON p.id = pg.property_id
LEFT JOIN gsc_upload   u                  ON u.id = pg.upload_id
WHERE COALESCE(p.domain_id, u.domain_id) IS NOT NULL;

COMMENT ON VIEW   v_gsc_page IS
  'gravton_table: {"description":"Google Search Console page-level search performance (clicks, impressions, CTR, position) per domain"}';
COMMENT ON COLUMN v_gsc_page.domain_id    IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_gsc_page.page_url     IS 'gravton: {"role":"dimension","description":"Page URL"}';
COMMENT ON COLUMN v_gsc_page.source       IS 'gravton: {"role":"dimension","description":"Data source: api or csv"}';
COMMENT ON COLUMN v_gsc_page.week_of      IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_gsc_page.clicks       IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Click count for this page in the date range"}';
COMMENT ON COLUMN v_gsc_page.impressions  IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Impression count for this page"}';
COMMENT ON COLUMN v_gsc_page.ctr          IS 'gravton: {"role":"metric","higher_is_better":true,"description":"Click-through rate (0–1)"}';
COMMENT ON COLUMN v_gsc_page.position     IS 'gravton: {"role":"metric","higher_is_better":false,"description":"Average search position (lower = better)"}';
