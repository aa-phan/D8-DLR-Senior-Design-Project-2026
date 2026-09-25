# Roadmap: ML Model Development (v1.3)

## Overview

This workstream (Track 2 of `docs/data-science/DEVELOPMENT-TRACKS.md`) replaces the two
components that satisfy C9/C10's naming and test contracts but are not actually ML —
`ampacity_forecast.py` (naive last-value + EWM statistical methods) and `anomaly_detector.py`
(a rolling `mean ± k*std` threshold) — with real trained models, dropped in behind each
module's existing public interface so neither Track 1 (Pipeline Integration) nor
`DLRSafetyMonitor`'s G6 gate wiring has to change. The two models are independent components
with no shared code path other than both being consumed by `DLRSafetyMonitor`, so the journey
is two parallel-safe, per-model phases rather than a design-then-validate split across all four
requirements: Phase 1 builds and validates the forecasting model (FCST-01, FCST-02), Phase 2
builds and validates the anomaly-detection model (ANOM-01, ANOM-02). Neither phase depends on
the other to start.

This is a fresh, independent workstream — phase numbering starts at 1 and does not continue any
other workstream's phase numbering.

**Interface contracts this workstream must preserve (owned by Track 1 and the standing
fail-safe commitment, not renegotiable here):**

- `ampacity_forecast.py::forecast_ampacity(history, horizon_min, method="naive", ...)` — the new
  method must be an additional value in `FORECAST_METHODS` (currently `("naive", "ewm")`), not a
  signature change, and must still return a `ForecastResult` populating the same four
  `PIPELINE_SCHEMA` columns via `forecast_columns()`.
- `anomaly_detector.py::AnomalyDetector.check(raw_data, rating) -> (bool, str)` — the new model
  must plug into this exact call shape, since `DLRSafetyMonitor` calls `.check(...)` directly and
  wraps it in `except Exception` to resolve to the static rating (G6) on any failure. That
  fail-safe resolution must keep holding under a trained model's failure mode, not just a
  heuristic's degenerate-std guard.

**Real training/validation data is less scarce than the live archive alone suggests.** The
`historical_archive.py` CSV (`config.HISTORICAL_ARCHIVE_PATH`) that Track 1 wires the pipeline
to accrue is empty today — Track 1's own phases haven't executed yet. But real (non-synthetic)
historical weather already exists independent of that: Open-Meteo's Archive API
(`open_meteo_provider.py`, WX-04, already shipped) reaches back to 1940 for all four cities, and
`ercot_data_retriever.py::pull_ercot_data` already pulls a real historical ERCOT load archive.
Both phases below can assemble a real (weather/load-driven, thermal-model-derived) training and
validation series from these existing sources rather than blocking on Track 1's live archive
accruing for weeks — see each phase's success criteria for how "real historical data" is defined
for that model.

**A new ML dependency (e.g., scikit-learn) is likely needed** for FCST-01/ANOM-01 and is not
yet part of this project's Python 3.12 stack (pandas/numpy/scipy only, per `PROJECT.md`
Constraints). This roadmap does not resolve that here — per this project's established
package-legitimacy audit precedent (`09-RESEARCH.md`), expect a legitimacy-review checkpoint
during phase planning/execution before any new dependency is added.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Forecasting Model** - Replace/extend `ampacity_forecast.py`'s naive/EWM methods with a trained regression or neural-network model, validated against real historical data (completed 2026-09-24)
- [ ] **Phase 2: Anomaly Detection Model** - Replace/augment `anomaly_detector.py`'s mean±k·std threshold with a trained model on historical per-variable baselines, validated against real historical data

## Phase Details

### Phase 1: Forecasting Model

**Goal**: `ampacity_forecast.forecast_ampacity` can produce an ampacity forecast from an actual
trained model — not just the last observed value or an exponentially-weighted average — and
that model's accuracy is proven against real historical data rather than assumed.
**Depends on**: Nothing (first phase in this workstream; independent of Phase 2)
**Requirements**: FCST-01, FCST-02
**Success Criteria** (what must be TRUE):

  1. `ampacity_forecast.FORECAST_METHODS` includes a new ML-backed method value alongside
     `"naive"` and `"ewm"`, and `forecast_ampacity(history, horizon_min, method=<new-method>)`
     returns a `ForecastResult` populating the same four `PIPELINE_SCHEMA` columns
     (`forecast_horizon_min`, `forecast_amps`, `forecast_ci_lower_amps`,
     `forecast_ci_upper_amps`) Track 1's caller already consumes — no signature or schema break.
  2. The new method's point forecast is produced by an actual fitted regression or
     neural-network model object, not a last-value read or an EWM smoothing calculation.
  3. The model is trained and evaluated against real historical data — historical weather
     (Open-Meteo backfill, reaching back well before this project started) run through the
     existing `thermal_model.ieee738_ampacity` to derive a real, non-synthetic `dlr_amps`
     series — using the existing out-of-sample walk-forward backtest machinery
     (`backtest_residuals`) so the confidence band stays apples-to-apples with the naive/EWM
     methods, not a parallel band implementation.
  4. A written validation record documents the new method's measured out-of-sample accuracy on
     real data, compared directly against the naive/EWM baselines on the same data, and states
     whether the model met expectations — per FCST-02, not just eyeballed once and discarded.
