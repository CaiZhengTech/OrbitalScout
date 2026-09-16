"""Tests for the long-to-wide load into the three-table DuckDB contract.

The melt produces one row per zone-date-index. The contract in
`docs/reviews/2026-09-15-step1-architecture.md` Decision 5 is one row per
zone-date with a column per index, so the load pivots.

The pivot is the second place a missing observation could silently become a
number. If a zone was clear for NDVI but its NDRE band was masked, the NDRE
column must be NULL, not zero, and not the row dropped entirely.
"""

import duckdb
import pandas as pd
import pytest

from orbitalscout.ingest import load


def obs(zone_id, date, index, value, n_valid=9, field_id=7, year=2020):
    return {
        "zone_id": zone_id, "field_id": field_id, "year": year, "date": date,
        "index": index, "value": value, "n_valid": n_valid,
    }


@pytest.fixture
def melted():
    rows = []
    for zone in (1001, 1002):
        for date in ("2020-06-01", "2020-06-11"):
            for index, value in (("ndvi", 0.5), ("ndre", 0.3), ("ndwi", 0.1)):
                rows.append(obs(zone, date, index, value))
    return pd.DataFrame(rows)


@pytest.fixture
def fields():
    return pd.DataFrame([{
        "field_id": 7, "csbid": "191825000655875", "area_m2": 299829.28,
        **{f"crop_{y}": 1 for y in range(2018, 2026)},
    }])


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "test.duckdb")


def test_zone_obs_is_one_row_per_zone_date_with_a_column_per_index(db, melted, fields):
    load.load(db, melted, fields)
    con = duckdb.connect(db)
    rows = con.execute(
        "SELECT zone_id, date, ndvi, ndre, ndwi, n_valid FROM zone_obs ORDER BY zone_id, date"
    ).fetchall()
    assert len(rows) == 4  # 2 zones x 2 dates, not 12
    assert rows[0] == (1001, "2020-06-01", 0.5, 0.3, 0.1, 9)


def test_index_missing_for_one_zone_date_is_null_not_zero(db, melted, fields):
    """A masked band must not become a 0.0 in the pivoted table."""
    melted = melted[~((melted["zone_id"] == 1001)
                      & (melted["date"] == "2020-06-01")
                      & (melted["index"] == "ndre"))]
    load.load(db, melted, fields)
    con = duckdb.connect(db)

    value = con.execute(
        "SELECT ndre FROM zone_obs WHERE zone_id=1001 AND date='2020-06-01'"
    ).fetchone()[0]
    assert value is None, "a masked index became a number"

    # The row survives, and its other indices are intact.
    ndvi = con.execute(
        "SELECT ndvi FROM zone_obs WHERE zone_id=1001 AND date='2020-06-01'"
    ).fetchone()[0]
    assert ndvi == 0.5
    assert con.execute("SELECT count(*) FROM zone_obs").fetchone()[0] == 4


def test_zones_table_is_one_row_per_zone_with_recoverable_coordinates(db, melted, fields):
    load.load(db, melted, fields)
    con = duckdb.connect(db)
    rows = con.execute("SELECT zone_id, field_id, x_5070, y_5070 FROM zones ORDER BY zone_id").fetchall()
    assert len(rows) == 2

    from orbitalscout.ingest.melt import xy_from_zone_id
    for zone_id, _, x, y in rows:
        assert (x, y) == xy_from_zone_id(zone_id)


def test_every_zone_points_at_a_real_field(db, melted, fields):
    load.load(db, melted, fields)
    con = duckdb.connect(db)
    orphans = con.execute(
        "SELECT count(*) FROM zones z LEFT JOIN fields f USING (field_id) WHERE f.field_id IS NULL"
    ).fetchone()[0]
    assert orphans == 0


def test_loading_twice_does_not_duplicate_rows(db, melted, fields):
    load.load(db, melted, fields)
    load.load(db, melted, fields)
    con = duckdb.connect(db)
    assert con.execute("SELECT count(*) FROM zone_obs").fetchone()[0] == 4
    assert con.execute("SELECT count(*) FROM zones").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM fields").fetchone()[0] == 1


def test_conflicting_values_for_one_zone_date_index_raises(db, melted, fields):
    """Two different values for the same cell means the export was wrong."""
    dup = melted.iloc[[0]].copy()
    dup["value"] = 0.99
    clashing = pd.concat([melted, dup], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate"):
        load.load(db, clashing, fields)


def test_unknown_index_name_raises_rather_than_being_dropped(db, melted, fields):
    stray = melted.iloc[[0]].copy()
    stray["index"] = "evi"
    with pytest.raises(ValueError, match="evi"):
        load.load(db, pd.concat([melted, stray], ignore_index=True), fields)
