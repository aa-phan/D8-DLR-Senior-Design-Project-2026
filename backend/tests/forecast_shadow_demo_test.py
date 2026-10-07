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


class _StopHereSentinel(Exception):
    """
    Raised by a monkeypatched `fetch_live_forecast_for_valid_time` purely to
    halt `run_once` right after capturing its call args -- deliberately NOT
    `shadow.StaleOrMissingDataError`, which `run_once` now catches itself
    (2026-10-06 fix: a forecast-fetch failure falls back to the static
    rating instead of propagating) and would make these grid-selection
    tests observe a returned `ShadowPrediction`, not a raised exception.
    """


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
        raise _StopHereSentinel("stop here -- only capturing the call")

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _capture)
    with pytest.raises(_StopHereSentinel):
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
        raise _StopHereSentinel("stop here -- only capturing the call")

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _capture)
    before = pd.Timestamp.utcnow()
    with pytest.raises(_StopHereSentinel):
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


def test_run_once_falls_back_to_static_rating_when_forecast_fetch_fails(monkeypatch, capsys):
    """
    Found live on GitHub Actions (2026-10-06): `fetch_live_forecast_for_
    valid_time` sat outside any try/except in `run_once`, so a real
    network timeout hitting it (confirmed independently against BOTH
    Open-Meteo and, in a separate run, TCEQ) escaped all the way to
    `forecast_shadow_collect.py`'s broad `except Exception`, which logs a
    HARD FAILURE (exit code 1) -- contradicting `collect_once`'s own
    comment, which already promised a graceful, logged fallback for "a
    missing anchor/model/forecast source". Without a forecast row there is
    no data to compute even `raw_forecast`'s ampacity from, so the correct
    fallback is this project's established total-unavailability discipline
    (`DLRSafetyMonitor`'s G6 gate: report the known-conservative static
    rating, never crash or guess) -- per endpoint city, reduced by the
    same weakest-link principle used elsewhere.
    """
    def _raise_stale(corridor, valid_time, horizon_minutes, *, lat, lon):
        raise shadow.StaleOrMissingDataError(
            f"fetch_live_forecast_for_valid_time: retrieval failed for "
            f"corridor {corridor!r}: synthetic timeout"
        )

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _raise_stale)

    prediction = demo.run_once("MIDLAND_EL_PASO", "ml_wind_corrected")

    assert prediction.method == "static_rating_fallback"
    assert prediction.fallback_used is True
    assert "synthetic timeout" in prediction.fallback_reason
    assert prediction.model_version is None
    # MIDLAND=1800.0, EL_PASO=1450.0 (config.STATIC_RATINGS) -- the
    # weakest-link minimum, never an average or the stronger city's value.
    assert prediction.ampacity_amps == min(
        config.STATIC_RATINGS["MIDLAND"], config.STATIC_RATINGS["EL_PASO"]
    )
    assert prediction.ampacity_amps == 1450.0
    # ShadowTimestamps must still be real and internally consistent even
    # though the HTTP call never completed -- all four fields are
    # computable from valid_time/horizon_minutes alone.
    assert prediction.timestamps.valid_time > prediction.timestamps.decision_time
    assert (
        prediction.timestamps.valid_time - prediction.timestamps.initialization_time
    ) == pd.Timedelta(minutes=1440)

    captured = capsys.readouterr()
    assert "actual=static_rating_fallback" in captured.out
    assert "fallback_used=True" in captured.out


