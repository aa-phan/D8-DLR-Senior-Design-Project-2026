<!-- generated-by: gsd-doc-writer -->
# F1 — Data Access & API Layer

**Phase:** 1 (Foundation) · **Effort:** M · **Status:** Not started.

**Responsibility:** Be the dashboard's single, tolerant way of reading DS pipeline output — a Flask backend-for-frontend (`api/`) that serves normalized per-city data (four independent rating points; never a corridor aggregate), plus a thin client in `frontend/` that every view calls. Implements WBS 4.2.1 ("Connect Data Science pipeline outputs to dashboard data feed") and SW-F9. Owns file-format quirks (timestamp formats, nulls, absent columns) in exactly one place so no panel re-derives them (SW-NF4, SW-NF5).

## Current Implementation

None. `api/README.md` and `frontend/README.md` are structural placeholders. There is no Flask dependency in `requirements.txt` and no `package.json` in `frontend/`. `api/README.md` states it is "Not yet decided: whether this is a thin file-serving layer, a live-polling service, or something that also proxies PSS/E outputs" — see PRD OD-2.

## Interface & Data Contract

Not yet designed. It should minimally need:

**Input (from DS):**
- The v1 CSV schema in `docs/data-science/schema/pipeline_output_v1.md`: `stid, datetime_utc, air_temp (degC), wind_speed (m/s), wind_direction (deg), wind_perp_ms (m/s), solar_radiation (W/m²), relative_humidity (%), dlr_amps (A), dlr_headroom_pct (%), dlr_uplift_flag (bool)`.
- The default dev source is `data/fixtures/sample_pipeline_output.csv` (one station, `AP140`, 10 rows, 5-minute cadence). Pipeline output under `outputs/station_data/{prefix}_{stid}.csv` is gitignored, so the data directory must be configurable and the fixture the default.
- Per-city rating results (`city_rating.rate_city`, `docs/frontend/specs/api-contract.md` §4) once DS exports them. Today they exist only as an in-process dict (plus an optional archive row), so a file-reading BFF cannot get them; how they arrive is an open decision (api-contract.md, open decision 2).
- Shadow logs, if consumed (OD-12): `data/shadow/predictions/{CITY}.jsonl`, `schema_version: 3`, records carry `city`. The legacy `AUSTIN_CORPUS_CHRISTI.jsonl` and `MIDLAND_EL_PASO.jsonl` (v1 flat rows and v2) must be tolerated and never merged into a per-city series.
- Additive columns from `PIPELINE_SCHEMA` v2/v3 (forecast, `anomaly_score`, `*_source`) once DS exports them — tolerated when present, never required (SW-NF5).

