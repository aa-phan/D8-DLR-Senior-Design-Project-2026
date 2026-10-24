"""
Tests for backend/city_pipeline.py::run_city_pipeline -- the per-city
orchestrator that reads the archived history, drops fallback rows, forecasts,
builds the anomaly detector and rates the city.

History comes from a tmp_path archive, weather from an injected fetcher, and
what the forecast and the detector receive is captured by spies. The tests
assert on what each stage is given and what the `pipeline` key reports, never
on a rating value. Follows backend/tests/city_rating_test.py's conventions
(module-level imports, plain asserts, no test classes, no network).
"""

import logging

import pandas as pd
import pytest
import requests

import ampacity_forecast
import anomaly_detector
import city_pipeline
import city_point
import config
import data_cleaning
import historical_archive

_CITY = "AUSTIN"
_DAY = "2025-06-01"
_START = f"{_DAY}T17:00:00Z"
_END = f"{_DAY}T18:00:00Z"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """
    Replace `requests.get` for every test. The composer and `rate_city` catch
    every provider exception, so raising alone could be swallowed; the teardown
    assert on the recorded attempts cannot be.
    """
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    yield
    assert attempts == []


@pytest.fixture(autouse=True)
def _offline_env(tmp_path, monkeypatch):
    # Another test module loads `.env` into the process at import time.
    for name in ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "HISTORICAL_ARCHIVE_PATH", str(tmp_path / "default_archive.csv"))
    # Trained models are git-ignored, so a test must not depend on whether this
    # checkout has them.
    monkeypatch.setattr(anomaly_detector, "_load_city_model_or_none", lambda city: None)


def _station_at(city):
    lat, lon = config.CITY_COORDINATES[city]
    return pd.DataFrame([{"stid": "T1", "name": "t", "lat": lat, "lon": lon}])


def _good_fetch(stids, start, end, provider="synoptic", **_):
    # Wind blows across AUSTIN's line, so the projected speed equals the measured
    # one; 25 C / 6.5 m/s / 500 W/m2 stays inside the gates, so G6 is evaluated.
    across = (city_point.city_point(_CITY).bearing_deg + 90) % 360
    return pd.DataFrame([{"stid": stids[0], "air_temp": 25.0, "wind_speed": 6.5,
                          "wind_direction": across, "solar_radiation": 500.0}])


def _archive_row(city, hour, dlr_amps=1200.0, fallback=False):
    return {
        "datetime_utc": f"{_DAY}T{hour:02d}:00:00Z",
        "city": city,
        "air_temp": 25.0 + 0.1 * hour,
        "wind_speed": 5.0 + 0.05 * hour,
        "solar_radiation": 500.0 + hour,
        "dlr_amps": dlr_amps,
        "static_rating": 1825.0,
        "status": "fallback" if fallback else "ok",
        "fallback": fallback,
        "schema_version": historical_archive.ARCHIVE_SCHEMA_VERSION,
    }


def _write_archive(path, rows):
    pd.DataFrame(rows, columns=historical_archive.ARCHIVE_COLUMNS).to_csv(path, index=False)


class _SpyDetector:
    signal = "spy"
    model_source = None

    def check(self, raw_data, rating):
        return False, ""


def _spy_detector(monkeypatch, detector=None):
    """Stand in for AnomalyDetector; record what `for_city` was given."""
    seen = {}
    built = detector or _SpyDetector()

    class _StandIn:
        @staticmethod
        def for_city(city, forecast=None, history=None, **kw):
            seen["city"] = city
            seen["forecast"] = forecast
            seen["history"] = history
            return built

    monkeypatch.setattr(city_pipeline, "AnomalyDetector", _StandIn)
    seen["detector"] = built
    return seen


def _spy_forecast(monkeypatch, result=None, raises=None):
    """Replace forecast_ampacity; record the history and method it was given."""
    seen = {}

    def fake(history, method="naive", **kw):
        seen["history"] = history
        seen["method"] = method
        if raises is not None:
            raise raises
        return result

    monkeypatch.setattr(ampacity_forecast, "forecast_ampacity", fake)
    return seen


