"""Step 0, gate G-0: how many clear observations does the AOI actually give?

Counts cloud-free Sentinel-2 observations per 10m cropland pixel, per season,
for Story County Iowa. If the median falls below MIN_MEDIAN_CLEAR_OBS the
design has to change before anything else is built, so this runs first.

Also reports the count per crop, because the baseline is crop-stratified
(SPEC Section 8) and a corn-soy rotation roughly halves the usable history
available to any one zone.

Run:
    python scripts/step0_observations.py --project YOUR_EE_PROJECT
"""

import argparse
import os
import sys

import ee
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orbitalscout import config  # noqa: E402


def county_geometry():
    """Story County boundary, from the TIGER county layer."""
    counties = ee.FeatureCollection("TIGER/2018/Counties")
    return counties.filter(ee.Filter.eq("GEOID", config.COUNTY_FIPS)).first().geometry()


def cropland_mask(year):
    """1 where that year's CDL says corn or soybean, masked elsewhere.

    Uses the actual year's CDL, not the prior year's. In-season deployment
    would have to use the prior year (CDL lands the following February), but
    this is a retrospective count and the real labels exist.
    """
    cdl = (
        ee.ImageCollection("USDA/NASS/CDL")
        .filter(ee.Filter.date(f"{year}-01-01", f"{year}-12-31"))
        .first()
        .select("cropland")
    )
    return cdl.remap(list(config.CROP_CDL_CODES), [1] * len(config.CROP_CDL_CODES), 0).selfMask()


def clear_observation_count(year, aoi):
    """Per-pixel count of clear Sentinel-2 observations in one season.

    Cloud Score+ is joined to the S2 scenes by system:index via linkCollection,
    which is the documented pairing and avoids a second definition of "clear".
    """
    start = ee.Date.fromYMD(year, *config.SEASON_START)
    end = ee.Date.fromYMD(year, *config.SEASON_END)

    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start, end)
        .linkCollection(
            ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"),
            [config.CLEAR_BAND],
        )
    )

    is_clear = s2.map(
        lambda img: img.select(config.CLEAR_BAND)
        .gte(config.CLEAR_THRESHOLD)
        .rename("clear")
        .copyProperties(img, ["system:time_start"])
    )

    # Count acquisition DATES, not scenes. One date can produce more than one
    # scene where footprints overlap, and counting scenes would credit a pixel
    # with two observations it did not get.
    dates = (
        s2.aggregate_array("system:time_start")
        .map(lambda t: ee.Date(t).format("YYYY-MM-dd"))
        .distinct()
    )

    def clear_on_date(date_str):
        day = ee.Date.parse("YYYY-MM-dd", ee.String(date_str))
        return (
            ee.ImageCollection(is_clear)
            .filterDate(day, day.advance(1, "day"))
            .max()
            .unmask(0)
        )

    per_date = ee.ImageCollection(dates.map(clear_on_date))
    return per_date.sum().rename("n_clear"), dates.size()


def orbit_overlap_fraction(year, aoi):
    """Fraction of the AOI seen by more than one relative orbit.

    Story County straddles two orbits, one of which clips it. Pixels under
    both get roughly twice the observations of pixels under one, which is a
    spatial confound rather than an agronomic signal.
    """
    start = ee.Date.fromYMD(year, *config.SEASON_START)
    end = ee.Date.fromYMD(year, *config.SEASON_END)
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi).filterDate(start, end)

    orbits = s2.aggregate_array("SENSING_ORBIT_NUMBER").distinct()

    def coverage(orbit):
        scenes = s2.filter(ee.Filter.eq("SENSING_ORBIT_NUMBER", orbit))
        return ee.Image(1).clip(scenes.geometry()).unmask(0)

    n_orbits = ee.ImageCollection(orbits.map(coverage)).sum()
    frac = n_orbits.gte(2).reduceRegion(
        reducer=ee.Reducer.mean(), geometry=aoi, scale=100, maxPixels=int(1e9)
    )
    return frac.values().get(0)


def sample_counts(count_image, aoi, crop_mask):
    """Pull a sample of per-pixel counts at native 10m resolution."""
    sampled = count_image.updateMask(crop_mask).sample(
        region=aoi,
        scale=10,
        numPixels=config.SAMPLE_PIXELS,
        seed=config.SAMPLE_SEED,
        dropNulls=True,
    )
    return np.array(sampled.aggregate_array("n_clear").getInfo(), dtype=float)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=os.environ.get("ORBITALSCOUT_EE_PROJECT"))
    args = parser.parse_args()
    if not args.project:
        parser.error("pass --project or set ORBITALSCOUT_EE_PROJECT")

    ee.Initialize(project=args.project)
    aoi = county_geometry()

    print(f"AOI: county FIPS {config.COUNTY_FIPS}")
    print(f"Clear = Cloud Score+ '{config.CLEAR_BAND}' >= {config.CLEAR_THRESHOLD}")
    print(f"Season: {config.SEASON_START} to {config.SEASON_END}\n")
    print(
        f"{'year':>6} {'dates':>6} {'p10':>5} {'p25':>5} {'median':>7} "
        f"{'p75':>5} {'p90':>5} {'2+orbit':>8}"
    )
    print("-" * 56)

    medians = {}
    for year in config.YEARS:
        try:
            count_image, n_scenes = clear_observation_count(year, aoi)
            counts = sample_counts(count_image, aoi, cropland_mask(year))
        except Exception as exc:  # noqa: BLE001
            print(f"{year:>6}  skipped: {str(exc)[:60]}")
            continue

        if counts.size == 0:
            print(f"{year:>6}  no cropland pixels sampled")
            continue

        p10, p25, p50, p75, p90 = np.percentile(counts, [10, 25, 50, 75, 90])
        medians[year] = p50
        overlap = float(ee.Number(orbit_overlap_fraction(year, aoi)).getInfo())
        print(
            f"{year:>6} {n_scenes.getInfo():>6} {p10:>5.0f} {p25:>5.0f} "
            f"{p50:>7.0f} {p75:>5.0f} {p90:>5.0f} {overlap * 100:>7.0f}%"
        )

    if not medians:
        print("\nNo years measured. G-0 not evaluated.")
        return 1

    worst_year = min(medians, key=medians.get)
    overall = np.median(list(medians.values()))
    print(f"\nMedian across years: {overall:.0f}")
    print(f"Worst year: {worst_year} at {medians[worst_year]:.0f}")
    print(f"G-0 threshold: {config.MIN_MEDIAN_CLEAR_OBS}")

    if overall < config.MIN_MEDIAN_CLEAR_OBS:
        print("\nG-0 FAILS. Stop and change the design before Step 1.")
        return 1
    print("\nG-0 passes on the median. Check the worst year before proceeding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
