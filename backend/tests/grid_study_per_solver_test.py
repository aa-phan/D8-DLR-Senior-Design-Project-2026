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

import contextlib
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

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


_PREFIXES = (
    _VIEW,
    "revoke all on public.latest_grid_study ",
    "grant select on public.latest_grid_study ",
    "comment on view public.latest_grid_study ",
    _COLUMN_COMMENT,
)


def _blanked(statement):
    """The statement with every string literal blanked, so a word inside a comment is not a keyword."""
    return re.sub(r"'(?:[^']|'')*'", "''", statement)


def test_text_only_view_statements_and_no_psse_only_filter():
    statements = _statements(_NEW_MIGRATION)
    assert len(statements) == 24
    for statement in statements:
        assert statement.startswith(_PREFIXES), statement[:60]
    assert len(_starting(statements, _VIEW)) == 1
    assert len(_starting(statements, "revoke all on public.latest_grid_study ")) == 1
    assert len(_starting(statements, "grant select on public.latest_grid_study ")) == 1
    assert len(_starting(statements, "comment on view public.latest_grid_study ")) == 1
    assert len(_starting(statements, _COLUMN_COMMENT)) == 20

    for statement in statements:
        lowered = _blanked(statement).lower()
        for word in ("alter", "drop", "insert", "update", "delete", "truncate"):
            assert not re.search(r"\b%s\b" % word, lowered), (word, statement[:60])
        for phrase in ("create role", "alter role"):
            assert phrase not in lowered, phrase
        if lowered.startswith(("grant ", "revoke ")):
            assert "psse_" not in lowered, statement

    # The PSS/E-only predicate and the constant label are gone; read on the raw statement.
    view = _only(statements, _VIEW)
    assert "r.solver = 'psse'" not in view
    assert "'psse'" not in view
    assert "limit 1" not in view


def test_text_select_items_match_the_phase3_view_except_solver():
    old = _normalised(_only(_statements(_SOLVER_TAG_MIGRATION), _VIEW))
    raw_new = _only(_statements(_NEW_MIGRATION), _VIEW)
    new = _normalised(raw_new)

    def middle(statement):
        start = statement.index(" d.city, n.slot_time,")
        return statement[start:statement.rindex(" order by d.city")]

    assert middle(new) == middle(old)
    assert "select n.solver, d.city, n.slot_time," in new
    assert new.endswith("order by d.city, n.solver")
    assert new.count("order by") == 2  # the newest_run step and the final order

    # The select list names the 20 contract columns in the contract's order.
    select = raw_new.split("\nselect\n", 1)[1].split("\nfrom newest_run", 1)[0]
    names = []
    for line in select.splitlines():
        line = line.strip()
        found = re.search(r"\bas\s+(\w+),?$", line) or re.search(r"\.(\w+),?$", line)
        assert found, line
        names.append(found.group(1))
    assert tuple(names) == contract.COLUMNS


def _comments_by_column(statements):
    comments = {}
    for statement in _starting(statements, _COLUMN_COMMENT):
        column = re.match(re.escape(_COLUMN_COMMENT) + r"(\w+) is ", statement).group(1)
        assert column not in comments, column
        comments[column] = statement
    return comments


def test_text_nineteen_comments_unchanged_two_rewritten():
    old = _statements(_SOLVER_TAG_MIGRATION)
    new = _statements(_NEW_MIGRATION)
    old_comments, new_comments = _comments_by_column(old), _comments_by_column(new)
    assert tuple(new_comments) == contract.COLUMNS
    assert tuple(old_comments) == contract.COLUMNS
    for column in contract.COLUMNS:
        if column != "solver":
            assert new_comments[column] == old_comments[column], column
    solver = new_comments["solver"]
    assert solver != old_comments["solver"]
    assert "pandapower" in solver and "filter on this column" in solver
    assert "later release" not in solver

    for prefix in ("revoke all on public.latest_grid_study ", "grant select on public.latest_grid_study "):
        assert _only(new, prefix) == _only(old, prefix)

    old_view_comment = _only(old, "comment on view public.latest_grid_study ")
    new_view_comment = _only(new, "comment on view public.latest_grid_study ")
    assert new_view_comment != old_view_comment
    for phrase in ("one row per city per solver", "PRELIMINARY", "90 minutes", "filter on solver"):
        assert phrase in new_view_comment, phrase
    assert "Until the per-solver view replaces it" not in new_view_comment
    assert "only PSS/E runs" not in new_view_comment


