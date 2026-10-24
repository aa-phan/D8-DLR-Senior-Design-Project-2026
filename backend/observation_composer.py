"""
Observation Composer (Track 1)
==================================================
Builds ONE weather reading per candidate station by taking each input from
the best available provider, with all three inputs taken from the SAME UTC
hour:

    air_temp         synoptic (station, ASOS-supplemented) -> tceq -> open_meteo
    wind_speed       tceq -> synoptic (station, ASOS-supplemented) -> open_meteo
    solar_radiation  nsrdb -> open_meteo -> synoptic (station)

Open-Meteo is the historical-archive source: last resort for temperature and
wind (so a past window with no station data still rates), and the fallback for
solar once NSRDB has no data (NSRDB stops at a past month). NSRDB is not called
at all for a window ending in the current UTC year: it publishes a calendar
year only after it ends, so solar for a live run comes from Open-Meteo (see
NSRDB_SKIP_YEARS_BEFORE_CURRENT). Open-Meteo also runs as its
own provider mode for bulk history. For solar, Synoptic's station reading stays
last, so a run newer than Open-Meteo's archive still gets solar.

Wind. Speed is only taken together with a direction (degrees, meteorological,
the direction the wind comes FROM) from the same provider and hour; the
rating path projects it onto the city's line bearing.

Time alignment. Providers report at different cadences (ASOS 1-min, Synoptic
5-min, TCEQ and NSRDB hourly) and TCEQ lags. Every provider's data is bucketed
by UTC hour (last non-blank observation in the hour). The reading is built at
the LATEST hour at or before `end` for which every input is available, so
temperature, wind and solar all describe the same hour. Providers are
preferred in FIELD_PRIORITY order: each field uses its first-choice provider
that has any data in the lookback window (so a down or inapplicable provider
is skipped, but a merely older one is not), and the reading is built at the
latest hour those providers share. Only if they share no hour do fallback
providers fill in hour by hour.

`make_composed_fetcher(stations)` returns a function with the same call shape
as `weather_provider.fetch_weather` for the station path
(`fetcher([stid], start, end, provider=...)`), so it plugs straight into
`city_rating.rate_city(fetch_weather=...)` with no change
there. It returns a one-row frame (stid, datetime_utc = the aligned hour,
air_temp, wind_speed, wind_direction, solar_radiation + per-field *_source
columns) or an
empty frame when no hour has all three inputs, which makes
`resolve_point_observation` move on to the next-nearest station.
"""

import logging
from collections import Counter

import pandas as pd
import requests

import config
import station_explorer
import weather_provider
import open_meteo_provider
import nsrdb_provider
import tceq_provider

log = logging.getLogger(__name__)

# Field -> ordered provider names. Providers: synoptic, tceq, nsrdb, open_meteo.
# Roles per the System Design Report (3.1.6): Synoptic live (ASOS-supplemented
# inside weather_provider), TCEQ as the primary wind source, NSRDB as the
# primary solar source, Open-Meteo's archive next, and the Synoptic station
# reading last. Open-Meteo is the last resort for temp and wind (historical).
FIELD_PRIORITY: dict[str, tuple[str, ...]] = {
    "air_temp": ("synoptic", "tceq", "open_meteo"),
    "wind_speed": ("tceq", "synoptic", "open_meteo"),
    "solar_radiation": ("nsrdb", "open_meteo", "synoptic"),
}

# How far back from `end` every provider is asked for data, so the slow ones
# (TCEQ publishes hourly with its newest hour still blank) have a completed
# hour to align on. The aligned reading can be up to this many hours old.
LOOKBACK_HOURS: float = 3.0

# After this many consecutive failures with no success, a grid provider
# (nsrdb, open_meteo) is skipped for the rest of the run instead of being
# called again for every remaining candidate station.
CIRCUIT_BREAKER_FAILURES: int = 3
_BREAKER_PROVIDERS = ("nsrdb", "open_meteo")

# NSRDB publishes a calendar year only after it ends, so a window ending in the
# current UTC year has no data there: the 2026-10-19 live run got HTTP 400 three
# times per run before the circuit breaker opened. A window whose end year is
# within this many years of the current one is not requested at all, and its
# solar comes from the next provider in FIELD_PRIORITY. 0 skips only the
# current year; raise it to 1 early in a year if the previous year is not yet
# published. The rule is relative to now on purpose: nsrdb_provider documents
# why a fixed ceiling year would be wrong (the product's last year advances).
NSRDB_SKIP_YEARS_BEFORE_CURRENT: int = 0

# For runs whose end is older than this many days, grid/TCEQ requests are
# widened to whole UTC days so hourly runs on the same day share one cached
# request per point instead of making a new one each hour (a long backfill
# would otherwise make thousands). Newer runs keep the exact lookback window.
HISTORICAL_AFTER_DAYS: float = 2.0

