# CLAUDE.md — OrbitalScout V1

Read `SPEC.md` and `DESIGN.md` before writing code. This file is the operating agreement on top of them.

---

## What this project is

Rank 10m sub-field zones by anomalous underperformance relative to each zone's own multi-year, phenology-aligned history, and measure that ranking against a commercial NDVI k-means baseline and a persistence null.

It answers **where to scout**, never **what is wrong**.

## Who you are working with

A new-grad software engineer building this as a portfolio project. They must be able to defend every architectural decision in an interview **without notes**. This constrains how you should work:

- **Prefer fewer lines they understand over more lines that work.** Code they cannot explain is worse than no code.
- **When you make a non-obvious choice, say why in one sentence**, in the commit or in a comment. Not a tutorial, one sentence.
- **Do not generate large amounts of code at once.** Small, reviewable increments.
- **If they ask for something that contradicts the spec, say so** before doing it. Do not silently comply.

They have asked to be told when they are being redundant, and prefer directness over agreement.

---

## Hard rules

These are not preferences. Violating them invalidates the project.

### 1. Never random-split zones or pixels

Splits are held out by **field AND year**. Adjacent zones are spatially autocorrelated and are not independent samples. A random split will produce excellent numbers that mean nothing.

If you write a split, `tests/test_splits.py` must assert two things: no field used to fit anything appears in the test set and no test year appears in any fit-set; and every baseline value uses only years strictly before the year it is applied to. The per-zone baseline is a feature, not a fit, and is governed by the temporal rule only. Write the tests first.

### 2. Never invent a number

No placeholder metrics. No "approximately X%" in a README. No example accuracy figures in docstrings that could be mistaken for results. Every number in any document is either measured or marked `[TBD]`.

This project exists partly as a reaction to portfolio repos that publish headline metrics with no evaluation behind them. Do not reproduce that pattern.

### 3. Cloud masking, CRS reprojection, and zonal aggregation happen once, at ingestion

All signals read a single clean feature table. No signal may reimplement any of these. Two definitions of "clear observation" would make the persistence signal meaningless.

### 4. All spatial data is EPSG:5070

Reprojected once, at ingestion. Assert CRS equality before any spatial join. A mismatch raises. Never silently reproject at join time.

Categorical rasters (CDL) use nearest-neighbour resampling only.

### 5. No crop name in a conditional

Crop-specific knowledge lives in the crop registry table keyed by CDL code. Adding a crop means adding a row. If you find yourself writing `if crop == "corn"`, stop and move it to the registry.

### 6. Masked pixels are nodata, never zero

Treating a masked pixel as zero silently corrupts every downstream statistic.

### 7. The evaluation protocol is frozen

`SPEC.md` Section 10 was written before any data was touched. Do not revise it after seeing results. If it needs to change, that is a conversation with the user, flagged explicitly, not an edit.

---

## Build order

Strictly sequential. Do not start a step before the previous one runs end to end.

**Step 0 — Clear observation count. DONE 2026-09-14.** G-0 passed: median 25 clear observations per season against a threshold of 6, across 2017 to 2025. Three findings changed the design: 2017 excluded as single-satellite, the AOI restricted to the region under both relative orbits, and crop stratification dropped in favour of a within-field relative baseline. See `RESULTS.md` and `docs/reviews/2026-09-14-baseline-depth-decision.md`. Zone size moved into Step 1.

**Step 1 — Ingestion.** CSB boundaries, zone construction, CDL labels, one Earth Engine expression that masks and zonally reduces every season into a zone-date-index table, export, load into DuckDB. Export the zone table at **both 10m and 30m**: the same expression emits both at negligible extra cost, and the zone-size comparison is then made on the within-field relative quantity rather than guessed beforehand. This is the longest step. Expect it to take most of the first week.

**Step 2 — Baseline construction.** GDD accumulation, phenology-aligned per-zone historical baseline.

**Step 3 — Signal 1 alone.** Temporal anomaly. Sort by it. No model.

**Step 4 — Evaluation harness.** Persistence null, NDVI k-means baseline, precision@k, lift, blocked splits. **At this point the project is complete and shippable.**

**Step 5 onward — one signal at a time.** S2, then S3, then S4, S5, S6. Each one: implement, measure the delta in lift over persistence, keep or cut. Record the result either way.

**Last — demo.** Static export, MapLibre, single HTML file.

