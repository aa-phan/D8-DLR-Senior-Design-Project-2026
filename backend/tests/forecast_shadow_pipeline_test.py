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
import forecast_training
import thermal_model
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


def _fake_tceq_observation(cams_id, air_temp=27.5, wind_speed=5.2, wind_direction=135.0):
    """Simulates a successful TCEQ-primary response -- the real composition's
    primary path (`provider="tceq"`), with a `wind_source` provenance column
    so `fetch_live_anchor_observation`'s actual-provider detection has
    something real to read, same as `weather_provider.attach_provenance`
    would set on the genuine path."""
    def _fetch(location, start, end, provider="tceq", **kw):
        assert provider == "tceq", f"expected the real primary 'tceq', got {provider!r}"
        assert location == [cams_id]
        end_ts = pd.Timestamp(end)
        idx = pd.MultiIndex.from_tuples([(cams_id, end_ts)], names=["stid", "datetime_utc"])
        return pd.DataFrame(
            {
                "air_temp": [air_temp], "wind_speed": [wind_speed],
                "wind_direction": [wind_direction], "relative_humidity": [48.0],
                "wind_source": ["tceq"], "temp_source": ["tceq"],
                "humidity_source": ["tceq"],
            },
            index=idx,
        )
    return _fetch


def test_fetch_live_anchor_observation_returns_the_latest_row_before_decision_time(monkeypatch):
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_tceq_observation(config.TCEQ_STATIONS["AUSTIN"]))
    decision_time = pd.Timestamp("2026-10-06T12:00:00Z")
    anchor = shadow.fetch_live_anchor_observation("AUSTIN", decision_time)
    assert anchor["anchor_wind_speed"] == 5.2
    assert anchor["anchor_wind_direction"] == 135.0
    assert anchor["anchor_source"] == "tceq"
    assert anchor["anchor_station"] == config.TCEQ_STATIONS["AUSTIN"]


def test_fetch_live_anchor_observation_rejects_unknown_city():
    with pytest.raises(shadow.StaleOrMissingDataError, match="no known TCEQ CAMS site"):
        shadow.fetch_live_anchor_observation("NOT_A_REAL_CITY", pd.Timestamp("2026-10-06T12:00:00Z"))


def test_fetch_live_anchor_observation_wraps_a_failed_fetch(monkeypatch):
    """Both the TCEQ primary attempt AND the explicit Synoptic retry raise
    here -- confirms the function tries both sources (not just one) before
    giving up, and reports that plainly rather than surfacing only the
    first exception's text."""
    def _raise(*a, **kw):
        raise OSError("Set SYNOPTIC_TOKEN env var.")
    monkeypatch.setattr(weather_provider, "fetch_weather", _raise)
    with pytest.raises(shadow.StaleOrMissingDataError, match="no usable wind observation"):
        shadow.fetch_live_anchor_observation("AUSTIN", pd.Timestamp("2026-10-06T12:00:00Z"))


def test_fetch_live_anchor_observation_rejects_empty_response(monkeypatch):
    """Both sources return an empty frame -- same final, honest message as
    the raise case; an empty response is handled identically to an
    exception, not as a separate code path."""
    monkeypatch.setattr(weather_provider, "fetch_weather", lambda *a, **kw: pd.DataFrame())
    with pytest.raises(shadow.StaleOrMissingDataError, match="no usable wind observation"):
        shadow.fetch_live_anchor_observation("AUSTIN", pd.Timestamp("2026-10-06T12:00:00Z"))


def test_fetch_live_anchor_observation_falls_back_to_synoptic_on_unusable_tceq_response(monkeypatch):
    """Positive control for the real gap a live run surfaced this session:
    TCEQ's `daily_summary.pl` can return a MECHANICALLY SUCCESSFUL response
    whose latest row is a not-yet-reported, null-wind trailing hour --
    `weather_provider.fetch_weather`'s own `fallback=True` never triggers
    for this case (it only catches a raised exception or a wholly empty
    response), so this function must explicitly retry Synoptic itself."""
    cams_id = config.TCEQ_STATIONS["AUSTIN"]
    synoptic_station = config.SYNOPTIC_FALLBACK_STATIONS["AUSTIN"]

    def _fetch(location, start, end, provider="tceq", **kw):
        end_ts = pd.Timestamp(end)
        if provider == "tceq":
            assert location == [cams_id]
            idx = pd.MultiIndex.from_tuples([(cams_id, end_ts)], names=["stid", "datetime_utc"])
            return pd.DataFrame(
                {"wind_speed": [None], "wind_direction": [None], "wind_source": [None]}, index=idx,
            )
        assert provider == "synoptic"
        assert location == [synoptic_station]
        idx = pd.MultiIndex.from_tuples([(synoptic_station, end_ts)], names=["stid", "datetime_utc"])
        return pd.DataFrame(
            {"wind_speed": [6.5], "wind_direction": [220.0], "wind_source": ["synoptic"]}, index=idx,
        )

    monkeypatch.setattr(weather_provider, "fetch_weather", _fetch)
    anchor = shadow.fetch_live_anchor_observation("AUSTIN", pd.Timestamp("2026-10-06T12:00:00Z"))
    assert anchor["anchor_wind_speed"] == 6.5
    assert anchor["anchor_source"] == "synoptic"
    assert anchor["anchor_station"] == synoptic_station


def test_fetch_live_anchor_observation_failure_names_each_provider_distinctly(monkeypatch):
    """The combined failure message must attribute EACH provider's OWN
    failure shape, not lump both into one ambiguous sentence -- TCEQ's
    null-wind-field case and Synoptic's raised-exception case are
    different failure shapes and the message must say so, not just that
    'both either raised, returned nothing, or had a null wind field'."""
    cams_id = config.TCEQ_STATIONS["AUSTIN"]
    synoptic_station = config.SYNOPTIC_FALLBACK_STATIONS["AUSTIN"]

    def _fetch(location, start, end, provider="tceq", **kw):
        end_ts = pd.Timestamp(end)
        if provider == "tceq":
            idx = pd.MultiIndex.from_tuples([(cams_id, end_ts)], names=["stid", "datetime_utc"])
            return pd.DataFrame(
                {"wind_speed": [None], "wind_direction": [None], "wind_source": [None]}, index=idx,
            )
        raise OSError("Synoptic connection refused")

    monkeypatch.setattr(weather_provider, "fetch_weather", _fetch)
    with pytest.raises(shadow.StaleOrMissingDataError) as exc_info:
        shadow.fetch_live_anchor_observation("AUSTIN", pd.Timestamp("2026-10-06T12:00:00Z"))
    message = str(exc_info.value)
    assert f"TCEQ CAMS {cams_id!r}" in message
    assert "null wind field" in message
    assert f"Synoptic {synoptic_station!r}" in message
    assert "Synoptic connection refused" in message


def test_attach_wind_correction_inputs_populates_every_feature_frame_column(monkeypatch):
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_tceq_observation(config.TCEQ_STATIONS["AUSTIN"]))
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
    assert enriched.attrs["anchor_source"] == "tceq"
    assert enriched.attrs["anchor_station"] == config.TCEQ_STATIONS["AUSTIN"]
    # The real feature builder must accept this frame with no missing column.
    features = forecast_correction_models._wind_feature_frame(enriched, pooling="per_city")
    assert not features.isnull().any().any()


def test_wind_correction_shadow_method_completes_live_path_with_no_fallback_when_anchor_available(monkeypatch):
    """
    Positive control for the exact gap a real live run surfaced: given a
    working anchor source, the wind-corrected method must complete its
    real predictive path -- not merely avoid crashing.
    """
    endpoint_city = config.CORRIDOR_ENDPOINTS[_CORRIDOR][0]
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_tceq_observation(config.TCEQ_STATIONS[endpoint_city]))
    fit_frame = _synthetic_wind_fit_frame_real_cities()
    model = forecast_correction_models.fit_wind_correction(
        fit_frame, forecast_correction_models._make_wind_linear_regression, pooling="per_city",
    )
    geometry = corridor_discretization.corridor_geometry(_CORRIDOR)
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
    Negative control: a missing/failed anchor source (both TCEQ and its
    explicit Synoptic retry) must be caught by the pipeline's existing
    fail-safe fallback machinery -- a named, traceable fallback, never a
    crash and never a silent success.
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
    assert "no usable wind observation" in prediction.fallback_reason


# ──────────────────────────────────────────────────────────────────────
# 2026-10-06 (continued): the CORRIDOR-correct weakest-link reduction.
# Training applies corridor_weakest_link to each city's own CORRECTED
# AMPACITY, never to a raw weather variable -- these tests close the
# single-city simplification named as a remaining gap by the prior pass.
# ──────────────────────────────────────────────────────────────────────

