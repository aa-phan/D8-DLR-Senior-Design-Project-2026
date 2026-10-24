"""
Tests that a live run's stdout carries no stray diagnostic or gate lines
(Phase 5, STATE.md item 4): `dlr_pipeline.fetch_timeseries` reports through the
`dlr_pipeline` logger at DEBUG, and `DLRSafetyMonitor` without an injected
logger reports a gate failure as a WARNING on the `DLRSafetyMonitor` logger.

Every provider call is stubbed; nothing here touches the network or the
repository's data. Follows backend/tests/dlr_orchestrator_test.py's
conventions (module-level imports, plain asserts, no test classes, no network).
"""

import logging

import pandas as pd
import pytest
import requests

import anomaly_detector
import config
import dlr_pipeline
from DLRSafetyMonitor import DLRSafetyMonitor


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """
    Replace `requests.get` for every test. A test that needs a response installs
    its own stub; any call that reaches this one is recorded and fails the test
    at teardown even if a caller swallowed the exception.
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
    monkeypatch.setattr(anomaly_detector, "_load_city_model_or_none", lambda city: None)


_VALID_READING = {
    "sensor_status": "ok",
    "link_status": "ok",
    "wind": 5.0,
    "temp": 25.0,
    "solar": 500.0,
}

# Bounds no real ampacity can satisfy, so the valid reading fails G4.
_IMPOSSIBLE_BOUNDS = (1, 2)


def _failing_monitor(**kwargs):
    return DLRSafetyMonitor(static_rating=1690.0, rating_bounds=_IMPOSSIBLE_BOUNDS, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# dlr_pipeline.fetch_timeseries
# ──────────────────────────────────────────────────────────────────────────────

_TIMES = ["2025-06-01T10:00:00Z", "2025-06-01T10:05:00Z"]


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _payload():
    return {
        "SUMMARY": {"RESPONSE_MESSAGE": "OK", "NUMBER_OF_OBJECTS": 2},
        "STATION": [
            {"STID": "AAA1", "LATITUDE": "30.25", "LONGITUDE": "-97.75",
             "OBSERVATIONS": {
                 "date_time": _TIMES,
                 "air_temp_set_1": [25.0, 25.5],
                 "wind_speed_set_1": [4.0, 4.5],
                 "wind_direction_set_1": [90.0, 95.0],
                 "wind_gust_set_1": [6.0, 6.5],
                 "solar_radiation_set_1": [500.0, 510.0],
                 "relative_humidity_set_1": [40.0, 41.0]}},
            # A station with only some variables and no coordinates.
            {"STID": "BBB2", "LATITUDE": None, "LONGITUDE": "n/a",
             "OBSERVATIONS": {"date_time": _TIMES, "air_temp_set_1": [20.0, 21.0]}},
        ],
    }


def _stub_synoptic(monkeypatch):
    seen = []

    def fake_get(url, params=None, timeout=None, **kwargs):
        seen.append({"url": url, "params": params, "timeout": timeout})
        return _Response(_payload())

    monkeypatch.setenv("SYNOPTIC_TOKEN", "dummy-token-for-tests")
    monkeypatch.setattr(dlr_pipeline.requests, "get", fake_get)
    return seen


def test_fetch_timeseries_prints_nothing(monkeypatch, capsys, caplog):
    _stub_synoptic(monkeypatch)

    with caplog.at_level(logging.DEBUG, logger="dlr_pipeline"):
        frame = dlr_pipeline.fetch_timeseries(["AAA1", "BBB2"], "2025-06-01T10:00:00Z",
                                              "2025-06-01T10:05:00Z")

    assert capsys.readouterr().out == ""
    debug = [r.getMessage() for r in caplog.records
             if r.name == "dlr_pipeline" and r.levelno == logging.DEBUG]
    assert any("SUMMARY" in m and "NUMBER_OF_OBJECTS" in m for m in debug)
    assert any("Returned stations" in m and "2" in m for m in debug)
    assert any("STID" in m and "AAA1" in m for m in debug)
    assert any("OBS keys" in m and "air_temp_set_1" in m for m in debug)
    # one STID line and one OBS keys line per station
    assert sum("STID" in m for m in debug) == 2
    assert sum("OBS keys" in m for m in debug) == 2
    # the diagnostics are not promoted to the root's INFO output
    assert not [r for r in caplog.records
                if r.name == "dlr_pipeline" and r.levelno > logging.DEBUG
                and "Returned stations" in r.getMessage()]


def test_fetch_timeseries_returns_the_same_frame_and_sends_the_same_request(monkeypatch):
    seen = _stub_synoptic(monkeypatch)

    frame = dlr_pipeline.fetch_timeseries(["AAA1", "BBB2"], "2025-06-01T10:00:00Z",
                                          "2025-06-01T10:05:00Z")

    assert len(seen) == 1
    assert seen[0]["url"] == f"{dlr_pipeline.SYNOPTIC_BASE}/stations/timeseries"
    assert seen[0]["timeout"] == 120
    assert seen[0]["params"] == {
        "token": "dummy-token-for-tests",
        "stid": "AAA1,BBB2",
        "vars": ",".join(dlr_pipeline.DLR_VARS),
        "start": "202506011000",
        "end": "202506011005",
        "obtimezone": "UTC",
        "units": "metric",
        "output": "json",
        "showemptystations": 1,
        "showemptyvars": 1,
        "qc": "off",
    }

    times = pd.to_datetime(_TIMES, utc=True)
    expected = pd.DataFrame({
        "stid": ["AAA1"] * 2 + ["BBB2"] * 2,
        "datetime_utc": list(times) * 2,
        "air_temp": [25.0, 25.5, 20.0, 21.0],
        "wind_speed": [4.0, 4.5, None, None],
        "wind_direction": [90.0, 95.0, None, None],
        "wind_gust": [6.0, 6.5, None, None],
        "solar_radiation": [500.0, 510.0, None, None],
        "relative_humidity": [40.0, 41.0, None, None],
        "lat": [30.25, 30.25, None, None],
        "lon": [-97.75, -97.75, None, None],
    }).set_index(["stid", "datetime_utc"]).sort_index()
    pd.testing.assert_frame_equal(frame, expected, check_dtype=False)


# ──────────────────────────────────────────────────────────────────────────────
# DLRSafetyMonitor default logger
# ──────────────────────────────────────────────────────────────────────────────

def test_safety_monitor_default_logger_warns_instead_of_printing(capsys, caplog):
    monitor = _failing_monitor()

    with caplog.at_level(logging.WARNING, logger="DLRSafetyMonitor"):
        result = monitor.run_check(_VALID_READING)

    assert capsys.readouterr().out == ""
    warnings = [r for r in caplog.records if r.name == "DLRSafetyMonitor"]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    assert "G4 FAIL" in warnings[0].getMessage()
    assert result["alerts"][0].startswith("G4 FAIL")
    assert warnings[0].getMessage() == result["alerts"][0]
    assert result["fallback"] is True
    assert result["rating"] == 1690.0


def test_injected_logger_still_receives_the_gate_message(capsys, caplog):
    messages = []
    monitor = _failing_monitor(logger=messages.append)

    with caplog.at_level(logging.DEBUG, logger="DLRSafetyMonitor"):
        result = monitor.run_check(_VALID_READING)

    assert messages == result["alerts"]
    assert messages[0].startswith("G4 FAIL")
    # an injected logger replaces the default: nothing is printed or logged twice
    assert capsys.readouterr().out == ""
    assert [r for r in caplog.records if r.name == "DLRSafetyMonitor"] == []
