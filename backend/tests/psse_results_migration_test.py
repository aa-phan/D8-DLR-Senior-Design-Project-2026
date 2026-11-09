"""
Tests of the PSS/E results migration (quick task 261109-o6v; requirements DBX-01 and DBX-02;
threats T-o6v-04..T-o6v-08).

`supabase/migrations/<UTC ts>_psse_results.sql` is the teammate's reference DDL
(docs/data-science/schema/psse_results_v1.sql on branch feature/pss-e-integration) copied
verbatim between its BEGIN and END marker lines, behind a comment-only header. The text tests pin
that region by sha256 and check that nothing outside it is SQL. The local-Postgres tests apply
every migration to a throwaway cluster and exercise the role `dlr_psse_writer`, `anon` and
`authenticated`, and run the read-only checker `supabase/ops/verify_psse_results.sql`, including
one negative per check.

The local-Postgres tests need `DLR_TEST_PG_AUTOSTART=1` (backend/tests/local_pg.py). A skip proves
nothing, so the verify command treats a skip as a failure. Nothing here touches the live Supabase
project, a remote or the network.
"""

import contextlib
import glob
import hashlib
import os
import re

import pytest

import local_pg

_MIGRATIONS_DIR = local_pg.MIGRATIONS_DIR
_OPS_DIR = os.path.join(local_pg.REPO_ROOT, "supabase", "ops")
_VERIFY_PSSE = os.path.join(_OPS_DIR, "verify_psse_results.sql")
_VERIFY_EXPOSURE = os.path.join(_OPS_DIR, "verify_exposure.sql")
_EXPOSE_MIGRATION = "20261108120100_expose_day_ahead_forecast.sql"

_BEGIN = "-- BEGIN psse_results_v1"
_END = "-- END psse_results_v1"
# sha256 of the marked region of the reference DDL (each line given one LF ending, UTF-8), confirmed
# at commit 30ec2d6 of origin/feature/pss-e-integration.
_REGION_SHA256 = "955f349d2df66394dbec4378ddcc2d9eb61f7e37bd4eda8de4b70de16c3a6643"

_TABLES = ("psse_run", "psse_dispatched_capacity", "psse_voltage_margin", "psse_contingency_result")

_PSSE_VERIFY_CHECKS = (
    "psse_tables_exist",
    "psse_tables_rls_enabled",
    "anon_authenticated_hold_nothing_on_psse_tables",
    "dlr_psse_writer_holds_exactly_insert_select_on_psse_tables",
    "dlr_psse_writer_holds_nothing_on_other_relations",
    "dlr_psse_writer_policies_are_insert_and_select_only",
    "dlr_psse_writer_role_attributes",
)


def _psse_paths():
    return sorted(glob.glob(os.path.join(_MIGRATIONS_DIR, "*_psse_results.sql")))


def _psse_path():
    paths = _psse_paths()
    assert len(paths) == 1, paths
    return paths[0]


def _lines(path=None):
    with open(path or _psse_path(), "rb") as handle:
        return handle.read().decode("utf-8").splitlines()


# --------------------------------------------------------------------------------------------------
# text: what the files say
# --------------------------------------------------------------------------------------------------

def test_text_there_is_one_psse_migration_named_by_utc_timestamp_and_it_sorts_last():
    paths = _psse_paths()
    assert len(paths) == 1, paths
    name = os.path.basename(paths[0])
    assert re.fullmatch(r"[0-9]{14}_psse_results\.sql", name), name
    names = sorted(os.listdir(_MIGRATIONS_DIR))
    assert name > _EXPOSE_MIGRATION
    assert names[-1] == name


def test_text_the_marked_region_is_the_reference_ddl_byte_for_byte():
    lines = _lines()
    assert lines.count(_BEGIN) == 1 and lines.count(_END) == 1
    begin, end = lines.index(_BEGIN), lines.index(_END)
    assert begin < end
    region = "".join(line + "\n" for line in lines[begin:end + 1])
    assert hashlib.sha256(region.encode("utf-8")).hexdigest() == _REGION_SHA256
    assert end + 1 - begin == 243


