"""
Tests of the pandapower engine entry point (pandapower-solver Phase 2, plan 02-04: ENG-02, ENG-05,
ENG-06 in-memory tier).

Every input is a synthetic RAW file generated at test time from pandapower's own 39-bus case with
the bus numbers offset by 90000 (`pandapower_study_fixture`), and the placeholder mapping written
beside it, into tmp_path only. The ratings come from `psse_fakes` rows, so no live data is read; the
study is run on the real solver with sockets blocked. Failure messages are counts and reason words
only.
"""

import datetime
import json
import os
import re
import socket

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import constants, contract, mapping as mapping_module, run_record, study  # noqa: E402
from pandapower_job import api as pandapower_api, engine  # noqa: E402

_FNSL_OPTIONS = [0, 0, 0, 0, 0, 0, 0, 0]


@pytest.fixture(scope="module")
def four_city_run(tmp_path_factory):
    """One full four-city study (about 36 s) on the fixture, sockets blocked, temp dir watched."""
    root = tmp_path_factory.mktemp("engine_run")
    case_path = study_fixture.write_case(root)
    mapping_path = study_fixture.write_placeholder_mapping(root)
    scratch = root / "scratch"
    scratch.mkdir()
    case_hash_before = run_record.file_sha256(case_path)
    selection = study_fixture.selection()

    def blocked(*args, **kwargs):
        raise OSError("network blocked in this test")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("tempfile.tempdir", str(scratch))
        patch.setattr(socket.socket, "connect", blocked)
        patch.setattr(socket, "create_connection", blocked)
        prepared = engine.prepare_run(engine.PLACEHOLDER_BACKEND, case_path, mapping_path,
                                      allow_placeholder=True)
        results = prepared.study(selection, None)
    return {"prepared": prepared, "results": results, "case_path": case_path,
            "mapping_path": mapping_path, "scratch": scratch, "selection": selection,
            "case_hash_before": case_hash_before}


def test_tracer_four_cities_in_memory(four_city_run):
    prepared = four_city_run["prepared"]
    results = four_city_run["results"]
    selection = four_city_run["selection"]
    case_path = four_city_run["case_path"]

    assert prepared.mapping_error is None
    assert prepared.case_sha256 == run_record.file_sha256(case_path)
    assert run_record.file_sha256(case_path) == four_city_run["case_hash_before"]
    assert prepared.mapping_sha256 == run_record.file_sha256(four_city_run["mapping_path"])

    assert isinstance(results, contract.StudyResults)
    assert [row["city"] for row in results.dispatch] == list(constants.CITIES)
    assert [row["city"] for row in results.margins] == list(constants.CITIES)
    assert results.n_contingencies > 0
    assert run_record.validate_results(results, selection) is None
    assert results.psse_version is None

    for row in results.dispatch:
        record = row["details"]["solve_settings"]
        assert tuple(record) == engine.SETTINGS_RECORD_KEYS
        assert record["solver"] == "pandapower"
        assert record["solver_version"] == pandapower.__version__
        assert record["placeholder"] is True
        assert record["enforce_q_lims"] is False
        assert record["tolerance_mva"] == engine.PLACEHOLDER_SOLVE.tolerance_mva
        assert record["max_iteration"] == engine.PLACEHOLDER_SOLVE.max_iteration
        assert record["collapse_voltage_pu"] == 0.5
        assert record["scaling_details"] == {
            "swing_in_total": "yes", "clamped_at_limits": "no", "q_scales_with_p": "yes"}
        assert all(value == engine.PLACEHOLDER_NOTE for value in record["sources"].values())

    for table in (results.dispatch, results.margins, results.contingencies):
        for row in table:
            json.dumps(row, allow_nan=False)

    started = datetime.datetime(2026, 10, 28, 12, 20, tzinfo=datetime.timezone.utc)
    finished = started + datetime.timedelta(minutes=1)
    context = contract.RunContext(
        run_record.new_run_id(started), started, prepared.case_id, prepared.case_sha256,
        prepared.mapping_sha256, "test-version")
    record = run_record.build_run_record(context, selection, finished, results)
    rows = run_record.result_rows(record, results)
    assert len(rows[contract.DISPATCH_TABLE]) == 4
    assert len(rows[contract.MARGIN_TABLE]) == 4
    assert len(rows[contract.CONTINGENCY_TABLE]) == len(results.contingencies)

    assert os.listdir(str(four_city_run["scratch"])) == []


# -- Task 2: refusals at stage mapping ----------------------------------------------------------


def _prepared(tmp_path, study_section=None, backend=None):
    case_path = study_fixture.write_case(tmp_path)
    mapping_path = study_fixture.write_placeholder_mapping(tmp_path, study=study_section)
    backend = engine.PLACEHOLDER_BACKEND if backend is None else backend
    prepared = engine.prepare_run(backend, case_path, mapping_path, allow_placeholder=True)
    return prepared, case_path, mapping_path


