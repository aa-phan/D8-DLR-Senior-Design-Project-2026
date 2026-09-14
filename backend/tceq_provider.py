"""
TCEQ CAMS Daily Summary Provider Adapter (C4, Phase 9 / WX-01)
================================================================
Fetches hourly wind/temperature/relative-humidity observations from the
Texas Commission on Environmental Quality's public `daily_summary.pl` CGI
report for one Continuous Ambient Monitoring Station (CAMS) site, scraping
its HTML table with `bs4.BeautifulSoup` and normalizing the result into
`PIPELINE_SCHEMA`-named columns, converting units via `units_def.Q` (never
hand-rolled).

The endpoint is public and unauthenticated -- this module needs no token.
Importing this module has no side effects (no file I/O, no network calls,
no environment variable reads), mirroring `asos_provider.py`/
`weather_provider.py`'s own no-side-effects-on-import contract. A network
call only happens when `fetch_tceq` is actually called.

TCEQ reports every site's data in fixed Local Standard Time year-round
(never Daylight Saving) -- `TCEQ_FIXED_UTC_OFFSET_HOURS` is therefore a
plain integer table, never a `zoneinfo`/`pytz` lookup (09-RESEARCH.md
Pitfall 2, Pattern 3).

This tracer (Plan 09-01 Task 3) proves the vertical slice for one city
(Corpus Christi, CAMS 83) across a single calendar day. Plan 09-02 extends
`fetch_tceq` to real multi-day decomposition (D-09) and the full
fail-loud/error-handling surface for all four configured sites.
"""

import logging
import re

import pandas as pd
import requests
from bs4 import BeautifulSoup

import units_def
from units_def import Q

log = logging.getLogger(__name__)

# TCEQ_BASE: fixed constant -- never built from caller input.
TCEQ_BASE: str = "https://www.tceq.texas.gov/cgi-bin/compliance/monops/daily_summary.pl"

# TARGET_LABELS: daily_summary.pl row label (exact <strong> text) ->
# PIPELINE_SCHEMA column. Matched with `==` only, never `in`/substring --
# "Resultant Wind Direction" and "Std. Dev. Wind Direction" both contain the
# substring "Wind Direction" and would silently supply the wrong parameter's
# data under `wind_direction` if a substring match were used
# (09-RESEARCH.md Pattern 2).
TARGET_LABELS: dict[str, str] = {
    "Wind Speed": "wind_speed",
    "Wind Direction": "wind_direction",
    "Outdoor Temperature": "air_temp",
    "Relative Humidity": "relative_humidity",
}

# TCEQ_FIXED_UTC_OFFSET_HOURS: CAMS ID -> fixed integer UTC offset. TCEQ
# reports in Local Standard Time year-round -- the report page's own text
# says so, and each site's rendered label reads "CST" or "MST" even on a
# September fetch -- which is why this is a fixed integer table and not a
# call into a timezone database (09-RESEARCH.md Pitfall 2, Pattern 3).
# fetch_tceq raises ValueError naming the CAMS ID for any ID absent from
# this table, rather than defaulting to -6: an unknown site's true offset
# is not knowable from a default, and a wrong offset is silent.
#
# Per-site evidence (09-RESEARCH.md CAMS Site Selection): CAMS 38 (Austin),
# 83 (Corpus Christi), and 1095 (Midland) each render "All times shown are
# in CST" on their live report page; CAMS 41 (El Paso) renders "All times
# shown are in MST" -- all four confirmed on the SAME September fetch date,
# which is exactly why El Paso carries its own -7 rather than sharing the
# other three's -6: this is a real per-site timezone difference, not a
# label that would coincide if DST were in effect for all four.
TCEQ_FIXED_UTC_OFFSET_HOURS: dict[str, int] = {
    "38": -6,  # Austin -- CST, never DST-adjusted
    "83": -6,  # Corpus Christi -- CST, never DST-adjusted
    "1095": -6,  # Midland -- CST, never DST-adjusted
    "41": -7,  # El Paso -- MST, never DST-adjusted
}

_RETURN_COLUMNS = [
    "datetime_utc",
    "air_temp",
    "wind_speed",
    "wind_direction",
    "relative_humidity",
]

