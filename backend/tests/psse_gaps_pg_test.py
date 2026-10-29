"""
SCH-02 gap-check proofs on a throwaway local Postgres (pss-e-integration Phase 3, plan 03-02):
`docs/data-science/schema/psse_run_gaps.sql` lists every UTC hour between the first recorded
run and the last closed hour that has no complete result set, and `psse_job.gaps.run` runs that
file as the writer credential on a read-only session and prints it.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's tmp
dir and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway
database (host 127.0.0.1, localhost or ::1; anything else fails the test). With
`PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping. They never
touch Supabase.

Honest scope: these tests prove the statement's logic and the wrapper on local Postgres. They do
not prove that the live table shows the real laptop's hours, that the laptop clock agrees with
the database, or daylight-saving effects (the statement works in UTC only); those are the
laptop session's induced-gap step and stay UNVERIFIED until then.

Follows backend/tests/psse_study_job_test.py (module-level imports, plain asserts, no classes).
"""

import datetime
import io
import os
import sys

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_local_pg as pg_helper  # noqa: E402
from psse_job import gaps, writer  # noqa: E402

WRITER_ROLE = "dlr_psse_writer"
HOUR = datetime.timedelta(hours=1)
UTC = datetime.timezone.utc


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


def _current_slot(admin_url):
    """The database's own current UTC hour, as an aware datetime."""
    rows = pg_helper.admin_rows(
        admin_url, "select (date_trunc('hour', now() at time zone 'UTC') at time zone 'UTC') as slot")
    return rows[0]["slot"].astimezone(UTC)


def _put(admin_conn, slot, outcome, n):
    """Insert one psse_run row started 15 minutes into `slot` (run row only, no result rows)."""
    started = slot + datetime.timedelta(minutes=15)
    run_id = pg_helper.make_run_id(n, started)
    if outcome == "failed":
        row = pg_helper.failed_run_row(run_id, started)
    else:
        row = pg_helper.valid_run_rows(run_id, started, outcome=outcome)["psse_run"][0]
    pg_helper.insert_rows(admin_conn, "psse_run", [row])


def _seed(admin_url, plan):
    """Insert `plan`, a list of (slot, outcome) pairs, as the superuser; run ids are unique."""
    import psycopg

    with psycopg.connect(admin_url, autocommit=True) as conn:
        for n, (slot, outcome) in enumerate(plan):
            _put(conn, slot, outcome, n + 1)


def _writer_url(admin_url):
    return pg_helper.role_url(admin_url, WRITER_ROLE)


def _env(admin_url):
    return {"SUPABASE_PSSE_DB_URL": _writer_url(admin_url)}


def _stable(admin_url, trial):
    """
    Reset the tables, read the current slot, run `trial(slot)` (which must return values, not
    assert) and accept the result only when the database's hour did not roll meanwhile; up to
    three attempts, then fail.
    """
    for _ in range(3):
        pg_helper.reset(admin_url)
        before = _current_slot(admin_url)
        result = trial(before)
        if _current_slot(admin_url) == before:
            return before, result
    pytest.fail("the database's UTC hour rolled during all three attempts")


def _iso(value):
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch(admin_url):
    conn = writer.connect(_writer_url(admin_url))
    try:
        return gaps.fetch_gaps(conn)
    finally:
        conn.close()


def test_tracer_gap_check_lists_the_missing_hours(clean_pg):
    def trial(s):
        _seed(clean_pg, [
            (s - 6 * HOUR, "fallback"),
            (s - 5 * HOUR, "fallback"), (s - 5 * HOUR, "ok"),
            (s - 3 * HOUR, "failed"),
            (s - 2 * HOUR, "failed"), (s - 2 * HOUR, "fallback"),
            (s, "fallback"),
        ])
        buffer = io.StringIO()
        code = gaps.run(_env(clean_pg), out=buffer)
        strict = gaps.run(_env(clean_pg), fail_on_gaps=True, out=io.StringIO())
        return code, strict, buffer.getvalue(), _fetch(clean_pg)

    s, (code, strict, text, rows) = _stable(clean_pg, trial)
    assert code == 0
    assert strict == 5

    gap_lines = [line for line in text.splitlines() if "no_run" in line or "failed_only" in line]
    assert [(line.split()[0], line.split()[1]) for line in gap_lines] == [
        (_iso(s - 4 * HOUR), "no_run"),
        (_iso(s - 3 * HOUR), "failed_only"),
        (_iso(s - 1 * HOUR), "no_run"),
    ]
    assert all(line.split()[0].endswith("Z") for line in gap_lines)
    assert "7 runs recorded" in text
    assert _iso(s - 6 * HOUR) in text
    assert _iso(s) in text

    assert [(r.slot_time.astimezone(UTC), r.gap_kind, r.runs, r.failed_runs) for r in rows] == [
        (s - 4 * HOUR, "no_run", 0, 0),
        (s - 3 * HOUR, "failed_only", 1, 1),
        (s - 1 * HOUR, "no_run", 0, 0),
    ]
