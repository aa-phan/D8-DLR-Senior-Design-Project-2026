# C8 — City Point Rating

**Phase:** 3 (Safety & Spatial) · **Effort:** L (original corridor build) · **Status:** Re-scoped 2026-10-12. The corridor model is **retired**; each of the four project cities (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`) is one independent rating point. The contract is `docs/data-science/decisions/point_scope.md`; this spec describes the API that contract names (`city_point.city_point`, `city_rating.rate_city`, `config.LOCATIONS`). The code migration was still in progress when this page was written — treat `point_scope.md` as authoritative if the two ever disagree, and see Known Issues for what is not done yet.

**Responsibility:** Resolve a city into a single rating point (coordinate, static rating, plausibility bounds, line bearing, conductor), and produce that city's rating from its nearest usable station observation, gated through C7's safety monitor. There is no spatial discretization, no pairing of cities and no `min()` reduction across points.

History: until 2026-10-11 this component was "Corridor Spatial Discretization" — two city-to-city corridors (`AUSTIN_CORPUS_CHRISTI`, `MIDLAND_EL_PASO`) interpolated along a great-circle arc into five points each, with the corridor rating taken as the minimum across points. That model was retired 2026-10-12; see `point_scope.md` for the decision and `decisions/geographic_scope.md` for the earlier corridor-era log. The modules `corridor_discretization.py` and `corridor_pipeline.py` and their tests were removed.

## Current Implementation

**`backend/city_point.py`**

- `city_point(city) -> CityPoint` resolves a key of `config.LOCATIONS` into a `CityPoint` carrying: `name`, `coord` (`config.CITY_COORDINATES[city]`), `bearing_deg` (`config.CITY_LINE_BEARING_DEG[city]`), a `thermal_model.ConductorConfig` built with that bearing (via `config.conductor_kwargs_for`), `static_rating` (`config.STATIC_RATINGS[city]`) and `rating_bounds` (`config.RATING_BOUNDS_BY_LOCATION[city]`).
- An unknown key raises `KeyError` naming the valid cities. This is also the closed-set guard that model-artifact path builders (C9, C10) rely on.
- Importing the module has no side effects.

**`backend/city_rating.py::rate_city`** (named by the contract; replaces `corridor_discretization.rate_corridor`)

- Resolves the city's nearest usable station observation, runs it through `DLRSafetyMonitor.run_check` (C7, which uses C5's ampacity) with the city's own static rating, optionally archives one row (`historical_archive.append_observation`), and returns a per-city dict.
- The probe/fallback behavior of the old per-point lookup is kept: candidate stations are probed in batches, and a city that exhausts every candidate falls back to its static rating rather than being dropped or interpolated.
- Signature: `rate_city(city, start, end, stations, fetch_weather=None, logger=None, sleep=time.sleep, anomaly_detector=None, archive=True, archive_path=None, provider="synoptic") -> dict`. With `provider` `open_meteo` or `nsrdb` it fetches once at the city's coordinate instead of probing stations. Probing starts with the nearest `PROBE_BATCH_SIZE` (5) candidates and expands to `MAX_PROBE_CANDIDATES` (10), pausing between batches.
- Returned keys: `city`, `point` (`(lat, lon)`), `station_id` (`None` when exhausted), `candidates_probed`, `probe_trail`, `rating`, `status`, `fallback`, `alerts`, `observation`, `exhausted`, `archived`. There are no corridor-level fields: nothing like `bottleneck_index`, `points` or a cross-city `min()` exists (`point_scope.md`, Conventions 2 and 5).
- Each call builds a fresh `DLRSafetyMonitor` with `delta_fraction=inf`, so C7's G5 delta check cannot trip within a single-observation call (as in the corridor-era code). An optional C10 `anomaly_detector` is forwarded as G6.
- Archive rows (`historical_archive`) are one per city per run. The archive's `corridor` column is now `city`; corridor-era archive files (header has `corridor`) remain readable, and the always-null `bottleneck_index` column was dropped on 2026-10-13 (older files that still carry it remain readable and are appended in their own header order).
- Importing the module has no side effects and needs no `SYNOPTIC_TOKEN`.

**Per-city configuration (`backend/config.py`)**

| Name | Meaning |
|---|---|
| `LOCATIONS` | The four city keys; replaces `CORRIDOR_ENDPOINTS` |
| `CITY_COORDINATES[city]` | One lat/lon per city |
| `STATIC_RATINGS[city]` | Per-city static rating in per-conductor amps: Austin 1825, Corpus Christi 1500, Midland 1875, El Paso 1320 (2026-10-13; bundle averages 3650, 3000, 3750, 1320 A divided by the subconductor counts) |
| `RATING_BOUNDS_BY_LOCATION[city]` | Per-city plausibility bounds for C7's G4 (previously the min of two cities' bounds) |
| `CITY_LINE_BEARING_DEG[city]` | Line azimuth for the perpendicular-wind component. **Assumption**: carried over from the retired corridor bearings (Austin and Corpus Christi 173.15 deg, Midland and El Paso 267.54 deg) so wind-cooling behavior is unchanged. A point has no line direction of its own |
| `LEGACY_CORRIDOR_ENDPOINTS` | Retired pairing, kept only for the frozen forecast-correction experiment modules (`forecast_experiment*.py`, `legacy_corridor.py`). Nothing else may import it |

**Shadow collection:** the shadow collector iterates `config.LOCATIONS` (four cities) and keeps the inter-city request delay. Logs are one file per city, `data/shadow/predictions/{CITY}.jsonl`, with `city` replacing the old `corridor` field and `schema_version: 3`. The old `AUSTIN_CORPUS_CHRISTI.jsonl` and `MIDLAND_EL_PASO.jsonl` are legacy corridor-era files, left untouched; readers must tolerate them and must not mix their rows into per-city evaluation.

The older `backend/station_explorer.py::CORRIDORS` (five hardcoded `(lat, lon)` tuples) is separate and unchanged: it is used only for ranking stations by proximity and is not part of this component.

## Interface & Data Contract

- Input: a city key in `config.LOCATIONS`. Every parameter, key, file suffix or record field formerly named `corridor` is now `city` (`point_scope.md`, Convention 1).
- `city_point(city)` returns a `CityPoint`; `rate_city` returns a per-city in-process dict. The only persisted record of a rating call is the optional archive row, not a file feed.
- Weather comes through C4's `weather_provider.fetch_weather` / station probing, ampacity through C7/C5. Nothing reduces across cities.
- ERCOT zone selection is per city (`config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CITY`): Austin and Corpus Christi `SOUTH`, Midland and El Paso `WEST`.

## Blocked by

**C4** (weather ingestion) and **C5** (ampacity, via C7's monitor) — both satisfied. Per-city gating uses C7's `DLRSafetyMonitor`, so this component depends on C7 as well. Build against C4's adapter interface, not directly against a provider.

## Blocks

C9 (ampacity forecasting), C10 (anomaly detection) and the shadow-forecast pipeline key their models, training frames and logs by the city defined here.

## Parallel-safe with

**C7** — C8 builds on C7's monitor; no shared files.

## Known Issues

- **Line bearing is an assumption.** The per-city bearings are carried over from the retired corridors, not measured. Replace them with real line orientation when known (`point_scope.md`, Open Questions).
- **Per-city model refit status.** The "ml" forecaster and the anomaly models were refit per city on 2026-10-13 (`docs/data-science/decisions/forecasting_model.md`, `docs/data-science/decisions/anomaly_detection_model.md`); those artifacts are git-ignored (`data/models/`), so a clean checkout or CI still has none and `method="ml"` raises the existing `FileNotFoundError`. The shadow correction models' refit status is as recorded in `docs/data-science/decisions/point_scope.md` (2026-10-12).
- **Legacy corridor-named artifacts and logs are retained, not loaded.** `data/models/anomaly_{CORRIDOR}.joblib` (no corridor-named `forecast_*.joblib` is present), `data/shadow/models/*_{CORRIDOR}.joblib` and the two corridor-named shadow logs remain on disk as history.
- **Shadow-evidence baseline.** Per-city logs began empty on 2026-10-12, so evidence has accumulated only since then (4 cycles/day, underlying weather model `gfs_seamless`, since 2026-10-13). The evaluation instant stays 2026-11-24 under the draft per-city confirmation protocol, which is not yet signed.
- No real transmission-line geometry is used or needed by the per-city model. The 2026-10-12 retirement also retires the `corridor-geometry` workstream documents.

## Acceptance Criteria

- `city_point.city_point` returns a `CityPoint` with the city's own coordinate, static rating, bounds and bearing for every key in `config.LOCATIONS`, and raises `KeyError` naming valid cities for anything else (`backend/tests/city_point_test.py`).
- `rate_city` for one city never reads another city's rating, bounds or observation, and produces no cross-city `min()`.
- A city whose station candidates are all unusable falls back to its own static rating rather than being dropped.
- No production, shadow or training module imports `legacy_corridor.py` or `config.LEGACY_CORRIDOR_ENDPOINTS`.

## Open Questions

- Real per-city line orientation (replaces the carried-over bearings).
- Whether the shadow-evaluation date (2026-11-24) is re-baselined against per-city collection.
- When, and against what data, the per-city models are refit.
