-- supabase/migrations/20261116200000_expose_latest_grid_study.sql
--
-- Expose the newest grid-study result per city, read-only, to the dashboard's key (the
-- pandapower-solver workstream's VIEW-01 and VIEW-02, taken early on the owner's request on
-- 2026-11-16 so the dashboard can show the PSS/E results already written).
--
-- Creates:
--   view public.latest_grid_study   one row per city from the newest complete grid-study run
--                                   (outcome ok or fallback): the rating the study applied, the
--                                   voltage-stability limit, the capacity dispatched and which of
--                                   the two limits it, the study hour, its age and a stale flag.
--                                   20 published columns.
-- Changes privileges:
--   anon and authenticated get SELECT on the view and nothing else. The four psse_* tables stay
--   private (no privilege, no policy for the public roles); this file does not touch them.
--
-- Owner's rights, on purpose: unlike latest_rating and the day-ahead views, this view runs with
-- the rights of its owner (security_invoker = false), because the public roles hold nothing on
-- the tables it reads. That is what keeps the tables private while the view is public. The
-- Supabase linter reports such a view as "security definer view" (lint 0010); the finding is
-- accepted for this view only. Do not switch it to security_invoker: it would return no rows to
-- the dashboard. The view exposes a fixed column list and no run id, hash, case name, bus, error
-- text or details field.
--
-- solver: every row written so far comes from PSS/E, so the column is the constant 'psse'. When
-- the pandapower-solver workstream adds a solver column to psse_run, a later migration replaces
-- this view to read it (one row per city per solver); the column list stays one-way (a name is
-- never renamed or dropped, a column is only appended after the last one). The Python twin is
-- backend/grid_study_contract.py (COLUMNS) and a test fails if the two differ.
--
-- Additive: it never edits an applied migration. Idempotent: the view is replaced and the revoke
-- then grant leaves the same result when run twice. The owner applies it with `supabase db push
-- --db-url ...`. This file adds no role and no credential.

create or replace view public.latest_grid_study with (security_invoker = false) as
with newest_run as (
    select r.run_id, r.slot_time, r.finished_at, r.outcome
      from public.psse_run r
     where r.outcome in ('ok', 'fallback')
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

comment on view public.latest_grid_study is 'The newest complete grid-study run (outcome ok or fallback), one row per city (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO): the rating the study applied to the grid model, the voltage-stability limit and the capacity the grid can use. PRELIMINARY: the study runs on the public IEEE 39-bus test case scaled per city, not on a utility network, and Power Systems has not reviewed the results; show them as a demonstration, not an operating limit. No rows until a complete run exists; a result is stale when its hour is more than 90 minutes old. Runs with the owner''s rights so the result tables stay private; read-only.';

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
