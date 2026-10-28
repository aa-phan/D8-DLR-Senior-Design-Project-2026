-- docs/data-science/schema/psse_results_v1_checks.sql
--
-- Read-only completeness checks for the PSS/E result tables (pss-e-integration Phase 1, WB-02).
-- Run as dlr_psse_writer or as an administrator; it changes nothing.
--
-- One statement returning one row per check, in this order: (check_name, ok, detail).
-- ok is true when no run offends; detail is 'offending runs: <n>', followed by
-- '; first: ' and up to five offending run_ids in run_id order when n > 0.
--
--   non_failed_runs_have_four_dispatch_rows   every ok or fallback run has exactly one
--                                             psse_dispatched_capacity row per city (four rows)
--   non_failed_runs_have_four_margin_rows     the same for psse_voltage_margin
--   non_failed_runs_contingency_count_matches the number of distinct contingency_id values among
--                                             the run's psse_contingency_result rows equals
--                                             psse_run.n_contingencies_with_results (0 when null)
--   failed_runs_have_no_results               no failed run has a row in any of the three
--                                             result tables
--   dispatch_voltage_limit_matches_margin     for each (run_id, city) the voltage_limit_mva of
--                                             psse_dispatched_capacity and psse_voltage_margin
--                                             agree within a relative 1e-6
--
-- Expected result on a healthy database: every ok is true.

with
dispatch_offenders as (
    select r.run_id
    from public.psse_run r
    left join public.psse_dispatched_capacity d on d.run_id = r.run_id
    where r.outcome in ('ok', 'fallback')
    group by r.run_id
    having count(distinct d.city) <> 4
),
margin_offenders as (
    select r.run_id
    from public.psse_run r
    left join public.psse_voltage_margin m on m.run_id = r.run_id
    where r.outcome in ('ok', 'fallback')
    group by r.run_id
    having count(distinct m.city) <> 4
),
contingency_offenders as (
    select r.run_id
    from public.psse_run r
    left join public.psse_contingency_result c on c.run_id = r.run_id
    where r.outcome in ('ok', 'fallback')
    group by r.run_id, r.n_contingencies_with_results
    having count(distinct c.contingency_id) <> coalesce(r.n_contingencies_with_results, 0)
),
failed_offenders as (
    select r.run_id
    from public.psse_run r
    where r.outcome = 'failed'
      and (exists (select 1 from public.psse_dispatched_capacity d where d.run_id = r.run_id)
           or exists (select 1 from public.psse_voltage_margin m where m.run_id = r.run_id)
           or exists (select 1 from public.psse_contingency_result c where c.run_id = r.run_id))
),
limit_offenders as (
    select distinct d.run_id
    from public.psse_dispatched_capacity d
    join public.psse_voltage_margin m on m.run_id = d.run_id and m.city = d.city
    where abs(d.voltage_limit_mva - m.voltage_limit_mva) > 1e-6 * greatest(abs(d.voltage_limit_mva), 1)
),
offenders as (
    select 1 as ord, run_id from dispatch_offenders
    union all
    select 2, run_id from margin_offenders
    union all
    select 3, run_id from contingency_offenders
    union all
    select 4, run_id from failed_offenders
    union all
    select 5, run_id from limit_offenders
),
checks (ord, check_name) as (
    values
        (1, 'non_failed_runs_have_four_dispatch_rows'),
        (2, 'non_failed_runs_have_four_margin_rows'),
        (3, 'non_failed_runs_contingency_count_matches'),
        (4, 'failed_runs_have_no_results'),
        (5, 'dispatch_voltage_limit_matches_margin')
)
select
    c.check_name::text as check_name,
    count(o.run_id) = 0 as ok,
    'offending runs: ' || count(o.run_id)
        || case
               when count(o.run_id) > 0 then
                   '; first: ' || (
                       select string_agg(f.run_id, ', ' order by f.run_id)
                       from (select x.run_id from offenders x where x.ord = c.ord order by x.run_id limit 5) f
                   )
               else ''
           end as detail
from checks c
left join offenders o on o.ord = c.ord
group by c.ord, c.check_name
order by c.ord;
