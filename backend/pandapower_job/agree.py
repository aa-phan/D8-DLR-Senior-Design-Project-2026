"""
The agreement rules (pandapower-solver Phase 4, plan 04-02: AGR-02 and AGR-03; decisions D-02 and
D-04).

What is compared. One recorded PSS/E run and one replayed run, per outage, on the same sets of
overloads, voltage violations and non-converged outages, on the violation values, on the voltage
margin of each city and on the dispatched capacity of each city. The stored tables hold violations
only, so a key present on one side only says that side's element exceeded its limit and the other
solver's value lies on the other side of it.

How a pass is earned. The tolerances are the owner's and are imported by name from
`pandapower_job.compare` (0.01 pu for a voltage, the larger of 2 percent and 2 MVA for a flow);
nothing here writes a second tolerance, and a test walks this file's syntax tree to prove it. D-02:
a margin is judged against the larger of the relative tolerance of the recorded value and the
resolution of the search that produced it (the stored step for a rating-bound search, which stops
at the first stepped point that reaches the rating, and the stored tolerance for a voltage-bound
one, which is bisected), so quantisation cannot pass for disagreement and the floor cannot be
widened (it is read from the recorded run). A one-sided element within the owner's tolerance of its
limit is borderline (counted, with its largest excess); outside it, or any one-sided
non-convergence row, is a failure. A different limiting class, a different search setting or
different input data is a failure, never borderline. D-04: the gate word is pass only with at
least one replayed run, at least one non-empty set comparison and no failure; zero of either is
incomplete, and a failure beats incomplete.

Counts and words only. `Summary` is built from integers, the verdict word and members of the closed
vocabularies, so it can be printed or put in a CI log; every value, element and run id lives in
`Detail`, which includes the largest deviation even on a pass (D-03; only the private report of
plan 04-03 and 04-04 writes it).

Pure: standard library plus `pandapower_job.compare` and `psse_job.constants`. No solver, no
database driver, no file or network module, so it is tested without pandapower.
"""

import collections
import math

from pandapower_job import compare
from psse_job import constants

KINDS = tuple(constants.VIOLATION_KINDS)

DATA_CHECK_WORDS = (
    "rating_data", "search_settings", "branches", "rate_before", "sink_buses", "rate_set",
    "limit_value", "element_fields",
)

CHECK_WORDS = (
    "n_contingencies", "city_rows", "duplicate_key", "rating_data", "branches", "rate_before",
    "sink_buses", "search_settings", "rate_set", "limit_value", "element_fields",
    "set_one_sided", "convergence_one_sided", "value_thermal", "value_voltage",
    "margin_bound_class", "margin_value", "dispatch_value", "limiting_factor", "replay_failed",
)

EXCLUSION_REASONS = (
    "failed_run", "mapping_hash_missing", "mapping_hash_differs", "case_hash_missing",
    "case_hash_differs", "ratings_unusable", "rows_incomplete",
)

NOTE_WORDS = ("bound_member_differs", "critical_bus_differs")

QUANTITIES = (
    "thermal_mva", "voltage_pu", "margin_mw", "limit_transfer_mw", "base_transfer_mw",
    "min_voltage_pu", "voltage_limit_mva", "dispatched_mva",
)

COMPARE_COUNT_KEYS = (
    "outages_thermal_overload", "outages_voltage_low", "outages_voltage_high",
    "outages_non_convergence", "pairs_compared", "agreeing_keys", "borderline",
    "margin_comparisons", "margin_quantised", "dispatch_comparisons", "dispatch_informative",
)

# The identity tolerance of inputs that must be the same on both sides (rounding of a stored
# float), and of a limit that must be the same; neither is a study tolerance.
DATA_RELATIVE_TOLERANCE = 1e-6
LIMIT_RELATIVE_TOLERANCE = 1e-9

FAILURE = "failure"
BORDERLINE = "borderline"

Side = collections.namedtuple(
    "Side", ["n_contingencies", "rate_set", "dispatch", "margins", "violations", "problems"])
