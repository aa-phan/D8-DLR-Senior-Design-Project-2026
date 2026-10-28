"""
Rating input of the PSS/E job (pss-e-integration Phase 1: IN-01, D-02, D-06).

`fetch_latest_rating` reads public.latest_rating once over Supabase REST with the
publishable key (apikey header only). `select_ratings` then decides, per city, between
the newest city_rating row and the city's static rating, and records why. Every doubt
maps to static: a missing, malformed, stale, provisional or unreadable row never lets a
non-static value reach a study (no last-known-good, interpolated or forecast value).

The static amps and subconductor counts always come from psse_job.constants, never from
the row. The job reads rating_amps (per conductor), never rating_mw (D-06). Standard
library only, Python 3.7 syntax, no import of backend/config.py (D-05).
"""

import base64
import binascii
import collections
import datetime
import http.client
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from psse_job import constants

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

_TS_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
    r"(?:\.(\d+))?"
    r"(Z|[+-]\d{2}(?::?\d{2})?)",
    re.ASCII,
)

_NOT_A_LIST = "latest_rating read failed: response is not a JSON list"


class ReadFailed(RuntimeError):
    """The ratings read could not be completed; the message is always redacted."""


def parse_ts(value):
    """
    Parse `YYYY-MM-DD` + `T` or space + `HH:MM:SS`, an optional fraction of any length,
    and a REQUIRED offset (`Z`, `+HH`, `+HHMM`, `+HH:MM` or the negative forms). Returns an
    aware datetime in UTC. Raises ValueError for a naive or malformed value and for a
    non-str. Built from a regex and `datetime(...)`, never `fromisoformat`, which older
    Pythons reject for `Z` and for odd fractions.
    """
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    match = _TS_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError("timestamp is not an ISO 8601 value with a UTC offset")
    year, month, day, hour, minute, second, fraction, offset = match.groups()
    micro = int((fraction or "0")[:6].ljust(6, "0"))
    if offset == "Z":
        delta = datetime.timedelta(0)
    else:
        sign = -1 if offset[0] == "-" else 1
        digits = offset[1:].replace(":", "")
        off_hours = int(digits[:2])
        off_minutes = int(digits[2:] or "0")
        if off_minutes > 59:
            raise ValueError("timestamp offset minutes out of range")
        delta = sign * datetime.timedelta(hours=off_hours, minutes=off_minutes)
    moment = datetime.datetime(
        int(year), int(month), int(day), int(hour), int(minute), int(second), micro,
        tzinfo=datetime.timezone(delta),
    )
    return moment.astimezone(datetime.timezone.utc)


def _is_service_role_jwt(key):
    """True when `key` is JWT-shaped and its payload names the service_role role."""
    parts = key.split(".")
    if len(parts) != 3:
        return False
    try:
        segment = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(segment.encode("ascii")).decode("utf-8"))
    except (ValueError, binascii.Error, UnicodeError):
        return False
    return isinstance(payload, dict) and payload.get("role") == "service_role"


def _scrub(text, removals, limit):
    """Remove every non-empty string in `removals` (longest first), then cut to `limit`."""
    for item in sorted({r for r in removals if r}, key=len, reverse=True):
        text = text.replace(item, "REDACTED")
    return text[:limit]


def fetch_latest_rating(env=None, opener=None, timeout=30):
    """
    GET the latest_rating view (the selected columns only, ordered by city) and return the
    decoded list of rows; choose() judges each row. Raises ReadFailed with a redacted
    message for anything that prevents a complete read. No request is made when the key
    is a secret key or a service_role JWT, or when the URL would send the key over plain
    HTTP to a non-loopback host.
    """
    env = os.environ if env is None else env
    base = env.get(constants.ENV_SUPABASE_URL)
    key = env.get(constants.ENV_PUBLISHABLE_KEY)
    if base is None or not str(base).strip():
        raise ReadFailed(constants.ENV_SUPABASE_URL + " is not set")
    if key is None or not str(key).strip():
        raise ReadFailed(constants.ENV_PUBLISHABLE_KEY + " is not set")
    base = str(base).strip().rstrip("/")
    key = str(key).strip()

    if key.startswith(constants.SECRET_KEY_PREFIX) or _is_service_role_jwt(key):
        raise ReadFailed("refusing to read latest_rating with a secret key; use the publishable key")
    parts = None
    host = None
    try:
        parts = urllib.parse.urlsplit(base)
        host = parts.hostname
    except ValueError:
        parts = None
    scheme = parts.scheme.lower() if (parts is not None and host) else ""
    if scheme != "https" and not (scheme == "http" and host in _LOOPBACK_HOSTS):
        raise ReadFailed("the Supabase URL must use https (plain http only for a loopback host)")

    query = urllib.parse.urlencode(
        [("select", ",".join(constants.LATEST_RATING_SELECT)), ("order", "city.asc")], safe=",."
    )
    url = base + "/rest/v1/" + constants.LATEST_RATING_VIEW + "?" + query
    request = urllib.request.Request(
        url,
        headers={"apikey": key, "Accept": "application/json", "User-Agent": constants.USER_AGENT},
    )
    opener = urllib.request.urlopen if opener is None else opener

    # Every ReadFailed is raised outside the except blocks, so no original exception (and
    # thus no part of its message) is chained.
    failure = None
    status = None
    raw = None
    try:
        response = opener(request, timeout=timeout)
        try:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            raw = response.read()
        finally:
            closer = getattr(response, "close", None)
            if closer is not None:
                closer()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = None
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as exc:
        failure = "latest_rating read failed: %s: %s" % (
            type(exc).__name__,
            _scrub(str(exc), [base, parts.netloc, host, key], constants.LOG_MAX_CHARS),
        )
    if failure is not None:
        raise ReadFailed(failure)
    if status != 200:
        raise ReadFailed("latest_rating read failed: HTTP %s" % status)
    rows = None
    try:
        rows = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, AttributeError):
        rows = None
    if not isinstance(rows, list):
        raise ReadFailed(_NOT_A_LIST)
    return rows


