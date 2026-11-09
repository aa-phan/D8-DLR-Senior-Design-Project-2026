-- supabase/ops/verify_psse_results.sql
--
-- pss-e-integration follow-on (DBX-01, DBX-02): the read-only check of the PSS/E result tables and
-- of the PSS/E job's database role, dlr_psse_writer.
--
-- One SELECT, no writes. It returns one row per check, in the order listed below:
-- (check_name, ok, detail). Every ok must be true. The local test
-- (backend/tests/psse_results_migration_test.py) runs this same file on a throwaway Postgres with
-- every migration applied. The owner runs it against the live project right after applying
-- supabase/migrations/*_psse_results.sql. This directory is never applied by the Supabase CLI; it
-- is not a migration.
--
-- What each check proves, in plain English:
--   psse_tables_exist
--       the four result tables (psse_run, psse_dispatched_capacity, psse_voltage_margin,
--       psse_contingency_result) are there in the public schema
--   psse_tables_rls_enabled
--       row-level security is switched on for all four
--   anon_authenticated_hold_nothing_on_psse_tables
--       the public keys (anon, authenticated) and PUBLIC hold no privilege on the four tables: no
--       entry in the permission list, and the database's own privilege functions say no for every
--       table and column privilege, so privileges inherited through role membership show up too
--   dlr_psse_writer_holds_exactly_insert_select_on_psse_tables
--       the PSS/E role holds INSERT and SELECT on each of the four tables (8 of 8 entries) and
--       nothing else: no UPDATE, DELETE, TRUNCATE, REFERENCES or TRIGGER, so a stored run is never
--       rewritten
--   dlr_psse_writer_holds_nothing_on_other_relations
--       the PSS/E role holds no privilege on any other table or view in public or ops
--       (city_rating, pipeline_run, latest_rating, the day-ahead objects, ops.freshness_log), so
--       its credential can never change the ratings
--   dlr_psse_writer_policies_are_insert_and_select_only
--       the four tables carry exactly 8 row-level security policies: a permissive insert policy and
--       a permissive select policy per table, both for dlr_psse_writer only
--   dlr_psse_writer_role_attributes
--       the PSS/E role can log in and is not a superuser, cannot create roles or databases, cannot
--       bypass row-level security and cannot replicate (read from pg_roles, not pg_authid)
--
-- A missing table or role turns its checks false instead of raising an error.

with
psse_tables(name) as (
    values ('psse_run'), ('psse_dispatched_capacity'), ('psse_voltage_margin'), ('psse_contingency_result')
),
-- The four tables as they exist now (oid and RLS flag are null when a table is missing).
psse as (
    select t.name, c.oid, c.relrowsecurity, c.relacl
      from psse_tables t
      left join pg_class c
        on c.relname = t.name
       and c.relnamespace = 'public'::regnamespace
       and c.relkind = 'r'
),
-- Roles by oid, so a missing role gives null instead of an error in the privilege functions.
roles as (
    select (select r.oid from pg_roles r where r.rolname = 'dlr_psse_writer') as writer,
           (select r.oid from pg_roles r where r.rolname = 'anon') as anon,
           (select r.oid from pg_roles r where r.rolname = 'authenticated') as authenticated
),
-- Permission-list entries on the four tables.
psse_acl as (
    select p.name, a.grantee, a.privilege_type::text as privilege
      from psse p
     cross join lateral aclexplode(p.relacl) as a
     where p.oid is not null
),
-- Entries held by anon, authenticated or PUBLIC (grantee 0).
public_acl as (
    select a.* from psse_acl a, roles r
     where a.grantee = 0 or a.grantee in (r.anon, r.authenticated)
),
-- Privilege-function answers for anon and authenticated on the four tables (true means held).
public_privs as (
    select p.name, g.role_name, v.privilege, has_table_privilege(g.role_oid, p.oid, v.privilege) as held
      from psse p
     cross join roles r
     cross join lateral (values ('anon', r.anon), ('authenticated', r.authenticated)) as g(role_name, role_oid)
     cross join (values ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'), ('TRUNCATE'), ('REFERENCES'), ('TRIGGER'))
          as v(privilege)
     where p.oid is not null
),
public_column_privs as (
    select p.name, g.role_name, v.privilege, has_any_column_privilege(g.role_oid, p.oid, v.privilege) as held
      from psse p
     cross join roles r
     cross join lateral (values ('anon', r.anon), ('authenticated', r.authenticated)) as g(role_name, role_oid)
     cross join (values ('SELECT'), ('INSERT'), ('UPDATE'), ('REFERENCES')) as v(privilege)
     where p.oid is not null
),
-- Entries held by the PSS/E role on the four tables.
writer_acl as (
    select a.* from psse_acl a, roles r where a.grantee = r.writer
),
writer_extra_privs as (
    select p.name, v.privilege, has_table_privilege(r.writer, p.oid, v.privilege) as held
      from psse p
     cross join roles r
     cross join (values ('UPDATE'), ('DELETE'), ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')) as v(privilege)
     where p.oid is not null
),
writer_update_column as (
    select p.name, has_any_column_privilege(r.writer, p.oid, 'UPDATE') as held
      from psse p cross join roles r where p.oid is not null
),
-- Every other table, view, materialized view or foreign table in public or ops.
other_relations as (
    select n.nspname::text || '.' || c.relname::text as relation, c.oid
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname in ('public', 'ops')
       and c.relkind in ('r', 'p', 'v', 'm', 'f')
       and not (n.nspname = 'public' and c.relname in (select name from psse_tables))
),
other_offenders as (
    select o.relation
      from other_relations o
      cross join roles r
     where exists (
               select 1
                 from (values ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'), ('TRUNCATE'), ('REFERENCES'), ('TRIGGER'))
                      as v(privilege)
                where has_table_privilege(r.writer, o.oid, v.privilege))
        or exists (
               select 1
                 from (values ('SELECT'), ('INSERT'), ('UPDATE'), ('REFERENCES')) as v(privilege)
                where has_any_column_privilege(r.writer, o.oid, v.privilege))
),
psse_policies as (
    select tablename::text as tablename, policyname::text as policyname, cmd::text as cmd,
           permissive::text as permissive, roles::text as roles
      from pg_policies
     where schemaname = 'public'
       and tablename in (select name from psse_tables)
),
well_formed_policies as (
    select * from psse_policies
     where permissive = 'PERMISSIVE'
       and roles = '{dlr_psse_writer}'
       and ((policyname = 'dlr_psse_writer_insert' and cmd = 'INSERT')
            or (policyname = 'dlr_psse_writer_select' and cmd = 'SELECT'))
),
writer_role as (
    select * from pg_roles where rolname = 'dlr_psse_writer'
)
select check_name, ok, detail
  from (
    select 1 as ord,
           'psse_tables_exist'::text as check_name,
           (select count(*) from psse where oid is not null) = 4 as ok,
           (select count(*) from psse where oid is not null)::text || ' of 4 tables exist, missing: ' ||
               coalesce((select string_agg(name, ', ' order by name) from psse where oid is null), 'none') as detail
    union all
    select 2,
           'psse_tables_rls_enabled',
           (select count(*) from psse where relrowsecurity is true) = 4,
           (select count(*) from psse where relrowsecurity is true)::text || ' of 4 tables have row-level security on'
    union all
    select 3,
           'anon_authenticated_hold_nothing_on_psse_tables',
           (select count(*) from psse where oid is not null) = 4
               and (select count(*) from public_acl) = 0
               and (select count(*) from public_privs where held is true) = 0
               and (select count(*) from public_column_privs where held is true) = 0,
           'permission-list entries: ' || (select count(*) from public_acl)::text ||
               ', table privileges held: ' || (select count(*) from public_privs where held is true)::text ||
               ', column privileges held: ' || (select count(*) from public_column_privs where held is true)::text
    union all
    select 4,
           'dlr_psse_writer_holds_exactly_insert_select_on_psse_tables',
           (select count(*) from psse where oid is not null) = 4
               and (select count(*) from writer_acl) = 8
               and (select count(*) from writer_acl where privilege in ('INSERT', 'SELECT')) = 8
               and (select count(*) from writer_extra_privs where held is true) = 0
               and (select count(*) from writer_update_column where held is true) = 0,
           (select count(*) from writer_acl where privilege in ('INSERT', 'SELECT'))::text || ' of 8 INSERT/SELECT entries, ' ||
               (select count(*) from writer_acl)::text || ' entries in all, other privileges held: ' ||
               (select count(*) from writer_extra_privs where held is true)::text ||
               ', column UPDATE held on ' || (select count(*) from writer_update_column where held is true)::text || ' tables'
    union all
    select 5,
           'dlr_psse_writer_holds_nothing_on_other_relations',
           (select writer from roles) is not null
               and (select count(*) from other_relations) > 0
               and (select count(*) from other_offenders) = 0,
           (select count(*) from other_relations)::text || ' other relations checked, offenders: ' ||
               coalesce((select string_agg(relation, ', ' order by relation) from other_offenders), 'none')
    union all
    select 6,
           'dlr_psse_writer_policies_are_insert_and_select_only',
           (select count(*) from psse_policies) = 8 and (select count(*) from well_formed_policies) = 8,
           (select count(*) from psse_policies)::text || ' policies on the four tables, ' ||
               (select count(*) from well_formed_policies)::text || ' of 8 as expected, found: ' ||
               coalesce((select string_agg(tablename || '.' || policyname || ' ' || cmd, ', ' order by tablename, policyname)
                           from psse_policies), 'none')
    union all
    select 7,
           'dlr_psse_writer_role_attributes',
           coalesce((select rolcanlogin
                         and not rolsuper and not rolcreaterole and not rolcreatedb
                         and not rolbypassrls and not rolreplication
                       from writer_role), false),
           coalesce((select 'canlogin=' || rolcanlogin::text || ', super=' || rolsuper::text ||
                            ', createrole=' || rolcreaterole::text || ', createdb=' || rolcreatedb::text ||
                            ', bypassrls=' || rolbypassrls::text || ', replication=' || rolreplication::text
                       from writer_role), 'role missing')
  ) as checks
 order by ord;
