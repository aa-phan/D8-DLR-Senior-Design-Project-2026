"""
Tests for backend/weather_provider.py's provenance layer (C4 / Plan 06-01)
and dispatch/city-resolution layer (C4 / Plan 06-02).

Proves the thin vertical slice end to end: schema layer (units_def.py v3)
-> validator layer (validate_pipeline_row's categorical branch) -> adapter
layer (weather_provider.attach_provenance) -> caller-visible output
(fetch_weather's station path). Follows
backend/tests/corridor_discretization_test.py's convention (module-level
imports, plain asserts, no test classes) and
backend/tests/dlr_pipeline_test.py's `monkeypatch.setattr(dlr_pipeline,
"fetch_timeseries", ...)` convention for avoiding a live network call.
"""

import inspect

import pandas as pd
import pytest

import config
import dlr_pipeline
import units_def
import weather_provider


def _synthetic_frame(**columns) -> pd.DataFrame:
    """
    Builds a synthetic observation frame in the shape
    dlr_pipeline.fetch_timeseries() returns: indexed by (stid,
    datetime_utc), with whichever weather columns the caller supplies.
    """
    times = pd.date_range("2025-07-01T00:00:00Z", periods=2, freq="5min")
    df = pd.DataFrame({"stid": ["KAUS"] * 2, "datetime_utc": times, **columns})
    return df.set_index(["stid", "datetime_utc"]).sort_index()


def test_station_fetch_end_to_end_row_carries_provenance_and_validates(monkeypatch):
    frame = _synthetic_frame(
        air_temp=[25.0, 26.0],
        wind_speed=[5.0, 5.5],
        wind_direction=[180.0, 190.0],
        relative_humidity=[40.0, 41.0],
        solar_radiation=[500.0, 510.0],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: frame)

    result = weather_provider.fetch_weather(
        ["KAUS"], "2025-07-01T00:00:00Z", "2025-07-01T01:00:00Z"
    )

    for col in ("wind_source", "temp_source", "humidity_source", "solar_source"):
        assert (result[col] == "synoptic").all()

    row = result.iloc[0].to_dict()
    assert units_def.validate_pipeline_row(row, strict=False) == []


def test_provenance_is_none_where_the_underlying_field_is_absent(monkeypatch):
    frame = _synthetic_frame(
        air_temp=[25.0, 26.0],
        wind_speed=[5.0, 5.5],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: frame)

    result = weather_provider.fetch_weather(
        ["KAUS"], "2025-07-01T00:00:00Z", "2025-07-01T01:00:00Z"
    )

    assert (result["temp_source"] == "synoptic").all()
    assert (result["wind_source"] == "synoptic").all()
    assert result["humidity_source"].isna().all()
    assert result["solar_source"].isna().all()


def test_provenance_is_none_where_the_underlying_value_is_null(monkeypatch):
    frame = _synthetic_frame(
        air_temp=[25.0, 26.0],
        solar_radiation=[None, 510.0],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: frame)

    result = weather_provider.fetch_weather(
        ["KAUS"], "2025-07-01T00:00:00Z", "2025-07-01T01:00:00Z"
    )

    assert result["solar_source"].iloc[0] is None or pd.isna(result["solar_source"].iloc[0])
    assert result["solar_source"].iloc[1] == "synoptic"


def test_attach_provenance_does_not_mutate_its_argument():
    frame = _synthetic_frame(air_temp=[25.0, 26.0], wind_speed=[5.0, 5.5])
    original_columns = list(frame.columns)

    result = weather_provider.attach_provenance(frame, "synoptic")

    assert list(frame.columns) == original_columns
    assert result is not frame
    for col in ("wind_source", "temp_source", "humidity_source", "solar_source"):
        assert col not in frame.columns


def test_attach_provenance_rejects_an_unregistered_provider_name():
    frame = _synthetic_frame(air_temp=[25.0, 26.0])

    with pytest.raises(ValueError) as excinfo:
        weather_provider.attach_provenance(frame, "notaprovider")

    assert "notaprovider" in str(excinfo.value)


def test_module_import_has_no_side_effects(monkeypatch):
    """
    Guards the module docstring's no-side-effects-on-import contract:
    importing weather_provider must not require SYNOPTIC_TOKEN. Re-verify
    explicitly with the token unset (mirrors
    corridor_discretization_test.py::test_module_importable_with_no_synoptic_token_and_no_network).
    """
    monkeypatch.delenv("SYNOPTIC_TOKEN", raising=False)
    import importlib

    importlib.reload(weather_provider)


# ──────────────────────────────────────────────────────────────────────────
# Task 1 (Plan 06-02): type-dispatched `location` parameter
# ──────────────────────────────────────────────────────────────────────────

_START = "2025-07-01T00:00:00Z"
_END = "2025-07-01T01:00:00Z"


def test_dispatch_station_list_routes_to_the_station_path(monkeypatch):
    recorded = {}

    def fake_fetch_timeseries(stids, start, end):
        recorded["stids"] = stids
        recorded["start"] = start
        recorded["end"] = end
        return pd.DataFrame()

    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", fake_fetch_timeseries)

    weather_provider.fetch_weather(["KAUS"], _START, _END)

    assert recorded["stids"] == ["KAUS"]


