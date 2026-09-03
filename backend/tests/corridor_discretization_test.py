"""
Tests for backend/corridor_discretization.py (C8 -- Corridor Spatial
Discretization) and backend/station_explorer.py::nearest_stations (the D-07
station-resolution generalization C8 depends on, added in Task 2).

Structure follows backend/tests/SafetyMonitor_TestSuite.py's convention
(module-level imports, @pytest.fixture, one test_* function per behavior,
plain asserts, no test classes) and backend/tests/thermal_model_test.py's
style for pure numeric functions (no mocks needed -- geometry functions are
offline; weather/station functions use fakes, never live network calls).
"""

import sys

import pandas as pd
import pytest

import config
import corridor_discretization as cd
import station_explorer as se


# ──────────────────────────────────────────────────────────────────────────────
# Task 1: geometry -- discretize_corridor / initial_bearing_deg / corridor_geometry
# ──────────────────────────────────────────────────────────────────────────────

# Austin/Corpus Christi endpoints used directly (not via config) so these
# tests exercise the pure geometry functions independently of whatever
# CITY_COORDINATES values config.py carries.
AUSTIN = (30.27, -97.74)
CORPUS_CHRISTI = (27.74, -97.40)
MIDLAND = (31.997, -102.078)
EL_PASO = (31.759, -106.487)


def test_discretize_corridor_returns_5_points_endpoints_exact():
    result = cd.discretize_corridor(*AUSTIN, *CORPUS_CHRISTI, n_points=5)

    assert len(result) == 5
    assert result[0] == pytest.approx(AUSTIN, abs=1e-9)
    assert result[4] == pytest.approx(CORPUS_CHRISTI, abs=1e-9)


def test_discretize_corridor_points_lie_on_great_circle_and_are_even():
    points = cd.discretize_corridor(*AUSTIN, *CORPUS_CHRISTI, n_points=5)

    segment_sum = sum(
        se.haversine_km(*points[i], *points[i + 1]) for i in range(len(points) - 1)
    )
    direct = se.haversine_km(*AUSTIN, *CORPUS_CHRISTI)
    assert abs(segment_sum - direct) < 0.5, (segment_sum, direct)

    segment_lengths = [
        se.haversine_km(*points[i], *points[i + 1]) for i in range(len(points) - 1)
    ]
    for length in segment_lengths[1:]:
        assert abs(length - segment_lengths[0]) < 0.01, segment_lengths


def test_discretize_corridor_identical_endpoints_returns_n_copies():
    a, b = 30.0, -97.0
    result = cd.discretize_corridor(a, b, a, b, n_points=5)

    assert len(result) == 5
    assert all(pt == pytest.approx((a, b), abs=1e-9) for pt in result)


def test_discretize_corridor_n_points_1_returns_single_endpoint():
    result = cd.discretize_corridor(*AUSTIN, *CORPUS_CHRISTI, n_points=1)
    assert result == [AUSTIN]


def test_discretize_corridor_n_points_0_raises_value_error():
    with pytest.raises(ValueError, match="n_points"):
        cd.discretize_corridor(*AUSTIN, *CORPUS_CHRISTI, n_points=0)


def test_initial_bearing_deg_austin_to_corpus_christi():
    bearing = cd.initial_bearing_deg(*AUSTIN, *CORPUS_CHRISTI)
    assert 0 <= bearing < 360
    assert abs(bearing - 173.0) < 2.0


def test_initial_bearing_deg_midland_to_el_paso():
    bearing = cd.initial_bearing_deg(*MIDLAND, *EL_PASO)
    assert 0 <= bearing < 360
    assert abs(bearing - 268.0) < 2.0


def test_interpolate_great_circle_fraction_endpoints():
    a = cd.interpolate_great_circle(*AUSTIN, *CORPUS_CHRISTI, fraction=0.0)
    b = cd.interpolate_great_circle(*AUSTIN, *CORPUS_CHRISTI, fraction=1.0)
    assert a == pytest.approx(AUSTIN, abs=1e-9)
    assert b == pytest.approx(CORPUS_CHRISTI, abs=1e-9)


def test_interpolate_great_circle_identical_endpoints_no_zero_division():
    result = cd.interpolate_great_circle(30.0, -97.0, 30.0, -97.0, fraction=0.5)
    assert result == pytest.approx((30.0, -97.0), abs=1e-9)


