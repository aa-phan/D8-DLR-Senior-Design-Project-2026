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


# -- the deliberate-mismatch matrix ----------------------------------------------------------------
#
# Two stand-ins are built once per module (default ratings, and every rating at 10 percent so
# thermal and rating-bound rows exist). Each case perturbs ONE recorded value of a copy of a stand-in's
# rows, sends the copy through an export file, the ingest and the loader, and replays it with a runner
# that returns the stand-in's own results: the real-solver self replay above shows the replay
# reproduces them exactly, and plan 02-05 proved two runs are equal, so the unperturbed side is what a
# fresh solve gives. The inside-tolerance side must pass with a non-zero deviation and the outside
# side must fail. A case that cannot reach its precondition fails with a message naming it.

import copy  # noqa: E402
import os  # noqa: E402

from pandapower_job import agree, compare  # noqa: E402
from psse_job import constants  # noqa: E402


@pytest.fixture(scope="module")
def stress_standin(tmp_path_factory):
    return fixture.standin(tmp_path_factory.mktemp("standin_stress"), stress=True)


def _gate(tmp_path, stand, mutate=None, recount=True, results=None, mapping=None, session=None,
          real=False):
    """The replay of one perturbed copy of `stand`; returns the ReplayResult."""
    repo = fixture.make_repo(tmp_path / "repo")
    snapshot = fixture.perturbed_snapshot(repo, stand, mutate or (lambda bundle: None), recount)
    given = stand.results if results is None else results
    runner = None if real else (lambda selection: given)
    return replay.replay_snapshot(
        snapshot, stand.backend, stand.network_path, mapping or stand.mapping_path,
        session or stand.case_sha256, runner=runner)


def _checks(result):
    return set(found.check for _, found in result.gate.detail.findings)


def _need(condition, precondition):
    assert condition, "precondition not reached: " + precondition


def _rows(bundle, kind):
    return sorted((row for row in bundle["contingencies"] if row["violation_kind"] == kind),
                  key=lambda row: row["exceeded_by"])


def _largest(bundle, kind):
    return _rows(bundle, kind)[-1]


def _by_city(bundle, table, city):
    return next(row for row in bundle[table] if row["city"] == city)


@pytest.mark.parametrize("which", ["default", "stress"])
def test_mismatch_self_replay_passes_for_both_stand_ins(tmp_path, which, default_standin,
                                                        stress_standin):
    stand = default_standin if which == "default" else stress_standin
    result = _gate(tmp_path, stand)
    assert result.gate.word == "pass"
    assert result.gate.detail.largest.utilisation == 0
    if which == "stress":
        assert result.gate.summary.nonempty["thermal_overload"] > 0
        assert "thermal_overload" not in result.gate.summary.not_exercised


def _scale_observed(amount, kind, additive):
    def change(bundle):
        row = _largest(bundle, kind)
        row["observed_value"] = (row["observed_value"] + amount if additive
                                 else row["observed_value"] * amount)
    return change


def test_mismatch_thermal_value_one_percent_passes_three_percent_fails(tmp_path, stress_standin):
    row = _largest(stress_standin.bundle, "thermal_overload")
    observed = row["observed_value"]
    _need(compare.within_flow(observed * 1.01, observed), "1 percent inside the flow allowance")
    _need(not compare.within_flow(observed * 1.03, observed), "3 percent outside the flow allowance")
    inside = _gate(tmp_path / "in", stress_standin, _scale_observed(1.01, "thermal_overload", False))
    assert inside.gate.word == "pass"
    assert 0 < inside.gate.detail.worst["thermal_mva"].utilisation < 1
    outside = _gate(tmp_path / "out", stress_standin, _scale_observed(1.03, "thermal_overload", False))
    assert outside.gate.word == "fail" and "value_thermal" in _checks(outside)


