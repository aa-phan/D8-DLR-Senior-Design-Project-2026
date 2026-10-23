"""
Orchestrator-to-store tests (production-pipeline Phase 4, DB-02, DB-06, OD-9).

The offline tests use a fake store (and, where the per-city result matters, a
fake per-city pipeline), so they check what the orchestrator reads, writes and
records, not ratings. Tests marked live need `DLR_TEST_PG_AUTOSTART=1` (the
fixture runs initdb and pg_ctl under pytest's tmp dir and stops the cluster
afterwards) or a local `DLR_TEST_DATABASE_URL` (host 127.0.0.1, localhost or
::1); they never touch Supabase and connect as the migration's own
`dlr_writer` role.

Follows backend/tests/city_rating_test.py's conventions (module-level imports,
plain asserts, no test classes, no network).
"""

import logging
import os
import shutil
import socket
import subprocess
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit

import pandas as pd
import pytest
import requests

import ampacity_forecast
import anomaly_detector
import city_point
import config
import dlr_orchestrator as orch
import historical_archive
import supabase_store

_MIGRATION = os.path.join(
    os.path.dirname(__file__), "..", "..", "supabase", "migrations",
    "20261019000000_create_city_rating.sql",
)
_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
_CITIES = ("AUSTIN", "EL_PASO")
_END = "2025-06-01T14:07:00Z"
_SLOT = datetime(2025, 6, 1, 14, 0, tzinfo=timezone.utc)


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


# ──────────────────────────────────────────────────────────────────────────────
# Live Postgres fixture and helpers (copied from supabase_live_test.py; the
# repository has no conftest.py)
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# Offline helpers
# ──────────────────────────────────────────────────────────────────────────────

def _stations():
    rows = []
    for city in _CITIES:
        lat, lon = config.CITY_COORDINATES[city]
        rows.append({"stid": f"T_{city}", "name": city, "lat": lat, "lon": lon})
    return pd.DataFrame(rows)


class _StubFetcher:
    """
    Stands in for the composed fetcher: `provenance` and `errors` are what
    `run_dlr_pipeline` reads from it, and every call appends the provenance
    record the real composer would.
    """

    def __init__(self):
        self.provenance = []
        self.errors = Counter()
        self.calls = []

    def __call__(self, stids, start, end, provider="synoptic", **_):
        self.calls.append((stids[0], end))
        city = stids[0].split("T_", 1)[1]
        self.provenance.append({"stid": stids[0], "hour": end, "air_temp": "synoptic",
                                "wind_speed": "synoptic", "solar_radiation": "synoptic"})
        # Wind blows across the line, so the projected speed equals the measured one.
        across = (city_point.city_point(city).bearing_deg + 90) % 360
        return pd.DataFrame([{"stid": stids[0], "air_temp": 25.0, "wind_speed": 6.5,
                              "wind_direction": across, "solar_radiation": 500.0}])


def _history_frame(city, hours, day="2025-06-01"):
    rows = [{
        "datetime_utc": f"{day}T{h:02d}:00:00Z", "city": city, "air_temp": 25.0,
        "wind_speed": 6.5, "solar_radiation": 500.0, "dlr_amps": 1200.0 + h,
        "static_rating": float(city_point.city_point(city).static_rating), "status": "ok",
        "fallback": False, "schema_version": historical_archive.ARCHIVE_SCHEMA_VERSION,
    } for h in hours]
    return pd.DataFrame(rows, columns=historical_archive.ARCHIVE_COLUMNS)


