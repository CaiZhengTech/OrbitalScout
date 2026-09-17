"""Characterization test against a crop of the real Earth Engine export.

Every other test in this suite builds its own rasters, and that is exactly how
four of the five Step 1 defects got through: the fixtures were written from the
same mental model that produced the bug, so they reproduced a file shape the
real export never emits. In particular they always declared a nodata value and
used a single absent marker, while a real export declares nodata only when the
export asks for it and separately zero-fills the gap between the export region
and the raster bounding box.

This fixture is a 32x32 window cut from `orbitalscout_values_2020.tif` and its
companions, about 20 KB total, carrying all three markers: valid cells, cells
masked by cloud, and cells zero-filled outside the export region.

The expected values below were measured once from a pipeline that had already
been verified against Planetary Computer (`RESULTS.md`, Step 1 cross-check).
They are a regression fence, not an independent oracle: if they change,
something in the reshape changed, and that needs a reason.
"""

import pathlib

import pytest

from orbitalscout.ingest import melt

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

# Measured 2026-09-17 from the verified pipeline.
EXPECTED_ROWS = 1192
EXPECTED_ZONES = 596
EXPECTED_DATES = ["2020-05-01", "2020-05-09"]
EXPECTED_FIELDS = [171, 172, 193, 195]
EXPECTED_NDVI_SUM = 228.714


@pytest.fixture
def melted():
    return melt.melt_cube(
        value_path=FIXTURES / "values_2020_crop.tif",
        count_path=FIXTURES / "counts_2020_crop.tif",
        field_path=FIXTURES / "fieldid_crop.tif",
        year=2020,
        min_valid=5,
    )


def test_real_export_melts_to_the_expected_shape(melted):
    assert len(melted) == EXPECTED_ROWS
    assert melted["zone_id"].nunique() == EXPECTED_ZONES
    assert sorted(melted["date"].unique()) == EXPECTED_DATES
    assert sorted(int(f) for f in melted["field_id"].unique()) == EXPECTED_FIELDS


def test_real_export_values_are_unchanged(melted):
    """A regression fence on the arithmetic, not just the row count."""
    assert melted["ndvi"].sum() == pytest.approx(EXPECTED_NDVI_SUM, abs=1e-3)
    assert melted["ndvi"].min() == pytest.approx(0.14, abs=1e-6)
    assert melted["ndvi"].max() == pytest.approx(0.7226, abs=1e-6)


def test_no_zero_filled_pixel_became_an_observation(melted):
    """The window contains cells Earth Engine zero-filled outside the region.

    Those carry field_id 0 and value 0 in the file. If any reached the output
    they would read as a real observation of zero greenness, which is the
    failure this whole module exists to prevent.
    """
    assert (melted["field_id"] > 0).all()
    assert not (melted["ndvi"] == 0).any()


def test_cloud_masked_cells_are_absent_rather_than_zero(melted):
    """21% of the window is masked in the field raster and must not appear."""
    cells_in_window = 32 * 32
    assert len(melted) < cells_in_window * len(EXPECTED_DATES)
    assert (melted["n_valid"] >= 5).all()
