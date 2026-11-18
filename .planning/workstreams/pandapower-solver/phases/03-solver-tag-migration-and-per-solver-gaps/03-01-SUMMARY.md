---
phase: 03-solver-tag-migration-and-per-solver-gaps
plan: 01
subsystem: database-migration
tags: [postgres, migration, check-constraint, solver-tag, text-tier, database-tier, skip-honestly]

requires:
  - phase: 03 (context)
    provides: decisions D-01 (columns and run-id tie), D-02 (idempotent, no role or grant), D-07 (database proofs skip here and are never claimed)
provides:
  - supabase/migrations/20261118200000_psse_run_solver_tag.sql - solver (default psse) and solver_version on psse_run, four check constraints, two column comments
  - backend/tests/solver_tag_migration_test.py - 9 text tests (run here) and 7 database tests (skipped here)
  - backend/tests/psse_local_pg.py - SOLVER_TAG_MIGRATION, apply_solver_tag_migration, apply_solver_schema, make_run_id(prefix=)
affects: [03-02 run record and writer tag, 03-03 per-solver gaps, 03-05 view guard (appends a section to this same file) and verify_solver_tag.sql, Phase 5 hourly workflow, Phase 6 per-solver view]

actuals:
  tokens: 6900
  tasks: 3
  commits: 3
plan_head_before: a75d86ad09768a9f26dfa5e06b9784794d054862
plan_head_after: a7ac6e7785e1bfc98ded9896ccf43cba51c0711b

tech-stack:
  added: []
  patterns:
    - "Migration text is pinned by parsing literals out of the normalised statements (regex over the file), never by line number"
    - "A pre-migration database is created fresh per test inside the module's cluster, because applying the migration cannot be undone"
    - "Constraint refusals are asserted by diag.constraint_name; Postgres reports the first failing CHECK in alphabetical name order, which the test cases rely on"

key-files:
  created:
    - supabase/migrations/20261118200000_psse_run_solver_tag.sql
    - backend/tests/solver_tag_migration_test.py
  modified:
    - backend/tests/psse_local_pg.py
    - backend/tests/psse_results_migration_test.py
    - backend/tests/day_ahead_expose_test.py

key-decisions:
  - "A5: two constraints (psse_run_run_id_ck widened for the pattern, psse_run_solver_run_id_ck for the tie) rather than one combined constraint, so a test can say whether the pattern or the tie refused an insert. Equivalent in effect; the owner can ask for one."
  - "A8: no new index. At 24 runs a day the existing slot_time index is enough; Phase 6 can add (solver, slot_time desc) if its view needs it."
  - "No NOT VALID: the check scan is momentary at about 19 rows and NOT VALID would leave an unvalidated constraint behind."
  - "No byte-hash 'unchanged after apply' pin for the new file (not applied yet; CRLF checkouts break raw hashes)."

requirements-completed: []

coverage:
  - id: D1
    description: "the migration text: two columns (default psse, solver_version nullable), four named constraints with the pp-/psse- tie, drop-before-add, add-if-missing, comments only in the header, no grant/revoke/role/credential/UPDATE"
    requirement: "DB-01"
    verification:
      - kind: unit
        ref: "backend/tests/solver_tag_migration_test.py#test_text_tracer_the_migration_adds_the_tag_and_ties_it_to_the_run_id"
        status: pass
      - kind: unit
        ref: "backend/tests/solver_tag_migration_test.py#test_text_run_id_pattern_matches_the_contract_shape"
        status: pass
      - kind: unit
        ref: "backend/tests/solver_tag_migration_test.py#test_text_tie_mirror_matrix"
        status: pass
      - kind: unit
        ref: "backend/tests/solver_tag_migration_test.py#test_text_nothing_privileged_on_the_result_tables"
        status: pass
    human_judgment: false
  - id: D2
    description: "on a throwaway database, runs stored before the migration read solver psse and solver_version NULL after it with no UPDATE; each constraint refuses its case by name; the writer role inserts a tagged run through its old grant; re-applying twice changes nothing; the unchanged 17-column PSS/E writer path still writes"
    requirement: "DB-01"
    verification: []
    human_judgment: true
    rationale: "Database proofs. All 7 test_db_* tests were SKIPPED on this checkout (no Postgres) and have not passed anywhere. They must be run with the Mac command in Database tier status before the database half of DB-01 can be called proven."

