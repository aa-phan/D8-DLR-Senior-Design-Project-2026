"""
Test helpers for the PSS/E job (pss-e-integration Phase 1). Not collected by pytest
(the file name does not match `*_test.py`).

`FakeLatestRatingServer` is a loopback PostgREST stand-in for `GET /rest/v1/latest_rating`
that records every request, so a test can prove which columns were selected and which
headers were sent. `latest_rows` builds rows with exactly the selected columns.
`fake_publishable_key` returns a key that is not credential-shaped for
backend/tests/secret_scan_test.py.

Plan 01-04 adds `fake_fetch` (a deep-copying stand-in for the ratings read), `fake_results`
(a StudyResults whose rows satisfy every DDL CHECK and match a Selection) and `FakeStudy`
(a callable study that records its calls).
"""

import copy
import datetime
import http.server
import json
import math
import os
import sys
import threading
import urllib.parse

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from psse_job import constants, contract, units  # noqa: E402


def fake_publishable_key():
    """A publishable-shaped test key assembled from pieces."""
    return "sb_" + "publishable_" + "testkeyabcdefghij0123456789"


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - signature fixed by the base class
        return

    def do_GET(self):
        server = self.server.owner
        parts = urllib.parse.urlsplit(self.path)
        server.requests.append({
            "method": "GET",
            "path": parts.path,
            "query": urllib.parse.parse_qsl(parts.query, keep_blank_values=True),
            "headers": {name.lower(): value for name, value in self.headers.items()},
        })
        if parts.path != "/rest/v1/latest_rating":
            self._send(404, "not found", "text/plain")
            return
        if server.key is not None and self.headers.get("apikey") != server.key:
            self._send(401, json.dumps({"message": "Invalid API key"}), "application/json")
            return
        if server.body is not None:
            self._send(server.status, server.body, "application/json")
            return
        self._send(server.status, json.dumps(server.rows), "application/json")

    def _send(self, status, text, content_type):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FakeLatestRatingServer(object):
    """Loopback server for GET /rest/v1/latest_rating; usable as a context manager."""

    def __init__(self, rows=None, status=200, body=None, key=None):
        self.rows = [] if rows is None else rows
        self.status = status
        self.body = body
        self.key = key
        self.requests = []
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.owner = self
        self._thread = None
        self.url = "http://127.0.0.1:%d" % self._httpd.server_address[1]

    def start(self):
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False


def _iso(moment):
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def latest_rows(now, provisional=True, age_minutes=10.0, cities=None, **overrides):
    """One latest_rating row per city with exactly the LATEST_RATING_SELECT keys.

    rating_amps is 1.1 x the static rating so a used row differs from static.
    `overrides` replace or add keys in every row.
    """
    valid = now - datetime.timedelta(minutes=age_minutes)
    computed = valid + datetime.timedelta(minutes=6)
    rows = []
    for city in (constants.CITIES if cities is None else cities):
        static = constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city]
        row = {
            "city": city,
            "valid_time": _iso(valid),
            "computed_at": _iso(computed),
            "rating_amps": static * 1.1,
            "static_rating_amps": static,
            "status": "ok",
            "fallback": False,
            "run_id": "1234567890",
            "config_fingerprint": "ab" * 32,
            "age_minutes": int(math.ceil(age_minutes)),
            "is_stale": age_minutes > 90,
            "is_provisional": provisional,
        }
        row.update(overrides)
        rows.append(row)
    return rows


def fake_fetch(rows):
    """A ratings read that returns a deep copy of `rows` on every call."""
    def fetch():
        return copy.deepcopy(rows)
    return fetch


def fake_results(selection, violations=2, n_contingencies=3, voltage_limit_factor=1.2,
                 line_voltage_kv=345.0):
    """
    A contract.StudyResults whose rows satisfy every DDL CHECK and match `selection`: one
    dispatch and one margin row per city, then `violations` (0, 1 or 2) contingency rows.
    The city_rating link columns are set only for a choice whose source is city_rating.
    """
    if violations not in (0, 1, 2):
        raise ValueError("violations must be 0, 1 or 2")
    dispatch = []
    margins = []
    applied = {}
    for city in constants.CITIES:
        choice = selection.choices[city]
        applied_amps_circuit = units.circuit_amps(choice.amps_per_conductor, choice.subconductors_per_phase)
        applied_mva = units.circuit_mva(
            choice.amps_per_conductor, choice.subconductors_per_phase, line_voltage_kv
        )
        applied[city] = applied_mva
        voltage_limit_mva = voltage_limit_factor * applied_mva
        dispatched_mva = min(applied_mva, voltage_limit_mva)
        dispatched_amps_circuit = units.mva_to_circuit_amps(dispatched_mva, line_voltage_kv)
        linked = choice.source == constants.SOURCE_CITY_RATING
        dispatch.append({
            "city": city,
            "rating_source": choice.source,
            "fallback_reason": choice.fallback_reason,
            "city_rating_valid_time": choice.row_valid_time if linked else None,
            "city_rating_computed_at": choice.row_computed_at if linked else None,
            "applied_amps_per_conductor": choice.amps_per_conductor,
            "subconductors_per_phase": choice.subconductors_per_phase,
            "applied_amps_circuit": applied_amps_circuit,
            "line_voltage_kv": line_voltage_kv,
            "applied_mva": applied_mva,
            "voltage_limit_mva": voltage_limit_mva,
            "dispatched_mva": dispatched_mva,
            "dispatched_amps_circuit": dispatched_amps_circuit,
            "dispatched_amps_per_conductor": dispatched_amps_circuit / choice.subconductors_per_phase,
            "power_factor": 0.95,
            "dispatched_mw": dispatched_mva * 0.95,
            "limiting_factor": "dlr_rating" if applied_mva <= voltage_limit_mva else "voltage_stability",
            "details": None,
        })
        margins.append({
            "city": city,
            "method": "pv_curve",
            "base_transfer_mw": 1000.0,
            "limit_transfer_mw": 1120.0,
            "margin_mw": 120.0,
            "margin_pct": 12.0,
            "voltage_limit_mva": voltage_limit_mva,
            "critical_bus": "1001",
            "min_voltage_pu": 0.93,
            "details": None,
        })
    contingencies = []
    if violations >= 1:
        limit = applied["AUSTIN"]
        observed = 1.05 * limit
        contingencies.append({
            "contingency_id": "1003-1004-1",
            "violation_kind": "thermal_overload",
            "element_type": "branch",
            "element_id": "1001-1002-1",
            "city": "AUSTIN",
            "limit_value": limit,
            "observed_value": observed,
            "exceeded_by": observed - limit,
            "unit": "MVA",
            "details": None,
        })
    if violations >= 2:
        contingencies.append({
            "contingency_id": "1005-1006-1",
            "violation_kind": "voltage_low",
            "element_type": "bus",
            "element_id": "2001",
            "city": None,
            "limit_value": 0.95,
            "observed_value": 0.92,
            "exceeded_by": 0.03,
            "unit": "pu",
            "details": None,
        })
    return contract.StudyResults(
        dispatch=dispatch, margins=margins, contingencies=contingencies,
        n_contingencies=n_contingencies, rate_set="RATEA", psse_version="35.6.0",
    )


class FakeStudy(object):
    """A callable study `(selection, context)`; records each call, raises or returns results."""

    def __init__(self, results=None, raises=None):
        self.results = results
        self.raises = raises
        self.calls = []

    def __call__(self, selection, context):
        self.calls.append((selection, context))
        if self.raises is not None:
            raise self.raises
        if self.results is not None:
            return self.results
        return fake_results(selection)
