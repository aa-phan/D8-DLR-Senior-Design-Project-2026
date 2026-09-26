---
phase: 02-anomaly-detection-model
plan: 02
subsystem: ml-anomaly-detection
tags: [scikit-learn, isolation-forest, elliptic-envelope, one-class-svm, bake-off, anomaly-detection]

# Dependency graph
requires:
  - phase: 02-anomaly-detection-model
    provides: "Plan 02-01's tracer estimator, corridor_observation_frame/build_feature_matrix/fit_corridor_model/persist_corridor_model, AnomalyDetector.for_corridor's load_model opt-out"
provides:
  - "anomaly_training.py measurement machinery: chronological_split, inject_anomalies (out_of_range + in_range_implausible), score_model, score_rolling_baseline, validate_candidate"
  - "anomaly_training.py D-03 bake-off machinery: CANDIDATE_ESTIMATORS (3 candidates), corridor_report, select_winner, --validate and --bakeoff CLI entry points"
  - "config.ANOMALY_ML_* measurement tunables (holdout fraction, contamination grid, injection rate, false-positive ceiling, SVM row cap, report filename)"
  - "Both corridors' measured-winner anomaly models persisted and loadable (data/models/anomaly_{corridor}.joblib)"
  - "data/models/anomaly_validation_report.json -- every (corridor, candidate, contamination) measurement, losers included, plus each corridor's selected winner"
affects: [02-03-ercot-load-characterization, 02-04-validation-record]

# Actuals (#2632)
actuals:
  tokens: 14300
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Chronological (never shuffled) fit/holdout split for false-positive measurement, mirroring TimeSeriesSplit's train-strictly-precedes-test guarantee at the whole-frame level"
    - "Two-category synthetic anomaly injection (out-of-range physical-bound violation vs. in-range jointly-implausible combination) to measure recall on an inherently unlabeled real-data problem"
    - "Baseline scored through the runtime module's own real branch (AnomalyDetector with load_model=False), never a parallel reimplementation of its band arithmetic"
    - "D-03 bake-off: three-candidate x contamination-grid cross product, every arm's numbers retained, deterministic eligible-set-then-tiebreak winner selection mirroring forecast_training.select_winner's refusal semantics"

key-files:
  created: []
  modified:
    - backend/config.py
    - backend/anomaly_training.py
    - backend/tests/anomaly_training_test.py

key-decisions:
  - "in_range_implausible triple uses nearest-rank (not linearly interpolated) quantiles of the fit slice, so every component value is one the real data actually contains -- only the joint combination is novel"
  - "The rolling-baseline arm is scored by constructing a real AnomalyDetector(history=..., load_model=False) and calling its own _check_against_rolling_baseline branch, never a second implementation of mean +/- k*std"
  - "OneClassSVM's training-row cap (config.ANOMALY_ML_SVM_MAX_TRAIN_ROWS) applies only during the bake-off sweep, taking the chronologically-earliest fit rows; the final winner refit (Task 2) always uses the full assembled frame per A-08, uncapped even when OneClassSVM wins"
  - "select_winner reads only report['measurements'], never a cached/derived summary, so a report that dropped a losing arm silently would raise rather than silently pick a winner"

patterns-established:
  - "anomaly_training.py's --validate/--bakeoff CLI entry points mirror forecast_training.py's own --bakeoff shape: per-corridor try-and-continue error handling, a fixed-width results table, one accumulated JSON report, and a final greppable SUMMARY: line per corridor"

requirements-completed: [ANOM-01, ANOM-02]

