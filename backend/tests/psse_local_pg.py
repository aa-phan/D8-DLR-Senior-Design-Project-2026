"""
Local-Postgres harness for the PSS/E result-table proofs (pss-e-integration
Phase 1, DBX-01, WB-01, WB-02). Not a test module: its name matches none of
`test_*.py`, `*_test.py`, `*_TestSuite.py`, so pytest never collects it.

It never touches Supabase. It starts (or is pointed at) a throwaway local
Postgres, applies the two Phase 4 migrations and then the reference DDL
`docs/data-science/schema/psse_results_v1.sql`, and builds rows that satisfy
every CHECK so a test can change exactly one field.

Environment:
  DLR_TEST_DATABASE_URL  a local throwaway database (host 127.0.0.1, localhost
                         or ::1; anything else fails the test)
  DLR_TEST_PG_AUTOSTART  "1": run initdb and pg_ctl under pytest's temp dir
  PSSE_REQUIRE_PG        "1": a missing database, driver or binary is a failure,
                         never a skip

`psycopg` is imported inside functions only, so importing this module needs no
driver.
"""

import contextlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# The two Phase 4 migrations, spelled out on purpose: a glob would let production-pipeline
# Phase 6's future migrations change what this fixture applies.
PHASE4_MIGRATIONS = (
    os.path.join(REPO_ROOT, "supabase", "migrations", "20261019000000_create_city_rating.sql"),
    os.path.join(
        REPO_ROOT, "supabase", "migrations",
        "20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql",
    ),
)
REFERENCE_DDL = os.path.join(REPO_ROOT, "docs", "data-science", "schema", "psse_results_v1.sql")
CHECKS_SQL = os.path.join(REPO_ROOT, "docs", "data-science", "schema", "psse_results_v1_checks.sql")

RESULT_TABLES = (
    "psse_run",
    "psse_dispatched_capacity",
    "psse_voltage_margin",
    "psse_contingency_result",
)
CITIES = ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")

