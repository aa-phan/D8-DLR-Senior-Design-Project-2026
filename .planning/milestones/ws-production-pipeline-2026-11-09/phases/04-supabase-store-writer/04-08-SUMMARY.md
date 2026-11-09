---
phase: 04-supabase-store-writer
plan: 08
subsystem: pipeline
tags: [exit-status, run-log, data-cleaning, forecast-status, gap-closure, postgres]

requires:
  - phase: 04-supabase-store-writer
    provides: "store path in dlr_orchestrator, build_run_row classification, city_rating_v1 consumer doc"
provides:
  - "dlr_orchestrator.main exits 1 when a --store postgres run fails any city (WR-01)"
  - "forecast_status 'failed' plus pipeline['cleaning_error'] when cleaning discards a non-empty history (WR-02)"
  - "cleaning failure surfaces as a degraded city with its redacted error in pipeline_run.cities_failed"
  - "city_rating_v1.md states the widened meaning of forecast_status 'failed'"
affects: [05-scheduled-live-runs, 06-exposure-e2e]

actuals:
  tokens: 3660
  tasks: 2
  commits: 4

plan_head_before: 993b7db71be00a99b2a5e9dc9eb319f0fb28bab3
plan_head_after: 200710fbeb13427e5671e72718c2074c9754e46b
commits: 4

tech-stack:
  added: []
  patterns:
    - "Exit policy is store-dependent: postgres means any failed city is a failed job; CSV keeps 'every city failed'"
    - "A cleaning failure travels as a pipeline-dict key into the run record, never into city_rating"

key-files:
  created: []
  modified:
    - backend/dlr_orchestrator.py
    - backend/city_pipeline.py
    - backend/tests/supabase_orchestrator_test.py
    - backend/tests/city_pipeline_test.py
    - docs/data-science/schema/city_rating_v1.md

key-decisions:
  - "WR-01: no distinct 'partial' exit code; any non-zero is an error to Phase 5's classify, and its single-city children already exit 1 on a failed city"
  - "WR-02: report the cleaning failure as forecast_status 'failed' (already allowed by the table CHECK) rather than a run-log-only flag, because both city_rating and the run log misreported it"
  - "WR-02: an empty history whose cleaning raises stays 'cold_start' (the city really has no history)"

patterns-established:
  - "Phase 1/2 pinned tests are left byte-identical; new assertions go in new tests, and the pinned key set only grows (cleaning_error added)"

requirements-completed: [DB-02, DB-05]

coverage:
  - id: D1
    description: "A postgres-store run (with or without --no-run-row) exits 1 when any city failed and 0 when none did; CSV and default runs keep Phase 1's exit rule"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_main_with_postgres_exits_one_when_any_city_failed"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_orchestrator_test.py#test_main_exit_code_is_one_only_when_every_city_failed"
        status: pass
    human_judgment: false
  - id: D2
    description: "A cleaning failure on non-empty history gives forecast_status 'failed' and a cleaning_error; empty history stays 'cold_start'; unvetted history still never reaches the forecast or detector"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_cleaning_failure_on_existing_history_reports_forecast_failed"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_cleaning_failure_on_empty_history_stays_cold_start"
        status: pass
      - kind: unit
        ref: "backend/tests/cleaning_pipeline_test.py#test_cleaning_failure_rates_the_city_with_no_history"
        status: pass
    human_judgment: false
  - id: D3
    description: "Through the store path the city's row is written, and the run row lists the city in cities_failed as degraded with the redacted cleaning error, not in cities_ok"
    requirement: DB-02
    verification:
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_a_cleaning_failure_is_a_degraded_city_with_its_error_in_the_run_row"
        status: pass
    human_judgment: false
  - id: D4
    description: "city_rating_v1.md tells consumers that failed also covers an uncleanable history, and that such a city is degraded in the run log"
    requirement: DB-05
    verification:
      - kind: other
        ref: "grep -n 'could not be cleaned' docs/data-science/schema/city_rating_v1.md (lines 139 and 181)"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_schema_doc_test.py"
        status: pass
    human_judgment: true
    rationale: "Whether the doc wording is clear to the other teams who read the table is a judgment no test asserts"