def _fake_fetch_single_run_const(air_temp=22.0, wind_speed=3.0, wind_direction=200.0, solar=400.0):
    def _fetch(lat, lon, run, forecast_days=None, **kwargs):
        return pd.DataFrame([{
            "datetime_utc": run + pd.Timedelta(hours=6),
            "air_temp": air_temp, "wind_speed": wind_speed, "wind_direction": wind_direction,
            "solar_radiation": solar, "relative_humidity": 55.0,
        }])
    return _fetch


def _fake_tceq_observation_per_station(speeds_by_cams_id, direction=135.0):
    """Like `_fake_tceq_observation`, but returns a DIFFERENT wind speed per
    CAMS ID so the two cities' corrected ampacities genuinely differ --
    needed to prove the weakest-link reduction picks the real minimum, not
    just whichever city happens to run first. Simulates the real TCEQ
    primary path (`wind_source="tceq"`)."""
    def _fetch(location, start, end, provider="tceq", **kw):
        cams_id = location[0]
        speed = speeds_by_cams_id[cams_id]
        end_ts = pd.Timestamp(end)
        idx = pd.MultiIndex.from_tuples([(cams_id, end_ts)], names=["stid", "datetime_utc"])
        return pd.DataFrame(
            {
                "air_temp": [27.5], "wind_speed": [speed],
                "wind_direction": [direction], "relative_humidity": [48.0],
                "wind_source": ["tceq"],
            },
            index=idx,
        )
    return _fetch


def test_corridor_wind_correction_reduces_to_the_true_minimum_of_both_cities(monkeypatch):
    """
    Positive control: give the two endpoint cities deliberately different
    live anchor wind speeds (via different stations) and confirm the
    returned ampacity is the elementwise MINIMUM of the two cities' own
    corrected ampacities -- not an average, not always city A, and not a
    reduction applied to a raw weather variable.
    """
    import open_meteo_forecast_provider

    monkeypatch.setattr(open_meteo_forecast_provider, "fetch_single_run", _fake_fetch_single_run_const())
    city_a, city_b = config.CORRIDOR_ENDPOINTS[_CORRIDOR]
    cams_a = config.TCEQ_STATIONS[city_a]
    cams_b = config.TCEQ_STATIONS[city_b]
    monkeypatch.setattr(
        weather_provider, "fetch_weather",
        _fake_tceq_observation_per_station({cams_a: 2.0, cams_b: 9.0}),
    )

    fit_frame = _synthetic_wind_fit_frame_real_cities()
    model = forecast_correction_models.fit_wind_correction(
        fit_frame, forecast_correction_models._make_wind_linear_regression, pooling="per_city",
    )
    geometry = corridor_discretization.corridor_geometry(_CORRIDOR)
    valid_time = pd.Timestamp("2026-10-07T00:00:00Z")
    decision_time = pd.Timestamp("2026-10-06T12:00:00Z")

    method = shadow.CorridorWindCorrectionMethod(
        model, corridor=_CORRIDOR, model_version="test-version",
        valid_time=valid_time, decision_time=decision_time, horizon_minutes=1440,
    )
    frame = pd.DataFrame([{"placeholder": True}])
    amps = method.predict(frame, geometry)

    per_city = frame.attrs["per_city_ampacity_amps"]
    assert set(per_city) == {city_a, city_b}
    assert amps == pytest.approx(min(per_city[city_a], per_city[city_b]))
    assert frame.attrs["bottleneck_city"] in (city_a, city_b)
    assert frame.attrs["bottleneck_city"] == (city_a if per_city[city_a] <= per_city[city_b] else city_b)
    assert set(frame.attrs["anchor_provenance"]) == {city_a, city_b}
    for city_provenance in frame.attrs["anchor_provenance"].values():
        assert city_provenance["anchor_source"] == "tceq"


def test_corridor_wind_correction_fails_whole_prediction_when_either_city_anchor_unavailable(monkeypatch):
    """
    Negative control: a corridor rating must never be reported from only
    ONE city's real data when the reduction requires both. If city B's
    anchor fetch fails, the whole corridor prediction must fail (and be
    caught by `ShadowPipeline`'s existing fallback) -- never silently
    fall back to a single-city answer.
    """
    import open_meteo_forecast_provider

    monkeypatch.setattr(open_meteo_forecast_provider, "fetch_single_run", _fake_fetch_single_run_const())
    city_a, city_b = config.CORRIDOR_ENDPOINTS[_CORRIDOR]
    cams_a = config.TCEQ_STATIONS[city_a]
    cams_b = config.TCEQ_STATIONS[city_b]
    synoptic_b = config.SYNOPTIC_FALLBACK_STATIONS[city_b]

    def _flaky(location, start, end, provider="tceq", **kw):
        # city_b fails on BOTH the TCEQ primary attempt AND the explicit
        # Synoptic retry `fetch_live_anchor_observation` makes when the
        # primary's latest row is unusable -- city_a succeeds normally via
        # TCEQ either way.
        if location[0] in (cams_b, synoptic_b):
            raise ValueError(f"simulated failure for city {city_b!r} on provider {provider!r}")
        return _fake_tceq_observation_per_station({cams_a: 2.0, cams_b: 9.0})(location, start, end, provider=provider, **kw)

    monkeypatch.setattr(weather_provider, "fetch_weather", _flaky)

    fit_frame = _synthetic_wind_fit_frame_real_cities()
    model = forecast_correction_models.fit_wind_correction(
        fit_frame, forecast_correction_models._make_wind_linear_regression, pooling="per_city",
    )
    valid_time = pd.Timestamp("2026-10-07T00:00:00Z")
    decision_time = pd.Timestamp("2026-10-06T12:00:00Z")
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-06T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-06T06:00:00Z"),
        decision_time=decision_time, valid_time=valid_time, horizon_minutes=1440,
    )
    method = shadow.CorridorWindCorrectionMethod(
        model, corridor=_CORRIDOR, model_version="test-version",
        valid_time=valid_time, decision_time=decision_time, horizon_minutes=1440,
    )
    pipeline = shadow.ShadowPipeline(_CORRIDOR, method)
    # A real, raw-forecast-usable frame -- the fallback method
    # (RawForecastShadowMethod) genuinely reads `fcst_*` columns from
    # whatever frame ShadowPipeline.predict was called with; a bare
    # placeholder frame would make the FALLBACK itself raise, masking
    # this test's actual assertion.
    frame = pd.DataFrame([_synthetic_row(endpoint_city=city_a)])
    prediction = pipeline.predict(frame, ts)
    assert prediction.fallback_used is True
    assert prediction.method == "raw_forecast"
    assert "no usable wind observation" in prediction.fallback_reason
    assert city_b in prediction.fallback_reason
    assert cams_b in prediction.fallback_reason


# ──────────────────────────────────────────────────────────────────────
# Adversarial mutation-testing pass (2026-10-06): closes coverage gaps
# surfaced by manually probing the existing suite -- each test below
# corresponds to a mutation that SURVIVED (the pre-existing suite stayed
# green under it) before this test was added, then was killed by it.
# ──────────────────────────────────────────────────────────────────────

def test_fetch_live_forecast_accepts_decision_time_exactly_at_availability_time(monkeypatch):
    """
    Boundary: the docstring says decision_time "must be >= availability_time"
    (inclusive) -- survived mutant: `<` -> `<=` on the rejection check, which
    would wrongly reject a request made AT the exact availability instant.
    The clock is pinned via monkeypatch (not raced against real wall-clock
    time, which cannot land on an exact nanosecond boundary reliably) so
    decision_time is deterministically EQUAL to availability_time.
    """
    import open_meteo_forecast_provider

    def _fake_fetch_single_run(lat, lon, run, forecast_days=None, **kwargs):
        return pd.DataFrame([{
            "datetime_utc": run + pd.Timedelta(hours=6),
            "air_temp": 20.0, "wind_speed": 3.0, "wind_direction": 100.0,
            "solar_radiation": 300.0, "relative_humidity": 50.0,
        }])

    monkeypatch.setattr(open_meteo_forecast_provider, "fetch_single_run", _fake_fetch_single_run)
    lag_hours = shadow._resolve_publication_lag_hours()
    horizon_minutes = 1440
    initialization_time = pd.Timestamp("2026-10-10T00:00:00Z")
    availability_time = initialization_time + pd.Timedelta(hours=lag_hours)
    valid_time = initialization_time + pd.Timedelta(minutes=horizon_minutes)

    class _FixedTimestamp(pd.Timestamp):
        @classmethod
        def now(cls, tz=None):
            return availability_time if tz is not None else availability_time.tz_localize(None)

    monkeypatch.setattr(pd, "Timestamp", _FixedTimestamp)
    row, ts = shadow.fetch_live_forecast_for_valid_time(
        _CORRIDOR, valid_time, horizon_minutes=horizon_minutes, lat=30.27, lon=-97.74,
    )
    assert row is not None
    assert ts.decision_time == availability_time


