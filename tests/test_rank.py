"""Tests for ranking and the scouting budget.

The ranking is per field-year: a farmer walks one field. Ranking across fields
would let a field with generally poor soil consume the whole budget, which is
exactly the failure D1 exists to prevent.
"""

import numpy as np
import pandas as pd
import pytest

from orbitalscout import rank


def scored(rows):
    """rows: list of (zone_id, field_id, year, score)."""
    return pd.DataFrame(rows, columns=["zone_id", "field_id", "year", "score"])


def test_highest_score_is_rank_one_within_each_field_year():
    frame = scored([(1, 10, 2023, 0.1), (2, 10, 2023, 0.5), (3, 10, 2023, 0.3)])
    ranked = rank.rank_within_field(frame).set_index("zone_id")
    assert ranked.loc[2, "rank"] == 1
    assert ranked.loc[3, "rank"] == 2
    assert ranked.loc[1, "rank"] == 3


def test_each_field_year_is_ranked_independently():
    frame = scored([(1, 10, 2023, 0.9), (2, 11, 2023, 0.1), (3, 11, 2023, 0.2)])
    ranked = rank.rank_within_field(frame).set_index("zone_id")
    assert ranked.loc[1, "rank"] == 1      # alone in its field
    assert ranked.loc[3, "rank"] == 1      # best in the other field
    assert ranked.loc[2, "rank"] == 2


def test_the_same_field_in_two_years_is_ranked_separately():
    frame = scored([(1, 10, 2023, 0.1), (1, 10, 2024, 0.9)])
    ranked = rank.rank_within_field(frame)
    assert set(ranked["rank"]) == {1}


def test_ties_break_deterministically_so_reruns_match():
    frame = scored([(5, 10, 2023, 0.4), (3, 10, 2023, 0.4), (9, 10, 2023, 0.4)])
    first = rank.rank_within_field(frame).sort_values("zone_id")["rank"].tolist()
    shuffled = rank.rank_within_field(frame.iloc[::-1].reset_index(drop=True))
    second = shuffled.sort_values("zone_id")["rank"].tolist()
    assert first == second
    assert sorted(first) == [1, 2, 3]


def test_zones_without_a_score_are_not_ranked():
    """An unscored zone cannot be placed; ranking it would invent a position."""
    frame = scored([(1, 10, 2023, 0.5), (2, 10, 2023, np.nan)])
    ranked = rank.rank_within_field(frame)
    assert ranked["zone_id"].tolist() == [1]


def test_an_absolute_budget_takes_that_many_zones_per_field_year():
    frame = scored([(i, 10, 2023, i / 10) for i in range(1, 11)])
    top = rank.select_budget(rank.rank_within_field(frame), zones=3)
    assert len(top) == 3
    assert set(top["zone_id"]) == {10, 9, 8}


def test_a_budget_larger_than_the_field_takes_the_whole_field():
    frame = scored([(1, 10, 2023, 0.2), (2, 10, 2023, 0.4)])
    top = rank.select_budget(rank.rank_within_field(frame), zones=5)
    assert len(top) == 2


def test_a_fractional_budget_rounds_up_so_every_field_gets_at_least_one():
    frame = scored([(i, 10, 2023, i / 10) for i in range(1, 6)])   # 5 zones
    assert len(rank.select_budget(rank.rank_within_field(frame), fraction=0.10)) == 1
    assert len(rank.select_budget(rank.rank_within_field(frame), fraction=0.40)) == 2


def test_a_budget_applies_per_field_year_not_across_the_whole_area():
    frame = scored([(1, 10, 2023, 0.9), (2, 10, 2023, 0.8),
                    (3, 11, 2023, 0.1), (4, 11, 2023, 0.05)])
    top = rank.select_budget(rank.rank_within_field(frame), zones=1)
    assert len(top) == 2, "one zone from each field, not one overall"
    assert set(top["field_id"]) == {10, 11}


def test_exactly_one_of_zones_or_fraction_is_required():
    ranked = rank.rank_within_field(scored([(1, 10, 2023, 0.5)]))
    with pytest.raises(ValueError, match="exactly one"):
        rank.select_budget(ranked)
    with pytest.raises(ValueError, match="exactly one"):
        rank.select_budget(ranked, zones=3, fraction=0.1)


