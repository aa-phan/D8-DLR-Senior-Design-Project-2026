---
phase: 05-scheduled-live-runs
plan: 01
subsystem: infra
tags: [github-actions, workflow_dispatch, subprocess, supabase, scheduling, pytest]

requires:
  - phase: 04-supabase-store-writer
    provides: "dlr_orchestrator --store postgres --no-run-row, summary key 'archived' as the row-written flag, SUPABASE_DB_URL as the only database secret, run_context() reading GITHUB_RUN_ID / GITHUB_RUN_ATTEMPT"
provides:
  - "backend/dlr_live_run.py: live runner, one dlr_orchestrator child per city with a per-city timeout, outcome records, exit policy, redaction, step summary and fault drill"
  - ".github/workflows/dlr_live.yml: workflow_dispatch-only live workflow (concurrency dlr-live, timeout-minutes 30, contents: read)"
  - "21 offline test cases (12 runner test functions, 3 workflow text checks, parametrized cases included) driven by a fake orchestrator child"
affects: [05-02, 05-03, 05-04, 05-05, 05-06, 05-07, 05-08, phase-06]

actuals:
  tokens: 11700
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "One child process per city with subprocess.run(timeout=...): a hard per-city time budget and a fresh interpreter"
    - "A city is 'ok' only with positive evidence (exit 0, an --output file, a summary row for the city, a true write flag)"
    - "Workflow inputs reach code only through an env mapping, validated against config.LOCATIONS; never inside a run: script"
    - "Secret-shaped test fixtures are assembled at run time from pieces"

key-files:
  created:
    - backend/dlr_live_run.py
    - .github/workflows/dlr_live.yml
    - backend/tests/dlr_live_run_test.py
    - backend/tests/dlr_live_workflow_test.py
  modified: []

key-decisions:
  - "STORE_ARGS = ('--store', 'postgres', '--no-run-row') and WRITE_FLAG_KEY = 'archived', taken from the 04-02 SUMMARY and confirmed against backend/dlr_orchestrator.py"
  - "Exit 0 requires forecast_status in ('ok', 'cold_start') and detector_model_loaded true for every city, so a row with no forecast_status also turns the run red"
  - "redact() also removes the password component of SUPABASE_DB_URL, not only the whole URL"
  - "The runner re-emits each child's stdout and stderr unredacted to the Actions log (GitHub masks registered secrets there); only text that enters a record or the step summary is redacted"

patterns-established:
  - "Runner tests point dlr_live_run.ORCHESTRATOR at a fake script and pass env explicitly; main() tests set the process env with monkeypatch"
  - "Workflow tests read the YAML as text with re (PyYAML is not installed and must not be added)"

requirements-completed: [PIPE-02, SCHED-01]

coverage:
  - id: D1
    description: "dlr_live.yml is dispatch-only and separate from shadow collection, with concurrency dlr-live, contents: read and timeout-minutes 30 that fits 4 x 300 s plus 10 min and the 60-minute cadence"
    requirement: PIPE-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_workflow_test.py#test_workflow_is_dispatch_only_and_separate_from_shadow_collection"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_workflow_test.py#test_timeout_fits_the_cities_and_the_cadence"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_workflow_test.py#test_every_required_secret_is_mapped_and_inputs_never_reach_a_run_script"
        status: pass
    human_judgment: false
  - id: D2
    description: "The runner rates every city in its own orchestrator child, in config.LOCATIONS order, with one shared end and the composed / ml / Postgres arguments, and those arguments are accepted by the real orchestrator CLI"
    requirement: PIPE-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_tracer_every_city_runs_in_its_own_child_and_the_run_exits_zero"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_child_argv_is_accepted_by_the_real_orchestrator_cli"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_run_end_and_slot_edges"
        status: pass
    human_judgment: false
  - id: D3
    description: "A crashing, hung, output-less, row-less or unwritten city is recorded per city with a redacted error and the others still run; the run exits 1 for any of them and for a failed forecast or missing anomaly model; no row is invented"
    requirement: SCHED-01
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_a_crashing_city_is_recorded_and_the_rest_still_run"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_a_hung_city_is_killed_at_the_timeout_and_the_rest_still_run"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_exit_zero_without_a_written_row_is_an_error"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_failed_forecast_or_missing_anomaly_model_fails_the_run_but_keeps_the_row"
        status: pass
    human_judgment: false
  - id: D4
    description: "Fault drill, required-env gate, redaction and the Actions step summary: the fault city alone runs with blank provider credentials, an unknown city is exit 2, a missing secret stops the run before any child with names only, errors are redacted and the summary table is ordered, truncated and pipe-escaped"
    requirement: SCHED-01
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_fault_city_blanks_provider_credentials_for_that_child_only"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_unknown_fault_city_is_a_usage_error"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_missing_required_env_stops_before_any_child_and_never_prints_values"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_redact_removes_secret_values_query_credentials_and_db_urls"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_run_test.py#test_step_summary_lists_cities_in_order_with_redacted_errors"
        status: pass
    human_judgment: false
  - id: D5
    description: "The live leg of the tracer (Actions run to Supabase rows on a GitHub-hosted runner) works"
    requirement: PIPE-02
    verification: []
    human_judgment: true
    rationale: "Offline the far end is only the orchestrator's --output contract; the real dispatch needs secrets, the pushed workflow and Supabase. Backstopped by plan 05-06 Task 2's first dispatch."

