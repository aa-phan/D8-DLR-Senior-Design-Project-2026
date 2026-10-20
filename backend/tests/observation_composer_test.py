"""
Tests for backend/observation_composer.py -- which provider supplies each field,
how the three inputs are aligned on one UTC hour, the fallback pass, the circuit
breaker, error-key redaction and per-field provenance.

Uses stub providers only and writes nothing. Follows
backend/tests/city_rating_test.py's conventions (module-level imports, plain
asserts, no test classes, no network). Assertions are on values, sources and
alignment, never on a rating.
"""

import math
from collections import Counter

import pandas as pd
import pytest
import requests

import anomaly_detector
import config
import observation_composer as oc

# A day far in the past: the composer then asks TCEQ/NSRDB/Open-Meteo for whole UTC
# days, so every stub frame carries fixed timestamps rather than ones derived from
# the `end` argument.
_DAY = "2025-06-01"
_END = f"{_DAY}T11:00:00Z"
_START = f"{_DAY}T10:00:00Z"


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


def _ts(hhmm):
    return pd.Timestamp(f"{_DAY}T{hhmm}:00Z")


def _rows(times, **values):
    """One row per "HH:MM" in `times` on _DAY, with the given constant columns."""
    return pd.DataFrame([{"datetime_utc": _ts(t), **values} for t in times])


def _station_at(city, stid="T1", dlat=0.0):
    lat, lon = config.CITY_COORDINATES[city]
    return pd.DataFrame([{"stid": stid, "name": "t", "lat": lat + dlat, "lon": lon}])


def _install(monkeypatch, calls, synoptic=None, tceq=None, nsrdb=None, open_meteo=None):
    """
    Stub the four providers the composer calls through its module references.
    Each argument is a DataFrame to return, an exception instance to raise, or a
    callable receiving the provider's own arguments; None means an empty frame.
    Every call appends the provider's name to `calls`.
    """
    def make(name, spec):
        def stub(*args, **kwargs):
            calls.append(name)
            result = spec(*args, **kwargs) if callable(spec) else spec
            if isinstance(result, Exception):
                raise result
            return pd.DataFrame() if result is None else result
        return stub

    def synoptic_stub(stids, start, end, provider=None, fallback=None):
        return make("synoptic", synoptic)(stids, start, end, provider=provider, fallback=fallback)

    monkeypatch.setattr(oc.weather_provider, "fetch_weather", synoptic_stub)
    monkeypatch.setattr(oc.tceq_provider, "fetch_tceq", make("tceq", tceq))
    monkeypatch.setattr(oc.nsrdb_provider, "fetch_nsrdb", make("nsrdb", nsrdb))
    monkeypatch.setattr(oc.open_meteo_provider, "fetch_open_meteo", make("open_meteo", open_meteo))


def _fetch(stations, stid="T1", end=_END, fetcher=None):
    """One composed fetch; builds the fetcher unless one is passed. Returns (frame, fetcher)."""
    fetcher = fetcher or oc.make_composed_fetcher(stations)
    return fetcher([stid], _START, end, provider="synoptic"), fetcher


# Distinct values identify the source of each field.
def _synoptic_all(times=("11:00",)):
    return _rows(times, air_temp=30.0, wind_speed=5.0, wind_direction=20.0, solar_radiation=520.0)


def _tceq_all(times=("11:00",)):
    return _rows(times, air_temp=31.0, wind_speed=6.0, wind_direction=10.0)


def _nsrdb_all(times=("11:00",)):
    return _rows(times, solar_radiation=500.0)


def _open_meteo_all(times=("11:00",)):
    return _rows(times, air_temp=32.0, wind_speed=4.0, wind_direction=30.0, solar_radiation=510.0)


# ──────────────────────────────────────────────────────────────────────────────
# Priority, alignment, boundary
# ──────────────────────────────────────────────────────────────────────────────

