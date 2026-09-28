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

import importlib
import json
import math
import os
import subprocess
import sys
import time

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


# ──────────────────────────────────────────────────────────────────────────────
# D-02 boundary guard (v1.3 Phase 2 Plan 02-03, ANOM-01): load stays
# training-time only and never reaches the live check() path
# ──────────────────────────────────────────────────────────────────────────────

def test_load_is_training_time_only_and_never_reaches_check():
    """
    Asserts all four halves of the D-02 boundary together, so a partial
    regression cannot pass:

    1. `backend/anomaly_detector.py`'s own SOURCE (not just its current
       import state) contains no import of `ercot_data_retriever` or
       `gridstatus`.
    2. No name in `config.ANOMALY_ML_FEATURE_COLUMNS` or
       `config.ANOMALY_ML_RAW_DATA_KEYS` contains "load".
    3. Freshly importing `anomaly_detector` (with `gridstatus` evicted
       from `sys.modules` first, so this check is not fooled by an
       unrelated test module -- e.g. `ercot_data_retriever_test.py` --
       having already imported `gridstatus` earlier in the same session)
       leaves `gridstatus` OUT of `sys.modules`.
    4. An `AnomalyDetector` holding a fitted three-feature model returns
       a normal `(bool, str)` two-tuple for a `raw_data` carrying exactly
       `wind`/`temp`/`solar` -- proving the live call site needs no load
       field.
    """
    # Half 1: source-level import ban (not just today's sys.modules state).
    detector_path = anomaly_detector.__file__
    with open(detector_path) as fh:
        detector_source = fh.read()
    for line in detector_source.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("import ercot_data_retriever"), line
        assert not stripped.startswith("from ercot_data_retriever"), line
        assert not stripped.startswith("import gridstatus"), line
        assert not stripped.startswith("from gridstatus"), line

    # Half 2: no "load" name in either config feature tuple.
    all_names = list(config.ANOMALY_ML_FEATURE_COLUMNS) + list(
        config.ANOMALY_ML_RAW_DATA_KEYS
    )
    assert not any("load" in name.lower() for name in all_names)

    # Half 3: importing anomaly_detector fresh does not pull in gridstatus.
    sys.modules.pop("gridstatus", None)
    sys.modules.pop("anomaly_detector", None)
    importlib.import_module("anomaly_detector")
    assert "gridstatus" not in sys.modules

    # Half 4: a normal two-tuple verdict on exactly wind/temp/solar.
    import anomaly_detector as reloaded_anomaly_detector
    from sklearn.ensemble import IsolationForest

    rng = np.random.default_rng(20260924)
    model = IsolationForest(
        n_estimators=10, contamination=0.1, random_state=20260924,
    ).fit(rng.normal(size=(50, 3)))

    detector = reloaded_anomaly_detector.AnomalyDetector(model=model)
    result = detector.check({"wind": 5.0, "temp": 20.0, "solar": 300.0}, 1000.0)

    assert isinstance(result, tuple)
    assert len(result) == 2
    is_anomalous, reason = result
    assert isinstance(is_anomalous, bool)
    assert isinstance(reason, str)


