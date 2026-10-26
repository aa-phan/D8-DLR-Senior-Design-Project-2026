-- supabase/ops/soak_cron_unschedule.sql
--
-- Production-pipeline Phase 6 (E2E-02, D-13): stop the five-minute soak freshness log.
--
-- Owner one-shot. Run it once in the Supabase SQL editor at the end of the soak, after the owner's
-- sign-off and after the soak record has been exported to the repo (plan 06-12).
--
-- Plain English: this removes the scheduled job named dlr-soak-freshness and then counts how many
-- jobs with that name are left. The answer must be 0.
--
-- Safe to run again: with no job of that name there is no row, so no call is made and the count is
-- still 0. It touches no other job: the cron-job.org freshness alarm is not a database job and is
-- not affected. The ops.freshness_log rows and the job's run history in cron.job_run_details stay
-- as they are and are harmless.

select cron.unschedule(jobid)
  from cron.job
 where jobname = 'dlr-soak-freshness';

select count(*) as remaining_jobs
  from cron.job
 where jobname = 'dlr-soak-freshness';
