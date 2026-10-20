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


def _forecast_spy(monkeypatch):
    """Replace forecast_ampacity; collect a copy of every history it is given."""
    seen = []

    def fake(history, method="naive", **kw):
        seen.append(history.copy())
        return None

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
