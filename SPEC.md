# OrbitalScout V1 — Technical Specification

Version 0.1 (pre-build)
Status: draft, written before implementation. Numbers marked `[TBD]` are outputs of the build, not targets.

---

## 1. Problem statement

Given an agricultural field and a scouting budget expressed as a fraction of field area, produce a ranked list of sub-field zones ordered by how urgently they warrant physical inspection.

The system answers **where to look**, not **what is wrong**. Disease and pest identification are explicitly out of scope: at 10m ground sample distance the signal to distinguish causes is not present.

## 2. Goals and non-goals

### Goals

- G1. Rank zones within a field by anomalous underperformance relative to that zone's own multi-year, phenology-aligned history.
- G2. Evaluate that ranking with ranking metrics (precision@k, lift) rather than pixel classification accuracy.
- G3. Compare against two baselines: the commercial-standard NDVI k-means zoning, and a persistence null.
- G4. Operate at zero marginal cost on free public data and CPU-only compute.
- G5. Produce a static, precomputed demo that remains functional without a running backend.

### Non-goals

- NG1. Disease or pest identification.
- NG2. Yield prediction in physical units.
- NG3. Real-time or near-real-time operation. Cadence is governed by cloud-free satellite revisit, typically 8 to 12 days in temperate growing regions.
- NG4. Prescription maps, variable-rate application, or any machine-executable output.
- NG5. Coverage outside the contiguous United States. Crop labels and soil data are US-specific.
- NG6. A live API or hosted service.

## 3. Scope for V1

| Dimension | V1 scope |
|---|---|
| Geography | Story County, Iowa, restricted to the region under both Sentinel-2 relative orbits (64% of the county; see `RESULTS.md` finding 2) |
| Crops | Corn and soybean |
| Years | 2018 to 2025; the last three held out in rotation. 2017 excluded, see `RESULTS.md` finding 1 |
| Season window | Roughly May through September, bounded by phenology not calendar |
| Zone size | 10m, matching Sentinel-2 native resolution |
| Field definition | USDA Crop Sequence Boundaries polygons |

## 4. Data sources

All sources are free. Registration requirements are flagged because they gate the start of work.

| Source | Purpose | Access | Registration |
|---|---|---|---|
| Sentinel-2 L2A | In-season optical time series | Earth Engine `COPERNICUS/S2_SR_HARMONIZED`, joined to Cloud Score+ by `system:index`, masked and zonally reduced in one expression | Earth Engine |
| Sentinel-2 L2A (cross-check) | Independent check of exported values on a sample of zones | Planetary Computer `sentinel-2-l2a` via `pystac-client` | No |
| Cloud Score+ | Cloud and shadow masking | Earth Engine `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | Earth Engine |
| USDA Crop Sequence Boundaries | Field polygons | GeoParquet mirror, Source Cooperative `fiboa/us-usda-cropland` | No |
| USDA Cropland Data Layer | Crop type labels | CropScape REST, or Earth Engine `USDA/NASS/CDL` | No |
| AlphaEarth Satellite Embedding | Multi-year zone prior. Rung 3 only; not ingested before rung 3 is reached | Earth Engine `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` | Earth Engine |
| USDA Soil Data Access | Drainage class, slope | POST to `https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest` | No |
| Open-Meteo Historical | Daily temps for GDD | `https://archive-api.open-meteo.com/v1/archive` | No |

### Known data constraints

- **CDL release lag.** Each year's CDL is published the following February. In-season crop type must come from the prior year's CDL. Acceptable in the Corn Belt given stable corn-soy rotation; the rotation mismatch rate must be quantified on the test fields, not assumed.
- **AlphaEarth is annual.** It cannot supply in-season signal. It serves as a multi-year zone prior only.
- **CSB polygons are synthetic field units**, not legal parcels. Adjacent same-crop fields not separated by a road or rail line may merge.
- **Clear observation count is unverified** for the chosen AOI and must be measured first. See Section 10, gate G-0.

## 5. Coordinate reference system

All spatial data is reprojected to **EPSG:5070 (NAD83 / Conus Albers)** at ingestion. CDL and CSB are native to this CRS; Sentinel-2 arrives in UTM and is reprojected once, during ingestion, never later.

