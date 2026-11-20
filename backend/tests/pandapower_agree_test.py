"""
Tests for the agreement rules (pandapower-solver Phase 4, plan 04-02: AGR-02 and AGR-03; decisions
D-02 and D-04).

Pure: no solver, no database. Every row here is hand-built and synthetic (no figure and no bus
number of the real network); these tests prove the comparison rules and the gate, never agreement
between PSS/E and pandapower. Follows `pandapower_compare_test.py`. Failure messages are counts
only.
"""

import ast
import copy
import json
import os
import subprocess
import sys

import pytest

from pandapower_job import agree, compare
from psse_job import constants, contract

CITIES = constants.CITIES


def _dispatch(city):
    return {
        "city": city, "rating_source": "city_rating", "fallback_reason": None,
        "applied_amps_per_conductor": 900.0, "subconductors_per_phase": 2,
        "line_voltage_kv": 345.0, "applied_mva": 1000.0, "voltage_limit_mva": 800.0,
        "dispatched_mva": 800.0, "limiting_factor": "voltage_stability",
        "details": {
            "branches": ["b1-b2-1", "b2-b3-1"], "rate_before_mva": [500.0, 600.0],
            "voltage_limit_bounded_by": "voltage_criterion",
        },
    }


def _margin(city):
    return {
        "city": city, "base_transfer_mw": 200.0, "limit_transfer_mw": 800.0, "margin_mw": 600.0,
        "voltage_limit_mva": 850.0, "critical_bus": "bus-a", "min_voltage_pu": 0.93,
        "details": {
            "bounded_by": "voltage_criterion", "lower_bound": False, "step_mw": 25.0,
            "tolerance_mw": 1.0, "sink_buses": ["s1", "s2"], "criterion_pu": 0.9,
        },
    }


def _violation(outage, kind, element, limit, observed, unit):
    exceeded = None
    if kind in ("thermal_overload", "voltage_high"):
        exceeded = observed - limit
    elif kind == "voltage_low":
        exceeded = limit - observed
    return {
        "contingency_id": outage, "violation_kind": kind,
        "element_type": "branch" if kind == "thermal_overload" else "bus",
        "element_id": element, "city": outage.split(":")[0], "limit_value": limit,
        "observed_value": observed, "exceeded_by": exceeded, "unit": unit, "details": None,
    }


def _rows():
    """A complete synthetic run: ten outages, four cities, three violation rows."""
    non_convergence = {
        "contingency_id": "MIDLAND:out03", "violation_kind": "non_convergence",
        "element_type": "contingency", "element_id": "MIDLAND:out03", "city": None,
        "limit_value": None, "observed_value": None, "exceeded_by": None, "unit": None,
        "details": {"ierr": 0},
    }
    return {
        "run": {"n_contingencies": 10, "rate_set": 1},
        "dispatch": [_dispatch(city) for city in CITIES],
        "margins": [_margin(city) for city in CITIES],
        "contingencies": [
            _violation("AUSTIN:out01", "thermal_overload", "br1", 1000.0, 1100.0, "MVA"),
            _violation("EL_PASO:out02", "voltage_low", "bus7", 0.90, 0.85, "pu"),
            non_convergence,
        ],
    }


def _recorded(rows):
    return agree.side_from_recorded(
        rows["run"], rows["dispatch"], rows["margins"], rows["contingencies"])


def _replayed(rows):
    results = contract.StudyResults(
        dispatch=rows["dispatch"], margins=rows["margins"], contingencies=rows["contingencies"],
        n_contingencies=rows["run"]["n_contingencies"], rate_set=rows["run"]["rate_set"],
        psse_version=None)
    return agree.side_from_results(results)


def _pair(mutate=None):
    """A recorded and a replayed Side from deep copies of _rows(); `mutate(recorded_rows,
    replayed_rows)` changes either or both."""
    recorded_rows, replayed_rows = _rows(), copy.deepcopy(_rows())
    if mutate is not None:
        mutate(recorded_rows, replayed_rows)
    return _recorded(recorded_rows), _replayed(replayed_rows)


def _failures(comparison):
    return sorted(set(item.check for item in comparison.findings if item.klass == "failure"))


# -- Task 1: the tracer ---------------------------------------------------------------------------


