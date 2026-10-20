"""
Tests for the cleaning step inside the per-city pipeline, offline: the
orchestrator -> city pipeline -> data_cleaning -> rate_city -> archive append
path (production-pipeline Phase 2, CLEAN-03 and CLEAN-04).

Every archive lives under `tmp_path`, weather comes from an injected stub
fetcher and nothing reaches the network. Follows
backend/tests/city_rating_test.py's conventions (module-level imports, plain
asserts, no test classes, no network).
"""

import logging
import os

import pandas as pd
import pytest
import requests

import ampacity_forecast
import anomaly_detector
import city_pipeline
import city_point
import config
import data_cleaning
import dlr_orchestrator
import historical_archive

_DAY = "2025-06-01"
_CITIES = ("AUSTIN", "EL_PASO")


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


def _stations():
    rows = []
    for city in _CITIES:
        lat, lon = config.CITY_COORDINATES[city]
        rows.append({"stid": f"T_{city}", "name": city, "lat": lat, "lon": lon})
    return pd.DataFrame(rows)


class _StubFetcher:
    """
    Stands in for the composed fetcher: `provenance` and `errors` are what
    `run_dlr_pipeline` reads from it, `calls` records what was asked.
    """

    def __init__(self):
        self.provenance = []
        self.errors = {}
        self.calls = []

    def __call__(self, stids, start, end, provider="synoptic", **_):
        self.calls.append((stids[0], end))
        city = stids[0].split("T_", 1)[1]
        # Wind blows across the line, so the projected speed equals the measured one.
        across = (city_point.city_point(city).bearing_deg + 90) % 360
        return pd.DataFrame([{"stid": stids[0], "air_temp": 25.0, "wind_speed": 6.5,
                              "wind_direction": across, "solar_radiation": 500.0}])


def _archive_row(city, datetime_utc, dlr_amps=1200.0, fallback=False,
                 air_temp=25.0, wind_speed=5.0, solar_radiation=500.0):
    return {
        "datetime_utc": datetime_utc,
        "city": city,
        "air_temp": air_temp,
        "wind_speed": wind_speed,
        "solar_radiation": solar_radiation,
        "dlr_amps": dlr_amps,
        "static_rating": 1825.0,
        "status": "fallback" if fallback else "ok",
        "fallback": fallback,
        "schema_version": historical_archive.ARCHIVE_SCHEMA_VERSION,
    }


def _write_archive(path, rows):
    pd.DataFrame(rows, columns=historical_archive.ARCHIVE_COLUMNS).to_csv(path, index=False)


def _forecast_spy(monkeypatch, result=None):
    """
    Replace forecast_ampacity; collect a copy of every history it is given and
    return `result` (None: no forecast).
    """
    seen = []

    def fake(history, method="naive", **kw):
        seen.append(history.copy())
        return result

    monkeypatch.setattr(ampacity_forecast, "forecast_ampacity", fake)
    return seen


# ──────────────────────────────────────────────────────────────────────────────
# Tracer: orchestrator -> city_pipeline -> clean_history -> rate_city -> append
# ──────────────────────────────────────────────────────────────────────────────

