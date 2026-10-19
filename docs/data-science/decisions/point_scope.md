# Point (Per-City) Scope Decision

**Status:** Adopted 2026-10-12. Supersedes the corridor model recorded in `geographic_scope.md` (C8) and used by the shadow pipeline, training modules and anomaly detector through 2026-10-11.

**Decision:** The project no longer rates transmission corridors. Each of the four project cities — `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO` — is one independent rating **point**. There is no pairing of cities, no spatial discretization between them, and no `min()` reduction across points.

## What a point is

| Property | Source | Notes |
|---|---|---|
| Location | `config.CITY_COORDINATES[city]` | One lat/lon per city |
| Static rating | `config.STATIC_RATINGS[city]` | Previously a corridor used `min()` of its two endpoint cities. Values changed again on 2026-10-13 (owner decision): per-conductor amps = owner-supplied 345 kV bundle average / subconductors per phase, i.e. Austin 1825, Corpus Christi 1500, Midland 1875, El Paso 1320 (before: 1900, 3000, 1800, 1450, midpoints of the Project Definition ranges). They affect headroom %, the static fallback and retained-capacity reporting only, not any model target or artifact |
| Plausibility bounds | `config.RATING_BOUNDS_BY_LOCATION[city]` | Previously the min of the two endpoint cities' bounds |
| Line bearing | `config.CITY_LINE_BEARING_DEG[city]` | **Assumption**: carried over from the retired corridor bearings (Austin and Corpus Christi 173.15°, Midland and El Paso 267.54°) so perpendicular-wind behavior is unchanged. A point has no line direction of its own |
| Resolver | `city_point.city_point(city)` → `CityPoint` | Replaces `corridor_discretization.corridor_geometry`. Raises `KeyError` naming valid cities for an unknown key (also the closed-set guard for model-artifact paths) |
| City list | `config.LOCATIONS` | Replaces `config.CORRIDOR_ENDPOINTS` |

## Conventions every module follows

1. A parameter, key, file suffix or record field formerly named `corridor` is now `city`. Valid values are exactly `config.LOCATIONS`.
2. Nothing reduces across cities. Remove `bottleneck_index`, `bottleneck_city`, `per_city_ampacity_amps`, `endpoint_city`/`endpoint_indicator` pooling across two cities, and corridor-level `min()`.
3. **Shadow logs:** one file per city, `data/shadow/predictions/{CITY}.jsonl`. Records carry `city` where they carried `corridor`, and `schema_version: 3`. Existing `AUSTIN_CORPUS_CHRISTI.jsonl` and `MIDLAND_EL_PASO.jsonl` are **legacy**: left untouched, documented as the corridor-era schema (v1 flat rows and v2). Readers that scan logs must tolerate legacy files and must not mix legacy corridor rows into per-city evaluation.
4. **Model artifacts** are per city: `forecast_{city}.joblib`, `anomaly_{city}.joblib`, `data/shadow/models/{method}_{CITY}.joblib`. Per-city fits use one city's own rows (`pooling="per_city"` for the wind/cooling correction models; the "ml", anomaly and `reference_ml_refit_24h` targets are that city's own ampacity, not a minimum). Existing corridor-named artifacts are legacy and are not loaded. Until per-city models are refit, the ML shadow candidates report `status="unavailable"` with a named reason (the existing `FileNotFoundError` path).
5. **Per-city rating** (`city_rating.rate_city`) replaces `corridor_discretization.rate_corridor`: resolve the city's nearest usable station observation, run it through `DLRSafetyMonitor` with the city's static rating, optionally archive one row, and return a per-city dict. The probe/fallback behavior of the old per-point lookup is kept.
6. The shadow collector iterates `config.LOCATIONS` (four cities), keeping the inter-city request delay.
7. ERCOT zone selection is per city (`config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CITY`): Austin and Corpus Christi `SOUTH`; Midland and El Paso `WEST`.

## Frozen, not migrated

The 2026 forecast-correction experiment (`forecast_experiment.py`, `forecast_experiment_audit.py`, their tests, and the `decisions/forecast_correction_*` records) reproduces a completed corridor-based study. It is kept as a historical record and now imports `legacy_corridor.py` and `config.LEGACY_CORRIDOR_ENDPOINTS`. Nothing else may import either.

## Removed

`backend/corridor_discretization.py`, `backend/corridor_pipeline.py`, their tests, and the C8 corridor-discretization spec (C8 is now "City Point Rating"). The `workstreams/corridor-geometry/` documents are retired.

## Open Questions

- **Line bearing per city.** The carried-over bearings are an assumption, not a measurement. Replace with real line orientation when known.
- **Re-baselining shadow evidence.** Per-city logs start empty; the 2026-11-24 evaluation date was set against corridor-level collection. Whether it moves is a team decision.
- **Per-city refit.** Done 2026-10-12 offline from the cached experiment frames (`backend/forecast_shadow_fit_models.py`). The wind and cooling models are fit on train + validation rather than train only, a documented choice made after model selection finished; see the runbook's "Fit-window decision" before quoting any performance figure for them.
