"""
Amps-to-MVA conversion for the PSS/E branch rating (pss-e-integration Phase 1, D-06).

    circuit amps = amps per conductor x subconductors per phase
    circuit MVA  = sqrt(3) x line kV x circuit amps / 1000

No function here takes a power factor: PSS/E branch ratings are apparent power (MVA), and
city_rating.rating_mw (per conductor, scaled by power factor 0.95) is never an input.
Standard library only, Python 3.7 syntax.
"""

import math


def _positive_number(name, value):
    """`value` as a float; ValueError naming `name` unless it is a finite number > 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a number" % name)
    try:
        number = float(value)
    except OverflowError:
        raise ValueError("%s is out of range" % name)
    if not (math.isfinite(number) and number > 0):
        raise ValueError("%s must be finite and greater than 0" % name)
    return number


def _count(name, value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("%s must be an integer of at least 1" % name)
    return value


def circuit_amps(amps_per_conductor, subconductors_per_phase):
    """Per-circuit amperes: the per-conductor rating times the bundle count."""
    amps = _positive_number("amps_per_conductor", amps_per_conductor)
    count = _count("subconductors_per_phase", subconductors_per_phase)
    return amps * count


def circuit_mva(amps_per_conductor, subconductors_per_phase, line_voltage_kv):
    """Per-circuit MVA: sqrt(3) x kV x circuit amps / 1000, with no power factor."""
    kv = _positive_number("line_voltage_kv", line_voltage_kv)
    return math.sqrt(3) * kv * circuit_amps(amps_per_conductor, subconductors_per_phase) / 1000.0


def mva_to_circuit_amps(mva, line_voltage_kv):
    """The per-circuit amperes that correspond to `mva` at `line_voltage_kv` (inverse of circuit_mva)."""
    apparent = _positive_number("mva", mva)
    kv = _positive_number("line_voltage_kv", line_voltage_kv)
    return apparent * 1000.0 / (math.sqrt(3) * kv)
