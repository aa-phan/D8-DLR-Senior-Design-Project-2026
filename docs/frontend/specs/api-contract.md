<!-- generated-by: gsd-doc-writer -->
# API Data Contract

**Audience:** Software sub-team (`api/` and `frontend/`).

**Status:** `api/` is not built. `api/README.md` is a structural placeholder with no Flask app, no routes, and no dependencies. There are no HTTP endpoints to document. This file records the **data contract** an API layer would serve: the shapes of the files and Python return values the DS backend already produces, plus the Python entry points that produce them. Nothing here is a decided API design.

**Scope (2026-10-12):** the rating unit is one of four independent city points (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`); corridors, corridor minima and bottleneck points are retired (`docs/data-science/decisions/point_scope.md`). Sections 3 to 5 and the entry-point table describe the per-city contract. At the time of writing the backend migration was in progress: `backend/city_point.py` and `backend/city_rating.py` existed and the `rate_city` keys below were read from them, and the shadow pipeline writes `schema_version: 3` rows (`forecast_shadow_pipeline.log_cycle_predictions`); the v3 record below was read from that code on 2026-10-12. Where the contract does not fix a detail, the detail is marked **open**.

Anything labeled **PROPOSED** is a suggestion for the Software team to accept or reject. It is not implemented and not agreed. The open decisions are collected at the end under [Open decisions on `api/` shape](#open-decisions-on-api-shape).

Related guides: [architecture.md](../guides/architecture.md) for how the data flows, and [configuration.md](../guides/configuration.md) for tokens, `config.py` constants, and file locations.

## Authentication

None exists. The repo contains no auth middleware, no API keys for consumers, and no session handling, because there is no server. Two separate things are easy to confuse:

- **Upstream credentials** (`SYNOPTIC_TOKEN`, `NREL_API_KEY`, `NREL_API_EMAIL`) are used by the backend to call weather providers. They must never be sent to or exposed by a browser client. See [configuration.md](../guides/configuration.md).
- **Consumer auth** (who may call `api/`) is undecided. <!-- VERIFY: whether the dashboard needs any authentication, and who the intended operators are -->

## Data sources overview

These are the four artifact families an API could serve. Paths are relative to the repo root, and a fresh clone contains only the files marked "tracked".

| Source | Producer | Contract | Tracked in git | Stability |
|--------|----------|----------|----------------|-----------|
| `outputs/station_data/{prefix}_{STID}.csv` | `dlr_pipeline.export_results` | [`pipeline_output_v1.md`](../../data-science/schema/pipeline_output_v1.md), 11 columns | No (`/outputs` ignored); fixture at `data/fixtures/sample_pipeline_output.csv` is tracked | Versioned doc, unversioned files |
| `outputs/merged_ercot_dlr_{STID}.csv` | `ercot_dlr_merger.py` `__main__` | Section below, 8 columns | No | Informal; no spec doc |
| `data/historical/ampacity_history.csv` | `historical_archive.append_observation` | `historical_archive.ARCHIVE_COLUMNS`, 10 columns | No | Column list locked in code |
| `data/shadow/predictions/{CITY}.jsonl` | `forecast_shadow_pipeline.log_cycle_predictions` | `schema_version: 3` (per city; field list in section 3). Legacy corridor files hold v1 flat and v2 rows | No on `main`; live copy on the `shadow-collection-data` branch | Experimental, may change |
| `rate_city(...)` return dict | `city_rating.rate_city` (per-city contract) | Section 4 | n/a (in-process only) | No file or HTTP form |

City identifiers are the keys of `config.LOCATIONS`: `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`. There are no corridor identifiers any more. The names `AUSTIN_CORPUS_CHRISTI` and `MIDLAND_EL_PASO` survive only as legacy shadow-log file names and in `config.LEGACY_CORRIDOR_ENDPOINTS`, which is reserved for a frozen historical experiment and is not for API use.

## Request/response formats

There are no requests. The "responses" below are the data shapes themselves.

### 1. Station pipeline CSV (`pipeline_output_v1`)

Eleven columns in this exact order. The authoritative definition with units and valid ranges is [`pipeline_output_v1.md`](../../data-science/schema/pipeline_output_v1.md); do not duplicate it elsewhere.

```
stid,datetime_utc,air_temp,wind_speed,wind_direction,wind_perp_ms,solar_radiation,relative_humidity,dlr_amps,dlr_headroom_pct,dlr_uplift_flag
```

| Column | Type | Unit | Notes |
|--------|------|------|-------|
| `stid` | string | n/a | Weather station ID, one file per station |
| `datetime_utc` | timestamp string | UTC | See format note below |
| `air_temp` | float | degC | |
| `wind_speed` | float | m/s | |
| `wind_direction` | float | deg | Compass degrees |
| `wind_perp_ms` | float | m/s | Wind component perpendicular to the line |
| `solar_radiation` | float | W/m2 | Missing values are filled with 1000 before the rating is computed |
| `relative_humidity` | float | % | May be empty |
| `dlr_amps` | float | A | IEEE 738 dynamic rating, per conductor |
| `dlr_headroom_pct` | float | % | `(dlr_amps - static) / static * 100` |
| `dlr_uplift_flag` | boolean | n/a | Serialized as `True` or `False` |

Differences between the spec/fixture and the real exports that a parser must tolerate (found by comparing `data/fixtures/sample_pipeline_output.csv` with `outputs/station_data/2025-07-01_2025-07-04_AN489.csv`):

| Aspect | Fixture | Real export (AN489 example) |
|--------|---------|-----------------------------|
| `datetime_utc` format | `2026-07-15T18:00:00Z` | `2025-07-01 00:00:00+00:00` |
| Cadence | 5 minutes | Hourly in the checked-in AN489 file (96 rows over four days) |
| `relative_humidity` | populated | Empty in every row of the AN489 file |

Parse timestamps with a library that accepts both ISO forms rather than a fixed format string.

The static rating behind `dlr_headroom_pct` and `dlr_uplift_flag` depends on the `city` passed to `run_pipeline`: a value from `config.STATIC_RATINGS` (a city uses its own entry, never the minimum of a corridor pair; Corpus Christi is 1500 A per conductor, previously 1900 A under the pair rule), or `config.DEFAULT_STATIC_RATING` (900 A) when `city` is omitted or unknown. The CSV does not record which rating was used. The checked-in AN489 file's headroom values are consistent with 900 A. Treat headroom as relative to an unrecorded, provisional rating.

There is no `schema_version` column and the filename carries no version. The file name pattern is `{file_prefix}_{stid}.csv`; the `__main__` block of `dlr_pipeline.py` sets the prefix to `{START date}_{END date}`, for example `2025-07-01_2025-07-04`.

### 2. Merged ERCOT and DLR CSV

Produced by `backend/ercot_dlr_merger.py`. It reads one station CSV, resamples to an hourly worst case, converts to MW, and inner-joins ERCOT West load on `datetime_utc`. The checked-in example is `outputs/merged_ercot_dlr_AN489.csv`. Columns, in order:

| Column | Type | Unit | Source |
|--------|------|------|--------|
| `datetime_utc` | timestamp (`2025-07-01 00:00:00+00:00`) | UTC | Hourly bucket |
| `dlr_amps` | float | A | `min` over the hour (weakest case) |
| `wind_speed` | float | m/s | `mean` over the hour |
| `air_temp` | float | degC | `mean` over the hour |
| `dlr_capacity_mw` | float | MW | `amps_to_mw(dlr_amps, 345 kV, 0.95)` using `config.LINE_VOLTAGE_KV` and `config.POWER_FACTOR` |
| `static_capacity_mw` | float | MW | Same conversion applied to the city's static rating (constant per file) |
| `ercot_west_load_mw` | float | MW | ERCOT West hourly load |
| `datetime_local` | timestamp with offset (`2025-06-30 19:00:00-05:00`) | US/Central | Added as a side effect of the plotting function, which mutates the merged frame before the CSV is written |

Caveats:

- `static_capacity_mw` in the checked-in example is 510.9 MW, which corresponds to the 900 A default rating, not the 1825 A `AUSTIN` rating. The file was likely produced before `city` selection existed, so regenerating it will give different static values. <!-- VERIFY: how and when outputs/merged_ercot_dlr_AN489.csv was generated -->
- Conversion formula: `P = sqrt(3) * V * I * PF / 1000`, with the amps being a single conductor's rating. Bundle counts are not applied here.
- The `datetime_local` column exists only because of that side effect. Do not depend on it; convert from `datetime_utc` in the frontend.
- The `__main__` block writes the CSV and PNG to the **current working directory**, not `outputs/`.
- ERCOT load alone (`ercot_west_load_mw`) comes from `ercot_data_retriever.py` as a two-column CSV, `datetime_utc,ercot_west_load_mw`, under `outputs/ercot_data/`.

### 3. Historical archive CSV

Appended by `historical_archive.append_observation` when a rating is archived (at most one row per `rate_city` call; `archive=True` is the default). The file is gitignored and absent from a fresh clone.

The scope contract says `rate_city` may archive one row but does not list the columns. In the code read on 2026-10-12, `historical_archive.ARCHIVE_COLUMNS` (10 columns, `ARCHIVE_SCHEMA_VERSION = 1`) is below. Treat it as current code, not a decided contract.

| Column | Type | Notes |
|--------|------|-------|
| `datetime_utc` | string | The `end` argument passed to `rate_city`, verbatim (for example `2026-09-23T23:55:00Z`). It is the analysis window boundary, **not** a wall-clock time. |
| `city` | string | City key. Was `corridor` in the corridor era (same position) |
| `air_temp` | float | degC, of the city's observation |
| `wind_speed` | float | m/s |
| `solar_radiation` | float | W/m2 |
| `dlr_amps` | float | The city's rating, A |
| `static_rating` | float | The city's own `STATIC_RATINGS` entry, A |
| `status` | string | `ok` or `fallback` |
| `fallback` | boolean | |
| `schema_version` | int | `1`. Not bumped for the `corridor` to `city` rename |

Corridor-era archive files (header has `corridor`, and possibly the old `bottleneck_index` column) are still readable: `read_history` exposes that column as `city`, and appends follow the file's existing header order. Legacy rows are corridor-level (the bottleneck point's values) and must not be mixed into a per-city series without deciding how to treat them (open). If the bottleneck point had no observation (exhausted probe) no row is written. Rows failing `units_def.validate_pipeline_row` are rejected on write, and `read_history` drops invalid rows on read.

### 4. City rating dict (`rate_city`)

In-process Python only. There is no file or JSON form today. `backend/city_rating.py::rate_city` replaces the corridor-era `rate_corridor`: it resolves the city's nearest usable station observation (probe-and-fallback behavior kept), runs it through `DLRSafetyMonitor` with the city's own static rating, optionally archives one row, and returns one dict per city. Keys, read from the code on 2026-10-12 (the contract names the same set):

| Key | Type | Notes |
|-----|------|-------|
| `city` | string | One of `config.LOCATIONS` |
| `point` | tuple `(lat, lon)` | The city's coordinate (`config.CITY_COORDINATES`). The static rating is **not** in this dict; read it from `config.STATIC_RATINGS` (backend) or ask DS for an exported field (open) |
| `station_id` | string or `None` | Resolved station. `None` when exhausted. Can differ between runs for the same city (nearest usable station). Grid providers (`open_meteo`, `nsrdb`) fetch at the city coordinate instead of probing stations (expected `None`; confirm) |
| `candidates_probed` | int | Length of the probe trail |
| `probe_trail` | list of dict | Each entry in the corridor-era shape had `stid`, `lat`, `lon`, `distance_km`, `outcome` (`usable` or `unusable`). Confirm entry keys in the code before depending on them |
| `rating` | float | Amps. The city's static rating when it fell back |
| `status` | string | `ok` or `fallback` |
| `fallback` | bool | |
| `alerts` | list of string | Free text such as `G4 FAIL (implausible (...) A) — fallback rating N A`, or for an exhausted lookup `EXHAUSTED FAIL (AUSTIN: n candidates exhausted) — fallback rating N A` |
| `observation` | dict or `None` | Corridor-era shape was `{sensor_status, link_status, temp, wind, solar}` with short key names that differ from the CSV columns; `None` when exhausted |
| `exhausted` | bool | True when no candidate station gave a usable observation. Replaces the corridor-era `exhausted_points` count |
| `archived` | bool | Whether an archive row was written |

Not in the per-city dict (corridor-era keys): `corridor`, corridor-level `bearing_deg`, the `points` list, `bottleneck_index`, `exhausted_points`, and the "any point fell back" meaning of `fallback`. There is no reduction across cities, so a client never receives a single value standing for several cities.

The dict may contain numpy/pandas scalar types (observation values come from DataFrame rows), so a JSON layer needs to convert them before serializing. `alerts` strings are human-readable only; there is no structured gate or reason code. If the dashboard needs to branch on which gate failed (G1 to G6), that requires a DS change or string parsing.

### 5. Shadow prediction JSONL

One JSON object per line, **one file per city** (`data/shadow/predictions/{CITY}.jsonl`), append-only. A cycle runs four times a day (00, 06, 12, 18 UTC) via `.github/workflows/shadow_collect.yml` (started by an external cron-job.org dispatch, not a GitHub `schedule:` trigger) and iterates the four cities (`config.LOCATIONS`), one child process per city, with an inter-city request delay. Runs that start late or are skipped still reduce the count, so expect up to 4 distinct `valid_time`s per day, and fewer in practice (the GitHub scheduler, used before 2026-10-15, started runs 3-8 h late; timing under the external trigger has not been measured). Live data is on the `shadow-collection-data` branch, not on `main`:

```bash
git fetch origin shadow-collection-data
git show origin/shadow-collection-data:data/shadow/predictions/AUSTIN.jsonl
```

Per-city logs began empty on 2026-10-12, so a file can be missing or hold few rows. The 12 per-city shadow correction artifacts are fit and committed, so ML candidates normally report `status="ok"`; `unavailable` with a named reason still occurs, for example `persistence_24h` on a cold start, or right after the model switch until a prior `gfs_seamless` entry is in tolerance.

**`forecast_model` and the one-hour offset fix (2026-10-13).** Since 2026-10-13 the collector uses the underlying weather model `gfs_seamless` (`config.SHADOW_LIVE_FORECAST_MODEL`), selects the exact valid hour (the earlier rows carried a one-hour forecast offset), and writes a string field `forecast_model` on every v3 row. **A v3 row without `forecast_model` is pre-fix: it carries the one-hour offset and an `ecmwf_ifs` forecast. Do not consume such rows as part of a per-city series, and never pool them with rows that have the field.** Rows with different `forecast_model` values must not be mixed either. `persistence_24h` is computed from the same underlying weather model as the row it sits in (same-model rule).

Three row shapes can exist and a reader must handle all of them:

| Shape | Where | `schema_version` | Distinguishing fields |
|-------|-------|------------------|------------------------|
| Per city (current) | `{CITY}.jsonl` | `3` | `city` replaces `corridor` |
| Corridor-era v2 (legacy) | `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl` | `2` | `corridor`, `candidates` |
| Corridor-era flat (legacy v1) | same two files | absent | `corridor`, `method`, `ampacity_amps`, no `candidates` |

The two corridor-named files are left untouched. Readers that scan logs must tolerate them and must **not** mix legacy corridor rows into per-city evaluation or display. Branch on `schema_version` (absent, 2, 3) and on whether the file name is a city key.

**What is fixed for v3** (from the scope contract): records carry `city` where they carried `corridor`, and `schema_version` is `3`; every per-city method targets that city's own ampacity, not a minimum; nothing reduces across cities.

**v3 record shape (read from code, 2026-10-12):** top level `schema_version`, `city`, `initialization_time`, `availability_time`, `decision_time`, `valid_time`, `horizon_minutes`, `logged_at`, `basis_caveat`, `candidates` (one entry per `CANDIDATE_METHOD_NAMES`: `status`, `ampacity_amps`, `fallback_used`, `fallback_reason`, `model_version`, `input_provenance`, `reason`, `bundle`) and the six-field mirror of `ml_wind_corrected`. `bundle` is `{status: "ok", bundle_ampacity_amps, subconductors_per_phase, config_version, rating_basis, reason}` or `{status: "unavailable", reason, config_version}`; `input_provenance` is `{anchor_provenance: {anchor_source, anchor_station, anchor_observation_time}}` for anchored candidates and null for `raw_forecast`. The corridor-era fields that pooled or reduced across cities (`per_city_ampacity_amps`, `bottleneck_city`, `endpoint_bundle_ampacity_amps`, `corridor_bundle_ampacity_amps`, `bundle_bottleneck_city`) are gone, so a v3 reader must not require them. DS has not formally frozen this shape; treat it as implemented, not guaranteed.

Fields that the corridor-era v2 record carried and that are expected to continue in some form (not confirmed for v3):

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | int | `3` for per-city rows |
| `city` | string | Replaces `corridor` |
| `initialization_time`, `availability_time`, `decision_time`, `valid_time` | ISO 8601 string, UTC offset | Weather model run start, when it became queryable, when the prediction was made, and the time it is for |
| `horizon_minutes` | int | `1440`, the only horizon the module accepted in v2 |
| `logged_at`, `basis_caveat` | string | `basis_caveat` must be shown or linked wherever predictions are displayed |
| `candidates` | object | Keyed by candidate name: `ml_wind_corrected`, `ml_cooling_corrected`, `raw_forecast`, `persistence_24h`, `reference_ml_refit_24h` in v2 |

`horizon_minutes` is a label, not the measured lead time. In the 13 rows of the legacy `AUSTIN_CORPUS_CHRISTI` log read on the data branch (a v2-era check), `valid_time - decision_time` was between 11.1 and 16.7 hours while `horizon_minutes` was 1440. Compute the lead from the two timestamps if the UI shows it, and do not caption values "24 hours ahead" without confirming with DS. <!-- VERIFY: whether the 6-hourly valid_time selection is intended to be described as a 24-hour horizon -->

Each v2 candidate object had `status` (`ok`, `unavailable`, or `failed`), `ampacity_amps` (float or `null`, per conductor), `fallback_used`, `fallback_reason`, `model_version`, `input_provenance`, `reason` and `bundle`. Treat `status` and `reason` as the way to tell "no value" from a value. The v2 `bundle` reported ampacity scaled by `config.SUBCONDUCTORS_PER_PHASE` (a provisional Power Systems assumption) with a `rating_basis` caveat text that has to be shown wherever bundle values appear. Whether and how bundles are reported per city in v3 is open. Choose deliberately whether the dashboard shows per-conductor or bundle values, and label it.

Timestamps have microseconds in some fields and not others (`2026-10-08T12:00:00+00:00` versus `2026-10-08T22:45:55.320055+00:00`).

### 6. Forecast result object (not exported)

`ampacity_forecast.forecast_ampacity(history)` returns a `ForecastResult` with attributes `horizon_min`, `amps`, `ci_lower_amps`, `ci_upper_amps`, `n_observations`, `method`, `n_residuals`, or `None` on a cold start. `forecast_columns(result)` maps it to four keys: `forecast_horizon_min`, `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps`, or `{}` when the result is `None`. The per-city rating path uses this only to build the anomaly detector; **no file or return value currently carries the forecast** to a consumer. The shadow JSONL is a separate, day-ahead forecast (labelled 1440 minutes; see the lead-time caveat in section 5).

## Python entry points

The backend is flat modules run with `PYTHONPATH=backend`, from the repo root.

| Entry point | Signature (abridged) | Returns / writes | Needs |
|-------------|----------------------|------------------|-------|
| `dlr_pipeline.run_pipeline` | `(stids, start, end, conductor, city=None, solar_alt_deg=45.0)` | DataFrame (CSV columns above, plus any extra columns from the fetch); empty DataFrame if nothing fetched | `SYNOPTIC_TOKEN` |
| `dlr_pipeline.export_results` | `(df, output_path=".", file_prefix=".")` | One CSV per station | none |
| `dlr_pipeline.plot_dlr_summary` | `(df, city=None, output_dir=".", file_prefix="dlr")` | One PNG per station | none |
| `ercot_dlr_merger.process_dlr_to_hourly` | `(dlr_csv_path, city=None)` | Hourly DataFrame with MW columns | none |
| `ercot_dlr_merger.load_ercot_west_data` | `(start, end, csv_path)` | ERCOT load DataFrame filtered to the window | a CSV from `ercot_data_retriever.py` |
| `city_point.city_point` | `(city)` | A `CityPoint` (coordinate, bearing, conductor, static rating, bounds); `KeyError` naming valid cities for an unknown key | none |
| `city_rating.rate_city` | `(city, start, end, stations, fetch_weather=None, logger=None, sleep=time.sleep, anomaly_detector=None, archive=True, archive_path=None, provider="synoptic")` | The `rate_city` dict (section 4); optionally appends one archive row | provider credentials; a stations DataFrame |
| `historical_archive.read_history` | `(path=None, city=None, validate=True, corridor=None)`; `corridor` is a deprecated alias for `city`, and a legacy file's `corridor` column is renamed to `city` on read | DataFrame in `ARCHIVE_COLUMNS` shape, empty if no file | none |
| `forecast_shadow_collect.collect_once` | `()` | Exit code `0` (ok), `1` (hard failure), `2` (lock held); appends one JSONL per city in `config.LOCATIONS` | `SYNOPTIC_TOKEN` |
| `forecast_shadow_demo.run_once_all_methods` | `(city, *, horizon_minutes=1440)` (parameter renamed from `corridor` under the contract; to confirm) | Dict of `ShadowPrediction` per candidate; also logs a cycle | network |
| `config.LOCATIONS`, `config.STATIC_RATINGS`, `config.CITY_COORDINATES`, `config.CITY_LINE_BEARING_DEG` | constants | City list and per-city lookups | none |

Practical notes:

- `run_pipeline` and `rate_city` take **station metadata** and **ISO 8601 window strings**, not a "latest" argument. A live API that wants current conditions must choose the window itself.
- `run_pipeline` never calls forecasting, per-city rating, or anomaly detection. In the corridor era `run_corridor_pipeline` was the only function that wired the forecast and anomaly detector into the rating; it was removed by the scope change (`corridor_pipeline.py` is listed as removed). Where the per-city equivalent lives and who schedules it is **open**; nothing schedules it today.
- Scripts such as `dlr_pipeline.py`, `ercot_dlr_merger.py`, and `smoke_test.py` hard-code their inputs under `if __name__ == "__main__"` or at module level, and take no CLI arguments. Import the functions instead of shelling out.
- Calling Python from Flask would require the API process to have the backend's requirements installed and `backend/` on `PYTHONPATH`, plus the provider tokens in its environment.

## Error codes

No HTTP status codes exist. Data-level failure signals the contract already carries:

| Signal | Where | Meaning |
|--------|-------|---------|
| `status: "fallback"`, `fallback: true` | `rate_city` dict, archive rows | A safety gate failed; `rating` is the city's static rating (or `min(computed, static)` for G5). `alerts` has the text. One city's fallback says nothing about the other three. |
| Gates G1 to G6 | `alerts` strings | G1 sensor availability, G2 link, G3 range, G4 plausibility, G5 large delta, G6 learned anomaly (including `detector error`) |
| Exhausted candidates | `rate_city` `alerts` and `exhausted` | Every candidate station for the city was unusable; `station_id` is `None`, `observation` is `None`, rating is the city's static rating. Alert text is `EXHAUSTED FAIL (CITY: n candidates exhausted) — fallback rating N A` in the code read on 2026-10-12 |
| `candidates.*.status` | Shadow JSONL | `ok`, `unavailable` (no input, for example `persistence_24h` on a cold start, or a missing model artifact), or `failed` (exception, text in `reason`) |
| `candidates.*.fallback_used` | Shadow JSONL | Method fell back internally to `raw_forecast` and still produced a value |
| `bundle.status: "unavailable"` | Shadow JSONL (v3) | No bundle value for this candidate this cycle |
| Empty DataFrame | `run_pipeline` | No observations returned |
| Missing station in output | Station CSVs | A requested station with zero rows is silently absent (known issue in `docs/data-science/specs/C3-export-visualization.md`) |
| `EnvironmentError("Set SYNOPTIC_TOKEN env var. ...")` | `run_pipeline`, at fetch time | Token not set |

A fallback is a valid, safe result, not an error: the dashboard should present it as a distinct state rather than hiding the point.

Two points of the pipeline validate rows against `units_def.PIPELINE_SCHEMA` (`validate_pipeline_row`): station export (log only, rows are never dropped) and the archive (rows rejected). If the UI needs to guard against out-of-range values, the ranges are in `pipeline_output_v1.md`.

## Rate limits

`api/` has none, since it does not exist. Upstream constraints that shape any live design:

- Synoptic, NREL, Open-Meteo, and TCEQ calls are made by the backend, and the repo documents no confirmed rate limits for them. The rating path deliberately spaces requests (the probe batch pause `PROBE_BATCH_PAUSE_S` in `backend/city_rating.py`, and the inter-city delay `INTER_CITY_DELAY_S` = 15.0 in `backend/forecast_shadow_collect.py`) and caps probes per city, so a request-per-page-load design would be unsafe. The exact constant names after the migration are to confirm. <!-- VERIFY: provider rate limits and quotas for the project's Synoptic and NREL keys -->
- A single city rating can cost several provider requests per call (probing candidate stations). Rating four cities multiplies that. Serve cached or file-backed results rather than computing per request.

## PROPOSED: HTTP surface

Everything in this section is **PROPOSED** and **not decided**. It exists only so the Software team has something concrete to accept or amend. Names, paths, and response shapes are placeholders. None are implemented.

| Method | Path | Would serve | Backing source | Depends on |
|--------|------|-------------|----------------|------------|
| GET | `/api/stations/{stid}/series` | Station rows as JSON, filterable by time range | `outputs/station_data/*.csv` | A pipeline run having produced the file |
| GET | `/api/cities` | The four city keys, each with its static rating (labelled provisional) | `config.LOCATIONS`, `config.STATIC_RATINGS` | none |
| GET | `/api/cities/{city}/rating` | Latest rating, fallback state, alerts, resolved station for one city | `rate_city` dict | A DS exporter or in-process call; see decision 2 |
| GET | `/api/cities/{city}/history` | Archived ratings for one city over time | `data/historical/ampacity_history.csv` | Archive populated by a scheduled run; per-city archive columns are open |
| GET | `/api/cities/{city}/shadow` | Shadow predictions and candidates for one city | `shadow-collection-data` branch `{CITY}.jsonl` | Decision 3 on how the JSONL reaches the API host; v3 field list not final |
| GET | `/api/grid/hourly/{stid}` | Merged DLR and ERCOT load | merged CSV | Someone running the merger |

`{city}` is validated against the closed set of four city keys and never forms a file path. There is no corridor route, no all-cities minimum and no bottleneck field, and none is proposed: a list endpoint that returns the four cities returns four independent results. Legacy corridor-named shadow files are not served as cities.

If adopted, two conventions would simplify the frontend (also proposed): return timestamps as ISO 8601 UTC with `Z`, and normalize the three timestamp formats listed above at the API boundary so the client sees one form.

## Open decisions on `api/` shape

None of these is resolved in the repo. Each needs an owner and a decision before `api/` code is written, and the answer should be recorded in the Software team's PRD (see `docs/frontend/README.md`).

1. **Role of `api/`.** A thin file-serving layer, a live-polling service, or one that also proxies PSS/E outputs. This is the question `api/README.md` leaves open. The PSS/E handoff format is itself unspecified (`docs/data-science/decisions/pss_e_handoff.md`).
2. **How per-city results reach the API.** Either call `rate_city` in-process (couples the API to the Python backend and provider credentials), or ask DS to add an exporter that writes each city's dict to a file (adds a new contract that does not exist today). Today these results are returned only to the caller, apart from an optional archive row.
3. **How shadow data reaches the API.** Read from the `shadow-collection-data` branch (git fetch, or raw GitHub fetch), have the workflow also publish somewhere else, or have the API host check out that branch. Repository visibility for unauthenticated raw fetches is unknown. <!-- VERIFY: repository visibility and whether raw.githubusercontent.com access to the shadow-collection-data branch is permitted -->
4. **Who runs the station and per-city rating pipelines on a schedule.** Only the shadow collector is scheduled. "Live" station or city data needs a scheduler owner.
5. **Which ampacity basis the UI shows:** per-conductor, bundle-level, or both, and where the `rating_basis` caveat is displayed.
6. **Which shadow candidate is displayed.** No winner is declared; `ml_wind_corrected` is only the provisional default behind the legacy mirror fields. v3 keeps those mirror fields (`method`, `ampacity_amps`, `fallback_used`, `fallback_reason`, `model_version`, `input_provenance`, taken from `ml_wind_corrected`).
7. **Schema versioning for station CSVs.** The export has no version marker. The open question is tracked in the C3 spec; if the CSV column list changes, `pipeline_output_v1.md` is meant to be superseded by a v2 document.
8. **Consumer authentication and hosting.** Not decided. <!-- VERIFY: hosting platform and consumer auth for api/ and frontend/ -->
9. **Station-to-city mapping.** The station CSV carries only `stid`, and a city's source station can change between runs. A per-city series from station files needs a mapping that does not exist yet (PRD OD-1, G1).
10. **Per-city archive and shadow v3 shapes.** The archive columns for per-city rows are implemented (`corridor` renamed `city`; the always-null `bottleneck_index` dropped on 2026-10-13) and the v3 shadow record is implemented (section 3), but neither is covered by the scope contract's own text. Confirm with DS before treating them as stable.
11. **Missing outputs.** The Project Definition lists a "trusted-duration window" and a forecast panel. No backend code computes the former, and the forecast is not in any feed. Confirm with DS before designing UI that depends on them.

## Compatibility rules for consumers

- Treat extra CSV columns and extra JSON keys as additive. `PIPELINE_SCHEMA` (version 3 in `units_def.PIPELINE_SCHEMA_VERSION`) is additive-only: keys are added, never renamed or removed.
- Do not assume the `candidates` key exists on every JSONL line.
- Static ratings in `config.STATIC_RATINGS` are unconfirmed per-conductor values derived from owner-supplied bundle averages (2026-10-13). Label them as such in the UI. A city uses its own entry, no longer the minimum of a corridor pair.
- Per-city line bearings (`config.CITY_LINE_BEARING_DEG`) are an assumption carried over from the retired corridor bearings, not a measurement. They affect `wind_perp_ms` and therefore the ratings.
- Never reduce across cities in a client: no minimum, no bottleneck, no corridor total.
- All backend timestamps are UTC. Convert to local time in the frontend.
