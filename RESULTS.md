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

### Parameter evidence: cloud threshold and bin width

Run with `python scripts/step2_measure.py` on 2026-09-17. Coverage uses a deterministic 5% sample of zones (hash of zone id), 34,973 zones and 7,051,748 observations; clear fraction is always computed over every zone in a field.

**Do partially clouded field-dates read differently?** NDVI on the date minus the same field's NDVI on fully clear (99% or more) dates at the same growth stage, same year. Stage bucket of 200 GDD, used for this diagnostic only.

| field clear | observations | median difference | p25 | p75 |
|---|---|---|---|---|
| 0 to 10% | 15,045 | -0.0104 | -0.0607 | 0.0268 |
| 10 to 25% | 40,284 | -0.0046 | -0.0477 | 0.0300 |
| 25 to 50% | 109,179 | 0.0004 | -0.0389 | 0.0345 |
| 50 to 75% | 187,169 | 0.0020 | -0.0349 | 0.0359 |
| 75 to 90% | 205,108 | 0.0020 | -0.0346 | 0.0356 |
| 90 to 99% | 278,814 | 0.0030 | -0.0332 | 0.0373 |
| 99 to 100% | 5,868,151 | 0.0013 | -0.0247 | 0.0242 |

Above 25% clear the median difference is indistinguishable from zero. Below 25% there is a small low bias, largest under 10%, consistent with missed cloud edge or haze. The narrower spread in the fully clear band is partly an artifact: that band is compared against a reference it contributes to.

**Bin coverage**, share of zone-year-bins holding at least one observation, over every bin from planting to 30 September:

| width (GDD) | no threshold | clear >= 50% | clear >= 90% | clear >= 99% |
|---|---|---|---|---|
| 150 | 74.2% | 72.8% | 69.3% | 66.5% |
| 200 | 83.6% | 82.4% | 79.4% | 76.9% |
| 250 | 88.4% | 87.4% | 84.6% | 82.4% |
| 300 | 91.1% | 90.3% | 88.1% | 86.1% |

**The rule fixed in SPEC Section 8 before binning, the narrowest width reaching 90%, selects 300 GDD, and only at a cloud threshold of 50% or below. Under stricter thresholds no candidate reaches 90%.**

**Where the shortfall sits**, at 200 GDD with no threshold:

| bin | GDD | coverage |
|---|---|---|
| 0 | 0 to 200 | 92.6% |
| 1 | 200 to 400 | 88.4% |
| 2 | 400 to 600 | 79.2% |
| 3 | 600 to 800 | 77.0% |
| 4 | 800 to 1000 | 84.9% |
| 5 | 1000 to 1200 | 80.9% |
| 6 | 1200 to 1400 | 92.2% |
| 7 | 1400 to 1600 | 89.4% |
| 8 | 1600 to 1800 | 84.3% |
| 9 | 1800 to 2000 | 80.0% |
| 10 | 2000 to 2200 | 91.8% |
| 11 | 2200 to 2400 | 84.5% |
| 12 | 2400 to 2600 | 84.3% |
| 13 to 16 | 2600 and above | partial last bin for some crop-years |

Excluding bins that are ever a partial last bin raises coverage only from 83.6% to 85.3%. The shortfall is therefore genuine sparsity rather than a counting artifact at the season edges, and it is concentrated at 400 to 800 GDD, late May into June, which is Iowa's cloudiest part of the season. The bin immediately after planting is well observed at 92.6%.

**Neither parameter has been chosen.** The pre-stated coverage rule points at the width that the Step 2 decision record named as too coarse to resolve growth stages, so this goes back for an explicit decision rather than a quiet relaxation of the rule.

### Parameters chosen

Cloud threshold 50%, bin width 200 GDD, prior-year floor 3. Reasoning in `docs/reviews/2026-09-17-step2-decisions.md`, amendment Decisions 5 and 6.

### Baseline built on real data

Run with `python scripts/build_baseline.py` on 2026-09-17. Field medians computed once over all zones (725,484 field-dates), then the windowed baseline over ten deterministic chunks of zones reusing them. **71,345,419 zone-year-bin cells**, about 4.2 GB of Parquet in `data/baseline/`.

### Reporting owed by Step 2

**1. Bin coverage the retired rule would have scored.** At 200 GDD and a 50% clear threshold: **82.4%**, from the 5% zone sample in `scripts/step2_measure.py`. Below the retired rule's 90%, as recorded when that rule was retired.

**2. Prior-year support in the held-out years, and the gate.**

| year | cells | 0 | 1 | 2 | 3 | 4 | 5+ | excluded by floor of 3 |
|---|---|---|---|---|---|---|---|---|
| 2023 | 9,805,464 | 0.2% | 1.6% | 10.1% | 28.1% | 36.0% | 24.0% | **12.0%** |
| 2024 | 9,729,563 | 0.0% | 0.3% | 1.9% | 11.5% | 28.8% | 57.5% | 2.2% |
| 2025 | 8,745,086 | 0.0% | 0.0% | 0.2% | 1.8% | 11.0% | 86.9% | 0.2% |

