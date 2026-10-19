"""
Tests for backend/city_rating.py (C8 -- City Point Rating) and
backend/station_explorer.py::nearest_stations (the station-resolution layer
rate_city depends on).

Follows backend/tests/SafetyMonitor_TestSuite.py's convention (module-level
imports, @pytest.fixture, one test_* function per behavior, plain asserts, no
test classes). Weather and station functions use injected fakes, never live
network calls.
"""

import sys

import pandas as pd
import pytest

import city_point
import city_rating as cr
import config
import station_explorer as se

_TEST_CITY = "TEST_CITY"
_SYNTHETIC_STATIC_RATING = 1690.0


@pytest.fixture(autouse=True)
def _isolate_historical_archive(tmp_path, monkeypatch):
    """
    `rate_city` defaults `archive=True`. Redirect the default archive path to
    a `tmp_path`-scoped file for every test so no test can poison the real
    historical archive.
    """
    monkeypatch.setattr(config, "HISTORICAL_ARCHIVE_PATH", str(tmp_path / "test_archive.csv"))


@pytest.fixture
def synthetic_city(monkeypatch):
    """A synthetic city at (0, 0) so station placement is easy to reason about."""
    monkeypatch.setattr(config, "LOCATIONS", config.LOCATIONS + (_TEST_CITY,))
    monkeypatch.setitem(config.CITY_COORDINATES, _TEST_CITY, (0.0, 0.0))
    monkeypatch.setitem(config.STATIC_RATINGS, _TEST_CITY, _SYNTHETIC_STATIC_RATING)
    monkeypatch.setitem(config.RATING_BOUNDS_BY_LOCATION, _TEST_CITY, (100.0, 5000.0))
    monkeypatch.setitem(config.CITY_LINE_BEARING_DEG, _TEST_CITY, 90.0)
    return _TEST_CITY


# Wind from due north (0 deg) is perpendicular to the synthetic city's 90 deg
# line, so the projected wind equals the measured speed in these fixtures.
def _weather_frame(
    stid: str, wind: float, temp: float = 25.0, solar: float = 500.0, wind_dir: float = 0.0
) -> pd.DataFrame:
    return pd.DataFrame(
        [{"stid": stid, "air_temp": temp, "wind_speed": wind, "wind_direction": wind_dir,
          "solar_radiation": solar}]
    )


def _empty_weather_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["stid", "air_temp", "wind_speed", "wind_direction", "solar_radiation"])


def _station_at_city() -> pd.DataFrame:
    return pd.DataFrame([{"stid": "S0", "name": "s0", "lat": 0.0, "lon": 0.0}])


def _good_fetch(stids, start, end, provider="synoptic"):
    return _weather_frame(stids[0], wind=6.5)


# ──────────────────────────────────────────────────────────────────────────────
# Import contract
# ──────────────────────────────────────────────────────────────────────────────


def test_no_geo_library_imported():
    for name in ("geopy", "pyproj", "shapely", "geographiclib"):
        assert name not in sys.modules


def test_module_importable_with_no_synoptic_token_and_no_network(monkeypatch):
    """No-side-effects import contract: no SYNOPTIC_TOKEN, no I/O at import."""
    monkeypatch.delenv("SYNOPTIC_TOKEN", raising=False)
    import importlib

    importlib.reload(cr)


def test_module_has_no_corridor_machinery():
    for name in ("rate_corridor", "corridor_geometry", "discretize_corridor"):
        assert not hasattr(cr, name)


# ──────────────────────────────────────────────────────────────────────────────
# station_explorer.nearest_stations
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_stations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"stid": "N1", "name": "north", "lat": 31.0, "lon": -97.0},
            {"stid": "N2", "name": "north2", "lat": 31.5, "lon": -97.0},
            {"stid": "S1", "name": "south", "lat": 28.0, "lon": -97.4},
        ]
    )


def test_nearest_stations_sorted_ascending_no_mutation(fake_stations):
    original_columns = list(fake_stations.columns)

    result = se.nearest_stations(fake_stations, 30.0, -97.2, n=5)

    assert list(result.columns[: len(original_columns)]) == original_columns
    assert "km_to_point" in result.columns
    assert "km_to_point" not in fake_stations.columns
    distances = list(result["km_to_point"])
    assert distances == sorted(distances)


