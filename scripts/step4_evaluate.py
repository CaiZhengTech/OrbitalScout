"""Step 4: measure the ranking against the nulls. SPEC Section 10.

Assembles one frame per held-out year carrying the label, the secondary label,
and one score per method, then reports precision@k with its ceiling, recall,
false positive rate and lift, under both labels, at four budgets, over two
populations.

Two population decisions are made here rather than in the modules, because
they are about this run rather than about the metric.

**Ground truth is computed before the methods are intersected.** The label is
the bottom decile among zone-years that have a label at all. Restricting first
and labelling second would make the decile depend on which methods happen to
be scorable, and B1b's coverage would then define ground truth.

**Every method is scored on the same zone-years.** B1b cannot score a zone
whose crop has not been grown before, and B1a and B2 cannot score a zone with
no prior years. Comparing a method on its own scorable subset against another
on a different subset is not a comparison. So the head-to-head runs on the
intersection, and the share that costs is reported. The realised base rate on
the intersection is measured rather than assumed, since dropping zones changes
it away from the decile it was constructed at.

Run:
    python scripts/step4_evaluate.py
"""

import os
import pathlib
import sys
import time

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import baselines, config, evaluate, label, rank, signals, split  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_baseline as bb  # noqa: E402

B2_K = range(2, 8)   # SPEC Section 10: k-means into 2 to 7 zones

# Two readings of "what commercial platforms ship", both reported. `b2h` is the
# static multi-year management zone map. `b2s` clusters this season's own level,
# which is the stronger comparison and the fair one, since S1 also reads the
# current season. SPEC Section 10 names the method and not the period.
B2_VARIANTS = {"b2h": "prior_level", "b2s": "season_level"}

OUT = pathlib.Path("data/eval")


def connect():
    con = duckdb.connect()
    con.execute("SET memory_limit = '2GB'")
    con.execute(f"SET temp_directory = '{pathlib.Path('data/duckdb_tmp').as_posix()}'")
    return con


def load(con):
    """The scored frame for the held-out years, and the B1b history for all years."""
    floor = config.MIN_PRIOR_YEARS
    feat_lo, feat_hi = config.FEATURE_BINS
    label_lo, label_hi = config.LABEL_BINS
    held = ", ".join(str(y) for y in config.HELD_OUT_YEARS)

    # B1a's quantity, and B2's input: the multi-year mean relative index over
    # strictly prior years. This is the feature baseline itself.
    con.execute(f"""
        CREATE VIEW prior_level AS
        SELECT zone_id, field_id, year, avg(baseline_ndvi) AS prior_level
        FROM read_parquet('{bb.chunks('baseline')}')
        WHERE bin BETWEEN {feat_lo} AND {feat_hi} AND n_prior_years >= {floor}
        GROUP BY 1, 2, 3
    """)

    # The other input B2 could have: this season's own level in the feature
    # window, with no baseline subtracted. Commercial platforms ship in-season
    # index maps as well as static multi-year zone maps, and S1 reads the
    # current season, so scoring B2 only on history would handicap it in a way
    # SPEC Section 10 never asked for. Both variants are reported. No support
    # floor, because a level needs no history to be measured.
    con.execute(f"""
        CREATE VIEW season_level AS
        SELECT zone_id, field_id, year, avg(rel_ndvi) AS season_level
        FROM read_parquet('{bb.chunks('baseline')}')
        WHERE bin BETWEEN {feat_lo} AND {feat_hi} AND rel_ndvi IS NOT NULL
        GROUP BY 1, 2, 3
    """)

    # B1b's history: the label-window residual against the STRICTLY PRIOR
    # baseline, every year. Not the leave-one-year-out residual the label uses,
    # which for 2022 includes 2024 and would have let the null read the year it
    # is predicting. Open item 10b.
    print("reading B1b history over every year ...", flush=True)
    started = time.time()
    history = con.execute(f"""
        SELECT zone_id, year, any_value(cdl_code) AS cdl_code,
               avg(residual_ndvi) AS residual
        FROM read_parquet('{bb.chunks('baseline')}')
        WHERE bin BETWEEN {label_lo} AND {label_hi} AND n_prior_years >= {floor}
        GROUP BY 1, 2
    """).df()
    print(f"  {len(history):,} zone-years in {time.time() - started:.0f}s", flush=True)

    print("reading the held-out labels, features and levels ...", flush=True)
    started = time.time()
    frame = con.execute(f"""
        SELECT l.zone_id, l.field_id, l.year, l.cdl_code,
               l.label_ndvi, l.level_ndvi, f.feature_ndvi,
               p.prior_level, s.season_level
        FROM read_parquet('{bb.chunks('label')}') l
        LEFT JOIN read_parquet('{bb.chunks('feature')}') f USING (zone_id, field_id, year)
        LEFT JOIN prior_level p USING (zone_id, field_id, year)
        LEFT JOIN season_level s USING (zone_id, field_id, year)
        WHERE l.year IN ({held})
          AND l.label_ndvi IS NOT NULL AND l.level_ndvi IS NOT NULL
    """).df()
    print(f"  {len(frame):,} zone-years in {time.time() - started:.0f}s", flush=True)
    return frame, history


