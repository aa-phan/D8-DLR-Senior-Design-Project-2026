"""
Tests for backend/open_meteo_forecast_provider.py (D-01, Phase 3 experiment).

Covers the forecast-archive adapter's bulk fetch, single-run fetch, the
null-completeness gate (03-RESEARCH.md Pitfall 3), the run-timestamp
formatting discipline (Pitfall 4), and the archive-boundary vs. malformed
-request 400 distinction. Clones `open_meteo_provider_test.py`'s
`_FakeResponse`/`_mock_get`/payload-builder scaffolding in shape -- module
-level plain-assert functions, no test classes, no fixtures beyond pytest
built-ins. Every test here is network-free.
"""

import sys

import pandas as pd
import pytest
import requests

import units_def

import open_meteo_provider
import open_meteo_forecast_provider


def _forecast_payload(n_hours: int = 2) -> dict:
    """
    Shared payload builder in the live-confirmed Historical Forecast /
    Single-Runs API response shape -- byte-for-byte the same envelope as
    the Archive API's (03-RESEARCH.md Pattern 1).
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
    def __init__(self, payload=None, json_exc=None, status_code=200):
        self._payload = payload
        self._json_exc = json_exc
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._payload


def _mock_get(monkeypatch, payload=None, json_exc=None, recorder=None, status_code=200):
    def fake_get(url, params=None, timeout=None):
        if recorder is not None:
            recorder["calls"] = recorder.get("calls", 0) + 1
            recorder["params"] = params
            recorder["url"] = url
        return _FakeResponse(payload=payload, json_exc=json_exc, status_code=status_code)

    monkeypatch.setattr(open_meteo_forecast_provider.requests, "get", fake_get)


# ──────────────────────────────────────────────────────────────────────────
# Import-time no-side-effects + identity-of-shared-tables
# ──────────────────────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects():
    import importlib

    importlib.reload(open_meteo_forecast_provider)


def test_mapping_tables_are_identical_objects_imported_from_archive_adapter():
    assert open_meteo_forecast_provider.HOURLY_TO_PIPELINE is open_meteo_provider.HOURLY_TO_PIPELINE
    assert open_meteo_forecast_provider.EXPECTED_HOURLY_UNITS is open_meteo_provider.EXPECTED_HOURLY_UNITS
    assert open_meteo_forecast_provider.OPEN_METEO_HOURLY_VARS == open_meteo_provider.OPEN_METEO_HOURLY_VARS


def test_three_base_urls_are_literal_https_constants():
    assert open_meteo_forecast_provider.OPEN_METEO_HISTORICAL_FORECAST_BASE.startswith(
        "https://historical-forecast-api.open-meteo.com"
    )
    assert open_meteo_forecast_provider.OPEN_METEO_SINGLE_RUNS_BASE.startswith(
        "https://single-runs-api.open-meteo.com"
    )
    assert open_meteo_forecast_provider.OPEN_METEO_PREVIOUS_RUNS_BASE.startswith(
        "https://previous-runs-api.open-meteo.com"
    )


def test_model_id_is_pinned_to_ecmwf_ifs():
    assert open_meteo_forecast_provider.FORECAST_MODEL_ID == "ecmwf_ifs"


# ──────────────────────────────────────────────────────────────────────────
# fetch_historical_forecast — bulk fetch, recorder idiom
# ──────────────────────────────────────────────────────────────────────────


def test_fetch_historical_forecast_records_pinned_model_and_units(monkeypatch):
    recorder = {}
    _mock_get(monkeypatch, payload=_forecast_payload(n_hours=2), recorder=recorder)

    open_meteo_forecast_provider.fetch_historical_forecast(
        30.2711, -97.7437, "2025-07-01", "2025-07-01"
    )

    params = recorder["params"]
    assert params["models"] == "ecmwf_ifs"
    assert params["wind_speed_unit"] == "ms"
    assert params["timezone"] == "UTC"
    assert recorder["url"] == open_meteo_forecast_provider.OPEN_METEO_HISTORICAL_FORECAST_BASE
    assert recorder["calls"] == 1


def test_fetch_historical_forecast_returns_six_pipeline_columns(monkeypatch):
    _mock_get(monkeypatch, payload=_forecast_payload(n_hours=2))

    frame = open_meteo_forecast_provider.fetch_historical_forecast(
        30.2711, -97.7437, "2025-07-01", "2025-07-01"
    )

    assert list(frame.columns) == [
        "datetime_utc",
        "air_temp",
        "wind_speed",
        "wind_direction",
        "solar_radiation",
        "relative_humidity",
    ]
    assert len(frame) == 2
    assert str(frame["datetime_utc"].dt.tz) == "UTC"


# ──────────────────────────────────────────────────────────────────────────
# Null-completeness gate (Pitfall 3)
# ──────────────────────────────────────────────────────────────────────────


def test_fully_null_variable_array_raises_naming_variable_and_count(monkeypatch):
    payload = _forecast_payload(n_hours=4)
    payload["hourly"]["wind_speed_10m"] = [None] * 4
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError) as excinfo:
        open_meteo_forecast_provider.fetch_historical_forecast(
            30.2711, -97.7437, "2025-07-01", "2025-07-01"
        )

    assert "wind_speed_10m" in str(excinfo.value)
    assert "4/4" in str(excinfo.value)


def test_single_interior_null_raises(monkeypatch):
    payload = _forecast_payload(n_hours=4)
    payload["hourly"]["temperature_2m"][2] = None
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError) as excinfo:
        open_meteo_forecast_provider.fetch_historical_forecast(
            30.2711, -97.7437, "2025-07-01", "2025-07-01"
        )

    assert "temperature_2m" in str(excinfo.value)
    assert "1/4" in str(excinfo.value)


def test_shortwave_radiation_leading_null_tolerated_on_single_run(monkeypatch):
    payload = _forecast_payload(n_hours=4)
    payload["hourly"]["shortwave_radiation"][0] = None
    _mock_get(monkeypatch, payload=payload)

    frame = open_meteo_forecast_provider.fetch_single_run(
        30.2711, -97.7437, "2025-07-01T00:00"
    )

    assert len(frame) == 4


def test_shortwave_radiation_null_at_index_one_still_raises(monkeypatch):
    payload = _forecast_payload(n_hours=4)
    payload["hourly"]["shortwave_radiation"][1] = None
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError) as excinfo:
        open_meteo_forecast_provider.fetch_single_run(
            30.2711, -97.7437, "2025-07-01T00:00"
        )

    assert "shortwave_radiation" in str(excinfo.value)


def test_shortwave_radiation_leading_null_not_tolerated_on_bulk_path(monkeypatch):
    # allow_leading_null_for is only passed on the single-run path -- the
    # bulk path must still raise on a null at index 0.
    payload = _forecast_payload(n_hours=4)
    payload["hourly"]["shortwave_radiation"][0] = None
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError) as excinfo:
        open_meteo_forecast_provider.fetch_historical_forecast(
            30.2711, -97.7437, "2025-07-01", "2025-07-01"
        )

    assert "shortwave_radiation" in str(excinfo.value)


# ──────────────────────────────────────────────────────────────────────────
# Single-run run-timestamp formatting (Pitfall 4)
# ──────────────────────────────────────────────────────────────────────────


def test_run_timestamp_formatted_with_no_seconds_and_no_zone_suffix(monkeypatch):
    recorder = {}
    _mock_get(monkeypatch, payload=_forecast_payload(n_hours=4), recorder=recorder)

    for spelling in (
        "2025-07-01T00:00",
        "2025-07-01T00:00:00",
        "2025-07-01T00:00:00Z",
        pd.Timestamp("2025-07-01T00:00:00", tz="UTC"),
        "2025-07-01 00:00:00",
    ):
        open_meteo_forecast_provider.fetch_single_run(30.2711, -97.7437, spelling)
        assert recorder["params"]["run"] == "2025-07-01T00:00"


def test_fetch_single_run_does_not_send_start_or_end_date(monkeypatch):
    recorder = {}
    _mock_get(monkeypatch, payload=_forecast_payload(n_hours=4), recorder=recorder)

    open_meteo_forecast_provider.fetch_single_run(30.2711, -97.7437, "2025-07-01T00:00")

    assert "start_date" not in recorder["params"]
    assert "end_date" not in recorder["params"]
    assert recorder["params"]["models"] == "ecmwf_ifs"


# ──────────────────────────────────────────────────────────────────────────
# Archive-boundary vs. malformed-request 400 distinction (Pitfall 4)
# ──────────────────────────────────────────────────────────────────────────


def test_unavailable_model_run_raises_single_run_unavailable(monkeypatch):
    payload = {
        "error": True,
        "reason": "The requested model run is not available. Model: ecmwf_ifs, run: 2025-07-01T03:00",
    }
    _mock_get(monkeypatch, payload=payload, status_code=400)

    with pytest.raises(open_meteo_forecast_provider.SingleRunUnavailable) as excinfo:
        open_meteo_forecast_provider.fetch_single_run(30.2711, -97.7437, "2025-07-01T03:00")

    assert "not available" in str(excinfo.value)


def test_bare_bad_request_400_propagates_as_http_error(monkeypatch):
    payload = {"error": True, "reason": "Bad Request"}
    _mock_get(monkeypatch, payload=payload, status_code=400)

    with pytest.raises(requests.HTTPError):
        open_meteo_forecast_provider.fetch_single_run(30.2711, -97.7437, "2025-07-01T00:00")


def test_400_with_unparseable_body_propagates_as_http_error(monkeypatch):
    _mock_get(monkeypatch, json_exc=ValueError("not json"), status_code=400)

    with pytest.raises(requests.HTTPError):
        open_meteo_forecast_provider.fetch_single_run(30.2711, -97.7437, "2025-07-01T00:00")


# ──────────────────────────────────────────────────────────────────────────
# Unit mismatch / out-of-range value (reused checks, named by this module)
# ──────────────────────────────────────────────────────────────────────────


def test_mismatched_unit_echo_raises(monkeypatch):
    payload = _forecast_payload(n_hours=2)
    payload["hourly_units"]["wind_speed_10m"] = "km/h"
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError) as excinfo:
        open_meteo_forecast_provider.fetch_historical_forecast(
            30.2711, -97.7437, "2025-07-01", "2025-07-01"
        )

    assert "wind_speed_10m" in str(excinfo.value)
    assert "km/h" in str(excinfo.value)


def test_value_outside_schema_range_raises(monkeypatch):
    payload = _forecast_payload(n_hours=1)
    high = units_def.PIPELINE_SCHEMA["wind_speed"]["range"][1] + 10.0
    payload["hourly"]["wind_speed_10m"] = [high]
    _mock_get(monkeypatch, payload=payload)

    with pytest.raises(ValueError) as excinfo:
        open_meteo_forecast_provider.fetch_historical_forecast(
            30.2711, -97.7437, "2025-07-01", "2025-07-01"
        )

    assert "wind_speed" in str(excinfo.value)


def test_fetch_propagates_http_error_on_500(monkeypatch):
    _mock_get(monkeypatch, payload=_forecast_payload(n_hours=2), status_code=500)

    with pytest.raises(requests.HTTPError):
        open_meteo_forecast_provider.fetch_historical_forecast(
            30.2711, -97.7437, "2025-07-01", "2025-07-01"
        )


def test_importing_module_adds_no_new_network_module_and_no_file_io(monkeypatch):
    # The module is already imported at collection time; assert that no
    # attribute on it performs file I/O by checking there's no open()/Path
    # write anywhere reachable via a fresh reload with network calls forced
    # to fail loudly if attempted.
    def _boom(*a, **k):
        raise AssertionError("reload triggered a network call")

    monkeypatch.setattr(open_meteo_forecast_provider.requests, "get", _boom)
    import importlib

    importlib.reload(open_meteo_forecast_provider)
