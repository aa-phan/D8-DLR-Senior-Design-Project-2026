"""
Database-tier proofs of the owner's export statement `supabase/ops/export_psse_runs_for_replay.sql`
(pandapower-solver Phase 4, plan 04-01: AGR-01, owner decision D-01), run on a throwaway local
Postgres.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's temp dir
and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway database (host
127.0.0.1, localhost or ::1; anything else fails the test). With `PSSE_REQUIRE_PG=1` a missing
database, driver or binary fails instead of skipping. These tests never touch Supabase, and the tests
themselves never call `pytest.skip`: only the harness's own skip path applies, so the strict flag
turns every skip into a failure.

Honest scope. They prove the statement and the importer on a local Postgres: that the file runs in a
read-only session, leaves the four tables unchanged, that a write in such a session is refused, and
that the one row it returns ingests to the seeded runs. They do not prove anything about the live
project's data (never queried from here) or its Postgres version. The tests run each proof on two
schemas, the one before the solver-tag migration and the one after it, because the live project may be
on either.

No module of the replay takes part in the connection: the tests read the file's text and execute it
directly on a psycopg connection. Follows backend/tests/psse_gaps_pg_test.py (module-scoped cluster,
plain asserts, no classes).
"""

import datetime
import math
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import pandapower_replay_fixture as fixture  # noqa: E402
import psse_local_pg  # noqa: E402
from pandapower_job import recorded  # noqa: E402

EXPORT_SQL = os.path.join(_ROOT, "supabase", "ops", "export_psse_runs_for_replay.sql")
UTC = datetime.timezone.utc
HOUR_ONE = datetime.datetime(2026, 11, 18, 9, 7, 30, tzinfo=UTC)
HOUR_TWO = datetime.datetime(2026, 11, 18, 10, 7, 30, tzinfo=UTC)
HOUR_THREE = datetime.datetime(2026, 11, 18, 11, 7, 30, tzinfo=UTC)
HOUR_FOUR = datetime.datetime(2026, 11, 18, 12, 7, 30, tzinfo=UTC)
FIXED_NOW = datetime.datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)

# The tables in insert order (the run row first: the composite foreign key needs it).
_BUNDLE_TABLES = (
    ("psse_run", "run"), ("psse_dispatched_capacity", "dispatch"),
    ("psse_voltage_margin", "margins"), ("psse_contingency_result", "contingencies"))


@pytest.fixture(scope="module", params=("before_solver_tag", "after_solver_tag"))
def pg(request, tmp_path_factory):
    """Admin URL of a database on one of the two schemas the live project may be on."""
    with psse_local_pg.cluster(tmp_path_factory) as url:
        if request.param == "before_solver_tag":
            psse_local_pg.apply_schema(url)
        else:
            psse_local_pg.apply_solver_schema(url)
        yield url


@pytest.fixture
def clean_pg(pg):
    """The same database with the four result tables empty."""
    psse_local_pg.reset(pg)
    return pg


def _export_text():
    with open(EXPORT_SQL, encoding="utf-8") as handle:
        return handle.read()


def _seeded_bundles():
    return [
        fixture.run_bundle(1, HOUR_ONE, outcome="ok"),
        fixture.run_bundle(2, HOUR_TWO, outcome="fallback"),
        fixture.run_bundle(3, HOUR_THREE, outcome="failed"),
    ]


def _insert_bundle(conn, bundle):
    for table, key in _BUNDLE_TABLES:
        rows = [bundle[key]] if key == "run" else bundle[key]
        psse_local_pg.insert_rows(conn, table, rows)


def _seed(url):
    """Three PSS/E runs (ok, fallback, failed); on a database with the solver tag also one pandapower
    run, which the export must not return."""
    import psycopg

    bundles = _seeded_bundles()
    with psycopg.connect(url) as conn:
        for bundle in bundles:
            _insert_bundle(conn, bundle)
    has_tag = psse_local_pg.admin_rows(
        url, "select count(*) as n from information_schema.columns "
             "where table_schema = 'public' and table_name = 'psse_run' and column_name = 'solver'")[0]["n"]
    if has_tag:
        pp_id = psse_local_pg.make_run_id(4, HOUR_FOUR, prefix="pp")
        rows = psse_local_pg.valid_run_rows(pp_id, HOUR_FOUR)
        rows["psse_run"][0].update(solver="pandapower", solver_version="3.5.6")
        with psycopg.connect(url) as conn:
            for table, _ in _BUNDLE_TABLES:
                psse_local_pg.insert_rows(conn, table, rows[table])
    return bundles


def _fingerprints(url):
    """(row count, md5 of the ordered row text) of each of the four tables."""
    found = {}
    for table in psse_local_pg.RESULT_TABLES:
        row = psse_local_pg.admin_rows(
            url,
            "select count(*) as n, md5(coalesce(string_agg(t::text, '|' order by t::text), '')) as h "
            "from public." + table + " t")[0]
        found[table] = (row["n"], row["h"])
    return found


