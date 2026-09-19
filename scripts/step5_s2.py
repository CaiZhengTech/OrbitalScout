"""Step 5, S2: measure it, then keep or cut it. SPEC Section 7 admission rule.

Reads the Step 4 scores, attaches the neighbourhood level, and answers one
question: does adding S2 to S1 improve lift over the B1b persistence null?

The prediction is on record in `docs/reviews/2026-09-18-step5-s2-prediction.md`,
committed before any S2 code existed. It says this combination will **not**
help, and that if it does the gain should concentrate in zones whose strictly
prior baseline rests on the fewest years. Both are checked here.

Everything is compared on the population where **every** method can score, so
rung 1 and rung 2 are not measured over different sets of zones. S2 is null for
a zone with fewer than three neighbours in its field-year.

Run:
    python scripts/step5_s2.py
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
METHODS = ("s1", "s2", "s1_s2", "b1b", "b2s_k7")


def budgets():
    yield f"{config.SCOUTING_BUDGET_ZONES} zones", {"zones": config.SCOUTING_BUDGET_ZONES}
    for fraction in config.EVAL_FRACTIONS:
        yield f"{fraction:.0%} of field", {"fraction": fraction}


def load():
    if not SCORED.exists():
        raise SystemExit("run scripts/step4_evaluate.py first")
    frame = pd.read_parquet(SCORED)
    frame["neighbour_level"] = signals.neighbour_mean(frame, "season_level")
    frame["s2"] = signals.s2_spatial_anomaly(frame)
    frame["s1_s2"] = rank.combine(frame, ["s1", "s2"])

    scorable = frame[list(METHODS)].notna().all(axis=1)
    print(f"Step 4 population: {len(frame):,} zone-years")
    print(f"  S2 scorable:     {frame['s2'].notna().sum():,} "
          f"({100 * frame['s2'].notna().mean():.1f}%), "
          f"the rest have fewer than {config.MIN_NEIGHBOURS} neighbours in their field-year")
    print(f"  compared here:   {int(scorable.sum()):,} ({100 * scorable.mean():.1f}%)")
    return frame[scorable].reset_index(drop=True)


def measure(frame, label_column):
    results = {}
    marked = frame.rename(columns={label_column: "is_positive"})
    for name in METHODS:
        ranked = rank.rank_within_field(marked[KEYS + [name]], score_column=name)
        for budget_name, kwargs in budgets():
            results[(budget_name, name)] = evaluate.metrics(ranked, **kwargs)
    return results


def report(results, label_name):
    print(f"\n{label_name} label")
    print(f"  {'budget':<14} {'method':<8} {'prec':>7} {'of ceil':>8} "
          f"{'lift/random':>12} {'lift over B1b':>14}")
    for budget_name, _ in budgets():
        for name in METHODS:
            got = results[(budget_name, name)]
            over_b1b = evaluate.lift_over(got, results[(budget_name, "b1b")])
            print(f"  {budget_name:<14} {name:<8} {got['precision']:>7.4f} "
                  f"{got['fraction_of_ceiling']:>8.3f} {got['lift_over_random']:>12.2f} "
                  f"{over_b1b:>14.3f}")

    print(f"\n  the admission rule: does S1+S2 beat S1 on lift over B1b?")
    print(f"  {'budget':<14} {'S1 over B1b':>12} {'S1+S2 over B1b':>16} "
          f"{'change':>9} {'verdict':>9}")
    verdicts = []
    for budget_name, _ in budgets():
        b1b = results[(budget_name, "b1b")]
        alone = evaluate.lift_over(results[(budget_name, "s1")], b1b)
        both = evaluate.lift_over(results[(budget_name, "s1_s2")], b1b)
        verdicts.append(both > alone)
        print(f"  {budget_name:<14} {alone:>12.3f} {both:>16.3f} "
              f"{100 * (both / alone - 1):>8.1f}% {'better' if both > alone else 'worse':>9}")
    return verdicts


def check_mechanism(frame):
    """Prediction 4: if S1+S2 helps, the gain concentrates where history is thin.

    Split by how many prior years the zone's feature baseline rests on. If the
    improvement is flat across that, the stated explanation is wrong and
    something else is going on, which would need finding before S2 ships.
    """
    con = duckdb.connect()
    con.execute("SET memory_limit = '2GB'")
    floor = config.MIN_PRIOR_YEARS
    lo, hi = config.FEATURE_BINS
    prior = con.execute(f"""
        SELECT zone_id, field_id, year, max(n_prior_years) AS n_prior_years
        FROM read_parquet('{bb.chunks('baseline')}')
        WHERE bin BETWEEN {lo} AND {hi} AND n_prior_years >= {floor}
        GROUP BY 1, 2, 3
    """).df()
    con.close()
    frame = frame.merge(prior, on=["zone_id", "field_id", "year"], how="left")

    print("\n  where does the change come from? by prior years behind the baseline")
    print(f"  {'n_prior':>8} {'zone-years':>11} {'S1 prec':>8} {'S1+S2 prec':>11} {'change':>9}")
    for n_prior, part in frame.groupby("n_prior_years"):
        marked = part.rename(columns={"primary": "is_positive"})
        got = {}
        for name in ("s1", "s1_s2"):
            ranked = rank.rank_within_field(marked[KEYS + [name]], score_column=name)
            got[name] = evaluate.metrics(ranked, zones=config.SCOUTING_BUDGET_ZONES)
        change = got["s1_s2"]["precision"] / got["s1"]["precision"] - 1
        print(f"  {int(n_prior):>8} {len(part):>11,} {got['s1']['precision']:>8.4f} "
              f"{got['s1_s2']['precision']:>11.4f} {100 * change:>8.1f}%")


def main():
    frame = load()
    primary = measure(frame, "primary")
    verdicts = report(primary, "primary")
    report(measure(frame, "secondary"), "secondary")
    check_mechanism(frame)

    print("\n" + "=" * 70)
    if any(verdicts):
        print("S1+S2 improves lift over B1b at "
              f"{sum(verdicts)} of {len(verdicts)} budgets.")
        print("Check the mechanism table above before admitting S2.")
    else:
        print("S2 did not improve lift over persistence at any budget.")
        print("The admission rule cuts it. Record the null result in RESULTS.md")
        print("and leave SIGNALS as S1 alone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