def test_field_priority_and_run_constants_are_pinned():
    assert oc.FIELD_PRIORITY == {
        "air_temp": ("synoptic", "tceq", "open_meteo"),
        "wind_speed": ("tceq", "synoptic", "open_meteo"),
        "solar_radiation": ("nsrdb", "open_meteo", "synoptic"),
    }
    assert oc.LOOKBACK_HOURS == 3.0
    assert oc.CIRCUIT_BREAKER_FAILURES == 3
    assert oc._BREAKER_PROVIDERS == ("nsrdb", "open_meteo")
    assert oc.HISTORICAL_AFTER_DAYS == 2.0
    assert oc.TCEQ_MAX_KM == 50.0
    assert oc._OUT_COLUMNS == [
        "stid", "datetime_utc", "air_temp", "wind_speed", "wind_direction", "solar_radiation",
        "temp_source", "wind_source", "solar_source",
    ]


def test_each_field_uses_its_first_choice_provider(monkeypatch):
    calls = []
    _install(monkeypatch, calls, synoptic=_synoptic_all(), tceq=_tceq_all(),
             nsrdb=_nsrdb_all(), open_meteo=_open_meteo_all())

    frame, fetcher = _fetch(_station_at("AUSTIN"))

    assert list(frame.columns) == oc._OUT_COLUMNS
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["stid"] == "T1"
    assert row["datetime_utc"] == _ts("11:00")
    assert row["air_temp"] == 30.0 and row["temp_source"] == "synoptic"
    assert row["wind_speed"] == 6.0 and row["wind_direction"] == 10.0
    assert row["wind_source"] == "tceq"
    assert row["solar_radiation"] == 500.0 and row["solar_source"] == "nsrdb"
    assert isinstance(fetcher.errors, Counter) and not fetcher.errors


def test_reading_is_built_at_the_latest_hour_the_chosen_providers_share(monkeypatch):
    calls = []
    hours = ("09:00", "10:00", "11:00")
    _install(monkeypatch, calls,
             synoptic=_rows(hours, air_temp=30.0, wind_speed=5.0, wind_direction=20.0),
             tceq=_tceq_all(("09:00", "10:00")),
             nsrdb=_nsrdb_all(hours))

    frame, _ = _fetch(_station_at("AUSTIN"))

    row = frame.iloc[0]
    # tceq is older than the other two but is not skipped for a newer provider
    assert row["datetime_utc"] == _ts("10:00")
    assert row["wind_source"] == "tceq"
    assert row["temp_source"] == "synoptic"
    assert row["solar_source"] == "nsrdb"
    assert row["wind_speed"] == 6.0


def test_last_reading_in_an_hour_wins_and_rows_after_end_are_ignored(monkeypatch):
    calls = []
    synoptic = pd.concat([_rows(["10:05"], air_temp=28.0), _rows(["10:55"], air_temp=29.0)])
    _install(monkeypatch, calls, synoptic=synoptic, tceq=_tceq_all(("10:00",)),
             nsrdb=_nsrdb_all(("10:00", "11:00")))

    frame, _ = _fetch(_station_at("AUSTIN"))

    assert len(frame) == 1
    assert frame.iloc[0]["datetime_utc"] == _ts("10:00")
    assert frame.iloc[0]["air_temp"] == 29.0

    # a row exactly at end counts; a row after end is ignored
    synoptic = pd.concat([_rows(["11:00"], air_temp=30.0), _rows(["11:30"], air_temp=99.0)])
    _install(monkeypatch, [], synoptic=synoptic, tceq=_tceq_all(("11:00",)),
             nsrdb=_nsrdb_all(("11:00",)))

    frame, _ = _fetch(_station_at("AUSTIN"), end=_END)

    assert frame.iloc[0]["datetime_utc"] == _ts("11:00")
    assert frame.iloc[0]["air_temp"] == 30.0


# ──────────────────────────────────────────────────────────────────────────────
# Fallback pass
# ──────────────────────────────────────────────────────────────────────────────

