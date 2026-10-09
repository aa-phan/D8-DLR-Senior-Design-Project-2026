<!-- generated-by: gsd-doc-writer -->
# API Data Contract

**Audience:** Software sub-team (`api/` and `frontend/`).

**Status:** `api/` is not built. `api/README.md` is a structural placeholder with no Flask app, no routes, and no dependencies. There are no HTTP endpoints to document. This file records the **data contract** an API layer would serve: the shapes of the files and Python return values the DS backend already produces, plus the Python entry points that produce them. Nothing here is a decided API design.

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
| `data/historical/ampacity_history.csv` | `historical_archive.append_observation` | `historical_archive.ARCHIVE_COLUMNS`, 11 columns | No | Column list locked in code |
| `data/shadow/predictions/{CORRIDOR}.jsonl` | `forecast_shadow_pipeline.log_cycle_predictions` | `schema_version: 2` plus legacy rows | No on `main`; live copy on the `shadow-collection-data` branch | Experimental, may change |
| `rate_corridor(...)` return dict | `corridor_discretization.rate_corridor` | Section below | n/a (in-process only) | No file or HTTP form |

Corridor identifiers are the keys of `config.CORRIDOR_ENDPOINTS`: `AUSTIN_CORPUS_CHRISTI` and `MIDLAND_EL_PASO`. City identifiers are `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`.

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

The static rating behind `dlr_headroom_pct` and `dlr_uplift_flag` depends on the `city` passed to `run_pipeline`: a value from `config.STATIC_RATINGS`, or `config.DEFAULT_STATIC_RATING` (900 A) when `city` is omitted or unknown. The CSV does not record which rating was used. The checked-in AN489 file's headroom values are consistent with 900 A. Treat headroom as relative to an unrecorded, provisional rating.

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

- `static_capacity_mw` in the checked-in example is 510.9 MW, which corresponds to the 900 A default rating, not the 1900 A `AUSTIN` rating. The file was likely produced before `city` selection existed, so regenerating it will give different static values. <!-- VERIFY: how and when outputs/merged_ercot_dlr_AN489.csv was generated -->
- Conversion formula: `P = sqrt(3) * V * I * PF / 1000`, with the amps being a single conductor's rating. Bundle counts are not applied here.
- The `datetime_local` column exists only because of that side effect. Do not depend on it; convert from `datetime_utc` in the frontend.
- The `__main__` block writes the CSV and PNG to the **current working directory**, not `outputs/`.
- ERCOT load alone (`ercot_west_load_mw`) comes from `ercot_data_retriever.py` as a two-column CSV, `datetime_utc,ercot_west_load_mw`, under `outputs/ercot_data/`.

### 3. Historical archive CSV

Appended once per `rate_corridor` call (`archive=True` is the default). Column order is `historical_archive.ARCHIVE_COLUMNS`:

| Column | Type | Notes |
|--------|------|-------|
| `datetime_utc` | string | The `end` argument passed to `rate_corridor`, verbatim (for example `2026-09-23T23:55:00Z`). It is the analysis window boundary, **not** a wall-clock time. |
| `corridor` | string | Corridor key |
| `air_temp` | float | degC, of the bottleneck point's observation |
| `wind_speed` | float | m/s, bottleneck point |
| `solar_radiation` | float | W/m2, bottleneck point |
| `dlr_amps` | float | The corridor rating (`min` over points) |
| `static_rating` | float | Corridor static rating, A |
| `status` | string | `ok` or `fallback`, of the bottleneck point |
| `fallback` | boolean | Of the bottleneck point, not the corridor-wide flag |
| `bottleneck_index` | int | Index into the `points` list of the returned dict |
| `schema_version` | int | `1` (`historical_archive.ARCHIVE_SCHEMA_VERSION`) |

Only the bottleneck point is archived. If the bottleneck point has no observation (exhausted probe), no row is written. Rows failing `units_def.validate_pipeline_row` are rejected on write, and `read_history` drops invalid rows on read.

### 4. Corridor rating dict (`rate_corridor`)

In-process Python only. There is no file or JSON form today.

