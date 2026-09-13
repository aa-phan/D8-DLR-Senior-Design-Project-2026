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

# NSRDB_FIRST_COVERED_YEAR: PSM v4 GOES CONUS coverage begins in 2018 -- a
# fixed product fact that cannot move backwards. Deliberately no matching
# upper-bound constant: the product's most recent covered year advances
# every time NREL/NLR publishes a new year, and a local ceiling would
# reject a year that now legitimately exists. The upper bound is left to
# the endpoint's own structured rejection (Task 2's error handler).
NSRDB_FIRST_COVERED_YEAR: int = 2018


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


def _window_bounds(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    Resolve a caller's [start, end] window to tz-aware UTC timestamps,
    coercing each argument exactly as `open_meteo_provider._to_archive_date`
    does (tz-naive localized to UTC, tz-aware converted to UTC).

    A bare-date `end` (containing neither "T" nor ":") names a calendar
    day rather than an instant, so it is advanced to the last microsecond
    of that day: Phase 7 confirmed live that Open-Meteo returns a full
    day's rows for a single-day window, and a caller writing the same
    window against this provider should get the same 24 rows rather than
    the single midnight row a literal reading would select. `start` is
    never widened this way -- only `end` names a closing boundary that a
    bare date could ambiguously read as "the start of that day" instead of
    "through the end of that day".

    Raises:
        ValueError: if either argument cannot be parsed by
            `_to_utc_timestamp`, or if the resolved end precedes the
            resolved start.
    """
    start_ts = _to_utc_timestamp(start)
    end_ts = _to_utc_timestamp(end)

    if "T" not in end and ":" not in end:
        end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)

    if end_ts < start_ts:
        raise ValueError(
            f"nsrdb_provider: resolved end {end_ts} precedes resolved start "
            f"{start_ts} (from start={start!r}, end={end!r})"
        )

    return start_ts, end_ts


def _years_spanned(start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> list[int]:
    """
    Return the ascending list of calendar years spanned by [start_ts,
    end_ts], e.g. [2023, 2024] for a window crossing that boundary.

    Raises:
        ValueError: naming the offending year and `NSRDB_FIRST_COVERED_YEAR`
            when any spanned year precedes the product's covered range.
            Raised before any request is issued, so an out-of-range request
            costs nothing and fails with a message about the product rather
            than a remote validation error. There is deliberately no
            matching check against an upper bound -- see
            `NSRDB_FIRST_COVERED_YEAR`'s comment.
    """
    years = list(range(start_ts.year, end_ts.year + 1))
    for year in years:
        if year < NSRDB_FIRST_COVERED_YEAR:
            raise ValueError(
                f"nsrdb_provider: requested year {year} precedes NSRDB PSM "
                f"v4 GOES CONUS coverage, which begins at "
                f"NSRDB_FIRST_COVERED_YEAR={NSRDB_FIRST_COVERED_YEAR}."
            )
    return years


def fetch_nsrdb(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """
    Fetch GHI from NSRDB PSM v4 (GOES CONUS) for one (lat, lon) point over
    an arbitrary [start, end] window, including one crossing a calendar-year
    boundary.

    NSRDB's CSV endpoint takes a single year in its `names` parameter and
    has no start/end parameter at all (08-RESEARCH.md Pitfall 2), so this
    function issues one request per calendar year spanned by the window,
    concatenates the per-year frames, and filters the result back down to
    the caller's actual window. A window inside one calendar year still
    issues exactly one request -- the loop is the general case, not an
    unconditional fan-out. Request volume consequence: one request per
    spanned calendar year per city, against a documented standard-key
    limit of 1,000 requests/hour, so a four-city eight-year backfill is 32
    requests. No retry, no backoff and no concurrency are added here -- a
    rate-limited response is a non-2xx and is handled like any other
    rejection (Task 2's error handler).

    Args:
        lat, lon: The target point's coordinates, latitude-first (matching
            `config.CITY_COORDINATES`).
        start, end: ISO-8601 or bare-date strings. A bare-date `end` covers
            that whole calendar day (`_window_bounds`).

    Returns:
        A DataFrame with exactly the columns ["datetime_utc",
        "solar_radiation"], in PIPELINE_SCHEMA units (W/m²). `datetime_utc`
        is tz-aware UTC, monotonically increasing, filtered to [start, end]
        inclusive, and carries no duplicate timestamp across a year seam
        (the first occurrence wins). No wind, temperature, or humidity
        column is ever present (D-02).

    Raises:
        EnvironmentError: if `NREL_API_KEY` or `NREL_API_EMAIL` is unset --
            this machine is misconfigured. Raised before any network call,
            both credential lookups being the first two statements below.
        ValueError: if a date argument cannot be parsed; if any spanned
            year precedes `NSRDB_FIRST_COVERED_YEAR`; if a response body is
            not a well-formed PSM v4 CSV; if the filtered result selects
            zero rows (07-CONTEXT.md D-05's fail-loud precedent -- NSRDB is
            a standalone primary on this path, not a supplement with a
            real-outage carve-out); or if a GHI value falls outside
            `units_def.PIPELINE_SCHEMA`'s declared range for
            `solar_radiation`. Deliberately a different exception type from
            `EnvironmentError`: a misconfigured machine and a malformed
            provider response are different failure modes, and Phase 10's
            fallback logic is meant to treat them differently.
    """
    api_key = _nrel_api_key()
    email = _nrel_contact_email()

    start_ts, end_ts = _window_bounds(start, end)
    years = _years_spanned(start_ts, end_ts)

    frames = []
    for year in years:
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

        # No .raise_for_status() call here: requests' HTTPError message
        # embeds the request URL, which carries api_key and email in its
        # query string -- letting that exception propagate would leak
        # both. The response body is handed straight to _parse_psm4_csv,
        # which fails loud on anything that isn't a well-formed PSM v4
        # CSV. Task 2 adds a dedicated dual-shape error check here, before
        # the parse, for a non-2xx response.
        r = requests.get(NSRDB_BASE, params=params, timeout=60)

        frame, _metadata = _parse_psm4_csv(r.text)

        frame["datetime_utc"] = pd.to_datetime(
            frame[["Year", "Month", "Day", "Hour", "Minute"]], utc=True
        )
        frame["solar_radiation"] = pd.to_numeric(frame["GHI"], errors="coerce")
        frames.append(frame[["datetime_utc", "solar_radiation"]])

    combined = pd.concat(frames, ignore_index=True)
    combined = combined[
        (combined["datetime_utc"] >= start_ts) & (combined["datetime_utc"] <= end_ts)
    ]
    combined = combined.sort_values("datetime_utc")
    combined = combined.drop_duplicates(subset="datetime_utc", keep="first")
    combined = combined.reset_index(drop=True)

    if combined.empty:
        raise ValueError(
            f"nsrdb_provider: window [{start_ts}, {end_ts}] selected zero "
            f"rows across {len(years)} year(s) of NSRDB data -- raising "
            "rather than returning an empty frame a caller could mistake "
            "for night-time (07-CONTEXT.md D-05)."
        )

    _range_check(combined)

    return combined