_HOUR_LABEL_RE = re.compile(r"^\d{4}$")

# TCEQ_MAX_DAYS_PER_FETCH: the self-imposed cap on calendar days a single
# fetch_tceq call may span. No rate limit is documented for daily_summary.pl
# and none was confirmed during research (09-RESEARCH.md Open Question 2) --
# this cap is this project's own restraint toward a free, unauthenticated,
# public government CGI endpoint, not a limit the server enforces. A caller
# needing a longer historical backfill should use Open-Meteo (WX-04)
# instead of looping this provider hundreds of times.
TCEQ_MAX_DAYS_PER_FETCH: int = 31


def _fetch_one_day(cams_id: str, year: int, month: int, day: int) -> str:
    """
    Issue one `daily_summary.pl` GET for `cams_id`'s report on the given
    calendar day and return the raw response body.

    `select_date=user` is REQUIRED -- omitting it silently returns TODAY's
    report at HTTP 200 for any requested date, with no error and no
    different response shape (09-RESEARCH.md Pitfall 1). `user_month` is
    0-indexed (January=0) per the report form's own <select> options.
    No custom headers are sent -- the endpoint is unauthenticated with no
    access control to defeat, so a browser-imitating identity buys nothing
    and misrepresents an automated consumer to a state agency.

    Raises:
        requests.HTTPError: propagated unchanged from `raise_for_status()`
            -- there is no credential in the URL, so unlike
            `nsrdb_provider` there is nothing to redact.
    """
    params = {
        "cams": cams_id,
        "select_date": "user",
        "user_month": month - 1,
        "user_day": day,
        "user_year": year,
        "time_format": "24hr",
    }
    r = requests.get(TCEQ_BASE, params=params, timeout=60)
    r.raise_for_status()
    return r.text


def _validate_response(html: str, cams_id: str):
    """
    Parse `html` and return the site's `<table border='1'>` data table, or
    raise if the response is not a genuine site-specific report.

    The endpoint answered HTTP 200 for a nonexistent CAMS ID during
    research -- rendering the generic site-selection form instead of a
    report -- so HTTP status is not a trust signal here (the same lesson
    `asos_provider.py` already encodes with its own response-body check,
    09-RESEARCH.md Pitfall 3). Requires BOTH a site-specific
    `<h1><a href=...CAMS=cams_id>` link AND a `<table border='1'>`
    element.

    Raises:
        ValueError: prefixed "tceq_provider:", naming `cams_id`, when
            either check fails.
    """
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    site_link = h1.find("a", href=lambda h: h and f"CAMS={cams_id}" in h) if h1 else None
    data_table = soup.find("table", attrs={"border": "1"})
    if site_link is None or data_table is None:
        raise ValueError(
            f"tceq_provider: no site-specific report found for CAMS "
            f"{cams_id!r} -- the endpoint returned the generic "
            "site-selection form instead of a report (unreachable, "
            "unknown CAMS ID, or the report page's structure changed)."
        )
    return data_table


def _hour_labels(data_table) -> list[str]:
    """
    Return the four-digit hour labels (e.g. "0000", "0100", ..., "2300")
    from `data_table`'s header row, in order.

    Deriving the hour count from the header rather than assuming 24 is
    what makes a partial same-day report (which returns only the hours
    elapsed so far -- 09-RESEARCH.md Pitfall 5) align correctly instead of
    silently shifting.
    """
    header_row = data_table.find("tr")
    if header_row is None:
        return []
    cells = header_row.find_all("td")
    labels = [c.get_text(strip=True) for c in cells]
    return [label for label in labels if _HOUR_LABEL_RE.match(label)]


