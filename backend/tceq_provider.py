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


def fetch_tceq(cams_id: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch one calendar day of TCEQ CAMS wind/temperature/RH observations
    for `cams_id`.

    Args:
        cams_id: A `config.TCEQ_STATIONS` value (e.g. "83" for Corpus
            Christi).
        start, end: ISO-8601 timestamp strings that must resolve to the
            SAME calendar day in UTC -- this tracer proves the single-day
            path only; a window spanning more than one calendar day
            raises (Plan 09-02 replaces this with real multi-day
            decomposition, D-09).

    Returns:
        A DataFrame with exactly the columns ["datetime_utc", "air_temp",
        "wind_speed", "wind_direction", "relative_humidity"], in
        PIPELINE_SCHEMA units (degC, m/s, deg, % respectively).
        `datetime_utc` is tz-aware UTC, built by subtracting
        `TCEQ_FIXED_UTC_OFFSET_HOURS[cams_id]` from each reported
        local-standard-time hour -- never a DST-aware conversion. Sorted
        ascending, de-duplicated by timestamp (first wins), and
        restricted to [start, end] inclusive.

    Raises:
        ValueError: if `cams_id` is absent from
            `TCEQ_FIXED_UTC_OFFSET_HOURS`; if a date argument cannot be
            parsed; if `start`/`end` resolve to different calendar days;
            if the response is not a genuine site-specific report
            (`_validate_response`); if the report is missing a required
            row entirely for `wind_speed`, `wind_direction`, or
            `air_temp` (relative_humidity's absence is never a raise --
            it becomes a null column instead, D-04); if a matched row is
            truncated relative to the header's hour count
            (`_extract_row_values`); or if a converted value falls
            outside `units_def.PIPELINE_SCHEMA`'s declared range for its
            column (a units regression -- see `_range_check`).
        requests.HTTPError: propagated unchanged from `_fetch_one_day`.
    """
    if cams_id not in TCEQ_FIXED_UTC_OFFSET_HOURS:
        raise ValueError(
            f"tceq_provider: no fixed UTC offset registered for CAMS ID "
            f"{cams_id!r} -- add it to TCEQ_FIXED_UTC_OFFSET_HOURS before "
            "requesting this site (an unknown site's true offset is not "
            "knowable from a default, and a wrong offset is silent)."
        )
    offset_hours = TCEQ_FIXED_UTC_OFFSET_HOURS[cams_id]

    try:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"tceq_provider: cannot parse date {start!r}/{end!r}: {exc}") from exc

    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")
    end_ts = end_ts.tz_localize("UTC") if end_ts.tzinfo is None else end_ts.tz_convert("UTC")

    if start_ts.normalize() != end_ts.normalize():
        raise ValueError(
            f"tceq_provider: window {start!r}..{end!r} spans more than "
            "one calendar day -- multi-day windows arrive in Plan 09-02."
        )

    report_day = start_ts.normalize()

    html = _fetch_one_day(cams_id, report_day.year, report_day.month, report_day.day)
    data_table = _validate_response(html, cams_id)
    hour_labels = _hour_labels(data_table)
    hour_count = len(hour_labels)

    per_column_values: dict[str, list] = {}
    missing_required = []
    for label, column in TARGET_LABELS.items():
        values = _extract_row_values(data_table, label, hour_count)
        if not values:
            if column == "relative_humidity":
                per_column_values[column] = [None] * hour_count
            else:
                missing_required.append(column)
        else:
            per_column_values[column] = values

    if missing_required:
        raise ValueError(
            f"tceq_provider: CAMS {cams_id!r} report for "
            f"{report_day.date()} is missing required row(s) for "
            f"column(s) {missing_required} -- the site does not monitor "
            "this parameter at all."
        )

    records = []
    for i, hour_label in enumerate(hour_labels):
        hour = int(hour_label[:2])
        # `report_day` is UTC-labeled but its wall-clock value represents
        # the site's LOCAL standard time midnight -- adding `hour` still
        # in that same "local, mislabeled UTC" frame, then subtracting the
        # fixed offset converts to real UTC (never a DST-aware lookup).
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

    frame = pd.DataFrame(records, columns=_RETURN_COLUMNS)
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], utc=True)

    frame = frame[(frame["datetime_utc"] >= start_ts) & (frame["datetime_utc"] <= end_ts)]
    frame = frame.sort_values("datetime_utc")
    frame = frame.drop_duplicates(subset="datetime_utc", keep="first")
    frame = frame.reset_index(drop=True)

    _range_check(frame)

    return frame[_RETURN_COLUMNS]