class FakeStore:
    """
    Records the calls the orchestrator makes. Presets: history frames per city,
    cities whose write raises StoreError, and whether record_run raises.
    """

    def __init__(self, history=None, fail_write=(), fail_run=False):
        self.history = history or {}
        self.fail_write = set(fail_write)
        self.fail_run = fail_run
        self.reads = []
        self.writes = []
        self.run_rows = []
        self.run_ctx = {"run_id": "fake-run", "run_attempt": 1, "pipeline_version": "abc1234"}

    def read_history(self, city, end):
        self.reads.append((city, end))
        return self.history.get(city, pd.DataFrame(columns=historical_archive.ARCHIVE_COLUMNS))

    def write_rating(self, result, end, provenance=None):
        if result["city"] in self.fail_write:
            raise supabase_store.StoreError(f"could not write the {result['city']} rating: disk full")
        self.writes.append({"city": result["city"], "end": end, "provenance": provenance})
        return True

    def record_run(self, row):
        if self.fail_run:
            raise RuntimeError("lost connection to postgresql" + "://svc:" + "Zq9Mk7Leak"
                               + "@db.example.com:5432/postgres")
        self.run_rows.append(row)


def _city_result(city, station_id="T1", forecast_status="ok", detector_model="anomaly.joblib"):
    return {
        "city": city, "point": config.CITY_COORDINATES[city], "station_id": station_id,
        "candidates_probed": 1, "probe_trail": [], "rating": 1000.0, "status": "ok",
        "fallback": False, "alerts": [], "observation": {}, "exhausted": False, "archived": False,
        "pipeline": {
            "history_rows": 0, "usable_history_rows": 0, "forecast_method": "ml",
            "forecast_status": forecast_status, "forecast_used_by_g6": False, "forecast": None,
            "detector_signal": "cold_start", "detector_model": detector_model,
        },
    }


def _fake_city_pipeline(monkeypatch, behaviors=None):
    """
    Replace `run_city_pipeline` in the orchestrator's namespace. `behaviors` maps
    a city to: `error` (raise RuntimeError with this text), `forecast_status`,
    `detector_model`, `station_id`, `provenance` (records the fetcher gains) and
    `provider_errors` (counts the fetcher gains). Returns the recorded calls.
    """
    behaviors = behaviors or {}
    calls = []

    def fake(name, start, end, stations, **kwargs):
        calls.append((name, kwargs))
        spec = behaviors.get(name, {})
        fetcher = kwargs.get("fetch_weather")
        for record in spec.get("provenance", []):
            fetcher.provenance.append(record)
        for key, count in spec.get("provider_errors", {}).items():
            fetcher.errors[key] += count
        if "error" in spec:
            raise RuntimeError(spec["error"])
        return _city_result(
            name, station_id=spec.get("station_id", "T1"),
            forecast_status=spec.get("forecast_status", "ok"),
            detector_model=spec.get("detector_model", "anomaly.joblib"))

    monkeypatch.setattr(orch, "run_city_pipeline", fake)
    return calls


def _run(store, fetcher=None, **kwargs):
    args = dict(stations=_stations(), end=_END, window_hours=1.0, provider="composed",
                forecast_method="ml", store=store, fetcher=fetcher or _StubFetcher())
    args.update(kwargs)
    return orch.run_dlr_pipeline(**args)


def _canned_run(**extra):
    run = {
        "start": "2025-06-01T13:07:00Z", "end": _END, "provider": "composed",
        "forecast_method": "naive", "results": [], "errors": {},
        "summary": [orch.summarize(_city_result("AUSTIN"))],
    }
    run.update(extra)
    return run


def _fake_run_dlr_pipeline(monkeypatch, run):
    seen = []

    def fake(**kwargs):
        seen.append(kwargs)
        return run

    monkeypatch.setattr(orch, "run_dlr_pipeline", fake)
    return seen


# ──────────────────────────────────────────────────────────────────────────────
# Offline: the orchestrator against a fake store
# ──────────────────────────────────────────────────────────────────────────────