```python
{
    "corridor": "AUSTIN_CORPUS_CHRISTI",
    "bearing_deg": float,
    "points": [ {point}, ... ],        # always exactly n_points entries (default 5)
    "rating": float,                   # min over points, amps
    "bottleneck_index": int,           # lowest index wins ties
    "fallback": bool,                  # True if ANY point fell back
    "exhausted_points": int,           # points where every candidate station failed
    "archived": bool,                  # whether an archive row was written
}
```

Each `{point}`:

| Key | Type | Notes |
|-----|------|-------|
| `lat`, `lon` | float | Point coordinates |
| `stid` | string or `None` | Resolved station; `None` when exhausted or when the provider is grid-based (`open_meteo`, `nsrdb`) |
| `candidates_probed` | int | Length of `probe_trail` |
| `probe_trail` | list of dict | Each entry has `stid`, `lat`, `lon`, `distance_km`, `outcome` (`usable` or `unusable`). Empty for grid providers. |
| `rating` | float | Amps; the static rating when the point fell back |
| `status` | string | `ok` or `fallback` |
| `fallback` | bool | |
| `alerts` | list of string | Free text such as `G4 FAIL (implausible (...) A) — fallback rating N A` or `EXHAUSTED FAIL (point i: n candidates exhausted) — fallback rating N A` |
| `observation` | dict or `None` | `{sensor_status, link_status, temp, wind, solar}`; `None` when exhausted. Note the short key names (`temp`, `wind`, `solar`), which differ from the CSV column names. |

The dict contains numpy/pandas scalar types in places (coordinates and observation values come from DataFrame rows), so a JSON layer needs to convert them before serializing. `alerts` strings are human-readable only; there is no structured gate or reason code. If the dashboard needs to branch on which gate failed (G1 to G6), that requires a DS change or string parsing.

### 5. Shadow prediction JSONL (`schema_version: 2`)

One JSON object per line, one file per corridor, append-only. A cycle runs twice a day via `.github/workflows/shadow_collect.yml`. Live data is on the `shadow-collection-data` branch, not on `main`:

```bash
git fetch origin shadow-collection-data
git show origin/shadow-collection-data:data/shadow/predictions/AUSTIN_CORPUS_CHRISTI.jsonl
```

Top-level fields of a v2 record:

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | int | `2` |
| `corridor` | string | |
| `initialization_time` | ISO 8601 string, UTC offset | Weather model run start |
| `availability_time` | ISO 8601 string | When that run became queryable |
| `decision_time` | ISO 8601 string | When the prediction was made |
| `valid_time` | ISO 8601 string | Time the prediction is for. `forecast_shadow_demo._resolve_next_valid_time` picks a point on a 6-hourly UTC grid (00, 06, 12, 18 UTC) between 11 and 17 hours after the run. |
| `horizon_minutes` | int | Always `1440`, the only horizon the module accepts |

`horizon_minutes` is a label, not the measured lead time. In all 13 rows of the AUSTIN_CORPUS_CHRISTI log on the data branch, `valid_time - decision_time` is between 11.1 and 16.7 hours while `horizon_minutes` is 1440. Compute the lead from the two timestamps if the UI shows it, and do not caption the values "24 hours ahead" without confirming with DS. <!-- VERIFY: whether the 6-hourly valid_time selection is intended to be described as a 24-hour horizon -->

| `logged_at` | ISO 8601 string | |
| `basis_caveat` | string | Must be shown or linked wherever predictions are displayed |
| `candidates` | object | Keyed by the five candidate names below |
| `method`, `ampacity_amps`, `fallback_used`, `fallback_reason`, `model_version`, `input_provenance` | various | Backward-compatible copy of `candidates.ml_wind_corrected`. New consumers should read `candidates` and ignore these. |

Timestamps have microseconds in some fields and not others (`2026-10-08T12:00:00+00:00` versus `2026-10-08T22:45:55.320055+00:00`).

The five candidate keys, from `forecast_shadow_pipeline.CANDIDATE_METHOD_NAMES`: `ml_wind_corrected`, `ml_cooling_corrected`, `raw_forecast`, `persistence_24h`, `reference_ml_refit_24h`. No winner has been declared among them.

Each candidate object:

| Field | Type | Notes |
|-------|------|-------|
| `status` | string | `ok`, `unavailable`, or `failed` |
| `ampacity_amps` | float or `null` | `null` unless `status` is `ok`. Per-conductor value. |
| `fallback_used` | bool | A method-internal fallback that still produced a value |
| `fallback_reason` | string or `null` | |
| `model_version` | string or `null` | Includes a training timestamp; `null` for `raw_forecast` |
| `input_provenance` | object or `null` | Shape depends on candidate; see below |
| `reason` | string or `null` | Why no value exists when `status` is `unavailable` or `failed` |
| `bundle` | object | Bundle-level reporting basis; see below |

`input_provenance` for `ml_wind_corrected`, `ml_cooling_corrected`, and `raw_forecast` is `{"per_city_ampacity_amps": {city: float}, "bottleneck_city": city}`. For `persistence_24h` it is copied from the matched prior entry (or `null`). For `reference_ml_refit_24h` it carries `truth_proxy_window_start`, `truth_proxy_window_end`, `per_city_ampacity_amps` (always `null`), `per_city_not_applicable_reason`, `station_provenance` (per city, `sources` and `fallback_hours`), and `solar_source`. That candidate is corridor-level only and has no per-city breakdown.

`bundle` has two shapes, discriminated by `bundle.status`:

```json
{
  "status": "ok",
  "endpoint_bundle_ampacity_amps": {"AUSTIN": 2261.3, "CORPUS_CHRISTI": 2380.5},
  "corridor_bundle_ampacity_amps": 2261.3,
  "bundle_bottleneck_city": "AUSTIN",
  "subconductors_per_phase": {"AUSTIN": 2, "CORPUS_CHRISTI": 2},
  "config_version": "v1-provisional-2026-10-08",
  "rating_basis": "…caveat text…",
  "reason": null
}
```

```json
{"status": "unavailable", "reason": "…", "config_version": "v1-provisional-2026-10-08"}
```

Bundle values are the per-city per-conductor ampacity multiplied by `config.SUBCONDUCTORS_PER_PHASE`, then reduced by `min`. `bundle_bottleneck_city` can differ from `input_provenance.bottleneck_city`. `reference_ml_refit_24h` always has an `unavailable` bundle. Show `rating_basis` wherever bundle values appear: the counts are a provisional regional assumption.

**Legacy rows.** Rows written before 2026-10-07 are flat: the top-level fields `corridor`, `method`, `ampacity_amps`, `fallback_used`, `fallback_reason`, `model_version`, `input_provenance`, `logged_at`, the four timestamps, `horizon_minutes`, and `basis_caveat`. They have no `schema_version`, no `candidates`, and no `bundle`. The AUSTIN_CORPUS_CHRISTI log on the data branch currently mixes both shapes (13 lines at the time of writing). Branch on `schema_version` being absent.

`ampacity_amps` in the JSONL is per conductor unless you read `bundle`. Choose deliberately which one the dashboard shows and label it.

### 6. Forecast result object (not exported)

`ampacity_forecast.forecast_ampacity(history)` returns a `ForecastResult` with attributes `horizon_min`, `amps`, `ci_lower_amps`, `ci_upper_amps`, `n_observations`, `method`, `n_residuals`, or `None` on a cold start. `forecast_columns(result)` maps it to four keys: `forecast_horizon_min`, `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps`, or `{}` when the result is `None`. The corridor path uses this only to build the anomaly detector; **no file or return value currently carries the forecast** to a consumer. The shadow JSONL is a separate, 24-hour-ahead forecast.

## Python entry points

The backend is flat modules run with `PYTHONPATH=backend`, from the repo root.