def test_run_once_falls_back_to_raw_forecast_when_no_persisted_model_exists(monkeypatch, tmp_path, capsys):
    """
    Negative control: a missing persisted model (`FileNotFoundError` from
    `load_correction_model`) must be caught by `run_once` itself and demoed
    as `raw_forecast` -- not an unhandled crash, and not silently reported
    as though `ml_wind_corrected` had actually run.

    `fallback_used` must be `True` here: a missing model artifact IS a
    fallback, even though it happens at the script level before
    `ShadowPipeline` ever runs, not inside `ShadowPipeline.predict`. Found
    via GitHub Actions' real first run (2026-10-06): the runner has no
    persisted model at all (the `data/shadow/models/` directory is
    git-ignored, local-only), and the previous version of this test pinned
    the resulting `requested=ml_wind_corrected actual=raw_forecast
    fallback_used=False` as correct -- exactly the fallback-signal
    conflation this project's reporting discipline exists to prevent
    elsewhere. Fixed in `run_once` via `dataclasses.replace`, so both the
    printed line and the persisted log entry are honest about it.
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
    assert prediction.fallback_used is True
    assert prediction.fallback_reason is not None
    assert "no persisted" in prediction.fallback_reason
    assert "ml_wind_corrected" in prediction.fallback_reason
    assert "AUSTIN_CORPUS_CHRISTI" in prediction.fallback_reason
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


# ──────────────────────────────────────────────────────────────────────
# Plan 05-02: run_once_all_methods -- the five-candidate orchestration
# entry point. Network-free throughout: the shared fetch itself is
# monkeypatched to a synthetic success/failure, never a real network call.
# ──────────────────────────────────────────────────────────────────────

def _fake_shared_inputs_factory(cities, *, air_temp=30.0, wind_speed=5.0, wind_direction=90.0,
                                  solar=500.0, anchor_wind_speed=4.0, anchor_wind_direction=95.0,
                                  anchor_air_temp=29.0):
    def _fake_shared_inputs(corridor_arg, *, valid_time, decision_time, horizon_minutes):
        frame = pd.DataFrame([{
            "fcst_air_temp": air_temp, "fcst_wind_speed": wind_speed,
            "fcst_wind_direction": wind_direction, "fcst_solar_radiation": solar,
        }])
        frame.attrs["geometry"] = None
        anchor = pd.Series({
            "anchor_wind_speed": anchor_wind_speed, "anchor_wind_direction": anchor_wind_direction,
            "anchor_air_temp": anchor_air_temp, "anchor_observation_time": decision_time,
            "anchor_source": "tceq", "anchor_station": "TEST",
        })
        return {
            city: shadow.SharedCityFetchResult(city, frame.copy(), None, anchor.copy(), None)
            for city in cities
        }
    return _fake_shared_inputs


def test_run_once_all_methods_attempts_all_five_and_isolates_one_sabotaged_candidate(monkeypatch, tmp_path):
    """D-07: a REAL code-level exception inside one candidate's own
    computation must be caught by that candidate's own try/except and
    recorded as status='failed'; the other four candidates still compute
    and log for the same cycle."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    corridor = "AUSTIN_CORPUS_CHRISTI"
    cities = config.CORRIDOR_ENDPOINTS[corridor]

    monkeypatch.setattr(shadow, "fetch_shared_corridor_inputs", _fake_shared_inputs_factory(cities))

    original = shadow.Persistence24hShadowMethod.compute

    def _raise(self, corridor_arg, decision_time):
        raise RuntimeError("deliberate sabotage for the isolation test")

    monkeypatch.setattr(shadow.Persistence24hShadowMethod, "compute", _raise)
    try:
        results = demo.run_once_all_methods(corridor)
    finally:
        shadow.Persistence24hShadowMethod.compute = original

    assert set(results) == set(shadow.CANDIDATE_METHOD_NAMES)
    assert results["persistence_24h"].status == "failed"
    assert "deliberate sabotage" in (results["persistence_24h"].reason or "")
    for name in shadow.CANDIDATE_METHOD_NAMES:
        if name == "persistence_24h":
            continue
        assert results[name].status != "failed", (name, results[name])

    # The same cycle's log line must still carry all five candidates --
    # one candidate's failure must not have aborted the write.
    import json
    path = __import__("os").path.join(str(tmp_path), f"{corridor}.jsonl")
    with open(path) as fh:
        record = json.loads(fh.readline())
    assert record["schema_version"] == 2
    assert set(record["candidates"]) == set(shadow.CANDIDATE_METHOD_NAMES)
    assert record["candidates"]["persistence_24h"]["status"] == "failed"


def test_run_once_all_methods_reports_reference_refit_as_unavailable_on_a_clean_run(monkeypatch, tmp_path):
    """On a clean run (no sabotage, no persisted reference artifact),
    `reference_ml_refit_24h` must read unavailable, and the three
    per-city-reduced candidates must reach status='ok' (real persisted
    wind/cooling models already exist in this repo for this corridor)."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    corridor = "AUSTIN_CORPUS_CHRISTI"
    cities = config.CORRIDOR_ENDPOINTS[corridor]
    monkeypatch.setattr(shadow, "fetch_shared_corridor_inputs", _fake_shared_inputs_factory(cities))

    results = demo.run_once_all_methods(corridor)

    assert results["reference_ml_refit_24h"].status == "unavailable"
    assert "reference_ml_refit_24h" in (results["reference_ml_refit_24h"].reason or "")
    for name in shadow.CANDIDATE_METHOD_NAMES:
        assert results[name].status != "failed", (name, results[name])


def test_run_once_all_methods_marks_ml_wind_corrected_unavailable_when_one_citys_anchor_missing(monkeypatch, tmp_path):
    """D-04: a candidate whose required inputs are missing for this cycle
    (here, one city's anchor) is recorded unavailable, independent of
    every other candidate's own availability -- raw_forecast (needs no
    anchor) must still read ok."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    corridor = "AUSTIN_CORPUS_CHRISTI"
    cities = config.CORRIDOR_ENDPOINTS[corridor]

    frame = pd.DataFrame([{
        "fcst_air_temp": 30.0, "fcst_wind_speed": 5.0, "fcst_wind_direction": 90.0,
        "fcst_solar_radiation": 500.0,
    }])
    frame.attrs["geometry"] = None
    anchor = pd.Series({
        "anchor_wind_speed": 4.0, "anchor_wind_direction": 95.0, "anchor_air_temp": 29.0,
        "anchor_observation_time": pd.Timestamp.now(tz="UTC"), "anchor_source": "tceq",
        "anchor_station": "TEST",
    })

    def _fake_shared_inputs(corridor_arg, *, valid_time, decision_time, horizon_minutes):
        results = {}
        for i, city in enumerate(cities):
            if i == 0:
                results[city] = shadow.SharedCityFetchResult(city, frame.copy(), None, None, "simulated anchor gap")
            else:
                results[city] = shadow.SharedCityFetchResult(city, frame.copy(), None, anchor.copy(), None)
        return results

    monkeypatch.setattr(shadow, "fetch_shared_corridor_inputs", _fake_shared_inputs)

    results = demo.run_once_all_methods(corridor)

    assert results["ml_wind_corrected"].status == "unavailable"
    assert results["ml_cooling_corrected"].status == "unavailable"
    assert results["raw_forecast"].status == "ok"
