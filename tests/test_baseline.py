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


def test_supported_view_drops_cells_below_the_prior_year_floor():
    """A baseline resting on one or two readings is not a history."""
    obs, gdd = target_zone_history({2018: 0.6, 2019: 0.7, 2020: 0.8, 2021: 0.9})
    con = build(make_con(obs, gdd))
    baseline.supported_view(con, min_prior_years=3)
    years = [r[0] for r in con.execute(
        "SELECT year FROM supported_baseline WHERE zone_id = 101 ORDER BY year"
    ).fetchall()]
    assert years == [2021]   # the only year with three prior years behind it


def test_the_raw_baseline_keeps_unsupported_cells_and_their_count():
    """The floor is applied where the baseline is consumed, so the raw count
    stays inspectable. Hiding unsupported cells inside the baseline view would
    make the share the floor excludes impossible to report."""
    obs, gdd = target_zone_history({2018: 0.6, 2019: 0.7, 2020: 0.8, 2021: 0.9})
    con = build(make_con(obs, gdd))
    baseline.supported_view(con, min_prior_years=3)
    counts = dict(con.execute(
        "SELECT year, n_prior_years FROM baseline WHERE zone_id = 101"
    ).fetchall())
    assert counts == {2018: 0, 2019: 1, 2020: 2, 2021: 3}


def test_supported_view_defaults_to_the_configured_floor():
    from orbitalscout import config
    obs, gdd = target_zone_history({2018: 0.6, 2019: 0.7, 2020: 0.8, 2021: 0.9})
    con = build(make_con(obs, gdd))
    baseline.supported_view(con)
    floor = con.execute("SELECT min(n_prior_years) FROM supported_baseline").fetchone()[0]
    assert floor == config.MIN_PRIOR_YEARS


def test_precomputed_field_stats_give_the_same_residuals(tmp_path):
    """The real build computes field medians once over all zones and reuses
    them while windowing zones in chunks. Reusing them must change nothing;
    recomputing per chunk would take a median over a chunk's zones only."""
    obs = [(101, 1, 2020, "2020-06-01", 0.4), (102, 1, 2020, "2020-06-01", 0.5),
           (103, 1, 2020, "2020-06-01", 0.9), (101, 1, 2021, "2021-06-01", 0.3),
           (102, 1, 2021, "2021-06-01", 0.6), (103, 1, 2021, "2021-06-01", 0.8)]
    gdd = {"2020-06-01": 300, "2021-06-01": 300}

    inline = build(make_con(obs, gdd))
    expected = inline.execute(
        "SELECT zone_id, year, rel_ndvi, residual_ndvi FROM baseline ORDER BY zone_id, year"
    ).fetchall()

    stats_path = tmp_path / "field_date_stats.parquet"
    inline.execute(f"COPY field_date_stats TO '{stats_path.as_posix()}' (FORMAT PARQUET)")

    # A chunk holding zone 101 only, exactly as the chunked build sees it. If
    # the precomputed stats were ignored, the median would be recomputed over
    # zone 101 alone, its relative index would be zero, and this would fail.
    chunk = make_con([o for o in obs if o[0] == 101], gdd,
                     zones_per_field={1: [101, 102, 103]})
    baseline.build_views(chunk, width_gdd=200, min_field_clear_frac=0.0, events=(),
                         field_stats=str(stats_path))
    got = chunk.execute(
        "SELECT zone_id, year, rel_ndvi, residual_ndvi FROM baseline ORDER BY zone_id, year"
    ).fetchall()
    assert got == [row for row in expected if row[0] == 101]
    assert got[0][2] == pytest.approx(-0.1), "median must come from all zones, not the chunk"


# ---- Second amendment: leave-one-year-out label baseline and stage windows ----

def staged_history(values):
    """Zone 101 by (year, bin); zones 102 and 103 sit at 0.5 so the median is 0.5.

    Zone 101's relative index is therefore exactly its value minus 0.5. Each
    bin gets its own date so several bins can share a year.
    """
    obs, gdd = [], {}
    for (year, b), value in values.items():
        date = f"{year}-06-{b + 1:02d}"
        gdd[date] = b * 200 + 50
        obs += [(101, 1, year, date, value),
                (102, 1, year, date, 0.5),
                (103, 1, year, date, 0.5)]
    return obs, gdd


def label_baseline_for(con, year, b=1):
    return con.execute(
        "SELECT label_baseline_ndvi, n_label_years FROM label_baseline "
        "WHERE zone_id = 101 AND year = ? AND bin = ?", [year, b]
    ).fetchone()


