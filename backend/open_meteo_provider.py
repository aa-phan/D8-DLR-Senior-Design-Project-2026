"""
Open-Meteo Historical Backfill Provider Adapter (C4, Phase 7 / WX-04)
======================================================================
Fetches historical hourly weather (temp, wind speed/direction, solar
irradiance, relative humidity) from Open-Meteo's Archive API
(`archive-api.open-meteo.com/v1/archive`) for use as C9/C10 training data,
and normalizes the response into `PIPELINE_SCHEMA`-named columns.

The Archive API variant was chosen (over the Historical Forecast API) for
historical-backfill depth: it reaches back to 1940 (ERA5/ERA5-Land
reanalysis), matching WX-04's stated training-volume purpose, whereas
Historical Forecast only starts around 2021. The base URL is isolated in
the single `OPEN_METEO_ARCHIVE_BASE` module constant, so reversing this
discretion-item choice later is a one-constant change plus a test-fixture
update, per `07-RESEARCH.md` Assumption A1.

The endpoint is public and unauthenticated -- this module needs no token
and no API key. Importing this module has no side effects (no file I/O, no
network calls, no environment variable reads), mirroring
`asos_provider.py`'s own no-side-effects-on-import contract. A network call
only happens when `fetch_open_meteo` is actually called.

Deliberate asymmetry against `asos_provider`: ASOS has a well-formed-empty
carve-out because it is a supplement to a primary (Synoptic) that already
succeeded (D-03), so a real sensor-outage window is a non-event. Open-Meteo
is a standalone backfill source with no such primary to fall back to
(D-04), so every absence -- missing `hourly`, empty `time`, a missing or
short variable array -- is a failure here (D-05). Nothing returned by this
module is ever padded, truncated, zero-filled, forward-filled, or
back-filled to paper over a gap; a variable the provider did not return is
a failed fetch, not a null column.
"""

import logging

import pandas as pd
import requests

import units_def

log = logging.getLogger(__name__)

# OPEN_METEO_ARCHIVE_BASE: a fixed constant -- never built from caller input.
OPEN_METEO_ARCHIVE_BASE: str = "https://archive-api.open-meteo.com/v1/archive"

# HOURLY_TO_PIPELINE: Open-Meteo's hourly variable name -> PIPELINE_SCHEMA
# column name. OPEN_METEO_HOURLY_VARS (the requested `hourly` parameter) is
# derived from this mapping's keys below rather than written out a second
# time, so the request and the response parsing cannot drift apart.
HOURLY_TO_PIPELINE: dict[str, str] = {
    "temperature_2m": "air_temp",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_direction",
    "shortwave_radiation": "solar_radiation",
    "relative_humidity_2m": "relative_humidity",
}

OPEN_METEO_HOURLY_VARS: tuple[str, ...] = tuple(HOURLY_TO_PIPELINE)

# EXPECTED_HOURLY_UNITS: the unit string the response's `hourly_units` echo
# should carry for each provider variable, matching PIPELINE_SCHEMA's units
# for the mapped column. Checked against the response as the cheapest
# possible detector for a request parameter that was dropped, renamed, or
# ignored upstream (RESEARCH.md Pitfall 4).
EXPECTED_HOURLY_UNITS: dict[str, str] = {
    "temperature_2m": "°C",
    "wind_speed_10m": "m/s",
    "wind_direction_10m": "°",
    "shortwave_radiation": "W/m²",
    "relative_humidity_2m": "%",
}


def _to_archive_date(value: str) -> str:
    """
    Coerce an ISO-8601 timestamp or a bare-date string into the Archive
    API's `start_date`/`end_date` calendar-date format ("YYYY-MM-DD"), UTC.

    Raises:
        ValueError: naming the offending value, when it cannot be parsed by
            `pd.Timestamp`.
    """
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"open_meteo_provider: cannot parse date {value!r}: {exc}"
        ) from exc

    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    return ts.strftime("%Y-%m-%d")


