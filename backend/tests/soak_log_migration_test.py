"""
Tests of the Phase 6 soak freshness log, `ops.freshness_log` and `ops.log_freshness()`
(production-pipeline, E2E-02; D-02, D-07, D-13, D-14, OD-4).

Plain English: "every five minutes the database writes down how old each city's current
rating is, using the same 90-minute rule the dashboard sees." These tests prove the log
agrees with `public.latest_rating` to the microsecond, is invisible to consumers, and that
the owner's three scripts (start, check, stop) behave against a stand-in for pg_cron.

Two kinds of test live here, as in backend/tests/expose_migration_test.py:

* Offline tests read the migration as text. They need no database and run in the default
  suite, so a pg_cron call sneaking into migration history or a city list drifting from
  config.LOCATIONS fails every run.
* Local-Postgres tests start a private throwaway cluster on 127.0.0.1 only when
  `DLR_TEST_PG_AUTOSTART=1` (or a local `DLR_TEST_DATABASE_URL` is given), apply every
  migration to a database that begins with Supabase's legacy default grants, and exercise
  the log as the superuser, as `anon`, `authenticated` and `dlr_writer`. pg_cron is not
  installed locally, so the owner scripts run against a stub `cron` schema that has the
  documented tables and the `schedule` / `unschedule` functions (06-RESEARCH). They skip
  otherwise, never touch Supabase, and always stop the cluster (backend/tests/local_pg.py).

Every test mutation happens inside a transaction that is rolled back.
"""

import contextlib
import glob
import os
import re
from datetime import timedelta

import pytest

import config
import local_pg

_MIGRATIONS_DIR = local_pg.MIGRATIONS_DIR
_OPS_DIR = os.path.join(local_pg.REPO_ROOT, "supabase", "ops")
_VERIFY_MONITORING_SQL = os.path.join(_OPS_DIR, "verify_monitoring.sql")

# Comment bodies are blanked before keyword checks, so a word inside a comment never counts.
_COMMENT_RE = re.compile(
    r"(comment\s+on\s+(?:table|column|view|function)\s+[\w.]+(?:\([^)]*\))?\s+is\s+)'(?:[^']|'')*'", re.IGNORECASE
)

# The log's 90 minutes, in seconds: the same limit the view's is_stale uses (OD-4).
_STALE_SECONDS = 90 * 60


def _soak_path():
    paths = glob.glob(os.path.join(_MIGRATIONS_DIR, "*_soak_freshness_log.sql"))
    assert len(paths) == 1, paths
    return paths[0]


def _expose_path():
    paths = glob.glob(os.path.join(_MIGRATIONS_DIR, "*_expose_latest_rating.sql"))
    assert len(paths) == 1, paths
    return paths[0]


def _raw(path=None):
    with open(path or _soak_path(), encoding="utf-8") as handle:
        return handle.read()


def _code(path=None):
    """The migration with comment bodies blanked and `--` comments removed."""
    text = _COMMENT_RE.sub(r"\1''", _raw(path))
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


# ---------------------------------------------------------------------------
# Offline tests: the migration as text.
# ---------------------------------------------------------------------------


def test_soak_migration_schedules_nothing_and_sorts_after_expose():
    # Scheduling stays outside migration history: a replay of the migrations must never start a job.
    code = _code()
    assert not re.search(r"\bcron\b", code, re.IGNORECASE), "the migration must not touch pg_cron"
    assert "schedule" not in code.lower()
    name = os.path.basename(_soak_path())
    assert re.fullmatch(r"\d{14}_soak_freshness_log\.sql", name)
    assert name > os.path.basename(_expose_path())
    # Nothing is ever granted to the consumer roles; the only grants are the two read-only ones for dlr_writer.
    grants = [" ".join(line.split()) for line in re.findall(r"\bgrant\b[^;]*;", code, re.IGNORECASE)]
    assert grants, "the dlr_writer grants are missing"
    for grant in grants:
        assert re.search(r"\bto dlr_writer\b", grant), grant
        assert not re.search(r"\b(anon|authenticated|public)\b", grant), grant
    assert re.search(r"grant usage on schema ops to dlr_writer", code)
    assert re.search(r"grant select on ops\.freshness_log to dlr_writer", code)
    assert "security definer" not in code.lower()


