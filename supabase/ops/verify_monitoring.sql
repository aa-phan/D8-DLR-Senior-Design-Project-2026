-- supabase/ops/verify_monitoring.sql
--
-- Production-pipeline Phase 6 (E2E-02, T-06-16): the read-only check of the soak log's privileges.
--
-- One SELECT, no writes. It returns one row per check: (check_name, ok, detail). Every ok
-- must be true. The local test (backend/tests/soak_log_migration_test.py) runs this same file on a
-- throwaway Postgres; the owner runs it in the Supabase SQL editor after the soak migration is
-- applied (plan 06-09) and at soak end (06-12). This directory is never applied by the Supabase
-- CLI; it is not a migration.
--
-- What each check proves, in plain English:
--   ops_schema_not_usable_by_anon_or_authenticated
--                                   the public key cannot even look inside the ops schema
--   freshness_log_not_readable_by_anon_or_authenticated
--                                   the public key cannot read the soak log (false too if the table is missing)
--   log_freshness_not_executable_by_anon_or_authenticated
--                                   the public key cannot run the logging function (false too if it is missing)
--   freshness_log_present           the soak log table exists
--   log_freshness_present           the logging function exists
--   dlr_writer_can_read_freshness_log
--                                   the CI writer role can read the log and not change it (true, with
--                                   "role absent", when the project has no such role)
--   assert_fresh_executable_by_anon the public freshness check the permanent alarm calls is still callable

select check_name, ok, detail
  from (
    select 'ops_schema_not_usable_by_anon_or_authenticated'::text as check_name,
           exists (select 1 from pg_namespace where nspname = 'ops')
               and not has_schema_privilege('anon', 'ops', 'usage')
               and not has_schema_privilege('authenticated', 'ops', 'usage')
               and not has_schema_privilege('anon', 'ops', 'create')
               and not has_schema_privilege('authenticated', 'ops', 'create') as ok,
           case when not exists (select 1 from pg_namespace where nspname = 'ops') then 'schema missing'
                else 'ops schema acl=' || coalesce((select nspacl::text from pg_namespace where nspname = 'ops'),
                                                   'default (owner only)')
           end as detail
    union all
    select 'freshness_log_not_readable_by_anon_or_authenticated',
           to_regclass('ops.freshness_log') is not null
               and not has_table_privilege('anon', 'ops.freshness_log', 'select')
               and not has_table_privilege('authenticated', 'ops.freshness_log', 'select')
               and not has_table_privilege('anon', 'ops.freshness_log', 'insert')
               and not has_table_privilege('authenticated', 'ops.freshness_log', 'insert'),
           'table acl=' || coalesce((select c.relacl::text from pg_class c where c.oid = to_regclass('ops.freshness_log')),
                                    case when to_regclass('ops.freshness_log') is null then 'table missing'
                                         else 'default (owner only)' end)
    union all
    select 'log_freshness_not_executable_by_anon_or_authenticated',
           to_regprocedure('ops.log_freshness()') is not null
               and not has_function_privilege('anon', to_regprocedure('ops.log_freshness()'), 'execute')
               and not has_function_privilege('authenticated', to_regprocedure('ops.log_freshness()'), 'execute'),
           'function acl=' || coalesce((select p.proacl::text from pg_proc p where p.oid = to_regprocedure('ops.log_freshness()')),
                                       case when to_regprocedure('ops.log_freshness()') is null then 'function missing'
                                            else 'default (PUBLIC may execute)' end)
    union all
    select 'freshness_log_present',
           to_regclass('ops.freshness_log') is not null,
           'to_regclass(ops.freshness_log)=' || coalesce(to_regclass('ops.freshness_log')::text, 'missing')
    union all
    select 'log_freshness_present',
           to_regprocedure('ops.log_freshness()') is not null,
           'to_regprocedure(ops.log_freshness())=' || coalesce(to_regprocedure('ops.log_freshness()')::text, 'missing')
    union all
    select 'dlr_writer_can_read_freshness_log',
           case when not exists (select 1 from pg_roles where rolname = 'dlr_writer') then true
                else to_regclass('ops.freshness_log') is not null
                     and has_schema_privilege('dlr_writer', 'ops', 'usage')
                     and has_table_privilege('dlr_writer', 'ops.freshness_log', 'select')
                     and not has_table_privilege('dlr_writer', 'ops.freshness_log', 'insert, update, delete, truncate')
           end,
           case when not exists (select 1 from pg_roles where rolname = 'dlr_writer') then 'role absent'
                when to_regclass('ops.freshness_log') is null then 'table missing'
                else 'schema usage=' || has_schema_privilege('dlr_writer', 'ops', 'usage')::text ||
                     ', select=' || has_table_privilege('dlr_writer', 'ops.freshness_log', 'select')::text ||
                     ', write=' || has_table_privilege('dlr_writer', 'ops.freshness_log', 'insert, update, delete, truncate')::text
           end
    union all
    select 'assert_fresh_executable_by_anon',
           coalesce(has_function_privilege('anon', to_regprocedure('public.assert_fresh(integer)'), 'execute'), false),
           'has_function_privilege(anon, public.assert_fresh(integer), execute)'
  ) as checks
 order by check_name;