def test_corridor_geometry_bearings_differ_and_neither_is_default():
    austin_cc = cd.corridor_geometry("AUSTIN_CORPUS_CHRISTI")
    midland_elpaso = cd.corridor_geometry("MIDLAND_EL_PASO")

    a = austin_cc.conductor.line_az
    b = midland_elpaso.conductor.line_az

    assert abs(a - b) > 45, (a, b)
    assert a != 90.0
    assert b != 90.0
    assert len(austin_cc.points) == 5
    assert len(midland_elpaso.points) == 5


def test_corridor_endpoints_resolve_into_all_location_tables():
    for corridor_name, (city_a, city_b) in config.CORRIDOR_ENDPOINTS.items():
        for city in (city_a, city_b):
            assert city in config.CITY_COORDINATES, (corridor_name, city)
            assert city in config.STATIC_RATINGS, (corridor_name, city)
            assert city in config.RATING_BOUNDS_BY_LOCATION, (corridor_name, city)


def test_corridor_endpoints_has_exactly_two_corridors():
    assert set(config.CORRIDOR_ENDPOINTS) == {"AUSTIN_CORPUS_CHRISTI", "MIDLAND_EL_PASO"}


def test_corridor_geometry_static_rating_is_conservative_minimum():
    geometry = cd.corridor_geometry("AUSTIN_CORPUS_CHRISTI")
    city_a, city_b = geometry.endpoint_keys
    expected = min(config.STATIC_RATINGS[city_a], config.STATIC_RATINGS[city_b])
    assert geometry.static_rating == expected


def test_corridor_geometry_unknown_name_raises_key_error():
    with pytest.raises(KeyError):
        cd.corridor_geometry("NOT_A_REAL_CORRIDOR")


def test_no_geo_library_imported():
    assert "geopy" not in sys.modules
    assert "pyproj" not in sys.modules
    assert "shapely" not in sys.modules
    assert "geographiclib" not in sys.modules


def test_module_importable_with_no_synoptic_token_and_no_network(monkeypatch):
    """
    Guards the C8 no-side-effects import contract: importing the module
    (already done at the top of this file) must not require SYNOPTIC_TOKEN.
    Re-verify explicitly with the token unset.
    """
    monkeypatch.delenv("SYNOPTIC_TOKEN", raising=False)
    import importlib

    importlib.reload(cd)


# ──────────────────────────────────────────────────────────────────────────────
# Task 2a: station_explorer.nearest_stations (D-07 station-resolution layer)
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
    result = se.nearest_stations(empty, 30.0, -97.0, n=5)
    assert result.empty


def test_nearest_stations_fewer_than_n_returns_all(fake_stations):
    result = se.nearest_stations(fake_stations, 30.0, -97.0, n=10)
    assert len(result) == len(fake_stations)


def test_nearest_stations_ties_broken_by_stid_ascending():
    df = pd.DataFrame(
        [
            {"stid": "B", "name": "b", "lat": 30.0, "lon": -97.0},
            {"stid": "A", "name": "a", "lat": 30.0, "lon": -97.0},
        ]
    )
    result = se.nearest_stations(df, 30.0, -97.0, n=2)
    assert list(result["stid"]) == ["A", "B"]

    # Deterministic across repeated calls.
    result2 = se.nearest_stations(df, 30.0, -97.0, n=2)
    assert list(result2["stid"]) == ["A", "B"]


# ──────────────────────────────────────────────────────────────────────────────
# Task 2b: rate_corridor -- per-point weather -> per-point ampacity -> minimum
# ──────────────────────────────────────────────────────────────────────────────

_TEST_CITY_A = "TEST_CITY_A"
_TEST_CITY_B = "TEST_CITY_B"
_TEST_CORRIDOR = "TEST_CORRIDOR"


