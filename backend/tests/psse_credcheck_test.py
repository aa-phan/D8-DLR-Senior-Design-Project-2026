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


# --------------------------------------------------------------------------- write proof, run, hygiene

WRITE_PROOF_CHECKS = [
    "write_proof:insert_and_read_back_inside_rollback",
    "write_proof:nothing_survives",
]
RUN_COUNTS = {
    "psse_run": 1, "psse_dispatched_capacity": 4, "psse_voltage_margin": 4, "psse_contingency_result": 2,
}


def _result_counts(admin_url):
    return dict(
        (table, pg_helper.admin_rows(admin_url, "select count(*) as n from public." + table)[0]["n"])
        for table in pg_helper.RESULT_TABLES)


class _RecordingConn(object):
    """
    A proxy around the real connection (the connect seam). It delegates every attribute, so the
    assignments `conn.autocommit = ...` and `conn.read_only = ...` a caller may make reach the real
    connection, and records, for every statement passed to `execute`: its first word, the depth of
    open transaction(force_rollback=True) blocks, the server's transaction status before it
    (psycopg reads it from libpq: 2 is inside a transaction block, 0 is idle) and its text.
    `cursor` is refused, so no statement can bypass the record.
    """

    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "statements", [])
        object.__setattr__(self, "forced_depth", 0)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        setattr(self._conn, name, value)

    def cursor(self, *args, **kwargs):
        raise AssertionError("a statement must go through conn.execute so that it is recorded")

    def execute(self, query, *args, **kwargs):
        text = query if isinstance(query, str) else str(query)
        self.statements.append({
            "word": text.split(None, 1)[0].lower(),
            "forced_depth": self.forced_depth,
            "status": int(self._conn.info.transaction_status),
            "text": text,
        })
        return self._conn.execute(query, *args, **kwargs)

    @contextlib.contextmanager
    def transaction(self, *args, **kwargs):
        forced = bool(kwargs.get("force_rollback"))
        with self._conn.transaction(*args, **kwargs) as block:
            if forced:
                object.__setattr__(self, "forced_depth", self.forced_depth + 1)
            try:
                yield block
            finally:
                if forced:
                    object.__setattr__(self, "forced_depth", self.forced_depth - 1)


def _recording(admin_url):
    return _RecordingConn(_writer_conn(admin_url))


def _result_inserts(proxy):
    return [item for item in proxy.statements if item["word"] == "insert" and "public.psse_" in item["text"]]


def test_synthetic_run_passes_phase1_validation(monkeypatch):
    calls = []
    real = credcheck.run_record.validate_results

    def spy(results, selection):
        calls.append((results, selection))
        return real(results, selection)

    monkeypatch.setattr(credcheck.run_record, "validate_results", spy)
    now = _now()
    selection, record, rows = credcheck.synthetic_run(now)

    assert len(calls) == 1 and calls[0][1] is selection
    assert all(selection.choices[city].source == constants.SOURCE_STATIC
               and selection.choices[city].fallback_reason == "missing" for city in constants.CITIES)
    assert record["outcome"] == "fallback"
    assert record["case_id"] == "credcheck-synthetic"
    assert record["job_version"] == "credcheck"
    assert record["started_at"] == now
    assert [len(rows[table]) for table in credcheck.contract.RESULT_TABLES] == [4, 4, 2]
    assert all(row["run_id"] == record["run_id"] and row["run_outcome"] == "fallback"
               for table in credcheck.contract.RESULT_TABLES for row in rows[table])
    assert [row["city"] for row in rows[credcheck.contract.DISPATCH_TABLE]] == list(constants.CITIES)
    # No database is needed to build it, and a second call is a different run.
    assert credcheck.synthetic_run(now)[1]["run_id"] != record["run_id"]


def test_write_proof_inserts_a_complete_run_and_nothing_survives(clean_pg):
    # Control first: the very same synthetic run, written as the job writes it, really persists, so
    # a zero afterwards is the rollback and not an insert that silently did nothing.
    conn = _writer_conn(clean_pg)
    try:
        _, record, rows = credcheck.synthetic_run(_now())
        assert writer.write_run(conn, record, rows) == writer.WRITTEN
        assert _result_counts(clean_pg) == RUN_COUNTS
        pg_helper.reset(clean_pg)
        assert _result_counts(clean_pg) == dict((table, 0) for table in pg_helper.RESULT_TABLES)

        proof = credcheck.write_proof(conn)
    finally:
        conn.close()
    assert [row.check for row in proof] == WRITE_PROOF_CHECKS
    assert [row.status for row in proof] == [credcheck.PASS] * 2, [(row.check, row.detail) for row in proof]
    assert "run 1, dispatch 4, margin 4, contingency 2" in proof[0].detail
    assert "run 0, dispatch 0, margin 0, contingency 0" in proof[1].detail
    assert _result_counts(clean_pg) == dict((table, 0) for table in pg_helper.RESULT_TABLES)


