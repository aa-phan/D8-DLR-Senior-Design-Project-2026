---
phase: 01-forecasting-model
plan: 02
subsystem: ml-forecasting
tags: [scikit-learn, timeseriessplit, histgradientboosting, mlpregressor, bakeoff, ampacity-forecast]

# Dependency graph
requires:
  - phase: 01-01
    provides: "ml" method scaffold (build_ml_features, _load_corridor_model, _MODEL_CACHE,
      _point_forecast/backtest_residuals history+model kwargs), forecast_training.py's
      corridor_training_frame/build_training_matrix/fit_corridor_model/persist_corridor_model
provides:
  - D-01's two-candidate bake-off (HistGradientBoostingRegressor vs MLPRegressor) scored
    against naive/ewm baselines on the identical real assembled matrix, via TimeSeriesSplit
  - Independently fitted and persisted per-corridor winners for both AUSTIN_CORPUS_CHRISTI
    and MIDLAND_EL_PASO, with cross-corridor bleed ruled out by test
  - A machine-readable bakeoff_report.json carrying all four candidate rows plus the
    window (row count, first/last timestamp) each score was measured on
  - "An honest, load-bearing negative result: on real 3-year data for both corridors, the
    naive last-value baseline beats both ML candidates on held-out MAE -- documented, not
    suppressed, per this plan's own transparency prohibitions"
affects: [01-03 (validation record must transcribe this bake-off result honestly, including
  the naive-wins finding, not just report a winner)]

# Actuals (#2632)
actuals:
  tokens: 44000
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TimeSeriesSplit as the only fold source for the bake-off -- no hand-rolled positional
      slicing loop, so train-strictly-precedes-test is a property of the primitive, not an
      assertion about custom code"
    - "MLPRegressor wrapped in make_pipeline(StandardScaler(), MLPRegressor(...)) so the
      neural-network arm isn't penalized by unscaled features spanning amps/degC/unit-interval"
    - "select_winner reads only the two ML candidates' measured mae -- naive/ewm are baselines
      in the same report, not eligible winners, so D-01's regression-vs-nn question and
      FCST-01's overall-vs-naive question stay analytically separate"

key-files:
  created: []
  modified:
    - backend/config.py
    - backend/forecast_training.py
    - backend/tests/forecast_training_test.py
    - backend/tests/ampacity_forecast_test.py
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "select_winner operates only over CANDIDATE_ESTIMATORS (the two ML arms) per the plan's
    explicit scope -- it does not compare against naive/ewm. The persisted 'winner' per
    corridor is therefore the better-of-two-ML-candidates, not proof the ML path beats naive."
  - "Full 3-year, both-corridor, both-candidate bake-off was actually run against the live
    Open-Meteo Archive API -- not shortened, not subsampled -- per this plan's first
    prohibition. Window: 2023-01-01 through 2025-12-31 (26304 assembled hourly rows per
    corridor before feature-engineering row loss)."
  - "Per-corridor cross-bleed isolation proven with two distinguishable fitted estimators
    (targets offset by a large constant) plus a real-cache test with joblib.load monkeypatched
    and _MODEL_CACHE cleared, exercising the actual cache rather than a stub's own bookkeeping."

patterns-established:
  - "Bake-off report shape: {corridor: {corridor, rows, window_start, window_end,
    feature_columns, horizon_min, candidates: {4 keys, each {mae, rmse, rows}}}} --
    Plan 03 transcribes this JSON (git-ignored) into the tracked ADR."

requirements-completed: [FCST-01, FCST-02]

coverage:
  - id: D1
    description: "Two-candidate bake-off (HistGradientBoostingRegressor + MLPRegressor)
      scored via TimeSeriesSplit, with naive/ewm scored on the identical series through
      the existing backtest_residuals -- four-row apples-to-apples comparison per corridor"
    requirement: "FCST-01"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_training_test.py -k 'bakeoff or select_winner or baseline or fold'"
        status: pass
      - kind: integration
        ref: ".venv/bin/python3 backend/forecast_training.py --bakeoff (live Open-Meteo run, both corridors)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Both corridors independently trained, persisted, and served with no
      cross-corridor model bleed"
    requirement: "FCST-01"
    verification:
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py -k 'corridor_isolation or corridor_model_cache or unknown_corridor'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Judgment on whether the winning ML candidate's margin over naive is a
      plausible forecasting improvement or shows the leakage signature (01-RESEARCH.md
      Pitfall 4) -- see Human-Check Judgment section below. Actual finding: naive WINS
      both corridors, which is the opposite of a leakage signature but is a substantive
      negative result FCST-02's validation record must carry forward honestly."
    verification: []
    human_judgment: true
    rationale: "01-RESEARCH.md Pitfall 4's near-zero/order-of-magnitude-better check is a
      leakage detector; this result (naive beats ML) doesn't trip that specific detector but
      is exactly the kind of number this plan's prohibitions require surfacing plainly rather
      than optimistically reframing as a 'win' via the two-ML-candidates-only select_winner."

