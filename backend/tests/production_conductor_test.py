"""
Offline tests of the per-city production conductor table and its resolver (production-pipeline
Phase 7, COND-01).

Production rating, training and validation read only `config.PRODUCTION_CONDUCTORS` through
`city_point.production_city_point`; the shadow collector and frozen evaluation keep
`config.DEFAULT_CONDUCTOR_CONFIG_KWARGS` through `city_point.city_point` (COND-02, proven by
cond02_shadow_golden_test.py). Covered here: table completeness and sources for every
`config.LOCATIONS` city, the resolver's closed-set and range contract (boundary, empty and
missing-field edges), and the provisional parity with the Drake default.

Follows backend/tests/city_point_test.py's conventions (module-level imports, plain asserts, no test
classes, no network, no conftest).
"""

import pytest
import requests

import city_point
import config
import thermal_model

_NUMERIC_FIELDS = (
    "diameter_m", "resistance_ac", "resist_temp_coef", "emissivity", "absorptivity",
    "max_temp_c", "elevation_m", "line_azimuth",
)
_FIELDS = ("conductor_type",) + _NUMERIC_FIELDS
_CITY = "AUSTIN"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(url, *args, **kwargs):
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)


def _entry(city=_CITY, **changes):
    """A copy of one city's table entry with `changes` applied."""
    return {**config.PRODUCTION_CONDUCTORS[city], **changes}


def test_field_list_names_the_nine_conductor_values():
    assert tuple(config.PRODUCTION_CONDUCTOR_FIELDS) == _FIELDS


def test_every_location_has_a_complete_entry_with_exactly_the_known_fields():
    assert set(config.PRODUCTION_CONDUCTORS) == set(config.LOCATIONS)
    for city in config.LOCATIONS:
        assert set(config.PRODUCTION_CONDUCTORS[city]) == set(config.PRODUCTION_CONDUCTOR_FIELDS), city


def test_every_value_has_a_non_empty_source_string():
    assert set(config.PRODUCTION_CONDUCTOR_SOURCES) == set(config.LOCATIONS)
    for city in config.LOCATIONS:
        sources = config.PRODUCTION_CONDUCTOR_SOURCES[city]
        assert set(sources) == set(config.PRODUCTION_CONDUCTOR_FIELDS), city
        for field, text in sources.items():
            assert isinstance(text, str) and text.strip(), f"{city}.{field} has no source text"
    assert config.PRODUCTION_CONDUCTOR_SOURCE_PROVISIONAL.strip()


def test_ranges_cover_every_numeric_field_and_contain_the_table_values():
    assert set(config.PRODUCTION_CONDUCTOR_RANGES) == set(_NUMERIC_FIELDS)
    for field, (lo, hi) in config.PRODUCTION_CONDUCTOR_RANGES.items():
        assert lo < hi, field
    for city in config.LOCATIONS:
        for field in _NUMERIC_FIELDS:
            lo, hi = config.PRODUCTION_CONDUCTOR_RANGES[field]
            assert lo <= config.PRODUCTION_CONDUCTORS[city][field] <= hi, (city, field)


def test_resolver_returns_the_eight_numeric_fields_as_floats_without_the_type():
    for city in config.LOCATIONS:
        kwargs = config.production_conductor_kwargs_for(city)
        assert set(kwargs) == set(_NUMERIC_FIELDS)
        assert all(type(v) is float for v in kwargs.values())
        assert kwargs == {f: float(config.PRODUCTION_CONDUCTORS[city][f]) for f in _NUMERIC_FIELDS}
        thermal_model.ConductorConfig(**kwargs)   # accepted by the physics model unchanged


def test_production_point_is_built_from_the_table_with_the_tables_azimuth(monkeypatch):
    monkeypatch.setitem(config.PRODUCTION_CONDUCTORS, _CITY, _entry(diameter_m=0.031, line_azimuth=111.5))
    point = city_point.production_city_point(_CITY)
    assert point.name == _CITY
    assert point.conductor.D == 0.031
    assert point.bearing_deg == 111.5 and point.conductor.line_az == 111.5
    assert point.coord == config.CITY_COORDINATES[_CITY]
    assert point.static_rating == config.STATIC_RATINGS[_CITY]
    assert point.rating_bounds == config.RATING_BOUNDS_BY_LOCATION[_CITY]
    # the shadow resolver does not follow the table (COND-02)
    assert city_point.city_point(_CITY).conductor.D == config.DEFAULT_CONDUCTOR_CONFIG_KWARGS["diameter_m"]
    assert city_point.city_point(_CITY).bearing_deg == config.CITY_LINE_BEARING_DEG[_CITY]


