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
from pathlib import Path

import pandas as pd
import pytest

import asos_provider
import config
import corridor_discretization
import dlr_pipeline
import nsrdb_provider
import open_meteo_provider
import tceq_provider
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


# ──────────────────────────────────────────────────────────────────────────
# Task 1 (Plan 06-03): city-keyed merge of a station frame and a grid frame
# ──────────────────────────────────────────────────────────────────────────


def _station_frame(city: str = "AUSTIN", n: int = 2, **columns) -> pd.DataFrame:
    """
    Builds a station-shaped frame the way Plan 06-03's merge actually
    receives one: fetch_weather's station-path shape (indexed by (stid,
    datetime_utc)) plus a `city` column (as attach_city would add) and
    provenance columns (as attach_provenance already tags), for whichever
    weather columns the caller supplies.
    """
    times = pd.date_range("2025-07-01T00:00:00Z", periods=n, freq="5min")
    df = pd.DataFrame(
        {
            "stid": ["KAUS"] * n,
            "datetime_utc": times,
            "city": [city] * n,
            **columns,
        }
    )
    df = weather_provider.attach_provenance(df, "synoptic")
    return df.set_index(["stid", "datetime_utc"]).sort_index()


def _grid_frame(city: str = "AUSTIN", n: int = 2, **columns) -> pd.DataFrame:
    """
    Builds a grid-shaped frame the way a real grid provider's output would
    look once tagged: no station index, just `datetime_utc` and `city`
    columns plus whichever weather columns the caller supplies.
    """
    times = pd.date_range("2025-07-01T00:00:00Z", periods=n, freq="5min")
    df = pd.DataFrame(
        {
            "datetime_utc": times,
            "city": [city] * n,
            **columns,
        }
    )
    return weather_provider.attach_provenance(df, "open_meteo")


def test_merge_combines_station_and_grid_into_one_row_per_timestamp():
    station = _station_frame(
        air_temp=[25.0, 26.0],
        wind_speed=[5.0, 5.5],
        wind_direction=[180.0, 190.0],
        relative_humidity=[40.0, 41.0],
    )
    grid = _grid_frame(solar_radiation=[500.0, 510.0])

    merged = weather_provider.merge_observations(station, grid)

    assert len(merged) == 2
    for col in (
        "air_temp",
        "wind_speed",
        "wind_direction",
        "relative_humidity",
        "solar_radiation",
    ):
        assert merged[col].notna().all()


def test_merge_provenance_names_the_actual_supplier_per_field():
    station = _station_frame(
        air_temp=[25.0, 26.0],
        wind_speed=[5.0, 5.5],
        wind_direction=[180.0, 190.0],
        relative_humidity=[40.0, 41.0],
    )
    grid = _grid_frame(solar_radiation=[500.0, 510.0])

    merged = weather_provider.merge_observations(station, grid)

    assert (merged["wind_source"] == "synoptic").all()
    assert (merged["temp_source"] == "synoptic").all()
    assert (merged["humidity_source"] == "synoptic").all()
    assert (merged["solar_source"] == "open_meteo").all()


def test_merge_station_value_wins_when_both_sides_supply_a_field():
    station = _station_frame(air_temp=[25.0, 26.0])
    grid = _grid_frame(air_temp=[99.0, 98.0], solar_radiation=[500.0, 510.0])

    merged = weather_provider.merge_observations(station, grid)

    assert list(merged["air_temp"]) == [25.0, 26.0]
    assert (merged["temp_source"] == "synoptic").all()


def test_merge_leaves_a_field_neither_side_supplied_null_with_null_provenance():
    # relative_humidity is included as an explicit null column on the
    # station side -- matching the real shape dlr_pipeline.fetch_timeseries
    # always returns (DLR_VARS columns exist even when a sensor is dead) --
    # so the merge's job is proven to be "leave it null", not "the column
    # never existed."
    station = _station_frame(
        air_temp=[25.0, 26.0], relative_humidity=[None, None]
    )
    grid = _grid_frame(solar_radiation=[500.0, 510.0])

    merged = weather_provider.merge_observations(station, grid)

    assert merged["relative_humidity"].isna().all()
    assert merged["humidity_source"].isna().all()


def test_merge_with_an_empty_station_frame_returns_the_grid_rows():
    grid = _grid_frame(solar_radiation=[500.0, 510.0])

    merged = weather_provider.merge_observations(pd.DataFrame(), grid)

    assert len(merged) == len(grid)
    assert list(merged["solar_radiation"]) == [500.0, 510.0]


def test_merge_with_an_empty_grid_frame_returns_the_station_rows():
    station = _station_frame(air_temp=[25.0, 26.0])

    merged = weather_provider.merge_observations(station, pd.DataFrame())

    assert len(merged) == len(station)
    assert list(merged["air_temp"]) == [25.0, 26.0]


def test_merge_of_two_empty_frames_returns_an_empty_frame():
    merged = weather_provider.merge_observations(pd.DataFrame(), pd.DataFrame())

    assert merged.empty


def test_merge_of_single_row_frames_needs_no_special_case():
    station = _station_frame(n=1, air_temp=[25.0])
    grid = _grid_frame(n=1, solar_radiation=[500.0])

    merged = weather_provider.merge_observations(station, grid)

    assert len(merged) == 1
    assert merged["air_temp"].iloc[0] == 25.0
    assert merged["solar_radiation"].iloc[0] == 500.0


def test_merge_raises_when_a_row_has_no_resolvable_city():
    station = _station_frame(air_temp=[25.0, 26.0])
    station_reset = station.reset_index()
    station_reset.loc[0, "city"] = None
    station_bad = station_reset.set_index(["stid", "datetime_utc"])
    grid = _grid_frame(solar_radiation=[500.0, 510.0])

    with pytest.raises(ValueError) as excinfo:
        weather_provider.merge_observations(station_bad, grid)

    assert "1" in str(excinfo.value)


def test_merge_output_is_sorted_and_reproducible():
    station = _station_frame(air_temp=[25.0, 26.0])
    grid = _grid_frame(solar_radiation=[500.0, 510.0])

    merged_forward = weather_provider.merge_observations(station, grid)
    merged_reversed = weather_provider.merge_observations(
        station.iloc[::-1], grid.iloc[::-1]
    )

    pd.testing.assert_frame_equal(merged_forward, merged_reversed)
    assert merged_forward.index.is_monotonic_increasing


