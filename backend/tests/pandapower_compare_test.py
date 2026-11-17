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

import ast
import copy
import inspect
import math
import os
import random

import pytest

pandapower = pytest.importorskip("pandapower")

import pandas  # noqa: E402

import pandapower_fixture as fixture  # noqa: E402
from psse_job import constants  # noqa: E402
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


# -- Task 2: the comparator, the registry, the verdict and the copied settings --------------------


def _city():
    """(solved scaled net, matching synthetic reference): built once, handed out as copies."""
    if "city" not in _CITY_CACHE:
        net = _base_net()
        load_target, gen_target = _targets(net)
        _CITY_CACHE["city"] = (_solved_scaled_city(load_target, gen_target),
                               _by_hand_reference(net, load_target, gen_target))
    solved, reference = _CITY_CACHE["city"]
    return copy.deepcopy(solved), copy.deepcopy(reference)


def _compare(solved, reference, registry=None, city="AUSTIN", run="algorithm"):
    return compare.compare_city(city, run, solved, reference, registry)


def _set_ref(reference, key, **values):
    """Set quantities of one branch in both reference tables (line_flows has no q_mvar)."""
    for row in reference["line_flows"]:
        if row["key"] == key:
            row.update({name: value for name, value in values.items() if name in row})
    for row in reference["branch_flows"]["rows"]:
        if row["key"] == key:
            row.update(values)


def _ref_value(reference, key, name):
    for row in reference["branch_flows"]["rows"]:
        if row["key"] == key:
            return row[name]
    raise KeyError("no such branch")


def _line_keys(solved):
    return [str(name) for name in solved.line.name]


def _registry(*entries):
    return compare.load_registry({
        compare.REGISTRY_MARKER: compare.REGISTRY_VERSION,
        "entries": [{"element": element, "quantity": quantity, "cause": cause,
                     "measured_size": size} for element, quantity, cause, size in entries]})


def test_d13_boundaries():
    # Voltage: exactly 0.01 passes either way round, 0.0100001 fails.
    assert compare.within_voltage(1.0, 1.01) and compare.within_voltage(1.0, 0.99)
    assert not compare.within_voltage(1.0, 1.0100001) and not compare.within_voltage(1.0, 0.9899999)
    assert compare.within_voltage(0.5, 0.51) and compare.within_voltage(1.1, 1.09)
    # Flow: 2 percent of a large flow is the bound; 2.5 percent fails.
    assert compare.within_flow(500.0, 510.0) and compare.within_flow(500.0, 490.0)
    assert not compare.within_flow(500.0, 512.5) and not compare.within_flow(-500.0, -512.5)
    assert compare.within_flow(-500.0, -510.0)
    # Flow: the 2 MVA floor judges a small flow, inclusive.
    assert compare.within_flow(0.5, 2.0) and compare.within_flow(0.5, -1.0)
    assert not compare.within_flow(0.5, 3.0)
    assert compare.within_flow(0.0, 2.0) and not compare.within_flow(0.0, 2.0000001)
    # Where the percentage overtakes the floor (100 MVA is the crossover).
    assert compare.within_flow(100.0, 102.0) and not compare.within_flow(100.0, 102.0001)
    assert compare.within_flow(101.0, 103.02) and not compare.within_flow(101.0, 103.03)
    # A non-finite value is never within.
    assert not compare.within_voltage(1.0, math.nan) and not compare.within_flow(1.0, math.nan)
    assert not compare.within_flow(1.0, math.inf)


def test_zero_and_out_of_service_reference_flows():
    def with_zero_reference(got):
        solved, reference = _city()
        key, index = str(solved.line.name.iloc[0]), solved.line.index[0]
        for column, value in (("p_from_mw", got), ("q_from_mvar", 0.0), ("p_to_mw", 0.0),
                              ("q_to_mvar", 0.0)):
            solved.res_line.at[index, column] = value
        _set_ref(reference, key, p_mw=0.0, q_mvar=0.0, max_mva=0.0)
        return _compare(solved, reference), key

    for inside in (1.9, 2.0):
        verdict, _ = with_zero_reference(inside)
        assert verdict.complete and verdict.passed and verdict.flows_failed == 0
    verdict, key = with_zero_reference(2.1)
    assert verdict.complete and not verdict.passed and verdict.flows_failed == 2
    assert [(item.element, item.quantity) for item in verdict.unexplained] == [
        (key, "max_mva"), (key, "p_from")]

    # Out of service in the reference, in service in the net: one in_service difference, and the
    # flows of that element are not also reported.
    solved, reference = _city()
    key, index = str(solved.line.name.iloc[0]), solved.line.index[0]
    _set_ref(reference, key, in_service=False, p_mw=0.0, q_mvar=0.0, max_mva=0.0)
    verdict = _compare(solved, reference)
    assert [tuple(item) for item in verdict.unexplained] == [(key, "in_service", 1.0)]
    assert verdict.flows_compared == (35 + 11) * 3 - 3 and not verdict.passed and verdict.complete

    # Out of service on both sides: judged under the floor, zero (or NaN) flows pass.
    for result in (0.0, math.nan):
        solved, reference = _city()
        solved.line.at[index, "in_service"] = False
        for column in ("p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar"):
            solved.res_line.at[index, column] = result
        _set_ref(reference, key, in_service=False, p_mw=0.0, q_mvar=0.0, max_mva=0.0)
        verdict = _compare(solved, reference)
        assert verdict.passed and verdict.flows_compared == (35 + 11) * 3

    # In service in the reference, out of service in the net: also one difference.
    solved, reference = _city()
    solved.line.at[index, "in_service"] = False
    verdict = _compare(solved, reference)
    assert [tuple(item) for item in verdict.unexplained] == [(key, "in_service", 1.0)]

    # A bus out of service in the reference must be out of service in the net.
    solved, reference = _city()
    reference["buses"][4]["type_code"] = 4
    number = reference["buses"][4]["number"]
    verdict = _compare(solved, reference)
    assert [tuple(item) for item in verdict.unexplained] == [(str(number), "in_service", 1.0)]


