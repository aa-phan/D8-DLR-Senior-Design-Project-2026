"""
Thermal Model / IEEE 738 (C5)
==================================================
Pure physics core: steady-state IEEE 738 conductor ampacity from weather
inputs and conductor properties. No ingestion, no orchestration, no
`__main__` side effects — importable and callable without a SYNOPTIC_TOKEN
env var or any file I/O.

Every other component (C7, C8, C9) that needs an IEEE 738 rating should
import and call this module rather than reimplementing the formula.
"""

import math
from typing import Union

import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# PERPENDICULAR WIND COMPONENT
# ──────────────────────────────────────────────────────────────────────────────

def perpendicular_wind(
    wind_speed_ms: Union[float, np.ndarray],
    wind_dir_deg: Union[float, np.ndarray],
    line_azimuth_deg: float,
) -> np.ndarray:
    """
    Compute the wind speed component perpendicular to the transmission line.

    IEEE 738 uses effective cooling wind; the perpendicular component is
    what drives forced convection.  For angles < 20° use minimum value
    to avoid instability in natural convection regime.

    Args:
        wind_speed_ms:   Measured wind speed (m/s)
        wind_dir_deg:    Meteorological wind direction (degrees from North,
                         direction wind is coming FROM)
        line_azimuth_deg: Compass bearing of the transmission line (0–360°)

    Returns:
        Effective perpendicular wind component (m/s), shape matching inputs
    """
    ws  = np.asarray(wind_speed_ms, dtype=float)
    wd  = np.asarray(wind_dir_deg,  dtype=float)
    # Wind flow direction = opposite of met convention
    flow_dir = (wd + 180) % 360
    # Angle between wind flow and line
    delta = np.abs(flow_dir - line_azimuth_deg) % 180
    # Convert angles > 90° to acute angle
    delta = np.where(delta > 90, 180 - delta, delta)
    # Perpendicular component
    perp = ws * np.sin(np.radians(delta))
    # IEEE 738: below ~20° treat as low-wind / natural convection dominates
    perp = np.where(delta < 20, ws * np.sin(np.radians(20)), perp)
    return perp


# ──────────────────────────────────────────────────────────────────────────────
# IEEE 738 THERMAL MODEL
# ──────────────────────────────────────────────────────────────────────────────

class ConductorConfig:
    """
    Physical properties of the ACSR conductor.
    Defaults match a typical 795 kcmil Drake ACSR used on ERCOT 345 kV lines.
    """
    def __init__(
        self,
        diameter_m:    float = 0.02814,   # outer diameter (m)
        resistance_ac: float = 0.0726,    # AC resistance at 25°C (Ω/km)
        resist_temp_coef: float = 0.00404, # per °C (aluminum)
        emissivity:    float = 0.8,        # conductor surface emissivity
        absorptivity:  float = 0.8,        # solar absorptivity
        max_temp_c:    float = 75.0,       # maximum allowable conductor temp (°C)
        line_azimuth:  float = 90.0,       # compass bearing of line (°)
        elevation_m:   float = 300.0,      # average elevation for air density
    ):
        self.D    = diameter_m
        self.R25  = resistance_ac / 1000   # Ω/m
        self.alpha_r = resist_temp_coef
        self.eps  = emissivity
        self.alpha_s = absorptivity
        self.T_max = max_temp_c
        self.line_az = line_azimuth
        self.elev = elevation_m


def _air_density(elevation_m: float) -> float:
    """Approximate air density (kg/m³) at elevation."""
    return 1.225 * math.exp(-elevation_m / 8435)


def _dynamic_viscosity(T_film_c: float) -> float:
    """Air dynamic viscosity (Pa·s) at film temperature."""
    T_k = T_film_c + 273.15
    return 1.458e-6 * T_k**1.5 / (T_k + 110.4)


def _thermal_conductivity(T_film_c: float) -> float:
    """Air thermal conductivity (W/m·K) at film temperature."""
    return 2.42e-2 + 7.2e-5 * T_film_c


