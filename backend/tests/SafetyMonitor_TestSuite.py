import pytest

import config
import thermal_model
from DLRSafetyMonitor import DLRSafetyMonitor  # replace with actual module name


@pytest.fixture
def monitor():
    return DLRSafetyMonitor(
        static_rating=1000,
        conductor=thermal_model.ConductorConfig(**config.DEFAULT_CONDUCTOR_CONFIG_KWARGS),
        logger=lambda msg: None,
    )


@pytest.fixture
def valid_data():
    return {
        "sensor_status": "ok",
        "link_status": "ok",
        "wind": 5.0,
        "temp": 25.0,
        "solar": 500.0,
    }


def test_run_check_success_returns_ok(monitor, valid_data):
    result = monitor.run_check(valid_data)

    expected_rating = float(thermal_model.ieee738_ampacity(
        T_amb_c=valid_data["temp"],
        wind_perp_ms=valid_data["wind"],
        ghi_wm2=valid_data["solar"],
        conductor=monitor.conductor,
        solar_altitude_deg=monitor.solar_altitude_deg,
    ))

    assert result["status"] == "ok"
    assert result["fallback"] is False
    assert result["rating"] == expected_rating
    assert type(result["rating"]) is float
    # Not asserting alerts == [] here: under real IEEE 738 physics, this
    # fixture's cold-start last_good_rating (== static_rating, 1000) is far
    # from the real ampacity these inputs compute (~1686.8 A), so the
    # still-flat G5 delta check legitimately fires on the very first call —
    # a cold-start interaction the placeholder formula happened to mask
    # (it coincidentally output ~1005 A for these same inputs). G5's own
    # semantics are covered by the dedicated G5 tests below.
    assert monitor.last_good_rating == expected_rating


def test_gate_1_fails_when_sensor_status_not_ok(monitor, valid_data):
    valid_data["sensor_status"] = "fail"

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert "G1 FAIL" in result["alerts"][0]
    assert "sensor timeout" in result["alerts"][0]


def test_gate_1_fails_when_wind_missing(monitor, valid_data):
    valid_data["wind"] = None

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert "G1 FAIL" in result["alerts"][0]


def test_gate_2_fails_when_link_status_not_ok(monitor, valid_data):
    valid_data["link_status"] = "down"

    result = monitor.run_check(valid_data)

    assert result["status"] == "ok"
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert "G2 FAIL" in result["alerts"][0]
    assert "link lost" in result["alerts"][0]


def test_gate_3_fails_when_wind_out_of_range(monitor, valid_data):
    valid_data["wind"] = 60

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert "G3 FAIL" in result["alerts"][0]
    assert "out-of-range" in result["alerts"][0]


def test_gate_3_fails_when_temp_out_of_range(monitor, valid_data):
    valid_data["temp"] = 100

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert "G3 FAIL" in result["alerts"][0]


def test_gate_3_fails_when_solar_out_of_range(monitor, valid_data):
    valid_data["solar"] = 2000

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert "G3 FAIL" in result["alerts"][0]


def test_gate_4_fails_when_rating_is_implausibly_low(monitor, valid_data):
    monitor._compute_ampacity = lambda d: 300

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert "G4 FAIL" in result["alerts"][0]
    assert "implausible" in result["alerts"][0]


def test_gate_4_fails_when_rating_is_implausibly_high(monitor, valid_data):
    valid_data.update({
        "wind": 50,
        "temp": -20,
        "solar": 0,
    })

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert result["rating"] == monitor.static_rating
    assert "G4 FAIL" in result["alerts"][0]
    assert "implausible" in result["alerts"][0]


@pytest.fixture
def wide_bounds_monitor():
    # G5 tests need G4 kept out of the way (real IEEE 738 ratings for these
    # inputs, ~1686-2277 A, exceed the default (400, 1800) upper bound), so
    # these two tests get their own monitor with widened rating_bounds.
    return DLRSafetyMonitor(
        static_rating=1000,
        conductor=thermal_model.ConductorConfig(**config.DEFAULT_CONDUCTOR_CONFIG_KWARGS),
        rating_bounds=(400.0, 5000.0),
        logger=lambda msg: None,
    )


def test_gate_5_adds_alert_when_delta_exceeds_threshold(wide_bounds_monitor):
    first_data = {
        "sensor_status": "ok",
        "link_status": "ok",
        "wind": 5,
        "temp": 25,
        "solar": 500,
    }
    second_data = {
        "sensor_status": "ok",
        "link_status": "ok",
        "wind": 12,
        "temp": 20,
        "solar": 100,
    }

    first_result = wide_bounds_monitor.run_check(first_data)
    second_result = wide_bounds_monitor.run_check(second_data)

    assert first_result["status"] == "ok"
    assert second_result["status"] == "ok"
    assert len(second_result["alerts"]) == 1
    assert "exceeds threshold" in second_result["alerts"][0]