def test_label_baseline_uses_every_other_year_but_never_its_own():
    """SPEC Section 10: the label baseline excludes the target year only."""
    obs, gdd = staged_history({(2018, 1): 0.6, (2019, 1): 0.8, (2020, 1): 1.0})
    con = build(make_con(obs, gdd))            # relative: 0.1, 0.3, 0.5

    value, n = label_baseline_for(con, 2019)
    assert (value, n) == (pytest.approx(0.3), 2)    # 2018 and 2020, not 2019
    value, n = label_baseline_for(con, 2018)
    assert (value, n) == (pytest.approx(0.4), 2)    # 2019 and 2020, including a later year


def test_label_residual_is_relative_minus_label_baseline():
    obs, gdd = staged_history({(2018, 1): 0.6, (2019, 1): 0.8, (2020, 1): 1.0})
    con = build(make_con(obs, gdd))
    residual = con.execute(
        "SELECT label_residual_ndvi FROM label_baseline WHERE zone_id = 101 AND year = 2019 AND bin = 1"
    ).fetchone()[0]
    assert residual == pytest.approx(0.3 - 0.3)


def test_label_baseline_excludes_known_event_observations_from_other_years():
    obs, gdd = staged_history({(2018, 1): 0.6, (2019, 1): 0.6})
    obs += [(101, 1, 2020, "2020-08-15", 0.0), (102, 1, 2020, "2020-08-15", 0.5),
            (103, 1, 2020, "2020-08-15", 0.5)]
    gdd["2020-08-15"] = 250                    # bin 1, inside the event window
    events = (("derecho_2020", "2020-08-10", "2020-12-31", "test"),)
    con = build(make_con(obs, gdd), events=events)

    value, n = label_baseline_for(con, 2019)
    assert n == 1, "the event reading must not count as another year"
    assert value == pytest.approx(0.1)


def five_years_then(target_values, constant=0.6, bins=(), years=range(2018, 2022)):
    values = {(y, b): constant for y in years for b in bins}
    values.update(target_values)
    return values


def outcomes(con, floor=3):
    baseline.supported_view(con, min_prior_years=floor)
    baseline.outcome_views(con, min_prior_years=floor)
    return con


def test_label_is_the_mean_residual_over_supported_cells_in_the_label_window():
    """Bins 7 and 12 fall outside the window; bin 9 lacks support."""
    values = five_years_then(
        {(2022, 7): 0.9, (2022, 8): 0.7, (2022, 11): 0.8, (2022, 12): 0.2,
         (2021, 9): 0.6, (2022, 9): 0.95},
        bins=(7, 8, 11, 12),
    )
    con = outcomes(build(make_con(*staged_history(values))))
    label, n = con.execute(
        "SELECT label_ndvi, n_label_cells FROM zone_year_label WHERE zone_id = 101 AND year = 2022"
    ).fetchone()
    assert n == 2
    assert label == pytest.approx(((0.2 - 0.1) + (0.3 - 0.1)) / 2)


def test_label_view_also_carries_the_raw_level_for_the_secondary_label():
    """SPEC Section 10: the secondary label is the bottom decile of raw index.

    Carried on the same view as the residual so both labels cover exactly the
    same zone-years. Two populations would make "reported under both labels"
    a comparison of different things.

    Zone 101 reads 0.7 in bin 8 and 0.8 in bin 11, the two supported cells in
    the window, so the level is their mean. The residual subtracts a baseline;
    the level does not.
    """
    values = five_years_then(
        {(2022, 7): 0.9, (2022, 8): 0.7, (2022, 11): 0.8, (2022, 12): 0.2,
         (2021, 9): 0.6, (2022, 9): 0.95},
        bins=(7, 8, 11, 12),
    )
    con = outcomes(build(make_con(*staged_history(values))))
    level, label = con.execute(
        "SELECT level_ndvi, label_ndvi FROM zone_year_label "
        "WHERE zone_id = 101 AND year = 2022"
    ).fetchone()
    assert level == pytest.approx((0.7 + 0.8) / 2)
    assert level != pytest.approx(label), "the level must not subtract a baseline"


def test_feature_is_the_residual_in_the_latest_supported_vegetative_cell():
    """Bin 6 lacks support and bin 7 is outside the window, so bin 5 is latest."""
    values = five_years_then(
        {(2021, 2): 0.9, (2021, 5): 0.7, (2020, 6): 0.6, (2021, 6): 0.95, (2021, 7): 0.99},
        bins=(2, 5, 7), years=range(2018, 2021),
    )
    con = outcomes(build(make_con(*staged_history(values))))
    feature, feature_bin = con.execute(
        "SELECT feature_ndvi, feature_bin FROM zone_year_feature WHERE zone_id = 101 AND year = 2021"
    ).fetchone()
    assert feature_bin == 5
    assert feature == pytest.approx(0.2 - 0.1)


