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
from psse_job import settings as settings_module  # noqa: E402
from pandapower_job import api as pandapower_api, cli, engine, scaling, solve  # noqa: E402

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
        run_record.new_run_id(started, engine.SOLVER), started, prepared.case_id,
        prepared.case_sha256, prepared.mapping_sha256, "test-version", solver=engine.SOLVER)
    record = run_record.build_run_record(context, selection, finished, results)
    assert results.solver == engine.SOLVER
    assert results.solver_version == pandapower.__version__
    assert list(record) == list(contract.TAGGED_RUN_COLUMNS)
    assert record["solver"] == "pandapower"
    assert record["solver_version"] == pandapower.__version__
    assert record["run_id"].startswith("pp-")
    assert record["psse_version"] is None
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


# -- Task 3: recorded settings drop in, fail closed ---------------------------------------------

_SOURCES = {"enforce_q_lims": "recorded session", "tolerance_mva": "recorded session",
            "max_iteration": "recorded session", "collapse_voltage_pu": "mapping"}


def _settings_doc(enforce=True, tolerance=1e-6, iterations=25, collapse=0.5, sources=None,
                  deviations=()):
    values = solve.SolveSettings(enforce, tolerance, iterations, collapse,
                                 dict(_SOURCES if sources is None else sources), deviations)
    return cli._settings_record(values)


def _scaling_doc(details=("yes", "no", "yes")):
    return {"swing_in_total": details[0], "clamped_at_limits": details[1],
            "q_scales_with_p": details[2], "evidence": {"swing": {"counted": 2}},
            "snapshots_wanted": 4, "snapshots_read": 4, cli.REPORT_MARKER: 1}


def _refusal(settings_record, scaling_record):
    with pytest.raises(engine.RecordsRefused) as raised:
        engine.backend_from_records(settings_record, scaling_record)
    assert str(raised.value) == "recorded settings refused: %s" % raised.value.reason
    assert raised.value.reason in engine.RECORD_REFUSAL_REASONS
    return raised.value.reason


def test_records_drop_in_and_are_not_placeholder():
    backend = engine.backend_from_records(_settings_doc(), _scaling_doc())
    assert isinstance(backend, pandapower_api.PandapowerBackend)
    assert backend.solve_settings.enforce_q_lims is True
    assert backend.solve_settings.tolerance_mva == 1e-6
    assert backend.solve_settings.max_iteration == 25
    assert backend.solve_settings.collapse_voltage_pu == 0.5
    assert backend.solve_settings.sources == _SOURCES
    assert backend.scaling_details.swing_in_total == "yes"
    assert engine.is_placeholder(backend) is False
    assert engine.is_placeholder(engine.PLACEHOLDER_BACKEND) is True
    record = engine.settings_record(backend, "3.5.6")
    assert tuple(record) == engine.SETTINGS_RECORD_KEYS
    assert record["placeholder"] is False
    assert record["solver_version"] == "3.5.6"
    assert record["enforce_q_lims"] is True
    assert record["tolerance_mva"] == 1e-6
    assert record["max_iteration"] == 25
    assert record["scaling_details"] == {
        "swing_in_total": "yes", "clamped_at_limits": "no", "q_scales_with_p": "yes"}


def test_records_keep_an_undecided_reactive_limit():
    backend = engine.backend_from_records(_settings_doc(enforce=None), _scaling_doc())
    assert backend.solve_settings.enforce_q_lims is None
    assert engine.settings_record(backend, "3.5.6")["enforce_q_lims"] is None
    reason = engine.preflight(settings_module.DEFAULT_SETTINGS, backend)
    assert reason is not None and "undecided" in reason


def test_records_accept_pandapower_default_iterations_only_with_its_source():
    sources = dict(_SOURCES, max_iteration="pandapower default")
    backend = engine.backend_from_records(
        _settings_doc(iterations="auto", sources=sources, deviations=["D-14 deviation"]),
        _scaling_doc())
    assert backend.solve_settings.max_iteration == "auto"
    assert backend.solve_settings.deviations == ("D-14 deviation",)
    assert _refusal(_settings_doc(iterations="auto"), _scaling_doc()) == "bad_value"
    assert _refusal(_settings_doc(iterations="25", sources=sources), _scaling_doc()) == "bad_value"