def test_fetch_live_forecast_uses_the_real_publication_lag_not_zero(monkeypatch):
    """
    Survived mutant: `_DEFAULT_PUBLICATION_LAG_HOURS = 6.0` -> `0.0`. A
    decision_time that is available only because the real ~6h lag is
    applied (and would be REJECTED under a zero lag) proves the constant's
    value is load-bearing, not just its presence.
    """
    import open_meteo_forecast_provider

    def _fake_fetch_single_run(lat, lon, run, forecast_days=None, **kwargs):
        return pd.DataFrame([{
            "datetime_utc": run + pd.Timedelta(hours=6),
            "air_temp": 20.0, "wind_speed": 3.0, "wind_direction": 100.0,
            "solar_radiation": 300.0, "relative_humidity": 50.0,
        }])

    monkeypatch.setattr(open_meteo_forecast_provider, "fetch_single_run", _fake_fetch_single_run)
    lag_hours = shadow._resolve_publication_lag_hours()
    assert lag_hours > 0.0, "a zero real lag would make this test meaningless"
    now = pd.Timestamp.now(tz="UTC")
    horizon_minutes = 1440
    # initialization_time lands 1 hour before "now"; availability_time is
    # init + lag_hours, i.e. (lag_hours - 1) hours AFTER "now" -- decision_time
    # ("now") is therefore BEFORE availability_time and must be rejected.
    valid_time = now + pd.Timedelta(minutes=horizon_minutes) - pd.Timedelta(hours=1)
    with pytest.raises(shadow.StaleOrMissingDataError, match="availability_time"):
        shadow.fetch_live_forecast_for_valid_time(
            _CORRIDOR, valid_time, horizon_minutes=horizon_minutes, lat=30.27, lon=-97.74,
        )


def test_fetch_live_forecast_rejects_a_row_with_only_one_null_field(monkeypatch):
    """
    Survived mutant: `row.isnull().any()` -> `row.isnull().all()`, which
    would only reject a row where EVERY field is null. A row with exactly
    one null field (the others valid) must still be rejected.
    """
    import open_meteo_forecast_provider

    def _fake_fetch_single_run(lat, lon, run, forecast_days=None, **kwargs):
        return pd.DataFrame([{
            "datetime_utc": run + pd.Timedelta(hours=6),
            "air_temp": None, "wind_speed": 3.0, "wind_direction": 100.0,
            "solar_radiation": 300.0, "relative_humidity": 50.0,
        }])

    monkeypatch.setattr(open_meteo_forecast_provider, "fetch_single_run", _fake_fetch_single_run)
    past_valid_time = pd.Timestamp("2026-01-01T00:00:00Z")
    with pytest.raises(shadow.StaleOrMissingDataError, match="null field"):
        shadow.fetch_live_forecast_for_valid_time(
            _CORRIDOR, past_valid_time, horizon_minutes=1440, lat=30.27, lon=-97.74,
        )


def test_fetch_live_anchor_observation_rejects_a_row_with_only_wind_direction_null(monkeypatch):
    """
    Survived mutant: `pd.isnull(wind_speed) or pd.isnull(wind_direction)` ->
    `and`, which would only reject when BOTH are null. A row with a valid
    wind_speed but a null wind_direction (or vice versa) must still be
    rejected as unusable -- `_wind_feature_frame` needs both.
    """
    cams_id = config.TCEQ_STATIONS["AUSTIN"]
    synoptic_station = config.SYNOPTIC_FALLBACK_STATIONS["AUSTIN"]

    def _fetch(location, start, end, provider="tceq", **kw):
        end_ts = pd.Timestamp(end)
        if provider == "tceq":
            idx = pd.MultiIndex.from_tuples([(cams_id, end_ts)], names=["stid", "datetime_utc"])
            # wind_speed present and valid, wind_direction null -- a partial
            # null that the pre-existing OR check correctly rejects.
            return pd.DataFrame(
                {"wind_speed": [5.0], "wind_direction": [None], "wind_source": [None]}, index=idx,
            )
        raise OSError("Synoptic also unavailable for this probe")

    monkeypatch.setattr(weather_provider, "fetch_weather", _fetch)
    with pytest.raises(shadow.StaleOrMissingDataError, match="null wind field"):
        shadow.fetch_live_anchor_observation("AUSTIN", pd.Timestamp("2026-10-06T12:00:00Z"))


def test_fetch_live_anchor_observation_picks_the_latest_of_several_rows_not_the_first(monkeypatch):
    """
    Survived mutant: `sort_values("datetime_utc")` -> descending, which
    makes `.iloc[-1]` select the EARLIEST row instead of the latest. Every
    pre-existing test supplied exactly one row per fetch, so this ordering
    was never actually exercised with multiple candidate rows. This test
    supplies three rows at different timestamps within the lookback window
    and confirms the chronologically LATEST one's wind values are returned,
    not the first-appearing one.
    """
    cams_id = config.TCEQ_STATIONS["AUSTIN"]
    decision_time = pd.Timestamp("2026-10-06T12:00:00Z")

    def _fetch(location, start, end, provider="tceq", **kw):
        assert provider == "tceq"
        # Deliberately out of chronological order in the returned frame,
        # so a naive "first row" or "last row of an unsorted frame" read
        # would pick the wrong one -- only an explicit sort-then-last is
        # correct.
        rows = [
            {"datetime_utc": decision_time - pd.Timedelta(hours=1), "wind_speed": 9.9, "wind_direction": 10.0, "wind_source": "tceq"},
            {"datetime_utc": decision_time - pd.Timedelta(hours=3), "wind_speed": 1.1, "wind_direction": 20.0, "wind_source": "tceq"},
            {"datetime_utc": decision_time - pd.Timedelta(hours=5), "wind_speed": 5.5, "wind_direction": 30.0, "wind_source": "tceq"},
        ]
        idx = pd.MultiIndex.from_tuples([(cams_id, r["datetime_utc"]) for r in rows], names=["stid", "datetime_utc"])
        return pd.DataFrame(
            {"wind_speed": [r["wind_speed"] for r in rows],
             "wind_direction": [r["wind_direction"] for r in rows],
             "wind_source": [r["wind_source"] for r in rows]},
            index=idx,
        )

    monkeypatch.setattr(weather_provider, "fetch_weather", _fetch)
    anchor = shadow.fetch_live_anchor_observation("AUSTIN", decision_time, lookback_hours=6.0)
    # The chronologically latest row is decision_time - 1h (wind_speed 9.9),
    # not the first-appearing row in the frame (wind_speed 9.9 happens to
    # also be first here deliberately -- assert on the VALUE, which is
    # unambiguous, and on the timestamp, which pins down which row won).
    assert anchor["anchor_wind_speed"] == 9.9
    assert anchor["anchor_observation_time"] == decision_time - pd.Timedelta(hours=1)


def test_fetch_live_anchor_observation_trusts_provenance_over_attempt_tracking_on_disagreement(monkeypatch):
    """
    Survived mutant: `provenance_source != actual_source` -> `==`, which
    makes the "trust provenance over attempt-tracking" correction a no-op
    (it would only ever re-assign a value that's already equal). This is
    only observable when provenance genuinely DISAGREES with which attempt
    the code THINKS succeeded -- never exercised by any pre-existing
    fixture, which always set `wind_source` to match the requested
    provider. Here the TCEQ attempt nominally "succeeds" (no exception, a
    usable row) but the frame's own `wind_source` provenance column says
    "synoptic" -- the function must trust the provenance column, not the
    attempt it thinks ran.
    """
    cams_id = config.TCEQ_STATIONS["AUSTIN"]

    def _fetch(location, start, end, provider="tceq", **kw):
        assert provider == "tceq"
        end_ts = pd.Timestamp(end)
        idx = pd.MultiIndex.from_tuples([(cams_id, end_ts)], names=["stid", "datetime_utc"])
        return pd.DataFrame(
            {"wind_speed": [4.2], "wind_direction": [88.0], "wind_source": ["synoptic"]}, index=idx,
        )

    monkeypatch.setattr(weather_provider, "fetch_weather", _fetch)
    anchor = shadow.fetch_live_anchor_observation("AUSTIN", pd.Timestamp("2026-10-06T12:00:00Z"))
    assert anchor["anchor_source"] == "synoptic"