Finding = collections.namedtuple("Finding", ["klass", "check", "where", "detail"])
Deviation = collections.namedtuple(
    "Deviation", ["quantity", "deviation", "allowance", "utilisation", "where"])


class RunComparison(collections.namedtuple(
        "RunComparison", ["findings", "counts", "notes", "worst"])):
    """The result of compare_run: findings (private), counts and notes (integers) and the largest
    Deviation per quantity (private)."""

    __slots__ = ()

    @property
    def passed(self):
        return not any(item.klass == FAILURE for item in self.findings)


# -- the two sides as plain tables ---------------------------------------------------------------


def _details(row):
    value = row.get("details") if isinstance(row, dict) else None
    return value if isinstance(value, dict) else {}


def _by_city(rows, table, problems):
    found = {}
    for row in rows:
        city = row.get("city") if isinstance(row, dict) else None
        if city not in constants.CITIES or city in found:
            problems.append(("city_rows", (table, city)))
            continue
        found[city] = row
    for city in constants.CITIES:
        if city not in found:
            problems.append(("city_rows", (table, city)))
    return found


def _build_side(n_contingencies, rate_set, dispatch_rows, margin_rows, contingency_rows):
    problems = []
    dispatch = _by_city(dispatch_rows, "dispatch", problems)
    margins = _by_city(margin_rows, "margins", problems)
    violations = {}
    for row in contingency_rows:
        key = (row.get("contingency_id"), row.get("violation_kind"), row.get("element_id"))
        if key in violations:
            problems.append(("duplicate_key", key))
            continue
        violations[key] = row
    return Side(n_contingencies, rate_set, dispatch, margins, violations, tuple(problems))


def side_from_recorded(run, dispatch_rows, margin_rows, contingency_rows):
    """A Side from the stored run row and its three tables (plain dictionaries)."""
    return _build_side(run.get("n_contingencies"), run.get("rate_set"), dispatch_rows,
                       margin_rows, contingency_rows)


def side_from_results(results):
    """A Side from a `contract.StudyResults` (or anything with the same attributes)."""
    return _build_side(results.n_contingencies, results.rate_set, results.dispatch,
                       results.margins, results.contingencies)


# -- small helpers -------------------------------------------------------------------------------


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _close(left, right, relative):
    """Equal to a relative tolerance; None equals None; a non-finite number equals nothing."""
    if left is None and right is None:
        return True
    if not _finite(left) or not _finite(right):
        return False
    return abs(left - right) <= relative * max(abs(left), abs(right))


def _deviation(quantity, reference, got, allowance, where):
    size = abs(got - reference)
    return Deviation(quantity, size, allowance, size / allowance, where)


def _record(worst, deviation):
    held = worst.get(deviation.quantity)
    if held is None or deviation.utilisation > held.utilisation:
        worst[deviation.quantity] = deviation


class _Run(object):
    """The accumulating state of one compare_run call."""

    def __init__(self):
        self.findings = []
        self.counts = dict.fromkeys(COMPARE_COUNT_KEYS, 0)
        self.notes = dict.fromkeys(NOTE_WORDS, 0)
        self.worst = {}

    def fail(self, check, where, detail=None):
        self.findings.append(Finding(FAILURE, check, where, detail))

    def borderline(self, check, where, excess, band):
        self.counts["borderline"] += 1
        self.findings.append(Finding(
            BORDERLINE, check, where, {"excess": excess, "band": band}))

    def result(self):
        return RunComparison(tuple(self.findings), dict(self.counts), dict(self.notes),
                             dict(self.worst))


# -- the violation sets and their values ----------------------------------------------------------


def _one_sided(run, key, side, row):
    kind = key[1]
    if kind == "non_convergence":
        run.fail("convergence_one_sided", key, side)
        return
    limit = row.get("limit_value")
    excess = row.get("exceeded_by")
    if kind == "thermal_overload":
        band = compare.flow_allowance(limit) if _finite(limit) else None
    else:
        band = compare.VOLTAGE_TOLERANCE_PU
    if not _finite(excess) or band is None:
        run.fail("set_one_sided", key, {"side": side, "excess": None})
    elif excess <= band + compare.COMPARISON_EPSILON:
        run.borderline("set_one_sided", key, excess, band)
    else:
        run.fail("set_one_sided", key, {"side": side, "excess": excess, "band": band})


