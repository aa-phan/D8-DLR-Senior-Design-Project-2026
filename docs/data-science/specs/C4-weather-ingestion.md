# C4 — Weather Ingestion

**Phase:** 2 (Core Consolidation) · **Effort:** M · **Status:** Implemented — provider-agnostic adapter now exists (`backend/weather_provider.py`); only Synoptic is behind it, by design (see below).

**Responsibility:** Discover weather stations near target corridors and fetch time-series observations (temp, wind speed/direction, solar, humidity) for them, behind an interface that doesn't hardcode which provider is behind it — because the provider decision is explicitly unresolved (see `PRD.md` §7.1).

## Current Implementation

- `backend/station_explorer.py::get_network_id(token, shortname) -> str`, `get_all_stations(token, network_id=None) -> pd.DataFrame`, `haversine_km`, `rank_by_corridor` — Synoptic station discovery and corridor-proximity ranking.
- `backend/dlr_pipeline.py::get_wtm_stations(bbox=None) -> pd.DataFrame` — a second, overlapping station-metadata fetch (bbox-based rather than corridor-proximity-based).
- `backend/dlr_pipeline.py::fetch_timeseries(stids, start, end) -> pd.DataFrame` — 5-minute observations via Synoptic `/stations/timeseries`, long-form indexed by `(stid, datetime_utc)`, now also carrying null-tolerant `lat`/`lon` columns parsed from each station's `LATITUDE`/`LONGITUDE` (Phase 6). Requires `SYNOPTIC_TOKEN` env var (`backend/dlr_pipeline.py::_token()`).
- `backend/dlr_pipeline.py::profile_missing_data(df)` — logs per-station, per-variable missing-data percentages and flags fully-dead sensors.

## Interface & Data Contract

Output rows conform to the weather-observation subset of `PIPELINE_SCHEMA` (C2): `air_temp` (degC), `wind_speed` (m/s), `wind_direction` (deg), `solar_radiation` (W/m²), `relative_humidity` (%), indexed by `(stid, datetime_utc)`.

