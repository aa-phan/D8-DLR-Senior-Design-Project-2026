"""
NSRDB PSM v4 GOES CONUS Solar Irradiance Provider Adapter (C4, Phase 8 / WX-03)
================================================================================
Fetches GHI (global horizontal irradiance) from NREL/NLR's National Solar
Radiation Database (NSRDB), PSM v4, GOES CONUS product, and normalizes it
into a single `PIPELINE_SCHEMA`-named `solar_radiation` column.

Importing this module performs no network call and reads no environment
variable -- the credential lookup happens inside `fetch_nsrdb`, exactly
like `weather_provider.py`'s own no-side-effects-on-import contract, so
this module stays importable on a machine with no key.

Two environment values are required at fetch time, not at import time:
`NREL_API_KEY` (a free developer key) and `NREL_API_EMAIL` (a syntactically
valid contact address NSRDB requires on every request, live-confirmed).
Both are read by dedicated env-var-or-raise helpers, modelled on
`dlr_pipeline._token()`, before any request is built -- a missing value
raises `EnvironmentError` naming the variable, never a remote 403 whose
body points at a dead signup URL, and never a silent downgrade to an
anonymous or demo-key request.

Only GHI is requested (`NSRDB_ATTRIBUTES` is a single attribute, D-02):
NREL's own documentation states the response's 2m MERRA-2 reanalysis wind
must not be used for wind power calculations, so this module never
requests, maps, or populates wind, temperature, or humidity fields from an
NSRDB response -- the returned frame carries `solar_radiation` and nothing
else.

The developer host below is `developer.nlr.gov`: the organization renamed
itself the National Laboratory of the Rockies, and the previous
`developer.nrel.gov` hostname no longer resolves. WX-03 and the env-var
names deliberately keep saying "NREL" to match the requirement's own
wording.
"""

import csv
import logging
import os
from io import StringIO

import pandas as pd
import requests

import units_def

log = logging.getLogger(__name__)

# NSRDB_BASE: a fixed constant -- never built from caller input.
NSRDB_BASE: str = (
    "https://developer.nlr.gov/api/nsrdb/v2/solar/"
    "nsrdb-GOES-conus-v4-0-0-download.csv"
)

# NSRDB_ATTRIBUTES: exactly one attribute. A live probe confirmed GHI alone
# is a legal request with no forced companion fields, so there is no
# technical reason to pull the variables D-02 excludes.
NSRDB_ATTRIBUTES: str = "ghi"

# NSRDB_INTERVAL_MINUTES: D-04.
NSRDB_INTERVAL_MINUTES: int = 60

# NSRDB_REQUEST_METADATA: the four optional, non-secret request-metadata
# parameters, sent rather than omitted -- a real key was never available to
# confirm they are optional under one, and sending fixed project values
# costs one dict literal.
NSRDB_REQUEST_METADATA: dict[str, str] = {
    "full_name": "DLR System",
    "affiliation": "ECE 464",
    "reason": "research",
    "mailing_list": "false",
}

# _REQUIRED_DATA_COLUMNS: the PSM v4 data column header this module requires
# to trust a response body enough to hand it to pd.read_csv.
_REQUIRED_DATA_COLUMNS: tuple[str, ...] = ("Year", "Month", "Day", "Hour", "Minute", "GHI")


def _nrel_api_key() -> str:
    """
    Env-var-or-raise credential lookup for `NREL_API_KEY`, modelled on
    `dlr_pipeline._token()`: names the variable, never echoes the value.

    Raises:
        EnvironmentError: if `NREL_API_KEY` is unset or empty.
    """
    key = os.getenv("NREL_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "Set NREL_API_KEY env var. Register a free developer key at "
            "the National Laboratory of the Rockies developer portal "
            "(developer.nlr.gov)."
        )
    return key


def _nrel_contact_email() -> str:
    """
    Env-var-or-raise lookup for `NREL_API_EMAIL`. NSRDB requires a
    syntactically valid contact address on every request; it is kept in
    the environment rather than in source so a course submission carries
    no personal address. The address's syntax is not validated locally --
    the endpoint is the authority on that, and a local regular expression
    would reject valid addresses the endpoint accepts.

    Raises:
        EnvironmentError: if `NREL_API_EMAIL` is unset or empty.
    """
    email = os.getenv("NREL_API_EMAIL", "")
    if not email:
        raise EnvironmentError(
            "Set NREL_API_EMAIL env var. NSRDB requires a syntactically "
            "valid contact email on every request; register one alongside "
            "your NREL_API_KEY at the developer portal (developer.nlr.gov)."
        )
    return email


def _wkt_point(lat: float, lon: float) -> str:
    """
    Build the `wkt` request parameter for one point.

    This function's own parameter order is latitude-first, matching
    `config.CITY_COORDINATES` and `_fetch_grid`. The string it returns is
    longitude-first, because that is what the WKT specification and this
    endpoint require. Getting it backwards yields syntactically valid WKT
    for a different point on Earth: nothing downstream raises, the range
    check passes, and the row is still tagged with the caller's city. This
    swap is kept in exactly one named function so there is exactly one
    place in the codebase where the order is decided and exactly one place
    a test has to pin.
    """
    return f"POINT({lon:.4f} {lat:.4f})"