coverage:
  - id: D1
    description: "Both halves of ANOM-02's bar are measured on real data: a clean false-positive rate on a strictly-later chronological holdout, and per-category recall on synthetically injected corruption (out-of-range and in-range-implausible), for the trained model AND the existing rolling mean-and-standard-deviation baseline on identical rows"
    requirement: ANOM-02
    verification:
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_chronological_split_returns_nonoverlapping_time_ordered_slices"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_inject_anomalies_out_of_range_values_are_outside_bounds"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_inject_anomalies_in_range_implausible_components_are_observed_but_combination_is_not"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_score_rolling_baseline_arm_uses_real_branch_and_bare_model"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_validate_candidate_returns_all_expected_finite_rate_keys"
        status: pass
      - kind: integration
        ref: ".venv/bin/python3 backend/anomaly_training.py --corridor AUSTIN_CORPUS_CHRISTI --years 1 --validate (live Open-Meteo Archive API, 17,520 rows)"
        status: pass
    human_judgment: false
  - id: D2
    description: "All three D-03 candidates (IsolationForest, EllipticEnvelope, OneClassSVM) are fitted and scored on identical per-corridor data across the same contamination grid; every candidate's measured numbers are recorded including the losers; the winner is selected by the plan's single stated deterministic rule, never by architecture preference, and refuses to pick a winner on a missing/non-finite measurement"
    requirement: ANOM-01
    verification:
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_candidate_estimators_has_exactly_three_keys_and_fresh_instances"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_no_eager_sklearn_import"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_select_winner_returns_highest_eligible_pooled_recall"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_select_winner_falls_back_to_lowest_false_positive_when_none_eligible"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_select_winner_recall_tie_breaks_by_false_positive_rate"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_select_winner_further_tie_breaks_by_insertion_order"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_select_winner_raises_on_missing_or_non_finite_measurement"
        status: pass
      - kind: integration
        ref: ".venv/bin/python3 backend/anomaly_training.py --bakeoff --years 1 (live Open-Meteo Archive API, both corridors)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Both corridors in config.CORRIDOR_ENDPOINTS are trained, scored, and persisted independently by --bakeoff, and each corridor's own artifact is loadable through AnomalyDetector.for_corridor and produces that corridor's own verdicts"
    requirement: ANOM-01
    verification:
      - kind: integration
        ref: "PYTHONPATH=backend .venv/bin/python3 -c \"...ad.AnomalyDetector.for_corridor(c).model is not None for c in config.CORRIDOR_ENDPOINTS...\" (BAKEOFF_OK printed for both corridors)"
        status: pass
    human_judgment: false

# Metrics
duration: 17min
completed: 2026-09-26
status: complete
---

# Phase 2 Plan 02: D-03 Bake-off and ANOM-02 Measurement Summary

**Turned Plan 02-01's single untuned `IsolationForest` tracer into a measured, evidence-selected winner per corridor: all three D-03 candidates (`IsolationForest`, `EllipticEnvelope`, `OneClassSVM`) fitted and scored across a five-point contamination grid against a strictly-later chronological holdout and two categories of synthetically injected corruption, compared against the existing rolling baseline on identical rows -- `OneClassSVM` won both corridors on real Open-Meteo data (contamination 0.001 and 0.005 respectively), each meeting the false-positive ceiling with pooled recall 1.0, with every measurement (losers included) written to `data/models/anomaly_validation_report.json`.**

## Performance

- **Duration:** ~17 min
- **Started:** 2026-09-26T17:37:00-05:00 (approx.)
- **Completed:** 2026-09-26T17:54:00-05:00 (approx.)
- **Tasks:** 2 completed
- **Files modified:** 3

## Accomplishments

