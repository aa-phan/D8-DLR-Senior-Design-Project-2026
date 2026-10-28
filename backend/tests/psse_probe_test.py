"""
Tests for the laptop probe (pss-e-integration Phase 2, plan 02-07): the TST-01 drift guard
that Phase 3 runs once against the real psspy. The probe compares every psse_api.SURFACE row
with the module it is given, exercises the adapter's calls on a case without changing that
case, and never raises for a probe failure. These tests run it against the fake psspy and
against deliberately broken variants of the fake.

Follows backend/tests/psse_contract_test.py's conventions (module-level imports, plain
asserts, no test classes, no network). Honest scope: against the fake the probe proves its own
logic only; whether the real psspy agrees with the SURFACE table is what Phase 3's run on the
licensed laptop shows.
"""

import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
from psse_job import mapping, probe, psse_api, run_record, settings  # noqa: E402

EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
AUSTIN_REF = settings.BranchRef(90001, 90002, "1")
READ_ONLY_CHECKS = (
    "version", "load_case", "branch_table", "bus_table", "column_alignment",
    "circuit_id_padding", "option_strings", "load_flow", "mapping",
)
WRITE_CHECKS = ("rating_write", "scale_load")


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _registered(tmp_path, fake=None, case=None):
    """(fake, case path): the placeholder case registered under a path whose file holds a marker."""
    fake = fake_module.FakePsspy() if fake is None else fake
    directory = tmp_path / "private_case_directory"
    directory.mkdir(exist_ok=True)
    path = str(directory / "PLACEHOLDER_CASE.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(path, fake_module.placeholder_case() if case is None else case)
    return fake, path


def _mapping(**cities):
    """The example mapping (placeholder allowed); `cities` maps a city to CityMapping replacements."""
    loaded = mapping.load_mapping(EXAMPLE, allow_placeholder=True)
    table = dict(loaded.cities)
    for city, fields in cities.items():
        table[city] = table[city]._replace(**fields)
    return loaded._replace(cities=table)


def _by_check(rows):
    return dict((row.check, row) for row in rows)


def _statuses(rows, names):
    table = _by_check(rows)
    return [(name, table[name].status if name in table else "MISSING") for name in names]


def _calls(fake, *names):
    return [call for call in fake.fake_calls if call[0] in names]


def test_tracer_probe_against_fake_all_pass(tmp_path):
    fake, path = _registered(tmp_path)
    before = run_record.file_sha256(path)
    rows = probe.run_probe(fake, path, mapping=_mapping(), write_check=True)
    failing = [(row.check, row.detail) for row in rows if row.status == "FAIL"]
    assert failing == []
    signature_rows = [row for row in rows if row.check.startswith("signature:")]
    assert len(signature_rows) == len(psse_api.SURFACE) == 19
    assert [row.check for row in signature_rows] == [
        "signature:" + surface.name for surface in psse_api.SURFACE]
    assert set(row.status for row in signature_rows) == {"PASS"}
    for name, status in _statuses(rows, READ_ONLY_CHECKS + WRITE_CHECKS):
        assert status == "PASS", name
    assert probe.probe_ok(rows) is True
    report = probe.format_report(rows)
    summary = report.splitlines()[-1]
    assert summary == "%d PASS, 0 FAIL, 0 SKIP" % len(rows)
    # The case is exactly as it was found: no save, same file, the original rating and load.
    assert _calls(fake, "save") == []
    assert fake.fake_saved_paths == []
    assert run_record.file_sha256(path) == before
    assert fake.fake_state.branch(90001, 90002, "1")["rates"][0] == 1500.0
    assert fake.fake_state.loads[90002][0] == 620.0
