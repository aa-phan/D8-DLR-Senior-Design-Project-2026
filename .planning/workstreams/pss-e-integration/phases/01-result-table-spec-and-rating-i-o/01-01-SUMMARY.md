---
phase: 01-result-table-spec-and-rating-i-o
plan: 01
subsystem: database
tags: [postgres, ddl, rls, grants, psse, psycopg, pytest]

requires:
  - phase: production-pipeline Phase 4 (other workstream)
    provides: city_rating and pipeline_run tables, the UTC-hour CHECK form, the role/policy/comment conventions
provides:
  - Reference DDL (not a migration) for public.psse_run, psse_dispatched_capacity, psse_voltage_margin, psse_contingency_result and role dlr_psse_writer, with BEGIN/END copy markers for production-pipeline Phase 6
  - Read-only completeness checks (check_name, ok, detail) that name a partial run
  - Local-Postgres harness (backend/tests/psse_local_pg.py) and 45 proofs of the DDL
affects: [01-02, 01-03, 01-04, 01-05, production-pipeline Phase 6, pss-e-integration Phase 3]

actuals:
  tokens: 18900
  tasks: 2
  commits: 2
plan_head_before: 5be371be94b39a56101423d93f4cc14c1419a0f8
plan_head_after: 68b0f43601d04bc31dada54c259f9db4a05c4e6c

tech-stack:
  added: []
  patterns:
    - "Composite foreign key (run_id, run_outcome) to psse_run (run_id, outcome) plus run_outcome CHECK in ('ok','fallback') makes a result row under a failed run impossible"
    - "Immutable private tables: INSERT and SELECT grant only, RLS on, one insert policy and one select policy per table, explicit revoke from public, anon, authenticated"
    - "Test harness applies the Phase 4 migrations (explicit tuple, never a glob) under Supabase's legacy default grants before the DDL under test"

key-files:
  created:
    - docs/data-science/schema/psse_results_v1.sql
    - docs/data-science/schema/psse_results_v1_checks.sql
    - backend/tests/psse_local_pg.py
    - backend/tests/psse_schema_pg_test.py
  modified: []

key-decisions:
  - "Followed D-01/D-03/D-06 as locked: DDL is reference only, writer role holds exactly INSERT and SELECT on the four tables, applied MVA is enforced as sqrt(3) x kV x circuit amps / 1000 with no power factor"
  - "Stale or provisional fallback cities carry no city_rating link in psse_dispatched_capacity (the plan's link rule ties both link columns to rating_source = city_rating); the row that was read but not used belongs in psse_run.ratings_used JSON"

requirements-completed: [DBX-01, WB-01, WB-02]

coverage:
  - id: D1
    description: "Reference DDL applies after both Phase 4 migrations under Supabase legacy default grants, creates the four tables and dlr_psse_writer, and re-applies without error or privilege change"
    requirement: "DBX-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_schema_pg_test.py#test_ddl_round_trip_one_complete_run"
        status: pass
      - kind: integration
        ref: "backend/tests/psse_schema_pg_test.py#test_ddl_is_reapply_safe"
        status: pass
    human_judgment: false
  - id: D2
    description: "dlr_psse_writer holds exactly INSERT and SELECT on the four tables, nothing on city_rating, pipeline_run or latest_rating; anon and authenticated hold nothing"
    requirement: "DBX-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_schema_pg_test.py -k privileges (5 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Run-record, dispatch and contingency row rules, including the failed-run composite key, UTC slot rule at +05:30 and the power-factor MVA trap, are enforced by the database"
    requirement: "WB-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_schema_pg_test.py -k integrity (35 cases)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Read-only completeness checks report ok for complete runs (including zero violations and failed runs) and flag a partial run by run_id"
    requirement: "WB-02"
    verification:
      - kind: integration
        ref: "backend/tests/psse_schema_pg_test.py -k checks (3 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The reference DDL and checks file are what gets handed to production-pipeline Phase 6 (hand-off is a human step owned by plan 01-03)"
    requirement: "DBX-01"
    verification: []
    human_judgment: true
    rationale: "Whether Phase 6's owner adopts the tables is a human decision; the written spec and hand-off note are plan 01-03"

