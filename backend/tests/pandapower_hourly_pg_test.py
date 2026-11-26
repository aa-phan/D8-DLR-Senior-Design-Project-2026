"""
OPS-03 database tier of the hourly runner (pandapower-solver Phase 5, plan 05-04): the `run` command
of `pandapower_job.hourly` against a throwaway local Postgres that has the Phase 3 schema (the
Phase 4 migrations, the reference DDL and the solver-tag migration) and the writer role's real
grants.

What is proven here: with a writer URL present in the environment, a dry `run` leaves the four result
tables unchanged (per-table count and an md5 fingerprint of every row) while any call to
`writer.connect` or `psycopg.connect` fails the test; the same inputs made live add exactly one run
row set stored with solver `pandapower`, the installed pandapower version and a `pp-` run id, so
"unchanged" is shown able to fail. Further tests, added in the same file, cover the refusals as they
are stored, the `soak` command on Postgres and the owner's size query.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's tmp dir and
stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway database (host
127.0.0.1, localhost or ::1; anything else fails the test). With `PSSE_REQUIRE_PG=1` a missing
database, driver or binary fails instead of skipping. Nothing here touches Supabase: the ratings come
from a fake fetch, the writer role is the local cluster's own, and no live host is named in this file.

Honest scope: the throwaway database has the Phase 3 schema and the writer role's real grants, but it
is not the live project. The study is the real four-city pandapower study on the public 39-bus
fixture; this file does not prove engineering agreement with PSS/E.

Synthetic data only; nothing here reads `data/private`. No test asserts a file mode or pins file
bytes (Windows). Follows backend/tests/pandapower_study_job_test.py (module-level imports, plain
asserts, no test classes).
"""

import io
import os
import re
import sys
import tempfile

import pytest

pandapower = pytest.importorskip("pandapower")

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import pandapower_hourly_fixture as fixture  # noqa: E402
import psse_local_pg as pg_helper  # noqa: E402
import psycopg  # noqa: E402
from pandapower_job import engine, hourly  # noqa: E402
from psse_job import constants, run_record, writer  # noqa: E402

