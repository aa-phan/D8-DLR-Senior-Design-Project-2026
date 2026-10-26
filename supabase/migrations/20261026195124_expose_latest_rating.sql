-- supabase/migrations/20261026195124_expose_latest_rating.sql
--
-- Production-pipeline Phase 6 (API-01, OD-6; D-01..D-05): expose the ratings read-only.
--
-- Creates:
--   index  city_rating_city_valid_desc_idx   newest-row-per-city lookups on public.city_rating
--   view   public.latest_rating              one row per city, the newest city_rating row by
--                                            valid_time (fallback rows included, D-04), with 34
--                                            published columns: 27 planned, 4 identity and source
--                                            columns (D-01), and 3 computed ones (D-02, D-03)
-- Changes privileges (OD-6):
--   anon and authenticated lose every privilege on every public table and sequence, then get
--   SELECT on public.city_rating and public.latest_rating only. Writes are refused by privilege,
--   not only blocked by row-level security. public.pipeline_run (the run log) stays private.
-- Adds the read policy city_rating_public_read on public.city_rating.
--
-- Additive: it never edits 20261019000000_create_city_rating.sql or
-- 20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql (both are applied to the
-- live project and pinned by sha256).
--
-- Idempotent: the index and view are created only if absent or replaced, the policy is dropped
-- before it is created, and the revokes and grants leave the same result when run twice.
--
-- Applied with `supabase db push --db-url ...` by the owner (plan 06-09). It adds no role and
-- no credential.
--
-- Why the view runs with the caller's rights: a Supabase view is created by the postgres role
-- and, by default, reads its tables with that role's rights, which skips row-level security
-- for every request. security_invoker = true makes the view read city_rating as the role that
-- asks (anon through the public API), so the read policy below is what decides who sees rows.
--
-- The column list is one-way (D-01..D-03): consumers code against these names, so a name is
-- never renamed or dropped, and a column is only ever appended after the last one. The Python
-- twin is backend/latest_rating_contract.py and a test fails if the two differ.

-- Newest row per city: the view orders by (city, valid_time desc).
create index if not exists city_rating_city_valid_desc_idx on public.city_rating (city, valid_time desc);

-- D-04: no status filter, so a newer fallback row wins over an older computed one.
-- D-02: is_stale is a direct timestamp comparison, never derived from the rounded age_minutes;
--       age_minutes is rounded UP so that age_minutes > 90 is exactly is_stale.
-- D-03 (revised 2026-10-25): is_provisional looks for the word in rating_basis OR config_version.
--       Live rows begin "Per-conductor amperes ..." and only backfill rows begin with the OD-5
--       prefix, so a prefix test would read every live row as final.
create or replace view public.latest_rating with (security_invoker = true) as
select distinct on (city)
    city,
    valid_time,
    observation_time,
    rating_amps,
    rating_mw,
    static_rating_amps,
    static_rating_mw,
    line_voltage_kv,
    power_factor,
    status,
    fallback,
    fallback_gates,
    alerts,
    exhausted,
    forecast_method,
    forecast_status,
    forecast_amps,
    forecast_ci_lower_amps,
    forecast_ci_upper_amps,
    forecast_horizon_min,
    detector_signal,
    rating_basis,
    config_version,
    origin,
    run_id,
    pipeline_version,
    computed_at,
    config_fingerprint,
    forecast_model_sha256,
    anomaly_model_sha256,
    solar_source,
    ceil(extract(epoch from (now() - valid_time)) / 60)::integer as age_minutes,
    (valid_time < now() - interval '90 minutes') as is_stale,
    (position('provisional' in lower(rating_basis)) > 0
        or position('provisional' in lower(config_version)) > 0) as is_provisional
from public.city_rating
order by city, valid_time desc;

comment on view public.latest_rating is 'The newest city_rating row per city by valid_time, one row per city (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO); a fallback row counts like any other (D-04). All rating values are PROVISIONAL per rating_basis and config_version (OD-5). Rows arrive hourly (OD-1); a row is stale when valid_time is more than 90 minutes old (OD-4). A city that fails writes no row, so its last good row ages and is_stale turns true (OD-9). Read-only: the view runs with the caller''s rights.';

