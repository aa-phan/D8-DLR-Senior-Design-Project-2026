# Anomaly Detection Model Validation Record

> **Scope change 2026-10-12.** The project no longer rates corridors; each of the four cities
> (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`, i.e. `config.LOCATIONS`) is an independent
> rating point (see `point_scope.md`). The anomaly model is now **per city**: one artifact
> `anomaly_{city}.joblib` per city, fitted on that city's own rows only, with no two-city
> pooling. **The per-city models were fitted and measured on 2026-10-13** with
> `--validate --years 1`, then `--bakeoff --years 1`, then `--characterize-load`, and the per-city
> results appear in the sections labeled **per-city refit (2026-10-13)**. **The corridor-era
> measurements further below (selected estimators and contaminations, rates, verdicts, load
> correlations) are labeled corridor-era (retired 2026-10-12)**: they were produced by pooled
> two-endpoint-city corridor models, remain as history, and do not describe the per-city models.

**Status:** Ratified as a record of measured fact — the numbers below are settled (a direct
transcription of a completed, reproducible run against real historical data). Both measured corridors' (corridor-era, retired 2026-10-12)
Verdicts read **MET** against both halves of the stated Expectation. That result is reported
plainly, per D-07, exactly as it came out — it is not a foregone conclusion just because it is a
pass: three of the five candidate/contamination combinations measured here (`EllipticEnvelope`,
and `IsolationForest` at low contamination) would have read NOT MET on the second half of the
bar had they been selected instead, and the model's false-positive rate, while under the ceiling,
is not zero the way the existing rolling baseline's structurally is. The 2026-10-13 per-city
refit also reads **MET** in all four cities (see Verdict), with the caveats recorded there. Whether the selected
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
city's (in the corridor-era run, each corridor's) evidence-selected winner. The per-city
selections (2026-10-13), persisted to `data/models/anomaly_{CITY}.joblib`:

| City | Selected estimator | Selected contamination | `ceiling_met` |
|---|---|---|---|
| `AUSTIN` | `OneClassSVM` | 0.01 | true |
| `CORPUS_CHRISTI` | `OneClassSVM` | 0.005 | true |
| `MIDLAND` | `OneClassSVM` | 0.001 | true |
| `EL_PASO` | `OneClassSVM` | 0.001 | true |

The **corridor-era (retired 2026-10-12)** result, kept as history:

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

**Per-city run (2026-10-13).** Each city's own Open-Meteo rows for one complete calendar year (`--years 1`,
2025), fitted and measured per city with no pooling: **8,760 hourly rows per city** (365 days x 24
hours, so the G3-bounds and finite-value filters dropped no row in any of `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`),
spanning **2025-01-01T00:00:00+00:00 through 2025-12-31T23:00:00+00:00**. After the chronological fit/holdout split: **6,570 fit rows**
and **2,190 holdout rows** per city, with **44 injected rows per category** (`round(2,190 * 0.02)`).
The corridor-era figures above (17,520 pooled rows, 13,140 fit, 4,380 holdout, 88 injected per
category) describe the retired pooled corridor frames and stay labeled as such.

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

**Actual assembled window (both corridor-era corridors, from the corridor-era run — see
Configuration measured for the exact command; the per-city counts are in the paragraph above):** 17,520 pooled hourly rows per corridor,
spanning **2025-01-01T00:00:00+00:00 through 2025-12-31T23:00:00+00:00**. After the chronological
fit/holdout split (never shuffled — the estimator is measured only against rows strictly later
than anything it was fitted on): **13,140 fit rows** and **4,380 holdout rows** per corridor.

## Configuration measured

A reader should be able to reproduce this run from the values below alone. All are the actual
landed `backend/config.py` constants at the time of this run. The corridor-era run used the last
two commands below. The per-city run (2026-10-13) used the full sequence, in this order — `--validate`
first and `--bakeoff` second, because both write the same report and the later writer replaces each
city's entry wholesale, so this order leaves the winner-bearing bake-off entries — with all
tunables unchanged, on scikit-learn 1.9.1:

```
.venv/bin/python3 backend/anomaly_training.py --validate --years 1
.venv/bin/python3 backend/anomaly_training.py --bakeoff --years 1
.venv/bin/python3 backend/anomaly_training.py --characterize-load
```

| Parameter | Value | Source |
|---|---|---|
| Backfill depth (this run) | 1 complete calendar year (2025) per city (per endpoint city in the corridor-era run) | CLI `--years 1`, overriding `config.ANOMALY_ML_TRAINING_YEARS` (3 years) for this measurement run |
| Holdout fraction | 0.25 | `config.ANOMALY_ML_VALIDATION_HOLDOUT_FRACTION` |
| Contamination grid | (0.001, 0.005, 0.01, 0.02, 0.05) | `config.ANOMALY_ML_CONTAMINATION_GRID` |
| Selected contamination (per-city, 2026-10-13, `AUSTIN`) | 0.01 | `data/models/anomaly_validation_report.json` |
| Selected contamination (per-city, 2026-10-13, `CORPUS_CHRISTI`) | 0.005 | `data/models/anomaly_validation_report.json` |
| Selected contamination (per-city, 2026-10-13, `MIDLAND`) | 0.001 | `data/models/anomaly_validation_report.json` |
| Selected contamination (per-city, 2026-10-13, `EL_PASO`) | 0.001 | `data/models/anomaly_validation_report.json` |
| Selected contamination (corridor-era, retired 2026-10-12, `AUSTIN_CORPUS_CHRISTI`) | 0.001 | `data/models/legacy_corridor_era/anomaly_validation_report.json` |
| Selected contamination (corridor-era, retired 2026-10-12, `MIDLAND_EL_PASO`) | 0.005 | `data/models/legacy_corridor_era/anomaly_validation_report.json` |
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

- **False-positive rate** is directly measurable on real, clean, held-out data: the chronological
  holdout slice (4,380 rows per corridor in the corridor-era run; 2,190 rows per city in the
  2026-10-13 per-city run), strictly later than every row the estimator fitted on.
- **False-negative rate (recall)** only exists against **deliberately injected synthetic
  corruption**, since no real labelled anomaly exists to measure recall against. Two categories
  were injected into the holdout slice, each at `config.ANOMALY_ML_INJECTION_RATE` (0.02) — 88
  rows per category per corridor in the corridor-era run (`round(4380 * 0.02)`) and 44 rows per
  category per city in the 2026-10-13 per-city run (`round(2190 * 0.02)`):
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

The per-city figures below are transcribed directly from `data/models/anomaly_validation_report.json`
(the 2026-10-13 run; every entry has `produced_by: bakeoff`), produced by the reproduction commands
above. All three D-03 candidates are shown at all five contamination grid points (15 rows per city)
— the losing candidates included, per D-03's no-default-lean discipline — not only the selected
winner's row. Baseline figures are identical across every row within a city (the baseline does not
depend on candidate/contamination) and are repeated per row for direct comparison. The earlier
`--validate` sweep of the same run (an `IsolationForest` sweep) reproduced the bake-off's
`IsolationForest` rows exactly in every city.

### AUSTIN — per-city refit (2026-10-13) (8,760 assembled rows; window 2025-01-01 → 2025-12-31; fit 6,570 rows, holdout 2,190 rows; 44 injected rows per category)

| Candidate | Contam. | FP rate | Baseline FP | Recall (out_of_range) | Baseline recall (o-o-r) | Recall (in_range_implausible) | Baseline recall (i-r-i) | Pooled recall | Baseline pooled recall |
|---|---|---|---|---|---|---|---|---|---|
| IsolationForest | 0.001 | 0.00% | 0.00% | 0.00% | 27.27% | 100.00% | 0.00% | 50.00% | 13.64% |
| IsolationForest | 0.005 | 0.00% | 0.00% | 6.82% | 27.27% | 100.00% | 0.00% | 53.41% | 13.64% |
| IsolationForest | 0.01 | 0.23% | 0.00% | 9.09% | 27.27% | 100.00% | 0.00% | 54.55% | 13.64% |
| IsolationForest | 0.02 | 0.55% | 0.00% | 22.73% | 27.27% | 100.00% | 0.00% | 61.36% | 13.64% |
| IsolationForest | 0.05 | 1.83% | 0.00% | 38.64% | 27.27% | 100.00% | 0.00% | 69.32% | 13.64% |
| EllipticEnvelope | 0.001 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.005 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.01 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.02 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.05 | 0.00% | 0.00% | 25.00% | 27.27% | 100.00% | 0.00% | 62.50% | 13.64% |
| OneClassSVM | 0.001 | 1.14% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| OneClassSVM | 0.005 | 1.05% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| **OneClassSVM (selected)** | **0.01** | **1.00%** | **0.00%** | **100.00%** | **27.27%** | **100.00%** | **0.00%** | **100.00%** | **13.64%** |
| OneClassSVM | 0.02 | 1.83% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| OneClassSVM | 0.05 | 4.52% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |

Winner selection: 15 of the 15 pairs have a false-positive rate at or below the 5.00% ceiling; the highest pooled recall among them is 100.00%, reached by 5 `OneClassSVM` contamination points (`contamination=0.001`, `contamination=0.005`, `contamination=0.01`, `contamination=0.02`, `contamination=0.05`); no other candidate exceeds 69.32% pooled recall. The tie was broken by the lowest false-positive rate, which is `contamination=0.01` (1.00%) — the selected pair. `ceiling_met: true` in the report (1.00% ≤ 5.00%).

### CORPUS_CHRISTI — per-city refit (2026-10-13) (8,760 assembled rows; window 2025-01-01 → 2025-12-31; fit 6,570 rows, holdout 2,190 rows; 44 injected rows per category)

| Candidate | Contam. | FP rate | Baseline FP | Recall (out_of_range) | Baseline recall (o-o-r) | Recall (in_range_implausible) | Baseline recall (i-r-i) | Pooled recall | Baseline pooled recall |
|---|---|---|---|---|---|---|---|---|---|
| IsolationForest | 0.001 | 0.00% | 0.00% | 0.00% | 27.27% | 100.00% | 0.00% | 50.00% | 13.64% |
| IsolationForest | 0.005 | 0.00% | 0.00% | 2.27% | 27.27% | 100.00% | 0.00% | 51.14% | 13.64% |
| IsolationForest | 0.01 | 0.09% | 0.00% | 4.55% | 27.27% | 100.00% | 0.00% | 52.27% | 13.64% |
| IsolationForest | 0.02 | 1.00% | 0.00% | 13.64% | 27.27% | 100.00% | 0.00% | 56.82% | 13.64% |
| IsolationForest | 0.05 | 3.29% | 0.00% | 31.82% | 27.27% | 100.00% | 0.00% | 65.91% | 13.64% |
| EllipticEnvelope | 0.001 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.005 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.01 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.02 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.05 | 0.00% | 0.00% | 25.00% | 27.27% | 100.00% | 0.00% | 62.50% | 13.64% |
| OneClassSVM | 0.001 | 0.32% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| **OneClassSVM (selected)** | **0.005** | **0.27%** | **0.00%** | **100.00%** | **27.27%** | **100.00%** | **0.00%** | **100.00%** | **13.64%** |
| OneClassSVM | 0.01 | 0.64% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| OneClassSVM | 0.02 | 1.46% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| OneClassSVM | 0.05 | 3.84% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |

Winner selection: 15 of the 15 pairs have a false-positive rate at or below the 5.00% ceiling; the highest pooled recall among them is 100.00%, reached by 5 `OneClassSVM` contamination points (`contamination=0.001`, `contamination=0.005`, `contamination=0.01`, `contamination=0.02`, `contamination=0.05`); no other candidate exceeds 65.91% pooled recall. The tie was broken by the lowest false-positive rate, which is `contamination=0.005` (0.27%) — the selected pair. `ceiling_met: true` in the report (0.27% ≤ 5.00%).

### MIDLAND — per-city refit (2026-10-13) (8,760 assembled rows; window 2025-01-01 → 2025-12-31; fit 6,570 rows, holdout 2,190 rows; 44 injected rows per category)

| Candidate | Contam. | FP rate | Baseline FP | Recall (out_of_range) | Baseline recall (o-o-r) | Recall (in_range_implausible) | Baseline recall (i-r-i) | Pooled recall | Baseline pooled recall |
|---|---|---|---|---|---|---|---|---|---|
| IsolationForest | 0.001 | 0.00% | 0.00% | 0.00% | 27.27% | 100.00% | 0.00% | 50.00% | 13.64% |
| IsolationForest | 0.005 | 0.00% | 0.00% | 15.91% | 27.27% | 100.00% | 0.00% | 57.95% | 13.64% |
| IsolationForest | 0.01 | 0.00% | 0.00% | 29.55% | 27.27% | 100.00% | 0.00% | 64.77% | 13.64% |
| IsolationForest | 0.02 | 0.00% | 0.00% | 34.09% | 27.27% | 100.00% | 0.00% | 67.05% | 13.64% |
| IsolationForest | 0.05 | 0.55% | 0.00% | 59.09% | 27.27% | 100.00% | 0.00% | 79.55% | 13.64% |
| EllipticEnvelope | 0.001 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.005 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.01 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.02 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.05 | 0.00% | 0.00% | 25.00% | 27.27% | 100.00% | 0.00% | 62.50% | 13.64% |
| **OneClassSVM (selected)** | **0.001** | **0.00%** | **0.00%** | **100.00%** | **27.27%** | **100.00%** | **0.00%** | **100.00%** | **13.64%** |
| OneClassSVM | 0.005 | 0.23% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| OneClassSVM | 0.01 | 0.27% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| OneClassSVM | 0.02 | 0.37% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| OneClassSVM | 0.05 | 1.05% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |

Winner selection: 15 of the 15 pairs have a false-positive rate at or below the 5.00% ceiling; the highest pooled recall among them is 100.00%, reached by 5 `OneClassSVM` contamination points (`contamination=0.001`, `contamination=0.005`, `contamination=0.01`, `contamination=0.02`, `contamination=0.05`); no other candidate exceeds 79.55% pooled recall. The tie was broken by the lowest false-positive rate, which is `contamination=0.001` (0.00%) — the selected pair. `ceiling_met: true` in the report (0.00% ≤ 5.00%).

### EL_PASO — per-city refit (2026-10-13) (8,760 assembled rows; window 2025-01-01 → 2025-12-31; fit 6,570 rows, holdout 2,190 rows; 44 injected rows per category)

| Candidate | Contam. | FP rate | Baseline FP | Recall (out_of_range) | Baseline recall (o-o-r) | Recall (in_range_implausible) | Baseline recall (i-r-i) | Pooled recall | Baseline pooled recall |
|---|---|---|---|---|---|---|---|---|---|
| IsolationForest | 0.001 | 0.00% | 0.00% | 4.55% | 27.27% | 100.00% | 0.00% | 52.27% | 13.64% |
| IsolationForest | 0.005 | 0.00% | 0.00% | 13.64% | 27.27% | 100.00% | 0.00% | 56.82% | 13.64% |
| IsolationForest | 0.01 | 0.00% | 0.00% | 27.27% | 27.27% | 100.00% | 0.00% | 63.64% | 13.64% |
| IsolationForest | 0.02 | 0.00% | 0.00% | 31.82% | 27.27% | 100.00% | 0.00% | 65.91% | 13.64% |
| IsolationForest | 0.05 | 0.18% | 0.00% | 50.00% | 27.27% | 100.00% | 0.00% | 75.00% | 13.64% |
| EllipticEnvelope | 0.001 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.005 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.01 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.02 | 0.00% | 0.00% | 25.00% | 27.27% | 0.00% | 0.00% | 12.50% | 13.64% |
| EllipticEnvelope | 0.05 | 0.00% | 0.00% | 25.00% | 27.27% | 100.00% | 0.00% | 62.50% | 13.64% |
| **OneClassSVM (selected)** | **0.001** | **0.37%** | **0.00%** | **100.00%** | **27.27%** | **100.00%** | **0.00%** | **100.00%** | **13.64%** |
| OneClassSVM | 0.005 | 0.37% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| OneClassSVM | 0.01 | 0.59% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| OneClassSVM | 0.02 | 0.82% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |
| OneClassSVM | 0.05 | 1.51% | 0.00% | 100.00% | 27.27% | 100.00% | 0.00% | 100.00% | 13.64% |

Winner selection: 15 of the 15 pairs have a false-positive rate at or below the 5.00% ceiling; the highest pooled recall among them is 100.00%, reached by 5 `OneClassSVM` contamination points (`contamination=0.001`, `contamination=0.005`, `contamination=0.01`, `contamination=0.02`, `contamination=0.05`); no other candidate exceeds 75.00% pooled recall. The tie was broken by the lowest false-positive rate, which is `contamination=0.001` (0.37%), tied with `contamination=0.005` at the same rate, so `select_winner` resolved the remaining tie by candidate order, then lowest contamination — the selected pair. `ceiling_met: true` in the report (0.37% ≤ 5.00%).

The corridor-era subsections below are the history of the retired pooled corridor models. Their
source report is preserved at `data/models/legacy_corridor_era/anomaly_validation_report.json`
(backed up before the per-city run, because the per-city report merge drops non-city keys from
`data/models/anomaly_validation_report.json`).

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

### Per-city load characterization (2026-10-13)

Transcribed from `data/models/anomaly_load_characterization.json`, produced on 2026-10-13 by
`.venv/bin/python3 backend/anomaly_training.py --characterize-load` (run after the fits, best-effort,
per D-02). All four cities report `available: true`:

| City | Zone substrings | Matched ERCOT zone columns | Retrieved window | Load rows | Joined rows | Correlation: `air_temp` | Correlation: `wind_speed` | Correlation: `solar_radiation` |
|---|---|---|---|---|---|---|---|---|
| `AUSTIN` | `("SOUTH",)` | `South`, `South Central` | 2025-01-01T06:00:00+00:00 → 2025-12-31T00:00:00+00:00 | 8,731 | 8,731 | 0.54 | 0.03 | 0.47 |
| `CORPUS_CHRISTI` | `("SOUTH",)` | `South`, `South Central` | 2025-01-01T06:00:00+00:00 → 2025-12-31T00:00:00+00:00 | 8,731 | 8,731 | 0.42 | 0.20 | 0.46 |
| `MIDLAND` | `("WEST",)` | `Far West`, `West` | 2025-01-01T06:00:00+00:00 → 2025-12-31T00:00:00+00:00 | 8,731 | 8,731 | 0.48 | -0.09 | 0.48 |
| `EL_PASO` | `("WEST",)` | `Far West`, `West` | 2025-01-01T06:00:00+00:00 → 2025-12-31T00:00:00+00:00 | 8,731 | 8,731 | 0.51 | -0.10 | 0.47 |

- **Two load series, not four.** The zone group is `SOUTH` for `AUSTIN` and `CORPUS_CHRISTI` and
  `WEST` for `MIDLAND` and `EL_PASO`, so `AUSTIN` and `CORPUS_CHRISTI` were joined against one shared
  ERCOT load series (8,731 rows), and `MIDLAND` and `EL_PASO` against another (also 8,731 rows). The
  correlations differ per city only because each is computed against that city's own weather.
- **This run succeeded where the 2026-08-25 live pull did not.** That earlier pull failed
  deterministically with `Bad CRC-32` for `Native_Load_2026.xlsx` (recorded in
  `docs/data-science/specs/C6-grid-load-integration.md`). This run fetched calendar year 2025 only
  (`config.ANOMALY_ML_LOAD_YEARS`, 1 year); the 2026 archive file that failed was not requested, so
  this success does not show that the earlier failure is resolved.
- **Reproducibility caveat.** `gridstatus` 0.35.0 is installed in `.venv` but is **not listed in
  `requirements.txt`**, so a fresh environment built from `requirements.txt` alone would not run
  `--characterize-load` until `gridstatus` is installed. `requirements.txt` was deliberately not
  changed by this run.

### Corridor-era load characterization (retired 2026-10-12)

*Corridor-era (retired 2026-10-12) measurement; the zone-substring mapping is now per city (`AUSTIN`/`CORPUS_CHRISTI` use `SOUTH`, `MIDLAND`/`EL_PASO` use `WEST`).*

Transcribed from the corridor-era report, preserved at
`data/models/legacy_corridor_era/anomaly_load_characterization.json` (the per-city
`--characterize-load` run replaced `data/models/anomaly_load_characterization.json`), produced by
the same `--characterize-load` command:

| Corridor | Zone substrings | Matched ERCOT zone columns | Retrieved window | Load rows | Joined rows | Correlation: `air_temp` | Correlation: `wind_speed` | Correlation: `solar_radiation` |
|---|---|---|---|---|---|---|---|---|
| `AUSTIN_CORPUS_CHRISTI` | `("SOUTH",)` | `South`, `South Central` | 2025-01-01T06:00:00+00:00 → 2025-12-31T00:00:00+00:00 | 8,731 | 8,731 | 0.49 | 0.14 | 0.47 |
| `MIDLAND_EL_PASO` | `("WEST",)` | `Far West`, `West` | 2025-01-01T06:00:00+00:00 → 2025-12-31T00:00:00+00:00 | 8,731 | 8,731 | 0.51 | -0.11 | 0.48 |

### D-02 boundary and interpretation

Per **D-02**, ERCOT historical load is a **training-time-only signal**: `raw_data` does not carry
load at the live `check()` call site, and wiring it in would touch Track 1's pipeline-wiring
scope — explicitly out of bounds for this workstream (REQUIREMENTS.md Out of Scope table). A
named test (`test_load_is_training_time_only_and_never_reaches_check`, added in Plan 02-03)
asserts all four halves of this boundary together: no source-level import of
`ercot_data_retriever`/`gridstatus` in `anomaly_detector.py`; no "load" name in either feature
config tuple; a fresh import of `anomaly_detector` leaves `gridstatus` out of `sys.modules`; and
`check()` still succeeds on a `raw_data` carrying exactly `wind`/`temp`/`solar`.

A **Pearson correlation measures linear association only** — the moderate positive correlations
against `air_temp`/`solar_radiation` (corridor-era ~0.47–0.51; per-city 0.42–0.54 for `air_temp`
and 0.46–0.48 for `solar_radiation`; physically sensible: hotter/sunnier conditions drive
higher grid load) and the much weaker `wind_speed` correlations (corridor-era 0.14 and -0.11;
per-city -0.10 to 0.20) are evidence of a *weak linear* relationship for wind specifically, not
evidence that load is irrelevant to wind — a nonlinear relationship could exist that Pearson's
coefficient cannot see. ERCOT's weather zones (`South`/`South Central`, `Far West`/`West`) are also
a **regional proxy** far larger than any single city's service area: the zone-aware selection
(verified genuinely distinct per zone group, per Plan 02-03) is a sanity check against a plausible
regional demand pattern, not a claim that either zone's load figure represents a city's own local
demand precisely.

## Verdict

**Per-city verdicts (2026-10-13 refit)**, each against both halves of the unchanged Expectation above:

**AUSTIN: MET.** The selected `OneClassSVM` (`contamination=0.01`) measured a false-positive rate of **1.00%**, at or below the 5.00% ceiling — half 1 met. Its recall on the `in_range_implausible` category is **100.00%**, strictly higher than the baseline's **0.00%** on the identical rows — half 2 met. Both halves of the Expectation are met.

**CORPUS_CHRISTI: MET.** The selected `OneClassSVM` (`contamination=0.005`) measured a false-positive rate of **0.27%**, at or below the 5.00% ceiling — half 1 met. Its recall on the `in_range_implausible` category is **100.00%**, strictly higher than the baseline's **0.00%** on the identical rows — half 2 met. Both halves of the Expectation are met.

**MIDLAND: MET.** The selected `OneClassSVM` (`contamination=0.001`) measured a false-positive rate of **0.00%**, at or below the 5.00% ceiling — half 1 met. Its recall on the `in_range_implausible` category is **100.00%**, strictly higher than the baseline's **0.00%** on the identical rows — half 2 met. Both halves of the Expectation are met.

**EL_PASO: MET.** The selected `OneClassSVM` (`contamination=0.001`) measured a false-positive rate of **0.37%**, at or below the 5.00% ceiling — half 1 met. Its recall on the `in_range_implausible` category is **100.00%**, strictly higher than the baseline's **0.00%** on the identical rows — half 2 met. Both halves of the Expectation are met.

**What this means per city (2026-10-13), beyond the raw MET/NOT MET label:** all four per-city selections are `OneClassSVM`, and all four read MET. The mean-and-standard-deviation baseline caught **zero** `in_range_implausible` rows in every city (0.00% recall, the same structural blind spot recorded for the corridor-era models), while each selected model caught all 44 injected rows in that category. The selected models' false-positive rates on clean held-out rows are 1.00% (AUSTIN), 0.27% (CORPUS_CHRISTI), 0.00% (MIDLAND), 0.37% (EL_PASO), all under the 5.00% ceiling; every selection except the zero-false-positive `MIDLAND` one is nonzero, as in the corridor-era run, against a baseline that is structurally 0.00%. Two caveats belong next to the MET labels. First, the `in_range_implausible` half of the Expectation is not discriminating between candidates in this data: `IsolationForest` also reaches 100.00% recall on that category at every contamination in all four cities (with a false-positive rate of at most 3.29% across the whole contamination grid), so `OneClassSVM` was selected on pooled recall, which is driven by the `out_of_range` category (the selected models' recall on it is 100.00% in all four cities). Per the Measurement method section, `out_of_range` rows are already rejected by G3 upstream in the live pipeline, so that part of the margin is redundant with an existing gate rather than new protection. Second, the per-city measurements use a 2,190-row holdout and 44 injected rows per category, a smaller sample than the corridor-era 4,380 / 88, so a single injected row is worth 2.27 percentage points of category recall.

**Next step:** the per-city contaminations (AUSTIN 0.01, CORPUS_CHRISTI 0.005, MIDLAND 0.001, EL_PASO 0.001) were each selected against exactly one calendar year (2025) of that city's real weather and one fixed injection methodology, and the `OneClassSVM` points within a city differ by small false-positive margins. In EL_PASO the lowest false-positive rate was shared by more than one `OneClassSVM` contamination point, and the selection rule broke that tie by grid order rather than by evidence. Re-running this bake-off once more historical data accrues (or once Track 1's live pipeline history is available) would be the natural next step before treating the per-city selections as final; the corridor-era `0.001`/`0.005` selections do not carry over to them — see Open Questions.

*The corridor-era (retired 2026-10-12) verdicts below are kept as history; the per-city verdicts are above.*

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

**Corridor-era (retired 2026-10-12) reading, kept as history: what this meant, honestly, beyond the raw MET/NOT MET label:** the `in_range_implausible`
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

**Corridor-era next step:** given the winning candidate's `contamination` was selected against exactly one
calendar year of real weather and one fixed injection methodology, re-running this bake-off once
more historical data accrues (or once Track 1's live pipeline history is available) would be the
natural next step before treating the current `contamination=0.001`/`0.005` selections as final —
see Open Questions.

## Limitations

- **Corridor-era pooled two-city envelope (retired 2026-10-12).** The measured models pooled
  both endpoint cities' raw readings into one corridor frame. Per-city models replace that
  design, so the corridor-era rates do not transfer to them; the per-city false-positive/recall
  tradeoff is in the per-city refit (2026-10-13) sections above. The live `check()` call site selects a city's model via
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
  numbers in Measured results come from an estimator fitted on the **fit slice only** (13,140 rows
  per corridor in the corridor-era run; 6,570 rows per city in the per-city run) and scored against
  the holdout it never saw (4,380 rows per corridor; 2,190 rows per city). The artifact actually
  persisted to `data/models/anomaly_{city}.joblib` is refit on the **full assembled frame** (fit +
  holdout combined: 17,520 rows per corridor in the corridor-era run; 8,760 rows per city in the
  per-city run), per the Plan 02-02 decision that the shipped model should use every
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
  itself, even though it did not block a full-data final refit. In the per-city run the cap still
  binds: `OneClassSVM` was fitted on 5,000 of each city's 6,570 fit rows during the sweep
  (`train_rows_used: 5000` in every `OneClassSVM` measurement), while the other two candidates used
  all 6,570.
- **Model artifacts are git-ignored generated data.** `data/models/` is not committed. A clean
  checkout has no trained model until `.venv/bin/python3 backend/anomaly_training.py --bakeoff`
  (or `--city <CITY>`; the corridor-era flag was `--corridor`) is run; until then, the model branch is simply **absent** (one logged
  `logger.warning`, `model=None`) rather than raising — `AnomalyDetector.check` continues to
  function on its two pre-existing heuristic branches alone, exactly as it did before Phase 2.
- **ERCOT weather zones are a regional proxy**, not a city-local load figure — see Load
  characterization above.

## Open Questions

- ~~Per-city refit and re-measurement of the per-city models (replacing the corridor-era pooled
  two-city envelope)~~ — **answered, 2026-10-13.** All four cities were fitted and measured on 2026-10-13; see the per-city refit (2026-10-13) sections under Measured results. Selected: `AUSTIN` `OneClassSVM` at 0.01, `CORPUS_CHRISTI` `OneClassSVM` at 0.005, `MIDLAND` `OneClassSVM` at 0.001, `EL_PASO` `OneClassSVM` at 0.001; all four read MET.
- Whether a richer, more varied synthetic-injection taxonomy (beyond the two categories measured
  here) would change the measured recall picture — particularly whether a wider range of
  "plausible-but-wrong" in-range combinations, not just the single "clear cold night" triple,
  would surface a different recall figure.
- Whether the selected contamination (corridor-era: `0.001` for `AUSTIN_CORPUS_CHRISTI`, `0.005` for
  `MIDLAND_EL_PASO`; per city (2026-10-13): AUSTIN 0.01, CORPUS_CHRISTI 0.005, MIDLAND 0.001, EL_PASO 0.001) should be re-swept per city once Track 1's live pipeline archive accrues real,
  multi-year historical data, rather than continuing to rely on this one-calendar-year
  Open-Meteo-backfill measurement.

## References

- `backend/anomaly_detector.py` — `AnomalyDetector.check`, `_check_against_model`,
  `_check_against_forecast`, `_check_against_rolling_baseline`, `for_city`,
  `_load_city_model_or_none`, `_model_path_for`.
- `backend/anomaly_training.py` — `city_observation_frame`, `fit_city_model`,
  `persist_city_model`, `chronological_split`, `inject_anomalies`, `_out_of_range_value`,
  `_implausible_combination`, `score_model`, `score_rolling_baseline`, `validate_candidate`,
  `CANDIDATE_ESTIMATORS`, `city_report`, `merge_city_report`, `select_winner`,
  `characterize_load`; `--bakeoff`, `--validate`, `--characterize-load` CLI entry points (and
  `--city` to scope a run to one city).
- `backend/ercot_data_retriever.py` — `pull_ercot_data`, the zone-aware ERCOT load
  retriever used by `characterize_load`.
- `backend/config.py` — every `ANOMALY_ML_*` tunable named in Configuration measured above.
- `backend/DLRSafetyMonitor.py` — `WIND_BOUNDS`/`TEMP_BOUNDS`/`SOLAR_BOUNDS` (the G3 bounds the
  `out_of_range` injection category is pushed past), `run_check`'s G6 call site and its
  `except Exception -> _fallback` fail-safe wiring (unchanged by this phase).
- `data/models/anomaly_validation_report.json` — the machine-readable bake-off report this
  document transcribes for the per-city run (git-ignored; reproduce via
  `.venv/bin/python3 backend/anomaly_training.py --validate --years 1` then `--bakeoff --years 1`).
- `data/models/anomaly_load_characterization.json` — the machine-readable load characterization
  report this document transcribes for the per-city run (git-ignored; reproduce via
  `.venv/bin/python3 backend/anomaly_training.py --characterize-load`).
- `data/models/legacy_corridor_era/anomaly_validation_report.json` and
  `data/models/legacy_corridor_era/anomaly_load_characterization.json` — backups of the
  corridor-era reports, taken before the per-city run (git-ignored); the source of the corridor-era
  numbers kept as history above.
- `data/models/retrain_logs/` — console logs of the 2026-10-13 per-city run (git-ignored).
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