# TCEQ CAMS sites are one per city (config.TCEQ_STATIONS); use one only when
# the station is within this many km of that city's centroid.
TCEQ_MAX_KM: float = 50.0

_PROVENANCE_COL = {
    "air_temp": "temp_source",
    "wind_speed": "wind_source",
    "wind_direction": "wind_source",
    "solar_radiation": "solar_source",
}
_OUT_COLUMNS = [
    "stid", "datetime_utc", "air_temp", "wind_speed", "wind_direction", "solar_radiation",
    "temp_source", "wind_source", "solar_source",
]
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _nsrdb_unpublished(end_ts: pd.Timestamp, now_ts: pd.Timestamp) -> bool:
    """True when a window ending at `end_ts` is too recent for NSRDB to have published."""
    return _utc(end_ts).year >= _utc(now_ts).year - NSRDB_SKIP_YEARS_BEFORE_CURRENT


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    """Flatten any (stid|city, datetime_utc) index into columns; UTC datetimes."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    names = [n for n in frame.index.names if n is not None and n not in frame.columns]
    if names:
        frame = frame.reset_index(level=names)
    if "datetime_utc" not in frame.columns:
        return pd.DataFrame()
    frame = frame.copy()
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], utc=True)
    return frame


def _by_hour(frame: pd.DataFrame, column: str, end_ts: pd.Timestamp) -> dict:
    """{UTC hour: (value, source-or-None)}: last non-null `column` in each hour, <= end."""
    if frame.empty or column not in frame.columns:
        return {}
    sub = frame[frame["datetime_utc"] <= end_ts].dropna(subset=[column])
    if sub.empty:
        return {}
    sub = sub.sort_values("datetime_utc")
    prov = _PROVENANCE_COL[column]
    out = {}
    for _, row in sub.iterrows():  # ascending, so a later row in an hour overwrites
        src = row[prov] if prov in sub.columns and pd.notna(row[prov]) else None
        out[row["datetime_utc"].floor("h")] = (float(row[column]), None if src is None else str(src))
    return out


def _nearest_city(lat: float, lon: float, max_km: float):
    best, best_km = None, None
    for city, (clat, clon) in config.CITY_COORDINATES.items():
        km = station_explorer.haversine_km(lat, lon, clat, clon)
        if best_km is None or km < best_km:
            best, best_km = city, km
    return best if best_km is not None and best_km <= max_km else None


def make_composed_fetcher(stations: pd.DataFrame, field_priority=None, tceq_max_km: float = TCEQ_MAX_KM):
    """
    Build the composed fetcher for one run. The returned callable carries two
    attributes the caller can report from: `.provenance` (one dict per
    completed reading: stid, aligned hour, and the source used for each field)
    and `.errors` (a Counter of "<provider>: <ErrorType>" strings).
    """
    priority = field_priority or FIELD_PRIORITY
    fields = list(priority)
    locs = {}
    if stations is not None and len(stations):
        locs = {str(r.stid): (float(r.lat), float(r.lon)) for r in stations.itertuples()}

    grid_cache: dict = {}
    errors: Counter = Counter()
    provenance: list = []

    consecutive_failures: Counter = Counter()
    open_circuits: set = set()

    def _record_error(name: str, exc: Exception) -> None:
        # Type name only, except for messages the grid/TCEQ adapters write
        # themselves (ValueError / a missing credential's EnvironmentError),
        # which are redacted of keys. A requests error string can echo a URL,
        # and Synoptic's carries the token, so those are never printed.
        # requests exceptions subclass OSError, so they are excluded explicitly.
        detail = f"{type(exc).__name__}"
        printable = isinstance(exc, ValueError) or (
            isinstance(exc, OSError) and not isinstance(exc, requests.RequestException)
        )
        if name != "synoptic" and printable:
            detail += f": {str(exc)[:200]}"
        errors[f"{name}: {detail}"] += 1
        log.debug("composer: provider %s failed (%s)", name, type(exc).__name__)

    def _window(start: str, end: str):
        """(start, end) strings for grid/TCEQ requests: whole days if historical."""
        end_ts = _utc(end)
        if end_ts >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=HISTORICAL_AFTER_DAYS):
            return start, end
        day0 = _utc(start).floor("D")
        day1 = end_ts.floor("D") + pd.Timedelta(hours=23, minutes=59, seconds=59)
        return day0.strftime(_TS_FMT), day1.strftime(_TS_FMT)

    def _call(name: str, stid: str, start: str, end: str):
        lat, lon = locs.get(stid, (None, None))
        if name == "synoptic":
            return weather_provider.fetch_weather([stid], start, end, provider="synoptic", fallback=False)
        if lat is None:
            return None  # no coordinates for this station: grid/TCEQ not applicable
        if name == "tceq":
            city = _nearest_city(lat, lon, tceq_max_km)
            cams = config.TCEQ_STATIONS.get(city) if city else None
            if cams is None:
                return None  # not applicable here -- not an error
            w_start, w_end = _window(start, end)
            key = ("tceq", cams, w_start, w_end)
            if key not in grid_cache:
                try:
                    grid_cache[key] = tceq_provider.fetch_tceq(cams, w_start, w_end)
                except Exception as exc:  # remember it: don't re-scrape per station
                    grid_cache[key] = exc
            if isinstance(grid_cache[key], Exception):
                raise grid_cache[key]
            return grid_cache[key]
        if name == "nsrdb" and _nsrdb_unpublished(_utc(end), pd.Timestamp.now(tz="UTC")):
            # None is "not applicable" (as for TCEQ): no request, no error entry,
            # and the circuit breaker is not touched.
            log.debug("composer: nsrdb skipped, window ending %s is not published yet", end)
            return None
        if name in ("nsrdb", "open_meteo"):
            w_start, w_end = _window(start, end)
            key = (name, round(lat, 2), round(lon, 2), w_start, w_end)
            if key not in grid_cache:
                fn = nsrdb_provider.fetch_nsrdb if name == "nsrdb" else open_meteo_provider.fetch_open_meteo
                grid_cache[key] = fn(lat, lon, w_start, w_end)
            return grid_cache[key]
        raise ValueError(f"observation_composer: unknown provider {name!r}")

    def fetcher(location, start, end, provider=None, **_ignored):
        stid = str(location[0])
        end_ts = _utc(end)
        look_start = (end_ts - pd.Timedelta(hours=LOOKBACK_HOURS)).strftime(_TS_FMT)
        end_str = end_ts.strftime(_TS_FMT)

        frames: dict = {}

        def _hours(name: str, f: str) -> dict:
            if name not in frames:
                if name in open_circuits:
                    errors[f"{name}: skipped after {CIRCUIT_BREAKER_FAILURES} consecutive failures"] += 1
                    frames[name] = pd.DataFrame()
                else:
                    try:
                        raw = _call(name, stid, look_start, end_str)
                        frames[name] = _normalize(raw)
                        if raw is not None:
                            consecutive_failures[name] = 0
                    except Exception as exc:  # one provider failing must not stop the rest
                        _record_error(name, exc)
                        frames[name] = pd.DataFrame()
                        if name in _BREAKER_PROVIDERS:
                            consecutive_failures[name] += 1
                            if consecutive_failures[name] >= CIRCUIT_BREAKER_FAILURES:
                                open_circuits.add(name)
            by_hour = _by_hour(frames[name], f, end_ts)
            if f != "wind_speed":
                return {h: (v, src or name, None) for h, (v, src) in by_hour.items()}
            # Wind speed only counts together with a direction from the SAME
            # provider and hour: the line projection needs both, and a speed
            # from one source with a direction from another is not one wind.
            directions = _by_hour(frames[name], "wind_direction", end_ts)
            return {h: (v, src or name, directions[h][0])
                    for h, (v, src) in by_hour.items() if h in directions}

        # Pass 1: each field uses its first-choice provider that has ANY data
        # in the lookback window (a provider that is down, not applicable, or
        # empty is skipped; one that is merely older than another is not).
        avail = {}
        for f in fields:
            avail[f] = {}
            for name in priority[f]:
                hrs = _hours(name, f)
                if hrs:
                    avail[f] = hrs
                    break
        common = set.intersection(*[set(avail[f]) for f in fields])
        chosen_hour = max(common) if common else None

        # Pass 2 (only if the chosen providers share no hour): let fallback
        # providers fill in hour by hour, earlier-ranked providers winning.
        if chosen_hour is None:
            avail = {f: {} for f in fields}
            for rank in range(max(len(v) for v in priority.values())):
                for f in fields:
                    if rank < len(priority[f]):
                        for h, val in _hours(priority[f][rank], f).items():
                            avail[f].setdefault(h, val)
                common = set.intersection(*[set(avail[f]) for f in fields])
                if common:
                    chosen_hour = max(common)
                    break

        if chosen_hour is None:
            return pd.DataFrame(columns=_OUT_COLUMNS)

        row = {"stid": stid, "datetime_utc": chosen_hour}
        rec = {"stid": stid, "hour": chosen_hour.strftime(_TS_FMT)}
        for f in fields:
            value, src, extra = avail[f][chosen_hour]
            if f == "wind_speed":
                row["wind_direction"] = extra
            row[f] = value
            row[_PROVENANCE_COL[f]] = src
            rec[f] = src
        provenance.append(rec)
        return pd.DataFrame([row], columns=_OUT_COLUMNS)

    fetcher.provenance = provenance
    fetcher.errors = errors
    return fetcher


def summarize_sources(provenance: list) -> dict:
    """{field: {source: count}} over the completed readings of a run."""
    out: dict = {}
    for rec in provenance:
        for field, source in rec.items():
            if field in ("stid", "hour"):
                continue
            out.setdefault(field, Counter())[source] += 1
    return {f: dict(c) for f, c in out.items()}
