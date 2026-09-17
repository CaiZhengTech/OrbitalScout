# Step 2 decisions, 2026-09-17

Made after Step 1 landed 149.6 million verified zone-date rows and before any baseline code. Settles the two items deferred to Step 2 (planting date, the 2020 derecho) and two parameters Step 2 cannot proceed without (where GDD is computed, how wide a phenology bin is). No evaluation number exists.

## Decision 1. The GDD origin is the USDA NASS 50% planted date, per crop, per year

**The problem.** GDD accumulates from planting. CSB carries a planting window, not a date. A fixed calendar start gives calendar-plus-temperature, not phenology. Green-up detection from the index curve introduces a threshold, which SPEC is rightly hostile to.

**What within-field relativity already handles.** D5 was written before D17. Its motivation, "two zones at the same date may be at different growth stages because of planting date," no longer applies between zones: a CSB field is planted as one unit, so every zone in a field shares a planting date and the field median absorbs it on every date. What GDD alignment still buys is the **cross-year** alignment of the baseline. A zone's relative standing changes with growth stage (a wet spot lags at emergence and closes the gap by canopy closure), so comparing bin b across years only means something if bin b is the same stage each year. The dominant variation in planting date is year to year, driven by spring weather, about plus or minus two weeks in the Corn Belt. Field to field within a year is smaller, and is a field-year constant that D17 cancels.

**Decision.** For each crop and year, the GDD origin is the date on which USDA NASS Crop Progress reports Iowa reaching 50% planted for that crop. This is an external, published, threshold-free anchor for exactly the component that matters, the year-level offset. It is crop-specific and lives in the crop registry keyed by CDL code, which is the D4 pattern: adding a crop means adding the NASS series to look up.

**Rejected: fixed calendar start.** Leaves the plus or minus two week year-to-year offset in every baseline, which is roughly 300 GDD on a 2,700 GDD season, so bins would be misaligned by about a tenth of the season in bad years.

**Rejected: per-field-year green-up detection.** Requires a threshold on the index curve or on its derivative, invented rather than measured, and estimated per field from a series that is 20% clear on any given date. The field-level residual it would correct is second order under D17.

**Diagnostic, not gate.** Step 2 also computes green-up per field-year from the field-median NDVI (the date it first exceeds the seasonal minimum plus half the amplitude) and reports its spread around the NASS anchor. If field-level green-up scatters widely around the state date, that is recorded in `RESULTS.md` and reconsidered; no threshold on the spread is set in advance.

**Honest limitation.** The anchor is state-level. Story County sits near the centre of Iowa and near the state median planting date, so the bias should be small; it is stated rather than assumed away, and the diagnostic above measures it.

## Decision 2. Post-derecho 2020 is excluded from baseline estimation, via a known-events table

**The problem.** The August 10, 2020 derecho flattened crop across central Iowa. Within-field relativity does not cancel it, because lodging is uneven inside a field, depending on hybrid, stage, orientation and local exposure. 2020 late-season relative standings therefore carry wind-damage signal, not soil or management signal, and 2020 sits in the baseline window of all three held-out years.

**Decision.** Observations from the AOI on or after 2020-08-10 are excluded from baseline estimation, for both the feature baseline and the leave-one-year-out label baseline. Observations before that date are kept; the event has a known date and the pre-event season is ordinary. The exclusion is expressed as a one-row table in `config.py`:

```
KNOWN_EVENTS = (
    # name, start, end, why
    ("derecho_2020", "2020-08-10", "2020-12-31",
     "Regional wind damage, uneven within fields; not soil or management"),
)
```

Knowledge as data, per D4. Adding an event means adding a row. Nothing branches on a year.

**Rejected: exclude all of 2020.** Costs a full season of a five-to-seven season history for the sake of its last third.

**Rejected: keep it and report sensitivity only.** The contamination is known, dated and directional. Leaving it in and reporting a number afterwards is the pattern the project exists to avoid.

**Sensitivity is still reported.** For the bins the exclusion touches, `RESULTS.md` records the baseline with and without post-derecho 2020, so the size of the effect is measured rather than argued.

**The case study is unaffected.** SPEC 10 designates the derecho as a qualitative check, to be run against the NASS damage polygons. That treats 2020 as a target year with an external truth, using 2018 and 2019 as its baseline. Thin, but it is qualitative, and it is separate from the evaluation.

