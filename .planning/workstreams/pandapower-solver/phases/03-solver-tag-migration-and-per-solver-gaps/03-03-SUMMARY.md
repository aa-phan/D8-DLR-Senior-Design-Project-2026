---
phase: 03-solver-tag-migration-and-per-solver-gaps
plan: 03
subsystem: psse-job-gap-check
tags: [gap-check, per-solver, read-only, stdlib-only, python37, oracle-test]

requires:
  - phase: 03 plan 01
    provides: migration 20261118200000 (the solver column RUNS_SQL selects), written there and only SKIPPED on this machine
  - phase: 03 plan 02
    provides: contract.SOLVER_PSSE (the PSS/E section is printed first)
provides:
  - gaps.RUNS_SQL, gaps.CURRENT_HOUR_SQL, gaps.SolverSummary
  - gaps.fetch_runs, fetch_current_slot, summarize, compute_gaps, solver_order, format_solver_report
  - gaps.run_by_solver(env, since, until, fail_on_gaps, out, connect, expected, failing) - the per-solver gap check
  - backend/tests/psse_gaps_solver_test.py - 14 pure-Python tests plus 1 database test that skips here
affects: [03-04, Phase 5 hourly runner (OPS-05), Phase 6 per-solver view]

actuals:
  tokens: 7540
  tasks: 3
  commits: 3
plan_head_before: 9f88a3175995a5da032fa454413f5e47a1754605
plan_head_after: e42ad9a8bd31522ac4fe3620355cd2dd2b832460

tech-stack:
  added: []
  patterns:
    - "Gap logic for the per-solver check lives in Python (compute_gaps), proven against an independent plain-loop oracle; the legacy SQL file stays the only SQL gap logic and is untouched"
    - "The database supplies its own current UTC hour on the same read-only connection, so the runner clock and the database clock cannot disagree"
    - "A fake connection that records autocommit/read_only assignments and statements proves the read-only order without Postgres"

key-files:
  created:
    - backend/tests/psse_gaps_solver_test.py
  modified:
    - backend/psse_job/gaps.py

key-decisions:
  - "Exit rule (a recommendation the owner may change): with fail_on_gaps, PSS/E gaps are listed but do not fail the check by default because its machine being offline is the known state; every other present or expected solver fails on a gap in the window or on being expected with no rows; an empty table fails. The caller overrides it with failing=(...)"
  - "Assumption A6: the laptop `gaps` command stays the legacy pooled check this phase; run_by_solver is library-level only. Phase 5 wires it into the hourly workflow (OPS-05)"
  - "A solver value that does not full-match [a-z][a-z0-9_]{0,31} is printed as `unknown`, so no arbitrary text reaches a log"

requirements-completed: []

coverage:
  - id: D1
    description: "A PSS/E run in an hour no longer hides a missing second-solver hour: the per-solver check lists that hour as no_run under the second solver and fails with fail_on_gaps"
    requirement: "DB-03"
    verification:
      - kind: unit
        ref: "backend/tests/psse_gaps_solver_test.py#test_tracer_a_psse_hour_does_not_hide_a_missing_pandapower_hour"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_gaps_solver_test.py#test_compute_gaps_matches_the_oracle_per_solver"
        status: pass
    human_judgment: false
  - id: D2
    description: "PSS/E offline hours are listed only in the PSS/E section; hours before a solver's own first slot, the current hour and later rows are not gaps; failed_only is per solver"
    requirement: "DB-03"
    verification:
      - kind: unit
        ref: "backend/tests/psse_gaps_solver_test.py#test_pss_e_offline_is_listed_separately"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_gaps_solver_test.py#test_hours_before_a_solvers_first_slot_are_not_its_gaps"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_gaps_solver_test.py#test_failed_only_is_per_solver"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_gaps_solver_test.py#test_only_the_current_hour_and_later_rows"
        status: pass
    human_judgment: false
  - id: D3
    description: "The report prints only times, tags, kinds and counts; a failure is one redacted line; the session is read-only before any statement; the legacy path is unchanged"
    requirement: "DB-03"
    verification:
      - kind: unit
        ref: "backend/tests/psse_gaps_solver_test.py#test_report_lines_hold_only_times_tags_kinds_and_counts"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_gaps_solver_test.py#test_failure_is_one_redacted_line"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_gaps_solver_test.py#test_read_only_before_any_statement"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_gaps_solver_test.py#test_legacy_path_is_unchanged"
        status: pass
    human_judgment: false
  - id: D4
    description: "RUNS_SQL and CURRENT_HOUR_SQL run on real Postgres against the migrated schema, and the writer role's read-only session refuses a write"
    requirement: "DB-03"
    verification: []
    human_judgment: true
    rationale: "Database proof. test_db_run_by_solver_on_the_migrated_schema was written but only SKIPPED on this machine (no Postgres); the two statements have never run on a real database."