def test_incomplete_comparisons_never_pass():
    solved, reference = _city()
    assert _compare(solved, reference).passed

    def check(verdict, missing=None, transformer_flows="ok"):
        assert not verdict.complete and not verdict.passed
        assert verdict.transformer_flows == transformer_flows
        if missing is not None:
            assert verdict.missing == missing
        return verdict

    # No reference at all, and one that is not usable.
    check(_compare(solved, None), (("reference", "unusable"),), "unavailable")
    unusable = copy.deepcopy(reference)
    unusable["solve"]["converged"] = False
    check(_compare(solved, unusable), (("reference", "unusable"),), "unavailable")
    failed = copy.deepcopy(reference)
    failed["status"] = "failed"
    check(_compare(solved, failed), (("reference", "unusable"),), "unavailable")

    # Transformer flows unavailable from the session: lines are compared, the rest is incomplete.
    flows = copy.deepcopy(reference)
    flows["branch_flows"] = {"status": "unavailable", "reason": "abrnreal ierr 1", "flag": 4,
                             "rows": []}
    verdict = check(_compare(solved, flows), (), "unavailable")
    assert verdict.flows_compared == 35 * 2 and verdict.unexplained == ()  # no Q without the extended read

    # Element sets that differ: a bus, a branch, either way round.
    short = copy.deepcopy(reference)
    gone = short["buses"].pop(5)["number"]
    check(_compare(solved, short), ((str(gone), "not_in_reference"),))
    extra = copy.deepcopy(reference)
    extra["buses"].append({"number": 123456, "type_code": 1, "base_kv": 1.0, "pu": 1.0})
    check(_compare(solved, extra), (("123456", "not_in_net"),))
    fewer = copy.deepcopy(reference)
    key = fewer["branch_flows"]["rows"][3]["key"]
    fewer["branch_flows"]["rows"] = [r for r in fewer["branch_flows"]["rows"] if r["key"] != key]
    fewer["line_flows"] = [r for r in fewer["line_flows"] if r["key"] != key]
    check(_compare(solved, fewer), ((key, "not_in_reference"),))
    more = copy.deepcopy(reference)
    row = dict(more["branch_flows"]["rows"][0], key="%d-%d-9" % (OFFSET + 1, OFFSET + 2))
    more["branch_flows"]["rows"].append(row)
    check(_compare(solved, more), ((row["key"], "not_in_net"),))

    # A branch the reference calls a transformer and the net holds as a line.
    flipped = copy.deepcopy(reference)
    flipped["branch_flows"]["rows"][0]["is_transformer"] = not flipped["branch_flows"]["rows"][
        0]["is_transformer"]
    check(_compare(solved, flipped), ((flipped["branch_flows"]["rows"][0]["key"],
                                       "class_differs"),))

    # A reference without a value where the rule needs one.
    blank = copy.deepcopy(reference)
    blank["buses"][2]["pu"] = None
    check(_compare(solved, blank), ((str(blank["buses"][2]["number"]), "reference_value"),))
    gap = copy.deepcopy(reference)
    gap["branch_flows"]["rows"][1]["max_mva"] = None
    check(_compare(solved, gap), ((gap["branch_flows"]["rows"][1]["key"], "reference_max_mva"),))

    # A net that was never solved.
    check(_compare(_base_net(), reference), (("net", "not_solved"),), "unavailable")

    # An unexplained difference on top of everything else is still just a failure.
    wrong = copy.deepcopy(short)
    wrong["buses"][0]["pu"] += 0.5
    verdict = check(_compare(solved, wrong))
    assert len(verdict.unexplained) == 1 and len(verdict.missing) == 1


def test_shuffled_reference_gives_an_equal_verdict():
    solved, reference = _city()
    reference["buses"][7]["pu"] += 0.011
    reference["buses"][20]["pu"] -= 0.02
    key = reference["branch_flows"]["rows"][5]["key"]
    _set_ref(reference, key, p_mw=_ref_value(reference, key, "p_mw") + 80.0)
    baseline = _compare(solved, reference)
    assert not baseline.passed and len(baseline.unexplained) >= 3

    for seed in (1, 2, 3):
        shuffled = copy.deepcopy(reference)
        generator = random.Random(seed)
        generator.shuffle(shuffled["buses"])
        generator.shuffle(shuffled["line_flows"])
        generator.shuffle(shuffled["branch_flows"]["rows"])
        assert shuffled["buses"] != reference["buses"]
        assert _compare(solved, shuffled) == baseline


def test_registry_explains_only_exact_listed_entries():
    solved, reference = _city()
    first, second = _line_keys(solved)[0], _line_keys(solved)[1]
    index = {str(name): i for i, name in zip(solved.line.index, solved.line.name)}
    deviations = {}
    for key in (first, second):
        shifted = _ref_value(reference, key, "p_mw") + 50.0
        _set_ref(reference, key, p_mw=shifted)
        deviations[key] = abs(float(solved.res_line.at[index[key], "p_from_mw"]) - shifted)
    cause = "a written cause"

    bare = _compare(solved, reference)
    assert [(i.element, i.quantity) for i in bare.unexplained] == sorted(
        [(first, "p_from"), (second, "p_from")]) and not bare.passed

    # Listed with a size equal to the deviation: explained (inclusive), and only that element.
    one = _compare(solved, reference, _registry((first, "p_from", cause, deviations[first])))
    assert [(i.element, i.quantity) for i in one.explained] == [(first, "p_from")]
    assert [(i.element, i.quantity) for i in one.unexplained] == [(second, "p_from")]
    assert one.complete and not one.passed and one.flows_failed == 2

    # Both listed: passes, still complete, and the counts still say two flows were out.
    both = _compare(solved, reference, _registry(
        (first, "p_from", cause, deviations[first] + 1.0),
        (second, "p_from", cause, deviations[second])))
    assert both.complete and both.passed and both.unexplained == () and len(both.explained) == 2
    assert both.flows_failed == 2

    # A size even slightly below the deviation explains nothing.
    short = _compare(solved, reference, _registry((first, "p_from", cause,
                                                  deviations[first] - 1e-3)))
    assert [(i.element, i.quantity) for i in short.unexplained] == sorted(
        [(first, "p_from"), (second, "p_from")])

    # Another quantity of the same element is not explained by a p_from entry, however large.
    _set_ref(reference, first, max_mva=_ref_value(reference, first, "max_mva") + 30.0)
    other = _compare(solved, reference, _registry((first, "p_from", cause, 1000.0),
                                                  (second, "p_from", cause, 1000.0)))
    assert [(i.element, i.quantity) for i in other.unexplained] == [(first, "max_mva")]
    wrong_quantity = _compare(solved, reference, _registry((first, "q_from", cause, 1000.0)))
    assert (first, "p_from") in [(i.element, i.quantity) for i in wrong_quantity.unexplained]

    # A bus: exact element and quantity, and the entry does not move the tolerance for others.
    solved, reference = _city()
    reference["buses"][3]["pu"] += 0.02
    reference["buses"][4]["pu"] += 0.02
    first_bus, second_bus = (str(reference["buses"][i]["number"]) for i in (3, 4))
    size = abs(float(solved.res_bus.at[reference["buses"][3]["number"], "vm_pu"])
               - reference["buses"][3]["pu"])
    verdict = _compare(solved, reference, _registry((first_bus, "voltage", cause, size)))
    assert [(i.element, i.quantity) for i in verdict.explained] == [(first_bus, "voltage")]
    assert [(i.element, i.quantity) for i in verdict.unexplained] == [(second_bus, "voltage")]
    assert verdict.buses_failed == 2


def test_registry_refuses_bad_entries():
    good = {"element": "90001", "quantity": "voltage", "cause": "a written cause",
            "measured_size": 0.02}

    def data(*entries, **extra):
        document = {compare.REGISTRY_MARKER: compare.REGISTRY_VERSION, "entries": list(entries)}
        document.update(extra)
        return document

    loaded = compare.load_registry(data(good))
    assert list(loaded) == [("90001", "voltage")]
    assert loaded[("90001", "voltage")].measured_size == 0.02
    assert compare.load_registry(data()) == {}
    assert compare.REGISTRY_MARKER == "pandapower_job_" + "registry"

    bad_inputs = {
        "not_an_object": [[good], "text", None],
        "missing_marker": [{"entries": [good]}, {compare.REGISTRY_MARKER: 2, "entries": [good]}],
        "bad_entries": [{compare.REGISTRY_MARKER: compare.REGISTRY_VERSION},
                        {compare.REGISTRY_MARKER: compare.REGISTRY_VERSION, "entries": {}}],
        "bad_entry": [data("text"), data(dict(good, element="")), data(dict(good, element=5)),
                      data(dict(good, quantity=None))],
        "unknown_quantity": [data(dict(good, quantity="angle"))],
        "empty_cause": [data(dict(good, cause="")), data(dict(good, cause="   ")),
                        data(dict(good, cause=None)), data({k: v for k, v in good.items()
                                                            if k != "cause"})],
        "bad_size": [data(dict(good, measured_size=math.nan)),
                     data(dict(good, measured_size=math.inf)),
                     data(dict(good, measured_size=-0.5)), data(dict(good, measured_size="0.02")),
                     data(dict(good, measured_size=True)), data(dict(good, measured_size=None))],
        "duplicate_entry": [data(good, dict(good, cause="another cause"))],
    }
    for reason, inputs in bad_inputs.items():
        for item in inputs:
            with pytest.raises(compare.RegistryRefused) as caught:
                compare.load_registry(item)
            assert caught.value.reason == reason
            assert "90001" not in str(caught.value) and "written" not in str(caught.value)


