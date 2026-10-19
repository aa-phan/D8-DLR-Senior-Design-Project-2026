"""
City Point Rating (C8)
==================================================
Per-city replacement for the retired `corridor_discretization.rate_corridor`
(see `docs/data-science/decisions/point_scope.md`). Each project city is one
independent rating point: `rate_city` resolves the nearest usable weather
observation to `config.CITY_COORDINATES[city]`, runs it through the same
fail-safe `DLRSafetyMonitor` (C7) with that city's own static rating,
plausibility bounds and conductor (`city_point.city_point`), optionally
archives one row, and returns a per-city dict. There is no discretization, no
`min()` reduction across points and no bottleneck.

Every ampacity value comes from `DLRSafetyMonitor.run_check`; this module
does not compute ampacity itself.

Importing this module has no side effects (no file I/O, no network calls)
and needs no `SYNOPTIC_TOKEN` -- all weather access happens lazily inside
`rate_city`, through `weather_provider.fetch_weather` (D-07), never through
the Synoptic-only fetch function on `dlr_pipeline` directly.
"""

import logging
import math
import time

import city_point as city_point_module
import config
import historical_archive
import station_explorer
import thermal_model
import weather_provider
from DLRSafetyMonitor import DLRSafetyMonitor

# Module logger, matching `dlr_pipeline.py`'s convention
# (`log = logging.getLogger(__name__)`); `resolve_point_observation`'s probe
# logging defaults to this when no `logger` is injected.
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Candidate-probe tuning (D-08)
# ──────────────────────────────────────────────────────────────────────────────
# A live access check found Synoptic returns a usable (non-null) observation
# for only 25-75% of candidate stations depending on the city. A
# single-nearest-station lookup would leave some cities dark most of the
# time, so a city probes its nearest 5 candidates first and, only if all 5
# are unusable, expands to the next 5 nearest (10 total) before giving up
# (D-08/D-09).
PROBE_BATCH_SIZE = 5
MAX_PROBE_CANDIDATES = 10

# Small pause between probe batches so a worst-case run doesn't burst
# unspaced requests at the provider. Worst case per city is
# MAX_PROBE_CANDIDATES (10) station-level fetch attempts, so a full run over
# `config.LOCATIONS` (4 cities) is at most 40 attempts.
PROBE_BATCH_PAUSE_S = 0.2

# Maps the weather-pipeline schema's column names to DLRSafetyMonitor's
# reading keys.
_OBSERVATION_FIELD_MAP = {
    "air_temp": "temp",
    "wind_speed": "wind",
    "solar_radiation": "solar",
}


def _reading_from_row(row) -> dict | None:
    """
    Build the `DLRSafetyMonitor.run_check` reading dict from one frame row,
    or `None` if any of `air_temp`/`wind_speed`/`solar_radiation` is absent
    or null (a partially-null reading is not usable -- forcing it through
    the monitor as `None` would trip G1 anyway). `sensor_status` and
    `link_status` are set to `"ok"` (G1/G2 pass).
    """
    reading: dict = {"sensor_status": "ok", "link_status": "ok"}
    for source_col, target_key in _OBSERVATION_FIELD_MAP.items():
        if source_col not in row.index:
            return None
        value = row[source_col]
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        reading[target_key] = value

    # Wind direction (meteorological, degrees the wind comes FROM) is needed
    # to project the measured wind onto the line; a reading without one is
    # unusable rather than rated on the unprojected speed.
    direction = row["wind_direction"] if "wind_direction" in row.index else None
    if direction is None or (isinstance(direction, float) and math.isnan(direction)):
        return None
    reading["wind_direction"] = float(direction)
    return reading


def _project_wind(observation: dict, bearing_deg: float) -> dict:
    """
    Copy of `observation` whose `wind` is the component of the measured wind
    perpendicular to the line (`thermal_model.perpendicular_wind` with the
    city's own bearing) -- what `ieee738_ampacity` expects as `wind_perp_ms`.
    The measured speed is kept as `wind_raw`. Because `wind` is replaced, the
    archived `wind_speed` and the detector's `raw_data["wind"]` are the
    projected value, as `historical_archive` documents.
    """
    projected = dict(observation)
    projected["wind_raw"] = observation["wind"]
    projected["wind"] = float(
        thermal_model.perpendicular_wind(
            observation["wind"], observation["wind_direction"], bearing_deg
        )
    )
    return projected


class _RawWindDetector:
    """
    Thin wrapper that hands the G6 detector the MEASURED wind speed
    (`wind_raw`) instead of the line-perpendicular `wind` the monitor uses
    for the physics. The learned weather envelope (`anomaly_training`,
    `config.ANOMALY_ML_FEATURE_COLUMNS`) is fitted on raw wind speed, and a
    weather envelope should not depend on a line's bearing; feeding it the
    projected value would judge live readings against a different
    distribution than it was trained on. Every other attribute (`signal`,
    `model_source`, ...) is delegated to the wrapped detector.
    """

    def __init__(self, detector):
        self._detector = detector

    def check(self, raw_data: dict, rating: float):
        data = dict(raw_data)
        if "wind_raw" in data:
            data["wind"] = data["wind_raw"]
        return self._detector.check(data, rating)

    def __getattr__(self, name):
        return getattr(self._detector, name)


