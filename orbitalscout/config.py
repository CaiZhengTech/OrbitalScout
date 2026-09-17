"""Single source of truth for AOI, years and thresholds. SPEC Section 11.

Everything that a later step might want to vary lives here, so that no value
is defined twice and no value is buried in a script.
"""

# Story County, Iowa. Roughly 85% corn and soybean with a stable rotation,
# which matters for gate G-4, and it sits in the 2020 derecho corridor that
# SPEC Section 10 wants as a qualitative case study.
COUNTY_FIPS = "19169"

# 2017 is excluded: Sentinel-2B was not operational for most of that season,
# so it yielded 26 acquisition dates against roughly 60 in every later year
# and its p10 clear count of 5 is the only value below the G-0 threshold.
# RESULTS.md finding 1.
YEARS = tuple(range(2018, 2026))

# Two relative orbits cover the county and orbit 112 clips it, so the region
# under both gets roughly twice the clear observations of the rest. The AOI is
# restricted to that region so an orbit boundary cannot masquerade as a spatial
# pattern in crop stress. RESULTS.md finding 2, DESIGN.md D18.
RESTRICTING_ORBIT = 112

# Loose calendar bounds on the growing season. Phenology bounds it properly
# at Step 2; here it only needs to exclude bare soil and winter.
SEASON_START = (5, 1)
SEASON_END = (9, 30)

# Cloud Score+ quality band. 'cs' scores each pixel 0 (occluded) to 1 (clear).
# 0.60 is the threshold Google documents as the balanced default. This is the
# ONE definition of "clear observation" in the project; SPEC Section 11 forbids
# any signal from reimplementing it, because S5 persistence would become
# meaningless if two definitions disagreed.
CLEAR_BAND = "cs"
CLEAR_THRESHOLD = 0.60

# CDL codes for the V1 crops. The full crop registry lands at Step 2; Step 0
# only needs to mask to cropland. Codes, never names, so that adding a crop
# stays a data change (SPEC Section 8).
CROP_CDL_CODES = (1, 5)  # 1 corn, 5 soybean

# Gate G-0. If the median clear-observation count per season falls below this,
# the design changes before anything else is built.
MIN_MEDIAN_CLEAR_OBS = 6

# Pixels sampled per year when estimating the count distribution. The count
# surface is spatially smooth, so this is far more than enough for a median.
SAMPLE_PIXELS = 10_000
SAMPLE_SEED = 42

# Earth Engine project, overridable per machine.
EE_PROJECT_ENV = "ORBITALSCOUT_EE_PROJECT"

# Batch exports land here in the user's Drive. Drive over a GCS bucket because
# this export runs once; reproducibility lives in the code, not in where the
# bytes were staged, and GCS would mean enabling billing for nothing.
DRIVE_FOLDER = "orbitalscout"

# The AOI and the selected field set are materialised once as Earth Engine
# assets, and every later step reads the assets rather than recomputing.
# Recomputing would re-derive the AOI from live Sentinel-2 footprints, and a
# footprint that shifts at the 90% coverage margin moves a field in or out.
# Because field numbering is dense and sorted, that renumbers every field after
# it, so a raster exported today would silently disagree with a lookup table
# exported tomorrow while each stayed internally consistent.
AOI_ASSET = "projects/{project}/assets/orbitalscout_aoi"
FIELDS_ASSET = "projects/{project}/assets/orbitalscout_fields"

# A pixel is in the AOI if the restricting orbit covered it in at least this
# fraction of that orbit's acquisitions. Absorbs small footprint variation.
ORBIT_COVERAGE_MIN = 0.90

# CSB carries one CDL code per field per year. Confirmed against the asset on
# 2026-09-16: the properties are CDL2018..CDL2025, not the CROP18..CROP25 that
# the community catalogue page lists.
CSB_ASSET = "projects/nass-csb/assets/CSB1825_rev23/CSBIA1825"
CSB_FIELD_ID = "CSBID"
CSB_CROP_PROPERTY = "CDL{year}"
CSB_STATE_FIPS = "19"
CSB_COUNTY_FIPS = "169"

# A field is selected if it grew a registry crop in at least this many seasons.
MIN_CROP_YEARS = 6

# Inward buffer, one zone width, so no zone straddles a field edge.
FIELD_BUFFER_M = -30

# Sentinel-2 bands behind each index. Red edge (B5) and SWIR (B11) are 20m
# native, which is the other reason zones are 30m and not 10m.
INDICES = {
    "ndvi": ("B8", "B4"),
    "ndre": ("B8", "B5"),
    "ndwi": ("B8", "B11"),  # Gao form: vegetation water content
}

# A 30m zone needs this many of its nine 10m sub-pixels valid on a date.
MIN_SUBPIXELS = 5
ZONE_SIZE_M = 30
NATIVE_SIZE_M = 10

# Written into every exported raster for masked pixels, and declared in the
# GeoTIFF nodata tag. Earth Engine writes masked pixels as 0 and omits the tag
# unless asked, which would make a cloudy day indistinguishable from a reading
# of zero greenness. Outside the range of any scaled index or sub-pixel count.
NODATA = -32768
