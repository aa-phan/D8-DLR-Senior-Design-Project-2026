"""
The city-to-branch mapping and the study settings, configuration side (pss-e-integration
Phase 2, plan 02-01: IN-02, D-08).

`psse_job.mapping.load_mapping` turns the one JSON file Power Systems supplies (a required
`cities` section and an optional `study` section) into a validated Mapping plus the sha256 of
the bytes it parsed. The tracer loads the committed placeholder; the rest prove that every
malformed file is refused with all of its problems named, that a placeholder never drives a
study by accident, that the real mapping and case cannot be committed, and that every study
parameter has a stated default and a validated override inside the same hashed file.

Follows backend/tests/psse_contract_test.py's conventions (module-level imports, plain
asserts, no test classes, no network; subprocess only for git).
"""

import copy
import hashlib
import json
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from psse_job import constants, mapping, run_record, settings  # noqa: E402

EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")


def _git(*args):
    return subprocess.run(
        ["git"] + list(args), cwd=_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).returncode


def test_tracer_example_mapping_loads_with_defaults():
    loaded = mapping.load_mapping(EXAMPLE, allow_placeholder=True)
    assert loaded.schema_version == 1
    assert loaded.placeholder is True
    assert list(loaded.cities) == list(constants.CITIES)
    austin = loaded.cities["AUSTIN"]
    assert austin.city == "AUSTIN"
    assert austin.branches == (mapping.BranchRef(90001, 90002, "1"),)
    assert austin.sink_buses == (90002,)
    assert austin.transfer_max_mw is None
    assert loaded.settings == mapping.settings.DEFAULT_SETTINGS
    assert loaded.sha256 == run_record.file_sha256(EXAMPLE)
    assert len(loaded.sha256) == 64
    assert loaded.sha256 == loaded.sha256.lower()


def test_private_example_is_placeholder_with_fake_buses():
    with open(EXAMPLE, "rb") as handle:
        data = json.loads(handle.read().decode("utf-8"))
    assert data["placeholder"] is True
    buses = []
    for city in data["cities"].values():
        for branch in city["branches"]:
            buses.extend([branch["from_bus"], branch["to_bus"]])
        buses.extend(city.get("sink_buses", []))
    assert buses
    assert all(90000 <= bus <= 99999 for bus in buses)
    relative = os.path.relpath(EXAMPLE, _ROOT).replace(os.sep, "/")
    assert _git("ls-files", "--error-unmatch", "--", relative) == 0


def test_private_real_files_are_git_ignored():
    for path in ("psse_local/city_branch_mapping.json", "psse_local/case.sav", "cases/ercot_2026.sav"):
        assert _git("check-ignore", "-q", path) == 0, path


def test_private_placeholder_refused_unless_allowed():
    with pytest.raises(mapping.MappingError) as caught:
        mapping.load_mapping(EXAMPLE)
    assert "placeholder" in str(caught.value)
    assert mapping.load_mapping(EXAMPLE, allow_placeholder=True).placeholder is True


# ---------------------------------------------------------------------------------------
# Every mapping rule, with all problems reported at once (Task 2)
# ---------------------------------------------------------------------------------------