def test_fallback_providers_fill_in_only_when_the_preferred_ones_share_no_hour(monkeypatch):
    calls = []
    _install(
        monkeypatch, calls,
        synoptic=_rows(["09:00"], air_temp=30.0, wind_speed=5.0, wind_direction=20.0),
        tceq=_tceq_all(("11:00",)),
        nsrdb=_nsrdb_all(("10:00",)),
        open_meteo=_rows(["09:00", "11:00"], solar_radiation=510.0))

    frame, _ = _fetch(_station_at("AUSTIN"))

    row = frame.iloc[0]
    assert row["datetime_utc"] == _ts("11:00")
    assert row["air_temp"] == 31.0 and row["temp_source"] == "tceq"
    assert row["wind_speed"] == 6.0 and row["wind_direction"] == 10.0
    assert row["wind_source"] == "tceq"
    assert row["solar_radiation"] == 510.0 and row["solar_source"] == "open_meteo"


def test_fallback_providers_are_not_called_when_the_preferred_ones_share_an_hour(monkeypatch):
    calls = []
    hours = ("09:00", "10:00", "11:00")
    _install(
        monkeypatch, calls,
        synoptic=_rows(["09:00"], air_temp=30.0, wind_speed=5.0, wind_direction=20.0),
        tceq=_tceq_all(("09:00",)),
        nsrdb=_nsrdb_all(("09:00",)),
        open_meteo=_open_meteo_all(hours))

    frame, _ = _fetch(_station_at("AUSTIN"))

    row = frame.iloc[0]
    assert row["datetime_utc"] == _ts("09:00")
    assert (row["temp_source"], row["wind_source"], row["solar_source"]) == (
        "synoptic", "tceq", "nsrdb")
    assert "open_meteo" not in calls


def test_earlier_ranked_provider_keeps_an_hour_in_the_fallback_pass(monkeypatch):
    calls = []
    tceq = pd.concat([
        _rows(["09:00"], air_temp=31.0, wind_speed=6.0, wind_direction=10.0),
        _rows(["11:00"], air_temp=31.0),
    ])
    _install(
        monkeypatch, calls,
        synoptic=_rows(["11:00"], air_temp=30.0, wind_speed=5.0, wind_direction=20.0),
        tceq=tceq,
        nsrdb=_nsrdb_all(("11:00",)))

    frame, _ = _fetch(_station_at("AUSTIN"))

    row = frame.iloc[0]
    assert row["datetime_utc"] == _ts("11:00")
    # tceq also offers 31.0 for 11:00 but ranks below synoptic for air_temp
    assert row["air_temp"] == 30.0 and row["temp_source"] == "synoptic"
    assert row["wind_speed"] == 5.0 and row["wind_direction"] == 20.0
    assert row["wind_source"] == "synoptic"
    assert row["solar_source"] == "nsrdb"


# ──────────────────────────────────────────────────────────────────────────────
# Wind pairing and the empty result
# ──────────────────────────────────────────────────────────────────────────────

def test_wind_speed_needs_a_direction_from_the_same_provider_and_hour(monkeypatch):
    calls = []
    tceq = pd.concat([
        _rows(["11:00"], wind_speed=6.0, wind_direction=math.nan),
        _rows(["10:00"], wind_speed=math.nan, wind_direction=10.0),
    ])
    _install(
        monkeypatch, calls,
        synoptic=_rows(["11:00"], air_temp=30.0, wind_speed=5.0, wind_direction=20.0),
        tceq=tceq,
        nsrdb=_nsrdb_all(("11:00",)))

    frame, _ = _fetch(_station_at("AUSTIN"))

    row = frame.iloc[0]
    assert row["datetime_utc"] == _ts("11:00")
    assert row["wind_speed"] == 5.0
    assert row["wind_direction"] == 20.0
    assert row["wind_source"] == "synoptic"


def test_no_hour_with_all_three_inputs_returns_an_empty_frame(monkeypatch):
    # no provider supplies solar radiation
    calls = []
    _install(monkeypatch, calls,
             synoptic=_rows(["11:00"], air_temp=30.0, wind_speed=5.0, wind_direction=20.0),
             tceq=_tceq_all())

    frame, fetcher = _fetch(_station_at("AUSTIN"))

    assert frame.empty
    assert list(frame.columns) == oc._OUT_COLUMNS
    assert fetcher.provenance == []

    # every provider returns nothing
    _install(monkeypatch, [])

    frame, fetcher = _fetch(_station_at("AUSTIN"))

    assert frame.empty
    assert list(frame.columns) == oc._OUT_COLUMNS
    assert fetcher.provenance == []