duration: 35min
completed: 2026-11-18
status: complete
---

# Phase 3 Plan 01: Solver-Tag Migration Summary

**One additive, idempotent migration adds `solver` (default `psse`) and `solver_version` to `public.psse_run` and ties the run-id prefix to the solver (`pp-` only with `pandapower`, `psse-` only with `psse`) with four named check constraints, adding no grant, role or credential. Its text is proven here; its database behaviour is written but was only SKIPPED here.**

## Database tier status

**The database proofs of this plan were only SKIPPED on this machine. They were never run, so nothing in this plan proves the database half of DB-01.** There is no Postgres here (no `initdb`, `pg_ctl`, `psql`, Docker or Supabase CLI). All 7 `test_db_*` tests in `backend/tests/solver_tag_migration_test.py` report `SKIPPED` with the harness reason "set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the PSS/E Postgres proofs", and with `PSSE_REQUIRE_PG=1` and no database all 7 end in `error` (checked: `7 errors`), so a missing Postgres cannot pass for proof. The SQL itself has never been executed by any Postgres, so a syntax or semantic slip in the migration is possible until the Mac run.

Command for the owner's Mac (must report 0 skipped):

```
DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/solver_tag_migration_test.py backend/tests/psse_results_migration_test.py backend/tests/expose_migration_test.py backend/tests/grid_study_expose_test.py backend/tests/psse_writer_test.py backend/tests/psse_schema_pg_test.py
```

`local_pg.require_local_pg` (used by `grid_study_expose_test.py`, `psse_results_migration_test.py`, `expose_migration_test.py`) ignores `PSSE_REQUIRE_PG`, so read the skipped count on those files rather than relying on the exit code. DB-01 is therefore left Pending in REQUIREMENTS.md.

## Performance

- **Duration:** about 35 min
- **Tasks:** 3 (tracer, text tier, database tier)
- **Files:** 2 created, 3 modified

## Accomplishments

- The migration `20261118200000_psse_run_solver_tag.sql`: three `alter table` statements (add columns if missing; drop four constraints if they exist; add `psse_run_solver_ck`, `psse_run_solver_version_ck`, the widened `psse_run_run_id_ck` and `psse_run_solver_run_id_ck`), two unit-first column comments, and a comment-only header that points at the owner's apply step and the read-only check script plan 03-05 will write. It sorts directly after `20261116200000_expose_latest_grid_study.sql`. The applied v1 migration, the grid-study view migration and the reference DDL are untouched.
- The harness gained `apply_solver_tag_migration`, `apply_solver_schema` and `make_run_id(prefix=)` (default output byte-identical); `apply_schema` is unchanged, so every existing PSS/E database test still runs against a table without `solver`.
- The two ordering tests that fail by design once a third migration exists were edited in this plan (Pitfall 1): `psse_results_migration_test.py` now expects `[grid-study view, solver tag]` after the PSS/E migration (test renamed as the plan says), and `day_ahead_expose_test.py` allows the new suffix and `<= 3`.
- Nine text tests pin the migration without a database: the run-id regex extracted from the file full-matches `psse-` and `pp-` ids and rejects seven bad shapes, the solver vocabulary and tie pairs are parsed and mirrored in Python, every constraint is dropped before it is added, no `NOT VALID`, comments-only header, no credential word, nothing privileged on the result tables, and a statement inventory that also tolerates the view statements plan 03-05 may append.
- Seven database tests are written for the Mac: existing runs (ok, fallback, failed) read `psse` and NULL after the migration with ids, outcomes, slot times and child-row counts unchanged; the default applies; each constraint refuses its case by name (including the omitted-solver `pp-` run and a 100-character version accepted, 101 refused); the writer role inserts a tagged run with no column-level grant added; re-applying twice leaves constraint definitions, column defaults and the `psse_run` ACL unchanged; the unchanged 17-column PSS/E writer path writes on the migrated schema and reads `psse`.

## Task Commits

1. **Task 1: Tracer (migration, harness helpers, ordering tests, one tagged insert each side of the tie)** - `be506bc`
2. **Task 2: Text tier** - `1b74a9a`
3. **Task 3: Database tier** - `a7ac6e7`

## Test Results (this machine, Windows, `.venv` Python 3.12.10)

