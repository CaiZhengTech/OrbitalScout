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
