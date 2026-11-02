"""
Offline tests of the per-city production conductor table and its resolver (production-pipeline
Phase 7, COND-01).

Production rating, training and validation read only `config.PRODUCTION_CONDUCTORS` through
`city_point.production_city_point`; the shadow collector and frozen evaluation keep
`config.DEFAULT_CONDUCTOR_CONFIG_KWARGS` through `city_point.city_point` (COND-02, proven by
cond02_shadow_golden_test.py). Covered here: table completeness and sources for every
`config.LOCATIONS` city, the resolver's closed-set and range contract (boundary, empty and
missing-field edges), and the documented divergence of AUSTIN (100 C) from the Drake default (the other cities at parity).

The caller split (COND-02, T-07-09) is pinned by an AST test over the module files: production
callers resolve through `production_city_point`, the three static-only callers use
`city_point.city_point` only for `.static_rating`, and no shadow or frozen-evaluation module names
`production_city_point`.

Follows backend/tests/city_point_test.py's conventions (module-level imports, plain asserts, no test
classes, no network, no conftest).
"""

import ast
from pathlib import Path

import pandas as pd
import pytest
import requests

import city_point
import city_rating
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


def test_documented_divergence():
    """
    DOCUMENTED DIVERGENCE (D-11, signed v4 O4): Power Systems answered for AUSTIN only, so exactly AUSTIN's
    production point differs from the shadow Drake point, and only in maximum operating temperature (100 C,
    not 75 C). CORPUS_CHRISTI, MIDLAND and EL_PASO stay at parity (795 kcmil Drake ACSR, 75 C, 900 m, the
    carried-over bearing). Moving another city off Drake is a table edit, a version bump and an edit here.
    """
    diverging = {"AUSTIN"}
    drake = lambda city: config.conductor_kwargs_for(config.CITY_LINE_BEARING_DEG[city])
    for city in config.LOCATIONS:
        production = city_point.production_city_point(city)
        shadow = city_point.city_point(city)
        entry = config.PRODUCTION_CONDUCTORS[city]
        # what is shared by every city, diverging or not
        assert production.bearing_deg == shadow.bearing_deg == config.CITY_LINE_BEARING_DEG[city]
        assert production.coord == shadow.coord
        assert production.static_rating == shadow.static_rating
        assert production.rating_bounds == shadow.rating_bounds
        assert entry["resist_temp_coef"] == thermal_model.ConductorConfig().alpha_r
        if city in diverging:
            assert vars(production.conductor) != vars(shadow.conductor), city
            assert production.conductor.T_max == 100.0 and shadow.conductor.T_max == 75.0
            # the only differing value is the maximum operating temperature
            assert {k: v for k, v in vars(production.conductor).items() if k != "T_max"} == \
                {k: v for k, v in vars(shadow.conductor).items() if k != "T_max"}
            assert {k: entry[k] for k in drake(city) if k != "max_temp_c"} == \
                {k: v for k, v in drake(city).items() if k != "max_temp_c"}
            assert entry["max_temp_c"] == 100.0 and entry["conductor_type"] == "795 kcmil ACSR Drake"
        else:
            assert vars(production.conductor) == vars(shadow.conductor), city
            assert {k: entry[k] for k in drake(city)} == drake(city)
            assert entry["max_temp_c"] == 75.0
    assert {c for c in config.LOCATIONS if vars(city_point.production_city_point(c).conductor)
            != vars(city_point.city_point(c).conductor)} == diverging


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


# --------------------------------------------------------------------------------------------------
# COND-02 caller split (production-pipeline Phase 7, plan 07-04)
# --------------------------------------------------------------------------------------------------

_BACKEND = Path(__file__).resolve().parent.parent

# Resolve the conductor from the per-city table (rating, training, validation).
PRODUCTION_CALLERS = (
    "city_rating", "anomaly_training", "forecast_training", "real_data_validation",
)
# Read `city_point.city_point(...)` only for `.static_rating`, the same config value on both resolvers.
STATIC_ONLY_CALLERS = ("dlr_orchestrator", "supabase_store", "supabase_smoke")
# The frozen shadow path, collector, legacy corridor, experiment and evaluation core.
SHADOW_MODULES = (
    "forecast_shadow_pipeline", "forecast_shadow_fit_models", "forecast_shadow_fit_reference_refit",
    "forecast_shadow_demo", "forecast_shadow_collect", "forecast_shadow_check_models",
    "forecast_shadow_healthcheck", "legacy_corridor", "forecast_experiment",
    "forecast_shadow_eval_core", "forecast_shadow_score",
)