duration: 25min
completed: 2026-11-18
status: complete
---

# Phase 3 Plan 03: Per-Solver Gap Check Summary

**`gaps.run_by_solver` computes each solver's missing UTC hours in Python from that solver's own first recorded slot, over one read-only SELECT plus the database's current hour, so a PSS/E row can no longer hide a missing second-solver hour (and the reverse); the legacy pooled `run` and the laptop `gaps` command are unchanged.**

## Database tier status

One proof in this plan needs a database and was **only SKIPPED on this machine** (Postgres is not installed here). It has not run anywhere, and nothing below claims it:

- `backend/tests/psse_gaps_solver_test.py::test_db_run_by_solver_on_the_migrated_schema` - on a throwaway local cluster with the solver-tag migration applied, inserts PSS/E runs at H-3h, H-2h, H-1h and second-solver runs at H-3h and H-1h, then checks that `run_by_solver` on the writer role with `fail_on_gaps` returns 5 and lists exactly H-2h `no_run` under the second solver, that `fetch_current_slot` equals the database's hour floor, and that an INSERT on a session set up as `run_by_solver` sets it up raises `ReadOnlySqlTransaction`.

What this means: `RUNS_SQL` and `CURRENT_HOUR_SQL` (and the `solver` column they read, from plan 03-01's migration) have never been executed by a real Postgres. Everything else, including the whole gap computation, the report, the exit rule, the redaction and the read-only statement order, is proven here without a database.

The owner's Mac command (must report **0 skipped**):

```
DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/psse_gaps_solver_test.py backend/tests/psse_gaps_pg_test.py
```

**DB-03 is left Pending** in REQUIREMENTS.md: the per-solver computation is done and proven, but the database half (the two statements on Postgres, the read-only refusal) is skipped here, and the laptop `gaps` command is still pooled (see Decisions).

## Accomplishments

- `gaps.py` additions only (182 lines, no existing line removed or reworded; checked with the additions-only gate after every commit): `RUNS_SQL = "select slot_time, solver, outcome from public.psse_run"`, `CURRENT_HOUR_SQL`, `SolverSummary`, `fetch_runs`, `fetch_current_slot`, `summarize`, `compute_gaps`, `solver_order`, `format_solver_report`, `run_by_solver`, one new `contract` import line, `import re`, and one docstring paragraph. The legacy `run`, `fetch_gaps`, `format_report`, `SUMMARY_SQL`, `GapRow`, and `docs/data-science/schema/psse_run_gaps.sql` and `launcher.py` are byte-identical (`git diff --quiet` against the plan base exits 0).
- `compute_gaps` applies the legacy five rules per solver: walk whole hours from that solver's first slot while before the current hour; an hour with no row of that solver is `no_run`, an hour whose rows of that solver are all `failed` is `failed_only`. There is no global first slot anywhere (Pitfall 8).
- Report: PSS/E section first, other solvers by name, expected-but-empty solvers as `solver <name>: no runs recorded`; the window filters gap lines only, the counts and first/latest slots cover every row. Solver values outside `[a-z][a-z0-9_]{0,31}` print as `unknown`.
- 15 tests in `psse_gaps_solver_test.py`. `reference_gaps` is copied verbatim from `psse_gaps_pg_test.py` and stays independent of `gaps.py`; the seeded comparison (`random.Random(20261118)`, 300 histories) produces gaps in more than 50 of them, and a throwaway mutant that pooled the solvers was killed by it.

## Task Commits

1. **Task 1: Tracer (a PSS/E hour does not hide a missing second-solver hour, through run_by_solver on a read-only fake connection)** - `aefca01`
2. **Task 2: compute_gaps against the per-solver oracle and the DB-03 scenarios** - `f859dfd`
3. **Task 3: Report shape, exit rule, one redacted failure line, read-only order, untouched legacy path, database test** - `e42ad9a`

## Test Results (this machine, Windows, `.venv` Python 3.12)

- `psse_gaps_solver_test.py`: **14 passed, 1 skipped, 0 failed**. The one skip is `test_db_run_by_solver_on_the_migrated_schema` with the harness reason "set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the PSS/E Postgres proofs".
- Plan verify command (the new file, `psse_gaps_pg_test.py`, `psse_laptop_modes_test.py`, `psse_setup_doc_test.py`, `psse_contract_test.py`, `pandapower_import_gate_test.py`): **60 passed, 16 skipped, 0 failed**; every skip is a database test.
- PSS/E regression set of plan 03-02 (the ten files): **122 passed, 43 skipped, 0 failed**, the same counts as before this plan.
- Task 1 acceptance: `pandapower_import_gate_test.py` and `psse_contract_test.py` 14 passed (gaps.py is still stdlib-only, Python 3.7 syntax, free of the second solver's name and of the SQL hour-series function name).
- Additions-only gate, file-scope gate (`(03-03)`) and the staged leak scan: exit 0 before each commit. No commit deleted a file.
- TDD note: `compute_gaps`, `format_solver_report` and `run_by_solver` were written in full in the tracer task, so Tasks 2 and 3 tests passed on first run (no red phase was observed). The oracle test was checked against a pooled mutant instead, which it killed.

## Decisions Made

- **Assumption A6 (laptop command stays pooled):** `gaps.run` and the laptop `gaps` command are unchanged this phase, so the per-solver check is library-level only; the laptop command still counts every solver's rows together. If the owner wants the laptop command to change, that would also change `launcher.py`, `psse_setup_doc_test.py` and the guide.
- **Exit-rule recommendation (owner may change it):** PSS/E gaps are listed but do not fail `fail_on_gaps` by default, because its machine being offline is the known state; every other present or expected solver fails on a shown gap or on being expected with no rows; an empty table fails. `failing=(...)` overrides the set.
- **`expected` and `failing` semantics:** an expected solver with no rows fails only if it is among the watched ones; a solver in `failing` that is neither present nor expected is not a failure.
- **Hand-off for Phase 5 (OPS-05):** call `gaps.run_by_solver(env, expected=(engine.SOLVER,), fail_on_gaps=True)` from the hourly workflow.

## Deviations from Plan

None - plan executed exactly as written. (Process notes, not deviations: the commit ledger `.git/gsd-plan-head-before-03-03` held a stale value from an earlier plan and was corrected to `9f88a31` before the first commit; Task 3 needed no change to `gaps.py` because the Task 1 implementation already satisfied every Task 3 test.)

## Known Stubs

None.

## Threat Flags

None. The check adds no endpoint or write path: two SELECT-only statements on a read-only session, printing only times, tags, kinds and counts (T-03-11 to T-03-14 mitigated by the tests named above).

## Self-Check: PASSED

- FOUND: backend/psse_job/gaps.py, backend/tests/psse_gaps_solver_test.py
- FOUND commits (ancestors of HEAD): aefca01, f859dfd, e42ad9a
- `git rev-list --count 9f88a31..HEAD` before this commit: 3, matching `actuals.commits`.