def test_text_header_names_the_order_and_the_owner_steps():
    header, _ = _header_and_text(_NEW_MIGRATION)
    for phrase in (
        _SOLVER_TAG_NAME, "restores", "Phase 5 soak", "supabase db push",
        "verify_solver_tag.sql (6 checks)", "verify_psse_results.sql (7 checks)",
        "verify_exposure.sql (37 checks)",
    ):
        assert phrase in header, phrase


def test_text_contract_max_rows_is_cities_times_solvers():
    assert contract.SOLVERS == ("psse", "pandapower")
    assert contract.MAX_ROWS == len(contract.SOLVERS) * len(psse_local_pg.CITIES) == 8
    constraint = next(s for s in _statements(_SOLVER_TAG_MIGRATION) if "psse_run_solver_ck check" in s)
    found = re.search(r"psse_run_solver_ck check \(solver in \(([^)]*)\)\)", constraint)
    assert found
    assert tuple(re.findall(r"'(\w+)'", found.group(1))) == contract.SOLVERS


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


def test_db_no_runs_gives_no_rows(clean_pg):
    assert _view_rows(clean_pg) == []


@pytest.mark.parametrize("solver", contract.SOLVERS)
def test_db_one_solver_gives_its_four_city_rows(clean_pg, solver):
    import psycopg

    started = local_pg.current_utc_hour() + timedelta(seconds=1)
    if solver == "psse":
        _, rows_of_run = _complete_run(40, started=started)
    else:
        _, rows_of_run = _pp_run(41, started)
    with psycopg.connect(clean_pg) as conn:
        _insert_complete(conn, rows_of_run)

    rows = _view_rows(clean_pg)
    assert {row["solver"] for row in rows} == {solver}
    assert sorted(row["city"] for row in rows) == sorted(psse_local_pg.CITIES)
    assert {row["slot_time"] for row in rows} == {local_pg.current_utc_hour()}
    assert {row["is_stale"] for row in rows} == {False}


def test_db_a_newer_failed_run_of_a_solver_is_skipped(clean_pg):
    import psycopg

    hour = local_pg.current_utc_hour()
    _, psse_rows = _complete_run(50, started=hour - timedelta(hours=2) + timedelta(minutes=7))
    _, pp_rows = _pp_run(51, hour - timedelta(hours=1) + timedelta(minutes=7))
    failed_started = hour + timedelta(seconds=1)
    failed = psse_local_pg.failed_run_row(psse_local_pg.make_run_id(52, failed_started, prefix="pp"), failed_started)
    failed = dict(failed, solver="pandapower", solver_version="3.5.6")
    with psycopg.connect(clean_pg) as conn:
        _insert_complete(conn, psse_rows)
        _insert_complete(conn, pp_rows)
        psse_local_pg.insert_rows(conn, "psse_run", [failed])

    rows = _view_rows(clean_pg)
    assert len(rows) == 8
    slots = {}
    for row in rows:
        slots.setdefault(row["solver"], set()).add(row["slot_time"])
    assert slots == {
        "psse": {hour - timedelta(hours=2)},
        "pandapower": {hour - timedelta(hours=1)},
    }


def test_db_two_runs_of_one_solver_in_one_hour_the_later_finish_wins(clean_pg):
    import psycopg

    hour = local_pg.current_utc_hour()
    earlier = hour - timedelta(hours=1) + timedelta(minutes=5)
    later = hour - timedelta(hours=1) + timedelta(minutes=20)
    _, first_rows = _pp_run(60, earlier)
    _, second_rows = _pp_run(61, later)
    with psycopg.connect(clean_pg) as conn:
        _insert_complete(conn, first_rows)
        _insert_complete(conn, second_rows)

    rows = _view_rows(clean_pg)
    assert len(rows) == 4
    assert {row["solver"] for row in rows} == {"pandapower"}
    # valid_run_rows finishes a run 90 seconds after it starts, so this is the later run's finish.
    assert {row["study_finished_at"] for row in rows} == {later + timedelta(seconds=90)}


@pytest.fixture
def sibling_db(pg):
    """An empty database next to the module database, dropped afterwards (one per test)."""
    import psycopg

    name = "per_solver_" + uuid.uuid4().hex[:8]
    with psycopg.connect(pg, autocommit=True) as conn:
        conn.execute('create database "' + name + '"')
    try:
        yield urlsplit(pg)._replace(path="/" + name).geturl()
    finally:
        with psycopg.connect(pg, autocommit=True) as conn:
            conn.execute('drop database if exists "' + name + '" with (force)')


