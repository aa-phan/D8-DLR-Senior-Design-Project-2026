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


# ──────────────────────────────────────────────────────────────────────────────
# Resume, log and interrupt behavior
# ──────────────────────────────────────────────────────────────────────────────

def _summary_row(city, rating=1000.0, fallback=False, exhausted=False, archived=True, gates=()):
    """The keys `backfill` reads from one `run_dlr_pipeline` summary row."""
    return {"city": city, "rating_a": rating, "fallback": fallback, "exhausted": exhausted,
            "archived": archived, "fallback_gates": list(gates)}


def _install_fake_pipeline(monkeypatch, summary=(), errors=None, printed=()):
    """
    Replace `run_dlr_pipeline` in backfill_archive's namespace (backfill imported
    the name, so patching dlr_orchestrator would not reach it). Returns the list
    of recorded call kwargs.
    """
    seen = []

    def fake(**kwargs):
        seen.append(kwargs)
        for line in printed:
            print(line)
        return {"summary": list(summary), "errors": dict(errors or {})}

    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline", fake)
    return seen


def test_partly_archived_step_runs_only_the_cities_not_yet_archived(tmp_path, monkeypatch):
    archive = tmp_path / "archive.csv"
    row = {
        "datetime_utc": f"{_DAY}T10:00:00Z", "city": "AUSTIN", "air_temp": 25.0,
        "wind_speed": 5.0, "solar_radiation": 500.0, "dlr_amps": 1200.0,
        "static_rating": 1825.0, "status": "ok", "fallback": False,
        "schema_version": historical_archive.ARCHIVE_SCHEMA_VERSION,
    }
    pd.DataFrame([row], columns=historical_archive.ARCHIVE_COLUMNS).to_csv(archive, index=False)
    seen = _install_fake_pipeline(monkeypatch)

    totals = backfill_archive.backfill(
        f"{_DAY}T10:00:00Z", f"{_DAY}T10:00:00Z", archive_path=str(archive),
        log_path=str(tmp_path / "log.csv"), cities=["AUSTIN", "EL_PASO"],
        stations=_station_at(_CITY), out=lambda _line: None)

    assert len(seen) == 1
    assert seen[0]["cities"] == ["EL_PASO"]
    assert seen[0]["end"] == f"{_DAY}T10:00:00Z"
    assert totals["runs"] == 1
    assert totals["skipped"] == 0


def test_retire_stale_log_moves_only_a_log_with_another_header(tmp_path, monkeypatch):
    missing = tmp_path / "missing.csv"
    backfill_archive._retire_stale_log(str(missing))
    assert not missing.exists()
    assert not (tmp_path / "missing.csv.legacy").exists()

    empty = tmp_path / "empty.csv"
    empty.write_text("")
    backfill_archive._retire_stale_log(str(empty))
    assert empty.exists()

    same = tmp_path / "same.csv"
    same.write_text(backfill_archive._LOG_HEADER + "\n")
    backfill_archive._retire_stale_log(str(same))
    assert same.exists()
    assert not (tmp_path / "same.csv.legacy").exists()

    legacy_text = "run_end_utc,corridor,rating_a\n2025-06-01T10:00:00Z,OLD,1000.0\n"
    old = tmp_path / "old.csv"
    old.write_text(legacy_text)
    backfill_archive._retire_stale_log(str(old))
    assert not old.exists()
    assert (tmp_path / "old.csv.legacy").read_text() == legacy_text

    # backfill retires a corridor-era log before writing its own header
    log = tmp_path / "log.csv"
    log.write_text(legacy_text)
    _install_fake_pipeline(monkeypatch)
    backfill_archive.backfill(
        f"{_DAY}T10:00:00Z", f"{_DAY}T10:00:00Z", archive_path=str(tmp_path / "archive.csv"),
        log_path=str(log), cities=[_CITY], stations=_station_at(_CITY), out=lambda _line: None)
    assert _read_lines(log)[0] == backfill_archive._LOG_HEADER
    assert (tmp_path / "log.csv.legacy").read_text() == legacy_text


def test_backfill_logs_one_row_per_city_and_per_error_and_counts_printed_gates(
        tmp_path, monkeypatch, capsys):
    _install_fake_pipeline(
        monkeypatch,
        summary=[_summary_row("AUSTIN", rating=1825.0, fallback=True, gates=("G4",))],
        errors={"MIDLAND": "provider down, retry later"},
        printed=["G4 FAIL (rating out of bounds) -- fallback rating 1825 A",
                 "G6 FAIL (anomaly) -- fallback rating 1825 A"])
    log = tmp_path / "log.csv"
    lines = []

    totals = backfill_archive.backfill(
        f"{_DAY}T10:00:00Z", f"{_DAY}T10:00:00Z", archive_path=str(tmp_path / "archive.csv"),
        log_path=str(log), cities=["AUSTIN", "MIDLAND"], stations=_station_at(_CITY),
        out=lines.append)

    assert _read_lines(log)[1:] == [
        f"{_DAY}T10:00:00Z,AUSTIN,1825.0,True,False,True,G4,",
        f"{_DAY}T10:00:00Z,MIDLAND,,,,,,provider down; retry later",
    ]
    assert totals["fallback"]["AUSTIN"] == 1
    assert totals["errors"]["MIDLAND"] == 1
    assert totals["gates"] == Counter({"G4": 1, "G6": 1})
    assert any("ERROR" in line for line in lines)
    # backfill captured the safety monitor's stdout rather than letting it through
    assert "G4 FAIL" not in capsys.readouterr().out


def test_interrupted_backfill_keeps_progress_and_a_rerun_finishes_the_rest(tmp_path, monkeypatch):
    archive = tmp_path / "archive.csv"
    log = tmp_path / "log.csv"
    lines = []

    def run():
        return backfill_archive.backfill(
            f"{_DAY}T10:00:00Z", f"{_DAY}T12:00:00Z", archive_path=str(archive),
            log_path=str(log), cities=[_CITY], stations=_station_at(_CITY), out=lines.append)

    _install_providers(monkeypatch, [], interrupt_at=f"{_DAY}T11:00:00Z")
    first = run()

    assert first["runs"] == 1
    hist = historical_archive.read_history(path=str(archive))
    assert list(hist["datetime_utc"]) == [f"{_DAY}T10:00:00Z"]
    log_lines = _read_lines(log)
    assert len(log_lines) == 2
    assert log_lines[0] == backfill_archive._LOG_HEADER
    assert log_lines[1].startswith(f"{_DAY}T10:00:00Z,AUSTIN,")
    assert lines[-1] == "\nInterrupted -- progress is saved; rerun the same command to continue."
    assert first["interrupted"] is True

    _install_providers(monkeypatch, [])
    second = run()

    assert second["runs"] == 2
    assert second["skipped"] == 1
    assert second["interrupted"] is False
    hist = historical_archive.read_history(path=str(archive))
    assert len(hist) == 3
    assert hist["datetime_utc"].is_unique


def test_no_synoptic_backfill_never_calls_the_station_provider(tmp_path, monkeypatch):
    calls = []
    _install_providers(monkeypatch, calls)

    totals = backfill_archive.backfill(
        f"{_DAY}T10:00:00Z", f"{_DAY}T10:00:00Z", archive_path=str(tmp_path / "archive.csv"),
        log_path=str(tmp_path / "log.csv"), cities=[_CITY], stations=_station_at(_CITY),
        skip_synoptic=True, fetcher=None, out=lambda _line: None)

    assert "synoptic" not in calls
    assert totals["sources"]["air_temp"] == {"tceq": 1}
    assert totals["archived"][_CITY] == 1
