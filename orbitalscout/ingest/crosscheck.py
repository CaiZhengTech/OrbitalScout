"""Independent check of the exported values against Planetary Computer.

Every other verification in this project is structural: row counts, nodata
handling, quantile ranges, agreement with the Step 0 gate. None of them can
tell whether NDVI 0.611 at a given zone on a given date is the number an
independent source would produce from the same satellite pass. This does.

Not a unit test. It needs network access and two accounts, so SPEC Section 14
keeps it out of CI and runs it by hand.

TOLERANCE IS FIXED BEFORE THE RUN. Earth Engine and Planetary Computer both
serve Sentinel-2 L2A but not necessarily the same processing baseline, and the
reprojection from UTM to EPSG:5070 is resampled differently on each side, so
exact equality is not the expectation. The pass condition is stated here, in
code, before any comparison happens, so it cannot be widened after seeing the
result.
"""

import numpy as np

# Median absolute difference in index units across the sampled zone-dates.
# 0.02 on a scale from -1 to 1. Chosen as roughly the scale of resampling and
# baseline differences, and well below the anomaly sizes the project ranks on.
MEDIAN_TOLERANCE = 0.02

# No single zone-date may differ by more than this. Catches a systematic
# misalignment that a median would absorb.
MAX_TOLERANCE = 0.10


def compare(earth_engine_values, planetary_values):
    """Compare two aligned arrays of index values.

    Returns a dict of measured statistics and whether the fixed tolerances
    hold. Reports rather than asserts, so a failure is inspected.
    """
    ee_vals = np.asarray(earth_engine_values, dtype="float64")
    pc_vals = np.asarray(planetary_values, dtype="float64")
    if ee_vals.shape != pc_vals.shape:
        raise ValueError(f"shape mismatch: {ee_vals.shape} vs {pc_vals.shape}")

    usable = ~np.isnan(ee_vals) & ~np.isnan(pc_vals)
    if not usable.any():
        raise ValueError("no overlapping observations to compare")

    difference = np.abs(ee_vals[usable] - pc_vals[usable])
    median = float(np.median(difference))
    worst = float(difference.max())
    return {
        "n_compared": int(usable.sum()),
        "n_requested": int(ee_vals.size),
        "median_abs_diff": median,
        "max_abs_diff": worst,
        "p95_abs_diff": float(np.percentile(difference, 95)),
        "correlation": float(np.corrcoef(ee_vals[usable], pc_vals[usable])[0, 1]),
        "median_ok": median <= MEDIAN_TOLERANCE,
        "max_ok": worst <= MAX_TOLERANCE,
        "passed": median <= MEDIAN_TOLERANCE and worst <= MAX_TOLERANCE,
    }