def test_nearest_stations_empty_dataframe_returns_empty():
    empty = pd.DataFrame(columns=["stid", "name", "lat", "lon"])
    assert se.nearest_stations(empty, 30.0, -97.0, n=5).empty


def test_nearest_stations_fewer_than_n_returns_all(fake_stations):
    assert len(se.nearest_stations(fake_stations, 30.0, -97.0, n=10)) == len(fake_stations)


def test_nearest_stations_ties_broken_by_stid_ascending():
    df = pd.DataFrame(
        [
            {"stid": "B", "name": "b", "lat": 30.0, "lon": -97.0},
            {"stid": "A", "name": "a", "lat": 30.0, "lon": -97.0},
        ]
    )
    assert list(se.nearest_stations(df, 30.0, -97.0, n=2)["stid"]) == ["A", "B"]
    assert list(se.nearest_stations(df, 30.0, -97.0, n=2)["stid"]) == ["A", "B"]


# ──────────────────────────────────────────────────────────────────────────────
# _usable_observation / _usable_observation_grid
# ──────────────────────────────────────────────────────────────────────────────


def test_usable_observation_none_when_data_missing():
    assert cr._usable_observation(None, "X") is None
    assert cr._usable_observation(_empty_weather_frame(), "X") is None
    assert cr._usable_observation(_weather_frame("OTHER", 5.0), "X") is None
    null_temp = pd.DataFrame(
        [{"stid": "X", "air_temp": None, "wind_speed": 5.0, "wind_direction": 0.0,
          "solar_radiation": 500.0}]
    )
    assert cr._usable_observation(null_temp, "X") is None
    missing_col = pd.DataFrame(
        [{"stid": "X", "air_temp": 25.0, "wind_speed": 5.0, "wind_direction": 0.0}]
    )
    assert cr._usable_observation(missing_col, "X") is None


def test_usable_observation_maps_schema_correctly():
    reading = cr._usable_observation(_weather_frame("X", wind=5.0, temp=20.0, solar=300.0), "X")

    assert reading == {
        "sensor_status": "ok",
        "link_status": "ok",
        "temp": 20.0,
        "wind": 5.0,
        "solar": 300.0,
        "wind_direction": 0.0,
    }


def test_usable_observation_grid_takes_first_row_without_stid():
    frame = pd.DataFrame(
        [{"air_temp": 21.0, "wind_speed": 4.0, "wind_direction": 0.0, "solar_radiation": 100.0}]
    )
    reading = cr._usable_observation_grid(frame)
    assert reading["temp"] == 21.0 and reading["wind"] == 4.0 and reading["solar"] == 100.0
    assert cr._usable_observation_grid(None) is None
    assert cr._usable_observation_grid(pd.DataFrame()) is None


# ──────────────────────────────────────────────────────────────────────────────
# resolve_point_observation -- nearest-5-then-10 probe
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def probe_stations() -> pd.DataFrame:
    """10 stations strictly ordered nearest-to-farthest from (0, 0)."""
    return pd.DataFrame(
        [
            {"stid": f"C{i:02d}", "name": f"c{i}", "lat": 0.0, "lon": 0.01 * i}
            for i in range(1, 11)
        ]
    )


def _probe_fetcher(usable_stids: set, calls: list):
    def fetch(stids, start, end, provider="synoptic"):
        stid = stids[0]
        calls.append(stid)
        if stid in usable_stids:
            return _weather_frame(stid, wind=5.0)
        return _empty_weather_frame()

    return fetch


def _probe(stations, fetch, **kw):
    return cr.resolve_point_observation(
        0.0, 0.0, "2025-01-01", "2025-01-02", stations, fetch, **kw
    )


def test_probe_constants():
    assert (cr.PROBE_BATCH_SIZE, cr.MAX_PROBE_CANDIDATES) == (5, 10)
    assert cr.PROBE_BATCH_PAUSE_S == 0.2


