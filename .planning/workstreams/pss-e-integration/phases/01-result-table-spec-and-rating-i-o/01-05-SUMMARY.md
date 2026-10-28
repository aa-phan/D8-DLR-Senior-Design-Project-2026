---
phase: 01-result-table-spec-and-rating-i-o
plan: 05
subsystem: job
tags: [psse, run-once, orchestration, exit-codes, postgres, redaction, pytest]

requires:
  - phase: 01-02
    provides: select_ratings, fetch_latest_rating, redaction, constants
  - phase: 01-04
    provides: run record, validate_results, the atomic writer, FakeStudy and fake_results
provides:
  - psse_job.job.run_once, the whole-run orchestration (ratings read, injected study, validation, one write at the end) with exit codes 0, 1 and 3
  - End-to-end and failure-matrix proofs from an HTTP ratings read to rows in local Postgres
affects: [pss-e-integration Phase 2 (real psspy study plugs into run_once), pss-e-integration Phase 3 (launcher maps the exit code), SCH-02]

actuals:
  tokens: 6300
  tasks: 2
  commits: 2
plan_head_before: c496583d2f1c397e38f82707c373f270d3753219
plan_head_after: cc3dfe03f60172eaf12ac67cfaa4ee2cb43ef103

tech-stack:
  added: []
  patterns:
    - "The database is connected only after the study has returned or failed; the single write is the last thing a run does (D-04)"
    - "Every message that is logged or stored is redacted twice: with the default secrets and with the secrets of the env that was passed in"
    - "One INFO summary line per run (psse run <id> outcome= status= stage= cities=) plus one WARNING line that deliberately does not repeat the 'psse run ' prefix"

key-files:
  created:
    - backend/psse_job/job.py
    - backend/tests/psse_job_test.py
  modified: []

key-decisions:
  - "A completed run whose connect() fails is reported as outcome failed, failed_stage write, status not_recorded, exit 3 (the same label the RecordFailed path uses), so an unrecorded run cannot read as a success; a failed study with an unreachable database keeps its own stage"
  - "Everything after the study (validate_results, build_run_record, result_rows) is one try block: any exception there, not only ResultsInvalid, becomes a validate_results failure and the results are dropped"
  - "finished_at is clamped to started_at for a backwards or naive second clock reading; a naive first reading raises ValueError before anything else"

patterns-established:
  - "Mutation check per plan: six plants in job.py (connect before study, failed run exits 0, no clamp, validation skipped, env redaction removed, unreachable exits 0); the env-redaction plant survived once and a test of the stored error was added"

requirements-completed: [IN-01, WB-01, WB-02]

coverage:
  - id: E1
    description: "With today's provisional labels, an HTTP ratings read, a fake study and local Postgres produce one fallback run, four static_fallback/provisional cities, 1 + 4 + 4 + 2 rows, case_id as a bare file name and every completeness check ok"
    requirement: "IN-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_job_test.py#test_tracer_run_once_http_to_postgres"
        status: pass
    human_judgment: false
  - id: E2
    description: "A StudyFailed at each of the seven study stages, or any other exception (internal), leaves one failed row with that stage, no result rows and exit 1"
    requirement: "WB-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_job_test.py#test_record_failed_study_each_stage (7 cases), test_record_unexpected_exception_is_internal"
        status: pass
    human_judgment: false
  - id: E3
    description: "A failed ratings read continues as a fallback run (four static read_failed cities, exit 0, ratings_read_error set)"
    requirement: "IN-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_job_test.py#test_record_read_failure_continues_as_fallback"
        status: pass
    human_judgment: false
  - id: E4
    description: "Incomplete results or a rating other than the selected one fail at validate_results with no result rows; zero violations is a complete 1 + 4 + 4 + 0 run"
    requirement: "WB-02"
    verification:
      - kind: integration
        ref: "backend/tests/psse_job_test.py#test_record_incomplete_results_fail_validation, test_record_zero_violations_is_complete"
        status: pass
    human_judgment: false
  - id: E5
    description: "A write failure is a recorded failure at stage write (exit 1); an unreachable database is exit 3 with no row; nothing is written before the study finishes"
    requirement: "WB-02"
    verification:
      - kind: integration
        ref: "backend/tests/psse_job_test.py#test_record_write_failure_is_recorded, test_record_unreachable_database_exit_code_3, test_no_write_before_the_study_finishes"
        status: pass
    human_judgment: false
  - id: E6
    description: "No log record and no stored error carries a database URL, password, user, project reference, host or key; the clock is clamped and the case id labelled"
    requirement: "WB-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_job_test.py#test_logs_never_carry_secrets, test_stored_error_never_carries_secrets, test_record_clock_going_backwards_is_clamped, test_record_empty_case_id_is_labelled_unknown, test_record_naive_start_raises_before_anything"
        status: pass
    human_judgment: false

