"""
End-to-end proofs of one whole PSS/E job run (pss-e-integration Phase 1: IN-01, WB-01, WB-02,
D-02, D-04).

`psse_job.job.run_once` reads the ratings, runs an injected fake study, validates the results
and records the run exactly once, at the end, through the atomic writer. The tracer goes from
an HTTP read (FakeLatestRatingServer) through a fake study to rows in a throwaway local
Postgres; the rest prove that every way a run can fail still leaves exactly one honest record
(or an explicit exit 3 when nothing could be recorded) and that nothing is written early.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's
tmp dir and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway
database (host 127.0.0.1, localhost or ::1; anything else fails the test). With
`PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping. They
never touch Supabase. Every planted secret is assembled from pieces so
backend/tests/secret_scan_test.py never matches this file.

Follows backend/tests/psse_writer_test.py (module-level imports, plain asserts, no test
classes).
"""

import copy
import datetime
import functools
import logging
import urllib.parse

import pytest

import psse_fakes
import psse_local_pg as pg_helper
from psse_job import constants, contract, job, ratings, writer

WRITER_ROLE = "dlr_psse_writer"
STARTED = datetime.datetime(2026, 10, 28, 14, 7, 30, tzinfo=datetime.timezone.utc)
CASE_PATH = "C:\\cases\\ercot_2026.sav"


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


def _clock(*offsets):
    """A clock returning STARTED plus each offset (a timedelta) in turn, then the last one again."""
    values = [STARTED + offset for offset in offsets]
    state = {"i": 0}

    def clock():
        value = values[min(state["i"], len(values) - 1)]
        state["i"] += 1
        return value

    return clock


def _connect(admin_url):
    return functools.partial(writer.connect, pg_helper.role_url(admin_url, WRITER_ROLE))


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


def test_tracer_run_once_http_to_postgres(clean_pg):
    """HTTP read of today's provisional ratings, a fake study, one complete fallback run in Postgres."""
    rows = psse_fakes.latest_rows(STARTED, provisional=True)
    key = psse_fakes.fake_publishable_key()
    study = psse_fakes.FakeStudy()
    with psse_fakes.FakeLatestRatingServer(rows=rows, key=key) as server:
        env = {constants.ENV_SUPABASE_URL: server.url, constants.ENV_PUBLISHABLE_KEY: key}
        outcome = job.run_once(
            fetch=functools.partial(ratings.fetch_latest_rating, env=env),
            study=study,
            connect=_connect(clean_pg),
            case_id=CASE_PATH,
            clock=_clock(datetime.timedelta(0), datetime.timedelta(minutes=3)),
        )
        assert len(server.requests) == 1

    assert outcome.outcome == "fallback"
    assert outcome.status == "written"
    assert outcome.failed_stage is None
    assert outcome.exit_code == 0

    assert len(study.calls) == 1
    selection, context = study.calls[0]
    assert [selection.choices[city].source for city in constants.CITIES] == ["static_fallback"] * 4
    assert [selection.choices[city].fallback_reason for city in constants.CITIES] == ["provisional"] * 4
    assert context.run_id == outcome.run_id

    assert _counts(clean_pg, outcome.run_id) == [1, 4, 4, 2]
    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["case_id"] == "ercot_2026.sav"
    assert stored["outcome"] == "fallback"
    assert stored["finished_at"] - stored["started_at"] == datetime.timedelta(minutes=3)
    problems = [row for row in _checks(clean_pg) if not row["ok"]]
    assert problems == [], problems
