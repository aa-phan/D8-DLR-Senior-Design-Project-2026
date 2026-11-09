---
phase: 01-land-pr-7
plan: 03
subsystem: testing
tags: [pytest, offline-tests, city-pipeline, fallback-latch, forecast-band]

requires:
  - phase: 01-land-pr-7
    provides: "01-01 offline fixtures (_no_network, _offline_env, _station_at) copied from backfill_archive_test.py"
provides:
  - "backend/tests/city_pipeline_test.py: 9 test functions (10 collected) for run_city_pipeline"
affects: [01-04, 02-data-cleaning]

actuals:
  tokens: 3300
  tasks: 2
  commits: 2
plan_head_before: 7acbf5b4cc5db29868e7f7111fd3fbfc069d24ae
plan_head_after: 17bfa456ed9b5ee41728c3d6ec3962db774def61

tech-stack:
  added: []
  patterns:
    - "_spy_detector / _spy_forecast: stand-ins installed with monkeypatch that record what run_city_pipeline hands the detector and the forecaster"
    - "_run(tmp_path, **kw): archive=False, tmp_path archive, injected fetcher; kwargs override"

key-files:
  created:
    - backend/tests/city_pipeline_test.py
  modified: []

key-decisions:
  - "No backend module, frozen module or workflow was touched; the plan adds one test file"
  - "Fixtures copied from backfill_archive_test.py (no conftest.py), per repo convention"

requirements-completed: []  # LAND-03 is shared with later plans; requirements.ready-ids reported 0/1 ready

coverage:
  - id: D1
    description: "Fallback-row exclusion (bool and any-case text) from the history seen by both forecast and detector; per-city history read; usable_history_rows count"
    requirement: "LAND-03"
    verification:
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_fallback_rows_are_left_out_of_the_history_the_forecast_and_detector_see"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_fallback_flag_is_matched_as_case_insensitive_text"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_history_is_read_for_this_city_only"
        status: pass
    human_judgment: false
  - id: D2
    description: "Forecast exception handling (None forecast, one WARNING, city still rated) and the cold-start path with the real detector"
    requirement: "LAND-03"
    verification:
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_forecast_exception_leaves_no_forecast_and_the_city_still_rates"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_cold_start_with_no_archive_rates_without_a_forecast"
        status: pass
    human_judgment: false
  - id: D3
    description: "Degenerate-band rule (zero width and inverted not passed to detector, positive width passed through), pipeline key shape, rate_city argument wiring"
    requirement: "LAND-03"
    verification:
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_zero_width_band_is_reported_but_not_given_to_the_detector"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_positive_width_band_is_given_to_the_detector"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_pipeline_key_reports_history_forecast_and_detector"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_rate_city_gets_the_detector_and_the_callers_arguments"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-10-20
status: complete
---

# Phase 1 Plan 03: City Pipeline Tests Summary

**Offline pytest coverage of `run_city_pipeline`: fallback-row exclusion that blocks the static-rating latch, zero-width forecast band handling, forecast-failure resilience, cold start, and the exact `pipeline` key shape.**

## Performance

- **Duration:** ~8 min
- **Completed:** 2026-10-20T00:27:00Z
- **Tasks:** 2
- **Files modified:** 1 (created)

## Accomplishments
- Fallback rows (bool, `"TRUE"`, `"True"`) are shown to be dropped before both `forecast_ampacity` and `AnomalyDetector.for_city`, which receive the very same frame; `history_rows` counts all, `usable_history_rows` the remainder.
- The history is read for the requested city only.
- A `forecast_ampacity` exception gives `forecast None`, `forecast_used_by_g6 False`, exactly one WARNING naming method and city, and the city is still rated.
- Cold start (no archive) with the real detector reports `detector_signal == "cold_start"`.
- Zero-width and inverted bands are reported in `pipeline["forecast"]` but not passed to the detector; a positive band is passed through by identity.
- `pipeline` and `pipeline["forecast"]` key sets and types pinned; `rate_city` receives the built detector and the caller's arguments unchanged.

## Task Commits

1. **Task 1: history filtering, city scoping, forecast failure, cold start** - `5807ac2` (test)
2. **Task 2: degenerate band, positive band, pipeline key, rate_city wiring** - `17bfa45` (test)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `backend/tests/city_pipeline_test.py` - 9 test functions (10 collected, one parametrized), offline, tmp_path only

## Decisions Made
None - followed plan as specified.

## Deviations from Plan

None - plan executed exactly as written.

## Discrepancies

none. The code in `backend/city_pipeline.py` matched the plan's description in every tested respect.

## Issues Encountered
None

## Verification
- `pytest -q -p no:cacheprovider backend/tests/city_pipeline_test.py`: 10 passed; `--collect-only`: 10 tests collected.
- No file under `data/` or `outputs/` changed during the run.
- `git diff 5efe97d HEAD -- backend ':(exclude)backend/tests'` is empty (no backend module changed).
- No test asserts a rating value.

## Known Stubs
None.

## Threat Flags
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Ready for 01-04 (dlr_orchestrator tests). LAND-03 is shared with later plans and stays unmarked until `requirements.ready-ids` reports it ready.

## Self-Check: PASSED
- `backend/tests/city_pipeline_test.py` exists; commits `5807ac2` and `17bfa45` are ancestors of HEAD.

---
*Phase: 01-land-pr-7*
*Completed: 2026-10-20*
