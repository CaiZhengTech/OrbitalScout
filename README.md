# OrbitalScout

Rank 10m sub-field zones by how urgently they warrant a physical visit, measured against each zone's own multi-year history.

It answers **where to scout**, never **what is wrong**.

> **Status: pre-build.**
> The specification (`SPEC.md`) and the evaluation protocol it contains were written before any
> data was touched, and are committed here with timestamps to prove it. No results exist yet.
> Every metric in this document is marked `[TBD]` and will be replaced only by measured output.
> There are no estimated, illustrative, or placeholder numbers anywhere in this repository.

---

## The problem

A farmer with a 100 acre field cannot walk all of it. Problems appear in patches, not uniformly. The real question is never "is my field healthy" but "where do I spend the two hours I actually have today."

Existing tools colour a map by vegetation index and leave the interpretation to the user. That is a visualisation, not a recommendation, and it carries no statement about whether the highlighted areas are the right ones to visit.

## The core idea

Ranking zones by **absolute** vegetation index value produces a map of permanent soil structure: the sandy corner, the compacted headland, the low wet spot. Those zones score badly every year for reasons that have nothing to do with an emerging problem, and the farmer already learned where they are twenty years ago. A tool that flags them is reporting the soil map.

The actionable signal is **deviation from a zone's own history**. A zone that is normally fine and is suddenly behind is worth driving out to see. A zone that is always behind is not news.

OrbitalScout ranks zones by that deviation, aligned by accumulated growing degree days rather than by calendar date, and then reports how good that ranking actually is under a fixed scouting budget.

## What this deliberately does not do

- **No disease or pest identification.** At 10m ground sample distance the signal required to distinguish causes is not present. Claiming otherwise would be an overclaim.
- **No yield prediction** in physical units.
- **No real-time operation.** Cadence is governed by cloud-free satellite revisit, typically 8 to 12 days in temperate growing regions. Output updates on each cloud-free pass.
- **No prescription maps** or machine-executable output.
- **No live API or hosted service.** The demo is precomputed and static.
- **No coverage outside the contiguous United States.** Crop labels and soil data are US-specific.

## What is actually being contributed

The detection components already exist in prior work. NDVI zoning is commercially shipped. NDVI change detection exists in Microsoft's FarmVibes.AI. Within-parcel anomaly detection is published as EOAD and validated on rice. See [Prior art](#prior-art).

What a bounded search did not find is anyone reporting whether such rankings are **correct**: no precision@k, no false-positive rate, no comparison against a null model.

**The contribution is the evaluation, not the detection.**

That framing is deliberately smaller than "I built a crop monitoring platform," and it is a great deal more defensible.

## Results

No results yet. This table is the output of the build, not a target.

| Metric | NDVI k-means (B2) | Persistence null (B1) | OrbitalScout |
|---|---|---|---|
| precision@5% | `[TBD]` | `[TBD]` | `[TBD]` |
| precision@10% | `[TBD]` | `[TBD]` | `[TBD]` |
| precision@20% | `[TBD]` | `[TBD]` | `[TBD]` |
| Lift over random @10% | `[TBD]` | `[TBD]` | `[TBD]` |
| False positive rate @10% | `[TBD]` | `[TBD]` | `[TBD]` |

**Lift over the persistence null at k=10% is the headline number.**

### A negative result is pre-committed as valid

The persistence null predicts that every zone behaves exactly as it always has. Because permanent soil structure repeats annually, it is genuinely hard to beat. There is a real chance OrbitalScout does not beat it.

If that happens it is reported as the headline finding, in these words: *permanent soil structure dominates the within-field anomaly signal, and a persistence null was not beaten at k=10%.* The protocol will not be retuned, the baseline will not be dropped, and the project will not be reframed to avoid saying so.

This paragraph exists in the repository before the results do, specifically so that it cannot be quietly removed afterwards.

## How it works

```
Sentinel-2 L2A  --+
Cloud Score+    --|
USDA CSB        --+-->  ingest  -->  zone feature  -->  baseline  -->  signals  -->  rank
USDA CDL        --|    (mask, reproject,   table         (GDD-aligned   (S1..S6)      |
USDA SDA soil   --|     aggregate: once)  (DuckDB over    per zone)                   |
Open-Meteo GDD  --+                        Parquet)                                   |
                                                                                      v
                                                                    evaluate  <-------+
                                                        (precision@k, lift, blocked splits)
                                                                        |
                                                                        v
                                                            static MapLibre demo
```

**Masking, CRS reprojection, and zonal aggregation happen exactly once, at ingestion.** Every signal reads one clean feature table. No signal reimplements any of them, because two competing definitions of "clear observation" would make the persistence signal meaningless.

