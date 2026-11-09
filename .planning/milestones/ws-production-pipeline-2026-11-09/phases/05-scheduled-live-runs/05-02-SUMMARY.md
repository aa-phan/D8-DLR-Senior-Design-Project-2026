---
phase: 05-scheduled-live-runs
plan: 02
subsystem: infra
tags: [logging, nsrdb, python-dotenv, pytest, observation-composer, safety-monitor]

requires:
  - phase: 04-supabase-store-writer
    provides: "pipeline['forecast_status'] and pipeline['forecast_error'] in run_city_pipeline, detector_model as the model-source value, --store postgres --no-run-row"
  - phase: 05-scheduled-live-runs
    provides: "05-01 dlr_live_run.classify reading forecast_status, forecast_error and detector_model_loaded from each summary row"
provides:
  - "summarize() rows end with forecast_status, forecast_error and detector_model_loaded (a boolean, never a path), so the orchestrator --output JSON tells the runner whether the ML forecast failed and whether an anomaly model loaded (OD-3)"
  - "pipeline['forecast_error'] capped at 300 characters (FORECAST_ERROR_MAX_CHARS)"
  - "load_dotenv() runs only in dlr_orchestrator's __main__ block"
  - "observation_composer skips NSRDB for any window ending in the current UTC year (NSRDB_SKIP_YEARS_BEFORE_CURRENT, _nsrdb_unpublished): no request, no error entry, no breaker count"
  - "fetch_timeseries diagnostics are DEBUG records on the dlr_pipeline logger; DLRSafetyMonitor with no logger warns on the DLRSafetyMonitor logger; backfill_archive._capture_gate_messages keeps per-step gate counting"
affects: [05-03, 05-04, 05-05, 05-06, phase-06]

actuals:
  tokens: 6300
  tasks: 3
  commits: 6

tech-stack:
  added: []
  patterns:
    - "A provider that is not applicable returns None from the composer's _call (as TCEQ does), which records no error and leaves the circuit breaker untouched"
    - "Library code reports through a module logger; a caller that needs the lines (backfill) attaches its own handler and restores the logger afterwards"
    - "load_dotenv() only under __main__, so tests that call main() never read the owner's .env"

key-files:
  created:
    - backend/tests/live_log_hygiene_test.py
  modified:
    - backend/city_pipeline.py
    - backend/dlr_orchestrator.py
    - backend/observation_composer.py
    - backend/dlr_pipeline.py
    - backend/DLRSafetyMonitor.py
    - backend/backfill_archive.py
    - backend/tests/city_pipeline_test.py
    - backend/tests/dlr_orchestrator_test.py
    - backend/tests/observation_composer_test.py
    - backend/tests/backfill_archive_test.py

key-decisions:
  - "pipeline['forecast_error'] keeps Phase 4's text form 'forecast failed: <message>' (documented in docs/data-science/schema/city_rating_v1.md and pinned by Phase 4 tests) and gains only the 300-character cap; the plan's '<ExceptionType>: <message>' form is not used"
  - "The NSRDB rule is relative to the current UTC year (NSRDB_SKIP_YEARS_BEFORE_CURRENT = 0), never a fixed ceiling year; nsrdb_provider.py is untouched"
  - "backfill's _capture_gate_messages sets the monitor logger to WARNING when the effective level is higher (the CLI sets ERROR), turns propagate off for the step, and restores level, propagate and handlers in finally"

patterns-established:
  - "Stdout-silence tests: capsys.readouterr().out == '' plus a caplog assertion on the logger that now carries the line"
  - "A guard test that passes before and after (backfill counting through a real monitor) is added with the RED tests and shown to fail when the capture is removed"

requirements-completed: [PIPE-02, SCHED-01]

