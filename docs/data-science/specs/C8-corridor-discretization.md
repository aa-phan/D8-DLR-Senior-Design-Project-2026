# C8 — Corridor Spatial Discretization

**Phase:** 3 (Safety & Spatial) · **Effort:** L · **Status:** Implemented in `backend/corridor_discretization.py` for two city-to-city corridors on great-circle geometry (real transmission-line geometry is still future work). Earlier versions of this spec and the System Design Report (§3.2, "Weather Data and Transmission Corridor Mapping") described this as not started; see `PRD.md` §10 Documentation Discrepancies for the history. Note: 23 tests in `backend/tests/corridor_discretization_test.py` currently fail (undiagnosed — see Known Issues).

**Responsibility:** Represent a transmission corridor as multiple geographic points along its real (or, initially, synthetic) route between substation endpoints, compute ampacity independently at each point, and report the corridor-level rating as the **minimum** across all points — the true thermal bottleneck, since a line is only as strong as its weakest span.

## Current Implementation

`backend/corridor_discretization.py`:

- `config.CORRIDOR_ENDPOINTS` defines two corridors by city endpoints: `AUSTIN_CORPUS_CHRISTI` and `MIDLAND_EL_PASO`.
- `interpolate_great_circle` / `discretize_corridor` place `DEFAULT_POINTS_PER_CORRIDOR` (5: two endpoints plus three evenly spaced interior points) along the great-circle arc; `corridor_geometry(name, n_points)` returns a `CorridorGeometry` (endpoints, points, bearing, `ConductorConfig` carrying that bearing, static rating, rating bounds).
- `resolve_point_observation` probes the nearest `PROBE_BATCH_SIZE` (5) candidate stations per point and expands to `MAX_PROBE_CANDIDATES` (10) before giving up, pausing `PROBE_BATCH_PAUSE_S` between batches. A point that exhausts every candidate falls back to the static rating rather than being dropped or interpolated.
- `rate_corridor(corridor_name, start, end, stations, ..., provider="synoptic")` runs each point's reading through `DLRSafetyMonitor.run_check` (C7, which uses C5's ampacity), then reduces to the corridor rating with `min()`. Returns `corridor`, `bearing_deg`, `points`, `rating`, `bottleneck_index`, `fallback`, `exhausted_points`, `archived`. With `provider` `open_meteo` or `nsrdb` it fetches by point coordinates instead of probing stations.
- Each call can append one row to the historical archive (`_archive_corridor_result` → `historical_archive.append_observation`).
- Importing the module has no side effects and needs no `SYNOPTIC_TOKEN`.

The older `backend/station_explorer.py::CORRIDORS` (five hardcoded `(lat, lon)` tuples) is still used only for ranking stations by proximity, separately from this component.

## Interface & Data Contract

The corridor definition is two city keys in `config.CORRIDOR_ENDPOINTS`; geometry is a straight great-circle line between them (the System Design Report's "synthetically connected substation coordinates"). Real transmission-line geometry (e.g. GIS shapefiles) is not implemented.

Output of `rate_corridor` is an in-process dict (see Current Implementation); the only persisted record is the archive row, not a file feed. Weather comes through C4's `weather_provider.fetch_weather`, per-point ampacity through C7/C5, and the corridor rating is `min()` across points — analogous to C6's hourly `.min()` in `backend/ercot_dlr_merger.py::process_dlr_to_hourly`, on the space axis instead of the time axis.

## Blocked by

**C4** (weather ingestion, called once per corridor point) and **C5** (ampacity, via C7's monitor) — both satisfied. Note: the implementation does use C7's `DLRSafetyMonitor` for per-point gating, so it now depends on C7 as well.

Also implicitly depends on the weather-provider decision remaining unresolved being a non-issue — see `PRD.md` §7.1 and C4's adapter-interface mitigation. C8 should build against C4's interface, not directly against Synoptic, so it's insulated from that decision.

## Blocks

C9 (ampacity forecasting) and the shadow-forecast pipeline use corridors as defined here.

## Parallel-safe with

**C7** — C8 builds on C7's monitor; no shared files.

## Known Issues

- 23 of 52 tests in `backend/tests/corridor_discretization_test.py` fail as of 2026-10-08 (e.g. `test_rate_corridor_archived_datetime_equals_end_and_two_calls_are_identical`: an injected `fetch_weather` is called 0 times where 5 are expected). Not yet diagnosed.
- Geometry is straight-line only; no real transmission geometry.

## Acceptance Criteria

Adapted from System Design Report §3.3's validation plan:

- Running the full spatial pipeline on a synthetic corridor confirms weather data is correctly fetched and assigned to each corridor point, and fed into the IEEE 738 calculator (C5) at each point.
- Minimum-ampacity logic is verified by artificially "cooling" one corridor segment (e.g. injecting a lower wind value at one point) and confirming the system correctly identifies it as the bottleneck.
- Once real transmission-line geometry is available (out of scope for the initial build): rerun against actual ERCOT transmission data and confirm results are reasonable and consistent with published SLR values for those lines.

## Open Questions

- Real geometry source — the System Design Report mentions GIS shapefiles as the eventual replacement for synthetic substation-to-substation lines; no such data source exists in this repo today. Where does it come from?
- How many points per corridor is enough to catch a real bottleneck without excessive API calls against a rate-limited weather provider (see C4's known issues on Synoptic's free-tier limits)?
- Does C8 call C4/C5 per-point synchronously, or does it need a batched/parallel fetch pattern given N points × however many corridors?
