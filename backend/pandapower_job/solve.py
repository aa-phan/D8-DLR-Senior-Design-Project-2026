"""
The load-flow solve of the pandapower solver (pandapower-solver Phase 1, plan 01-08: NET-03).

D-14 says the solve settings are copied from what PSS/E was doing, not chosen. This module holds
the settings record (`SolveSettings`), the one place a solve is run (`run_load_flow`) and the
rule for when a solve counts as converged. Phase 2 extends it into the engine's stored solve
settings.

Settings table (research Pattern 2), PSS/E setting to pandapower argument:

- var limits applied      -> `enforce_q_lims` True or False, copied. pandapower's loop converts a
  machine that breaks a Q limit to a fixed-Q machine at the limit and never converts it back; the
  reference (swing) machine's Q is never limited. Whether PSS/E does the same is not known.
- mismatch tolerance, MVA -> `tolerance_mva`
- iteration limit         -> `max_iteration`
- tap, switched-shunt and area-interchange adjustment, flat start, non-divergent solution have no
  pandapower equivalent used here: the builder refuses a case where they could matter.

A load flow counts as converged only when `runpp` raises nothing, `net.converged` is True, no
in-service bus has a NaN voltage and none is below the collapse limit (the same limit the PSS/E
job applies). A solve that raises, whatever the exception, is `SolveOutcome(False, <class name>,
None)`: the message is never kept, because pandapower messages can name buses.

`run_load_flow` solves the net it is given; callers pass a copy.
"""

import collections
import collections.abc
import inspect
import math
import numbers

import pandapower as pp

# Two bus voltages agree when they differ by at most this (per unit). It is far above solver noise
# and far below the 0.01 pu a reactive-limit effect has to show to be seen at all.
FINGERPRINT_TOLERANCE_PU = 1e-6
# Binary rounding slack so a gap written in decimal exactly at the tolerance counts as agreeing.
_AGREE_SLACK = 1e-12

# `enforce_q_lims` is True, False or None; None means "inconclusive: the caller solves both ways".
# `sources` maps each setting to where its value came from and `deviations` lists every departure
# from D-14 (a value that could not be read and was replaced by pandapower's default).
SolveSettings = collections.namedtuple(
    "SolveSettings",
    ["enforce_q_lims", "tolerance_mva", "max_iteration", "collapse_voltage_pu", "sources",
     "deviations"])
SolveOutcome = collections.namedtuple("SolveOutcome", ["converged", "reason", "iterations"])


def _iterations(net):
    try:
        value = net._ppc["iterations"]   # noqa: SLF001 - pandapower keeps the count only here
    except (AttributeError, KeyError, TypeError):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def run_load_flow(net, settings, enforce_q_lims):
    """
    Solve `net` in place with Newton-Raphson under `settings` and the explicit `enforce_q_lims`
    (True or False; `settings.enforce_q_lims` None means the caller runs both, so None here is a
    ValueError). Returns a SolveOutcome; see the module docstring for the convergence rule.
    """
    if not isinstance(enforce_q_lims, bool):
        raise ValueError("enforce_q_lims must be True or False")
    try:
        pp.runpp(net, algorithm="nr", calculate_voltage_angles=True,
                 enforce_q_lims=enforce_q_lims, tolerance_mva=settings.tolerance_mva,
                 max_iteration=settings.max_iteration)
    except Exception as error:  # noqa: BLE001 - any failure is a non-converged outcome
        return SolveOutcome(False, type(error).__name__, None)
    iterations = _iterations(net)
    if not bool(net.converged):
        return SolveOutcome(False, "not_converged", iterations)
    live = net.bus.index[net.bus.in_service.astype(bool)]
    voltages = net.res_bus.vm_pu.reindex(live)
    if any(math.isnan(float(value)) for value in voltages):
        return SolveOutcome(False, "nan_voltage", iterations)
    if any(not float(value) >= settings.collapse_voltage_pu for value in voltages):
        return SolveOutcome(False, "voltage_collapse", iterations)
    return SolveOutcome(True, None, iterations)


# -- settings copied from the session ------------------------------------------------------------

_DEFAULT_VARIANT = "default"
_IMMEDIATE_VARIANT = "var_limits_immediate"
_IGNORE_VARIANT = "var_limits_ignore"


def _voltages(payload):
    """{bus number: pu} of a fingerprint payload, or None when it holds no usable solve."""
    solve = payload.get("solve")
    if isinstance(solve, dict) and solve.get("converged") is False:
        return None
    rows = payload.get("buses")
    if not rows:
        return None
    table = {}
    for row in rows:
        value = row.get("pu")
        if isinstance(value, numbers.Real) and not isinstance(value, bool) and math.isfinite(value):
            table[int(row["number"])] = float(value)
    return table or None