@pytest.fixture
def synthetic_corridor(monkeypatch):
    """
    A synthetic corridor along the equator (both endpoints at lat=0) so
    great-circle interpolation lands on round, easy-to-reason-about
    coordinates: discretize_corridor(0,0, 0,4, n_points=5) yields exactly
    (0,0), (0,1), (0,2), (0,3), (0,4).
    """
    monkeypatch.setitem(config.CITY_COORDINATES, _TEST_CITY_A, (0.0, 0.0))
    monkeypatch.setitem(config.CITY_COORDINATES, _TEST_CITY_B, (0.0, 4.0))
    monkeypatch.setitem(config.STATIC_RATINGS, _TEST_CITY_A, 1690.0)
    monkeypatch.setitem(config.STATIC_RATINGS, _TEST_CITY_B, 1690.0)
    monkeypatch.setitem(config.RATING_BOUNDS_BY_LOCATION, _TEST_CITY_A, (100.0, 5000.0))
    monkeypatch.setitem(config.RATING_BOUNDS_BY_LOCATION, _TEST_CITY_B, (100.0, 5000.0))
    monkeypatch.setitem(
        config.CORRIDOR_ENDPOINTS, _TEST_CORRIDOR, (_TEST_CITY_A, _TEST_CITY_B)
    )
    return _TEST_CORRIDOR


def _weather_frame(stid: str, wind: float, temp: float = 25.0, solar: float = 500.0) -> pd.DataFrame:
    return pd.DataFrame(
        [{"stid": stid, "air_temp": temp, "wind_speed": wind, "solar_radiation": solar}]
    )


def test_rate_corridor_calls_fetcher_once_per_point_even_with_shared_station(
    synthetic_corridor,
):
    # Points 2 and 3 ((0,2) and (0,3)) both resolve to the same nearest
    # station "S23" -- no dedicated station is placed near point 3, and S4
    # is pushed out to lon=5.0 (2 degrees from point 3, vs S23's 1 degree),
    # so S23 (placed exactly at point 2) is unambiguously the closest
    # available candidate for both points 2 and 3 (D-05, explicitly not
    # deduplicated), while S4 remains nearest for point 4 (1 degree away
    # vs S23's 3 degrees).
    stations = pd.DataFrame(
        [
            {"stid": "S0", "name": "s0", "lat": 0.0, "lon": 0.0},
            {"stid": "S1", "name": "s1", "lat": 0.0, "lon": 1.0},
            {"stid": "S23", "name": "s23", "lat": 0.0, "lon": 2.0},
            {"stid": "S4", "name": "s4", "lat": 0.0, "lon": 5.0},
        ]
    )

    calls = []

    def fake_fetch(stids, start, end):
        calls.append(tuple(stids))
        return _weather_frame(stids[0], wind=5.0)

    result = cd.rate_corridor(
        synthetic_corridor, "2025-01-01", "2025-01-02", stations, fetch_weather=fake_fetch
    )

    assert len(calls) == 5
    # Points 2 and 3 both resolved to S23 -- two independent calls for the
    # same station id, not deduplicated or shared.
    assert calls.count(("S23",)) == 2
    assert result["points"][2]["stid"] == "S23"
    assert result["points"][3]["stid"] == "S23"


def test_rate_corridor_default_fetcher_is_weather_provider_fetch_weather():
    import inspect

    sig = inspect.signature(cd.rate_corridor)
    assert sig.parameters["fetch_weather"].default is None
    # Verify the module-level fallback wiring by source inspection rather
    # than calling it (which would require network/SYNOPTIC_TOKEN).
    src = inspect.getsource(cd.rate_corridor)
    assert "weather_provider.fetch_weather" in src


def test_rate_corridor_returns_expected_keys_and_min_reduction(synthetic_corridor):
    stations = pd.DataFrame(
        [
            {"stid": "S0", "name": "s0", "lat": 0.0, "lon": 0.0},
            {"stid": "S1", "name": "s1", "lat": 0.0, "lon": 1.0},
            {"stid": "S2", "name": "s2", "lat": 0.0, "lon": 2.0},
            {"stid": "S3", "name": "s3", "lat": 0.0, "lon": 3.0},
            {"stid": "S4", "name": "s4", "lat": 0.0, "lon": 4.0},
        ]
    )

    # Point index 2 gets a deliberately low wind speed -> lowest ampacity.
    winds_by_stid = {"S0": 5.0, "S1": 5.0, "S2": 1.0, "S3": 5.0, "S4": 5.0}

    def fake_fetch(stids, start, end):
        stid = stids[0]
        return _weather_frame(stid, wind=winds_by_stid[stid])

    result = cd.rate_corridor(
        synthetic_corridor, "2025-01-01", "2025-01-02", stations, fetch_weather=fake_fetch
    )

    assert set(result.keys()) == {"corridor", "bearing_deg", "points", "rating", "bottleneck_index"}
    assert len(result["points"]) == 5
    assert result["bottleneck_index"] == 2
    assert result["rating"] == result["points"][2]["rating"]
    assert result["rating"] == min(p["rating"] for p in result["points"])
    # The bottleneck point's rating is strictly the lowest.
    for i, p in enumerate(result["points"]):
        if i != 2:
            assert p["rating"] > result["rating"]


