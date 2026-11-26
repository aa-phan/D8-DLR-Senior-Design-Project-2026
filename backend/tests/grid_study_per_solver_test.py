"""
Proof of the per-solver replacement of public.latest_grid_study (pandapower-solver workstream, phase 6,
requirements VIEW-01 and VIEW-02; decisions D-01, D-03, D-05, D-06 and D-09).

The migration `supabase/migrations/20261126200000_latest_grid_study_per_solver.sql` replaces the view
of the solver-tag migration (PSS/E runs only) with one that returns the newest complete run of each
solver: one row per city per solver, at most 8 rows. The owner applies it to the live project only
after the Phase 5 soak passes, so these tests prove it on a throwaway local Postgres.

Two tiers:
  text tests      (`test_text_*`) run everywhere: they read the migration files.
  database tests  (`test_db_*`) apply the whole migration chain, in name order, to a throwaway local
                  Postgres through `psse_local_pg.cluster`. They are skipped unless
                  `DLR_TEST_PG_AUTOSTART=1` or a local `DLR_TEST_DATABASE_URL` is set, and FAIL under
                  `PSSE_REQUIRE_PG=1` when no database is available (a skip proves nothing about the
                  database). They never touch Supabase.
"""

import os
import re
from datetime import datetime, timedelta, timezone

import pytest

import grid_study_contract as contract
import local_pg
import psse_local_pg

_NEW_NAME = "20261126200000_latest_grid_study_per_solver.sql"
_NEW_MIGRATION = os.path.join(local_pg.MIGRATIONS_DIR, _NEW_NAME)
_SOLVER_TAG_NAME = "20261118200000_psse_run_solver_tag.sql"
_SOLVER_TAG_MIGRATION = psse_local_pg.SOLVER_TAG_MIGRATION

_VIEW = "create or replace view public.latest_grid_study "
_COLUMN_COMMENT = "comment on column public.latest_grid_study."

STARTED = datetime(2026, 10, 28, 14, 7, 30, tzinfo=timezone.utc)


# --------------------------------------------------------------------------------------------------
# helpers (copied from solver_tag_owner_check_test.py: test modules do not import each other)
# --------------------------------------------------------------------------------------------------

def _statements(path):
    """The file without `--` comment lines, split on a semicolon at line end, raw text kept."""
    with open(path, encoding="utf-8") as handle:
        body = "\n".join(line for line in handle.read().splitlines() if not line.lstrip().startswith("--"))
    return [part.strip() for part in re.split(r";[ \t]*(?:\n|$)", body) if part.strip()]


def _normalised(statement):
    return re.sub(r"\s+", " ", statement).strip()


def _starting(statements, prefix):
    return [s for s in statements if s.startswith(prefix)]


def _only(statements, prefix):
    found = _starting(statements, prefix)
    assert len(found) == 1, (prefix, len(found))
    return found[0]


def _complete_run(n, prefix="psse", started=STARTED, **run_changes):
    """Rows of one complete run keyed by table; `run_changes` set columns of the psse_run row."""
    run_id = psse_local_pg.make_run_id(n, started, prefix=prefix)
    rows = psse_local_pg.valid_run_rows(run_id, started)
    rows["psse_run"] = [dict(rows["psse_run"][0], **run_changes)]
    return run_id, rows


def _pp_run(n, started):
    """Rows of one complete pandapower run: a pp- run id with solver pandapower and its version."""
    return _complete_run(n, prefix="pp", started=started, solver="pandapower", solver_version="3.5.6")


def _insert_complete(conn, rows):
    for table in psse_local_pg.RESULT_TABLES:
        psse_local_pg.insert_rows(conn, table, rows[table])


def _view_rows(url, role="anon"):
    """The rows of public.latest_grid_study as `role` (the dashboard's key), always rolled back."""
    import psycopg
    from psycopg import sql

    conn = psycopg.connect(url)
    try:
        conn.execute("set timezone = 'UTC'")
        conn.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
        cur = conn.execute("select * from public.latest_grid_study")
        names = [d.name for d in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]
    finally:
        conn.rollback()
        conn.close()


# --------------------------------------------------------------------------------------------------
# text: the tracer
# --------------------------------------------------------------------------------------------------

def _header_and_text(path):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    header = []
    for line in text.splitlines():
        if line.strip() and not line.startswith("--"):
            break
        header.append(line)
    return "\n".join(header), text


def test_text_tracer_the_migration_is_a_commented_per_solver_replacement():
    assert os.path.isfile(_NEW_MIGRATION)
    names = [os.path.basename(path) for path in local_pg.migration_files()]
    assert names.index(_NEW_NAME) > names.index(_SOLVER_TAG_NAME)

    header, text = _header_and_text(_NEW_MIGRATION)
    assert header.splitlines()[0] == "-- supabase/migrations/" + _NEW_NAME
    assert all(line.startswith("--") for line in header.splitlines() if line.strip())
    lowered = header.lower()
    for word in ("password", "create role", "alter role", "postgres://", "postgresql://"):
        assert word not in lowered, word

    assert "create or replace view public.latest_grid_study with (security_invoker = false) as" in text
    assert "distinct on (r.solver)" in text
    assert "revoke all on public.latest_grid_study from public, anon, authenticated;" in text
    assert "grant select on public.latest_grid_study to anon, authenticated;" in text


# --------------------------------------------------------------------------------------------------
# database
# --------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a database that holds every migration of the repository, in name order."""
    with psse_local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url)
        import psycopg

        with psycopg.connect(url) as conn:
            hour = local_pg.current_utc_hour()
            local_pg.insert_rows(conn, [local_pg.rating_row(city, hour) for city in psse_local_pg.CITIES])
        yield url


@pytest.fixture
def clean_pg(pg):
    """The same database with the four result tables empty."""
    psse_local_pg.reset(pg)
    return pg


def test_db_tracer_anon_reads_one_row_per_city_per_solver(clean_pg):
    import psycopg

    hour = local_pg.current_utc_hour()
    psse_started = hour - timedelta(hours=2) + timedelta(minutes=7)
    pp_started = hour + timedelta(seconds=1)
    _, psse_rows = _complete_run(30, started=psse_started)
    _, pp_rows = _pp_run(31, pp_started)
    with psycopg.connect(clean_pg) as conn:
        _insert_complete(conn, psse_rows)
        _insert_complete(conn, pp_rows)

    rows = _view_rows(clean_pg, "anon")
    assert len(rows) == 8
    by_solver = {}
    for row in rows:
        by_solver.setdefault(row["solver"], []).append(row)
    assert sorted(by_solver) == ["pandapower", "psse"]
    for group in by_solver.values():
        assert sorted(row["city"] for row in group) == sorted(psse_local_pg.CITIES)

    for row in by_solver["psse"]:
        assert row["slot_time"] == hour - timedelta(hours=2)
        assert row["is_stale"] is True
        assert row["age_minutes"] > contract.STALE_AFTER_MINUTES
    for row in by_solver["pandapower"]:
        assert row["slot_time"] == hour
        assert row["is_stale"] is False

    assert tuple(rows[0]) == contract.COLUMNS
    assert not set(rows[0]) & set(contract.FORBIDDEN)