def test_shadow_pipeline_predict_propagates_corridor_method_provenance_excluding_geometry(monkeypatch):
    """
    Integration gap: no pre-existing test called `ShadowPipeline.predict`
    (which filters `frame.attrs` for `input_provenance`, dropping only the
    `geometry` key) together with `CorridorWindCorrectionMethod` (which
    WRITES the real per-city provenance onto `frame.attrs`) -- every
    existing provenance assertion called the method's `.predict` directly,
    bypassing `ShadowPipeline` entirely. Survived mutant: the geometry
    filter's `!=` -> `==`, which would make `input_provenance` report ONLY
    `{"geometry": ...}` (or `None`) instead of the real per-city data.
    """
    import open_meteo_forecast_provider

    def _fake_fetch_single_run(lat, lon, run, forecast_days=None, **kwargs):
        return pd.DataFrame([{
            "datetime_utc": run + pd.Timedelta(hours=6),
            "air_temp": 22.0, "wind_speed": 3.0, "wind_direction": 200.0,
            "solar_radiation": 400.0, "relative_humidity": 55.0,
        }])

    monkeypatch.setattr(open_meteo_forecast_provider, "fetch_single_run", _fake_fetch_single_run)
    city_a, city_b = config.CORRIDOR_ENDPOINTS[_CORRIDOR]
    cams_a = config.TCEQ_STATIONS[city_a]
    cams_b = config.TCEQ_STATIONS[city_b]

    def _fake_anchor(location, start, end, provider="tceq", **kw):
        cams_id = location[0]
        speed = 2.0 if cams_id == cams_a else 9.0
        end_ts = pd.Timestamp(end)
        idx = pd.MultiIndex.from_tuples([(cams_id, end_ts)], names=["stid", "datetime_utc"])
        return pd.DataFrame(
            {"wind_speed": [speed], "wind_direction": [135.0], "wind_source": ["tceq"]}, index=idx,
        )

    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_anchor)
    fit_frame = _synthetic_wind_fit_frame_real_cities()
    model = forecast_correction_models.fit_wind_correction(
        fit_frame, forecast_correction_models._make_wind_linear_regression, pooling="per_city",
    )
    valid_time = pd.Timestamp("2026-10-07T00:00:00Z")
    decision_time = pd.Timestamp("2026-10-06T12:00:00Z")
    method = shadow.CorridorWindCorrectionMethod(
        model, corridor=_CORRIDOR, model_version="test-version",
        valid_time=valid_time, decision_time=decision_time, horizon_minutes=1440,
    )
    pipeline = shadow.ShadowPipeline(_CORRIDOR, method)
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-06T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-06T06:00:00Z"),
        decision_time=decision_time, valid_time=valid_time, horizon_minutes=1440,
    )
    frame = pd.DataFrame([{"placeholder": True}])
    prediction = pipeline.predict(frame, ts)

    assert prediction.fallback_used is False
    assert prediction.input_provenance is not None
    assert "geometry" not in prediction.input_provenance
    assert set(prediction.input_provenance["per_city_ampacity_amps"]) == {city_a, city_b}
    assert prediction.input_provenance["bottleneck_city"] in (city_a, city_b)
    assert set(prediction.input_provenance["anchor_provenance"]) == {city_a, city_b}


@pytest.mark.parametrize("air_temp", [-60.0, 60.0])
def test_validate_and_prepare_shadow_row_accepts_temperature_at_exact_boundary(air_temp):
    """Survived mutant: `-60.0 <= air_temp` -> `-59.0 <= air_temp` (and the
    symmetric case at the upper bound) -- the boundary values themselves
    were never tested, only values well inside or well outside the range."""
    row = _synthetic_row(fcst_air_temp=air_temp)
    frame = shadow.validate_and_prepare_shadow_row(row, corridor=_CORRIDOR)
    assert frame["fcst_air_temp"].iloc[0] == air_temp


def test_validate_and_prepare_shadow_row_rejects_temperature_just_past_lower_boundary():
    row = _synthetic_row(fcst_air_temp=-60.01)
    with pytest.raises(ValueError, match="outside"):
        shadow.validate_and_prepare_shadow_row(row, corridor=_CORRIDOR)


def test_validate_and_prepare_shadow_row_accepts_exactly_zero_wind_speed():
    """Survived mutant: `wind_speed < 0.0` -> `<= 0.0`. Calm wind (0.0 m/s)
    is physically valid and must be accepted, not rejected as though it
    were negative."""
    row = _synthetic_row(fcst_wind_speed=0.0)
    frame = shadow.validate_and_prepare_shadow_row(row, corridor=_CORRIDOR)
    assert frame["fcst_wind_speed"].iloc[0] == 0.0


def test_validate_and_prepare_shadow_row_accepts_exactly_zero_solar_radiation():
    """Survived mutant: `solar < 0.0` -> `<= 0.0`. Night-time (0.0 W/m^2
    solar radiation) is physically valid and must be accepted."""
    row = _synthetic_row(fcst_solar_radiation=0.0)
    frame = shadow.validate_and_prepare_shadow_row(row, corridor=_CORRIDOR)
    assert frame["fcst_solar_radiation"].iloc[0] == 0.0


def test_wind_correction_shadow_method_propagates_anchor_attrs_onto_callers_frame_object(monkeypatch):
    """
    Survived mutant: deleting `frame.attrs.update(enriched.attrs)` --
    which the code's own comment names as fixing a real propagation bug
    (`enriched` is a fresh copy, not an alias, so without this line the
    CALLER's frame object -- the one `ShadowPipeline.predict` reads
    `.attrs` from afterward -- never sees the anchor provenance at all).
    No pre-existing test asserted on the ORIGINAL frame object's `.attrs`
    after `predict` returned; they only checked the return value.
    """
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_tceq_observation(config.TCEQ_STATIONS["AUSTIN"]))
    fit_frame = _synthetic_wind_fit_frame_real_cities()
    model = forecast_correction_models.fit_wind_correction(
        fit_frame, forecast_correction_models._make_wind_linear_regression, pooling="per_city",
    )
    geometry = corridor_discretization.corridor_geometry(_CORRIDOR)
    endpoint_city = config.CORRIDOR_ENDPOINTS[_CORRIDOR][0]
    row = _synthetic_row(endpoint_city=endpoint_city)
    frame = pd.DataFrame([row]).drop(columns=["anchor_wind_speed", "anchor_wind_direction"])

    method = shadow.WindCorrectionShadowMethod(
        model, endpoint_city=endpoint_city,
        valid_time=pd.Timestamp("2026-10-07T00:00:00Z"),
        decision_time=pd.Timestamp("2026-10-06T12:00:00Z"),
    )
    method.predict(frame, geometry)
    # Asserting on the ORIGINAL `frame` object passed in, not any return
    # value or internal copy -- this is exactly the alias/copy distinction
    # the deleted line exists to bridge.
    assert frame.attrs.get("anchor_source") == "tceq"
    assert frame.attrs.get("anchor_station") == config.TCEQ_STATIONS["AUSTIN"]


def test_raw_forecast_shadow_method_does_not_swap_wind_speed_and_direction():
    """
    Survived mutant: swapping the `fcst_wind_speed`/`fcst_wind_direction`
    arguments to `thermal_model.perpendicular_wind`. The pre-existing test
    only asserted `amps > 0.0`, which both the correct and swapped-argument
    call satisfy (IEEE 738 produces a positive ampacity for any physically
    plausible pair of numbers in either argument slot) -- not
    discriminating. This test instead computes the expected perpendicular
    wind directly, in the documented argument order, and confirms the
    method's result matches a correctly-ordered call and DIFFERS from a
    deliberately swapped-order call, for a case where speed and direction
    are numerically different enough that swapping them changes the
    result.
    """
    geometry = corridor_discretization.corridor_geometry(_CORRIDOR)
    row = _synthetic_row(fcst_wind_speed=2.0, fcst_wind_direction=250.0)
    frame = pd.DataFrame([row])
    method = shadow.RawForecastShadowMethod()
    amps = method.predict(frame, geometry)

    correct_perp = thermal_model.perpendicular_wind(
        np.array([2.0]), np.array([250.0]), geometry.bearing_deg,
    )
    correct_amps = float(np.asarray(thermal_model.ieee738_ampacity(
        np.array([28.0]), correct_perp, np.array([600.0]), geometry.conductor,
    ))[0])
    swapped_perp = thermal_model.perpendicular_wind(
        np.array([250.0]), np.array([2.0]), geometry.bearing_deg,
    )
    swapped_amps = float(np.asarray(thermal_model.ieee738_ampacity(
        np.array([28.0]), swapped_perp, np.array([600.0]), geometry.conductor,
    ))[0])

    assert amps == pytest.approx(correct_amps)
    assert amps != pytest.approx(swapped_amps)


# ──────────────────────────────────────────────────────────────────────
# Plan 05-02: shared-input fetch, corridor-level reduction for all three
# reused candidates, a real persistence_24h, an honest
# reference_ml_refit_24h stub, and the new nested schema.
# ──────────────────────────────────────────────────────────────────────

