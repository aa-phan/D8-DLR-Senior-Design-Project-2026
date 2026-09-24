"""
Tests for backend/forecast_training.py (v1.3 Phase 1 Plan 01-01/01-02,
FCST-01/FCST-02 model-honesty invariants and D-01's evidence-based
two-candidate bake-off).

Covers the four invariants that separate a real forecasting model from a
physics inversion or a disguised naive read: no future leakage, the
codebase's own weakest-link `min()` target reduction, and a hard refusal
to fit on an invalid row. Also covers Plan 01-02's bake-off machinery: the
two-candidate comparison, the naive/ewm baselines scored through the same
`backtest_residuals` the runtime band uses, the four-row report shape, and
`select_winner`'s symmetric, evidence-only selection rule. Follows this
suite's existing conventions: module-level imports, plain asserts, no
classes, deterministic synthetic inputs, no network (a real Open-Meteo
fetch is exercised only by Plan 01-01/01-02's own live `<verify>` blocks,
not by this unit suite -- `forecast_training.fetch_city_weather` is
monkeypatched in every test here that needs weather data).
"""

import logging
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import TimeSeriesSplit

import ampacity_forecast
import config
import corridor_discretization
import forecast_training as ft
import thermal_model


def _synthetic_corridor_frame(n=150, seed=20260924):
    """
    A deterministic, `corridor_training_frame`-shaped synthetic frame (no
    network, no `fetch_city_weather` call) for the bake-off tests: hourly
    `datetime_utc` strings, a `dlr_amps` series, and the three
    `config.FORECAST_ML_FEATURE_WEATHER_COLUMNS` weather columns, all
    within `units_def.PIPELINE_SCHEMA`'s ranges.
    """
    rng = np.random.default_rng(seed)
    base_dt = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [(base_dt + timedelta(hours=i)).isoformat() for i in range(n)]

    return pd.DataFrame({
        "datetime_utc": timestamps,
        "dlr_amps": 1200.0 + rng.normal(0.0, 20.0, n),
        "air_temp": 25.0 + rng.normal(0.0, 3.0, n),
        "wind_speed": 5.0 + rng.normal(0.0, 1.5, n),
        "solar_radiation": 500.0 + rng.normal(0.0, 50.0, n),
    })


def _synthetic_training_matrix(n=150, seed=20260924):
    """(X, y) built the same way `forecast_training.main` builds it, from
    a deterministic synthetic frame."""
    return ft.build_training_matrix(_synthetic_corridor_frame(n=n, seed=seed))


# ──────────────────────────────────────────────────────────────────────────────
# build_training_matrix — no future leakage (RESEARCH.md Pitfall 4)
# ──────────────────────────────────────────────────────────────────────────────

def test_build_training_matrix_no_future_leakage():
    n = 40
    base_dt = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [(base_dt + timedelta(hours=i)).isoformat() for i in range(n)]
    rng = np.random.default_rng(20260924)

    frame = pd.DataFrame({
        "datetime_utc": timestamps,
        "dlr_amps": 1200.0 + rng.normal(0.0, 15.0, n),
        "air_temp": 25.0 + rng.normal(0.0, 2.0, n),
        "wind_speed": 5.0 + rng.normal(0.0, 1.0, n),
        "solar_radiation": 500.0 + rng.normal(0.0, 20.0, n),
    })

    X, y = ft.build_training_matrix(frame)

    assert len(X) > 0
    assert len(X) == len(y)

    horizon = pd.Timedelta(minutes=config.FORECAST_HORIZON_MINUTES)
    feature_times = X.index
    target_times = y.index

    assert (target_times - feature_times == horizon).all()
    assert (feature_times < target_times).all()


# ──────────────────────────────────────────────────────────────────────────────
# corridor_training_frame — weakest-link min() reduction (RESEARCH.md
# Pattern 3) and the drop-invalid-row-before-fit invariant (T-01-01)
# ──────────────────────────────────────────────────────────────────────────────

def _alternating_weather_frames(corridor, n=20, hot_temp=40.0, mild_temp=20.0):
    """
    Build two endpoint-city weather frames whose ambient temperature
    alternates which one is hotter (and therefore, holding wind/solar
    constant, which one has the LOWER ieee738_ampacity -- the corridor's
    bottleneck) at each timestamp, so a weakest-link test exercises both
    directions rather than a single, possibly-degenerate case.
    """
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]
    base_dt = datetime(2024, 6, 1, 0, 0, 0)
    timestamps = pd.to_datetime(
        [(base_dt + timedelta(hours=i)).isoformat() + "Z" for i in range(n)], utc=True
    )

    temp_a = np.array([hot_temp if i % 2 == 0 else mild_temp for i in range(n)])
    temp_b = np.array([mild_temp if i % 2 == 0 else hot_temp for i in range(n)])
    wind_speed = np.full(n, 5.0)
    wind_direction = np.full(n, 90.0)
    solar_radiation = np.full(n, 500.0)
    relative_humidity = np.full(n, 50.0)

    def _frame(temp):
        return pd.DataFrame({
            "datetime_utc": timestamps,
            "air_temp": temp,
            "wind_speed": wind_speed,
            "wind_direction": wind_direction,
            "solar_radiation": solar_radiation,
            "relative_humidity": relative_humidity,
        })

    return city_a, city_b, timestamps, temp_a, temp_b, wind_speed, wind_direction, \
        solar_radiation, _frame(temp_a), _frame(temp_b)