def test_gate_5_no_alert_when_delta_equals_threshold(wide_bounds_monitor):
    data = {
        "sensor_status": "ok",
        "link_status": "ok",
        "wind": 10,
        "temp": 20,
        "solar": 0,
    }
    computed_rating = float(thermal_model.ieee738_ampacity(
        T_amb_c=data["temp"],
        wind_perp_ms=data["wind"],
        ghi_wm2=data["solar"],
        conductor=wide_bounds_monitor.conductor,
        solar_altitude_deg=wide_bounds_monitor.solar_altitude_deg,
    ))
    # Set last_good_rating so the delta lands exactly on the threshold —
    # boundary is inclusive (a delta exactly equal to the threshold is not a
    # swing), matching the existing >-not->= comparison in the G5 check.
    wide_bounds_monitor.last_good_rating = computed_rating - wide_bounds_monitor.DELTA_THRESH

    result = wide_bounds_monitor.run_check(data)

    assert result["status"] == "ok"
    assert len(result["alerts"]) == 0


def test_last_good_rating_not_updated_on_fallback(monitor, valid_data):
    success_result = monitor.run_check(valid_data)
    previous_good = success_result["rating"]

    bad_data = valid_data.copy()
    bad_data["link_status"] = "fail"

    result = monitor.run_check(bad_data)

    assert result["status"] == "fallback"
    assert monitor.last_good_rating == previous_good


def test_gate_1_fallback_uses_last_good_rating_after_prior_success(monitor, valid_data):
    first_result = monitor.run_check(valid_data)
    good_rating = first_result["rating"]

    bad_data = valid_data.copy()
    bad_data["sensor_status"] = "fail"

    result = monitor.run_check(bad_data)

    assert result["status"] == "fallback"
    assert result["rating"] == good_rating
    assert "G1 FAIL" in result["alerts"][0]


def test_gate_2_fallback_uses_last_good_rating_after_prior_success(monitor, valid_data):
    first_result = monitor.run_check(valid_data)
    good_rating = first_result["rating"]

    bad_data = valid_data.copy()
    bad_data["link_status"] = "fail"

    result = monitor.run_check(bad_data)

    assert result["status"] == "fallback"
    assert result["rating"] == good_rating
    assert "G2 FAIL" in result["alerts"][0]


def test_gate_3_fallback_uses_static_rating_not_last_good(monitor, valid_data):
    monitor.run_check(valid_data)
    assert monitor.last_good_rating != monitor.static_rating

    bad_data = valid_data.copy()
    bad_data["temp"] = 100

    result = monitor.run_check(bad_data)

    assert result["status"] == "fallback"
    assert result["rating"] == monitor.static_rating
    assert "G3 FAIL" in result["alerts"][0]


def test_gate_4_fallback_uses_static_rating_not_last_good(monitor, valid_data):
    monitor.run_check(valid_data)
    assert monitor.last_good_rating != monitor.static_rating

    bad_data = valid_data.copy()
    bad_data.update({
        "wind": 50,
        "temp": -20,
        "solar": 0,
    })

    result = monitor.run_check(bad_data)

    assert result["status"] == "fallback"
    assert result["rating"] == monitor.static_rating
    assert "G4 FAIL" in result["alerts"][0]


def test_range_bounds_are_inclusive(monitor):
    data = {
        "sensor_status": "ok",
        "link_status": "ok",
        "wind": 0,
        "temp": -20,
        "solar": 0,
    }

    result = monitor.run_check(data)

    assert result["status"] in {"ok", "fallback"}  # depends on plausibility, but range should pass
    assert "G3 FAIL" not in "".join(result["alerts"])


def test_plausibility_bounds_are_inclusive():
    # No rating_bounds passed -> pins config.DEFAULT_RATING_BOUNDS == (400.0, 1800.0)
    m = DLRSafetyMonitor(static_rating=1000, logger=lambda msg: None)

    assert m._gate_plausible(400) is True
    assert m._gate_plausible(1800) is True
    assert m._gate_plausible(399.99) is False
    assert m._gate_plausible(1800.01) is False


def test_plausibility_bounds_are_per_location_and_inclusive():
    m = DLRSafetyMonitor(
        static_rating=1900.0,
        rating_bounds=config.RATING_BOUNDS_BY_LOCATION["AUSTIN"],
        logger=lambda msg: None,
    )

    assert m._gate_plausible(800.0) is True
    assert m._gate_plausible(3000.0) is True
    assert m._gate_plausible(799.99) is False
    assert m._gate_plausible(3000.01) is False


def test_rating_bounds_cover_every_city_static_rating():
    for city, static_rating in config.STATIC_RATINGS.items():
        assert city in config.RATING_BOUNDS_BY_LOCATION, city
        lo, hi = config.RATING_BOUNDS_BY_LOCATION[city]
        assert lo <= static_rating <= hi, (city, static_rating, lo, hi)


def test_compute_ampacity_is_wired_to_thermal_model():
    conductor = thermal_model.ConductorConfig(**config.DEFAULT_CONDUCTOR_CONFIG_KWARGS)
    m = DLRSafetyMonitor(static_rating=1000, conductor=conductor, logger=lambda msg: None)

    triples = [
        (5.0, 25.0, 500.0),
        (0.0, 40.0, 1000.0),
        (12.0, 20.0, 100.0),
    ]
    for wind, temp, solar in triples:
        d = {"wind": wind, "temp": temp, "solar": solar}
        direct = float(thermal_model.ieee738_ampacity(
            T_amb_c=temp, wind_perp_ms=wind, ghi_wm2=solar, conductor=conductor,
        ))
        assert m._compute_ampacity(d) == direct