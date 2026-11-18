"""
Tests of the solver-tag migration `supabase/migrations/20261118200000_psse_run_solver_tag.sql`
(pandapower-solver workstream, phase 3, requirement DB-01, decisions D-01 and D-02).

The migration adds `solver` (default 'psse') and `solver_version` to public.psse_run and ties the
run id prefix to the solver with check constraints: a `pp-` id is stored only with solver
'pandapower' and a `psse-` id only with solver 'psse'.

Two tiers:
  text tests      (`test_text_*`) run everywhere: they read the migration file and pin its
                  statements, constraint expressions and what it must not contain.
  database tests  (`test_db_*`) apply the file to a throwaway local Postgres. They are skipped
                  unless `DLR_TEST_PG_AUTOSTART=1` or a local `DLR_TEST_DATABASE_URL` is set, and
                  FAIL under `PSSE_REQUIRE_PG=1` when no database is available. A skip proves
                  nothing about the database. They never touch Supabase.

Follows backend/tests/psse_schema_pg_test.py (module-level imports, plain asserts, no classes).
"""

import os
import re
from datetime import datetime, timezone

import pytest

import psse_local_pg as pg_helper

STARTED = datetime(2026, 10, 28, 14, 7, 30, tzinfo=timezone.utc)
WRITER_ROLE = "dlr_psse_writer"

_MIGRATIONS_DIR = os.path.join(pg_helper.REPO_ROOT, "supabase", "migrations")
_MIGRATION_NAME = "20261118200000_psse_run_solver_tag.sql"
_GRID_STUDY_MIGRATION = "20261116200000_expose_latest_grid_study.sql"

_COLUMNS_STATEMENT = (
    "alter table public.psse_run add column if not exists solver text not null default 'psse', "
    "add column if not exists solver_version text"
)
_CONSTRAINT_EXPRESSIONS = (
    "add constraint psse_run_solver_ck check (solver in ('psse', 'pandapower'))",
    "add constraint psse_run_solver_version_ck check (length(solver_version) between 1 and 100)",
    "add constraint psse_run_run_id_ck check (run_id ~ '^(psse|pp)-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}$')",
    "add constraint psse_run_solver_run_id_ck check ((solver = 'psse' and left(run_id, 5) = 'psse-') "
    "or (solver = 'pandapower' and left(run_id, 3) = 'pp-'))",
)


# --------------------------------------------------------------------------- text helpers


def _text():
    with open(os.path.join(_MIGRATIONS_DIR, _MIGRATION_NAME), encoding="utf-8") as handle:
        return handle.read()


def _statements():
    """The file without `--` comment lines, split on a semicolon at line end, normalised and lower-cased."""
    body = "\n".join(line for line in _text().splitlines() if not line.lstrip().startswith("--"))
    parts = re.split(r";[ \t]*(?:\n|$)", body)
    return [re.sub(r"\s+", " ", part).strip().lower() for part in parts if part.strip()]


# --------------------------------------------------------------------------- database helpers


@pytest.fixture(scope="module")
def pg_pre(tmp_path_factory):
    """A database with the reference schema and NO solver migration; the tracer applies it."""
    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_schema(admin_url)
        yield admin_url


def _insert_complete(admin_url, rows):
    """Commit one complete run (psse_run first, then the child tables) as the superuser."""
    import psycopg

    with psycopg.connect(admin_url) as conn:
        for table in pg_helper.RESULT_TABLES:
            pg_helper.insert_rows(conn, table, rows[table])


def _tagged_rows(run_id, **run_changes):
    rows = pg_helper.valid_run_rows(run_id, STARTED)
    rows["psse_run"] = [dict(rows["psse_run"][0], **run_changes)]
    return rows


def _rejected(url, table, row, constraint):
    """Insert one row on its own connection; it must raise CheckViolation naming `constraint`."""
    import psycopg
    import psycopg.errors

    with psycopg.connect(url) as conn:
        with pytest.raises(psycopg.errors.CheckViolation) as caught:
            with conn.transaction():
                pg_helper.insert_rows(conn, table, [row])
    assert caught.value.diag.constraint_name == constraint


