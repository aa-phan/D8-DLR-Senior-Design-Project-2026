"""
Phase 4 end-to-end tracer: proves one anomalous reading travels the whole
new stack — archive append, archive read, forecast, anomaly detection,
and the new G6 gate resolving to DLRSafetyMonitor's existing `_fallback`
helper. Per-layer unit coverage lives in the three per-module test files
Plans 04-02 and 04-03 add.
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import pytest

import config
import historical_archive
from ampacity_forecast import forecast_ampacity
from anomaly_detector import AnomalyDetector
from DLRSafetyMonitor import DLRSafetyMonitor


class _RaisingDetector:
    """Stub detector whose check() always raises, for the fail-safe test."""

    def check(self, raw_data, rating):
        raise RuntimeError("synthetic detector failure")


def _valid_archive_row(datetime_utc="2026-01-01T00:00:00", air_temp=25.0,
                        city="AUSTIN"):
    return {
        "datetime_utc": datetime_utc,
        "city": city,
        "air_temp": air_temp,
        "wind_speed": 5.0,
        "solar_radiation": 500.0,
        "dlr_amps": 1200.0,
        "static_rating": 1200.0,
        "status": "ok",
        "fallback": False,
        "schema_version": historical_archive.ARCHIVE_SCHEMA_VERSION,
    }


def _seed_archive(path, n=24, city="AUSTIN"):
    """
    Append `n` archive rows through `historical_archive.append_observation`
    to `path`, with `dlr_amps` tightly clustered around 1200.0 A (alternating
    +/-10.0 A, with the final row forced to exactly 1200.0 A) and hourly
    `datetime_utc` stamps, so the resulting forecast band is narrow and
    deterministic.
    """
    base_dt = datetime(2026, 1, 1, 0, 0, 0)

    values = []
    for i in range(n):
        if i == n - 1:
            values.append(1200.0)
        else:
            values.append(1200.0 + (10.0 if i % 2 == 0 else -10.0))

    for i, amps in enumerate(values):
        row = {
            "datetime_utc": (base_dt + timedelta(hours=i)).isoformat(),
            "city": city,
            "air_temp": 25.0,
            "wind_speed": 5.0,
            "solar_radiation": 500.0,
            "dlr_amps": amps,
            "static_rating": 1200.0,
            "status": "ok",
            "fallback": False,
            "schema_version": historical_archive.ARCHIVE_SCHEMA_VERSION,
        }
        assert historical_archive.append_observation(row, path=str(path)) is True


@pytest.fixture
def valid_data():
    return {
        "sensor_status": "ok",
        "link_status": "ok",
        "wind": 5.0,
        "temp": 25.0,
        "solar": 500.0,
    }


def test_anomalous_reading_falls_back_to_static_rating_end_to_end(tmp_path, valid_data):
    archive_path = tmp_path / "ampacity_history.csv"
    _seed_archive(archive_path, n=24)

    history = historical_archive.read_history(path=str(archive_path))
    forecast = forecast_ampacity(history)
    assert forecast is not None

    detector = AnomalyDetector(forecast=forecast, location_key="AUSTIN")

    monitor = DLRSafetyMonitor(
        static_rating=1200.0,
        rating_bounds=(800.0, 3000.0),
        logger=lambda msg: None,
        anomaly_detector=detector,
    )
    monitor._compute_ampacity = lambda d: 1350.0

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == 1200.0
    assert result["alerts"][0].startswith("G6 FAIL")


def test_clean_reading_inside_band_passes_g6(tmp_path, valid_data):
    archive_path = tmp_path / "ampacity_history.csv"
    _seed_archive(archive_path, n=24)

    history = historical_archive.read_history(path=str(archive_path))
    forecast = forecast_ampacity(history)
    assert forecast is not None

    detector = AnomalyDetector(forecast=forecast, location_key="AUSTIN")

    monitor = DLRSafetyMonitor(
        static_rating=1200.0,
        rating_bounds=(800.0, 3000.0),
        logger=lambda msg: None,
        anomaly_detector=detector,
    )
    monitor._compute_ampacity = lambda d: 1210.0

    result = monitor.run_check(valid_data)

    assert result["status"] == "ok"
    assert result["fallback"] is False
    assert result["rating"] == 1210.0


def test_forecast_returns_none_below_min_history_rows(tmp_path):
    archive_path = tmp_path / "ampacity_history.csv"
    _seed_archive(archive_path, n=config.FORECAST_MIN_HISTORY_ROWS - 1)

    history = historical_archive.read_history(path=str(archive_path))
    forecast = forecast_ampacity(history)

    assert forecast is None


def test_detector_raising_falls_back_to_static_rating(valid_data):
    monitor = DLRSafetyMonitor(
        static_rating=1200.0,
        rating_bounds=(800.0, 3000.0),
        logger=lambda msg: None,
        anomaly_detector=_RaisingDetector(),
    )
    monitor._compute_ampacity = lambda d: 1210.0

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert result["rating"] == monitor.static_rating
    assert result["alerts"][0].startswith("G6 FAIL")


def test_append_observation_returns_false_when_parent_is_a_regular_file(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    bad_path = blocker / "ampacity_history.csv"

    result = historical_archive.append_observation(_valid_archive_row(), path=str(bad_path))

    assert result is False


def test_append_observation_rejects_out_of_range_row_and_creates_no_file(tmp_path):
    path = tmp_path / "ampacity_history.csv"
    row = _valid_archive_row(air_temp=999.0)  # outside PIPELINE_SCHEMA's (-20.0, 60.0)

    result = historical_archive.append_observation(row, path=str(path))

    assert result is False
    assert not os.path.exists(path)


def test_two_appends_produce_one_header_line_and_two_data_lines(tmp_path):
    path = tmp_path / "ampacity_history.csv"

    assert historical_archive.append_observation(_valid_archive_row(), path=str(path)) is True
    # A second row for the same instant is now refused (CLEAN-03).
    assert historical_archive.append_observation(
        _valid_archive_row(datetime_utc="2026-01-01T01:00:00"), path=str(path)) is True

    lines = path.read_text().splitlines()
    assert len(lines) == 3  # one header + two data lines
    assert lines.count(lines[0]) == 1


def test_two_appends_read_history_returns_two_rows(tmp_path):
    path = tmp_path / "ampacity_history.csv"

    assert historical_archive.append_observation(_valid_archive_row(), path=str(path)) is True
    # A second row for the same instant is now refused (CLEAN-03).
    assert historical_archive.append_observation(
        _valid_archive_row(datetime_utc="2026-01-01T01:00:00"), path=str(path)) is True

    df = historical_archive.read_history(path=str(path))
    assert len(df) == 2


def test_read_history_on_nonexistent_path_returns_empty_archive_columns_frame(tmp_path):
    path = tmp_path / "does_not_exist.csv"

    df = historical_archive.read_history(path=str(path))

    assert list(df.columns) == historical_archive.ARCHIVE_COLUMNS
    assert len(df) == 0


def test_read_history_orders_ascending_even_when_appended_descending(tmp_path):
    path = tmp_path / "ampacity_history.csv"
    base_dt = datetime(2026, 1, 1, 0, 0, 0)

    for i in (2, 1, 0):
        row = _valid_archive_row(datetime_utc=(base_dt + timedelta(hours=i)).isoformat())
        assert historical_archive.append_observation(row, path=str(path)) is True

    df = historical_archive.read_history(path=str(path))
    timestamps = pd.to_datetime(df["datetime_utc"]).tolist()

    assert timestamps == sorted(timestamps)
