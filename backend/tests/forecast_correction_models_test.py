"""
Tests for backend/forecast_correction_models.py (Phase 3 Plan 05, D-02).

Covers the wind-correction family (arm 3): fit/predict entirely in u/v
space, a constant-vector-offset recovery on held-out rows, a
0/360-wrap-straddling regression test (the exact failure mode
`wind_vector.py` exists to prevent), both pooling strategies, and the
validation-only selector. Follows this suite's existing conventions:
module-level imports, plain asserts, no classes for tests themselves (one
lightweight geometry stand-in is a plain class), deterministic synthetic
inputs, no network.
"""

import math
import os
import subprocess
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import forecast_correction_models as m
import thermal_model
import wind_vector as wv


class _FakeGeometry:
    """
    Minimal `corridor_discretization.CorridorGeometry` duck type
    (`bearing_deg`, `conductor`) -- `forecast_correction_models` never
    imports `corridor_discretization` itself (staying decoupled from the
    experiment harness's own geometry construction), so tests supply their
    own lightweight stand-in.
    """

    def __init__(self, bearing_deg=90.0, conductor=None):
        self.bearing_deg = bearing_deg
        self.conductor = conductor or thermal_model.ConductorConfig()


def _timestamps(n, seed_dt=datetime(2026, 1, 1)):
    return [(seed_dt + timedelta(hours=i)).isoformat() for i in range(n)]


def _synthetic_wind_frame(
    n=220, seed=20260929, offset_u=0.0, offset_v=0.0, noise_std=0.1,
    two_cities=True, geometry=None,
):
    """
    Deterministic corridor-shaped synthetic frame for the wind-correction
    family: `fcst_wind_*` is the truth wind offset by a constant (u, v)
    vector plus noise, `anchor_wind_*` is a noisy observation of truth,
    and `truth_ampacity` is computed directly through `thermal_model` from
    the truth wind so `select_wind_configuration`'s ampacity-MAE scoring
    has something real to score against.
    """
    geometry = geometry or _FakeGeometry()
    rng = np.random.default_rng(seed)

    truth_speed = np.clip(5.0 + rng.normal(0.0, 2.0, n), 0.2, None)
    truth_dir = rng.uniform(0.0, 360.0, n)
    truth_u, truth_v = wv.to_uv(truth_speed, truth_dir)

    fcst_u = truth_u + offset_u + rng.normal(0.0, noise_std, n)
    fcst_v = truth_v + offset_v + rng.normal(0.0, noise_std, n)
    fcst_speed, fcst_dir = wv.from_uv(fcst_u, fcst_v)

    anchor_u = truth_u + rng.normal(0.0, noise_std, n)
    anchor_v = truth_v + rng.normal(0.0, noise_std, n)
    anchor_speed, anchor_dir = wv.from_uv(anchor_u, anchor_v)

    air_temp = 25.0 + rng.normal(0.0, 3.0, n)
    solar = 500.0 + rng.normal(0.0, 40.0, n)

    perp_truth = thermal_model.perpendicular_wind(truth_speed, truth_dir, geometry.bearing_deg)
    truth_ampacity = thermal_model.ieee738_ampacity(
        air_temp, perp_truth, solar, geometry.conductor
    )

    if two_cities:
        cities = np.where(np.arange(n) % 2 == 0, "CITY_A", "CITY_B")
    else:
        cities = np.full(n, "CITY_A")

    return pd.DataFrame({
        "datetime_utc": _timestamps(n),
        "endpoint_city": cities,
        "fcst_wind_speed": fcst_speed,
        "fcst_wind_direction": fcst_dir,
        "anchor_wind_speed": anchor_speed,
        "anchor_wind_direction": anchor_dir,
        "truth_wind_speed": truth_speed,
        "truth_wind_direction": truth_dir,
        "fcst_air_temp": air_temp,
        "fcst_solar_radiation": solar,
        "truth_ampacity": truth_ampacity,
    })