def _run(tmp_path, **kw):
    args = dict(archive=False, archive_path=str(tmp_path / "archive.csv"),
                fetch_weather=_good_fetch)
    args.update(kw)
    return city_pipeline.run_city_pipeline(_CITY, _START, _END, _station_at(_CITY), **args)


# ──────────────────────────────────────────────────────────────────────────────
# History filtering, city scoping, forecast failure, cold start
# ──────────────────────────────────────────────────────────────────────────────

def test_fallback_rows_are_left_out_of_the_history_the_forecast_and_detector_see(
        tmp_path, monkeypatch):
    fallback_hours = {3, 7, 11, 15}
    rows = [
        _archive_row(_CITY, h, dlr_amps=1825.0, fallback=True) if h in fallback_hours
        else _archive_row(_CITY, h, dlr_amps=1200.0 + h)
        for h in range(18)
    ]
    _write_archive(tmp_path / "archive.csv", rows)
    detector_seen = _spy_detector(monkeypatch)
    forecast_seen = _spy_forecast(monkeypatch)

    result = _run(tmp_path)

    history = forecast_seen["history"]
    assert len(history) == 14
    assert not history["fallback"].astype(str).str.lower().eq("true").any()
    assert 1825.0 not in set(history["dlr_amps"])
    assert detector_seen["history"] is forecast_seen["history"]
    assert result["pipeline"]["history_rows"] == 18
    assert result["pipeline"]["usable_history_rows"] == 14


def test_fallback_flag_is_matched_as_case_insensitive_text(tmp_path, monkeypatch):
    flags = ["TRUE", "false", True, "True", False]
    frame = pd.DataFrame({
        "datetime_utc": [f"{_DAY}T{h:02d}:00:00Z" for h in range(5)],
        "city": [_CITY] * 5,
        "dlr_amps": [1300.0, 1301.0, 1302.0, 1303.0, 1304.0],
        "fallback": pd.Series(flags, dtype=object),
    })
    monkeypatch.setattr(city_pipeline.historical_archive, "read_history", lambda **kw: frame)
    _spy_detector(monkeypatch)
    forecast_seen = _spy_forecast(monkeypatch)

    result = _run(tmp_path)

    history = forecast_seen["history"]
    assert list(history["dlr_amps"]) == [1301.0, 1304.0]
    assert result["pipeline"]["history_rows"] == 5
    assert result["pipeline"]["usable_history_rows"] == 2


def test_history_is_read_for_this_city_only(tmp_path, monkeypatch):
    rows = [_archive_row(_CITY, h) for h in range(3)]
    rows += [_archive_row("EL_PASO", h) for h in range(3, 5)]
    _write_archive(tmp_path / "archive.csv", rows)
    _spy_detector(monkeypatch)
    forecast_seen = _spy_forecast(monkeypatch)

    result = _run(tmp_path)

    history = forecast_seen["history"]
    assert len(history) == 3
    assert set(history["city"]) == {_CITY}
    assert result["pipeline"]["history_rows"] == 3