def test_dispatch_latlon_tuple_routes_to_the_grid_path(monkeypatch):
    called = {"count": 0}

    def fake_fetch_timeseries(*a, **k):
        called["count"] += 1
        return pd.DataFrame()

    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", fake_fetch_timeseries)

    with pytest.raises(ValueError) as excinfo:
        weather_provider.fetch_weather((30.2711, -97.7437), _START, _END)

    assert "grid" in str(excinfo.value)
    assert called["count"] == 0


def test_dispatch_rejects_a_two_element_list_of_numbers():
    with pytest.raises(ValueError):
        weather_provider.fetch_weather([30.27, -97.74], _START, _END)


def test_dispatch_rejects_a_two_element_tuple_of_strings():
    with pytest.raises(ValueError):
        weather_provider.fetch_weather(("KAUS", "KDFW"), _START, _END)


def test_dispatch_rejects_empty_location():
    with pytest.raises(ValueError):
        weather_provider.fetch_weather([], _START, _END)
    with pytest.raises(ValueError):
        weather_provider.fetch_weather((), _START, _END)


def test_dispatch_rejects_a_three_element_tuple():
    with pytest.raises(ValueError):
        weather_provider.fetch_weather((1.0, 2.0, 3.0), _START, _END)


def test_dispatch_existing_positional_call_shape_still_works():
    params = list(inspect.signature(weather_provider.fetch_weather).parameters)
    assert params[:4] == ["location", "start", "end", "provider"]


# ──────────────────────────────────────────────────────────────────────────
# Task 2 (Plan 06-02): internal station -> city resolution
# ──────────────────────────────────────────────────────────────────────────


def test_city_resolution_returns_a_literal_config_key():
    city = weather_provider.resolve_station_city(30.2711, -97.7437)
    assert city == "AUSTIN"
    assert city in config.CITY_COORDINATES


def test_city_resolution_covers_all_four_cities():
    for city, (lat, lon) in config.CITY_COORDINATES.items():
        assert weather_provider.resolve_station_city(lat, lon) == city


def test_city_resolution_returns_none_for_missing_coordinates():
    assert weather_provider.resolve_station_city(None, -97.74) is None
    assert weather_provider.resolve_station_city(30.27, None) is None
    assert weather_provider.resolve_station_city(float("nan"), -97.74) is None
    assert weather_provider.resolve_station_city("x", "y") is None


def test_city_resolution_never_defaults_to_a_city():
    for lat, lon in (
        (None, -97.74),
        (30.27, None),
        (float("nan"), -97.74),
        ("x", "y"),
    ):
        result = weather_provider.resolve_station_city(lat, lon)
        assert result not in config.CITY_COORDINATES


def test_city_resolution_is_deterministic_for_an_equidistant_point():
    austin_lat, austin_lon = config.CITY_COORDINATES["AUSTIN"]
    cc_lat, cc_lon = config.CITY_COORDINATES["CORPUS_CHRISTI"]
    mid_lat = (austin_lat + cc_lat) / 2
    mid_lon = (austin_lon + cc_lon) / 2

    first = weather_provider.resolve_station_city(mid_lat, mid_lon)
    second = weather_provider.resolve_station_city(mid_lat, mid_lon)

    assert first == second


def _synthetic_synoptic_payload(include_coords: bool) -> dict:
    station = {
        "STID": "KAUS",
        "OBSERVATIONS": {
            "date_time": ["2025-07-01T00:00:00Z", "2025-07-01T00:05:00Z"],
            "air_temp_set_1": [25.0, 26.0],
        },
    }
    if include_coords:
        station["LATITUDE"] = "30.2711"
        station["LONGITUDE"] = "-97.7437"
    return {"SUMMARY": {"RESPONSE_CODE": "1"}, "STATION": [station]}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_timeseries_frame_carries_lat_and_lon(monkeypatch):
    monkeypatch.setattr(dlr_pipeline, "_token", lambda: "fake-token")
    monkeypatch.setattr(
        dlr_pipeline.requests,
        "get",
        lambda *a, **k: _FakeResponse(_synthetic_synoptic_payload(include_coords=True)),
    )

    frame = dlr_pipeline.fetch_timeseries(["KAUS"], _START, _END)

    assert list(frame.index.names) == ["stid", "datetime_utc"]
    assert "lat" in frame.columns
    assert "lon" in frame.columns
    assert (frame["lat"] == 30.2711).all()
    assert (frame["lon"] == -97.7437).all()


def test_fetch_timeseries_tolerates_a_station_object_without_coordinates(monkeypatch):
    monkeypatch.setattr(dlr_pipeline, "_token", lambda: "fake-token")
    monkeypatch.setattr(
        dlr_pipeline.requests,
        "get",
        lambda *a, **k: _FakeResponse(_synthetic_synoptic_payload(include_coords=False)),
    )

    frame = dlr_pipeline.fetch_timeseries(["KAUS"], _START, _END)

    assert frame["lat"].isna().all()
    assert frame["lon"].isna().all()
