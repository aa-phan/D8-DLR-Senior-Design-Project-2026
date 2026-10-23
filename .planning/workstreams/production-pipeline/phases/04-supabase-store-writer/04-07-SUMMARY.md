---
phase: 04-supabase-store-writer
plan: 07
subsystem: database
tags: [postgres, supabase, psycopg, secret-hygiene, reconnect, gap-closure]
gap_closure: true
gap_ids: [G-04-2]

requires:
  - phase: 04-supabase-store-writer
    provides: "04-01/04-02: connect(), redact(), SupabaseStore (read_history, write_rating, record_run), dlr_orchestrator --store postgres"
provides:
  - "connect() logs the role the server reports (select current_user), redacted against the URL secrets, project reference and host; the client-supplied pooler user is never read"
  - "connect() hands libpq the stripped URL, whether it came from the argument or from SUPABASE_DB_URL"
  - "SupabaseStore(conn, run_ctx=None, history_days=None, reconnect=None); from_env() supplies a factory that goes back through connect(); read_history, write_rating and record_run reconnect once and retry once on a lost connection"
affects: [05 scheduled runner (05-03), 06 read view (06-04, 06-05), 04-08..04-12 gap-closure plans touching supabase_store.py]

actuals:
  tokens: 6700
  tasks: 3
  commits: 5
plan_head_before: 206588fe02afd42f77428306b8ff780e5b2adb48
plan_head_after: 74b67944e2c1ded07799d92f0603538966c0ee76

tech-stack:
  added: []
  patterns:
    - "Log the server-reported identity (select current_user), never the client-supplied connection user, because a pooler user embeds the project reference"
    - "Reconnect-once helper: replace the connection and retry once only when the connection is lost (closed, broken or failing select 1); a StoreError on a healthy connection is raised unchanged"
    - "Row shaping happens outside the retried action, so a ValueError is never retried"

key-files:
  created: []
  modified:
    - backend/supabase_store.py
    - backend/tests/supabase_store_test.py
    - backend/tests/supabase_live_test.py

key-decisions:
  - "The success log redacts the server role against the URL project reference and host but not the URL user, so a bare role (dlr_writer) stays readable while a server echoing a dotted user still could not print the reference (new helper _project_identifiers)"
  - "A reconnect factory that raises a non-StoreError is wrapped in a redacted StoreError (database reconnect failed: ...) so no factory can leak a URL part through the store"
  - "No-factory stores (SupabaseStore(conn)) keep today's behavior exactly: the first StoreError propagates, nothing is retried"

patterns-established:
  - "Offline fake pooler connection (_PoolerConn) whose client user carries a project reference and whose server reports the bare role, with lose_on_op / probe_fails switches for lost-connection tests"

requirements-completed: [DB-04, DB-02]

coverage:
  - id: D1
    description: "CR-01: a dlr_orchestrator --store postgres run logs 'connected to Postgres as dlr_writer' and the project reference appears in no log record, stdout or stderr"
    requirement: "DB-04"
    verification:
      - kind: integration
        ref: "backend/tests/supabase_store_test.py#test_tracer_postgres_run_logs_the_server_role_not_the_project_reference"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_live_test.py#test_connect_logs_the_role_the_server_reports"
        status: pass
    human_judgment: false
  - id: D2
    description: "IN-02: connect() passes the stripped URL to libpq for an argument with a trailing newline and for a padded SUPABASE_DB_URL; a trailing-newline URL connects to a local Postgres"
    requirement: "DB-04"
    verification:
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_connect_strips_whitespace_around_the_url_before_connecting"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_live_test.py#test_a_url_with_a_trailing_newline_connects"
        status: pass
    human_judgment: false
  - id: D3
    description: "WR-03: the store reconnects once and retries once on a lost connection for each of the three operations, never retries a healthy-connection failure, raises a redacted StoreError on a failed reconnect and tries again on the next call, and keeps the run_id"
    requirement: "DB-02"
    verification:
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_store_reconnects_once_when_the_connection_was_lost"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_store_reconnects_before_using_a_connection_already_closed"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_store_does_not_retry_a_failure_on_a_healthy_connection"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_a_lost_connection_is_detected_by_a_failing_probe"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_a_failed_reconnect_raises_a_redacted_store_error_and_the_next_call_tries_again"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_a_store_without_a_reconnect_factory_raises_as_before"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_live_test.py#test_store_recovers_from_a_terminated_backend"
        status: pass
    human_judgment: false

