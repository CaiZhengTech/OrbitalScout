# Step 4 decisions: splits, scouting budget, and what precision@k can mean

2026-09-18. Written before `evaluate.py` and before `tests/test_splits.py`, so that
the protocol questions are settled without a metric on screen.

Three judgments were flagged at the close of Step 3. A fourth surfaced while
working through the third and turned out to be the largest of the four.

`SPEC.md` Section 10 is frozen. Nothing here revises it. Two of these decisions
fill values the section explicitly delegated, and two settle details it left
unspecified. Where a detail was unspecified, that is said plainly rather than
presented as though the spec had decided it.

---

## Decision 8: what `tests/test_splits.py` actually asserts

`CLAUDE.md` calls this the most valuable test in the repository and requires it
before any code it guards. The question is not whether to write it but what it
can honestly claim.

### The finding: field blocking is vacuous at Step 4

Section 10 requires holdout by year **and** by field, and scopes field blocking
to "everything that is fit on data: z-score statistics, rung-2 weights, k-means,
LightGBM, and any calibration of the label."

Taking an inventory of what Step 4 actually fits:

| Object | Fit? | Scope | Governed by |
|---|---|---|---|
| S1 temporal anomaly | no, zero parameters | per row | nothing to block |
| Per-zone feature baseline | no, a temporal rule | one zone's own history | strictly prior years |
| Label baseline | no, a temporal rule | one zone's own history | leave-one-year-out |
| Label decile threshold | within field-year only | one field-year | uses its own year, by definition |
| B1a, B1b | no, a temporal rule | one zone's own history | strictly prior years |
| B2 NDVI k-means | **yes** | within one field | strictly prior years |

Every fitted object at Step 4 is fit **within a single field**. Nothing pools
across fields. A `GroupKFold` grouped by field would therefore partition a set
that no estimator reads, and reporting G-1 as passed on the strength of it would
be a gate measured on the wrong thing. That is the failure already recorded twice
in this project, at Decision 6 and again at the Step 2 support gate.

So the honest position is recorded rather than dressed up: **field blocking
becomes load-bearing at rung 2**, where z-score statistics are pooled across
fields, and at rung 3. The split function and its test are written now, because
`CLAUDE.md` rule 1 requires the test to exist before the code it guards and
because writing it after the first pooled statistic exists is how leaks happen.
But the claim made in `RESULTS.md` will be that field blocking was exercised
and had nothing to separate at this rung, not that it passed a meaningful test.

`evaluate.py` carries a one-line comment saying that any statistic added there
which is fit across fields must go through the split function. No registry, no
enforcement machinery. The comment is the mechanism.

### The trap: the two baselines obey *different* rules

The obvious way to write the temporal assertion is the way `CLAUDE.md` phrases
it: "every baseline value uses only years strictly before the year it is applied
to." Written that way the test is **wrong**, and wrong in the direction that
destroys the project.

The feature baseline is strictly prior. The label baseline is leave-one-year-out,
which deliberately includes years *after* the target year. That asymmetry is not
sloppiness; it is Section 10's circularity control. If feature and label
subtracted the same estimate they would share its estimation error, and no
temporal gap separates that. This project has already been bitten by shared
estimation error twice, most recently in the D1 diagnostic at Step 3.

A test asserting the strictly-prior rule against both views would fail on the
label baseline. The likely repair, under time pressure, is to make the label
baseline strictly prior so the test goes green. That silently collapses the two
estimators into one and reintroduces exactly the contamination the control
exists to prevent, while every number gets quietly better.

So the test encodes two rules, keyed to the view:

1. `baseline` (feature): for zone z, year y, bin b, no year at or after y
   contributes.
2. `label_baseline`: year y itself does not contribute, and years after y **do**.
   The second half is asserted positively, not merely tolerated.
3. The two views are numerically different on a fixture that has at least one
   later year. This is the load-bearing assertion. Applying the project's own
   test ("if I delete this, what breaks and how would I notice?"), the answer is
   that the numbers improve and nobody finds out.
4. No feature reads a bin at or above `LABEL_BINS[0]`, and no label reads a bin
   at or below `FEATURE_BINS[1]`. The gap bin belongs to neither.

### How the temporal rules are tested

Not by inspecting SQL. By poisoning a year.

Build a synthetic zone history, set one year's observations to an extreme value,
and assert the baseline does not move where the rule forbids that year from
contributing. Repeat per year in the fixture. This is mechanical, survives a
rewrite of the SQL, and is mutation testable: reverse the window frame from
`1 PRECEDING` to `CURRENT ROW` and the test must go red.

---

## Decision 9: `SCOUTING_BUDGET_ZONES = 20`

Section 10 specifies the primary metric at "a fixed absolute scouting budget,
expressed in zones, set from what one person can physically walk in a single
visit," and delegates the value to `config.py`. Filling that value is what the
section asked for, not a revision of it.

### Derivation

A 30m zone is 900 m², which is 0.222 acres. Walking a directed scouting visit:

- In-field time for a single field visit: about one hour.
- Time at a stop, enough to look at plants rather than glance at a spot: 2 to 3
  minutes.
