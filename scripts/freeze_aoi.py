"""Freeze the AOI and the field ordering into the repository.

Run once, already run. Every later step reads `orbitalscout/frozen/` rather
than recomputing, because build_aoi derives the polygon from live Sentinel-2
footprints and Earth Engine reprocesses scenes. A footprint that shifts at the
coverage margin moves a field in or out, and because field numbering is dense
and sorted, that renumbers every field after it. Architecture note Decision 4.

Frozen to files rather than Earth Engine assets so the freeze is version
controlled: anyone who clones gets the identical AOI and numbering without
needing access to one account's assets, and a change shows up in a diff.

Re-running after any export would renumber fields and invalidate every raster
already produced, so this refuses to overwrite.

Run:
    python scripts/freeze_aoi.py --project YOUR_EE_PROJECT
"""

import argparse
import csv
import json
import os
import sys

import ee

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config  # noqa: E402
from orbitalscout.ingest import gee  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=os.environ.get("ORBITALSCOUT_EE_PROJECT"))
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing freeze. Renumbers fields.")
    args = parser.parse_args()
    if not args.project:
        parser.error("pass --project or set ORBITALSCOUT_EE_PROJECT")

    aoi_path = gee.FROZEN / "aoi.geojson"
    fields_path = gee.FROZEN / "fields.csv"
    existing = [p for p in (aoi_path, fields_path) if p.exists()]
    if existing and not args.force:
        raise SystemExit(
            "already frozen:\n  " + "\n  ".join(str(p) for p in existing) +
            "\nRefusing to overwrite. Every raster exported so far is numbered "
            "against this field set, and re-freezing would renumber it."
        )

    ee.Initialize(project=args.project)
    gee.FROZEN.mkdir(parents=True, exist_ok=True)

    aoi = gee.build_aoi()
    with open(aoi_path, "w", encoding="utf-8") as handle:
        json.dump(aoi.getInfo(), handle, separators=(",", ":"))
    print(f"wrote {aoi_path}, {aoi.area(10).getInfo() / 1e6:.1f} km2")

    fields = gee.indexed_fields(gee.selected_fields(aoi))
    features = fields.select(
        ["field_idx", config.CSB_FIELD_ID], retainGeometry=False
    ).getInfo()["features"]
    pairs = sorted(
        (f["properties"]["field_idx"], f["properties"][config.CSB_FIELD_ID])
        for f in features
    )
    with open(fields_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field_idx", "csbid"])
        writer.writerows(pairs)
    print(f"wrote {fields_path}, {len(pairs)} fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
