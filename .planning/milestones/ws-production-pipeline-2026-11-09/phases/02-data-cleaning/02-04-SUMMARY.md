---
phase: 02-data-cleaning
plan: 04
subsystem: data-cleaning
tags: [forecast, g6, gap-guard, hourly-slots, ml-lookback, policy-doc]
status: complete

requires:
  - phase: 02-data-cleaning
    provides: "02-03: report trailing_gap_slots, contiguous_tail_rows, missing_slots; after_gap marking; policy doc and its agreement test"
provides:
  - "backend/data_cleaning.py: forecast_gap_reason(report, forecast_method), MAX_TRAILING_GAP_SLOTS = 1, ML_LOOKBACK_ROWS = 7"
  - "backend/city_pipeline.py: a forecast built across too large a gap is reported but not given to G6 (INFO line, same handling as a zero-width band)"
  - "docs/data-science/decisions/data_cleaning.md: '## Forecast use across gaps (CLEAN-02)' and two new threshold rows"
affects: [03-real-data-validation, 04-postgres-writer]

actuals:
  tokens: 9000
  tasks: 2
  commits: 1
plan_head_before: 3739b4de0b7e6edbafe0e17e18e87ad3c3fc45de
plan_head_after: bdaf2b09e9ea713b0d886198e52ad9b158c02494

tech-stack:
  added: []
  patterns:
    - "A use rule is separate from a cleaning rule: forecast_gap_reason excludes no row, it only says whether a forecast may gate G6"
    - "A withheld forecast follows the zero-width-band convention: still reported in pipeline['forecast'], forecast_used_by_g6 False, detector gets forecast=None"

key-files:
  created: []
  modified:
    - backend/data_cleaning.py
    - backend/city_pipeline.py
    - backend/tests/cleaning_pipeline_test.py
    - docs/data-science/decisions/data_cleaning.md

key-decisions:
  - "A forecast is withheld from G6 when the newest usable row is more than MAX_TRAILING_GAP_SLOTS (1) hourly slots before the run: one skipped cycle is tolerated, two are not"
  - "An ml forecast is withheld unless the newest ML_LOOKBACK_ROWS (7, derived from config.FORECAST_ML_LAG_HOURS and FORECAST_ML_ROLLING_WINDOW_HOURS) usable rows are on consecutive hours; naive and ewm ignore lookback contiguity"
  - "The guard is consulted only when a forecast exists and cleaning succeeded; it returns None for zero usable rows. The zero-width band check keeps priority and its own log line"

requirements-completed: [CLEAN-02]

coverage:
  - id: D1
    description: "forecast_gap_reason tolerates one skipped cycle before the run, ignores an empty history, and requires an unbroken lookback only for ml"
    requirement: CLEAN-02
    verification:
      - kind: unit
        ref: "backend/tests/cleaning_pipeline_test.py#test_gap_reason_tolerates_one_skipped_cycle_before_the_run"
        status: pass
      - kind: unit
        ref: "backend/tests/cleaning_pipeline_test.py#test_gap_reason_ignores_an_empty_history"
        status: pass
      - kind: unit
        ref: "backend/tests/cleaning_pipeline_test.py#test_gap_reason_requires_an_unbroken_lookback_only_for_ml"
        status: pass
      - kind: unit
        ref: "backend/tests/cleaning_pipeline_test.py#test_ml_lookback_follows_the_feature_definition"
        status: pass
    human_judgment: false
  - id: D2
    description: "Skipped-cycle edge (SC2) end to end through run_city_pipeline: one skipped cycle inside the history keeps the forecast, two before the run withhold it, ml across a gap in its lookback withholds it, a zero-width band keeps its own handling"
    requirement: CLEAN-02
    verification:
      - kind: integration
        ref: "backend/tests/cleaning_pipeline_test.py#test_one_skipped_cycle_inside_the_history_keeps_the_forecast_for_g6"
        status: pass
      - kind: integration
        ref: "backend/tests/cleaning_pipeline_test.py#test_the_previous_cycle_skipped_still_uses_the_forecast"
        status: pass
      - kind: integration
        ref: "backend/tests/cleaning_pipeline_test.py#test_two_skipped_cycles_before_the_run_withhold_the_forecast_from_g6"
        status: pass
      - kind: integration
        ref: "backend/tests/cleaning_pipeline_test.py#test_ml_forecast_across_a_gap_in_its_lookback_is_withheld"
        status: pass
      - kind: integration
        ref: "backend/tests/cleaning_pipeline_test.py#test_zero_width_band_keeps_its_own_handling_when_the_history_is_also_stale"
        status: pass
    human_judgment: false
  - id: D3
    description: "The policy doc states the forecast-use rule and both constants with their values, pinned by the doc agreement test"
    requirement: CLEAN-02
    verification:
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_policy_doc_names_every_flag_and_threshold"
        status: pass
    human_judgment: false