def _mock_grid_provider(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """
    Phase 6 test scaffolding only (D-07) -- a synthetic grid-based weather
    provider used to prove the merge path end to end before a real grid
    provider exists. Never registered in weather_provider's provider
    dispatch, never imported by any production module, and never
    referenced from fetch_weather. Phase 7 replaces this with a real
    Open-Meteo/ASOS adapter.

    Returns a frame carrying only `datetime_utc` and `solar_radiation` --
    the shape a real grid provider supplies, since NSRDB/Open-Meteo are the
    solar/backfill sources in data_provider.md's composition.
    """
    times = pd.date_range(start, periods=2, freq="5min")
    return pd.DataFrame(
        {
            "datetime_utc": times,
            "solar_radiation": [500.0, 510.0],
        }
    )


def _end_to_end_merged_frame(monkeypatch) -> pd.DataFrame:
    """
    Shared setup for the Task 2 end-to-end tests: a synthetic Austin
    station frame (via a monkeypatched dlr_pipeline.fetch_timeseries) tagged
    and city-attached through the real fetch_weather path, merged with
    _mock_grid_provider's synthetic solar-bearing frame tagged and
    city-attached the same way a real grid provider's output would be.
    """
    station_source = _synthetic_frame(
        air_temp=[25.0, 26.0],
        wind_speed=[5.0, 5.5],
        wind_direction=[180.0, 190.0],
        relative_humidity=[40.0, 41.0],
        lat=[30.2711, 30.2711],
        lon=[-97.7437, -97.7437],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: station_source)
    monkeypatch.setattr(asos_provider, "fetch_asos_1min", lambda *a, **k: pd.DataFrame())

    station = weather_provider.fetch_weather(["KAUS"], _START, _END)
    station = weather_provider.attach_city(station)

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    grid = _mock_grid_provider(lat, lon, _START, _END)
    grid = weather_provider.attach_provenance(grid, "open_meteo")
    grid = weather_provider.attach_city(grid, lat=lat, lon=lon)

    return weather_provider.merge_observations(station, grid)


def test_end_to_end_station_plus_mock_grid_produces_one_validated_row(monkeypatch):
    merged = _end_to_end_merged_frame(monkeypatch)

    assert len(merged) == 2
    assert (merged["wind_source"] == "synoptic").all()
    assert (merged["temp_source"] == "synoptic").all()
    assert (merged["humidity_source"] == "synoptic").all()
    assert (merged["solar_source"] == "open_meteo").all()

    for _, row in merged.iterrows():
        assert units_def.validate_pipeline_row(row.to_dict(), strict=False) == []


def test_mock_grid_provider_is_not_registered_in_the_real_dispatch():
    with pytest.raises(ValueError):
        weather_provider.fetch_weather((30.2711, -97.7437), _START, _END)


def test_merged_row_provenance_matches_its_values(monkeypatch):
    merged = _end_to_end_merged_frame(monkeypatch)

    for provenance_col, source_cols in weather_provider.PROVENANCE_FIELD_MAP.items():
        present_source_cols = [c for c in source_cols if c in merged.columns]
        has_value = merged[present_source_cols].notna().any(axis=1)
        assert (merged[provenance_col].notna() == has_value).all()


def test_attach_city_returns_literal_config_keys():
    times = pd.date_range("2025-07-01T00:00:00Z", periods=2, freq="5min")
    frame = pd.DataFrame(
        {
            "stid": ["KAUS"] * 2,
            "datetime_utc": times,
            "lat": [30.2711, 30.2711],
            "lon": [-97.7437, -97.7437],
        }
    ).set_index(["stid", "datetime_utc"])
    original_columns = list(frame.columns)

    result = weather_provider.attach_city(frame)

    assert "city" in result.columns
    assert set(result["city"].dropna().unique()) <= set(config.CITY_COORDINATES)
    assert list(frame.columns) == original_columns
    assert "city" not in frame.columns


# ──────────────────────────────────────────────────────────────────────────
# Task 2 (Plan 07-01): ASOS supplement, automatic and transparent (D-01..D-03)
# ──────────────────────────────────────────────────────────────────────────

_ASOS_SUPPLEMENT_TIMESTAMPS = [
    "2025-07-01T00:00:00Z",
    "2025-07-01T00:01:00Z",
    "2025-07-01T00:02:00Z",
]


def _asos_supplement_frame() -> pd.DataFrame:
    """
    A synthetic 1-minute ASOS frame overlapping the Synoptic frame's 00:00
    timestamp (with deliberately different sentinel values, to prove
    Synoptic wins there) and adding two ASOS-only timestamps (00:01, 00:02).
    """
    return pd.DataFrame(
        {
            "datetime_utc": pd.to_datetime(_ASOS_SUPPLEMENT_TIMESTAMPS, utc=True),
            "air_temp": [99.0, 25.1, 25.2],
            "wind_speed": [99.0, 5.05, 5.1],
            "wind_direction": [999.0, 181.0, 181.5],
        }
    )


def _asos_supplemented_result(monkeypatch) -> pd.DataFrame:
    """
    Shared setup: a synthetic 5-minute Austin Synoptic frame (00:00, 00:05)
    monkeypatched through dlr_pipeline.fetch_timeseries, supplemented by a
    1-minute ASOS frame (00:00, 00:01, 00:02) monkeypatched through
    asos_provider.fetch_asos_1min, obtained through the real, unmodified
    fetch_weather(["KAUS"], ...) call -- no new argument, no new keyword.
    """
    synoptic_source = _synthetic_frame(
        air_temp=[25.0, 25.5],
        wind_speed=[5.0, 5.2],
        wind_direction=[180.0, 182.0],
        relative_humidity=[40.0, 41.0],
        solar_radiation=[None, None],
        lat=[30.2711, 30.2711],
        lon=[-97.7437, -97.7437],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: synoptic_source)
    monkeypatch.setattr(asos_provider, "fetch_asos_1min", lambda *a, **k: _asos_supplement_frame())

    return weather_provider.fetch_weather(["KAUS"], _START, _END)


def _row_at(frame: pd.DataFrame, timestamp: str) -> pd.Series:
    reset = frame.reset_index()
    matches = reset[reset["datetime_utc"] == pd.Timestamp(timestamp, tz="UTC")]
    assert len(matches) == 1, f"expected exactly one row at {timestamp}, found {len(matches)}"
    return matches.iloc[0]


def test_asos_supplement_adds_rows_at_timestamps_synoptic_does_not_have(monkeypatch):
    result = _asos_supplemented_result(monkeypatch)

    assert len(result) == 4  # union of {00:00, 00:05} and {00:00, 00:01, 00:02}


def test_asos_supplement_leaves_synoptic_winning_at_a_shared_timestamp(monkeypatch):
    result = _asos_supplemented_result(monkeypatch)

    shared = _row_at(result, "2025-07-01T00:00:00Z")
    assert shared["air_temp"] == 25.0
    assert shared["temp_source"] == "synoptic"


def test_asos_only_rows_are_attributed_to_asos(monkeypatch):
    result = _asos_supplemented_result(monkeypatch)

    asos_only = _row_at(result, "2025-07-01T00:01:00Z")
    assert asos_only["temp_source"] == "asos"
    assert asos_only["wind_source"] == "asos"


def test_asos_only_rows_leave_unmeasured_fields_null(monkeypatch):
    result = _asos_supplemented_result(monkeypatch)

    asos_only = _row_at(result, "2025-07-01T00:01:00Z")
    assert pd.isna(asos_only["relative_humidity"])
    assert pd.isna(asos_only["solar_radiation"])
    assert asos_only["humidity_source"] is None or pd.isna(asos_only["humidity_source"])
    assert asos_only["solar_source"] is None or pd.isna(asos_only["solar_source"])


def test_asos_supplemented_rows_validate_against_pipeline_schema(monkeypatch):
    result = _asos_supplemented_result(monkeypatch)

    for _, row in result.iterrows():
        assert units_def.validate_pipeline_row(row.to_dict(), strict=False) == []


# ──────────────────────────────────────────────────────────────────────────
# Task 3 (Plan 07-01): fail loud on bad responses, stay silent-free on real
# outages, protect the primary
# ──────────────────────────────────────────────────────────────────────────


def test_asos_failure_propagates_out_of_fetch_weather(monkeypatch):
    synoptic_source = _synthetic_frame(
        air_temp=[25.0, 25.5],
        wind_speed=[5.0, 5.2],
        wind_direction=[180.0, 182.0],
        relative_humidity=[40.0, 41.0],
        solar_radiation=[None, None],
        lat=[30.2711, 30.2711],
        lon=[-97.7437, -97.7437],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: synoptic_source)

    def _raise(*a, **k):
        raise ValueError("ASOS boom")

    monkeypatch.setattr(asos_provider, "fetch_asos_1min", _raise)

    with pytest.raises(ValueError):
        weather_provider.fetch_weather(["KAUS"], _START, _END)


def test_asos_empty_window_returns_the_synoptic_frame_unchanged(monkeypatch):
    synoptic_source = _synthetic_frame(
        air_temp=[25.0, 25.5],
        wind_speed=[5.0, 5.2],
        wind_direction=[180.0, 182.0],
        relative_humidity=[40.0, 41.0],
        solar_radiation=[None, None],
        lat=[30.2711, 30.2711],
        lon=[-97.7437, -97.7437],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: synoptic_source)
    monkeypatch.setattr(asos_provider, "fetch_asos_1min", lambda *a, **k: pd.DataFrame())

    expected = weather_provider.attach_provenance(synoptic_source, "synoptic")
    result = weather_provider.fetch_weather(["KAUS"], _START, _END)

    pd.testing.assert_frame_equal(result, expected)


def test_asos_supplement_is_skipped_when_a_synoptic_row_has_no_resolvable_city(monkeypatch):
    synoptic_source = _synthetic_frame(
        air_temp=[25.0, 25.5],
        wind_speed=[5.0, 5.2],
        wind_direction=[180.0, 182.0],
        relative_humidity=[40.0, 41.0],
        solar_radiation=[None, None],
        lat=[30.2711, None],
        lon=[-97.7437, None],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: synoptic_source)
    monkeypatch.setattr(asos_provider, "fetch_asos_1min", lambda *a, **k: _asos_supplement_frame())

    expected = weather_provider.attach_provenance(synoptic_source, "synoptic")
    result = weather_provider.fetch_weather(["KAUS"], _START, _END)

    pd.testing.assert_frame_equal(result, expected)


def test_asos_supplement_is_skipped_when_the_synoptic_frame_has_duplicate_city_timestamp_keys(
    monkeypatch,
):
    times = pd.to_datetime(
        ["2025-07-01T00:00:00Z", "2025-07-01T00:00:00Z"], utc=True
    )
    synoptic_source = pd.DataFrame(
        {
            "stid": ["KAUS", "KAUS2"],
            "datetime_utc": times,
            "air_temp": [25.0, 26.0],
            "wind_speed": [5.0, 5.1],
            "wind_direction": [180.0, 181.0],
            "relative_humidity": [40.0, 41.0],
            "solar_radiation": [None, None],
            "lat": [30.2711, 30.2711],
            "lon": [-97.7437, -97.7437],
        }
    ).set_index(["stid", "datetime_utc"]).sort_index()
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: synoptic_source)
    monkeypatch.setattr(asos_provider, "fetch_asos_1min", lambda *a, **k: _asos_supplement_frame())

    expected = weather_provider.attach_provenance(synoptic_source, "synoptic")
    result = weather_provider.fetch_weather(["KAUS", "KAUS2"], _START, _END)

    pd.testing.assert_frame_equal(result, expected)


