-- supabase/ops/verify_exposure.sql
--
-- Production-pipeline Phase 6 (API-01, OD-6) and Phase 8 (DAY-06, D-09, D-10, D-12): the read-only
-- exposure check.
--
-- One SELECT, no writes. It returns one row per check: (check_name, ok, detail). Every ok
-- must be true. The local test (backend/tests/expose_migration_test.py) runs this same file
-- on a throwaway Postgres; the owner runs it in the Supabase SQL editor in plans 06-09
-- (after the apply), 06-12 (after the soak) and 06-13 (the post-2026-10-30 permission
-- re-check), and again in Phase 8 after the day-ahead expose migration. This directory is never applied by the Supabase CLI; it is not a migration.
--
-- What each check proves, in plain English:
--   latest_rating_is_security_invoker       the view obeys the table's access rules; it is not a back door
--   city_rating_rls_enabled                 row-level security is switched on for the ratings table
--   read_policy_city_rating_public_read     the one read rule exists, for the public roles, for SELECT only
--   no_write_policy_for_anon_or_authenticated  no rule lets the public roles insert, change or delete rows
--   anon_authenticated_grants_are_select_on_published_objects_only
--                                           the database's own permission list gives the public roles
--                                           read access to exactly the six published objects (the ratings
--                                           table and view, the day-ahead table and its two views, the
--                                           grid-study view), 12 of 12 grants, nothing else
--   anon_authenticated_hold_no_write_or_column_privilege_in_public
--                                           asks the database's privilege functions directly, so column-level
--                                           grants and privileges inherited through role membership show up too
--   anon_can_select_city_rating             the public key can read the full rating history
--   anon_can_select_latest_rating           the public key can read the current rating per city
--   pipeline_run_not_readable_by_anon       the private run log cannot be read with the public key
--   anon_executable_public_functions_are_assert_fresh_only
--                                           the freshness check is the only function the public key may run
--   latest_rating_has_34_columns            the published column list has its 34 columns
--   latest_rating_ends_with_the_computed_columns  the last three are age_minutes, is_stale, is_provisional
--   latest_rating_columns_all_commented     every published column has its unit-first description
--   latest_rating_one_row_per_city          the view returns at most one row per city
--   latest_rating_has_the_four_cities       all four cities are present
--   is_stale_matches_age_minutes            the stale flag never contradicts the minutes shown (stale = more than 90)
--   is_provisional_matches_the_labels       the provisional flag is true exactly when a row's label says provisional
--   index_city_rating_city_valid_desc_present  the index that keeps "newest row per city" fast exists
-- Phase 8 (the day-ahead forecast and its two views):
--   day_ahead_forecast_rls_enabled          row-level security is switched on for the day-ahead table
--   read_policy_day_ahead_forecast_public_read  the one read rule exists on it, for the public roles, for SELECT only
--   day_ahead_upcoming_is_security_invoker  the upcoming-targets view obeys the table's access rules
--   day_ahead_status_is_security_invoker    the status view obeys the table's access rules
--   anon_can_select_day_ahead_forecast      the public key can read the day-ahead table, past targets included
--   anon_can_select_day_ahead_upcoming      the public key can read the upcoming targets
--   anon_can_select_day_ahead_status        the public key can read the per-city status and late flag
--   day_ahead_upcoming_matches_the_contract the upcoming view has its 26 columns, the last one lead_minutes
--   day_ahead_status_has_the_four_cities    the status view always lists all four cities
--   day_ahead_view_columns_all_commented    every column of both day-ahead views has its unit-first description
--   assert_fresh_has_one_signature          the alarm function exists once, so the alarm URL cannot meet an overload
-- The grid-study view (20261116200000_expose_latest_grid_study.sql):
--   latest_grid_study_runs_with_owner_rights  the view runs with its owner's rights, on purpose, so the
--                                           result tables can stay private (lint 0010 accepted for it)
--   anon_can_select_latest_grid_study       the public key can read the newest grid-study result per city
--   psse_tables_not_readable_by_public_roles  the four psse_* result tables stay private
--   latest_grid_study_matches_the_contract  the view has its 20 columns, ending with age_minutes, is_stale
--   latest_grid_study_columns_all_commented every published column has its unit-first description
--   latest_grid_study_one_row_per_city_per_solver  never two rows for the same city and solver
--   latest_grid_study_is_stale_matches_age_minutes  the stale flag never contradicts the minutes shown