def test_write_proof_is_off_by_default(clean_pg):
    env = {"SUPABASE_PSSE_DB_URL": pg_helper.role_url(clean_pg, WRITER_ROLE)}

    # Without the flag: the only insert is the where-false insert into city_rating, none reaches a
    # result table, and nothing is left in them.
    proxy = _recording(clean_pg)
    try:
        code = credcheck.run(env, skip_rest=True, out=io.StringIO(), connect=lambda: proxy)
    finally:
        proxy.close()
    assert code == 0
    inserts = [item for item in proxy.statements if item["word"] == "insert"]
    assert len(inserts) == 1
    assert "public.city_rating" in inserts[0]["text"] and inserts[0]["text"].endswith("where false")
    assert _result_inserts(proxy) == []
    assert _result_counts(clean_pg) == dict((table, 0) for table in pg_helper.RESULT_TABLES)

    # The proxy can tell: outside a transaction block the server reports idle (0), not 2.
    probe = _recording(clean_pg)
    try:
        probe.execute("select 1")
        with probe.transaction():
            probe.execute("select 1")
    finally:
        probe.close()
    assert [item["status"] for item in probe.statements] == [0, 2]

    # With the flag: 11 inserts into the result tables (the run row and 4 + 4 + 2), each executed
    # inside the forced-rollback block and inside a transaction on the server.
    proxy = _recording(clean_pg)
    try:
        code = credcheck.run(env, skip_rest=True, write_proof=True, out=io.StringIO(), connect=lambda: proxy)
    finally:
        proxy.close()
    assert code == 0
    inserts = _result_inserts(proxy)
    assert len(inserts) == 11
    assert all(item["forced_depth"] >= 1 and item["status"] == 2 for item in inserts)
    assert _result_counts(clean_pg) == dict((table, 0) for table in pg_helper.RESULT_TABLES)


def test_write_proof_failure_reported_and_still_rolled_back(clean_pg):
    with _planted(
        clean_pg,
        ["revoke insert on public.psse_voltage_margin from " + WRITER_ROLE],
        ["grant insert on public.psse_voltage_margin to " + WRITER_ROLE],
    ):
        conn = _writer_conn(clean_pg)
        try:
            proof = credcheck.write_proof(conn)
        finally:
            conn.close()
        # The failed-run record that write_run writes after its own rollback sat inside the outer
        # transaction too, so no row of any table exists.
        assert _result_counts(clean_pg) == dict((table, 0) for table in pg_helper.RESULT_TABLES)
    named = _by_name(proof)
    assert [row.check for row in proof] == WRITE_PROOF_CHECKS
    assert named["write_proof:insert_and_read_back_inside_rollback"].status == credcheck.FAIL
    assert "psse_voltage_margin" in named["write_proof:insert_and_read_back_inside_rollback"].detail
    assert "postgresql://" not in named["write_proof:insert_and_read_back_inside_rollback"].detail
    assert named["write_proof:nothing_survives"].status == credcheck.PASS
    # Restored: the proof passes again.
    conn = _writer_conn(clean_pg)
    try:
        assert [row.status for row in credcheck.write_proof(conn)] == [credcheck.PASS] * 2
    finally:
        conn.close()


def _url_with_password(admin_url, user, password):
    parts = urllib.parse.urlsplit(pg_helper.role_url(admin_url, user))
    return parts._replace(netloc="%s:%s@%s:%d" % (user, password, parts.hostname, parts.port)).geturl()


def test_run_exit_codes_and_skip_rest(clean_pg):
    db_url = pg_helper.role_url(clean_pg, WRITER_ROLE)
    with RestStandIn(rows=psse_fakes.latest_rows(_now())) as server:
        env = dict(_rest_env(server), SUPABASE_PSSE_DB_URL=db_url)
        buffer = io.StringIO()
        assert credcheck.run(env, out=buffer) == 0
        assert buffer.getvalue().splitlines()[-1] == "16 PASS, 0 FAIL, 0 SKIP"

        buffer = io.StringIO()
        assert credcheck.run(env, write_proof=True, out=buffer) == 0
        assert buffer.getvalue().splitlines()[-1] == "18 PASS, 0 FAIL, 0 SKIP"

        # Any FAIL gives 6: here the credential under test is the superuser.
        buffer = io.StringIO()
        admin_env = dict(env, SUPABASE_PSSE_DB_URL=clean_pg)
        assert credcheck.run(admin_env, out=buffer) == 6
        assert "FAIL  role_attributes" in buffer.getvalue()

    # REST configured-missing is a FAIL unless skip_rest was asked for.
    db_only = {"SUPABASE_PSSE_DB_URL": db_url}
    buffer = io.StringIO()
    assert credcheck.run(db_only, out=buffer) == 6
    assert buffer.getvalue().splitlines()[-1] == "13 PASS, 1 FAIL, 2 SKIP"
    assert "FAIL  rest:read_ratings" in buffer.getvalue()

    buffer = io.StringIO()
    assert credcheck.run(db_only, skip_rest=True, out=buffer) == 0
    lines = buffer.getvalue().splitlines()
    assert lines[-1] == "13 PASS, 0 FAIL, 1 SKIP"
    assert len([line for line in lines if line.startswith("SKIP")]) == 1
    assert [line for line in lines if "rest:" in line][0].startswith("SKIP  rest:skipped")