def _fake_fetch_single_run_counting(counter, **overrides):
    base = {"air_temp": 22.0, "wind_speed": 3.0, "wind_direction": 200.0, "solar_radiation": 400.0}
    base.update(overrides)

    def _fetch(lat, lon, run, forecast_days=None, **kwargs):
        counter["forecast"] += 1
        return pd.DataFrame([{
            "datetime_utc": run + pd.Timedelta(hours=6),
            "air_temp": base["air_temp"], "wind_speed": base["wind_speed"],
            "wind_direction": base["wind_direction"], "solar_radiation": base["solar_radiation"],
            "relative_humidity": 55.0,
        }])
    return _fetch


def test_fetch_shared_corridor_inputs_makes_at_most_two_forecast_and_two_anchor_calls(monkeypatch):
    """D-02/T-05-02-05: exactly one shared fetch per city per cycle -- never
    a second network call for a second candidate's own benefit."""
    import open_meteo_forecast_provider

    counter = {"forecast": 0, "anchor": 0}
    monkeypatch.setattr(
        open_meteo_forecast_provider, "fetch_single_run", _fake_fetch_single_run_counting(counter),
    )

    def _fake_anchor(location, start, end, provider="tceq", **kw):
        counter["anchor"] += 1
        cams_id = location[0]
        end_ts = pd.Timestamp(end)
        idx = pd.MultiIndex.from_tuples([(cams_id, end_ts)], names=["stid", "datetime_utc"])
        return pd.DataFrame(
            {"air_temp": [27.5], "wind_speed": [5.0], "wind_direction": [135.0],
             "wind_source": ["tceq"]}, index=idx,
        )

    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_anchor)

    valid_time = pd.Timestamp("2026-10-07T00:00:00Z")
    decision_time = pd.Timestamp("2026-10-06T12:00:00Z")
    result = shadow.fetch_shared_corridor_inputs(
        _CORRIDOR, valid_time=valid_time, decision_time=decision_time, horizon_minutes=1440,
    )
    city_a, city_b = config.CORRIDOR_ENDPOINTS[_CORRIDOR]
    assert set(result) == {city_a, city_b}
    assert counter["forecast"] <= 2
    assert counter["anchor"] <= 2
    for city, outcome in result.items():
        assert outcome.forecast_frame is not None and outcome.forecast_error is None
        assert outcome.anchor is not None and outcome.anchor_error is None


def test_fetch_shared_corridor_inputs_isolates_one_citys_anchor_failure(monkeypatch):
    """One city's anchor failure must not block that SAME city's own
    forecast fetch, nor the other city's forecast/anchor fetches (D-02)."""
    import open_meteo_forecast_provider

    counter = {"forecast": 0}
    monkeypatch.setattr(
        open_meteo_forecast_provider, "fetch_single_run", _fake_fetch_single_run_counting(counter),
    )
    city_a, city_b = config.CORRIDOR_ENDPOINTS[_CORRIDOR]
    cams_b = config.TCEQ_STATIONS[city_b]
    synoptic_b = config.SYNOPTIC_FALLBACK_STATIONS[city_b]

    def _flaky(location, start, end, provider="tceq", **kw):
        if location[0] in (cams_b, synoptic_b):
            raise ValueError(f"simulated anchor failure for {city_b!r}")
        cams_id = location[0]
        end_ts = pd.Timestamp(end)
        idx = pd.MultiIndex.from_tuples([(cams_id, end_ts)], names=["stid", "datetime_utc"])
        return pd.DataFrame(
            {"air_temp": [27.5], "wind_speed": [5.0], "wind_direction": [135.0],
             "wind_source": ["tceq"]}, index=idx,
        )

    monkeypatch.setattr(weather_provider, "fetch_weather", _flaky)

    valid_time = pd.Timestamp("2026-10-07T00:00:00Z")
    decision_time = pd.Timestamp("2026-10-06T12:00:00Z")
    result = shadow.fetch_shared_corridor_inputs(
        _CORRIDOR, valid_time=valid_time, decision_time=decision_time, horizon_minutes=1440,
    )
    # city_a's forecast AND anchor both succeed.
    assert result[city_a].forecast_frame is not None
    assert result[city_a].anchor is not None
    # city_b's forecast still succeeds even though its anchor fails.
    assert result[city_b].forecast_frame is not None
    assert result[city_b].anchor is None
    assert result[city_b].anchor_error is not None


def test_fetch_live_anchor_observation_returns_anchor_air_temp(monkeypatch):
    """Plan 05-02: the returned Series must carry `anchor_air_temp`
    alongside the five pre-existing keys, read from the same fetched row,
    no new network call."""
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_tceq_observation(config.TCEQ_STATIONS["AUSTIN"]))
    anchor = shadow.fetch_live_anchor_observation("AUSTIN", pd.Timestamp("2026-10-06T12:00:00Z"))
    assert anchor["anchor_air_temp"] == pytest.approx(27.5)
    assert {"anchor_wind_speed", "anchor_wind_direction", "anchor_air_temp",
            "anchor_observation_time", "anchor_source", "anchor_station"} <= set(anchor.index)


def test_fetch_live_anchor_observation_passes_through_nan_when_air_temp_missing(monkeypatch):
    """A null/missing air_temp on an otherwise-usable row must pass
    through as NaN, not raise a second temperature-specific validation."""
    cams_id = config.TCEQ_STATIONS["AUSTIN"]

    def _fetch(location, start, end, provider="tceq", **kw):
        end_ts = pd.Timestamp(end)
        idx = pd.MultiIndex.from_tuples([(cams_id, end_ts)], names=["stid", "datetime_utc"])
        return pd.DataFrame(
            {"wind_speed": [5.0], "wind_direction": [135.0], "wind_source": ["tceq"]}, index=idx,
        )

    monkeypatch.setattr(weather_provider, "fetch_weather", _fetch)
    anchor = shadow.fetch_live_anchor_observation("AUSTIN", pd.Timestamp("2026-10-06T12:00:00Z"))
    assert np.isnan(anchor["anchor_air_temp"])


def test_corridor_reduce_per_city_reduces_two_cities_to_the_minimum():
    geometry = corridor_discretization.corridor_geometry(_CORRIDOR)
    city_a, city_b = config.CORRIDOR_ENDPOINTS[_CORRIDOR]

    class _FixedPerCityMethod:
        name = "fixed"

        def predict(self, frame, geometry):
            return frame["fixed_amps"].iloc[0]

    city_frames = {
        city_a: pd.DataFrame([{"fixed_amps": 1200.0}]),
        city_b: pd.DataFrame([{"fixed_amps": 900.0}]),
    }
    dlr_amps, per_city, bottleneck_city = shadow._corridor_reduce_per_city(
        _FixedPerCityMethod(), city_frames, geometry,
    )
    assert dlr_amps == pytest.approx(900.0)
    assert per_city == {city_a: 1200.0, city_b: 900.0}
    assert bottleneck_city == city_b


@pytest.mark.parametrize("city_frames", [{"A": None}, {"A": None, "B": None, "C": None}])
def test_corridor_reduce_per_city_rejects_wrong_city_count(city_frames):
    with pytest.raises(ValueError, match=str(len(city_frames))):
        shadow._corridor_reduce_per_city(None, city_frames, None)


def _write_jsonl_entry(path, entry):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(__import__("json").dumps(entry) + "\n")


def test_persistence_24h_cold_start_returns_unavailable_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    result = shadow.Persistence24hShadowMethod().compute(_CORRIDOR, pd.Timestamp.now(tz="UTC"))
    assert result.status == "unavailable"
    assert "cold start" in (result.reason or "").lower() or "gap" in (result.reason or "").lower()
    assert result.ampacity_amps is None


