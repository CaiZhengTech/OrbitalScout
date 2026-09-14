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
| Geography | One county, US Corn Belt (Iowa or Illinois) |
| Crops | Corn and soybean |
| Years | 5 growing seasons minimum; most recent year held out |
| Season window | Roughly May through September, bounded by phenology not calendar |
| Zone size | 10m, matching Sentinel-2 native resolution |
| Field definition | USDA Crop Sequence Boundaries polygons |

## 4. Data sources

All sources are free. Registration requirements are flagged because they gate the start of work.

| Source | Purpose | Access | Registration |
|---|---|---|---|
| Sentinel-2 L2A | In-season optical time series | STAC: Microsoft Planetary Computer `sentinel-2-l2a` via `pystac-client` + `odc-stac`, with `planetary_computer.sign` | No |
| Sentinel-2 L2A (alt) | Fallback / cross-check | Element84 `https://earth-search.aws.element84.com/v1`, collection `sentinel-2-c1-l2a` | No |
| Cloud Score+ | Cloud and shadow masking | Earth Engine `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | Earth Engine |
| USDA Crop Sequence Boundaries | Field polygons | GeoParquet mirror, Source Cooperative `fiboa/us-usda-cropland` | No |
| USDA Cropland Data Layer | Crop type labels | CropScape REST, or Earth Engine `USDA/NASS/CDL` | No |
| AlphaEarth Satellite Embedding | Multi-year zone prior | Earth Engine `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` | Earth Engine |
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

A zone is a 10m grid cell whose centroid falls inside a CSB field polygon, after an inward buffer of one pixel to exclude boundary-contaminated pixels.

Zonal aggregation uses `exactextract` with fractional pixel coverage weights. Centroid-based or all-touched aggregation is not acceptable at this pixel size.

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

End-of-season underperformance of a zone relative to its own multi-year baseline.

**Circularity control:** a mandatory temporal gap separates the feature window from the label window. Features may not use observations from within the label window. The gap is configured once and recorded.

This proxy is not independent ground truth and the limitation is stated plainly in results. Where a documented damage event overlaps the AOI (for example the August 2020 Iowa derecho, for which USDA NASS published a damage polygon layer), it is used as a qualitative case-study check, not as the primary label.

### Splits

- Held out by **year** and by **field**. Both.
- Never a random split of zones or pixels. Adjacent zones are spatially autocorrelated and are not independent samples.
- Implemented as `GroupKFold` grouped by field, with year holdout applied independently.

The split function is unit tested. A test asserts that no field appears in both train and test, and that no test year appears in train.

### Metrics

- Primary: **precision@k** at k = 5%, 10%, 20% of field area.
- **Lift over random** = precision@k divided by base rate.
- **Lift over persistence null** — the headline number.
- **Lift over NDVI k-means baseline** — the commercial comparison.
- False positive rate at each k.

### Baselines

- **B1, persistence null.** Predicts each zone behaves exactly as it always has. Zero anomaly everywhere. Hard to beat because permanent soil structure repeats annually. This is the honesty check.
- **B2, NDVI k-means.** k-means on a vegetation index into 2 to 7 zones, matching what commercial platforms ship. Rank zones by cluster mean.

### Acceptance gates

| Gate | Condition | Action if failed |
|---|---|---|
| G-0 | Median clear observations per season ≥ 6 for the AOI | Widen phenology bins, add Sentinel-1, or change AOI. **Run this first, before anything else.** |
| G-1 | Split function passes leakage unit tests | Stop. Nothing downstream is valid. |
| G-2 | Ranker beats random at precision@10% | Investigate before proceeding |
| G-3 | Ranker beats persistence null at precision@10% | Not required to pass. If failed, report as the primary finding: permanent soil structure dominates the anomaly signal. |
| G-4 | CDL rotation mismatch below 10% on test fields | Restrict to fields with confirmed stable rotation |

**G-3 is not a pass/fail gate on the project.** A well-characterised negative result is a valid and reportable outcome. The failure mode to avoid is discovering a negative result and quietly reframing the project to hide it.

## 11. Module layout

Flat and boring. No plugin architecture, no registry pattern, no abstract base classes.

```
orbitalscout/
  config.py           # AOI, years, CRS, paths, thresholds. One place.
  crops.py            # crop registry table loader
  ingest/
    stac.py           # Sentinel-2 via pystac-client + odc-stac
    masking.py        # Cloud Score+ clear-observation determination
    boundaries.py     # CSB field polygons
    cdl.py            # crop labels
    soil.py           # SDA queries
    weather.py        # Open-Meteo, GDD accumulation
    embeddings.py     # AlphaEarth export handling
  zones.py            # zone construction, inward buffer
  features.py         # indices, exactextract zonal aggregation
  baseline.py         # phenology-aligned per-zone historical baseline
  signals.py          # six functions, one shared signature
  rank.py             # combination and sort
  baselines.py        # persistence null, NDVI k-means
  evaluate.py         # precision@k, lift, splits
  export.py           # precomputed GeoJSON for the demo
tests/
  test_splits.py      # leakage tests. The most important tests in the repo.
  test_zonal.py       # zonal aggregation correctness
  test_baseline.py    # baseline computation
demo/
  index.html          # MapLibre, one file
Makefile              # the pipeline. Five linear steps. Not an orchestrator.
```

### Shared-once rule

Cloud masking, CRS reprojection, and zonal aggregation are applied **once during ingestion**, producing a clean feature table that all signals read. No signal may reimplement any of them. Two definitions of "clear observation" would make S5 meaningless.

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

- **Split logic.** Field appears in exactly one of train/test. Test years absent from train. This is the highest-value test in the repo.
- **Zonal aggregation.** Known synthetic raster and polygon, known expected fractional-weight result.
- **Baseline computation.** Known synthetic time series, known expected residual.
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
