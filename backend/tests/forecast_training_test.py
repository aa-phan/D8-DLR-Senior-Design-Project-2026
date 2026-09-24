"""
Tests for backend/forecast_training.py (v1.3 Phase 1 Plan 01-01, FCST-01/
FCST-02 model-honesty invariants).

Covers the four invariants that separate a real forecasting model from a
physics inversion or a disguised naive read: no future leakage, the
codebase's own weakest-link `min()` target reduction, and a hard refusal
to fit on an invalid row. Follows this suite's existing conventions:
module-level imports, plain asserts, no classes, deterministic synthetic
inputs, no network (a real Open-Meteo fetch is exercised only by Plan
01-01's own live `<verify>` block, not by this unit suite --
`forecast_training.fetch_city_weather` is monkeypatched in every test
here that needs weather data).
"""

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import config
import corridor_discretization
import forecast_training as ft
import thermal_model


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
