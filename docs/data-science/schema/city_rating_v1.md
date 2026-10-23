# City Rating Store: public.city_rating, Schema v1

**Schema version:** v1
**Date:** 2026-10-23
**Status:** decided contract (DS decision authority, REQUIREMENTS.md); values are PROVISIONAL (see "Provisional label (OD-5)")
**Scope:** `public.city_rating` in the production Supabase Postgres, written hourly by the production pipeline. Migrations: `supabase/migrations/20261019000000_create_city_rating.sql` (tables, writer role, policies) and `supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql` (hour check evaluated in UTC in every session, run-log comments). This document also describes `public.pipeline_run`, the operational run log, which consumers do not read.

**Read this first.** Every value in this table is a provisional estimate, not a verified line limit. The ratings come from the IEEE 738 thermal model at one rating point per city, with owner-supplied static ratings divided by an assumed subconductor count and assumed line bearings. Show the label (`rating_basis`) wherever a value is shown. Phase 3's go/no-go on real data was a NO-GO; the owner decided on 2026-10-21 to publish provisional rows anyway. No row, backfill included, has passed a go/no-go.

## Where the data lives

- A Supabase-hosted Postgres database, table `public.city_rating`: one row per city per hour.
- Rows are written by `dlr_orchestrator --store postgres` (the scheduled runner arrives in Phase 5) and, for history, by the one-time backfill loader (see "Backfill rows").
- Consumers read the table through Supabase's REST API once Phase 6 grants SELECT to the `anon` role on the table and adds the `latest_rating` view. Until Phase 6 delivers that, no consumer role has any access to the table (OD-6). Nothing in this document says Phase 5 or Phase 6 is already live.
- No connection details (host, project reference, key, URL) are published in this repository's docs. The owner hands them to the teams that need them.
- The full history will be public by owner decision (OD-6), so no column holds anything sensitive: no file path, no credential, no error text.

## Key and time semantics

There are four distinct times on a row. Do not confuse them.

| Time | Column | Meaning |
|---|---|---|
| Slot | `valid_time` | The hour the row is for: the hour-truncated UTC slot of the run window end (OD-7). Part of the primary key. |
| Weather | `observation_time` | The weather hour actually rated. It can be older than `valid_time` when the newest observation lags. NULL when unknown (see the column table). |
| First write | `first_written_at` | When the row was first inserted. It never changes after insert. |
| Last write | `computed_at` | When the row was last written. It changes every time the same key is rewritten. |

Rules:

- `(city, valid_time)` is unique. `valid_time` is always on a whole UTC hour (the table rejects anything else).
- The slot is the hour floor of the run end, never a rounding: a run at 14:07Z and a retry at 14:12Z both write 14:00Z; a run at 14:59Z also writes 14:00Z.
- A live retry within the same hour overwrites the row for that slot: values and `computed_at` change, `first_written_at` does not.
- A backfill never overwrites an existing row.
- The offline CSV archive from Phase 2 keeps the first write for an exact instant. The production store keeps the last write for the hour. This is a deliberate difference; the CSV is the offline store (tests, backfill source), not the production store.
- Rows of different cities at the same `valid_time` are independent. Never combine, minimise or otherwise reduce across cities: there is no corridor minimum and no bottleneck value.

## Columns: public.city_rating

Columns are listed in migration order. "NULL when" says when the column is empty; "never" means the table forbids NULL.

| Column | Type | Unit | NULL when | Meaning |
|---|---|---|---|---|
| `city` | `text` | none | never | City key, one of `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`. Part of the primary key. |
| `valid_time` | `timestamptz` | UTC instant | never | Hour-truncated UTC slot of the run end (OD-7). Part of the primary key. |
| `observation_time` | `timestamptz` | UTC instant | exhausted rows; rows from a provider with no per-field timing; backfill rows | The weather hour the composer aligned the observation to; may be older than `valid_time`. |
| `rating_amps` | `double precision` | A, per conductor | never | The dynamic line rating after the safety gates, or the static rating when `status` is `fallback`. Always finite and positive. |
| `rating_mw` | `double precision` | MW | never | Three-phase real power from `rating_amps`, `line_voltage_kv` and `power_factor` (see "Reading rules for consumers"). |
| `static_rating_amps` | `double precision` | A, per conductor | never | The owner-supplied static rating for the city (provisional). |
| `static_rating_mw` | `double precision` | MW | never | The same conversion applied to `static_rating_amps`. |
| `line_voltage_kv` | `double precision` | kV | never | Line voltage used for the MW conversion. |
| `power_factor` | `double precision` | dimensionless | never | Power factor used for the MW conversion. |
| `status` | `text` | none (category) | never | `ok` when the computed rating passed every gate; `fallback` when the static rating was published. |
| `fallback` | `boolean` | none (flag) | never | True when the published rating is the static fallback rating. |
| `fallback_gates` | `text[]` | none (labels) | never (empty array when no gate fired; also empty on backfill rows) | Sorted, de-duplicated first token of each alert, for example `G4`, `EXHAUSTED`. |
| `alerts` | `text[]` | none (text) | never (empty array when none; also empty on backfill rows) | The safety-gate alert messages of the run. |
| `exhausted` | `boolean` | none (flag) | never | True when every candidate weather station was exhausted and no observation exists. |
| `station_id` | `text` | none (identifier) | exhausted rows; backfill rows | The weather station that supplied the observation. |
| `candidates_probed` | `integer` | count | backfill rows | Number of candidate stations probed. |
| `probe_trail` | `jsonb` | none (json) | backfill rows | One entry per probed station: `stid`, `lat`, `lon`, `distance_km`, `outcome`. |
| `air_temp_c` | `double precision` | degC | exhausted rows; a missing reading | Air temperature of the observation. |
| `wind_perp_ms` | `double precision` | m/s | exhausted rows; a missing reading | Wind component perpendicular to the line: the wind the thermal model used. The CSV archive calls it `wind_speed`. |
| `wind_speed_ms` | `double precision` | m/s | exhausted rows; backfill rows | Measured wind speed before projection onto the line. |
| `wind_direction_deg` | `double precision` | degrees | exhausted rows; backfill rows | Meteorological direction the wind comes from. |
| `solar_radiation_wm2` | `double precision` | W/m2 | exhausted rows; a missing reading | Solar radiation of the observation. |
| `temp_source` | `text` | none (label) | non-composed provider; exhausted rows; backfill rows | Provider that supplied the air temperature. |
| `wind_source` | `text` | none (label) | non-composed provider; exhausted rows; backfill rows | Provider that supplied the wind. |
| `solar_source` | `text` | none (label) | non-composed provider; exhausted rows; backfill rows | Provider that supplied the solar radiation. |
| `forecast_method` | `text` | none (label) | not recorded | Forecast method requested for the run: `naive`, `ewm` or `ml`. Backfill rows carry the Phase 3 run's method. |
| `forecast_status` | `text` | none (category) | backfill rows | `ok`, `cold_start` or `failed` (see "Forecast fields"). |
| `forecast_amps` | `double precision` | A, per conductor | cold start; failed forecast; backfill rows | One-step-ahead forecast of the rating. |
| `forecast_ci_lower_amps` | `double precision` | A, per conductor | cold start; failed forecast; backfill rows | Lower edge of the empirical forecast band. |
| `forecast_ci_upper_amps` | `double precision` | A, per conductor | cold start; failed forecast; backfill rows | Upper edge of the empirical forecast band. |
| `forecast_horizon_min` | `double precision` | minutes | cold start; failed forecast; backfill rows | Forecast horizon (60). |
| `forecast_n_observations` | `integer` | count | cold start; failed forecast; backfill rows | History observations the forecast used. |
| `forecast_used_by_g6` | `boolean` | none (flag) | backfill rows | True when the forecast fed the G6 detector this run. |
| `detector_signal` | `text` | none (label) | backfill rows | The anomaly detector signal of the run. |
| `detector_model_loaded` | `boolean` | none (flag) | backfill rows | True when a trained anomaly model was loaded. The model path is never stored. |
| `history_rows` | `integer` | count | backfill rows | History rows read before cleaning. |
| `usable_history_rows` | `integer` | count | backfill rows | History rows left usable after cleaning. |
| `rating_basis` | `text` | none (text) | never | The provisional label (OD-5): what the values are and are not. |
| `config_version` | `text` | none (label) | never | Human label of the rating assumption set (DB-06). |
| `config_fingerprint` | `text` | none (identifier) | never | Lowercase hex sha256 of the city's rating assumptions (DB-06). |
| `forecast_model_sha256` | `text` | none (identifier) | method without an artifact (`naive`, `ewm`); cold start or failed forecast | sha256 of the forecast model file the run loaded (DB-06). |
| `anomaly_model_sha256` | `text` | none (identifier) | no anomaly model loaded | sha256 of the anomaly model file the run loaded (DB-06). |
| `origin` | `text` | none (category) | never | `live` for pipeline rows, `backfill` for rows loaded from the Phase 3 archive. |
| `run_id` | `text` | none (identifier) | not recorded (live rows always carry one) | Workflow run id that wrote the row; `local-<UTC time>-<id>` for a direct run outside a workflow; `backfill-<sha12>` for backfill rows. |
| `run_attempt` | `integer` | count | not recorded (live rows always carry one) | Workflow run attempt number (1 outside a workflow). |
| `pipeline_version` | `text` | none (identifier) | not recorded | Short git commit of the pipeline code (`unknown` when it cannot be read). |
| `schema_version` | `integer` | none (version) | never | Row schema version (1). |
| `first_written_at` | `timestamptz` | UTC instant | never | When the row was first inserted. Never changes. |
| `computed_at` | `timestamptz` | UTC instant | never | When the row was last written. Changes on every rewrite. |

