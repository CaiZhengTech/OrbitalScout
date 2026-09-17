"""Tests for the within-field relative, phenology-aligned baseline.

SPEC Section 8 and DESIGN D17:

    relative_index(i, t, b) = index(i, t, b) - median over zones in f of index(., t, b)
    baseline(i, b)          = mean over prior years of relative_index(i, ., b)
    residual(i, t, b)       = relative_index(i, t, b) - baseline(i, b)

Everything here fails silently if wrong. A mean instead of a median, a baseline
that includes its own year, or a derecho observation leaking into history would
each produce plausible residuals and a plausible ranking, and nothing would raise.
"""

import duckdb
import pandas as pd
import pytest

from orbitalscout import baseline

CORN = 1
ALFALFA = 36  # deliberately absent from the crop registry


def make_con(obs, gdd, crops_by_year=None, zones_per_field=None):
    """A DuckDB connection holding the three Step 1 tables plus a gdd table.

    obs: list of (zone_id, field_id, year, date, ndvi)
    gdd: dict of date -> cumulative GDD, applied to corn
    crops_by_year: dict of year -> CDL code for field 1, default all corn
    """
    con = duckdb.connect()
    zone_obs = pd.DataFrame(obs, columns=["zone_id", "field_id", "year", "date", "ndvi"])
    zone_obs["ndre"] = zone_obs["ndvi"]
    zone_obs["ndwi"] = zone_obs["ndvi"]
    zone_obs["n_valid"] = 9
    con.register("zone_obs", zone_obs)

    fields_seen = sorted(set(zone_obs["field_id"]))
    crops_by_year = crops_by_year or {}
    fields = pd.DataFrame([
        {"field_id": f, **{f"crop_{y}": crops_by_year.get(y, CORN) for y in range(2018, 2026)}}
        for f in fields_seen
    ])
    con.register("fields", fields)

    zone_rows = sorted({(z, f) for z, f, *_ in obs})
    if zones_per_field:
        zone_rows = [(z, f) for f, zs in zones_per_field.items() for z in zs]
    con.register("zones", pd.DataFrame(zone_rows, columns=["zone_id", "field_id"]))

    con.register("gdd", pd.DataFrame(
        [(CORN, d, g) for d, g in gdd.items()], columns=["cdl_code", "date", "gdd"]
    ))
    return con


def build(con, width=200, min_clear=0.0, events=()):
    baseline.build_views(con, width_gdd=width, min_field_clear_frac=min_clear, events=events)
    return con


def test_relative_index_subtracts_the_field_median_not_the_mean():
    """0.4, 0.5, 0.9 has median 0.5 and mean 0.6. The median is required."""
    con = build(make_con(
        obs=[(101, 1, 2020, "2020-06-01", 0.4),
             (102, 1, 2020, "2020-06-01", 0.5),
             (103, 1, 2020, "2020-06-01", 0.9)],
        gdd={"2020-06-01": 300},
    ))
    got = dict(con.execute(
        "SELECT zone_id, rel_ndvi FROM relative_obs ORDER BY zone_id"
    ).fetchall())
    assert got[101] == pytest.approx(-0.1)
    assert got[102] == pytest.approx(0.0)
    assert got[103] == pytest.approx(0.4)


def test_observation_before_the_planting_origin_is_dropped():
    """No GDD row exists before planting, so the observation has no stage."""
    con = build(make_con(
        obs=[(101, 1, 2020, "2020-04-20", 0.2), (101, 1, 2020, "2020-06-01", 0.5)],
        gdd={"2020-06-01": 300},
    ))
    dates = [r[0] for r in con.execute("SELECT date FROM binned_obs").fetchall()]
    assert dates == ["2020-06-01"]


def test_zone_year_with_a_crop_outside_the_registry_is_dropped():
    con = build(make_con(
        obs=[(101, 1, 2019, "2019-06-01", 0.5), (101, 1, 2020, "2020-06-01", 0.5)],
        gdd={"2019-06-01": 300, "2020-06-01": 300},
        crops_by_year={2019: ALFALFA},
    ))
    years = [r[0] for r in con.execute("SELECT DISTINCT year FROM binned_obs").fetchall()]
    assert years == [2020]


