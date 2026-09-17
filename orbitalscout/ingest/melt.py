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
import pyarrow as pa
import pyarrow.parquet as pq
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
    """Open a raster, refusing a wrong CRS or a missing nodata value."""
    src = rasterio.open(path)
    if src.crs is None or src.crs.to_string() != TARGET_CRS:
        actual = src.crs.to_string() if src.crs else "none"
        src.close()
        raise ValueError(
            f"{path} is in {actual}, expected {TARGET_CRS}. "
            "Reprojection happens once at ingestion, never here."
        )
    if src.nodata is None:
        src.close()
        raise ValueError(
            f"{path} declares no nodata value, so a masked pixel cannot be "
            "told apart from a real zero. Earth Engine writes masked pixels as "
            "0 and omits the tag unless the export asks for one; re-export with "
            "formatOptions={'noData': ...}."
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


def _wide_columns(index_names):
    return ["zone_id", "field_id", "year", "date"] + list(index_names) + ["n_valid"]


def _iter_date_frames(values, counts, fields, value_bands, count_by_date, year,
                      min_valid, index_names):
    """One wide frame per acquisition date, so nothing holds a whole season.

    A season of real data is roughly 26 million rows in long form, which does
    not fit in memory once the index name is stored as a string on every row.
    The wide form carries the same information in a third of the rows without
    that column, and yielding per date bounds the peak regardless of season
    length.
    """
    field_arr = fields.read(1, masked=True)
    rows, cols = field_arr.shape
    col_idx, row_idx = np.meshgrid(np.arange(cols), np.arange(rows))
    xs, ys = values.xy(row_idx.ravel(), col_idx.ravel())  # pixel centres
    zone_ids = np.array(
        [zone_id_from_xy(x, y) for x, y in zip(xs, ys)], dtype="int64"
    ).reshape(rows, cols)

    # Field indices start at 1. Earth Engine fills the gap between the export
    # region and the raster bounding box with 0 rather than the declared
    # nodata, so a real export carries two absent markers and honouring only
    # the mask would admit every out-of-region pixel.
    in_field = ~np.ma.getmaskarray(field_arr) & (field_arr.filled(0) > 0)

    bands_by_date = {}
    for number, parts in value_bands.items():
        bands_by_date.setdefault(parts["date"], {})[parts["index"]] = number

    for stamp in sorted(bands_by_date):
        count_arr = counts.read(count_by_date[stamp], masked=True)
        keep = (
            in_field
            & ~np.ma.getmaskarray(count_arr)
            & (count_arr.filled(0) >= min_valid)
        )
        if not keep.any():
            continue

        frame = pd.DataFrame({
            "zone_id": zone_ids[keep],
            "field_id": field_arr.data[keep].astype("int64"),
            "year": year,
            "date": _iso(stamp),
            "n_valid": count_arr.data[keep].astype("int16"),
        })
        for name in index_names:
            number = bands_by_date[stamp].get(name)
            if number is None:
                frame[name] = np.nan
                continue
            value_arr = values.read(number, masked=True)
            column = np.where(
                np.ma.getmaskarray(value_arr)[keep],
                np.nan,
                value_arr.data[keep].astype("float64") / SCALE,
            )
            frame[name] = column
        yield frame[_wide_columns(index_names)]


def _prepare(values, counts, fields, value_path, count_path):
    value_bands = _parse_bands(values.descriptions, _VALUE_BAND, value_path)
    count_bands = _parse_bands(counts.descriptions, _COUNT_BAND, count_path)
    count_by_date = {p["date"]: n for n, p in count_bands.items()}
    missing = {p["date"] for p in value_bands.values()} - set(count_by_date)
    if missing:
        raise ValueError(
            f"{count_path} has no count band for date(s) {sorted(missing)}"
        )
    index_names = sorted({p["index"] for p in value_bands.values()})
    return value_bands, count_by_date, index_names


def melt_cube(value_path, count_path, field_path, year, min_valid=5):
    """Melt one season cube to wide rows, held in memory.

    The value cube carries every index, in bands named "<index>_<YYYYMMDD>".
    The count cube is per date only, in bands named "count_<YYYYMMDD>", because
    the cloud mask is shared across indices and so the valid sub-pixel count is
    the same for all of them.

    Returns one row per zone per date that survived masking, with one column
    per index. An index masked on a date it shares with others is NULL rather
    than zero, and the row survives. A zone-date with no valid observation at
    all is absent entirely.

    Use melt_cube_to_parquet for a real season; this holds the result.
    """
    with _open_checked(value_path) as values,          _open_checked(count_path) as counts,          _open_checked(field_path) as fields:
        value_bands, count_by_date, index_names = _prepare(
            values, counts, fields, value_path, count_path
        )
        frames = list(_iter_date_frames(
            values, counts, fields, value_bands, count_by_date, year,
            min_valid, index_names
        ))

    if not frames:
        return pd.DataFrame(columns=_wide_columns(index_names))
    return pd.concat(frames, ignore_index=True)


def melt_cube_to_parquet(value_path, count_path, field_path, year, out_path,
                         min_valid=5):
    """Same reshape, streamed one date at a time to a Parquet file.

    Returns the number of rows written. DuckDB reads the result directly,
    which is the reason SPEC Section 12 chose it.
    """
    writer = None
    written = 0
    try:
        with _open_checked(value_path) as values,              _open_checked(count_path) as counts,              _open_checked(field_path) as fields:
            value_bands, count_by_date, index_names = _prepare(
                values, counts, fields, value_path, count_path
            )
            for frame in _iter_date_frames(
                values, counts, fields, value_bands, count_by_date, year,
                min_valid, index_names
            ):
                table = pa.Table.from_pandas(frame, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(out_path, table.schema)
                writer.write_table(table)
                written += len(frame)
    finally:
        if writer is not None:
            writer.close()
    return written
