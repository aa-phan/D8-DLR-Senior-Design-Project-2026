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
import json

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