def _tree(module: str) -> ast.Module:
    return ast.parse((_BACKEND / f"{module}.py").read_text(encoding="utf-8"), filename=module)


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    """Calls whose function is the attribute `<x>.name(...)` or the bare name `name(...)`."""
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == name)
            or (isinstance(node.func, ast.Name) and node.func.id == name)
        )
    ]


def _names_in(tree: ast.AST, name: str) -> list[ast.AST]:
    """Every Name, attribute, import alias or definition that spells `name`."""
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            hits.append(node)
        elif isinstance(node, ast.Attribute) and node.attr == name:
            hits.append(node)
        elif isinstance(node, ast.alias) and name in (node.name, node.asname):
            hits.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            hits.append(node)
    return hits


def test_caller_split():
    # the three module lists exist as files and do not overlap
    groups = (PRODUCTION_CALLERS, STATIC_ONLY_CALLERS, SHADOW_MODULES)
    assert len({m for group in groups for m in group}) == sum(len(group) for group in groups)
    for group in groups:
        for module in group:
            assert (_BACKEND / f"{module}.py").is_file(), module

    # production callers: resolve through the per-city table, never through the shadow resolver
    for module in PRODUCTION_CALLERS:
        tree = _tree(module)
        assert _calls_named(tree, "production_city_point"), f"{module} does not call production_city_point"
        shadow_calls = [c for c in _calls_named(tree, "city_point") if isinstance(c.func, ast.Attribute)]
        assert not shadow_calls, f"{module} still calls <module>.city_point() at line {shadow_calls[0].lineno}"

    # static-only callers: every city_point.city_point(...) is immediately read for `.static_rating`
    for module in STATIC_ONLY_CALLERS:
        tree = _tree(module)
        static_reads = {
            id(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "static_rating"
        }
        calls = _calls_named(tree, "city_point")
        assert calls, f"{module} no longer calls city_point.city_point (update STATIC_ONLY_CALLERS)"
        for call in calls:
            assert id(call) in static_reads, f"{module}:{call.lineno} uses city_point() for more than .static_rating"
        assert not _names_in(tree, "production_city_point"), module

    # shadow and frozen-evaluation modules never name the production resolver (T-07-09)
    for module in SHADOW_MODULES:
        assert not _names_in(_tree(module), "production_city_point"), module

    # city_point.py is the only module that defines it
    definers = sorted(
        path.stem for path in _BACKEND.glob("*.py")
        if any(
            isinstance(node, ast.FunctionDef) and node.name == "production_city_point"
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        )
    )
    assert definers == ["city_point"]


def _austin_observation_frame(wind: float = 4.0):
    """One in-band AUSTIN observation: the computed ampacity at wind 4 m/s sits inside the G4 bounds."""
    def fetch(stids, start, end, provider="synoptic"):
        return pd.DataFrame([{
            "stid": stids[0], "air_temp": 20.0, "wind_speed": wind, "wind_direction": 0.0,
            "solar_radiation": 300.0,
        }])

    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    stations = pd.DataFrame([{"stid": "S0", "name": "s0", "lat": lat, "lon": lon}])
    return fetch, stations


def test_production_follows_the_table_and_shadow_does_not(monkeypatch):
    fetch, stations = _austin_observation_frame()

    def rate():
        return city_rating.rate_city(
            "AUSTIN", "2025-01-01", "2025-01-02", stations, fetch_weather=fetch, archive=False,
        )

    baseline = rate()
    assert baseline["fallback"] is False
    shadow_before = vars(city_point.city_point("AUSTIN").conductor).copy()

    monkeypatch.setitem(config.PRODUCTION_CONDUCTORS, "AUSTIN", _entry("AUSTIN", max_temp_c=125.0))   # AUSTIN is at 100 C since v3
    hotter = rate()
    assert hotter["fallback"] is False
    # a hotter allowed conductor temperature carries more current for the same observation
    assert hotter["rating"] > baseline["rating"]
    # the shadow resolver (and its Drake 75 C conductor, not AUSTIN's 100 C) did not move
    assert vars(city_point.city_point("AUSTIN").conductor) == shadow_before
    assert city_point.city_point("AUSTIN").conductor.T_max == 75.0
