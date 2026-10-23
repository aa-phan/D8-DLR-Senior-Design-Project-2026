"""
Tests of the DB-04 smoke test (production-pipeline Phase 4, DB-04).

Offline tests check the exit codes and that no part of a connection URL reaches the
output, the logs or the report. The live tests (env-gated, like supabase_live_test.py)
run the smoke test as the migration's own `dlr_writer` role against a throwaway local
Postgres and never touch Supabase.

Follows backend/tests/city_rating_test.py's conventions (module-level imports, plain
asserts, no test classes, no network).
"""

import json
import logging
import os
import re
import shutil
import socket
import subprocess
from urllib.parse import quote, urlsplit

import pytest
import requests

import anomaly_detector
import config
import supabase_smoke
import supabase_store

_MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")
_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")

# Markers assembled from pieces so no literal credential URL is in this file.
_USER = "mk7" + "user" + ".mk7ref"
_CREDENTIAL = "Mk7" + "@Zq9/" + "Leak"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """
    Replace `requests.get` for every test. The composer and `rate_city` catch
    every provider exception, so raising alone could be swallowed; the teardown
    assert on the recorded attempts cannot be.
    """
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    yield
    assert attempts == []


@pytest.fixture(autouse=True)
def _offline_env(tmp_path, monkeypatch):
    # Another test module loads `.env` into the process at import time.
    for name in ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "HISTORICAL_ARCHIVE_PATH", str(tmp_path / "default_archive.csv"))
    # Trained models are git-ignored, so a test must not depend on whether this
    # checkout has them.
    monkeypatch.setattr(anomaly_detector, "_load_city_model_or_none", lambda city: None)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def _pg_admin_url(tmp_path_factory):
    """
    URL of an empty throwaway database, as a superuser. Either the local
    database the caller named or a private cluster this fixture creates and
    always stops.
    """
    explicit = os.environ.get("DLR_TEST_DATABASE_URL")
    if explicit:
        host = urlsplit(explicit).hostname
        if host not in _LOCAL_HOSTS:
            pytest.fail("DLR_TEST_DATABASE_URL must name a local database (127.0.0.1, localhost or ::1)")
        yield explicit
        return
    if os.environ.get("DLR_TEST_PG_AUTOSTART") != "1":
        pytest.skip("set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the live Postgres tests")

    psycopg = pytest.importorskip("psycopg")
    if shutil.which("initdb") is None or shutil.which("pg_ctl") is None:
        pytest.skip("initdb / pg_ctl not on PATH")

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


_ROLE_SQL = """
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
end
$$;
"""


def _apply_migration(admin_url):
    """
    Create the Supabase roles a plain cluster lacks, then apply every committed
    migration in name order (the production chain), each in one transaction.
    """
    import psycopg

    names = sorted(name for name in os.listdir(_MIGRATIONS_DIR) if name.endswith(".sql"))
    assert names, "no migration files found"
    with psycopg.connect(admin_url) as conn:
        conn.execute(_ROLE_SQL)
        for name in names:
            with open(os.path.join(_MIGRATIONS_DIR, name), encoding="utf-8") as handle:
                conn.execute(handle.read())


def _writer_url(admin_url):
    """The same database as the migration's `dlr_writer` (trust auth, no credential locally)."""
    parts = urlsplit(admin_url)
    return parts._replace(netloc=f"dlr_writer@{parts.hostname}:{parts.port}").geturl()


