import pytest

import config
import thermal_model
from DLRSafetyMonitor import DLRSafetyMonitor  # replace with actual module name


@pytest.fixture
def monitor():
    # static_rating is close to (but not exactly) valid_data's real IEEE 738
    # ampacity (~1686.8 A) rather than the old placeholder-era 1000 A: with
    # G5 now a real fallback gate (Task 3), a cold-start last_good_rating far
    # from the first real reading would spuriously trip G5 on every test's
    # first "successful" check, before that test ever reaches the gate it's
    # actually exercising.
    return DLRSafetyMonitor(
        static_rating=1690.0,
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
    assert result["alerts"] == []
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

    assert result["status"] == "fallback"
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


def test_gate_5_no_alert_when_delta_equals_threshold(monitor, valid_data):
    # static_rating=1690.0, delta_fraction defaults to config.DELTA_FRACTION
    # (0.15) -> threshold = 253.5 A. Set last_good_rating so the delta lands
    # exactly on the threshold: inclusive boundary, matching _gate_plausible/
    # _gate_range's inclusive convention (a delta exactly equal to the
    # threshold is not a swing).
    threshold = monitor.delta_fraction * monitor.static_rating
    monitor.last_good_rating = 1000.0
    monitor._compute_ampacity = lambda d: 1000.0 + threshold

    result = monitor.run_check(valid_data)

    assert result["status"] == "ok"
    assert result["fallback"] is False
    assert len(result["alerts"]) == 0
    assert monitor.last_good_rating == 1000.0 + threshold


def test_gate_5_fallback_when_delta_exceeds_threshold(monitor, valid_data):
    monitor.static_rating = 1000.0
    monitor.last_good_rating = 1000.0
    monitor._compute_ampacity = lambda d: 1150.01  # 150.01 A above last_good; 0.15 * 1000 = 150.0

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert result["fallback"] is True
    assert "G5" in result["alerts"][0]
    assert result["rating"] == min(1150.01, monitor.static_rating)
    # last_good_rating updates to the freshly computed value even on a G5
    # fallback, so a genuine sustained weather change resolves in one cycle
    # rather than latching the monitor in permanent fallback.
    assert monitor.last_good_rating == 1150.01


def test_gate_5_does_not_latch_after_fallback(monitor, valid_data):
    monitor.static_rating = 1000.0
    monitor.last_good_rating = 1000.0
    monitor._compute_ampacity = lambda d: 1150.01

    first_result = monitor.run_check(valid_data)
    assert first_result["status"] == "fallback"

    # Same reading repeated: last_good_rating was updated to 1150.01 by the
    # fallback above, so this second, identical check has a delta of 0 and
    # resolves ok — the monitor does not stay latched in fallback.
    second_result = monitor.run_check(valid_data)
    assert second_result["status"] == "ok"


def test_last_good_rating_not_updated_on_fallback(monitor, valid_data):
    success_result = monitor.run_check(valid_data)
    previous_good = success_result["rating"]

    bad_data = valid_data.copy()
    bad_data["link_status"] = "fail"

    result = monitor.run_check(bad_data)

    assert result["status"] == "fallback"
    assert monitor.last_good_rating == previous_good


def test_gate_1_fallback_uses_static_rating_not_last_good(monitor, valid_data):
    monitor.run_check(valid_data)
    assert monitor.last_good_rating != monitor.static_rating

    bad_data = valid_data.copy()
    bad_data["sensor_status"] = "fail"

    result = monitor.run_check(bad_data)

    assert result["status"] == "fallback"
    assert result["rating"] == monitor.static_rating
    assert "G1 FAIL" in result["alerts"][0]


def test_gate_2_fallback_uses_static_rating_not_last_good(monitor, valid_data):
    monitor.run_check(valid_data)
    assert monitor.last_good_rating != monitor.static_rating

    bad_data = valid_data.copy()
    bad_data["link_status"] = "fail"

    result = monitor.run_check(bad_data)

    assert result["status"] == "fallback"
    assert result["rating"] == monitor.static_rating
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


def test_gate_order_short_circuits_at_lowest_failing_gate(monitor, valid_data):
    # sensor_status="fail" fails G1; temp=100 (out of TEMP_BOUNDS) fails G3.
    # The gate chain evaluates G1 -> G2 -> G3 -> G4 -> G5 in that fixed
    # order and short-circuits at the first failure, so the reported alert
    # must name G1, never G3 (DS-NF5 ordering edge).
    valid_data["sensor_status"] = "fail"
    valid_data["temp"] = 100

    result = monitor.run_check(valid_data)

    assert result["status"] == "fallback"
    assert "G1 FAIL" in result["alerts"][0]
    assert "G3" not in result["alerts"][0]


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


def test_g6_is_inert_when_no_detector_is_injected():
    # No anomaly_detector argument at all -- proves G6 is inert by default
    # (D-05), not merely inert because a test happened to pass None.
    m = DLRSafetyMonitor(
        static_rating=1000,
        conductor=thermal_model.ConductorConfig(**config.DEFAULT_CONDUCTOR_CONFIG_KWARGS),
        logger=lambda msg: None,
    )
    assert m.anomaly_detector is None

    valid_data = {
        "sensor_status": "ok", "link_status": "ok",
        "wind": 5.0, "temp": 25.0, "solar": 500.0,
    }
    # 1050.0 is inside DEFAULT_RATING_BOUNDS (400.0, 1800.0) and within
    # G5's threshold of the cold-start last_good_rating (0.15 * 1000 = 150.0
    # A away from 1000.0), so the reading clears G1-G5 cleanly.
    m._compute_ampacity = lambda d: 1050.0

    result = m.run_check(valid_data)

    assert result["status"] == "ok"
    assert result["fallback"] is False