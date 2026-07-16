"""
Gravton Investigation Engine — Prototype v2 (Schema-Driven / Generic)
======================================================================

v1 problem: every metric, table, and comparison ("Salesforce", "SOV",
"citation_distribution"...) was hardcoded into a Skill class or an
EvidenceNeed enum. Adding a new column to the real Postgres schema meant
writing new Python.

v2 fix: nothing about a specific metric, table, or brand name is hardcoded
anywhere in the engine. Instead:

  1. A SchemaRegistry describes tables/fields generically: which fields
     are metrics, which are dimensions (things you group/filter by), which
     are time, which are text evidence. This is metadata, not code.

  2. A GenericQueryEngine can compute a trend, a distribution, or a raw
     lookup for ANY registered table/field, because it only ever consumes
     schema metadata (field names + roles), never a hardcoded field name.

  3. An AnomalyDetector + CorrelationEngine work over ANY metric: they
     detect meaningful week-over-week change on any numeric column, then
     scan every OTHER registered table for rows that share a dimension
     value (e.g. the same brand) and time window — i.e. they *discover*
     corroborating evidence structurally, rather than a Skill author
     manually deciding "DeepDive also needs brand_signals + technical
     findings".

  4. The Planner resolves a free-text question against the live catalog
     (metric names/descriptions, dimension values actually present in the
     data) instead of `if "decline" in question: return DeepDiveSkill()`.

Net effect: to make a brand-new metric investigable, you REGISTER it
(one TableSpec, or in production one Django model with a metric-tagged
field) — you do not write a new Skill, a new EvidenceNeed, or a new
repository method. The bottom of this file proves it: a brand-new table
is registered at runtime with zero engine changes, and the engine
investigates it correctly.

Production integration point: see `introspect_django_apps()` near the
bottom of the SchemaRegistry section — that's where this would plug into
your real Django app registry.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

import anthropic as _anthropic

from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gravton")


def now() -> datetime:
    return datetime.now(timezone.utc)


# ===========================================================================
# 1. SCHEMA LAYER — this replaces every hardcoded EvidenceNeed / Skill.
#    A table is described once, declaratively. That description is the
#    ONLY thing the rest of the engine ever consults.
# ===========================================================================


class FieldSpec(BaseModel):
    name: str
    dtype: str  # "float" | "int" | "str" | "bool" | "datetime"
    role: str
    # roles:
    #   "metric"    -> numeric, trackable over time, anomaly-detectable
    #   "dimension" -> a thing you group/filter by (brand, page_url, model_id)
    #   "category"  -> a small-cardinality field good for distributions
    #                  (e.g. attribution_type: owned/community/earned)
    #   "weight"    -> numeric weight used when aggregating a category
    #   "time"      -> the timestamp a row belongs to
    #   "identifier"-> primary/foreign key, not analytically interesting
    #   "flag"      -> boolean marker (e.g. is_focal)
    #   "text"      -> free text that can be surfaced as evidence
    higher_is_better: Optional[bool] = None  # only meaningful for metrics
    description: str = ""


class TableSpec(BaseModel):
    name: str
    description: str
    fields: list[FieldSpec]

    def field(self, name: str) -> Optional[FieldSpec]:
        return next((f for f in self.fields if f.name == name), None)

    def has_field(self, name: str) -> bool:
        return self.field(name) is not None

    def metrics(self) -> list[FieldSpec]:
        return [f for f in self.fields if f.role == "metric"]

    def dimensions(self) -> list[FieldSpec]:
        return [f for f in self.fields if f.role in ("dimension", "category")]

    def time_field(self) -> Optional[str]:
        f = next((f for f in self.fields if f.role == "time"), None)
        return f.name if f else None

    def text_fields(self) -> list[FieldSpec]:
        return [f for f in self.fields if f.role == "text"]

    def flag_fields(self) -> list[FieldSpec]:
        return [f for f in self.fields if f.role == "flag"]


STOPWORDS = {
    "the", "a", "an", "is", "are", "this", "our", "we", "for", "on", "in",
    "of", "to", "did", "what", "why", "how", "and", "it", "was", "were",
    "does", "do", "us", "that", "with", "about", "at",
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - STOPWORDS


def _overlap_score(question: str, *texts: str) -> int:
    q = _tokens(question)
    t = set()
    for text in texts:
        t |= _tokens(text)
    return len(q & t)


class SchemaRegistry:
    """The catalog. Register a TableSpec once and every part of the engine
    (retrieval, anomaly detection, correlation, planning) can use it
    without any further code changes."""

    def __init__(self) -> None:
        self.tables: dict[str, TableSpec] = {}

    def register(self, spec: TableSpec) -> None:
        self.tables[spec.name] = spec
        log.info(f"[SchemaRegistry] registered table '{spec.name}' "
                  f"({len(spec.metrics())} metric field(s), {len(spec.dimensions())} dimension field(s))")

    def all_metrics(self) -> list[tuple[str, FieldSpec]]:
        return [(t.name, f) for t in self.tables.values() for f in t.metrics()]

    def best_matching_metric(self, question: str) -> Optional[tuple[str, FieldSpec, int]]:
        scored = [
            (table.name, f, _overlap_score(question, f.name, f.description, table.description))
            for table in self.tables.values()
            for f in table.metrics()
        ]
        scored = [s for s in scored if s[2] > 0]
        if not scored:
            return None
        scored.sort(key=lambda s: s[2], reverse=True)
        return scored[0]

    def best_matching_table(self, question: str) -> Optional[tuple[str, int]]:
        scored = [(t.name, _overlap_score(question, t.name, t.description)) for t in self.tables.values()]
        scored = [s for s in scored if s[1] > 0]
        if not scored:
            return None
        scored.sort(key=lambda s: s[1], reverse=True)
        return scored[0]

    def tables_sharing_dimension(self, dim_name: str, exclude: str = "") -> list[str]:
        """Which OTHER registered tables can serve as corroborating
        evidence for an anomaly on this dimension? Answered structurally:
        any table that has both this dimension field and a time field."""
        return [
            t.name for t in self.tables.values()
            if t.name != exclude and t.has_field(dim_name) and t.time_field()
        ]


def introspect_django_apps() -> "SchemaRegistry":
    """
    PRODUCTION INTEGRATION POINT (not runnable here — no Django in this
    sandbox). This is how a real engineer wires this prototype's schema
    layer to the actual Gravton Postgres schema with zero manual curation:

        from django.apps import apps
        registry = SchemaRegistry()
        for model in apps.get_models():
            fields = []
            for f in model._meta.get_fields():
                # Opt-in convention: any Django field can carry a
                # `gravton_metric_meta` kwarg, e.g.:
                #   visibility_score = models.FloatField(
                #       gravton_metric_meta={"role": "metric",
                #                            "higher_is_better": True,
                #                            "description": "Composite AI visibility score"})
                meta = getattr(f, "gravton_metric_meta", None)
                if meta:
                    fields.append(FieldSpec(name=f.name, dtype=meta.get("dtype", "float"),
                                             role=meta["role"],
                                             higher_is_better=meta.get("higher_is_better"),
                                             description=meta.get("description", "")))
            if fields:
                registry.register(TableSpec(name=model._meta.db_table,
                                             description=model.__doc__ or model.__name__,
                                             fields=fields))
        return registry

    A data engineer adding a brand-new column to PromptMetric, or a whole
    new app (say, `youtube_signals`), tags the relevant fields with
    `gravton_metric_meta` at model-definition time. The next time this
    registry is built (e.g. at Django app-ready time, cached), the new
    metric is automatically: queryable, trend-able, anomaly-detectable,
    and cross-correlatable with every existing table. No planner, skill,
    or repository code is touched.
    """
    raise NotImplementedError("Prototype runs on the in-memory DataStore below; see docstring.")


# ===========================================================================
# 2. GENERIC DATA STORE & QUERY ENGINE
#    Stands in for Postgres. Rows are plain dicts. Critically, there is
#    ONE query method, driven entirely by a QuerySpec + the schema — not
#    one hardcoded repository method per table like v1 had.
# ===========================================================================


class DataStore:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        self.tables[table].extend(rows)

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables.get(table, [])


def _row_matches(row: dict, filters: dict[str, Any]) -> bool:
    for k, v in filters.items():
        if v is None:
            continue
        if row.get(k) != v:
            return False
    return True


class QuerySpec(BaseModel):
    table: str
    kind: str  # "timeseries" | "distribution" | "raw" | "latest"
    metric: Optional[str] = None
    group_by: list[str] = Field(default_factory=list)
    category_field: Optional[str] = None
    weight_field: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    since: Optional[datetime] = None

    def cache_key(self) -> str:
        filt = "|".join(f"{k}={v}" for k, v in sorted(self.filters.items()))
        grp = ",".join(self.group_by)
        return f"{self.table}:{self.kind}:{self.metric}:{grp}:{filt}:{self.since}"


class GenericQueryEngine:
    """The entire retrieval layer for ANY table/metric. No per-table
    methods. This is what makes new metrics 'free' to investigate."""

    def __init__(self, store: DataStore, schema: SchemaRegistry) -> None:
        self.store = store
        self.schema = schema

    async def run(self, spec: QuerySpec) -> list[dict[str, Any]]:
        await asyncio.sleep(0.03)  # simulate query latency
        table_spec = self.schema.tables[spec.table]
        rows = [r for r in self.store.rows(spec.table) if _row_matches(r, spec.filters)]

        time_field = table_spec.time_field()
        if spec.since and time_field:
            rows = [r for r in rows if r[time_field] >= spec.since]

        if spec.kind == "timeseries":
            return self._group_and_aggregate(rows, spec.metric, spec.group_by, time_field)
        if spec.kind == "distribution":
            return self._distribution(rows, spec.category_field, spec.weight_field)
        if spec.kind == "latest":
            if time_field:
                rows = sorted(rows, key=lambda r: r[time_field])
            return rows[-1:]
        return rows  # "raw"

    @staticmethod
    def _group_and_aggregate(rows, metric, group_by, time_field) -> list[dict[str, Any]]:
        buckets: dict[tuple, list[float]] = defaultdict(list)
        for r in rows:
            key = tuple(r.get(g) for g in group_by) + (r.get(time_field),)
            val = r.get(metric)
            if val is not None:
                buckets[key].append(val)
        out = []
        for key, values in buckets.items():
            *group_vals, t = key
            entry = dict(zip(group_by, group_vals))
            entry[time_field or "time"] = t
            entry["value"] = sum(values) / len(values)
            out.append(entry)
        out.sort(key=lambda e: e.get(time_field or "time") or 0)
        return out

    @staticmethod
    def _distribution(rows, category_field, weight_field) -> list[dict[str, Any]]:
        totals: dict[Any, float] = defaultdict(float)
        for r in rows:
            w = r.get(weight_field, 1.0) if weight_field else 1.0
            totals[r.get(category_field)] += w
        total = sum(totals.values()) or 1.0
        return [{"category": k, "share": v / total} for k, v in totals.items()]


async def resolve_focal_value(
    schema: SchemaRegistry, retrieval: "RetrievalEngine", pack: "EvidencePack",
    trace: "InvestigationTrace", dimension: str, domain_id: Optional[str] = None,
) -> Optional[Any]:
    """Generic version of 'which brand is the client's own?' — scans any
    registered table that has BOTH this dimension field and a 'flag'-role
    field (e.g. is_focal), and returns the dimension value on the flagged
    row. Mirrors brandkit.Competitor.is_focal without hardcoding it.
    Backend-agnostic: goes through the same RetrievalEngine (and therefore
    the same cache/Evidence Pack) as every other lookup, so it works
    identically whether the query engine underneath is in-memory or
    Postgres."""
    for spec in schema.tables.values():
        if spec.has_field(dimension) and spec.flag_fields():
            flag_name = spec.flag_fields()[0].name
            filters: dict[str, Any] = {flag_name: True}
            if domain_id and spec.has_field("domain_id"):
                filters["domain_id"] = domain_id
            rows = await retrieval.fetch(QuerySpec(table=spec.name, kind="raw", filters=filters), pack, trace)
            if rows:
                return rows[0].get(dimension)
    return None


class DimensionValueIndex:
    """A small, refreshable index of literal values seen in dimension
    fields, used only to spot a named entity (a brand, a page, a model)
    in free text. Deliberately built from small reference tables only
    (e.g. the list of tracked brands) — never by scanning large fact
    tables — so it's cheap to keep fully in memory and refresh on a
    schedule, regardless of which backend serves the actual queries."""

    def __init__(self) -> None:
        self._values: dict[str, set[str]] = defaultdict(set)

    def add(self, field_name: str, values: list[Any]) -> None:
        self._values[field_name].update(v for v in values if isinstance(v, str) and v)

    def find_in_text(self, text: str) -> dict[str, Any]:
        text_lower = text.lower()
        for field_name, values in self._values.items():
            for v in values:
                if v.lower() in text_lower:
                    return {field_name: v}
        return {}


def build_dimension_index_from_store(schema: SchemaRegistry, store: "DataStore") -> DimensionValueIndex:
    """In-memory convenience builder — used by the prototype/demo path."""
    index = DimensionValueIndex()
    for table in schema.tables.values():
        for dim in table.dimensions():
            index.add(dim.name, [r.get(dim.name) for r in store.rows(table.name)])
    return index


# ===========================================================================
# 3. CACHE + EVIDENCE PACK (generic — one dict, not a dozen hardcoded
#    fields like v1's EvidencePack.trends / .citations / .brand_signals...)
# ===========================================================================


class TTLCache:
    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)


class EvidencePack(BaseModel):
    """Generic: results keyed by QuerySpec.cache_key(). A brand-new table
    automatically has somewhere to live — no schema migration of this
    class required when a new metric is registered."""

    results: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    fulfilled: set[str] = Field(default_factory=set)

    model_config = {"arbitrary_types_allowed": True}

    def has(self, spec: QuerySpec) -> bool:
        return spec.cache_key() in self.fulfilled

    def put(self, spec: QuerySpec, data: list[dict[str, Any]]) -> None:
        self.results[spec.cache_key()] = data
        self.fulfilled.add(spec.cache_key())

    def get(self, spec: QuerySpec) -> list[dict[str, Any]]:
        return self.results.get(spec.cache_key(), [])


@dataclass
class InvestigationTrace:
    question: str
    plan_kind: str = ""
    queries: int = 0
    cache_hits: int = 0
    evidence_reused: int = 0
    confidence_progression: list[float] = dc_field(default_factory=list)
    duration_ms: float = 0.0

    def render(self) -> str:
        return (
            f"\n--- InvestigationTrace ---\n"
            f"question    : {self.question}\n"
            f"plan_kind   : {self.plan_kind}\n"
            f"queries     : {self.queries}\n"
            f"cache_hits  : {self.cache_hits}\n"
            f"evidence_reused: {self.evidence_reused}\n"
            f"confidence  : {[round(c,2) for c in self.confidence_progression]}\n"
            f"duration_ms : {round(self.duration_ms, 1)}\n"
            f"---------------------------\n"
        )


class RetrievalEngine:
    """Generic retrieval: check the Evidence Pack, then the TTL cache,
    then the GenericQueryEngine — in that order — for ANY QuerySpec."""

    def __init__(self, query_engine: GenericQueryEngine, cache: TTLCache) -> None:
        self.query_engine = query_engine
        self.cache = cache

    async def fetch(self, spec: QuerySpec, pack: EvidencePack, trace: InvestigationTrace) -> list[dict[str, Any]]:
        if pack.has(spec):
            trace.evidence_reused += 1
            log.info(f"  evidence REUSED: {spec.table}.{spec.metric or spec.category_field}")
            return pack.get(spec)

        cached = self.cache.get(spec.cache_key())
        if cached is not None:
            trace.cache_hits += 1
            log.info(f"  cache HIT: {spec.table}.{spec.metric or spec.category_field}")
            pack.put(spec, cached)
            return cached

        trace.queries += 1
        log.info(f"  query: table={spec.table} kind={spec.kind} metric={spec.metric} group_by={spec.group_by}")
        data = await self.query_engine.run(spec)
        self.cache.set(spec.cache_key(), data)
        pack.put(spec, data)
        return data


# ===========================================================================
# 4. GENERIC ANOMALY DETECTION + CORRELATION
#    This replaces every hand-written Skill.build_hypotheses() from v1.
#    It works over ANY metric because it only consumes schema roles
#    (metric / dimension / time), never a specific field name.
# ===========================================================================


@dataclass
class Anomaly:
    table: str
    metric: str
    metric_description: str
    higher_is_better: Optional[bool]
    dimension_value: dict[str, Any]
    baseline: float
    current: float
    pct_change: float
    direction: str  # "increase" | "decrease"
    window: tuple[Any, Any]

    @property
    def is_unfavorable(self) -> bool:
        if self.higher_is_better is None:
            return False
        if self.higher_is_better:
            return self.direction == "decrease"
        return self.direction == "increase"


class AnomalyDetector:
    def __init__(self, threshold_pct: float = 0.12) -> None:
        self.threshold_pct = threshold_pct

    def detect(
        self,
        series: list[dict[str, Any]],
        dim_keys: list[str],
        table: str,
        metric_spec: FieldSpec,
        time_field: Optional[str],
    ) -> list[Anomaly]:
        grouped: dict[tuple, list[dict]] = defaultdict(list)
        for row in series:
            key = tuple(row.get(d) for d in dim_keys)
            grouped[key].append(row)

        anomalies = []
        for key, pts in grouped.items():
            pts_sorted = sorted(pts, key=lambda r: r.get(time_field or "time") or 0)
            if len(pts_sorted) < 2:
                continue
            baseline, current = pts_sorted[0]["value"], pts_sorted[-1]["value"]
            if baseline is None or current is None or baseline == 0:
                continue
            pct_change = (current - baseline) / abs(baseline)
            if abs(pct_change) >= self.threshold_pct:
                anomalies.append(Anomaly(
                    table=table,
                    metric=metric_spec.name,
                    metric_description=metric_spec.description or metric_spec.name,
                    higher_is_better=metric_spec.higher_is_better,
                    dimension_value=dict(zip(dim_keys, key)),
                    baseline=baseline,
                    current=current,
                    pct_change=pct_change,
                    direction="increase" if pct_change > 0 else "decrease",
                    window=(pts_sorted[0].get(time_field or "time"), pts_sorted[-1].get(time_field or "time")),
                ))
        anomalies.sort(key=lambda a: abs(a.pct_change), reverse=True)
        return anomalies


class CorrelationEngine:
    """Given an anomaly on some dimension value (e.g. brand='Zoho CRM'),
    structurally discovers OTHER registered tables that share that
    dimension and a time window, and pulls their rows as candidate
    corroborating evidence. No table is special-cased — a brand-new table
    registered tomorrow is automatically eligible."""

    def __init__(self, schema: SchemaRegistry, retrieval: RetrievalEngine) -> None:
        self.schema = schema
        self.retrieval = retrieval

    async def find_corroboration(
        self, anomaly: Anomaly, domain_id: str, pack: EvidencePack, trace: InvestigationTrace,
    ) -> list[dict[str, Any]]:
        corroboration = []
        for dim_name, dim_value in anomaly.dimension_value.items():
            candidate_tables = self.schema.tables_sharing_dimension(dim_name, exclude=anomaly.table)
            for table_name in candidate_tables:
                table_spec = self.schema.tables[table_name]
                spec = QuerySpec(
                    table=table_name,
                    kind="raw",
                    filters={"domain_id": domain_id, dim_name: dim_value},
                    since=anomaly.window[0],
                )
                rows = await self.retrieval.fetch(spec, pack, trace)
                if rows:
                    corroboration.append({
                        "table": table_name,
                        "description": table_spec.description,
                        "text_fields": [f.name for f in table_spec.text_fields()],
                        "rows": rows,
                    })
        return corroboration


# ===========================================================================
# 5. LLM CLIENT ABSTRACTION (unchanged shape from v1 — swap for real
#    OpenAI/Anthropic client without touching Planner/Reasoner)
# ===========================================================================


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str: ...


class MockLLMClient(LLMClient):
    async def complete(self, system: str, user: str) -> str:
        await asyncio.sleep(0.02)
        return "[mock completion]"


class AnthropicLLMClient(LLMClient):
    """LLMClient backed by the Anthropic Messages API.

    Args:
        model:   Claude model ID. Defaults to claude-sonnet-4-6.
        max_tokens: Upper bound on response tokens.
        api_key: Anthropic API key. Reads ANTHROPIC_API_KEY env var when omitted.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 2048,
        api_key: Optional[str] = None,
    ) -> None:
        import os
        self._client = _anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
        )
        self._model = model
        self._max_tokens = max_tokens

    async def complete(self, system: str, user: str) -> str:
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text


# ===========================================================================
# 6. PLANNER — catalog-driven, not keyword-to-Skill-class mapping.
#    Resolves: (a) does the question name a known metric? (b) does it name
#    a known dimension value (a brand, a page, a model)? (c) if no metric
#    matches, does it match a table description (e.g. "technical issues")
#    for a raw evidence lookup? This is what makes the Planner automatically
#    aware of new tables/metrics: it just iterates schema.tables.
# ===========================================================================


class InvestigationPlan(BaseModel):
    kind: str  # "definition" | "investigate_change" | "raw_lookup" | "general_qa"
    domain_id: Union[str, int]
    table: Optional[str] = None
    metric: Optional[str] = None
    dimension_filter: dict[str, Any] = Field(default_factory=dict)


class InvestigationPlanner:
    def __init__(self, llm: LLMClient, schema: SchemaRegistry, dimension_index: Optional[DimensionValueIndex] = None) -> None:
        self.llm = llm
        self.schema = schema
        self.dimension_index = dimension_index or DimensionValueIndex()

    def _find_named_dimension_value(self, question: str) -> dict[str, Any]:
        """Looks up the (small, pre-built) DimensionValueIndex — if the
        question literally names a known brand, page, or model, use it as
        a filter. Fully data-driven: no hardcoded brand list, and no need
        to scan large fact tables to answer this."""
        return self.dimension_index.find_in_text(question)

    async def plan(self, question: str, domain_id: str) -> InvestigationPlan:
        await self.llm.complete("planner-system-prompt", question)  # would carry live catalog as context in prod

        is_definition_ask = bool(re.search(r"\bwhat is\b|\bexplain\b", question.lower()))
        best_metric = self.schema.best_matching_metric(question)

        if is_definition_ask and best_metric:
            table, field_spec, _ = best_metric
            return InvestigationPlan(kind="definition", domain_id=domain_id, table=table, metric=field_spec.name)

        dim_filter = self._find_named_dimension_value(question)
        best_table = self.schema.best_matching_table(question)

        metric_score = best_metric[2] if best_metric else -1
        table_score = best_table[1] if best_table else -1

        if best_metric and metric_score >= table_score:
            table, field_spec, score = best_metric
            log.info(f"[Planner] matched metric '{field_spec.name}' on table '{table}' (score={score}) dim_filter={dim_filter}")
            return InvestigationPlan(kind="investigate_change", domain_id=domain_id, table=table, metric=field_spec.name, dimension_filter=dim_filter)

        if best_table:
            table, score = best_table
            log.info(f"[Planner] table description outscored any metric match; raw lookup on '{table}' (score={score})")
            return InvestigationPlan(kind="raw_lookup", domain_id=domain_id, table=table, dimension_filter=dim_filter)

        log.info("[Planner] nothing matched the catalog; general_qa fallback")
        return InvestigationPlan(kind="general_qa", domain_id=domain_id)


