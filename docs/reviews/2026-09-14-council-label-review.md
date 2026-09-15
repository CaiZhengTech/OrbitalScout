# Council review of the primary label, 2026-09-14

Second review of the same day, run after the edits in `2026-09-14-spec-review.md` landed and before Step 0. Five independent advisors answered one question, peer-reviewed each other anonymously, and the result was synthesised. Still no data pulled.

The question put to them: the primary label had just been set to "residual below minus one standard deviation of that zone's own residual history." Was that right, versus a within-field quantile, a pooled field-level standard deviation, or a leave-one-year-out baseline for the label only? Specifically, what does each do to the base rate, to the persistence null, and to the honesty of the reported lift?

The answer came back that the question was aimed at the wrong thing.

---

## The finding: the headline comparison was not a test

The primary label measures a zone's deviation from its own mean. The persistence null B1, as defined in this morning's review, ranks zones by that same mean. The label therefore subtracts out exactly the quantity the null ranks on, so the null is scored on an axis the label erased. It cannot win.

Any "lift over persistence" reported that way would be a property of the label definition, not evidence that the ranker found anything. For a project whose stated contribution is evaluation honesty, that is the worst available failure: a rigged comparison presented as the honesty check.

This was introduced by finding 1 of the morning review, which replaced a null that could not rank at all with one that cannot win. Both versions were wrong in opposite directions.

**Resolution.** Two nulls, each matched to the label it is scored against, plus a written prediction recorded before data. SPEC 10, Baselines.

## The changes made

**1. The persistence null splits in two.**

- **B1a, level persistence.** Ranks by multi-year mean index, ascending. Hard to beat on the secondary absolute label, because permanent soil structure repeats annually. Kept for that label only.
- **B1b, anomaly persistence.** Ranks by prior-year residual, ascending. Predicts that zones which were unusually bad last year will be unusually bad again. Construct-matched to the primary label, so it is not handicapped and can genuinely win. **This is the headline null.**

A pre-registered prediction is recorded alongside them: B1a is expected to score at or near chance against the primary label, and any large lift over it on that label must be reported as an artifact of the label definition rather than as evidence of skill.

**2. The primary label becomes a within-field quantile.**

Bottom decile of residuals within each field-year. Base rate fixed at 10% by construction and stated before any data was pulled, which makes lift over random arithmetic rather than a quantity discovered after the fact.

This reverses finding 2 of the morning review, which rejected the quantile label on the grounds that it forces a fixed fraction of every field to be anomalous every year. That objection answered the wrong question. Incidence ("how often does something go wrong") and ranking quality ("under a fixed budget, can the ranker find the worst zones in this field-year") are different questions, and the product answers the second. The secondary absolute label carries the incidence question.

The per-zone standard-deviation threshold is rejected on three counts: with roughly four usable prior seasons per crop it is estimated from far too few points; it selects on estimation error, so zones whose variance is underestimated by chance are flagged every year; and it flags backwards, tripping stable zones on trivial deviations while giving erratic zones a band they rarely cross.

**3. The label baseline is estimated leave-one-year-out.**

The baseline used for the label excludes the target year and is computed separately from the baseline used for features. Without it, feature and label subtract the same estimated baseline and share its estimation error, which the temporal gap does not separate. One line of code, owed regardless of which threshold is used.

**4. The per-zone baseline is stratified by crop.**

Corn Belt fields rotate corn and soybean annually, and the two differ in canopy structure and index scale. A pooled per-zone baseline would treat a rotation as an anomaly. Stratifying halves the usable history per zone, to roughly four seasons per crop out of nine, which is the direct reason the per-zone standard deviation in change 2 is not estimable. Effective history length per zone-crop is measured and reported.

This was missed by the morning review and by all five advisors. It surfaced only in the peer-review round.

**5. Scouting budget k is set in absolute zones, not only as a percentage.**

Reporting precision only at 5, 10 and 20 percent of field area is convention, not agronomy. On a 100 acre field, 10 percent is 10 acres, which nobody walks in a visit. An absolute budget in zones is added as the agronomically meaningful number; the percentages remain for comparability with how the metric is usually quoted.

## What was rejected

A label-sensitivity grid, four labels crossed with four methods, three held-out years and three values of k, published as a surface. All five peer reviewers independently flagged it as the weakest proposal. Every cell would have inherited the same null handicap, so the grid would have measured one artifact sixteen ways, and "lift is stable across label definitions" would have been the most misleading sentence available to put in the repository.

## Open items added

**11. The 2020 derecho sits inside the baseline history.** The chosen AOI is in the derecho corridor. A region-wide damage event inside the baseline window distorts each zone's notion of normal. Either exclude 2020 from baseline estimation or keep it and report sensitivity both ways. Decide at Step 2.

**12. Whether roughly four prior seasons per crop survive cloud masking.** Step 0 measures this. If the usable count per zone-crop is materially below four, the per-zone baseline itself is in question, not merely the per-zone standard deviation already rejected in change 2.

## Method note

Five advisors, then five anonymised peer reviews, then synthesis. Findings 1 and 5 came from the advisor round. The crop-rotation finding and the corrected null came only from the peer-review round, where reviewers were asked what all five advisors had missed. Neither appeared in any individual advisor response.
