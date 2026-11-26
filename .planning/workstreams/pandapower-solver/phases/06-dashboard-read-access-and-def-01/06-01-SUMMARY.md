---
phase: 06-dashboard-read-access-and-def-01
plan: 01
subsystem: database
tags: [postgres, supabase, view, distinct-on, owner-rights-view, pytest]
status: complete

requires:
  - phase: 03-solver-tag
    provides: psse_run.solver column, the run-id tie constraint, the PSS/E-only view guard this plan replaces
provides:
  - migration 20261126200000_latest_grid_study_per_solver.sql, the per-solver replacement of public.latest_grid_study (inert until the owner applies it)
  - grid_study_per_solver_test.py, 16 text and database proofs on a throwaway Postgres
  - verify_solver_tag.sql with 6 checks (check 7, the PSS/E-only guard, retired)
  - contract constants SOLVERS and MAX_ROWS
affects: [06-02 exposure checker (37 checks), 06-03 docs, 06-04 owner runbook and live apply]

actuals:
  tokens: 9255
  tasks: 3
  commits: 2
plan_head_before: 8321aa128f9cb9880776075efb15a6692c15fc40
plan_head_after: 10f08ea4c89a437964dc5bdb7919fdbd51192eae

tech-stack:
  added: []
  patterns:
    - "newest row per group with select distinct on (r.solver) and a full tie-break order (slot_time, finished_at, run_id)"
    - "a replaced view keeps name, 20 columns, owner rights and ACL; only the two comments that became false change"

key-files:
  created:
    - supabase/migrations/20261126200000_latest_grid_study_per_solver.sql
    - backend/tests/grid_study_per_solver_test.py
  modified:
    - supabase/ops/verify_solver_tag.sql
    - backend/tests/solver_tag_owner_check_test.py
    - backend/tests/psse_results_migration_test.py
    - backend/tests/day_ahead_expose_test.py
    - backend/grid_study_contract.py
    - backend/tests/grid_study_expose_test.py

key-decisions:
  - "Tasks 1 and 2 were committed together (fe98f29) so no commit leaves the tree red; the plan's red window between them (five tests in other files) never reached a commit"
  - "No SHA-256 pin of the new migration anywhere: the convention pins applied files, and this one is not applied live yet"
  - "Migration header wording avoids the literal 'distinct on (r.solver)' so the plan's grep finds exactly one line"

requirements-completed: []  # VIEW-01 and VIEW-02 stay Pending until the owner's live apply (orchestrator instruction)

duration: about 55 min
completed: 2026-11-26
---

# Phase 6 Plan 01: Per-solver latest_grid_study view Summary

**public.latest_grid_study now returns the newest complete run of each solver (one row per city per solver, at most 8 rows) through `distinct on (r.solver)`, with the 20 columns, owner rights, grants and 19 of 20 column comments unchanged, proven on a throwaway local Postgres.**

## What was built

- **Migration** `supabase/migrations/20261126200000_latest_grid_study_per_solver.sql`: a comment-only header (order warning, owner apply sentence naming 6, 7 and 37 checks), the view statement, revoke then grant, the view comment and 20 column comments. Compared with the Phase 3 view the CTE drops the `r.solver = 'psse'` predicate and `limit 1`, the constant `'psse'` label becomes `n.solver`, and the final order is `d.city, n.solver`. The view comment and the `solver` column comment are the only texts that change.
- **Owner check** `supabase/ops/verify_solver_tag.sql`: check 7 (definition-text match on the PSS/E-only guard) retired; header says why. 6 checks remain, each still proven able to fail.
- **Tests**: `grid_study_per_solver_test.py` holds 16 tests (7 text, 9 database). `solver_tag_owner_check_test.py` lost the guard check name and sabotage case and gained `test_db_after_the_chain_the_view_shows_each_solvers_newest_run`. The two migration-order pins (`psse_results_migration_test.py`, `day_ahead_expose_test.py`) accept the new file.
- **Contract**: `grid_study_contract.py` gains `SOLVERS = ("psse", "pandapower")` and `MAX_ROWS = 8`; `COLUMNS`, `FORBIDDEN` and `STALE_AFTER_MINUTES` unchanged. `grid_study_expose_test.py` changed comments only.

## Verification (this machine, Windows, PostgreSQL 17.12 throwaway cluster, PSSE_REQUIRE_PG=1)

- Plan regression set: 105 passed, 2 deselected (16 + 14 + 12 + 24 + 23 + 16), nothing skipped.
- Task 2 gate alone: 59 passed, 2 deselected.
- Inertness: `git diff --quiet bce1c3b` over `backend/psse_job`, `backend/pandapower_job`, the three applied migrations and both requirements files exits 0.
- File-scope gate for plan 06-01 exits 0; `private_leak_scan --staged` exited 0 before both commits.
- Acceptance greps: one `distinct on (r.solver)` line, 20 column-comment statements, one `order by d.city, n.solver;` line, 6 checks in `verify_solver_tag.sql`, 0 references to the retired check name, 16 and 14 collected tests, 0 logic lines changed in `grid_study_expose_test.py`.

## Deviations from Plan

**1. [Process] Tasks 1 and 2 committed as one commit.** The plan expected a planned red window (five tests in three other files) between the tracer and Task 2. The orchestrator allowed folding the Task 2 edits into the Task 1 commit to keep every commit green. Commit `fe98f29` holds both; Task 3 is `10f08ea`. No code change followed from this.

**2. [Rule 1 - Bug, own test] Header phrase split across lines.** The first full run failed `test_text_header_names_the_order_and_the_owner_steps` because the migration header wrapped `verify_solver_tag.sql (6 checks)` onto two lines. The header was re-wrapped so each owner-step phrase sits on one line; included in commit `10f08ea`.

**3. [Rule 3 - Blocking, authoring] Header wording.** The first draft of the migration header repeated `distinct on (r.solver)` in a comment, which would have made the plan's grep list two lines. Reworded before the first commit.

Otherwise the plan was executed as written.

## Known issues not touched

- Known Windows-only failures deselected as instructed (CRLF byte-hash tests, matplotlib test); not caused by this plan.
- Working-tree line endings: several test files in this repository are CRLF and others LF; edits kept each file's existing style. Git reports the usual LF-to-CRLF warnings.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or file access; the view exposes the same 20 columns (T-06-01 asserted by the whitelist and FORBIDDEN tests as anon and authenticated with both solvers stored).

## Self-Check: PASSED

- FOUND: supabase/migrations/20261126200000_latest_grid_study_per_solver.sql
- FOUND: backend/tests/grid_study_per_solver_test.py
- FOUND commits fe98f29 and 10f08ea on feature/pandapower-solver (2 commits measured from the plan ledger base 8321aa1)