def test_rate_corridor_never_calls_network_with_injected_fetcher(synthetic_corridor):
    stations = pd.DataFrame(
        [{"stid": "S0", "name": "s0", "lat": 0.0, "lon": 0.0}]
        + [
            {"stid": f"S{i}", "name": f"s{i}", "lat": 0.0, "lon": float(i)}
            for i in range(1, 5)
        ]
    )

    call_count = {"n": 0}

    def fake_fetch(stids, start, end):
        call_count["n"] += 1
        return _weather_frame(stids[0], wind=5.0)

    cd.rate_corridor(
        synthetic_corridor, "2025-01-01", "2025-01-02", stations, fetch_weather=fake_fetch
    )

    # 5 points -> exactly 5 fetcher calls, all through the injected fake
    # (no requests/network module involved at all).
    assert call_count["n"] == 5


def test_rate_corridor_per_point_rating_comes_from_run_check_gate_failure(synthetic_corridor):
    """
    A point whose observation fails a gate (here: temp far outside
    TEMP_BOUNDS, tripping G3) still contributes a fallback rating (the
    corridor's static_rating) rather than an ungated number or a crash.
    """
    stations = pd.DataFrame(
        [
            {"stid": f"S{i}", "name": f"s{i}", "lat": 0.0, "lon": float(i)}
            for i in range(5)
        ]
    )

    def fake_fetch(stids, start, end):
        stid = stids[0]
        if stid == "S2":
            return _weather_frame(stid, wind=5.0, temp=999.0)  # out of TEMP_BOUNDS -> G3
        return _weather_frame(stid, wind=5.0)

    result = cd.rate_corridor(
        synthetic_corridor, "2025-01-01", "2025-01-02", stations, fetch_weather=fake_fetch
    )

    point2 = result["points"][2]
    assert point2["status"] == "fallback"
    assert point2["fallback"] is True
    assert point2["rating"] == 1690.0  # the synthetic corridor's static_rating
    assert "G3" in point2["alerts"][0]


def test_usable_observation_none_when_data_missing():
    empty = pd.DataFrame(columns=["stid", "air_temp", "wind_speed", "solar_radiation"])
    assert cd._usable_observation(empty, "S0") is None

    frame = pd.DataFrame([{"stid": "S0", "air_temp": None, "wind_speed": 5.0, "solar_radiation": 500.0}])
    assert cd._usable_observation(frame, "S0") is None

    frame_missing_station = pd.DataFrame(
        [{"stid": "S1", "air_temp": 25.0, "wind_speed": 5.0, "solar_radiation": 500.0}]
    )
    assert cd._usable_observation(frame_missing_station, "S0") is None


def test_usable_observation_maps_schema_correctly():
    frame = pd.DataFrame(
        [{"stid": "S0", "air_temp": 25.0, "wind_speed": 5.0, "solar_radiation": 500.0}]
    )
    obs = cd._usable_observation(frame, "S0")
    assert obs == {
        "sensor_status": "ok",
        "link_status": "ok",
        "temp": 25.0,
        "wind": 5.0,
        "solar": 500.0,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Task 1 (03-03): resolve_point_observation -- D-08 nearest-5-then-10 probe
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def probe_stations() -> pd.DataFrame:
    """
    10 candidate stations, strictly ordered nearest-to-farthest from
    (0.0, 0.0) by construction (increasing longitude offset), so probe
    order is fully predictable: C01 is always candidate 1, C10 is always
    candidate 10.
    """
    return pd.DataFrame(
        [
            {"stid": f"C{i:02d}", "name": f"c{i}", "lat": 0.0, "lon": 0.01 * i}
            for i in range(1, 11)
        ]
    )


def _empty_weather_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["stid", "air_temp", "wind_speed", "solar_radiation"])


def _probe_fetcher(usable_stids: set, calls: list):
    def fetch(stids, start, end):
        stid = stids[0]
        calls.append(stid)
        if stid in usable_stids:
            return _weather_frame(stid, wind=5.0)
        return _empty_weather_frame()

    return fetch