def test_asos_supplement_never_drops_a_synoptic_row(monkeypatch):
    result = _asos_supplemented_result(monkeypatch)

    reset = result.reset_index()
    for ts in ("2025-07-01T00:00:00Z", "2025-07-01T00:05:00Z"):
        matches = reset[
            (reset["stid"] == "KAUS")
            & (reset["datetime_utc"] == pd.Timestamp(ts, tz="UTC"))
        ]
        assert len(matches) == 1


def test_all_four_cities_resolve_to_a_three_letter_asos_station():
    for city, (lat, lon) in config.CITY_COORDINATES.items():
        resolved = weather_provider.resolve_station_city(lat, lon)
        assert resolved in config.ASOS_STATIONS


def test_corridor_usable_observation_reads_an_asos_supplemented_frame(monkeypatch):
    synoptic_source = _synthetic_frame(
        air_temp=[25.0, 25.5],
        wind_speed=[5.0, 5.2],
        wind_direction=[180.0, 182.0],
        relative_humidity=[40.0, 41.0],
        solar_radiation=[500.0, 510.0],
        lat=[30.2711, 30.2711],
        lon=[-97.7437, -97.7437],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: synoptic_source)
    monkeypatch.setattr(asos_provider, "fetch_asos_1min", lambda *a, **k: _asos_supplement_frame())

    result = weather_provider.fetch_weather(["KAUS"], _START, _END)

    reading = corridor_discretization._usable_observation(result, "KAUS")

    assert reading is not None
    assert reading["temp"] == 25.0
    assert reading["wind"] == 5.0
    assert reading["solar"] == 500.0


# ──────────────────────────────────────────────────────────────────────────
# Task 1 (Plan 07-02): Open-Meteo grid-path dispatch (D-04, WX-04)
# ──────────────────────────────────────────────────────────────────────────


def _open_meteo_frame(n: int = 2) -> pd.DataFrame:
    times = pd.date_range("2025-07-01T00:00:00Z", periods=n, freq="1h")
    return pd.DataFrame(
        {
            "datetime_utc": times,
            "air_temp": [29.9 + i for i in range(n)],
            "wind_speed": [3.4 + i * 0.1 for i in range(n)],
            "wind_direction": [160.0 + i for i in range(n)],
            "solar_radiation": [291.0 + i for i in range(n)],
            "relative_humidity": [63.0 + i for i in range(n)],
        }
    )