**Implemented:** `backend/weather_provider.py::fetch_weather(location, start, end, provider="synoptic") -> pd.DataFrame`. `location` is type-dispatched (Phase 6): a `list[str]` of station IDs selects the station path, a `(lat, lon)` tuple of two numbers selects the grid path, and every other shape raises `ValueError` naming the received type/length rather than being silently misread. The station path delegates to `dlr_pipeline.fetch_timeseries` and tags each returned row with per-field provenance via `attach_provenance` (`PIPELINE_SCHEMA` v3's four categorical `*_source` columns — `wind_source`, `temp_source`, `humidity_source`, `solar_source` — naming the provider that actually supplied that field family, never inferred or defaulted). The grid path (`_fetch_grid`) raises `ValueError` naming that no grid provider is registered yet — Phase 7 lands the first one (NSRDB or Open-Meteo) by replacing that function's body, not its signature. `merge_observations(station_frame, grid_frame) -> pd.DataFrame` is the city-keyed combination seam (D-05): it keys both sides on `(city, datetime_utc)` (via `resolve_station_city`/`attach_city`, never a default or nearest-guess fallback) and combines them with pandas' `combine_first` — station values win where both sides supply a field, and each field's provenance travels with its value. This adapter now *accommodates* a second provider's shape; the still-open provider decision (`PRD.md` §7.1) itself is unaffected — Phases 7-10 wire the real second/third/fourth providers behind this same seam. `dlr_pipeline.py` gained only additive `lat`/`lon` columns for this purpose (see Known Issues — the duplicate station-metadata fetchers inside it are still there).

## Blocked by

**C1** — needs station source and date-window config.

## Blocks

- **C8** — corridor discretization needs weather at multiple points, which means calling this component's fetch logic repeatedly per corridor point.
- **C9** — forecasting needs both live and historical weather as features.

**Related, not blocking:** C5's ampacity math takes weather values as plain parameters and has no ingestion dependency — it's blocked only by C1, not by this component. C5 needs *some* weather values to be called meaningfully end-to-end, but not this specific ingestion path; a test fixture with hand-set values is enough to develop and test C5 independent of C4 landing.

## Parallel-safe with

C5, C6 (all Phase 2) — no shared files or functions.

## Known Issues

- `backend/station_explorer.py` and `backend/dlr_pipeline.py` each implement their own station-metadata fetch (`get_all_stations` vs. `get_wtm_stations`) with different filtering (corridor-proximity vs. bounding box) and different output columns (`elev_ft` vs. `elevation_m`) — duplicated logic that should consolidate into one.
- `network_id = 152` is hardcoded in `backend/station_explorer.py:99`, with the shortname-lookup path (`get_network_id`) commented out — brittle if the network ID changes. **Still open** — explicitly out of scope for this pass per the Open Questions below.
- ~~Output file/log-message mismatch...~~ **Fixed** — `station_explorer.py`'s log line now correctly reports `data/wtm_stations_austin.csv`.
- Missing `solar_radiation` is filled with a hardcoded `1000` W/m² (`backend/dlr_pipeline.py:348`) rather than being flagged — happens to be conservative for ampacity (more assumed solar → lower computed rating) but is an undocumented magic number, not a named constant. **Still open** — `dlr_pipeline.py` was deliberately not touched this pass (see Interface & Data Contract above), to keep C4 and C5's concurrent work non-overlapping.
- Debug `print()` calls inside `fetch_timeseries` (`backend/dlr_pipeline.py:138-143`) alongside the module's proper `logging` calls elsewhere. **Still open**, same reason.
- No retry/backoff or rate-limit handling on the Synoptic requests — relevant given the free-tier constraints noted in `PRD.md` §7.1. **Still open.**
- **Still duplicated**: `backend/station_explorer.py::get_all_stations` and `backend/dlr_pipeline.py::get_wtm_stations` remain two separate station-metadata fetchers — consolidating them was explicitly out of scope (see Open Questions).
- **Newly found via live verification (2026-08-25)**: `data/wtm_stations_austin.csv` — the file `config.DEFAULT_STATION_SOURCE` points at, i.e. the pipeline's own default station list — contains only 2 real stations (`MOFWL`, `MOLOK`), and **both return zero observation rows** under the currently-configured Synoptic token. Station *metadata* access works for both (they show up in `/stations/metadata`), but the `/stations/latest` endpoint returns `RESPONSE_CODE: 2, "No stations found... or your account does not have access"` for them — a real account/tier restriction, not a code bug. This means `dlr_pipeline.py`'s `__main__` block, run as-is today with default config, would silently produce an empty result. A different station (`KAUS`, Austin-Bergstrom Airport) confirmed full data access and was used for all the live verification below. Worth fixing the default station source before anyone relies on `python backend/dlr_pipeline.py` producing real output.
- **Newly found**: stations that lack Synoptic's `solar_radiation` field entirely (confirmed true for both `KAUS` and the two `wtm_stations_austin.csv` stations) mean the `dlr_pipeline.py:348` hardcoded `1000` W/m² fallback (see above) isn't an edge case — it's the *normal* path for airport/METAR-style stations. This raises the priority of turning it into a named, documented constant.

## Acceptance Criteria

- ✅ A provider swap (Synoptic → mock/alternate) requires changes only inside the ingestion module, with zero changes to C5, C7, or C8 call sites. Verified: `weather_provider.py` is the only file with provider-specific logic; an unsupported provider name raises a clear `ValueError` before any Synoptic-specific code runs.
- ✅ Importable without a `SYNOPTIC_TOKEN` env var. Verified directly (`env -u SYNOPTIC_TOKEN python -c "import weather_provider"` succeeds).
- ✅ **Now verified live (2026-08-25)**: `fetch_timeseries`/`weather_provider.fetch_weather` confirmed against real Synoptic data — `KAUS`, 6-hour window, 79 real observation rows retrieved, fed successfully through the full pipeline (C5's `ieee738_ampacity`, C2's validation, C3's export/plot — see those specs). Missing-data profiling correctly identified `KAUS`'s missing `solar_radiation` field (`WARNING | Stations completely missing 'solar_radiation': KAUS`). The stricter "a station with intentionally ALL fields missing" case was also tested (a zero-row station alongside a working one) — see C3's new Known Issue: that station is silently dropped rather than flagged, which is real, now-documented behavior rather than an untested criterion.

## Open Questions

- Weather provider (see `PRD.md` §7.1) — deliberately unresolved; this component's job is to make the decision inconsequential to everything downstream, not to make it.
- Should historical data accumulation (needed for C9/C10, per `ROADMAP.md` Finding 5) live here as a background job, or as a separate scheduled script?
- Should the two duplicate station-metadata fetchers (`backend/station_explorer.py` vs. `backend/dlr_pipeline.py`) be merged now, or is the duplication tolerable until the provider decision lands?
