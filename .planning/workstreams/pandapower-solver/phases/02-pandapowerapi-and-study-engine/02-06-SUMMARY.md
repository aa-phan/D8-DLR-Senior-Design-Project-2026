---
phase: 02-pandapowerapi-and-study-engine
plan: 06
subsystem: study-engine
tags: [pandapower, postgres, database-tier, write-back, refusals, island, skip-honestly]

requires:
  - phase: 02 plan 04
    provides: engine.prepare_run, engine.PLACEHOLDER_BACKEND and the solve_settings record in every dispatch row
  - phase: 02 plan 05
    provides: the islanding outage as one non_convergence row through the unchanged screen
provides:
  - backend/tests/pandapower_study_job_test.py - the database tier of ENG-06, written and ready to run where Postgres exists (5 tests; 1 runs here, 4 skip here)
affects: [02-07 recorded settings wiring, Phase 3 solver column (extend these tests with it), Phase 5 hourly workflow]

actuals:
  tokens: 3274
  tasks: 2
  commits: 2
plan_head_before: f7da487c3585e112145fc46cfabd4aad379fa9d1
plan_head_after: 2278eec97798487cd1862a7e49c3922d9427697e

tech-stack:
  added: []
  patterns:
    - "The PSS/E database-tier module is copied (fixtures pg and clean_pg, _private_temp, _run through the unchanged job.run_once and the writer role); only the way a PreparedRun is built changes (engine.prepare_run)"
    - "Skip and fail rules come from psse_local_pg unchanged: a missing database skips with the harness reason, PSSE_REQUIRE_PG=1 turns that into a failure"

key-files:
  created:
    - backend/tests/pandapower_study_job_test.py
  modified: []

key-decisions:
  - "The tests assert nothing about a solver or solver_version column (Phase 3 owns that migration), so they still pass after it and can be extended there."
  - "The leak list of the one-city scaling test is built from the targets actually written to the mapping (repr, %g and %.1f), not from a constant, because the mapping is generated at run time."
  - "ENG-06 is left Pending: the database tier has been skipped here and has not run green anywhere."

requirements-completed: []

coverage:
  - id: D1
    description: "the prepared run carries case_id CASE39_FIXTURE.raw, the two file hashes and no mapping error, ready for the writer"
    requirement: "ENG-06"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_study_job_test.py#test_prepared_run_is_ready_for_the_writer"
        status: pass
    human_judgment: false
  - id: D2
    description: "a full four-city pandapower run through engine.prepare_run, the unchanged job.run_once and the real writer stores 1 run, 4 dispatch, 4 margin and its contingency rows with every completeness check ok, psse_version NULL and solver pandapower / placeholder true in every dispatch row's solve_settings"
    requirement: "ENG-06"
    verification: []
    human_judgment: true
    rationale: "Database proof. SKIPPED on this checkout (no Postgres), so it has not passed anywhere. It must be run with DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 on a machine with Postgres (the owner's Mac or CI) before ENG-06 can be called complete."
  - id: D3
    description: "a preflight refusal, a one-city scaling refusal and an islanding outage are stored the way the PSS/E job stores them (one failed run with no result rows, or a non_convergence row), with no target value in any stored error or log line"
    requirement: "ENG-06"
    verification: []
    human_judgment: true
    rationale: "Database proofs. SKIPPED on this checkout (no Postgres), so they have not passed anywhere. Same manual run as D2."

duration: 25min
completed: 2026-11-18
status: complete
---

# Phase 2 Plan 06: Database Tier of the pandapower Study Summary

**The database tier of ENG-06 is written: a full four-city pandapower run, three recorded refusals and an islanding outage go through the unchanged `job.run_once` and the real writer into a throwaway local Postgres. On this machine that tier was only SKIPPED. It has not run green anywhere yet, so ENG-06 stays Pending.**

## Database tier status (read this first)

- **Not run green.** This checkout has no Postgres (no `initdb`, `pg_ctl` or `psql`). The four database tests SKIP with the harness's reason, "set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the PSS/E Postgres proofs". Skipped is not passed.
- **Owner follow-up (unmet acceptance criterion).** Task 2's manual criterion, a run with nothing skipped, was not met here. On a machine with Postgres (the owner's Mac or CI): `DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_study_job_test.py` must pass with 5 passed and 0 skipped. It is already listed in 02-VALIDATION.md, Manual-Only Verifications ("Database tier green"), so that file was not edited.
- **What was and was not checked without a database.** I ran each of the four scenarios once through the real `job.run_once` with a recording stand-in for the connection (an ad hoc script in the scratchpad, not committed, so nothing in the repository fakes a database assertion). That confirmed the data the assertions read: outcome `fallback` / `written`; 1 run, 4 dispatch, 4 margin and 54 contingency rows; `psse_version` None; `rate_set` RATEA; `n_contingencies_with_results` 24 equal to the 24 distinct contingency ids; `solver` pandapower and `placeholder` True in all four dispatch rows; the scratch folder empty; the preflight refusal stored as `failed` at stage `mapping` with the error starting "pandapower: " and the mapping hash equal to the file's; the scaling refusal stored as one failed run at stage `apply_ratings` with the error text `1 of 4 cities failed; AUSTIN: ok; CORPUS_CHRISTI: failed at apply_ratings: scaling: ...; MIDLAND: ok; EL_PASO: ok` and none of the 14 target texts in it or in the log; the islanding outage giving exactly one `non_convergence` row with ierr 3 per city (58 contingency rows in that run). It did **not** exercise the database's own CHECK constraints, the row-level-security policies, the writer role, the transaction behaviour or `_checks` (psse_results_v1_checks.sql). Those are exactly what the manual run proves. The non_convergence rows built by `violations.non_convergence_row` match the DDL's shape rule by reading (element_type contingency, element_id equal to contingency_id, unit and the three values null), but that is a reading, not a run.