def test_open_meteo_grid_fetch_returns_a_validated_provenanced_frame(monkeypatch):
    monkeypatch.setattr(
        open_meteo_provider, "fetch_open_meteo", lambda *a, **k: _open_meteo_frame()
    )

    result = weather_provider.fetch_weather(
        config.CITY_COORDINATES["AUSTIN"], _START, _END, provider="open_meteo"
    )

    for col in ("temp_source", "wind_source", "solar_source", "humidity_source"):
        assert (result[col] == "open_meteo").all()
    assert (result["city"] == "AUSTIN").all()
    for _, row in result.iterrows():
        assert units_def.validate_pipeline_row(row.to_dict(), strict=False) == []


def test_open_meteo_is_not_reachable_from_the_station_path(monkeypatch):
    counter = {"count": 0}

    def _recorder(*a, **k):
        counter["count"] += 1
        return _open_meteo_frame()

    monkeypatch.setattr(open_meteo_provider, "fetch_open_meteo", _recorder)

    with pytest.raises(ValueError):
        weather_provider.fetch_weather(["KAUS"], _START, _END, provider="open_meteo")

    assert counter["count"] == 0


def test_open_meteo_grid_path_still_rejects_other_provider_names():
    with pytest.raises(ValueError) as excinfo:
        weather_provider.fetch_weather(config.CITY_COORDINATES["AUSTIN"], _START, _END)

    assert "grid" in str(excinfo.value)


# ──────────────────────────────────────────────────────────────────────────
# Task 2 (Plan 07-02): Open-Meteo adjacency merge + unresolvable-coordinate
# guard (WX-04 adjacency edge, D-04)
# ──────────────────────────────────────────────────────────────────────────


def test_open_meteo_row_merges_with_a_station_row_at_an_exactly_equal_key():
    station = _station_frame(air_temp=[25.0, 26.0], wind_speed=[5.0, 5.5])
    grid = _grid_frame(air_temp=[99.0, 98.0], solar_radiation=[500.0, 510.0])

    merged = weather_provider.merge_observations(station, grid)

    assert len(merged) == 2
    assert list(merged["air_temp"]) == [25.0, 26.0]
    assert (merged["temp_source"] == "synoptic").all()
    assert list(merged["solar_radiation"]) == [500.0, 510.0]
    assert (merged["solar_source"] == "open_meteo").all()


def test_open_meteo_grid_fetch_raises_on_unresolvable_coordinates(monkeypatch):
    monkeypatch.setattr(
        open_meteo_provider, "fetch_open_meteo", lambda *a, **k: _open_meteo_frame()
    )

    with pytest.raises(ValueError):
        weather_provider.fetch_weather(
            (float("nan"), float("nan")), _START, _END, provider="open_meteo"
        )


# ──────────────────────────────────────────────────────────────────────────
# Plan 07-03: one frame, three providers, honest provenance (T-07-14,
# ROADMAP SC3 for WX-02 + WX-04 simultaneously) -- and a source-level
# no-secrets gate over both new provider modules (T-07-15, ROADMAP SC4)
# ──────────────────────────────────────────────────────────────────────────

_THREE_PROVIDER_ASOS_TIMESTAMPS = [
    "2025-07-01T00:01:00Z",
    "2025-07-01T00:02:00Z",
]

_THREE_PROVIDER_OPEN_METEO_TIMESTAMPS = [
    "2025-07-01T00:00:00Z",
    "2025-07-01T00:10:00Z",
]


def _three_provider_asos_frame() -> pd.DataFrame:
    """A 1-minute ASOS frame at two ASOS-only timestamps -- no humidity or
    solar columns (D-02: ASOS never measures those fields)."""
    return pd.DataFrame(
        {
            "datetime_utc": pd.to_datetime(_THREE_PROVIDER_ASOS_TIMESTAMPS, utc=True),
            "air_temp": [25.1, 25.2],
            "wind_speed": [5.05, 5.1],
            "wind_direction": [181.0, 181.5],
        }
    )


def _three_provider_open_meteo_frame() -> pd.DataFrame:
    """
    A grid-sourced frame at two timestamps: `00:00`, which overlaps the
    Synoptic frame (Synoptic's value and provenance still win there per
    `merge_observations`' station-first contract -- these values are never
    read out), and `00:10`, which has no station-side coverage at all --
    the frame's only genuinely grid-only row.

    Carries the full 5-column set `fetch_open_meteo` always returns in
    production (it never returns a partial variable set -- see
    `open_meteo_provider.fetch_open_meteo`'s ordered body-shape validation),
    rather than a solar-only shape: `PIPELINE_SCHEMA` marks `air_temp`,
    `wind_speed` and `wind_direction` `required: True`, so a genuinely
    grid-only row (00:10) that supplied only `solar_radiation` could never
    satisfy `validate_pipeline_row` no matter what merge logic ran --
    that's a property of the schema, not something this test's provenance
    assertions get to waive. Making the mock match real Open-Meteo's actual
    output shape is what resolves it, and is also the more faithful test.
    """
    times = pd.to_datetime(_THREE_PROVIDER_OPEN_METEO_TIMESTAMPS, utc=True)
    return pd.DataFrame(
        {
            "datetime_utc": times,
            "air_temp": [40.0, 27.0],
            "wind_speed": [12.0, 6.0],
            "wind_direction": [270.0, 200.0],
            "solar_radiation": [500.0, 505.0],
            "relative_humidity": [70.0, 55.0],
        }
    )


def _three_provider_frame(monkeypatch) -> pd.DataFrame:
    """
    Shared setup for this group: one frame assembled from all three
    providers this phase composes -- Synoptic (station primary), ASOS
    (station supplement, D-01..D-03) and Open-Meteo (grid backfill, D-04)
    -- each obtained through the real fetch_weather dispatch (never a
    hand-built tagged frame), then combined with the real
    merge_observations.

    - Synoptic: a 5-minute Austin frame at 00:00 and 00:05 carrying
      air_temp, wind_speed, wind_direction, relative_humidity, lat, lon.
    - ASOS: a 1-minute frame at 00:01 and 00:02 carrying only air_temp,
      wind_speed, wind_direction.
    - Open-Meteo: the full 5-column set (matching its real, unconditional
      response shape) at 00:00 (overlapping Synoptic -- discarded there,
      since Synoptic wins) and 00:10 (the frame's only genuinely
      grid-only row -- see `_three_provider_open_meteo_frame`'s docstring
      for why a solar-only mock at this row cannot satisfy
      `PIPELINE_SCHEMA`'s required-field check).
    """
    synoptic_source = _synthetic_frame(
        air_temp=[25.0, 25.5],
        wind_speed=[5.0, 5.2],
        wind_direction=[180.0, 182.0],
        relative_humidity=[40.0, 41.0],
        lat=[30.2711, 30.2711],
        lon=[-97.7437, -97.7437],
    )
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: synoptic_source)
    monkeypatch.setattr(
        asos_provider, "fetch_asos_1min", lambda *a, **k: _three_provider_asos_frame()
    )
    monkeypatch.setattr(
        open_meteo_provider,
        "fetch_open_meteo",
        lambda *a, **k: _three_provider_open_meteo_frame(),
    )

    station = weather_provider.fetch_weather(["KAUS"], _START, _END)
    grid = weather_provider.fetch_weather(
        config.CITY_COORDINATES["AUSTIN"], _START, _END, provider="open_meteo"
    )

    return weather_provider.merge_observations(station, grid)


