# 🛰️ OrbitalScout

### Telling a farmer which parts of a field to walk today, and measuring whether the answer is any good.

> **Status: Step 0 done, Step 1 in progress.**
> The plan and the scoring rules were written and committed *before* any data was downloaded, with
> timestamps to prove it. **No accuracy result exists yet.** Every unmeasured figure is marked `[TBD]`.
> There are no estimated or placeholder numbers anywhere in this repository.

---

## 📋 What this is, in plain English

Picture a farmer with a 100 acre field. Somewhere in it, a patch of crop is struggling. They have two hours before dark. **Which part do they drive out to?**

Satellites photograph every field on Earth every few days, for free. So you would think you could just look at the picture and find the sick patch. You can't, and the reason is the whole point of this project:

> **The worst-looking parts of a field are almost always the parts that look bad every single year.**
>
> The sandy corner. The wet dip that never drains. The strip the tractor compacted years ago. A satellite map faithfully highlights all of them, every time. The farmer has known about them for twenty years. It is a map of the dirt, not a map of today's problem.

**So this project asks a different question.** Instead of "which patch looks worst?" it asks **"which patch is doing worse than it normally does at this point in the summer?"** A patch that is usually fine and is suddenly lagging is worth driving out to see. A patch that is always bad is not news.

That comparison needs history, so the system looks at eight years of satellite images, learns what normal looks like for every 30 metre square of every field, and then ranks the squares by how far below their own normal they are today. The output is a to-do list: *check these spots first.*

### The part that is actually new

Tools that draw these maps already exist and are sold commercially. **What appears to be missing is anyone checking whether the maps are right.**

Reading through the published work and the commercial documentation, you find plenty of systems that highlight patches, and essentially no one reporting how often the highlighted patch actually had a problem. No hit rate. No false alarm rate. No comparison against an obvious dumb guess.

So the real deliverable here is not the map. **It is the scoring system that tells you whether the map is worth trusting**, including an honest comparison against the dumbest possible strategy: *"just go back to wherever was bad last time."* That turns out to be surprisingly hard to beat, and this project has committed in writing, in advance, to publishing the result even if it loses.

### Why a hiring manager might care

| What it demonstrates | Where to look |
|---|---|
| Designing an evaluation *before* seeing data, so results cannot be quietly tuned | [`SPEC.md`](SPEC.md) Section 10, committed before any download |
| Catching a subtle bug that would have faked a good result | [`docs/reviews/2026-09-14-council-label-review.md`](docs/reviews/) |
| Changing course when a measurement contradicted the plan, and writing down why | [`RESULTS.md`](RESULTS.md) findings 1 to 3 |
| Test-first discipline on code that fails silently rather than loudly | [`tests/test_melt.py`](tests/test_melt.py) |
| Data engineering at scale on a laptop, with the arithmetic done first | ~180 million rows, ~3 GB, no cloud bill |
| Knowing what *not* to build | No Docker, no orchestrator, no API, no ML model so far |

---

## 🔍 A Worked Example

One 30 metre square inside a real Iowa cornfield, July 2020, measured by this pipeline:

| date | greenness (NDVI) | what it means |
|---|---|---|
| 3 July | 0.611 | corn filling in |
| 10 July | 0.705 | still growing |
| 28 July | 0.871 | full canopy |
| 30 July | 0.852 | at peak |

Eight other July dates are missing from that list because clouds covered the field. **Those dates are simply absent, not recorded as zero.** That distinction sounds pedantic and is the single most dangerous bug in the project: a cloudy day stored as "greenness 0" would look exactly like a dead crop, nothing would crash, and every number downstream would be quietly wrong. There is a test guarding it, and that test was checked by deliberately reintroducing the bug to confirm it catches it.

To find the struggling patches, the system compares this square's curve to the same square's curve in previous years, and to the rest of its own field on the same day.

---

## 🎯 The Core Idea, Stated Precisely

Ranking zones by **absolute** vegetation index reproduces the permanent soil map. Those zones score badly every year for reasons unrelated to any emerging problem.

The actionable signal is **deviation from a zone's own history**.

