"""
The per-city voltage-stability margin of the real PSS/E study (pss-e-integration Phase 2, plan
02-05: STU-03, research D-13).

The margin is a transfer search built from plain load flows, because PSS/E's PV and QV engines
need DFAX files and a licence and cannot be exercised without them. For a transfer of d MW the
saved base is reloaded, subsystem SINK_SID is defined on the city's sink buses, their load is
raised by d MW at constant P/Q and the load flow is solved under the strict convergence rule;
the swing bus absorbs the increase (the transfer source is open question 4, so this is the
researched default, not a decision). A point is good when the solve converged, no monitored bus
collapsed and the lowest monitored voltage is at or above voltage.contingency_low_pu. The search
steps up by transfer.step_mw and bisects to transfer.tolerance_mw once a step is bad. It stops at
the first of: a bad point (non_convergence or voltage_criterion), the flow on the mapped branches
reaching the applied DLR rating (dlr_rating, so the margin is then a lower bound), or the base
case already failing the criterion (base_case).

transfer.max_mw is a starting cap, never a stop. Reaching it with no bound and the flow still
below the applied rating keeps the walk going, with the same step, for at most
transfer.extra_steps more steps; running out of them fails the stage (NoTransferBound, then
StudyFailed("voltage_margin")). A search ended by the cap alone is therefore never reported, so
a voltage-stability limit can only come from a non-convergence or a voltage-criterion bound.
The label pv_curve is the DDL's example for this load-transfer search, not a PSS/E PV-curve
analysis.

The search itself (find_transfer_limit) is pure; city_margin is the one adapter loop. The caller
owns the base and calls study.cleanup_base(base) on every exit path.

Standard library and psse_job only, Python 3.7 syntax (D-05).
"""

import collections
import math

from psse_job import contract, psse_api, run_record

StudyFailed = contract.StudyFailed

SINK_SID = 9

_STAGE = "voltage_margin"
_METHOD = "pv_curve"
_BASE_MIN_MW = 0.1
_REASONS = ("non_convergence", "voltage_criterion")

Point = collections.namedtuple("Point", [
    "ok", "converged", "reason", "transfer_mw", "p_mapped_mw", "max_flow_mva",
    "min_voltage_pu", "critical_bus",
])
Limit = collections.namedtuple("Limit", [
    "base", "good", "bounded_by", "evaluations", "first_bad_mw", "extended",
])
MarginResult = collections.namedtuple("MarginResult", ["row", "voltage_limit_mva", "bounded_by"])


class NoTransferBound(Exception):
    """The walk used up its steps with no bad point and the flow still below the rating."""

    def __init__(self, steps, last_increment_mw, last_flow_mva):
        Exception.__init__(
            self, "no bound after %d steps (last increment %g MW, last flow %s MVA)" % (
                steps, last_increment_mw, last_flow_mva))
        self.steps = steps
        self.last_increment_mw = last_increment_mw
        self.last_flow_mva = last_flow_mva


# -- the search (pure) -----------------------------------------------------------------------------


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _positive(name, value):
    if not _is_number(value) or not math.isfinite(value) or not value > 0:
        raise ValueError("%s must be a finite number above 0" % name)


def _reaches(point, stop_flow_mva):
    return point.max_flow_mva is not None and point.max_flow_mva >= stop_flow_mva


def _reason(point):
    if point.reason not in _REASONS:
        raise ValueError("a point that is not ok needs a reason of %s" % ", ".join(_REASONS))
    return point.reason


