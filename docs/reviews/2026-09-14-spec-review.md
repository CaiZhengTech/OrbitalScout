# Spec review, 2026-09-14

Pre-data architectural review of `SPEC.md` v0.1 and `DESIGN.md`. Conducted before Step 0 ran and before any satellite data was pulled. Committed so the record shows these concerns were raised, and the resulting protocol changes were made, while the evaluation protocol could still be changed honestly.

Findings are ranked by how badly each would hurt if discovered at Step 4 instead of now. Each finding states what was done about it and in which commit.

---

## 1. The persistence null as written cannot produce a ranking

SPEC 10 defined B1 as "predicts each zone behaves exactly as it always has. Zero anomaly everywhere." A constant score ranks nothing; precision@k against it is the random baseline under a different name. The same paragraph said B1 is "hard to beat because permanent soil structure repeats annually," which describes a different null: rank zones by their multi-year mean index, worst first. That second definition is the soil map and is the one the design intends.

**Resolution.** B1 is now defined as: rank zones within a field by their multi-year mean index in ascending order, computed from prior years only. SPEC 10, Baselines.

## 2. Precision@k needs a binary label; the spec had a continuous one

"End-of-season underperformance relative to own baseline" is a residual. Precision@k requires a threshold that turns it into anomalous or not. That threshold sets the base rate, which sets lift over random, which is a headline metric. It was unspecified.

The two natural choices behave very differently. A within-field quantile label ("bottom 10% of residuals") forces exactly that fraction of every field to be anomalous in every year, including benign years where nothing is wrong. That is false by construction and makes lift over random at k=10% a tautology with a ceiling of 10. A threshold against the zone's own historical variability lets the base rate be a measured quantity that varies by field and year.

**Resolution.** A zone-year is labelled underperforming when its end-of-season residual is below minus one standard deviation of that zone's own residual history. The base rate is measured and reported per field-year, never assumed. SPEC 10, Ground truth.

**Consequence.** Per-zone standard deviation from a handful of seasons is poorly estimated. This is the direct motivation for findings 4 and 6.

## 3. The split test as described tested the wrong layer

SPEC 14 said `test_splits.py` asserts "no field appears in both train and test." Implemented literally, that deletes the test fields' prior-year rows, and the per-zone baseline for a test-field zone must be built from exactly those rows. That is not leakage; it is the feature.

The distinction that matters: field-and-year blocking applies to everything that is **fit** on data (z-score statistics, rung-2 weights, k-means, the label threshold, LightGBM). The per-zone baseline is not fit. It is computed from one zone's own history and needs only a **temporal** guarantee: strictly prior years, never the target year, never the label window. The originally described test would pass while the actual leakage channel, z-scoring on statistics that include the test year, went undetected.

**Resolution.** Two tests, not one. Fit-sets are blocked by field and by year. Baselines and every other per-zone feature use only years strictly before the target year. SPEC 10, Splits; SPEC 14; DESIGN D8 amended.

## 4. One held-out year is an anecdote, and a four-year baseline is thin

"Most recent year held out" gives one test season. If it was benign, anomalies are rare, the base rate is tiny, and precision@k is noise. With five seasons total, the held-out year has a four-year baseline behind it, and per-zone variance from four observations is barely a number.

Sentinel-2 L2A covers the study region from 2017. The marginal cost of additional seasons is bandwidth, not design.

**Resolution.** All seasons with Sentinel-2 L2A coverage are ingested. The year holdout rolls across the last three seasons and results are reported as a spread, not a point. SPEC 3; SPEC 10, Splits.

## 5. Two-platform ingestion was the most fragile piece and had no decision record

Pixels from Planetary Computer via `odc-stac`; cloud mask from Google Earth Engine via export. Two platforms, two grids, pixel-exact co-registration required, GEE export quota consumed for every scene across every season. DESIGN D9 chose Cloud Score+ but never discussed the platform split it forces.

The project is already committed to GEE for Cloud Score+ and AlphaEarth. Using it fully removes the split: `COPERNICUS/S2_SR_HARMONIZED` joined to Cloud Score+ by `system:index`, mask applied in the same expression, zonal reduction in GEE, one table of zone-date-index exported. That deletes `odc-stac`, `exactextract`, and every local raster from the core path, and makes "one definition of clear observation" literally one line of code. Step 0 becomes a `reduceRegions` count.

The cost is deeper dependence on Google and on GEE export limits. Both were already accepted.

**Resolution.** Ingestion moves to GEE end to end. Planetary Computer becomes the cross-check source only. SPEC 4; SPEC 11; DESIGN D15 added.

## 6. 10m zones and exactextract did not fit together, and 10m is probably too small

If a zone is one pixel, fractional coverage weights are 1.0 everywhere except the edge already removed by the inward buffer, so `exactextract` contributes nothing. Separately, Sentinel-2 carries roughly one pixel of co-registration jitter between passes (reduced by the 2021 reprocessing, not eliminated). At 10m a zone's multi-year series is partly its neighbour's. Signals S2 and S5 exist partly to fight that noise. A 3x3 block (30m, about a tenth of a hectare) is closer to what a person walks to, averages the jitter down, and makes the per-zone standard deviation in finding 2 estimable.

**Resolution.** Zone size is a configuration parameter, not a constant. Step 0 measures year-over-year variance of stable zones at 10m and 30m and the choice is made from that measurement, recorded in `RESULTS.md`. SPEC 6; CLAUDE.md Step 0; DESIGN D16 added.

## 7. The commercial comparison is disadvantaged by construction and must say so

The primary label is a residual. B2 (NDVI k-means) ranks by absolute level and is therefore designed to lose against it; it answers a different question. Reporting that lift as a win would be misleading.

**Resolution.** A secondary label is added: absolute end-of-season underperformance, the bottom decile of raw index within field. B2 is expected to do well on it. Both labels are reported for every method. The gap between them is the thesis, stated as a measurement rather than an argument. SPEC 10, Ground truth and Metrics.

## 8. AlphaEarth had no consumer

Ingested as a "zone prior" but not one of the six signals and absent from the rung-2 weighted sum. Under the project's own deletion test it breaks nothing before rung 3.

**Resolution.** Deferred until rung 3 is reached. Not ingested before then. SPEC 4; SPEC 11.

---

## Open items, recorded with a target step

These need decisions that are better made with the pipeline in front of us. They are recorded here so they are not forgotten and so the eventual decision can be checked against the concern.

**9. Planting date is unspecified, and the phenology claim depends on it.** GDD accumulates from planting. The registry holds a planting window, not a per-field-year date. A fixed window start yields calendar-plus-temperature, not phenology. Green-up detection from the NDVI curve is the standard fix and introduces a threshold. Decide at Step 2, with a decision record.

**10a. Prior-year CDL is a deployment constraint, not an evaluation one.** For a retrospective evaluation the actual-year CDL exists for every season. Use it for labels; report the prior-year mismatch rate (gate G-4) separately as a deployability number. Decide at Step 1.

**10b. Label and feature baselines share estimation error.** The temporal gap separates observation windows but not the baseline term both sides divide by. A leave-one-year-out baseline for the label alone would close that channel. Decide at Step 2 alongside item 9, since both touch `baseline.py`.

---

## What this review did not change

The problem statement, the goals and non-goals, the residual-anomaly framing (D1), the ranking formulation (D2), the persistence null as the headline comparison (D3), the crop registry (D4), GDD alignment (D5), sequential signal admission (D6), the complexity ladder (D7), the static demo (D12), DuckDB (D13), and no orchestrator (D14). The negative-result pre-commitment stands unchanged.
