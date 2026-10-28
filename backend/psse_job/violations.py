"""
Pure evaluation of thermal and voltage violations for the N-1 screen (pss-e-integration
Phase 2, plan 02-04: STU-02, research D-11).

A row is a dict keyed by contract.CONTINGENCY_COLUMNS without run_id and run_outcome, and must
satisfy run_record.validate_results and the DDL of psse_contingency_result: a thermal row is a
branch in MVA, a voltage row a bus in pu, exceeded_by is above 0 and equals the distance past
the limit, and a non_convergence row names its contingency and carries no values. Nothing here
calls psspy or does I/O; the readings arrive as psse_api.BranchFlow and psse_api.BusRow values.
Every float placed in `details` goes through run_record.finite, because the writer serialises
JSON with allow_nan=False (research Pitfall 13).

Standard library and psse_job only, Python 3.7 syntax (D-05).
"""

import math

from psse_job import run_record

_ISOLATED_BUS_TYPE = 4


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _positive_finite(value):
    return _is_number(value) and math.isfinite(value) and value > 0


def _limits_and_source(bus_row, settings, post_contingency):
    """((low, high), source actually used): the case's own pair when source is "case" and the
    pair is usable, else the configured pair."""
    if post_contingency:
        configured = (settings.contingency_low_pu, settings.contingency_high_pu)
    else:
        configured = (settings.base_low_pu, settings.base_high_pu)
    if settings.voltage_source == "case":
        if post_contingency:
            pair = (bus_row.evlmlo, bus_row.evlmhi)
        else:
            pair = (bus_row.nvlmlo, bus_row.nvlmhi)
        if _positive_finite(pair[0]) and _positive_finite(pair[1]) and pair[0] < pair[1]:
            return (float(pair[0]), float(pair[1])), "case"
    return configured, "config"


def voltage_limits(bus_row, settings, post_contingency):
    """(low, high) in pu for a bus: configured, or the case's own pair (emergency limits after
    an outage, normal limits for the base) when the voltage source is "case" and the case's
    pair is two finite positive values with low below high; otherwise the configured pair."""
    return _limits_and_source(bus_row, settings, post_contingency)[0]


def city_maps(base_cities):
    """(city_of_branch, city_of_bus) from the base's cities (city -> CityBase).

    A mapped branch key maps to its city; an endpoint bus of a mapped branch maps to its city
    only when exactly one city uses that bus.
    """
    city_of_branch = {}
    users = {}
    for city, city_base in base_cities.items():
        for branch in city_base.branches:
            city_of_branch[branch.ref.key] = city
            for number in (branch.ref.from_bus, branch.ref.to_bus):
                users.setdefault(number, set()).add(city)
    city_of_bus = {}
    for number, cities in users.items():
        if len(cities) == 1:
            city_of_bus[number] = next(iter(cities))
    return city_of_branch, city_of_bus


def _row(contingency_id, kind, element_type, element_id, city, limit, observed, exceeded, unit,
         details):
    return {
        "contingency_id": contingency_id,
        "violation_kind": kind,
        "element_type": element_type,
        "element_id": element_id,
        "city": city,
        "limit_value": limit,
        "observed_value": observed,
        "exceeded_by": exceeded,
        "unit": unit,
        "details": details,
    }


def _usable_flow(flow):
    return (flow.in_service and _is_number(flow.rate_mva) and math.isfinite(flow.rate_mva)
            and flow.rate_mva > 0 and _is_number(flow.pct) and math.isfinite(flow.pct))


def _observed_mva(flow):
    """The loading expressed in MVA of the rating: rate x pct / 100 (the same operation order as
    the limit, so a loading exactly at the limit percentage is exactly at the limit)."""
    return flow.rate_mva * flow.pct / 100.0


def thermal_violations(flows, monitored_keys, settings, contingency_id, city_of_branch,
                       base_flows_by_key, skip_key=None):
    """thermal_overload rows for the monitored in-service lines loaded past their limit.

    limit = rating x thermal_limit_pct / 100 on the first listed rate set; observed = pct / 100
    x rating (current or MVA basis per settings.thermal_basis). A rating of 0 (no limit in
    PSS/E), a non-finite value, an out-of-service line, the outaged line itself and an
    unmonitored line give no row; a loading exactly at the limit is not a violation.
    """
    rows = []
    for flow in flows:
        key = flow.key
        if key not in monitored_keys or key == skip_key or not _usable_flow(flow):
            continue
        limit = flow.rate_mva * settings.thermal_limit_pct / 100.0
        observed = _observed_mva(flow)
        if not observed > limit:
            continue
        base = base_flows_by_key.get(key)
        base_value = None
        in_base_case = False
        if base is not None and _usable_flow(base):
            base_value = _observed_mva(base)
            in_base_case = base_value > base.rate_mva * settings.thermal_limit_pct / 100.0
        rows.append(_row(
            contingency_id, "thermal_overload", "branch", key, city_of_branch.get(key),
            float(limit), float(observed), float(observed - limit), "MVA",
            {
                "basis": settings.thermal_basis,
                "rate_set": settings.rate_sets[0],
                "pct_of_rating": run_record.finite(flow.pct),
                "in_base_case": in_base_case,
                "base_value": run_record.finite(base_value),
            }))
    return rows


def voltage_violations(buses, monitored_buses, settings, contingency_id, city_of_bus,
                       base_buses):
    """voltage_low and voltage_high rows for the monitored buses outside the post-contingency
    limits, in ascending bus order.

    A bus missing from the table, isolated (type 4 or more) or with a pu that is not finite and
    above 0 is skipped. in_base_case is true when the bus already violated its pre-contingency
    limit of the same kind in the solved base.
    """
    rows = []
    for number in sorted(monitored_buses):
        bus = buses.get(number)
        if (bus is None or bus.type_code >= _ISOLATED_BUS_TYPE
                or not _positive_finite(bus.pu)):
            continue
        (low, high), source = _limits_and_source(bus, settings, True)
        if bus.pu < low:
            kind, limit, exceeded = "voltage_low", low, low - bus.pu
        elif bus.pu > high:
            kind, limit, exceeded = "voltage_high", high, bus.pu - high
        else:
            continue
        base = base_buses.get(number)
        base_value = None
        in_base_case = False
        if base is not None and _positive_finite(base.pu):
            base_value = base.pu
            base_low, base_high = voltage_limits(base, settings, False)
            in_base_case = base.pu < base_low if kind == "voltage_low" else base.pu > base_high
        rows.append(_row(
            contingency_id, kind, "bus", str(number), city_of_bus.get(number),
            float(limit), float(bus.pu), float(exceeded), "pu",
            {
                "source": source,
                "in_base_case": in_base_case,
                "base_value": run_record.finite(base_value),
            }))
    return rows


def non_convergence_row(contingency_id, solve_result, collapsed=False):
    """The one row of an outage whose load flow did not converge, or converged to a collapsed
    voltage. After a failed fnsl, solved() describes an older attempt, so it is not recorded."""
    solved = solve_result.solved_code if solve_result.ierr == 0 else None
    meaning = solve_result.meaning
    if collapsed:
        meaning = "collapsed voltage solution; %s" % meaning
    return _row(
        contingency_id, "non_convergence", "contingency", contingency_id, None, None, None, None,
        None,
        {
            "ierr": solve_result.ierr if isinstance(solve_result.ierr, int) else None,
            "solved": solved if isinstance(solved, int) else None,
            "meaning": str(meaning),
            "collapsed": bool(collapsed),
        })
