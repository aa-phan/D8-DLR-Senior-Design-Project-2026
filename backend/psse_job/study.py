"""
The real PSS/E study behind Phase 1's study(selection, context) seam (pss-e-integration
Phase 2). This part is the base of the study (plan 02-03: IN-02, IN-03, STU-01); plan 02-06
assembles the whole study around it.

psspy arrives as an injected module and is reached only through psse_api.PsseApi; this
package never imports it. Every failure is contract.StudyFailed with a stage from
constants.FAILED_STAGES. prepare_base loads Power Systems' case, indexes its lines and buses,
checks the whole mapping against that index before anything is written to the case, writes
each city's selected rating as per-circuit MVA at the branch's own base kV (read back), solves
the base load flow under the strict convergence rule and saves the solved base to a private
per-run temporary file. Later stages reload that file before every outage and every transfer
step and never save onto the case file.

Standard library and psse_job only, Python 3.7 syntax (D-05).
"""

import collections
import os
import tempfile
import time

from psse_job import constants, contract, psse_api, run_record, settings as settings_module, units

StudyFailed = contract.StudyFailed
BranchRef = settings_module.BranchRef

ResolvedBranch = collections.namedtuple("ResolvedBranch", ["ref", "base_kv"])
CityBase = collections.namedtuple("CityBase", [
    "city", "branches", "line_voltage_kv", "sink_buses", "transfer_max_mw",
    "applied_amps_circuit", "applied_mva", "rate_before_mva",
])
StudyArea = collections.namedtuple("StudyArea", ["branch_keys", "buses", "by_city"])
BaseCase = collections.namedtuple("BaseCase", [
    "api", "case_label", "case_path", "mapping", "settings", "selection", "lines",
    "transformers", "buses", "cities", "area", "solve", "base_buses", "base_flows",
    "saved_path", "temp_dir", "budget", "psse_version", "rate_set",
])

_RELATIVE_TOLERANCE = 1e-6
_KV_TOLERANCE = 1e-6
_TEMP_PREFIX = "psse_job_"


class Budget(object):
    """The run-time budget (research D-12): checked between solves with an injected clock."""

    def __init__(self, clock=None, max_seconds=1500.0):
        self._clock = time.monotonic if clock is None else clock
        self.max_seconds = max_seconds
        self._start = self._clock()

    def elapsed(self):
        return self._clock() - self._start

    def check(self, stage):
        if self.elapsed() > self.max_seconds:
            raise StudyFailed(stage, "run-time budget of %g s exceeded" % self.max_seconds)


# -- the mapping against the case ---------------------------------------------------------------


