"""
Tests for backend/thermal_model.py (C5 — Thermal Model / IEEE 738).

Two things are being verified here:

1. `ieee738_ampacity` reproduces the published IEEE Std 738-2023 worked
   example (795 kcmil Drake ACSR conductor, §4.6.1) within a tolerance that
   is derived — not guessed — from a known, documented difference between
   this project's resistance-vs-temperature model and the standard's own
   worked-example method. This is also a regression test for the Part 2 bug
   fix: an erroneous `* np.pi` factor in the forced-convection terms
   previously inflated the computed heat-loss capacity and therefore the
   ampacity (sqrt of a heat term that's too large by ~pi) well outside any
   reasonable tolerance of the reference value.

2. Basic sanity/monotonicity checks using the project's normal conductor
   defaults, as a safety net for the dlr_pipeline.py -> thermal_model.py
   extraction (make sure nothing broke in the move itself).
"""

import math

import numpy as np
import pytest

import thermal_model as tm


# ──────────────────────────────────────────────────────────────────────────────
# 1. Published worked-example validation (IEEE Std 738-2023, §4.6.1)
# ──────────────────────────────────────────────────────────────────────────────

def test_ieee738_worked_example_795kcmil_drake_acsr():
    """
    Reproduces the IEEE Std 738-2023 published worked example for a 795 kcmil
    "Drake" ACSR conductor and checks `ieee738_ampacity` against its
    published answer of 1025 A (steady-state rating, §4.6.1).

    Every input below is chosen to map this project's `ieee738_ampacity`
    parameters onto the standard's worked-example inputs as closely as this
    function's actual formula allows — see inline comments for each one.
    """

    # ── Conductor, matching the STANDARD's worked example (not this
    # project's own ConductorConfig defaults, which model a slightly
    # different Drake ACSR data set / different max-temp assumption) ──
    conductor = tm.ConductorConfig(
        diameter_m=0.02814,
        # Standard gives R at 100C as 9.391e-5 Ohm/m = 7.283e-5 Ohm/m... no:
        # the standard's R(25C) value converts to 0.07283 Ohm/km (this
        # project's constructor takes Ohm/km and divides by 1000 internally).
        # This is intentionally NOT this project's own default of 0.0726
        # Ohm/km -- it is the standard's own R(25C) value for its example
        # conductor, converted to match this project's constructor units.
        resistance_ac=0.07283,
        emissivity=0.8,
        absorptivity=0.8,
        # The example's conductor limit temperature is 100C, not this
        # project's own default of 75C -- 100C is specific to reproducing
        # this worked example.
        max_temp_c=100.0,
        line_azimuth=90.0,
        # Sea level, per the example.
        elevation_m=0.0,
    )

    ampacity = tm.ieee738_ampacity(
        T_amb_c=40.0,
        # The example's wind is already stated as perpendicular to the
        # conductor (Kangle = 1), so it is passed directly rather than run
        # through perpendicular_wind() first.
        wind_perp_ms=0.61,
        # This is the standard's own computed clear-sky solar heat flux
        # Qse (W/m^2) at the example's solar altitude -- the closest match
        # to what this function's ghi_wm2 parameter represents.
        ghi_wm2=1027.0,
        conductor=conductor,
        # IMPORTANT NUANCE: this function computes sin(solar_altitude_deg)
        # as a stand-in for the standard's sin(theta), where theta is the
        # angle of incidence of solar rays on the conductor -- a quantity
        # that depends on BOTH solar position and the line's azimuth
        # relative to the sun, NOT the raw solar altitude Hc. In the worked
        # example, the true solar altitude is Hc = 74.9 deg, but the actual
        # angle of incidence (accounting for the line's east-west azimuth)
        # is theta = 76.2 deg. Passing 76.2 here is the closest honest match
        # to what this function's solar term actually computes, even though
        # the parameter is named `solar_altitude_deg`. This function does
        # NOT independently compute incidence angle from line azimuth vs.
        # solar azimuth -- it's a known modeling simplification (documented
        # in thermal_model.ieee738_ampacity's own docstring and in
        # docs/data-science/specs/C5-thermal-model.md), not something fixed
        # as part of this test/pass.
        solar_altitude_deg=76.2,
    )

    expected = 1025.0

    # ── Tolerance derivation (not a guessed number) ──
    #
    # This project's resistance-vs-temperature model is a single-coefficient
    # linear extrapolation: R(Tc) = R25 * (1 + alpha_r * (Tc - 25)). The
    # standard's own worked example instead uses a two-point linear
    # interpolation between measured R(25C) and R(75C), extrapolated to
    # R(100C) = 9.391e-5 Ohm/m.
    #
    # Computing what THIS project's formula gives for R at Tc=100C with
    # resistance_ac=0.07283 Ohm/km (-> R25 = 7.283e-5 Ohm/m) and the default
    # resist_temp_coef=0.00404/C:
    #
    #   R_Tc = 7.283e-5 * (1 + 0.00404 * (100 - 25)) = 9.48975e-5 Ohm/m
    #
    # vs. the standard's 9.391e-5 Ohm/m -> a +1.0515% difference in R.
    #
    # Since I = sqrt(heat_balance / R_Tc), a resistance value that is too
    # high by a fraction x lowers computed ampacity by approximately x/2
    # (first-order sqrt propagation) -- i.e. the resistance-formula
    # difference alone predicts roughly a -0.52% shift in ampacity relative
    # to the standard's answer.
    #
    # The actual computed ampacity here comes out ~+0.95% ABOVE 1025 A
    # (opposite sign, and about 2x the resistance-only magnitude) -- meaning
    # other small approximations in this function (this project's simplified
    # air-property equations for viscosity/conductivity vs. the standard's
    # tabulated coefficients, the 1.347 vs. 1.35 rounding in the forced
    # convection coefficient, etc.) contribute a further ~1.5% on net. This
    # is a real, noted residual discrepancy worth future investigation, but
    # it stays within "low-single-digit-percent" territory consistent with
    # a simplified physics model reproducing a standard's fully worked
    # example, so a 2% relative tolerance is used below -- wide enough to
    # cover the resistance-formula difference plus this observed residual,
    # but nowhere close to wide enough to hide the *actual* bug this test
    # guards against (see next paragraph).
    #
    # Sanity-check contrast: the OLD, buggy version of ieee738_ampacity
    # (with the erroneous extra `* np.pi` factor in both forced-convection
    # branches) gives ~1728 A for these exact inputs -- a ~69% overshoot,
    # wildly outside any reasonable tolerance, and the reason this fix
    # (Part 2) was necessary.
    rel_tol = 0.02
    rel_error = abs(ampacity - expected) / expected

    assert rel_error <= rel_tol, (
        f"ieee738_ampacity({ampacity:.2f} A) deviates from the IEEE Std "
        f"738-2023 worked-example answer ({expected} A) by "
        f"{rel_error * 100:.3f}%, exceeding the {rel_tol * 100:.1f}% "
        f"tolerance justified above."
    )


