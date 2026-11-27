# Phase 6 apply record (counts only)

## Local evidence

- Date (UTC): 2026-11-26
- Commit the checks ran on: aa3d093 (branch `feature/pandapower-solver`)
- Test command as run (repository root, Git Bash, throwaway local Postgres 17 started by the test harness):
  `DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 DEF01_REQUIRE_BRANCH=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs` on the nine Phase 6 test files (`grid_study_per_solver_test.py`, `grid_study_expose_test.py`, `solver_tag_owner_check_test.py`, `expose_migration_test.py`, `psse_results_migration_test.py`, `day_ahead_expose_test.py`, `solver_tag_migration_test.py`, `grid_study_def01_text_test.py`, `rest_api_doc_test.py`) with the four `--deselect` options below.
- Summary line: `173 passed, 4 deselected in 268.96s (0:04:28)`. Passed 173, deselected 4, skipped 0, failed 0, exit code 0.
- Four deselected tests (known Windows-only failures: the first three compare CRLF byte hashes of applied migration files, the fourth needs matplotlib, which is absent here; all four pass on the owner's Mac, and the inertness diff below covers the same risk for the applied files):
  - `backend/tests/expose_migration_test.py::test_phase6_migrations_are_unchanged_after_apply`
  - `backend/tests/expose_migration_test.py::test_is_provisional_reads_the_real_labels`
  - `backend/tests/psse_results_migration_test.py::test_psse_migration_is_unchanged_after_apply`
  - `backend/tests/day_ahead_expose_test.py::test_expose_migration_is_unchanged_after_apply`
- Leak scan, working tree (`backend/private_leak_scan.py`): exit code 0 (it reported 36 files not scanned as binary or over 2 MiB, and no match).
- Inertness diff against the phase start commit bce1c3b (`git diff --quiet` over `backend/psse_job`, `backend/pandapower_job`, `supabase/migrations/20261109233541_psse_results.sql`, `supabase/migrations/20261116200000_expose_latest_grid_study.sql`, `supabase/migrations/20261118200000_psse_run_solver_tag.sql`, `requirements.txt`, `requirements-pandapower.txt`): exit code 0, nothing differs.
- Migration the owner applies: `supabase/migrations/20261126200000_latest_grid_study_per_solver.sql` (only after the Phase 5 soak record reads `Soak verdict: pass`, decision D-02).
- Counts the owner must see afterwards, all ok true: `supabase/ops/verify_solver_tag.sql` 6 of 6, `supabase/ops/verify_psse_results.sql` 7 of 7, `supabase/ops/verify_exposure.sql` 37 of 37.
- Note for the owner, pre-existing and outside this phase: `docs/data-science/decisions/dlr_live_runbook.md` line 673 still says `verify_exposure.sql` returns "29 rows, all ok"; the live count was 36 on 2026-11-25 and is 37 after this apply.

## Owner live apply

Not recorded yet.

## Dashboard hand-over

Not recorded yet.
