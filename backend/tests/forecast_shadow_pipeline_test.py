"""
Tests for the experimental/shadow forecast-correction prototype
(`backend/forecast_shadow_pipeline.py`). Network-free throughout except
where explicitly noted; this module is never invoked by production code,
so these tests exercise it directly.
"""

import numpy as np
import pandas as pd
import pytest

import config
import corridor_discretization
import forecast_correction_models
import forecast_shadow_pipeline as shadow
import weather_provider

_CORRIDOR = "AUSTIN_CORPUS_CHRISTI"


def _synthetic_wind_fit_frame(n=80, seed=1):
    rng = np.random.default_rng(seed)
    geometry = corridor_discretization.corridor_geometry(_CORRIDOR)
    cities = list(geometry.endpoints) if hasattr(geometry, "endpoints") else [_CORRIDOR + "_A", _CORRIDOR + "_B"]
    ts = pd.date_range("2024-01-01", periods=n, freq="6h", tz="UTC")
    rows = []
    for i in range(n):
        city = cities[i % 2] if len(cities) >= 2 else "CITY"
        rows.append({
            "datetime_utc": ts[i],
            "endpoint_city": city,
            "fcst_wind_speed": rng.uniform(1.0, 10.0),
            "fcst_wind_direction": rng.uniform(0.0, 360.0),
            "fcst_air_temp": rng.uniform(10.0, 35.0),
            "fcst_solar_radiation": rng.uniform(0.0, 800.0),
            "anchor_wind_speed": rng.uniform(1.0, 10.0),
            "anchor_wind_direction": rng.uniform(0.0, 360.0),
            "truth_wind_speed": rng.uniform(1.0, 10.0),
            "truth_wind_direction": rng.uniform(0.0, 360.0),
        })
    return pd.DataFrame(rows)


def _synthetic_row(**overrides):
    base = {
        "fcst_air_temp": 28.0,
        "fcst_wind_speed": 4.5,
        "fcst_wind_direction": 120.0,
        "fcst_solar_radiation": 600.0,
        "anchor_wind_speed": 4.0,
        "anchor_wind_direction": 110.0,
        "datetime_utc": pd.Timestamp("2026-10-05T18:00:00Z"),
        "endpoint_city": "CITY",
    }
    base.update(overrides)
    return pd.Series(base)


def test_shadow_timestamps_as_dict_keeps_four_fields_distinct():
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-04T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-04T06:00:00Z"),
        decision_time=pd.Timestamp("2026-10-04T12:00:00Z"),
        valid_time=pd.Timestamp("2026-10-05T00:00:00Z"),
        horizon_minutes=1440,
    )
    d = ts.as_dict()
    assert len({d["initialization_time"], d["availability_time"], d["decision_time"], d["valid_time"]}) == 4
    assert d["horizon_minutes"] == 1440


def test_fetch_live_forecast_rejects_a_run_not_yet_available_without_any_network_call(monkeypatch):
    def _should_not_be_called(*a, **k):
        raise AssertionError("fetch_single_run must not be called once the availability check fails")

    import open_meteo_forecast_provider
    monkeypatch.setattr(open_meteo_forecast_provider, "fetch_single_run", _should_not_be_called)

    far_future_valid_time = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=3650)
    with pytest.raises(shadow.StaleOrMissingDataError, match="availability_time"):
        shadow.fetch_live_forecast_for_valid_time(
            _CORRIDOR, far_future_valid_time, horizon_minutes=1,
            lat=30.27, lon=-97.74,
        )


def test_fetch_live_forecast_wraps_single_run_unavailable(monkeypatch):
    import open_meteo_forecast_provider

    def _raise_unavailable(*a, **k):
        raise open_meteo_forecast_provider.SingleRunUnavailable("no such run")

    monkeypatch.setattr(open_meteo_forecast_provider, "fetch_single_run", _raise_unavailable)

    past_valid_time = pd.Timestamp("2026-01-01T00:00:00Z")
    with pytest.raises(shadow.StaleOrMissingDataError, match="unavailable"):
        shadow.fetch_live_forecast_for_valid_time(
            _CORRIDOR, past_valid_time, horizon_minutes=1440,
            lat=30.27, lon=-97.74,
        )