## What fallback means

- `status` is `ok` when the computed rating passed every safety gate. It is `fallback` when a gate failed or no observation could be obtained; in that case the published `rating_amps` is the city's static rating (`static_rating_amps`) and `fallback` is true.
- `alerts` holds the gate messages, for example `G4 FAIL (implausible (1080 A)) — fallback rating 1825 A`. `fallback_gates` holds the first token of each alert, sorted and de-duplicated. Tokens are `G1` to `G6` and `EXHAUSTED`. Gate G5 is disabled on this path and never appears.
- `exhausted` means no usable weather station was found for the run. `exhausted` implies `fallback`, but `fallback` does not imply `exhausted`: a gate can also force a fallback while an observation exists.
- A fallback row is still a fresh row. It was written for its `valid_time` and counts toward freshness; it simply publishes the static rating.
- A city that fails outright (the pipeline raises) writes no row at all; that is not a fallback (see "Freshness and failures").

## Provisional label (OD-5)

Every row carries the label in `rating_basis`. The current live label is:

> Per-conductor amperes from the IEEE 738 thermal model at one rating point per city. Static ratings are owner-supplied 345 kV bundle averages divided by an assumed subconductor count; line bearings are assumed, not measured. Not a verified equipment-limited circuit rating. Values are provisional until Phase 7's re-validation go (REVAL-01) lifts this label.

The current assumption-set label is `v1-provisional-2026-10-13` (that is `config.RATING_CONFIG_VERSION`). It is bumped by people whenever any rating assumption changes, every per-city conductor parameter included. The fingerprint (next section) changes automatically; the version is its human-readable label.

Rules for consumers:

- Display the label wherever a value is shown. Do not drop the static-rating caveat or the line-bearing caveat.
- Every row, live or backfill, stays provisional until Phase 7's re-validation go (REVAL-01) lifts the label.
- Phase 3's go/no-go on real data was a NO-GO and stays recorded as written in `docs/data-science/decisions/real_data_validation.md`. On 2026-10-21 the owner decided to publish provisional rows anyway, so Phases 4 to 6 are not blocked by it. Never describe any row, the backfill included, as having passed a go/no-go.

## What produced each row (DB-06)

Four columns say what produced a row, so a change in configuration or model is visible in the data without any schema change.

- `config_version`: the human label of the rating assumption set. People bump it.
- `config_fingerprint`: the authoritative identity, computed automatically. It is the sha256 of the canonical JSON of the city's rating assumptions: every conductor parameter (diameter, AC resistance and its temperature coefficient, emissivity, absorptivity, maximum operating temperature, elevation, line azimuth), the rating point's coordinate, the static rating, the plausibility bounds, the line bearing, the subconductors per phase, line voltage, power factor, the G6 control limit and the forecast and detector parameters. It is computed per city, so a change that touches one city changes only that city's fingerprint.
- `forecast_model_sha256`: the sha256 of the forecast model file the run loaded. NULL when the forecast method has no artifact (`forecast_method` then names it, for example `naive` or `ewm`), or when no forecast was produced.
- `anomaly_model_sha256`: the sha256 of the anomaly model file the run loaded. NULL when none was loaded.

Backfill rows carry the values of the Phase 3 run: fingerprints computed on the code at the Phase 3 manifest's commit and model hashes from that manifest.

For consumers: within one city, a change in `config_fingerprint`, `forecast_model_sha256` or `anomaly_model_sha256` between rows marks a configuration or model change. The web app should mark such a change on charts and tables, and PSS/E studies should not splice values across it without noting it. Phase 7's per-city conductors (COND-01) and any change of forecast method or model (SEL-04) arrive this way, as new values in these same columns, never as a schema change.

## Freshness and failures

- Cadence is hourly (OD-1): one row per city per hour once Phase 5's scheduled runner is live.
- The target is that the newest `valid_time` of each city is no older than 90 minutes (OD-4), once Phase 5 runs. Before Phase 5 delivers the schedule, rows appear only when someone runs the pipeline.
- A city that fails outright writes no row (OD-9), so its newest row ages and the freshness check flags it. A consumer sees the gap as an old latest row, not as an error row.
- Run outcomes, including per-city failures, go to `public.pipeline_run`. That table is an operational log; consumers never read it.

## Forecast fields

- `forecast_amps` is a one-step-ahead forecast of the rating with a 60-minute horizon (`forecast_horizon_min`), and `forecast_ci_lower_amps` / `forecast_ci_upper_amps` are an empirical band from out-of-sample walk-forward residuals.
- `forecast_status` is `ok` when a forecast was computed (even if the gap guard from Phase 2 or a zero-width band kept it from G6; see `forecast_used_by_g6`), `cold_start` when there was too little history, and `failed` when the forecast raised (for example a missing ML model) or when the city's history could not be cleaned, so the forecast ran on no history although the city had history rows; the detector then reports a cold start (`detector_signal`). It is NULL on backfill rows.
- `forecast_used_by_g6` says whether the forecast fed the G6 detector in that run.
- Cold start in production: the backfill window ends on 2026-09-28 and the read window is the last 30 days (OD-8). Phase 2's gap guard withholds a forecast after more than one missing hour. So after go-live the forecast and the detector rebuild from live hours: the `ml` method needs 7 consecutive hours of history, and the rolling detector baseline needs 24 usable rows. Until then expect `forecast_status` of `cold_start` and empty forecast columns.

## Backfill rows

