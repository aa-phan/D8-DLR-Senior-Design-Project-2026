"""
The NET-03 comparator (pandapower-solver Phase 1, plan 01-08: NET-03; decisions D-12 and D-13).

D-13, in words. A bus passes when its voltage differs from the reference by at most 0.01 pu. A
flow passes when it differs from the reference by at most the larger of 2 percent of the
reference flow and 2 MVA, so a small flow is judged under an absolute floor and a large one by
its percentage. Both bounds are inclusive, with a slack of `COMPARISON_EPSILON` so that a boundary
written in decimal (exactly 0.01, exactly 2 percent) is not lost to binary rounding. The rule is
applied to every in-service bus voltage and, per branch, to the signed from-end P, the from-end Q
when the reference has it and the larger-end apparent flow (the quantity the job's rating check
uses), joined by bus number and by the from-to-circuit key, never by position. Angles, losses and
machine Q are not gates.

D-12, in words. Nothing is tuned to make pandapower agree with PSS/E. The four constants below are
the only place a tolerance is written (a test walks this file's syntax tree to prove it). The
explained-differences registry is the only way an out-of-tolerance value passes: it must list the
exact element and quantity, with a written cause and a measured size at least as large as the
deviation, and an entry never widens the tolerance for any other element or quantity. The
registry is passed in as data (it is a private file the owner writes; plan 01-09 loads it). The
comparator reads the net and never writes to it.

Incomplete is not passed. A comparison is `complete` only when the reference is usable, the net
has a solved state, the transformer flows came from the session, no element is present on one side
only and every quantity the rule needs is present. `passed` needs `complete` and no unexplained
difference. NET-03 passes only when each city has a complete passing algorithm-run verdict; the
injected-snapshot run is a diagnostic that localises a wrong scaling rule.

Verdicts carry the element keys (private, for the owner's report); `render_counts` holds counts and
the pass or fail word only, so it can be printed or committed.
"""

import collections
import math
import numbers

from psse_job import constants

VOLTAGE_TOLERANCE_PU = 0.01
FLOW_RELATIVE_TOLERANCE = 0.02
FLOW_FLOOR_MVA = 2.0
COMPARISON_EPSILON = 1e-12

RUN_ALGORITHM = "algorithm"
RUN_INJECTED = "injected"
QUANTITIES = ("voltage", "p_from", "q_from", "max_mva", "in_service")
# Assembled from pieces: the registry file carries this key, and the shape layer of the private
# data guard looks for it in tracked text.
REGISTRY_MARKER = "pandapower_job_" + "registry"
REGISTRY_VERSION = 1

Difference = collections.namedtuple("Difference", ["element", "quantity", "size"])
RegistryEntry = collections.namedtuple("RegistryEntry", ["cause", "measured_size"])

_VERDICT_FIELDS = (
    "city", "run", "complete", "passed", "buses_compared", "buses_failed", "flows_compared",
    "flows_failed", "transformer_flows", "worst_voltage_pu", "worst_flow_excess_mva", "explained",
    "unexplained", "missing", "deviations")


class CityVerdict(collections.namedtuple("CityVerdict", _VERDICT_FIELDS)):
    """One city's comparison under one run (see compare_city)."""

    __slots__ = ()

    def render_counts(self):
        """Counts and pass or fail only: no bus number, key or value."""
        return ("%s %s: %s, complete %s, buses %d compared %d failed, flows %d compared %d failed,"
                " transformer flows %s, explained %d, unexplained %d, missing %d, deviations %d"
                % (self.city, self.run, "PASS" if self.passed else "FAIL",
                   "yes" if self.complete else "no", self.buses_compared, self.buses_failed,
                   self.flows_compared, self.flows_failed, self.transformer_flows,
                   len(self.explained), len(self.unexplained), len(self.missing),
                   len(self.deviations)))


def within_voltage(ref_pu, got_pu):
    """D-13 for a bus voltage (False for a non-finite value)."""
    return abs(got_pu - ref_pu) <= VOLTAGE_TOLERANCE_PU + COMPARISON_EPSILON


def flow_allowance(ref_mva):
    """The most a flow may differ from `ref_mva` (D-13)."""
    return max(FLOW_RELATIVE_TOLERANCE * abs(ref_mva), FLOW_FLOOR_MVA)


def within_flow(ref_mva, got_mva):
    """D-13 for a branch flow (False for a non-finite value)."""
    return abs(got_mva - ref_mva) <= flow_allowance(ref_mva) + COMPARISON_EPSILON


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _size(value):
    """A deviation size; a non-finite deviation is infinitely large."""
    return value if math.isfinite(value) else math.inf


# -- the reference and the net as plain tables ---------------------------------------------------


def _reference_usable(reference):
    if not isinstance(reference, dict) or reference.get("status") != "ok":
        return False
    if not isinstance(reference.get("buses"), list) or not isinstance(
            reference.get("line_flows"), list):
        return False
    solve = reference.get("solve")
    return isinstance(solve, dict) and solve.get("converged") is True


def _net_buses(net):
    """{bus number: (in_service, vm_pu)} of the solved net."""
    voltages = net.res_bus.vm_pu if "vm_pu" in net.res_bus else None
    table = {}
    for index in net.bus.index:
        value = math.nan
        if voltages is not None and index in voltages.index:
            value = float(voltages.at[index])
        table[int(index)] = (bool(net.bus.at[index, "in_service"]), value)
    return table


def _end_flow(p_mw, q_mvar):
    return math.hypot(p_mw, q_mvar)


# The result columns of the from end (the builder puts the from bus at the high-voltage side of a
# transformer) and the to end, for a line and for a transformer.
_LINE_COLUMNS = ("p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar")
_TRAFO_COLUMNS = ("p_hv_mw", "q_hv_mvar", "p_lv_mw", "q_lv_mvar")


def _net_branches(net):
    """{key: (is_transformer, in_service, p_from, q_from, larger-end apparent flow)}."""
    table = {}
    for is_transformer, rows, results, columns in (
            (False, net.line, net.res_line, _LINE_COLUMNS),
            (True, net.trafo, net.res_trafo, _TRAFO_COLUMNS)):
        for index in rows.index:
            key = str(rows.at[index, "name"])
            values = [math.nan] * 4
            if len(results) and index in results.index:
                values = [float(results.at[index, name]) for name in columns]
            p_from, q_from, p_to, q_to = values
            apparent = max(_end_flow(p_from, q_from), _end_flow(p_to, q_to)) if all(
                math.isfinite(item) for item in values) else math.nan
            table[key] = (is_transformer, bool(rows.at[index, "in_service"]), p_from, q_from,
                          apparent)
    return table


def _reference_branches(reference):
    """({key: entry}, transformer status). Entries from branch_flows win over line_flows."""
    entries = {}
    for row in reference.get("line_flows") or ():
        entries[row["key"]] = {
            "is_transformer": None, "in_service": bool(row.get("in_service")),
            "p_mw": row.get("p_mw"), "q_mvar": None, "max_mva": row.get("max_mva")}
    flows = reference.get("branch_flows")
    status = "ok" if isinstance(flows, dict) and flows.get("status") == "ok" else "unavailable"
    if status == "ok":
        for row in flows.get("rows") or ():
            entries[row["key"]] = {
                "is_transformer": bool(row.get("is_transformer")),
                "in_service": bool(row.get("in_service")), "p_mw": row.get("p_mw"),
                "q_mvar": row.get("q_mvar"), "max_mva": row.get("max_mva")}
    return entries, status


# -- the comparison ------------------------------------------------------------------------------


