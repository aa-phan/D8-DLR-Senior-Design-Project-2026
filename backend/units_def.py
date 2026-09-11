# units def
"""
units.py — Dimensional Analysis & Unit Validation Module
=========================================================
Provides a Quantity wrapper that tracks physical units through the DLR pipeline
and raises UnitError whenever a mismatched or unexpected unit is encountered.

Usage
-----
    from units import Q, UnitError, expect_unit, validate_pipeline_row

    wind = Q(5.2, "m/s")
    temp = Q(35.0, "degC")
    rating = Q(900.0, "A")

    # Automatic conversion
    mw = rating.to("MW", voltage_kv=345.0, pf=0.95)

    # Explicit assertion
    expect_unit(wind, "m/s")          # passes
    expect_unit(wind, "km/h")         # raises UnitError
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Union

import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# UNIT REGISTRY
# All known units grouped by physical dimension.
# ──────────────────────────────────────────────────────────────────────────────

UNIT_DIMENSIONS: Dict[str, str] = {
    # Temperature
    "degC": "temperature",
    "degF": "temperature",
    "K":    "temperature",
    # Wind / velocity
    "m/s":  "velocity",
    "km/h": "velocity",
    "mph":  "velocity",
    "knots":"velocity",
    # Current
    "A":    "current",
    "kA":   "current",
    # Power
    "W":    "power",
    "kW":   "power",
    "MW":   "power",
    "GW":   "power",
    # Irradiance
    "W/m2": "irradiance",
    "W/m²": "irradiance",
    # Resistance
    "ohm/m":   "resistance_per_length",
    "ohm/km":  "resistance_per_length",
    "ohm":     "resistance",
    "pu":      "per_unit",            # per-unit (dimensionless, context-dependent)
    # Humidity
    "%":    "fraction_or_percent",
    "frac": "fraction_or_percent",
    # Angle
    "deg":  "angle",
    "rad":  "angle",
    # Length / diameter
    "m":    "length",
    "mm":   "length",
    "ft":   "length",
    "km":   "length",
    # Voltage
    "V":    "voltage",
    "kV":   "voltage",
}

# Conversion factors to a canonical base unit within each dimension
# (base unit is listed first in each group)
CONVERSIONS: Dict[str, float] = {
    # temperature → degC  (offset conversions handled separately)
    "degC":  1.0,
    "degF":  None,   # handled via formula
    "K":     None,   # handled via formula

    # velocity → m/s
    "m/s":   1.0,
    "km/h":  1 / 3.6,
    "mph":   0.44704,
    "knots": 0.514444,

    # current → A
    "A":     1.0,
    "kA":    1_000.0,

    # power → W
    "W":     1.0,
    "kW":    1_000.0,
    "MW":    1_000_000.0,
    "GW":    1_000_000_000.0,

    # irradiance → W/m²
    "W/m2":  1.0,
    "W/m²":  1.0,

    # resistance/length → ohm/m
    "ohm/m":  1.0,
    "ohm/km": 1 / 1_000.0,

    # angle → degrees
    "deg":   1.0,
    "rad":   math.degrees(1.0),

    # length → m
    "m":     1.0,
    "mm":    0.001,
    "ft":    0.3048,
    "km":    1_000.0,

    # voltage → V
    "V":     1.0,
    "kV":    1_000.0,
}


# ──────────────────────────────────────────────────────────────────────────────
# EXCEPTION
# ──────────────────────────────────────────────────────────────────────────────

class UnitError(Exception):
    """Raised when a unit mismatch or unexpected representation is detected."""
    pass


# ──────────────────────────────────────────────────────────────────────────────
# QUANTITY CLASS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Q:
    """
    A scalar or array quantity with an attached unit.

    Parameters
    ----------
    value : numeric or np.ndarray
    unit  : str — must be in UNIT_DIMENSIONS
    label : optional human-readable name for error messages
    """
    value: Any
    unit:  str
    label: str = ""

    def __post_init__(self):
        if self.unit not in UNIT_DIMENSIONS:
            raise UnitError(
                f"Unknown unit '{self.unit}' for quantity '{self.label or self.value}'. "
                f"Registered units: {sorted(UNIT_DIMENSIONS.keys())}"
            )

    @property
    def dimension(self) -> str:
        return UNIT_DIMENSIONS[self.unit]

    # ── Conversion ────────────────────────────────────────────────────────────

    def to(self, target_unit: str, **kwargs) -> "Q":
        """
        Convert this quantity to target_unit.
        Raises UnitError if dimensions are incompatible.

        Special conversions that require extra kwargs:
          A → MW  requires  voltage_kv=<float>, pf=<float>
          MW → A  requires  voltage_kv=<float>, pf=<float>
        """
        if target_unit not in UNIT_DIMENSIONS:
            raise UnitError(f"Unknown target unit '{target_unit}'.")

        src_dim = self.dimension
        tgt_dim = UNIT_DIMENSIONS[target_unit]

        # ── Special cross-dimension conversions ───────────────────────────────
        if src_dim == "current" and tgt_dim == "power":
            vkv = kwargs.get("voltage_kv")
            pf  = kwargs.get("pf", 1.0)
            if vkv is None:
                raise UnitError(
                    "Converting A → MW requires keyword argument voltage_kv=<float>."
                )
            # A → W first, then to target
            amps_in_A = self._to_base()
            watts = math.sqrt(3) * (vkv * 1_000) * amps_in_A * pf
            base_power_q = Q(watts, "W", self.label)
            return base_power_q._from_base(target_unit)

        if src_dim == "power" and tgt_dim == "current":
            vkv = kwargs.get("voltage_kv")
            pf  = kwargs.get("pf", 1.0)
            if vkv is None:
                raise UnitError(
                    "Converting MW → A requires keyword argument voltage_kv=<float>."
                )
            watts = self._to_base()  # value in W
            amps  = watts / (math.sqrt(3) * (vkv * 1_000) * pf)
            return Q(amps, "A", self.label)

        # ── Same-dimension conversions ─────────────────────────────────────────
        if src_dim != tgt_dim:
            raise UnitError(
                f"Cannot convert '{self.unit}' ({src_dim}) → '{target_unit}' ({tgt_dim}): "
                f"incompatible dimensions."
            )

        base_value = self._to_base()
        result_q   = Q(base_value, _base_unit(src_dim), self.label)
        return result_q._from_base(target_unit)

    def _to_base(self) -> float:
        """Convert value to canonical base unit (as a float)."""
        factor = CONVERSIONS.get(self.unit)

        if self.unit == "degF":
            return (self.value - 32) * 5 / 9
        if self.unit == "K":
            return self.value - 273.15
        if self.unit == "frac":
            return self.value * 100   # frac → %

        if factor is None:
            raise UnitError(f"No direct conversion factor for '{self.unit}'.")
        return self.value * factor

    def _from_base(self, target_unit: str) -> "Q":
        """Build a Q in target_unit assuming self.value is already in the base unit."""
        factor = CONVERSIONS.get(target_unit)

        if target_unit == "degF":
            return Q(self.value * 9 / 5 + 32, "degF", self.label)
        if target_unit == "K":
            return Q(self.value + 273.15, "K", self.label)
        if target_unit == "frac":
            return Q(self.value / 100, "frac", self.label)

        if factor is None:
            raise UnitError(f"No inverse conversion factor for '{target_unit}'.")
        return Q(self.value / factor, target_unit, self.label)

    # ── Convenience ───────────────────────────────────────────────────────────

    def assert_unit(self, expected: str):
        """Raise UnitError if this quantity's unit doesn't match expected."""
        if self.unit != expected:
            raise UnitError(
                f"Unit assertion failed for '{self.label or 'quantity'}': "
                f"expected '{expected}' but got '{self.unit}'."
            )
        return self

    def assert_dimension(self, expected_dim: str):
        """Raise UnitError if this quantity's dimension doesn't match expected."""
        if self.dimension != expected_dim:
            raise UnitError(
                f"Dimension assertion failed for '{self.label or 'quantity'}': "
                f"expected '{expected_dim}' but got '{self.dimension}'."
            )
        return self

    def assert_range(self, lo: float, hi: float):
        """Raise UnitError if value falls outside [lo, hi] (sanity check)."""
        v = float(np.mean(self.value))
        if not (lo <= v <= hi):
            raise UnitError(
                f"Range check failed for '{self.label or self.unit}': "
                f"value {v:.4g} is outside expected range [{lo}, {hi}]."
            )
        return self

    def __repr__(self):
        return f"Q({self.value}, '{self.unit}')"


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _base_unit(dimension: str) -> str:
    """Return the canonical base unit for a dimension."""
    _BASE = {
        "temperature":            "degC",
        "velocity":               "m/s",
        "current":                "A",
        "power":                  "W",
        "irradiance":             "W/m²",
        "resistance_per_length":  "ohm/m",
        "resistance":             "ohm",
        "per_unit":               "pu",
        "fraction_or_percent":    "%",
        "angle":                  "deg",
        "length":                 "m",
        "voltage":                "V",
    }
    if dimension not in _BASE:
        raise UnitError(f"No base unit defined for dimension '{dimension}'.")
    return _BASE[dimension]


def expect_unit(q: Q, expected_unit: str) -> Q:
    """Assert q is in expected_unit. Returns q for chaining."""
    return q.assert_unit(expected_unit)


def expect_dimension(q: Q, expected_dim: str) -> Q:
    """Assert q belongs to expected physical dimension. Returns q for chaining."""
    return q.assert_dimension(expected_dim)


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE ROW VALIDATOR
# Wraps the key values from one row of the DLR pipeline output.
# ──────────────────────────────────────────────────────────────────────────────

# KNOWN_PROVIDER_NAMES: the registry of legal provenance values a v3+
# categorical provenance column may hold. A future weather provider
# (Phases 7-10) is registered here, and nowhere else, so D-04 (per-field
# provenance sourced from any registered provider) holds without a schema
# change.
KNOWN_PROVIDER_NAMES: frozenset[str] = frozenset({
    "synoptic",
    "tceq",
    "asos",
    "nsrdb",
    "open_meteo",
})

# PIPELINE_SCHEMA_VERSION: version 1 is the Phase 1-3 baseline (the ten
# columns below, unchanged). Version 2 adds five Phase 4 (C9/C10) columns.
# Version 3 adds four Phase 6 (C4 multi-provider) provenance columns, same
# additive-only rule. The rule this version exists to enforce: keys are
# only ever ADDED, always with "required": False, and no existing key's
# name, unit or range is ever changed. Downstream consumers that only know
# v1 (or v2) keep working unmodified against a v3-produced row — see
# RESEARCH.md Pattern 1, ROADMAP SC2.
PIPELINE_SCHEMA_VERSION: int = 3

PIPELINE_SCHEMA: Dict[str, Dict] = {
    "air_temp": {
        "unit":      "degC",
        "range":     (-20.0, 60.0),
        "required":  True,
    },
    "wind_speed": {
        "unit":      "m/s",
        "range":     (0.0, 50.0),
        "required":  True,
    },
    "wind_direction": {
        "unit":      "deg",
        "range":     (0.0, 360.0),
        "required":  True,
    },
    "wind_perp_ms": {
        "unit":      "m/s",
        "range":     (0.0, 50.0),
        "required":  False,
    },
    "solar_radiation": {
        "unit":      "W/m²",
        "range":     (0.0, 1400.0),
        "required":  False,
    },
    "relative_humidity": {
        "unit":      "%",
        "range":     (0.0, 100.0),
        "required":  False,
    },
    "dlr_amps": {
        "unit":      "A",
        "range":     (100.0, 4000.0),
        "required":  False,
    },
    "dlr_capacity_mw": {
        "unit":      "MW",
        "range":     (50.0, 2500.0),
        "required":  False,
    },
    "static_capacity_mw": {
        "unit":      "MW",
        "range":     (50.0, 2500.0),
        "required":  False,
    },
    "ercot_west_load_mw": {
        "unit":      "MW",
        "range":     (0.0, 30_000.0),
        "required":  False,
    },

    # --- v2 additions (Phase 4 / C9 forecasting, C10 anomaly detection) ---
    "forecast_horizon_min": {
        "unit":      "min",
        "range":     (0.0, 1440.0),
        "required":  False,
    },
    "forecast_amps": {
        "unit":      "A",
        "range":     (100.0, 4000.0),  # matches dlr_amps -- same physical plausibility
        "required":  False,
    },
    "forecast_ci_lower_amps": {
        "unit":      "A",
        "range":     (0.0, 4000.0),  # floor at 0: a lower band edge may legitimately sit under dlr_amps' floor
        "required":  False,
    },
    "forecast_ci_upper_amps": {
        "unit":      "A",
        "range":     (0.0, 8000.0),  # ceiling widened so a genuinely uncertain band is recorded, not clipped
        "required":  False,
    },
    "anomaly_score": {
        "unit":      "pu",  # dimensionless
        "range":     (0.0, 1000.0),
        "required":  False,
    },

    # --- v3 additions (Phase 6 / C4 provider provenance) ---
    "wind_source": {
        "unit":      "categorical",
        "range":     None,
        "required":  False,
        "allowed_values": KNOWN_PROVIDER_NAMES,
    },
    "temp_source": {
        "unit":      "categorical",
        "range":     None,
        "required":  False,
        "allowed_values": KNOWN_PROVIDER_NAMES,
    },
    "humidity_source": {
        "unit":      "categorical",
        "range":     None,
        "required":  False,
        "allowed_values": KNOWN_PROVIDER_NAMES,
    },
    "solar_source": {
        "unit":      "categorical",
        "range":     None,
        "required":  False,
        "allowed_values": KNOWN_PROVIDER_NAMES,
    },
}


def validate_pipeline_row(row: Dict[str, Any], strict: bool = True) -> list[str]:
    """
    Validate a dictionary representing one pipeline observation row against
    PIPELINE_SCHEMA.  Does NOT require Q objects — accepts plain floats and
    infers units from the schema.

    Parameters
    ----------
    row    : dict of column_name → value
    strict : if True, raise UnitError on first failure;
             if False, collect all errors and return them as strings.

    Returns
    -------
    List of error strings (empty list = all checks passed).
    """
    errors: list[str] = []

    for col, spec in PIPELINE_SCHEMA.items():
        value = row.get(col)

        if value is None:
            if spec["required"]:
                msg = f"MISSING required column '{col}' (expected unit: {spec['unit']})"
                if strict:
                    raise UnitError(msg)
                errors.append(msg)
            continue

        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
            msg = f"NON-FINITE value in '{col}': {value}"
            if strict:
                raise UnitError(msg)
            errors.append(msg)
            continue

        if spec.get("unit") == "categorical":
            if value not in spec["allowed_values"]:
                msg = (
                    f"UNKNOWN PROVIDER in '{col}': {value!r} not one of "
                    f"{sorted(spec['allowed_values'])}"
                )
                if strict:
                    raise UnitError(msg)
                errors.append(msg)
            continue

        lo, hi = spec["range"]
        v = float(np.mean(value))
        if not (lo <= v <= hi):
            msg = (
                f"RANGE VIOLATION in '{col}' (unit={spec['unit']}): "
                f"value {v:.4g} outside [{lo}, {hi}]. "
                f"Possible unit mismatch (e.g. kW where MW expected)."
            )
            if strict:
                raise UnitError(msg)
            errors.append(msg)

    return errors


# ──────────────────────────────────────────────────────────────────────────────
# DECORATOR: @check_units
# Annotate a function's parameters with expected units; enforced at call time.
# ──────────────────────────────────────────────────────────────────────────────

def check_units(**expected_units):
    """
    Decorator that enforces Q unit annotations on function arguments.

    Example
    -------
        @check_units(wind_speed="m/s", air_temp="degC")
        def my_rating_func(wind_speed: Q, air_temp: Q) -> Q:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            import inspect
            sig    = inspect.signature(fn)
            params = list(sig.parameters.keys())
            bound  = dict(zip(params, args))
            bound.update(kwargs)

            for param_name, expected_unit in expected_units.items():
                val = bound.get(param_name)
                if val is None:
                    continue
                if not isinstance(val, Q):
                    raise UnitError(
                        f"@check_units: argument '{param_name}' must be a Q object, "
                        f"got {type(val).__name__}."
                    )
                if val.unit != expected_unit:
                    raise UnitError(
                        f"@check_units: argument '{param_name}' has unit '{val.unit}', "
                        f"expected '{expected_unit}'."
                    )
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator