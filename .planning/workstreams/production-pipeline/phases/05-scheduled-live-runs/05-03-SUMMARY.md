---
phase: 05-scheduled-live-runs
plan: 03
subsystem: infra
tags: [supabase, postgres, pipeline_run, run-log, psycopg, pytest, github-actions]

requires:
  - phase: 04-supabase-store-writer
    provides: "public.pipeline_run (run_id primary key pipeline_run_pk), supabase_store.upsert_run / connect / run_context, dlr_orchestrator --no-run-row"
  - phase: 05-scheduled-live-runs
    provides: "05-01 run state and outcome records in dlr_live_run.py, STORE_ARGS with --no-run-row; 05-02 forecast_status / detector_model_loaded in the child output"
provides:
  - "backend/live_run_log.py: build_run_row (pure), upsert_run_row (delegates to Phase 4's upsert_run), open_connection, pipeline_version"
  - "dlr_live_run.run_live(record_fn=None, record_run=True): pipeline_run row written before the first child, after each city and at the end; run_log {writes, failed}; --no-run-log; step-summary line"
  - "Outcome records now carry each child's sources; provider error keys are redacted"
affects: [05-04, 05-05, 05-06, 05-07, 05-08, phase-06]

actuals:
  tokens: 10700
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "The runner is the only pipeline_run writer: children run with --no-run-row, and the runner upserts one row keyed by run_id at start, after each city and at the end"
    - "A fresh database connection per run-log write, so an idle session dropped during a 300 s child cannot fail the next write"
    - "A run-log write failure is counted, logged by exception type plus redacted message (no traceback), and turns the exit code to 1 without stopping the cities"
    - "Drift guard: a test parses Phase 4's migration for the pipeline_run columns and primary key and checks the executed INSERT against them"

key-files:
  created:
    - backend/live_run_log.py
    - backend/tests/live_run_log_test.py
  modified:
    - backend/dlr_live_run.py
    - backend/tests/dlr_live_run_test.py

key-decisions:
  - "upsert_run_row delegates to supabase_store.upsert_run: it accepts a subset of columns, updates every non-key column on conflict, binds all values and casts the jsonb columns; no second SQL builder"
  - "Row timestamps are aware UTC datetimes (as Phase 4's rows are), not ISO strings, so the driver binds them as timestamptz"
  - "An outcome 'ok' city that is not healthy (forecast_status not ok/cold_start, or no anomaly model) is 'degraded' in cities_failed; this also covers a missing forecast_status"
  - "The orchestrator already has --no-run-row from Phase 4 and the runner already passes it, so no orchestrator edit was needed"
  - "pipeline_version is computed once per run (Phase 4's run_context helper) and cached in the run state"

patterns-established:
  - "Test files that call run_live pass a no-op record_fn, and an autouse fixture makes the default writer fail loudly if a test reaches it"

requirements-completed: [SCHED-01]

