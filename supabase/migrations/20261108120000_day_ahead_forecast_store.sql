-- supabase/migrations/20261108120000_day_ahead_forecast_store.sql
--
-- Production-pipeline Phase 8 (DAY-05, D-09, D-11): the write side of the day-ahead forecast.
--
-- Creates:
--   public.day_ahead_forecast   one row per (city, valid_time): the day-ahead ml_cooling_corrected
--                               value for one 00/06/12/18 UTC target hour, its 5-95% band, and the
--                               identity of what produced it (cooling model hash, band artifact
--                               hash, config fingerprint, run). The weather run behind every row
--                               was initialised exactly 24 h before valid_time.
-- Adds:
--   public.pipeline_run.day_ahead   private jsonb: per-city day-ahead outcomes and redacted
--                                   reasons. Operational, never public.
--
-- It never changes city_rating, latest_rating or their 34-column contract.
--
-- Idempotent: safe to re-apply (the table uses if not exists, the column uses add column if not
-- exists, the policy is dropped before it is created).
--
-- Applied with `supabase db push --db-url ...` by the owner. This file holds no credential and no
-- connection string. It gives anon and authenticated no privilege at all: the separate expose
-- migration (D-17) grants SELECT only after the first issued rows have been checked.
--
-- First write wins (D-04): the runner inserts with ON CONFLICT (city, valid_time) DO NOTHING, and
-- dlr_writer holds select and insert only, so an issued value can never be rewritten or deleted
-- through the writer role.
--
-- Row-level security is on. A role without a policy sees zero rows and gets no error, so
-- dlr_writer gets one permissive policy.

