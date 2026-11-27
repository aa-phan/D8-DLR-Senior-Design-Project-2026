---
phase: 06-dashboard-read-access-and-def-01
plan: 02
subsystem: database
tags: [postgres, supabase, owner-check, exposure-checker, sabotage-proof, pytest]
status: complete

requires:
  - phase: 06-dashboard-read-access-and-def-01
    provides: plan 06-01's per-solver latest_grid_study view and the grid_study_per_solver_test.py fixtures
provides:
  - verify_exposure.sql with 37 checks, the new one comparing the per-solver view with the result tables
  - owner-trio proof on one database (6, 7 and 37 checks, all ok) with the counts tied to the migration header
  - three rolled-back sabotage proofs that only the new check fails
affects: [06-03 docs, 06-04 owner runbook and live apply]

actuals:
  tokens: 3300
  tasks: 2
  commits: 2
plan_head_before: 32d4e8855a27f5258f71bbdcf9908cb97658c176
plan_head_after: 2193d04ad69b207d58fcc1230182c716c70c6877

tech-stack:
  added: []
  patterns:
    - "a live check compares a view with the tables behind it (distinct on solver CTE) instead of matching the view definition text"
    - "sabotage proof: replace the view inside a force_rollback transaction, run the checker, assert the exact set of failing checks, then assert the rollback left everything ok"

key-files:
  created: []
  modified:
    - supabase/ops/verify_exposure.sql
    - backend/tests/expose_migration_test.py
    - backend/tests/psse_results_migration_test.py
    - backend/tests/grid_study_per_solver_test.py

key-decisions:
  - "The CTE newest_complete_run and the check sit strictly inside the two grid_study regions, so the stripped checker still has 29 checks and its four fragments are untouched"
  - "The check detail is two counts (view rows, solvers with a complete run); no run id, prefix, hash or version"

requirements-completed: []  # VIEW-02 stays Pending until the owner runs the trio on the live project (orchestrator instruction)

duration: about 35 min
completed: 2026-11-26
---

# Phase 6 Plan 02: Exposure check of the per-solver view Summary

**`verify_exposure.sql` now has 37 checks; the new `latest_grid_study_has_each_solvers_newest_complete_run` compares the view with the result tables, holds for no runs, one solver and both solvers, and is the only check that turns false for the Phase 3 PSS/E-only view, a view that hides a city, and a view that shows an older run.**

## What was built

- **Checker** `supabase/ops/verify_exposure.sql`: CTE `newest_complete_run` (`distinct on (r.solver)` over runs with outcome ok or fallback, full tie-break order) inside the `grid_study_ctes` region; the new check inside the `grid_study_checks` region. It is true when, for each solver's newest complete run, the view holds exactly as many rows for that solver and slot as the run has dispatched-capacity rows, and the view's total equals the sum over those runs. Header: the check list names the new check, the grid-study view line names the per-solver migration, and "per city" became "per city and solver". Detail example: `view rows=8, solvers with a complete run=2`.
- **Pins**: `_VERIFY_CHECKS` in `expose_migration_test.py` holds 37 names with the comment updated; `_EXPOSURE_CHECKS = 37` in `psse_results_migration_test.py`; `_EXPOSURE_CHECKS_WITHOUT_GRID_STUDY` stays 29.
- **Proofs** in `grid_study_per_solver_test.py` (16 to 23 tests): the owner trio (6, 7, 37 rows, all ok, no run id, `psse-`, `pp-` or `3.5.6` in any detail, counts equal the numbers in the migration header); the new check true for none, psse and pandapower; three sabotages in rolled-back transactions (Phase 3 view statement read from the applied file, a view with `where d.city <> 'EL_PASO'`, a view ordered `slot_time asc`), each making exactly the new check false, with the rollback shown by an all-ok checker afterwards.

## Verification (Windows, PostgreSQL 17.12 throwaway cluster, PSSE_REQUIRE_PG=1)

- Task 1 gate: 72 passed, 3 deselected, nothing skipped.
- Task 2 gate: 23 passed in `grid_study_per_solver_test.py`.
- Plan regression set: 118 passed, 4 deselected (23 + 36 + 24 + 12 + 23), nothing skipped.
- Acceptance greps: check name on 2 lines of `verify_exposure.sql` (header and check), 4 marker lines, one `_EXPOSURE_CHECKS = 37` line, one name line in `_VERIFY_CHECKS`.
- Inertness: `git diff --quiet 32d4e88` over `backend/psse_job`, `backend/pandapower_job`, `supabase/migrations` and REQUIREMENTS.md exits 0.
- File-scope gate for 06-02 exits 0; `private_leak_scan --staged` exited 0 before both commits.

## Deviations from Plan

**1. [Acceptance count] `force_rollback=True` appears once, not three times.** The plan's acceptance criterion expects at least 3 occurrences. The three sabotage tests share one helper, `_sabotaged_view`, which holds the single `conn.transaction(force_rollback=True)` block; every sabotage still runs inside it and shows the rollback afterwards. Behaviour is as the plan describes; only the literal grep count differs.

**2. [Authoring] One authoring slip fixed before the first run of Task 2.** A newline escape in the hidden-city fragment was written as a real line break by my edit script, giving a syntax error at collection. Replaced with `chr(10)` before any commit of the file; no test result was affected.

Otherwise the plan was executed as written.

## Known issues not touched

- Windows-only failures deselected as instructed (CRLF byte-hash tests, matplotlib test).
- `docs/data-science/decisions/dlr_live_runbook.md:673` says "29 rows, all ok" (research item 15); not this plan's. Mention to the owner only.
- Edited files are CRLF in the working tree; edits kept each file's line endings.

## Known Stubs

None.

## Threat Flags

None. The checker is read-only SQL; no new endpoint, auth path or file access.

## Self-Check: PASSED

- FOUND: supabase/ops/verify_exposure.sql, backend/tests/expose_migration_test.py, backend/tests/psse_results_migration_test.py, backend/tests/grid_study_per_solver_test.py
- FOUND commits aa61021 and 2193d04 on feature/pandapower-solver (2 commits measured from the plan ledger base 32d4e88)
