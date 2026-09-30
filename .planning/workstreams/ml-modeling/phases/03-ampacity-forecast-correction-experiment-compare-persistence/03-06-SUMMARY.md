---
phase: 03-ampacity-forecast-correction-experiment-compare-persistence
plan: 06
subsystem: ml-modeling
tags: [forecast-experiment, leakage-probe, wind-correction, cooling-correction, mlp-regressor, no-peeking-lock, checkpoint-decision]

# Dependency graph
requires:
  - phase: 03 (plans 03, 04, 05)
    provides: "The lead_hours-generalized anchored-pair-frame contract and NON_FITTED_ARMS registry (03-03/03-04), and the wind/cooling correction families plus build_training_matrix's horizon_minutes seam (03-05) this plan wires together."
provides:
  - "docs/data-science/decisions/forecast_correction_experiment.md: the Expectation section (predicted winner, oracle ceiling, amperes-scale practical-significance threshold, and a commitment to reporting a null result), committed in an isolated two-file commit with the test-split lock flip -- git log is the audit trail proving the Expectation predates every held-out test read."
  - "backend/forecast_experiment.py: ALL_ARMS (the seven-arm registry), FITTED_ARM_NAMES, WIND_CONFIGURATION/COOLING_CONFIGURATION (Plan 03-05's validation-selected configurations, passed in rather than re-selected), fit_fitted_arms (fits arms 3/4/5 on a stacked two-city train+validation frame, arm 5 refit from scratch at a 24-hour target via forecast_training.build_training_matrix), _stacked_pair_frame/_arm5_truth_frame/_add_correction_columns (the column-contract adapter between this module and forecast_correction_models.py), and leakage_probe (a truth-column-sabotage measurement with demonstrated power against six real forecast arms plus a deliberately sabotaged one)."
affects: ["03-06 Task 3 (unstarted)", "03-07"]

# Actuals (#2632)
actuals:
  tokens: 12178
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Placeholder-factory registry entries: ALL_ARMS keeps all seven arm names inspectable by length/membership without a live fetch or a model fit, by giving the three fitted-arm entries a factory whose returned callable raises (naming fit_fitted_arms) rather than silently returning a callable that would fail deep inside scoring."
    - "Stacked (not corridor-reduced) two-city frame for pooled/per-city model fitting: _stacked_pair_frame concatenates both endpoint cities' own anchored_pair_frames with an endpoint_city tag, preserving each city's individual weather/wind rows side by side -- the corridor-reduced single-row-per-timestamp shape corridor_anchored_pair_frame returns cannot supply this, since weakest-link reduction already discarded the losing city's own values."
    - "Genuinely live-recomputing arm callables as the leakage probe's precondition: _wind_corrected_ampacity/_cooling_corrected_ampacity re-read frame's own fcst_*/anchor_* columns on every call rather than caching a prediction by timestamp, which is what gives the sabotage-and-compare probe real power against these two fitted arms."
    - "A reference-model callable that structurally cannot leak by construction: the from-scratch 24-hour reference arm's prediction path only ever reads anchor_datetime_utc from the frame it's given -- never any truth_*/fcst_* column -- so a sabotaged truth column cannot reach it regardless of what the probe does, verified directly rather than assumed."

key-files:
  created:
    - docs/data-science/decisions/forecast_correction_experiment.md
  modified:
    - backend/forecast_experiment.py
    - backend/tests/forecast_experiment_test.py