def _extract_row_values(data_table, label: str, hour_count: int) -> list[float | None]:
    """
    Return the `hour_count` hourly values for the row whose `<strong>`
    label cell matches `label` EXACTLY (never `in`/substring -- see
    TARGET_LABELS' module comment), or an empty list if no row carries
    that label at all (the site does not monitor this parameter -- D-04
    territory for relative_humidity).

    A cell that fails `float(...)` (the "FEW"/"NA" placeholders --
    09-RESEARCH.md Pitfall 4) becomes `None`, not a raise: both are
    well-formed, expected states of a live report, not malformed
    responses.

    Raises:
        ValueError: if a matched row has fewer cells than
            `1 + hour_count` -- a truncated row would otherwise misalign
            hours against values.
    """
    for row in data_table.find_all("tr"):
        strong = row.find("strong")
        if strong is None or strong.get_text(strip=True) != label:
            continue
        cells = row.find_all("td")
        if len(cells) < 1 + hour_count:
            raise ValueError(
                f"tceq_provider: row {label!r} has {len(cells)} cell(s), "
                f"fewer than the required 1 + hour_count={1 + hour_count} "
                "-- a truncated row would misalign hours against values."
            )
        hourly_cells = cells[1 : 1 + hour_count]
        values: list[float | None] = []
        for cell in hourly_cells:
            text = cell.get_text(strip=True)
            try:
                values.append(float(text))
            except ValueError:
                values.append(None)  # "FEW" / "NA" placeholder -- not an error
        return values
    return []  # row not present at all -- site doesn't monitor this parameter


def _range_check(frame: pd.DataFrame) -> None:
    """
    Raise `ValueError` naming the column, the offending value, and both
    bounds when any non-null value in `frame` falls outside
    `units_def.PIPELINE_SCHEMA`'s declared range for that column.

    Mirrors `asos_provider._range_check` exactly, widened to include
    `relative_humidity` alongside `air_temp`, `wind_speed` and
    `wind_direction`. This is the phase's V5 input-validation control: it
    is the one gate that catches a units regression, since a provider
    value left in its native units is otherwise an ordinary-looking,
    in-range number.
    """
    for column in ("air_temp", "wind_speed", "wind_direction", "relative_humidity"):
        if column not in frame.columns:
            continue
        lo, hi = units_def.PIPELINE_SCHEMA[column]["range"]
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        out_of_range = values[(values < lo) | (values > hi)]
        if not out_of_range.empty:
            bad_value = out_of_range.iloc[0]
            raise ValueError(
                f"tceq_provider: converted value {bad_value!r} for column "
                f"{column!r} is outside PIPELINE_SCHEMA's range "
                f"[{lo}, {hi}] -- check for a native-unit value that was "
                "never converted."
            )


def _to_utc_timestamp(value: str) -> pd.Timestamp:
    """
    Coerce an ISO-8601 timestamp or a bare-date string into a tz-aware UTC
    `pd.Timestamp`, matching `nsrdb_provider._to_utc_timestamp`'s coercion.

    Raises:
        ValueError: prefixed "tceq_provider:", naming the offending value,
            when it cannot be parsed by `pd.Timestamp`.
    """
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"tceq_provider: cannot parse date {value!r}: {exc}") from exc

    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    return ts


def _window_bounds(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    Resolve a caller's [start, end] window to tz-aware UTC timestamps,
    mirroring `nsrdb_provider._window_bounds`'s coercion exactly: a bare-date
    `end` (containing neither "T" nor ":") is advanced to the last
    microsecond of that day, so a single-day window returns a full day's
    rows rather than the single midnight instant a literal reading would
    select. `start` is never widened this way.

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
            f"tceq_provider: resolved end {end_ts} precedes resolved start "
            f"{start_ts} (from start={start!r}, end={end!r})"
        )

    return start_ts, end_ts


def _days_spanned(start_ts: pd.Timestamp, end_ts: pd.Timestamp, offset_hours: int) -> list:
    """
    Return the ascending list of calendar dates (`datetime.date`) that
    [start_ts, end_ts] spans, keyed to the LOCAL calendar the report is
    actually organized by rather than to UTC.

    A window is expressed in UTC but a `daily_summary.pl` report is a local
    calendar day -- shifting each bound by `offset_hours` before taking the
    date component is what makes a window starting at, e.g., 00:30Z include
    the local day that actually contains its first hours, rather than
    silently starting one local day late.

    Args:
        offset_hours: The requesting site's fixed UTC offset (e.g. -6),
            passed in rather than looked up from the module constant, so
            this function stays a pure date computation independent of
            which site is asking.
    """
    local_start = (start_ts + pd.Timedelta(hours=offset_hours)).normalize()
    local_end = (end_ts + pd.Timedelta(hours=offset_hours)).normalize()

    days = []
    current = local_start
    while current <= local_end:
        days.append(current.date())
        current = current + pd.Timedelta(days=1)
    return days


