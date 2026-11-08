-- supabase/ops/verify_day_ahead_store.sql
--
-- Production-pipeline Phase 8 (DAY-05, D-09): the read-only check of the day-ahead write side.
--
-- One SELECT, no writes. It returns one row per check: (check_name, ok, detail). Every ok must be
-- true. The local test (backend/tests/day_ahead_migration_test.py) runs this same file on a
-- throwaway Postgres migrated through the write-side file. The owner runs it in the Supabase SQL
-- editor once, right after applying supabase/migrations/20261108120000_day_ahead_forecast_store.sql
-- (plan 08-07). This directory is never applied by the Supabase CLI; it is not a migration.
--
-- What each check proves, in plain English:
--   day_ahead_forecast_exists                    the day-ahead table is there
--   day_ahead_forecast_rls_enabled               row-level security is switched on for it
--   day_ahead_forecast_has_25_columns            it has its 25 columns, no more and no fewer
--   day_ahead_forecast_columns_all_commented     every column has its unit-first description
--   day_ahead_forecast_primary_key_city_valid_time  one row per city and target hour is enforced by the key
--   day_ahead_forecast_not_readable_by_anon_or_authenticated
--                                                the public keys cannot read the table yet (the separate
--                                                expose step grants that later, after the first rows are checked)
--   dlr_writer_can_select_and_insert_day_ahead_forecast
--                                                the runner's database role can read and add rows
--   dlr_writer_cannot_update_delete_or_truncate_day_ahead_forecast
--                                                the runner's role cannot change or remove a row it wrote,
--                                                so an issued value is never rewritten
--   pipeline_run_has_day_ahead_jsonb             the private run log has its day_ahead column, as json
--   pipeline_run_not_readable_by_anon            the private run log still cannot be read with the public keys
--
-- Each privilege check asks the database's own privilege functions, so column-level grants and
-- privileges inherited through role membership show up too. A missing table or role turns its
-- checks false instead of raising an error.

