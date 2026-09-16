"""Tests for the cube-to-long-rows reshape.

The reshape is where a masked pixel could silently become a zero. Nothing
downstream would raise; every statistic would just be wrong. That is the
failure mode SPEC Section 14 calls out as needing a test, so it gets one here
before any implementation exists.
"""

import numpy as np
import pytest
import rasterio
from affine import Affine

from orbitalscout.ingest import melt

NODATA = -32768
SCALE = 10000
GRID = 30

# Arbitrary EPSG:5070 origin inside Iowa, snapped to the 30m grid.
ORIGIN_X = 150_000.0
ORIGIN_Y = 2_100_000.0


def write_raster(path, array, crs="EPSG:5070", descriptions=None, dtype="int16"):
    """Write a small GeoTIFF. array is (bands, rows, cols)."""
    bands, rows, cols = array.shape
    transform = Affine(GRID, 0.0, ORIGIN_X, 0.0, -GRID, ORIGIN_Y)
    with rasterio.open(
        path, "w", driver="GTiff", height=rows, width=cols, count=bands,
        dtype=dtype, crs=crs, transform=transform, nodata=NODATA,
    ) as dst:
        dst.write(array)
        if descriptions:
            for i, name in enumerate(descriptions, start=1):
                dst.set_band_description(i, name)


@pytest.fixture
def cube(tmp_path):
    """A 2x2 zone grid over two dates, all valid, all inside one field.

    Values are 0.25 and 0.50 NDVI everywhere, stored scaled by 10000.
    """
    dates = ["2020-06-01", "2020-06-11"]
    values = np.full((2, 2, 2), int(0.25 * SCALE), dtype="int16")
    values[1] = int(0.50 * SCALE)
    counts = np.full((2, 2, 2), 9, dtype="int16")
    fields = np.full((1, 2, 2), 7, dtype="int32")

    v, c, f = tmp_path / "v.tif", tmp_path / "c.tif", tmp_path / "f.tif"
    write_raster(v, values, descriptions=dates)
    write_raster(c, counts, descriptions=dates)
    write_raster(f, fields, dtype="int32")
    return {"value": v, "count": c, "field": f, "dates": dates}


def melt_cube(paths, **kw):
    return melt.melt_cube(
        value_path=paths["value"], count_path=paths["count"],
        field_path=paths["field"], index_name="ndvi", year=2020, **kw
    )


def test_all_valid_cube_yields_one_row_per_zone_date(cube):
    df = melt_cube(cube)
    assert len(df) == 8  # 4 zones x 2 dates
    assert set(df.columns) == {
        "zone_id", "field_id", "year", "date", "index", "value", "n_valid"
    }
    assert df["value"].min() == pytest.approx(0.25)
    assert df["value"].max() == pytest.approx(0.50)
    assert (df["field_id"] == 7).all()
    assert (df["index"] == "ndvi").all()


def test_masked_pixel_produces_no_row_and_never_a_zero(cube, tmp_path):
    """The load-bearing test. A masked pixel must vanish, not become 0.0."""
    values = np.full((2, 2, 2), int(0.25 * SCALE), dtype="int16")
    values[1] = int(0.50 * SCALE)
    values[0, 1, 1] = NODATA  # one pixel, one date, masked
    write_raster(cube["value"], values, descriptions=cube["dates"])

    df = melt_cube(cube)

    assert len(df) == 7, "masked pixel should drop a row, not zero-fill it"
    assert not (df["value"] == 0).any(), "a masked pixel became a zero"

    masked_zone = melt.zone_id_from_xy(ORIGIN_X + 1.5 * GRID, ORIGIN_Y - 1.5 * GRID)
    present = df[(df["zone_id"] == masked_zone) & (df["date"] == "2020-06-01")]
    assert len(present) == 0
    # The same zone on the other date survives.
    other = df[(df["zone_id"] == masked_zone) & (df["date"] == "2020-06-11")]
    assert len(other) == 1


def test_subpixel_count_below_minimum_produces_no_row(cube):
    counts = np.full((2, 2, 2), 9, dtype="int16")
    counts[0, 0, 0] = 4  # below the default minimum of 5
    write_raster(cube["count"], counts, descriptions=cube["dates"])

    df = melt_cube(cube, min_valid=5)

    assert len(df) == 7
    assert df["n_valid"].min() >= 5


def test_pixel_outside_any_field_produces_no_row(cube):
    fields = np.full((1, 2, 2), 7, dtype="int32")
    fields[0, 0, 0] = NODATA
    write_raster(cube["field"], fields, dtype="int32")

    df = melt_cube(cube)

    assert len(df) == 6  # one zone gone on both dates
    assert (df["field_id"] == 7).all()


def test_wrong_crs_raises_and_does_not_reproject(cube):
    values = np.full((2, 2, 2), int(0.25 * SCALE), dtype="int16")
    write_raster(cube["value"], values, crs="EPSG:4326", descriptions=cube["dates"])

    with pytest.raises(ValueError, match="EPSG:5070"):
        melt_cube(cube)


def test_zone_id_round_trips_for_grid_aligned_coordinates():
    """Zone identity is a grid cell, so exact round-trip holds on the grid."""
    for x, y in [(ORIGIN_X, ORIGIN_Y), (-2_100_000.0, 300_000.0), (2_199_990.0, 3_100_020.0)]:
        zid = melt.zone_id_from_xy(x, y)
        back_x, back_y = melt.xy_from_zone_id(zid)
        assert back_x == pytest.approx(x)
        assert back_y == pytest.approx(y)


def test_zone_id_snaps_any_point_to_its_containing_cell():
    """Every point inside one cell maps to that cell, so pixel centres work."""
    corner = melt.zone_id_from_xy(ORIGIN_X, ORIGIN_Y)
    assert melt.zone_id_from_xy(ORIGIN_X + 0.1, ORIGIN_Y + 0.1) == corner
    assert melt.zone_id_from_xy(ORIGIN_X + GRID - 0.1, ORIGIN_Y + GRID - 0.1) == corner
    assert melt.zone_id_from_xy(ORIGIN_X + GRID, ORIGIN_Y) != corner


def test_band_count_mismatch_between_value_and_count_raises(cube):
    counts = np.full((1, 2, 2), 9, dtype="int16")
    write_raster(cube["count"], counts, descriptions=cube["dates"][:1])

    with pytest.raises(ValueError, match="band"):
        melt_cube(cube)
