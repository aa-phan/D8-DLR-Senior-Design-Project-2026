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
