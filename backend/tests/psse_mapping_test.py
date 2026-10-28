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
