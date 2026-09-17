"""Assemble the three-table DuckDB contract from the melted Parquet.

`docs/reviews/2026-09-15-step1-architecture.md` Decision 5. Everything
downstream reads `fields`, `zones` and `zone_obs`. Nothing downstream reads a
raster or calls Earth Engine.

`melt` writes wide Parquet, one row per zone-date with a column per index, so
there is no pivot here. DuckDB reads the Parquet directly, which is the reason
SPEC Section 12 chose it over anything with a server.
"""

import duckdb

from .melt import ZONE_GRID_M, _OFFSET, _STRIDE


def load(db_path, zone_obs_glob, fields):
    """Write fields, zones and zone_obs. Replaces, so re-running is safe.

    `zone_obs_glob` is a path or glob of wide Parquet files, one per season.
    """
    con = duckdb.connect(db_path)
    try:
        con.register("_fields", fields)
        con.execute("CREATE OR REPLACE TABLE fields AS SELECT * FROM _fields")
        con.execute(
            "CREATE OR REPLACE TABLE zone_obs AS "
            "SELECT * FROM read_parquet(?)", [zone_obs_glob]
        )

        duplicates = con.execute(
            "SELECT count(*) FROM (SELECT zone_id, date FROM zone_obs "
            "GROUP BY zone_id, date HAVING count(*) > 1)"
        ).fetchone()[0]
        if duplicates:
            raise ValueError(
                f"duplicate zone-date rows: {duplicates} pairs appear more "
                "than once. A season was probably melted into two files."
            )

        # Zone identity is its grid cell, so the coordinates are recoverable
        # from the id rather than stored twice and allowed to disagree.
        con.execute(f"""
            CREATE OR REPLACE TABLE zones AS
            SELECT DISTINCT
                zone_id,
                field_id,
                (zone_id // {_STRIDE} - {_OFFSET}) * {ZONE_GRID_M} AS x_5070,
                (zone_id %  {_STRIDE} - {_OFFSET}) * {ZONE_GRID_M} AS y_5070
            FROM zone_obs
        """)

        orphans = con.execute(
            "SELECT count(*) FROM zones z "
            "LEFT JOIN fields f USING (field_id) WHERE f.field_id IS NULL"
        ).fetchone()[0]
        if orphans:
            raise ValueError(
                f"{orphans} zones reference a field absent from the fields "
                "table. The raster and the lookup table were built from "
                "different orderings."
            )
    finally:
        con.close()
