"""The Step 2 diagnostics owed by the decision record. Reported, never gating.

1. Derecho sensitivity. The baseline and the label with and without the post-
   derecho exclusion. Labels are compared over every zone-year; baseline cells
   in the touched bins are compared on one chunk of zones (10%), which is
   ample for a distribution and avoids rebuilding every cell twice.

2. Corn versus soybean relative standing. Across zones, the correlation between
   a zone's mean relative NDVI in its corn years and in its soybean years. A
   correlation alone cannot say whether a low value is a crop interaction or
   plain noise, so the same statistic between the earlier and later half of a
   zone's own same-crop years is reported alongside as the reference.

3. Green-up spread around the NASS anchor. Per field-year, the first date the
   field-median NDVI reaches its seasonal minimum plus half its amplitude,
   against that crop-year's 50% planted date. Field-years whose first clear
   reading is already past that level are counted as unidentifiable rather
   than assigned a date.

Run:
    python scripts/step2_diagnostics.py
"""

import os
import pathlib
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import baseline, config, crops  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_baseline as bb  # noqa: E402

OUT = bb.OUT
HELD = ", ".join(str(y) for y in bb.HELD_OUT)
NAMES = {code: crops.get(code).name for code in crops.codes()}


def derecho_sensitivity():
    print("1. Derecho sensitivity", flush=True)
    stats = (OUT / "field_date_stats.parquet").as_posix()
    con = bb.connect()
    for chunk in range(bb.CHUNKS):
        t = time.time()
        bb.zone_obs_view(con, chunk)
        baseline.build_views(con, config.BIN_WIDTH_GDD, config.MIN_FIELD_CLEAR_FRAC,
                             events=(), field_stats=stats)
        baseline.outcome_views(con)
        con.execute(f"COPY zone_year_label TO "
                    f"'{(OUT / f'label_noevent_{chunk:02d}.parquet').as_posix()}' (FORMAT PARQUET)")
        if chunk == 0:
            con.execute(f"""COPY (
                SELECT zone_id, year, bin, baseline_ndvi, n_prior_years FROM baseline
                WHERE bin >= 10 AND year <> 2020
            ) TO '{(OUT / 'cells_noevent_00.parquet').as_posix()}' (FORMAT PARQUET)""")
            con.execute(f"""COPY (
                SELECT zone_id, year, bin, label_baseline_ndvi, n_label_years FROM label_baseline
                WHERE bin >= 10 AND year <> 2020
            ) TO '{(OUT / 'labelcells_noevent_00.parquet').as_posix()}' (FORMAT PARQUET)""")
        print(f"   rebuilt chunk {chunk + 1}/{bb.CHUNKS} without the exclusion, {time.time() - t:.0f}s",
              flush=True)

    # The same two cell tables with the exclusion, for chunk 0 only.
    bb.zone_obs_view(con, 0)
    baseline.build_views(con, config.BIN_WIDTH_GDD, config.MIN_FIELD_CLEAR_FRAC, field_stats=stats)
    con.execute("CREATE TEMP TABLE with_b AS SELECT zone_id, year, bin, baseline_ndvi, n_prior_years "
                "FROM baseline WHERE bin >= 10 AND year <> 2020")
    con.execute("CREATE TEMP TABLE with_l AS SELECT zone_id, year, bin, label_baseline_ndvi, n_label_years "
                "FROM label_baseline WHERE bin >= 10 AND year <> 2020")

    print("\n   baseline cells in bins 10 and later, years other than 2020, one chunk of zones:")
    for name, with_t, without, col, n in (
        ("feature baseline (strictly prior)", "with_b", "cells_noevent_00", "baseline_ndvi", "n_prior_years"),
        ("label baseline (leave-one-year-out)", "with_l", "labelcells_noevent_00", "label_baseline_ndvi", "n_label_years"),
    ):
        r = con.execute(f"""
            SELECT count(*), avg(abs(w.{col} - o.{col})), median(abs(w.{col} - o.{col})),
                   quantile_cont(abs(w.{col} - o.{col}), 0.9), max(abs(w.{col} - o.{col})),
                   avg((w.{n} <> o.{n})::INT)
            FROM {with_t} w
            JOIN read_parquet('{(OUT / f'{without}.parquet').as_posix()}') o USING (zone_id, year, bin)
            WHERE w.{col} IS NOT NULL AND o.{col} IS NOT NULL
        """).fetchone()
        print(f"   {name}: {r[0]:,} cells, mean |diff| {r[1]:.4f}, median {r[2]:.4f}, "
              f"p90 {r[3]:.4f}, max {r[4]:.4f}; year count changed in {100*r[5]:.1f}%")

    print("\n   labels, every zone-year, with against without the exclusion:")
    rows = con.execute(f"""
        WITH w AS (SELECT *, percent_rank() OVER (PARTITION BY field_id, year ORDER BY label_ndvi) AS pr
                   FROM read_parquet('{OUT.as_posix()}/label_[0-9][0-9].parquet')),
             o AS (SELECT *, percent_rank() OVER (PARTITION BY field_id, year ORDER BY label_ndvi) AS pr
                   FROM read_parquet('{OUT.as_posix()}/label_noevent_*.parquet'))
        SELECT CASE WHEN w.year IN ({HELD}) THEN 'held-out' ELSE 'other' END AS grp,
               count(*), avg(abs(w.label_ndvi - o.label_ndvi)), quantile_cont(abs(w.label_ndvi - o.label_ndvi), 0.9),
               avg(((w.pr <= 0.10) <> (o.pr <= 0.10))::INT)
        FROM w JOIN o USING (zone_id, year)
        WHERE w.year <> 2020
        GROUP BY grp ORDER BY grp
    """).fetchall()
    for grp, n, mean_diff, p90, flip in rows:
        print(f"   {grp:<9} {n:>10,} zone-years, mean |diff| {mean_diff:.4f}, p90 {p90:.4f}, "
              f"bottom-decile membership flips for {100*flip:.2f}%")
    con.close()