# --- rung 2, the weighted sum of z-scored signals -------------------------

def two_signals(per_field):
    """{(field, year): [(s1, s2), ...]} into a frame, one row per zone."""
    rows = []
    for (field_id, year), pairs in per_field.items():
        rows += [(f"f{field_id}z{i}", field_id, year, a, b)
                 for i, (a, b) in enumerate(pairs)]
    return pd.DataFrame(rows, columns=["zone_id", "field_id", "year", "s1", "s2"])


def test_z_scores_are_computed_within_each_field_year_separately():
    """Pooling would let a field's overall level decide its zones' z-scores.

    Field 1 sits at 1, 2, 3 and field 2 at 101, 102, 103. Within field they are
    the same shape and must get the same z-scores. Pooled, field 2 would be
    three standard deviations up and its zones nearly tied.
    """
    frame = two_signals({(1, 2024): [(1.0, 0)], (2, 2024): [(101.0, 0)]})
    frame = two_signals({(1, 2024): [(1.0, 0), (2.0, 0), (3.0, 0)],
                    (2, 2024): [(101.0, 0), (102.0, 0), (103.0, 0)]})
    z = rank.zscore_within_field(frame, "s1")
    assert list(z[:3].round(6)) == list(z[3:].round(6))


def test_a_z_score_has_zero_mean_and_unit_spread_in_its_field_year():
    frame = two_signals({(1, 2024): [(1.0, 0), (2.0, 0), (3.0, 0), (4.0, 0)]})
    z = rank.zscore_within_field(frame, "s1")
    assert z.mean() == pytest.approx(0.0)
    assert z.std() == pytest.approx(1.0)


def test_a_field_year_with_no_spread_scores_zero_rather_than_dividing_by_zero():
    """Every zone equal carries no information; it must not raise or go null."""
    frame = two_signals({(1, 2024): [(0.5, 0), (0.5, 0), (0.5, 0)],
                    (2, 2024): [(0.7, 0)]})
    z = rank.zscore_within_field(frame, "s1")
    assert (z == 0).all(), "a flat field-year, and a single-zone one, must score 0"


def test_z_scoring_does_not_change_a_single_signals_ranking():
    """It is a monotone transform inside the ranking unit, so rung 1 is safe."""
    frame = two_signals({(1, 2024): [(0.3, 0), (-0.1, 0), (0.9, 0)],
                    (2, 2024): [(5.0, 0), (1.0, 0)]})
    frame["z"] = rank.zscore_within_field(frame, "s1")
    plain = rank.rank_within_field(frame, score_column="s1")["zone_id"].tolist()
    zed = rank.rank_within_field(frame, score_column="z")["zone_id"].tolist()
    assert plain == zed


def test_a_missing_score_stays_missing_through_the_z_score():
    frame = two_signals({(1, 2024): [(0.3, 0), (np.nan, 0), (0.9, 0)]})
    z = rank.zscore_within_field(frame, "s1")
    assert pd.isna(z.iloc[1])
    assert z.notna().sum() == 2


def test_the_combination_is_the_equal_weight_sum_of_z_scores():
    """Rung 2 takes no weights. Searching them is training and belongs to rung 3."""
    frame = two_signals({(1, 2024): [(1.0, 3.0), (2.0, 2.0), (3.0, 1.0)]})
    got = rank.combine(frame, ["s1", "s2"])
    expected = (rank.zscore_within_field(frame, "s1")
                + rank.zscore_within_field(frame, "s2"))
    assert got.tolist() == pytest.approx(expected.tolist())
    assert got.tolist() == pytest.approx([0.0, 0.0, 0.0]), "s1 and s2 cancel exactly here"


def test_the_combination_is_unscored_when_any_component_is_missing():
    """Falling back to the signals that survive would score two populations."""
    frame = two_signals({(1, 2024): [(1.0, 3.0), (2.0, np.nan), (3.0, 1.0)]})
    got = rank.combine(frame, ["s1", "s2"])
    assert pd.isna(got.iloc[1])
    assert got.notna().sum() == 2