RatingChoice = collections.namedtuple(
    "RatingChoice",
    [
        "city", "source", "fallback_reason", "amps_per_conductor", "subconductors_per_phase",
        "amps_circuit", "static_amps_per_conductor", "row_valid_time", "row_computed_at",
        "row_run_id", "row_status", "row_config_fingerprint", "age_minutes",
        "server_is_stale", "server_is_provisional",
    ],
)

Selection = collections.namedtuple("Selection", ["choices", "read_error", "ignored_rows"])


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _make_choice(city, source, reason, amps, row_info=None):
    """One RatingChoice. `row_info` is None, or a dict of the facts kept from the row read."""
    count = constants.SUBCONDUCTORS_PER_PHASE[city]
    info = row_info or {}
    return RatingChoice(
        city=city,
        source=source,
        fallback_reason=reason,
        amps_per_conductor=amps,
        subconductors_per_phase=count,
        amps_circuit=amps * count,
        static_amps_per_conductor=constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city],
        row_valid_time=info.get("valid_time"),
        row_computed_at=info.get("computed_at"),
        row_run_id=info.get("run_id"),
        row_status=info.get("status"),
        row_config_fingerprint=info.get("config_fingerprint"),
        age_minutes=info.get("age_minutes"),
        server_is_stale=info.get("is_stale"),
        server_is_provisional=info.get("is_provisional"),
    )


def _static(city, reason, row_info=None):
    return _make_choice(
        city, constants.SOURCE_STATIC, reason,
        constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city], row_info,
    )


def _text_or_none(value):
    return value if isinstance(value, str) else None


def choose(city, row, now):
    """
    Decide one city's rating. Pure; never raises for bad row content. Reason precedence:
    missing, invalid, stale, provisional. The static amps come from constants, never from
    the row. Only city, rating_amps, valid_time, computed_at, is_stale, is_provisional,
    run_id, status and config_fingerprint are read from the row.
    """
    if row is None:
        return _static(city, "missing")
    try:
        if not isinstance(row, dict) or row.get("city") != city:
            return _static(city, "invalid")
        amps_raw = row.get("rating_amps")
        if not _is_number(amps_raw):
            return _static(city, "invalid")
        amps = float(amps_raw)
        if not (math.isfinite(amps) and amps > 0):
            return _static(city, "invalid")
        valid = parse_ts(row.get("valid_time"))
        computed = parse_ts(row.get("computed_at"))
        server_stale = row.get("is_stale")
        server_provisional = row.get("is_provisional")
        if not isinstance(server_stale, bool) or not isinstance(server_provisional, bool):
            return _static(city, "invalid")
        if valid > now + datetime.timedelta(minutes=constants.FUTURE_TOLERANCE_MINUTES):
            return _static(city, "invalid")
        info = {
            "valid_time": valid,
            "computed_at": computed,
            "run_id": _text_or_none(row.get("run_id")),
            "status": _text_or_none(row.get("status")),
            "config_fingerprint": _text_or_none(row.get("config_fingerprint")),
            "is_stale": server_stale,
            "is_provisional": server_provisional,
        }
    except (ValueError, TypeError, OverflowError, ArithmeticError):
        return _static(city, "invalid")
    age = (now - valid).total_seconds() / 60.0
    info["age_minutes"] = age
    if server_stale or age > constants.STALE_AFTER_MINUTES:
        return _static(city, "stale", info)
    if server_provisional:
        return _static(city, "provisional", info)
    return _make_choice(city, constants.SOURCE_CITY_RATING, None, amps, info)


def select_ratings(fetch, now):
    """
    Call `fetch()` exactly once and choose a rating for each of the four cities, returned
    in the fixed order of constants.CITIES. A failed read (D-02) gives every city the
    static rating with reason read_failed and a redacted `read_error`; it never raises.
    Rows are matched to cities by exact, case-sensitive key; other rows are counted in
    `ignored_rows`; two rows for one city make that city invalid. `now` must be aware.
    """
    if not isinstance(now, datetime.datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    read_error = None
    rows = None
    try:
        rows = fetch()
    except ReadFailed as exc:
        read_error = str(exc)
    except Exception as exc:  # noqa: BLE001 - a failed read is a fallback, never a crash (D-02)
        read_error = type(exc).__name__
    if read_error is None and not isinstance(rows, list):
        read_error = _NOT_A_LIST
    if read_error is not None:
        choices = dict((city, _static(city, "read_failed")) for city in constants.CITIES)
        return Selection(choices, read_error, 0)

    grouped = dict((city, []) for city in constants.CITIES)
    ignored = 0
    for row in rows:
        city = row.get("city") if isinstance(row, dict) else None
        if isinstance(city, str) and city in grouped:
            grouped[city].append(row)
        else:
            ignored += 1
    choices = {}
    for city in constants.CITIES:
        found = grouped[city]
        if not found:
            choices[city] = choose(city, None, now)
        elif len(found) > 1:
            choices[city] = _static(city, "invalid")
        else:
            choices[city] = choose(city, found[0], now)
    return Selection(choices, None, ignored)