CRS equality is asserted before any spatial join. A mismatch must raise, never silently reproject at join time.

Categorical rasters (CDL) are resampled with nearest neighbour only. Continuous rasters use bilinear.

## 6. Zone definition

A zone is a square grid cell of configurable side length, aligned to the Sentinel-2 10m grid, whose centroid falls inside a CSB field polygon after an inward buffer of one pixel to exclude boundary-contaminated pixels.

Zone size is a parameter in `config.py`, not a constant. Step 0 measures the year-over-year variance of stable zones at 10m and 30m on a sample of fields across all seasons; the choice is made from that measurement and recorded in `RESULTS.md`. The concern at 10m is Sentinel-2 co-registration jitter of roughly one pixel between passes, which makes a single pixel's multi-year series partly its neighbour's.

Zonal aggregation is a mean over the pixels within the zone, computed in Earth Engine in the same expression that applies the cloud mask, so masked pixels are excluded by construction. Nothing is aggregated locally.

Zones with fewer than a configured minimum of valid pixels across the season are dropped, not imputed.

## 7. Signals

Six signals. Each returns one score per zone per observation date. All are z-scored before combination so they are unit-comparable.

| ID | Signal | Definition | Detects what the others miss |
|---|---|---|---|
| S1 | Temporal anomaly | Deviation from this zone's own phenology-aligned multi-year mean | Baseline signal |
| S2 | Spatial anomaly | Deviation from immediately neighbouring zones, same date | First-year problems with no history; self-corrects for whole-field effects like regional drought |
| S3 | Multi-index divergence | Disagreement between standardised NDVI, NDRE, NDWI | Water stress before visible decline; chlorophyll issues before biomass loss |
| S4 | Velocity | Rate of change of the S1 anomaly | Earlier detection than level-based signals |
| S5 | Persistence | Run length of consecutive clear-observation anomalies | Suppresses missed cloud shadow, the dominant false positive |
| S6 | Soil-context residual | Residual after regressing index on SSURGO drainage class and slope | Distinguishes "bad because always sandy" from "bad beyond soil explanation" |

### Signal interface contract

Every signal is a function with identical shape:

```
score(zone_features: DataFrame, context: Context) -> Series  # one score per zone-date
```

No signal may require a special branch in the orchestrator. If one does, reshape the signal, not the orchestrator.

### Signal admission rule

A signal enters the shipped system only if adding it measurably improves lift over persistence. Signals that do not are removed from the combination and their null result recorded in `RESULTS.md`. Building a signal does not entitle it to ship.

## 8. Phenology alignment

The temporal baseline is aligned by **accumulated growing degree days**, not calendar day of year.

- GDD computed from Open-Meteo daily max/min at the field centroid.
- Corn: base 50°F, cap 86°F.
- Soybean: base 50°F. Note that soybean development is strongly photoperiod and maturity-group driven and there is no authoritative GDD-per-stage table. Soybean phenology alignment is therefore weaker than corn and this limitation is stated in results rather than hidden.

The per-zone baseline is **within-field relative**, not absolute. For zone i in field f at phenology bin b in year t:

```
relative_index(i, t, b) = index(i, t, b) - median over zones in f of index(., t, b)
baseline(i, b)          = mean over prior years of relative_index(i, ., b)
residual(i, t, b)       = relative_index(i, t, b) - baseline(i, b)
```

The field centre is a median rather than a mean so that a large anomaly covering a substantial share of the field cannot drag the centre toward itself and shrink its own residual.

Crop is a property of the field-year, not of the zone. Corn Belt fields rotate as whole units, so within any field-year every zone shares one crop, and so does the weather, the planting date and the management. Measuring each zone against its own field in the same year cancels all of them at once. The baseline therefore pools every prior year regardless of crop, which keeps usable history at five to seven seasons rather than the two to four that crop stratification left. Effective history length is measured and reported in `RESULTS.md`, never assumed.

Within-field relativity does not cancel a zone-by-crop interaction, where a zone's relative standing genuinely differs between corn years and soybean years. A crop-stratified variant of S1 is therefore a candidate refinement in the ablation ladder, admitted only if it measurably improves lift over B1b, exactly like any other signal. Step 2 reports the across-zone correlation between mean relative standing in corn years and in soybean years as a diagnostic, not as a gate.