def score(frame, history):
    """One column per method. Larger is more urgent, for every one of them."""
    print("attaching the prior same-crop residual for B1b ...", flush=True)
    frame = baselines.prior_same_crop(frame, history)
    frame["s1"] = signals.s1_temporal_anomaly(frame)
    frame["b1a"] = baselines.b1a_level_persistence(frame)
    frame["b1b"] = baselines.b1b_anomaly_persistence(frame)
    for prefix, column in B2_VARIANTS.items():
        for k in B2_K:
            t = time.time()
            frame[f"{prefix}_k{k}"] = baselines.b2_ndvi_kmeans(frame, k=k, level_column=column)
            print(f"  {prefix} k={k} on {column} in {time.time() - t:.0f}s", flush=True)
    return frame


def methods():
    return (["s1", "b1a", "b1b"]
            + [f"{p}_k{k}" for p in B2_VARIANTS for k in B2_K])


def b2_families():
    return list(B2_VARIANTS)


def report_coverage(frame, comparable):
    print(f"\nlabelled zone-years in the held-out years: {len(frame):,}")
    print("share each method can score, before the intersection:")
    for name in methods():
        share = frame[name].notna().mean()
        print(f"  {name:<8} {100 * share:5.1f}%")
    kept = 100 * len(comparable) / len(frame)
    print(f"\nscored by every method, the comparison population: "
          f"{len(comparable):,} ({kept:.1f}%)")


def budgets():
    yield f"{config.SCOUTING_BUDGET_ZONES} zones", {"zones": config.SCOUTING_BUDGET_ZONES}
    for f in config.EVAL_FRACTIONS:
        yield f"{f:.0%} of field", {"fraction": f}


def table(marked, label_name, population):
    """Every method at every budget, for one label and one population."""
    print(f"\n{label_name} label, {population}")
    print(f"  {'budget':<14} {'method':<8} {'base':>6} {'prec':>7} {'ceil':>7} "
          f"{'of ceil':>8} {'recall':>7} {'FPR':>6} {'lift':>6} {'max':>6}")
    # Rank once per method, then walk the budgets. Ranking inside the budget
    # loop would sort two million rows 60 times instead of 15.
    results = {}
    keep = ["zone_id", "field_id", "year", "is_positive"]
    for name in methods():
        # Slice to the columns the ranking needs. Sorting the full frame with
        # all fifteen score columns attached costs four times the memory for
        # nothing, and this project has been killed by working sets that
        # scaled with the dataset rather than with the answer four times now.
        ranked = rank.rank_within_field(marked[keep + [name]], score_column=name)
        for budget_name, kwargs in budgets():
            results[(budget_name, name)] = evaluate.metrics(ranked, **kwargs)
    for budget_name, _ in budgets():
        for name in methods():
            got = results[(budget_name, name)]
            print(f"  {budget_name:<14} {name:<8} {got['base_rate']:>6.3f} "
                  f"{got['precision']:>7.4f} {got['precision_ceiling']:>7.4f} "
                  f"{got['fraction_of_ceiling']:>8.3f} {got['recall']:>7.4f} "
                  f"{got['false_positive_rate']:>6.4f} "
                  f"{got['lift_over_random']:>6.2f} {got['lift_ceiling']:>6.2f}")
    return results


def report_lift(results):
    """The comparisons that carry information: ranker against ranker.

    Each B2 family is taken at its **best** k for this budget and label. Picking
    a baseline's hyperparameter after seeing results is normally cheating; here
    it is cheating in the baseline's favour, which makes our own claim
    conservative rather than flattering.
    """
    print("\n  lift of S1 over each null, at each budget (above 1.00 is S1 ahead)")
    print(f"  {'budget':<14} {'over B1a':>9} {'over B1b':>9} "
          f"{'over B2 hist':>13} {'k':>3} {'over B2 season':>15} {'k':>3}")
    for budget_name, _ in budgets():
        s1 = results[(budget_name, "s1")]
        cells = []
        for prefix in b2_families():
            best_k = max(B2_K, key=lambda k: results[(budget_name, f"{prefix}_k{k}")]["precision"])
            cells.append((evaluate.lift_over(s1, results[(budget_name, f"{prefix}_k{best_k}")]),
                          best_k))
        print(f"  {budget_name:<14} "
              f"{evaluate.lift_over(s1, results[(budget_name, 'b1a')]):>9.3f} "
              f"{evaluate.lift_over(s1, results[(budget_name, 'b1b')]):>9.3f} "
              f"{cells[0][0]:>13.3f} {cells[0][1]:>3} "
              f"{cells[1][0]:>15.3f} {cells[1][1]:>3}")


