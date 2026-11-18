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
import socket

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import constants, contract, run_record  # noqa: E402
from pandapower_job import engine  # noqa: E402


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