def test_compare_reads_the_net_only():
    solved, reference = _city()
    reference["buses"][7]["pu"] += 0.02
    key = reference["branch_flows"]["rows"][2]["key"]
    _set_ref(reference, key, p_mw=_ref_value(reference, key, "p_mw") + 40.0)
    registry = _registry((str(reference["buses"][7]["number"]), "voltage", "a written cause", 1.0))
    before = copy.deepcopy(solved)
    verdict = _compare(solved, reference, registry)
    assert verdict.explained and verdict.unexplained and not verdict.passed

    tables = [name for name in solved.keys() if isinstance(solved[name], pandas.DataFrame)]
    assert len(tables) > 10
    assert all(solved[name].equals(before[name]) for name in tables)
    assert all(list(solved[name].columns) == list(before[name].columns) for name in tables)
    assert solved.converged == before.converged


def _verdicts_for(cities, run="algorithm", reference_for=None):
    solved, reference = _city()
    found = []
    for city in cities:
        ref = reference_for(city, copy.deepcopy(reference)) if reference_for else reference
        found.append(compare.compare_city(city, run, solved, ref))
    return found


def test_net03_verdict_needs_four_complete_passing_cities():
    cities = constants.CITIES
    assert len(cities) == 4
    verdict = compare.net03_verdict(_verdicts_for(cities))
    assert verdict.passed and verdict.cities_passed == 4 and verdict.cities_complete == 4
    assert verdict.cities == tuple(cities) and len(verdict.verdicts) == 4

    def unavailable(city, reference):
        if city == cities[2]:
            reference["branch_flows"] = {"status": "unavailable", "reason": "x", "flag": 4,
                                         "rows": []}
        return reference

    verdict = compare.net03_verdict(_verdicts_for(cities, reference_for=unavailable))
    assert not verdict.passed and verdict.cities_complete == 3 and verdict.cities_passed == 3

    def failing(city, reference):
        if city == cities[1]:
            reference["buses"][0]["pu"] += 0.5
        return reference

    verdict = compare.net03_verdict(_verdicts_for(cities, reference_for=failing))
    assert not verdict.passed and verdict.cities_complete == 4 and verdict.cities_passed == 3

    # A city with no verdict, and no verdicts at all.
    verdict = compare.net03_verdict(_verdicts_for(cities[:3]))
    assert not verdict.passed and verdict.cities_complete == 3
    assert not compare.net03_verdict([]).passed

    # The injected run is a diagnostic: it neither rescues nor sinks the algorithm run.
    injected_failing = _verdicts_for(cities, run=compare.RUN_INJECTED, reference_for=failing)
    verdict = compare.net03_verdict(_verdicts_for(cities) + injected_failing)
    assert verdict.passed
    verdict = compare.net03_verdict(_verdicts_for(cities[:3]) + _verdicts_for(
        cities, run=compare.RUN_INJECTED))
    assert not verdict.passed and verdict.cities_complete == 3

    # Inconclusive var limits: both settings are solved and both must pass.
    both = (_verdicts_for(cities, run="algorithm:enforce_q_lims_off")
            + _verdicts_for(cities, run="algorithm:enforce_q_lims_on"))
    assert compare.net03_verdict(both).passed
    one_fails = (_verdicts_for(cities, run="algorithm:enforce_q_lims_off")
                 + _verdicts_for(cities, run="algorithm:enforce_q_lims_on", reference_for=failing))
    verdict = compare.net03_verdict(one_fails)
    assert not verdict.passed and verdict.cities_passed == 3 and verdict.cities_complete == 4


def _fingerprint(city, point, variant, shift=0.0, converged=True):
    voltages = [1.0 + shift, 1.02, 0.98]
    rows = [{"number": OFFSET + i, "type_code": 1, "base_kv": 345.0, "pu": value}
            for i, value in enumerate(voltages, 1)]
    return {"city": city, "point": point, "variant": variant, "options": None,
            "call_form": "positional",
            "solve": {"converged": converged, "ierr": 0, "solved_code": 0, "meaning": "x",
                      "iterations": 3, "mismatch_mva": 0.0},
            "buses": rows if converged else None}


def _point(city, point, immediate_shift, ignore_shift, shift_default=0.0):
    return [_fingerprint(city, point, "default", shift_default),
            _fingerprint(city, point, "forum", 0.5),
            _fingerprint(city, point, "var_limits_immediate", shift_default + immediate_shift),
            _fingerprint(city, point, "var_limits_ignore", shift_default + ignore_shift)]


def _session(payloads, tolerance=("read", 0.0001), iterations=("read", 30)):
    def setting(pair, source):
        status, value = pair
        return {"status": status, "value": value, "source": source if status == "read" else None,
                "reason": None if status == "read" else "no reader", "members": []}

    members = {}
    listed = []
    for payload in payloads:
        member = "settings/fingerprint_%s_%s_%s.json" % (
            payload["city"].lower(), payload["point"], payload["variant"])
        members[member] = payload
        listed.append({"city": payload["city"], "point": payload["point"],
                       "variant": payload["variant"], "member": member})
    document = {"settings": {
        "var_limits": {"status": "measured", "value": None, "source": "fingerprint",
                       "reason": None, "members": sorted(members)},
        "mismatch_tolerance_mva": setting(tolerance, "prmdat TOLN"),
        "iteration_limit": setting(iterations, "prmint ITMXN")}, "fingerprints": listed}
    return document, members


