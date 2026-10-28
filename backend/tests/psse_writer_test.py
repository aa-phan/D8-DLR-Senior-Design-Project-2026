"""
Local-Postgres proofs of the atomic PSS/E result writer (pss-e-integration Phase 1,
WB-01, WB-02, D-03, D-04).

`psse_job.writer` connects as the DDL's own `dlr_psse_writer` role to a throwaway local
Postgres that carries the Phase 4 migrations and the reference DDL
(docs/data-science/schema/psse_results_v1.sql). The tests show that one call writes a run and
all its result rows together, that any failure leaves no result rows and a failed record,
that a retry never duplicates or overwrites, and that no secret reaches an error.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's
tmp dir and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway
database (host 127.0.0.1, localhost or ::1; anything else fails the test). With
`PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping. They
never touch Supabase. Every planted secret is assembled from pieces so
backend/tests/secret_scan_test.py never matches this file.

Follows backend/tests/psse_schema_pg_test.py (module-level imports, plain asserts, no test
classes, no network).
"""

import datetime
import urllib.parse

import pytest

import psse_fakes
import psse_local_pg as pg_helper
from psse_job import constants, contract, ratings, run_record, writer

WRITER_ROLE = "dlr_psse_writer"
STARTED = datetime.datetime(2026, 10, 28, 14, 7, 30, tzinfo=datetime.timezone.utc)
FINISHED = STARTED + datetime.timedelta(seconds=90)
NOW = STARTED


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


def _context(n=1, started=STARTED):
    return contract.RunContext(
        run_id=pg_helper.make_run_id(n, started),
        started_at=started,
        case_id="summer_peak_case",
        case_sha256="ab" * 32,
        mapping_sha256="cd" * 32,
        job_version="abc1234",
    )


def _selection(provisional=True, age_minutes=10.0):
    rows = psse_fakes.latest_rows(NOW, provisional=provisional, age_minutes=age_minutes)
    return ratings.select_ratings(psse_fakes.fake_fetch(rows), NOW)


def _built(n=1, selection=None, results=None):
    """(record, rows, results) of one completed run built from today's selection."""
    selection = _selection() if selection is None else selection
    results = psse_fakes.fake_results(selection) if results is None else results
    record = run_record.build_run_record(_context(n), selection, FINISHED, results=results)
    return record, run_record.result_rows(record, results), results


def _connect(admin_url):
    return writer.connect(pg_helper.role_url(admin_url, WRITER_ROLE))


def _counts(admin_url, run_id):
    """(psse_run, dispatch, margin, contingency) row counts for `run_id`, read as the superuser."""
    return [
        pg_helper.admin_rows(
            admin_url, "select count(*) as n from public." + table + " where run_id = %s", (run_id,)
        )[0]["n"]
        for table in pg_helper.RESULT_TABLES
    ]


def _run_row(admin_url, run_id):
    rows = pg_helper.admin_rows(admin_url, "select * from public.psse_run where run_id = %s", (run_id,))
    return rows[0] if rows else None


def _checks(admin_url):
    return pg_helper.admin_rows(admin_url, pg_helper._read(pg_helper.CHECKS_SQL))


def test_tracer_write_one_fallback_run_round_trip(clean_pg):
    """One fallback run built from today's provisional selection is written whole as dlr_psse_writer."""
    record, rows, _ = _built()
    assert record["outcome"] == "fallback"
    assert [len(rows[table]) for table in contract.RESULT_TABLES] == [4, 4, 2]
    assert all(row["run_id"] == record["run_id"] and row["run_outcome"] == "fallback"
               for table in contract.RESULT_TABLES for row in rows[table])

    conn = _connect(clean_pg)
    try:
        assert writer.write_run(conn, record, rows) == "written"
    finally:
        conn.close()

    assert _counts(clean_pg, record["run_id"]) == [1, 4, 4, 2]
    stored = pg_helper.admin_rows(
        clean_pg,
        "select outcome, ratings_used -> 'AUSTIN' ->> 'fallback_reason' as reason from public.psse_run where run_id = %s",
        (record["run_id"],),
    )[0]
    assert stored["outcome"] == "fallback"
    assert stored["reason"] == "provisional"
    problems = [row for row in _checks(clean_pg) if not row["ok"]]
    assert problems == [], problems


# --------------------------------------------------------------------------- helpers