One refinement makes this work with only eight seasons of data. Rather than compare each zone to its own absolute history, compare it to **how it usually stands relative to the rest of its own field.** Crop type, weather, planting date and management are all properties of the *field-year*, not the zone, because Corn Belt fields rotate as whole units. Measuring within the field cancels all of them at once. (This is the within transformation from panel econometrics, arrived at by asking what level each variable actually varies at.)

---

## 🏗️ Architecture and Pipeline

```
   Earth Engine (one expression)                 Local (DuckDB over Parquet)
 ┌──────────────────────────────────┐        ┌────────────────────────────────┐
 │ Sentinel-2 L2A  ──┐              │        │                                │
 │ Cloud Score+    ──┤ mask         │        │  melt ──> fields               │
 │                   │ index @10m   │ export │           zones                │
 │ USDA CSB        ──┤ reduce @30m  │ ─────> │           zone_obs             │
 │ (fields + crop)   │ EPSG:5070    │  cube  │              │                 │
 │                   │              │        │              v                 │
 │ Open-Meteo GDD  ──┘              │        │  baseline ──> signals ──> rank │
 └──────────────────────────────────┘        │                        │       │
                                             │                        v       │
                                             │   evaluate: precision@k, lift, │
                                             │   blocked splits, null models  │
                                             └────────────────┬───────────────┘
                                                              v
                                              static MapLibre demo (no backend)
```

**In words:** Google's satellite platform does the heavy lifting: throw away cloudy pixels, compute greenness, average up to 30 metre squares, and hand back one compact file per season. A laptop then reshapes those files into a database table, works out what normal looks like per square, ranks the squares, and scores the ranking.

**Masking, CRS reprojection and zonal aggregation happen exactly once, inside a single Earth Engine expression.** Every signal reads one clean feature table and none reimplements any of them, because two competing definitions of "clear observation" would make the persistence signal meaningless.

The local reshape is a reshape and nothing else: no masking, no reprojection, no thresholds. A masked pixel becomes an **absent row**, never a zero.

---

## 🛠️ Technical Stack

| Layer | Choice | Why this and not the obvious alternative |
|---|---|---|
| Imagery and masking | Google Earth Engine | Cloud Score+ lives here, and doing pixels elsewhere would mean two grids and a co-registration problem |
| Cloud masking | Cloud Score+ `cs` >= 0.60 | Shadow is the dominant false positive and the SCL band handles it worst |
| Field boundaries | USDA CSB, Earth Engine asset | USDA already solved road and rail splitting; the Common Land Unit is legally unavailable |
| Storage | DuckDB over Parquet | About 180M rows, roughly 3 GB. Chosen for join ergonomics at small scale, not for scale |
| Raster IO | rasterio | Reads the exported cube. Nothing else touches a raster |
| Compute | NumPy, pandas, CPU only | Zero marginal cost is a project goal |
| Testing | pytest | Split logic and the melt are the highest-value tests in the repo |
| Demo | MapLibre GL JS, one HTML file | A live API is a thing that breaks in six months when a free tier lapses |

**Deliberately not used:** PostGIS, Spark, Sedona, Docker, Kubernetes, any workflow orchestrator, any backend API, any frontend framework, and so far any machine learning model. The pipeline is five linear stages in a Makefile.

---

## 🧮 Mathematical Foundation

### Vegetation indices

Computed per 10m pixel **before** aggregation to 30m, because a mean of ratios is not a ratio of means.

$$NDVI = \frac{B8 - B4}{B8 + B4} \qquad NDRE = \frac{B8 - B5}{B8 + B5} \qquad NDWI = \frac{B8 - B11}{B8 + B11}$$

NDVI tracks canopy biomass, NDRE tracks chlorophyll through the red edge, and the Gao form of NDWI tracks vegetation water content, which is what lets it catch water stress before visible decline.

### The within-field relative residual

For zone $i$ in field $f$ at phenology bin $b$ in year $t$:

```
relative_index(i, t, b) = index(i, t, b) - median over zones in f of index(., t, b)
baseline(i, b)          = mean over prior years of relative_index(i, ., b)
residual(i, t, b)       = relative_index(i, t, b) - baseline(i, b)
```