def report_years(comparable):
    """Each held-out season separately, as a spread. SPEC Section 10, Splits.

    Pooling the three hides a year that carried the result. The spread is the
    reported quantity, not the pooled number.
    """
    print("\nper-year spread, primary label, at the scouting budget")
    print(f"  {'year':>5} {'zone-years':>11} {'S1 prec':>8} {'ceiling':>8} "
          f"{'B1b prec':>9} {'S1 / B1b':>9} {'S1 / B2s':>9} {'k':>3}")
    keep = ["zone_id", "field_id", "year", "is_positive"]
    for year in config.HELD_OUT_YEARS:
        part = comparable[comparable["year"] == year].rename(columns={"primary": "is_positive"})
        got = {}
        for name in ["s1", "b1b"] + [f"b2s_k{k}" for k in B2_K]:
            ranked = rank.rank_within_field(part[keep + [name]], score_column=name)
            got[name] = evaluate.metrics(ranked, zones=config.SCOUTING_BUDGET_ZONES)
        best_k = max(B2_K, key=lambda k: got[f"b2s_k{k}"]["precision"])
        print(f"  {year:>5} {len(part):>11,} {got['s1']['precision']:>8.4f} "
              f"{got['s1']['precision_ceiling']:>8.4f} {got['b1b']['precision']:>9.4f} "
              f"{evaluate.lift_over(got['s1'], got['b1b']):>9.3f} "
              f"{evaluate.lift_over(got['s1'], got[f'b2s_k{best_k}']):>9.3f} {best_k:>3}")


def check_folds(frame):
    """G-1 on real data: the folds partition the fields and leak nothing.

    At Step 4 no estimator reads the fit set, so these folds separate nothing
    yet. That is worth demonstrating rather than asserting: the union of the
    test folds must reconstruct the year exactly, and no field may appear on
    both sides.
    """
    print("\nG-1, blocked splits on real data:")
    seen = {y: set() for y in config.HELD_OUT_YEARS}
    overlaps = dict.fromkeys(config.HELD_OUT_YEARS, 0)
    for year, _fold, fit, test in split.folds(frame):
        overlaps[year] += len(set(fit["field_id"]) & set(test["field_id"]))
        seen[year] |= set(test["field_id"])
    for test_year in config.HELD_OUT_YEARS:
        whole = set(frame.loc[frame["year"] == test_year, "field_id"])
        print(f"  {test_year}: {len(seen[test_year]):,} fields across "
              f"{split.N_FIELD_FOLDS} folds, {overlaps[test_year]} field overlaps "
              f"with any fit set, "
              f"{'partition exact' if seen[test_year] == whole else 'PARTITION BROKEN'}")


def build_scores():
    """Load, label and score. Cached, because the reporting gets iterated on.

    Scoring costs about eleven minutes, almost all of it the twelve k-means
    sweeps, and none of it changes when a report changes. Delete
    `data/eval/scored.parquet` to force a rescore.
    """
    cache = OUT / "scored.parquet"
    if cache.exists():
        print(f"reusing {cache}; delete it to rescore", flush=True)
        return pd.read_parquet(cache)

    con = connect()
    frame, history = load(con)
    con.close()
    print(f"loaded {len(frame):,} labelled zone-years, "
          f"{len(history):,} zone-years of B1b history")

    # Ground truth first, over everything that has a label, so that the decile
    # does not depend on which methods can score.
    frame = label.bottom_fraction(frame, "label_ndvi")
    frame = frame.rename(columns={"is_positive": "primary"})
    frame = label.bottom_fraction(frame, "level_ndvi")
    frame = frame.rename(columns={"is_positive": "secondary"})
    print(f"base rate over all labelled zone-years: "
          f"primary {frame['primary'].mean():.4f}, secondary {frame['secondary'].mean():.4f}")

    frame = score(frame, history)
    comparable = frame.dropna(subset=methods()).reset_index(drop=True)
    report_coverage(frame, comparable)
    comparable.to_parquet(cache, index=False)
    print(f"wrote {cache}")
    return comparable


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    comparable = build_scores()
    check_folds(comparable)
    report_years(comparable)

    for label_name, column in (("primary", "primary"), ("secondary", "secondary")):
        marked = comparable.rename(columns={column: "is_positive"})
        for population, subset in (
            ("all field-years", marked),
            ("field-years larger than the budget",
             evaluate.strict_subset(marked, zones=config.SCOUTING_BUDGET_ZONES)),
        ):
            results = table(subset, label_name, population)
            report_lift(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
