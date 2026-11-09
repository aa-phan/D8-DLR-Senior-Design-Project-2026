# Dynamic Line Rating: REST interface for consumers

**Contract version:** v1
**Date:** 2026-10-26
**Status:** decided contract (DS decision authority, REQUIREMENTS.md); values PROVISIONAL (OD-5); readable once the owner applies Phase 6's migration (`supabase/migrations/20261026195124_expose_latest_rating.sql`)
**Audience:** the Software team (React dashboard), Power Systems (PSS/E scripts), and any other consumer of the ratings
**Scope:** how to read the hourly dynamic line ratings of the four project cities through Supabase's REST interface: what to call, what each column means, how fresh the data is, and what to do when it is not. Column-by-column storage details, the backfill rows and the run log are in [`city_rating_v1.md`](../data-science/schema/city_rating_v1.md).

**Read this first.** Every rating value (`*_amps`, `*_mw`) is PROVISIONAL: a model estimate at one rating point per city, not a verified line limit (OD-5). Show the label in `rating_basis` wherever you show a value. A row whose `status` is `fallback` is not an error and not missing data: it is a valid, safe, published rating (the city's static rating), and it is the newest row on purpose (see "Fallback rows").

## Connecting

- The interface is Supabase's REST service (PostgREST). You need two values: `SUPABASE_URL` (the project URL) and `SUPABASE_PUBLISHABLE_KEY` (the publishable key).
- **The Data Science owner gives both values to each team directly.** They are never written into this repository, into these docs or into the examples (D-10). The examples read them from the environment variables of the same names.
- Send the key in the `apikey` header only, never in an `Authorization` header and never in the URL. The supabase-js client does this for you.
- The publishable key maps to the read-only `anon` role: it can read `latest_rating` and `city_rating` and, once the owner applies the day-ahead expose migration, `day_ahead_forecast`, `day_ahead_upcoming` and `day_ahead_status`, and nothing else. The secret key (`sb_secret_...`) and any `service_role` token are never for consumers; if you hold one, do not use it for this.
- Rotation: if the key is exposed or retired, the DS owner issues a new publishable key to each team, you switch, and the old key is retired. Nothing else changes.
- Base URL for every call below: `$SUPABASE_URL/rest/v1/`.

## Endpoints

| Call | What it returns |
|---|---|
| `GET /rest/v1/latest_rating` | Exactly four rows, one per city (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`): the newest row of each city, with `age_minutes`, `is_stale` and `is_provisional` added. Use `?select=...&order=city`. |
| `GET /rest/v1/city_rating` | The full per-city history (OD-6: public). Filters `eq.`, `in.`, `gte.`, `lt.` work on every column of `latest_rating` and on the stored diagnostics listed in [`city_rating_v1.md`](../data-science/schema/city_rating_v1.md). Always give an explicit `order`. Page with `limit` and `offset`, or with the `Range` header. |
| `GET /rest/v1/day_ahead_upcoming` | The day-ahead forecast values whose target is still in the future, ordered by `city` then `valid_time`, with `lead_minutes` added (26 columns). Labelled `day-ahead-24h; engineering-selection; not-validated`. See "Day-ahead forecast". Readable once the owner applies the expose migration `20261108120100_expose_day_ahead_forecast.sql`. |
| `GET /rest/v1/day_ahead_status` | Exactly four rows, one per city: when the next target is, how many future values exist, when the newest was issued, which targets due within the next 12 hours have no value, and `is_late` (7 columns). |
| `GET /rest/v1/day_ahead_forecast` | The full day-ahead history (OD-6: public), 25 columns, including targets that have passed. Always give an explicit `order` and page it like `city_rating`. |
| `GET /rest/v1/rpc/assert_fresh?max_age_minutes=90` | A freshness check across all four cities: HTTP 200 with a small JSON document when every city is fresh, HTTP 503 (code `PT503`) naming the missing or stale cities when not, HTTP 400 (code `22023`) for a bad parameter. |

Details that matter:

- **`latest_rating`** has one row per city, always the newest by `valid_time`, fallback rows included. Filter and order it like a table.
- **`city_rating` paging.** The service returns at most 1000 rows per request, silently: there is no error and no warning when a result is cut. Page with an explicit unique order (`order=valid_time.asc` is unique within one city; for several cities use `order=valid_time.asc,city.asc`) and keep going until a page comes back empty. Bound the range with `valid_time=gte.<start>` and `valid_time=lt.<end>` (two filters on the same column are allowed) so rows appended while you page cannot shift your offsets. `Prefer: count=exact` with `Range-Unit: items` and `Range: 0-0` returns the total after the slash of `Content-Range` (for example `0-0/2500`).
- **`rpc/assert_fresh`** answers `{"ok": true, "cities": 4, "max_age_minutes": 90, "oldest_valid_time": "..."}` with HTTP 200. When a city has no row or only an older one it answers HTTP 503 with code `PT503` and a `details` text of the form `missing=... stale=...`. A `max_age_minutes` outside 0 to 10080 is HTTP 400 with code `22023`. Once the owner applies the day-ahead expose migration, the same call also fails with HTTP 503 (`PT503`) when the day-ahead feed has stalled: the `details` text then reads `missing=... stale=... day_ahead_late=CITY@UTC-time,...`, and the HTTP 200 body gains `day_ahead_armed` (true once the day-ahead table holds its first value; the day-ahead part of the alarm is armed by the first value, so an empty feed cannot raise a false alarm). It is documented here, and the DS owner runs it as the permanent alarm; the examples do not need it (D-12).

## `latest_rating` columns

The view has 34 columns, in this order. The first 31 are read straight from `city_rating`; the last three are computed at request time. "NULL when" for each stored column is in [`city_rating_v1.md`](../data-science/schema/city_rating_v1.md). Every `*_amps` and `*_mw` value is PROVISIONAL (OD-5).

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `city` | text | none (identifier) | City key: `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND` or `EL_PASO`. |
| `valid_time` | timestamptz | UTC instant | The hour the row is for: the hour-truncated UTC slot of the run (OD-7). The newest slot for the city. |
| `observation_time` | timestamptz | UTC instant | The weather hour the rating used; may be older than `valid_time`. NULL when unknown or when no observation exists. |
| `rating_amps` | double precision | A, per conductor | PROVISIONAL. The dynamic line rating after the safety gates, or the static fallback rating when `status` is `fallback`. |
| `rating_mw` | double precision | MW, three-phase | PROVISIONAL. `rating_amps` converted with `line_voltage_kv` and `power_factor`. |
| `static_rating_amps` | double precision | A, per conductor | PROVISIONAL. The owner-supplied static rating of the city. |
| `static_rating_mw` | double precision | MW, three-phase | PROVISIONAL. `static_rating_amps` converted the same way. |
| `line_voltage_kv` | double precision | kV | Line voltage used for the MW conversion. |
| `power_factor` | double precision | dimensionless | Power factor used for the MW conversion. |
| `status` | text | none (category) | `ok` when the computed rating passed every gate; `fallback` when the static rating was published. |
| `fallback` | boolean | none (flag) | True when the published rating is the static fallback rating. |
| `fallback_gates` | text[] | none (labels) | Which gates fired, for example `G4` or `EXHAUSTED`; an empty array when none did. |
| `alerts` | text[] | none (text) | The safety-gate messages of the run; an empty array when there are none. |
| `exhausted` | boolean | none (flag) | True when no weather station could be used and no observation exists. |
| `forecast_method` | text | none (label) | Forecast method requested for the run: `naive`, `ewm` or `ml`. |
| `forecast_status` | text | none (category) | `ok`, `cold_start` or `failed`; NULL when not recorded. |
| `forecast_amps` | double precision | A, per conductor | PROVISIONAL. One-step-ahead forecast of the rating; NULL when no forecast was produced. |
| `forecast_ci_lower_amps` | double precision | A, per conductor | PROVISIONAL. Lower edge of the forecast band. |
| `forecast_ci_upper_amps` | double precision | A, per conductor | PROVISIONAL. Upper edge of the forecast band. |
| `forecast_horizon_min` | double precision | minutes | Forecast horizon. |
| `detector_signal` | text | none (label) | The anomaly detector signal of the run. |
| `rating_basis` | text | none (text) | The provisional label: what the values are and are not (OD-5). Show it with every value. |
| `config_version` | text | none (label) | Human-readable label of the rating assumption set. |
| `origin` | text | none (category) | `live` for pipeline rows, `backfill` for rows loaded from the Phase 3 archive. |
| `run_id` | text | none (identifier) | The workflow run that wrote the row. |
| `pipeline_version` | text | none (identifier) | Short git commit of the pipeline code. |
| `computed_at` | timestamptz | UTC instant | When the row was last written; changes when the same hour is rewritten. |
| `config_fingerprint` | text | none (identifier) | Automatic identity of the city's rating assumptions (conductor, point, static rating, bounds, bearing, voltage, power factor, forecast and detector parameters). A change from one row to the next marks a conductor or model change (D-01). |
| `forecast_model_sha256` | text | none (identifier) | sha256 of the forecast model file the run loaded; NULL when the method has no model file. A change from one row to the next marks a conductor or model change. |
| `anomaly_model_sha256` | text | none (identifier) | sha256 of the anomaly model file the run loaded; NULL when none was loaded. A change from one row to the next marks a conductor or model change. |
| `solar_source` | text | none (label) | Provider that supplied the solar radiation. |
| `age_minutes` | integer | minutes | Computed (D-02). Whole minutes from `valid_time` to the moment of your request, rounded up: a started minute counts as a minute. |
| `is_stale` | boolean | none (flag) | Computed (D-02). True when `valid_time` is strictly more than 90 minutes before your request (OD-4). Exactly 90 minutes is fresh. It is a direct time comparison, so it never disagrees with `age_minutes > 90`. |
| `is_provisional` | boolean | none (flag) | Computed (D-03). True while the word `provisional` (any capitalisation) appears in `rating_basis` or in `config_version`. See "Provisional values". |

The identity columns are how a change shows up (D-01). If `config_fingerprint`, `forecast_model_sha256` or `anomaly_model_sha256` differs from the previous row of the same city, the conductor, the assumptions or a model changed at that hour; see "What produced each row".

## Freshness

- **Cadence (OD-1):** one row per city per hour, written by the scheduled pipeline.
- **Slot (OD-7):** `valid_time` is the hour of the run, rounded down. A run at 14:07 UTC and a retry at 14:12 UTC both write the 14:00 row, and the retry overwrites it (`computed_at` changes). At 14:12 that row is 12 minutes old.
- **Limit (OD-4):** a city is fresh while its newest `valid_time` is no more than 90 minutes old: 60 minutes for the hourly cadence plus a 30-minute grace. Exactly 90 minutes is fresh; more than 90 minutes is stale. `is_stale` and `rpc/assert_fresh` use the same rule.
- **A failed city (OD-9):** if a city fails outright, no row is written for that hour. The view keeps showing that city's last good row, which then ages and reads `is_stale` true. Your code sees an old row, not an error row.
- **Check every city, never only the row count.** Four rows can come back while one city is three hours old. Read `is_stale` (or `age_minutes`) on each row, or call `rpc/assert_fresh`.
- `age_minutes` is rounded up, so a started minute counts as a minute: a row 90 minutes and 1 second old reads 91 and is stale.
- `age_minutes` is computed when you ask, so two requests a minute apart give different values; compare stored columns, not `age_minutes`, when you compare two reads.

## Fallback rows

- `latest_rating` always returns the newest row of each city, even when it is a fallback (D-04). It never skips back to an older computed row.
- `status` is `fallback`, `fallback` is true and `fallback_gates` and `alerts` say why (for example `G4`: the computed value was outside the plausible band). The published `rating_amps` is then the city's static rating.
- Falling back is safe by the owner's rule: the documented static rating is safe, and a computation outside the band means the model is inaccurate. It is a valid published value, not an error and not missing data. Do not hide it, and do not replace it with an older computed value.
- AUSTIN publishes its static rating in a large share of hours while Phase 7's conductor data is pending. That is expected and is not a freshness failure: a fallback row is still a fresh row.

## Provisional values

- Every rating value is PROVISIONAL (OD-5) except on rows written going forward under the new label, which the Phase 7 re-validation go (REVAL-01, 2026-11-02) covers. `is_provisional` lets your code branch on a boolean instead of reading the label text.
- **The word rule.** `is_provisional` is true while the word `provisional` (any capitalisation) appears in `rating_basis` OR in `config_version`. Live rows and backfill rows begin their labels differently, so the flag looks for the word, not for a prefix.
- **Phase 7 hand-off.** The owner signed the Phase 7 re-validation go (REVAL-01) on 2026-11-02, for rows written going forward only. A row written with the new `rating_basis` and a `config_version` that both lack the word `provisional` shows `is_provisional` false (the new label lacks the word); older live rows and backfill rows keep their labels and still show true. A phrase such as "no longer provisional" would still read as provisional, because it contains the word.
- Show `rating_basis` next to every value. Never describe a backfill row or a row written before the label change as having passed a go/no-go; only rows carrying the new label are covered by the Phase 7 re-validation (`docs/data-science/decisions/real_data_validation_p7.md`).

## What produced each row

- The identity columns (`config_version`, `config_fingerprint`, `forecast_model_sha256`, `anomaly_model_sha256`) say what produced a row, so a change is visible in the data without any schema change.
- Phase 7 may deploy new per-city conductor settings or new models around 2026-11-01. They arrive as new values in these same columns. Mark such a change on charts and tables, and never splice values across it without noting it.
- Within one city, compare each row's three identifiers with the previous row's. Never reduce across cities (no minimum, no sum, no bottleneck): each city is an independent point.

## Timestamps

- Every timestamp is a UTC instant and arrives with an offset (for example `2026-10-25T01:00:00+00:00`). Always parse the offset; do not assume it.
- Python before 3.11 cannot parse these strings with `datetime.fromisoformat` (it rejects `Z` and fractions that are not 3 or 6 digits). Use the `parse_ts` helper in [`examples/read_ratings.py`](examples/read_ratings.py).
- `valid_time` is always a whole UTC hour. Convert to local time in the client.

## Status codes

| HTTP | Code | When |
|---|---|---|
| 200 | none | Success. |
| 206 | none | Success for a `Range` request that returned part of the result. |
| 400 | `42703` | A column in `select`, a filter or `order` does not exist (a misspelled name). |
| 400 | `22023` | `rpc/assert_fresh` was given a `max_age_minutes` outside 0 to 10080. |
| 401 | none | The `apikey` header is missing or invalid. |
| 401 or 403 | `42501` | Permission denied: any write, or a read of a table consumers may not read. |
| 404 | `PGRST202`, `PGRST205` | Unknown table or function, or the service is reloading its schema after a change; retry shortly. |
| 406 | `PGRST116` | You asked for exactly one object (`Accept: application/vnd.pgrst.object+json`) and the result had zero or several rows. |
| 503 | `PT503` | `rpc/assert_fresh` found a city with no row or only a stale one, or (once armed by the first day-ahead value) a day-ahead target that is late; `details` names the cities, and `day_ahead_late=...` names each late city and target. |

## Write protection and visibility

- The publishable key reads; it cannot write. Every insert, update and delete on the rating tables and the view is refused by privilege (OD-6), not merely filtered by row-level security. The DS owner checks this against the live project (E2E-03) before the interface is announced to the teams.
- The run log (`pipeline_run`) and the freshness log (`ops.freshness_log`) are not readable with this key.
- The full history is public by owner decision (OD-6). No credential is stored, and each `alerts` entry is redacted and cut to 300 characters before it is stored. An entry for a detector failure (`G6 ... detector error`) can still carry a short error message, so treat `alerts` as diagnostic text.

## Limits and polling

- The data changes hourly. Poll no faster than every 60 seconds; once per few minutes is plenty for a dashboard.
- Keep requests small: select only the columns you need, and bound history queries with `valid_time` filters.
- The service returns at most 1000 rows per request. See "Endpoints" for paging.

## Examples

Three examples, each showing (1) the current row of every city from `latest_rating`, (2) one city's rows over a date range from `city_rating`, paged past the 1000-row cap, and (3) the upcoming day-ahead targets (`day_ahead_upcoming`) and the per-city day-ahead status (`day_ahead_status`). All three are read-only, read `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` from the environment and contain no project value.

| Example | For | Run it |
|---|---|---|
| [`examples/curl.sh`](examples/curl.sh) | any consumer, any language | `bash curl.sh` with `CITY`, `START` and `END` (UTC, ending in `Z`) optional |
| [`examples/supabase_js.mjs`](examples/supabase_js.mjs) | the dashboard | in your own project: `npm install @supabase/supabase-js@2` (Node 22 or newer for current 2.x; a browser needs only `fetch`), then `node supabase_js.mjs` with `CITY`, `START` and `END` optional |
| [`examples/read_ratings.py`](examples/read_ratings.py) | PSS/E and Python 3.7+ | `python read_ratings.py --city AUSTIN --start 2026-10-25T00:00:00Z --end 2026-11-01T00:00:00Z` |

Set the two variables first. On Windows use `set SUPABASE_URL=<value from the DS owner>` and `set SUPABASE_PUBLISHABLE_KEY=<value from the DS owner>` in the command shell; elsewhere use `export`.

## PSS/E environment

- The Python example targets Python 3.7 or newer and uses the standard library only (`urllib`, `json`, `re`, `datetime`). It keeps Python's default TLS certificate verification.
- Python 3.7 or newer with TLS 1.2 and SNI is **assumed and unconfirmed**. Power Systems is asked to run `import sys, ssl; print(sys.version); print(ssl.OPENSSL_VERSION)` inside PSS/E's Python and to run `read_ratings.py` once.
- If the answer is Python 2.7, that becomes a follow-up (a separate example), not a blocker for this interface.

## OpenAPI

Since April 2026 the publishable key can no longer read the service's OpenAPI description, so there is no generated contract for you to read. This document is the contract.

## Compatibility

- Column names are never renamed or dropped without a coordinated change with both teams (D-01). Columns may be appended after the last one, so ignore columns you do not know.
- Never reduce across cities.
- This contract is v1. A breaking change needs a v2 document and a coordinated change.

## Monitoring

The DS owner runs a permanent freshness alarm on `rpc/assert_fresh` (see section 14 of the [live runbook](../data-science/decisions/dlr_live_runbook.md)). Consumers still check `is_stale` on every row they use: the alarm tells the owner, not your code. The same alarm URL also fails with `day_ahead_late=...` when the day-ahead feed stalls, armed by the first day-ahead value; there is no new alarm job.

## Day-ahead forecast

**Label:** `day-ahead-24h; engineering-selection; not-validated`. Show it wherever you show a day-ahead value.

A 24-hour-ahead estimate from ml_cooling_corrected. It has more error than the 60-minute forecast because it looks further ahead. On past data (TEST window, Mar-Sep 2026) its typical error was about 23 A (~1.7% of rating) larger. It is the owner's engineering choice, not picked by the signed selection rule, and it never sets or checks the live rating.

- **Evidence, exploratory.** The "about 23 A" and "about 1.7%" are from the horizon comparison on the TEST window, an exploratory analysis that was not pre-registered: [`REPORT.md`](../data-science/exploratory/2026-11-02_horizon_comparison/REPORT.md) (`docs/data-science/exploratory/2026-11-02_horizon_comparison/REPORT.md`). They describe past data, not future error. The value has no safety role: it is not validated, it never gates a rating, and it is separate from the 60-minute forecast in `city_rating` that does.
- **What "24 h" means.** It is the age of the weather run behind the value (`forecast_run_init_time` is exactly 24 hours before `valid_time`), not how early you get the value. A value is issued 0 to 18 hours before its target. `issued_at`, `forecast_run_init_time` and `anchor_observation_time` let you compute both leads for every row.
- **Targets.** One value per city for each 00, 06, 12 and 18 UTC hour. A target that has passed is never filled afterwards; it stays empty.
- **Issue rule.** A target is due from about 18 hours before it, and the hourly job issues it as soon as it is due and retries every hour. A value issued late shows a later `issued_at`. Rows are written once and never rewritten.
- **Band rule.** `forecast_ci_lower_amps` and `forecast_ci_upper_amps` are the 5-95% empirical band, one per city and target hour. At launch every band comes from the TEST split, measured against reanalysis truth with a 24 h anchor (`band_source` is `test-split`). A band switches on its own to `live-rolling` once 60 graded pairs exist for its city and hour, using the newest 120, and only when it brackets the value; the live band is measured against the station-composed rating, with hours where the live rating was the static fallback left out. The two measurements differ, so the width can change when `band_source` changes.
- **Late rule.** A 6-hourly target due within the next 12 hours with no value marks its city late, once the feed has its first value (armed by the first value). `day_ahead_status.is_late` and `missing_targets` show it, and the permanent alarm reads the same rule (`day_ahead_late=...` in the `rpc/assert_fresh` details).
- **Out-of-range values are published as computed.** The live rating falls back to the static rating when a computed value is outside its bounds; the day-ahead value does not. A value outside the rating bounds is still published (on the first live run two MIDLAND values were below 1250 A) and the pipeline logs a warning.
- **Amperes only.** There is no MW column; convert as for `city_rating`, with the line voltage and power factor of the rating rows.

Column-by-column storage details, the identity columns, the versioning rule and the run log are in [`day_ahead_forecast_v1.md`](../data-science/schema/day_ahead_forecast_v1.md).

## `day_ahead_upcoming` columns

The view has 26 columns, in this order: the 25 columns of `day_ahead_forecast`, then `lead_minutes`. Every row is a future target with a value. Every `*_amps` value carries the day-ahead label and is not validated.

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `city` | text | none (identifier) | City key: `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND` or `EL_PASO`. |
| `valid_time` | timestamptz | UTC instant | The target hour: 00, 06, 12 or 18 UTC. Always in the future in this view. |
| `issued_at` | timestamptz | UTC instant | When the issuing run decided to issue the value, before `valid_time`. A catch-up issue carries a later value. |
| `forecast_run_init_time` | timestamptz | UTC instant | Start of the weather run behind the value, exactly 24 hours before `valid_time` (the age of the weather run, not the lead from `issued_at`). |
| `horizon_minutes` | integer | minutes | Age of the weather run at `valid_time`; always 1440. |
| `forecast_amps` | double precision | A, per conductor | The day-ahead forecast of the ampacity at `valid_time`. Not validated; see the label. |
| `forecast_ci_lower_amps` | double precision | A, per conductor | Lower edge (5%) of the empirical band. |
| `forecast_ci_upper_amps` | double precision | A, per conductor | Upper edge (95%) of the empirical band. |
| `band_source` | text | none (category) | `test-split` (launch band) or `live-rolling`. |
| `band_n` | integer | count | Number of residuals behind the band. |
| `band_pairs_through` | timestamptz | UTC instant | `valid_time` of the newest live pair behind a `live-rolling` band; NULL for `test-split`. |
| `band_artifact_sha256` | text | none (identifier) | sha256 of the TEST band artifact file; always recorded. |
| `forecast_method` | text | none (label) | Always `ml_cooling_corrected`. |
| `cooling_model_sha256` | text | none (identifier) | sha256 of the cooling model file the value came from. |
| `cooling_model_source` | text | none (category) | `refit` or `frozen`. |
| `anchor_observation_time` | timestamptz | UTC instant | Time of the station observation the correction used; can be hours before `valid_time`. |
| `anchor_source` | text | none (label) | Provider of the anchor observation (`tceq` or `synoptic`). |
| `label` | text | none (label) | `day-ahead-24h; engineering-selection; not-validated`. |
| `config_version` | text | none (label) | Human-readable label of the rating assumption set. |
| `config_fingerprint` | text | none (identifier) | Automatic identity of the city's rating assumptions. |
| `run_id` | text | none (identifier) | The workflow run that issued the value. |
| `run_attempt` | integer | count | Attempt number of that workflow run. |
| `pipeline_version` | text | none (identifier) | Short git commit of the pipeline code. |
| `schema_version` | integer | version | Row schema version; 1 here. |
| `first_written_at` | timestamptz | UTC instant | When the row was inserted; never changes. |
| `lead_minutes` | integer | minutes | Computed. Whole minutes from your request to `valid_time`, rounded up, so always at least 1 here. |

## `day_ahead_status` columns

The view always has four rows, one per city, and seven columns in this order. Check every city, never only the row count.

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `city` | text | none (identifier) | City key. |
| `checked_at` | timestamptz | UTC instant | The moment of your request; every other column is computed as of it. |
| `next_target_time` | timestamptz | UTC instant | The first 00, 06, 12 or 18 UTC target after `checked_at`. |
| `upcoming_count` | integer | count | Stored day-ahead values for the city whose `valid_time` is after `checked_at`. |
| `newest_issued_at` | timestamptz | UTC instant | The newest `issued_at` of the city, past or future; NULL when the city has no value. |
| `missing_targets` | timestamptz[] | UTC instants | Every target due within the next 12 hours (after `checked_at`, up to 12 hours later) that has no stored value; an empty array when none. |
| `is_late` | boolean | none (flag) | True when `missing_targets` is not empty and the table holds at least one row (armed by the first value); false otherwise. |