# ===========================================================================
# 7. HYPOTHESIS ENGINE — replaces every hand-written Skill.build_hypotheses.
#    Works identically for a metric that existed at design time and one
#    registered five minutes ago.
# ===========================================================================


class Hypothesis(BaseModel):
    statement: str
    confidence: float
    supporting_evidence: list[str] = Field(default_factory=list)


class HypothesisEngine:
    def __init__(self, schema: SchemaRegistry, retrieval: RetrievalEngine, correlator: CorrelationEngine) -> None:
        self.schema = schema
        self.retrieval = retrieval
        self.correlator = correlator
        self.detector = AnomalyDetector()

    async def investigate(self, plan: InvestigationPlan, pack: EvidencePack, trace: InvestigationTrace) -> list[Hypothesis]:
        table_spec = self.schema.tables[plan.table]
        field_spec = table_spec.field(plan.metric)
        dim_keys = [f.name for f in table_spec.dimensions()]
        time_field = table_spec.time_field()

        spec = QuerySpec(
            table=plan.table, kind="timeseries", metric=plan.metric,
            group_by=dim_keys, filters={"domain_id": plan.domain_id},
        )
        series = await self.retrieval.fetch(spec, pack, trace)

        anomalies = self.detector.detect(series, dim_keys, plan.table, field_spec, time_field)
        if not anomalies:
            return []

        # Prioritize: an anomaly matching a dimension value the user named,
        # else the focal entity, else the single largest mover.
        focal_values = {}
        for d in dim_keys:
            focal_values[d] = await resolve_focal_value(self.schema, self.retrieval, pack, trace, d, plan.domain_id)
        anomalies.sort(key=lambda a: (
            bool(plan.dimension_filter) and all(a.dimension_value.get(k) == v for k, v in plan.dimension_filter.items()),
            any(a.dimension_value.get(d) == v for d, v in focal_values.items() if v),
            abs(a.pct_change),
        ), reverse=True)

        hypotheses = []
        for anomaly in anomalies[:2]:
            corroboration = await self.correlator.find_corroboration(anomaly, plan.domain_id, pack, trace)
            hypotheses.append(self._render_hypothesis(anomaly, corroboration))
        return hypotheses

    def _render_hypothesis(self, anomaly: Anomaly, corroboration: list[dict[str, Any]]) -> Hypothesis:
        dim_desc = ", ".join(f"{k}={v}" for k, v in anomaly.dimension_value.items())
        favorability = "an unfavorable change" if anomaly.is_unfavorable else "a favorable change"
        statement = (
            f"{anomaly.metric_description} ({dim_desc}) {anomaly.direction}d by "
            f"{abs(anomaly.pct_change):.0%} ({anomaly.baseline:.2f} -> {anomaly.current:.2f}), "
            f"which is {favorability}."
        )
        supporting = [f"{anomaly.table}.{anomaly.metric}: {anomaly.baseline:.2f} -> {anomaly.current:.2f} "
                      f"between {anomaly.window[0]} and {anomaly.window[1]}"]
        confidence = min(0.5 + abs(anomaly.pct_change), 0.75)

        for item in corroboration:
            rows = item["rows"]
            confidence = min(confidence + 0.08 * len(item["text_fields"] and rows), 0.97)
            for row in rows[:2]:
                text_bits = [str(row.get(tf)) for tf in item["text_fields"] if row.get(tf)]
                if text_bits:
                    supporting.append(f"[{item['table']}] {' | '.join(text_bits)}")
                else:
                    supporting.append(f"[{item['table']}] activity recorded in the same window for {dim_desc}")

        return Hypothesis(statement=statement, confidence=confidence, supporting_evidence=supporting)


