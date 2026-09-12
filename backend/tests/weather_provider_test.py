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

import asos_provider
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