def _agree(first, second):
    """True when two voltage tables agree on every common bus; None when they share no bus."""
    common = first.keys() & second.keys()
    if not common:
        return None
    return max(abs(first[number] - second[number]) for number in common) <= (
        FINGERPRINT_TOLERANCE_PU + _AGREE_SLACK)


def _classify_point(variants):
    """"on", "off" or "inconclusive" for one (city, point) that holds fingerprints by variant."""
    wanted = (_DEFAULT_VARIANT, _IMMEDIATE_VARIANT, _IGNORE_VARIANT)
    if any(name not in variants for name in wanted):
        return "inconclusive"
    with_immediate = _agree(variants[_DEFAULT_VARIANT], variants[_IMMEDIATE_VARIANT])
    with_ignore = _agree(variants[_DEFAULT_VARIANT], variants[_IGNORE_VARIANT])
    if with_immediate is None or with_ignore is None:
        return "inconclusive"
    if with_immediate and not with_ignore:
        return "on"
    if with_ignore and not with_immediate:
        return "off"
    return "inconclusive"


def classify_var_limits(fingerprints):
    """
    Whether PSS/E's default solve applies generator var limits: "on", "off" or "inconclusive".

    `fingerprints` are the session's fingerprint payloads (`city`, `point`, `variant`, `solve`,
    `buses`). At each (city, point) the three variants default, var_limits_immediate and
    var_limits_ignore are compared by bus voltage, joined by bus number: the default solve
    behaves like the "on" variant when it agrees with the immediate one (within
    FINGERPRINT_TOLERANCE_PU, inclusive) and differs from the ignore one, like the "off" variant
    for the reverse, and the point says nothing when all agree or the default matches neither.
    A fingerprint that did not converge is skipped. Points that decide opposite ways raise
    ValueError naming the conflict: that is a human decision (D-14), not a guess.
    """
    points = {}
    for payload in fingerprints:
        voltages = _voltages(payload)
        if voltages is None:
            continue
        key = (payload.get("city"), payload.get("point"))
        points.setdefault(key, {})[payload.get("variant")] = voltages
    verdicts = [_classify_point(variants) for variants in points.values()]
    on, off = verdicts.count("on"), verdicts.count("off")
    if on and off:
        raise ValueError("var limit fingerprints conflict: %d point(s) say on and %d say off"
                         % (on, off))
    if on:
        return "on"
    if off:
        return "off"
    return "inconclusive"


def _runpp_default(name):
    return inspect.signature(pp.runpp).parameters[name].default


def _valid_tolerance(value):
    return (isinstance(value, numbers.Real) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0.0)


def _valid_iterations(value):
    return isinstance(value, numbers.Integral) and not isinstance(value, bool) and value >= 1


def _copied(name, setting, valid, sources, deviations):
    """The value of the setting `name` read by the session, or pandapower's default and a
    recorded D-14 deviation."""
    if isinstance(setting, dict) and setting.get("status") == "read":
        value = setting.get("value")
        if valid(value):
            sources[name] = "read: %s" % setting.get("source")
            return value
        reason = "invalid value"
    else:
        reason = "unavailable"
    sources[name] = "pandapower default"
    deviations.append("D-14 deviation: %s not copied (%s); pandapower default used" % (name, reason))
    return _runpp_default(name)


def _payloads(settings_json, fingerprint_payloads):
    if isinstance(fingerprint_payloads, collections.abc.Mapping):
        listed = settings_json.get("fingerprints")
        if isinstance(listed, list):
            return [fingerprint_payloads[item["member"]] for item in listed
                    if isinstance(item, dict) and item.get("member") in fingerprint_payloads]
        return list(fingerprint_payloads.values())
    return list(fingerprint_payloads)


def settings_from_session(settings_json, fingerprint_payloads, collapse_voltage_pu):
    """
    The SolveSettings copied from the session (D-14). `settings_json` is `settings/settings.json`
    and `fingerprint_payloads` the fingerprint members, either a mapping of member name to payload
    or a list of payloads. `enforce_q_lims` comes from `classify_var_limits` (None when
    inconclusive: the caller runs both and both must pass); `tolerance_mva` and `max_iteration`
    are the values the session read. A value that could not be read, or is not a usable number,
    is pandapower's own default and one entry of `deviations` naming D-14; `sources` says where
    each value came from. A conflict between decisive fingerprints raises ValueError.
    """
    settings = settings_json.get("settings") or {}
    verdict = classify_var_limits(_payloads(settings_json, fingerprint_payloads))
    sources = {"enforce_q_lims": "fingerprint: %s" % verdict}
    deviations = []
    tolerance = _copied("tolerance_mva", settings.get("mismatch_tolerance_mva"), _valid_tolerance,
                        sources, deviations)
    iterations = _copied("max_iteration", settings.get("iteration_limit"), _valid_iterations,
                         sources, deviations)
    enforce = {"on": True, "off": False, "inconclusive": None}[verdict]
    return SolveSettings(enforce, tolerance, iterations, collapse_voltage_pu, sources,
                         tuple(deviations))