def test_probe_first_candidate_succeeds_calls_fetcher_once(probe_stations):
    calls = []
    obs, stid, trail = _probe(probe_stations, _probe_fetcher({"C01"}, calls))

    assert calls == ["C01"]
    assert stid == "C01"
    assert obs is not None
    assert len(trail) == 1 and trail[0]["outcome"] == "usable"


def test_probe_fifth_candidate_succeeds_stays_in_first_batch(probe_stations):
    calls = []
    obs, stid, trail = _probe(probe_stations, _probe_fetcher({"C05"}, calls))

    assert calls == ["C01", "C02", "C03", "C04", "C05"]
    assert stid == "C05"
    assert len(trail) == 5


def test_probe_seventh_candidate_succeeds_expands_to_second_batch(probe_stations):
    calls = []
    obs, stid, trail = _probe(probe_stations, _probe_fetcher({"C07"}, calls), sleep=lambda s: None)

    assert calls == ["C01", "C02", "C03", "C04", "C05", "C06", "C07"]
    assert stid == "C07"
    assert len(trail) == 7


def test_probe_all_ten_candidates_unusable_stops_at_ten(probe_stations):
    calls = []
    obs, stid, trail = _probe(probe_stations, _probe_fetcher(set(), calls), sleep=lambda s: None)

    assert calls == [f"C{i:02d}" for i in range(1, 11)]
    assert obs is None and stid is None
    assert len(trail) == 10
    assert all(entry["outcome"] == "unusable" for entry in trail)


def test_probe_unusable_frame_variants_are_all_skipped(probe_stations):
    calls = []

    def fetch(stids, start, end, provider="synoptic"):
        stid = stids[0]
        calls.append(stid)
        if stid == "C01":
            return _empty_weather_frame()
        if stid == "C02":
            return _weather_frame("OTHER", wind=5.0)
        if stid == "C03":
            return pd.DataFrame(
                [{"stid": "C03", "air_temp": None, "wind_speed": 5.0, "wind_direction": 0.0,
                  "solar_radiation": 500.0}]
            )
        return _weather_frame(stid, wind=5.0)

    obs, stid, trail = _probe(probe_stations, fetch)

    assert calls == ["C01", "C02", "C03", "C04"]
    assert stid == "C04"
    assert obs is not None


def test_probe_raising_fetcher_is_unusable_and_probe_continues(probe_stations):
    calls = []

    def fetch(stids, start, end, provider="synoptic"):
        calls.append(stids[0])
        if stids[0] == "C01":
            raise RuntimeError("boom")
        return _weather_frame(stids[0], wind=5.0)

    obs, stid, trail = _probe(probe_stations, fetch)

    assert stid == "C02"
    assert trail[0]["outcome"] == "unusable"


def test_probe_trail_has_no_credential_or_request_parameter_material(probe_stations):
    calls = []
    obs, stid, trail = _probe(probe_stations, _probe_fetcher({"C03"}, calls))

    assert len(trail) == 3
    trail_text = str(trail).lower()
    for forbidden in ("token", "key", "params"):
        assert forbidden not in trail_text, (forbidden, trail)
    for entry in trail:
        assert set(entry.keys()) == {"stid", "lat", "lon", "distance_km", "outcome"}


def test_probe_equidistant_candidates_probed_in_same_order_across_runs():
    stations = pd.DataFrame(
        [
            {"stid": "B", "name": "b", "lat": 0.0, "lon": 0.01},
            {"stid": "A", "name": "a", "lat": 0.0, "lon": -0.01},
        ]
    )
    calls1, calls2 = [], []
    _probe(stations, _probe_fetcher(set(), calls1), max_candidates=2)
    _probe(stations, _probe_fetcher(set(), calls2), max_candidates=2)

    assert calls1 == calls2 == ["A", "B"]


