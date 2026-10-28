# PSS/E result tables: hand-off to production-pipeline Phase 6

**Date:** 2026-10-28
**From:** pss-e-integration Phase 1 (DBX-01)
**To:** the owner of production-pipeline Phase 6
**Status:** proposal; nothing here is applied, and no production-pipeline file was edited

## Summary

The PSS/E job needs four private result tables and a write-only database role, `dlr_psse_writer`. They are specified in [the schema specification](../schema/psse_results_v1.md), with the reference DDL [`psse_results_v1.sql`](../schema/psse_results_v1.sql) and the read-only completeness checks [`psse_results_v1_checks.sql`](../schema/psse_results_v1_checks.sql). The tables are `psse_run`, `psse_dispatched_capacity`, `psse_voltage_margin` and `psse_contingency_result`.

DBX-01 ships through Phase 6's migration: this workstream adds no migration (D-01). This note says what Phase 6 must add and which of its plans that touches. Phase 6's owner decides.

## What Phase 6 must add

1. One migration `supabase/migrations/<UTC ts>_psse_results.sql` whose body is the region of `psse_results_v1.sql` from the `-- BEGIN psse_results_v1` line to the `-- END psse_results_v1` line, copied verbatim. It should sort after Phase 6's expose and soak-log migrations.
2. The role `dlr_psse_writer` is created by that region, without a credential. The owner sets its password out of band, and the laptop keeps the session-pooler connection string as the secret `SUPABASE_PSSE_DB_URL` (never committed).
3. `supabase/ops/verify_psse_results.sql`, read-only, returning `check_name, ok, detail`: the four tables exist with row-level security on; `anon` and `authenticated` hold nothing on them; `dlr_psse_writer` holds exactly INSERT and SELECT on them and nothing on `city_rating`, `pipeline_run` or `latest_rating`; the role is not superuser, createrole, createdb or bypassrls. The completeness checks in `psse_results_v1_checks.sql` can be run by the owner after the first real run.
4. A sha256 pin test that compares the migration's marked region with the value under "Reference DDL identity" below.
5. A Phase 6 decision recording the scope change: `06-CONTEXT.md` lists PSS/E-side code as not in scope, and production-pipeline REQUIREMENTS.md lists PSS/E results back into the database as out of scope (a follow-on).

## Phase 6 plans this touches

- **06-09** (the owner's push). Its truths say "the dry run listed exactly the two Phase 6 files" and "after the push both applied migration files are pinned by SHA-256 in backend/tests/expose_migration_test.py". Its Task 1 acceptance check reads "exactly four migrations are tracked and the two Phase 6 files sort last". A third Phase 6 migration breaks all three statements. Two resolutions:
  - Option (a): amend 06-09 to three Phase 6 files and five tracked migrations, and pin all three; one owner push.
  - Option (b): leave 06-09 untouched and add a separate later owner step (for example a new plan 06-14) with its own dry run, push and sha256 pin.

  Phase 6's planner chooses.
- **06-01**. It creates the expose migration, `backend/tests/local_pg.py` (which applies Supabase's legacy default privileges before the migrations) and `supabase/ops/verify_exposure.sql`. The rule in `verify_exposure.sql` that `anon` and `authenticated` hold SELECT on exactly two objects (`city_rating` and `latest_rating`) stays true, because the PSS/E DDL gives them nothing; that check is the regression net if anyone adds a consumer privilege to these tables. The DDL's explicit revoke undoes the legacy default privileges that `local_pg.py` applies, which `backend/tests/psse_schema_pg_test.py` proves. The PSS/E migration should still sort after the expose migration.
- `dlr_writer` is untouched: the new role is separate.

## Reference DDL identity

The marked region is every line of `psse_results_v1.sql` from the line `-- BEGIN psse_results_v1` through the line `-- END psse_results_v1`, both included. To hash it, read the file in text mode, give every line a single LF ending (so a CRLF Windows checkout and an LF checkout agree), encode as UTF-8 and take the sha256. `backend/tests/psse_schema_doc_test.py` recomputes this value and fails if the DDL changes without this note.

Marked-region sha256: 955f349d2df66394dbec4378ddcc2d9eb61f7e37bd4eda8de4b70de16c3a6643

## What is already proven

- `backend/tests/psse_schema_pg_test.py` applies the DDL after the Phase 4 migrations on a local Postgres with the legacy default privileges, and proves the privileges, the integrity rules including the composite foreign key, and the completeness checks.
- `backend/tests/psse_schema_doc_test.py` keeps the specification, the DDL text and this note in step.
- Plan 01-04 of this phase adds job-side tests that write through the role.

## What this workstream does not do

- It adds no file under `supabase/migrations/`.
- It edits no production-pipeline plan or file.
- It takes no live action and applies nothing to any database.
- It adds no consumer privilege: the results stay private.

## Questions for Phase 6's owner

1. Which vehicle: option (a) or option (b) above?
2. Please confirm the results stay private (D-03).
3. Do each city's mapped branches share one base kV? The job assumes so; Power Systems' mapping is the authority.
4. Does this hand-off need to land before a given Phase 6 wave?
