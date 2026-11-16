"""
public.latest_grid_study (supabase/migrations/20261116200000_expose_latest_grid_study.sql): the
newest complete grid-study run per city, readable with the dashboard's key while the four psse_*
result tables stay private.

The text tests always run. The database tests need a local Postgres (DLR_TEST_PG_AUTOSTART=1 or
DLR_TEST_DATABASE_URL), like the other migration tests.
"""

import contextlib
import math
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

import grid_study_contract as contract
import local_pg

_MIGRATION = os.path.join(local_pg.MIGRATIONS_DIR, "20261116200000_expose_latest_grid_study.sql")
_CITIES = ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")
_SQRT3 = math.sqrt(3.0)


# --------------------------------------------------------------------------------------------------
# text
# --------------------------------------------------------------------------------------------------

def _text():
    with open(_MIGRATION, encoding="utf-8") as handle:
        return handle.read()


def test_text_the_view_runs_with_owner_rights_and_grants_select_only():
    text = _text()
    assert "create or replace view public.latest_grid_study with (security_invoker = false) as" in text
    assert "revoke all on public.latest_grid_study from public, anon, authenticated;" in text
    assert "grant select on public.latest_grid_study to anon, authenticated;" in text
    # No statement grants anything on the private tables.
    for statement in re.findall(r"(?im)^\s*grant [^;]*;", text):
        assert "psse_" not in statement, statement


def test_text_no_forbidden_field_is_selected():
    # The published select list: from the outer select to "from newest_run" (the join may use run_id).
    view = _text().split("create or replace view", 1)[1].split(";", 1)[0]
    select = view.split("\nselect\n", 1)[1].split("\nfrom newest_run", 1)[0]
    assert "'psse'::text as solver" in select
    for name in contract.FORBIDDEN:
        assert not re.search(r"\b[dn]\.%s\b" % re.escape(name), select), name


def test_text_every_contract_column_has_a_comment():
    text = _text()
    for name in contract.COLUMNS:
        assert "comment on column public.latest_grid_study.%s is '" % name in text, name
    assert "comment on view public.latest_grid_study is '" in text


# --------------------------------------------------------------------------------------------------
# database
# --------------------------------------------------------------------------------------------------

@contextlib.contextmanager
def _session(url, role=None):
    """A connection that is always rolled back; optionally acting as `role`."""
    import psycopg
    from psycopg import sql

    conn = psycopg.connect(url)
    try:
        conn.execute("set timezone = 'UTC'")
        if role:
            conn.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    local_pg.require_local_pg()
    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url)
        yield url


def _run_id(started_at, suffix):
    return "psse-%sZ-%s" % (started_at.strftime("%Y%m%dT%H%M%S"), suffix)


def _insert_run(conn, started_at, outcome, suffix, voltage_limit_mva=900.0):
    """One run row and, unless it failed, four dispatched-capacity rows that satisfy every identity
    constraint of the table. Returns the run id."""
    from psycopg.types.json import Jsonb

    run_id = _run_id(started_at, suffix)
    slot_time = started_at.replace(minute=0, second=0, microsecond=0)
    failed = outcome == "failed"
    conn.execute(
        "insert into public.psse_run (run_id, slot_time, started_at, finished_at, outcome, failed_stage, error, "
        "case_id, ratings_used, n_contingencies, n_contingencies_with_results, job_version) values "
        "(%s, %s, %s, %s, %s, %s, %s, 'ieee39', %s, %s, %s, 'test')",
        (run_id, slot_time, started_at, started_at + timedelta(seconds=2), outcome,
         "load_case" if failed else None, "test" if failed else None,
         Jsonb({city: {} for city in _CITIES}), None if failed else 32, None if failed else 32))
    if failed:
        return run_id
    per_conductor, subconductors, kv, power_factor = 1000.0, 2, 345.0, 0.95
    circuit = per_conductor * subconductors
    applied_mva = _SQRT3 * kv * circuit / 1000
    for index, city in enumerate(_CITIES):
        limit = voltage_limit_mva + 500 * index  # city 0 voltage-limited, the rest rating-limited
        dispatched_mva = min(applied_mva, limit)
        dispatched_circuit = dispatched_mva * 1000 / (_SQRT3 * kv)
        live = outcome == "ok"
        conn.execute(
            "insert into public.psse_dispatched_capacity (run_id, run_outcome, city, rating_source, "
            "fallback_reason, city_rating_valid_time, city_rating_computed_at, applied_amps_per_conductor, "
            "subconductors_per_phase, applied_amps_circuit, line_voltage_kv, applied_mva, voltage_limit_mva, "
            "dispatched_mva, dispatched_amps_circuit, dispatched_amps_per_conductor, power_factor, dispatched_mw, "
            "limiting_factor, details) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, %s, %s)",
            (run_id, outcome, city, "city_rating" if live else "static_fallback", None if live else "stale",
             slot_time if live else None, slot_time if live else None, per_conductor, subconductors, circuit, kv,
             applied_mva, limit, dispatched_mva, dispatched_circuit, dispatched_circuit / subconductors,
             power_factor, dispatched_mva * power_factor,
             "dlr_rating" if applied_mva <= limit else "voltage_stability", Jsonb({"note": "test"})))
    return run_id


