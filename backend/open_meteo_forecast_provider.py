"""
Open-Meteo Forecast-Archive Provider Adapter (D-01, Phase 3 experiment)
========================================================================
Fetches real, past model-run NWP forecast output -- not reanalysis -- from
two Open-Meteo endpoints and normalizes the response into the same
`PIPELINE_SCHEMA`-named columns `open_meteo_provider`'s Archive (reanalysis)
adapter produces:

- `historical-forecast-api.open-meteo.com` (bulk date-range mode):
  a continuous stitched-together series of past model-run output, used as
  this phase's main forecast data volume. `fetch_historical_forecast`.
- `single-runs-api.open-meteo.com` (`&run=<timestamp>` mode): one exact
  model run at its native forecast leads, used only by
  `forecast_leadtime_calibration.py` to empirically verify what lead time
  the bulk product actually carries. `fetch_single_run`.

This module is the forecast-archive sibling of `open_meteo_provider`'s
reanalysis adapter -- a fifth entry in this repo's provider-adapter tier,
not a subclass and not a monkeypatch of it. Importing this module performs
no network call, no file I/O and no environment variable read, exactly as
the Archive adapter's own docstring promises for itself.

The forecast model identifier is pinned to `FORECAST_MODEL_ID` and is never
left to either endpoint's own automatic-selection default. That unpinned
default resolves to a *different* model domain per location and per
endpoint -- 03-RESEARCH.md live-observed the Single-Runs endpoint's
automatic selection resolving to a German regional model (ICON) for an
Austin request, while the bulk endpoint's automatic selection resolved
elsewhere -- which would silently destroy the deterministic lead rule
(`lead_hours = valid_time.hour % 6`) this whole phase's calibration gate
depends on. `ecmwf_ifs` was selected because it alone showed the
bit-identical bulk/single-run alignment at leads 0-5, while the
superficially more obvious `ecmwf_ifs025` (0.25-degree ECMWF) showed no such
alignment and only reaches back to April 2026.

Both endpoints answer an out-of-archive-depth or out-of-horizon request with
HTTP 200 and a null-filled array rather than an error -- this is why this
module adds an explicit completeness check (`_completeness_check`) that the
Archive adapter does not need: the Archive adapter's `_range_check` drops
nulls before comparing values (`pd.to_numeric(...).dropna()`) and is
therefore structurally blind to this failure mode. Nothing in this module is
ever padded, truncated, zero-filled, forward-filled, or back-filled to
paper over a null -- an absent value here is a failed fetch, never a null
column (mirrors D-04/D-05 in `open_meteo_provider`).
"""

import logging

import pandas as pd
import requests

import config
import open_meteo_provider
import units_def

log = logging.getLogger(__name__)

# All three forecast-family base URLs are declared here, together, even
# though this module's functions only use the first two -- Plan 03-06 is the
# Previous-Runs API's only consumer, so all three live in one place rather
# than being introduced piecemeal. Each is, like
# `open_meteo_provider.OPEN_METEO_ARCHIVE_BASE`, a fixed constant -- never
# built from caller input. No function in this module accepts a URL, a
# base, a host, or a path fragment from a caller (T-03-01).
OPEN_METEO_HISTORICAL_FORECAST_BASE: str = "https://historical-forecast-api.open-meteo.com/v1/forecast"
OPEN_METEO_SINGLE_RUNS_BASE: str = "https://single-runs-api.open-meteo.com/v1/forecast"
OPEN_METEO_PREVIOUS_RUNS_BASE: str = "https://previous-runs-api.open-meteo.com/v1/forecast"

# Pinned model identifier. Live evidence (03-RESEARCH.md Pattern 2): with
# this model pinned on both endpoints, the bulk product's value at valid
# time T is bit-identical to the `run = T.floor('6h')` single run's value at
# lead `T.hour % 6`, across three cities (Austin, El Paso, Corpus Christi)
# and three seasons, with a clean cut at lead 6 (MAE ~0 for leads 0-5, MAE
# 0.26-0.58 m/s for leads 6-8). `ecmwf_ifs025` showed no such alignment
# (L1:1/4 L2:0/4 L4:0/4 L5:0/4) and only reaches back to 2026-04-02.
FORECAST_MODEL_ID: str = "ecmwf_ifs"

