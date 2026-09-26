---
phase: 02-anomaly-detection-model
plan: 01
subsystem: ml-anomaly-detection
tags: [scikit-learn, isolation-forest, joblib, anomaly-detection, open-meteo]

# Dependency graph
requires:
  - phase: 01-forecasting-model
    provides: "forecast_training.fetch_city_weather (reused verbatim), persist_corridor_model atomic-write pattern, ampacity_forecast._model_path_for/_load_corridor_model lazy-loader pattern"
provides:
  - "AnomalyDetector's third, additive model branch (_check_against_model) judging raw wind/temp/solar readings against a fitted IsolationForest"
  - "anomaly_training.py: offline pooled-observation assembly, fit, atomic persistence, CLI"
  - "config.ANOMALY_ML_* tunables"
affects: [02-02-multi-candidate-bakeoff, 02-03-ercot-load-characterization, 02-04-validation-record]

# Actuals (#2632)
actuals:
  tokens: 12830
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive third branch in an existing OR-dispatch chain (mirrors Phase 1's naive/ewm/ml additive method pattern)"
    - "Offline train / atomic persist (tempfile + os.replace) / lazy-load-and-cache runtime pattern, second instance after forecast_training.py"
    - "Pooled (not weakest-link-reduced) per-corridor training frame for a per-variable envelope model"

key-files:
  created:
    - backend/anomaly_training.py
    - backend/tests/anomaly_training_test.py
  modified:
    - backend/config.py
    - backend/anomaly_detector.py
    - backend/tests/anomaly_detector_test.py

key-decisions:
  - "Model branch is additive and OR-combined per D-06 — check() restructured from early-return dispatch to accumulate-then-OR so the model branch runs alongside (never in place of) the forecast/rolling-baseline branch"
  - "Feature set is exactly air_temp/wind_speed/solar_radiation (D-01) — no hour-of-day/seasonal encoding, since raw_data carries no timestamp at the check() call site"
  - "One pooled model per corridor (both endpoint cities' readings concatenated, not reduced via min()) since raw_data carries no location identifier to key a per-city selector on"
  - "Absent artifact resolves to model=None with one logged warning (A-04) — differs from Phase 1's ml method, where an absent artifact raises, because this branch is additive and an unprovisioned model must leave behavior identical to today's two-branch detector"
  - "No exception handler exists anywhere in anomaly_detector.py — a broken model propagates uncaught to DLRSafetyMonitor's existing G6 fail-safe boundary (T-02-03)"

patterns-established:
  - "anomaly_training.py mirrors forecast_training.py's offline-assembly/persist/CLI shape exactly, the second instance of this codebase's train-offline/load-lazily convention"

requirements-completed: [ANOM-01]

coverage:
  - id: D1
    description: "AnomalyDetector.for_corridor loads a scikit-learn IsolationForest fitted offline on real Open-Meteo Archive weather, and check(raw_data, rating) returns a native (bool, str) whose model verdict participates via the additive branch"
    requirement: ANOM-01
    verification:
      - kind: unit
        ref: "backend/tests/anomaly_detector_test.py::test_model_branch_returns_two_tuple_of_bool_and_str"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_detector_test.py::test_model_clean_reading_inside_envelope"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_detector_test.py::test_model_trip_reading_far_outside_envelope"
        status: pass
      - kind: integration
        ref: ".venv/bin/python3 backend/anomaly_training.py --corridor AUSTIN_CORPUS_CHRISTI --years 1 (live Open-Meteo Archive API, E2E verify block)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The model branch is additive and one-directional: it can only add a trip on top of an existing branch's verdict, never suppress one (D-06)"
    requirement: ANOM-01
    verification:
      - kind: unit
        ref: "backend/tests/anomaly_detector_test.py::test_model_cannot_suppress_existing_trip"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_detector_test.py::test_model_can_trip_on_its_own"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_detector_test.py::test_both_branches_clean_returns_false_with_both_reasons"
        status: pass
    human_judgment: false
  - id: D3
    description: "A model failure (raising prediction entry point) still resolves through DLRSafetyMonitor's existing G6 handler to the corridor's static rating, and the exception propagates out of AnomalyDetector.check uncaught"
    requirement: ANOM-01
    verification:
      - kind: unit
        ref: "backend/tests/anomaly_detector_test.py::test_model_failure_resolves_to_static_rating"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_detector_test.py::test_model_exception_propagates_out_of_check"
        status: pass
    human_judgment: false
  - id: D4
    description: "A missing/None/non-finite raw wind/temp/solar value raises ValueError naming the offending field rather than substituting a default (T-02-04); a non-finite rating still skips the model branch"
    requirement: ANOM-01
    verification:
      - kind: unit
        ref: "backend/tests/anomaly_detector_test.py::test_missing_raw_field_raises_rather_than_substituting[...]"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_detector_test.py::test_non_finite_rating_still_skips_model_branch"
        status: pass
    human_judgment: false
  - id: D5
    description: "Offline training pools both endpoint cities' raw readings (not weakest-link reduction) and drops rows outside DLRSafetyMonitor's G3 bounds or carrying a null value without ever imputing (T-02-01)"
    requirement: ANOM-01
    verification:
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_corridor_observation_frame_pools_both_endpoint_cities"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_corridor_observation_frame_drops_out_of_bounds_and_null_rows_without_imputing"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_persist_round_trips_through_detector_loader"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-09-26
status: complete
---

# Phase 2 Plan 01: Trained-Model Anomaly Detection Branch Summary

**A fitted scikit-learn IsolationForest, trained offline on real pooled Open-Meteo weather for a corridor's two endpoint cities, now contributes a third, additive OR-combined verdict inside `AnomalyDetector.check(raw_data, rating)`, with zero change to the fail-safe contract.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-09-26T17:23:00-05:00 (approx.)
- **Completed:** 2026-09-26T17:33:00-05:00 (approx.)
- **Tasks:** 2 completed
- **Files modified:** 5 (2 new, 3 modified)

## Accomplishments

- `AnomalyDetector.for_corridor("AUSTIN_CORPUS_CHRISTI")` loads a real, fitted `IsolationForest` per corridor via a lazy, cached loader (`_load_corridor_model`/`_load_corridor_model_or_none`), and `check(raw_data, rating)` returns a native `(bool, str)` in which that model's verdict on the raw `wind`/`temp`/`solar` reading participates alongside the two existing heuristic branches.
- `backend/anomaly_training.py` (new): offline entry point that pools (never weakest-link-reduces) both endpoint cities' real Open-Meteo Archive backfill, drops rows outside `DLRSafetyMonitor`'s G3 physical bounds or carrying a null/non-finite value (logging aggregated warnings, never imputing), fits an `IsolationForest`, and persists it atomically (`tempfile` + `os.replace`) — mirroring `forecast_training.py`'s established pattern exactly.
- `check()` restructured from early-return-per-branch to accumulate-then-OR (D-06): the model branch can only ever add a trip on top of an existing branch's verdict, never suppress one — proven by dedicated tests for all four (existing-branch x model) verdict combinations.
- No exception handler exists anywhere in `anomaly_detector.py`: a broken model (raising prediction entry point, corrupt artifact, feature mismatch) propagates uncaught to `DLRSafetyMonitor.run_check`'s existing G6 `except Exception -> _fallback` boundary, resolving to the corridor's static rating exactly as today's two heuristic branches already do.
- A missing/`None`/non-finite raw `wind`/`temp`/`solar` value raises `ValueError` naming the offending field — never a substituted default — across all 9 parametrized (key x malformed-shape) combinations.
- Live E2E run against the real Open-Meteo Archive API: 17,520 pooled hourly rows (both endpoint cities, 2025 calendar year), persisted `.joblib` + observation CSV, `for_corridor` loads the artifact and `check()` returns a real verdict on a row read back from that CSV.
- Full test suite: 433 passed (up from the 409-test pre-phase baseline), 0 failed; `backend/DLRSafetyMonitor.py` carries zero diff.

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end "a trained model decides"** - `901e33c` (feat)
2. **Task 2: Fail-safe and OR-combination invariants** - `ef34185` (test)

**Plan metadata:** committed alongside this SUMMARY (see final commit below).

_Note: Task 2 (`tdd="true"`) wrote the full named invariant suite and ran it against Task 1's already-committed implementation before making any further changes — every test passed on first run, so no separate RED-then-GREEN commit split applied; see "Deviations from Plan" for why._

## Files Created/Modified

- `backend/config.py` - New `ANOMALY_ML_*` config block (model dir/filename/observation-frame templates, feature-column/raw-data-key tuples, training years, contamination, random seed)
- `backend/anomaly_detector.py` - `_model_path_for`, `_MODEL_CACHE`, `_load_corridor_model`, `_load_corridor_model_or_none`, `_check_against_model`; `__init__`/`for_corridor` gain `model`/`load_model` params; `check()` restructured to accumulate-then-OR
- `backend/anomaly_training.py` (new) - `corridor_observation_frame`, `build_feature_matrix`, `fit_corridor_model`, `persist_corridor_model`, `_make_isolation_forest_candidate`, `main`/CLI
- `backend/tests/anomaly_detector_test.py` - `fitted_anomaly_model` fixture, model-branch tests, fail-safe/OR-combination invariant tests
- `backend/tests/anomaly_training_test.py` (new) - pooling, drop-without-imputing, and persist-round-trip tests

## Decisions Made

- Feature set is exactly `air_temp`/`wind_speed`/`solar_radiation` with no time-of-day encoding (D-01 resolution) — `raw_data` carries no timestamp at the `check()` call site, so a feature the inference path cannot compute would latch G6 in permanent fallback.
- One pooled model per corridor rather than per-city models (D-01 resolution) — `raw_data` carries no location field, so a per-city selector would have nothing to key on.
- Absent artifact resolves to `model=None` with a logged warning rather than raising (A-04) — differs deliberately from Phase 1's `"ml"` method, since this branch is additive: an unprovisioned model must leave behavior identical to today's two-branch detector.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `02-PATTERNS.md` absent from this isolated worktree's checkout**
- **Found during:** Required-reading step, before Task 1
- **Issue:** `02-PATTERNS.md` was listed as required reading but does not exist inside this worktree (it is untracked in the source checkout, so it never propagated into this isolated worktree's working tree — confirmed via `find`).
- **Fix:** Proceeded using `02-RESEARCH.md`'s equivalent "Architecture Patterns" section (Patterns 1-3), which covers the identical content (additive branch, offline-train/atomic-persist/lazy-load, per-corridor pooling), rather than blocking the whole plan on one missing supplementary file.
- **Files modified:** None (reading-step workaround only).
- **Verification:** Cross-checked plan requirements against `02-RESEARCH.md`'s content before implementing; no gap surfaced during execution or verification.

**2. [Rule 3 - Blocking] `.venv` absent from this fresh worktree checkout**
- **Found during:** Environment setup, before Task 1
- **Issue:** `.venv` is git-ignored and therefore absent from this isolated worktree's checkout (each worktree is a separate working-tree clone).
- **Fix:** Symlinked the shared checkout's already-provisioned `.venv` (`/Users/aphan/Senior_Design/.venv`, where `scikit-learn`/`joblib` were already installed by Phase 1's sessions) into this worktree — a one-time, git-ignored local setup step, not a plan deviation. Every prior `ml-modeling` worktree session in `ACKNOWLEDGEMENTS.md` documents this identical step.
- **Files modified:** None (a `.venv` symlink is git-ignored, invisible to `git status`).
- **Verification:** `.venv/bin/python3 -c "import sklearn, joblib"` succeeded before any task work began.

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking environment/reading-step gaps, no production code affected)
**Impact on plan:** Zero impact on scope or correctness — both were pre-task setup workarounds for isolated-worktree checkout gaps this codebase's prior sessions have repeatedly encountered and documented the same way.