- `solver_tag_migration_test.py`: **9 passed, 7 skipped, 0 failed** (the skips are the database tier).
- Under `PSSE_REQUIRE_PG=1` with no database: the 7 database tests all end in `error` (7 errors), as intended.
- Migration text subset (7 files from the plan): **3 failed, 52 passed, 97 skipped**, identical to the baseline. The three failures are the pre-existing CRLF byte-hash tests (`psse_results_migration_test.py::test_psse_migration_is_unchanged_after_apply`, `day_ahead_expose_test.py::test_expose_migration_is_unchanged_after_apply`, `expose_migration_test.py::test_phase6_migrations_are_unchanged_after_apply`); the renamed ordering test and the day-ahead ordering test pass.
- Adjacent PSS/E tests (`psse_contract_test`, `pandapower_import_gate_test`, `psse_run_record_test`, `psse_phase4_validation_test`, `psse_writer_test`, `psse_schema_pg_test`): **68 passed, 55 skipped, 0 failed**.
- File-scope gate for `(03-01)`: exit 0. Staged leak scan before each commit: exit 0. Full leak scan: exit 0.

## Decisions Made

- **A5 (two constraints, not one combined):** the widened `psse_run_run_id_ck` carries the pattern and `psse_run_solver_run_id_ck` carries the tie, so a test can tell which one refused an insert. Same effect as one constraint; the owner can ask for a combined one.
- **A8 (no new index):** no `(solver, slot_time desc)` index; the existing `slot_time` index is enough at 24 runs a day and Phase 6 can add one.
- No `NOT VALID` and no byte-hash pin for the new file (see key-decisions).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The `pg_pre` fixture is function-scoped over a shared cluster, not module-scoped**
- **Found during:** Task 3
- **Issue:** the plan asks for a module-scoped `pg_pre` (reference schema without the migration). Task 1's tracer applies the migration to it, so `test_db_existing_runs_read_psse_after_the_migration` would start from an already migrated database and its "before the migration" assertions could never hold.
- **Fix:** a module-scoped `_cluster` fixture yields the empty database; `pg` (module) applies `apply_solver_schema` to it; `pg_pre` (per test) creates a sibling database `tag_pre_<8 hex>` in the same cluster, applies `apply_schema`, and drops it afterwards with `with (force)`. The tracer and the existing-runs test both use it. The existing-runs test also asserts the `solver` column is absent before the migration.
- **Files modified:** backend/tests/solver_tag_migration_test.py
- **Commit:** `a7ac6e7` (fixture refactor), tracer fixture first written in `be506bc`

**2. [Process] Stale commit ledger corrected**
- `.git/gsd-plan-head-before-03-01` held `cc6c59a2...` (from the other workstream's 03-01). It was overwritten with `a75d86a` (HEAD at this plan's start) before the first task commit; `plan_head_before` above is that value and `commits: 3` was measured with `git rev-list --count a75d86a..HEAD` before the summary commit.

**Total deviations:** 1 auto-fixed (fixture scope), 1 process correction. **Impact:** none on the plan's behaviours or acceptance criteria.

## Known Stubs

None. No stub, placeholder or unrun `<verify>` besides the intentionally skipped database tier described above. The seven skipped database tests are recorded here instead of in the broken-windows ledger because the ledger is optional and they are the plan's own declared Mac tier (D-07).

## Threat Flags

None. The migration adds no endpoint, role, grant or credential; the threat register entries T-03-01 to T-03-04 are covered by tests as planned (T-03-01 database half pending the Mac run).

## Issues Encountered

- A first attempt to append the database tier in one shell heredoc failed with a quoting error before anything was written; the section was then written through the Write tool and appended, with no effect on the repository.

## Next Phase Readiness

- Plan 03-02 (run record and writer) can rely on `apply_solver_schema` and `make_run_id(prefix=)`.
- Plan 03-05 appends the public view section to the same migration file; the text tests were written to hold with or without it (the header sentence "The public view section, if present below, is described there." is the marker).
- Owner steps outside this plan: run the Mac command above; apply the migration to the live project (`supabase db push --db-url ...`) only after the whole phase is reviewed.

## Self-Check: PASSED

- FOUND: supabase/migrations/20261118200000_psse_run_solver_tag.sql
- FOUND: backend/tests/solver_tag_migration_test.py
- FOUND commits: be506bc, 1b74a9a, a7ac6e7 (all ancestors of HEAD)
