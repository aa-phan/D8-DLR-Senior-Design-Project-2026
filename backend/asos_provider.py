"""
ASOS 1-minute Provider Adapter (C4, Phase 7 / WX-02)
=====================================================
Fetches high-temporal-density (1-minute) wind/temperature observations from
the Iowa Environmental Mesonet's ASOS 1-minute CGI endpoint
(`mesonet.agron.iastate.edu`) and normalizes them into `PIPELINE_SCHEMA`-
named columns, converting units via `units_def.Q` (never hand-rolled).

The endpoint is public and unauthenticated -- this module needs no token.
Importing this module has no side effects (no file I/O, no network calls,
no environment variable reads), mirroring `weather_provider.py`'s own
no-side-effects-on-import contract. A network call only happens when
`fetch_asos_1min` is actually called.
"""

import logging
from io import StringIO

import pandas as pd
import requests

from units_def import Q

log = logging.getLogger(__name__)

# ASOS_BASE / ASOS_VARS: fixed constants -- never built from caller input.
ASOS_BASE: str = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos1min.py"
ASOS_VARS: tuple[str, ...] = ("tmpf", "sknt", "drct")

_RETURN_COLUMNS = ["datetime_utc", "air_temp", "wind_speed", "wind_direction"]


def _to_asos_timestamp(value: str) -> str:
    """
    Coerce an ISO-8601 or bare-date string (both shapes
    `corridor_discretization.rate_corridor` passes today) into the ASOS
    CGI's `sts`/`ets` timestamp format ("YYYY-MM-DDTHH:MMZ"), UTC.

    Raises:
        ValueError: naming the offending value, when it cannot be parsed by
            `pd.Timestamp`.
    """
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"asos_provider: cannot parse timestamp {value!r}: {exc}") from exc

    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    return ts.strftime("%Y-%m-%dT%H:%MZ")


def fetch_asos_1min(station: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch ASOS 1-minute wind/temperature observations for one station over
    [start, end).

    Args:
        station: The IEM ASOS network's 3-letter station identifier (e.g.
            "AUS" -- NOT the 4-letter ICAO code `config.ASOS_STATIONS`
            deliberately avoids).
        start, end: ISO-8601 or bare-date strings.

    Returns:
        A DataFrame with exactly the columns
        ["datetime_utc", "air_temp", "wind_speed", "wind_direction"], in
        PIPELINE_SCHEMA units (degC, m/s, deg respectively). `datetime_utc`
        is tz-aware UTC.

    Raises:
        requests.HTTPError: propagated unchanged from `raise_for_status()`.
        ValueError: if a timestamp argument cannot be parsed.
    """
    params = {
        "station": station,
        "vars": ASOS_VARS,
        "sts": _to_asos_timestamp(start),
        "ets": _to_asos_timestamp(end),
        "sample": "1min",
        "tz": "UTC",
        "what": "download",
    }
    r = requests.get(ASOS_BASE, params=params, timeout=120)
    r.raise_for_status()

    text = r.text
    df = pd.read_csv(StringIO(text))

    df["datetime_utc"] = pd.to_datetime(df["valid(UTC)"], utc=True)

    tmpf = pd.to_numeric(df["tmpf"], errors="coerce")
    sknt = pd.to_numeric(df["sknt"], errors="coerce")
    drct = pd.to_numeric(df["drct"], errors="coerce")

    df["air_temp"] = tmpf.apply(
        lambda v: Q(v, "degF").to("degC").value if pd.notna(v) else None
    )
    df["wind_speed"] = sknt.apply(
        lambda v: Q(v, "knots").to("m/s").value if pd.notna(v) else None
    )
    df["wind_direction"] = drct

    return df[_RETURN_COLUMNS]
