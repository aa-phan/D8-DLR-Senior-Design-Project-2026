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

import math
import os
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlsplit

import pandas as pd
import pytest
import requests

import anomaly_detector
import city_pipeline
import city_point
import config
import data_cleaning
import ercot_dlr_merger
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


# ──────────────────────────────────────────────────────────────────────────────
# Contract: CHECKs, keys, privileges, row-level security
# ──────────────────────────────────────────────────────────────────────────────

_RUN_CTX = {"run_id": "live-test", "run_attempt": 1, "pipeline_version": "abcdef1"}
_END = "2025-06-01T14:07:00Z"


def _result(**overrides):
    """A rate_city-shaped result with a `pipeline` key."""
    result = {
        "city": "AUSTIN",
        "point": (30.2711, -97.7437),
        "station_id": "T_AUSTIN",
        "candidates_probed": 1,
        "probe_trail": [{"stid": "T_AUSTIN", "lat": 30.27, "lon": -97.74, "distance_km": 0.5, "outcome": "ok"}],
        "rating": 1825.0,
        "status": "ok",
        "fallback": False,
        "alerts": [],
        "observation": {"sensor_status": "ok", "link_status": "ok", "temp": 25.0, "wind": 6.5,
                        "solar": 500.0, "wind_direction": 263.15, "wind_raw": 6.5},
        "exhausted": False,
        "archived": False,
        "pipeline": {
            "history_rows": 10, "usable_history_rows": 9, "forecast_method": "naive",
            "forecast_used_by_g6": False, "forecast": None, "detector_signal": "cold_start",
            "detector_model": None,
        },
    }
    result.update(overrides)
    return result


def _row(end=_END, **overrides):
    row = supabase_store.build_rating_row(_result(), end, _RUN_CTX, _PROVENANCE)
    row.update(overrides)
    return row


def _writer(admin_url):
    return supabase_store.connect(_writer_url(admin_url))


def _count(admin_url, where="true"):
    return _admin_rows(admin_url, f"select count(*) as n from public.city_rating where {where}")[0]["n"]


_NEG_INF = float("-inf")
_BAD_AMPS = (0.0, -1.0, float("nan"), float("inf"))

_CHECK_CASES = (
    [(f"rating_amps={v}", {"rating_amps": v}, "CheckViolation") for v in _BAD_AMPS]
    + [(f"rating_mw={v}", {"rating_mw": v}, "CheckViolation") for v in _BAD_AMPS]
    + [
        ("rating_amps=1e-9 accepted", {"rating_amps": 1e-9, "rating_mw": 1e-9}, None),
        ("valid_time 14:00:00Z accepted", {"valid_time": datetime(2025, 6, 1, 14, 0, 0, tzinfo=timezone.utc)}, None),
        ("valid_time 14:00:01Z", {"valid_time": datetime(2025, 6, 1, 14, 0, 1, tzinfo=timezone.utc)}, "CheckViolation"),
        ("valid_time 14:30Z", {"valid_time": datetime(2025, 6, 1, 14, 30, tzinfo=timezone.utc)}, "CheckViolation"),
        ("lower-case city", {"city": "austin"}, "CheckViolation"),
        ("unknown city", {"city": "HOUSTON"}, "CheckViolation"),
        ("status", {"status": "maybe"}, "CheckViolation"),
        ("forecast_status", {"forecast_status": "maybe"}, "CheckViolation"),
        ("forecast_status ok accepted", {"forecast_status": "ok"}, None),
        ("origin", {"origin": "imported"}, "CheckViolation"),
        ("NULL rating_basis", {"rating_basis": None}, "NotNullViolation"),
        ("NULL config_version", {"config_version": None}, "NotNullViolation"),
        ("NULL config_fingerprint", {"config_fingerprint": None}, "NotNullViolation"),
        ("short config_fingerprint", {"config_fingerprint": "abc"}, "CheckViolation"),
        ("upper-case config_fingerprint", {"config_fingerprint": "A" * 64}, "CheckViolation"),
        ("bad forecast_model_sha256", {"forecast_model_sha256": "f" * 63}, "CheckViolation"),
        ("bad anomaly_model_sha256", {"anomaly_model_sha256": "G" * 64}, "CheckViolation"),
        ("good model hashes accepted", {"forecast_model_sha256": "a" * 64, "anomaly_model_sha256": "0" * 64}, None),
        ("NULL model hashes accepted", {"forecast_model_sha256": None, "anomaly_model_sha256": None}, None),
        ("NULL alerts", {"alerts": None}, "NotNullViolation"),
    ]
)