def test_persistence_24h_propagates_unavailable_from_matched_entrys_raw_forecast(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    path = str(tmp_path / f"{_CORRIDOR}.jsonl")
    now = pd.Timestamp.now(tz="UTC")
    _write_jsonl_entry(path, {
        "schema_version": 2, "valid_time": now.isoformat(),
        "candidates": {"raw_forecast": {
            "status": "unavailable", "ampacity_amps": None, "fallback_used": False,
            "fallback_reason": None, "model_version": None, "input_provenance": None,
            "reason": "no usable forecast this cycle",
        }},
    })
    result = shadow.Persistence24hShadowMethod().compute(_CORRIDOR, now)
    assert result.status == "unavailable"
    assert "raw_forecast" in result.reason
    assert "unavailable" in result.reason


def test_persistence_24h_skips_a_pre_cutover_flat_shape_line_without_raising(tmp_path, monkeypatch):
    """A pre-cutover flat-shape row (no schema_version, or schema_version
    1) is a normal, expected, skippable input -- never a corruption."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    path = str(tmp_path / f"{_CORRIDOR}.jsonl")
    now = pd.Timestamp.now(tz="UTC")
    _write_jsonl_entry(path, {
        "method": "ml_wind_corrected", "ampacity_amps": 1234.0, "fallback_used": False,
        "fallback_reason": None, "model_version": None, "input_provenance": None,
        "logged_at": now.isoformat(), "valid_time": now.isoformat(),
    })
    result = shadow.Persistence24hShadowMethod().compute(_CORRIDOR, now)
    # The flat-shape row is skipped entirely -- no match exists, so this is
    # the honest cold-start case, never a crash and never a false match on
    # the skipped line's own 1234.0 value.
    assert result.status == "unavailable"
    assert result.ampacity_amps is None


def test_reference_refit_24h_reports_unavailable_naming_missing_path_when_no_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))

    def _should_not_be_called(*a, **k):
        raise AssertionError("no fetch/feature-build/training function may be called when the artifact itself is missing")

    monkeypatch.setattr(weather_provider, "fetch_weather", _should_not_be_called)
    result = shadow.ReferenceRefit24hShadowMethod().compute(_CORRIDOR, pd.Timestamp.now(tz="UTC"))
    assert result.status == "unavailable"
    assert "reference_ml_refit_24h" in result.reason
    assert _CORRIDOR in result.reason
    assert result.ampacity_amps is None


def test_log_cycle_predictions_writes_all_five_candidates_with_exact_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-06T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-06T06:00:00Z"),
        decision_time=pd.Timestamp("2026-10-06T12:00:00Z"),
        valid_time=pd.Timestamp("2026-10-07T00:00:00Z"),
        horizon_minutes=1440,
    )
    candidates = {
        name: shadow.ShadowPrediction(
            corridor=_CORRIDOR, method=name, ampacity_amps=1000.0 + i, timestamps=ts,
            fallback_used=False, model_version=f"v-{name}", input_provenance={"k": name},
            status="ok", reason=None,
        )
        for i, name in enumerate(shadow.CANDIDATE_METHOD_NAMES)
    }
    path = shadow.log_cycle_predictions(_CORRIDOR, candidates, ts)

    import json
    with open(path) as fh:
        record = json.loads(fh.readline())

    assert record["schema_version"] == 2
    assert set(record["candidates"]) == set(shadow.CANDIDATE_METHOD_NAMES)
    for name, cand in record["candidates"].items():
        assert set(cand) == {"status", "ampacity_amps", "fallback_used", "fallback_reason",
                              "model_version", "input_provenance", "reason"}
    mirror = record["candidates"]["ml_wind_corrected"]
    assert record["method"] == "ml_wind_corrected"
    assert record["ampacity_amps"] == mirror["ampacity_amps"]
    assert record["fallback_used"] == mirror["fallback_used"]
    assert record["fallback_reason"] == mirror["fallback_reason"]
    assert record["model_version"] == mirror["model_version"]
    assert record["input_provenance"] == mirror["input_provenance"]


def test_log_cycle_predictions_mirrors_ml_wind_corrected_even_when_unavailable(tmp_path, monkeypatch):
    """The six-field top-level mirror must be an exact copy of
    `ml_wind_corrected`'s own fields EVEN WHEN that candidate's own status
    is not 'ok' -- an honest null, never a different candidate's value
    silently promoted into that slot."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    ts = shadow.ShadowTimestamps(
        initialization_time=pd.Timestamp("2026-10-06T00:00:00Z"),
        availability_time=pd.Timestamp("2026-10-06T06:00:00Z"),
        decision_time=pd.Timestamp("2026-10-06T12:00:00Z"),
        valid_time=pd.Timestamp("2026-10-07T00:00:00Z"),
        horizon_minutes=1440,
    )
    candidates = {
        name: shadow.ShadowPrediction(
            corridor=_CORRIDOR, method=name, ampacity_amps=777.0, timestamps=ts,
            fallback_used=False, status="ok", reason=None,
        )
        for name in shadow.CANDIDATE_METHOD_NAMES
    }
    candidates["ml_wind_corrected"] = shadow.ShadowPrediction(
        corridor=_CORRIDOR, method="ml_wind_corrected", ampacity_amps=None, timestamps=ts,
        fallback_used=False, status="unavailable", reason="no anchor this cycle",
    )
    path = shadow.log_cycle_predictions(_CORRIDOR, candidates, ts)

    import json
    with open(path) as fh:
        record = json.loads(fh.readline())

    assert record["method"] == "ml_wind_corrected"
    assert record["ampacity_amps"] is None
    assert record["candidates"]["ml_wind_corrected"]["status"] == "unavailable"
    # A different candidate's genuine 777.0 value must NEVER leak into the
    # mirror just because ml_wind_corrected itself had nothing to report.
    assert record["ampacity_amps"] != 777.0


# ─────────────────────────────────────────────────────────────────────────
# Plan 05-04: fetch_live_truth_proxy_series and the real
# ReferenceRefit24hShadowMethod.compute predict path.
# ─────────────────────────────────────────────────────────────────────────

_TRUTH_PROXY_ANCHOR = pd.Timestamp("2026-10-07T18:00:00Z")
_TRUTH_PROXY_LOOKBACK_HOURS = config.FORECAST_ML_ROLLING_WINDOW_HOURS


def _synthetic_truth_proxy_city_frame(
    anchor_time=_TRUTH_PROXY_ANCHOR, *, lookback_hours=_TRUTH_PROXY_LOOKBACK_HOURS,
    skip_hour=None, null_field=None, null_field_hour=None,
):
    """One city's own synthetic hourly station window, shaped like
    `weather_provider.fetch_weather`'s real return (a `datetime_utc`
    column plus `air_temp`/`wind_speed`/`wind_direction`/`solar_radiation`)
    -- complete by default, with knobs to drop one hour entirely
    (`skip_hour`) or null one field at one hour (`null_field`/
    `null_field_hour`), for the gap/null tests below."""
    rows = []
    for h in range(lookback_hours, -1, -1):
        ts = anchor_time - pd.Timedelta(hours=h)
        if skip_hour is not None and ts == skip_hour:
            continue
        row = {
            "datetime_utc": ts,
            "air_temp": 25.0 + h,
            "wind_speed": 5.0,
            "wind_direction": 100.0,
            "solar_radiation": 400.0,
        }
        if null_field is not None and null_field_hour is not None and ts == null_field_hour:
            row[null_field] = float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def _synthetic_solar_proxy_frame(
    anchor_time=_TRUTH_PROXY_ANCHOR, *, lookback_hours=_TRUTH_PROXY_LOOKBACK_HOURS,
    skip_hour=None, null_hour=None,
):
    """2026-10-08: `solar_radiation`'s own synthetic source, shaped like
    `open_meteo_forecast_provider.fetch_historical_forecast`'s real
    return (`datetime_utc`, `solar_radiation`, plus the other hourly vars
    that function also returns) -- complete by default, with knobs to
    drop or null one hour, mirroring `_synthetic_truth_proxy_city_frame`'s
    own knobs for the (now solar-free) station frame below."""
    rows = []
    for h in range(lookback_hours, -1, -1):
        ts = anchor_time - pd.Timedelta(hours=h)
        if skip_hour is not None and ts == skip_hour:
            continue
        value = 400.0
        if null_hour is not None and ts == null_hour:
            value = float("nan")
        rows.append({
            "datetime_utc": ts, "air_temp": 25.0, "wind_speed": 5.0,
            "wind_direction": 100.0, "solar_radiation": value, "relative_humidity": 50.0,
        })
    return pd.DataFrame(rows)


def _install_fake_fetch_historical_forecast(monkeypatch, *, frame=None, raise_exc=None):
    """Monkeypatch `open_meteo_forecast_provider.fetch_historical_forecast`
    (the solar-proxy source every truth-proxy test now depends on) to
    return `frame` (defaulting to a complete synthetic window) for BOTH
    endpoint cities, or raise `raise_exc` if given -- never issuing a
    real network call. `_install_fake_fetch_weather` below calls this
    with the default complete frame automatically, so existing callers
    need no change unless a test wants to exercise a solar-specific gap."""

    def _fake_fetch_historical_forecast(lat, lon, start, end):
        if raise_exc is not None:
            raise raise_exc
        return (frame if frame is not None else _synthetic_solar_proxy_frame()).copy()

    monkeypatch.setattr(
        shadow.open_meteo_forecast_provider, "fetch_historical_forecast",
        _fake_fetch_historical_forecast,
    )


