"""
Tests for backend/anomaly_training.py (v1.3 Phase 2 Plan 02-01, ANOM-01).

Covers the offline assembly invariants that separate a real, honest
training pipeline from one that silently manufactures data: pooling both
endpoint cities' raw readings rather than reducing them to one series,
dropping out-of-bounds/null rows without ever imputing a replacement
value, and an atomic persist/load round-trip through the runtime's own
loader. Follows this suite's established conventions: module-level
imports, `@pytest.fixture`, plain asserts, no classes, deterministic
synthetic inputs seeded through `numpy.random.default_rng`, no network --
`forecast_training.fetch_city_weather` is monkeypatched in every test
here that needs weather data.
"""

import os

import numpy as np
import pandas as pd
import pytest

import anomaly_detector
import anomaly_training as at
import config
import forecast_training
from DLRSafetyMonitor import DLRSafetyMonitor


def _synthetic_city_weather_frame(city, n=48, seed=20260924, spike_index=None,
                                   null_index=None):
    """
    A deterministic, `open_meteo_provider.fetch_open_meteo`-shaped weather
    frame for one city: `datetime_utc`, `air_temp`, `wind_speed`,
    `solar_radiation` (plus the columns `fetch_city_weather` also returns
    but `corridor_observation_frame` does not read), all comfortably
    inside `DLRSafetyMonitor`'s G3 bounds except for the two deliberately
    injected rows named by `spike_index`/`null_index`.
    """
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2026-01-01T00:00:00Z")
    timestamps = pd.date_range(base, periods=n, freq="h")

    frame = pd.DataFrame({
        "datetime_utc": timestamps,
        "air_temp": 25.0 + rng.normal(0.0, 2.0, n),
        "wind_speed": 8.0 + rng.normal(0.0, 1.5, n),
        "wind_direction": np.full(n, 90.0),
        "solar_radiation": 400.0 + rng.normal(0.0, 50.0, n),
        "relative_humidity": np.full(n, 50.0),
    })

    if spike_index is not None:
        # Comfortably outside DLRSafetyMonitor.WIND_BOUNDS = (0, 50).
        frame.loc[spike_index, "wind_speed"] = 999.0
    if null_index is not None:
        frame.loc[null_index, "air_temp"] = np.nan

    return frame


# ──────────────────────────────────────────────────────────────────────────────
# corridor_observation_frame — pooling (not weakest-link reduction)
# ──────────────────────────────────────────────────────────────────────────────


def test_corridor_observation_frame_pools_both_endpoint_cities(monkeypatch):
    corridor = "AUSTIN_CORPUS_CHRISTI"
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]

    frame_a = _synthetic_city_weather_frame(city_a, n=48, seed=1)
    frame_b = _synthetic_city_weather_frame(city_b, n=48, seed=2)

    def _fake_fetch(city, years):
        if city == city_a:
            return frame_a.copy()
        if city == city_b:
            return frame_b.copy()
        raise AssertionError(f"unexpected city {city!r}")

    monkeypatch.setattr(forecast_training, "fetch_city_weather", _fake_fetch)

    result = at.corridor_observation_frame(corridor, years=1)

    assert set(result["city"].unique()) == {city_a, city_b}
    assert len(result) == len(frame_a) + len(frame_b)


# ──────────────────────────────────────────────────────────────────────────────
# corridor_observation_frame — drop out-of-bounds/null rows, never impute
# ──────────────────────────────────────────────────────────────────────────────


def test_corridor_observation_frame_drops_out_of_bounds_and_null_rows_without_imputing(
    monkeypatch,
):
    corridor = "AUSTIN_CORPUS_CHRISTI"
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]

    frame_a = _synthetic_city_weather_frame(city_a, n=48, seed=3, spike_index=5)
    frame_b = _synthetic_city_weather_frame(city_b, n=48, seed=4, null_index=10)

    def _fake_fetch(city, years):
        if city == city_a:
            return frame_a.copy()
        if city == city_b:
            return frame_b.copy()
        raise AssertionError(f"unexpected city {city!r}")

    monkeypatch.setattr(forecast_training, "fetch_city_weather", _fake_fetch)

    result = at.corridor_observation_frame(corridor, years=1)

    # Exactly the two injected rows are gone -- one wind-speed spike from
    # city_a, one null air_temp from city_b -- and no value in the
    # surviving frame is a substituted replacement for either.
    assert len(result) == len(frame_a) + len(frame_b) - 2
    assert not (result["wind_speed"] == 999.0).any()
    assert not result["air_temp"].isna().any()
    assert result["air_temp"].between(*DLRSafetyMonitor.TEMP_BOUNDS).all()
    assert result["wind_speed"].between(*DLRSafetyMonitor.WIND_BOUNDS).all()
    assert result["solar_radiation"].between(*DLRSafetyMonitor.SOLAR_BOUNDS).all()


# ──────────────────────────────────────────────────────────────────────────────
# build_feature_matrix
# ──────────────────────────────────────────────────────────────────────────────


def test_build_feature_matrix_raises_on_missing_column():
    frame = pd.DataFrame({"air_temp": [25.0], "wind_speed": [5.0]})

    with pytest.raises(ValueError) as exc_info:
        at.build_feature_matrix(frame)

    assert "solar_radiation" in str(exc_info.value)


def test_build_feature_matrix_column_order_matches_config():
    frame = pd.DataFrame({
        "solar_radiation": [400.0, 410.0],
        "air_temp": [25.0, 26.0],
        "wind_speed": [8.0, 9.0],
    })

    X = at.build_feature_matrix(frame)

    assert X.dtype == np.float64
    assert X.shape == (2, 3)
    np.testing.assert_array_equal(X[:, 0], frame["air_temp"].to_numpy())
    np.testing.assert_array_equal(X[:, 1], frame["wind_speed"].to_numpy())
    np.testing.assert_array_equal(X[:, 2], frame["solar_radiation"].to_numpy())


# ──────────────────────────────────────────────────────────────────────────────
# persist_corridor_model — atomic round-trip through the detector's loader
# ──────────────────────────────────────────────────────────────────────────────


def test_persist_round_trips_through_detector_loader(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ANOMALY_ML_MODEL_DIR", str(tmp_path))
    anomaly_detector._MODEL_CACHE.clear()

    corridor = "AUSTIN_CORPUS_CHRISTI"
    rng = np.random.default_rng(20260924)
    X = np.column_stack([
        25.0 + rng.normal(0.0, 2.0, 100),
        8.0 + rng.normal(0.0, 1.5, 100),
        400.0 + rng.normal(0.0, 50.0, 100),
    ])
    estimator = at._make_isolation_forest_candidate(config.ANOMALY_ML_CONTAMINATION)
    fitted = at.fit_corridor_model(X, estimator)

    path = at.persist_corridor_model(fitted, corridor)

    assert os.path.exists(path)
    leftover_tmp_files = [f for f in os.listdir(tmp_path) if f.endswith(".joblib.tmp")]
    assert leftover_tmp_files == []

    loaded = anomaly_detector._load_corridor_model(corridor)

    probe_row = X[:1]
    np.testing.assert_array_equal(fitted.predict(probe_row), loaded.predict(probe_row))

    anomaly_detector._MODEL_CACHE.clear()