WRITER_ROLE = "dlr_psse_writer"
SOLVER_VERSION = pandapower.__version__


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a database with the Phase 4 migrations, the reference DDL and the solver-tag migration."""
    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_solver_schema(admin_url)
        yield admin_url


@pytest.fixture
def clean_pg(pg):
    """The same database with the four result tables empty."""
    pg_helper.reset(pg)
    return pg


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _vocabulary_ok(lines):
    return all(any(pattern.match(line) for pattern in hourly.HOURLY_LINE_PATTERNS) for line in lines)


def _clock():
    return lambda: fixture.FIXED_NOW


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


def _fingerprint(admin_url):
    """{table: (row count, md5 of every row's text in text order)} for the four result tables, read as
    the superuser. The table names come from `pg_helper.RESULT_TABLES`, never from input."""
    result = {}
    for table in pg_helper.RESULT_TABLES:
        row = pg_helper.admin_rows(
            admin_url,
            "select count(*) as n, md5(coalesce(string_agg(t::text, '|' order by t::text), '')) as h "
            "from public." + table + " t")[0]
        result[table] = (row["n"], row["h"])
    return result


def _seeded_fingerprint(admin_url, run_ids):
    """The same fingerprint restricted to the rows of `run_ids` (so a seeded run can be shown intact
    after another run was added)."""
    result = {}
    for table in pg_helper.RESULT_TABLES:
        row = pg_helper.admin_rows(
            admin_url,
            "select count(*) as n, md5(coalesce(string_agg(t::text, '|' order by t::text), '')) as h "
            "from public." + table + " t where run_id = any(%s)", (list(run_ids),))[0]
        result[table] = (row["n"], row["h"])
    return result


def _insert_run_set(conn, rows):
    for table in pg_helper.RESULT_TABLES:
        pg_helper.insert_rows(conn, table, rows[table])


def _pandapower_rows(run_id, started_at, outcome="fallback"):
    """One complete run set tagged pandapower: the helper's rows with the run row's solver, solver
    version and no PSS/E version."""
    rows = pg_helper.valid_run_rows(run_id, started_at, outcome=outcome)
    rows["psse_run"][0].update(solver="pandapower", solver_version=SOLVER_VERSION, psse_version=None)
    return rows


def _seed(admin_url):
    """One PSS/E run and one pandapower run, written through an admin connection. Returns their ids."""
    psse_start = fixture.FIXED_NOW.replace(hour=7, minute=5)
    pp_start = fixture.FIXED_NOW.replace(hour=8, minute=6)
    psse_id = pg_helper.make_run_id(1, psse_start, prefix="psse")
    pp_id = pg_helper.make_run_id(2, pp_start, prefix="pp")
    with psycopg.connect(admin_url) as conn:
        _insert_run_set(conn, pg_helper.valid_run_rows(psse_id, psse_start))
        _insert_run_set(conn, _pandapower_rows(pp_id, pp_start))
    return [psse_id, pp_id]


def _writer_url(admin_url):
    return pg_helper.role_url(admin_url, WRITER_ROLE)


def _writer_env(tmp_path, admin_url, **extra):
    """The hourly environment of the public fixture plus the local writer URL."""
    environ = fixture.hourly_env(tmp_path, **extra)
    environ[constants.ENV_PSSE_DB_URL] = _writer_url(admin_url)
    return environ


def _fail_connect(calls):
    def refuse(*args, **kwargs):
        calls.append(1)
        raise AssertionError("a database connection was opened by a dry run")

    return refuse


def _main(environ, command="run", **seams):
    """(exit code, printed lines) of one runner call on the real engine; every printed line is
    asserted to be in the vocabulary."""
    buffer = io.StringIO()
    options = dict(fetch=fixture.fake_fetch_for(fixture.FIXED_NOW), clock=_clock(), sink=False)
    options.update(seams)
    code = hourly.main([command] if isinstance(command, str) else list(command), out=buffer,
                       environ=environ, **options)
    lines = buffer.getvalue().splitlines()
    assert _vocabulary_ok(lines)
    return code, lines


def _rows_line(lines):
    matches = [re.match(r"rows: run=(\d+) dispatch=(\d+) margin=(\d+) contingency=(\d+)\Z", line)
               for line in lines]
    found = [match for match in matches if match]
    assert len(found) == 1, lines
    return [int(group) for group in found[0].groups()]


# --------------------------------------------------------------------------- the tracer


def test_tracer_dry_run_leaves_the_four_tables_unchanged_and_live_adds_one_tagged_set(
        clean_pg, tmp_path, monkeypatch):
    """OPS-03, D-03, D-04, D-10: a dry run with a writer URL in the environment and every connect
    made fatal changes nothing; the same inputs made live add exactly one pandapower-tagged run
    row set, so the unchanged fingerprint is shown able to fail."""
    seeded = _seed(clean_pg)
    before = _fingerprint(clean_pg)
    assert [count for count, _hash in before.values()] == [2, 8, 8, 4]
    seeded_before = _seeded_fingerprint(clean_pg, seeded)

    environ = _writer_env(tmp_path, clean_pg)
    assert hourly.decide_mode(environ) == "dry"

    calls = []
    with monkeypatch.context() as patch:
        patch.setattr(writer, "connect", _fail_connect(calls))
        patch.setattr(psycopg, "connect", _fail_connect(calls))
        dry_code, dry_lines = _main(environ)
    assert calls == []
    assert dry_code == 0
    assert dry_lines[0] == "mode: dry"
    assert dry_lines[-1] == "dry run: nothing was written to the database"
    assert "study: ok" in dry_lines
    assert _fingerprint(clean_pg) == before

    live_environ = dict(environ)
    live_environ[hourly.LIVE_VARIABLE] = "true"
    live_code, live_lines = _main(live_environ)
    assert live_code == 0
    assert live_lines[0] == "mode: live"
    assert live_lines[-1] == "run status: written"
    printed = _rows_line(live_lines)
    assert printed[:3] == [1, 4, 4]
    assert printed[3] >= 1

    after = _fingerprint(clean_pg)
    assert after != before
    for table in pg_helper.RESULT_TABLES:
        assert after[table][1] != before[table][1], table
    added = [after[table][0] - before[table][0] for table in pg_helper.RESULT_TABLES]
    assert added == printed

    new_runs = pg_helper.admin_rows(
        clean_pg, "select * from public.psse_run where not (run_id = any(%s))", (seeded,))
    assert len(new_runs) == 1
    stored = new_runs[0]
    assert stored["solver"] == "pandapower"
    assert stored["solver_version"] == SOLVER_VERSION
    assert stored["run_id"].startswith("pp-")
    assert stored["psse_version"] is None
    assert _counts(clean_pg, stored["run_id"]) == printed

    assert _seeded_fingerprint(clean_pg, seeded) == seeded_before
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []

    text = "\n".join(dry_lines + live_lines)
    assert stored["run_id"] not in text
    assert "pp-" not in text
    assert os.listdir(tempfile.gettempdir()) == []
