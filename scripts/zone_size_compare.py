"""Issue #7: compare year-over-year variation at 10m and 30m over the same fields.

Implements the metric fixed in scripts/zone_size_export.py before any 10m data
existed. Both resolutions go through the production baseline views, so the only
difference between them is the zone size.

Steps:
    1. fetch the 10m exports into data/zone_size/
    2. melt each season on a 10m grid
    3. build the baseline views over the 10m zones
    4. per zone and year, mean within-field relative NDVI over the label window;
       per zone, the SD of that across years, zones with enough years only;
       median across zones, at 10m and at 30m over the same sample fields

Run:
    python scripts/zone_size_compare.py
"""

import csv
import os
import pathlib
import subprocess
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import baseline, config  # noqa: E402
from orbitalscout.ingest import melt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_baseline as bb  # noqa: E402

DATA = pathlib.Path("data/zone_size")
SAMPLE = pathlib.Path("orbitalscout/frozen/zone_size_sample.csv")


def sample_fields():
    with open(SAMPLE, newline="", encoding="utf-8") as handle:
        return sorted(int(r["field_idx"]) for r in csv.DictReader(handle))


def fetch_and_melt():
    DATA.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "scripts/fetch_exports.py", "--pattern", "orbitalscout10_",
                    "--out", str(DATA)], check=True)
    for year in config.YEARS:
        out = DATA / f"zone_obs10_{year}.parquet"
        if out.exists():
            continue
        rows = melt.melt_cube_to_parquet(
            value_path=DATA / f"orbitalscout10_values_{year}.tif",
            count_path=DATA / f"orbitalscout10_counts_{year}.tif",
            field_path=DATA / "orbitalscout10_fieldid.tif",
            year=year, out_path=out, min_valid=1, grid=config.NATIVE_SIZE_M,
        )
        print(f"melted {year} at 10m: {rows:,} pixel-date rows", flush=True)


def per_zone_sd(con, table):
    """Median across zones of the SD across years of the zone-year mean."""
    return con.execute(f"""
        SELECT count(*), median(sd), quantile_cont(sd, 0.25), quantile_cont(sd, 0.75)
        FROM (SELECT zone_id, stddev_samp(m) AS sd, count(*) AS n FROM {table} GROUP BY zone_id)
        WHERE n >= {config.MIN_PRIOR_YEARS}
    """).fetchone()


def main():
    if "--skip-fetch" not in sys.argv:
        fetch_and_melt()
    chosen = sample_fields()
    fields = ", ".join(str(f) for f in chosen)
    lo, hi = config.LABEL_BINS

    con = bb.connect()
    con.execute("SET memory_limit = '1GB'")
    con.execute("SET threads = 2")
    con.execute("CREATE TEMP TABLE zy10 (zone_id BIGINT, year INTEGER, m DOUBLE)")
    con.execute("CREATE TEMP TABLE zy30 (zone_id BIGINT, year INTEGER, m DOUBLE)")
    con.execute("DROP VIEW zones")

    # One season at a time. A field median is taken per field-date, so a year's
    # result depends only on that year: splitting by year is exact, not an
    # approximation, and keeps the working set to one season.
    for year in config.YEARS:
        con.execute(f"""CREATE OR REPLACE VIEW zone_obs AS SELECT * FROM
            read_parquet('{DATA.as_posix()}/zone_obs10_{year}.parquet')
            WHERE field_id IN ({fields})""")
        con.execute("CREATE OR REPLACE VIEW zones AS SELECT DISTINCT zone_id, field_id FROM zone_obs")
        baseline.build_views(con, config.BIN_WIDTH_GDD, config.MIN_FIELD_CLEAR_FRAC)
        con.execute(f"""INSERT INTO zy10
            SELECT zone_id, year, avg(rel_ndvi) FROM zone_year_bin
            WHERE bin BETWEEN {lo} AND {hi} AND rel_ndvi IS NOT NULL
            GROUP BY zone_id, year""")
        print(f"  10m {year} done", flush=True)

    # The 30m side is already built; zone ids never span chunks, so aggregating
    # per chunk gives the same answer as aggregating over all of them at once.
    for chunk in range(bb.CHUNKS):
        path = (bb.OUT / f"baseline_{chunk:02d}.parquet").as_posix()
        con.execute(f"""INSERT INTO zy30
            SELECT zone_id, year, avg(rel_ndvi) FROM read_parquet('{path}')
            WHERE field_id IN ({fields}) AND bin BETWEEN {lo} AND {hi} AND rel_ndvi IS NOT NULL
            GROUP BY zone_id, year""")
    print("  30m done", flush=True)

    print()
    print(f"zone size comparison over {len(chosen)} fields, label window bins "
          f"{lo} to {hi}, zones with at least {config.MIN_PRIOR_YEARS} years")
    print()
    print(f"  {'zone size':<10} {'zones':>9} {'median SD':>10} {'p25':>8} {'p75':>8}")
    results = {}
    for label, table in (("10m", "zy10"), ("30m", "zy30")):
        n, med, p25, p75 = per_zone_sd(con, table)
        results[label] = med
        print(f"  {label:<10} {n:>9,} {med:>10.4f} {p25:>8.4f} {p75:>8.4f}")
    print()
    print(f"  ratio of median SD, 10m over 30m: {results['10m'] / results['30m']:.2f}")
    print("  prior expectation, recorded before measurement: 30m lower")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