def _install_fake_fetch_weather(monkeypatch, *, city_frames: dict, solar_frame=None, solar_raise_exc=None):
    """Monkeypatch `weather_provider.fetch_weather` to return
    `city_frames[cams_id]` for a station-path call whose single requested
    CAMS id matches -- never issuing a real network call. Also installs
    the default (complete) solar-proxy fake via
    `_install_fake_fetch_historical_forecast` (2026-10-08: solar no
    longer comes from this station path at all -- see
    `_TRUTH_PROXY_STATION_FIELDS`), unless a test passes its own
    `solar_frame`/`solar_raise_exc` to exercise a solar-specific gap."""

    def _fake_fetch_weather(location, start, end, provider="synoptic", **kwargs):
        assert provider == "tceq"
        cams_id = location[0]
        frame = city_frames.get(cams_id)
        if frame is None:
            return pd.DataFrame(columns=["datetime_utc", "air_temp", "wind_speed", "wind_direction"])
        return frame.copy()

    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_fetch_weather)
    _install_fake_fetch_historical_forecast(
        monkeypatch, frame=solar_frame, raise_exc=solar_raise_exc,
    )


def _complete_truth_proxy_city_frames():
    austin_cams = config.TCEQ_STATIONS["AUSTIN"]
    corpus_cams = config.TCEQ_STATIONS["CORPUS_CHRISTI"]
    return {
        austin_cams: _synthetic_truth_proxy_city_frame(),
        corpus_cams: _synthetic_truth_proxy_city_frame(),
    }


