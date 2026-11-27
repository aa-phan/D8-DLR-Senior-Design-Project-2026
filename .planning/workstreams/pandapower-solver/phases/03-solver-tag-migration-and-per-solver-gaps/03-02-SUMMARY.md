---
phase: 03-solver-tag-migration-and-per-solver-gaps
plan: 02
subsystem: psse-job-package
tags: [solver-tag, run-record, writer, registry, run-id-prefix, stdlib-only, python37]

requires:
  - phase: 03 plan 01
    provides: migration 20261118200000 (solver and solver_version columns, the pp-/psse- tie), written there and only SKIPPED on this machine
provides:
  - contract.SOLVER_PSSE, RUN_ID_PREFIXES, register_solver_tag(name, prefix) - the tag registry the second solver's package fills on import
  - contract.SOLVER_RUN_COLUMNS, TAGGED_RUN_COLUMNS, INSERT_RUN_TAGGED_SQL, insert_sql(columns=), RunContext.solver, StudyResults.solver and solver_version
  - run_record.new_run_id(started_at, solver), SOLVER_VERSION_MAX_CHARS, a 19-key tagged record for a non-PSS/E run
  - job.run_once(..., solver="psse")
  - writer._check_tag and the 17-or-19-column insert choice
  - backend/tests/psse_solver_tag_test.py - 13 pure-Python tests
affects: [03-04 solver package registers its tag and runs through run_once(solver=...), 03-03 gaps, Phase 5 hourly runner, Phase 6 per-solver view]

actuals:
  tokens: 6240
  tasks: 3
  commits: 3
plan_head_before: 0dc7f7c2917e297e93798988cb3b7aef18aab439
plan_head_after: 4864e56641b7f5f95e9f5f0bd744738e8a3ac642

tech-stack:
  added: []
  patterns:
    - "A registry in psse_job (contract.RUN_ID_PREFIXES) that the solver package fills on import, so psse_job never names the second solver (same shape as study.register_solver)"
    - "Two run INSERTs: the PSS/E job keeps the 17-column one (works before the migration), another solver's run uses the 19-column one"
    - "Refusals are fixed-text ValueErrors raised before any statement or transaction and name the rule, never a value"

key-files:
  created:
    - backend/tests/psse_solver_tag_test.py
  modified:
    - backend/psse_job/contract.py
    - backend/psse_job/run_record.py
    - backend/psse_job/job.py
    - backend/psse_job/writer.py

key-decisions:
  - "Registry form: contract.register_solver_tag(name, prefix), filled by the solver package on import; an existing name or prefix is never re-bound, so the PSS/E tag cannot be replaced"
  - "A tagged PSS/E record is refused by the writer, so PSS/E always uses the 17-column insert and never depends on the migration"
  - "A second-solver study run with the default tag is stored as one failed psse run at validate_results with no result rows; it never stores figures as PSS/E. Phase 5's runner avoids it by passing its tag"

requirements-completed: []

coverage:
  - id: D1
    description: "run_once takes solver (default psse); the default run still writes exactly the 17 PSSE_RUN_COLUMNS with contract.INSERT_RUN_SQL; a registered second solver's run gets a pp- id and a 19-key record written with INSERT_RUN_TAGGED_SQL"
    requirement: "DB-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_solver_tag_test.py#test_tracer_tagged_run_is_written_with_the_tagged_insert"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_solver_tag_test.py#test_build_run_record_shapes"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_solver_tag_test.py#test_old_constructions_keep_working"
        status: pass
    human_judgment: false
  - id: D2
    description: "the writer refuses, before any statement, every tag mismatch (id vs tag, one tag key, unregistered, tagged PSS/E, bad solver_version) with fixed messages; a tagged write failure keeps its tag on the failed record"
    requirement: "DB-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_solver_tag_test.py#test_writer_refuses_a_mismatched_tag_before_any_statement"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_solver_tag_test.py#test_tagged_write_failure_records_a_tagged_failed_run"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_solver_tag_test.py#test_insert_texts"
        status: pass
    human_judgment: false
  - id: D3
    description: "results from another solver are never written as results; failed and refused tagged runs keep their tag; the registry cannot be re-bound; psse_job registers only the psse tag and loads no solver module"
    requirement: "DB-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_solver_tag_test.py#test_results_from_another_solver_are_never_written"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_solver_tag_test.py#test_register_solver_tag_rules"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_solver_tag_test.py#test_importing_psse_job_registers_only_the_psse_tag"
        status: pass
    human_judgment: false
  - id: D4
    description: "the database tie that makes a pp- run impossible to store as psse (third layer, plan 03-01's migration)"
    requirement: "DB-02"
    verification: []
    human_judgment: true
    rationale: "Database proof. This plan's tests use a recording connection; the migration's constraints were only SKIPPED here (plan 03-01) and have never run on a real Postgres."