def test_tracer_identical_pass_and_one_change_fails():
    recorded, replayed = _pair()
    comparison = agree.compare_run(recorded, replayed)
    assert comparison.passed and comparison.findings == ()
    assert comparison.counts["outages_thermal_overload"] == 1
    assert comparison.counts["outages_voltage_low"] == 1
    assert comparison.counts["outages_non_convergence"] == 1
    assert comparison.counts["outages_voltage_high"] == 0
    assert comparison.counts["pairs_compared"] == 2
    assert comparison.counts["agreeing_keys"] == 3
    assert set(comparison.counts) == set(agree.COMPARE_COUNT_KEYS)
    assert all(item.deviation == 0 for item in comparison.worst.values())
    assert agree.gate([("run", comparison)], [], 1, 1).word == "pass"

    def three_percent(rec, rep):
        rep["contingencies"][0]["observed_value"] *= 1.03

    changed = agree.compare_run(*_pair(three_percent))
    assert not changed.passed
    assert _failures(changed) == ["value_thermal"]
    assert agree.gate([("run", changed)], [], 1, 1).word == "fail"


# -- Task 2: the rule matrix, a tolerance edge on both sides --------------------------------------


def _marg(rows, city="AUSTIN"):
    return [row for row in rows["margins"] if row["city"] == city][0]


def _disp(rows, city="AUSTIN"):
    return [row for row in rows["dispatch"] if row["city"] == city][0]


def _setd(**fields):
    return lambda rows: _disp(rows).update(fields)


def _setdd(**fields):
    return lambda rows: _disp(rows)["details"].update(fields)


def _setm(**fields):
    return lambda rows: _marg(rows).update(fields)


def _setmd(**fields):
    return lambda rows: _marg(rows)["details"].update(fields)


def _setv(index, **fields):
    return lambda rows: rows["contingencies"][index].update(fields)


def _rep(fn):
    return lambda rec, rep: fn(rep)


def _rec(fn):
    return lambda rec, rep: fn(rec)


def _both(fn):
    return lambda rec, rep: (fn(rec), fn(rep))


def _all(*fns):
    return lambda rec, rep: [fn(rec, rep) for fn in fns]


def _add(row):
    return lambda rows: rows["contingencies"].append(row)


def _drop_key(name):
    return lambda rows: _marg(rows)["details"].pop(name)


def _rating_class(margin):
    """Both sides rating-bound, the recorded margin `margin`."""
    return _all(_both(_setmd(bounded_by="dlr_rating", lower_bound=True)),
                _both(_setm(margin_mw=margin)))


def _small_flow(rows):
    row = rows["contingencies"][0]
    row.update(limit_value=40.0, observed_value=50.0, exceeded_by=10.0)


def _rows_for_dispatch_factor(rows):
    _disp(rows).update(limiting_factor="dlr_rating", voltage_limit_mva=1200.0,
                       dispatched_mva=1000.0)


_BORDER_VH = _violation("EL_PASO:out05", "voltage_high", "bus9", 1.05, 1.06, "pu")
_BORDER_VH_OUT = _violation("EL_PASO:out05", "voltage_high", "bus9", 1.05, 1.061, "pu")
_BORDER_TH = _violation("AUSTIN:out04", "thermal_overload", "br2", 1000.0, 1020.0, "MVA")
_BORDER_TH_OUT = _violation("AUSTIN:out04", "thermal_overload", "br2", 1000.0, 1020.2, "MVA")
_LONE_NC = dict(_rows()["contingencies"][2], contingency_id="AUSTIN:out06",
                element_id="AUSTIN:out06")

