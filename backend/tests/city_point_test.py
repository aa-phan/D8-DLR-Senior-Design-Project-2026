import pytest

import config
import city_point


def test_every_location_resolves_with_its_own_tables():
    for city in config.LOCATIONS:
        pt = city_point.city_point(city)
        assert pt.name == city
        assert pt.coord == config.CITY_COORDINATES[city]
        assert pt.static_rating == config.STATIC_RATINGS[city]
        assert pt.rating_bounds == config.RATING_BOUNDS_BY_LOCATION[city]
        assert pt.bearing_deg == config.CITY_LINE_BEARING_DEG[city]
        assert pt.conductor.line_az == pt.bearing_deg


def test_unknown_city_raises_keyerror_naming_valid_cities():
    with pytest.raises(KeyError, match="AUSTIN"):
        city_point.city_point("NOT_A_CITY")


def test_per_city_tables_cover_exactly_the_locations():
    keys = set(config.LOCATIONS)
    assert set(config.CITY_LINE_BEARING_DEG) == keys
    assert set(config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CITY) == keys
