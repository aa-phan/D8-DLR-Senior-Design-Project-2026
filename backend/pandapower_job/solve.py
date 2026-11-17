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
import math

import pandapower as pp

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
