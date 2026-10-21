-- supabase/migrations/20261019000000_create_city_rating.sql
--
-- Production-pipeline Phase 4 (DB-01, DB-06): the rating store.
--
-- Creates:
--   public.city_rating   one row per (city, valid_time): the hourly per-city rating,
--                        its weather inputs, forecast and detector facts, and the
--                        identity of what produced it (config fingerprint, model hashes)
--   public.pipeline_run  operational run log (one row per workflow run), not a
--                        consumer table
--   role dlr_writer      the CI writer: SELECT, INSERT, UPDATE on the two tables only
--
-- Idempotent: safe to re-apply (tables use if not exists, each policy is dropped
-- before it is created, the role is created inside a guard).
--
-- Applied with `supabase db push --db-url ...` by the owner (plan 04-05). The writer
-- role is created here WITHOUT a credential: the owner sets its credential once, out
-- of band, and it is never stored in a migration, code or any committed file.
-- Phase 6 adds the anon read grant and policy in its own migration; this migration
-- gives anon and authenticated no privilege at all.
--
-- Row-level security is on for both tables. A role without a policy sees zero rows
-- and gets no error, so dlr_writer gets one permissive policy per table.

create table if not exists public.city_rating (
    city text not null constraint city_rating_city_ck check (city in ('AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO')),
    valid_time timestamptz not null constraint city_rating_valid_time_hour_ck check (valid_time = date_trunc('hour', valid_time)),
    observation_time timestamptz,
    rating_amps double precision not null constraint city_rating_rating_amps_ck check (rating_amps > 0 and rating_amps < 'Infinity'::float8),
    rating_mw double precision not null constraint city_rating_rating_mw_ck check (rating_mw > 0 and rating_mw < 'Infinity'::float8),
    static_rating_amps double precision not null,
    static_rating_mw double precision not null,
    line_voltage_kv double precision not null,
    power_factor double precision not null,
    status text not null constraint city_rating_status_ck check (status in ('ok', 'fallback')),
    fallback boolean not null,
    fallback_gates text[] not null default '{}',
    alerts text[] not null default '{}',
    exhausted boolean not null default false,
    station_id text,
    candidates_probed integer,
    probe_trail jsonb,
    air_temp_c double precision,
    wind_perp_ms double precision,
    wind_speed_ms double precision,
    wind_direction_deg double precision,
    solar_radiation_wm2 double precision,
    temp_source text,
    wind_source text,
    solar_source text,
    forecast_method text,
    forecast_status text constraint city_rating_forecast_status_ck check (forecast_status in ('ok', 'cold_start', 'failed')),
    forecast_amps double precision,
    forecast_ci_lower_amps double precision,
    forecast_ci_upper_amps double precision,
    forecast_horizon_min double precision,
    forecast_n_observations integer,
    forecast_used_by_g6 boolean,
    detector_signal text,
    detector_model_loaded boolean,
    history_rows integer,
    usable_history_rows integer,
    rating_basis text not null,
    config_version text not null,
    config_fingerprint text not null constraint city_rating_config_fingerprint_ck check (config_fingerprint ~ '^[0-9a-f]{64}$'),
    forecast_model_sha256 text constraint city_rating_forecast_model_sha256_ck check (forecast_model_sha256 ~ '^[0-9a-f]{64}$'),
    anomaly_model_sha256 text constraint city_rating_anomaly_model_sha256_ck check (anomaly_model_sha256 ~ '^[0-9a-f]{64}$'),
    origin text not null default 'live' constraint city_rating_origin_ck check (origin in ('live', 'backfill')),
    run_id text,
    run_attempt integer,
    pipeline_version text,
    schema_version integer not null default 1,
    first_written_at timestamptz not null default date_trunc('second', now()),
    computed_at timestamptz not null default date_trunc('second', now()),
    constraint city_rating_pk primary key (city, valid_time)
);

create table if not exists public.pipeline_run (
    run_id text constraint pipeline_run_pk primary key,
    run_attempt integer,
    started_at timestamptz not null default date_trunc('second', now()),
    finished_at timestamptz,
    window_end timestamptz,
    provider text,
    forecast_method text,
    pipeline_version text,
    cities_ok text[] not null default '{}',
    cities_failed jsonb not null default '{}'::jsonb,
    provider_errors jsonb,
    sources jsonb
);