@pytest.mark.parametrize("overrides, expected", [c[1:] for c in _CHECK_CASES], ids=[c[0] for c in _CHECK_CASES])
def test_checks_reject_bad_rows(_pg_admin_url, overrides, expected):
    import psycopg

    _reset(_pg_admin_url)
    row = _row(**overrides)
    with _writer(_pg_admin_url) as conn:
        if expected is None:
            conn.execute(supabase_store.UPSERT_RATING_SQL, row)
            assert _count(_pg_admin_url) == 1
        else:
            with pytest.raises(getattr(psycopg.errors, expected)):
                conn.execute(supabase_store.UPSERT_RATING_SQL, row)
            assert _count(_pg_admin_url) == 0


def test_offset_spellings_are_one_key_and_neighbors_are_separate(_pg_admin_url):
    _reset(_pg_admin_url)
    with supabase_store.SupabaseStore(_writer(_pg_admin_url), run_ctx=_RUN_CTX) as store:
        store.write_rating(_result(rating=1700.0), end="2025-06-01T14:00:00Z")
        store.write_rating(_result(rating=1710.0), end="2025-06-01T09:00:00-05:00")
        rows = _admin_rows(_pg_admin_url, "select rating_amps from public.city_rating")
        assert [r["rating_amps"] for r in rows] == [1710.0]  # the second spelling updated the one row

        store.write_rating(_result(rating=1720.0), end="2025-06-01T13:00:00Z")
        assert _count(_pg_admin_url, "city = 'AUSTIN'") == 2

        el_paso = _result(city="EL_PASO", station_id="T_EL_PASO", rating=1300.0)
        store.write_rating(el_paso, end="2025-06-01T14:00:00Z")
        assert _count(_pg_admin_url) == 3
        assert _count(_pg_admin_url, "city = 'EL_PASO'") == 1