def test_settings_are_copied_with_recorded_deviations():
    tolerance = solve.FINGERPRINT_TOLERANCE_PU
    payloads = _point("AUSTIN", "base", 0.0, 10 * tolerance)
    document, members = _session(payloads)
    settings = solve.settings_from_session(document, members, 0.5)
    assert settings.enforce_q_lims is True
    assert settings.tolerance_mva == 0.0001 and settings.max_iteration == 30
    assert settings.collapse_voltage_pu == 0.5 and settings.deviations == ()
    assert settings.sources["tolerance_mva"] == "read: prmdat TOLN"
    assert settings.sources["max_iteration"] == "read: prmint ITMXN"
    assert settings.sources["enforce_q_lims"] == "fingerprint: on"
    # The same answer when the payloads are handed over as a list.
    assert solve.settings_from_session(document, payloads, 0.5) == settings

    # Off, and inconclusive (all three agree) which asks for both settings to be run.
    off_document, off_members = _session(_point("AUSTIN", "base", 10 * tolerance, 0.0))
    assert solve.settings_from_session(off_document, off_members, 0.5).enforce_q_lims is False
    flat_document, flat_members = _session(_point("AUSTIN", "base", 0.0, 0.0))
    flat = solve.settings_from_session(flat_document, flat_members, 0.5)
    assert flat.enforce_q_lims is None and flat.sources["enforce_q_lims"] == (
        "fingerprint: inconclusive")
    none_document, none_members = _session([])
    assert solve.settings_from_session(none_document, none_members, 0.5).enforce_q_lims is None

    # Neither value could be read: pandapower's own defaults (read from its signature, never
    # copied here) and two recorded deviations that name D-14.
    unread, members = _session(payloads, tolerance=("unavailable", None),
                               iterations=("unavailable", None))
    settings = solve.settings_from_session(unread, members, 0.5)
    parameters = inspect.signature(pandapower.runpp).parameters
    assert settings.tolerance_mva == parameters["tolerance_mva"].default
    assert settings.max_iteration == parameters["max_iteration"].default
    assert len(settings.deviations) == 2 and all("D-14" in text for text in settings.deviations)
    assert settings.sources["tolerance_mva"] == "pandapower default"
    assert settings.sources["max_iteration"] == "pandapower default"
    # Those defaults are usable settings: a solve under them converges.
    solved, _ = _city()
    fresh = _base_net()
    assert solve.run_load_flow(fresh, settings, True).converged

    # A read value that is not a usable number is a deviation too, one per setting.
    for value in (-1.0, 0.0, math.nan, True, "0.1", None):
        document, members = _session(payloads, tolerance=("read", value))
        result = solve.settings_from_session(document, members, 0.5)
        assert len(result.deviations) == 1 and "tolerance_mva" in result.deviations[0]
        assert result.tolerance_mva == parameters["tolerance_mva"].default
    for value in (0, -3, 2.5, True, "30", None):
        document, members = _session(payloads, iterations=("read", value))
        result = solve.settings_from_session(document, members, 0.5)
        assert len(result.deviations) == 1 and "max_iteration" in result.deviations[0]

    # Decisive fingerprints that disagree are not guessed at.
    document, members = _session(_point("AUSTIN", "base", 0.0, 10 * tolerance)
                                 + _point("MIDLAND", "base", 10 * tolerance, 0.0))
    with pytest.raises(ValueError, match="conflict"):
        solve.settings_from_session(document, members, 0.5)


def test_var_limit_classification_boundaries():
    tolerance = solve.FINGERPRINT_TOLERANCE_PU
    step = 1e-9

    def classify(*groups):
        return solve.classify_var_limits([item for group in groups for item in group])

    # "on": default equals immediate and differs from ignore.
    assert classify(_point("A", "base", 0.0, 10 * tolerance)) == "on"
    # Ignore differing by exactly the tolerance agrees (inclusive), one step more differs.
    assert classify(_point("A", "base", 0.0, tolerance)) == "inconclusive"
    assert classify(_point("A", "base", 0.0, tolerance - step)) == "inconclusive"
    assert classify(_point("A", "base", 0.0, tolerance + step)) == "on"
    # Immediate differing by exactly the tolerance still equals the default, one step more does not.
    assert classify(_point("A", "base", tolerance, 10 * tolerance)) == "on"
    assert classify(_point("A", "base", tolerance - step, 10 * tolerance)) == "on"
    assert classify(_point("A", "base", tolerance + step, 10 * tolerance)) == "inconclusive"
    # "off" is the mirror image.
    assert classify(_point("A", "base", 10 * tolerance, 0.0)) == "off"
    assert classify(_point("A", "base", tolerance + step, 0.0)) == "off"
    assert classify(_point("A", "base", tolerance, 0.0)) == "inconclusive"
    # The default matching neither says nothing.
    assert classify(_point("A", "base", 0.0, 0.0, shift_default=0.0)) == "inconclusive"
    mid = _point("A", "base", 10 * tolerance, -10 * tolerance)
    assert classify(mid) == "inconclusive"
    # Two points agreeing, and an inconclusive point beside a decisive one.
    assert classify(_point("A", "base", 0.0, 10 * tolerance),
                    _point("B", "base", 0.0, 10 * tolerance)) == "on"
    assert classify(_point("A", "base", 0.0, 10 * tolerance),
                    _point("B", "base", 0.0, 0.0)) == "on"
    # Decisive points that disagree.
    with pytest.raises(ValueError, match="conflict"):
        classify(_point("A", "base", 0.0, 10 * tolerance),
                 _point("A", "margin_last_good", 10 * tolerance, 0.0))
    # A variant that did not converge, a missing variant and no fingerprints: nothing decided.
    without_ignore = [item for item in _point("A", "base", 0.0, 10 * tolerance)
                      if item["variant"] != "var_limits_ignore"]
    assert classify(without_ignore) == "inconclusive"
    failed = _point("A", "base", 0.0, 10 * tolerance)
    failed[3] = _fingerprint("A", "base", "var_limits_ignore", 10 * tolerance, converged=False)
    assert classify(failed) == "inconclusive"
    assert solve.classify_var_limits([]) == "inconclusive"
    # The decisive variants joined by bus number, not position: shuffled rows classify alike.
    shuffled = _point("A", "base", 0.0, 10 * tolerance)
    for item in shuffled:
        random.Random(3).shuffle(item["buses"])
    assert classify(shuffled) == "on"


def test_convergence_rule_nan_and_collapse():
    settings = solve.SolveSettings(False, 1e-8, 30, 0.5, {}, ())
    good = solve.run_load_flow(_base_net(), settings, False)
    assert good.converged and good.reason is None and isinstance(good.iterations, int)

    # An in-service bus with no connection has no voltage: not converged, with a reason.
    isolated = _base_net()
    pandapower.create_bus(isolated, vn_kv=345.0, index=1, in_service=True)
    outcome = solve.run_load_flow(isolated, settings, False)
    assert not outcome.converged and outcome.reason == "nan_voltage"
    assert math.isnan(isolated.res_bus.at[1, "vm_pu"])
    # Out of service, the same bus is no problem.
    quiet = _base_net()
    pandapower.create_bus(quiet, vn_kv=345.0, index=1, in_service=False)
    assert solve.run_load_flow(quiet, settings, False).converged

    # A bus below the collapse limit: the limit is the mapping's, copied.
    low = solve.SolveSettings(False, 1e-8, 30, 1.2, {}, ())
    outcome = solve.run_load_flow(_base_net(), low, False)
    assert not outcome.converged and outcome.reason == "voltage_collapse"
    edge = _base_net()
    assert solve.run_load_flow(edge, settings, False).converged
    lowest = float(edge.res_bus.vm_pu.min())
    exactly = solve.SolveSettings(False, 1e-8, 30, lowest, {}, ())
    assert solve.run_load_flow(_base_net(), exactly, False).converged
    above = solve.SolveSettings(False, 1e-8, 30, lowest + 1e-6, {}, ())
    assert not solve.run_load_flow(_base_net(), above, False).converged

    # A solve that raises is a non-converged outcome named by the exception class, never its text.
    broken = _base_net()
    broken.ext_grid.drop(broken.ext_grid.index, inplace=True)
    outcome = solve.run_load_flow(broken, settings, False)
    assert not outcome.converged and outcome.iterations is None
    assert outcome.reason.isidentifier()
    heavy = _base_net()
    heavy.load["p_mw"] = heavy.load["p_mw"] * 60.0
    heavy.load["q_mvar"] = heavy.load["q_mvar"] * 60.0
    outcome = solve.run_load_flow(heavy, settings, False)
    assert not outcome.converged and outcome.reason

    # The setting the caller must pass is a real choice, never None.
    with pytest.raises(ValueError):
        solve.run_load_flow(_base_net(), settings, None)
    with pytest.raises(ValueError):
        solve.run_load_flow(_base_net(), settings, 1)
    # Reactive limits enforced: the solve runs and the net it was given is the one solved.
    limited = _base_net()
    assert solve.run_load_flow(limited, settings, True).converged and limited.converged