duration: 13min
completed: 2026-10-28
status: complete
---

# Phase 1 Plan 05: run_once, the Whole Run Summary

**`run_once` reads the ratings, runs the injected study once, validates it and writes the run exactly once at the end, returning exit 0 (ok or fallback written), 1 (failed run recorded) or 3 (nothing could be recorded); proven from an HTTP read to rows in local Postgres, including every failure path.**

## Performance

- **Duration:** about 13 min
- **Started:** 2026-10-28T11:08Z
- **Completed:** 2026-10-28T11:21Z
- **Tasks:** 2 (one tracer, one auto/tdd)
- **Files modified:** 2 (both created)

## Accomplishments

- `job.run_once(fetch, study, connect, case_id, case_sha256=None, mapping_sha256=None, clock=None, env=None)` follows the plan's eleven steps. The start time is taken once and used for every city's age check and for `slot_time`; the run id comes from it. `select_ratings` never raises, so a failed read is a `fallback` run (D-02). The study is called once inside a try; `connect()` is called only after it (D-04), and `close()` runs in a `finally`.
- `RunOutcome(run_id, outcome, status, failed_stage, exit_code)` with statuses `written`, `already_recorded`, `failure_recorded` and `not_recorded`; `EXIT_OK = 0`, `EXIT_FAILED_RECORDED = 1`, `EXIT_NOT_RECORDED = 3`.
- Every run logs one INFO summary line (run id, outcome, status, stage, each city's source and reason) and, when there is an error, one WARNING line cut to 300 characters.
- 20 tests in `psse_job_test.py`: the tracer (HTTP, fake study, Postgres, completeness checks), seven study stages, an internal error, a failed read, two kinds of invalid results, zero violations, a write failure, an unreachable database, a backwards clock, an empty case id, a naive clock, no early write, and two secret-hygiene tests.

## Task Commits

1. **Task 1 (tracer): run_once from an HTTP ratings read through a fake study to a recorded fallback run** - `5c8a3e4` (feat)
2. **Task 2: every failure path leaves one honest record or an explicit exit 3** - `cc3dfe0` (feat)

The tracer gate: auto mode was not active and the tracer's `<verify>` is automated only, so `<verify>` was re-run (1 passed) before expansion. The tracer test was run RED first (collection failed: no `psse_job.job`).

## Decisions Made

- An unreachable database on a run that otherwise succeeded is reported as outcome `failed`, stage `write`, status `not_recorded`, exit 3. Without this the outcome field would say `fallback` for a run that was never recorded.
- All post-study work (validate, build record, build rows) shares one try block mapped to `validate_results`, so a malformed study result of any kind (a key outside the column tuple included) is recorded as a failed run instead of crashing the job.
- Carry-over fact (b) is honoured: `RecordFailed` gives exit 3 (no row exists), `WriteFailed` gives exit 1 (a failed record exists). A lost commit acknowledgement raises `WriteFailed` while the rows are present; a retry with the same run_id returns `already_recorded`. `run_once` creates a new run id per call, so that retry belongs to the launcher (Phase 3).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Failure messages are redacted with the passed-in env's secrets, and a test proves the stored error**
- **Found during:** Task 2 (mutation check)
- **Issue:** `failure_from_exception` redacts with `os.environ`, not with the `env` handed to `run_once`. A secret that appears alone in a study message (a password or project reference, not inside a URL) would be stored in `psse_run.error`. The first mutation run (removing the extra redaction) still passed, because the log line re-redacts, so no test covered the stored text.
- **Fix:** `job._redacted_failure` re-redacts the failure message with `env_secrets(env)` before the record is built; added `test_stored_error_never_carries_secrets` (a recording connection, no database) which fails when that redaction is removed.
- **Files modified:** `backend/psse_job/job.py`, `backend/tests/psse_job_test.py`
- **Commit:** `5c8a3e4` (job.py), `cc3dfe0` (test)

**2. [Rule 2 - Missing critical functionality] A naive start raises before anything, tested**
- **Found during:** Task 2
- **Issue:** The plan states the behaviour (ValueError before anything else) but lists no test.
- **Fix:** `test_record_naive_start_raises_before_anything` (no fetch, no study, no connect).
- **Files modified:** `backend/tests/psse_job_test.py`
- **Commit:** `cc3dfe0`

**Total deviations:** 2 additions, both Rule 2, inside the plan's scope. **Impact:** none on interfaces. The plan's counts become 20 tests in the module (plan: at least 18) and 16 matching `-k record` (plan: at least 15); `-k "read_failure or no_write_before"` is still exactly 2.

## Notes for the next plans

- **Phase 2:** `study(selection, context)` plugs straight into `run_once(study=...)`. The study must raise `StudyFailed(stage, message)` with one of the seven study stages, or return `StudyResults`; any other exception is recorded as stage `internal`. `psse_fakes.fake_results` shows the exact row shapes `validate_results` accepts.
- **Phase 3:** the launcher calls `run_once` and passes `exit_code` to `sys.exit`. Exit 3 is the "no record" signal SCH-02 should see as a gap. `fetch` is `functools.partial(ratings.fetch_latest_rating, env=env)` and `connect` is `functools.partial(writer.connect, url)`; `connect` takes no arguments in `run_once`.
- **Logging is not configured here:** `job.py` only creates the logger. The launcher must configure handlers and must not log the environment.

## Authentication Gates

None. The only database is a private local cluster that trusts loopback connections; no Supabase project or credential was touched.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model; T-01-27 to T-01-30 each have a named test (`test_record_failed_study_each_stage`, `test_record_unreachable_database_exit_code_3`, `test_logs_never_carry_secrets`, `test_stored_error_never_carries_secrets`, `test_record_read_failure_continues_as_fallback`, `test_record_incomplete_results_fail_validation`, `test_no_write_before_the_study_finishes`).

## Verification Results

Environment: Windows 11 Git Bash, Python 3.12 venv (`.venv/Scripts/python.exe`), pytest 9.0.3, psycopg 3.3.6, local Postgres 18.6 portable binaries on PATH for the commands only (POSIX path form `/c/Users/...`). The fixtures start and stop a private cluster under pytest's temp dir; `tasklist` shows no postgres process afterwards.

- `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 ... backend/tests/psse_job_test.py -k tracer` - 1 passed (RED first: ImportError on `psse_job.job`)
- `... backend/tests/psse_job_test.py` - 20 passed, 0 skipped
- `... backend/tests/psse_job_test.py -k record` - 16 passed
- `... backend/tests/psse_job_test.py -k "read_failure or no_write_before"` - 2 passed
- `... backend/tests/psse_schema_pg_test.py backend/tests/psse_writer_test.py backend/tests/psse_job_test.py` - 78 passed, 0 skipped
- `... backend/tests/psse_contract_test.py psse_ratings_test.py psse_run_record_test.py psse_schema_doc_test.py secret_scan_test.py` (no PG variables) - 165 passed
- `python -c "... print(job.EXIT_OK, job.EXIT_FAILED_RECORDED, job.EXIT_NOT_RECORDED)"` prints `0 1 3`
- `git status --porcelain -- backend/config.py supabase/migrations .planning/workstreams/production-pipeline docs/data-science/schema/psse_results_v1.sql` prints nothing
- Phase gate (whole suite): `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 ... -m pytest -q -p no:cacheprovider -rs` stops at collection (exit 2, 60 errors) because pandas, numpy, requests, joblib, matplotlib and fcntl are not installed in this environment (pandas and numpy must not be installed here). With `--continue-on-collection-errors` the run gives 320 passed, 7 failed, 60 errors in 108 s; all 67 failures and errors are `ModuleNotFoundError` from existing pipeline tests that import `supabase_store` or numpy/pandas (for example `dlr_live_window_check_test.py`). No psse, contract or secret-scan test failed and none was skipped. This is an environment limit, not caused by this plan.
- Mutation checks: connect-before-study, failed-run-exits-0, no clamp, validation skipped, env redaction removed and unreachable-exits-0 were each caught by a test (the env-redaction plant after `test_stored_error_never_carries_secrets` was added); `job.py` was restored byte-for-byte from a backup and `git diff` on it is empty.

## Self-Check: PASSED

- FOUND: backend/psse_job/job.py, backend/tests/psse_job_test.py
- FOUND commits 5c8a3e4, cc3dfe0 (ancestors of HEAD); `git rev-list --count c496583..HEAD` was 2 before this SUMMARY commit
