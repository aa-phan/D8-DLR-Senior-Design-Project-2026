"""
Tests for backend/forecast_experiment.py (D-01 legacy 1h arm + D-04 PRIMARY
24h arm, Phase 3 Plans 03-01/03-03).

Every test is network-free: monkeypatch `open_meteo_provider.
fetch_open_meteo` and either `open_meteo_forecast_provider.fetch_historical_
forecast` (legacy 1h lead) or `open_meteo_forecast_provider.
fetch_previous_runs` (D-04 primary 24h lead) on the module objects
`forecast_experiment` imports, following the convention
`anomaly_training_test.py`/`forecast_training_test.py` use for mocking a
fetch one layer up. Module-level plain-assert functions, no test classes.
Every test also redirects `config.FORECAST_EXPERIMENT_CACHE_DIR` to a
pytest `tmp_path`, so no test reads or writes the real `data/experiment/`
cache.

`lead_hours` is now a REQUIRED keyword-only parameter on
`anchored_pair_frame`/`assert_exact_lead`/`filter_to_exact_lead` (Plan
03-03's checkpoint decision) -- every pre-existing call site below is
updated to pass `lead_hours=1` explicitly, preserving the LEGACY arm's
exact prior behavior and keeping these tests scoped to it (per Plan
03-03's Task 3 instruction). The 24-hour-primary section below is new.
"""

import json
import os

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
    """Legacy 1-hour lead: patches fetch_historical_forecast."""

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


def _patch_fetches_24h(monkeypatch, truth_frame, fcst_frame, calls=None):
    """D-04 primary 24-hour lead: patches fetch_previous_runs."""

    def fake_truth_fetch(lat, lon, start, end):
        if calls is not None:
            calls["truth"] = calls.get("truth", 0) + 1
        return truth_frame.copy()

    def fake_fcst_fetch(lat, lon, start, end, previous_day=None):
        if calls is not None:
            calls["fcst"] = calls.get("fcst", 0) + 1
        return fcst_frame.copy()

    monkeypatch.setattr(fe.open_meteo_provider, "fetch_open_meteo", fake_truth_fetch)
    monkeypatch.setattr(
        fe.open_meteo_forecast_provider, "fetch_previous_runs", fake_fcst_fetch
    )


PRIMARY_LEAD = config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS


# ──────────────────────────────────────────────────────────────────────────
# anchored_pair_frame contract -- LEGACY 1-hour lead
# ──────────────────────────────────────────────────────────────────────────