- Walking speed through a closed row-crop canopy: about 1.3 m/s, well under open
  ground pace.
- Travel between n scattered stops in a field of side L follows a nearest
  neighbour tour of roughly 0.7 · L · √n. The mean field-year here is 223 zones,
  about 50 acres, so L is about 450m.

At n = 20: travel is 0.7 · 450 · 4.47 ≈ 1410 m, which is about 18 minutes, plus
20 stops at 2 minutes is 40 minutes. Total about 58 minutes.
At n = 15 with 3 minutes per stop: about 16 minutes travel plus 45 minutes of
stops, about 61 minutes.

One hour of in-field time lands at 15 to 20 zones. That is the band.

### Why 20 rather than 15

Three reasons, in order of weight:

1. **Rounding up is the conservative choice against our own system.** For a real
   ranker, precision@k falls as k grows, because the ranker exhausts its true
   positives and starts spending budget on zones it was less sure about. Taking
   the top of the band makes the headline metric harder to pass, not easier.
2. 20 zones is 4.45 acres, about 9% of an average field-year. That sits next to
   the 10%-of-field figure the metric is conventionally quoted at, so the
   absolute number and the fractional number measure nearly the same thing and
   can be read against each other. At 15 they would diverge for no reason.
3. Extension scouting practice recommends on the order of 5 to 10 stops per
   field for stand assessment. This is the same order of magnitude, a little
   more thorough, which is what a directed visit should be: the ranker spends
   the budget on chosen locations rather than on a fixed W pattern.

### What was deliberately not used

The Step 3 run reported a 20-zone budget selecting 18.2 zones per field-year on
average. That table was on screen before this value was chosen, which is worth
declaring. It reports only how many zones a budget selects, never how well any
ranker performs, so there is no outcome to tune toward. The derivation above
does not reference it.

### One note for the user, not an edit

`SPEC.md` line 199 reads "Recorded in `config.py` `[TBD]`." The value now lives
in `config.py` as the section instructed, so the delegation is honoured. The
literal `[TBD]` in Section 10 is left in place, because Section 10 is frozen and
`CLAUDE.md` rule 7 makes changes to it a conversation rather than an edit. If the
user wants that token replaced with a pointer, that is the conversation.

---

## Decision 10: how precision@k is reported when the base rate is 10% by construction

The primary label is the bottom decile within field-year, so the base rate is
fixed at 10% before any measurement. Section 10 says so itself, and says it makes
lift over random "arithmetic rather than a quantity discovered afterwards."

Three consequences follow, and the third is the one that matters.

### Lift over random carries no information about the ranker

With a constant base rate, lift over random is precision@k multiplied by ten. It
is a change of units. It is reported because Section 10 requires it and Section
10 is frozen, but it is reported **in the same row as the precision it rescales**,
never as a separate finding and never as the headline. The headline stays lift
over B1b, as `CLAUDE.md` already requires, and every informative comparison in
this project is ranker against ranker, where the constant base rate cancels and
what remains is a genuine difference in ordering.

### Precision@k has a ceiling that binds at k = 20%

With a 10% base rate, a perfect ranker achieves precision 1.0 only while k does
not exceed the positive count. Above that it must spend budget on negatives:

| k | zones at 223 | ceiling on precision | ceiling on lift |
|---|---|---|---|
| 5% | 11 | 1.00 | 10.0 |
| 10% | 22 | 1.00 | 10.0 |
| 20% | 45 | 0.50 | 5.0 |
| 20 zones | 20 | 1.00 | 10.0 |

Reporting precision@5%, @10% and @20% as a bare row invites the reader to
conclude the ranker degrades with k, when half the fall at k = 20% is arithmetic.
So each k is reported with three numbers: precision@k, the ceiling
min(1, base rate / k), and precision as a fraction of that ceiling. For every k
at or below 10% the ceiling is 1.0 and the third column equals the first, so
nothing is distorted where the ceiling does not bind. Lift is quoted with its own
ceiling attached for the same reason: "lift 3.2" reads as unbounded until the
maximum of 10.0 is next to it.

### The base rate is not actually 10%, and that is the fourth judgment

Measured on the ranked output, the field-year size distribution is heavily right
skewed:

| | zones per field-year |
|---|---|
| min | 1 |
| p10 | 11 |
| p25 | 27 |
| median | 122 |
| mean | 223 |
| p75 | 307 |
| p90 | 594 |
| max | 2,892 |

Two things break at the small end.

**The decile does not divide evenly.** The positive count is
ceil(0.10 · n), so a five-zone field-year has one positive and a 20% base rate,
an eleven-zone field-year has two positives and an 18.2% base rate, and a
one-zone field-year has a 100% base rate. `ceil` rather than `floor` because
`floor` gives zero positives for every field-year under ten zones, which leaves
precision undefined there. Ties are broken by `zone_id` ascending so the label is
deterministic.

