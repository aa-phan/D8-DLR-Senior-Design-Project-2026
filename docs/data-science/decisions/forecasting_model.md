# Forecasting Model Validation Record

**Status:** Ratified as a record of measured fact — the numbers below are settled (they are a
direct transcription of a completed, reproducible run). The *recommendation* implied by those
numbers (whether `method="ml"` should be the production-preferred method) is explicitly **open**,
per this document's own Verdict and Open Questions sections below — the team should read the
Verdict before treating `"ml"` as a strict improvement over the existing Tier-1 methods.

**Purpose:** This document discharges **FCST-02** (the forecasting model's accuracy and
calibration must be validated against real historical data, not synthetic fixtures, and the
result documented) and **D-06** (FCST-02's written validation record lives here, as a new
ADR-style file under `docs/data-science/decisions/`, not only in a plan `SUMMARY.md`). It follows
the same working-log shape as `data_provider.md` and `geographic_scope.md` in this directory.

## What was built

`backend/ampacity_forecast.py::FORECAST_METHODS` was extended additively from `("naive", "ewm")`
to `("naive", "ewm", "ml")`. The new `"ml"` value is a Tier-2, fitted-model method: for each of
the two corridors in `config.CORRIDOR_ENDPOINTS`, a `scikit-learn` estimator is trained offline
(`backend/forecast_training.py`) on a real, per-corridor historical series and persisted to disk
(`config.FORECAST_ML_MODEL_DIR`). At call time, `forecast_ampacity(history, method="ml")` selects
the correct corridor's persisted artifact purely from `history["corridor"]` (`_corridor_of`,
`_load_corridor_model`) — no new parameter was added to the locked public signature. The point
forecast comes from that model's `.predict()` call on a lagged-`dlr_amps` + weather feature row
(`ML_FEATURE_COLUMNS`, built by `build_ml_features`); the confidence band, exactly as for
`"naive"`/`"ewm"`, comes from the existing `backtest_residuals` expanding-window walk-forward
machinery — `"ml"` does not introduce a second, parallel band implementation.

The estimator persisted per corridor is `MLPRegressor` (wrapped in
`make_pipeline(StandardScaler(), MLPRegressor(...))`), chosen over the alternative
`HistGradientBoostingRegressor` candidate by comparing measured out-of-sample MAE between the two
— see Verdict below for the full reasoning, including that this choice is a comparison between
the two ML candidates only, not evidence that either beats the existing baselines.

## Data provenance

The training and validation series is **not** the live `historical_archive.py` CSV
(`config.HISTORICAL_ARCHIVE_PATH`) — that file has zero rows today because Track 1 (Pipeline
Integration) has not executed yet (confirmed: `data/historical/ampacity_history.csv` does not
exist in this checkout). Per the ROADMAP Overview's explicit sourcing decision, this phase
assembles its own real (non-synthetic) series instead, using data that already exists
independently of Track 1's live accrual:

1. **Weather.** Hourly historical weather is pulled from the **Open-Meteo Archive API**
   (`open_meteo_provider.fetch_open_meteo`) for each corridor's two endpoint cities
   (`config.CITY_COORDINATES`), one HTTP request per complete calendar year per city
   (`forecast_training.fetch_city_weather`).
