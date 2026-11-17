"""
Tests for the NET-03 machinery and the PSE-02 analyser (pandapower-solver Phase 1, plan 01-08):
scaling a city's copy from its targets, solving it under settings copied from the session, and
comparing it with a reference under the D-13 rule, plus the offline classification of the
session's scaling experiments.

Every reference here is synthetic and circular: it is made by `pandapower_fixture.
reference_from_solved` from a pandapower solve of a network built from the 39-bus case with the
bus numbers offset by 90000. These tests prove plumbing, tolerance logic and failure detection,
never agreement with PSS/E; physics is validated only by plan 01-10's real data.

Failure messages are counts only.
"""

import copy
import inspect
import math

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_fixture as fixture  # noqa: E402
from pandapower_job import compare, network, raw, scaling, solve  # noqa: E402

OFFSET = fixture.OFFSET
TARGET_LOAD_FACTOR = 1.1
TARGET_GEN_FACTOR = 1.1


def _parse(records):
    return raw.parse_raw(fixture.raw_text(records).encode("utf-8"))


ROOMY_PT_MW = 5000.0


def _roomy_records():
    """The synthetic records with every machine's P maximum raised, so a scaling factor above one
    never passes a limit (several machines of the 39-bus case sit at their maximum)."""
    records = fixture.case39_records(OFFSET)
    for machine in records["generator"]:
        machine["PT"] = ROOMY_PT_MW
    return records


def _case(records=None):
    return _parse(records if records is not None else _roomy_records())


def _settings(enforce=False):
    return solve.SolveSettings(enforce, 1e-8, 30, 0.5, {}, ())


def _totals(net):
    load = float(net.load.loc[net.load.in_service, "p_mw"].sum())
    gen = float(net.gen.loc[net.gen.in_service, "p_mw"].sum())
    return load, gen


def _targets(net):
    load, gen = _totals(net)
    return load * TARGET_LOAD_FACTOR, gen * TARGET_GEN_FACTOR


_CITY_CACHE = {}


def _base_net():
    """A fresh unsolved network of the synthetic case (build once, copy out)."""
    if "net" not in _CITY_CACHE:
        _CITY_CACHE["net"] = network.build_network(_case())
    return copy.deepcopy(_CITY_CACHE["net"])


def _by_hand_reference(net, load_target, gen_target, city="AUSTIN"):
    """The 'PSS/E side': loads times a factor, non-swing machines times the factor that reaches
    the generation target with the swing machine excluded, solved and turned into a reference."""
    own_load, own_gen = _totals(net)
    scaled = copy.deepcopy(net)
    scaled.load["p_mw"] = scaled.load["p_mw"] * (load_target / own_load)
    scaled.load["q_mvar"] = scaled.load["q_mvar"] * (load_target / own_load)
    scaled.gen["p_mw"] = scaled.gen["p_mw"] * (gen_target / own_gen)
    outcome = solve.run_load_flow(scaled, _settings(), False)
    assert outcome.converged
    return _reference(scaled, city)


def _reference(solved, city):
    """
    `pandapower_fixture.reference_from_solved` of a solved net. That fixture reads a transformer's
    flows from the line column names (p_from_mw), which res_trafo does not have (it has p_hv_mw
    and friends), and it is frozen for this plan; so the transformer results are given the line
    names on a copy first. The values are the same numbers, hv end as the from end.
    """
    aliased = copy.deepcopy(solved)
    for line_name, trafo_name in zip(compare._LINE_COLUMNS, compare._TRAFO_COLUMNS):
        aliased.res_trafo[line_name] = aliased.res_trafo[trafo_name]
    return fixture.reference_from_solved(aliased, city)


def _solved_scaled_city(load_target, gen_target, details=None):
    net = _base_net()
    details = details or scaling.ScalingDetails("no", "inconclusive", "inconclusive", {})
    scaled = scaling.scale_city(
        net, scaling_tuple(load_target, gen_target), details)
    outcome = solve.run_load_flow(scaled, _settings(), False)
    assert outcome.converged
    return scaled


def scaling_tuple(load_target, gen_target):
    from psse_job import mapping
    return mapping.Scaling(load_target, gen_target, "average")


def test_tracer_scaled_city_solve_and_compare_on_synthetic_data():
    net = _base_net()
    load_target, gen_target = _targets(net)
    reference = _by_hand_reference(net, load_target, gen_target)

    solved = _solved_scaled_city(load_target, gen_target)
    verdict = compare.compare_city("AUSTIN", "algorithm", solved, reference)

    assert verdict.complete and verdict.passed
    assert verdict.buses_compared == 39 and verdict.buses_failed == 0
    assert verdict.flows_compared == (35 + 11) * 3 and verdict.flows_failed == 0
    assert verdict.unexplained == () and verdict.missing == ()
    assert verdict.transformer_flows == "ok"
    # The source network was not scaled by the call.
    assert abs(_totals(net)[0] - _totals(_base_net())[0]) == 0.0

    # One planted 0.011 pu error is one unexplained bus.
    wrong = copy.deepcopy(reference)
    wrong["buses"][7]["pu"] = wrong["buses"][7]["pu"] + 0.011
    planted = wrong["buses"][7]["number"]
    verdict = compare.compare_city("AUSTIN", "algorithm", solved, wrong)
    assert verdict.complete and not verdict.passed
    assert verdict.buses_failed == 1 and verdict.flows_failed == 0
    assert [(item.element, item.quantity) for item in verdict.unexplained] == [
        (str(planted), "voltage")]


def test_verdict_rendering_is_counts_only():
    net = _base_net()
    load_target, gen_target = _targets(net)
    reference = _by_hand_reference(net, load_target, gen_target)
    solved = _solved_scaled_city(load_target, gen_target)
    wrong = copy.deepcopy(reference)
    wrong["buses"][3]["pu"] = wrong["buses"][3]["pu"] + 0.0345678
    planted = str(wrong["buses"][3]["number"])
    verdict = compare.compare_city("AUSTIN", "algorithm", solved, wrong)
    assert verdict.worst_voltage_pu is not None and verdict.unexplained

    text = verdict.render_counts()
    assert "FAIL" in text and "AUSTIN" in text and "algorithm" in text
    assert planted not in text
    assert ("%g" % verdict.worst_voltage_pu) not in text and "0.0345" not in text
    assert "voltage" not in text
    good = compare.compare_city("AUSTIN", "algorithm", solved, reference).render_counts()
    assert "PASS" in good and "FAIL" not in good
    assert not any(str(number) in good for number in (OFFSET + 1, OFFSET + 2, OFFSET + 30))