Excluded share by year and bin:

| bin | GDD | 2023 | 2024 | 2025 |
|---|---|---|---|---|
| 0 | 0 to 200 | 1.0% | 0.2% | 0.0% |
| 1 | 200 to 400 | 7.5% | 3.4% | 0.3% |
| 2 | 400 to 600 | 6.8% | 1.1% | 0.0% |
| 3 | 600 to 800 | 0.5% | 0.2% | 0.0% |
| 4 | 800 to 1000 | 0.9% | 0.0% | 0.0% |
| 5 | 1000 to 1200 | 7.2% | 4.2% | 0.3% |
| 6 | 1200 to 1400 | 0.1% | 0.0% | 0.0% |
| 7 | 1400 to 1600 | 1.0% | 0.0% | 0.0% |
| 8 | 1600 to 1800 | 8.5% | 2.7% | 0.1% |
| 9 | 1800 to 2000 | 11.7% | 4.6% | 1.5% |
| 10 | 2000 to 2200 | 0.1% | 1.0% | 0.1% |
| 11 | 2200 to 2400 | **31.1%** | 4.1% | 0.1% |
| 12 | 2400 to 2600 | **30.4%** | 1.0% | 0.0% |
| 13 | 2600 to 2800 | **54.9%** | 8.5% | 3.4% |
| 14 | 2800 to 3000 | 4.4% | 0.7% | 0.0% |
| 15 | 3000 to 3200 | **100.0%** (68,908 cells) | none | none |

**The gate tripped.** The floor was allowed to exclude at most a fifth of cells anywhere. It exceeds that in four places, all in 2023 and all late season: bins 11, 12, 13 and 15. Items 3 to 5 of the reporting owed were not run, because the gate is a stop condition.

**Cause, measured from the weather and planting tables rather than inferred.** Two earlier decisions interact with 2023 having only five prior years.

The derecho exclusion (Decision 2) removes 2020 from exactly the late bins. 2020 corn entered bin 11 on 15 August and soybean on 19 August, both after the 10 August storm. For 2023 that leaves at most four usable prior years in bins 11 to 14, so a floor of three requires three of four to be observed, and late-season cloud misses enough to exclude roughly a third of cells. 2024 and 2025 keep five and six usable prior years in the same bins and pass.

| bin | GDD | corn prior years usable for 2023 | soybean prior years usable for 2023 |
|---|---|---|---|
| 9 | 1800 to 2000 | 5 of 5 | 5 of 5 |
| 10 | 2000 to 2200 | 5 of 5 | 4 of 5 |
| 11 to 13 | 2200 to 2800 | 4 of 5 | 4 of 5 |
| 14 | 2800 to 3000 | 4 of 5 | 3 of 5 |
| 15 | 3000 to 3200 | 2 of 5 | 1 of 5 |

Bin 15 cannot pass by construction: only one or two of the prior crop-years accumulate 3,000 GDD before 30 September, so a floor of three is unreachable regardless of cloud. It is a season-edge artifact, 1% of 2023's cells.

**Why this is consequential rather than cosmetic.** The primary label is the end-of-season residual, which lives in the late bins. For the 2023 holdout, the cells the label depends on are the ones with the thinnest support. This is a decision for the evaluation, not a baseline bug, and it is recorded here before any label or evaluation number exists.

### Label, feature, and the re-specified gate

Following the second Step 2 amendment (Decisions 7 to 9): the label is the mean NDVI residual over supported cells in bins 8 to 11 (R2 to R5, grain fill) against the leave-one-year-out baseline; the feature is the NDVI residual in the latest supported cell in bins 0 to 6 (emergence to VT) against the strictly prior baseline. Run with `python scripts/build_baseline.py --outcomes` on 2026-09-17.

The cell-level gate above measured an intermediate. Decision 9 re-specified it at the granularity of what it protects: in each held-out year, at most 20% of eligible zone-years may lack a label, and at most 20% may lack a feature. Written before the number existed.

| year | eligible zone-years | no label | no feature | ineligible (field grew another crop) |
|---|---|---|---|---|
| 2023 | 699,460 | 0.1% | 0.0% | 2,132 |
| 2024 | 696,733 | 0.0% | 0.0% | 4,859 |
| 2025 | 692,347 | 0.0% | 0.0% | 9,245 |

**Gate passed.**

Label cells used per labelled zone-year, out of a possible four:

| year | 1 cell | 2 cells | 3 cells | 4 cells |
|---|---|---|---|---|
| 2023 | 3.2% | 7.8% | 40.9% | 48.1% |
| 2024 | 0.2% | 1.7% | 18.2% | 80.0% |
| 2025 | 0.1% | 4.6% | 32.3% | 63.1% |

2023 remains the most thinly supported held-out year, as the cell-level result predicted, but 89% of its labels rest on three or four cells.

Bin the feature came from:

| year | bin 4 | bin 5 | bin 6 |
|---|---|---|---|
| 2023 | 0.0% | 0.0% | 100.0% |
| 2024 | 1.1% | 4.9% | 94.1% |
| 2025 | 0.0% | 0.0% | 100.0% |

