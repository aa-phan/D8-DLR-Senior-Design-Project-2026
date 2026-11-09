#!/usr/bin/env python3
"""Read the current dynamic line rating of every city, one city's history, and the day-ahead
forecast, over REST.

What it prints
  1. One line per city from the view `latest_rating` (the current row of each city): the rating
     in amperes and megawatts, status, how old the row is, whether it is stale, and whether the
     values are provisional.
  2. For one city (--city, default AUSTIN), how many hourly rows the table `city_rating` holds
     between --start and --end (default: the last seven days), read in pages of 1000 rows, with
     the first and last `valid_time`.
  3. The day-ahead forecast (Phase 8): the upcoming targets of every city from the view
     `day_ahead_upcoming` (one value per city at each of the 00, 06, 12 and 18 UTC targets, with
     the band, the lead in minutes and where the band came from), then one status line per city
     from the view `day_ahead_status` (how many targets are upcoming, whether the feed is late
     and which targets are missing). These values carry the label
         day-ahead-24h; engineering-selection; not-validated
     They are NOT the live rating, and they never set or check it.

Requirements
  * Python 3.7 or newer, standard library only. Nothing to install.
  * Two environment variables. The Data Science owner gives you both values directly; they are
    never written into this file or into the repository.
        SUPABASE_URL              the project URL
        SUPABASE_PUBLISHABLE_KEY  the publishable key (safe to use from a client, read-only)
    macOS and Linux:   export SUPABASE_URL="<value from the DS owner>"
                       export SUPABASE_PUBLISHABLE_KEY="<value from the DS owner>"
    Windows (cmd):     set SUPABASE_URL=<value from the DS owner>
                       set SUPABASE_PUBLISHABLE_KEY=<value from the DS owner>

Usage
    python read_ratings.py
    python read_ratings.py --city MIDLAND --start 2026-10-25T00:00:00Z --end 2026-11-01T00:00:00Z

The script only reads (HTTP GET), writes no file and keeps no state, so it is safe to run
repeatedly, at the same time as other copies of itself, or to interrupt. The key travels in the
`apikey` header only. TLS certificates are verified with Python's defaults.

Exit status: 0 success (a late day-ahead feed is printed, not an error); 1 the service answered
with an error, could not be reached, or did not return all four cities (also for the day-ahead
status); 2 a missing environment variable or an unusable argument.

All rating values are PROVISIONAL (see docs/integration/rest-api.md). A row whose status is
"fallback" is a valid published rating (the static value), not an error.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

CITIES = ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")
PAGE = 1000  # the service returns at most 1000 rows per request
ENV_URL = "SUPABASE_URL"
ENV_KEY = "SUPABASE_PUBLISHABLE_KEY"
LATEST_SELECT = ("city,valid_time,rating_amps,rating_mw,status,fallback_gates,"
                 "age_minutes,is_stale,is_provisional")
DAY_AHEAD_UPCOMING_SELECT = ("city,valid_time,issued_at,lead_minutes,forecast_amps,forecast_ci_lower_amps,"
                             "forecast_ci_upper_amps,band_source,band_n,label")
DAY_AHEAD_STATUS_SELECT = "city,next_target_time,upcoming_count,newest_issued_at,missing_targets,is_late"
DAY_AHEAD_LABEL = "day-ahead-24h; engineering-selection; not-validated"
STAMP = "%Y-%m-%dT%H:%M:%SZ"

_TS = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}(?::?\d{2})?)?$")


def parse_ts(s):
    """PostgREST timestamp -> timezone-aware datetime.

    datetime.fromisoformat() before Python 3.11 rejects a trailing 'Z' and any fraction that is
    not exactly 3 or 6 digits, and PostgREST sends both forms, so parse by hand. A timestamp with
    no offset is read as UTC. Raises ValueError for anything else.
    """
    text = str(s).strip()
    match = _TS.match(text)
    if not match:
        raise ValueError("unrecognised timestamp: %r" % text)
    day, clock, fraction, offset = match.groups()
    offset = offset or "+00:00"
    if offset == "Z":
        offset = "+00:00"
    if re.match(r"^[+-]\d{2}$", offset):
        offset += ":00"
    if re.match(r"^[+-]\d{4}$", offset):
        offset = offset[:3] + ":" + offset[3:]
    return datetime.fromisoformat("%sT%s.%s%s" % (day, clock, ((fraction or "") + "000000")[:6], offset))


def get(path, params=None):
    """GET <SUPABASE_URL>/rest/v1/<path>?<params> and return the decoded JSON.

    `params` is a list of (name, value) pairs, so one column can be filtered twice.
    Raises RuntimeError with a short message (never the key or the URL) on any failure.
    """
    base = os.environ[ENV_URL].strip().rstrip("/")
    query = ("?" + urllib.parse.urlencode(params, safe=",.()*:")) if params else ""
    request = urllib.request.Request(
        base + "/rest/v1/" + path + query,
        headers={"apikey": os.environ[ENV_KEY].strip(), "Accept": "application/json",
                 "User-Agent": "dlr-psse-client/1.0"})
    failure = None
    body = None
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        failure = "HTTP %s from %s" % (error.code, path)
    except urllib.error.URLError as error:
        failure = "could not reach the service: %s" % (error.reason,)
    except ValueError:
        failure = "%s is not a usable URL" % ENV_URL
    if failure is not None:
        raise RuntimeError(failure)  # raised outside the except block: no chained message
    try:
        return json.loads(body)
    except ValueError:
        raise RuntimeError("unexpected answer from %s (not JSON)" % path)


def get_all(path, params, order):
    """Every matching row, fetched in pages.

    `order` must be unique per row (valid_time.asc is unique within one city), so no row repeats
    or is skipped between pages. The offset advances by the rows actually received and the loop
    stops on an EMPTY page, so it still works if the service cap is ever lower than PAGE.
    """
    rows = []
    offset = 0
    while True:
        page = get(path, list(params) + [("order", order), ("limit", str(PAGE)), ("offset", str(offset))])
        if not page:
            return rows
        rows.extend(page)
        offset += len(page)


def default_window(now=None):
    """(start, end) as UTC strings: seven days before the current UTC hour, and one hour after it."""
    now = now or datetime.now(timezone.utc)
    hour = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    return (hour - timedelta(days=7)).strftime(stamp), (hour + timedelta(hours=1)).strftime(stamp)


def _timestamp_argument(text):
    try:
        parse_ts(text)
    except ValueError:
        raise argparse.ArgumentTypeError("not an ISO timestamp such as 2026-10-25T00:00:00Z: %r" % text)
    return text


def _number(value, spec):
    return (spec % value) if isinstance(value, (int, float)) else "n/a"


def _print_latest(rows):
    for row in rows:
        gates = ",".join(row.get("fallback_gates") or []) or "-"
        print("%-15s %7s A %8s MW  %-8s age %4s min  stale=%s  provisional=%s  gates=%s" % (
            row.get("city"), _number(row.get("rating_amps"), "%.1f"), _number(row.get("rating_mw"), "%.1f"),
            row.get("status"), row.get("age_minutes"), row.get("is_stale"), row.get("is_provisional"), gates))


def _utc(value):
    """A PostgREST timestamp as UTC text ending in Z, or the text unchanged if it cannot be read."""
    try:
        return parse_ts(value).astimezone(timezone.utc).strftime(STAMP)
    except ValueError:
        return str(value)


def _city_order(row):
    return CITIES.index(row["city"]) if row.get("city") in CITIES else len(CITIES)


def _print_day_ahead(upcoming, status):
    """Part 3 output. Every line is indented, so none can be read as a Part 1 city line."""
    upcoming = sorted(upcoming, key=lambda r: (_city_order(r), _utc(r.get("valid_time"))))
    status = sorted(status, key=_city_order)
    labels = []
    for row in upcoming:
        if row.get("label") not in labels:
            labels.append(row.get("label"))
    print("")
    print("Day-ahead forecast: upcoming targets (view day_ahead_upcoming)")
    print("label: %s" % (" | ".join(str(label) for label in labels) or DAY_AHEAD_LABEL))
    print("this is not the live rating: it never sets or checks it, and it is not validated")
    if not upcoming:
        print("no upcoming day-ahead values")
    for row in upcoming:
        print("  %-15s %s  %7s A  band %s to %s A  lead %s min  %s n=%s" % (
            row.get("city"), _utc(row.get("valid_time")), _number(row.get("forecast_amps"), "%.1f"),
            _number(row.get("forecast_ci_lower_amps"), "%.1f"), _number(row.get("forecast_ci_upper_amps"), "%.1f"),
            row.get("lead_minutes"), row.get("band_source"), row.get("band_n")))
    print("")
    print("Day-ahead status per city (view day_ahead_status)")
    late = []
    for row in status:
        missing = [_utc(t) for t in (row.get("missing_targets") or [])]
        print("  %-15s upcoming %s  late=%s  missing %s" % (
            row.get("city"), row.get("upcoming_count"), row.get("is_late"), ", ".join(missing) or "-"))
        if row.get("is_late"):
            late.append("%s (missing %s)" % (row.get("city"), ", ".join(missing) or "-"))
    if late:
        print("day-ahead feed is LATE for %s" % "; ".join(late))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read DLR ratings from the Supabase REST interface.")
    parser.add_argument("--city", choices=CITIES, default="AUSTIN", help="city for the history part")
    parser.add_argument("--start", type=_timestamp_argument, help="first valid_time (inclusive), ISO")
    parser.add_argument("--end", type=_timestamp_argument, help="end of the range (exclusive), ISO")
    args = parser.parse_args(argv)
    for name in (ENV_URL, ENV_KEY):
        if not os.environ.get(name, "").strip():
            print("%s is not set (the Data Science owner gives you the value)" % name, file=sys.stderr)
            return 2
    default_start, default_end = default_window()
    start = args.start or default_start
    end = args.end or default_end

    try:
        # Part 1: the current row of every city.
        latest = get("latest_rating", [("select", LATEST_SELECT), ("order", "city")])
        latest = sorted(latest, key=lambda r: CITIES.index(r["city"]) if r.get("city") in CITIES else len(CITIES))
        print("Current rating per city (view latest_rating)")
        _print_latest(latest)
        if any(row.get("is_provisional") for row in latest):
            print("values are PROVISIONAL (see rating_basis)")
        missing = [city for city in CITIES if city not in [row.get("city") for row in latest]]
        if missing:
            print("latest_rating is missing: %s" % ", ".join(missing), file=sys.stderr)
            return 1

        # Part 2: one city over a date range, past the 1000-row cap.
        rows = get_all("city_rating", [
            ("city", "eq." + args.city),
            ("select", "valid_time,rating_amps"),
            ("valid_time", "gte." + start),
            ("valid_time", "lt." + end),
        ], "valid_time.asc")
        print("")
        print("%s rows from %s to %s: %d" % (args.city, start, end, len(rows)))
        if rows:
            stamp = "%Y-%m-%dT%H:%M:%SZ"
            print("first valid_time: %s" % parse_ts(rows[0]["valid_time"]).astimezone(timezone.utc).strftime(stamp))
            print("last valid_time:  %s" % parse_ts(rows[-1]["valid_time"]).astimezone(timezone.utc).strftime(stamp))

        # Part 3: the day-ahead targets and the per-city status (not the live rating).
        upcoming = get("day_ahead_upcoming", [("select", DAY_AHEAD_UPCOMING_SELECT), ("order", "city,valid_time")])
        status = get("day_ahead_status", [("select", DAY_AHEAD_STATUS_SELECT), ("order", "city")])
        _print_day_ahead(upcoming, status)
        absent = [city for city in CITIES if city not in [row.get("city") for row in status]]
        if absent:
            print("day_ahead_status is missing: %s" % ", ".join(absent), file=sys.stderr)
            return 1
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