duration: 30min
completed: 2026-11-18
status: complete
---

# Phase 3 Plan 02: Solver Tag in the PSS/E Job Package Summary

**`psse_job` now carries a solver tag end to end with no new dependency: a registry of tags and run-id prefixes in `contract.py`, `run_once(..., solver="psse")`, a 19-key record and a 19-column INSERT only for a non-PSS/E run, and a writer that refuses every tag mismatch before it executes anything, while the default PSS/E run is byte-for-byte the 17-column path of today.**

## Database tier status

This plan has **no database-only criterion**: every behaviour it adds is proven here with a recording connection and no Postgres. Two things are nevertheless not proven by it, and neither should be read as proven:

- The database half of DB-02 (a `pp-` run cannot be stored as `psse`) is the migration's tie from plan 03-01, whose seven database tests were only **SKIPPED** on this machine and have never run anywhere. The 19-column INSERT built here has therefore never been executed by a real Postgres either.
- The owner's Mac command for the migration and writer files (must report 0 skipped):

```
DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/solver_tag_migration_test.py backend/tests/psse_writer_test.py backend/tests/psse_schema_pg_test.py
```

DB-02 is therefore left **Pending** in REQUIREMENTS.md: its Python half is done, but the requirement also names the pandapower job writing through the writer (plan 03-04 and Phase 5) and the database-side guarantee (Mac run).

## Accomplishments

- `contract.py`: `SOLVER_PSSE`, `RUN_ID_PREFIXES = {"psse": "psse"}`, `register_solver_tag` (non-empty text name and prefix, prefix full-matches `[a-z]{1,10}`, a name or prefix is never re-bound, identical pair is a no-op), `SOLVER_RUN_COLUMNS`, `TAGGED_RUN_COLUMNS`, `insert_sql(table, suffix, columns=None)` (default text byte-identical), `INSERT_RUN_TAGGED_SQL`, `RunContext.solver` and `StudyResults.solver` / `solver_version` as trailing defaulted fields. `PSSE_RUN_COLUMNS`, `TABLE_COLUMNS` and `constants.py` are untouched.
- `run_record.py`: `new_run_id(started_at, solver)` uses the registered prefix and raises `ValueError("solver is not registered")` for an unknown or non-text solver; `build_run_record` returns the 17 keys for PSS/E and the 19 keys otherwise, cuts `solver_version` to 100 characters and turns an empty one into None, and raises `ResultsInvalid` when the results come from a different solver than the run.
- `job.py`: one new keyword `solver`; the cross-check raises inside the existing validate/build `try`, so it becomes one `validate_results` failure with no result rows, built from the context so it carries the run's own tag.
- `writer.py`: `_check_tag` (both tag keys or neither, registered non-PSS/E solver, prefix matches run id, `solver_version` None or text of 1 to 100 characters) is called in `write_run` after the outcome check and before the `try`, in `record_failure` before its `try`, and in `_insert_run`; a refusal is a plain `ValueError` with nothing executed. The insert is chosen by whether the record carries `solver`.
- 13 tests in `psse_solver_tag_test.py`, none skipped, none importing the second solver (its tag is registered only through `monkeypatch`).

## Task Commits

1. **Task 1: Tracer (one tagged run to the 19-column insert, default run on the 17-column one)** - `82a04c9`
2. **Task 2: Writer refusals, tagged all-or-nothing write, the two INSERT texts** - `49f40fa` (red first: the refusal test failed against the Task 1 subset of `_check_tag`, then green)
3. **Task 3: Registry rules, run-loop cross-check, failed tagged runs, import boundary** - `4864e56` (red first: 3 of 13 tests failed, then green)

## Test Results (this machine, Windows, `.venv` Python 3.12)