duration: 22min
completed: 2026-10-28
status: complete
---

# Phase 1 Plan 01: Reference DDL for the PSS/E Result Tables Summary

**Four private PSS/E result tables and a least-privilege `dlr_psse_writer` role as tested reference DDL: a result row can never sit under a failed run, the database itself rejects the per-conductor MW unit trap, and a read-only check names any partial run.**

## Performance

- **Duration:** about 22 min
- **Started:** about 2026-10-28T10:08Z
- **Completed:** 2026-10-28T10:31Z
- **Tasks:** 2
- **Files modified:** 4 (all created)

## Accomplishments

- `psse_results_v1.sql` creates `psse_run`, `psse_dispatched_capacity`, `psse_voltage_margin`, `psse_contingency_result` with named constraints, composite run foreign keys, RLS, unit-first comments for every column, and a guarded credential-less `dlr_psse_writer`. It creates no function, view or sequence and no grant naming `city_rating`, `pipeline_run` or `latest_rating`.
- `psse_results_v1_checks.sql` is one read-only statement returning the five completeness checks in order.
- `psse_local_pg.py` starts a private Postgres cluster (or uses a local `DLR_TEST_DATABASE_URL`), applies the roles, the two Phase 4 migrations and the DDL, and builds rows that satisfy every CHECK so a test changes one field. `PSSE_REQUIRE_PG=1` turns every skip into a failure.
- 45 tests prove the round trip, the privilege matrix, 35 integrity cases (most assert the exact violated constraint name), re-apply safety and the checks.

## Task Commits

1. **Task 1: Tracer, reference DDL applies and dlr_psse_writer round-trips one complete run** - `30cb802` (feat)
2. **Task 2: Privilege, integrity and completeness proofs, plus the read-only checks file** - `68b0f43` (feat)

**Plan metadata:** the docs(01-01) commit that holds this file, STATE.md and ROADMAP.md (see git log).

_RED for Task 1 was observed before the DDL existed: the target test errored in its `pg` fixture with `FileNotFoundError` for `psse_results_v1.sql` (the cluster started, both Phase 4 migrations applied, and the cluster stopped cleanly). That is a fixture-level failure, not a classifier-grade assertion RED, and the plan defines one commit per task, so no separate test commit was made._

## Files Created/Modified

- `docs/data-science/schema/psse_results_v1.sql` - reference DDL, region between the `-- BEGIN psse_results_v1` and `-- END psse_results_v1` lines is what Phase 6 copies (281 lines)
- `docs/data-science/schema/psse_results_v1_checks.sql` - read-only completeness checks (97 lines)
- `backend/tests/psse_local_pg.py` - local Postgres harness and row builders (not collected by pytest)
- `backend/tests/psse_schema_pg_test.py` - the proofs

## Decisions Made

