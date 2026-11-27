"""
Owner-local tests of the recorded PSE-02 settings (pandapower-solver Phase 2, plan 02-04: ENG-05).

These read the check output the Phase 1 check command wrote on the owner's machine under
`data/private/pandapower/sessions/<session>/check_<stamp>/` (or the folder named by the
environment variable DLR_PANDAPOWER_CHECK_DIR). When no such folder exists they skip with an
owner-local reason, as the private-data guard's owner-local test does; with
DLR_PANDAPOWER_REQUIRE_RECORDS set to "1" they fail instead, so plan 02-07 cannot pass on a
machine without the records. Assertion messages hold counts and reason words only, never a value
or a path.
"""

import glob
import os

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import constants, mapping as mapping_module, run_record, study  # noqa: E402
from pandapower_job import api as pandapower_api, engine  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NO_RECORDS = "owner-local check: no recorded PSE-02 check output on this machine"
_UNDECIDED = "recorded settings are undecided: owner decision needed (plan 02-07)"
_REFUSED_STAGES = ("mapping", "apply_ratings")


def _check_dir():
    """The check directory to load, or None: the environment's, else the newest on this machine."""
    named = os.environ.get("DLR_PANDAPOWER_CHECK_DIR")
    if named:
        return named if os.path.isdir(named) else None
    pattern = os.path.join(_REPO_ROOT, "data", "private", "pandapower", "sessions", "*", "check_*")
    found = sorted(path for path in glob.glob(pattern) if os.path.isdir(path))
    return found[-1] if found else None


def _need_records():
    directory = _check_dir()
    if directory is None:
        if os.environ.get("DLR_PANDAPOWER_REQUIRE_RECORDS") == "1":
            pytest.fail(_NO_RECORDS)
        pytest.skip(_NO_RECORDS)
    return directory


def _recorded_backend():
    try:
        return engine.load_recorded_backend(_need_records())
    except engine.RecordsRefused as problem:
        pytest.fail("recorded settings were refused: %s" % problem.reason)


def test_owner_local_recorded_backend_is_not_placeholder():
    backend = _recorded_backend()
    assert engine.is_placeholder(backend) is False
    print("recorded settings: %d sources, %d deviations" % (
        len(backend.solve_settings.sources), len(backend.solve_settings.deviations)))


def test_owner_local_recorded_settings_run_four_cities(tmp_path):
    backend = _recorded_backend()
    case_path = study_fixture.write_case(tmp_path)
    mapping_path = study_fixture.write_placeholder_mapping(tmp_path)
    selection = study_fixture.selection()
    prepared = engine.prepare_run(backend, case_path, mapping_path, allow_placeholder=True)

    undecided = backend.solve_settings.enforce_q_lims is None or any(
        getattr(backend.scaling_details, name) == "inconclusive"
        for name in ("swing_in_total", "clamped_at_limits", "q_scales_with_p"))
    if undecided:
        try:
            prepared.study(selection, None)
        except study.StudyFailed as refused:
            assert refused.stage in _REFUSED_STAGES, "stage %s" % refused.stage
        pytest.fail(_UNDECIDED)

    results = prepared.study(selection, None)
    assert run_record.validate_results(results, selection) is None
    loaded = mapping_module.load_mapping(mapping_path, allow_placeholder=True)
    expected = engine.settings_record(
        pandapower_api.PandapowerBackend(
            backend.solve_settings._replace(
                collapse_voltage_pu=loaded.settings.collapse_voltage_pu),
            backend.scaling_details),
        pandapower.__version__)
    assert expected["placeholder"] is False
    assert [row["city"] for row in results.dispatch] == list(constants.CITIES)
    mismatched = [row["city"] for row in results.dispatch
                  if row["details"]["solve_settings"] != expected]
    assert mismatched == [], "%d rows carry other settings" % len(mismatched)
