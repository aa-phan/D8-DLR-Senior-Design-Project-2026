"""
Tests for the agreement rules (pandapower-solver Phase 4, plan 04-02: AGR-02 and AGR-03; decisions
D-02 and D-04).

Pure: no solver, no database. Every row here is hand-built and synthetic (no figure and no bus
number of the real network); these tests prove the comparison rules and the gate, never agreement
between PSS/E and pandapower. Follows `pandapower_compare_test.py`. Failure messages are counts
only.
"""

import copy

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


def _pair(mutate=None, on="replayed"):
    """A recorded and a replayed Side from deep copies of _rows(); `mutate(rows)` changes one."""
    recorded_rows, replayed_rows = _rows(), copy.deepcopy(_rows())
    if mutate is not None:
        mutate(replayed_rows if on == "replayed" else recorded_rows)
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

    def three_percent(rows):
        rows["contingencies"][0]["observed_value"] *= 1.03

    changed = agree.compare_run(*_pair(three_percent))
    assert not changed.passed
    assert _failures(changed) == ["value_thermal"]
    assert agree.gate([("run", changed)], [], 1, 1).word == "fail"
