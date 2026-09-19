# Step 5, S3 multi-index divergence: decisions and a prediction written before the run

2026-09-19. Written before `s3_multi_index_divergence` exists. S2's three
predictions all held when written this way; Step 4's spec-level prediction about
B1a failed in public for the same reason. Both outcomes are the point.

`SPEC.md` Section 7 defines S3 as "disagreement between standardised NDVI, NDRE,
NDWI", detecting "water stress before visible decline; chlorophyll issues before
biomass loss." This is the first signal to read NDRE and NDWI at all. Step 1
ingested them and nothing has touched them since.

---

## Decision 17: the three indices must come from one observation

A signal that compares indices against each other is meaningless if they come
from different dates. A zone can be dry in late June and fine in mid July, and a
"divergence" assembled across those two dates measures the calendar.

Measured before deciding: across 3,432,652 supported zone-year feature cells
there are **zero** null residuals in any of the three indices, and the bin that
`max(bin)` reports never disagrees with the bin `arg_max` selects. So today
three separate `arg_max` calls would in fact agree.

That is a property of the data, not of the code, and the failure it guards
against is silent. `zone_year_feature` therefore selects **one row** explicitly,
the highest supported bin in the feature window, and takes all three residuals
from it. If an index is null in that row its feature is null and the zone goes
unscored, rather than quietly falling back to an earlier date for that one
index while the others stay put.

This also removes a latent inconsistency that already existed: `feature_ndvi`
came from `arg_max(residual_ndvi, bin)` while `feature_bin` came from a separate
`max(bin)`, and the two could name different cells the moment a null appeared.

## Decision 18: S3 is directional, and SPEC's wording admits two readings

"Disagreement" could mean either of two things, and they are not the same signal.

**The divergence reading, which is what Section 7's mechanism describes.** NDWI
tracks water and NDRE tracks chlorophyll; both are expected to move before NDVI,
which tracks biomass. So the informative case is not symmetric disagreement, it
is the early indices reading worse than the late one:

    S3 = z(residual_ndvi) - mean(z(residual_ndre), z(residual_ndwi))

standardised within field-year, larger meaning more urgent. High when NDVI still
looks acceptable but water and chlorophyll do not. A symmetric measure such as
the spread of the three would also fire when NDVI is the worst of the three,
which is not an early warning and is not the stated mechanism. The symmetric
version is rejected for that reason.

**The aggregation reading.** Use all three residuals as a combined level rather
than as a contrast:

    multi-index level = -mean(z(residual_ndvi), z(residual_ndre), z(residual_ndwi))

This is not literally "divergence", so it is not S3. But it is the obvious way
to ask whether NDRE and NDWI carry anything beyond NDVI, and the prediction
below argues the rung 2 combination collapses onto it anyway. It is therefore
measured alongside, as a named diagnostic, so that a null result on S3 cannot be
mistaken for a null result on "NDRE and NDWI are useless." The same reasoning
made B2 report two periods at Step 4.

## Decision 19: no new machinery

Rung 2 already exists from S2 and is reused unchanged: equal weights, z-scored
within field-year, no weight search. Decision 16 stands.

---

## The prediction

At the 20-zone scouting budget, primary label, on the population every method
can score.

1. **S3 alone scores below random.** Lift over random under 1.0. This is a
   sharper claim than "it is weak", and it follows from the algebra rather than
   from pessimism: S3 is loaded **positively** on `residual_ndvi`, the label is
   the bottom decile of an NDVI residual, and the two NDVI residuals are
   positively correlated. A signal that rewards a healthy NDVI should rank the
   label backwards.

2. **The rung 2 combination collapses onto the aggregation.** Writing
   `z(S1) = -z(residual_ndvi)` and `z(S3)` as roughly
   `z(residual_ndvi) - mean(z_ndre, z_ndwi)`, the sum is approximately
   `-mean(z_ndre, z_ndwi)`: the NDVI terms cancel and S1+S3 effectively discards
   NDVI. Checkable, not rhetorical: the Spearman correlation between the S1+S3
   score and `-mean(z_ndre, z_ndwi)` should exceed 0.9.

3. **The admission test: S1+S3 does NOT improve lift over B1b against S1
   alone.** Because of prediction 2 it throws away NDVI, and NDVI is the index
   the label is built from.

4. **The diagnostic that decides what the null means.** If the aggregation
   variant also fails to beat S1, then NDRE and NDWI carry no usable information
   beyond NDVI at this grain, and that is the finding. If the aggregation
   variant beats S1 while S3 does not, then the information is real and it is
   S3's contrast form that wastes it, which would be an argument about Section
   7's definition rather than about the data. These lead to different write-ups
   and the distinction is fixed here, before the numbers.

A null result is a reportable finding. S2 was cut on the same rule the day
before and the repository is better for the record, not worse.

---

## Outcome, same day

**S3 was cut.** S1+S3 scores 19.5% to 32.1% worse than S1 alone on lift over
B1b, at all four budgets. Numbers in `RESULTS.md`.

**Two of the four predictions failed.** Prediction 3, the one that decides
admission, held. Predictions 1 and 2 did not, and both were wrong in the same
way: the algebra was right about direction and wrong about magnitude.

Prediction 1 said S3 alone would score below random because it is loaded
positively on the NDVI residual that the label is built from. Measured, the
rank correlation between S3 and S1 is only -0.136. Standardising each index
within field-year and averaging the two early ones dilutes the NDVI term far
more than the derivation assumed, and S3 lands slightly above chance rather
than below it.

Prediction 2 said the NDVI terms would cancel in the rung 2 sum, checkable as
Spearman above 0.90 against the early-index mean. Measured 0.843. The
derivation treated `z(S3)` as arriving on the same scale as
`z(residual_ndvi)`, but rung 2 standardises S3 as a whole and leaves some NDVI
behind. The direction held: S1+S3 correlates 0.843 with the early-index mean
against 0.584 with S1.

Prediction 4's fork resolved toward the indices rather than toward S3's form.
The aggregation variant also fails to beat S1 on the primary label, by 0.1% to
2.6%, so this is not a case of a real signal wasted by a bad contrast.

The mechanism was then measured rather than argued. Across 3,432,652 feature
cells the three indices correlate at 0.960 for NDVI against NDRE and 0.909
against NDWI. Adding indices that correlate above 0.9 cannot add much, and
contrasting them leaves a residue dominated by measurement noise. Section 7's
premise, that NDWI and NDRE move before NDVI, is a claim about within-season
timing; this evaluation carries one residual per zone-year from the latest
supported feature cell, and at that grain the three indices are nearly the same
measurement. Whether the premise holds per date is a different experiment and
this one does not answer it.

One result went the other way and is reported because it was measured: on the
secondary level label the all-three level beats S1, 1.271 against 1.234 at the
20-zone budget. Averaging correlated measurements estimates a level better. It
does not estimate an anomaly better, and the anomaly is what the admission rule
asks about.