key-decisions:
  - "Followed 03-06-PLAN.md's explicit, repeated instruction to use Plan 03-05's validation-selected wind/cooling configurations (LinearRegression+pooled, GradientBoostingRegressor+log_ratio) AS FIXED ARGUMENTS to fit_fitted_arms, rather than re-running select_wind_configuration/select_cooling_configuration against real corridor data -- even though 03-05-SUMMARY.md's own 'Next Phase Readiness' section explicitly anticipated Plan 03-06 re-running both selectors on real data ('these numbers are illustrative... Plan 03-06 will re-run both selectors against the real 24-hour Previous-Runs corridor data'). Resolved in favor of THIS plan's literal, repeated text ('Pass those selections in as arguments rather than re-running the selectors here... re-selecting now would be a selection decision taken after the test split was unlocked'), since the plan being executed is the authoritative instruction and its own no-peeking rationale is explicit and specific. Recorded in the decision record's Configuration measured section so a future reader sees both the configuration used and the source of the tension."
  - "ALL_ARMS' three fitted-arm entries are placeholder factories that raise when their returned callable is invoked, rather than genuinely scoreable factory(geometry)->callable(frame) entries. A fitted arm structurally needs a model fit on real train+validation data before it can predict anything, which a zero-argument-plus-geometry factory cannot supply; the placeholder keeps ALL_ARMS's length/membership inspectable by a bare import (matching the plan's own <verify> gate, which only checks length and membership) while making the actual fitting-and-scoring path (fit_fitted_arms) the only real entry point, and fails loudly rather than silently if a caller tries to shortcut it."
  - "fit_fitted_arms accepts a STACKED (endpoint_city-tagged) two-city frame, not the corridor-reduced single-row-per-timestamp shape corridor_anchored_pair_frame (03-04) returns. Arms 3/4's pooled-with-endpoint-indicator or per-city fitting genuinely needs each city's own individual weather/wind rows side by side; the corridor-reduced shape has already thrown away the losing city's own values via weakest-link reduction. A new _stacked_pair_frame helper builds this shape by concatenation rather than reduction."
  - "Arm 5 is fit on train_val_frame's FULL (unfiltered w.r.t. lead) hourly cadence, never the exact-24h-lead-filtered subset arms 3/4 use -- its lag features (1/2/3/6 hours) need genuine hour-to-hour spacing, which the six-hourly-filtered subset would corrupt. Arms 3/4, by contrast, fit ONLY on the exact-lead subset, so their training data carries the same verified 24.0-hour lead their scoring will claim (03-RESEARCH.md Pitfall 1's discipline extended from scoring to training)."
  - "Deferred to Task 3 (not built in this session): the corridor-level SCORING integration that would wire fit_fitted_arms's fitted objects into _run_corridor/main's actual score_arms call. Task 2's own <files> list only backend/forecast_experiment.py and its test file, with no mention of extending _run_corridor/main -- that wiring is Task 3's stated job ('all seven arms scored on a byte-identical index'). This session stops at the checkpoint immediately after Task 2, before Task 3 begins, per standard (non-auto-mode) checkpoint protocol."

patterns-established:
  - "Leakage-probe test coverage assembled from BOTH already-existing live-recomputing arms (NON_FITTED_ARMS) and newly-fitted ones (arms 3/4/5), plus one deliberately sabotaged arm, in a single test -- demonstrating the probe's power against a representative superset of the phase's actual arm registry rather than only against arms trivially known to be clean."

requirements-completed: []

coverage:
  - id: D1
    description: "The Expectation section of the decision record is committed in an isolated two-file commit (the record plus the test-split lock flip) containing no scoring run and no arm implementation -- git log is the audit trail, not a document's self-reported date"
    requirement: D-02
    verification:
      - kind: other
        ref: "git log -1 --name-only on commit 4d964cf: exactly docs/data-science/decisions/forecast_correction_experiment.md and backend/forecast_experiment.py (EXPECTATION_COMMIT_OK)"
        status: pass
      - kind: unit
        ref: "PYTHONPATH=backend .venv/bin/python3 -c \"import forecast_experiment as fe; fe._require_test_split_unlocked()\" (TEST_SPLIT_UNLOCKED_OK)"
        status: pass
    human_judgment: false
  - id: D2
    description: "ALL_ARMS is a seven-entry registry (four non-fitted plus three fitted-arm placeholders) containing the oracle; the candidate mapping derived from it (excluding the oracle) has six entries"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py::test_all_arms_has_exactly_seven_entries_and_contains_oracle, test_candidate_mapping_derived_from_all_arms_excludes_oracle_and_has_six"
        status: pass
    human_judgment: false
  - id: D3
    description: "fit_fitted_arms fits arms 3 and 4 via forecast_correction_models on the exact-24h-lead subset of a stacked two-city frame, and refits arm 5 from scratch at a 24-hour target via build_training_matrix(horizon_minutes=1440) -- with the monkeypatched production model loader never reached and no reference in non-comment source to FORECAST_ML_MODEL_DIR/_load_corridor_model/_MODEL_CACHE"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py::test_fit_fitted_arms_returns_three_fitted_objects, test_arm5_target_index_is_exactly_24_hours_after_feature_index, test_fit_fitted_arms_arm5_never_touches_production_model_loader_or_cache"
        status: pass
      - kind: other
        ref: "grep -vE '^[[:space:]]*#' backend/forecast_experiment.py | grep -cE 'FORECAST_ML_MODEL_DIR|_load_corridor_model|_MODEL_CACHE' -> 0 (NO_ARTIFACT_REUSE_OK)"
        status: pass
    human_judgment: false
  - id: D4
    description: "leakage_probe, given a sabotaged-truth-column frame, reports no change for six real forecast arms (persistence_24h, nwp_wind_delta, raw_forecast, ml_wind_corrected, ml_cooling_corrected, reference_ml_refit_24h), flags the oracle, and flags a deliberately sabotaged arm that reads truth_wind_speed directly -- demonstrated power, not a vacuous pass"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py::test_leakage_probe_passes_on_real_arms_flags_oracle_and_flags_a_sabotaged_arm"
        status: pass
    human_judgment: false