def test_forecast_exception_leaves_no_forecast_and_the_city_still_rates(
        tmp_path, monkeypatch, caplog):
    detector_seen = _spy_detector(monkeypatch)
    _spy_forecast(monkeypatch, raises=RuntimeError("no trained artifact"))

    with caplog.at_level(logging.WARNING, logger="city_pipeline"):
        result = _run(tmp_path, forecast_method="ml")

    pipeline = result["pipeline"]
    assert pipeline["forecast"] is None
    assert pipeline["forecast_used_by_g6"] is False
    assert pipeline["forecast_method"] == "ml"
    assert detector_seen["forecast"] is None
    assert result["exhausted"] is False
    assert "rating" in result
    # OD-3: the run output must say the ML forecast failed, and why.
    assert pipeline["forecast_status"] == "failed"
    assert pipeline["forecast_error"] == "forecast failed: no trained artifact"
    warnings = [r for r in caplog.records
                if r.name == "city_pipeline" and r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "method='ml'" in message
    assert "AUSTIN" in message
    assert "continuing without a forecast" in message


def test_cold_start_with_no_archive_rates_without_a_forecast(tmp_path):
    # Empty edge: no archive file, real forecast, real detector (no model).
    assert not (tmp_path / "archive.csv").exists()

    result = _run(tmp_path)

    pipeline = result["pipeline"]
    assert pipeline["history_rows"] == 0
    assert pipeline["usable_history_rows"] == 0
    assert pipeline["forecast"] is None
    assert pipeline["forecast_used_by_g6"] is False
    assert pipeline["detector_signal"] == "cold_start"
    assert pipeline["detector_model"] is None
    assert pipeline["forecast_status"] == "cold_start"
    assert pipeline["forecast_error"] is None
    assert result["exhausted"] is False


# ──────────────────────────────────────────────────────────────────────────────
# Degenerate band, the pipeline key, and rate_city wiring
# ──────────────────────────────────────────────────────────────────────────────

def _forecast_result(lower, upper):
    return ampacity_forecast.ForecastResult(
        horizon_min=60.0, amps=1200.0, ci_lower_amps=lower, ci_upper_amps=upper,
        n_observations=14, method="naive")


@pytest.mark.parametrize(
    "lower, upper",
    [(1200.0, 1200.0), (1210.0, 1190.0)],
    ids=["zero_width", "inverted"],
)
def test_zero_width_band_is_reported_but_not_given_to_the_detector(
        tmp_path, monkeypatch, caplog, lower, upper):
    # Adjacency edge: a width of exactly zero already counts as degenerate.
    detector_seen = _spy_detector(monkeypatch)
    _spy_forecast(monkeypatch, result=_forecast_result(lower, upper))

    with caplog.at_level(logging.INFO, logger="city_pipeline"):
        result = _run(tmp_path)

    pipeline = result["pipeline"]
    assert detector_seen["forecast"] is None
    assert pipeline["forecast_used_by_g6"] is False
    assert pipeline["forecast"] == {
        "amps": 1200.0, "ci_lower_amps": lower, "ci_upper_amps": upper,
        "n_observations": 14, "horizon_min": 60.0,
    }
    assert any("forecast band has zero width" in r.getMessage() for r in caplog.records)


def test_positive_width_band_is_given_to_the_detector(tmp_path, monkeypatch):
    detector_seen = _spy_detector(monkeypatch)
    forecast = _forecast_result(1150.0, 1250.0)
    _spy_forecast(monkeypatch, result=forecast)

    result = _run(tmp_path)

    assert detector_seen["forecast"] is forecast
    assert result["pipeline"]["forecast_used_by_g6"] is True


def test_pipeline_key_reports_history_forecast_and_detector(tmp_path, monkeypatch):
    _write_archive(tmp_path / "archive.csv", [_archive_row(_CITY, h) for h in range(3)])
    spy = _SpyDetector()
    spy.signal = "forecast_residual"
    spy.model_source = "spy-model"
    _spy_detector(monkeypatch, detector=spy)
    forecast_seen = _spy_forecast(monkeypatch, result=_forecast_result(1150.0, 1250.0))

    result = _run(tmp_path, forecast_method="ewm")

    pipeline = result["pipeline"]
    assert set(pipeline) == {
        "history_rows", "usable_history_rows", "forecast_method", "forecast_status",
        "forecast_used_by_g6", "forecast", "detector_signal", "detector_model",
        "cleaning_error", "forecast_error",
    }
    assert pipeline["cleaning_error"] is None
    assert pipeline["forecast_error"] is None
    assert set(pipeline["forecast"]) == {
        "amps", "ci_lower_amps", "ci_upper_amps", "n_observations", "horizon_min",
    }
    assert isinstance(pipeline["forecast"]["n_observations"], int)
    assert isinstance(pipeline["forecast"]["amps"], float)
    assert pipeline["forecast_method"] == "ewm"
    assert forecast_seen["method"] == "ewm"
    assert pipeline["detector_signal"] == "forecast_residual"
    assert pipeline["detector_model"] == "spy-model"
    assert pipeline["history_rows"] == 3


def test_rate_city_gets_the_detector_and_the_callers_arguments(tmp_path, monkeypatch):
    detector_seen = _spy_detector(monkeypatch)
    calls = []

    def fake_rate_city(*args, **kwargs):
        calls.append((args, kwargs))
        return {"city": _CITY, "rating": 1.0}

    monkeypatch.setattr(city_pipeline.city_rating, "rate_city", fake_rate_city)
    stations = _station_at(_CITY)
    sentinel_fetch = object()
    archive_path = str(tmp_path / "archive.csv")

    result = city_pipeline.run_city_pipeline(
        _CITY, _START, _END, stations, provider="open_meteo", archive_path=archive_path,
        archive=True, fetch_weather=sentinel_fetch)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:3] == (_CITY, _START, _END)
    assert args[3] is stations
    assert kwargs["anomaly_detector"] is detector_seen["detector"]
    assert kwargs["fetch_weather"] is sentinel_fetch
    assert kwargs["archive"] is True
    assert kwargs["archive_path"] == archive_path
    assert kwargs["provider"] == "open_meteo"
    assert {k: v for k, v in result.items() if k != "pipeline"} == {"city": _CITY, "rating": 1.0}
    assert "pipeline" in result