def _usable_observation(frame, stid: str) -> dict | None:
    """
    Extract the reading dict `DLRSafetyMonitor.run_check` needs for one
    station from a weather-pipeline DataFrame (the shape
    `weather_provider.fetch_weather` returns).

    Returns `None` when the frame is empty, the station is absent, or any
    required variable (including `wind_direction`) is null for that
    station's row(s).
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

    return _reading_from_row(rows.iloc[0])


def _usable_observation_grid(frame) -> dict | None:
    """
    Grid-path counterpart to `_usable_observation`. open_meteo/nsrdb frames
    are keyed by coordinate, not stid, so this just takes the first row
    rather than filtering by station id.
    """
    if frame is None or frame.empty:
        return None

    return _reading_from_row(frame.iloc[0])


def discover_city_stations(token: str, state: str = "TX"):
    """
    Broadened, unrestricted-network station discovery (D-06): delegates to
    `station_explorer.get_all_stations` with no network restriction, so this
    module has exactly one call site for the "don't restrict to WTM"
    decision. `state` is accepted for interface symmetry;
    `station_explorer.get_all_stations` itself always queries `state=TX`.
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
    sleep=time.sleep,
    provider="synoptic",
):
    """
    D-08's bounded candidate probe for one point: rank up to
    `max_candidates` nearest stations to (lat, lon) once (so a later batch
    is genuinely the next-nearest stations, never a re-probe of an earlier
    batch), then probe them in order, `batch_size` at a time, stopping at
    the first usable reading. Never probes a (`max_candidates` + 1)-th
    candidate.

    Between batch 1 exhausting and batch 2 beginning, sleeps
    `PROBE_BATCH_PAUSE_S` -- never between candidates within a batch, and
    never after the final batch. `sleep` is injectable (defaults to
    `time.sleep`) so tests can record pause calls without waiting.

    Each candidate's `fetch_weather` result is converted through
    `_usable_observation`. A `fetch_weather` call that itself raises is
    treated as unusable (the probe moves on); only the exception's message
    text is logged, never its repr (T-03-02 -- a repr could echo
    request/params state).

    Args:
        lat, lon: The point's coordinates.
        start, end: The weather-fetch date window, passed through unchanged.
        stations: A station metadata DataFrame (`station_explorer`'s shape).
        fetch_weather: `(stids, start, end, provider=...) -> DataFrame`,
            called once per candidate with a single-element `stids` list.
        batch_size: Candidates probed per batch before pausing/expanding.
        max_candidates: Hard ceiling on candidates probed for this point.
        logger: Injectable `logging.Logger`-like object (`.info(...)`),
            defaulting to this module's logger. Log lines carry only a
            station id, lat, lon, distance and a usable/unusable word.

    Returns:
        `(observation, stid, trail)`. On success `observation` is the usable
        reading dict and `stid` the station id that produced it; on
        exhaustion both are `None`. `trail` is the ordered list of every
        candidate probed, each a dict with exactly `stid`, `lat`, `lon`,
        `distance_km` and `outcome`.
    """
    log_ = logger or log
    candidates = station_explorer.nearest_stations(stations, lat, lon, n=max_candidates)

    trail: list = []
    n = min(len(candidates), max_candidates)
    for batch_start in range(0, n, batch_size):
        if batch_start > 0:
            sleep(PROBE_BATCH_PAUSE_S)
            log_.info(
                f"city probe: point=({lat:.4f},{lon:.4f}) "
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
            where = (
                f"city probe candidate stid={stid} lat={row['lat']:.4f} "
                f"lon={row['lon']:.4f} dist_km={row['km_to_point']:.2f}"
            )

            try:
                frame = fetch_weather([stid], start, end, provider=provider)
            except Exception as exc:
                entry["outcome"] = "unusable"
                trail.append(entry)
                log_.info(f"{where} outcome=unusable ({exc})")
                continue

            observation = _usable_observation(frame, stid)
            if observation is not None:
                entry["outcome"] = "usable"
                trail.append(entry)
                log_.info(f"{where} outcome=usable")
                return observation, stid, trail

            entry["outcome"] = "unusable"
            trail.append(entry)
            log_.info(f"{where} outcome=unusable")

    return None, None, trail


def _archive_city_result(city, point, result, datetime_utc, archive_path) -> bool:
    """
    Build and append one archive row for this `rate_city` call (one row per
    city per run). The archived weather is the point's own observation, so
    the archived weather is always the weather that produced the archived
    rating (T-04-13).

    If the city exhausted its candidate probe and has no observation,
    returns `False` without writing: a row of nulls would poison the
    baseline the detector later builds from this file.

    Must not raise: `historical_archive.append_observation` is already
    exception-wrapped (T-04-03) and the row assembly here is wrapped the
    same way, so an archive failure can never alter the computed rating.
    """
    try:
        observation = result.get("observation")
        if observation is None:
            return False

        row = historical_archive.build_archive_row(
            city=city,
            datetime_utc=datetime_utc,
            observation=observation,
            check_result={
                "status": result["status"],
                "rating": result["rating"],
                "fallback": result["fallback"],
            },
            static_rating=point.static_rating,
        )
        return historical_archive.append_observation(row, path=archive_path)
    except Exception as exc:
        # str(exc) only, never repr (T-03-02 precedent).
        log.warning("city archive row assembly failed (non-fatal): %s", str(exc))
        return False


def rate_city(
    city: str,
    start: str,
    end: str,
    stations,
    fetch_weather=None,
    logger=None,
    sleep=time.sleep,
    anomaly_detector=None,
    archive=True,
    archive_path=None,
    provider: str = "synoptic",
) -> dict:
    """
    Rate one city end to end: probe up to `MAX_PROBE_CANDIDATES` nearest
    stations to `config.CITY_COORDINATES[city]` via
    `resolve_point_observation` (nearest-5-then-10), run the first usable
    reading through a `DLRSafetyMonitor` configured from
    `city_point.city_point(city)`, and optionally archive one row.

    Args:
        city: A key in `config.LOCATIONS`; unknown keys raise `KeyError`
            (from `city_point.city_point`).
        start, end: The weather-fetch date window (ISO 8601 strings).
        stations: A station metadata DataFrame (`stid`, `lat`, `lon`, ...).
            Unused by the `open_meteo`/`nsrdb` coordinate path.
        fetch_weather: Injectable `(stids_or_coord, start, end, provider=...)
            -> DataFrame`. Defaults to `weather_provider.fetch_weather`.
        logger, sleep: Forwarded to `resolve_point_observation`.
        anomaly_detector: Forwarded to `DLRSafetyMonitor` as its G6 signal;
            `None` means G1-G5 only.
        archive: When true (default) write one archive row via
            `_archive_city_result`; when false no file is touched.
        archive_path: Forwarded to `historical_archive.append_observation`.
        provider: `"synoptic"` (station probe), or `"open_meteo"`/`"nsrdb"`
            (one coordinate fetch at the city's lat/lon).

    Returns:
        dict with keys `city`, `point` (`(lat, lon)`), `station_id` (`None`
        when exhausted), `candidates_probed`, `probe_trail`, `rating`,
        `status`, `fallback`, `alerts`, `observation` (reading dict, or
        `None` when exhausted), `exhausted` (bool) and `archived` (whether a
        row was written; a failed or skipped write never changes any other
        key).

    Note:
        A city whose probe exhausts every candidate resolves to its static
        rating (D-09) with `status="fallback"` and `fallback=True` -- the
        same terminal target every other data-loss gate uses -- rather than
        raising.
    """
    if fetch_weather is None:
        fetch_weather = weather_provider.fetch_weather

    point = city_point_module.city_point(city)
    lat, lon = point.coord

    if provider in ("open_meteo", "nsrdb"):
        try:
            frame = fetch_weather([lat, lon], start, end, provider=provider)
            observation = _usable_observation_grid(frame)
        except Exception:
            observation = None
        stid, trail = None, []
    else:
        observation, stid, trail = resolve_point_observation(
            lat, lon, start, end, stations, fetch_weather,
            logger=logger, sleep=sleep, provider=provider,
        )

    if observation is None:
        # D-09: exhausted -> the city's static rating. Message shape mirrors
        # DLRSafetyMonitor._fallback's "{gate} FAIL ({reason}) -- fallback
        # rating {rating:.0f} A" convention.
        result = {
            "rating": point.static_rating,
            "status": "fallback",
            "fallback": True,
            "alerts": [
                f"EXHAUSTED FAIL ({city}: {len(trail)} candidates exhausted) "
                f"— fallback rating {point.static_rating:.0f} A"
            ],
            "observation": None,
        }
    else:
        observation = _project_wind(observation, point.bearing_deg)
        monitor = DLRSafetyMonitor(
            static_rating=point.static_rating,
            conductor=point.conductor,
            rating_bounds=point.rating_bounds,
            anomaly_detector=None if anomaly_detector is None else _RawWindDetector(anomaly_detector),
            # G5 (step-change vs the previous rating) is intentionally off:
            # this monitor is built fresh for every call, so it has no
            # previous rating to compare against.
            delta_fraction=float("inf"),
        )
        check = monitor.run_check(observation)
        result = {
            "rating": check["rating"],
            "status": check["status"],
            "fallback": check["fallback"],
            "alerts": check["alerts"],
            "observation": observation,
        }

    archived = False
    if archive:
        # `datetime_utc` comes from `end` -- the window's own deterministic
        # boundary -- never a clock (DS-NF2: two runs over the same window
        # must produce identical archive rows).
        archived = _archive_city_result(
            city, point, result, datetime_utc=end, archive_path=archive_path,
        )

    return {
        "city": city,
        "point": (lat, lon),
        "station_id": stid,
        "candidates_probed": len(trail),
        "probe_trail": trail,
        "rating": result["rating"],
        "status": result["status"],
        "fallback": result["fallback"],
        "alerts": result["alerts"],
        "observation": result["observation"],
        "exhausted": observation is None,
        "archived": archived,
    }