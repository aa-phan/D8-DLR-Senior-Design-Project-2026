# Phase 1: Forecasting Model - Research

**Researched:** 2026-09-24
**Domain:** Multivariate, per-location time-series ML forecasting (regression or neural network) layered on an existing physics-based (IEEE 738) dynamic-line-rating pipeline with a locked public interface contract (Python 3.12 / pandas / numpy / scipy)
**Confidence:** MEDIUM — every codebase fact below was read directly from the actual files this session (HIGH); the recommended architecture pattern for reusing `backtest_residuals` with a multivariate ML method is a design recommendation, not yet-existing code (MEDIUM); the specific estimator class is intentionally left an open, evidence-driven decision per CONTEXT.md D-01 (not a research gap — a locked scope boundary).

## Summary

This phase extends `backend/ampacity_forecast.py`'s two-method Tier-1 baseline (`"naive"`, `"ewm"` — both a pure function of the univariate `dlr_amps` series, added in the prior v1.0 Phase 4) with a real, fitted-model Tier-2 method. The prior phase's own research (`04-RESEARCH.md`) explicitly deferred this exact upgrade behind a "wait for real data volume" gate and flagged `scikit-learn`/`statsmodels` as `[SUS]`-but-legitimate dependencies requiring a `checkpoint:human-verify` before install — that data-volume blocker is resolved this phase by *not* waiting for the live (currently empty) `historical_archive.py` CSV, but instead assembling a real, multi-year, per-location training/validation series offline from Open-Meteo Archive-API backfill run through the existing `thermal_model.ieee738_ampacity`, and the human-verify checkpoint itself is pre-waived by CONTEXT.md D-02 (the legitimacy *scan* is still required and was run this session — see Package Legitimacy Audit).

The central engineering finding this session: `ampacity_forecast.py`'s two private helpers, `_point_forecast` and `backtest_residuals`, both currently operate on a bare `pd.Series` of `dlr_amps` values only — there is no path today for a method to see the weather columns (`air_temp`, `wind_speed`, `solar_radiation`) that D-04 requires as model inputs. The recommended pattern is a **backward-compatible internal signature extension**: give both helpers an optional way to receive the full `history` frame (not just the series) so a new method can build multivariate lag features, while `"naive"`/`"ewm"` keep calling the unchanged, series-only path. This satisfies D-04 (multivariate features), the ROADMAP's "no signature or schema break" contract (only the *public* `forecast_ampacity` signature is frozen — its two private helpers are not), and CONTEXT.md's explicit instruction to reuse `backtest_residuals`' walk-forward exclusivity guarantee rather than hand-rolling a second band.

The second central finding: `historical_archive.ARCHIVE_COLUMNS` already includes a `corridor` column, and `historical_archive.read_history(corridor=...)` already filters to one corridor per call — so the `history` frame `forecast_ampacity` receives at runtime already carries its own location identity with zero signature change needed. This directly answers D-05's "mechanism for selecting the right location's fitted model" open question: read `history["corridor"]`, look up a persisted per-corridor model, mirroring `config.STATIC_RATINGS`'s keying convention but at the corridor grain (2 keys — `AUSTIN_CORPUS_CHRISTI`, `MIDLAND_EL_PASO` — not the 4-city grain), since the corridor is the only location identity actually present in the frame the public function is contractually limited to.

**Primary recommendation:** Build a small offline training/evaluation script (not part of `ampacity_forecast.py`'s runtime import graph) that (1) backfills Open-Meteo weather for each of the 4 cities, (2) derives a corridor-level `dlr_amps` series per corridor using the codebase's own established weakest-link `min()` reduction (already used by `corridor_discretization.rate_corridor` and `ercot_dlr_merger.process_dlr_to_hourly`) across each corridor's two endpoint cities, (3) engineers lagged multivariate features (weather + lagged `dlr_amps`), (4) fits and backtests both a `scikit-learn` regression candidate (e.g. `HistGradientBoostingRegressor`) and a `scikit-learn` neural-network candidate (`MLPRegressor` — already part of `scikit-learn`, no second heavy dependency needed) per corridor using an extended, `backtest_residuals`-compatible walk-forward split, (5) picks whichever wins on out-of-sample MAE/RMSE against each other AND against `naive`/`ewm` on the identical data (D-01's evidence-based mandate), (6) persists the winning fitted model per corridor via `joblib`, and (7) writes the comparison to a new `docs/data-science/decisions/forecasting_model.md` ADR (D-06) alongside correcting the stale `C9-ampacity-forecasting.md` spec (D-07). At runtime, `forecast_ampacity(history, method="ml")` (exact name is the planner's call) loads the persisted model for `history["corridor"]`, builds the same lag features from `history`'s own tail, and reuses the extended `backtest_residuals` path (walking the *fixed*, already-fitted model forward — no per-step retraining) to produce the same empirical-quantile confidence band shape the naive/EWM methods already return.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Regression vs. neural network is fully open — the researcher/planner decides based
  on measured out-of-sample backtested accuracy on the actual assembled real-data training
  series, with **no default lean toward either approach**. Do not treat "regression" as a safer
  default; make the call on evidence once real data is assembled.
- **D-02:** A new ML dependency is **pre-approved** — the package-legitimacy review this
  project's `09-RESEARCH.md` precedent would otherwise require as a human checkpoint is not
  needed as a blocking gate here. — **Reversibility:** reversible — approval of a class of
  dependency, not a specific pin; a specific chosen library can still be swapped before it's
  used anywhere else.
- **D-03:** The approval is **not scoped to scikit-learn specifically** — the researcher/planner
  has latitude to pick whichever well-established scientific-Python ML library best fits the
  chosen model approach (e.g. scikit-learn, statsmodels, xgboost), still subject to this
  project's standard package-legitimacy verification pass (registry/typosquat check) before the
  first import lands — that verification step itself is not skipped, only the human
  re-approval checkpoint on top of it.
- **D-04:** Model inputs are **multivariate**, not autoregressive-only: feed the real weather
  variables already flowing through the pipeline (wind speed, temperature, solar irradiance —
  the same Open-Meteo-backfill-derived series used to compute the training `dlr_amps` target)
  alongside lagged `dlr_amps`, not just past ampacity values the way naive/EWM do.
- **D-05:** Train **per-location models** (per corridor, or per city — researcher's call on
  exact granularity), not one shared model across all four cities/both corridors. This matches
  the existing per-location pattern already established in this codebase
  (`config.STATIC_RATINGS`, `config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION`,
  `config.RATING_BOUNDS_BY_LOCATION`) and avoids one corridor's climate signal (Austin↔Corpus
  Christi's coastal/humid pattern vs. Midland↔El Paso's arid West Texas pattern) diluting the
  other's. The exact mechanism for selecting/loading the right location's fitted model inside
  `forecast_ampacity` (which today takes only a `history` frame, no explicit location parameter)
  is left to research/planning to design — it must not require a signature change per the
  locked interface contract in ROADMAP.md.
- **D-06:** FCST-02's written validation record is a **new file under
  `docs/data-science/decisions/`** (matching this project's existing ADR-style convention —
  `data_provider.md`, `geographic_scope.md`), not a spec update and not only the plan's own
  `SUMMARY.md`. Name it descriptively for the model built (e.g.
  `docs/data-science/decisions/forecasting_model.md`) — exact filename is the planner's call.
