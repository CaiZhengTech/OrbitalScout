"""Tests for S1 and the shared signal signature.

S1 is the whole of rung 1: the ranking is this score sorted, with no model.
The failure that matters is the sign. A score that ranks the healthiest zones
first would still produce a plausible-looking ranked list, a plausible
precision@k, and no error anywhere.
"""

import numpy as np
import pandas as pd
import pytest

from orbitalscout import signals
from orbitalscout.ingest import melt


def features(residuals):
    return pd.DataFrame({
        "zone_id": range(100, 100 + len(residuals)),
        "field_id": 1,
        "year": 2023,
        "feature_ndvi": residuals,
    })


def test_a_zone_below_its_own_baseline_scores_higher_than_one_above():
    """Urgency increases as a zone falls further below its own normal."""
    scores = signals.s1_temporal_anomaly(features([-0.20, 0.0, 0.15]))
    assert scores.iloc[0] > scores.iloc[1] > scores.iloc[2]


def test_the_score_is_the_negated_residual():
    scores = signals.s1_temporal_anomaly(features([-0.20, 0.05]))
    assert scores.iloc[0] == pytest.approx(0.20)
    assert scores.iloc[1] == pytest.approx(-0.05)


def test_the_score_is_aligned_to_the_input_index():
    frame = features([-0.1, -0.2, -0.3]).set_index(pd.Index([7, 8, 9], name="row"))
    scores = signals.s1_temporal_anomaly(frame)
    assert list(scores.index) == [7, 8, 9]


def test_a_missing_residual_stays_missing_and_never_becomes_zero():
    """A null scored as 0 would rank an unknown zone as exactly average."""
    scores = signals.s1_temporal_anomaly(features([-0.2, np.nan]))
    assert scores.iloc[0] == pytest.approx(0.2)
    assert pd.isna(scores.iloc[1])


def test_every_registered_signal_shares_one_signature():
    """CLAUDE.md: six functions with the same signature and a list."""
    frame = features([-0.1, 0.0])
    for signal in signals.SIGNALS:
        scores = signal(frame, context=None)
        assert isinstance(scores, pd.Series)
        assert len(scores) == len(frame)


def test_s1_is_the_only_signal_registered_so_far():
    """Rung 1 is S1 alone. Signals join the list when they are admitted."""
    assert [s.__name__ for s in signals.SIGNALS] == ["s1_temporal_anomaly"]


# --- S2, spatial anomaly --------------------------------------------------
#
# The failures that matter here are quiet ones. A neighbourhood that reaches
# into the next field compares a zone against a different crop on a different
# planting date. A neighbourhood that includes the zone itself shrinks its own
# anomaly toward zero. Neither raises, and both produce a plausible ranking.

def grid(values, field_id=1, year=2023, spacing=melt.ZONE_GRID_M):
    """A frame from {(col, row): value}, on the real packed zone id grid."""
    rows = [(melt.zone_id_from_xy(col * spacing, row * spacing), field_id, year, value)
            for (col, row), value in values.items()]
    return pd.DataFrame(rows, columns=["zone_id", "field_id", "year", "season_level"])


def full_3x3(centre=0.0, ring=0.8):
    values = {(c, r): ring for c in range(3) for r in range(3)}
    values[(1, 1)] = centre
    return values


def at(frame, series, col, row, spacing=melt.ZONE_GRID_M):
    zone_id = melt.zone_id_from_xy(col * spacing, row * spacing)
    return series[frame["zone_id"] == zone_id].iloc[0]


def test_the_neighbourhood_is_all_eight_surrounding_cells():
    """Four-connected would miss the diagonals and read 0.8 either way here.

    So the ring is split: the four edge neighbours read 1.0 and the four
    diagonals 0.6. All eight gives 0.8; only the edges gives 1.0.
    """
    values = {(c, r): 0.6 for c in range(3) for r in range(3)}
    for c, r in ((0, 1), (2, 1), (1, 0), (1, 2)):
        values[(c, r)] = 1.0
    values[(1, 1)] = 0.0
    frame = grid(values)
    got = signals.neighbour_mean(frame, "season_level", min_neighbours=3)
    assert at(frame, got, 1, 1) == pytest.approx(0.8)


