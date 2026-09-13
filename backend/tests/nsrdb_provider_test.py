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
import json

import pandas as pd
import pytest

import config
import units_def

import nsrdb_provider


def _psm4_csv(
    n_hours: int = 2,
    year: int = 2023,
    ghi: list[float] | None = None,
    start: str | None = None,
) -> str:
    """
    Shared payload builder in the documented PSM v4 CSV response shape:
    line 1 is the metadata field-name row (including Latitude, Longitude,
    and GHI Units), line 2 is the matching metadata value row, line 3 is
    the data column header ``Year,Month,Day,Hour,Minute,GHI``, and the
    remaining lines are hourly data rows.

    `start` (an ISO timestamp string) overrides the default "{year}-07-01
    00:00:00" starting point -- used by the year-boundary tests below to
    place rows on either side of a requested window's edges within the
    same calendar year.
    """
    if ghi is None:
        ghi = [200.0 + i * 10 for i in range(n_hours)]

    lines = [
        "Source,Location ID,Latitude,Longitude,Time Zone,GHI Units",
        "NSRDB,145809,30.2711,-97.7437,0,w/m2",
        "Year,Month,Day,Hour,Minute,GHI",
    ]
    start_ts = pd.Timestamp(start) if start is not None else pd.Timestamp(f"{year}-07-01T00:00:00")
    for i in range(n_hours):
        ts = start_ts + pd.Timedelta(hours=i)
        lines.append(f"{ts.year},{ts.month},{ts.day},{ts.hour},{ts.minute},{ghi[i]}")

    return "\n".join(lines) + "\n"


def _year_boundary_fixtures() -> dict[int, str]:
    """
    Two per-year PSM v4 fixtures straddling the 2023/2024 boundary, each
    carrying rows on both sides of a [2023-12-28, 2024-01-03] window so the
    year-chunking tests can prove filtering actually ran rather than
    trivially passing on an all-inside fixture.

    2023 fixture: 2023-12-27T22:00 .. 2023-12-28T03:00 (6 hourly rows) --
    2 rows before the window's start bound (2023-12-28T00:00:00Z), 4 inside.
    2024 fixture: 2024-01-03T20:00 .. 2024-01-04T01:00 (6 hourly rows) --
    4 rows inside the window's end bound (2024-01-03T23:59:59.999999Z), 2
    after it.
    """
    return {
        2023: _psm4_csv(n_hours=6, year=2023, start="2023-12-27T22:00:00"),
        2024: _psm4_csv(n_hours=6, year=2024, start="2024-01-03T20:00:00"),
    }


class _FakeResponse:
    def __init__(self, text: str = "", ok: bool = True, status_code: int = 200):
        self.text = text
        self.ok = ok
        self.status_code = status_code
        self.content = text.encode()

    def json(self):
        # json.JSONDecodeError is a ValueError subclass -- matches the
        # production error handler's `except ValueError` branch, which must
        # fall back to the raw CSV body when the response isn't JSON.
        return json.loads(self.text)


def _mock_get(
    monkeypatch,
    text: str = "",
    ok: bool = True,
    status_code: int = 200,
    recorder: dict | None = None,
    response_for_year=None,
):
    """
    `response_for_year`, when supplied, is a callable(year) -> _FakeResponse
    used by the multi-year tests to serve a different body per requested
    `names` year. `recorder`, when supplied, accumulates every call's
    params in `recorder["all_params"]` (order-preserving) in addition to
    the last-call convenience keys `recorder["calls"]`/`["params"]`/["url"]`
    already relied on by Plan 08-01's tests. `ok`/`status_code` let a test
    mock a non-2xx response for the fixed (non-year-keyed) body case.
    """

    def fake_get(url, params=None, timeout=None):
        if recorder is not None:
            all_params = recorder.setdefault("all_params", [])
            all_params.append(params)
            recorder["calls"] = len(all_params)
            recorder["params"] = params
            recorder["url"] = url
        if response_for_year is not None:
            return response_for_year(params["names"])
        return _FakeResponse(text=text, ok=ok, status_code=status_code)

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


# ──────────────────────────────────────────────────────────────────────────
# Task 2: credential fail-loud path, request contract for all four cities
# ──────────────────────────────────────────────────────────────────────────