coverage:
  - id: D1
    description: "build_run_row turns a run state into Phase 4's pipeline_run row: cities_ok in config.LOCATIONS order, error / timeout / degraded cities in cities_failed with written, exit_code, duration_s, forecast status and error, redacted error text and fault_injected; provider_errors and sources keyed by city; finished_at None while in progress"
    requirement: SCHED-01
    verification:
      - kind: unit
        ref: "backend/tests/live_run_log_test.py#test_build_run_row_splits_ok_failed_and_degraded_cities"
        status: pass
      - kind: unit
        ref: "backend/tests/live_run_log_test.py#test_in_progress_and_finished_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/live_run_log_test.py#test_drill_city_is_marked"
        status: pass
    human_judgment: false
  - id: D2
    description: "upsert_run_row is one parameterized insert ... on conflict (run_id) do update, in one transaction; a repeated send or a re-run attempt replaces the row in place; values never appear in the SQL text; every INSERT column and the conflict key exist in the shipped migration"
    requirement: SCHED-01
    verification:
      - kind: unit
        ref: "backend/tests/live_run_log_test.py#test_upsert_is_keyed_on_the_run_and_updates_in_place"
        status: pass
      - kind: unit
        ref: "backend/tests/live_run_log_test.py#test_values_are_bound_parameters_never_sql_text"
        status: pass
      - kind: unit
        ref: "backend/tests/live_run_log_test.py#test_insert_columns_exist_in_the_phase4_migration"
        status: pass
    human_judgment: false
  - id: D3
    description: "The runner records the row at start, after each city (before the next child starts) and at the end; every row carries the run's id, attempt and window end; no secret from a crashed child reaches a row"
    requirement: SCHED-01
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_run_row_is_written_at_start_after_each_city_and_at_the_end"
        status: pass
    human_judgment: false
  - id: D4
    description: "A run-log write failure is logged redacted, makes the run exit 1 and never stops the remaining cities; --no-run-log is the only way to skip recording; the default writer opens and closes a fresh connection per write; children keep --no-run-row"
    requirement: SCHED-01
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_a_run_log_failure_fails_the_run_but_not_the_other_cities"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_no_run_log_flag_skips_recording"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_child_argv_is_accepted_by_the_real_orchestrator_cli"
        status: pass
    human_judgment: false
  - id: D5
    description: "On the live project dlr_writer can insert and update pipeline_run and the anon key cannot read it"
    requirement: SCHED-01
    verification: []
    human_judgment: true
    rationale: "Needs the real Supabase project and its grants; offline only the stub connection and the migration text are checked. Backstopped by plan 05-06 Task 2, which records it in its SUMMARY."

duration: 8 min
completed: 2026-10-24
status: complete
plan_head_before: 8da629a6ee3e8d5f0c3d76141f240ab809763f3b
plan_head_after: 27e4f7b7d83ba85e8de3388b0be7dacca369d1e1
commits: 4
---

# Phase 5 Plan 03: Run log in pipeline_run Summary

**Every live run now has one `public.pipeline_run` row that only the runner writes (inserted before the first child, upserted after each city, finished at the end), with error, timeout and degraded cities recorded in `cities_failed`; a run-log failure turns the run red without stopping the other cities.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-10-24T08:34:32Z
- **Completed:** 2026-10-24T08:43:00Z
- **Tasks:** 2 (4 commits: a RED and a GREEN commit per task)
- **Files modified:** 4 (2 new, 2 existing)

## Accomplishments

- `backend/live_run_log.py`: `build_run_row(state, env)` (pure) builds Phase 4's row from the runner state. `cities_ok` follows `config.LOCATIONS` order and holds cities with a written row, `forecast_status` `ok` or `cold_start` and a loaded anomaly model. Every other reached city is in `cities_failed` with `outcome` (`error`, `timeout`, or `degraded` for a written row with a broken ML path), `written`, `exit_code`, `duration_s`, `forecast_status`, `forecast_error` (cut to 300), the redacted `error` (cut to 1000) and `fault_injected`. `provider_errors` and `sources` are keyed by city and leave out cities with none.
- `upsert_run_row` delegates to `supabase_store.upsert_run` (reused, not rewritten), `open_connection` to `supabase_store.connect`, `pipeline_version` to `supabase_store.run_context`; all three import `supabase_store` inside the function, so building a row needs no driver.
- Runner wiring: `run_live` takes `record_fn` (default `write_run_row`, a fresh connection per write, closed after) and `record_run`. It writes once before the first child, after each city and after the last with `finished_at` set, so a job-timeout kill leaves `finished_at` null and the cities reached. Each write is wrapped: the exception type and the redacted message are logged (no traceback, so no unredacted text), the failure is counted, the cities carry on, and any failure makes the exit code 1. The returned state gains `run_log: {writes, failed}` (None under `--no-run-log`) and `pipeline_version`.
- `--no-run-log` (local dry runs; the workflow never passes it) skips recording. The Actions step summary gains `pipeline_run: N writes, M failed` (or `skipped (--no-run-log)`).
- Records now carry each child's `sources` (the child `--output` already had it), and provider error keys are redacted in `classify` because a provider message can echo a credential.
- OD-9 holds: an `error` or `timeout` city has `written` false and no rating row; the run log is its only record.