def test_a_zone_is_not_its_own_neighbour():
    """Including itself would pull the neighbourhood toward the anomaly."""
    frame = grid(full_3x3(centre=0.0, ring=0.8))
    got = signals.neighbour_mean(frame, "season_level", min_neighbours=3)
    assert at(frame, got, 1, 1) == pytest.approx(0.8)      # not 8*0.8/9 = 0.711


def test_a_neighbour_in_another_field_is_not_counted():
    """Fields differ in crop and planting date; the comparison is meaningless."""
    near = grid({(0, 0): 0.0, (1, 0): 0.9, (0, 1): 0.9, (1, 1): 0.9}, field_id=1)
    far = grid({(2, 0): 0.1, (2, 1): 0.1}, field_id=2)
    frame = pd.concat([near, far], ignore_index=True)
    got = signals.neighbour_mean(frame, "season_level", min_neighbours=3)
    assert at(frame, got, 0, 0) == pytest.approx(0.9)
    # Zone (1, 0) borders field 2. Its three same-field neighbours average 0.6.
    # Letting field 2's two zones in would make it (0.0+0.9+0.9+0.1+0.1)/5 = 0.4,
    # which is a plausible number and no error.
    assert at(frame, got, 1, 0) == pytest.approx(0.6), "field 2 leaked into field 1"
    assert got[frame["field_id"] == 2].isna().all(), "field 2's zones have one neighbour each"


def test_a_neighbour_in_another_year_is_not_counted():
    this_year = grid(full_3x3(centre=0.0, ring=0.8), year=2023)
    last_year = grid(full_3x3(centre=0.0, ring=0.2), year=2022)
    frame = pd.concat([this_year, last_year], ignore_index=True)
    got = signals.neighbour_mean(frame, "season_level", min_neighbours=3)
    assert at(frame[frame["year"] == 2023], got[frame["year"] == 2023], 1, 1) == pytest.approx(0.8)


def test_a_zone_with_too_few_neighbours_is_unscored():
    """A mean over one or two zones is not a local expectation."""
    frame = grid({(0, 0): 0.0, (1, 0): 0.9, (0, 1): 0.9, (1, 1): 0.9})
    assert signals.neighbour_mean(frame, "season_level", min_neighbours=3).notna().all()
    lifted = signals.neighbour_mean(frame, "season_level", min_neighbours=4)
    assert lifted.isna().all(), "a corner has three neighbours, not four"


def test_a_neighbour_with_no_value_is_skipped_not_counted_as_zero():
    values = full_3x3(centre=0.0, ring=0.8)
    values[(0, 0)] = np.nan
    frame = grid(values)
    got = signals.neighbour_mean(frame, "season_level", min_neighbours=3)
    assert at(frame, got, 1, 1) == pytest.approx(0.8), "a null neighbour was averaged in"


def test_s2_scores_a_zone_below_its_neighbours_as_more_urgent():
    frame = grid(full_3x3(centre=0.0, ring=0.8))
    frame["neighbour_level"] = signals.neighbour_mean(frame, "season_level", min_neighbours=3)
    scores = signals.s2_spatial_anomaly(frame)
    assert at(frame, scores, 1, 1) == pytest.approx(0.8)
    assert at(frame, scores, 1, 1) > at(frame, scores, 0, 1)


def test_s2_is_the_neighbourhood_mean_less_the_zones_own_level():
    frame = grid(full_3x3(centre=0.5, ring=0.2))
    frame["neighbour_level"] = signals.neighbour_mean(frame, "season_level", min_neighbours=3)
    scores = signals.s2_spatial_anomaly(frame)
    assert at(frame, scores, 1, 1) == pytest.approx(-0.3), "a zone above its neighbours is not urgent"


def test_s2_leaves_a_zone_with_no_neighbourhood_unscored():
    frame = grid({(0, 0): 0.0, (1, 0): 0.9})
    frame["neighbour_level"] = signals.neighbour_mean(frame, "season_level", min_neighbours=3)
    assert signals.s2_spatial_anomaly(frame).isna().all()


def test_s2_is_not_registered_until_the_admission_rule_admits_it():
    """CLAUDE.md: building a signal does not entitle it to ship."""
    assert signals.s2_spatial_anomaly not in signals.SIGNALS