def test_run_output_names_no_secret(clean_pg):
    password = "pw" + "-credcheck-" + "7391"
    key = psse_fakes.fake_publishable_key()
    db_url = _url_with_password(clean_pg, WRITER_ROLE, password)
    with RestStandIn(rows=psse_fakes.latest_rows(_now())) as server:
        env = dict(_rest_env(server, key), SUPABASE_PSSE_DB_URL=db_url)
        buffer = io.StringIO()
        assert credcheck.run(env, write_proof=True, out=buffer) == 0
        text = buffer.getvalue()
        port = str(urllib.parse.urlsplit(clean_pg).port)
        for secret in (password, key, db_url, server.url, "127.0.0.1", WRITER_ROLE, "postgresql://",
                       "localhost", "apikey", port):
            assert secret not in text, secret
        # A failing report is as clean: the credential under test is the superuser, with a password.
        admin_env = dict(env, SUPABASE_PSSE_DB_URL=_url_with_password(clean_pg, "postgres", password))
        buffer = io.StringIO()
        assert credcheck.run(admin_env, out=buffer) == 6
        for secret in (password, key, server.url, "127.0.0.1", "postgres@", "postgresql://", port):
            assert secret not in buffer.getvalue(), secret


def test_run_connection_failure_exit_6():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    password = "pw" + "-credcheck-" + "5512"
    user = "cc" + "user"
    url = "postgresql://" + user + ":" + password + "@127.0.0.1:" + str(port) + "/nodb"
    buffer = io.StringIO()
    assert credcheck.run({"SUPABASE_PSSE_DB_URL": url}, skip_rest=True, out=buffer) == 6
    text = buffer.getvalue()
    assert len(text.splitlines()) == 1
    assert text.startswith("credential check could not run: ")
    for secret in (password, user, "127.0.0.1", url):
        assert secret not in text, secret
    # No URL at all is the same one clean line.
    buffer = io.StringIO()
    assert credcheck.run({}, skip_rest=True, out=buffer) == 6
    assert buffer.getvalue() == "credential check could not run: SUPABASE_PSSE_DB_URL is not set\n"


def test_run_active_statements_all_run_in_a_forced_rollback_transaction(clean_pg):
    env = {"SUPABASE_PSSE_DB_URL": pg_helper.role_url(clean_pg, WRITER_ROLE)}
    proxy = _recording(clean_pg)
    try:
        assert credcheck.run(env, skip_rest=True, out=io.StringIO(), connect=lambda: proxy) == 0
    finally:
        proxy.close()
    active = [item for item in proxy.statements if "where false" in item["text"]]
    assert len(active) == 7
    assert all(item["forced_depth"] == 1 and item["status"] == 2 for item in active), active
    # Every other statement is a catalog read.
    others = [item for item in proxy.statements if "where false" not in item["text"]]
    assert others and all(item["word"] == "select" for item in others)


def test_run_inconclusive_error_names_no_text(clean_pg):
    with _planted(
        clean_pg,
        ["alter table public.pipeline_run rename to pipeline_run_renamed"],
        ["alter table public.pipeline_run_renamed rename to pipeline_run"],
    ):
        rows = _writer_role_checks(clean_pg)
    named = _by_name(rows)
    assert _failing(rows) == set(["refused:select_pipeline_run"])
    assert named["refused:select_pipeline_run"].detail == "inconclusive: SQLSTATE 42P01"
    for row in rows:
        assert "does not exist" not in row.detail and "pipeline_run" not in row.detail


def test_run_session_is_not_read_only_because_that_would_hide_the_proof(clean_pg):
    # Control for the lesson of plan 03-02: a really read-only session (autocommit off, then
    # read_only on) is refused with 25006 before privileges are looked at, so the five write
    # statements would be "inconclusive" and a planted write grant could never be seen. credcheck.run
    # therefore never sets read_only, and its proxy never sees the flag change.
    conn = _writer_conn(clean_pg)
    try:
        conn.autocommit = False
        conn.read_only = True
        rows = credcheck.role_checks(conn)
    finally:
        conn.close()
    named = _by_name(rows)
    assert _failing(rows) == set([
        "refused:insert_city_rating", "refused:update_city_rating", "refused:delete_city_rating",
        "refused:update_psse_run", "refused:delete_psse_run"])
    assert named["refused:update_city_rating"].detail == "inconclusive: SQLSTATE 25006"
    assert named["refused:select_city_rating"].status == credcheck.PASS

    env = {"SUPABASE_PSSE_DB_URL": pg_helper.role_url(clean_pg, WRITER_ROLE)}
    proxy = _recording(clean_pg)
    try:
        assert credcheck.run(env, skip_rest=True, write_proof=True, out=io.StringIO(), connect=lambda: proxy) == 0
        assert not proxy.read_only
    finally:
        proxy.close()