def fetch_tceq(cams_id: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch TCEQ CAMS wind/temperature/RH observations for `cams_id` over an
    arbitrary [start, end] window, up to `TCEQ_MAX_DAYS_PER_FETCH` calendar
    days.

    Because `daily_summary.pl` reports exactly one calendar day per request
    (D-09), this issues one request per LOCAL calendar day the window spans
    (`_days_spanned`), each with its own `user_month`/`user_day`/`user_year`
    values, concatenates the per-day frames, restricts the result back to
    [start, end], sorts, and de-duplicates by timestamp (first wins) --
    mirroring `nsrdb_provider.fetch_nsrdb`'s per-period-loop-then-concat
    shape exactly, adapted from per-year to per-calendar-day.

    Args:
        cams_id: A `config.TCEQ_STATIONS` value (e.g. "83" for Corpus
            Christi).
        start, end: ISO-8601 or bare-date strings. A bare-date `end` covers
            that whole calendar day (`_window_bounds`).

    Returns:
        A DataFrame with exactly the columns ["datetime_utc", "air_temp",
        "wind_speed", "wind_direction", "relative_humidity"], in
        PIPELINE_SCHEMA units (degC, m/s, deg, % respectively).
        `datetime_utc` is tz-aware UTC, built by subtracting
        `TCEQ_FIXED_UTC_OFFSET_HOURS[cams_id]` from each reported
        local-standard-time hour -- never a DST-aware conversion. Sorted
        ascending, de-duplicated by timestamp (first wins, via a stable
        sort so "first" is deterministic), and restricted to [start, end]
        inclusive. The same window fetched twice returns a byte-identical
        frame.

    Raises:
        ValueError: if `cams_id` is absent from
            `TCEQ_FIXED_UTC_OFFSET_HOURS` (raised before any request); if a
            window argument cannot be parsed (`_window_bounds`); if the
            resolved window spans more than `TCEQ_MAX_DAYS_PER_FETCH`
            calendar days (raised before any request -- see
            `TCEQ_MAX_DAYS_PER_FETCH`); if any fetched day's response is
            not a genuine site-specific report (`_validate_response`); if
            any fetched day's report is missing a required row entirely
            for `Wind Speed`, `Wind Direction`, or `Outdoor Temperature`
            (`Relative Humidity`'s absence is never a raise -- it becomes
            a null column instead, D-04); if a matched row is truncated
            relative to the header's hour count (`_extract_row_values`);
            if the resolved window selects zero rows across every fetched
            day (an empty frame a caller could mistake for a quiet weather
            day, D-06); or if a converted value falls outside
            `units_def.PIPELINE_SCHEMA`'s declared range for its column (a
            units regression -- see `_range_check`).
        requests.HTTPError: propagated unchanged from `_fetch_one_day`.
    """
    if cams_id not in TCEQ_FIXED_UTC_OFFSET_HOURS:
        raise ValueError(
            f"tceq_provider: no fixed UTC offset registered for CAMS ID "
            f"{cams_id!r} -- known CAMS IDs are "
            f"{sorted(TCEQ_FIXED_UTC_OFFSET_HOURS)}. Add it to "
            "TCEQ_FIXED_UTC_OFFSET_HOURS before requesting this site (an "
            "unknown site's true offset is not knowable from a default, "
            "and a wrong offset is silent)."
        )
    offset_hours = TCEQ_FIXED_UTC_OFFSET_HOURS[cams_id]

    start_ts, end_ts = _window_bounds(start, end)
    days = _days_spanned(start_ts, end_ts, offset_hours)

    if len(days) > TCEQ_MAX_DAYS_PER_FETCH:
        raise ValueError(
            f"tceq_provider: window {start_ts}..{end_ts} spans {len(days)} "
            f"calendar days, exceeding TCEQ_MAX_DAYS_PER_FETCH="
            f"{TCEQ_MAX_DAYS_PER_FETCH}. No rate limit is documented for "
            "daily_summary.pl, but this project does not service a long "
            "historical backfill by issuing hundreds of rapid sequential "
            "requests against a free, unauthenticated, public government "
            "CGI endpoint -- use Open-Meteo (WX-04) for bulk historical "
            "backfill instead."
        )

    frames = []
    for day in days:
        report_day = pd.Timestamp(day, tz="UTC")
        html = _fetch_one_day(cams_id, report_day.year, report_day.month, report_day.day)
        data_table = _validate_response(html, cams_id)
        hour_labels = _hour_labels(data_table)
        hour_count = len(hour_labels)

        if hour_count == 0:
            # A single fetched day that yields no hour labels at all
            # contributes no rows and is not itself a raise condition --
            # the window-level empty check below is what catches a fetch
            # that produced nothing overall.
            log.info(
                "tceq_provider: CAMS %s report for %s carried no hour "
                "labels -- contributing 0 rows",
                cams_id,
                report_day.date(),
            )
            continue

        per_column_values: dict[str, list] = {}
        missing_required_labels = []
        for label, column in TARGET_LABELS.items():
            values = _extract_row_values(data_table, label, hour_count)
            if not values:
                if column == "relative_humidity":
                    per_column_values[column] = [None] * hour_count
                else:
                    missing_required_labels.append(label)
            else:
                per_column_values[column] = values

        if missing_required_labels:
            raise ValueError(
                f"tceq_provider: CAMS {cams_id!r} report for "
                f"{report_day.date()} is missing required row(s) "
                f"{missing_required_labels!r} -- Wind Speed, Wind "
                "Direction, and Outdoor Temperature were confirmed present "
                "at every TCEQ site this project checked, so their "
                "absence signals a broken or unexpectedly-shaped report "
                "rather than an ordinary site limitation. Relative "
                "Humidity is deliberately exempt from this check (D-04)."
            )

        records = []
        for i, hour_label in enumerate(hour_labels):
            hour = int(hour_label[:2])
            # `report_day` is UTC-labeled but its wall-clock value
            # represents the site's LOCAL standard time midnight -- adding
            # `hour` still in that same "local, mislabeled UTC" frame,
            # then subtracting the fixed offset converts to real UTC
            # (never a DST-aware lookup).
            local_as_utc = report_day + pd.Timedelta(hours=hour)
            datetime_utc = local_as_utc - pd.Timedelta(hours=offset_hours)

            raw_temp = per_column_values["air_temp"][i]
            raw_wind = per_column_values["wind_speed"][i]

            records.append(
                {
                    "datetime_utc": datetime_utc,
                    "air_temp": Q(raw_temp, "degF").to("degC").value if raw_temp is not None else None,
                    "wind_speed": Q(raw_wind, "mph").to("m/s").value if raw_wind is not None else None,
                    "wind_direction": per_column_values["wind_direction"][i],
                    "relative_humidity": per_column_values["relative_humidity"][i],
                }
            )

        frames.append(pd.DataFrame(records, columns=_RETURN_COLUMNS))

    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=_RETURN_COLUMNS)
    combined["datetime_utc"] = pd.to_datetime(combined["datetime_utc"], utc=True)

    combined = combined[(combined["datetime_utc"] >= start_ts) & (combined["datetime_utc"] <= end_ts)]
    # A stable sort is required, not merely convenient: it is what makes
    # "duplicates dropped keep='first'" deterministically mean "the
    # earlier-fetched day's value wins" rather than an arbitrary tie-break.
    combined = combined.sort_values("datetime_utc", kind="stable")
    combined = combined.drop_duplicates(subset="datetime_utc", keep="first")
    combined = combined.reset_index(drop=True)

    if combined.empty:
        raise ValueError(
            f"tceq_provider: window {start_ts}..{end_ts} for CAMS "
            f"{cams_id!r} selected zero rows across {len(days)} day(s) "
            "fetched -- raising rather than returning an empty frame a "
            "caller could mistake for a quiet weather day (D-06)."
        )

    _range_check(combined)

    return combined[_RETURN_COLUMNS]
