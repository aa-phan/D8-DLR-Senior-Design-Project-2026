# units def test code
"""
test_units.py — Unit Validation Test Suite
==========================================
Runs a battery of test cases, including intentionally introduced unit errors,
and confirms the units module catches every one.

Run with:
    python test_units.py
or via pytest:
    pytest test_units.py -v
"""

import math
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np

from units_def import Q, UnitError, check_units, expect_unit, validate_pipeline_row

# ──────────────────────────────────────────────────────────────────────────────
# TINY TEST HARNESS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name:    str
    passed:  bool
    message: str


_results: list[TestResult] = []


def _run(name: str, fn: Callable) -> TestResult:
    try:
        fn()
        result = TestResult(name, True, "OK")
    except AssertionError as e:
        result = TestResult(name, False, f"AssertionError: {e}")
    except Exception as e:
        result = TestResult(name, False, f"Unexpected {type(e).__name__}: {e}")
    _results.append(result)
    status = "✓ PASS" if result.passed else "✗ FAIL"
    print(f"  {status}  {name}")
    if not result.passed:
        print(f"         └─ {result.message}")
    return result


def _expect_unit_error(fn: Callable, hint: str = "") -> None:
    """Assert that fn() raises UnitError (otherwise the test itself fails)."""
    try:
        fn()
        raise AssertionError(
            f"Expected UnitError but none was raised. {hint}"
        )
    except UnitError:
        pass   # correct — the module caught it


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 1 — BASIC QUANTITY CONSTRUCTION
# ──────────────────────────────────────────────────────────────────────────────

def section_basic_construction():
    print("\n[1] Basic Quantity Construction")

    def test_valid_units():
        q = Q(5.2, "m/s", "wind_speed")
        assert q.dimension == "velocity"
        assert q.unit == "m/s"

    def test_unknown_unit():
        _expect_unit_error(lambda: Q(5.2, "furlongs/fortnight"), "Unknown unit should raise.")

    def test_assert_unit_pass():
        q = Q(35.0, "degC", "air_temp")
        q.assert_unit("degC")   # must not raise

    def test_assert_unit_fail():
        q = Q(35.0, "degC", "air_temp")
        _expect_unit_error(lambda: q.assert_unit("degF"), "Wrong unit should raise.")

    _run("valid Q construction",               test_valid_units)
    _run("unknown unit raises UnitError",      test_unknown_unit)
    _run("assert_unit passes correctly",       test_assert_unit_pass)
    _run("assert_unit fails on mismatch",      test_assert_unit_fail)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 2 — SAME-DIMENSION CONVERSIONS
# ──────────────────────────────────────────────────────────────────────────────

def section_conversions():
    print("\n[2] Same-Dimension Conversions")

    def test_kmh_to_ms():
        q   = Q(36.0, "km/h").to("m/s")
        assert abs(q.value - 10.0) < 1e-6, f"Expected 10.0 m/s, got {q.value}"

    def test_degf_to_degc():
        q = Q(212.0, "degF").to("degC")
        assert abs(q.value - 100.0) < 1e-4, f"Expected 100 °C, got {q.value}"

    def test_kw_to_mw():
        q = Q(500_000.0, "kW").to("MW")
        assert abs(q.value - 500.0) < 1e-6, f"Expected 500 MW, got {q.value}"

    def test_ka_to_a():
        q = Q(0.9, "kA").to("A")
        assert abs(q.value - 900.0) < 1e-6, f"Expected 900 A, got {q.value}"

    def test_incompatible_dims():
        q = Q(5.0, "m/s")
        _expect_unit_error(lambda: q.to("degC"), "velocity → temperature should raise.")

    _run("km/h → m/s",                   test_kmh_to_ms)
    _run("°F → °C",                      test_degf_to_degc)
    _run("kW → MW",                      test_kw_to_mw)
    _run("kA → A",                       test_ka_to_a)
    _run("incompatible dimensions raise", test_incompatible_dims)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 3 — CROSS-DIMENSION: AMPS ↔ MW
# ──────────────────────────────────────────────────────────────────────────────

