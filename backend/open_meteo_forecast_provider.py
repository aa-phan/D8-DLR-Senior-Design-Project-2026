"""
Open-Meteo Forecast-Archive Provider Adapter (D-01 legacy 1h arm + D-04
PRIMARY 24h arm, Phase 3 experiment)
========================================================================
Fetches real, past model-run NWP forecast output -- not reanalysis -- from
THREE Open-Meteo endpoints and normalizes the response into the same
`PIPELINE_SCHEMA`-named columns `open_meteo_provider`'s Archive (reanalysis)
adapter produces:

- `historical-forecast-api.open-meteo.com` (bulk date-range mode):
  a continuous stitched-together series of past model-run output, used as
  the LEGACY 1-hour, now non-primary curiosity arm's forecast data volume
  (D-01, downgraded by D-04). `fetch_historical_forecast`.
- `single-runs-api.open-meteo.com` (`&run=<timestamp>` mode): one exact
  model run at its native forecast leads, used by
  `forecast_leadtime_calibration.py` to empirically verify what lead time
  BOTH the legacy bulk product and the primary Previous-Runs product
  actually carry. `fetch_single_run`.
- `previous-runs-api.open-meteo.com` (bulk date-range mode,
  `<var>_previous_dayN` columns): a continuous stitched-together series of
  each day's prior-day model-run output, used as D-04's PRIMARY 24-hour-lead
  forecast data volume. `fetch_previous_runs`.

This module is the forecast-archive sibling of `open_meteo_provider`'s
reanalysis adapter -- a fifth entry in this repo's provider-adapter tier,
not a subclass and not a monkeypatch of it. Importing this module performs
no network call, no file I/O and no environment variable read, exactly as
the Archive adapter's own docstring promises for itself.

The forecast model identifier is pinned -- `FORECAST_MODEL_ID` for the
legacy Historical-Forecast/Single-Runs pair, `PREVIOUS_RUNS_MODEL_ID` for
the Previous-Runs pair -- and is never left to either endpoint's own
automatic-selection default. That unpinned default resolves to a
*different* model domain per location and per endpoint -- 03-RESEARCH.md
live-observed the Single-Runs endpoint's automatic selection resolving to a
German regional model (ICON) for an Austin request, while the bulk endpoint's
automatic selection resolved elsewhere -- which would silently destroy the
deterministic lead rules (`lead_hours = valid_time.hour % 6` for the legacy
arm, `lead_hours = 24 + valid_time.hour % 6` for the primary arm) this
phase's calibration gates depend on. `ecmwf_ifs` was selected for the legacy
pair because it alone showed the bit-identical bulk/single-run alignment at
leads 0-5, while the superficially more obvious `ecmwf_ifs025` (0.25-degree
ECMWF) showed no such alignment and only reaches back to April 2026.
`gfs_seamless` was selected for the Previous-Runs pair for the DIFFERENT
reason documented at `PREVIOUS_RUNS_MODEL_ID`'s own declaration -- these two
pins are intentionally different models on two independently-provisioned
archives, not an inconsistency to reconcile (03-RESEARCH.md Pitfall 2).

All three endpoints answer an out-of-archive-depth or out-of-horizon request
with HTTP 200 and a null-filled array rather than an error -- this is why
this module adds an explicit completeness check (`_completeness_check`) that
the Archive adapter does not need: the Archive adapter's `_range_check` drops
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

# Pinned model identifier for the Previous Runs API (D-04, 03-RESEARCH.md
# Pattern 1) -- a SEPARATE constant from FORECAST_MODEL_ID above, never a
# reuse of it. Live-verified this session: pinning FORECAST_MODEL_ID
# ("ecmwf_ifs") on THIS endpoint returns HTTP 200 with a fully null array for
# almost the entire candidate window (24/24 null for a 2024-06-01 AUSTIN
# request) -- its Previous-Runs archive only reaches back a few months, a
# completely different (and much shallower) depth story than its
# Historical-Forecast/Single-Runs depth (March 2024) the legacy arm relies
# on. These are two INDEPENDENTLY-PROVISIONED archives on Open-Meteo's side
# for the same model name; depth on one endpoint says nothing about depth on
# the other, and that is the correct state, not an inconsistency for a
# future refactor to reconcile (03-RESEARCH.md Pitfall 2).
#
# The endpoint's automatic ("best_match") selection was live-confirmed this
# session to resolve to this exact model, with an identical grid-point snap
# and identical values, for all four project cities (AUSTIN, EL_PASO,
# MIDLAND, CORPUS_CHRISTI) -- but the pin is explicit anyway, for the same
# reason FORECAST_MODEL_ID is explicit: an auto-resolved default can
# silently re-resolve later, and this phase does not build a primary
# comparison arm on an unpinned foundation.
PREVIOUS_RUNS_MODEL_ID: str = "gfs_seamless"

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
    response_suffix: str = "",
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
    still raises. It is checked against the UNSUFFIXED `provider_key`, since
    callers (e.g. `fetch_single_run`) pass the carve-out as base variable
    names, matching `EXPECTED_HOURLY_UNITS`/`HOURLY_TO_PIPELINE`'s own keys.

    `response_suffix` (e.g. `"_previous_day1"`) is appended to `provider_key`
    to form the actual key looked up in `hourly` -- the Previous-Runs API
    echoes suffixed keys in its response body, while `provider_keys` and the
    mapping tables stay unsuffixed base names (03-RESEARCH.md's Code
    Examples section). Error messages quote the actual suffixed response key
    that was looked for, so a future suffix change is diagnosable from the
    message alone.

    This check runs BEFORE `open_meteo_provider._range_check`, because that
    function drops nulls before comparing (`pd.to_numeric(...).dropna()`)
    and is therefore structurally blind to this failure mode.
    """
    for provider_key in provider_keys:
        response_key = provider_key + response_suffix
        values = hourly[response_key]
        null_indices = [i for i, v in enumerate(values) if v is None]
        if not null_indices:
            continue
        if provider_key in allow_leading_null_for and null_indices == [0]:
            continue
        raise ValueError(
            f"open_meteo_forecast_provider: {response_key!r} has "
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
    response_suffix: str = "",
) -> pd.DataFrame:
    """
    Parse an Open-Meteo hourly-forecast response body into a PIPELINE_SCHEMA
    -named DataFrame, reusing the Archive adapter's five sequential checks
    (body parses as JSON handled by the caller; `hourly` is a dict; `time`
    is a non-empty list; every requested variable array is present and
    length-matched; the `hourly_units` echo matches expectations), then the
    completeness check (Pitfall 3), then `open_meteo_provider._range_check`.

    `response_suffix` (default `""`, leaving existing callers byte-identical
    in behavior) is appended to each `provider_key` to form the ACTUAL key
    looked up in the response body's `hourly`/`hourly_units` dicts -- the
    Previous-Runs API echoes `<var>_previous_dayN`-suffixed keys in both
    (live-confirmed: `wind_speed_10m_previous_day1`). The UNSUFFIXED
    `provider_key` is always used for the `EXPECTED_HOURLY_UNITS` and
    `HOURLY_TO_PIPELINE` lookups -- those two tables are keyed on base
    variable names. If the suffix were instead passed to those tables'
    `.get()` calls, a lookup miss would silently disable the unit-echo check
    (returning `None`, taking the `continue` branch) rather than raising --
    a check silently disabling itself is worse than no check at all.

    Error messages name this module, not the Archive adapter, and quote the
    actual (possibly suffixed) response key that was looked for.
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
        response_key = provider_key + response_suffix
        if response_key not in hourly:
            raise ValueError(
                f"open_meteo_forecast_provider: {context} response is "
                f"missing the {response_key!r} variable array under "
                "'hourly' -- a missing variable is a failed fetch, never "
                "substituted with a null column."
            )
        values = hourly[response_key]
        if not isinstance(values, list) or len(values) != n:
            got_len = len(values) if isinstance(values, list) else type(values).__name__
            raise ValueError(
                f"open_meteo_forecast_provider: {context} {response_key!r} "
                f"array length ({got_len}) does not match 'hourly.time' "
                f"length ({n}) -- never padded or truncated to fit."
            )

    hourly_units = data.get("hourly_units")
    if isinstance(hourly_units, dict):
        for provider_key in provider_keys:
            response_key = provider_key + response_suffix
            expected_unit = EXPECTED_HOURLY_UNITS.get(provider_key)
            if expected_unit is None:
                continue
            echoed_unit = hourly_units.get(response_key)
            if echoed_unit is None:
                continue
            if echoed_unit != expected_unit:
                raise ValueError(
                    f"open_meteo_forecast_provider: {context} response "
                    f"echoed unit {echoed_unit!r} for {response_key!r}, "
                    f"expected {expected_unit!r} -- check the request "
                    "parameter for a dropped or ignored unit override."
                )

    _completeness_check(
        hourly, provider_keys, n, context,
        allow_leading_null_for=allow_leading_null_for,
        response_suffix=response_suffix,
    )

    frame = pd.DataFrame({"datetime_utc": pd.to_datetime(time, utc=True)})
    for provider_key in provider_keys:
        pipeline_col = HOURLY_TO_PIPELINE.get(provider_key)
        if pipeline_col is not None:
            frame[pipeline_col] = hourly[provider_key + response_suffix]

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


def fetch_single_run(lat: float, lon: float, run, hourly_vars=None, forecast_days=None, model=None, timeout=None) -> pd.DataFrame:
    """
    Fetch one exact model run from the Single-Runs API, in exactly one HTTP
    request, with `models` pinned to `FORECAST_MODEL_ID` by default.

    `model` (additive keyword, appended last; default `None` resolves to
    `FORECAST_MODEL_ID`, leaving both existing call sites -- this module's
    own tests and `forecast_leadtime_calibration.measure_lead_alignment` --
    byte-identical in behavior) lets a caller query the Single-Runs endpoint
    under a DIFFERENT pinned model. Task 2's 24-hour offset-lead
    cross-check needs this to query Single-Runs under `PREVIOUS_RUNS_
    MODEL_ID` ("gfs_seamless") rather than the legacy `FORECAST_MODEL_ID`
    ("ecmwf_ifs") -- the alternative, a second near-duplicate fetch
    function, is exactly the duplication 03-RESEARCH.md's "Don't Hand-Roll"
    guidance forbids.

    `timeout` (additive keyword, appended last; default `None` keeps
    `config.FORECAST_EXPERIMENT_HTTP_TIMEOUT_S`, so every existing caller,
    including the frozen experiment harness, is unchanged) lets the live shadow
    collector use a shorter per-attempt read timeout together with its own
    retry loop.

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

    A single run's response array is fixed-length (live-measured 168 hours
    -- 7 days -- for `ecmwf_ifs`) regardless of the model's actual forecast
    depth; hours beyond the model's real output are null-padded rather than
    omitted (the same out-of-horizon null behavior Pitfall 3 documents for
    the bulk endpoint). `forecast_days` truncates the request to the given
    number of days via the endpoint's own `forecast_days` parameter
    (live-confirmed: `forecast_days=1` returns exactly the first 24 hours,
    null-free) -- callers who only need a few leading hours (e.g. this
    module's own calibration gate, which never looks past lead 11) should
    pass a small value so the completeness check never has to reject
    tail-padding nulls it was never going to use.

    Args:
        lat, lon: The target point's coordinates.
        run: An ISO-8601 timestamp, bare-date string, or `pd.Timestamp`
            naming the model run's initialization time.
        hourly_vars: The provider variable keys to request. Defaults to
            `OPEN_METEO_HOURLY_VARS`.
        forecast_days: Optional truncation of the response to this many
            days from `run`. Omitted (the default) requests the endpoint's
            own default full-length response.

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
    if model is None:
        model = FORECAST_MODEL_ID

    run_ts = _to_run_timestamp(run)
    params = {
        "latitude": lat,
        "longitude": lon,
        "run": run_ts,
        "hourly": ",".join(hourly_vars),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "models": model,
    }
    if forecast_days is not None:
        params["forecast_days"] = forecast_days
    r = requests.get(
        OPEN_METEO_SINGLE_RUNS_BASE,
        params=params,
        timeout=config.FORECAST_EXPERIMENT_HTTP_TIMEOUT_S if timeout is None else timeout,
        # `Connection: close` (2026-10-07): confirmed via an isolated-runner
        # diagnostic that calling this endpoint twice within the SAME
        # process -- once per city, back-to-back, in
        # forecast_shadow_collect.py's own loop -- reproducibly times out
        # on the second call, while the identical request from two
        # separate processes (or two separate GitHub Actions runners)
        # succeeds every time. The published Open-Meteo free-tier rate
        # limits (600 calls/min) are far too generous to explain this, and
        # no rate-limit header is exposed either way -- ruling out a
        # documented quota as the cause. This points at per-process
        # HTTP keep-alive/connection-pool reuse (each `requests.get` call
        # already opens its own short-lived `Session`, but an underlying
        # kept-alive TCP/TLS connection to the same host could still be
        # reused across calls at a lower layer) as the most likely
        # mechanism. Forcing the connection closed after this response is
        # the direct, minimal mitigation for that specific hypothesis --
        # if repeated-city runs still fail after this, that hypothesis
        # itself needs revisiting, the same discipline applied to the
        # now-abandoned rate-limit theory.
        headers={"Connection": "close"},
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
                f"model={model!r} run={run_ts!r}: {reason}"
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

    # Live-observed archive-boundary condition beyond the documented HTTP
    # 400 case: a well-formed, in-range `run` can also come back HTTP 200
    # with EVERY requested variable's array fully null -- the run simply
    # was never archived for this model, and the endpoint reports that
    # with a null-filled 200 rather than a "not available" 400. This is
    # only checked when every requested variable is null for its entire
    # array (never a single variable or a partial gap, which stays a hard
    # failure via _completeness_check below) -- a total-null response is
    # the boundary condition; a partial one is still a failed fetch.
    hourly = data.get("hourly") if isinstance(data, dict) else None
    if isinstance(hourly, dict):
        arrays = [hourly.get(key) for key in hourly_vars]
        if arrays and all(
            isinstance(arr, list) and len(arr) > 0 and all(v is None for v in arr)
            for arr in arrays
        ):
            raise SingleRunUnavailable(
                f"open_meteo_forecast_provider: model run not available -- "
                f"model={model!r} run={run_ts!r}: HTTP 200 with "
                f"every requested variable fully null (archive gap, not "
                f"surfaced as an HTTP 400 by this endpoint)"
            )

    return _parse_hourly_response(
        data, hourly_vars, context=f"single-run fetch (run={run_ts!r}, model={model!r})",
        allow_leading_null_for=("shortwave_radiation",),
    )


def fetch_previous_runs(lat: float, lon: float, start: str, end: str, previous_day=None) -> pd.DataFrame:
    """
    Fetch the bulk Previous Runs series for one (lat, lon) point over
    [start, end], in exactly one HTTP request, with `models` pinned to
    `PREVIOUS_RUNS_MODEL_ID` (D-04, 03-RESEARCH.md Pattern 1/2).

    `previous_day` (default `config.FORECAST_EXPERIMENT_PREVIOUS_DAY`, = 1)
    selects which `<var>_previous_dayN` column family to request. Each
    requested `hourly` variable name carries the suffix
    `f"_previous_day{previous_day}"`; the response echoes that same
    suffixed key in both `hourly` and `hourly_units` (live-confirmed:
    `wind_speed_10m_previous_day1`), stripped by `_parse_hourly_response`'s
    `response_suffix` keyword before the Archive adapter's `HOURLY_TO_
    PIPELINE`/`EXPECTED_HOURLY_UNITS` lookups (both keyed on unsuffixed base
    names) are consulted -- so the unit-echo check still fires on this path
    rather than silently skipping via a suffix-mismatched dictionary lookup.

    Called WITHOUT any leading-null carve-out (`allow_leading_null_for` is
    omitted, so `_parse_hourly_response`'s empty-tuple default applies) --
    unlike `fetch_single_run`'s Single-Runs carve-out for
    `shortwave_radiation`'s index-0 null (that product's solar flux is
    undefined at the run's OWN analysis step), a `previous_dayN` value
    ALWAYS comes from a run already at least 24 hours old and is therefore
    never an analysis-step value. Live-confirmed this session: a
    2025-06-15 AUSTIN request for the suffixed solar, humidity and
    wind-direction arrays returned zero nulls, with index 0 = 318.0 W/m^2.
    A null anywhere in a Previous-Runs array is a genuine completeness
    failure and must raise -- never forward-filled, back-filled, padded, or
    otherwise substituted.

    EFFECTIVE LEAD (read before trusting a "24-hour" claim on this data):
    `previous_day1`'s effective lead at valid time `T` is
    `24 + (T.hour % 6)` hours -- exactly 24.0 h ONLY when `T.hour % 6 == 0`
    (03-RESEARCH.md Pattern 2, live-verified bit-for-bit against
    `single-runs-api` at all four six-hourly GFS cycles, 96 hour-cells
    across 2 cities, 2 dates and 2 variables, zero exceptions). This
    function does NOT filter or verify that rule itself -- see
    `forecast_leadtime_calibration.assert_exact_offset_lead` for the
    automated gate, and `forecast_experiment.filter_to_exact_lead` for
    where the exact-lead subset is selected for scoring. A caller of this
    function alone must not walk away believing the vendor's flat
    -24-hour-lead framing (Open-Meteo's own docs, and D-04's original
    `03-CONTEXT.md` text, both state it as flat -- both are incomplete).

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
    if previous_day is None:
        previous_day = config.FORECAST_EXPERIMENT_PREVIOUS_DAY

    suffix = f"_previous_day{previous_day}"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": open_meteo_provider._to_archive_date(start),
        "end_date": open_meteo_provider._to_archive_date(end),
        "hourly": ",".join(f"{var}{suffix}" for var in OPEN_METEO_HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "models": PREVIOUS_RUNS_MODEL_ID,
    }
    r = requests.get(
        OPEN_METEO_PREVIOUS_RUNS_BASE,
        params=params,
        timeout=config.FORECAST_EXPERIMENT_HTTP_TIMEOUT_S,
    )
    r.raise_for_status()

    try:
        data = r.json()
    except ValueError as exc:
        raise ValueError(
            f"open_meteo_forecast_provider: previous-runs response body "
            f"could not be parsed as JSON: {exc}"
        ) from exc

    return _parse_hourly_response(
        data, OPEN_METEO_HOURLY_VARS,
        context=f"previous-runs fetch (previous_day={previous_day})",
        response_suffix=suffix,
    )
