"""Materialise the AOI and the selected field set as Earth Engine assets.

Run once. Every later step reads the assets rather than recomputing, because
build_aoi derives the polygon from live Sentinel-2 footprints and Earth Engine
reprocesses scenes. A footprint that shifts at the coverage margin moves a
field in or out, and since field numbering is dense and sorted, that renumbers
every field after it. Architecture note Decision 4.

Re-running after any export would invalidate every raster already produced, so
this refuses to overwrite an existing asset.

Run:
    python scripts/freeze_aoi.py --project YOUR_EE_PROJECT
"""

import argparse
import os
import sys

import ee

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config  # noqa: E402
from orbitalscout.ingest import gee  # noqa: E402


def exists(asset_id):
    try:
        ee.data.getAsset(asset_id)
        return True
    except ee.EEException:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=os.environ.get("ORBITALSCOUT_EE_PROJECT"))
    args = parser.parse_args()
    if not args.project:
        parser.error("pass --project or set ORBITALSCOUT_EE_PROJECT")

    ee.Initialize(project=args.project)
    aoi_id = config.AOI_ASSET.format(project=args.project)
    fields_id = config.FIELDS_ASSET.format(project=args.project)

    present = [a for a in (aoi_id, fields_id) if exists(a)]
    if present:
        raise SystemExit(
            "already frozen:\n  " + "\n  ".join(present) +
            "\nRefusing to overwrite. Every raster exported so far is numbered "
            "against this field set; re-freezing would invalidate all of them."
        )

    aoi = gee.build_aoi()
    fields = gee.indexed_fields(gee.selected_fields(aoi))
    print(f"freezing {fields.size().getInfo()} fields")

    for collection, asset_id, name in (
        (ee.FeatureCollection([ee.Feature(aoi)]), aoi_id, "orbitalscout_aoi_asset"),
        (fields, fields_id, "orbitalscout_fields_asset"),
    ):
        task = ee.batch.Export.table.toAsset(
            collection=collection, description=name, assetId=asset_id
        )
        task.start()
        print(f"  {name}: {task.status()['state']} -> {asset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
