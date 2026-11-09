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


# ---------------------------------------------------------------------------
# Task 2: the owner's pg_cron scripts and the probe smoke check, against a stub cron schema.
# ---------------------------------------------------------------------------

_JOB = "dlr-soak-freshness"
_SCHEDULE = "*/5 * * * *"
_COMMAND = "select ops.log_freshness()"
_SCHEDULE_SQL = os.path.join(_OPS_DIR, "soak_cron_schedule.sql")
_UNSCHEDULE_SQL = os.path.join(_OPS_DIR, "soak_cron_unschedule.sql")
_SMOKE_SQL = os.path.join(_OPS_DIR, "soak_probe_smoke.sql")

_SMOKE_CHECKS = (
    "last_three_probes_wrote_four_rows",
    "last_three_runs_succeeded",
    "no_breach_in_the_last_three_probes",
    "soak_job_active_every_5_minutes",
)

# pg_cron is not installed locally. This stub has the documented tables and the two functions the
# owner scripts call, so the scripts run exactly as written (06-RESEARCH, Supabase Cron docs).
_STUB_CRON_SQL = """
create schema cron;
create table cron.job (
    jobid bigint generated always as identity primary key,
    schedule text not null,
    command text not null,
    nodename text not null default 'localhost',
    nodeport integer not null default 5432,
    database text not null default current_database(),
    username text not null default current_user,
    active boolean not null default true,
    jobname text unique
);
create table cron.job_run_details (
    jobid bigint,
    runid bigint generated always as identity primary key,
    job_pid integer,
    database text,
    username text,
    command text,
    status text,
    return_message text,
    start_time timestamptz,
    end_time timestamptz
);
create function cron.schedule(job_name text, schedule text, command text) returns bigint
language plpgsql as $$
declare
    id bigint;
begin
    insert into cron.job (jobname, schedule, command) values (job_name, schedule, command)
    on conflict (jobname) do update set schedule = excluded.schedule, command = excluded.command, active = true
    returning jobid into id;
    return id;
end
$$;
create function cron.unschedule(job_id bigint) returns boolean
language plpgsql as $$
begin
    delete from cron.job where jobid = job_id;
    return found;
end
$$;
"""


def _install_stub_cron(conn):
    conn.execute(_STUB_CRON_SQL)


def _run_file(conn, path):
    """Run an owner SQL file as pasted in the SQL editor; return the rows of every result set, as dicts."""
    from psycopg.rows import dict_row

    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    results = []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(text)
        while True:
            if cur.description is not None:
                results.append(cur.fetchall())
            if not cur.nextset():
                break
    return results


def _jobs(conn, name=_JOB):
    return conn.execute("select jobid, jobname, schedule, command, active from cron.job where jobname = %s",
                        [name]).fetchall()


def test_schedule_file_creates_one_job_and_is_repeatable(pg_url):
    with _session(pg_url) as conn:
        _install_stub_cron(conn)
        conn.execute("select cron.schedule('some-other-job', '0 * * * *', 'select 1')")
        results = _run_file(conn, _SCHEDULE_SQL)
        shown = results[-1]                      # the SQL editor shows the last result: the job row
        assert len(shown) == 1
        assert {k: shown[0][k] for k in ("jobname", "schedule", "command", "active")} == {
            "jobname": _JOB, "schedule": _SCHEDULE, "command": _COMMAND, "active": True}
        assert set(shown[0]) == {"jobid", "jobname", "schedule", "command", "active"}
        first = _jobs(conn)
        assert len(first) == 1
        _run_file(conn, _SCHEDULE_SQL)           # run twice: the same named job is updated, not duplicated
        again = _jobs(conn)
        assert again == first
        # An existing job with a stale definition is brought back to the soak definition.
        conn.execute("update cron.job set schedule = '0 * * * *', active = false where jobname = %s", [_JOB])
        _run_file(conn, _SCHEDULE_SQL)
        assert _jobs(conn) == first
        assert len(_jobs(conn, "some-other-job")) == 1       # nothing else is touched