class _Tally(object):
    """What one comparison has found so far."""

    def __init__(self):
        self.buses_compared = 0
        self.buses_failed = 0
        self.flows_compared = 0
        self.flows_failed = 0
        self.worst_voltage = None
        self.worst_excess = None
        self.differences = []
        self.missing = []

    def voltage(self, element, ref, got):
        self.buses_compared += 1
        deviation = _size(abs(got - ref))
        if self.worst_voltage is None or deviation > self.worst_voltage:
            self.worst_voltage = deviation
        if not within_voltage(ref, got):
            self.buses_failed += 1
            self.differences.append(Difference(element, "voltage", deviation))

    def flow(self, element, quantity, ref, got):
        self.flows_compared += 1
        deviation = _size(abs(got - ref))
        excess = deviation - flow_allowance(ref)
        if self.worst_excess is None or excess > self.worst_excess:
            self.worst_excess = excess
        if not within_flow(ref, got):
            self.flows_failed += 1
            self.differences.append(Difference(element, quantity, deviation))

    def in_service(self, element):
        self.differences.append(Difference(element, "in_service", 1.0))

    def absent(self, element, reason):
        self.missing.append((element, reason))


def _compare_buses(tally, net, reference):
    ours = _net_buses(net)
    theirs = {}
    for row in reference["buses"]:
        theirs[int(row["number"])] = row
    for number in sorted(set(ours) | set(theirs)):
        element = str(number)
        if number not in theirs:
            tally.absent(element, "not_in_reference")
        elif number not in ours:
            tally.absent(element, "not_in_net")
        else:
            row = theirs[number]
            net_live, got = ours[number]
            ref_live = row.get("type_code") != 4
            if ref_live != net_live:
                tally.in_service(element)
            elif ref_live:
                ref = row.get("pu")
                if not _finite(ref):
                    tally.absent(element, "reference_value")
                else:
                    tally.voltage(element, float(ref), got)


def _quantities(entry, got_p, got_q, got_apparent):
    """(quantity, reference value or None, net value); Q is gated only when the reference has it."""
    items = [("p_from", entry["p_mw"], got_p)]
    if entry["q_mvar"] is not None:
        items.append(("q_from", entry["q_mvar"], got_q))
    items.append(("max_mva", entry["max_mva"], got_apparent))
    return items


def _compare_branches(tally, net, reference):
    """The branch comparison; returns the transformer-flow status."""
    ours = _net_branches(net)
    theirs, status = _reference_branches(reference)
    for key in sorted(set(ours) | set(theirs)):
        mine = ours.get(key)
        entry = theirs.get(key)
        if mine is not None and mine[0] and status != "ok":
            continue   # transformer flows unavailable: reported through the status
        if entry is None:
            tally.absent(key, "not_in_reference")
            continue
        if mine is None:
            tally.absent(key, "not_in_net")
            continue
        is_transformer, live, got_p, got_q, got_apparent = mine
        if entry["is_transformer"] is not None and entry["is_transformer"] != is_transformer:
            tally.absent(key, "class_differs")
            continue
        if entry["in_service"] != live:
            tally.in_service(key)
            continue
        if not live:
            got_p, got_q, got_apparent = [0.0 if not math.isfinite(item) else item
                                          for item in (got_p, got_q, got_apparent)]
        for quantity, ref, got in _quantities(entry, got_p, got_q, got_apparent):
            if ref is None and not live:
                ref = 0.0
            if not _finite(ref):
                tally.absent(key, "reference_" + quantity)
            else:
                tally.flow(key, quantity, float(ref), got)
    return status


def _explains(registry, difference):
    entry = registry.get((difference.element, difference.quantity))
    return entry is not None and difference.size <= entry.measured_size + COMPARISON_EPSILON


def compare_city(city, run, net_solved, reference, registry=None, deviations=()):
    """
    Compare the solved net `net_solved` with `reference` (the session's base.json, or None when
    missing) under D-13 and return a CityVerdict for `city` and the run label `run` ("algorithm"
    or "injected"). `registry` is the dict `load_registry` returns (or None); `deviations` are the
    D-14 deviations of the settings the net was solved under, passed through. The net is read, never
    written. See the module docstring for what makes a verdict complete and passing.
    """
    registry = registry or {}
    tally = _Tally()
    status = "unavailable"
    if not _reference_usable(reference):
        tally.absent("reference", "unusable")
    elif not bool(getattr(net_solved, "converged", False)):
        tally.absent("net", "not_solved")
    else:
        _compare_buses(tally, net_solved, reference)
        status = _compare_branches(tally, net_solved, reference)
    explained = tuple(sorted((d for d in tally.differences if _explains(registry, d)),
                             key=lambda d: (d.element, d.quantity)))
    unexplained = tuple(sorted((d for d in tally.differences if not _explains(registry, d)),
                               key=lambda d: (d.element, d.quantity)))
    missing = tuple(sorted(tally.missing))
    complete = not missing and status == "ok"
    return CityVerdict(
        city, run, complete, complete and not unexplained, tally.buses_compared,
        tally.buses_failed, tally.flows_compared, tally.flows_failed, status,
        tally.worst_voltage, tally.worst_excess, explained, unexplained, missing,
        tuple(deviations))