def test_anchored_pair_frame_anchor_gap_is_exactly_one_hour(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame()
    fcst = _synthetic_weather_frame()
    _patch_fetches(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=1)

    gaps = frame["datetime_utc"] - frame["anchor_datetime_utc"]
    assert (gaps == pd.Timedelta(hours=1)).all()
    # No exception -- this is the automated enforcement of the same fact.
    fe.assert_exact_lead(frame, lead_hours=1)


def test_anchored_pair_frame_median_anchor_spacing_is_one_hour_before_filtering(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame()
    fcst = _synthetic_weather_frame()
    _patch_fetches(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=1)

    spacing = frame["anchor_datetime_utc"].diff().dropna()
    assert spacing.median() == pd.Timedelta(hours=1)

    filtered = fe.filter_to_exact_lead(frame, lead_hours=1)
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
        fe.assert_exact_lead(frame, lead_hours=1)

    assert str(idx[2]) in str(excinfo.value) or idx[2].isoformat() in str(excinfo.value)


def test_assert_exact_lead_names_the_claimed_lead_in_the_error():
    idx = pd.date_range("2025-10-01", periods=3, freq="h", tz="UTC")
    frame = pd.DataFrame({
        "datetime_utc": idx,
        "anchor_datetime_utc": idx - pd.Timedelta(hours=1),
    })

    with pytest.raises(ValueError) as excinfo:
        # Claim a 24h lead against data that actually carries a 1h gap.
        fe.assert_exact_lead(frame, lead_hours=24)

    assert "24" in str(excinfo.value)


def test_filter_to_exact_lead_selects_only_the_configured_remainder(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame()
    fcst = _synthetic_weather_frame()
    _patch_fetches(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=1)
    filtered = fe.filter_to_exact_lead(frame, lead_hours=1)

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

    frame1 = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=1)
    assert calls["truth"] == 1 and calls["fcst"] == 1

    frame2 = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=1)
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
# score_arms -- identical-index requirement (lead-agnostic, unchanged)
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
    result = fe.score_arms(frame, arms)

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
# Persistence-agreement regression -- the guard against a stale anchor.
# LEGACY LEAD ONLY (Plan 03-03 Task 3): this test's ground truth is
# ampacity_forecast.backtest_residuals's "naive" (one-ROW-lag) branch, which
# is only a genuine one-hour lag at this project's hourly cadence -- it must
# never be generalized to the 24-hour arm (that would silently validate the
# 24h persistence arm against a one-hour-old baseline). The 24-hour
# equivalent is `test_24h_persistence_prediction_equals_hand_computed_24h_shift`
# below, which hand-computes a 24-hour shift directly instead.
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

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-30", lead_hours=1)
    fe.assert_exact_lead(frame, lead_hours=1)
    filtered = fe.filter_to_exact_lead(frame, lead_hours=1)
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
# Realizability caveat -- must appear on every output surface (LEGACY lead)
# ──────────────────────────────────────────────────────────────────────────


def test_caveat_appears_in_emitted_report(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame()
    fcst = _synthetic_weather_frame()
    _patch_fetches(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=1)
    filtered = fe.filter_to_exact_lead(frame, lead_hours=1)
    boundaries = fe._default_split_boundaries(frame)
    scored = fe.score_arms(
        filtered, {"persistence": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float)}
    )

    report = fe.corridor_experiment_report(
        CITY, "2025-10-01", "2025-10-20", frame, filtered, boundaries, scored, lead_hours=1,
    )

    assert report["caveat"] == fe.EXPERIMENT_LEAD_REALIZABILITY_CAVEAT
    assert report["measured_lead_hours"] == 1.0
    import json
    assert fe.EXPERIMENT_LEAD_REALIZABILITY_CAVEAT in json.dumps(report)


def test_main_prints_the_caveat_and_writes_a_report(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 30)
    fcst = _synthetic_weather_frame(periods=24 * 30)
    _patch_fetches(monkeypatch, truth, fcst)

    fe.main(["--city", CITY, "--start", "2025-10-01", "--end", "2025-10-30", "--lead-hours", "1"])

    captured = capsys.readouterr()
    assert fe.EXPERIMENT_LEAD_REALIZABILITY_CAVEAT in captured.out
    assert "persistence" in captured.out
    assert "raw_forecast" in captured.out
    assert "split=val" in captured.out


# ──────────────────────────────────────────────────────────────────────────
# D-04 PRIMARY 24-hour lead (Plan 03-03 Task 3) -- the generalized contract
# ──────────────────────────────────────────────────────────────────────────


def test_lead_source_config_raises_for_unsupported_lead():
    with pytest.raises(ValueError):
        fe._lead_source_config(7)


def test_anchored_pair_frame_at_24h_lead_anchor_gap_is_exactly_24_hours(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 30)
    fcst = _synthetic_weather_frame(periods=24 * 30)
    _patch_fetches_24h(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD)

    gaps = frame["datetime_utc"] - frame["anchor_datetime_utc"]
    assert (gaps == pd.Timedelta(hours=PRIMARY_LEAD)).all()
    # No exception -- this is the automated enforcement of the same fact.
    fe.assert_exact_lead(frame, lead_hours=PRIMARY_LEAD)


def test_anchor_group_at_24h_lead_is_built_from_full_unfiltered_series(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 30)
    fcst = _synthetic_weather_frame(periods=24 * 30)
    _patch_fetches_24h(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD)

    spacing = frame["anchor_datetime_utc"].diff().dropna()
    assert spacing.median() == pd.Timedelta(hours=1)

    filtered = fe.filter_to_exact_lead(frame, lead_hours=PRIMARY_LEAD)
    assert len(filtered) > 0
    remainder = config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER
    modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
    assert (filtered["datetime_utc"].dt.hour % modulus == remainder).all()
    # After filtering, scored rows are 6h apart from each other, but each
    # row's OWN anchor gap is still exactly lead_hours.
    filtered_spacing = filtered["datetime_utc"].diff().dropna()
    assert filtered_spacing.median() == pd.Timedelta(hours=6)
    filtered_gaps = filtered["datetime_utc"] - filtered["anchor_datetime_utc"]
    assert (filtered_gaps == pd.Timedelta(hours=PRIMARY_LEAD)).all()


def test_fcst_anchor_columns_present_and_shifted_by_lead_hours(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 20)
    fcst = _synthetic_weather_frame(periods=24 * 20)
    _patch_fetches_24h(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=PRIMARY_LEAD)

    for col in (
        "fcst_anchor_air_temp", "fcst_anchor_wind_speed",
        "fcst_anchor_wind_direction", "fcst_anchor_solar_radiation",
        "fcst_anchor_relative_humidity", "fcst_anchor_datetime_utc",
    ):
        assert col in frame.columns

    gaps = frame["datetime_utc"] - frame["fcst_anchor_datetime_utc"]
    assert (gaps == pd.Timedelta(hours=PRIMARY_LEAD)).all()

    # The fcst_anchor value at row T must equal the forecast series' own
    # value at T - lead_hours -- the same shift discipline as the truth
    # anchor group, applied to the forecast series instead.
    fcst_by_time = fcst.set_index("datetime_utc")
    sample_row = frame.iloc[len(frame) // 2]
    anchor_time = sample_row["fcst_anchor_datetime_utc"]
    assert anchor_time in fcst_by_time.index
    assert sample_row["fcst_anchor_wind_speed"] == pytest.approx(
        float(fcst_by_time.loc[anchor_time, "wind_speed"])
    )


def test_filter_to_exact_lead_selects_remainder_zero_for_24h_lead(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 20)
    fcst = _synthetic_weather_frame(periods=24 * 20)
    _patch_fetches_24h(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=PRIMARY_LEAD)
    filtered = fe.filter_to_exact_lead(frame, lead_hours=PRIMARY_LEAD)

    remainder = config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER
    assert remainder == 0
    modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
    assert (filtered["datetime_utc"].dt.hour % modulus == remainder).all()
    assert len(filtered) < len(frame)


def test_cache_path_differs_between_two_leads_for_same_city_and_window():
    a = fe._cache_path_for("AUSTIN", "2024-01-20", "2024-02-20", lead_hours=1)
    b = fe._cache_path_for("AUSTIN", "2024-01-20", "2024-02-20", lead_hours=PRIMARY_LEAD)
    assert a != b


def test_two_leads_assembled_for_same_city_and_window_write_distinct_cache_files(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 20)
    fcst_legacy = _synthetic_weather_frame(periods=24 * 20)
    fcst_24h = _synthetic_weather_frame(periods=24 * 20)

    _patch_fetches(monkeypatch, truth, fcst_legacy)
    frame_1h = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=1)

    _patch_fetches_24h(monkeypatch, truth, fcst_24h)
    frame_24h = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=PRIMARY_LEAD)

    path_1h = fe._cache_path_for(CITY, "2025-10-01", "2025-10-20", lead_hours=1)
    path_24h = fe._cache_path_for(CITY, "2025-10-01", "2025-10-20", lead_hours=PRIMARY_LEAD)
    assert path_1h != path_24h
    import os
    assert os.path.exists(path_1h)
    assert os.path.exists(path_24h)
    # A warmed 1h cache is never returned to a 24h caller: the two frames'
    # anchor gaps differ.
    gap_1h = (frame_1h["datetime_utc"] - frame_1h["anchor_datetime_utc"]).iloc[0]
    gap_24h = (frame_24h["datetime_utc"] - frame_24h["anchor_datetime_utc"]).iloc[0]
    assert gap_1h == pd.Timedelta(hours=1)
    assert gap_24h == pd.Timedelta(hours=PRIMARY_LEAD)


