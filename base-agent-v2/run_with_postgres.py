"""
Run the Investigation Engine against a real Postgres database.

Usage:
    export GRAVTON_DSN="postgresql://gravton:gravton@localhost:5432/gravton_demo"
    python3 run_with_postgres.py
"""

import asyncio
import os
from dataclasses import dataclass, field

from gravton_engine import AnthropicLLMClient, ConversationState, EvidencePack, render_answer
from postgres_backend import create_postgres_engine

DSN = os.environ.get("GRAVTON_DSN", "postgresql://gravton:gravton@localhost:5432/gravton_demo")
DOMAIN_ID = 64  # TODO: replace with the actual integer domain_id from your Postgres DB


async def main() -> None:
    engine, pool = await create_postgres_engine(DSN, AnthropicLLMClient(), include_tables=[
        # --- AI visibility (views — domain_id via join) ---
        "v_prompt_metric",           # per-prompt SOV, sentiment, visibility per brand
        "v_prompt_citation",         # URL citations attributed to brand + topic
        "v_topic_metric",            # topic-level SOV/sentiment rollup per brand
        "v_topic_metric_unbranded",  # same for unbranded queries
        "v_brand_signal_metric",     # canonical sentiment signals per brand
        "v_opportunity",             # content/optimization opportunities

        # --- Demand universe (direct domain_id) ---
        "demand_universe_prompt_labels",  # demand_score, sov, prompt_volume per brand per prompt

        # --- Keywords (direct domain_id) ---
        "k_lib",                     # search volume, AI search volume, AI demand per keyword

        # --- SEO (views — domain_id via join / filter) ---
        "v_technical_seo_scan",      # health scores per completed scan
        "v_seo_finding",             # individual audit findings

        # --- GSC search performance (views — domain_id via join) ---
        "v_gsc_query",               # clicks, impressions, CTR, position per query
        "v_gsc_page",                # clicks, impressions, CTR, position per page

        # --- Alerts & opportunities (direct domain_id) ---
        "checkpoint_callouts",       # impact-scored callouts per run
        "opportunity_clusters",      # clustered opportunities with impact scores

        # --- Social signals (direct domain_id) ---
        "reddit_insight_signals",    # aggregated Reddit signals per domain
        "quora_insight_signals",     # aggregated Quora signals per domain
        "reddit_threads",            # thread-level engagement (score, comments)
        "quora_questions",           # question-level engagement (followers, views)
    ])
    state = ConversationState(domain_id=DOMAIN_ID)

    questions = [
        "What is Share of Voice?"
    ]
    try:
        for i, q in enumerate(questions, 1):
            print(f"\n\n########## TURN {i}: {q} ##########")
            report, trace = await engine.investigate(q, state)
            print(render_answer(report))
            print(trace.render())
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())