# --------------------------------------------------------------------------- tracer


def test_text_tracer_the_migration_adds_the_tag_and_ties_it_to_the_run_id():
    names = sorted(n for n in os.listdir(_MIGRATIONS_DIR) if n.endswith(".sql"))
    assert _MIGRATION_NAME in names
    assert names.index(_MIGRATION_NAME) == names.index(_GRID_STUDY_MIGRATION) + 1
    statements = _statements()
    assert _COLUMNS_STATEMENT in statements
    constraint_statement = [s for s in statements if s.startswith("alter table public.psse_run add constraint")]
    assert len(constraint_statement) == 1
    for expression in _CONSTRAINT_EXPRESSIONS:
        assert expression in constraint_statement[0], expression.split(" check ")[0]


def test_db_tracer_tagged_runs_side_by_side(pg_pre):
    pg_helper.reset(pg_pre)
    before = pg_helper.make_run_id(1, STARTED)
    _insert_complete(pg_pre, pg_helper.valid_run_rows(before, STARTED))

    pg_helper.apply_solver_tag_migration(pg_pre)

    stored = pg_helper.admin_rows(
        pg_pre, "select solver, solver_version from public.psse_run where run_id = %s", (before,)
    )
    assert stored == [{"solver": "psse", "solver_version": None}]

    tagged = pg_helper.make_run_id(2, STARTED, prefix="pp")
    _insert_complete(pg_pre, _tagged_rows(tagged, solver="pandapower"))
    stored = pg_helper.admin_rows(
        pg_pre, "select solver from public.psse_run where run_id = %s", (tagged,)
    )
    assert stored == [{"solver": "pandapower"}]

    mismatched = pg_helper.make_run_id(3, STARTED, prefix="pp")
    row = _tagged_rows(mismatched, solver="psse")["psse_run"][0]
    _rejected(pg_pre, "psse_run", row, "psse_run_solver_run_id_ck")
    assert pg_helper.admin_rows(
        pg_pre, "select count(*) as n from public.psse_run where run_id = %s", (mismatched,)
    )[0]["n"] == 0


# --------------------------------------------------------------------------- text tier


def _raw_statements():
    """Like `_statements` but keeps the letter case (the run id pattern has a capital T and Z)."""
    body = "\n".join(line for line in _text().splitlines() if not line.lstrip().startswith("--"))
    parts = re.split(r";[ \t]*(?:\n|$)", body)
    return [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]


def _run_id_pattern():
    literals = re.findall(r"run_id ~ '([^']*)'", "\n".join(_raw_statements()))
    assert len(literals) == 1, len(literals)
    return re.compile(literals[0])


def _tie_pairs():
    """[(solver, prefix, left() count)] named by the tie expression."""
    expression = [s for s in _statements() if "add constraint psse_run_solver_run_id_ck" in s]
    assert len(expression) == 1
    return re.findall(r"solver = '([a-z]+)' and left\(run_id, ([0-9]+)\) = '([a-z-]+)'", expression[0])


def test_text_run_id_pattern_matches_the_contract_shape():
    pattern = _run_id_pattern()
    for good in ("psse-20261118T120000Z-0123abcd", "pp-20261118T120000Z-0123abcd"):
        assert pattern.fullmatch(good), good
    for bad in (
        "pandapower-20261118T120000Z-0123abcd",
        "pp-20261118T120000Z-0123ABCD",
        "pp-20261118T120000Z-0123abc",
        "p-20261118T120000Z-0123abcd",
        "pp_20261118T120000Z-0123abcd",
        "psse-20261118T1200Z-0123abcd",
        "",
    ):
        assert not pattern.fullmatch(bad), bad


def test_text_solver_vocabulary_is_psse_and_pandapower():
    listed = [s for s in _raw_statements() if "add constraint psse_run_solver_ck" in s]
    assert len(listed) == 1
    members = re.search(r"solver in \(([^)]*)\)", listed[0])
    assert members is not None
    assert re.findall(r"'([a-z]+)'", members.group(1)) == ["psse", "pandapower"]
    pairs = _tie_pairs()
    assert [(solver, prefix) for solver, _count, prefix in pairs] == [("psse", "psse-"), ("pandapower", "pp-")]
    for _solver, count, prefix in pairs:
        assert int(count) == len(prefix)


