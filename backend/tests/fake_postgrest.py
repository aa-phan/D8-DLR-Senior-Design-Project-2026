"""
In-process fake of the PostgREST surface the Phase 6 consumers see (not a test module: the
file name does not match the collected patterns). Used by e2e_readonly_test.py and reused by
the example, soak and trace tests (06-06, 06-08).

`FakePostgrest` runs a `http.server.ThreadingHTTPServer` on 127.0.0.1 (port 0) in a daemon
thread. It serves

  GET/HEAD  latest_rating     the newest row per city plus the three computed columns,
                              keys in latest_rating_contract.LATEST_COLUMNS order
  GET/HEAD  city_rating       select, eq./neq./gt./gte./lt./lte./in. filters (repeated filters
                              are ANDed), order, limit/offset, the Range header, Prefer
                              count=exact -> Content-Range, and the `max_rows` cap
  GET/HEAD  day_ahead_upcoming, day_ahead_status
                              the Phase 8 views (08-12): defaults built from the fake's clock by
                              `make_day_ahead_view_rows`, or the lists given as
                              `day_ahead_upcoming=` / `day_ahead_status=`; same select, filter,
                              order, limit/offset, Range and `max_rows` handling as city_rating;
                              writes answer 401 42501 permission denied
  GET       rpc/assert_fresh  200 JSON, or 503 with code PT503 (`fresh=False`)
  pipeline_run                401 42501 permission denied
  any other Accept-Profile    406 PGRST106; unknown relation 404 PGRST205
  a missing or wrong apikey   401 (unless `require_key=False`)

Write behaviour on city_rating and latest_rating follows `write_mode`:

  revoked   no write grant: INSERT/PATCH/DELETE on the table answer 401 42501 "permission
            denied for table city_rating" (what a correct project does)
  rls_only  a grant is still present and only RLS blocks: INSERT 401 42501 "new row violates
            row-level security policy", PATCH and DELETE 200 with an empty list (the silent
            case that fooled status-only tests, 06-RESEARCH Pitfall 1)
  open      writes are applied to the stored rows (a misconfigured project)

Writes to the DISTINCT ON view answer 500 55000 "not automatically updatable" in every mode.
`table_write_response` / `view_write_response` force one (status, body) for those writes, and
`before_request(fake, record)` runs ahead of each request so a test can change `fake.rows`
between two calls (a live upsert, a backfill, an edit). Every request is appended to
`fake.requests` as {method, path, query (pairs), headers (lower-case), body}.
"""

import json
import re
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

import config
import day_ahead_contract
import latest_rating_contract as contract
import supabase_rest

DEFAULT_KEY = "sb_" + "publishable_" + "FakeKey0123456789abcdef"
_TS_COLUMNS = frozenset({"valid_time", "observation_time", "computed_at", "first_written_at",
                         "issued_at", "forecast_run_init_time", "anchor_observation_time",
                         "checked_at", "next_target_time", "newest_issued_at"})
