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
import weather_provider


@pytest.fixture(autouse=True)
def _isolate_shadow_predictions_dir(monkeypatch, tmp_path_factory):
    """
    Never let a test append to the real `data/shadow/predictions/` logs
    (found 2026-10-12: three `run_once` tests lacked this redirect and
    polluted both the legacy corridor logs and the per-city logs). Tests
    that need to read the log re-patch `SHADOW_PREDICTIONS_DIR` to their own
    `tmp_path`, which takes precedence.
    """
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path_factory.mktemp("predictions")))


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

    def _capture(city, valid_time, horizon_minutes, *, lat, lon):
        captured["valid_time"] = valid_time
        raise _StopHereSentinel("stop here -- only capturing the call")

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _capture)
    with pytest.raises(_StopHereSentinel):
        demo.run_once("AUSTIN")

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

    def _capture(city, valid_time, horizon_minutes, *, lat, lon):
        captured["valid_time"] = valid_time
        raise _StopHereSentinel("stop here -- only capturing the call")

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _capture)
    before = pd.Timestamp.utcnow()
    with pytest.raises(_StopHereSentinel):
        demo.run_once("AUSTIN")
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

    def _fake_fetch(city, valid_time, horizon_minutes, *, lat, lon):
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
    prediction = demo.run_once("AUSTIN", "raw_forecast")
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
    def _raise_stale(city, valid_time, horizon_minutes, *, lat, lon):
        raise shadow.StaleOrMissingDataError(
            f"fetch_live_forecast_for_valid_time: retrieval failed for "
            f"city {city!r}: synthetic timeout"
        )

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", _raise_stale)

    prediction = demo.run_once("EL_PASO", "ml_wind_corrected")

    assert prediction.method == "static_rating_fallback"
    assert prediction.fallback_used is True
    assert "synthetic timeout" in prediction.fallback_reason
    assert prediction.model_version is None
    # EL_PASO's OWN static rating (1450.0, config.STATIC_RATINGS) -- each
    # city is an independent point; no other city's rating is involved.
    assert prediction.city == "EL_PASO"
    assert prediction.ampacity_amps == config.STATIC_RATINGS["EL_PASO"]
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

    def _fake_fetch(city, valid_time, horizon_minutes, *, lat, lon):
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
    prediction = demo.run_once("AUSTIN", "ml_wind_corrected")
    assert prediction.method == "raw_forecast"
    assert prediction.fallback_used is True
    assert prediction.fallback_reason is not None
    assert "no persisted" in prediction.fallback_reason
    assert "ml_wind_corrected" in prediction.fallback_reason
    assert "AUSTIN" in prediction.fallback_reason
    captured = capsys.readouterr()
    assert "no persisted" in captured.err