def test_probe_pause_only_between_batches_never_within_or_after(probe_stations):
    pauses = []

    def fetch_expand(stids, start, end, provider="synoptic"):
        if stids[0] == "C07":
            return _weather_frame(stids[0], wind=5.0)
        return _empty_weather_frame()

    _probe(probe_stations, fetch_expand, sleep=lambda s: pauses.append(s))
    assert pauses == [cr.PROBE_BATCH_PAUSE_S]

    pauses.clear()
    _probe(probe_stations, _good_fetch, sleep=lambda s: pauses.append(s))
    assert pauses == []

    # Exhausting both batches pauses exactly once, never after the last.
    pauses.clear()
    _probe(probe_stations, _probe_fetcher(set(), []), sleep=lambda s: pauses.append(s))
    assert len(pauses) == 1


def test_discover_city_stations_uses_unrestricted_network(monkeypatch):
    captured = {}

    def fake_get_all_stations(token, network_id=None):
        captured["token"] = token
        captured["network_id"] = network_id
        return pd.DataFrame()

    monkeypatch.setattr(se, "get_all_stations", fake_get_all_stations)

    cr.discover_city_stations("fake-token")

    assert captured == {"token": "fake-token", "network_id": None}


# ──────────────────────────────────────────────────────────────────────────────
# rate_city
# ──────────────────────────────────────────────────────────────────────────────


def test_rate_city_returns_expected_keys_for_one_point(synthetic_city):
    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=_good_fetch,
    )

    assert set(result) == {
        "city", "point", "station_id", "candidates_probed", "probe_trail",
        "rating", "status", "fallback", "alerts", "observation", "exhausted", "archived",
    }
    for gone in ("points", "bottleneck_index", "bearing_deg", "exhausted_points", "corridor"):
        assert gone not in result
    assert result["city"] == synthetic_city
    assert result["point"] == (0.0, 0.0)
    assert result["station_id"] == "S0"
    assert result["status"] == "ok"
    assert result["fallback"] is False
    assert result["exhausted"] is False
    assert result["candidates_probed"] == 1
    assert result["observation"]["wind"] == 6.5
    assert result["rating"] > 0


def test_rate_city_rating_matches_direct_monitor_run(synthetic_city):
    from DLRSafetyMonitor import DLRSafetyMonitor

    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=_good_fetch, archive=False,
    )

    pt = city_point.city_point(synthetic_city)
    expected = DLRSafetyMonitor(
        static_rating=pt.static_rating, conductor=pt.conductor,
        rating_bounds=pt.rating_bounds, delta_fraction=float("inf"),
    ).run_check(result["observation"])
    assert result["rating"] == expected["rating"]


def test_rate_city_uses_the_cities_own_static_rating_when_exhausted():
    """No min() with any other city: Corpus Christi uses its own rating."""
    def fetch(stids, start, end, provider="synoptic"):
        return _weather_frame(stids[0], wind=6.5)

    # A missing station (exhausted) resolves to the static rating itself.
    empty = pd.DataFrame(columns=["stid", "name", "lat", "lon"])
    for city in config.LOCATIONS:
        result = cr.rate_city(
            city, "2025-01-01", "2025-01-02", empty, fetch_weather=fetch, archive=False,
        )
        assert result["rating"] == config.STATIC_RATINGS[city]


def test_rate_city_default_fetcher_is_weather_provider_fetch_weather(synthetic_city, monkeypatch):
    calls = []

    def fake_default(stids, start, end, provider="synoptic"):
        calls.append(stids)
        return _weather_frame(stids[0], wind=6.5)

    monkeypatch.setattr(cr.weather_provider, "fetch_weather", fake_default)

    result = cr.rate_city(synthetic_city, "2025-01-01", "2025-01-02", _station_at_city())

    assert calls == [["S0"]]
    assert result["station_id"] == "S0"


def test_rate_city_unknown_city_raises_key_error_naming_valid_cities():
    with pytest.raises(KeyError, match="AUSTIN"):
        cr.rate_city("NOT_A_CITY", "2025-01-01", "2025-01-02", _station_at_city(),
                     fetch_weather=_good_fetch)


def test_rate_city_never_calls_network_with_injected_fetcher(synthetic_city, monkeypatch):
    import weather_provider

    def explode(*a, **k):
        raise AssertionError("network/default fetcher must not be used")

    monkeypatch.setattr(weather_provider, "fetch_weather", explode)

    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=_good_fetch,
    )
    assert result["rating"] > 0


