"""Step 3: rank zones by S1 alone. No model.

Reads the per-zone-year features from Step 2, scores them with S1, ranks within
each field-year and writes the ranking. Then reports two things:

  - what the budget looks like in practice, absolute and fractional;
  - whether the ranking reproduces the permanent soil map.

The second is the point of the whole project. D1 says ranking by absolute level
reproduces the soil map, and the residual is supposed to remove it. A leak would
show as a negative correlation between urgency and a zone's persistent standing,
urgent zones being the ones that are always poor.

Persistent standing is measured from years the strictly prior baseline never
saw. Correlating the score against the baseline it is computed from looks like
the same test and is not one: the score is baseline minus relative, and the
covariance of the residual with the baseline is minus the variance of the
baseline's own estimation noise, so a positive result is arithmetic rather than
evidence. That is the shared-estimation-error trap of open item 10b.

This is a sanity check on the premise, not the evaluation. Whether the ranking
is correct is precision@k against the label, and whether it beats the obvious
alternatives is lift over B1a and B1b. Both are Step 4.

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
        FROM read_parquet('{bb.chunks('feature')}')
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

    # D1: ranking by absolute level reproduces the permanent soil map, and the
    # residual is supposed to remove it. A leak would show as a NEGATIVE
    # correlation, urgent zones being the persistently poor ones.
    #
    # Persistent standing must come from years the baseline never saw.
    # Correlating the score against the baseline it is computed from is
    # guaranteed positive, because the score is baseline minus relative and
    # Cov(residual, baseline) is minus the variance of the baseline's own
    # estimation noise. That is the shared-estimation-error trap of open item
    # 10b, so later years are used instead.
    print("\nDoes the ranking reproduce the soil map? (D1)")
    print("  urgency in year t against persistent standing from years after t\n")
    print(f"  {'year':>5} {'standing from':>15} {'zone-years':>11} {'Pearson':>9} {'Spearman':>9}")
    lo, hi = config.FEATURE_BINS
    for year in bb.HELD_OUT:
        later = [y for y in bb.HELD_OUT if y > year]
        if not later:
            print(f"  {year:>5} {'none available':>15} {'-':>11} {'-':>9} {'-':>9}")
            continue
        years = ", ".join(str(y) for y in later)
        n, pearson, spearman = con.execute(f"""
            WITH standing AS (
                SELECT zone_id, avg(rel_ndvi) AS persistent
                FROM read_parquet('{bb.chunks('baseline')}')
                WHERE year IN ({years}) AND bin BETWEEN {lo} AND {hi}
                  AND rel_ndvi IS NOT NULL
                GROUP BY zone_id
            ),
            joined AS (
                SELECT r.score, s.persistent FROM r
                JOIN standing s USING (zone_id) WHERE r.year = {year}
            )
            SELECT count(*), corr(score, persistent),
                   (SELECT corr(a, b) FROM (
                        SELECT rank() OVER (ORDER BY score) AS a,
                               rank() OVER (ORDER BY persistent) AS b FROM joined))
            FROM joined
        """).fetchone()
        print(f"  {year:>5} {years:>15} {n:>11,} {pearson:>9.3f} {spearman:>9.3f}")
    print("\n  a soil-map leak would be negative; near zero is the residual working")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
