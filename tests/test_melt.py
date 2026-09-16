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


def write_raster(path, array, crs="EPSG:5070", descriptions=None, dtype="int16",
                 nodata=NODATA):
    """Write a small GeoTIFF. array is (bands, rows, cols)."""
    bands, rows, cols = array.shape
    transform = Affine(GRID, 0.0, ORIGIN_X, 0.0, -GRID, ORIGIN_Y)
    with rasterio.open(
        path, "w", driver="GTiff", height=rows, width=cols, count=bands,
        dtype=dtype, crs=crs, transform=transform, nodata=nodata,
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
    dates = ["20200601", "20200611"]
    # One cube carries every index. Band order is index-major.
    bands = [f"{ix}_{d}" for ix in ("ndvi", "ndre", "ndwi") for d in dates]
    values = np.full((6, 2, 2), int(0.25 * SCALE), dtype="int16")
    values[1::2] = int(0.50 * SCALE)  # second date of each index
    counts = np.full((2, 2, 2), 9, dtype="int16")  # per date, mask is shared
    fields = np.full((1, 2, 2), 7, dtype="int32")

    v, c, f = tmp_path / "v.tif", tmp_path / "c.tif", tmp_path / "f.tif"
    write_raster(v, values, descriptions=bands)
    write_raster(c, counts, descriptions=[f"count_{d}" for d in dates])
    write_raster(f, fields, dtype="int32")
    return {"value": v, "count": c, "field": f, "dates": dates, "bands": bands}


def melt_cube(paths, **kw):
    return melt.melt_cube(
        value_path=paths["value"], count_path=paths["count"],
        field_path=paths["field"], year=2020, **kw
    )


def test_all_valid_cube_yields_one_row_per_zone_date_index(cube):
    df = melt_cube(cube)
    assert len(df) == 24  # 4 zones x 2 dates x 3 indices
    assert set(df["index"]) == {"ndvi", "ndre", "ndwi"}
    assert set(df["date"]) == {"2020-06-01", "2020-06-11"}
    assert set(df.columns) == {
        "zone_id", "field_id", "year", "date", "index", "value", "n_valid"
    }
    assert df["value"].min() == pytest.approx(0.25)
    assert df["value"].max() == pytest.approx(0.50)
    assert (df["field_id"] == 7).all()


def test_masked_pixel_produces_no_row_and_never_a_zero(cube, tmp_path):
    """The load-bearing test. A masked pixel must vanish, not become 0.0."""
    values = np.full((6, 2, 2), int(0.25 * SCALE), dtype="int16")
    values[1::2] = int(0.50 * SCALE)
    values[0, 1, 1] = NODATA  # one pixel, one date, one index, masked
    write_raster(cube["value"], values, descriptions=cube["bands"])

    df = melt_cube(cube)

    assert len(df) == 23, "masked pixel should drop a row, not zero-fill it"
    assert not (df["value"] == 0).any(), "a masked pixel became a zero"

    masked_zone = melt.zone_id_from_xy(ORIGIN_X + 1.5 * GRID, ORIGIN_Y - 1.5 * GRID)
    gone = df[(df["zone_id"] == masked_zone) & (df["date"] == "2020-06-01")
              & (df["index"] == "ndvi")]
    assert len(gone) == 0
    # The other indices on that same date are untouched.
    others = df[(df["zone_id"] == masked_zone) & (df["date"] == "2020-06-01")]
    assert set(others["index"]) == {"ndre", "ndwi"}


def test_subpixel_count_below_minimum_produces_no_row(cube):
    counts = np.full((2, 2, 2), 9, dtype="int16")
    counts[0, 0, 0] = 4  # below the default minimum of 5
    write_raster(cube["count"], counts, descriptions=[f"count_{d}" for d in cube["dates"]])

    df = melt_cube(cube, min_valid=5)

    # One zone-date drops for every index, because the mask is shared.
    assert len(df) == 21
    assert df["n_valid"].min() >= 5


def test_pixel_outside_any_field_produces_no_row(cube):
    fields = np.full((1, 2, 2), 7, dtype="int32")
    fields[0, 0, 0] = NODATA
    write_raster(cube["field"], fields, dtype="int32")

    df = melt_cube(cube)

    assert len(df) == 18  # one zone gone on both dates, all three indices
    assert (df["field_id"] == 7).all()


def test_wrong_crs_raises_and_does_not_reproject(cube):
    values = np.full((6, 2, 2), int(0.25 * SCALE), dtype="int16")
    write_raster(cube["value"], values, crs="EPSG:4326", descriptions=cube["bands"])

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


def test_date_present_in_values_but_missing_from_counts_raises(cube):
    counts = np.full((1, 2, 2), 9, dtype="int16")
    write_raster(cube["count"], counts, descriptions=["count_20200601"])

    with pytest.raises(ValueError, match="20200611"):
        melt_cube(cube)


def test_unparseable_band_name_raises_rather_than_being_skipped(cube):
    bad = list(cube["bands"]); bad[0] = "mystery_band"
    values = np.full((6, 2, 2), int(0.25 * SCALE), dtype="int16")
    write_raster(cube["value"], values, descriptions=bad)

    with pytest.raises(ValueError, match="mystery_band"):
        melt_cube(cube)


def test_raster_without_a_nodata_value_raises(cube):
    """A GeoTIFF with no nodata tag cannot distinguish masked from zero.

    Earth Engine writes masked pixels as 0 and omits the nodata tag unless it
    is asked for one. Reading such a file with masked=True masks nothing, so
    every cloudy pixel silently becomes a valid observation of zero greenness.
    This is the real-export shape of the bug the whole module guards against,
    and the synthetic fixtures did not reproduce it, so it is asserted here.
    """
    values = np.full((6, 2, 2), int(0.25 * SCALE), dtype="int16")
    write_raster(cube["value"], values, descriptions=cube["bands"], nodata=None)

    with pytest.raises(ValueError, match="nodata"):
        melt_cube(cube)