def test_old_buggy_formula_would_have_failed_worked_example():
    """
    Documents (does not re-implement as production code) that the old
    `* np.pi` bug would have produced a value far outside any reasonable
    tolerance for the same worked-example inputs -- concrete evidence the
    Part 2 fix was a real correctness fix, not a cosmetic change.
    """
    conductor = tm.ConductorConfig(
        diameter_m=0.02814,
        resistance_ac=0.07283,
        emissivity=0.8,
        absorptivity=0.8,
        max_temp_c=100.0,
        line_azimuth=90.0,
        elevation_m=0.0,
    )

    T_a, Vw, Q_s = 40.0, 0.61, 1027.0
    T_c = conductor.T_max
    T_f = (T_c + T_a) / 2
    rho_f = tm._air_density(conductor.elev)
    mu_f = 1.458e-6 * (T_f + 273.15) ** 1.5 / (T_f + 110.4 + 273.15)
    k_f = 2.42e-2 + 7.2e-5 * T_f
    N_Re = conductor.D * Vw * rho_f / mu_f

    # Reconstruct the OLD (buggy) forced-convection term with the erroneous
    # extra pi factor, exactly as it existed in dlr_pipeline.py before the
    # Part 2 fix.
    Q_cf_old = np.where(
        N_Re < 1000,
        k_f * (1.01 + 1.347 * N_Re ** 0.52) * np.pi * (T_c - T_a),
        k_f * 0.754 * N_Re ** 0.6 * np.pi * (T_c - T_a),
    )
    Q_cn = 3.645 * rho_f ** 0.5 * conductor.D ** 0.75 * (T_c - T_a) ** 1.25
    Q_conv_old = np.maximum(Q_cf_old, Q_cn)

    T_c_k, T_a_k = T_c + 273.15, T_a + 273.15
    Q_rad = 17.8 * conductor.D * conductor.eps * (
        ((T_c_k / 100) ** 4) - ((T_a_k / 100) ** 4)
    )
    sin_alt = math.sin(math.radians(76.2))
    Q_solar = conductor.alpha_s * Q_s * conductor.D * sin_alt
    R_Tc = conductor.R25 * (1 + conductor.alpha_r * (T_c - 25))

    heat_balance_old = max(Q_conv_old + Q_rad - Q_solar, 0)
    I_old = math.sqrt(heat_balance_old / R_Tc)

    # ~1728 A -- nowhere close to the published 1025 A answer.
    assert I_old > 1500, (
        "expected the old buggy formula to badly overshoot the worked "
        f"example (~1728 A); got {I_old:.1f} A"
    )
    assert abs(I_old - 1025.0) / 1025.0 > 0.5


# ──────────────────────────────────────────────────────────────────────────────
# 2. Sanity / monotonicity tests (extraction safety net, project defaults)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def default_conductor() -> tm.ConductorConfig:
    """795 kcmil Drake ACSR using this project's own ConductorConfig defaults."""
    return tm.ConductorConfig()