def find_transfer_limit(evaluate, step_mw, max_mw, tol_mw, stop_flow_mva, extra_steps):
    """The largest transfer that is still good, found by a walk and a bisection.

    `evaluate(d)` returns a Point for a transfer of d MW (ok is True for a good point; a point
    that is not ok has reason "non_convergence" or "voltage_criterion"). Returns a Limit whose
    `good` point is the last good one; `bounded_by` says what stopped the search:

    - "base_case": the base point (d = 0) is not ok; good is the base point;
    - "dlr_rating": a good point's max_flow_mva reached stop_flow_mva, on the walk or during the
      bisection (so the limit is a lower bound);
    - "non_convergence" or "voltage_criterion": the reason of the bad point nearest the limit.

    The walk steps by step_mw while d + step_mw <= max_mw; when that ends with no bad point and
    the rating not reached it continues with the same step for at most extra_steps more steps
    (Limit.extended becomes True when a step past the starting cap was evaluated). When those
    are used up too, NoTransferBound is raised: there is no "max_transfer" outcome, because a
    search ended by the cap alone would understate the limit.
    """
    _positive("step_mw", step_mw)
    _positive("tol_mw", tol_mw)
    if not _is_number(max_mw) or not math.isfinite(max_mw) or max_mw < 0:
        raise ValueError("max_mw must be a finite number that is not negative")
    if not _is_number(stop_flow_mva) or math.isnan(stop_flow_mva):
        raise ValueError("stop_flow_mva must be a number")
    if isinstance(extra_steps, bool) or not isinstance(extra_steps, int) or extra_steps < 0:
        raise ValueError("extra_steps must be an integer that is not negative")

    base = evaluate(0.0)
    evaluations = 1
    if not base.ok:
        return Limit(base, base, "base_case", evaluations, 0.0, False)
    cap_steps = int(math.floor(max_mw / step_mw + 1e-9))
    good, lo = base, 0.0
    bad, hi = None, None
    steps = 0
    while steps < cap_steps + extra_steps:
        steps += 1
        increment = steps * step_mw
        point = evaluate(increment)
        evaluations += 1
        if not point.ok:
            bad, hi = point, increment
            break
        good, lo = point, increment
        if _reaches(point, stop_flow_mva):
            return Limit(base, good, "dlr_rating", evaluations, None, steps > cap_steps)
    extended = steps > cap_steps
    if bad is None:
        raise NoTransferBound(steps, lo, good.max_flow_mva)
    while hi - lo > tol_mw:
        mid = 0.5 * (lo + hi)
        point = evaluate(mid)
        evaluations += 1
        if point.ok:
            good, lo = point, mid
            if _reaches(point, stop_flow_mva):
                return Limit(base, good, "dlr_rating", evaluations, hi, extended)
        else:
            bad, hi = point, mid
    return Limit(base, good, _reason(bad), evaluations, hi, extended)


# -- the city's margin -----------------------------------------------------------------------------


def _bound_message(city, bound, city_base, settings):
    return (
        "%s: no voltage, convergence or rating bound up to %g MW (transfer.max_mw %g plus "
        "transfer.extra_steps %d steps of %g MW) while the mapped flow (%g MVA) is still below "
        "the applied rating (%g MVA); raise study.transfer.extra_steps or transfer.max_mw, or "
        "check the sink buses" % (
            city, bound.last_increment_mw, city_base.transfer_max_mw,
            settings.transfer_extra_steps, settings.transfer_step_mw, bound.last_flow_mva,
            city_base.applied_mva))


def _check_loads_mapped_branches(city, points, min_rise_fraction):
    """StudyFailed unless the transfer really loaded the mapped branches (research Pitfall 10).

    `points` is every evaluated (increment, Point) in order, the base point first. The good point
    with the smallest positive increment must show the mapped branches' summed active power
    above the base point's by at least min_rise_fraction x that increment; a flat flow (a sink
    with no scalable load, on the wrong side, or a solver that ignores it) is no limit at all.
    """
    base_point = points[0][1]
    if base_point.p_mapped_mw is None:
        return
    candidates = [item for item in points if item[0] > 0 and item[1].ok]
    if not candidates:
        return
    increment, point = min(candidates, key=lambda item: item[0])
    rise = point.p_mapped_mw - base_point.p_mapped_mw
    if not rise >= min_rise_fraction * increment:
        raise StudyFailed(_STAGE, (
            "%s: the transfer does not load the mapped branches (flow rose %g MW for %g MW of "
            "extra sink load); check the sink buses") % (city, rise, increment))


