"""
Tests for the demo/integration entry point
(`backend/forecast_shadow_demo.py`). Network-free throughout; this module
is never invoked by production code.

Adversarial mutation-testing pass (2026-10-06): this module had ZERO
dedicated tests before this file -- it was only ever exercised via real
live network runs reported in prior passes, or indirectly as a black box
by `forecast_shadow_collect_test.py`'s monkeypatching of `run_once` itself
(which never exercises `run_once`'s own internal logic at all). Every
mutation applied to this module's own code survived trivially (there was
nothing to run). These tests close that gap.
"""
from __future__ import annotations

import pandas as pd
import pytest

import config
import forecast_shadow_demo as demo
import forecast_shadow_pipeline as shadow


def test_run_once_requests_a_valid_time_on_the_six_hour_utc_grid(monkeypatch):
    """
    The provider's Previous-Runs model only has runs at 6-hourly UTC
    boundaries -- `run_once`'s own comment explains this was found by an
    actual live run, not a synthetic test. Pins the grid-alignment
    property: whatever `valid_time` `run_once` selects, it must be exactly
    on an hour%6==0, minute==0, second==0 boundary.

    `utcnow` is pinned (not raced against real wall-clock time) to a value
    chosen so the while loop's body executes at least once -- at an
    arbitrary real "now", the initial `floor(now+12h, 6h)` candidate can
    already clear the `now+11h` threshold with ZERO loop iterations,
    which would make a broken loop body (wrong advance amount, wrong
    comparison) silently inert and unobservable. 05:59:59 is chosen so
    `floor(now+12h, 6h)` lands on the PREVIOUS 6h boundary relative to
    `now+12h`, one 6h step short of `now+11h`, forcing exactly one
    iteration.
    """
    fixed_now = pd.Timestamp("2026-10-07T05:59:59")

    class _FixedTimestamp(pd.Timestamp):
        @classmethod
        def utcnow(cls):
            return fixed_now

    monkeypatch.setattr(pd, "Timestamp", _FixedTimestamp)

    captured = {}

    def _capture(corridor, valid_time, horizon_minutes, *, lat, lon):
        captured["valid_time"] = valid_time
        raise shadow.StaleOrMissingDataError("stop here -- only capturing the call")

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _capture)
    with pytest.raises(shadow.StaleOrMissingDataError):
        demo.run_once("AUSTIN_CORPUS_CHRISTI")

    valid_time = captured["valid_time"]
    assert valid_time == pd.Timestamp("2026-10-07T18:00:00")
    assert valid_time.hour % 6 == 0
    assert valid_time.minute == 0
    assert valid_time.second == 0
    assert valid_time.microsecond == 0
    assert valid_time > fixed_now + pd.Timedelta(hours=11)


def test_run_once_requests_a_valid_time_strictly_more_than_eleven_hours_out(monkeypatch):
    """
    The while loop's own purpose: `candidate` must land strictly after
    `now + 11h`, not merely at-or-after -- survived mutant candidates
    (removing the `+ pd.Timedelta(hours=12)` offset, or changing the loop's
    `<=` comparison / its `+= pd.Timedelta(hours=6)` advance) would all
    produce a valid_time too close to "now" for the run it implies to
    actually be available yet. Probed directly: this property is what
    distinguishes a correct grid-selection from several plausible broken
    ones.
    """
    captured = {}

    def _capture(corridor, valid_time, horizon_minutes, *, lat, lon):
        captured["valid_time"] = valid_time
        raise shadow.StaleOrMissingDataError("stop here -- only capturing the call")

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _capture)
    before = pd.Timestamp.utcnow()
    with pytest.raises(shadow.StaleOrMissingDataError):
        demo.run_once("AUSTIN_CORPUS_CHRISTI")
    after = pd.Timestamp.utcnow()

    valid_time = captured["valid_time"]
    # tz-naive utcnow() vs the (also tz-naive, per pd.Timestamp.utcnow)
    # candidate -- compare directly.
    assert valid_time > before + pd.Timedelta(hours=11)
    assert valid_time > after + pd.Timedelta(hours=11)