# (name, mutate(recorded_rows, replayed_rows), expected klass or None, expected check or None)
MATRIX = [
    ("identical", None, None, None),
    # input data that must be the same (never borderline)
    ("rating_source", _rep(_setd(rating_source="static")), "failure", "rating_data"),
    ("fallback_reason", _rep(_setd(fallback_reason="stale")), "failure", "rating_data"),
    ("subconductors", _rep(_setd(subconductors_per_phase=3)), "failure", "rating_data"),
    ("applied_amps inside", _rep(_setd(applied_amps_per_conductor=900.0 * (1 + 1e-8))),
     None, None),
    ("applied_amps outside", _rep(_setd(applied_amps_per_conductor=900.0 * (1 + 1e-4))),
     "failure", "rating_data"),
    ("line_voltage", _rep(_setd(line_voltage_kv=230.0)), "failure", "rating_data"),
    ("applied_mva", _rep(_setd(applied_mva=1010.0)), "failure", "rating_data"),
    ("branches reordered", _rep(_setdd(branches=["b2-b3-1", "b1-b2-1"])), None, None),
    ("branches differ", _rep(_setdd(branches=["b1-b2-1"])), "failure", "branches"),
    ("branches missing", _rep(_setdd(branches=None)), "failure", "branches"),
    ("rate_before reordered", _rep(_setdd(rate_before_mva=[600.0, 500.0])), None, None),
    ("rate_before None both", _both(_setdd(rate_before_mva=None)), None, None),
    ("rate_before None one", _rep(_setdd(rate_before_mva=None)), "failure", "rate_before"),
    ("rate_before differs", _rep(_setdd(rate_before_mva=[500.0, 700.0])), "failure",
     "rate_before"),
    ("rate_before length", _rep(_setdd(rate_before_mva=[500.0])), "failure", "rate_before"),
    ("sink_buses reordered", _rep(_setmd(sink_buses=["s2", "s1"])), None, None),
    ("sink_buses differ", _rep(_setmd(sink_buses=["s1"])), "failure", "sink_buses"),
    ("step differs", _rep(_setmd(step_mw=50.0)), "failure", "search_settings"),
    ("tolerance differs", _rep(_setmd(tolerance_mw=0.5)), "failure", "search_settings"),
    ("criterion differs", _rep(_setmd(criterion_pu=0.92)), "failure", "search_settings"),
    ("step missing recorded", _rec(_drop_key("step_mw")), "failure", "search_settings"),
    ("step zero both", _both(_setmd(step_mw=0.0)), "failure", "search_settings"),
    ("tolerance not finite", _both(_setmd(tolerance_mw=float("nan"))), "failure",
     "search_settings"),
    ("rate_set differs", lambda rec, rep: rep["run"].update(rate_set=2), "failure", "rate_set"),
    ("limit inside", _rep(_setv(0, limit_value=1000.0 * (1 + 1e-10))), None, None),
    ("limit outside", _rep(_setv(0, limit_value=1000.001)), "failure", "limit_value"),
    ("element city", _rep(_setv(0, city="MIDLAND")), "failure", "element_fields"),
    ("element type", _rep(_setv(0, element_type="bus")), "failure", "element_fields"),
    ("element unit", _rep(_setv(0, unit="pu")), "failure", "element_fields"),
    ("n_contingencies", lambda rec, rep: rep["run"].update(n_contingencies=9), "failure",
     "n_contingencies"),
    # shape: nothing raises
    ("duplicate key replayed", _rep(lambda rows: rows["contingencies"].append(
        dict(rows["contingencies"][0]))), "failure", "duplicate_key"),
    ("duplicate key recorded", _rec(lambda rows: rows["contingencies"].append(
        dict(rows["contingencies"][0]))), "failure", "duplicate_key"),
    ("repeated city", _rep(lambda rows: rows["margins"].append(dict(rows["margins"][0]))),
     "failure", "city_rows"),
    ("missing dispatch city", _rec(lambda rows: rows["dispatch"].pop()), "failure",
     "city_rows"),
    ("missing margin city", _rep(lambda rows: rows["margins"].pop()), "failure", "city_rows"),
    # violation values, both sides of each tolerance
    ("voltage 0.01 passes", _rep(_setv(1, observed_value=0.86)), None, None),
    ("voltage 0.0101 fails", _rep(_setv(1, observed_value=0.8601)), "failure", "value_voltage"),
    ("voltage below also", _rep(_setv(1, observed_value=0.84)), None, None),
    ("voltage below fails", _rep(_setv(1, observed_value=0.8399)), "failure", "value_voltage"),
    ("flow 2 percent passes", _rep(_setv(0, observed_value=1122.0)), None, None),
    ("flow 2.1 percent fails", _rep(_setv(0, observed_value=1123.1)), "failure",
     "value_thermal"),
    ("floor 2 MVA passes", _all(_both(_small_flow), _rep(_setv(0, observed_value=52.0))),
     None, None),
    ("floor 2.1 MVA fails", _all(_both(_small_flow), _rep(_setv(0, observed_value=52.1))),
     "failure", "value_thermal"),
    ("value not finite", _rep(_setv(0, observed_value=float("nan"))), "failure",
     "value_thermal"),
    # one-sided rows: borderline inside the band, a failure outside it
    ("recorded-only voltage_high 0.01 borderline", _rec(_add(_BORDER_VH)), "borderline",
     "set_one_sided"),
    ("recorded-only voltage_high 0.011 fails", _rec(_add(_BORDER_VH_OUT)), "failure",
     "set_one_sided"),
    ("replayed-only thermal at the allowance borderline", _rep(_add(_BORDER_TH)),
     "borderline", "set_one_sided"),
    ("replayed-only thermal 1.01 times fails", _rep(_add(_BORDER_TH_OUT)), "failure",
     "set_one_sided"),
    ("recorded-only thermal at the allowance borderline", _rec(_add(_BORDER_TH)),
     "borderline", "set_one_sided"),
    ("recorded-only non_convergence", _rec(_add(_LONE_NC)), "failure", "convergence_one_sided"),
    ("replayed-only non_convergence", _rep(_add(_LONE_NC)), "failure", "convergence_one_sided"),
    # margin classes
    ("member differs only", _rep(_setmd(bounded_by="non_convergence")), None, None),
    ("rating against voltage", _rep(_setmd(bounded_by="dlr_rating")), "failure",
     "margin_bound_class"),
    ("base against voltage", _rep(_setmd(bounded_by="base_case")), "failure",
     "margin_bound_class"),
    ("bounded_by missing", _rep(_drop_key("bounded_by")), "failure", "margin_bound_class"),
    ("bounded_by unknown", _both(_setmd(bounded_by="other")), "failure", "margin_bound_class"),
    ("critical bus differs only", _rep(_setm(critical_bus="bus-z")), None, None),
    # margin values (D-02): voltage class, recorded margin 600, tolerance 1
    ("voltage-bound 612 passes", _rep(_setm(margin_mw=612.0)), None, None),
    ("voltage-bound 612.5 fails", _rep(_setm(margin_mw=612.5)), "failure", "margin_value"),
    ("voltage-bound 588 passes", _rep(_setm(margin_mw=588.0)), None, None),
    ("voltage-bound 587.5 fails", _rep(_setm(margin_mw=587.5)), "failure", "margin_value"),
    ("voltage-bound small margin floor is the tolerance 11",
     _all(_both(_setm(margin_mw=10.0)), _rep(_setm(margin_mw=11.0))), None, None),
    ("voltage-bound small margin 11.5 fails",
     _all(_both(_setm(margin_mw=10.0)), _rep(_setm(margin_mw=11.5))), "failure",
     "margin_value"),
    ("voltage-bound small margin never gets the step",
     _all(_both(_setm(margin_mw=10.0)), _rep(_setm(margin_mw=12.0))), "failure",
     "margin_value"),
    ("limit_transfer 816 passes", _rep(_setm(limit_transfer_mw=816.0)), None, None),
    ("limit_transfer 816.5 fails", _rep(_setm(limit_transfer_mw=816.5)), "failure",
     "margin_value"),
    ("base_transfer 204 passes", _rep(_setm(base_transfer_mw=204.0)), None, None),
    ("base_transfer 204.1 fails", _rep(_setm(base_transfer_mw=204.1)), "failure",
     "margin_value"),
    ("min_voltage 0.01 passes", _rep(_setm(min_voltage_pu=0.94)), None, None),
    ("min_voltage 0.0101 fails", _rep(_setm(min_voltage_pu=0.9401)), "failure", "margin_value"),
    ("voltage_limit 2 percent passes", _rep(_setm(voltage_limit_mva=867.0)), None, None),
    ("voltage_limit 2.1 percent fails", _rep(_setm(voltage_limit_mva=867.85)), "failure",
     "margin_value"),
    # rating class, recorded margin 400, step 25
    ("rating-bound 425 passes",
     _all(_rating_class(400.0), _rep(_setm(margin_mw=425.0))), None, None),
    ("rating-bound 426 fails",
     _all(_rating_class(400.0), _rep(_setm(margin_mw=426.0))), "failure", "margin_value"),
    ("rating-bound 375 passes",
     _all(_rating_class(400.0), _rep(_setm(margin_mw=375.0))), None, None),
    ("rating-bound 374 fails",
     _all(_rating_class(400.0), _rep(_setm(margin_mw=374.0))), "failure", "margin_value"),
    ("rating-bound large margin 2040 passes (2 percent wins)",
     _all(_rating_class(2000.0), _rep(_setm(margin_mw=2040.0))), None, None),
    ("rating-bound large margin 2041 fails",
     _all(_rating_class(2000.0), _rep(_setm(margin_mw=2041.0))), "failure", "margin_value"),
    ("rating-bound quantised voltage figures are not compared",
     _all(_rating_class(400.0), _rep(_setm(min_voltage_pu=0.5, voltage_limit_mva=5000.0))),
     None, None),
    # dispatch
    ("dispatched 816 passes", _rep(_setd(dispatched_mva=816.0)), None, None),
    ("dispatched 816.5 fails", _rep(_setd(dispatched_mva=816.5)), "failure", "dispatch_value"),
    ("dispatch voltage limit 816 passes", _rep(_setd(voltage_limit_mva=816.0)), None, None),
    ("dispatch voltage limit 817 fails", _rep(_setd(voltage_limit_mva=817.0)), "failure",
     "dispatch_value"),
    ("rating-limited voltage limits not compared",
     _all(_both(_rows_for_dispatch_factor), _rep(_setd(voltage_limit_mva=5000.0))), None,
     None),
    ("factor differs near the limit",
     _all(_rec(_setd(voltage_limit_mva=980.0, dispatched_mva=980.0)),
          _rep(_setd(limiting_factor="dlr_rating", voltage_limit_mva=1100.0,
                     dispatched_mva=1000.0))), "borderline", "limiting_factor"),
    ("factor differs outside the band",
     _all(_rec(_setd(voltage_limit_mva=979.0, dispatched_mva=979.0)),
          _rep(_setd(limiting_factor="dlr_rating", voltage_limit_mva=1100.0,
                     dispatched_mva=1000.0))), "failure", "limiting_factor"),
    ("factor unknown", _rep(_setd(limiting_factor="other")), "failure", "limiting_factor"),
]