create table if not exists public.day_ahead_forecast (
    city text not null constraint day_ahead_forecast_city_ck check (city in ('AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO')),
    valid_time timestamptz not null
        constraint day_ahead_forecast_valid_time_hour_ck check ((valid_time at time zone 'UTC') = date_trunc('hour', valid_time at time zone 'UTC'))
        constraint day_ahead_forecast_valid_time_grid_ck check (extract(hour from valid_time at time zone 'UTC')::int % 6 = 0),
    issued_at timestamptz not null constraint day_ahead_forecast_issued_before_valid_ck check (issued_at < valid_time),
    forecast_run_init_time timestamptz not null constraint day_ahead_forecast_run_init_ck check (forecast_run_init_time = valid_time - interval '24 hours'),
    horizon_minutes integer not null default 1440 constraint day_ahead_forecast_horizon_ck check (horizon_minutes = 1440),
    forecast_amps double precision not null constraint day_ahead_forecast_amps_ck check (forecast_amps > 0 and forecast_amps < 'Infinity'::float8),
    forecast_ci_lower_amps double precision not null constraint day_ahead_forecast_ci_lower_ck check (forecast_ci_lower_amps > '-Infinity'::float8 and forecast_ci_lower_amps < 'Infinity'::float8),
    forecast_ci_upper_amps double precision not null constraint day_ahead_forecast_ci_upper_ck check (forecast_ci_upper_amps > '-Infinity'::float8 and forecast_ci_upper_amps < 'Infinity'::float8),
    band_source text not null constraint day_ahead_forecast_band_source_ck check (band_source in ('test-split', 'live-rolling')),
    band_n integer not null constraint day_ahead_forecast_band_n_ck check (band_n > 0),
    band_pairs_through timestamptz,
    band_artifact_sha256 text not null constraint day_ahead_forecast_band_artifact_sha256_ck check (band_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    forecast_method text not null constraint day_ahead_forecast_method_ck check (forecast_method = 'ml_cooling_corrected'),
    cooling_model_sha256 text not null constraint day_ahead_forecast_cooling_model_sha256_ck check (cooling_model_sha256 ~ '^[0-9a-f]{64}$'),
    cooling_model_source text not null constraint day_ahead_forecast_cooling_model_source_ck check (cooling_model_source in ('refit', 'frozen')),
    anchor_observation_time timestamptz not null,
    anchor_source text not null,
    label text not null constraint day_ahead_forecast_label_ck check (label <> ''),
    config_version text not null,
    config_fingerprint text not null constraint day_ahead_forecast_config_fingerprint_ck check (config_fingerprint ~ '^[0-9a-f]{64}$'),
    run_id text not null,
    run_attempt integer not null,
    pipeline_version text not null,
    schema_version integer not null default 1,
    first_written_at timestamptz not null default date_trunc('second', now()),
    constraint day_ahead_forecast_band_contains_point_ck check (forecast_ci_lower_amps <= forecast_amps and forecast_amps <= forecast_ci_upper_amps),
    constraint day_ahead_forecast_band_pairs_through_ck check ((band_pairs_through is not null) = (band_source = 'live-rolling')),
    constraint day_ahead_forecast_pk primary key (city, valid_time)
);

alter table public.pipeline_run add column if not exists day_ahead jsonb;

alter table public.day_ahead_forecast enable row level security;

-- Grants are stated explicitly so behavior is the same before and after Supabase stops
-- auto-granting new public tables to the API roles. The expose migration (D-17) adds the read
-- grant for anon; it is deliberately not part of this one.
revoke all on public.day_ahead_forecast from anon, authenticated;

grant usage on schema public to dlr_writer;
-- Insert only, no update and no delete: an issued value is never rewritten (first write wins).
grant select, insert on public.day_ahead_forecast to dlr_writer;

drop policy if exists dlr_writer_all on public.day_ahead_forecast;
create policy dlr_writer_all on public.day_ahead_forecast for all to dlr_writer using (true) with check (true);

comment on table public.day_ahead_forecast is 'Day-ahead ml_cooling_corrected ampacity forecasts: one row per (city, valid_time) for each 00/06/12/18 UTC target hour, from the Open-Meteo run initialised exactly 24 h before valid_time, with a 5-95% empirical band. Label: day-ahead-24h; engineering-selection; not-validated. It never sets or checks the live rating and never gates G6. First write wins: an issued row is never rewritten.';

comment on column public.day_ahead_forecast.city is 'none (identifier): upper-case project city key, one of AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO.';
comment on column public.day_ahead_forecast.valid_time is 'UTC timestamp: the target hour the forecast is for, on the 00/06/12/18 UTC grid. Together with city it is the primary key.';
comment on column public.day_ahead_forecast.issued_at is 'UTC timestamp: the actual decision time of the run that issued the row, strictly before valid_time. A catch-up issue carries a later value than the first chance, so late values are visible.';
comment on column public.day_ahead_forecast.forecast_run_init_time is 'UTC timestamp: initialisation time of the Open-Meteo weather run behind the value, exactly valid_time minus 24 h. The 24 h is the age of the weather run, not the lead from issued_at.';
comment on column public.day_ahead_forecast.horizon_minutes is 'minutes: age of the weather run at valid_time; always 1440.';
comment on column public.day_ahead_forecast.forecast_amps is 'amperes (A), per conductor: the day-ahead ml_cooling_corrected ampacity forecast for valid_time, under the city production conductor.';
comment on column public.day_ahead_forecast.forecast_ci_lower_amps is 'amperes (A), per conductor: lower edge (5%) of the empirical residual-quantile band around forecast_amps.';
comment on column public.day_ahead_forecast.forecast_ci_upper_amps is 'amperes (A), per conductor: upper edge (95%) of the empirical residual-quantile band around forecast_amps.';
comment on column public.day_ahead_forecast.band_source is 'none (category): where the band came from, test-split (hashed TEST-split artifact, the launch band) or live-rolling (the forecast own recent misses against the live outcome).';
comment on column public.day_ahead_forecast.band_n is 'count: number of residuals behind the band.';
comment on column public.day_ahead_forecast.band_pairs_through is 'UTC timestamp: valid_time of the newest live pair behind a live-rolling band; NULL for a test-split band.';
comment on column public.day_ahead_forecast.band_artifact_sha256 is 'none (identifier): lowercase hex sha256 of the TEST band artifact file; always recorded because the TEST artifact is the fallback band.';
comment on column public.day_ahead_forecast.forecast_method is 'none (label): forecast method; always ml_cooling_corrected. No substitute method is ever published.';
comment on column public.day_ahead_forecast.cooling_model_sha256 is 'none (identifier): lowercase hex sha256 of the cooling model file the value came from, verified before it was loaded.';
comment on column public.day_ahead_forecast.cooling_model_source is 'none (category): refit when the city serves a production-conductor refit model, frozen when it serves the frozen shadow model.';
comment on column public.day_ahead_forecast.anchor_observation_time is 'UTC timestamp: time of the station observation (the "now" reading) the correction used; it can be hours before valid_time.';
comment on column public.day_ahead_forecast.anchor_source is 'none (label): provider that supplied the anchor observation (tceq or synoptic).';
comment on column public.day_ahead_forecast.label is 'none (label): day-ahead-24h; engineering-selection; not-validated. States that this is a higher-error, engineering-selected, not-validated forecast.';
comment on column public.day_ahead_forecast.config_version is 'none (label): human-readable label of the rating assumption set (config.RATING_CONFIG_VERSION).';
comment on column public.day_ahead_forecast.config_fingerprint is 'none (identifier): lowercase hex sha256 of the canonical JSON of the city rating assumptions (supabase_store.rating_config_fingerprint); the same identity the rating rows carry.';
comment on column public.day_ahead_forecast.run_id is 'none (identifier): workflow run id (GITHUB_RUN_ID) that issued the row.';
comment on column public.day_ahead_forecast.run_attempt is 'count: workflow run attempt number.';
comment on column public.day_ahead_forecast.pipeline_version is 'none (identifier): short git commit of the pipeline code.';
comment on column public.day_ahead_forecast.schema_version is 'none (version): day_ahead_forecast row schema version.';
comment on column public.day_ahead_forecast.first_written_at is 'UTC timestamp: when the row was inserted. Never changes; rows are never rewritten.';

comment on column public.pipeline_run.day_ahead is 'none (json): per-city day-ahead outcomes of the run (outcome, due and issued targets, band source, duration) and redacted reasons. Operational, never public.';