def _synthetic_cooling_frame(
    n=220, seed=20260929, wind_factor=1.3, temp_offset=-2.0, noise_std=0.05,
    wind_scale=1.0, geometry=None,
):
    """
    Deterministic synthetic frame for the cooling-correction family: the
    truth convective term is genuinely different from the forecast's own
    term (truth wind is `wind_factor` times the forecast wind and truth
    air temperature is offset by `temp_offset`, both plus noise) --
    something real for `fit_cooling_correction` to recover. `wind_scale`
    uniformly scales the whole scenario's wind magnitude, holding the
    forecast/truth *relationship* fixed, purpose-built for the log-ratio
    invariance test (Task 3's rescaling assertion).
    """
    geometry = geometry or _FakeGeometry()
    rng = np.random.default_rng(seed)

    fcst_air_temp = 25.0 + rng.normal(0.0, 3.0, n)
    fcst_perp_wind = np.clip((4.0 + rng.normal(0.0, 1.2, n)) * wind_scale, 0.3, None)

    truth_air_temp = fcst_air_temp + temp_offset + rng.normal(0.0, noise_std, n)
    truth_perp_wind = np.clip(
        fcst_perp_wind * wind_factor + rng.normal(0.0, noise_std * wind_scale, n),
        0.3, None,
    )

    anchor_air_temp = fcst_air_temp + rng.normal(0.0, noise_std, n)
    anchor_perp_wind = np.clip(
        fcst_perp_wind + rng.normal(0.0, noise_std * wind_scale, n), 0.3, None
    )

    fcst_solar = 500.0 + rng.normal(0.0, 40.0, n)
    truth_solar = fcst_solar + rng.normal(0.0, 5.0, n)

    truth_ampacity = thermal_model.ieee738_ampacity(
        truth_air_temp, truth_perp_wind, truth_solar, geometry.conductor
    )

    return pd.DataFrame({
        "datetime_utc": _timestamps(n),
        "fcst_air_temp": fcst_air_temp,
        "fcst_perp_wind_ms": fcst_perp_wind,
        "fcst_solar_radiation": fcst_solar,
        "anchor_air_temp": anchor_air_temp,
        "anchor_perp_wind_ms": anchor_perp_wind,
        "truth_air_temp": truth_air_temp,
        "truth_perp_wind_ms": truth_perp_wind,
        "truth_solar_radiation": truth_solar,
        "truth_ampacity": truth_ampacity,
    })


def _synthetic_rotation_frame(n=360, rotation_deg=2.0):
    """
    Full-circle, zero-noise rotation frame purpose-built for the
    wrap-straddling test: truth = fcst rotated by a small constant angle,
    with `fcst_wind_direction` sweeping every integer degree 0..359 so the
    0/360 seam sits directly inside the swept range (row 359 has
    `fcst_wind_direction=359`, `truth_wind_direction=(359+2)%360=1` -- two
    degrees apart, not 358).
    """
    fcst_dir = np.arange(n, dtype=float) % 360.0
    fcst_speed = np.full(n, 6.0)
    truth_dir = (fcst_dir + rotation_deg) % 360.0
    truth_speed = fcst_speed.copy()

    return pd.DataFrame({
        "datetime_utc": _timestamps(n),
        "endpoint_city": np.full(n, "CITY_A"),
        "fcst_wind_speed": fcst_speed,
        "fcst_wind_direction": fcst_dir,
        "anchor_wind_speed": fcst_speed,
        "anchor_wind_direction": fcst_dir,
        "truth_wind_speed": truth_speed,
        "truth_wind_direction": truth_dir,
        "fcst_air_temp": np.full(n, 25.0),
        "fcst_solar_radiation": np.full(n, 500.0),
    })


# ──────────────────────────────────────────────────────────────────────────────
# WIND_CORRECTION_ESTIMATORS — fresh, never-before-fit factories
# ──────────────────────────────────────────────────────────────────────────────

def test_wind_correction_estimators_are_two_fresh_factories():
    assert len(m.WIND_CORRECTION_ESTIMATORS) == 2
    for name, factory in m.WIND_CORRECTION_ESTIMATORS.items():
        a, b = factory(), factory()
        assert a is not b, f"{name} returned a shared instance, not a fresh one"


# ──────────────────────────────────────────────────────────────────────────────
# Constant vector offset recovery (D-02 approach 3's central claim)
# ──────────────────────────────────────────────────────────────────────────────

