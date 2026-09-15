# OrbitalScout V1 — Design Document

Companion to `SPEC.md`. The spec says what is built. This says why, and what was rejected.

Every decision here should be defensible out loud, without notes, under follow-up questioning.

---

## 1. The problem, plainly

A farmer with a 100-acre field cannot walk all of it. Problems appear in patches, not uniformly. The real question is never "is my field healthy" but "where do I spend the two hours I actually have today."

Existing tools show a coloured map of vegetation index values and leave interpretation to the user. That is a visualisation, not a recommendation, and it carries no statement about whether the highlighted areas are the right ones to visit.

## 2. The core insight

Ranking zones by **absolute** vegetation index value produces a map of permanent soil structure: the sandy corner, the compacted headland, the low wet spot. Those zones score badly every year, for reasons that have nothing to do with an emerging problem, and the farmer already knows about them. A tool that flags them is telling the user something they learned twenty years ago.

The actionable signal is **deviation from a zone's own history**. A zone that is normally fine and is suddenly behind is worth driving out to see. A zone that is always behind is not news.

This single reframe drives most of the rest of the design.

## 3. Decision records

### D1. Residual anomaly, not absolute level

**Decision.** Rank by deviation from the zone's own phenology-aligned multi-year baseline.

**Rejected: absolute vegetation index level.** Reproduces the soil map. Trivially high apparent accuracy, near-zero user value.

**Consequence.** Requires multi-year history per zone, which sets the minimum data acquisition scope at roughly five seasons.

**The follow-up question this invites:** "Why not just predict which zones are low?" Answer: because the farmer already knows which zones are low, and a model that predicts it is measuring soil type, not crop stress.

---

### D2. Ranking problem, not classification

**Decision.** Output is an ordered list under a scouting budget. Evaluation uses precision@k, lift over random, lift over baselines.

**Rejected: pixel classification with accuracy or F1.** This is the field's default and it answers the wrong question. The user cannot inspect every flagged pixel; they can inspect a fixed fraction of the field. The metric should match the constraint.

**Consequence.** Requires a ranking evaluation harness, which is uncommon in this domain and is the main novelty claim.

---

### D3. Persistence null as the headline baseline

**Decision.** The primary comparison is against a model predicting every zone behaves exactly as it always has.

**Rationale.** Because permanent soil structure repeats annually, persistence is genuinely hard to beat. Most published work in this space compares against random or against nothing. Beating persistence is the only evidence that something was actually found.

**Consequence.** Meaningful probability of a negative result. Accepted deliberately.

**Pre-commitment.** If the ranker does not beat persistence, that becomes the reported headline finding: permanent soil structure dominates the within-field anomaly signal. This is written down before results exist specifically so it cannot be quietly reframed afterwards.

**Correction (2026-09-14 council review).** "Persistence" is two different nulls depending on the label. Ranking by multi-year level is the right null for an absolute label and is structurally unable to win against a residual label, which subtracts the level. Ranking by prior-year residual is the right null for a residual label and is the one that is genuinely hard to beat. Both are now specified, as B1a and B1b, and a prediction about B1a is pre-registered in `SPEC.md` Section 10. See `docs/reviews/2026-09-14-council-label-review.md`.

**Refinement (2026-09-14, after Step 0).** B1b is the residual in the most recent prior year with the **same crop**, not simply the prior year. Step 0 measured a crop change across 82% of consecutive year pairs, so under a rotation the prior year is the other crop. If a zone-by-crop interaction exists, last year's residual is anti-informative about a crop-specific recurrence, which would handicap the null again by a different route. See `docs/reviews/2026-09-14-baseline-depth-decision.md`.

---

### D4. Crop-agnostic by construction; crop knowledge as data

**Decision.** The method compares each zone to itself, which is inherently crop-agnostic. Crop-specific knowledge lives in a registry table keyed by CDL code.

**Rejected: a lookup table of acceptable vegetation index ranges per crop.** Scientifically unsupportable. Index values are not comparable across sensors, soil backgrounds, planting dates, regions, or growth stages, and indices saturate at different canopy heights. Publishing such a table would mean inventing numbers.

**Rejected: branching code per crop.** Violates DRY and does not scale past two crops.

**Consequence.** Adding a crop means adding a row. No crop name may appear in a conditional.