duration: ~35min (agent execution) + orchestrator finalization after a stream stall during
  SUMMARY.md write-up (all task work and live verification completed before the stall)
completed: 2026-09-24
status: complete
---

# Phase 01, Plan 02: D-01 Estimator Bake-off Summary

**Both ML candidates were fitted and scored per D-01's mandate — and on this real 3-year window, both lose to the naive last-value baseline on held-out MAE, for both corridors.**

## Performance

- **Duration:** ~35 min of agent execution (three commits, plus the live two-corridor, two-candidate bake-off run against Open-Meteo) + orchestrator-completed finalization after the executor agent's process stalled during the final SUMMARY.md write step (no plan work was incomplete — see Deviations).
- **Tasks:** 2/2

## Accomplishments

### Task 1 — Two-candidate bake-off with naive/ewm baselines
- Added `backend/config.py::FORECAST_ML_BAKEOFF_SPLITS = 5` and `FORECAST_ML_BAKEOFF_REPORT_NAME = "bakeoff_report.json"`.
- Added `backend/forecast_training.py::CANDIDATE_ESTIMATORS` — exactly two factories: a `HistGradientBoostingRegressor` (fixed `random_state`) and `make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(32,16), max_iter=2000, random_state=fixed, early_stopping=False))`.
- Added `bakeoff_corridor(X, y)` — `TimeSeriesSplit(n_splits=5)`, fresh estimator per fold per candidate, pooled MAE/RMSE across all folds, held-out row count recorded.
- Added `baseline_scores(frame)` — `naive`/`ewm` scored via `ampacity_forecast.backtest_residuals` on the identical assembled series (not a second error implementation).
- Added `corridor_report(...)` merging both into one 4-candidate mapping plus `rows`/`window_start`/`window_end`/`feature_columns`/`horizon_min`.
- Added `select_winner(report)` — reads only the two ML candidates' `mae`, symmetric under reordering, raises `ValueError` on a missing/non-finite candidate. Tie-break: `rmse`, then declaration order, both stated in-report if fired (no tie occurred in the real run).
- Refactored `fit_corridor_model(X, y, estimator)` to take an unfitted estimator (was hardcoded); all existing call sites updated.
- Extended `main(argv=None)` with `--bakeoff`: assembles, scores, selects, refits the winner on the full matrix, persists it, writes the JSON report, and prints a 4-row comparison table + winner line per corridor.
- 183 new lines in `backend/tests/forecast_training_test.py`: bake-off shape, symmetric-selection (both MAE orderings), no-fold-overlap (asserted on `TimeSeriesSplit` indices directly, not inferred from a score), baseline-parity tests — all offline, synthetic, deterministic (`numpy.random.default_rng`), no network.

