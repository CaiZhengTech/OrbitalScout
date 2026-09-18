"""Tests for the ranking metrics. SPEC Section 10, Metrics.

The arithmetic here is easy. What is not easy is reporting it in a way that
cannot be misread, which is what most of these tests are about: a precision
that is capped below 1 by the budget, a base rate that is not the 10% the
label construction implies, and field-years the budget swallows whole.
"""

import pandas as pd
import pytest

from orbitalscout import evaluate


def ranked(per_field, label_column="is_positive"):
    """One field-year per key. `per_field` maps key to a list of 0/1 in rank order.

    Position in the list is the rank, so [1, 0, 0] means the ranker put the
    single true positive first.
    """
    rows = []
    for (field_id, year), flags in per_field.items():
        rows += [(f"f{field_id}z{i}", field_id, year, i + 1, bool(flag))
                 for i, flag in enumerate(flags)]
    return pd.DataFrame(rows, columns=["zone_id", "field_id", "year", "rank", label_column])


def test_precision_is_true_positives_over_zones_actually_visited():
    """Two of the four zones visited were worth visiting.

    Field 1 has a positive at rank 1 and another at rank 3, so a budget of two
    finds one of them. Field 2 has positives at ranks 2 and 3, and finds one.
    The positives at rank 3 are missed in both, which is what recall measures
    and precision does not.
    """
    got = evaluate.metrics(ranked({(1, 2024): [1, 0, 1, 0, 0, 0, 0, 0, 0, 0],
                                   (2, 2024): [0, 1, 1, 0, 0, 0, 0, 0, 0, 0]}), zones=2)
    assert got["n_selected"] == 4
    assert got["precision"] == pytest.approx(2 / 4)


def test_a_perfect_ranker_reaches_the_ceiling_and_not_above_it():
    """Ten zones, two positives, a budget of four. Four stops cannot all pay."""
    perfect = ranked({(1, 2024): [1, 1, 0, 0, 0, 0, 0, 0, 0, 0]})
    got = evaluate.metrics(perfect, zones=4)
    assert got["precision"] == pytest.approx(2 / 4)
    assert got["precision_ceiling"] == pytest.approx(2 / 4)
    assert got["fraction_of_ceiling"] == pytest.approx(1.0)


def test_the_ceiling_binds_when_the_budget_exceeds_the_positive_count():
    """Step 4, Decision 10. At k = 20% with a 10% base rate the cap is 0.5.

    Without this column a reader compares precision@5% against precision@20%
    and concludes the ranker degrades, when half the fall is arithmetic.
    """
    twenty = ranked({(1, 2024): [1] * 2 + [0] * 18})
    assert evaluate.metrics(twenty, fraction=0.20)["precision_ceiling"] == pytest.approx(0.5)
    assert evaluate.metrics(twenty, fraction=0.10)["precision_ceiling"] == pytest.approx(1.0)


def test_lift_over_random_uses_the_measured_base_rate_not_the_nominal_decile():
    """An eleven-zone field-year carries two positives, an 18.2% base rate.

    Dividing by 0.10 instead would overstate the lift by nearly a factor of
    two, and the error would look like a result.
    """
    frame = ranked({(1, 2024): [1, 1] + [0] * 9})
    got = evaluate.metrics(frame, zones=2)
    assert got["base_rate"] == pytest.approx(2 / 11)
    assert got["lift_over_random"] == pytest.approx(1.0 / (2 / 11))
    assert got["lift_over_random"] != pytest.approx(1.0 / 0.10)


def test_lift_carries_its_own_ceiling():
    """Lift of 3.2 reads as unbounded until the maximum sits next to it."""
    got = evaluate.metrics(ranked({(1, 2024): [1] * 2 + [0] * 18}), fraction=0.10)
    assert got["lift_ceiling"] == pytest.approx(got["precision_ceiling"] / got["base_rate"])


def test_recall_is_the_share_of_bad_zones_the_visit_actually_found():
    got = evaluate.metrics(ranked({(1, 2024): [1, 0, 1, 0, 0, 0, 0, 0, 0, 0]}), zones=1)
    assert got["recall"] == pytest.approx(1 / 2)


def test_false_positive_rate_is_over_negatives_not_over_the_budget():
    """One of eight healthy zones was visited; precision would say one of two."""
    got = evaluate.metrics(ranked({(1, 2024): [1, 0, 1, 0, 0, 0, 0, 0, 0, 0]}), zones=2)
    assert got["false_positive_rate"] == pytest.approx(1 / 8)


def test_a_field_year_the_budget_covers_whole_measures_nothing():
    """Step 4, Decision 10. Every zone selected means precision equals the base rate.

    A five-zone field-year under a 20-zone budget scores the same whether the
    ranking is perfect or reversed, so it reports on field size, not on skill.
    """
    small = {(1, 2024): [1, 0, 0, 0, 0]}
    forward = evaluate.metrics(ranked(small), zones=20)
    reversed_ = evaluate.metrics(ranked({(1, 2024): [0, 0, 0, 0, 1]}), zones=20)
    assert forward["precision"] == pytest.approx(reversed_["precision"])
    assert forward["precision"] == pytest.approx(forward["base_rate"])


def test_the_strict_subset_drops_exactly_the_field_years_the_budget_swallows():
    frame = ranked({(1, 2024): [1] + [0] * 4,        # 5 zones, budget covers it
                    (2, 2024): [1] + [0] * 29})      # 30 zones, budget does not
    kept = evaluate.strict_subset(frame, zones=20)
    assert set(kept["field_id"]) == {2}
    assert evaluate.metrics(frame, zones=20)["n_field_years"] == 2
    assert evaluate.metrics(kept, zones=20)["n_field_years"] == 1


def test_a_fractional_budget_always_leaves_a_strict_subset():
    """ceil(0.20 * n) is below n for every field-year of two zones or more."""
    frame = ranked({(1, 2024): [1, 0], (2, 2024): [1] + [0] * 9})
    assert len(evaluate.strict_subset(frame, fraction=0.20)) == len(frame)


def test_lift_over_a_method_compares_precision_at_the_same_budget():
    """The base rate cancels, which is why this is the informative comparison."""
    ours = evaluate.metrics(ranked({(1, 2024): [1, 1, 0, 0, 0, 0, 0, 0, 0, 0]}), zones=2)
    null = evaluate.metrics(ranked({(1, 2024): [1, 0, 0, 0, 0, 0, 0, 0, 0, 1]}), zones=2)
    assert evaluate.lift_over(ours, null) == pytest.approx(1.0 / 0.5)
