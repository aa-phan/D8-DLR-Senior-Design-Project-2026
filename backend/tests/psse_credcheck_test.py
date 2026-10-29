"""
DBX-02 proofs of the credential check on a throwaway local Postgres and a loopback PostgREST
stand-in (pss-e-integration Phase 3, plan 03-03): `psse_job.credcheck` shows, with the job's own
database credential, that `dlr_psse_writer` can insert into and select from the four result
tables and holds nothing else, and, over REST, that the publishable key can read ratings and
cannot change them.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's tmp
dir and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway
database (host 127.0.0.1, localhost or ::1; anything else fails the test). With
`PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping. They never
touch Supabase; the REST leg only ever talks to a server this module starts on 127.0.0.1.

Honest scope: on local Postgres 18.6 the role is the one the reference DDL creates and PostgREST
is a stand-in. These tests do not prove that Phase 6's live migration applied the same grants,
that Supabase's session pooler accepts the custom role, that role memberships and function
privileges on the live project are clean, or that the live publishable key answers 401 or 403;
each is runbook step 8 (plan 03-08) and stays UNVERIFIED until then. A where-false statement
raising 42501 is verified here for PostgreSQL 18.6 only.

Follows backend/tests/psse_study_job_test.py (module-level imports, plain asserts, no classes
except the stand-in server).
"""

import contextlib
import datetime
import http.server
import io
import json
import os
import sys
import threading
import urllib.parse

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fakes  # noqa: E402
import psse_local_pg as pg_helper  # noqa: E402
from psse_job import constants, credcheck, writer  # noqa: E402

WRITER_ROLE = "dlr_psse_writer"
UTC = datetime.timezone.utc