def test_run_once_logs_and_returns_the_same_prediction(monkeypatch, tmp_path):
    """`run_once` must log the prediction it returns, not a different one
    (e.g. logging before a later mutation of the value, or logging the
    wrong object)."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))

    def _fake_fetch(city, valid_time, horizon_minutes, *, lat, lon):
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
    prediction = demo.run_once("AUSTIN", "raw_forecast")

    import json
    path = __import__("os").path.join(str(tmp_path), "AUSTIN.jsonl")
    with open(path) as fh:
        logged = json.loads(fh.readline())
    assert logged["city"] == "AUSTIN"
    assert "corridor" not in logged
    assert logged["ampacity_amps"] == prediction.ampacity_amps
    assert logged["method"] == prediction.method


# ──────────────────────────────────────────────────────────────────────
# Plan 05-02: run_once_all_methods -- the five-candidate orchestration
# entry point, per city since 2026-10-12. Network-free throughout: the
# shared fetch itself is monkeypatched to a synthetic success/failure,
# never a real network call.
# ──────────────────────────────────────────────────────────────────────

def _fake_shared_inputs_factory(*, air_temp=30.0, wind_speed=5.0, wind_direction=90.0,
                                  solar=500.0, anchor_wind_speed=4.0, anchor_wind_direction=95.0,
                                  anchor_air_temp=29.0):
    def _fake_shared_inputs(city_arg, *, valid_time, decision_time, horizon_minutes):
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
        return shadow.SharedCityFetchResult(city_arg, frame.copy(), None, anchor.copy(), None)
    return _fake_shared_inputs


def _read_single_record(tmp_path, city):
    import json
    import os
    with open(os.path.join(str(tmp_path), f"{city}.jsonl")) as fh:
        return json.loads(fh.readline())


def test_run_once_all_methods_attempts_all_five_and_isolates_one_sabotaged_candidate(monkeypatch, tmp_path):
    """D-07: a REAL code-level exception inside one candidate's own
    computation must be caught by that candidate's own try/except and
    recorded as status='failed'; the other four candidates still compute
    and log for the same cycle."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path / "no_models"))
    city = "AUSTIN"
    monkeypatch.setattr(shadow, "fetch_shared_city_inputs", _fake_shared_inputs_factory())

    def _raise(self, city_arg, decision_time):
        raise RuntimeError("deliberate sabotage for the isolation test")

    monkeypatch.setattr(shadow.Persistence24hShadowMethod, "compute", _raise)
    results = demo.run_once_all_methods(city)

    assert set(results) == set(shadow.CANDIDATE_METHOD_NAMES)
    assert results["persistence_24h"].status == "failed"
    assert "deliberate sabotage" in (results["persistence_24h"].reason or "")
    for name in shadow.CANDIDATE_METHOD_NAMES:
        if name == "persistence_24h":
            continue
        assert results[name].status != "failed", (name, results[name])

    # The same cycle's log line must still carry all five candidates --
    # one candidate's failure must not have aborted the write.
    record = _read_single_record(tmp_path, city)
    assert record["schema_version"] == 3
    assert record["city"] == city
    assert "corridor" not in record
    assert set(record["candidates"]) == set(shadow.CANDIDATE_METHOD_NAMES)
    assert record["candidates"]["persistence_24h"]["status"] == "failed"


def _fake_truth_proxy_fetch_weather(location, start, end, provider="synoptic", **kwargs):
    """Plan 05-04: a complete, network-free 7-hour station window for
    whichever single CAMS id `fetch_live_truth_proxy_series` requests."""
    end_ts = pd.Timestamp(end)
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize("UTC")
    rows = []
    for h in range(config.FORECAST_ML_ROLLING_WINDOW_HOURS, -1, -1):
        rows.append({
            "datetime_utc": end_ts - pd.Timedelta(hours=h),
            "air_temp": 25.0, "wind_speed": 5.0, "wind_direction": 100.0,
            "solar_radiation": 400.0,
        })
    return pd.DataFrame(rows)


def _fit_synthetic_wind_model(city):
    import numpy as np
    import forecast_correction_models

    rng = np.random.default_rng(1)
    n = 80
    ts = pd.date_range("2024-01-01", periods=n, freq="6h", tz="UTC")
    frame = pd.DataFrame({
        "datetime_utc": ts, "city": city,
        "fcst_wind_speed": rng.uniform(1.0, 10.0, n), "fcst_wind_direction": rng.uniform(0.0, 360.0, n),
        "fcst_air_temp": rng.uniform(10.0, 35.0, n), "fcst_solar_radiation": rng.uniform(0.0, 800.0, n),
        "anchor_wind_speed": rng.uniform(1.0, 10.0, n), "anchor_wind_direction": rng.uniform(0.0, 360.0, n),
        "truth_wind_speed": rng.uniform(1.0, 10.0, n), "truth_wind_direction": rng.uniform(0.0, 360.0, n),
    })
    return forecast_correction_models.fit_wind_correction(
        frame, forecast_correction_models._make_wind_linear_regression, pooling="per_city",
    )


class _FakeEstimator:
    def predict(self, X):
        import numpy as np
        return np.array([1234.0])


