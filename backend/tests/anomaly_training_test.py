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

import math
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

import anomaly_detector
import anomaly_training as at
import config
import forecast_training
from DLRSafetyMonitor import DLRSafetyMonitor


def _synthetic_observation_frame(n=100, seed=1):
    """
    A deterministic, `corridor_observation_frame`-shaped pooled frame
    (`datetime_utc`, `corridor`, `city`, the three `config.ANOMALY_ML_
    FEATURE_COLUMNS`), comfortably inside `DLRSafetyMonitor`'s G3 bounds,
    for the measurement-machinery tests below that don't need a live
    network fetch -- only `chronological_split`/`inject_anomalies`/
    `score_rolling_baseline`/`validate_candidate`'s own logic, never
    `corridor_observation_frame` itself.
    """
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2026-01-01T00:00:00Z")
    timestamps = pd.date_range(base, periods=n, freq="h")
    return pd.DataFrame({
        "datetime_utc": timestamps,
        "corridor": "AUSTIN_CORPUS_CHRISTI",
        "city": np.where(np.arange(n) % 2 == 0, "AUSTIN", "CORPUS_CHRISTI"),
        "air_temp": 25.0 + rng.normal(0.0, 2.0, n),
        "wind_speed": 8.0 + rng.normal(0.0, 1.5, n),
        "solar_radiation": 400.0 + rng.normal(0.0, 50.0, n),
    })


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


# ──────────────────────────────────────────────────────────────────────────────
# chronological_split (v1.3 Phase 2 Plan 02-02, ANOM-02)
# ──────────────────────────────────────────────────────────────────────────────


def test_chronological_split_returns_nonoverlapping_time_ordered_slices():
    frame = _synthetic_observation_frame(n=100, seed=101)
    shuffled = frame.sample(frac=1.0, random_state=7).reset_index(drop=True)

    fit, holdout = at.chronological_split(shuffled, holdout_fraction=0.25)

    assert len(fit) + len(holdout) == len(shuffled)
    assert fit["datetime_utc"].max() <= holdout["datetime_utc"].min()
    assert set(fit["datetime_utc"]).isdisjoint(set(holdout["datetime_utc"]))

    # Pure function of the input -- called twice, identical slices.
    fit2, holdout2 = at.chronological_split(shuffled, holdout_fraction=0.25)
    pd.testing.assert_frame_equal(fit, fit2)
    pd.testing.assert_frame_equal(holdout, holdout2)


def test_chronological_split_raises_on_empty_or_undersized_fit_slice():
    # Fit slice below anomaly_detector.ROLLING_BASELINE_MIN_ROWS (24).
    tiny_frame = _synthetic_observation_frame(n=10, seed=102)
    with pytest.raises(ValueError):
        at.chronological_split(tiny_frame, holdout_fraction=0.25)

    # holdout_fraction=0.0 forces an empty holdout side.
    with pytest.raises(ValueError):
        at.chronological_split(
            _synthetic_observation_frame(n=50, seed=103), holdout_fraction=0.0
        )


# ──────────────────────────────────────────────────────────────────────────────
# inject_anomalies -- non-mutation, category construction, reproducibility
# ──────────────────────────────────────────────────────────────────────────────


def test_inject_anomalies_out_of_range_leaves_input_unmutated_and_masks_correct_count():
    frame = _synthetic_observation_frame(n=200, seed=111)
    pre_call_copy = frame.copy(deep=True)

    injected, mask = at.inject_anomalies(
        frame, "out_of_range", rng=np.random.default_rng(20260924), rate=0.02,
    )

    pd.testing.assert_frame_equal(frame, pre_call_copy)
    assert int(mask.sum()) == round(len(frame) * 0.02)
    assert len(injected) == len(frame)


def test_inject_anomalies_out_of_range_values_are_outside_bounds():
    frame = _synthetic_observation_frame(n=200, seed=112)

    injected, mask = at.inject_anomalies(
        frame, "out_of_range", rng=np.random.default_rng(20260924), rate=0.05,
    )

    bound_pairs = (
        ("wind_speed", DLRSafetyMonitor.WIND_BOUNDS),
        ("air_temp", DLRSafetyMonitor.TEMP_BOUNDS),
        ("solar_radiation", DLRSafetyMonitor.SOLAR_BOUNDS),
    )
    injected_rows = injected.loc[mask]
    assert len(injected_rows) > 0
    for _, row in injected_rows.iterrows():
        outside = [not (lo <= row[col] <= hi) for col, (lo, hi) in bound_pairs]
        assert any(outside), f"row {row.to_dict()} has no out-of-bounds feature"