alter table public.city_rating enable row level security;
alter table public.pipeline_run enable row level security;

-- Grants are stated explicitly so behavior is the same before and after Supabase
-- stops auto-granting new public tables to the API roles (2026-10-30). Phase 6 adds
-- the read grant for anon; it is deliberately not part of this phase (OD-6).
revoke all on public.city_rating, public.pipeline_run from anon, authenticated;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'dlr_writer') then
        create role dlr_writer login;
    end if;
end
$$;

grant usage on schema public to dlr_writer;
grant select, insert, update on public.city_rating, public.pipeline_run to dlr_writer;

drop policy if exists dlr_writer_all on public.city_rating;
create policy dlr_writer_all on public.city_rating for all to dlr_writer using (true) with check (true);

drop policy if exists dlr_writer_all on public.pipeline_run;
create policy dlr_writer_all on public.pipeline_run for all to dlr_writer using (true) with check (true);

comment on table public.city_rating is 'Per-city hourly dynamic line rating rows. Values are provisional per rating_basis. Key semantics (OD-7): one row per (city, valid_time); a same-hour retry overwrites the row while first_written_at never changes.';
comment on table public.pipeline_run is 'Operational run log, one row per workflow run. Not a consumer table.';

comment on column public.city_rating.city is 'none (identifier): upper-case project city key, one of AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO.';
comment on column public.city_rating.valid_time is 'UTC instant: the hour-truncated UTC run slot of the run window end (OD-7). Together with city it is the primary key.';
comment on column public.city_rating.observation_time is 'UTC instant: the weather hour the composer aligned the observation to; may be older than valid_time. NULL when unknown or exhausted.';
comment on column public.city_rating.rating_amps is 'amperes (A), per conductor: the dynamic line rating after the safety gates, or the static fallback rating when status is fallback.';
comment on column public.city_rating.rating_mw is 'megawatts (MW), three-phase real power via ercot_dlr_merger.amps_to_mw from rating_amps, line_voltage_kv and power_factor.';
comment on column public.city_rating.static_rating_amps is 'amperes (A), per conductor: the owner-supplied static rating for the city (provisional).';
comment on column public.city_rating.static_rating_mw is 'megawatts (MW), three-phase real power via ercot_dlr_merger.amps_to_mw from static_rating_amps.';
comment on column public.city_rating.line_voltage_kv is 'kilovolts (kV): line voltage used for the MW conversion.';
comment on column public.city_rating.power_factor is 'dimensionless: power factor used for the MW conversion.';
comment on column public.city_rating.status is 'none (category): ok when the computed rating passed every gate, fallback when the static rating was used.';
comment on column public.city_rating.fallback is 'none (flag): true when the rating is the static fallback rating.';
comment on column public.city_rating.fallback_gates is 'none (labels): sorted, de-duplicated first token of each alert (for example G4, EXHAUSTED); empty when no gate fired.';
comment on column public.city_rating.alerts is 'none (text): safety-gate alert messages of the run; empty array when there are none.';
comment on column public.city_rating.exhausted is 'none (flag): true when every candidate weather station was exhausted and no observation exists.';
comment on column public.city_rating.station_id is 'none (identifier): weather station that supplied the observation; NULL when exhausted.';
comment on column public.city_rating.candidates_probed is 'count: number of candidate stations probed.';
comment on column public.city_rating.probe_trail is 'none (json): one entry per probed station with stid, lat, lon, distance_km and outcome.';
comment on column public.city_rating.air_temp_c is 'degrees Celsius: air temperature of the observation.';
comment on column public.city_rating.wind_perp_ms is 'metres per second, component perpendicular to the line: the wind the thermal model used (the CSV archive calls it wind_speed).';
comment on column public.city_rating.wind_speed_ms is 'metres per second: measured wind speed before projection onto the line.';
comment on column public.city_rating.wind_direction_deg is 'degrees, meteorological direction the wind comes from.';
comment on column public.city_rating.solar_radiation_wm2 is 'watts per square metre: solar radiation of the observation.';
comment on column public.city_rating.temp_source is 'none (label): provider that supplied the air temperature.';
comment on column public.city_rating.wind_source is 'none (label): provider that supplied the wind.';
comment on column public.city_rating.solar_source is 'none (label): provider that supplied the solar radiation.';
comment on column public.city_rating.forecast_method is 'none (label): forecast method requested for the run (naive, ewm or ml).';
comment on column public.city_rating.forecast_status is 'none (category): ok, cold_start or failed; NULL when not recorded.';
comment on column public.city_rating.forecast_amps is 'amperes (A), per conductor: one-step-ahead forecast of the rating; NULL when no forecast was produced.';
comment on column public.city_rating.forecast_ci_lower_amps is 'amperes (A), per conductor: lower edge of the forecast band.';
comment on column public.city_rating.forecast_ci_upper_amps is 'amperes (A), per conductor: upper edge of the forecast band.';
comment on column public.city_rating.forecast_horizon_min is 'minutes: forecast horizon.';
comment on column public.city_rating.forecast_n_observations is 'count: history observations the forecast used.';
comment on column public.city_rating.forecast_used_by_g6 is 'none (flag): true when the forecast fed the G6 detector this run.';
comment on column public.city_rating.detector_signal is 'none (label): the anomaly detector signal of the run.';
comment on column public.city_rating.detector_model_loaded is 'none (flag): true when a trained anomaly model was loaded. The model path is never stored.';
comment on column public.city_rating.history_rows is 'count: history rows read before cleaning.';
comment on column public.city_rating.usable_history_rows is 'count: history rows left usable after cleaning.';
comment on column public.city_rating.rating_basis is 'none (text): provisional-label text stating what the values are and are not (OD-5).';
comment on column public.city_rating.config_version is 'none (label): human-readable label of the rating assumption set (config.RATING_CONFIG_VERSION).';
comment on column public.city_rating.config_fingerprint is 'none (identifier): lowercase hex sha256 of the canonical JSON of the city rating assumptions (conductor, point, static rating, bounds, bearing, subconductors, voltage, power factor, G6 and forecast parameters; supabase_store.rating_config_snapshot). It changes whenever any of them changes; config_version is its human-readable label.';
comment on column public.city_rating.forecast_model_sha256 is 'none (identifier): sha256 of the forecast model file the run loaded; NULL when the forecast method has no artifact (forecast_method names it) or no forecast was produced. Backfill rows carry the Phase 3 run values.';
comment on column public.city_rating.anomaly_model_sha256 is 'none (identifier): sha256 of the anomaly model file the run loaded; NULL when none was loaded. Backfill rows carry the Phase 3 run values.';
comment on column public.city_rating.origin is 'none (category): live for pipeline rows, backfill for rows loaded from the Phase 3 archive.';
comment on column public.city_rating.run_id is 'none (identifier): workflow run id (GITHUB_RUN_ID) that wrote the row.';
comment on column public.city_rating.run_attempt is 'count: workflow run attempt number.';
comment on column public.city_rating.pipeline_version is 'none (identifier): short git commit of the pipeline code.';
comment on column public.city_rating.schema_version is 'none (version): city_rating row schema version.';
comment on column public.city_rating.first_written_at is 'UTC instant: when the row was first inserted. Never changes after insert.';
comment on column public.city_rating.computed_at is 'UTC instant: when the row was last written; updated on every rewrite of the same key.';

comment on column public.pipeline_run.run_id is 'none (identifier): workflow run id (GITHUB_RUN_ID).';
comment on column public.pipeline_run.run_attempt is 'count: workflow run attempt number.';
comment on column public.pipeline_run.started_at is 'UTC instant: when the run row was created.';
comment on column public.pipeline_run.finished_at is 'UTC instant: when the run finished.';
comment on column public.pipeline_run.window_end is 'UTC instant: end of the run weather window.';
comment on column public.pipeline_run.provider is 'none (label): weather provider mode of the run.';
comment on column public.pipeline_run.forecast_method is 'none (label): forecast method of the run.';
comment on column public.pipeline_run.pipeline_version is 'none (identifier): short git commit of the pipeline code.';
comment on column public.pipeline_run.cities_ok is 'none (labels): cities whose rating row was written.';
comment on column public.pipeline_run.cities_failed is 'none (json): city to error text for cities that failed.';
comment on column public.pipeline_run.provider_errors is 'none (json): provider error summary of the run.';
comment on column public.pipeline_run.sources is 'none (json): count of weather sources used per field.';
