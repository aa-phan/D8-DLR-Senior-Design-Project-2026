-- supabase/migrations/20261108120100_expose_day_ahead_forecast.sql
--
-- Production-pipeline Phase 8 (DAY-06, DAY-07; D-09, D-10, D-12): expose the day-ahead forecast
-- read-only, and let the permanent alarm catch a stalled day-ahead feed.
--
-- Creates:
--   view public.day_ahead_upcoming   every row of public.day_ahead_forecast whose valid_time is
--                                    still in the future, ordered by city then valid_time, with
--                                    26 published columns: the 25 table columns plus lead_minutes
--                                    (D-10). Past values stay readable in the table (OD-6).
--   view public.day_ahead_status     always four rows, one per city: when the next target is, how
--                                    many future values exist, when the newest value was issued,
--                                    which targets due within the next 12 hours have no row, and
--                                    the late flag (D-12). Seven published columns.
-- Changes privileges (D-09):
--   anon and authenticated get SELECT, and nothing else, on public.day_ahead_forecast and the two
--   views, plus the read policy day_ahead_forecast_public_read. Writes stay refused by privilege.
--   public.pipeline_run (the run log) stays private. city_rating, latest_rating and its 34
--   columns are not touched.
-- Replaces:
--   function public.assert_fresh(integer)   same signature, same 90-minute rating rule, same
--                                           SQLSTATE 22023 range check and PT503 alarm code, plus
--                                           one clause: once the day-ahead table holds a row, a
--                                           late city also raises PT503, with detail
--                                           day_ahead_late=... The 200 body gains day_ahead_armed.
--
-- Applied only after the first live issuing run was verified (D-17), so the exposure never reaches
-- consumers ahead of real, label-correct rows. The owner applies it with `supabase db push
-- --db-url ...`. This file adds no role and no credential.
--
-- Additive: it never edits an applied migration (Phase 4, Phase 6 or 20261108120000, all pinned by
-- sha256).
--
-- Idempotent: the views and the function are replaced, the policy is dropped before it is created,
-- and the revoke then grant leaves the same result when run twice.
--
-- One-way column lists (D-09): a name is never renamed or dropped, and a column is only ever
-- appended after the last one. The Python twin is backend/day_ahead_contract.py (UPCOMING_COLUMNS
-- and STATUS_COLUMNS) and a test fails if the two differ.
--
-- The late rule (D-12), stated once and shared by the status view and the alarm: the targets are
-- the 00/06/12/18 UTC instants T with now() < T <= now() + 12 hours; a target with no row is
-- missing; a city is late when it has a missing target AND the table holds at least one row (the
-- flag is armed by the first issued row, so a table that has never been written cannot raise a
-- false alarm).

-- D-10: the future targets with a value, one row each, with the lead from now in whole minutes
-- rounded up (a started minute counts), so lead_minutes is always at least 1.
create or replace view public.day_ahead_upcoming with (security_invoker = true) as
select
    city,
    valid_time,
    issued_at,
    forecast_run_init_time,
    horizon_minutes,
    forecast_amps,
    forecast_ci_lower_amps,
    forecast_ci_upper_amps,
    band_source,
    band_n,
    band_pairs_through,
    band_artifact_sha256,
    forecast_method,
    cooling_model_sha256,
    cooling_model_source,
    anchor_observation_time,
    anchor_source,
    label,
    config_version,
    config_fingerprint,
    run_id,
    run_attempt,
    pipeline_version,
    schema_version,
    first_written_at,
    ceil(extract(epoch from (valid_time - now())) / 60)::integer as lead_minutes
from public.day_ahead_forecast
where valid_time > now()
order by city, valid_time;