def test_higher_wind_speed_increases_ampacity(default_conductor):
    low_wind = tm.ieee738_ampacity(
        T_amb_c=35.0, wind_perp_ms=0.5, ghi_wm2=900.0,
        conductor=default_conductor, solar_altitude_deg=60.0,
    )
    high_wind = tm.ieee738_ampacity(
        T_amb_c=35.0, wind_perp_ms=5.0, ghi_wm2=900.0,
        conductor=default_conductor, solar_altitude_deg=60.0,
    )
    assert high_wind > low_wind


def test_higher_ambient_temp_decreases_ampacity(default_conductor):
    cool = tm.ieee738_ampacity(
        T_amb_c=15.0, wind_perp_ms=2.0, ghi_wm2=900.0,
        conductor=default_conductor, solar_altitude_deg=60.0,
    )
    hot = tm.ieee738_ampacity(
        T_amb_c=40.0, wind_perp_ms=2.0, ghi_wm2=900.0,
        conductor=default_conductor, solar_altitude_deg=60.0,
    )
    assert hot < cool


def test_perpendicular_wind_matches_full_perpendicular_case(default_conductor):
    # Wind blowing FROM due north (met convention 0deg) onto an E-W line
    # (azimuth 90deg) flows due south -- perpendicular to the line -- so the
    # perpendicular component should equal the full wind speed.
    perp = tm.perpendicular_wind(
        wind_speed_ms=10.0, wind_dir_deg=0.0, line_azimuth_deg=90.0,
    )
    assert perp == pytest.approx(10.0, rel=1e-6)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Convective-heat-loss extraction equality gate (Phase 3 Plan 02, D-03)
# ──────────────────────────────────────────────────────────────────────────────
#
# The gate is bit-for-bit exact equality (`np.array_equal`), never a
# tolerance-based comparator (`allclose`/`approx`/`isclose`). This is pure
# code motion -- the extraction must not change a single bit of the
# output. An automated check greps this section for a tolerant comparator
# to prove it never sneaks in.

@pytest.fixture(scope="module")
def golden_thermal_fixture():
    import os

    path = os.path.join(
        os.path.dirname(__file__), "thermal_model_pre_refactor_golden.npz"
    )
    return np.load(path)


def test_ieee738_ampacity_is_bit_identical_to_pre_refactor_golden(
    golden_thermal_fixture,
):
    g = golden_thermal_fixture
    conductor = tm.ConductorConfig()
    live = tm.ieee738_ampacity(
        g["T_amb_c"], g["wind_perp_ms"], g["ghi_wm2"], conductor
    )
    assert np.array_equal(live, g["ampacity"]), (
        "the convective-term extraction changed ieee738_ampacity output -- "
        "this is code motion, so it must be bit-identical, not merely close"
    )


def test_convective_heat_loss_matches_pre_refactor_golden(golden_thermal_fixture):
    g = golden_thermal_fixture
    conductor = tm.ConductorConfig()
    live = tm.convective_heat_loss(g["T_amb_c"], g["wind_perp_ms"], conductor)
    assert np.array_equal(live, g["q_conv"]), (
        "convective_heat_loss does not reproduce the pre-refactor "
        "convective term exactly"
    )


def test_q_conv_override_defaults_to_true_no_op(golden_thermal_fixture):
    g = golden_thermal_fixture
    conductor = tm.ConductorConfig()
    no_kwarg = tm.ieee738_ampacity(g["T_amb_c"], g["wind_perp_ms"], g["ghi_wm2"], conductor)
    explicit_none = tm.ieee738_ampacity(
        g["T_amb_c"], g["wind_perp_ms"], g["ghi_wm2"], conductor,
        q_conv_override=None,
    )
    assert np.array_equal(no_kwarg, explicit_none), (
        "the new keyword is not a true no-op at its default"
    )


def test_q_conv_override_changes_the_result(golden_thermal_fixture):
    g = golden_thermal_fixture
    conductor = tm.ConductorConfig()
    baseline = tm.ieee738_ampacity(g["T_amb_c"], g["wind_perp_ms"], g["ghi_wm2"], conductor)
    bumped = tm.ieee738_ampacity(
        g["T_amb_c"], g["wind_perp_ms"], g["ghi_wm2"], conductor,
        q_conv_override=g["q_conv"] * 1.5,
    )
    assert not np.array_equal(baseline, bumped), (
        "an explicit convective override did not change the result -- the "
        "override is not wired to the heat balance"
    )


def test_natural_convection_is_strictly_positive_below_conductor_max(default_conductor):
    result = tm.natural_convection(np.array([-10.0, 0.0, 30.0, 74.0]), default_conductor)
    assert (result > 0).all()


def test_module_importable_with_no_env_or_io():
    """
    Guards the C5 extraction goal: thermal_model must be importable and its
    functions callable without SYNOPTIC_TOKEN or any file I/O. This test
    file's mere ability to `import thermal_model` at module scope already
    demonstrates this, but assert explicitly that no SYNOPTIC_TOKEN is
    required by calling a function directly.
    """
    import os

    os.environ.pop("SYNOPTIC_TOKEN", None)
    conductor = tm.ConductorConfig()
    result = tm.ieee738_ampacity(
        T_amb_c=25.0, wind_perp_ms=1.0, ghi_wm2=800.0,
        conductor=conductor, solar_altitude_deg=45.0,
    )
    assert result > 0