def test_writer_cannot_delete_truncate_or_create(_pg_admin_url):
    import psycopg

    _reset(_pg_admin_url)
    with supabase_store.SupabaseStore(_writer(_pg_admin_url), run_ctx=_RUN_CTX) as store:
        store.write_rating(_result(), end=_END)
        for statement in (
            "delete from public.city_rating",
            "truncate public.city_rating",
            "create table public.sneaky (a integer)",
            "drop table public.city_rating",
            "alter table public.city_rating add column sneaky integer",
            "create role sneaky login",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                store.conn.execute(statement)
    assert _count(_pg_admin_url) == 1


def test_consumer_roles_have_no_privileges(_pg_admin_url):
    _reset(_pg_admin_url)
    privileges = ("select", "insert", "update", "delete", "truncate", "references", "trigger")
    for role in ("anon", "authenticated"):
        for table in ("public.city_rating", "public.pipeline_run"):
            for privilege in privileges:
                granted = _admin_rows(
                    _pg_admin_url, "select has_table_privilege(%s, %s, %s) as granted", (role, table, privilege)
                )[0]["granted"]
                assert granted is False, (role, table, privilege)
        usage = _admin_rows(_pg_admin_url, "select has_schema_privilege(%s, 'public', 'create') as c", (role,))
        assert usage[0]["c"] is False

    for table in ("public.city_rating", "public.pipeline_run"):
        for privilege in privileges:
            granted = _admin_rows(
                _pg_admin_url, "select has_table_privilege('dlr_writer', %s, %s) as granted", (table, privilege)
            )[0]["granted"]
            assert granted is (privilege in ("select", "insert", "update")), (table, privilege)
    schema = _admin_rows(
        _pg_admin_url,
        "select has_schema_privilege('dlr_writer', 'public', 'usage') as u, "
        "has_schema_privilege('dlr_writer', 'public', 'create') as c",
    )[0]
    assert (schema["u"], schema["c"]) == (True, False)

    role = _admin_rows(
        _pg_admin_url,
        "select rolcanlogin, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolpassword is null as no_credential "
        "from pg_authid where rolname = 'dlr_writer'",
    )[0]
    assert role == {"rolcanlogin": True, "rolsuper": False, "rolbypassrls": False,
                    "rolcreaterole": False, "rolcreatedb": False, "no_credential": True}
    rls = _admin_rows(
        _pg_admin_url,
        "select relname, relrowsecurity from pg_class where oid in "
        "('public.city_rating'::regclass, 'public.pipeline_run'::regclass)",
    )
    assert {r["relname"]: r["relrowsecurity"] for r in rls} == {"city_rating": True, "pipeline_run": True}


def test_dropping_the_policy_hides_rows_without_an_error(_pg_admin_url):
    import psycopg

    _reset(_pg_admin_url)
    with supabase_store.SupabaseStore(_writer(_pg_admin_url), run_ctx=_RUN_CTX) as store:
        store.write_rating(_result(), end=_END)
        assert store.conn.execute("select count(*) from public.city_rating").fetchone()[0] == 1
        try:
            with psycopg.connect(_pg_admin_url, autocommit=True) as admin:
                admin.execute("drop policy dlr_writer_all on public.city_rating")
            # No policy: the writer sees zero rows and gets no error ...
            assert store.conn.execute("select count(*) from public.city_rating").fetchone()[0] == 0
            assert len(store.read_history("AUSTIN", "2025-06-01T15:05:00Z")) == 0
            # ... and cannot insert.
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                store.conn.execute(supabase_store.UPSERT_RATING_SQL, _row(end="2025-06-01T16:00:00Z"))
        finally:
            _apply_migration(_pg_admin_url)  # re-applying restores the policy
        assert store.conn.execute("select count(*) from public.city_rating").fetchone()[0] == 1


def test_timestamps_are_whole_seconds_and_text_round_trips(tmp_path, _pg_admin_url):
    _reset(_pg_admin_url)
    em_dash_alert = "G4 FAIL (implausible (1080 A)) \u2014 fallback rating 1825 A"
    with supabase_store.SupabaseStore(_writer(_pg_admin_url), run_ctx=_RUN_CTX) as store:
        store.write_rating(
            _result(alerts=[em_dash_alert], status="fallback", fallback=True), end="2025-06-01T14:59:59Z",
            provenance=_PROVENANCE)
        store.write_rating(_result(), end="2025-06-01T15:10:00Z")  # alert-free
        store.write_rating(
            _result(rating=1825.0, status="fallback", fallback=True, observation=None, exhausted=True,
                    station_id=None, alerts=["EXHAUSTED FAIL (AUSTIN: 3 candidates exhausted) \u2014 fallback rating 1825 A"]),
            end="2025-06-01T16:00:00Z")

        rows = {r["valid_time"].astimezone(timezone.utc).hour: r
                for r in _admin_rows(_pg_admin_url, "select * from public.city_rating")}
        assert set(rows) == {14, 15, 16}

        flagged = rows[14]  # 14:59:59Z is the 14:00Z slot, never 15:00Z
        assert flagged["alerts"] == [em_dash_alert]
        assert flagged["alerts"][0].encode("utf-8") == em_dash_alert.encode("utf-8")
        assert flagged["fallback_gates"] == ["G4"]
        assert flagged["rating_mw"] == pytest.approx(
            ercot_dlr_merger.amps_to_mw(flagged["rating_amps"], config.LINE_VOLTAGE_KV, config.POWER_FACTOR), abs=1e-9)
        assert flagged["rating_mw"] == pytest.approx(1036.0153652297765, abs=1e-9)

        clean = rows[15]
        assert clean["alerts"] == [] and clean["fallback_gates"] == []

        exhausted = rows[16]
        assert exhausted["exhausted"] is True and exhausted["fallback_gates"] == ["EXHAUSTED"]
        for column in ("observation_time", "station_id", "air_temp_c", "wind_perp_ms", "wind_speed_ms",
                       "wind_direction_deg", "solar_radiation_wm2", "temp_source", "wind_source", "solar_source"):
            assert exhausted[column] is None, column

        for row in rows.values():
            assert row["first_written_at"].microsecond == 0
            assert row["computed_at"].microsecond == 0
            assert math.isfinite(row["rating_mw"])