CATALOG_CHECKS = [
    "role_attributes",
    "role_memberships",
    "result_tables_insert_select",
    "result_tables_nothing_else",
    "nothing_on_other_relations",
    "no_executable_security_definer_in_public",
]
REFUSED_CHECKS = [
    "refused:select_city_rating",
    "refused:insert_city_rating",
    "refused:update_city_rating",
    "refused:delete_city_rating",
    "refused:select_pipeline_run",
    "refused:update_psse_run",
    "refused:delete_psse_run",
]
ROLE_LEG = CATALOG_CHECKS + REFUSED_CHECKS


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a database that already carries the Phase 4 migrations and the reference DDL."""
    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_schema(admin_url)
        yield admin_url


@pytest.fixture
def clean_pg(pg):
    """The same database with the four result tables empty."""
    pg_helper.reset(pg)
    return pg


def _writer_conn(admin_url):
    """An autocommit connection as the writer role, as the job opens it; the test closes it."""
    return writer.connect(pg_helper.role_url(admin_url, WRITER_ROLE))


def _superuser_conn(admin_url):
    import psycopg

    return psycopg.connect(admin_url, autocommit=True)


def _row_counts(admin_url):
    """count(*) of city_rating, pipeline_run and the four result tables, read as the superuser."""
    names = ("city_rating", "pipeline_run") + tuple(pg_helper.RESULT_TABLES)
    counts = {}
    for name in names:
        counts[name] = pg_helper.admin_rows(admin_url, "select count(*) as n from public." + name)[0]["n"]
    return counts


_SEED_CITY_RATING = (
    "insert into public.city_rating (city, valid_time, rating_amps, rating_mw, static_rating_amps, "
    "static_rating_mw, line_voltage_kv, power_factor, status, fallback, rating_basis, config_version, "
    "config_fingerprint) values ('AUSTIN', '2026-01-01 00:00:00+00', 1800, 1000, 1825, 1010, 345, 0.95, "
    "'ok', false, 'test', 'test', repeat('a', 64))"
)
_SEED_PIPELINE_RUN = "insert into public.pipeline_run (run_id) values ('credcheck-test-run')"


@contextlib.contextmanager
def _seeded(admin_url):
    """One city_rating row, one pipeline_run row and one complete run in the result tables."""
    import psycopg

    started = datetime.datetime(2026, 1, 1, 0, 15, tzinfo=UTC)
    run_id = pg_helper.make_run_id(1, started)
    rows = pg_helper.valid_run_rows(run_id, started)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(_SEED_CITY_RATING)
        conn.execute(_SEED_PIPELINE_RUN)
        for table in pg_helper.RESULT_TABLES:
            pg_helper.insert_rows(conn, table, rows[table])
    try:
        yield
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute("delete from public.city_rating")
            conn.execute("delete from public.pipeline_run")
        pg_helper.reset(admin_url)


def _by_name(rows):
    return dict((row.check, row) for row in rows)


def test_tracer_role_leg_passes_as_the_writer_and_fails_as_a_superuser(clean_pg):
    with _seeded(clean_pg):
        before = _row_counts(clean_pg)
        assert before["city_rating"] == 1 and before["pipeline_run"] == 1
        assert all(before[table] >= 1 for table in pg_helper.RESULT_TABLES)

        conn = _writer_conn(clean_pg)
        try:
            as_writer = credcheck.role_checks(conn)
        finally:
            conn.close()
        assert [row.check for row in as_writer] == ROLE_LEG
        assert [row.status for row in as_writer] == [credcheck.PASS] * 13, [
            (row.check, row.detail) for row in as_writer if row.status != credcheck.PASS]
        for row in as_writer:
            if row.check.startswith("refused:"):
                assert "42501" in row.detail, row
        assert credcheck.checks_ok(as_writer) is True
        assert credcheck.format_report(as_writer).splitlines()[-1] == "13 PASS, 0 FAIL, 0 SKIP"

        conn = _superuser_conn(clean_pg)
        try:
            as_superuser = credcheck.role_checks(conn)
        finally:
            conn.close()
        assert [row.check for row in as_superuser] == ROLE_LEG
        named = _by_name(as_superuser)
        must_fail = ["role_attributes", "result_tables_nothing_else", "nothing_on_other_relations"] + REFUSED_CHECKS
        for name in must_fail:
            assert named[name].status == credcheck.FAIL, (name, named[name].detail)
        for name in REFUSED_CHECKS:
            assert "the statement was allowed" in named[name].detail, named[name]
        for name in ("role_memberships", "result_tables_insert_select", "no_executable_security_definer_in_public"):
            assert named[name].status == credcheck.PASS, (name, named[name].detail)
        assert credcheck.checks_ok(as_superuser) is False
        assert credcheck.format_report(as_superuser).splitlines()[-1] == "3 PASS, 10 FAIL, 0 SKIP"

        # Neither call changed a row of any table.
        assert _row_counts(clean_pg) == before


# --------------------------------------------------------------------------- planted faults


@contextlib.contextmanager
def _planted(admin_url, apply_sql, revert_sql):
    """Apply the fault as the superuser; always revert it (the database is shared by the module's tests)."""
    import psycopg

    with psycopg.connect(admin_url, autocommit=True) as conn:
        try:
            for statement in apply_sql:
                conn.execute(statement)
            yield
        finally:
            for statement in revert_sql:
                conn.execute(statement)


def _writer_role_checks(admin_url):
    conn = _writer_conn(admin_url)
    try:
        return credcheck.role_checks(conn)
    finally:
        conn.close()


def _failing(rows):
    return set(row.check for row in rows if row.status == credcheck.FAIL)


def _assert_fault(admin_url, apply_sql, revert_sql, failing):
    """
    The planted fault turns exactly the `failing` checks red (the named ones, and no unrelated
    one), and after the revert every check is green again.
    """
    with _planted(admin_url, apply_sql, revert_sql):
        rows = _writer_role_checks(admin_url)
        assert [row.check for row in rows] == ROLE_LEG
        assert _failing(rows) == set(failing), [(row.check, row.status, row.detail) for row in rows]
        assert credcheck.checks_ok(rows) is False
    restored = _writer_role_checks(admin_url)
    assert [row.status for row in restored] == [credcheck.PASS] * 13, [
        (row.check, row.detail) for row in restored if row.status != credcheck.PASS]


def test_fault_update_on_city_rating(clean_pg):
    # UPDATE alone, without SELECT: the statement must not need SELECT, or the missing SELECT would
    # refuse it with 42501 and hide the fault.
    _assert_fault(
        clean_pg,
        ["grant update on public.city_rating to " + WRITER_ROLE],
        ["revoke update on public.city_rating from " + WRITER_ROLE],
        ["nothing_on_other_relations", "refused:update_city_rating"],
    )


def test_fault_insert_revoked_on_result_table(clean_pg):
    _assert_fault(
        clean_pg,
        ["revoke insert on public.psse_dispatched_capacity from " + WRITER_ROLE],
        ["grant insert on public.psse_dispatched_capacity to " + WRITER_ROLE],
        ["result_tables_insert_select"],
    )


def test_fault_public_grant_on_pipeline_run(clean_pg):
    _assert_fault(
        clean_pg,
        ["grant select on public.pipeline_run to public"],
        ["revoke select on public.pipeline_run from public"],
        ["nothing_on_other_relations", "refused:select_pipeline_run"],
    )


def test_fault_update_on_result_table(clean_pg):
    _assert_fault(
        clean_pg,
        ["grant update on public.psse_run to " + WRITER_ROLE],
        ["revoke update on public.psse_run from " + WRITER_ROLE],
        ["result_tables_nothing_else", "refused:update_psse_run"],
    )


def test_fault_delete_on_result_table(clean_pg):
    _assert_fault(
        clean_pg,
        ["grant delete on public.psse_run to " + WRITER_ROLE],
        ["revoke delete on public.psse_run from " + WRITER_ROLE],
        ["result_tables_nothing_else", "refused:delete_psse_run"],
    )


def test_fault_role_membership(clean_pg):
    role = "credcheck_member_role"
    _assert_fault(
        clean_pg,
        ["create role " + role, "grant " + role + " to " + WRITER_ROLE],
        ["revoke " + role + " from " + WRITER_ROLE, "drop role " + role],
        ["role_memberships"],
    )


def test_fault_security_definer_function(clean_pg):
    _assert_fault(
        clean_pg,
        ["create function public.credcheck_probe_fn() returns integer language sql security definer "
         "as 'select 1'"],
        ["drop function public.credcheck_probe_fn()"],
        ["no_executable_security_definer_in_public"],
    )


def test_fault_role_attribute(clean_pg):
    _assert_fault(
        clean_pg,
        ["alter role " + WRITER_ROLE + " createrole"],
        ["alter role " + WRITER_ROLE + " nocreaterole"],
        ["role_attributes"],
    )


def test_planted_column_level_update_is_seen(clean_pg):
    # has_table_privilege alone cannot see a column grant; the checks use has_any_column_privilege.
    _assert_fault(
        clean_pg,
        ["grant update (rating_amps) on public.city_rating to " + WRITER_ROLE],
        ["revoke update (rating_amps) on public.city_rating from " + WRITER_ROLE],
        ["nothing_on_other_relations", "refused:update_city_rating"],
    )
    _assert_fault(
        clean_pg,
        ["grant update (job_version) on public.psse_run to " + WRITER_ROLE],
        ["revoke update (job_version) on public.psse_run from " + WRITER_ROLE],
        ["result_tables_nothing_else", "refused:update_psse_run"],
    )


# --------------------------------------------------------------------------- REST leg


class _RestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - signature fixed by the base class
        return

    def _record(self, method):
        owner = self.server.owner
        parts = urllib.parse.urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        owner.requests.append({
            "method": method,
            "path": parts.path,
            "query": urllib.parse.parse_qsl(parts.query, keep_blank_values=True),
            "headers": dict((name.lower(), value) for name, value in self.headers.items()),
            "body": body,
        })
        return owner, parts

    def _send(self, status, text):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        owner, parts = self._record("GET")
        if parts.path != "/rest/v1/latest_rating":
            self._send(404, json.dumps({"message": "not found"}))
        elif owner.read_status == 200:
            self._send(200, json.dumps(owner.rows))
        else:
            self._send(owner.read_status, json.dumps({"message": "refused"}))

    def do_PATCH(self):
        owner, parts = self._record("PATCH")
        self._answer(owner, parts, owner.patch_status)

    def do_DELETE(self):
        owner, parts = self._record("DELETE")
        self._answer(owner, parts, owner.delete_status)

    def _answer(self, owner, parts, status):
        if parts.path != "/rest/v1/city_rating":
            self._send(404, json.dumps({"message": "not found"}))
        elif 200 <= status < 300:
            self._send(status, "" if status == 204 else "[]")
        else:
            self._send(status, json.dumps({"message": "refused"}))


class RestStandIn(object):
    """
    Loopback PostgREST stand-in for the REST leg: GET /rest/v1/latest_rating answers `read_status`
    (the rows when 200) and PATCH or DELETE /rest/v1/city_rating answer the configured status.
    Every request is recorded (method, path, query, lower-case headers, body). It checks no key. Plan
    03-06's rehearsal imports this class. Usable as a context manager.
    """

    def __init__(self, rows=None, read_status=200, patch_status=401, delete_status=401):
        self.rows = [] if rows is None else rows
        self.read_status = read_status
        self.patch_status = patch_status
        self.delete_status = delete_status
        self.requests = []
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RestHandler)
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