duration: 9 min
completed: 2026-10-24
status: complete
plan_head_before: fde51cd170f5509a173fcd79fe75deab2d6e5420
plan_head_after: 156cdc2e8fc5e33e51b3d6ade48592496077b0c1
commits: 3
---

# Phase 5 Plan 01: Live runner and dispatch-only workflow Summary

**`backend/dlr_live_run.py` runs each city in its own `dlr_orchestrator.py` child (composed providers, ML forecast, `--store postgres --no-run-row`, one shared 5-minute-floored end, 300 s per-city kill), records error/timeout/empty-output cities without stopping the rest, exits 1 on any unhealthy city, and is called by a `workflow_dispatch`-only `dlr_live.yml` with a 30-minute timeout.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-10-24T08:06:02Z
- **Completed:** 2026-10-24T08:15:26Z
- **Tasks:** 2 (3 commits: tracer feat, TDD RED test, TDD GREEN feat)
- **Files modified:** 4 (all new)

## Accomplishments

- Tracer: a dispatch-only workflow (`concurrency: dlr-live`, `cancel-in-progress: false`, `permissions: contents: read`, `timeout-minutes: 30`, `setup-python` 3.12 with pip cache) calls the runner, which runs each city one after another in `config.LOCATIONS` order. The child argv is fed to the real `dlr_orchestrator.main` in a test, so a flag rename in the orchestrator breaks this plan's tests.
- Failure handling: a non-zero child is `error` with a redacted stderr tail, a child past `CITY_TIMEOUT_S` is killed and recorded `timeout`, and an exit-0 child with no output file, no summary row or a false write flag is `error`. No row is ever written or substituted by the runner (OD-9).
- Exit policy: 0 only when every city is `ok` with `forecast_status` `ok` or `cold_start` and a loaded anomaly model; anything else exits 1 so the Actions run is red.
- Fault drill (`--fault-city` / `DLR_LIVE_FAULT_CITY`): that city's child gets `SYNOPTIC_TOKEN`, `NREL_API_KEY` and `NREL_API_EMAIL` set to empty strings; its record has `fault_injected` true; an unknown value is exit 2. The input reaches the runner only through the env mapping.
- `main` refuses to start a child when any `REQUIRED_ENV` name is unset or empty (names logged, values never), `redact()` cleans every error text, and `write_step_summary` appends an ordered, truncated, pipe-escaped table to `GITHUB_STEP_SUMMARY`.

## Phase 4 values used (precondition)

