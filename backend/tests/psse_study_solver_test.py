"""
Tests for the solver seam of the real study (pandapower-solver Phase 2, plan 02-01, ENG-01, D-02):
the study entry points take a last keyword `solver` (default "psse"), resolved by name through
study.API_FACTORIES, so a second solver package can register its adapter without psse_job ever
naming or importing it.

All at the study level against the fake psspy; no second solver is needed here. Follows
backend/tests/psse_study_test.py's conventions (module-level imports, plain asserts, no test
classes, no network).
"""

import datetime
import inspect
import os
import re
import sys
import tempfile

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
import psse_fakes  # noqa: E402
from psse_job import constants, contract, psse_api, ratings, study  # noqa: E402

EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
NOW = datetime.datetime(2026, 10, 28, 12, 20, 0, tzinfo=datetime.timezone.utc)


def _registered(tmp_path, name="PLACEHOLDER_CASE.sav"):
    """(fake, case path): the placeholder case registered under a path whose file holds a marker."""
    fake = fake_module.FakePsspy()
    path = str(tmp_path / name)
    with open(path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(path, fake_module.placeholder_case())
    return fake, path


def _selection():
    return ratings.select_ratings(psse_fakes.fake_fetch(psse_fakes.latest_rows(NOW, provisional=True)), NOW)


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _recording_factory(calls):
    def factory(backend, case_path):
        calls.append((backend, case_path))
        return psse_api.PsseApi(backend, protected_path=case_path)
    return factory


def test_tracer_registered_solver_runs_the_whole_study(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setitem(study.API_FACTORIES, "recording_psse", _recording_factory(calls))
    first_dir = tmp_path / "a"
    second_dir = tmp_path / "b"
    first_dir.mkdir()
    second_dir.mkdir()
    fake_a, path_a = _registered(first_dir)
    fake_b, path_b = _registered(second_dir)
    selection = _selection()

    chosen = study.prepare_run(
        fake_a, path_a, EXAMPLE, allow_placeholder=True, solver="recording_psse"
    ).study(selection, None)
    default = study.prepare_run(fake_b, path_b, EXAMPLE, allow_placeholder=True).study(selection, None)

    assert len(calls) == 1
    assert calls[0][0] is fake_a and calls[0][1] == path_a
    for result in (chosen, default):
        assert isinstance(result, contract.StudyResults)
        assert [row["city"] for row in result.dispatch] == list(constants.CITIES)
        assert len(result.dispatch) == 4
    assert chosen.dispatch == default.dispatch
    assert chosen.margins == default.margins
    assert chosen.contingencies == default.contingencies
    assert chosen.n_contingencies == default.n_contingencies
    assert chosen.rate_set == default.rate_set
    assert chosen.psse_version == default.psse_version
    assert chosen == default
