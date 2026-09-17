"""Issue #7: export a field sample at native 10m for the zone-size comparison.

The sample
----------
The architecture note asked for a seeded random sample of about 50 fields. An
Earth Engine export is always a rectangle, so 50 fields scattered across the
county would mean a county-sized box at 10m, about 1.5 GB per season. The sample
is therefore one field chosen at random with the project seed, plus its 49
nearest neighbours by centroid: a compact block, just as reproducible, about a
twentieth of the size. The comparison concerns sensor noise and co-registration
jitter, neither of which is organised at county scale, so a compact block is a
fair sample of it. The deviation is recorded in RESULTS.md.

The metric, fixed here before any 10m data exists
--------------------------------------------------
For each zone and year: the mean within-field relative NDVI over the label
window, bins 8 to 11, built by the same baseline views as production. For each
zone: the standard deviation of that value across years, over zones with at
least MIN_PRIOR_YEARS years. Reported as the median across zones at 10m and at
30m over the same fields, with the ratio.

Prior expectation, recorded in issue #7 before measurement: 30m shows lower
year-over-year variation, because averaging nine pixels suppresses sensor noise
and roughly one pixel of co-registration jitter between passes.

Run:
    python scripts/zone_size_export.py --project YOUR_EE_PROJECT
"""

import argparse
import csv
import os
import random
import sys

import ee

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config  # noqa: E402
from orbitalscout.ingest import gee  # noqa: E402

SAMPLE_SIZE = 50
SAMPLE_FILE = gee.FROZEN / "zone_size_sample.csv"


def choose_sample():
    """Freeze the sample once; later runs read the file."""
    if SAMPLE_FILE.exists():
        with open(SAMPLE_FILE, newline="", encoding="utf-8") as handle:
            return [int(r["field_idx"]) for r in csv.DictReader(handle)]

    indices, _ = gee.frozen_field_order()
    seed_idx = random.Random(config.SAMPLE_SEED).choice(sorted(indices))
    fields = gee.frozen_fields()
    seed_centre = fields.filter(ee.Filter.eq("field_idx", seed_idx)).first().geometry().centroid(10)
    nearest = (
        fields.map(lambda f: f.set("d", f.geometry().centroid(10).distance(seed_centre, 10)))
        .sort("d")
        .limit(SAMPLE_SIZE)
    )
    chosen = sorted(int(i) for i in nearest.aggregate_array("field_idx").getInfo())
    with open(SAMPLE_FILE, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field_idx", "seed_field_idx"])
        writer.writerows([i, seed_idx] for i in chosen)
    print(f"froze {len(chosen)} fields around seed field {seed_idx} to {SAMPLE_FILE}")
    return chosen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=os.environ.get(config.EE_PROJECT_ENV))
    parser.add_argument("--smoke", action="store_true", help="check one season, queue nothing")
    args = parser.parse_args()
    if not args.project:
        parser.error("pass --project or set ORBITALSCOUT_EE_PROJECT")
    ee.Initialize(project=args.project)

    chosen = choose_sample()
    sample = gee.frozen_fields().filter(ee.Filter.inList("field_idx", ee.List(chosen)))
    region = sample.geometry().bounds(10)
    area_km2 = region.area(10).getInfo() / 1e6
    print(f"sample: {len(chosen)} fields, export box {area_km2:.1f} km2 at 10m")

    field_ids = gee.field_id_image(sample, already_indexed=True)
    if args.smoke:
        values, counts, dates = gee.season_cubes(2020, region, zone_size_m=config.NATIVE_SIZE_M)
        print(f"2020 at 10m: {len(dates)} dates, {len(values.bandNames().getInfo())} value bands, "
              f"{len(counts.bandNames().getInfo())} count bands")
        return 0

    gee.start_export(field_ids, "orbitalscout10_fieldid", region, scale=config.NATIVE_SIZE_M)
    for year in config.YEARS:
        values, counts, _ = gee.season_cubes(year, region, zone_size_m=config.NATIVE_SIZE_M)
        gee.start_export(values, f"orbitalscout10_values_{year}", region, scale=config.NATIVE_SIZE_M)
        gee.start_export(counts, f"orbitalscout10_counts_{year}", region, scale=config.NATIVE_SIZE_M)
        print(f"queued {year}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
