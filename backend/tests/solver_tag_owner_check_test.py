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

import os
import re
from datetime import datetime, timezone

import pytest

import local_pg
import psse_local_pg

_OPS_DIR = os.path.join(local_pg.REPO_ROOT, "supabase", "ops")
_VERIFY_SOLVER_TAG = os.path.join(_OPS_DIR, "verify_solver_tag.sql")
_VERIFY_PSSE = os.path.join(_OPS_DIR, "verify_psse_results.sql")
_VERIFY_EXPOSURE = os.path.join(_OPS_DIR, "verify_exposure.sql")

STARTED = datetime(2026, 10, 28, 14, 7, 30, tzinfo=timezone.utc)

CHECK_NAMES = (
    "psse_run_solver_column_is_text_not_null_default_psse",
    "psse_run_solver_version_column_is_nullable_text",
    "psse_run_solver_constraints_exist",
    "psse_prefixed_runs_are_tagged_psse",
    "pp_prefixed_runs_are_tagged_pandapower",
    "psse_runs_carry_no_solver_version",
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


def _complete_run(n, prefix="psse", **run_changes):
    """Rows of one complete run keyed by table; `run_changes` set columns of the psse_run row."""
    run_id = psse_local_pg.make_run_id(n, STARTED, prefix=prefix)
    rows = psse_local_pg.valid_run_rows(run_id, STARTED)
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


# Each sabotage makes exactly the named check false; a related check may fall with it (dropping the
# tie also fails the constraints check), so only the named one is asserted.
_SABOTAGE = {
    "psse_run_solver_column_is_text_not_null_default_psse": _sabotage_default,
    "psse_run_solver_version_column_is_nullable_text": _sabotage_version_not_null,
    "psse_run_solver_constraints_exist": _sabotage_drop_tie,
    "psse_prefixed_runs_are_tagged_psse": _sabotage_psse_run_tagged_pandapower,
    "pp_prefixed_runs_are_tagged_pandapower": _sabotage_pp_run_tagged_psse,
    "psse_runs_carry_no_solver_version": _sabotage_psse_run_with_version,
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
