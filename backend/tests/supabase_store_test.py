"""
Offline tests of the Postgres writer's row shaping, SQL, history frame and secret
hygiene (production-pipeline Phase 4, DB-01, DB-02, DB-04).

A fake connection stands in for psycopg: it records each statement with its
parameters and returns preset rows, so nothing needs a database or the network.
The real database behavior is proven in supabase_live_test.py. Follows
backend/tests/city_rating_test.py's conventions (module-level imports, plain
asserts, no test classes, no network).
"""

import contextlib
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import numpy as np
import pandas as pd
import pytest
import requests

import ampacity_forecast
import anomaly_detector
import config
import data_cleaning
import ercot_dlr_merger
import historical_archive
import supabase_store

_UTC = timezone.utc
_RUN_CTX = {"run_id": "123", "run_attempt": 2, "pipeline_version": "abcdef1"}
_PROVENANCE = {"stid": "T_AUSTIN", "hour": "2025-06-01T14:00:00Z", "air_temp": "synoptic",
               "wind_speed": "tceq", "solar_radiation": "nsrdb"}
_END = "2025-06-01T14:07:00Z"

# A marker credential, assembled from pieces so no literal credential URL is in this file.
_MARKER = "Mk7" + "Zq9" + "Leak"


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


def _url(user, secret, host):
    """A connection URL built from separate pieces (so no literal credential URL sits in this file)."""
    return "postgresql" + "://" + user + ":" + secret + "@" + host


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


def _exhausted_result():
    return _result(
        rating=1825.0, status="fallback", fallback=True, observation=None, exhausted=True,
        station_id=None, candidates_probed=3,
        alerts=["EXHAUSTED FAIL (AUSTIN: 3 candidates exhausted) — fallback rating 1825 A"],
    )


class _Column:
    def __init__(self, name):
        self.name = name


class FakeCursor:
    def __init__(self, rows, names):
        self._rows = rows
        self.description = [_Column(name) for name in names]

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    """Records (normalized sql, params) and whether it ran inside `transaction()`."""

    def __init__(self, rows=None, names=None, error=None):
        self.calls = []
        self.in_transaction = []
        self.transactions = 0
        self._depth = 0
        self._rows = rows or []
        self._names = names or []
        self._error = error

    def execute(self, sql, params=None):
        if self._error is not None:
            raise self._error
        self.calls.append((" ".join(sql.split()), params))
        self.in_transaction.append(self._depth > 0)
        return FakeCursor(self._rows, self._names)

    @contextlib.contextmanager
    def transaction(self):
        self.transactions += 1
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1


def _native(value):
    return value is None or type(value) in (str, int, float, bool, list, datetime)


def test_build_rating_row_uses_python_types_and_the_mw_golden():
    result = _result(
        rating=np.float64(1825.0), candidates_probed=np.int64(1),
        observation={"temp": np.float64(25.0), "wind": np.float64(6.5), "solar": np.float64(500.0),
                     "wind_direction": np.float64(263.15), "wind_raw": np.float64(6.5)},
    )
    result["pipeline"]["forecast"] = {
        "amps": np.float64(1700.0), "ci_lower_amps": 1650.0, "ci_upper_amps": 1750.0,
        "n_observations": np.int64(40), "horizon_min": 60.0}
    result["pipeline"]["history_rows"] = np.int64(10)

    row = supabase_store.build_rating_row(result, _END, _RUN_CTX, _PROVENANCE)

    assert tuple(row) == supabase_store.CITY_RATING_COLUMNS
    for key, value in row.items():
        assert _native(value), (key, type(value))
    assert row["rating_amps"] == 1825.0
    assert row["rating_mw"] == pytest.approx(1036.0153652297765, abs=1e-9)
    assert row["rating_mw"] == pytest.approx(
        ercot_dlr_merger.amps_to_mw(1825.0, config.LINE_VOLTAGE_KV, config.POWER_FACTOR), abs=1e-9)
    assert row["static_rating_amps"] == config.STATIC_RATINGS["AUSTIN"]
    assert row["static_rating_mw"] == pytest.approx(
        ercot_dlr_merger.amps_to_mw(config.STATIC_RATINGS["AUSTIN"], 345.0, 0.95), abs=1e-9)
    assert (row["line_voltage_kv"], row["power_factor"]) == (config.LINE_VOLTAGE_KV, config.POWER_FACTOR)
    assert row["wind_perp_ms"] == 6.5 and row["wind_speed_ms"] == 6.5
    assert row["air_temp_c"] == 25.0 and row["solar_radiation_wm2"] == 500.0
    assert row["wind_direction_deg"] == 263.15
    assert row["forecast_amps"] == 1700.0 and row["forecast_n_observations"] == 40
    assert row["rating_basis"] == config.RATING_BASIS
    assert row["config_version"] == config.RATING_CONFIG_VERSION
    assert row["origin"] == "live" and row["schema_version"] == supabase_store.CITY_RATING_SCHEMA_VERSION
    assert (row["run_id"], row["run_attempt"], row["pipeline_version"]) == ("123", 2, "abcdef1")
    # Whole seconds are the database's job: the row carries no first_written_at / computed_at.
    assert "first_written_at" not in row and "computed_at" not in row


