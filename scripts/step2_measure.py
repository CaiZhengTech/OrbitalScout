"""Evidence for the two Step 2 parameters that must be chosen before the baseline runs.

1. Minimum clear fraction of a field on a date. Measured by whether zones seen on
   partially clouded field-dates read differently from the same fields, at the
   same growth stage, on fully clear dates. If partial dates read low, they carry
   missed cloud edge, shadow or haze, and a strict threshold is justified by data.

2. Phenology bin width. The rule in SPEC Section 8: the narrowest of 150, 200,
   250 and 300 GDD leaving at least 90% of zone-year-bins observed. Reported for
   every clear-fraction candidate, because dropping cloudy field-dates lowers
   coverage and the two choices interact.

Coverage is estimated on a deterministic 5% sample of zones (hash of the zone id),
which is ample for a proportion over 700,000 zones and avoids scanning 150 million
rows sixteen times. Clear fraction itself is always computed over every zone in
the field, since a sample would misstate it.

Run:
    python scripts/step2_measure.py
"""

import os
import sys

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config  # noqa: E402
from orbitalscout.ingest import weather  # noqa: E402

FROZEN = "orbitalscout/frozen"
CLEAR_CANDIDATES = (0.0, 0.5, 0.9, 0.99)
PROVISIONAL_WIDTH = 200  # only for the contamination diagnostic, which needs a stage bucket


def main():
    con = duckdb.connect("data/orbitalscout.duckdb", read_only=True)
    con.execute("SET memory_limit = '2GB'")

    daily = pd.read_csv(f"{FROZEN}/weather_daily.csv", dtype={"date": str})
    planting = pd.read_csv(f"{FROZEN}/planting_dates.csv")
    con.register("gdd", weather.gdd_table(daily, planting))

    crop_cols = ", ".join(f"crop_{y}" for y in config.YEARS)
    con.execute(f"""
        CREATE TEMP TABLE field_crop AS
        SELECT field_id, CAST(replace(k, 'crop_', '') AS INTEGER) AS year, cdl_code
        FROM (UNPIVOT fields ON {crop_cols} INTO NAME k VALUE cdl_code)
    """)

    print("clear fraction per field-date, over all zones ...", flush=True)
    con.execute("""
        CREATE TEMP TABLE fds AS
        SELECT o.field_id, o.date, count(*)::DOUBLE / any_value(z.n) AS clear_frac
        FROM zone_obs o
        JOIN (SELECT field_id, count(*) AS n FROM zones GROUP BY field_id) z USING (field_id)
        GROUP BY o.field_id, o.date
    """)

    print("sampling 5% of zones and attaching stage ...", flush=True)
    con.execute("""
        CREATE TEMP TABLE s AS
        SELECT o.zone_id, o.field_id, o.year, o.date, o.ndvi, g.gdd, f.clear_frac
        FROM zone_obs o
        JOIN field_crop fc ON fc.field_id = o.field_id AND fc.year = o.year
        JOIN gdd g ON g.cdl_code = fc.cdl_code AND g.date = o.date
        JOIN fds f ON f.field_id = o.field_id AND f.date = o.date
        WHERE hash(o.zone_id) % 20 = 0
    """)
    n = con.execute("SELECT count(*), count(DISTINCT zone_id) FROM s").fetchone()
    print(f"  {n[0]:,} observations over {n[1]:,} sampled zones\n")

    # ---- 1. contamination by clear-fraction band ----
    print("1. Do partially clouded field-dates read differently?")
    print("   NDVI on the date, minus the same field's fully clear (>=99%) NDVI")
    print(f"   at the same growth stage ({PROVISIONAL_WIDTH} GDD bucket), same year.\n")
    rows = con.execute(f"""
        WITH b AS (
            SELECT *, CAST(floor(gdd / {PROVISIONAL_WIDTH}) AS INTEGER) AS stage FROM s
        ),
        clear_ref AS (
            SELECT field_id, year, stage, avg(ndvi) AS ref FROM b
            WHERE clear_frac >= 0.99 GROUP BY ALL
        ),
        banded AS (
            SELECT b.*, b.ndvi - r.ref AS diff,
                CASE WHEN clear_frac < 0.10 THEN '00-10%'
                     WHEN clear_frac < 0.25 THEN '10-25%'
                     WHEN clear_frac < 0.50 THEN '25-50%'
                     WHEN clear_frac < 0.75 THEN '50-75%'
                     WHEN clear_frac < 0.90 THEN '75-90%'
                     WHEN clear_frac < 0.99 THEN '90-99%'
                     ELSE '99-100%' END AS band
            FROM b JOIN clear_ref r USING (field_id, year, stage)
        )
        SELECT band, count(*), median(diff), quantile_cont(diff, 0.25), quantile_cont(diff, 0.75)
        FROM banded GROUP BY band ORDER BY band
    """).fetchall()
    print(f"   {'field clear':<12} {'obs':>10} {'median diff':>12} {'p25':>8} {'p75':>8}")
    for band, cnt, med, p25, p75 in rows:
        print(f"   {band:<12} {cnt:>10,} {med:>12.4f} {p25:>8.4f} {p75:>8.4f}")

    # ---- 2. bin coverage per width per threshold ----
    print("\n2. Share of zone-year-bins holding at least one observation")
    print("   denominator: every bin from planting to 30 September for that crop-year\n")
    con.execute("""
        CREATE TEMP TABLE season_end AS
        SELECT cdl_code, CAST(substr(date, 1, 4) AS INTEGER) AS year, max(gdd) AS gdd_end
        FROM gdd WHERE substr(date, 6, 5) <= '09-30' GROUP BY ALL
    """)
    header = "   width  " + "".join(f"  clear>={c:<5}" for c in CLEAR_CANDIDATES)
    print(header)
    for width in config.BIN_WIDTH_CANDIDATES_GDD:
        cells = []
        for threshold in CLEAR_CANDIDATES:
            observed, possible = con.execute(f"""
                WITH zy AS (
                    SELECT DISTINCT s.zone_id, s.year, fc.cdl_code
                    FROM s JOIN field_crop fc ON fc.field_id = s.field_id AND fc.year = s.year
                ),
                possible AS (
                    SELECT sum(CAST(floor(e.gdd_end / {width}) AS INTEGER) + 1)
                    FROM zy JOIN season_end e USING (cdl_code, year)
                ),
                observed AS (
                    SELECT count(*) FROM (
                        SELECT DISTINCT zone_id, year, CAST(floor(gdd / {width}) AS INTEGER)
                        FROM s WHERE clear_frac >= {threshold}
                    )
                )
                SELECT (SELECT * FROM observed), (SELECT * FROM possible)
            """).fetchone()
            cells.append(f"  {100 * observed / possible:>9.1f}%  ")
        print(f"   {width:>5}  " + "".join(cells))
    print(f"\n   rule: narrowest width with coverage >= {config.BIN_COVERAGE_MIN:.0%}")


if __name__ == "__main__":
    main()