def test_rate_city_gate_failure_comes_from_run_check(synthetic_city):
    """An out-of-range temperature trips a gate; the fallback is the static rating."""
    def fetch(stids, start, end, provider="synoptic"):
        return _weather_frame(stids[0], wind=6.5, temp=500.0)

    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=fetch, archive=False,
    )

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == _SYNTHETIC_STATIC_RATING
    assert result["exhausted"] is False
    assert result["station_id"] == "S0"


def test_rate_city_exhausted_falls_back_to_static_no_exception(synthetic_city):
    stations = pd.DataFrame(
        [{"stid": f"BAD{j}", "name": f"b{j}", "lat": 0.0, "lon": 0.01 * j} for j in range(10)]
    )

    def fetch(stids, start, end, provider="synoptic"):
        return _empty_weather_frame()

    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", stations,
        fetch_weather=fetch, sleep=lambda s: None, archive=False,
    )

    assert result["exhausted"] is True
    assert result["station_id"] is None
    assert result["observation"] is None
    assert result["rating"] == _SYNTHETIC_STATIC_RATING
    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["candidates_probed"] == 10
    assert len(result["probe_trail"]) == 10
    assert len(result["alerts"]) == 1 and "EXHAUSTED FAIL" in result["alerts"][0]
    assert "1690 A" in result["alerts"][0]


def test_rate_city_exhaustion_with_no_stations_at_all(synthetic_city):
    empty = pd.DataFrame(columns=["stid", "name", "lat", "lon"])
    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", empty,
        fetch_weather=_good_fetch, archive=False,
    )
    assert result["exhausted"] is True
    assert result["candidates_probed"] == 0
    assert result["rating"] == _SYNTHETIC_STATIC_RATING


def test_worst_case_probe_count_is_ten_per_city_forty_per_run():
    rows = []
    for city in config.LOCATIONS:
        lat, lon = config.CITY_COORDINATES[city]
        for j in range(10):
            rows.append(
                {"stid": f"{city}_{j}", "name": f"{city}_{j}", "lat": lat, "lon": lon + 0.001 * j}
            )
    stations = pd.DataFrame(rows)
    call_count = {"n": 0}

    def fetch(stids, start, end, provider="synoptic"):
        call_count["n"] += 1
        return _empty_weather_frame()

    for city in config.LOCATIONS:
        before = call_count["n"]
        cr.rate_city(
            city, "2025-01-01", "2025-01-02", stations,
            fetch_weather=fetch, sleep=lambda s: None, archive=False,
        )
        assert call_count["n"] - before == 10

    assert call_count["n"] == 10 * len(config.LOCATIONS) == 40


def test_all_four_cities_rate_successfully_with_independent_points():
    stations = pd.DataFrame(
        [
            {"stid": f"S_{c}", "name": c, "lat": config.CITY_COORDINATES[c][0],
             "lon": config.CITY_COORDINATES[c][1]}
            for c in config.LOCATIONS
        ]
    )
    results = {
        c: cr.rate_city(c, "2025-01-01", "2025-01-02", stations,
                        fetch_weather=_good_fetch, archive=False)
        for c in config.LOCATIONS
    }
    for city, r in results.items():
        assert r["city"] == city
        assert r["point"] == config.CITY_COORDINATES[city]
        assert r["station_id"] == f"S_{city}"
        assert r["rating"] is not None


def test_rate_city_open_meteo_provider_fetches_city_coordinate(synthetic_city):
    seen = {}

    def fetch(stids, start, end, provider="synoptic"):
        seen["args"] = (stids, provider)
        return pd.DataFrame(
            [{"air_temp": 25.0, "wind_speed": 6.5, "wind_direction": 0.0, "solar_radiation": 500.0}]
        )

    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", None,
        fetch_weather=fetch, provider="open_meteo", archive=False,
    )

    assert seen["args"] == ([0.0, 0.0], "open_meteo")
    assert result["station_id"] is None
    assert result["probe_trail"] == []
    assert result["exhausted"] is False
    assert result["status"] == "ok"


