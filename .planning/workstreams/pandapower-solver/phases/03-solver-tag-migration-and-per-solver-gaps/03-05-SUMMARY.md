---
phase: 03-solver-tag-migration-and-per-solver-gaps
plan: 05
subsystem: solver-tag-owner-check-and-public-view-guard
tags: [solver-tag, owner-check, read-only-sql, public-view, latest_grid_study, decision-D-03, migration]

requires:
  - phase: 03 plan 01
    provides: migration 20261118200000_psse_run_solver_tag.sql (the file this plan appends the view section to), psse_local_pg.apply_solver_tag_migration and make_run_id(prefix=)
provides:
  - supabase/ops/verify_solver_tag.sql - the owner's read-only post-apply check, one SELECT, seven checks
  - the migration's last section - public.latest_grid_study guarded to PSS/E runs (owner chose "guard" on 2026-11-18)
  - backend/tests/solver_tag_owner_check_test.py - text pins that run here, database proofs that skip here
  - grid_study_expose_test.test_the_migration_reapplies_cleanly re-applies the whole chain from the grid-study file onward
affects: [Phase 5 live write gate (no longer blocked on Phase 6 for the view), Phase 6 per-solver view (replaces the guarded view), owner's live apply]

actuals:
  tokens: 8619
  tasks: 3
  commits: 3
plan_head_before: 8642233c16963d2a3df9b3c259af8a0d96da5127
plan_head_after: cbf3e1215c041599fd40471ecf1d7a28b63d682c

tech-stack:
  added: []
  patterns:
    - "Owner check files are one read-only SELECT of (check_name, ok, detail) with counts only in detail, a missing column reads as null through to_jsonb so a check turns false instead of raising"
    - "A view replaced by a later migration is re-applied with the whole chain from its first migration onward, never as one file (Pitfall 1)"
    - "A guarded view statement is pinned as the earlier statement plus exactly one added line, by line diff"

key-files:
  created:
    - supabase/ops/verify_solver_tag.sql
    - backend/tests/solver_tag_owner_check_test.py
  modified:
    - supabase/migrations/20261118200000_psse_run_solver_tag.sql
    - backend/tests/grid_study_expose_test.py

key-decisions:
  - "D-03 (owner, 2026-11-18, interactive question): guard public.latest_grid_study to PSS/E runs in the solver-tag migration"
  - "The guard check reads the view definition (pg_get_viewdef contains solver = 'psse'); it is the seventh check of the owner's script"
  - "A missing public.psse_run table (not a missing column) would still raise in the owner script; the table has existed since 20261109233541_psse_results.sql"

requirements-completed: []

coverage:
  - id: D1
    description: "The owner's read-only check is one SELECT with no write keyword and the seven check names pinned in order"
    requirement: "DB-01"
    verification:
      - kind: unit
        ref: "backend/tests/solver_tag_owner_check_test.py#test_text_tracer_the_check_is_one_read_only_select_with_the_pinned_names"
        status: pass
    human_judgment: false
  - id: D2
    description: "The guarded view statement is the earlier statement plus exactly one line (and r.solver = 'psse'); revoke, grant, owner-rights option and the 20 column comments are word for word the earlier ones; the select list is the 20 contract columns in order"
    requirement: "DB-01"
    verification:
      - kind: unit
        ref: "backend/tests/solver_tag_owner_check_test.py#test_text_the_guarded_view_is_the_old_view_plus_one_predicate"
        status: pass
      - kind: unit
        ref: "backend/tests/solver_tag_owner_check_test.py#test_text_the_guarded_view_section_follows_the_table_changes_and_names_the_owner_decision"
        status: pass
    human_judgment: false
  - id: D3
    description: "On a throwaway Postgres: every check is ok after the whole chain, each check can be made to fail once, a newer pandapower run never changes the view, the guard keeps columns, comments, owner and grants"
    requirement: "DB-01"
    verification: []
    human_judgment: true
    rationale: "Database proof. All test_db_* tests of this plan were written but only SKIPPED on this machine (no Postgres); the SQL has never run on a real database."

duration: 30min
completed: 2026-11-18
status: complete
---

# Phase 3 Plan 05: Owner's Solver-Tag Check and the Guarded Public View Summary

**The owner now has a one-SELECT read-only script, `supabase/ops/verify_solver_tag.sql`, that checks the two new columns, the four constraints, that every `psse-` run reads `psse` with no `solver_version`, and that `latest_grid_study` shows PSS/E runs only; and, on the owner's answer "guard" (2026-11-18), the solver-tag migration ends with the view replaced by its earlier statement plus the single line `and r.solver = 'psse'`, with its 20 columns, order, owner rights, grants and comments unchanged.**

## Database tier status

**The database proofs of this plan were only SKIPPED on this machine. They were never run, so nothing here proves the database half of DB-01, and the migration SQL, the view guard and the owner's check script have never run on any Postgres.** There is no Postgres here (no `initdb`, `pg_ctl`, `psql`, Docker or Supabase CLI). What did run here is the text tier only: the one-read-only-SELECT pin, the line-diff pin of the guarded view statement against the earlier statement, the grants and comment pins, and the check-name order pin.

Written but only SKIPPED here (10 tests in `backend/tests/solver_tag_owner_check_test.py`, all with the harness reason "set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the PSS/E Postgres proofs"):

- `test_db_tracer_every_check_is_ok_after_the_chain` - every one of the seven checks ok after the whole migration chain with one PSS/E and one pandapower run stored; no detail holds a run id, a prefix or a version; `verify_psse_results.sql` and `verify_exposure.sql` also all ok on the same database.
- `test_db_each_check_can_fail` x 7 - each check is ok before, false after its own sabotage (drop the default, make `solver_version` not null, drop the tie constraint, a `psse-` run tagged pandapower, a `pp-` run tagged psse, a psse run with a version, the earlier unguarded view statement re-applied), and ok again after the rollback.
- `test_db_a_newer_pandapower_run_never_changes_the_view` - a complete PSS/E run at H-2h and a newer complete pandapower run at H-1h give four rows, all slot H-2h and solver psse; with only pandapower runs the view is empty.
- `test_db_the_guard_keeps_columns_comments_and_privileges` - on a fresh database holding the chain up to the grid-study file, applying the solver-tag file leaves column names and order, column comments, `relacl`, owner and `reloptions` equal, and puts the guard into the definition.
- `grid_study_expose_test.test_the_migration_reapplies_cleanly` (edited) - re-applies every migration from the grid-study file onward twice and compares the view definition and permission list.

Verified here: with `PSSE_REQUIRE_PG=1`, no database variable set, `-k db`, the database tests of `solver_tag_owner_check_test.py` all end in `error` (10 errors: the 10 `test_db_*` cases), so a missing Postgres cannot pass for proof.

On the owner's Mac (must report **0 skipped**; `local_pg.require_local_pg` in the last three files ignores `PSSE_REQUIRE_PG`, so read the skipped count):

```
DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/solver_tag_owner_check_test.py backend/tests/solver_tag_migration_test.py backend/tests/grid_study_expose_test.py backend/tests/expose_migration_test.py backend/tests/psse_results_migration_test.py
```

DB-01 stays **Pending** in REQUIREMENTS.md: its text half is proven here, its database half is not.

## Owner's live steps (not done by this plan; nothing touches the live project)

1. Apply the migration: `supabase db push --db-url ...` (the owner's own connection; no credential is in the repository).
2. Run the three read-only checks and expect every `ok` true: `supabase/ops/verify_solver_tag.sql`, `supabase/ops/verify_psse_results.sql`, `supabase/ops/verify_exposure.sql`. This is success criterion 4. The expected `verify_solver_tag.sql` rows: the existing 19-or-so runs all read `psse` (check 4 detail shows how many runs have a `psse` id prefix and 0 not tagged psse), 0 `pp` runs, 0 psse runs with a solver version, and the view definition filters on solver psse.

## Performance

- **Duration:** about 30 min
- **Started:** 2026-11-18T21:35:00Z (approx.)
- **Completed:** 2026-11-18T22:10:00Z (approx.)
- **Tasks:** 3 (Task 2 was a decision checkpoint, already answered)
- **Files modified:** 4

## Accomplishments

- `supabase/ops/verify_solver_tag.sql`: one SELECT returning `(check_name, ok, detail)` in this order: the `solver` column (text, not null, default psse), the `solver_version` column (nullable text), the four constraints exist, `psse-` runs tagged psse, `pp-` runs tagged pandapower, psse runs carry no `solver_version`, and the view reads PSS/E runs only. Run rows are read through `to_jsonb`, so a `solver` column that is not there yet reads as null and turns the checks false instead of raising. `detail` holds counts and yes/no counts only.
- The migration's view section: the earlier view statement copied word for word with one added line in `newest_run`, the earlier revoke and grant, the earlier view comment plus one sentence, and the 20 earlier column comments. The header's placeholder sentence is replaced by a description of the section, and the header lines that said the file adds no grant or revoke now say it adds none on the result tables and only repeats the view's own earlier ones.
- `solver_tag_owner_check_test.py` (392 lines): 3 text tests that run here and 10 database tests that skip here.
- `grid_study_expose_test.test_the_migration_reapplies_cleanly` re-applies the chain (Pitfall 1), so re-applying the grid-study file alone can no longer restore the unguarded view in a test.

## Task Commits

1. **Task 1 (tracer): the owner's read-only check** - `85c7e8e` (feat)
2. **Task 2: owner decision D-03** - no commit; answered "guard" by the owner on 2026-11-18 (see Decisions Made)
3. **Task 3: the guard, test first** - `ed9a990` (test, RED: three text pins fail, database proofs skip) then `cbf3e12` (feat, GREEN: migration section and the seventh check)

**Plan metadata:** the docs commit that carries this SUMMARY, STATE.md and ROADMAP.md.

## Files Created/Modified

- `supabase/ops/verify_solver_tag.sql` - the owner's read-only post-apply check, seven checks
- `backend/tests/solver_tag_owner_check_test.py` - text pins and database proofs of the check and of the guarded view
- `supabase/migrations/20261118200000_psse_run_solver_tag.sql` - header edits and the appended view section (93 lines added); the four table statements and two column comments are untouched
- `backend/tests/grid_study_expose_test.py` - only `test_the_migration_reapplies_cleanly` changed

## Decisions Made

- **D-03 answered by the owner: "guard" (Guard the view, the recommended option).** Asked of the owner in this session through an interactive question on 2026-11-18 (plain-language wording: "Should the new migration change that view so it only ever shows PSS/E results until Phase 6?"); the owner selected "Guard the view (Recommended)". The orchestrator relayed the answer into this execution and Task 2's checkpoint was treated as answered, not auto-selected. Consequence recorded: the view shows the last PSS/E run (stale flag true while the laptop stays paused) even after pandapower runs exist; Phase 5's live write is therefore no longer blocked on Phase 6 for the dashboard-label reason. Phase 6 replaces the guarded view with the per-solver one. The guard is costly to undo (another migration) once the owner applies it live.
- The seventh check reads the view definition (`pg_get_viewdef` contains `solver = 'psse'`), not the rows, so it works on an empty database and with no run stored.
- Check 6 is vacuous when the `solver_version` column is missing; check 2 is what fails then.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The first draft of the section-order test used the raw statement text**
- **Found during:** Task 3 (GREEN run)
- **Issue:** `test_text_the_guarded_view_section_follows_the_table_changes_and_names_the_owner_decision` searched raw statements for `"alter table public.psse_run "` (trailing space) but the migration breaks the line after the table name, so `max()` ran on an empty list.
- **Fix:** the statements are whitespace-normalised before the prefix test.
- **Files modified:** backend/tests/solver_tag_owner_check_test.py
- **Verification:** the text tests pass (15 passed in the three files).
- **Committed in:** `cbf3e12`

**2. [Rule 2 - Missing Critical] Migration header said the file adds no grant or revoke**
- **Found during:** Task 3
- **Issue:** with the view section the file now issues the view's own revoke and grant, so the sentence "this file adds no grant, no revoke" was false.
- **Fix:** it now says no grant or revoke on the result tables, and that the view section repeats the view's earlier revoke and grant unchanged. Comment lines only; plan 03-01's tests still pass.
- **Files modified:** supabase/migrations/20261118200000_psse_run_solver_tag.sql
- **Committed in:** `cbf3e12`

**3. Plan wording, missing table:** the plan asks that "a missing column or table makes a check false instead of raising". A missing column does. A missing `public.psse_run` table still raises in the runs query (the table has existed on the live project since 20261109233541_psse_results.sql and a plain SELECT cannot name a table that may not exist without dynamic SQL, which could not be exercised on any Postgres here). Left as is and stated here; not a database-tier claim either way.

**Total deviations:** 2 auto-fixed (1 bug in a test, 1 comment correctness), 1 stated narrowing of a plan sentence.

## Issues Encountered

- A stale commit ledger (`.git/gsd-plan-head-before-03-05` held `40721fb`, an older plan's commit) was found at the start and overwritten with HEAD `8642233`, the 03-04 docs commit, before the first task commit; `plan_head_before`, `plan_head_after` and `commits: 3` above are measured from it (`git rev-list --count 8642233..cbf3e12` = 3).
- The migration test subset still reports only the three known CRLF byte-hash failures (`psse_results_migration_test::test_psse_migration_is_unchanged_after_apply`, `day_ahead_expose_test::test_expose_migration_is_unchanged_after_apply`, `expose_migration_test::test_phase6_migrations_are_unchanged_after_apply`); not touched.
- Other database test files (`pandapower_solver_tag_test`, `pandapower_study_job_test`, `psse_gaps_solver_test`, `solver_tag_migration_test`) build their schema with `apply_solver_schema`, which has no grid-study migration; the guarded view section there now creates `latest_grid_study` fresh (the statement is `create or replace`, the roles exist, the default privileges are revoked by the section's own revoke). Their assertions read neither the view nor the public roles, so nothing should change; unproven here, covered by the Mac run.

## Tests run here (real counts)

- `solver_tag_owner_check_test.py` + `solver_tag_migration_test.py` + `grid_study_expose_test.py`: **15 passed, 0 failed, 28 skipped** (the skips are the database tier, all with the harness Postgres reason).
- `solver_tag_owner_check_test.py` alone: 3 passed, 10 skipped.
- With `PSSE_REQUIRE_PG=1` and no database: `-k db` gives **10 errors**, 0 passed.
- Migration/expose subset (`psse_results_migration_test`, `expose_migration_test`, `day_ahead_expose_test`, `solver_tag_migration_test`): **28 passed, 3 failed, 72 skipped**; the 3 failures are the known CRLF byte-hash tests.
- File-scope gate (PLAN=03-05): exit 0. Staged leak scan before each commit: exit 0. Full leak scan: exit 0. The word `pandapower` does not appear in any `backend/psse_job/*.py`.

## Known Stubs

None.

## Threat Flags

None. The public surface (`latest_grid_study`) is narrowed by the guard, not widened; no endpoint, grant or credential is added (T-03-18 mitigated by the guard and its database proof, T-03-19 by the unchanged owner rights, revoke, grant and `security_invoker = false` pinned in text, T-03-20 by the one-read-only-SELECT pin, T-03-21 by counts-only details; the database halves are only skipped here).

## User Setup Required

None for tooling. The owner's live steps are listed above (apply the migration, then the three read-only checks).

## Next Phase Readiness

- Phase 3 has no remaining plan. Phase 3 verification is run by the orchestrator.
- Database tier of DB-01, DB-02 and DB-03 is only SKIPPED here; the Mac command above, with the commands of plans 03-01 to 03-04, must report 0 skipped before those requirements are marked complete.
- Phase 5 can write a live pandapower run without the dashboard labelling it PSS/E, once the owner has applied the migration; the view will keep showing the last PSS/E run until Phase 6 replaces it.

## Self-Check: PASSED

- FOUND: supabase/ops/verify_solver_tag.sql
- FOUND: backend/tests/solver_tag_owner_check_test.py
- FOUND: supabase/migrations/20261118200000_psse_run_solver_tag.sql (view section present, `and r.solver = 'psse'` once)
- FOUND commits: 85c7e8e, ed9a990, cbf3e12 (all ancestors of HEAD)

---
*Phase: 03-solver-tag-migration-and-per-solver-gaps*
*Completed: 2026-11-18*