def _base():
    with open(EXAMPLE, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def _dump(data):
    return json.dumps(data).encode("utf-8")


def _edit(change):
    data = _base()
    change(data)
    return _dump(data)


def _austin(data):
    return data["cities"]["AUSTIN"]


def _set(path, value):
    """A change that sets the key path below cities.AUSTIN to `value`."""

    def change(data):
        target = _austin(data)
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return change


def _drop(path):
    def change(data):
        target = _austin(data)
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return change


def _many_branches(data):
    _austin(data)["branches"] = [
        {"from_bus": 91000 + index, "to_bus": 92000 + index, "ckt": "1"} for index in range(21)
    ]


def _lowercase_austin(data):
    data["cities"]["austin"] = data["cities"].pop("AUSTIN")


_SENTINEL = 1234567

_BAD_INPUT = [
    ("not_json", b"{not json", "not valid JSON"),
    ("not_object", b"[1, 2]", "must hold a JSON object"),
    (
        "nan_literal",
        _edit(_set(["transfer_max_mw"], _SENTINEL)).replace(b"1234567", b"NaN"),
        "NaN",
    ),
    (
        "infinity_literal",
        _edit(_set(["transfer_max_mw"], _SENTINEL)).replace(b"1234567", b"Infinity"),
        "Infinity",
    ),
    (
        "duplicate_key",
        _edit(lambda data: None).replace(
            b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1'
        ),
        "duplicate key",
    ),
    ("unknown_top_key", _edit(lambda data: data.update(extra=1)), "unknown key"),
    ("schema_missing", _edit(lambda data: data.pop("schema_version")), "schema_version: missing"),
    ("schema_two", _edit(lambda data: data.update(schema_version=2)), "schema_version: must be"),
    ("schema_text", _edit(lambda data: data.update(schema_version="1")), "schema_version: must be"),
    ("schema_bool", _edit(lambda data: data.update(schema_version=True)), "schema_version: must be"),
    ("placeholder_text", _edit(lambda data: data.update(placeholder="yes")), "placeholder: must be"),
    ("note_too_long", _edit(lambda data: data.update(note="x" * 201)), "note: must be"),
    ("cities_missing", _edit(lambda data: data.pop("cities")), "cities: missing"),
    ("city_missing", _edit(lambda data: data["cities"].pop("EL_PASO")), "cities.EL_PASO: missing"),
    (
        "city_unknown",
        _edit(lambda data: data["cities"].update(HOUSTON=data["cities"]["AUSTIN"])),
        "cities.HOUSTON: unknown city",
    ),
    ("city_lowercase", _edit(_lowercase_austin), "cities.austin: unknown city"),
    (
        "city_not_object",
        _edit(lambda data: data["cities"].update(AUSTIN=[])),
        "cities.AUSTIN: must be an object",
    ),
    ("city_unknown_key", _edit(_set(["colour"], "red")), "cities.AUSTIN.colour: unknown key"),
    ("branches_missing", _edit(_drop(["branches"])), "cities.AUSTIN.branches: missing"),
    (
        "branches_empty",
        _edit(_set(["branches"], [])),
        "cities.AUSTIN.branches: must be a list of 1 to 20",
    ),
    (
        "branches_too_many",
        _edit(_many_branches),
        "cities.AUSTIN.branches: must be a list of 1 to 20",
    ),
    (
        "branch_unknown_key",
        _edit(_set(["branches", 0, "colour"], 1)),
        "branches[0].colour: unknown key",
    ),
    ("branch_missing_ckt", _edit(_drop(["branches", 0, "ckt"])), "branches[0].ckt: missing"),
    ("bus_zero", _edit(_set(["branches", 0, "from_bus"], 0)), "branches[0].from_bus: bus number"),
    ("bus_negative", _edit(_set(["branches", 0, "from_bus"], -5)), "branches[0].from_bus: bus number"),
    ("bus_bool", _edit(_set(["branches", 0, "from_bus"], True)), "branches[0].from_bus: bus number"),
    ("bus_float", _edit(_set(["branches", 0, "from_bus"], 90001.5)), "branches[0].from_bus: bus number"),
    ("bus_text", _edit(_set(["branches", 0, "from_bus"], "90001")), "branches[0].from_bus: bus number"),
    (
        "bus_too_large",
        _edit(_set(["branches", 0, "from_bus"], 1000000)),
        "branches[0].from_bus: bus number",
    ),
    ("same_ends", _edit(_set(["branches", 0, "to_bus"], 90001)), "from_bus and to_bus must differ"),
    ("ckt_empty", _edit(_set(["branches", 0, "ckt"], "")), "branches[0].ckt"),
    ("ckt_three_chars", _edit(_set(["branches", 0, "ckt"], "123")), "branches[0].ckt"),
    ("ckt_space_only", _edit(_set(["branches", 0, "ckt"], " ")), "branches[0].ckt"),
    ("ckt_int", _edit(_set(["branches", 0, "ckt"], 1)), "branches[0].ckt"),
    ("ckt_multisection", _edit(_set(["branches", 0, "ckt"], "&1")), "branches[0].ckt"),
    ("ckt_control_char", _edit(_set(["branches", 0, "ckt"], "\x01")), "branches[0].ckt"),
    ("sink_empty", _edit(_set(["sink_buses"], [])), "cities.AUSTIN.sink_buses: must be a list"),
    (
        "sink_duplicate",
        _edit(_set(["sink_buses"], [90002, 90002])),
        "sink_buses[1]: bus 90002 is listed twice",
    ),
    ("sink_not_int", _edit(_set(["sink_buses"], ["90002"])), "sink_buses[0]: bus number"),
    ("transfer_max_zero", _edit(_set(["transfer_max_mw"], 0)), "cities.AUSTIN.transfer_max_mw"),
    ("transfer_max_bool", _edit(_set(["transfer_max_mw"], True)), "cities.AUSTIN.transfer_max_mw"),
    ("not_utf8", b"\xff\xfe{}", "not UTF-8"),
]


def test_rule_case_count_is_42():
    assert len(_BAD_INPUT) == 42
    assert len(set(item[0] for item in _BAD_INPUT)) == 42


@pytest.mark.parametrize(
    "data,fragment",
    [(item[1], item[2]) for item in _BAD_INPUT],
    ids=[item[0] for item in _BAD_INPUT],
)
def test_rule_rejects_bad_input(data, fragment):
    with pytest.raises(mapping.MappingError) as caught:
        mapping.parse_mapping(data, allow_placeholder=True)
    assert fragment in str(caught.value)
    assert caught.value.problems


def test_rule_reports_every_problem_at_once():
    def three(data):
        data["schema_version"] = 2
        data["note"] = "x" * 201
        _austin(data)["branches"][0]["ckt"] = ""

    with pytest.raises(mapping.MappingError) as caught:
        mapping.parse_mapping(_edit(three), allow_placeholder=True)
    problems = caught.value.problems
    assert len(problems) == 3
    assert any("schema_version" in p for p in problems)
    assert any("note" in p for p in problems)
    assert any("cities.AUSTIN.branches[0].ckt" in p for p in problems)


def test_rule_keeps_at_most_20_problems():
    def many(data):
        for index in range(30):
            data["junk%02d" % index] = index

    with pytest.raises(mapping.MappingError) as caught:
        mapping.parse_mapping(_edit(many), allow_placeholder=True)
    assert len(caught.value.problems) == 20


def test_rule_size_cap_before_parsing(tmp_path, monkeypatch):
    path = tmp_path / "big.json"
    path.write_bytes(b" " * (mapping.MAX_MAPPING_BYTES + 1))

    def must_not_parse(*args, **kwargs):
        raise AssertionError("json.loads was called on an oversized file")

    monkeypatch.setattr(mapping.json, "loads", must_not_parse)
    with pytest.raises(mapping.MappingError) as caught:
        mapping.load_mapping(str(path), allow_placeholder=True)
    assert "larger than 65536 bytes" in str(caught.value)
    assert "big.json" in str(caught.value)


def test_rule_file_at_the_cap_is_parsed(tmp_path):
    data = _edit(lambda d: d.update(note="n"))
    padded = data + b" " * (mapping.MAX_MAPPING_BYTES - len(data))
    assert len(padded) == mapping.MAX_MAPPING_BYTES
    path = tmp_path / "exact.json"
    path.write_bytes(padded)
    assert mapping.load_mapping(str(path), allow_placeholder=True).note == "n"


def test_rule_sink_default_and_ckt_strip():
    def change(data):
        city = _austin(data)
        del city["sink_buses"]
        city["branches"] = [
            {"from_bus": 90001, "to_bus": 90002, "ckt": " 1"},
            {"from_bus": 90003, "to_bus": 90004, "ckt": "A1"},
        ]
        city["transfer_max_mw"] = 400

    loaded = mapping.parse_mapping(_edit(change), allow_placeholder=True)
    austin = loaded.cities["AUSTIN"]
    assert austin.branches[0].ckt == "1"
    assert austin.branches[1].ckt == "A1"
    assert austin.sink_buses == (90002,)
    assert austin.transfer_max_mw == 400.0
    assert isinstance(austin.branches, tuple)
    assert isinstance(austin.sink_buses, tuple)
    assert loaded.cities["MIDLAND"].sink_buses == (90022,)


def test_rule_duplicate_branch_any_orientation():
    def reversed_same_city(data):
        _austin(data)["branches"].append({"from_bus": 90002, "to_bus": 90001, "ckt": "1"})

    def other_city(data):
        data["cities"]["MIDLAND"]["branches"].append({"from_bus": 90001, "to_bus": 90002, "ckt": "1"})

    def other_city_reversed(data):
        data["cities"]["MIDLAND"]["branches"].append({"from_bus": 90002, "to_bus": 90001, "ckt": "1"})

    def same_twice(data):
        _austin(data)["branches"].append({"from_bus": 90001, "to_bus": 90002, "ckt": "1"})

    def parallel(data):
        _austin(data)["branches"].append({"from_bus": 90001, "to_bus": 90002, "ckt": "2"})

    for change in (reversed_same_city, other_city, other_city_reversed, same_twice):
        with pytest.raises(mapping.MappingError) as caught:
            mapping.parse_mapping(_edit(change), allow_placeholder=True)
        assert "already listed" in str(caught.value)
    loaded = mapping.parse_mapping(_edit(parallel), allow_placeholder=True)
    assert [b.ckt for b in loaded.cities["AUSTIN"].branches] == ["1", "2"]


def test_rule_unreadable_file_names_base_name_only(tmp_path):
    path = tmp_path / "secret_dir" / "city_map.json"
    with pytest.raises(mapping.MappingError) as caught:
        mapping.load_mapping(str(path), allow_placeholder=True)
    text = str(caught.value)
    assert "city_map.json" in text
    assert "secret_dir" not in text
    assert "FileNotFoundError" in text


def test_rule_sha256_is_the_parsed_bytes():
    data = _dump(_base())
    assert mapping.parse_mapping(data, allow_placeholder=True).sha256 == hashlib.sha256(data).hexdigest()
    with open(EXAMPLE, "rb") as handle:
        raw = handle.read()
    lf = raw.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    loaded_lf = mapping.parse_mapping(lf, allow_placeholder=True)
    loaded_crlf = mapping.parse_mapping(crlf, allow_placeholder=True)
    assert loaded_lf.sha256 == hashlib.sha256(lf).hexdigest()
    assert loaded_crlf.sha256 == hashlib.sha256(crlf).hexdigest()
    assert loaded_lf.sha256 != loaded_crlf.sha256
    assert loaded_lf.cities == loaded_crlf.cities


def test_rule_bom_is_accepted_and_hashed():
    data = b"\xef\xbb\xbf" + _dump(_base())
    loaded = mapping.parse_mapping(data, allow_placeholder=True)
    assert loaded.sha256 == hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------------------
# Study settings: stated defaults and validated overrides (Task 3)
# ---------------------------------------------------------------------------------------


def test_settings_defaults_pinned():
    d = settings.DEFAULT_SETTINGS
    assert len(settings.Settings._fields) == 22
    assert d.rate_sets == ("RATEA",)
    assert d.thermal_basis == "current"
    assert d.thermal_limit_pct == 100.0
    assert d.voltage_source == "config"
    assert d.base_low_pu == 0.95
    assert d.base_high_pu == 1.05
    assert d.contingency_low_pu == 0.90
    assert d.contingency_high_pu == 1.05
    assert d.min_monitor_kv == 100.0
    assert d.contingency_scope == "neighbourhood"
    assert d.contingency_hops == 2
    assert d.contingency_max == 200
    assert d.contingency_extra == ()
    assert d.transfer_step_mw == 25.0
    assert d.transfer_max_mw == 1000.0
    assert d.transfer_extra_steps == 80
    assert d.transfer_tolerance_mw == 1.0
    assert d.transfer_min_rise_fraction == 0.01
    assert d.solve_options is None
    assert d.max_mismatch_mva == 1.0
    assert d.collapse_voltage_pu == 0.5
    assert d.max_runtime_seconds == 1500.0
    assert settings.Settings._fields == (
        "rate_sets", "thermal_basis", "thermal_limit_pct", "voltage_source", "base_low_pu",
        "base_high_pu", "contingency_low_pu", "contingency_high_pu", "min_monitor_kv",
        "contingency_scope", "contingency_hops", "contingency_max", "contingency_extra",
        "transfer_step_mw", "transfer_max_mw", "transfer_extra_steps", "transfer_tolerance_mw",
        "transfer_min_rise_fraction", "solve_options", "max_mismatch_mva", "collapse_voltage_pu",
        "max_runtime_seconds",
    )
    assert settings.parse_settings(None) == d
    assert settings.parse_settings({}) == d


_FULL_STUDY = {
    "rate_sets": ["RATEA", "RATEB"],
    "thermal": {"basis": "mva", "limit_pct": 95},
    "voltage": {
        "source": "case",
        "base_low_pu": 0.96,
        "base_high_pu": 1.04,
        "contingency_low_pu": 0.92,
        "contingency_high_pu": 1.06,
        "min_monitor_kv": 69,
    },
    "contingency": {
        "scope": "all",
        "hops": 3,
        "max": 300,
        "extra": [{"from_bus": 90001, "to_bus": 90003, "ckt": "2"}],
    },
    "transfer": {
        "step_mw": 50,
        "max_mw": 2000,
        "extra_steps": 10,
        "tolerance_mw": 2,
        "min_rise_fraction": 0.05,
    },
    "solve": {"options": [0, 0, 0, 0, 0, 0, 0, 1], "max_mismatch_mva": 0.5, "collapse_voltage_pu": 0.6},
    "max_runtime_seconds": 1200,
}


def test_settings_overrides_parse():
    got = settings.parse_settings(copy.deepcopy(_FULL_STUDY))
    assert got.rate_sets == ("RATEA", "RATEB")
    assert got.thermal_basis == "mva"
    assert got.thermal_limit_pct == 95.0
    assert got.voltage_source == "case"
    assert (got.base_low_pu, got.base_high_pu) == (0.96, 1.04)
    assert (got.contingency_low_pu, got.contingency_high_pu) == (0.92, 1.06)
    assert got.min_monitor_kv == 69.0
    assert got.contingency_scope == "all"
    assert got.contingency_hops == 3
    assert got.contingency_max == 300
    assert got.contingency_extra == (settings.BranchRef(90001, 90003, "2"),)
    assert got.transfer_step_mw == 50.0
    assert got.transfer_max_mw == 2000.0
    assert got.transfer_extra_steps == 10
    assert got.transfer_tolerance_mw == 2.0
    assert got.transfer_min_rise_fraction == 0.05
    assert got.solve_options == (0, 0, 0, 0, 0, 0, 0, 1)
    assert isinstance(got.solve_options, tuple)
    assert got.max_mismatch_mva == 0.5
    assert got.collapse_voltage_pu == 0.6
    assert got.max_runtime_seconds == 1200.0
    for field in settings.Settings._fields:
        assert getattr(got, field) != getattr(settings.DEFAULT_SETTINGS, field), field


def test_settings_partial_override_keeps_other_defaults():
    got = settings.parse_settings({"contingency": {"hops": 1}})
    assert got.contingency_hops == 1
    assert got._replace(contingency_hops=2) == settings.DEFAULT_SETTINGS
    explicit_null = settings.parse_settings({"solve": {"options": None}})
    assert explicit_null == settings.DEFAULT_SETTINGS


def test_settings_branchref_key_and_orientation():
    ref = settings.BranchRef(90002, 90001, "1")
    assert ref.key == "90002-90001-1"
    assert ref.normalised() == (90001, 90002, "1")
    assert settings.BranchRef(90001, 90002, "1").normalised() == ref.normalised()


_BAD_OVERRIDES = [
    ("extra_steps_negative", {"transfer": {"extra_steps": -1}}, "study.transfer.extra_steps"),
    ("extra_steps_float", {"transfer": {"extra_steps": 1.5}}, "study.transfer.extra_steps"),
    ("rate_set_unknown", {"rate_sets": ["RATED"]}, "study.rate_sets[0]"),
    ("rate_set_duplicate", {"rate_sets": ["RATEA", "RATEA"]}, "listed twice"),
    ("rate_sets_empty", {"rate_sets": []}, "study.rate_sets"),
    ("rate_sets_text", {"rate_sets": "RATEA"}, "study.rate_sets"),
    ("thermal_basis_amps", {"thermal": {"basis": "amps"}}, "study.thermal.basis"),
    ("thermal_limit_zero", {"thermal": {"limit_pct": 0}}, "study.thermal.limit_pct"),
    ("thermal_limit_250", {"thermal": {"limit_pct": 250}}, "study.thermal.limit_pct"),
    ("thermal_unknown_key", {"thermal": {"colour": 1}}, "study.thermal.colour: unknown key"),
    ("voltage_source_bus", {"voltage": {"source": "bus"}}, "study.voltage.source"),
    ("base_low_above_high", {"voltage": {"base_low_pu": 1.10}}, "base_low_pu: must be below"),
    (
        "contingency_low_above_high",
        {"voltage": {"contingency_low_pu": 1.10}},
        "contingency_low_pu: must be below",
    ),
    ("pu_band_two", {"voltage": {"base_high_pu": 2.0}}, "study.voltage.base_high_pu"),
    ("pu_bool", {"voltage": {"base_low_pu": True}}, "study.voltage.base_low_pu"),
    ("min_kv_negative", {"voltage": {"min_monitor_kv": -1}}, "study.voltage.min_monitor_kv"),
    ("scope_region", {"contingency": {"scope": "region"}}, "study.contingency.scope"),
    ("hops_six", {"contingency": {"hops": 6}}, "study.contingency.hops"),
    ("hops_float", {"contingency": {"hops": 1.5}}, "study.contingency.hops"),
    ("max_zero", {"contingency": {"max": 0}}, "study.contingency.max"),
    ("max_large", {"contingency": {"max": 1001}}, "study.contingency.max"),
    (
        "extra_bad_bus",
        {"contingency": {"extra": [{"from_bus": 0, "to_bus": 2, "ckt": "1"}]}},
        "study.contingency.extra[0].from_bus",
    ),
    (
        "extra_duplicate",
        {
            "contingency": {
                "extra": [
                    {"from_bus": 1, "to_bus": 2, "ckt": "1"},
                    {"from_bus": 2, "to_bus": 1, "ckt": "1"},
                ]
            }
        },
        "listed twice",
    ),
    ("step_zero", {"transfer": {"step_mw": 0}}, "study.transfer.step_mw"),
    ("max_below_step", {"transfer": {"max_mw": 10}}, "study.transfer.max_mw"),
    ("tolerance_not_below_step", {"transfer": {"tolerance_mw": 30}}, "study.transfer.tolerance_mw"),
    ("min_rise_one", {"transfer": {"min_rise_fraction": 1}}, "study.transfer.min_rise_fraction"),
    ("options_seven", {"solve": {"options": [1] * 7}}, "study.solve.options"),
    ("options_bool", {"solve": {"options": [True] * 8}}, "study.solve.options"),
    ("mismatch_zero", {"solve": {"max_mismatch_mva": 0}}, "study.solve.max_mismatch_mva"),
    ("collapse_one", {"solve": {"collapse_voltage_pu": 1}}, "study.solve.collapse_voltage_pu"),
    (
        "collapse_above_criterion",
        {"solve": {"collapse_voltage_pu": 0.95}},
        "collapse_voltage_pu: must be below",
    ),
    ("runtime_zero", {"max_runtime_seconds": 0}, "study.max_runtime_seconds"),
    ("runtime_4000", {"max_runtime_seconds": 4000}, "study.max_runtime_seconds"),
    ("study_not_object", [], "study: must be an object"),
    ("top_unknown_key", {"colour": 1}, "study.colour: unknown key"),
]


def test_settings_case_count_is_36():
    assert len(_BAD_OVERRIDES) == 36
    assert len(set(item[0] for item in _BAD_OVERRIDES)) == 36


@pytest.mark.parametrize(
    "study,fragment",
    [(item[1], item[2]) for item in _BAD_OVERRIDES],
    ids=[item[0] for item in _BAD_OVERRIDES],
)
def test_settings_rejects_bad_overrides(study, fragment):
    with pytest.raises(settings.SettingsError) as caught:
        settings.parse_settings(copy.deepcopy(study))
    assert fragment in str(caught.value)
    assert caught.value.problems


def test_settings_reports_every_problem_at_once():
    with pytest.raises(settings.SettingsError) as caught:
        settings.parse_settings(
            {"thermal": {"basis": "amps"}, "voltage": {"source": "bus"}, "colour": 1}
        )
    assert len(caught.value.problems) == 3


def test_settings_nan_and_infinity_are_refused():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(settings.SettingsError):
            settings.parse_settings({"thermal": {"limit_pct": bad}})
        with pytest.raises(settings.SettingsError):
            settings.parse_settings({"max_runtime_seconds": bad})


def test_settings_errors_surface_in_mapping():
    def bad_study(data):
        data["study"] = {"thermal": {"colour": 1}}

    with pytest.raises(mapping.MappingError) as caught:
        mapping.parse_mapping(_edit(bad_study), allow_placeholder=True)
    assert caught.value.problems
    assert all(problem.startswith("study: ") for problem in caught.value.problems)
    assert "study.thermal.colour" in str(caught.value)

    def both(data):
        data["study"] = {"max_runtime_seconds": 0}
        data["schema_version"] = 2

    with pytest.raises(mapping.MappingError) as caught:
        mapping.parse_mapping(_edit(both), allow_placeholder=True)
    assert len(caught.value.problems) == 2

    def good_study(data):
        data["study"] = copy.deepcopy(_FULL_STUDY)

    data = _edit(good_study)
    loaded = mapping.parse_mapping(data, allow_placeholder=True)
    assert loaded.settings == settings.parse_settings(copy.deepcopy(_FULL_STUDY))
    assert loaded.sha256 == hashlib.sha256(data).hexdigest()
    assert loaded.sha256 != mapping.load_mapping(EXAMPLE, allow_placeholder=True).sha256


def test_settings_rate_set_label():
    assert settings.rate_set_label(settings.DEFAULT_SETTINGS) == "RATEA"
    got = settings.parse_settings({"rate_sets": ["RATEA", "RATEB"]})
    assert settings.rate_set_label(got) == "RATEA+RATEB"