class _FailOnNth(object):
    """
    Wraps a real writer connection: delegates everything (including `transaction()`), counts
    `execute` calls and raises RuntimeError exactly once, on call number `n`.
    """

    def __init__(self, conn, n, message=None):
        self._conn = conn
        self.n = n
        self.message = message
        self.calls = 0

    def transaction(self, *args, **kwargs):
        return self._conn.transaction(*args, **kwargs)

    def execute(self, *args, **kwargs):
        self.calls += 1
        if self.calls == self.n:
            raise RuntimeError(self.message or "injected failure at statement %s" % self.n)
        return self._conn.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)


class _ForbiddenConnection(object):
    """A connection that fails the test when anything is executed on it."""

    def execute(self, *args, **kwargs):
        raise AssertionError("nothing may be executed")

    def transaction(self, *args, **kwargs):
        raise AssertionError("no transaction may be opened")


def _assert_failed_and_empty(admin_url, run_id):
    """Zero result rows, exactly one psse_run row: failed, stage 'write'; returns that row."""
    assert _counts(admin_url, run_id) == [1, 0, 0, 0]
    stored = _run_row(admin_url, run_id)
    assert stored["outcome"] == "failed"
    assert stored["failed_stage"] == "write"
    assert stored["error"].startswith("result write failed: ")
    return stored


# --------------------------------------------------------------------------- atomic

@pytest.mark.parametrize("n", [1, 2, 6, "last"])
def test_atomic_failure_on_nth_statement_leaves_no_results(clean_pg, n):
    """A failure injected on the 1st, 2nd, 6th or last statement leaves no result row, one failed record."""
    record, rows, _ = _built(n=10)
    total = 1 + sum(len(rows[table]) for table in contract.RESULT_TABLES)
    assert total == 11
    position = total if n == "last" else n
    conn = _connect(clean_pg)
    try:
        proxy = _FailOnNth(conn, position)
        with pytest.raises(writer.WriteFailed) as caught:
            writer.write_run(proxy, record, rows)
    finally:
        conn.close()
    assert "injected failure at statement %s" % position in str(caught.value)
    stored = _assert_failed_and_empty(clean_pg, record["run_id"])
    assert "injected failure at statement %s" % position in stored["error"]
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []


def test_atomic_duplicate_result_key_rolls_back_and_records_failed(clean_pg):
    """Two contingency rows with one primary key abort the write; a failed record names the duplicate."""
    record, rows, _ = _built(n=11)
    rows[contract.CONTINGENCY_TABLE] = rows[contract.CONTINGENCY_TABLE] + rows[contract.CONTINGENCY_TABLE]
    conn = _connect(clean_pg)
    try:
        with pytest.raises(writer.WriteFailed):
            writer.write_run(conn, record, rows)
    finally:
        conn.close()
    stored = _assert_failed_and_empty(clean_pg, record["run_id"])
    assert "duplicate key" in stored["error"]


# --------------------------------------------------------------------------- idempotent

def test_idempotent_same_run_id_twice(clean_pg):
    """The same run written twice leaves exactly one row set."""
    record, rows, _ = _built(n=12)
    conn = _connect(clean_pg)
    try:
        assert writer.write_run(conn, record, rows) == "written"
        assert writer.write_run(conn, record, rows) == "already_recorded"
    finally:
        conn.close()
    assert _counts(clean_pg, record["run_id"]) == [1, 4, 4, 2]
    assert _run_row(clean_pg, record["run_id"])["outcome"] == "fallback"


def test_idempotent_failure_record_never_overwrites_a_good_run(clean_pg):
    """A failure record for a committed run_id changes nothing: no duplicate, no overwrite."""
    record, rows, _ = _built(n=13)
    conn = _connect(clean_pg)
    try:
        assert writer.write_run(conn, record, rows) == "written"
        failed = run_record.as_failed(record, "write", "late failure")
        assert writer.record_failure(conn, failed) == "already_recorded"
    finally:
        conn.close()
    assert _counts(clean_pg, record["run_id"]) == [1, 4, 4, 2]
    stored = _run_row(clean_pg, record["run_id"])
    assert stored["outcome"] == "fallback"
    assert stored["error"] is None
    assert stored["failed_stage"] is None


# --------------------------------------------------------------------------- failed