def _both_sided(run, key, recorded_row, replayed_row):
    kind = key[1]
    failed = False
    unlike = [name for name in ("city", "element_type", "unit")
              if recorded_row.get(name) != replayed_row.get(name)]
    if unlike:
        run.fail("element_fields", key, unlike)
        failed = True
    if kind == "non_convergence":
        return not failed
    if not _close(recorded_row.get("limit_value"), replayed_row.get("limit_value"),
                  LIMIT_RELATIVE_TOLERANCE):
        run.fail("limit_value", key)
        failed = True
    reference = recorded_row.get("observed_value")
    got = replayed_row.get("observed_value")
    if kind == "thermal_overload":
        check, quantity = "value_thermal", "thermal_mva"
    else:
        check, quantity = "value_voltage", "voltage_pu"
    if not _finite(reference) or not _finite(got):
        run.fail(check, key, "not_finite")
        return False
    if kind == "thermal_overload":
        agreed = compare.within_flow(reference, got)
        allowance = compare.flow_allowance(reference)
    else:
        agreed = compare.within_voltage(reference, got)
        allowance = compare.VOLTAGE_TOLERANCE_PU
    run.counts["pairs_compared"] += 1
    _record(run.worst, _deviation(quantity, reference, got, allowance, key))
    if not agreed:
        run.fail(check, key)
        failed = True
    return not failed


def _compare_violations(run, recorded, replayed):
    outages = dict((kind, set()) for kind in KINDS)
    for key in sorted(set(recorded.violations) | set(replayed.violations), key=repr):
        kind = key[1]
        if kind not in outages:
            run.fail("element_fields", key, "violation_kind")
            continue
        outages[kind].add(key[0])
        in_recorded = key in recorded.violations
        in_replayed = key in replayed.violations
        if in_recorded and in_replayed:
            if _both_sided(run, key, recorded.violations[key], replayed.violations[key]):
                run.counts["agreeing_keys"] += 1
        elif in_recorded:
            _one_sided(run, key, "recorded", recorded.violations[key])
        else:
            _one_sided(run, key, "replayed", replayed.violations[key])
    for kind in KINDS:
        run.counts["outages_" + kind] = len(outages[kind])


# -- the per-city input data, margins and dispatch -------------------------------------------------

_RATING_FIELDS_TEXT = ("rating_source", "fallback_reason", "subconductors_per_phase")
_RATING_FIELDS_NUMBER = ("applied_amps_per_conductor", "line_voltage_kv", "applied_mva")

_RATING_CLASS = "rating"
_VOLTAGE_CLASS = "voltage"
_BASE_CLASS = "base"
_MARGIN_CLASSES = {
    "dlr_rating": _RATING_CLASS, "voltage_criterion": _VOLTAGE_CLASS,
    "non_convergence": _VOLTAGE_CLASS, "base_case": _BASE_CLASS,
}


def _hashable(item):
    return tuple(item) if isinstance(item, (list, tuple)) else item


def _key_set(value):
    """A stored list as a set (None stays None, so a missing detail differs from an empty one)."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return value
    return frozenset(_hashable(item) for item in value)


def _sorted_numbers(value):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return value
    return sorted(value, key=lambda item: (item is None, item if _finite(item) else 0.0))


def _same_numbers(left, right):
    left, right = _sorted_numbers(left), _sorted_numbers(right)
    if left is None or right is None:
        return left is None and right is None
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
        return False
    return all(_close(one, other, DATA_RELATIVE_TOLERANCE) for one, other in zip(left, right))


def _check_rating_data(run, city, recorded, replayed):
    unlike = [name for name in _RATING_FIELDS_TEXT if recorded.get(name) != replayed.get(name)]
    unlike += [name for name in _RATING_FIELDS_NUMBER
               if not _close(recorded.get(name), replayed.get(name), DATA_RELATIVE_TOLERANCE)]
    if unlike:
        run.fail("rating_data", ("dispatch", city), unlike)
    rec, rep = _details(recorded), _details(replayed)
    if _key_set(rec.get("branches")) != _key_set(rep.get("branches")):
        run.fail("branches", ("dispatch", city))
    if not _same_numbers(rec.get("rate_before_mva"), rep.get("rate_before_mva")):
        run.fail("rate_before", ("dispatch", city))


def _positive(value):
    return _finite(value) and value > 0


def _check_search_settings(run, city, recorded, replayed):
    """Returns whether the floor of the recorded search can be derived."""
    rec, rep = _details(recorded), _details(replayed)
    if _key_set(rec.get("sink_buses")) != _key_set(rep.get("sink_buses")):
        run.fail("sink_buses", ("margins", city))
    unlike = []
    for name in ("step_mw", "tolerance_mw"):
        if not (_positive(rec.get(name)) and _positive(rep.get(name))
                and _close(rec.get(name), rep.get(name), DATA_RELATIVE_TOLERANCE)):
            unlike.append(name)
    if not (_finite(rec.get("criterion_pu")) and _finite(rep.get("criterion_pu"))
            and _close(rec.get("criterion_pu"), rep.get("criterion_pu"), DATA_RELATIVE_TOLERANCE)):
        unlike.append("criterion_pu")
    if unlike:
        run.fail("search_settings", ("margins", city), unlike)
    return _positive(rec.get("step_mw")) and _positive(rec.get("tolerance_mw"))


def margin_allowance(ref_mw, resolution_mw):
    """D-02: the most a margin may differ from `ref_mw`, the larger of the relative tolerance of
    the recorded value and the resolution of the search that produced it."""
    return max(compare.FLOW_RELATIVE_TOLERANCE * abs(ref_mw), resolution_mw)


def _margin_pair(run, city, quantity, reference, got, allowance):
    """Compare one margin-table quantity; `allowance` is the quantity's tolerance."""
    run.counts["margin_comparisons"] += 1
    if not _finite(reference) or not _finite(got):
        run.fail("margin_value", ("margins", city), quantity)
        return
    _record(run.worst, _deviation(quantity, reference, got, allowance, ("margins", city)))
    if not abs(got - reference) <= allowance + compare.COMPARISON_EPSILON:
        run.fail("margin_value", ("margins", city), quantity)


def _compare_margin(run, city, recorded, replayed):
    derivable = _check_search_settings(run, city, recorded, replayed)
    rec, rep = _details(recorded), _details(replayed)
    rec_class = _MARGIN_CLASSES.get(rec.get("bounded_by"))
    rep_class = _MARGIN_CLASSES.get(rep.get("bounded_by"))
    if rec_class is None or rep_class is None or rec_class != rep_class:
        run.fail("margin_bound_class", ("margins", city))
        return
    if rec.get("bounded_by") != rep.get("bounded_by"):
        run.notes["bound_member_differs"] += 1
    if recorded.get("critical_bus") != replayed.get("critical_bus"):
        run.notes["critical_bus_differs"] += 1
    if not derivable:
        return
    resolution = rec["step_mw"] if rec_class == _RATING_CLASS else rec["tolerance_mw"]
    for quantity in ("margin_mw", "limit_transfer_mw"):
        reference = recorded.get(quantity)
        allowance = margin_allowance(reference, resolution) if _finite(reference) else None
        _margin_pair(run, city, quantity, reference, replayed.get(quantity), allowance)
    reference, got = recorded.get("base_transfer_mw"), replayed.get("base_transfer_mw")
    _margin_pair(run, city, "base_transfer_mw", reference, got,
                 compare.flow_allowance(reference) if _finite(reference) else None)
    if rec_class == _RATING_CLASS:
        run.counts["margin_quantised"] += 1
        return
    _margin_pair(run, city, "min_voltage_pu", recorded.get("min_voltage_pu"),
                 replayed.get("min_voltage_pu"), compare.VOLTAGE_TOLERANCE_PU)
    reference = recorded.get("voltage_limit_mva")
    _margin_pair(run, city, "voltage_limit_mva", reference, replayed.get("voltage_limit_mva"),
                 compare.flow_allowance(reference) if _finite(reference) else None)


