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
import city_point
import forecast_training as ft
import thermal_model


def _synthetic_city_frame(n=150, seed=20260924):
    """
    A deterministic, `city_training_frame`-shaped synthetic frame (no
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
    return ft.build_training_matrix(_synthetic_city_frame(n=n, seed=seed))


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
# build_training_matrix — additive horizon_minutes parameter (Phase 3 Plan 05,
# D-03, RESEARCH.md Pitfall 4). The equality gate below is pure parameter
# plumbing, not a numerical reformulation, so it is an exact-equality check
# (np.array_equal) against a golden capture taken from the UNMODIFIED source
# -- never a tolerance comparator.
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def golden_horizon_fixture():
    import os

    path = os.path.join(
        os.path.dirname(__file__), "forecast_training_pre_horizon_param_golden.npz"
    )
    return np.load(path, allow_pickle=True)


def test_build_training_matrix_default_path_is_bit_identical_to_pre_horizon_param_golden(
    golden_horizon_fixture,
):
    g = golden_horizon_fixture
    frame = _synthetic_city_frame(n=150, seed=20260924)

    X, y = ft.build_training_matrix(frame)

    assert list(X.columns) == list(g["X_columns"]), (
        "the additive horizon_minutes parameter changed the feature column "
        "set at its default -- this is pure parameter plumbing and must not"
    )
    assert np.array_equal(X.to_numpy(dtype=float), g["X_values"]), (
        "the default path's feature matrix is not bit-identical to the "
        "pre-edit golden capture"
    )
    assert np.array_equal(X.index.to_numpy(), g["X_index"]), (
        "the default path's feature index is not bit-identical to the "
        "pre-edit golden capture"
    )
    assert np.array_equal(y.to_numpy(dtype=float), g["y_values"]), (
        "the default path's target series is not bit-identical to the "
        "pre-edit golden capture"
    )
    assert np.array_equal(y.index.to_numpy(), g["y_index"]), (
        "the default path's target index is not bit-identical to the "
        "pre-edit golden capture"
    )


def test_build_training_matrix_1440_minute_horizon_shifts_target_by_exactly_24_hours():
    # The direct refutation of RESEARCH.md Pitfall 4's failure mode: a
    # target still shifted by one row (the production 60-minute default)
    # would produce a plausible-looking arm-5 score that means nothing.
    # Asserting on the returned index values -- not merely on prose -- is
    # what makes the 24-hour shift inspectable.
    frame = _synthetic_city_frame(n=150, seed=20260924)

    X, y = ft.build_training_matrix(frame, horizon_minutes=1440)

    assert len(X) > 0
    assert (y.index - X.index == pd.Timedelta(hours=24)).all()


def test_build_training_matrix_1440_minute_horizon_drops_exactly_23_more_rows_than_default():
    """
    `build_ml_features` is causal-only (lag/rolling-mean columns look
    backward, never forward), so its trailing edge never carries a NaN --
    every row through the frame's own last row has valid features. The
    ONLY reason any trailing row is dropped is a NaN target from the
    horizon shift.

    At the default 60-minute (1-row) horizon, exactly the frame's own
    last row lacks a target -- 1 row dropped for that reason. At a
    1440-minute (24-row) horizon, the last 24 rows lack a target -- 24
    rows dropped for that reason. Both drop ranges sit entirely inside
    the same feature-valid trailing edge (feature validity never changes
    with the horizon), so the row count at 1440 minutes is fewer than the
    row count at 60 minutes by exactly 24 - 1 = 23 rows, NOT 24: the
    60-minute path was already dropping one of those same trailing rows,
    so counting it a second time when comparing the two horizons would
    double-count it. Asserted directly from both returned frames' lengths
    rather than assumed from the naive "24 trailing rows now lack a
    target" framing, which is the exact "verify the horizon/lag
    assumption explicitly, don't trust it" discipline this phase has
    already applied twice before (thermal_model, corridor_weakest_link).
    """
    frame = _synthetic_city_frame(n=150, seed=20260924)

    X_60, y_60 = ft.build_training_matrix(frame)
    X_1440, y_1440 = ft.build_training_matrix(frame, horizon_minutes=1440)

    assert len(X_60) - len(X_1440) == 23
    assert len(y_60) - len(y_1440) == 23


def test_build_training_matrix_non_whole_multiple_horizon_raises_and_names_value():
    frame = _synthetic_city_frame(n=150, seed=20260924)

    with pytest.raises(ValueError, match="90"):
        ft.build_training_matrix(frame, horizon_minutes=90)


def test_build_training_matrix_production_call_sites_remain_single_positional():
    """
    Both production call sites (`main`, `_run_bakeoff`) call
    `build_training_matrix(frame)` with the frame passed positionally and
    no keyword -- a direct source-level guard that the additive parameter
    was appended last with a default that requires no call-site change.
    """
    import inspect
    import re

    source = inspect.getsource(ft)
    calls = re.findall(r"build_training_matrix\(([^)]*)\)", source)
    # Exclude the function's own definition line and this test's imports.
    call_sites = [c for c in calls if c.strip() == "frame"]
    assert len(call_sites) >= 2, (
        f"expected at least 2 single-positional call sites, found: {calls}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# corridor_weakest_link — FROZEN legacy helper (frozen experiment only)
# (Phase 3 Plan 02, D-03)
# ──────────────────────────────────────────────────────────────────────────────

def test_corridor_weakest_link_exact_tie_resolves_to_city_a():
    a = np.array([100.0, 200.0, 150.0, 150.0])
    b = np.array([120.0, 180.0, 150.0, 140.0])

    amps, idx, cols = ft.corridor_weakest_link(
        a, b,
        {"air_temp": np.array([1.0, 2.0, 3.0, 4.0])},
        {"air_temp": np.array([9.0, 8.0, 7.0, 6.0])},
    )

    assert np.array_equal(amps, np.minimum(a, b))
    assert int(idx[2]) == 0, (
        "an exact ampacity tie must resolve to city A, matching "
        "rate_corridor's first-match convention"
    )
    assert list(idx) == [0, 1, 0, 1]


def test_corridor_weakest_link_returns_winning_citys_own_weather():
    a = np.array([100.0, 200.0, 150.0, 150.0])
    b = np.array([120.0, 180.0, 150.0, 140.0])

    _amps, _idx, cols = ft.corridor_weakest_link(
        a, b,
        {"air_temp": np.array([1.0, 2.0, 3.0, 4.0])},
        {"air_temp": np.array([9.0, 8.0, 7.0, 6.0])},
    )

    assert list(cols["air_temp"]) == [1.0, 8.0, 3.0, 6.0], (
        "the reduction did not carry the winning city's own weather"
    )


# ──────────────────────────────────────────────────────────────────────────────
# city_training_frame — one city's OWN ampacity, no cross-city reduction, and
# the drop-invalid-row-before-fit invariant (T-01-01)
# ──────────────────────────────────────────────────────────────────────────────

def _city_weather(n=20, temp=None):
    base_dt = datetime(2024, 6, 1, 0, 0, 0)
    timestamps = pd.to_datetime(
        [(base_dt + timedelta(hours=i)).isoformat() + "Z" for i in range(n)], utc=True
    )
    if temp is None:
        temp = np.array([40.0 if i % 2 == 0 else 20.0 for i in range(n)])
    return timestamps, pd.DataFrame({
        "datetime_utc": timestamps,
        "air_temp": temp,
        "wind_speed": np.full(n, 5.0),
        "wind_direction": np.full(n, 90.0),
        "solar_radiation": np.full(n, 500.0),
        "relative_humidity": np.full(n, 50.0),
    })


@pytest.mark.parametrize("city", sorted(config.LOCATIONS))
def test_city_training_frame_uses_own_ampacity(monkeypatch, city):
    timestamps, weather = _city_weather()
    fetched = []

    def _fake_fetch(c, years):
        fetched.append(c)
        return weather.copy()

    monkeypatch.setattr(ft, "fetch_city_weather", _fake_fetch)
    result = ft.city_training_frame(city, years=1)

    assert fetched == [city]  # exactly one city's weather, no pairing
    point = city_point.city_point(city)
    perp = thermal_model.perpendicular_wind(
        weather["wind_speed"].to_numpy(), weather["wind_direction"].to_numpy(),
        point.bearing_deg,
    )
    expected = np.asarray(thermal_model.ieee738_ampacity(
        weather["air_temp"].to_numpy(), perp,
        weather["solar_radiation"].to_numpy(), point.conductor,
    ), dtype=float)

    assert len(result) == len(timestamps)
    np.testing.assert_allclose(result["dlr_amps"].to_numpy(), expected, rtol=1e-9)
    np.testing.assert_allclose(
        result["air_temp"].to_numpy(), weather["air_temp"].to_numpy(), rtol=1e-9
    )
    assert (result["city"] == city).all()
    assert "corridor" not in result.columns
    assert result["static_rating"].iloc[0] == float(point.static_rating)


def test_city_training_frame_has_no_min_reduction():
    import inspect

    source = inspect.getsource(ft.city_training_frame)
    assert "np.minimum" not in source
    assert "weakest_link" not in source


def test_city_training_frame_unknown_city_raises():
    with pytest.raises(KeyError):
        ft.city_training_frame("NOT_A_CITY", years=1)


def test_city_training_frame_invalid_row_dropped_before_fit(monkeypatch, caplog):
    n = 5
    temp = np.full(n, 25.0)
    # 65C is outside units_def.PIPELINE_SCHEMA's air_temp range (-20, 60) yet
    # below the conductor's 75C max so the heat balance stays finite.
    temp[2] = 65.0
    timestamps, weather = _city_weather(n=n, temp=temp)
    monkeypatch.setattr(ft, "fetch_city_weather", lambda c, y: weather.copy())

    with caplog.at_level(logging.WARNING):
        result = ft.city_training_frame("AUSTIN", years=1)

    assert len(result) == n - 1
    assert timestamps[2] not in set(pd.to_datetime(result["datetime_utc"]))
    assert any(
        "dropped 1 invalid row" in record.message for record in caplog.records
    )


# ──────────────────────────────────────────────────────────────────────────────
# bakeoff_city — two-candidate comparison via TimeSeriesSplit (D-01)
# ──────────────────────────────────────────────────────────────────────────────

def test_bakeoff_city_shape_and_finiteness(monkeypatch):
    monkeypatch.setattr(config, "FORECAST_ML_BAKEOFF_SPLITS", 2)
    X, y = _synthetic_training_matrix()

    result = ft.bakeoff_city(X, y)

    assert set(result) == set(ft.CANDIDATE_ESTIMATORS)
    for name, scores in result.items():
        assert math.isfinite(scores["mae"]), (name, scores)
        assert math.isfinite(scores["rmse"]), (name, scores)
        assert scores["rows"] > 0, (name, scores)


def test_bakeoff_city_folds_never_overlap(monkeypatch):
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
    frame = _synthetic_city_frame()

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
# city_report — the four-row comparison (this plan's core deliverable)
# ──────────────────────────────────────────────────────────────────────────────

def test_city_report_has_exactly_four_candidates_and_window_fields(monkeypatch):
    monkeypatch.setattr(config, "FORECAST_ML_BAKEOFF_SPLITS", 2)
    frame = _synthetic_city_frame()
    X, y = ft.build_training_matrix(frame)

    report = ft.city_report("AUSTIN", frame, X, y)

    expected_names = set(ft.CANDIDATE_ESTIMATORS) | {"naive", "ewm"}
    assert set(report["candidates"]) == expected_names
    assert len(report["candidates"]) == 4

    for name, scores in report["candidates"].items():
        assert math.isfinite(scores["mae"]), name
        assert math.isfinite(scores["rmse"]), name
        assert scores["rows"] > 0, name

    assert report["city"] == "AUSTIN"
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
