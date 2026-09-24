"""
Tests for backend/ampacity_forecast.py (C9 — Ampacity Forecasting, DS-F11).

Fixtures are generated deterministically (`_synthetic_history`, seeded via
`numpy.random.default_rng`) rather than committed as static data, so the
suite stays reproducible under DS-NF2 with no binary or bulky data in the
repo. Follows backend/tests/corridor_discretization_test.py's conventions:
module-level imports, `@pytest.fixture`/`@pytest.mark.parametrize`, one
`test_*` per behavior, plain asserts, no classes, no network.

Also covers Plan 04-02 Task 2's `forecast_columns` <-> `units_def.PIPELINE_SCHEMA`
agreement (the link that catches a key rename on either side).
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import ampacity_forecast as amp_forecast
import config
import historical_archive
import units_def


def _synthetic_history(n_rows=672, noise_amps=25.0, seed=20260908,
                        base_amps=1200.0, trend_amps_per_row=0.0,
                        varying_weather=False):
    """
    A deterministic, `historical_archive.ARCHIVE_COLUMNS`-compatible frame
    with hourly `datetime_utc` strings and a `dlr_amps` series built from
    `numpy.random.default_rng(seed)` so the same call always produces the
    same frame. The default 672 rows is four weeks of hourly data — the
    "larger synthetic fixture" RESEARCH.md's Wave 0 Gaps asked for, and
    enough for a meaningful walk-forward backtest.

    `varying_weather=True` (v1.3 Phase 1) makes `air_temp`/`wind_speed`/
    `solar_radiation` vary deterministically across rows (a simple
    diurnal-ish sinusoid, all values kept within `units_def.PIPELINE_
    SCHEMA`'s ranges) instead of holding them constant — Task 2's
    weather-sensitivity tests need a frame where the weather features
    actually carry signal for the "ml" method to respond to.
    """
    rng = np.random.default_rng(seed)
    base_dt = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [(base_dt + timedelta(hours=i)).isoformat() for i in range(n_rows)]
    trend = trend_amps_per_row * np.arange(n_rows)
    noise = rng.normal(loc=0.0, scale=noise_amps, size=n_rows) if noise_amps > 0 else np.zeros(n_rows)
    dlr_amps = base_amps + trend + noise

    if varying_weather:
        hours = np.arange(n_rows)
        air_temp = 25.0 + 5.0 * np.sin(2 * np.pi * hours / 24.0)
        wind_speed = 5.0 + 2.0 * np.cos(2 * np.pi * hours / 48.0)
        solar_radiation = 500.0 + 200.0 * np.sin(2 * np.pi * hours / 24.0)
    else:
        air_temp = np.full(n_rows, 25.0)
        wind_speed = np.full(n_rows, 5.0)
        solar_radiation = np.full(n_rows, 500.0)

    return pd.DataFrame({
        "datetime_utc": timestamps,
        "corridor": ["AUSTIN_CORPUS_CHRISTI"] * n_rows,
        "air_temp": air_temp,
        "wind_speed": wind_speed,
        "solar_radiation": solar_radiation,
        "dlr_amps": dlr_amps,
        "static_rating": [1200.0] * n_rows,
        "status": ["ok"] * n_rows,
        "fallback": [False] * n_rows,
        "bottleneck_index": [0] * n_rows,
        "schema_version": [historical_archive.ARCHIVE_SCHEMA_VERSION] * n_rows,
    })


@pytest.fixture
def fitted_ml_model(monkeypatch):
    """
    Monkeypatches `ampacity_forecast._load_corridor_model` to return a
    small, genuinely fitted `HistGradientBoostingRegressor` -- trained
    in-memory on `build_ml_features` output from a varying-weather
    `_synthetic_history` frame -- so a test exercises the real prediction
    path with no disk I/O and no network. Inert for `"naive"`/`"ewm"`
    (they never call `_load_corridor_model`).
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    history = _synthetic_history(n_rows=672, noise_amps=10.0, varying_weather=True)
    frame = history.copy()
    frame.index = pd.to_datetime(frame["datetime_utc"])
    frame = frame.sort_index()

    features = amp_forecast.build_ml_features(frame)
    target = frame["dlr_amps"].shift(-1)  # 1-hour horizon == 1 row at hourly cadence

    valid = features.notna().all(axis=1) & target.notna()
    X = features[valid].to_numpy(dtype=float)
    y = target[valid].to_numpy(dtype=float)

    model = HistGradientBoostingRegressor(random_state=20260908)
    model.fit(X, y)

    monkeypatch.setattr(amp_forecast, "_load_corridor_model", lambda corridor: model)
    return model


# ──────────────────────────────────────────────────────────────────────────────
# backtest_residuals — the out-of-sample walk-forward backtest
# ──────────────────────────────────────────────────────────────────────────────

def test_backtest_residuals_all_zero_on_flat_series():
    history = _synthetic_history(n_rows=100, noise_amps=0.0)
    series = history["dlr_amps"]

    residuals = amp_forecast.backtest_residuals(
        series, method="naive", min_train_rows=config.FORECAST_MIN_HISTORY_ROWS
    )

    assert residuals.size > 0
    assert np.allclose(residuals, 0.0)


def test_backtest_residuals_centered_on_constant_step_for_trend():
    step = 5.0
    history = _synthetic_history(n_rows=100, noise_amps=0.0, trend_amps_per_row=step)
    series = history["dlr_amps"]

    residuals = amp_forecast.backtest_residuals(
        series, method="naive", min_train_rows=config.FORECAST_MIN_HISTORY_ROWS
    )

    assert residuals.size > 0
    assert np.allclose(residuals, step)


def test_band_widens_with_noise():
    narrow = _synthetic_history(n_rows=672, noise_amps=25.0)
    wide = _synthetic_history(n_rows=672, noise_amps=200.0)

    narrow_result = amp_forecast.forecast_ampacity(narrow, method="naive")
    wide_result = amp_forecast.forecast_ampacity(wide, method="naive")

    assert narrow_result is not None and wide_result is not None
    narrow_width = narrow_result.ci_upper_amps - narrow_result.ci_lower_amps
    wide_width = wide_result.ci_upper_amps - wide_result.ci_lower_amps
    assert wide_width > narrow_width


def test_backtest_residuals_order_dependent_on_reversed_tail():
    history = _synthetic_history(n_rows=100, noise_amps=25.0)
    series = history["dlr_amps"]
    original_residuals = amp_forecast.backtest_residuals(
        series, method="naive", min_train_rows=config.FORECAST_MIN_HISTORY_ROWS
    )

    reversed_series = series.copy()
    q = len(series) // 4
    reversed_series.iloc[-q:] = reversed_series.iloc[-q:].iloc[::-1].to_numpy()

    reversed_residuals = amp_forecast.backtest_residuals(
        reversed_series, method="naive", min_train_rows=config.FORECAST_MIN_HISTORY_ROWS
    )

    assert not np.array_equal(original_residuals, reversed_residuals)


# ──────────────────────────────────────────────────────────────────────────────
# Both Tier-1 methods share one signature (D-02, D-10)
# ──────────────────────────────────────────────────────────────────────────────

def test_ewm_and_naive_agree_on_flat_series():
    history = _synthetic_history(n_rows=100, noise_amps=0.0)

    naive_result = amp_forecast.forecast_ampacity(history, method="naive")
    ewm_result = amp_forecast.forecast_ampacity(history, method="ewm")

    assert naive_result is not None and ewm_result is not None
    assert naive_result.amps == pytest.approx(ewm_result.amps, abs=1e-6)


def test_ewm_has_smaller_deviation_from_mean_than_naive_on_noisy_series():
    history = _synthetic_history(n_rows=672, noise_amps=100.0)
    series_mean = float(history["dlr_amps"].mean())

    naive_result = amp_forecast.forecast_ampacity(history, method="naive")
    ewm_result = amp_forecast.forecast_ampacity(history, method="ewm")

    naive_deviation = abs(naive_result.amps - series_mean)
    ewm_deviation = abs(ewm_result.amps - series_mean)

    assert ewm_deviation < naive_deviation


def test_forecast_ampacity_unknown_method_raises_value_error_naming_valid_methods():
    history = _synthetic_history(n_rows=config.FORECAST_MIN_HISTORY_ROWS)

    with pytest.raises(ValueError) as exc_info:
        amp_forecast.forecast_ampacity(history, method="holt")

    message = str(exc_info.value)
    assert "naive" in message
    assert "ewm" in message


# ──────────────────────────────────────────────────────────────────────────────
# Cold-start floor (RESEARCH.md Pitfall 1)
# ──────────────────────────────────────────────────────────────────────────────

def test_forecast_returns_none_below_min_history_rows_and_result_at_exactly_min_rows():
    below = _synthetic_history(n_rows=config.FORECAST_MIN_HISTORY_ROWS - 1)
    at_floor = _synthetic_history(n_rows=config.FORECAST_MIN_HISTORY_ROWS)

    assert amp_forecast.forecast_ampacity(below) is None

    result = amp_forecast.forecast_ampacity(at_floor)
    assert isinstance(result, amp_forecast.ForecastResult)


# ──────────────────────────────────────────────────────────────────────────────
# Band ordering + boundary type discipline (RESEARCH.md Pitfall 2)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method", amp_forecast.FORECAST_METHODS)
def test_band_contains_point_forecast_and_types_are_native(method, fitted_ml_model):
    history = _synthetic_history(n_rows=672, noise_amps=50.0, varying_weather=True)
    result = amp_forecast.forecast_ampacity(history, method=method)

    assert result is not None
    assert result.ci_lower_amps <= result.amps <= result.ci_upper_amps
    assert type(result.amps) is float
    assert type(result.ci_lower_amps) is float
    assert type(result.ci_upper_amps) is float
    assert type(result.n_observations) is int
    assert type(result.n_residuals) is int


# ──────────────────────────────────────────────────────────────────────────────
# forecast_columns <-> units_def.PIPELINE_SCHEMA v2 agreement (Plan 04-02 Task 2)
# ──────────────────────────────────────────────────────────────────────────────

def test_forecast_columns_keys_all_exist_in_pipeline_schema():
    history = _synthetic_history(n_rows=672)
    result = amp_forecast.forecast_ampacity(history)

    assert result is not None
    for key in amp_forecast.forecast_columns(result):
        assert key in units_def.PIPELINE_SCHEMA


def test_forecast_columns_round_trip_validates():
    history = _synthetic_history(n_rows=672)
    result = amp_forecast.forecast_ampacity(history)

    row = {
        "air_temp": 25.0,
        "wind_speed": 5.0,
        "wind_direction": 180.0,
    }
    row.update(amp_forecast.forecast_columns(result))

    errors = units_def.validate_pipeline_row(row, strict=False)
    assert errors == []


def test_forecast_columns_of_none_is_empty():
    assert amp_forecast.forecast_columns(None) == {}


# ──────────────────────────────────────────────────────────────────────────────
# "ml" method model-honesty invariants (v1.3 Phase 1 Plan 01-01 Task 2)
# ──────────────────────────────────────────────────────────────────────────────

def test_build_ml_features_no_future_leakage_on_mutation():
    n = 30
    base_dt = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = pd.to_datetime([(base_dt + timedelta(hours=i)).isoformat() for i in range(n)])
    rng = np.random.default_rng(20260924)

    frame = pd.DataFrame({
        "dlr_amps": 1200.0 + rng.normal(0.0, 15.0, n),
        "air_temp": 25.0 + rng.normal(0.0, 2.0, n),
        "wind_speed": 5.0 + rng.normal(0.0, 1.0, n),
        "solar_radiation": 500.0 + rng.normal(0.0, 20.0, n),
    }, index=timestamps)

    baseline = amp_forecast.build_ml_features(frame)

    t = 15  # comfortably clear of both edges, given max lag = 6h

    mutated_after = frame.copy()
    mutated_after.loc[frame.index[t + 1], "dlr_amps"] += 500.0
    features_after = amp_forecast.build_ml_features(mutated_after)
    pd.testing.assert_series_equal(
        baseline.iloc[t], features_after.iloc[t], check_names=False
    )

    mutated_before = frame.copy()
    mutated_before.loc[frame.index[t - 1], "dlr_amps"] += 500.0
    features_before = amp_forecast.build_ml_features(mutated_before)
    assert not features_before.iloc[t].equals(baseline.iloc[t])


def test_ml_method_sensitive_to_weather_naive_ewm_unaffected(fitted_ml_model):
    history = _synthetic_history(n_rows=672, noise_amps=10.0, varying_weather=True)

    baseline_ml = amp_forecast.forecast_ampacity(history, method="ml")
    baseline_naive = amp_forecast.forecast_ampacity(history, method="naive")
    baseline_ewm = amp_forecast.forecast_ampacity(history, method="ewm")

    edited = history.copy()
    edited["air_temp"] = edited["air_temp"] + 15.0
    edited["wind_speed"] = edited["wind_speed"] + 3.0
    edited["solar_radiation"] = edited["solar_radiation"] + 100.0

    edited_ml = amp_forecast.forecast_ampacity(edited, method="ml")
    edited_naive = amp_forecast.forecast_ampacity(edited, method="naive")
    edited_ewm = amp_forecast.forecast_ampacity(edited, method="ewm")

    assert abs(edited_ml.amps - baseline_ml.amps) > 1e-6
    assert edited_naive.amps == pytest.approx(baseline_naive.amps, abs=1e-9)
    assert edited_ewm.amps == pytest.approx(baseline_ewm.amps, abs=1e-9)


def test_corridor_model_selection_mixed_corridor_raises_naming_both():
    history = _synthetic_history(n_rows=50)
    history = history.copy()
    half = len(history) // 2
    history.loc[history.index[:half], "corridor"] = "AUSTIN_CORPUS_CHRISTI"
    history.loc[history.index[half:], "corridor"] = "MIDLAND_EL_PASO"

    with pytest.raises(ValueError) as exc_info:
        amp_forecast._corridor_of(history)

    message = str(exc_info.value)
    assert "AUSTIN_CORPUS_CHRISTI" in message
    assert "MIDLAND_EL_PASO" in message


def test_corridor_model_selection_unknown_corridor_raises_naming_valid_corridors():
    history = _synthetic_history(n_rows=50).copy()
    history["corridor"] = "NOT_A_REAL_CORRIDOR"

    with pytest.raises(ValueError) as exc_info:
        amp_forecast._corridor_of(history)

    message = str(exc_info.value)
    assert "NOT_A_REAL_CORRIDOR" in message
    for corridor in config.CORRIDOR_ENDPOINTS:
        assert corridor in message


def test_missing_artifact_raises_and_never_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FORECAST_ML_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(amp_forecast, "_MODEL_CACHE", {})

    corridor = "AUSTIN_CORPUS_CHRISTI"
    expected_path = amp_forecast._model_path_for(corridor)

    with pytest.raises(FileNotFoundError) as exc_info:
        amp_forecast._load_corridor_model(corridor)

    message = str(exc_info.value)
    assert corridor in message
    assert expected_path in message

    history = _synthetic_history(n_rows=50)
    with pytest.raises(FileNotFoundError):
        amp_forecast.forecast_ampacity(history, method="ml")


def test_null_weather_raises_rather_than_imputing(fitted_ml_model):
    history = _synthetic_history(n_rows=100, varying_weather=True).copy()
    history.loc[history.index[-1], "wind_speed"] = np.nan

    with pytest.raises(ValueError) as exc_info:
        amp_forecast.forecast_ampacity(history, method="ml")

    assert "wind_speed" in str(exc_info.value)


def test_forecast_ampacity_ml_missing_weather_columns_raises_naming_them():
    history = _synthetic_history(n_rows=50).drop(
        columns=["air_temp", "wind_speed", "solar_radiation"]
    )

    with pytest.raises(ValueError) as exc_info:
        amp_forecast.forecast_ampacity(history, method="ml")

    message = str(exc_info.value)
    for column in config.FORECAST_ML_FEATURE_WEATHER_COLUMNS:
        assert column in message