## Plan answers

- **pipeline_run primary key as shipped:** `run_id text` (`constraint pipeline_run_pk primary key`), a single column. `run_attempt` is a plain integer column, so the key does not include the attempt.
- **Was `upsert_run` reused:** yes. Delegation criteria held: it accepts any subset of `PIPELINE_RUN_COLUMNS` that includes `run_id`, updates every given non-key column on conflict (including `run_attempt`, `started_at`, `finished_at`), binds values as parameters and casts the jsonb columns.
- **Child opt-out decision:** none needed in the orchestrator. Phase 4 already added `--no-run-row` (only valid with `--store postgres`), and 05-01's `STORE_ARGS = ("--store", "postgres", "--no-run-row")` already puts it in every child's argv. `backend/dlr_orchestrator.py` and `backend/tests/dlr_orchestrator_test.py` are untouched. Phase 4's tests (`supabase_orchestrator_test.py`, with and without `--no-run-row`) and 05-01's real-CLI argv test (`record_run is False`) cover that a child does not write the row and that a direct CLI run still does.
- **Re-run behaviour:** a manual re-run of the same Actions run (same `GITHUB_RUN_ID`, attempt 2) is an upsert under the same key, so it replaces the row, including `run_attempt` and `started_at`; the runbook (05-05) must say so. Test: `test_upsert_is_keyed_on_the_run_and_updates_in_place`.
- No migration, grant or policy changed (`git log --oneline -- supabase/migrations` lists only Phase 4 commits).

## Task Commits

1. **Task 1 RED:** failing tests for the row builder and upsert, with a skeleton module so the target fails on its assertion - `9adc6e8` (test)
2. **Task 1 GREEN:** build and upsert the pipeline_run row for a live run - `887e321` (feat)
3. **Task 2 RED:** failing tests for the runner's pipeline_run writes - `1b0a9ef` (test)
4. **Task 2 GREEN:** runner records each live run in pipeline_run - `27e4f7b` (feat)

**Plan metadata:** recorded in the docs commit that follows this file (SUMMARY, then STATE/ROADMAP/REQUIREMENTS).

## TDD Gate Compliance

Both tasks are `tdd="true"`; each has a `test(05-03)` commit before its `feat(05-03)` commit.

- **Task 1 RED:** 6 failed, 0 passed. The skeleton `live_run_log.py` returns an empty row and `upsert_run_row` raises `NotImplementedError`, because a missing module would be a load failure (INVALID_RED), not RED. `gsd-tools check tdd-red-evidence` on the pytest JUnit XML for the target `test_build_run_row_splits_ok_failed_and_degraded_cities` returned `RED_EVIDENCE_OK` (`target_test_failed`, format `junit`). Semantic assessment: the target ran and failed on `assert [] == ['AUSTIN']`, the planned assertion on `cities_ok`, not on a collection, import or fixture fault; the other five failed on their first planned read of the row or the missing upsert. Evidence record: `.planning/tmp/05-03-t1-red-evidence.json` (untracked, like the rest of `.planning/tmp`).
- **Task 2 RED:** 3 failed, 18 passed (the 18 are the 05-01 tests, untouched at that point). Target `test_run_row_is_written_at_start_after_each_city_and_at_the_end` returned `RED_EVIDENCE_OK`. Semantic assessment: it failed with `TypeError` at the `run_live(..., record_fn=record)` call because `run_live` has no `record_fn` parameter, which is the planned absent behaviour and not a fixture fault; the other two failed on the missing `record_fn` and the unrecognised `--no-run-log` (exit 2). Evidence: `.planning/tmp/05-03-t2-red-evidence.json`.
- **GREEN:** the two plan test files plus the orchestrator and workflow tests: 51 passed. Full suite (`backend/tests`): 1705 passed, 48 skipped, 0 failed (baseline before this plan: 1696 passed, 48 skipped; +6 +3 new test functions).
- **REFACTOR:** none needed.
- **Mutation spot-check:** removing the detector check, the `degraded` mapping, the 1000-character cap, the omit-empty-sources rule, the fault flag or the city ordering in `live_run_log.py` each made at least one test fail. Making a run-log failure not turn the run red, un-redacting the logged message, dropping the start, per-city or final write, ignoring `--no-run-log`, and letting a write error stop the run each made at least one test fail.

