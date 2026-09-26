"""
Tests for backend/anomaly_detector.py (C10 -- Learned Anomaly Detection,
requirement DS-F12).

Covers the detector in isolation: the D-04 forecast-residual primary
signal, the D-04 rolling-baseline cold-start fallback, the D-06
per-location control-limit resolution via `for_corridor`, and the D-05
guarantee that a trip resolves only through `DLRSafetyMonitor`'s existing
`_fallback` helper -- never a second, competing result shape.
`backend/tests/predictive_tracer_test.py` covers this detector's path
through the monitor end to end; this file covers the detector's own
decision logic.

Structure follows `backend/tests/SafetyMonitor_TestSuite.py`'s convention:
module-level imports, `@pytest.fixture`, one `test_*` per behavior, plain
asserts, no classes.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

import anomaly_detector
import config
import thermal_model
from ampacity_forecast import ForecastResult
from anomaly_detector import ROLLING_BASELINE_MIN_ROWS, AnomalyDetector
from DLRSafetyMonitor import DLRSafetyMonitor


def _forecast(amps=1000.0, ci_lower_amps=900.0, ci_upper_amps=1100.0):
    return ForecastResult(
        horizon_min=60.0,
        amps=amps,
        ci_lower_amps=ci_lower_amps,
        ci_upper_amps=ci_upper_amps,
        n_observations=50,
        method="naive",
    )


@pytest.fixture
def fitted_anomaly_model():
    """
    A genuinely fitted, small `IsolationForest` over a deterministic
    synthetic three-column envelope (air_temp, wind_speed,
    solar_radiation, in `config.ANOMALY_ML_RAW_DATA_KEYS` order) -- a
    really-fitted estimator, not a hand-written stub prediction method,
    so these tests exercise the real `predict`/`decision_function` path
    with no disk I/O and no network.
    """
    rng = np.random.default_rng(20260924)
    n = 300
    temp = rng.normal(25.0, 5.0, size=n)
    wind = np.clip(rng.normal(8.0, 3.0, size=n), 0.0, None)
    solar = np.clip(rng.normal(400.0, 150.0, size=n), 0.0, None)
    X = np.column_stack([temp, wind, solar])

    model = IsolationForest(n_estimators=50, contamination=0.02, random_state=20260924)
    model.fit(X)
    return model


# ──────────────────────────────────────────────────────────────────────────────
# Forecast-residual branch (D-04 primary signal)
# ──────────────────────────────────────────────────────────────────────────────


def test_forecast_far_outside_band_trips_and_names_limits():
    detector = AnomalyDetector(forecast=_forecast(), k=1.0)

    is_anomalous, reason = detector.check({}, 2000.0)

    assert is_anomalous is True
    assert "900.0" in reason
    assert "1100.0" in reason
    assert detector.signal == "forecast_residual"


def test_forecast_inclusive_boundary_not_anomalous():
    detector = AnomalyDetector(forecast=_forecast(), k=1.0)

    lower_is_anomalous, _ = detector.check({}, 900.0)
    upper_is_anomalous, _ = detector.check({}, 1100.0)

    assert lower_is_anomalous is False
    assert upper_is_anomalous is False
    assert detector.signal == "forecast_residual"


# ──────────────────────────────────────────────────────────────────────────────
# Rolling-baseline branch (D-04 cold-start path)
# ──────────────────────────────────────────────────────────────────────────────


def test_rolling_baseline_trips_far_from_mean():
    rng = np.random.default_rng(42)
    series = rng.normal(1700.0, 50.0, size=500)
    history = pd.DataFrame({"dlr_amps": series})
    detector = AnomalyDetector(history=history, k=config.DEFAULT_ANOMALY_CONTROL_LIMIT_K)

    mean = float(history["dlr_amps"].mean())
    std = float(history["dlr_amps"].std())
    far_rating = mean + 10 * std

    is_anomalous, reason = detector.check({}, far_rating)

    assert is_anomalous is True
    assert detector.signal == "rolling_baseline"
    assert "rolling" in reason.lower()


def test_rolling_baseline_cold_start_below_min_rows():
    history = pd.DataFrame({"dlr_amps": [1700.0, 1690.0, 1710.0, 1705.0, 1695.0]})
    detector = AnomalyDetector(history=history)

    is_anomalous, reason = detector.check({}, 5000.0)

    assert is_anomalous is False
    assert "cold start" in reason.lower()
    assert detector.signal == "cold_start"


def test_rolling_baseline_constant_history_returns_false_not_zero_division():
    history = pd.DataFrame({"dlr_amps": [1700.0] * ROLLING_BASELINE_MIN_ROWS})
    detector = AnomalyDetector(history=history)

    is_anomalous, reason = detector.check({}, 5000.0)

    assert is_anomalous is False
    assert detector.signal == "rolling_baseline"


def test_clean_data_no_false_positive():
    # Baseline history and the checked series are drawn from the same
    # generator/distribution but are independent samples (baseline is not
    # simply re-checked against itself), covering a full four-week
    # (672 hourly observations) synthetic series with zero false trips.
    rng = np.random.default_rng(7)
    baseline = rng.normal(1700.0, 50.0, size=500)
    history = pd.DataFrame({"dlr_amps": baseline})
    detector = AnomalyDetector(history=history, k=config.DEFAULT_ANOMALY_CONTROL_LIMIT_K)

    four_weeks_hourly = 4 * 7 * 24
    test_series = rng.normal(1700.0, 50.0, size=four_weeks_hourly)

    for rating in test_series:
        is_anomalous, _ = detector.check({}, float(rating))
        assert is_anomalous is False


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher edge cases
# ──────────────────────────────────────────────────────────────────────────────


def test_non_finite_rating_defers_to_g3_g4():
    detector = AnomalyDetector(forecast=_forecast())

    is_anomalous, reason = detector.check({}, float("nan"))

    assert is_anomalous is False
    assert "non-finite" in reason
    assert detector.signal == "non_finite_guard"


def test_check_dispatch_prefers_forecast_over_history_when_both_present():
    # Forecast band [900, 1100] (k=1) would not trip at 1700; a rolling
    # baseline built from a tight 1700-centered history would trip at
    # 1700 too, so this only distinguishes branches if the forecast branch
    # actually wins -- assert via detector.signal, not just the outcome.
    history = pd.DataFrame({"dlr_amps": [1700.0] * (ROLLING_BASELINE_MIN_ROWS + 10)})
    detector = AnomalyDetector(forecast=_forecast(), history=history, k=1.0)

    detector.check({}, 1000.0)

    assert detector.signal == "forecast_residual"


def test_signal_starts_not_yet_evaluated():
    detector = AnomalyDetector()
    assert detector.signal == "not_yet_evaluated"


def test_check_always_returns_two_tuple_of_bool_and_str():
    detector = AnomalyDetector()
    result = detector.check({}, 1000.0)

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert isinstance(result[1], str)


# ──────────────────────────────────────────────────────────────────────────────
# for_corridor (D-06 per-location control limit)
# ──────────────────────────────────────────────────────────────────────────────


def test_corridor_k_is_the_wider_of_two_endpoints():
    detector = AnomalyDetector.for_corridor("MIDLAND_EL_PASO")

    expected = max(
        config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION["MIDLAND"],
        config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION["EL_PASO"],
    )
    assert detector.k == expected


def test_for_corridor_unknown_corridor_raises_key_error():
    with pytest.raises(KeyError) as exc_info:
        AnomalyDetector.for_corridor("NOT_A_CORRIDOR")

    assert "AUSTIN_CORPUS_CHRISTI" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────────────
# D-05: a trip resolves only through DLRSafetyMonitor._fallback
# ──────────────────────────────────────────────────────────────────────────────


def test_anomaly_resolves_through_existing_fallback_contract():
    # A tight forecast band the overridden computed rating clears G1-G5
    # cleanly but deviates far from, so the trip is attributable to G6
    # alone.
    detector = AnomalyDetector(forecast=_forecast(amps=1000.0, ci_lower_amps=990.0, ci_upper_amps=1010.0), k=1.0)

    monitor = DLRSafetyMonitor(
        static_rating=1690.0,
        conductor=thermal_model.ConductorConfig(**config.DEFAULT_CONDUCTOR_CONFIG_KWARGS),
        anomaly_detector=detector,
        logger=lambda msg: None,
    )
    monitor._compute_ampacity = lambda d: 1700.0  # clears G4/G5, deviates from the tight forecast band above

    valid_data = {
        "sensor_status": "ok", "link_status": "ok",
        "wind": 5.0, "temp": 25.0, "solar": 500.0,
    }

    result = monitor.run_check(valid_data)

    assert sorted(result.keys()) == ["alerts", "fallback", "rating", "status"]
    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert result["alerts"][0].startswith("G6 FAIL")


# ──────────────────────────────────────────────────────────────────────────────
# Model branch (v1.3 Phase 2, ANOM-01) -- additive third signal on raw readings
# ──────────────────────────────────────────────────────────────────────────────


def test_model_path_rejects_unknown_corridor_naming_valid_corridors():
    with pytest.raises(ValueError) as exc_info:
        anomaly_detector._model_path_for("../../etc/passwd")

    message = str(exc_info.value)
    assert "AUSTIN_CORPUS_CHRISTI" in message
    assert "MIDLAND_EL_PASO" in message


def test_model_branch_returns_two_tuple_of_bool_and_str(fitted_anomaly_model):
    detector = AnomalyDetector(model=fitted_anomaly_model)

    result = detector.check({"wind": 8.0, "temp": 25.0, "solar": 400.0}, 1000.0)

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert isinstance(result[1], str)


def test_model_clean_reading_inside_envelope(fitted_anomaly_model):
    detector = AnomalyDetector(model=fitted_anomaly_model)

    is_anomalous, reason = detector.check({"wind": 8.0, "temp": 25.0, "solar": 400.0}, 1000.0)

    assert is_anomalous is False
    assert detector.signal == "model_clean"


def test_model_trip_reading_far_outside_envelope(fitted_anomaly_model):
    detector = AnomalyDetector(model=fitted_anomaly_model)

    is_anomalous, reason = detector.check(
        {"wind": 45.0, "temp": -15.0, "solar": 1350.0}, 1000.0
    )

    assert is_anomalous is True
    assert detector.signal == "model_trip"


# ──────────────────────────────────────────────────────────────────────────────
# Fail-safe and OR-combination invariants (v1.3 Phase 2 Plan 02-01 Task 2)
# ──────────────────────────────────────────────────────────────────────────────


class _RaisingModel:
    """A minimal raising stand-in whose prediction entry point always
    raises a distinctive exception -- proves a broken model propagates
    all the way to G6's existing fail-safe handler rather than being
    caught by a second, competing exception path inside this module."""

    def predict(self, X):
        raise RuntimeError("distinctive_model_failure_marker")


class _AlwaysInlierModel:
    """Deterministic stand-in that always votes not-anomalous."""

    def predict(self, X):
        return np.array([1] * len(X))

    def decision_function(self, X):
        return np.array([0.5] * len(X))


class _AlwaysOutlierModel:
    """Deterministic stand-in that always votes anomalous."""

    def predict(self, X):
        return np.array([-1] * len(X))

    def decision_function(self, X):
        return np.array([-0.5] * len(X))


_MODEL_BRANCH_RAW_DATA = {"wind": 5.0, "temp": 25.0, "solar": 500.0}


def test_model_failure_resolves_to_static_rating():
    detector = AnomalyDetector(model=_RaisingModel())

    monitor = DLRSafetyMonitor(
        static_rating=1690.0,
        conductor=thermal_model.ConductorConfig(**config.DEFAULT_CONDUCTOR_CONFIG_KWARGS),
        anomaly_detector=detector,
        logger=lambda msg: None,
    )
    monitor._compute_ampacity = lambda d: 1700.0  # clears G4/G5

    valid_data = {
        "sensor_status": "ok", "link_status": "ok",
        "wind": 5.0, "temp": 25.0, "solar": 500.0,
    }

    result = monitor.run_check(valid_data)

    assert sorted(result.keys()) == ["alerts", "fallback", "rating", "status"]
    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert result["alerts"][0].startswith("G6 FAIL")
    assert "distinctive_model_failure_marker" in result["alerts"][0]


def test_model_exception_propagates_out_of_check():
    detector = AnomalyDetector(model=_RaisingModel())

    with pytest.raises(RuntimeError, match="distinctive_model_failure_marker"):
        detector.check(_MODEL_BRANCH_RAW_DATA, 1700.0)


def test_model_cannot_suppress_existing_trip():
    # Tight forecast band [990, 1010] (k=1); rating 1700 trips the
    # forecast branch. A model that always votes not-anomalous must not
    # suppress that trip (D-06).
    detector = AnomalyDetector(
        forecast=_forecast(amps=1000.0, ci_lower_amps=990.0, ci_upper_amps=1010.0),
        model=_AlwaysInlierModel(),
        k=1.0,
    )

    is_anomalous, reason = detector.check(_MODEL_BRANCH_RAW_DATA, 1700.0)

    assert is_anomalous is True
    assert "990.0" in reason
    assert "1010.0" in reason
    assert "forecast_residual" in detector.signal
    assert "model_clean" in detector.signal


def test_model_can_trip_on_its_own():
    # Forecast band [900, 1100] (k=1); rating 1000 is comfortably inside
    # it (a clean forecast verdict). A model that always votes anomalous
    # must still trip the overall check (D-06's "add caution" half).
    detector = AnomalyDetector(
        forecast=_forecast(amps=1000.0, ci_lower_amps=900.0, ci_upper_amps=1100.0),
        model=_AlwaysOutlierModel(),
        k=1.0,
    )

    is_anomalous, reason = detector.check(_MODEL_BRANCH_RAW_DATA, 1000.0)

    assert is_anomalous is True
    assert "model flagged" in reason
    assert "forecast_residual" in detector.signal
    assert "model_trip" in detector.signal


def test_both_branches_clean_returns_false_with_both_reasons():
    detector = AnomalyDetector(
        forecast=_forecast(amps=1000.0, ci_lower_amps=900.0, ci_upper_amps=1100.0),
        model=_AlwaysInlierModel(),
        k=1.0,
    )

    is_anomalous, reason = detector.check(_MODEL_BRANCH_RAW_DATA, 1000.0)

    assert is_anomalous is False
    assert "within widened forecast band" in reason
    assert "model judged reading" in reason


@pytest.mark.parametrize("key", ["wind", "temp", "solar"])
@pytest.mark.parametrize("malformed", ["absent", "none", "non_finite"])
def test_missing_raw_field_raises_rather_than_substituting(malformed, key, fitted_anomaly_model):
    raw_data = dict(_MODEL_BRANCH_RAW_DATA)
    if malformed == "absent":
        del raw_data[key]
    elif malformed == "none":
        raw_data[key] = None
    else:
        raw_data[key] = float("nan")

    detector = AnomalyDetector(model=fitted_anomaly_model)

    with pytest.raises(ValueError) as exc_info:
        detector.check(raw_data, 1000.0)

    assert key in str(exc_info.value)


def test_non_finite_rating_still_skips_model_branch(fitted_anomaly_model):
    detector = AnomalyDetector(model=fitted_anomaly_model)

    is_anomalous, reason = detector.check(_MODEL_BRANCH_RAW_DATA, float("nan"))

    assert is_anomalous is False
    assert detector.signal == "non_finite_guard"
