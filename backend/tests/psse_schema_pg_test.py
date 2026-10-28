"""
Local-Postgres proofs of the reference DDL for the PSS/E result tables
(pss-e-integration Phase 1, DBX-01, WB-01, WB-02).

The reference DDL (docs/data-science/schema/psse_results_v1.sql) is applied, after the two
Phase 4 migrations, to a throwaway local Postgres that carries Supabase's legacy default
grants. The tests connect as the DDL's own `dlr_psse_writer` role and show what it can and
cannot do.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's
tmp dir and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local
throwaway database (host 127.0.0.1, localhost or ::1; anything else fails the test). With
`PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping. They
never touch Supabase.

Follows backend/tests/supabase_live_test.py's conventions (module-level imports, plain
asserts, no test classes, no network).
"""

from datetime import datetime, timezone

import pytest

import psse_local_pg as pg_helper

WRITER = "dlr_psse_writer"
STARTED = datetime(2026, 10, 28, 14, 7, 30, tzinfo=timezone.utc)


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


def _writer(admin_url, time_zone=None):
    """An autocommit connection as dlr_psse_writer (trust auth, no credential locally)."""
    import psycopg

    conn = psycopg.connect(pg_helper.role_url(admin_url, WRITER), autocommit=True)
    if time_zone:
        conn.execute("set time zone '" + time_zone + "'")
    return conn


def test_ddl_round_trip_one_complete_run(clean_pg):
    """One transaction writes a run plus 4 + 4 + 2 result rows; the same role reads them back."""
    run_id = pg_helper.make_run_id(1, STARTED)
    rows = pg_helper.valid_run_rows(run_id, STARTED, outcome="fallback", violations=2)
    with _writer(clean_pg) as conn:
        with conn.transaction():
            for table in pg_helper.RESULT_TABLES:
                pg_helper.insert_rows(conn, table, rows[table])
        counts = [
            conn.execute("select count(*) from public." + table + " where run_id = %s", (run_id,)).fetchone()[0]
            for table in pg_helper.RESULT_TABLES
        ]
        run = conn.execute(
            "select outcome, slot_time, started_at from public.psse_run where run_id = %s", (run_id,)
        ).fetchone()
    assert counts == [1, 4, 4, 2]
    assert run[0] == "fallback"
    assert run[1] == datetime(2026, 10, 28, 14, 0, 0, tzinfo=timezone.utc)
    assert run[2] == STARTED
