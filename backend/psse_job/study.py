"""
The real PSS/E study behind Phase 1's study(selection, context) seam (pss-e-integration
Phase 2). The first part is the base of the study (plan 02-03: IN-02, IN-03, STU-01); the last
part (plan 02-06) assembles the whole study around it: make_study runs the base, the N-1 screen
(plan 02-04), the margins and the dispatch rows (plan 02-05) and returns contract.StudyResults,
and prepare_run is the single entry point Phase 3's launcher calls (the study, the case label,
the case and mapping hashes).

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
import datetime
import os
import tempfile
import time

from psse_job import (
    constants, contingency, contract, dispatch, mapping as mapping_module, margin, psse_api,
    run_record, settings as settings_module, units,
)

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
        message = "load flow did not converge: ierr=%s solved=%s (%s)" % (
            result.ierr, result.solved_code, result.meaning)
        if result.ierr == 2:
            message += (" - the saved case has converted generators; Power Systems must supply "
                        "an unconverted case")
        raise StudyFailed("load_flow", message)
    if result.mismatch_mva is not None and not result.mismatch_mva <= settings.max_mismatch_mva:
        raise StudyFailed("load_flow", "load flow mismatch %g MVA exceeds %g MVA" % (
            result.mismatch_mva, settings.max_mismatch_mva))
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
    collapsed = [bus for bus in base_buses.values()
                 if bus.type_code < 4 and not bus.pu >= settings.collapse_voltage_pu]
    if collapsed:
        raise StudyFailed("load_flow", "collapsed solution: %d in-service buses below %g pu" % (
            len(collapsed), settings.collapse_voltage_pu))
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


# -- the whole study (plan 02-06) -----------------------------------------------------------------

PreparedRun = collections.namedtuple("PreparedRun", [
    "study", "case_id", "case_sha256", "mapping_sha256", "mapping_error",
])


def failing_study(stage, message):
    """A study callable that raises StudyFailed(stage, message) without touching psspy."""
    def failing(selection, context):
        raise StudyFailed(stage, message)
    return failing


def json_safe(value):
    """A JSON-safe copy of `value` (research Pitfall 13: the writer dumps details with
    allow_nan=False): dict keys become text, lists and tuples lists, floats go through
    run_record.finite (NaN and infinity become None), datetimes ISO text, None, bool, int and str
    pass through and any other object becomes its text."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return run_record.finite(value)
    if isinstance(value, dict):
        return dict((str(key), json_safe(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return str(value)


def _with_safe_details(row):
    row = dict(row)
    row["details"] = json_safe(row.get("details"))
    return row


def make_study(psspy_module, case_path, mapping, clock=None):
    """study(selection, context) for run_once: the base, the N-1 screen, a margin and a dispatch
    row per city, as contract.StudyResults.

    Every call builds a new PsseApi and loads the case afresh (one study per process, never an
    adapter reused across runs), and removes its temporary files on every path.
    """
    def study(selection, context):
        budget = Budget(clock, mapping.settings.max_runtime_seconds)
        base = prepare_base(psspy_module, case_path, mapping, selection, budget)
        try:
            screened = contingency.screen(base)
            margins = [margin.city_margin(base, city) for city in constants.CITIES]
            dispatch_rows = []
            for city, result in zip(constants.CITIES, margins):
                city_base = base.cities[city]
                try:
                    dispatch_rows.append(dispatch.build_dispatch_row(
                        selection.choices[city], city_base.line_voltage_kv,
                        result.voltage_limit_mva,
                        details=dispatch.dispatch_details(
                            city_base, base.settings.rate_sets, result.bounded_by),
                        bounded_by=result.bounded_by))
                except ValueError as error:
                    raise StudyFailed("dispatch", "%s: %s" % (city, error))
            return contract.StudyResults(
                dispatch=[_with_safe_details(row) for row in dispatch_rows],
                margins=[_with_safe_details(result.row) for result in margins],
                contingencies=[_with_safe_details(row) for row in screened.rows],
                n_contingencies=screened.n_contingencies,
                rate_set=base.rate_set,
                psse_version=base.psse_version)
        finally:
            cleanup_base(base)
    return study


def prepare_run(psspy_module, case_path, mapping_path, allow_placeholder=False, clock=None):
    """Everything Phase 3's launcher passes to job.run_once: the study, the case label, the case
    file's sha256 and the mapping's sha256.

    A mapping that cannot be read, parsed or validated (a refused placeholder included) gives a
    study that fails at stage mapping and mapping_sha256 None, "the mapping was not loaded"; a
    mapping that loads keeps its hash even when it does not match the case (that failure comes
    from inside the study). The case is hashed from the same path the study loads; the gap
    between the hash and the load is accepted.
    """
    case_id = run_record.case_label(case_path)
    case_sha256 = run_record.file_sha256(case_path)
    try:
        loaded = mapping_module.load_mapping(mapping_path, allow_placeholder)
    except mapping_module.MappingError as error:
        text = str(error)
        return PreparedRun(
            failing_study("mapping", "mapping file not usable: %s" % text),
            case_id, case_sha256, None, text)
    return PreparedRun(make_study(psspy_module, case_path, loaded, clock),
                       case_id, case_sha256, loaded.sha256, None)
