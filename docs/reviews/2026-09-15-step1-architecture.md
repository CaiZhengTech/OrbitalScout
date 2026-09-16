# Step 1 architecture, 2026-09-15

Made before any Step 1 code, after PR #8. Settles the ingestion shape so that implementation is mechanical. Three of these decisions are forced by arithmetic that had not been done; one is enabled by a fact that was not known.

## Decision 1. Zones are 30m over the full AOI; 10m only on a field sample

The arithmetic. AOI after orbit restriction is about 950 km2, roughly 85% cropland, so about 800 km2 of zones. At 10m that is about 8 million zones; times about 25 clear observations per season, times 8 seasons, is about **1.6 billion zone-date rows**, on the order of 25 GB before indices. At 30m it is about 890 thousand zones and about 180 million rows, around 3 GB.

SPEC Section 12 promised "single-digit GB, fits on a laptop." That was only ever true at 30m. The claim and the 10m zone size were inconsistent from the first draft and nobody multiplied them out. CLAUDE.md's Step 1 instruction to "export the zone table at both 10m and 30m" is therefore wrong for the full AOI and is corrected.

Two further reasons 30m is the right full-AOI grid, independent of volume:

- Red edge (B5) and SWIR (B11) are 20m native on Sentinel-2. A 10m zone for NDRE or NDWI was always an interpolation. 30m is the first grid at which all three indices are at or above native resolution.
- Co-registration jitter of about one pixel between passes, already recorded as the prior expectation in issue #7.

The 10m versus 30m comparison in #7 still happens, on a seeded random sample of about 50 CSB fields inside the AOI, exported at both resolutions. That is enough to measure year-over-year variance of stable zones and is a few thousand zones, not eight million.

## Decision 2. CSB comes from the Earth Engine community asset, not from a download

`projects/nass-csb/assets/CSB1825_rev23/CSBIA1825`, public domain, 2018 to 2025 window, updated 2026-08-30. Properties include a field identifier and `CDL2018` through `CDL2025`, one CDL code per field per year.

This removes the GeoParquet download, the local filter, the asset upload and the local spatial join that D15 had left implicit. Field membership, the inward buffer, and the per-field-year crop label all happen inside Earth Engine. D15 now holds completely: masking, reprojection, aggregation and field assignment are one expression.

Consequences:

- **The CDL raster is not used in Step 1.** Zone crop is the field's `CDL<year>` value. Under D17 the crop is a field-year property, and CSB assigns it at exactly that level, so pixel-level CDL disagreement inside a field is CDL noise rather than information. CDL is retained only as the source of the G-4 prior-year mismatch rate, which is now computed from the `CDL<year>` columns directly.
- **D17 is strengthened.** "Corn Belt fields rotate as whole units" was stated as an agronomic assumption. For CSB polygons it is definitional. Amend D17 to say so.
- Field selection: CSB fields intersecting the AOI whose `CDL<year>` is in the crop registry codes for at least six of the eight years. The threshold is a config value and its effect on field count is reported.
- Inward buffer is one zone width, 30m, applied to the polygon before it is painted to the zone grid, so no 30m zone straddles a field edge.

The exact name of the field identifier property is confirmed at implementation with `.first().propertyNames()`; the catalogue page abbreviates it.

## Decision 3. Export shape is a per-season data cube, melted locally

For each season and each index, one Earth Engine image export: 30m, EPSG:5070, one band per acquisition date, values scaled by 10000 and stored as int16, masked where not clear or not inside a selected field. A companion single-band image carries `field_id` painted from the buffered CSB polygons. Band names encode the acquisition date.

Local code reads each cube, melts it to a long table (`zone_id, field_id, year, date, index, value, n_valid`), and writes Parquet for DuckDB. The melt is a reshape. It contains no masking, no reprojection, no aggregation and no thresholds. A masked pixel becomes an absent row, never a zero.

**Rejected: table export via `sample()` on the full AOI.** About 890 thousand points with 60 or more properties each per index-season is where Earth Engine batch exports start hitting memory limits, and the result is a CSV several times larger than the equivalent int16 GeoTIFF. Image export is the path Earth Engine is most robust on. The cost is one local raster read, which walks back D15's wording "local code starts at DuckDB" to "local code starts at a reshape, then DuckDB." That is an honest one-sentence amendment, not a design reversal.

**Rejected: computing the within-field median in Earth Engine.** It would be another export per season and it belongs to Step 2. In DuckDB it is one window function over `field_id, date`.

Index computation happens **before** aggregation to 30m, per 10m pixel, because a mean of ratios is not a ratio of means. Aggregation is `reduceResolution` with a mean reducer over the nine 10m sub-pixels, with a companion count; a 30m zone with fewer than a configured minimum of valid sub-pixels (default 5 of 9) is masked for that date. This is the SPEC Section 6 rule about minimum valid pixels, now with a concrete unit.

Indices, with bands: NDVI (B8, B4); NDRE (B8, B5); NDWI in the Gao form (B8, B11), which tracks vegetation water content, matching S3's stated purpose of catching water stress. Values are Sentinel-2 L2A surface reflectance from `COPERNICUS/S2_SR_HARMONIZED`.

## Decision 4. The AOI polygon is materialised once

A pixel is inside the AOI if it is inside Story County and was covered by relative orbit 112 in at least 90% of that orbit's acquisitions over 2018 to 2025. The 90% absorbs small footprint variation between scenes. The resulting geometry is stored once as an Earth Engine asset under the project, its area in km2 and its field count are recorded in `RESULTS.md`, and every later step reads the asset rather than recomputing it.

## Decision 5. Output contract for everything downstream

Three tables in DuckDB, normalised so the split tests at Step 4 are trivial to write:

- `fields`: `field_id`, `area_m2`, `crop_2018` through `crop_2025`.
- `zones`: `zone_id`, `field_id`, `x_5070`, `y_5070`. Zone identity is the 30m grid cell centre in EPSG:5070; `zone_id` is derived from it deterministically.
- `zone_obs`: `zone_id`, `year`, `date`, `ndvi`, `ndre`, `ndwi`, `n_valid`. One row per zone per clear acquisition date. Absent means masked.

Nothing downstream may read a raster or call Earth Engine. Everything downstream reads these three tables. This is the "single clean feature table" of SPEC Section 11 in normalised form.

## Tests written before the melt

Per CLAUDE.md, test what fails silently:

- A synthetic two-band cube with one masked pixel melts to a table with **no row** for that pixel-date, and no zero.
- `n_valid` below the minimum produces no row.
- The melt asserts the cube's CRS is EPSG:5070 and raises otherwise. It never reprojects.
- `zone_id` round-trips to and from `(x_5070, y_5070)`.

The cross-check against an independent Planetary Computer pull on a zone sample remains manual, network, and out of CI, as SPEC Section 14 already states.

## Documents this changes

SPEC Section 6 (zone size and minimum valid sub-pixels), Section 11 (module list: `gee.py` gains the cube export, `crosscheck.py` unchanged, a `melt.py` is added under `ingest/`), Section 12 (the single-digit-GB claim is now conditional on 30m and says so). DESIGN D15 (wording amended as above), D17 (CSB makes whole-field rotation definitional). CLAUDE.md Step 1. Issue #7 gets the field-sample method as a comment.