def test_characterize_load_reports_the_retrieved_window_not_the_requested_one(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(config, "ANOMALY_ML_MODEL_DIR", str(tmp_path))
    corridor = "AUSTIN_CORPUS_CHRISTI"

    # Pre-seed the pooled observation frame on disk so characterize_load
    # never calls corridor_observation_frame (no live Open-Meteo fetch).
    obs_frame = _synthetic_observation_frame(n=48)
    obs_path = os.path.join(
        config.ANOMALY_ML_MODEL_DIR,
        config.ANOMALY_ML_OBSERVATION_FRAME_TEMPLATE.format(corridor=corridor),
    )
    obs_frame.to_csv(obs_path, index=False)

    # The requested window (config.ANOMALY_ML_LOAD_YEARS=1 by default)
    # spans a full calendar year, but the fake pull_ercot_data deliberately
    # returns a much SHORTER span -- the report must reflect what actually
    # came back, never the request (T-02-12).
    short_frame = pd.DataFrame({
        "datetime_utc": pd.to_datetime(obs_frame["datetime_utc"].iloc[:5], utc=True),
        "ercot_south_load_mw": [1000.0, 1010.0, 1020.0, 1030.0, 1040.0],
    })
    short_frame.attrs["load_column"] = "ercot_south_load_mw"
    short_frame.attrs["zone_columns_matched"] = ["South", "South Central"]

    def _fake_pull(start, end, zone_substrings=None, save=True):
        return short_frame

    monkeypatch.setattr(at.ercot_data_retriever, "pull_ercot_data", _fake_pull)

    result = at.characterize_load(corridor, years=1)

    assert result["available"] is True
    assert result["load_rows"] == 5
    assert result["zone_columns"] == ["South", "South Central"]
    expected_start = pd.Timestamp(short_frame["datetime_utc"].min()).isoformat()
    expected_end = pd.Timestamp(short_frame["datetime_utc"].max()).isoformat()
    assert result["window_start"] == expected_start
    assert result["window_end"] == expected_end
    assert set(result["correlations"]) == set(config.ANOMALY_ML_FEATURE_COLUMNS)


def test_characterize_load_records_unavailability_without_raising(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ANOMALY_ML_MODEL_DIR", str(tmp_path))
    corridor = "MIDLAND_EL_PASO"

    def _raising_pull(start, end, zone_substrings=None, save=True):
        raise RuntimeError("simulated ERCOT network failure")

    monkeypatch.setattr(at.ercot_data_retriever, "pull_ercot_data", _raising_pull)

    result = at.characterize_load(corridor, years=1)

    assert result["available"] is False
    assert result["corridor"] == corridor
    assert "simulated ERCOT network failure" in result["error"]
    assert "zone_substrings" in result


# ──────────────────────────────────────────────────────────────────────────────
# merge_corridor_report (v1.3 Phase 2 Plan 02-05, CR-01): a corridor-scoped
# re-run must carry forward, never delete, the other corridor's evidence.
# ──────────────────────────────────────────────────────────────────────────────


def _fake_fetch_city_weather_factory(n=150, seed_offset=0):
    """
    A `forecast_training.fetch_city_weather`-shaped stand-in covering all
    four endpoint cities in `config.CORRIDOR_ENDPOINTS`, so `_run_bakeoff`/
    `_run_validate` can run for both corridors with no network access.
    """
    frames_by_city = {
        "AUSTIN": _synthetic_city_weather_frame("AUSTIN", n=n, seed=500 + seed_offset),
        "CORPUS_CHRISTI": _synthetic_city_weather_frame(
            "CORPUS_CHRISTI", n=n, seed=501 + seed_offset
        ),
        "MIDLAND": _synthetic_city_weather_frame("MIDLAND", n=n, seed=502 + seed_offset),
        "EL_PASO": _synthetic_city_weather_frame("EL_PASO", n=n, seed=503 + seed_offset),
    }

    def _fetch(city, years):
        return frames_by_city[city].copy()

    return _fetch


def test_merge_corridor_report_carries_forward_corridors_absent_from_this_run(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(config, "ANOMALY_ML_MODEL_DIR", str(tmp_path))
    report_name = "fake_merge_report.json"
    report_path = os.path.join(str(tmp_path), report_name)

    seeded = {
        "AUSTIN_CORPUS_CHRISTI": {"measurements": [1, 2, 3], "winner": "OneClassSVM"},
        "MIDLAND_EL_PASO": {"measurements": [4, 5], "winner": "IsolationForest"},
    }
    with open(report_path, "w") as fh:
        json.dump(seeded, fh)

    new_entries = {
        "MIDLAND_EL_PASO": {"measurements": [9, 9, 9], "winner": "EllipticEnvelope"},
    }

    result_path = at.merge_corridor_report(report_name, new_entries, "bakeoff")

    assert result_path == report_path
    with open(report_path) as fh:
        written = json.load(fh)

    assert set(written) == {"AUSTIN_CORPUS_CHRISTI", "MIDLAND_EL_PASO"}
    # Untouched corridor carried forward verbatim.
    assert written["AUSTIN_CORPUS_CHRISTI"] == seeded["AUSTIN_CORPUS_CHRISTI"]
    # Processed corridor replaced wholesale, not field-blended with the old entry.
    assert written["MIDLAND_EL_PASO"]["measurements"] == [9, 9, 9]
    assert written["MIDLAND_EL_PASO"]["winner"] == "EllipticEnvelope"
    assert written["MIDLAND_EL_PASO"]["produced_by"] == "bakeoff"
    assert "generated_at" in written["MIDLAND_EL_PASO"]


def test_bakeoff_rerun_for_one_corridor_preserves_the_other_corridors_entry(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(config, "ANOMALY_ML_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(
        forecast_training,
        "fetch_city_weather",
        _fake_fetch_city_weather_factory(n=150, seed_offset=0),
    )
    anomaly_detector._MODEL_CACHE.clear()

    corridors = ["AUSTIN_CORPUS_CHRISTI", "MIDLAND_EL_PASO"]
    at._run_bakeoff(corridors, years=1)

    report_path = os.path.join(
        str(tmp_path), config.ANOMALY_ML_VALIDATION_REPORT_NAME
    )
    with open(report_path) as fh:
        snapshot = json.load(fh)

    assert set(snapshot) == set(corridors)
    for corridor in corridors:
        assert "measurements" in snapshot[corridor]
        assert "winner" in snapshot[corridor]
        assert "selected_contamination" in snapshot[corridor]

    time.sleep(0.01)
    at._run_bakeoff(["MIDLAND_EL_PASO"], years=1)

    with open(report_path) as fh:
        after = json.load(fh)

    assert set(after) == set(corridors)
    # The unprocessed corridor's entry is identical to the snapshot -- carried
    # forward, not regenerated and not field-blended.
    assert after["AUSTIN_CORPUS_CHRISTI"] == snapshot["AUSTIN_CORPUS_CHRISTI"]
    # The re-measured corridor is stamped with this run's provenance, and its
    # transcription-gate fields (Plan 02-04's TRANSCRIPTION_OK) survive.
    assert after["MIDLAND_EL_PASO"]["produced_by"] == "bakeoff"
    assert (
        after["MIDLAND_EL_PASO"]["generated_at"]
        > after["AUSTIN_CORPUS_CHRISTI"]["generated_at"]
    )
    assert "measurements" in after["MIDLAND_EL_PASO"]
    assert "winner" in after["MIDLAND_EL_PASO"]
    assert "selected_contamination" in after["MIDLAND_EL_PASO"]

    anomaly_detector._MODEL_CACHE.clear()
