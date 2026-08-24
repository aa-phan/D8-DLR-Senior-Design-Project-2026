# C4 — Weather Ingestion

**Phase:** 2 (Core Consolidation) · **Effort:** M · **Status:** Implemented against Synoptic/WTM; provider-locked (no adapter boundary yet).

**Responsibility:** Discover weather stations near target corridors and fetch time-series observations (temp, wind speed/direction, solar, humidity) for them, behind an interface that doesn't hardcode which provider is behind it — because the provider decision is explicitly unresolved (see `PRD.md` §7.1).

## Current Implementation

- `src/station_explorer.py::get_network_id(token, shortname) -> str`, `get_all_stations(token, network_id=None) -> pd.DataFrame`, `haversine_km`, `rank_by_corridor` — Synoptic station discovery and corridor-proximity ranking.
- `src/dlr_pipeline.py::get_wtm_stations(bbox=None) -> pd.DataFrame` — a second, overlapping station-metadata fetch (bbox-based rather than corridor-proximity-based).
- `src/dlr_pipeline.py::fetch_timeseries(stids, start, end) -> pd.DataFrame` — 5-minute observations via Synoptic `/stations/timeseries`, long-form indexed by `(stid, datetime_utc)`. Requires `SYNOPTIC_TOKEN` env var (`src/dlr_pipeline.py::_token()`).
- `src/dlr_pipeline.py::profile_missing_data(df)` — logs per-station, per-variable missing-data percentages and flags fully-dead sensors.

## Interface & Data Contract

Output rows conform to the weather-observation subset of `PIPELINE_SCHEMA` (C2): `air_temp` (degC), `wind_speed` (m/s), `wind_direction` (deg), `solar_radiation` (W/m²), `relative_humidity` (%), indexed by `(stid, datetime_utc)`.

**Target design (not yet built):** a provider-agnostic interface — something like `fetch_weather(stids, start, end, provider="synoptic") -> pd.DataFrame` — where `fetch_timeseries`'s current Synoptic-specific logic becomes one implementation behind that interface. This is what lets C8 and later components stay unaffected by the still-open provider decision.

## Blocked by

**C1** — needs station source and date-window config.

## Blocks

- **C8** — corridor discretization needs weather at multiple points, which means calling this component's fetch logic repeatedly per corridor point.
- **C9** — forecasting needs both live and historical weather as features.

**Related, not blocking:** C5's ampacity math takes weather values as plain parameters and has no ingestion dependency — it's blocked only by C1, not by this component. C5 needs *some* weather values to be called meaningfully end-to-end, but not this specific ingestion path; a test fixture with hand-set values is enough to develop and test C5 independent of C4 landing.

## Parallel-safe with

C5, C6 (all Phase 2) — no shared files or functions.

## Known Issues

- `src/station_explorer.py` and `src/dlr_pipeline.py` each implement their own station-metadata fetch (`get_all_stations` vs. `get_wtm_stations`) with different filtering (corridor-proximity vs. bounding box) and different output columns (`elev_ft` vs. `elevation_m`) — duplicated logic that should consolidate into one.
- `network_id = 152` is hardcoded in `src/station_explorer.py:99`, with the shortname-lookup path (`get_network_id`) commented out — brittle if the network ID changes.
- Output file is written as `data/wtm_stations_austin.csv` (`src/station_explorer.py:110`) but the log line claims `data/wtm_stations.csv` (`src/station_explorer.py:111`).
- Missing `solar_radiation` is filled with a hardcoded `1000` W/m² (`src/dlr_pipeline.py:348`) rather than being flagged — happens to be conservative for ampacity (more assumed solar → lower computed rating) but is an undocumented magic number, not a named constant.
- Debug `print()` calls inside `fetch_timeseries` (`src/dlr_pipeline.py:138-143`) alongside the module's proper `logging` calls elsewhere.
- No retry/backoff or rate-limit handling on the Synoptic requests — relevant given the free-tier constraints noted in `PRD.md` §7.1.

## Acceptance Criteria

- `fetch_timeseries` (or its successor) returns data for a known station/date range matching expected row counts (5-minute cadence) and no unit violations against `PIPELINE_SCHEMA`.
- Missing-data profiling (`profile_missing_data`) correctly identifies a station with intentionally all-missing data in a test fixture.
- A provider swap (Synoptic → mock/alternate) requires changes only inside the ingestion module, with zero changes to C5, C7, or C8 call sites.

## Open Questions

- Weather provider (see `PRD.md` §7.1) — deliberately unresolved; this component's job is to make the decision inconsequential to everything downstream, not to make it.
- Should historical data accumulation (needed for C9/C10, per `ROADMAP.md` Finding 5) live here as a background job, or as a separate scheduled script?
- Should the two duplicate station-metadata fetchers (`src/station_explorer.py` vs. `src/dlr_pipeline.py`) be merged now, or is the duplication tolerable until the provider decision lands?