- Followed the locked decisions D-01, D-03, D-06 as written. Postgres 18.6 was used locally (the plan assumed 16/17); the DDL needed no change.
- The privilege matrix also checks `MAINTAIN` when the server is version 17 or newer, so the check stays complete on newer Postgres.
- Where several CHECKs would fire on one bad row, the test asserts only the error class; where exactly one fires, it asserts the constraint name (the power-factor trap asserts `psse_dispatched_capacity_applied_mva_identity_ck`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pg_ctl start hung on Windows with captured pipes**
- **Found during:** Task 1 (first RED run; pytest never returned and two clusters were left running)
- **Issue:** `subprocess.run(..., capture_output=True)` on `pg_ctl start` waits for pipe EOF, but on Windows the postgres server inherits pg_ctl's stdout/stderr handles, so the call blocked until the server exited.
- **Fix:** `pg_ctl start` now runs with stdin, stdout and stderr set to DEVNULL (diagnostics stay in the server log under the pytest temp dir). Both leftover clusters were stopped with `pg_ctl -m immediate stop`; none is running now.
- **Files modified:** `backend/tests/psse_local_pg.py`
- **Verification:** all runs after the fix start and stop the cluster cleanly (no postgres process remains).
- **Commit:** `30cb802`

**2. [Rule 1 - Bug] Read-only test counted a semicolon inside a string literal as a second statement**
- **Found during:** Task 2 (first full run, 44 passed 1 failed)
- **Issue:** the checks file's `detail` text contains `'; first: '`, which a naive split on `;` read as a statement end.
- **Fix:** string literals are blanked before counting statements; the forbidden-word scan still runs on the full comment-stripped text.
- **Files modified:** `backend/tests/psse_schema_pg_test.py`
- **Verification:** `-k read_only` passes without a database.
- **Commit:** `68b0f43`

**3. [Rule 3 - Blocking] Explicit-URL / Windows adjustments to the harness**
- Per the plan: `unix_socket_directories` is omitted on `os.name == "nt"`. IPv6 hosts are re-bracketed in `role_url`. No other change.

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug) plus the planned Windows option. **Impact:** none on the DDL or the plan's scope; no file outside the plan's four was touched.

## Notes for the next plans

- **Link rule (affects 01-02, 01-03, 01-04):** `psse_dispatched_capacity_link_rule_ck` requires `city_rating_valid_time` and `city_rating_computed_at` to be non-null exactly when `rating_source = 'city_rating'`. A city that fell back as `stale` or `provisional` therefore must insert NULL link times; the link to the row that was read but not used can only live in `psse_run.ratings_used`. The run-record builder and the spec should say so.
- **Line endings (affects 01-03's sha256 pin):** `core.autocrlf=true` on this machine, so the checked-out DDL has CRLF while the committed blob has LF. A hash of the region between the markers must normalise line endings or it will differ between checkouts.
- **`ratings_used` check** requires only the four city keys; the inner keys are not constrained by the DDL.
- Postgres reports the first violated CHECK in constraint-name order, so tests that mutate several fields at once should assert the error class, not the name.

## Authentication Gates

None. The role is created without a credential and the tests connect over local trust auth.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or file access beyond the plan's threat model; T-01-01 to T-01-08 are each covered by a test named in the plan.

## Verification Results

Environment: Windows 11 Git Bash, Python 3.12 venv, pytest 9.0.3, psycopg 3.3.6, portable Postgres 18.6 on PATH for the commands only.

- `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_schema_pg_test.py` - 45 passed, 0 skipped
- same with `-k round_trip` - 1 passed; `-k "privileges or checks"` - 8 passed; `-k privileges` - 5 passed
- `-k read_only` without PSSE_REQUIRE_PG or a database - 1 passed
- `backend/tests/secret_scan_test.py` - 3 passed (run after the files were tracked)
- Without any PG variable the DB tests skip; with `PSSE_REQUIRE_PG=1` and no database they fail (checked)
- Plan boundary: `git status --porcelain -- supabase/migrations backend/config.py .planning/workstreams/production-pipeline` prints nothing
- Task 1 grep criteria: BEGIN 1, END 1, `create table if not exists public.psse_` 4, role create 1, grant line 1, composite references 3, "NOT a migration" 1; checks file names all 5 checks (10 matching lines including the header)

## Self-Check: PASSED

- FOUND: docs/data-science/schema/psse_results_v1.sql, docs/data-science/schema/psse_results_v1_checks.sql, backend/tests/psse_local_pg.py, backend/tests/psse_schema_pg_test.py
- FOUND commits 30cb802 and 68b0f43 (ancestors of HEAD); `git rev-list --count 5be371b..HEAD` was 2 before this SUMMARY commit
