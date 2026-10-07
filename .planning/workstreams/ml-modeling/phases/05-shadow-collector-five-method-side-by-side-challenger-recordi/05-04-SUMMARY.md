---
phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi
plan: 04
subsystem: data-science
tags: [shadow-collector, reference-ml-refit, mlp, truth-proxy, decision-time]

# Dependency graph
requires:
  - phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi
    provides: "The five-candidate orchestration, shared fetch, real persistence_24h, and the honest reference_ml_refit_24h unavailable stub (05-02)"
provides:
  - "Two real, committed reference_ml_refit_24h MLP artifacts (both corridors), fit offline via fit_fitted_arms's exact arm-5 recipe on the pinned train-plus-validation window"
  - "fetch_live_truth_proxy_series: a live, decision-time-available, corridor-level 7-hour truth-proxy series built from near-real-time TCEQ/Synoptic station observations, through the same thermal_model physics and forecast_training.corridor_weakest_link reduction training used"
  - "ReferenceRefit24hShadowMethod's real predict path, replacing 05-02's honest unavailable stub without changing its name or callers' expectations"
affects: [05-05]

# Actuals (#2632)
actuals:
  tokens: 10091
  tasks: 3
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Offline-fit-then-commit: forecast_shadow_fit_reference_refit.py is a standalone, __main__-driven script, never imported by the runtime collector, mirroring forecast_training.py's own convention -- its sole output is a .joblib artifact under data/shadow/models/ (the one directory deliberately carved out of .gitignore for exactly this)"
    - "Live truth-proxy reconstruction: a short (7-hour) corridor-level series built from live station observations, run through the SAME physics + weakest-link reduction used for training truth, reused as the feature-builder's own input shape rather than a second feature contract"
    - "First-gap-stops, never accumulates: fetch_live_truth_proxy_series raises StaleOrMissingDataError on the FIRST missing/null required hour it finds (never interpolates, pads, or continues scanning for more gaps before reporting)"

key-files:
  created:
    - backend/forecast_shadow_fit_reference_refit.py
    - backend/tests/forecast_shadow_fit_reference_refit_test.py
    - data/shadow/models/reference_ml_refit_24h_AUSTIN_CORPUS_CHRISTI.joblib
    - data/shadow/models/reference_ml_refit_24h_MIDLAND_EL_PASO.joblib
  modified:
    - backend/forecast_shadow_pipeline.py
    - backend/forecast_shadow_demo.py
    - backend/tests/forecast_shadow_pipeline_test.py
    - backend/tests/forecast_shadow_demo_test.py

key-decisions:
  - "ReferenceRefit24hShadowMethod.compute's signature grew a required anchor_time parameter (the live truth-proxy window's anchor) -- the one call site outside this plan's own files_modified list, forecast_shadow_demo.py's run_once_all_methods, was updated with a one-line fix (passing the already-in-scope decision_time) since the signature change directly breaks it (Rule 3: auto-fix blocking issue caused by this plan's own change)."
  - "Per-city/per-hour validation iterates city-then-hour (not hour-then-city): the first missing/null hour found for the first city checked is the one named in the raised StaleOrMissingDataError. The plan's own <behavior> spec requires naming SOME specific hour+city on the first gap, not a particular iteration order, so this is a compliant, deterministic choice."
  - "fetch_live_truth_proxy_series uses CORRIDOR_ENDPOINTS's own tuple order (not sorted(cities)) for city-A/city-B assignment into corridor_weakest_link, matching CorridorWindCorrectionMethod's own convention in the same file, rather than _corridor_reduce_per_city's sorted() convention (that sorted choice was explicit to 05-02's own per-city-reduced methods, not a project-wide rule)."

requirements-completed: [D-01, D-03, D-04]