def test_store_path_reads_and_writes_through_the_store_and_writes_no_csv(tmp_path):
    store = FakeStore(history={"AUSTIN": _history_frame("AUSTIN", [11, 12, 13])})
    archive_path = tmp_path / "archive.csv"

    run = _run(store, cities=list(_CITIES), archive_path=str(archive_path))

    assert store.reads == [("AUSTIN", _END), ("EL_PASO", _END)]
    assert [(w["city"], w["end"]) for w in store.writes] == [(c, _END) for c in _CITIES]
    assert run["errors"] == {}
    assert [row["city"] for row in run["summary"]] == list(_CITIES)
    assert all(row["archived"] is True for row in run["summary"])
    assert all(result["archived"] is True for result in run["results"])
    by_city = {row["city"]: row for row in run["summary"]}
    assert by_city["AUSTIN"]["history_rows"] == 3
    assert by_city["EL_PASO"]["history_rows"] == 0
    # No CSV exists anywhere: neither the configured default nor the explicit path.
    assert not os.path.exists(config.HISTORICAL_ARCHIVE_PATH)
    assert not archive_path.exists()
    assert list(tmp_path.glob("*.csv")) == []
    assert len(store.run_rows) == 1


def test_provenance_of_the_rated_station_reaches_the_writer(monkeypatch):
    def rec(stid, hour):
        return {"stid": stid, "hour": hour, "air_temp": "synoptic",
                "wind_speed": "tceq", "solar_radiation": "nsrdb"}

    _fake_city_pipeline(monkeypatch, {
        # a probed-but-unused station, then the rated station read twice: the last wins
        "AUSTIN": {"station_id": "T_AUSTIN", "provenance": [
            rec("T_UNUSED", "2025-06-01T14:00:00Z"), rec("T_AUSTIN", "2025-06-01T13:00:00Z"),
            rec("T_AUSTIN", "2025-06-01T14:00:00Z")]},
        # this city's slice holds no record of its station, though an earlier city's slice did
        "CORPUS_CHRISTI": {"station_id": "T_AUSTIN", "provenance": [rec("T_UNUSED", "2025-06-01T14:00:00Z")]},
        # an exhausted city has no station
        "MIDLAND": {"station_id": None, "provenance": [rec("T_UNUSED", "2025-06-01T14:00:00Z")]},
    })
    store = FakeStore()

    _run(store)

    by_city = {w["city"]: w["provenance"] for w in store.writes}
    assert by_city["AUSTIN"] == rec("T_AUSTIN", "2025-06-01T14:00:00Z")
    assert by_city["CORPUS_CHRISTI"] is None
    assert by_city["MIDLAND"] is None
    assert by_city["EL_PASO"] is None


def test_a_failing_city_writes_no_rating_row_and_is_recorded_in_the_run_row(monkeypatch, caplog):
    _fake_city_pipeline(monkeypatch, {"AUSTIN": {"error": "token=s3cr3tv failed"}})
    store = FakeStore()

    with caplog.at_level(logging.INFO):
        run = _run(store)

    assert [w["city"] for w in store.writes] == ["CORPUS_CHRISTI", "MIDLAND", "EL_PASO"]
    assert list(run["errors"]) == ["AUSTIN"]
    assert "AUSTIN" not in [row["city"] for row in run["summary"]]
    row, = store.run_rows
    assert row["cities_ok"] == ["CORPUS_CHRISTI", "MIDLAND", "EL_PASO"]
    assert row["cities_failed"] == {"AUSTIN": {
        "outcome": "error", "written": False, "forecast_status": None,
        "detector_model_loaded": False, "error": "token=REDACTED failed",
    }}
    assert "s3cr3tv" not in repr(row)


def test_a_store_write_failure_is_a_city_error_and_the_others_still_write(monkeypatch):
    _fake_city_pipeline(monkeypatch)
    store = FakeStore(fail_write=("EL_PASO",))

    run = _run(store)

    assert [w["city"] for w in store.writes] == ["AUSTIN", "CORPUS_CHRISTI", "MIDLAND"]
    assert list(run["errors"]) == ["EL_PASO"]
    assert [r["city"] for r in run["summary"]] == ["AUSTIN", "CORPUS_CHRISTI", "MIDLAND"]
    row, = store.run_rows
    assert row["cities_ok"] == ["AUSTIN", "CORPUS_CHRISTI", "MIDLAND"]
    failed = row["cities_failed"]["EL_PASO"]
    assert failed["outcome"] == "error" and failed["written"] is False
    # the pipeline had run: its forecast status and detector state are still recorded
    assert failed["forecast_status"] == "ok" and failed["detector_model_loaded"] is True
    assert "disk full" in failed["error"]


