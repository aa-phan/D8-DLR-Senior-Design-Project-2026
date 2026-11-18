"""
Tests of the owner's read-only check `supabase/ops/verify_solver_tag.sql` (pandapower-solver
workstream, phase 3, requirement DB-01, success criterion 4, decision D-07), and later the public
view guard that the solver-tag migration appends (decision D-03).

The owner applies `supabase/migrations/20261118200000_psse_run_solver_tag.sql` to the live project
and then runs the check. These tests are what makes that run mean something: the check is one
read-only SELECT with pinned check names (text tier), it reports every check ok on a database that
holds the whole migration chain, and each check can be made to fail once (database tier).

Two tiers:
  text tests      (`test_text_*`) run everywhere: they read the files.
  database tests  (`test_db_*`) apply the whole migration chain, in name order, to a throwaway local
                  Postgres. They are skipped unless `DLR_TEST_PG_AUTOSTART=1` or a local
                  `DLR_TEST_DATABASE_URL` is set, and FAIL under `PSSE_REQUIRE_PG=1` when no
                  database is available (the fixture uses psse_local_pg.cluster, which honours that
                  variable). A skip proves nothing about the database. They never touch Supabase.
"""

import difflib
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import pytest

import grid_study_contract as contract
import local_pg
import psse_local_pg

_OPS_DIR = os.path.join(local_pg.REPO_ROOT, "supabase", "ops")
_VERIFY_SOLVER_TAG = os.path.join(_OPS_DIR, "verify_solver_tag.sql")
_VERIFY_PSSE = os.path.join(_OPS_DIR, "verify_psse_results.sql")
_VERIFY_EXPOSURE = os.path.join(_OPS_DIR, "verify_exposure.sql")
_GRID_STUDY_NAME = "20261116200000_expose_latest_grid_study.sql"
_GRID_STUDY_MIGRATION = os.path.join(local_pg.MIGRATIONS_DIR, _GRID_STUDY_NAME)
_SOLVER_TAG_MIGRATION = psse_local_pg.SOLVER_TAG_MIGRATION

STARTED = datetime(2026, 10, 28, 14, 7, 30, tzinfo=timezone.utc)

# The last name is the view guard (decision D-03, chosen by the owner on 2026-11-18).
CHECK_NAMES = (
    "psse_run_solver_column_is_text_not_null_default_psse",
    "psse_run_solver_version_column_is_nullable_text",
    "psse_run_solver_constraints_exist",
    "psse_prefixed_runs_are_tagged_psse",
    "pp_prefixed_runs_are_tagged_pandapower",
    "psse_runs_carry_no_solver_version",
    "latest_grid_study_reads_psse_runs_only",
)


# --------------------------------------------------------------------------------------------------
# text: what the check file says
# --------------------------------------------------------------------------------------------------

def _code(path=_VERIFY_SOLVER_TAG):
    """The file with every `--` comment removed."""
    with open(path, encoding="utf-8") as handle:
        raw = handle.read()
    return "\n".join(line.split("--", 1)[0] for line in raw.splitlines())


def test_text_tracer_the_check_is_one_read_only_select_with_the_pinned_names():
    code = _code()
    # String literals are blanked first: a name or a default may hold a word that is not a keyword here.
    bare = re.sub(r"'(?:[^']|'')*'", "''", code)
    statements = [s.strip() for s in bare.split(";") if s.strip()]
    assert len(statements) == 1
    statement = statements[0].lower()
    assert re.match(r"(with|select)\b", statement)
    for word in ("insert", "update", "delete", "alter", "drop", "create", "grant", "revoke", "truncate"):
        assert not re.search(r"\b%s\b" % word, statement), word
    assert "check_name" in statement and "detail" in statement
    seen = []
    for name in re.findall(r"'(\w+)'", code):
        if name in CHECK_NAMES and name not in seen:
            seen.append(name)
    assert tuple(seen) == CHECK_NAMES