with
day_ahead as (
    select to_regclass('public.day_ahead_forecast') as oid
),
writer as (
    select exists (select 1 from pg_roles where rolname = 'dlr_writer') as present
),
table_columns as (
    select a.attnum, a.attname::text as column_name, col_description(a.attrelid, a.attnum) as column_comment
      from pg_attribute a
     where a.attrelid = to_regclass('public.day_ahead_forecast')
       and a.attnum > 0
       and not a.attisdropped
),
primary_key as (
    select array_agg(a.attname::text order by k.ord) as columns
      from pg_constraint c
      cross join lateral unnest(c.conkey) with ordinality as k(attnum, ord)
      join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k.attnum
     where c.conrelid = to_regclass('public.day_ahead_forecast')
       and c.contype = 'p'
)
select check_name, ok, detail
  from (
    select 'day_ahead_forecast_exists'::text as check_name,
           (select oid is not null from day_ahead) as ok,
           'to_regclass(public.day_ahead_forecast)=' || coalesce((select oid::text from day_ahead), 'table missing') as detail
    union all
    select 'day_ahead_forecast_rls_enabled',
           coalesce((select c.relrowsecurity from pg_class c where c.oid = (select oid from day_ahead)), false),
           'relrowsecurity=' || coalesce((select c.relrowsecurity::text
                                            from pg_class c where c.oid = (select oid from day_ahead)), 'table missing')
    union all
    select 'day_ahead_forecast_has_25_columns',
           (select count(*) from table_columns) = 25,
           'columns=' || (select count(*) from table_columns)::text
    union all
    select 'day_ahead_forecast_columns_all_commented',
           (select count(*) from table_columns) > 0
               and (select count(*) from table_columns where column_comment is null or btrim(column_comment) = '') = 0,
           'columns without a comment: ' || coalesce((select string_agg(column_name, ', ' order by attnum)
                                                       from table_columns
                                                      where column_comment is null or btrim(column_comment) = ''), 'none')
    union all
    select 'day_ahead_forecast_primary_key_city_valid_time',
           coalesce((select columns = array['city', 'valid_time'] from primary_key), false),
           'primary key columns: ' || coalesce((select array_to_string(columns, ', ') from primary_key), 'none')
    union all
    select 'day_ahead_forecast_not_readable_by_anon_or_authenticated',
           (select oid is not null from day_ahead)
               and case when (select oid is not null from day_ahead)
                        then not (has_table_privilege('anon', (select oid from day_ahead), 'select')
                                  or has_table_privilege('authenticated', (select oid from day_ahead), 'select')
                                  or has_any_column_privilege('anon', (select oid from day_ahead), 'select')
                                  or has_any_column_privilege('authenticated', (select oid from day_ahead), 'select'))
                        else false end,
           case when (select oid is not null from day_ahead)
                then 'anon select=' || has_table_privilege('anon', (select oid from day_ahead), 'select')::text ||
                     ', authenticated select=' || has_table_privilege('authenticated', (select oid from day_ahead), 'select')::text
                else 'table missing' end
    union all
    select 'dlr_writer_can_select_and_insert_day_ahead_forecast',
           case when (select oid is not null from day_ahead) and (select present from writer)
                then has_table_privilege('dlr_writer', (select oid from day_ahead), 'select')
                     and has_table_privilege('dlr_writer', (select oid from day_ahead), 'insert')
                else false end,
           case when (select oid is not null from day_ahead) and (select present from writer)
                then 'dlr_writer select=' || has_table_privilege('dlr_writer', (select oid from day_ahead), 'select')::text ||
                     ', insert=' || has_table_privilege('dlr_writer', (select oid from day_ahead), 'insert')::text
                else 'table or role dlr_writer missing' end
    union all
    select 'dlr_writer_cannot_update_delete_or_truncate_day_ahead_forecast',
           case when (select oid is not null from day_ahead) and (select present from writer)
                then not (has_table_privilege('dlr_writer', (select oid from day_ahead), 'update, delete, truncate')
                          or has_any_column_privilege('dlr_writer', (select oid from day_ahead), 'update'))
                else false end,
           case when (select oid is not null from day_ahead) and (select present from writer)
                then 'dlr_writer update=' || has_table_privilege('dlr_writer', (select oid from day_ahead), 'update')::text ||
                     ', delete=' || has_table_privilege('dlr_writer', (select oid from day_ahead), 'delete')::text ||
                     ', truncate=' || has_table_privilege('dlr_writer', (select oid from day_ahead), 'truncate')::text
                else 'table or role dlr_writer missing' end
    union all
    select 'pipeline_run_has_day_ahead_jsonb',
           exists (select 1 from information_schema.columns
                    where table_schema = 'public' and table_name = 'pipeline_run'
                      and column_name = 'day_ahead' and data_type = 'jsonb'),
           'pipeline_run.day_ahead data_type=' || coalesce((select data_type::text from information_schema.columns
                                                              where table_schema = 'public' and table_name = 'pipeline_run'
                                                                and column_name = 'day_ahead'), 'column missing')
    union all
    select 'pipeline_run_not_readable_by_anon',
           to_regclass('public.pipeline_run') is not null
               and case when to_regclass('public.pipeline_run') is not null
                        then not (has_table_privilege('anon', to_regclass('public.pipeline_run'), 'select')
                                  or has_table_privilege('authenticated', to_regclass('public.pipeline_run'), 'select'))
                        else false end,
           case when to_regclass('public.pipeline_run') is not null
                then 'anon select=' || has_table_privilege('anon', to_regclass('public.pipeline_run'), 'select')::text ||
                     ', authenticated select=' || has_table_privilege('authenticated', to_regclass('public.pipeline_run'), 'select')::text
                else 'table missing' end
  ) as checks
 order by check_name;