def test_unschedule_file_removes_the_job_and_is_a_no_op_after(pg_url):
    with _session(pg_url) as conn:
        _install_stub_cron(conn)
        conn.execute("select cron.schedule('some-other-job', '0 * * * *', 'select 1')")
        _run_file(conn, _SCHEDULE_SQL)
        assert len(_jobs(conn)) == 1
        results = _run_file(conn, _UNSCHEDULE_SQL)
        assert len(_jobs(conn)) == 0
        assert len(_jobs(conn, "some-other-job")) == 1       # the freshness alarm and any other job stay
        assert list(results[-1][0].values()) == [0]          # the editor reports 0 remaining
        again = _run_file(conn, _UNSCHEDULE_SQL)             # no row, no call: a no-op, not an error
        assert list(again[-1][0].values()) == [0]
        assert len(_jobs(conn, "some-other-job")) == 1


def _seed_healthy_soak(conn, probes=4):
    """The scheduled job, three succeeded runs and `probes` probes of four city rows, newest first."""
    now = conn.execute("select now()").fetchone()[0]
    _run_file(conn, _SCHEDULE_SQL)
    jobid = _jobs(conn)[0][0]
    for back in range(3):
        start = now - timedelta(minutes=5 * back)
        conn.execute("insert into cron.job_run_details (jobid, command, status, return_message, start_time, end_time) "
                     "values (%s, %s, 'succeeded', '1 row', %s, %s)", [jobid, _COMMAND, start, start + timedelta(seconds=1)])
    for back in range(probes):
        probed_at = now - timedelta(minutes=5 * back)
        for city in config.LOCATIONS:
            conn.execute("insert into ops.freshness_log (probed_at, city, latest_valid_time, age_seconds, breach) "
                         "values (%s, %s, %s, 600, false)", [probed_at, city, probed_at - timedelta(minutes=10)])
    return jobid, now


def _smoke(conn):
    rows = local_pg.run_select_file(conn, _SMOKE_SQL)
    assert [r["check_name"] for r in rows] == sorted(_SMOKE_CHECKS)
    assert all(set(r) == {"check_name", "ok", "detail"} for r in rows)
    return {r["check_name"]: r for r in rows}


def test_probe_smoke_passes_on_healthy_probes(pg_url):
    with _session(pg_url) as conn:
        _install_stub_cron(conn)
        jobid, now = _seed_healthy_soak(conn)
        # Evidence older than the last three runs and probes does not count: an old failure and an
        # old breach sit beyond the window and the checks still pass.
        conn.execute("insert into cron.job_run_details (jobid, command, status, start_time) values (%s, %s, 'failed', %s)",
                     [jobid, _COMMAND, now - timedelta(minutes=60)])
        conn.execute("insert into ops.freshness_log (probed_at, city, breach) values (%s, 'AUSTIN', true)",
                     [now - timedelta(minutes=60)])
        checks = _smoke(conn)
        assert [name for name, row in checks.items() if row["ok"] is not True] == []
        assert all(row["detail"] for row in checks.values())