Crop-specific parameters live in a **crop registry table**, one row per crop, keyed by CDL code:

```
cdl_code, crop_name, gdd_base_f, gdd_cap_f, planting_window_start, planting_window_end,
gdd_stage_map, indices_by_stage, min_zone_pixels
```

Adding a crop means adding a row. No crop name may appear in a conditional anywhere in the codebase.

## 9. Model and ranking

Deliberate complexity ladder. Each rung must beat the one below it to justify existing.

1. **Single signal, sorted.** No model. Complete and shippable.
2. **Weighted sum of z-scored signals, sorted.** One line, no hyperparameters.
3. **LightGBM learning the combination.** Only if it beats rung 2 on held-out precision@k.

If rung 3 does not beat rung 2, it is cut and the result reported. A weighted sum being sufficient is a finding, not a failure.

Rungs 1 and 2 involve no training. Holdout structure still applies to evaluation.

## 10. Evaluation protocol

**This section is written before any data is touched and must not be revised after seeing results.**

### Ground truth

**Primary label.** A zone-year is underperforming when its end-of-season residual falls in the bottom decile of residuals within that field-year. The residual is the within-field relative residual defined in Section 8, with its baseline estimated leave-one-year-out as described under Circularity control. The base rate is fixed at 10% by construction and is stated here before any data was pulled, which makes lift over random arithmetic rather than a quantity discovered afterwards.

This is a ranking-quality label, not an incidence label. It answers "under a fixed scouting budget, can the ranker find the worst zones in this field-year," which is the question the product answers. It does not answer "how often does something go wrong," which is what the secondary label addresses.

A per-zone standard-deviation threshold was rejected on three counts. A held-out year has five to seven prior seasons behind it, so an annual residual standard deviation would rest on five to seven points, far too few. It selects on estimation error, so zones whose variance is underestimated by chance are flagged every year. And it flags backwards, tripping stable zones on trivial deviations while giving erratic zones a band they rarely cross.

**Secondary label.** Absolute end-of-season underperformance: the bottom decile of raw index within field. The NDVI k-means baseline (B2) is expected to do well on this label and poorly on the primary one. Both labels are reported for every method; the gap between them is the thesis, stated as a measurement.

**Circularity control.** A mandatory temporal gap separates the feature window from the label window. Features may not use observations from within the label window. The gap is configured once and recorded.

The baseline used to compute the **label** residual is estimated leave-one-year-out: it excludes the target year and is computed separately from the baseline used for features. Without this, the feature and the label subtract the same estimated baseline and share its estimation error, which the temporal gap does not separate.

This proxy is not independent ground truth and the limitation is stated plainly in results. Where a documented damage event overlaps the AOI (for example the August 2020 Iowa derecho, for which USDA NASS published a damage polygon layer), it is used as a qualitative case-study check, not as the primary label.

### Splits

- Held out by **year** and by **field**. Both.
- Never a random split of zones or pixels. Adjacent zones are spatially autocorrelated and are not independent samples.
- Year holdout rolls across the last three seasons. Each held-out season is evaluated separately and results are reported as a spread across the three, not as a single point.
- Field holdout is `GroupKFold` grouped by field, within each year holdout.

Blocking applies to everything that is **fit** on data: z-score statistics, rung-2 weights, k-means, LightGBM, and any calibration of the label. The per-zone baseline is not fit; it is computed from one zone's own history and is subject to a temporal rule only: strictly prior years, never the target year, never the label window.

The split logic is unit tested at both layers. One test asserts that no field used to fit anything appears in the test set, and that no test year appears in any fit-set. A second test asserts that every baseline value is computed only from years strictly before the year it is applied to.

### Metrics

