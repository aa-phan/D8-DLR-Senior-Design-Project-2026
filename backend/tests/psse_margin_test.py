"""
Tests for the voltage-stability margin and the dispatched capacity (pss-e-integration Phase 2,
plan 02-05): STU-03 and STU-04 against the fake psspy and an analytic two-bus model. The margin
is a transfer search on plain load flows; the dispatched capacity is the lower of the applied DLR
rating and the voltage-stability limit.

Follows backend/tests/psse_contract_test.py's conventions (module-level imports, plain asserts,
no test classes, no network). Honest scope: the fake proves call order, value flow and failure
handling, not that real PSS/E accepts these calls (the Phase 3 probe does).
"""

import copy
import datetime
import json
import math
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
import psse_fakes  # noqa: E402
from psse_job import (  # noqa: E402
    constants, contract, dispatch, mapping, margin, ratings, run_record, study,
)

EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
NOW = datetime.datetime(2026, 10, 28, 12, 20, 0, tzinfo=datetime.timezone.utc)


def _registered(tmp_path, case=None, solver=None, fake=None):
    """(fake, case path): the case registered under a path whose file holds a marker."""
    fake = fake_module.FakePsspy(solver=solver) if fake is None else fake
    path = str(tmp_path / "PLACEHOLDER_CASE.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(path, fake_module.placeholder_case() if case is None else case)
    return fake, path


def _mapping(**changes):
    """The example mapping (placeholder allowed) with study settings replaced by `changes`."""
    loaded = mapping.load_mapping(EXAMPLE, allow_placeholder=True)
    return loaded._replace(settings=loaded.settings._replace(**changes))


def _selection(provisional=True):
    rows = psse_fakes.latest_rows(NOW, provisional=provisional)
    return ratings.select_ratings(psse_fakes.fake_fetch(rows), NOW)


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


@pytest.fixture
def prepared(tmp_path):
    """prepare_base(...) -> (fake, case path, base); every base made is cleaned up afterwards."""
    made = []

    def run(case=None, solver=None, fake=None, mapping_=None, selection=None, budget=None):
        fake, path = _registered(tmp_path, case=case, solver=solver, fake=fake)
        base = study.prepare_base(
            fake, path, _mapping() if mapping_ is None else mapping_,
            _selection() if selection is None else selection, budget=budget)
        made.append(base)
        return fake, path, base

    yield run
    for base in made:
        study.cleanup_base(base)


def test_tracer_austin_margin_and_dispatch_validate(prepared):
    selection = _selection()
    fake, path, base = prepared(selection=selection)
    result = margin.city_margin(base, "AUSTIN")
    row = result.row
    assert result.bounded_by == "voltage_criterion"
    assert set(row) == set(contract.MARGIN_COLUMNS) - set(["run_id", "run_outcome"])
    assert row["city"] == "AUSTIN"
    assert row["method"] == "pv_curve"
    assert row["base_transfer_mw"] == pytest.approx(310.0)
    assert 474.0 <= row["limit_transfer_mw"] <= 475.0
    assert row["margin_mw"] == pytest.approx(row["limit_transfer_mw"] - row["base_transfer_mw"])
    assert 499.0 <= row["voltage_limit_mva"] <= 500.0
    assert result.voltage_limit_mva == row["voltage_limit_mva"]
    assert row["critical_bus"] == "90002"
    assert row["min_voltage_pu"] >= 0.90
    assert row["details"]["bounded_by"] == "voltage_criterion"
    assert row["details"]["extended_past_cap"] is False
    assert row["details"]["lower_bound"] is False

    assert dispatch.POWER_FACTOR_DEFAULT == 0.95
    choice = selection.choices["AUSTIN"]
    dispatched = dispatch.build_dispatch_row(
        choice, 345.0, result.voltage_limit_mva, bounded_by=result.bounded_by)
    assert set(dispatched) == set(contract.DISPATCH_COLUMNS) - set(["run_id", "run_outcome"])
    assert dispatched["limiting_factor"] == "voltage_stability"
    assert dispatched["dispatched_mva"] == result.voltage_limit_mva
    assert dispatched["dispatched_mw"] == pytest.approx(0.95 * dispatched["dispatched_mva"])
    assert dispatched["voltage_limit_mva"] == row["voltage_limit_mva"]
    assert dispatched["rating_source"] == "static_fallback"
    assert dispatched["city_rating_valid_time"] is None
    assert dispatched["city_rating_computed_at"] is None

    template = psse_fakes.fake_results(selection)
    swap_dispatch = [dispatched if r["city"] == "AUSTIN" else r for r in template.dispatch]
    swap_margins = [row if r["city"] == "AUSTIN" else r for r in template.margins]
    results = contract.StudyResults(
        dispatch=swap_dispatch, margins=swap_margins, contingencies=template.contingencies,
        n_contingencies=template.n_contingencies, rate_set="RATEA", psse_version="35.6.0")
    run_record.validate_results(results, selection)
    json.dumps(row["details"], allow_nan=False)


# ──────────────────────────────────────────────────────────────────────────────
# The search as a pure function: an analytic two-bus model and synthetic evaluators
# ──────────────────────────────────────────────────────────────────────────────

# Source E behind reactance X feeding a load of constant power factor 0.95 (research
# "Closed-form model for the one physical fake test"): V^2 = (E^2/2 - QX) + sqrt((E^2/2 - QX)^2
# - X^2 (P^2 + Q^2)); the load flow converges exactly when the discriminant is not negative,
# and the sending-end apparent flow is E x |S| / V. Quantities are per unit on a 100 MVA base.
_E = 1.0
_X = 0.2
_TAN = math.tan(math.acos(0.95))
_MVA_BASE = 100.0


def _two_bus(total_mw):
    """(converged, voltage_pu, sending_mva) of the two-bus model at `total_mw` of load."""
    p = total_mw / _MVA_BASE
    q = p * _TAN
    half = _E * _E / 2.0 - q * _X
    discriminant = half * half - _X * _X * (p * p + q * q)
    if discriminant < 0.0:
        return False, None, None
    voltage = math.sqrt(half + math.sqrt(discriminant))
    return True, voltage, _E * math.hypot(p, q) / voltage * _MVA_BASE


def _independent_nose_mw():
    """The nose of the model, by bisection on the discriminant (not by the code under test)."""
    lo, hi = 0.0, 1000.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if _two_bus(mid)[0]:
            lo = mid
        else:
            hi = mid
    return lo


def _independent_mw_at_voltage(target):
    """The load at which the upper-branch voltage equals `target`, by bisection."""
    lo, hi = 0.0, _independent_nose_mw()
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if _two_bus(mid)[1] >= target:
            lo = mid
        else:
            hi = mid
    return lo


def _two_bus_evaluate(base_mw, criterion=None):
    def evaluate(increment):
        converged, voltage, sending = _two_bus(base_mw + increment)
        if not converged:
            return margin.Point(False, False, "non_convergence", increment, None, None, None, None)
        if criterion is not None and voltage < criterion:
            return margin.Point(False, True, "voltage_criterion", increment, sending, sending,
                                voltage, "2")
        return margin.Point(True, True, None, increment, sending, sending, voltage, "2")
    return evaluate


def test_search_two_bus_nose_within_tolerance():
    nose = _independent_nose_mw()
    assert nose == pytest.approx(180.99, abs=0.01)
    limit = margin.find_transfer_limit(
        _two_bus_evaluate(50.0), 25.0, 400.0, 1.0, math.inf, 80)
    assert limit.bounded_by == "non_convergence"
    total = 50.0 + limit.good.transfer_mw
    assert nose - 1.0 < total <= nose
    assert limit.good.ok and limit.good.min_voltage_pu > 0.6
    assert limit.first_bad_mw - limit.good.transfer_mw <= 1.0
    assert limit.extended is False


def test_search_two_bus_voltage_criterion():
    point_090 = _independent_mw_at_voltage(0.90)
    assert point_090 < _independent_nose_mw()
    limit = margin.find_transfer_limit(
        _two_bus_evaluate(50.0, criterion=0.90), 25.0, 400.0, 1.0, math.inf, 80)
    assert limit.bounded_by == "voltage_criterion"
    total = 50.0 + limit.good.transfer_mw
    assert point_090 - 1.0 < total <= point_090
    assert limit.good.min_voltage_pu >= 0.90


def _synthetic(ok_below, reason, flow_slope=1.0):
    """An evaluator that is good below `ok_below` MW and bad (with `reason`) from there on; the
    mapped flow is flow_slope x the increment plus 10 MVA."""
    calls = []

    def evaluate(increment):
        calls.append(increment)
        if increment < ok_below:
            return margin.Point(True, True, None, increment, 100.0 + increment,
                                10.0 + flow_slope * increment, 0.99, "2")
        return margin.Point(False, reason != "non_convergence", reason, increment, None, None,
                            None, None)
    evaluate.calls = calls
    return evaluate


@pytest.mark.parametrize("scenario", [
    "base_case", "dlr_rating_walk", "dlr_rating_after_cap", "non_convergence",
    "voltage_criterion",
])
def test_search_bounded_by_variants(scenario):
    if scenario == "base_case":
        evaluate = _synthetic(0.0, "voltage_criterion")
        limit = margin.find_transfer_limit(evaluate, 25.0, 400.0, 1.0, 1e9, 80)
        assert limit.bounded_by == "base_case"
        assert limit.good is limit.base and not limit.base.ok
        assert limit.evaluations == 1 and evaluate.calls == [0.0]
        assert limit.first_bad_mw == 0.0 and limit.extended is False
    elif scenario == "dlr_rating_walk":
        evaluate = _synthetic(1e9, None)
        limit = margin.find_transfer_limit(evaluate, 25.0, 400.0, 1.0, 60.0, 80)
        assert limit.bounded_by == "dlr_rating"
        assert limit.good.transfer_mw == 50.0 and limit.good.max_flow_mva == 60.0
        assert limit.evaluations == 3 and limit.extended is False
        assert limit.first_bad_mw is None
    elif scenario == "dlr_rating_after_cap":
        evaluate = _synthetic(1e9, None)
        limit = margin.find_transfer_limit(evaluate, 25.0, 100.0, 1.0, 160.0, 10)
        assert limit.bounded_by == "dlr_rating"
        assert limit.good.transfer_mw == 150.0
        assert limit.evaluations == 7 and limit.extended is True
    else:
        evaluate = _synthetic(130.0, scenario)
        limit = margin.find_transfer_limit(evaluate, 25.0, 400.0, 1.0, 1e9, 80)
        assert limit.bounded_by == scenario
        assert 129.0 <= limit.good.transfer_mw < 130.0
        assert 130.0 <= limit.first_bad_mw <= limit.good.transfer_mw + 1.0
        assert limit.extended is False
    assert limit.bounded_by in ("base_case", "dlr_rating", "non_convergence", "voltage_criterion")
    assert limit.bounded_by != "max_transfer"


def test_search_dlr_rating_reached_during_bisection():
    # Good below 120 MW, mapped flow 10 + d MVA, rating 126 MVA. The walk (25, 50, 75, 100 good,
    # flow 110 at most) never reaches the rating and 125 is bad; the bisection of (100, 125)
    # finds 112.5 good (122.5 MVA) and 118.75 good (128.75 MVA, at or above the rating).
    evaluate = _synthetic(120.0, "non_convergence")
    limit = margin.find_transfer_limit(evaluate, 25.0, 400.0, 1.0, 126.0, 80)
    assert limit.bounded_by == "dlr_rating"
    assert limit.good.transfer_mw == 118.75
    assert limit.good.max_flow_mva >= 126.0
    assert limit.first_bad_mw == 125.0
    assert limit.evaluations == 1 + 5 + 2
    assert limit.extended is False


def test_search_not_bounded_raises():
    evaluate = _synthetic(1e9, None, flow_slope=0.0)
    with pytest.raises(margin.NoTransferBound) as caught:
        margin.find_transfer_limit(evaluate, 25.0, 400.0, 1.0, 1e9, 7)
    # ceil(400 / 25) + 7 walk steps, each evaluated once, after the base point
    assert caught.value.steps == 23
    assert len(evaluate.calls) == 24
    assert caught.value.last_increment_mw == 575.0
    assert caught.value.last_flow_mva == 10.0
    evaluate = _synthetic(1e9, None, flow_slope=0.0)
    with pytest.raises(margin.NoTransferBound) as caught:
        margin.find_transfer_limit(evaluate, 25.0, 400.0, 1.0, 1e9, 0)
    assert caught.value.steps == 16
    assert len(evaluate.calls) == 17
    assert caught.value.last_increment_mw == 400.0


@pytest.mark.parametrize("max_mw", [400.0, 410.0])
def test_search_evaluations_bounded(max_mw):
    step, tol, extra = 25.0, 1.0, 10
    bound = (1 + math.ceil(max_mw / step) + extra + math.ceil(math.log(step / tol, 2)) + 1)
    for threshold in range(0, 700, 7):
        evaluate = _synthetic(float(threshold), "voltage_criterion", flow_slope=0.0)
        try:
            limit = margin.find_transfer_limit(evaluate, step, max_mw, tol, 1e9, extra)
            assert limit.evaluations == len(evaluate.calls)
        except margin.NoTransferBound:
            pass
        assert len(evaluate.calls) <= bound, threshold


# ──────────────────────────────────────────────────────────────────────────────
# The city's margin on the fake case
# ──────────────────────────────────────────────────────────────────────────────

_SINK_LOAD = [620.0, 620.0 * math.tan(math.acos(0.95))]


def _flat_solver(case):
    """The radial solver on a case whose loads are frozen at the base: the sink load never rises."""
    frozen = copy.deepcopy(case)
    for bus in frozen.loads:
        frozen.loads[bus] = list(_SINK_LOAD)
    return fake_module.radial_solver(frozen)


def _zero_flow_solver(case):
    """AUSTIN's sink below the voltage criterion with no flow on its mapped branch."""
    outcome = fake_module.radial_solver(case)
    outcome.voltages[90002] = 0.85
    outcome.flows[(90001, 90002, "1")] = {"p_mw": 0.0, "max_mva": 0.0, "current_mva": 0.0}
    return outcome


class _ScaleFails(fake_module.FakePsspy):
    """A psspy whose scal_2 reports an error code."""

    def scal_2(self, sid, all, apiopt, status, scalval):  # noqa: A002 - the manual's name
        return (6, [], [])


def _fails(call):
    with pytest.raises(contract.StudyFailed) as caught:
        call()
    assert caught.value.stage == "voltage_margin"
    return caught.value


def test_city_flat_transfer_fails(prepared):
    fake, path, base = prepared(solver=_flat_solver, mapping_=_mapping(transfer_extra_steps=3))
    failure = _fails(lambda: margin.city_margin(base, "AUSTIN"))
    assert "does not load the mapped branches" in failure.message
    assert failure.message.startswith("AUSTIN: ")


def test_city_sink_without_load_fails(prepared):
    case = fake_module.placeholder_case()
    case.loads[90002] = [0.0, 0.0]
    fake, path, base = prepared(case=case, mapping_=_mapping(transfer_extra_steps=3))
    failure = _fails(lambda: margin.city_margin(base, "AUSTIN"))
    assert "does not load the mapped branches" in failure.message


def test_city_reloads_base_and_redefines_subsystem_each_evaluation(prepared):
    fake, path, base = prepared()
    first = len(fake.fake_calls)
    result = margin.city_margin(base, "AUSTIN")
    calls = [call for call in fake.fake_calls[first:]
             if call[0] in ("case", "bsys", "scal_2", "fnsl")]
    names = [call[0] for call in calls]
    index = 0
    evaluations = 0
    while index < len(names) - 1:
        assert names[index:index + 2] == ["case", "bsys"], names[index:index + 4]
        index += 2
        if names[index] == "scal_2":
            index += 1
        assert names[index] == "fnsl"
        index += 1
        evaluations += 1
    assert names[index:] == ["case"]
    assert evaluations == result.row["details"]["evaluations"]
    assert names.count("scal_2") == evaluations - 1
    loaded = [call[1][0] for call in calls if call[0] == "case"]
    assert loaded and all(item == base.saved_path for item in loaded)
    assert path not in loaded
    for call in calls:
        if call[0] == "bsys":
            assert call[2]["sid"] == margin.SINK_SID and call[2]["buses"] == [90002]


def test_city_el_paso_bounded_by_dlr_rating(prepared):
    selection = _selection()
    fake, path, base = prepared(selection=selection)
    result = margin.city_margin(base, "EL_PASO")
    details = result.row["details"]
    assert result.bounded_by == "dlr_rating"
    assert details["lower_bound"] is True
    assert details["extended_past_cap"] is False
    assert details["increment_mw"] == pytest.approx(900.0)
    assert result.voltage_limit_mva == pytest.approx(800.0, abs=0.01)
    applied = base.cities["EL_PASO"].applied_mva
    assert applied == pytest.approx(788.77, abs=0.01)
    row = dispatch.build_dispatch_row(
        selection.choices["EL_PASO"], 345.0, result.voltage_limit_mva, bounded_by="dlr_rating")
    assert row["limiting_factor"] == "dlr_rating"
    assert row["dispatched_mva"] == pytest.approx(applied)


def test_city_el_paso_fresh_rating_extends_past_cap_to_dlr_rating(prepared):
    selection = _selection(provisional=False)
    choice = selection.choices["EL_PASO"]
    assert choice.source == constants.SOURCE_CITY_RATING
    assert choice.amps_per_conductor == pytest.approx(1452.0)
    fake, path, base = prepared(selection=selection)
    applied = base.cities["EL_PASO"].applied_mva
    assert applied == pytest.approx(867.65, abs=0.01)
    result = margin.city_margin(base, "EL_PASO")
    details = result.row["details"]
    assert result.bounded_by == "dlr_rating"
    assert details["extended_past_cap"] is True
    assert details["increment_mw"] == pytest.approx(1050.0)
    assert details["max_mw"] == 1000.0
    assert details["first_bad_mw"] is None
    assert result.voltage_limit_mva == pytest.approx(878.95, abs=0.01)
    # the flow at the 1000 MW cap (852.63 MVA) must never stand in for the voltage limit
    assert result.voltage_limit_mva > applied
    row = dispatch.build_dispatch_row(
        choice, 345.0, result.voltage_limit_mva, bounded_by=result.bounded_by)
    assert row["limiting_factor"] == "dlr_rating"
    assert row["dispatched_mva"] == pytest.approx(applied)
    assert row["dispatched_mva"] != pytest.approx(852.63, abs=0.1)


def test_city_not_bounded_within_extra_steps_fails(prepared):
    fake, path, base = prepared(selection=_selection(provisional=False),
                                mapping_=_mapping(transfer_extra_steps=0))
    failure = _fails(lambda: margin.city_margin(base, "EL_PASO"))
    assert "transfer.max_mw" in failure.message
    assert "transfer.extra_steps" in failure.message
    assert failure.message.startswith("EL_PASO: no voltage, convergence or rating bound up to ")
    assert "1000 MW" in failure.message
    assert "852." in failure.message


def test_city_budget_exceeded_fails(prepared):
    clock = {"now": 0.0}
    budget = study.Budget(clock=lambda: clock["now"], max_seconds=100.0)
    fake, path, base = prepared(budget=budget)
    clock["now"] = 1000.0
    first = len(fake.fake_calls)
    failure = _fails(lambda: margin.city_margin(base, "AUSTIN"))
    assert "run-time budget" in failure.message
    assert len(fake.fake_calls) == first


def test_city_scale_failure_is_stage_voltage_margin(prepared):
    fake, path, base = prepared(fake=_ScaleFails())
    failure = _fails(lambda: margin.city_margin(base, "AUSTIN"))
    assert "scal_2" in failure.message
    assert failure.message.startswith("AUSTIN: ")


def test_city_zero_flow_voltage_limit_fails(prepared):
    fake, path, base = prepared(solver=_zero_flow_solver)
    failure = _fails(lambda: margin.city_margin(base, "AUSTIN"))
    assert "no flow" in failure.message


def test_city_row_fields_and_details_json_safe(prepared):
    fake, path, base = prepared()
    expected = set(["bounded_by", "lower_bound", "extended_past_cap", "step_mw", "tolerance_mw",
                    "max_mw", "extra_steps", "evaluations", "increment_mw", "first_bad_mw",
                    "sink_buses", "criterion_pu"])
    for city in constants.CITIES:
        result = margin.city_margin(base, city)
        row = result.row
        assert row["city"] == city
        assert row["method"] == "pv_curve"
        assert set(row["details"]) == expected
        json.dumps(row["details"], allow_nan=False)
        assert row["margin_mw"] == pytest.approx(row["limit_transfer_mw"] - row["base_transfer_mw"])
        assert row["margin_pct"] == pytest.approx(row["margin_mw"] / row["base_transfer_mw"] * 100)
        assert row["voltage_limit_mva"] > 0 and result.voltage_limit_mva == row["voltage_limit_mva"]
        assert row["details"]["sink_buses"] == [base.cities[city].sink_buses[0]]
        assert row["details"]["step_mw"] == 25.0 and row["details"]["criterion_pu"] == 0.90
        bounded = "dlr_rating" if city == "EL_PASO" else "voltage_criterion"
        assert result.bounded_by == bounded
        assert row["details"]["lower_bound"] is (city == "EL_PASO")