# --------------------------------------------------------------------------------------------------
# text: the public view guard in the migration (decision D-03: the owner chose "guard" on 2026-11-18)
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


_VIEW = "create or replace view public.latest_grid_study "
_COLUMN_COMMENT = "comment on column public.latest_grid_study."


def test_text_the_guarded_view_is_the_old_view_plus_one_predicate():
    old = _statements(_GRID_STUDY_MIGRATION)
    new = _statements(_SOLVER_TAG_MIGRATION)
    old_view, new_view = _only(old, _VIEW), _only(new, _VIEW)

    # Line by line: nothing removed, nothing changed, exactly the predicate line added.
    diff = [line for line in difflib.ndiff(old_view.splitlines(), new_view.splitlines()) if line[:1] in "+-?"]
    assert [line[2:].strip() for line in diff if line[:1] == "+"] == ["and r.solver = 'psse'"]
    assert [line for line in diff if line[:1] in "-?"] == []
    lines = [line.strip() for line in new_view.splitlines()]
    at = lines.index("where r.outcome in ('ok', 'fallback')")
    assert lines[at + 1] == "and r.solver = 'psse'"
    assert lines[at + 2].startswith("order by r.slot_time desc")
    assert new_view.count("r.solver = 'psse'") == 1

    # Owner's rights, the grants and the 20 column comments are the old ones, word for word.
    assert "with (security_invoker = false)" in new_view
    for prefix in ("revoke all on public.latest_grid_study ", "grant select on public.latest_grid_study "):
        assert _only(new, prefix) == _only(old, prefix)
    old_comments = _starting(old, _COLUMN_COMMENT)
    assert len(old_comments) == 20
    assert _starting(new, _COLUMN_COMMENT) == old_comments

    # The view comment is the old text plus one closing sentence.
    old_view_comment = _only(old, "comment on view public.latest_grid_study ")
    new_view_comment = _only(new, "comment on view public.latest_grid_study ")
    assert old_view_comment.endswith("read-only.'")
    assert new_view_comment == (
        old_view_comment[:-1]
        + " Until the per-solver view replaces it, only PSS/E runs (solver psse) are shown.'")

    # The select list names the 20 contract columns in the contract's order.
    select = new_view.split("\nselect\n", 1)[1].split("\nfrom newest_run", 1)[0]
    names = []
    for line in select.splitlines():
        line = line.strip()
        found = re.search(r"\bas\s+(\w+),?$", line) or re.search(r"\.(\w+),?$", line)
        assert found, line
        names.append(found.group(1))
    assert tuple(names) == contract.COLUMNS


def test_text_the_guarded_view_section_follows_the_table_changes_and_names_the_owner_decision():
    path = _SOLVER_TAG_MIGRATION
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    # The header's placeholder sentence is replaced by a description of the section.
    assert "if present below" not in text
    header = text.split("\nalter table public.psse_run", 1)[0]
    assert "latest_grid_study" in header
    assert "2026-11-18" in text and "D-03" in text
    # The section comes after the column and constraint statements, never before them.
    statements = [_normalised(s) for s in _statements(path)]
    last_table_statement = max(i for i, s in enumerate(statements) if s.startswith("alter table public.psse_run "))
    first_view_statement = min(i for i, s in enumerate(statements) if "public.latest_grid_study" in s)
    assert last_table_statement < first_view_statement


# --------------------------------------------------------------------------------------------------
# database
# --------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a database that holds every migration of the repository, in name order."""
    with psse_local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url)
        yield url


@pytest.fixture
def clean_pg(pg):
    """The same database with the four result tables empty."""
    psse_local_pg.reset(pg)
    return pg


def _complete_run(n, prefix="psse", started=STARTED, **run_changes):
    """Rows of one complete run keyed by table; `run_changes` set columns of the psse_run row."""
    run_id = psse_local_pg.make_run_id(n, started, prefix=prefix)
    rows = psse_local_pg.valid_run_rows(run_id, started)
    rows["psse_run"] = [dict(rows["psse_run"][0], **run_changes)]
    return run_id, rows


