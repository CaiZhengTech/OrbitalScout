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