def test_run_row_classifies_ok_degraded_and_error_with_per_city_provider_counts(monkeypatch):
    _fake_city_pipeline(monkeypatch, {
        "AUSTIN": {"provider_errors": {"nsrdb: ValueError: down": 2},
                   "provenance": [{"stid": "T1", "hour": _END, "air_temp": "synoptic",
                                   "wind_speed": "tceq", "solar_radiation": "nsrdb"}]},
        "CORPUS_CHRISTI": {"forecast_status": "cold_start"},
        "MIDLAND": {"forecast_status": "failed", "provider_errors": {"tceq: HTTPError": 1}},
        "EL_PASO": {"error": "provider down", "provider_errors": {"synoptic: token=s3cr3tv": 3}},
    })
    store = FakeStore()
    fetcher = _StubFetcher()
    fetcher.errors["nsrdb: ValueError: down"] = 5   # from an earlier run on this fetcher

    run = _run(store, fetcher=fetcher)

    row, = store.run_rows
    assert row["run_id"] == "fake-run" and row["pipeline_version"] == "abc1234"
    assert row["cities_ok"] == ["AUSTIN", "CORPUS_CHRISTI"]
    assert row["cities_failed"]["MIDLAND"]["outcome"] == "degraded"
    assert row["cities_failed"]["MIDLAND"]["written"] is True
    assert row["cities_failed"]["MIDLAND"]["forecast_status"] == "failed"
    assert row["cities_failed"]["EL_PASO"]["outcome"] == "error"
    # per-city deltas, not the fetcher's running totals; secret-looking keys are redacted
    assert row["provider_errors"] == {
        "AUSTIN": {"nsrdb: ValueError: down": 2},
        "CORPUS_CHRISTI": {},
        "MIDLAND": {"tceq: HTTPError": 1},
        "EL_PASO": {"synoptic: token=REDACTED": 3},
    }
    assert row["sources"]["AUSTIN"] == {
        "air_temp": {"synoptic": 1}, "wind_speed": {"tceq": 1}, "solar_radiation": {"nsrdb": 1}}
    assert row["sources"]["MIDLAND"] == {}
    assert row["window_end"] == datetime(2025, 6, 1, 14, 7, tzinfo=timezone.utc)
    assert row["provider"] == "composed" and row["forecast_method"] == "ml"
    assert row["started_at"] <= row["finished_at"]
    # the whole-run keys keep their meaning
    assert run["provider_errors"]["nsrdb: ValueError: down"] == 7
    assert run["sources"]["air_temp"] == {"synoptic": 1}
    assert "run_log_error" not in run


def test_run_log_failure_is_logged_redacted_and_main_returns_one(monkeypatch, caplog, capsys):
    _fake_city_pipeline(monkeypatch)
    store = FakeStore(fail_run=True)

    with caplog.at_level(logging.ERROR, logger="dlr_orchestrator"):
        run = _run(store)

    assert [w["city"] for w in store.writes] == list(config.LOCATIONS)
    assert len(run["summary"]) == len(config.LOCATIONS)
    assert "Zq9Mk7Leak" not in run["run_log_error"]
    assert "db.example.com" not in run["run_log_error"]
    messages = [r.getMessage() for r in caplog.records if r.name == "dlr_orchestrator"]
    assert any("pipeline_run write failed" in m for m in messages)
    assert all("Zq9Mk7Leak" not in m for m in messages)

    # main turns a run-log failure into exit status 1 even though every city rated
    _fake_run_dlr_pipeline(monkeypatch, _canned_run(run_log_error="lost connection"))
    assert orch.main([]) == 1
    assert "lost connection" in capsys.readouterr().out
    _fake_run_dlr_pipeline(monkeypatch, _canned_run())
    assert orch.main([]) == 0