coverage:
  - id: D1
    description: "Each city's summary row reports forecast_status, forecast_error (capped at 300 characters, None unless the forecast raised) and detector_model_loaded as a boolean, after the existing keys; a result without pipeline details gives None, None, False"
    requirement: PIPE-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_summarize_row_shape_and_gate_names"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_summarize_reports_a_failed_forecast_and_whether_an_anomaly_model_loaded"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_forecast_error_is_truncated_to_300_characters"
        status: pass
    human_judgment: false
  - id: D2
    description: ".env is loaded only when dlr_orchestrator runs as a script, never from main()"
    requirement: SCHED-01
    verification:
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_dotenv_is_loaded_only_when_run_as_a_script"
        status: pass
    human_judgment: false
  - id: D3
    description: "A window ending in the current UTC year never calls NSRDB and records no error or breaker count, with the adjacency edges at 1 January 00:00Z and 31 December 23:00Z; past-year windows call NSRDB as before and the 3-failure breaker still opens"
    requirement: PIPE-02
    verification:
      - kind: unit
        ref: "backend/tests/observation_composer_test.py#test_nsrdb_unpublished_year_boundaries"
        status: pass
      - kind: unit
        ref: "backend/tests/observation_composer_test.py#test_current_year_window_never_calls_nsrdb_and_records_no_error"
        status: pass
      - kind: unit
        ref: "backend/tests/observation_composer_test.py#test_past_year_window_still_calls_nsrdb_and_breaker_still_opens"
        status: pass
    human_judgment: false
  - id: D4
    description: "fetch_timeseries and the default safety-monitor logger write nothing to stdout (DEBUG and WARNING log records instead), with the return value, request parameters, injected-logger behaviour and result['alerts'] unchanged"
    requirement: PIPE-02
    verification:
      - kind: unit
        ref: "backend/tests/live_log_hygiene_test.py#test_fetch_timeseries_prints_nothing"
        status: pass
      - kind: unit
        ref: "backend/tests/live_log_hygiene_test.py#test_fetch_timeseries_returns_the_same_frame_and_sends_the_same_request"
        status: pass
      - kind: unit
        ref: "backend/tests/live_log_hygiene_test.py#test_safety_monitor_default_logger_warns_instead_of_printing"
        status: pass
      - kind: unit
        ref: "backend/tests/live_log_hygiene_test.py#test_injected_logger_still_receives_the_gate_message"
        status: pass
    human_judgment: false
  - id: D5
    description: "backfill still counts gate failures per step when the monitor logs, at any root log level, and leaves the monitor logger as it found it"
    requirement: SCHED-01
    verification:
      - kind: unit
        ref: "backend/tests/backfill_archive_test.py#test_backfill_counts_gate_failures_the_monitor_logs"
        status: pass
      - kind: unit
        ref: "backend/tests/backfill_archive_test.py#test_backfill_counts_one_gate_failure_per_step_over_several_steps"
        status: pass
      - kind: unit
        ref: "backend/tests/backfill_archive_test.py#test_backfill_leaves_the_monitor_logger_as_it_found_it"
        status: pass
      - kind: unit
        ref: "backend/tests/backfill_archive_test.py#test_backfill_logs_one_row_per_city_and_per_error_and_counts_printed_gates"
        status: pass
    human_judgment: false

duration: 10 min
completed: 2026-10-24
status: complete
plan_head_before: 31487bece29f2472cfb0d54c3a84b4d4a04b4afa
plan_head_after: 20a3c1b087d6c9a0d3a4e6bb4be6770cbf2fd7a0
commits: 6
---

# Phase 5 Plan 02: Run output, NSRDB skip and log hygiene Summary

**Summary rows now carry `forecast_status`, `forecast_error` (capped at 300 characters) and a boolean `detector_model_loaded` so the live runner can fail a run on a broken ML forecast or a missing anomaly model; NSRDB is no longer called for windows in the current UTC year; `fetch_timeseries` and the safety monitor log instead of printing, with backfill still counting gates; `.env` loads for script runs only.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-10-24T08:18:29Z
- **Completed:** 2026-10-24T08:28:18Z
- **Tasks:** 3 (6 commits: a RED test commit and a GREEN commit for each)
- **Files modified:** 11 (6 production modules, 4 existing test files, 1 new test file)

## Accomplishments