def test_records_refusals():
    good = _settings_doc()
    scale = _scaling_doc()

    assert _refusal({"refused": "var_limit_conflict"}, scale) == "settings_refused"
    assert _refusal([], scale) == "not_a_dict"
    assert _refusal(good, []) == "not_a_dict"
    assert _refusal(None, scale) == "not_a_dict"

    missing = dict(good)
    del missing["tolerance_mva"]
    assert _refusal(missing, scale) == "missing_field"
    assert _refusal(dict(good, extra=1), scale) == "unknown_field"
    no_detail = dict(scale)
    del no_detail["swing_in_total"]
    assert _refusal(good, no_detail) == "missing_field"
    assert _refusal(good, dict(scale, extra=1)) == "unknown_field"

    for field, value in (
            ("tolerance_mva", 0), ("tolerance_mva", float("nan")), ("tolerance_mva", True),
            ("tolerance_mva", "1e-6"), ("tolerance_mva", -1e-6),
            ("max_iteration", 0), ("max_iteration", True), ("max_iteration", 2.5),
            ("collapse_voltage_pu", 1.5), ("collapse_voltage_pu", 0), ("collapse_voltage_pu", 1),
            ("collapse_voltage_pu", None), ("enforce_q_lims", "yes"), ("enforce_q_lims", 1),
            ("sources", ["a"]), ("sources", {"a": 1}), ("sources", {1: "a"}),
            ("deviations", "none"), ("deviations", [1]), ("deviations", ("a",))):
        assert _refusal(dict(good, **{field: value}), scale) == "bad_value", (field, repr(value))

    assert _refusal(dict(good, sources=dict(_SOURCES, tolerance_mva="placeholder: x")),
                    scale) == "placeholder_source"
    assert _refusal(dict(good, sources=dict(_SOURCES, tolerance_mva=" Placeholder")),
                    scale) == "placeholder_source"
    assert _refusal(good, dict(scale, evidence={"placeholder": True})) == "placeholder_source"

    for name in ("swing_in_total", "clamped_at_limits", "q_scales_with_p"):
        assert _refusal(good, dict(scale, **{name: "maybe"})) == "bad_detail"
        assert _refusal(good, dict(scale, **{name: None})) == "bad_detail"


def _dump(path, document):
    with open(str(path), "w", encoding="ascii") as handle:
        handle.write(json.dumps(document, sort_keys=True, allow_nan=False, indent=1) + "\n")


def _write_check(directory, settings=None, details=None):
    """The two files of a check directory in the shape the check command writes them."""
    _dump(directory / "report.json", {
        "stamp": "20260101T000000Z", "settings": _settings_doc() if settings is None else settings,
        cli.REPORT_MARKER: 1})
    _dump(directory / "scaling_details.json", _scaling_doc() if details is None else details)


def test_load_recorded_backend_reads_the_check_shape(tmp_path):
    _write_check(tmp_path)
    backend = engine.load_recorded_backend(str(tmp_path))
    assert backend == engine.backend_from_records(_settings_doc(), _scaling_doc())
    assert engine.is_placeholder(backend) is False
    assert engine.load_recorded_backend(tmp_path).solve_settings.tolerance_mva == 1e-6

    # a check that could not decide the reactive limits still loads (the preflight refuses it)
    _write_check(tmp_path, settings=_settings_doc(enforce=None))
    assert engine.load_recorded_backend(str(tmp_path)).solve_settings.enforce_q_lims is None


