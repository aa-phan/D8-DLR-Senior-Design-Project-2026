# Day-Ahead Forecast Store: public.day_ahead_forecast, Schema v1

**Schema version:** v1
**Date:** 2026-11-08
**Label:** day-ahead-24h; engineering-selection; not-validated
**Status:** decided contract (DS decision authority); values are an owner-selected engineering estimate, not validated, with no safety role
**Scope:** `public.day_ahead_forecast`, written by the hourly production pipeline, and its two read-only views `public.day_ahead_upcoming` and `public.day_ahead_status`. Migrations: `supabase/migrations/20261108120000_day_ahead_forecast_store.sql` (the table) and `supabase/migrations/20261108120100_expose_day_ahead_forecast.sql` (the views, the public read grant and the alarm clause). The way to read all of it from a client is [`rest-api.md`](../../integration/rest-api.md).

## What it is

A 24-hour-ahead forecast of the ampacity of each project city, one value for each 00, 06, 12 and 18 UTC hour, with a 5-95% band. In the owner's words, which every row's `label` points back to:

A 24-hour-ahead estimate from ml_cooling_corrected. It has more error than the 60-minute forecast because it looks further ahead. On past data (TEST window, Mar-Sep 2026) its typical error was about 23 A (~1.7% of rating) larger. It is the owner's engineering choice, not picked by the signed selection rule, and it never sets or checks the live rating.

- **Label:** every row carries `day-ahead-24h; engineering-selection; not-validated`. Show it wherever you show a value.
- **No safety role.** It is information for planning. It never replaces, sets, checks or gates the hourly rating in `city_rating`, and the 60-minute forecast that gates the safety checks is a different field of a different table.
- **Not validated.** It is the owner's labelled engineering selection. The signed selection rule did not pick it, so no go/no-go covers it.
- **Where the "about 23 A" comes from.** The horizon comparison on the TEST window (2026-03-18 to 2026-09-29, 784 six-hourly slots per city) found the typical error of the day-ahead method about 23 A (about 1.7% of the rating) larger than the live 60-minute forecast, similar in every city (18 to 28 A). That comparison was exploratory, not pre-registered, and it used reanalysis as truth: see the [horizon comparison report (exploratory)](../exploratory/2026-11-02_horizon_comparison/REPORT.md) (`docs/data-science/exploratory/2026-11-02_horizon_comparison/REPORT.md`). The figures describe past data. They are not a promise about future error.
- **Out-of-range values are published as computed.** The live rating falls back to the city's static rating when a computed value is outside its plausibility bounds. The day-ahead value never falls back: if the computed value is outside the rating bounds it is still published, and the pipeline logs a warning. On the first live run, two MIDLAND values were below the lower bound of 1250 A. They were published, not withheld. Judge a value by its band and its label, not by the live rating's bounds.

## Where the data lives

- A Supabase-hosted Postgres database: the table `public.day_ahead_forecast` (one row per city per target hour) and two views, `public.day_ahead_upcoming` (the future targets) and `public.day_ahead_status` (is the feed on time).
- Read-only access is through Supabase's REST API with the publishable key; the contract is [`rest-api.md`](../../integration/rest-api.md). The read grant (SELECT for `anon`) takes effect when the owner applies the expose migration `20261108120100_expose_day_ahead_forecast.sql`; until then the objects are not readable with the publishable key. Nothing in this document says the migration is already applied.
- The full history stays readable in the table (OD-6, public by owner decision): a target that has passed leaves the upcoming view but not the table.
- No connection details (host, project reference, key, URL) are in this repository. The owner hands them to the teams that need them.
- Writes are refused for every consumer. The writer role can insert a row and never update or delete it, so an issued value is never rewritten (first write wins).

## Columns: public.day_ahead_forecast