def _ids(rows):
    return [row[0] for row in rows]


def _produced(mutate):
    comparison = agree.compare_run(*_pair(mutate))
    return comparison, set((item.klass, item.check) for item in comparison.findings)


@pytest.mark.parametrize("name,mutate,klass,check", MATRIX, ids=_ids(MATRIX))
def test_rule_matrix(name, mutate, klass, check):
    comparison, produced = _produced(mutate)
    if klass is None:
        assert produced == set() and comparison.passed
    else:
        assert (klass, check) in produced
        if klass == "failure":
            assert not comparison.passed
        else:
            assert comparison.counts["borderline"] >= 1


def test_every_check_word_is_produced_by_the_matrix():
    seen = set()
    for _, mutate, _, _ in MATRIX:
        seen |= set(check for _, check in _produced(mutate)[1])
    assert seen == set(agree.CHECK_WORDS) - {"replay_failed"}


def test_borderline_alone_passes_and_is_counted_with_its_excess():
    comparison, produced = _produced(_rep(_add(_BORDER_TH)))
    assert produced == {("borderline", "set_one_sided")}
    assert comparison.passed and comparison.counts["borderline"] == 1
    item = comparison.findings[0]
    assert item.detail["band"] == compare.flow_allowance(1000.0)
    assert item.detail["excess"] <= item.detail["band"]
    comparison, produced = _produced(_all(
        _rec(_setd(voltage_limit_mva=999.0, dispatched_mva=999.0)),
        _rep(_setd(limiting_factor="dlr_rating", voltage_limit_mva=1100.0,
                   dispatched_mva=1000.0))))
    assert produced == {("borderline", "limiting_factor")} and comparison.passed