def _tie_accepts(pairs, solver, run_id):
    """A Python mirror of the tie expression, built from the pairs parsed out of the file."""
    return any(solver == name and run_id[:int(count)] == prefix for name, count, prefix in pairs)


def test_text_tie_mirror_matrix():
    pairs = _tie_pairs()
    psse_id = "psse-20261118T120000Z-0123abcd"
    pp_id = "pp-20261118T120000Z-0123abcd"
    assert _tie_accepts(pairs, "psse", psse_id)
    assert _tie_accepts(pairs, "pandapower", pp_id)
    assert not _tie_accepts(pairs, "psse", pp_id)
    assert not _tie_accepts(pairs, "pandapower", psse_id)
    assert not _tie_accepts(pairs, "matpower", pp_id)


def test_text_every_constraint_is_dropped_before_it_is_added_and_columns_are_added_if_missing():
    statements = _statements()
    names = ("psse_run_solver_ck", "psse_run_solver_version_ck", "psse_run_solver_run_id_ck", "psse_run_run_id_ck")
    drops = [i for i, s in enumerate(statements) if s.startswith("alter table public.psse_run drop constraint")]
    adds = [i for i, s in enumerate(statements) if s.startswith("alter table public.psse_run add constraint")]
    assert len(drops) == 1 and len(adds) == 1 and drops[0] < adds[0]
    for name in names:
        assert len(re.findall(r"drop constraint if exists " + name + r"\b", statements[drops[0]])) == 1, name
        assert len(re.findall(r"add constraint " + name + r"\b", statements[adds[0]])) == 1, name
    columns = [s for s in statements if s.startswith("alter table public.psse_run add column")]
    assert len(columns) == 1
    assert len(re.findall(r"add column if not exists ", columns[0])) == 2
    assert columns[0].count("add column") == 2
    assert not any("not valid" in s for s in statements)


def test_text_header_is_comments_only_and_names_no_credential():
    lines = _text().splitlines()
    first = next(i for i, line in enumerate(lines) if line.strip() and not line.lstrip().startswith("--"))
    assert first > 0
    assert all(not line.strip() or line.lstrip().startswith("--") for line in lines[:first])
    assert lines[first].lower().startswith("alter table public.psse_run")
    lowered = _text().lower()
    for word in ("password", "postgres://", "postgresql://", "create role", "alter role"):
        assert word not in lowered, word


def test_text_nothing_privileged_on_the_result_tables():
    result_tables = ("psse_run", "psse_dispatched_capacity", "psse_voltage_margin", "psse_contingency_result")
    for statement in _statements():
        assert "dlr_psse_writer" not in statement
        if re.match(r"(grant|revoke) ", statement):
            assert "public.latest_grid_study" in statement
            roles = re.split(r" (?:to|from) ", statement, maxsplit=1)[1]
            assert set(re.split(r"[ ,]+", roles.strip())) <= {"public", "anon", "authenticated"}
            for table in result_tables:
                assert table not in statement


_ALLOWED_STARTS = (
    "alter table public.psse_run ",
    "comment on column public.psse_run.solver",
    "create or replace view public.latest_grid_study ",
    "revoke all on public.latest_grid_study ",
    "grant select on public.latest_grid_study ",
    "comment on view public.latest_grid_study ",
    "comment on column public.latest_grid_study.",
)


def test_text_statement_inventory():
    statements = _statements()
    assert statements
    for statement in statements:
        assert statement.startswith(_ALLOWED_STARTS), statement.split(" ")[:5]
        assert not re.match(r"(update|delete|insert|truncate) ", statement)
    assert len([s for s in statements if s.startswith("alter table public.psse_run")]) == 3


def test_text_both_new_columns_are_commented_unit_first():
    statements = _statements()
    for column in ("solver", "solver_version"):
        found = [s for s in statements if s.startswith("comment on column public.psse_run." + column + " is ")]
        assert len(found) == 1, column
        assert found[0].split(" is ", 1)[1].startswith("'none (label): "), column