duration: 7min
completed: 2026-10-23
status: complete
---

# Phase 4 Plan 08: Run-Health Gap Closure (G-04-2, WR-01 and WR-02) Summary

**A `--store postgres` run now exits 1 when any city fails to write, and a data-cleaning failure that discards a city's real history is reported as `forecast_status 'failed'` and a `degraded` city with its redacted cause, instead of a healthy `cold_start`.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-10-23T21:40:03Z
- **Completed:** 2026-10-23T21:47:28Z
- **Tasks:** 2 (both TDD, RED then GREEN)
- **Files modified:** 5 (139 insertions, 7 deletions)

## Accomplishments
- WR-01: a scheduled job no longer stays green when a city has no row in the production table. Phase 5's runner reads this exit status, so the policy is fixed in Phase 4.
- WR-02: a cleaning bug is now visible in both places the review said misreported it: `city_rating.forecast_status` and the run log.
- The cleaning error text goes only to the run record (redacted by `build_run_row`); `build_rating_row` maps explicit columns, so it never reaches `city_rating`.
- Phase 1 and Phase 2 pinned tests are untouched (`git diff --quiet f7eb3fb` on `dlr_orchestrator_test.py` and `cleaning_pipeline_test.py` exits 0).

## Task Commits

Each task committed atomically, failing-first:

1. **Task 1 (WR-01): postgres-store run with any failed city exits 1**
   - RED `2148f98` (test)
   - GREEN `b63b564` (fix)
2. **Task 2 (WR-02): cleaning failure is a failed forecast and a degraded city**
   - RED `c2d78f7` (test)
   - GREEN `200710f` (fix)

**Plan metadata:** the docs commit that adds this SUMMARY, then the state and roadmap commit.

## TDD Evidence (failing first)

RED evidence is pytest console output, which `gsd_run check tdd-red-evidence` has no adapter for (TAP, JUnit, swift-testing and unittest only), so the classifier was not run. Semantic assessment is by inspection: each target test executed and failed on the planned assertion for the intended reason, and nothing failed on setup, import or collection.

**WR-01 (`2148f98`).** `test_main_with_postgres_exits_one_when_any_city_failed`, 6 parametrized cases. On the old code exactly the two partial postgres cases failed (`argv0`: `--store postgres`; `argv1`: `--store postgres --no-run-row`) with `assert 0 == 1`; the four other cases (clean postgres, no store, `--store csv`) passed. Result: `2 failed, 4 passed`. After `b63b564`: all 6 pass; `supabase_orchestrator_test.py` plus `dlr_orchestrator_test.py` gave 32 passed, 3 skipped (live DB tests).

**WR-02 (`c2d78f7`).** Four tests failed on the old code, all for the planned reason:
- `test_pipeline_key_reports_history_forecast_and_detector`: the pinned key set lacked `cleaning_error`.
- `test_cleaning_failure_on_existing_history_reports_forecast_failed`: `assert 'cold_start' == 'failed'`.
- `test_cleaning_failure_on_empty_history_stays_cold_start`: `KeyError: 'cleaning_error'`.
- `test_a_cleaning_failure_is_a_degraded_city_with_its_error_in_the_run_row`: the run row's `error` was `None`, not the redacted cleaning text (outcome, written and forecast_status already matched).

Result `4 failed, 29 passed, 3 skipped`. After `200710f`: the five-file verify set gave 65 passed, 3 skipped.

The plan's acceptance text says "three new tests"; the plan's own RED instructions produce four failing tests (the two new `city_pipeline_test` tests, the pinned-key addition, and the supabase run-row test), so all four are recorded above.