# ──────────────────────────────────────────────────────────────────────────────
# Provenance, circuit breaker, error keys, provider applicability
# ──────────────────────────────────────────────────────────────────────────────

def _stations_near(city, n):
    """
    Stations T1..Tn, each 0.01 degree further north than the last: each has its own
    rounded grid coordinate (hence its own grid cache key) yet stays within
    TCEQ_MAX_KM of the city.
    """
    lat, lon = config.CITY_COORDINATES[city]
    return pd.DataFrame([
        {"stid": f"T{i}", "name": "t", "lat": lat + 0.01 * i, "lon": lon}
        for i in range(1, n + 1)])


def test_provenance_columns_and_one_record_per_reading(monkeypatch):
    def synoptic(stids, start, end, provider=None, fallback=None):
        frame = _synoptic_all()
        if stids[0] == "T1":
            frame["temp_source"] = "asos"  # a provider-supplied source passes through
        return frame

    _install(monkeypatch, [], synoptic=synoptic, tceq=_tceq_all(),
             nsrdb=_nsrdb_all(), open_meteo=_open_meteo_all())

    stations = _stations_near("AUSTIN", 2)
    first, fetcher = _fetch(stations, stid="T1")
    second, _ = _fetch(stations, stid="T2", fetcher=fetcher)

    assert first.iloc[0]["temp_source"] == "asos"
    assert second.iloc[0]["temp_source"] == "synoptic"
    assert len(fetcher.provenance) == 2
    assert fetcher.provenance[0] == {
        "stid": "T1", "hour": f"{_DAY}T11:00:00Z",
        "air_temp": "asos", "wind_speed": "tceq", "solar_radiation": "nsrdb",
    }
    assert oc.summarize_sources(fetcher.provenance) == {
        "air_temp": {"asos": 1, "synoptic": 1},
        "wind_speed": {"tceq": 2},
        "solar_radiation": {"nsrdb": 2},
    }


@pytest.mark.parametrize("name", ["nsrdb", "open_meteo"])
def test_circuit_breaker_skips_a_grid_provider_after_consecutive_failures(monkeypatch, name):
    calls = []
    down = ValueError("down")
    if name == "nsrdb":
        providers = {"nsrdb": down, "open_meteo": _rows(["11:00"], solar_radiation=510.0)}
        solar_source = "open_meteo"
    else:
        # no data from nsrdb is not a failure; open_meteo is what is down
        providers = {"nsrdb": None, "open_meteo": down}
        solar_source = "synoptic"
    _install(monkeypatch, calls, synoptic=_synoptic_all(), tceq=_tceq_all(), **providers)

    fetcher = oc.make_composed_fetcher(_station_at("AUSTIN"))
    for _ in range(5):
        frame, _ = _fetch(None, fetcher=fetcher)
        assert len(frame) == 1
        assert frame.iloc[0]["solar_source"] == solar_source

    assert calls.count(name) == oc.CIRCUIT_BREAKER_FAILURES
    assert fetcher.errors[f"{name}: ValueError: down"] == 3
    assert fetcher.errors[f"{name}: skipped after 3 consecutive failures"] == 2