def test_three_provider_frame_has_one_row_per_distinct_timestamp(monkeypatch):
    result = _three_provider_frame(monkeypatch)

    # union of {00:00, 00:05} (synoptic), {00:01, 00:02} (asos) and
    # {00:00, 00:10} (open_meteo) -- five distinct timestamps
    assert len(result) == 5


def test_three_provider_frame_names_the_actual_supplier_per_field(monkeypatch):
    result = _three_provider_frame(monkeypatch)

    # temp_source: Synoptic wins at 00:00/00:05 (it's the station primary and
    # combine_first keeps its non-null value even though Open-Meteo also
    # supplies air_temp at 00:00); ASOS is the sole supplier at 00:01/00:02;
    # Open-Meteo is the sole supplier at 00:10 (no station coverage there).
    assert _row_at(result, "2025-07-01T00:00:00Z")["temp_source"] == "synoptic"
    assert _row_at(result, "2025-07-01T00:05:00Z")["temp_source"] == "synoptic"
    assert _row_at(result, "2025-07-01T00:01:00Z")["temp_source"] == "asos"
    assert _row_at(result, "2025-07-01T00:02:00Z")["temp_source"] == "asos"
    assert _row_at(result, "2025-07-01T00:10:00Z")["temp_source"] == "open_meteo"

    # solar_source: only Open-Meteo ever supplies solar_radiation -- present
    # at both its timestamps, null everywhere neither Synoptic nor ASOS (nor
    # Open-Meteo) reports it.
    assert _row_at(result, "2025-07-01T00:00:00Z")["solar_source"] == "open_meteo"
    assert _row_at(result, "2025-07-01T00:10:00Z")["solar_source"] == "open_meteo"
    for ts in ("2025-07-01T00:01:00Z", "2025-07-01T00:02:00Z", "2025-07-01T00:05:00Z"):
        assert pd.isna(_row_at(result, ts)["solar_source"])

    # humidity_source: Synoptic supplies it at 00:00/00:05 and wins there;
    # ASOS never measures it (D-02, null at 00:01/00:02); Open-Meteo is the
    # sole supplier at 00:10.
    assert _row_at(result, "2025-07-01T00:00:00Z")["humidity_source"] == "synoptic"
    assert _row_at(result, "2025-07-01T00:05:00Z")["humidity_source"] == "synoptic"
    assert _row_at(result, "2025-07-01T00:10:00Z")["humidity_source"] == "open_meteo"
    for ts in ("2025-07-01T00:01:00Z", "2025-07-01T00:02:00Z"):
        assert pd.isna(_row_at(result, ts)["humidity_source"])


def test_three_provider_frame_provenance_matches_its_values(monkeypatch):
    result = _three_provider_frame(monkeypatch)

    for provenance_col, source_cols in weather_provider.PROVENANCE_FIELD_MAP.items():
        present_source_cols = [c for c in source_cols if c in result.columns]
        has_value = result[present_source_cols].notna().any(axis=1)
        assert (result[provenance_col].notna() == has_value).all()


def test_three_provider_frame_uses_only_registered_provider_names(monkeypatch):
    result = _three_provider_frame(monkeypatch)

    seen = set()
    for provenance_col in weather_provider.PROVENANCE_FIELD_MAP:
        seen |= set(result[provenance_col].dropna().unique())

    assert seen <= units_def.KNOWN_PROVIDER_NAMES
    assert seen == {"synoptic", "asos", "open_meteo"}


def test_three_provider_frame_rows_validate_against_pipeline_schema(monkeypatch):
    result = _three_provider_frame(monkeypatch)

    for _, row in result.iterrows():
        assert units_def.validate_pipeline_row(row.to_dict(), strict=False) == []