def test_wind_correction_recovers_known_vector_offset_on_held_out_rows():
    frame = _synthetic_wind_frame(offset_u=1.3, offset_v=-0.9, noise_std=0.1)
    train = frame.iloc[:160].reset_index(drop=True)
    val = frame.iloc[160:].reset_index(drop=True)

    factory = m.WIND_CORRECTION_ESTIMATORS["LinearRegression"]
    model = m.fit_wind_correction(train, factory, pooling="per_city")
    pred = m.predict_wind_correction(model, val)

    truth_u, truth_v = wv.to_uv(
        val["truth_wind_speed"].to_numpy(dtype=float),
        val["truth_wind_direction"].to_numpy(dtype=float),
    )
    fcst_u, fcst_v = wv.to_uv(
        val["fcst_wind_speed"].to_numpy(dtype=float),
        val["fcst_wind_direction"].to_numpy(dtype=float),
    )
    corrected_u, corrected_v = wv.to_uv(pred.speed, pred.direction)

    raw_err = float(np.mean(np.hypot(fcst_u - truth_u, fcst_v - truth_v)))
    corrected_err = float(np.mean(np.hypot(corrected_u - truth_u, corrected_v - truth_v)))

    assert corrected_err < raw_err * 0.5, (
        f"corrected error ({corrected_err}) is not substantially smaller "
        f"than raw forecast error ({raw_err}) -- the correction did not "
        f"recover the planted constant vector offset"
    )


# ──────────────────────────────────────────────────────────────────────────────
# A perfect forecast should be left essentially unchanged
# ──────────────────────────────────────────────────────────────────────────────

def test_wind_correction_leaves_perfect_forecast_essentially_unchanged():
    frame = _synthetic_wind_frame(offset_u=0.0, offset_v=0.0, noise_std=0.0)
    train = frame.iloc[:160].reset_index(drop=True)
    val = frame.iloc[160:].reset_index(drop=True)
    geometry = _FakeGeometry()

    for factory in m.WIND_CORRECTION_ESTIMATORS.values():
        model = m.fit_wind_correction(train, factory, pooling="per_city")
        pred = m.predict_wind_correction(model, val)

        perp_raw = thermal_model.perpendicular_wind(
            val["fcst_wind_speed"].to_numpy(dtype=float),
            val["fcst_wind_direction"].to_numpy(dtype=float),
            geometry.bearing_deg,
        )
        raw_ampacity = thermal_model.ieee738_ampacity(
            val["fcst_air_temp"].to_numpy(dtype=float), perp_raw,
            val["fcst_solar_radiation"].to_numpy(dtype=float), geometry.conductor,
        )

        perp_corrected = thermal_model.perpendicular_wind(
            pred.speed, pred.direction, geometry.bearing_deg
        )
        corrected_ampacity = thermal_model.ieee738_ampacity(
            val["fcst_air_temp"].to_numpy(dtype=float), perp_corrected,
            val["fcst_solar_radiation"].to_numpy(dtype=float), geometry.conductor,
        )

        tolerance = max(5.0, 0.05 * float(np.mean(raw_ampacity)))
        assert np.mean(np.abs(corrected_ampacity - raw_ampacity)) < tolerance, (
            "a correction fitted on a perfect forecast moved the ampacity "
            "by more than a small tolerance -- it is learning noise"
        )


# ──────────────────────────────────────────────────────────────────────────────
# The 0/360 wrap-straddling test -- the exact failure mode wind_vector.py
# exists to prevent
# ──────────────────────────────────────────────────────────────────────────────