All spatial data is reprojected once to EPSG:5070 (NAD83 / Conus Albers). CRS equality is asserted before any spatial join, and a mismatch raises rather than silently reprojecting.

### Signals

Six signals, each detecting a physically different failure mode, all sharing one signature:

```python
def score(zone_features: pd.DataFrame, context: Context) -> pd.Series:
    """One score per zone-date."""
```

| ID | Signal | What it catches that the others miss | Ships? |
|---|---|---|---|
| S1 | Temporal anomaly vs the zone's own GDD-aligned history | The baseline signal | `[TBD]` |
| S2 | Spatial anomaly vs neighbouring zones, same date | First-year problems with no history; cancels whole-field effects like regional drought | `[TBD]` |
| S3 | Multi-index divergence across NDVI, NDRE, NDWI | Water stress before visible decline | `[TBD]` |
| S4 | Velocity, the rate of change of S1 | Earlier detection than level-based signals | `[TBD]` |
| S5 | Persistence, run length of consecutive anomalies | Suppresses missed cloud shadow, the dominant false positive | `[TBD]` |
| S6 | Soil-context residual after regressing on SSURGO drainage and slope | Separates "bad because always sandy" from "bad beyond what soil explains" | `[TBD]` |

**Admission rule:** a signal ships only if it measurably improves lift over persistence. Signals that do not are removed from the combination and their null result is recorded in `RESULTS.md`. Building a signal does not entitle it to ship.

### Combination

A deliberate complexity ladder. Each rung must beat the one below it to justify existing.

1. Single signal, sorted. No model, no training.
2. Weighted sum of z-scored signals, sorted. No hyperparameters.
3. LightGBM learning the combination.

If rung 3 does not beat rung 2 it is cut and that is reported. A weighted sum being sufficient is a finding, not a failure.

## Evaluation protocol

Frozen in `SPEC.md` Section 10 before any data was touched.

**Splits are blocked by field AND by year. Never a random split of zones.** Adjacent zones are spatially autocorrelated and are not independent samples; a random zone split leaks neighbouring information into the test set and produces an excellent number that means nothing. This is the same class of error as shared-group leakage in image datasets.

The split function is the most important tested code in the repository. `tests/test_splits.py` asserts that no field appears in both train and test, and that no test year appears in train.

**Circularity control.** A mandatory temporal gap separates the feature window from the label window. Features may not use observations from inside the label window. The gap is configured once and recorded.

**The label is a proxy**, namely end-of-season underperformance of a zone relative to its own multi-year baseline. It is not independent ground truth, and that limitation is stated plainly rather than buried.

### Acceptance gates

| Gate | Condition | If it fails |
|---|---|---|
| G-0 | Median clear observations per season >= 6 for the AOI | Widen phenology bins, add Sentinel-1, or change AOI. **Runs first, before anything else is built.** |
| G-1 | Split function passes leakage tests | Stop. Nothing downstream is valid. |
| G-2 | Ranker beats random at precision@10% | Investigate before proceeding |
| G-3 | Ranker beats the persistence null at precision@10% | **Not required to pass.** Reported as the primary finding either way. |
| G-4 | CDL rotation mismatch below 10% on test fields | Restrict to fields with confirmed stable rotation |

Current gate status: `[TBD]`, none run yet.

## Build order

Strictly sequential. Each step runs end to end before the next begins.

- [ ] **Step 0.** Clear observation count. One county, one season, Cloud Score+ masking, count usable observations per zone. Gate G-0.
- [ ] **Step 1.** Ingestion. STAC pull, masking, CSB boundaries, CDL labels, zone construction, `exactextract` aggregation into DuckDB.
- [ ] **Step 2.** Baseline construction. GDD accumulation, phenology-aligned per-zone history.
- [ ] **Step 3.** Signal S1 alone. Sort by it. No model.
- [ ] **Step 4.** Evaluation harness. Persistence null, NDVI k-means baseline, precision@k, lift, blocked splits. **The project is complete and shippable at this point.**
- [ ] **Step 5+.** One signal at a time. Implement, measure the delta in lift, keep or cut, record the result either way.
- [ ] **Last.** Static MapLibre demo.

Everything after Step 4 is an ablation study. Steps 0 through 4 done well beats all six signals half-finished.

## Scope

| Dimension | V1 |
|---|---|
| Geography | One county, US Corn Belt (Iowa or Illinois) `[TBD]` |
| Crops | Corn and soybean |
| Years | 5 growing seasons minimum, most recent held out |
| Season window | Roughly May through September, bounded by phenology not calendar |
| Zone size | 10m, matching Sentinel-2 native resolution |
| Field definition | USDA Crop Sequence Boundaries polygons |