@pytest.mark.parametrize("end", [
    "2025-06-01T14:00:00Z",
    "2025-06-01T14:59:59Z",
    "2025-06-01T14:07:00",
    "2025-06-01T09:30:00-05:00",
    pd.Timestamp("2025-06-01T14:30:00Z"),
])
def test_valid_time_is_the_floored_utc_hour(end):
    expected = datetime(2025, 6, 1, 14, 0, tzinfo=_UTC)
    assert supabase_store.slot_of(end) == expected
    assert supabase_store.slot_of(end).tzinfo is not None
    row = supabase_store.build_rating_row(_result(), end, _RUN_CTX)
    assert row["valid_time"] == expected
    assert row["valid_time"].utcoffset() == timedelta(0)

    with pytest.raises(ValueError, match="not-a-time"):
        supabase_store.slot_of("not-a-time")


def test_non_finite_inputs_become_null_and_a_bad_rating_is_refused():
    result = _result()
    result["observation"].update({"temp": float("nan"), "wind": float("inf"), "wind_direction": -math.inf})
    result["pipeline"]["forecast"] = {
        "amps": 1700.0, "ci_lower_amps": float("nan"), "ci_upper_amps": float("inf"),
        "n_observations": 40, "horizon_min": float("nan")}

    row = supabase_store.build_rating_row(result, _END, _RUN_CTX)
    for key in ("air_temp_c", "wind_perp_ms", "wind_direction_deg",
                "forecast_ci_lower_amps", "forecast_ci_upper_amps", "forecast_horizon_min"):
        assert row[key] is None, key
    assert row["solar_radiation_wm2"] == 500.0

    for bad in (float("nan"), float("inf"), float("-inf"), 0.0, -1.0, None):
        with pytest.raises(ValueError, match="rating"):
            supabase_store.build_rating_row(_result(rating=bad), _END, _RUN_CTX)


def test_exhausted_result_writes_nulls_and_the_exhausted_gate():
    row = supabase_store.build_rating_row(_exhausted_result(), _END, _RUN_CTX)
    for key in ("observation_time", "station_id", "air_temp_c", "wind_perp_ms", "wind_speed_ms",
                "wind_direction_deg", "solar_radiation_wm2", "temp_source", "wind_source", "solar_source"):
        assert row[key] is None, key
    assert row["exhausted"] is True
    assert row["fallback_gates"] == ["EXHAUSTED"]
    assert row["status"] == "fallback" and row["fallback"] is True
    assert row["rating_amps"] == config.STATIC_RATINGS["AUSTIN"]
    assert row["candidates_probed"] == 3

    clean = supabase_store.build_rating_row(_result(), _END, _RUN_CTX)
    assert clean["alerts"] == [] and clean["fallback_gates"] == []


def test_gates_are_sorted_unique_first_tokens_and_alerts_keep_utf8():
    alerts = [
        "G4 FAIL (implausible (1080 A)) — fallback rating 1825 A",
        "G6 FAIL (forecast residual)",
        "G4 FAIL (again)",
        "G1 FAIL (stale)",
    ]
    row = supabase_store.build_rating_row(_result(alerts=alerts), _END, _RUN_CTX)
    assert row["fallback_gates"] == ["G1", "G4", "G6"]
    assert row["alerts"] == alerts
    assert "—" in row["alerts"][0]


