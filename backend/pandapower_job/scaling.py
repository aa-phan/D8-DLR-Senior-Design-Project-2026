"""
Minimal scaling for NET-03 (pandapower-solver Phase 1, plan 01-08: PSE-02, NET-03).

Research Pattern 7. The PSS/E job scales a city's copy of the case with `scal_2` to a target load
and a target generation (`psse_job.study.scale_city_case`); this module reproduces that on a
pandapower network. Phase 2 promotes it into the engine's `scale_case`.

The rules it reproduces, and which measured detail (`ScalingDetails`) decides each:

- Loads: one factor, `target load / own load`, on P and Q of every in-service load (constant power
  factor, as `scal_2` is believed to do). Not a detail: the Q-with-P measurement is about the
  increment form the margin search uses, and is reported in `ScalingDetails` for Phase 2.
- Generation: one factor on the P of every in-service machine. Whether the swing machine's own
  P (the ext_grid's `psse_pg_mw`) is part of the total the factor is computed from, and is scaled
  with the rest, is `swing_in_total`.
- Clamping: a machine that the factor pushes past its P limits is held at the limit only when
  `clamped_at_limits` is "yes". With clamping the generation total falls short of the target by
  design, so the read-back of the generation total is skipped when a machine was held.

A detail is "yes", "no" or "inconclusive" (`DETAIL_VALUES`). The rules that need a detail refuse
rather than guess: `ScalingUndetermined` when `swing_in_total` is inconclusive, or when
`clamped_at_limits` is inconclusive and at least one machine would pass a limit. Targets outside
the factor bounds and a read-back that misses its target are `ScalingRefused`. The bounds and the
read-back tolerance are imported from `psse_job.study`, so the two solvers refuse the same
targets. Messages hold a reason word and nothing else.

`scale_city` and `inject_snapshot` return a deep copy; the net they are given is not changed.
"""

import collections
import copy
import math

from psse_job import study

DETAIL_VALUES = ("yes", "no", "inconclusive")

# Two MW values are equal when they differ by at most this much. It is larger than the resolution
# PSS/E prints P with in a RAW file (RAW_PRINT_RESOLUTION_MW), so values that differ only by print
# rounding classify as equal; no classification compares floats for equality.
MW_TOLERANCE = 0.01
RAW_PRINT_RESOLUTION_MW = 1e-4
# Two ratios (after over before) are equal when they differ by at most this much.
RATIO_TOLERANCE = 1e-4
# A quantity counts as having changed only when its relative change reaches this.
MIN_RELATIVE_CHANGE = 1e-3
# Binary rounding slack so a boundary written in decimal is not lost; far below every threshold.
_BOUNDARY_SLACK = 1e-12

ScalingDetails = collections.namedtuple(
    "ScalingDetails", ["swing_in_total", "clamped_at_limits", "q_scales_with_p", "evidence"])


class ScalingRefused(ValueError):
    """The scaling cannot be done or did not take. `reason` is one word; the message holds no figure."""

    def __init__(self, reason):
        self.reason = reason
        ValueError.__init__(self, "scaling refused: %s" % reason)


class ScalingUndetermined(ValueError):
    """A needed detail is inconclusive, so the scaling rule is unknown. `reason` names the detail."""

    def __init__(self, reason):
        self.reason = reason
        ValueError.__init__(self, "scaling undetermined: %s" % reason)


def _check_details(details):
    for name in ("swing_in_total", "clamped_at_limits", "q_scales_with_p"):
        if getattr(details, name) not in DETAIL_VALUES:
            raise ValueError("a scaling detail is not one of %s" % (DETAIL_VALUES,))


def _in_service(table):
    return table.in_service.astype(bool)


def _factor(own, target, reason):
    """The factor target/own, refused when there is nothing to scale or it is outside the bounds."""
    low, high = study.SCALE_FACTOR_BOUNDS
    if not own > 0.0:
        raise ScalingRefused(reason + "_none")
    ratio = target / own
    if not low <= ratio <= high:
        raise ScalingRefused(reason + "_bounds")
    return ratio


def _read_back(read, target, reason):
    if not abs(read - target) <= study.SCALE_TOLERANCE * target:
        raise ScalingRefused(reason + "_read_back")


