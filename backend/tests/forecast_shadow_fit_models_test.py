"""
Network-free tests for `forecast_shadow_fit_models.py` (per-city refit of the
three shadow ML candidates). Synthetic anchored-pair frames only; artifacts
go to tmp_path (SHADOW_MODEL_DIR monkeypatched); no cache or network access.
"""

import os

import numpy as np
import pandas as pd
import pytest

import city_point
import config
import forecast_experiment_audit
import forecast_shadow_fit_models as fm
import forecast_shadow_pipeline as shadow
import thermal_model

_SPLIT = pd.Timestamp(forecast_experiment_audit.FROZEN_TEST_SPLIT_START, tz="UTC")


def _frame(start="2026-01-10", periods=24 * 80, seed=3):
    """Hourly anchored-pair-shaped frame straddling the test split."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=periods, freq="1h", tz="UTC")
    n = len(ts)
    cols = {"datetime_utc": ts, "anchor_datetime_utc": ts - pd.Timedelta(hours=24)}
    for prefix in ("truth", "fcst", "anchor", "fcst_anchor"):
        cols[f"{prefix}_air_temp"] = rng.uniform(5, 35, n)
        cols[f"{prefix}_wind_speed"] = rng.uniform(1, 10, n)
        cols[f"{prefix}_wind_direction"] = rng.uniform(0, 360, n)
        cols[f"{prefix}_solar_radiation"] = rng.uniform(0, 800, n)
        cols[f"{prefix}_relative_humidity"] = rng.uniform(20, 90, n)
    cols["truth_dlr_amps"] = np.full(n, -1.0)  # sentinel: must be recomputed
    cols["anchor_dlr_amps"] = rng.uniform(800, 2000, n)
    return pd.DataFrame(cols)


@pytest.fixture(scope="module")
def fitted():
    return fm.fit_from_frame("EL_PASO", _frame())


def test_fits_all_three_models_for_one_city(fitted):
    assert set(fitted["models"]) == set(fm.FIT_METHODS)
    wind = fitted["models"][fm.WIND_METHOD]
    assert wind.pooling == "per_city"
    assert list(wind.models) == ["EL_PASO"]  # one city, no endpoint pair
    assert all(n > 0 for n in fitted["n_rows_fit"].values())
    # exact-24h-lead subset: strictly before the split
    pre = fm.restrict_to_train_val(_frame())["datetime_utc"]
    expected = int((pre.dt.hour % config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
                    == config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER).sum())
    assert fitted["n_rows_fit"][fm.WIND_METHOD] == expected
    assert fitted["n_rows_fit"][fm.COOLING_METHOD] == expected


def test_fit_city_writes_per_city_artifacts_loadable_by_shadow_path(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))
    out = fm.fit_city("MIDLAND", _frame())
    assert sorted(os.listdir(tmp_path)) == sorted(f"{m}_MIDLAND.joblib" for m in fm.FIT_METHODS)
    for method in fm.FIT_METHODS:
        assert out["paths"][method] == os.path.join(str(tmp_path), f"{method}_MIDLAND.joblib")
        assert shadow.load_correction_model("MIDLAND", method) is not None


def test_unknown_city_is_rejected_before_any_write(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))
    with pytest.raises(KeyError):
        fm.fit_city("AUSTIN_CORPUS_CHRISTI", _frame())
    assert os.listdir(tmp_path) == []


def test_test_period_rows_never_reach_a_fit():
    frame = _frame()
    assert frame["datetime_utc"].max() >= _SPLIT  # the input does straddle the split
    trimmed = fm.restrict_to_train_val(frame)
    assert trimmed["datetime_utc"].max() < _SPLIT
    fm.assert_no_test_leak(trimmed)


def test_leak_assertion_fires_on_test_period_rows():
    with pytest.raises(AssertionError, match="leak"):
        fm.assert_no_test_leak(_frame())


def test_window_end_is_day_before_test_split():
    assert fm.train_val_window_end() == (_SPLIT - pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def test_arm5_target_is_the_citys_own_ampacity():
    frame = _frame(periods=48)
    for city in ("AUSTIN", "EL_PASO"):
        out = fm.weather_to_arm5_frame(frame, city, prefix="truth_")
        point = city_point.city_point(city)
        perp = thermal_model.perpendicular_wind(
            frame["truth_wind_speed"].to_numpy(), frame["truth_wind_direction"].to_numpy(), point.bearing_deg)
        expected = thermal_model.ieee738_ampacity(
            frame["truth_air_temp"].to_numpy(), perp, frame["truth_solar_radiation"].to_numpy(), point.conductor)
        assert out["dlr_amps"].to_numpy() == pytest.approx(np.asarray(expected, dtype=float))
        assert list(out.columns) == ["datetime_utc", "dlr_amps", "air_temp", "wind_speed", "solar_radiation"]


def test_arm5_fit_uses_citys_own_ampacity_not_cached_or_other_city(monkeypatch):
    import forecast_training
    seen = {}
    real = forecast_training.build_training_matrix

    def spy(frame, horizon_minutes=None):
        seen["frame"], seen["h"] = frame.copy(), horizon_minutes
        return real(frame, horizon_minutes=horizon_minutes)

    monkeypatch.setattr(forecast_training, "build_training_matrix", spy)
    frame = _frame()
    fm.fit_from_frame("EL_PASO", frame)
    assert seen["h"] == 1440
    assert (seen["frame"]["dlr_amps"] > 0).all()  # sentinel -1 was replaced
    expected = fm.weather_to_arm5_frame(fm.restrict_to_train_val(frame), "EL_PASO", prefix="truth_")
    assert seen["frame"]["dlr_amps"].to_numpy() == pytest.approx(expected["dlr_amps"].to_numpy())
    other = fm.weather_to_arm5_frame(fm.restrict_to_train_val(frame), "AUSTIN", prefix="truth_")
    assert not np.allclose(seen["frame"]["dlr_amps"], other["dlr_amps"])


def test_missing_cache_refuses_instead_of_hitting_network(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    import forecast_experiment

    def boom(*a, **k):
        raise AssertionError("network path reached")

    monkeypatch.setattr(forecast_experiment, "anchored_pair_frame", boom)
    with pytest.raises(FileNotFoundError, match="missing"):
        fm.load_city_frame("AUSTIN")
