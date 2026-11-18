-- supabase/ops/verify_solver_tag.sql
--
-- pandapower-solver workstream, phase 3 (DB-01, success criterion 4, decision D-07): the read-only
-- check of the solver tag that supabase/migrations/20261118200000_psse_run_solver_tag.sql adds to
-- public.psse_run.
--
-- One SELECT, no writes. It returns one row per check, in the order listed below:
-- (check_name, ok, detail). Every ok must be true. The local test
-- (backend/tests/solver_tag_owner_check_test.py) runs this same file on a throwaway Postgres with
-- every migration applied, and makes each check fail once. The owner runs it against the live
-- project right after `supabase db push` applies the solver-tag migration, together with
-- verify_psse_results.sql and verify_exposure.sql; all three all ok shows that the existing runs are
-- tagged psse and nothing else changed. This directory is never applied by the Supabase CLI; it is
-- not a migration.
--
-- The detail column holds counts and yes/no answers only: never a run id, a hash, a case name or
-- any other stored value.
--
-- What each check proves, in plain English:
--   psse_run_solver_column_is_text_not_null_default_psse
--       the column solver exists on public.psse_run as text, cannot be null and defaults to psse,
--       so an older writer that does not send it stores psse
--   psse_run_solver_version_column_is_nullable_text
--       the column solver_version exists as text and may be null (a PSS/E run has none)
--   psse_run_solver_constraints_exist
--       the four check constraints (psse_run_solver_ck, psse_run_solver_version_ck,
--       psse_run_run_id_ck, psse_run_solver_run_id_ck) are on public.psse_run
--   psse_prefixed_runs_are_tagged_psse
--       no run whose id starts with the PSS/E prefix has a solver other than psse, so every run
--       stored before the migration reads psse
--   pp_prefixed_runs_are_tagged_pandapower
--       no run whose id starts with the second program's prefix has a solver other than pandapower
--   psse_runs_carry_no_solver_version
--       no run tagged psse has a solver_version
--
-- A missing column turns its checks false instead of raising an error: the run rows are read as
-- JSON, so a solver column that is not there yet reads as null. The table public.psse_run itself has
-- existed since 20261109233541_psse_results.sql.

with
-- The two new columns as they exist now (no row when a column is missing).
solver_columns as (
    select c.column_name::text as column_name,
           c.data_type::text as data_type,
           c.is_nullable::text as is_nullable,
           c.column_default::text as column_default
      from information_schema.columns c
     where c.table_schema = 'public'
       and c.table_name = 'psse_run'
       and c.column_name in ('solver', 'solver_version')
),
constraint_names(name) as (
    values ('psse_run_solver_ck'),
           ('psse_run_solver_version_ck'),
           ('psse_run_run_id_ck'),
           ('psse_run_solver_run_id_ck')
),
-- The four constraints as check constraints on public.psse_run (oid is null when one is missing).
found_constraints as (
    select n.name, c.oid
      from constraint_names n
      left join pg_constraint c
        on c.conname = n.name
       and c.conrelid = to_regclass('public.psse_run')
       and c.contype = 'c'
),
-- Every run, with the two tag columns read through JSON so a missing column gives null.
runs as (
    select r.run_id::text as run_id,
           to_jsonb(r) ->> 'solver' as solver,
           to_jsonb(r) ->> 'solver_version' as solver_version
      from public.psse_run r
),
run_counts as (
    select count(*) as all_runs,
           count(*) filter (where left(run_id, 5) = 'psse-') as psse_id_runs,
           count(*) filter (where left(run_id, 5) = 'psse-' and solver is distinct from 'psse') as psse_id_mistagged,
           count(*) filter (where left(run_id, 3) = 'pp-') as pp_id_runs,
           count(*) filter (where left(run_id, 3) = 'pp-' and solver is distinct from 'pandapower') as pp_id_mistagged,
           count(*) filter (where solver = 'psse') as tagged_psse,
           count(*) filter (where solver = 'pandapower') as tagged_pandapower,
           count(*) filter (where solver = 'psse' and solver_version is not null) as psse_with_version
      from runs
)
select check_name, ok, detail
  from (
    select 1 as ord,
           'psse_run_solver_column_is_text_not_null_default_psse'::text as check_name,
           (select count(*) from solver_columns
             where column_name = 'solver' and data_type = 'text' and is_nullable = 'NO'
               and column_default = '''psse''::text') = 1 as ok,
           'solver column found: ' || (select count(*) from solver_columns where column_name = 'solver')::text ||
               ' of 1, text: ' || (select count(*) from solver_columns where column_name = 'solver' and data_type = 'text')::text ||
               ', not null: ' || (select count(*) from solver_columns where column_name = 'solver' and is_nullable = 'NO')::text ||
               ', default psse: ' || (select count(*) from solver_columns
                                       where column_name = 'solver' and column_default = '''psse''::text')::text as detail
    union all
    select 2,
           'psse_run_solver_version_column_is_nullable_text',
           (select count(*) from solver_columns
             where column_name = 'solver_version' and data_type = 'text' and is_nullable = 'YES') = 1,
           'solver_version column found: ' ||
               (select count(*) from solver_columns where column_name = 'solver_version')::text ||
               ' of 1, text: ' ||
               (select count(*) from solver_columns where column_name = 'solver_version' and data_type = 'text')::text ||
               ', nullable: ' ||
               (select count(*) from solver_columns where column_name = 'solver_version' and is_nullable = 'YES')::text
    union all
    select 3,
           'psse_run_solver_constraints_exist',
           (select count(*) from found_constraints where oid is not null) = 4,
           (select count(*) from found_constraints where oid is not null)::text || ' of 4 constraints found'
    union all
    select 4,
           'psse_prefixed_runs_are_tagged_psse',
           (select psse_id_mistagged from run_counts) = 0,
           (select psse_id_runs from run_counts)::text || ' runs with a psse id prefix, ' ||
               (select psse_id_mistagged from run_counts)::text || ' not tagged psse; runs in all ' ||
               (select all_runs from run_counts)::text || ' (tagged psse ' ||
               (select tagged_psse from run_counts)::text || ', tagged pandapower ' ||
               (select tagged_pandapower from run_counts)::text || ')'
    union all
    select 5,
           'pp_prefixed_runs_are_tagged_pandapower',
           (select pp_id_mistagged from run_counts) = 0,
           (select pp_id_runs from run_counts)::text || ' runs with a pp id prefix, ' ||
               (select pp_id_mistagged from run_counts)::text || ' not tagged pandapower'
    union all
    select 6,
           'psse_runs_carry_no_solver_version',
           (select psse_with_version from run_counts) = 0,
           (select tagged_psse from run_counts)::text || ' runs tagged psse, ' ||
               (select psse_with_version from run_counts)::text || ' of them with a solver version'
  ) as checks
 order by ord;