def test_circuit_breaker_counts_only_consecutive_failures(monkeypatch):
    calls = []

    def nsrdb(lat, lon, start, end):
        # call 3 succeeds; every other call fails
        if calls.count("nsrdb") == 3:
            return _nsrdb_all()
        return ValueError("down")

    _install(monkeypatch, calls, synoptic=_synoptic_all(), tceq=_tceq_all(),
             nsrdb=nsrdb, open_meteo=_rows(["11:00"], solar_radiation=510.0))

    stations = _stations_near("AUSTIN", 7)
    fetcher = oc.make_composed_fetcher(stations)

    for i in range(1, 6):  # fail, fail, success, fail, fail
        frame, _ = _fetch(stations, stid=f"T{i}", fetcher=fetcher)
        assert len(frame) == 1
    assert calls.count("nsrdb") == 5
    assert not any("skipped" in key for key in fetcher.errors)

    _fetch(stations, stid="T6", fetcher=fetcher)  # third failure in a row opens the circuit
    assert calls.count("nsrdb") == 6

    frame, _ = _fetch(stations, stid="T7", fetcher=fetcher)
    assert calls.count("nsrdb") == 6
    assert fetcher.errors["nsrdb: skipped after 3 consecutive failures"] == 1
    assert len(frame) == 1


def test_station_and_tceq_failures_never_open_a_circuit(monkeypatch):
    # (a) the station provider fails on every call; tceq supplies temperature
    calls = []
    _install(monkeypatch, calls, synoptic=RuntimeError("synoptic down"),
             tceq=_tceq_all(), nsrdb=_nsrdb_all())
    fetcher = oc.make_composed_fetcher(_station_at("AUSTIN"))
    for _ in range(5):
        frame, _ = _fetch(None, fetcher=fetcher)
        assert frame.iloc[0]["temp_source"] == "tceq"

    assert calls.count("synoptic") == 5
    assert fetcher.errors["synoptic: RuntimeError"] == 5
    assert not any(key.startswith("synoptic: skipped") for key in fetcher.errors)

    # (b) tceq fails: the failed window is fetched once and re-raised from the cache
    calls = []
    _install(monkeypatch, calls, synoptic=_synoptic_all(),
             tceq=RuntimeError("scrape failed"), nsrdb=_nsrdb_all())
    fetcher = oc.make_composed_fetcher(_station_at("AUSTIN"))
    for _ in range(5):
        frame, _ = _fetch(None, fetcher=fetcher)
        assert frame.iloc[0]["wind_source"] == "synoptic"

    assert calls.count("tceq") == 1
    assert fetcher.errors["tceq: RuntimeError"] == 5
    assert not any(key.startswith("tceq: skipped") for key in fetcher.errors)


def test_error_keys_never_echo_synoptic_or_request_messages(monkeypatch):
    _install(
        monkeypatch, [],
        synoptic=ValueError("token=SECRET-TOKEN rejected"),
        tceq=_tceq_all(),
        nsrdb=ValueError("NSRDB returned HTTP 400 for this window"),
        open_meteo=requests.ConnectionError("https://example.invalid/archive?apikey=SECRET-KEY"))

    _, fetcher = _fetch(_station_at("AUSTIN"))

    assert set(fetcher.errors) == {
        "synoptic: ValueError",
        "nsrdb: ValueError: NSRDB returned HTTP 400 for this window",
        "open_meteo: ConnectionError",
    }
    assert not any("SECRET" in key for key in fetcher.errors)


def test_tceq_needs_a_nearby_city_and_grid_providers_need_coordinates(monkeypatch):
    # (a) a station more than 400 km from every city gets no tceq request
    calls = []
    _install(monkeypatch, calls, synoptic=_synoptic_all(), tceq=_tceq_all(), nsrdb=_nsrdb_all())
    far = pd.DataFrame([{"stid": "FAR", "name": "t", "lat": 35.5, "lon": -100.5}])

    frame, _ = _fetch(far, stid="FAR")

    assert "tceq" not in calls
    row = frame.iloc[0]
    assert row["wind_source"] == "synoptic"
    assert row["solar_source"] == "nsrdb"

    # (b) a station without coordinates gets only the station provider
    calls = []
    _install(monkeypatch, calls, synoptic=_synoptic_all(), tceq=_tceq_all(),
             nsrdb=_nsrdb_all(), open_meteo=_open_meteo_all())

    frame, _ = _fetch(_station_at("AUSTIN"), stid="UNKNOWN")

    assert calls == ["synoptic"]
    row = frame.iloc[0]
    assert (row["temp_source"], row["wind_source"], row["solar_source"]) == (
        "synoptic", "synoptic", "synoptic")