def check_mapping(mapping, lines, transformers, buses):
    """(resolved, problems): each city's mapped lines in the case's orientation with their base
    kV, and every problem found. Pure; no psspy call.

    A mapped branch must be an in-service line (not a transformer) whose two ends share one
    base kV, a city's branches must share one base kV (the result tables store one
    line_voltage_kv per city), each sink bus must be a bus in service, and each extra outage
    must be a line in the case (research D-08). The reversed orientation is accepted and
    normalised to the case's, because whether PSS/E accepts reversed ends is unknown.
    """
    by_key = {}
    for row in lines:
        by_key[(row.from_bus, row.to_bus, row.ckt)] = row
    transformer_keys = set()
    for row in transformers:
        transformer_keys.add((row.from_bus, row.to_bus, row.ckt))
        transformer_keys.add((row.to_bus, row.from_bus, row.ckt))

    def find_line(ref):
        row = by_key.get((ref.from_bus, ref.to_bus, ref.ckt))
        return row if row is not None else by_key.get((ref.to_bus, ref.from_bus, ref.ckt))

    problems = []
    resolved = {}
    for city in constants.CITIES:
        branches = []
        for ref in mapping.cities[city].branches:
            row = find_line(ref)
            if row is None:
                if (ref.from_bus, ref.to_bus, ref.ckt) in transformer_keys:
                    problems.append("%s: branch %s is a two-winding transformer, not a line"
                                    % (city, ref.key))
                else:
                    problems.append("%s: branch %s is not in the case" % (city, ref.key))
                continue
            if not row.in_service:
                problems.append("%s: branch %s is out of service" % (city, ref.key))
                continue
            from_end = buses.get(row.from_bus)
            to_end = buses.get(row.to_bus)
            if (from_end is None or to_end is None or not from_end.base_kv > 0
                    or not to_end.base_kv > 0
                    or abs(from_end.base_kv - to_end.base_kv) > _KV_TOLERANCE):
                problems.append(
                    "%s: branch %s has endpoints of different base kV (a transformer or a data "
                    "error)" % (city, ref.key))
                continue
            branches.append(ResolvedBranch(BranchRef(row.from_bus, row.to_bus, row.ckt),
                                           from_end.base_kv))
        kv_values = sorted(set(round(branch.base_kv, 6) for branch in branches))
        if len(kv_values) > 1:
            problems.append("%s: mapped branches have different base kV %s" % (city, kv_values))
        for number in mapping.cities[city].sink_buses:
            sink = buses.get(number)
            if sink is None:
                problems.append("%s: sink bus %d is not in the case" % (city, number))
            elif sink.type_code >= 4:
                problems.append("%s: sink bus %d is isolated" % (city, number))
        resolved[city] = tuple(branches)
    for ref in mapping.settings.contingency_extra:
        if find_line(ref) is None:
            problems.append("contingency.extra: branch %s is not a line in the case" % ref.key)
    return resolved, problems


def study_area(lines, buses, resolved, settings, sinks=None):
    """The neighbourhood of the mapped branches within settings.contingency_hops lines.

    `sinks` (city -> sink bus numbers) are always part of a city's monitored buses.
    """
    sinks = {} if sinks is None else sinks
    touching = {}
    for row in lines:
        if row.in_service:
            touching.setdefault(row.from_bus, []).append(row)
            touching.setdefault(row.to_bus, []).append(row)

    def monitored(number):
        bus = buses.get(number)
        return bus is not None and bus.type_code < 4 and bus.base_kv >= settings.min_monitor_kv

    by_city = {}
    for city in constants.CITIES:
        keys = set()
        reached = set()
        for branch in resolved.get(city, ()):
            keys.add(branch.ref.key)
            reached.update((branch.ref.from_bus, branch.ref.to_bus))
        frontier = set(reached)
        for _ in range(settings.contingency_hops):
            new = set()
            for number in frontier:
                for row in touching.get(number, ()):
                    keys.add(row.key)
                    for end in (row.from_bus, row.to_bus):
                        if end not in reached:
                            new.add(end)
            reached |= new
            frontier = new
        monitor = set(number for number in reached if monitored(number))
        monitor.update(sinks.get(city, ()))
        by_city[city] = (frozenset(keys), frozenset(monitor))
    branch_keys = frozenset().union(*[value[0] for value in by_city.values()])
    monitor_all = frozenset().union(*[value[1] for value in by_city.values()])
    return StudyArea(branch_keys, monitor_all, by_city)


# -- ratings --------------------------------------------------------------------------------------


def apply_ratings(api, resolved, mapping, selection):
    """Write each city's selected rating (per-circuit MVA at the case's base kV) to every listed
    rate set of every mapped circuit, reading each value back (IN-03, research D-09)."""
    rate_sets = mapping.settings.rate_sets
    cities = collections.OrderedDict()
    for city in constants.CITIES:
        choice = selection.choices[city]
        branches = resolved[city]
        kv = branches[0].base_kv
        try:
            amps_circuit = units.circuit_amps(choice.amps_per_conductor,
                                              choice.subconductors_per_phase)
            mva = units.circuit_mva(choice.amps_per_conductor, choice.subconductors_per_phase, kv)
        except ValueError as error:
            raise StudyFailed("apply_ratings", "%s: %s" % (city, error))
        before = []
        for branch in branches:
            try:
                before.append(api.read_rate(branch.ref, rate_sets[0]))
                for rate_set in rate_sets:
                    api.set_rate(branch.ref, rate_set, mva)
                    read = api.read_rate(branch.ref, rate_set)
                    if abs(read - mva) > _RELATIVE_TOLERANCE * mva:
                        raise StudyFailed("apply_ratings", "%s %s %s read back %r, wrote %r" % (
                            city, branch.ref.key, rate_set, read, mva))
            except (psse_api.PsseCallError, ValueError) as error:
                raise StudyFailed("apply_ratings", "%s %s: %s" % (city, branch.ref.key, error))
        cities[city] = CityBase(
            city, branches, kv, tuple(mapping.cities[city].sink_buses),
            _transfer_max(mapping, city), amps_circuit, mva, tuple(before))
    return cities


