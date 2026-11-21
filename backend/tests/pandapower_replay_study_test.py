"""
Real-solver tests of the replay (pandapower-solver Phase 4, plan 04-03: AGR-01 and AGR-02).

The "recorded PSS/E run" here is a stand-in built from the public 39-bus fixture on the real
solver. These tests prove the wiring and the failure detection of the replay, never that PSS/E and
pandapower agree: nothing here reads a PSS/E result. Every file that looks private lives in a
throwaway repository under tmp_path.
"""

import pytest

pytest.importorskip("pandapower")

import pandapower_replay_fixture as fixture  # noqa: E402
from pandapower_job import replay  # noqa: E402


@pytest.fixture(scope="module")
def default_standin(tmp_path_factory):
    return fixture.standin(tmp_path_factory.mktemp("standin_default"), stress=False)


def _repo(tmp_path):
    return fixture.make_repo(tmp_path / "repo")


def test_tracer_self_replay_passes_on_the_real_solver(tmp_path, default_standin):
    stand = default_standin
    repo = _repo(tmp_path)
    snapshot = fixture.ingest_standins(repo, [stand])

    result = replay.replay_snapshot(
        snapshot, stand.backend, stand.network_path, stand.mapping_path, stand.case_sha256)

    summary = result.gate.summary
    assert result.gate.word == "pass"
    assert summary.runs_replayed == 1
    assert summary.runs_in_snapshot == 1
    assert summary.nonempty["voltage_high"] > 0
    assert summary.nonempty["non_convergence"] > 0
    assert set(summary.not_exercised) == {"thermal_overload", "voltage_low"}
    assert result.gate.detail.largest is not None
    assert result.gate.detail.largest.utilisation == 0