def section_amps_to_mw():
    print("\n[3] Cross-Dimension: Amps ↔ MW")

    def test_amps_to_mw_correct():
        rating   = Q(900.0, "A", "static_rating")
        capacity = rating.to("MW", voltage_kv=345.0, pf=0.95)
        # Expected: sqrt(3)*345*900*0.95/1000 ≈ 511.5 MW
        assert abs(capacity.value - 511.46) < 1.0, f"Expected ~511.5 MW, got {capacity.value:.2f}"

    def test_amps_to_mw_missing_voltage():
        q = Q(900.0, "A")
        _expect_unit_error(lambda: q.to("MW"), "Missing voltage_kv should raise.")

    def test_mw_to_amps_roundtrip():
        original = Q(900.0, "A")
        mw       = original.to("MW", voltage_kv=345.0, pf=0.95)
        back     = mw.to("A",  voltage_kv=345.0, pf=0.95)
        assert abs(back.value - 900.0) < 0.01, f"Round-trip failed: {back.value:.4f} A"

    _run("900 A → MW (345 kV, pf=0.95)",  test_amps_to_mw_correct)
    _run("A → MW without voltage raises", test_amps_to_mw_missing_voltage)
    _run("A → MW → A round-trip",         test_mw_to_amps_roundtrip)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 4 — INTENTIONAL UNIT ERRORS (must all be caught)
# ──────────────────────────────────────────────────────────────────────────────

def section_intentional_errors():
    """
    These are representative bugs that *would* silently corrupt a pipeline.
    Every test here must raise UnitError — if it doesn't the module has a gap.
    """
    print("\n[4] Intentional Unit Errors (all must be caught)")

    # Error 1: passing kW where MW is expected
    def error_kw_passed_as_mw():
        load_in_kw = Q(510_000.0, "kW", "ercot_load")       # kW, not MW
        # Caller asserts it expects MW — should raise
        _expect_unit_error(
            lambda: load_in_kw.assert_unit("MW"),
            "kW passed where MW expected should raise."
        )

    # Error 2: wind speed in km/h used raw where m/s is required
    def error_kmh_used_as_ms():
        wind_kmh = Q(36.0, "km/h", "wind_speed")
        _expect_unit_error(
            lambda: expect_unit(wind_kmh, "m/s"),
            "km/h used as m/s should raise."
        )

    # Error 3: temperature in °F passed where °C is expected
    def error_degf_used_as_degc():
        temp_f = Q(95.0, "degF", "air_temp")      # 95 °F = 35 °C
        _expect_unit_error(
            lambda: expect_unit(temp_f, "degC"),
            "°F passed as °C should raise."
        )

    # Error 4: per-unit impedance mixed with actual ohm/km impedance
    def error_pu_mixed_with_ohm_per_km():
        pu_impedance   = Q(0.05, "pu",     "line_impedance_pu")
        ohm_impedance  = Q(0.07, "ohm/km", "line_resistance_ohm")
        _expect_unit_error(
            lambda: pu_impedance.assert_unit("ohm/km"),
            "per-unit vs ohm/km mix should raise."
        )
        _expect_unit_error(
            lambda: ohm_impedance.assert_unit("pu"),
            "ohm/km vs per-unit mix should raise."
        )

    # Error 5: ampacity value given in kA (0.9 kA) but pipeline expects A
    def error_ka_used_as_amps():
        rating_ka = Q(0.9, "kA", "dlr_rating")    # 0.9 kA = 900 A
        _expect_unit_error(
            lambda: expect_unit(rating_ka, "A"),
            "kA passed where A expected should raise."
        )

    # Error 6: solar radiation in kW/m² where W/m² is expected
    def error_kwm2_used_as_wm2():
        # kW/m² is not in the registry at all — catches typos / unofficial units
        _expect_unit_error(
            lambda: Q(1.0, "kW/m²", "solar_radiation"),
            "Unregistered unit kW/m² should raise."
        )

    # Error 7: value wildly outside physical range exposes implicit unit bug
    def error_range_check_catches_kw_as_mw():
        """
        A developer passes ercot_west_load_mw = 15_000_000 (i.e. MW stored as W).
        The range check [0, 30_000] MW catches this as a probable unit error.
        """
        row = {
            "air_temp":            35.0,
            "wind_speed":           8.0,
            "wind_direction":      270.0,
            "ercot_west_load_mw":  15_000_000.0,  # ← clearly W not MW
        }
        errors = validate_pipeline_row(row, strict=False)
        assert any("ercot_west_load_mw" in e for e in errors), \
            f"Range check did not flag the inflated MW value. Errors: {errors}"

    _run("kW passed where MW expected",            error_kw_passed_as_mw)
    _run("km/h used as m/s",                       error_kmh_used_as_ms)
    _run("°F passed as °C",                        error_degf_used_as_degc)
    _run("per-unit mixed with ohm/km",             error_pu_mixed_with_ohm_per_km)
    _run("kA used where A expected",               error_ka_used_as_amps)
    _run("unregistered unit (kW/m²) raises",       error_kwm2_used_as_wm2)
    _run("range check catches W stored as MW",     error_range_check_catches_kw_as_mw)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 5 — validate_pipeline_row
# ──────────────────────────────────────────────────────────────────────────────