def _reset(admin_url):
    """Make sure the schema exists (idempotent), then empty both tables as the superuser."""
    import psycopg

    _apply_migration(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("truncate public.city_rating, public.pipeline_run")


def _admin_rows(admin_url, sql, params=None):
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(admin_url, autocommit=True, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


def _count_rows(admin_url):
    return _admin_rows(
        admin_url,
        "select (select count(*) from public.city_rating) as ratings, (select count(*) from public.pipeline_run) as runs",
    )[0]


# ──────────────────────────────────────────────────────────────────────────────
# Offline
# ──────────────────────────────────────────────────────────────────────────────

def test_missing_url_exits_two_and_prints_no_value(monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise AssertionError("no connection may be opened")

    monkeypatch.setattr(supabase_store, "connect", boom)
    for value in (None, "", "   "):
        if value is None:
            monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
        else:
            monkeypatch.setenv("SUPABASE_DB_URL", value)
        assert supabase_smoke.main([]) == 2
        captured = capsys.readouterr()
        assert "SUPABASE_DB_URL" in captured.err
        assert captured.out == ""
        assert "   " not in captured.err.replace("SUPABASE_DB_URL is not set", "")


def test_connection_failure_prints_no_part_of_the_url(tmp_path, monkeypatch, capsys, caplog):
    encoded = quote(_CREDENTIAL, safe="")
    assert encoded != _CREDENTIAL and "%40" in encoded
    # Port 9 on loopback refuses at once; the second URL's host never resolves.
    for host in ("127.0.0.1:9", "mk7host.invalid:5432"):
        url = "postgresql://" + _USER + ":" + encoded + "@" + host + "/postgres"
        monkeypatch.setenv("SUPABASE_DB_URL", url)
        report_path = tmp_path / "failed.json"
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            assert supabase_smoke.main(["--report", str(report_path)]) == 1
        captured = capsys.readouterr()
        everything = captured.out + captured.err + caplog.text + report_path.read_text(encoding="utf-8")
        assert "SMOKE FAILED: connected" in captured.out
        for forbidden in (encoded, _CREDENTIAL, _USER, "mk7ref", "mk7user", "Zq9", "mk7host", "127.0.0.1", url):
            assert forbidden not in everything, forbidden
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["schema"] == "supabase_smoke/1"
        assert report["checks"] == {"connected": False} and report["all_passed"] is False


# ──────────────────────────────────────────────────────────────────────────────
# Live (throwaway local Postgres, as dlr_writer)
# ──────────────────────────────────────────────────────────────────────────────

def test_smoke_passes_on_a_fresh_migration_and_leaves_no_rows(tmp_path, monkeypatch, capsys, _pg_admin_url):
    _reset(_pg_admin_url)
    monkeypatch.setenv("SUPABASE_DB_URL", _writer_url(_pg_admin_url))
    report_path = tmp_path / "smoke.json"
    assert supabase_smoke.main(["--allow-no-ssl", "--report", str(report_path)]) == 0
    out = capsys.readouterr().out
    assert out.rstrip().endswith("SMOKE OK")
    assert "127.0.0.1" not in out and "dlr_test" not in out

    text = report_path.read_text(encoding="utf-8")
    assert "127.0.0.1" not in text and "dlr_test" not in text
    report = json.loads(text)
    assert report["all_passed"] is True
    assert report["checks"]["ssl_in_use"] == "skipped"
    expected = ["connected", "role_is_dlr_writer", "server_version_ge_15", "tables_exist", "rls_enabled",
                "writer_policies_exist", "writer_privileges_exact", "consumers_cannot_write",
                "rating_upsert_idempotent", "run_row_idempotent", "delete_denied",
                "session_timezone_utc", "utc_hour_check_zone_independent"]
    assert all(report["checks"][name] is True for name in expected)
    assert report["info"]["role"] == "dlr_writer" and report["info"]["anon_can_select"] is False
    assert report["checked_at"].endswith("Z")
    # Nothing a smoke run wrote survives it.
    assert _count_rows(_pg_admin_url) == {"ratings": 0, "runs": 0}


def test_smoke_fails_when_the_writer_policy_is_missing(tmp_path, monkeypatch, capsys, _pg_admin_url):
    import psycopg

    _reset(_pg_admin_url)
    monkeypatch.setenv("SUPABASE_DB_URL", _writer_url(_pg_admin_url))
    try:
        with psycopg.connect(_pg_admin_url, autocommit=True) as admin:
            admin.execute("drop policy dlr_writer_all on public.city_rating")
        report_path = tmp_path / "smoke.json"
        assert supabase_smoke.main(["--allow-no-ssl", "--report", str(report_path)]) == 1
        out = capsys.readouterr().out
        failed_line = [line for line in out.splitlines() if line.startswith("SMOKE FAILED")][0]
        assert "writer_policies_exist" in failed_line
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["checks"]["writer_policies_exist"] is False and report["all_passed"] is False
        assert _count_rows(_pg_admin_url) == {"ratings": 0, "runs": 0}
    finally:
        _apply_migration(_pg_admin_url)  # re-applying restores the policy
    assert supabase_smoke.main(["--allow-no-ssl"]) == 0
    capsys.readouterr()


def test_hour_check_accepts_utc_hours_in_a_half_hour_offset_session(monkeypatch, _pg_admin_url):
    import psycopg

    _reset(_pg_admin_url)
    monkeypatch.setenv("SUPABASE_DB_URL", _writer_url(_pg_admin_url))
    row = supabase_smoke._sentinel_row()
    at = lambda stamp: dict(row, valid_time=stamp)  # noqa: E731
    conn = supabase_store.connect()
    try:
        with conn.transaction(force_rollback=True):
            conn.execute("set local timezone = 'Asia/Kolkata'")  # UTC+05:30
            supabase_store.upsert_rating(conn, at("2000-01-01T01:00:00Z"))  # whole UTC hour, 06:30 local
            with pytest.raises(psycopg.errors.CheckViolation) as refused:
                with conn.transaction():
                    # Raw upsert: upsert_rating re-raises as a redacted StoreError.
                    conn.execute(supabase_store.UPSERT_RATING_SQL, at("2000-01-01T01:30:00Z"))  # whole hour in Kolkata only
            assert refused.value.diag.constraint_name == "city_rating_valid_time_hour_ck"
    finally:
        conn.close()
    assert _count_rows(_pg_admin_url) == {"ratings": 0, "runs": 0}


def test_zone_check_fails_against_the_original_constraint(tmp_path, monkeypatch, capsys, _pg_admin_url):
    import psycopg

    _reset(_pg_admin_url)
    monkeypatch.setenv("SUPABASE_DB_URL", _writer_url(_pg_admin_url))
    report_path = tmp_path / "smoke.json"
    try:
        with psycopg.connect(_pg_admin_url, autocommit=True) as admin:
            admin.execute("alter table public.city_rating drop constraint city_rating_valid_time_hour_ck")
            admin.execute("alter table public.city_rating add constraint city_rating_valid_time_hour_ck "
                          "check (valid_time = date_trunc('hour', valid_time))")
        assert supabase_smoke.main(["--allow-no-ssl", "--report", str(report_path)]) == 1
        out = capsys.readouterr().out
        failed_line = [line for line in out.splitlines() if line.startswith("SMOKE FAILED")][0]
        assert failed_line == "SMOKE FAILED: utc_hour_check_zone_independent"
        checks = json.loads(report_path.read_text(encoding="utf-8"))["checks"]
        assert checks["utc_hour_check_zone_independent"] is False
        assert checks["session_timezone_utc"] is True
        assert all(value is True for name, value in checks.items()
                   if name not in ("utc_hour_check_zone_independent", "ssl_in_use"))
        assert _count_rows(_pg_admin_url) == {"ratings": 0, "runs": 0}
    finally:
        _apply_migration(_pg_admin_url)  # the chain restores the UTC expression
    assert supabase_smoke.main(["--allow-no-ssl"]) == 0
    capsys.readouterr()


def test_expect_rows_fails_on_an_empty_city(monkeypatch, capsys, _pg_admin_url):
    _reset(_pg_admin_url)
    monkeypatch.setenv("SUPABASE_DB_URL", _writer_url(_pg_admin_url))
    assert supabase_smoke.main(["--allow-no-ssl", "--expect-rows"]) == 1
    out = capsys.readouterr().out
    assert "check rows_visible: FAILED" in out and "SMOKE FAILED: rows_visible" in out
    for city in config.LOCATIONS:
        assert city in out.split("no rows for:")[1].splitlines()[0]


# ──────────────────────────────────────────────────────────────────────────────
# The Actions workflow (text checks, no YAML library)
# ──────────────────────────────────────────────────────────────────────────────

_WORKFLOW = os.path.join(os.path.dirname(__file__), "..", "..", ".github", "workflows", "supabase_smoke.yml")
_GITIGNORE = os.path.join(os.path.dirname(__file__), "..", "..", ".gitignore")


def _top_level_block(lines, key):
    """The lines under a top-level `key:` up to the next top-level key."""
    start = next(i for i, line in enumerate(lines) if line.rstrip() == f"{key}:")
    block = []
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith((" ", "#")):
            break
        block.append(line)
    return block


def _run_blocks(lines):
    """The text of every `run:` step: the same-line command or the indented block after `run: |`."""
    blocks = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("run:"):
            continue
        text = [stripped[len("run:"):].strip()]
        if text[0] in ("|", ">", "|-", ">-"):
            text = []
            indent = len(line) - len(line.lstrip())
            for follow in lines[index + 1:]:
                if follow.strip() and len(follow) - len(follow.lstrip()) <= indent:
                    break
                text.append(follow.strip())
        blocks.append("\n".join(text))
    return blocks


def test_smoke_workflow_is_dispatch_only_and_passes_the_secret_by_env():
    with open(_WORKFLOW, encoding="utf-8") as handle:
        text = handle.read()
    lines = text.splitlines()

    triggers = [line.strip().rstrip(":") for line in _top_level_block(lines, "on") if line.strip() and not line.strip().startswith("#")]
    assert triggers == ["workflow_dispatch"]
    for forbidden in ("push", "pull_request", "pull_request_target", "schedule", "workflow_run"):
        assert forbidden not in triggers

    permissions = [line.strip() for line in _top_level_block(lines, "permissions") if line.strip()]
    assert permissions == ["contents: read"]

    # The secret is mapped once, on an env line.
    assert text.count("${{ secrets.SUPABASE_DB_URL }}") == 1
    assert text.count("secrets.") == 1
    secret_index = next(i for i, line in enumerate(lines) if "${{ secrets.SUPABASE_DB_URL }}" in line)
    assert lines[secret_index].strip() == "SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}"
    above = [line for line in lines[:secret_index] if line.strip()]
    assert above[-1].strip() == "env:"
    assert "supabase_smoke.py" in "\n".join(lines[secret_index + 1:])

    # No expression in a run block, no tracing, no admin URL, no echo of the secret.
    runs = _run_blocks(lines)
    assert len(runs) == 2 and not any("${{" in block for block in runs)
    assert "set -x" not in text and "SUPABASE_ADMIN" not in text
    assert not [line for line in lines if re.match(r"\s*(-\s+)?echo\b", line) and "SUPABASE" in line]

    with open(_GITIGNORE, encoding="utf-8") as handle:
        ignored = handle.read().splitlines()
    assert "/supabase/.temp/" in ignored and "/supabase/.branches/" in ignored