-- View comments do not inherit from the table, so every column is commented here.
comment on column public.latest_rating.city is 'none (identifier): upper-case project city key, one of AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO.';
comment on column public.latest_rating.valid_time is 'UTC instant: the hour-truncated UTC run slot of the run window end (OD-7). The newest slot for the city.';
comment on column public.latest_rating.observation_time is 'UTC instant: the weather hour the composer aligned the observation to; may be older than valid_time. NULL when unknown or exhausted.';
comment on column public.latest_rating.rating_amps is 'amperes (A), per conductor, PROVISIONAL (OD-5): the dynamic line rating after the safety gates, or the static fallback rating when status is fallback.';
comment on column public.latest_rating.rating_mw is 'megawatts (MW), three-phase real power, PROVISIONAL (OD-5): rating_amps converted with line_voltage_kv and power_factor.';
comment on column public.latest_rating.static_rating_amps is 'amperes (A), per conductor, PROVISIONAL (OD-5): the owner-supplied static rating for the city.';
comment on column public.latest_rating.static_rating_mw is 'megawatts (MW), three-phase real power, PROVISIONAL (OD-5): static_rating_amps converted with line_voltage_kv and power_factor.';
comment on column public.latest_rating.line_voltage_kv is 'kilovolts (kV): line voltage used for the MW conversion.';
comment on column public.latest_rating.power_factor is 'dimensionless: power factor used for the MW conversion.';
comment on column public.latest_rating.status is 'none (category): ok when the computed rating passed every gate, fallback when the static rating was used.';
comment on column public.latest_rating.fallback is 'none (flag): true when the rating is the static fallback rating.';
comment on column public.latest_rating.fallback_gates is 'none (labels): sorted, de-duplicated first token of each alert (for example G4, EXHAUSTED); empty when no gate fired.';
comment on column public.latest_rating.alerts is 'none (text): safety-gate alert messages of the run; empty array when there are none.';
comment on column public.latest_rating.exhausted is 'none (flag): true when every candidate weather station was exhausted and no observation exists.';
comment on column public.latest_rating.forecast_method is 'none (label): forecast method requested for the run (naive, ewm or ml).';
comment on column public.latest_rating.forecast_status is 'none (category): ok, cold_start or failed; NULL when not recorded.';
comment on column public.latest_rating.forecast_amps is 'amperes (A), per conductor, PROVISIONAL (OD-5): one-step-ahead forecast of the rating; NULL when no forecast was produced.';
comment on column public.latest_rating.forecast_ci_lower_amps is 'amperes (A), per conductor, PROVISIONAL (OD-5): lower edge of the forecast band.';
comment on column public.latest_rating.forecast_ci_upper_amps is 'amperes (A), per conductor, PROVISIONAL (OD-5): upper edge of the forecast band.';
comment on column public.latest_rating.forecast_horizon_min is 'minutes: forecast horizon.';
comment on column public.latest_rating.detector_signal is 'none (label): the anomaly detector signal of the run.';
comment on column public.latest_rating.rating_basis is 'none (text): provisional-label text stating what the values are and are not (OD-5).';
comment on column public.latest_rating.config_version is 'none (label): human-readable label of the rating assumption set (config.RATING_CONFIG_VERSION).';
comment on column public.latest_rating.origin is 'none (category): live for pipeline rows, backfill for rows loaded from the Phase 3 archive.';
comment on column public.latest_rating.run_id is 'none (identifier): workflow run id (GITHUB_RUN_ID) that wrote the row.';
comment on column public.latest_rating.pipeline_version is 'none (identifier): short git commit of the pipeline code.';
comment on column public.latest_rating.computed_at is 'UTC instant: when the row was last written; updated on every rewrite of the same key.';
comment on column public.latest_rating.config_fingerprint is 'none (identifier): lowercase hex sha256 of the canonical JSON of the city rating assumptions (conductor, point, static rating, bounds, bearing, subconductors, voltage, power factor, G6 and forecast parameters). It changes whenever any of them changes; config_version is its human-readable label.';
comment on column public.latest_rating.forecast_model_sha256 is 'none (identifier): sha256 of the forecast model file the run loaded; NULL when the forecast method has no artifact or no forecast was produced.';
comment on column public.latest_rating.anomaly_model_sha256 is 'none (identifier): sha256 of the anomaly model file the run loaded; NULL when none was loaded.';
comment on column public.latest_rating.solar_source is 'none (label): provider that supplied the solar radiation.';
comment on column public.latest_rating.age_minutes is 'minutes (whole, rounded up): from valid_time to the moment of the request; stale when greater than 90.';
comment on column public.latest_rating.is_stale is 'none (flag): true when valid_time is strictly more than 90 minutes before the request (OD-4); exactly 90 minutes is fresh; a stale row is the city last good row (OD-9).';
comment on column public.latest_rating.is_provisional is 'none (flag): true while rating_basis or config_version contains the word provisional (OD-5); false only after the Phase 7 re-validation go (REVAL-01) removes the word from both.';

-- Privileges (OD-6): privilege is the lock, row-level security the second lock. Until the
-- 2026-10-30 platform change a new public table is granted to anon, authenticated and
-- service_role in full, so every grant is stated and every other one is swept away.
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
grant select on public.city_rating, public.latest_rating to anon, authenticated;

-- Objects the postgres role creates later no longer arrive pre-granted to the API roles.
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;

-- Row-level security: the one read policy. No write policy exists for either role.
alter table public.city_rating enable row level security;
drop policy if exists city_rating_public_read on public.city_rating;
create policy city_rating_public_read on public.city_rating for select to anon, authenticated using (true);

-- Ask PostgREST to reload its schema cache so the new view is served at once.
notify pgrst, 'reload schema';