def test_tolerances_are_defined_once():
    path = os.path.join(os.path.dirname(os.path.abspath(compare.__file__)), "compare.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names = {"VOLTAGE_TOLERANCE_PU": 0.01, "FLOW_RELATIVE_TOLERANCE": 0.02,
             "FLOW_FLOOR_MVA": 2.0, "COMPARISON_EPSILON": 1e-12}
    assert (compare.VOLTAGE_TOLERANCE_PU, compare.FLOW_RELATIVE_TOLERANCE,
            compare.FLOW_FLOOR_MVA, compare.COMPARISON_EPSILON) == tuple(names.values())

    allowed = set()
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names):
            assert isinstance(node.value, ast.Constant)
            assert node.value.value == names[node.targets[0].id]
            allowed.add(id(node.value))
    assert len(allowed) == 4

    wanted = set(names.values())
    stray = [node for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and not isinstance(node.value, (str, bytes, bool))
             and isinstance(node.value, (int, float)) and node.value in wanted
             and id(node) not in allowed]
    assert len(stray) == 0


# -- Task 3: the scaling-detail analyser and the injected-snapshot run ----------------------------

SWING_BUS = OFFSET + 31
STEP = 1e-6


def _gen_index(records, bus):
    return [i for i, rec in enumerate(records["generator"]) if rec["I"] == bus][0]


def _with_swing_pg(records, pg):
    return fixture.mutate(records, "generator", _gen_index(records, SWING_BUS), "PG", pg)


def _snapshot(records):
    return _parse(records)


def _pg_sum(records, include_swing):
    return sum(rec["PG"] for rec in records["generator"]
               if rec["STAT"] == 1 and (include_swing or rec["I"] != SWING_BUS))


def _record(name, before=None, after=None, status="ok", **fields):
    record = {"name": name, "status": status, "detail": [] if status == "ok" else ["PsseCallError"],
              "totals_before": None, "totals_after": None, "targets": None, "sink_buses": None,
              "increment_mw": None,
              "before": "scaling/%s_before.raw" % name if before is not None else None,
              "after": "scaling/%s_after.raw" % name if after is not None else None}
    record.update(fields)
    return record


def _snapshots(*named):
    """{member: ParsedCase} for (name, before records, after records) triples."""
    found = {}
    for name, before, after in named:
        if before is not None:
            found["scaling/%s_before.raw" % name] = _snapshot(before)
        if after is not None:
            found["scaling/%s_after.raw" % name] = _snapshot(after)
    return found


def _swing_details(records, gen_total):
    experiment = _record("swing_in_total", before=records,
                         totals_before={"load_mw": 1.0, "gen_mw": gen_total})
    return scaling.analyse_scaling_details(
        [experiment], _snapshots(("swing_in_total", records, None))).swing_in_total


def test_swing_in_total_classification():
    records = _with_swing_pg(_roomy_records(), 300.0)
    with_swing, without = _pg_sum(records, True), _pg_sum(records, False)
    assert abs(with_swing - without - 300.0) < 1e-6

    assert _swing_details(records, with_swing) == "yes"
    assert _swing_details(records, without) == "no"
    assert _swing_details(records, with_swing + 5.0) == "inconclusive"
    # A swing machine that produces nothing cannot tell the two apart.
    zero = _with_swing_pg(_roomy_records(), 0.0)
    assert _swing_details(zero, _pg_sum(zero, True)) == "inconclusive"
    # Machines out of service are in neither sum.
    off = fixture.mutate(records, "generator", 0, "STAT", 0)
    assert _swing_details(off, _pg_sum(off, True)) == "yes"
    assert _swing_details(off, _pg_sum(off, False)) == "no"

    # Boundary: a gap of exactly MW_TOLERANCE is equal; one step inside and outside.
    tolerance = scaling.MW_TOLERANCE
    for target, gap_total in (("yes", with_swing), ("no", without)):
        assert _swing_details(records, gap_total + tolerance) == target
        assert _swing_details(records, gap_total - tolerance) == target
        assert _swing_details(records, gap_total + tolerance - 0.001) == target
        assert _swing_details(records, gap_total + tolerance + 0.001) == "inconclusive"
        assert _swing_details(records, gap_total - tolerance - 0.001) == "inconclusive"

    # The experiments document as written by the session is accepted as well as its list.
    experiment = _record("swing_in_total", before=records,
                         totals_before={"load_mw": 1.0, "gen_mw": with_swing})
    document = {"experiments": [experiment], "no_raw_export": False}
    details = scaling.analyse_scaling_details(
        document, _snapshots(("swing_in_total", records, None)))
    assert details.swing_in_total == "yes"
    assert details.clamped_at_limits == "inconclusive" and details.q_scales_with_p == "inconclusive"
    assert set(scaling.DETAIL_VALUES) >= {details.swing_in_total, details.clamped_at_limits}


def _clamp_records(passing_limit=None):
    """Records where every machine has room, except `passing_limit` = (index, factor): that
    machine's P maximum sits at P times the factor, so a larger scaling factor passes it."""
    records = _with_swing_pg(_roomy_records(), 0.0)
    if passing_limit is not None:
        index, factor = passing_limit
        records = fixture.mutate(records, "generator", index, "PT",
                                 records["generator"][index]["PG"] * factor)
    return records


def _clamp_details(records, after_records, factor=1.5, name="clamp_at_limits_x1_5", others=()):
    own = _pg_sum(records, False)
    experiment = _record(
        name, before=records, after=after_records,
        totals_before={"load_mw": 1.0, "gen_mw": own},
        targets={"load_mw": 1.0, "gen_mw": own * factor})
    snapshots = _snapshots((name, records, after_records))
    experiments = [experiment]
    for other_name, other_before, other_after, other_factor in others:
        other_own = _pg_sum(other_before, False)
        experiments.append(_record(
            other_name, before=other_before, after=other_after,
            totals_before={"load_mw": 1.0, "gen_mw": other_own},
            targets={"load_mw": 1.0, "gen_mw": other_own * other_factor}))
        snapshots.update(_snapshots((other_name, other_before, other_after)))
    return scaling.analyse_scaling_details(experiments, snapshots)


def _after_with(records, index, pg):
    return fixture.mutate(records, "generator", index, "PG", pg)


