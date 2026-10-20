"""
Tests for the backfill validation trace (`backfill_archive --trace-path`) and the
offline `real_data_validation` analysis that reads it back.

The tracer test runs the whole per-city stack offline (stub providers, no
network), writes a trace, and feeds it to the `completeness` subcommand. The
remaining tests harden the trace: error records, credential redaction, the
provenance record of the rated station, and a resumed run's duplicate records.

Every test writes under `tmp_path`, so no test touches the real backfill
archive, log or trace. Follows backend/tests/backfill_archive_test.py's
conventions (module-level imports, plain asserts, no test classes, stub
providers, no network).
"""

import json

import pandas as pd
import pytest
import requests

import anomaly_detector
import backfill_archive
import config
import observation_composer as oc
import real_data_validation

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


def _install_providers(monkeypatch):
    """
    Stub the four providers the composer calls through its module references.
    Values differ by provider so a field's source can be read off the value:
    synoptic for temperature, tceq for wind (with direction), nsrdb for solar,
    and an empty Open-Meteo.
    """
    def synoptic(stids, start, end, provider=None, fallback=None):
        return _hourly(range(8, 13), stid=stids[0], air_temp=30.0, wind_speed=5.0,
                       wind_direction=20.0, solar_radiation=520.0)

    def tceq(cams_id, start, end):
        return _hourly(range(8, 13), air_temp=31.0, wind_speed=6.0, wind_direction=10.0)

    def nsrdb(lat, lon, start, end):
        return _hourly(range(24), solar_radiation=500.0)

    def open_meteo(lat, lon, start, end):
        return pd.DataFrame()

    monkeypatch.setattr(oc.weather_provider, "fetch_weather", synoptic)
    monkeypatch.setattr(oc.tceq_provider, "fetch_tceq", tceq)
    monkeypatch.setattr(oc.nsrdb_provider, "fetch_nsrdb", nsrdb)
    monkeypatch.setattr(oc.open_meteo_provider, "fetch_open_meteo", open_meteo)


def _read_trace(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh.read().splitlines()]


def _run_backfill(tmp_path, **kwargs):
    lines = []
    totals = backfill_archive.backfill(
        f"{_DAY}T10:00:00Z", f"{_DAY}T11:00:00Z",
        archive_path=str(tmp_path / "archive.csv"), log_path=str(tmp_path / "log.csv"),
        cities=[_CITY], stations=_station_at(_CITY), out=lines.append, **kwargs)
    return totals, lines


# ──────────────────────────────────────────────────────────────────────────────
# Tracer: backfill trace -> completeness table, offline
# ──────────────────────────────────────────────────────────────────────────────

def test_backfill_trace_feeds_the_completeness_table_end_to_end(tmp_path, monkeypatch):
    _install_providers(monkeypatch)
    trace_path = tmp_path / "trace.jsonl"

    _run_backfill(tmp_path, trace_path=trace_path)

    assert backfill_archive.TRACE_SCHEMA == real_data_validation.TRACE_SCHEMA
    trace = _read_trace(trace_path)
    assert len(trace) == 2
    assert [r["schema"] for r in trace] == ["backfill_trace/1", "backfill_trace/1"]
    assert [r["city"] for r in trace] == [_CITY, _CITY]
    assert [r["run_end_utc"] for r in trace] == [f"{_DAY}T10:00:00Z", f"{_DAY}T11:00:00Z"]
    for record in trace:
        assert record["sources"] == {
            "air_temp": "synoptic", "wind_speed": "tceq", "solar_radiation": "nsrdb"}
        assert set(record["observation"]) == {"temp", "wind", "wind_raw", "wind_direction", "solar"}
        assert "history_rows" in record["pipeline"]

    out_csv = tmp_path / "completeness.csv"
    code = real_data_validation.main([
        "completeness", "--archive", str(tmp_path / "archive.csv"), "--trace", str(trace_path),
        "--log", str(tmp_path / "log.csv"), "--start", f"{_DAY}T10:00:00Z",
        "--end", f"{_DAY}T11:00:00Z", "--cities", _CITY, "--out", str(out_csv)])

    assert code == 0
    table = pd.read_csv(out_csv)
    assert len(table) == 1
    row = table.iloc[0]
    assert row["city"] == _CITY
    assert {k: int(row[k]) for k in (
        "expected_steps", "trace_records", "archive_rows", "log_rows",
        "exhausted", "errors", "no_trace", "missing")} == {
        "expected_steps": 2, "trace_records": 2, "archive_rows": 2, "log_rows": 2,
        "exhausted": 0, "errors": 0, "no_trace": 0, "missing": 0}


def test_backfill_without_trace_path_writes_no_trace_file(tmp_path, monkeypatch):
    _install_providers(monkeypatch)

    _run_backfill(tmp_path)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["archive.csv", "log.csv"]