# The three mapping tables below are imported BY IDENTITY from
# open_meteo_provider, not restated -- the Historical Forecast API's
# response envelope is byte-for-byte the same shape as the Archive API's
# (03-RESEARCH.md Pattern 1), so the request and the response parsing for
# this module can never drift apart from the Archive adapter's.
HOURLY_TO_PIPELINE = open_meteo_provider.HOURLY_TO_PIPELINE
OPEN_METEO_HOURLY_VARS = open_meteo_provider.OPEN_METEO_HOURLY_VARS
EXPECTED_HOURLY_UNITS = open_meteo_provider.EXPECTED_HOURLY_UNITS


class SingleRunUnavailable(Exception):
    """
    Raised only for the archive-boundary condition where a well-formed
    Single-Runs `run=` timestamp names a model run the archive does not
    reach -- distinct from a malformed `run` timestamp, which is a bug and
    propagates as the underlying HTTP error (03-RESEARCH.md Pitfall 4).
    `forecast_leadtime_calibration.measure_lead_alignment` catches this
    exception to count and report archive-boundary skips separately from
    genuine bugs.
    """


def _to_run_timestamp(value) -> str:
    """
    Coerce an ISO-8601 timestamp, a bare-date string, or a `pd.Timestamp`
    into the Single-Runs API's `run=` format.

    Live-measured (03-RESEARCH.md Pitfall 4): this endpoint's `run`
    parameter is stricter than general ISO 8601. Only the no-seconds,
    no-zone-suffix spelling `YYYY-MM-DDTHH:MM` is accepted --
    `2026-09-25T00:00Z`, `2026-09-25T00:00:00Z`, and `2026-09-25 00:00`
    (space separator) all return HTTP 400 `"Bad Request"`.

    Raises:
        ValueError: naming the offending value, when it cannot be parsed by
            `pd.Timestamp`.
    """
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"open_meteo_forecast_provider: cannot parse run timestamp "
            f"{value!r}: {exc}"
        ) from exc

    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    return ts.strftime("%Y-%m-%dT%H:%M")


def _completeness_check(
    hourly: dict,
    provider_keys,
    n: int,
    context: str,
    allow_leading_null_for: tuple = (),
) -> None:
    """
    Raise `ValueError` naming the module, the variable, the null count, the
    array length and the context, when any requested variable array in
    `hourly` contains a `None` entry (03-RESEARCH.md Pitfall 3).

    Both new endpoints answer an out-of-archive-depth or out-of-horizon
    request with HTTP 200 and a null-filled array rather than an error, so
    an absent value here is a failed fetch -- it is never forward-filled,
    back-filled, or otherwise substituted.

    `allow_leading_null_for` is a narrow, documented carve-out for
    variables whose index 0 is legitimately undefined -- `shortwave_radiation`
    on a Single-Runs response, where the flux is undefined at the analysis
    step (live-measured 167 of 168 non-null, index 0 null). The carve-out
    tolerates a null at index 0 ONLY; a null anywhere else in that array
    still raises.

    This check runs BEFORE `open_meteo_provider._range_check`, because that
    function drops nulls before comparing (`pd.to_numeric(...).dropna()`)
    and is therefore structurally blind to this failure mode.
    """
    for provider_key in provider_keys:
        values = hourly[provider_key]
        null_indices = [i for i, v in enumerate(values) if v is None]
        if not null_indices:
            continue
        if provider_key in allow_leading_null_for and null_indices == [0]:
            continue
        raise ValueError(
            f"open_meteo_forecast_provider: {provider_key!r} has "
            f"{len(null_indices)}/{n} null value(s) in {context} -- an "
            "out-of-archive-depth or out-of-horizon request returns HTTP "
            "200 with nulls, not an error. Never forward-filled, "
            "back-filled, padded, or otherwise substituted."
        )


