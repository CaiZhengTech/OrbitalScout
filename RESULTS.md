# Results

Measured output only. Every number here came from a script in this repository and can be reproduced by running it. Anything not yet measured is marked `[TBD]` rather than estimated.

AOI: Story County, Iowa (FIPS 19169), 1483.5 km2.
Clear observation: Cloud Score+ `cs` band >= 0.60, the single definition used everywhere.
Season window: 1 May to 30 September.

---

## Step 0, gate G-0: clear observation count

Run: `python scripts/step0_observations.py --project <EE_PROJECT>` on 2026-09-14.

Counts are distinct acquisition dates on which a 10m pixel was clear, sampled over pixels that the same year's CDL labels corn or soybean. 10,000 pixels requested per year, seed 42.

| year | acquisition dates | p10 | p25 | median | p75 | p90 | AOI under 2+ orbits |
|---|---|---|---|---|---|---|---|
| 2017 | 26 | 5 | 6 | 11 | 13 | 14 | 65% |
| 2018 | 58 | 10 | 12 | 22 | 25 | 26 | 64% |
| 2019 | 61 | 8 | 8 | 19 | 21 | 23 | 64% |
| 2020 | 61 | 12 | 13 | 25 | 27 | 29 | 65% |
| 2021 | 60 | 16 | 17 | 32 | 35 | 36 | 64% |
| 2022 | 61 | 12 | 13 | 25 | 28 | 29 | 64% |
| 2023 | 61 | 17 | 18 | 30 | 33 | 34 | 64% |
| 2024 | 60 | 17 | 18 | 29 | 32 | 34 | 65% |
| 2025 | 67 | 15 | 17 | 24 | 29 | 31 | 64% |

Median across years: 25. Worst year: 2017, median 11. Threshold: 6.

**G-0 passes.** The median exceeds the threshold by roughly four times in every year, and the tenth percentile exceeds it in every year except 2017.

### Finding 1: 2017 is not comparable to the other seasons

2017 yielded 26 acquisition dates against roughly 60 in every subsequent year, and its tenth percentile of 5 is the only value in the table below the G-0 threshold. Sentinel-2B did not reach operational service until mid-2017, so most of that season was single-satellite.

2017 is excluded. The usable record is 2018 to 2025, eight seasons.

### Finding 2: observation density varies about twofold across a hard spatial boundary

Two Sentinel-2 relative orbits cover the AOI. Orbit 69 covers 100% of the county; orbit 112 covers 65% of it. Measured for 2020: 32 scenes from orbit 69 and 30 from orbit 112.

Consistently across all nine years, 64% to 65% of the AOI falls under both orbits and the remainder under one. This produces the bimodal distribution visible in the table: for 2020, the tenth and twenty-fifth percentiles sit at 12 and 13 observations while the median and seventy-fifth sit at 25 and 27.

The boundary is drawn by orbit geometry and has no agronomic meaning. Zones on the thin side receive roughly half the observations, which gives them noisier baselines, shorter achievable persistence runs for S5, and less chance of catching a short-lived anomaly. Pooling the two regions would let a satellite artifact appear as a spatial pattern in crop stress.

**Decided 2026-09-14: the AOI is restricted to the doubly covered region**, that is Story County intersected with the footprint of relative orbit 112. Carrying coverage as a per-zone covariate was rejected because the thin region is a contiguous stripe rather than a random sample, so the confound would be spatial and would attach to every downstream comparison. About a third of the fields are dropped. The excluded stripe is retained as an optional robustness experiment: does ranking quality degrade at half the observation density? See `DESIGN.md` D18.

### Finding 3: effective per-crop history is two to four seasons, not eight

Measured over 2018 to 2025 on 4,000 sampled pixels at 30m, of which 2,892 were corn or soybean in at least six of the eight years.

| quantity | p10 | median | p90 |
|---|---|---|---|
| corn seasons per pixel | 4 | 4 | 6 |
| soybean seasons per pixel | 2 | 4 | 4 |

Crop changes across 82% of consecutive year pairs, and 49.3% of pixels alternate in every single year. The rotation is strong but not universal.