- Primary: **precision@k** at a fixed absolute scouting budget, expressed in zones, set from what one person can physically walk in a single visit. Recorded in `config.py` `[TBD]`. This is the agronomically meaningful number.
- Also reported at k = 5%, 10%, 20% of field area, for comparability with how the metric is usually quoted.
- **Lift over random** = precision@k divided by base rate.
- **Lift over B1b, anomaly persistence** is the headline number.
- **Lift over B1a, level persistence** is reported on the secondary label, where it is a fair comparison.
- **Lift over NDVI k-means baseline** — the commercial comparison.
- False positive rate at each k.
- Base rate per field-year, under each label.
- **Zone-by-crop correlation**, reported from Step 2: the across-zone correlation between a zone's mean relative standing in corn years and in soybean years. This is a diagnostic on the pooled baseline of Section 8, reported in `RESULTS.md` whatever its value. It does not gate anything and no threshold is set on it; the crop-stratified variant of S1 earns its place by lift or not at all.

All metrics are reported under both labels, for every method and both baselines.

### Baselines

- **B1a, level persistence.** Ranks zones within a field by their multi-year mean index, ascending, computed from prior years only. It predicts that the zones which have always been worst will be worst again. Permanent soil structure repeats annually, which makes it hard to beat on the **secondary** label. It is scored against the primary label as well, but see the pre-registered prediction below.
- **B1b, anomaly persistence. The headline null.** Ranks zones by their residual in the most recent prior year **with the same crop**, ascending. It predicts that the zones which were unusually bad the last time this crop was grown will be unusually bad again. Under the rotation measured at Step 0 that is usually two years back; where a field does not rotate it reduces to the prior year. Same-crop rather than simply prior-year, because if a zone-by-crop interaction exists then last year's residual is anti-informative about a crop-specific recurrence, which would handicap the null a second time by a different route. It is construct-matched to the primary label, since both are measured on the same residual, so it can genuinely win.
- **B2, NDVI k-means.** k-means on a vegetation index into 2 to 7 zones, matching what commercial platforms ship. Rank zones by cluster mean.

**Pre-registered prediction, written before Step 0 ran and before any data was pulled.** B1a is expected to score at or near chance against the primary label, because the primary label subtracts the zone mean that B1a ranks on. Any large lift over B1a on the primary label is therefore an artifact of the label definition and must not be reported as evidence that the ranker works. The honest headline is lift over B1b on the primary label, and lift over B1a on the secondary label. This paragraph exists so that the distinction cannot be quietly dropped after results are seen.

### Acceptance gates

| Gate | Condition | Action if failed |
|---|---|---|
| G-0 | Median clear observations per season ≥ 6 for the AOI | Widen phenology bins, add Sentinel-1, or change AOI. **Run this first, before anything else.** |
| G-1 | Split function passes leakage unit tests | Stop. Nothing downstream is valid. |
| G-2 | Ranker beats random at precision@10%, primary label | Investigate before proceeding |
| G-3 | Ranker beats B1b anomaly persistence at the absolute scouting budget, primary label | Not required to pass. If failed, report as the primary finding: prior-year anomaly explains this year's anomaly and the ranker adds nothing beyond it. |
| G-4 | CDL rotation mismatch below 10% on test fields | Restrict to fields with confirmed stable rotation |

**G-3 is not a pass/fail gate on the project.** A well-characterised negative result is a valid and reportable outcome. The failure mode to avoid is discovering a negative result and quietly reframing the project to hide it.

## 11. Module layout

Flat and boring. No plugin architecture, no registry pattern, no abstract base classes.

```
orbitalscout/
  config.py           # AOI, years, CRS, paths, thresholds. One place.
  crops.py            # crop registry table loader
  ingest/
    gee.py            # Sentinel-2 + Cloud Score+ + zonal reduce, one expression, table export
    masking.py        # the single clear-observation threshold, imported by gee.py
    boundaries.py     # CSB field polygons
    cdl.py            # crop labels
    soil.py           # SDA queries
    weather.py        # Open-Meteo, GDD accumulation
    embeddings.py     # AlphaEarth. Rung 3 only. Not written before then.
    crosscheck.py     # Planetary Computer pull of a zone sample, compared to the GEE export
  zones.py            # zone construction, inward buffer
  features.py         # index computation over the exported zone table
  baseline.py         # phenology-aligned per-zone historical baseline
  signals.py          # six functions, one shared signature
  rank.py             # combination and sort
  baselines.py        # persistence null, NDVI k-means
  evaluate.py         # precision@k, lift, splits
  export.py           # precomputed GeoJSON for the demo
tests/
  test_splits.py      # leakage tests. The most important tests in the repo.
  test_crosscheck.py  # GEE export vs independent PC pull on a zone sample. Manual, network, not CI.
  test_baseline.py    # baseline computation
demo/
  index.html          # MapLibre, one file
Makefile              # the pipeline. Five linear steps. Not an orchestrator.
```