def test_load_recorded_backend_refusals(tmp_path):
    def refused(directory):
        with pytest.raises(engine.RecordsRefused) as raised:
            engine.load_recorded_backend(str(directory))
        text = str(raised.value)
        assert text == "recorded settings refused: %s" % raised.value.reason
        assert str(directory) not in text
        assert os.path.basename(str(directory)) not in text
        return raised.value.reason

    def fresh(name):
        directory = tmp_path / ("check_dir_" + name)
        directory.mkdir()
        _write_check(directory)
        return directory

    empty = tmp_path / "empty"
    empty.mkdir()
    assert refused(empty) == "unreadable"

    directory = fresh("only_report")
    os.remove(str(directory / "scaling_details.json"))
    assert refused(directory) == "unreadable"

    directory = fresh("big")
    with open(str(directory / "report.json"), "w", encoding="ascii") as handle:
        handle.write(" " * (engine.MAX_RECORD_BYTES + 1))
    assert refused(directory) == "too_large"

    for name, text in (("garbage", "not json"), ("nan", '{"a": NaN}'),
                       ("infinity", '{"a": -Infinity}'), ("duplicate", '{"a": 1, "a": 2}')):
        directory = fresh(name)
        with open(str(directory / "scaling_details.json"), "w", encoding="ascii") as handle:
            handle.write(text)
        assert refused(directory) == "not_json", name

    directory = fresh("not_a_dict")
    _dump(directory / "report.json", [1, 2])
    assert refused(directory) == "not_a_dict"

    directory = fresh("no_marker")
    _dump(directory / "report.json", {"settings": _settings_doc()})
    assert refused(directory) == "bad_marker"

    directory = fresh("bad_marker_value")
    _dump(directory / "report.json", {"settings": _settings_doc(), cli.REPORT_MARKER: True})
    assert refused(directory) == "bad_marker"

    directory = fresh("scaling_no_marker")
    document = _scaling_doc()
    del document[cli.REPORT_MARKER]
    _dump(directory / "scaling_details.json", document)
    assert refused(directory) == "bad_marker"

    directory = fresh("no_settings")
    _dump(directory / "report.json", {cli.REPORT_MARKER: 1})
    assert refused(directory) == "missing_field"

    directory = tmp_path / "phase1_refused"
    directory.mkdir()
    _write_check(directory, settings={"refused": "var_limit_conflict"})
    assert refused(directory) == "settings_refused"


def test_adapter_solves_with_the_backend_settings(tmp_path, monkeypatch):
    backend = engine.backend_from_records(
        _settings_doc(enforce=False, tolerance=1e-6, iterations=25), _scaling_doc())
    assert backend.solve_settings != engine.PLACEHOLDER_SOLVE
    seen = []
    real = solve.run_load_flow

    def recorder(net, settings, enforce_q_lims):
        seen.append((settings, enforce_q_lims))
        return real(net, settings, enforce_q_lims)

    monkeypatch.setattr(solve, "run_load_flow", recorder)
    adapter = pandapower_api.PandapowerApi(backend)
    adapter.load_case(study_fixture.write_case(tmp_path))
    result = adapter.solve()
    assert result.converged
    assert len(seen) == 1
    assert seen[0][0] is backend.solve_settings
    assert seen[0][1] is backend.solve_settings.enforce_q_lims


def test_placeholder_is_detectable():
    assert engine.is_placeholder(engine.PLACEHOLDER_BACKEND) is True
    assert engine.settings_record(engine.PLACEHOLDER_BACKEND, "3.5.6")["placeholder"] is True
    recorded = engine.backend_from_records(_settings_doc(), _scaling_doc())
    by_source = recorded._replace(solve_settings=recorded.solve_settings._replace(
        sources=dict(recorded.solve_settings.sources, tolerance_mva=engine.PLACEHOLDER_NOTE)))
    assert engine.is_placeholder(by_source) is True
    by_evidence = recorded._replace(scaling_details=scaling.ScalingDetails(
        "yes", "no", "yes", {"placeholder": True}))
    assert engine.is_placeholder(by_evidence) is True
    assert engine.is_placeholder(recorded) is False
    assert recorded.solve_settings.sources != engine.PLACEHOLDER_SOLVE.sources