def crop_correlation():
    print("\n2. Corn versus soybean relative standing", flush=True)
    con = bb.connect()
    con.execute(f"""
        CREATE TEMP TABLE zcy AS
        SELECT zone_id, cdl_code, year, avg(rel_ndvi) AS m
        FROM read_parquet('{OUT.as_posix()}/baseline_*.parquet')
        WHERE bin <= {config.LABEL_BINS[1]} AND rel_ndvi IS NOT NULL
        GROUP BY ALL
    """)
    con.execute("""
        CREATE TEMP TABLE zc AS
        SELECT zone_id, cdl_code, avg(m) AS all_years,
               avg(m) FILTER (WHERE k <= n / 2.0) AS early,
               avg(m) FILTER (WHERE k > n / 2.0) AS late, max(n) AS n
        FROM (SELECT *, row_number() OVER (PARTITION BY zone_id, cdl_code ORDER BY year) AS k,
                        count(*) OVER (PARTITION BY zone_id, cdl_code) AS n FROM zcy)
        GROUP BY zone_id, cdl_code
    """)
    # Two registry crops, compared by position rather than by name (CLAUDE.md rule 5).
    crop_a, crop_b = crops.codes()[0], crops.codes()[1]
    con.execute(f"""
        CREATE TEMP TABLE zc_wide AS
        SELECT zone_id,
               max(all_years) FILTER (WHERE cdl_code = {crop_a}) AS a_all,
               max(all_years) FILTER (WHERE cdl_code = {crop_b}) AS b_all,
               max(early) FILTER (WHERE cdl_code = {crop_a} AND n >= 2) AS a_early,
               max(late)  FILTER (WHERE cdl_code = {crop_a} AND n >= 2) AS a_late,
               max(early) FILTER (WHERE cdl_code = {crop_b} AND n >= 2) AS b_early,
               max(late)  FILTER (WHERE cdl_code = {crop_b} AND n >= 2) AS b_late
        FROM zc GROUP BY zone_id
    """)
    print(f"   relative NDVI averaged over bins 0 to {config.LABEL_BINS[1]}, one value per zone per crop\n")
    print(f"   {'pair':<44} {'zones':>9} {'Pearson':>8} {'Spearman':>9}")
    for label, a, b in (
        (f"{NAMES[crop_a]} years vs {NAMES[crop_b]} years", "a_all", "b_all"),
        (f"reference: earlier vs later {NAMES[crop_a]} years", "a_early", "a_late"),
        (f"reference: earlier vs later {NAMES[crop_b]} years", "b_early", "b_late"),
    ):
        n, pearson = con.execute(
            f"SELECT count(*), corr({a}, {b}) FROM zc_wide WHERE {a} IS NOT NULL AND {b} IS NOT NULL"
        ).fetchone()
        spearman = con.execute(f"""
            SELECT corr(ra, rb) FROM (
                SELECT rank() OVER (ORDER BY {a}) AS ra, rank() OVER (ORDER BY {b}) AS rb
                FROM zc_wide WHERE {a} IS NOT NULL AND {b} IS NOT NULL)
        """).fetchone()[0]
        print(f"   {label:<44} {n:>9,} {pearson:>8.3f} {spearman:>9.3f}")
    con.close()