## Files Created/Modified

- `backend/live_run_log.py` - `build_run_row`, `upsert_run_row`, `open_connection`, `pipeline_version`, `HEALTHY_FORECAST_STATUSES` (now the single source; `dlr_live_run` re-exports it)
- `backend/tests/live_run_log_test.py` - 6 test functions with a stub connection and a migration drift guard
- `backend/dlr_live_run.py` - `write_run_row`, `record_fn` / `record_run` on `run_live`, `--no-run-log`, `run_log` counts, step-summary line, `sources` and redacted provider error keys on records
- `backend/tests/dlr_live_run_test.py` - 3 new test functions (15 total), a no-op `record_fn` on existing `run_live` calls, `--no-run-log` on existing `main` calls that run, an autouse fixture that makes the default writer fail loudly, a fake child that now emits `sources`

## Decisions Made

- Delegated to Phase 4's `upsert_run` rather than writing another SQL builder, so the conflict rule, the jsonb casts and the column allow-list live in one place.
- Timestamps are aware UTC datetimes (Phase 4 binds datetimes, and a timestamptz parameter then has an exact type).
- `degraded` is decided by health, not only by `forecast_status == "failed"`: an 'ok' child with a missing status or no anomaly model is degraded too, so it can never be dropped from both lists (`cities_ok` requires positive evidence of health).
- `pipeline_version` is looked up once per run and stored in the run state, so the `git rev-parse` fallback runs once, not on each of up to six writes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Redact provider error keys in `classify`**
- **Found during:** Task 2
- **Issue:** the child's `provider_errors` keys are provider error text and can echo a credential. `classify` copied them into the record unredacted, and the run log would have stored them (T-05-11). Phase 4's own `build_run_row` redacts these keys; this plan's row builder is a different one.
- **Fix:** `_redact_counts` redacts every key (summing counts of keys that become equal) when the record is built.
- **Files modified:** `backend/dlr_live_run.py`
- **Verification:** the existing 05-01 assertion `provider_errors == {"synoptic: HTTP 429": 2}` still passes (nothing to redact there); the redaction itself uses the already-tested `redact()`.
- **Committed in:** `27e4f7b`

**2. [Rule 3 - Blocking] The records had no `sources`**
- **Found during:** Task 2
- **Issue:** the plan wants `sources` keyed by city, and the child `--output` carries it, but `classify` dropped it, so the row builder could not read it.
- **Fix:** `classify` stores `output.get("sources") or {}` on the record (empty for a failed child). The fake child now emits a non-empty `sources` so the test can see it.
- **Files modified:** `backend/dlr_live_run.py`, `backend/tests/dlr_live_run_test.py`
- **Committed in:** `27e4f7b`, `1b0a9ef`

### Plan-vs-instruction differences (not defects)

- **Commit shape:** the plan says one commit per task; each `tdd="true"` task has a `test(...)` commit and then the `feat(...)` commit with the plan's message, per the canonical TDD reference (same as 05-01 and 05-02). Task 1's RED commit includes a skeleton `live_run_log.py` so the RED run is a real assertion failure and not a load failure.
- **Commit trailer:** `Co-Authored-By: Claude Sonnet 5.5` instead of the plan's `Claude Opus 5.5`, per the attribution instruction for this run.
- **Second verify command:** the plan's last `pytest` call has no path. It was run as `.venv/bin/python -m pytest backend/tests` as the run instructions require (a smoke script elsewhere in `backend/` needs a token).
- **Existing tests edited (no assertion removed):** the `run_live` call sites gained `record_fn=_no_record` and two `main` calls gained `--no-run-log`, as the plan says. The fake child's `sources` changed from `{}` to a non-empty value.
- **No orchestrator change:** the plan allows it; see "Plan answers".

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking)
**Impact on plan:** no scope change; both fixes are inside the planned files.