def test_different_data_is_never_borderline():
    for name, mutate, klass, check in MATRIX:
        if check in agree.DATA_CHECK_WORDS or check in ("margin_bound_class", "n_contingencies"):
            assert klass == "failure", name


def test_notes_are_counted():
    comparison, _ = _produced(_rep(_setmd(bounded_by="non_convergence")))
    assert comparison.notes == {"bound_member_differs": 1, "critical_bus_differs": 0}
    comparison, _ = _produced(_rep(_setm(critical_bus="bus-z")))
    assert comparison.notes == {"bound_member_differs": 0, "critical_bus_differs": 1}
    assert set(comparison.notes) == set(agree.NOTE_WORDS)


def test_margin_counts_and_quantisation():
    comparison, _ = _produced(None)
    assert comparison.counts["margin_quantised"] == 0
    assert comparison.counts["margin_comparisons"] == 5 * len(CITIES)
    assert comparison.counts["dispatch_comparisons"] == len(CITIES)
    assert comparison.counts["dispatch_informative"] == len(CITIES)
    comparison, _ = _produced(_rating_class(400.0))
    assert comparison.counts["margin_quantised"] == 1
    assert comparison.counts["margin_comparisons"] == 5 * len(CITIES) - 2


def test_margin_allowance_is_the_larger_of_two_things():
    assert agree.margin_allowance(600.0, 1.0) == compare.FLOW_RELATIVE_TOLERANCE * 600.0
    assert agree.margin_allowance(400.0, 25.0) == 25.0
    assert agree.margin_allowance(2000.0, 25.0) == compare.FLOW_RELATIVE_TOLERANCE * 2000.0
    assert agree.margin_allowance(-2000.0, 25.0) == agree.margin_allowance(2000.0, 25.0)


def test_utilisation_is_deviation_over_its_own_allowance():
    comparison, _ = _produced(None)
    assert all(item.utilisation == 0 for item in comparison.worst.values())
    comparison, _ = _produced(_rep(_setv(0, observed_value=1111.0)))
    assert comparison.passed
    worst = comparison.worst["thermal_mva"]
    assert worst.deviation == pytest.approx(11.0)
    assert worst.allowance == compare.flow_allowance(1100.0)
    assert worst.utilisation == pytest.approx(0.5)
    assert worst.where[0] == "AUSTIN:out01"
    assert comparison.worst["voltage_pu"].utilisation == 0
    comparison, _ = _produced(_rep(_setv(1, observed_value=0.855)))
    assert comparison.worst["voltage_pu"].utilisation == pytest.approx(0.5)