def test_validate_and_prepare_shadow_row_accepts_a_good_row_and_attaches_uv():
    row = _synthetic_row()
    frame = shadow.validate_and_prepare_shadow_row(row, corridor=_CORRIDOR)
    assert "fcst_wind_u" in frame.columns and "fcst_wind_v" in frame.columns
    assert frame.attrs["geometry"] is not None


def test_validate_and_prepare_shadow_row_rejects_missing_field():
    row = _synthetic_row()
    row = row.drop("fcst_air_temp")
    with pytest.raises(ValueError, match="missing/null"):
        shadow.validate_and_prepare_shadow_row(row, corridor=_CORRIDOR)


def test_validate_and_prepare_shadow_row_rejects_negative_wind_speed():
    row = _synthetic_row(fcst_wind_speed=-1.0)
    with pytest.raises(ValueError, match="negative"):
        shadow.validate_and_prepare_shadow_row(row, corridor=_CORRIDOR)


def test_validate_and_prepare_shadow_row_rejects_implausible_temperature():
    row = _synthetic_row(fcst_air_temp=200.0)
    with pytest.raises(ValueError, match="outside"):
        shadow.validate_and_prepare_shadow_row(row, corridor=_CORRIDOR)


def test_validate_and_prepare_shadow_row_rejects_unknown_corridor():
    row = _synthetic_row()
    with pytest.raises(KeyError):
        shadow.validate_and_prepare_shadow_row(row, corridor="NOT_A_REAL_CORRIDOR")


def test_raw_forecast_shadow_method_returns_a_positive_ampacity():
    geometry = corridor_discretization.corridor_geometry(_CORRIDOR)
    row = _synthetic_row()
    frame = pd.DataFrame([row])
    method = shadow.RawForecastShadowMethod()
    amps = method.predict(frame, geometry)
    assert amps > 0.0


def test_wind_correction_shadow_method_round_trips_through_a_fitted_model():
    fit_frame = _synthetic_wind_fit_frame()
    model = forecast_correction_models.fit_wind_correction(
        fit_frame, forecast_correction_models._make_wind_linear_regression, pooling="per_city",
    )
    geometry = corridor_discretization.corridor_geometry(_CORRIDOR)
    row = _synthetic_row(endpoint_city=fit_frame["endpoint_city"].iloc[0])
    frame = pd.DataFrame([row])
    method = shadow.WindCorrectionShadowMethod(model)
    amps = method.predict(frame, geometry)
    assert amps > 0.0


def test_save_and_load_correction_model_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))
    fit_frame = _synthetic_wind_fit_frame()
    model = forecast_correction_models.fit_wind_correction(
        fit_frame, forecast_correction_models._make_wind_linear_regression, pooling="per_city",
    )
    path = shadow.save_correction_model(model, _CORRIDOR, "ml_wind_corrected")
    assert path.startswith(str(tmp_path))
    loaded = shadow.load_correction_model(_CORRIDOR, "ml_wind_corrected")
    assert loaded.feature_names == model.feature_names


def test_load_correction_model_raises_with_training_hint_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="fit_wind_correction"):
        shadow.load_correction_model(_CORRIDOR, "ml_wind_corrected")


class _AlwaysFailsMethod:
    name = "sabotaged"

    def predict(self, frame, geometry):
        raise RuntimeError("deliberate failure for the fallback test")


def test_shadow_pipeline_falls_back_on_primary_method_failure():
    pipeline = shadow.ShadowPipeline(_CORRIDOR, _AlwaysFailsMethod())
    row = _synthetic_row()
    frame = pd.DataFrame([row])
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-04T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-04T06:00:00Z"),
        decision_time=pd.Timestamp("2026-10-04T12:00:00Z"),
        valid_time=pd.Timestamp("2026-10-05T00:00:00Z"),
        horizon_minutes=1440,
    )
    prediction = pipeline.predict(frame, ts)
    assert prediction.fallback_used is True
    assert prediction.method == "raw_forecast"
    assert "deliberate failure" in prediction.fallback_reason
    assert prediction.ampacity_amps > 0.0


def test_shadow_pipeline_no_fallback_when_primary_succeeds():
    pipeline = shadow.ShadowPipeline(_CORRIDOR, shadow.RawForecastShadowMethod())
    row = _synthetic_row()
    frame = pd.DataFrame([row])
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-04T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-04T06:00:00Z"),
        decision_time=pd.Timestamp("2026-10-04T12:00:00Z"),
        valid_time=pd.Timestamp("2026-10-05T00:00:00Z"),
        horizon_minutes=1440,
    )
    prediction = pipeline.predict(frame, ts)
    assert prediction.fallback_used is False
    assert prediction.method == "raw_forecast"


