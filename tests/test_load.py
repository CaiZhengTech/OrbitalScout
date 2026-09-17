"""Tests for the load into the three-table DuckDB contract.

`melt` now writes wide Parquet, one row per zone-date with a column per index,
so `load` no longer pivots. Its job is to assemble the three tables of
`docs/reviews/2026-09-15-step1-architecture.md` Decision 5 and refuse anything
that would leave them inconsistent.
"""

import duckdb
import pandas as pd
import pytest

from orbitalscout.ingest import load


@pytest.fixture
def zone_obs(tmp_path):
    rows = []
    for zone in (1001, 1002):
        for date in ("2020-06-01", "2020-06-11"):
            rows.append({
                "zone_id": zone, "field_id": 7, "year": 2020, "date": date,
                "ndvi": 0.5, "ndre": 0.3, "ndwi": 0.1, "n_valid": 9,
            })
    path = tmp_path / "zone_obs_2020.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


@pytest.fixture
def fields():
    return pd.DataFrame([{
        "field_id": 7, "csbid": "191825000655875", "area_m2": 299829.28,
        **{f"crop_{y}": 1 for y in range(2018, 2026)},
    }])


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "test.duckdb")


def test_zone_obs_is_one_row_per_zone_date(db, zone_obs, fields):
    load.load(db, str(zone_obs), fields)
    con = duckdb.connect(db)
    rows = con.execute(
        "SELECT zone_id, date, ndvi, ndre, ndwi, n_valid FROM zone_obs "
        "ORDER BY zone_id, date"
    ).fetchall()
    assert len(rows) == 4
    assert rows[0] == (1001, "2020-06-01", 0.5, 0.3, 0.1, 9)


def test_a_null_index_survives_the_load_as_null(db, tmp_path, fields):
    """A masked index must stay NULL through the load, never become 0."""
    frame = pd.DataFrame([{
        "zone_id": 1001, "field_id": 7, "year": 2020, "date": "2020-06-01",
        "ndvi": 0.5, "ndre": None, "ndwi": 0.1, "n_valid": 9,
    }])
    path = tmp_path / "zone_obs_2020.parquet"
    frame.to_parquet(path, index=False)

    load.load(db, str(path), fields)
    value = duckdb.connect(db).execute("SELECT ndre FROM zone_obs").fetchone()[0]
    assert value is None


def test_zones_table_has_recoverable_coordinates(db, zone_obs, fields):
    load.load(db, str(zone_obs), fields)
    rows = duckdb.connect(db).execute(
        "SELECT zone_id, field_id, x_5070, y_5070 FROM zones ORDER BY zone_id"
    ).fetchall()
    assert len(rows) == 2

    from orbitalscout.ingest.melt import xy_from_zone_id
    for zone_id, _, x, y in rows:
        assert (x, y) == xy_from_zone_id(zone_id)


def test_every_zone_points_at_a_real_field(db, zone_obs, fields):
    load.load(db, str(zone_obs), fields)
    orphans = duckdb.connect(db).execute(
        "SELECT count(*) FROM zones z LEFT JOIN fields f USING (field_id) "
        "WHERE f.field_id IS NULL"
    ).fetchone()[0]
    assert orphans == 0


def test_a_zone_referencing_an_unknown_field_raises(db, zone_obs):
    """The raster and the lookup table must have been built together."""
    wrong = pd.DataFrame([{
        "field_id": 999, "csbid": "x", "area_m2": 1.0,
        **{f"crop_{y}": 1 for y in range(2018, 2026)},
    }])
    with pytest.raises(ValueError, match="field"):
        load.load(db, str(zone_obs), wrong)


def test_loading_twice_does_not_duplicate_rows(db, zone_obs, fields):
    load.load(db, str(zone_obs), fields)
    load.load(db, str(zone_obs), fields)
    con = duckdb.connect(db)
    assert con.execute("SELECT count(*) FROM zone_obs").fetchone()[0] == 4
    assert con.execute("SELECT count(*) FROM zones").fetchone()[0] == 2


def test_duplicate_zone_date_raises(db, tmp_path, fields):
    """Two rows for one zone-date means the export was written twice."""
    row = {
        "zone_id": 1001, "field_id": 7, "year": 2020, "date": "2020-06-01",
        "ndvi": 0.5, "ndre": 0.3, "ndwi": 0.1, "n_valid": 9,
    }
    path = tmp_path / "zone_obs_2020.parquet"
    pd.DataFrame([row, row]).to_parquet(path, index=False)

    with pytest.raises(ValueError, match="duplicate"):
        load.load(db, str(path), fields)


def test_multiple_season_files_load_together(db, tmp_path, fields):
    """Eight seasons arrive as eight files and must land in one table."""
    for year, date in ((2020, "2020-06-01"), (2021, "2021-06-05")):
        pd.DataFrame([{
            "zone_id": 1001, "field_id": 7, "year": year, "date": date,
            "ndvi": 0.5, "ndre": 0.3, "ndwi": 0.1, "n_valid": 9,
        }]).to_parquet(tmp_path / f"zone_obs_{year}.parquet", index=False)

    load.load(db, str(tmp_path / "zone_obs_*.parquet"), fields)
    con = duckdb.connect(db)
    assert con.execute("SELECT count(*) FROM zone_obs").fetchone()[0] == 2
    assert con.execute("SELECT count(DISTINCT year) FROM zone_obs").fetchone()[0] == 2


def test_zone_obs_is_a_view_not_a_copy(db, zone_obs, fields):
    """The Parquet is the data; the database must not duplicate it.

    Materialising zone_obs as a table copies every row into the .duckdb file,
    which for eight seasons is 1.5 GB duplicated and was enough to get the load
    killed for memory. SPEC Section 12 chose DuckDB over Parquet so the rows
    can stay where they are.
    """
    load.load(db, str(zone_obs), fields)
    kind = duckdb.connect(db).execute(
        "SELECT table_type FROM information_schema.tables WHERE table_name = 'zone_obs'"
    ).fetchone()[0]
    assert kind == "VIEW"


def test_database_file_stays_small_relative_to_the_parquet(db, zone_obs, fields):
    import pathlib
    load.load(db, str(zone_obs), fields)
    assert pathlib.Path(db).stat().st_size < 4 * 1024 * 1024