duration: ~40min (Tasks 1-2 plus the preceding architecture design)
completed: 2026-09-30
status: halted
---

# Phase 3 Plan 6: Expectation Commit, Fitted-Arm Wiring, and a Power-Tested Leakage Probe (HALTED at the pre-test-set checkpoint) Summary

**Committed the decision record's Expectation (predicting `raw_forecast` as the likely winner, with no margin expected to be large) in the same isolated commit that unlocked the held-out test split, wired arms 3 (`ml_wind_corrected`), 4 (`ml_cooling_corrected`) and 5 (`reference_ml_refit_24h`, a from-scratch `MLPRegressor` refit at a 24-hour target) into a seven-entry `ALL_ARMS` registry, and built a leakage probe that demonstrably catches a deliberately sabotaged arm while passing cleanly on all six real forecast arms and correctly flagging the oracle — then stopped at the plan's own checkpoint before the one irreversible step (scoring the held-out test set), because auto-mode is not active for this project and the checkpoint's `gate="blocking"` still requires an explicit human reply in interactive mode.**

## Performance

- **Duration:** ~40 min (Tasks 1-2, including the architecture work needed to reconcile Plan 03-05's per-city correction-model contract with this module's corridor-level anchored-pair-frame shape)
- **Completed:** 2026-09-30
- **Tasks:** 2 of 3 (plus the checkpoint, reached and NOT resolved — see below)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- **Task 1 — the Expectation, committed before any test read.** `docs/data-science/decisions/forecast_correction_experiment.md` now exists with all nine sections; the four writable-now sections (What was built, Data provenance, Configuration measured, Expectation, References) are substantive, and the four not-yet-writable sections (Measured results, Verdict, Limitations, Open Questions) each carry an explicit Plan 03-07 placeholder. The Expectation predicts `raw_forecast` (arm 2) as the likely winner, reasoning from Plan 03-04's own validation-split evidence that the full forecast already beats every cheaper non-fitted baseline at one corridor and is nearly tied with persistence at the other; states the oracle's measured margin as the ceiling (88-92% of `raw_forecast`'s own error, but unlikely to be substantially closed by a real correction, since even the non-fitted `nwp_wind_delta` baseline failed to close it); names a 30-50 amp practical-significance threshold; predicts arm 5 underperforms persistence by a margin at least as large, proportionally, as Phase 1's 60-minute loss; and commits explicitly to reporting a null result if no arm's interval excludes zero. In the SAME commit, `backend/forecast_experiment.py`'s `_TEST_SPLIT_UNLOCKED` flag flipped from `False` to `True` — `git log` shows this as an isolated, two-file commit containing no scoring run and no arm implementation.
- **Task 2 — arms 3/4/5 wired, leakage probe built and power-tested.** `ALL_ARMS` is now a seven-entry registry; `fit_fitted_arms` fits the wind-correction and cooling-correction families (via `forecast_correction_models`, using Plan 03-05's validation-selected `LinearRegression+pooled`/`GradientBoostingRegressor+log_ratio` configurations, passed in rather than re-selected) on the exact-24h-lead subset of a newly-built stacked two-city frame, and refits arm 5 from scratch — the same `MLPRegressor` family `forecasting_model.md` persisted as the production winner — at an explicit 24-hour target via `forecast_training.build_training_matrix(horizon_minutes=1440)`, proven never to touch the production model directory, the per-corridor loader, or the process-global model cache (monkeypatch-to-raise test passes; grep confirms zero non-comment references to any of the three forbidden constants/functions). `leakage_probe` sabotages every `truth_`-prefixed column with an in-range sentinel and re-runs every supplied arm; its power test registers six real forecast arms (three non-fitted, two newly-fitted corrections, and the from-scratch reference model) plus the oracle plus one deliberately sabotaged arm reading `truth_wind_speed` directly, and correctly reports the six forecast arms unchanged, the oracle changed, and the sabotaged arm changed.
- **Fixed a Task-1-induced regression.** Flipping `_TEST_SPLIT_UNLOCKED` to `True` broke three pre-existing tests that asserted the module's live flag value was `False`; re-scoped them to monkeypatch the flag back to locked so they test the lock MECHANISM rather than a snapshot of the module's current state (documented as a deviation below).

## Task Commits

1. **Task 1: Commit the Expectation and unlock the test split** - `4d964cf` (docs)
2. **Fix: re-scope the no-peeking lock tests** (Rule 1, fallout from Task 1) - `045d0ea` (fix)
3. **Task 2 RED: failing tests for ALL_ARMS/fit_fitted_arms/leakage_probe** - `bf5d92b` (test)
4. **Task 2 GREEN: wire arms 3/4/5 and land the leakage probe** - `2ad9971` (feat)

## Files Created/Modified

- `docs/data-science/decisions/forecast_correction_experiment.md` — the decision record: What was built, Data provenance, Configuration measured, Expectation, and References written now; Measured results/Verdict/Limitations/Open Questions explicitly deferred to Plan 03-07.
- `backend/forecast_experiment.py` — `_TEST_SPLIT_UNLOCKED` flipped to `True`; `ALL_ARMS`, `FITTED_ARM_NAMES`, `WIND_CONFIGURATION`/`COOLING_CONFIGURATION`, `_fitted_arm_not_wired_via_registry`, `_add_correction_columns`, `_wind_corrected_ampacity`/`_cooling_corrected_ampacity`, `_stacked_pair_frame`, `_arm5_truth_frame`, `fit_fitted_arms`, `leakage_probe` added.
- `backend/tests/forecast_experiment_test.py` — 11 new tests for Task 2's registry/fitting/leakage-probe behavior; 3 pre-existing lock tests re-scoped to monkeypatch the flag rather than read the module's live value.

## Decisions Made

See `key-decisions` in frontmatter for full detail. Summary:
1. Used Plan 03-05's synthetic-data-selected wind/cooling configurations as fixed arguments, per this plan's own explicit repeated instruction, rather than re-selecting against real data as Plan 03-05's own SUMMARY anticipated — documented as a genuine tension, resolved in favor of the plan being executed.
2. `ALL_ARMS`' three fitted-arm entries are placeholder factories that raise, not genuinely scoreable factories — the real fitting path is `fit_fitted_arms`, matching the plan's own `<verify>` gate (length/membership only).
3. Built a new stacked (not corridor-reduced) two-city frame shape for arms 3/4's fitting, since the existing corridor-reduced shape has already discarded per-city data the pooled/per-city model fitting needs.
4. Arm 5 fits on the FULL unfiltered hourly cadence (needs real hour-to-hour lag spacing); arms 3/4 fit only on the exact-24h-lead-filtered subset (needs the verified lead claim to hold in training, not just scoring).
5. Deferred the corridor-level SCORING integration (wiring `fit_fitted_arms`'s output into `_run_corridor`/`main`'s actual `score_arms` call) to Task 3, since Task 2's own `<files>` list doesn't include that wiring and Task 3's own text owns "all seven arms scored on a byte-identical index."

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed three pre-existing tests broken by Task 1's legitimate lock flip**
- **Found during:** Task 2, running the full `forecast_experiment_test.py` file after Task 1's commit
- **Issue:** `test_guard_test_split_access_raises_for_test_and_not_for_val`, `test_require_test_split_unlocked_raises_naming_expectation_and_plan_03_06`, and `test_guard_test_split_access_delegates_to_require_test_split_unlocked` all asserted the module's actual `_TEST_SPLIT_UNLOCKED` value was `False` — true before Task 1, false after Task 1's intentional unlock.
- **Fix:** Each test now monkeypatches `fe._TEST_SPLIT_UNLOCKED` to `False` for its own duration, testing the lock mechanism (`_require_test_split_unlocked`/`_guard_test_split_access`) independent of the module's actual current value.
- **Files modified:** `backend/tests/forecast_experiment_test.py`
- **Verification:** All three tests pass; full file returns to 59/59 passing before Task 2's own new tests were added.
- **Committed in:** `045d0ea` (fix)

---

**Total deviations:** 1 auto-fixed (Rule 1, a direct and expected consequence of Task 1's own intentional change). **Impact:** Zero scope creep — the fix only touches test assertions about a flag Task 1 was explicitly instructed to flip.

## Checkpoint Reached (plan HALTED here)

**Checkpoint:** "Checkpoint: approve crossing into the held-out test set" (`type="checkpoint:decision"`, `gate="blocking"`)

**Why this session stops here rather than proceeding to Task 3:** `workflow._auto_chain_active` and `workflow.auto_advance` are both unset/false in `.planning/config.json` — auto-mode is NOT active for this project. Per the standard (non-auto-mode) checkpoint protocol, a `type="checkpoint:*"` task means STOP immediately and return a structured checkpoint message; a `gate="blocking"` checkpoint is only auto-approved when auto-mode is active, which it is not here. Task 3 — the phase's one irreversible step (scoring the held-out test set) — has NOT been executed. No test-set row has been read.

**What is true right now, checkable rather than asserted (matching the checkpoint's own three preconditions):**
1. The Expectation is committed and predates everything — `git log` shows it landing in a single two-file commit (`4d964cf`) with the lock flip and no scoring run.
2. The leakage probe has demonstrated power — it passes on all six forecast arms, flags the oracle, and flags a deliberately sabotaged arm (`test_leakage_probe_passes_on_real_arms_flags_oracle_and_flags_a_sabotaged_arm`).
3. Arm 3's pooling and arm 4's target parameterization are fixed to Plan 03-05's validation-selected configurations and passed into `fit_fitted_arms` rather than re-selected.

**Awaiting:** An explicit reply of `proceed` (authorizing the single test-set run) or `hold` (naming a specific guard to strengthen first) from whoever resumes this plan. Per the checkpoint's own `<resume-signal>`, this decision and its rationale must be recorded in this plan's SUMMARY when Task 3 eventually runs.

## Issues Encountered

None beyond the Task-1-induced test regression documented above under Deviations.

## Known Stubs

None — every function this session's tasks built is fully implemented and tested against synthetic data; `ALL_ARMS`' three placeholder factories are a deliberate, documented design (not a stub left unfinished — they raise loudly by design, and the real fitting path `fit_fitted_arms` is fully implemented).

## User Setup Required

None — no external service configuration required. This session used only cached/synthetic test data; no live network call was made.

## Next Phase Readiness

- **NOT ready for Plan 03-07** — Task 3 (the held-out test-set scoring, the Measured results section, and the paired bootstrap confidence intervals) has not run. Plan 03-07 depends on this plan's Task 3 output.
- **Ready for Task 3 to resume, once the checkpoint is answered:** `fit_fitted_arms`, `ALL_ARMS`, and `leakage_probe` are fully built and tested; `_stacked_pair_frame`/`_arm5_truth_frame`/`_add_correction_columns` give Task 3 the column-contract adapter it needs to wire these three fitted arms into `_run_corridor`/`main`'s actual corridor-level scoring, without re-deriving the fitting logic.
- **No blockers other than the checkpoint itself.** No file outside this plan's own scope was touched; the full suite carries exactly the same 23 pre-existing `corridor_discretization_test.py` failures recorded in `.planning/WINDOWS.md` (627 passed / 23 failed after this plan's commits, up from 590/23 at plan start) — no regression introduced.
- **ACKNOWLEDGEMENTS.md intentionally not touched**, per this phase's established precedent (Plans 03-03/03-04/03-05 also did not touch it) — Plan 03-07 owns the consolidated Waves 2-5 AI-use disclosure entry.

## Self-Check: PASSED

- `docs/data-science/decisions/forecast_correction_experiment.md` (contains all nine section headings, Expectation >=150 words with "amp" and "oracle") — FOUND
- `backend/forecast_experiment.py` (contains `ALL_ARMS`, `FITTED_ARM_NAMES`, `fit_fitted_arms`, `leakage_probe`, `_TEST_SPLIT_UNLOCKED: bool = True`) — FOUND
- `backend/tests/forecast_experiment_test.py` — FOUND (70 tests, verified passing)
- Commit `4d964cf` — FOUND in `git log --oneline --all`
- Commit `045d0ea` — FOUND
- Commit `bf5d92b` — FOUND
- Commit `2ad9971` — FOUND
- `backend/forecast_training.py`, `backend/forecast_correction_models.py`, `backend/thermal_model.py`, `backend/ampacity_forecast.py`, `backend/anomaly_detector.py`, `backend/DLRSafetyMonitor.py`, `backend/config.py` carry zero diff from this plan's base (`c043c17`) — CONFIRMED
- Full suite: 627 passed, 23 failed (unchanged pre-existing `corridor_discretization_test.py` baseline per `.planning/WINDOWS.md`) — CONFIRMED

---
*Phase: 03-ampacity-forecast-correction-experiment-compare-persistence*
*Plan: 06 (HALTED at checkpoint before Task 3)*
*Completed: 2026-09-30*
