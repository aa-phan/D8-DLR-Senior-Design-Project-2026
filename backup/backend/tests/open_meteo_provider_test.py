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
    times = [
        ts.strftime("%Y-%m-%dT%H:%M")
        for ts in pd.date_range("2025-07-01T00:00:00", periods=n_hours, freq="h")
    ]
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
            "temperature_2m": [29.9 + (i % 10) for i in range(n_hours)],
            "wind_speed_10m": [3.4 + (i % 10) * 0.1 for i in range(n_hours)],
            "wind_direction_10m": [(160 + i) % 360 for i in range(n_hours)],
            "shortwave_radiation": [291.0 + (i % 10) for i in range(n_hours)],
            "relative_humidity_2m": [63 + (i % 10) for i in range(n_hours)],
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


# ──────────────────────────────────────────────────────────────────────────
# Task 2: fail loud on every malformed/missing/short body shape; ordering,
# adjacency, single-request, and no-substitution guarantees
# ──────────────────────────────────────────────────────────────────────────


def test_fetch_open_meteo_raises_when_hourly_is_missing(monkeypatch):
    payload = _archive_payload(n_hours=2)
    del payload["hourly"]
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError):
        open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")


def test_fetch_open_meteo_raises_when_the_time_array_is_empty(monkeypatch):
    payload = _archive_payload(n_hours=2)
    payload["hourly"]["time"] = []
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError):
        open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")


def test_fetch_open_meteo_raises_when_the_body_is_not_json(monkeypatch):
    _mock_get(monkeypatch, json_exc=ValueError("Expecting value: line 1 column 1"))

    with pytest.raises(ValueError) as excinfo:
        open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    assert "JSON" in str(excinfo.value) or "json" in str(excinfo.value)


def test_fetch_open_meteo_raises_when_a_variable_array_is_missing(monkeypatch):
    payload = _archive_payload(n_hours=2)
    del payload["hourly"]["shortwave_radiation"]
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError) as excinfo:
        open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    assert "shortwave_radiation" in str(excinfo.value)


def test_fetch_open_meteo_raises_when_a_variable_array_is_short(monkeypatch):
    payload = _archive_payload(n_hours=2)
    payload["hourly"]["wind_speed_10m"] = payload["hourly"]["wind_speed_10m"][:-1]
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError) as excinfo:
        open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    assert "wind_speed_10m" in str(excinfo.value)


def test_fetch_open_meteo_propagates_an_http_error(monkeypatch):
    class _FailingResponse:
        def raise_for_status(self):
            raise requests.HTTPError("500 Server Error")

    monkeypatch.setattr(
        open_meteo_provider.requests, "get", lambda *a, **k: _FailingResponse()
    )

    with pytest.raises(requests.HTTPError):
        open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")


def test_fetch_open_meteo_raises_when_the_echoed_wind_unit_is_wrong(monkeypatch):
    payload = _archive_payload(n_hours=2)
    payload["hourly_units"]["wind_speed_10m"] = "km/h"
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError) as excinfo:
        open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    assert "wind_speed_10m" in str(excinfo.value)
    assert "km/h" in str(excinfo.value)


def test_fetch_open_meteo_raises_when_a_value_is_out_of_schema_range(monkeypatch):
    payload = _archive_payload(n_hours=1)
    high = units_def.PIPELINE_SCHEMA["wind_speed"]["range"][1] + 10.0
    payload["hourly"]["wind_speed_10m"] = [high]
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError) as excinfo:
        open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    assert "wind_speed" in str(excinfo.value)


def test_fetch_open_meteo_returns_one_row_for_a_single_hour_window(monkeypatch):
    _mock_get(monkeypatch, payload=_archive_payload(n_hours=1))

    frame = open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    assert len(frame) == 1
    for col in (
        "air_temp",
        "wind_speed",
        "wind_direction",
        "solar_radiation",
        "relative_humidity",
    ):
        assert frame[col].notna().all()


def test_fetch_open_meteo_output_is_ordered_and_reproducible(monkeypatch):
    payload = _archive_payload(n_hours=4)
    _mock_get(monkeypatch, payload=payload)

    first = open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    _mock_get(monkeypatch, payload=_archive_payload(n_hours=4))
    second = open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    assert first["datetime_utc"].is_monotonic_increasing
    pd.testing.assert_frame_equal(first, second)


def test_fetch_open_meteo_does_not_mutate_module_state(monkeypatch):
    base_url = open_meteo_provider.OPEN_METEO_ARCHIVE_BASE
    mapping = dict(open_meteo_provider.HOURLY_TO_PIPELINE)
    hourly_vars = open_meteo_provider.OPEN_METEO_HOURLY_VARS

    payload = _archive_payload(n_hours=2)
    payload_copy = _archive_payload(n_hours=2)
    _mock_get(monkeypatch, payload=payload)
    open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    _mock_get(monkeypatch, payload=payload)
    open_meteo_provider.fetch_open_meteo(30.2711, -97.7437, "2025-07-01", "2025-07-01")

    assert open_meteo_provider.OPEN_METEO_ARCHIVE_BASE == base_url
    assert open_meteo_provider.HOURLY_TO_PIPELINE == mapping
    assert open_meteo_provider.OPEN_METEO_HOURLY_VARS == hourly_vars
    assert payload == payload_copy