# ──────────────────────────────────────────────────────────────────────────────
# History reader seam (DB-02) and forecast status (OD-3)
# ──────────────────────────────────────────────────────────────────────────────

def test_history_reader_replaces_the_archive_read(tmp_path, monkeypatch):
    frame = pd.DataFrame(
        [_archive_row(_CITY, h) for h in range(4)], columns=historical_archive.ARCHIVE_COLUMNS)
    calls = []

    def reader(city, end):
        calls.append((city, end))
        return frame

    def archive_read_must_not_run(**kw):
        raise AssertionError("historical_archive.read_history must not be called")

    monkeypatch.setattr(historical_archive, "read_history", archive_read_must_not_run)
    cleaned_seen = {}
    real_clean = data_cleaning.clean_history

    def spy_clean(history, as_of=None, **kw):
        cleaned_seen["history"] = history
        cleaned_seen["as_of"] = as_of
        return real_clean(history, as_of=as_of, **kw)

    monkeypatch.setattr(data_cleaning, "clean_history", spy_clean)
    _spy_detector(monkeypatch)
    _spy_forecast(monkeypatch)

    result = _run(tmp_path, history_reader=reader)

    assert calls == [(_CITY, _END)]
    assert cleaned_seen["history"] is frame
    assert cleaned_seen["as_of"] == _END
    assert result["pipeline"]["history_rows"] == len(frame) == 4


def test_without_a_history_reader_the_csv_archive_is_read(tmp_path, monkeypatch):
    archive_path = str(tmp_path / "archive.csv")
    calls = []
    real_read = historical_archive.read_history

    def spy_read(**kw):
        calls.append(kw)
        return real_read(**kw)

    monkeypatch.setattr(historical_archive, "read_history", spy_read)
    _spy_detector(monkeypatch)
    _spy_forecast(monkeypatch)

    _run(tmp_path)

    assert calls == [{"path": archive_path, "city": _CITY}]


@pytest.mark.parametrize(
    "spy_kwargs, expected",
    [
        ({"result": _forecast_result(1150.0, 1250.0)}, "ok"),
        ({"result": None}, "cold_start"),
        ({"raises": RuntimeError("no trained artifact")}, "failed"),
    ],
    ids=["band", "none", "raised"],
)
def test_forecast_status_reports_ok_cold_start_and_failed(
        tmp_path, monkeypatch, spy_kwargs, expected):
    _spy_detector(monkeypatch)
    _spy_forecast(monkeypatch, **spy_kwargs)

    result = _run(tmp_path)

    assert result["pipeline"]["forecast_status"] == expected
    assert "rating" in result
    assert result["exhausted"] is False


def test_a_forecast_failure_reports_its_reason(tmp_path, monkeypatch):
    # IN-07: a failed forecast needs a stored reason, as a failed cleaning has one.
    _spy_detector(monkeypatch)
    _spy_forecast(monkeypatch, raises=RuntimeError("no trained artifact"))

    pipeline = _run(tmp_path)["pipeline"]

    assert pipeline["forecast_status"] == "failed"
    assert pipeline["forecast_error"] == "forecast failed: no trained artifact"
    assert pipeline["cleaning_error"] is None