def test_worst_keeps_the_largest_utilisation_per_quantity():
    def two_changes(rec, rep):
        rep["margins"][0]["margin_mw"] = 606.0
        rep["margins"][1]["margin_mw"] = 609.0

    comparison, _ = _produced(two_changes)
    assert comparison.passed
    assert comparison.worst["margin_mw"].utilisation == pytest.approx(0.75)
    assert comparison.worst["margin_mw"].where == ("margins", CITIES[1])


def test_compare_run_never_raises_on_malformed_sides():
    def broken(rec, rep):
        rep["dispatch"] = []
        rep["margins"][0]["details"] = None
        rep["contingencies"][0]["observed_value"] = None
        rep["contingencies"].append({"contingency_id": "X", "violation_kind": "other"})

    comparison, produced = _produced(broken)
    assert not comparison.passed
    assert {"city_rows", "search_settings", "value_thermal", "element_fields"} <= set(
        check for _, check in produced)


# -- Task 3: the gate (D-04), the counts-only summary, the private detail, the proofs -------------


def _comparison(mutate=None):
    return agree.compare_run(*_pair(mutate))


def _empty(rec, rep):
    rec["contingencies"] = []
    rep["contingencies"] = []


def _gate(compared, exclusions=(), runs=None):
    return agree.gate(list(compared), list(exclusions),
                      len(compared) + len(exclusions) if runs is None else runs, 1)


def test_gate_pass_fail_incomplete():
    assert _gate([("r1", _comparison())]).word == "pass"
    assert _gate([("r1", _comparison()), ("r2", _comparison())]).word == "pass"
    failing = _comparison(_rep(_setv(0, observed_value=1200.0)))
    assert _gate([("r1", _comparison()), ("r2", failing)]).word == "fail"


def test_gate_incomplete_is_never_pass():
    assert _gate([]).word == "incomplete"
    assert _gate([], [("r1", "mapping_hash_differs"), ("r2", "failed_run")]).word == "incomplete"
    assert _gate([("r1", _comparison(_empty))]).word == "incomplete"
    gated = _gate([("r1", _comparison(_empty))], [("r2", "case_hash_missing")])
    assert gated.word == "incomplete"
    assert gated.summary.word == "incomplete" and gated.summary.runs_replayed == 1


def test_gate_failure_beats_incomplete():
    assert _gate([("r1", _comparison(_empty)), ("r2", agree.replay_failed("load_flow"))]
                 ).word == "fail"
    assert _gate([("r1", agree.replay_failed("mapping"))]).word == "fail"
    # a failure with nothing non-empty compared anywhere
    broken = _comparison(lambda rec, rep: (_empty(rec, rep), rep["run"].update(rate_set=9)))
    assert _gate([("r1", broken)]).word == "fail"


def test_gate_lists_kinds_not_exercised():
    summary = _gate([("r1", _comparison())]).summary
    assert summary.not_exercised == ("voltage_high",)
    assert summary.nonempty == {"thermal_overload": 1, "voltage_low": 1, "voltage_high": 0,
                                "non_convergence": 1}
    summary = _gate([("r1", _comparison(_empty))]).summary
    assert summary.not_exercised == agree.KINDS
    assert set(summary.nonempty) == set(agree.KINDS)
    summary = _gate([("r1", _comparison(_rec(_add(_BORDER_VH))))]).summary
    assert summary.not_exercised == ()
    assert _gate([]).summary.not_exercised == agree.KINDS


def test_gate_counts_every_exclusion_reason_zeros_included():
    summary = _gate([("r1", _comparison())]).summary
    assert summary.excluded == dict.fromkeys(agree.EXCLUSION_REASONS, 0)
    reasons = list(agree.EXCLUSION_REASONS)
    summary = _gate([("r1", _comparison())], [("x%d" % n, why) for n, why in enumerate(reasons)]
                    ).summary
    assert summary.excluded == dict.fromkeys(agree.EXCLUSION_REASONS, 1)
    summary = _gate([], [("a", "failed_run"), ("b", "failed_run")]).summary
    assert summary.excluded["failed_run"] == 2 and summary.runs_in_snapshot == 2
    with pytest.raises(ValueError):
        _gate([], [("a", "no_such_reason")])


def test_gate_summary_counts():
    passing, failing = _comparison(), _comparison(_rep(_setv(0, observed_value=1200.0)))
    borderline = _comparison(_rep(_add(_BORDER_TH)))
    summary = agree.gate([("a", passing), ("b", failing), ("c", borderline)], [], 5, 3).summary
    assert (summary.runs_in_snapshot, summary.runs_replayed, summary.runs_passed,
            summary.runs_failed, summary.configurations) == (5, 3, 2, 1, 3)
    assert summary.borderline == 1
    assert summary.pairs_compared == passing.counts["pairs_compared"] * 3
    assert summary.dispatch_comparisons == 3 * len(CITIES)
    assert summary.margin_comparisons == 3 * 5 * len(CITIES)


