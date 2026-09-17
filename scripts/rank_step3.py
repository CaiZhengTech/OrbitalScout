"""Step 3: rank zones by S1 alone. No model.

Reads the per-zone-year features from Step 2, scores them with S1, ranks within
each field-year and writes the ranking. Then reports two things:

  - what the budget looks like in practice, absolute and fractional;
  - whether the ranking reproduces the permanent soil map.

The second is the point of the whole project. D1 says ranking by absolute level
reproduces the soil map, and the residual is supposed to remove it. The zone's
own baseline, its persistent relative standing, is the soil map proxy, so the
correlation between the S1 score and that baseline says whether the residual
actually removed it. Near zero is the design working. This is a sanity check,
not the evaluation: precision@k and the null comparisons are Step 4.

Run:
    python scripts/rank_step3.py
"""

import os
import pathlib
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config, rank, signals  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_baseline as bb  # noqa: E402

OUT = pathlib.Path("data/rank")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit = '1GB'")
    con.execute("SET threads = 2")

    held = ", ".join(str(y) for y in bb.HELD_OUT)
    features = con.execute(f"""
        SELECT zone_id, field_id, year, cdl_code, feature_ndvi, feature_bin
        FROM read_parquet('{bb.OUT.as_posix()}/feature_*.parquet')
        WHERE year IN ({held})
    """).df()
    print(f"features for held-out years: {len(features):,} zone-years")

    features["score"] = signals.s1_temporal_anomaly(features)
    ranked = rank.rank_within_field(features)
    print(f"ranked: {len(ranked):,} zone-years "
          f"({len(features) - len(ranked):,} dropped for a missing score)")

    for year in bb.HELD_OUT:
        part = ranked[ranked["year"] == year]
        part.to_parquet(OUT / f"ranked_{year}.parquet", index=False)
    print(f"wrote {len(bb.HELD_OUT)} files to {OUT}")

    print("\nS1 score distribution by year (larger is more urgent):")
    print(f"  {'year':>5} {'zone-years':>11} {'p1':>8} {'p25':>8} {'median':>8} {'p75':>8} {'p99':>8}")
    con.register("r", ranked)
    for row in con.execute("""
        SELECT year, count(*), quantile_cont(score, 0.01), quantile_cont(score, 0.25),
               median(score), quantile_cont(score, 0.75), quantile_cont(score, 0.99)
        FROM r GROUP BY year ORDER BY year
    """).fetchall():
        year, n, *q = row
        print(f"  {year:>5} {n:>11,} " + " ".join(f"{v:>8.4f}" for v in q))

    print("\nwhat a budget selects, per field-year:")
    print(f"  {'budget':<16} {'zones chosen':>13} {'fields':>8} {'mean per field':>15}")
    for label, kwargs in (("20 zones", {"zones": 20}), ("5% of field", {"fraction": 0.05}),
                          ("10% of field", {"fraction": 0.10}), ("20% of field", {"fraction": 0.20})):
        top = rank.select_budget(ranked, **kwargs)
        groups = top.groupby(["field_id", "year"]).size()
        print(f"  {label:<16} {len(top):>13,} {len(groups):>8,} {groups.mean():>15.1f}")

    print("\nDoes the ranking reproduce the soil map? (D1)")
    print("  correlation between the S1 score and the zone's own persistent standing\n")
    print(f"  {'year':>5} {'zone-years':>11} {'Pearson':>9} {'Spearman':>9}")
    for year in bb.HELD_OUT:
        row = con.execute(f"""
            WITH standing AS (
                SELECT zone_id, year, avg(baseline_ndvi) AS persistent
                FROM read_parquet('{bb.OUT.as_posix()}/baseline_*.parquet')
                WHERE year = {year} AND bin BETWEEN {config.FEATURE_BINS[0]} AND {config.FEATURE_BINS[1]}
                  AND baseline_ndvi IS NOT NULL
                GROUP BY zone_id, year
            ),
            joined AS (
                SELECT r.score, s.persistent FROM r JOIN standing s
                  ON s.zone_id = r.zone_id AND s.year = r.year
            )
            SELECT count(*), corr(score, persistent),
                   (SELECT corr(a, b) FROM (SELECT rank() OVER (ORDER BY score) AS a,
                                                   rank() OVER (ORDER BY persistent) AS b
                                            FROM joined))
            FROM joined
        """).fetchone()
        n, pearson, spearman = row
        print(f"  {year:>5} {n:>11,} {pearson:>9.3f} {spearman:>9.3f}")
    print("\n  near zero means the residual removed the permanent soil signal, as D1 intends")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
