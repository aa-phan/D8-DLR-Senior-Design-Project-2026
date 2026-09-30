---
phase: 03-ampacity-forecast-correction-experiment-compare-persistence
plan: 05
subsystem: ml-modeling
tags: [scikit-learn, wind-vector, ieee738, q_conv_override, u-v-decomposition, correction-models, pandas, numpy]

# Dependency graph
requires:
  - phase: 03 (plan 02)
    provides: "wind_vector.to_uv/from_uv, thermal_model.convective_heat_loss/q_conv_override -- the two seams this plan's correction families are built on"
  - phase: 03 (plan 03)
    provides: "FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE config constant, consumed by both estimator registries in this plan"
provides:
  - "backend/forecast_correction_models.py: WIND_CORRECTION_ESTIMATORS/COOLING_CORRECTION_ESTIMATORS registries, fit_wind_correction/predict_wind_correction (arm 3, u/v space, both pooling strategies), fit_cooling_correction/predict_cooling_correction/apply_cooling_correction (arm 4, both target parameterizations, through the q_conv_override seam), select_wind_configuration/select_cooling_configuration (validation-only selectors returning winner + full score table)"
  - "backend/forecast_training.py: additive, default-preserving horizon_minutes parameter on build_training_matrix, gated by a golden capture taken before the edit -- unblocks arm 5's 24-hour reference-model refit"
  - "backend/tests/forecast_training_pre_horizon_param_golden.npz: pre-edit golden capture of build_training_matrix's default-path output"