_DAY_AHEAD_RELATIONS = ("day_ahead_upcoming", "day_ahead_status")
_RESERVED = frozenset({"select", "order", "limit", "offset", "on_conflict", "columns"})
_VIEW_NOT_UPDATABLE = {
    "code": "55000",
    "details": "Views containing DISTINCT are not automatically updatable.",
    "hint": None,
    "message": "cannot change view \"latest_rating\"",
}


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def make_rating_rows(slots, cities=config.LOCATIONS, newest=None, **overrides):
    """
    Complete city_rating rows (the 31 published columns plus a few diagnostics) for every city and
    every hourly slot. `slots` is a count (newest slot, then one hour older each) or an iterable of
    aware datetimes. `newest` defaults to the current UTC hour. `overrides` replace a column on every
    row. Labels are the real config strings; since the Phase 7 go they lack the word, so is_provisional is false unless overridden.
    """
    if newest is None:
        newest = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if isinstance(slots, int):
        slot_times = [newest - timedelta(hours=i) for i in range(slots)]
    else:
        slot_times = list(slots)
    rows = []
    for city_index, city in enumerate(cities):
        for slot_index, slot in enumerate(slot_times):
            amps = 900.0 + 25.0 * city_index + 1.0 * slot_index
            row = {
                "city": city,
                "valid_time": _iso(slot),
                "observation_time": _iso(slot - timedelta(minutes=5)),
                "rating_amps": amps,
                "rating_mw": round(amps * 0.568, 3),
                "static_rating_amps": 800.0 + 10.0 * city_index,
                "static_rating_mw": round((800.0 + 10.0 * city_index) * 0.568, 3),
                "line_voltage_kv": 345.0,
                "power_factor": 0.95,
                "status": "ok",
                "fallback": False,
                "fallback_gates": [],
                "alerts": [],
                "exhausted": False,
                "forecast_method": "ml",
                "forecast_status": "ok",
                "forecast_amps": amps + 20.0,
                "forecast_ci_lower_amps": amps - 40.0,
                "forecast_ci_upper_amps": amps + 80.0,
                "forecast_horizon_min": 60.0,
                "detector_signal": "normal",
                "rating_basis": config.RATING_BASIS,
                "config_version": config.RATING_CONFIG_VERSION,
                "origin": "live",
                "run_id": "fake-run-%s" % slot.strftime("%Y%m%d%H"),
                "pipeline_version": "fake0001",
                "computed_at": _iso(slot + timedelta(minutes=6)),
                "config_fingerprint": "ab" * 32,
                "forecast_model_sha256": "cd" * 32,
                "anomaly_model_sha256": "ef" * 32,
                "solar_source": "nsrdb",
                # diagnostics that only city_rating exposes
                "station_id": "KFAKE",
                "run_attempt": 1,
                "schema_version": 1,
                "first_written_at": _iso(slot + timedelta(minutes=6)),
            }
            row.update(overrides)
            rows.append(row)
    return rows