def test_soak_city_list_matches_config_locations():
    match = re.search(r"from \(values (.*?)\) as c\(city\)", _code(), re.DOTALL)
    assert match, "ops.log_freshness has no city list"
    cities = re.findall(r"\('([A-Z_]+)'\)", match.group(1))
    assert sorted(cities) == sorted(config.LOCATIONS)
    # One definition of stale: it reads the view's own flag and never restates 90 minutes.
    assert "public.latest_rating" in _code()
    assert "is_stale" in _code()
    assert "90" not in _code() and "5400" not in _code()


# ---------------------------------------------------------------------------
# Local-Postgres tests: the log as the superuser and as every role that matters.
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _session(url, role=None):
    """A connection that is always rolled back; optionally acting as `role`."""
    import psycopg
    from psycopg import sql

    conn = psycopg.connect(url)
    try:
        if role:
            conn.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _sqlstate(error):
    return getattr(error.value, "sqlstate", None)


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    """A migrated throwaway database holding three hourly slots for each of the four cities."""
    local_pg.require_local_pg()
    import psycopg

    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url)
        newest = local_pg.current_utc_hour()
        rows = [local_pg.rating_row(city, newest - timedelta(hours=back),
                                    rating_amps=1000.0 + 10 * index + back)
                for index, city in enumerate(config.LOCATIONS) for back in (2, 1, 0)]
        with psycopg.connect(url) as conn:
            local_pg.insert_rows(conn, rows)
        yield url


def _replace_city_rows(conn, rows):
    """As the superuser inside the open transaction: empty city_rating, then insert `rows`."""
    conn.execute("delete from public.city_rating")
    local_pg.insert_rows(conn, rows)


def _drop_hour_check(conn):
    # The whole-hour CHECK is dropped inside the rolled-back transaction only, so a row can sit at
    # an exact age before the transaction's fixed now().
    conn.execute("alter table public.city_rating drop constraint city_rating_valid_time_hour_ck")


def _log_rows(conn):
    """The log as {city: (latest_valid_time, age_seconds, breach)} after one `log_freshness()` call."""
    rows = conn.execute(
        "select city, latest_valid_time, age_seconds, breach from ops.freshness_log order by city").fetchall()
    return {city: (valid, age, breach) for city, valid, age, breach in rows}


def test_tracer_log_freshness_matches_the_view(pg_url):
    with _session(pg_url) as conn:
        written = conn.execute("select ops.log_freshness()").fetchone()[0]
        assert written == 4
        log = _log_rows(conn)
        view = {city: (valid, stale) for city, valid, stale in conn.execute(
            "select city, valid_time, is_stale from public.latest_rating").fetchall()}
        count = conn.execute("select count(*) from ops.freshness_log").fetchone()[0]
    assert count == 4
    assert sorted(log) == sorted(config.LOCATIONS) == sorted(view)
    for city, (valid, age, breach) in log.items():
        assert valid == view[city][0], city
        assert breach is view[city][1], city             # the log carries the view's own flag
        assert age is not None and (age > _STALE_SECONDS) is breach, city   # D-02: one rule, 90 minutes
        assert 0 <= age <= 3600, city                    # the seeded newest slot is the current UTC hour
    # One probe is one instant: all four rows share probed_at.
    with _session(pg_url) as conn:
        conn.execute("select ops.log_freshness()")
        assert conn.execute("select count(distinct probed_at) from ops.freshness_log").fetchone()[0] == 1


