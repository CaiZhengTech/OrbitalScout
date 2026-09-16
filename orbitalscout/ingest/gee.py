"""The one Earth Engine expression: mask, index, reduce, export.

Everything that could be defined twice is defined here once. Cloud masking,
reprojection to EPSG:5070, and aggregation to 30m zones all happen inside a
single chain, so no signal downstream can reimplement them with a different
threshold. SPEC Section 11, DESIGN D15.

Export shape per `docs/reviews/2026-09-15-step1-architecture.md` Decision 3:
one value cube per season carrying every index, bands named `<index>_<YYYYMMDD>`,
plus one count cube named `count_<YYYYMMDD>`. The count is per date rather than
per index because the mask is shared, so all three indices see the same valid
sub-pixels.
"""

import ee

from .. import config


def county_geometry():
    """Story County boundary, from the TIGER county layer."""
    counties = ee.FeatureCollection("TIGER/2018/Counties")
    return counties.filter(ee.Filter.eq("GEOID", config.COUNTY_FIPS)).first().geometry()


def build_aoi():
    """County, restricted to where the clipping orbit reliably reaches.

    Two relative orbits cover the county and one of them clips it, leaving
    roughly a third of the county with half the observations of the rest along
    a boundary drawn by orbit geometry rather than agronomy. RESULTS.md finding
    2, DESIGN D18. A pixel qualifies when the restricting orbit covered it on at
    least ORBIT_COVERAGE_MIN of that orbit's acquisitions, which absorbs the
    small footprint variation between scenes.
    """
    county = county_geometry()
    scenes = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(county)
        .filterDate(f"{config.YEARS[0]}-01-01", f"{config.YEARS[-1]}-12-31")
        .filter(ee.Filter.eq("SENSING_ORBIT_NUMBER", config.RESTRICTING_ORBIT))
    )
    covered = scenes.map(lambda img: ee.Image(1).clip(img.geometry()).unmask(0))
    fraction = covered.mean()  # share of that orbit's passes covering each pixel
    return (
        fraction.gte(config.ORBIT_COVERAGE_MIN)
        .selfMask()
        .reduceToVectors(
            geometry=county, scale=100, maxPixels=int(1e9), geometryType="polygon"
        )
        .geometry()
    )


def selected_fields(aoi):
    """CSB fields inside the AOI that grew a registry crop often enough.

    CSB carries one CDL code per field per year, so the crop is assigned at the
    field-year level by construction. That is what makes the within-field
    relative baseline of D17 definitional here rather than assumed.
    """
    crop_codes = ee.List(list(config.CROP_CDL_CODES))
    properties = [config.CSB_CROP_PROPERTY.format(year=y) for y in config.YEARS]

    county_fields = ee.FeatureCollection(config.CSB_ASSET).filter(
        ee.Filter.And(
            ee.Filter.eq("STATEFIPS", config.CSB_STATE_FIPS),
            ee.Filter.eq("CNTYFIPS", config.CSB_COUNTY_FIPS),
        )
    ).filterBounds(aoi)

    def count_crop_years(feature):
        hits = ee.List(properties).map(
            lambda key: ee.Algorithms.If(
                crop_codes.contains(feature.get(ee.String(key))), 1, 0
            )
        )
        return feature.set("n_crop_years", ee.Number(hits.reduce(ee.Reducer.sum())))

    return county_fields.map(count_crop_years).filter(
        ee.Filter.gte("n_crop_years", config.MIN_CROP_YEARS)
    )


def field_id_image(fields):
    """Paint a dense integer field index, inward-buffered by one zone width.

    The buffer is applied before painting so that no 30m zone straddles a field
    edge and mixes two fields' pixels. CSBID is a 15-digit string, so a dense
    index is painted instead and the mapping is exported alongside.
    """
    indexed = ee.FeatureCollection(
        fields.toList(fields.size()).map(
            lambda f: ee.Feature(f).buffer(config.FIELD_BUFFER_M)
        )
    )
    with_index = ee.FeatureCollection(
        indexed.toList(indexed.size()).zip(
            ee.List.sequence(1, indexed.size())
        ).map(lambda pair: ee.Feature(ee.List(pair).get(0))
              .set("field_idx", ee.List(pair).get(1)))
    )
    return with_index.reduceToImage(["field_idx"], ee.Reducer.first()).rename("field_id")


def _masked_indices(image):
    """Clear-masked index bands for one scene, at native 10m.

    Indices are computed per 10m pixel before any aggregation, because a mean
    of ratios is not a ratio of means.
    """
    clear = image.select(config.CLEAR_BAND).gte(config.CLEAR_THRESHOLD)
    bands = [
        image.normalizedDifference([near, far]).rename(name)
        for name, (near, far) in config.INDICES.items()
    ]
    return ee.Image.cat(bands).updateMask(clear)


def season_cubes(year, aoi):
    """Value cube and count cube for one season, aggregated to 30m.

    Returns (value_image, count_image, dates). Values are scaled by 10000 and
    stored as int16 so the export is a quarter the size of float32 and still
    resolves an index to four decimal places.
    """
    start = ee.Date.fromYMD(year, *config.SEASON_START)
    end = ee.Date.fromYMD(year, *config.SEASON_END)

    scenes = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start, end)
        .linkCollection(
            ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"),
            [config.CLEAR_BAND],
        )
    )

    # Distinct acquisition dates, resolved once. Counting scenes instead would
    # credit a pixel with observations it did not get where footprints overlap.
    stamps = (
        scenes.aggregate_array("system:time_start")
        .map(lambda t: ee.Date(t).format("YYYYMMdd"))
        .distinct()
        .sort()
    )
    dates = stamps.getInfo()

    value_bands, count_bands = [], []
    for stamp in dates:
        day = ee.Date.parse("YYYYMMdd", stamp)
        daily = scenes.filterDate(day, day.advance(1, "day"))
        native = (
            ee.ImageCollection(daily.map(_masked_indices))
            .mosaic()
            .reproject(crs="EPSG:5070", scale=config.NATIVE_SIZE_M)
        )
        aggregated = (
            native.reduceResolution(
                reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
                maxPixels=16,
            )
            .reproject(crs="EPSG:5070", scale=config.ZONE_SIZE_M)
        )
        enough = aggregated.select("ndvi_count").gte(config.MIN_SUBPIXELS)

        for name in config.INDICES:
            value_bands.append(
                aggregated.select(f"{name}_mean")
                .multiply(10000).round().int16()
                .updateMask(enough)
                .rename(f"{name}_{stamp}")
            )
        count_bands.append(
            aggregated.select("ndvi_count").int16()
            .updateMask(enough)
            .rename(f"count_{stamp}")
        )

    return ee.Image.cat(value_bands), ee.Image.cat(count_bands), dates


def start_export(image, description, aoi):
    """Queue one batch export to Drive. Returns the task, already started."""
    task = ee.batch.Export.image.toDrive(
        image=image.clip(aoi),
        description=description,
        folder=config.DRIVE_FOLDER,
        fileNamePrefix=description,
        region=aoi,
        scale=config.ZONE_SIZE_M,
        crs="EPSG:5070",
        maxPixels=int(1e10),
        fileFormat="GeoTIFF",
    )
    task.start()
    return task