def test_24h_persistence_arm_does_not_route_through_production_point_forecast_helpers(
    monkeypatch, tmp_path
):
    """
    With ampacity_forecast.backtest_residuals and ampacity_forecast.
    _point_forecast monkeypatched to raise, the full 24-hour assembly and
    scoring path still completes -- proving the 24-hour persistence arm
    does not route through the one-row-lag production helpers, whose
    "naive" branch returns the immediately preceding ROW (1 hour at this
    project's cadence, silently wrong by a factor of 24 for this lead).
    """
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))

    def _boom(*a, **k):
        raise AssertionError(
            "the 24h persistence arm routed through a production "
            "point-forecast helper"
        )

    monkeypatch.setattr(ampacity_forecast, "backtest_residuals", _boom)
    monkeypatch.setattr(ampacity_forecast, "_point_forecast", _boom)

    truth = _synthetic_weather_frame(periods=24 * 30)
    fcst = _synthetic_weather_frame(periods=24 * 30)
    _patch_fetches_24h(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD)
    fe.assert_exact_lead(frame, lead_hours=PRIMARY_LEAD)
    filtered = fe.filter_to_exact_lead(frame, lead_hours=PRIMARY_LEAD)
    assert len(filtered) > 0

    scored = fe.score_arms(
        filtered, {"persistence_24h": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float)}
    )
    mae = scored["candidates"]["persistence_24h"]["mae"]
    assert mae == mae  # not NaN -- the path completed


def test_24h_persistence_prediction_equals_hand_computed_24h_shift(monkeypatch, tmp_path):
    """
    The 24-hour persistence prediction for a row at valid time T equals the
    truth ampacity computed at T - 24h, verified against an independently
    hand-computed 24-hour shift of the synthetic truth series -- not
    against any function in `ampacity_forecast`.
    """
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 30)
    fcst = _synthetic_weather_frame(periods=24 * 30)
    _patch_fetches_24h(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD)
    fe.assert_exact_lead(frame, lead_hours=PRIMARY_LEAD)
    filtered = fe.filter_to_exact_lead(frame, lead_hours=PRIMARY_LEAD)
    assert len(filtered) > 0

    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))
    dlr_amps = fe._city_ampacity(
        truth["air_temp"], truth["wind_speed"], truth["wind_direction"],
        truth["solar_radiation"], geometry,
    )
    truth_series = pd.Series(
        dlr_amps, index=pd.to_datetime(truth["datetime_utc"], utc=True)
    ).sort_index()

    # Hand-computed 24-hour shift: the value that occurred at time t is the
    # PREDICTION for time t + 24h.
    shifted = truth_series.copy()
    shifted.index = shifted.index + pd.Timedelta(hours=PRIMARY_LEAD)

    predicted = filtered.set_index(
        pd.to_datetime(filtered["datetime_utc"], utc=True)
    )["anchor_dlr_amps"]
    expected = shifted.reindex(predicted.index)
    assert not expected.isna().any()

    np.testing.assert_allclose(
        predicted.to_numpy(), expected.to_numpy(), rtol=1e-9, atol=1e-6
    )


def test_primary_24h_lead_caveat_is_distinct_from_legacy_caveat():
    assert fe.PRIMARY_24H_LEAD_CAVEAT != fe.EXPERIMENT_LEAD_REALIZABILITY_CAVEAT
    assert isinstance(fe.PRIMARY_24H_LEAD_CAVEAT, str)