def test_clamping_classification():
    index = _gen_index(_roomy_records(), OFFSET + 32)     # 650 MW
    records = _clamp_records((index, 1.2))                # PT = 780, factor 1.5 passes it
    limit = records["generator"][index]["PT"]
    tolerance = scaling.MW_TOLERANCE

    # Held at the limit: yes. Inside the tolerance of the limit, still yes (boundary, inclusive).
    assert _clamp_details(records, _after_with(records, index, limit)).clamped_at_limits == "yes"
    assert _clamp_details(records, _after_with(
        records, index, limit + tolerance)).clamped_at_limits == "yes"
    assert _clamp_details(records, _after_with(
        records, index, limit - tolerance)).clamped_at_limits == "yes"
    assert _clamp_details(records, _after_with(
        records, index, limit + tolerance - 0.001)).clamped_at_limits == "yes"
    # Above the limit by more than the tolerance: no. One step beyond the boundary.
    assert _clamp_details(records, _after_with(
        records, index, limit + tolerance + 0.001)).clamped_at_limits == "no"
    assert _clamp_details(records, _after_with(
        records, index, records["generator"][index]["PG"] * 1.5)).clamped_at_limits == "no"
    # Short of the limit by more than the tolerance (neither held nor above): no conclusion.
    assert _clamp_details(records, _after_with(
        records, index, limit - tolerance - 0.001)).clamped_at_limits == "inconclusive"
    # No machine reaches its maximum: no conclusion either way.
    roomy = _clamp_records()
    assert _clamp_details(roomy, roomy).clamped_at_limits == "inconclusive"

    # Whether a machine counts as pushed past its maximum has the same boundary: P times the
    # factor at exactly maximum plus tolerance is not past it, one step more is.
    index2 = _gen_index(_roomy_records(), OFFSET + 35)
    base = _clamp_records()
    pg = base["generator"][index2]["PG"]
    edge = fixture.mutate(base, "generator", index2, "PT", pg * 1.5 - tolerance)
    assert _clamp_details(edge, _after_with(edge, index2, pg * 1.5)).clamped_at_limits == (
        "inconclusive")
    past = fixture.mutate(base, "generator", index2, "PT", pg * 1.5 - tolerance - 0.001)
    assert _clamp_details(past, _after_with(past, index2, pg * 1.5)).clamped_at_limits == "no"

    # Mixed machines (one held, one above): not a rule PSS/E applies to all, so inconclusive.
    two = _clamp_records((index, 1.2))
    other = _gen_index(two, OFFSET + 36)
    two = fixture.mutate(two, "generator", other, "PT", two["generator"][other]["PG"] * 1.2)
    after = _after_with(two, index, two["generator"][index]["PT"])
    after = _after_with(after, other, two["generator"][other]["PG"] * 1.5)
    assert _clamp_details(two, after).clamped_at_limits == "inconclusive"
    # Both machines held: yes. The swing machine is not judged.
    after = _after_with(after, other, two["generator"][other]["PT"])
    details = _clamp_details(two, after)
    assert details.clamped_at_limits == "yes"
    counts = details.evidence["clamped_at_limits"]["clamp_at_limits_x1_5"]
    assert counts["candidates"] == 2 and counts["at_limit"] == 2 and counts["above_limit"] == 0

    # Two experiments are combined: agreeing, one without evidence, and a contradiction.
    held = _after_with(records, index, limit)
    unheld = _after_with(records, index, records["generator"][index]["PG"] * 3.0)
    x3_records = _clamp_records((index, 2.0))
    x3_held = _after_with(x3_records, index, x3_records["generator"][index]["PT"])
    assert _clamp_details(records, held, others=[
        ("clamp_at_limits_x3", x3_records, x3_held, 3.0)]).clamped_at_limits == "yes"
    assert _clamp_details(records, held, others=[
        ("clamp_at_limits_x3", roomy, roomy, 3.0)]).clamped_at_limits == "yes"
    clash = _clamp_details(records, held, others=[
        ("clamp_at_limits_x3", x3_records,
         _after_with(x3_records, index, x3_records["generator"][index]["PG"] * 3.0), 3.0)])
    assert clash.clamped_at_limits == "inconclusive"
    assert clash.evidence["clamped_at_limits"]["clamp_at_limits_x1_5"]["at_limit"] == 1
    assert clash.evidence["clamped_at_limits"]["clamp_at_limits_x3"]["above_limit"] == 1
    assert clash.evidence["clamped_at_limits"]["combined"] == "contradiction"
    assert unheld["generator"][index]["PG"] > limit


def _q_records(p_before=100.0, q_before=20.0, count=2):
    """Records whose first `count` loads are the sink loads, at known P and Q."""
    records = _roomy_records()
    for position in range(count):
        records = fixture.mutate(records, "load", position, "PL", p_before)
        records = fixture.mutate(records, "load", position, "QL", q_before)
    return records


def _q_details(before, after, count=2):
    buses = [before["load"][position]["I"] for position in range(count)]
    experiment = _record("q_with_p", before=before, after=after, sink_buses=buses,
                         increment_mw=10.0)
    return scaling.analyse_scaling_details(
        [experiment], _snapshots(("q_with_p", before, after))).q_scales_with_p


def _after_loads(records, ratios, count=2):
    """Records with the sink loads' P and Q multiplied by (p ratio, q ratio) per load."""
    result = records
    for position in range(count):
        p_ratio, q_ratio = ratios[position] if isinstance(ratios, list) else ratios
        load = records["load"][position]
        result = fixture.mutate(result, "load", position, "PL", load["PL"] * p_ratio)
        result = fixture.mutate(result, "load", position, "QL", load["QL"] * q_ratio)
    return result


def test_q_with_p_classification():
    before = _q_records()
    # Q moves with P: yes. Q stays put while P moves: no.
    assert _q_details(before, _after_loads(before, (1.01, 1.01))) == "yes"
    assert _q_details(before, _after_loads(before, (1.01, 1.0))) == "no"
    # Q moves by some other ratio: no conclusion.
    assert _q_details(before, _after_loads(before, (1.01, 1.02))) == "inconclusive"

    # RATIO_TOLERANCE at, inside and outside (Q ratio against the P ratio).
    ratio = scaling.RATIO_TOLERANCE
    assert _q_details(before, _after_loads(before, (1.01, 1.01 + ratio))) == "yes"
    assert _q_details(before, _after_loads(before, (1.01, 1.01 - ratio))) == "yes"
    assert _q_details(before, _after_loads(before, (1.01, 1.01 + ratio - STEP))) == "yes"
    assert _q_details(before, _after_loads(before, (1.01, 1.01 + ratio + STEP))) == "inconclusive"
    # ... and Q unchanged within the same tolerance.
    assert _q_details(before, _after_loads(before, (1.01, 1.0 + ratio))) == "no"
    assert _q_details(before, _after_loads(before, (1.01, 1.0 - ratio + STEP))) == "no"
    assert _q_details(before, _after_loads(before, (1.01, 1.0 + ratio + STEP))) == "inconclusive"

    # MIN_RELATIVE_CHANGE at, inside and outside (relative change of P).
    change = scaling.MIN_RELATIVE_CHANGE
    assert _q_details(before, _after_loads(before, (1.0 + change, 1.0 + change))) == "yes"
    assert _q_details(before, _after_loads(
        before, (1.0 + change + STEP, 1.0 + change + STEP))) == "yes"
    assert _q_details(before, _after_loads(
        before, (1.0 + change - STEP, 1.0 + change - STEP))) == "inconclusive"
    assert _q_details(before, _after_loads(before, (1.0 - change, 1.0))) == "no"
    assert _q_details(before, _after_loads(before, (1.0 - change + STEP, 1.0))) == "inconclusive"
    assert _q_details(before, before) == "inconclusive"

    # A zero Q (or zero P) gives nothing to compare.
    zero_q = _q_records(q_before=0.0)
    assert _q_details(zero_q, _after_loads(zero_q, (1.01, 1.01))) == "inconclusive"
    zero_p = _q_records(p_before=0.0)
    assert _q_details(zero_p, _after_loads(zero_p, (1.01, 1.01))) == "inconclusive"

    # Loads that disagree give no conclusion; loads away from the sink buses and out of service
    # are not looked at.
    assert _q_details(before, _after_loads(before, [(1.01, 1.01), (1.01, 1.0)])) == (
        "inconclusive")
    elsewhere = _after_loads(before, (1.01, 1.01))
    elsewhere = fixture.mutate(elsewhere, "load", 5, "QL", 1234.5)
    assert _q_details(before, elsewhere) == "yes"
    quiet = fixture.mutate(_after_loads(before, [(1.01, 1.01), (1.01, 1.0)]), "load", 1,
                           "STATUS", 0)
    quiet_before = fixture.mutate(before, "load", 1, "STATUS", 0)
    assert _q_details(quiet_before, quiet) == "yes"
    experiment = _record("q_with_p", before=before, after=before, sink_buses=[],
                         increment_mw=10.0)
    assert scaling.analyse_scaling_details(
        [experiment], _snapshots(("q_with_p", before, before))).q_scales_with_p == "inconclusive"