def test_two_hour_old_rows_are_breaches_and_one_hour_old_are_not(pg_url):
    for minutes, expected_breach in ((120, True), (60, False)):
        with _session(pg_url) as conn:
            now = conn.execute("select now()").fetchone()[0]
            _drop_hour_check(conn)
            slot = now - timedelta(minutes=minutes)
            _replace_city_rows(conn, [local_pg.rating_row(city, slot) for city in config.LOCATIONS])
            assert conn.execute("select ops.log_freshness()").fetchone()[0] == 4
            log = _log_rows(conn)
        assert sorted(log) == sorted(config.LOCATIONS)
        for city, (valid, age, breach) in log.items():
            assert valid == slot, city
            assert age == minutes * 60, (city, age)       # exact seconds, not rounded
            assert breach is expected_breach, (city, minutes)
            assert (age > _STALE_SECONDS) is breach, city


def test_exactly_90_minutes_is_fresh_in_the_log_and_one_microsecond_more_is_a_breach(pg_url):
    # OD-4 adjacency edge: the log, the view and assert_fresh apply one 90-minute rule.
    from decimal import Decimal

    cases = ((timedelta(0), False), (timedelta(microseconds=1), True))
    for extra, expected_breach in cases:
        with _session(pg_url) as conn:
            now = conn.execute("select now()").fetchone()[0]
            _drop_hour_check(conn)
            slot = now - timedelta(minutes=90) - extra
            _replace_city_rows(conn, [local_pg.rating_row(city, slot) for city in config.LOCATIONS])
            conn.execute("select ops.log_freshness()")
            log = _log_rows(conn)
            view_flags = {row[0] for row in conn.execute("select is_stale from public.latest_rating").fetchall()}
        assert view_flags == {expected_breach}
        for city, (_, age, breach) in log.items():
            assert breach is expected_breach, (city, extra)
            assert age == Decimal(_STALE_SECONDS) + Decimal(extra.microseconds) / Decimal(1_000_000), (city, age)
            assert (age > _STALE_SECONDS) is breach, city


def test_missing_city_is_a_breach_with_null_age(pg_url):
    with _session(pg_url) as conn:
        conn.execute("delete from public.city_rating where city = 'EL_PASO'")
        assert conn.execute("select ops.log_freshness()").fetchone()[0] == 4   # one row per city, even a missing one
        log = _log_rows(conn)
    assert log["EL_PASO"] == (None, None, True)
    for city in ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND"):
        valid, age, breach = log[city]
        assert valid is not None and age is not None and breach is False, city


def test_anon_and_authenticated_cannot_reach_ops(pg_url):
    import psycopg

    for role in ("anon", "authenticated"):
        with _session(pg_url) as conn:
            assert conn.execute("select has_schema_privilege(%s, 'ops', 'usage')", [role]).fetchone()[0] is False
            assert conn.execute("select has_schema_privilege(%s, 'ops', 'create')", [role]).fetchone()[0] is False
            assert conn.execute("select has_table_privilege(%s, 'ops.freshness_log', 'select')", [role]).fetchone()[0] is False
            assert conn.execute("select has_sequence_privilege(%s, 'ops.freshness_log_id_seq', 'usage')",
                                [role]).fetchone()[0] is False
            assert conn.execute("select has_function_privilege(%s, 'ops.log_freshness()', 'execute')",
                                [role]).fetchone()[0] is False
        with _session(pg_url, role) as conn:
            for statement in ("select * from ops.freshness_log", "select ops.log_freshness()",
                              "insert into ops.freshness_log (city, breach) values ('AUSTIN', false)"):
                with pytest.raises(psycopg.Error) as denied, conn.transaction():
                    conn.execute(statement)
                assert _sqlstate(denied) == "42501", (role, statement)
    # No grant to PUBLIC either (a PUBLIC grant would reach anon as well).
    with _session(pg_url) as conn:
        schema_acl, table_acl, function_acl = conn.execute(
            "select (select nspacl::text from pg_namespace where nspname = 'ops'), "
            "(select relacl::text from pg_class where oid = 'ops.freshness_log'::regclass), "
            "(select proacl::text from pg_proc where oid = 'ops.log_freshness()'::regprocedure)").fetchone()
    for acl in (schema_acl, table_acl, function_acl):
        assert not re.search(r"(^\{|,)=", acl), acl      # an empty grantee name is PUBLIC
        assert "anon" not in acl and "authenticated" not in acl, acl