def test_new_providers_read_no_secret():
    """
    ROADMAP Success Criterion 4, asserted at the source level rather than
    inferred from the tests happening to pass without a token (T-07-15).
    """
    backend_dir = Path(__file__).resolve().parent.parent
    forbidden_substrings = (
        "os.environ",
        "os.getenv",
        "getpass",
        "_TOKEN",
        "_KEY",
        "_SECRET",
    )

    for module_name in ("asos_provider.py", "open_meteo_provider.py"):
        source_path = backend_dir / module_name
        text = source_path.read_text()
        code_lines = [
            line for line in text.splitlines() if not line.strip().startswith("#")
        ]
        stripped_text = "\n".join(code_lines)

        for forbidden in forbidden_substrings:
            assert forbidden not in stripped_text, (
                f"{module_name} contains forbidden substring {forbidden!r}"
            )

        import_lines = [
            line
            for line in code_lines
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for import_line in import_lines:
            assert "import os" not in import_line, (
                f"{module_name} imports 'os': {import_line!r}"
            )
            assert "dotenv" not in import_line, (
                f"{module_name} imports 'dotenv': {import_line!r}"
            )

        assert "dlr_pipeline._token" not in stripped_text


# ──────────────────────────────────────────────────────────────────────────
# Task 1 (Plan 08-01): NSRDB grid-path dispatch (D-05, WX-03)
# ──────────────────────────────────────────────────────────────────────────


def _nsrdb_frame(n: int = 2) -> pd.DataFrame:
    # Same cadence as _station_frame's default (freq="5min") so the merge
    # test below aligns on an exactly-equal (city, datetime_utc) key rather
    # than exercising the union-of-timestamps path -- that path is already
    # covered by test_merge_combines_station_and_grid_into_one_row_per_timestamp.
    times = pd.date_range("2025-07-01T00:00:00Z", periods=n, freq="5min")
    return pd.DataFrame(
        {
            "datetime_utc": times,
            "solar_radiation": [291.0 + i for i in range(n)],
        }
    )


def test_nsrdb_grid_fetch_returns_a_solar_only_provenanced_frame(monkeypatch):
    monkeypatch.setattr(nsrdb_provider, "fetch_nsrdb", lambda *a, **k: _nsrdb_frame())

    result = weather_provider.fetch_weather(
        config.CITY_COORDINATES["AUSTIN"], _START, _END, provider="nsrdb"
    )

    assert (result["solar_source"] == "nsrdb").all()
    assert (result["city"] == "AUSTIN").all()


def test_nsrdb_row_validates_against_the_schema_once_merged_with_a_station_row(monkeypatch):
    monkeypatch.setattr(nsrdb_provider, "fetch_nsrdb", lambda *a, **k: _nsrdb_frame())

    nsrdb_result = weather_provider.fetch_weather(
        config.CITY_COORDINATES["AUSTIN"], _START, _END, provider="nsrdb"
    )
    station = _station_frame(
        air_temp=[25.0, 26.0],
        wind_speed=[5.0, 5.5],
        wind_direction=[180.0, 190.0],
    )

    # Assert over the merged row rather than the bare NSRDB row
    # deliberately: air_temp, wind_speed and wind_direction are
    # required: True in PIPELINE_SCHEMA, so a solar-only frame reports
    # three MISSING-required errors by design. The merged row is the shape
    # a real pipeline row has, and this is the assertion ROADMAP SC3's
    # "pass PIPELINE_SCHEMA range validation" is actually about.
    merged = weather_provider.merge_observations(station, nsrdb_result)

    for _, row in merged.iterrows():
        assert units_def.validate_pipeline_row(row.to_dict(), strict=False) == []


def test_nsrdb_is_not_reachable_from_the_station_path(monkeypatch):
    counter = {"count": 0}

    def _recorder(*a, **k):
        counter["count"] += 1
        return _nsrdb_frame()

    monkeypatch.setattr(nsrdb_provider, "fetch_nsrdb", _recorder)

    with pytest.raises(ValueError):
        weather_provider.fetch_weather(["KAUS"], _START, _END, provider="nsrdb")

    assert counter["count"] == 0


def test_nsrdb_grid_fetch_raises_on_unresolvable_coordinates(monkeypatch):
    monkeypatch.setattr(nsrdb_provider, "fetch_nsrdb", lambda *a, **k: _nsrdb_frame())

    with pytest.raises(ValueError):
        weather_provider.fetch_weather(
            (float("nan"), float("nan")), _START, _END, provider="nsrdb"
        )


def test_grid_path_still_rejects_unknown_provider_names():
    with pytest.raises(ValueError) as excinfo:
        weather_provider.fetch_weather(
            config.CITY_COORDINATES["AUSTIN"], _START, _END, provider="tceq"
        )

    message = str(excinfo.value)
    assert "grid" in message
    assert "open_meteo" in message
    assert "nsrdb" in message


# ──────────────────────────────────────────────────────────────────────────
# Task 2 (Plan 08-02): D-02's solar-only provenance guarantee, observed
# through fetch_weather and through a real cross-provider merge
# ──────────────────────────────────────────────────────────────────────────


def test_nsrdb_row_leaves_wind_temp_and_humidity_provenance_null(monkeypatch):
    monkeypatch.setattr(nsrdb_provider, "fetch_nsrdb", lambda *a, **k: _nsrdb_frame())

    result = weather_provider.fetch_weather(
        config.CITY_COORDINATES["AUSTIN"], _START, _END, provider="nsrdb"
    )

    assert (result["solar_source"] == "nsrdb").all()
    assert result["wind_source"].isna().all()
    assert result["temp_source"].isna().all()
    assert result["humidity_source"].isna().all()


def test_nsrdb_solar_merges_with_a_station_row_at_an_exactly_equal_key():
    station = _station_frame(air_temp=[25.0, 26.0], wind_speed=[5.0, 5.5])
    times = pd.date_range("2025-07-01T00:00:00Z", periods=2, freq="5min")
    nsrdb_grid = weather_provider.attach_provenance(
        pd.DataFrame(
            {
                "datetime_utc": times,
                "city": ["AUSTIN"] * 2,
                "solar_radiation": [291.0, 292.0],
            }
        ),
        "nsrdb",
    )

    merged = weather_provider.merge_observations(station, nsrdb_grid)

    assert len(merged) == 2
    assert list(merged["air_temp"]) == [25.0, 26.0]
    assert (merged["temp_source"] == "synoptic").all()
    assert list(merged["wind_speed"]) == [5.0, 5.5]
    assert (merged["wind_source"] == "synoptic").all()
    assert list(merged["solar_radiation"]) == [291.0, 292.0]
    assert (merged["solar_source"] == "nsrdb").all()


# ──────────────────────────────────────────────────────────────────────────
# Task 1 (Plan 08-03): NSRDB credential-source gate (T-08-15, T-08-16)
# ──────────────────────────────────────────────────────────────────────────


class _FakeNsrdbResponse:
    """
    A minimal stand-in for `requests.Response`, carrying only the
    attributes `nsrdb_provider.fetch_nsrdb`'s success path reads
    (`ok`, `status_code`, `text`). Scoped to this test group rather than
    reusing `nsrdb_provider_test.py::_FakeResponse`, since this file tests
    `nsrdb_provider` only from the outside, through `weather_provider`'s
    own import of it.
    """

    def __init__(self, text: str = ""):
        self.text = text
        self.ok = True
        self.status_code = 200


_NSRDB_SUCCESS_CSV = (
    "Source,Location ID,Latitude,Longitude,Time Zone,GHI Units\n"
    "NSRDB,145809,30.2711,-97.7437,0,w/m2\n"
    "Year,Month,Day,Hour,Minute,GHI\n"
    "2023,7,1,0,0,200.0\n"
)


def test_nsrdb_provider_imports_without_any_credential(monkeypatch):
    """
    Importing nsrdb_provider must never require NREL_API_KEY or
    NREL_API_EMAIL -- both credential lookups happen inside fetch_nsrdb,
    not at module level (mirrors
    test_module_import_has_no_side_effects's SYNOPTIC_TOKEN check above).
    """
    monkeypatch.delenv("NREL_API_KEY", raising=False)
    monkeypatch.delenv("NREL_API_EMAIL", raising=False)

    import importlib

    importlib.reload(nsrdb_provider)


def test_nsrdb_provider_reads_its_credentials_only_from_the_environment(monkeypatch):
    """
    Behavioural proof that no credential literal exists anywhere in
    nsrdb_provider: with both variables unset, fetch_nsrdb must raise
    EnvironmentError having issued zero requests (a baked-in default would
    make this half pass silently with a request); with sentinel values
    set, the recorded request params must carry exactly those sentinels
    (a baked-in override would make this half carry something else).
    """
    monkeypatch.delenv("NREL_API_KEY", raising=False)
    monkeypatch.delenv("NREL_API_EMAIL", raising=False)

    counter = {"count": 0}

    def _counting_recorder(*a, **k):
        counter["count"] += 1
        return _FakeNsrdbResponse(_NSRDB_SUCCESS_CSV)

    monkeypatch.setattr(nsrdb_provider.requests, "get", _counting_recorder)

    with pytest.raises(EnvironmentError):
        nsrdb_provider.fetch_nsrdb(30.2711, -97.7431, "2023-07-01", "2023-07-01")

    assert counter["count"] == 0

    sentinel_key = "sentinel-key-08-03"
    sentinel_email = "sentinel-email-08-03@example.com"
    monkeypatch.setenv("NREL_API_KEY", sentinel_key)
    monkeypatch.setenv("NREL_API_EMAIL", sentinel_email)

    recorder = {}

    def _success_recorder(url, params=None, timeout=None):
        recorder["params"] = params
        return _FakeNsrdbResponse(_NSRDB_SUCCESS_CSV)

    monkeypatch.setattr(nsrdb_provider.requests, "get", _success_recorder)

    nsrdb_provider.fetch_nsrdb(30.2711, -97.7431, "2023-07-01", "2023-07-01")

    assert recorder["params"]["api_key"] == sentinel_key
    assert recorder["params"]["email"] == sentinel_email


def test_no_nsrdb_credential_value_is_tracked_in_the_repository():
    """
    Source-level gate (T-08-15): narrow and readable on purpose -- its job
    is to catch a pasted key during development, not to be a general
    secret scanner. Asserts nsrdb_provider.py contains no line that
    assigns a quoted string literal to a name containing "key" or "email"
    (case-insensitive); every real credential read in the module is an
    os.getenv(...) call, never a literal.
    """
    import re

    source_path = Path(__file__).resolve().parent.parent / "nsrdb_provider.py"
    lines = source_path.read_text().splitlines()

    assignment_pattern = re.compile(
        r'^\s*[A-Za-z_][A-Za-z0-9_]*(key|email)[A-Za-z0-9_]*\s*'
        r'(?::\s*\w+\s*)?=\s*["\'][^"\']*["\']\s*$',
        re.IGNORECASE,
    )

    offending = [line for line in lines if assignment_pattern.match(line)]
    assert offending == [], (
        f"nsrdb_provider.py assigns a quoted string literal to a "
        f"KEY/EMAIL-named variable: {offending!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# Plan 09-01 Task 3: "tceq" station-path dispatch (WX-01 tracer)
# ──────────────────────────────────────────────────────────────────────────


def _tceq_frame() -> pd.DataFrame:
    times = pd.date_range("2026-07-01T06:00:00Z", periods=2, freq="h")
    return pd.DataFrame(
        {
            "datetime_utc": times,
            "air_temp": [24.0, 24.5],
            "wind_speed": [4.0, 4.5],
            "wind_direction": [180.0, 185.0],
            "relative_humidity": [60.0, 61.0],
        }
    )


def test_tceq_station_path_returns_a_provenanced_frame(monkeypatch):
    monkeypatch.setattr(tceq_provider, "fetch_tceq", lambda *a, **k: _tceq_frame())

    result = weather_provider.fetch_weather(["83"], _START, _END, provider="tceq")

    row = result.iloc[0]
    assert row["wind_source"] == "tceq"
    assert row["temp_source"] == "tceq"
    assert row["humidity_source"] == "tceq"


def test_tceq_is_not_reachable_from_the_grid_path(monkeypatch):
    counter = {"count": 0}

    def _recorder(*a, **k):
        counter["count"] += 1
        return _tceq_frame()

    monkeypatch.setattr(tceq_provider, "fetch_tceq", _recorder)

    with pytest.raises(ValueError) as excinfo:
        weather_provider.fetch_weather((27.8006, -97.3964), _START, _END, provider="tceq")

    assert "grid" in str(excinfo.value)
    assert counter["count"] == 0


def test_tceq_station_path_still_rejects_an_unknown_provider_name():
    with pytest.raises(ValueError) as excinfo:
        weather_provider.fetch_weather(["83"], _START, _END, provider="nope")

    message = str(excinfo.value)
    assert "synoptic" in message
    assert "tceq" in message


def test_tceq_row_validates_against_pipeline_schema(monkeypatch):
    monkeypatch.setattr(tceq_provider, "fetch_tceq", lambda *a, **k: _tceq_frame())

    result = weather_provider.fetch_weather(["83"], _START, _END, provider="tceq")

    for _, row in result.iterrows():
        assert units_def.validate_pipeline_row(row.to_dict(), strict=False) == []


# ──────────────────────────────────────────────────────────────────────────
# Plan 09-02 Task 2: four-city provenance, including the null-RH proof (D-05)
# ──────────────────────────────────────────────────────────────────────────


def _tceq_frame_with_rh(relative_humidity) -> pd.DataFrame:
    times = pd.date_range("2026-07-01T06:00:00Z", periods=2, freq="h")
    return pd.DataFrame(
        {
            "datetime_utc": times,
            "air_temp": [24.0, 24.5],
            "wind_speed": [4.0, 4.5],
            "wind_direction": [180.0, 185.0],
            "relative_humidity": relative_humidity,
        }
    )


def test_tceq_null_rh_row_has_null_humidity_source(monkeypatch):
    monkeypatch.setattr(
        tceq_provider, "fetch_tceq", lambda *a, **k: _tceq_frame_with_rh([None, None])
    )

    result = weather_provider.fetch_weather(["38"], _START, _END, provider="tceq")

    row = result.iloc[0]
    assert pd.isna(row["humidity_source"])
    assert row["wind_source"] == "tceq"
    assert row["temp_source"] == "tceq"


@pytest.mark.parametrize("cams_id", sorted(config.TCEQ_STATIONS.values()))
def test_tceq_provenance_holds_for_every_configured_city(monkeypatch, cams_id):
    monkeypatch.setattr(
        tceq_provider, "fetch_tceq", lambda *a, **k: _tceq_frame_with_rh([60.0, 61.0])
    )

    result = weather_provider.fetch_weather([cams_id], _START, _END, provider="tceq")

    row = result.iloc[0]
    assert row["wind_source"] == "tceq"
    assert row["temp_source"] == "tceq"
    assert row["humidity_source"] == "tceq"


# ──────────────────────────────────────────────────────────────────────────
# Plan 09-02 Task 3: the multi-CAMS-ID guard on the "tceq" station path.
# ──────────────────────────────────────────────────────────────────────────


def test_tceq_rejects_multiple_cams_ids(monkeypatch):
    counter = {"count": 0}

    def _recorder(*a, **k):
        counter["count"] += 1
        return _tceq_frame()

    monkeypatch.setattr(tceq_provider, "fetch_tceq", _recorder)

    with pytest.raises(ValueError) as excinfo:
        weather_provider.fetch_weather(["38", "83"], _START, _END, provider="tceq")

    message = str(excinfo.value)
    assert "38" in message
    assert "83" in message
    assert counter["count"] == 0


def test_tceq_accepts_a_single_cams_id_list(monkeypatch):
    monkeypatch.setattr(tceq_provider, "fetch_tceq", lambda *a, **k: _tceq_frame())

    result = weather_provider.fetch_weather(["83"], _START, _END, provider="tceq")

    assert not result.empty


# ──────────────────────────────────────────────────────────────────────────
# Plan 09-03 Task 1: TCEQ no-credential source-and-behaviour gate
# (T-09-20, T-09-21)
# ──────────────────────────────────────────────────────────────────────────


def test_tceq_provider_reads_no_credential(monkeypatch):
    """
    Source-and-behaviour gate in the same style as Plan 07-03's
    `test_new_providers_read_no_secret` and Plan 08-03's
    `test_no_nsrdb_credential_value_is_tracked_in_the_repository`/
    `test_nsrdb_provider_imports_without_any_credential`: TCEQ's
    `daily_summary.pl` endpoint is public and unauthenticated, so this
    phase must not have quietly introduced a credential path (T-09-20).

    Comment lines are filtered out before scanning so a comment explaining
    that TCEQ needs no credential (the module docstring says exactly this)
    cannot itself trip the gate -- the gate is proven load-bearing by
    making it fail against a deliberately broken scratch copy before being
    accepted as green (T-09-21).
    """
    import re

    source_path = Path(__file__).resolve().parent.parent / "tceq_provider.py"
    lines = source_path.read_text().splitlines()
    code_lines = [line for line in lines if not line.strip().startswith("#")]
    stripped_text = "\n".join(code_lines)

    assert "os.environ" not in stripped_text, (
        "tceq_provider.py references os.environ -- TCEQ is unauthenticated "
        "and must read no environment variable."
    )
    assert "os.getenv" not in stripped_text, (
        "tceq_provider.py references os.getenv -- TCEQ is unauthenticated "
        "and must read no environment variable."
    )

    import_lines = [
        line
        for line in code_lines
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    for import_line in import_lines:
        assert "import os" not in import_line, (
            f"tceq_provider.py imports 'os': {import_line!r}"
        )

    assignment_pattern = re.compile(
        r'^\s*[A-Za-z_][A-Za-z0-9_]*(TOKEN|KEY|SECRET|PASSWORD)[A-Za-z0-9_]*\s*'
        r'(?::\s*\w+(?:\[[^\]]*\])?\s*)?=\s*["\'][^"\']*["\']\s*$',
        re.IGNORECASE,
    )
    offending = [line for line in code_lines if assignment_pattern.match(line)]
    assert offending == [], (
        f"tceq_provider.py assigns a quoted string literal to a "
        f"TOKEN/KEY/SECRET/PASSWORD-named variable: {offending!r}"
    )

    # Behavioural proof: the claim that actually matters is that
    # tceq_provider works with none of this phase's sibling providers'
    # credential env vars set either -- reload must succeed regardless.
    for var in ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL"):
        monkeypatch.delenv(var, raising=False)

    import importlib

    importlib.reload(tceq_provider)


# ──────────────────────────────────────────────────────────────────────────
# Plan 10-01 Task 1: end-to-end TCEQ-to-Synoptic fallback -- one path only
# (WX-06, ROADMAP SC1/SC2)
# ──────────────────────────────────────────────────────────────────────────


def _fallback_synoptic_frame() -> pd.DataFrame:
    """
    A Synoptic-shaped frame with no `lat` column -- deliberately, so
    `_supplement_with_asos` takes its "no 'lat' column" skip branch and
    these fallback tests never attempt a live ASOS network call.
    """
    return _synthetic_frame(
        air_temp=[24.0, 24.5],
        wind_speed=[4.0, 4.2],
        wind_direction=[180.0, 182.0],
    )


def test_tceq_failure_triggers_fallback_and_returns_a_usable_synoptic_frame(monkeypatch):
    def _raise_tceq(*a, **k):
        raise ValueError("TCEQ boom")

    monkeypatch.setattr(tceq_provider, "fetch_tceq", _raise_tceq)
    monkeypatch.setattr(
        dlr_pipeline, "fetch_timeseries", lambda *a, **k: _fallback_synoptic_frame()
    )

    result = weather_provider.fetch_weather(["83"], _START, _END, provider="tceq")

    assert not result.empty
    assert (result["wind_source"] == "synoptic").all()
    assert (result["temp_source"] == "synoptic").all()
    for col in ("wind_source", "temp_source", "humidity_source", "solar_source"):
        assert not (result[col] == "tceq").any()


def test_tceq_fallback_disabled_reproduces_the_original_raise(monkeypatch):
    def _raise_tceq(*a, **k):
        raise ValueError("TCEQ boom")

    monkeypatch.setattr(tceq_provider, "fetch_tceq", _raise_tceq)

    counter = {"count": 0}

    def _counting_fetch_timeseries(*a, **k):
        counter["count"] += 1
        return _fallback_synoptic_frame()

    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", _counting_fetch_timeseries)

    with pytest.raises(ValueError) as excinfo:
        weather_provider.fetch_weather(
            ["83"], _START, _END, provider="tceq", fallback=False
        )

    assert "TCEQ boom" in str(excinfo.value)
    assert counter["count"] == 0


def test_tceq_success_does_not_invoke_fallback(monkeypatch):
    monkeypatch.setattr(tceq_provider, "fetch_tceq", lambda *a, **k: _tceq_frame())

    counter = {"count": 0}

    def _counting_fetch_timeseries(*a, **k):
        counter["count"] += 1
        return _fallback_synoptic_frame()

    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", _counting_fetch_timeseries)

    result = weather_provider.fetch_weather(["83"], _START, _END, provider="tceq")

    assert (result["temp_source"] == "tceq").all()
    assert counter["count"] == 0


def test_tceq_empty_result_triggers_fallback(monkeypatch):
    monkeypatch.setattr(tceq_provider, "fetch_tceq", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(
        dlr_pipeline, "fetch_timeseries", lambda *a, **k: _fallback_synoptic_frame()
    )

    result = weather_provider.fetch_weather(["83"], _START, _END, provider="tceq")

    assert not result.empty
    assert (result["temp_source"] == "synoptic").all()


def test_fallback_failure_after_tceq_failure_chains_the_original_tceq_error(monkeypatch):
    tceq_error = ValueError("TCEQ boom")

    def _raise_tceq(*a, **k):
        raise tceq_error

    def _raise_synoptic(*a, **k):
        raise ValueError("Synoptic boom")

    monkeypatch.setattr(tceq_provider, "fetch_tceq", _raise_tceq)
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", _raise_synoptic)

    with pytest.raises(ValueError) as excinfo:
        weather_provider.fetch_weather(["83"], _START, _END, provider="tceq")

    message = str(excinfo.value)
    assert "tceq" in message
    assert "synoptic" in message
    assert excinfo.value.__cause__ is tceq_error