def test_three_failure_counts_are_kept_apart():
    mapping = _gate([("r", agree.replay_failed("mapping"))]).summary
    assert mapping.failed_stages["mapping"] == 1 and sum(mapping.failed_stages.values()) == 1
    assert mapping.runs_disagreeing == 0 and sum(mapping.data_differences.values()) == 0
    assert set(mapping.failed_stages) == set(constants.FAILED_STAGES)
    assert set(mapping.data_differences) == set(agree.DATA_CHECK_WORDS)

    for mutate, word in ((_rep(_setd(rating_source="static")), "rating_data"),
                         (_rep(_setmd(step_mw=50.0)), "search_settings"),
                         (_rep(_setdd(branches=["b1-b2-1"])), "branches")):
        summary = _gate([("r", _comparison(mutate))]).summary
        assert summary.data_differences[word] == 1
        assert sum(summary.data_differences.values()) == 1
        assert summary.runs_disagreeing == 0
        assert sum(summary.failed_stages.values()) == 0

    for mutate in (_rep(_setv(0, observed_value=1200.0)), _rec(_add(_BORDER_VH_OUT)),
                   _rep(_setm(margin_mw=700.0)), _rep(_add(_LONE_NC)),
                   _rep(_setd(dispatched_mva=900.0))):
        summary = _gate([("r", _comparison(mutate))]).summary
        assert summary.runs_disagreeing == 1
        assert sum(summary.data_differences.values()) == 0
        assert sum(summary.failed_stages.values()) == 0

    both = _comparison(_all(_rep(_setd(rating_source="static")),
                            _rep(_setv(0, observed_value=1200.0))))
    summary = _gate([("r", both)]).summary
    assert summary.data_differences["rating_data"] == 1 and summary.runs_disagreeing == 1


def test_replay_failed_is_a_failed_run_with_zero_counts():
    comparison = agree.replay_failed("contingency")
    assert not comparison.passed
    assert [(item.klass, item.check, item.detail) for item in comparison.findings] == [
        ("failure", "replay_failed", "contingency")]
    assert comparison.counts == dict.fromkeys(agree.COMPARE_COUNT_KEYS, 0)
    assert comparison.worst == {}
    unknown = _gate([("r", agree.replay_failed("not a stage"))]).summary
    assert unknown.failed_stages["internal"] == 1
    assert sum(unknown.failed_stages.values()) == 1
    assert _gate([("r", comparison)]).summary.runs_failed == 1