affects: [03-06 (seven-arm held-out comparison wires these correction families and the horizon param into forecast_experiment.py), 03-07 (decision record cites this plan's pooling/target selection evidence)]

# Actuals (#2632)
actuals:
  tokens: 17400
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Correction-model result objects (WindCorrectionModel/CoolingCorrectionModel) carry their own ordered feature-name list so predict_* can never silently reorder columns -- extends forecast_training.CANDIDATE_ESTIMATORS's zero-argument-factory convention to a fit/predict pair with state"
    - "Validation-only selector shape: select_*_configuration(train_frame, val_frame, geometry) -> {winner, winner_key, scores} -- fits every open combination on train, scores every combination on validation by ampacity MAE, and returns the full table so a losing option's evidence is never discarded"
    - "Arm 4's target-parameterization contrast (level vs. scale-free log-ratio) is demonstrated with a tree-based estimator specifically, because a linear model can accidentally extrapolate a roughly-correct scale through its own coefficient on the forecast-term feature, while a tree's bounded extrapolation makes the level target's lack of scale-freeness concrete"
    - "Additive, default-preserving parameter appended LAST on a function with existing positional-only call sites, gated by an exact-equality (np.array_equal) golden-capture test -- the same pattern Plan 03-02 used twice, applied a third time to forecast_training.build_training_matrix"

key-files:
  created:
    - backend/forecast_correction_models.py
    - backend/tests/forecast_correction_models_test.py
    - backend/tests/forecast_training_pre_horizon_param_golden.npz
  modified:
    - backend/forecast_training.py
    - backend/tests/forecast_training_test.py

key-decisions:
  - "Corrected the plan's own row-count example: the <behavior> block claimed the 1440-minute horizon produces '24 fewer rows' than the 60-minute default. Verified this is mathematically 23 fewer (not 24) for this already-shipped build_ml_features/build_training_matrix pair, because the 60-minute default path already drops one of the same trailing rows the 24-hour path drops -- counting it twice when comparing the two horizons double-counts it. Wrote the test to assert the verified '23 fewer' invariant instead of the plan's unverified '24 fewer' claim, per this task's own critical_reminder to verify the horizon/lag assumption explicitly rather than trust it."
  - "fit_cooling_correction/predict_cooling_correction take a required keyword-only conductor parameter, not explicitly spelled out in the plan's abbreviated signature blurb (fit_cooling_correction(train_frame, estimator_factory, *, target)). Necessary because the action item requires the function to call thermal_model.convective_heat_loss internally (to compute the forecast's, truth's, and anchor's own convective terms from raw air-temp/perpendicular-wind columns), which structurally requires a conductor object; only select_cooling_configuration's given geometry parameter can supply it. No acceptance criterion or automated <verify> check enumerates fit_cooling_correction's exact parameter list, so this is a design completion, not a deviation from a locked contract."
  - "LinearRegression entries in both estimator registries receive no random_state argument -- sklearn's LinearRegression has no stochastic component and accepts no such keyword. The config-backed random state (FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE) is applied only to the GradientBoostingRegressor entries, mirroring forecast_training.CANDIDATE_ESTIMATORS's own convention of seeding only its stochastic entries."
  - "Wind/cooling correction frame contracts (fcst_*/anchor_*/truth_* column names) are this module's own invention, not dictated by forecast_experiment.py (which this plan does not touch). Documented in each function's docstring; Plan 03-06 (wiring these families into the harness) will need to shape forecast_experiment.py's own frame to match, or add a small adapter -- flagged in Next Phase Readiness below."

patterns-established:
  - "A tree-based estimator (GradientBoostingRegressor), not a linear one, is the estimator that makes a scale-invariance claim testable -- a linear model can mask a lack of scale-freeness by learning a proportional coefficient on a same-scale input feature, while a tree's inability to extrapolate past its training target range exposes the difference directly."

requirements-completed: [D-02, D-03, D-04]

coverage:
  - id: D1
    description: "build_training_matrix gains an additive, default-preserving horizon_minutes parameter; the default path is proven bit-identical (np.array_equal) to a golden capture taken from the unmodified source before the edit; a 1440-minute horizon shifts the target index by exactly 24 hours on every row; both production call sites remain single-positional"
    requirement: D-03
    verification:
      - kind: unit
        ref: "backend/tests/forecast_training_test.py::test_build_training_matrix_default_path_is_bit_identical_to_pre_horizon_param_golden"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_training_test.py::test_build_training_matrix_1440_minute_horizon_shifts_target_by_exactly_24_hours"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_training_test.py::test_build_training_matrix_non_whole_multiple_horizon_raises_and_names_value"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_training_test.py::test_build_training_matrix_production_call_sites_remain_single_positional"
        status: pass
    human_judgment: false
  - id: D2
    description: "The wind-correction family (arm 3) fits and predicts entirely in u/v vector space via wind_vector.to_uv/from_uv, recovers a known constant vector offset on held-out rows, leaves a perfect forecast essentially unchanged, and is proven correct across the 0/360 wrap by a dedicated straddling test"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_wind_correction_recovers_known_vector_offset_on_held_out_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_wind_correction_leaves_perfect_forecast_essentially_unchanged"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_wind_correction_treats_359_and_1_as_two_degrees_apart_not_358"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_wind_correction_predicted_direction_is_always_in_half_open_circle"
        status: pass
    human_judgment: false
  - id: D3
    description: "Both wind-correction pooling strategies (pooled with an endpoint indicator, per-city) are implemented; select_wind_configuration fits every combination on train rows, scores each on validation rows by ampacity MAE, and returns the winner plus the full score table; its signature accepts only train and validation frames"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_fit_wind_correction_per_city_produces_one_model_pair_per_city"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_fit_wind_correction_pooled_adds_endpoint_indicator_feature"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_select_wind_configuration_returns_winner_and_full_score_table"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_select_wind_configuration_signature_has_no_test_frame_param"
        status: pass
    human_judgment: false
  - id: D4
    description: "The cooling-correction family (arm 4) targets the convective term through the proven q_conv_override seam in both a level and a scale-free log-ratio parameterization, recovers a known constant factor on held-out rows, and reproduces the raw-forecast ampacity exactly when the override equals the forecast's own term"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_cooling_correction_recovers_known_constant_factor_on_held_out_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_cooling_correction_override_with_forecast_own_term_reproduces_raw_ampacity_exactly"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_log_ratio_generalizes_across_a_rescaled_term_but_level_does_not"
        status: pass
    human_judgment: false
  - id: D5
    description: "predict_cooling_correction refuses a non-positive predicted/recovered convective term (fit- and predict-time domain guards for the log-ratio's undefined-ratio case), naming the offending row count rather than clamping or dropping; select_cooling_configuration's signature accepts only train and validation frames"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_predict_cooling_correction_rejects_non_positive_predicted_term"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_fit_cooling_correction_log_ratio_raises_on_non_positive_forecast_term"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_correction_models_test.py::test_select_cooling_configuration_signature_has_no_test_frame_param"
        status: pass
    human_judgment: false

duration: ~31min
completed: 2026-09-29
status: complete
---

# Phase 3 Plan 5: ML Correction Families (Arms 3/4) and the Arm-5 Horizon Seam Summary

**`backend/forecast_correction_models.py` landed both ML correction families as standalone, independently testable units -- u/v-space wind correction with both pooling strategies, convective-term correction through the `q_conv_override` seam with both target parameterizations -- plus an additive `horizon_minutes` parameter on `build_training_matrix` gated by a golden capture, unblocking arm 5's 24-hour refit.**

## Performance

- **Duration:** ~31 min
- **Started:** 2026-09-29T23:20:00-05:00
- **Completed:** 2026-09-29T23:51:28-05:00
- **Tasks:** 3
- **Files modified:** 5 (2 created source/module files, 1 created golden fixture, 2 modified test/source files)

## Accomplishments

- **Task 1 -- arm 5's horizon seam:** `build_training_matrix` gained an additive `horizon_minutes=None` parameter, appended last. The default path (`None` resolves to `config.FORECAST_HORIZON_MINUTES`) is proven bit-identical (`np.array_equal`, no tolerance) to a golden capture (`forecast_training_pre_horizon_param_golden.npz`) taken from the unmodified source and committed strictly before the source edit. At `horizon_minutes=1440`, every row's target index is exactly 24 hours after its feature index -- the direct refutation of RESEARCH.md Pitfall 4's silent-one-row-shift failure mode. Both production call sites (`main`, `_run_bakeoff`) remain single-positional; no global constant is mutated anywhere.
- **Task 2 -- arm 3, the wind-correction family:** `fit_wind_correction`/`predict_wind_correction` fit and predict entirely in u/v vector space via `wind_vector.to_uv`/`from_uv`, never on a wrapping direction in degrees. Both pooling strategies (pooled-with-endpoint-indicator, per-city) are implemented; `select_wind_configuration` scores every (estimator, pooling) combination on validation rows by ampacity MAE and returns the winner plus the full score table. A dedicated wrap-straddling test (forecast=359 deg, truth=1 deg) proves the correction treats the pair as 2 degrees apart, not 358.
- **Task 3 -- arm 4, the cooling-correction family:** `fit_cooling_correction`/`predict_cooling_correction`/`apply_cooling_correction` target the convective heat-loss term through the SAME extracted `thermal_model.convective_heat_loss` function the physics core uses, substituting the corrected term via `ieee738_ampacity`'s `q_conv_override` seam -- never reimplementing the heat balance. Both target parameterizations (level, scale-free log-ratio) are implemented; a predicted non-positive term is refused (fail-loud, matching the provider layer's null discipline) rather than clamped. `select_cooling_configuration` mirrors the wind selector's shape.
- **Illustrative selection run** (synthetic representative data -- see "Selection Evidence" below; real corridor data is Plan 03-06's job): wind selector chose `LinearRegression + pooled`; cooling selector chose `GradientBoostingRegressor + log_ratio`.

## Task Commits

Each task was committed atomically (Task 1 split into its required golden-fixture-first pair):

1. **Task 1 golden capture** - `ce3ee4d` (test)
2. **Task 1: additive horizon_minutes parameter** - `a307512` (feat)
3. **Task 2: wind correction family (arm 3)** - `6ef8ae2` (feat)
4. **Task 3: cooling correction family (arm 4)** - `f39e6b1` (feat)

## Files Created/Modified

- `backend/forecast_correction_models.py` - new module: both ML correction families, estimator registries, validation-only selectors
- `backend/tests/forecast_correction_models_test.py` - 21 tests covering both families' `<behavior>` blocks
- `backend/forecast_training.py` - additive `horizon_minutes=None` parameter on `build_training_matrix`
- `backend/tests/forecast_training_test.py` - 5 new tests: golden equality gate, 24-hour index shift, corrected row-count invariant, non-whole-multiple guard, call-site regression check
- `backend/tests/forecast_training_pre_horizon_param_golden.npz` - golden capture from the unmodified source

## Decisions Made

See `key-decisions` in frontmatter for full detail. Summary:
1. Corrected the plan's own "24 fewer rows" row-count claim to the mathematically verified "23 fewer" (double-counting the row the 60-minute default already drops).
2. Added a required `conductor` keyword to `fit_cooling_correction`/`predict_cooling_correction`, needed for the function to call `convective_heat_loss` internally as instructed; not locked by any acceptance criterion.
3. `LinearRegression` registry entries receive no `random_state` (the estimator has none); the config-backed random state applies only to the stochastic `GradientBoostingRegressor` entries.
4. This module's frame column contracts (`fcst_*`/`anchor_*`/`truth_*`) are this plan's own invention since `forecast_experiment.py` is out of scope; Plan 03-06 will need to align or adapt.

## Selection Evidence (illustrative, synthetic data)

This plan is deliberately decoupled from `forecast_experiment.py` (Plan 03-04's file, running in parallel this wave) and does not fetch or read real corridor data. To close `03-CONTEXT.md`'s two open questions with *some* measured evidence now, both selectors were run once against representative synthetic data built the same way this plan's own test fixtures are built (`_synthetic_wind_frame`/`_synthetic_cooling_frame`, 400 rows, 280/120 train/validation split). **These numbers are illustrative, not the phase's final answer** -- Plan 03-06 will re-run both selectors against the real 24-hour Previous-Runs corridor data and its own numbers supersede these.

**Wind (arm 3) pooling:**

| Configuration | MAE (ampacity, synthetic) |
|---|---|
| `LinearRegression + pooled` (winner) | 22.60 |
| `LinearRegression + per_city` | 23.52 |
| `GradientBoostingRegressor + pooled` | 30.33 |
| `GradientBoostingRegressor + per_city` | 33.29 |

**Cooling (arm 4) target parameterization:**

| Configuration | MAE (ampacity, synthetic) |
|---|---|
| `GradientBoostingRegressor + log_ratio` (winner) | 34.54 |
| `LinearRegression + level` | 36.01 |
| `LinearRegression + log_ratio` | 37.18 |
| `GradientBoostingRegressor + level` | 38.31 |

The losing options are retained above (not deleted) per the plan's own instruction to report what was tried, not only what won.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in plan's own illustrative arithmetic] Corrected the "24 fewer rows" row-count claim to "23 fewer"**
- **Found during:** Task 1, writing the row-count test
- **Issue:** The plan's `<behavior>` block asserts that a 1440-minute horizon produces a row count "24 fewer" than the 60-minute default, reasoning that "24 more trailing rows have no target." Verified directly against the already-shipped `build_ml_features`/`build_training_matrix` pair: because feature validity never has a trailing edge (lag/rolling-mean features are causal-only), the ONLY rows ever dropped at the trailing edge are rows lacking a target. At the 60-minute default, exactly 1 trailing row lacks a target (the frame's own last row). At 1440 minutes, exactly 24 trailing rows lack a target. The DIFFERENCE between "24 rows now lack a target" and "1 row already lacked a target" is 23, not 24 -- the naive framing double-counts the single row the 60-minute default already excludes. This is an invariant of the shipped code's causal feature construction, not fixable by choosing a different frame.
- **Fix:** Wrote the row-count test (`test_build_training_matrix_1440_minute_horizon_drops_exactly_23_more_rows_than_default`) to assert the verified relationship (`len(X_60) - len(X_1440) == 23`), with an inline docstring explaining the double-counting error in the naive "24" framing. No production code was affected -- this is purely a test-assertion correction, applying this task's own `critical_reminder` to verify the horizon/lag assumption explicitly rather than trust it.
- **Files modified:** `backend/tests/forecast_training_test.py`
- **Verification:** Test passes; the underlying relationship was hand-verified via a standalone interpreter session before writing the test (see conversation transcript).
- **Committed in:** `a307512` (Task 1 source+test commit)

---

**Total deviations:** 1 auto-fixed (Rule 1, a plan-text arithmetic correction affecting only a new test's own assertion, not production code). **Impact:** Zero scope creep -- the plan's own `<verify>` block does not hard-code the "24" number in any automated gate, only in prose/acceptance-criteria illustration.

## Issues Encountered

**Worktree lacked its own `.venv`.** This git worktree was created without its own Python virtual environment (untracked, gitignored `.venv/` directories are not shared across worktrees by git). Symlinked `.venv` in this worktree to the main repository's `.venv` (`/Users/aphan/Senior_Design/.venv`) so the plan's `.venv/bin/python3`-prefixed `<verify>` commands could run unchanged. This is a local, untracked, gitignored convenience symlink -- it introduces no git-visible change and was not committed (git status confirmed clean after creation).

**Pre-existing, out-of-scope test failures (not fixed):** the same 23 `backend/tests/corridor_discretization_test.py` failures already logged in `.planning/WINDOWS.md` (from Plan 03-02) are still present and unchanged by this plan. Full-suite count after this plan's three commits: 586 passed / 23 failed -- the failure count never changed; only new tests were added.

## Known Stubs

None -- every function this plan touches is fully implemented and tested against synthetic data; the "Selection Evidence" numbers above are explicitly labeled illustrative/synthetic (not a stub -- Plan 03-06's real-data run is the intended next step, not a gap in this plan's own deliverable).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Ready for Plan 03-06 (leakage probe + seven-arm held-out comparison):** `backend/forecast_correction_models.py` exports everything named in this plan's frontmatter (`WIND_CORRECTION_ESTIMATORS`, `COOLING_CORRECTION_ESTIMATORS`, `fit_wind_correction`, `predict_wind_correction`, `fit_cooling_correction`, `predict_cooling_correction`, `apply_cooling_correction`, `select_wind_configuration`, `select_cooling_configuration`). Plan 03-06 will need to shape `forecast_experiment.py`'s own anchored-pair frame to match this module's `fcst_*`/`anchor_*`/`truth_*` column contract (documented in each function's docstring), or add a small adapter -- this module deliberately does not import or depend on `forecast_experiment.py`'s own column names.
- **Ready for Plan 03-06's arm-5 refit:** `build_training_matrix(frame, horizon_minutes=1440)` is available and proven bit-identical at its default; the refit-from-scratch, train+validation-only discipline (D-02 approach 5) is unaffected by this plan (this plan touches no persisted-model-loading code path).
- **The two `03-CONTEXT.md` open questions (arm 3 pooling, arm 4 target parameterization) have a first illustrative measurement** (synthetic data, see Selection Evidence) but are NOT yet closed with real evidence -- Plan 03-06 must re-run both selectors on the real 24-hour Previous-Runs corridor data before Plan 03-07's decision record cites a final answer.
- **No blockers.**

## Self-Check: PASSED

- `backend/forecast_correction_models.py` (contains `WIND_CORRECTION_ESTIMATORS`, `COOLING_CORRECTION_ESTIMATORS`, all 8 exported names) — FOUND
- `backend/tests/forecast_correction_models_test.py` — FOUND (21 tests, verified passing)
- `backend/forecast_training.py` (contains `horizon_minutes`) — FOUND
- `backend/tests/forecast_training_test.py` — FOUND (19 tests, verified passing)
- `backend/tests/forecast_training_pre_horizon_param_golden.npz` — FOUND
- Commit `ce3ee4d` — FOUND in `git log --oneline --all`
- Commit `a307512` — FOUND
- Commit `6ef8ae2` — FOUND
- Commit `f39e6b1` — FOUND
- `backend/forecast_experiment.py`, `backend/tests/forecast_experiment_test.py`, `backend/config.py`, `backend/thermal_model.py`, `backend/ampacity_forecast.py`, `ACKNOWLEDGEMENTS.md`, `backend/anomaly_detector.py`, `backend/DLRSafetyMonitor.py` carry zero diff from base (`7f93271`) — CONFIRMED
- Full suite: 586 passed, 23 failed (unchanged pre-existing `corridor_discretization_test.py` baseline per `.planning/WINDOWS.md`) — CONFIRMED

---
*Phase: 03-ampacity-forecast-correction-experiment-compare-persistence*
*Plan: 05*
*Completed: 2026-09-29*
