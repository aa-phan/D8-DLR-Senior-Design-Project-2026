"""
Corridor Spatial Discretization (C8)
==================================================
This module is C8 per `docs/data-science/specs/C8-corridor-discretization.md`.

It turns a corridor from a name into a rated line: a corridor is defined by
two city endpoints (`config.CORRIDOR_ENDPOINTS`), discretized into several
geodesic points along the great circle between them, resolved point-by-point
to a nearby weather station, fed through the same fail-safe safety monitor
C7 uses, and reduced to a corridor-level rating via the minimum across all
points -- the true thermal bottleneck, since a line is only as strong as its
weakest span (D-04/D-05).

This module composes three already-existing patterns rather than
reimplementing them: `station_explorer.py::haversine_km`'s stdlib-`math`
great-circle style, `station_explorer.py`'s proximity-ranking pattern
(generalized here from "rank near 5 fixed points" to "rank near any point"
via `station_explorer.nearest_stations`), and
`ercot_dlr_merger.py::process_dlr_to_hourly`'s `.min()` weakest-link
reduction (same principle, space axis instead of time axis). Every ampacity
value in this module comes from `DLRSafetyMonitor.run_check`, which is
already wired to the real thermal model's ampacity function (C7, Plan
03-01) -- this module does not compute ampacity itself and does not call
`thermal_model` directly (only for `ConductorConfig`).

Importing this module has no side effects (no file I/O, no network calls)
and needs no `SYNOPTIC_TOKEN` -- all weather access happens lazily inside
`rate_corridor`, through `weather_provider.fetch_weather` (D-07), never
through the Synoptic-only fetch function on `dlr_pipeline` directly.
"""

import logging
import math
import time

import config
import station_explorer
import thermal_model
import weather_provider
from DLRSafetyMonitor import DLRSafetyMonitor

# Module logger, matching the convention `dlr_pipeline.py` already uses
# (`log = logging.getLogger(__name__)`, called as `log.info(...)`) --
# `resolve_point_observation`'s probe logging defaults to this when no
# `logger` is injected.
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Discretization density
# ──────────────────────────────────────────────────────────────────────────────
# 2 endpoints + 3 interior points, evenly spaced along the great-circle arc
# (D-04). Balances bottleneck-detection resolution against per-run API call
# volume: more points means finer-grained bottleneck detection, but each
# point costs one independent weather fetch (D-05) -- 5 points/corridor x 2
# corridors = 10 fetches/run today, before D-08's candidate-probe fallback
# (Plan 03-03) can multiply that further.
DEFAULT_POINTS_PER_CORRIDOR = 5

# ──────────────────────────────────────────────────────────────────────────────
# Candidate-probe tuning (D-08, Plan 03-03)
# ──────────────────────────────────────────────────────────────────────────────
# D-06's live access check found Synoptic returns a usable (non-null)
# observation for only 25-75% of candidate stations depending on the city
# (Austin 75%, Corpus Christi 25%, Midland 25%, El Paso 38%, across 8 probed
# stations per city -- .planning/phases/03-safety-spatial/03-CONTEXT.md
# D-06). A single-nearest-station lookup would leave Corpus Christi/Midland
# corridors dark most of the time, so each point probes its nearest 5
# candidates first and, only if all 5 are unusable, expands to the next 5
# nearest (10 total) before giving up (D-08/D-09).
PROBE_BATCH_SIZE = 5
MAX_PROBE_CANDIDATES = 10

# Small pause between probe batches so a worst-case run doesn't burst
# unspaced requests at the provider (RESEARCH.md Pitfall 3: 5 points x 2
# corridors x 10 candidates = 100 station-level fetch attempts per run,
# against C4's own still-open "no retry/backoff or rate-limit handling"
# issue). Defined here, alongside the other probe-tuning constants, so
# Task 3's pacing has exactly one call site; the actual `sleep()` call is
# wired into `resolve_point_observation` in Task 3.
PROBE_BATCH_PAUSE_S = 0.2


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Forward azimuth (initial compass bearing, degrees) from point 1 to point
    2 along the great circle connecting them. Standard formula, stdlib
    `math` only -- matches `station_explorer.haversine_km`'s style; no geo
    library is used or needed.

    Returns a value in [0, 360).
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    theta = math.atan2(y, x)
    return (math.degrees(theta) + 360) % 360