def test_caveat_and_measured_lead_appear_in_emitted_report_for_24h_lead(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 20)
    fcst = _synthetic_weather_frame(periods=24 * 20)
    _patch_fetches_24h(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-20", lead_hours=PRIMARY_LEAD)
    filtered = fe.filter_to_exact_lead(frame, lead_hours=PRIMARY_LEAD)
    boundaries = fe._default_split_boundaries(frame)
    scored = fe.score_arms(
        filtered, {"persistence_24h": lambda f: f["anchor_dlr_amps"].to_numpy(dtype=float)}
    )

    report = fe.corridor_experiment_report(
        CITY, "2025-10-01", "2025-10-20", frame, filtered, boundaries, scored,
        lead_hours=PRIMARY_LEAD,
    )

    assert report["caveat"] == fe.PRIMARY_24H_LEAD_CAVEAT
    assert report["measured_lead_hours"] == float(PRIMARY_LEAD)
    assert report["filter_remainder"] == config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER
    import json
    assert fe.PRIMARY_24H_LEAD_CAVEAT in json.dumps(report)
    assert fe.EXPERIMENT_LEAD_REALIZABILITY_CAVEAT not in json.dumps(report)


def test_guard_test_split_access_raises_for_test_and_not_for_val():
    with pytest.raises(RuntimeError):
        fe._guard_test_split_access("test")
    # No exception for "val" while locked.
    fe._guard_test_split_access("val")


def test_main_at_24h_lead_scores_validation_split_with_24h_caveat(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = _synthetic_weather_frame(periods=24 * 60)
    fcst = _synthetic_weather_frame(periods=24 * 60)
    _patch_fetches_24h(monkeypatch, truth, fcst)

    fe.main([
        "--city", CITY, "--start", "2025-10-01", "--end", "2025-11-30",
        "--lead-hours", str(PRIMARY_LEAD),
    ])

    captured = capsys.readouterr()
    assert fe.PRIMARY_24H_LEAD_CAVEAT in captured.out
    assert fe.EXPERIMENT_LEAD_REALIZABILITY_CAVEAT not in captured.out
    assert "persistence_24h" in captured.out
    assert "raw_forecast" in captured.out
    assert "split=val" in captured.out
    assert f"lead_hours={PRIMARY_LEAD}" in captured.out


# ──────────────────────────────────────────────────────────────────────────
# Plan 03-04 Task 1: NON_FITTED_ARMS registry -- the four non-fitted arms
# (persistence_24h, nwp_wind_delta, raw_forecast, the oracle), all built
# directly from Plan 03-03's anchor/fcst_anchor column groups, NEVER via
# ampacity_forecast.forecast_ampacity/backtest_residuals/_point_forecast.
# ──────────────────────────────────────────────────────────────────────────


def _synthetic_24h_frame(monkeypatch, tmp_path, *, truth=None, fcst=None, periods=24 * 30):
    """
    Build a real `anchored_pair_frame` at the D-04 primary 24h lead from
    synthetic (or caller-supplied) truth/forecast weather, filtered to the
    exact-lead subset -- shared setup for every Task 1 arm test below.
    """
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth = truth if truth is not None else _synthetic_weather_frame(periods=periods)
    fcst = fcst if fcst is not None else _synthetic_weather_frame(periods=periods)
    _patch_fetches_24h(monkeypatch, truth, fcst)

    frame = fe.anchored_pair_frame(CITY, "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD)
    filtered = fe.filter_to_exact_lead(frame, lead_hours=PRIMARY_LEAD)
    assert len(filtered) > 0
    return truth, fcst, filtered


def test_non_fitted_arms_registry_has_exactly_four_entries_all_factories():
    assert len(fe.NON_FITTED_ARMS) == 4
    assert fe.ORACLE_ARM_NAME in fe.NON_FITTED_ARMS
    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))
    for name, factory in fe.NON_FITTED_ARMS.items():
        arm = factory(geometry)
        assert callable(arm), f"{name!r} is not a factory returning a callable"


def test_persistence_24h_arm_equals_anchor_dlr_amps_column(monkeypatch, tmp_path):
    truth, fcst, filtered = _synthetic_24h_frame(monkeypatch, tmp_path)
    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))
    arm = fe._make_persistence_24h_arm(geometry)
    pred = arm(filtered)
    np.testing.assert_allclose(pred, filtered["anchor_dlr_amps"].to_numpy(dtype=float))


def test_persistence_24h_arm_matches_independent_24h_shift_of_truth(monkeypatch, tmp_path):
    """
    Arm 0's prediction must equal an INDEPENDENTLY hand-computed 24-hour
    shift of the synthetic truth ampacity series -- never merely internally
    self-consistent with anchored_pair_frame's own anchor column.
    """
    truth, fcst, filtered = _synthetic_24h_frame(monkeypatch, tmp_path)
    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))
    dlr_amps = fe._city_ampacity(
        truth["air_temp"], truth["wind_speed"], truth["wind_direction"],
        truth["solar_radiation"], geometry,
    )
    truth_series = pd.Series(
        dlr_amps, index=pd.to_datetime(truth["datetime_utc"], utc=True)
    ).sort_index()
    shifted = truth_series.copy()
    shifted.index = shifted.index + pd.Timedelta(hours=PRIMARY_LEAD)

    arm = fe._make_persistence_24h_arm(geometry)
    pred = pd.Series(
        arm(filtered), index=pd.to_datetime(filtered["datetime_utc"], utc=True)
    )
    expected = shifted.reindex(pred.index)
    assert not expected.isna().any()
    np.testing.assert_allclose(pred.to_numpy(), expected.to_numpy(), rtol=1e-9, atol=1e-6)


