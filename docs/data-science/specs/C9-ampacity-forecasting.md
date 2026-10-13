# C9 — Ampacity Forecasting

**Phase:** 4 (Predictive) · **Effort:** L · **Status:** Shipped in two stages. Two Tier-1
statistical methods (`"naive"`, `"ewm"`) shipped in **v1.0 Phase 4**; a Tier-2 fitted-model
method (`"ml"`) shipped in **v1.3 Phase 1** of the independent `ml-modeling` workstream. Both
are referenced by `System Design Report.md` §3.1 ("thermal limit forecasting via regression or
neural network models") and by the Prior Art Report (IEEE Trans. Smart Grid MILP planning work)
— those two documents are the origin of the "regression or neural network" framing that shaped
`"ml"`'s design, and the regression-vs-neural-network question they leave open is now answered
on measured evidence (see Open Questions below and
`docs/data-science/decisions/forecasting_model.md`).

**Responsibility:** Forecast ampacity ahead of real time (rather than only reporting the current
instantaneous rating), so the UI dashboard's "trusted duration" concept (per
`Project Definition.md`'s I/O spec) has a forward-looking basis instead of just an assumed
static window.

## Current Implementation

`backend/ampacity_forecast.py::FORECAST_METHODS` provides three methods behind one
`forecast_ampacity` signature:

- **`method="naive"`** — the last observed `dlr_amps` value, projected forward unchanged.
- **`method="ewm"`** — a time-aware exponentially-weighted moving average
  (`config.FORECAST_EWM_HALFLIFE_MIN` half-life), using `series.ewm(times=...)` when a real
  `datetime_utc` index is available.
- **`method="ml"`** (v1.3 Phase 1, `ml-modeling` workstream) — a per-city fitted
  `scikit-learn` estimator over lagged `dlr_amps` plus multivariate weather features
  (`ampacity_forecast.ML_FEATURE_COLUMNS`, built by `build_ml_features`), loaded from a
  persisted artifact keyed purely off `history["city"]` — no new parameter was added to the
  function signature to support this. The city must be a key of `config.LOCATIONS`; it is
  validated against that closed set before any artifact path is built. (Until 2026-10-12 this
  was a per-corridor model keyed off `history["corridor"]`; see `decisions/point_scope.md`.)

All three share the same downstream machinery: `backtest_residuals`'s expanding-window
walk-forward backtest is the **single source** of the confidence band's width for every method —
there is no separate band implementation for `"ml"`. `forecast_columns()` is the **only** path
from a `ForecastResult` to pipeline output, mapping onto the four `PIPELINE_SCHEMA` forecast
columns.

`backend/forecast_training.py` is the offline training/bake-off entry point for the `"ml"`
method: it assembles a real, Open-Meteo-backfill-derived per-city training series (one city's own
rows and that city's own ampacity as the target — not a minimum across cities), fits and persists
a per-city model `forecast_{city}.joblib`, and (via `--bakeoff`) runs the two-candidate comparison
documented in `docs/data-science/decisions/forecasting_model.md`. `--city <CITY>` selects one city
(default: every city in `config.LOCATIONS`). Model artifacts are git-ignored generated data
(`config.FORECAST_ML_MODEL_DIR`, `/data/models/`) — a clean checkout has no trained model until
this script is run. **The per-city refit has not been run yet**; no corridor-named `forecast_*.joblib` artifact is
present in this checkout, and any such file would be legacy and is not loaded.

## Interface & Data Contract

The shipped contract, read off `backend/ampacity_forecast.py`:

- **Function:** `forecast_ampacity(history: pd.DataFrame, horizon_min=None, method="naive", quantiles=None, min_rows=None) -> ForecastResult | None`.
  - `history` — an archive-shaped frame (`historical_archive.read_history`'s output shape for
    `"naive"`/`"ewm"`; additionally requires `city` and the weather columns in
    `config.FORECAST_ML_FEATURE_WEATHER_COLUMNS` for `"ml"`).
  - `method` — one of `FORECAST_METHODS` (`"naive"`, `"ewm"`, `"ml"`); raises `ValueError` naming
    the tuple for anything else, checked before any history is read.
  - Returns `None` — an explicit, documented cold start — when fewer than `min_rows`
    (defaults to `config.FORECAST_MIN_HISTORY_ROWS`) non-null `dlr_amps` observations are
    available, rather than a confidently wrong band on a handful of rows.
- **`ForecastResult`** attributes (each `float`/`int`/`str`-wrapped at assignment):
  `horizon_min`, `amps`, `ci_lower_amps`, `ci_upper_amps`, `n_observations`, `method`,
  `n_residuals`.
- **Output:** `forecast_columns(result)` maps a `ForecastResult` onto exactly the four
  `PIPELINE_SCHEMA` v2 forecast columns — `forecast_horizon_min`, `forecast_amps`,
  `forecast_ci_lower_amps`, `forecast_ci_upper_amps` — returning `{}` for a `None` result (a
  cold-start run emits no forecast columns at all, never nulls or zeros that could be mistaken
  for a real forecast).
- **Features (`"ml"` only):** the ordered `ML_FEATURE_COLUMNS` tuple — four lagged-`dlr_amps`
  offsets, a shifted rolling mean, the multivariate weather columns
  (`config.FORECAST_ML_FEATURE_WEATHER_COLUMNS`), and a cyclical hour-of-day encoding.
- **Target:** `dlr_amps` shifted forward by `config.FORECAST_HORIZON_MINUTES` worth of rows
  (offline, `forecast_training.build_training_matrix`); at inference, the point forecast is the
  fitted model's `.predict()` call on the current feature row.
- **Failure mode:** `method="ml"` **raises** `FileNotFoundError` (naming the city, the
  expected artifact path, and the exact training command to run) when no trained artifact
  exists for the requested city — it never silently degrades to `"naive"` or `"ewm"`.

## Blocked by

**C4** (weather features) and **C5** (ampacity as both a feature and the training target) — both
long since shipped and unchanged as this component's dependencies.

The **accumulated historical data volume** blocker this section originally anticipated (per the
original `ROADMAP.md` Finding 5, a lead-time problem distinct from the component dependency
graph) was resolved differently than anticipated: rather than waiting for the live
`historical_archive.py` archive to accrue — it remains empty today, since Track 1 (Pipeline
Integration) has not executed — the `"ml"` method's training series is assembled **offline**,
directly from Open-Meteo Archive API backfill run through the existing IEEE 738 thermal model.
See `docs/data-science/decisions/forecasting_model.md` for the full data-provenance detail.

## Blocks

Nothing else in this roadmap depends on C9.

## Parallel-safe with

C10 — both Phase 4, but distinct models (forecasting vs. anomaly detection) with no obvious
shared code beyond both consuming C4/C5 outputs. Workable by different people simultaneously.

## Known Issues

Sourced from `docs/data-science/decisions/forecasting_model.md`'s Limitations section:

- **No per-city model exists yet.** The per-city refit (one city's own rows, that city's own
  ampacity as the target) needs live Open-Meteo data and has not been run. Until it is, `"ml"`
  raises `FileNotFoundError` for every city, and the shadow-pipeline ML candidates report
  `status="unavailable"` with a named reason (`decisions/point_scope.md`).
- The accuracy evidence in `decisions/forecasting_model.md` was measured on the retired
  corridor-level series (a two-endpoint-city proxy whose target was the weaker of two cities'
  ampacities). It is a corridor-era record and does not describe per-city model accuracy; a
  per-city bake-off would have to be re-run to produce that.
- The Open-Meteo backfill depth (`config.FORECAST_ML_TRAINING_YEARS`, currently 3 years) is a
  fixed choice inside a proposed band, not a value tuned against measured accuracy.
- A clean checkout has **no model artifact** until
  `.venv/bin/python3 backend/forecast_training.py --bakeoff` (or `--city <CITY>`) is run —
  `data/models/` is git-ignored, generated data, not part of the repository checkout.

## Acceptance Criteria

Implementation-testable, replacing the pre-implementation placeholder:

- `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py` and
  `.venv/bin/python3 -m pytest -q backend/tests/forecast_training_test.py` both pass.
- Those suites enforce, by name: no future weather leaks into a feature row (no lag/rolling
  feature may see its own or a later row); the `"ml"` point forecast is genuinely sensitive to
  its weather inputs while `"naive"`/`"ewm"` are provably unaffected by the same edit; the
  confidence band's width comes from `backtest_residuals`'s walk-forward machinery alone, for
  every method, never a second/parallel band implementation; and per-city model artifacts
  are isolated (`_MODEL_CACHE` never serves city A's model for a city B request).
- `docs/data-science/decisions/forecasting_model.md` is the out-of-sample accuracy evidence:
  measured MAE/RMSE per candidate per corridor (corridor-era; per-city numbers do not exist yet), an expectation stated before the verdict, and an
  explicit met/not-met verdict — replacing "looks reasonable" with the record's stated
  expectation (the chosen candidate's held-out MAE beating both `"naive"` and `"ewm"` on the
  identical series) as the explicit, agreed error margin this section originally called for.

## Open Questions

- ~~Regression vs. neural network~~ — **answered, on measured evidence.** Per
  `docs/data-science/decisions/forecasting_model.md`, `MLPRegressor` (the neural-network
  candidate) was selected over `HistGradientBoostingRegressor` (the regression candidate) for
  both retired corridors, by comparing measured out-of-sample MAE between the two. That same record
  also states, and does not soften, that neither candidate currently beats the existing `"naive"`
  baseline at the current 60-minute horizon — the estimator-selection question and the
  overall-improvement-over-naive question are answered separately, and only the first reads as a
  clean win.
- What forecast horizon matters for the dashboard's "trusted duration" feature — minutes, hours?
  Still genuinely open; no dashboard requirement has been specified yet.
- Does this feed C10 (e.g. using forecast/actual divergence as an anomaly signal), or are they
  fully independent models? **Partly answered today**: `backend/anomaly_detector.py`'s
  `_check_against_forecast` already consumes a `ForecastResult`'s band as one of its detection
  signals (widening the forecast's confidence band by a control-limit multiplier) when a
  forecast is available. Whether that coupling should deepen, and whether it should account for
  the forecasting_model.md's naive-wins finding, remains open.
