"""Tests for the split rules. CLAUDE.md calls this the most valuable test here.

A leak here does not raise. It makes every number better and leaves no trace,
so each test below is written against a mutation that was shown to survive the
rest of the suite, or against code that did not exist when it was written.

What is deliberately **not** re-asserted here, because `tests/test_baseline.py`
already covers it and a second copy would only drift:

  - the feature baseline uses strictly prior years
    (`test_baseline_uses_only_strictly_prior_years`, and reversing the window
    frame to CURRENT ROW fails six tests)
  - the label baseline is leave-one-year-out and does include later years
    (`test_label_baseline_uses_every_other_year_but_never_its_own`, and making
    it strictly prior fails four)
  - the feature window ends before the gap and the label window starts after it
    (`test_feature_window_ends_before_the_gap_and_label_window_starts_after_it`)

What was **not** covered, and is the reason this file exists: those two rules
are enforced on two views, and nothing checked that the label is actually read
from the right one. Pointing `zone_year_label` at the feature baseline passed
all 85 tests. Feature and label would then subtract one estimate and share its
error, precision@k would improve, and nothing would raise.
"""

import duckdb
import pandas as pd
import pytest

from orbitalscout import baseline, config, split

CORN = 1
FEATURE_GDD = 1250   # bin 6 at a 200 GDD width, inside FEATURE_BINS
LABEL_GDD = 1650     # bin 8, inside LABEL_BINS


def outcome_con(values_by_year):
    """Zone 101 takes a value per year in both windows; 102 and 103 hold 0.5.

    The field median is then 0.5, so zone 101's relative index in every bin is
    exactly its value minus 0.5. Each year contributes one observation to the
    feature window and one to the label window.
    """
    obs, gdd = [], {}
    for year, value in values_by_year.items():
        for tag, g in (("06-01", FEATURE_GDD), ("08-01", LABEL_GDD)):
            date = f"{year}-{tag}"
            gdd[date] = g
            obs += [(101, 1, year, date, value),
                    (102, 1, year, date, 0.5),
                    (103, 1, year, date, 0.5)]

    con = duckdb.connect()
    zone_obs = pd.DataFrame(obs, columns=["zone_id", "field_id", "year", "date", "ndvi"])
    zone_obs["ndre"] = zone_obs["ndvi"]
    zone_obs["ndwi"] = zone_obs["ndvi"]
    con.register("zone_obs", zone_obs)
    con.register("fields", pd.DataFrame(
        [{"field_id": 1, **{f"crop_{y}": CORN for y in config.YEARS}}]))
    con.register("zones", pd.DataFrame(
        [(z, 1) for z in (101, 102, 103)], columns=["zone_id", "field_id"]))
    con.register("gdd", pd.DataFrame(
        [(CORN, d, g) for d, g in gdd.items()], columns=["cdl_code", "date", "gdd"]))

    baseline.build_views(con, width_gdd=200, min_field_clear_frac=0.0, events=())
    baseline.outcome_views(con)
    return con


def test_the_label_and_the_feature_are_read_from_different_baselines():
    """SPEC Section 10's circularity control, checked where it is consumed.

    2018 through 2021 sit at 0.6 and 2022 at 1.0, so the relative index is
    0.1, 0.1, 0.1, 0.1, 0.5. For 2021 the two estimators must disagree:

      feature: strictly prior 2018 to 2020, mean 0.1, residual 0.1 - 0.1 = 0.0
      label:   every year but 2021, mean (0.1+0.1+0.1+0.5)/4 = 0.2,
               residual 0.1 - 0.2 = -0.1

    Reading the label from the feature baseline would make both 0.0.
    """
    con = outcome_con({2018: 0.6, 2019: 0.6, 2020: 0.6, 2021: 0.6, 2022: 1.0})
    feature = con.execute(
        "SELECT feature_ndvi FROM zone_year_feature WHERE zone_id = 101 AND year = 2021"
    ).fetchone()[0]
    label = con.execute(
        "SELECT label_ndvi FROM zone_year_label WHERE zone_id = 101 AND year = 2021"
    ).fetchone()[0]

    assert feature == pytest.approx(0.0)
    assert label == pytest.approx(-0.1)
    assert label != pytest.approx(feature), "feature and label share one baseline"