# ===========================================================================
# 8. REASONER — receives ONLY question + plan + hypotheses + pack.
#    Recommendation lookup is also generic: any table whose description
#    matches "opportunity/recommendation/action" semantics and shares a
#    dimension with the anomaly is surfaced, rather than a hardcoded
#    `OpportunityRepository.get_opportunities()` call.
# ===========================================================================


class Recommendation(BaseModel):
    title: str
    priority: str
    rationale: str


class AnswerReport(BaseModel):
    summary: str
    supporting_evidence: list[str]
    confidence: float
    recommendations: list[Recommendation] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)


class Reasoner:
    def __init__(self, llm: LLMClient, schema: SchemaRegistry, query_engine: Any) -> None:
        self.llm = llm
        self.schema = schema
        self.query_engine = query_engine  # anything with async .run(QuerySpec) -> list[dict]

    async def reason(self, plan: InvestigationPlan, hypotheses: list[Hypothesis]) -> AnswerReport:
        await self.llm.complete("reasoner-system-prompt", plan.model_dump_json())

        if plan.kind == "definition":
            field_spec = self.schema.tables[plan.table].field(plan.metric)
            return AnswerReport(
                summary=f"{field_spec.name}: {field_spec.description or 'no description registered.'}",
                supporting_evidence=[],
                confidence=1.0,
            )

        if plan.kind == "raw_lookup":
            table_spec = self.schema.tables[plan.table]
            rows = await self.query_engine.run(QuerySpec(
                table=plan.table, kind="raw", filters={"domain_id": plan.domain_id},
            ))
            evidence = []
            for r in rows[:5]:
                bits = [str(r.get(f.name)) for f in table_spec.text_fields() if r.get(f.name)]
                evidence.append(" | ".join(bits) if bits else str(r))
            return AnswerReport(
                summary=f"Found {len(rows)} record(s) in '{plan.table}' ({table_spec.description}).",
                supporting_evidence=evidence,
                confidence=0.8 if rows else 0.3,
            )

        if plan.kind == "general_qa":
            return AnswerReport(
                summary="I couldn't match this question to a known metric or table in the catalog.",
                supporting_evidence=[f"Known metrics: {[f.name for _, f in self.schema.all_metrics()]}"],
                confidence=0.2,
            )

        if not hypotheses:
            return AnswerReport(
                summary=f"No significant change was detected in {plan.metric} for the requested scope.",
                supporting_evidence=[],
                confidence=0.4,
            )

        # hypotheses[0] is already the one HypothesisEngine prioritized
        # (named entity match > focal brand > largest mover) — respect
        # that ordering rather than re-picking by raw confidence, or a
        # named "how is Salesforce doing" question could get answered
        # with an unrelated, higher-confidence anomaly about a different brand.
        top = hypotheses[0]
        recs = await self._find_recommendations(plan)
        return AnswerReport(
            summary=top.statement,
            supporting_evidence=top.supporting_evidence,
            confidence=top.confidence,
            recommendations=recs,
            next_questions=[
                f"Which specific pages should we prioritize for {plan.metric}?",
                "How does this look broken down by AI model?",
                "Has anything similar happened on other metrics this week?",
            ],
        )

    async def _find_recommendations(self, plan: InvestigationPlan) -> list[Recommendation]:
        """Generic: any table whose description mentions action/opportunity
        semantics AND shares the anomaly's domain, surfaced as-is."""
        recs = []
        for table_spec in self.schema.tables.values():
            if _overlap_score("action opportunity recommendation gap fix", table_spec.description) == 0:
                continue
            rows = await self.query_engine.run(QuerySpec(
                table=table_spec.name, kind="raw", filters={"domain_id": plan.domain_id},
            ))
            for row in rows:
                title_field = next((f.name for f in table_spec.text_fields()), None)
                priority = row.get("priority", "Unranked")
                rationale_field = next((f.name for f in table_spec.text_fields()[1:]), title_field)
                recs.append(Recommendation(
                    title=str(row.get(title_field, "Untitled")),
                    priority=str(priority),
                    rationale=str(row.get(rationale_field, "")),
                ))
        return recs


