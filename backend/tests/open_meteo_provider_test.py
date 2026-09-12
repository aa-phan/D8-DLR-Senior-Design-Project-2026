"""
Tests for backend/open_meteo_provider.py (C4, Phase 7 / WX-04).

Covers the Open-Meteo Archive API fetch-and-normalize module: variable
mapping into PIPELINE_SCHEMA-named columns, the metres-per-second wind
request parameter, tz-aware UTC timestamps (RESEARCH.md Pitfall 3), and the
single-request guarantee. Task 2 adds the fail-loud body-shape checks --
there is deliberately no non-fatal empty case on this standalone grid path
(D-04/D-05), unlike asos_provider's real-outage carve-out.

Follows backend/tests/asos_provider_test.py's `_FakeResponse` +
`monkeypatch.setattr(module.requests, "get", ...)` convention. Module-level
plain-assert functions, no test classes -- matches every existing test
file's convention in this project.
"""

import pandas as pd
import pytest
import requests

import units_def

import open_meteo_provider


def _archive_payload(n_hours: int = 2) -> dict:
    """
    Shared payload builder in the live-confirmed Open-Meteo Archive API
    response shape: offset-free ISO `time` strings (RESEARCH Pitfall 3),
    `hourly_units` echoing the five variables' units, and one array per
    mapped variable.
    """
    times = [f"2025-07-01T{h:02d}:00" for h in range(n_hours)]
    return {
        "latitude": 30.263618,
        "longitude": -97.69321,
        "hourly_units": {
            "time": "iso8601",
            "temperature_2m": "°C",
            "wind_speed_10m": "m/s",
            "wind_direction_10m": "°",
            "shortwave_radiation": "W/m²",
            "relative_humidity_2m": "%",
        },
        "hourly": {
            "time": times,
            "temperature_2m": [29.9 + i for i in range(n_hours)],
            "wind_speed_10m": [3.4 + i * 0.1 for i in range(n_hours)],
            "wind_direction_10m": [160 + i for i in range(n_hours)],
            "shortwave_radiation": [291.0 + i for i in range(n_hours)],
            "relative_humidity_2m": [63 + i for i in range(n_hours)],
        },
    }


class _FakeResponse:
    def __init__(self, payload=None, json_exc=None):
        self._payload = payload
        self._json_exc = json_exc

    def raise_for_status(self):
        pass

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._payload


def _mock_get(monkeypatch, payload=None, json_exc=None, recorder=None):
    def fake_get(url, params=None, timeout=None):
        if recorder is not None:
            recorder["calls"] = recorder.get("calls", 0) + 1
            recorder["params"] = params
            recorder["url"] = url
        return _FakeResponse(payload=payload, json_exc=json_exc)

    monkeypatch.setattr(open_meteo_provider.requests, "get", fake_get)


# ──────────────────────────────────────────────────────────────────────────
# Task 1: happy path, unit contract, tz-awareness, single-request guarantee
# ──────────────────────────────────────────────────────────────────────────


def test_fetch_open_meteo_returns_all_five_pipeline_columns(monkeypatch):
    _mock_get(monkeypatch, payload=_archive_payload(n_hours=2))

    frame = open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    assert list(frame.columns) == [
        "datetime_utc",
        "air_temp",
        "wind_speed",
        "wind_direction",
        "solar_radiation",
        "relative_humidity",
    ]
    assert len(frame) == 2


def test_fetch_open_meteo_maps_each_provider_variable_to_its_pipeline_column(monkeypatch):
    payload = _archive_payload(n_hours=2)
    _mock_get(monkeypatch, payload=payload)

    frame = open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    for provider_key, pipeline_col in open_meteo_provider.HOURLY_TO_PIPELINE.items():
        assert list(frame[pipeline_col]) == payload["hourly"][provider_key]


def test_fetch_open_meteo_timestamps_are_tz_aware_utc(monkeypatch):
    payload = _archive_payload(n_hours=2)
    assert not payload["hourly"]["time"][0].endswith("Z")
    _mock_get(monkeypatch, payload=payload)

    frame = open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    assert frame["datetime_utc"].dt.tz is not None
    assert str(frame["datetime_utc"].dt.tz) == "UTC"


def test_fetch_open_meteo_requests_metres_per_second_wind(monkeypatch):
    recorder = {}
    _mock_get(monkeypatch, payload=_archive_payload(n_hours=2), recorder=recorder)

    open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-02")

    params = recorder["params"]
    assert params["wind_speed_unit"] == "ms"
    assert set(params["hourly"].split(",")) == set(open_meteo_provider.HOURLY_TO_PIPELINE)
    assert params["timezone"] == "UTC"


def test_fetch_open_meteo_issues_exactly_one_request(monkeypatch):
    recorder = {}
    _mock_get(monkeypatch, payload=_archive_payload(n_hours=48), recorder=recorder)

    open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-02")

    assert recorder["calls"] == 1


def test_fetch_open_meteo_accepts_iso_and_date_only_windows(monkeypatch):
    recorder = {}
    _mock_get(monkeypatch, payload=_archive_payload(n_hours=2), recorder=recorder)

    open_meteo_provider.fetch_open_meteo(
        30.2711, -97.7437, "2025-07-01T00:00:00Z", "2025-07-01"
    )

    assert recorder["params"]["start_date"] == "2025-07-01"
    assert recorder["params"]["end_date"] == "2025-07-01"


def test_module_import_has_no_side_effects():
    import importlib

    importlib.reload(open_meteo_provider)