def test_corridor_training_frame_weakest_link_min_matches_convention(monkeypatch):
    corridor = "AUSTIN_CORPUS_CHRISTI"
    (city_a, city_b, timestamps, temp_a, temp_b, wind_speed, wind_direction,
     solar_radiation, frame_a, frame_b) = _alternating_weather_frames(corridor)

    def _fake_fetch(city, years):
        if city == city_a:
            return frame_a.copy()
        if city == city_b:
            return frame_b.copy()
        raise AssertionError(f"unexpected city {city!r}")

    monkeypatch.setattr(ft, "fetch_city_weather", _fake_fetch)

    result = ft.corridor_training_frame(corridor, years=1)

    # Ground truth from the SAME thermal_model functions the code under
    # test calls -- not independently hand-computed numbers.
    geometry = corridor_discretization.corridor_geometry(corridor)
    perp = thermal_model.perpendicular_wind(wind_speed, wind_direction, geometry.bearing_deg)
    amps_a = np.asarray(
        thermal_model.ieee738_ampacity(temp_a, perp, solar_radiation, geometry.conductor),
        dtype=float,
    )
    amps_b = np.asarray(
        thermal_model.ieee738_ampacity(temp_b, perp, solar_radiation, geometry.conductor),
        dtype=float,
    )
    expected_dlr = np.minimum(amps_a, amps_b)
    expected_bottleneck = np.where(amps_a <= amps_b, 0, 1)
    expected_air_temp = np.where(expected_bottleneck == 0, temp_a, temp_b)

    assert len(result) == len(timestamps)
    np.testing.assert_allclose(result["dlr_amps"].to_numpy(), expected_dlr, rtol=1e-9)
    assert (result["bottleneck_index"].to_numpy() == expected_bottleneck).all()
    np.testing.assert_allclose(result["air_temp"].to_numpy(), expected_air_temp, rtol=1e-9)
    # Both directions are actually exercised, not a degenerate single-city case.
    assert set(expected_bottleneck.tolist()) == {0, 1}


def test_corridor_training_frame_invalid_row_dropped_before_fit(monkeypatch, caplog):
    corridor = "AUSTIN_CORPUS_CHRISTI"
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]

    n = 5
    base_dt = datetime(2024, 6, 1, 0, 0, 0)
    timestamps = pd.to_datetime(
        [(base_dt + timedelta(hours=i)).isoformat() + "Z" for i in range(n)], utc=True
    )

    temp_a = np.full(n, 25.0)
    # 65C stays comfortably below the conductor's 75C max (so the ieee738
    # heat-balance stays finite, not NaN-from-negative-fractional-power),
    # while still being outside units_def.PIPELINE_SCHEMA's air_temp range
    # (-20, 60) and low enough an ampacity that city A remains the
    # bottleneck (winning) city at this timestamp -- so its own (invalid)
    # air_temp is what reaches the output row, not silently swapped for
    # city B's valid one.
    temp_a[2] = 65.0
    temp_b = np.full(n, 30.0)
    wind_speed = np.full(n, 5.0)
    wind_direction = np.full(n, 90.0)
    solar_radiation = np.full(n, 500.0)
    relative_humidity = np.full(n, 50.0)

    def _frame(temp):
        return pd.DataFrame({
            "datetime_utc": timestamps,
            "air_temp": temp,
            "wind_speed": wind_speed,
            "wind_direction": wind_direction,
            "solar_radiation": solar_radiation,
            "relative_humidity": relative_humidity,
        })

    frame_a = _frame(temp_a)
    frame_b = _frame(temp_b)

    def _fake_fetch(city, years):
        return frame_a.copy() if city == city_a else frame_b.copy()

    monkeypatch.setattr(ft, "fetch_city_weather", _fake_fetch)

    with caplog.at_level(logging.WARNING):
        result = ft.corridor_training_frame(corridor, years=1)

    assert len(result) == n - 1
    assert timestamps[2] not in set(pd.to_datetime(result["datetime_utc"]))
    assert any(
        "dropped 1 invalid row" in record.message for record in caplog.records
    )


# ──────────────────────────────────────────────────────────────────────────────
# bakeoff_corridor — two-candidate comparison via TimeSeriesSplit (D-01)
# ──────────────────────────────────────────────────────────────────────────────

def test_bakeoff_corridor_shape_and_finiteness(monkeypatch):
    monkeypatch.setattr(config, "FORECAST_ML_BAKEOFF_SPLITS", 2)
    X, y = _synthetic_training_matrix()

    result = ft.bakeoff_corridor(X, y)

    assert set(result) == set(ft.CANDIDATE_ESTIMATORS)
    for name, scores in result.items():
        assert math.isfinite(scores["mae"]), (name, scores)
        assert math.isfinite(scores["rmse"]), (name, scores)
        assert scores["rows"] > 0, (name, scores)


