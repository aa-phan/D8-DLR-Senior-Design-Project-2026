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