def _transfer_max(mapping, city):
    value = mapping.cities[city].transfer_max_mw
    return mapping.settings.transfer_max_mw if value is None else value


# -- the base load flow ---------------------------------------------------------------------------


def solve_base(api, settings):
    """The base load flow; anything but a converged solve is StudyFailed("load_flow")."""
    try:
        result = api.solve(settings.solve_options)
    except (psse_api.PsseCallError, ValueError) as error:
        raise StudyFailed("load_flow", "load flow could not be run: %s" % error)
    if not result.converged:
        raise StudyFailed("load_flow", "load flow did not converge: ierr=%s solved=%s (%s)" % (
            result.ierr, result.solved_code, result.meaning))
    return result


# -- the base case --------------------------------------------------------------------------------


def _remove_dir(path):
    """Remove every file in `path` and then the directory itself, ignoring OSError."""
    try:
        for name in os.listdir(path):
            try:
                os.remove(os.path.join(path, name))
            except OSError:
                pass
        os.rmdir(path)
    except OSError:
        pass


def cleanup_base(base):
    """Remove the temporary directory of the base case (never the case file)."""
    _remove_dir(base.temp_dir)


def prepare_base(psspy_module, case_path, mapping, selection, budget=None):
    """Load, check, rate, solve and save the base case; see the module docstring."""
    settings = mapping.settings
    if budget is None:
        budget = Budget(max_seconds=settings.max_runtime_seconds)
    label = run_record.case_label(case_path)
    try:
        api = psse_api.PsseApi(psspy_module, protected_path=case_path)
        psse_version = api.version()
        api.load_case(case_path)
        lines, transformers = api.branch_table()
        buses = api.bus_table()
    except (psse_api.PsseCallError, ValueError) as error:
        raise StudyFailed("load_case", "case %s could not be loaded: %s" % (
            label, getattr(error, "meaning", error)))
    resolved, problems = check_mapping(mapping, lines, transformers, buses)
    if problems:
        raise StudyFailed("mapping", "; ".join(problems))
    sinks = dict((city, mapping.cities[city].sink_buses) for city in constants.CITIES)
    area = study_area(lines, buses, resolved, settings, sinks)
    cities = apply_ratings(api, resolved, mapping, selection)
    result = solve_base(api, settings)
    try:
        base_buses = api.bus_table()
        base_flows = api.branch_loading(settings.rate_sets[0], settings.thermal_basis)
    except (psse_api.PsseCallError, ValueError) as error:
        raise StudyFailed("load_flow", "the solved base case could not be read: %s" % error)
    temp_dir = tempfile.mkdtemp(prefix=_TEMP_PREFIX)
    try:
        saved_path = os.path.join(temp_dir, "base.sav")
        try:
            api.save_case(saved_path)
        except psse_api.PsseCallError as error:
            raise StudyFailed(
                "contingency",
                "the solved base case could not be saved to a temporary file: %s" % error.meaning)
    except BaseException:
        _remove_dir(temp_dir)
        raise
    return BaseCase(
        api, label, case_path, mapping, settings, selection, tuple(lines), tuple(transformers),
        buses, cities, area, result, base_buses, base_flows, saved_path, temp_dir, budget,
        psse_version, settings_module.rate_set_label(settings))
