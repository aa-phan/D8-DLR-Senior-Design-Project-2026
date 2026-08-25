import pytest

from DLRSafetyMonitor import DLRSafetyMonitor  # replace with actual module name


@pytest.fixture
def monitor():
    return DLRSafetyMonitor(static_rating=1000, logger=lambda msg: None)


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

    expected_rating = 900 + 5.0 * 30 - (25.0 - 20) * 4 - 500.0 * 0.05

    assert result["status"] == "ok"
    assert result["fallback"] is False
    assert result["rating"] == expected_rating
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


def test_gate_5_adds_alert_when_delta_exceeds_threshold(monitor):
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

    first_result = monitor.run_check(first_data)
    second_result = monitor.run_check(second_data)

    assert first_result["status"] == "ok"
    assert second_result["status"] == "ok"
    assert len(second_result["alerts"]) == 1
    assert "exceeds threshold" in second_result["alerts"][0]


def test_gate_5_no_alert_when_delta_equals_threshold(monitor):
    monitor.last_good_rating = 1000

    data = {
        "sensor_status": "ok",
        "link_status": "ok",
        "wind": 10,
        "temp": 20,
        "solar": 0,
    }
    # rating = 900 + 300 = 1200, delta = 200, so adjust:
    # let's instead use wind=8.333... for 1150 exactly
    data["wind"] = 8.3333333333

    result = monitor.run_check(data)

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
    m = DLRSafetyMonitor(static_rating=1000, logger=lambda msg: None)

    assert m._gate_plausible(400) is True
    assert m._gate_plausible(1800) is True
    assert m._gate_plausible(399.99) is False
    assert m._gate_plausible(1800.01) is False