The field centre is a **median**, not a mean, so that an anomaly covering a large share of the field cannot drag the centre toward itself and shrink its own residual.

### Phenology alignment

The baseline is aligned by accumulated growing degree days rather than calendar day, because two zones on the same date may be at different growth stages:

$$GDD = \sum_{d} \max\left(0, \frac{\min(T_{max}, T_{cap}) + \max(T_{min}, T_{base})}{2} - T_{base}\right)$$

Corn uses $T_{base} = 50°F$ and $T_{cap} = 86°F$. Soybean development is photoperiod and maturity-group driven with no authoritative GDD-per-stage table, so its alignment is weaker. That limitation is reported, not hidden.

### Evaluation

$$\text{precision@}k = \frac{|\\{\text{top-}k\text{ ranked}\\} \cap \\{\text{underperforming}\\}|}{k} \qquad \text{lift} = \frac{\text{precision@}k}{\text{precision@}k \text{ of the baseline}}$$

The primary label is the bottom decile of residuals within each field-year, so the base rate is **10% by construction**, fixed before any data was pulled. That makes lift over random arithmetic rather than a quantity discovered afterwards.

---

## 🌟 What the System Does

### 🛰️ Ingestion with one definition of everything
Sentinel-2 joined to Cloud Score+ by `system:index`, masked, indexed and reduced to 30m zones in a single Earth Engine expression, reprojected once to EPSG:5070. A CRS mismatch raises rather than silently reprojecting.

### 📉 Baseline-relative anomaly ranking
Each zone is scored against its own phenology-aligned history of relative standing, over five to seven prior seasons, not against a global threshold or a neighbouring field.

### 🧪 Six signals, admitted one at a time
S1 temporal anomaly, S2 spatial anomaly, S3 multi-index divergence, S4 velocity, S5 persistence, S6 soil-context residual. **A signal ships only if it measurably improves lift.** Ones that do not are removed and their null result recorded. Building a signal does not entitle it to ship.

### 📊 A ranking evaluation harness
precision@k at a scouting budget, lift over random, lift over a commercial NDVI k-means baseline, and lift over two null models. Splits blocked by field **and** year, never randomly, because adjacent zones are spatially autocorrelated and are not independent samples.

### 🗺️ A static, precomputed demo
Two maps side by side, same field, same date, with a scouting budget slider. No backend, so nothing expires.

---

## 🚫 What This Deliberately Does Not Do

These are constraints, not gaps.

- **No disease or pest identification.** At 10m ground sample distance the signal to distinguish causes is not present. Claiming otherwise would be an overclaim.
- **No yield prediction** in physical units.
- **No real-time operation.** Cadence is governed by cloud-free satellite revisit. Output updates on each cloud-free pass.
- **No prescription maps** or machine-executable output.
- **No live API or hosted service.** The demo is precomputed and static.
- **No coverage outside the contiguous United States.** Crop labels and soil data are US-specific.

---

## 📊 Results

### Step 0: clear observation count (measured)

Story County, Iowa. Distinct acquisition dates on which a pixel was clear, sampled over corn and soybean cropland. Full detail in [`RESULTS.md`](RESULTS.md).

| year | dates | p10 | median | p90 | AOI under 2+ orbits |
|---|---|---|---|---|---|
| 2017 | 26 | **5** | 11 | 14 | 65% |
| 2018 | 58 | 10 | 22 | 26 | 64% |
| 2019 | 61 | 8 | 19 | 23 | 64% |
| 2020 | 61 | 12 | 25 | 29 | 65% |
| 2021 | 60 | 16 | 32 | 36 | 64% |
| 2022 | 61 | 12 | 25 | 29 | 64% |
| 2023 | 61 | 17 | 30 | 34 | 64% |
| 2024 | 60 | 17 | 29 | 34 | 65% |
| 2025 | 67 | 15 | 24 | 31 | 64% |

**Gate G-0 passed**: median 25 against a threshold of 6. Three findings changed the design as a result:

1. **2017 is single-satellite** and not comparable to later years. Excluded.
2. **Two orbits split the county.** 64% of it gets roughly twice the observations of the rest, along a boundary with no agronomic meaning. The AOI is restricted to the doubly covered region.
3. **Crop rotation halves per-zone history.** Crop changes across 82% of consecutive year pairs, leaving 2 to 4 seasons per zone-crop. This is what forced the within-field relative baseline.

### Evaluation results

No evaluation has been run. This table is the output of the build, not a target.

| Metric, primary label | NDVI k-means (B2) | Level persistence (B1a) | Anomaly persistence (B1b) | OrbitalScout |
|---|---|---|---|---|
| precision@budget | `[TBD]` | `[TBD]` | `[TBD]` | `[TBD]` |
| precision@5% | `[TBD]` | `[TBD]` | `[TBD]` | `[TBD]` |
| precision@10% | `[TBD]` | `[TBD]` | `[TBD]` | `[TBD]` |
| precision@20% | `[TBD]` | `[TBD]` | `[TBD]` | `[TBD]` |
| False positive rate @10% | `[TBD]` | `[TBD]` | `[TBD]` | `[TBD]` |

**Lift over B1b, anomaly persistence, at the scouting budget is the headline number.**

### A negative result is pre-committed as valid

The headline null ranks zones by their residual the last time this crop was grown, predicting that whatever was unusually bad then is unusually bad again. Because problems recur in the same places, it is genuinely hard to beat, and there is a real chance OrbitalScout does not beat it.

If that happens it is reported as the headline finding, in these words: *prior-year anomaly explains this year's anomaly, and the anomaly-persistence null was not beaten at the scouting budget.* The protocol will not be retuned, neither null will be dropped, and the project will not be reframed to avoid saying so.

This paragraph is in the repository before the results are, specifically so that it cannot be quietly removed afterwards.

---

## ⚙️ Installation

### Prerequisites

- Python 3.11 or higher, developed on 3.14
- A Google Earth Engine account and cloud project, free for non-commercial use
- About 5 GB of disk space for the exported cubes and the DuckDB store
- CPU only. No GPU is used anywhere in this project

### Setup

```bash
git clone https://github.com/CaiZhengTech/orbitalscout.git
cd orbitalscout

python -m venv .venv
source .venv/bin/activate        # Linux and macOS
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### Earth Engine authentication

```bash
earthengine authenticate
export ORBITALSCOUT_EE_PROJECT=your-ee-project-id
```

Sign up at [earthengine.google.com/signup](https://earthengine.google.com/signup/) if you do not have a project yet.

---

## 🚀 Usage

### Run the Step 0 gate

```bash
python scripts/step0_observations.py --project $ORBITALSCOUT_EE_PROJECT
```

Counts clear observations per zone for every season and evaluates gate G-0. Takes roughly six minutes.

### Run the tests

```bash
python -m pytest tests/ -q
```

### Remaining stages

`[TBD]`. Steps 1 through 4 are not yet runnable. The Makefile lands with Step 1.

---

## 📁 Project Structure

```
orbitalscout/
├── config.py                 # AOI, years, thresholds. One place, one definition each
├── crops.py                  # crop registry, keyed by CDL code. No crop name in a conditional
├── ingest/
│   ├── gee.py                # S2 + Cloud Score+ + index + reduce, one expression, cube export
│   ├── melt.py               # cube to long rows. A reshape only: no mask, no reproject
│   ├── masking.py            # the single clear-observation threshold
│   ├── boundaries.py         # CSB field selection, inward buffer, field_id painting
│   ├── cdl.py                # G-4 mismatch rate only. Not a source of zone crop labels
│   ├── soil.py               # SSURGO drainage class and slope
│   ├── weather.py            # Open-Meteo, GDD accumulation
│   └── crosscheck.py         # independent Planetary Computer pull on a zone sample
├── zones.py                  # zone construction, inward buffer
├── features.py               # index computation over the exported zone table
├── baseline.py               # within-field relative, phenology-aligned baseline
├── signals.py                # six functions, one shared signature
├── rank.py                   # combination and sort
├── baselines.py              # persistence nulls, NDVI k-means
├── evaluate.py               # precision@k, lift, blocked splits
└── export.py                 # precomputed GeoJSON for the demo