### Task 2 — Both corridors trained and independently served
- `main`'s no-`--corridor` default iterates every key in `config.CORRIDOR_ENDPOINTS`; a failure assembling one corridor is reported by name and the run continues to the next rather than aborting silently. Added a final per-corridor summary line (corridor, rows, window span, winner, persisted path).
- Verified `_MODEL_CACHE` in `backend/ampacity_forecast.py` was already correctly keyed per-corridor from Plan 01 (dict keyed by corridor string) — no fix needed, confirmed rather than assumed.
- Added 133 new lines to `backend/tests/ampacity_forecast_test.py`: per-corridor isolation test (two distinguishable fitted estimators — same features, targets offset by a large constant — called in both orders and one corridor called twice consecutively, all correctly routed); a real-cache test with `joblib.load` monkeypatched and `_MODEL_CACHE` cleared first, proving the cache itself (not a stub's bookkeeping) avoids a second disk read for an already-seen corridor; an unknown-corridor test proving `_corridor_of` raises (naming valid corridors) before any path is built.
- **Ran the real, full-window, two-corridor, two-candidate bake-off against the live Open-Meteo Archive API** (`--bakeoff`, no `--corridor` — both corridors in one invocation): 26304 assembled hourly rows per corridor, window 2023-01-01T00:00 through 2025-12-31T23:00 (the full configured `FORECAST_ML_TRAINING_YEARS=3`, not shortened). Produced `data/models/bakeoff_report.json`, `data/models/forecast_AUSTIN_CORPUS_CHRISTI.joblib`, `data/models/forecast_MIDLAND_EL_PASO.joblib` (all present, non-empty, `git status --porcelain data/models` empty).

## Bake-off Results (transcribe verbatim into Plan 03's validation record)

| Corridor | Candidate | MAE | RMSE | Held-out rows |
|---|---|---|---|---|
| AUSTIN_CORPUS_CHRISTI | HistGradientBoostingRegressor | 79.09 | 105.14 | 21910 |
| AUSTIN_CORPUS_CHRISTI | MLPRegressor | 77.70 | 103.79 | 21910 |
| AUSTIN_CORPUS_CHRISTI | naive | **67.17** | **97.95** | 26292 |
| AUSTIN_CORPUS_CHRISTI | ewm | 88.32 | 116.25 | 26292 |
| MIDLAND_EL_PASO | HistGradientBoostingRegressor | 90.13 | 117.09 | 21910 |
| MIDLAND_EL_PASO | MLPRegressor | 89.59 | 116.85 | 21910 |
| MIDLAND_EL_PASO | naive | **79.76** | **113.51** | 26292 |
| MIDLAND_EL_PASO | ewm | 99.65 | 129.87 | 26292 |

Per-corridor ML winner (by `select_winner`, comparing only the two ML candidates): **MLPRegressor** for both corridors (marginally lower MAE than HistGradientBoosting in both cases — Austin: 77.70 vs 79.09; Midland: 89.59 vs 90.13). MLPRegressor was the candidate refit on the full window and persisted for both corridors.

## Human-Check Judgment (Task 2 `<human-check>`, performed by the executing agent since no human was in the loop)

01-RESEARCH.md Pitfall 4 describes a **leakage** signature: an ML result implausibly close to zero error, or an order of magnitude better than naive, which would indicate the model is being fed weather from at-or-after the forecast target and is silently re-deriving physics rather than forecasting. **That signature is not present here** — no candidate's error is near-zero or anomalously tiny.

What *is* present, and must be stated plainly rather than glossed over: **naive beats both ML candidates on both corridors**, by a similar relative margin each time (naive's MAE is roughly 14-18% lower than the better ML candidate in both corridors). This is not evidence of a bug in the leakage-check sense — the no-future-leakage tests from Plan 01 (`no_future_leakage`, asserting `feature_timestamp < target_timestamp` for every row and mutation-invariance of earlier rows) still pass, and this bake-off's `TimeSeriesSplit` folds are independently verified to never let training data occur after test data. It is a legitimate measured outcome: at a 60-minute horizon, the most recent observed value is a strong predictor of dynamic line rating (weather changes relatively slowly hour-to-hour), and a naive last-value read is a genuinely hard baseline to beat at this horizon with the feature set and lag structure this phase built (lags of 1/2/3/6h, a 6h rolling mean, and instantaneous weather).

**This is a load-bearing negative result for FCST-01's premise as currently scoped**, not a defect in this plan's execution. Per this plan's own transparency prohibitions (do not select or report a winner in a way that obscures the measured numbers), Plan 03's validation record must carry this finding forward exactly as measured — including the fact that the fitted, persisted "ml" method does not currently outperform the naive method it was meant to replace at this forecast horizon on this real data. Whether that changes the project's recommendation (e.g., reconsidering the forecast horizon, feature set, or whether "ml" should be the recommended method at all) is a decision for Plan 03 / the project owner to make explicitly, not one this plan is scoped to resolve.

## Verification

- `.venv/bin/python3 -m pytest -q backend/tests/forecast_training_test.py -k "bakeoff or select_winner or baseline or fold"` — pass.
- `PYTHONPATH=backend .venv/bin/python3 -c "..."` selection-symmetry contract check — `SELECTION_OK` printed.
- `grep -q 'TimeSeriesSplit' backend/forecast_training.py && ...` — `BAKEOFF_WIRED_OK` printed.
- `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py -k "corridor_isolation or corridor_model_cache or unknown_corridor"` — pass.
- Live `--bakeoff` run + report-shape/window/artifact-distinctness check — `BOTH_CORRIDORS_OK ['AUSTIN_CORPUS_CHRISTI', 'MIDLAND_EL_PASO']` printed.
- `git status --porcelain data/models` — empty (`MODELS_IGNORED_OK`).
- Full suite: **409 passed, 0 failed** (up from Plan 01's 399-passed baseline; +10 new tests across both test files).

## Deviations from Plan

- **Process stall during finalization (Rule 1, environment — not a plan deviation).** The isolated executor agent's process stalled ("no progress for 600s") while writing this SUMMARY.md, after all three commits (tests, bake-off implementation, isolation implementation) and the full live verification chain had already completed successfully and were already committed to the worktree branch. The orchestrating session inspected the stalled worktree directly, confirmed `git log` showed all planned commits present, re-ran the full `pytest` suite (409 passed) and inspected `data/models/bakeoff_report.json` directly to independently confirm the live bake-off's actual numbers (not re-running the live fetch again), then completed this SUMMARY.md and the ACKNOWLEDGEMENTS.md entry the stalled agent had already drafted (found as an uncommitted change in the worktree) on its behalf. No task work, verification, or judgment call was redone or invented — this is a write-up completion, not a re-execution.

## Issues Encountered

- None in the implementation itself. The one substantive "issue" is the bake-off result described above (naive beats ML), which is a real measured finding, not a bug.

## Next Steps

- Plan 03 must write FCST-02's validation record transcribing these exact numbers, including the naive-wins finding, and correct `docs/data-science/specs/C9-ampacity-forecasting.md`. Plan 03 (or a follow-up decision) should explicitly address what the naive-wins finding means for whether `"ml"` is recommended as the production method at the current 60-minute horizon and feature set, rather than letting the persisted-and-shippable artifact imply a recommendation the measured evidence does not support.