def test_failed_record_alone_has_no_results(clean_pg):
    """record_failure writes the run row alone, with all four cities in ratings_used (ROADMAP criterion 3)."""
    selection = _selection()
    failure = contract.Failure("load_flow", "load flow did not converge")
    record = run_record.build_run_record(_context(14), selection, FINISHED, failure=failure)
    assert record["outcome"] == "failed"
    conn = _connect(clean_pg)
    try:
        assert writer.record_failure(conn, record) == "written"
    finally:
        conn.close()
    assert _counts(clean_pg, record["run_id"]) == [1, 0, 0, 0]
    stored = _run_row(clean_pg, record["run_id"])
    assert stored["outcome"] == "failed"
    assert stored["failed_stage"] == "load_flow"
    assert stored["error"] == "load flow did not converge"
    assert stored["started_at"] == STARTED and stored["finished_at"] == FINISHED
    assert stored["case_id"] == "summer_peak_case"
    assert sorted(stored["ratings_used"]) == sorted(constants.CITIES)
    assert stored["ratings_used"]["AUSTIN"]["source"] == "static_fallback"
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []


def test_failed_record_unreachable_database_raises_record_failed(clean_pg):
    """With a closed connection not even the failure record is written: RecordFailed, no row at all."""
    record, rows, _ = _built(n=15)
    conn = _connect(clean_pg)
    conn.close()
    with pytest.raises(writer.RecordFailed) as caught:
        writer.write_run(conn, record, rows)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert _counts(clean_pg, record["run_id"]) == [0, 0, 0, 0]


def test_failed_outcome_is_refused_by_write_run():
    """write_run takes ok or fallback records only; a failed one raises ValueError and writes nothing."""
    selection = _selection()
    failure = contract.Failure("load_flow", "x")
    record = run_record.build_run_record(_context(16), selection, FINISHED, failure=failure)
    with pytest.raises(ValueError):
        writer.write_run(_ForbiddenConnection(), record, {})
    ok_record, _, _ = _built(n=17)
    with pytest.raises(ValueError):
        writer.record_failure(_ForbiddenConnection(), ok_record)


# --------------------------------------------------------------------------- redact

def _require_driver():
    """psycopg imports; with PSSE_REQUIRE_PG=1 a missing driver is a failure, not a skip."""
    try:
        import psycopg  # noqa: F401
    except ImportError:
        pg_helper._skip("psycopg is not installed")


def test_redact_connect_failure_carries_no_url_or_identity():
    """A refused connection raises WriteFailed, not chained, with none of the URL's parts in it."""
    _require_driver()
    user = "dlr_psse_writer." + "abcdefghij" + "klmnopqrst"
    reference = user.split(".", 1)[1]
    password_raw = "p/ss:w@rd" + "#9?x"
    password_encoded = urllib.parse.quote(password_raw, safe="")
    host = "127.0.0" + ".1"
    url = "postgresql" + "://" + user + ":" + password_encoded + "@" + host + ":1/postgres"
    with pytest.raises(writer.WriteFailed) as caught:
        writer.connect(url, env={})
    exc = caught.value
    assert exc.__cause__ is None and exc.__context__ is None
    message = str(exc)
    assert message.startswith("database connection failed: ")
    for secret in (url, password_raw, password_encoded, user, reference, host):
        assert secret not in message
    assert len(message) <= len("database connection failed: ") + constants.LOG_MAX_CHARS

    with pytest.raises(writer.WriteFailed) as missing:
        writer.connect(None, env={})
    assert constants.ENV_PSSE_DB_URL in str(missing.value)
    with pytest.raises(writer.WriteFailed):
        writer.connect("   ", env={})


def test_redact_write_failure_message(clean_pg):
    """A planted URL and password pair in a failure text reach neither the exception nor psse_run.error."""
    secret = "hunter2" + "hunter2"
    url = "postgresql" + "://" + "someone" + ":" + secret + "@" + "db.example.invalid" + ":5432/postgres"
    pair = "pass" + "word=" + secret
    planted = "boom " + url + " " + pair + " " + ("tail " * 400)
    record, rows, _ = _built(n=18)
    conn = _connect(clean_pg)
    try:
        proxy = _FailOnNth(conn, 2, message=planted)
        with pytest.raises(writer.WriteFailed) as caught:
            writer.write_run(proxy, record, rows)
    finally:
        conn.close()
    message = str(caught.value)
    assert secret not in message and "db.example.invalid" not in message
    assert len(message) <= constants.ERROR_MAX_CHARS
    stored = _assert_failed_and_empty(clean_pg, record["run_id"])
    assert secret not in stored["error"] and "db.example.invalid" not in stored["error"]
    assert len(stored["error"]) <= constants.ERROR_MAX_CHARS
