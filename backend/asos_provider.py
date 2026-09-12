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

import units_def
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
        is tz-aware UTC. Empty (but column-complete) when the response is
        well-formed but carries zero data rows -- a real ASOS sensor-outage
        window (RESEARCH.md Pitfall 2, live-confirmed for station ELP), not
        a failure. Rows in which `air_temp`, `wind_speed`, and
        `wind_direction` are all null after conversion are dropped (they
        contribute no data and would otherwise add an all-null union row to
        the merged series).

    Raises:
        requests.HTTPError: propagated unchanged from `raise_for_status()`.
        ValueError: if a timestamp argument cannot be parsed; if the
            response body names `station` as unknown; if the response's
            first line does not carry the expected ASOS header; or if a
            converted value falls outside `units_def.PIPELINE_SCHEMA`'s
            declared range for its column (a units regression -- see
            `_range_check`).
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

    # The endpoint answers HTTP 200 for an unknown-station request (RESEARCH
    # Pitfall 1) -- status alone is not a trust signal, so this string check
    # is what actually catches it. Copied verbatim from the live-confirmed
    # error text, never paraphrased.
    if "Unknown station provided" in text:
        raise ValueError(
            f"asos_provider: unknown station {station!r} -- check the "
            f"3-letter FAA code (see config.ASOS_STATIONS). ASOS response: "
            f"{text.strip()!r}"
        )

    first_line = text.splitlines()[0] if text else ""
    if "valid(UTC)" not in first_line:
        raise ValueError(
            f"asos_provider: unrecognised response header for station "
            f"{station!r} -- expected a 'valid(UTC)' column, got first "
            f"line {first_line!r}. An HTML error page or a redirected "
            "response would otherwise be fed to pd.read_csv and look "
            "parseable."
        )

    df = pd.read_csv(StringIO(text))

    if df.empty:
        log.info(
            "ASOS 1-minute: no data rows for station=%s window=%s..%s "
            "(well-formed empty response -- likely a real sensor outage, "
            "not a failure)",
            station, start, end,
        )
        return pd.DataFrame(columns=_RETURN_COLUMNS)

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

    result = df[_RETURN_COLUMNS]

    all_null = result[["air_temp", "wind_speed", "wind_direction"]].isna().all(axis=1)
    dropped = int(all_null.sum())
    if dropped:
        log.debug(
            "asos_provider: dropping %d all-null row(s) for station=%s",
            dropped, station,
        )
        result = result[~all_null].reset_index(drop=True)

    _range_check(result)

    return result


def _range_check(frame: pd.DataFrame) -> None:
    """
    Raise `ValueError` naming the column, the offending value, and both
    bounds when any non-null value in `frame` falls outside
    `units_def.PIPELINE_SCHEMA`'s declared range for that column.

    This is the phase's V5 input-validation control: it is the one gate
    that catches a units regression, since a provider value left in its
    native units (e.g. an unconverted Fahrenheit temperature) is otherwise
    an ordinary-looking, in-range number.

    NOTE: if live operation ever shows this gate is too brittle for
    genuine sensor noise, the follow-up is to null the offending cell and
    log it -- never to pass the value through.
    """
    for column in ("air_temp", "wind_speed", "wind_direction"):
        if column not in frame.columns:
            continue
        lo, hi = units_def.PIPELINE_SCHEMA[column]["range"]
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        out_of_range = values[(values < lo) | (values > hi)]
        if not out_of_range.empty:
            bad_value = out_of_range.iloc[0]
            raise ValueError(
                f"asos_provider: converted value {bad_value!r} for column "
                f"{column!r} is outside PIPELINE_SCHEMA's range "
                f"[{lo}, {hi}] -- check for a native-unit value that was "
                "never converted."
            )
