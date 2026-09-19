# Step 5, S2 spatial anomaly: decisions and a prediction written before the run

2026-09-18. Written before `s2_spatial_anomaly` exists, so that the prediction
cannot be adjusted to fit the number. The Step 1 zone-size comparison and the
Step 2 coverage rule were both caught by doing this, and the Step 4 pre-registered
prediction about B1a failed in public because it was on record.

`SPEC.md` Section 7 defines S2 as "deviation from immediately neighbouring
zones, same date," detecting "first-year problems with no history" and
"self-correcting for whole-field effects like regional drought."

---

## Decision 14: S2 is a level signal, and that is the point

S2 must not subtract a temporal baseline. If it did it would be a spatially
local restatement of S1, and it would lose the one thing Section 7 says it is
for: scoring a zone with no usable history at all.

The consequence is stated up front rather than discovered later. **A level
signal partly reproduces the permanent soil map**, because a patch that is
always sandy is always below its neighbours. D1 established that ranking by
level reproduces the soil map, and D17 exists to remove it. So S2 carries back
in some of exactly what the project removed. Whether that costs more than it
adds is what the admission rule decides.

## Decision 15: the neighbourhood

Zone ids pack the grid coordinate, so adjacency is arithmetic rather than a
spatial join: east and west are `zone_id` plus or minus the stride, north and
south plus or minus one. The neighbourhood is the eight surrounding 30m cells.

**Neighbours must be in the same field-year.** A zone at a field boundary whose
neighbour lies in a different field, likely under a different crop with a
different planting date, would be compared against something the within-field
framework never intended. Looking a neighbour up under the target's own field id
gives this in one step: a neighbour in another field simply does not match.

**A neighbourhood mean needs at least three neighbours.** Fewer and it is one or
two zones rather than a local expectation. Three is the same floor and the same
reasoning as `MIN_PRIOR_YEARS`. The share of zone-years this excludes is
reported rather than assumed small, and it is a direct count of the thing the
floor protects, not a proxy for it. That distinction is what the Step 2 coverage
rule got wrong.

The value averaged is the within-field relative index over the feature window,
the same `season_level` the in-season B2 clusters. Within a field-year the field
median is a per-date constant, so it largely cancels in the difference between a
zone and its neighbours; using the relative index rather than the raw one keeps
that true when a zone and its neighbours were seen on different dates.

## Decision 16: rung 2 is equal weights, z-scored within field-year

`CLAUDE.md` puts rung 2 at "weighted sum of z-scored signals" and states that
rungs 1 and 2 require no training. Equal weights is the no-training reading, and
it is the one taken.

**Weights will not be searched if equal weights lose.** Searching them is
training, it would make the field-blocked split load-bearing, and it is the
"retune until the number improves" behaviour `CLAUDE.md` forbids by name.
Fitted weights belong to rung 3, with blocked splits, if the project gets there.

Z-scoring is done **within field-year**. It uses no labels, so it cannot leak
one, and for a single signal it is a monotone transform within the ranking unit,
so ranking by `z(S1)` and by `S1` are the same ranking. It also keeps the
z-score statistics from pooling across fields, which means field blocking still
has nothing to separate at this rung. That is said again rather than quietly
skipped.

---

## The prediction

Written before any S2 code exists. Measured at the 20-zone scouting budget, on
the comparison population, against the primary label unless stated.

1. **S2 alone beats random but lands well below S1.** Lift over random between
   1.2 and 2.0, against S1's measured 3.07. Mechanism: the primary label has the
   zone's own level subtracted by a leave-one-year-out baseline, so a level
   signal can only reach the part of this season's condition that the baseline
   does not already explain.

2. **S2 does relatively better on the level label than on the residual label**,
   the same way B1a and B2 do. Concretely, S2's lift over random on the
   secondary label exceeds its lift on the primary.

3. **The admission test: S1 plus S2 at equal weight does NOT improve lift over
   B1b compared with S1 alone, on the primary label.** This is the prediction
   that decides whether S2 ships. Reason: adding a level signal reintroduces the
   permanent local soil structure that D17 removes, and the primary label
   subtracts precisely that.

4. **If prediction 3 is wrong**, the most plausible mechanism is that the
   neighbourhood supplies a second estimate of a zone's expected level that needs
   no history, so the gain should concentrate in zones whose strictly prior
   baseline rests on the fewest years. That is checkable: split the improvement
   by `n_prior_years` and it should be largest at the floor of 3. If the gain is
   flat across `n_prior_years`, this explanation is wrong and something else is
   happening, which would need finding before S2 ships.

A null result here is a reportable finding, not a failure. "S2 spatial anomaly
did not improve lift over persistence and was cut" is what the admission rule is
for, and `RESULTS.md` records it either way.

---

## Outcome, same day

**S2 was cut.** S1+S2 scores 9.5% to 11.8% worse than S1 alone on lift over
B1b, at all four budgets. Numbers in `RESULTS.md`.

All three predictions held. The first held only barely: S2 alone measured lift
1.99 over random at the 20-zone budget against a predicted range of 1.2 to 2.0,
sitting at the top edge, and it would have failed the range at any tighter
budget. That is recorded rather than rounded in our favour.

Decision 16 said weights would not be searched if equal weights lost. They were
not. The loss is about a tenth at every budget, so no weight short of putting
almost nothing on S2 would change the verdict, and finding that weight by
searching is the behaviour the decision existed to prevent.

The mechanism check was written for a case that did not arise, and paid for
itself anyway. It shows the damage is flat across history depth, so S2 dilutes
S1 uniformly rather than trading a gain somewhere for a loss elsewhere. It also
shows that only 973 zone-years of 1.8 million rest on the minimum three prior
years, which means the "first-year problems with no history" case that Section 7
uses to justify S2 is **empty by construction** in this evaluation: the
`MIN_PRIOR_YEARS` floor removes those zones before S2 is consulted.

So the cut is narrower than it looks. S2 is a dilutant where S1 works. It has
not been shown to be useless on zones below the support floor, because that
population was defined away at Step 2. Issue #20 records the untested case so
the result is not over-claimed.