def test_inject_anomalies_in_range_implausible_components_are_observed_but_combination_is_not():
    frame = _synthetic_observation_frame(n=300, seed=113)
    fit_frame, holdout_frame = at.chronological_split(frame, holdout_fraction=0.25)

    injected, mask = at.inject_anomalies(
        holdout_frame, "in_range_implausible",
        rng=np.random.default_rng(20260924), rate=0.2, fit_frame=fit_frame,
    )

    bound_pairs = {
        "wind_speed": DLRSafetyMonitor.WIND_BOUNDS,
        "air_temp": DLRSafetyMonitor.TEMP_BOUNDS,
        "solar_radiation": DLRSafetyMonitor.SOLAR_BOUNDS,
    }
    injected_rows = injected.loc[mask]
    assert len(injected_rows) > 0
    for column, (lo, hi) in bound_pairs.items():
        assert injected_rows[column].between(lo, hi).all()
        assert injected_rows[column].min() >= fit_frame[column].min()
        assert injected_rows[column].max() <= fit_frame[column].max()

    # All injected rows carry the SAME triple; that exact triple must be
    # absent from the fit slice at every timestamp.
    triple = tuple(
        injected_rows[["air_temp", "wind_speed", "solar_radiation"]].iloc[0]
    )
    fit_triples = set(
        map(tuple, fit_frame[["air_temp", "wind_speed", "solar_radiation"]].to_numpy())
    )
    assert triple not in fit_triples


def test_inject_anomalies_unknown_category_raises():
    frame = _synthetic_observation_frame(n=50, seed=114)
    with pytest.raises(ValueError) as exc_info:
        at.inject_anomalies(frame, "not_a_real_category")
    assert "not_a_real_category" in str(exc_info.value)


def test_inject_anomalies_in_range_implausible_without_fit_frame_raises():
    frame = _synthetic_observation_frame(n=50, seed=115)
    with pytest.raises(ValueError) as exc_info:
        at.inject_anomalies(frame, "in_range_implausible")
    assert "fit_frame" in str(exc_info.value)


def test_inject_anomalies_reproducible_with_same_seed():
    frame = _synthetic_observation_frame(n=200, seed=116)

    injected_1, mask_1 = at.inject_anomalies(
        frame, "out_of_range", rng=np.random.default_rng(42), rate=0.02,
    )
    injected_2, mask_2 = at.inject_anomalies(
        frame, "out_of_range", rng=np.random.default_rng(42), rate=0.02,
    )

    pd.testing.assert_series_equal(mask_1, mask_2)
    pd.testing.assert_frame_equal(injected_1, injected_2)


# ──────────────────────────────────────────────────────────────────────────────
# score_rolling_baseline_arm -- provenance: the real branch ran, model is None
# ──────────────────────────────────────────────────────────────────────────────


def test_score_rolling_baseline_arm_uses_real_branch_and_bare_model(monkeypatch):
    corridor = "AUSTIN_CORPUS_CHRISTI"
    frame = _synthetic_observation_frame(n=200, seed=121)
    fit_frame, holdout_frame = at.chronological_split(frame, holdout_fraction=0.25)

    anomaly_detector._MODEL_CACHE.clear()

    captured = {}
    original_for_corridor = anomaly_detector.AnomalyDetector.for_corridor.__func__

    def _capturing_for_corridor(cls, *args, **kwargs):
        detector = original_for_corridor(cls, *args, **kwargs)
        captured["detector"] = detector
        return detector

    monkeypatch.setattr(
        anomaly_detector.AnomalyDetector,
        "for_corridor",
        classmethod(_capturing_for_corridor),
    )

    flags = at.score_rolling_baseline(corridor, fit_frame, holdout_frame)

    assert captured["detector"].model is None
    assert captured["detector"].signal == "rolling_baseline"
    assert isinstance(flags, np.ndarray)
    assert flags.dtype == bool
    assert len(flags) == len(holdout_frame)

    anomaly_detector._MODEL_CACHE.clear()


# ──────────────────────────────────────────────────────────────────────────────
# validate_candidate -- shape, finiteness, disjoint denominators
# ──────────────────────────────────────────────────────────────────────────────


def test_validate_candidate_returns_all_expected_finite_rate_keys():
    corridor = "AUSTIN_CORPUS_CHRISTI"
    frame = _synthetic_observation_frame(n=400, seed=131)
    fit_frame, holdout_frame = at.chronological_split(frame, holdout_fraction=0.25)

    anomaly_detector._MODEL_CACHE.clear()
    result = at.validate_candidate(
        corridor, fit_frame, holdout_frame,
        "IsolationForest", at._make_isolation_forest_candidate, 0.02,
    )

    expected_keys = (
        "false_positive_rate", "baseline_false_positive_rate",
        "recall_out_of_range", "recall_in_range_implausible", "recall_pooled",
        "baseline_recall_out_of_range", "baseline_recall_in_range_implausible",
        "baseline_recall_pooled",
    )
    for key in expected_keys:
        assert key in result
        assert math.isfinite(result[key]), f"{key} is not finite: {result[key]!r}"
        assert 0.0 <= result[key] <= 1.0, f"{key} is outside [0, 1]: {result[key]!r}"

    anomaly_detector._MODEL_CACHE.clear()


