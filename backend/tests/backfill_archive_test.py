"""
Tests for backend/backfill_archive.py -- the resume/skip behavior, the run log,
the interrupt handling, plus one offline end-to-end run through
`dlr_orchestrator` -> `city_pipeline` -> `city_rating` -> `observation_composer`
(PIPE-01 evidence without a network).

Every test writes under `tmp_path`, so no test touches the real backfill
archive, the backfill log or `config.HISTORICAL_ARCHIVE_PATH`. Follows
backend/tests/city_rating_test.py's conventions (module-level imports, plain
asserts, no test classes, stub providers, no network).
"""

import os
from collections import Counter

import pandas as pd
import pytest
import requests

import anomaly_detector
import backfill_archive
import config
import historical_archive
import observation_composer as oc

_CITY = "AUSTIN"
# A day far in the past: the composer then asks the grid/TCEQ providers for whole
# UTC days, which is why the stub providers below return fixed timestamps rather
# than ones derived from the `end` argument.
_DAY = "2025-06-01"


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


def _hourly(hours, **values):
    """One row per hour in `hours` on _DAY, with the given constant columns."""
    rows = [{"datetime_utc": pd.Timestamp(f"{_DAY}T{h:02d}:00:00Z"), **values} for h in hours]
    return pd.DataFrame(rows)


def _install_providers(monkeypatch, calls, interrupt_at=None):
    """
    Stub the four providers the composer calls through its module references.
    Values differ by provider so a field's source can be read off the value.
    """
    def synoptic(stids, start, end, provider=None, fallback=None):
        calls.append("synoptic")
        if interrupt_at is not None and end == interrupt_at:
            raise KeyboardInterrupt
        return _hourly(range(8, 13), stid=stids[0], air_temp=30.0, wind_speed=5.0,
                       wind_direction=20.0, solar_radiation=520.0)

    def tceq(cams_id, start, end):
        calls.append("tceq")
        return _hourly(range(8, 13), air_temp=31.0, wind_speed=6.0, wind_direction=10.0)

    def nsrdb(lat, lon, start, end):
        calls.append("nsrdb")
        return _hourly(range(24), solar_radiation=500.0)

    def open_meteo(lat, lon, start, end):
        calls.append("open_meteo")
        return pd.DataFrame()

    monkeypatch.setattr(oc.weather_provider, "fetch_weather", synoptic)
    monkeypatch.setattr(oc.tceq_provider, "fetch_tceq", tceq)
    monkeypatch.setattr(oc.nsrdb_provider, "fetch_nsrdb", nsrdb)
    monkeypatch.setattr(oc.open_meteo_provider, "fetch_open_meteo", open_meteo)


def _read_lines(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


# ──────────────────────────────────────────────────────────────────────────────
# Tracer: the whole per-city stack offline, then resume
# ──────────────────────────────────────────────────────────────────────────────

def test_backfill_rates_through_the_composed_stack_offline_and_a_rerun_skips_archived_steps(
        tmp_path, monkeypatch):
    calls = []
    _install_providers(monkeypatch, calls)
    archive = tmp_path / "archive.csv"
    log = tmp_path / "backfill_log.csv"
    lines = []

    def run():
        return backfill_archive.backfill(
            f"{_DAY}T10:00:00Z", f"{_DAY}T11:00:00Z", step_hours=1.0,
            archive_path=str(archive), log_path=str(log), cities=[_CITY],
            stations=_station_at(_CITY), out=lines.append)

    first = run()

    assert first["runs"] == 2
    assert first["skipped"] == 0
    assert first["archived"][_CITY] == 2
    assert first["exhausted"][_CITY] == 0
    assert not first["errors"]
    assert first["provider_issues"] == {}
    assert first["sources"] == {
        "air_temp": {"synoptic": 2},
        "wind_speed": {"tceq": 2},
        "solar_radiation": {"nsrdb": 2},
    }

    hist = historical_archive.read_history(path=str(archive))
    assert len(hist) == 2
    assert list(hist["city"]) == [_CITY, _CITY]
    assert list(hist["datetime_utc"]) == [f"{_DAY}T10:00:00Z", f"{_DAY}T11:00:00Z"]

    log_lines = _read_lines(log)
    assert log_lines[0] == backfill_archive._LOG_HEADER
    assert len(log_lines) == 3
    assert log_lines[1].startswith(f"{_DAY}T10:00:00Z,AUSTIN,")
    assert log_lines[2].startswith(f"{_DAY}T11:00:00Z,AUSTIN,")

    assert "tceq" in calls and "nsrdb" in calls
    assert not os.path.exists(config.HISTORICAL_ARCHIVE_PATH)

    second = run()

    assert second["runs"] == 0
    assert second["skipped"] == 2
    assert len(historical_archive.read_history(path=str(archive))) == 2
    assert len(_read_lines(log)) == len(log_lines)
