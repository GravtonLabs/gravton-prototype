# Connecting to Your Existing Database

I can't reach your database from this session — the sandbox's network is
locked to a fixed allowlist of package/API domains, no arbitrary DB
connections, even to your own infrastructure. Everything below is designed
to be run **by you**, against your own connection string, in your own
environment. Nothing here requires giving me credentials.

## Step 1 — Audit before you tag anything

Run the read-only audit script against your real database first, before
writing a single `COMMENT ON`:

```bash
export GRAVTON_DSN="postgresql://user:password@host:5432/dbname"
python3 audit_schema.py                                    # everything
python3 audit_schema.py insight_metrics_promptmetric citations_promptcitation   # scoped
```

It only issues `SELECT`/`information_schema` queries — safe against
production, though a read replica is still preferable since the heuristic
fallback runs a `COUNT(DISTINCT ...)` per untagged text column.

**Scope it.** Your real schema (per what you shared earlier) has ~18 Django
apps and includes things like `auth_user`, `django_session`, and
`feature_flags_*` that have nothing to do with investigations. Pass
specific table names rather than auditing everything — faster, and the
output is actually readable.

It writes `tagging_starter.sql` — review and fill in the `TODO`s, then:

```bash
psql $GRAVTON_DSN -f tagging_starter.sql
```

## Step 2 — the part that needs a human: your schema is normalized

Here's the honest catch, and it's real: `PromptMetric` (your prompt-level
scores table) doesn't carry `domain_id` directly — it reaches a `Domain`
through `prompt → IntentCluster → Domain`. `PromptCitation` is better, it
has a direct `source_domain` FK. This project's query engine currently
does single-table filtering only (no joins — see the limitations note in
`SETUP.md` §7), so a table like `PromptMetric` needs a **view** that
flattens the join before it's investigable, rather than being tagged
as-is.

This is a good idea structurally anyway — it keeps the investigation layer
reading from a stable reporting surface instead of your live OLTP tables.

**Two worked examples, based on the fields you described earlier.** Table
and FK-column names below follow Django's default conventions
(`app_modelname`, `fieldname_id`) — **verify against your real schema with
`\d tablename` in psql before running**, since a custom `db_table` or
`AppConfig.label` would change these:

```sql
-- PromptCitation already has a direct domain FK — no join needed, but a
-- view still lets you resolve the domain's natural key if you want one
-- more human-readable than a raw ID.
CREATE VIEW v_prompt_citation AS
SELECT
    pc.id,
    pc.source_domain_id AS domain_id,
    co.name              AS brand,
    pc.page_url,
    pc.citation_mass_weight,
    pc.damping_factor,
    pc.created_at        AS week_of      -- adjust to your real timestamp column
FROM citations_promptcitation pc
LEFT JOIN brandkit_competitor co ON co.id = pc.aggregate_brand_id;

COMMENT ON TABLE v_prompt_citation IS
  'gravton_table: {"description":"URL citations from AI responses, attributed to a brand"}';
COMMENT ON COLUMN v_prompt_citation.domain_id  IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_prompt_citation.brand      IS 'gravton: {"role":"dimension","description":"Brand name"}';
COMMENT ON COLUMN v_prompt_citation.week_of    IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_prompt_citation.citation_mass_weight IS
  'gravton: {"role":"metric","higher_is_better":true,"description":"Weighted importance of this citation"}';


-- PromptMetric needs the join: prompt -> intent_cluster -> domain.
CREATE VIEW v_prompt_metric AS
SELECT
    pm.id,
    ic.domain_id,
    ic.label              AS topic,
    pm.brand_id            AS brand,          -- confirm: is this a Competitor FK or a raw code?
    ir.created_at          AS week_of,        -- adjust to your real InsightRun timestamp
    pm.sov,
    pm.visibility_score,
    pm.sentiment_score,
    pm.consistency_score,
    pm.position_rank
FROM insight_metrics_promptmetric pm
JOIN intent_core_syntheticprompt sp ON sp.id = pm.prompt_id
JOIN intent_core_intentcluster ic   ON ic.id = sp.cluster_id
JOIN insight_metrics_insightrun ir  ON ir.id = pm.run_id;

COMMENT ON TABLE v_prompt_metric IS
  'gravton_table: {"description":"Weekly AI visibility metrics per brand per prompt"}';
COMMENT ON COLUMN v_prompt_metric.domain_id IS 'gravton: {"role":"identifier"}';
COMMENT ON COLUMN v_prompt_metric.topic     IS 'gravton: {"role":"dimension","description":"Intent cluster / topic"}';
COMMENT ON COLUMN v_prompt_metric.brand     IS 'gravton: {"role":"dimension","description":"Brand identifier"}';
COMMENT ON COLUMN v_prompt_metric.week_of   IS 'gravton: {"role":"time"}';
COMMENT ON COLUMN v_prompt_metric.sov IS
  'gravton: {"role":"metric","higher_is_better":true,"description":"Share of Voice"}';
COMMENT ON COLUMN v_prompt_metric.sentiment_score IS
  'gravton: {"role":"metric","higher_is_better":true,"description":"Sentiment, -1 to 1"}';
```

Postgres views support `COMMENT ON COLUMN` exactly like tables, so
`audit_schema.py` and `PostgresSchemaIntrospector` work on them unchanged
— just pass the view names when you scope the audit.

**Repeat this pattern** for `TopicMetric` (join through `IntentCluster` to
`Domain` directly, no `SyntheticPrompt` hop needed), `BrandSignalMetric`,
`TechnicalSeoScan`/`Finding` (probably already flat per-domain, check with
`\d`), and `Opportunity`. I'd start with just `v_prompt_citation` and
`v_prompt_metric` — that's already enough for the flagship "why did SOV
change" investigation — and add the rest once that's working end to end.

## Step 3 — point the engine at it

```bash
export GRAVTON_DSN="postgresql://user:password@host:5432/dbname"
```

```python
from postgres_backend import create_postgres_engine, PostgresSchemaIntrospector

# Scope discovery to your views/tables explicitly — don't let it wander
# into auth/session/feature-flag tables.
introspector = PostgresSchemaIntrospector(DSN)
schema = await introspector.discover(include_tables=[
    "v_prompt_citation", "v_prompt_metric",  # add more as you tag them
])
```

then wire it through `create_postgres_engine` / `InvestigationEngine` as
in `run_with_postgres.py`, swapping in your real `domain_id` values (from
your `brandkit_domain` table) in place of `domain_zoho_crm`.

## Checklist

- [ ] Ran `audit_schema.py` scoped to specific tables, not the whole DB
- [ ] Confirmed real table/column names with `\d` before writing any view
- [ ] Created reporting views for anything without a direct `domain_id`
- [ ] Tagged the views (`gravton_table:` + `gravton:` comments)
- [ ] Re-ran the audit to confirm 0 `NEEDS REVIEW` on anything load-bearing
- [ ] Passed `include_tables=[...]` explicitly when building the engine