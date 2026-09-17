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
