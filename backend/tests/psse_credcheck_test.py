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
import io
import json
import os
import sys

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_local_pg as pg_helper  # noqa: E402
from psse_job import credcheck, writer  # noqa: E402

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