def test_probe_trail_is_json_text_without_numpy_or_nan():
    trail = [
        {"stid": "A", "lat": np.float64(30.1), "lon": -97.7, "distance_km": np.float64("nan"),
         "outcome": "stale", "rank": np.int64(1), "ok": np.bool_(False)},
        {"stid": "B", "lat": 30.2, "lon": -97.8, "distance_km": float("inf"), "outcome": "ok"},
    ]
    row = supabase_store.build_rating_row(_result(probe_trail=trail), _END, _RUN_CTX)
    text = row["probe_trail"]
    assert isinstance(text, str)
    assert "NaN" not in text and "Infinity" not in text
    parsed = json.loads(text)
    assert parsed[0]["lat"] == 30.1 and parsed[0]["distance_km"] is None
    assert parsed[0]["rank"] == 1 and parsed[0]["ok"] is False
    assert parsed[1]["distance_km"] is None
    assert json.loads(supabase_store.build_rating_row(_result(probe_trail=[]), _END, _RUN_CTX)["probe_trail"]) == []


def test_provenance_maps_observation_hour_and_sources():
    row = supabase_store.build_rating_row(_result(), _END, _RUN_CTX, _PROVENANCE)
    assert row["observation_time"] == datetime(2025, 6, 1, 14, 0, tzinfo=_UTC)
    assert (row["temp_source"], row["wind_source"], row["solar_source"]) == ("synoptic", "tceq", "nsrdb")

    shifted = dict(_PROVENANCE, hour="2025-06-01T08:00:00-05:00")
    assert supabase_store.build_rating_row(_result(), _END, _RUN_CTX, shifted)["observation_time"] == \
        datetime(2025, 6, 1, 13, 0, tzinfo=_UTC)

    none = supabase_store.build_rating_row(_result(), _END, _RUN_CTX, None)
    assert none["observation_time"] is None
    assert (none["temp_source"], none["wind_source"], none["solar_source"]) == (None, None, None)


def test_detector_path_is_stored_only_as_a_boolean(tmp_path):
    model = tmp_path / "anomaly_AUSTIN.joblib"
    model.write_bytes(b"model")
    result = _result()
    result["pipeline"]["detector_model"] = str(model)

    row = supabase_store.build_rating_row(result, _END, _RUN_CTX)
    assert row["detector_model_loaded"] is True
    assert row["anomaly_model_sha256"] == supabase_store.file_sha256(str(model))
    dump = repr(row)
    assert str(tmp_path) not in dump and "anomaly_AUSTIN.joblib" not in dump

    assert supabase_store.build_rating_row(_result(), _END, _RUN_CTX)["detector_model_loaded"] is False


def test_upsert_sends_one_parameterized_statement():
    injection = "x'); drop table public.city_rating; --"
    row = supabase_store.build_rating_row(_result(alerts=[injection]), _END, _RUN_CTX)
    conn = FakeConn()

    supabase_store.upsert_rating(conn, row)

    assert len(conn.calls) == 1 and conn.transactions == 1 and conn.in_transaction == [True]
    sql, params = conn.calls[0]
    assert tuple(params) == supabase_store.CITY_RATING_COLUMNS
    assert params["alerts"] == [injection]
    assert injection not in sql and "drop table" not in sql
    assert sql.startswith("insert into public.city_rating")
    assert "on conflict (city, valid_time) do update set" in sql
    assert "first_written_at" not in sql

    # A database failure becomes a StoreError carrying no connection detail.
    leaky = _url("dlr_writer", _MARKER, "db.example.invalid:5432/postgres")
    failing = FakeConn(error=RuntimeError(f"server closed the connection ({leaky})"))
    with pytest.raises(supabase_store.StoreError) as raised:
        supabase_store.upsert_rating(failing, row)
    assert _MARKER not in str(raised.value) and "db.example.invalid" not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_read_history_excludes_the_current_slot_and_bounds_the_window(monkeypatch):
    conn = FakeConn()
    frame = supabase_store.read_history(conn, "AUSTIN", "2025-06-01T14:30:00Z")
    sql, params = conn.calls[0]
    slot = datetime(2025, 6, 1, 14, 0, tzinfo=_UTC)
    assert params == {"city": "AUSTIN", "slot": slot, "since": slot - timedelta(days=30)}
    assert config.DB_HISTORY_WINDOW_DAYS == 30
    assert "valid_time < %(slot)s" in sql
    assert "valid_time >= %(since)s" in sql
    assert "not exhausted" in sql
    assert "order by valid_time" in sql
    assert "city = %(city)s" in sql
    assert frame.empty and list(frame.columns) == historical_archive.ARCHIVE_COLUMNS

    supabase_store.read_history(conn, "AUSTIN", "2025-06-01T14:30:00Z", days=7)
    assert conn.calls[1][1]["since"] == slot - timedelta(days=7)

    monkeypatch.setattr(config, "DB_HISTORY_WINDOW_DAYS", 10)
    store = supabase_store.SupabaseStore(conn, run_ctx=_RUN_CTX)
    store.read_history("AUSTIN", "2025-06-01T14:59:00Z")
    assert conn.calls[2][1]["since"] == slot - timedelta(days=10)
    store = supabase_store.SupabaseStore(conn, run_ctx=_RUN_CTX, history_days=3)
    store.read_history("AUSTIN", "2025-06-01T14:59:00Z")
    assert conn.calls[3][1]["since"] == slot - timedelta(days=3)


