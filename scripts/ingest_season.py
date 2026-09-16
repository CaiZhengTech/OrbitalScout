"""Cube on disk to rows in DuckDB. The local half of Step 1.

Reads the Earth Engine export, reshapes it, and writes the three tables that
`docs/reviews/2026-09-15-step1-architecture.md` Decision 5 defines. Nothing
downstream reads a raster after this.

Run:
    python scripts/ingest_season.py --year 2020
"""

import argparse
import os
import pathlib
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config  # noqa: E402
from orbitalscout.ingest import load, melt  # noqa: E402

ACRE_M2 = 4046.8564224


def read_fields(path):
    """Earth Engine's CSV of the index-to-field lookup, renamed to the contract."""
    raw = pd.read_csv(path)
    fields = pd.DataFrame({
        "field_id": raw["field_idx"].astype("int64"),
        "csbid": raw[config.CSB_FIELD_ID].astype(str),
        "area_m2": raw["CSBACRES"].astype(float) * ACRE_M2,
    })
    for year in config.YEARS:
        fields[f"crop_{year}"] = raw[config.CSB_CROP_PROPERTY.format(year=year)].astype("int64")
    return fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--data", default="data")
    parser.add_argument("--db", default="data/orbitalscout.duckdb")
    args = parser.parse_args()

    data = pathlib.Path(args.data)
    paths = {
        "value": data / f"orbitalscout_values_{args.year}.tif",
        "count": data / f"orbitalscout_counts_{args.year}.tif",
        "field": data / "orbitalscout_fieldid.tif",
        "fields": data / "orbitalscout_fields.csv",
    }
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise SystemExit("missing input(s):\n  " + "\n  ".join(missing))

    fields = read_fields(paths["fields"])
    print(f"fields: {len(fields)} rows")

    melted = melt.melt_cube(
        value_path=paths["value"], count_path=paths["count"],
        field_path=paths["field"], year=args.year,
        min_valid=config.MIN_SUBPIXELS,
    )
    print(f"melted: {len(melted):,} zone-date-index rows")
    if melted.empty:
        raise SystemExit("melt produced nothing; check the export")

    # A masked pixel must have vanished, not become a zero. Exact zeros are
    # possible in principle but vanishingly unlikely for a scaled index, so a
    # pile of them means the nodata handling regressed.
    zeros = int((melted["value"] == 0).sum())
    if zeros > len(melted) // 100:
        raise SystemExit(
            f"{zeros:,} of {len(melted):,} values are exactly 0. "
            "That is the masked-pixel-became-zero failure; check the nodata tag."
        )

    unknown = set(melted["field_id"]) - set(fields["field_id"])
    if unknown:
        raise SystemExit(
            f"{len(unknown)} field ids in the raster are absent from the lookup "
            f"table, for example {sorted(unknown)[:5]}. The raster and the table "
            "were built from different orderings."
        )

    load.load(args.db, melted, fields)
    print(f"loaded into {args.db}")

    import duckdb
    con = duckdb.connect(args.db)
    for table in ("fields", "zones", "zone_obs"):
        print(f"  {table}: {con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:,} rows")
    stats = con.execute(
        "SELECT count(DISTINCT zone_id), count(DISTINCT date), "
        "min(ndvi), median(ndvi), max(ndvi) FROM zone_obs"
    ).fetchone()
    print(f"  zones: {stats[0]:,}  dates: {stats[1]}")
    print(f"  ndvi min/median/max: {stats[2]:.3f} / {stats[3]:.3f} / {stats[4]:.3f}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
