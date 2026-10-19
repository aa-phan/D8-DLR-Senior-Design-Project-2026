"""
Wind projection in city_rating (Track 1): the measured wind is projected onto
the city's line bearing before the safety monitor, the archive and G6 see it.
Plain asserts; runs under pytest (pythonpath = backend) or by calling each
test_ function directly.
"""
import math
import os
import tempfile

import pandas as pd

import city_point
import city_rating
import historical_archive
import thermal_model


def _row(**overrides):
    base = {"air_temp": 30.0, "wind_speed": 6.0, "solar_radiation": 500.0, "wind_direction": 90.0}
    base.update(overrides)
    return pd.Series(base)


def test_project_wind_across_line_keeps_full_speed():
    bearing = city_point.city_point("AUSTIN").bearing_deg
    obs = {"wind": 5.0, "wind_direction": (bearing + 90) % 360}
    out = city_rating._project_wind(obs, bearing)
    assert math.isclose(out["wind"], 5.0, rel_tol=1e-9)
    assert out["wind_raw"] == 5.0


def test_project_wind_along_line_uses_the_20_degree_floor():
    bearing = city_point.city_point("MIDLAND").bearing_deg
    out = city_rating._project_wind({"wind": 5.0, "wind_direction": bearing % 360}, bearing)
    assert math.isclose(out["wind"], 5.0 * math.sin(math.radians(20)), rel_tol=1e-9)


def test_project_wind_does_not_mutate_its_input():
    obs = {"wind": 5.0, "wind_direction": 10.0}
    city_rating._project_wind(obs, 100.0)
    assert obs == {"wind": 5.0, "wind_direction": 10.0}


def test_perpendicular_wind_scalar_converts_to_float():
    assert isinstance(float(thermal_model.perpendicular_wind(5.0, 90.0, 173.0)), float)


def test_reading_without_wind_direction_is_unusable():
    assert city_rating._reading_from_row(_row(wind_direction=float("nan"))) is None
    assert city_rating._reading_from_row(_row().drop("wind_direction")) is None


def test_reading_with_wind_direction_keeps_it():
    reading = city_rating._reading_from_row(_row(wind_direction=250.0))
    assert reading is not None and reading["wind_direction"] == 250.0


class _SpyDetector:
    signal = "spy"
    model_source = None

    def __init__(self):
        self.seen = None

    def check(self, raw_data, rating):
        self.seen = dict(raw_data)
        return False, ""


def test_archive_gets_projected_wind_and_detector_gets_raw_wind():
    point = city_point.city_point("AUSTIN")
    lat, lon = point.coord
    stations = pd.DataFrame([{"stid": "T1", "name": "t", "lat": lat, "lon": lon,
                              "elev_ft": 0, "county": "", "state": "TX"}])
    across = (point.bearing_deg + 90) % 360

    def fake_fetch(stids, start, end, provider="synoptic", **_):
        return pd.DataFrame([{"stid": stids[0], "air_temp": 30.0, "wind_speed": 6.0,
                              "wind_direction": across, "solar_radiation": 400.0}])

    spy = _SpyDetector()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "a.csv")
        out = city_rating.rate_city("AUSTIN", "2025-06-01T00:00:00Z", "2025-06-01T01:00:00Z", stations,
                                    fetch_weather=fake_fetch, anomaly_detector=spy,
                                    archive=True, archive_path=path, sleep=lambda s: None)
        along = city_rating.rate_city("AUSTIN", "2025-06-01T02:00:00Z", "2025-06-01T03:00:00Z", stations,
                                      fetch_weather=lambda *a, **k: fake_fetch(*a, **k).assign(wind_direction=point.bearing_deg),
                                      archive=True, archive_path=path, sleep=lambda s: None)
        hist = historical_archive.read_history(path=path)
    assert out["archived"] and out["exhausted"] is False
    assert math.isclose(out["observation"]["wind"], 6.0, rel_tol=1e-9)        # across the line
    assert math.isclose(hist["wind_speed"].iloc[0], 6.0, rel_tol=1e-9)
    assert hist["wind_speed"].iloc[1] < 3.0                                   # along the line: floor
    assert along["rating"] < out["rating"]                                    # less cooling -> lower rating
    assert spy.seen["wind"] == 6.0                                            # detector sees the measured speed
    assert out["observation"]["wind_raw"] == 6.0


def test_reading_without_direction_makes_the_city_exhausted():
    point = city_point.city_point("EL_PASO")
    lat, lon = point.coord
    stations = pd.DataFrame([{"stid": "T1", "name": "t", "lat": lat, "lon": lon,
                              "elev_ft": 0, "county": "", "state": "TX"}])

    def no_direction(stids, start, end, provider="synoptic", **_):
        return pd.DataFrame([{"stid": stids[0], "air_temp": 30.0, "wind_speed": 6.0,
                              "wind_direction": None, "solar_radiation": 400.0}])

    out = city_rating.rate_city("EL_PASO", "2025-06-01T00:00:00Z", "2025-06-01T01:00:00Z", stations,
                                fetch_weather=no_direction, archive=False, sleep=lambda s: None)
    assert out["exhausted"] is True and out["fallback"] is True
    assert out["rating"] == point.static_rating
