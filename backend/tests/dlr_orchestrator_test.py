"""
Tests for backend/dlr_orchestrator.py -- `run_dlr_pipeline` (per-city error
isolation, city order, input validation, composed and single-provider wiring,
the default window), `summarize` and `main`.

The per-city pipeline is replaced by a fake, so these tests check
orchestration, not ratings. The ordering test is also offline evidence that
the one entry point covers every city in `config.LOCATIONS`.

Every test writes only under `tmp_path`, and none reaches station discovery or
the network. Follows backend/tests/city_rating_test.py's conventions
(module-level imports, plain asserts, no test classes, no network).
"""

from collections import Counter

import pandas as pd
import pytest
import requests

import anomaly_detector
import city_point
import config
import dlr_orchestrator as orch

_END = "2025-06-01T12:00:00Z"


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
    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    return pd.DataFrame([{"stid": "T1", "name": "t", "lat": lat, "lon": lon}])


def _city_result(city, rating=1000.0, fallback=False, alerts=(), forecast=None):
    """The keys `rate_city` returns, plus the `pipeline` block of `run_city_pipeline`."""
    return {
        "city": city,
        "point": config.CITY_COORDINATES[city],
        "station_id": "T1",
        "candidates_probed": 1,
        "probe_trail": [],
        "rating": rating,
        "status": "fallback" if fallback else "ok",
        "fallback": fallback,
        "alerts": list(alerts),
        "observation": {},
        "exhausted": False,
        "archived": False,
        "pipeline": {
            "history_rows": 0,
            "usable_history_rows": 0,
            "forecast_method": "naive",
            "forecast_used_by_g6": False,
            "forecast": forecast,
            "detector_signal": "cold_start",
            "detector_model": None,
        },
    }


def _fake_city_pipeline(monkeypatch, fail=()):
    """
    Replace `run_city_pipeline` in the orchestrator's namespace (it imported the
    name). Returns the list of `(name, start, end, stations, kwargs)` calls.
    """
    calls = []

    def fake(name, start, end, stations, **kwargs):
        calls.append((name, start, end, stations, kwargs))
        if name in fail:
            raise RuntimeError(f"{name} provider down")
        return _city_result(name)

    monkeypatch.setattr(orch, "run_city_pipeline", fake)
    return calls


def _composed_stub(provenance=(), errors=None):
    """Stands in for a caller-supplied composed fetcher."""
    def fetcher(*args, **kwargs):
        raise AssertionError("the fake per-city pipeline never calls the fetcher")

    fetcher.provenance = list(provenance)
    fetcher.errors = Counter(errors or {})
    return fetcher


def _called_cities(calls):
    return [call[0] for call in calls]


# ──────────────────────────────────────────────────────────────────────────────
# run_dlr_pipeline: isolation, order, validation, wiring, window
# ──────────────────────────────────────────────────────────────────────────────

def test_one_failing_city_is_recorded_and_the_others_still_rate(monkeypatch):
    calls = _fake_city_pipeline(monkeypatch, fail=("MIDLAND",))

    run = orch.run_dlr_pipeline(stations=_stations(), end=_END, archive=False)

    assert run["errors"] == {"MIDLAND": "MIDLAND provider down"}
    assert [row["city"] for row in run["summary"]] == [c for c in config.LOCATIONS if c != "MIDLAND"]
    assert len(run["results"]) == 3
    assert _called_cities(calls) == list(config.LOCATIONS)


def test_cities_run_in_the_order_given_and_default_to_config_locations(monkeypatch):
    calls = _fake_city_pipeline(monkeypatch)

    run = orch.run_dlr_pipeline(
        cities=["EL_PASO", "AUSTIN"], stations=_stations(), end=_END, archive=False)

    assert _called_cities(calls) == ["EL_PASO", "AUSTIN"]
    assert [row["city"] for row in run["summary"]] == ["EL_PASO", "AUSTIN"]

    for every_city in (None, []):
        del calls[:]
        run = orch.run_dlr_pipeline(
            cities=every_city, stations=_stations(), end=_END, archive=False)
        assert _called_cities(calls) == list(config.LOCATIONS)
        assert [row["city"] for row in run["summary"]] == list(config.LOCATIONS)


def test_unknown_city_raises_key_error_before_any_city_runs(monkeypatch):
    calls = _fake_city_pipeline(monkeypatch)

    with pytest.raises(KeyError, match="ATLANTIS"):
        orch.run_dlr_pipeline(
            cities=["AUSTIN", "ATLANTIS"], stations=_stations(), end=_END, archive=False)

    assert calls == []