def test_print_rounding_classifies_as_equal():
    # PSS/E prints P with four decimals in a RAW file; the tolerance is not finer than that.
    assert scaling.MW_TOLERANCE >= scaling.RAW_PRINT_RESOLUTION_MW
    assert scaling.RAW_PRINT_RESOLUTION_MW == 1e-4
    assert scaling.MW_TOLERANCE >= len(_roomy_records()["generator"]) * 0.5 * (
        scaling.RAW_PRINT_RESOLUTION_MW)

    exact = _with_swing_pg(_roomy_records(), 300.123456)
    for position, machine in enumerate(exact["generator"]):
        exact = fixture.mutate(exact, "generator", position, "PG",
                               machine["PG"] + 0.123456 * (position + 1))
    printed = copy.deepcopy(exact)
    for machine in printed["generator"]:
        machine["PG"] = round(machine["PG"], 4)
    total = _pg_sum(exact, True)
    assert total != _pg_sum(printed, True)
    assert abs(total - _pg_sum(printed, True)) < scaling.MW_TOLERANCE
    assert _swing_details(printed, total) == "yes"
    assert _swing_details(printed, _pg_sum(exact, False)) == "no"
    # A gap of less than the print resolution never changes the answer.
    assert _swing_details(exact, total + 0.5 * scaling.RAW_PRINT_RESOLUTION_MW) == "yes"

    # A machine held at a limit that prints rounded is still at it.
    index = _gen_index(_roomy_records(), OFFSET + 32)
    records = _clamp_records((index, 1.2))
    records = fixture.mutate(records, "generator", index, "PT", 780.12345)
    after = _after_with(records, index, round(780.12345, 4))
    assert _clamp_details(records, after).clamped_at_limits == "yes"

    # Loads that print rounded keep their ratios.
    before = _q_records(p_before=100.123456, q_before=20.654321)
    after = _after_loads(before, (1.01, 1.01))
    for load in after["load"][:2]:
        load["PL"], load["QL"] = round(load["PL"], 4), round(load["QL"], 4)
    assert _q_details(before, after) == "yes"


def test_failed_experiment_is_inconclusive():
    records = _with_swing_pg(_roomy_records(), 300.0)
    total = _pg_sum(records, True)

    def swing(**fields):
        record = _record("swing_in_total", before=records,
                         totals_before={"load_mw": 1.0, "gen_mw": total})
        record.update(fields)
        return record

    snapshots = _snapshots(("swing_in_total", records, None))
    ok = scaling.analyse_scaling_details([swing()], snapshots)
    assert ok.swing_in_total == "yes"

    failed = scaling.analyse_scaling_details([swing(status="failed", detail=["PsseCallError"])], snapshots)
    assert failed.swing_in_total == "inconclusive"
    assert failed.evidence["swing_in_total"]["reason"] == "failed"
    assert failed.evidence["swing_in_total"]["detail"] == ["PsseCallError"]
    # No experiment at all, no snapshot recorded, a snapshot that was not delivered, no totals.
    assert scaling.analyse_scaling_details([], snapshots).evidence["swing_in_total"][
        "reason"] == "missing"
    for broken, reason in ((swing(before=None), "no_snapshot"),
                           (swing(before="scaling/elsewhere.raw"), "snapshot_not_delivered"),
                           (swing(totals_before=None), "no_totals"),
                           (swing(totals_before={"load_mw": 1.0, "gen_mw": math.nan}), "no_totals")):
        result = scaling.analyse_scaling_details([broken], snapshots)
        assert result.swing_in_total == "inconclusive"
        assert result.evidence["swing_in_total"]["reason"] == reason

    # A failed clamp experiment gives no evidence; the other one still speaks, and both failing
    # leaves nothing. A failed q_with_p is inconclusive too.
    index = _gen_index(_roomy_records(), OFFSET + 32)
    held_records = _clamp_records((index, 1.2))
    held = _after_with(held_records, index, held_records["generator"][index]["PT"])
    own = _pg_sum(held_records, False)
    good = _record("clamp_at_limits_x1_5", before=held_records, after=held,
                   totals_before={"load_mw": 1.0, "gen_mw": own},
                   targets={"load_mw": 1.0, "gen_mw": own * 1.5})
    bad = _record("clamp_at_limits_x3", status="failed")
    clamp_snapshots = _snapshots(("clamp_at_limits_x1_5", held_records, held))
    one = scaling.analyse_scaling_details([good, bad], clamp_snapshots)
    assert one.clamped_at_limits == "yes"
    assert one.evidence["clamped_at_limits"]["clamp_at_limits_x3"]["reason"] == "failed"
    both = scaling.analyse_scaling_details(
        [dict(good, status="failed"), bad], clamp_snapshots)
    assert both.clamped_at_limits == "inconclusive"
    q_failed = _record("q_with_p", status="failed")
    assert scaling.analyse_scaling_details([q_failed], {}).q_scales_with_p == "inconclusive"
    for detail in scaling.analyse_scaling_details([], {})[:3]:
        assert detail == "inconclusive"


def _scaled_records(records, load_target_factor, gen_target_factor):
    """The PSS/E side by hand on RAW records: loads times one factor, non-swing machines times
    the factor that reaches the generation target with the swing machine excluded."""
    gen_total = _pg_sum(records, False)
    load_total = sum(rec["PL"] for rec in records["load"] if rec["STATUS"] == 1)
    scaled = copy.deepcopy(records)
    for load in scaled["load"]:
        load["PL"] *= load_target_factor
        load["QL"] *= load_target_factor
    for machine in scaled["generator"]:
        if machine["I"] != SWING_BUS:
            machine["PG"] *= gen_target_factor
    return scaled, load_total * load_target_factor, gen_total * gen_target_factor


