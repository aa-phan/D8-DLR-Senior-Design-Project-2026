---
phase: 03-laptop-run-and-handover
plan: 03
subsystem: database
tags: [credential-proof, dbx-02, postgres, privileges, rest, rollback, mutation-tested]

requires:
  - phase: 01-writer-and-contract
    provides: dlr_psse_writer role and grants in the reference DDL, writer.connect and write_run, ratings.fetch_latest_rating, run_record, redaction
  - phase: 02-study
    provides: dispatch.build_dispatch_row
provides:
  - psse_job.credcheck (CheckRow, PASS, FAIL, SKIP, role_checks, rest_checks, synthetic_run, write_proof, format_report, checks_ok, run, EXIT_OK 0, EXIT_CHECK_FAILED 6)
  - backend/tests/psse_credcheck_test.py with RestStandIn, the loopback PostgREST stand-in plan 03-06's rehearsal imports
affects: [03-04 launcher credcheck mode, 03-06 guide and rehearsal, 03-08 runbook step 8]

actuals:
  tokens: 14800
  tasks: 3
  commits: 3
plan_head_before: 21296f78f983c6958efda2ed92bce2cf99244835
plan_head_after: d9d458d32a6ce0c7d496f17aaaf7e51ebbed1803

tech-stack:
  added: []
  patterns:
    - "every privilege statement is where-false and needs exactly one privilege, run inside conn.transaction(force_rollback=True); only SQLSTATE 42501 is a refusal"
    - "recording connection proxy that asks the server for its transaction status before each statement and tolerates assignment to autocommit and read_only"
    - "fault helper that plants a grant as the superuser, asserts the exact set of failing checks, reverts in a finally block and re-asserts all green"

key-files:
  created:
    - backend/psse_job/credcheck.py
    - backend/tests/psse_credcheck_test.py
  modified: []

key-decisions:
  - "The role-leg statements need exactly one privilege each (select 1 ... where false, insert ... select 'AUSTIN' where false, update ... set rating_amps = 1 where false), so a missing SELECT cannot mask a planted UPDATE or INSERT grant"
  - "The privilege checks use has_any_column_privilege for SELECT, INSERT, UPDATE and REFERENCES, so a column-level grant is seen as well as a table-level one"
  - "The session is deliberately not read-only (see Deviations 2)"
  - "Details name relations, privileges, SQLSTATE codes, HTTP statuses and counts only; role memberships are reported as a count"

patterns-established:
  - "Mutation harness outside the repository (scratchpad mutate_0303.py): exact-text replace, whole test file run, byte-for-byte restore"

requirements-completed: [DBX-02]

duration: about 2 h
completed: 2026-10-29
status: complete
---

# Phase 3 Plan 03: Credential proof Summary

**`credcheck.run` proves with the job's own credential that dlr_psse_writer can insert into and select from the four result tables and holds nothing else, and that the publishable key reads ratings but is refused (401 or 403) when it tries to change city_rating. Every check is held to a planted fault and a mutation, and the proof changes nothing.**

## Commits

| Commit | Subject |
|--------|---------|
| a44d6a8 | feat(03-03): tracer - the role leg of the credential proof passes as dlr_psse_writer and fails as a superuser |
| c500f53 | test(03-03): each planted privilege is a named failure and the REST leg refuses writes with 401 or 403 |
| d9d458d | test(03-03): the opt-in write proof inserts a complete run and nothing survives, and the report names no secret |

`commits: 3` is measured (`git rev-list --count 21296f7..d9d458d`); the docs commit of this SUMMARY is not counted.

## Accomplishments

- `role_checks`: six catalog checks (role attributes, memberships, INSERT and SELECT on the four tables, nothing else on them, nothing on any other relation of schema public, no executable SECURITY DEFINER function in public) and seven where-false statements, each in a transaction forced to roll back.
- `rest_checks`: ratings read through the job's own `fetch_latest_rating` (its key and URL guards apply), then zero-match PATCH and DELETE (`city=eq.__no_such_city__`, apikey header only); nothing is sent after a failed read.
- `synthetic_run` and `write_proof`: a complete synthetic fallback run (1 + 4 + 4 + 2 rows) from the job's own functions, written with `writer.write_run` inside a forced rollback, counted inside (1, 4, 4, 2) and outside (0).
- `run`: role leg, REST leg or one `rest:skipped` row, opt-in write proof; exit 0 only without a FAIL, else 6; a connection failure prints one redacted line.