**The rung 1 feature is in practice a late-vegetative snapshot**, taken at 1,200 to 1,400 GDD just before tassel, rather than an early-season reading. That follows from "latest supported cell" and is consistent with the design, but it bounds what the claim can be: the ranking uses the canopy's standing at the end of vegetative growth, not at emergence. It is also the baseline against which the Step 5 velocity signal, which uses earlier bins, must show added value.

### Diagnostics

Run with `python scripts/step2_diagnostics.py` on 2026-09-17. Reported, not gating.

**3. Derecho sensitivity.** Everything rebuilt with the known-event exclusion switched off, then compared.

| compared | cells or zone-years | mean abs diff | median | p90 | max |
|---|---|---|---|---|---|
| feature baseline cells, bins 10+, years other than 2020 (10% of zones) | 1,700,675 | 0.0082 | 0.0023 | 0.0226 | 0.4213 |
| label baseline cells, bins 10+, years other than 2020 (10% of zones) | 2,092,083 | 0.0049 | 0.0019 | 0.0135 | 0.2618 |
| labels, held-out years | 2,088,039 | 0.0015 | | 0.0035 | |
| labels, other years | 2,793,668 | 0.0012 | | 0.0030 | |

Bottom-decile membership within field-year flips for **1.36%** of held-out zone-years and 0.95% of others. The exclusion is small in aggregate and large for individual cells, up to 0.42 NDVI in the feature baseline: the signature of a targeted correction that leaves most zones alone and changes the lodged ones. The feature is unaffected by construction, because its bins, 0 to 6, all precede 10 August 2020.

**4. Corn versus soybean relative standing.** Per zone, mean relative NDVI over bins 0 to 11 in its corn years and in its soybean years, correlated across zones. The reference is the same statistic between the earlier and later half of a zone's own years of one crop.

| pair | zones | Pearson | Spearman |
|---|---|---|---|
| corn years vs soybean years | 695,433 | 0.539 | 0.460 |
| reference: earlier vs later corn years | 700,795 | 0.651 | 0.572 |
| reference: earlier vs later soybean years | 640,391 | 0.537 | 0.546 |

The raw figures are not directly comparable. The cross-crop correlation uses all of a zone's years on each side, while each reference splits one crop's years in half and so rests on fewer. Correcting the references to full length with the Spearman-Brown formula, 2r / (1 + r), gives reliabilities of 0.789 for corn and 0.699 for soybean. Dividing the cross-crop correlation by the square root of their product gives a **disattenuated cross-crop correlation of 0.726**, so about **53%** of a zone's stable relative standing is shared between its corn and soybean years and the remainder is crop-specific.

Two caveats. The earlier-versus-later split also absorbs genuine change in a zone over eight years, which lowers the reference and makes the correction slightly generous. And the correction assumes the halves are parallel measurements, which a corn-soybean rotation only approximates.

