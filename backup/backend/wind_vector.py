"""
Wind u/v Vector Decomposition (Phase 3 Plan 02, D-02)
==================================================================
Pure math: stateless, no I/O, no config read, no logging -- the same tier
as `thermal_model.perpendicular_wind`, which this module must agree with.

**Convention.** The direction argument throughout this module is the
METEOROLOGICAL wind direction: degrees from North, the direction the wind
is coming FROM. This is not asserted independently here -- it is the exact
convention `thermal_model.perpendicular_wind` declares in its own
docstring ("Meteorological wind direction (degrees from North, direction
wind is coming FROM)") and confirms in its body by flipping to flow
direction before projecting. `u` is positive eastward and `v` is positive
northward. The formulas come from ECMWF's published wind-component pair
[CITED: https://confluence.ecmwf.int/pages/viewpage.action?pageId=133262398].

**Why this module exists at all.** A regression cannot be fitted on a
direction in degrees, because the value wraps discontinuously at the
0/360 boundary -- 359 degrees and 1 degree are two degrees apart
physically but 358 apart numerically -- and both a linear model and a
tree will learn nonsense at that wrap. A u/v vector decomposition has no
such seam: a small physical change in direction is always a small
numerical change in both components.

**Why a sign error here is silent and dangerous.** `perpendicular_wind`
folds the wind-to-line angle to an acute angle before projecting (see
`thermal_model.py`), so a 180-degree-flipped wind still yields a
plausible-looking ampacity -- the bug survives every smoke test and every
eyeball check. The round-trip equality test against `perpendicular_wind`
itself, across the full direction circle, is the only real guard that
this decomposition agrees with the repo's own wind convention rather than
merely claiming to.
"""

from typing import Tuple, Union

import numpy as np

ArrayOrFloat = Union[float, np.ndarray]


def to_uv(
    wind_speed_ms: ArrayOrFloat, wind_dir_deg: ArrayOrFloat
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Meteorological (speed, FROM-direction) -> (u eastward, v northward), m/s.

    `u` and `v` are the negative of the speed times the sine and cosine of
    the direction respectively -- negative because the wind's FLOW is
    opposite its FROM-direction (a wind FROM due north, direction 0, blows
    TOWARD the south, so its northward component v is negative).

    Args:
        wind_speed_ms: wind speed, m/s (non-negative).
        wind_dir_deg: meteorological direction, degrees from North, the
            direction the wind is coming FROM.

    Returns:
        (u, v) as `np.ndarray`, matching the broadcast shape of the inputs.
    """
    ws = np.asarray(wind_speed_ms, dtype=float)
    phi = np.radians(np.asarray(wind_dir_deg, dtype=float))
    u = -ws * np.sin(phi)
    v = -ws * np.cos(phi)
    return u, v


def from_uv(u: ArrayOrFloat, v: ArrayOrFloat) -> Tuple[np.ndarray, np.ndarray]:
    """
    (u, v) -> (speed m/s, meteorological FROM-direction deg in [0, 360)).

    Speed is recovered with `np.hypot`. Direction is recovered by taking
    `arctan2(u, v)` (note the argument order -- u first, v second, which is
    what makes the +180 offset below land on the FROM-direction rather than
    the flow direction), converting to degrees, adding 180, and reducing
    modulo 360 so the result always lands in the half-open circle
    `[0, 360)`, matching `units_def.PIPELINE_SCHEMA`'s `wind_direction`
    range.

    The returned direction is directly consumable by
    `thermal_model.perpendicular_wind` with no adjustment -- that claim is
    enforced by this repo's round-trip test
    (`backend/tests/wind_vector_test.py`), not merely stated here.

    Args:
        u: eastward wind component, m/s.
        v: northward wind component, m/s.

    Returns:
        (speed, direction_deg) as `np.ndarray`, matching the broadcast
        shape of the inputs.
    """
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    speed = np.hypot(u, v)
    direction = np.mod(180.0 + np.degrees(np.arctan2(u, v)), 360.0)
    return speed, direction