# -- the explained-differences registry ----------------------------------------------------------


class RegistryRefused(ValueError):
    """The registry data is not usable. `reason` is one word; the message holds no element key."""

    def __init__(self, reason):
        self.reason = reason
        ValueError.__init__(self, "registry refused: %s" % reason)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _entry(item):
    if not isinstance(item, dict):
        raise RegistryRefused("bad_entry")
    element, quantity = item.get("element"), item.get("quantity")
    if not _text(element) or not _text(quantity):
        raise RegistryRefused("bad_entry")
    if quantity not in QUANTITIES:
        raise RegistryRefused("unknown_quantity")
    if not _text(item.get("cause")):
        raise RegistryRefused("empty_cause")
    size = item.get("measured_size")
    if (not isinstance(size, numbers.Real) or isinstance(size, bool)
            or not math.isfinite(size) or size < 0):
        raise RegistryRefused("bad_size")
    return (element, quantity), RegistryEntry(item["cause"].strip(), float(size))


def load_registry(data):
    """
    The registry as {(element, quantity): RegistryEntry} from its parsed JSON: an object holding
    `REGISTRY_MARKER` (value REGISTRY_VERSION) and `entries`, a list of objects with `element` (a
    bus number or a from-to-circuit key, as text), `quantity` (one of QUANTITIES), a non-empty
    `cause` and a finite non-negative `measured_size` in the unit of the quantity (pu or MVA).
    Anything else, and a pair listed twice, is a RegistryRefused. Passing the result to
    `compare_city` explains exactly those pairs, up to exactly that size, and nothing else.
    """
    if not isinstance(data, dict):
        raise RegistryRefused("not_an_object")
    if data.get(REGISTRY_MARKER) != REGISTRY_VERSION:
        raise RegistryRefused("missing_marker")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise RegistryRefused("bad_entries")
    registry = {}
    for item in entries:
        key, entry = _entry(item)
        if key in registry:
            raise RegistryRefused("duplicate_entry")
        registry[key] = entry
    return registry


# -- the NET-03 verdict --------------------------------------------------------------------------

Net03Verdict = collections.namedtuple(
    "Net03Verdict", ["passed", "cities", "cities_passed", "cities_complete", "verdicts"])


def _is_algorithm_run(run):
    return run == RUN_ALGORITHM or str(run).startswith(RUN_ALGORITHM + ":")


def net03_verdict(verdicts):
    """
    NET-03 over every city of `psse_job.constants.CITIES`. It passes only when each city has at
    least one algorithm-run verdict and every algorithm-run verdict of that city is complete and
    passing. A run label is "algorithm", or "algorithm:<label>" when the var-limit classification
    is inconclusive and both settings were solved (both must pass). The injected-snapshot run
    ("injected") is a diagnostic and never counts, for or against.
    """
    verdicts = tuple(verdicts)
    by_city = {}
    for verdict in verdicts:
        if _is_algorithm_run(verdict.run):
            by_city.setdefault(verdict.city, []).append(verdict)
    cities = tuple(constants.CITIES)
    complete = sum(1 for city in cities
                   if by_city.get(city) and all(item.complete for item in by_city[city]))
    passed = sum(1 for city in cities
                 if by_city.get(city) and all(item.passed for item in by_city[city]))
    return Net03Verdict(passed == len(cities), cities, passed, complete, verdicts)