- OD-3: `summarize()` appends `forecast_status`, `forecast_error` and `detector_model_loaded` after the existing keys. These are the names `dlr_live_run.py` reads, so a real run through the runner no longer records `forecast_status` None and a false model flag for every city (the 05-01 discrepancy). `detector_model_loaded` is `bool(pipe.get("detector_model"))`, never the filesystem path.
- `pipeline["forecast_error"]` is cut to 300 characters (`FORECAST_ERROR_MAX_CHARS`); exactly 300 passes whole. It stays out of every `city_rating` column (the Phase 4 row builder maps explicit columns).
- `load_dotenv()` runs in the `__main__` block only; a test pins that `main()` does not call it. python-dotenv's default leaves an existing variable, even an empty one, alone, which the 05-01 fault drill relies on (checked with an empty variable and a `.env` that sets it).
- NSRDB: `_nsrdb_unpublished(end_ts, now_ts)` returns `end_ts.year >= now_ts.year - NSRDB_SKIP_YEARS_BEFORE_CURRENT` (0). `_call` returns None for such a window, the composer's existing "not applicable" signal, so there is no request, no `fetcher.errors` entry and no breaker count, and solar comes from Open-Meteo. Four consecutive current-year fetches left `fetcher.errors` empty; a later 2025 fetch on the same fetcher still reached NSRDB.
- Log hygiene: the four `fetch_timeseries` diagnostics are `log.debug` calls with %-style arguments; the frame and the request parameters are asserted unchanged. `DLRSafetyMonitor` uses `logger or log.warning`, so a gate failure is a WARNING on the `DLRSafetyMonitor` logger with the same message; an injected logger gets the same message and nothing is logged twice.
- `backfill_archive._capture_gate_messages(buf)` replaces the bare `redirect_stdout`: it redirects stdout into the step buffer and attaches a `%(message)s` handler to the `DLRSafetyMonitor` logger, with a WARNING threshold when the effective level is higher and `propagate = False`, restoring level, propagate and handlers in `finally` (also when the step raises).

## Task Commits

1. **Task 1 RED:** failing tests for the error cap, the summary keys and script-only dotenv - `85f754c` (test)
2. **Task 1 GREEN:** report forecast status, errors and anomaly-model presence per city; load .env for script runs - `7142b6c` (feat)
3. **Task 2 RED:** failing tests for skipping NSRDB in the current UTC year - `0b4795b` (test)
4. **Task 2 GREEN:** skip NSRDB for windows in the current UTC year - `2559d0a` (feat)
5. **Task 3 RED:** failing tests for stdout silence and backfill gate counting through the monitor logger - `d34b138` (test)
6. **Task 3 GREEN:** diagnostic prints and gate messages go to logging; backfill still counts gates - `20a3c1b` (fix)

**Plan metadata:** recorded in the docs commit that follows this file (SUMMARY, then STATE/ROADMAP/REQUIREMENTS).

## TDD Gate Compliance

All three tasks are `tdd="true"`; each has a `test(05-02)` commit before its `feat`/`fix` commit.

- **Task 1 RED:** 5 failed, 37 passed. `gsd-tools check tdd-red-evidence` on the pytest JUnit XML for the target `test_forecast_error_is_truncated_to_300_characters` returned `RED_EVIDENCE_OK` (`target_test_failed`, format `junit`). Semantic assessment: the target ran and failed on the planned length assertion (the 1000-character message was kept whole); the other four failures were the summarize key list, the three-key values and the dotenv source check, each the planned assertion and not a collection or fixture fault. Evidence record: `.planning/tmp/05-02-t1-red-evidence.json`.
- **Task 2 RED:** 7 failed, 17 passed. Target `test_current_year_window_never_calls_nsrdb_and_records_no_error` returned `RED_EVIDENCE_OK`; it failed on `assert 'nsrdb' not in calls` (NSRDB was called for the current-year window). The assertions run in the order calls, errors, then frames so the failure names the planned behaviour. The other six were the missing `_nsrdb_unpublished` and `NSRDB_SKIP_YEARS_BEFORE_CURRENT` names. Evidence: `.planning/tmp/05-02-t2-red-evidence.json`.
- **Task 3 RED:** 2 failed, 12 passed. Target `test_fetch_timeseries_prints_nothing` returned `RED_EVIDENCE_OK`; stdout carried the SUMMARY, Returned stations, STID and OBS keys lines. `test_safety_monitor_default_logger_warns_instead_of_printing` failed on the printed `G4 FAIL` line. The backfill tests passed in RED by design (the monitor still printed and backfill still redirected stdout); they are regression guards. After the monitor change and before the backfill change, 3 of them failed (both `root_warning` and `root_error` cases and the several-step case), showing the new capture is what keeps the count. Evidence: `.planning/tmp/05-02-t3-red-evidence.json`.
- **GREEN:** every task's verify command passes; the full suite is 1696 passed, 48 skipped, 0 failed (baseline before this plan: 1676 passed, 48 skipped).
- **REFACTOR:** none needed.