def _insert_complete(conn, rows):
    for table in psse_local_pg.RESULT_TABLES:
        psse_local_pg.insert_rows(conn, table, rows[table])


def _check_rows(conn, path=_VERIFY_SOLVER_TAG):
    return local_pg.run_select_file(conn, path)


def _ok(conn, name):
    by_name = {row["check_name"]: row["ok"] for row in _check_rows(conn)}
    return by_name[name]


def test_db_tracer_every_check_is_ok_after_the_chain(clean_pg):
    import psycopg

    psse_id, psse_rows = _complete_run(1)
    pp_id, pp_rows = _complete_run(2, prefix="pp", solver="pandapower", solver_version="3.5.6")
    with psycopg.connect(clean_pg) as conn:
        _insert_complete(conn, psse_rows)
        _insert_complete(conn, pp_rows)

    with psycopg.connect(clean_pg) as conn:
        rows = _check_rows(conn)
        assert [row["check_name"] for row in rows] == list(CHECK_NAMES)
        assert all(set(row) == {"check_name", "ok", "detail"} for row in rows)
        failing = [(row["check_name"], row["detail"]) for row in rows if row["ok"] is not True]
        assert failing == []
        # The detail holds counts only: no run id, no prefix, no stored version.
        for row in rows:
            for fragment in ("psse-", "pp-", psse_id, pp_id, "3.5.6"):
                assert fragment not in row["detail"], (row["check_name"], fragment)
        # The two earlier checks of the same live apply stay all ok on the same database.
        for path in (_VERIFY_PSSE, _VERIFY_EXPOSURE):
            other = _check_rows(conn, path)
            assert other, path
            assert [r["check_name"] for r in other if r["ok"] is not True] == [], path


def _sabotage_default(conn):
    conn.execute("alter table public.psse_run alter column solver drop default")


def _sabotage_version_not_null(conn):
    conn.execute("alter table public.psse_run alter column solver_version set not null")


def _sabotage_drop_tie(conn):
    conn.execute("alter table public.psse_run drop constraint psse_run_solver_run_id_ck")


def _sabotage_psse_run_tagged_pandapower(conn):
    _sabotage_drop_tie(conn)
    run_id, rows = _complete_run(10, solver="pandapower")
    psse_local_pg.insert_rows(conn, "psse_run", rows["psse_run"])


def _sabotage_pp_run_tagged_psse(conn):
    _sabotage_drop_tie(conn)
    run_id, rows = _complete_run(11, prefix="pp", solver="psse")
    psse_local_pg.insert_rows(conn, "psse_run", rows["psse_run"])


def _sabotage_psse_run_with_version(conn):
    run_id, rows = _complete_run(12, solver_version="1")
    psse_local_pg.insert_rows(conn, "psse_run", rows["psse_run"])


def _sabotage_unguarded_view(conn):
    # The grid-study file's own view statement, as it stood before the guard.
    statement = _only(_statements(_GRID_STUDY_MIGRATION), _VIEW)
    conn.execute(statement)


# Each sabotage makes exactly the named check false; a related check may fall with it (dropping the
# tie also fails the constraints check), so only the named one is asserted.
_SABOTAGE = {
    "psse_run_solver_column_is_text_not_null_default_psse": _sabotage_default,
    "psse_run_solver_version_column_is_nullable_text": _sabotage_version_not_null,
    "psse_run_solver_constraints_exist": _sabotage_drop_tie,
    "psse_prefixed_runs_are_tagged_psse": _sabotage_psse_run_tagged_pandapower,
    "pp_prefixed_runs_are_tagged_pandapower": _sabotage_pp_run_tagged_psse,
    "psse_runs_carry_no_solver_version": _sabotage_psse_run_with_version,
    "latest_grid_study_reads_psse_runs_only": _sabotage_unguarded_view,
}