def _parse_hourly_response(
    data: dict,
    provider_keys,
    context: str,
    allow_leading_null_for: tuple = (),
) -> pd.DataFrame:
    """
    Parse an Open-Meteo hourly-forecast response body into a PIPELINE_SCHEMA
    -named DataFrame, reusing the Archive adapter's five sequential checks
    (body parses as JSON handled by the caller; `hourly` is a dict; `time`
    is a non-empty list; every requested variable array is present and
    length-matched; the `hourly_units` echo matches expectations), then the
    completeness check (Pitfall 3), then `open_meteo_provider._range_check`.

    Error messages name this module, not the Archive adapter.
    """
    hourly = data.get("hourly")
    if not isinstance(hourly, dict):
        raise ValueError(
            f"open_meteo_forecast_provider: {context} response is missing "
            f"a valid 'hourly' object, got {type(hourly).__name__}"
        )

    time = hourly.get("time")
    if not isinstance(time, list) or len(time) == 0:
        raise ValueError(
            f"open_meteo_forecast_provider: {context} response's "
            f"'hourly.time' array is missing, not a list, or empty "
            f"(got {time!r})"
        )
    n = len(time)

    for provider_key in provider_keys:
        if provider_key not in hourly:
            raise ValueError(
                f"open_meteo_forecast_provider: {context} response is "
                f"missing the {provider_key!r} variable array under "
                "'hourly' -- a missing variable is a failed fetch, never "
                "substituted with a null column."
            )
        values = hourly[provider_key]
        if not isinstance(values, list) or len(values) != n:
            got_len = len(values) if isinstance(values, list) else type(values).__name__
            raise ValueError(
                f"open_meteo_forecast_provider: {context} {provider_key!r} "
                f"array length ({got_len}) does not match 'hourly.time' "
                f"length ({n}) -- never padded or truncated to fit."
            )

    hourly_units = data.get("hourly_units")
    if isinstance(hourly_units, dict):
        for provider_key in provider_keys:
            expected_unit = EXPECTED_HOURLY_UNITS.get(provider_key)
            if expected_unit is None:
                continue
            echoed_unit = hourly_units.get(provider_key)
            if echoed_unit is None:
                continue
            if echoed_unit != expected_unit:
                raise ValueError(
                    f"open_meteo_forecast_provider: {context} response "
                    f"echoed unit {echoed_unit!r} for {provider_key!r}, "
                    f"expected {expected_unit!r} -- check the request "
                    "parameter for a dropped or ignored unit override."
                )

    _completeness_check(
        hourly, provider_keys, n, context,
        allow_leading_null_for=allow_leading_null_for,
    )

    frame = pd.DataFrame({"datetime_utc": pd.to_datetime(time, utc=True)})
    for provider_key in provider_keys:
        pipeline_col = HOURLY_TO_PIPELINE.get(provider_key)
        if pipeline_col is not None:
            frame[pipeline_col] = hourly[provider_key]

    open_meteo_provider._range_check(frame)

    return frame