def test_rerunning_one_window_keeps_one_row_per_city_and_the_forecast_sees_cleaned_history(
        tmp_path, monkeypatch):
    archive = tmp_path / "archive.csv"
    _write_archive(archive, [
        _archive_row("AUSTIN", f"{_DAY}T10:00:00Z", dlr_amps=1200.0),
        # Same instant as the row above, second spelling, written second.
        _archive_row("AUSTIN", f"{_DAY}T10:00:00+00:00", dlr_amps=1300.0),
        _archive_row("AUSTIN", f"{_DAY}T11:00:00Z", dlr_amps=1825.0, fallback=True),
        _archive_row("EL_PASO", f"{_DAY}T10:00:00Z", dlr_amps=1100.0),
    ])
    forecast_seen = _forecast_spy(monkeypatch)
    run_args = dict(
        cities=list(_CITIES), end=f"{_DAY}T12:00:00Z", window_hours=1.0,
        provider="composed", forecast_method="naive", archive=True,
        archive_path=str(archive), stations=_stations(),
    )

    first = dlr_orchestrator.run_dlr_pipeline(fetcher=_StubFetcher(), **run_args)

    assert first["errors"] == {}
    assert [r["archived"] for r in first["summary"]] == [True, True]
    austin, el_paso = (r["pipeline"] for r in first["results"])
    assert austin["history_rows"] == 3
    assert austin["usable_history_rows"] == 1
    assert el_paso["history_rows"] == 1
    assert el_paso["usable_history_rows"] == 1
    austin_history = forecast_seen[0]
    assert len(austin_history) == 1
    assert austin_history["dlr_amps"].iloc[0] == 1200.0
    assert austin_history["datetime_utc"].iloc[0] == f"{_DAY}T10:00:00Z"
    assert austin_history["clean_flags"].iloc[0] == ""

    # The 12:00 row the first run archived is not asserted on: plan 02-03's
    # gap rule will flag it.
    marked = data_cleaning.clean_history(
        historical_archive.read_history(path=str(archive), city="AUSTIN")).frame
    flags = dict(zip(marked["dlr_amps"], marked["clean_flags"]))
    assert flags[1300.0] == "duplicate"
    assert flags[1825.0] == "fallback"
    assert flags[1200.0] == ""

    second = dlr_orchestrator.run_dlr_pipeline(fetcher=_StubFetcher(), **run_args)

    assert second["errors"] == {}
    assert [r["archived"] for r in second["summary"]] == [False, False]
    rows = historical_archive.read_history(path=str(archive))
    assert (rows["city"] == "AUSTIN").sum() == 4
    assert (rows["city"] == "EL_PASO").sum() == 2
    austin_rows = rows[rows["city"] == "AUSTIN"]
    twelve = pd.Timestamp(f"{_DAY}T12:00:00Z")
    parsed = pd.to_datetime(austin_rows["datetime_utc"], utc=True, format="ISO8601")
    assert (parsed == twelve).sum() == 1
    assert not os.path.exists(config.HISTORICAL_ARCHIVE_PATH)


# ──────────────────────────────────────────────────────────────────────────────
# Cleaning failure degrades to cold start; cleaning is read-only
# ──────────────────────────────────────────────────────────────────────────────