def test_wind_correction_treats_359_and_1_as_two_degrees_apart_not_358():
    """
    A correction accidentally fitted on a raw direction in degrees would
    see a discontinuous jump in its training target right at the 0/360
    seam (fcst=358 -> truth=0, fcst=359 -> truth=1, immediately after a
    long smooth run of fcst=0..357 -> truth=fcst+2) and would
    systematically mispredict at the seam while looking fine everywhere
    else. Because this module fits entirely in u/v space, the rotation
    mapping is smooth everywhere -- including at the seam -- so the
    held-out prediction at the wrap should be exactly as accurate as
    anywhere else on the circle, recovering the true 2-degree offset, not
    a spurious 358-degree one.
    """
    frame = _synthetic_rotation_frame(n=360, rotation_deg=2.0)
    train = frame.iloc[::2].reset_index(drop=True)
    val = frame.iloc[1::2].reset_index(drop=True)

    factory = m.WIND_CORRECTION_ESTIMATORS["LinearRegression"]
    model = m.fit_wind_correction(train, factory, pooling="per_city")
    pred = m.predict_wind_correction(model, val)

    def circular_error(predicted_deg, true_deg):
        diff = abs(predicted_deg - true_deg) % 360.0
        return min(diff, 360.0 - diff)

    wrap_pos = val.index[val["fcst_wind_direction"] == 359.0][0]
    wrap_corrected_dir = pred.direction[wrap_pos]
    wrap_error = circular_error(wrap_corrected_dir, 1.0)
    assert wrap_error < 5.0, (
        f"wrap row corrected direction {wrap_corrected_dir} is not within "
        f"5 degrees of the true 1.0 -- the correction may be treating the "
        f"0/360 wrap as a 358-degree gap rather than a 2-degree one"
    )

    mid_pos = val.index[val["fcst_wind_direction"] == 101.0][0]
    mid_corrected_dir = pred.direction[mid_pos]
    mid_error = circular_error(mid_corrected_dir, 103.0)
    assert mid_error < 5.0, (
        "accuracy at an ordinary, non-wrapping row is worse than expected "
        "-- the comparison point for the wrap-straddling assertion is not "
        "meaningful"
    )
    # The wrap row's error is not materially worse than the ordinary row's
    # -- no special degradation right at the 0/360 seam.
    assert wrap_error < mid_error + 5.0


# ──────────────────────────────────────────────────────────────────────────────
# Corrected direction is always directly consumable by perpendicular_wind
# ──────────────────────────────────────────────────────────────────────────────

def test_wind_correction_predicted_direction_is_always_in_half_open_circle():
    frame = _synthetic_wind_frame(offset_u=1.0, offset_v=1.0, noise_std=0.2)
    train = frame.iloc[:160].reset_index(drop=True)
    val = frame.iloc[160:].reset_index(drop=True)

    model = m.fit_wind_correction(
        train, m.WIND_CORRECTION_ESTIMATORS["GradientBoostingRegressor"], pooling="pooled"
    )
    pred = m.predict_wind_correction(model, val)

    assert (pred.direction >= 0).all()
    assert (pred.direction < 360).all()


def test_wind_correction_prediction_reports_zero_clamp_count_normally():
    frame = _synthetic_wind_frame(offset_u=0.3, offset_v=-0.2, noise_std=0.1)
    train = frame.iloc[:160].reset_index(drop=True)
    val = frame.iloc[160:].reset_index(drop=True)

    model = m.fit_wind_correction(
        train, m.WIND_CORRECTION_ESTIMATORS["LinearRegression"], pooling="pooled"
    )
    pred = m.predict_wind_correction(model, val)

    assert pred.clamped_count == 0
    assert (pred.speed >= 0).all()


# ──────────────────────────────────────────────────────────────────────────────
# Both pooling strategies fit and predict
# ──────────────────────────────────────────────────────────────────────────────

def test_fit_wind_correction_per_city_produces_one_model_pair_per_city():
    frame = _synthetic_wind_frame(offset_u=0.5, offset_v=0.5, noise_std=0.1)
    model = m.fit_wind_correction(
        frame, m.WIND_CORRECTION_ESTIMATORS["LinearRegression"], pooling="per_city"
    )
    assert set(model.models) == {"CITY_A", "CITY_B"}
    assert "endpoint_indicator" not in model.feature_names


def test_fit_wind_correction_pooled_adds_endpoint_indicator_feature():
    frame = _synthetic_wind_frame(offset_u=0.5, offset_v=0.5, noise_std=0.1)
    model = m.fit_wind_correction(
        frame, m.WIND_CORRECTION_ESTIMATORS["LinearRegression"], pooling="pooled"
    )
    assert model.pooling == "pooled"
    assert "endpoint_indicator" in model.feature_names
    assert set(model.models) == {"pooled"}