## Decision 3. GDD is computed once, at the AOI centroid

D5 said "at the field centroid." Under D17 that is 3,445 Open-Meteo series for a temperature field that varies by a fraction of a degree across a 30 km AOI, and whose field-to-field difference is a field-year constant that cancels anyway. What matters is the year-to-year series, which is shared across the AOI. One daily Tmax and Tmin series at the AOI centroid, eight years, from the Open-Meteo archive. If a later diagnostic shows a temperature gradient across the AOI that matters, it becomes a second series, not 3,445.

## Decision 4. Bin width is the narrowest that leaves most zone-year-bins observed

A phenology bin needs to be narrow enough to resolve a stage and wide enough that a zone has at least one clear observation in it most years. With about 25 clear observations spread over roughly 2,700 GDD, the mean gap is about 110 GDD, but cloud gaps are not uniform.

**Rule, stated before the data is binned:** choose the narrowest bin width, from the candidates 150, 200, 250, 300 GDD, such that at least 90% of zone-year-bins contain at least one observation. Record the coverage for every candidate in `RESULTS.md`. The 90% is a coverage floor, not a tuned quantity; it is chosen so that fewer than one bin in ten per zone-year is an empty cell that the baseline has to skip.

## Documents this changes

`DESIGN.md` D5 gains the NASS origin and the AOI-centroid amendment, with the reasoning that D17 changed what GDD alignment is for. `SPEC.md` Section 8 gains the origin, the known-events table, and the bin-width rule. `config.py` gains `KNOWN_EVENTS`. `crops.py`, when written, carries the NASS commodity name per CDL code. Issues #5 and #6 close with a pointer here.

## What Step 2 needs from outside

A free USDA NASS Quick Stats API key, from quickstats.nass.usda.gov/api. The query is state IA, commodity CORN or SOYBEANS, statistic category PROGRESS, unit PCT PLANTED, weekly, 2018 to 2025. Sixteen crossing dates in total. Confirm the exact unit string against the API before relying on it.

---

## Amendment, 2026-09-17, after measurement

Made after `scripts/step2_measure.py` ran and before the baseline was built on real data. The evidence is in `RESULTS.md` under "Parameter evidence: cloud threshold and bin width". Two things are decided; one earlier rule is retired, and the reason is stated rather than the threshold quietly moved.

### Decision 5. Minimum field clear fraction is 50%

The diagnostic measured one concern: whether zones seen on a partly clouded date read differently from the same field at the same stage on a clear date. Above 25% clear they do not. Below 25% there is a small low bias, minus 0.010 NDVI under 10% clear, consistent with missed cloud edge or haze.

There is a second concern the diagnostic did not measure, and it is specific to D17. The field median on a date is taken over the zones that are visible. Cloud is spatially contiguous, so a 25% visible field is a 25% contiguous patch, and its median is that patch's centre rather than the field's. Every visible zone is then measured against the wrong centre. At one visible zone the median is that zone and its relative index is exactly zero, an observation that says nothing.

Fifty percent covers the second concern by construction: a median over at least half the zones is a median over the majority of the field. It costs about 1.2 points of bin coverage against no threshold at all. Ninety percent would cost a further 3 points for no measured benefit, since the absolute bias is already gone above 25%.

`MIN_FIELD_CLEAR_FRAC = 0.50`.

### Decision 6. Bin width is 200 GDD, chosen for stage resolution, and the coverage rule is retired

**What the original rule said.** Decision 4: the narrowest of 150, 200, 250 and 300 GDD such that at least 90% of zone-year-bins hold an observation.

**What it selected.** 300 GDD, and only at a cloud threshold of 50% or below. 250 reaches 88%, 200 reaches 84%.

**Why it is retired rather than followed.** The shortfall is not a counting artifact; excluding partial season-end bins moves coverage by under two points. It is genuine sparsity at 400 to 800 GDD, late May into June, Iowa's cloudiest weeks. Widening the bins does not add a single observation to that window. It makes the cells larger so that the same sparse observations fall into fewer, bigger cells, and the coverage number passes. A rule that can be satisfied by its own mechanism without improving the thing it was meant to protect is measuring the wrong quantity.

