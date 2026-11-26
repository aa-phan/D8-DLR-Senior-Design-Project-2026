-- supabase/ops/psse_result_size.sql
--
-- pandapower-solver workstream, phase 5 (OPS-04, decision D-01): the review trigger of
-- .planning/workstreams/pandapower-solver/phases/05-hourly-workflow-dry-run-and-live-soak/05-RETENTION-DECISION.md.
-- The result rows are kept without limit in that phase, so the owner reads how big the four result
-- tables have become and revisits the decision when the `all four result tables` total nears the
-- limit the owner named.
--
-- Who runs it: the Supabase project owner, in the Supabase SQL editor. It reads counts and sizes
-- only, never the contents of a row, and it changes nothing. This directory is never applied by the
-- Supabase CLI; it is not a migration.
--
-- One SELECT, six rows, in this order, with the columns
-- (table_name, row_count, total_bytes, total_size):
--   public.psse_run, public.psse_dispatched_capacity, public.psse_voltage_margin,
--   public.psse_contingency_result   one row per result table: its row count, its total size in
--                                    bytes (table, indexes and toast) and the same size in words
--   all four result tables           the sums of the four rows above
--   whole database                   the size of the current database; row_count is empty
--
-- Read the `all four result tables` row. A reading equal to the named limit counts as reached, so
-- the review is meant to happen while the reading is still below it.

select table_name, row_count, total_bytes, pg_size_pretty(total_bytes) as total_size
  from (
    select 1 as ord,
           'public.psse_run'::text as table_name,
           (select count(*) from public.psse_run) as row_count,
           pg_total_relation_size('public.psse_run'::regclass) as total_bytes
    union all
    select 2,
           'public.psse_dispatched_capacity',
           (select count(*) from public.psse_dispatched_capacity),
           pg_total_relation_size('public.psse_dispatched_capacity'::regclass)
    union all
    select 3,
           'public.psse_voltage_margin',
           (select count(*) from public.psse_voltage_margin),
           pg_total_relation_size('public.psse_voltage_margin'::regclass)
    union all
    select 4,
           'public.psse_contingency_result',
           (select count(*) from public.psse_contingency_result),
           pg_total_relation_size('public.psse_contingency_result'::regclass)
    union all
    select 5,
           'all four result tables',
           (select count(*) from public.psse_run)
               + (select count(*) from public.psse_dispatched_capacity)
               + (select count(*) from public.psse_voltage_margin)
               + (select count(*) from public.psse_contingency_result),
           pg_total_relation_size('public.psse_run'::regclass)
               + pg_total_relation_size('public.psse_dispatched_capacity'::regclass)
               + pg_total_relation_size('public.psse_voltage_margin'::regclass)
               + pg_total_relation_size('public.psse_contingency_result'::regclass)
    union all
    select 6,
           'whole database',
           null::bigint,
           pg_database_size(current_database())
  ) as sizes
 order by ord;
