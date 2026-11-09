-- supabase/ops/soak_cron_schedule.sql
--
-- Production-pipeline Phase 6 (E2E-02, D-14): start the five-minute soak freshness log.
--
-- Owner one-shot. Run it once in the Supabase SQL editor, after (1) the Cron integration is
-- enabled (Dashboard -> Integrations -> Cron) and (2) plan 06-09 applied the soak migration
-- (supabase/migrations/*_soak_freshness_log.sql), which created ops.log_freshness(). Then run
-- supabase/ops/soak_probe_smoke.sql after a few probes, before the 72 h clock starts (D-07).
--
-- Plain English: this tells the database to call ops.log_freshness() every five minutes, which
-- writes down how old each city's current rating is, using the 90-minute rule consumers see.
--
-- It lives here, and not in a migration, on purpose: a replay of migration history must never
-- start a job. Re-running it is safe: pg_cron creates the job named dlr-soak-freshness or updates
-- the existing one of that name, so there is never a second copy. The job runs as the role that
-- scheduled it. The soak ends with supabase/ops/soak_cron_unschedule.sql.
--
-- The result shown is the one job row: jobname, the schedule, the command and active = true.

select cron.schedule('dlr-soak-freshness', '*/5 * * * *', 'select ops.log_freshness()');

select jobid, jobname, schedule, command, active
  from cron.job
 where jobname = 'dlr-soak-freshness';
