"""
Throwaway local Postgres harness for the Phase 6 exposure tests (production-pipeline,
API-01 and the later E2E tests that reuse it).

A helper, not a test module: the name matches no pytest collection pattern, and
`pytest.ini` puts `backend/` on the path, so a test imports it as `import local_pg`.

What it touches: only a private cluster that it starts on 127.0.0.1 under pytest's tmp
dir (initdb with trust auth, no unix socket) when `DLR_TEST_PG_AUTOSTART=1`, or a
uniquely named scratch database inside the local server named by
`DLR_TEST_DATABASE_URL` (host 127.0.0.1, localhost or ::1; anything else fails the
test). The cluster is always stopped, the scratch database always dropped. It never
touches Supabase, reads no `.env` and makes no network call.

`SUPABASE_ROLES_SQL` rebuilds the worst case the migration has to survive: Supabase's
legacy default grants, which hand every new public table and sequence to anon,
authenticated and service_role in full.
"""

import contextlib
import os
import shutil
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

import pytest

import config

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "supabase", "migrations")

_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")

# Roles a plain cluster lacks, plus Supabase's legacy auto-grants on future public objects.
SUPABASE_ROLES_SQL = """
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'service_role') then
        create role service_role nologin;
    end if;
end
$$;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
"""


def migration_files():
    """Every migration path, in the order `supabase db push` applies them."""
    return [os.path.join(MIGRATIONS_DIR, name)
            for name in sorted(os.listdir(MIGRATIONS_DIR)) if name.endswith(".sql")]


def _explicit_url():
    explicit = os.environ.get("DLR_TEST_DATABASE_URL")
    if explicit:
        host = urlsplit(explicit).hostname
        if host not in _LOCAL_HOSTS:
            pytest.fail("DLR_TEST_DATABASE_URL must name a local database (127.0.0.1, localhost or ::1)")
    return explicit or None


def require_local_pg():
    """Skip unless a local throwaway Postgres may be used; fail for a non-local URL."""
    if _explicit_url():
        pytest.importorskip("psycopg")
        return
    if os.environ.get("DLR_TEST_PG_AUTOSTART") != "1":
        pytest.skip("set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the live Postgres tests")
    pytest.importorskip("psycopg")
    if shutil.which("initdb") is None or shutil.which("pg_ctl") is None:
        pytest.skip("initdb / pg_ctl not on PATH")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def cluster(tmp_path_factory):
    """
    Yield an administrator URL to an EMPTY database on a local server, then clean up.

    Autostart: initdb + pg_ctl under a pytest tmp dir, always stopped in a `finally`.
    Explicit URL: a uniquely named database is created beside the named one and
    dropped afterwards.
    """
    import psycopg

    explicit = _explicit_url()
    if explicit:
        name = "dlr_test_" + uuid.uuid4().hex[:12]
        with psycopg.connect(explicit, autocommit=True) as conn:
            conn.execute(f'create database "{name}"')
        parts = urlsplit(explicit)
        scratch = parts._replace(path="/" + name).geturl()
        try:
            yield scratch
        finally:
            with psycopg.connect(explicit, autocommit=True) as conn:
                conn.execute(f'drop database if exists "{name}" with (force)')
        return

    root = tmp_path_factory.mktemp("pg")
    data = str(root / "data")
    log_file = str(root / "log")
    port = _free_port()
    subprocess.run(
        ["initdb", "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-locale"],
        check=True, capture_output=True,
    )
    options = (f"-p {port} -c listen_addresses=127.0.0.1 -c unix_socket_directories='' "
               "-c fsync=off -c synchronous_commit=off")
    try:
        subprocess.run(
            ["pg_ctl", "-D", data, "-l", log_file, "-w", "-o", options, "start"],
            check=True, capture_output=True,
        )
        with psycopg.connect(f"postgresql://postgres@127.0.0.1:{port}/postgres", autocommit=True) as conn:
            conn.execute("create database dlr_test")
        yield f"postgresql://postgres@127.0.0.1:{port}/dlr_test"
    finally:
        subprocess.run(["pg_ctl", "-D", data, "-m", "immediate", "stop"], capture_output=True)


def apply_migrations(admin_url, paths=None):
    """The Supabase roles and legacy default grants first, then each file in its own transaction."""
    import psycopg

    with psycopg.connect(admin_url) as conn:
        conn.execute(SUPABASE_ROLES_SQL)
    for path in (migration_files() if paths is None else list(paths)):
        with open(path, encoding="utf-8") as handle:
            sql = handle.read()
        with psycopg.connect(admin_url) as conn:
            conn.execute(sql)


def rating_row(city, valid_time, **overrides):
    """A complete valid city_rating row: every NOT NULL column filled, no diagnostics."""
    row = {
        "city": city,
        "valid_time": valid_time,
        "rating_amps": 1000.0,
        "rating_mw": 568.0,
        "static_rating_amps": 900.0,
        "static_rating_mw": 511.0,
        "line_voltage_kv": 345.0,
        "power_factor": 0.95,
        "status": "ok",
        "fallback": False,
        "fallback_gates": [],
        "alerts": [],
        "exhausted": False,
        "rating_basis": config.RATING_BASIS,
        "config_version": config.RATING_CONFIG_VERSION,
        "config_fingerprint": "ab" * 32,
        "origin": "live",
        "run_id": "test-run",
        "pipeline_version": "test000",
    }
    row.update(overrides)
    return row


def insert_rows(conn, rows, update_on_conflict=()):
    """
    Parameter-bound INSERT of the given row dicts into public.city_rating. With
    `update_on_conflict` (column names), a row whose (city, valid_time) key exists is
    updated in those columns instead, the shape of Phase 4's upsert (OD-7).
    """
    from psycopg import sql

    for row in rows:
        columns = list(row)
        statement = sql.SQL("insert into public.city_rating ({}) values ({})").format(
            sql.SQL(", ").join(sql.Identifier(c) for c in columns),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        if update_on_conflict:
            statement += sql.SQL(" on conflict (city, valid_time) do update set {}").format(
                sql.SQL(", ").join(
                    sql.SQL("{0} = excluded.{0}").format(sql.Identifier(c)) for c in update_on_conflict)
            )
        conn.execute(statement, [row[c] for c in columns])


def run_select_file(conn, path):
    """Run a one-statement SQL file and return its rows as dicts."""
    from psycopg.rows import dict_row

    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(text)
        return cur.fetchall()


def current_utc_hour():
    """The current UTC hour as an aware datetime."""
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
