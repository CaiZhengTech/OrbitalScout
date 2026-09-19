# Step 5: probe the shared premise before building S4 and S5

2026-09-19. A change of method, prompted by the user after two signals were
built, measured and cut in two days: if something is not improving anything, go
back to the drawing board rather than keep incorporating.

## Decision 20: test the premise once instead of building two signals

S4 velocity and S5 persistence are different summaries of the same thing. Both
assume that a zone's **within-season trajectory** carries information beyond the
single residual S1 already uses, which is the latest supported cell of the
feature window.

That assumption is testable directly, on data already on disk, without building
either signal. So it gets tested first.

- If the trajectory adds nothing, S4 and S5 are both answered by one result, and
  the finding is stronger than two separate null write-ups would be.
- If it adds something, the probe says which summary carries it, and S4 or S5
  gets built knowing what it is reaching for rather than guessing.

This is not a shortcut around the admission rule. Anything that survives the
probe still has to be built test-first and pass the admission rule on lift over
B1b. The probe decides what is worth building, not what ships.

**The trajectory exists.** Measured before writing this: across 2,088,521
held-out zone-years, 52.1% have all seven feature bins supported, 88.2% have six
or seven, 99.8% have three or more, and every single one has at least two, so a
slope is always defined. Bin coverage runs from 82.4% at bin 5 to 98.0% at bin
6. This is a dense time series, not a sparse one. An earlier worry that S4 and
S5 would need a finer per-date grain than the pipeline produces was simply
wrong: the 200 GDD bins already are the time series.

## What is measured

Four summaries of the same feature-window residual series, all per zone-year,
all scored so that larger means more urgent:

| name | definition | the signal it stands for |
|---|---|---|
| `latest` | residual in the highest supported bin | S1 as it ships today |
| `mean` | mean residual across supported bins | a simple alternative to `latest` |
| `slope` | OLS slope of residual against bin, negated | **S4 velocity** |
| `n_below` | count of bins with a negative residual | **S5 persistence** |

Each is scored alone, and each is combined with S1 at rung 2, against the B1b
persistence null on the primary label. Partial rank correlation with the label,
controlling for `latest`, is reported alongside to explain whatever the ranking
metrics show.

## The prediction

At the 20-zone budget, primary label.

1. **`latest` is the strongest of the four alone.** The label is the
   *end-of-season* residual and `latest` is the summary closest to it in time.

2. **`mean` lands within 10% of `latest` on lift over B1b.** The bins are
   phenology-aligned observations of one zone in one season, so they should be
   highly correlated, the same redundancy that sank S3.

3. **Neither `slope` nor `n_below` improves lift over B1b when added to S1.**
   Once a zone's ending level is known, the path it took there adds little about
   where it ends up at grain fill.

4. **The partial rank correlation of `slope` with the label, controlling for
   `latest`, is below 0.05 in absolute value.** This is the sharp version of
   prediction 3 and the one that generalises: if it holds, no cleverer velocity
   feature rescues S4, because the information is not there to be extracted.

If prediction 4 fails while prediction 3 holds, the information exists and the
combination is wasting it, which would be an argument for rung 3 rather than for
another hand-built signal.

---

## Outcome, same day

**The premise does not hold. Neither S4 nor S5 was built.** Numbers in
`RESULTS.md`.

Three of the four predictions held, including prediction 4, which was the one
written to generalise: the partial rank correlation of `slope` with the label,
controlling for `latest`, measured **0.007**. Velocity contributes essentially
nothing once the ending level is known. `slope` correlates 0.338 with the label
on its own, which looks like a signal, but 0.872 with `latest`: it is mostly a
restatement of where the zone ended up rather than a reading of how it got
there. No better velocity feature recovers information that is not present.

`n_below`, standing in for S5, is worse than that. It scores below the B1b null
on its own, 0.748 at the 20-zone budget, and costs 15 to 19 percent in
combination. Counting how many bins were negative throws away magnitude, and
magnitude is what the label is made of.

**Prediction 2 failed and its failure is the most useful thing here.** The
reasoning was that the bins are phenology-aligned observations of one zone in
one season, so they should be highly correlated, the redundancy that sank S3.
Measured, `mean` correlates only 0.637 with `latest`. The bins are genuinely
different measurements; a zone's standing at emergence is not its standing at
VT. So the trajectory is real information that does not help, which is a
sharper statement than "the bins are redundant" would have been, and it is the
opposite of the S3 mechanism rather than a repeat of it.

Averaging across the window mixes early-season readings into a prediction about
grain fill and dilutes the recent reading that carries the signal. That is why
`mean` loses 25% against `latest` rather than matching it, and it is an argument
for the existing design choice to take the latest supported cell rather than
the window mean.

### What the probe cost and saved

One script and one run, against two build-measure-cut cycles with two write-ups
that would have reached the same place. The admission rule was not weakened:
anything that survived here would still have been built test-first and still
had to beat B1b.

### S6 and the recommendation

S6 subtracts a soil-context fit to separate "bad because always sandy" from
"bad beyond soil explanation." Step 3 already measured that the D17 relative
baseline removes permanent standing, Pearson 0.002 and 0.001 against standing
computed from later years. There is no soil map left in the residual for S6 to
remove, and S6 alone would require ingesting SSURGO.

Recommendation: close the ablation and move to the demo. Two signals built and
cut on measurement, two answered by this probe, one made redundant by a
measurement already recorded. Rung 1 stands alone and rung 2 never earned its
place.