def test_fetch_nsrdb_raises_when_api_key_is_unset(monkeypatch):
    monkeypatch.delenv("NREL_API_KEY", raising=False)
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    recorder: dict = {}
    _mock_get(monkeypatch, text=_psm4_csv(), recorder=recorder)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(EnvironmentError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert "NREL_API_KEY" in str(excinfo.value)
    assert recorder.get("calls", 0) == 0


def test_fetch_nsrdb_raises_when_contact_email_is_unset(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.delenv("NREL_API_EMAIL", raising=False)
    recorder: dict = {}
    _mock_get(monkeypatch, text=_psm4_csv(), recorder=recorder)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(EnvironmentError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert "NREL_API_EMAIL" in str(excinfo.value)
    assert recorder.get("calls", 0) == 0


def test_fetch_nsrdb_credential_errors_are_not_value_errors(monkeypatch):
    monkeypatch.delenv("NREL_API_KEY", raising=False)
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(EnvironmentError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert not isinstance(excinfo.value, ValueError)


def test_fetch_nsrdb_error_message_never_echoes_the_credential_values(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "sentinel-key-8675309")
    monkeypatch.setenv("NREL_API_EMAIL", "sentinel-email-8675309@example.com")
    _mock_get(monkeypatch, text="<html><body>Internal Server Error</body></html>")

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    message = str(excinfo.value)
    assert "sentinel-key-8675309" not in message
    assert "sentinel-email-8675309@example.com" not in message


def test_fetch_nsrdb_builds_a_distinct_longitude_first_wkt_for_all_four_cities(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")

    wkts = {}
    for city, (lat, lon) in config.CITY_COORDINATES.items():
        recorder: dict = {}
        _mock_get(monkeypatch, text=_psm4_csv(), recorder=recorder)
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")
        wkts[city] = recorder["params"]["wkt"]

    assert len(set(wkts.values())) == 4

    # The assertion that actually catches a swap: parse the two numbers
    # back out of each string (never call _wkt_point to build the
    # expectation -- a round-trip agrees with itself) and assert the first
    # is negative and the second positive. All four Texas cities have
    # negative longitude and positive latitude, so a latitude-first string
    # fails this on every city at once.
    for city, wkt in wkts.items():
        inner = wkt[len("POINT(") : -1]
        lon_str, lat_str = inner.split()
        assert float(lon_str) < 0 < float(lat_str), (city, wkt)


def test_fetch_nsrdb_sends_the_optional_request_metadata_parameters(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    recorder: dict = {}
    _mock_get(monkeypatch, text=_psm4_csv(), recorder=recorder)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    for key, value in nsrdb_provider.NSRDB_REQUEST_METADATA.items():
        assert recorder["params"][key] == value


def test_fetch_nsrdb_raises_when_the_response_is_not_a_psm4_csv(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    _mock_get(
        monkeypatch,
        text="<html><head><title>Error</title></head><body>Bad Request</body></html>",
    )

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert "<html>" in str(excinfo.value)


def test_fetch_nsrdb_raises_when_a_ghi_value_is_out_of_schema_range(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    hi = units_def.PIPELINE_SCHEMA["solar_radiation"]["range"][1]
    _mock_get(monkeypatch, text=_psm4_csv(n_hours=2, ghi=[hi + 100.0, 200.0]))

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    message = str(excinfo.value)
    assert "solar_radiation" in message
    assert str(hi) in message


# ──────────────────────────────────────────────────────────────────────────
# Plan 08-02 Task 1: year-chunking and window reconstruction
# ──────────────────────────────────────────────────────────────────────────


def test_fetch_nsrdb_issues_one_request_per_calendar_year(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    fixtures = _year_boundary_fixtures()
    recorder: dict = {}
    _mock_get(
        monkeypatch,
        recorder=recorder,
        response_for_year=lambda year: _FakeResponse(text=fixtures[year]),
    )

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    nsrdb_provider.fetch_nsrdb(lat, lon, "2023-12-28", "2024-01-03")

    assert recorder["calls"] == 2
    assert [p["names"] for p in recorder["all_params"]] == [2023, 2024]


def test_fetch_nsrdb_still_issues_one_request_for_a_single_year_window(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    recorder: dict = {}
    _mock_get(monkeypatch, text=_psm4_csv(n_hours=2, year=2023), recorder=recorder)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert recorder["calls"] == 1


def test_fetch_nsrdb_concatenates_year_chunks_into_one_ordered_frame(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    fixtures = _year_boundary_fixtures()
    _mock_get(
        monkeypatch,
        response_for_year=lambda year: _FakeResponse(text=fixtures[year]),
    )

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    frame = nsrdb_provider.fetch_nsrdb(lat, lon, "2023-12-28", "2024-01-03")

    assert (frame["datetime_utc"].dt.year == 2023).any()
    assert (frame["datetime_utc"].dt.year == 2024).any()
    assert frame["datetime_utc"].is_monotonic_increasing
    assert not frame["datetime_utc"].duplicated().any()


def test_fetch_nsrdb_filters_the_concatenated_frame_to_the_requested_window(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    fixtures = _year_boundary_fixtures()
    _mock_get(
        monkeypatch,
        response_for_year=lambda year: _FakeResponse(text=fixtures[year]),
    )

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    start = "2023-12-28"
    end = "2024-01-03"
    frame = nsrdb_provider.fetch_nsrdb(lat, lon, start, end)

    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    assert (frame["datetime_utc"] >= start_ts).all()
    assert (frame["datetime_utc"] <= end_ts).all()
    # 6 rows per fixture year, 12 total -- filtering must drop at least the
    # 2 (2023) + 2 (2024) rows _year_boundary_fixtures placed outside the
    # window, so the returned count must be strictly smaller than 12.
    assert len(frame) < 12


def test_fetch_nsrdb_treats_a_bare_date_end_as_the_whole_day(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    full_day = _psm4_csv(n_hours=24, year=2023, start="2023-07-01T00:00:00")

    _mock_get(monkeypatch, text=full_day)
    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    whole_day_frame = nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-01")
    assert len(whole_day_frame) == 24

    _mock_get(monkeypatch, text=full_day)
    midnight_frame = nsrdb_provider.fetch_nsrdb(
        lat, lon, "2023-07-01", "2023-07-01T00:00:00Z"
    )
    assert len(midnight_frame) == 1


def test_fetch_nsrdb_raises_for_a_year_before_the_products_first_covered_year(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    recorder: dict = {}
    _mock_get(monkeypatch, text=_psm4_csv(year=2015), recorder=recorder)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2015-01-01", "2015-02-01")

    message = str(excinfo.value)
    assert "2015" in message
    assert str(nsrdb_provider.NSRDB_FIRST_COVERED_YEAR) in message
    assert recorder.get("calls", 0) == 0


def test_fetch_nsrdb_does_not_locally_reject_a_future_year(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    recorder: dict = {}
    _mock_get(monkeypatch, text=_psm4_csv(n_hours=2, year=2030), recorder=recorder)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    nsrdb_provider.fetch_nsrdb(lat, lon, "2030-07-01", "2030-07-02")

    assert recorder.get("calls", 0) >= 1


def test_fetch_nsrdb_raises_when_the_window_selects_no_rows(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    # All rows fall on 2023-07-02, entirely outside the requested
    # 2023-07-01 single-day window.
    _mock_get(monkeypatch, text=_psm4_csv(n_hours=2, year=2023, start="2023-07-02T00:00:00"))

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-01")

    assert "2023-07-01" in str(excinfo.value)


# ──────────────────────────────────────────────────────────────────────────
# Plan 08-02 Task 2: dual-shape error handling, credential redaction, GHI
# units metadata check
# ──────────────────────────────────────────────────────────────────────────


def _psm4_csv_with_ghi_units(units: str, n_hours: int = 2, year: int = 2023) -> str:
    lines = [
        "Source,Location ID,Latitude,Longitude,Time Zone,GHI Units",
        f"NSRDB,145809,30.2711,-97.7437,0,{units}",
        "Year,Month,Day,Hour,Minute,GHI",
    ]
    start_ts = pd.Timestamp(f"{year}-07-01T00:00:00")
    for i in range(n_hours):
        ts = start_ts + pd.Timedelta(hours=i)
        lines.append(f"{ts.year},{ts.month},{ts.day},{ts.hour},{ts.minute},{200.0 + i}")
    return "\n".join(lines) + "\n"


def _psm4_csv_without_ghi_units(n_hours: int = 2, year: int = 2023) -> str:
    lines = [
        "Source,Location ID,Latitude,Longitude,Time Zone",
        "NSRDB,145809,30.2711,-97.7437,0",
        "Year,Month,Day,Hour,Minute,GHI",
    ]
    start_ts = pd.Timestamp(f"{year}-07-01T00:00:00")
    for i in range(n_hours):
        ts = start_ts + pd.Timedelta(hours=i)
        lines.append(f"{ts.year},{ts.month},{ts.day},{ts.hour},{ts.minute},{200.0 + i}")
    return "\n".join(lines) + "\n"


def test_fetch_nsrdb_raises_on_json_error_body(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    body = json.dumps(
        {
            "inputs": {},
            "metadata": {"version": "2.0.0"},
            "status": 400,
            "errors": [
                "The optional 'interval' parameter must be an integer in the set [5,15,30,60]"
            ],
        }
    )
    _mock_get(monkeypatch, text=body, ok=False, status_code=400)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    message = str(excinfo.value)
    assert "interval" in message
    assert "2023" in message


def test_fetch_nsrdb_raises_on_csv_error_body(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    body = (
        "Error Code,Error Message\n"
        '"API_KEY_MISSING","No api_key was supplied. Get one at '
        'https://developer.nrel.gov/signup/"\n'
    )
    _mock_get(monkeypatch, text=body, ok=False, status_code=403)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert type(excinfo.value) is ValueError
    assert "API_KEY_MISSING" in str(excinfo.value)


def test_fetch_nsrdb_error_message_redacts_the_api_key_and_email(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "sentinel-key-8675309")
    monkeypatch.setenv("NREL_API_EMAIL", "sentinel-email-8675309@example.com")
    body = json.dumps(
        {
            "inputs": {
                "api_key": "sentinel-key-8675309",
                "email": "sentinel-email-8675309@example.com",
            },
            "metadata": {"version": "2.0.0"},
            "status": 400,
            "errors": [
                "Invalid api_key sentinel-key-8675309 for contact "
                "sentinel-email-8675309@example.com"
            ],
        }
    )
    _mock_get(monkeypatch, text=body, ok=False, status_code=400)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    message = str(excinfo.value)
    assert "sentinel-key-8675309" not in message
    assert "sentinel-email-8675309@example.com" not in message
    assert "[REDACTED]" in message


def test_fetch_nsrdb_error_detection_does_not_depend_on_a_specific_wording(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    body = json.dumps({"status": 400, "errors": ["some arbitrary rejection text"]})
    _mock_get(monkeypatch, text=body, ok=False, status_code=400)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError):
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")


def test_fetch_nsrdb_raises_on_a_rate_limited_response(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    _mock_get(monkeypatch, text="", ok=False, status_code=429)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert "429" in str(excinfo.value)


def test_fetch_nsrdb_stops_at_the_first_failing_year(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    recorder: dict = {}

    def response_for_year(year):
        if year == 2023:
            return _FakeResponse(text=_psm4_csv(year=2023, start="2023-12-28T00:00:00"))
        return _FakeResponse(
            text=json.dumps({"status": 400, "errors": ["boom"]}),
            ok=False,
            status_code=400,
        )

    _mock_get(monkeypatch, recorder=recorder, response_for_year=response_for_year)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError):
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-12-28", "2024-01-03")

    assert recorder["calls"] == 2


def test_fetch_nsrdb_raises_when_the_ghi_units_metadata_is_unexpected(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    _mock_get(monkeypatch, text=_psm4_csv_with_ghi_units("kw/m2"))

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as excinfo:
        nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")

    assert "kw/m2" in str(excinfo.value)


# Read via getattr with a fallback so this module collects cleanly during
# RED (before NSRDB_ACCEPTED_GHI_UNITS exists) -- the parametrize list
# itself is not the assertion; the test body is.
_GHI_UNITS_FOR_PARAMETRIZE = sorted(
    getattr(nsrdb_provider, "NSRDB_ACCEPTED_GHI_UNITS", {"w/m2", "w/m^2", "w/m²"})
)


@pytest.mark.parametrize(
    "units_spelling",
    _GHI_UNITS_FOR_PARAMETRIZE
    + [
        _GHI_UNITS_FOR_PARAMETRIZE[0].upper(),
        " " + _GHI_UNITS_FOR_PARAMETRIZE[0] + " ",
    ],
)
def test_fetch_nsrdb_accepts_the_documented_ghi_unit_spellings(monkeypatch, units_spelling):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    _mock_get(monkeypatch, text=_psm4_csv_with_ghi_units(units_spelling))

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    frame = nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")
    assert not frame.empty


def test_fetch_nsrdb_skips_the_units_check_when_the_metadata_field_is_absent(monkeypatch):
    monkeypatch.setenv("NREL_API_KEY", "test-key")
    monkeypatch.setenv("NREL_API_EMAIL", "test@example.com")
    _mock_get(monkeypatch, text=_psm4_csv_without_ghi_units())

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    frame = nsrdb_provider.fetch_nsrdb(lat, lon, "2023-07-01", "2023-07-02")
    assert not frame.empty