def test_run_once_all_methods_ok_with_per_city_artifacts_and_a_complete_truth_proxy_window(monkeypatch, tmp_path):
    """Plan 05-04, per city: with this city's own artifacts present
    (stubbed here -- the real per-city refit has not been run) and a
    complete (mocked, network-free) truth-proxy window, wind and
    reference_ml_refit_24h reach status='ok', each carrying this city's own
    ampacity; the cooling candidate whose artifact is absent is
    `unavailable` with the named FileNotFoundError reason, never failed."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_truth_proxy_fetch_weather)
    city = "AUSTIN"
    monkeypatch.setattr(shadow, "fetch_shared_city_inputs", _fake_shared_inputs_factory())

    wind_model = _fit_synthetic_wind_model(city)

    def _load(city_arg, method_name):
        assert city_arg == city
        if method_name == "ml_wind_corrected":
            return wind_model
        if method_name == "reference_ml_refit_24h":
            return _FakeEstimator()
        raise FileNotFoundError(f"no persisted {method_name!r} model for city {city_arg!r}")

    monkeypatch.setattr(shadow, "load_correction_model", _load)
    monkeypatch.setattr(shadow, "model_version_for", lambda city_arg, method_name: f"{method_name}_{city_arg}@test")

    results = demo.run_once_all_methods(city)

    assert results["ml_wind_corrected"].status == "ok"
    assert results["ml_wind_corrected"].city == city
    assert results["ml_wind_corrected"].model_version == f"ml_wind_corrected_{city}@test"
    assert results["ml_wind_corrected"].input_provenance["anchor_provenance"]["anchor_source"] == "tceq"
    assert results["raw_forecast"].status == "ok"
    assert results["raw_forecast"].input_provenance is None
    assert results["reference_ml_refit_24h"].status == "ok"
    assert results["reference_ml_refit_24h"].ampacity_amps == 1234.0
    assert results["ml_cooling_corrected"].status == "unavailable"
    assert "ml_cooling_corrected" in results["ml_cooling_corrected"].reason
    for name in shadow.CANDIDATE_METHOD_NAMES:
        assert results[name].status != "failed", (name, results[name])
        assert "per_city_ampacity_amps" not in (results[name].input_provenance or {})
        assert "bottleneck_city" not in (results[name].input_provenance or {})


def test_run_once_all_methods_missing_per_city_artifacts_are_unavailable_never_a_crash(monkeypatch, tmp_path):
    """Until each city is refit, the three ML candidates report
    unavailable with a named reason (the FileNotFoundError path) while
    raw_forecast still records. A legacy corridor artifact in the models
    dir is not loaded."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path / "pred"))
    models = tmp_path / "models"
    models.mkdir()
    (models / "ml_wind_corrected_AUSTIN_CORPUS_CHRISTI.joblib").write_bytes(b"legacy")
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(models))
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_truth_proxy_fetch_weather)
    monkeypatch.setattr(shadow, "fetch_shared_city_inputs", _fake_shared_inputs_factory())

    results = demo.run_once_all_methods("AUSTIN")

    for name in ("ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h"):
        assert results[name].status == "unavailable", (name, results[name])
        assert f"{name}_AUSTIN.joblib" in results[name].reason
    assert results["raw_forecast"].status == "ok"