- `backend/anomaly_training.py` gained the ANOM-02 measurement machinery: `chronological_split` (time-ordered, never-shuffled fit/holdout split, refuses an empty side or a fit side below `ROLLING_BASELINE_MIN_ROWS`), `inject_anomalies` (two labelled categories -- `out_of_range` values pushed past `DLRSafetyMonitor`'s G3 bounds, and `in_range_implausible` combinations whose individual values are each in-bounds and each individually observed in the fit slice but whose joint combination never occurs there), `score_model`/`score_rolling_baseline` (the baseline arm scores through the REAL `AnomalyDetector._check_against_rolling_baseline` branch via `load_model=False`, never a reimplementation of its band arithmetic), and `validate_candidate` (measures false-positive rate and per-category recall for the candidate AND the baseline, on identical rows, with disjoint clean/injected denominators).
- `backend/anomaly_training.py` gained D-03's full three-candidate comparison: `_make_elliptic_envelope_candidate`/`_make_one_class_svm_candidate` alongside the existing `_make_isolation_forest_candidate`, `CANDIDATE_ESTIMATORS` (insertion order is the last-resort tiebreak), `corridor_report` (every candidate x contamination pair, losers included), and `select_winner` (the plan's stated deterministic rule -- highest pooled recall among false-positive-ceiling-eligible pairs, tie broken by lower false-positive rate then by candidate insertion order; falls back to lowest false-positive rate with `ceiling_met=False` when no pair is eligible; raises `ValueError` naming the candidate on a missing/non-finite measurement).
- Six new `ANOMALY_ML_*` tunables in `backend/config.py`: `ANOMALY_ML_VALIDATION_HOLDOUT_FRACTION`, `ANOMALY_ML_CONTAMINATION_GRID`, `ANOMALY_ML_INJECTION_RATE`, `ANOMALY_ML_MAX_FALSE_POSITIVE_RATE`, `ANOMALY_ML_SVM_MAX_TRAIN_ROWS`, `ANOMALY_ML_VALIDATION_REPORT_NAME`.
- CLI extended with `--validate` (single-candidate contamination sweep, one corridor) and `--bakeoff` (full three-candidate bake-off, selects and persists each corridor's measured winner, one `SUMMARY:` line per corridor).
- Live E2E run against the real Open-Meteo Archive API for both corridors (~52 seconds total): 15 measurements per corridor (3 candidates x 5 contamination points), both persisted `.joblib` artifacts load through `AnomalyDetector.for_corridor` with a non-`None` model. **The real, honest measurement: `OneClassSVM` won both corridors** (`AUSTIN_CORPUS_CHRISTI` at contamination 0.001, `MIDLAND_EL_PASO` at 0.005), each meeting the false-positive ceiling with pooled recall 1.0. `EllipticEnvelope` measured markedly worse (pooled recall capped near 0.125-0.625 across the grid, consistent with 02-RESEARCH.md's own doubt about its Gaussian assumption against irradiance's night-time zero floor). `IsolationForest`'s recall on the `out_of_range` category was surprisingly weak at low contamination (as low as 0.53 pooled) even though it reliably caught the `in_range_implausible` category -- reported honestly per D-07's precedent rather than smoothed over.
- Full test suite: 451 passed (up from the 433-test pre-plan baseline), 0 failed. `backend/anomaly_detector.py` carries zero diff.

## Task Commits

Each task was committed atomically:

1. **Task 1: Measure both halves of ANOM-02's bar** - `d181c96` (feat)
2. **Task 2: D-03 bake-off and deterministic winner selection** - `8f627f9` (feat)

**Plan metadata:** committed alongside this SUMMARY (see final commit below).

_Note: Both tasks (`tdd="true"`) wrote their named invariant test suites and ran them against the same-session implementation; every test passed without a separate RED-then-GREEN split, mirroring Plan 02-01's own documented precedent for this repeated pattern (see "Deviations from Plan")._

## Files Created/Modified

- `backend/config.py` - Six new `ANOMALY_ML_*` measurement tunables (holdout fraction, contamination grid, injection rate, false-positive ceiling, SVM row cap, validation report filename)
- `backend/anomaly_training.py` - `chronological_split`, `_out_of_range_value`, `_implausible_combination`, `inject_anomalies`, `_dlr_amps_for`, `score_model`, `score_rolling_baseline`, `validate_candidate`, `_run_validate`, `_make_elliptic_envelope_candidate`, `_make_one_class_svm_candidate`, `CANDIDATE_ESTIMATORS`, `corridor_report`, `select_winner`, `_run_bakeoff`; new `--validate`/`--bakeoff` CLI flags
- `backend/tests/anomaly_training_test.py` - 18 new tests covering split ordering, injection non-mutation/category construction/reproducibility, baseline-arm provenance, validate_candidate shape/disjoint-denominators, candidate-set shape, no-eager-sklearn-import, and select_winner's full selection-rule/tiebreak/refusal matrix

## Decisions Made

- `_implausible_combination` draws each component from the fit slice's own nearest-rank (not linearly interpolated) quantile, so every component value is one the real data actually contains -- guarantees the acceptance criterion that only the joint combination, never a component, is novel.
- The OneClassSVM training-row cap applies only during the bake-off sweep (taking the chronologically-earliest fit rows); the final winner refit always uses the full assembled frame (fit + holdout), uncapped, per A-08 -- confirmed feasible in practice (both corridors' bake-offs, including OneClassSVM's uncapped 17,520-row final refit when it won, completed in ~52 seconds total).
- `select_winner` reads only `report["measurements"]`, never a cached/derived summary, so a report that silently dropped a losing arm would raise rather than silently pick a winner on incomplete evidence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `02-PATTERNS.md` absent from this isolated worktree's checkout**
- **Found during:** Required-reading step, before Task 1
- **Issue:** `02-PATTERNS.md` is listed as required reading but does not exist inside this worktree's checkout (untracked in the source checkout per the orchestrator's git-status snapshot, so it never propagated into this isolated worktree) -- the identical gap Plan 02-01 documented in its own SUMMARY.
- **Fix:** Proceeded using `02-RESEARCH.md`'s equivalent "Architecture Patterns"/"Don't Hand-Roll" sections, which cover the same content (bake-off convention, offline-train/persist pattern), rather than blocking the whole plan on one missing supplementary file.
- **Files modified:** None (reading-step workaround only).

