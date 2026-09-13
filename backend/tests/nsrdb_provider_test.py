"""
Tests for backend/nsrdb_provider.py (C4, Phase 8 / WX-03).

Covers the NSRDB PSM v4 (GOES CONUS) fetch-and-normalize module: the
longitude-first WKT coordinate order (the one defect in this phase that
produces confidently wrong data with no exception anywhere in the stack),
the GHI-only/60-minute/UTC request contract, tz-aware UTC timestamps built
from separate Year/Month/Day/Hour/Minute columns, and the credential
fail-loud path. Task 2 adds the malformed-response and out-of-range guards.

Follows backend/tests/open_meteo_provider_test.py's `_FakeResponse` +
`monkeypatch.setattr(module.requests, "get", ...)` convention, adapted from
a `json()`-bearing response to one exposing `ok`, `status_code`, `text` and
`content`, since NSRDB's success body is CSV rather than JSON. Module-level
plain-assert functions, no test classes -- matches every existing test
file's convention in this project.
"""

import importlib

import pandas as pd
import pytest

import config
import units_def

import nsrdb_provider


def _psm4_csv(n_hours: int = 2, year: int = 2023, ghi: list[float] | None = None) -> str:
    """
    Shared payload builder in the documented PSM v4 CSV response shape:
    line 1 is the metadata field-name row (including Latitude, Longitude,
    and GHI Units), line 2 is the matching metadata value row, line 3 is
    the data column header ``Year,Month,Day,Hour,Minute,GHI``, and the
    remaining lines are hourly data rows.
    """
    if ghi is None:
        ghi = [200.0 + i * 10 for i in range(n_hours)]

    lines = [
        "Source,Location ID,Latitude,Longitude,Time Zone,GHI Units",
        "NSRDB,145809,30.2711,-97.7437,0,w/m2",
        "Year,Month,Day,Hour,Minute,GHI",
    ]
    start = pd.Timestamp(f"{year}-07-01T00:00:00")
    for i in range(n_hours):
        ts = start + pd.Timedelta(hours=i)
        lines.append(f"{ts.year},{ts.month},{ts.day},{ts.hour},{ts.minute},{ghi[i]}")

    return "\n".join(lines) + "\n"


class _FakeResponse:
    def __init__(self, text: str = "", ok: bool = True, status_code: int = 200):
        self.text = text
        self.ok = ok
        self.status_code = status_code
        self.content = text.encode()


def _mock_get(monkeypatch, text: str = "", recorder: dict | None = None):
    def fake_get(url, params=None, timeout=None):
        if recorder is not None:
            recorder["calls"] = recorder.get("calls", 0) + 1
            recorder["params"] = params
            recorder["url"] = url
        return _FakeResponse(text=text)

    monkeypatch.setattr(nsrdb_provider.requests, "get", fake_get)


# ──────────────────────────────────────────────────────────────────────────
# Task 1: happy path, WKT order, request contract, tz-awareness,
# single-request guarantee, no-side-effects-on-import
# ──────────────────────────────────────────────────────────────────────────


def test_fetch_nsrdb_returns_solar_radiation_for_a_known_city(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    ghi = [200.0, 210.0]
    _mock_get(monkeypatch, text=_psm4_csv(n_hours=2, ghi=ghi))

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    frame = nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert list(frame.columns) == ["datetime_utc", "solar_radiation"]
    assert list(frame["solar_radiation"]) == ghi


def test_fetch_nsrdb_returns_no_wind_temperature_or_humidity_columns(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    _mock_get(monkeypatch, text=_psm4_csv())

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    frame = nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-01")

    for column in ("wind_speed", "wind_direction", "air_temp", "relative_humidity"):
        assert column not in frame.columns


def test_fetch_nsrdb_timestamps_are_tz_aware_utc(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    _mock_get(monkeypatch, text=_psm4_csv(n_hours=3))

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    frame = nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert len(frame) == 3
    assert frame["datetime_utc"].dt.tz is not None
    assert str(frame["datetime_utc"].dt.tz) == "UTC"
    assert frame["datetime_utc"].is_monotonic_increasing


def test_fetch_nsrdb_wkt_is_longitude_first(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    recorder: dict = {}
    _mock_get(monkeypatch, text=_psm4_csv(), recorder=recorder)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-01")

    # Assert the literal string, not a round-trip through _wkt_point -- a
    # round-trip through the same swapped helper agrees with itself.
    assert recorder["params"]["wkt"] == "POINT(-97.7437 30.2711)"


def test_fetch_nsrdb_requests_only_ghi_at_sixty_minute_interval(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    recorder: dict = {}
    _mock_get(monkeypatch, text=_psm4_csv(), recorder=recorder)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-01")

    params = recorder["params"]
    assert params["attributes"] == "ghi"
    assert params["interval"] == 60
    assert params["utc"] == "true"
    assert params["names"] == 2023


def test_fetch_nsrdb_issues_exactly_one_request_for_a_single_year_window(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    recorder: dict = {}
    _mock_get(monkeypatch, text=_psm4_csv(n_hours=24), recorder=recorder)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert recorder["calls"] == 1


def test_module_import_has_no_side_effects(monkeypatch):
    monkeypatch.delenv("NREL_API_KEY", raising=False)
    monkeypatch.delenv("NREL_API_EMAIL", raising=False)

    importlib.reload(nsrdb_provider)