def scale_city(net, scaling, details):
    """
    A deep copy of `net` scaled to `scaling.load_mw` and `scaling.gen_mw` under `details` (see the
    module docstring). Raises ScalingRefused and ScalingUndetermined; the net is never changed.
    """
    _check_details(details)
    if details.swing_in_total == "inconclusive":
        raise ScalingUndetermined("swing_in_total")
    swing_in = details.swing_in_total == "yes"
    scaled = copy.deepcopy(net)

    loads = scaled.load.index[_in_service(scaled.load)]
    own_load = float(scaled.load.loc[loads, "p_mw"].sum())
    load_factor = _factor(own_load, scaling.load_mw, "load")

    gens = scaled.gen.index[_in_service(scaled.gen)]
    swing = scaled.ext_grid.index[_in_service(scaled.ext_grid)] if swing_in else []
    own_gen = float(scaled.gen.loc[gens, "p_mw"].sum())
    if swing_in:
        own_gen += float(scaled.ext_grid.loc[swing, "psse_pg_mw"].sum())
    gen_factor = _factor(own_gen, scaling.gen_mw, "generation")

    new_gen = scaled.gen.loc[gens, "p_mw"] * gen_factor
    low, high = scaled.gen.loc[gens, "min_p_mw"], scaled.gen.loc[gens, "max_p_mw"]
    new_swing = scaled.ext_grid.loc[swing, "psse_pg_mw"] * gen_factor if swing_in else None
    swing_low = scaled.ext_grid.loc[swing, "psse_pb_mw"] if swing_in else None
    swing_high = scaled.ext_grid.loc[swing, "psse_pt_mw"] if swing_in else None

    past = int(((new_gen > high) | (new_gen < low)).sum())
    if swing_in:
        past += int(((new_swing > swing_high) | (new_swing < swing_low)).sum())
    held = 0
    if past:
        if details.clamped_at_limits == "inconclusive":
            raise ScalingUndetermined("clamped_at_limits")
        if details.clamped_at_limits == "yes":
            held = past
            new_gen = new_gen.clip(lower=low, upper=high)
            if swing_in:
                new_swing = new_swing.clip(lower=swing_low, upper=swing_high)

    scaled.load.loc[loads, "p_mw"] = scaled.load.loc[loads, "p_mw"] * load_factor
    scaled.load.loc[loads, "q_mvar"] = scaled.load.loc[loads, "q_mvar"] * load_factor
    scaled.gen.loc[gens, "p_mw"] = new_gen
    if swing_in:
        scaled.ext_grid.loc[swing, "psse_pg_mw"] = new_swing

    _read_back(float(scaled.load.loc[loads, "p_mw"].sum()), scaling.load_mw, "load")
    if not held:
        total = float(scaled.gen.loc[gens, "p_mw"].sum())
        if swing_in:
            total += float(scaled.ext_grid.loc[swing, "psse_pg_mw"].sum())
        _read_back(total, scaling.gen_mw, "generation")
    return scaled


# -- the injected snapshot -----------------------------------------------------------------------


def _by_name(case, section):
    """{"bus-id": values} of the records of `section` (every status; the net holds them all)."""
    return {"%d-%s" % (rec.values["I"], rec.values["ID"]): rec.values
            for rec in case.sections[section]}


def inject_snapshot(net, presolve_case):
    """
    A deep copy of `net` carrying PSS/E's own post-scaling values from the pre-solve snapshot
    `presolve_case` (a ParsedCase): every machine's PG (the swing machine's into `psse_pg_mw`) and
    every load's P and Q, matched by the `bus-id` names the builder gives. The run built on it is
    the diagnostic of research Pattern 7: if it passes where the algorithm run fails, the scaling
    rule is wrong and the network is not; if both fail, the network or the settings are. A snapshot
    missing any element of the net is ScalingRefused("snapshot_missing_element").
    """
    machines = _by_name(presolve_case, "generator")
    loads = _by_name(presolve_case, "load")
    injected = copy.deepcopy(net)
    wanted = (list(injected.gen.name), list(injected.ext_grid.name))
    if (any(name not in machines for names in wanted for name in names)
            or any(name not in loads for name in injected.load.name)):
        raise ScalingRefused("snapshot_missing_element")
    for index in injected.gen.index:
        injected.gen.at[index, "p_mw"] = machines[injected.gen.at[index, "name"]]["PG"]
    for index in injected.ext_grid.index:
        injected.ext_grid.at[index, "psse_pg_mw"] = machines[
            injected.ext_grid.at[index, "name"]]["PG"]
    for index in injected.load.index:
        values = loads[injected.load.at[index, "name"]]
        injected.load.at[index, "p_mw"] = values["PL"]
        injected.load.at[index, "q_mvar"] = values["QL"]
    return injected