---

### D5. Phenology alignment via growing degree days

**Decision.** Align the temporal baseline by accumulated GDD rather than calendar day of year.

**Rationale.** Two zones at the same calendar date may be at different growth stages because of planting date or local temperature. Comparing them on the calendar introduces a difference that is not stress.

**Rejected: double-logistic or Savitzky-Golay curve fitting (TIMESAT-style).** Standard in land surface phenology literature, but finicky with cloud gaps and disproportionate to the timeline.

**Rejected: dynamic time warping.** Most sophisticated option, clearly overkill.

**Known weakness.** Soybean development is strongly photoperiod and maturity-group driven and there is no authoritative GDD-per-stage table. Soybean alignment is weaker than corn. Stated in results, not hidden.

---

### D6. Six signals, added one at a time

**Decision.** Six independent signals, each detecting a physically different failure mode, but built and admitted sequentially with measured deltas.

**Rationale.** More signals from the same free data is the only way to be more comprehensive without acquiring hardware or paid platforms. But six signals built simultaneously is a mess nobody can defend. Six signals added one at a time, each with a measured improvement, is an ablation study.

**Admission rule.** A signal ships only if it measurably improves lift over persistence. Otherwise it is removed and its null result recorded.

**The question this must survive:** "Which signal is doing the work?" If that cannot be answered with numbers, the design has failed regardless of overall performance.

**Cost acknowledged.** More signals means more opportunities to fire, which means more false positives. An alerting system that flags a third of the field is worse than useless because the user stops reading it. Precision@k is what keeps this honest.

---

### D7. Complexity ladder for combination

**Decision.** Single signal sorted, then weighted sum of z-scores, then LightGBM. Each rung must beat the previous.

**Rationale.** With six features and limited field-years, a linear combination is often hard to beat. Using a gradient boosting model because models look serious is resume-driven development.

**Consequence.** LightGBM may be cut. "A weighted sum was sufficient" is a finding, not a failure, and it removes the need for training-time cross-validation machinery.

---

### D8. Splits blocked by field and year

**Decision.** Hold out by both field and year. Never a random split of zones.

**Rationale.** Adjacent zones are spatially autocorrelated and are not independent samples. A random zone split leaks neighbouring information into the test set and produces a beautiful number that means nothing.

**Precedent.** This is the same class of error as shared-group leakage in image datasets, where multiple views of one physical object are split across train and test. Same lesson, different domain.

**Consequence.** The split function is the most important tested code in the repo.

**Refinement (2026-09-14 review).** Blocking governs what is fit. The per-zone baseline is a feature computed from one zone's own prior years and is subject to a temporal rule, not a field rule. A literal "no field in both sets" test would delete the history the baseline needs while missing the real leakage channel, which is fitting z-score statistics on the test year. See `docs/reviews/2026-09-14-spec-review.md`, finding 3.

---

### D9. Cloud Score+ masking, plus persistence as backstop

**Decision.** Mask with Cloud Score+ rather than the SCL band alone. S5 persistence acts as a second line of defence.

**Rationale.** Cloud shadow is the dominant false-positive source for this design, and it is the thing SCL handles worst. A single-date anomaly is very often a missed shadow; an anomaly holding across four consecutive clear observations is much more likely to be real.

**Consequence.** S5 depends on a single shared definition of "clear observation," which is why masking must be applied once during ingestion and never reimplemented per signal.

---

### D10. USDA Crop Sequence Boundaries for field polygons

**Decision.** Use CSB.

**Rejected: USDA Common Land Unit.** Legally restricted from public release since 2008. Not obtainable.

**Rejected: rolling our own CDL connected-components segmentation.** The USDA already did this and published it as CSB, including road and rail network injection to split merged same-crop fields, which is the main failure mode of the naive approach.

**Cross-check.** Sample against Fields of The World to confirm polygons cut the target fields sensibly.

**Known limitation.** CSB polygons are synthetic remote-sensing field units, not legal parcels.

---

### D11. AlphaEarth as prior, not as time series

**Decision.** Use AlphaEarth embeddings as a multi-year per-zone context feature. In-season signal comes from native Sentinel-2.

**Rationale.** The public AlphaEarth product is annual. It cannot supply within-season velocity or phenology-aligned deviation. Claiming otherwise would be an overclaim.