scripts/step0_observations.py # gate G-0
tests/
├── test_splits.py            # leakage tests. The most important tests in the repo
├── test_melt.py              # a masked pixel becomes an absent row, never a zero
└── test_baseline.py          # baseline against a known synthetic series
demo/index.html               # MapLibre, one file, no backend
docs/reviews/                 # dated design reviews, all predating the data
```

---

## 🧪 Testing Philosophy

**Test what fails silently. Skip what fails loudly.**

Tested: split logic, the cube-to-rows melt, baseline computation, CRS assertions, nodata handling.

Not tested: satellite API responses, visual output, anything needing network access in CI.

The melt tests were written before `melt.py` existed, and the load-bearing one was then mutation checked: removing the value mask from the keep condition, which is exactly the bug it guards against, turns it red while the others stay green. A test that cannot fail is not evidence.

The test that matters most is the split test. A random split of zones leaks spatially autocorrelated neighbours into the test set and produces an excellent number that means nothing.

---

## 📐 Design Documents

| File | What it is |
|---|---|
| [`SPEC.md`](SPEC.md) | What gets built. Contains the frozen evaluation protocol (Section 10) |
| [`DESIGN.md`](DESIGN.md) | Why, and what was rejected. Decision records D1 through D18 |
| [`RESULTS.md`](RESULTS.md) | Measured outcomes, including null results |
| [`CLAUDE.md`](CLAUDE.md) | The operating agreement: hard rules, build order, what not to build |
| [`docs/reviews/`](docs/reviews/) | Dated architectural reviews. All predate the data that could have tuned them |

---

## 📚 References and Prior Art

Cited rather than obscured. The detection components exist in prior work.

1. **EOSDA Crop Monitoring.** Commercial k-means zoning on a vegetation index into 2 to 7 zones, with field prioritisation as an NDVI-change leaderboard. This is baseline B2.
2. **Microsoft FarmVibes.AI**, `farm_ai/agriculture/change_detection`. NDVI outliers across dates, cross-date within-season rather than baseline-relative across years. Read as an architecture reference, not adopted.
3. **Burke et al.**, Earth Observation-based Anomaly Detection (EOAD). Within-parcel distributional anomaly thresholds, validated on rice. The closest published analog to the scouting-priority goal. Does not use ranking metrics.
4. **Brown et al. (2025)**, *AlphaEarth Foundations*. 64-dimensional 10m annual embeddings. No published evaluation at sub-field anomaly scale.
5. **Hunt, Abernethy, Beeson, Bowman, Wallander and Williams**, *Crop Sequence Boundaries: Delineated Fields Using Remotely Sensed Crop Rotations*, USDA NASS and ERS.
6. **Pasquarella et al.**, Cloud Score+ for Sentinel-2 cloud and shadow assessment, Google Earth Engine.
7. **Rouse et al. (1974)**, *Monitoring the Vernal Advancement and Retrogradation of Natural Vegetation*, NASA/GSFC. The original NDVI paper.
8. **Gao (1996)**, *NDWI: a normalized difference water index for remote sensing of vegetation liquid water from space*, Remote Sensing of Environment.
9. **Allen et al. (1998)**, FAO Irrigation and Drainage Paper 56. Source for the GDD conventions.
10. **Wooldridge**, *Econometric Analysis of Cross Section and Panel Data*. The within transformation, which is what the field-relative baseline is.

The contribution claim is framed as **"rare and not found in a bounded search"** rather than "never done," because it rests on three research passes rather than on exhaustive proof of absence.

---

## 🙏 Acknowledgements

- **USDA NASS and ERS** for Crop Sequence Boundaries and the Cropland Data Layer, both public domain.
- **ESA and the Copernicus programme** for free and open Sentinel-2 imagery.
- **Google Earth Engine** for Cloud Score+ and free non-commercial compute, and **Samapriya Roy** for the community catalog that hosts the CSB asset.
- **Open-Meteo** for free historical weather.
- **Microsoft Planetary Computer** for an independent Sentinel-2 source used as a cross-check.

## 📄 License

`[TBD]`