def _run_export_read_only(url):
    """The export file's text, executed on a read-only session with autocommit off: the one row as a
    dict keyed by column name. The statement is sent without parameters, so its % is literal."""
    import psycopg

    conn = psycopg.connect(url)
    try:
        conn.read_only = True
        cur = conn.execute(_export_text())
        names = [column.name for column in cur.description]
        rows = cur.fetchall()
    finally:
        conn.rollback()
        conn.close()
    assert len(rows) == 1
    return dict(zip(names, rows[0]))


def _has_pp(url):
    return psse_local_pg.admin_rows(
        url, "select count(*) as n from public.psse_run where run_id like 'pp-%'")[0]["n"] > 0


def test_db_export_runs_read_only_and_the_four_tables_are_unchanged(clean_pg):
    _seed(clean_pg)
    before = _fingerprints(clean_pg)
    extra = 1 if _has_pp(clean_pg) else 0   # the pandapower run seeded on the after-migration schema
    assert [n for n, _ in before.values()] == [3 + extra, 8 + 4 * extra, 8 + 4 * extra, 4 + 2 * extra]
    row = _run_export_read_only(clean_pg)
    assert tuple(row) == recorded.EXPORT_COLUMNS
    assert row["counts"] == {"runs": 3, "usable_runs": 2, "dispatch": 8, "margins": 8, "contingencies": 4}
    assert [len(row[name]) for name in ("runs", "dispatch", "margins", "contingencies")] == [3, 8, 8, 4]
    assert all(not run["run_id"].startswith("pp-") for run in row["runs"])
    assert _fingerprints(clean_pg) == before


def _close(seeded, found):
    if isinstance(seeded, float) and isinstance(found, (int, float)):
        return math.isclose(seeded, found, rel_tol=1e-9, abs_tol=1e-12)
    return seeded == found


def test_db_export_output_ingests_to_the_seeded_runs(clean_pg, tmp_path):
    bundles = _seed(clean_pg)
    document = _run_export_read_only(clean_pg)

    json_repo = fixture.make_repo(tmp_path / "json")
    from_json = recorded.ingest_export(
        fixture.write_export_json(os.path.join(json_repo, "data", "private", "pandapower", "incoming", "x.json"),
                                  document),
        repo_root=json_repo, now=FIXED_NOW)
    csv_repo = fixture.make_repo(tmp_path / "csv")
    from_csv = recorded.ingest_export(
        fixture.write_export_csv(os.path.join(csv_repo, "data", "private", "pandapower", "incoming", "x.csv"),
                                 document),
        repo_root=csv_repo, now=FIXED_NOW)
    assert from_csv.snapshot == from_json.snapshot

    recorded_runs = recorded.by_run(from_json.snapshot)
    assert [item.run["run_id"] for item in recorded_runs] == [b["run"]["run_id"] for b in bundles]
    assert [recorded.complete(item) for item in recorded_runs] == [True, True, False]

    for bundle, item in zip(bundles, recorded_runs):
        for column in recorded.RUN_COLUMNS:
            seeded = bundle["run"].get(column)
            if column == "slot_time":
                assert datetime.datetime.fromisoformat(item.run[column]) == seeded
            else:
                assert _close(seeded, item.run[column]), column
        for key, columns in (("dispatch", recorded.DISPATCH_COLUMNS), ("margins", recorded.MARGIN_COLUMNS),
                             ("contingencies", recorded.CONTINGENCY_COLUMNS)):
            found = getattr(item, key)
            assert len(found) == len(bundle[key])
            if key == "contingencies":
                keyed = lambda row: (row["contingency_id"], row["violation_kind"], row["element_id"])  # noqa: E731
                seeded_rows = sorted(bundle[key], key=keyed)
                found_rows = sorted(found, key=keyed)
            else:
                seeded_rows = sorted(bundle[key], key=lambda row: row["city"])
                found_rows = sorted(found, key=lambda row: row["city"])
            for seeded_row, found_row in zip(seeded_rows, found_rows):
                for column in columns:
                    assert _close(seeded_row.get(column), found_row[column]), (key, column)


def test_db_a_write_in_the_read_only_session_is_refused(clean_pg):
    import psycopg

    run = _seeded_bundles()[0]["run"]
    conn = psycopg.connect(clean_pg)
    try:
        conn.read_only = True
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction) as info:
            psse_local_pg.insert_rows(conn, "psse_run", [run])
        assert info.value.sqlstate == "25006"
    finally:
        conn.rollback()
        conn.close()
    assert psse_local_pg.admin_rows(clean_pg, "select count(*) as n from public.psse_run")[0]["n"] == 0