def test_run_once_uses_raw_forecast_method_without_attempting_any_model_load(monkeypatch):
    """`method_name="raw_forecast"` must never even attempt
    `load_correction_model` -- there is no model to load for the
    uncorrected baseline."""
    def _should_not_be_called(*a, **kw):
        raise AssertionError("load_correction_model must not be called for raw_forecast")

    monkeypatch.setattr(shadow, "load_correction_model", _should_not_be_called)

    def _fake_fetch(corridor, valid_time, horizon_minutes, *, lat, lon):
        row = pd.Series({
            "fcst_air_temp": 25.0, "fcst_wind_speed": 3.0, "fcst_wind_direction": 180.0,
            "fcst_solar_radiation": 500.0, "datetime_utc": valid_time,
        })
        ts = shadow.ShadowTimestamps(
            initialization_time=valid_time - pd.Timedelta(minutes=horizon_minutes),
            availability_time=valid_time - pd.Timedelta(minutes=horizon_minutes) + pd.Timedelta(hours=6),
            decision_time=pd.Timestamp.now(tz="UTC"),
            valid_time=valid_time, horizon_minutes=horizon_minutes,
        )
        return row, ts

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _fake_fetch)
    prediction = demo.run_once("AUSTIN_CORPUS_CHRISTI", "raw_forecast")
    assert prediction.method == "raw_forecast"
    assert prediction.fallback_used is False


def test_run_once_falls_back_to_raw_forecast_when_no_persisted_model_exists(monkeypatch, tmp_path, capsys):
    """
    Negative control: a missing persisted model (`FileNotFoundError` from
    `load_correction_model`) must be caught by `run_once` itself and demoed
    as `raw_forecast` -- not an unhandled crash, and not silently reported
    as though `ml_wind_corrected` had actually run.
    """
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path))

    def _fake_fetch(corridor, valid_time, horizon_minutes, *, lat, lon):
        row = pd.Series({
            "fcst_air_temp": 25.0, "fcst_wind_speed": 3.0, "fcst_wind_direction": 180.0,
            "fcst_solar_radiation": 500.0, "datetime_utc": valid_time,
        })
        ts = shadow.ShadowTimestamps(
            initialization_time=valid_time - pd.Timedelta(minutes=horizon_minutes),
            availability_time=valid_time - pd.Timedelta(minutes=horizon_minutes) + pd.Timedelta(hours=6),
            decision_time=pd.Timestamp.now(tz="UTC"),
            valid_time=valid_time, horizon_minutes=horizon_minutes,
        )
        return row, ts

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _fake_fetch)
    prediction = demo.run_once("AUSTIN_CORPUS_CHRISTI", "ml_wind_corrected")
    assert prediction.method == "raw_forecast"
    assert prediction.fallback_used is False  # the demo-level fallback, not ShadowPipeline's own
    captured = capsys.readouterr()
    assert "no persisted" in captured.err


def test_run_once_logs_and_returns_the_same_prediction(monkeypatch, tmp_path):
    """`run_once` must log the prediction it returns, not a different one
    (e.g. logging before a later mutation of the value, or logging the
    wrong object)."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))

    def _fake_fetch(corridor, valid_time, horizon_minutes, *, lat, lon):
        row = pd.Series({
            "fcst_air_temp": 25.0, "fcst_wind_speed": 3.0, "fcst_wind_direction": 180.0,
            "fcst_solar_radiation": 500.0, "datetime_utc": valid_time,
        })
        ts = shadow.ShadowTimestamps(
            initialization_time=valid_time - pd.Timedelta(minutes=horizon_minutes),
            availability_time=valid_time - pd.Timedelta(minutes=horizon_minutes) + pd.Timedelta(hours=6),
            decision_time=pd.Timestamp.now(tz="UTC"),
            valid_time=valid_time, horizon_minutes=horizon_minutes,
        )
        return row, ts

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _fake_fetch)
    prediction = demo.run_once("AUSTIN_CORPUS_CHRISTI", "raw_forecast")

    import json
    path = __import__("os").path.join(str(tmp_path), "AUSTIN_CORPUS_CHRISTI.jsonl")
    with open(path) as fh:
        logged = json.loads(fh.readline())
    assert logged["ampacity_amps"] == prediction.ampacity_amps
    assert logged["method"] == prediction.method