def fetch_historical_forecast(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """
    Fetch the bulk Historical Forecast series for one (lat, lon) point over
    [start, end], in exactly one HTTP request, with `models` pinned to
    `FORECAST_MODEL_ID`.

    This endpoint's relative-window parameters (the number of hours ahead of
    or behind "now" to serve) are live-confirmed mutually exclusive with a
    `start_date`/`end_date` range (03-RESEARCH.md `<verified_facts>`) and
    must not be sent here.

    Returns:
        A DataFrame with exactly the same six columns
        `open_meteo_provider.fetch_open_meteo` returns: `datetime_utc`
        (tz-aware UTC), `air_temp`, `wind_speed`, `wind_direction`,
        `solar_radiation`, `relative_humidity`.

    Raises:
        requests.HTTPError: propagated unchanged from `raise_for_status()`.
        ValueError: on any malformed/missing/short body shape, any unit
            mismatch, any out-of-range value, or any null in any requested
            variable array (a failed fetch is never a null column).
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": open_meteo_provider._to_archive_date(start),
        "end_date": open_meteo_provider._to_archive_date(end),
        "hourly": ",".join(OPEN_METEO_HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "models": FORECAST_MODEL_ID,
    }
    r = requests.get(
        OPEN_METEO_HISTORICAL_FORECAST_BASE,
        params=params,
        timeout=config.FORECAST_EXPERIMENT_HTTP_TIMEOUT_S,
    )
    r.raise_for_status()

    try:
        data = r.json()
    except ValueError as exc:
        raise ValueError(
            f"open_meteo_forecast_provider: bulk response body could not "
            f"be parsed as JSON: {exc}"
        ) from exc

    return _parse_hourly_response(
        data, OPEN_METEO_HOURLY_VARS, context="bulk historical-forecast fetch",
    )


def fetch_single_run(lat: float, lon: float, run, hourly_vars=None) -> pd.DataFrame:
    """
    Fetch one exact model run from the Single-Runs API, in exactly one HTTP
    request, with `models` pinned to `FORECAST_MODEL_ID`.

    This endpoint live-confirmed rejects a `start_date`/`end_date` range
    outright (`{"error":true,"reason":"Parameter 'start_date' must not be
    set"}`) -- neither is ever sent here.

    Two distinct HTTP 400 bodies must be distinguished before
    `raise_for_status` is allowed to propagate (03-RESEARCH.md Pitfall 4):
    a body whose `reason` names an unavailable model run
    ("The requested model run is not available...") is an expected
    archive-boundary condition and raises `SingleRunUnavailable`, for the
    calibration gate to count and report; any other 400 -- notably the bare
    `"Bad Request"` a malformed run timestamp produces -- is a bug and
    propagates as the underlying `requests.HTTPError`.

    Args:
        lat, lon: The target point's coordinates.
        run: An ISO-8601 timestamp, bare-date string, or `pd.Timestamp`
            naming the model run's initialization time.
        hourly_vars: The provider variable keys to request. Defaults to
            `OPEN_METEO_HOURLY_VARS`.

    Returns:
        A DataFrame with `datetime_utc` plus one column per requested
        variable's pipeline name.

    Raises:
        SingleRunUnavailable: the run is well-formed but archive-boundary
            unavailable.
        requests.HTTPError: any other HTTP error, including a malformed
            run timestamp's bare 400.
        ValueError: on any malformed/missing/short body shape, any unit
            mismatch, any out-of-range value, or a disallowed null.
    """
    if hourly_vars is None:
        hourly_vars = OPEN_METEO_HOURLY_VARS

    run_ts = _to_run_timestamp(run)
    params = {
        "latitude": lat,
        "longitude": lon,
        "run": run_ts,
        "hourly": ",".join(hourly_vars),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "models": FORECAST_MODEL_ID,
    }
    r = requests.get(
        OPEN_METEO_SINGLE_RUNS_BASE,
        params=params,
        timeout=config.FORECAST_EXPERIMENT_HTTP_TIMEOUT_S,
    )

    if r.status_code == 400:
        try:
            body = r.json()
        except ValueError:
            body = {}
        reason = body.get("reason", "") if isinstance(body, dict) else ""
        if "not available" in reason:
            raise SingleRunUnavailable(
                f"open_meteo_forecast_provider: model run not available -- "
                f"model={FORECAST_MODEL_ID!r} run={run_ts!r}: {reason}"
            )
        # A malformed run timestamp (or any other bad-request cause) is a
        # bug, not a boundary condition -- let raise_for_status propagate.

    r.raise_for_status()

    try:
        data = r.json()
    except ValueError as exc:
        raise ValueError(
            f"open_meteo_forecast_provider: single-run response body "
            f"could not be parsed as JSON: {exc}"
        ) from exc

    return _parse_hourly_response(
        data, hourly_vars, context=f"single-run fetch (run={run_ts!r})",
        allow_leading_null_for=("shortwave_radiation",),
    )