def test_dlr_writer_can_read_but_not_write_the_log(pg_url):
    import psycopg

    with _session(pg_url) as conn:
        conn.execute("select ops.log_freshness()")      # the owner's job writes; the writer role only reads
        conn.execute("set role dlr_writer")
        assert conn.execute("select count(*) from ops.freshness_log").fetchone()[0] == 4
        for statement in ("insert into ops.freshness_log (city, breach) values ('AUSTIN', false)",
                          "update ops.freshness_log set breach = true",
                          "delete from ops.freshness_log",
                          "truncate ops.freshness_log",
                          "select ops.log_freshness()"):
            with pytest.raises(psycopg.Error) as denied, conn.transaction():
                conn.execute(statement)
            assert _sqlstate(denied) == "42501", statement
        conn.execute("reset role")
        assert conn.execute("select has_schema_privilege('dlr_writer', 'ops', 'usage')").fetchone()[0] is True
        assert conn.execute("select has_schema_privilege('dlr_writer', 'ops', 'create')").fetchone()[0] is False


_MONITORING_CHECKS = (
    "assert_fresh_executable_by_anon",
    "dlr_writer_can_read_freshness_log",
    "freshness_log_not_readable_by_anon_or_authenticated",
    "freshness_log_present",
    "log_freshness_not_executable_by_anon_or_authenticated",
    "log_freshness_present",
    "ops_schema_not_usable_by_anon_or_authenticated",
)


def _failing(conn):
    return {row["check_name"] for row in local_pg.run_select_file(conn, _VERIFY_MONITORING_SQL) if row["ok"] is not True}


def test_verify_monitoring_sql_reports_every_check_ok(pg_url):
    with open(_VERIFY_MONITORING_SQL, encoding="utf-8") as handle:
        raw = handle.read()
    code = "\n".join(line.split("--", 1)[0] for line in raw.splitlines())
    bare = re.sub(r"'(?:[^']|'')*'", "''", code)  # string literals may hold a semicolon or a keyword
    statements = [s.strip() for s in bare.split(";") if s.strip()]
    assert len(statements) == 1
    assert re.match(r"(select|with)\b", statements[0], re.IGNORECASE)
    for forbidden in ("insert ", "update ", "delete ", "drop ", "alter ", "create ", "grant ", "revoke ",
                      "truncate ", "set role", "pg_sleep"):
        assert forbidden not in statements[0].lower(), forbidden
    for name in _MONITORING_CHECKS:
        assert f"'{name}'" in code, name

    with _session(pg_url) as conn:
        rows = local_pg.run_select_file(conn, _VERIFY_MONITORING_SQL)
        assert [r["check_name"] for r in rows] == sorted(_MONITORING_CHECKS)
        assert all(set(r) == {"check_name", "ok", "detail"} for r in rows)
        assert [(r["check_name"], r["detail"]) for r in rows if r["ok"] is not True] == []

    # Each check can fail: a stray grant, a stray execute, a missing object or a lost role right.
    with _session(pg_url) as conn:
        conn.execute("grant usage on schema ops to authenticated")
        assert _failing(conn) == {"ops_schema_not_usable_by_anon_or_authenticated"}
    with _session(pg_url) as conn:
        conn.execute("grant select on ops.freshness_log to anon")
        assert _failing(conn) == {"freshness_log_not_readable_by_anon_or_authenticated"}
    with _session(pg_url) as conn:
        conn.execute("grant execute on function ops.log_freshness() to anon")
        assert _failing(conn) == {"log_freshness_not_executable_by_anon_or_authenticated"}
    with _session(pg_url) as conn:
        conn.execute("revoke select on ops.freshness_log from dlr_writer")
        assert _failing(conn) == {"dlr_writer_can_read_freshness_log"}
    with _session(pg_url) as conn:
        conn.execute("grant insert on ops.freshness_log to dlr_writer")
        assert _failing(conn) == {"dlr_writer_can_read_freshness_log"}
    with _session(pg_url) as conn:
        conn.execute("revoke execute on function public.assert_fresh(integer) from anon")
        assert _failing(conn) == {"assert_fresh_executable_by_anon"}
    with _session(pg_url) as conn:
        conn.execute("drop function ops.log_freshness()")
        assert _failing(conn) == {"log_freshness_present", "log_freshness_not_executable_by_anon_or_authenticated"}
    with _session(pg_url) as conn:
        conn.execute("drop table ops.freshness_log")
        assert {"freshness_log_present", "freshness_log_not_readable_by_anon_or_authenticated"} <= _failing(conn)

    # With the role absent the check is true and says why (a project that never created dlr_writer).
    with _session(pg_url) as conn:
        conn.execute("drop owned by dlr_writer")
        conn.execute("drop role dlr_writer")
        rows = {r["check_name"]: r for r in local_pg.run_select_file(conn, _VERIFY_MONITORING_SQL)}
        assert rows["dlr_writer_can_read_freshness_log"]["ok"] is True
        assert "role absent" in rows["dlr_writer_can_read_freshness_log"]["detail"]