def test_log_prediction_writes_a_json_line_with_basis_caveat(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    pipeline = shadow.ShadowPipeline(_CORRIDOR, shadow.RawForecastShadowMethod())
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-04T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-04T06:00:00Z"),
        decision_time=pd.Timestamp("2026-10-04T12:00:00Z"),
        valid_time=pd.Timestamp("2026-10-05T00:00:00Z"),
        horizon_minutes=1440,
    )
    prediction = shadow.ShadowPrediction(
        corridor=_CORRIDOR, method="raw_forecast", ampacity_amps=500.0,
        timestamps=ts, fallback_used=False,
    )
    path = pipeline.log_prediction(prediction)
    import json
    with open(path) as fh:
        record = json.loads(fh.readline())
    assert record["ampacity_amps"] == 500.0
    assert "reanalysis" in record["basis_caveat"].lower() or "Reanalysis" in record["basis_caveat"]
    assert record["decision_time"] == ts.decision_time.isoformat()


def test_fetch_live_forecast_renames_provider_columns_to_fcst_prefix(monkeypatch):
    """
    Regression test for a real bug found by an actual live-network run of
    this module (pre-confirmation readiness pass, 2026-10-05): the raw
    provider returns `air_temp`/`wind_speed`/... (no prefix), but
    `validate_and_prepare_shadow_row` and the correction models' feature
    builders require `fcst_air_temp`/`fcst_wind_speed`/.... Every prior
    test in this file passed `_synthetic_row()`'s already-prefixed columns
    directly, so none of them could have caught this -- only an actual
    live invocation surfaced it.
    """
    import open_meteo_forecast_provider

    def _fake_fetch_single_run(lat, lon, run, forecast_days=None, **kwargs):
        return pd.DataFrame([{
            "datetime_utc": run + pd.Timedelta(hours=6),
            "air_temp": 22.5, "wind_speed": 3.1, "wind_direction": 200.0,
            "solar_radiation": 450.0, "relative_humidity": 60.0,
        }])

    monkeypatch.setattr(open_meteo_forecast_provider, "fetch_single_run", _fake_fetch_single_run)

    valid_time = pd.Timestamp("2026-01-02T06:00:00Z")
    row, ts = shadow.fetch_live_forecast_for_valid_time(
        _CORRIDOR, valid_time, horizon_minutes=1440, lat=30.27, lon=-97.74,
    )
    for col in ("fcst_air_temp", "fcst_wind_speed", "fcst_wind_direction", "fcst_solar_radiation"):
        assert col in row.index, f"{col} missing after rename -- provider's raw column survived unrenamed"
    assert "air_temp" not in row.index, "raw provider column name should not survive alongside the renamed one"
    # The renamed row must also satisfy validate_and_prepare_shadow_row directly.
    frame = shadow.validate_and_prepare_shadow_row(row, corridor=_CORRIDOR)
    assert frame["fcst_air_temp"].iloc[0] == 22.5


def test_shadow_pipeline_rejects_unevaluated_horizon_before_attempting_fallback():
    """
    horizon_minutes must be a hard rejection (UnsupportedHorizonError),
    never something the fallback machinery could silently absorb into a
    raw_forecast answer a caller might mistake for a correction-model result.
    """
    pipeline = shadow.ShadowPipeline(_CORRIDOR, shadow.RawForecastShadowMethod())
    row = _synthetic_row()
    frame = pd.DataFrame([row])
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-04T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-04T06:00:00Z"),
        decision_time=pd.Timestamp("2026-10-04T12:00:00Z"),
        valid_time=pd.Timestamp("2026-10-04T13:00:00Z"),
        horizon_minutes=60,  # never evaluated -- only 1440 has evidence behind it
    )
    with pytest.raises(shadow.UnsupportedHorizonError, match="60"):
        pipeline.predict(frame, ts)


def test_shadow_pipeline_accepts_the_one_evaluated_horizon():
    assert shadow.EVALUATED_HORIZONS_MINUTES == (1440,)
    pipeline = shadow.ShadowPipeline(_CORRIDOR, shadow.RawForecastShadowMethod())
    row = _synthetic_row()
    frame = pd.DataFrame([row])
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-04T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-04T06:00:00Z"),
        decision_time=pd.Timestamp("2026-10-04T12:00:00Z"),
        valid_time=pd.Timestamp("2026-10-05T12:00:00Z"),
        horizon_minutes=1440,
    )
    prediction = pipeline.predict(frame, ts)
    assert prediction.fallback_used is False


