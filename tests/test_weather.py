"""Tests for GDD accumulation.

The arithmetic is simple and the failure is silent: an off-by-one in the cap or
a wrong origin shifts every phenology bin, which would misalign every baseline
without anything raising.
"""

import pandas as pd
import pytest

from orbitalscout.ingest import weather


def daily(pairs):
    return pd.DataFrame(
        {"date": [p[0] for p in pairs],
         "tmax_f": [p[1] for p in pairs],
         "tmin_f": [p[2] for p in pairs]}
    )


def test_a_day_at_the_base_contributes_nothing():
    df = daily([("2020-05-01", 50.0, 50.0)])
    assert weather.accumulate(df, base_f=50.0, cap_f=86.0)["gdd"].iloc[0] == 0


def test_a_normal_day_contributes_mean_minus_base():
    df = daily([("2020-05-01", 70.0, 50.0)])
    # mean 60, base 50, so 10
    assert weather.accumulate(df, base_f=50.0, cap_f=86.0)["gdd"].iloc[0] == pytest.approx(10.0)


def test_tmax_is_capped():
    """A 100F day counts as 86F, or hot weeks inflate the accumulation."""
    hot = weather.accumulate(daily([("2020-07-01", 100.0, 70.0)]), 50.0, 86.0)
    capped = weather.accumulate(daily([("2020-07-01", 86.0, 70.0)]), 50.0, 86.0)
    assert hot["gdd"].iloc[0] == capped["gdd"].iloc[0]


def test_tmin_is_floored_at_the_base():
    """A 40F night counts as 50F, not as a negative contribution."""
    cold = weather.accumulate(daily([("2020-05-01", 60.0, 40.0)]), 50.0, 86.0)
    floored = weather.accumulate(daily([("2020-05-01", 60.0, 50.0)]), 50.0, 86.0)
    assert cold["gdd"].iloc[0] == floored["gdd"].iloc[0]


def test_a_day_below_the_base_never_subtracts():
    df = daily([("2020-04-01", 45.0, 30.0)])
    assert weather.accumulate(df, 50.0, 86.0)["gdd"].iloc[0] == 0


def test_accumulation_is_cumulative_from_the_origin():
    df = daily([("2020-05-01", 70.0, 50.0),
                ("2020-05-02", 70.0, 50.0),
                ("2020-05-03", 70.0, 50.0)])
    out = weather.accumulate(df, 50.0, 86.0, origin="2020-05-02")
    assert out.loc[out["date"] == "2020-05-01", "gdd_cumulative"].iloc[0] == 0
    assert out.loc[out["date"] == "2020-05-02", "gdd_cumulative"].iloc[0] == pytest.approx(10.0)
    assert out.loc[out["date"] == "2020-05-03", "gdd_cumulative"].iloc[0] == pytest.approx(20.0)


def test_days_before_the_origin_contribute_nothing():
    """Accumulation starts at planting, so April warmth must not count."""
    df = daily([("2020-04-20", 80.0, 60.0), ("2020-05-02", 70.0, 50.0)])
    out = weather.accumulate(df, 50.0, 86.0, origin="2020-05-02")
    assert out.loc[out["date"] == "2020-04-20", "gdd_cumulative"].iloc[0] == 0
    assert out.loc[out["date"] == "2020-05-02", "gdd_cumulative"].iloc[0] == pytest.approx(10.0)


def planting(rows):
    return pd.DataFrame(rows, columns=["cdl_code", "year", "fifty_pct_planted"])


def two_crop_daily():
    return daily([
        ("2020-05-01", 70.0, 50.0), ("2020-05-02", 70.0, 50.0),
        ("2020-05-03", 70.0, 50.0), ("2021-05-01", 70.0, 50.0),
        ("2021-05-02", 70.0, 50.0),
    ])


def test_gdd_table_excludes_days_before_each_crop_years_origin():
    """Pre-planting days measure bare soil, not crop, so they carry no stage."""
    table = weather.gdd_table(
        two_crop_daily(), planting([(1, 2020, "2020-05-02"), (1, 2021, "2021-05-01")])
    )
    corn_2020 = table[(table["cdl_code"] == 1) & (table["date"].str.startswith("2020"))]
    assert corn_2020["date"].tolist() == ["2020-05-02", "2020-05-03"]


def test_gdd_table_accumulates_separately_per_crop():
    """Corn and soybean share weather but not planting dates, so not GDD."""
    table = weather.gdd_table(
        two_crop_daily(), planting([(1, 2020, "2020-05-01"), (5, 2020, "2020-05-02")])
    )
    on = table[table["date"] == "2020-05-03"].set_index("cdl_code")["gdd"]
    assert on[1] == pytest.approx(30.0)   # three days of 10
    assert on[5] == pytest.approx(20.0)   # two days of 10


def test_gdd_table_resets_every_year():
    table = weather.gdd_table(
        two_crop_daily(), planting([(1, 2020, "2020-05-01"), (1, 2021, "2021-05-01")])
    )
    first_2021 = table[table["date"] == "2021-05-01"]["gdd"].iloc[0]
    assert first_2021 == pytest.approx(10.0), "2020 heat must not carry into 2021"


def test_gdd_table_uses_each_crops_registry_thresholds(monkeypatch):
    """Base and cap come from the registry by CDL code, never from a name."""
    from orbitalscout import crops
    hot = daily([("2020-07-01", 100.0, 70.0)])
    table = weather.gdd_table(hot, planting([(1, 2020, "2020-07-01")]))
    corn = crops.get(1)
    expected = (min(100.0, corn.gdd_cap_f) + max(70.0, corn.gdd_base_f)) / 2 - corn.gdd_base_f
    assert table["gdd"].iloc[0] == pytest.approx(expected)
