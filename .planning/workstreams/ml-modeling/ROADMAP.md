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
- [x] **Phase 2: Anomaly Detection Model** - Replace/augment `anomaly_detector.py`'s mean±k·std threshold with a trained model on historical per-variable baselines, validated against real historical data (completed 2026-09-28)
- [ ] **Phase 3: Ampacity Forecast Correction Experiment** - Determine what should replace the current lagged-ampacity `"ml"` method: compare persistence, raw-forecast-through-IEEE-738, ML-corrected-wind, and ML-corrected-cooling approaches (plus an oracle diagnostic) against a real, empirically lead-time-calibrated weather forecast archive on a fixed chronological train/val/test split (supersedes backlog Phase 999.1)

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
**Plans**: 5/5 plans complete (4 build/validation plans + 1 gap closure)

**Wave 1**

- [x] 02-01-PLAN.md — Tracer: one real end-to-end trained-model anomaly check (`ANOMALY_ML_*`
  config, `backend/anomaly_training.py` assembling pooled Open-Meteo readings per corridor,
  an additive `_check_against_model` branch OR-combined into `check()` per D-05/D-06) plus the
  fail-safe and no-substitution invariants

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — ANOM-02 measurement + D-03 bake-off: false-positive rate on a
  strictly-later real holdout and per-category recall on injected corruption, for all three
  scikit-learn candidates across a contamination grid and for the existing mean±k·std baseline
  on identical rows; each corridor's measured winner persisted

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-03-PLAN.md — D-02 load half of ANOM-01: per-corridor ERCOT zone load characterized at
  training time only (`pull_ercot_data` made usable in process, per-calendar-year loop, correct
  zone mapping per corridor) plus the boundary test keeping load out of `check()`

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 02-04-PLAN.md — ANOM-02 validation record (`docs/data-science/decisions/anomaly_detection_model.md`)
  written from the real measurement runs per D-07's honesty standard, and the stale
  `C10-anomaly-detection.md` spec corrected

**Wave 5** *(gap closure — blocked on Wave 4 completion)*

- [x] 02-05-PLAN.md — Close 02-VERIFICATION.md's single failed must-have (P8 / 02-REVIEW.md CR-01):
  `anomaly_training.py`'s three corridor-scopable report writers overwrite
  `anomaly_validation_report.json` with a corridor-scoped subset, silently deleting the other
  corridor's measurement history; replaced by one load-merge-atomic-write helper with entry-level
  provenance so a shortened run is visible in the evidence rather than erasing it (restores T-02-09)

### Phase 3: Ampacity Forecast Correction Experiment

**Goal**: Determine, on real evidence rather than assumption, what should replace the current
lagged-ampacity `"ml"` forecasting method — a reproducible experiment comparing persistence,
a raw-forecast-through-IEEE-738 approach, an NWP-wind-delta baseline, two ML-correction
approaches (wind-only via u/v decomposition; convective-heat-loss-term), the current `"ml"`
model refit for a fair comparison, and a non-forecast oracle diagnostic that bounds the maximum
benefit wind correction could capture.
**Depends on**: Nothing new (independent of Phase 1/2 — this is Phase 1's own forecasting method
under revisit, not a new model class; supersedes backlog Phase 999.1, which found both trained
candidates lost to naive persistence at the 60-minute horizon — see
`docs/data-science/decisions/forecasting_model.md`)
**Requirements**: No FCST/ANOM requirement ID — D-04 reconfirmed this remains a methodology
investigation of FCST-01/FCST-02's existing "ml" method, not new project scope.
**Success Criteria** (what must be TRUE):

  1. A forecast archive with a genuinely measured (never vendor-assumed) lead time backs the
     phase's primary comparison. **Executed as, per D-04 — a decision made before any test-set
     result was seen, following Wave 1's discovery that the originally-scoped 1-hour Historical
     Forecast archive was bit-identical to truth for the necessarily-recent calibration window,
     not following the eventual test-set outcome:** Open-Meteo's **Previous Runs API** is the
     primary 24-hour-lead forecast source, with its `24 + (hour % 6)`-hour effective lead measured
     (not trusted from Open-Meteo's own "exact by construction" documentation) against the
     Single-Runs API, and every scored row filtered to the verified exact-24h-lead subset
     (`hour % 6 == 0`). The originally-scoped 1-hour Historical Forecast arm (Wave 1, its own
     measured lead-time calibration gate against Single-Runs) is demoted to a labelled, non-primary
     curiosity — see `forecast_correction_experiment.md`'s Legacy 1-Hour Arm section.
     **Disposition: MET, as amended by D-04** — Plan 03-03 (the 24-hour offset-lead gate) and
     `forecast_correction_experiment.md`.
  2. All seven approaches (persistence, NWP-wind-delta, raw-forecast, ML-wind-correction,
     ML-cooling-correction, refit reference `"ml"`, oracle) are scored on identical held-out
     chronological test timestamps — a fixed calendar train/val/test split, not the existing
     walk-forward-only evaluation machinery — with the oracle labeled as non-forecast in every
     output surface.
     **Disposition: MET** — Plan 03-06 scored all seven arms on one byte-identical held-out
     test-timestamp index per corridor; the oracle is structurally isolated out of the candidate
     mapping (Plan 03-04), never merely labelled.
  3. No approach's prediction or regime label can be shown to depend on any post-issue-time
     information (a leakage test suite proves this directly, not just by construction).
     **Disposition: MET** — Plan 03-06's leakage probe demonstrated power against a deliberately
     sabotaged arm; the probe's own coverage gap (a model trained on test rows, rather than a
     direct read of a truth column) is closed instead by arm 5's from-scratch train+validation-only
     refit and the filtered-frame split-disjointness assertion (Plan 03-04) — see
     `forecast_correction_experiment.md`'s Limitations.
  4. `backend/thermal_model.py::ieee738_ampacity` and `backend/anomaly_detector.py` are
     unchanged in observable behavior (any refactor — e.g. exposing a substitutable convective
     term — is proven behavior-identical via an equality test against the pre-refactor output).
     **Disposition: MET** — the convective-term extraction (Plan 03-02) is proven bit-identical via
     an exact-equality (`np.array_equal`) golden-fixture gate; `anomaly_detector.py` carried zero
     diff after every plan in this phase.
  5. A written decision record (`docs/data-science/decisions/forecast_correction_experiment.md`,
     matching the existing 9-section structure) states which approach wins on the held-out test
     set, or states plainly that none beat persistence — with the Expectation section committed
     before the test-set run, per this workstream's existing no-peeking discipline.
     **Disposition: MET** — the Expectation section was committed in the same isolated commit
     (`4d964cf`) that unlocked the held-out test split (Plan 03-06); the Verdict (Plan 03-07) states
     `ml_cooling_corrected` wins distinguishably at both corridors, read against that unedited
     Expectation.