def test_fit_wind_correction_rejects_unknown_pooling_value():
    frame = _synthetic_wind_frame()
    with pytest.raises(ValueError):
        m.fit_wind_correction(
            frame, m.WIND_CORRECTION_ESTIMATORS["LinearRegression"], pooling="bogus"
        )


# ──────────────────────────────────────────────────────────────────────────────
# select_wind_configuration — validation-only selector, full score table
# ──────────────────────────────────────────────────────────────────────────────

def test_select_wind_configuration_returns_winner_and_full_score_table():
    frame = _synthetic_wind_frame(offset_u=0.8, offset_v=-0.5, noise_std=0.15)
    train = frame.iloc[:160].reset_index(drop=True)
    val = frame.iloc[160:].reset_index(drop=True)
    geometry = _FakeGeometry()

    result = m.select_wind_configuration(train, val, geometry)

    expected_keys = {
        f"{est}__{pooling}"
        for est in m.WIND_CORRECTION_ESTIMATORS
        for pooling in ("pooled", "per_city")
    }
    assert set(result["scores"]) == expected_keys

    for key, entry in result["scores"].items():
        assert math.isfinite(entry["mae"]), key

    assert result["winner_key"] in result["scores"]
    assert result["winner"]["mae"] == min(e["mae"] for e in result["scores"].values())


def test_select_wind_configuration_signature_has_no_test_frame_param():
    import inspect

    params = list(inspect.signature(m.select_wind_configuration).parameters)
    assert not any("test" in p.lower() for p in params), params


# ──────────────────────────────────────────────────────────────────────────────
# No-side-effects-on-import contract, matching wind_vector's own
# ──────────────────────────────────────────────────────────────────────────────

def test_importing_forecast_correction_models_alone_never_imports_requests():
    """
    Subprocess-isolated check (other test modules in this same pytest
    session import `requests` for unrelated reasons, e.g.
    `open_meteo_provider` -- polluting the shared `sys.modules` of a
    same-process check). A fresh interpreter that imports ONLY
    `forecast_correction_models` must never pull in `requests`.
    """
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import forecast_correction_models; import sys; "
            "assert 'requests' not in sys.modules; print('OK')",
        ],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# ──────────────────────────────────────────────────────────────────────────────
# COOLING_CORRECTION_ESTIMATORS — fresh, never-before-fit factories
# ──────────────────────────────────────────────────────────────────────────────

def test_cooling_correction_estimators_are_two_fresh_factories():
    assert len(m.COOLING_CORRECTION_ESTIMATORS) == 2
    for name, factory in m.COOLING_CORRECTION_ESTIMATORS.items():
        a, b = factory(), factory()
        assert a is not b, f"{name} returned a shared instance, not a fresh one"


# ──────────────────────────────────────────────────────────────────────────────
# Constant-factor recovery (D-02 approach 4's central claim)
# ──────────────────────────────────────────────────────────────────────────────