def _ops_snapshot(conn):
    """Everything the soak migration decides, as plain values."""
    return (
        conn.execute("select nspacl::text from pg_namespace where nspname = 'ops'").fetchone(),
        conn.execute("select c.relname, c.relkind::text, c.relacl::text from pg_class c join pg_namespace n "
                     "on n.oid = c.relnamespace where n.nspname = 'ops' order by 1").fetchall(),
        conn.execute("select pg_get_functiondef('ops.log_freshness()'::regprocedure), "
                     "(select proacl::text from pg_proc where oid = 'ops.log_freshness()'::regprocedure)").fetchone(),
        conn.execute("select a.attname, col_description(a.attrelid, a.attnum) from pg_attribute a "
                     "where a.attrelid = 'ops.freshness_log'::regclass and a.attnum > 0 and not a.attisdropped "
                     "order by a.attnum").fetchall(),
        conn.execute("select obj_description('ops.freshness_log'::regclass, 'pg_class'), "
                     "obj_description('ops.log_freshness()'::regprocedure, 'pg_proc')").fetchone(),
        conn.execute("select indexdef from pg_indexes where schemaname = 'ops' order by indexname").fetchall(),
    )


def test_soak_migration_reapplies_cleanly(pg_url):
    sql_text = _raw()
    with _session(pg_url) as conn:
        conn.execute("select ops.log_freshness()")
        before = _ops_snapshot(conn)
        rows_before = conn.execute("select id, probed_at, city, latest_valid_time, age_seconds, breach "
                                   "from ops.freshness_log order by id").fetchall()
        conn.execute(sql_text)          # the second (and a third) apply of an already-applied migration
        conn.execute(sql_text)
        after = _ops_snapshot(conn)
        rows_after = conn.execute("select id, probed_at, city, latest_valid_time, age_seconds, breach "
                                  "from ops.freshness_log order by id").fetchall()
    assert after == before
    assert rows_after == rows_before and len(rows_after) == 4   # re-applying never touches logged rows
    # Every grant on the objects is the one the migration states: nothing for the consumer roles.
    schema_acl = before[0][0]
    assert "dlr_writer=U/" in schema_acl
    assert "anon" not in schema_acl and "authenticated" not in schema_acl
    # Every column carries a unit-first comment.
    assert [name for name, _ in before[3]] == ["id", "probed_at", "city", "latest_valid_time", "age_seconds", "breach"]
    for name, text in before[3]:
        assert text and text.strip(), name
    assert before[4][0] and before[4][1]