-- D-12: one row per city, even when the table is empty. The grid is the 6-hour UTC grid anchored
-- at 2000-01-01 00:00 UTC (a multiple of 6 hours from UTC midnight), so its instants are exactly
-- 00, 06, 12 and 18 UTC. generate_series starts at the first instant strictly after now() and ends
-- at now() + 12 hours inclusive.
create or replace view public.day_ahead_status with (security_invoker = true) as
select
    city,
    checked_at,
    next_target_time,
    upcoming_count,
    newest_issued_at,
    missing_targets,
    (exists (select 1 from public.day_ahead_forecast) and cardinality(missing_targets) > 0) as is_late
from (
    select c.city,
           now() as checked_at,
           date_bin(interval '6 hours', now(), timestamptz '2000-01-01 00:00:00+00') + interval '6 hours' as next_target_time,
           (select count(*)::integer from public.day_ahead_forecast f
             where f.city = c.city and f.valid_time > now()) as upcoming_count,
           (select max(f.issued_at) from public.day_ahead_forecast f where f.city = c.city) as newest_issued_at,
           array(
               select g.target
                 from generate_series(
                          date_bin(interval '6 hours', now(), timestamptz '2000-01-01 00:00:00+00') + interval '6 hours',
                          now() + make_interval(hours => 12),
                          interval '6 hours') as g(target)
                where not exists (select 1 from public.day_ahead_forecast f
                                   where f.city = c.city and f.valid_time = g.target)
                order by g.target
           ) as missing_targets
      from (values ('AUSTIN'), ('CORPUS_CHRISTI'), ('MIDLAND'), ('EL_PASO')) as c(city)
) as per_city
order by city;

comment on view public.day_ahead_upcoming is 'The day-ahead forecast rows whose valid_time is still in the future, ordered by city then valid_time, with the lead from now in minutes. Each value is an ml_cooling_corrected ampacity forecast from the Open-Meteo run initialised exactly 24 h before valid_time, with a 5-95% empirical band. Label: day-ahead-24h; engineering-selection; not-validated. It never sets or checks the live rating and never gates G6. Targets in the past stay readable in public.day_ahead_forecast. Read-only: the view runs with the caller''s rights.';