- **STORE_ARGS:** `("--store", "postgres", "--no-run-row")`. The CLI default is `--store csv`; `--no-run-row` is only valid with `--store postgres` and leaves the `pipeline_run` row to the runner (plan 05-03).
- **WRITE_FLAG_KEY:** `"archived"` (the summary row's `archived` is True only when the rating row was written; a failed city has no summary row and appears in `errors`).
- **Database secret:** `SUPABASE_DB_URL` is the only one.
- **How Phase 4's writer reads run_id:** `supabase_store.run_context()` reads `GITHUB_RUN_ID` and `GITHUB_RUN_ATTEMPT` (and the first 7 characters of `GITHUB_SHA`); without `GITHUB_RUN_ID` it makes its own `local-<stamp>-<uuid8>` id per process. The runner therefore sets `GITHUB_RUN_ID` / `GITHUB_RUN_ATTEMPT` in every child's environment to its own local id when the run is local, so all four children and the run log (05-03) share one id. In Actions the variables already exist and are passed through.

## Task Commits

1. **Task 1 (tracer): one child per city through the real orchestrator CLI, from a dispatch-only workflow** - `0e7380d` (feat)
2. **Task 2 RED: failing tests for timeouts, empty output, model checks, fault drill, env, redaction and step summary** - `27067c3` (test)
3. **Task 2 GREEN: runner timeouts, empty-output and model checks, fault drill and step summary** - `156cdc2` (feat)

**Plan metadata:** recorded in the docs commit that follows this file (SUMMARY, then STATE/ROADMAP/REQUIREMENTS).

## TDD Gate Compliance (Task 2, `tdd="true"`)

- **RED:** 13 of 21 test cases failed against the Task 1 code (the 8 that passed were Task 1's seven plus the `cold_start` case, which already exited 0). `gsd-tools check tdd-red-evidence` on the pytest JUnit XML for the target `test_a_hung_city_is_killed_at_the_timeout_and_the_rest_still_run` returned `RED_EVIDENCE_OK` (`target_test_failed`, format `junit`). Semantic assessment: the target failed because `subprocess.TimeoutExpired` escaped `run_city` (no timeout handling), not because of a collection, import or fixture fault. The other 12 failures were each the planned assertion (`'no output' in 'child output is unusable'`, `0 == 1` exit codes for failed forecast and missing model, missing `redact`, `--fault-city` not accepted, no `SystemExit` for an unknown city, no step-summary support). The evidence record is at `.planning/tmp/05-01-red-evidence.json` (untracked, like the rest of `.planning/tmp`).
- **GREEN:** all 21 tests pass; the full suite is 1676 passed, 48 skipped (baseline before this plan: 1655 passed, 48 skipped).
- **REFACTOR:** none needed.
- **Mutation spot-check:** removing the detector check from the exit policy, the DB-password redaction, the fault blanking, the "row not written" branch, the pipe escape, the timeout branch and the URL redaction each made at least one test fail.

## Files Created/Modified

- `backend/dlr_live_run.py` - the runner (`run_live`, `run_city`, `classify`, `run_end`, `slot_of`, `run_identity`, `redact`, `write_step_summary`, `main`; constants `CITY_TIMEOUT_S`, `PROVIDER`, `FORECAST_METHOD`, `STORE_ARGS`, `WRITE_FLAG_KEY`, `REQUIRED_ENV`)
- `.github/workflows/dlr_live.yml` - workflow_dispatch-only workflow with a `fault_city` input; a comment marks where 05-04 inserts the model pre-flight
- `backend/tests/dlr_live_run_test.py` - 12 test functions (21 cases with parametrization) over a fake orchestrator child
- `backend/tests/dlr_live_workflow_test.py` - 3 regex checks of the workflow text

## Decisions Made

- Taken from the plan: composed providers (OD-2), ML forecast (OD-3), Postgres store, 300 s per city, 30-minute job timeout (4 x 300 s = 20 min plus up to 10 min, under the 60-minute cadence of OD-1).
- Exit 0 needs `forecast_status` in (`ok`, `cold_start`), not just "not failed". The plan's truths say "exits 0 only when ... `forecast_status` 'ok' or 'cold_start'", while Task 2's prose names only 'failed'; the stricter truth is implemented, so a missing or unknown status is also red.
- `redact()` additionally removes the password component of `SUPABASE_DB_URL` (raw and percent-decoded) when it appears alone, because a driver message can echo the password without the URL. This is stdlib `urllib.parse` only.
- The child's own stdout and stderr are re-emitted as captured. They are not redacted, because rewriting log lines with the `key=` pattern would damage diagnostics and GitHub already masks the registered secret values in the log. Only text that enters a record, the step summary or `--summary-json` is redacted.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `sys.executable` can be a relative path**
- **Found during:** Task 2 (reading the hung-city failure output)
- **Issue:** under `.venv/bin/python -m pytest` the interpreter path is relative (`.venv/bin/python`), but each child runs with `cwd=REPO_ROOT`, so a run started from another directory would fail to find the interpreter.
- **Fix:** `child_argv` uses `os.path.abspath(sys.executable)`; the argv test compares against the same value.
- **Files modified:** `backend/dlr_live_run.py`, `backend/tests/dlr_live_run_test.py`
- **Committed in:** `156cdc2`

**2. [Rule 2 - Missing Critical] Required env, fault city and `--end` input hardening**
- **Found during:** Task 2
- **Issue:** the plan's threat T-05-01 wants the fault input kept out of shells and logs as code. An unknown value echoed with `%s` could carry newlines (log injection of Actions workflow commands), and `--end` is passed to every child's argv.
- **Fix:** the usage error formats the value with `!r`; `run_live` also raises `ValueError` for a fault city outside `config.LOCATIONS` (defence in depth); `--end` is validated against `%Y-%m-%dT%H:%M:%SZ` by argparse before any child starts.
- **Files modified:** `backend/dlr_live_run.py`
- **Committed in:** `0e7380d`, `156cdc2`

### Plan-vs-instruction differences (not defects)

- **Commit trailer:** the plan says `Co-Authored-By: Claude Opus 5.5`; the commits carry `Claude Sonnet 5.5`, the model that made them, per the attribution instruction for this run.
- **Task 2 commit split:** the plan says one commit for Task 2. The canonical TDD reference for a `tdd="true"` task asks for `test(...)` then `feat(...)`, so there are two commits (`27067c3`, `156cdc2`). The `feat` message is the one the plan specifies.
- **Signature additions (compatible):** `run_identity(env, now=None)`, `classify(..., env=None)` and `run_city(..., fault_injected=False)` gained optional parameters so tests can pin time, redaction can see the right environment and the fault flag reaches the record.
- **Extra test cases:** the model-status test also covers `nodetectorkey` (missing key counts as false) and `noforecaststatus` (no status is red), in addition to the cases the plan listed. The function count is still 12 and 3.

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** no scope change; both fixes are inside the planned files.

## Discrepancies

- **Phase 4's real summary rows do not yet carry the Phase 5 fields.** `summarize()` in `backend/dlr_orchestrator.py` (at `fde51cd`) returns no `forecast_status`, `forecast_error` or `detector_model_loaded` keys. Plan 05-02 (same wave) adds them. Until it lands, a real run through this runner records `forecast_status` None and `detector_model_loaded` false for every city and exits 1 by design. This is the same-wave dependency the plan describes, not a bug here, but 05-02 must merge before any real dispatch (05-06).
- Everything else matched the plan and Phase 4's SUMMARY (store flags, write-flag key, secret name, run id variables).

## Issues Encountered

None beyond the items above. The pre-existing untracked files in the working tree (`.DS_Store`, `.obsidian/`, `graphify-out/`, the phase 07 directory, and so on) were left unstaged; every commit used explicit paths.

## Known Stubs

None. No placeholder values, TODO or FIXME text, and no hardcoded empty data flows to a consumer.

## Threat Flags

None. The surface added is the one in the plan's threat model (T-05-01 to T-05-05): the dispatch input, secrets in child environments, child stderr and step-summary text, and the job timeout.

## User Setup Required

None in this plan. The workflow needs the repository secrets `SYNOPTIC_TOKEN`, `NREL_API_KEY`, `NREL_API_EMAIL` and `SUPABASE_DB_URL`, and nothing has been pushed; plan 05-06 pushes after the owner approves.

## Next Phase Readiness

- Ready for 05-02 (summary rows gain `forecast_status`, `forecast_error`, `detector_model_loaded`), 05-03 (the runner writes Phase 4's `pipeline_run` row, using `run_identity` and the records), 05-04 (model pre-flight step at the marked place in the workflow) and 05-05 (runbook).
- Nothing pushed: `git log origin/main..HEAD` lists only this plan's three commits; `shadow_collect.yml` and every `forecast_shadow_*.py` are unchanged from `origin/main`.

## Self-Check: PASSED

- FOUND: `backend/dlr_live_run.py`, `.github/workflows/dlr_live.yml`, `backend/tests/dlr_live_run_test.py`, `backend/tests/dlr_live_workflow_test.py`
- FOUND commits: `0e7380d`, `27067c3`, `156cdc2` (all ancestors of HEAD; `check evaluation-scope --plan 05-01 --commits-only` resolves them)
- Acceptance criteria re-run: test counts 12 and 3, constants and workflow greps pass, no `schedule`/`push`/`pull_request`/`cron` lines, shadow files unchanged, the two plan test files report 21 passed, full suite 1676 passed and 0 failed, no path under `data/` or `outputs/` in `git status`.

---
*Phase: 05-scheduled-live-runs*
*Completed: 2026-10-24*
