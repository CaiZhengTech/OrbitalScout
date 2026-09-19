"""Does the within-season trajectory add anything beyond the latest residual?

S4 velocity and S5 persistence are different summaries of one assumption. This
probes the assumption once, on data already on disk, before either is built.
Decisions and the prediction are in
`docs/reviews/2026-09-19-step5-trajectory-probe.md`, committed before this ran.

Not a substitute for the admission rule. Anything that survives here still gets
built test-first and still has to beat B1b. The probe decides what is worth
building.

Run:
    python scripts/step5_trajectory_probe.py
"""

import os
import pathlib
import sys

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config, evaluate, rank  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_baseline as bb  # noqa: E402

SCORED = pathlib.Path("data/eval/scored.parquet")
KEYS = ["zone_id", "field_id", "year", "is_positive"]

# Every summary is negated where needed so that larger means more urgent.
SUMMARIES = {
    "latest": "residual in the highest supported bin (S1 today)",
    "mean": "mean residual across supported bins",
    "slope": "OLS slope against bin, negated (S4 velocity)",
    "n_below": "count of bins with a negative residual (S5 persistence)",
}


def budgets():
    yield f"{config.SCOUTING_BUDGET_ZONES} zones", {"zones": config.SCOUTING_BUDGET_ZONES}
    for fraction in config.EVAL_FRACTIONS:
        yield f"{fraction:.0%} of field", {"fraction": fraction}


def load():
    lo, hi = config.FEATURE_BINS
    floor = config.MIN_PRIOR_YEARS
    held = ", ".join(str(y) for y in config.HELD_OUT_YEARS)
    con = duckdb.connect()
    con.execute("SET memory_limit = '2GB'")
    frame = con.execute(f"""
        WITH traj AS (
            SELECT zone_id, field_id, year,
                   arg_max(residual_ndvi, bin) AS latest,
                   avg(residual_ndvi) AS mean_resid,
                   regr_slope(residual_ndvi, bin) AS raw_slope,
                   count(*) FILTER (residual_ndvi < 0) AS n_below_raw,
                   count(*) AS n_bins
            FROM read_parquet('{bb.chunks('baseline')}')
            WHERE bin BETWEEN {lo} AND {hi} AND n_prior_years >= {floor}
              AND residual_ndvi IS NOT NULL AND year IN ({held})
            GROUP BY 1, 2, 3
        )
        SELECT s.zone_id, s.field_id, s.year, s.primary, s.secondary, s.s1, s.b1b,
               t.latest, t.mean_resid, t.raw_slope, t.n_below_raw, t.n_bins
        FROM read_parquet('{SCORED.as_posix()}') s
        JOIN traj t USING (zone_id, field_id, year)
    """).df()
    con.close()

    # Urgency convention: larger is more urgent, for every column.
    frame["latest"] = -frame["latest"]
    frame["mean"] = -frame["mean_resid"]
    frame["slope"] = -frame["raw_slope"]           # falling through the season
    frame["n_below"] = frame["n_below_raw"].astype(float)
    for name in SUMMARIES:
        frame[f"s1_{name}"] = rank.combine(frame, ["s1", name])
    return frame


def sanity(frame):
    """`latest` is S1's feature by another route. It had better agree."""
    rho = frame["latest"].rank().corr(frame["s1"].rank())
    print(f"\nSpearman(latest, s1) = {rho:.6f}  "
          f"({'the same feature, recomputed' if rho > 0.9999 else 'MISMATCH, investigate'})")


def partial_rank_correlations(frame):
    """Does each summary predict the label after `latest` is already known?

    Partial correlation from the 3 by 3 rank-correlation matrix, which is
    arithmetic rather than a fit, so it needs no split. The label here is the
    continuous primary label residual, not the decile, because a correlation
    against a binary is attenuated for reasons that have nothing to do with the
    question.
    """
    print("\npartial rank correlation with the label, controlling for `latest`")
    print(f"  {'summary':<10} {'r(x, y)':>9} {'r(x, latest)':>13} {'partial':>9}")
    ranked = {name: frame[name].rank() for name in SUMMARIES}
    # The label residual, ranked. Lower residual is worse, so negate to match
    # the urgency convention of the summaries.
    y = (-frame["label_residual"]).rank()
    z = ranked["latest"]
    r_zy = z.corr(y)
    for name in SUMMARIES:
        if name == "latest":
            continue
        x = ranked[name]
        r_xy, r_xz = x.corr(y), x.corr(z)
        partial = ((r_xy - r_xz * r_zy)
                   / ((1 - r_xz ** 2) ** 0.5 * (1 - r_zy ** 2) ** 0.5))
        print(f"  {name:<10} {r_xy:>9.3f} {r_xz:>13.3f} {partial:>9.3f}")
    print(f"  {'latest':<10} {r_zy:>9.3f} {1.0:>13.3f} {'-':>9}")


def measure(frame, label_column="primary"):
    marked = frame.rename(columns={label_column: "is_positive"})
    names = ["s1", "b1b"] + list(SUMMARIES) + [f"s1_{n}" for n in SUMMARIES]
    results = {}
    for name in names:
        ranked = rank.rank_within_field(marked[KEYS + [name]], score_column=name)
        for budget_name, kwargs in budgets():
            results[(budget_name, name)] = evaluate.metrics(ranked, **kwargs)
    return results


def report(results):
    print("\nprimary label, lift over B1b")
    print(f"  {'budget':<14} {'S1':>7} " + " ".join(f"{n:>9}" for n in SUMMARIES)
          + "   " + " ".join(f"{'+' + n:>9}" for n in SUMMARIES))
    for budget_name, _ in budgets():
        b1b = results[(budget_name, "b1b")]
        alone = " ".join(
            f"{evaluate.lift_over(results[(budget_name, n)], b1b):>9.3f}" for n in SUMMARIES)
        combo = " ".join(
            f"{evaluate.lift_over(results[(budget_name, f's1_{n}')], b1b):>9.3f}"
            for n in SUMMARIES)
        s1 = evaluate.lift_over(results[(budget_name, "s1")], b1b)
        print(f"  {budget_name:<14} {s1:>7.3f} {alone}   {combo}")

    print("\n  change against S1 alone, when combined at rung 2")
    print(f"  {'budget':<14} " + " ".join(f"{'+' + n:>10}" for n in SUMMARIES))
    for budget_name, _ in budgets():
        b1b = results[(budget_name, "b1b")]
        s1 = evaluate.lift_over(results[(budget_name, "s1")], b1b)
        cells = " ".join(
            f"{100 * (evaluate.lift_over(results[(budget_name, f's1_{n}')], b1b) / s1 - 1):>9.1f}%"
            for n in SUMMARIES)
        print(f"  {budget_name:<14} {cells}")


def main():
    if not SCORED.exists():
        raise SystemExit("run scripts/step4_evaluate.py first")
    frame = load()
    print(f"{len(frame):,} zone-years with a feature-window trajectory")
    print(f"  bins per zone-year: median {frame['n_bins'].median():.0f}, "
          f"mean {frame['n_bins'].mean():.2f}")
    sanity(frame)

    con = duckdb.connect()
    con.execute("SET memory_limit = '2GB'")
    labels = con.execute(f"""
        SELECT zone_id, field_id, year, label_ndvi AS label_residual
        FROM read_parquet('{bb.chunks('label')}')
        WHERE year IN ({", ".join(str(y) for y in config.HELD_OUT_YEARS)})
    """).df()
    con.close()
    frame = frame.merge(labels, on=["zone_id", "field_id", "year"], how="inner")
    partial_rank_correlations(frame)
    report(measure(frame))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