def _dispatch_pair(run, city, quantity, reference, got):
    if not _finite(reference) or not _finite(got):
        run.fail("dispatch_value", ("dispatch", city), quantity)
        return
    allowance = compare.flow_allowance(reference)
    _record(run.worst, _deviation(quantity, reference, got, allowance, ("dispatch", city)))
    if not compare.within_flow(reference, got):
        run.fail("dispatch_value", ("dispatch", city), quantity)


def _factor_gap(row):
    """(gap, band) between the applied rating and the voltage limit of a dispatch row."""
    applied, limit = row.get("applied_mva"), row.get("voltage_limit_mva")
    if not _finite(applied) or not _finite(limit):
        return None
    return abs(applied - limit), compare.flow_allowance(applied)


def _compare_dispatch(run, city, recorded, replayed):
    run.counts["dispatch_comparisons"] += 1
    _dispatch_pair(run, city, "dispatched_mva", recorded.get("dispatched_mva"),
                   replayed.get("dispatched_mva"))
    rec_factor, rep_factor = recorded.get("limiting_factor"), replayed.get("limiting_factor")
    if rec_factor == rep_factor == "voltage_stability":
        run.counts["dispatch_informative"] += 1
        _dispatch_pair(run, city, "voltage_limit_mva", recorded.get("voltage_limit_mva"),
                       replayed.get("voltage_limit_mva"))
    if rec_factor == rep_factor and rec_factor in constants.LIMITING_FACTORS:
        return
    if rec_factor not in constants.LIMITING_FACTORS or rep_factor not in constants.LIMITING_FACTORS:
        run.fail("limiting_factor", ("dispatch", city), "unknown")
        return
    near = []
    for row in (recorded, replayed):
        gap = _factor_gap(row)
        if gap is not None and gap[0] <= gap[1] + compare.COMPARISON_EPSILON:
            near.append(gap)
    if near:
        gap, band = min(near, key=lambda item: item[0] / item[1])
        run.borderline("limiting_factor", ("dispatch", city), gap, band)
    else:
        run.fail("limiting_factor", ("dispatch", city), "different")


def compare_run(recorded, replayed):
    """Compare a recorded Side with a replayed Side; returns a RunComparison."""
    run = _Run()
    if recorded.n_contingencies != replayed.n_contingencies:
        run.fail("n_contingencies", None, None)
    if recorded.rate_set != replayed.rate_set:
        run.fail("rate_set", None, None)
    for name, side in (("recorded", recorded), ("replayed", replayed)):
        for check, where in side.problems:
            run.fail(check, where, name)
    for city in constants.CITIES:
        if city in recorded.dispatch and city in replayed.dispatch:
            _check_rating_data(run, city, recorded.dispatch[city], replayed.dispatch[city])
            _compare_dispatch(run, city, recorded.dispatch[city], replayed.dispatch[city])
        if city in recorded.margins and city in replayed.margins:
            _compare_margin(run, city, recorded.margins[city], replayed.margins[city])
    _compare_violations(run, recorded, replayed)
    return run.result()


# -- the gate ------------------------------------------------------------------------------------

Gate = collections.namedtuple("Gate", ["word", "summary", "detail"])


def gate(compared, exclusions, runs_in_snapshot, configurations):
    """The verdict over many comparisons (D-04). `compared` is a list of (run_id, RunComparison).
    Pass needs a replayed run, a non-empty set comparison and no failure; a failure beats
    incomplete; incomplete beats pass."""
    nonempty = sum(sum(item.counts["outages_" + kind] for kind in KINDS) for _, item in compared)
    failing = any(not item.passed for _, item in compared)
    if failing:
        word = "fail"
    elif compared and nonempty:
        word = "pass"
    else:
        word = "incomplete"
    return Gate(word, None, None)