with
-- The six objects the public roles may read: Phase 6 (two), Phase 8 (three) and the grid-study view.
published(relation) as (
    values ('city_rating'), ('latest_rating'), ('day_ahead_forecast'), ('day_ahead_upcoming'), ('day_ahead_status'),
           ('latest_grid_study')
),
-- Every privilege a role other than the table owner holds on a public relation, for anon,
-- authenticated and PUBLIC (a PUBLIC grant reaches anon as well).
grants as (
    select c.relname::text as relation,
           case when a.grantee = 0 then 'public' else a.grantee::regrole::text end as grantee,
           a.privilege_type::text as privilege
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     cross join lateral aclexplode(c.relacl) as a
     where n.nspname = 'public'
       and c.relkind in ('r', 'p', 'v', 'm', 'f', 'S')
       and (a.grantee = 0 or a.grantee::regrole::text in ('anon', 'authenticated'))
),
extra_grants as (
    select * from grants
     where not (privilege = 'SELECT' and relation in (select relation from published))
),
select_grants as (
    select * from grants
     where privilege = 'SELECT' and relation in (select relation from published)
       and grantee in ('anon', 'authenticated')
),
-- Relations in public where anon or authenticated hold a write, trigger or column-level privilege
-- (reading is allowed only on the six published objects).
public_role_privileges as (
    select c.relname::text as relation, r.rolname
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     cross join (values ('anon'), ('authenticated')) as r(rolname)
     where n.nspname = 'public'
       and c.relkind in ('r', 'p', 'v', 'm', 'f')
       and (has_table_privilege(r.rolname, c.oid, 'insert, update, delete, truncate, references, trigger')
            or has_any_column_privilege(r.rolname, c.oid, 'insert, update, references')
            or (c.relname not in (select relation from published)
                and has_any_column_privilege(r.rolname, c.oid, 'select')))
),
other_functions as (
    select p.proname::text as function_name
      from pg_proc p
     where p.pronamespace = 'public'::regnamespace
       and p.proname <> 'assert_fresh'
       and has_function_privilege('anon', p.oid, 'execute')
       and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
),
view_columns as (
    select a.attnum, a.attname::text as column_name, col_description(a.attrelid, a.attnum) as column_comment
      from pg_attribute a
     where a.attrelid = to_regclass('public.latest_rating')
       and a.attnum > 0
       and not a.attisdropped
),
-- The columns of the two Phase 8 views.
day_ahead_view_columns as (
    select c.relname::text as view_name, a.attnum, a.attname::text as column_name,
           col_description(a.attrelid, a.attnum) as column_comment
      from pg_attribute a
      join pg_class c on c.oid = a.attrelid
     where a.attrelid in (to_regclass('public.day_ahead_upcoming'), to_regclass('public.day_ahead_status'))
       and a.attnum > 0
       and not a.attisdropped
)
-- BEGIN grid_study_ctes (a checker run on a database without the grid-study view strips this region)
-- The columns of the grid-study view (the leading comma belongs to this region).
, grid_view_columns as (
    select a.attnum, a.attname::text as column_name, col_description(a.attrelid, a.attnum) as column_comment
      from pg_attribute a
     where a.attrelid = to_regclass('public.latest_grid_study')
       and a.attnum > 0
       and not a.attisdropped
),
psse_tables(relation) as (
    values ('psse_run'), ('psse_dispatched_capacity'), ('psse_voltage_margin'), ('psse_contingency_result')
),
psse_readable as (
    select t.relation, r.rolname
      from psse_tables t
     cross join (values ('anon'), ('authenticated')) as r(rolname)
     where to_regclass('public.' || t.relation) is not null
       and has_table_privilege(r.rolname, to_regclass('public.' || t.relation), 'select')
)
-- END grid_study_ctes
select check_name, ok, detail
  from (
    select 'latest_rating_is_security_invoker'::text as check_name,
           coalesce((select coalesce(c.reloptions, '{}') @> array['security_invoker=true']
                       from pg_class c where c.oid = to_regclass('public.latest_rating')), false) as ok,
           'reloptions=' || coalesce((select c.reloptions::text
                                        from pg_class c where c.oid = to_regclass('public.latest_rating')), 'view missing') as detail
    union all
    select 'city_rating_rls_enabled',
           coalesce((select c.relrowsecurity from pg_class c where c.oid = to_regclass('public.city_rating')), false),
           'relrowsecurity=' || coalesce((select c.relrowsecurity::text
                                            from pg_class c where c.oid = to_regclass('public.city_rating')), 'table missing')
    union all
    select 'read_policy_city_rating_public_read',
           exists (select 1 from pg_policies
                    where schemaname = 'public' and tablename = 'city_rating'
                      and policyname = 'city_rating_public_read' and cmd = 'SELECT'
                      and roles::text[] @> array['anon', 'authenticated']),
           'policies on city_rating: ' || coalesce((select string_agg(policyname || ' ' || cmd, ', ' order by policyname)
                                                     from pg_policies
                                                    where schemaname = 'public' and tablename = 'city_rating'), 'none')
    union all
    select 'no_write_policy_for_anon_or_authenticated',
           not exists (select 1 from pg_policies
                        where schemaname = 'public'
                          and cmd in ('INSERT', 'UPDATE', 'DELETE', 'ALL')
                          and roles::text[] && array['anon', 'authenticated', 'public']),
           'write policies reaching the public roles: ' ||
               coalesce((select string_agg(tablename || '.' || policyname, ', ' order by tablename, policyname)
                           from pg_policies
                          where schemaname = 'public'
                            and cmd in ('INSERT', 'UPDATE', 'DELETE', 'ALL')
                            and roles::text[] && array['anon', 'authenticated', 'public']), 'none')
    union all
    select 'anon_authenticated_grants_are_select_on_published_objects_only',
           (select count(*) from extra_grants) = 0 and (select count(*) from select_grants) = 12,
           'extra grants: ' || coalesce((select string_agg(grantee || ' ' || privilege || ' on ' || relation, ', '
                                                           order by relation, grantee, privilege)
                                           from extra_grants), 'none') ||
               '; select grants on the six published objects: ' || (select count(*) from select_grants)::text || ' of 12'
    union all
    -- The grants CTE above reads only pg_class.relacl, which never lists column-level grants
    -- (pg_attribute.attacl) or privileges inherited through role membership. The has_*_privilege
    -- functions see both.
    select 'anon_authenticated_hold_no_write_or_column_privilege_in_public',
           not exists (select 1 from public_role_privileges),
           'write, trigger or column-level privileges held by anon or authenticated (directly or inherited): ' ||
               coalesce((select string_agg(relation || ' ' || rolname, ', ' order by relation, rolname)
                           from public_role_privileges), 'none')
    union all
    select 'anon_can_select_city_rating',
           coalesce(has_table_privilege('anon', 'public.city_rating', 'select'), false),
           'has_table_privilege(anon, city_rating, select)'
    union all
    select 'anon_can_select_latest_rating',
           coalesce(has_table_privilege('anon', 'public.latest_rating', 'select'), false),
           'has_table_privilege(anon, latest_rating, select)'
    union all
    select 'pipeline_run_not_readable_by_anon',
           not has_table_privilege('anon', 'public.pipeline_run', 'select')
               and not has_table_privilege('authenticated', 'public.pipeline_run', 'select'),
           'anon select=' || has_table_privilege('anon', 'public.pipeline_run', 'select')::text ||
               ', authenticated select=' || has_table_privilege('authenticated', 'public.pipeline_run', 'select')::text
    union all
    select 'anon_executable_public_functions_are_assert_fresh_only',
           (select count(*) from other_functions) = 0
               and coalesce(has_function_privilege('anon', to_regprocedure('public.assert_fresh(integer)'), 'execute'), false),
           'other functions anon may execute: ' || coalesce((select string_agg(function_name, ', ' order by function_name)
                                                              from other_functions), 'none')
    union all
    select 'latest_rating_has_34_columns',
           (select count(*) from view_columns) = 34,
           'columns=' || (select count(*) from view_columns)::text
    union all
    select 'latest_rating_ends_with_the_computed_columns',
           coalesce((select array_agg(column_name order by attnum) from view_columns where attnum between 32 and 34)
                    = array['age_minutes', 'is_stale', 'is_provisional'], false),
           'columns 32-34: ' || coalesce((select string_agg(column_name, ', ' order by attnum)
                                            from view_columns where attnum between 32 and 34), 'none')
    union all
    select 'latest_rating_columns_all_commented',
           (select count(*) from view_columns) > 0
               and (select count(*) from view_columns where column_comment is null or btrim(column_comment) = '') = 0,
           'columns without a comment: ' || coalesce((select string_agg(column_name, ', ' order by attnum)
                                                       from view_columns
                                                      where column_comment is null or btrim(column_comment) = ''), 'none')
    union all
    select 'latest_rating_one_row_per_city',
           (select count(*) = count(distinct city) and count(*) > 0 from public.latest_rating),
           'rows=' || (select count(*) from public.latest_rating)::text
    union all
    select 'latest_rating_has_the_four_cities',
           coalesce((select array_agg(city order by city) from public.latest_rating)
                    = array['AUSTIN', 'CORPUS_CHRISTI', 'EL_PASO', 'MIDLAND'], false),
           'cities: ' || coalesce((select string_agg(city, ', ' order by city) from public.latest_rating), 'none')
    union all
    select 'is_stale_matches_age_minutes',
           coalesce((select bool_and(is_stale = (age_minutes > 90)) from public.latest_rating), false),
           'rows checked=' || (select count(*) from public.latest_rating)::text
    union all
    select 'is_provisional_matches_the_labels',
           coalesce((select bool_and(is_provisional = (position('provisional' in lower(rating_basis)) > 0
                                                       or position('provisional' in lower(config_version)) > 0))
                       from public.latest_rating), false),
           'rows checked=' || (select count(*) from public.latest_rating)::text
    union all
    select 'index_city_rating_city_valid_desc_present',
           exists (select 1 from pg_indexes
                    where schemaname = 'public' and tablename = 'city_rating'
                      and indexname = 'city_rating_city_valid_desc_idx'),
           'index city_rating_city_valid_desc_idx on city_rating'
    union all
    select 'day_ahead_forecast_rls_enabled',
           coalesce((select c.relrowsecurity from pg_class c where c.oid = to_regclass('public.day_ahead_forecast')), false),
           'relrowsecurity=' || coalesce((select c.relrowsecurity::text
                                            from pg_class c where c.oid = to_regclass('public.day_ahead_forecast')), 'table missing')
    union all
    select 'read_policy_day_ahead_forecast_public_read',
           exists (select 1 from pg_policies
                    where schemaname = 'public' and tablename = 'day_ahead_forecast'
                      and policyname = 'day_ahead_forecast_public_read' and cmd = 'SELECT'
                      and roles::text[] @> array['anon', 'authenticated']),
           'policies on day_ahead_forecast: ' || coalesce((select string_agg(policyname || ' ' || cmd, ', ' order by policyname)
                                                            from pg_policies
                                                           where schemaname = 'public' and tablename = 'day_ahead_forecast'), 'none')
    union all
    select 'day_ahead_upcoming_is_security_invoker',
           coalesce((select coalesce(c.reloptions, '{}') @> array['security_invoker=true']
                       from pg_class c where c.oid = to_regclass('public.day_ahead_upcoming')), false),
           'reloptions=' || coalesce((select c.reloptions::text
                                        from pg_class c where c.oid = to_regclass('public.day_ahead_upcoming')), 'view missing')
    union all
    select 'day_ahead_status_is_security_invoker',
           coalesce((select coalesce(c.reloptions, '{}') @> array['security_invoker=true']
                       from pg_class c where c.oid = to_regclass('public.day_ahead_status')), false),
           'reloptions=' || coalesce((select c.reloptions::text
                                        from pg_class c where c.oid = to_regclass('public.day_ahead_status')), 'view missing')
    union all
    select 'anon_can_select_day_ahead_forecast',
           coalesce(has_table_privilege('anon', 'public.day_ahead_forecast', 'select'), false),
           'has_table_privilege(anon, day_ahead_forecast, select)'
    union all
    select 'anon_can_select_day_ahead_upcoming',
           coalesce(has_table_privilege('anon', 'public.day_ahead_upcoming', 'select'), false),
           'has_table_privilege(anon, day_ahead_upcoming, select)'
    union all
    select 'anon_can_select_day_ahead_status',
           coalesce(has_table_privilege('anon', 'public.day_ahead_status', 'select'), false),
           'has_table_privilege(anon, day_ahead_status, select)'
    union all
    select 'day_ahead_upcoming_matches_the_contract',
           (select count(*) from day_ahead_view_columns where view_name = 'day_ahead_upcoming') = 26
               and coalesce((select column_name from day_ahead_view_columns
                              where view_name = 'day_ahead_upcoming' and attnum = 26), '') = 'lead_minutes',
           'columns=' || (select count(*) from day_ahead_view_columns where view_name = 'day_ahead_upcoming')::text ||
               ', column 26=' || coalesce((select column_name from day_ahead_view_columns
                                            where view_name = 'day_ahead_upcoming' and attnum = 26), 'none')
    union all
    select 'day_ahead_status_has_the_four_cities',
           coalesce((select array_agg(city order by city) from public.day_ahead_status)
                    = array['AUSTIN', 'CORPUS_CHRISTI', 'EL_PASO', 'MIDLAND'], false),
           'cities: ' || coalesce((select string_agg(city, ', ' order by city) from public.day_ahead_status), 'none')
    union all
    select 'day_ahead_view_columns_all_commented',
           (select count(*) from day_ahead_view_columns) > 0
               and (select count(*) from day_ahead_view_columns
                     where column_comment is null or btrim(column_comment) = '') = 0,
           'columns without a comment: ' || coalesce((select string_agg(view_name || '.' || column_name, ', '
                                                                         order by view_name, attnum)
                                                        from day_ahead_view_columns
                                                       where column_comment is null or btrim(column_comment) = ''), 'none')
    union all
    select 'assert_fresh_has_one_signature',
           (select count(*) from pg_proc p
             where p.pronamespace = 'public'::regnamespace and p.proname = 'assert_fresh') = 1,
           'functions named assert_fresh in public: ' ||
               (select count(*) from pg_proc p
                 where p.pronamespace = 'public'::regnamespace and p.proname = 'assert_fresh')::text
    -- BEGIN grid_study_checks (stripped together with grid_study_ctes)
    union all
    select 'latest_grid_study_runs_with_owner_rights',
           coalesce((select c.relkind = 'v' and not (coalesce(c.reloptions, '{}') @> array['security_invoker=true'])
                       from pg_class c where c.oid = to_regclass('public.latest_grid_study')), false),
           'reloptions=' || coalesce((select coalesce(c.reloptions::text, '{}')
                                        from pg_class c where c.oid = to_regclass('public.latest_grid_study')), 'view missing')
    union all
    select 'anon_can_select_latest_grid_study',
           coalesce(has_table_privilege('anon', to_regclass('public.latest_grid_study'), 'select'), false),
           'has_table_privilege(anon, latest_grid_study, select)'
    union all
    select 'psse_tables_not_readable_by_public_roles',
           not exists (select 1 from psse_readable),
           'readable: ' || coalesce((select string_agg(relation || ' ' || rolname, ', ' order by relation, rolname)
                                       from psse_readable), 'none')
    union all
    select 'latest_grid_study_matches_the_contract',
           (select count(*) from grid_view_columns) = 20
               and coalesce((select array_agg(column_name order by attnum) from grid_view_columns where attnum between 19 and 20)
                            = array['age_minutes', 'is_stale'], false),
           'columns=' || (select count(*) from grid_view_columns)::text ||
               ', columns 19-20: ' || coalesce((select string_agg(column_name, ', ' order by attnum)
                                                  from grid_view_columns where attnum between 19 and 20), 'none')
    union all
    select 'latest_grid_study_columns_all_commented',
           (select count(*) from grid_view_columns) > 0
               and (select count(*) from grid_view_columns where column_comment is null or btrim(column_comment) = '') = 0,
           'columns without a comment: ' || coalesce((select string_agg(column_name, ', ' order by attnum)
                                                       from grid_view_columns
                                                      where column_comment is null or btrim(column_comment) = ''), 'none')
    union all
    select 'latest_grid_study_one_row_per_city_per_solver',
           coalesce((select count(*) = count(distinct (solver, city)) from public.latest_grid_study), false),
           'rows=' || coalesce((select count(*) from public.latest_grid_study)::text, 'view missing')
    union all
    select 'latest_grid_study_is_stale_matches_age_minutes',
           coalesce((select coalesce(bool_and(is_stale = (age_minutes > 90)), true) from public.latest_grid_study), false),
           'rows checked=' || coalesce((select count(*) from public.latest_grid_study)::text, 'view missing')
    -- END grid_study_checks
  ) as checks
 order by check_name;