@pytest.mark.parametrize("bad", [{"provider": "tceq"}, {"forecast_method": "arima"}])
def test_bad_provider_or_forecast_method_raises_value_error(monkeypatch, bad):
    calls = _fake_city_pipeline(monkeypatch)

    # stations=None: validation must come before station discovery, which would
    # raise EnvironmentError here (`_offline_env` has removed the token).
    with pytest.raises(ValueError):
        orch.run_dlr_pipeline(stations=None, end=_END, archive=False, **bad)

    assert calls == []


def test_composed_mode_shares_one_fetcher_and_rates_on_the_station_path(tmp_path, monkeypatch):
    calls = _fake_city_pipeline(monkeypatch)
    archive_path = str(tmp_path / "archive.csv")

    run = orch.run_dlr_pipeline(
        stations=_stations(), end=_END, archive=False, archive_path=archive_path,
        forecast_method="ewm", fetcher=None)

    assert len(calls) == len(config.LOCATIONS)
    for _name, _start, _end, _stations_arg, kwargs in calls:
        assert kwargs["provider"] == "synoptic"
        assert kwargs["forecast_method"] == "ewm"
        assert kwargs["archive"] is False
        assert kwargs["archive_path"] == archive_path
    fetchers = [kwargs["fetch_weather"] for *_rest, kwargs in calls]
    assert all(f is fetchers[0] for f in fetchers)
    assert hasattr(fetchers[0], "provenance")
    assert hasattr(fetchers[0], "errors")
    assert run["provider"] == "composed"
    assert run["sources"] == {}
    assert run["provider_errors"] == {}


def test_composed_mode_uses_the_callers_fetcher_when_given(monkeypatch):
    calls = _fake_city_pipeline(monkeypatch)
    fetcher = _composed_stub(
        provenance=[{"stid": "T1", "hour": "2025-06-01T12:00:00Z", "air_temp": "synoptic",
                     "wind_speed": "tceq", "solar_radiation": "nsrdb"}],
        errors={"nsrdb: ValueError: down": 2})

    run = orch.run_dlr_pipeline(
        stations=_stations(), end=_END, archive=False, fetcher=fetcher)

    assert len(calls) == len(config.LOCATIONS)
    for *_rest, kwargs in calls:
        assert kwargs["fetch_weather"] is fetcher
    assert run["sources"] == {
        "air_temp": {"synoptic": 1},
        "wind_speed": {"tceq": 1},
        "solar_radiation": {"nsrdb": 1},
    }
    assert run["provider_errors"] == {"nsrdb: ValueError: down": 2}


def test_single_provider_mode_passes_no_fetcher_and_reports_no_sources(monkeypatch):
    calls = _fake_city_pipeline(monkeypatch)

    run = orch.run_dlr_pipeline(
        provider="open_meteo", stations=None, end=_END, archive=False, fetcher=_composed_stub())

    assert len(calls) == len(config.LOCATIONS)
    for _name, _start, _end, stations_arg, kwargs in calls:
        assert kwargs["fetch_weather"] is None
        assert kwargs["provider"] == "open_meteo"
        # grid providers need neither discovery nor a token
        assert isinstance(stations_arg, pd.DataFrame)
        assert stations_arg.empty
    assert "sources" not in run
    assert "provider_errors" not in run


def test_composed_mode_without_stations_or_token_raises_before_any_city(monkeypatch):
    calls = _fake_city_pipeline(monkeypatch)

    # Station discovery happens before the per-city loop, so its failure ends the
    # whole run rather than being recorded per city (Phase 5's SCHED-01 relies on it).
    with pytest.raises(EnvironmentError, match="SYNOPTIC_TOKEN"):
        orch.run_dlr_pipeline(stations=None, end=_END, archive=False)

    assert calls == []


def test_window_defaults_to_window_hours_before_end(monkeypatch):
    calls = _fake_city_pipeline(monkeypatch)

    run = orch.run_dlr_pipeline(
        stations=_stations(), end=_END, window_hours=2.0, archive=False)

    assert run["start"] == "2025-06-01T10:00:00Z"
    assert run["end"] == _END
    assert len(calls) == len(config.LOCATIONS)
    for _name, start, end, *_rest in calls:
        assert (start, end) == ("2025-06-01T10:00:00Z", _END)
