---
phase: 01-land-pr-7
plan: 01
subsystem: testing
tags: [pytest, offline-tests, backfill, observation-composer, city-pipeline, dlr-orchestrator]

requires:
  - phase: 01-land-pr-7
    provides: PR #7 modules landed at backend/ paths (LAND-01, LAND-02)
provides:
  - "backend/tests/backfill_archive_test.py: offline tracer through backfill -> dlr_orchestrator -> city_pipeline -> city_rating -> observation_composer"
  - "Offline seams reused by plans 01-02..01-04: _no_network and _offline_env autouse fixtures, _station_at, _hourly, _install_providers"
affects: [01-02, 01-03, 01-04, 02-data-cleaning]

actuals:
  tokens: 3253
  tasks: 2
  commits: 2
plan_head_before: 236ec230e0f55b82424658f4dccc3d9e67f0c49b
plan_head_after: d909136b477c3c978ee3a67850af9ae70b7967b9

tech-stack:
  added: []
  patterns:
    - "Stub providers by monkeypatching the module attributes observation_composer calls (oc.weather_provider.fetch_weather, oc.tceq_provider.fetch_tceq, oc.nsrdb_provider.fetch_nsrdb, oc.open_meteo_provider.fetch_open_meteo)"
    - "Network guard records requests.get attempts and asserts the record is empty at teardown, so a provider exception swallowed by except Exception still fails the test"
    - "Stub frames carry fixed datetime_utc values, because runs older than 2 days make the composer request whole UTC days"

key-files:
  created:
    - backend/tests/backfill_archive_test.py
  modified: []

key-decisions:
  - "No backend module, frozen module or workflow was touched; the plan adds one test file"
  - "Fixtures live in the test file (no conftest.py), per repo convention"

patterns-established:
  - "Offline tracer first: one test drives the full per-city stack with stub providers, tmp_path archive and log, credentials unset and the anomaly model loader patched to None"

requirements-completed: [LAND-03, PIPE-01]

coverage:
  - id: D1
    description: "Offline tracer: one backfill window rates AUSTIN through the composed stack into a tmp_path archive, field sources follow FIELD_PRIORITY, and a rerun skips archived steps with no duplicate rows"
    requirement: "PIPE-01"
    verification:
      - kind: unit
        ref: "backend/tests/backfill_archive_test.py#test_backfill_rates_through_the_composed_stack_offline_and_a_rerun_skips_archived_steps"
        status: pass
    human_judgment: false
  - id: D2
    description: "backfill resume, partial-step skip, stale-log retirement, log rows and printed-gate counting, interrupt and resume, and skip_synoptic"
    requirement: "LAND-03"
    verification:
      - kind: unit
        ref: "backend/tests/backfill_archive_test.py (5 tests after the tracer)"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-10-20
status: complete
---

# Phase 1 Plan 01: Offline Backfill Tracer and Resume Tests Summary

**Six offline tests for backfill_archive, led by a tracer that runs backfill -> dlr_orchestrator -> city_pipeline -> city_rating -> the composed observation fetcher with stub providers, and covers resume/skip, log rows, gate counting, interrupt and no-synoptic.**

## Performance

- **Duration:** 8 min
- **Tasks:** 2 of 2
- **Files:** 1 created (`backend/tests/backfill_archive_test.py`, 319 lines, 6 tests)

## Accomplishments

- Tracer test: two hourly steps for AUSTIN archive exactly two rows, `totals["sources"] == {"air_temp": {"synoptic": 2}, "wind_speed": {"tceq": 2}, "solar_radiation": {"nsrdb": 2}}`, exhausted 0, no provider issues; a rerun reports `runs == 0`, `skipped == 2` and leaves the archive and log unchanged.
- Partly archived step calls `run_dlr_pipeline` with only the cities not yet archived for that timestamp.
- `_retire_stale_log` moves only a log whose first line differs from `_LOG_HEADER` to `.legacy`; missing, empty and same-header logs are left alone; backfill writes a fresh header afterwards.
- Log rows per summary city and per error (commas become semicolons); gate failures printed during a step are counted from captured stdout and do not reach the real stdout.
- KeyboardInterrupt mid-run returns the totals so far, keeps archived and logged steps, prints the resume message; the rerun finishes the remaining steps with unique `datetime_utc` values.
- `skip_synoptic=True` never calls the station provider.
- Every test runs with `requests.get` guarded (attempts asserted empty at teardown), the three credentials unset, `anomaly_detector._load_city_model_or_none` patched to None, and writes only under tmp_path. `config.HISTORICAL_ARCHIVE_PATH` is redirected and asserted unwritten.

## Task Commits

1. **Task 1 (tracer): offline tracer through backfill, orchestrator, city pipeline and composer** - `ba98fc6`
2. **Task 2: backfill resume, stale log, log rows, interrupt and no-synoptic** - `d909136`

## Verification

- `pytest backend/tests/backfill_archive_test.py`: 6 passed (collect-only: 6 tests collected).
- Tracer `<verify>` re-run before expansion: 1 passed (tracer feedback gate, automated-only, end-of-phase mode).
- Full suite on main at d909136: 1242 passed, 0 failed (baseline 1236 plus 6).
- `find data outputs -newer <marker>` after the run: nothing changed.
- `git diff --quiet 236ec23 HEAD -- backend ':(exclude)backend/tests'` exits 0 (no backend module changed). `git diff --name-only HEAD~2 HEAD` lists only the new test file.
- All acceptance criteria for both tasks pass.

## Deviations from Plan

None - plan executed exactly as written.

Process note (not a code deviation): the executor's pre-commit assertion treats `main` as a protected branch. This plan ran sequentially on `main` at the orchestrator's explicit direction (worktree isolation degraded), so the two task commits landed on `main` without changing any git configuration. Nothing was pushed.

## Discrepancies

none

## Known Stubs

None. The stub providers in the test file are test doubles by design.

## Threat Flags

None. The plan's threat register (T-01-01..T-01-04) is mitigated: credentials deleted, `stations=` passed explicitly, `requests.get` guarded with a teardown assert, archive and log under tmp_path, anomaly model loader patched.

## Next Phase Readiness

Ready for 01-02 (observation_composer tests), which should copy `_no_network`, `_offline_env`, `_station_at`, `_hourly` and `_install_providers` from this file.