def test_feature_window_ends_before_the_gap_and_label_window_starts_after_it():
    """The feature must never see the label window."""
    from orbitalscout import config
    assert config.FEATURE_BINS[1] < config.GAP_BINS[0]
    assert config.GAP_BINS[0] <= config.GAP_BINS[1]
    assert config.GAP_BINS[1] < config.LABEL_BINS[0]


# --- all three indices must come from one observation. Step 5, Decision 17 ---
#
# S3 compares indices against each other. If they are picked from different
# dates the comparison measures the calendar, not the crop, and nothing raises.

def three_index_con(rows, gdd):
    """rows: (year, bin, ndvi, ndre, ndwi) for zone 101. 102 and 103 hold 0.5.

    The neighbours carry 0.5 in every index, so the field median is 0.5 and
    zone 101's relative index is its value minus 0.5 in each index separately.
    """
    obs = []
    for year, b, ndvi, ndre, ndwi in rows:
        date = f"{year}-06-{b + 1:02d}"
        obs += [(101, 1, year, date, ndvi, ndre, ndwi),
                (102, 1, year, date, 0.5, 0.5, 0.5),
                (103, 1, year, date, 0.5, 0.5, 0.5)]

    con = duckdb.connect()
    zone_obs = pd.DataFrame(obs, columns=["zone_id", "field_id", "year", "date",
                                          "ndvi", "ndre", "ndwi"])
    zone_obs["n_valid"] = 9
    con.register("zone_obs", zone_obs)
    con.register("fields", pd.DataFrame(
        [{"field_id": 1, **{f"crop_{y}": CORN for y in range(2018, 2026)}}]))
    con.register("zones", pd.DataFrame([(z, 1) for z in (101, 102, 103)],
                                       columns=["zone_id", "field_id"]))
    con.register("gdd", pd.DataFrame([(CORN, d, g) for d, g in gdd.items()],
                                     columns=["cdl_code", "date", "gdd"]))
    return outcomes(build(con))


def history_then(last_year_row, years=range(2018, 2022), bins=(5, 6)):
    """Four flat prior years so the floor of 3 is met, then one varying year."""
    rows = [(y, b, 0.6, 0.6, 0.6) for y in years for b in bins]
    rows.append(last_year_row)
    gdd = {f"{y}-06-{b + 1:02d}": b * 200 + 50
           for y in list(years) + [last_year_row[0]] for b in bins}
    return rows, gdd


def feature_row(con, year=2022):
    return con.execute(
        "SELECT feature_ndvi, feature_ndre, feature_ndwi, feature_bin "
        "FROM zone_year_feature WHERE zone_id = 101 AND year = ?", [year]
    ).fetchone()


def test_the_feature_carries_all_three_indices_from_the_same_bin():
    """NDRE and NDWI were ingested at Step 1 and nothing read them until S3."""
    rows, gdd = history_then((2022, 6, 0.9, 0.4, 0.2))
    rows += [(2022, 5, 0.6, 0.6, 0.6)]
    gdd["2022-06-06"] = 5 * 200 + 50
    ndvi, ndre, ndwi, bin_used = feature_row(three_index_con(rows, gdd))
    assert bin_used == 6
    assert ndvi == pytest.approx(0.4 - 0.1)      # 0.9 - 0.5 relative, minus baseline 0.1
    assert ndre == pytest.approx(-0.1 - 0.1)
    assert ndwi == pytest.approx(-0.3 - 0.1)


def test_a_null_index_in_the_top_cell_does_not_fall_back_to_an_earlier_date():
    """The trap: NDVI from bin 6 and NDRE from bin 5 is a divergence across dates.

    Bin 6 is the latest supported cell and its NDRE is missing. NDRE must come
    back null, not silently from bin 5, where the zone read very differently.
    """
    rows, gdd = history_then((2022, 6, 0.9, None, 0.2))
    rows += [(2022, 5, 0.1, 0.1, 0.1)]
    gdd["2022-06-06"] = 5 * 200 + 50
    ndvi, ndre, ndwi, bin_used = feature_row(three_index_con(rows, gdd))
    assert bin_used == 6, "the chosen cell is still the latest supported one"
    assert ndvi == pytest.approx(0.4 - 0.1)
    assert ndwi == pytest.approx(-0.3 - 0.1)
    assert ndre is None, "NDRE fell back to bin 5 and now describes another date"