# Supabase creates these roles and (until its 2026-10-30 change) grants every new public
# table, sequence and function to them by default. Reproducing the legacy grants here is the
# worst case the reference DDL's explicit revoke must undo.
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
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
"""

_COLUMN_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
_JSONB_COLUMNS = ("ratings_used", "details")

# Per-conductor static ratings (A), subconductors per phase and line voltage the valid rows use.
_AMPS = {"AUSTIN": 1825.0, "CORPUS_CHRISTI": 1500.0, "MIDLAND": 1875.0, "EL_PASO": 1320.0}
_SUBCONDUCTORS = {"AUSTIN": 2, "CORPUS_CHRISTI": 2, "MIDLAND": 2, "EL_PASO": 1}
_LINE_KV = 345.0
_POWER_FACTOR = 0.95
_HEX64 = "0123456789abcdef" * 4


def _skip(reason):
    """Skip, or fail when PSSE_REQUIRE_PG=1 (a skipped database proof is a failed gate)."""
    if os.environ.get("PSSE_REQUIRE_PG") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


def require_local_pg():
    """
    Check the environment allows a local database proof. Returns the explicit local
    DLR_TEST_DATABASE_URL, or None when the harness should start its own cluster.
    """
    explicit = os.environ.get("DLR_TEST_DATABASE_URL")
    if explicit:
        if urlsplit(explicit).hostname not in LOCAL_HOSTS:
            pytest.fail("DLR_TEST_DATABASE_URL must name a local database (127.0.0.1, localhost or ::1)")
    elif os.environ.get("DLR_TEST_PG_AUTOSTART") != "1":
        _skip("set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the PSS/E Postgres proofs")
    try:
        import psycopg  # noqa: F401
    except ImportError:
        _skip("psycopg is not installed")
    if not explicit and (shutil.which("initdb") is None or shutil.which("pg_ctl") is None):
        _skip("initdb / pg_ctl not on PATH")
    return explicit


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _netloc(user, host, port):
    shown = f"[{host}]" if ":" in host else host
    return f"{user}@{shown}:{port}" if port else f"{user}@{shown}"


@contextlib.contextmanager
def cluster(tmp_path_factory):
    """
    Yield a superuser URL to an empty database: either a uniquely named database on the local
    server the caller named (dropped afterwards) or a private cluster this context manager
    creates and always stops.
    """
    import psycopg

    explicit = require_local_pg()
    if explicit:
        name = "psse_test_" + uuid.uuid4().hex[:8]
        with psycopg.connect(explicit, autocommit=True) as conn:
            conn.execute(f'create database "{name}"')
        parts = urlsplit(explicit)
        url = parts._replace(path="/" + name).geturl()
        try:
            yield url
        finally:
            with psycopg.connect(explicit, autocommit=True) as conn:
                conn.execute(f'drop database if exists "{name}" with (force)')
        return

    root = tmp_path_factory.mktemp("psse_pg")
    data = str(root / "data")
    log_file = str(root / "log")
    port = _free_port()
    subprocess.run(
        ["initdb", "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-locale"],
        check=True, capture_output=True,
    )
    options = f"-p {port} -c listen_addresses=127.0.0.1 -c fsync=off -c synchronous_commit=off"
    if os.name != "nt":
        # Windows creates no Unix socket by default and the quoted empty value does not
        # survive pg_ctl's command line there.
        options += " -c unix_socket_directories=''"
    try:
        # No pipes here: on Windows the server inherits pg_ctl's stdout/stderr handles, so a
        # captured pipe never reaches EOF and subprocess.run would wait for the server to exit.
        # The server log (log_file) keeps the diagnostics.
        subprocess.run(
            ["pg_ctl", "-D", data, "-l", log_file, "-w", "-o", options, "start"],
            check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with psycopg.connect(f"postgresql://postgres@127.0.0.1:{port}/postgres", autocommit=True) as conn:
            conn.execute("create database psse_test")
        yield f"postgresql://postgres@127.0.0.1:{port}/psse_test"
    finally:
        subprocess.run(["pg_ctl", "-D", data, "-m", "immediate", "stop"], capture_output=True)


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def apply_reference_ddl(admin_url):
    """Apply the reference DDL alone, in one transaction (the re-apply test uses this)."""
    import psycopg

    sql = _read(REFERENCE_DDL)
    with psycopg.connect(admin_url) as conn:
        conn.execute(sql)


def apply_schema(admin_url):
    """
    Create the Supabase roles and legacy default grants, apply the two Phase 4 migrations in
    name order, then the reference DDL, each in its own transaction.
    """
    import psycopg

    with psycopg.connect(admin_url) as conn:
        conn.execute(SUPABASE_ROLES_SQL)
    for path in PHASE4_MIGRATIONS:
        sql = _read(path)
        with psycopg.connect(admin_url) as conn:
            conn.execute(sql)
    apply_reference_ddl(admin_url)


def role_url(admin_url, role):
    """The same database as `role` (trust auth: no credential locally)."""
    parts = urlsplit(admin_url)
    return parts._replace(netloc=_netloc(role, parts.hostname, parts.port)).geturl()


def admin_rows(admin_url, sql, params=None):
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(admin_url, autocommit=True, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


def reset(admin_url):
    """Empty the four result tables as the superuser (one statement, so the foreign keys allow it)."""
    import psycopg

    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("truncate " + ", ".join("public." + name for name in RESULT_TABLES))


def insert_rows(conn, table, rows):
    """
    Insert dict rows into one of the four result tables. The table must be on the allow-list,
    every column name must be a plain identifier, and every value is a bound parameter;
    `ratings_used` and `details` are bound as jsonb.
    """
    if table not in RESULT_TABLES:
        raise ValueError("not a PSS/E result table: " + repr(table))
    for row in rows:
        names = list(row)
        for name in names:
            if not _COLUMN_NAME.match(name):
                raise ValueError("bad column name: " + repr(name))
        params = {}
        placeholders = []
        for name in names:
            value = row[name]
            if name in _JSONB_COLUMNS:
                params[name] = None if value is None else json.dumps(value, allow_nan=False)
                placeholders.append("%(" + name + ")s::jsonb")
            else:
                params[name] = value
                placeholders.append("%(" + name + ")s")
        conn.execute(
            "insert into public." + table + " (" + ", ".join(names) + ") values (" + ", ".join(placeholders) + ")",
            params,
        )


def make_run_id(n, when):
    """A run_id that matches the DDL pattern: psse-<UTC yyyymmddThhmmssZ>-<8 hex>."""
    stamp = when.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "psse-{}-{:08x}".format(stamp, n)


def _hour_floor(when):
    return when.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def valid_run_rows(run_id, started_at, outcome="fallback", violations=2, n_contingencies=3):
    """
    Rows for one complete run, keyed by table name, that satisfy every CHECK. `started_at` is a
    timezone-aware datetime. For outcome "fallback" every city is on the static rating with
    reason provisional; for "ok" every city used a city_rating row (valid time the previous
    whole UTC hour, computed six minutes after it). `violations` is 0, 1 or 2 contingency
    rows, each on its own contingency_id.
    """
    if outcome not in ("ok", "fallback"):
        raise ValueError("outcome must be ok or fallback")
    if violations not in (0, 1, 2):
        raise ValueError("violations must be 0, 1 or 2")
    slot = _hour_floor(started_at)
    finished_at = started_at + timedelta(seconds=90)
    link_valid = slot - timedelta(hours=1)
    link_computed = link_valid + timedelta(minutes=6)
    root3 = math.sqrt(3)

    ratings_used = {}
    dispatch = []
    margins = []
    for city in CITIES:
        per_conductor = _AMPS[city]
        subs = _SUBCONDUCTORS[city]
        circuit = per_conductor * subs
        applied_mva = root3 * _LINE_KV * circuit / 1000
        limit_mva = 1.2 * applied_mva
        dispatched_mva = min(applied_mva, limit_mva)
        dispatched_circuit = dispatched_mva * 1000 / (root3 * _LINE_KV)
        if outcome == "ok":
            source, reason, valid, computed = "city_rating", None, link_valid, link_computed
        else:
            source, reason, valid, computed = "static_fallback", "provisional", None, None
        ratings_used[city] = {
            "source": source,
            "fallback_reason": reason,
            "rating_amps_per_conductor": per_conductor,
            "subconductors_per_phase": subs,
        }
        dispatch.append({
            "run_id": run_id,
            "run_outcome": outcome,
            "city": city,
            "rating_source": source,
            "fallback_reason": reason,
            "city_rating_valid_time": valid,
            "city_rating_computed_at": computed,
            "applied_amps_per_conductor": per_conductor,
            "subconductors_per_phase": subs,
            "applied_amps_circuit": circuit,
            "line_voltage_kv": _LINE_KV,
            "applied_mva": applied_mva,
            "voltage_limit_mva": limit_mva,
            "dispatched_mva": dispatched_mva,
            "dispatched_amps_circuit": dispatched_circuit,
            "dispatched_amps_per_conductor": dispatched_circuit / subs,
            "power_factor": _POWER_FACTOR,
            "dispatched_mw": dispatched_mva * _POWER_FACTOR,
            "limiting_factor": "dlr_rating",
        })
        margins.append({
            "run_id": run_id,
            "run_outcome": outcome,
            "city": city,
            "method": "pv_curve",
            "base_transfer_mw": 800.0,
            "limit_transfer_mw": 1000.0,
            "margin_mw": 200.0,
            "margin_pct": 25.0,
            "voltage_limit_mva": limit_mva,
            "critical_bus": "5001",
            "min_voltage_pu": 0.97,
        })

    austin_limit = dispatch[0]["applied_mva"]
    contingencies = []
    if violations >= 1:
        observed = austin_limit * 1.05
        contingencies.append({
            "run_id": run_id,
            "run_outcome": outcome,
            "contingency_id": "BR-101-102-1",
            "violation_kind": "thermal_overload",
            "element_type": "branch",
            "element_id": "103-104-1",
            "city": "AUSTIN",
            "limit_value": austin_limit,
            "observed_value": observed,
            "exceeded_by": observed - austin_limit,
            "unit": "MVA",
        })
    if violations >= 2:
        contingencies.append({
            "run_id": run_id,
            "run_outcome": outcome,
            "contingency_id": "BR-201-202-1",
            "violation_kind": "voltage_low",
            "element_type": "bus",
            "element_id": "301",
            "city": None,
            "limit_value": 0.95,
            "observed_value": 0.91,
            "exceeded_by": 0.95 - 0.91,
            "unit": "pu",
        })

    run = {
        "run_id": run_id,
        "slot_time": slot,
        "started_at": started_at,
        "finished_at": finished_at,
        "outcome": outcome,
        "case_id": "summer_peak_case",
        "case_sha256": _HEX64,
        "mapping_sha256": _HEX64,
        "rate_set": "RATEA",
        "ratings_used": ratings_used,
        "n_contingencies": n_contingencies,
        "n_contingencies_with_results": len(contingencies),
        "job_version": "abc1234",
        "psse_version": "35.5.0",
    }
    return {
        "psse_run": [run],
        "psse_dispatched_capacity": dispatch,
        "psse_voltage_margin": margins,
        "psse_contingency_result": contingencies,
    }


def failed_run_row(run_id, started_at, stage="load_flow", error="load flow did not converge"):
    """One psse_run row for a failed run: error and stage set, no counts, no result rows."""
    ratings_used = {
        city: {
            "source": "static_fallback",
            "fallback_reason": "provisional",
            "rating_amps_per_conductor": _AMPS[city],
            "subconductors_per_phase": _SUBCONDUCTORS[city],
        }
        for city in CITIES
    }
    return {
        "run_id": run_id,
        "slot_time": _hour_floor(started_at),
        "started_at": started_at,
        "finished_at": started_at + timedelta(seconds=30),
        "outcome": "failed",
        "failed_stage": stage,
        "error": error,
        "case_id": "summer_peak_case",
        "ratings_used": ratings_used,
        "job_version": "abc1234",
    }