duration: 13min
completed: 2026-10-23
status: complete
---

# Phase 4 Plan 07: Connection handling gap closure (CR-01, IN-02, WR-03) Summary

**`SupabaseStore` now logs only the server-reported role (never the pooler user carrying the project reference), connects with the stripped URL, and reconnects once per operation when its pooler session is dropped.**

## Performance

- **Duration:** about 13 min
- **Started:** 2026-10-23T21:25Z (approximate; the start timestamp was not captured at the first command)
- **Completed:** 2026-10-23T21:38Z
- **Tasks:** 3 (1 tracer, 2 TDD)
- **Files modified:** 3 (`backend/supabase_store.py`, two test files)

## Accomplishments

- CR-01 closed. The success log line `connected to Postgres as ...` read `conn.info.user`, the client-supplied pooler user `dlr_writer.<project-ref>`. It now logs `select current_user` from the server, redacted against the URL secrets, project reference and host. `grep -c "info.user" backend/supabase_store.py` prints 0.
- IN-02 closed. `connect()` rebinds `url` to `str(url).strip()` after the emptiness check, so the stripped URL is the one redacted and the one connected.
- WR-03 closed. `SupabaseStore` takes an optional `reconnect` factory; `from_env()` passes `lambda: connect(url)`, so a reconnect re-reads the URL and re-applies the statement timeout and UTC settings. Every run in Phase 5 now survives one dropped pooler session, and the run row (OD-9, the only record of a failed city) is still written.

## Findings: commit, failing-first evidence, live-local result

| Finding | Commit(s) | Failing-first evidence | Live-local |
|---|---|---|---|
| CR-01 (Task 1, tracer) | `20b6010` fix | `test_tracer_postgres_run_logs_the_server_role_not_the_project_reference` failed before the fix on `assert ['connected to Postgres as dlr_writer.qxprojrefqx'] == ['connected to Postgres as dlr_writer']` (the log carried the pooler user). Passed after. | `test_connect_logs_the_role_the_server_reports` passed against a throwaway local Postgres (DLR_TEST_PG_AUTOSTART=1) |
| IN-02 (Task 2) | `b612a22` test (RED), `1fce522` fix | `test_connect_strips_whitespace_around_the_url_before_connecting` failed on `assert ['postgresql://...postgres\r\n'] == ['postgresql://...5432/postgres']` (libpq received the unstripped URL). Live RED: `database "dlr_test\n" does not exist`. | `test_a_url_with_a_trailing_newline_connects` passed after the fix |
| WR-03 (Task 3) | `484fad1` test (RED), `74b6794` fix | Nine offline tests failed with `TypeError: SupabaseStore.__init__() got an unexpected keyword argument 'reconnect'`; the failed-reconnect test failed on `assert 1 == 2` (current code made one connect attempt, not two). Live RED: `StoreError: could not read AUSTIN history: terminating connection due to administrator command`. | `test_store_recovers_from_a_terminated_backend` passed: after `pg_terminate_backend`, the same store read history, wrote a rating row and recorded the run row; 2 rating rows share one run_id, 1 run row |

TDD semantic assessment of RED evidence: each RED failed on the planned behavior (the unstripped URL reaching libpq, the missing reconnect capability, the dropped session surfacing as a StoreError), not on a syntax, import or fixture fault. The RED runs were pytest console output, not a classifier-supported TAP/JUnit report, so `gsd check tdd-red-evidence` was not run; the assertion text above is the evidence.

## Task Commits

1. **Task 1: log the server role (CR-01, tracer)** - `20b6010` (fix)
2. **Task 2: connect with the stripped URL (IN-02)** - `b612a22` (test, RED), `1fce522` (fix, GREEN)
3. **Task 3: reconnect once on a lost connection (WR-03)** - `484fad1` (test, RED), `74b6794` (fix, GREEN)

**Plan metadata:** committed separately as `docs(04-07): complete connection handling gap-closure plan`.

## Verification Results

- `pytest backend/tests/supabase_store_test.py -k "tracer_postgres_run_logs or connection_failure or missing"`: 2 passed.
- `DLR_TEST_PG_AUTOSTART=1 pytest backend/tests/supabase_live_test.py`: 37 passed, 0 skipped.
- `pytest backend/tests/supabase_store_test.py backend/tests/supabase_orchestrator_test.py backend/tests/supabase_run_log_test.py`: 57 passed, 3 skipped (the 3 skips are the pre-existing env-gated tests in those files).
- Full suite `pytest -q -p no:cacheprovider`: 1518 passed, 46 skipped (gated live tests), 0 failed.
- `grep -n "current_user" backend/supabase_store.py` shows the query inside `connect()`; `grep -n "reconnect"` shows the constructor keyword, the `from_env` factory and the retry helper.