comment on column public.day_ahead_upcoming.city is 'none (identifier): upper-case project city key, one of AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO.';
comment on column public.day_ahead_upcoming.valid_time is 'UTC timestamp: the target hour the forecast is for, on the 00/06/12/18 UTC grid; always in the future in this view.';
comment on column public.day_ahead_upcoming.issued_at is 'UTC timestamp: the actual decision time of the run that issued the row, strictly before valid_time. A catch-up issue carries a later value than the first chance, so late values are visible.';
comment on column public.day_ahead_upcoming.forecast_run_init_time is 'UTC timestamp: initialisation time of the Open-Meteo weather run behind the value, exactly valid_time minus 24 h. The 24 h is the age of the weather run, not the lead from issued_at.';
comment on column public.day_ahead_upcoming.horizon_minutes is 'minutes: age of the weather run at valid_time; always 1440.';
comment on column public.day_ahead_upcoming.forecast_amps is 'amperes (A), per conductor: the day-ahead ml_cooling_corrected ampacity forecast for valid_time, under the city production conductor.';
comment on column public.day_ahead_upcoming.forecast_ci_lower_amps is 'amperes (A), per conductor: lower edge (5%) of the empirical residual-quantile band around forecast_amps.';
comment on column public.day_ahead_upcoming.forecast_ci_upper_amps is 'amperes (A), per conductor: upper edge (95%) of the empirical residual-quantile band around forecast_amps.';
comment on column public.day_ahead_upcoming.band_source is 'none (category): where the band came from, test-split (hashed TEST-split artifact, the launch band) or live-rolling (the forecast own recent misses against the live outcome).';
comment on column public.day_ahead_upcoming.band_n is 'count: number of residuals behind the band.';
comment on column public.day_ahead_upcoming.band_pairs_through is 'UTC timestamp: valid_time of the newest live pair behind a live-rolling band; NULL for a test-split band.';
comment on column public.day_ahead_upcoming.band_artifact_sha256 is 'none (identifier): lowercase hex sha256 of the TEST band artifact file; always recorded because the TEST artifact is the fallback band.';
comment on column public.day_ahead_upcoming.forecast_method is 'none (label): forecast method; always ml_cooling_corrected. No substitute method is ever published.';
comment on column public.day_ahead_upcoming.cooling_model_sha256 is 'none (identifier): lowercase hex sha256 of the cooling model file the value came from, verified before it was loaded.';
comment on column public.day_ahead_upcoming.cooling_model_source is 'none (category): refit when the city serves a production-conductor refit model, frozen when it serves the frozen shadow model.';
comment on column public.day_ahead_upcoming.anchor_observation_time is 'UTC timestamp: time of the station observation (the "now" reading) the correction used; it can be hours before valid_time.';
comment on column public.day_ahead_upcoming.anchor_source is 'none (label): provider that supplied the anchor observation (tceq or synoptic).';
comment on column public.day_ahead_upcoming.label is 'none (label): day-ahead-24h; engineering-selection; not-validated. States that this is a higher-error, engineering-selected, not-validated forecast.';
comment on column public.day_ahead_upcoming.config_version is 'none (label): human-readable label of the rating assumption set (config.RATING_CONFIG_VERSION).';
comment on column public.day_ahead_upcoming.config_fingerprint is 'none (identifier): lowercase hex sha256 of the canonical JSON of the city rating assumptions; the same identity the rating rows carry.';
comment on column public.day_ahead_upcoming.run_id is 'none (identifier): workflow run id (GITHUB_RUN_ID) that issued the row.';
comment on column public.day_ahead_upcoming.run_attempt is 'count: workflow run attempt number.';
comment on column public.day_ahead_upcoming.pipeline_version is 'none (identifier): short git commit of the pipeline code.';
comment on column public.day_ahead_upcoming.schema_version is 'none (version): day_ahead_forecast row schema version.';
comment on column public.day_ahead_upcoming.first_written_at is 'UTC timestamp: when the row was inserted. Never changes; rows are never rewritten.';
comment on column public.day_ahead_upcoming.lead_minutes is 'minutes (whole, rounded up): from the moment of the request to valid_time; it counts started minutes up to the target, so it is always at least 1 here.';

comment on view public.day_ahead_status is 'One row per city (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO), always four rows. It says when the next 00/06/12/18 UTC target is, how many future values exist, when the newest value was issued, which targets due within the next 12 hours have no value, and whether the city is late: it has a missing target and the table holds at least one row (the flag is armed by the first issued row). Read-only: the view runs with the caller''s rights.';

comment on column public.day_ahead_status.city is 'none (identifier): upper-case project city key, one of AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO.';
comment on column public.day_ahead_status.checked_at is 'UTC timestamp: the moment of the request; every other column is computed as of this instant.';
comment on column public.day_ahead_status.next_target_time is 'UTC timestamp: the first 00/06/12/18 UTC target strictly after checked_at.';
comment on column public.day_ahead_status.upcoming_count is 'count: number of stored day-ahead values for the city whose valid_time is after checked_at.';
comment on column public.day_ahead_status.newest_issued_at is 'UTC timestamp: the latest issued_at of any stored value of the city, past or future; NULL when the city has no value.';
comment on column public.day_ahead_status.missing_targets is 'UTC timestamps (array, ascending): every 00/06/12/18 UTC target T with checked_at < T <= checked_at + 12 hours that has no stored value for the city (the 12-hour rule); empty when none is missing.';
comment on column public.day_ahead_status.is_late is 'none (flag): true when missing_targets is not empty AND the day-ahead table holds at least one row (the 12-hour rule, armed by the first issued row); false when nothing is missing or nothing has ever been issued.';

