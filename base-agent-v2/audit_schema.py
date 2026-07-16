"""
Schema audit — run this against YOUR OWN database. Read-only: it only
issues SELECT/information_schema queries, never writes anything, so it's
safe to point at production (though a read replica is still preferable —
see the note on cost below).

Usage:
    export GRAVTON_DSN="postgresql://user:password@host:5432/dbname"
    python3 audit_schema.py                          # all tables
    python3 audit_schema.py table1 table2 table3      # only these tables

Output:
    - A printed report of every discovered table/column: tagged vs
      heuristic-guessed, and anything flagged NEEDS REVIEW.
    - tagging_starter.sql — COMMENT ON statements for every table/column
      that has NO existing gravton: tag, pre-filled with the best guess,
      for you to review and edit before applying. Columns/tables that are
      already tagged are left out — this file is purely the delta.

Cost note: for each UNTAGGED text/varchar column, the heuristic fallback
runs a `COUNT(DISTINCT col) / COUNT(*)` query to guess category vs
dimension. On a large table this is a real scan. Two ways to control this:
  1. Pass specific table names as CLI args to limit scope.
  2. Tag the columns that matter first — a tagged column is never scanned.
"""

import asyncio
import os
import sys

import asyncpg

from postgres_backend import PostgresSchemaIntrospector

DSN = os.environ.get("GRAVTON_DSN")


async def main() -> None:
    if not DSN:
        print("Set GRAVTON_DSN first, e.g.:\n"
              '  export GRAVTON_DSN="postgresql://user:password@host:5432/dbname"')
        sys.exit(1)

    include_tables = sys.argv[1:] or None
    if include_tables:
        print(f"Scoping audit to: {include_tables}\n")
    else:
        print("No table names given — auditing ALL base tables in the 'public' schema.\n"
              "For a large production DB, consider passing specific table names instead.\n")

    conn = await asyncpg.connect(DSN)
    introspector = PostgresSchemaIntrospector(DSN)

    # Pull raw comment status directly (separate from the full discover()
    # call) so we can report tagged-vs-guessed even for tables discover()
    # would skip (e.g. a table with no metric/dimension fields at all).
    tables = await conn.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    all_table_names = [t["table_name"] for t in tables]
    if include_tables:
        all_table_names = [t for t in all_table_names if t in include_tables]
    await conn.close()

    schema = await introspector.discover(include_tables=include_tables)

    print("=" * 70)
    print(f"DISCOVERED {len(schema.tables)} analytically-useful table(s) "
          f"out of {len(all_table_names)} scanned")
    print("=" * 70)

    starter_sql_lines: list[str] = [
        "-- Auto-generated starter tags. REVIEW BEFORE APPLYING.",
        "-- Fill in / correct descriptions and higher_is_better where marked TODO.",
        "",
    ]
    needs_review_count = 0
    skipped_tables = set(all_table_names) - set(schema.tables.keys())

    for table in schema.tables.values():
        tagged_cols = await introspector.tagged_columns(table.name)
        table_tagged = table.description != table.name  # discover() only sets this from a real gravton_table: tag
        print(f"\n[{table.name}]  {table.description}")
        if not table_tagged:
            starter_sql_lines.append(
                f"COMMENT ON TABLE {table.name} IS "
                f"'gravton_table: {{\"description\":\"TODO: describe what this table holds\"}}';"
            )
        for f in table.fields:
            tagged = f.name in tagged_cols
            status = "tagged" if tagged else "GUESSED"
            review = ""
            if f.role == "metric" and f.higher_is_better is None:
                review = "  <-- NEEDS REVIEW: confirm higher_is_better"
                needs_review_count += 1
            print(f"    {f.name:<28} role={f.role:<11} [{status}]{review}")

            if not tagged:
                desc = "TODO: describe this field" if f.description.startswith("[auto") or not f.description else f.description
                if f.role == "metric":
                    hib_known = f.higher_is_better is not None
                    hib = "true" if f.higher_is_better else "false"
                    if not hib_known:
                        starter_sql_lines.append(
                            f"-- REVIEW: higher_is_better defaulted to false below for "
                            f"{table.name}.{f.name} — confirm the real direction before applying."
                        )
                    starter_sql_lines.append(
                        f'COMMENT ON COLUMN {table.name}.{f.name} IS '
                        f'\'gravton: {{"role":"{f.role}","higher_is_better":{hib},"description":"{desc}"}}\';'
                    )
                else:
                    starter_sql_lines.append(
                        f'COMMENT ON COLUMN {table.name}.{f.name} IS '
                        f'\'gravton: {{"role":"{f.role}","description":"{desc}"}}\';'
                    )

    if skipped_tables:
        print(f"\n\nSKIPPED (no metric or dimension field detected — not registered): "
              f"{sorted(skipped_tables)}")
        print("If one of these should be investigable, it likely just needs at least")
        print("one column tagged 'role':'metric' or 'role':'dimension'.")

    with open("tagging_starter.sql", "w") as f:
        f.write("\n".join(starter_sql_lines) + "\n")

    print(f"\n\nWrote tagging_starter.sql ({len(starter_sql_lines) - 3} statement(s)).")
    print(f"{needs_review_count} metric field(s) need a human to confirm higher_is_better.")
    print("\nNext step: open tagging_starter.sql, fill in the TODOs, then:")
    print("  psql $GRAVTON_DSN -f tagging_starter.sql")


if __name__ == "__main__":
    asyncio.run(main())