def _parse_psm4_csv(text: str) -> tuple[pd.DataFrame, dict[str, str]]:
    """
    Parse a PSM v4 CSV response body: two metadata header lines, then a
    data column header row, then hourly data rows.

    Returns:
        A tuple of (data frame from row 3 onward, metadata dict built from
        the first two lines). The metadata dict is built with the `csv`
        module rather than a bare `str.split(",")`, because a metadata
        value such as a location name can itself contain a quoted comma.

    Raises:
        ValueError: if the body has fewer than three lines, or if the data
            column header does not carry every column in
            `_REQUIRED_DATA_COLUMNS` -- an HTML error page or a redirected
            response would otherwise reach `pd.read_csv` and look
            parseable.
    """
    lines = text.splitlines()
    if len(lines) < 3:
        raise ValueError(
            "nsrdb_provider: expected a PSM v4 CSV response with two "
            "metadata header lines and a data column header, but got only "
            f"{len(lines)} line(s). Body (truncated): {text[:200]!r}"
        )

    metadata_reader = csv.reader(StringIO("\n".join(lines[:2])))
    field_names = next(metadata_reader)
    field_values = next(metadata_reader)
    metadata = dict(zip(field_names, field_values))

    data_header = [c.strip() for c in lines[2].split(",")]
    missing = [c for c in _REQUIRED_DATA_COLUMNS if c not in data_header]
    if missing:
        raise ValueError(
            "nsrdb_provider: expected a PSM v4 data column header "
            f"containing {list(_REQUIRED_DATA_COLUMNS)}, but got "
            f"{data_header!r} -- missing {missing}. Body (truncated): "
            f"{text[:200]!r}"
        )

    frame = pd.read_csv(StringIO(text), skiprows=2)
    return frame, metadata


def _range_check(frame: pd.DataFrame) -> None:
    """
    Raise `ValueError` naming the column, the offending value, and both
    bounds when any non-null `solar_radiation` value in `frame` falls
    outside `units_def.PIPELINE_SCHEMA`'s declared range.

    This mirrors `open_meteo_provider._range_check` exactly, over the
    single column this module ever populates.
    """
    lo, hi = units_def.PIPELINE_SCHEMA["solar_radiation"]["range"]
    values = pd.to_numeric(frame["solar_radiation"], errors="coerce").dropna()
    out_of_range = values[(values < lo) | (values > hi)]
    if not out_of_range.empty:
        bad_value = out_of_range.iloc[0]
        raise ValueError(
            f"nsrdb_provider: value {bad_value!r} for column "
            f"'solar_radiation' is outside PIPELINE_SCHEMA's range "
            f"[{lo}, {hi}] -- check for a native-unit value that was never "
            "converted or a dropped unit request parameter."
        )


def _to_utc_timestamp(value: str) -> pd.Timestamp:
    """
    Coerce an ISO-8601 timestamp or a bare-date string into a tz-aware UTC
    `pd.Timestamp`, matching `open_meteo_provider._to_archive_date`'s
    coercion.

    Raises:
        ValueError: naming the offending value, when it cannot be parsed by
            `pd.Timestamp`.
    """
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"nsrdb_provider: cannot parse date {value!r}: {exc}") from exc

    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    return ts


def fetch_nsrdb(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """
    Fetch GHI from NSRDB PSM v4 (GOES CONUS) for one (lat, lon) point over
    a window lying wholly inside one calendar year, in exactly one HTTP
    request.

    Args:
        lat, lon: The target point's coordinates, latitude-first (matching
            `config.CITY_COORDINATES`).
        start, end: ISO-8601 or bare-date strings, both inside the same
            calendar year.

    Returns:
        A DataFrame with exactly the columns ["datetime_utc",
        "solar_radiation"], in PIPELINE_SCHEMA units (W/m²). `datetime_utc`
        is tz-aware UTC and monotonically increasing. No wind, temperature,
        or humidity column is ever present (D-02).

    Raises:
        EnvironmentError: if `NREL_API_KEY` or `NREL_API_EMAIL` is unset --
            this machine is misconfigured. Raised before any network call,
            both credential lookups being the first two statements below.
        ValueError: if a date argument cannot be parsed; if the response
            body is not a well-formed PSM v4 CSV; or if a GHI value falls
            outside `units_def.PIPELINE_SCHEMA`'s declared range for
            `solar_radiation`. Deliberately a different exception type from
            `EnvironmentError`: a misconfigured machine and a malformed
            provider response are different failure modes, and Phase 10's
            fallback logic is meant to treat them differently.
    """
    api_key = _nrel_api_key()
    email = _nrel_contact_email()

    start_ts = _to_utc_timestamp(start)
    end_ts = _to_utc_timestamp(end)
    # This task handles a window wholly inside one calendar year. Plan
    # 08-02 generalises this into a loop over every year spanned by
    # [start, end].
    year = start_ts.year

    params = {
        "api_key": api_key,
        "email": email,
        "names": year,
        "attributes": NSRDB_ATTRIBUTES,
        "interval": NSRDB_INTERVAL_MINUTES,
        "utc": "true",
        "wkt": _wkt_point(lat, lon),
        **NSRDB_REQUEST_METADATA,
    }

    # No .raise_for_status() call here: requests' HTTPError message embeds
    # the request URL, which carries api_key and email in its query string
    # -- letting that exception propagate would leak both. The response
    # body is handed straight to _parse_psm4_csv, which fails loud on
    # anything that isn't a well-formed PSM v4 CSV.
    r = requests.get(NSRDB_BASE, params=params, timeout=60)

    frame, _metadata = _parse_psm4_csv(r.text)

    frame["datetime_utc"] = pd.to_datetime(
        frame[["Year", "Month", "Day", "Hour", "Minute"]], utc=True
    )
    frame["solar_radiation"] = pd.to_numeric(frame["GHI"], errors="coerce")

    result = frame[["datetime_utc", "solar_radiation"]]
    result = result[
        (result["datetime_utc"] >= start_ts) & (result["datetime_utc"] <= end_ts)
    ]
    result = result.sort_values("datetime_utc").reset_index(drop=True)

    _range_check(result)

    return result