def test_cooling_correction_recovers_known_constant_factor_on_held_out_rows():
    frame = _synthetic_cooling_frame(wind_factor=1.3, temp_offset=-2.0, noise_std=0.05)
    train = frame.iloc[:160].reset_index(drop=True)
    val = frame.iloc[160:].reset_index(drop=True)
    geometry = _FakeGeometry()

    factory = m.COOLING_CORRECTION_ESTIMATORS["LinearRegression"]
    model = m.fit_cooling_correction(train, factory, target="level", conductor=geometry.conductor)
    pred = m.predict_cooling_correction(model, val)

    fcst_q_conv = thermal_model.convective_heat_loss(
        val["fcst_air_temp"].to_numpy(dtype=float),
        val["fcst_perp_wind_ms"].to_numpy(dtype=float),
        geometry.conductor,
    )
    truth_q_conv = thermal_model.convective_heat_loss(
        val["truth_air_temp"].to_numpy(dtype=float),
        val["truth_perp_wind_ms"].to_numpy(dtype=float),
        geometry.conductor,
    )

    raw_err = float(np.mean(np.abs(fcst_q_conv - truth_q_conv)))
    corrected_err = float(np.mean(np.abs(pred.q_conv - truth_q_conv)))

    assert corrected_err < raw_err * 0.6, (
        f"corrected term error ({corrected_err}) is not substantially "
        f"smaller than the raw forecast term error ({raw_err}) -- the "
        f"correction did not recover the planted wind/temperature offset"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Both target parameterizations fit, predict a strictly positive term, and
# round-trip through the override seam to a finite positive ampacity
# ──────────────────────────────────────────────────────────────────────────────

def test_cooling_correction_both_parameterizations_produce_finite_positive_ampacity():
    frame = _synthetic_cooling_frame()
    train = frame.iloc[:160].reset_index(drop=True)
    val = frame.iloc[160:].reset_index(drop=True)
    geometry = _FakeGeometry()

    for target in ("level", "log_ratio"):
        for factory in m.COOLING_CORRECTION_ESTIMATORS.values():
            model = m.fit_cooling_correction(
                train, factory, target=target, conductor=geometry.conductor
            )
            pred = m.predict_cooling_correction(model, val)
            assert (pred.q_conv > 0).all(), target

            ampacity = m.apply_cooling_correction(val, pred.q_conv, geometry)
            assert np.isfinite(ampacity).all(), target
            assert (ampacity > 0).all(), target


# ──────────────────────────────────────────────────────────────────────────────
# The log-ratio parameterization is scale-free; the level parameterization
# is not -- the whole reason the option exists (03-CONTEXT Open Questions)
# ──────────────────────────────────────────────────────────────────────────────

def test_log_ratio_generalizes_across_a_rescaled_term_but_level_does_not():
    """
    A model trained at one magnitude of convective term is evaluated,
    WITHOUT refitting, on a scenario whose wind (and therefore convective
    term) is scaled up by 8x while the forecast/truth *relationship*
    (wind_factor, temp_offset) is held fixed. The log-ratio target's
    VALUE (a ratio) is roughly the same regardless of magnitude, so a
    model trained on it generalizes across the rescale even without
    extrapolating. The level target's value is a magnitude calibrated to
    the TRAINING scale -- and a tree-based estimator (which cannot
    extrapolate past the range of targets it was trained on, unlike a
    linear model, which can accidentally extrapolate a roughly-correct
    scale through its own coefficient on the forecast-term feature) is
    the estimator that makes this contrast concrete: its "level"
    predictions stay capped near the small training magnitude no matter
    how large the rescaled input's true target actually is.
    """
    train_frame = _synthetic_cooling_frame(
        seed=1, wind_factor=1.3, temp_offset=-2.0, wind_scale=1.0, n=200
    )
    rescaled_frame = _synthetic_cooling_frame(
        seed=2, wind_factor=1.3, temp_offset=-2.0, wind_scale=8.0, n=100
    )
    geometry = _FakeGeometry()

    def _term_errors(target):
        factory = m.COOLING_CORRECTION_ESTIMATORS["GradientBoostingRegressor"]
        model = m.fit_cooling_correction(
            train_frame, factory, target=target, conductor=geometry.conductor
        )
        pred = m.predict_cooling_correction(model, rescaled_frame)

        fcst_q_conv = thermal_model.convective_heat_loss(
            rescaled_frame["fcst_air_temp"].to_numpy(dtype=float),
            rescaled_frame["fcst_perp_wind_ms"].to_numpy(dtype=float),
            geometry.conductor,
        )
        truth_q_conv = thermal_model.convective_heat_loss(
            rescaled_frame["truth_air_temp"].to_numpy(dtype=float),
            rescaled_frame["truth_perp_wind_ms"].to_numpy(dtype=float),
            geometry.conductor,
        )
        raw_err = float(np.mean(np.abs(fcst_q_conv - truth_q_conv)))
        corrected_err = float(np.mean(np.abs(pred.q_conv - truth_q_conv)))
        return raw_err, corrected_err

    level_raw_err, level_corrected_err = _term_errors("level")
    log_ratio_raw_err, log_ratio_corrected_err = _term_errors("log_ratio")

    assert log_ratio_corrected_err < log_ratio_raw_err * 0.7, (
        "the scale-free log-ratio model did not generalize to the "
        "rescaled magnitude -- it should still improve on the raw "
        "forecast even without retraining"
    )
    assert level_corrected_err >= level_raw_err * 0.7, (
        "the level model unexpectedly generalized as well as log-ratio "
        "to the rescaled magnitude -- this test's premise (level is NOT "
        "scale-free) did not hold, which means it is not actually "
        "distinguishing the two parameterizations"
    )


# ──────────────────────────────────────────────────────────────────────────────
# The seam round-trip: overriding with the forecast's own term must
# reproduce the raw-forecast arm's ampacity exactly
# ──────────────────────────────────────────────────────────────────────────────

def test_cooling_correction_override_with_forecast_own_term_reproduces_raw_ampacity_exactly():
    frame = _synthetic_cooling_frame()
    geometry = _FakeGeometry()

    fcst_q_conv = thermal_model.convective_heat_loss(
        frame["fcst_air_temp"].to_numpy(dtype=float),
        frame["fcst_perp_wind_ms"].to_numpy(dtype=float),
        geometry.conductor,
    )
    overridden_ampacity = m.apply_cooling_correction(frame, fcst_q_conv, geometry)
    raw_ampacity = thermal_model.ieee738_ampacity(
        frame["fcst_air_temp"].to_numpy(dtype=float),
        frame["fcst_perp_wind_ms"].to_numpy(dtype=float),
        frame["fcst_solar_radiation"].to_numpy(dtype=float),
        geometry.conductor,
    )
    assert np.array_equal(overridden_ampacity, raw_ampacity), (
        "an override set to exactly the forecast's own convective term "
        "did not reproduce the raw-forecast ampacity exactly -- the "
        "override seam is not wired correctly"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Non-positive convective term rejection (fail-loud discipline, T-03-05-01)
# ──────────────────────────────────────────────────────────────────────────────

def test_predict_cooling_correction_rejects_non_positive_predicted_term():
    frame = _synthetic_cooling_frame(n=50)
    geometry = _FakeGeometry()

    factory = m.COOLING_CORRECTION_ESTIMATORS["LinearRegression"]
    model = m.fit_cooling_correction(frame, factory, target="level", conductor=geometry.conductor)
    model.estimator.predict = lambda X: np.full(len(X), -5.0)

    with pytest.raises(ValueError, match="non-positive"):
        m.predict_cooling_correction(model, frame)


def test_fit_cooling_correction_log_ratio_raises_on_non_positive_forecast_term(monkeypatch):
    frame = _synthetic_cooling_frame(n=30)
    geometry = _FakeGeometry()

    def _fake_convective_heat_loss(t_amb, wind_perp, conductor):
        values = np.asarray(t_amb, dtype=float) * 0.0 + 10.0
        values[0] = -1.0
        return values

    monkeypatch.setattr(m.thermal_model, "convective_heat_loss", _fake_convective_heat_loss)

    factory = m.COOLING_CORRECTION_ESTIMATORS["LinearRegression"]
    with pytest.raises(ValueError, match="non-positive"):
        m.fit_cooling_correction(frame, factory, target="log_ratio", conductor=geometry.conductor)


# ──────────────────────────────────────────────────────────────────────────────
# select_cooling_configuration — validation-only selector, full score table
# ──────────────────────────────────────────────────────────────────────────────

def test_select_cooling_configuration_returns_winner_and_full_score_table():
    frame = _synthetic_cooling_frame(wind_factor=1.3, temp_offset=-2.0)
    train = frame.iloc[:160].reset_index(drop=True)
    val = frame.iloc[160:].reset_index(drop=True)
    geometry = _FakeGeometry()

    result = m.select_cooling_configuration(train, val, geometry)

    expected_keys = {
        f"{est}__{target}"
        for est in m.COOLING_CORRECTION_ESTIMATORS
        for target in ("level", "log_ratio")
    }
    assert set(result["scores"]) == expected_keys

    for key, entry in result["scores"].items():
        assert math.isfinite(entry["mae"]), key

    assert result["winner_key"] in result["scores"]
    assert result["winner"]["mae"] == min(e["mae"] for e in result["scores"].values())


def test_select_cooling_configuration_signature_has_no_test_frame_param():
    import inspect

    params = list(inspect.signature(m.select_cooling_configuration).parameters)
    assert not any("test" in p.lower() for p in params), params
