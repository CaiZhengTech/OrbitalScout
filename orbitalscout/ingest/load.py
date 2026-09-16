"""Load melted rows into the three-table DuckDB contract.

`docs/reviews/2026-09-15-step1-architecture.md` Decision 5. Everything
downstream reads `fields`, `zones` and `zone_obs`. Nothing downstream reads a
raster or calls Earth Engine.

The melt produces one row per zone-date-index; the contract is one row per
zone-date with a column per index, so this pivots. That pivot is the second
place a missing observation could quietly become a number, so a masked index
lands as NULL and the row is kept rather than dropped.
"""

import duckdb
import pandas as pd

from .. import config
from .melt import xy_from_zone_id

INDEX_COLUMNS = tuple(config.INDICES)


def _pivot(melted):
    """Long to wide, keeping absences as nulls."""
    unknown = set(melted["index"]) - set(INDEX_COLUMNS)
    if unknown:
        raise ValueError(f"unknown index name(s) {sorted(unknown)}")

    keys = ["zone_id", "field_id", "year", "date"]
    duplicated = melted.duplicated(subset=keys + ["index"], keep=False)
    if duplicated.any():
        example = melted.loc[duplicated, keys + ["index"]].iloc[0].to_dict()
        raise ValueError(f"duplicate rows for the same zone-date-index: {example}")

    wide = melted.pivot(index=keys, columns="index", values="value").reset_index()
    wide.columns.name = None
    for column in INDEX_COLUMNS:
        if column not in wide:
            wide[column] = pd.NA

    # n_valid is per zone-date, shared across indices, so one value per key.
    counts = melted.groupby(keys, as_index=False)["n_valid"].max()
    wide = wide.merge(counts, on=keys, how="left")
    return wide[keys + list(INDEX_COLUMNS) + ["n_valid"]]


def _zones(wide):
    """One row per zone, with its grid-cell origin recovered from the id."""
    zones = wide[["zone_id", "field_id"]].drop_duplicates().reset_index(drop=True)
    coords = [xy_from_zone_id(int(z)) for z in zones["zone_id"]]
    zones["x_5070"] = [x for x, _ in coords]
    zones["y_5070"] = [y for _, y in coords]
    return zones


def load(db_path, melted, fields):
    """Write fields, zones and zone_obs. Replaces, so re-running is safe."""
    wide = _pivot(melted)
    zones = _zones(wide)
    zone_obs = wide.drop(columns=["field_id"])

    con = duckdb.connect(db_path)
    try:
        con.register("_fields", fields)
        con.register("_zones", zones)
        con.register("_zone_obs", zone_obs)
        con.execute("CREATE OR REPLACE TABLE fields AS SELECT * FROM _fields")
        con.execute("CREATE OR REPLACE TABLE zones AS SELECT * FROM _zones")
        con.execute("CREATE OR REPLACE TABLE zone_obs AS SELECT * FROM _zone_obs")

        orphans = con.execute(
            "SELECT count(*) FROM zones z "
            "LEFT JOIN fields f USING (field_id) WHERE f.field_id IS NULL"
        ).fetchone()[0]
        if orphans:
            raise ValueError(f"{orphans} zones reference a field not in the fields table")
    finally:
        con.close()