def make_day_ahead_view_rows(now, cities=config.LOCATIONS, per_city=3):
    """
    (upcoming, status) as the Phase 8 views show them at `now`, built from day_ahead_contract.

    `upcoming` has, per city, the next `per_city` 6-hour UTC grid targets strictly after `now`, every
    UPCOMING_COLUMNS key filled with plausible values (ISO +00:00 timestamps; the hash columns are
    64 lower-case hex characters built from repeated digits, so the secret scan cannot match them).
    `status` has one not-late row per city with the STATUS_COLUMNS keys and no missing targets.
    """
    now = now.astimezone(timezone.utc)
    grid = day_ahead_contract.GRID_HOURS
    first = now.replace(minute=0, second=0, microsecond=0)
    first = first - timedelta(hours=first.hour % grid) + timedelta(hours=grid)
    targets = [first + timedelta(hours=grid * i) for i in range(per_city)]
    upcoming = []
    status = []
    for city_index, city in enumerate(cities):
        amps = 1200.0 + 10.0 * city_index
        issued = now.replace(minute=0, second=0, microsecond=0)
        for target in targets:
            lead = -((now - target).total_seconds() // 60)  # ceiling of the minutes to the target
            row = {
                "city": city,
                "valid_time": _iso(target),
                "issued_at": _iso(issued),
                "forecast_run_init_time": _iso(target - timedelta(minutes=day_ahead_contract.HORIZON_MINUTES)),
                "horizon_minutes": day_ahead_contract.HORIZON_MINUTES,
                "forecast_amps": amps,
                "forecast_ci_lower_amps": amps - 60.0,
                "forecast_ci_upper_amps": amps + 60.0,
                "band_source": "test-split",
                "band_n": 196,
                "band_pairs_through": _iso(target - timedelta(days=30)),
                "band_artifact_sha256": "12" * 32,
                "forecast_method": day_ahead_contract.FORECAST_METHOD,
                "cooling_model_sha256": "34" * 32,
                "cooling_model_source": "fake-cooling-model",
                "anchor_observation_time": _iso(issued - timedelta(minutes=5)),
                "anchor_source": "station",
                "label": day_ahead_contract.DAY_AHEAD_LABEL,
                "config_version": config.RATING_CONFIG_VERSION,
                "config_fingerprint": "56" * 32,
                "run_id": "fake-day-ahead-%s" % issued.strftime("%Y%m%d%H"),
                "run_attempt": 1,
                "pipeline_version": "fake0001",
                "schema_version": 1,
                "first_written_at": _iso(issued + timedelta(minutes=6)),
                "lead_minutes": int(lead),
            }
            upcoming.append({column: row[column] for column in day_ahead_contract.UPCOMING_COLUMNS})
        status.append({
            "city": city,
            "checked_at": _iso(now),
            "next_target_time": _iso(targets[0]),
            "upcoming_count": len(targets),
            "newest_issued_at": _iso(issued),
            "missing_targets": [],
            "is_late": False,
        })
    return upcoming, status


def _json_default(value):
    if isinstance(value, datetime):
        return _iso(value)
    raise TypeError("not serialisable: %r" % (value,))


def _coerce(column, value):
    """A comparable form of a stored or filter value."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if column in _TS_COLUMNS:
        return supabase_rest.parse_ts(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)


def _coerce_filter(column, text, sample):
    if column in _TS_COLUMNS:
        return supabase_rest.parse_ts(text)
    if isinstance(sample, bool):
        return text.lower() == "true"
    if isinstance(sample, (int, float)):
        return float(text)
    return text


def _matches(row, column, op, text):
    sample = row.get(column)
    have = _coerce(column, sample)
    if op == "in":
        wanted = [t.strip().strip('"') for t in text.strip("()").split(",") if t.strip()]
        return any(have == _coerce_filter(column, w, sample) for w in wanted)
    want = _coerce_filter(column, text, sample)
    if have is None:
        return False
    if op == "eq":
        return have == want
    if op == "neq":
        return have != want
    if op == "gt":
        return have > want
    if op == "gte":
        return have >= want
    if op == "lt":
        return have < want
    if op == "lte":
        return have <= want
    raise ValueError("unsupported operator %r" % op)


class _Handler(BaseHTTPRequestHandler):
    server_version = "FakePostgrest/1.0"
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):  # noqa: A002 - signature fixed by the base class
        pass

    def do_GET(self):
        self._serve()

    do_HEAD = do_GET
    do_POST = do_GET
    do_PATCH = do_GET
    do_DELETE = do_GET

    def _serve(self):
        fake = self.server.fake
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        parts = urlsplit(self.path)
        record = {
            "method": self.command,
            "path": parts.path,
            "query": parse_qsl(parts.query, keep_blank_values=True),
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": raw.decode("utf-8", errors="replace") if raw else None,
        }
        with fake.lock:
            fake.requests.append(record)
            if fake.before_request is not None:
                fake.before_request(fake, record)
            status, headers, payload = fake.dispatch(record)
        body = b"" if payload is None else json.dumps(payload, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


class FakePostgrest(object):
    def __init__(self, rows=None, key=DEFAULT_KEY, max_rows=1000, now=None, fresh=True,
                 write_mode="revoked", rpc_available=True, require_key=True, latest_override=None,
                 route_overrides=None, table_write_response=None, view_write_response=None,
                 count_override=None, before_request=None, day_ahead_upcoming=None,
                 day_ahead_status=None):
        if write_mode not in ("revoked", "rls_only", "open"):
            raise ValueError("write_mode must be revoked, rls_only or open")
        self.rows = [dict(r) for r in (rows or [])]
        self.key = key
        self.max_rows = max_rows
        self.now = now
        self.fresh = fresh
        self.write_mode = write_mode
        self.rpc_available = rpc_available
        self.require_key = require_key
        self.latest_override = latest_override
        self.route_overrides = dict(route_overrides or {})
        self.table_write_response = table_write_response
        self.view_write_response = view_write_response
        self.count_override = count_override
        self.before_request = before_request
        self.day_ahead_upcoming = None if day_ahead_upcoming is None else [dict(r) for r in day_ahead_upcoming]
        self.day_ahead_status = None if day_ahead_status is None else [dict(r) for r in day_ahead_status]
        self.requests = []
        self.lock = threading.RLock()
        self._server = None
        self._thread = None

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._server.fake = self
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=5)
            self._server = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc_info):
        self.stop()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self._server.server_address[1]

    # -- views -------------------------------------------------------------

    def _now(self):
        return self.now if self.now is not None else datetime.now(timezone.utc)

    def latest_view_rows(self):
        """What latest_rating shows: the newest row per city with age_minutes, is_stale, is_provisional."""
        if self.latest_override is not None:
            return [dict(r) for r in self.latest_override]
        now = self._now()
        newest = {}
        for row in self.rows:
            city = row["city"]
            stamp = supabase_rest.parse_ts(row["valid_time"])
            if city not in newest or stamp > newest[city][0]:
                newest[city] = (stamp, row)
        view = []
        for city in sorted(newest):
            stamp, row = newest[city]
            shown = {c: row.get(c) for c in contract.STORED_COLUMNS}
            shown["age_minutes"] = contract.age_minutes(stamp, now)
            shown["is_stale"] = contract.is_stale(stamp, now)
            shown["is_provisional"] = contract.is_provisional(row.get("rating_basis"), row.get("config_version"))
            view.append(shown)
        return view

    def day_ahead_view_rows(self, relation):
        """What day_ahead_upcoming or day_ahead_status shows: the lists given, else the defaults at now."""
        given = self.day_ahead_upcoming if relation == "day_ahead_upcoming" else self.day_ahead_status
        if given is not None:
            return [dict(r) for r in given]
        upcoming, status = make_day_ahead_view_rows(self._now())
        return upcoming if relation == "day_ahead_upcoming" else status

    # -- routing -----------------------------------------------------------

    def dispatch(self, record):
        """(status, extra headers, JSON payload) for one request. Called with the lock held."""
        headers = record["headers"]
        if self.require_key and headers.get("apikey") != self.key:
            return 401, {}, {"message": "No API key found in request",
                             "hint": "No `apikey` request header or url param was found."}
        path = record["path"]
        if not path.startswith("/rest/v1/"):
            return 404, {}, {"code": "PGRST125", "message": "Invalid path specified in request URL"}
        relation = path[len("/rest/v1/"):]
        method = record["method"]
        profile = headers.get("accept-profile") if method in ("GET", "HEAD") else headers.get("content-profile")
        if profile and profile != "public":
            override = self.route_overrides.get("%s.%s" % (profile, relation))
            if override is not None:
                return override[0], {}, override[1]
            return 406, {}, {"code": "PGRST106", "message": "The schema must be one of the following: public"}
        override = self.route_overrides.get("public.%s" % relation) or self.route_overrides.get(relation)
        if override is not None:
            return override[0], {}, override[1]
        if relation == "pipeline_run":
            return 401, {}, {"code": "42501", "details": None, "hint": None,
                             "message": "permission denied for table pipeline_run"}
        if relation == "rpc/assert_fresh":
            return self._assert_fresh()
        if relation in ("latest_rating", "city_rating"):
            if method in ("GET", "HEAD"):
                return self._read(relation, record)
            return self._write(relation, record)
        if relation in _DAY_AHEAD_RELATIONS:
            if method in ("GET", "HEAD"):
                return self._read(relation, record)
            return 401, {}, {"code": "42501", "details": None, "hint": None,
                             "message": "permission denied for view %s" % relation}
        return 404, {}, {"code": "PGRST205", "message": "Could not find the table 'public.%s' in the schema cache" % relation}

    def _assert_fresh(self):
        if not self.rpc_available:
            return 404, {}, {"code": "PGRST202", "message": "Could not find the function public.assert_fresh in the schema cache"}
        if self.fresh:
            return 200, {}, {"ok": True, "max_age_minutes": contract.STALE_AFTER_MINUTES, "cities": len(config.LOCATIONS)}
        return 503, {}, {"code": "PT503", "message": "stale", "details": "stale=%s" % config.LOCATIONS[0], "hint": None}

    # -- reads -------------------------------------------------------------

    @staticmethod
    def _filter(rows, query):
        """Rows matching every column filter in the query pairs (repeated filters are ANDed)."""
        for name, text in query:
            if name in _RESERVED or "." not in text:
                continue
            op, value = text.split(".", 1)
            rows = [r for r in rows if _matches(r, name, op, value)]
        return rows

    def _read(self, relation, record):
        query = record["query"]
        if relation == "latest_rating":
            rows = self.latest_view_rows()
        elif relation in _DAY_AHEAD_RELATIONS:
            rows = self.day_ahead_view_rows(relation)
        else:
            rows = [dict(r) for r in self.rows]
        try:
            rows = self._filter(rows, query)
        except ValueError as exc:
            return 400, {}, {"code": "PGRST100", "message": str(exc)}
        for name, text in query:
            if name == "order":
                rows = self._order(rows, text)
        if relation == "latest_rating" and not any(n == "order" for n, _ in query):
            rows.sort(key=lambda r: str(r.get("city")))
        if relation in _DAY_AHEAD_RELATIONS and not any(n == "order" for n, _ in query):
            rows = self._order(rows, "city,valid_time" if relation == "day_ahead_upcoming" else "city")
        total = len(rows)
        offset, limit = 0, None
        for name, text in query:
            if name == "offset":
                offset = int(text)
            elif name == "limit":
                limit = int(text)
        range_header = record["headers"].get("range")
        ranged = False
        if range_header and re.match(r"^\d+-\d+$", range_header.strip()):
            start, end = (int(x) for x in range_header.strip().split("-"))
            offset += start
            limit = (end - start + 1) if limit is None else min(limit, end - start + 1)
            ranged = True
        rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        rows = rows[:self.max_rows]
        select = next((t for n, t in query if n == "select"), "*")
        if select != "*":
            wanted = [c.strip() for c in select.split(",") if c.strip()]
            rows = [{c: r.get(c) for c in wanted} for r in rows]
        prefer = record["headers"].get("prefer", "")
        exact = "count=exact" in prefer
        shown_total = self.count_override if (exact and self.count_override is not None) else total
        if rows:
            span = "%d-%d" % (offset, offset + len(rows) - 1)
        else:
            span = "*"
        content_range = "%s/%s" % (span, shown_total if exact else "*")
        status = 206 if (ranged and offset + len(rows) < total) else 200
        return status, {"Content-Range": content_range}, rows

    @staticmethod
    def _order(rows, text):
        keys = []
        for item in text.split(","):
            pieces = item.strip().split(".")
            keys.append((pieces[0], "desc" in pieces[1:]))
        for column, descending in reversed(keys):
            rows = sorted(rows, key=lambda r: (r.get(column) is None, _coerce(column, r.get(column))),
                          reverse=descending)
        return rows

    # -- writes ------------------------------------------------------------

    def _write(self, relation, record):
        if relation == "latest_rating":
            if self.view_write_response is not None:
                return self.view_write_response[0], {}, self.view_write_response[1]
            return 500, {}, dict(_VIEW_NOT_UPDATABLE)
        if self.table_write_response is not None:
            return self.table_write_response[0], {}, self.table_write_response[1]
        if self.write_mode == "revoked":
            return 401, {}, {"code": "42501", "details": None, "hint": None,
                             "message": "permission denied for table city_rating"}
        if self.write_mode == "rls_only":
            if record["method"] == "POST":
                return 401, {}, {"code": "42501", "details": None, "hint": None,
                                 "message": "new row violates row-level security policy for table \"city_rating\""}
            return 200, {}, []  # a grant without a write policy: PATCH and DELETE match nothing and change nothing
        return self._apply_write(record)

    def _apply_write(self, record):
        """write_mode "open": the change is applied to the stored rows, as on a misconfigured project."""
        try:
            body = json.loads(record["body"]) if record["body"] else None
            query = record["query"]
            method = record["method"]
            prefer = record["headers"].get("prefer", "")
            if method == "POST":
                items = body if isinstance(body, list) else [body]
                upsert = "resolution=merge-duplicates" in prefer
                done = []
                for item in items:
                    key = (item["city"], supabase_rest.parse_ts(item["valid_time"]))
                    existing = next((r for r in self.rows
                                     if (r["city"], supabase_rest.parse_ts(r["valid_time"])) == key), None)
                    if existing is None:
                        existing = dict(item)
                        self.rows.append(existing)
                    elif upsert:
                        existing.update(item)
                    else:
                        return 409, {}, {"code": "23505", "message": "duplicate key value violates unique constraint"}
                    done.append(dict(existing))
                status = 201
            else:
                matched = self._filter(self.rows, query)
                if method == "PATCH":
                    for row in matched:
                        row.update(body)
                else:
                    self.rows = [r for r in self.rows if not any(r is m for m in matched)]
                done = [dict(r) for r in matched]
                status = 200
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            return 400, {}, {"code": "PGRST102", "message": "invalid body: %s" % exc}
        return status, {}, (done if "return=representation" in prefer else None)