def test_text_every_line_outside_the_region_is_a_comment_or_blank():
    lines = _lines()
    begin, end = lines.index(_BEGIN), lines.index(_END)
    outside = lines[:begin] + lines[end + 1:]
    assert outside, "the header is missing"
    for line in outside:
        assert line.strip() == "" or line.startswith("--"), line
    header = "\n".join(lines[:begin]).lower()
    # The header carries no credential and no connection string.
    for forbidden in ("password", "postgresql://", "postgres://"):
        assert forbidden not in header, forbidden


def test_text_the_checker_is_one_read_only_select_with_the_pinned_check_names_in_order():
    with open(_VERIFY_PSSE, encoding="utf-8") as handle:
        raw = handle.read()
    code = "\n".join(line.split("--", 1)[0] for line in raw.splitlines())
    statements = [s.strip() for s in code.split(";") if s.strip()]
    assert len(statements) == 1
    statement = statements[0].lower()
    assert statement.startswith("with") and "select check_name, ok, detail" in statement
    # String literals are blanked first: the privilege names 'INSERT' and 'UPDATE' are arguments there.
    bare = re.sub(r"'(?:[^']|'')*'", "''", statement)
    for word in ("insert", "update", "delete", "truncate", "drop", "alter", "create", "grant", "revoke"):
        assert not re.search(rf"\b{word}\b", bare), word
    seen = []
    for name in re.findall(r"'(\w+)'", code):
        if name in _PSSE_VERIFY_CHECKS and name not in seen:
            seen.append(name)
    assert tuple(seen) == _PSSE_VERIFY_CHECKS


# --------------------------------------------------------------------------------------------------
# Local Postgres: every migration applied, then exercised as the PSS/E role and the public roles
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


def _seed_ratings(url):
    """A fresh rating row for each city, as the exposure checker expects a populated latest_rating."""
    import psycopg
    from datetime import timedelta

    import config

    newest = local_pg.current_utc_hour()
    rows = [local_pg.rating_row(city, newest - timedelta(hours=back), rating_amps=1000.0 + 10 * index + back)
            for index, city in enumerate(config.LOCATIONS) for back in (1, 0)]
    with psycopg.connect(url) as conn:
        local_pg.insert_rows(conn, rows)


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    """A database with every migration applied."""
    local_pg.require_local_pg()
    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url)
        _seed_ratings(url)
        yield url


def _checks(conn):
    return local_pg.run_select_file(conn, _VERIFY_PSSE)


def _failed(rows):
    return [row["check_name"] for row in rows if row["ok"] is not True]


