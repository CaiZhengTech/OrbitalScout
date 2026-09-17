"""Compare exported NDVI against an independent Planetary Computer pull.

Samples zone-dates from the loaded database, fetches the same Sentinel-2
scenes from Planetary Computer, computes NDVI over the same 30m footprint,
and reports the difference against tolerances fixed in crosscheck.py before
the run.

Needs network access. Not part of CI, per SPEC Section 14.

Run:
    python scripts/run_crosscheck.py --zones 20
"""

import argparse
import os
import sys
import warnings

import duckdb
import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.warp import transform_bounds

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config  # noqa: E402
from orbitalscout.ingest import crosscheck  # noqa: E402
from orbitalscout.ingest.melt import ZONE_GRID_M  # noqa: E402

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"


def sample_zone_dates(db_path, n_zones, seed):
    """One date per sampled zone, taken from the middle of the season."""
    con = duckdb.connect(db_path)
    # Deterministic hash ordering rather than USING SAMPLE. The sampler can be
    # applied before an outer filter, which silently shrinks the result, and it
    # returned nothing at all inside CREATE TABLE AS SELECT DISTINCT. Ordering
    # by a hash of the id is exact, reproducible, and depends on no sampler
    # semantics.
    con.execute(f"""
        CREATE TEMP TABLE picked AS
        SELECT zone_id FROM (
            SELECT DISTINCT zone_id FROM zone_obs
            WHERE ndvi IS NOT NULL AND date BETWEEN '2020-06-15' AND '2020-08-15'
        ) ORDER BY hash(zone_id + {seed}) LIMIT {n_zones}
    """)
    rows = con.execute("""
        SELECT zone_id, x_5070, y_5070, date, ndvi FROM (
            SELECT o.zone_id, z.x_5070, z.y_5070, o.date, o.ndvi,
                   row_number() OVER (PARTITION BY o.zone_id ORDER BY o.date) AS rn
            FROM zone_obs o
            JOIN zones z USING (zone_id)
            JOIN picked p USING (zone_id)
            WHERE o.ndvi IS NOT NULL AND o.date BETWEEN '2020-06-15' AND '2020-08-15'
        ) WHERE rn = 1
    """).fetchall()
    con.close()
    return rows


def planetary_ndvi(x, y, date):
    """NDVI over the same 30m cell, from Planetary Computer's own COGs.

    Reads the red and NIR assets directly with rasterio rather than going
    through odc-stac, so the only shared code with the Earth Engine path is
    the arithmetic of a normalised difference.
    """
    # The zone is a 30m cell whose origin is (x, y) in EPSG:5070.
    west, south, east, north = x, y, x + ZONE_GRID_M, y + ZONE_GRID_M
    lon_w, lat_s, lon_e, lat_n = transform_bounds(
        "EPSG:5070", "EPSG:4326", west, south, east, north
    )
    centre = ((lon_w + lon_e) / 2, (lat_s + lat_n) / 2)

    catalog = pystac_client.Client.open(STAC, modifier=planetary_computer.sign_inplace)
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        intersects={"type": "Point", "coordinates": list(centre)},
        datetime=f"{date}/{date}",
    )
    items = list(search.items())
    if not items:
        return np.nan

    item = items[0]
    values = {}
    for band, asset in (("nir", "B08"), ("red", "B04")):
        with rasterio.open(item.assets[asset].href) as src:
            bounds = transform_bounds("EPSG:5070", src.crs, west, south, east, north)
            window = rasterio.windows.from_bounds(*bounds, transform=src.transform)
            block = src.read(1, window=window, masked=True).astype("float64")
            if block.size == 0 or block.mask.all():
                return np.nan
            values[band] = float(block.mean())

    nir, red = values["nir"], values["red"]
    # Planetary Computer serves the same harmonized L2A scaling as the Earth
    # Engine collection, so the offset cancels in a normalised difference.
    if nir + red == 0:
        return np.nan
    return (nir - red) / (nir + red)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zones", type=int, default=20)
    parser.add_argument("--seed", type=int, default=config.SAMPLE_SEED)
    parser.add_argument("--db", default="data/orbitalscout.duckdb")
    args = parser.parse_args()

    print("Tolerances, fixed in crosscheck.py before this run:")
    print(f"  median absolute difference <= {crosscheck.MEDIAN_TOLERANCE}")
    print(f"  max absolute difference    <= {crosscheck.MAX_TOLERANCE}\n")

    rows = sample_zone_dates(args.db, args.zones, args.seed)
    print(f"sampled {len(rows)} zone-dates\n")

    ours, theirs = [], []
    for zone_id, x, y, date, ndvi in rows:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                other = planetary_ndvi(x, y, date)
            except Exception as exc:  # noqa: BLE001
                print(f"  {zone_id} {date}: fetch failed, {str(exc)[:60]}")
                other = np.nan
        ours.append(ndvi)
        theirs.append(other)
        flag = "" if np.isnan(other) else f"  diff {abs(ndvi - other):.4f}"
        print(f"  {zone_id} {date}: ours {ndvi:.4f}  theirs "
              f"{'n/a' if np.isnan(other) else f'{other:.4f}'}{flag}")

    result = crosscheck.compare(ours, theirs)
    print("\nresult:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