def _leaves(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            for leaf in _leaves(item):
                yield leaf
    elif isinstance(value, (tuple, list)):
        for item in value:
            for leaf in _leaves(item):
                yield leaf
    else:
        yield value


def test_summary_is_counts_and_fixed_words_only():
    run_id = "run-secret-id-77"
    changed = _comparison(_rep(_setv(0, observed_value=1234.5678)))
    gated = agree.gate([(run_id, changed), ("run-two", _comparison(_rep(_add(_BORDER_TH)))),
                        ("run-three", agree.replay_failed("dispatch"))],
                       [("run-four", "failed_run")], 4, 2)
    words = (set(agree.VERDICT_WORDS) | set(agree.EXCLUSION_REASONS) | set(agree.KINDS)
             | set(constants.FAILED_STAGES) | set(agree.DATA_CHECK_WORDS))
    fields = set(agree.Summary._fields)
    for name, value in gated.summary.as_dict().items():
        assert name in fields
        for leaf in _leaves(value):
            assert not isinstance(leaf, (float, bool))
            assert isinstance(leaf, int) or leaf in words
    text = repr(gated.summary.as_dict()) + repr(gated.summary)
    for secret in (run_id, "run-two", "run-four", "1234", "AUSTIN", "out01", "br1"):
        assert secret not in text
    # the value and the id are in the private detail
    assert run_id in repr(gated.detail)
    # the summary cannot be made to carry a figure, an id or an element
    good = gated.summary._asdict()
    for bad in (0.5, run_id, "AUSTIN", True, None, {run_id: 1}, ("br1",)):
        with pytest.raises(ValueError):
            agree.Summary(**dict(good, borderline=bad))


def test_detail_largest_deviation_is_kept_on_a_pass():
    small = _comparison(_rep(_setv(0, observed_value=1111.0)))
    gated = _gate([("r1", _comparison()), ("r2", small)])
    assert gated.word == "pass"
    largest = gated.detail.largest
    assert largest.quantity == "thermal_mva"
    assert largest.deviation == pytest.approx(11.0)
    assert 0 < largest.utilisation < 1
    assert largest.where[0] == "r2"
    assert gated.detail.worst["thermal_mva"] == largest
    assert set(gated.detail.worst) <= set(agree.QUANTITIES)
    assert gated.detail.findings == [] and gated.detail.exclusions == []
    assert _gate([]).detail.largest is None
    assert _gate([("r1", agree.replay_failed("write"))]).detail.largest is None


def test_detail_holds_findings_exclusions_borderline_and_notes():
    borderline = _comparison(_all(_rep(_add(_BORDER_TH)),
                                  _rep(_setmd(bounded_by="non_convergence"))))
    failing = _comparison(_rep(_setm(critical_bus="bus-z", margin_mw=700.0)))
    gated = agree.gate([("r1", borderline), ("r2", failing)], [("r3", "ratings_unusable")], 3, 1)
    detail = gated.detail
    assert [(run_id, item.klass, item.check) for run_id, item in detail.findings] == [
        ("r1", "borderline", "set_one_sided"), ("r2", "failure", "margin_value")]
    assert detail.exclusions == [("r3", "ratings_unusable")]
    assert detail.notes == {"bound_member_differs": 1, "critical_bus_differs": 1}
    near = detail.borderline_largest
    assert near.where == ("r1", ("AUSTIN:out04", "thermal_overload", "br2"))
    assert near.utilisation == pytest.approx(1.0)
    assert _gate([("r1", _comparison())]).detail.borderline_largest is None


def test_tolerance_header_reads_compare_by_name():
    header = agree.tolerance_header()
    assert header["voltage_tolerance_pu"] == compare.VOLTAGE_TOLERANCE_PU
    assert header["flow_relative_tolerance"] == compare.FLOW_RELATIVE_TOLERANCE
    assert header["flow_floor_mva"] == compare.FLOW_FLOOR_MVA
    assert header["comparison_epsilon"] == compare.COMPARISON_EPSILON
    assert header["data_relative_tolerance"] == agree.DATA_RELATIVE_TOLERANCE
    assert "stored step" in header["margin_rule"] and "stored tolerance" in header["margin_rule"]
    assert "2 percent" in header["margin_rule"]
    assert "borderline" in header["borderline_rule"]
    assert agree.margin_allowance(1000.0, 0.0) == header["flow_relative_tolerance"] * 1000.0


def _agree_source():
    with open(agree.__file__, encoding="utf-8") as handle:
        return handle.read()


def _stray_tolerances(source):
    tree = ast.parse(source)
    wanted = {compare.VOLTAGE_TOLERANCE_PU, compare.FLOW_RELATIVE_TOLERANCE,
              compare.FLOW_FLOOR_MVA, compare.COMPARISON_EPSILON}
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and not isinstance(node.value, (str, bytes, bool))
            and isinstance(node.value, (int, float)) and node.value in wanted]


def test_no_second_tolerance_literal_in_agree():
    source = _agree_source()
    assert _stray_tolerances(source) == []
    for planted in ("0.01", "0.02", "2.0", "1e-12", "2"):
        assert len(_stray_tolerances(source + "\nSTRAY = %s\n" % planted)) == 1, planted
    tree = ast.parse(source)
    used = set(node.attr for node in ast.walk(tree)
               if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
               and node.value.id == "compare")
    assert {"VOLTAGE_TOLERANCE_PU", "FLOW_RELATIVE_TOLERANCE", "within_voltage", "within_flow",
            "flow_allowance", "COMPARISON_EPSILON"} <= used
    assert source.count("compare.") >= 5
    # no flag or override takes a tolerance
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            names = [arg.arg for arg in node.args.args + node.args.kwonlyargs]
            assert not [name for name in names if "toler" in name or "epsilon" in name], node.name


def test_agree_is_pure():
    tree = ast.parse(_agree_source())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= set(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported |= set("%s.%s" % (node.module, alias.name) for alias in node.names)
    assert imported == {"collections", "math", "pandapower_job.compare", "psse_job.constants"}

    backend = os.path.dirname(os.path.dirname(os.path.abspath(agree.__file__)))
    code = (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import pandapower_job.agree\n"
        "print(json.dumps(sorted(n for n in sys.modules if n.split('.')[0] in json.loads("
        "sys.argv[2]))))\n"
    )
    names = ["pandapower", "psycopg", "psycopg2", "numpy", "pandas", "psse_job",
             "pandapower_job"]
    done = subprocess.run(
        [sys.executable, "-I", "-c", code, backend, json.dumps(names)],
        capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-500:]
    loaded = json.loads(done.stdout.strip().splitlines()[-1])
    assert loaded == ["pandapower_job", "pandapower_job.agree", "pandapower_job.compare",
                      "psse_job", "psse_job.constants"]