@pytest.mark.parametrize("argv, errors, expected", [
    (["--store", "postgres"], {"EL_PASO": "down"}, 1),
    (["--store", "postgres", "--no-run-row"], {"EL_PASO": "down"}, 1),
    (["--store", "postgres"], {}, 0),
    (["--store", "postgres", "--no-run-row"], {}, 0),
    ([], {"EL_PASO": "down"}, 0),
    (["--store", "csv"], {"EL_PASO": "down"}, 0),
])
def test_main_with_postgres_exits_one_when_any_city_failed(
        monkeypatch, capsys, argv, errors, expected):
    # WR-01: a missing city row is a data gap in the production table, so a
    # partial postgres run must not leave a scheduled job green. The CSV path
    # keeps Phase 1's rule (1 only when every city failed).
    _fake_run_dlr_pipeline(monkeypatch, _canned_run(errors=errors))

    assert orch.main(argv) == expected

    printed = capsys.readouterr().out
    for city in errors:
        assert f"ERROR {city}: down" in printed


def test_main_store_flags_extend_the_pinned_arguments_only_for_postgres(tmp_path, monkeypatch):
    seen = _fake_run_dlr_pipeline(monkeypatch, _canned_run())
    archive_path = str(tmp_path / "archive.csv")
    pinned = {
        "cities": ["MIDLAND"], "start": None, "end": _END, "window_hours": 2.0,
        "provider": "open_meteo", "forecast_method": "ewm", "archive": False,
        "archive_path": archive_path,
    }
    base = ["--cities", "MIDLAND", "--end", _END, "--window-hours", "2", "--provider", "open_meteo",
            "--forecast-method", "ewm", "--no-archive", "--archive-path", archive_path]

    assert orch.main(base) == 0
    assert orch.main(base + ["--store", "csv"]) == 0
    assert orch.main(base + ["--store", "postgres"]) == 0
    assert orch.main(base + ["--store", "postgres", "--no-run-row"]) == 0

    assert seen == [
        pinned,
        pinned,
        {**pinned, "store": "postgres", "record_run": True},
        {**pinned, "store": "postgres", "record_run": False},
    ]
    # --no-run-row means nothing without --store postgres
    with pytest.raises(SystemExit):
        orch.main(["--no-run-row"])
    with pytest.raises(SystemExit):
        orch.main(["--store", "csv", "--no-run-row"])
    with pytest.raises(SystemExit):
        orch.main(["--store", "sqlite"])
    assert len(seen) == 4


def test_no_archive_with_a_store_writes_nothing(tmp_path):
    store = FakeStore(history={"AUSTIN": _history_frame("AUSTIN", [12, 13])})

    run = _run(store, cities=list(_CITIES), archive=False, archive_path=str(tmp_path / "archive.csv"))

    assert store.reads == [(c, _END) for c in _CITIES]
    assert store.writes == []
    assert store.run_rows == []
    assert all(row["archived"] is False for row in run["summary"])
    assert run["errors"] == {}
    assert next(r for r in run["summary"] if r["city"] == "AUSTIN")["history_rows"] == 2
    assert list(tmp_path.glob("*.csv")) == []
    assert not os.path.exists(config.HISTORICAL_ARCHIVE_PATH)


# ──────────────────────────────────────────────────────────────────────────────
# Live: the orchestrator against a throwaway Postgres
# ──────────────────────────────────────────────────────────────────────────────

class _InlierModel:
    """A stand-in anomaly estimator that never trips (scikit-learn outlier convention)."""

    def predict(self, rows):
        return [1]

    def decision_function(self, rows):
        return [0.5]