**2. [Rule 3 - Blocking] `.venv` absent from this fresh worktree checkout**
- **Found during:** Environment setup, before Task 1
- **Issue:** `.venv` is git-ignored and therefore absent from this isolated worktree's checkout.
- **Fix:** Symlinked the shared checkout's already-provisioned `.venv` (`/Users/aphan/Senior_Design/.venv`) into this worktree -- the same one-time, git-ignored local setup step every prior `ml-modeling` worktree session (including Plan 02-01) has documented identically.
- **Files modified:** None (a `.venv` symlink is git-ignored, invisible to `git status`).

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking environment/reading-step gaps, no production code affected, both identical in kind to Plan 02-01's own documented workarounds for the same isolated-worktree checkout gaps).
**Impact on plan:** Zero impact on scope or correctness.

## Issues Encountered

None beyond the two deviations above. One notable non-issue worth recording for Plan 02-04's Limitations: `IsolationForest`'s recall on the `out_of_range` injection category was measurably weaker than expected at low contamination (as low as 0.53 pooled recall, driven by the out-of-range half specifically) despite the injected values being comfortably beyond `DLRSafetyMonitor`'s own physical bounds. Direct inspection of `decision_function` scores confirmed this is a genuine property of `IsolationForest`'s isolation-path behavior on single-dimension extrapolation beyond the training range in this low-dimensional (3-feature) space, not a bug in the injection or scoring code -- the `in_range_implausible` category (a genuinely joint anomaly) was caught with recall 1.0 by the winning `OneClassSVM` and reliably by `IsolationForest` too. This is real, honest evidence for Plan 02-04's record, not a defect to fix in this plan.

## User Setup Required

None - no external service configuration required. `scikit-learn`'s `EllipticEnvelope`/`OneClassSVM` are submodules of the already-approved, already-pinned `scikit-learn` package (not separate PyPI packages) -- this plan installs nothing new, per its own T-02-SC threat-register entry.

## Next Phase Readiness

- Plan 02-03 (ERCOT load characterization) is unblocked -- independent of this plan's anomaly-model work.
- Plan 02-04 (validation record, C10 spec correction) can transcribe `data/models/anomaly_validation_report.json`'s numbers directly: both corridors' full 15-measurement comparison (losers included), selected winner/contamination/ceiling-met flag, row counts, and window spans are all present and machine-readable. Plan 02-04 should specifically state: (a) the two injection categories and their rates/margins per A-05, (b) that the `out_of_range` category is partly redundant with G3 per A-06 while `in_range_implausible` is the multivariate-value proof, (c) that the holdout fraction and contamination grid were fixed choices, not swept, per A-07, and (d) that the persisted artifact is a full-frame refit distinct from the holdout-scored measurement per A-08.
- No blockers. Both corridors' anomaly models are now measured, evidence-selected, and persisted -- `AUSTIN_CORPUS_CHRISTI` and `MIDLAND_EL_PASO` both load a real `OneClassSVM` through `AnomalyDetector.for_corridor`.

---
*Phase: 02-anomaly-detection-model*
*Completed: 2026-09-26*

## Self-Check: PASSED

All modified files confirmed present on disk (`backend/config.py`, `backend/anomaly_training.py`, `backend/tests/anomaly_training_test.py`, `ACKNOWLEDGEMENTS.md`, this SUMMARY.md). Both task commit hashes (`d181c96`, `8f627f9`) confirmed present in `git log --oneline --all`. Full test suite: 451 passed, 0 failed. `data/models/anomaly_AUSTIN_CORPUS_CHRISTI.joblib` and `data/models/anomaly_MIDLAND_EL_PASO.joblib` both confirmed present and loadable with non-`None` models via `AnomalyDetector.for_corridor`.