coverage:
  - id: D1
    description: "A persisted reference_ml_refit_24h MLP artifact exists and is committed for both corridors, fit via forecast_experiment's exact arm-5 recipe, never touching ampacity_forecast's 60-minute production artifact or cache"
    requirement: "D-03"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_fit_reference_refit_test.py#test_fit_and_save_calls_the_exact_arm5_recipe_in_order"
        status: pass
      - kind: other
        ref: "real offline fit for both corridors: AUSTIN_CORPUS_CHRISTI 18834 rows, MIDLAND_EL_PASO 18834 rows; both artifacts committed and loadable"
        status: pass
    human_judgment: false
  - id: D2
    description: "The live reference_ml_refit_24h prediction is computed from a genuinely decision-time-available truth-proxy series (live station observations through the same physics/weakest-link reduction), never reanalysis/archive data; any gap reports unavailable naming the specific missing hour/city, never interpolated"
    requirement: "D-04"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_fetch_live_truth_proxy_series_raises_naming_the_missing_hour_and_city"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_fetch_live_truth_proxy_series_treats_a_null_required_field_like_a_missing_hour"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_reference_refit_24h_compute_predicts_ok_from_a_complete_synthetic_window"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_reference_refit_24h_compute_loads_and_predicts_from_the_real_persisted_artifact"
        status: pass
    human_judgment: false
  - id: D3
    description: "ReferenceRefit24hShadowMethod never fits/retrains an estimator at live-prediction time -- it only ever loads and predicts"
    requirement: "D-01"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_reference_refit_24h_compute_never_calls_fit_corridor_model"
        status: pass
    human_judgment: false
  - id: D4
    description: "One real live cycle shows reference_ml_refit_24h producing either a plausible positive ampacity or an honest unavailable reason that is NOT 'no persisted artifact'"
    verification:
      - kind: other
        ref: "live call, AUSTIN_CORPUS_CHRISTI, 2026-10-07T21:47:41Z anchor_time -- status=unavailable, reason names AUSTIN and a specific missing solar_radiation hour (see narrative below); REFERENCE_REFIT_LIVE_RUN_OK printed"
        status: pass
    human_judgment: false

duration: ~45 min
completed: 2026-10-07
status: complete
---

# Phase 5 Plan 4: Reference-Refit-24h Artifact, Live Truth-Proxy Reconstruction, Real Predict Path Summary

**Both corridors now have a real, committed `reference_ml_refit_24h` MLP artifact (18,834 training rows each) and a real live predict path built from a decision-time-available, hourly truth-proxy series reconstructed from live TCEQ/Synoptic station observations -- replacing 05-02's honest "no persisted artifact" stub.**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-10-07
- **Tasks:** 3/3 completed
- **Files modified:** 4 modified, 4 created (2 code/test files, 2 `.joblib` artifacts)

## Accomplishments