duration: 6 min
completed: 2026-10-20
---

# Phase 2 Plan 4: Forecast Gap Guard Summary

**`forecast_gap_reason` keeps a stale or lag-misaligned forecast (newest usable row more than one slot before the run; `ml` with fewer than 7 consecutive newest rows) from gating G6, while still reporting it; skipped-cycle behavior is tested end to end through `run_city_pipeline`.**

## Accomplishments

- `data_cleaning.forecast_gap_reason(report, forecast_method)` plus `MAX_TRAILING_GAP_SLOTS = 1` and `ML_LOOKBACK_ROWS = 7` (derived from the ML feature definition, config read only). It excludes no row.
- `run_city_pipeline` consults the guard next to the zero-width-band check. A withheld forecast sets `forecast_used_by_g6` False, passes `forecast=None` to `AnomalyDetector.for_city`, keeps `pipeline["forecast"]`, and logs one INFO line `forecast not used for G6 this run -- <reason>`. No new key in `pipeline` or the result.
- Nine tests in `backend/tests/cleaning_pipeline_test.py` cover both boundaries, the empty edge, the SC2 skipped-cycle case (hourly 00:00-09:00 without 05:00, run at 10:00: 9-row history, 06:00 row `after_gap`, forecast used), and zero-width precedence.
- Policy doc gains `## Forecast use across gaps (CLEAN-02)` and both constants in the thresholds table.

TDD note: the tests were written first and run before the implementation (6 of 12 in the file failed on the missing function and behavior; the other 3 integration cases passed because they assert the unchanged keep-the-forecast and zero-width paths). The plan prescribes one commit for the task, so RED and GREEN landed together rather than as separate `test` and `feat` commits.

## Task Commits

1. Task 1: Withhold a forecast built across too large a gap from G6 - `bdaf2b0` (feat)
2. Task 2: Phase 1 compatibility and phase gate - no commit (no Phase 1 fixture conflicted)

## Deviations from Plan

None - plan executed exactly as written. The commit trailer uses `Co-Authored-By: Claude Sonnet 5.5` per the session's attribution instruction rather than the `Opus 5.5` line in the plan text.

## Fixture reconciliations

None. All four Phase 1 test files (`city_pipeline_test.py`, `dlr_orchestrator_test.py`, `backfill_archive_test.py`, `observation_composer_test.py`) pass unchanged with the guard in place (50 passed); `backend/tests/city_pipeline_test.py` is untouched.

## Discrepancies

- The plan's `<interfaces>` said the detector stand-in `check` records arguments; the working Phase 1 stand-in `check(raw_data, rating)` returns `(False, "")`, and the new stand-in copies that (a `None` return made G6 fall back with "detector error", a test-double mistake caught in the first run).
- The plan estimated 60000 tokens; actual chars/4 over the changed files is about 9000 (recorded in `actuals`).

## Phase gate results

| Check | Result |
|---|---|
| Task 1 verify (cleaning_pipeline_test + data_cleaning_test, no change under data/ or outputs/) | 46 passed; no path changed |
| Doc agreement test `test_policy_doc_names_every_flag_and_threshold` | 1 passed |
| Phase 1 test files | 50 passed |
| Full suite (`pytest` from repo root) | 1349 passed, 0 failed, 0 errors (250 s); no path under data/ or outputs/ changed |
| Shadow-facing AST check (`_validation_row`, `ARCHIVE_COLUMNS`, `ARCHIVE_SCHEMA_VERSION` vs 5efe97d) | "shadow-facing definitions unchanged" |
| `git diff --quiet 5efe97d` over config.py, ampacity_forecast.py, anomaly_detector.py, forecast_training.py, forecast_experiment.py, forecast_experiment_audit.py, legacy_corridor.py, shadow_collect.yml | exit 0 |
| Phase 1 assert lines vs the `test(01-03)` commit | diff empty |
| `python backend/dlr_orchestrator.py --help` | exit 0 |
| Task 1 acceptance greps (function, constants, wiring pattern, three test names, doc heading) | all pass |

## Known Stubs

None.

## Threat Flags

None. The change adds no endpoint, auth path, file access or schema; T-02-12 (stale or misaligned forecast gating G6), T-02-13 (guard on empty or failed cleaning) and T-02-14 (frozen modules) are mitigated and tested or gate-checked as above.

## Next Phase Readiness

Phase 2 is complete: all four plans have summaries. Phase 3 should measure per-city flag rates and how often `MAX_TRAILING_GAP_SLOTS` and `ML_LOOKBACK_ROWS` withhold the forecast on real archives; both are provisional.

## Self-Check: PASSED

- FOUND: backend/data_cleaning.py (`def forecast_gap_reason`), backend/city_pipeline.py, backend/tests/cleaning_pipeline_test.py, docs/data-science/decisions/data_cleaning.md
- FOUND: commit bdaf2b0 is an ancestor of HEAD