The project is shippable after step 4. Everything after is an ablation study. If time runs out, having steps 0 through 4 done well beats having all six signals half-finished.

---

## Signal admission rule

A signal ships only if it measurably improves lift over persistence.

If a signal does not help, **remove it from the combination and record the null result in `RESULTS.md`**. Do not keep it because it was built. Do not keep it because it seems like it should help.

"S4 velocity did not improve lift over persistence and was cut" is a finding worth reporting.

---

## Architecture constraints

### Do not build

- Abstract base classes for signals. Six functions with the same signature and a list is correct.
- A plugin architecture, registry pattern, or config-driven signal pipeline.
- An orchestration framework. A Makefile with five linear stages is the right answer.
- A backend API. The demo is precomputed and static.
- A frontend framework. One HTML file with MapLibre and a slider.
- Docker or Kubernetes. Not this project.
- PostGIS, Spark, or Sedona. The dataset is single-digit GB.

If you find yourself writing an abstract base class, you have gone wrong.

### Signal interface

All six signals share one signature:

```python
def score(zone_features: pd.DataFrame, context: Context) -> pd.Series:
    """One score per zone-date."""
```

No signal may require a special branch in the orchestrator. If one does, reshape the signal.

### Complexity ladder for combination

1. Single signal, sorted
2. Weighted sum of z-scored signals, sorted
3. LightGBM

Each rung must beat the previous on held-out precision@k. If LightGBM does not beat the weighted sum, cut it and report that. Rungs 1 and 2 require no training.

---

## Testing

Test what fails silently. Skip what fails loudly.

**Test:**
- Split logic (highest value in the repo)
- Index computation against known band values
- Baseline computation against a known synthetic time series
- CRS mismatch raises
- Nodata handling

**Do not test:**
- Satellite API responses
- Visual output
- Anything requiring network access in CI

---

## Language and framing

- **Never use the phrase "real time."** Cadence is governed by cloud-free satellite revisit, typically 8 to 12 days. Say "updated on each cloud-free pass" or "periodic batch."
- **Never claim disease or pest identification.** The system says where to look, not what is wrong. 10m resolution cannot support cause identification.
- **Never claim novelty for the detection.** The detection components exist in prior work (EOSDA, FarmVibes.AI, EOAD). The contribution is the evaluation. Prior art is cited in `SPEC.md` Section 16 and should be cited in the README.
- **No em dashes in generated documentation or comments.** User preference.

---

## If the ranker does not beat the persistence null

The null that matters is **B1b, anomaly persistence**: rank zones by last year's residual. Beating B1a, level persistence, on the primary label proves nothing, because the label subtracts the level B1a ranks on. Do not report lift over B1a on the primary label as a win.

This is a plausible outcome, roughly one chance in three, and it is pre-committed as a valid result.

Do not: retune until the number improves, quietly change the evaluation, drop the persistence baseline, or reframe the project to avoid reporting it.

Do: report it as the headline finding. "Permanent soil structure dominates the within-field anomaly signal; a persistence null was not beaten at k=10%." Then investigate why, and write that up.

A well-characterised negative result is a stronger portfolio artifact than a suspiciously high precision@k.

---

## Data source quick reference

| Purpose | Source | Access |
|---|---|---|
| Sentinel-2 L2A | Earth Engine `COPERNICUS/S2_SR_HARMONIZED` | Joined to Cloud Score+ by `system:index`; Planetary Computer retained as cross-check only |
| Cloud masking | Cloud Score+ | GEE `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` |
| Field polygons | USDA CSB | Source Cooperative `fiboa/us-usda-cropland`, GeoParquet |
| Crop labels | USDA CDL | CropScape REST or GEE `USDA/NASS/CDL` |
| Zone prior | AlphaEarth (rung 3 only) | GEE `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` |
| Soil | USDA SDA | POST `https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest` |
| Weather / GDD | Open-Meteo | `https://archive-api.open-meteo.com/v1/archive` |

Gotchas: CDL is released the following February, so in-season crop type uses the prior year. AlphaEarth is annual and cannot supply in-season signal. CSB polygons are synthetic field units, not legal parcels.

---

## The test to apply to any component

**If I delete this, what specifically breaks, and how would I notice?**

If the answer is "nothing" or "I would not notice," delete it.

If the answer is "the numbers get quietly better and I would never know they were wrong," it is load-bearing and needs a test.