# ──────────────────────────────────────────────────────────────────────
# 2026-10-06 pass: complete the wind-corrected live path (no fallback).
# These tests close the exact gap a real live run surfaced: the
# wind-correction model's feature frame needs a live anchor observation
# that nothing upstream of this pass ever supplied.
# ──────────────────────────────────────────────────────────────────────

def _synthetic_wind_fit_frame_real_cities(n=80, seed=1):
    """
    Same shape as `_synthetic_wind_fit_frame`, but keyed on `_CORRIDOR`'s
    REAL endpoint city names (`config.CORRIDOR_ENDPOINTS`) rather than
    `_CORRIDOR + "_A"/"_B"` placeholders -- needed for tests that also
    call `fetch_live_anchor_observation`, which looks the city up in
    `config.SYNOPTIC_FALLBACK_STATIONS` and only knows real city names.
    """
    rng = np.random.default_rng(seed)
    cities = list(config.CORRIDOR_ENDPOINTS[_CORRIDOR])
    ts = pd.date_range("2024-01-01", periods=n, freq="6h", tz="UTC")
    rows = []
    for i in range(n):
        rows.append({
            "datetime_utc": ts[i],
            "endpoint_city": cities[i % 2],
            "fcst_wind_speed": rng.uniform(1.0, 10.0),
            "fcst_wind_direction": rng.uniform(0.0, 360.0),
            "fcst_air_temp": rng.uniform(10.0, 35.0),
            "fcst_solar_radiation": rng.uniform(0.0, 800.0),
            "anchor_wind_speed": rng.uniform(1.0, 10.0),
            "anchor_wind_direction": rng.uniform(0.0, 360.0),
            "truth_wind_speed": rng.uniform(1.0, 10.0),
            "truth_wind_direction": rng.uniform(0.0, 360.0),
        })
    return pd.DataFrame(rows)


def _fake_synoptic_observation(station, air_temp=27.5, wind_speed=5.2, wind_direction=135.0):
    def _fetch(location, start, end, provider="synoptic", **kw):
        assert location == [station]
        end_ts = pd.Timestamp(end)
        idx = pd.MultiIndex.from_tuples([(station, end_ts)], names=["stid", "datetime_utc"])
        return pd.DataFrame(
            {
                "air_temp": [air_temp], "wind_speed": [wind_speed],
                "wind_direction": [wind_direction], "solar_radiation": [410.0],
                "relative_humidity": [48.0],
            },
            index=idx,
        )
    return _fetch


def test_fetch_live_anchor_observation_returns_the_latest_row_before_decision_time(monkeypatch):
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_synoptic_observation("KAUS"))
    decision_time = pd.Timestamp("2026-10-06T12:00:00Z")
    anchor = shadow.fetch_live_anchor_observation("AUSTIN", decision_time)
    assert anchor["anchor_wind_speed"] == 5.2
    assert anchor["anchor_wind_direction"] == 135.0
    assert anchor["anchor_source"] == "synoptic"
    assert anchor["anchor_station"] == "KAUS"


def test_fetch_live_anchor_observation_rejects_unknown_city():
    with pytest.raises(shadow.StaleOrMissingDataError, match="no known live station"):
        shadow.fetch_live_anchor_observation("NOT_A_REAL_CITY", pd.Timestamp("2026-10-06T12:00:00Z"))


def test_fetch_live_anchor_observation_wraps_a_failed_fetch(monkeypatch):
    def _raise(*a, **kw):
        raise OSError("Set SYNOPTIC_TOKEN env var.")
    monkeypatch.setattr(weather_provider, "fetch_weather", _raise)
    with pytest.raises(shadow.StaleOrMissingDataError, match="live observation fetch failed"):
        shadow.fetch_live_anchor_observation("AUSTIN", pd.Timestamp("2026-10-06T12:00:00Z"))


def test_fetch_live_anchor_observation_rejects_empty_response(monkeypatch):
    monkeypatch.setattr(weather_provider, "fetch_weather", lambda *a, **kw: pd.DataFrame())
    with pytest.raises(shadow.StaleOrMissingDataError, match="no observation rows"):
        shadow.fetch_live_anchor_observation("AUSTIN", pd.Timestamp("2026-10-06T12:00:00Z"))