def interpolate_great_circle(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float
) -> tuple[float, float]:
    """
    Standard great-circle intermediate-point formula: the point that lies
    `fraction` of the way along the great-circle arc from (lat1, lon1) to
    (lat2, lon2). `fraction=0.0` returns point 1 exactly; `fraction=1.0`
    returns point 2 exactly.

    On a great circle, an equal fraction of the arc IS an equal fraction of
    the distance -- so this single formula satisfies both the "equal
    fraction of arc" and "equal distance" readings of D-04's "evenly spaced"
    requirement; CONTEXT.md left the exact interpolation choice to
    discretion, and this identity is why no separate distance-based
    interpolation is needed.

    The central angle `d` below is `station_explorer.haversine_km`'s own
    `2 * asin(sqrt(a))` expression, without that function's Earth-radius
    factor (`d` is in radians here, not km) -- same haversine math, same
    style, different final scaling.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    lam1, lam2 = math.radians(lon1), math.radians(lon2)

    a = (
        math.sin((phi2 - phi1) / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin((lam2 - lam1) / 2) ** 2
    )
    d = 2 * math.asin(math.sqrt(a))

    # Identical endpoints -> zero arc length. Guard the division before it
    # happens, rather than letting sin(d)=0 raise ZeroDivisionError.
    if d == 0:
        return (lat1, lon1)

    A = math.sin((1 - fraction) * d) / math.sin(d)
    B = math.sin(fraction * d) / math.sin(d)
    x = A * math.cos(phi1) * math.cos(lam1) + B * math.cos(phi2) * math.cos(lam2)
    y = A * math.cos(phi1) * math.sin(lam1) + B * math.cos(phi2) * math.sin(lam2)
    z = A * math.sin(phi1) + B * math.sin(phi2)
    phi_i = math.atan2(z, math.sqrt(x**2 + y**2))
    lam_i = math.atan2(y, x)
    return (math.degrees(phi_i), math.degrees(lam_i))


def discretize_corridor(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    n_points: int = DEFAULT_POINTS_PER_CORRIDOR,
) -> list[tuple[float, float]]:
    """
    Discretize the great-circle corridor between (lat1, lon1) and
    (lat2, lon2) into `n_points` evenly-spaced points (D-03/D-04).

    `result[0]` is always endpoint A exactly; `result[-1]` is always
    endpoint B exactly (when `n_points >= 2`).

    Raises:
        ValueError: if `n_points < 1` -- an empty corridor has no
            defensible minimum and must not silently return `[]`.
    """
    if n_points < 1:
        raise ValueError(f"n_points must be >= 1, got {n_points}")

    if n_points == 1:
        return [(lat1, lon1)]

    return [
        interpolate_great_circle(lat1, lon1, lat2, lon2, i / (n_points - 1))
        for i in range(n_points)
    ]


class CorridorGeometry:
    """
    A corridor's resolved geometry: its endpoints, discretized points, its
    own computed bearing, a `ConductorConfig` carrying that bearing, and the
    corridor-level static rating/plausibility bounds. Plain-class,
    explicit-`__init__` style matching `thermal_model.ConductorConfig`.
    """

    def __init__(
        self,
        name: str,
        endpoint_keys: tuple[str, str],
        endpoint_coords: tuple[tuple[float, float], tuple[float, float]],
        points: list[tuple[float, float]],
        bearing_deg: float,
        conductor: thermal_model.ConductorConfig,
        static_rating: float,
        rating_bounds: tuple[float, float],
    ):
        self.name = name
        self.endpoint_keys = endpoint_keys
        self.endpoint_coords = endpoint_coords
        self.points = points
        self.bearing_deg = bearing_deg
        self.conductor = conductor
        self.static_rating = static_rating
        self.rating_bounds = rating_bounds


def corridor_geometry(
    corridor_name: str, n_points: int = DEFAULT_POINTS_PER_CORRIDOR
) -> CorridorGeometry:
    """
    Resolve a named corridor (a key in `config.CORRIDOR_ENDPOINTS`) into its
    full geometry: endpoints, discretized points, computed bearing, a
    per-corridor `ConductorConfig`, and the corridor's static rating/bounds.

    Per 03-RESEARCH Pattern 2, the two D-01 corridors differ by roughly 95
    degrees of bearing (Austin-to-Corpus-Christi runs near north-south,
    Midland-to-El-Paso runs near east-west) -- reusing one global
    `line_azimuth` (the module default of 90.0) would systematically
    mis-model wind cooling on whichever corridor isn't near-east-west. Each
    corridor's bearing is computed here from its own endpoints via
    `initial_bearing_deg` and passed through `config.conductor_kwargs_for`.

    The corridor-level static rating and rating bounds take the MORE
    CONSERVATIVE of the two endpoint cities: `min()` of the two
    `STATIC_RATINGS` values, and `(min of the two lower bounds, min of the
    two upper bounds)`. A corridor is only as strong as its weakest end --
    the same weakest-link principle the point-level `min()` reduction in
    `rate_corridor` (Task 2) applies spatially along the corridor.

    Raises:
        KeyError: if `corridor_name` is not in `config.CORRIDOR_ENDPOINTS`,
            naming the valid corridor names.
    """
    if corridor_name not in config.CORRIDOR_ENDPOINTS:
        raise KeyError(
            f"Unknown corridor {corridor_name!r}. Valid corridors: "
            f"{sorted(config.CORRIDOR_ENDPOINTS)}"
        )

    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor_name]
    coord_a = config.CITY_COORDINATES[city_a]
    coord_b = config.CITY_COORDINATES[city_b]

    bearing_deg = initial_bearing_deg(coord_a[0], coord_a[1], coord_b[0], coord_b[1])
    conductor = thermal_model.ConductorConfig(**config.conductor_kwargs_for(bearing_deg))

    points = discretize_corridor(coord_a[0], coord_a[1], coord_b[0], coord_b[1], n_points)

    static_rating = min(config.STATIC_RATINGS[city_a], config.STATIC_RATINGS[city_b])
    bounds_a = config.RATING_BOUNDS_BY_LOCATION[city_a]
    bounds_b = config.RATING_BOUNDS_BY_LOCATION[city_b]
    rating_bounds = (min(bounds_a[0], bounds_b[0]), min(bounds_a[1], bounds_b[1]))

    return CorridorGeometry(
        name=corridor_name,
        endpoint_keys=(city_a, city_b),
        endpoint_coords=(coord_a, coord_b),
        points=points,
        bearing_deg=bearing_deg,
        conductor=conductor,
        static_rating=static_rating,
        rating_bounds=rating_bounds,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Per-point weather -> per-point ampacity -> corridor minimum
# ──────────────────────────────────────────────────────────────────────────────

# Maps the weather-pipeline schema's column names to DLRSafetyMonitor's
# reading keys. Kept in one place so Plan 03-03's candidate probe reuses it
# rather than duplicating the mapping.
_OBSERVATION_FIELD_MAP = {
    "air_temp": "temp",
    "wind_speed": "wind",
    "solar_radiation": "solar",
}


def _usable_observation(frame, stid: str) -> dict | None:
    """
    Extract the reading dict `DLRSafetyMonitor.run_check` needs for one
    station from a weather-pipeline DataFrame (the shape
    `weather_provider.fetch_weather` returns).

    Returns `None` when the frame is empty, the station is absent, or any
    of `air_temp`/`wind_speed`/`solar_radiation` is null for that station's
    row(s) -- a partially-null reading is not usable, and forcing it
    through the monitor as `None` would trip G1 (sensor availability)
    anyway. When usable, returns a dict with `sensor_status` and
    `link_status` both set to `"ok"` (G1/G2 pass), plus `temp`/`wind`/
    `solar` mapped per `_OBSERVATION_FIELD_MAP`.
    """
    if frame is None or frame.empty:
        return None

    if "stid" in frame.columns:
        rows = frame[frame["stid"] == stid]
    else:
        # Some callers may pass an already-filtered, stid-indexed frame.
        rows = frame

    if rows.empty:
        return None

    row = rows.iloc[0]

    reading: dict = {"sensor_status": "ok", "link_status": "ok"}
    for source_col, target_key in _OBSERVATION_FIELD_MAP.items():
        if source_col not in row.index:
            return None
        value = row[source_col]
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        reading[target_key] = value

    return reading


def discover_corridor_stations(token: str, state: str = "TX"):
    """
    D-06's broadened, unrestricted-network station discovery: delegates to
    `station_explorer.get_all_stations` with no network restriction, so this
    module has exactly one call site for the "don't restrict to WTM"
    decision rather than each caller re-deriving it.

    D-06 reverses the WTM-only restriction that `station_explorer.py`'s
    `__main__` block previously hardcoded (`network_id = 152`): a live
    access check found that restriction admitted just 2 stations (both
    zero-data), where the unrestricted query resolves to hundreds of
    solar-tagged candidates per city (Austin 628, Corpus Christi 64,
    Midland 30, El Paso 94 within 50km, per
    `.planning/phases/03-safety-spatial/03-CONTEXT.md` D-06). `state` is
    accepted for interface symmetry with a future per-state discovery need,
    but `station_explorer.get_all_stations` itself always queries `state=TX`
    today (left untouched per this plan's own prohibition on widening that
    function's scope).
    """
    return station_explorer.get_all_stations(token, network_id=None)


def resolve_point_observation(
    lat: float,
    lon: float,
    start: str,
    end: str,
    stations,
    fetch_weather,
    batch_size: int = PROBE_BATCH_SIZE,
    max_candidates: int = MAX_PROBE_CANDIDATES,
    logger=None,
):
    """
    D-08's bounded candidate probe for one corridor point: rank up to
    `max_candidates` nearest stations to (lat, lon) once (so a later batch
    is genuinely the next-nearest stations, never a re-probe of an earlier
    batch), then probe them in order, `batch_size` at a time, stopping at
    the first usable reading. Never probes an (`max_candidates` + 1)-th
    candidate.

    Each candidate's `fetch_weather` result is converted through
    `_usable_observation` -- an empty frame, a frame missing the station, or
    a frame with any of the three required variables null is all treated as
    unusable, exactly like the single-nearest-station lookup 03-02 shipped.
    A `fetch_weather` call that itself raises is also treated as unusable
    (the probe moves to the next candidate rather than propagating the
    exception); only the exception's message text is logged, never its full
    repr (T-03-02 -- a full repr could echo request/params state).

    Args:
        lat, lon: The corridor point's coordinates.
        start, end: The weather-fetch date window, passed through unchanged.
        stations: A station metadata DataFrame (`station_explorer`'s shape).
        fetch_weather: `(stids, start, end) -> DataFrame`, called once per
            candidate with a single-element `stids` list -- never a batch
            fetch across candidates (D-05's per-point independence extends
            to per-candidate independence within a point).
        batch_size: Candidates probed per batch before pausing/expanding.
        max_candidates: Hard ceiling on candidates probed for this point.
        logger: Injectable `logging.Logger`-like object (must support
            `.info(...)`), defaulting to this module's own logger --
            matches `dlr_pipeline`'s `log = logging.getLogger(__name__)`
            convention. Every log line here carries only a station id,
            latitude, longitude, distance in km, and a usable/unusable
            outcome word -- never a params dict, grouped fetch arguments, or
            a caught exception's full repr (T-03-02).

    Returns:
        `(observation, stid, trail)`. On success, `observation` is the
        usable reading dict and `stid` is the station id that produced it.
        On exhaustion, both are `None`. `trail` is always the ordered list
        of every candidate probed so far, each entry a dict with `stid`,
        `lat`, `lon`, `distance_km`, and `outcome` -- and nothing else, so
        no key or value here can ever name a token, key, or request
        parameter mapping.
    """
    log_ = logger or log
    candidates = station_explorer.nearest_stations(stations, lat, lon, n=max_candidates)

    trail: list = []
    n = min(len(candidates), max_candidates)
    for batch_start in range(0, n, batch_size):
        if batch_start > 0:
            log_.info(
                f"corridor probe: point=({lat:.4f},{lon:.4f}) "
                f"batch boundary at candidate {batch_start + 1}"
            )

        batch = candidates.iloc[batch_start: batch_start + batch_size]
        for _, row in batch.iterrows():
            stid = row["stid"]
            entry = {
                "stid": stid,
                "lat": row["lat"],
                "lon": row["lon"],
                "distance_km": row["km_to_point"],
            }

            try:
                frame = fetch_weather([stid], start, end)
            except Exception as exc:
                entry["outcome"] = "unusable"
                trail.append(entry)
                log_.info(
                    f"corridor probe candidate stid={stid} lat={row['lat']:.4f} "
                    f"lon={row['lon']:.4f} dist_km={row['km_to_point']:.2f} "
                    f"outcome=unusable ({exc})"
                )
                continue

            observation = _usable_observation(frame, stid)
            if observation is not None:
                entry["outcome"] = "usable"
                trail.append(entry)
                log_.info(
                    f"corridor probe candidate stid={stid} lat={row['lat']:.4f} "
                    f"lon={row['lon']:.4f} dist_km={row['km_to_point']:.2f} "
                    "outcome=usable"
                )
                return observation, stid, trail

            entry["outcome"] = "unusable"
            trail.append(entry)
            log_.info(
                f"corridor probe candidate stid={stid} lat={row['lat']:.4f} "
                f"lon={row['lon']:.4f} dist_km={row['km_to_point']:.2f} "
                "outcome=unusable"
            )

    return None, None, trail


def rate_corridor(
    corridor_name: str,
    start: str,
    end: str,
    stations,
    fetch_weather=None,
    n_points: int = DEFAULT_POINTS_PER_CORRIDOR,
    logger=None,
) -> dict:
    """
    Rate a named corridor end to end: for each of its `n_points` geodesic
    points, independently probe up to `MAX_PROBE_CANDIDATES` nearest
    stations via `resolve_point_observation` (D-08 -- nearest-5-then-10,
    D-05's per-point independence: a station id already probed for an
    earlier point is probed again for this one, never shared or cached),
    run any usable reading through the corridor's `DLRSafetyMonitor` (wired
    to the real thermal model's ampacity function, C7), then reduce the
    per-point ratings to a single corridor-level rating via `min()` --
    mirroring `ercot_dlr_merger.process_dlr_to_hourly`'s `.min()`
    weakest-link reduction, on the space axis instead of the time axis.

    Args:
        corridor_name: A key in `config.CORRIDOR_ENDPOINTS`.
        start, end: The weather-fetch date window (ISO 8601 strings),
            passed straight through to `fetch_weather`.
        stations: A station metadata DataFrame (the shape
            `station_explorer.get_all_stations` / `nearest_stations`
            expect: `stid`, `lat`, `lon`, ...).
        fetch_weather: Injectable weather fetcher, `(stids, start, end) ->
            DataFrame`. Defaults to `weather_provider.fetch_weather` when
            `None` -- never bypasses into the Synoptic-only fetch function
            on `dlr_pipeline` directly (D-07).
        n_points: Points per corridor (default `DEFAULT_POINTS_PER_CORRIDOR`).
        logger: Forwarded to `resolve_point_observation`'s probe logging.

    Returns:
        A dict with keys `corridor`, `bearing_deg`, `points` (one entry per
        point, in point order -- always exactly `n_points` entries, never
        shortened, since an exhausted point still contributes a fallback
        record -- each holding its coordinates, resolved station id (`None`
        when exhausted), candidate probe count/trail, and gated
        rating/status/fallback/alerts), `rating` (the minimum per-point
        rating), `bottleneck_index` (the index of the point that produced
        it; ties broken toward the lowest index), `fallback` (true whenever
        any point fell back -- gate failure or candidate exhaustion alike),
        and `exhausted_points` (how many points exhausted their candidate
        probe, D-09).

    Note:
        A point whose candidate probe exhausts every candidate with no
        usable observation resolves to the corridor's static rating (D-09)
        -- the same terminal target every other data-loss gate in this
        system uses (`DLRSafetyMonitor._fallback`'s G1-G5) -- rather than
        raising, being dropped, or being interpolated from a neighbour
        (T-03-01).
    """
    if fetch_weather is None:
        fetch_weather = weather_provider.fetch_weather

    geometry = corridor_geometry(corridor_name, n_points=n_points)

    monitor = DLRSafetyMonitor(
        static_rating=geometry.static_rating,
        conductor=geometry.conductor,
        rating_bounds=geometry.rating_bounds,
    )

    point_results = []
    for idx, (lat, lon) in enumerate(geometry.points):
        observation, stid, trail = resolve_point_observation(
            lat, lon, start, end, stations, fetch_weather, logger=logger,
        )

        if observation is None:
            # D-09: an exhausted point resolves to the corridor static
            # rating -- never omitted from `points`, never interpolated
            # from a neighbour, and still counted in the min() reduction
            # below, exactly like any other data-loss gate (T-03-01).
            # Message shape mirrors DLRSafetyMonitor._fallback's own
            # "{gate} FAIL ({reason}) -- fallback rating {rating:.0f} A"
            # convention rather than inventing a second alert vocabulary.
            msg = (
                f"EXHAUSTED FAIL (point {idx}: {len(trail)} candidates "
                f"exhausted) — fallback rating {geometry.static_rating:.0f} A"
            )
            point_results.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "stid": None,
                    "candidates_probed": len(trail),
                    "probe_trail": trail,
                    "rating": geometry.static_rating,
                    "status": "fallback",
                    "fallback": True,
                    "alerts": [msg],
                }
            )
            continue

        result = monitor.run_check(observation)
        point_results.append(
            {
                "lat": lat,
                "lon": lon,
                "stid": stid,
                "candidates_probed": len(trail),
                "probe_trail": trail,
                "rating": result["rating"],
                "status": result["status"],
                "fallback": result["fallback"],
                "alerts": result["alerts"],
            }
        )

    # Every point contributes exactly one record above -- either a gated
    # rating or the D-09 static-rating fallback -- so this list can never
    # be shorter than geometry.points and min() below can never see an
    # empty sequence. Asserted explicitly so that invariant is structural,
    # not incidental (DS-NF5 empty-sequence edge).
    assert len(point_results) == len(geometry.points), (
        "rate_corridor: point_results length diverged from geometry.points "
        "-- every point must contribute exactly one record"
    )

    ratings = [p["rating"] for p in point_results]
    min_rating = min(ratings)
    # Tie-break toward the lowest index: index() already returns the first
    # (lowest-index) match, so no extra logic is needed here -- explicit
    # for readability.
    bottleneck_index = ratings.index(min_rating)

    corridor_fallback = any(p["fallback"] for p in point_results)
    exhausted_points = sum(1 for p in point_results if p["stid"] is None)

    return {
        "corridor": corridor_name,
        "bearing_deg": geometry.bearing_deg,
        "points": point_results,
        "rating": min_rating,
        "bottleneck_index": bottleneck_index,
        "fallback": corridor_fallback,
        "exhausted_points": exhausted_points,
    }