def _synthetic_rating(city, hour, db_url):
    """Write one earlier-hour rating row for `city` so the next run has history."""
    result = _city_result(city, station_id=f"T_{city}", detector_model=None)
    result["rating"] = 1200.0 + hour
    result["observation"] = {"temp": 25.0, "wind": 6.5, "solar": 500.0, "wind_raw": 6.5,
                             "wind_direction": 180.0}
    result["pipeline"]["forecast_method"] = "naive"
    ctx = {"run_id": "earlier", "run_attempt": 1, "pipeline_version": "abc1234"}
    row = supabase_store.build_rating_row(result, f"2025-06-01T{hour:02d}:00:00Z", ctx)
    with supabase_store.SupabaseStore(supabase_store.connect(db_url), run_ctx=ctx) as store:
        supabase_store.upsert_rating(store.conn, row)


def _live_env(monkeypatch, admin_url, attempt="1"):
    monkeypatch.setenv("SUPABASE_DB_URL", _writer_url(admin_url))
    monkeypatch.setenv("GITHUB_RUN_ID", "4242")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", attempt)
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234567890")


def test_orchestrator_rerun_against_postgres_keeps_one_row_per_city_and_one_run_row(
        tmp_path, monkeypatch, _pg_admin_url):
    _reset(_pg_admin_url)
    _live_env(monkeypatch, _pg_admin_url)
    # Real model files (a stand-in estimator) so each city's anomaly hash is non-null.
    monkeypatch.setattr(config, "ANOMALY_ML_MODEL_DIR", str(tmp_path / "models"))
    os.makedirs(tmp_path / "models")
    for city in _CITIES:
        (tmp_path / "models" / f"anomaly_{city}.joblib").write_bytes(f"model-{city}".encode())
    monkeypatch.setattr(anomaly_detector, "_load_city_model_or_none", lambda city: _InlierModel())
    for hour in (11, 12, 13):
        _synthetic_rating("AUSTIN", hour, _writer_url(_pg_admin_url))

    first = orch.run_dlr_pipeline(
        cities=list(_CITIES), stations=_stations(), end=_END, window_hours=1.0,
        forecast_method="naive", store="postgres", fetcher=_StubFetcher())
    _live_env(monkeypatch, _pg_admin_url, attempt="2")
    second = orch.run_dlr_pipeline(
        cities=list(_CITIES), stations=_stations(), end=_END, window_hours=1.0,
        forecast_method="naive", store="postgres", fetcher=_StubFetcher())

    for run in (first, second):
        assert run["errors"] == {}
        assert "run_log_error" not in run
        by_city = {row["city"]: row for row in run["summary"]}
        assert set(by_city) == set(_CITIES)
        assert all(row["archived"] is True for row in run["summary"])
        # history_rows is what Postgres held for AUSTIN before the slot
        assert by_city["AUSTIN"]["history_rows"] == 3
        assert by_city["EL_PASO"]["history_rows"] == 0

    at_slot = _admin_rows(_pg_admin_url, "select * from public.city_rating where valid_time = %s "
                          "order by city", (_SLOT,))
    assert [r["city"] for r in at_slot] == list(_CITIES)
    assert _admin_rows(_pg_admin_url, "select count(*) as n from public.city_rating")[0]["n"] == 3 + 2
    assert all(r["run_id"] == "4242" and r["run_attempt"] == 2 for r in at_slot)

    runs = _admin_rows(_pg_admin_url, "select * from public.pipeline_run")
    assert len(runs) == 1
    run_row = runs[0]
    assert run_row["run_id"] == "4242"
    assert run_row["run_attempt"] == 2          # the re-run attempt replaced the row
    assert run_row["finished_at"] is not None and run_row["finished_at"] >= run_row["started_at"]
    assert run_row["window_end"] == datetime(2025, 6, 1, 14, 7, tzinfo=timezone.utc)
    assert run_row["cities_ok"] == list(_CITIES)
    assert run_row["cities_failed"] == {}
    assert run_row["provider"] == "composed" and run_row["forecast_method"] == "naive"
    assert run_row["pipeline_version"] == "abcdef1"
    assert set(run_row["sources"]) == set(_CITIES)

    # DB-06 through the production seam: each row names its own city's assumptions and models.
    by_city = {r["city"]: r for r in at_slot}
    assert by_city["AUSTIN"]["config_fingerprint"] == supabase_store.rating_config_fingerprint("AUSTIN")
    assert by_city["EL_PASO"]["config_fingerprint"] == supabase_store.rating_config_fingerprint("EL_PASO")
    assert by_city["AUSTIN"]["config_fingerprint"] != by_city["EL_PASO"]["config_fingerprint"]
    for result in second["results"]:
        row = by_city[result["city"]]
        assert row["forecast_method"] == "naive"
        assert row["forecast_model_sha256"] is None
        detector_model = result["pipeline"]["detector_model"]
        assert detector_model is not None
        assert row["anomaly_model_sha256"] == supabase_store.file_sha256(detector_model)
        assert row["config_version"] == config.RATING_CONFIG_VERSION

    # Nothing was written to a CSV archive.
    assert not os.path.exists(config.HISTORICAL_ARCHIVE_PATH)
    assert list(tmp_path.glob("*.csv")) == []