def test_provisional_parity():
    """
    PROVISIONAL (D-09): until Power Systems answers, every city's production point equals the shadow Drake
    point (795 kcmil Drake ACSR, 75 C, 900 m, the carried-over bearing). DELETE OR REWRITE THIS TEST when
    Power Systems' values land in config.PRODUCTION_CONDUCTORS.
    """
    for city in config.LOCATIONS:
        production = city_point.production_city_point(city)
        shadow = city_point.city_point(city)
        assert vars(production.conductor) == vars(shadow.conductor), city
        assert production.bearing_deg == shadow.bearing_deg == config.CITY_LINE_BEARING_DEG[city]
        assert production.coord == shadow.coord
        assert production.static_rating == shadow.static_rating
        assert production.rating_bounds == shadow.rating_bounds
        entry = config.PRODUCTION_CONDUCTORS[city]
        drake = config.conductor_kwargs_for(config.CITY_LINE_BEARING_DEG[city])
        assert {k: entry[k] for k in drake} == drake
        assert entry["resist_temp_coef"] == thermal_model.ConductorConfig().alpha_r


@pytest.mark.parametrize("bad_city", ["NOT_A_CITY", ""])
def test_unknown_or_empty_city_raises_keyerror_naming_the_sorted_valid_cities(bad_city):
    for resolve in (config.production_conductor_kwargs_for, city_point.production_city_point):
        with pytest.raises(KeyError) as caught:
            resolve(bad_city)
        assert str(sorted(config.LOCATIONS)) in str(caught.value)


def test_a_location_without_a_table_entry_raises_keyerror_naming_the_city(monkeypatch):
    monkeypatch.setattr(config, "LOCATIONS", config.LOCATIONS + ("SYNTHETIC_CITY",))
    with pytest.raises(KeyError, match="SYNTHETIC_CITY"):
        config.production_conductor_kwargs_for("SYNTHETIC_CITY")


@pytest.mark.parametrize("field", _FIELDS)
def test_a_missing_field_raises_keyerror_naming_city_and_field(monkeypatch, field):
    entry = _entry()
    del entry[field]
    monkeypatch.setitem(config.PRODUCTION_CONDUCTORS, _CITY, entry)
    with pytest.raises(KeyError) as caught:
        config.production_conductor_kwargs_for(_CITY)
    assert _CITY in str(caught.value) and field in str(caught.value)


def test_an_extra_unknown_key_raises_valueerror_naming_it(monkeypatch):
    monkeypatch.setitem(config.PRODUCTION_CONDUCTORS, _CITY, _entry(wind_exposure=0.4))
    with pytest.raises(ValueError, match="wind_exposure"):
        config.production_conductor_kwargs_for(_CITY)


@pytest.mark.parametrize("bad_type", ["", "   ", None, 795])
def test_an_empty_or_non_string_conductor_type_raises_valueerror(monkeypatch, bad_type):
    monkeypatch.setitem(config.PRODUCTION_CONDUCTORS, _CITY, _entry(conductor_type=bad_type))
    with pytest.raises(ValueError, match="conductor_type"):
        config.production_conductor_kwargs_for(_CITY)


@pytest.mark.parametrize("field", _NUMERIC_FIELDS)
def test_range_boundaries_are_accepted_and_one_step_outside_is_rejected(monkeypatch, field):
    lo, hi = config.PRODUCTION_CONDUCTOR_RANGES[field]
    for edge in (lo, hi):
        monkeypatch.setitem(config.PRODUCTION_CONDUCTORS, _CITY, _entry(**{field: edge}))
        assert config.production_conductor_kwargs_for(_CITY)[field] == float(edge)
    for outside, bound in ((lo - 1e-9, lo), (hi + 1e-9, hi)):
        monkeypatch.setitem(config.PRODUCTION_CONDUCTORS, _CITY, _entry(**{field: outside}))
        with pytest.raises(ValueError) as caught:
            config.production_conductor_kwargs_for(_CITY)
        message = str(caught.value)
        assert _CITY in message and field in message and repr(outside) in message
        assert repr(lo) in message and repr(hi) in message, message


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "0.0281", None, True])
def test_a_non_numeric_or_non_finite_value_raises_valueerror(monkeypatch, bad_value):
    monkeypatch.setitem(config.PRODUCTION_CONDUCTORS, _CITY, _entry(diameter_m=bad_value))
    with pytest.raises(ValueError, match="diameter_m"):
        config.production_conductor_kwargs_for(_CITY)