def test_a_later_year_moves_the_label_but_never_the_feature():
    """The same fixture with 2022 changed. Only the label may respond."""
    low = outcome_con({2018: 0.6, 2019: 0.6, 2020: 0.6, 2021: 0.6, 2022: 1.0})
    high = outcome_con({2018: 0.6, 2019: 0.6, 2020: 0.6, 2021: 0.6, 2022: 2.0})

    def read(con, view, column):
        return con.execute(
            f"SELECT {column} FROM {view} WHERE zone_id = 101 AND year = 2021"
        ).fetchone()[0]

    assert read(low, "zone_year_feature", "feature_ndvi") == pytest.approx(
        read(high, "zone_year_feature", "feature_ndvi")
    ), "a later year reached the feature"
    assert read(low, "zone_year_label", "label_ndvi") != pytest.approx(
        read(high, "zone_year_label", "label_ndvi")
    ), "a later year did not reach the label"


# --- the field and year holdout -------------------------------------------

def zone_years(fields_and_sizes, years=(2020, 2021, 2022)):
    rows = [(f"z{f}_{i}", f, y)
            for f, n in fields_and_sizes.items()
            for i in range(n)
            for y in years]
    return pd.DataFrame(rows, columns=["zone_id", "field_id", "year"])


def test_no_field_used_to_fit_appears_in_the_test_set():
    """CLAUDE.md rule 1, first half. Adjacent zones are not independent."""
    frame = zone_years({1: 5, 2: 3, 3: 8, 4: 2, 5: 6, 6: 4})
    folds = split.field_folds(frame)
    for test_fold in range(split.N_FIELD_FOLDS):
        fit, test = split.split(frame, test_year=2022, test_fold=test_fold, folds=folds)
        assert set(fit["field_id"]) & set(test["field_id"]) == set()


def test_no_test_year_appears_in_any_fit_set():
    """CLAUDE.md rule 1, second half, and the deployable direction of it.

    Fit years are strictly before the test year, not merely different from it.
    A model fit on 2022 to score 2021 could not be run in 2021.
    """
    frame = zone_years({1: 5, 2: 3, 3: 8, 4: 2}, years=(2020, 2021, 2022))
    folds = split.field_folds(frame)
    for test_year in (2021, 2022):
        fit, test = split.split(frame, test_year=test_year, test_fold=0, folds=folds)
        assert set(test["year"]) == {test_year}
        assert max(fit["year"]) < test_year


def test_every_field_is_tested_exactly_once_across_the_folds():
    """A fold assignment that drops a field would shrink the test set silently."""
    frame = zone_years({f: f for f in range(1, 13)})
    folds = split.field_folds(frame)
    tested = [f for fold in range(split.N_FIELD_FOLDS)
              for f in split.split(frame, 2022, fold, folds)[1]["field_id"].unique()]
    assert sorted(tested) == sorted(frame["field_id"].unique())


def test_folds_are_balanced_by_zone_count_and_take_the_largest_field_first():
    """Field size spans 1 to 2,892 zones here, so balancing is not automatic.

    Sizes 5, 5, 5, 5, 20 into two folds, with the large field last by id so
    that id order and size order disagree. Largest first packs them 20 against
    20. Dealing them out by field id instead leaves 30 against 10, and so does
    counting fields rather than zones: both mutations were checked and both
    are caught here.

    Determinism is deliberately not tested separately. `groupby` returns groups
    in field id order and ties break on field id, so no mutation makes the
    assignment unstable without first making it unbalanced, and a test that
    cannot fail is worse than none.
    """
    frame = zone_years({1: 5, 2: 5, 3: 5, 4: 5, 5: 20})
    folds = split.field_folds(frame, n_folds=2)
    sizes = frame.groupby("field_id").size()
    per_fold = sorted(sizes[[f for f, k in folds.items() if k == fold]].sum()
                      for fold in range(2))
    assert per_fold[1] <= 1.5 * per_fold[0], f"folds are lopsided: {per_fold}"


def test_held_out_years_are_the_last_three_seasons():
    """SPEC Section 10: the year holdout rolls across the last three."""
    assert config.HELD_OUT_YEARS == tuple(config.YEARS[-3:])
