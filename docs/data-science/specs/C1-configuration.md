# C1 — Configuration & Parameterization

**Phase:** 1 (Foundation) · **Effort:** S · **Status:** Implemented (`backend/config.py`)

**Responsibility:** Provide a single, non-code source for values currently hardcoded and duplicated across modules — station source file, analysis date window, static ratings (per-location), and conductor properties — so every component reads the same values instead of drifting independently.

## Current Implementation

Implemented as `backend/config.py`, a plain Python constants module (no new dependencies — matches the "flat `backend/`" convention). Exposes:

- `STATIC_RATINGS: dict[str, float]` — per-city static ratings for the project's 4 documented target cities (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`), per `Project Definition.md`'s I/O Specification Table. Re-keyed from an earlier 5-city table (Houston, Austin, Dallas, Fort Worth, San Antonio) that only overlapped the real spec on Austin — see `docs/data-science/decisions/geographic_scope.md` for the full evidence trail. Since 2026-10-13 each value is the owner-supplied 345 kV bundle average divided by `SUBCONDUCTORS_PER_PHASE` (per-conductor amps; before then, the midpoint of that table's range), labeled as derived rather than independently sourced per-city — see the in-file comments for detail and next steps if a more precise citation is wanted later.
- `CITY_COORDINATES`, `LOCATIONS`, `CITY_LINE_BEARING_DEG`, `RATING_BOUNDS_BY_LOCATION` — the per-city point tables (C8). `LOCATIONS` (the four city keys) replaces the retired `CORRIDOR_ENDPOINTS`; each city is one independent rating point with its own coordinate, static rating, plausibility bounds and line bearing, and nothing is reduced across cities (see `decisions/point_scope.md`, retired 2026-10-12). `CITY_LINE_BEARING_DEG` values are carried over from the retired corridor bearings and are an assumption, not a measurement. `LEGACY_CORRIDOR_ENDPOINTS` keeps the old pairing only for the frozen forecast-correction experiment modules; no other module may read it. Per-city static ratings are no longer reduced by a corridor `min()`, so Corpus Christi is 3000 A and El Paso 1450 A.
- Per-city model and ERCOT-zone settings: `FORECAST_ML_MODEL_FILENAME_TEMPLATE` (`forecast_{city}.joblib`), `FORECAST_ML_TRAINING_FRAME_TEMPLATE`, `ANOMALY_ML_MODEL_FILENAME_TEMPLATE` (`anomaly_{city}.joblib`), `ANOMALY_ML_OBSERVATION_FRAME_TEMPLATE` and `ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CITY` (Austin and Corpus Christi `SOUTH`; Midland and El Paso `WEST`). Placeholders are formatted only after the city is checked against `LOCATIONS`.
- `DEFAULT_STATIC_RATING = 900.0` — fallback for any location not in `STATIC_RATINGS`.
- `DEFAULT_CONDUCTOR_CONFIG_KWARGS` — the `ConductorConfig` kwargs previously hardcoded in `dlr_pipeline.py`'s `__main__`.
- `DEFAULT_STATION_SOURCE`, `DEFAULT_START`, `DEFAULT_END` — moved unchanged from `dlr_pipeline.py`'s `__main__`.
- `LINE_VOLTAGE_KV = 345.0`, `POWER_FACTOR = 0.95` — moved from `ercot_dlr_merger.py`'s module-level constants.

`backend/dlr_pipeline.py`'s `__main__` and `backend/ercot_dlr_merger.py` both import from `config.py` now instead of holding independent literals — this directly fixes the "two independent `900.0` A literals" known issue below. Runtime values are unchanged from before this component landed; only their source changed.

Per-city selection is wired: `dlr_pipeline.py` (`run_pipeline`, `plot_dlr_summary`) and `ercot_dlr_merger.py` take a `city` argument and use `config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)`; `DEFAULT_STATIC_RATING` is only the fallback for an unrecognised or omitted city.

## Interface & Data Contract

`backend/config.py`, importable as `import config` from any script co-located in `backend/` (or via `pythonpath = backend` in `pytest.ini` for tests). Importing it has no side effects (no file I/O, no network calls).

## Blocked by

None — this is a foundation component.

## Blocks

- **C2** (data contract needs to know the config's shape to validate config-derived fields, e.g. `static_capacity_mw` bounds)
- **C4** (weather ingestion needs the station source + date window)
- **C5** (thermal model needs `ConductorConfig` values)
- **C6** (ERCOT retriever needs the date window; merger needs the static rating)
- Transitively, everything downstream of C4/C5/C6 in Phase 3–4 (including C7, which needs `static_rating` for its fallback value — reached via C5, not directly)

## Parallel-safe with

C2, C3 — all three are Phase 1 and touch different concerns (config values vs. schema vs. export format), though C2 and C3 will want to know what shape C1 lands on before finalizing.

## Known Issues

- ~~The two independent `900.0` A literals...~~ **Fixed** — both files now import `config.DEFAULT_STATIC_RATING`.
- ~~`STATIC_RATINGS` exists but nothing selects a per-city entry per run.~~ **Fixed** — `dlr_pipeline.py` and `ercot_dlr_merger.py` look up `STATIC_RATINGS` by `city`; `DEFAULT_STATIC_RATING` remains the fallback when `city` is omitted or unknown.
- `backend/ercot_data_retriever.py`'s own hardcoded date window (`"2025-07-01"` to `"2025-07-05"` in its `__main__`) was NOT moved into `config.py` — it's a separate, still-hardcoded literal that can still drift from `config.DEFAULT_START`/`DEFAULT_END`. Out of scope for this implementation pass; flagged for a future pass.

## Acceptance Criteria

- ✅ A single change to a static rating (per location) is reflected in every module that computes headroom or fallback — no literal duplicated elsewhere. (True for the two fixed literals; `ercot_data_retriever.py`'s date window is the one remaining exception, see Known Issues.)
- ⚠️ `backend/dlr_pipeline.py` and `backend/ercot_data_retriever.py` read the same date window from the same source when run together for the same analysis. **Not yet met** — see Known Issues above.
- ✅ Config values are loadable without importing `backend/dlr_pipeline.py`'s `__main__` block (i.e., no side effects from importing the config). Verified: `config.py` has zero side effects at import time.

## Open Questions

- Config format/location — no strong constraint from the existing code, team's call.
- Should conductor properties be per-city (multiple conductor types across different locations) or a single global default as today? Only the line azimuth is per-city today (`CITY_LINE_BEARING_DEG`), and those values are an assumption (see `decisions/point_scope.md`).