def section_pipeline_row_validator():
    print("\n[5] Pipeline Row Validator")

    def test_valid_row():
        row = {
            "air_temp":          35.0,
            "wind_speed":         8.5,
            "wind_direction":   270.0,
            "solar_radiation":  850.0,
            "dlr_amps":         950.0,
            "dlr_capacity_mw":  540.0,
        }
        errors = validate_pipeline_row(row, strict=False)
        assert errors == [], f"Valid row raised errors: {errors}"

    def test_missing_required():
        row = {"wind_speed": 8.5, "wind_direction": 270.0}  # air_temp missing
        errors = validate_pipeline_row(row, strict=False)
        assert any("air_temp" in e for e in errors), "Missing air_temp not caught."

    def test_non_finite_value():
        row = {"air_temp": float("nan"), "wind_speed": 8.0, "wind_direction": 180.0}
        errors = validate_pipeline_row(row, strict=False)
        assert any("NON-FINITE" in e for e in errors), "NaN not caught."

    def test_out_of_range_temp():
        # 350 °C is outside [-20, 60] — flags possible K or °F mix-up
        row = {"air_temp": 350.0, "wind_speed": 5.0, "wind_direction": 90.0}
        errors = validate_pipeline_row(row, strict=False)
        assert any("air_temp" in e for e in errors), "Out-of-range temp not caught."

    def test_strict_raises():
        row = {"air_temp": 350.0, "wind_speed": 5.0, "wind_direction": 90.0}
        try:
            validate_pipeline_row(row, strict=True)
            raise AssertionError("strict=True should have raised UnitError")
        except UnitError:
            pass

    _run("valid row passes",              test_valid_row)
    _run("missing required column",       test_missing_required)
    _run("NaN flagged as non-finite",     test_non_finite_value)
    _run("out-of-range temp flagged",     test_out_of_range_temp)
    _run("strict=True raises on error",   test_strict_raises)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 6 — @check_units DECORATOR
# ──────────────────────────────────────────────────────────────────────────────

def section_decorator():
    print("\n[6] @check_units Decorator")

    @check_units(wind_speed="m/s", air_temp="degC")
    def compute_dummy_rating(wind_speed: Q, air_temp: Q) -> float:
        return wind_speed.value * 10 - air_temp.value

    def test_decorator_passes():
        result = compute_dummy_rating(
            wind_speed=Q(8.0,  "m/s"),
            air_temp  =Q(35.0, "degC"),
        )
        assert result == 45.0

    def test_decorator_wrong_wind_unit():
        _expect_unit_error(
            lambda: compute_dummy_rating(
                wind_speed=Q(28.8, "km/h"),   # ← wrong unit, not converted
                air_temp  =Q(35.0, "degC"),
            ),
            "Decorator should catch km/h where m/s expected."
        )

    def test_decorator_plain_float_raises():
        _expect_unit_error(
            lambda: compute_dummy_rating(
                wind_speed=8.0,                # ← plain float, no unit
                air_temp  =Q(35.0, "degC"),
            ),
            "Decorator should require Q objects, not plain floats."
        )

    _run("decorator passes with correct units",    test_decorator_passes)
    _run("decorator rejects km/h where m/s needed",test_decorator_wrong_wind_unit)
    _run("decorator rejects plain float (no unit)",test_decorator_plain_float_raises)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 7 — RANGE SANITY CHECKS (assert_range)
# ──────────────────────────────────────────────────────────────────────────────

def section_range_checks():
    print("\n[7] Range Sanity Checks")

    def test_dlr_amps_reasonable():
        Q(950.0, "A", "dlr_amps").assert_range(100, 4000)   # should pass

    def test_dlr_amps_suspiciously_low():
        # 9.5 A for a 345 kV line is obviously a unit error (likely kA not A)
        _expect_unit_error(
            lambda: Q(0.95, "A", "dlr_amps").assert_range(100, 4000),
            "0.95 A (likely 0.95 kA) should fail range check."
        )

    def test_solar_radiation_range():
        Q(850.0, "W/m²", "ghi").assert_range(0, 1400)       # fine

    def test_solar_radiation_excessive():
        # 8500 W/m² would indicate value was in W/cm² or some other unit
        _expect_unit_error(
            lambda: Q(8500.0, "W/m²", "ghi").assert_range(0, 1400),
            "8500 W/m² outside range should raise."
        )

    _run("DLR amps 950 A in range",            test_dlr_amps_reasonable)
    _run("DLR amps 0.95 A (kA bug) detected",  test_dlr_amps_suspiciously_low)
    _run("solar radiation 850 W/m² in range",  test_solar_radiation_range)
    _run("solar 8500 W/m² out of range",       test_solar_radiation_excessive)


# ──────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