# -- the analyser: the session's experiments into the three details ------------------------------

_SWING_IDE = 3
SWING_EXPERIMENT = "swing_in_total"
CLAMP_EXPERIMENTS = ("clamp_at_limits_x1_5", "clamp_at_limits_x3")
Q_EXPERIMENT = "q_with_p"


def _same(first, second, tolerance):
    return abs(first - second) <= tolerance + _BOUNDARY_SLACK


def _records(experiments):
    """{name: experiment record} from the session's list or its experiments.json document."""
    if isinstance(experiments, dict):
        experiments = experiments.get("experiments")
    return {item.get("name"): item for item in experiments or () if isinstance(item, dict)}


def _finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _inputs(records, snapshots, name, members):
    """
    (record, cases, None) for an experiment that ran and delivered every snapshot in `members`
    (names of record fields), else (None, None, evidence) with the one-word reason.
    """
    record = records.get(name)
    if record is None:
        return None, None, {"reason": "missing"}
    if record.get("status") != "ok":
        return None, None, {"reason": "failed", "detail": list(record.get("detail") or ())}
    cases = {}
    for field in members:
        member = record.get(field)
        if member is None:
            return None, None, {"reason": "no_snapshot"}
        if member not in snapshots:
            return None, None, {"reason": "snapshot_not_delivered"}
        cases[field] = snapshots[member]
    return record, cases, None


def _swing_buses(case):
    return {rec.values["I"] for rec in case.sections["bus"] if rec.values["IDE"] == _SWING_IDE}


def _live_machines(case):
    return [rec.values for rec in case.sections["generator"] if rec.values["STAT"] == 1]


def _swing_in_total(records, snapshots, evidence):
    record, cases, why = _inputs(records, snapshots, SWING_EXPERIMENT, ("before",))
    if why is None:
        totals = record.get("totals_before")
        total = totals.get("gen_mw") if isinstance(totals, dict) else None
        if not _finite(total):
            why = {"reason": "no_totals"}
    if why is not None:
        evidence[SWING_EXPERIMENT] = why
        return "inconclusive"
    case = cases["before"]
    swing_buses = _swing_buses(case)
    machines = _live_machines(case)
    with_swing = sum(item["PG"] for item in machines)
    without = sum(item["PG"] for item in machines if item["I"] not in swing_buses)
    equal_with = _same(total, with_swing, MW_TOLERANCE)
    equal_without = _same(total, without, MW_TOLERANCE)
    evidence[SWING_EXPERIMENT] = {
        "reason": "measured", "equals_total_with_swing": equal_with,
        "equals_total_without_swing": equal_without,
        "machines": len(machines), "swing_machines": sum(
            1 for item in machines if item["I"] in swing_buses)}
    if equal_with and not equal_without:
        return "yes"
    if equal_without and not equal_with:
        return "no"
    return "inconclusive"


def _clamp_one(record, before, after):
    """(detail, counts) of one clamp experiment: which machines the factor pushes past their P
    maximum, and where each ends up."""
    totals, targets = record.get("totals_before"), record.get("targets")
    own = totals.get("gen_mw") if isinstance(totals, dict) else None
    goal = targets.get("gen_mw") if isinstance(targets, dict) else None
    if not _finite(own) or not _finite(goal) or not own > 0.0:
        return "inconclusive", {"reason": "no_totals"}
    factor = goal / own
    swing_buses = _swing_buses(before)
    ends = {(item["I"], item["ID"]): item["PG"] for item in _live_machines(after)}
    counts = {"reason": "measured", "candidates": 0, "at_limit": 0, "above_limit": 0, "other": 0}
    for item in _live_machines(before):
        if item["I"] in swing_buses or not item["PG"] > 0.0:
            continue
        limit = item["PT"]
        if not item["PG"] * factor > limit + MW_TOLERANCE + _BOUNDARY_SLACK:
            continue
        counts["candidates"] += 1
        end = ends.get((item["I"], item["ID"]))
        if end is not None and _same(end, limit, MW_TOLERANCE):
            counts["at_limit"] += 1
        elif end is not None and end > limit:
            counts["above_limit"] += 1
        else:
            counts["other"] += 1
    if counts["candidates"] == 0:
        return "inconclusive", counts
    if counts["at_limit"] == counts["candidates"]:
        return "yes", counts
    if counts["above_limit"] == counts["candidates"]:
        return "no", counts
    return "inconclusive", counts