def _rows(conn):
    cur = conn.execute("select * from public.latest_grid_study")
    names = [d.name for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _now_hour(conn):
    return conn.execute("select date_trunc('hour', now())").fetchone()[0]


def test_the_view_columns_equal_the_contract(pg_url):
    with _session(pg_url) as conn:
        names = [r[0] for r in conn.execute(
            "select a.attname from pg_attribute a where a.attrelid = 'public.latest_grid_study'::regclass "
            "and a.attnum > 0 and not a.attisdropped order by a.attnum").fetchall()]
    assert tuple(names) == contract.COLUMNS
    assert not set(names) & set(contract.FORBIDDEN)


def test_an_empty_table_gives_no_rows(pg_url):
    with _session(pg_url, "anon") as conn:
        assert _rows(conn) == []


def test_the_newest_complete_run_wins_and_a_later_failed_run_is_skipped(pg_url):
    with _session(pg_url) as conn:
        hour = _now_hour(conn)
        _insert_run(conn, hour - timedelta(hours=3) + timedelta(minutes=15), "ok", "00000001")
        newest = _insert_run(conn, hour - timedelta(hours=2) + timedelta(minutes=15), "fallback", "00000002")
        _insert_run(conn, hour - timedelta(hours=1) + timedelta(minutes=15), "failed", "00000003")
        conn.execute("set role anon")
        rows = _rows(conn)
        assert sorted(r["city"] for r in rows) == sorted(_CITIES)
        assert {r["slot_time"] for r in rows} == {hour - timedelta(hours=2)}
        assert {r["run_outcome"] for r in rows} == {"fallback"}
        assert {r["solver"] for r in rows} == {"psse"}
        assert all(r["rating_source"] == "static_fallback" and r["fallback_reason"] == "stale" for r in rows)
        assert newest  # the run id itself is never published
        assert "run_id" not in rows[0]


def test_two_runs_in_one_hour_the_later_finish_wins(pg_url):
    with _session(pg_url) as conn:
        hour = _now_hour(conn)
        _insert_run(conn, hour - timedelta(hours=1) + timedelta(minutes=10), "ok", "0000000a", voltage_limit_mva=800)
        _insert_run(conn, hour - timedelta(hours=1) + timedelta(minutes=15), "ok", "0000000b", voltage_limit_mva=700)
        rows = {r["city"]: r for r in _rows(conn)}
        assert len(rows) == 4
        assert rows["AUSTIN"]["voltage_limit_mva"] == pytest.approx(700)


def test_usable_pct_limiting_factor_age_and_stale(pg_url):
    with _session(pg_url) as conn:
        hour = _now_hour(conn)
        _insert_run(conn, hour + timedelta(minutes=0, seconds=1), "ok", "000000aa")
        now = conn.execute("select now()").fetchone()[0]
        rows = {r["city"]: r for r in _rows(conn)}
        austin, el_paso = rows["AUSTIN"], rows["EL_PASO"]
        assert austin["limiting_factor"] == "voltage_stability"
        assert austin["usable_pct"] == pytest.approx(900 / austin["applied_mva"] * 100)
        assert austin["dispatched_amps_per_conductor"] < austin["applied_amps_per_conductor"]
        assert el_paso["limiting_factor"] == "dlr_rating" and el_paso["usable_pct"] == pytest.approx(100)
        assert austin["city_rating_valid_time"] == hour
        for row in rows.values():
            assert row["is_stale"] is False
            assert row["age_minutes"] == math.ceil((now - hour).total_seconds() / 60)
        conn.execute("delete from public.psse_dispatched_capacity")
        conn.execute("delete from public.psse_run")
        _insert_run(conn, hour - timedelta(hours=2) + timedelta(minutes=15), "ok", "000000bb")
        for row in _rows(conn):
            assert row["is_stale"] is True and row["age_minutes"] > contract.STALE_AFTER_MINUTES


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_the_public_roles_read_the_view_but_not_the_tables(pg_url, role):
    from psycopg import errors

    for table in ("psse_run", "psse_dispatched_capacity", "psse_voltage_margin", "psse_contingency_result"):
        with _session(pg_url, role) as conn:
            with pytest.raises(errors.InsufficientPrivilege):
                conn.execute("select 1 from public.%s limit 1" % table)
    with _session(pg_url, role) as conn:
        conn.execute("select * from public.latest_grid_study").fetchall()


@pytest.mark.parametrize("statement", [
    "insert into public.latest_grid_study (city) values ('AUSTIN')",
    "update public.latest_grid_study set city = 'AUSTIN'",
    "delete from public.latest_grid_study",
])
def test_the_public_roles_cannot_write_through_the_view(pg_url, statement):
    from psycopg import errors

    # Refused either way: anon holds only SELECT, and a view with WITH is not updatable at all.
    with _session(pg_url, "anon") as conn:
        with pytest.raises((errors.InsufficientPrivilege, errors.ObjectNotInPrerequisiteState)):
            conn.execute(statement)
    with _session(pg_url) as conn:
        assert conn.execute("select has_table_privilege('anon', 'public.latest_grid_study', 'insert, update, delete')"
                            ).fetchone()[0] is False


def test_the_migration_reapplies_cleanly(pg_url):
    import psycopg

    def snapshot(conn):
        definition = conn.execute("select pg_get_viewdef('public.latest_grid_study'::regclass)").fetchone()[0]
        acl = conn.execute("select relacl::text from pg_class where oid = 'public.latest_grid_study'::regclass"
                           ).fetchone()[0]
        return definition, acl

    with _session(pg_url) as conn:
        before = snapshot(conn)
    for _ in range(2):
        with psycopg.connect(pg_url) as conn:
            conn.execute(_text())
    with _session(pg_url) as conn:
        assert snapshot(conn) == before