def greenup_spread():
    print("\n3. Green-up spread around the NASS 50% planted anchor", flush=True)
    con = bb.connect()
    bb.zone_obs_view(con)
    crop_cols = ", ".join(f"crop_{y}" for y in config.YEARS)
    con.execute(f"""
        CREATE TEMP TABLE field_crop AS
        SELECT field_id, CAST(replace(k, 'crop_', '') AS INTEGER) AS year, cdl_code
        FROM (UNPIVOT fields ON {crop_cols} INTO NAME k VALUE cdl_code)
    """)
    con.execute("CREATE TEMP TABLE planting AS SELECT * FROM read_csv('orbitalscout/frozen/planting_dates.csv')")
    # Every clear field-date, including those before planting, so the curve has a floor.
    con.execute(f"""
        CREATE TEMP TABLE curve AS
        SELECT o.field_id, o.year, o.date, median(o.ndvi) AS med
        FROM zone_obs o
        JOIN (SELECT field_id, count(*) AS n FROM zones GROUP BY field_id) z USING (field_id)
        GROUP BY o.field_id, o.year, o.date
        HAVING count(*) >= {config.MIN_FIELD_CLEAR_FRAC} * any_value(z.n)
    """)
    con.execute("""
        CREATE TEMP TABLE greenup AS
        WITH lvl AS (
            SELECT field_id, year, min(med) + 0.5 * (max(med) - min(med)) AS level,
                   min(date) AS first_date
            FROM curve GROUP BY field_id, year
        ),
        crossing AS (
            SELECT c.field_id, c.year, min(c.date) AS greenup_date
            FROM curve c JOIN lvl USING (field_id, year)
            WHERE c.med >= lvl.level GROUP BY c.field_id, c.year
        )
        SELECT l.field_id, l.year, fc.cdl_code, x.greenup_date,
               x.greenup_date = l.first_date AS unidentifiable,
               date_diff('day', CAST(p.fifty_pct_planted AS DATE), CAST(x.greenup_date AS DATE)) AS days
        FROM lvl l
        JOIN crossing x USING (field_id, year)
        JOIN field_crop fc USING (field_id, year)
        JOIN planting p ON p.cdl_code = fc.cdl_code AND p.year = l.year
    """)
    print("   days from the NASS 50% planted date to field green-up\n")
    print(f"   {'crop':<9} {'year':>5} {'field-years':>12} {'unidentifiable':>15} {'p10':>6} {'median':>7} {'p90':>6}")
    for code, year, n, unident, p10, med, p90 in con.execute("""
        SELECT cdl_code, year, count(*), avg(unidentifiable::INT),
               quantile_cont(days, 0.1) FILTER (WHERE NOT unidentifiable),
               median(days) FILTER (WHERE NOT unidentifiable),
               quantile_cont(days, 0.9) FILTER (WHERE NOT unidentifiable)
        FROM greenup GROUP BY cdl_code, year ORDER BY cdl_code, year
    """).fetchall():
        print(f"   {NAMES[code]:<9} {year:>5} {n:>12,} {100*unident:>14.1f}% "
              f"{p10:>6.0f} {med:>7.0f} {p90:>6.0f}")
    for code, n, p10, med, p90, iqr in con.execute("""
        SELECT cdl_code, count(*) FILTER (WHERE NOT unidentifiable),
               quantile_cont(days, 0.1) FILTER (WHERE NOT unidentifiable),
               median(days) FILTER (WHERE NOT unidentifiable),
               quantile_cont(days, 0.9) FILTER (WHERE NOT unidentifiable),
               quantile_cont(days, 0.75) FILTER (WHERE NOT unidentifiable)
                 - quantile_cont(days, 0.25) FILTER (WHERE NOT unidentifiable)
        FROM greenup GROUP BY cdl_code ORDER BY cdl_code
    """).fetchall():
        print(f"   {NAMES[code]} all years: {n:,} identifiable field-years, median {med:.0f} days, "
              f"p10 {p10:.0f}, p90 {p90:.0f}, interquartile range {iqr:.0f} days")
    con.close()


if __name__ == "__main__":
    only = [a for a in sys.argv[1:] if a.isdigit()]
    if not only or "1" in only:
        derecho_sensitivity()
    if not only or "2" in only:
        crop_correlation()
    if not only or "3" in only:
        greenup_spread()