The rule conflated two separate questions. How wide a bin should be is a question about **resolution**: within a bin, a zone's relative standing should be roughly constant, or the baseline averages across a change. How much history a baseline cell rests on is a question about **support**. Coverage was a proxy for support, and a leaky one.

**Resolution.** A zone's relative standing changes fastest between emergence and canopy closure, roughly 0 to 800 GDD, and is comparatively stable from canopy closure through grain fill. 200 GDD gives four bins across that early window and about fourteen across a season. 300 gives two or three early bins and nine or ten overall. 150 would be finer still but drops coverage to 74% and thins every cell. 200 is chosen as the narrowest width that does not make cells routinely empty, stated as a judgment about what the baseline must resolve, not derived from a coverage figure.

**Support.** The baseline already skips empty cells and records `n_prior_years` per zone-year-bin. That count is the quantity the coverage rule was standing in for, so it is enforced directly: a cell whose baseline rests on fewer than three prior years is not used for the label and not ranked. Three is the smallest count at which a mean of prior years is meaningfully a history rather than one or two readings. Fixed here, before the distribution of `n_prior_years` has been computed. If it excludes a large share of cells, that is reported as a finding, not treated as a reason to lower the floor.

**Pre-registered concern.** The decision record for this step said, before measurement: "next Fable moment is if the bin-coverage rule picks 300 GDD (too coarse to resolve stages)." Both the rule and the concern about its likely answer were written down in advance, and they conflicted. This amendment resolves a pre-stated conflict; it is not a threshold moved after an inconvenient number.

**What was not unreasonable.** 300 GDD would have served the core evaluation. The primary label is an end-of-season residual, and late-season relative standing is stable enough that 300 and 200 bin it similarly. The cost of 300 falls on the early-season signals of Step 5, which is where resolution matters. That is worth saying so the choice reads as a trade-off and not as the only defensible answer.

`BIN_WIDTH_GDD = 200`. `MIN_PRIOR_YEARS = 3`. `BIN_WIDTH_CANDIDATES_GDD` and `BIN_COVERAGE_MIN` are removed from config; the measurement script and its results stay as the record of why.

### Reporting owed by Step 2

- Bin coverage at 200 GDD and 50% clear, the figure the retired rule would have scored.
- The distribution of `n_prior_years` per cell for the held-out years 2023, 2024 and 2025, and the share of cells the floor of three excludes, overall and by bin.
- The baseline with and without the post-derecho exclusion for the bins it touches (Decision 2).
- The across-zone corn-versus-soybean correlation (architecture note, Decision 2).
- Per-field green-up spread around the NASS anchor (Decision 1).


---

## Second amendment, 2026-09-17, after the support gate tripped

Made after `scripts/build_baseline.py` ran on all eight seasons and the prior-year gate tripped in four places, all 2023 late-season bins. Evidence and the structural cause are in `RESULTS.md`, "Reporting owed by Step 2", item 2. No label and no evaluation number exist.

### What the trip was, and what it was not

The floor of three prior years excludes 30 to 55% of 2023's cells in bins 11 to 13 and all of bin 15. The cause is measured: the derecho exclusion removes 2020 from exactly those bins, 2023 has only five prior years to begin with, and three of the remaining four then have to be cloud-free. 2024 and 2025 pass with room to spare. Bin 15 cannot pass by construction, because only one or two prior crop-years reach 3,000 GDD before 30 September.

Two things were unpinned when the gate was set, and both bear on whether the trip matters.

First, **which bins the label uses** was never stated. The gate was applied to every bin uniformly, but a label is an aggregate over a window, and a zone-year can carry a label with some cells in the window missing. Per-cell exclusion was the wrong granularity.

Second, **the label baseline is not the feature baseline.** SPEC Section 10, circularity control, requires the label residual to use a baseline estimated leave-one-year-out, excluding the target year and computed separately from the strictly-prior feature baseline. That view has not been built. The gate was measured on the strictly-prior baseline, which for 2023's late bins has four usable years; the leave-one-year-out baseline for the same cells has six (2018, 2019, 2021, 2022, 2024, 2025). The cells that tripped are the strictly-prior late-bin cells, and neither the label nor the rung 1 feature uses those cells in that form.

This is the second gate today measured on an intermediate rather than on the thing it protects. The coverage rule measured cell presence when it meant baseline support; this gate measured per-cell support when it meant label and feature availability. The pattern is recorded so the next gate is set on the deliverable.

