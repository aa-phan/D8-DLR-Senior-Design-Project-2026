"""
Database smoke test (production-pipeline Phase 4: DB-04)
==================================================
One-command live check of the production database connection as the CI writer
role. Run it as the role the pipeline will use (`SUPABASE_DB_URL`); it proves:

  connected                  the session pooler accepts the connection
  role_is_dlr_writer         the session user is the least-privilege writer
  ssl_in_use                 the connection is encrypted
  server_version_ge_15       the server is PostgreSQL 15 or newer
  session_timezone_utc       the session time zone is UTC after connect() (the writer pins it)
  tables_exist               public.city_rating and public.pipeline_run exist
  rls_enabled                row-level security is on for both
  writer_policies_exist      the dlr_writer policy is present on both (without it the
                             writer sees zero rows and gets no error)
  writer_privileges_exact    SELECT, INSERT, UPDATE and no DELETE, TRUNCATE on both
  consumers_cannot_write     anon and authenticated hold no write privilege on either
  rating_upsert_idempotent   a sentinel rating written twice leaves one row and the
                             first_written_at stays as it was (OD-7)
  run_row_idempotent         a sentinel run row written twice leaves one row
  delete_denied              the writer cannot remove a row
  utc_hour_check_zone_independent
                             the hour CHECK is evaluated in UTC: in an Asia/Kolkata (UTC+05:30)
                             session a whole UTC hour is accepted and 01:30Z is refused
  rows_visible               (--expect-rows) every city has at least one row

Every write happens inside ONE transaction that is always rolled back
(`force_rollback=True`), so a completed, interrupted or concurrent run leaves no row
in either table. The output holds only booleans, counts, the role name, the server
version number and UTC times; never a URL, host, project reference or credential.

Exit codes: 0 every check passed, 1 a check failed or the connection failed,
2 SUPABASE_DB_URL is missing or blank (no connection is attempted).

The owner runs it from the repository root with the secret read from .env:

    PYTHONPATH=backend .venv/bin/python -c "from dotenv import load_dotenv; \\
load_dotenv('.env'); import sys, supabase_smoke; sys.exit(supabase_smoke.main([]))"

The Actions workflow (.github/workflows/supabase_smoke.yml) runs
`PYTHONPATH=backend python backend/supabase_smoke.py` with the secret in the step env.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import city_point
import config
import supabase_store

REPORT_SCHEMA = "supabase_smoke/1"
TABLES = ("public.city_rating", "public.pipeline_run")
POLICY_NAME = "dlr_writer_all"
SENTINEL_RUN_ID = "smoke-sentinel"
SENTINEL_END = "2000-01-01T00:00:00Z"
SENTINEL_FIRST_WRITTEN = "2000-01-02T03:04:05Z"
HOUR_CHECK_NAME = "city_rating_valid_time_hour_ck"
ZONE_PROBE_ZONE = "Asia/Kolkata"  # UTC+05:30: whole hours there are half hours in UTC
ZONE_PROBE_WHOLE_HOUR = "2000-01-01T01:00:00Z"
ZONE_PROBE_HALF_HOUR = "2000-01-01T01:30:00Z"  # 07:00 in Asia/Kolkata
CONSUMER_ROLES = ("anon", "authenticated")
WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE")


def _scalar(conn, sql, params=None):
    return conn.execute(sql, params).fetchone()[0]


def _sentinel_row():
    """A valid AUSTIN rating at its static rating, in the year 2000 so it can never be a real slot."""
    rating = float(city_point.city_point("AUSTIN").static_rating)
    result = {
        "city": "AUSTIN", "station_id": None, "candidates_probed": 0, "probe_trail": [],
        "rating": rating, "status": "fallback", "fallback": True, "alerts": [],
        "observation": None, "exhausted": False,
        "pipeline": {"forecast_method": "naive", "forecast_used_by_g6": False, "forecast": None,
                     "detector_model": None},
    }
    ctx = {"run_id": SENTINEL_RUN_ID, "run_attempt": 1, "pipeline_version": "smoke"}
    return supabase_store.build_rating_row(result, SENTINEL_END, ctx)


class _Checks:
    """Ordered check results; each is True, False or 'skipped'."""

    def __init__(self):
        self.results = {}

    def run(self, name, function):
        try:
            outcome = function()
        except Exception as exc:  # noqa: BLE001 - a failed probe is a failed check, reported redacted
            print(f"  {name}: {type(exc).__name__}: {supabase_store.redact(str(exc))}")
            outcome = False
        self.results[name] = outcome if outcome == "skipped" else bool(outcome)
        label = "skipped" if outcome == "skipped" else ("ok" if outcome else "FAILED")
        print(f"check {name}: {label}")
        return self.results[name]

    def failed(self):
        return [name for name, value in self.results.items() if value is False]


def _privilege(conn, role, table, privilege):
    return _scalar(conn, "select has_table_privilege(%(role)s, %(table)s, %(priv)s)",
                   {"role": role, "table": table, "priv": privilege})


def _roles_present(conn):
    rows = conn.execute("select rolname from pg_roles where rolname = any(%(names)s)",
                        {"names": list(CONSUMER_ROLES)}).fetchall()
    return [row[0] for row in rows]


def _rating_upsert_idempotent(conn):
    row = _sentinel_row()
    key = {"city": row["city"], "slot": row["valid_time"]}
    supabase_store.upsert_rating(conn, row)
    # Inside one transaction now() is constant, so move first_written_at to a known past
    # value; a rewrite that touched it would then show.
    conn.execute(
        "update public.city_rating set first_written_at = %(stamp)s where city = %(city)s and valid_time = %(slot)s",
        dict(key, stamp=SENTINEL_FIRST_WRITTEN),
    )
    supabase_store.upsert_rating(conn, dict(row, rating_amps=row["rating_amps"] + 1.0))
    count = _scalar(conn, "select count(*) from public.city_rating where city = %(city)s and valid_time = %(slot)s", key)
    first, amps = conn.execute(
        "select first_written_at, rating_amps from public.city_rating where city = %(city)s and valid_time = %(slot)s", key
    ).fetchone()
    return (
        count == 1
        and first == datetime(2000, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        and amps == row["rating_amps"] + 1.0
    )


def _run_row_idempotent(conn):
    supabase_store.upsert_run(conn, {"run_id": SENTINEL_RUN_ID, "provider": "smoke-1"})
    supabase_store.upsert_run(conn, {"run_id": SENTINEL_RUN_ID, "provider": "smoke-2"})
    count = _scalar(conn, "select count(*) from public.pipeline_run where run_id = %(id)s", {"id": SENTINEL_RUN_ID})
    provider = _scalar(conn, "select provider from public.pipeline_run where run_id = %(id)s", {"id": SENTINEL_RUN_ID})
    return count == 1 and provider == "smoke-2"


def _delete_denied(conn):
    import psycopg

    try:
        with conn.transaction():
            conn.execute("delete from public.city_rating where valid_time = %(slot)s",
                         {"slot": _sentinel_row()["valid_time"]})
    except psycopg.errors.InsufficientPrivilege:
        return True
    return False


def _utc_hour_check_zone_independent(conn):
    """
    The hour CHECK holds in UTC whatever the session zone: in a +05:30 session a whole UTC
    hour is accepted and a UTC half hour that is a whole hour locally is refused. Runs in a
    nested rolled-back savepoint, so the zone setting and both rows vanish.
    """
    import psycopg

    row = _sentinel_row()
    with conn.transaction(force_rollback=True):
        conn.execute(f"set local timezone = '{ZONE_PROBE_ZONE}'")
        try:
            conn.execute(supabase_store.UPSERT_RATING_SQL, dict(row, valid_time=ZONE_PROBE_WHOLE_HOUR))
        except psycopg.errors.CheckViolation:
            return False  # a valid UTC slot was refused: the session-zone form of the CHECK
        try:
            with conn.transaction():
                conn.execute(supabase_store.UPSERT_RATING_SQL, dict(row, valid_time=ZONE_PROBE_HALF_HOUR))
        except psycopg.errors.CheckViolation as exc:
            return exc.diag.constraint_name == HOUR_CHECK_NAME
    return False


def _write_report(path, report):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")


def _finish(checks, info, report_path):
    failed = checks.failed()
    report = {
        "schema": REPORT_SCHEMA,
        "checks": checks.results,
        "info": info,
        "all_passed": not failed,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if report_path:
        _write_report(report_path, report)
    if failed:
        print("SMOKE FAILED: " + ", ".join(failed))
        return 1
    print("SMOKE OK")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check the production database connection as the writer role.")
    parser.add_argument("--report", default=None, help="write the check report JSON here")
    parser.add_argument("--expect-rows", action="store_true", help="fail when any city has no row")
    parser.add_argument("--allow-no-ssl", action="store_true",
                        help="local throwaway databases only: record ssl_in_use as skipped")
    args = parser.parse_args(argv)

    if not os.environ.get("SUPABASE_DB_URL", "").strip():
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2

    checks = _Checks()
    info = {}
    try:
        conn = supabase_store.connect()
    except supabase_store.StoreError as exc:
        print(f"check connected: FAILED ({exc})")
        checks.results["connected"] = False
        return _finish(checks, info, args.report)

    try:
        checks.results["connected"] = True
        print("check connected: ok")
        role = _scalar(conn, "select current_user")
        info["role"] = role
        info["server_version_num"] = int(conn.info.server_version)
        checks.run("role_is_dlr_writer", lambda: role == "dlr_writer")
        if args.allow_no_ssl:
            checks.results["ssl_in_use"] = "skipped"
            print("check ssl_in_use: skipped")
        else:
            checks.run("ssl_in_use", lambda: bool(conn.pgconn.ssl_in_use))
        checks.run("server_version_ge_15", lambda: conn.info.server_version >= 150000)
        checks.run("session_timezone_utc", lambda: _scalar(conn, "show timezone") == "UTC")
        checks.run("tables_exist", lambda: all(
            _scalar(conn, "select to_regclass(%(t)s) is not null", {"t": table}) for table in TABLES))

        def rls_enabled():
            rows = conn.execute(
                "select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relname in ('city_rating', 'pipeline_run')"
            ).fetchall()
            return len(rows) == 2 and all(flag for _, flag in rows)

        def policies_exist():
            rows = conn.execute(
                "select tablename from pg_policies where schemaname = 'public' and policyname = %(p)s",
                {"p": POLICY_NAME},
            ).fetchall()
            return sorted(r[0] for r in rows) == ["city_rating", "pipeline_run"]

        def writer_privileges_exact():
            for table in TABLES:
                for privilege in ("SELECT", "INSERT", "UPDATE"):
                    if not _privilege(conn, "dlr_writer", table, privilege):
                        return False
                for privilege in ("DELETE", "TRUNCATE"):
                    if _privilege(conn, "dlr_writer", table, privilege):
                        return False
            return True

        def consumers_cannot_write():
            present = _roles_present(conn)
            for role_name in present:
                for table in TABLES:
                    if any(_privilege(conn, role_name, table, p) for p in WRITE_PRIVILEGES):
                        return False
            # Informational only: Phase 6 grants anon SELECT.
            info["anon_can_select"] = bool(
                "anon" in present and _privilege(conn, "anon", "public.city_rating", "SELECT"))
            return True

        checks.run("rls_enabled", rls_enabled)
        checks.run("writer_policies_exist", policies_exist)
        checks.run("writer_privileges_exact", writer_privileges_exact)
        checks.run("consumers_cannot_write", consumers_cannot_write)

        # Every write below is rolled back, whatever happens.
        with conn.transaction(force_rollback=True):
            checks.run("rating_upsert_idempotent", lambda: _rating_upsert_idempotent(conn))
            checks.run("run_row_idempotent", lambda: _run_row_idempotent(conn))
            checks.run("delete_denied", lambda: _delete_denied(conn))
            checks.run("utc_hour_check_zone_independent", lambda: _utc_hour_check_zone_independent(conn))

        city_rows = {}
        try:
            for city, count, newest in conn.execute(
                "select city, count(*), max(valid_time) from public.city_rating group by city order by city"
            ).fetchall():
                city_rows[city] = {"rows": int(count), "newest": newest.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        except Exception as exc:  # noqa: BLE001
            print(f"  could not count rows: {type(exc).__name__}: {supabase_store.redact(str(exc))}")
        info["city_rows"] = city_rows
        for city in config.LOCATIONS:
            entry = city_rows.get(city)
            print(f"city {city}: rows {entry['rows'] if entry else 0}, newest {entry['newest'] if entry else 'none'}")

        if args.expect_rows:
            empty = [city for city in config.LOCATIONS if not city_rows.get(city, {}).get("rows")]

            def rows_visible():
                if empty:
                    print("  no rows for: " + ", ".join(empty))
                return not empty

            checks.run("rows_visible", rows_visible)
    except Exception as exc:  # noqa: BLE001 - never print more than the type and the redacted text
        print(f"smoke test stopped: {type(exc).__name__}: {supabase_store.redact(str(exc))}")
        checks.results.setdefault("completed", False)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return _finish(checks, info, args.report)


if __name__ == "__main__":
    sys.exit(main())