def test_nwp_wind_delta_arm_reduces_to_persistence_when_forecast_anchor_equals_valid(
    monkeypatch, tmp_path
):
    """When fcst_wind_speed == fcst_anchor_wind_speed on every row (a forecast
    with zero change over the lead), arm 1 must equal arm 0 exactly."""
    truth = _synthetic_weather_frame(periods=24 * 30)
    # A constant forecast series: fcst_wind_speed at T equals fcst_anchor_
    # wind_speed at T (both come from the SAME constant series shifted).
    fcst = truth.copy()
    fcst["wind_speed"] = 4.0  # constant -> zero delta over any shift
    truth_frame, fcst_frame, filtered = _synthetic_24h_frame(
        monkeypatch, tmp_path, truth=truth, fcst=fcst,
    )
    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))

    arm0 = fe._make_persistence_24h_arm(geometry)
    arm1 = fe._make_nwp_wind_delta_arm(geometry)
    np.testing.assert_allclose(arm1(filtered), arm0(filtered), rtol=1e-9, atol=1e-6)


def test_nwp_wind_delta_arm_clamps_negative_wind_at_the_physical_zero_bound(
    monkeypatch, tmp_path
):
    truth = _synthetic_weather_frame(periods=24 * 30)
    fcst = _synthetic_weather_frame(periods=24 * 30)
    # A steadily DECREASING forecast wind series (slope -1/hour) means the
    # forecast's own value at valid time T is always exactly 24 units LOWER
    # than its own value at T - 24h (fcst_anchor_wind_speed) -- a uniform
    # delta of -24, far below the synthetic truth-derived anchor_wind_speed
    # (~3-7 m/s), so anchor_wind_speed + delta is negative on every row.
    t = np.arange(len(fcst), dtype=float)
    fcst["wind_speed"] = 1000.0 - t

    truth_frame, fcst_frame, filtered = _synthetic_24h_frame(
        monkeypatch, tmp_path, truth=truth, fcst=fcst,
    )

    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))
    raw = fe._nwp_wind_delta_raw_wind_speed(filtered)
    assert (raw < 0.0).any(), "test setup did not actually produce a negative raw wind speed"

    clamp_count = fe.nwp_wind_delta_clamp_count(filtered)
    assert clamp_count == int(np.sum(raw < 0.0))
    assert clamp_count > 0

    arm1 = fe._make_nwp_wind_delta_arm(geometry)
    pred = arm1(filtered)
    assert np.isfinite(pred).all()
    # The clamped wind speed used inside _city_ampacity was floored at
    # zero -- verified by re-deriving the same prediction from the
    # explicitly-clamped wind array.
    expected = fe._city_ampacity(
        filtered["anchor_air_temp"], np.maximum(raw, 0.0), filtered["anchor_wind_direction"],
        filtered["anchor_solar_radiation"], geometry,
    )
    np.testing.assert_allclose(pred, expected)


def test_raw_forecast_arm_equals_city_ampacity_on_forecast_columns(monkeypatch, tmp_path):
    truth, fcst, filtered = _synthetic_24h_frame(monkeypatch, tmp_path)
    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))
    arm = fe._make_raw_forecast_arm(geometry)
    expected = fe._city_ampacity(
        filtered["fcst_air_temp"], filtered["fcst_wind_speed"], filtered["fcst_wind_direction"],
        filtered["fcst_solar_radiation"], geometry,
    )
    np.testing.assert_allclose(arm(filtered), expected)


def test_oracle_arm_uses_truth_wind_and_forecast_thermal_inputs(monkeypatch, tmp_path):
    truth, fcst, filtered = _synthetic_24h_frame(monkeypatch, tmp_path)
    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))
    arm = fe._make_oracle_arm(geometry)
    expected = fe._city_ampacity(
        filtered["fcst_air_temp"], filtered["truth_wind_speed"], filtered["truth_wind_direction"],
        filtered["fcst_solar_radiation"], geometry,
    )
    np.testing.assert_allclose(arm(filtered), expected)


def test_oracle_and_raw_forecast_agree_and_equal_truth_when_forecast_equals_truth(
    monkeypatch, tmp_path
):
    """
    Degenerate-input sanity check: when the forecast weather equals the
    truth weather on every row, arm 2 (raw_forecast) and arm 6 (oracle)
    must produce identical predictions, and both must equal the truth
    ampacity. This is the shape the bit-identity artifact took in the real
    1-hour data (03-CONTEXT.md D-04) -- a check that would have caught it
    on synthetic data alone, without needing a live network call.
    """
    truth = _synthetic_weather_frame(periods=24 * 30)
    fcst = truth.copy()  # forecast == truth on every row
    truth_frame, fcst_frame, filtered = _synthetic_24h_frame(
        monkeypatch, tmp_path, truth=truth, fcst=fcst,
    )
    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))

    raw_forecast_arm = fe._make_raw_forecast_arm(geometry)
    oracle_arm = fe._make_oracle_arm(geometry)

    pred_raw = raw_forecast_arm(filtered)
    pred_oracle = oracle_arm(filtered)
    np.testing.assert_allclose(pred_raw, pred_oracle)
    np.testing.assert_allclose(pred_raw, filtered["truth_dlr_amps"].to_numpy(dtype=float))