Crop-specific parameters live in a registry table keyed by CDL code. Adding a crop means adding a row. No crop name appears in a conditional anywhere in the codebase.

## Data sources

All free. Registration requirements are flagged because they gate the start of work.

| Purpose | Source | Access | Registration |
|---|---|---|---|
| Optical time series | Sentinel-2 L2A | Planetary Computer STAC, `pystac-client` + `odc-stac` | No |
| Cloud and shadow masking | Cloud Score+ | Earth Engine `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | Earth Engine |
| Field polygons | USDA Crop Sequence Boundaries | Source Cooperative `fiboa/us-usda-cropland`, GeoParquet | No |
| Crop labels | USDA Cropland Data Layer | CropScape REST or Earth Engine | No |
| Multi-year zone prior | AlphaEarth Satellite Embedding | Earth Engine `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` | Earth Engine |
| Drainage class, slope | USDA Soil Data Access | POST to SDMDataAccess | No |
| Daily temps for GDD | Open-Meteo Historical | `archive-api.open-meteo.com` | No |

Known constraints, stated rather than assumed away:

- **CDL is released the following February**, so in-season crop type comes from the prior year. The rotation mismatch rate is measured on the test fields, not assumed (gate G-4).
- **AlphaEarth is annual** and cannot supply in-season signal. It is a multi-year zone prior only.
- **CSB polygons are synthetic field units**, not legal parcels. Adjacent same-crop fields not separated by a road or rail line may merge.

## Stack

DuckDB over Parquet, local, CPU only. The full modelling dataset is single-digit GB and fits on a laptop.

Chosen for join ergonomics at small scale, not for scale itself: the joins across five years of zone-level data are cleaner in SQL, and DuckDB reads Parquet directly with no server.

Deliberately not used: PostGIS, Spark, Sedona, Docker, Kubernetes, any workflow orchestrator, any backend API, any frontend framework. The pipeline is five linear stages in a Makefile, run on demand. An orchestrator would be infrastructure for a scheduling problem that does not exist here.

## Repository layout

```
orbitalscout/
  config.py         AOI, years, CRS, paths, thresholds. One place.
  crops.py          crop registry table loader
  ingest/           stac, masking, boundaries, cdl, soil, weather, embeddings
  zones.py          zone construction, inward buffer
  features.py       indices, exactextract zonal aggregation
  baseline.py       phenology-aligned per-zone historical baseline
  signals.py        six functions, one shared signature
  rank.py           combination and sort
  baselines.py      persistence null, NDVI k-means
  evaluate.py       precision@k, lift, splits
  export.py         precomputed GeoJSON for the demo
tests/
  test_splits.py    leakage tests. The most important tests in the repo.
  test_zonal.py     zonal aggregation against a known synthetic raster
  test_baseline.py  baseline against a known synthetic series
demo/
  index.html        MapLibre, one file, no backend
Makefile            five linear stages
```

## Documents

| File | What it is |
|---|---|
| `SPEC.md` | What gets built. Contains the frozen evaluation protocol (Section 10). |
| `DESIGN.md` | Why, and what was rejected. Decision records D1 through D14. |
| `CLAUDE.md` | The operating agreement: hard rules, build order, what not to build. |
| `RESULTS.md` | Measured outcomes, including null results. `[TBD]` |

## Prior art

Cited rather than obscured.

- **EOSDA Crop Monitoring.** Commercial zoning via k-means on a vegetation index into 2 to 7 zones, with field prioritisation as a leaderboard sorted by NDVI change. This is baseline B2.
- **Microsoft FarmVibes.AI.** `farm_ai/agriculture/change_detection` identifies NDVI outliers across dates. Cross-date within-season, not baseline-relative across years. Read as an architecture reference and not adopted, since its Docker cluster and YAML DAG framework exceed this project's scope.
- **EOAD (Earth Observation-based Anomaly Detection)**, Burke et al. Within-parcel distributional anomaly thresholds, validated on rice. The closest published analog to the scouting-priority goal. Does not use ranking metrics.
- **AlphaEarth Foundations**, Brown et al. 2025. 64-dimensional 10m annual embeddings, benchmarked at field level by the Stanford/Corteva "Harvesting AlphaEarth" paper for yield, tillage, and cover crop. No published evaluation at sub-field anomaly scale.

The claim here is framed as "rare and not found in a bounded search" rather than "never done."

## Getting started

`[TBD]`. Nothing is runnable yet. Setup instructions land with Step 0.

## License

`[TBD]`
