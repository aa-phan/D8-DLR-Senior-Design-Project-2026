"""
Phase 4 end-to-end tracer: proves one anomalous reading travels the whole
new stack — archive append, archive read, forecast, anomaly detection,
and the new G6 gate resolving to DLRSafetyMonitor's existing `_fallback`
helper. Per-layer unit coverage lives in the three per-module test files
Plans 04-02 and 04-03 add.
"""

from datetime import datetime, timedelta

import pytest

import config
import historical_archive
from ampacity_forecast import forecast_ampacity
from anomaly_detector import AnomalyDetector
from DLRSafetyMonitor import DLRSafetyMonitor


def _seed_archive(path, n=24, corridor="AUSTIN_CORPUS_CHRISTI"):
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
            "corridor": corridor,
            "air_temp": 25.0,
            "wind_speed": 5.0,
            "solar_radiation": 500.0,
            "dlr_amps": amps,
            "static_rating": 1200.0,
            "status": "ok",
            "fallback": False,
            "bottleneck_index": 0,
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
