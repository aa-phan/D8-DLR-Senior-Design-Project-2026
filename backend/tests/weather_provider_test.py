"""
Tests for backend/weather_provider.py's provenance layer (C4 / Plan 06-01).

Proves the thin vertical slice end to end: schema layer (units_def.py v3)
-> validator layer (validate_pipeline_row's categorical branch) -> adapter
layer (weather_provider.attach_provenance) -> caller-visible output
(fetch_weather's station path). Follows
backend/tests/corridor_discretization_test.py's convention (module-level
imports, plain asserts, no test classes) and
backend/tests/dlr_pipeline_test.py's `monkeypatch.setattr(dlr_pipeline,
"fetch_timeseries", ...)` convention for avoiding a live network call.
"""

import pandas as pd
import pytest

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