def _failed_run_row():
    from psycopg.types.json import Jsonb
    from datetime import datetime, timezone

    return {
        "run_id": "psse-20261109T120000Z-0123abcd",
        "slot_time": datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
        "started_at": datetime(2026, 11, 9, 12, 0, 5, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 11, 9, 12, 1, 0, tzinfo=timezone.utc),
        "outcome": "failed",
        "failed_stage": "load_case",
        "error": "test",
        "case_id": "ieee39",
        "ratings_used": Jsonb({city: {} for city in ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")}),
        "job_version": "test",
    }


_INSERT_RUN = (
    "insert into public.psse_run (run_id, slot_time, started_at, finished_at, outcome, failed_stage, error, "
    "case_id, ratings_used, job_version) values (%(run_id)s, %(slot_time)s, %(started_at)s, %(finished_at)s, "
    "%(outcome)s, %(failed_stage)s, %(error)s, %(case_id)s, %(ratings_used)s, %(job_version)s)"
)


def test_the_checker_returns_the_seven_pinned_checks_in_order_all_ok(pg_url):
    with _session(pg_url) as conn:
        rows = _checks(conn)
    assert tuple(row["check_name"] for row in rows) == _PSSE_VERIFY_CHECKS
    assert _failed(rows) == [], rows
    assert all(isinstance(row["detail"], str) and row["detail"] for row in rows)


def test_the_exposure_checker_still_returns_29_checks_all_ok(pg_url):
    with _session(pg_url) as conn:
        rows = local_pg.run_select_file(conn, _VERIFY_EXPOSURE)
    assert len(rows) == 29
    assert _failed(rows) == [], rows


def test_the_psse_migration_leaves_every_exposure_check_and_detail_unchanged(tmp_path_factory):
    local_pg.require_local_pg()
    paths = local_pg.migration_files()
    psse = _psse_path()
    before_paths = [p for p in paths if p != psse]
    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url, paths=before_paths)
        _seed_ratings(url)
        with _session(url) as conn:
            before = local_pg.run_select_file(conn, _VERIFY_EXPOSURE)
        local_pg.apply_migrations(url, paths=[psse])
        with _session(url) as conn:
            after = local_pg.run_select_file(conn, _VERIFY_EXPOSURE)
    assert len(before) == 29 and _failed(before) == []
    assert after == before


def test_the_writer_can_insert_and_read_a_run_but_not_update_delete_or_truncate_it(pg_url):
    from psycopg import errors

    with _session(pg_url, "dlr_psse_writer") as conn:
        conn.execute(_INSERT_RUN, _failed_run_row())
        rows = conn.execute("select run_id, outcome from public.psse_run").fetchall()
        assert rows == [("psse-20261109T120000Z-0123abcd", "failed")]
        for statement in ("update public.psse_run set error = 'x'",
                          "delete from public.psse_run",
                          "truncate public.psse_run"):
            with pytest.raises(errors.InsufficientPrivilege), conn.transaction():
                conn.execute(statement)
        # The refused statements changed nothing.
        assert conn.execute("select count(*) from public.psse_run").fetchone()[0] == 1


def test_the_writer_is_refused_on_the_rating_tables_and_views(pg_url):
    from psycopg import errors

    with _session(pg_url, "dlr_psse_writer") as conn:
        for relation in ("city_rating", "pipeline_run", "latest_rating"):
            with pytest.raises(errors.InsufficientPrivilege), conn.transaction():
                conn.execute(f"select 1 from public.{relation} limit 1")
        with pytest.raises(errors.InsufficientPrivilege), conn.transaction():
            conn.execute("insert into public.city_rating (city) values ('AUSTIN')")


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("table", _TABLES)
def test_the_public_roles_cannot_read_the_psse_tables(pg_url, role, table):
    from psycopg import errors

    with _session(pg_url, role) as conn:
        with pytest.raises(errors.InsufficientPrivilege), conn.transaction():
            conn.execute(f"select 1 from public.{table} limit 1")


def test_the_psse_migration_applies_again_without_error_and_the_checker_stays_ok(pg_url):
    path = _psse_path()
    local_pg.apply_migrations(pg_url, paths=[path])
    local_pg.apply_migrations(pg_url, paths=[path])
    with _session(pg_url) as conn:
        rows = _checks(conn)
    assert _failed(rows) == [], rows


_NEGATIVES = [
    ("grant select on public.psse_run to anon",
     "anon_authenticated_hold_nothing_on_psse_tables"),
    ("grant update on public.psse_run to dlr_psse_writer",
     "dlr_psse_writer_holds_exactly_insert_select_on_psse_tables"),
    ("grant select on public.city_rating to dlr_psse_writer",
     "dlr_psse_writer_holds_nothing_on_other_relations"),
    ("alter table public.psse_voltage_margin disable row level security",
     "psse_tables_rls_enabled"),
    ("create policy dlr_psse_writer_update on public.psse_run for update to dlr_psse_writer using (true)",
     "dlr_psse_writer_policies_are_insert_and_select_only"),
    ("alter role dlr_psse_writer bypassrls",
     "dlr_psse_writer_role_attributes"),
]


@pytest.mark.parametrize("change, check", _NEGATIVES, ids=[check for _, check in _NEGATIVES])
def test_the_checker_turns_exactly_the_named_check_false(pg_url, change, check):
    with _session(pg_url) as conn:
        assert _failed(_checks(conn)) == []
        conn.execute(change)
        rows = _checks(conn)
    assert tuple(row["check_name"] for row in rows) == _PSSE_VERIFY_CHECKS
    assert _failed(rows) == [check], rows