| Entry point | Signature (abridged) | Returns / writes | Needs |
|-------------|----------------------|------------------|-------|
| `dlr_pipeline.run_pipeline` | `(stids, start, end, conductor, city=None, solar_alt_deg=45.0)` | DataFrame (CSV columns above, plus any extra columns from the fetch); empty DataFrame if nothing fetched | `SYNOPTIC_TOKEN` |
| `dlr_pipeline.export_results` | `(df, output_path=".", file_prefix=".")` | One CSV per station | none |
| `dlr_pipeline.plot_dlr_summary` | `(df, city=None, output_dir=".", file_prefix="dlr")` | One PNG per station | none |
| `ercot_dlr_merger.process_dlr_to_hourly` | `(dlr_csv_path, city=None)` | Hourly DataFrame with MW columns | none |
| `ercot_dlr_merger.load_ercot_west_data` | `(start, end, csv_path)` | ERCOT load DataFrame filtered to the window | a CSV from `ercot_data_retriever.py` |
| `corridor_pipeline.run_corridor_pipeline` | `(corridor_name, start, end, stations, provider="synoptic", archive_path=None)` | The rate_corridor dict; appends to the archive | provider credentials; a stations DataFrame |
| `corridor_discretization.rate_corridor` | `(corridor_name, start, end, stations, ..., provider="synoptic")` | The rate_corridor dict | as above |
| `historical_archive.read_history` | `(path=None, corridor=None, validate=True)` | DataFrame in `ARCHIVE_COLUMNS` shape, empty if no file | none |
| `forecast_shadow_collect.collect_once` | `()` | Exit code `0` (ok), `1` (hard failure), `2` (lock held); appends JSONL for both corridors | `SYNOPTIC_TOKEN` |
| `forecast_shadow_demo.run_once_all_methods` | `(corridor, *, horizon_minutes=1440)` | Dict of `ShadowPrediction` per candidate; also logs a cycle | network |
| `config.CORRIDOR_ENDPOINTS`, `config.STATIC_RATINGS` | constants | Corridor and city lookups | none |

Practical notes:

- `run_pipeline` and `rate_corridor` take **station metadata** and **ISO 8601 window strings**, not a "latest" argument. A live API that wants current conditions must choose the window itself.
- `run_pipeline` never calls forecasting, corridor rating, or anomaly detection. `run_corridor_pipeline` is the only function that wires the forecast and anomaly detector into the rating; nothing schedules it, and `backend/smoke_test.py` is its only non-test caller.
- Scripts such as `dlr_pipeline.py`, `ercot_dlr_merger.py`, and `smoke_test.py` hard-code their inputs under `if __name__ == "__main__"` or at module level, and take no CLI arguments. Import the functions instead of shelling out.
- Calling Python from Flask would require the API process to have the backend's requirements installed and `backend/` on `PYTHONPATH`, plus the provider tokens in its environment.

## Error codes

No HTTP status codes exist. Data-level failure signals the contract already carries:

| Signal | Where | Meaning |
|--------|-------|---------|
| `status: "fallback"`, `fallback: true` | Corridor points, archive rows | A safety gate failed; `rating` is the static rating (or `min(computed, static)` for G5). `alerts` has the text. |
| Gates G1 to G6 | `alerts` strings | G1 sensor availability, G2 link, G3 range, G4 plausibility, G5 large delta, G6 learned anomaly (including `detector error`) |
| `EXHAUSTED FAIL` | Point `alerts` | Every candidate station for that point was unusable; `stid` is `None`, `observation` is `None`, rating is static |
| `exhausted_points` | Corridor dict | Count of exhausted points |
| `candidates.*.status` | Shadow JSONL | `ok`, `unavailable` (no input, for example `persistence_24h` on a cold start), or `failed` (exception, text in `reason`) |
| `candidates.*.fallback_used` | Shadow JSONL | Method fell back internally to `raw_forecast` and still produced a value |
| `bundle.status: "unavailable"` | Shadow JSONL | No bundle value for this candidate this cycle |
| Empty DataFrame | `run_pipeline` | No observations returned |
| Missing station in output | Station CSVs | A requested station with zero rows is silently absent (known issue in `docs/data-science/specs/C3-export-visualization.md`) |
| `EnvironmentError("Set SYNOPTIC_TOKEN env var. ...")` | `run_pipeline`, at fetch time | Token not set |

A fallback is a valid, safe result, not an error: the dashboard should present it as a distinct state rather than hiding the point.

Two points of the pipeline validate rows against `units_def.PIPELINE_SCHEMA` (`validate_pipeline_row`): station export (log only, rows are never dropped) and the archive (rows rejected). If the UI needs to guard against out-of-range values, the ranges are in `pipeline_output_v1.md`.

## Rate limits

`api/` has none, since it does not exist. Upstream constraints that shape any live design:

- Synoptic, NREL, Open-Meteo, and TCEQ calls are made by the backend, and the repo documents no confirmed rate limits for them. The corridor path deliberately spaces requests (`PROBE_BATCH_PAUSE_S` in `corridor_discretization.py`, `INTER_CORRIDOR_DELAY_S` in `forecast_shadow_collect.py`) and caps probes per point, so a request-per-page-load design would be unsafe. <!-- VERIFY: provider rate limits and quotas for the project's Synoptic and NREL keys -->
- A full corridor rating costs up to dozens of provider requests per call. Serve cached or file-backed results rather than computing per request.

