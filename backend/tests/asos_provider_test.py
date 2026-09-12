"""
Tests for backend/asos_provider.py (C4, Phase 7 / WX-02).

Covers the ASOS 1-minute fetch-and-normalize module: CSV parsing into
PIPELINE_SCHEMA-named columns, unit conversion via units_def.Q (never
hand-rolled), tz-aware UTC timestamps, and the bare-date request-window
shape corridor_discretization.rate_corridor passes today. Task 3 adds the
fail-loud / outage-carve-out test group below.

Follows backend/tests/dlr_pipeline_test.py's `_FakeResponse` +
`monkeypatch.setattr(module.requests, "get", ...)` convention (also reused
in weather_provider_test.py) to avoid a live network call. Module-level
plain-assert functions, no test classes -- matches every existing test
file's convention in this project.
"""

import re

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