## Discrepancies

- **A cleaning failure is invisible in this run log.** Phase 4's own `build_run_row` (used when the orchestrator writes the row, now disabled for the runner's children) marks a written city `degraded` when `pipeline.cleaning_error` is set, and `docs/data-science/schema/city_rating_v1.md` (line 181) documents that. The orchestrator's `summarize()` does not export `cleaning_error`, so the runner's record never sees it, and a city whose history cleaning failed but whose forecast was fine reads as healthy here. Closing this means adding a key to the summary row (05-02's area) or reading it another way; it is not done in this plan and is for the owner or a later plan to decide.
- **`timeout` is a new `outcome` value.** The schema doc says `cities_failed` outcomes are `error` or `degraded`, and the migration comment from 20261023 lists the same two. This plan adds `timeout` (the truths require it) plus the extra keys `exit_code`, `duration_s`, `forecast_error` and `fault_injected`. It is jsonb, so no schema change is needed, but `docs/data-science/schema/city_rating_v1.md` and the column comment are now a subset of what is stored. Updating the doc belongs with 05-05 (runbook) or Phase 6; the comment would need a migration, which this plan must not add.
- **`started_at` is overwritten on a re-run.** Because the upsert updates every given non-key column, attempt 2 of the same run replaces `started_at` as well as `run_attempt`. This matches the plan's "replaces the row".
- **pipeline_run grants on the live project are unchecked.** `dlr_writer` insert/update and the anon refusal are only read from the migration text offline; the live check is plan 05-06 Task 2.

## Issues Encountered

None. Mutation checks were run with `sed -i ''` (BSD sed); the first attempt without the empty suffix changed nothing and was repeated correctly, and the file was verified identical to the committed content afterwards. The pre-existing untracked files in the working tree (`.DS_Store`, `.obsidian/`, `graphify-out/`, the phase 07 directory, `.planning/config.json` and so on) were left unstaged; every commit used explicit paths.

## Known Stubs

None. No placeholder values, TODO or FIXME text, and no hardcoded empty data flows to a consumer. (`live_run_log.py` was a skeleton only in the RED commit `9adc6e8`.)

## Threat Flags

None. The surface touched is the one in the plan's threat model (T-05-11 to T-05-15): error text in `pipeline_run` (redacted by the runner, truncated by the builder, provider keys redacted), the anon-readability of the table (no grant changed), SQL parameters (bound only, tested with a quote and `drop table` string), run-log failure handling, and the single-writer rule (children keep `--no-run-row`).

## User Setup Required

None - no external service configuration required. The runner needs `SUPABASE_DB_URL`, which it already required.

## Next Phase Readiness

- Ready for 05-04 (model pre-flight at the marked place in the workflow), 05-05 (runbook: say that a re-run of the same Actions run replaces the row, document `--no-run-log`, correct the `cities_failed` outcome list) and 05-06 (first real dispatch; Task 2 checks the `dlr_writer` insert/update grants and that an anon GET of `pipeline_run` is refused).
- Nothing pushed.

## Self-Check: PASSED

- FOUND: `backend/live_run_log.py`, `backend/tests/live_run_log_test.py`, `backend/dlr_live_run.py`, `backend/tests/dlr_live_run_test.py`
- FOUND commits: `9adc6e8`, `887e321`, `1b0a9ef`, `27e4f7b` (all ancestors of HEAD; `check evaluation-scope --plan 05-03 --commits-only` resolves the plan)
- Acceptance criteria re-run: 6 test functions in `live_run_log_test.py`, 15 in `dlr_live_run_test.py`; `def build_run_row(` and `def upsert_run_row(` present; `build_run_row(` and `no-run-log` present in `dlr_live_run.py`; `git log --oneline -- supabase/migrations` shows only Phase 4 commits; orchestrator files unchanged; the four runner-related test files report 51 passed; full suite 1705 passed, 0 failed.

---
*Phase: 05-scheduled-live-runs*
*Completed: 2026-10-24*