## PROPOSED: HTTP surface

Everything in this section is **PROPOSED** and **not decided**. It exists only so the Software team has something concrete to accept or amend. Names, paths, and response shapes are placeholders. None are implemented.

| Method | Path | Would serve | Backing source | Depends on |
|--------|------|-------------|----------------|------------|
| GET | `/api/stations/{stid}/series` | Station rows as JSON, filterable by time range | `outputs/station_data/*.csv` | A pipeline run having produced the file |
| GET | `/api/corridors` | Corridor keys and endpoint cities | `config.CORRIDOR_ENDPOINTS` | none |
| GET | `/api/corridors/{corridor}/rating` | Latest corridor rating, fallback state, alerts, bottleneck point | rate_corridor dict | A DS exporter or in-process call; see decision 2 |
| GET | `/api/corridors/{corridor}/history` | Archived bottleneck ratings over time | `data/historical/ampacity_history.csv` | Archive populated by a scheduled run |
| GET | `/api/corridors/{corridor}/shadow` | Shadow predictions, candidates, bundle basis | `shadow-collection-data` branch JSONL | Decision 3 on how the JSONL reaches the API host |
| GET | `/api/grid/hourly/{stid}` | Merged DLR and ERCOT load | merged CSV | Someone running the merger |

If adopted, two conventions would simplify the frontend (also proposed): return timestamps as ISO 8601 UTC with `Z`, and normalize the three timestamp formats listed above at the API boundary so the client sees one form.

## Open decisions on `api/` shape

None of these is resolved in the repo. Each needs an owner and a decision before `api/` code is written, and the answer should be recorded in the Software team's PRD (see `docs/frontend/README.md`).

1. **Role of `api/`.** A thin file-serving layer, a live-polling service, or one that also proxies PSS/E outputs. This is the question `api/README.md` leaves open. The PSS/E handoff format is itself unspecified (`docs/data-science/decisions/pss_e_handoff.md`).
2. **How corridor results reach the API.** Either call `rate_corridor` or `run_corridor_pipeline` in-process (couples the API to the Python backend and provider credentials), or ask DS to add an exporter that writes the corridor dict to a file (adds a new contract that does not exist today). Today these results are returned only to the caller.
3. **How shadow data reaches the API.** Read from the `shadow-collection-data` branch (git fetch, or raw GitHub fetch), have the workflow also publish somewhere else, or have the API host check out that branch. Repository visibility for unauthenticated raw fetches is unknown. <!-- VERIFY: repository visibility and whether raw.githubusercontent.com access to the shadow-collection-data branch is permitted -->
4. **Who runs the station and corridor pipelines on a schedule.** Only the shadow collector is scheduled. "Live" station or corridor data needs a scheduler owner.
5. **Which ampacity basis the UI shows:** per-conductor, bundle-level, or both, and where the `rating_basis` caveat is displayed.
6. **Which shadow candidate is displayed.** No winner is declared; `ml_wind_corrected` is only the provisional default behind the legacy mirror fields.
7. **Schema versioning for station CSVs.** The export has no version marker. The open question is tracked in the C3 spec; if the CSV column list changes, `pipeline_output_v1.md` is meant to be superseded by a v2 document.
8. **Consumer authentication and hosting.** Not decided. <!-- VERIFY: hosting platform and consumer auth for api/ and frontend/ -->
9. **Missing outputs.** The Project Definition lists a "trusted-duration window" and a forecast panel. No backend code computes the former, and the forecast is not in any feed. Confirm with DS before designing UI that depends on them.

## Compatibility rules for consumers

- Treat extra CSV columns and extra JSON keys as additive. `PIPELINE_SCHEMA` (version 3 in `units_def.PIPELINE_SCHEMA_VERSION`) is additive-only: keys are added, never renamed or removed.
- Do not assume the `candidates` key exists on every JSONL line.
- Static ratings in `config.STATIC_RATINGS` are unconfirmed placeholders (midpoints of ranges in the Project Definition). Label them as such in the UI.
- All backend timestamps are UTC. Convert to local time in the frontend.
