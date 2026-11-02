-- supabase/ops/verify_exposure.sql
--
-- Production-pipeline Phase 6 (API-01, OD-6): the read-only exposure check.
--
-- One SELECT, no writes. It returns one row per check: (check_name, ok, detail). Every ok
-- must be true. The local test (backend/tests/expose_migration_test.py) runs this same file
-- on a throwaway Postgres; the owner runs it in the Supabase SQL editor in plans 06-09
-- (after the apply), 06-12 (after the soak) and 06-13 (the post-2026-10-30 permission
-- re-check). This directory is never applied by the Supabase CLI; it is not a migration.
--
-- What each check proves, in plain English:
--   latest_rating_is_security_invoker       the view obeys the table's access rules; it is not a back door
--   city_rating_rls_enabled                 row-level security is switched on for the ratings table
--   read_policy_city_rating_public_read     the one read rule exists, for the public roles, for SELECT only
--   no_write_policy_for_anon_or_authenticated  no rule lets the public roles insert, change or delete rows
--   anon_authenticated_grants_are_select_on_two_objects_only
--                                           the database's own permission list gives the public roles
--                                           read access to exactly the ratings table and the view, nothing else
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

with
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
     where not (privilege = 'SELECT' and relation in ('city_rating', 'latest_rating'))
),
select_grants as (
    select * from grants
     where privilege = 'SELECT' and relation in ('city_rating', 'latest_rating')
       and grantee in ('anon', 'authenticated')
),
-- Relations in public where anon or authenticated hold a write, trigger or column-level privilege
-- (reading is allowed only on the two published objects).
public_role_privileges as (
    select c.relname::text as relation, r.rolname
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     cross join (values ('anon'), ('authenticated')) as r(rolname)
     where n.nspname = 'public'
       and c.relkind in ('r', 'p', 'v', 'm', 'f')
       and (has_table_privilege(r.rolname, c.oid, 'insert, update, delete, truncate, references, trigger')
            or has_any_column_privilege(r.rolname, c.oid, 'insert, update, references')
            or (c.relname not in ('city_rating', 'latest_rating')
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
)
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
    select 'anon_authenticated_grants_are_select_on_two_objects_only',
           (select count(*) from extra_grants) = 0 and (select count(*) from select_grants) = 4,
           'extra grants: ' || coalesce((select string_agg(grantee || ' ' || privilege || ' on ' || relation, ', '
                                                           order by relation, grantee, privilege)
                                           from extra_grants), 'none') ||
               '; select grants on the two objects: ' || (select count(*) from select_grants)::text || ' of 4'
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
  ) as checks
 order by check_name;