# ===========================================================================
# 9. ORCHESTRATOR + CONVERSATION MEMORY
# ===========================================================================


@dataclass
class ConversationState:
    domain_id: Union[str, int]
    pack: EvidencePack = dc_field(default_factory=EvidencePack)


class InvestigationEngine:
    """Backend-agnostic by construction: pass any `query_engine` that
    implements `async def run(self, spec: QuerySpec) -> list[dict]` —
    GenericQueryEngine (in-memory) or PostgresQueryEngine (real Postgres,
    see postgres_backend.py) both satisfy this, and nothing else in this
    class or the components it wires together changes between them."""

    def __init__(
        self,
        schema: SchemaRegistry,
        query_engine: Any,
        llm: LLMClient,
        dimension_index: Optional[DimensionValueIndex] = None,
    ) -> None:
        self.schema = schema
        self.query_engine = query_engine
        cache = TTLCache()
        self.retrieval = RetrievalEngine(query_engine, cache)
        self.correlator = CorrelationEngine(schema, self.retrieval)
        self.hypothesis_engine = HypothesisEngine(schema, self.retrieval, self.correlator)
        self.planner = InvestigationPlanner(llm, schema, dimension_index)
        self.reasoner = Reasoner(llm, schema, query_engine)

    @classmethod
    def in_memory(cls, schema: SchemaRegistry, store: "DataStore", llm: LLMClient) -> "InvestigationEngine":
        """Convenience constructor for the prototype/demo path."""
        query_engine = GenericQueryEngine(store, schema)
        dimension_index = build_dimension_index_from_store(schema, store)
        return cls(schema, query_engine, llm, dimension_index)

    async def investigate(self, question: str, state: ConversationState) -> tuple[AnswerReport, InvestigationTrace]:
        start = time.monotonic()
        plan = await self.planner.plan(question, state.domain_id)
        trace = InvestigationTrace(question=question, plan_kind=plan.kind)

        hypotheses: list[Hypothesis] = []
        if plan.kind == "investigate_change":
            hypotheses = await self.hypothesis_engine.investigate(plan, state.pack, trace)
            trace.confidence_progression = [h.confidence for h in hypotheses] or [0.0]

        report = await self.reasoner.reason(plan, hypotheses)
        trace.duration_ms = (time.monotonic() - start) * 1000
        return report, trace


