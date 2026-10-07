"""
Network-free tests for `forecast_shadow_fit_reference_refit.py` (Phase 5
Plan 04, Task 1) -- the one-time offline fit+commit script for the
`reference_ml_refit_24h` shadow candidate's persisted MLP artifact.

`forecast_experiment._stacked_pair_frame` is monkeypatched to return a
small synthetic two-city stacked frame rather than issuing a real network
call, per this task's own network-free test contract. The real (network-
touching) fit for both corridors is a separate, explicit step this plan's
Task 1 `<action>` performs directly, not inside this test file.
"""

import numpy as np
import pandas as pd

import config
import forecast_experiment
import forecast_experiment_audit
import forecast_shadow_fit_reference_refit as fit_module
import forecast_shadow_pipeline as shadow
import forecast_training

_CORRIDOR = "AUSTIN_CORPUS_CHRISTI"


def _synthetic_stacked_frame(corridor=_CORRIDOR, n=40):
    """
    A minimal two-city STACKED frame shaped like `_stacked_pair_frame`'s
    own output: `datetime_utc`, `endpoint_city`, `truth_dlr_amps`,
    `truth_air_temp`, `truth_wind_speed`, `truth_solar_radiation` --
    enough hourly rows (40) for `build_training_matrix(horizon_minutes=
    1440)` to produce at least one non-null row: the leading 6 rows are
    dropped for the lag/rolling features (`FORECAST_ML_LAG_HOURS`'s max of
    6h), and the trailing 24 rows are dropped for the 24h-ahead target
    shift, leaving 40 - 6 - 24 = 10 usable rows.
    """
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]
    ts = pd.date_range("2024-01-20", periods=n, freq="1h", tz="UTC")
    rng = np.random.default_rng(7)

    rows = []
    for city in (city_a, city_b):
        for i in range(n):
            rows.append({
                "datetime_utc": ts[i],
                "endpoint_city": city,
                "truth_dlr_amps": 1000.0 + rng.uniform(-50.0, 50.0),
                "truth_air_temp": rng.uniform(10.0, 35.0),
                "truth_wind_speed": rng.uniform(1.0, 10.0),
                "truth_solar_radiation": rng.uniform(0.0, 800.0),
            })
    return pd.DataFrame(rows)


def test_fit_and_save_calls_the_exact_arm5_recipe_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))

    captured_window = {}
    synthetic_frame = _synthetic_stacked_frame()

    def _fake_stacked_pair_frame(corridor, start, end, *, lead_hours):
        captured_window["corridor"] = corridor
        captured_window["start"] = start
        captured_window["end"] = end
        captured_window["lead_hours"] = lead_hours
        return synthetic_frame

    monkeypatch.setattr(forecast_experiment, "_stacked_pair_frame", _fake_stacked_pair_frame)

    call_order = []
    real_arm5_truth_frame = forecast_experiment._arm5_truth_frame
    real_build_training_matrix = forecast_training.build_training_matrix
    real_fit_corridor_model = forecast_training.fit_corridor_model

    def _tracking_arm5_truth_frame(*a, **k):
        call_order.append("_arm5_truth_frame")
        return real_arm5_truth_frame(*a, **k)

    def _tracking_build_training_matrix(*a, **k):
        call_order.append("build_training_matrix")
        return real_build_training_matrix(*a, **k)

    def _tracking_fit_corridor_model(*a, **k):
        call_order.append("fit_corridor_model")
        return real_fit_corridor_model(*a, **k)

    monkeypatch.setattr(forecast_experiment, "_arm5_truth_frame", _tracking_arm5_truth_frame)
    monkeypatch.setattr(forecast_training, "build_training_matrix", _tracking_build_training_matrix)
    monkeypatch.setattr(forecast_training, "fit_corridor_model", _tracking_fit_corridor_model)

    path = fit_module.fit_and_save(_CORRIDOR)

    assert call_order == ["_arm5_truth_frame", "build_training_matrix", "fit_corridor_model"]
    assert path.endswith(f"reference_ml_refit_24h_{_CORRIDOR}.joblib")


def test_fit_and_save_writes_a_loadable_artifact_with_predict(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))
    synthetic_frame = _synthetic_stacked_frame()
    monkeypatch.setattr(
        forecast_experiment, "_stacked_pair_frame",
        lambda corridor, start, end, *, lead_hours: synthetic_frame,
    )

    path = fit_module.fit_and_save(_CORRIDOR)

    import os
    assert os.path.exists(path)

    model = shadow.load_correction_model(_CORRIDOR, "reference_ml_refit_24h")
    assert hasattr(model, "predict")


def test_fit_and_save_passes_the_pinned_frozen_window_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))
    captured_window = {}
    synthetic_frame = _synthetic_stacked_frame()

    def _fake_stacked_pair_frame(corridor, start, end, *, lead_hours):
        captured_window["start"] = start
        captured_window["end"] = end
        captured_window["lead_hours"] = lead_hours
        return synthetic_frame

    monkeypatch.setattr(forecast_experiment, "_stacked_pair_frame", _fake_stacked_pair_frame)

    fit_module.fit_and_save(_CORRIDOR)

    expected_end = (
        pd.Timestamp(forecast_experiment_audit.FROZEN_TEST_SPLIT_START) - pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    assert captured_window["start"] == forecast_experiment_audit.FROZEN_WINDOW_START
    assert captured_window["end"] == expected_end
    assert captured_window["lead_hours"] == config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS


def test_fit_and_save_runs_for_every_configured_corridor_via_main(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(
        forecast_experiment, "_stacked_pair_frame",
        lambda corridor, start, end, *, lead_hours: _synthetic_stacked_frame(corridor),
    )

    fit_module.main()

    for corridor in config.CORRIDOR_ENDPOINTS:
        model = shadow.load_correction_model(corridor, "reference_ml_refit_24h")
        assert hasattr(model, "predict")
