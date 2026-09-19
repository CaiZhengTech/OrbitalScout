"""Tests for the comparison baselines. SPEC Section 10, Baselines.

B1a level persistence, B1b anomaly persistence, B2 NDVI k-means.

These are the things the ranker has to beat, so each one is given its best
honest shot. A null that has been quietly handicapped proves nothing, and the
temptation to handicap it is strongest here.
"""

import numpy as np
import pandas as pd
import pytest

from orbitalscout import baselines

CORN, SOY = 1, 5


def history(rows):
    return pd.DataFrame(rows, columns=["zone_id", "year", "cdl_code", "residual"])


def targets(rows):
    return pd.DataFrame(rows, columns=["zone_id", "field_id", "year", "cdl_code"])


# --- B1a, level persistence ------------------------------------------------

def test_b1a_ranks_the_persistently_worst_zone_as_most_urgent():
    """Ascending by multi-year mean, so the lowest standing scores highest."""
    frame = pd.DataFrame({"zone_id": [1, 2, 3], "prior_level": [-0.2, 0.0, 0.3]})
    score = baselines.b1a_level_persistence(frame)
    assert score.iloc[0] > score.iloc[1] > score.iloc[2]


def test_b1a_leaves_a_zone_with_no_history_unscored():
    """A zone with no prior years has no standing, and inventing one ranks it."""
    frame = pd.DataFrame({"zone_id": [1, 2], "prior_level": [-0.2, np.nan]})
    assert baselines.b1a_level_persistence(frame).isna().tolist() == [False, True]


# --- B1b, anomaly persistence, the headline null ---------------------------

def test_b1b_uses_the_most_recent_prior_year_with_the_same_crop():
    """SPEC Section 10. Under this rotation that is usually two years back.

    Zone 1 grew corn in 2020, soy in 2021, corn in 2022. Scoring corn in 2022
    must reach back to 2020, not to the soy year in between.
    """
    past = history([(1, 2020, CORN, -0.5), (1, 2021, SOY, -0.1)])
    got = baselines.prior_same_crop(targets([(1, 10, 2022, CORN)]), past)
    assert got["prior_residual"].iloc[0] == pytest.approx(-0.5)


def test_b1b_never_reaches_into_the_target_year_itself():
    """A null that reads its own year would be unbeatable and meaningless."""
    past = history([(1, 2020, CORN, -0.5), (1, 2022, CORN, -0.9)])
    got = baselines.prior_same_crop(targets([(1, 10, 2022, CORN)]), past)
    assert got["prior_residual"].iloc[0] == pytest.approx(-0.5)


def test_b1b_never_reaches_forward_to_a_later_year():
    past = history([(1, 2023, CORN, -0.9)])
    got = baselines.prior_same_crop(targets([(1, 10, 2022, CORN)]), past)
    assert got["prior_residual"].isna().all()


def test_b1b_is_unscored_when_the_crop_has_never_been_grown_before():
    """Not zero. Zero is a claim that the zone was exactly average."""
    past = history([(1, 2020, SOY, -0.5)])
    got = baselines.prior_same_crop(targets([(1, 10, 2022, CORN)]), past)
    assert got["prior_residual"].isna().all()


def test_b1b_does_not_borrow_another_zones_history():
    past = history([(2, 2020, CORN, -0.9)])
    got = baselines.prior_same_crop(targets([(1, 10, 2022, CORN)]), past)
    assert got["prior_residual"].isna().all()


def test_b1b_scores_the_worst_prior_residual_as_most_urgent():
    past = history([(1, 2020, CORN, -0.5), (2, 2020, CORN, 0.4)])
    got = baselines.prior_same_crop(targets([(1, 10, 2022, CORN), (2, 10, 2022, CORN)]), past)
    score = baselines.b1b_anomaly_persistence(got)
    assert score.iloc[0] > score.iloc[1]


# --- B2, NDVI k-means ------------------------------------------------------

def test_b2_separates_two_obvious_groups():
    """Three low readings and three high ones must not share a cluster."""
    values = np.array([0.2, 0.21, 0.22, 0.8, 0.81, 0.82])
    assignment = baselines.kmeans_1d(values, k=2)
    assert len(set(assignment[:3])) == 1
    assert len(set(assignment[3:])) == 1
    assert assignment[0] != assignment[3]


def test_b2_scores_by_cluster_mean_so_a_whole_cluster_ties():
    """A management zone map has k distinct values, not one per zone.

    That is the point of the comparison: commercial products hand a scout a
    handful of polygons, and every zone inside one is equally urgent.
    """
    frame = pd.DataFrame({
        "zone_id": [1, 2, 3, 4], "field_id": [10] * 4, "year": [2024] * 4,
        "prior_level": [0.2, 0.22, 0.8, 0.81],
    })
    score = baselines.b2_ndvi_kmeans(frame, k=2)
    assert score.iloc[0] == pytest.approx(score.iloc[1])
    assert score.iloc[2] == pytest.approx(score.iloc[3])
    assert score.iloc[0] > score.iloc[2], "the low cluster must be the urgent one"
    # The score is the cluster mean, not the cluster index. Both rank the same
    # way here, since quantile starts keep the centres sorted, so this pins the
    # value rather than the order: a cluster mean is an index offset a reader
    # can interpret and a cluster number is not.
    assert score.iloc[0] == pytest.approx(-(0.2 + 0.22) / 2)


def test_b2_clusters_each_field_year_on_its_own():
    """Clustering across fields would put a whole poor field in one cluster."""
    frame = pd.DataFrame({
        "zone_id": [1, 2, 3, 4], "field_id": [10, 10, 20, 20], "year": [2024] * 4,
        "prior_level": [0.2, 0.3, 0.8, 0.9],
    })
    score = baselines.b2_ndvi_kmeans(frame, k=2)
    assert score.iloc[0] > score.iloc[1], "field 10 was not clustered on its own"
    assert score.iloc[2] > score.iloc[3], "field 20 was not clustered on its own"


def test_b2_handles_a_field_with_fewer_zones_than_clusters():
    """A three-zone field-year cannot yield seven clusters and must not raise."""
    frame = pd.DataFrame({
        "zone_id": [1, 2, 3], "field_id": [10] * 3, "year": [2024] * 3,
        "prior_level": [0.2, 0.5, 0.9],
    })
    score = baselines.b2_ndvi_kmeans(frame, k=7)
    assert score.notna().all()
    assert score.iloc[0] > score.iloc[2]


def test_b2_is_deterministic():
    """Lloyd's result depends on its start, so the start must not be random."""
    rng = np.random.default_rng(0)
    values = rng.random(200)
    first = baselines.kmeans_1d(values, k=5)
    second = baselines.kmeans_1d(values, k=5)
    assert (first == second).all()


def test_b2_gives_a_constant_field_one_cluster_without_dividing_by_zero():
    values = np.full(10, 0.5)
    assignment = baselines.kmeans_1d(values, k=3)
    assert len(set(assignment)) == 1
