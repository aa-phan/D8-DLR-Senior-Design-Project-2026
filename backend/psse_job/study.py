"""
The real PSS/E study behind Phase 1's study(selection, context) seam (pss-e-integration
Phase 2). The first part is the base of the study (plan 02-03: IN-02, IN-03, STU-01); the last
part (plan 02-06) assembles the whole study around it: make_study runs the base, the N-1 screen
(plan 02-04), the margins and the dispatch rows (plan 02-05) and returns contract.StudyResults,
and prepare_run is the single entry point Phase 3's launcher calls (the study, the case label,
the case and mapping hashes).

psspy arrives as an injected module and is reached only through psse_api.PsseApi; this
package never imports it. Every failure is contract.StudyFailed with a stage from
constants.FAILED_STAGES.

Phase 4 (plan 04-03: SCL-02, SCL-03, SCL-05) makes the study four independent studies on four
fresh copies of the same case. make_study loads and indexes Power Systems' case once and checks
the whole mapping against that index before anything is written to the case (IN-02). Then, for
each city in constants.CITIES order, prepare_city_base loads the case file afresh, scales the
whole case to that city's target load and generation with the job's own scal_2 call (never a
script or an .idv file, CD-2), reads the totals back before the solve, writes only that city's
selected rating as per-circuit MVA at the branch's own base kV (read back), solves the load flow
under the strict convergence rule and saves the solved copy to <private temp dir>/<CITY>.sav.
The N-1 screen, the margin search and the dispatch row of that city run on that copy. The four
copies share one private temporary directory, removed on every path; later stages reload the
saved copy before every outage and every transfer step and nothing is ever saved onto the case
file. A scaling that does not take, errors or is absurd fails that city at stage apply_ratings
with a message that names the city and the quantity but no figure.

Phase 4 (plan 04-04: SCL-04, CD-8) attempts every city: a city whose study fails with a
StudyFailed is remembered and the next city is studied, then the run fails once with a message
that names each city's outcome (combined_failure), so job.run_once stores one failed run with no
result row for any city (WB-02) and the other cities' problems are not hidden behind the first.
The run-time budget is shared; a city that cannot start for lack of it is "not attempted".

prepare_base (the four cities in one unscaled case) is kept for the component tests of the
screen and the margin.

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
    "saved_path", "temp_dir", "budget", "psse_version", "rate_set", "scaling",
])
CaseIndex = collections.namedtuple("CaseIndex", [
    "api", "label", "case_path", "psse_version", "lines", "transformers", "buses", "resolved",
])

_RELATIVE_TOLERANCE = 1e-6
_KV_TOLERANCE = 1e-6
_TEMP_PREFIX = "psse_job_"

# The totals read back after the scaling call must be within this relative amount of each target.
SCALE_TOLERANCE = 1e-3
# A target over the case's own total must lie within these bounds (inclusive); a kW-for-MW typo
# or a target for the wrong city is far outside them.
SCALE_FACTOR_BOUNDS = (0.05, 20.0)
SCALING_METHOD = ("scal_2 whole case to the city's target load and generation, load power "
                  "factor kept, one fresh case copy per city")

# What one city's study ends in (combined_failure): CITY_OK, ("failed", stage, message) or
# ("not_attempted",).
CITY_OK = "ok"
_FAILED = "failed"
_NOT_ATTEMPTED = ("not_attempted",)
# Each city's text in the combined failure is cut to this many characters, so the whole message
# stays within constants.ERROR_MAX_CHARS after redaction and never loses a city: a header of 20
# characters plus four clauses of at most 43 + 180 characters and their separators is under 950.
_CLAUSE_TEXT_CHARS = 180


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


def apply_ratings(api, resolved, mapping, selection, cities=None):
    """Write each city's selected rating (per-circuit MVA at the case's base kV) to every listed
    rate set of every mapped circuit, reading each value back (IN-03, research D-09).

    `cities` None means every city in constants.CITIES; otherwise only the given cities, in
    constants.CITIES order (the per-city study rates one city per case copy)."""
    rate_sets = mapping.settings.rate_sets
    result = collections.OrderedDict()
    for city in constants.CITIES:
        if cities is not None and city not in cities:
            continue
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
        result[city] = CityBase(
            city, branches, kv, tuple(mapping.cities[city].sink_buses),
            _transfer_max(mapping, city), amps_circuit, mva, tuple(before))
    return result


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


def _read_solved_base(api, settings):
    """(bus table, branch loading) of the solved case, with the collapsed-solution guard."""
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
    return base_buses, base_flows


def _open_case(psspy_module, case_path):
    """(api, label, psse_version, lines, transformers, buses) of the freshly loaded case; a
    failure is StudyFailed("load_case")."""
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
    return api, label, psse_version, lines, transformers, buses


def _save_solved(api, path):
    """Save the solved working case to `path`; a failure is StudyFailed("contingency")."""
    try:
        api.save_case(path)
    except psse_api.PsseCallError as error:
        raise StudyFailed(
            "contingency",
            "the solved base case could not be saved to a temporary file: %s" % error.meaning)


def prepare_base(psspy_module, case_path, mapping, selection, budget=None):
    """Load, check, rate, solve and save the base case with all four cities in one unscaled
    case; see the module docstring.

    Kept for the component tests of the screen and the margin (psse_contingency_test.py,
    psse_margin_test.py, psse_study_test.py). The job runs make_study's per-city copies
    (index_case and prepare_city_base), not this.
    """
    settings = mapping.settings
    if budget is None:
        budget = Budget(max_seconds=settings.max_runtime_seconds)
    api, label, psse_version, lines, transformers, buses = _open_case(psspy_module, case_path)
    resolved, problems = check_mapping(mapping, lines, transformers, buses)
    if problems:
        raise StudyFailed("mapping", "; ".join(problems))
    sinks = dict((city, mapping.cities[city].sink_buses) for city in constants.CITIES)
    area = study_area(lines, buses, resolved, settings, sinks)
    cities = apply_ratings(api, resolved, mapping, selection)
    result = solve_base(api, settings)
    base_buses, base_flows = _read_solved_base(api, settings)
    temp_dir = tempfile.mkdtemp(prefix=_TEMP_PREFIX)
    try:
        saved_path = os.path.join(temp_dir, "base.sav")
        _save_solved(api, saved_path)
    except BaseException:
        _remove_dir(temp_dir)
        raise
    return BaseCase(
        api, label, case_path, mapping, settings, selection, tuple(lines), tuple(transformers),
        buses, cities, area, result, base_buses, base_flows, saved_path, temp_dir, budget,
        psse_version, settings_module.rate_set_label(settings), None)


# -- one copy of the case per city (Phase 4) --------------------------------------------------------


def index_case(psspy_module, case_path, mapping):
    """Load the case once and index it: lines, transformers and buses, then the whole mapping
    checked against them (a problem is one `mapping` failure, as before). Reads no totals and
    writes nothing, so a mapping failure leaves no write call behind (IN-02)."""
    api, label, psse_version, lines, transformers, buses = _open_case(psspy_module, case_path)
    resolved, problems = check_mapping(mapping, lines, transformers, buses)
    if problems:
        raise StudyFailed("mapping", "; ".join(problems))
    return CaseIndex(api, label, case_path, psse_version, tuple(lines), tuple(transformers),
                     buses, resolved)


def scale_city_case(api, city, scaling):
    """Scale the loaded case to `city`'s target load and generation and read the totals back.

    Refused before the call (StudyFailed("apply_ratings"), message starting "scaling:"): a case
    without load or generation, or a target outside SCALE_FACTOR_BOUNDS times the case's own
    total (a kW-for-MW typo). Refused after it: a total that differs from its target by more
    than SCALE_TOLERANCE, relative. The read-back comes before the solve, because a solve moves
    the swing machine and any voltage-dependent load. No message holds a figure.
    """
    low, high = SCALE_FACTOR_BOUNDS

    def refuse(text):
        return StudyFailed("apply_ratings", "scaling: %s: %s" % (city, text))

    try:
        before = api.read_totals()
        for quantity, own, target in (("load", before.load_mw, scaling.load_mw),
                                      ("generation", before.gen_mw, scaling.gen_mw)):
            if not own > 0:
                raise refuse("the case has no %s to scale" % quantity)
            if not low <= target / own <= high:
                raise refuse("the %s target is outside %g to %g times the case's own total" % (
                    quantity, low, high))
        api.scale_case(scaling.load_mw, scaling.gen_mw)
        after = api.read_totals()
    except (psse_api.PsseCallError, ValueError) as error:
        raise refuse(str(error))
    for quantity, read, target in (("load", after.load_mw, scaling.load_mw),
                                   ("generation", after.gen_mw, scaling.gen_mw)):
        if not abs(read - target) <= SCALE_TOLERANCE * target:
            raise refuse("the %s total read back differs from the target by more than %g percent"
                         % (quantity, SCALE_TOLERANCE * 100.0))


def scaling_record(scaling):
    """What a row may say about the scaling: the basis and the method, never a target or a
    realised total (CD-10; the mapping hash proves the targets)."""
    return {"basis": scaling.basis, "method": SCALING_METHOD}


def prepare_city_base(index, mapping, selection, city, budget, temp_dir):
    """A BaseCase for `city` alone: a fresh load of the case file, the city's scaling, only its
    own rating, the solve and the saved solved copy `<temp_dir>/<CITY>.sav`."""
    api = index.api
    settings = mapping.settings
    try:
        api.load_case(index.case_path)
    except (psse_api.PsseCallError, ValueError) as error:
        raise StudyFailed("load_case", "case %s could not be loaded for %s: %s" % (
            index.label, city, getattr(error, "meaning", error)))
    scaling = mapping.cities[city].scaling
    scale_city_case(api, city, scaling)
    one = {city: index.resolved[city]}
    cities = apply_ratings(api, one, mapping, selection, cities=(city,))
    result = solve_base(api, settings)
    base_buses, base_flows = _read_solved_base(api, settings)
    area = study_area(index.lines, index.buses, one, settings,
                      {city: mapping.cities[city].sink_buses})
    saved_path = os.path.join(temp_dir, city + ".sav")
    _save_solved(api, saved_path)
    return BaseCase(
        api, index.label, index.case_path, mapping, settings, selection, index.lines,
        index.transformers, index.buses, cities, area, result, base_buses, base_flows,
        saved_path, temp_dir, budget, index.psse_version, settings_module.rate_set_label(settings),
        scaling)


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


def _clause_text(city, message):
    """A city's failure message without its own name in front, cut to _CLAUSE_TEXT_CHARS.

    Dropped from the front: "scaling: <CITY>: " (leaving "scaling: "), else "<CITY>: " or
    "<CITY> ". The cut only trims text; it never adds any.
    """
    text = "" if message is None else str(message)
    scaling_prefix = "scaling: %s: " % city
    if text.startswith(scaling_prefix):
        text = "scaling: " + text[len(scaling_prefix):]
    elif text.startswith(city + ": "):
        text = text[len(city) + 2:]
    elif text.startswith(city + " "):
        text = text[len(city) + 1:]
    return text[:_CLAUSE_TEXT_CHARS]


def combined_failure(outcomes, max_seconds):
    """The one StudyFailed of a run in which at least one city did not finish (CD-8).

    `outcomes` holds one item per city in constants.CITIES order: CITY_OK,
    ("failed", stage, message) or ("not_attempted",). The message is "<n> of 4 cities failed"
    (failed and not attempted together), then one clause per city in that order: "<CITY>: ok",
    "<CITY>: failed at <stage>: <text>" or "<CITY>: not attempted: run-time budget of <s> s
    exceeded". The stage is the first failed city's; load_case when no city failed but one was
    not attempted. No message holds a figure: the clauses only trim text the earlier stages
    already wrote without one.
    """
    clauses = []
    count = 0
    stage = None
    for city, outcome in zip(constants.CITIES, outcomes):
        if outcome == CITY_OK:
            clauses.append("%s: ok" % city)
        elif outcome[0] == _FAILED:
            count += 1
            if stage is None:
                stage = outcome[1]
            clauses.append("%s: failed at %s: %s" % (city, outcome[1],
                                                      _clause_text(city, outcome[2])))
        else:
            count += 1
            clauses.append("%s: not attempted: run-time budget of %g s exceeded" % (
                city, max_seconds))
    header = "%d of %d cities failed" % (count, len(constants.CITIES))
    return StudyFailed("load_case" if stage is None else stage, "; ".join([header] + clauses))


def _study_city(index, mapping, selection, city, budget, temp_dir):
    """(dispatch row, margin row, contingency rows, n_contingencies) of one city on its own
    scaled copy of the case; a StudyFailed passes through to make_study's collecting loop."""
    base = prepare_city_base(index, mapping, selection, city, budget, temp_dir)
    screened = contingency.screen(base, id_prefix=city + ":")
    result = margin.city_margin(base, city)
    city_base = base.cities[city]
    record = scaling_record(base.scaling)
    details = dispatch.dispatch_details(city_base, base.settings.rate_sets, result.bounded_by)
    details["scaling"] = dict(record)
    try:
        dispatch_row = dispatch.build_dispatch_row(
            selection.choices[city], city_base.line_voltage_kv, result.voltage_limit_mva,
            details=details, bounded_by=result.bounded_by)
    except ValueError as error:
        raise StudyFailed("dispatch", "%s: %s" % (city, error))
    margin_row = dict(result.row)
    margin_row["details"] = dict(result.row["details"], scaling=dict(record))
    return dispatch_row, margin_row, screened.rows, screened.n_contingencies


