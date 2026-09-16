"""Reshape an Earth Engine cube export into long rows.

A reshape and nothing else. No masking, no reprojection, no aggregation and no
thresholds beyond the minimum-valid-subpixel rule that SPEC Section 6 defines.
All of those happen once, in Earth Engine, per SPEC Section 11.

The one thing this must never do is turn a masked pixel into a zero. A masked
pixel has no observation, and an absent row is how that is represented.
"""

import math
import re

import numpy as np
import pandas as pd
import rasterio

TARGET_CRS = "EPSG:5070"
ZONE_GRID_M = 30
SCALE = 10000

# Offsets keep the packed id positive and unambiguous for CONUS in EPSG:5070,
# where easting spans roughly -2.4e6 to 2.3e6 and northing 0.2e6 to 3.2e6.
_OFFSET = 1_000_000
_STRIDE = 10_000_000


def zone_id_from_xy(x, y, grid=ZONE_GRID_M):
    """Pack a coordinate into the integer id of the grid cell containing it."""
    col = math.floor(x / grid)
    row = math.floor(y / grid)
    return (col + _OFFSET) * _STRIDE + (row + _OFFSET)


def xy_from_zone_id(zone_id, grid=ZONE_GRID_M):
    """Unpack a zone id back to its cell origin."""
    col = zone_id // _STRIDE - _OFFSET
    row = zone_id % _STRIDE - _OFFSET
    return col * grid, row * grid


def _open_checked(path):
    """Open a raster, refusing anything not already in the target CRS."""
    src = rasterio.open(path)
    if src.crs is None or src.crs.to_string() != TARGET_CRS:
        actual = src.crs.to_string() if src.crs else "none"
        src.close()
        raise ValueError(
            f"{path} is in {actual}, expected {TARGET_CRS}. "
            "Reprojection happens once at ingestion, never here."
        )
    return src


_VALUE_BAND = re.compile(r"^(?P<index>[a-z][a-z0-9]*)_(?P<date>\d{8})$")
_COUNT_BAND = re.compile(r"^count_(?P<date>\d{8})$")


def _parse_bands(descriptions, pattern, path):
    """Map band number to its parsed parts, refusing anything unrecognised.

    An unparseable band is raised on rather than skipped. Skipping would drop
    real observations and leave no trace, which is the failure mode this whole
    module exists to avoid.
    """
    parsed = {}
    for number, name in enumerate(descriptions, start=1):
        match = pattern.match(name or "")
        if not match:
            raise ValueError(f"{path} has unparseable band name {name!r}")
        parsed[number] = match.groupdict()
    return parsed


def _iso(compact):
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"


def melt_cube(value_path, count_path, field_path, year, min_valid=5):
    """Melt one season cube to long rows.

    The value cube carries every index, in bands named "<index>_<YYYYMMDD>".
    The count cube is per date only, in bands named "count_<YYYYMMDD>", because
    the cloud mask is shared across indices and so the valid sub-pixel count is
    the same for all of them.

    Returns columns zone_id, field_id, year, date, index, value, n_valid.
    One row per zone per date per index that survived masking. Absent means
    masked; a masked pixel never becomes a zero.
    """
    with _open_checked(value_path) as values, \
         _open_checked(count_path) as counts, \
         _open_checked(field_path) as fields:

        value_bands = _parse_bands(values.descriptions, _VALUE_BAND, value_path)
        count_bands = _parse_bands(counts.descriptions, _COUNT_BAND, count_path)
        count_by_date = {p["date"]: n for n, p in count_bands.items()}

        missing = {p["date"] for p in value_bands.values()} - set(count_by_date)
        if missing:
            raise ValueError(
                f"{count_path} has no count band for date(s) {sorted(missing)}"
            )

        field_arr = fields.read(1, masked=True)
        rows, cols = field_arr.shape
        col_idx, row_idx = np.meshgrid(np.arange(cols), np.arange(rows))
        xs, ys = values.xy(row_idx.ravel(), col_idx.ravel())  # pixel centres
        zone_ids = np.array(
            [zone_id_from_xy(x, y) for x, y in zip(xs, ys)], dtype="int64"
        ).reshape(rows, cols)

        frames = []
        for band, parts in value_bands.items():
            value_arr = values.read(band, masked=True)
            count_arr = counts.read(count_by_date[parts["date"]], masked=True)

            keep = (
                ~np.ma.getmaskarray(value_arr)
                & ~np.ma.getmaskarray(count_arr)
                & ~np.ma.getmaskarray(field_arr)
                & (count_arr.filled(0) >= min_valid)
            )
            if not keep.any():
                continue

            frames.append(pd.DataFrame({
                "zone_id": zone_ids[keep],
                "field_id": field_arr.data[keep].astype("int64"),
                "year": year,
                "date": _iso(parts["date"]),
                "index": parts["index"],
                "value": value_arr.data[keep].astype("float64") / SCALE,
                "n_valid": count_arr.data[keep].astype("int16"),
            }))

    columns = ["zone_id", "field_id", "year", "date", "index", "value", "n_valid"]
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)[columns]