def _snapshot(url):
    columns = psse_local_pg.admin_rows(
        url,
        "select a.attname, format_type(a.atttypid, a.atttypmod) as type, "
        "col_description(a.attrelid, a.attnum) as column_comment from pg_attribute a "
        "where a.attrelid = 'public.latest_grid_study'::regclass and a.attnum > 0 and not a.attisdropped "
        "order by a.attnum")
    meta = psse_local_pg.admin_rows(
        url,
        "select c.relkind::text as kind, c.relacl::text as acl, c.reloptions::text as options, "
        "pg_get_userbyid(c.relowner)::text as owner "
        "from pg_class c where c.oid = 'public.latest_grid_study'::regclass")
    definition = psse_local_pg.admin_rows(
        url, "select pg_get_viewdef('public.latest_grid_study'::regclass) as definition")[0]["definition"]
    return columns, meta, definition


def test_db_the_replacement_keeps_columns_types_comments_and_privileges(sibling_db):
    chain = [path for path in local_pg.migration_files() if os.path.basename(path) <= _SOLVER_TAG_NAME]
    assert os.path.basename(chain[-1]) == _SOLVER_TAG_NAME
    local_pg.apply_migrations(sibling_db, paths=chain)
    before_columns, before_meta, before_definition = _snapshot(sibling_db)
    assert [row["attname"] for row in before_columns] == list(contract.COLUMNS)
    assert "solver = 'psse'" in before_definition

    local_pg.apply_migrations(sibling_db, paths=[_NEW_MIGRATION])
    after_columns, after_meta, after_definition = _snapshot(sibling_db)

    assert [row["attname"] for row in after_columns] == list(contract.COLUMNS)
    assert [row["type"] for row in after_columns] == [row["type"] for row in before_columns]
    kept = [(b, a) for b, a in zip(before_columns, after_columns) if b["attname"] != "solver"]
    assert len(kept) == 19
    for before, after in kept:
        assert after == before, before["attname"]
    before_solver = next(row for row in before_columns if row["attname"] == "solver")
    after_solver = next(row for row in after_columns if row["attname"] == "solver")
    assert after_solver["column_comment"] != before_solver["column_comment"]
    assert "pandapower" in after_solver["column_comment"]

    assert after_meta == before_meta  # relkind, relacl, owner and reloptions
    assert "security_invoker=false" in after_meta[0]["options"]
    assert "DISTINCT ON (r.solver)" in after_definition
    assert "solver = 'psse'" not in after_definition


@contextlib.contextmanager
def _as_role(url, role):
    """A connection that reads as `role` (the dashboard's key is anon), always rolled back."""
    import psycopg
    from psycopg import sql

    conn = psycopg.connect(url)
    try:
        conn.execute("set timezone = 'UTC'")
        conn.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_db_public_roles_read_the_view_not_the_tables_with_both_solvers(clean_pg, role):
    import psycopg
    from psycopg import errors

    hour = local_pg.current_utc_hour()
    _, psse_rows = _complete_run(70, started=hour - timedelta(hours=2) + timedelta(minutes=7))
    _, pp_rows = _pp_run(71, hour + timedelta(seconds=1))
    with psycopg.connect(clean_pg) as conn:
        _insert_complete(conn, psse_rows)
        _insert_complete(conn, pp_rows)

    for table in psse_local_pg.RESULT_TABLES:
        with _as_role(clean_pg, role) as conn:
            with pytest.raises(errors.InsufficientPrivilege):
                conn.execute("select 1 from public.%s limit 1" % table)

    rows = _view_rows(clean_pg, role)
    assert len(rows) == contract.MAX_ROWS
    for row in rows:
        assert not set(row) & set(contract.FORBIDDEN)
        assert tuple(row) == contract.COLUMNS


def test_db_the_migration_reapplies_cleanly(clean_pg):
    import psycopg

    def snapshot():
        return psse_local_pg.admin_rows(
            clean_pg,
            "select pg_get_viewdef('public.latest_grid_study'::regclass) as definition, "
            "c.relacl::text as acl, c.reloptions::text as options "
            "from pg_class c where c.oid = 'public.latest_grid_study'::regclass")

    def apply(path):
        with open(path, encoding="utf-8") as handle:
            sql_text = handle.read()
        with psycopg.connect(clean_pg) as conn:
            conn.execute(sql_text)

    before = snapshot()
    assert "DISTINCT ON (r.solver)" in before[0]["definition"]

    apply(_NEW_MIGRATION)
    apply(_NEW_MIGRATION)
    assert snapshot() == before

    # Re-applying the solver-tag file alone restores the PSS/E-only view; the new file after it
    # puts the per-solver definition and the same permissions back (the header's order warning).
    apply(_SOLVER_TAG_MIGRATION)
    assert "solver = 'psse'" in snapshot()[0]["definition"]
    apply(_NEW_MIGRATION)
    assert snapshot() == before
