"""
Tests for backend/asos_provider.py (C4, Phase 7 / WX-02).

Covers the ASOS 1-minute fetch-and-normalize module: CSV parsing into
PIPELINE_SCHEMA-named columns, unit conversion via units_def.Q (never
hand-rolled), tz-aware UTC timestamps, and the bare-date request-window
shape city_rating.rate_city passes today. Task 3 adds the
fail-loud / outage-carve-out test group below.

Follows backend/tests/dlr_pipeline_test.py's `_FakeResponse` +
`monkeypatch.setattr(module.requests, "get", ...)` convention (also reused
in weather_provider_test.py) to avoid a live network call. Module-level
plain-assert functions, no test classes -- matches every existing test
file's convention in this project.
"""

import re

import pandas as pd
import pytest
import requests

import units_def
from units_def import Q

import asos_provider


_TWO_ROW_CSV = (
    "station,station_name,lat,lon,valid(UTC),tmpf,sknt,drct\n"
    "AUS,Austin Bergstrom Intl,30.1830,-97.6799,2024-07-01 00:00,95,7,142\n"
    "AUS,Austin Bergstrom Intl,30.1830,-97.6799,2024-07-01 00:01,95,8,142\n"
)

_ONE_ROW_CSV = (
    "station,station_name,lat,lon,valid(UTC),tmpf,sknt,drct\n"
    "AUS,Austin Bergstrom Intl,30.1830,-97.6799,2024-07-01 00:00,95,7,142\n"
)

_HEADER_ONLY_CSV = "station,station_name,lat,lon,valid(UTC),tmpf,sknt,drct\n"


class _FakeResponse:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    @property
    def text(self):
        return self._text


def _mock_get(monkeypatch, text):
    monkeypatch.setattr(asos_provider.requests, "get", lambda *a, **k: _FakeResponse(text))


# ──────────────────────────────────────────────────────────────────────────
# Task 2: happy path, unit conversion, tz-awareness, request-window shape
# ──────────────────────────────────────────────────────────────────────────


def test_fetch_asos_1min_parses_the_live_response_header_into_pipeline_columns(monkeypatch):
    _mock_get(monkeypatch, _TWO_ROW_CSV)

    frame = asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")

    assert list(frame.columns) == ["datetime_utc", "air_temp", "wind_speed", "wind_direction"]
    assert len(frame) == 2


def test_fetch_asos_1min_converts_temperature_to_degc(monkeypatch):
    _mock_get(monkeypatch, _ONE_ROW_CSV)

    frame = asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")

    expected = Q(95, "degF").to("degC").value
    assert abs(frame["air_temp"].iloc[0] - expected) < 1e-6


def test_fetch_asos_1min_converts_wind_speed_to_metres_per_second(monkeypatch):
    _mock_get(monkeypatch, _ONE_ROW_CSV)

    frame = asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")

    expected = Q(7, "knots").to("m/s").value
    assert abs(frame["wind_speed"].iloc[0] - expected) < 1e-6


def test_fetch_asos_1min_leaves_wind_direction_in_degrees(monkeypatch):
    _mock_get(monkeypatch, _ONE_ROW_CSV)

    frame = asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")

    assert frame["wind_direction"].iloc[0] == 142.0


def test_fetch_asos_1min_timestamps_are_tz_aware_utc(monkeypatch):
    _mock_get(monkeypatch, _ONE_ROW_CSV)

    frame = asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")

    assert frame["datetime_utc"].dt.tz is not None
    assert str(frame["datetime_utc"].dt.tz) == "UTC"


def test_fetch_asos_1min_accepts_a_date_only_window(monkeypatch):
    recorded = {}

    def fake_get(url, params=None, timeout=None):
        recorded["params"] = params
        return _FakeResponse(_ONE_ROW_CSV)

    monkeypatch.setattr(asos_provider.requests, "get", fake_get)

    asos_provider.fetch_asos_1min("AUS", "2025-01-01", "2025-01-02")

    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")
    assert pattern.match(recorded["params"]["sts"])
    assert pattern.match(recorded["params"]["ets"])


def test_module_import_has_no_side_effects(monkeypatch):
    """
    Guards the module docstring's no-side-effects-on-import contract:
    importing asos_provider must not require any environment variable or
    perform any network call (mirrors
    weather_provider_test.py::test_module_import_has_no_side_effects).
    """
    import importlib

    importlib.reload(asos_provider)


# ──────────────────────────────────────────────────────────────────────────
# Task 3: fail loud on bad responses, stay silent-free on real outages,
# protect the primary
# ──────────────────────────────────────────────────────────────────────────


def test_fetch_asos_1min_raises_on_an_unknown_station_body(monkeypatch):
    _mock_get(monkeypatch, "ERROR: Unknown station provided: KAUS\n")

    with pytest.raises(ValueError) as excinfo:
        asos_provider.fetch_asos_1min("KAUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")

    assert "KAUS" in str(excinfo.value)


def test_fetch_asos_1min_raises_on_an_unrecognised_response_header(monkeypatch):
    _mock_get(monkeypatch, "<html><body>Service Unavailable</body></html>\n")

    with pytest.raises(ValueError):
        asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")


def test_fetch_asos_1min_propagates_an_http_error(monkeypatch):
    class _FailingResponse:
        def raise_for_status(self):
            raise requests.HTTPError("500 Server Error")

    monkeypatch.setattr(asos_provider.requests, "get", lambda *a, **k: _FailingResponse())

    with pytest.raises(requests.HTTPError):
        asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")


def test_fetch_asos_1min_returns_an_empty_frame_for_a_header_only_response(monkeypatch):
    _mock_get(monkeypatch, _HEADER_ONLY_CSV)

    frame = asos_provider.fetch_asos_1min("ELP", "2023-07-01T00:00Z", "2023-07-01T00:15Z")

    assert frame.empty
    assert list(frame.columns) == ["datetime_utc", "air_temp", "wind_speed", "wind_direction"]


def test_fetch_asos_1min_raises_when_a_converted_value_is_out_of_schema_range(monkeypatch):
    out_of_range_degc = units_def.PIPELINE_SCHEMA["air_temp"]["range"][1] + 10.0
    out_of_range_degf = Q(out_of_range_degc, "degC").to("degF").value

    csv_text = (
        "station,station_name,lat,lon,valid(UTC),tmpf,sknt,drct\n"
        f"AUS,Austin Bergstrom Intl,30.1830,-97.6799,2024-07-01 00:00,{out_of_range_degf},7,142\n"
    )
    _mock_get(monkeypatch, csv_text)

    with pytest.raises(ValueError):
        asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")


def test_fetch_asos_1min_issues_exactly_one_request(monkeypatch):
    calls = {"count": 0}

    def fake_get(*a, **k):
        calls["count"] += 1
        return _FakeResponse(_ONE_ROW_CSV)

    monkeypatch.setattr(asos_provider.requests, "get", fake_get)

    asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")

    assert calls["count"] == 1


def test_fetch_asos_1min_does_not_mutate_module_state(monkeypatch):
    base_url = asos_provider.ASOS_BASE
    base_vars = asos_provider.ASOS_VARS

    _mock_get(monkeypatch, _ONE_ROW_CSV)
    first = asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")

    _mock_get(monkeypatch, _ONE_ROW_CSV)
    second = asos_provider.fetch_asos_1min("AUS", "2024-07-01T00:00Z", "2024-07-01T00:05Z")

    pd.testing.assert_frame_equal(first, second)
    assert asos_provider.ASOS_BASE == base_url
    assert asos_provider.ASOS_VARS == base_vars