def test_attach_wind_correction_inputs_populates_every_feature_frame_column(monkeypatch):
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_synoptic_observation("KAUS"))
    row = _synthetic_row()
    frame = pd.DataFrame([row]).drop(columns=["anchor_wind_speed", "anchor_wind_direction"])
    enriched = shadow.attach_wind_correction_inputs(
        frame, endpoint_city="AUSTIN",
        valid_time=pd.Timestamp("2026-10-07T00:00:00Z"),
        decision_time=pd.Timestamp("2026-10-06T12:00:00Z"),
    )
    assert enriched["anchor_wind_speed"].iloc[0] == 5.2
    assert enriched["anchor_wind_direction"].iloc[0] == 135.0
    assert enriched["endpoint_city"].iloc[0] == "AUSTIN"
    assert enriched["datetime_utc"].iloc[0] == pd.Timestamp("2026-10-07T00:00:00Z")
    assert enriched.attrs["anchor_source"] == "synoptic"
    assert enriched.attrs["anchor_station"] == "KAUS"
    # The real feature builder must accept this frame with no missing column.
    features = forecast_correction_models._wind_feature_frame(enriched, pooling="per_city")
    assert not features.isnull().any().any()


def test_wind_correction_shadow_method_completes_live_path_with_no_fallback_when_anchor_available(monkeypatch):
    """
    Positive control for the exact gap a real live run surfaced: given a
    working anchor source, the wind-corrected method must complete its
    real predictive path -- not merely avoid crashing.
    """
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_synoptic_observation("KAUS"))
    fit_frame = _synthetic_wind_fit_frame_real_cities()
    model = forecast_correction_models.fit_wind_correction(
        fit_frame, forecast_correction_models._make_wind_linear_regression, pooling="per_city",
    )
    geometry = corridor_discretization.corridor_geometry(_CORRIDOR)
    endpoint_city = config.CORRIDOR_ENDPOINTS[_CORRIDOR][0]
    row = _synthetic_row(endpoint_city=endpoint_city)
    frame = pd.DataFrame([row]).drop(columns=["anchor_wind_speed", "anchor_wind_direction"])

    method = shadow.WindCorrectionShadowMethod(
        model, model_version="test-version",
        endpoint_city=endpoint_city,
        valid_time=pd.Timestamp("2026-10-07T00:00:00Z"),
        decision_time=pd.Timestamp("2026-10-06T12:00:00Z"),
    )
    amps = method.predict(frame, geometry)
    assert amps > 0.0


def test_shadow_pipeline_falls_back_explicitly_when_anchor_source_unavailable(monkeypatch):
    """
    Negative control: a missing/failed anchor source (e.g. no
    SYNOPTIC_TOKEN) must be caught by the pipeline's existing fail-safe
    fallback machinery -- a named, traceable fallback, never a crash and
    never a silent success.
    """
    def _raise(*a, **kw):
        raise OSError("Set SYNOPTIC_TOKEN env var.")
    monkeypatch.setattr(weather_provider, "fetch_weather", _raise)

    fit_frame = _synthetic_wind_fit_frame_real_cities()
    model = forecast_correction_models.fit_wind_correction(
        fit_frame, forecast_correction_models._make_wind_linear_regression, pooling="per_city",
    )
    endpoint_city = config.CORRIDOR_ENDPOINTS[_CORRIDOR][0]
    row = _synthetic_row(endpoint_city=endpoint_city)
    frame = pd.DataFrame([row]).drop(columns=["anchor_wind_speed", "anchor_wind_direction"])
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-06T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-06T06:00:00Z"),
        decision_time=pd.Timestamp("2026-10-06T12:00:00Z"),
        valid_time=pd.Timestamp("2026-10-07T00:00:00Z"),
        horizon_minutes=1440,
    )
    method = shadow.WindCorrectionShadowMethod(
        model, endpoint_city=endpoint_city,
        valid_time=ts.valid_time, decision_time=ts.decision_time,
    )
    pipeline = shadow.ShadowPipeline(_CORRIDOR, method)
    prediction = pipeline.predict(frame, ts)
    assert prediction.fallback_used is True
    assert prediction.method == "raw_forecast"
    assert "SYNOPTIC_TOKEN" in prediction.fallback_reason