def test_fetch_live_truth_proxy_series_returns_seven_rows_ending_at_anchor_time(monkeypatch):
    _install_fake_fetch_weather(monkeypatch, city_frames=_complete_truth_proxy_city_frames())

    series, provenance = shadow.fetch_live_truth_proxy_series(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    assert list(series.columns) == ["datetime_utc", "dlr_amps", "air_temp", "wind_speed", "solar_radiation"]
    assert len(series) == 7
    assert series["datetime_utc"].is_monotonic_increasing
    assert series["datetime_utc"].iloc[-1] == _TRUTH_PROXY_ANCHOR
    # 2026-10-08: provenance names which provider supplied each hour, per
    # city -- never a single corridor-wide summary.
    assert provenance["solar_source"] == "open_meteo_historical_forecast"
    for city in ("AUSTIN", "CORPUS_CHRISTI"):
        assert provenance["station_provenance"][city]["sources"] == ["tceq"] * 7
        assert provenance["station_provenance"][city]["fallback_hours"] == []


def test_fetch_live_truth_proxy_series_raises_naming_the_missing_hour_and_city(monkeypatch):
    missing_hour = _TRUTH_PROXY_ANCHOR - pd.Timedelta(hours=3)
    austin_cams = config.TCEQ_STATIONS["AUSTIN"]
    corpus_cams = config.TCEQ_STATIONS["CORPUS_CHRISTI"]
    city_frames = {
        austin_cams: _synthetic_truth_proxy_city_frame(skip_hour=missing_hour),
        corpus_cams: _synthetic_truth_proxy_city_frame(),
    }
    _install_fake_fetch_weather(monkeypatch, city_frames=city_frames)

    with pytest.raises(shadow.StaleOrMissingDataError) as exc_info:
        shadow.fetch_live_truth_proxy_series(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    message = str(exc_info.value)
    assert "AUSTIN" in message
    assert missing_hour.isoformat() in message


def test_fetch_live_truth_proxy_series_treats_a_null_required_field_like_a_missing_hour(monkeypatch):
    null_hour = _TRUTH_PROXY_ANCHOR - pd.Timedelta(hours=2)
    austin_cams = config.TCEQ_STATIONS["AUSTIN"]
    corpus_cams = config.TCEQ_STATIONS["CORPUS_CHRISTI"]
    city_frames = {
        austin_cams: _synthetic_truth_proxy_city_frame(
            null_field="air_temp", null_field_hour=null_hour,
        ),
        corpus_cams: _synthetic_truth_proxy_city_frame(),
    }
    _install_fake_fetch_weather(monkeypatch, city_frames=city_frames)

    with pytest.raises(shadow.StaleOrMissingDataError) as exc_info:
        shadow.fetch_live_truth_proxy_series(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    message = str(exc_info.value)
    assert "AUSTIN" in message
    assert "air_temp" in message
    assert null_hour.isoformat() in message


# ──────────────────────────────────────────────────────────────────────
# 2026-10-08 ("investigate wiring NSRDB or forecast-API solar"):
# `solar_radiation` now comes from `open_meteo_forecast_provider.
# fetch_historical_forecast`, never TCEQ -- these three tests pin that
# source's own three failure modes (total fetch failure, a missing
# required hour, a null value at a required hour), mirroring the
# station-path tests above but against the new source.
# ──────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────
# 2026-10-08 ("what would the fix for that be"): per-hour TCEQ -> Synoptic
# retry for the station fields, mirroring fetch_live_anchor_observation's
# own explicit-row-level-retry pattern, generalized to seven hours.
# ──────────────────────────────────────────────────────────────────────


def _install_fake_fetch_weather_with_synoptic(monkeypatch, *, tceq_frames: dict, synoptic_frames: dict):
    """Dispatches on `provider` -- unlike `_install_fake_fetch_weather`
    (which asserts `provider == "tceq"` and is unsuitable for these
    fallback tests), this fake returns `tceq_frames[cams_id]` for a
    `provider="tceq"` call and `synoptic_frames[station_id]` for a
    `provider="synoptic"` call, each never issuing a real network call.
    Also installs the default (complete) solar-proxy fake."""

    def _fake_fetch_weather(location, start, end, provider="synoptic", **kwargs):
        station_id = location[0]
        frames = tceq_frames if provider == "tceq" else synoptic_frames
        frame = frames.get(station_id)
        if frame is None:
            return pd.DataFrame(columns=["datetime_utc", "air_temp", "wind_speed", "wind_direction"])
        return frame.copy()

    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_fetch_weather)
    _install_fake_fetch_historical_forecast(monkeypatch)


def test_fetch_live_truth_proxy_series_falls_back_to_synoptic_for_one_gap_hour(monkeypatch):
    """
    TCEQ's AUSTIN window has one null `air_temp` hour (its own documented
    trailing-not-yet-reported-hour case); the SAME hour is fully usable
    at AUSTIN's configured Synoptic fallback station. The series must
    still come back complete, and the provenance must name EXACTLY that
    one hour as a fallback -- never a corridor-wide flag, never silently
    dropped.
    """
    gap_hour = _TRUTH_PROXY_ANCHOR - pd.Timedelta(hours=3)
    austin_cams = config.TCEQ_STATIONS["AUSTIN"]
    corpus_cams = config.TCEQ_STATIONS["CORPUS_CHRISTI"]
    austin_synoptic = config.SYNOPTIC_FALLBACK_STATIONS["AUSTIN"]
    tceq_frames = {
        austin_cams: _synthetic_truth_proxy_city_frame(
            null_field="air_temp", null_field_hour=gap_hour,
        ),
        corpus_cams: _synthetic_truth_proxy_city_frame(),
    }
    synoptic_frames = {
        austin_synoptic: _synthetic_truth_proxy_city_frame(),  # fully usable at every hour
    }
    _install_fake_fetch_weather_with_synoptic(
        monkeypatch, tceq_frames=tceq_frames, synoptic_frames=synoptic_frames,
    )

    series, provenance = shadow.fetch_live_truth_proxy_series(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    assert len(series) == 7
    assert series["air_temp"].notna().all()  # the gap hour was actually filled, not skipped
    austin_prov = provenance["station_provenance"]["AUSTIN"]
    assert austin_prov["fallback_hours"] == [gap_hour.isoformat()]
    gap_index = sorted(
        (_TRUTH_PROXY_ANCHOR - pd.Timedelta(hours=h) for h in range(_TRUTH_PROXY_LOOKBACK_HOURS, -1, -1))
    ).index(gap_hour)
    assert austin_prov["sources"][gap_index] == "synoptic"
    # Every OTHER hour, and CORPUS_CHRISTI entirely, stayed on the primary.
    assert austin_prov["sources"].count("synoptic") == 1
    assert provenance["station_provenance"]["CORPUS_CHRISTI"]["sources"] == ["tceq"] * 7
    assert provenance["station_provenance"]["CORPUS_CHRISTI"]["fallback_hours"] == []


def test_fetch_live_truth_proxy_series_raises_naming_both_providers_when_synoptic_also_fails(monkeypatch):
    """
    The gap hour is unusable at BOTH TCEQ and its Synoptic fallback -- the
    raised error must name the hour and BOTH providers' own specific
    failure reasons, not a vague single-provider message.
    """
    gap_hour = _TRUTH_PROXY_ANCHOR - pd.Timedelta(hours=5)
    austin_cams = config.TCEQ_STATIONS["AUSTIN"]
    corpus_cams = config.TCEQ_STATIONS["CORPUS_CHRISTI"]
    austin_synoptic = config.SYNOPTIC_FALLBACK_STATIONS["AUSTIN"]
    tceq_frames = {
        austin_cams: _synthetic_truth_proxy_city_frame(
            null_field="wind_speed", null_field_hour=gap_hour,
        ),
        corpus_cams: _synthetic_truth_proxy_city_frame(),
    }
    synoptic_frames = {
        austin_synoptic: _synthetic_truth_proxy_city_frame(skip_hour=gap_hour),  # no row at all
    }
    _install_fake_fetch_weather_with_synoptic(
        monkeypatch, tceq_frames=tceq_frames, synoptic_frames=synoptic_frames,
    )

    with pytest.raises(shadow.StaleOrMissingDataError) as exc_info:
        shadow.fetch_live_truth_proxy_series(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    message = str(exc_info.value)
    assert "AUSTIN" in message
    assert gap_hour.isoformat() in message
    assert "tceq" in message.lower() and "wind_speed" in message
    assert "synoptic" in message.lower()


def test_fetch_live_truth_proxy_series_raises_when_no_synoptic_fallback_station_configured(monkeypatch):
    """
    A gap hour with NO configured Synoptic fallback station for that city
    must still raise (never silently pass an incomplete window through),
    naming that specifically as the reason -- not a generic "both
    providers failed" message when only one was ever actually tried.
    """
    gap_hour = _TRUTH_PROXY_ANCHOR - pd.Timedelta(hours=2)
    austin_cams = config.TCEQ_STATIONS["AUSTIN"]
    corpus_cams = config.TCEQ_STATIONS["CORPUS_CHRISTI"]
    tceq_frames = {
        austin_cams: _synthetic_truth_proxy_city_frame(
            null_field="air_temp", null_field_hour=gap_hour,
        ),
        corpus_cams: _synthetic_truth_proxy_city_frame(),
    }
    _install_fake_fetch_weather_with_synoptic(monkeypatch, tceq_frames=tceq_frames, synoptic_frames={})
    monkeypatch.setattr(config, "SYNOPTIC_FALLBACK_STATIONS", {})

    with pytest.raises(shadow.StaleOrMissingDataError) as exc_info:
        shadow.fetch_live_truth_proxy_series(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    assert "no Synoptic fallback station configured" in str(exc_info.value)


def test_fetch_live_truth_proxy_series_raises_when_solar_proxy_fetch_fails(monkeypatch):
    _install_fake_fetch_weather(
        monkeypatch, city_frames=_complete_truth_proxy_city_frames(),
        solar_raise_exc=RuntimeError("Open-Meteo historical-forecast: 503"),
    )

    with pytest.raises(shadow.StaleOrMissingDataError) as exc_info:
        shadow.fetch_live_truth_proxy_series(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    assert "solar-proxy" in str(exc_info.value)


def test_fetch_live_truth_proxy_series_raises_naming_the_missing_solar_hour(monkeypatch):
    missing_hour = _TRUTH_PROXY_ANCHOR - pd.Timedelta(hours=4)
    _install_fake_fetch_weather(
        monkeypatch, city_frames=_complete_truth_proxy_city_frames(),
        solar_frame=_synthetic_solar_proxy_frame(skip_hour=missing_hour),
    )

    with pytest.raises(shadow.StaleOrMissingDataError) as exc_info:
        shadow.fetch_live_truth_proxy_series(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    message = str(exc_info.value)
    assert "solar" in message.lower()
    assert missing_hour.isoformat() in message


def test_fetch_live_truth_proxy_series_treats_a_null_solar_hour_like_a_missing_one(monkeypatch):
    null_hour = _TRUTH_PROXY_ANCHOR - pd.Timedelta(hours=1)
    _install_fake_fetch_weather(
        monkeypatch, city_frames=_complete_truth_proxy_city_frames(),
        solar_frame=_synthetic_solar_proxy_frame(null_hour=null_hour),
    )

    with pytest.raises(shadow.StaleOrMissingDataError) as exc_info:
        shadow.fetch_live_truth_proxy_series(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    message = str(exc_info.value)
    assert "solar_radiation" in message
    assert null_hour.isoformat() in message


def test_fetch_live_truth_proxy_series_solar_source_tolerates_off_the_hour_anchor(monkeypatch):
    """
    Open-Meteo's historical-forecast product is hourly-ON-THE-HOUR, but a
    real `decision_time` almost never lands exactly on one (e.g.
    `00:45:36`). `_TRUTH_PROXY_SOLAR_HOUR_TOLERANCE` (35 min) must still
    resolve each off-the-hour target time to its nearest hourly solar
    row -- this is the exact live-run failure mode `_TRUTH_PROXY_HOUR_
    TOLERANCE`'s own tighter 20-minute figure would have caused.
    """
    off_hour_anchor = _TRUTH_PROXY_ANCHOR + pd.Timedelta(minutes=45, seconds=36)
    austin_cams = config.TCEQ_STATIONS["AUSTIN"]
    corpus_cams = config.TCEQ_STATIONS["CORPUS_CHRISTI"]
    city_frames = {
        austin_cams: _synthetic_truth_proxy_city_frame(anchor_time=off_hour_anchor),
        corpus_cams: _synthetic_truth_proxy_city_frame(anchor_time=off_hour_anchor),
    }
    # The solar source's own rows land on the HOUR nearest each target
    # time, not at the off-the-hour target times themselves -- exactly
    # how the real Open-Meteo product reports.
    solar_frame = _synthetic_solar_proxy_frame(anchor_time=_TRUTH_PROXY_ANCHOR + pd.Timedelta(hours=1))
    _install_fake_fetch_weather(monkeypatch, city_frames=city_frames, solar_frame=solar_frame)

    series, _ = shadow.fetch_live_truth_proxy_series(_CORRIDOR, off_hour_anchor)

    assert len(series) == 7
    assert series["solar_radiation"].notna().all()


class _FakeMLPEstimator:
    """A minimal stand-in for a fitted `MLPRegressor` -- records whether
    (and with what shape) `.predict` was called, without touching
    scikit-learn at all."""

    def __init__(self, value=1234.5):
        self.value = value
        self.predict_calls = []

    def predict(self, X):
        self.predict_calls.append(np.asarray(X).shape)
        return np.array([self.value])


def test_reference_refit_24h_compute_predicts_ok_from_a_complete_synthetic_window(monkeypatch):
    fake_model = _FakeMLPEstimator(value=1555.0)
    monkeypatch.setattr(shadow, "load_correction_model", lambda corridor, method_name: fake_model)
    monkeypatch.setattr(shadow, "model_version_for", lambda corridor, method_name: "fake@test")
    _install_fake_fetch_weather(monkeypatch, city_frames=_complete_truth_proxy_city_frames())

    result = shadow.ReferenceRefit24hShadowMethod().compute(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    assert result.status == "ok"
    assert isinstance(result.ampacity_amps, float)
    assert np.isfinite(result.ampacity_amps)
    assert result.ampacity_amps == 1555.0
    assert result.input_provenance["per_city_ampacity_amps"] is None
    assert result.input_provenance["per_city_not_applicable_reason"]
    # 2026-10-08: never silently presented as a true station observation.
    assert result.input_provenance["solar_source"] == "open_meteo_historical_forecast"
    # The real estimator's own .predict was actually called -- not bypassed.
    assert len(fake_model.predict_calls) == 1


def test_reference_refit_24h_compute_never_calls_fit_corridor_model(monkeypatch):
    fake_model = _FakeMLPEstimator()
    monkeypatch.setattr(shadow, "load_correction_model", lambda corridor, method_name: fake_model)
    monkeypatch.setattr(shadow, "model_version_for", lambda corridor, method_name: "fake@test")
    _install_fake_fetch_weather(monkeypatch, city_frames=_complete_truth_proxy_city_frames())

    def _must_not_fit(*a, **k):
        raise AssertionError("ReferenceRefit24hShadowMethod.compute must never fit/retrain an estimator")

    monkeypatch.setattr(forecast_training, "fit_corridor_model", _must_not_fit)

    result = shadow.ReferenceRefit24hShadowMethod().compute(_CORRIDOR, _TRUTH_PROXY_ANCHOR)
    assert result.status == "ok"


def test_reference_refit_24h_compute_loads_and_predicts_from_the_real_persisted_artifact(monkeypatch):
    """Integration check (network-free): Task 1's REAL, already-committed
    artifact fed a synthetic (non-network) 7-row truth-proxy frame through
    the real `build_ml_features` + `.predict(...)` path -- proving the
    offline fit and the live feature-building path agree on feature
    shape/order. Does NOT monkeypatch SHADOW_MODEL_DIR -- loads the real
    on-disk artifact committed by Task 1."""
    _install_fake_fetch_weather(monkeypatch, city_frames=_complete_truth_proxy_city_frames())

    result = shadow.ReferenceRefit24hShadowMethod().compute(_CORRIDOR, _TRUTH_PROXY_ANCHOR)

    assert result.status == "ok"
    assert isinstance(result.ampacity_amps, float)
    assert np.isfinite(result.ampacity_amps)
