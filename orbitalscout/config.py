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

# Windows excluded from baseline estimation, because the signal inside them is
# a different physical process from the one the baseline is meant to capture.
# Knowledge as data (D4): adding an event is adding a row, never a branch on a
# year. Applied to the feature baseline and the leave-one-year-out label
# baseline alike; observations are still ingested and still available to the
# qualitative case study in SPEC Section 10.
KNOWN_EVENTS = (
    # name, start (inclusive), end (inclusive), why
    ("derecho_2020", "2020-08-10", "2020-12-31",
     "Regional wind damage. Lodging is uneven inside a field, so within-field "
     "relativity does not cancel it, and 2020 sits in the baseline window of "
     "every held-out year."),
)

# Open-Meteo archive, daily 2m max and min temperature. One series at the AOI
# centroid rather than per field: the temperature field varies by a fraction of
# a degree across a 30 km AOI, and any field-to-field difference is a
# field-year constant that the within-field baseline cancels.
WEATHER_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# A field-date is used only if at least this share of the field's zones is
# clear. The field median is taken over visible zones and cloud is contiguous,
# so below half the field the "centre" describes a patch, not the field.
# Step 2 amendment, Decision 5.
MIN_FIELD_CLEAR_FRAC = 0.50

# Phenology bin width, chosen for stage resolution: four bins across emergence
# to canopy closure, where relative standing changes fastest. Step 2
# amendment, Decision 6, which retires the earlier coverage rule.
BIN_WIDTH_GDD = 200

# A baseline cell resting on fewer prior years than this is not labelled or
# ranked. Enforced where the baseline is consumed, not inside the baseline
# view, so the raw count stays inspectable. Decision 6.
MIN_PRIOR_YEARS = 3

# Growth-stage windows, as inclusive bin ranges at BIN_WIDTH_GDD. Anchored to
# Abendroth et al. 2011, Corn Growth and Development, ISU Extension PMR 1009,
# for a 2,700 GDD hybrid. Step 2 second amendment, Decision 7.
#   feature: emergence through VT, what an in-season scout can act on
#   gap:     R1 silking, the SPEC Section 10 temporal gap
#   label:   R2 through R5, grain fill. Senescence is left out because a low
#            reading there is confounded between stress and early maturity.
# The feature window must end before the gap and the label window start after
# it, so the feature never sees the label window. A test asserts this.
FEATURE_BINS = (0, 6)
GAP_BINS = (7, 7)
LABEL_BINS = (8, 11)

# A neighbourhood mean below this many of the eight surrounding cells is not a
# local expectation, it is one or two zones. Same floor and reasoning as
# MIN_PRIOR_YEARS. Step 5, Decision 15.
MIN_NEIGHBOURS = 3

# The primary and secondary labels are the bottom decile within field-year.
# Fixed by SPEC Section 10 before any data was pulled, which is what makes the
# base rate 10% by construction. It is 10% only in the limit: the positive
# count rounds up, so an eleven-zone field-year reaches 18.2%. Step 4,
# Decision 10.
LABEL_FRACTION = 0.10

# The year holdout rolls across the last three seasons, each evaluated
# separately and reported as a spread, so a year that happened to be easy
# cannot carry the result. SPEC Section 10.
HELD_OUT_YEARS = YEARS[-3:]

# The fixed absolute scouting budget, in zones, that SPEC Section 10 delegates
# to this file. A 30m zone is 0.222 acres, so 20 zones is 4.45 acres, roughly
# 9% of an average field-year. Derived from one hour of in-field time: stops at
# 2 to 3 minutes each, plus a nearest-neighbour walk between scattered stops in
# a 50 acre field at canopy walking pace, which lands at 15 to 20 zones. The top
# of that band is taken because precision@k falls as k grows, so rounding up
# makes the headline metric harder to pass. Step 4, Decision 9.
SCOUTING_BUDGET_ZONES = 20

# Every metric is reported at the absolute budget above and at these fractions
# of field area, for comparability with how precision@k is usually quoted.
# SPEC Section 10.
EVAL_FRACTIONS = (0.05, 0.10, 0.20)