def render_answer(report: AnswerReport) -> str:
    lines = [
        "\n============================================================",
        f"SUMMARY: {report.summary}",
        "------------------------------------------------------------",
    ]
    if report.supporting_evidence:
        lines.append("Supporting evidence:")
        for e in report.supporting_evidence:
            lines.append(f"  - {e}")
    lines.append(f"Confidence: {report.confidence:.0%}")
    if report.recommendations:
        lines.append("Recommendations:")
        for r in report.recommendations:
            lines.append(f"  [{r.priority}] {r.title} — {r.rationale}")
    if report.next_questions:
        lines.append("Suggested next questions:")
        for nq in report.next_questions:
            lines.append(f"  - {nq}")
    lines.append("============================================================\n")
    return "\n".join(lines)


# ===========================================================================
# 10. SEED SCHEMA + DATA — this is the ONLY place that knows about
#     "Zoho CRM", "SOV", "citations", etc. The engine above never does.
#     In production this section doesn't exist at all — introspect_django_
#     apps() builds the SchemaRegistry from real models, and real Postgres
#     rows fill the DataStore.
# ===========================================================================


DOMAIN_ID = 64


def seed() -> tuple[SchemaRegistry, DataStore]:
    schema = SchemaRegistry()
    store = DataStore()
    random.seed(7)
    base_week = now() - timedelta(weeks=6)
    weeks = [base_week + timedelta(weeks=i) for i in range(6)]

    # --- competitor (dimension source table w/ is_focal flag) -------------
    schema.register(TableSpec(
        name="competitor", description="Tracked brands, including the client's own focal brand",
        fields=[
            FieldSpec(name="domain_id", dtype="str", role="identifier"),
            FieldSpec(name="brand", dtype="str", role="dimension", description="Brand name"),
            FieldSpec(name="is_focal", dtype="bool", role="flag", description="Is this the client's own brand"),
        ],
    ))
    store.insert("competitor", [
        {"domain_id": DOMAIN_ID, "brand": "Zoho CRM", "is_focal": True},
        {"domain_id": DOMAIN_ID, "brand": "Salesforce", "is_focal": False},
        {"domain_id": DOMAIN_ID, "brand": "HubSpot", "is_focal": False},
        {"domain_id": DOMAIN_ID, "brand": "Pipedrive", "is_focal": False},
    ])

    # --- brand_topic_metric (mirrors insight_metrics.TopicMetric) ---------
    schema.register(TableSpec(
        name="brand_topic_metric",
        description="Weekly AI visibility metrics per brand per topic (Share of Voice, sentiment)",
        fields=[
            FieldSpec(name="domain_id", dtype="str", role="identifier"),
            FieldSpec(name="brand", dtype="str", role="dimension", description="Brand name"),
            FieldSpec(name="topic", dtype="str", role="dimension", description="Intent cluster / topic"),
            FieldSpec(name="week_of", dtype="datetime", role="time"),
            FieldSpec(name="sov", dtype="float", role="metric", higher_is_better=True,
                       description="Share of Voice — proportion of brand mentions in a topic"),
            FieldSpec(name="sentiment_score", dtype="float", role="metric", higher_is_better=True,
                       description="Sentiment score of AI responses about the brand, -1 to 1"),
        ],
    ))
    decline_curve = {
        "Zoho CRM": [0.34, 0.33, 0.31, 0.29, 0.19, 0.14],
        "Salesforce": [0.29, 0.30, 0.31, 0.32, 0.37, 0.41],
        "HubSpot": [0.22, 0.22, 0.23, 0.22, 0.24, 0.25],
        "Pipedrive": [0.15, 0.15, 0.15, 0.17, 0.20, 0.20],
    }
    rows = []
    for brand, curve in decline_curve.items():
        for i, sov in enumerate(curve):
            rows.append({
                "domain_id": DOMAIN_ID, "brand": brand, "topic": "Cloud Security", "week_of": weeks[i],
                "sov": sov,
                "sentiment_score": round(0.4 - (0.5 if brand == "Zoho CRM" and i >= 4 else 0), 2),
            })
    store.insert("brand_topic_metric", rows)

    # --- prompt_citation (mirrors citations.PromptCitation) ---------------
    schema.register(TableSpec(
        name="prompt_citation",
        description="URLs cited by AI models when answering prompts, attributed to a brand",
        fields=[
            FieldSpec(name="domain_id", dtype="str", role="identifier"),
            FieldSpec(name="brand", dtype="str", role="dimension", description="Brand the citation supports"),
            FieldSpec(name="week_of", dtype="datetime", role="time"),
            FieldSpec(name="page_url", dtype="str", role="text", description="Cited URL"),
            FieldSpec(name="attribution_type", dtype="str", role="category",
                       description="owned / community / earned_media"),
            FieldSpec(name="citation_mass_weight", dtype="float", role="weight"),
        ],
    ))
    store.insert("prompt_citation", [
        {"domain_id": DOMAIN_ID, "brand": "Zoho CRM", "week_of": weeks[0], "page_url": "zoho.com/crm/security", "attribution_type": "owned", "citation_mass_weight": 1.1},
        {"domain_id": DOMAIN_ID, "brand": "Zoho CRM", "week_of": weeks[3], "page_url": "reddit.com/r/CRM/x1", "attribution_type": "community", "citation_mass_weight": 0.4},
        {"domain_id": DOMAIN_ID, "brand": "Salesforce", "week_of": weeks[4], "page_url": "salesforce.com/compare/zoho-vs-salesforce-security", "attribution_type": "owned", "citation_mass_weight": 1.3},
        {"domain_id": DOMAIN_ID, "brand": "Salesforce", "week_of": weeks[5], "page_url": "g2.com/compare/salesforce-vs-zoho", "attribution_type": "community", "citation_mass_weight": 0.6},
        {"domain_id": DOMAIN_ID, "brand": "Zoho CRM", "week_of": weeks[5], "page_url": "zoho.com/crm/security", "attribution_type": "owned", "citation_mass_weight": 0.7},
    ])

    # --- technical_finding (mirrors technical_seo.Finding) -----------------
    schema.register(TableSpec(
        name="technical_finding",
        description="Technical SEO / AI-readability issues found on crawled pages",
        fields=[
            FieldSpec(name="domain_id", dtype="str", role="identifier"),
            FieldSpec(name="brand", dtype="str", role="dimension", description="Brand the page belongs to"),
            FieldSpec(name="week_of", dtype="datetime", role="time"),
            FieldSpec(name="severity", dtype="str", role="category"),
            FieldSpec(name="fix_hint", dtype="str", role="text", description="Suggested fix"),
        ],
    ))
    store.insert("technical_finding", [
        {"domain_id": DOMAIN_ID, "brand": "Zoho CRM", "week_of": weeks[4], "severity": "p1",
         "fix_hint": "zoho.com/crm/security hasn't been updated in 9 months; missing SOC 2 Type II / ISO 27001 mentions competitors cite."},
        {"domain_id": DOMAIN_ID, "brand": "Zoho CRM", "week_of": weeks[4], "severity": "p2",
         "fix_hint": "zoho.com/crm/security has no FAQPage schema markup."},
    ])

    # --- opportunity (mirrors opportunity.Opportunity) ---------------------
    schema.register(TableSpec(
        name="opportunity",
        description="Recommended actions to close AI visibility gaps (content opportunity)",
        fields=[
            FieldSpec(name="domain_id", dtype="str", role="identifier"),
            FieldSpec(name="brand", dtype="str", role="dimension"),
            FieldSpec(name="week_of", dtype="datetime", role="time"),
            FieldSpec(name="gap_title", dtype="str", role="text"),
            FieldSpec(name="rationale", dtype="str", role="text"),
            FieldSpec(name="priority", dtype="str", role="category"),
        ],
    ))
    store.insert("opportunity", [
        {"domain_id": DOMAIN_ID, "brand": "Zoho CRM", "week_of": weeks[5],
         "gap_title": "Refresh Zoho CRM security page with current certifications",
         "rationale": "Still the most-cited owned source but losing ground to Salesforce's newer comparison page.",
         "priority": "Quick Win"},
        {"domain_id": DOMAIN_ID, "brand": "Zoho CRM", "week_of": weeks[5],
         "gap_title": "Publish a Zoho vs Salesforce security comparison page",
         "rationale": "Salesforce currently owns this comparison narrative; no equivalent owned asset exists.",
         "priority": "Big Bet"},
    ])

    return schema, store