Because the baseline may use only years strictly prior to the target year, and because SPEC Section 8 stratified the baseline by crop at the time this was measured, the depth actually available to a held-out year was lower than the totals above:

| test year | prior seasons | approximate seasons per crop |
|---|---|---|
| 2023 | 5 (2018 to 2022) | 2 to 3 |
| 2024 | 6 (2018 to 2023) | 3 |
| 2025 | 7 (2018 to 2024) | 3 to 4 |

This triggers open item 12 of `docs/reviews/2026-09-14-council-label-review.md`, which recorded in advance that a measured per-zone-crop count materially below four would put the per-zone baseline itself in question, not merely the per-zone standard deviation already rejected.

**Decided 2026-09-14: crop stratification is dropped in favour of a within-field relative baseline.** Crop is a property of the field-year, not of the zone, because Corn Belt fields rotate as whole units. Measuring each zone against its own field median in the same year cancels crop, weather, planting date and management together, so the baseline can pool every prior year and usable history returns to five to seven seasons. Formulas in `SPEC.md` Section 8; reasoning in `DESIGN.md` D17 and `docs/reviews/2026-09-14-baseline-depth-decision.md`.

A zone-by-crop interaction, where a zone's relative standing genuinely differs between corn and soybean years, is not cancelled by this. Soybean iron deficiency chlorosis on the calcareous soils of the Des Moines Lobe is a plausible local mechanism. It is handled as a candidate refinement admitted by measured lift, not by assumption, and the across-zone corn-versus-soybean correlation is reported from Step 2 as a diagnostic: `[TBD]`.

---

## Step 0, zone size

`[TBD]`. Moved into Step 1. The Earth Engine expression that exports the zone table can emit 10m and 30m at negligible extra cost, and the comparison should be made on the within-field relative quantity that finding 3 settled. Prior expectation, recorded so it can be checked against the result: 30m will show lower year-over-year variance for stable zones, because it averages down Sentinel-2 co-registration jitter of roughly one pixel between passes.

## Step 1: area of interest and field selection

Measured 2026-09-16 with `orbitalscout/ingest/gee.py`.

| quantity | value |
|---|---|
| County area | 1483.5 km2 |
| AOI after orbit restriction | **996.5 km2**, 67% of the county |
| CSB fields in the county | 6027 |
| Fields corn or soybean in >= 6 of 8 seasons | 5033 |
| Of those, inside the AOI (**selected**) | **3445** |
| Mean selected field size | 52.9 acres |

The AOI is the county intersected with the region where relative orbit 112 was present on at least 90% of that orbit's acquisitions across 2018 to 2025. At 67% it is slightly larger than the 64% to 65% two-orbit figure in finding 2, because the 90% threshold admits pixels near the swath edge that a strict all-acquisitions rule would drop.

Field selection is by the CSB `CDL2018` to `CDL2025` properties. **Correction to earlier documentation:** the community catalogue page lists these as `CROP18` to `CROP25`; confirmed against the asset on 2026-09-16, they are `CDL<year>`. The field identifier is `CSBID`, a 15-digit string, so a dense integer index is painted into the raster and the mapping exported alongside. The asset is served in EPSG:4326, not EPSG:5070 as SPEC Section 5 assumed for the shapefile distribution, so reprojection happens in the export.

### End-to-end check on one season before queuing the rest

2020, one zone inside a selected field, NDVI after masking and aggregation to 30m:

| date | NDVI | valid sub-pixels |
|---|---|---|
| 2020-07-03 | 0.611 | 9 of 9 |
| 2020-07-10 | 0.705 | 9 of 9 |
| 2020-07-28 | 0.871 | 9 of 9 |
| 2020-07-30 | 0.852 | 9 of 9 |

Four of the twelve July acquisition dates survived masking at this zone, consistent with the roughly 41% clear rate implied by the Step 0 counts. The values trace canopy closure through July rather than sitting at implausible extremes, and no masked date produced a zero.

Cube shape for 2020: 61 acquisition dates, 183 value bands (`<index>_<YYYYMMDD>`, three indices) and 61 count bands (`count_<YYYYMMDD>`, one per date because the mask is shared across indices).

