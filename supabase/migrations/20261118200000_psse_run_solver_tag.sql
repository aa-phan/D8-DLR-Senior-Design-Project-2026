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
-- this file adds no grant or revoke on them, no role and no credential (D-02); the view section
-- below only repeats the view's own earlier revoke and grant, unchanged. The four psse_* tables stay
-- private. No index is added: at 24 runs a day the existing slot_time index is enough.
--
-- Public view (D-03, owner-confirmed 2026-11-18): the last section replaces public.latest_grid_study
-- with its earlier statement plus one predicate, r.solver = 'psse', so the view reads PSS/E runs
-- only until the per-solver view of a later phase replaces it. It changes no column, no column
-- order, no owner right and no grant.
--
-- Additive: it never edits an applied migration (20261109233541_psse_results.sql and
-- 20261116200000_expose_latest_grid_study.sql are untouched). Idempotent: the columns are added
-- only if missing, every constraint is dropped if it exists then added, and the view is replaced by
-- the same statement, so a second run leaves the same definitions. The owner applies it with
-- `supabase db push --db-url ...` and then runs the read-only check
-- supabase/ops/verify_solver_tag.sql together with verify_psse_results.sql and verify_exposure.sql.

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

-- ---------------------------------------------------------------------------------------------
-- Public view guard (decision D-03 of phase 3, confirmed by the owner on 2026-11-18).
--
-- public.latest_grid_study (20261116200000_expose_latest_grid_study.sql) takes the newest complete
-- run with no solver filter and labels every row with the constant 'psse'. Once a run of the second
-- program is stored, the dashboard would show it as PSS/E until the per-solver view of a later phase
-- replaces this one. The statement below is the earlier view statement word for word with one added
-- line in newest_run, a filter that keeps only runs whose solver column reads psse: the view reads
-- PSS/E runs only. With only runs of the second program stored it has no rows.
--
-- Nothing else changes: the 20 columns and their order, with (security_invoker = false), the revoke
-- and grant, and the 20 column comments are the earlier ones. create or replace view keeps the
-- owner and the permission list; the revoke, grant and comments are issued again at no cost in case
-- a replace dropped one. The view comment gains one closing sentence. Replacing the view again
-- later needs no change here: the column list stays one-way (a column is only appended).
-- ---------------------------------------------------------------------------------------------

create or replace view public.latest_grid_study with (security_invoker = false) as
with newest_run as (
    select r.run_id, r.slot_time, r.finished_at, r.outcome
      from public.psse_run r
     where r.outcome in ('ok', 'fallback')
       and r.solver = 'psse'
     order by r.slot_time desc, r.finished_at desc, r.run_id desc
     limit 1
)
select
    'psse'::text as solver,
    d.city,
    n.slot_time,
    n.finished_at as study_finished_at,
    n.outcome as run_outcome,
    d.rating_source,
    d.fallback_reason,
    d.city_rating_valid_time,
    d.applied_amps_per_conductor,
    d.dispatched_amps_per_conductor,
    d.subconductors_per_phase,
    d.line_voltage_kv,
    d.applied_mva,
    d.voltage_limit_mva,
    d.dispatched_mva,
    d.dispatched_mw,
    d.dispatched_mva / d.applied_mva * 100 as usable_pct,
    d.limiting_factor,
    ceil(extract(epoch from (now() - n.slot_time)) / 60)::integer as age_minutes,
    (n.slot_time < now() - interval '90 minutes') as is_stale
from newest_run n
join public.psse_dispatched_capacity d on d.run_id = n.run_id and d.run_outcome = n.outcome
order by d.city;

revoke all on public.latest_grid_study from public, anon, authenticated;
grant select on public.latest_grid_study to anon, authenticated;

comment on view public.latest_grid_study is 'The newest complete grid-study run (outcome ok or fallback), one row per city (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO): the rating the study applied to the grid model, the voltage-stability limit and the capacity the grid can use. PRELIMINARY: the study runs on the public IEEE 39-bus test case scaled per city, not on a utility network, and Power Systems has not reviewed the results; show them as a demonstration, not an operating limit. No rows until a complete run exists; a result is stale when its hour is more than 90 minutes old. Runs with the owner''s rights so the result tables stay private; read-only. Until the per-solver view replaces it, only PSS/E runs (solver psse) are shown.';

comment on column public.latest_grid_study.solver is 'none (identifier): the power-flow program that produced the row; psse (Siemens PSS/E). pandapower rows arrive in a later release.';
comment on column public.latest_grid_study.city is 'none (identifier): upper-case project city key, one of AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO.';
comment on column public.latest_grid_study.slot_time is 'UTC timestamp: the hour the study belongs to (the UTC hour its run started in).';
comment on column public.latest_grid_study.study_finished_at is 'UTC timestamp: when the study run finished.';
comment on column public.latest_grid_study.run_outcome is 'none (label): ok when every city used its live rating, fallback when at least one city used its static rating.';
comment on column public.latest_grid_study.rating_source is 'none (label): city_rating when the study used this city''s live rating, static_fallback when it used the normal (static) rating.';
comment on column public.latest_grid_study.fallback_reason is 'none (label): why the static rating was used (missing, invalid, stale, provisional, read_failed); null when rating_source is city_rating.';
comment on column public.latest_grid_study.city_rating_valid_time is 'UTC timestamp: the valid_time of the city_rating row the study used; null when the static rating was used.';
comment on column public.latest_grid_study.applied_amps_per_conductor is 'amperes per conductor (per wire): the rating the study applied, the same unit as latest_rating.rating_amps.';
comment on column public.latest_grid_study.dispatched_amps_per_conductor is 'amperes per conductor (per wire): the capacity the grid can use, the lower of the applied rating and the voltage-stability limit.';
comment on column public.latest_grid_study.subconductors_per_phase is 'count: conductors per phase in the study (multiply a per-conductor value by this for the circuit).';
comment on column public.latest_grid_study.line_voltage_kv is 'kilovolts (line to line): the voltage class the study used to convert amperes to MVA.';
comment on column public.latest_grid_study.applied_mva is 'MVA per circuit: the applied rating, sqrt(3) x kV x circuit amperes / 1000.';
comment on column public.latest_grid_study.voltage_limit_mva is 'MVA per circuit: the most the city''s transfer can carry before voltage limits are reached.';
comment on column public.latest_grid_study.dispatched_mva is 'MVA per circuit: the lower of applied_mva and voltage_limit_mva.';
comment on column public.latest_grid_study.dispatched_mw is 'MW per circuit: dispatched_mva times the study power factor; per circuit, so not comparable with city_rating.rating_mw (per conductor).';
comment on column public.latest_grid_study.usable_pct is 'percent: dispatched_mva / applied_mva x 100, the share of the rating the grid can use; 100 when the rating is the limit.';
comment on column public.latest_grid_study.limiting_factor is 'none (label): dlr_rating when the rating is the limit, voltage_stability when voltage limits cap the capacity below the rating.';
comment on column public.latest_grid_study.age_minutes is 'minutes (whole, rounded up): from slot_time to the moment of the request; stale when greater than 90.';
comment on column public.latest_grid_study.is_stale is 'none (flag): true when slot_time is strictly more than 90 minutes before the request; exactly 90 minutes is fresh.';