**Upside.** Embeddings are precomputed, so there is no GPU inference step. This is the decision that keeps compute cost at zero.

---

### D12. Static precomputed demo

**Decision.** No backend. Precomputed GeoJSON, MapLibre, single HTML file, static hosting.

**Rejected: a live API.** Introduces hosting, cold starts, and a thing that breaks in six months when a free tier lapses. A demo that returns an error when a recruiter finally clicks it is worse than no demo.

**Rejected: a heatmap-only demo.** A coloured severity map looks identical to what commercial tools already ship and makes the actual contribution invisible. The side-by-side comparison with a budget slider makes the comparison itself the demo.

**Consequence.** The demo cannot and must not claim real-time operation.

---

### D13. DuckDB over Parquet

**Decision.** Local DuckDB as the feature store.

**Rationale.** The full dataset is single-digit GB. Joins across five years of zone-level data are cleaner in SQL, and DuckDB reads Parquet directly with no server.

**Rejected: PostGIS plus a tile server.** Correct architecture for an interactive web application with live spatial queries. This project has no live queries.

**Rejected: Spark or Sedona.** Cluster tooling for a laptop-sized dataset.

**Honest note.** Part of DuckDB's appeal is that it is recognisable on a resume. That is a legitimate secondary reason as long as the primary reason holds independently, which it does.

---

### D14. No orchestrator

**Decision.** A Makefile with five linear stages. No Prefect, Dagster, or Airflow.

**Rationale.** The DAG is linear and runs on demand. An orchestrator would be infrastructure for a scheduling problem that does not exist here.

**Interview framing.** "I chose not to add an orchestrator because the pipeline is five linear steps run on demand" is a better answer than having added one and being unable to say why.

---

### D15. Ingestion lives entirely in Earth Engine

**Decision.** Sentinel-2 pixels, the Cloud Score+ mask, and zonal reduction all run in one Earth Engine expression. One table of zone-date-index is exported. Local code starts at DuckDB.

**Rejected: pixels from Planetary Computer, mask from Earth Engine.** Two platforms, two grids, pixel-exact co-registration required, export quota consumed for every scene. The most fragile piece of the original design, and it had no decision record.

**Rationale.** The project was already committed to Earth Engine for Cloud Score+ and AlphaEarth. Using it fully removes the split and makes "one definition of clear observation" literally one line.

**Cost.** Deeper dependence on Google and on export limits. Both were already accepted. Planetary Computer is retained as an independent cross-check on a sample of zones.

Raised in `docs/reviews/2026-09-14-spec-review.md`, finding 5.

---

### D16. Zone size is measured, not assumed

**Decision.** Zone side length is a configuration parameter. Step 0 measures year-over-year variance of stable zones at 10m and 30m on a sample of fields across all seasons, and the choice is recorded in `RESULTS.md`.

**Rejected: 10m as a constant.** Sentinel-2 carries roughly one pixel of co-registration jitter between passes. At 10m a zone's multi-year series is partly its neighbour's, and the per-zone standard deviation the primary label depends on becomes hard to estimate. A 3x3 block is also closer to what a person actually walks to.

**Consequence.** `exactextract` is no longer needed; aggregation is a masked mean inside the Earth Engine expression.

Raised in `docs/reviews/2026-09-14-spec-review.md`, finding 6.

---

### D17. The baseline is within-field relative, not absolute

**Decision.** A zone's baseline is its typical standing relative to its own field in the same year, pooled across all prior years regardless of crop. Formulas in `SPEC.md` Section 8.

**Rejected: a crop-stratified absolute baseline.** Adopted in the morning of 2026-09-14 and removed the same day once Step 0 measured the rotation. Crop changes across 82% of consecutive year pairs, which left two to four seasons per zone-crop and only two or three for the earliest held-out year. A mean of two seasons is not a baseline; one unusual year is half of it.

**Rationale.** Crop is a property of the field-year, not of the zone. Corn Belt fields rotate as whole units, so within a field-year every zone shares one crop, one weather record, one planting date and one management regime. Measuring each zone against its own field in the same year cancels all of them simultaneously, and the quantity that survives is the zone's persistent relative standing plus whatever is different about it this year. That is also exactly what the product ranks, and what the primary label already scores, so the change makes the baseline consistent with both rather than introducing a new idea.

