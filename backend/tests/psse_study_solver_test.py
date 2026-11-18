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


def test_solver_defaults_to_psse_on_every_entry_point():
    for function in (study._open_case, study.index_case, study.prepare_base, study.make_study,
                     study.prepare_run):
        parameters = list(inspect.signature(function).parameters.values())
        assert parameters[-1].name == "solver", function.__name__
        assert parameters[-1].default == "psse", function.__name__


def _fails_at_load_case(tmp_path, solver):
    fake, path = _registered(tmp_path)
    prepared = study.prepare_run(fake, path, EXAMPLE, allow_placeholder=True, solver=solver)
    with pytest.raises(contract.StudyFailed) as caught:
        prepared.study(_selection(), None)
    assert caught.value.stage == "load_case"
    assert fake.fake_calls == []
    return caught.value.message


def test_unknown_solver_fails_at_load_case(tmp_path):
    message = _fails_at_load_case(tmp_path, "no_such_solver")
    assert "not registered" in message
    assert re.search(r"\b9[0-9]{4}\b", message) is None


def test_unregistered_name_fails_at_load_case(tmp_path, monkeypatch):
    monkeypatch.delitem(study.API_FACTORIES, "pandapower", raising=False)
    assert "not registered" in _fails_at_load_case(tmp_path, "pandapower")


def test_solver_must_be_given_by_name(tmp_path):
    assert "by name" in _fails_at_load_case(tmp_path, None)
    assert "by name" in _fails_at_load_case(tmp_path, ["psse"])


def test_factory_error_is_a_load_case_failure(tmp_path, monkeypatch):
    def factory(backend, case_path):
        raise ValueError("boom")

    monkeypatch.setitem(study.API_FACTORIES, "exploding", factory)
    fake, path = _registered(tmp_path)
    prepared = study.prepare_run(fake, path, EXAMPLE, allow_placeholder=True, solver="exploding")
    with pytest.raises(contract.StudyFailed) as caught:
        prepared.study(_selection(), None)
    assert caught.value.stage == "load_case"
    assert "boom" in caught.value.message


def test_register_solver_refuses_replacement(monkeypatch):
    monkeypatch.setattr(study, "API_FACTORIES", dict(study.API_FACTORIES))
    original = study.API_FACTORIES["psse"]

    def first(backend, case_path):
        return None

    def other(backend, case_path):
        return None

    study.register_solver("extra", first)
    assert study.API_FACTORIES["extra"] is first
    study.register_solver("extra", first)
    assert study.API_FACTORIES["extra"] is first
    for name in ("extra", "psse"):
        with pytest.raises(ValueError):
            study.register_solver(name, other)
    assert study.API_FACTORIES["extra"] is first
    assert study.API_FACTORIES["psse"] is original
    for name, factory in (("", first), (None, first), ("named", None), ("named", "not callable")):
        with pytest.raises(ValueError):
            study.register_solver(name, factory)
    assert "named" not in study.API_FACTORIES


def test_mapping_failure_never_builds_an_adapter(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setitem(study.API_FACTORIES, "recording_psse", _recording_factory(calls))
    fake, path = _registered(tmp_path)
    missing = str(tmp_path / "no_such_mapping.json")
    prepared = study.prepare_run(fake, path, missing, allow_placeholder=True, solver="recording_psse")
    with pytest.raises(contract.StudyFailed) as caught:
        prepared.study(_selection(), None)
    assert caught.value.stage == "mapping"
    assert calls == []
    assert fake.fake_calls == []
