"""
Tests for backend/forecast_experiment.py (D-01/D-02, Phase 3 Plan 03-01
Task 3).

Every test is network-free: monkeypatch `open_meteo_provider.
fetch_open_meteo` and `open_meteo_forecast_provider.fetch_historical_
forecast` on the module objects `forecast_experiment` imports, following
the convention `anomaly_training_test.py`/`forecast_training_test.py` use
for mocking a fetch one layer up. Module-level plain-assert functions, no
test classes. Every test also redirects `config.FORECAST_EXPERIMENT_
CACHE_DIR` to a pytest `tmp_path`, so no test reads or writes the real
`data/experiment/` cache.
"""

import numpy as np
import pandas as pd
import pytest

import ampacity_forecast
import config
import corridor_discretization
import forecast_experiment as fe


CITY = "AUSTIN"


def _synthetic_weather_frame(start="2025-10-01", periods=24 * 20):
    """
    A deterministic, fully-populated hourly weather frame (no seasonality
    subtlety needed -- these tests exercise the frame-assembly and
    scoring machinery, not physical realism).
    """
    idx = pd.date_range(start, periods=periods, freq="h", tz="UTC")
    t = np.arange(len(idx), dtype=float)
    rng = np.random.default_rng(20260929)
    return pd.DataFrame({
        "datetime_utc": idx,
        "air_temp": 25.0 + 8.0 * np.sin(t / 24.0),
        "wind_speed": 3.0 + rng.random(len(idx)) * 2.0,
        "wind_direction": (t * 7.0) % 360.0,
        "solar_radiation": np.clip(600.0 * np.sin(t / 24.0), 0.0, None),
        "relative_humidity": 50.0 + rng.random(len(idx)) * 10.0,
    })


def _patch_fetches(monkeypatch, truth_frame, fcst_frame, calls=None):
    def fake_truth_fetch(lat, lon, start, end):
        if calls is not None:
            calls["truth"] = calls.get("truth", 0) + 1
        return truth_frame.copy()

    def fake_fcst_fetch(lat, lon, start, end):
        if calls is not None:
            calls["fcst"] = calls.get("fcst", 0) + 1
        return fcst_frame.copy()

    monkeypatch.setattr(fe.open_meteo_provider, "fetch_open_meteo", fake_truth_fetch)
    monkeypatch.setattr(
        fe.open_meteo_forecast_provider, "fetch_historical_forecast", fake_fcst_fetch
    )


# ──────────────────────────────────────────────────────────────────────────
# anchored_pair_frame contract
# ──────────────────────────────────────────────────────────────────────────