This is a partial zone-by-crop interaction, not a negligible one. It does not change the Step 2 baseline, which pools crops by design, but it strengthens the case for the crop-stratified S1 variant already scheduled as an ablation (issue #4), and the two mechanisms named there, soybean iron deficiency chlorosis on the calcareous soils of the Des Moines Lobe and droughty patches penalising corn more than soybean, are plausible sources.

**5. Green-up spread around the NASS anchor.** Per field-year, the first date the field-median NDVI reaches its seasonal minimum plus half its amplitude, using field-dates at least 50% clear and including dates before planting so the curve has a floor. Days after the NASS 50% planted date.

| crop | identifiable field-years | p10 | median | p90 | interquartile range |
|---|---|---|---|---|---|
| corn | 14,317 | 37 | 47 | 59 | 11 days |
| soybean | 10,732 | 40 | 52 | 63 | 15 days |

Unidentifiable field-years, where the first clear reading was already past the level, run from 0.0% to 3.0% by crop-year. Per-year quantiles fall on acquisition dates, so they move in steps of a few days.

Half-amplitude green-up corresponds to mid-canopy development, and a median of 47 days after 50% planting is consistent with that for corn. The interquartile ranges of 11 and 15 days are roughly one 200 GDD bin in midsummer. Field-to-field planting variation within a year is a field-year constant that the within-field baseline cancels, so this spread matters only for cross-year bin alignment, where it amounts to about one bin of misalignment for the middle half of field-years. Recorded as the size of the anchor's limitation rather than as grounds to change it.

**6. Zone size, 10m against 30m.** Issue #7. Metric and prior expectation were committed before any 10m pixel was exported (`scripts/zone_size_export.py`, commit c74bef5). Fifty fields: one chosen with the project seed plus its 49 nearest neighbours, a 16.3 km2 box, frozen in `orbitalscout/frozen/zone_size_sample.csv`. The architecture note asked for a scattered random sample; an Earth Engine export is rectangular, so scattered fields would have meant a county-sized 10m box, roughly 1.5 GB per season. Noise and co-registration jitter are not organised at county scale, so a compact block samples them fairly, but the deviation is recorded.

Both resolutions run through the same production baseline views. Per zone and year, the mean within-field relative NDVI over the label window; per zone, the standard deviation of that across years, zones with at least three years.

| zone size | zones | median SD | p25 | p75 |
|---|---|---|---|---|
| 10m | 59,327 | 0.0125 | 0.0072 | 0.0253 |
| 30m | 7,469 | 0.0128 | 0.0071 | 0.0257 |

Ratio of median SD, 10m over 30m: **0.98**.

**The prior expectation is not supported.** Issue #7 predicted 30m would show clearly lower year-over-year variation because averaging nine pixels suppresses sensor noise and roughly one pixel of co-registration jitter. The two are indistinguishable, and 10m is marginally lower.

The honest reading is that year-over-year variation in this quantity is not dominated by independent per-pixel noise, so aggregating nine pixels does not reduce it. Two caveats bound the claim. The metric averages over four bins and several dates before the standard deviation is taken, so per-date pixel noise is already largely averaged out on both sides; this is a fair measure of the stability of the label-window quantity, which is what the evaluation uses, but it is not a sensitive test of jitter itself, which a single-date comparison would be. And the two sides apply their minimum-valid rule at different scales: a 30m zone-date needs five of nine sub-pixels clear, while a 10m pixel-date needs only itself, so the 30m side discards partly clouded dates the 10m side keeps.

**The zone size does not change.** 30m rested on three arguments. Volume: 10m over the full AOI is about 1.6 billion rows against a single-digit GB storage claim, which stands and is decisive. Native resolution: red edge and SWIR are 20m on Sentinel-2, so a 10m NDRE or NDWI zone interpolates, which stands. Noise and jitter: **not supported by this measurement**, and that argument should not be repeated in the write-up.

## Step 3: ranking by S1 alone

Run with `python scripts/rank_step3.py` on 2026-09-17. Rung 1 of the complexity ladder: one signal, sorted, no model and no training.

**2,088,521 zone-years ranked** across the three held-out years, none dropped for a missing score.

S1 score, the negated within-field relative residual, where larger is more urgent:

| year | zone-years | p1 | p25 | median | p75 | p99 |
|---|---|---|---|---|---|---|
| 2023 | 699,441 | -0.2040 | -0.0265 | -0.0014 | 0.0187 | 0.1740 |
| 2024 | 696,733 | -0.1575 | -0.0215 | -0.0012 | 0.0183 | 0.2127 |
| 2025 | 692,347 | -0.1333 | -0.0190 | -0.0010 | 0.0135 | 0.1522 |

The median sits within 0.002 of zero in every year, which is what a residual against a zone's own history should do, and the tails are roughly symmetric.

What a budget selects, over 9,365 field-years:

| budget | zones chosen | mean per field-year |
|---|---|---|
| 20 zones | 170,350 | 18.2 |
| 5% of field | 109,000 | 11.6 |
| 10% of field | 213,103 | 22.8 |
| 20% of field | 421,449 | 45.0 |

A 20-zone budget averages 18.2 rather than 20 because some field-years hold fewer than 20 zones after the inward buffer. Mean field-year size is 223 zones, so 20 zones is roughly 9% of an average field, close to the 10% the metric is usually quoted at.

### Does the ranking reproduce the soil map?

This is the premise of D1: ranking by absolute vegetation index reproduces the permanent soil map, and the residual is supposed to remove it. A leak would appear as a **negative** correlation between urgency and persistent standing, urgent zones being the ones that are always poor.

Persistent standing has to be measured from years the strictly-prior baseline never saw. The first version of this diagnostic correlated the score against the baseline it is computed from, and reported +0.174 to +0.194. That number is arithmetic, not evidence: the score is baseline minus relative, and the covariance of the residual with the baseline is minus the variance of the baseline's own estimation noise, so a positive value is guaranteed. That is the shared-estimation-error trap recorded as open item 10b of the council review. The diagnostic was rewritten rather than reported.

Measured against later years instead:

| year | standing measured from | zone-years | Pearson | Spearman |
|---|---|---|---|---|
| 2023 | 2024, 2025 | 695,739 | 0.002 | 0.068 |
| 2024 | 2025 | 691,190 | 0.001 | 0.119 |
| 2025 | no later years available | | | |

**The residual removes the permanent soil signal.** Pearson correlation is within 0.002 of zero, and the sign is not negative, so the ranking is not selecting the always-poor zones. The small positive Spearman is consistent with mild mean reversion, zones sitting above a noisily estimated baseline having more room to fall below it, rather than with a soil-map leak.

This is a sanity check on the premise, not the evaluation. Whether the ranking is **correct** is precision@k against the label, and whether it beats the obvious alternatives is lift over B1a and B1b. Both are Step 4.

## Step 4: the evaluation harness

Run with `python scripts/step4_evaluate.py` on 2026-09-18. Gates G-1 and G-2 both pass. This is the step the project was built to reach: the ranking is measured against the nulls under the protocol frozen in `SPEC.md` Section 10 before any data was touched.

### Population

**2,088,039 labelled zone-years** across the three held-out seasons. Realised base rate **0.1020** under both labels, not the nominal 0.10, because the positive count is `ceil(0.10n)` and rounds up on every field-year that ten does not divide.

Every method is scored on the same zone-years, because comparing one method on its own scorable subset against another on a different subset is not a comparison. Coverage before the intersection:

| method | share it can score |
|---|---|
| S1 | 100.0% |
| B1a, B2 (both variants, every k) | 100.0% |
| B1b | 87.4% |

The intersection is **1,825,396 zone-years (87.4%) over 8,065 field-years**, limited entirely by B1b: a zone whose crop has not been grown in a prior year has no same-crop residual to persist, and is left unscored rather than given a zero.

### G-1, blocked splits

| held-out year | fields | field overlaps with any fit set | partition |
|---|---|---|---|
| 2023 | 2,375 | 0 | exact |
| 2024 | 2,797 | 0 | exact |
| 2025 | 2,893 | 0 | exact |

**Field blocking had nothing to separate at this rung, and that is reported rather than dressed up.** Taking an inventory of what Step 4 actually fits turns up one object, B2's k-means, and it is fit within a single field. Nothing pools across fields until rung 2. The split and its tests are in place because a leak here invalidates every number and writing them after the first pooled statistic exists is how leaks happen, but G-1 passing on this rung is a statement about the split function, not evidence that anything was held apart.

### The headline: S1 against the anomaly-persistence null

Primary label, at the 20-zone scouting budget, pooled over all field-years:

| method | precision@20 | of ceiling | recall | FPR | lift over random |
|---|---|---|---|---|---|
| **S1 temporal anomaly** | **0.3133** | 0.482 | 0.2478 | 0.0617 | 3.07 |
| B1b anomaly persistence | 0.2002 | 0.308 | 0.1584 | 0.0719 | 1.96 |
| B2 k-means, in-season, k=7 | 0.2213 | 0.340 | 0.1751 | 0.0700 | 2.17 |
| B1a level persistence | 0.1502 | 0.231 | 0.1188 | 0.0764 | 1.47 |
| B2 k-means, historical, k=7 | 0.1461 | 0.225 | 0.1156 | 0.0768 | 1.43 |

Ceiling on precision 0.6504, ceiling on lift 6.37.

Lift of S1 over each null, primary label, all field-years. B2 is taken at its best k, which was 7 in every cell:

| budget | over B1a | over B1b | over B2 historical | over B2 in-season |
|---|---|---|---|---|
| 20 zones | 2.086 | **1.565** | 2.145 | 1.416 |
| 5% of field | 2.425 | **1.837** | 2.532 | 1.468 |
| 10% of field | 2.256 | **1.688** | 2.329 | 1.421 |
| 20% of field | 1.937 | **1.469** | 1.978 | 1.363 |

**The persistence null was beaten, at every budget.** `CLAUDE.md` pre-committed to a roughly one-in-three chance of the opposite outcome and to reporting it as the headline if it happened. It did not happen.

### Per-year spread

`SPEC.md` Section 10 requires each held-out season separately, reported as a spread rather than a point, so that a year which happened to be easy cannot carry the result.

| year | zone-years | S1 precision@20 | ceiling | B1b precision@20 | S1 / B1b | S1 / B2 in-season |
|---|---|---|---|---|---|---|
| 2023 | 523,458 | 0.3200 | 0.6456 | 0.1983 | 1.614 | 1.449 |
| 2024 | 640,207 | 0.3468 | 0.6526 | 0.2005 | 1.730 | 1.400 |
| 2025 | 661,731 | 0.2754 | 0.6522 | 0.2016 | 1.366 | 1.404 |

S1 leads B1b in every year. The spread on that lift is **1.37 to 1.73**, and 2025 is the weakest season by a clear margin while B1b itself barely moves across the three. The spread is the reported quantity.

### The thesis, stated as a measurement

The claim of the project is that a within-field relative residual finds *anomalous* underperformance, where a commercial index map finds *permanently poor ground*. That predicts a large margin on the residual label and a small one on the level label. Measured, at the 20-zone budget:

| label | S1 | B2 in-season k=7 | B1a | S1 over B2 | S1 over B1a |
|---|---|---|---|---|---|
| primary, residual | 0.3133 | 0.2213 | 0.1502 | **1.416** | **2.086** |
| secondary, level | 0.2928 | 0.2669 | 0.2478 | **1.097** | **1.182** |

On the level label S1's margin over the best commercial baseline collapses from 42% to 10%, and its margin over level persistence from 109% to 18%. **That collapse is the contribution.** The detection is not novel and is not claimed to be; what the evaluation shows is that the two labels rank methods differently, and that a system measured only on the level label would look almost indistinguishable from a k-means zone map.

B1a moves the other way, from 0.1502 on the residual to 0.2478 on the level, which is the same fact seen from the baseline's side.

### Where the pre-registered prediction was wrong

Section 10 predicted that "B1a is expected to score at or near chance against the primary label, because the primary label subtracts the zone mean that B1a ranks on."

**That was too strong.** B1a scores lift 1.47 over random on the primary label, well above chance. The direction of the prediction holds, since B1a is far weaker on the residual label (1.47) than on the level label (2.42), but the magnitude was wrong and the reason is identifiable: the primary label subtracts the *leave-one-year-out* baseline over the label window, while B1a ranks on the *strictly prior* baseline over the feature window. Those are different quantities estimated from different years over different growth stages, so the subtraction was never going to be exact and B1a keeps real signal.

The prediction is left in `SPEC.md` unedited, and this paragraph is the record that it did not survive contact with the data.

### The ceiling binds, and precision alone would be misread

At the 20-zone budget a perfect ranker reaches **0.6504**, not 1.0. The reason is field-year size: median positives per field-year is **14** against a 20-zone budget, and **59.9% of field-years hold fewer positives than the budget has stops**. Those stops cannot be spent on positives because there are not enough to spend them on.

So S1's 0.3133 is **48.2% of what was achievable**, not 31% of a notional 100%. At k = 20% of field the ceiling is **0.5058**, which is the 0.50 arithmetic cap that Step 4 Decision 10 predicted before the run: with a 10% base rate, a fifth of the field cannot be more than half positives.

Reading the raw precision row across budgets without the ceiling would suggest S1 degrades from 0.4359 at k=5% to 0.2516 at k=20%. As a fraction of ceiling it goes 0.436, 0.350, 0.497: it does not degrade, it runs out of positives to find.

### Field-years the budget swallows whole

At a 20-zone budget, **1,491 of 8,065 field-years (18.5%)** hold 20 zones or fewer and are selected in full. There precision equals the base rate whatever the ranking does. They supply **10.8% of every zone precision@20 is computed over**.

Excluding them:

| population | S1 precision@20 | ceiling | S1 / B1b |
|---|---|---|---|
| all field-years | 0.3133 | 0.6504 | 1.565 |
| field-years larger than the budget | 0.3343 | 0.7121 | 1.611 |

The exclusion raises S1's precision by 6.7% and its lift over B1b by 2.9%, so leaving it in **understates** the ranker. It is a smaller effect than Decision 10 anticipated, because micro-averaging over selected zones already downweights small field-years: they are 18.5% of field-years but 0.9% of zone-years. Both populations are reported at every budget and both labels; the conclusions do not depend on the choice.

### B2, and a comparison that was deliberately made harder

B2 improves monotonically with k and is strongest at k=7 in **every** cell of every table, which is what a finer partition should do: more clusters means a less tied ranking. B2 is therefore always reported at its best k. Choosing a hyperparameter after seeing results is normally cheating; here it is cheating in the baseline's favour, which makes the claim against it conservative.

The larger decision was the period B2 clusters. `SPEC.md` Section 10 names the method and not the period, and the first implementation clustered prior years only, matching a static multi-year management zone map. But S1 reads the current season, and commercial platforms ship in-season index maps too, so a history-only B2 is a handicapped commercial baseline. Both variants are reported, and the difference is not small:

| comparison | lift of S1, 20 zones |
|---|---|
| over B2 historical, k=7 | 2.145 |
| over B2 in-season, k=7 | **1.416** |

The fair comparison costs a third of the headline. The weaker number is the one that would have been easier to publish, which is why it is not the one reported.

### G-2

`SPEC.md` gate G-2 requires the ranker to beat random at precision@10% on the primary label. S1 scores 0.3488 against a measured base rate of 0.1020, a lift of **3.42**. Passed.

### Limitations

- The label is a proxy, not independent ground truth. It is a within-field-year decile of a modelled residual, so this measures whether the ranking finds the zones the residual calls worst, not whether a scout would find something wrong there. Section 10 says so and it remains true.
- The temporal gap is a single 200 GDD bin, bin 7 at R1 silking. Features come overwhelmingly from bin 6, immediately before it. That is the gap the frozen protocol specifies, and it is short.
- S1 has access to current-season observations that B1a, B1b and the historical B2 do not. For the persistence nulls that asymmetry is the whole experiment, since the question is whether in-season imagery adds anything to what last year already told you. The in-season B2 exists so that the commercial comparison does not inherit the same asymmetry.
- Uncertainty intervals are not reported. Where they are added they must be resampled over fields, never zones: a zone-level bootstrap over 1.8 million spatially autocorrelated rows would produce an interval tight enough to be a lie.
- Timing, for reproduction rather than as a result: the first run took about twelve minutes in `load` against a cold page cache and eight seconds warm. Scoring is about eleven minutes, almost all of it the twelve k-means sweeps, and is cached in `data/eval/scored.parquet`.

## Step 5, S2 spatial anomaly: cut

Run with `python scripts/step5_s2.py` on 2026-09-18. The prediction was committed in `docs/reviews/2026-09-18-step5-s2-prediction.md` before any S2 code existed.

**S2 did not improve lift over persistence and was cut.** It is implemented and tested, and it is not in `SIGNALS`.

### Population

1,819,058 zone-years, 99.7% of the Step 4 comparison population. The 6,338 lost are zones with fewer than three neighbours inside their own field-year. 72.0% of zones have all eight neighbours, so the floor costs almost nothing. Every method below is measured on this same set, so rung 1 and rung 2 are not scored over different zones. S1's numbers therefore differ from the Step 4 table in the fourth decimal.

### The admission rule

Primary label. The question is whether adding S2 to S1 improves lift over the B1b persistence null.

| budget | S1 over B1b | S1+S2 over B1b | change |
|---|---|---|---|
| 20 zones | 1.576 | 1.405 | **-10.8%** |
| 5% of field | 1.846 | 1.629 | **-11.8%** |
| 10% of field | 1.695 | 1.504 | **-11.3%** |
| 20% of field | 1.473 | 1.332 | **-9.5%** |

Worse at every budget, by about a tenth. Not marginal, not a coin flip.

### S2 on its own

| budget | precision | of ceiling | lift over random | lift over B1b |
|---|---|---|---|---|
| 20 zones | 0.2022 | 0.309 | 1.99 | 1.017 |
| 5% of field | 0.2626 | 0.263 | 2.58 | 1.116 |
| 10% of field | 0.2158 | 0.218 | 2.12 | 1.052 |
| 20% of field | 0.1689 | 0.335 | 1.66 | 0.992 |

**S2 alone is roughly the persistence null.** Lift over B1b runs 0.99 to 1.12. A spatial level signal and a temporal persistence null are, on this label, about equally good, which is what two different views of the same permanent structure should look like.

On the secondary level label S2 rises to lift 2.61 over random at the 20-zone budget against 1.99 on the residual label, and sits level with the in-season k-means baseline (0.2648 against 0.2659). A level signal scores levels. That is the whole story.

### The predictions

All three held, which is worth stating plainly next to Step 4, where the spec's own pre-registered prediction about B1a did not.

| prediction | outcome |
|---|---|
| S2 alone lands at lift 1.2 to 2.0 over random at the 20-zone budget | **held, barely.** Measured 1.99, at the top edge. It would have failed at any tighter budget: 2.58 at k = 5% |
| S2 does relatively better on the level label than the residual label | **held.** 2.61 against 1.99 |
| S1 plus S2 does not improve lift over B1b | **held, at all four budgets** |

### The mechanism check, and what it found instead

Prediction 4 said that if the combination helped, the gain should concentrate in zones whose baseline rests on the fewest prior years. It did not help, so that test was not needed for its original purpose. Run anyway, it says something more useful:

| prior years behind the baseline | zone-years | S1 precision@20 | S1+S2 precision@20 | change |
|---|---|---|---|---|
| 3 | 973 | 0.2214 | 0.1985 | -10.3% |
| 4 | 46,917 | 0.2378 | 0.2148 | -9.7% |
| 5 | 558,753 | 0.3031 | 0.2668 | -12.0% |
| 6 | 647,678 | 0.3283 | 0.3001 | -8.6% |
| 7 | 564,737 | 0.2792 | 0.2452 | -12.2% |

The damage is **flat across history depth**, between 9 and 12 percent everywhere with no trend. So this is not "S2 helps thin-history zones and hurts the rest." S2 dilutes S1 uniformly.

### The finding that matters more than the verdict

Look at the first row. **Only 973 zone-years out of 1.8 million rest on the minimum three prior years.** `SPEC.md` Section 7 justifies S2 as detecting "first-year problems with no history," but a zone with no history is excluded from this evaluation by the `MIN_PRIOR_YEARS` support floor before S2 is ever consulted.

**S2's advertised niche is empty by construction here.** It was measured only on the population where S1 already works, and there it is a dilutant. Whether it earns its place on zones below the support floor is a different experiment and is not answered by this one, because that population was defined away at Step 2.

That is not a reason to admit S2 now. It is a reason to be precise about what was and was not tested, and it is recorded as issue [#20](https://github.com/CaiZhengTech/OrbitalScout/issues/20).

### What this changes

Nothing ships. `SIGNALS` remains S1 alone and a test asserts it. `signals.s2_spatial_anomaly`, `signals.neighbour_mean` and the rung 2 machinery in `rank.py` stay in the repository with their tests, because the null result is a reported finding and the code behind a reported finding has to be inspectable.

Rung 2 was exercised and did not beat rung 1. The complexity ladder stops at rung 1 for now.

## Step 5, S3 multi-index divergence: cut

Run with `python scripts/step5_s3.py` on 2026-09-19. The prediction was committed in `docs/reviews/2026-09-19-step5-s3-prediction.md` before any S3 code existed.

**S3 did not improve lift over persistence and was cut.** It is implemented and tested, and it is not in `SIGNALS`.

**Two of the four predictions failed.** Both failures are recorded below with what they got wrong.

### Population

1,825,396 zone-years, 100.0% of the Step 4 comparison population. S3 loses no coverage: every zone with a feature has all three indices.

The feature table was rebuilt so that all three residuals come from one observation (Step 5, Decision 17). `feature_ndvi` came back **bit-identical on all 1,825,396 rows**, so S1's Step 4 numbers carry over unchanged and the two steps are directly comparable.

### The admission rule

Primary label. The question is whether adding S3 to S1 improves lift over the B1b persistence null.

| budget | S1 over B1b | S1+S3 over B1b | change | all three as a level | vs S1 |
|---|---|---|---|---|---|
| 20 zones | 1.565 | 1.147 | **-26.7%** | 1.533 | -2.0% |
| 5% of field | 1.837 | 1.247 | **-32.1%** | 1.790 | -2.6% |
| 10% of field | 1.688 | 1.224 | **-27.5%** | 1.663 | -1.5% |
| 20% of field | 1.469 | 1.183 | **-19.5%** | 1.467 | -0.1% |

Worse at every budget, and by much more than S2 was. S3 is cut.

### S3 on its own

| budget | precision | lift over random | lift over B1b |
|---|---|---|---|
| 20 zones | 0.1258 | 1.23 | 0.628 |
| 5% of field | 0.1391 | 1.36 | 0.586 |
| 10% of field | 0.1283 | 1.26 | 0.621 |
| 20% of field | 0.1149 | 1.13 | 0.671 |

Barely better than random, and well under the persistence null.

### The predictions, two of four wrong

| prediction | outcome |
|---|---|
| 1. S3 alone scores **below** random, lift under 1.0 | **FAILED.** Measured 1.13 to 1.36, above random at every budget |
| 2. NDVI cancels in S1+S3: Spearman with the early-index mean above 0.90 | **FAILED.** Measured 0.843 |
| 3. S1+S3 does not improve lift over B1b | **held**, at all four budgets, by 19.5% to 32.1% |
| 4. The diagnostic decides what the null means | **resolved**: the aggregation also fails, so this is a verdict on the indices, not on S3's form |

**Why prediction 1 was wrong.** The argument was that S3 is loaded positively on the NDVI residual, the label is built from an NDVI residual, so S3 should rank the label backwards. Measured, the rank correlation between S3 and S1 is only **-0.136**: S3 is close to orthogonal to S1, not strongly opposed to it. Standardising each index within field-year and then averaging the two early ones dilutes the NDVI term far more than the algebra assumed, and what is left carries enough real information to sit slightly above chance rather than below it.

**Why prediction 2 was wrong.** The cancellation is partial, not complete. The algebra treated `z(S3)` as if it arrived already on the same scale as `z(residual_ndvi)`, but rung 2 standardises S3 as a whole, which rescales the contrast and leaves some NDVI behind. The direction was right and the magnitude was not: S1+S3 correlates 0.843 with the early-index mean against only **0.584** with S1, so the combination is much closer to having discarded NDVI than to being S1 plus something.

### Why S3 fails, measured rather than argued

The three indices are largely redundant at this grain. Across 3,432,652 zone-year feature cells:

| Pearson | NDVI | NDRE | NDWI |
|---|---|---|---|
| **NDVI** | 1.000 | 0.960 | 0.909 |
| **NDRE** | 0.960 | 1.000 | 0.943 |
| **NDWI** | 0.909 | 0.943 | 1.000 |

Rank correlation after z-scoring within field-year is 0.934 for NDVI against NDRE and 0.857 against NDWI.

That single table explains both results. Adding two indices that correlate above 0.9 with the first cannot add much, which is why the all-three level sits within 2.6% of S1. And contrasting quantities that correlate above 0.9 leaves a small residue dominated by measurement noise rather than by differential plant physiology, which is why the contrast ranks barely above chance.

**Section 7's premise is not visible in this data at this grain.** The claim that NDWI moves before NDVI and NDRE before that is a statement about within-season timing. What is measured here is one residual per zone-year, taken from the latest supported cell of the feature window, and at that resolution the three indices are nearly the same measurement. Whether the premise holds at a per-date grain is a different question and this run does not answer it.

### One result the other way

On the **secondary** level label the all-three level beats S1: lift over B1b of 1.271 against 1.234 at the 20-zone budget, and 1.339 against 1.300 at k = 5%. Averaging three correlated measurements is a better estimate of a zone's level, which is what that label rewards. It is not a better estimate of a zone's anomaly, which is what the primary label and the admission rule ask for. The finding is reported because it was measured, not because it changes the verdict.

### What this changes

Nothing ships. `SIGNALS` remains S1 alone. `signals.s3_multi_index_divergence` and `signals.multi_index_level` stay with their tests.

The feature table change does ship: `zone_year_feature` now carries all three residuals and selects one row explicitly, which also closed a latent inconsistency where `feature_ndvi` came from `arg_max(residual_ndvi, bin)` while `feature_bin` came from a separate `max(bin)`. Those name different cells the moment a null appears. There are no nulls today, so nothing was wrong; there was simply nothing stopping it.

Two signals measured, two cut. Rung 1 still stands alone.

## Step 5, S4 onward

`[TBD]`. S4 velocity not started.