**Plans**: 3/3 plans executed
**Wave 1**

- [x] 01-01-PLAN.md — Tracer: one real end-to-end ML ampacity forecast (scikit-learn pinned, `backend/forecast_training.py` assembling Open-Meteo→IEEE 738 per-corridor data, `method="ml"` returning the same four `PIPELINE_SCHEMA` columns) plus the model-honesty invariants

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — D-01 bake-off: regression vs. neural-network candidate scored against each other and against naive/EWM on the identical series via `TimeSeriesSplit`, winner persisted per corridor, both corridors trained and provably served independently

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — FCST-02 validation record (`docs/data-science/decisions/forecasting_model.md`) written from the real full-window run, and the stale `C9-ampacity-forecasting.md` spec corrected (D-07)

### Phase 2: Anomaly Detection Model

**Goal**: The G6 safety gate can be backed by an actual model trained on historical
per-variable baselines (wind, temp, solar, load) instead of only the rolling mean±k·std /
forecast-residual heuristics, with the fail-safe contract intact, and that model's
false-positive/false-negative behavior is proven against real historical data.
**Depends on**: Nothing new (independent of Phase 1 — a separate model with no shared code
path other than both being consumed by `DLRSafetyMonitor`; may be executed in parallel)
**Requirements**: ANOM-01, ANOM-02
**Success Criteria** (what must be TRUE):

  1. `AnomalyDetector.check(raw_data, rating)` — however the detector is constructed (base
     constructor or `AnomalyDetector.for_corridor`) — still returns the same
     `(is_anomalous: bool, reason: str)` tuple shape, so `DLRSafetyMonitor`'s G6 call site and
     its `except Exception -> _fallback` wiring require zero changes.
  2. At least one of the detector's decision paths is backed by an actual model trained on
     historical per-variable baselines (wind, temp, solar, load) — not only the rolling
     mean±k·std threshold or the forecast-residual comparison already in place.
  3. A trained-model failure (an exception raised inside the new path) still resolves to the
     corridor's static rating via G6's existing exception handling in
     `DLRSafetyMonitor._fallback` — the fail-safe contract holds under a model failure exactly
     as it does today under the existing degenerate-std guard.
  4. The trained model is evaluated against real historical data — historical weather
     (Open-Meteo backfill) and historical ERCOT load (`ercot_data_retriever.pull_ercot_data`),
     not `_synthetic_history` fixtures — for false-positive/false-negative trip rate, compared
     against the existing mean±k·std baseline's trip rate on the same data.
  5. A written validation record documents that false-positive/false-negative measurement and
     states whether the model met expectations — per ANOM-02.
**Plans**: 4 plans

**Wave 1**

- [ ] 02-01-PLAN.md — Tracer: one real end-to-end trained-model anomaly check (`ANOMALY_ML_*`
  config, `backend/anomaly_training.py` assembling pooled Open-Meteo readings per corridor,
  an additive `_check_against_model` branch OR-combined into `check()` per D-05/D-06) plus the
  fail-safe and no-substitution invariants

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 02-02-PLAN.md — ANOM-02 measurement + D-03 bake-off: false-positive rate on a
  strictly-later real holdout and per-category recall on injected corruption, for all three
  scikit-learn candidates across a contamination grid and for the existing mean±k·std baseline
  on identical rows; each corridor's measured winner persisted

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 02-03-PLAN.md — D-02 load half of ANOM-01: per-corridor ERCOT zone load characterized at
  training time only (`pull_ercot_data` made usable in process, per-calendar-year loop, correct
  zone mapping per corridor) plus the boundary test keeping load out of `check()`

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 02-04-PLAN.md — ANOM-02 validation record (`docs/data-science/decisions/anomaly_detection_model.md`)
  written from the real measurement runs per D-07's honesty standard, and the stale
  `C10-anomaly-detection.md` spec corrected

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 (though Phase 2 has no technical dependency on Phase 1
and may be executed first or in parallel if that better fits available capacity)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Forecasting Model | 3/3 | Complete    | 2026-09-24 |
| 2. Anomaly Detection Model | 0/4 | Planned | - |

## Backlog

### Phase 999.1: Revisit ml forecast method accuracy vs naive baseline (BACKLOG)

**Goal:** [Captured for future planning]
**Requirements:** TBD
**Plans:** 0 plans

Context: Phase 1's bake-off (Plans 01-02/01-03) found both trained candidates
(`HistGradientBoostingRegressor`, `MLPRegressor`) lost to the naive last-value baseline on
held-out MAE, for both corridors, at the current 60-minute forecast horizon — see
`docs/data-science/decisions/forecasting_model.md` and
`.planning/workstreams/ml-modeling/phases/01-forecasting-model/01-VERIFICATION.md`. Not
blocking: the live/current DLR rating is computed independently via real-time IEEE 738
physics and never calls the naive/ewm/ml forecast; `"ml"` is an opt-in, not-yet-wired-in
feature. Follow-up candidates to try before deciding whether `"ml"` should become the
recommended forecast method: a longer forecast horizon (naive degrades faster than ML as
horizon grows, giving ML more room to add value), a longer/richer training window (more
than the current 3 years), and/or additional features.

Plans:
- [ ] TBD (promote with /gsd-review-backlog when ready)