def test_rate_city_grid_provider_failure_falls_back_to_static(synthetic_city):
    def fetch(stids, start, end, provider="synoptic"):
        raise RuntimeError("grid down")

    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", None,
        fetch_weather=fetch, provider="nsrdb", archive=False,
    )

    assert result["exhausted"] is True
    assert result["rating"] == _SYNTHETIC_STATIC_RATING


# ──────────────────────────────────────────────────────────────────────────────
# Anomaly detector injection + archive write
# ──────────────────────────────────────────────────────────────────────────────


class _AlwaysTripDetector:
    """A detector test-double that always reports an anomaly."""

    def check(self, raw_data, rating):
        return True, "synthetic always-trip detector (test double)"


def test_rate_city_injected_detector_that_always_trips_forces_static_fallback(synthetic_city):
    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=_good_fetch, anomaly_detector=_AlwaysTripDetector(), archive=False,
    )

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == _SYNTHETIC_STATIC_RATING


def test_rate_city_anomaly_detector_unset_is_ok(synthetic_city):
    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=_good_fetch, archive=False,
    )
    assert result["fallback"] is False
    assert result["status"] == "ok"


def test_rate_city_archives_one_row_per_call(synthetic_city, tmp_path):
    archive_path = tmp_path / "archive.csv"

    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=_good_fetch, archive_path=str(archive_path),
    )

    assert result["archived"] is True
    assert len(archive_path.read_text().strip("\n").split("\n")) == 2  # header + 1 row


def test_rate_city_archived_row_matches_rating_and_city(synthetic_city, tmp_path):
    archive_path = tmp_path / "archive.csv"

    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=_good_fetch, archive_path=str(archive_path),
    )

    df = pd.read_csv(archive_path)
    assert len(df) == 1
    assert df.iloc[0]["dlr_amps"] == result["rating"]
    assert df.iloc[0]["city"] == synthetic_city
    assert "corridor" not in df.columns
    assert df.iloc[0]["static_rating"] == _SYNTHETIC_STATIC_RATING
    assert df.iloc[0]["wind_speed"] == 6.5


def test_rate_city_archived_datetime_equals_end_and_two_calls_are_identical(
    synthetic_city, tmp_path
):
    paths = []
    for name in ("archive1.csv", "archive2.csv"):
        path = tmp_path / name
        cr.rate_city(
            synthetic_city, "2025-01-01", "2025-06-15T00:00:00Z", _station_at_city(),
            fetch_weather=_good_fetch, archive_path=str(path),
        )
        paths.append(path)

    assert pd.read_csv(paths[0]).iloc[0]["datetime_utc"] == "2025-06-15T00:00:00Z"
    # DS-NF2: datetime_utc comes from `end`, never a clock.
    assert paths[0].read_text() == paths[1].read_text()


def test_rate_city_archive_false_writes_no_file_and_returns_archived_false(
    synthetic_city, tmp_path
):
    archive_path = tmp_path / "should_not_exist.csv"

    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=_good_fetch, archive=False, archive_path=str(archive_path),
    )

    assert not archive_path.exists()
    assert result["archived"] is False


def test_rate_city_exhausted_writes_no_archive_row(synthetic_city, tmp_path):
    archive_path = tmp_path / "archive.csv"
    empty = pd.DataFrame(columns=["stid", "name", "lat", "lon"])

    result = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", empty,
        fetch_weather=_good_fetch, archive_path=str(archive_path),
    )

    assert result["archived"] is False
    assert not archive_path.exists()


def test_rate_city_unwritable_archive_path_leaves_rest_of_dict_unchanged(
    synthetic_city, tmp_path
):
    # A regular file where the archive's parent directory should be makes
    # os.makedirs fail inside historical_archive.append_observation.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")

    result_unwritable = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=_good_fetch, archive_path=str(blocker / "archive.csv"),
    )
    result_no_archive = cr.rate_city(
        synthetic_city, "2025-01-01", "2025-01-02", _station_at_city(),
        fetch_weather=_good_fetch, archive=False,
    )

    assert result_unwritable["archived"] is False
    for key in ("city", "point", "station_id", "rating", "status", "fallback", "alerts",
                "exhausted", "candidates_probed"):
        assert result_unwritable[key] == result_no_archive[key]