## Accomplishments

- `backend/tests/pandapower_study_job_test.py` (298 lines, 5 tests): header states the skip rules and that the file never touches Supabase and asserts nothing about a solver column; fixtures `pg`, `clean_pg`, `_private_temp` and helpers `_clock`, `_connect`, `_counts`, `_run_row`, `_table_rows`, `_checks`, `_rows`, `_prepared`, `_run` copied from `psse_study_job_test.py`.
- `test_prepared_run_is_ready_for_the_writer` (no database, runs here): `case_id` "CASE39_FIXTURE.raw", both hashes equal `run_record.file_sha256` of the files, `mapping_error` None.
- `test_tracer_engine_run_written_to_local_postgres`: the full run described above, plus the case file's hash unchanged and an empty scratch folder.
- `test_recorded_preflight_refusal`, `test_recorded_one_city_scaling_refused` (CORPUS_CHRISTI's load target is 25 times the fixture's own load, set by editing the generated mapping JSON in tmp_path; the fixture module is untouched), `test_written_island_row_is_stored` (the islanding outage passed as `contingency.extra`; the row `"<CITY>:" + ISLANDING_OUTAGE.key` per city has `violation_kind` non_convergence and `details.ierr` 3).

## Task Commits

1. **Task 1 (tracer): a full pandapower run through engine.prepare_run, job.run_once and the real writer into a throwaway local Postgres** - `c7e7181` (test)
2. **Task 2: refusals and an islanding outage stored the way the PSS/E job stores them, with no target in any stored error or log** - `2278eec` (test)

Commits measured from the ledger: `f7da487..HEAD` is 2, matching the two task commits.

## Verification (this checkout, Windows, `.venv/Scripts/python.exe`)

- pandapower 3.5.6 import check: passed (precondition of both tasks).
- Plan verify, whole module: **1 passed, 4 skipped** in 3.75 s. Every SKIPPED line carries the harness's Postgres reason. This is the plan's expected result on a checkout without Postgres.
- Task 1 second command (`PSSE_REQUIRE_PG=1`, both Postgres variables unset, `-k tracer`): exit 1, the tracer is reported as an error from the fixture's `pytest.fail` with the harness reason, so a missing database does fail the gate (T-02-22). The whole file under `PSSE_REQUIRE_PG=1`: 1 passed, 4 errors (all four database tests).
- Acceptance greps: `engine.prepare_run(` 4 matches, `job.run_once(` 1 match, `supabase.co|pooler.supabase` 0 matches; file is 298 lines (plan minimum 120).
- Staged leak scan exited 0 before each commit; full `private_leak_scan.py` exited 0 after the last commit; neither commit deletes a file.
- Frozen-file gate (PLAN=02-06) exited 0 after each commit.
- Commands written as `.venv/bin/python` ran as `.venv/Scripts/python.exe`; the `env -u ...` form ran under Git Bash. No assertion was weakened.
- Not run: the full pandapower suite (not part of this plan's verification), and any real database test.

## Deviations from Plan

### Auto-fixed Issues

None. No production file was changed and no test needed a fix.

### Notes (no code deviation)

**1. Commit ledger collision (process, as in plans 02-01 to 02-05)**
- `.git/gsd-plan-head-before-02-06` held a stale base (`7686d07`) from the old pss-e-integration workstream's own plan 02-06. It was overwritten with this plan's true base (`f7da487`) before the first commit.

**2. Database criteria unmet here (environmental, not a defect)**
- Task 2's manual acceptance criterion (a run with nothing skipped) and the plan-level "where Postgres exists" verification could not be run on this machine. See "Database tier status". Recorded as an owner follow-up; ENG-06 stays Pending.

**3. Small chance of a flaky leak check**
- The log text in `test_recorded_one_city_scaling_refused` contains the run id, which ends in 8 random hex characters. A target text of only digits (for example "5058") could in principle appear inside it by chance (roughly 0.1 percent per run across the 14 texts). The PSS/E test has the same exposure. Not changed.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-02-20 met by reading (the harness refuses non-local hosts, the ratings are a fake fetch, the grep gate shows no live host in the file), though never exercised against a database. T-02-21 is covered by the leak check in `test_recorded_one_city_scaling_refused`, proven on the data side only. T-02-22 verified: `PSSE_REQUIRE_PG=1` turns each skip into a failure. T-02-SC met (nothing installed, requirements files untouched).

## Handoff to Phase 3

Extend these tests with the `solver` and `solver_version` columns once Phase 3's migration exists. Until then the run id keeps the `psse-` prefix, which is one more reason these tests write only to a throwaway local database.

## Self-Check: PASSED

- FOUND: backend/tests/pandapower_study_job_test.py (298 lines, 5 tests)
- FOUND commits c7e7181 and 2278eec (ancestors of HEAD)
- The database tier is not claimed as passing: 4 of 5 tests SKIPPED here, none run green anywhere.