def test_orchestrator_reads_its_history_from_postgres(tmp_path, monkeypatch, _pg_admin_url):
    _reset(_pg_admin_url)
    _live_env(monkeypatch, _pg_admin_url)
    for hour in (11, 12, 13):
        _synthetic_rating("AUSTIN", hour, _writer_url(_pg_admin_url))
    seen = {}
    real_forecast = ampacity_forecast.forecast_ampacity

    def spy(history, method="naive", **kw):
        seen["history"] = history.copy()
        return real_forecast(history, method=method, **kw)

    monkeypatch.setattr(ampacity_forecast, "forecast_ampacity", spy)

    run = orch.run_dlr_pipeline(
        cities=["AUSTIN"], stations=_stations(), end=_END, window_hours=1.0,
        forecast_method="naive", store="postgres", archive=False, fetcher=_StubFetcher())

    assert run["errors"] == {}
    history = seen["history"]
    assert list(history["dlr_amps"]) == [1211.0, 1212.0, 1213.0]
    assert list(history["datetime_utc"]) == [
        "2025-06-01T11:00:00Z", "2025-06-01T12:00:00Z", "2025-06-01T13:00:00Z"]
    assert run["summary"][0]["history_rows"] == 3
    # --no-archive with a store: nothing written, no rating row and no run row
    assert run["summary"][0]["archived"] is False
    assert _admin_rows(_pg_admin_url, "select count(*) as n from public.city_rating")[0]["n"] == 3
    assert _admin_rows(_pg_admin_url, "select count(*) as n from public.pipeline_run")[0]["n"] == 0


def test_history_window_boundary_against_postgres(_pg_admin_url):
    _reset(_pg_admin_url)
    db_url = _writer_url(_pg_admin_url)
    slot = datetime(2025, 7, 1, 12, 0, tzinfo=timezone.utc)
    ctx = {"run_id": "boundary", "run_attempt": 1, "pipeline_version": "abc1234"}
    offsets = {
        "30 days before the slot": pd.Timedelta(days=30),
        "30 days and an hour before": pd.Timedelta(days=30, hours=1),
        "the slot itself": pd.Timedelta(0),
        "the hour before the slot": pd.Timedelta(hours=1),
    }
    with supabase_store.SupabaseStore(supabase_store.connect(db_url), run_ctx=ctx) as store:
        for offset in offsets.values():
            at = (slot - offset.to_pytimedelta()).strftime("%Y-%m-%dT%H:%M:%SZ")
            result = _city_result("AUSTIN", station_id="T_AUSTIN", detector_model=None)
            result["observation"] = {"temp": 25.0, "wind": 6.5, "solar": 500.0, "wind_raw": 6.5,
                                     "wind_direction": 180.0}
            result["pipeline"]["forecast_method"] = "naive"
            supabase_store.upsert_rating(store.conn, supabase_store.build_rating_row(result, at, ctx))

        frame = store.read_history("AUSTIN", "2025-07-01T12:20:00Z")

    assert list(frame["datetime_utc"]) == ["2025-06-01T12:00:00Z", "2025-07-01T11:00:00Z"]