def test_run_once_all_methods_marks_anchored_candidates_unavailable_when_the_anchor_is_missing(monkeypatch, tmp_path):
    """D-04: a candidate whose required inputs are missing for this cycle
    (here, the anchor) is recorded unavailable, independent of every
    other candidate's own availability -- raw_forecast (needs no anchor)
    must still read ok."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path / "no_models"))

    def _fake_shared_inputs(city_arg, *, valid_time, decision_time, horizon_minutes):
        frame = pd.DataFrame([{
            "fcst_air_temp": 30.0, "fcst_wind_speed": 5.0, "fcst_wind_direction": 90.0,
            "fcst_solar_radiation": 500.0,
        }])
        frame.attrs["geometry"] = None
        return shadow.SharedCityFetchResult(city_arg, frame, None, None, "simulated anchor gap")

    monkeypatch.setattr(shadow, "fetch_shared_city_inputs", _fake_shared_inputs)

    results = demo.run_once_all_methods("AUSTIN")

    assert results["ml_wind_corrected"].status == "unavailable"
    assert "simulated anchor gap" in results["ml_wind_corrected"].reason
    assert results["ml_cooling_corrected"].status == "unavailable"
    assert results["raw_forecast"].status == "ok"


def test_run_once_all_methods_marks_frame_candidates_unavailable_when_the_forecast_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path / "no_models"))

    def _fake_shared_inputs(city_arg, *, valid_time, decision_time, horizon_minutes):
        return shadow.SharedCityFetchResult(city_arg, None, "simulated forecast gap", None, "simulated anchor gap")

    monkeypatch.setattr(shadow, "fetch_shared_city_inputs", _fake_shared_inputs)
    results = demo.run_once_all_methods("EL_PASO")

    for name in shadow.FRAME_BASED_METHOD_NAMES:
        assert results[name].status == "unavailable"
        assert "simulated forecast gap" in results[name].reason
        assert results[name].bundle["status"] == "unavailable"


def test_run_once_all_methods_uses_the_citys_own_bearing_and_never_reduces_across_cities(monkeypatch, tmp_path):
    """Each city's raw_forecast ampacity is computed from that city's own
    frame via `city_point(city)`: identical weather in two cities with
    DIFFERENT bearings (AUSTIN 173.15 vs MIDLAND 267.54) yields different
    values, and each equals the direct per-city computation."""
    import numpy as np
    import city_point
    import thermal_model

    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path / "no_models"))
    monkeypatch.setattr(shadow, "fetch_shared_city_inputs", _fake_shared_inputs_factory())

    got = {}
    for city in ("AUSTIN", "MIDLAND"):
        got[city] = demo.run_once_all_methods(city)["raw_forecast"].ampacity_amps
        point = city_point.city_point(city)
        perp = thermal_model.perpendicular_wind(np.array([5.0]), np.array([90.0]), point.bearing_deg)
        expected = thermal_model.ieee738_ampacity(np.array([30.0]), perp, np.array([500.0]), point.conductor)
        assert got[city] == pytest.approx(float(np.asarray(expected)[0]))
    assert got["AUSTIN"] != pytest.approx(got["MIDLAND"])


# ──────────────────────────────────────────────────────────────────────
# 2026-10-08 ("bundle-level ampacity"), per city since 2026-10-12:
# run_once_all_methods wires real bundle computation into the live
# orchestration loop, end to end.
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("city,count", [("MIDLAND", 2), ("EL_PASO", 1)])
def test_run_once_all_methods_bundle_uses_the_citys_own_subconductor_count(monkeypatch, tmp_path, city, count):
    """MIDLAND (2 subconductors) and EL_PASO (1) share a bearing, so with
    identical weather their per-conductor values tie; only the bundle
    differs, by each city's own count -- and it persists through the real
    logging path."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path / "no_models"))
    monkeypatch.setattr(shadow, "fetch_shared_city_inputs", _fake_shared_inputs_factory())

    results = demo.run_once_all_methods(city)

    raw = results["raw_forecast"]
    assert raw.status == "ok"
    bundle = raw.bundle
    assert bundle["status"] == "ok"
    assert bundle["subconductors_per_phase"] == count == config.SUBCONDUCTORS_PER_PHASE[city]
    assert bundle["bundle_ampacity_amps"] == count * raw.ampacity_amps
    assert bundle["config_version"] == config.BUNDLE_CONFIG_VERSION

    logged = _read_single_record(tmp_path, city)["candidates"]["raw_forecast"]["bundle"]
    assert logged["bundle_ampacity_amps"] == count * raw.ampacity_amps


def test_run_once_all_methods_bundle_unavailable_mirrors_the_candidates_own_unavailable_reason(monkeypatch, tmp_path):
    """A candidate that is itself unavailable this cycle (here: a missing
    anchor for ml_wind_corrected) must report bundle unavailable with a
    reason tied to that same cause -- never silently omitted, never a
    generic unrelated message."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(shadow, "SHADOW_MODEL_DIR", str(tmp_path / "no_models"))

    def _fake_shared_missing_anchor(city_arg, *, valid_time, decision_time, horizon_minutes):
        frame = pd.DataFrame([{
            "fcst_air_temp": 30.0, "fcst_wind_speed": 5.0,
            "fcst_wind_direction": 90.0, "fcst_solar_radiation": 500.0,
        }])
        frame.attrs["geometry"] = None
        return shadow.SharedCityFetchResult(city_arg, frame, None, None, "anchor fetch failed (test)")

    monkeypatch.setattr(shadow, "fetch_shared_city_inputs", _fake_shared_missing_anchor)

    results = demo.run_once_all_methods("AUSTIN")

    wind = results["ml_wind_corrected"]
    assert wind.status == "unavailable"
    assert wind.bundle["status"] == "unavailable"
    assert wind.bundle["reason"] == wind.reason
    assert results["raw_forecast"].status == "ok"
    assert results["raw_forecast"].bundle["status"] == "ok"
