"""
Network-free tests for `forecast_shadow_fit_reference_refit.py` (Phase 5
Plan 04, Task 1; per city since 2026-10-12) -- the one-time offline
fit+commit script for the `reference_ml_refit_24h` shadow candidate's
persisted MLP artifact.

`open_meteo_provider.fetch_open_meteo` (the Archive API truth fetch) is
monkeypatched to a small synthetic hourly frame rather than issuing a real
network call. The real (network-touching) per-city fit is a separate,
explicit human step and is NOT run by these tests.
"""

import os

import numpy as np
import pandas as pd
import pytest

import city_point
import config
import forecast_experiment_audit
import forecast_shadow_fit_reference_refit as fit_module
import forecast_shadow_pipeline as shadow
import forecast_training
import open_meteo_provider
import thermal_model

_CITY = "AUSTIN"


def _synthetic_archive_frame(n=40, seed=7):
    """
    A minimal hourly Archive-API-shaped frame (`fetch_open_meteo`'s own
    columns) -- enough hourly rows (40) for `build_training_matrix(
    horizon_minutes=1440)` to produce at least one non-null row: the
    leading 6 rows are dropped for the lag/rolling features, and the
    trailing 24 rows for the 24h-ahead target shift (40 - 6 - 24 = 10).
    """
    ts = pd.date_range("2024-01-20", periods=n, freq="1h", tz="UTC")
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "datetime_utc": ts,
        "air_temp": rng.uniform(10.0, 35.0, n),
        "wind_speed": rng.uniform(1.0, 10.0, n),
        "wind_direction": rng.uniform(0.0, 360.0, n),
        "solar_radiation": rng.uniform(0.0, 800.0, n),
        "relative_humidity": rng.uniform(20.0, 90.0, n),
    })


@pytest.fixture
def captured_fetches(monkeypatch):
    """Patch the archive fetch; records every (lat, lon, start, end) call."""
    calls = []

    def _fake_fetch_open_meteo(lat, lon, start, end):
        calls.append({"lat": lat, "lon": lon, "start": start, "end": end})
        return _synthetic_archive_frame()

    monkeypatch.setattr(open_meteo_provider, "fetch_open_meteo", _fake_fetch_open_meteo)
    return calls


def test_fit_and_save_runs_the_per_city_arm5_recipe_in_order(tmp_path, monkeypatch, captured_fetches):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))

    call_order = []
    real_build_training_matrix = forecast_training.build_training_matrix
    real_fit_model = forecast_training.fit_model

    def _tracking_build_training_matrix(*a, **k):
        call_order.append("build_training_matrix")
        assert k.get("horizon_minutes") == 1440
        return real_build_training_matrix(*a, **k)

    def _tracking_fit_model(*a, **k):
        call_order.append("fit_model")
        return real_fit_model(*a, **k)

    monkeypatch.setattr(forecast_training, "build_training_matrix", _tracking_build_training_matrix)
    monkeypatch.setattr(forecast_training, "fit_model", _tracking_fit_model)

    path = fit_module.fit_and_save(_CITY)

    assert call_order == ["build_training_matrix", "fit_model"]
    assert os.path.basename(path) == f"reference_ml_refit_24h_{_CITY}.joblib"


def test_fit_and_save_writes_a_loadable_artifact_with_predict(tmp_path, monkeypatch, captured_fetches):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))

    path = fit_module.fit_and_save(_CITY)

    assert os.path.exists(path)
    model = shadow.load_correction_model(_CITY, "reference_ml_refit_24h")
    assert hasattr(model, "predict")


def test_fit_and_save_fetches_this_citys_own_coordinates_over_the_pinned_window(tmp_path, monkeypatch, captured_fetches):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))

    fit_module.fit_and_save("EL_PASO")

    assert len(captured_fetches) == 1  # one city -> one fetch; no second endpoint
    call = captured_fetches[0]
    assert (call["lat"], call["lon"]) == config.CITY_COORDINATES["EL_PASO"]
    expected_end = (
        pd.Timestamp(forecast_experiment_audit.FROZEN_TEST_SPLIT_START) - pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    assert call["start"] == forecast_experiment_audit.FROZEN_WINDOW_START
    assert call["end"] == expected_end


def test_truth_frame_target_is_the_citys_own_ampacity_not_a_minimum_across_cities(monkeypatch, captured_fetches):
    """`dlr_amps` must equal that city's own IEEE 738 value from
    `city_point(city)`; two cities with different bearings fed identical
    weather get different, individually-correct series (no min() across
    them)."""
    frames = {}
    for city in ("AUSTIN", "MIDLAND"):
        frame = fit_module._city_truth_frame(city, "2024-01-20", "2024-01-22")
        point = city_point.city_point(city)
        weather = _synthetic_archive_frame()
        perp = thermal_model.perpendicular_wind(
            weather["wind_speed"].to_numpy(dtype=float),
            weather["wind_direction"].to_numpy(dtype=float), point.bearing_deg,
        )
        expected = thermal_model.ieee738_ampacity(
            weather["air_temp"].to_numpy(dtype=float), perp,
            weather["solar_radiation"].to_numpy(dtype=float), point.conductor,
        )
        assert frame["dlr_amps"].to_numpy() == pytest.approx(np.asarray(expected, dtype=float))
        assert list(frame.columns) == ["datetime_utc", "dlr_amps", "air_temp", "wind_speed", "solar_radiation"]
        frames[city] = frame
    assert not np.allclose(frames["AUSTIN"]["dlr_amps"], frames["MIDLAND"]["dlr_amps"])


def test_fit_and_save_does_not_touch_the_production_model_path(tmp_path, monkeypatch, captured_fetches):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))

    def _must_not_persist(*a, **k):
        raise AssertionError("fit_and_save must never call forecast_training.persist_model")

    monkeypatch.setattr(forecast_training, "persist_model", _must_not_persist)
    fit_module.fit_and_save(_CITY)


def test_main_fits_every_configured_city(tmp_path, monkeypatch, captured_fetches):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))

    fit_module.main()

    assert len(captured_fetches) == len(config.LOCATIONS) == 4
    for city in config.LOCATIONS:
        model = shadow.load_correction_model(city, "reference_ml_refit_24h")
        assert hasattr(model, "predict")
    assert sorted(os.listdir(tmp_path)) == sorted(f"reference_ml_refit_24h_{c}.joblib" for c in config.LOCATIONS)
