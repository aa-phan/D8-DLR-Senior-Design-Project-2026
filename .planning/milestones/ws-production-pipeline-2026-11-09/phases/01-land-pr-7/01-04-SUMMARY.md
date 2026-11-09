---
phase: 01-land-pr-7
plan: 04
subsystem: testing
tags: [pytest, offline-tests, dlr-orchestrator, error-isolation, cli]

requires:
  - phase: 01-land-pr-7
    provides: "01-01 offline fixtures (_no_network, _offline_env) copied from backfill_archive_test.py"
provides:
  - "backend/tests/dlr_orchestrator_test.py: 14 test functions (18 collected) for run_dlr_pipeline, summarize and main"
affects: [01-05, 05-scheduled-collection]

actuals:
  tokens: 3800
  tasks: 2
  commits: 2
plan_head_before: aee272a371235771576c29fe1834fa96abfc7d58
plan_head_after: 234128e6bc6ec7675c1bf64dd1f2493faffa7964

tech-stack:
  added: []
  patterns:
    - "_fake_city_pipeline: patches run_city_pipeline onto the orchestrator module (imported by name) and records (name, start, end, stations, kwargs)"
    - "_fake_run_dlr_pipeline + _canned_run: main() is only ever called with the run replaced"
    - "_composed_stub: callable with .provenance / .errors standing in for a caller-supplied composed fetcher"

key-files:
  created:
    - backend/tests/dlr_orchestrator_test.py
  modified: []

key-decisions:
  - "No backend module, frozen module or workflow was touched; the plan adds one test file"
  - "Fixtures copied from backfill_archive_test.py (no conftest.py), per repo convention"

requirements-completed: []  # LAND-03 / PIPE-01 are shared with 01-05; requirements.ready-ids reported 0/2 ready

coverage:
  - id: D1
    description: "Per-city error isolation, city order (given, None and [] default to config.LOCATIONS), KeyError/ValueError validation before any city or discovery"
    requirement: "LAND-03"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_one_failing_city_is_recorded_and_the_others_still_rate"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_cities_run_in_the_order_given_and_default_to_config_locations"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_unknown_city_raises_key_error_before_any_city_runs"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_bad_provider_or_forecast_method_raises_value_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "Composed vs single-provider fetcher wiring, sources/provider_errors reporting, no-token EnvironmentError before any city, default window"
    requirement: "PIPE-01"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_composed_mode_shares_one_fetcher_and_rates_on_the_station_path"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_composed_mode_uses_the_callers_fetcher_when_given"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_single_provider_mode_passes_no_fetcher_and_reports_no_sources"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_composed_mode_without_stations_or_token_raises_before_any_city"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_window_defaults_to_window_hours_before_end"
        status: pass
    human_judgment: false
  - id: D3
    description: "summarize() row shape and gate names; main() exit code, CLI pass-through and --output JSON"
    requirement: "LAND-03"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_summarize_row_shape_and_gate_names"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_summarize_tolerates_a_result_without_pipeline_details"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_main_exit_code_is_one_only_when_every_city_failed"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_main_passes_cli_arguments_through"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_main_output_writes_the_run_summary_json"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-10-20
status: complete
---

# Phase 1 Plan 04: DLR Orchestrator Tests Summary

**Offline pytest coverage of `dlr_orchestrator`: a failing city is recorded while the rest still rate, validation fails before any city or station discovery, composed-mode fetcher wiring, the `summarize()` row shape and `main()`'s exit code, argument pass-through and JSON output.**

## Performance

- **Duration:** ~6 min
- **Completed:** 2026-10-20T00:38:00Z
- **Tasks:** 2
- **Files modified:** 1 (created)

## Accomplishments
- One city raising leaves `errors == {"MIDLAND": "MIDLAND provider down"}` while the other three cities still produce results and summary rows, in `config.LOCATIONS` order.
- City order is the order given; `cities=None` and `cities=[]` both mean every city in `config.LOCATIONS` (PIPE-01 offline evidence).
- `KeyError` (unknown city), and `ValueError` (bad provider or forecast method) are raised before any city runs and before discovery.
- Composed mode shares one fetcher across cities (or uses the caller's by identity) with provider `synoptic` and reports `sources` / `provider_errors`; a single-provider mode passes `fetch_weather=None`, discards a caller fetcher, needs no token and reports neither key.
- Composed mode with no stations and no token raises `EnvironmentError` before any city runs.
- `summarize()` key order, sorted/de-duplicated gate names, and `None` fields for a result without `pipeline` are pinned.
- `main()` returns 1 only when there are errors and no summary rows; CLI arguments reach `run_dlr_pipeline` unchanged; `--output` creates its directory and writes the eight-key JSON.

## Task Commits

1. **Task 1: isolation, order, validation, wiring, default window** - `f5dbd33` (test)
2. **Task 2: summarize row shape and main** - `234128e` (test)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `backend/tests/dlr_orchestrator_test.py` - 14 test functions (18 collected), offline, tmp_path only

## Decisions Made
None - followed plan as specified.

## Deviations from Plan

None - plan executed exactly as written.

## Discrepancies

none. `backend/dlr_orchestrator.py` behaved as the plan's interface block described in every tested respect.

Note for Phase 5 (SCHED-01): a station-discovery failure (composed/synoptic with no stations and no token) raises `EnvironmentError` out of `run_dlr_pipeline` and ends the whole run; it is not isolated per city. `test_composed_mode_without_stations_or_token_raises_before_any_city` pins this.

## Issues Encountered
None

## Verification
- `pytest -q -p no:cacheprovider backend/tests/dlr_orchestrator_test.py`: 18 passed; `--collect-only`: 18 tests collected.
- No file under `data/` or `outputs/` changed during the run.
- `git diff 5efe97d HEAD -- backend ':(exclude)backend/tests'` is empty (no backend module changed).
- No test asserts a rating value or reads shadow predictions.

## Known Stubs
None.

## Threat Flags
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Ready for 01-05. LAND-03 and PIPE-01 are shared with 01-05 and stay unmarked until `requirements.ready-ids` reports them ready.

## Self-Check: PASSED
- `backend/tests/dlr_orchestrator_test.py` exists; commits `f5dbd33` and `234128e` are ancestors of HEAD.

---
*Phase: 01-land-pr-7*
*Completed: 2026-10-20*