# ===========================================================================
# 11. DEMO
# ===========================================================================


async def main() -> None:
    schema, store = seed()
    state = ConversationState(domain_id=DOMAIN_ID)
    engine = InvestigationEngine.in_memory(schema, store, MockLLMClient())

    questions = [
        "Why did our Share of Voice decrease on Cloud Security this month?",
        "What technical issues are affecting our AI visibility?",
        "What is sentiment_score?",
    ]
    for i, q in enumerate(questions, 1):
        print(f"\n\n########## TURN {i}: {q} ##########")
        report, trace = await engine.investigate(q, state)
        print(render_answer(report))
        print(trace.render())

    # -----------------------------------------------------------------
    # THE PAYOFF: register a brand-new table/metric at runtime, with
    # ZERO changes to any Planner/Skill/Hypothesis/Repository code above,
    # and prove the engine can already investigate it.
    # -----------------------------------------------------------------
    print("\n\n>>> Simulating a schema change: a new 'reddit_signal_metric' table "
          "ships with a brand-new 'controversy_score' column. No engine code is touched. <<<\n")

    week_of = now() - timedelta(weeks=1)
    schema.register(TableSpec(
        name="reddit_signal_metric",
        description="Reddit community controversy and engagement signal per brand per week",
        fields=[
            FieldSpec(name="domain_id", dtype="str", role="identifier"),
            FieldSpec(name="brand", dtype="str", role="dimension"),
            FieldSpec(name="week_of", dtype="datetime", role="time"),
            FieldSpec(name="controversy_score", dtype="float", role="metric", higher_is_better=False,
                       description="Composite Reddit controversy/backlash signal"),
            FieldSpec(name="thread_summary", dtype="str", role="text"),
        ],
    ))
    store.insert("reddit_signal_metric", [
        {"domain_id": DOMAIN_ID, "brand": "Zoho CRM", "week_of": now() - timedelta(weeks=6), "controversy_score": 0.10,
         "thread_summary": "quiet week, no notable threads"},
        {"domain_id": DOMAIN_ID, "brand": "Zoho CRM", "week_of": week_of, "controversy_score": 0.61,
         "thread_summary": "r/CRM thread: users frustrated about unclear SOC 2 compliance answers from support"},
    ])

    report, trace = await engine.investigate("Why did our controversy score spike this week?", state)
    print(render_answer(report))
    print(trace.render())


if __name__ == "__main__":
    asyncio.run(main())