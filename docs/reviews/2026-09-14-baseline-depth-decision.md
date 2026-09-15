# Baseline depth decision, 2026-09-14

Made after Step 0 ran and before Step 1. The only data seen is what `RESULTS.md` records: clear-observation counts, orbit coverage, and crop-rotation frequency. No evaluation number exists, so the protocol is still being fixed under uncertainty rather than fitted to an outcome.

## The problem, measured

Finding 3 of `RESULTS.md`: with 2017 excluded, a held-out year has five to seven prior seasons behind it. SPEC Section 8, as amended this morning, stratifies the per-zone baseline by crop. Under the measured rotation (crop changes across 82% of consecutive year pairs) that leaves two to four seasons per zone-crop, and only two or three for the 2023 holdout.

A baseline whose "normal" is the average of two seasons is not a baseline. One unusual year is half of it. The council pre-recorded this outcome as putting the per-zone baseline itself in question, and it has occurred.

## What was actually wrong

Crop stratification was the right instinct aimed at the wrong level. The concern was that a pooled per-zone baseline would register a routine rotation as an anomaly, because corn and soybean canopies sit at different index levels. That is true of an **absolute** per-zone baseline.

But the crop is a property of the field-year, not of the zone. Corn Belt fields rotate as whole units, so within any field-year every zone shares one crop. The same is true of weather, planting date and management. All of these are field-year constants.

If the quantity being baselined is the zone's standing **relative to its own field in that year**, every field-year constant cancels. Crop cancels. Wet spring cancels. Late planting cancels. What remains is the zone's persistent relative standing, which is the soil map, plus whatever is different about this zone this year, which is the anomaly.

This is also the quantity the product ranks. The output is a within-field ordering under a scouting budget. The primary label is already the bottom decile of residuals within field-year. Making the baseline within-field too is consistency, not a new idea.

## Decision 1. The baseline is within-field relative, pooled across crops

For zone i in field f at phenology bin b in year t:

    relative_index(i, t, b) = index(i, t, b) - median over zones in f of index(., t, b)
    baseline(i, b)          = mean over prior years of relative_index(i, ., b)
    residual(i, t, b)       = relative_index(i, t, b) - baseline(i, b)

Median, not mean, for the field centre, so that a large anomaly covering a substantial share of the field does not drag the centre toward itself and shrink its own residual.

The baseline pools all prior years regardless of crop. The 2023 holdout gets five seasons, 2025 gets seven. Each season contributes roughly 25 clear observations per zone, so the per-bin curve is estimated from on the order of a hundred points rather than a handful.

Crop stratification is removed from Section 8 as the default. The paragraph that introduced it this morning is replaced.

## Decision 2. Crop-specific adjustment becomes a candidate refinement, admitted only by measurement

Within-field relativity cancels the field-level crop effect. It does not cancel a zone-by-crop interaction: a zone whose relative standing genuinely differs between corn years and soybean years. Two known mechanisms make that plausible here. Soybean iron deficiency chlorosis is a soybean-specific problem on the calcareous soils of the Des Moines Lobe, which Story County sits on, and barely affects corn. Droughty patches hurt water-demanding corn more than drought-tolerant soybean.

If that interaction is large, a pooled baseline will flag an IDC-prone zone in every soybean year. That is a periodic false positive, not an emerging problem.

Rather than guess its size, treat it exactly as the project treats every other proposed improvement. "S1 with a crop-stratified baseline" is an entry in the ablation ladder. It ships only if it measurably improves lift over B1b. The null result is recorded if it does not. No threshold on a correlation coefficient is invented to decide it in advance.

As a diagnostic, not a gate, Step 2 also reports the correlation across zones between mean relative standing in corn years and in soybean years. That number goes in `RESULTS.md` either way.

## Decision 3. B1b is the most recent prior year with the same crop

B1b, the headline null, was defined as "rank by prior-year residual." Under a rotation the prior year is the other crop. If the zone-by-crop interaction is real, last year's residual is anti-informative about a crop-specific recurrence, and the null would be handicapped again, by a different route.

B1b is therefore defined as: rank zones by their residual in the most recent prior year **with the same crop**. Under a strict rotation that is two years back. Where there is no rotation it reduces to the prior year. This keeps the null construct-matched to the label under the data structure that was actually measured.

This is an edit to SPEC Section 10 after Step 0 and before any evaluation. It is driven by a measured property of the data (rotation frequency), not by an outcome, and it is recorded here for that reason.

## Decision 4. The AOI is restricted to the doubly covered region

Finding 2 of `RESULTS.md`: 64% of the county lies under two Sentinel-2 relative orbits and receives roughly twice the clear observations of the remainder, along a boundary drawn by orbit geometry.

The AOI becomes the footprint of orbit 112 intersected with the county. SPEC Section 15 already states the tradeoff in as many words: accept a smaller AOI over a bigger boundary problem. Carrying coverage as a per-zone covariate instead would attach a confound to every downstream comparison, and the thin region is not a random sample of the county.

The excluded third is not wasted. It is a free robustness experiment for later: does ranking quality degrade at half the observation density? Recorded as an option, not scheduled.

## Decision 5. Zone size is measured during Step 1, not before it

The 10m versus 30m comparison is deferred into Step 1 rather than run as a separate Step 0 task. The Earth Engine expression that exports the zone table can emit both sizes at negligible extra cost, and the comparison should be made on the within-field relative quantity now that Decision 1 defines it. Prior expectation, stated so it can be checked: 30m will show lower year-over-year variance for stable zones because it averages down co-registration jitter. The measurement decides.

## What this does not resolve

Open item 9, planting date and the start of GDD accumulation, is unchanged and remains a Step 2 decision.

Open item 11, the 2020 derecho inside the baseline window, is unchanged. Note that within-field relativity does not cancel it: a derecho flattens fields unevenly, so 2020 relative standings carry real signal about wind exposure, not soil. Still a Step 2 decision.

## Interview version

"I stratified the baseline by crop, then measured the rotation and found that left two seasons per zone-crop. Two seasons is not a baseline. The fix was to notice the crop is a property of the field-year, not the zone, so a within-field relative baseline cancels it along with weather and planting date, and history goes back to five to seven seasons. The residual crop interaction becomes a candidate refinement that has to earn its place by lift, like every other signal."