- `psse_solver_tag_test.py`: **13 passed, 0 failed, 0 skipped**.
- PSS/E regression set from the plan plus the new file (11 files): **135 passed, 43 skipped, 0 failed** (baseline 122 passed, 43 skipped, plus the 13 new tests). Every skip is an existing database test.
- `psse_contract_test.py` import-boundary, Python 3.7 parse and no-heavy-module tests and every test of `pandapower_import_gate_test.py`: pass.
- File-scope gate for `(03-02)`: exit 0 after each commit. Staged leak scan before each commit: exit 0. Full leak scan: exit 0. No commit deleted a file.
- Wider run (`psse_*_test.py` and `pandapower_*_test.py`, run after Task 3): 4 failures, none caused by this plan and none in a file it edited: the known CRLF byte-hash test `psse_results_migration_test::test_psse_migration_is_unchanged_after_apply`, and three Windows-only failures in Phase 1 files (`pandapower_cli_test::test_private_outputs_are_ignored_and_flagged_by_the_leak_guard` and `pandapower_ingest_test::test_private_writers_add_the_marker_and_keep_the_file_private` assert file mode 0o600, which Windows reports as 0o666; `pandapower_ingest_test::test_ingest_refuses_each_unsafe_archive[bad_member_name-...]` expects a different refusal reason for a Windows member name). I did not fix them (out of scope; the mode family is the known 0o600 item). The `-q -q` run printed no totals line, so no pass count is claimed for it.

## Decisions Made

- **Registry form:** `contract.register_solver_tag(name, prefix)`, filled by the solver package on import; an existing name or prefix is never re-bound, so the PSS/E tag cannot be replaced (T-03-07).
- **A tagged PSS/E record is refused**, so PSS/E always uses the 17-column insert and keeps working on a database where migration 20261118200000 has not been applied.
- **A second-solver study run with the default tag** is stored as one failed `psse` run at `validate_results` with no result rows (it never stores figures as PSS/E). Phase 5's runner avoids this by passing its tag.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] A non-text `solver_version` is stored as text**
- **Found during:** Task 3
- **Issue:** the writer refuses a `solver_version` that is not text of 1 to 100 characters with a `ValueError`. `build_run_record` passed a study's value through unchanged, so a study returning a number would make `write_run` raise a `ValueError` out of `job.run_once` uncaught, instead of storing a run.
- **Fix:** `run_record._solver_version` turns a non-None non-text value into `str(value)` before the strip, cut and empty-to-None rules the plan asks for. Covered in `test_build_run_record_shapes` (`7` becomes `"7"`).
- **Files modified:** backend/psse_job/run_record.py, backend/tests/psse_solver_tag_test.py
- **Commit:** `4864e56`

**2. [Process] Stale commit ledger corrected**
- `.git/gsd-plan-head-before-03-02` held `d967e48...` (from another workstream's 03-02). It was overwritten with `0dc7f7c` (HEAD at this plan's start) before the first task commit; `commits: 3` was measured with `git rev-list --count 0dc7f7c..HEAD` before this summary commit.

**3. [Process] Task 1 `_check_tag` kept to the plan's Task 1 subset**
- I first wrote the complete `_check_tag`, then cut it back to the Task 1 subset for the tracer commit so Task 2's refusal test was a real red step, and restored the full version in Task 2. No effect on the final code.

**Total deviations:** 1 auto-fixed (Rule 2), 2 process notes. **Impact:** none on the plan's acceptance criteria.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, role, credential or file access; the new surface is the in-process registry and a second parameterised INSERT into the same table through the same writer role. T-03-06 to T-03-10 are covered by the tests named in the plan.

## Issues Encountered

- STATE.md pointer: `state.advance-plan` moved Phase 1's `current_plan` from 10 to 11 and overwrote Stopped At and Resume File. I restored current_plan 10, the "Plan: 10 of 11" line (with this plan appended), `**Current Plan:** 10` and the 01-10 laptop-checkpoint Stopped At and Resume File; the tool's progress counts (17 of 23 plans) were kept.
- A multi-line shell heredoc that appended the Task 3 tests failed on a quoting error before anything was written (repository untouched, checked with `git status`); the tests were then added with the Edit tool.

## Next Phase Readiness

- Plan 03-04's solver package can call `contract.register_solver_tag("pandapower", "pp")` on import and run through `job.run_once(..., solver="pandapower")`, returning `StudyResults` with `solver="pandapower"` and a `solver_version`.
- Its parity test should hold `contract.RUN_ID_PREFIXES` in step with the migration's solver check.
- Owner step: the Mac database run above before DB-01 or DB-02 can be called proven.

## Self-Check: PASSED

- FOUND: backend/tests/psse_solver_tag_test.py
- FOUND: backend/psse_job/contract.py, run_record.py, job.py, writer.py (modified)
- FOUND commits: 82a04c9, 49f40fa, 4864e56 (all ancestors of HEAD)
