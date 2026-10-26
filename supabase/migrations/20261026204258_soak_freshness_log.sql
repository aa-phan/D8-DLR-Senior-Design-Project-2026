-- supabase/migrations/20261026204258_soak_freshness_log.sql
--
-- Production-pipeline Phase 6 (E2E-02; D-02, D-07, D-14, OD-4): the freshness log for the 72 h soak.
--
-- Plain English: every five minutes a scheduled call to ops.log_freshness() writes down, for each
-- of the four cities, the time of its current rating, how old that rating is in seconds, and
-- whether it is a breach (older than 90 minutes, or missing). The breach flag is the one that
-- public.latest_rating already shows consumers (is_stale), and the age is the exact elapsed
-- time, so the soak record, the consumer flag and the freshness alarm can never disagree
-- (D-02, D-14: this log, not the alarm, is the soak's record).
--
-- What this file does NOT do: it schedules nothing. Starting and stopping the five-minute job is
-- the owner's one-shot SQL in supabase/ops/soak_cron_schedule.sql and soak_cron_unschedule.sql,
-- kept outside migration history on purpose so that replaying the migrations can never start a job.
--
-- The ops schema is not an exposed schema (the Data API serves public only). Nothing here is
-- granted to anon, authenticated or PUBLIC; the CI writer role dlr_writer, when it exists, may
-- read the log (so the owner's soak export can) and nothing more.
--
-- Idempotent: safe to apply twice; logged rows are never touched. Additive: no Phase 4 or
-- Phase 6 expose file is changed. Applied by the owner in plan 06-09, after Phase 5's 05-08 sign-off.

create schema if not exists ops;
revoke all on schema ops from public, anon, authenticated;

create table if not exists ops.freshness_log (
    id                bigint generated always as identity primary key,
    probed_at         timestamptz not null default now(),
    city              text not null,
    latest_valid_time timestamptz,
    age_seconds       numeric,
    breach            boolean not null
);

create index if not exists freshness_log_probed_at_idx on ops.freshness_log (probed_at);

-- One probe: one row per expected city, even a city with no current rating. The four city keys
-- equal config.LOCATIONS (guarded by backend/tests/soak_log_migration_test.py). It reads the view
-- as the calling role, so the rating it logs is the rating a consumer with the same rights sees.
-- Returns the number of rows written (4 when every city is listed).
create or replace function ops.log_freshness()
returns integer
language plpgsql
volatile
set search_path = ''
as $$
declare
    written integer;
begin
    insert into ops.freshness_log (city, latest_valid_time, age_seconds, breach)
    select c.city,
           l.valid_time,
           extract(epoch from (now() - l.valid_time)),
           coalesce(l.is_stale, true)
      from (values ('AUSTIN'), ('CORPUS_CHRISTI'), ('MIDLAND'), ('EL_PASO')) as c(city)
      left join public.latest_rating l on l.city = c.city;
    get diagnostics written = row_count;
    return written;
end
$$;

-- Privileges: nothing for the consumer roles, whatever the platform's default grants hand out.
revoke all on all tables in schema ops from public, anon, authenticated;
revoke all on all sequences in schema ops from public, anon, authenticated;
revoke all on function ops.log_freshness() from public, anon, authenticated;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'dlr_writer') then
        grant usage on schema ops to dlr_writer;
        grant select on ops.freshness_log to dlr_writer;
    end if;
end
$$;

comment on table ops.freshness_log is 'Soak freshness log (E2E-02): one row per city per five-minute probe, written by ops.log_freshness(). breach is public.latest_rating.is_stale (OD-4: strictly more than 90 minutes old; a city with no rating is a breach). Not exposed through the Data API.';
comment on column ops.freshness_log.id is 'none (identifier): generated row number; rows of one probe are consecutive.';
comment on column ops.freshness_log.probed_at is 'UTC instant (timestamptz): when the probe ran; every row of one probe carries the same value.';
comment on column ops.freshness_log.city is 'none (label): city key as in config.LOCATIONS (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO).';
comment on column ops.freshness_log.latest_valid_time is 'UTC instant (timestamptz): valid_time of the city''s newest rating at the probe; null when the city has no rating.';
comment on column ops.freshness_log.age_seconds is 'seconds (exact, not rounded): elapsed time from latest_valid_time to probed_at; null when the city has no rating.';
comment on column ops.freshness_log.breach is 'none (flag): true when the rating is strictly more than 90 minutes old (age_seconds > 5400) or missing; exactly 90 minutes is fresh.';

comment on function ops.log_freshness() is 'Writes one ops.freshness_log row per expected city (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO) from public.latest_rating, using the view''s own is_stale flag and the exact age in seconds, and returns the number of rows written. Scheduled by the owner outside migration history (supabase/ops/soak_cron_schedule.sql); no consumer role may execute it.';