### Decision 7. The label window, the gap and the feature window are pinned to growth stages

Anchored to Abendroth, Elmore, Boyer and Marlay (2011), *Corn Growth and Development*, Iowa State University Extension PMR 1009, for a 2,700 GDD hybrid: VT about 1,135 to 1,350 GDD from planting, R1 silking about 1,400 to 1,500, R5 dent about 2,300, R6 black layer about 2,700. In 200 GDD bins:

| window | bins | GDD | stage | why |
|---|---|---|---|---|
| feature | 0 to 6 | 0 to 1,400 | emergence through VT | vegetative growth; what an in-season scout can act on |
| gap | 7 | 1,400 to 1,600 | R1 silking | the SPEC Section 10 temporal gap, one bin |
| label | 8 to 11 | 1,600 to 2,400 | R2 blister through R5 dent | grain fill, where yield is determined and canopy still reflects photosynthetic capacity |

Bins 12 and 13, R5.5 to R6, are excluded from the label on purpose. NDVI falls through senescence, and a low reading there is confounded between stress and early maturity. Bins 14 and 15 are past physiological maturity for most crop-years.

**The label** for a zone-year is the mean NDVI residual over its supported cells in bins 8 to 11, computed against the leave-one-year-out baseline. At least one supported cell is required; the number of supporting cells is recorded per zone-year. Underperforming is the bottom decile of that label within field-year, over the zones that carry a label, as SPEC Section 10 already states.

**The rung 1 feature** for a zone-year is the NDVI residual in its latest supported cell within bins 0 to 6, against the strictly-prior baseline. At least one supported cell is required; the bin used is recorded.

Soybean uses the same bins. Its development is photoperiod-driven and the correspondence to R-stages is looser, which D5 already records as a weakness reported rather than hidden. Choosing a different window for soybean would put a crop name in a conditional; the crop-specific part, the GDD origin, is already in the registry.

This formulation makes the product claim concrete: rank by vegetative-stage anomaly, score against grain-fill outcome, with silking as the gap. The feature never sees the label window.

### Decision 8. The leave-one-year-out label baseline is built

Required by SPEC Section 10 and not yet implemented. Same three formulas as D17, same known-event exclusion, same field median, same floor of three supporting years, but the window is every other year in the record rather than strictly prior years. Two views, `baseline` and `label_baseline`, and the Step 4 split tests assert that the feature side never reads a year at or after its target and the label side never reads its own target year.

### Decision 9. The gate is re-specified at the granularity of what it protects

**Original.** The floor may exclude at most a fifth of zone-year-bin cells anywhere in the held-out years. Tripped as recorded.

**Re-specified.** In each held-out year, separately:

- share of zone-years with **no label** (zero supported cells in bins 8 to 11 against the leave-one-year-out baseline) at most 20%;
- share of zone-years with **no feature** (zero supported cells in bins 0 to 6 against the strictly-prior baseline) at most 20%.

Bins that fewer than three prior crop-years structurally reach are undefined, not failed, and are outside both windows by construction.

**This has not been measured.** The amendment is written before the number exists. If either share exceeds 20% in any held-out year, Step 2 stops and the question of which years are held out goes to the user as a conversation about the frozen protocol, per CLAUDE.md rule 7. It does not become a further amendment.

### Decision 10. The floor stays at three

Lowering it after the gate tripped is the forking-paths problem in its plainest form, and the reasoning that set it, a mean of two readings is not a history, has not changed.

### Rejected

**Drop 2023 as a held-out year.** Touches SPEC Section 10, which requires a conversation with the user, not a decision record. Also premature: the correctly specified gate has not been measured, and the cells that tripped are not the ones the label uses.

**Narrow the derecho window.** Lodged corn does not recover, so 2020 after 10 August is contaminated through harvest. Physically unjustified. Scoping the exclusion spatially to the NASS damage polygons rather than the whole AOI is noted as a possible refinement if the re-specified gate still trips; it adds a data dependency and is not adopted now.

### What the tripped cells still affect

The strictly-prior late-bin cells for 2023 are used by late-season signals at Step 5 (S4 velocity, S5 persistence) and by the support behind the B1b null, whose prior-year residual for 2023 rests on 2021's baseline. Both are reported when reached; neither is in the rung 1 evaluation.