**The budget covers the whole field.** At a 20-zone budget, 19.3% of field-years
hold 20 zones or fewer, contributing 11.3% of all selected zones. In those
field-years precision@k equals the base rate no matter how good or bad the
ranking is, because every zone is selected. They are not measuring the ranker.
They pull the pooled number toward the base rate and so understate skill, which
is the flattering direction to leave uncorrected and therefore the direction to
be explicit about.

**Decision.** Section 10 fixes the metrics and the label but never states which
population they are computed over, so this fills a gap rather than changing an
answer. Every metric is reported twice, side by side:

- **all field-years**, the complete population, and
- **field-years with more than k zones**, where the budget selects a strict
  subset and ranking is a real question.

The second is the headline. The exclusion is reported as a count and a share
every time it appears, so a reader can see exactly what was dropped, and the
first column is always present so the exclusion is auditable rather than
asserted. The realized pooled base rate is measured and reported rather than
assumed to be 0.10, which Section 10 already anticipated by listing "base rate
per field-year, under each label" among the metrics.

### Uncertainty intervals are bootstrapped over fields

A spread across three held-out years is the only uncertainty Section 10 asks for.
Where an interval is quoted, it is resampled over **fields**, not zones and not
field-years. Adjacent zones are spatially autocorrelated and a zone-level
bootstrap over two million rows would produce an interval so tight it would be
a lie, for the same reason a random zone split would produce an excellent and
meaningless score. This is the split rule applied to resampling.

---

## What Step 4 now has to build

1. `tests/test_splits.py` first, with the two temporal rules, the
   feature-and-label views being different, the window separation, and the field
   purity assertion on the split function. Red before any of it is green.
2. `orbitalscout/split.py`, the year and field holdout.
3. `orbitalscout/evaluate.py`, precision@k with its ceiling, recall, false
   positive rate, realized base rate, and lift against B1a, B1b and B2, reported
   on both populations and both labels.
4. `orbitalscout/baselines.py`, B1a, B1b and B2. B2's k is chosen per field over
   2 to 7 by silhouette on prior-year mean index only, never on the target year,
   so the commercial comparison is held to the same temporal rule as our own
   ranker.

---

## Amendment, same day, after the harness ran

Three decisions were forced by the run itself and are recorded here rather than
folded silently into the code.

### Decision 11: B2 is reported for two periods, and the harder one is the headline

`SPEC.md` Section 10 names B2's method and not its period. The first
implementation clustered prior years only, which is a static multi-year
management zone map and is a reasonable reading.

It is also a handicapped one. S1 reads the current season. B1a and B1b having no
current-season data is the entire point of a persistence null, so that asymmetry
is the experiment. But commercial platforms ship in-season index maps as well as
static zone maps, so a history-only B2 is a commercial baseline denied the input
its real counterpart has, and beating it would prove less than it appears to.

Both variants now run. The difference is a third of the headline: lift of S1 at
the 20-zone budget is 2.145 over the historical B2 and 1.416 over the in-season
one. The in-season figure is the reported one.

B2 is also taken at its best k, which measured out at 7 in every cell of every
table. Choosing a baseline's hyperparameter after seeing results is normally
cheating; here it runs in the baseline's favour, so it makes the claim
conservative rather than flattering.

### Decision 12: the evaluated population may not depend on any ranking

`strict_subset` first sized the budget by cutting a ranking, which crashed
because it was handed an unranked frame. The crash was the cheap part. The
defect it exposed is that the population being measured would have been an
output of the thing being measured, even though every method would have produced
the same subset, because the budget covers a field-year or does not regardless
of order.

It now sizes the budget from field-year counts alone, through
`rank.budget_size`, and a test pins that function to what `rank.select_budget`
actually selects so two definitions of one budget cannot drift apart.

The exclusion turned out smaller than Decision 10 expected: 18.5% of field-years
but only 0.9% of zone-years, moving S1's precision@20 by 6.7% and its lift over
B1b by 2.9%. Micro-averaging over selected zones already downweights small
field-years. Both populations are still reported at every budget, because that
was pre-committed and because the size of a correction is not a reason to stop
showing it.

### Decision 13: the chunked Parquet glob

Not an evaluation decision, but it surfaced here and is worth the record.
`data/baseline/` holds the ten chunk files of each Step 2 output and also the
outputs of `scripts/step2_diagnostics.py`. `label_*.parquet` matches
`label_noevent_*.parquet`, reading every zone-year twice: 20 files and
11,163,605 rows against the correct 10 files and 5,581,563.

Nothing published was affected. The Step 2 gate ran at 13:44 and the diagnostics
wrote at 13:46, so `RESULTS.md` carries the clean counts, and re-running the gate
with the fix reproduces them exactly. That is timing, not care. Every reader now
goes through one `build_baseline.chunks` helper, and a test greps every script
for a bare chunked glob on a `read_parquet` line.

### What the results changed about the spec

Nothing. Section 10 is unedited. Its pre-registered prediction that B1a would
score "at or near chance" on the primary label did not survive the data, B1a
reaching lift 1.47 over random, and that is recorded in `RESULTS.md` as a failed
prediction rather than repaired in the spec. The direction of the prediction
held; its magnitude did not.