def print_summary():
    total  = len(_results)
    passed = sum(1 for r in _results if r.passed)
    failed = total - passed
    print(f"\n{'═'*55}")
    print(f"  RESULTS:  {passed}/{total} passed  |  {failed} failed")
    print(f"{'═'*55}")
    if failed:
        print("\nFailed tests:")
        for r in _results:
            if not r.passed:
                print(f"  ✗  {r.name}")
                print(f"       {r.message}")
    else:
        print("  All unit checks are working correctly.")


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 55)
    print("  DLR Pipeline — Unit Validation Test Suite")
    print("═" * 55)

    section_basic_construction()
    section_conversions()
    section_amps_to_mw()
    section_intentional_errors()
    section_pipeline_row_validator()
    section_decorator()
    section_range_checks()

    print_summary()


# ──────────────────────────────────────────────────────────────────────────────
# PYTEST SECTION — Plan 04-02 Task 2 (C9): PIPELINE_SCHEMA v2 additive extension
# ──────────────────────────────────────────────────────────────────────────────
# Everything above this line is the pre-existing standalone harness (run only
# via `if __name__ == "__main__"` — it is never collected by pytest, since its
# test functions are nested closures inside `section_*` functions rather than
# top-level `test_*` names; confirmed live, see the 2026-08-31
# ACKNOWLEDGEMENTS.md entry documenting this gap). The tests below are real
# top-level `test_*` functions so pytest actually collects and runs them,
# following backend/tests/corridor_discretization_test.py's convention
# (module-level imports, plain asserts, no classes).

import units_def as _units_def_module  # noqa: E402  (see note above on section placement)

# Frozen snapshot of every pre-Phase-4 (v1) PIPELINE_SCHEMA entry, duplicated
# here rather than derived from the module at import time -- a test that
# reads the value it is checking proves nothing.
_V1_SCHEMA_SNAPSHOT = {
    "air_temp": {"unit": "degC", "range": (-20.0, 60.0), "required": True},
    "wind_speed": {"unit": "m/s", "range": (0.0, 50.0), "required": True},
    "wind_direction": {"unit": "deg", "range": (0.0, 360.0), "required": True},
    "wind_perp_ms": {"unit": "m/s", "range": (0.0, 50.0), "required": False},
    "solar_radiation": {"unit": "W/m²", "range": (0.0, 1400.0), "required": False},
    "relative_humidity": {"unit": "%", "range": (0.0, 100.0), "required": False},
    "dlr_amps": {"unit": "A", "range": (100.0, 4000.0), "required": False},
    "dlr_capacity_mw": {"unit": "MW", "range": (50.0, 2500.0), "required": False},
    "static_capacity_mw": {"unit": "MW", "range": (50.0, 2500.0), "required": False},
    "ercot_west_load_mw": {"unit": "MW", "range": (0.0, 30_000.0), "required": False},
}


def test_schema_version_bumped_and_v1_columns_are_byte_identical():
    assert _units_def_module.PIPELINE_SCHEMA_VERSION == 2
    for name, spec in _V1_SCHEMA_SNAPSHOT.items():
        assert _units_def_module.PIPELINE_SCHEMA[name] == spec


def test_v2_columns_are_all_optional():
    v2_keys = set(_units_def_module.PIPELINE_SCHEMA) - set(_V1_SCHEMA_SNAPSHOT)
    assert v2_keys == {
        "forecast_horizon_min", "forecast_amps", "forecast_ci_lower_amps",
        "forecast_ci_upper_amps", "anomaly_score",
    }
    for key in v2_keys:
        assert _units_def_module.PIPELINE_SCHEMA[key]["required"] is False


def test_pre_phase4_row_still_validates():
    row = {
        "air_temp": 25.0,
        "wind_speed": 5.0,
        "wind_direction": 180.0,
    }
    errors = validate_pipeline_row(row, strict=False)
    assert errors == []


def test_row_with_valid_forecast_columns_validates():
    row = {
        "air_temp": 25.0,
        "wind_speed": 5.0,
        "wind_direction": 180.0,
        "forecast_horizon_min": 60.0,
        "forecast_amps": 1200.0,
        "forecast_ci_lower_amps": 1100.0,
        "forecast_ci_upper_amps": 1300.0,
        "anomaly_score": 0.5,
    }
    errors = validate_pipeline_row(row, strict=False)
    assert errors == []


def test_forecast_amps_out_of_range_produces_one_error_naming_column():
    row = {
        "air_temp": 25.0,
        "wind_speed": 5.0,
        "wind_direction": 180.0,
        "forecast_amps": 50.0,  # below the (100.0, 4000.0) floor
    }
    errors = validate_pipeline_row(row, strict=False)
    assert len(errors) == 1
    assert "forecast_amps" in errors[0]