## Issues Encountered

None beyond the two deviations above.

## User Setup Required

None - no external service configuration required. `scikit-learn`/`joblib` were pre-approved and pinned by Phase 1 (v1.3); this phase installs nothing new (per the plan's own T-02-SC threat-register entry).

## Next Phase Readiness

- Plan 02-02 (multi-candidate bake-off and false-positive/false-negative measurement) can build directly on `anomaly_training.py`'s `_make_isolation_forest_candidate`/`corridor_observation_frame`/`build_feature_matrix` and the `ANOMALY_ML_CONTAMINATION` tunable, which this plan explicitly left untuned (0.01, a starting value only).
- Plan 02-03 (ERCOT load characterization) and Plan 02-04 (validation record, C10 spec correction) are unblocked — this plan's model branch and its fail-safe/OR-combination invariants are locked in and tested.
- No blockers. `MIDLAND_EL_PASO`'s own anomaly model is not yet trained (only `AUSTIN_CORPUS_CHRISTI` was trained this session, per Task 1's tracer scope) — training it is a one-command follow-up (`--corridor MIDLAND_EL_PASO`), not a code change.

---
*Phase: 02-anomaly-detection-model*
*Completed: 2026-09-26*

## Self-Check: PASSED

All created/modified files confirmed present on disk (`backend/config.py`, `backend/anomaly_detector.py`, `backend/anomaly_training.py`, `backend/tests/anomaly_detector_test.py`, `backend/tests/anomaly_training_test.py`, this SUMMARY.md). Both task commit hashes (`901e33c`, `ef34185`) confirmed present in `git log --oneline --all`.
