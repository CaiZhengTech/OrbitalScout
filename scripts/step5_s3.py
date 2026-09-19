"""Step 5, S3: measure it, then keep or cut it. SPEC Section 7 admission rule.

The prediction is on record in `docs/reviews/2026-09-19-step5-s3-prediction.md`,
committed before any S3 code existed. It makes three falsifiable claims and
names a fourth diagnostic that decides what a null result would mean. All four
are checked here.

Reads the Step 4 scores for labels, S1 and B1b, and joins the rebuilt feature
table for NDRE and NDWI. Every method is compared on the population where all
of them can score.

Run:
    python scripts/step5_s3.py
"""

import os
import pathlib
import sys

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config, evaluate, rank, signals  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_baseline as bb  # noqa: E402

SCORED = pathlib.Path("data/eval/scored.parquet")
KEYS = ["zone_id", "field_id", "year", "is_positive"]
METHODS = ("s1", "s3", "s1_s3", "mil", "b1b")
LABELS = {"s1": "S1 alone", "s3": "S3 alone", "s1_s3": "S1 + S3 (rung 2)",
          "mil": "all three as a level", "b1b": "B1b persistence null"}


def budgets():
    yield f"{config.SCOUTING_BUDGET_ZONES} zones", {"zones": config.SCOUTING_BUDGET_ZONES}
    for fraction in config.EVAL_FRACTIONS:
        yield f"{fraction:.0%} of field", {"fraction": fraction}


def load():
    if not SCORED.exists():
        raise SystemExit("run scripts/step4_evaluate.py first")
    con = duckdb.connect()
    con.execute("SET memory_limit = '2GB'")
    frame = con.execute(f"""
        SELECT s.zone_id, s.field_id, s.year, s.primary, s.secondary, s.s1, s.b1b,
               f.feature_ndvi, f.feature_ndre, f.feature_ndwi
        FROM read_parquet('{SCORED.as_posix()}') s
        JOIN read_parquet('{bb.chunks('feature')}') f USING (zone_id, field_id, year)
    """).df()
    con.close()

    frame["s3"] = signals.s3_multi_index_divergence(frame)
    frame["mil"] = signals.multi_index_level(frame)
    frame["s1_s3"] = rank.combine(frame, ["s1", "s3"])

    scorable = frame[list(METHODS)].notna().all(axis=1)
    print(f"Step 4 population joined to the rebuilt features: {len(frame):,} zone-years")
    print(f"  scored by every method: {int(scorable.sum()):,} "
          f"({100 * scorable.mean():.1f}%)")
    return frame[scorable].reset_index(drop=True)


def check_cancellation(frame):
    """Prediction 2: the rung 2 sum throws NDVI away.

    z(S1) is minus the NDVI z-score and z(S3) is roughly the NDVI z-score less
    the mean of the two early ones, so the sum should be close to minus that
    mean. If it is, S1+S3 is not "S1 plus extra information", it is a different
    signal that discarded the index the label is built from.
    """
    early = -(rank.zscore_within_field(frame, "feature_ndre")
              + rank.zscore_within_field(frame, "feature_ndwi")) / 2
    # Spearman is Pearson on ranks. Computed that way rather than adding scipy,
    # which pandas needs for method="spearman", for a single number.
    ranks = frame["s1_s3"].rank()
    rho = ranks.corr(early.rank())
    print("\nprediction 2, does NDVI cancel in S1+S3?")
    print(f"  Spearman(S1+S3, -mean(z_ndre, z_ndwi)) = {rho:.3f}  "
          f"(predicted above 0.90: {'held' if rho > 0.90 else 'FAILED'})")
    print(f"  Spearman(S1+S3, S1)                    = {ranks.corr(frame['s1'].rank()):.3f}")
    print(f"  Spearman(S3, S1)                       = "
          f"{frame['s3'].rank().corr(frame['s1'].rank()):.3f}")
    return rho


def measure(frame, label_column):
    marked = frame.rename(columns={label_column: "is_positive"})
    results = {}
    for name in METHODS:
        ranked = rank.rank_within_field(marked[KEYS + [name]], score_column=name)
        for budget_name, kwargs in budgets():
            results[(budget_name, name)] = evaluate.metrics(ranked, **kwargs)
    return results


def report(results, label_name):
    print(f"\n{label_name} label")
    print(f"  {'budget':<14} {'method':<7} {'prec':>7} {'of ceil':>8} "
          f"{'lift/random':>12} {'lift over B1b':>14}  what it is")
    for budget_name, _ in budgets():
        for name in METHODS:
            got = results[(budget_name, name)]
            over = evaluate.lift_over(got, results[(budget_name, "b1b")])
            print(f"  {budget_name:<14} {name:<7} {got['precision']:>7.4f} "
                  f"{got['fraction_of_ceiling']:>8.3f} {got['lift_over_random']:>12.2f} "
                  f"{over:>14.3f}  {LABELS[name]}")


def admission(results):
    print("\n  the admission rule: does S1+S3 beat S1 on lift over B1b?")
    print(f"  {'budget':<14} {'S1':>8} {'S1+S3':>8} {'change':>9} {'verdict':>9}"
          f"{'':>4}{'all three':>10} {'vs S1':>8}")
    verdicts = []
    for budget_name, _ in budgets():
        b1b = results[(budget_name, "b1b")]
        alone = evaluate.lift_over(results[(budget_name, "s1")], b1b)
        both = evaluate.lift_over(results[(budget_name, "s1_s3")], b1b)
        level = evaluate.lift_over(results[(budget_name, "mil")], b1b)
        verdicts.append(both > alone)
        print(f"  {budget_name:<14} {alone:>8.3f} {both:>8.3f} "
              f"{100 * (both / alone - 1):>8.1f}% {'better' if both > alone else 'worse':>9}"
              f"{'':>4}{level:>10.3f} {100 * (level / alone - 1):>7.1f}%")
    return verdicts


def main():
    frame = load()
    check_cancellation(frame)
    primary = measure(frame, "primary")
    report(primary, "primary")
    verdicts = admission(primary)
    report(measure(frame, "secondary"), "secondary")

    print("\n" + "=" * 78)
    if any(verdicts):
        print(f"S1+S3 improves lift over B1b at {sum(verdicts)} of {len(verdicts)} budgets.")
    else:
        print("S3 did not improve lift over persistence at any budget.")
        print("The admission rule cuts it. Whether that is a verdict on S3's")
        print("contrast form or on NDRE and NDWI themselves is answered by the")
        print("'all three as a level' column above, per prediction 4.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
