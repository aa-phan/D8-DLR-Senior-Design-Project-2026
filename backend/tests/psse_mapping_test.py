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

from psse_job import constants, mapping, run_record  # noqa: E402

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
