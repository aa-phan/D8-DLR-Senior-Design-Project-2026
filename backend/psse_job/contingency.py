"""
The N-1 branch-outage screen of the real PSS/E study (pss-e-integration Phase 2, plan 02-04:
STU-02, research D-12 and D-14).

For each selected outage the saved base is reloaded, the line is tripped, the load flow is
solved under the strict convergence rule and every thermal overload and voltage violation on
the monitored elements becomes a row (psse_job.violations). The saved base is reloaded before
every outage and once more at the end; an outage is never un-tripped and re-solved, so a blown
up solution cannot contaminate the next outage. An outage that does not converge, or converges
to a collapsed voltage, is one non_convergence row and the other outages are still screened.
Zero selected outages, more outages than contingency.max, more rows than
run_record.MAX_CONTINGENCY_ROWS and an exhausted run-time budget fail the stage
(StudyFailed("contingency", ...)); a truncated screen is never returned. Transformer,
generator and multi-element outages are not screened.

The caller owns the base and calls study.cleanup_base(base) on every exit path.

Standard library and psse_job only, Python 3.7 syntax (D-05).
"""

import collections

from psse_job import contract, psse_api, run_record, settings as settings_module, violations

StudyFailed = contract.StudyFailed
BranchRef = settings_module.BranchRef

ContingencyResult = collections.namedtuple("ContingencyResult",
                                           ["rows", "n_contingencies", "outages"])

_STAGE = "contingency"


def select_outages(base):
    """The branch outages to screen: BranchRef values in the case's orientation, sorted by key.

    Scope "neighbourhood" takes the in-service lines of the study area, scope "all" every
    in-service line; each contingency.extra line that is in service is added once.
    """
    settings = base.settings
    in_service = dict((row.key, row) for row in base.lines if row.in_service)
    if settings.contingency_scope == "all":
        chosen = set(in_service)
    else:
        chosen = set(key for key in base.area.branch_keys if key in in_service)
    for extra in settings.contingency_extra:
        for key in (extra.key, BranchRef(extra.to_bus, extra.from_bus, extra.ckt).key):
            if key in in_service:
                chosen.add(key)
                break
    outages = [BranchRef(in_service[key].from_bus, in_service[key].to_bus, in_service[key].ckt)
               for key in sorted(chosen)]
    if not outages:
        raise StudyFailed(_STAGE, "no branch outage was selected; a screen that screens nothing "
                                  "is not a result")
    if len(outages) > settings.contingency_max:
        raise StudyFailed(_STAGE, "%d branch outages exceed contingency.max %d; narrow "
                                  "contingency.hops or the scope" % (
                                      len(outages), settings.contingency_max))
    return outages


def _call_failure(outage, error):
    return StudyFailed(_STAGE, "outage %s: %s" % (outage.key, getattr(error, "meaning", error)))


def screen(base):
    """Screen every selected outage; see the module docstring."""
    api = base.api
    settings = base.settings
    outages = select_outages(base)
    city_of_branch, city_of_bus = violations.city_maps(base.cities)
    base_flows_by_key = dict((flow.key, flow) for flow in base.base_flows)
    monitored_keys = base.area.branch_keys
    monitored_buses = base.area.buses
    rate_set = settings.rate_sets[0]
    rows = []
    for outage in outages:
        base.budget.check(_STAGE)
        contingency_id = outage.key
        try:
            api.load_case(base.saved_path)
            api.set_status(outage, False)
            result = api.solve(settings.solve_options)
            if not result.converged:
                rows.append(violations.non_convergence_row(contingency_id, result))
            else:
                buses = api.bus_table()
                if _collapsed(buses, monitored_buses, settings.collapse_voltage_pu):
                    rows.append(violations.non_convergence_row(contingency_id, result,
                                                               collapsed=True))
                else:
                    flows = api.branch_loading(rate_set, settings.thermal_basis)
                    rows.extend(violations.thermal_violations(
                        flows, monitored_keys, settings, contingency_id, city_of_branch,
                        base_flows_by_key, skip_key=contingency_id))
                    rows.extend(violations.voltage_violations(
                        buses, monitored_buses, settings, contingency_id, city_of_bus,
                        base.base_buses))
        except (psse_api.PsseCallError, ValueError) as error:
            raise _call_failure(outage, error)
        cap = run_record.MAX_CONTINGENCY_ROWS
        if len(rows) > cap:
            raise StudyFailed(_STAGE, "%d violation rows exceed the limit of %d; narrow "
                                      "contingency.hops or the scope" % (len(rows), cap))
    try:
        api.load_case(base.saved_path)
    except (psse_api.PsseCallError, ValueError) as error:
        raise StudyFailed(_STAGE, "the solved base case could not be reloaded after the "
                                  "screen: %s" % getattr(error, "meaning", error))
    return ContingencyResult(rows, len(outages), outages)


def _collapsed(buses, monitored_buses, collapse_voltage_pu):
    """True when a monitored in-service bus is below the collapse voltage (NaN counts as
    collapsed, as in the base load-flow guard)."""
    for number in monitored_buses:
        bus = buses.get(number)
        if bus is not None and bus.type_code < 4 and not bus.pu >= collapse_voltage_pu:
            return True
    return False
