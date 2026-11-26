-- supabase/migrations/20261126200000_latest_grid_study_per_solver.sql
--
-- Replace public.latest_grid_study with the per-solver view (the pandapower-solver workstream, phase 6,
-- VIEW-01 and VIEW-02, decisions D-01, D-06 and D-09).
--
-- What the view returns: the newest complete run (outcome ok or fallback) of each solver, one row per
-- city per solver, so at most 8 rows (four cities, two solvers). A solver with no complete run has no
-- rows; the view never returns a placeholder row for it. A run that failed is skipped. The solver of a
-- row is read from public.psse_run.solver, because the four result tables carry no solver column.
--
-- What it keeps: the view name, the 20 columns with their order and types (the contract the owner
-- approved on 2026-11-16), with (security_invoker = false) on purpose, the revoke and the grant
-- (reissued unchanged), the 90 minute stale rule (a result is stale when its hour is more than 90
-- minutes old, judged per solver) and 19 of the 20 column comments word for word.
--
-- Why security_invoker = false: the view runs with its owner's rights so that anon and authenticated
-- read it while holding nothing on the four psse_* tables, which stay private. Supabase lint 0010
-- (security definer view) is accepted for this view only; do not switch it to invoker rights.
--
-- What changes: the newest_run step no longer filters on solver psse and no longer takes one run only;
-- it takes the newest complete run per solver (one row for each value of the solver column). The constant label psse is
-- replaced by the solver stored on the run. Only the view comment and the solver column comment
-- change, because their old texts (one row per city, only PSS/E runs shown, pandapower rows come in a
-- later release) are no longer true.
--
-- Additive and idempotent: it never edits an applied migration (20261109233541_psse_results.sql,
-- 20261116200000_expose_latest_grid_study.sql and 20261118200000_psse_run_solver_tag.sql are
-- untouched). The view is replaced with create or replace, the revoke is followed by the grant, and the
-- comments are re-runnable, so a second run leaves the same definitions. It has no table change, no
-- data change, no index, no role and no credential, and no grant on any psse_ table.
--
-- Order warning: it must sort and be applied after 20261118200000_psse_run_solver_tag.sql; re-applying
-- that file alone afterwards restores the PSS/E-only view, so re-apply this file after it.
--
-- The owner applies it to the live project only after the Phase 5 soak passes (D-02), with
-- `supabase db push --db-url ...`, then runs the read-only checks
-- supabase/ops/verify_solver_tag.sql (6 checks), supabase/ops/verify_psse_results.sql (7 checks) and
-- supabase/ops/verify_exposure.sql (37 checks), every ok true.

create or replace view public.latest_grid_study with (security_invoker = false) as
with newest_run as (
    select distinct on (r.solver) r.solver, r.run_id, r.slot_time, r.finished_at, r.outcome
      from public.psse_run r
     where r.outcome in ('ok', 'fallback')
     order by r.solver, r.slot_time desc, r.finished_at desc, r.run_id desc
)
select
    n.solver,
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
order by d.city, n.solver;

revoke all on public.latest_grid_study from public, anon, authenticated;
grant select on public.latest_grid_study to anon, authenticated;

comment on view public.latest_grid_study is 'The newest complete grid-study run (outcome ok or fallback) of each solver, one row per city per solver (at most 8 rows: AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO for psse and for pandapower; filter on solver): the rating the study applied to the grid model, the voltage-stability limit and the capacity the grid can use. PRELIMINARY: the study runs on the public IEEE 39-bus test case scaled per city, not on a utility network, and Power Systems has not reviewed the results; show them as a demonstration, not an operating limit. No rows until a complete run exists; a result is stale when its hour is more than 90 minutes old. Runs with the owner''s rights so the result tables stay private; read-only.';

comment on column public.latest_grid_study.solver is 'none (identifier): the power-flow program that produced the row; psse (Siemens PSS/E) or pandapower (open-source solver). The view returns one row per city per solver, so filter on this column.';
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