## Files Created/Modified

- `backend/city_pipeline.py` - `FORECAST_ERROR_MAX_CHARS = 300` and the cap on `forecast_error`
- `backend/dlr_orchestrator.py` - three summarize keys; `from dotenv import load_dotenv` and the call in the `__main__` block
- `backend/observation_composer.py` - `NSRDB_SKIP_YEARS_BEFORE_CURRENT`, `_nsrdb_unpublished`, the skip in `_call`, docstring
- `backend/dlr_pipeline.py` - four `print` calls in `fetch_timeseries` became `log.debug`
- `backend/DLRSafetyMonitor.py` - module logger; default `logger or log.warning`
- `backend/backfill_archive.py` - `_capture_gate_messages` and its use in `backfill`
- `backend/tests/live_log_hygiene_test.py` - new: 4 test functions (fetch_timeseries silence, same frame and request, monitor default logger, injected logger)
- `backend/tests/city_pipeline_test.py`, `dlr_orchestrator_test.py`, `observation_composer_test.py`, `backfill_archive_test.py` - extended as listed below

**Phase 1 pinned lists extended (no assertion deleted):**

- `dlr_orchestrator_test.py`: the expected key list in `test_summarize_row_shape_and_gate_names` gained `forecast_status`, `forecast_error`, `detector_model_loaded` (the one removed line is that list, replaced by its extended form), with value assertions added there and in `test_summarize_tolerates_a_result_without_pipeline_details`; the `_city_result` helper's `pipeline` block gained `forecast_status` and `forecast_error`.
- `city_pipeline_test.py`: the pinned `pipeline` key set already held `forecast_status` and `forecast_error` (Phase 4 added both), so it needed no change; the forecast-exception and cold-start tests gained assertions on them.
- `observation_composer_test.py` and `backfill_archive_test.py`: appended tests only; the constants pin test was left alone (a separate test pins the new constant, because the pin test does not cover every module constant).

## Decisions Made

- Kept Phase 4's `forecast_error` text form (see Discrepancies) and added only the cap.
- The NSRDB skip lives in the composer and is relative to the current year; `nsrdb_provider.py`, `FIELD_PRIORITY` and every `forecast_shadow_*` file are untouched.
- The step capture handles the process-level logging level itself rather than relying on the root level, because `backfill_archive.main()` sets the root to ERROR.

## Deviations from Plan

### Auto-fixed Issues

None.

### Plan-vs-instruction differences (not defects)

- **Commit shape:** the plan says one commit per task; each `tdd="true"` task has a `test(...)` commit then a `feat`/`fix` commit, per the canonical TDD reference (same as 05-01). The `feat`/`fix` messages are the ones the plan specifies. For Task 3 the plan lists five files in one commit; the two test files are in the RED commit and the three production files in the GREEN commit.
- **Commit trailer:** `Co-Authored-By: Claude Sonnet 5.5` instead of the plan's `Claude Opus 5.5`, per the attribution instruction for this run.
- **Extra tests:** `test_forecast_error_of_exactly_300_characters_is_kept_whole`, `test_nsrdb_skip_constant_skips_only_the_current_year`, `test_fetch_timeseries_returns_the_same_frame_and_sends_the_same_request`, `test_backfill_counts_one_gate_failure_per_step_over_several_steps` and `test_backfill_leaves_the_monitor_logger_as_it_found_it`, plus a second log level for the backfill test; the three named hygiene tests and the other named tests exist as specified.

