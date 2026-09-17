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
