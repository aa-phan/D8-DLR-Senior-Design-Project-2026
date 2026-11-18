---
phase: 03-solver-tag-migration-and-per-solver-gaps
plan: 04
subsystem: pandapower-engine-solver-tag
tags: [solver-tag, pandapower, run-id-prefix, parity, recording-connection, database-rehearsal]

requires:
  - phase: 03 plan 01
    provides: migration 20261118200000 (solver column, widened run-id pattern, tie constraint) and psse_local_pg.apply_solver_schema, written there and only SKIPPED on this machine
  - phase: 03 plan 02
    provides: contract.register_solver_tag, RUN_ID_PREFIXES, TAGGED_RUN_COLUMNS, INSERT_RUN_TAGGED_SQL, job.run_once(solver=), the results-versus-run solver cross-check
  - phase: 02 plan 04
    provides: engine.prepare_run and _recording_study (psse_version None, version in solve_settings)
provides:
  - api.py registers the pandapower tag with run-id prefix pp on import, next to study.register_solver
  - engine._recording_study stamps solver=SOLVER and solver_version (the adapter's version) on every pandapower study result
  - backend/tests/pandapower_solver_tag_test.py - tracer, parity, refusal tests that run here, and three database tests that skip here
  - the two Phase 2 pandapower tests brought in step with the tagged run
affects: [Phase 5 hourly runner (OPS-05), Phase 6 per-solver view, 03-05]

actuals:
  tokens: 5255
  tasks: 3
  commits: 3
plan_head_before: 47fe3d9059cb4ac204f5e5a9810d9ccd111cee43
plan_head_after: 89e3a928ee1c25ccaea1c35f24a0d0bbebc64c57

tech-stack:
  added: []
  patterns:
    - "A solver package registers its database tag on import (contract.register_solver_tag next to study.register_solver); psse_job still names neither"
    - "The engine stamps its own tag on its results; the run loop refuses results whose solver differs from the run's tag, so a run started with the default tag fails at validate_results instead of being stored as PSS/E"
    - "One parity test compares the Python registry with the migration's check constraints by reading the comment-stripped SQL text"

key-files:
  created:
    - backend/tests/pandapower_solver_tag_test.py
  modified:
    - backend/pandapower_job/api.py
    - backend/pandapower_job/engine.py
    - backend/tests/pandapower_engine_test.py
    - backend/tests/pandapower_study_job_test.py

key-decisions:
  - "solver_version is the bare version string the adapter reports (assumption A7); psse_version stays None for a pandapower run"
  - "The runner (Phase 5) must call job.run_once(..., solver=engine.SOLVER); the default tag is refused at validate_results, never stored as PSS/E"
  - "No production change beyond api.py and engine.py was needed for the parity and refusal tests"

requirements-completed: []

coverage:
  - id: D1
    description: "A four-city pandapower study run through run_once(solver=engine.SOLVER) is written with the tagged insert: a pp- run id, solver pandapower, solver_version equal to the installed pandapower version, psse_version NULL"
    requirement: "DB-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_solver_tag_test.py#test_tracer_engine_run_is_written_tagged"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_tracer_four_cities_in_memory"
        status: pass
    human_judgment: false
  - id: D2
    description: "The Python tag vocabulary, prefixes and built run ids equal the migration's check constraints; registration is idempotent and a second prefix is refused"
    requirement: "DB-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_solver_tag_test.py#test_parity_tag_vocabulary_equals_the_migration"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_solver_tag_test.py#test_parity_built_run_ids_match_the_migration_pattern"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_solver_tag_test.py#test_parity_registration_is_idempotent_and_fixed"
        status: pass
    human_judgment: false
  - id: D3
    description: "The engine's study run with the default tag is never stored as PSS/E results (one failed psse- run at validate_results, no result rows); a refused preflight run as pandapower is stored tagged"
    requirement: "DB-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_solver_tag_test.py#test_refused_default_tag_never_stores_results"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_solver_tag_test.py#test_refused_preflight_is_stored_tagged"
        status: pass
    human_judgment: false
  - id: D4
    description: "On a throwaway Postgres with the solver migration applied, the real writer as dlr_psse_writer stores the tagged four-city run, a pp- run sent as psse by either insert is refused by psse_run_solver_run_id_ck, and both solvers sit side by side in one hour"
    requirement: "DB-02"
    verification: []
    human_judgment: true
    rationale: "Database proof. The three test_db_* tests and the four tagged study-job database tests were written but only SKIPPED on this machine (no Postgres); the SQL has never run on a real database."

duration: 13min
completed: 2026-11-18
status: complete
---

# Phase 3 Plan 04: Pandapower Runs Carry Their Tag Summary

**Importing `pandapower_job.api` now registers the `pandapower` tag with run-id prefix `pp`, `engine._recording_study` stamps `solver` and the installed pandapower version on every study result, and a real four-city engine run through `job.run_once(solver=engine.SOLVER)` reaches the writer as one tagged `pp-` insert, while the same study with the default tag becomes one failed run with no figures instead of PSS/E results.**

## Database tier status

Four groups of proofs in this plan need a database and were **only SKIPPED on this machine** (Postgres is not installed here). They have not run anywhere, and nothing below claims them:

- `backend/tests/pandapower_solver_tag_test.py::test_db_tagged_rehearsal_through_the_real_writer` - the engine's four-city run, started as a pandapower run, written by the real writer as `dlr_psse_writer` on the migrated schema: 1 run, 4 dispatch and 4 margin rows, stored `solver` pandapower, `solver_version` equal to the installed version, `psse_version` NULL, every completeness check ok.
- `test_db_a_pandapower_run_cannot_be_stored_as_psse` - executed directly as the writer role (the writer's own check bypassed): `INSERT_RUN_SQL` with a `pp-` id, and `INSERT_RUN_TAGGED_SQL` with a `pp-` id and solver `psse`, are both refused with `psse_run_solver_run_id_ck`, and no row exists afterwards.
- `test_db_both_solvers_side_by_side_in_one_hour` - a PSS/E run and a pandapower run started in the same UTC hour are both stored, one `psse-` run with no solver version and one `pp-` run.
- The four existing database tests in `pandapower_study_job_test.py` (tracer, preflight refusal, one-city scaling refusal, island row), now on the migrated schema and asserting the tag (solver pandapower, version for written runs and NULL for failed ones, a `pp-` id).

What this means: the tagged insert, the database tie and the writer role's permissions on the new columns have never been exercised by a real Postgres from this plan. The Python side (what the job builds, what the writer is handed, that the vocabulary matches the migration's text) is proven here without a database. One check that I made without a database: the helper rows the direct-insert test uses were run through `_bind` here, and they bind to exactly 17 and 19 parameters. The SQL itself was not executed.

Without a database and with `PSSE_REQUIRE_PG=1`, the three new `test_db_*` tests all error (`3 errors`), so a skip cannot pass for proof under the strict flag.

The owner's Mac command (must report **0 skipped**, nothing failed):

```
DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_solver_tag_test.py backend/tests/pandapower_study_job_test.py
```

**DB-02 is left Pending** in REQUIREMENTS.md: both halves of the Python contract are done and proven (plan 03-02 and this plan), but the database tie that keeps a pandapower run from being stored as PSS/E is only skipped here, and plan 03-01's migration it depends on has not run green anywhere either.

## Accomplishments

- `api.py`: `from psse_job import contract, psse_api, study`, and `contract.register_solver_tag(SOLVER_NAME, "pp")` directly after `study.register_solver(SOLVER_NAME, factory)`, with a comment saying the database tag and prefix come from the same import and that `psse_job` never names this solver. `pandapower_import_gate_test.py` still passes (no file under `backend/psse_job/` was touched, so the word `pandapower` still appears in none).
- `engine.py`: `_recording_study` returns `results._replace(dispatch=dispatch, psse_version=None, solver=SOLVER, solver_version=results.psse_version)`; the module docstring's "Settings provenance" paragraph and the function docstring now say the run row carries `solver` and `solver_version` and that the runner must pass `solver=engine.SOLVER`.
- `pandapower_solver_tag_test.py` (new, 6 tests that run here, 3 that skip): the tracer through a recording connection, three parity tests that read the migration's comment-stripped text (vocabulary equals the `solver in (...)` list and the tie pairs, built run ids full-match the migration's pattern and the pattern's prefix alternation equals the registered prefixes, re-registration is idempotent and a different prefix raises `ValueError`), the default-tag refusal and the stored-tagged preflight refusal, then the three database tests.
- `pandapower_engine_test.py` tracer extended: results carry `solver` and `solver_version`, the built record has exactly the 19 tagged columns, a `pp-` id and the installed version, and `psse_version` is still None.
- `pandapower_study_job_test.py`: the module fixture applies `apply_solver_schema`, `_run` passes `solver=engine.SOLVER`, the tracer, `_assert_failed` and the island test assert the stored tag, and the header's two Phase 2 sentences (nothing asserted about a solver column; run id keeps `psse-`) are rewritten. `test_prepared_run_is_ready_for_the_writer` is unchanged and still runs here.

## Task Commits

1. **Task 1: Tracer (engine four-city study through run_once(solver=engine.SOLVER) to one tagged pp- insert)** - `b6215d1`
2. **Task 2: Vocabulary parity with the migration, and runs that must not be stored as PSS/E** - `cc63ac9`
3. **Task 3: Tagged database rehearsal through the real writer (skips here)** - `89e3a92`

## Test Results (this machine, Windows, `.venv` Python 3.12, pandapower 3.5.6)

- Task 1 verify (two tracers plus `pandapower_import_gate_test.py`): **6 passed, 0 skipped, 0 failed**.
- Task 2 verify (`-k "tracer or parity or refused"`): **6 passed, 0 failed, 0 skipped**.
- Task 3 verify (`pandapower_solver_tag_test.py` plus `pandapower_study_job_test.py`): **7 passed, 7 skipped, 0 failed**. All 7 skips are database tests with the harness reason "set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the PSS/E Postgres proofs". With `PSSE_REQUIRE_PG=1` and no database, `-k db` on the new file gives `3 errors`.
- Combined run (new file, study job, import gate, engine, study behaviour, API contract): **57 passed, 7 skipped, 0 failed**, 184 s. No new skips or failures in `pandapower_engine_test.py`, `pandapower_study_behaviour_test.py` or `pandapower_api_contract_test.py`.
- The file-scope gate (PLAN=03-04) exited 0 after each commit; the staged leak scan exited 0 before each commit.

## Decisions Made

- `solver_version` is the bare version string the adapter reports (assumption A7), identical to `pandapower.__version__`.
- The engine stamps the tag, and the run loop's cross-check from plan 03-02 is what refuses a default-tag run; no second guard was added in the engine.
- The tests are `test_refused_default_tag_never_stores_results` (real engine, recording connection) for the Python side of T-03-15, and `test_db_a_pandapower_run_cannot_be_stored_as_psse` for the database side (Mac tier).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test helper rows omit their NULL columns**
- **Found during:** Task 3, before committing (checked by running the helper without a database)
- **Issue:** `pg_helper.valid_run_rows(...)["psse_run"][0]` leaves out `failed_stage`, `error` and `ratings_read_error` when they are NULL, so my first `_bind` (which asserted the key set equals the insert's columns) would have failed the database test on the Mac for a reason that has nothing to do with the database.
- **Fix:** `_bind` now asserts `set(row) <= set(columns)` and binds a missing column as NULL.
- **Files modified:** `backend/tests/pandapower_solver_tag_test.py`
- **Verification:** the helper rows bind to 17 and 19 parameters here; the database tests themselves still only skip.
- **Committed in:** `89e3a92`

**2. [Rule 3 - Blocking] Heredoc escaping broke a test file while writing it**
- **Found during:** Task 2 (collection error: unterminated string literal)
- **Issue:** two `"\n"` and one `\t` ended up as real line breaks in the file when appended through a quoted shell heredoc.
- **Fix:** replaced the broken lines by hand; all six selected tests pass.
- **Committed in:** `cc63ac9`

### Plan wording corrected (not a code deviation)

The plan says the edits to `pandapower_engine_test.py` and `pandapower_study_job_test.py` are forced by plan 03-02's cross-check. That is not accurate. They are forced by this plan's own change to `engine._recording_study`: once the engine tags its results with its own solver, `build_run_record` on a default-tagged context refuses them (the engine test builds a record from engine results with the default context) and `job.run_once` without `solver=` stores a failed run (the study-job tests expect a written run). The edits stay in Task 1's commit so no commit is left red.

---

**Total deviations:** 2 auto-fixed (1 bug in my own test helper, 1 blocking tooling slip), no production change beyond what the plan named.
**Impact on plan:** none on scope.

## Issues Encountered

- The `Edit` and `Write` tools leave line endings alone, and `api.py` has CRLF in the working tree (the repository stores LF). The edits are three single-line changes plus one inserted block; git normalizes them, and `git diff --numstat` shows only the intended lines (5 added, 2 removed in `api.py`).
- Known environmental failures that are not from this plan (CRLF byte-hash migration tests, `day_ahead_migration_test.py` not collecting, Windows-only Phase 1 CLI and ingest failures) were not run in this plan's selection and were not touched.

## Known Stubs

None. No stub, placeholder-data path or skipped test was added other than the database tests described above, which skip by design when no database is available (and fail under `PSSE_REQUIRE_PG=1`). They were not added to `.planning/WINDOWS.md`: earlier plans of this workstream did not log their environment skips there either, and the Mac command above is what closes them.

## Threat Flags

None. No new network endpoint, auth path or schema change; the only new surface is the registered tag, which the parity test pins to the migration's constraints.

## User Setup Required

None. The owner's Mac command in "Database tier status" closes the database proofs.

## Next Phase Readiness

- Hand-off to Phase 5: the hourly runner must call `job.run_once(..., solver=engine.SOLVER)` after `engine.prepare_run(...)`; with the default tag the run is refused at validate_results and stored as one failed run.
- Plan 03-05 waits for an owner decision and was not started.
- Blocker for marking DB-01 and DB-02 complete: one green Mac run with 0 skipped over the migration, writer, gap, and these tagged tests.

## Self-Check: PASSED

- FOUND: backend/tests/pandapower_solver_tag_test.py
- FOUND commits b6215d1, cc63ac9, 89e3a92 (ancestors of HEAD)
- `git rev-list --count 47fe3d9..HEAD` measured 3 before this SUMMARY was committed

---
*Phase: 03-solver-tag-migration-and-per-solver-gaps*
*Completed: 2026-11-18*