---

**Total deviations:** 0 auto-fixed
**Impact on plan:** none; the changes stay inside the planned files.

## Discrepancies

- **`forecast_status` and `forecast_error` already existed.** Phase 4 (04-02, and 04-10 for IN-07) had added both to `run_city_pipeline` before this plan ran, with `forecast_error = f"forecast failed: {exc}"`. The plan's truth and test call for `"<ExceptionType>: <message>"` (`"RuntimeError: no trained artifact"`). That text is documented as the stored reason in `docs/data-science/schema/city_rating_v1.md` and pinned by `city_pipeline_test.py::test_a_forecast_failure_reports_its_reason` and `supabase_orchestrator_test.py`, and the plan says "add only what is missing", so the format was kept and only the 300-character cap was added. If the exception type name is wanted in the run log, that is a Phase 4 contract change (schema doc and two test files) for the owner to decide.
- **The cap is applied before redaction.** `forecast_error` is cut to 300 characters in `city_pipeline`; the secret redaction happens later (the runner's `redact`, Phase 4's `build_run_row`). A secret that straddled character 300 could leave a prefix fragment, which exact-value redaction would not match. This is the plan's accepted T-05-09 (low) and was not widened.
- **Two detector flags with different truthiness.** The store path still sets the run-row flag with `pipeline.get("detector_model") is not None`; `summarize()` uses `bool(pipe.get("detector_model"))` as the plan specifies. They differ only for an empty-string model source, which `AnomalyDetector` does not produce.
- Everything else matched the plan and the 05-01 summary (names `forecast_status`, `forecast_error`, `detector_model_loaded` are the ones `dlr_live_run.py` reads).

## Issues Encountered

None. The pre-existing untracked files in the working tree (`.DS_Store`, `.obsidian/`, `graphify-out/`, the phase 07 directory, `.planning/config.json` and so on) were left unstaged; every commit used explicit paths.

## Known Stubs

None. No placeholder values, TODO or FIXME text, and no hardcoded empty data flows to a consumer.

## Threat Flags

None. The surface touched is the one in the plan's threat model (T-05-06 to T-05-10): `.env` loading, backfill gate counts, the NSRDB rule, forecast error text and `dlr_pipeline.py`'s diagnostic lines. `git diff --stat origin/main` over `backend/forecast_shadow_*.py`, `.github/workflows/shadow_collect.yml` and `backend/nsrdb_provider.py` prints nothing, and the pre-edit grep for `Returned stations` and `OBS keys` in the shadow modules and tests found nothing.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 05-03 (the runner writes the `pipeline_run` row from the records, which now carry real `forecast_status`, `forecast_error` and `detector_model_loaded` values), 05-04 (model pre-flight) and 05-05 (runbook: document `NSRDB_SKIP_YEARS_BEFORE_CURRENT`).
- 05-02 no longer blocks a real dispatch; 05-06 still needs the models provisioned (05-04) or every city will report `detector_model_loaded` false and the run will exit 1 by design.
- Nothing pushed.

## Self-Check: PASSED

- FOUND: `backend/tests/live_log_hygiene_test.py` and the six modified production and test files listed above
- FOUND commits: `85f754c`, `7142b6c`, `0b4795b`, `2559d0a`, `d34b138`, `20a3c1b` (all ancestors of HEAD; `check evaluation-scope --plan 05-02 --commits-only` resolves the plan)
- Acceptance criteria re-run: `forecast_error` count in `city_pipeline.py` is 4; the `dlr_orchestrator.py` greps, the new test names and the composer constant and function greps pass; `fetch_timeseries` has 0 `print(`; `logger or log.warning` and `_capture_gate_messages` present; shadow files and `nsrdb_provider.py` unchanged from `origin/main`; no test function deleted; full suite 1696 passed, 0 failed.

---
*Phase: 05-scheduled-live-runs*
*Completed: 2026-10-24*
