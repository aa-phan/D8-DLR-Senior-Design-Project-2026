-- supabase/migrations/20261118200000_psse_run_solver_tag.sql
--
-- Let public.psse_run hold PSS/E runs and runs of a second power-flow program side by side (the
-- pandapower-solver workstream's DB-01, decisions D-01 and D-02 of its phase 3).
--
-- Creates:
--   column public.psse_run.solver          text, not null, default 'psse': the program that produced
--                                          the run, 'psse' or 'pandapower'.
--   column public.psse_run.solver_version  text, nullable: that program's version as it reported it.
--   constraint psse_run_solver_ck          solver is 'psse' or 'pandapower'.
--   constraint psse_run_solver_version_ck  solver_version, when present, is 1 to 100 characters.
--   constraint psse_run_run_id_ck          replaced (same name): the run id starts with psse- or pp-,
--                                          then the UTC stamp and 8 hex digits as before.
--   constraint psse_run_solver_run_id_ck   the run id prefix names the program: a psse- id is stored
--                                          only with solver 'psse' and a pp- id only with solver
--                                          'pandapower'.
--
-- Why the tie: the column default is 'psse', so an older or buggy writer that does not know the
-- column and sends a pp- run id gets the default, and that insert fails loudly on
-- psse_run_solver_run_id_ck. A run of the second program can never be stored as PSS/E.
--
-- Existing runs: every row stored before this file has a psse- id and reads solver 'psse' and
-- solver_version NULL through the column default. A constant default is kept in the catalog, so
-- there is no UPDATE and no table rewrite. Adding the checks scans the table once under a short
-- exclusive lock (about 19 rows; the PSS/E writer is paused). NOT VALID is not used, so no
-- constraint is left unvalidated.
--
-- Privileges: none are changed. The writer role's table-level INSERT and SELECT grant on
-- public.psse_run, from the migration that created the table, already covers the new columns, so
-- this file adds no grant, no revoke, no role and no credential (D-02). The four psse_* tables stay
-- private. No index is added: at 24 runs a day the existing slot_time index is enough.
--
-- The public view section, if present below, is described there.
--
-- Additive: it never edits an applied migration (20261109233541_psse_results.sql and
-- 20261116200000_expose_latest_grid_study.sql are untouched). Idempotent: the columns are added
-- only if missing and every constraint is dropped if it exists, then added, so a second run leaves
-- the same definitions. The owner applies it with `supabase db push --db-url ...` and then runs the
-- read-only check supabase/ops/verify_solver_tag.sql together with verify_psse_results.sql and
-- verify_exposure.sql.

alter table public.psse_run
    add column if not exists solver text not null default 'psse',
    add column if not exists solver_version text;

alter table public.psse_run
    drop constraint if exists psse_run_solver_ck,
    drop constraint if exists psse_run_solver_version_ck,
    drop constraint if exists psse_run_solver_run_id_ck,
    drop constraint if exists psse_run_run_id_ck;

alter table public.psse_run
    add constraint psse_run_solver_ck check (solver in ('psse', 'pandapower')),
    add constraint psse_run_solver_version_ck check (length(solver_version) between 1 and 100),
    add constraint psse_run_run_id_ck check (run_id ~ '^(psse|pp)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$'),
    add constraint psse_run_solver_run_id_ck check ((solver = 'psse' and left(run_id, 5) = 'psse-') or (solver = 'pandapower' and left(run_id, 3) = 'pp-'));

comment on column public.psse_run.solver is 'none (label): the power-flow program that produced the run, psse (Siemens PSS/E) or pandapower; the run id starts with psse- or pp- to match.';
comment on column public.psse_run.solver_version is 'none (label): that program''s version as it reported it; NULL for a PSS/E run (its version is psse_version) and NULL when the study was not reached.';