_HISTORY_NAMES = ["datetime_utc", "city", "air_temp", "wind_speed", "solar_radiation",
                  "dlr_amps", "static_rating", "status", "fallback"]


def test_history_frame_has_archive_columns_and_csv_spelling():
    rows = [
        ("2025-06-01T10:00:00Z", "AUSTIN", 25.0, 6.5, 500.0, 1700.0, 1825.0, "ok", False),
        ("2025-06-01T11:00:00Z", "AUSTIN", None, 6.0, 450.0, 1825.0, 1825.0, "fallback", True),
    ]
    conn = FakeConn(rows=rows, names=_HISTORY_NAMES)
    frame = supabase_store.read_history(conn, "AUSTIN", "2025-06-01T15:05:00Z")

    assert list(frame.columns) == historical_archive.ARCHIVE_COLUMNS
    assert list(frame["datetime_utc"]) == ["2025-06-01T10:00:00Z", "2025-06-01T11:00:00Z"]
    for column in ("air_temp", "wind_speed", "solar_radiation", "dlr_amps", "static_rating"):
        assert str(frame[column].dtype) == "float64", column
    assert math.isnan(frame["air_temp"].iloc[1])
    assert frame["fallback"].tolist() == [False, True]
    assert (frame["schema_version"] == historical_archive.ARCHIVE_SCHEMA_VERSION).all()