def _clamped_at_limits(records, snapshots, evidence):
    found = {}
    details = []
    for name in CLAMP_EXPERIMENTS:
        record, cases, why = _inputs(records, snapshots, name, ("before", "after"))
        if why is not None:
            found[name] = why
            continue
        detail, counts = _clamp_one(record, cases["before"], cases["after"])
        found[name] = counts
        details.append(detail)
    decisive = {detail for detail in details if detail != "inconclusive"}
    if decisive == {"yes", "no"}:
        found["combined"] = "contradiction"
        result = "inconclusive"
    elif len(decisive) == 1:
        found["combined"] = "agreement"
        result = decisive.pop()
    else:
        found["combined"] = "no_evidence"
        result = "inconclusive"
    evidence["clamped_at_limits"] = found
    return result


def _q_with_p(records, snapshots, evidence):
    record, cases, why = _inputs(records, snapshots, Q_EXPERIMENT, ("before", "after"))
    sinks = record.get("sink_buses") if record is not None else None
    if why is None and not sinks:
        why = {"reason": "no_sink_buses"}
    if why is not None:
        evidence[Q_EXPERIMENT] = why
        return "inconclusive"
    after = {key: values for key, values in _by_name(cases["after"], "load").items()
             if values["STATUS"] == 1}
    counts = {"reason": "measured", "loads": 0, "yes": 0, "no": 0, "undecided": 0,
              "no_information": 0}
    for key, before in _by_name(cases["before"], "load").items():
        if before["I"] not in sinks or before["STATUS"] != 1 or key not in after:
            continue
        counts["loads"] += 1
        p0, q0, p1, q1 = before["PL"], before["QL"], after[key]["PL"], after[key]["QL"]
        if abs(p0) <= RAW_PRINT_RESOLUTION_MW or abs(q0) <= RAW_PRINT_RESOLUTION_MW:
            counts["no_information"] += 1
            continue
        p_ratio, q_ratio = p1 / p0, q1 / q0
        if abs(p_ratio - 1.0) + _BOUNDARY_SLACK < MIN_RELATIVE_CHANGE:
            counts["no_information"] += 1
        elif _same(q_ratio, p_ratio, RATIO_TOLERANCE):
            counts["yes"] += 1
        elif _same(q_ratio, 1.0, RATIO_TOLERANCE):
            counts["no"] += 1
        else:
            counts["undecided"] += 1
    evidence[Q_EXPERIMENT] = counts
    if counts["yes"] and not counts["no"] and not counts["undecided"]:
        return "yes"
    if counts["no"] and not counts["yes"] and not counts["undecided"]:
        return "no"
    return "inconclusive"


def analyse_scaling_details(experiments, snapshots):
    """
    The three scaling details of PSE-02 from the session's scaling experiments.

    `experiments` is the list in `scaling/experiments.json` (or the document that holds it) and
    `snapshots` maps each RAW member name the records mention to its ParsedCase. Each detail is
    "yes", "no" or "inconclusive" (DETAIL_VALUES); `evidence` holds counts and one-word reasons per
    detail, never a bus number or a value. An experiment that failed, is missing, or did not
    deliver its snapshots makes its detail inconclusive with the reason in the evidence.

    - swing_in_total: the generation total PSS/E read equals the sum of every machine's P ("yes")
      or of the machines away from the swing bus ("no"); both or neither is inconclusive.
    - clamped_at_limits: of the machines the factor of a clamp experiment pushes past their P
      maximum, all sit at it afterwards ("yes") or all are above it ("no"); a mixture, or no
      machine reaching a limit, is inconclusive. The two clamp experiments are combined: one
      decisive answer stands, opposite answers are inconclusive.
    - q_scales_with_p: at the sink loads the Q ratio equals the P ratio ("yes") or Q did not move
      ("no"), judged only where P moved by MIN_RELATIVE_CHANGE and Q is not zero; any disagreement
      between loads is inconclusive.
    """
    records = _records(experiments)
    evidence = {}
    swing = _swing_in_total(records, snapshots, evidence)
    clamped = _clamped_at_limits(records, snapshots, evidence)
    q_scaled = _q_with_p(records, snapshots, evidence)
    return ScalingDetails(swing, clamped, q_scaled, evidence)