def test_mismatch_voltage_value_half_band_passes_double_band_fails(tmp_path, default_standin):
    inside = _gate(tmp_path / "in", default_standin, _scale_observed(0.005, "voltage_high", True))
    assert inside.gate.word == "pass"
    assert inside.gate.detail.worst["voltage_pu"].deviation > 0
    assert 0 < inside.gate.detail.worst["voltage_pu"].utilisation < 1
    outside = _gate(tmp_path / "out", default_standin, _scale_observed(0.02, "voltage_high", True))
    assert outside.gate.word == "fail" and "value_voltage" in _checks(outside)


def _biggest_dispatch(bundle):
    return max(bundle["dispatch"], key=lambda row: row["dispatched_mva"])


def test_mismatch_dispatched_mva_one_percent_passes_three_percent_fails(tmp_path, default_standin):
    city = _biggest_dispatch(default_standin.bundle)["city"]
    value = _by_city(default_standin.bundle, "dispatch", city)["dispatched_mva"]
    _need(compare.within_flow(value * 1.01, value), "1 percent inside the flow allowance")
    _need(not compare.within_flow(value * 1.03, value), "3 percent outside the flow allowance")

    def scale(factor):
        def change(bundle):
            _by_city(bundle, "dispatch", city)["dispatched_mva"] *= factor
        return change

    inside = _gate(tmp_path / "in", default_standin, scale(1.01))
    assert inside.gate.word == "pass"
    assert 0 < inside.gate.detail.worst["dispatched_mva"].utilisation < 1
    outside = _gate(tmp_path / "out", default_standin, scale(1.03))
    assert outside.gate.word == "fail" and "dispatch_value" in _checks(outside)


def _margin_case(stand, classes):
    for row in stand.bundle["margins"]:
        if row["details"].get("bounded_by") in classes:
            return row["city"], row
    raise AssertionError("precondition not reached: a margin bounded by one of %s" % (classes,))


@pytest.mark.parametrize("which,classes,resolution_key", [
    ("default", ("voltage_criterion", "non_convergence"), "tolerance_mw"),
    ("stress", ("dlr_rating",), "step_mw"),
])
def test_mismatch_margin_nine_tenths_of_its_allowance_passes_eleven_tenths_fails(
        tmp_path, which, classes, resolution_key, default_standin, stress_standin):
    stand = default_standin if which == "default" else stress_standin
    city, row = _margin_case(stand, classes)
    old = row["margin_mw"]
    resolution = row["details"][resolution_key]
    first = max(compare.FLOW_RELATIVE_TOLERANCE * abs(old), resolution)

    def allowance(new):
        return max(compare.FLOW_RELATIVE_TOLERANCE * abs(new), resolution)

    def shifted(fraction):
        def change(bundle):
            _by_city(bundle, "margins", city)["margin_mw"] = old + fraction * first
        return change

    _need(0.9 * first <= allowance(old + 0.9 * first), "0.9 of the allowance is inside it")
    _need(1.1 * first > allowance(old + 1.1 * first), "1.1 of the allowance is outside it")
    inside = _gate(tmp_path / "in", stand, shifted(0.9))
    assert inside.gate.word == "pass"
    assert 0 < inside.gate.detail.worst["margin_mw"].utilisation < 1
    outside = _gate(tmp_path / "out", stand, shifted(1.1))
    assert outside.gate.word == "fail" and "margin_value" in _checks(outside)


def test_mismatch_a_changed_contingency_count_fails(tmp_path, default_standin):
    def change(bundle):
        bundle["run"]["n_contingencies"] += 1

    result = _gate(tmp_path, default_standin, change)
    assert result.gate.word == "fail" and "n_contingencies" in _checks(result)