def test_bakeoff_corridor_folds_never_overlap(monkeypatch):
    monkeypatch.setattr(config, "FORECAST_ML_BAKEOFF_SPLITS", 3)
    X, _ = _synthetic_training_matrix()

    splitter = TimeSeriesSplit(n_splits=config.FORECAST_ML_BAKEOFF_SPLITS)
    folds = list(splitter.split(X.to_numpy(dtype=float)))

    assert len(folds) == 3
    for train_idx, test_idx in folds:
        assert max(train_idx) < min(test_idx)


# ──────────────────────────────────────────────────────────────────────────────
# baseline_scores — naive/ewm via the SAME backtest_residuals the runtime
# band uses (ROADMAP SC3/SC4 apples-to-apples requirement)
# ──────────────────────────────────────────────────────────────────────────────

def test_baseline_scores_matches_backtest_residuals_directly():
    frame = _synthetic_corridor_frame()

    result = ft.baseline_scores(frame)

    assert set(result) == {"naive", "ewm"}

    indexed = frame.copy()
    indexed.index = pd.to_datetime(indexed["datetime_utc"])
    indexed = indexed.sort_index()
    series = indexed["dlr_amps"]

    for method in ("naive", "ewm"):
        residuals = ampacity_forecast.backtest_residuals(
            series, method,
            min_train_rows=config.FORECAST_MIN_HISTORY_ROWS,
            halflife_min=config.FORECAST_EWM_HALFLIFE_MIN,
        )
        expected_mae = float(np.mean(np.abs(residuals)))
        expected_rmse = float(np.sqrt(np.mean(residuals ** 2)))

        assert result[method]["mae"] == pytest.approx(expected_mae)
        assert result[method]["rmse"] == pytest.approx(expected_rmse)
        assert result[method]["rows"] == residuals.size
        assert math.isfinite(result[method]["mae"])
        assert math.isfinite(result[method]["rmse"])


# ──────────────────────────────────────────────────────────────────────────────
# corridor_report — the four-row comparison (this plan's core deliverable)
# ──────────────────────────────────────────────────────────────────────────────

def test_corridor_report_has_exactly_four_candidates_and_window_fields(monkeypatch):
    monkeypatch.setattr(config, "FORECAST_ML_BAKEOFF_SPLITS", 2)
    frame = _synthetic_corridor_frame()
    X, y = ft.build_training_matrix(frame)

    report = ft.corridor_report("AUSTIN_CORPUS_CHRISTI", frame, X, y)

    expected_names = set(ft.CANDIDATE_ESTIMATORS) | {"naive", "ewm"}
    assert set(report["candidates"]) == expected_names
    assert len(report["candidates"]) == 4

    for name, scores in report["candidates"].items():
        assert math.isfinite(scores["mae"]), name
        assert math.isfinite(scores["rmse"]), name
        assert scores["rows"] > 0, name

    assert report["corridor"] == "AUSTIN_CORPUS_CHRISTI"
    assert report["rows"] == len(frame)
    assert report["window_start"]
    assert report["window_end"]
    assert report["window_start"] < report["window_end"]
    assert report["feature_columns"] == list(ampacity_forecast.ML_FEATURE_COLUMNS)
    assert report["horizon_min"] == config.FORECAST_HORIZON_MINUTES


# ──────────────────────────────────────────────────────────────────────────────
# select_winner — symmetric, evidence-only selection (D-01's no-default-lean)
# ──────────────────────────────────────────────────────────────────────────────

def _hand_built_report(mae_a, mae_b):
    ml_names = list(ft.CANDIDATE_ESTIMATORS)
    row = lambda mae: {"mae": mae, "rmse": mae + 1.0, "rows": 10}
    return {
        "candidates": {
            ml_names[0]: row(mae_a),
            ml_names[1]: row(mae_b),
            "naive": row(9.0),
            "ewm": row(8.0),
        }
    }


def test_select_winner_is_symmetric_under_mae_reordering():
    ml_names = list(ft.CANDIDATE_ESTIMATORS)

    assert ft.select_winner(_hand_built_report(5.0, 3.0)) == ml_names[1]
    assert ft.select_winner(_hand_built_report(1.0, 3.0)) == ml_names[0]


def test_select_winner_raises_when_candidate_missing():
    report = _hand_built_report(5.0, 3.0)
    ml_names = list(ft.CANDIDATE_ESTIMATORS)
    del report["candidates"][ml_names[0]]

    with pytest.raises(ValueError):
        ft.select_winner(report)


def test_select_winner_raises_when_mae_not_finite():
    report = _hand_built_report(5.0, 3.0)
    ml_names = list(ft.CANDIDATE_ESTIMATORS)
    report["candidates"][ml_names[1]]["mae"] = float("nan")

    with pytest.raises(ValueError):
        ft.select_winner(report)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