**The follow-up question this invites:** "Doesn't that throw away the crop information?" Answer: it throws away the crop *level*, which is a field-year constant and is noise for a within-field ranking. It keeps any zone-by-crop interaction as a candidate refinement that has to earn its place by lift.

**Consequence.** Usable history per zone returns to five to seven prior seasons. The field centre is a median rather than a mean so a large anomaly cannot drag the centre toward itself.

Raised in `docs/reviews/2026-09-14-baseline-depth-decision.md`, Decisions 1 and 2.

---

### D18. The AOI is restricted to the doubly covered region

**Decision.** The study area is Story County intersected with the footprint of Sentinel-2 relative orbit 112, roughly 64% of the county.

**Rejected: the whole county with orbit coverage as a per-zone covariate.** Step 0 measured that two relative orbits cover the AOI, one of which clips it, so 64% of the county receives roughly twice the clear observations of the remainder. Zones on the thin side get noisier baselines and shorter achievable persistence runs for S5. Carrying that as a covariate would attach a confound to every downstream comparison, and the thin region is a contiguous stripe rather than a random sample, so the confound is spatial.

**Rationale.** `SPEC.md` Section 15 already states the tradeoff: accept a smaller AOI over a bigger boundary problem. A satellite orbit boundary appearing as a spatial pattern in crop stress is precisely the kind of artifact this project exists to avoid reporting.

**Consequence.** About a third of the fields are dropped. The excluded stripe is retained as a free robustness experiment for later: does ranking quality degrade at half the observation density? Recorded as an option, not scheduled.

Raised in `docs/reviews/2026-09-14-baseline-depth-decision.md`, Decision 4.

---

## 4. What this project is not contributing

Stated explicitly so it is never overclaimed.

The detection components exist in prior work. NDVI zoning is commercially shipped. NDVI change detection exists in Microsoft's FarmVibes.AI. Within-parcel anomaly detection is published as EOAD and validated on rice.

What could not be found, across three research passes, is anyone reporting whether such rankings are actually correct. No precision@k, no false-positive rate, no comparison against a null model.

**The contribution is the evaluation, not the detection.** The system is built end to end and every line is original, but the part that is new is the measurement. The claim is framed as "rare and not found in a bounded search" rather than "never done."

This is a smaller claim than "I built a crop monitoring platform," and it is much more defensible.

## 5. Risk assessment

**Maintenance risk: near zero.** The output is a static precomputed artifact. Nothing runs, nothing serves, nothing expires. It will still work in two years.

**Build risk: concentrated in data acquisition.** Realistically three to five days before any modelling. This is the estimate most likely to slip. The field boundary problem, which was the feared blocker, is resolved by CSB.

**Result risk: real and accepted.** Roughly a one-in-three chance the ranker does not beat persistence. Mitigated not by avoiding it but by pre-committing to how it is reported.

**Scope risk: the main behavioural risk.** The temptation will be to add "and it tells you what is wrong." It cannot, at 10m, and adding it converts a defensible project into an overclaim.

## 6. Anti-patterns to avoid

Drawn from reviewing existing repositories in this space, several of which fail on exactly these points.

- **Unfitted models presenting confident output.** A model with randomly initialised weights still returns a plausible-looking JSON with a class name and a confidence score. It fails silently, not loudly.
- **Headline metrics with no evaluation behind them.** Percentage improvement claims in a README with no eval script, no benchmark, no test set.
- **Advertising capabilities the code does not have.** Claiming satellite ingestion in documentation when the entry point takes a local image file.
- **Invented thresholds presented as science.** Hardcoded index cutoffs with no citation and no calibration.

The structural defence is that this spec's acceptance gates and evaluation protocol were written before the data was touched, and the negative-result reporting is pre-committed.

## 7. Open questions

Resolved by running code, not by further reading.

1. How many usable clear observations does the chosen AOI actually yield per season? Gate G-0 answers this and must run first.
2. What is the CDL rotation mismatch rate on the test fields?
3. Does any signal beyond S1 measurably improve lift?
4. Does LightGBM beat a weighted sum?
5. Does the ranker beat persistence?

Questions 3 through 5 are the project. Question 1 could change the design and therefore runs before anything else is built.