def test_cleaning_failure_rates_the_city_with_no_history(tmp_path, monkeypatch, caplog):
    archive = tmp_path / "archive.csv"
    _write_archive(archive, [
        _archive_row("AUSTIN", f"{_DAY}T{h:02d}:00:00Z", dlr_amps=1200.0 + h)
        for h in (7, 8, 9)
    ])

    def raiser(history, as_of=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(data_cleaning, "clean_history", raiser)

    with caplog.at_level(logging.WARNING, logger="city_pipeline"):
        result = city_pipeline.run_city_pipeline(
            "AUSTIN", f"{_DAY}T09:00:00Z", f"{_DAY}T10:00:00Z", _stations(),
            provider="synoptic", archive=False, archive_path=str(archive),
            fetch_weather=_StubFetcher())

    pipeline = result["pipeline"]
    assert pipeline["history_rows"] == 3
    assert pipeline["usable_history_rows"] == 0
    assert pipeline["forecast"] is None
    assert pipeline["forecast_used_by_g6"] is False
    assert pipeline["detector_signal"] == "cold_start"
    assert "rating" in result
    warnings = [r for r in caplog.records
                if r.name == "city_pipeline" and r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "AUSTIN" in message
    assert "cold start" in message


def test_a_pipeline_run_never_rewrites_the_archive(tmp_path):
    archive = tmp_path / "archive.csv"
    _write_archive(archive, [
        _archive_row("AUSTIN", f"{_DAY}T07:00:00Z", dlr_amps=1201.0),
        _archive_row("AUSTIN", f"{_DAY}T07:00:00+00:00", dlr_amps=1202.0),    # duplicate
        _archive_row("AUSTIN", f"{_DAY}T08:00:00Z", dlr_amps=1825.0, fallback=True),
        _archive_row("AUSTIN", "garbage", dlr_amps=1203.0),                  # bad timestamp
        _archive_row("AUSTIN", f"{_DAY}T09:00:00Z", dlr_amps=1204.0),
    ])
    before = archive.read_bytes()

    result = city_pipeline.run_city_pipeline(
        "AUSTIN", f"{_DAY}T09:00:00Z", f"{_DAY}T10:00:00Z", _stations(),
        provider="synoptic", archive=False, archive_path=str(archive),
        fetch_weather=_StubFetcher())

    assert "rating" in result
    assert result["pipeline"]["history_rows"] == 5
    assert result["pipeline"]["usable_history_rows"] == 2
    assert archive.read_bytes() == before


# ──────────────────────────────────────────────────────────────────────────────
# Forecast use across gaps (CLEAN-02, SC2): a forecast built from history with
# too large a gap is reported but does not gate G6
# ──────────────────────────────────────────────────────────────────────────────

def _band(method="naive", lower=1150.0, upper=1250.0):
    return ampacity_forecast.ForecastResult(60.0, 1200.0, lower, upper, 14, method)


class _Detector:
    signal = "forecast"
    model_source = "stand-in"

    def check(self, raw_data, rating):
        return False, ""


def _detector_spy(monkeypatch):
    """Stand in for AnomalyDetector; record what `for_city` was given."""
    seen = {}

    class _StandIn:
        @staticmethod
        def for_city(city, forecast=None, history=None, **kw):
            seen["forecast"] = forecast
            seen["history"] = history
            return _Detector()

    monkeypatch.setattr(city_pipeline, "AnomalyDetector", _StandIn)
    return seen


def _hourly_archive(path, hours, city="AUSTIN"):
    """One row per listed hour on _DAY, with values that vary so no rule flags them."""
    _write_archive(path, [
        _archive_row(
            city, f"{_DAY}T{h:02d}:00:00Z", dlr_amps=1200.0 + h,
            air_temp=25.0 + 0.1 * h, wind_speed=5.0 + 0.05 * h,
            solar_radiation=500.0 + h)
        for h in hours
    ])


def _run_at_ten(archive, method="naive"):
    return city_pipeline.run_city_pipeline(
        "AUSTIN", f"{_DAY}T09:00:00Z", f"{_DAY}T10:00:00Z", _stations(),
        provider="synoptic", archive=False, archive_path=str(archive),
        fetch_weather=_StubFetcher(), forecast_method=method)


def _report(rows_usable=5, trailing_gap_slots=0, contiguous_tail_rows=5):
    return {"rows_usable": rows_usable, "trailing_gap_slots": trailing_gap_slots,
            "contiguous_tail_rows": contiguous_tail_rows}


def _gap_notes(caplog):
    return [r.getMessage() for r in caplog.records
            if r.name == "city_pipeline" and "forecast not used for G6" in r.getMessage()]


def test_gap_reason_tolerates_one_skipped_cycle_before_the_run():
    assert data_cleaning.MAX_TRAILING_GAP_SLOTS == 1
    for slots in (0, 1, None):
        assert data_cleaning.forecast_gap_reason(_report(trailing_gap_slots=slots), "naive") is None
    reason = data_cleaning.forecast_gap_reason(_report(trailing_gap_slots=2), "naive")
    assert "2 missing hourly slot" in reason


def test_gap_reason_ignores_an_empty_history():
    report = _report(rows_usable=0, trailing_gap_slots=9, contiguous_tail_rows=0)
    assert data_cleaning.forecast_gap_reason(report, "naive") is None
    assert data_cleaning.forecast_gap_reason(report, "ml") is None


def test_gap_reason_requires_an_unbroken_lookback_only_for_ml():
    assert data_cleaning.forecast_gap_reason(_report(contiguous_tail_rows=7), "ml") is None
    reason = data_cleaning.forecast_gap_reason(_report(contiguous_tail_rows=6), "ml")
    assert "ml" in reason
    assert "6" in reason
    for method in ("naive", "ewm"):
        assert data_cleaning.forecast_gap_reason(_report(contiguous_tail_rows=1), method) is None


def test_ml_lookback_follows_the_feature_definition():
    expected = max(max(config.FORECAST_ML_LAG_HOURS), config.FORECAST_ML_ROLLING_WINDOW_HOURS) + 1
    assert data_cleaning.ML_LOOKBACK_ROWS == expected == 7


def test_one_skipped_cycle_inside_the_history_keeps_the_forecast_for_g6(tmp_path, monkeypatch):
    archive = tmp_path / "archive.csv"
    _hourly_archive(archive, [h for h in range(10) if h != 5])
    band = _band()
    forecast_seen = _forecast_spy(monkeypatch, result=band)
    detector_seen = _detector_spy(monkeypatch)

    result = _run_at_ten(archive)

    assert result["pipeline"]["forecast_used_by_g6"] is True
    assert detector_seen["forecast"] is band
    history = forecast_seen[0]
    assert len(history) == 9
    flags = dict(zip(history["datetime_utc"], history["clean_flags"]))
    assert flags[f"{_DAY}T06:00:00Z"] == "after_gap"
    assert flags[f"{_DAY}T04:00:00Z"] == ""


def test_the_previous_cycle_skipped_still_uses_the_forecast(tmp_path, monkeypatch):
    archive = tmp_path / "archive.csv"
    _hourly_archive(archive, range(9))
    band = _band()
    _forecast_spy(monkeypatch, result=band)
    detector_seen = _detector_spy(monkeypatch)

    result = _run_at_ten(archive)

    assert result["pipeline"]["forecast_used_by_g6"] is True
    assert detector_seen["forecast"] is band


def test_two_skipped_cycles_before_the_run_withhold_the_forecast_from_g6(
        tmp_path, monkeypatch, caplog):
    archive = tmp_path / "archive.csv"
    _hourly_archive(archive, range(8))
    _forecast_spy(monkeypatch, result=_band())
    detector_seen = _detector_spy(monkeypatch)

    with caplog.at_level(logging.INFO, logger="city_pipeline"):
        result = _run_at_ten(archive)

    pipeline = result["pipeline"]
    assert pipeline["forecast_used_by_g6"] is False
    assert pipeline["forecast"]["amps"] == 1200.0
    assert pipeline["forecast"]["ci_lower_amps"] == 1150.0
    assert detector_seen["forecast"] is None
    assert "rating" in result
    notes = _gap_notes(caplog)
    assert len(notes) == 1
    assert "missing hourly slot" in notes[0]
    assert "AUSTIN" in notes[0]


def test_ml_forecast_across_a_gap_in_its_lookback_is_withheld(tmp_path, monkeypatch, caplog):
    archive = tmp_path / "archive.csv"
    _hourly_archive(archive, [h for h in range(10) if h != 5])
    _forecast_spy(monkeypatch, result=_band("ml"))
    detector_seen = _detector_spy(monkeypatch)

    with caplog.at_level(logging.INFO, logger="city_pipeline"):
        result = _run_at_ten(archive, method="ml")

    assert result["pipeline"]["forecast_used_by_g6"] is False
    assert result["pipeline"]["forecast"] is not None
    assert detector_seen["forecast"] is None
    notes = _gap_notes(caplog)
    assert len(notes) == 1
    assert "ml" in notes[0]

    complete = tmp_path / "complete.csv"
    _hourly_archive(complete, range(10))
    band = _band("ml")
    _forecast_spy(monkeypatch, result=band)
    detector_seen = _detector_spy(monkeypatch)

    result = _run_at_ten(complete, method="ml")

    assert result["pipeline"]["forecast_used_by_g6"] is True
    assert detector_seen["forecast"] is band


def test_zero_width_band_keeps_its_own_handling_when_the_history_is_also_stale(
        tmp_path, monkeypatch, caplog):
    archive = tmp_path / "archive.csv"
    _hourly_archive(archive, range(8))
    _forecast_spy(monkeypatch, result=_band(lower=1200.0, upper=1200.0))
    detector_seen = _detector_spy(monkeypatch)

    with caplog.at_level(logging.INFO, logger="city_pipeline"):
        result = _run_at_ten(archive)

    assert result["pipeline"]["forecast_used_by_g6"] is False
    assert detector_seen["forecast"] is None
    messages = [r.getMessage() for r in caplog.records if r.name == "city_pipeline"]
    assert any("forecast band has zero width" in m for m in messages)
    assert _gap_notes(caplog) == []
