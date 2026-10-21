"""
Tests against a real but throwaway local Postgres (production-pipeline Phase 4,
DB-01, DB-02, DB-06).

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl
under pytest's tmp dir and stops the cluster afterwards) or
`DLR_TEST_DATABASE_URL` names a local throwaway database (host 127.0.0.1,
localhost or ::1; anything else fails the test). They never touch Supabase: the
committed migration is applied to the throwaway database only, and the writer
connects as the migration's own `dlr_writer` role.

Follows backend/tests/city_rating_test.py's conventions (module-level imports,
plain asserts, no test classes, no network).
"""

import os
import shutil
import socket
import subprocess
from datetime import timezone
from urllib.parse import urlsplit

import pandas as pd
import pytest
import requests

import anomaly_detector
import city_pipeline
import city_point
import config
import data_cleaning
import historical_archive
import supabase_store

_MIGRATION = os.path.join(
    os.path.dirname(__file__), "..", "..", "supabase", "migrations",
    "20261019000000_create_city_rating.sql",
)
_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
_CITIES = ("AUSTIN", "EL_PASO")


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
    Create the Supabase roles a plain cluster lacks, then apply the committed
    migration in one transaction.
    """
    import psycopg

    with open(_MIGRATION, encoding="utf-8") as handle:
        sql = handle.read()
    with psycopg.connect(admin_url) as conn:
        conn.execute(_ROLE_SQL)
        conn.execute(sql)


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


def _stations():
    rows = []
    for city in _CITIES:
        lat, lon = config.CITY_COORDINATES[city]
        rows.append({"stid": f"T_{city}", "name": city, "lat": lat, "lon": lon})
    return pd.DataFrame(rows)


class _StubFetcher:
    """Stands in for the composed fetcher; air temperature is set per instance."""

    def __init__(self, air_temp=25.0):
        self.air_temp = air_temp
        self.provenance = []
        self.errors = {}
        self.calls = []

    def __call__(self, stids, start, end, provider="synoptic", **_):
        self.calls.append((stids[0], end))
        city = stids[0].split("T_", 1)[1]
        # Wind blows across the line, so the projected speed equals the measured one.
        across = (city_point.city_point(city).bearing_deg + 90) % 360
        return pd.DataFrame([{"stid": stids[0], "air_temp": self.air_temp, "wind_speed": 6.5,
                              "wind_direction": across, "solar_radiation": 500.0}])


_PROVENANCE = {"stid": "T_AUSTIN", "hour": "2025-06-01T14:00:00Z", "air_temp": "synoptic",
               "wind_speed": "tceq", "solar_radiation": "nsrdb"}


def _run_austin(tmp_path, end, air_temp):
    return city_pipeline.run_city_pipeline(
        "AUSTIN", "2025-06-01T13:07:00Z", end, _stations(), provider="synoptic",
        archive=False, archive_path=str(tmp_path / "none.csv"),
        fetch_weather=_StubFetcher(air_temp=air_temp),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tracer: one city, one hour, through migration, writer and history read
# ──────────────────────────────────────────────────────────────────────────────

def test_tracer_one_city_hour_round_trips_through_postgres(tmp_path, monkeypatch, _pg_admin_url):
    # A fresh database: the migration applies twice in a row, both times cleanly.
    _apply_migration(_pg_admin_url)
    _apply_migration(_pg_admin_url)
    _reset(_pg_admin_url)

    with supabase_store.SupabaseStore(supabase_store.connect(_writer_url(_pg_admin_url))) as store:
        end = "2025-06-01T14:07:00Z"
        result = _run_austin(tmp_path, end, air_temp=25.0)
        assert store.write_rating(result, end=end, provenance=_PROVENANCE) is True

        rows = _admin_rows(_pg_admin_url, "select * from public.city_rating")
        assert len(rows) == 1
        row = rows[0]
        assert row["city"] == "AUSTIN"
        assert row["valid_time"].astimezone(timezone.utc).isoformat() == "2025-06-01T14:00:00+00:00"
        assert row["rating_amps"] == result["rating"]
        assert row["wind_perp_ms"] == result["observation"]["wind"]
        assert row["temp_source"] == "synoptic"
        assert row["origin"] == "live"
        assert row["rating_basis"] == config.RATING_BASIS
        assert row["config_version"] == config.RATING_CONFIG_VERSION
        # DB-06: the row names the assumptions and the models behind it.
        assert row["config_fingerprint"] == supabase_store.rating_config_fingerprint("AUSTIN")
        assert row["forecast_method"] == "naive"
        assert row["forecast_model_sha256"] is None
        detector_model = result["pipeline"]["detector_model"]
        if detector_model is not None:
            assert row["anomaly_model_sha256"] == supabase_store.file_sha256(detector_model)
        else:
            assert row["anomaly_model_sha256"] is None
        first_written = row["first_written_at"]
        computed = row["computed_at"]

        # OD-7: a same-hour retry overwrites the row in place.
        retry_end = "2025-06-01T14:12:00Z"
        retry = _run_austin(tmp_path, retry_end, air_temp=30.0)
        store.write_rating(retry, end=retry_end, provenance=_PROVENANCE)
        rows = _admin_rows(_pg_admin_url, "select * from public.city_rating")
        assert len(rows) == 1
        assert rows[0]["air_temp_c"] == 30.0
        assert rows[0]["first_written_at"] == first_written
        assert rows[0]["computed_at"] >= computed

        # The next hour reads the row back in the CSV archive's frame shape.
        frame = store.read_history("AUSTIN", "2025-06-01T15:05:00Z")
        assert len(frame) == 1
        assert list(frame.columns) == historical_archive.ARCHIVE_COLUMNS
        assert frame["datetime_utc"].iloc[0] == "2025-06-01T14:00:00Z"
        assert frame["dlr_amps"].iloc[0] == rows[0]["rating_amps"]
        # The current slot is excluded, so a retry never learns from its own row.
        assert len(store.read_history("AUSTIN", "2025-06-01T14:30:00Z")) == 0

        cleaned = data_cleaning.clean_history(frame, as_of="2025-06-01T15:05:00Z")
        assert len(cleaned.usable) == 1

    # Writing to Postgres never touches the CSV archive.
    assert not os.path.exists(config.HISTORICAL_ARCHIVE_PATH)
    assert list(tmp_path.glob("*.csv")) == []