def test_validate_candidate_false_positive_and_recall_denominators_are_disjoint():
    corridor = "AUSTIN_CORPUS_CHRISTI"
    frame = _synthetic_observation_frame(n=400, seed=132)
    fit_frame, holdout_frame = at.chronological_split(frame, holdout_fraction=0.25)

    anomaly_detector._MODEL_CACHE.clear()
    result = at.validate_candidate(
        corridor, fit_frame, holdout_frame,
        "IsolationForest", at._make_isolation_forest_candidate, 0.02,
    )

    assert result["clean_rows"] == len(holdout_frame)
    assert result["injected_rows_out_of_range"] == round(
        len(holdout_frame) * config.ANOMALY_ML_INJECTION_RATE
    )
    assert result["injected_rows_out_of_range"] > 0
    assert result["injected_rows_in_range_implausible"] > 0

    anomaly_detector._MODEL_CACHE.clear()


# ──────────────────────────────────────────────────────────────────────────────
# CANDIDATE_ESTIMATORS / no-eager-sklearn-import (v1.3 Phase 2 Plan 02-02, D-03)
# ──────────────────────────────────────────────────────────────────────────────


def test_candidate_estimators_has_exactly_three_keys_and_fresh_instances():
    assert sorted(at.CANDIDATE_ESTIMATORS) == [
        "EllipticEnvelope", "IsolationForest", "OneClassSVM",
    ]

    for name, factory in at.CANDIDATE_ESTIMATORS.items():
        est_1 = factory(0.02)
        est_2 = factory(0.02)
        assert est_1 is not est_2, f"{name} factory returned the same instance twice"


def test_no_eager_sklearn_import():
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; import anomaly_training; print('sklearn' in sys.modules)"],
        capture_output=True, text=True, cwd=backend_dir,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


# ──────────────────────────────────────────────────────────────────────────────
# select_winner -- deterministic selection rule (v1.3 Phase 2 Plan 02-02, D-04)
# ──────────────────────────────────────────────────────────────────────────────


def _fake_measurement(candidate, contamination, recall_pooled, false_positive_rate):
    return {
        "candidate": candidate,
        "contamination": contamination,
        "recall_pooled": recall_pooled,
        "false_positive_rate": false_positive_rate,
    }


def test_select_winner_returns_highest_eligible_pooled_recall():
    ceiling = config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE
    measurements = [
        _fake_measurement("IsolationForest", 0.01, 0.80, ceiling - 0.01),
        _fake_measurement("EllipticEnvelope", 0.01, 0.60, ceiling - 0.02),
        _fake_measurement("OneClassSVM", 0.01, 0.40, ceiling - 0.005),
    ]
    report = {"measurements": measurements}

    winner, contamination, ceiling_met = at.select_winner(report)

    assert winner == "IsolationForest"
    assert contamination == 0.01
    assert ceiling_met is True


def test_select_winner_falls_back_to_lowest_false_positive_when_none_eligible():
    ceiling = config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE
    measurements = [
        _fake_measurement("IsolationForest", 0.01, 0.80, ceiling + 0.05),
        _fake_measurement("EllipticEnvelope", 0.01, 0.60, ceiling + 0.01),
        _fake_measurement("OneClassSVM", 0.01, 0.40, ceiling + 0.10),
    ]
    report = {"measurements": measurements}

    winner, contamination, ceiling_met = at.select_winner(report)

    assert winner == "EllipticEnvelope"
    assert ceiling_met is False


def test_select_winner_recall_tie_breaks_by_false_positive_rate():
    measurements = [
        _fake_measurement("IsolationForest", 0.01, 0.70, 0.03),
        _fake_measurement("EllipticEnvelope", 0.01, 0.70, 0.01),
        _fake_measurement("OneClassSVM", 0.01, 0.50, 0.02),
    ]
    report = {"measurements": measurements}

    winner, contamination, ceiling_met = at.select_winner(report)

    assert winner == "EllipticEnvelope"


def test_select_winner_further_tie_breaks_by_insertion_order():
    measurements = [
        _fake_measurement("IsolationForest", 0.01, 0.70, 0.02),
        _fake_measurement("EllipticEnvelope", 0.01, 0.70, 0.02),
        _fake_measurement("OneClassSVM", 0.01, 0.40, 0.10),
    ]
    report = {"measurements": measurements}

    winner, contamination, ceiling_met = at.select_winner(report)

    # CANDIDATE_ESTIMATORS insertion order: IsolationForest, EllipticEnvelope,
    # OneClassSVM -- IsolationForest wins the further tie.
    assert winner == "IsolationForest"


def test_select_winner_raises_on_missing_or_non_finite_measurement():
    measurements_missing = [
        _fake_measurement("IsolationForest", 0.01, 0.70, 0.02),
        _fake_measurement("EllipticEnvelope", 0.01, 0.70, 0.02),
        # OneClassSVM missing entirely.
    ]
    with pytest.raises(ValueError) as exc_info:
        at.select_winner({"measurements": measurements_missing})
    assert "OneClassSVM" in str(exc_info.value)

    measurements_nonfinite = [
        _fake_measurement("IsolationForest", 0.01, float("nan"), 0.02),
        _fake_measurement("EllipticEnvelope", 0.01, 0.70, 0.02),
        _fake_measurement("OneClassSVM", 0.01, 0.40, 0.02),
    ]
    with pytest.raises(ValueError) as exc_info:
        at.select_winner({"measurements": measurements_nonfinite})
    assert "IsolationForest" in str(exc_info.value)
