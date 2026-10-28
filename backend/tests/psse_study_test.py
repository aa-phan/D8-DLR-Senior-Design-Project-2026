"""
Tests for the base of the real PSS/E study (pss-e-integration Phase 2, plan 02-03): IN-02
(the mapping is checked against the case before anything is written), IN-03 (each city's
selected rating reaches PSS/E as read-back per-circuit MVA at the branch's base kV) and STU-01
(a base load flow that is not genuinely solved is a failed run), all at the study level against
the fake psspy.

Follows backend/tests/psse_contract_test.py's conventions (module-level imports, plain
asserts, no test classes, no network). Honest scope: the fake proves call order, value
flow and failure handling, not that real PSS/E accepts these calls (the Phase 3 probe does).
"""

import datetime
import os
import sys

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
import psse_fakes  # noqa: E402
from psse_job import constants, contract, mapping, psse_api, ratings, run_record, settings, study, units  # noqa: E402

EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
NOW = datetime.datetime(2026, 10, 28, 12, 20, 0, tzinfo=datetime.timezone.utc)
AUSTIN_REF = settings.BranchRef(90001, 90002, "1")


def _registered(tmp_path, case=None, solver=None, fake=None):
    """(fake, case path): the case registered under a path whose file holds a marker."""
    fake = fake_module.FakePsspy(solver=solver) if fake is None else fake
    path = str(tmp_path / "PLACEHOLDER_CASE.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(path, fake_module.placeholder_case() if case is None else case)
    return fake, path


def _mapping(cities=None, **changes):
    """The example mapping (placeholder allowed); `cities` maps a city to CityMapping field
    replacements and `changes` replace study settings."""
    loaded = mapping.load_mapping(EXAMPLE, allow_placeholder=True)
    table = dict(loaded.cities)
    for city, fields in (cities or {}).items():
        table[city] = table[city]._replace(**fields)
    return loaded._replace(cities=table, settings=loaded.settings._replace(**changes))


def _selection(provisional=True):
    rows = psse_fakes.latest_rows(NOW, provisional=provisional)
    return ratings.select_ratings(psse_fakes.fake_fetch(rows), NOW)


def _writes(fake):
    """The recorded calls that change the case, solve it or save it."""
    return [call for call in fake.fake_calls
            if call[0] in ("branch_chng_3", "fnsl", "save", "bsys", "scal_2")]


def test_tracer_base_on_placeholder_case(tmp_path):
    fake, path = _registered(tmp_path)
    before = run_record.file_sha256(path)
    base = study.prepare_base(fake, path, _mapping(), _selection(provisional=True))
    try:
        austin = base.cities["AUSTIN"]
        assert austin.line_voltage_kv == 345.0
        expected = units.circuit_mva(1825.0, 2, 345.0)
        assert austin.applied_mva == expected
        assert round(austin.applied_mva, 1) == 2181.1
        assert fake.fake_state.branch(90001, 90002, "1")["rates"][0] == expected
        assert austin.rate_before_mva == (1500.0,)
        assert list(base.cities) == list(constants.CITIES)
        assert base.solve.converged is True
        assert base.rate_set == "RATEA"
        assert base.psse_version == "35.6.0"
        assert base.case_label == "PLACEHOLDER_CASE.sav"
        assert os.path.dirname(base.saved_path) == base.temp_dir
        assert os.path.normcase(base.saved_path) != os.path.normcase(path)
        assert fake.fake_saved_paths == [base.saved_path]
        assert os.path.isfile(base.saved_path)
    finally:
        study.cleanup_base(base)
    assert not os.path.exists(base.temp_dir)
    assert run_record.file_sha256(path) == before