**Plans**: 7 plans across 5 waves — all complete. Wave 1's originally-scoped Waves 2-5 (designed
around a 1-hour idealized lead) were redesigned around D-04's pivot to a 24-hour realizable lead
after Wave 1 discovered the 1-hour data source was bit-identical to truth for the necessarily-recent
calibration window; the redesigned Waves 2-5 (Plans 03-03 through 03-07) are the waves documented
below. The 1-hour arm's already-committed code is retained as a documented, non-primary curiosity
per D-04's disposition.

**Wave 1**

- [x] 03-01-PLAN.md — Tracer: forecast-archive provider, the hard lead-time calibration gate, the
  three-way calendar split, and a first scored slice (persistence vs. raw-forecast-through-IEEE-738)
  — completed after two live window corrections and the discovery of D-04's bit-identity finding,
  which the plan surfaced honestly rather than hiding
- [x] 03-02-PLAN.md — Building blocks: `wind_vector` u/v decomposition, the additive `thermal_model`
  convective-term extraction plus `q_conv_override` (bit-exact via `np.array_equal`), and the
  `corridor_weakest_link` extraction — all lead-time-agnostic and fully reused by the redesigned waves

**Wave 2** *(redesigned around D-04)*

- [x] 03-03-PLAN.md — Delivered the 24-hour realizable lead end-to-end: `fetch_previous_runs` under
  its own `gfs_seamless` pin, the measured `24 + (hour % 6)` offset-lead verification correcting
  D-04's own "no gate needed" framing, the `lead_hours`-generalized anchored-pair contract with a
  lead-aware cache key, and a live validation-split score proving the forecast is no longer
  bit-identical to truth

**Wave 3** *(two plans run in parallel — disjoint file ownership)*

- [x] 03-04-PLAN.md — Delivered the four non-fitted arms (24-hour persistence, NWP-wind-delta, raw
  forecast, oracle) in one registry, promoted to corridor level via `corridor_weakest_link`, with the
  oracle structurally outside the candidate mapping rather than merely labelled
- [x] 03-05-PLAN.md — Delivered the two ML correction families as standalone units: u/v wind
  correction (both pooling strategies) and convective-term correction through `q_conv_override`
  (both target parameterizations), selected on the validation set; plus the additive
  `horizon_minutes` parameter giving arm 5 a 24-hour target without mutating a global constant

**Wave 4**

- [x] 03-06-PLAN.md — Delivered the Expectation committed before any test row was read, a leakage
  probe with demonstrated power, and the single seven-arm held-out test-set run with paired
  bootstrap confidence intervals on every margin against persistence

**Wave 5**

- [x] 03-07-PLAN.md — Delivered the completed 9-section decision record: the primary 24-hour verdict
  read against the unedited Expectation, the legacy 1-hour arm as a labelled curiosity with its
  bit-identity caveat, honest limitations, and the phase's closing records

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 (though Phase 2 has no technical dependency on Phase 1
and may be executed first or in parallel if that better fits available capacity)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Forecasting Model | 3/3 | Complete    | 2026-09-24 |
| 2. Anomaly Detection Model | 5/5 | Complete   | 2026-09-28 |
| 3. Ampacity Forecast Correction Experiment | 7/7 | Complete | 2026-09-30 |

## Backlog

*(none — Phase 999.1 promoted to Phase 3 above, 2026-09-28)*