def test_oracle_arm_factory_docstring_first_line_states_not_a_forecast():
    first_line = fe._make_oracle_arm.__doc__.strip().splitlines()[0].strip()
    assert "not" in first_line.lower() and "forecast" in first_line.lower()


def test_every_registry_arm_returns_full_length_array_for_the_scored_frame(
    monkeypatch, tmp_path
):
    truth, fcst, filtered = _synthetic_24h_frame(monkeypatch, tmp_path)
    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))
    for name, factory in fe.NON_FITTED_ARMS.items():
        arm = factory(geometry)
        pred = np.asarray(arm(filtered), dtype=float)
        assert len(pred) == len(filtered), f"arm {name!r} returned the wrong length"


def test_score_arms_scores_the_full_non_fitted_arm_registry(monkeypatch, tmp_path):
    """score_arms still enforces its length/uniqueness/sort invariants when
    scoring the real four-arm registry (not just the minimal hand-built
    frames the pre-existing score_arms tests use)."""
    truth, fcst, filtered = _synthetic_24h_frame(monkeypatch, tmp_path)
    geometry = corridor_discretization.corridor_geometry(fe._corridor_for_city(CITY))
    arms = {name: factory(geometry) for name, factory in fe.NON_FITTED_ARMS.items()}
    scored = fe.score_arms(filtered, arms)
    assert set(scored["candidates"]) == set(fe.NON_FITTED_ARMS)
    for name, s in scored["candidates"].items():
        assert s["rows"] == len(filtered)


# ──────────────────────────────────────────────────────────────────────────
# Plan 03-04 Task 2: corridor-level assembly, weakest-link reduction (via
# forecast_training.corridor_weakest_link, never a second np.minimum), and
# the oracle's structural isolation from report["candidates"].
# ──────────────────────────────────────────────────────────────────────────

AUSTIN_LATLON = config.CITY_COORDINATES["AUSTIN"]
CC_LATLON = config.CITY_COORDINATES["CORPUS_CHRISTI"]
CORRIDOR = "AUSTIN_CORPUS_CHRISTI"


def _patch_two_city_24h_fetches(monkeypatch, truth_by_latlon, fcst_by_latlon):
    """
    Route `open_meteo_provider.fetch_open_meteo`/`open_meteo_forecast_
    provider.fetch_previous_runs` to different synthetic frames per
    (lat, lon) -- the corridor path fetches both endpoint cities, so a
    single-return-value patch (`_patch_fetches_24h`) cannot distinguish them.
    """

    def fake_truth_fetch(lat, lon, start, end):
        return truth_by_latlon[(lat, lon)].copy()

    def fake_fcst_fetch(lat, lon, start, end, previous_day=None):
        return fcst_by_latlon[(lat, lon)].copy()

    monkeypatch.setattr(fe.open_meteo_provider, "fetch_open_meteo", fake_truth_fetch)
    monkeypatch.setattr(
        fe.open_meteo_forecast_provider, "fetch_previous_runs", fake_fcst_fetch
    )


def _flat_weather_frame(wind_speed, wind_direction=90.0, air_temp=25.0,
                         solar_radiation=300.0, start="2025-10-01", periods=24 * 10):
    """A weather frame with every column held FLAT except wind_speed, so
    ampacity ordering between two such frames is driven by wind_speed alone
    -- used by the mixed-bottleneck and tie-break tests below, where the
    test needs to CONTROL which city is the bottleneck at a given time."""
    idx = pd.date_range(start, periods=periods, freq="h", tz="UTC")
    n = len(idx)
    return pd.DataFrame({
        "datetime_utc": idx,
        "air_temp": np.full(n, air_temp),
        "wind_speed": np.asarray(wind_speed, dtype=float),
        "wind_direction": np.full(n, wind_direction),
        "solar_radiation": np.full(n, solar_radiation),
        "relative_humidity": np.full(n, 55.0),
    })