- The Phase 3 real-data archive is loaded once with origin `backfill`. The window comes from the Phase 3 manifest (2026-09-08T00:00Z to 2026-09-28T23:00Z), 504 hourly rows per city. `run_id` is `backfill-<sha12>` (the first 12 hex characters of the archive's sha256).
- They are labelled provisional: `config_version` is `v1-provisional-2026-10-13` and `rating_basis` starts with `PROVISIONAL (OD-5)`, names the Phase 3 window and commit and the single Drake conductor used for every city, and ends with REVAL-01. They stay provisional until Phase 7's re-validation go (REVAL-01). Phase 3's go/no-go was a NO-GO; these rows have not passed it.
- Their identity columns come from the Phase 3 run (see "What produced each row (DB-06)"), and `forecast_method` is the method Phase 3 used.
- Columns that are NULL or empty on a backfill row, because the archive does not hold them: `observation_time`, `station_id`, `candidates_probed`, `probe_trail`, `wind_speed_ms`, `wind_direction_deg`, the three `*_source` columns, `forecast_status`, all `forecast_*` values, `forecast_used_by_g6`, `detector_signal`, `detector_model_loaded`, `history_rows` and `usable_history_rows`. `fallback_gates` and `alerts` are empty, so a backfill row with status `fallback` does not say which gate fired.
- A backfill never overwrites an existing row: a live row at the same `(city, valid_time)` keeps its values and its origin.

## Reading rules for consumers

- Rows carry no implicit order. Always order by `valid_time` explicitly.
- Never reduce across cities (no minimum, no sum, no bottleneck). Each city row is an independent point.
- Timestamps are UTC instants (`timestamptz`); the REST API returns them with an offset. Convert to local time in the client.
- Treat added columns as additive: ignore columns you do not know.
- MW: `rating_mw` = sqrt(3) x `line_voltage_kv` x `rating_amps` x `power_factor` / 1000, computed by `ercot_dlr_merger.amps_to_mw`. The voltage (345.0 kV) and power factor (0.95) are stored on each row, so a row is self-describing.
- A reader sees a whole row, old or new, never a mix of both.
- The current slot's row can be rewritten by a retry within its hour: `computed_at` changes, `first_written_at` does not. Do not treat a changed value in the current hour as an error.
- Show the provisional label (`rating_basis`) with every value, and mark changes in the identity columns (see "What produced each row (DB-06)").

## Run log: public.pipeline_run (operational, not for consumers)

One row per run, written by the scheduled runner (Phase 5) or by a direct `--store postgres` run. Consumers have no access to it and should not build on it. It exists so a failed city, which has no rating row, still leaves a record.

| Column | Type | Meaning |
|---|---|---|
| `run_id` | `text` | Workflow run id. Primary key. |
| `run_attempt` | `integer` | Workflow run attempt number. |
| `started_at` | `timestamptz` | When the run row was created. |
| `finished_at` | `timestamptz` | When the run finished. |
| `window_end` | `timestamptz` | End of the run's weather window. |
| `provider` | `text` | Weather provider mode of the run. |
| `forecast_method` | `text` | Forecast method of the run. |
| `pipeline_version` | `text` | Short git commit of the pipeline code. |
| `cities_ok` | `text[]` | Cities whose rating row was written healthily. |
| `cities_failed` | `jsonb` | City to outcome (`error` or `degraded`), whether a row was written, and redacted error text. |
| `provider_errors` | `jsonb` | Provider error summary of the run. |
| `sources` | `jsonb` | Count of weather sources used per field. |

A city written while its history could not be cleaned is `degraded`, with the redacted cleaning error (`data cleaning failed: ...`) in `cities_failed`; it is not in `cities_ok`.

## Versioning

- v1 is additive-only: columns may be added; none is renamed or removed, and none changes meaning.
- A rename, removal or change of meaning needs a new migration and a v2 document.
- A configuration, model or forecast-method change is not a schema change; it shows up in the identity columns (see "What produced each row (DB-06)").
- Evidence of the live checks (migration applied, writer smoke test, backfill parity) lives in `docs/data-science/decisions/supabase_store/`, written by plan 04-06 and, after the review-fix migration, plan 04-12 (`smoke_review_fixes.json`, `smoke_actions_review_fixes.json`).
