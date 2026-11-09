-- supabase/ops/soak_probe_smoke.sql
--
-- Production-pipeline Phase 6 (E2E-02, D-07): the probe smoke check before the 72 h clock.
--
-- One read-only SELECT, no writes. The owner runs it in the Supabase SQL editor once the job
-- dlr-soak-freshness (supabase/ops/soak_cron_schedule.sql) has run a few times, roughly 15 to 20
-- minutes after scheduling. It returns one row per check: (check_name, ok, detail). Every ok must
-- be true before the 72 h soak clock starts: a probe that is broken is far cheaper to find now
-- than at hour 40, when it would force a restart. The local test
-- (backend/tests/soak_log_migration_test.py) runs this same file against a stand-in for pg_cron.
-- This directory is never applied by the Supabase CLI; it is not a migration.
--
-- What each check proves, in plain English:
--   soak_job_active_every_5_minutes      the job exists exactly once, is switched on, runs every five
--                                        minutes and calls the logging function
--   last_three_runs_succeeded            the database's own job history shows the last three runs
--                                        succeeded (none failed, none stuck)
--   last_three_probes_wrote_four_rows    each of the last three probes wrote one row for each of the
--                                        four cities
--   no_breach_in_the_last_three_probes   in those three probes no city was older than 90 minutes or
--                                        missing, the same rule consumers see in latest_rating.is_stale

with
job as (
    select jobid, active, schedule, command
      from cron.job
     where jobname = 'dlr-soak-freshness'
),
runs as (
    select runid, status, return_message, start_time
      from cron.job_run_details
     where jobid in (select jobid from job)
     order by start_time desc nulls last, runid desc
     limit 3
),
probes as (
    select probed_at,
           count(*) as city_rows,
           count(*) filter (where breach) as breaches
      from ops.freshness_log
     group by probed_at
     order by probed_at desc
     limit 3
)
select check_name, ok, detail
  from (
    select 'soak_job_active_every_5_minutes'::text as check_name,
           (select count(*) from job) = 1
               and exists (select 1 from job
                            where active
                              and schedule = '*/5 * * * *'
                              and command like '%ops.log_freshness()%') as ok,
           'jobs named dlr-soak-freshness=' || (select count(*) from job)::text ||
               coalesce((select '; active=' || active::text || '; schedule=' || schedule ||
                                '; command=' || command
                           from job limit 1), '') as detail
    union all
    select 'last_three_runs_succeeded',
           (select count(*) from runs) = 3
               and (select count(*) from runs where status = 'succeeded') = 3,
           'runs found=' || (select count(*) from runs)::text || ' of 3; newest first: ' ||
               coalesce((select string_agg(coalesce(status, 'unknown') ||
                                           coalesce(' (' || left(return_message, 80) || ')', ''),
                                           ', ' order by start_time desc nulls last, runid desc)
                           from runs), 'none')
    union all
    select 'last_three_probes_wrote_four_rows',
           (select count(*) from probes) = 3
               and (select count(*) from probes where city_rows = 4) = 3,
           'probes found=' || (select count(*) from probes)::text || ' of 3; rows per probe, newest first: ' ||
               coalesce((select string_agg(city_rows::text, ', ' order by probed_at desc) from probes), 'none')
    union all
    select 'no_breach_in_the_last_three_probes',
           (select count(*) from probes) > 0
               and coalesce((select sum(breaches) from probes), 0) = 0,
           'breach rows per probe, newest first: ' ||
               coalesce((select string_agg(breaches::text, ', ' order by probed_at desc) from probes), 'no probe yet')
  ) as checks
 order by check_name;
