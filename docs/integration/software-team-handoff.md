# Rating database: handoff to the Software team

**Audience:** the Software sub-team building the React dashboard (`frontend/`) and the Flask layer (`api/`).
**Owner of the data:** the Data Science sub-team. Questions, keys and access go to the Data Science owner, Aaron Phan.
**Contract this document routes to:** [`rest-api.md`](rest-api.md) (v1). Where this handoff and the contract disagree, the contract wins and this handoff is the bug.

The ratings are live: the public read path was checked on 2026-11-02, with four fresh rows returned through the publishable key (the "Promotion" section of [`real_data_validation_p7.md`](../data-science/decisions/real_data_validation_p7.md)). A Supabase Postgres database holds one dynamic line rating per city per hour for the four project cities (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`), and the dashboard can read it today over HTTPS with a read-only key. There is nothing to deploy on the Data Science side: ask for the two connection values, then call the REST endpoints below. This document gets you to a first working request, tells you which columns serve which dashboard view, and lists the rules that are easy to get wrong. Column-by-column definitions live in the contract, not here.

## Get access

1. **Ask the Data Science owner for two values:** `SUPABASE_URL` (the project URL) and `SUPABASE_PUBLISHABLE_KEY` (the publishable key). They are handed to each team directly and are never committed to this repository.
2. **Store them as environment variables** with exactly those names. The examples in [`examples/`](examples/) read them from the environment. Keep them out of git: put them in a git-ignored `.env` or your shell profile.
3. **Send the key in the `apikey` header only.** Never put it in an `Authorization` header or in the URL. The supabase-js client sets the header for you.

What the key can and cannot do:

| The publishable key | Result |
|---|---|
| Reads `latest_rating` (view) and `city_rating` (table) | Allowed |
| Calls `rpc/assert_fresh` | Allowed |
| Reads `day_ahead_upcoming` and `day_ahead_status` (views) and `day_ahead_forecast` (table) | Allowed |
| Inserts, updates or deletes anything | Refused by privilege (HTTP 401 or 403, code `42501`) |
| Reads the run log `pipeline_run` or the freshness log `ops.freshness_log` | Refused |

The key maps to Supabase's read-only `anon` role, and the full history is public by owner decision (OD-6 in the contract), so the key may ship in a browser bundle. Nobody on the Software team needs the secret key (`sb_secret_...`) or a `service_role` token; if you are handed one, do not use it. If the publishable key is exposed or retired, the Data Science owner issues a new one and you swap the environment variable; nothing else changes.

## First request

With the two variables set, this returns the current rating of every city:

```bash
curl -fsS "$SUPABASE_URL/rest/v1/latest_rating?select=city,valid_time,rating_amps,rating_mw,status,is_stale,is_provisional&order=city" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```

The same call in the dashboard, with `@supabase/supabase-js` version 2:

```js
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)
const { data, error } = await supabase
  .from('latest_rating')
  .select('city,valid_time,rating_amps,rating_mw,status,is_stale,is_provisional')
  .order('city')