def _now():
    return datetime.datetime.now(UTC)


def _rest_env(server, key=None):
    return {
        "SUPABASE_URL": server.url,
        "SUPABASE_PUBLISHABLE_KEY": psse_fakes.fake_publishable_key() if key is None else key,
    }


REST_CHECKS = ["rest:read_ratings", "rest:patch_city_rating_refused", "rest:delete_city_rating_refused"]


def _rest(server, key=None):
    return _by_name(credcheck.rest_checks(_rest_env(server, key)))


def test_rest_refused_with_401_or_403_passes():
    for patch_status, delete_status in ((401, 403), (403, 401)):
        with RestStandIn(rows=psse_fakes.latest_rows(_now()), patch_status=patch_status,
                         delete_status=delete_status) as server:
            rows = credcheck.rest_checks(_rest_env(server))
        assert [row.check for row in rows] == REST_CHECKS
        assert [row.status for row in rows] == [credcheck.PASS] * 3, [(row.check, row.detail) for row in rows]
        assert "4 rows" in rows[0].detail
        assert "HTTP %d" % patch_status in rows[1].detail
        assert "HTTP %d" % delete_status in rows[2].detail
        assert [request["method"] for request in server.requests] == ["GET", "PATCH", "DELETE"]


def test_rest_write_allowed_fails():
    for which in ("patch", "delete"):
        for allowed in (200, 204):
            kwargs = {which + "_status": allowed}
            with RestStandIn(rows=psse_fakes.latest_rows(_now()), **kwargs) as server:
                named = _rest(server)
            bad = "rest:%s_city_rating_refused" % which
            other = "rest:delete_city_rating_refused" if which == "patch" else "rest:patch_city_rating_refused"
            assert named[bad].status == credcheck.FAIL
            assert "allowed to change city_rating (HTTP %d)" % allowed in named[bad].detail
            assert named[other].status == credcheck.PASS
            assert named["rest:read_ratings"].status == credcheck.PASS