def make_study(psspy_module, case_path, mapping, clock=None):
    """study(selection, context) for run_once: for each city, on its own freshly loaded and
    scaled copy of the case, the base load flow, the N-1 screen, a margin and a dispatch row, as
    contract.StudyResults.

    Every call builds a new PsseApi, indexes the case once and loads the case file afresh for
    every city (one study per process, never an adapter reused across runs), and removes its
    temporary files on every path. Every city is attempted (CD-8): a city that fails with a
    StudyFailed is remembered and the next one is studied; when any city failed the run fails
    once, naming each city's outcome (combined_failure), so there is never a partial result set
    (WB-02). The run-time budget is shared by the four cities, and a city that cannot start
    because it is spent is reported as not attempted. A case that cannot be indexed or a mapping
    that does not match it still fails at once, before any city, and an exception that is not a
    StudyFailed is a programming error and surfaces as itself.
    """
    def study(selection, context):
        budget = Budget(clock, mapping.settings.max_runtime_seconds)
        index = index_case(psspy_module, case_path, mapping)
        temp_dir = tempfile.mkdtemp(prefix=_TEMP_PREFIX)
        try:
            outcomes = []
            pieces = []
            for city in constants.CITIES:
                if budget.elapsed() > budget.max_seconds:
                    outcomes.append(_NOT_ATTEMPTED)
                    continue
                try:
                    pieces.append(_study_city(index, mapping, selection, city, budget, temp_dir))
                except StudyFailed as failure:
                    outcomes.append((_FAILED, failure.stage, failure.message))
                else:
                    outcomes.append(CITY_OK)
            if any(outcome != CITY_OK for outcome in outcomes):
                raise combined_failure(outcomes, budget.max_seconds)
            dispatch_rows = [piece[0] for piece in pieces]
            margin_rows = [piece[1] for piece in pieces]
            contingency_rows = []
            for piece in pieces:
                contingency_rows.extend(piece[2])
            n_contingencies = sum(piece[3] for piece in pieces)
            cap = run_record.MAX_CONTINGENCY_ROWS
            if len(contingency_rows) > cap:
                raise StudyFailed(
                    "contingency", "%d violation rows across the four cities exceed the limit "
                                   "of %d; narrow contingency.hops or the scope" % (
                                       len(contingency_rows), cap))
            return contract.StudyResults(
                dispatch=[_with_safe_details(row) for row in dispatch_rows],
                margins=[_with_safe_details(row) for row in margin_rows],
                contingencies=[_with_safe_details(row) for row in contingency_rows],
                n_contingencies=n_contingencies,
                rate_set=settings_module.rate_set_label(mapping.settings),
                psse_version=index.psse_version)
        finally:
            _remove_dir(temp_dir)
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