@pytest.mark.parametrize("name, mutation, expected_failing", [
    ("a failed latest run",
     "update cron.job_run_details set status = 'failed', return_message = 'permission denied' "
     "where runid = (select runid from cron.job_run_details order by start_time desc limit 1)",
     {"last_three_runs_succeeded"}),
    ("only two runs so far",
     "delete from cron.job_run_details where runid = (select runid from cron.job_run_details order by start_time desc limit 1)",
     {"last_three_runs_succeeded"}),
    ("a probe with three rows",
     "delete from ops.freshness_log where id = (select id from ops.freshness_log order by probed_at desc, id desc limit 1)",
     {"last_three_probes_wrote_four_rows"}),
    ("a breach in the latest probe",
     "update ops.freshness_log set breach = true, age_seconds = 6000 "
     "where id = (select id from ops.freshness_log where city = 'MIDLAND' order by probed_at desc limit 1)",
     {"no_breach_in_the_last_three_probes"}),
    ("a missing city in the third probe",
     "delete from ops.freshness_log where city = 'EL_PASO' and probed_at = "
     "(select probed_at from ops.freshness_log order by probed_at desc offset 8 limit 1)",
     {"last_three_probes_wrote_four_rows"}),
    ("the job paused",
     "update cron.job set active = false",
     {"soak_job_active_every_5_minutes"}),
    ("the job on another schedule",
     "update cron.job set schedule = '*/10 * * * *'",
     {"soak_job_active_every_5_minutes"}),
    ("the job running another command",
     "update cron.job set command = 'select 1'",
     {"soak_job_active_every_5_minutes"}),
    ("the job unscheduled",
     "delete from cron.job",
     {"soak_job_active_every_5_minutes", "last_three_runs_succeeded"}),
    ("no probe written yet",
     "delete from ops.freshness_log",
     {"last_three_probes_wrote_four_rows", "no_breach_in_the_last_three_probes"}),
])
def test_probe_smoke_fails_on_a_failed_run_a_short_probe_or_a_breach(pg_url, name, mutation, expected_failing):
    with _session(pg_url) as conn:
        _install_stub_cron(conn)
        _seed_healthy_soak(conn)
        assert [n for n, row in _smoke(conn).items() if row["ok"] is not True] == []   # healthy before the fault
        conn.execute(mutation)
        checks = _smoke(conn)
        failing = {n for n, row in checks.items() if row["ok"] is not True}
        assert failing == expected_failing, (name, {n: checks[n]["detail"] for n in failing})
        for n in failing:
            assert checks[n]["detail"], (name, n)         # the owner is told why


def test_owner_sql_files_name_the_job_and_command():
    texts = {}
    for path in (_SCHEDULE_SQL, _UNSCHEDULE_SQL, _SMOKE_SQL):
        with open(path, encoding="utf-8") as handle:
            texts[path] = handle.read()
        assert _JOB in texts[path], path
        # Plain SQL the owner pastes in the SQL editor: no psql meta-commands, no transaction control.
        code = "\n".join(line.split("--", 1)[0] for line in texts[path].splitlines())
        assert not re.search(r"^\s*\\", code, re.MULTILINE), path
        assert not re.search(r"\b(begin|commit|rollback)\b", code, re.IGNORECASE), path
    schedule = "\n".join(line.split("--", 1)[0] for line in texts[_SCHEDULE_SQL].splitlines())
    assert schedule.count("cron.schedule(") == 1
    assert f"'{_JOB}'" in schedule and f"'{_SCHEDULE}'" in schedule and _COMMAND in schedule
    assert "cron.job" in schedule
    unschedule = "\n".join(line.split("--", 1)[0] for line in texts[_UNSCHEDULE_SQL].splitlines())
    assert unschedule.count("cron.unschedule(") == 1
    assert f"where jobname = '{_JOB}'" in unschedule
    assert "cron.schedule" not in unschedule
    # The smoke check is one read-only SELECT with the four named checks.
    code = "\n".join(line.split("--", 1)[0] for line in texts[_SMOKE_SQL].splitlines())
    bare = re.sub(r"'(?:[^']|'')*'", "''", code)
    statements = [s.strip() for s in bare.split(";") if s.strip()]
    assert len(statements) == 1 and re.match(r"(select|with)\b", statements[0], re.IGNORECASE)
    for forbidden in ("insert ", "update ", "delete ", "drop ", "alter ", "create ", "grant ", "revoke ",
                      "truncate ", "set role", "pg_sleep", "cron.schedule", "cron.unschedule"):
        assert forbidden not in statements[0].lower(), forbidden
    for name in _SMOKE_CHECKS:
        assert f"'{name}'" in code, name
    assert "check_name" in code and "detail" in code