@pytest.mark.parametrize("name", CHECK_NAMES)
def test_db_each_check_can_fail(clean_pg, name):
    import psycopg

    with psycopg.connect(clean_pg, autocommit=True) as conn:
        with conn.transaction(force_rollback=True):
            assert _ok(conn, name) is True, "the check is not ok before the sabotage"
            _SABOTAGE[name](conn)
            assert _ok(conn, name) is False
        # The rollback left the database as it was.
        assert _ok(conn, name) is True


# --------------------------------------------------------------------------------------------------
# database: the guarded public view (decision D-03)
# --------------------------------------------------------------------------------------------------

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


def test_db_a_newer_pandapower_run_never_changes_the_view(clean_pg):
    import psycopg

    hour = local_pg.current_utc_hour()
    psse_started = hour - timedelta(hours=2) + timedelta(minutes=7)
    pp_started = hour - timedelta(hours=1) + timedelta(minutes=7)
    _, psse_rows = _complete_run(20, started=psse_started)
    _, pp_rows = _complete_run(21, prefix="pp", started=pp_started, solver="pandapower", solver_version="3.5.6")
    with psycopg.connect(clean_pg) as conn:
        _insert_complete(conn, psse_rows)
        _insert_complete(conn, pp_rows)

    # The newer pandapower run is complete and its four city rows exist, yet the view shows the
    # older PSS/E run: four rows, that run's hour, solver psse.
    rows = _view_rows(clean_pg)
    assert sorted(row["city"] for row in rows) == sorted(psse_local_pg.CITIES)
    assert {row["slot_time"] for row in rows} == {hour - timedelta(hours=2)}
    assert {row["solver"] for row in rows} == {"psse"}

    # With only pandapower runs in the table the view is empty.
    psse_local_pg.reset(clean_pg)
    _, pp_only = _complete_run(22, prefix="pp", started=pp_started, solver="pandapower", solver_version="3.5.6")
    with psycopg.connect(clean_pg) as conn:
        _insert_complete(conn, pp_only)
    assert _view_rows(clean_pg) == []


@pytest.fixture
def sibling_db(pg):
    """An empty database next to the module database, dropped afterwards (one per test)."""
    import psycopg

    name = "view_guard_" + uuid.uuid4().hex[:8]
    with psycopg.connect(pg, autocommit=True) as conn:
        conn.execute('create database "' + name + '"')
    try:
        yield urlsplit(pg)._replace(path="/" + name).geturl()
    finally:
        with psycopg.connect(pg, autocommit=True) as conn:
            conn.execute('drop database if exists "' + name + '" with (force)')


def _view_contract_snapshot(url):
    columns = psse_local_pg.admin_rows(
        url,
        "select a.attname, col_description(a.attrelid, a.attnum) as column_comment from pg_attribute a "
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


def test_db_the_guard_keeps_columns_comments_and_privileges(sibling_db):
    chain = [path for path in local_pg.migration_files() if os.path.basename(path) <= _GRID_STUDY_NAME]
    assert os.path.basename(chain[-1]) == _GRID_STUDY_NAME
    local_pg.apply_migrations(sibling_db, paths=chain)
    before_columns, before_meta, before_definition = _view_contract_snapshot(sibling_db)
    assert [row["attname"] for row in before_columns] == list(contract.COLUMNS)
    assert "solver = 'psse'" not in before_definition

    psse_local_pg.apply_solver_tag_migration(sibling_db)
    after_columns, after_meta, after_definition = _view_contract_snapshot(sibling_db)

    assert after_columns == before_columns  # the same 20 names in the same order, the same comments
    assert after_meta == before_meta  # relkind, relacl, owner and reloptions
    assert "security_invoker=false" in after_meta[0]["options"]
    assert "solver = 'psse'" in after_definition  # and the guard really is in the definition