def fetch_open_meteo(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """
    Fetch the full temp/wind/solar/RH hourly variable set from Open-Meteo's
    Archive API for one (lat, lon) point over [start, end], in exactly one
    HTTP request (WX-04's single-request requirement -- no per-variable
    fan-out, no per-day chunking, no re-issuing retry).

    Args:
        lat, lon: The target point's coordinates.
        start, end: ISO-8601 or bare-date strings.

    Returns:
        A DataFrame with exactly the columns ["datetime_utc", "air_temp",
        "wind_speed", "wind_direction", "solar_radiation",
        "relative_humidity"], in PIPELINE_SCHEMA units. `datetime_utc` is
        tz-aware UTC (parsed with `utc=True` explicitly -- the provider's
        ISO strings carry no offset suffix even for a UTC request,
        RESEARCH.md Pitfall 3) and monotonically increasing, preserving the
        provider's own `hourly.time` order.

    Raises:
        requests.HTTPError: propagated unchanged from `raise_for_status()`.
        ValueError: if the body is not JSON; if `hourly` is missing or not
            a dict; if `time` is missing, not a list, or empty; if any
            mapped variable's array is missing from `hourly` or its length
            differs from `time`'s; if the response's `hourly_units` echoes
            a unit that does not match `EXPECTED_HOURLY_UNITS`; or if any
            value falls outside `units_def.PIPELINE_SCHEMA`'s declared
            range for its column. Never padded, truncated, zero-filled, or
            null-columned in place of a variable the provider did not
            return -- a failed fetch is not a null column (D-04/D-05).
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": _to_archive_date(start),
        "end_date": _to_archive_date(end),
        "hourly": ",".join(OPEN_METEO_HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }
    r = requests.get(OPEN_METEO_ARCHIVE_BASE, params=params, timeout=60)
    r.raise_for_status()

    try:
        data = r.json()
    except ValueError as exc:
        raise ValueError(
            f"open_meteo_provider: response body could not be parsed as "
            f"JSON: {exc}"
        ) from exc

    hourly = data.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError(
            "open_meteo_provider: response is missing a valid 'hourly' "
            f"object, got {type(hourly).__name__}"
        )

    time = hourly.get("time")
    if not isinstance(time, list) or len(time) == 0:
        raise ValueError(
            "open_meteo_provider: response's 'hourly.time' array is "
            f"missing, not a list, or empty (got {time!r})"
        )
    n = len(time)

    for provider_key in HOURLY_TO_PIPELINE:
        if provider_key not in hourly:
            raise ValueError(
                f"open_meteo_provider: response is missing the "
                f"{provider_key!r} variable array under 'hourly' -- a "
                "missing variable is a failed fetch, never substituted "
                "with a null column."
            )
        values = hourly[provider_key]
        if not isinstance(values, list) or len(values) != n:
            got_len = len(values) if isinstance(values, list) else type(values).__name__
            raise ValueError(
                f"open_meteo_provider: {provider_key!r} array length "
                f"({got_len}) does not match 'hourly.time' length ({n}) -- "
                "never padded or truncated to fit."
            )

    hourly_units = data.get("hourly_units")
    if isinstance(hourly_units, dict):
        for provider_key, expected_unit in EXPECTED_HOURLY_UNITS.items():
            echoed_unit = hourly_units.get(provider_key)
            if echoed_unit is None:
                continue
            if echoed_unit != expected_unit:
                raise ValueError(
                    f"open_meteo_provider: response echoed unit "
                    f"{echoed_unit!r} for {provider_key!r}, expected "
                    f"{expected_unit!r} -- check the request parameter for "
                    "a dropped or ignored unit override."
                )

    frame = pd.DataFrame({"datetime_utc": pd.to_datetime(time, utc=True)})
    for provider_key, pipeline_col in HOURLY_TO_PIPELINE.items():
        frame[pipeline_col] = hourly[provider_key]

    _range_check(frame)

    return frame


def _range_check(frame: pd.DataFrame) -> None:
    """
    Raise `ValueError` naming the column, the offending value, and both
    bounds when any non-null value in `frame` falls outside
    `units_def.PIPELINE_SCHEMA`'s declared range for that column.

    This is the phase's V5 input-validation control: it is the one gate
    that catches a units regression (e.g. a wind-speed unit parameter that
    was dropped or ignored upstream), since a provider value left in its
    native units is otherwise an ordinary-looking, in-range number.
    """
    for column in HOURLY_TO_PIPELINE.values():
        if column not in frame.columns:
            continue
        lo, hi = units_def.PIPELINE_SCHEMA[column]["range"]
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        out_of_range = values[(values < lo) | (values > hi)]
        if not out_of_range.empty:
            bad_value = out_of_range.iloc[0]
            raise ValueError(
                f"open_meteo_provider: value {bad_value!r} for column "
                f"{column!r} is outside PIPELINE_SCHEMA's range "
                f"[{lo}, {hi}] -- check for a native-unit value that was "
                "never converted or a dropped unit request parameter."
            )