def test_mismatch_removing_the_largest_voltage_row_fails_and_the_smallest_is_one_borderline(
        tmp_path, default_standin):
    rows = _rows(default_standin.bundle, "voltage_high")
    _need(rows[-1]["exceeded_by"] > compare.VOLTAGE_TOLERANCE_PU, "the largest excess above the band")
    _need(rows[0]["exceeded_by"] <= compare.VOLTAGE_TOLERANCE_PU, "the smallest excess inside the band")

    def drop(which):
        def change(bundle):
            victim = _rows(bundle, "voltage_high")[which]
            bundle["contingencies"].remove(victim)
        return change

    largest = _gate(tmp_path / "large", default_standin, drop(-1))
    assert largest.gate.word == "fail" and "set_one_sided" in _checks(largest)
    smallest = _gate(tmp_path / "small", default_standin, drop(0))
    assert smallest.gate.word == "pass"
    assert smallest.gate.summary.borderline == 1


def _bogus(kind, element_id, limit, excess, unit):
    def change(bundle):
        row = copy.deepcopy(_largest(bundle, kind))
        row.update(violation_kind=kind, element_id=element_id, limit_value=limit,
                   observed_value=limit + excess, exceeded_by=excess, unit=unit)
        bundle["contingencies"].append(row)
    return change


def test_mismatch_a_bogus_voltage_row_far_over_fails_and_one_just_over_is_borderline(
        tmp_path, default_standin):
    limit = _largest(default_standin.bundle, "voltage_high")["limit_value"]
    far = _gate(tmp_path / "far", default_standin, _bogus("voltage_high", "99999", limit, 0.05, "pu"))
    assert far.gate.word == "fail" and "set_one_sided" in _checks(far)
    near = _gate(tmp_path / "near", default_standin, _bogus("voltage_high", "99999", limit, 0.004, "pu"))
    assert near.gate.word == "pass" and near.gate.summary.borderline == 1


def test_mismatch_a_bogus_thermal_row_far_over_fails_and_one_just_over_is_borderline(
        tmp_path, stress_standin):
    limit = _largest(stress_standin.bundle, "thermal_overload")["limit_value"]
    band = compare.flow_allowance(limit)
    far = _gate(tmp_path / "far", stress_standin,
                _bogus("thermal_overload", "99999-99998-1", limit, 5 * band, "MVA"))
    assert far.gate.word == "fail" and "set_one_sided" in _checks(far)
    near = _gate(tmp_path / "near", stress_standin,
                 _bogus("thermal_overload", "99999-99998-1", limit, 0.5 * band, "MVA"))
    assert near.gate.word == "pass" and near.gate.summary.borderline == 1


def test_mismatch_a_recorded_non_convergence_for_an_outage_that_converged_fails(
        tmp_path, default_standin):
    def add(bundle):
        island = next(row for row in bundle["contingencies"]
                      if row["violation_kind"] == "non_convergence")
        row = copy.deepcopy(island)
        converged = _largest(bundle, "voltage_high")["contingency_id"]
        row.update(contingency_id=converged, element_id=converged)
        bundle["contingencies"].append(row)

    result = _gate(tmp_path, default_standin, add)
    assert result.gate.word == "fail" and "convergence_one_sided" in _checks(result)


def test_mismatch_removing_the_recorded_island_rows_fails(tmp_path, default_standin):
    def remove(bundle):
        kept = [row for row in bundle["contingencies"] if row["violation_kind"] != "non_convergence"]
        _need(len(kept) < len(bundle["contingencies"]), "recorded non_convergence rows exist")
        bundle["contingencies"] = kept

    result = _gate(tmp_path, default_standin, remove)
    assert result.gate.word == "fail" and "convergence_one_sided" in _checks(result)


def test_mismatch_a_changed_limiting_factor_fails_unless_the_limits_are_within_the_band(
        tmp_path, default_standin):
    city = next(row["city"] for row in default_standin.bundle["dispatch"]
                if row["limiting_factor"] == "voltage_stability")
    row = _by_city(default_standin.bundle, "dispatch", city)
    gap = abs(row["applied_mva"] - row["voltage_limit_mva"])
    _need(gap > compare.flow_allowance(row["applied_mva"]),
          "applied and voltage limit differ by more than the band")

    def flip(near):
        def change(bundle):
            target = _by_city(bundle, "dispatch", city)
            target["limiting_factor"] = "dlr_rating"
            if near:
                target["voltage_limit_mva"] = target["applied_mva"] * 1.001
        return change

    far = _gate(tmp_path / "far", default_standin, flip(False))
    assert far.gate.word == "fail" and "limiting_factor" in _checks(far)
    close = _gate(tmp_path / "close", default_standin, flip(True))
    assert close.gate.word == "pass" and close.gate.summary.borderline == 1