def city_margin(base, city):
    """The margin row of `city` and what bounded it; StudyFailed("voltage_margin") on any
    failure (no number is ever invented). See the module docstring."""
    city_base = base.cities[city]
    settings = base.settings
    api = base.api
    monitored = sorted(base.area.by_city[city][1])
    mapped_keys = [branch.ref.key for branch in city_base.branches]
    rate_set = settings.rate_sets[0]
    points = []

    def failure(message):
        return StudyFailed(_STAGE, "%s: %s" % (city, message))

    def read_point(increment):
        buses = api.bus_table()
        min_pu = None
        critical = None
        collapsed = False
        seen = False
        for number in monitored:
            bus = buses.get(number)
            if bus is None or bus.type_code >= 4:
                continue
            seen = True
            if not bus.pu >= settings.collapse_voltage_pu:
                collapsed = True
            if math.isfinite(bus.pu) and (min_pu is None or bus.pu < min_pu):
                min_pu, critical = bus.pu, number
        if not seen:
            raise failure("no monitored bus is in service in the solved case")
        critical_text = None if critical is None else str(critical)
        if collapsed:
            return Point(False, True, "non_convergence", increment, None, None, min_pu,
                         critical_text)
        by_key = dict((flow.key, flow) for flow in
                      api.branch_loading(rate_set, settings.thermal_basis))
        p_mapped = 0.0
        max_flow = 0.0
        for key in mapped_keys:
            flow = by_key.get(key)
            if flow is None or not flow.in_service:
                raise failure("mapped branch %s is not in service in the solved case" % key)
            if not (math.isfinite(flow.p_mw) and math.isfinite(flow.max_mva)):
                raise failure("mapped branch %s has a flow that is not a number" % key)
            p_mapped += abs(flow.p_mw)
            max_flow = max(max_flow, flow.max_mva)
        low = not min_pu >= settings.contingency_low_pu
        return Point(not low, True, "voltage_criterion" if low else None, increment, p_mapped,
                     max_flow, min_pu, critical_text)

    def evaluate(increment):
        base.budget.check(_STAGE)
        try:
            api.load_case(base.saved_path)
            api.define_subsystem(SINK_SID, city_base.sink_buses)
            if increment > 0:
                api.scale_load(SINK_SID, increment)
            result = api.solve(settings.solve_options)
            if not result.converged:
                point = Point(False, False, "non_convergence", increment, None, None, None, None)
            else:
                point = read_point(increment)
        except (psse_api.PsseCallError, ValueError) as error:
            raise failure(str(error))
        points.append((increment, point))
        return point

    try:
        limit = find_transfer_limit(
            evaluate, settings.transfer_step_mw, city_base.transfer_max_mw,
            settings.transfer_tolerance_mw, city_base.applied_mva, settings.transfer_extra_steps)
    except NoTransferBound as bound:
        # A flat transfer never finds a bound; say so rather than only "no bound found".
        _check_loads_mapped_branches(city, points, settings.transfer_min_rise_fraction)
        raise StudyFailed(_STAGE, _bound_message(city, bound, city_base, settings))
    _check_loads_mapped_branches(city, points, settings.transfer_min_rise_fraction)
    try:
        api.load_case(base.saved_path)
    except (psse_api.PsseCallError, ValueError) as error:
        raise failure("the solved base case could not be reloaded after the search: %s" % error)

    good = limit.good
    voltage_limit = good.max_flow_mva
    if voltage_limit is None or not math.isfinite(voltage_limit) or not voltage_limit > 0:
        raise failure("no flow on the mapped branches at the limit")
    base_mw = limit.base.p_mapped_mw
    limit_mw = good.p_mapped_mw
    margin_mw = limit_mw - base_mw
    margin_pct = None if base_mw < _BASE_MIN_MW else margin_mw / base_mw * 100.0
    finite = run_record.finite
    details = {
        "bounded_by": limit.bounded_by,
        "lower_bound": limit.bounded_by == "dlr_rating",
        "extended_past_cap": limit.extended,
        "step_mw": finite(settings.transfer_step_mw),
        "tolerance_mw": finite(settings.transfer_tolerance_mw),
        "max_mw": finite(city_base.transfer_max_mw),
        "extra_steps": settings.transfer_extra_steps,
        "evaluations": limit.evaluations,
        "increment_mw": finite(good.transfer_mw),
        "first_bad_mw": finite(limit.first_bad_mw),
        "sink_buses": list(city_base.sink_buses),
        "criterion_pu": finite(settings.contingency_low_pu),
    }
    row = {
        "city": city,
        "method": _METHOD,
        "base_transfer_mw": finite(base_mw),
        "limit_transfer_mw": finite(limit_mw),
        "margin_mw": finite(margin_mw),
        "margin_pct": finite(margin_pct),
        "voltage_limit_mva": finite(voltage_limit),
        "critical_bus": good.critical_bus,
        "min_voltage_pu": finite(good.min_voltage_pu),
        "details": details,
    }
    return MarginResult(row, row["voltage_limit_mva"], limit.bounded_by)
