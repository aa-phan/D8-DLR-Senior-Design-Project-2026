# Anomaly Detection Model Validation Record

> **Scope change 2026-10-12.** The project no longer rates corridors; each of the four cities
> (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`, i.e. `config.LOCATIONS`) is an independent
> rating point (see `point_scope.md`). The anomaly model is now **per city**: one artifact
> `anomaly_{city}.joblib` per city, fitted on that city's own rows only, with no two-city
> pooling. **Every measurement below (selected estimators and contaminations, rates, verdicts,
> load correlations) is corridor-era (retired 2026-10-12)**: it was produced by pooled
> two-endpoint-city corridor models, is kept unchanged as history, and has not been re-measured
> per city. Per-city refit has not been run (it needs live Open-Meteo and ERCOT data); until it
> is, no per-city artifact exists and the model branch is absent (see Limitations).

**Status:** Ratified as a record of measured fact — the numbers below are settled (a direct
transcription of a completed, reproducible run against real historical data). Both measured corridors' (corridor-era, retired 2026-10-12)
Verdicts read **MET** against both halves of the stated Expectation. That result is reported
plainly, per D-07, exactly as it came out — it is not a foregone conclusion just because it is a
pass: three of the five candidate/contamination combinations measured here (`EllipticEnvelope`,
and `IsolationForest` at low contamination) would have read NOT MET on the second half of the
bar had they been selected instead, and the model's false-positive rate, while under the ceiling,
is not zero the way the existing rolling baseline's structurally is. Whether the selected
`OneClassSVM` artifact should be trusted as a general-purpose anomaly detector beyond the two
measured injection categories, and whether the pooled two-city training envelope generalizes
past this one-year real window, remain open — see Open Questions.

**Purpose:** This document discharges **ANOM-02** (the anomaly-detection model's false-positive
and false-negative behavior must be validated against real historical data, not synthetic
fixtures, and the results documented) and **D-07** (per the honesty precedent FCST-02 established
in Phase 1: state the expectation before the result, and report the real number whichever way it
comes out). It follows the same working-log shape as `docs/data-science/decisions/
forecasting_model.md`, this workstream's own Phase 1 precedent, and lives alongside it under
`docs/data-science/decisions/`.

## What was built

`backend/anomaly_detector.py::AnomalyDetector.check(raw_data, rating)` gained a third, additive
branch — `_check_against_model` — alongside the two existing heuristic branches
(`_check_against_forecast`, `_check_against_rolling_baseline`). Per D-01, the new branch judges
the **raw** `wind`/`temp`/`solar` readings in `raw_data` against a fitted `scikit-learn` outlier
estimator's learned per-variable envelope — never the derived `rating` the two existing branches
judge. Per D-05/D-06, the branch is strictly additive and one-directional: `check()` was
restructured from an early-return `if`/`elif` dispatch to an accumulate-then-OR pattern, so the
model branch runs *alongside* whichever of the two existing branches also ran (never replacing
either), and the combined verdict is the logical OR of every branch that ran — the model can only
ever add a trip on top of an existing branch's verdict, it can never suppress one.

The persisted per-city artifact is selected through `AnomalyDetector.for_city`, which
lazily loads (and caches) the city's fitted estimator via `_load_city_model_or_none` — an
absent artifact resolves to `model=None` with one logged warning, leaving behavior identical to
the pre-Phase-2 two-branch detector, rather than raising. `backend/anomaly_training.py` is the
offline entry point that assembled the real training/measurement series, ran the
D-03 bake-off across three candidates and five contamination points, and persisted each
corridor's evidence-selected winner. The table is the **corridor-era (retired 2026-10-12)**
result; no per-city selection has been made yet:

| Corridor (retired) | Selected estimator | Selected contamination |
|---|---|---|
| `AUSTIN_CORPUS_CHRISTI` | `OneClassSVM` | 0.001 |
| `MIDLAND_EL_PASO` | `OneClassSVM` | 0.005 |

`AnomalyDetector.check`'s public `(bool, str)` contract is unchanged, and `DLRSafetyMonitor.py`'s
G6 call site and its `except Exception -> _fallback` fail-safe wiring carry **zero diff** — no
exception handler of any kind was added anywhere in `anomaly_detector.py`, so a broken model (a
raising prediction entry point, a corrupt artifact, a feature-count mismatch) still propagates
uncaught, all the way to G6's existing fail-safe boundary, resolving to the city's static
rating exactly as the two pre-existing branches already do. Neither `_check_against_forecast` nor
`_check_against_rolling_baseline` was modified.

## Data provenance

*Corridor-era (retired 2026-10-12) procedure, kept as the record of how the measured numbers
below were produced. The per-city procedure fits each city's own hourly rows (one complete
calendar year per city per `--years`, default `config.ANOMALY_ML_TRAINING_YEARS`) into that
city's own artifact; no pooling across cities.*

The training and measurement series is **not** the live `historical_archive.py` CSV — that file
has zero rows today because Track 1 (Pipeline Integration) has not executed yet, mirroring Phase
1's own sourcing decision. Instead:

1. **Weather.** Hourly historical weather is pulled from the **Open-Meteo Archive API** for each
   corridor's two endpoint cities (`config.CITY_COORDINATES`), one complete calendar year per
   city for this run (see Configuration measured — `--years 1`, not the 3-year config default
   used elsewhere in this codebase).
2. **Pooling, not weakest-link reduction.** Both endpoint cities' raw readings are **pooled**
   (concatenated) into one per-corridor training frame, never reduced via `min()`. This is a
   deliberate departure from the forecasting model's own bottleneck-`min()` convention: this
   model judges each city's own raw sensor reading against a plausible per-variable envelope, not
   a corridor-level derived ampacity rating, so there is no single "bottleneck" reading to reduce
   to — `raw_data` also carries no location identifier at the live `check()` call site that could
   key a per-city model selector, which is the practical reason pooling was chosen over strict
   per-city models (RESEARCH.md Architecture Pattern 3).
3. **Dropped, never imputed.** Rows failing `DLRSafetyMonitor`'s G3 physical bounds
   (`WIND_BOUNDS`, `TEMP_BOUNDS`, `SOLAR_BOUNDS`) or carrying a null value are dropped before
   fitting, never imputed.
4. **Feature set.** The fitted features are exactly the three raw variables —
   `air_temp`/`wind_speed`/`solar_radiation` — with **no time-of-day encoding**, because
   `raw_data` carries no timestamp at the `check()` call site; a feature the inference path
   cannot compute would leave the model branch permanently unable to run.

**Actual assembled window (both corridor-era corridors, from the fresh run behind this document — see
Configuration measured for the exact command):** 17,520 pooled hourly rows per corridor,
spanning **2025-01-01T00:00:00+00:00 through 2025-12-31T23:00:00+00:00**. After the chronological
fit/holdout split (never shuffled — the estimator is measured only against rows strictly later
than anything it was fitted on): **13,140 fit rows** and **4,380 holdout rows** per corridor.

## Configuration measured

A reader should be able to reproduce this run from the values below alone. All are the actual
landed `backend/config.py` constants at the time of this run. The reproduction commands are:

```
.venv/bin/python3 backend/anomaly_training.py --bakeoff --years 1
.venv/bin/python3 backend/anomaly_training.py --characterize-load
```

| Parameter | Value | Source |
|---|---|---|
| Backfill depth (this run) | 1 complete calendar year (2025) per endpoint city | CLI `--years 1`, overriding `config.ANOMALY_ML_TRAINING_YEARS` (3 years) for this measurement run |
| Holdout fraction | 0.25 | `config.ANOMALY_ML_VALIDATION_HOLDOUT_FRACTION` |
| Contamination grid | (0.001, 0.005, 0.01, 0.02, 0.05) | `config.ANOMALY_ML_CONTAMINATION_GRID` |
| Selected contamination (corridor-era `AUSTIN_CORPUS_CHRISTI`) | 0.001 | `data/models/anomaly_validation_report.json` |
| Selected contamination (corridor-era `MIDLAND_EL_PASO`) | 0.005 | `data/models/anomaly_validation_report.json` |
| Injection rate | 0.02 | `config.ANOMALY_ML_INJECTION_RATE` |
| False-positive ceiling | 0.05 | `config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE` |
| Kernel-candidate (`OneClassSVM`) training-row cap (bake-off sweep only) | 5,000 | `config.ANOMALY_ML_SVM_MAX_TRAIN_ROWS` |
| Random seed | 20260924 | `config.ANOMALY_ML_RANDOM_SEED` |
| Feature columns (fit order) | `air_temp`, `wind_speed`, `solar_radiation` | `config.ANOMALY_ML_FEATURE_COLUMNS` |
| Live `raw_data` keys (positional match to feature columns) | `temp`, `wind`, `solar` | `config.ANOMALY_ML_RAW_DATA_KEYS` |
| Untuned tracer contamination (Plan 02-01, superseded by the grid above) | 0.01 | `config.ANOMALY_ML_CONTAMINATION` |
| Model artifact directory | `data/models` (git-ignored) | `config.ANOMALY_ML_MODEL_DIR` |
| Model filename template | `anomaly_{city}.joblib` | `config.ANOMALY_ML_MODEL_FILENAME_TEMPLATE` |
| Observation-frame filename template | `anomaly_observations_{city}.csv` | `config.ANOMALY_ML_OBSERVATION_FRAME_TEMPLATE` |
| Validation report filename | `anomaly_validation_report.json` | `config.ANOMALY_ML_VALIDATION_REPORT_NAME` |
| ERCOT zone substrings (`AUSTIN`, `CORPUS_CHRISTI`; corridor-era run used `AUSTIN_CORPUS_CHRISTI`) | `("SOUTH",)` → matched `["South", "South Central"]` | `config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CITY` |
| ERCOT zone substrings (`MIDLAND`, `EL_PASO`; corridor-era run used `MIDLAND_EL_PASO`) | `("WEST",)` → matched `["Far West", "West"]` | `config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CITY` |
| Load characterization window depth | 1 complete calendar year | `config.ANOMALY_ML_LOAD_YEARS` |
| Load characterization report filename | `anomaly_load_characterization.json` | `config.ANOMALY_ML_LOAD_REPORT_NAME` |

**Each candidate's constructor configuration** (`backend/anomaly_training.py`):

- `IsolationForest(n_estimators=100, contamination=<swept grid point>, random_state=20260924)`
- `EllipticEnvelope(contamination=<swept grid point>, random_state=20260924)`
- `make_pipeline(StandardScaler(), OneClassSVM(kernel="rbf", gamma="scale", nu=<swept grid point>))` —
  scaled because this estimator is scale-sensitive across the three raw features' differing
  units (m/s, °C, W/m²); capped at 5,000 chronologically-earliest fit rows **only during the
  bake-off sweep** (see Limitations for what this means for the final persisted artifact).

## Measurement method

This is **not a regression-accuracy problem — it is an unlabeled binary-classification
problem.** No historical weather archive in this project carries a "this reading was an
anomalous sensor fault" label: Open-Meteo backfill and ERCOT settlements record what actually
happened, not injected sensor faults. That means:

- **False-positive rate** is directly measurable on real, clean, held-out data: the 4,380-row
  chronological holdout slice, strictly later than every row the estimator fitted on.
- **False-negative rate (recall)** only exists against **deliberately injected synthetic
  corruption**, since no real labelled anomaly exists to measure recall against. Two categories
  were injected into the holdout slice, each at `config.ANOMALY_ML_INJECTION_RATE` (0.02) — 88
  rows per category per corridor (`round(4380 * 0.02)`):
  - **`out_of_range`** — exactly one of the three feature columns is replaced by a value
    comfortably beyond `DLRSafetyMonitor`'s own G3 physical bound for that column (30 m/s beyond
    the wind bound, 35 °C beyond the temperature bound, 600 W/m² beyond the solar bound). **This
    category is already caught by G3 upstream in the live pipeline** — G3's range gate rejects
    these rows before G6 (and therefore this model) ever runs on them. It is reported here
    because the measurement infrastructure produces it as a byproduct of the same injection
    machinery, not because it demonstrates the multivariate model's unique value.
  - **`in_range_implausible`** — all three feature values are replaced simultaneously by a
    "clear cold night" triple (high solar irradiance, low temperature, low wind), where each
    individual component is drawn from the fit slice's own *observed* extreme quantile (nearest-
    rank, not interpolated) — so every component value is one the real data actually contains,
    and only the *joint* combination is novel. Every component individually passes G3's per-
    variable range gate. **This is the category that measures what the multivariate model
    uniquely contributes** on top of the deterministic gates and the univariate rolling baseline.

The mean-and-standard-deviation baseline (`AnomalyDetector._check_against_rolling_baseline`) was
scored on the **identical rows** through its own real branch — never a parallel reimplementation
of its band arithmetic — judging the IEEE 738 ampacity derived from those same raw readings
(reproducing `DLRSafetyMonitor._compute_ampacity`'s exact physics call).

## Expectation

The bar this model is judged against, **stated here before any verdict below**. Two parts, both
required:

1. The selected model's false-positive rate on clean held-out real data is **at or below**
   `config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE` (0.05, i.e. 5.00%).
2. Its recall on the **`in_range_implausible`** category is **strictly higher** than the existing
   mean-and-standard-deviation baseline's, on the identical rows — because a model that only
   matches the baseline on the category the baseline structurally cannot see adds nothing the
   existing gate did not already provide.

This bar was chosen, rather than an absolute false-positive-per-week or accuracy target, because
no project document contains an independently sourced anomaly-detection accuracy figure —
inventing one with no citation would be a fabricated baseline, exactly the reasoning
`forecasting_model.md` used for FCST-02.

## Measured results

Every figure below is transcribed directly from `data/models/anomaly_validation_report.json`,
produced by the reproduction command above. All three D-03 candidates are shown at all five
contamination grid points — the losing candidates included, per D-03's no-default-lean
discipline — not only the selected winner's row. Baseline figures are identical across every row
within a corridor (the baseline does not depend on candidate/contamination) and are repeated per
row for direct comparison.

### AUSTIN_CORPUS_CHRISTI — corridor-era (retired 2026-10-12) (17,520 assembled rows; window 2025-01-01 → 2025-12-31; fit 13,140 rows, holdout 4,380 rows; 88 injected rows per category)

| Candidate | Contam. | FP rate | Baseline FP | Recall (out_of_range) | Baseline recall (o-o-r) | Recall (in_range_implausible) | Baseline recall (i-r-i) | Pooled recall | Baseline pooled recall |
|---|---|---|---|---|---|---|---|---|---|
| IsolationForest | 0.001 | 0.00% | 0.00% | 6.82% | 36.36% | 100.00% | 0.00% | 53.41% | 18.18% |
| IsolationForest | 0.005 | 0.11% | 0.00% | 13.64% | 36.36% | 100.00% | 0.00% | 56.82% | 18.18% |
| IsolationForest | 0.01 | 0.34% | 0.00% | 26.14% | 36.36% | 100.00% | 0.00% | 63.07% | 18.18% |
| IsolationForest | 0.02 | 0.68% | 0.00% | 37.50% | 36.36% | 100.00% | 0.00% | 68.75% | 18.18% |
| IsolationForest | 0.05 | 2.65% | 0.00% | 60.23% | 36.36% | 100.00% | 0.00% | 80.11% | 18.18% |
| EllipticEnvelope | 0.001 | 0.00% | 0.00% | 25.00% | 36.36% | 0.00% | 0.00% | 12.50% | 18.18% |
| EllipticEnvelope | 0.005 | 0.00% | 0.00% | 25.00% | 36.36% | 0.00% | 0.00% | 12.50% | 18.18% |
| EllipticEnvelope | 0.01 | 0.00% | 0.00% | 25.00% | 36.36% | 0.00% | 0.00% | 12.50% | 18.18% |
| EllipticEnvelope | 0.02 | 0.00% | 0.00% | 25.00% | 36.36% | 0.00% | 0.00% | 12.50% | 18.18% |
| EllipticEnvelope | 0.05 | 0.00% | 0.00% | 25.00% | 36.36% | 100.00% | 0.00% | 62.50% | 18.18% |
| **OneClassSVM (selected)** | **0.001** | **3.77%** | **0.00%** | **100.00%** | **36.36%** | **100.00%** | **0.00%** | **100.00%** | **18.18%** |
| OneClassSVM | 0.005 | 3.90% | 0.00% | 100.00% | 36.36% | 100.00% | 0.00% | 100.00% | 18.18% |
| OneClassSVM | 0.01 | 4.82% | 0.00% | 100.00% | 36.36% | 100.00% | 0.00% | 100.00% | 18.18% |
| OneClassSVM | 0.02 | 6.99% | 0.00% | 100.00% | 36.36% | 100.00% | 0.00% | 100.00% | 18.18% |
| OneClassSVM | 0.05 | 11.69% | 0.00% | 100.00% | 36.36% | 100.00% | 0.00% | 100.00% | 18.18% |

Winner selection: among the 5 `OneClassSVM` points, pooled recall ties at 100.00%; the tie was
broken by the lowest false-positive rate, which is `contamination=0.001` (3.77%) — the selected
pair. `ceiling_met: true` in the report (3.77% ≤ 5.00%).

### MIDLAND_EL_PASO — corridor-era (retired 2026-10-12) (17,520 assembled rows; window 2025-01-01 → 2025-12-31; fit 13,140 rows, holdout 4,380 rows; 88 injected rows per category)

| Candidate | Contam. | FP rate | Baseline FP | Recall (out_of_range) | Baseline recall (o-o-r) | Recall (in_range_implausible) | Baseline recall (i-r-i) | Pooled recall | Baseline pooled recall |
|---|---|---|---|---|---|---|---|---|---|
| IsolationForest | 0.001 | 0.00% | 0.00% | 11.36% | 36.36% | 100.00% | 0.00% | 55.68% | 18.18% |
| IsolationForest | 0.005 | 0.00% | 0.00% | 29.55% | 36.36% | 100.00% | 0.00% | 64.77% | 18.18% |
| IsolationForest | 0.01 | 0.05% | 0.00% | 36.36% | 36.36% | 100.00% | 0.00% | 68.18% | 18.18% |
| IsolationForest | 0.02 | 0.11% | 0.00% | 48.86% | 36.36% | 100.00% | 0.00% | 74.43% | 18.18% |
| IsolationForest | 0.05 | 0.32% | 0.00% | 65.91% | 36.36% | 100.00% | 0.00% | 82.95% | 18.18% |
| EllipticEnvelope | 0.001 | 0.00% | 0.00% | 25.00% | 36.36% | 0.00% | 0.00% | 12.50% | 18.18% |
| EllipticEnvelope | 0.005 | 0.00% | 0.00% | 25.00% | 36.36% | 0.00% | 0.00% | 12.50% | 18.18% |
| EllipticEnvelope | 0.01 | 0.00% | 0.00% | 25.00% | 36.36% | 0.00% | 0.00% | 12.50% | 18.18% |
| EllipticEnvelope | 0.02 | 0.00% | 0.00% | 25.00% | 36.36% | 0.00% | 0.00% | 12.50% | 18.18% |
| EllipticEnvelope | 0.05 | 0.00% | 0.00% | 25.00% | 36.36% | 100.00% | 0.00% | 62.50% | 18.18% |
| OneClassSVM | 0.001 | 0.98% | 0.00% | 100.00% | 36.36% | 100.00% | 0.00% | 100.00% | 18.18% |
| **OneClassSVM (selected)** | **0.005** | **0.53%** | **0.00%** | **100.00%** | **36.36%** | **100.00%** | **0.00%** | **100.00%** | **18.18%** |
| OneClassSVM | 0.01 | 0.78% | 0.00% | 100.00% | 36.36% | 100.00% | 0.00% | 100.00% | 18.18% |
| OneClassSVM | 0.02 | 1.30% | 0.00% | 100.00% | 36.36% | 100.00% | 0.00% | 100.00% | 18.18% |
| OneClassSVM | 0.05 | 3.47% | 0.00% | 100.00% | 36.36% | 100.00% | 0.00% | 100.00% | 18.18% |

Winner selection: among the 5 `OneClassSVM` points, pooled recall ties at 100.00%; the tie was
broken by the lowest false-positive rate, which is `contamination=0.005` (0.53% — genuinely lower
than `contamination=0.001`'s 0.98% on this corridor's real data, a non-monotonic relationship
worth noting honestly rather than assuming FP rate always increases with contamination). The
selected pair has `ceiling_met: true` in the report (0.53% ≤ 5.00%).

## Load characterization (D-02)

*Corridor-era (retired 2026-10-12) measurement; the zone-substring mapping is now per city (`AUSTIN`/`CORPUS_CHRISTI` use `SOUTH`, `MIDLAND`/`EL_PASO` use `WEST`).*

Transcribed from `data/models/anomaly_load_characterization.json`, produced by
`.venv/bin/python3 backend/anomaly_training.py --characterize-load`:

| Corridor | Zone substrings | Matched ERCOT zone columns | Retrieved window | Load rows | Joined rows | Correlation: `air_temp` | Correlation: `wind_speed` | Correlation: `solar_radiation` |
|---|---|---|---|---|---|---|---|---|
| `AUSTIN_CORPUS_CHRISTI` | `("SOUTH",)` | `South`, `South Central` | 2025-01-01T06:00:00+00:00 → 2025-12-31T00:00:00+00:00 | 8,731 | 8,731 | 0.49 | 0.14 | 0.47 |
| `MIDLAND_EL_PASO` | `("WEST",)` | `Far West`, `West` | 2025-01-01T06:00:00+00:00 → 2025-12-31T00:00:00+00:00 | 8,731 | 8,731 | 0.51 | -0.11 | 0.48 |

Per **D-02**, ERCOT historical load is a **training-time-only signal**: `raw_data` does not carry
load at the live `check()` call site, and wiring it in would touch Track 1's pipeline-wiring
scope — explicitly out of bounds for this workstream (REQUIREMENTS.md Out of Scope table). A
named test (`test_load_is_training_time_only_and_never_reaches_check`, added in Plan 02-03)
asserts all four halves of this boundary together: no source-level import of
`ercot_data_retriever`/`gridstatus` in `anomaly_detector.py`; no "load" name in either feature
config tuple; a fresh import of `anomaly_detector` leaves `gridstatus` out of `sys.modules`; and
`check()` still succeeds on a `raw_data` carrying exactly `wind`/`temp`/`solar`.

A **Pearson correlation measures linear association only** — the moderate positive correlations
against `air_temp`/`solar_radiation` (~0.47–0.51, physically sensible: hotter/sunnier conditions
drive higher grid load) and the much weaker `wind_speed` correlations (0.14 and -0.11) are
evidence of a *weak linear* relationship for wind specifically, not evidence that load is
irrelevant to wind — a nonlinear relationship could exist that Pearson's coefficient cannot see.
ERCOT's weather zones (`South`/`South Central`, `Far West`/`West`) are also a **regional proxy**
far larger than either transmission corridor: the zone-aware selection (verified genuinely
distinct per corridor, per Plan 02-03) is a sanity check against a plausible regional demand
pattern, not a claim that either zone's load figure represents the corridor's own local demand
precisely.

## Verdict

*Corridor-era (retired 2026-10-12) verdicts, kept as history; not re-measured per city.*

**AUSTIN_CORPUS_CHRISTI: MET.** The selected `OneClassSVM` (`contamination=0.001`) measured a
false-positive rate of **3.77%**, at or below the 5.00% ceiling — half 1 met. Its recall on the
`in_range_implausible` category is **100.00%**, strictly higher than the baseline's **0.00%** on
the identical rows — half 2 met. Both halves of the Expectation are met; the record states this
plainly rather than either overstating it or hedging it because it happens to be a positive
result.

**MIDLAND_EL_PASO: MET.** The selected `OneClassSVM` (`contamination=0.005`) measured a
false-positive rate of **0.53%**, at or below the 5.00% ceiling — half 1 met. Its recall on the
`in_range_implausible` category is **100.00%**, strictly higher than the baseline's **0.00%** on
the identical rows — half 2 met. Both halves of the Expectation are met.

**What this means, honestly, beyond the raw MET/NOT MET label:** the `in_range_implausible`
category's rows are the ones this Expectation is actually built to test, and the mean-and-
standard-deviation baseline caught **zero** of them on either corridor (0.00% recall) — the
baseline is univariate over `dlr_amps` and has no mechanism to see a jointly-implausible-but-
individually-plausible combination of three raw variables. The selected `OneClassSVM` model
caught **all 88** injected rows in this category on both corridors. This is the multivariate
signal ANOM-01 asks for, and it is real. The `out_of_range` category's near-100% recall for the
winning candidate is **not** additional evidence of this — per the Measurement method section
above, those rows are already caught by G3 upstream in the live pipeline, so a model's recall on
them is redundant with an existing gate, not a demonstration of added value.

The honest tradeoff this MET verdict does not erase: the selected model's false-positive rate,
while under the ceiling, is **not zero** the way the rolling baseline's structurally is
(`baseline_false_positive_rate: 0.0` in every single measured row, both corridors) — `OneClassSVM`
trips on 0.53%–3.77% of genuinely clean holdout rows, depending on corridor. This is the real
cost of the added caution the model buys: per D-05/D-06, this is acceptable because the branch is
strictly additive and OR-combined — a false trip here can only ever add an extra, correctable
alert on top of the two existing paths, it can never suppress or replace their protection, and a
static-rating fallback is always the safe resolution of any G6 trip. Had either corridor's
ceiling not been met, or had the selected recall not beaten the baseline, D-05/D-06 make clear
that shipping the additive branch would still not have been blocked — a weak or NOT MET model
only ever adds caution and never removes protection the two existing paths already provide. That
this phase's real measurement happened to read MET for both corridors does not change that this
would have been the outcome either way; it changes only whether "MET" or "NOT MET" is the honest
word written above.

**Next step:** given the winning candidate's `contamination` was selected against exactly one
calendar year of real weather and one fixed injection methodology, re-running this bake-off once
more historical data accrues (or once Track 1's live pipeline history is available) would be the
natural next step before treating the current `contamination=0.001`/`0.005` selections as final —
see Open Questions.

## Limitations

- **Corridor-era pooled two-city envelope (retired 2026-10-12).** The measured models pooled
  both endpoint cities' raw readings into one corridor frame. Per-city models replace that
  design, so the measured rates above do not transfer to them, and the per-city false-positive/
  recall tradeoff has not been measured. The live `check()` call site selects a city's model via
  `AnomalyDetector.for_city`, not via a field in `raw_data`.
- **No time-of-day feature.** `raw_data` carries no timestamp at the `check()` call site, so the
  fitted model cannot condition on hour-of-day or season the way the forecasting model's
  `hour_sin`/`hour_cos` features do — a reading that would be implausible at 2am but normal at
  2pm is judged by the same envelope either way.
- **Fixed holdout fraction and contamination grid, neither swept against behavior.** The 0.25
  holdout fraction and the five-point `(0.001, 0.005, 0.01, 0.02, 0.05)` contamination grid are
  values chosen for this measurement, not tuned or swept against how sensitive the resulting
  false-positive/recall tradeoff is to either choice.
- **Injection methodology, rate and margins are this phase's own choices, not externally
  sourced.** The 2% injection rate, the fixed out-of-range margins (30 m/s / 35 °C / 600 W/m²
  beyond each G3 bound), and the 0.97/0.03 quantile choice for the "clear cold night"
  `in_range_implausible` triple are this phase's own judgment calls (RESEARCH.md Assumption A3),
  not values drawn from an external anomaly taxonomy or a labeled real-world dataset — no such
  dataset exists for this problem (see Measurement method).
- **The persisted artifact is a full-frame refit, not byte-identical to the measured model.** The
  numbers in Measured results come from an estimator fitted on the 13,140-row **fit slice only**
  and scored against the 4,380-row holdout it never saw. The artifact actually persisted to
  `data/models/anomaly_{city}.joblib` is refit on the **full assembled frame** (fit + holdout
  combined, 17,520 rows), per the Plan 02-02 decision that the shipped model should use every
  real row available rather than withholding 25% of it in production. This means the shipped
  artifact's exact decision boundary is not byte-identical to the one that produced the reported
  rates, though it is the same estimator type and configuration.
- **The kernel candidate's training-row cap applies only during the bake-off sweep.** The
  `OneClassSVM` measurements above were fitted on at most 5,000 chronologically-earliest fit rows
  (`config.ANOMALY_ML_SVM_MAX_TRAIN_ROWS`) during the sweep — `OneClassSVM`'s training cost grows
  superlinearly in sample count, and an uncapped multi-year hourly fit across 15 sweep points
  would have been prohibitively slow. The final persisted winner is refit on the full,
  **uncapped** assembled frame (see previous bullet), so the winning artifact's fit used more
  rows than the measurement that selected it — the cap's effect on `OneClassSVM`'s comparability
  against the other two (uncapped) candidates during the sweep is a real caveat on the bake-off
  itself, even though it did not block a full-data final refit.
- **Model artifacts are git-ignored generated data.** `data/models/` is not committed. A clean
  checkout has no trained model until `.venv/bin/python3 backend/anomaly_training.py --bakeoff`
  (or `--city <name>`) <!-- VERIFY: CLI flag name after the per-city migration; the corridor-era flag was `--corridor` --> is run; until then, the model branch is simply **absent** (one logged
  `logger.warning`, `model=None`) rather than raising — `AnomalyDetector.check` continues to
  function on its two pre-existing heuristic branches alone, exactly as it did before Phase 2.
- **ERCOT weather zones are a regional proxy**, not a city-local load figure — see Load
  characterization above.

## Open Questions

- Per-city refit and re-measurement: the per-city models (replacing the corridor-era pooled
  two-city envelope) have not been fitted, so the false-positive/recall tradeoff per city is
  unmeasured.
- Whether a richer, more varied synthetic-injection taxonomy (beyond the two categories measured
  here) would change the measured recall picture — particularly whether a wider range of
  "plausible-but-wrong" in-range combinations, not just the single "clear cold night" triple,
  would surface a different recall figure.
- Whether the selected contamination (corridor-era: `0.001` for `AUSTIN_CORPUS_CHRISTI`, `0.005` for
  `MIDLAND_EL_PASO`) should be re-swept per city once Track 1's live pipeline archive accrues real,
  multi-year historical data, rather than continuing to rely on this one-calendar-year
  Open-Meteo-backfill measurement.

## References

- `backend/anomaly_detector.py` — `AnomalyDetector.check`, `_check_against_model`,
  `_check_against_forecast`, `_check_against_rolling_baseline`, `for_city`,
  `_load_city_model_or_none`, `_model_path_for`.
- `backend/anomaly_training.py` — `corridor_observation_frame`, `chronological_split`,
  `inject_anomalies`, `_out_of_range_value`, `_implausible_combination`, `score_model`,
  `score_rolling_baseline`, `validate_candidate`, `CANDIDATE_ESTIMATORS`, `corridor_report`,
  `select_winner`, `characterize_load`; <!-- VERIFY: corridor-era function names; the per-city migration of this module was in progress when this note was written --> `--bakeoff`, `--validate`, `--characterize-load` CLI
  entry points.
- `backend/ercot_data_retriever.py` — `pull_ercot_data`, the zone-aware ERCOT load
  retriever used by `characterize_load`.
- `backend/config.py` — every `ANOMALY_ML_*` tunable named in Configuration measured above.
- `backend/DLRSafetyMonitor.py` — `WIND_BOUNDS`/`TEMP_BOUNDS`/`SOLAR_BOUNDS` (the G3 bounds the
  `out_of_range` injection category is pushed past), `run_check`'s G6 call site and its
  `except Exception -> _fallback` fail-safe wiring (unchanged by this phase).
- `data/models/anomaly_validation_report.json` — the machine-readable bake-off report this
  document transcribes (git-ignored; reproduce via
  `.venv/bin/python3 backend/anomaly_training.py --bakeoff --years 1`).
- `data/models/anomaly_load_characterization.json` — the machine-readable load characterization
  report this document transcribes (git-ignored; reproduce via
  `.venv/bin/python3 backend/anomaly_training.py --characterize-load`).
- `docs/data-science/specs/C10-anomaly-detection.md` — the corrected spec this record backs.
- `docs/data-science/decisions/forecasting_model.md` — Phase 1's precedent for this record's
  shape and D-07's honesty standard.
- `.planning/workstreams/ml-modeling/ROADMAP.md` — Phase 2 Success Criteria 1–5.
- `.planning/workstreams/ml-modeling/REQUIREMENTS.md` — ANOM-01, ANOM-02 full text.
- `.planning/workstreams/ml-modeling/phases/02-anomaly-detection-model/02-01-SUMMARY.md`,
  `02-02-SUMMARY.md`, `02-03-SUMMARY.md` — the plans that built, measured, and characterized this
  phase's model.
- Open-Meteo Archive API (`https://archive-api.open-meteo.com`) — the historical weather source.
- ERCOT historical load archive, via the `gridstatus` client (`backend/ercot_data_retriever.py`).