### Round trip verified end to end on 2020

Export, download, melt and load run end to end. `data/orbitalscout.duckdb`:

| table | rows |
|---|---|
| `fields` | 3,445 |
| `zones` | 701,592 |
| `zone_obs` | 17,892,753 |

44 of the 61 acquisition dates produced at least one usable zone; the other 17 were cloudy across the whole AOI. Rows per date range from 21,641 to 627,827.

Index distributions are physically plausible. NDVI p1 to p99 spans 0.143 to 0.923, NDRE 0.093 to 0.815, NDWI minus 0.414 to 0.525. Three rows in 17.9 million sit at the degenerate limits of plus or minus one, which is what a normalised difference returns when one band reads zero; they are recorded, not clipped.

201 of the 3,445 selected fields ended up with no zones at all, because the 30m inward buffer consumes a narrow or small field entirely. 3,244 fields carry zones.

### Cross-check against Step 0

The database was built by a different code path from the Step 0 gate, so the two are an independent check on each other.

| statistic | Step 0, 10m pixels, whole county | Database, 30m zones, restricted AOI |
|---|---|---|
| median clear observations | 25 | 26 |
| p75 | 27 | 28 |
| p90 | 29 | 29 |
| p10 | 12 | 21 |
| overall clear fraction | 41.0% | 41.8% |

The upper quantiles and the overall clear fraction agree. The p10 deliberately does not: Step 0 measured the whole county including the single-orbit stripe, which is where its 12 came from, and the database covers only the doubly covered AOI. The disappearance of that tail is independent confirmation that the restriction in `DESIGN.md` D18 did what it was specified to do.

### Independent value check against Planetary Computer

Run 2026-09-17 with `scripts/run_crosscheck.py --zones 20`.

Every other verification in this project is structural: row counts, nodata handling, quantile ranges, agreement with the Step 0 gate. None of them can say whether a given NDVI is the number an independent source produces from the same satellite pass. This compares 20 zone-dates against Sentinel-2 L2A served by Microsoft Planetary Computer, read with rasterio directly from the COGs, so the only code shared with the Earth Engine path is the arithmetic of a normalised difference.

**Tolerances were fixed as constants in `orbitalscout/ingest/crosscheck.py` before the comparison ran**, so they could not be widened after seeing the result.

| statistic | measured | tolerance |
|---|---|---|
| median absolute difference | 0.0039 | 0.02 |
| 95th percentile absolute difference | 0.0273 | none set |
| maximum absolute difference | 0.0448 | 0.10 |
| correlation | 0.9985 | none set |

Passed. The residual difference is consistent with the two services resampling from UTM to EPSG:5070 differently, and is far below the anomaly magnitudes the project ranks on.

### Regression fixture cut from the real export

`tests/fixtures/` holds a 32x32 window of the 2020 export, about 20 KB, carrying all three of the markers a real file contains: valid cells, cells masked by cloud, and cells zero-filled outside the export region. `tests/test_real_fixture.py` pins the melted output at 1,192 rows across 596 zones and 2 dates, with an NDVI sum of 228.714.

It exists because four of the five defects below were invisible to synthetic fixtures by construction: those fixtures were written from the same mental model that produced the bug, and always declared a nodata value and used a single absent marker.

### Bugs found by running, that the review documents did not catch

Recorded because they are the argument for the build order, not incidental.

