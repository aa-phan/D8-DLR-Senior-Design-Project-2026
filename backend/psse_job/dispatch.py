"""
The dispatched-capacity row of one city (pss-e-integration Phase 2, plan 02-05: STU-04, research
D-13).

The dispatched capacity is the lower of the applied DLR rating and the voltage-stability limit,
both per circuit, with the amperes taken from psse_job.units and the power factor entering only
dispatched_mw. A tie goes to the DLR rating, which is the rule run_record.validate_results and
the DDL check. A margin search that was stopped by the rating (bounded_by "dlr_rating") cannot
have found a voltage limit below that rating, so build_dispatch_row refuses the combination
instead of reporting an understated voltage_stability figure.

Pure functions, no psspy. Standard library and psse_job only, Python 3.7 syntax (D-05).
"""

import math

from psse_job import constants, run_record, units

# Copy of backend/config.py POWER_FACTOR (the D-05 pattern: job code never imports config); used
# only for dispatched_mw, the same convention as the city rating's per-conductor MW (research
# D-13); backend/tests/psse_dispatch_test.py fails if they drift.
POWER_FACTOR_DEFAULT = 0.95

# What stopped the margin search (psse_job.margin.Limit.bounded_by).
BOUNDS = ("base_case", "dlr_rating", "non_convergence", "voltage_criterion")


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def build_dispatch_row(choice, line_voltage_kv, voltage_limit_mva, power_factor=None,
                       details=None, bounded_by=None):
    """The dispatch row of one city, keyed by contract.DISPATCH_COLUMNS without run_id and
    run_outcome.

    `choice` is the city's ratings.RatingChoice; its source, fallback reason, amperes and bundle
    count are copied, never recomputed, and the city_rating link is kept only for a city_rating
    source (the DDL link rule). ValueError for a voltage limit that is not a finite number above
    0, a power factor outside (0, 1] or a bool, an unknown `bounded_by`, bad amperes or kV (from
    psse_job.units), and, as a tripwire, a "dlr_rating" bound with a voltage limit below the
    applied MVA.
    """
    if not _is_number(voltage_limit_mva) or not math.isfinite(voltage_limit_mva) \
            or not voltage_limit_mva > 0:
        raise ValueError("voltage_limit_mva must be a finite number above 0")
    factor = POWER_FACTOR_DEFAULT if power_factor is None else power_factor
    if not _is_number(factor) or not math.isfinite(factor) or not 0 < factor <= 1:
        raise ValueError("power_factor must be a number above 0 and at most 1")
    if bounded_by is not None and bounded_by not in BOUNDS:
        raise ValueError("bounded_by must be one of %s" % ", ".join(BOUNDS))
    subconductors = choice.subconductors_per_phase
    applied_amps_circuit = units.circuit_amps(choice.amps_per_conductor, subconductors)
    applied_mva = units.circuit_mva(choice.amps_per_conductor, subconductors, line_voltage_kv)
    if bounded_by == "dlr_rating" and voltage_limit_mva < applied_mva:
        raise ValueError(
            "a margin bounded by the DLR rating cannot have a voltage limit (%g MVA) below the "
            "applied rating (%g MVA)" % (voltage_limit_mva, applied_mva))
    voltage_limit = float(voltage_limit_mva)
    dispatched_mva = min(applied_mva, voltage_limit)
    dispatched_amps_circuit = units.mva_to_circuit_amps(dispatched_mva, line_voltage_kv)
    linked = choice.source == constants.SOURCE_CITY_RATING
    return {
        "city": choice.city,
        "rating_source": choice.source,
        "fallback_reason": choice.fallback_reason,
        "city_rating_valid_time": choice.row_valid_time if linked else None,
        "city_rating_computed_at": choice.row_computed_at if linked else None,
        "applied_amps_per_conductor": choice.amps_per_conductor,
        "subconductors_per_phase": subconductors,
        "applied_amps_circuit": applied_amps_circuit,
        "line_voltage_kv": float(line_voltage_kv),
        "applied_mva": applied_mva,
        "voltage_limit_mva": voltage_limit,
        "dispatched_mva": dispatched_mva,
        "dispatched_amps_circuit": dispatched_amps_circuit,
        "dispatched_amps_per_conductor": dispatched_amps_circuit / subconductors,
        "power_factor": float(factor),
        "dispatched_mw": dispatched_mva * factor,
        "limiting_factor": "dlr_rating" if applied_mva <= voltage_limit else "voltage_stability",
        "details": details,
    }


def dispatch_details(city_base, rate_sets, bounded_by):
    """The details object of a dispatch row: the mapped circuits, the rate sets the rating was
    written to, the case's own ratings that the DLR or static rating replaced (Power Systems sees
    what changed, research open question 5; None for a value that is not a finite number) and
    what bounded the voltage limit."""
    return {
        "branches": [branch.ref.key for branch in city_base.branches],
        "rate_sets": list(rate_sets),
        "rate_before_mva": [run_record.finite(value) for value in city_base.rate_before_mva],
        "voltage_limit_bounded_by": bounded_by,
    }