def _failure(prepared):
    with pytest.raises(study.StudyFailed) as raised:
        prepared.study(study_fixture.selection(), None)
    return raised.value


def _counting_factory(patch):
    calls = []

    def factory(backend, protected_path=None):
        calls.append(1)
        raise AssertionError("an adapter must not be built")

    patch.setitem(study.API_FACTORIES, "pandapower", factory)
    return calls


def test_preflight_refuses_mva_basis(tmp_path):
    prepared, _, _ = _prepared(tmp_path, {"thermal": {"basis": "mva"}})
    failure = _failure(prepared)
    assert failure.stage == "mapping"
    assert failure.message.startswith("pandapower: ")
    assert "thermal basis" in failure.message


def test_preflight_refuses_fnsl_options(tmp_path):
    prepared, _, _ = _prepared(tmp_path, {"solve": {"options": _FNSL_OPTIONS}})
    failure = _failure(prepared)
    assert failure.stage == "mapping"
    assert failure.message.startswith("pandapower: ")
    assert "solve.options" in failure.message


def test_preflight_refuses_case_voltage_source(tmp_path):
    prepared, _, _ = _prepared(tmp_path, {"voltage": {"source": "case"}})
    failure = _failure(prepared)
    assert failure.stage == "mapping"
    assert failure.message.startswith("pandapower: ")
    assert "voltage.source" in failure.message


def test_preflight_refuses_undecided_reactive_limits(tmp_path):
    backend = study_fixture.fixture_backend(enforce_q_lims=None)
    prepared, _, _ = _prepared(tmp_path, backend=backend)
    failure = _failure(prepared)
    assert failure.stage == "mapping"
    assert failure.message.startswith("pandapower: ")
    assert "reactive-limit setting is undecided" in failure.message


@pytest.mark.parametrize("study_section, backend", [
    ({"thermal": {"basis": "mva"}}, None),
    ({"solve": {"options": _FNSL_OPTIONS}}, None),
    ({"voltage": {"source": "case"}}, None),
    (None, study_fixture.fixture_backend(enforce_q_lims=None)),
])
def test_preflight_refusal_builds_no_adapter_and_keeps_the_hash(
        tmp_path, monkeypatch, study_section, backend):
    calls = _counting_factory(monkeypatch)
    prepared, case_path, mapping_path = _prepared(tmp_path, study_section, backend)
    failure = _failure(prepared)
    assert failure.stage == "mapping"
    assert calls == []
    assert prepared.mapping_sha256 == run_record.file_sha256(mapping_path)
    assert prepared.mapping_error is None
    assert prepared.case_sha256 == run_record.file_sha256(case_path)


def test_unreadable_mapping_is_not_loaded(tmp_path, monkeypatch):
    calls = _counting_factory(monkeypatch)
    case_path = study_fixture.write_case(tmp_path)
    prepared = engine.prepare_run(engine.PLACEHOLDER_BACKEND, case_path,
                                  os.path.join(str(tmp_path), "no_such_mapping.json"),
                                  allow_placeholder=True)
    failure = _failure(prepared)
    assert failure.stage == "mapping"
    assert prepared.mapping_sha256 is None
    assert prepared.mapping_error
    assert calls == []


def test_preflight_accepts_defaults_and_several_rate_sets(tmp_path):
    for section in ({}, {"rate_sets": ["RATEA", "RATEB"]}):
        mapping_path = study_fixture.write_placeholder_mapping(tmp_path, study=section)
        loaded = mapping_module.load_mapping(mapping_path, allow_placeholder=True)
        assert engine.preflight(loaded.settings, engine.PLACEHOLDER_BACKEND) is None


def test_preflight_messages_are_figure_free(tmp_path):
    texts = study_fixture.synthetic_target_texts(study_fixture.fixture_records())
    cases = [({"thermal": {"basis": "mva"}}, engine.PLACEHOLDER_BACKEND),
             ({"solve": {"options": _FNSL_OPTIONS}}, engine.PLACEHOLDER_BACKEND),
             ({"voltage": {"source": "case"}}, engine.PLACEHOLDER_BACKEND),
             ({}, study_fixture.fixture_backend(enforce_q_lims=None))]
    reasons = []
    for section, backend in cases:
        mapping_path = study_fixture.write_placeholder_mapping(tmp_path, study=section)
        loaded = mapping_module.load_mapping(mapping_path, allow_placeholder=True)
        reason = engine.preflight(loaded.settings, backend)
        assert reason
        reasons.append(reason)
    assert len(set(reasons)) == 4
    for reason in reasons:
        assert "\n" not in reason
        assert not any(text in reason for text in texts)
        assert re.search(r"\d{5}", reason) is None


def test_prepare_run_needs_a_pandapower_backend(tmp_path):
    case_path = study_fixture.write_case(tmp_path)
    mapping_path = study_fixture.write_placeholder_mapping(tmp_path)
    with pytest.raises(TypeError):
        engine.prepare_run(object(), case_path, mapping_path, allow_placeholder=True)