-- Privileges (D-09): the table and both views are read-only for the public roles. The revoke
-- clears whatever an earlier default grant gave, then exactly SELECT is granted.
revoke all on public.day_ahead_forecast, public.day_ahead_upcoming, public.day_ahead_status from anon, authenticated;
grant select on public.day_ahead_forecast, public.day_ahead_upcoming, public.day_ahead_status to anon, authenticated;

-- Row-level security is already on for the table (20261108120000). The one read policy; no write
-- policy exists for either public role.
drop policy if exists day_ahead_forecast_public_read on public.day_ahead_forecast;
create policy day_ahead_forecast_public_read on public.day_ahead_forecast for select to anon, authenticated using (true);

-- The freshness check (API-01, DAY-07): the same signature as Phase 6, so there is still exactly
-- one function of this name and the alarm URL never meets an overload (HTTP 300). The rating part
-- is unchanged. The day-ahead part reads public.day_ahead_status, the one late rule that the view
-- also publishes. It runs as the caller (security invoker) and, with an empty search_path, every
-- name below is schema-qualified.
create or replace function public.assert_fresh(max_age_minutes integer default 90)
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
as $$
declare
    missing text[];
    stale text[];
    city_count integer;
    oldest timestamptz;
    armed boolean;
    day_ahead_late text[];
begin
    if max_age_minutes is null or max_age_minutes < 0 or max_age_minutes > 10080 then
        raise sqlstate '22023' using message = 'max_age_minutes must be between 0 and 10080';
    end if;

    select array_agg(c.city order by c.city) filter (where l.city is null),
           array_agg(c.city order by c.city) filter (where l.valid_time < now() - make_interval(mins => max_age_minutes)),
           count(l.city),
           min(l.valid_time)
      into missing, stale, city_count, oldest
      from (values ('AUSTIN'), ('CORPUS_CHRISTI'), ('MIDLAND'), ('EL_PASO')) as c(city)
      left join public.latest_rating l on l.city = c.city;

    -- D-12: armed once the day-ahead table holds a row; late cities are listed as CITY@<UTC target>.
    select exists (select 1 from public.day_ahead_forecast) into armed;

    select array_agg(s.city || '@' || to_char(m.target at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
                     order by s.city, m.target)
      into day_ahead_late
      from public.day_ahead_status s
     cross join lateral unnest(s.missing_targets) as m(target)
     where s.is_late;

    if missing is not null or stale is not null or day_ahead_late is not null then
        raise sqlstate 'PT503' using
            message = 'stale or missing city rating or late day-ahead forecast',
            detail = format('missing=%s stale=%s day_ahead_late=%s',
                            coalesce(missing::text, '{}'), coalesce(stale::text, '{}'),
                            coalesce(day_ahead_late::text, '{}'));
    end if;

    return jsonb_build_object(
        'ok', true,
        'cities', city_count,
        'max_age_minutes', max_age_minutes,
        'oldest_valid_time', oldest,
        'day_ahead_armed', armed);
end
$$;

revoke all on function public.assert_fresh(integer) from public, anon, authenticated;
grant execute on function public.assert_fresh(integer) to anon, authenticated;

comment on function public.assert_fresh(integer) is 'Freshness check for the permanent alarm. HTTP 200 with {ok, cities, max_age_minutes, oldest_valid_time, day_ahead_armed} when every one of the four cities has a latest_rating row no older than max_age_minutes (default 90, OD-4; exactly the limit is fresh) and no day-ahead target is late. Day-ahead clause: the day-ahead part is armed once public.day_ahead_forecast holds a row (day_ahead_armed true); from then on a city with a missing 00/06/12/18 UTC target due within the next 12 hours (public.day_ahead_status) is late. HTTP 503 (SQLSTATE PT503) with detail missing=... stale=... day_ahead_late=CITY@UTC-time,... when a city has no rating, only an older one, or is late. SQLSTATE 22023 (HTTP 400) when max_age_minutes is outside 0..10080. Runs as the caller.';

-- Ask PostgREST to reload its schema cache so the new views and the extended function are served at once.
notify pgrst, 'reload schema';
