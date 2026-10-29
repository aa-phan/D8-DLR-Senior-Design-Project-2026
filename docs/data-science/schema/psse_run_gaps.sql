-- docs/data-science/schema/psse_run_gaps.sql
--
-- Gap check for the hourly PSS/E job (pss-e-integration Phase 3, SCH-02): which UTC hours have
-- no complete result set. SELECT only; it changes nothing. Safe to run in the Supabase SQL
-- editor as the owner, or as dlr_psse_writer (the job's own credential holds SELECT on
-- public.psse_run and a select policy).
--
-- One statement returning one row per gap, oldest first: (slot_time, gap_kind, runs, failed_runs).
--
--   slot_time    the UTC hour (timestamptz) with no complete result set
--   gap_kind     no_run       no psse_run row at all for that hour (laptop off or asleep,
--                             database unreachable, process killed before the record was written)
--                failed_only  rows exist for that hour but every one is failed (the job ran,
--                             the study or the write did not complete)
--   runs         number of psse_run rows in that hour (0 for no_run)
--   failed_runs  how many of them are failed
--
-- The five rules:
--   1. Several rows in one hour are not a gap (the table is append-only; a catch-up run after a
--      wake can add a second row to a slot). Only an hour with no ok or fallback row is listed.
--   2. A failed run is a record, so its hour is never no_run; but an hour whose rows are all
--      failed has no results, so it is listed as failed_only and never hidden.
--   3. The current UTC hour is excluded: its run may still be pending.
--   4. Hours before the first recorded run are not gaps.
--   5. An empty table gives no rows (the caller reports that no runs are recorded).
--
-- slot_time is the UTC hour floor of the laptop's start time. A laptop clock far from the
-- database's clock therefore shows as a false gap plus a doubled slot, and this statement
-- cannot tell the difference. It works in UTC only.

with bounds as (
    select min(slot_time) as first_slot,
           (date_trunc('hour', now() at time zone 'UTC') at time zone 'UTC') - interval '1 hour' as last_closed_slot
    from public.psse_run
),
expected as (
    select g.slot_time
    from bounds b, generate_series(b.first_slot, b.last_closed_slot, interval '1 hour') as g(slot_time)
),
seen as (
    select slot_time,
           count(*) as runs,
           count(*) filter (where outcome in ('ok', 'fallback')) as complete_runs,
           count(*) filter (where outcome = 'failed') as failed_runs
    from public.psse_run
    group by slot_time
)
select e.slot_time,
       case when s.slot_time is null then 'no_run' else 'failed_only' end as gap_kind,
       coalesce(s.runs, 0) as runs,
       coalesce(s.failed_runs, 0) as failed_runs
from expected e
left join seen s on s.slot_time = e.slot_time
where s.slot_time is null or s.complete_runs = 0
order by e.slot_time;