def ieee738_ampacity(
    T_amb_c: Union[float, np.ndarray],
    wind_perp_ms: Union[float, np.ndarray],
    ghi_wm2: Union[float, np.ndarray],
    conductor: ConductorConfig,
    solar_altitude_deg: float = 45.0,
) -> np.ndarray:
    """
    IEEE 738 steady-state ampacity (A) given weather conditions.

    Returns current rating in Amperes for each observation.

    Note on `solar_altitude_deg`: this function computes the solar term
    using `sin(solar_altitude_deg)` as a stand-in for the standard's
    `sin(theta)`, where theta is the *angle of incidence* of solar rays on
    the conductor. IEEE Std 738's real geometry accounts for both solar
    position AND the line's azimuth relative to the sun; this function does
    not independently compute that angle — it trusts the caller to have
    already supplied the effective incidence angle here. Passing the raw
    solar altitude (rather than the true incidence angle) will overstate or
    understate solar gain depending on line orientation. This is a known
    modeling simplification (see docs/data-science/specs/C5-thermal-model.md),
    not something fixed in this pass.
    """
    T_a  = np.asarray(T_amb_c,     dtype=float)
    Vw   = np.asarray(wind_perp_ms, dtype=float)
    Q_s  = np.asarray(ghi_wm2,     dtype=float)

    T_c  = conductor.T_max
    T_f  = (T_c + T_a) / 2          # film temperature

    # Air properties at film temp (vectorized approximation)
    rho_f = _air_density(conductor.elev)
    mu_f  = 1.458e-6 * (T_f + 273.15)**1.5 / (T_f + 110.4 + 273.15)
    k_f   = 2.42e-2 + 7.2e-5 * T_f

    # Reynolds number
    N_Re = conductor.D * Vw * rho_f / mu_f

    # Forced convection (IEEE Std 738-2023 eq. 9 / eq. 10).
    #
    # NOTE (bug fix, C5 Part 2): the previous version of this formula had an
    # erroneous extra `* np.pi` factor in both branches. Neither published
    # equation (qc1 = Kangle*[1.01 + 1.35*NRe^0.52]*kf*(Ts-Ta), qc2 =
    # Kangle*0.754*NRe^0.6*kf*(Ts-Ta)) contains a pi term. `perpendicular_wind()`
    # already applies the Kangle directionality adjustment upstream (that's
    # what wind_perp_ms represents), so Kangle correctly does not reappear
    # here — only the extraneous pi factor was wrong, and has been removed.
    Q_cf = np.where(
        N_Re < 1000,
        k_f * (1.01 + 1.347 * N_Re**0.52) * (T_c - T_a),
        k_f * 0.754 * N_Re**0.6 * (T_c - T_a)
    )

    # Natural convection (when wind is very low, use max of forced/natural)
    Q_cn = 3.645 * rho_f**0.5 * conductor.D**0.75 * (T_c - T_a)**1.25

    Q_conv = np.maximum(Q_cf, Q_cn)

    # Radiated heat loss (Stefan–Boltzmann linearized)
    T_c_k = T_c + 273.15
    T_a_k = T_a + 273.15
    Q_rad = 17.8 * conductor.D * conductor.eps * (
        ((T_c_k / 100)**4) - ((T_a_k / 100)**4)
    )

    # Solar heat gain — use a simplified angle factor
    sin_alt = math.sin(math.radians(solar_altitude_deg))
    Q_solar = conductor.alpha_s * Q_s * conductor.D * sin_alt

    # Resistance at conductor temperature
    R_Tc = conductor.R25 * (1 + conductor.alpha_r * (T_c - 25))

    # Solve for I:  I² * R_Tc = Q_conv + Q_rad - Q_solar
    heat_balance = Q_conv + Q_rad - Q_solar
    heat_balance = np.maximum(heat_balance, 0)   # cannot be negative
    I = np.sqrt(heat_balance / R_Tc)
    return I