2. **Physics.** Each endpoint city's weather is run through
   `thermal_model.perpendicular_wind` (projected onto the corridor's own bearing) and then
   `thermal_model.ieee738_ampacity`, using that corridor's `ConductorConfig`
   (`corridor_discretization.corridor_geometry`) — the same IEEE 738 physics core every other
   DLR component calls, not a separate or approximated formula.
3. **Spatial reduction.** The corridor-level target at each timestamp is the elementwise `min()`
   of the two endpoint cities' computed ampacities — the codebase's established **weakest-link**
   convention, mirroring `corridor_discretization.rate_corridor`'s own bottleneck-point logic.
   The row's recorded weather is always the *winning* (lower-ampacity, bottleneck) city's own
   observation, never an average of the two and never the other city's reading.
4. **Validation.** Every assembled row is checked through
   `units_def.validate_pipeline_row(..., strict=False)` before it reaches the estimator; rows
   that fail (out-of-range values) are dropped, with the drop count and first offending message
   logged.

This is explicitly a **two-endpoint-city proxy** for the bottleneck the pipeline will eventually
measure at more points once Track 1's corridor discretization accrues real per-point history —
see Limitations below.

**Actual assembled window (both corridors, from the fresh run behind this document — see
Configuration measured for the exact command):** 26,304 rows assembled per corridor, spanning
**2023-01-01T00:00:00+00:00 through 2025-12-31T23:00:00+00:00** (the full configured 3-year
backfill depth, not shortened or subsampled). After feature engineering (lag/rolling-window
construction consumes leading rows) and the fold-holdout split, 21,910 rows were scored per ML
candidate and 26,292 rows were scored per baseline candidate, per corridor (see Measured results).

## Configuration measured

A reader should be able to reproduce this run from the values below alone. All are the actual
landed `backend/config.py` constants at the time of this run, and the reproduction command is:

```
.venv/bin/python3 backend/forecast_training.py --bakeoff
```

| Parameter | Value | Source |
|---|---|---|
| Forecast horizon | 60.0 minutes | `config.FORECAST_HORIZON_MINUTES` |
| Cold-start floor (min history rows) | 12 | `config.FORECAST_MIN_HISTORY_ROWS` |
| Backtest confidence quantiles | (0.05, 0.95) | `config.FORECAST_BACKTEST_QUANTILES` |
| EWM half-life (baseline comparison) | 180.0 minutes | `config.FORECAST_EWM_HALFLIFE_MIN` |
| Lag offsets (hours) | (1, 2, 3, 6) | `config.FORECAST_ML_LAG_HOURS` |
| Rolling-mean window | 6 hours | `config.FORECAST_ML_ROLLING_WINDOW_HOURS` |
| Backfill depth | 3 complete calendar years per city | `config.FORECAST_ML_TRAINING_YEARS` |
| Bake-off fold count | 5 (`TimeSeriesSplit(n_splits=5)`) | `config.FORECAST_ML_BAKEOFF_SPLITS` |
| Full ordered feature list | `dlr_amps_lag_1h`, `dlr_amps_lag_2h`, `dlr_amps_lag_3h`, `dlr_amps_lag_6h`, `dlr_amps_roll_mean_6h`, `air_temp`, `wind_speed`, `solar_radiation`, `hour_sin`, `hour_cos` | `ampacity_forecast.ML_FEATURE_COLUMNS` |
| Regression candidate | `HistGradientBoostingRegressor(random_state=20260924)` | `forecast_training._make_regression_candidate` |
| Neural-network candidate | `make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(32,16), max_iter=2000, random_state=20260924, early_stopping=False))` | `forecast_training._make_neural_network_candidate` |
| Assembled rows per corridor | 26,304 | `bakeoff_report.json` (this run) |
| Window (both corridors) | 2023-01-01T00:00:00+00:00 → 2025-12-31T23:00:00+00:00 | `bakeoff_report.json` (this run) |

## Expectation

The bar this model is judged against, **stated here before any verdict below**: the chosen ML
candidate's held-out MAE must be **lower than BOTH `naive`'s and `ewm`'s** on the identical
series for that corridor. Beating only one of the two baselines does not count as meeting the
bar — the model has to actually outperform the statistical methods it was built to replace, not
just one of them.

This bar was chosen, rather than a specific amperage error threshold, because no project document
(PRD, ROADMAP, `Project Definition.md`) contains an independently sourced accuracy target for
ampacity forecasting. Inventing a specific amp threshold with no citation behind it would be a
fabricated baseline. Beating the two statistical methods this model is meant to replace is the
most defensible, non-fabricated bar available from what actually exists in this project.

## Measured results

Every figure below is transcribed directly from `data/models/bakeoff_report.json`, produced by
the reproduction command above. Both ML candidates are shown regardless of which one lost, per
D-01's no-default-lean mandate — a reader can see both arms' numbers, not just the winner's.

### AUSTIN_CORPUS_CHRISTI (26,304 assembled rows; window 2023-01-01 → 2025-12-31)

| Candidate | Held-out MAE (A) | Held-out RMSE (A) | Rows scored |
|---|---|---|---|
| HistGradientBoostingRegressor | 79.09 | 105.14 | 21,910 |
| MLPRegressor (persisted winner among ML arms) | **77.70** | 103.79 | 21,910 |
| naive | **67.17** | 97.95 | 26,292 |
| ewm | 88.32 | 116.25 | 26,292 |

### MIDLAND_EL_PASO (26,304 assembled rows; window 2023-01-01 → 2025-12-31)

| Candidate | Held-out MAE (A) | Held-out RMSE (A) | Rows scored |
|---|---|---|---|
| HistGradientBoostingRegressor | 90.13 | 117.09 | 21,910 |
| MLPRegressor (persisted winner among ML arms) | **89.59** | 116.85 | 21,910 |
| naive | **79.76** | 113.51 | 26,292 |
| ewm | 99.65 | 129.87 | 26,292 |

## Verdict

**AUSTIN_CORPUS_CHRISTI: NOT MET.** MLPRegressor (MAE 77.70) is lower than
HistGradientBoostingRegressor (MAE 79.09) and lower than ewm (MAE 88.32), but it is **not** lower
than naive (MAE 67.17) — 77.70 > 67.17. The expectation required beating BOTH baselines; naive
was not beaten. The record states this plainly rather than reframing MLPRegressor's win over the
other ML candidate as an overall pass.

**MIDLAND_EL_PASO: NOT MET.** MLPRegressor (MAE 89.59) is lower than
HistGradientBoostingRegressor (MAE 90.13) and lower than ewm (MAE 99.65), but it is **not** lower
than naive (MAE 79.76) — 89.59 > 79.76. Same shortfall pattern as the other corridor.

**Estimator selection (the part of the question that WAS resolved on evidence):** for both
corridors, `MLPRegressor` was chosen over `HistGradientBoostingRegressor` by comparing measured
MAE between the two ML candidates only — 77.70 vs. 79.09 for AUSTIN_CORPUS_CHRISTI, and 89.59 vs.
90.13 for MIDLAND_EL_PASO. This choice was made on evidence, not a default lean toward either
architecture (D-01), and the losing arm's score is recorded here rather than only the winner's.
That selection is a real, evidence-based answer to "regression vs. neural network" — it is a
narrower question than "does the ML method as a whole outperform naive/ewm," which is the
question the Expectation section above actually judges, and on which both corridors read
**not met**.

**What this means and what the next step would be:** at the currently configured 60-minute
horizon, with the currently configured lag/rolling-window feature set, the persisted `"ml"`
method does not currently outperform the naive last-value method it was built to replace, on
either corridor, on this real 3-year window. This is not a leakage signature (see Limitations —
no candidate's error is anomalously small; naive's own strength here is a documented property of
short-horizon, slowly-varying physical series) and it is not a defect in the training or
evaluation pipeline — the no-future-leakage invariants from Plan 01-01 and the
`TimeSeriesSplit`/`backtest_residuals` fold-isolation guarantees from Plan 01-02 both hold. It is
a substantive negative result: a longer forecast horizon (where the last observed value is a
weaker predictor), a richer feature set, or a different lag structure would be the natural next
steps to investigate before recommending `"ml"` as the production-preferred method over `"naive"`
at this specific horizon.

## Limitations

- **Two-endpoint-city bottleneck proxy.** The corridor-level target is a `min()` reduction over
  exactly two endpoint cities' computed ampacity, standing in for the true multi-point bottleneck
  the pipeline's corridor-discretization (C8) will eventually measure once Track 1 accrues real
  per-point history. The model's feature distribution may not exactly match live bottleneck-point
  weather statistics once that richer data exists (RESEARCH.md Assumption A1).
- **Fixed backfill depth.** Three years of Open-Meteo history per city was a fixed choice inside
  a proposed 2–5 year band (RESEARCH.md Assumption A3), not a value tuned or swept against
  accuracy — a different depth was not evaluated in this run.
- **`MLPRegressor` stands in for "neural network."** The neural-network arm of this bake-off is
  `scikit-learn`'s `MLPRegressor`, a shallow multi-layer perceptron, not a deeper or
  purpose-built time-series architecture. This candidate's loss here is evidence about this
  specific estimator, not a general claim about neural networks for this problem
  (RESEARCH.md Assumption A4).
- **The training job is not resumable.** An interrupted training run for a corridor refetches
  and refits that corridor from scratch on the next invocation; what is guaranteed is atomic
  artifact replacement (`forecast_training.persist_corridor_model`'s temp-file-then-`os.replace`
  pattern), so a partially-written model artifact can never be loaded.
- **Model artifacts are git-ignored generated data.** `data/models/` is not committed. A clean
  checkout has no trained model until `.venv/bin/python3 backend/forecast_training.py --bakeoff`
  (or `--corridor <name>`) is run; until then, `forecast_ampacity(history, method="ml")` raises a
  `FileNotFoundError` naming the exact training command to run — it does not silently fall back
  to `"naive"` or `"ewm"`.

## Open Questions

- Whether `"ml"` should be retrained (or reconfigured — different horizon, lag structure, or
  feature set) once Track 1's live archive accrues real multi-point bottleneck history, rather
  than continuing to train against the two-endpoint-city proxy.
- Whether a deeper or purpose-built time-series architecture (beyond `MLPRegressor`) is worth a
  second ML dependency, given that the current neural-network arm did not close the gap to
  naive at this horizon.
- Whether the fixed 3-year backfill depth should be tuned (swept against measured accuracy)
  rather than left at its current default.
- Whether `"ml"` should be recommended as the production-preferred method at all at the current
  60-minute horizon, given that the measured evidence in this document does not currently support
  that recommendation — this document intentionally does not resolve that recommendation; it
  records the evidence a future decision would need.

## References

- `backend/ampacity_forecast.py` — the runtime `"ml"` method, `ML_FEATURE_COLUMNS`,
  `build_ml_features`, `backtest_residuals`, `forecast_columns`.
- `backend/forecast_training.py` — offline assembly (`corridor_training_frame`,
  `build_training_matrix`), the bake-off (`CANDIDATE_ESTIMATORS`, `bakeoff_corridor`,
  `baseline_scores`, `corridor_report`, `select_winner`), and persistence
  (`fit_corridor_model`, `persist_corridor_model`).
- `backend/config.py` — every tunable named in Configuration measured above.
- `backend/thermal_model.py` — `perpendicular_wind`, `ieee738_ampacity`, the physics behind
  every `dlr_amps` figure in this record.
- `backend/open_meteo_provider.py` — the Open-Meteo Archive API client used for backfill.
- `data/models/bakeoff_report.json` — the machine-readable report this document transcribes
  (git-ignored; reproduce via `.venv/bin/python3 backend/forecast_training.py --bakeoff`).
- `.planning/workstreams/ml-modeling/ROADMAP.md` — Phase 1 Success Criteria 3 and 4, and the
  Overview paragraph defining "real historical data" for this workstream.
- `.planning/workstreams/ml-modeling/REQUIREMENTS.md` — FCST-01, FCST-02 full text.
- `.planning/workstreams/ml-modeling/phases/01-forecasting-model/01-01-SUMMARY.md` and
  `01-02-SUMMARY.md` — the plans that built and bake-off-tested this method, including the
  first documentation of the naive-wins finding this record ratifies.
- Open-Meteo Archive API (`https://archive-api.open-meteo.com`) — the historical weather source.