1. **Masked pixels written as zero.** Earth Engine writes masked pixels as 0 and omits the GeoTIFF nodata tag unless the export asks for one, so 51.7% of the first NDVI band was a literal zero and a masked read masked nothing. Fixed on the export side with a declared sentinel and on the read side by refusing any raster without a nodata tag.
2. **Two absent markers in one file.** Earth Engine fills the gap between the export region and the raster bounding box with 0 rather than the declared nodata, so 255,996 pixels carried a second, undeclared absent marker. Field indices start at 1, so a non-positive field id now means absent.
3. **Stale duplicate downloads.** Earth Engine writes a new Drive file per export rather than overwriting, so the corrected exports downloaded as the broken versions they were meant to replace. This masked the fix for finding 1. The fetcher now keeps the newest file of each name.
4. **Field numbering built twice.** The field raster and the lookup table were produced by separate Earth Engine calls over a collection with no guaranteed iteration order, which could have pointed every zone at the wrong field with nothing to raise on. Both now share one ordering, sorted by CSBID.
5. **The long intermediate did not fit in memory.** A season is 26.2 million rows in long form and about 3.1 GB in pandas, and the first round trip was killed by the OS. The cost was the shape: the long form stores the index name as a string on every row, duplicating the band name and tripling the row count. `melt` now streams one wide frame per date straight to Parquet, so peak memory is one date regardless of season count.

### All eight seasons ingested

| season | zone-date rows | dates with data | median NDVI |
|---|---|---|---|
| 2018 | 16,103,298 | 46 | 0.645 |
| 2019 | 13,570,387 | 42 | 0.790 |
| 2020 | 17,892,753 | 44 | 0.596 |
| 2021 | 22,983,655 | 48 | 0.590 |
| 2022 | 17,857,046 | 47 | 0.734 |
| 2023 | 21,324,419 | 50 | 0.703 |
| 2024 | 21,244,454 | 51 | 0.594 |
| 2025 | 18,596,800 | 59 | 0.641 |
| **total** | **149,572,812** | **387** | |

All 701,592 zones are present in every season, which is what the frozen field set guarantees.

Cloud drives a 1.7 times spread in usable observations between the worst season (2019, 13.6M rows) and the best (2021, 23.0M). Because a baseline uses only prior years, a held-out year backed by 2019 carries measurably less history than one backed by 2021. Recorded here so that a difference in baseline quality between test years is not later mistaken for a difference in signal.

Median NDVI by season ranges from 0.590 to 0.790. This is interannual variation in the growing season, not a defect, but it is also the reason the baseline is within-field relative: a whole-season shift of that size would otherwise be attributed to individual zones.

33 rows in 149.6 million sit at the degenerate limits of plus or minus one. No nulls in any index column.

**Storage.** 1.65 GB of Parquet and a 7.4 MB database, because `zone_obs` is a view over the Parquet rather than a copy of it. The database is 0.4% of the data it indexes.

## Step 2: phenology inputs

### Weather

Open-Meteo archive, daily 2m maximum and minimum temperature at the AOI centroid (42.0482 N, 93.5394 W), 2018 to 2025. 2,922 days, none missing. Frozen in `orbitalscout/frozen/weather_daily.csv` so the baseline rebuilds without network access and is unaffected by later reanalysis revisions.

As a sanity range only, corn GDD from a fixed 1 May origin to 30 September runs from 2,980 (2020) to 3,234 (2021). The baseline does not use a fixed origin.

### GDD origin: USDA NASS 50% planted date

Interpolated from NASS Crop Progress weekly cumulative percent planted, state of Iowa. Raw weekly series frozen in `orbitalscout/frozen/nass_planting_progress.csv` (165 rows), derived dates in `orbitalscout/frozen/planting_dates.csv`.

| year | corn | soybean |
|---|---|---|
| 2018 | 2018-05-08 | 2018-05-17 |
| 2019 | 2019-05-12 | **2019-06-04** |
| 2020 | 2020-04-27 | 2020-05-04 |
| 2021 | 2021-04-29 | 2021-05-04 |
| 2022 | 2022-05-13 | 2022-05-18 |
| 2023 | 2023-05-03 | 2023-05-07 |
| 2024 | 2024-05-07 | 2024-05-15 |
| 2025 | 2025-05-04 | 2025-05-07 |

Corn spans 16 days across the eight years and soybean spans 31. Soybean follows corn in every year. 2019 soybean is the record-late wet spring and is the case a fixed calendar origin would have handled worst: a 1 May start would have credited more than a month of pre-planting heat to that crop-year.

No week in any series was reported twice with conflicting values.

## Step 2 onward

`[TBD]`. Bin width coverage, the within-field baseline, and the 10m against 30m zone size comparison not yet measured.
