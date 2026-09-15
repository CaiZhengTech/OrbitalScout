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

Not yet decided: whether to restrict the AOI to the doubly covered portion or to carry orbit coverage as a per-zone covariate and report ranking quality separately for each region.

### Finding 3: effective per-crop history is two to four seasons, not eight

Measured over 2018 to 2025 on 4,000 sampled pixels at 30m, of which 2,892 were corn or soybean in at least six of the eight years.

| quantity | p10 | median | p90 |
|---|---|---|---|
| corn seasons per pixel | 4 | 4 | 6 |
| soybean seasons per pixel | 2 | 4 | 4 |

Crop changes across 82% of consecutive year pairs, and 49.3% of pixels alternate in every single year. The rotation is strong but not universal.

Because the baseline may use only years strictly prior to the target year, and because SPEC Section 8 stratifies the baseline by crop, the depth actually available to a held-out year is lower than the totals above:

| test year | prior seasons | approximate seasons per crop |
|---|---|---|
| 2023 | 5 (2018 to 2022) | 2 to 3 |
| 2024 | 6 (2018 to 2023) | 3 |
| 2025 | 7 (2018 to 2024) | 3 to 4 |

This triggers open item 12 of `docs/reviews/2026-09-14-council-label-review.md`, which recorded in advance that a measured per-zone-crop count materially below four would put the per-zone baseline itself in question, not merely the per-zone standard deviation already rejected.

Unresolved and consequential. Recorded here rather than worked around.

---

## Step 0, zone size

`[TBD]`. Year-over-year variance of stable zones at 10m against 30m has not been measured yet. It is deferred until the baseline question raised by finding 3 is settled, because the two interact: a coarser zone averages down per-observation noise and would change the variance comparison.

## Step 1 onward

`[TBD]`. Not started.