def test_probe_first_candidate_succeeds_calls_fetcher_once(probe_stations):
    calls = []
    fetch = _probe_fetcher({"C01"}, calls)

    obs, stid, trail = cd.resolve_point_observation(
        0.0, 0.0, "2025-01-01", "2025-01-02", probe_stations, fetch
    )

    assert calls == ["C01"]
    assert stid == "C01"
    assert obs is not None
    assert len(trail) == 1
    assert trail[0]["outcome"] == "usable"


def test_probe_fifth_candidate_succeeds_stays_in_first_batch(probe_stations):
    calls = []
    fetch = _probe_fetcher({"C05"}, calls)

    obs, stid, trail = cd.resolve_point_observation(
        0.0, 0.0, "2025-01-01", "2025-01-02", probe_stations, fetch
    )

    assert calls == ["C01", "C02", "C03", "C04", "C05"]
    assert stid == "C05"
    assert len(trail) == 5


def test_probe_seventh_candidate_succeeds_expands_to_second_batch(probe_stations):
    calls = []
    fetch = _probe_fetcher({"C07"}, calls)

    obs, stid, trail = cd.resolve_point_observation(
        0.0, 0.0, "2025-01-01", "2025-01-02", probe_stations, fetch
    )

    assert calls == ["C01", "C02", "C03", "C04", "C05", "C06", "C07"]
    # The 6th call is the 6th-nearest station -- the expansion probes the
    # next 5 nearest, never re-probing batch 1.
    assert calls[5] == "C06"
    assert stid == "C07"
    assert len(trail) == 7


def test_probe_all_ten_candidates_unusable_stops_at_ten(probe_stations):
    calls = []
    fetch = _probe_fetcher(set(), calls)

    obs, stid, trail = cd.resolve_point_observation(
        0.0, 0.0, "2025-01-01", "2025-01-02", probe_stations, fetch
    )

    assert len(calls) == 10
    assert calls == [f"C{i:02d}" for i in range(1, 11)]
    assert obs is None
    assert stid is None
    assert len(trail) == 10
    assert all(entry["outcome"] == "unusable" for entry in trail)


def test_probe_unusable_frame_variants_are_all_skipped(probe_stations):
    calls = []

    def fetch(stids, start, end):
        stid = stids[0]
        calls.append(stid)
        if stid == "C01":
            return _empty_weather_frame()  # empty frame
        if stid == "C02":
            return pd.DataFrame(
                [{"stid": "OTHER", "air_temp": 25.0, "wind_speed": 5.0, "solar_radiation": 500.0}]
            )  # frame missing the requested station
        if stid == "C03":
            return pd.DataFrame(
                [{"stid": "C03", "air_temp": None, "wind_speed": 5.0, "solar_radiation": 500.0}]
            )  # null in a required variable
        return _weather_frame(stid, wind=5.0)

    obs, stid, trail = cd.resolve_point_observation(
        0.0, 0.0, "2025-01-01", "2025-01-02", probe_stations, fetch
    )

    assert calls == ["C01", "C02", "C03", "C04"]
    assert stid == "C04"
    assert obs is not None


def test_probe_trail_has_no_credential_or_request_parameter_material(probe_stations):
    calls = []
    fetch = _probe_fetcher({"C03"}, calls)

    obs, stid, trail = cd.resolve_point_observation(
        0.0, 0.0, "2025-01-01", "2025-01-02", probe_stations, fetch
    )

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

    calls1 = []
    cd.resolve_point_observation(
        0.0, 0.0, "2025-01-01", "2025-01-02", stations,
        _probe_fetcher(set(), calls1), max_candidates=2,
    )

    calls2 = []
    cd.resolve_point_observation(
        0.0, 0.0, "2025-01-01", "2025-01-02", stations,
        _probe_fetcher(set(), calls2), max_candidates=2,
    )

    assert calls1 == calls2 == ["A", "B"]


def test_probe_discover_corridor_stations_uses_unrestricted_network(monkeypatch):
    captured = {}

    def fake_get_all_stations(token, network_id=None):
        captured["token"] = token
        captured["network_id"] = network_id
        return pd.DataFrame()

    monkeypatch.setattr(se, "get_all_stations", fake_get_all_stations)

    cd.discover_corridor_stations("fake-token")

    assert captured["network_id"] is None
    assert captured["token"] == "fake-token"
