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
import re
import sys
import tempfile
import types

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


# ──────────────────────────────────────────────────────────────────────────────
# Broken variants of the fake: each way the laptop's psspy could differ
# ──────────────────────────────────────────────────────────────────────────────


def _namespace(fake, remove=(), **replace):
    """A module-like object over the fake's bound SURFACE functions, with some removed or replaced."""
    members = dict((surface.name, getattr(fake, surface.name)) for surface in psse_api.SURFACE)
    for name in remove:
        del members[name]
    members.update(replace)
    return types.SimpleNamespace(**members)


class _RenamedParameterFake(fake_module.FakePsspy):
    def abrnint(self, sid, owner, ties, flag, entry, strings):
        return fake_module.FakePsspy.abrnint(self, sid, owner, ties, flag, entry, strings)


class _MisalignedRatingFake(fake_module.FakePsspy):
    def brndat(self, ibus, jbus, ickt, string):
        ierr, value = fake_module.FakePsspy.brndat(self, ibus, jbus, ickt, string)
        return (ierr, value + 1.0)


class _WriteIgnoredFake(fake_module.FakePsspy):
    def branch_chng_3(self, ibus, jbus, ckt, intgar, realar, ratings, namear):
        return 0


class _Uninspectable(object):
    """A callable whose signature inspect cannot produce (a bad __signature__)."""

    __signature__ = "not a signature"

    def __init__(self, function):
        self._function = function

    def __call__(self):
        return self._function()


def test_detects_renamed_parameter(tmp_path):
    fake, path = _registered(tmp_path, fake=_RenamedParameterFake())
    rows = _by_check(probe.run_probe(fake, path))
    assert rows["signature:abrnint"].status == "FAIL"
    assert "string" in rows["signature:abrnint"].detail
    assert rows["signature:abrnreal"].status == "PASS"
    assert probe.probe_ok(list(rows.values())) is False


def test_detects_missing_function(tmp_path):
    fake, path = _registered(tmp_path)
    module = _namespace(fake, remove=("branch_chng_3",))
    rows = _by_check(probe.run_probe(module, path, write_check=True))
    assert rows["signature:branch_chng_3"].status == "FAIL"
    assert rows["signature:branch_chng_3"].detail == "missing"
    assert rows["rating_write"].status == "FAIL"
    assert rows["signature:bsys"].status == "PASS"


def test_detects_uninspectable_signature_as_skip(tmp_path):
    fake, path = _registered(tmp_path)
    module = _namespace(fake, solved=_Uninspectable(fake.solved))
    rows = probe.run_probe(module, path)
    table = _by_check(rows)
    assert table["signature:solved"].status == "SKIP"
    assert "assumption A6" in table["signature:solved"].detail
    assert table["load_flow"].status == "PASS"
    assert probe.probe_ok(rows) is True
    assert probe.format_report(rows).splitlines()[-1] == "%d PASS, 0 FAIL, 1 SKIP" % (len(rows) - 1)


def test_detects_misaligned_columns(tmp_path):
    fake, path = _registered(tmp_path, fake=_MisalignedRatingFake())
    rows = _by_check(probe.run_probe(fake, path))
    assert rows["column_alignment"].status == "FAIL"
    assert "aligned" in rows["column_alignment"].detail
    assert rows["branch_table"].status == "PASS"


def test_detects_rating_not_read_back(tmp_path):
    fake, path = _registered(tmp_path, fake=_WriteIgnoredFake())
    rows = _by_check(probe.run_probe(fake, path, mapping=_mapping(), write_check=True))
    assert rows["rating_write"].status == "FAIL"
    assert "not read back" in rows["rating_write"].detail
    assert fake.fake_state.branch(90001, 90002, "1")["rates"][0] == 1500.0


def test_detects_non_converging_case(tmp_path):
    def stalled(case):
        return fake_module.SolveOutcome(ierr=0, solved=1)

    fake, path = _registered(tmp_path, fake=fake_module.FakePsspy(solver=stalled))
    rows = _by_check(probe.run_probe(fake, path))
    assert rows["load_flow"].status == "FAIL"
    assert "iteration limit exceeded" in rows["load_flow"].detail


def test_detects_mapping_problems(tmp_path):
    fake, path = _registered(tmp_path)
    missing = _mapping(AUSTIN={"branches": (settings.BranchRef(90001, 90099, "1"),)})
    rows = _by_check(probe.run_probe(fake, path, mapping=missing))
    assert rows["mapping"].status == "FAIL"
    assert "1 problem" in rows["mapping"].detail
    assert "90099" not in rows["mapping"].detail
    assert "90001-90099-1" not in rows["mapping"].detail
    shown = _by_check(probe.run_probe(fake, path, mapping=missing, show_identifiers=True))
    assert shown["mapping"].status == "FAIL"
    assert "90001-90099-1" in shown["mapping"].detail
    good = _by_check(probe.run_probe(fake, path, mapping=_mapping()))
    assert good["mapping"].status == "PASS"
    assert "0 problems" in good["mapping"].detail
    assert "AUSTIN 345 kV" in good["mapping"].detail


# ──────────────────────────────────────────────────────────────────────────────
# The report: safe to paste, never raises, writes only when asked
# ──────────────────────────────────────────────────────────────────────────────


def test_report_hides_identifiers_by_default(tmp_path):
    fake, path = _registered(tmp_path, fake=_MisalignedRatingFake())
    missing = _mapping(AUSTIN={"branches": (settings.BranchRef(90001, 90099, "1"),)})
    rows = probe.run_probe(fake, path, mapping=missing, write_check=True)
    report = probe.format_report(rows)
    assert "FAIL" in report
    assert re.search(r"\b\d{5,}\b", report) is None
    assert re.search(r"\d+-\d+-\w", report) is None
    assert "private_case_directory" not in report
    assert "PLACEHOLDER_CASE" not in report
    assert os.path.dirname(path) not in report
    revealed = probe.format_report(
        probe.run_probe(fake, path, mapping=missing, write_check=True, show_identifiers=True))
    assert "90001-90099-1" in revealed


def test_report_never_raises(tmp_path):
    def explode(*args, **kwargs):
        raise RuntimeError("secret bus 90001 in /private/path")

    module = types.SimpleNamespace(**dict(
        (surface.name, explode) for surface in psse_api.SURFACE))
    for target in (module, object(), None):
        rows = probe.run_probe(target, str(tmp_path / "missing.sav"), mapping=_mapping(),
                               write_check=True)
        assert len(rows) >= len(psse_api.SURFACE)
        assert probe.probe_ok(rows) is False
        report = probe.format_report(rows)
        assert "secret" not in report and "90001" not in report and "/private" not in report
        assert report.splitlines()[-1].endswith("SKIP")
    revealed = probe.format_report(
        probe.run_probe(module, str(tmp_path / "missing.sav"), show_identifiers=True))
    assert "secret bus" not in revealed  # the adapter never carries a psspy exception's text
    assert _by_check(probe.run_probe(module, "x"))["version"].status == "FAIL"


def test_report_write_check_off_by_default(tmp_path):
    fake, path = _registered(tmp_path)
    rows = probe.run_probe(fake, path, mapping=_mapping())
    assert _calls(fake, "branch_chng_3", "bsys", "scal_2", "save") == []
    assert "rating_write" not in _by_check(rows)
    assert "scale_load" not in _by_check(rows)
    probe.run_probe(fake, path, mapping=_mapping(), write_check=True)
    assert [call[0] for call in _calls(fake, "branch_chng_3", "bsys", "scal_2")] == [
        "branch_chng_3", "bsys", "scal_2"]