## Files Created/Modified

- `backend/supabase_store.py` - `connect()` logs the server role from a stripped URL; `_project_identifiers()` helper; `SupabaseStore` reconnect-once (`_flagged_lost`, `_lost`, `_replace_connection`, `_with_reconnect`); module docstring and class docstring updated.
- `backend/tests/supabase_store_test.py` - `_PoolerConn` fake, CR-01 tracer through `dlr_orchestrator.main`, IN-02 test, six WR-03 tests (the reconnect test is parametrized over three operations and two lost-connection flags).
- `backend/tests/supabase_live_test.py` - server-role log, trailing-newline URL, terminated-backend recovery; `import logging` and `import time` added.

## Decisions Made

- The success log redacts the server role against the URL project reference and host but not the URL user, per the plan, so `dlr_writer` stays readable.
- A reconnect factory raising a non-StoreError is wrapped in a redacted `StoreError("database reconnect failed: ...")`.
- A lost-connection check before the operation uses only the `closed`/`broken` flags (no probe on every call); the `select 1` probe runs only after a failure.

## Deviations from Plan

### Auto-fixed Issues

None for Rules 1-4. Minor notes, none of which changed the plan's behavior:

1. **Commit split for the TDD tasks.** The plan names one `fix(04-07)` commit per task. Tasks 2 and 3 are `tdd="true"`, so per `tdd.md` each has a `test(04-07)` RED commit before its `fix(04-07)` commit (5 commits instead of 3). The commit messages of the fix commits are the ones the plan names.
2. **Co-Authored-By line.** The plan text says `Claude Opus 5.5`; the dispatch attribution instruction says `Claude Sonnet 5.5`, which takes precedence, and is what the commits carry.
3. **One WR-03 test passes before the change.** `test_a_store_without_a_reconnect_factory_raises_as_before` is a regression guard for today's behavior, so it passed on the pre-change code by design. The other nine WR-03 test cases failed first.
4. **Small addition inside the plan's "redacted StoreError" requirement.** `_replace_connection` wraps a non-StoreError from the factory in a redacted StoreError (see Decisions).

**Total deviations:** 0 rule-based auto-fixes, 4 notes above. **Impact on plan:** none.

## Issues Encountered

- The first full-suite run exceeded the 120 s default tool timeout (the suite takes about 160 s); it was re-run in the foreground with a larger timeout and passed.
- A `gsd-tools` safety lookup for the protected-branch check could not be run (the `node ... gsd-tools.cjs` invocation form failed in the shell); `allow_default_branch_commits: true` is set in both `.planning/config.json` and the workstream config, and the orchestrator dispatched this plan onto main, so the commits were made on `main` deliberately.

## Known Stubs

None.

## Threat Flags

None. The plan's register (T-04-29 success-log disclosure, T-04-30 reconnect path, T-04-31 dropped connection, T-04-32 retried upsert) is covered by the tracer test, the failed-reconnect redaction test, the reconnect tests and idempotent upserts. No new endpoints, auth paths or schema changes.

## User Setup Required

None - no external service configuration required. Nothing connected to the real Supabase project; every test used fakes or the throwaway local Postgres.

## Next Phase Readiness

- CR-01 is fixed before any scheduled `--store postgres` run executes at INFO in GitHub Actions (Phase 5).
- Signatures stay backward compatible (new parameter is an optional keyword), so 05-03, 06-04 and 06-05 callers are unaffected.
- Gap-closure plans 04-08 to 04-12 may touch `backend/supabase_store.py`; they start from `74b6794`.

---
*Phase: 04-supabase-store-writer*
*Completed: 2026-10-23*

## Self-Check: PASSED

- Files modified exist: `backend/supabase_store.py`, `backend/tests/supabase_store_test.py`, `backend/tests/supabase_live_test.py`.
- Commits `20b6010`, `b612a22`, `1fce522`, `484fad1`, `74b6794` are ancestors of HEAD; `git rev-list --count 206588f..HEAD` = 5 (matches `actuals.commits`).
- All task acceptance criteria re-checked: tracer and WR-03 tests failed first and pass; `info.user` count 0; `current_user` inside `connect()`; both verify commands per task exit 0; full suite 0 failed; live-local 0 skipped.