### Shared-once rule

Cloud masking, CRS reprojection, and zonal aggregation are applied **once during ingestion, in a single Earth Engine expression**, producing a clean feature table that all signals read. No signal may reimplement any of them. Two definitions of "clear observation" would make S5 meaningless.

## 12. Storage

DuckDB over Parquet, local. The full modelling dataset is single-digit GB and fits on a laptop.

Justification for interview: the joins across five years of zone-level data are cleaner in SQL, and DuckDB reads Parquet directly with no server. Not chosen for scale, chosen for join ergonomics at small scale.

No PostGIS, no cloud warehouse, no Spark.

## 13. Demo

Static, precomputed, no backend.

- Two maps side by side, same field, same date: NDVI k-means baseline versus the residual ranker.
- Slider: scouting budget at 5%, 10%, 20% of field area. Both maps highlight their top-ranked zones; precision@k for each updates live.
- Toggle: reveal ground-truth underperformance overlay.
- MapLibre GL JS, single HTML file, GeoJSON loaded directly.
- Hosted on GitHub Pages or Vercel static.

PMTiles only if the GeoJSON payload becomes unwieldy. Not preemptively.

The demo must not use the phrase "real time."

## 14. Testing

Unit test what fails silently:

- **Split logic.** Two tests. No field used to fit anything appears in the test set, and no test year appears in any fit-set. Every baseline value uses only years strictly before the year it is applied to. These are the highest-value tests in the repo.
- **Index computation.** Known band values, known expected index. The zonal reduction itself runs in Earth Engine and is checked by an independent Planetary Computer pull on a zone sample, run manually, never in CI.
- **Baseline computation.** Known synthetic time series, known expected residual. Separately: a zone whose crop alternates must produce two baselines, not one, and the leave-one-year-out label baseline must exclude the target year. Both are asserted.
- **CRS assertions.** Mismatched inputs raise rather than silently reproject.
- **Nodata handling.** Masked pixels are excluded, never treated as zero.

Do not test: satellite API responses, visual output, or anything requiring network access in CI.

## 15. Known risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Data acquisition overruns the budget | High | Gate G-0 first; single county; accept smaller AOI over bigger boundary problems |
| Ranker fails to beat persistence null | Moderate | Pre-committed to reporting as primary finding |
| Missed cloud shadow drives false positives | Moderate | Cloud Score+ masking plus S5 persistence |
| CSB merges target fields | Low | Cross-check a sample against Fields of The World |
| Circular evaluation | Low if gap enforced | Mandatory temporal gap, documented, tested |
| Scope drift toward disease ID | Moderate | NG1 is explicit; 10m cannot support it |

## 16. Prior art

Cited rather than obscured.

- **EOSDA Crop Monitoring** — commercial zoning via k-means on a vegetation index into 2 to 7 zones; field prioritisation as a leaderboard sorted by NDVI change. This is baseline B2.
- **Microsoft FarmVibes.AI** — `farm_ai/agriculture/change_detection` identifies outliers over NDVI across dates. Cross-date within-season, not baseline-relative across years. Read as architecture reference; not adopted, as its Docker cluster and YAML DAG framework exceed this project's scope.
- **EOAD (Earth Observation-based Anomaly Detection)**, Burke et al. — within-parcel distributional anomaly thresholds, validated on rice. Closest published analog to the scouting-priority goal. Does not use ranking metrics.
- **AlphaEarth Foundations**, Brown et al. 2025 — 64-dim 10m annual embeddings. Benchmarked at field level by the Stanford/Corteva "Harvesting AlphaEarth" paper for yield, tillage, cover crop. No published evaluation at sub-field anomaly scale.

**Contribution claim:** the detection components exist in prior work. What could not be found is anyone reporting whether such rankings are correct — no precision@k, no false-positive rate, no null comparison. The contribution is the evaluation, not the detection. The claim is framed as "rare and not found" rather than "never done," since it rests on a bounded search.