## Files Created/Modified
- `backend/dlr_orchestrator.py` - `main` returns 1 for `--store postgres` with any entry in `errors`; exit statuses stated in the module docstring and the argparse epilog; `_run_cities_with_store` copies `pipeline["cleaning_error"]` into `record["error"]`.
- `backend/city_pipeline.py` - `cleaning_error` set in the cleaning except branch; `forecast_status = "failed"` when it is set and the history had rows; `cleaning_error` added to `result["pipeline"]`; the single WARNING still names the city and contains "cold start" and now also gives the discarded row count and, when above zero, that the forecast status is failed.
- `backend/tests/supabase_orchestrator_test.py` - WR-01 parametrized test; `_fake_city_pipeline` gains an optional `cleaning_error` behavior; WR-02 run-row test.
- `backend/tests/city_pipeline_test.py` - two WR-02 tests; `cleaning_error` added to the pinned key set with an `is None` assertion (add only).
- `docs/data-science/schema/city_rating_v1.md` - two sentences (below).

## Doc sentences added (DB-05)

"Forecast fields" now reads: "`forecast_status` is `ok` when a forecast was computed (...), `cold_start` when there was too little history, and `failed` when the forecast raised (for example a missing ML model) **or when the city's history could not be cleaned, so the forecast ran on no history although the city had history rows; the detector then reports a cold start (`detector_signal`)**. It is NULL on backfill rows."

Run-log section, under the table: "**A city written while its history could not be cleaned is `degraded`, with the redacted cleaning error (`data cleaning failed: ...`) in `cities_failed`; it is not in `cities_ok`.**"

No column, type or section was added, removed or renamed.

## Decisions Made
- No distinct "partial" exit code. Phase 5's `classify` treats any non-zero child status as an error, and its single-city children already exit 1 when their city fails.
- Chose status `failed` (allowed by the table CHECK) over a run-log-only flag, because the review's defect is that both the row and the log misreport.
- An empty history whose cleaning raises stays `cold_start`: the city genuinely has no history, and `cleaning_error` is still reported.

## Deviations from Plan

None - plan executed exactly as written. The plan's "three new tests" wording understates the count (four failing tests, see TDD Evidence); no scope was added.

## Issues Encountered
- The first full-suite run had one failure, `backend/tests/forecast_shadow_demo_test.py::test_run_once_all_methods_ok_with_per_city_artifacts_and_a_complete_truth_proxy_window`. It passes alone, passes with its whole file (15 passed), and the second full-suite run was green (1527 passed, 46 skipped). That module imports none of `city_pipeline`, `dlr_orchestrator` or `supabase_store`, so it is treated as a pre-existing transient (likely order or timing dependent) and out of scope. Flagged here for whoever owns the shadow tests.
- Behavior to know: on a cleaning failure with an empty history the status is `cold_start`, so `build_run_row` keeps the city in `cities_ok` (healthy status, model loaded) and the `cleaning_error` is not shown in the run row for that city. This follows the plan and the "too little history" definition.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema change; T-04-33, T-04-34 and T-04-35 are mitigated as planned (exit policy tests; cleaning text only in the pipeline dict and redacted run row; history still emptied on a cleaning failure).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 5's runner can rely on a non-zero child exit status for any failed postgres-store city.
- G-04-2 findings WR-01 and WR-02 are closed. Other review findings are covered by sibling gap-closure plans.

## TDD Gate Compliance

RED (`test(04-08)`) precedes GREEN (`fix(04-08)`) for both tasks. The GREEN commits use the `fix` type as the plan specified rather than `feat`. No REFACTOR commit was needed.

## Self-Check: PASSED

- Modified files all exist: `backend/dlr_orchestrator.py`, `backend/city_pipeline.py`, `backend/tests/supabase_orchestrator_test.py`, `backend/tests/city_pipeline_test.py`, `docs/data-science/schema/city_rating_v1.md`.
- Commits found in `git rev-list 993b7db..HEAD`: `2148f98`, `b63b564`, `c2d78f7`, `200710f` (count 4, matches `commits:`).
- Acceptance: `grep "could not be cleaned"` matches in the forecast-fields section; Phase 1/2 tests unchanged since `f7eb3fb`; both verify commands exit 0 (full suite on re-run).

---
*Phase: 04-supabase-store-writer*
*Completed: 2026-10-23*