**Output (to the dashboard) — a normalized view-model, proposed, not decided:**
- A location list for the selector: the four cities (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`, i.e. `config.LOCATIONS`). There is no corridor entry, no cross-city minimum and no bottleneck field. A per-station list is an open decision (OD-1).
- Per location: an ordered time series of observations with a parsed, timezone-aware UTC timestamp, numeric fields with explicit nulls (never zero-fill), and the DS-supplied `dlr_headroom_pct` / `dlr_uplift_flag`.
- A per-snapshot **limit basis** the views can trust: `dynamic`, `static_fallback`, or `stale_or_missing` — the one place feed staleness is decided (SW-NF1). The `static_fallback` value can only be populated once DS exports fallback status (PRD §8, G2); until then, the BFF reports only `dynamic` or `stale_or_missing`.
- A data-freshness indicator (timestamp of the newest row and age) so the UI can state when the feed is old.

**Failure behavior:** a missing file, unreadable file, or schema mismatch returns an explicit error state the UI renders as "data unavailable — static rating in effect" (SW-NF1), never an empty chart that looks like a valid zero.

**Security:** reads files from a configured directory only; request parameters never form a file path (the DS side already follows the same rule for model artifacts, `config.py`, "never a caller-supplied path"). A `{city}` route parameter is validated against the closed set of four city keys before use, mirroring `city_point.city_point`, which raises `KeyError` naming the valid cities for an unknown key. No DS credentials needed or exposed (SW-NF6).

## Blocked by

None internal. Depends on two team decisions rather than components: **OD-1** (what a location is) before routes are fixed, and **OD-11** (Flask dependency management, JS tooling) before scaffolding. The DS schema and fixture it needs already exist (`C3` acceptance criteria are met).

## Blocks

- **F3, F4, F5, F6, F7** — every view reads through this layer.
- **F8** — end-to-end tests exercise this path.

## Parallel-safe with

**F2** — data layer vs. layout and wireframes; the only shared concern is the OD-1 decision.

## Known Issues

Upstream data this layer must cope with (read off the fixture and the local, untracked `outputs/` files — PRD §9):

- **Two timestamp formats** for the same UTC semantics: fixture `2026-07-15T18:00:00Z` vs. outputs `2025-07-01 00:00:00+00:00`. DS `C3` Open Questions already asks about schema versioning; there is no `schema_version` column or filename tag to detect the shape.
- **Variable cadence** across station files (hourly, ~15-minute, ~20-minute, vs. the 5-minute the schema document states) and **missing slots** (`AN490`: 92 rows over a four-day hourly window).
- **Entire columns null** (`relative_humidity` for `AN489`, `AN490`) and a **constant `solar_radiation = 1000.0`** in five of six station files.
- **Filenames encode the window and station** (`{prefix}_{stid}.csv`); a station that returned zero rows from the weather API is silently absent from the output (DS `C3` Known Issues) — the BFF cannot distinguish "no such station" from "dead station" and should not claim to.
- **Static rating is per city now.** A city uses its own `config.STATIC_RATINGS` entry rather than the minimum of a corridor pair (Corpus Christi 1500 A per conductor since 2026-10-13; it was 1900 A under the pair rule). The station CSV still does not record which rating was used, and no `stid`→city mapping exists in it (PRD G1).
- **No static-rating column.** Derivable only as `dlr_amps / (1 + dlr_headroom_pct / 100)` (PRD §8, G5); decide whether to derive in the BFF (arithmetic the DS team hasn't sanctioned — tension with SW-NF4) or request the column.

## Acceptance Criteria

- Against the fixture, the API returns all 10 `AP140` rows with values equal to the CSV (no rounding, no unit change) and timestamps parsed as UTC.
- Both timestamp formats above parse to the same UTC instants.
- A CSV with an entirely empty column (e.g. `relative_humidity`) returns explicit nulls, not zeros or errors.
- An unknown column in the input (simulating a schema v2/v3 additive column) is passed through or ignored without error; a **missing required** column (`air_temp`, `wind_speed`, `wind_direction` are `required: True` in `PIPELINE_SCHEMA`) returns a clear error state naming the column.
- A request for an unknown city returns a clear error naming the valid cities, and a legacy corridor-named shadow file is never served as a city.
- A missing or empty data file yields the "data unavailable" state, and the freshness indicator marks a feed older than the chosen staleness threshold (threshold itself pending OD-2/OD-3) as `stale_or_missing`.
- Request parameters cannot cause the API to read outside its configured data directory (negative test).
- No DS credential appears in `frontend/` or in any API response.
- The API runs from a fresh clone using only the committed fixture (SW-NF8).

## Open Questions

- OD-1 (narrowed): routes are per city; the station-to-city mapping and any per-station route are undecided.
- The `rate_city` result keys (`city`, `point` as `(lat, lon)`, `station_id`, `candidates_probed`, `probe_trail`, `rating`, `status`, `fallback`, `alerts`, `observation`, `exhausted` as a bool, `archived`) were read from `backend/city_rating.py` on 2026-10-12; re-check before freezing the API shape.
- OD-2: file-serving vs. polling vs. push; refresh cadence; whether the BFF ever triggers pipeline runs (assumed **no** — it reads output).
- OD-11: how Flask is added to dependency management; how the frontend is built and served in dev.
- OD-13: any access control at all.
- Who owns the staleness threshold, and does it derive from the trusted duration (OD-3) or a fixed number?