- **D-07:** This phase also **corrects the stale `docs/data-science/specs/C9-ampacity-forecasting.md`**
  spec file alongside writing the new decision doc: its "Current Implementation" section and
  Status line still say "None. No model code... exists anywhere in the repo," which has been
  false since v1.0 Phase 4 shipped the naive/EWM methods and becomes even more false once this
  phase lands a trained model. Update it to reflect what naive/EWM already are and what this
  phase adds — same kind of documentation-debt correction as v1.1's `PRD.md` §7.1 ratification.

### Claude's Discretion

- Exact model class within "regression or neural network" (e.g. which specific
  scikit-learn/statsmodels/xgboost estimator).
- Exact per-location granularity (per-city vs. per-corridor) and the mechanism for selecting the
  right location's fitted model inside `forecast_ampacity` without a signature change.
- Exact feature engineering details: lag window size, which weather variables beyond
  wind/temp/solar (if any), how missing/null weather values are handled going into the model.
- Exact filename and structure of the new `docs/data-science/decisions/` validation record.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within Phase 1 scope. (Phase 2 — Anomaly Detection Model — is a
separate, independent phase in this same workstream; not discussed here.)

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FCST-01 | An ML model (regression or neural network) forecasts ampacity ahead of real time, dropped in behind `forecast_ampacity`'s existing signature and `PIPELINE_SCHEMA` output columns | Architecture Patterns (Pattern 1, 2, 4), Standard Stack, Code Examples |
| FCST-02 | The model's accuracy/calibration is validated against real historical archive data (not synthetic fixtures) and the results are documented | Architecture Patterns (Pattern 3), Validation Architecture, Common Pitfalls (Pitfall 1, 4), Sources |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Historical weather backfill (Open-Meteo) | API / Backend | — | Already-shipped adapter (`open_meteo_provider.py`), pure HTTP fetch, no DB tier exists |
| Corridor-level `dlr_amps` target derivation (weakest-link `min()` over endpoint cities) | API / Backend | — | Pure function composition over `thermal_model.ieee738_ampacity`; mirrors `corridor_discretization.rate_corridor`'s existing tier placement |
| Feature engineering (lags, multivariate frame assembly) | API / Backend | — | In-process pandas transform, no persistence tier of its own |
| Model fit + offline backtest/bake-off | API / Backend | Database/Storage (reads/writes the persisted model artifact) | Offline training script, not a request-time computation |
| Model artifact persistence (`joblib`) | Database / Storage (flat-file, mirrors `historical_archive.py`'s own CSV-on-disk convention) | — | No SQL/object-store tier exists anywhere in this repo; a versioned file under `data/models/` matches the existing `data/historical/` convention |
| `forecast_ampacity` runtime inference + confidence band | API / Backend | — | Same tier as the existing naive/EWM methods it extends |
| Validation record (`docs/data-science/decisions/forecasting_model.md`) | Documentation (no runtime tier) | — | ADR-style doc, not code |

## Standard Stack

### Core (already installed — verified this session, project's actual `.venv`, not system Python)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.3.3 [VERIFIED: `.venv/bin/python3 -m pip list`, this session] | Frame assembly, lag features (`.shift()`), time-indexed joins | Already the pipeline's dataframe backbone throughout `backend/` |
| numpy | 2.4.3 [VERIFIED: `.venv/bin/python3 -m pip list`, this session] | Array math, `ieee738_ampacity`'s vectorized core | Already used throughout `thermal_model.py` |
| scipy | 1.17.1 [VERIFIED: `.venv/bin/python3 -m pip list`, this session] | Available for auxiliary stats if needed | Already installed; no new dependency needed for anything scipy already covers |

### Supporting (new dependency — this phase's ML library)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scikit-learn [ASSUMED: package name from training knowledge, cross-checked against the real PyPI registry this session — see Package Legitimacy Audit] | 1.9.1 latest [VERIFIED: `.venv/bin/python3 -m pip index versions scikit-learn`, this session — confirmed absent from `.venv` before this check] | Regression candidates (`HistGradientBoostingRegressor`, `Ridge`) AND the neural-network candidate (`MLPRegressor`, bundled in the same package) for D-01's bake-off; `TimeSeriesSplit` for the leakage-safe backtest; `joblib` (a `scikit-learn` dependency, always installed alongside it) for model persistence | Covers **both** arms of D-01's "regression or neural network" choice from a single new dependency — recommended over adding a second, heavier deep-learning library (PyTorch/TensorFlow) unless a bake-off later shows `MLPRegressor` is genuinely insufficient |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `scikit-learn` `MLPRegressor` (in-package NN) | A dedicated deep-learning library (PyTorch/TensorFlow) | A per-location tabular dataset of a few tens of thousands of hourly rows with ~10-20 engineered features does not need GPU-scale deep learning; a second heavy dependency would also need its own fresh legitimacy pass, doubling D-02/D-03's dependency-approval surface for no demonstrated benefit yet |
| `scikit-learn` `HistGradientBoostingRegressor` | `xgboost` | `xgboost` [ASSUMED name, `[SUS]` per legitimacy check this session, same as `scikit-learn`/`statsmodels`] is a real, well-established boosting library, but adds a second new dependency when `scikit-learn`'s native histogram-based GBM already covers the same regression family without a second install |
| `scikit-learn` overall | `statsmodels` (classical time-series: ARIMA/Holt-Winters/SARIMAX) | `statsmodels` [ASSUMED name, `[SUS]` per legitimacy check this session] is the natural fit if the bake-off favors a *pure* autoregressive/seasonal-smoothing approach over a feature-driven regressor, but D-04 explicitly requires multivariate exogenous weather inputs, which `scikit-learn` regressors handle more directly than `statsmodels`' classical univariate/SARIMAX API; keep as a documented fallback if the bake-off surprises |
| Fold-based `TimeSeriesSplit` backtest for the new method | Literal per-row expanding-window retraining (naive/EWM's current pattern, extended unchanged to the ML method) | Retraining a `scikit-learn` estimator at every one of potentially tens of thousands of hourly rows is a well-documented computational-cost trap in walk-forward validation [CITED: MachineLearningMastery "How To Backtest Machine Learning Models for Time Series Forecasting", scikit-learn `TimeSeriesSplit` docs]; a handful of expanding folds preserves the same "train strictly precedes test" guarantee at a fraction of the cost |

**Installation:**
```bash
.venv/bin/pip install scikit-learn
```
Then add a pinned line to the existing `requirements.txt` (`scikit-learn==1.9.1`), replacing that
file's current comment block explaining their deliberate absence
[VERIFIED: `requirements.txt`, read this session — quoted verbatim: `"Tier 2 modelling libraries
(scikit-learn, statsmodels) are deliberately absent per D-10: there is no historical data yet to
justify or validate them against, and both carry unresolved [SUS] legitimacy verdicts in
04-RESEARCH.md's Package Legitimacy Audit. Neither may be added without the human legitimacy
checkpoint that audit requires."`] — that human-checkpoint condition is exactly what CONTEXT.md
D-02 waives for this phase; the comment itself should be updated/removed as part of the same edit
that adds the pin (a stale "may not be added without a checkpoint" comment sitting next to an
actual pin would itself be a new documentation-debt bug of the kind D-07 is already fixing
elsewhere).

**Version verification:** Confirmed directly against the real PyPI registry via the project's own
`.venv`, not a training-data guess:
```bash
.venv/bin/python3 -m pip index versions scikit-learn   # -> 1.9.1 (latest), deep 0.9-1.9.1 history
.venv/bin/python3 -m pip index versions statsmodels     # -> 0.15.0 (latest), deep 0.4-0.15.0 history
.venv/bin/python3 -m pip index versions xgboost          # -> 3.4.1 (latest), deep 0.7-3.4.1 history
```
All three were also confirmed absent from the actual installed `.venv` this session
(`.venv/bin/python3 -c "import sklearn"` -> `ModuleNotFoundError`), consistent with `requirements.txt`'s
own comment and `STACK.md`'s "pandas/numpy/scipy only" characterization — this phase is the first
to actually add one.

## Package Legitimacy Audit

Run this session via the project's legitimacy seam (`gsd_run query package-legitimacy check --ecosystem pypi scikit-learn statsmodels xgboost`) — identical verdicts to the prior `04-RESEARCH.md` pass, confirming this is a stable characteristic of the seam's metadata gaps for these three packages, not a new red flag.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `scikit-learn` | PyPI | Deep version history 0.9 -> 1.9.1 across dozens of releases [VERIFIED: `pip index versions scikit-learn`, this session] | null — legitimacy seam could not resolve download-count metadata | not returned by legitimacy seam | `[SUS]` (`too-new`, `unknown-downloads`, `no-repository`) [VERIFIED: `gsd_run query package-legitimacy check --ecosystem pypi scikit-learn`, this session] | **Approved, no `checkpoint:human-verify` required** — CONTEXT.md D-02 explicitly pre-waives the human-approval checkpoint this `[SUS]` verdict would otherwise trigger (per `09-RESEARCH.md`'s precedent). The verification *scan* itself (this table) is still required by D-03 and was run. Same "incomplete metadata, not a real red flag" pattern the prior `04-RESEARCH.md` pass already documented for this exact package. |
| `statsmodels` | PyPI | Deep version history 0.4 -> 0.15.0 [VERIFIED: `pip index versions statsmodels`, this session] | null | not returned | `[SUS]` (`too-new`, `unknown-downloads`, `no-repository`) [VERIFIED: `gsd_run query package-legitimacy check --ecosystem pypi statsmodels`, this session] | **Not recommended for this phase** (see Alternatives Considered). If a future plan adopts it, D-02's waiver still applies — no new checkpoint needed, but re-run this table's scan for the actual chosen version at that time. |
| `xgboost` | PyPI | Deep version history 0.7 -> 3.4.1 [VERIFIED: `pip index versions xgboost`, this session] | null | not returned | `[SUS]` (`unknown-downloads`, `no-repository`) [VERIFIED: `gsd_run query package-legitimacy check --ecosystem pypi xgboost`, this session] | **Not recommended for this phase** (see Alternatives Considered — `scikit-learn`'s native `HistGradientBoostingRegressor` covers the same regression family without a second dependency). |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `scikit-learn`, `statsmodels`, `xgboost` — all three, per CONTEXT.md D-02, are **exempted from the `checkpoint:human-verify` gate** this project's protocol would otherwise require for a `[SUS]` verdict. The planner should NOT insert a `checkpoint:human-verify` task before the `scikit-learn` install specifically because D-02 names this exact scenario ("the package-legitimacy review this project's `09-RESEARCH.md` precedent would otherwise require as a human checkpoint is not needed as a blocking gate here"). This is a documented, user-approved deviation from the default protocol, not an oversight — do not "correct" it back in by re-adding the checkpoint at plan time.

## Architecture Patterns

### System Architecture Diagram

```
                         OFFLINE (training / evaluation — new script, this phase)
                         ============================================================
Open-Meteo Archive API            Open-Meteo Archive API
  (AUSTIN lat/lon)                  (CORPUS_CHRISTI lat/lon)          ... (MIDLAND, EL_PASO)
        |                                  |
        v                                  v
open_meteo_provider.fetch_open_meteo()  (one call per city, per config.CITY_COORDINATES)
        |                                  |
        v                                  v
thermal_model.perpendicular_wind()  -> thermal_model.ieee738_ampacity()   (per city, per corridor's line_azimuth)
        |                                  |
        +----------------+-----------------+
                          v
        [NEW] weakest-link min() reduction across each corridor's 2 endpoint cities
              (mirrors corridor_discretization.rate_corridor's existing min() convention)
                          |
                          v
        [NEW] per-corridor lag-feature frame: air_temp/wind_speed/solar_radiation
              (bottleneck city's own weather, matching runtime's own bottleneck-point
              archiving rule) + lagged dlr_amps, target = dlr_amps shifted forward by horizon
                          |
                          v
        [NEW] fit + bake-off: scikit-learn regression candidate vs. MLPRegressor,
              backtested via an extended backtest_residuals-compatible walk-forward split,
              ALSO compare naive/ewm on the identical assembled series (apples-to-apples)
                          |
                          v
        [NEW] winner persisted per corridor: data/models/forecast_<corridor>.joblib
                          |
                          v
        [NEW] docs/data-science/decisions/forecasting_model.md (D-06) — measured accuracy,
              comparison table, met-expectations verdict
              + docs/data-science/specs/C9-ampacity-forecasting.md corrected (D-07)


                         RUNTIME (unchanged call site, new method value)
                         ============================================================
historical_archive.read_history(corridor=X)  -->  history: pd.DataFrame (has "corridor" column)
                          |
                          v
        ampacity_forecast.forecast_ampacity(history, horizon_min, method="ml")
                          |
              +-----------+------------------------------+
              v                                            v
     [NEW] load data/models/forecast_<history["corridor"]>.joblib     _extract_series() (unchanged,
              |                                            |           still used for naive/ewm)
              v                                            |
     [NEW] build lag features from history's own tail       |
              |                                            |
              v                                            v
     point forecast = fitted_model.predict(features)   backtest_residuals (EXTENDED: accepts
              |                                          full history for the "ml" method,
              +----------------------> band <-------------  walks the FIXED model forward,
                                                              no per-step retraining)
                          |
                          v
              ForecastResult -> forecast_columns() -> same 4 PIPELINE_SCHEMA columns
                          |
                          v
              (unchanged) Track 1's future pipeline caller / DLRSafetyMonitor
```

A reader can trace the primary use case both ways: offline, real weather -> physics ampacity ->
corridor-level weakest-link reduction -> lag features -> fitted model -> persisted artifact ->
written validation record; at runtime, the exact same public function signature reads the
persisted artifact keyed off the frame's own `corridor` column and produces the same four output
columns every existing caller already understands.

### Recommended Project Structure
```
backend/
├── ampacity_forecast.py        # MODIFY — add "ml" (or similar) to FORECAST_METHODS;
│                                #   extend _point_forecast/backtest_residuals internals
│                                #   (new optional params), _extract_series unchanged
├── forecast_training.py        # NEW — offline assembly + bake-off + persistence script
│                                #   (not imported by the runtime pipeline; a standalone
│                                #   entry point, mirroring ercot_data_retriever.py's own
│                                #   __main__-driven, offline-data-pull convention)
├── config.py                   # MODIFY — new constants: lag window size, backfill window
│                                #   length, model artifact path template
data/
├── models/                     # NEW — persisted per-corridor joblib artifacts
│                                #   (git-ignored, mirrors data/historical/'s own convention)
docs/data-science/
├── decisions/
│   └── forecasting_model.md    # NEW (D-06) — ADR-style validation record
├── specs/
│   └── C9-ampacity-forecasting.md  # MODIFY (D-07) — correct stale "no model exists" claim
backend/tests/
├── ampacity_forecast_test.py   # MODIFY — new tests for the "ml" method's forecast_ampacity
│                                #   path (fixture-injected fitted model, no real network/joblib
│                                #   I/O in unit tests)
├── forecast_training_test.py   # NEW — unit tests for feature engineering / min() reduction
│                                #   logic, using synthetic weather (real-network calls are
│                                #   integration-only, see Validation Architecture)
```

### Pattern 1: Backward-compatible internal signature extension for multivariate methods

**What:** `_point_forecast(series, method, halflife_min=None)` and
`backtest_residuals(series, method, min_train_rows=None, halflife_min=None)` both currently take
only a `pd.Series` of `dlr_amps`. Extend both with a new optional parameter (e.g.
`history: pd.DataFrame = None`) that, when provided, gives the method access to the weather
columns. `"naive"`/`"ewm"` never pass it and behave byte-identically to today. The new ML method
requires it and raises if it's missing.
**When to use:** Any new multivariate method added to `FORECAST_METHODS`.
**Basis (verbatim, existing signatures read this session — `backend/ampacity_forecast.py:93-171`):**
```python
def _point_forecast(series: pd.Series, method: str, halflife_min=None) -> float:
    ...
def backtest_residuals(series: pd.Series, method: str, min_train_rows=None,
                        halflife_min=None) -> np.ndarray:
    ...
```
This is an internal-only extension — the ROADMAP's locked contract is specifically
`ampacity_forecast.py::forecast_ampacity(history, horizon_min, method="naive", ...)`'s *public*
signature and `ForecastResult`'s columns, not these two private helpers, so extending their
parameter lists is not a contract break.

### Pattern 2: Per-corridor model selection from `history["corridor"]`, zero signature change

**What:** `forecast_ampacity`'s only per-call location signal is whatever `history` already
contains. `historical_archive.ARCHIVE_COLUMNS` already includes `corridor`, and
`historical_archive.read_history(corridor=...)` already filters a call's `history` to exactly one
corridor.
**Basis (verbatim, read this session — `backend/historical_archive.py:38-50`):**
```python
ARCHIVE_COLUMNS: list[str] = [
    "datetime_utc",
    "corridor",
    "air_temp",
    "wind_speed",
    "solar_radiation",
    "dlr_amps",
    "static_rating",
    "status",
    "fallback",
    "bottleneck_index",
    "schema_version",
]
```
And the test fixture already models a single-corridor frame (`backend/tests/ampacity_forecast_test.py:46`):
`"corridor": ["AUSTIN_CORPUS_CHRISTI"] * n_rows`.
**Recommended mechanism:** inside the new method's `_point_forecast`/`backtest_residuals` path,
read `history["corridor"].iloc[-1]` (or assert a single unique value across the frame, raising a
clear `ValueError` if the caller ever passes a mixed-corridor frame — which should never happen
given `read_history(corridor=...)`'s own filtering), then look up
`data/models/forecast_<corridor>.joblib`. This directly answers D-05's open "mechanism" question
without touching `forecast_ampacity`'s public parameter list.
**Per-corridor vs. per-city:** `historical_archive.py`'s own docstring is explicit that the
archive "holds one row per corridor per run" — the frame's only location key is the corridor
(2 possible values: `AUSTIN_CORPUS_CHRISTI`, `MIDLAND_EL_PASO`, from
`config.CORRIDOR_ENDPOINTS`), not one of the 4 cities `config.STATIC_RATINGS` uses. Recommend
**per-corridor granularity** (2 models) as the grain that requires zero additional
location-derivation logic at the one runtime data source `forecast_ampacity` is contractually
limited to reading — see Assumptions Log A2 for the tradeoff against D-05's city-keyed-precedent
citation.

### Pattern 3: Weakest-link `min()` reduction for offline corridor-level training data

**What:** The corridor's archived weather/rating is always the *bottleneck point's own*
observation — the single point (of several along the corridor) whose rating the corridor
actually reports — never an average or another point's reading.
**Basis (verbatim, read this session — `backend/corridor_discretization.py:482-486`):**
```
Build and append one archive row for this `rate_corridor` call (D-08: one row per corridor
per run). The archived weather is the bottleneck point's own observation -- the point whose
rating the corridor actually reports -- so the archived weather is always the weather that
produced the archived rating, never another point's (T-04-13).
```
And the reduction itself (`backend/corridor_discretization.py:546-549`):
```
reduce the per-point ratings to a single corridor-level rating via `min()` -- mirroring
`ercot_dlr_merger.process_dlr_to_hourly`'s `.min()` weakest-link reduction, on the space axis
instead of the time axis.
```
**When to use:** Assembling the offline per-corridor training series. Real per-point station
probes are not available for a multi-year backfill (`resolve_point_observation`'s live-station
discovery only works for the current/recent window), so approximate the bottleneck with the
corridor's **two endpoint cities** (`config.CORRIDOR_ENDPOINTS`, `config.CITY_COORDINATES` — both
already have real Open-Meteo backfill coverage): compute `ieee738_ampacity` independently for
each endpoint city's weather series (using `config.conductor_kwargs_for(line_azimuth)` for that
corridor), then take the elementwise `min()` of the two cities' ampacity series as the training
target, and take the *winning* (lower-ampacity) city's own weather at each timestamp as that row's
feature values — the same "weather that produced the rating" rule the runtime archive already
follows. Flag this two-city proxy explicitly as an approximation of the true (future, Track-1-built)
n-point bottleneck — see Assumptions Log A1.

### Pattern 4: Persist the fitted model; never refit inside the request/backtest hot path

**What:** Fit each corridor's model **once**, offline, in `forecast_training.py`. At runtime and
during the OOS backtest, only ever call `.predict()` on the already-fitted, loaded model — never
`.fit()`.
**When to use:** Every call to the new method, and the extended `backtest_residuals` path for it.
**Why:** Retraining at every step of an expanding-window walk-forward over a multi-year hourly
series (tens of thousands of steps) is a documented computational-cost trap
[CITED: MachineLearningMastery "How To Backtest Machine Learning Models for Time Series
Forecasting"; scikit-learn `TimeSeriesSplit` docs, "each fold retrains the model, which becomes
costly at scale"]. Because the offline bake-off already produces a **fixed** fitted model, the
extended `backtest_residuals` path for the ML method does not need to retrain per step at all —
it only needs to evaluate the fixed model's prediction against each row's own strictly-prior lag
features and compare to the actual outcome, which is cheap and still genuinely out-of-sample
(the model's parameters were fit on an earlier, non-overlapping split). Persist via `joblib.dump`/
`joblib.load` [CITED: scikit-learn "Model persistence" docs — joblib is scikit-learn's own
documented preferred format for numpy-array-heavy estimators over raw `pickle`].
**Anti-pattern to avoid:** Calling `.fit()` inside `forecast_ampacity` or inside the per-row loop
of `backtest_residuals` for the ML method — this both violates "no signature/schema break" in
spirit (a request-time fit is a hidden, unbounded-latency side effect no naive/ewm caller expects)
and reintroduces the exact retraining-cost trap this pattern exists to avoid.

### Anti-Patterns to Avoid
- **Feeding the model weather observed at (or after) the forecast target time.** The model must
  only ever see weather/`dlr_amps` known as of the time the forecast is made — feeding
  `horizon_min`-ahead weather as an input feature is not a forecast, it's a physics recomputation,
  and is not available at real deployment time anyway (see Pitfall 4).
- **A second, parallel confidence-band implementation for the ML method** (e.g. `predict_proba`-style
  quantile regression bounds computed independently of `backtest_residuals`). CONTEXT.md is explicit
  that the same empirical-residual walk-forward machinery must produce the band, so it stays
  apples-to-apples with naive/EWM.
- **Refitting per walk-forward step** for the ML method (Pattern 4).
- **A new, parallel `PIPELINE_SCHEMA`-shaped output for the ML method.** `forecast_columns()` is
  the only place a `ForecastResult` becomes pipeline output; the new method must still return a
  plain `ForecastResult` through the existing constructor.
- **Loading an untrusted/unversioned joblib artifact.** `joblib`/`pickle`-based deserialization
  executes arbitrary code on load [CITED: scikit-learn "Model persistence" docs, explicit security
  note] — only ever load artifacts this repo's own training script produced (see Security Domain).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Leakage-safe train/test split for the offline bake-off | A hand-rolled loop slicing `history.iloc[:i]`/`history.iloc[i:]` per fold | `sklearn.model_selection.TimeSeriesSplit` | Standard, tested, enforces "train strictly precedes test" with no shuffling [CITED: scikit-learn `TimeSeriesSplit` docs] |
| Confidence/uncertainty band for the new method | A separate quantile-regression or bootstrap band computed only for the ML method | The existing `backtest_residuals` empirical-quantile band (Pattern 1's extension) | CONTEXT.md explicitly requires reuse so the band stays apples-to-apples with naive/EWM, not a second band implementation |
| Model persistence | Hand-rolled JSON/CSV dump of model coefficients | `joblib.dump`/`joblib.load` | scikit-learn's own documented, tested persistence path for numpy-array-heavy estimators [CITED: scikit-learn "Model persistence" docs] |
| Corridor-level target/feature aggregation for training | A new, independently-invented city-combination rule (mean, weighted average, etc.) | The existing weakest-link `min()` convention (`corridor_discretization.rate_corridor`, `ercot_dlr_merger.process_dlr_to_hourly`) | Already the codebase's one established, tested convention for reducing multiple spatial readings to one corridor value; a second competing aggregation rule would silently diverge from what the runtime archive actually records |
| Great-circle / corridor geo math | Reimplementing haversine/bearing formulas for endpoint lookups | Existing `config.CITY_COORDINATES`, `config.CORRIDOR_ENDPOINTS` | Already-defined, live-verified coordinates; no geo math is actually needed for a two-endpoint-city proxy |

**Key insight:** This codebase's existing discipline — one physics source of truth
(`thermal_model.py`), one fallback contract (`DLRSafetyMonitor._fallback`), one centralized
config module, one weakest-link reduction rule, one walk-forward backtest function — already *is*
the anti-hand-rolling posture this phase needs. The only genuinely new tool this phase introduces
is the ML library itself (`scikit-learn`); everything else should extend an existing, already-tested
in-repo mechanism.

## Common Pitfalls

### Pitfall 1: Retraining the model at every walk-forward step over a multi-year hourly series
**What goes wrong:** A literal one-row-at-a-time expanding-window retrain (naive/EWM's current
pattern, applied unchanged to an ML estimator) over tens of thousands of hourly rows can take
hours to days depending on the estimator.
**Why it happens:** `backtest_residuals`' existing loop calls `_point_forecast` fresh at every
step; for naive/EWM this is nearly free (no fit step exists), but a real estimator's `.fit()` is
not free at scale.
**How to avoid:** Pattern 4 — fit once offline, walk the *fixed* model forward for OOS residuals
(cheap), or use a small number of `TimeSeriesSplit` folds for the bake-off comparison rather than
per-row refitting.
**Warning signs:** The offline training script's runtime growing linearly (or worse) with row
count in a way that would make CI/re-training impractical; a backtest that silently truncates the
training window to "make it fast enough" without that truncation being a documented decision.

### Pitfall 2: `ieee738_ampacity`'s `np.ndarray`-vs-`float` boundary trap (carried over, still applies)
**What goes wrong:** `thermal_model.ieee738_ampacity` returns `np.ndarray` even for scalar input
[VERIFIED: `backend/thermal_model.py:180-181`, `I = np.sqrt(...)  return I`]. New offline
training-assembly code that derives the `dlr_amps` target from this function's output will
silently carry 0-d/1-element arrays instead of scalars if not wrapped.
**How to avoid:** Apply the same `float(...)` wrap already used elsewhere in this codebase
(`DLRSafetyMonitor._compute_ampacity`, `historical_archive.build_archive_row`) at every new
boundary that reads a computed ampacity value, including the offline training script.

### Pitfall 3: Redefining `PIPELINE_SCHEMA` or the `ForecastResult` shape ad hoc
**What goes wrong:** A new method path constructs its own result dict/columns instead of routing
through the existing `ForecastResult` constructor and `forecast_columns()`.
**How to avoid:** The new method's `forecast_ampacity` branch must still end in exactly one
`ForecastResult(...)` construction and let `forecast_columns()` do the mapping, unchanged.

### Pitfall 4: The model "cheating" by implicitly re-deriving physics instead of forecasting
**What goes wrong:** `dlr_amps` is a *deterministic* function of concurrent weather
(`ieee738_ampacity(T_amb, wind_perp, ghi, conductor)`) with no independent measurement noise. If
the feature set for predicting `dlr_amps` at time `t+horizon` is ever built from weather observed
**at or after** `t+horizon` (rather than strictly from `t` and earlier), the model doesn't learn
to forecast anything — it learns to numerically invert a closed-form equation it's given the exact
inputs to, producing a suspiciously perfect backtest score that would collapse the moment the
model is deployed against real future weather it doesn't have yet.
**Why it happens:** Easy to introduce accidentally during feature-frame construction (e.g. joining
weather and target on the same row index without an explicit forward shift).
**How to avoid:** The target column must be `dlr_amps` shifted **forward** by the horizon; the
feature columns must only ever be built from rows strictly at or before the *feature* timestamp,
never the target timestamp. Add an explicit unit test asserting the feature/target time
relationship (e.g. `feature_time + horizon == target_time`, `feature_time < target_time` always).
**Warning signs:** Near-perfect backtest MAE noticeably better than the naive/EWM baselines by an
implausible margin — a "too good to be true" score is exactly the anti-signal this project's own
prior research (`RESEARCH.md` Pitfall 1 precedent) already treats as suspect.

### Pitfall 5: Per-location granularity mismatch between D-05's cited precedent and the archive's actual key
**What goes wrong:** D-05 cites `config.STATIC_RATINGS`/`RATING_BOUNDS_BY_LOCATION`/
`ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` (4 city keys) as the established per-location pattern, but
`history["corridor"]` (the only location signal actually available inside `forecast_ampacity`)
only has 2 possible values.
**How to avoid:** Recommend per-corridor granularity (Pattern 2) as the grain requiring no new
location-derivation logic; if the planner instead wants strict per-city models, a corridor-to-city
mapping step would need to be designed and justified (which of the corridor's two cities "wins"
for a given call — not obviously answerable from `history` alone without also re-deriving the
bottleneck logic at runtime, which the archive already resolved once at write time and did not
persist as a separate city column).

### Pitfall 6: `[SUS]` legitimacy verdict mistaken for a blocking condition
**What goes wrong:** A planner unfamiliar with CONTEXT.md D-02 sees `scikit-learn` flagged
`[SUS]` in the Package Legitimacy Audit and reflexively inserts a `checkpoint:human-verify` task,
per this project's default protocol.
**How to avoid:** D-02 explicitly pre-waives that exact checkpoint for this phase's ML dependency
class. The scan itself (this document's Package Legitimacy Audit) still had to run — and did —
but no additional human-approval gate belongs in the plan.

## Code Examples

### Existing helper signatures to extend (Pattern 1)
```python
# Source: backend/ampacity_forecast.py:93-171 (read this session)
def _point_forecast(series: pd.Series, method: str, halflife_min=None) -> float:
    if method not in FORECAST_METHODS:
        raise ValueError(
            f"Unknown forecast method {method!r}; FORECAST_METHODS is {FORECAST_METHODS}"
        )
    if method == "naive":
        return float(series.iloc[-1])
    # method == "ewm" ...

def backtest_residuals(series: pd.Series, method: str, min_train_rows=None,
                        halflife_min=None) -> np.ndarray:
    ...
    for offset, i in enumerate(range(min_train_rows, n)):
        prefix = series.iloc[:i]
        prediction = _point_forecast(prefix, method, halflife_min)
        residuals[offset] = float(series.iloc[i]) - prediction
    return residuals
```

### Existing corridor-key precedent to reuse (Pattern 2)
```python
# Source: backend/historical_archive.py:38-50 (read this session)
ARCHIVE_COLUMNS: list[str] = [
    "datetime_utc", "corridor", "air_temp", "wind_speed", "solar_radiation",
    "dlr_amps", "static_rating", "status", "fallback", "bottleneck_index", "schema_version",
]
```

### Existing weakest-link reduction to mirror for offline target assembly (Pattern 3)
```python
# Source: backend/corridor_discretization.py:674-679 (read this session)
ratings = [p["rating"] for p in point_results]
min_rating = min(ratings)
bottleneck_index = ratings.index(min_rating)
```

### scikit-learn TimeSeriesSplit — the leakage-safe bake-off primitive
```python
# Source: scikit-learn model_selection.TimeSeriesSplit docs
# https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
from sklearn.model_selection import TimeSeriesSplit

tscv = TimeSeriesSplit(n_splits=5)  # expanding window, train always precedes test
for train_idx, test_idx in tscv.split(X):
    model.fit(X[train_idx], y[train_idx])
    preds = model.predict(X[test_idx])
```

### scikit-learn candidates for D-01's bake-off (regression vs. neural network, one dependency)
```python
# Both estimators live in the single new scikit-learn dependency — no second
# library needed to cover both arms of D-01's "regression or neural network" choice.
from sklearn.ensemble import HistGradientBoostingRegressor   # regression candidate
from sklearn.neural_network import MLPRegressor              # neural-network candidate

regression_model = HistGradientBoostingRegressor()
nn_model = MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=2000)
```

### Model persistence (Pattern 4)
```python
# Source: scikit-learn "Model persistence" docs
# https://scikit-learn.org/stable/model_persistence.html
from joblib import dump, load

dump(fitted_model, "data/models/forecast_AUSTIN_CORPUS_CHRISTI.joblib")
fitted_model = load("data/models/forecast_AUSTIN_CORPUS_CHRISTI.joblib")  # only ever load
                                                                            # this repo's own output
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| No forecasting at all (C9 spec: "None. No model code... exists anywhere in the repo") | Naive last-value / EWM Tier-1 statistical forecast with an empirical-residual walk-forward band | v1.0 Phase 4 (this project) | Established `FORECAST_METHODS`, `ForecastResult`, `backtest_residuals` — the exact scaffolding this phase extends |
| Tier-1 statistical baseline, explicitly deferred Tier-2 pending real data volume | Real fitted regression/NN model, trained on a real (Open-Meteo-backfill-derived) multi-year series | This phase (v1.3 Phase 1) | Resolves `04-RESEARCH.md`'s own "wait for volume" blocker by sourcing real data independent of the (still-empty) live archive |
| `_point_forecast`/`backtest_residuals` operate on a bare univariate `pd.Series` | (Recommended) optionally operate on the full multivariate `history` frame | This phase, if the recommended Pattern 1 extension is adopted | Enables D-04's multivariate feature requirement without a public signature break |

**Deprecated/outdated:** Nothing in this repo is deprecated by this phase — purely additive, exactly like the prior Phase 4.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Offline corridor-level training data is assembled by proxying the true (future, Track-1-built) n-point bottleneck with a 2-endpoint-city `min()` reduction, since real per-point historical station probes for a multi-year backfill don't exist. | Architecture Patterns (Pattern 3) | Once Track 1 accrues real per-point bottleneck history, the trained model's feature distribution may not exactly match live bottleneck-point weather statistics — the model may need retraining against real accrued data later, which the persisted-artifact design (Pattern 4) makes cheap to do without another interface change |
| A2 | Per-corridor (not per-city) granularity is recommended for D-05, based on `history["corridor"]` being the only location key actually present in the frame `forecast_ampacity` receives — even though D-05's cited precedent (`STATIC_RATINGS` etc.) is city-keyed. | Architecture Patterns (Pattern 2), Common Pitfalls (Pitfall 5) | If the user/planner actually wants strict per-city models, an additional corridor-to-city selection mechanism would need to be designed at plan time (D-05 explicitly leaves this open, so this is a recommendation, not a violation) |
| A3 | A multi-year (e.g. 2-5 years) Open-Meteo hourly backfill window per city is assumed to be a practical, sufficient training-volume default, absent any user-specified value. | Standard Stack, Architecture Patterns | Too short a window risks an unrepresentative/underfit model; too long risks including weather-pattern drift or slows offline fitting for no accuracy gain — exact window length is Claude's Discretion per CONTEXT.md, flagged here as needing a concrete number at plan time |
| A4 | `scikit-learn`'s in-package `MLPRegressor` is assumed sufficient to satisfy the "neural network" arm of D-01's bake-off without adding a second, heavier deep-learning dependency. | Standard Stack, Code Examples | If the bake-off shows `MLPRegressor` meaningfully underperforms a deeper architecture, a second dependency (e.g. PyTorch) would need its own fresh legitimacy scan under D-03 before being added |
| A5 | Open-Meteo's Archive API is assumed to comfortably support a multi-year single-request pull per city without server-side chunking failures, based on a general WebSearch (not a live probe against the actual multi-year range this phase needs) [CITED: general web search, not this project's own live call]. | Standard Stack, Environment Availability | If the live API actually caps single-request ranges more tightly than assumed, the offline script needs a per-year (or similar) chunked-fetch loop — a small, mechanical fallback, not a design change |

**If this table is empty:** N/A — see entries above; A1-A5 are flagged for confirmation before being treated as locked implementation decisions.

## Open Questions

1. **Exact estimator class (regression vs. neural network, and which specific scikit-learn class).**
   - What we know: D-01 requires this be decided empirically, on the real assembled data, with no default lean. `scikit-learn` offers both `HistGradientBoostingRegressor` (regression) and `MLPRegressor` (neural network) from one dependency.
   - What's unclear: Which will actually win the bake-off on this project's real per-corridor data — cannot be known before that data is assembled.
   - Recommendation: Run the bake-off described in this document's Summary/Pattern 4 at plan/execution time; document the losing candidate's score alongside the winner's in the FCST-02 validation record (D-06), not just the winner in isolation, so the "no default lean" mandate is demonstrably honored.

2. **Backfill window length (years of Open-Meteo history to pull per city).**
   - What we know: Open-Meteo Archive API reaches back to 1940; more data generally helps a tree/NN model but isn't free (fetch time, offline fit time, possible climate-pattern drift in very old data).
   - What's unclear: No specific volume was decided in CONTEXT.md (Claude's Discretion: "exact feature engineering details... lag window size").
   - Recommendation: Start with a 2-5 year window per city as a practical default (Assumption A3); document the chosen value and rationale in the FCST-02 validation record.

3. **Whether the offline bake-off's walk-forward should use fold-based `TimeSeriesSplit` or the fixed-model-then-walk approach (Pattern 4) for computing OOS residuals feeding the confidence band.**
   - What we know: Both preserve the "train strictly precedes test" guarantee `backtest_residuals` exists to protect; the fixed-model approach is cheaper and is what's recommended for the *runtime* band (since it requires no retraining at call time).
   - What's unclear: Whether the offline bake-off itself (choosing between candidate estimators) should use multiple `TimeSeriesSplit` folds for a more robust comparison, versus a single train/validation split.
   - Recommendation: Use `TimeSeriesSplit` with a small number of folds (e.g. 5) for the offline bake-off comparison (more robust estimator selection), then fit the winner once on the full available training window and use the fixed-model-then-walk approach (Pattern 4) for the runtime/backtest_residuals-integrated band.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| Python 3.12 (`.venv`) | All backend code | ✓ [VERIFIED: `.venv/bin/python3 --version`, this session] | 3.12.13 | — |
| pandas | Feature engineering, frame assembly | ✓ [VERIFIED: `.venv` pip list, this session] | 2.3.3 | — |
| numpy | `ieee738_ampacity`, array math | ✓ [VERIFIED: `.venv` pip list, this session] | 2.4.3 | — |
| scipy | Auxiliary stats | ✓ [VERIFIED: `.venv` pip list, this session] | 1.17.1 | — |
| pytest | Test running | ✓ [VERIFIED: `.venv` pip list, `pytest.ini` present, this session] | 9.0.3 | — |
| scikit-learn | New Tier-2 model, bake-off, `TimeSeriesSplit`, `joblib` | ✗ [VERIFIED: `.venv/bin/python3 -c "import sklearn"` raised `ModuleNotFoundError`, this session] | — (1.9.1 latest on PyPI, registry-verified this session) | None viable — this is the phase's one required new dependency; install per Package Legitimacy Audit (no blocking checkpoint per D-02) |
| Network access to Open-Meteo Archive API | Offline backfill assembly | Not directly tested this session (no live HTTP call made) — the endpoint is documented as public/unauthenticated [VERIFIED: `backend/open_meteo_provider.py:17`, "The endpoint is public and unauthenticated -- this module needs no token and no API key"] | — | If the live endpoint is unreachable at execution time, no viable fallback for *real* data exists (synthetic data is explicitly out of scope per FCST-02) — this should be confirmed with a live smoke-test call early in execution, not assumed |
| `data/historical/ampacity_history.csv` (live archive) | NOT required this phase | ✗ confirmed absent [VERIFIED: `ls data/historical/` this session shows no CSV, only `data/fixtures/`, `data/wtm_stations_austin.csv`, `data/wtm_stations.csv`] | — | Not needed — ROADMAP.md's Overview already establishes Open-Meteo backfill as the real-data source, independent of Track 1's archive accrual timeline |

**Missing dependencies with no fallback:** `scikit-learn` (must be installed — see Standard Stack/Package Legitimacy Audit for the pre-cleared installation path).
**Missing dependencies with fallback:** none beyond the above — this phase does not depend on the live historical archive at all.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 [VERIFIED: `.venv` pip list, this session] |
| Config file | `pytest.ini` [VERIFIED: read this session — `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`] |
| Quick run command | `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py` |
| Full suite command | `.venv/bin/python3 -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|-------------|
| FCST-01 | `FORECAST_METHODS` includes the new method value | unit | `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py -k new_method_in_forecast_methods` | ❌ Wave 0 |
| FCST-01 | `forecast_ampacity(history, method=<new>)` returns a `ForecastResult` populating the same 4 `PIPELINE_SCHEMA` columns | unit | `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py -k forecast_columns` | ⚠️ existing generic test exists (`test_forecast_columns_keys_all_exist_in_pipeline_schema`), needs parametrization to cover the new method |
| FCST-01 | Point forecast comes from an actual fitted model object (not last-value/EWM) | unit | `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py -k ml_method_uses_fitted_model` | ❌ Wave 0 |
| FCST-01 | Multivariate features (weather + lagged `dlr_amps`) actually influence the prediction (not autoregressive-only) | unit | `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py -k ml_method_sensitive_to_weather` | ❌ Wave 0 |
| FCST-01 | Per-corridor model selection reads `history["corridor"]` correctly; mismatched/missing artifact raises a clear error | unit | `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py -k corridor_model_selection` | ❌ Wave 0 |
| FCST-02 | Confidence band for the new method comes from `backtest_residuals` (or its extended path), same shape/ordering guarantees as naive/EWM | unit | `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py -k band_contains_point_forecast` (extend existing parametrized test to include the new method) | ⚠️ existing test parametrizes over `FORECAST_METHODS` already — will auto-cover the new method once it's added to the tuple |
| FCST-02 | Feature/target time relationship never leaks future weather into the feature set (Pitfall 4) | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_training_test.py -k no_future_leakage` | ❌ Wave 0 |
| FCST-02 | Real-data (Open-Meteo-backfill-derived) model accuracy measured and compared against naive/EWM on the same data | integration / manual-only | Not a `pytest -x`-shaped assertion — this is the offline bake-off script's own output, captured in `docs/data-science/decisions/forecasting_model.md` (D-06); a smoke-test-level pytest can assert the script runs end-to-end against a small real date range and produces a non-empty comparison table | ❌ Wave 0 |
| FCST-02 | Corridor-level weakest-link `min()` target/feature derivation matches the existing convention | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_training_test.py -k weakest_link_min_matches_convention` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** targeted new test file(s) (`.venv/bin/python3 -m pytest -q backend/tests/<file>.py`)
- **Per wave merge:** `.venv/bin/python3 -m pytest -q` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`; the offline bake-off script's actual run against real Open-Meteo data (not mocked) should be executed at least once and its output captured in the D-06 validation record before the phase is considered done — this is the one FCST-02 check that is inherently not a fast, mocked unit test.

### Wave 0 Gaps
- [ ] `backend/tests/ampacity_forecast_test.py` — new tests for the "ml" (or chosen name) method path, using a fixture-injected fake/small fitted model (no real joblib I/O or network calls in unit tests — mirrors `open_meteo_provider_test.py`'s existing mocked-HTTP convention for network isolation)
- [ ] `backend/tests/forecast_training_test.py` — new file covering feature engineering, the weakest-link `min()` reduction, and the no-future-leakage invariant, using synthetic (not live-network) weather fixtures
- [ ] A live-network smoke test (manual or a separately-marked slow/integration test) that actually calls `open_meteo_provider.fetch_open_meteo` for a short real range and feeds it through the full offline pipeline once, since FCST-02 explicitly requires validation against **real**, non-synthetic data
- [ ] Framework install: `.venv/bin/pip install scikit-learn` (Package Legitimacy Audit — no blocking checkpoint per D-02)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V2 Authentication | no | No auth layer exists yet in this subsystem; Open-Meteo's Archive API is public/unauthenticated [VERIFIED: `backend/open_meteo_provider.py:17`] |
| V3 Session Management | no | Same as above |
| V4 Access Control | no | Same as above |
| V5 Input Validation | yes | `PIPELINE_SCHEMA` + `validate_pipeline_row` (`backend/units_def.py`) already validates weather/`dlr_amps` ranges; the offline-assembled training frame should be validated the same way before it's used to fit a model, exactly mirroring `historical_archive.read_history`'s existing "validate before training" convention |
| V6 Cryptography | no | No new secrets/crypto surface — Open-Meteo needs no token |
| (New this phase) Deserialization of persisted model artifacts | yes | `joblib`/`pickle`-based deserialization executes arbitrary code on load [CITED: scikit-learn "Model persistence" docs, explicit security note: "should only be used if the artifact is trusted"]. This is a genuinely new threat surface relative to the naive/EWM era (which persists nothing) — only ever load a `.joblib` file this repo's own training script produced; never load a model artifact sourced from outside the repo or from user input |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Training-data poisoning (a corrupted or malformed Open-Meteo/derived row silently skews the fitted model) | Tampering | Validate every row of the offline-assembled training frame against `units_def.validate_pipeline_row` before fitting, mirroring `historical_archive.read_history`'s existing validate-before-training convention |
| Model-artifact tampering (a `.joblib` file on disk is replaced with a malicious pickle payload) | Tampering | Only load artifacts produced by this repo's own training script at a path under this repo's own `data/models/` (git-ignored, but locally trusted); never accept a model path from external/user input |
| Future-weather leakage silently making the backtest look better than real deployment accuracy | Tampering (of the evaluation result's integrity) | Explicit feature/target time-relationship test (Pitfall 4) — this is a correctness threat to the FCST-02 validation record's own trustworthiness, not just a modeling nicety |

## Sources

### Primary (HIGH confidence — read directly this session)
- `backend/ampacity_forecast.py` (read in full) — `FORECAST_METHODS`, `ForecastResult`, `_extract_series`, `_point_forecast`, `backtest_residuals`, `forecast_ampacity`, `forecast_columns`
- `backend/historical_archive.py` (read in full) — `ARCHIVE_COLUMNS`, `build_archive_row`, `append_observation`, `read_history`
- `backend/thermal_model.py` (read in full) — `ieee738_ampacity`, `perpendicular_wind`, `ConductorConfig`
- `backend/open_meteo_provider.py` (read in full) — `fetch_open_meteo`, `HOURLY_TO_PIPELINE`, rate/auth characteristics
- `backend/config.py` (read in full) — `STATIC_RATINGS`, `RATING_BOUNDS_BY_LOCATION`, `CORRIDOR_ENDPOINTS`, `CITY_COORDINATES`, `FORECAST_*` constants
- `backend/units_def.py` (read in full) — `PIPELINE_SCHEMA`, `validate_pipeline_row`
- `backend/corridor_discretization.py:470-680` (read this session) — `rate_corridor`, `_archive_corridor_result`, weakest-link `min()` reduction
- `backend/DLRSafetyMonitor.py:1-40` (read this session) — `solar_altitude_deg` default, constructor injection pattern
- `backend/tests/ampacity_forecast_test.py` (read in full) — existing test conventions, fixture shape
- `requirements.txt` (read in full) — explicit comment on scikit-learn/statsmodels' deliberate absence and the D-10/checkpoint condition D-02 now waives
- `.planning/milestones/v1.0-phases/04-predictive/04-RESEARCH.md` (read in full) — prior Tier-1/Tier-2 research, Package Legitimacy Audit precedent this session's audit reproduces
- `.planning/workstreams/ml-modeling/phases/01-forecasting-model/01-CONTEXT.md`, `REQUIREMENTS.md`, `STATE.md`, `ROADMAP.md` (read in full)
- `docs/data-science/specs/C9-ampacity-forecasting.md`, `docs/data-science/decisions/data_provider.md`, `docs/data-science/decisions/geographic_scope.md` (read in full) — stale-spec content D-07 corrects, ADR format precedent for D-06
- `.venv/bin/python3 --version` / `.venv/bin/python3 -m pip list` / `.venv/bin/python3 -c "import sklearn"` / `.venv/bin/python3 -m pip index versions scikit-learn|statsmodels|xgboost` (all run this session, against the project's actual `.venv`, not system Python)
- `gsd_run query package-legitimacy check --ecosystem pypi scikit-learn statsmodels xgboost` (run this session)

### Secondary (MEDIUM confidence — WebSearch cross-checked against official docs)
- scikit-learn `TimeSeriesSplit` official docs (scikit-learn.org) — expanding-window CV semantics
- scikit-learn "Model persistence" official docs (scikit-learn.org) — `joblib` recommendation, security note
- MachineLearningMastery "How To Backtest Machine Learning Models for Time Series Forecasting" — walk-forward validation cost tradeoffs

### Tertiary (LOW confidence — general WebSearch, not independently verified against a live call)
- Open-Meteo Archive API date-range/rate-limit characteristics (Assumption A5) — should be confirmed with an actual live smoke-test call early in execution rather than trusted as-is

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `scikit-learn`/`statsmodels`/`xgboost` versions and absence confirmed directly in the project's own `.venv` and the real PyPI registry this session, not a training-data guess.
- Architecture (signature-extension + per-corridor-key patterns): MEDIUM — grounded in verbatim-quoted existing code this session, but the extension itself is a recommendation, not yet-existing code; the planner should confirm the exact shape at plan time.
- Pitfalls: HIGH for the carried-over `ieee738_ampacity` float-wrap and schema pitfalls (previously proven in this exact codebase); MEDIUM for the leakage/retraining-cost pitfalls (general ML-engineering knowledge cross-checked via WebSearch, not this codebase's own prior incident).
- Package legitimacy: HIGH — verdicts reproduced live this session via the actual legitimacy seam, matching the prior phase's own independently-run audit.

**Research date:** 2026-09-24
**Valid until:** 30 days (stable domain — scikit-learn API surface and this codebase's existing contracts are both slow-moving; re-verify package versions if execution starts materially later)