def test_a_forecast_withheld_by_the_gap_guard_is_still_status_ok(tmp_path, monkeypatch):
    # The status describes the forecast call; forecast_used_by_g6 says whether G6 got it.
    _write_archive(tmp_path / "archive.csv", [_archive_row(_CITY, h) for h in range(3)])
    detector_seen = _spy_detector(monkeypatch)
    _spy_forecast(monkeypatch, result=_forecast_result(1150.0, 1250.0))
    monkeypatch.setattr(data_cleaning, "forecast_gap_reason", lambda report, method: "stale newest row")

    result = _run(tmp_path)

    assert detector_seen["forecast"] is None
    assert result["pipeline"]["forecast_used_by_g6"] is False
    assert result["pipeline"]["forecast_status"] == "ok"


def _raising_clean(monkeypatch, text="boom"):
    def raiser(history, as_of=None, **kw):
        raise RuntimeError(text)

    monkeypatch.setattr(data_cleaning, "clean_history", raiser)


def test_cleaning_failure_on_existing_history_reports_forecast_failed(
        tmp_path, monkeypatch, caplog):
    # WR-02: a cleaning bug that throws away real history is not a cold start.
    _write_archive(tmp_path / "archive.csv", [_archive_row(_CITY, h) for h in range(3)])
    detector_seen = _spy_detector(monkeypatch)
    forecast_seen = _spy_forecast(monkeypatch)
    _raising_clean(monkeypatch, "boom")

    with caplog.at_level(logging.WARNING, logger="city_pipeline"):
        result = _run(tmp_path)

    pipeline = result["pipeline"]
    assert pipeline["history_rows"] == 3
    assert pipeline["usable_history_rows"] == 0
    assert pipeline["forecast_status"] == "failed"
    assert pipeline["cleaning_error"].startswith("data cleaning failed:")
    assert "boom" in pipeline["cleaning_error"]
    assert pipeline["detector_signal"] is not None
    # unvetted history still never reaches the forecast or the detector (Phase 2 rule)
    assert len(forecast_seen["history"]) == 0
    assert len(detector_seen["history"]) == 0
    assert "rating" in result
    warnings = [r.getMessage() for r in caplog.records
                if r.name == "city_pipeline" and r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert _CITY in warnings[0] and "cold start" in warnings[0]


def test_cleaning_failure_on_empty_history_stays_cold_start(tmp_path, monkeypatch):
    _spy_detector(monkeypatch)
    _spy_forecast(monkeypatch)
    _raising_clean(monkeypatch, "boom")

    result = _run(tmp_path)

    pipeline = result["pipeline"]
    assert pipeline["history_rows"] == 0
    assert pipeline["forecast_status"] == "cold_start"
    assert pipeline["cleaning_error"].startswith("data cleaning failed:")
    assert "boom" in pipeline["cleaning_error"]


def test_forecast_error_is_truncated_to_300_characters(tmp_path, monkeypatch):
    # The text reaches the --output JSON and the run log, so its size is bounded.
    _spy_detector(monkeypatch)
    _spy_forecast(monkeypatch, raises=RuntimeError("x" * 1000))

    pipeline = _run(tmp_path)["pipeline"]

    assert pipeline["forecast_status"] == "failed"
    assert len(pipeline["forecast_error"]) == 300
    assert pipeline["forecast_error"].startswith("forecast failed: xxxx")


def test_forecast_error_of_exactly_300_characters_is_kept_whole(tmp_path, monkeypatch):
    # Adjacency edge of the cap: 300 passes through, 301 is cut.
    _spy_detector(monkeypatch)
    prefix = "forecast failed: "
    _spy_forecast(monkeypatch, raises=RuntimeError("y" * (300 - len(prefix))))

    error = _run(tmp_path)["pipeline"]["forecast_error"]

    assert len(error) == 300
    assert error.endswith("y")