```

Expect four rows, one per city. Complete, runnable versions, including history paging, are [`examples/curl.sh`](examples/curl.sh), [`examples/supabase_js.mjs`](examples/supabase_js.mjs) and [`examples/read_ratings.py`](examples/read_ratings.py). The table under "Examples" in the contract says how to run each.

## What you can read

| Object | Shape | Use it for |
|---|---|---|
| `latest_rating` | View. Always four rows, the newest row of each city, with 34 columns. | Anything that shows "now": the status page, current values, freshness badges. |
| `city_rating` | Table. One row per city per hour, every stored column. Backfill rows (`origin` = `backfill`) cover 2026-09-08 to 2026-09-28; live rows follow from go-live, so expect a gap between the two. | Charts and history: DLR against static over time, forecast bands, gate history, weather inputs. |
| `day_ahead_upcoming` | View. The day-ahead targets that are still to come, one row per city and per 00, 06, 12 and 18 UTC target that has been issued so far (at most three targets per city, because a value appears only about 18 hours before its target), with 26 columns. | The next-day panel: the expected current with its band and its label. |
| `day_ahead_status` | View. Always four rows, one per city, with 7 columns. | A feed status badge: on time or late, and which targets are missing. |
| `day_ahead_forecast` | Table. Every day-ahead value ever issued, one row per city and target, with 25 columns. | History of past day-ahead values, for example to compare them with what happened. |
| `rpc/assert_fresh` | Function. HTTP 200 when all four cities are fresh, HTTP 503 naming the stale or missing ones. | An optional health check. The Data Science owner already runs it as a permanent alarm. |

`latest_rating` carries three computed columns that `city_rating` does not: `age_minutes`, `is_stale` and `is_provisional`. `city_rating` also carries diagnostic columns that `latest_rating` leaves out:

- the weather inputs: `air_temp_c`, `wind_perp_ms`, `wind_speed_ms`, `wind_direction_deg`, `solar_radiation_wm2`;
- the station and its sources: `station_id`, `candidates_probed`, `probe_trail`, `temp_source`, `wind_source`;
- forecast and detector detail: `forecast_n_observations`, `forecast_used_by_g6`, `detector_model_loaded`;
- bookkeeping: `history_rows`, `usable_history_rows`, `run_attempt`, `schema_version`, `first_written_at`.

Full column lists, types, units and "NULL when" rules:

- `latest_rating`: the "`latest_rating` columns" table in [`rest-api.md`](rest-api.md).
- `city_rating`: the "Columns: public.city_rating" table in [`city_rating_v1.md`](../data-science/schema/city_rating_v1.md).

The database also documents itself: every column of both objects carries a comment with its unit and meaning, defined in [`supabase/migrations/`](../../supabase/migrations/).

## Dashboard views mapped to columns

This maps the component specs in [`docs/frontend/specs/`](../frontend/specs/) to columns. The meaning of each column is in the contract.

| Dashboard view | Read from | Columns |
|---|---|---|
| Line status (F3) | `latest_rating` | `city`, `rating_amps`, `rating_mw`, `static_rating_amps`, `static_rating_mw`, `status`, `valid_time`, `observation_time`, `age_minutes`, `is_stale`, `rating_basis`, `is_provisional` |
| Current conditions (F3) | `city_rating`, newest row of the city (`order=valid_time.desc&limit=1`) | `air_temp_c`, `wind_speed_ms`, `wind_perp_ms`, `wind_direction_deg`, `solar_radiation_wm2`, `station_id` |
| DLR against static capacity chart (F4) | `city_rating`, one city, a `valid_time` range | `valid_time`, `rating_amps`, `static_rating_amps` (or the `_mw` pair), `status`, `config_fingerprint` to mark changes |
| Forecast band (F5) | either | `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps`, `forecast_horizon_min`, `forecast_status`, `forecast_method` |
| Anomaly and fallback indicators (F6) | either | `status`, `fallback`, `fallback_gates`, `alerts`, `exhausted`, `detector_signal` |
| Weather provenance (optional detail) | `solar_source` from either; the others from `city_rating` only | `temp_source`, `wind_source`, `solar_source` |

Two things the specs ask for are not in the database:

- **A trusted-duration value (F5).** No column holds one. Derive it from the forecast band yourself, or raise it with the Data Science owner as a new column.
- **PSS/E results (F7).** The database holds ratings only. Power Systems outputs have no agreed interface yet.

## Rules that are easy to get wrong

Each rule below is stated in full in the contract section named in brackets.

- **Show `rating_basis` next to every rating value** ("Provisional values"). Rows that carry the current `rating_basis` label read `is_provisional` false; backfill rows and older live rows stay provisional and read true. A history chart therefore mixes both. Branch on `is_provisional`, not on the label text.
- **A `fallback` row is a valid rating, not an error** ("Fallback rows"). It publishes the city's static rating because a safety gate fired. Show it as the current value; never skip back to an older computed row.
- **Check freshness per city** ("Freshness"). A city that fails writes no row, so `latest_rating` keeps returning its last row while it ages. Four rows can come back while one city is hours old. Read `is_stale` on each row; a row more than 90 minutes old is stale.
- **Page history explicitly** ("Endpoints"). The service returns at most 1000 rows per request and does not warn you when it cuts a result. Always give an `order` (`valid_time.asc` within one city), bound the range with `valid_time=gte.` and `valid_time=lt.`, and page until a page comes back empty.
- **Never combine cities** ("Compatibility"). No minimum, sum or bottleneck across cities: each city is an independent rating point.
- **Mark identity changes on charts** ("What produced each row"). When `config_fingerprint`, `forecast_model_sha256` or `anomaly_model_sha256` differs from the previous row of the same city, the conductor data, the assumptions or a model changed at that hour. Draw a marker; do not join the two sides into one smooth line without one.
- **Parse timestamps with their offset** ("Timestamps"). Every timestamp is UTC and arrives with an offset such as `+00:00`. Convert to local time in the client. `valid_time` is always a whole hour.
- **Expect the current hour to change** ("Freshness"). A retry within the same hour overwrites that hour's row, and `computed_at` moves. This is not an error.
- **Ignore columns you do not know** ("Compatibility"). Columns are only ever appended after the last one; none is renamed or dropped in v1. Select the columns you use by name.

## Day-ahead forecast

Besides the live rating, the database holds a second, separate value for each city: a day-ahead forecast of the current the line can carry, one value for each 00, 06, 12 and 18 UTC hour. It is meant for looking at the day ahead, with a short lookahead: a value appears about 18 hours before its target hour, so the view holds at most three upcoming targets per city and nothing for a target further away. Every value carries the label `day-ahead-24h; engineering-selection; not-validated`, which says three things: it comes from a forecast made about a day ahead, it is the owner's engineering choice rather than a model picked by a signed rule, and it has not been validated.

What to read:

- **`day_ahead_upcoming`** (view) to display values: the targets still to come, soonest first within each city.
- **`day_ahead_status`** (view) for the badge: always four rows, one per city, saying whether the feed is late.
- **`day_ahead_forecast`** (table) for history: every value ever issued, never rewritten.

| Dashboard view | Read from | Columns |
|---|---|---|
| Next-day panel per city | `day_ahead_upcoming`, ordered by `city` then `valid_time` | `city`, `valid_time`, `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps`, `lead_minutes`, `issued_at`, `band_source`, `label` |
| Feed status badge | `day_ahead_status` | `is_late`, `missing_targets`, `next_target_time` |

The easy mistakes:

- **It is not the live rating, and it never gates it.** Do not show it in place of `rating_amps`, do not use it to colour the status page, and do not feed it back into any gate or alarm. It never sets or checks the live rating.
- **Always show the band and the label next to the value.** `forecast_ci_lower_amps` and `forecast_ci_upper_amps` are the 5-95% band; a bare `forecast_amps` hides the uncertainty. `band_source` says how the band was measured. Show `label` as it is.
- **"24 h" is the age of the weather run, not how early you get the value.** A value is issued 0-18 h before its target, so `issued_at` and `valid_time` differ by less than a day.
- **Values exist only at 00/06/12/18 UTC.** Do not draw a line between them as if they were hourly. Convert to local time in the client, as for every timestamp.
- **A target more than 18 hours away is not late, it is only not yet due.** Nothing is published for it yet, `is_late` stays false and `missing_targets` stays empty. Show "not yet available", not an error.
- **An empty or late target stays empty.** Show it as missing; never fill it from another hour or city. A target that has passed is not filled afterwards.
- **`is_late` is the stall flag.** It turns true when a target due within the next 12 hours has no value; `missing_targets` lists them. A late feed is a status to show, not an error to throw.

Values change about every 6 hours, so hourly polling is enough. The rules and every column are in [`rest-api.md`](rest-api.md) ("Day-ahead forecast") and in [`day_ahead_forecast_v1.md`](../data-science/schema/day_ahead_forecast_v1.md). The three examples in [`examples/`](examples/) each print the upcoming targets and the status as their last part.

## Cadence and polling

- A scheduled run writes one row per city each hour. The external scheduler dispatches it at five minutes past the hour.
- Poll no faster than once every 60 seconds; once every few minutes is enough for a dashboard, since the data changes hourly.
- Select only the columns you need and bound every history query by `valid_time`.

## Errors you will see

| HTTP | Code | Usual cause |
|---|---|---|
| 400 | `42703` | A misspelled column in `select`, a filter or `order`. |
| 401 | none | The `apikey` header is missing or wrong. |
| 401 or 403 | `42501` | A write, or a read of `pipeline_run`. |
| 404 | `PGRST205` | A misspelled table name, or the service is reloading its schema; retry shortly. |
| 503 | `PT503` | `rpc/assert_fresh` found a stale or missing city, or (`day_ahead_late` in the details) a day-ahead target that is overdue. |

The full table is "Status codes" in the contract.

## Frontend documents that name flat files

The frontend planning documents were written before the database existed and still name flat files as the data source. `api/README.md`, `frontend/README.md` and the F1 spec describe reading `outputs/` CSV files and `data/fixtures/sample_pipeline_output.csv`. The production source is now this database. The fixture still works for offline development, but its columns follow the older pipeline output schema ([`pipeline_output_v1.md`](../data-science/schema/pipeline_output_v1.md)), not `city_rating`. Those documents belong to the Software team, so this handoff flags the difference and leaves the edits to you.

There is no generated OpenAPI description to build a client from: the publishable key cannot read it. [`rest-api.md`](rest-api.md) is the contract.

## Getting help

- **Access, keys, a column you need, or data that looks wrong:** the Data Science owner.
- **Operations** (how the hourly run works, the freshness alarm, pausing and resuming): [`dlr_live_runbook.md`](../data-science/decisions/dlr_live_runbook.md). You do not need it to build the dashboard.
- **A breaking change to the contract** needs a v2 of [`rest-api.md`](rest-api.md), agreed with both the Software and Power Systems teams.