def test_mismatch_a_changed_stored_rating_replays_another_configuration_and_fails_on_dispatch(
        tmp_path, stress_standin):
    def faster(bundle):
        used = bundle["run"]["ratings_used"]["AUSTIN"]
        used["rating_amps_per_conductor"] *= 10
        used["rating_amps_circuit"] *= 10

    result = _gate(tmp_path, stress_standin, faster, real=True)
    summary = result.gate.summary
    assert result.gate.word == "fail"
    assert summary.runs_replayed == 1 and summary.configurations == 1
    assert summary.data_differences["rating_data"] == 1
    assert {"rating_data", "dispatch_value"} <= _checks(result)


def test_mismatch_an_altered_mapping_is_excluded_and_never_passes(tmp_path, default_standin):
    altered = os.path.join(str(tmp_path), "altered_mapping.json")
    with open(default_standin.mapping_path, "rb") as handle:
        original = handle.read()
    with open(altered, "wb") as handle:
        handle.write(original + b"\n")
    result = _gate(tmp_path, default_standin, mapping=altered)
    summary = result.gate.summary
    assert summary.excluded["mapping_hash_differs"] == 1
    assert summary.runs_replayed == 0
    assert result.gate.word == "incomplete"


def test_mismatch_a_different_session_case_hash_excludes_every_run(tmp_path, default_standin):
    result = _gate(tmp_path, default_standin, session="11" * 32)
    assert result.gate.summary.excluded["case_hash_differs"] == 1
    assert result.gate.summary.runs_replayed == 0
    assert result.gate.word == "incomplete"


def test_mismatch_a_snapshot_of_only_a_failed_run_is_incomplete(tmp_path, default_standin):
    repo = fixture.make_repo(tmp_path / "repo")
    snapshot = fixture.snapshot_of_bundles(
        repo, [fixture.run_bundle(1, fixture.FIXED_NOW, outcome="failed")])
    result = replay.replay_snapshot(
        snapshot, default_standin.backend, default_standin.network_path,
        default_standin.mapping_path, default_standin.case_sha256,
        runner=lambda selection: pytest.fail("no study for a failed run"))
    assert result.gate.summary.excluded["failed_run"] == 1
    assert result.gate.word == "incomplete"


def test_mismatch_a_broken_count_is_excluded_as_incomplete_rows(tmp_path, default_standin):
    def break_count(bundle):
        bundle["run"]["n_contingencies_with_results"] += 1

    result = _gate(tmp_path, default_standin, break_count, recount=False)
    assert result.gate.summary.excluded["rows_incomplete"] == 1
    assert result.gate.word == "incomplete"


def test_mismatch_both_sides_with_no_violation_rows_are_incomplete_not_a_pass(
        tmp_path, default_standin):
    def empty(bundle):
        bundle["contingencies"] = []

    result = _gate(tmp_path, default_standin, empty,
                   results=default_standin.results._replace(contingencies=[]))
    summary = result.gate.summary
    assert summary.runs_replayed == 1 and summary.runs_failed == 0
    assert sum(summary.nonempty.values()) == 0
    assert result.gate.word == "incomplete"


def test_mismatch_the_matrix_reads_the_tolerances_from_compare():
    assert compare.VOLTAGE_TOLERANCE_PU == 0.01 and compare.FLOW_RELATIVE_TOLERANCE == 0.02
    assert set(agree.tolerance_header()) >= {"voltage_tolerance_pu", "flow_relative_tolerance"}
    assert constants.CITIES