def test_bin_is_the_floor_of_gdd_over_width():
    con = build(make_con(
        obs=[(101, 1, 2020, "2020-06-01", 0.5), (101, 1, 2020, "2020-06-20", 0.5)],
        gdd={"2020-06-01": 199.9, "2020-06-20": 450.0},
    ), width=200)
    bins = dict(con.execute("SELECT date, bin FROM binned_obs").fetchall())
    assert bins == {"2020-06-01": 0, "2020-06-20": 2}


def target_zone_history(values_by_year, extra=()):
    """Zone 101 varies by year; zones 102 and 103 sit at 0.5 so the median is 0.5.

    That makes zone 101's relative index exactly its value minus 0.5.
    """
    obs, gdd = [], {}
    for year, value in values_by_year.items():
        date = f"{year}-06-01"
        gdd[date] = 300
        obs += [(101, 1, year, date, value),
                (102, 1, year, date, 0.5),
                (103, 1, year, date, 0.5)]
    for zone, year, date, value, g in extra:
        gdd[date] = g
        obs += [(zone, 1, year, date, value),
                (102, 1, year, date, 0.5),
                (103, 1, year, date, 0.5)]
    return obs, gdd


def baseline_for(con, year):
    return con.execute(
        "SELECT baseline_ndvi, n_prior_years FROM baseline "
        "WHERE zone_id = 101 AND year = ? AND bin = 1", [year]
    ).fetchone()


def test_baseline_uses_only_strictly_prior_years():
    """A baseline that includes its own year partly predicts itself."""
    obs, gdd = target_zone_history({2018: 0.6, 2019: 0.8, 2020: 1.0})
    con = build(make_con(obs, gdd))

    assert baseline_for(con, 2018) == (None, 0)
    value, n = baseline_for(con, 2019)
    assert (value, n) == (pytest.approx(0.1), 1)          # 2018 only
    value, n = baseline_for(con, 2020)
    assert (value, n) == (pytest.approx(0.2), 2)          # mean of 0.1 and 0.3


def test_residual_is_relative_minus_baseline():
    obs, gdd = target_zone_history({2018: 0.6, 2019: 0.8, 2020: 1.0})
    con = build(make_con(obs, gdd))
    residual = con.execute(
        "SELECT residual_ndvi FROM baseline WHERE zone_id = 101 AND year = 2020 AND bin = 1"
    ).fetchone()[0]
    assert residual == pytest.approx(0.5 - 0.2)


def test_known_event_observations_do_not_enter_later_baselines():
    """A derecho reading must not become part of what normal looks like."""
    obs, gdd = target_zone_history(
        {2018: 0.6, 2019: 0.6, 2021: 0.6},
        extra=[(101, 2020, "2020-08-15", 0.0, 300)],   # inside the event window
    )
    events = (("derecho_2020", "2020-08-10", "2020-12-31", "test"),)
    con = build(make_con(obs, gdd), events=events)

    value, n = baseline_for(con, 2021)
    assert n == 2, "the 2020 event year must not count as a prior year"
    assert value == pytest.approx(0.1)


def test_known_event_observations_still_appear_as_their_own_target():
    """Excluded from history, but the case study still needs the reading."""
    obs, gdd = target_zone_history(
        {2018: 0.6, 2019: 0.6},
        extra=[(101, 2020, "2020-08-15", 0.0, 300)],
    )
    events = (("derecho_2020", "2020-08-10", "2020-12-31", "test"),)
    con = build(make_con(obs, gdd), events=events)
    row = con.execute(
        "SELECT rel_ndvi FROM baseline WHERE zone_id = 101 AND year = 2020 AND bin = 1"
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(-0.5)


def test_field_dates_below_the_minimum_clear_fraction_are_dropped():
    """If clouds leave one zone of four visible, its field median is that zone."""
    con = build(make_con(
        obs=[(101, 1, 2020, "2020-06-01", 0.9),
             (101, 1, 2020, "2020-06-11", 0.9),
             (102, 1, 2020, "2020-06-11", 0.5),
             (103, 1, 2020, "2020-06-11", 0.5)],
        gdd={"2020-06-01": 300, "2020-06-11": 320},
        zones_per_field={1: [101, 102, 103, 104]},
    ), min_clear=0.5)
    dates = sorted({r[0] for r in con.execute("SELECT date FROM relative_obs").fetchall()})
    assert dates == ["2020-06-11"]   # 1 of 4 clear dropped, 3 of 4 kept