def test_injected_run_localises_a_wrong_scaling_flag():
    records = _with_swing_pg(_roomy_records(), 1000.0)
    scaled_records, load_target, gen_target = _scaled_records(records, 1.1, 1.1)
    base = network.build_network(_case(records))

    # The PSS/E side: solved from its own scaled values.
    pse_net = network.build_network(_case(scaled_records))
    assert solve.run_load_flow(pse_net, _settings(), False).converged
    reference = _reference(pse_net, "AUSTIN")
    target = scaling_tuple(load_target, gen_target)

    def algorithm(swing_flag):
        details = scaling.ScalingDetails(swing_flag, "no", "inconclusive", {})
        net = scaling.scale_city(base, target, details)
        assert solve.run_load_flow(net, _settings(), False).converged
        return compare.compare_city("AUSTIN", "algorithm", net, reference)

    right = algorithm("no")
    wrong = algorithm("yes")
    assert right.complete and right.passed
    assert wrong.complete and not wrong.passed and wrong.flows_failed > 0

    # The injected run takes PSS/E's own post-scaling values and passes whichever flag is wrong.
    injected = scaling.inject_snapshot(base, _snapshot(scaled_records))
    assert solve.run_load_flow(injected, _settings(), False).converged
    verdict = compare.compare_city("AUSTIN", compare.RUN_INJECTED, injected, reference)
    assert verdict.complete and verdict.passed
    # ... and a net that was not injected is a different net (deep copies both ways).
    assert float(base.load.p_mw.sum()) != float(injected.load.p_mw.sum())
    assert float(base.load.p_mw.sum()) == pytest.approx(
        sum(rec["PL"] for rec in records["load"]))
    assert float(injected.ext_grid.psse_pg_mw.iloc[0]) == 1000.0

    # Every in-service machine's P and every load's P and Q are copied, by name.
    for _, row in injected.gen.iterrows():
        bus, ident = str(row["name"]).split("-", 1)
        expected = [m["PG"] for m in scaled_records["generator"]
                    if str(m["I"]) == bus and m["ID"] == ident][0]
        assert row["p_mw"] == expected
    for _, row in injected.load.iterrows():
        bus, ident = str(row["name"]).split("-", 1)
        expected = [m for m in scaled_records["load"] if str(m["I"]) == bus and m["ID"] == ident][0]
        assert (row["p_mw"], row["q_mvar"]) == (expected["PL"], expected["QL"])

    # A snapshot missing an element is refused, with no figure in the message.
    for section, position in (("load", 0), ("generator", 0),
                              ("generator", _gen_index(records, SWING_BUS))):
        with pytest.raises(scaling.ScalingRefused) as caught:
            scaling.inject_snapshot(base, _snapshot(fixture.remove(
                scaled_records, section, position)))
        assert caught.value.reason == "snapshot_missing_element"
        assert not any(char.isdigit() for char in str(caught.value))


def test_scale_city_refusals_and_clamping(monkeypatch):
    base = network.build_network(_case())
    own_load, own_gen = _totals(base)
    no = scaling.ScalingDetails("no", "no", "inconclusive", {})

    def target(load_factor, gen_factor):
        return scaling_tuple(own_load * load_factor, own_gen * gen_factor)

    # Undetermined: the swing flag, and the clamp flag only when a machine would pass a limit.
    with pytest.raises(scaling.ScalingUndetermined) as caught:
        scaling.scale_city(base, target(1.0, 1.0), no._replace(swing_in_total="inconclusive"))
    assert caught.value.reason == "swing_in_total"
    unsure = no._replace(clamped_at_limits="inconclusive")
    scaling.scale_city(base, target(1.0, 1.0), unsure)       # no machine passes a limit at 1.0
    limited = network.build_network(_case(_clamp_records((_gen_index(
        _roomy_records(), OFFSET + 32), 1.05))))
    with pytest.raises(scaling.ScalingUndetermined) as caught:
        scaling.scale_city(limited, target(1.0, 1.1), unsure)
    assert caught.value.reason == "clamped_at_limits"

    # Targets outside the bounds psse_job.study uses, on either side, load or generation.
    for load_factor, gen_factor in ((0.0495, 1.0), (20.2, 1.0), (1.0, 0.0495), (1.0, 20.2)):
        with pytest.raises(scaling.ScalingRefused) as caught:
            scaling.scale_city(base, target(load_factor, gen_factor), no)
        assert caught.value.reason.endswith("_bounds")
        assert not any(char.isdigit() for char in str(caught.value))
    scaled = scaling.scale_city(base, target(0.0505, 19.9), no)
    assert abs(float(scaled.load.p_mw.sum()) - own_load * 0.0505) < 1e-6 * own_load
    # Nothing to scale, and a bad detail value.
    idle = copy.deepcopy(base)
    idle.load["in_service"] = False
    with pytest.raises(scaling.ScalingRefused) as caught:
        scaling.scale_city(idle, target(1.0, 1.0), no)
    assert caught.value.reason == "load_none"
    with pytest.raises(ValueError):
        scaling.scale_city(base, target(1.0, 1.0), no._replace(swing_in_total="maybe"))
    # The read-back tolerance is the job's: with an impossible one every scaling is refused.
    monkeypatch.setattr(scaling.study, "SCALE_TOLERANCE", -1.0)
    with pytest.raises(scaling.ScalingRefused) as caught:
        scaling.scale_city(base, target(1.1, 1.1), no)
    assert caught.value.reason == "load_read_back"
    monkeypatch.undo()
    assert scaling.study.SCALE_FACTOR_BOUNDS == (0.05, 20.0)

    # Clamping "yes" holds a machine at its limit and the generation total falls short;
    # "no" lets it pass; the source net is never changed.
    snapshot = copy.deepcopy(limited)
    held = scaling.scale_city(limited, target(1.0, 1.1), no._replace(clamped_at_limits="yes"))
    index = limited.gen.index[limited.gen.name == "%d-1" % (OFFSET + 32)][0]
    assert held.gen.at[index, "p_mw"] == limited.gen.at[index, "max_p_mw"]
    assert float(held.gen.p_mw.sum()) < own_gen * 1.1 - 1.0
    passed = scaling.scale_city(limited, target(1.0, 1.1), no)
    assert passed.gen.at[index, "p_mw"] > limited.gen.at[index, "max_p_mw"]
    assert limited.gen.equals(snapshot.gen) and limited.load.equals(snapshot.load)

    # The swing machine in the total: its stored P is scaled with the rest and the others scale
    # by less; excluded, it is left alone.
    swung = network.build_network(_case(_with_swing_pg(_roomy_records(), 500.0)))
    swing_total = own_gen + 500.0
    inside = scaling.scale_city(swung, scaling_tuple(own_load, swing_total * 1.1),
                                no._replace(swing_in_total="yes"))
    assert float(inside.ext_grid.psse_pg_mw.iloc[0]) == pytest.approx(550.0)
    assert float(inside.gen.p_mw.sum()) == pytest.approx(own_gen * 1.1)
    outside = scaling.scale_city(swung, scaling_tuple(own_load, own_gen * 1.1), no)
    assert float(outside.ext_grid.psse_pg_mw.iloc[0]) == 500.0
    assert float(outside.gen.p_mw.sum()) == pytest.approx(own_gen * 1.1)


def test_threshold_values_are_the_plans():
    # The boundary tests above are written against the constants; this pins the constants.
    assert (scaling.MW_TOLERANCE, scaling.RATIO_TOLERANCE, scaling.MIN_RELATIVE_CHANGE) == (
        0.01, 1e-4, 1e-3)
    assert solve.FINGERPRINT_TOLERANCE_PU == 1e-6
    assert scaling.DETAIL_VALUES == ("yes", "no", "inconclusive")