Columns are listed in table order. No column is ever empty except `band_pairs_through`, which is NULL while the band is the launch band.

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `city` | text | none (identifier) | City key: `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND` or `EL_PASO`. Part of the primary key. |
| `valid_time` | timestamptz | UTC instant | The target hour the forecast is for, always 00, 06, 12 or 18 UTC. Part of the primary key. |
| `issued_at` | timestamptz | UTC instant | When the run that issued the row decided to issue it, always before `valid_time`. A catch-up issue carries a later value than the first chance, so a late value is visible. |
| `forecast_run_init_time` | timestamptz | UTC instant | The start time of the weather run behind the value, exactly 24 hours before `valid_time`. The 24 hours are the age of this weather run, not the time from `issued_at`. |
| `horizon_minutes` | integer | minutes | The age of the weather run at `valid_time`; always 1440. |
| `forecast_amps` | double precision | A, per conductor | The day-ahead ampacity forecast for `valid_time` under the city's production conductor. Not validated. |
| `forecast_ci_lower_amps` | double precision | A, per conductor | Lower edge (5%) of the empirical band around `forecast_amps`. |
| `forecast_ci_upper_amps` | double precision | A, per conductor | Upper edge (95%) of the empirical band around `forecast_amps`. |
| `band_source` | text | none (category) | `test-split` (the launch band from the hashed TEST-split artifact) or `live-rolling` (the forecast's own recent misses against the live outcome). See "Uncertainty band". |
| `band_n` | integer | count | How many residuals are behind the band. |
| `band_pairs_through` | timestamptz | UTC instant | The `valid_time` of the newest live pair behind a `live-rolling` band; NULL for a `test-split` band. |
| `band_artifact_sha256` | text | none (identifier) | sha256 of the TEST band artifact file. Always recorded, because the TEST band is the fallback. |
| `forecast_method` | text | none (label) | Always `ml_cooling_corrected`. No other method is ever published in this table. |
| `cooling_model_sha256` | text | none (identifier) | sha256 of the cooling model file the value came from. |
| `cooling_model_source` | text | none (category) | `refit` when the city serves a refit model for its production conductor, `frozen` when it serves the frozen shadow model. |
| `anchor_observation_time` | timestamptz | UTC instant | The time of the station observation (the "now" reading) the correction used. It can be hours before `valid_time`. |
| `anchor_source` | text | none (label) | The provider that supplied the anchor observation (`tceq` or `synoptic`). |
| `label` | text | none (label) | `day-ahead-24h; engineering-selection; not-validated`. |
| `config_version` | text | none (label) | Human-readable label of the rating assumption set. |
| `config_fingerprint` | text | none (identifier) | Automatic identity of the city's rating assumptions, the same identity the rating rows carry. |
| `run_id` | text | none (identifier) | The workflow run that issued the row. |
| `run_attempt` | integer | count | The attempt number of that workflow run. |
| `pipeline_version` | text | none (identifier) | Short git commit of the pipeline code. |
| `schema_version` | integer | version | The row schema version; 1 here. |
| `first_written_at` | timestamptz | UTC instant | When the row was inserted. It never changes, because rows are never rewritten. |

## Views

- **`public.day_ahead_upcoming`** has the 25 columns above in the same order, plus `lead_minutes` (integer, minutes, rounded up) last: the time from your request to `valid_time`. It lists every future target that has a value, ordered by city and then `valid_time`. Targets that have passed are not in the view; they stay in the table.
- **`public.day_ahead_status`** has seven columns and always four rows, one per city: `city`, `checked_at` (the moment of your request), `next_target_time` (the first 00, 06, 12 or 18 UTC instant after `checked_at`), `upcoming_count` (future values stored for the city), `newest_issued_at` (the newest `issued_at` of the city, NULL when it has none), `missing_targets` (a `timestamptz[]` of targets due within the next 12 hours that have no value) and `is_late`. The column tables are in [`rest-api.md`](../../integration/rest-api.md).
- Both views run with the caller's rights and are read-only.

## When values appear

- Targets are the 00, 06, 12 and 18 UTC hours. A target is due from about 18 hours before it until the target itself, and the hourly job issues it as soon as it is due. The first run after go-live wrote up to 3 targets per city; afterwards a normal run writes one new target per city.
- Catch-up: the hourly job tries again every hour, so a target missed by one run is issued by the next, and `issued_at` shows the later time. A target that has passed is never filled afterwards: it stays empty.
- **"24 h" is the age of the weather run, not how early you get the value.** The weather run starts exactly 24 hours before the target (`forecast_run_init_time`), but the weather run is only available some hours after it starts, so a value is issued 0 to 18 hours before its target. `issued_at`, `forecast_run_init_time` and `anchor_observation_time` let you compute both leads for each row.
- The anchor reading (`anchor_observation_time`) is a real station observation. In the TEST comparison it was 24 hours ahead of the target; in the shadow it was about 12 hours ahead; in live use it is up to 18 hours ahead. A value issued closer to its target uses a fresher anchor, so the error figures in the report describe the TEST case and are not an estimate for every row.

## Uncertainty band

- The band is the 5-95% range of how far past forecasts missed the truth (empirical residual quantiles), one band for each city and each target hour: 16 bands (4 cities, 4 hours). It is never a mean plus or minus a multiple of the spread.
- **At launch** every band comes from the TEST split of 2026-03-18 to 2026-09-29: `band_source` is `test-split`, `band_n` is the number of residuals, and `band_artifact_sha256` identifies the file. These residuals were measured against reanalysis truth with a 24 h anchor, not against the rating the pipeline publishes.
- **Live bands.** A band switches on its own to `live-rolling` once 60 graded pairs exist for its city and target hour, using the newest 120, and only when the live band brackets the value (the 5% offset is below zero and the 95% offset above it). Otherwise it keeps the TEST band. A pair is the day-ahead value and the published live rating of the same city and hour, so the live band is measured against the station-composed rating, not against reanalysis. Hours where the live rating was the static fallback are left out. `band_pairs_through` gives the newest pair's `valid_time`.
- The two measurements differ, so a live band can be narrower or wider than the launch band. Do not read a change of `band_source` as a change in the forecast model.

## Stall flag and alarm

- **The late rule (12 hours):** a target due within the next 12 hours that has no value marks the city late, once the feed has its first value. The flag is armed by the first value, so a table that has never been written cannot raise a false alarm.
- `day_ahead_status.is_late` is true when `missing_targets` is not empty and the table holds at least one row. `missing_targets` lists the exact targets.
- The owner's permanent alarm, `rpc/assert_fresh` (see [`rest-api.md`](../../integration/rest-api.md)), reads the same rule: the same alarm URL fails with a detail `day_ahead_late=CITY@UTC-time` for a stalled day-ahead feed, and its 200 body has `day_ahead_armed`. There is no separate alarm job.

## Identity and label

- `cooling_model_sha256` and `cooling_model_source` say which model file produced a value; `config_fingerprint` and `config_version` say which assumptions; `run_id`, `run_attempt` and `pipeline_version` say which run and which code. Within one city, a change in these between rows marks a model or configuration change, so do not splice values across it without noting it.
- Amperes only. No MW column is stored. To convert, use the same formula as for `city_rating`: three-phase real power from the amperes, the line voltage (`line_voltage_kv` in the rating rows) and the power factor (`power_factor` in the rating rows): MW = sqrt(3) x kV x A x power factor / 1000.
- `label` is the same on every row. If you show a value, show the label.

## Run log: pipeline_run.day_ahead (operational, not for consumers)

The run log row of the hourly job has a private `day_ahead` column with the per-city outcome of the day-ahead stage (what was due, what was issued, the band source, the duration, a redacted reason). The publishable key cannot read it, and it is not part of this contract.

## Versioning

- Columns may be appended after the last one, never renamed or dropped. Ignore columns you do not know.
- A change to a column, to the meaning of a value or to a rule above is a new migration and a revision of this contract.
- The Python twin of the column lists is `backend/day_ahead_contract.py`; a test fails if the table, the views or these documents drift from it.