def test_anchored_pair_frame_anchor_gap_is_exactly_one_hour(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame()
    fcst = _synthetic_weather_frame()
    _patch_fetches(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20")

    gaps = frame["datetime_utc"] - frame["anchor_datetime_utc"]
    assert (gaps == pd.Timedelta(hours=1)).all()
    # No exception -- this is the automated enforcement of the same fact.
    fe.assert_exact_lead(frame)


def test_anchored_pair_frame_median_anchor_spacing_is_one_hour_before_filtering(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame()
    fcst = _synthetic_weather_frame()
    _patch_fetches(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20")

    spacing = frame["anchor_datetime_utc"].diff().dropna()
    assert spacing.median() == pd.Timedelta(hours=1)

    filtered = fe.filter_to_exact_lead(frame)
    assert len(filtered) > 0
    # After filtering, scored rows are 6h apart from each other, but each
    # row's OWN anchor gap is still exactly 1h.
    filtered_spacing = filtered["datetime_utc"].diff().dropna()
    assert filtered_spacing.median() == pd.Timedelta(hours=6)
    filtered_gaps = filtered["datetime_utc"] - filtered["anchor_datetime_utc"]
    assert (filtered_gaps == pd.Timedelta(hours=1)).all()


def test_assert_exact_lead_raises_naming_offending_timestamp():
    idx = pd.date_range("2025-10-01", periods=5, freq="h", tz="UTC")
    frame = pd.DataFrame({
        "datetime_utc": idx,
        "anchor_datetime_utc": idx - pd.Timedelta(hours=1),
    })
    # Corrupt one row's anchor gap to 6 hours (the six-hour-stale defect
    # this assertion exists to catch).
    frame.loc[2, "anchor_datetime_utc"] = frame.loc[2, "datetime_utc"] - pd.Timedelta(hours=6)

    with pytest.raises(ValueError) as excinfo:
        fe.assert_exact_lead(frame)

    assert str(idx[2]) in str(excinfo.value) or idx[2].isoformat() in str(excinfo.value)


def test_filter_to_exact_lead_selects_only_the_configured_remainder(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame()
    fcst = _synthetic_weather_frame()
    _patch_fetches(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20")
    filtered = fe.filter_to_exact_lead(frame)

    remainder = config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER
    modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
    assert (filtered["datetime_utc"].dt.hour % modulus == remainder).all()
    assert len(filtered) < len(frame)


def test_anchored_pair_frame_caches_and_does_not_refetch(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame()
    fcst = _synthetic_weather_frame()
    calls = {}
    _patch_fetches(monkeypatch, truth, fcst, calls=calls)

    frame1 = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20")
    assert calls["truth"] == 1 and calls["fcst"] == 1

    frame2 = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20")
    # No new fetch on the second call -- the cache was read instead.
    assert calls["truth"] == 1 and calls["fcst"] == 1
    assert frame1["datetime_utc"].equals(frame2["datetime_utc"])


def test_corridor_for_city_raises_for_unknown_city():
    with pytest.raises(ValueError):
        fe._corridor_for_city("NOT_A_CITY")


def test_corridor_for_city_resolves_known_endpoints():
    for corridor, (city_a, city_b) in config.CORRIDOR_ENDPOINTS.items():
        assert fe._corridor_for_city(city_a) == corridor
        assert fe._corridor_for_city(city_b) == corridor


# ──────────────────────────────────────────────────────────────────────────
# score_arms -- identical-index requirement
# ──────────────────────────────────────────────────────────────────────────


def _minimal_test_frame(n=10):
    idx = pd.date_range("2025-10-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({
        "datetime_utc": idx,
        "truth_dlr_amps": np.linspace(900.0, 1000.0, n),
        "anchor_dlr_amps": np.linspace(890.0, 990.0, n),
    })


def test_score_arms_returns_identical_index_for_every_arm():
    frame = _minimal_test_frame()
    arms = {
        "persistence": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float),
        "raw_forecast": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float) + 5.0,
    }
    result = score_arms_result = fe.score_arms(frame, arms)

    assert set(result["candidates"]) == {"persistence", "raw_forecast"}
    for name, s in result["candidates"].items():
        assert s["rows"] == len(frame)
        assert s["mae"] == s["mae"]  # not NaN
        assert s["rmse"] == s["rmse"]
    assert result["test_index"] == list(frame.index)


def test_score_arms_raises_on_length_mismatch():
    frame = _minimal_test_frame()
    arms = {"bad": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float)[:-1]}
    with pytest.raises(ValueError):
        fe.score_arms(frame, arms)


def test_score_arms_raises_on_non_unique_index():
    frame = _minimal_test_frame()
    frame.index = [0] * len(frame)
    with pytest.raises(ValueError):
        fe.score_arms(frame, {"persistence": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float)})


def test_score_arms_raises_on_non_sorted_index():
    frame = _minimal_test_frame()
    frame.index = list(reversed(range(len(frame))))
    with pytest.raises(ValueError):
        fe.score_arms(frame, {"persistence": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float)})


# ──────────────────────────────────────────────────────────────────────────
# Persistence-agreement regression -- the guard against a stale anchor
# ──────────────────────────────────────────────────────────────────────────


def test_persistence_arm_agrees_with_backtest_residuals(monkeypatch, tmp_path):
    """
    Arm 0's MAE on the anchored frame must agree with persistence's MAE
    derived from `ampacity_forecast.backtest_residuals` over the SAME
    timestamps on the unfiltered hourly series -- the guard against the
    six-hour-stale-anchor defect this plan's central invariant exists to
    prevent.
    """
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 30)
    fcst = _synthetic_weather_frame(periods=24 * 30)  # arm 2 not exercised here
    _patch_fetches(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-30")
    fe.assert_exact_lead(frame)
    filtered = fe.filter_to_exact_lead(frame)
    assert len(filtered) > 0

    scored = fe.score_arms(
        filtered, {"persistence": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float)}
    )
    experiment_mae = scored["candidates"]["persistence"]["mae"]

    # Ground truth: the SAME per-row ampacity (via the SAME _city_ampacity
    # every arm uses) fed through ampacity_forecast.backtest_residuals on
    # the FULL, unfiltered hourly series, restricted to the timestamps
    # this test actually scored.
    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))
    dlr_amps = fe._city_ampacity(
        truth["air_temp"], truth["wind_speed"], truth["wind_direction"],
        truth["solar_radiation"], geometry,
    )
    series = pd.Series(dlr_amps, index=pd.to_datetime(truth["datetime_utc"], utc=True))
    series = series.sort_index()

    residuals = ampacity_forecast.backtest_residuals(series, "naive", min_train_rows=1)
    residual_index = series.index[1:]
    residual_series = pd.Series(residuals, index=residual_index)

    scored_timestamps = pd.to_datetime(filtered["datetime_utc"], utc=True)
    matching = residual_series.reindex(scored_timestamps)
    assert not matching.isna().any(), "scored timestamps missing from backtest_residuals ground truth"

    backtest_mae = float(np.mean(np.abs(matching.to_numpy())))

    assert experiment_mae == pytest.approx(backtest_mae, rel=1e-9, abs=1e-6)


# ──────────────────────────────────────────────────────────────────────────
# Realizability caveat -- must appear on every output surface
# ──────────────────────────────────────────────────────────────────────────


def test_caveat_appears_in_emitted_report(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame()
    fcst = _synthetic_weather_frame()
    _patch_fetches(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20")
    filtered = fe.filter_to_exact_lead(frame)
    boundaries = fe._default_split_boundaries(frame)
    scored = fe.score_arms(
        filtered, {"persistence": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float)}
    )

    report = fe.corridor_experiment_report(
        CITY, "2025-10-01", "2025-10-20", frame, filtered, boundaries, scored,
    )

    assert report["caveat"] == fe.EXPERIMENT_LEAD_REALIZABILITY_CAVEAT
    import json
    assert fe.EXPERIMENT_LEAD_REALIZABILITY_CAVEAT in json.dumps(report)


def test_main_prints_the_caveat_and_writes_a_report(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 30)
    fcst = _synthetic_weather_frame(periods=24 * 30)
    _patch_fetches(monkeypatch, truth, fcst)

    fe.main(["--city", CITY, "--start", "2025-10-01", "--end", "2025-10-30"])

    captured = capsys.readouterr()
    assert fe.EXPERIMENT_LEAD_REALIZABILITY_CAVEAT in captured.out
    assert "persistence" in captured.out
    assert "raw_forecast" in captured.out


# ──────────────────────────────────────────────────────────────────────────
# Import-time no-side-effects
# ──────────────────────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects():
    import importlib
    importlib.reload(fe)