def test_rest_inconclusive_status_fails():
    for status in (404, 500):
        with RestStandIn(rows=psse_fakes.latest_rows(_now()), patch_status=status, delete_status=status) as server:
            named = _rest(server)
        for check in ("rest:patch_city_rating_refused", "rest:delete_city_rating_refused"):
            assert named[check].status == credcheck.FAIL
            assert "inconclusive: HTTP %d" % status in named[check].detail
        assert credcheck.checks_ok(list(named.values())) is False


def test_rest_read_failure_skips_the_write_attempts():
    with RestStandIn(rows=psse_fakes.latest_rows(_now()), read_status=401) as server:
        rows = credcheck.rest_checks(_rest_env(server))
    named = _by_name(rows)
    assert [row.check for row in rows] == REST_CHECKS
    assert named["rest:read_ratings"].status == credcheck.FAIL
    assert "HTTP 401" in named["rest:read_ratings"].detail
    for check in ("rest:patch_city_rating_refused", "rest:delete_city_rating_refused"):
        assert named[check].status == credcheck.SKIP
        assert "not sent" in named[check].detail
    assert [request["method"] for request in server.requests] == ["GET"]


def test_rest_secret_key_refused_and_nothing_sent():
    secret_key = "sb_" + "secret_" + "testkeyabcdefghij0123456789"
    with RestStandIn(rows=psse_fakes.latest_rows(_now()), patch_status=204, delete_status=204) as server:
        rows = credcheck.rest_checks(_rest_env(server, secret_key))
    named = _by_name(rows)
    assert named["rest:read_ratings"].status == credcheck.FAIL
    assert named["rest:patch_city_rating_refused"].status == credcheck.SKIP
    assert named["rest:delete_city_rating_refused"].status == credcheck.SKIP
    assert server.requests == []
    assert secret_key not in credcheck.format_report(rows)


def test_rest_requests_are_zero_match_and_apikey_only():
    key = psse_fakes.fake_publishable_key()
    with RestStandIn(rows=psse_fakes.latest_rows(_now())) as server:
        rows = credcheck.rest_checks(_rest_env(server, key))
    assert [row.status for row in rows] == [credcheck.PASS] * 3
    _, patch, delete = server.requests
    for request in (patch, delete):
        assert request["path"] == "/rest/v1/city_rating"
        assert request["query"] == [("city", "eq.__no_such_city__")]
        assert request["headers"]["apikey"] == key
        assert "authorization" not in request["headers"]
    assert patch["method"] == "PATCH"
    body = json.loads(patch["body"].decode("utf-8"))
    assert isinstance(body, dict) and len(body) == 1
    assert delete["method"] == "DELETE"
    assert delete["body"] == b""
    assert key not in credcheck.format_report(rows)
