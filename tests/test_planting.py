"""Tests for deriving the 50% planted date from NASS weekly progress.

NASS reports cumulative percent planted once a week. The 50% crossing almost
never falls on a reporting date, so it has to be interpolated between the week
below and the week at or above. That interpolation is the whole of the logic
here, and getting it wrong shifts the GDD origin, which shifts every phenology
bin, which misaligns every baseline. Nothing would raise.
"""

import pytest

from orbitalscout.ingest import planting


def weeks(pairs):
    return [{"week_ending": d, "pct_planted": p} for d, p in pairs]


def test_crossing_is_interpolated_between_reporting_weeks():
    """40% on the 10th and 60% on the 17th puts the midpoint on the 13th/14th."""
    series = weeks([("2020-05-03", 20), ("2020-05-10", 40), ("2020-05-17", 60)])
    assert planting.fifty_percent_date(series) == "2020-05-13"


def test_an_exact_fifty_reading_is_used_as_is():
    series = weeks([("2020-05-10", 40), ("2020-05-17", 50)])
    assert planting.fifty_percent_date(series) == "2020-05-17"


def test_a_crossing_close_to_the_lower_week_lands_near_it():
    series = weeks([("2020-05-10", 48), ("2020-05-17", 98)])
    # 2 points of 50 needed, over a 7 day gap, so under half a day past the 10th
    assert planting.fifty_percent_date(series) == "2020-05-10"


def test_unsorted_input_is_handled():
    series = weeks([("2020-05-17", 60), ("2020-05-03", 20), ("2020-05-10", 40)])
    assert planting.fifty_percent_date(series) == "2020-05-13"


def test_a_series_that_never_reaches_fifty_raises():
    """Silently returning the last date would put the origin near harvest."""
    with pytest.raises(ValueError, match="never reaches"):
        planting.fifty_percent_date(weeks([("2020-05-10", 10), ("2020-05-17", 30)]))


def test_an_empty_series_raises():
    with pytest.raises(ValueError, match="empty"):
        planting.fifty_percent_date([])


def test_a_series_already_past_fifty_at_its_first_reading_uses_that_date():
    """Late-starting reporting must not be extrapolated backwards."""
    series = weeks([("2020-05-10", 65), ("2020-05-17", 80)])
    assert planting.fifty_percent_date(series) == "2020-05-10"