## Test results

- `psse_credcheck_test.py` (PG prefix, PSSE_REQUIRE_PG=1): 26 passed, 0 skipped (`-k fault`: 8 passed).
- `psse_contract_test.py` plus `secret_scan_test.py`: 13 passed.
- Full `psse_*_test.py` plus `secret_scan_test.py` (informational, the wave-end gate is the orchestrator's): 595 passed, 0 skipped.
- Own-changes gate (PLAN=03-03): exit 0 after each commit.
- No postgres process left running after any run.

Red first: Task 1 failed at import (no module). In Task 2 the eight REST and fault tests that depended on new code were red before it; the same run also showed the planned `set rating_amps = rating_amps` statement hiding the UPDATE fault (see Deviations 1). Task 3: all nine new tests were red before the code.

## Mutation results (each planted in credcheck.py, whole test file run, restored byte for byte; `git diff --quiet` on both files passed afterwards)

| Planted fault | Red tests (named ones all red) |
|---------------|-------------------------------|
| write proof without the forced rollback | test_write_proof_inserts_a_complete_run_and_nothing_survives (rows survive), test_write_proof_is_off_by_default, test_write_proof_failure_reported_and_still_rolled_back, test_run_exit_codes_and_skip_rest, test_run_output_names_no_secret, test_run_session_is_not_read_only_because_that_would_hide_the_proof |
| any exception counts as a refusal | test_run_inconclusive_error_names_no_text, test_run_session_is_not_read_only_because_that_would_hide_the_proof (the plan named a fault test and the superuser tracer: those stay green, because a planted grant and a superuser make the statements succeed, not raise; the inconclusive-error tests are what catch it) |
| nothing_on_other_relations always passes | test_tracer_..., test_fault_update_on_city_rating, test_fault_public_grant_on_pipeline_run, test_planted_column_level_update_is_seen |
| PATCH and DELETE sent after a failed read | test_rest_read_failure_skips_the_write_attempts, test_rest_secret_key_refused_and_nothing_sent, test_run_exit_codes_and_skip_rest |
| apikey value in a detail text | test_run_output_names_no_secret, test_rest_requests_are_zero_match_and_apikey_only |
| URL in a detail text | test_run_output_names_no_secret |
| write proof runs without the flag | test_write_proof_is_off_by_default, test_run_exit_codes_and_skip_rest, test_run_active_statements_all_run_in_a_forced_rollback_transaction |
| active statements without the forced rollback | test_run_active_statements_all_run_in_a_forced_rollback_transaction |
| run makes the session read-only | test_run_session_is_not_read_only_because_that_would_hide_the_proof, test_write_proof_is_off_by_default, test_run_exit_codes_and_skip_rest, test_run_output_names_no_secret, test_run_active_statements_... |
| column-level privilege not seen | test_planted_column_level_update_is_seen |
| update statement reads a column | test_fault_update_on_city_rating, test_planted_column_level_update_is_seen |
| HTTP 404 counts as a refusal | test_rest_inconclusive_status_fails |
| write attempt matches a real city | test_rest_requests_are_zero_match_and_apikey_only |

The eight planted privileges themselves (UPDATE on city_rating, INSERT revoked on a result table, PUBLIC grant on pipeline_run, UPDATE and DELETE on psse_run, a role membership, a SECURITY DEFINER function, CREATEROLE) are the `test_fault_*` tests: each plants as the superuser, asserts the exact set of failing checks (the named ones and no other), reverts in a finally block and asserts all 13 checks green again.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The planned statements let a missing SELECT mask a planted UPDATE or INSERT grant**
- **Found during:** Task 2 (the red run: `test_fault_update_on_city_rating` failed)
- **Issue:** `update ... set rating_amps = rating_amps where false` reads the column, so it needs SELECT as well as UPDATE; the writer has no SELECT on city_rating, so it is refused with 42501 even when UPDATE is planted, and the check stays PASS. The planned insert-select has the same flaw, and `select *` needs every column.
- **Fix:** each statement needs one privilege: `select 1 ... where false`, `insert into public.city_rating (city) select 'AUSTIN' where false`, `update ... set rating_amps = 1 where false`, `update public.psse_run set job_version = 'credcheck' where false`. The mutation "update statement reads a column" turns the fault test red.
- **Files modified:** backend/psse_job/credcheck.py
- **Commit:** c500f53

**2. [Rule 1 - Design, per the 03-02 lesson] No read-only session in this plan**
- **Found during:** reading the 03-02 lesson against this plan
- **Issue:** the plan relies on a forced-rollback transaction, not a read-only one, and a read-only session would be wrong here: PostgreSQL checks read-only before privileges, so INSERT, UPDATE and DELETE are refused with 25006 whatever the role may do (verified in a scratch run on 18.6: update and delete as the writer gave 25006 in a read-only transaction, 42501 for select), and a planted write grant would never be seen.
- **Fix:** `conn.transaction(force_rollback=True)` is used (it works on the autocommit connection writer.connect returns) and proven by `test_run_active_statements_all_run_in_a_forced_rollback_transaction` (a proxy asks the server for its transaction status before each statement: 2 inside a block; a control shows 0 outside one) and by the write proof's control, which writes the same synthetic run normally and sees 1, 4, 4, 2 rows persist. `test_run_session_is_not_read_only_because_that_would_hide_the_proof` shows the 25006 masking and that `run` never sets `read_only`. The recording proxy tolerates assignment to autocommit and read_only.
- **Files modified:** backend/psse_job/credcheck.py, backend/tests/psse_credcheck_test.py
- **Commit:** a44d6a8, d9d458d

**3. [Rule 2 - Correctness] Column-level grants are checked**
- **Issue:** has_table_privilege (D-01) is false for a column-level UPDATE, so `grant update (rating_amps) on city_rating` would pass.
- **Fix:** SELECT, INSERT, UPDATE and REFERENCES use has_any_column_privilege (true for a table-level or a column-level grant). Extra test `test_planted_column_level_update_is_seen` (named so that `-k fault` still selects exactly the eight planned tests).
- **Commit:** c500f53

**4. [Plan wording] "no statement starting with insert" without write_proof**
- The role leg's own `refused:insert_city_rating` is a where-false insert into city_rating, so the test asserts that it is the only insert and that none reaches a result table; with the flag it asserts exactly 11 inserts into the result tables, each executed inside the forced-rollback block and a server-side transaction.

**5. Minor**
- `contract.RunContext` has `case_id`, not `case_label`; the synthetic run uses `case_id="credcheck-synthetic"`.
- `write_proof` takes an optional `env` (redaction secrets) beyond the planned `(conn, now=None)`; `run` passes it.
- Role memberships are reported as a count (D-06), not by role name.

## Authentication gates

None.

## Known Stubs

None.

## Threat Flags

None. T-03-13 to T-03-18 are covered by the tests and mutations above; T-03-19 (functions outside schema public, service_role, owner) stays accepted.

## Honest scope: UNVERIFIED items handed to plan 03-08 (runbook step 8)

Proved on local Postgres 18.6 and a loopback stand-in only. Not proved:
- that Phase 6's live migration applied the same grants and that `latest_rating` exists and is readable;
- that Supabase's session pooler accepts the custom role in the form `ROLE.PROJECT-REF` (question 1 of the plan);
- that role memberships, function privileges and other schemas on the live project are clean (live Supabase has objects the local database lacks);
- that the live publishable key answers 401 or 403 to the PATCH and DELETE (PostgREST maps 42501 to 401 or 403);
- that a where-false statement is refused the same way on the live server (verified for 18.6 only);
- whether `--write-proof` may run on the live database at all (question 2; a rolled-back insert leaves dead tuples; the owner decides).
Plan 03-04's launcher must keep passing a connection that tolerates assignment to `autocommit` and `read_only`, and must not add `argparse` to credcheck (it parses `--skip-rest` and `--write-proof` and calls `credcheck.run`). Plan 03-06 may import `RestStandIn` from `psse_credcheck_test` and should check the exit codes 0 and 6 against the launcher's table.

## Self-Check: PASSED

- Files exist: backend/psse_job/credcheck.py, backend/tests/psse_credcheck_test.py
- Commits a44d6a8, c500f53, d9d458d are ancestors of HEAD