- `backend/forecast_shadow_fit_reference_refit.py` fits and persists `reference_ml_refit_24h`'s MLP estimator for both corridors, reusing `forecast_experiment.fit_fitted_arms`'s exact arm-5 recipe (`_stacked_pair_frame` → `_arm5_truth_frame` → `forecast_training.build_training_matrix(horizon_minutes=1440)` → `fit_corridor_model` with `CANDIDATE_ESTIMATORS["MLPRegressor"]`) on the pinned train-plus-validation window (`forecast_experiment_audit.FROZEN_WINDOW_START` through the day before `FROZEN_TEST_SPLIT_START`) -- never the frozen test split, never `ampacity_forecast`'s production model/cache.
- Both real artifacts are committed under `data/shadow/models/` (the deliberately-not-gitignored carve-out): `reference_ml_refit_24h_AUSTIN_CORPUS_CHRISTI.joblib` fit on 18,834 rows, `reference_ml_refit_24h_MIDLAND_EL_PASO.joblib` fit on 18,834 rows. Both load successfully and expose `.predict`.
- `fetch_live_truth_proxy_series` builds a real, decision-time-available, hourly, corridor-level 7-row truth-proxy series (`anchor_time - 6h` through `anchor_time`) from live TCEQ (Synoptic-fallback) station observations for both endpoint cities, through the SAME `thermal_model.perpendicular_wind`/`ieee738_ampacity` physics and the SAME `forecast_training.corridor_weakest_link` reduction training used -- never reanalysis/archive data. Any missing or null required field at any of the 7 hours, for either city, raises `StaleOrMissingDataError` naming the specific corridor/city/hour -- never interpolated, padded, or backfilled.
- `ReferenceRefit24hShadowMethod.compute(corridor, anchor_time)` now loads the persisted artifact, builds its live feature row via `ampacity_forecast.build_ml_features` (the SAME feature builder the offline fit used) on the 7-row truth-proxy series, and predicts for real from the last (fully-determined) row -- replacing 05-02's stub body. `per_city_ampacity_amps` is explicitly `None` with a named `per_city_not_applicable_reason` (arm 5 is corridor-level-native, by design, at both training and inference time).
- One real live call against live TCEQ data for `AUSTIN_CORPUS_CHRISTI` completed without raising, reporting `status="unavailable"` with a specifically-named gap (AUSTIN's `solar_radiation` field at one required hour) -- the exact, expected, acceptable live-data limitation this task's own precondition flagged (TCEQ CAMS stations may not reliably report solar radiation), not a code defect.
- Every frozen Phase 1/3/4 module (`forecast_experiment.py`, `forecast_training.py`, `forecast_experiment_audit.py`, `ampacity_forecast.py`, `thermal_model.py`, `weather_provider.py`) confirmed to carry zero git diff throughout.

## Task Commits

1. **Task 1: Fit and commit the reference_ml_refit_24h artifact for both corridors, offline, reusing the exact arm-5 recipe** - `555411a` (feat) -- 4 new network-free tests, all pass; real offline fit for both corridors (18,834 rows each), artifacts committed and loadable.
2. **Task 2: Live truth-proxy reconstruction and the real reference_ml_refit_24h predict path** - `935f588` (feat) -- 8 new tests in `forecast_shadow_pipeline_test.py` + the existing stub test updated for the new `compute(corridor, anchor_time)` signature (66 total pass in that file); `forecast_shadow_demo.py`'s one call site updated (1-line fix); its own test updated to reflect the real `ok` path (9 pass).
3. **Task 3: One real live cycle exercising the real reference_ml_refit_24h path** - no separate commit (an isolated, direct `compute()` call that returns a `ShadowPrediction` object; it does not write to the collector's append-only log, since the plan deliberately bypasses `run_once_all_methods`/`log_cycle_predictions` to isolate this one candidate's real-data behavior). Its result is recorded in this SUMMARY and committed as part of this plan's closing docs commit.

**Plan metadata:** recorded in the closing docs commit (see final commit for this plan).

## Files Created/Modified

- `backend/forecast_shadow_fit_reference_refit.py` (new) - `fit_and_save(corridor)`, `main()`; the one-time offline fit+commit script.
- `backend/tests/forecast_shadow_fit_reference_refit_test.py` (new) - 4 network-free tests (call order, loadability, pinned window dates, `main()`'s per-corridor loop).
- `data/shadow/models/reference_ml_refit_24h_AUSTIN_CORPUS_CHRISTI.joblib` (new) - real persisted MLP, fit on 18,834 rows.
- `data/shadow/models/reference_ml_refit_24h_MIDLAND_EL_PASO.joblib` (new) - real persisted MLP, fit on 18,834 rows.
- `backend/forecast_shadow_pipeline.py` - `_TRUTH_PROXY_HOUR_TOLERANCE`, `_select_hour_row`, `fetch_live_truth_proxy_series`, `_PER_CITY_NOT_APPLICABLE_REASON`; `ReferenceRefit24hShadowMethod.compute`'s body replaced with the real predict path (signature grew `anchor_time`); `ampacity_forecast` added to imports.
- `backend/forecast_shadow_demo.py` - one-line call-site fix: `ReferenceRefit24hShadowMethod().compute(corridor, decision_time)`.
- `backend/tests/forecast_shadow_pipeline_test.py` - 8 new tests (7-row shape/ordering, missing-hour error, null-field error, complete-window `ok` prediction via a fake estimator, zero `fit_corridor_model` calls, real-artifact integration) + the stub test renamed/updated for the new signature.
- `backend/tests/forecast_shadow_demo_test.py` - the clean-run test replaced to mock a complete truth-proxy window and assert `reference_ml_refit_24h` now reaches `status="ok"` with the real artifact, rather than the 05-02-era permanent "unavailable" expectation.

## Decisions Made

- `ReferenceRefit24hShadowMethod.compute`'s signature grew a required `anchor_time` parameter. `forecast_shadow_demo.py`'s `run_once_all_methods` (not in this plan's own `files_modified`) calls this method at one site and was updated with a minimal one-line fix (passing the already-in-scope `decision_time`) since the signature change directly breaks that call site -- Rule 3 (auto-fix blocking issue caused by this plan's own change), not scope creep.
- Per-city/per-hour validation in `fetch_live_truth_proxy_series` iterates city-then-hour (checks all 7 hours for city A before moving to city B), so the first `StaleOrMissingDataError` raised names whichever city/hour combination is checked first in that order. The plan's `<behavior>` spec requires the error to name SOME specific hour+city on the first gap found, not a particular iteration order -- this is a compliant, deterministic choice, not an arbitrary one.
- City-A/city-B assignment into `corridor_weakest_link` uses `config.CORRIDOR_ENDPOINTS[corridor]`'s own tuple order, matching `CorridorWindCorrectionMethod`'s own convention in the same file, rather than `_corridor_reduce_per_city`'s `sorted()` convention (that `sorted()` choice was specific to 05-02's own per-city-reduced methods' instructions, not a project-wide rule this new function inherits).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated `forecast_shadow_demo.py`'s one call site for the new `compute` signature**
- **Found during:** Task 2 (replacing the stub body)
- **Issue:** `ReferenceRefit24hShadowMethod.compute` grew a required `anchor_time` parameter (needed to build the live truth-proxy window); the one existing caller, `forecast_shadow_demo.run_once_all_methods`, called `.compute(corridor)` with no second argument and would raise `TypeError` on every invocation after this plan's change.
- **Fix:** Changed the call to `.compute(corridor, decision_time)`, reusing the `decision_time` variable already in scope at that call site (the same value `Persistence24hShadowMethod.compute` already receives one line above).
- **Files modified:** `backend/forecast_shadow_demo.py` (1 line).
- **Verification:** `backend/tests/forecast_shadow_demo_test.py` (9/9 pass, including the updated clean-run test asserting `reference_ml_refit_24h` now reaches `status="ok"`).
- **Committed in:** `935f588` (Task 2 commit).

**2. [Rule 1 - Bug] Updated `forecast_shadow_demo_test.py`'s clean-run test, which issued a real network call after this plan's change**
- **Found during:** Task 2's full-suite regression check
- **Issue:** `test_run_once_all_methods_reports_reference_refit_as_unavailable_on_a_clean_run` (05-02-era) asserted the old stub's "no persisted artifact" message and did not mock `weather_provider.fetch_weather` for the new live truth-proxy path -- after this plan's change, running it made a REAL network call to TCEQ, violating this test file's own "network-free throughout" docstring guarantee, and its assertion on the exact stub-era reason string no longer held.
- **Fix:** Renamed and rewrote the test to mock a complete 7-hour truth-proxy window via `weather_provider.fetch_weather`, asserting `reference_ml_refit_24h` now reaches `status="ok"` with a real, finite ampacity -- proving the real artifact + real live path integration at the orchestration layer too, network-free.
- **Files modified:** `backend/tests/forecast_shadow_demo_test.py`.
- **Verification:** `backend/tests/forecast_shadow_demo_test.py` (9/9 pass).
- **Committed in:** `935f588` (Task 2 commit).

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug/regression caused by this plan's own signature change).
**Impact on plan:** Both auto-fixes were required consequences of changing `ReferenceRefit24hShadowMethod.compute`'s signature, as the plan itself instructs ("keep the existing `FileNotFoundError` handling... add the new truth-proxy-and-predict path below it"). No scope creep beyond the one call site and its own test.

## Issues Encountered

- A full `backend/tests/` regression run (857 passed, 23 failed) surfaced 23 pre-existing failures in `backend/tests/corridor_discretization_test.py`, entirely unrelated to this plan (that test file imports only `config`, `corridor_discretization`, `station_explorer` -- none of which this plan touches; `git log` shows no commit from this plan touching `corridor_discretization.py`). Logged to `.planning/workstreams/ml-modeling/phases/05-shadow-collector-five-method-side-by-side-challenger-recordi/deferred-items.md`, not fixed, per this plan's own scope boundary.
- The real live call for Task 3 reached `status="unavailable"` due to a missing `solar_radiation` field from TCEQ's CAMS station for AUSTIN -- this project's own `PROJECT.md` already documents that "TCEQ is wired for wind/temp/RH only in v1.1" (solar-radiation instrumentation is a separate, not-yet-pursued v2 item, WX-09). This is the exact, expected, acceptable live-data gap this task's own `<precondition>` flagged in advance ("CAMS air-quality stations may not reliably report `solar_radiation` -- an honest `status='unavailable'`... is an expected and acceptable outcome... not a defect to chase"), not a code bug. No fallback-at-the-field-level to Synoptic for `solar_radiation` was added, since the plan's own `<action>` scoped the live Synoptic fallback to `fetch_weather`'s own automatic exception/empty-response retry (the same mechanism `fetch_live_anchor_observation` relies on), not a second explicit per-field retry -- adding one would be new, unscoped behavior beyond what this task asked for.

## Live Cycle Result (Task 3)

One real, isolated call to `ReferenceRefit24hShadowMethod().compute('AUSTIN_CORPUS_CHRISTI', pd.Timestamp.now(tz='UTC'))` ran against live TCEQ/Synoptic endpoints at `anchor_time≈2026-10-07T21:47:41Z` (no mocking):

```
status=unavailable ampacity_amps=None
reason=fetch_live_truth_proxy_series: corridor 'AUSTIN_CORPUS_CHRISTI' city 'AUSTIN':
       null 'solar_radiation' at required hour 2026-10-07T15:47:41.348717+00:00
```

The call completed without raising (`compute` itself caught the gap into its own `status` field, exactly as designed). The reason names a specific hour, a specific city, and a specific missing field -- not a generic message -- satisfying this task's own acceptance criterion. This is NOT "no persisted artifact" (the artifact now exists and loads); it is a genuine, honestly-reported live-data limitation of the TCEQ CAMS network for solar radiation, consistent with `PROJECT.md`'s own documented TCEQ wind/temp/RH-only scope. The companion automated verification script printed `REFERENCE_REFIT_LIVE_RUN_OK unavailable`.

Per D-11, this result is reported strictly as operational completeness (the real path runs end to end and fails honestly, by name, when live data is incomplete) -- no claim is made about this candidate's accuracy or reliability relative to any other candidate; that question remains reserved for the Nov 1/Nov 24 fresh-basis confirmation protocol.

## User Setup Required

None - no external service configuration required. The real offline fit (Task 1) and the real live call (Task 3) both succeeded using this environment's existing network reachability to Open-Meteo (Archive + Previous-Runs) and TCEQ; no `SYNOPTIC_TOKEN` fallback was exercised in this plan's own runs.

## Next Phase Readiness

- `reference_ml_refit_24h` is no longer perpetually "no persisted artifact" for either corridor -- it now either produces a real prediction or an honestly, specifically-named live-data gap, exactly like the other four candidates.
- The `solar_radiation`-from-TCEQ gap observed in Task 3's live run is worth flagging to whoever operates this collector going forward: if TCEQ's CAMS network continues to not reliably report `solar_radiation` for AUSTIN (or any other endpoint city), `reference_ml_refit_24h` may report `unavailable` on a recurring basis in production shadow-collection cycles, independent of any code defect. This is observational information for the collector operator, not a blocker to this plan or to 05-05.
- 05-05 (next plan in this phase) can proceed with all five candidates now wired to real compute paths (or honestly-named unavailability) for both corridors.

---
*Phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi*
*Completed: 2026-10-07*

## Self-Check: PASSED

- `backend/forecast_shadow_fit_reference_refit.py` - FOUND
- `backend/tests/forecast_shadow_fit_reference_refit_test.py` - FOUND
- `data/shadow/models/reference_ml_refit_24h_AUSTIN_CORPUS_CHRISTI.joblib` - FOUND
- `data/shadow/models/reference_ml_refit_24h_MIDLAND_EL_PASO.joblib` - FOUND
- `backend/forecast_shadow_pipeline.py` - FOUND
- `backend/forecast_shadow_demo.py` - FOUND
- `backend/tests/forecast_shadow_pipeline_test.py` - FOUND
- `backend/tests/forecast_shadow_demo_test.py` - FOUND
- This SUMMARY.md - FOUND
- Commit `555411a` - FOUND in `git log --oneline --all`
- Commit `935f588` - FOUND in `git log --oneline --all`