def test_corridor_anchored_pair_frame_assembles_from_both_endpoints_and_inner_joins(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth_a = _synthetic_weather_frame(periods=24 * 30)
    truth_b = _synthetic_weather_frame(periods=24 * 30)
    fcst_a = _synthetic_weather_frame(periods=24 * 30)
    fcst_b = _synthetic_weather_frame(periods=24 * 30)
    _patch_two_city_24h_fetches(
        monkeypatch,
        {AUSTIN_LATLON: truth_a, CC_LATLON: truth_b},
        {AUSTIN_LATLON: fcst_a, CC_LATLON: fcst_b},
    )

    frame = fe.corridor_anchored_pair_frame(
        CORRIDOR, "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD,
    )
    city_a_frame = fe.anchored_pair_frame("AUSTIN", "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD)
    city_b_frame = fe.anchored_pair_frame(
        "CORPUS_CHRISTI", "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD
    )

    assert len(frame) > 0
    assert len(frame) <= min(len(city_a_frame), len(city_b_frame))
    assert set(frame["datetime_utc"]) <= set(city_a_frame["datetime_utc"])
    assert set(frame["datetime_utc"]) <= set(city_b_frame["datetime_utc"])


def test_corridor_truth_reduction_matches_forecast_training_corridor_weakest_link(
    monkeypatch, tmp_path
):
    import forecast_training

    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth_a = _synthetic_weather_frame(periods=24 * 30)
    truth_b = _synthetic_weather_frame(periods=24 * 30)
    fcst_a = _synthetic_weather_frame(periods=24 * 30)
    fcst_b = _synthetic_weather_frame(periods=24 * 30)
    _patch_two_city_24h_fetches(
        monkeypatch,
        {AUSTIN_LATLON: truth_a, CC_LATLON: truth_b},
        {AUSTIN_LATLON: fcst_a, CC_LATLON: fcst_b},
    )

    frame = fe.corridor_anchored_pair_frame(
        CORRIDOR, "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD,
    )
    city_a_frame = fe.anchored_pair_frame("AUSTIN", "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD)
    city_b_frame = fe.anchored_pair_frame(
        "CORPUS_CHRISTI", "2025-10-01", "2025-10-30", lead_hours=PRIMARY_LEAD
    )
    merged = city_a_frame.merge(city_b_frame, on="datetime_utc", suffixes=("_a", "_b"))

    expected_amps, expected_bottleneck, expected_winning = forecast_training.corridor_weakest_link(
        merged["truth_dlr_amps_a"].to_numpy(dtype=float),
        merged["truth_dlr_amps_b"].to_numpy(dtype=float),
        {"truth_air_temp": merged["truth_air_temp_a"].to_numpy(dtype=float)},
        {"truth_air_temp": merged["truth_air_temp_b"].to_numpy(dtype=float)},
    )

    np.testing.assert_allclose(frame["truth_dlr_amps"].to_numpy(), expected_amps)
    np.testing.assert_array_equal(
        frame["bottleneck_index_truth"].to_numpy(), expected_bottleneck
    )
    np.testing.assert_allclose(
        frame["truth_air_temp"].to_numpy(), expected_winning["truth_air_temp"]
    )


def test_corridor_truth_tie_resolves_to_the_first_endpoint_city(monkeypatch, tmp_path):
    """When both endpoint cities' truth ampacity is IDENTICAL on every row
    (an exact tie), the bottleneck must resolve to the first endpoint city
    (AUSTIN, index 0 in config.CORRIDOR_ENDPOINTS[CORRIDOR]) -- matching
    forecast_training.corridor_weakest_link's own documented tie-break."""
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    identical_truth = _flat_weather_frame(wind_speed=np.full(24 * 10, 5.0), periods=24 * 10)
    identical_fcst = identical_truth.copy()
    _patch_two_city_24h_fetches(
        monkeypatch,
        {AUSTIN_LATLON: identical_truth, CC_LATLON: identical_truth},
        {AUSTIN_LATLON: identical_fcst, CC_LATLON: identical_fcst},
    )

    frame = fe.corridor_anchored_pair_frame(
        CORRIDOR, "2025-10-01", "2025-10-10", lead_hours=PRIMARY_LEAD,
    )
    assert len(frame) > 0
    assert (frame["bottleneck_index_truth"].to_numpy() == 0).all()


def test_corridor_mixed_bottleneck_between_anchor_and_valid_time_selected_per_group(
    monkeypatch, tmp_path
):
    """
    Construct two cities whose wind speed is a 48-hour sinusoid, exactly
    out of phase with each other: city A's wind at time t equals city B's
    wind at t - 24h, and vice versa. Since 24h is exactly half the 48h
    period, this GUARANTEES the bottleneck city at the anchor time
    (T - 24h) differs from the bottleneck city at the valid time T for
    every row except a sine zero-crossing -- the exact "mixed bottleneck"
    shape this task's own reduction discipline exists to handle correctly
    (never collapsing both groups to one selection).
    """
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    periods = 24 * 10
    t = np.arange(periods, dtype=float)
    omega = 2.0 * np.pi / 48.0
    wind_a = 10.0 + 5.0 * np.sin(omega * t)
    wind_b = 10.0 - 5.0 * np.sin(omega * t)

    truth_a = _flat_weather_frame(wind_a, periods=periods)
    truth_b = _flat_weather_frame(wind_b, periods=periods)
    fcst_a = truth_a.copy()
    fcst_b = truth_b.copy()
    _patch_two_city_24h_fetches(
        monkeypatch,
        {AUSTIN_LATLON: truth_a, CC_LATLON: truth_b},
        {AUSTIN_LATLON: fcst_a, CC_LATLON: fcst_b},
    )

    frame = fe.corridor_anchored_pair_frame(
        CORRIDOR, "2025-10-01", "2025-10-10", lead_hours=PRIMARY_LEAD,
    )
    assert len(frame) > 0

    mismatched = frame["bottleneck_index_anchor"] != frame["bottleneck_index_truth"]
    assert mismatched.sum() > 0, (
        "test construction did not actually produce a row whose anchor-time "
        "bottleneck differs from its valid-time bottleneck"
    )
    # Most rows should mismatch (only sine zero-crossings coincide) --
    # confirms the two groups are genuinely reduced independently, not
    # accidentally sharing one selection.
    assert mismatched.sum() > len(frame) * 0.5


def test_corridor_anchored_pair_frame_has_pred_and_bottleneck_columns_for_every_arm(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    truth_a = _synthetic_weather_frame(periods=24 * 20)
    truth_b = _synthetic_weather_frame(periods=24 * 20)
    fcst_a = _synthetic_weather_frame(periods=24 * 20)
    fcst_b = _synthetic_weather_frame(periods=24 * 20)
    _patch_two_city_24h_fetches(
        monkeypatch,
        {AUSTIN_LATLON: truth_a, CC_LATLON: truth_b},
        {AUSTIN_LATLON: fcst_a, CC_LATLON: fcst_b},
    )

    frame = fe.corridor_anchored_pair_frame(
        CORRIDOR, "2025-10-01", "2025-10-20", lead_hours=PRIMARY_LEAD,
    )
    for arm_name in fe.NON_FITTED_ARMS:
        assert f"pred_{arm_name}" in frame.columns
        assert f"bottleneck_index_{arm_name}" in frame.columns
        assert np.isfinite(frame[f"pred_{arm_name}"].to_numpy()).all()


def test_corridor_experiment_report_pops_oracle_into_its_own_key():
    """
    Direct, network-free unit test of the structural isolation itself: even
    a hand-built `scored["candidates"]` mapping that INCLUDES the oracle is
    reduced to exactly 3 candidates in the emitted report, with the oracle
    moved to its own top-level key -- the isolation is a property of
    `corridor_experiment_report`, not caller discipline.
    """
    idx = pd.date_range("2025-10-01", periods=5, freq="h", tz="UTC")
    frame = pd.DataFrame({"datetime_utc": idx})
    boundaries = fe._default_split_boundaries(frame)
    scored = {
        "candidates": {
            "persistence_24h": {"mae": 1.0, "rmse": 1.0, "rows": 5},
            "raw_forecast": {"mae": 2.0, "rmse": 2.0, "rows": 5},
            "nwp_wind_delta": {"mae": 3.0, "rmse": 3.0, "rows": 5},
            fe.ORACLE_ARM_NAME: {"mae": 0.0, "rmse": 0.0, "rows": 5},
        },
        "test_index": list(range(5)),
    }

    report = fe.corridor_experiment_report(
        CORRIDOR, "2025-10-01", "2025-10-05", frame, frame, boundaries, scored,
        lead_hours=PRIMARY_LEAD, split="val", id_key="corridor",
    )

    assert fe.ORACLE_ARM_NAME not in report["candidates"]
    assert len(report["candidates"]) == 3
    assert set(report["candidates"]) == {"persistence_24h", "raw_forecast", "nwp_wind_delta"}
    assert "oracle_diagnostic" in report
    assert report["oracle_diagnostic"]["score"] == scored["candidates"][fe.ORACLE_ARM_NAME]
    assert "not a forecast" in report["oracle_diagnostic"]["statement"].lower()
    assert report["corridor"] == CORRIDOR
    assert report["split"] == "val"


def test_corridor_experiment_report_omits_oracle_key_when_no_oracle_scored():
    """The city-level tracer path never scores the oracle -- the report
    must not gain an oracle_diagnostic key it has nothing to fill."""
    idx = pd.date_range("2025-10-01", periods=5, freq="h", tz="UTC")
    frame = pd.DataFrame({"datetime_utc": idx})
    boundaries = fe._default_split_boundaries(frame)
    scored = {
        "candidates": {"persistence": {"mae": 1.0, "rmse": 1.0, "rows": 5}},
        "test_index": list(range(5)),
    }
    report = fe.corridor_experiment_report(
        "AUSTIN", "2025-10-01", "2025-10-05", frame, frame, boundaries, scored, lead_hours=1,
    )
    assert "oracle_diagnostic" not in report


def test_main_scores_both_corridors_from_one_invocation(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))

    frames = {}
    for city in config.CITY_COORDINATES:
        frames[config.CITY_COORDINATES[city]] = _synthetic_weather_frame(
            periods=24 * 90, start="2025-10-01"
        )

    def fake_truth_fetch(lat, lon, start, end):
        return frames[(lat, lon)].copy()

    def fake_fcst_fetch(lat, lon, start, end, previous_day=None):
        return frames[(lat, lon)].copy()

    monkeypatch.setattr(fe.open_meteo_provider, "fetch_open_meteo", fake_truth_fetch)
    monkeypatch.setattr(
        fe.open_meteo_forecast_provider, "fetch_previous_runs", fake_fcst_fetch
    )

    fe.main([
        "--lead-hours", str(PRIMARY_LEAD), "--start", "2025-10-01", "--end", "2025-12-30",
    ])

    captured = capsys.readouterr()
    assert captured.out.count("SUMMARY: ") == len(config.CORRIDOR_ENDPOINTS)
    for corridor in config.CORRIDOR_ENDPOINTS:
        assert corridor in captured.out
    assert "split=val" in captured.out
    assert fe.ORACLE_ARM_NAME in captured.out
    assert "NON-FORECAST DIAGNOSTIC" in captured.out

    for corridor in config.CORRIDOR_ENDPOINTS:
        report_path = os.path.join(str(tmp_path), f"experiment_report_{corridor}.json")
        assert os.path.exists(report_path)
        with open(report_path) as fh:
            report = json.load(fh)
        assert len(report["candidates"]) == 3
        assert fe.ORACLE_ARM_NAME not in report["candidates"]
        assert "oracle_diagnostic" in report


# ──────────────────────────────────────────────────────────────────────────
# Import-time no-side-effects
# ──────────────────────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects():
    import importlib
    importlib.reload(fe)