def test_history_frame_matches_the_csv_reader_for_the_same_rows(tmp_path):
    base = pd.Timestamp("2025-06-01T00:00:00Z")
    records = []
    for hour in range(30):
        records.append({
            "datetime_utc": (base + pd.Timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "city": "AUSTIN",
            "air_temp": 20.0 + 5.0 * math.sin(hour / 4.0),
            "wind_speed": 4.0 + math.cos(hour / 3.0),
            "solar_radiation": max(0.0, 600.0 * math.sin(hour / 3.8)),
            "dlr_amps": 1600.0 + 120.0 * math.sin(hour / 5.0),
            "static_rating": 1825.0,
            "status": "ok",
            "fallback": False,
            "schema_version": historical_archive.ARCHIVE_SCHEMA_VERSION,
        })
    csv_path = tmp_path / "archive.csv"
    pd.DataFrame(records, columns=historical_archive.ARCHIVE_COLUMNS).to_csv(csv_path, index=False)

    from_csv = historical_archive.read_history(path=str(csv_path), city="AUSTIN")
    rows = [tuple(record[name] for name in _HISTORY_NAMES) for record in records]
    from_db = supabase_store.read_history(
        FakeConn(rows=rows, names=_HISTORY_NAMES), "AUSTIN", "2025-06-02T12:30:00Z")

    assert list(from_csv.columns) == list(from_db.columns)
    pd.testing.assert_frame_equal(
        from_csv.reset_index(drop=True), from_db.reset_index(drop=True), check_dtype=False)

    as_of = "2025-06-02T12:30:00Z"
    for method in ("naive", "ewm"):
        csv_forecast = ampacity_forecast.forecast_ampacity(
            data_cleaning.clean_history(from_csv, as_of=as_of).usable, method=method)
        db_forecast = ampacity_forecast.forecast_ampacity(
            data_cleaning.clean_history(from_db, as_of=as_of).usable, method=method)
        assert csv_forecast is not None and db_forecast is not None
        # pandas' default CSV float parser can differ from the exact value by one ulp,
        # so the CSV side is compared to within 1e-12 relative, not bit for bit.
        assert csv_forecast.n_observations == db_forecast.n_observations
        assert csv_forecast.amps == pytest.approx(db_forecast.amps, rel=1e-12)
        assert csv_forecast.ci_lower_amps == pytest.approx(db_forecast.ci_lower_amps, rel=1e-12)
        assert csv_forecast.ci_upper_amps == pytest.approx(db_forecast.ci_upper_amps, rel=1e-12)

    csv_report = data_cleaning.clean_history(from_csv, as_of=as_of).report
    db_report = data_cleaning.clean_history(from_db, as_of=as_of).report
    assert csv_report["flag_counts"] == db_report["flag_counts"]
    assert csv_report == db_report


def test_connect_without_url_raises_naming_the_variable(monkeypatch):
    import psycopg

    def boom(*args, **kwargs):
        raise AssertionError("psycopg.connect must not be called without a URL")

    monkeypatch.setattr(psycopg, "connect", boom)

    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with pytest.raises(supabase_store.StoreError, match="SUPABASE_DB_URL"):
        supabase_store.connect()
    for blank in ("", "   "):
        monkeypatch.setenv("SUPABASE_DB_URL", blank)
        with pytest.raises(supabase_store.StoreError, match="SUPABASE_DB_URL"):
            supabase_store.connect()
    with pytest.raises(supabase_store.StoreError, match="SUPABASE_DB_URL"):
        supabase_store.connect("  ")


def _chain_text(exc):
    parts = []
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        parts.append(f"{type(exc).__name__}: {exc}")
        exc = exc.__cause__ or exc.__context__
    return "\n".join(parts)


def test_connection_failure_does_not_leak_the_password(monkeypatch, caplog):
    # Port 9 on loopback refuses at once, and psycopg's error text for it is not under our control.
    secrets = [_MARKER, "Mk7Zq9%40Leak"]
    for secret in secrets:
        url = _url("dlr_writer", secret, "127.0.0.1:9/postgres")
        monkeypatch.setenv("SUPABASE_DB_URL", url)
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(supabase_store.StoreError) as raised:
                supabase_store.connect()
        for forbidden in (secret, unquote(secret)):
            assert forbidden not in str(raised.value)
            assert forbidden not in caplog.text
            assert forbidden not in _chain_text(raised.value)
        assert url not in str(raised.value)
        assert "database connection failed" in str(raised.value)
        assert raised.value.__cause__ is None and raised.value.__context__ is None

    # The same through an explicit argument, with no environment variable set.
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with pytest.raises(supabase_store.StoreError) as raised:
        supabase_store.connect(_url("dlr_writer", _MARKER, "127.0.0.1:9/postgres"))
    assert _MARKER not in _chain_text(raised.value)


def test_redact_removes_urls_key_values_and_env_secrets(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ADMIN_DB_URL", raising=False)

    url = _url("dlr_writer.projref", _MARKER, "aws-0-us-east-1.pooler.example.invalid:5432/postgres")
    cleaned = supabase_store.redact(f"could not connect to {url}?sslmode=require: refused")
    assert _MARKER not in cleaned and "pooler.example.invalid" not in cleaned
    assert "postgresql://REDACTED" in cleaned

    text = "password=abc123 token=xyz&key=k9 API_KEY=zzz secret=s3 apikey=q1 user=ok"
    cleaned = supabase_store.redact(text)
    for leaked in ("abc123", "xyz", "k9", "zzz", "s3", "q1"):
        assert leaked not in cleaned, leaked
    assert "user=ok" in cleaned

    # Secret values from the environment are removed wherever they appear, raw and percent-decoded.
    monkeypatch.setenv("SUPABASE_DB_URL", _url("dlr_writer", "Ab%40Cd" + _MARKER, "host.example.invalid:5432/db"))
    monkeypatch.setenv("SUPABASE_ADMIN_DB_URL", _url("postgres", "AdminSecret" + _MARKER, "host.example.invalid:5432/db"))
    cleaned = supabase_store.redact(
        f"bad value Ab%40Cd{_MARKER} and Ab@Cd{_MARKER} and AdminSecret{_MARKER} and host.example.invalid")
    assert _MARKER not in cleaned and "AdminSecret" not in cleaned

    # An explicit secrets list replaces the environment default.
    assert supabase_store.redact("keep ENVONLY drop THIS", secrets=["THIS"]) == "keep ENVONLY drop REDACTED"

    assert len(supabase_store.redact("x" * 1000)) == 300
    assert supabase_store.redact(None) == ""


def test_run_context_reads_github_env_and_falls_back_locally():
    env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_SHA": "abcdef123456"}
    assert supabase_store.run_context(env) == {
        "run_id": "123", "run_attempt": 2, "pipeline_version": "abcdef1"}

    local = supabase_store.run_context({})
    assert local["run_id"].startswith("local-")
    assert local["run_attempt"] == 1
    assert isinstance(local["pipeline_version"], str) and local["pipeline_version"]
    assert supabase_store.run_context({})["run_id"] != local["run_id"]
