"""
Dynamic Line Rating Pipeline
==================================================
Uses the Synoptic Data API to fetch
5-minute weather observations and compute IEEE 738 conductor ratings.

Requirements:
    pip install requests pandas numpy scipy matplotlib rich

Setup:
    1. Register for a free API token at https://synopticdata.com/
    2. Set env var:  export SYNOPTIC_TOKEN=your_token_here
       (or pass token= directly to each function)
"""

import os
import math
import json
import logging
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Union

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# 0.  CONFIG
# ──────────────────────────────────────────────────────────────────────────────

SYNOPTIC_BASE = "https://api.synopticdata.com/v2"

# West Texas Mesonet network ID in Synoptic — WTM stations carry network "wtm"
WTM_NETWORK = "wtm"

# Variables needed for DLR (Synoptic variable names)
DLR_VARS = [
    "air_temp",           # °C  — ambient temperature
    "wind_speed",         # m/s — average wind speed
    "wind_direction",     # °   — meteorological convention (where wind is FROM)
    "wind_gust",          # m/s — useful for conservative rating
    "solar_radiation",    # W/m² — global horizontal irradiance
    "relative_humidity",  # %
]

# ──────────────────────────────────────────────────────────────────────────────
# 1.  SYNOPTIC API HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _token() -> str:
    tok = os.getenv("SYNOPTIC_TOKEN", "")
    if not tok:
        raise EnvironmentError(
            "Set SYNOPTIC_TOKEN env var. "
            "Free research tokens: https://synopticdata.com/"
        )
    return tok


def get_wtm_stations(bbox: Optional[tuple] = None) -> pd.DataFrame:
    """
    Retrieve metadata for all WTM stations.

    Args:
        bbox: Optional (lat_min, lon_min, lat_max, lon_max) bounding box.
              Defaults to West Texas region.

    Returns:
        DataFrame with columns: stid, name, lat, lon, elevation_m, county, state
    """
    bbox = bbox or (28.5, -106.5, 36.5, -99.0)  # West Texas default
    params = {
        "token":   _token(),
        "network": WTM_NETWORK,
        "bbox":    f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}",
        "output":  "json",
    }
    log.info("Fetching WTM station metadata …")
    r = requests.get(f"{SYNOPTIC_BASE}/stations/metadata", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    rows = []
    for s in data.get("STATION", []):
        rows.append({
            "stid":        s["STID"],
            "name":        s["NAME"],
            "lat":         float(s["LATITUDE"]),
            "lon":         float(s["LONGITUDE"]),
            "elevation_m": float(s.get("ELEVATION", 0)) * 0.3048,  # ft→m
            "county":      s.get("COUNTY", ""),
            "state":       s.get("STATE", ""),
        })
    df = pd.DataFrame(rows)
    log.info(f"  Found {len(df)} WTM stations")
    return df


def fetch_timeseries(
    stids: list[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    Fetch 5-minute observations for given stations and time window.

    Args:
        stids: List of station IDs (e.g. ['LBBT2', 'MRST2'])
        start: ISO-8601 string, e.g. '2024-07-01T00:00:00Z'
        end:   ISO-8601 string, e.g. '2024-07-31T23:55:00Z'

    Returns:
        Long-form DataFrame indexed by (stid, datetime_utc)
    """
    params = {
        "token":    _token(),
        "stid":     ",".join(stids),
        "vars":     ",".join(DLR_VARS),
        "start":    start.replace("-", "").replace(":", "").replace("T", "")[:12],
        "end":      end.replace("-", "").replace(":", "").replace("T", "")[:12],
        "obtimezone": "UTC",
        "units":    "metric",
        "output":   "json",
        "showemptystations": 1,
        "showemptyvars": 1,
        "qc": "off"
    }
    log.info(f"Fetching timeseries for {len(stids)} stations ({start} → {end}) …")
    r = requests.get(f"{SYNOPTIC_BASE}/stations/timeseries", params=params, timeout=120)
    r.raise_for_status()
    data = r.json()

    print("SUMMARY:", data.get("SUMMARY"))
    print("Returned stations:", len(data.get("STATION", [])))

    for station in data.get("STATION", []):
        print("STID:", station.get("STID"))
        print("OBS keys:", list(station.get("OBSERVATIONS", {}).keys()))
        
    frames = []
    for station in data.get("STATION", []):
        stid = station["STID"]
        obs  = station.get("OBSERVATIONS", {})
        times = pd.to_datetime(obs.get("date_time", []), utc=True)
        row = {"stid": stid, "datetime_utc": times}
        for var in DLR_VARS:
            key = f"{var}_set_1"
            row[var] = obs.get(key, [None] * len(times))
        frames.append(pd.DataFrame(row))

    if not frames:
        log.warning("No data returned — check station IDs and date range.")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = df.set_index(["stid", "datetime_utc"]).sort_index()
    log.info(f"  Retrieved {len(df):,} observation rows")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# 2.  PERPENDICULAR WIND COMPONENT
# ──────────────────────────────────────────────────────────────────────────────

def perpendicular_wind(
    wind_speed_ms: Union[float,np.ndarray],
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
# 3.  IEEE 738 THERMAL MODEL
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

    # Forced convection (IEEE 738 eq. 3a / 3b)
    Q_cf = np.where(
        N_Re < 1000,
        k_f * (1.01 + 1.347 * N_Re**0.52) * np.pi * (T_c - T_a),
        k_f * 0.754 * N_Re**0.6 * np.pi * (T_c - T_a)
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


# ──────────────────────────────────────────────────────────────────────────────
# 4.  PIPELINE ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    stids:          list[str],
    start:          str,
    end:            str,
    conductor:      ConductorConfig,
    static_rating:  float = 900.0,    # A — conventional static rating for comparison
    solar_alt_deg:  float = 45.0,
) -> pd.DataFrame:
    """
    Full pipeline: fetch WTM data → compute perpendicular wind → IEEE 738 DLR.

    Args:
        stids:          List of WTM station IDs
        start / end:    ISO-8601 UTC strings
        conductor:      ConductorConfig instance
        static_rating:  Conventional static rating in Amps (for headroom calc)
        solar_alt_deg:  Representative solar altitude for the analysis period

    Returns:
        DataFrame with DLR results per station per timestamp
    """
    # Step 1 — Fetch observations
    obs = fetch_timeseries(stids, start, end)
    if obs.empty:
        return obs

    obs = obs.reset_index()
    
    profile_missing_data(obs)
    
    # Step 2 — Drop rows with missing critical variables
    obs = obs.dropna(subset=["air_temp", "wind_speed", "wind_direction"])
    obs["solar_radiation"] = obs["solar_radiation"].fillna(1000)

    # Step 3 — Perpendicular wind
    obs["wind_perp_ms"] = perpendicular_wind(
        obs["wind_speed"].values,
        obs["wind_direction"].values,
        conductor.line_az,
    )

    # Step 4 — IEEE 738 dynamic rating
    obs["dlr_amps"] = ieee738_ampacity(
        T_amb_c      = obs["air_temp"].values,
        wind_perp_ms = obs["wind_perp_ms"].values,
        ghi_wm2      = obs["solar_radiation"].values,
        conductor    = conductor,
        solar_altitude_deg = solar_alt_deg,
    )

    # Step 5 — DLR headroom vs static rating
    obs["dlr_headroom_pct"] = (obs["dlr_amps"] - static_rating) / static_rating * 100
    obs["dlr_uplift_flag"]  = obs["dlr_amps"] > static_rating

    log.info(
        f"Pipeline complete. "
        f"Median DLR = {obs['dlr_amps'].median():.0f} A | "
        f"% time DLR > static = {obs['dlr_uplift_flag'].mean()*100:.1f}%"
    )
    return obs

def profile_missing_data(df: pd.DataFrame):
    """Analyzes and prints the percentage of missing values per station."""
    log.info("--- Missing Data Profile ---")
    
    # Check if the dataframe is completely empty first
    if df.empty:
        log.warning("Dataframe is empty. Cannot profile missing data.")
        return

    # Calculate the percentage of missing data for each variable, grouped by station
    missing_pct = df.groupby("stid").apply(lambda x: x.isna().mean() * 100)
    
    # Filter to only show our critical DLR variables
    cols_to_check = [c for c in DLR_VARS if c in missing_pct.columns]
    
    print("\nPercentage of missing data per station:")
    print(missing_pct[cols_to_check].round(1).to_string())
    
    # Identify completely dead sensors (100% missing)
    for col in cols_to_check:
        dead_stations = missing_pct[missing_pct[col] == 100].index.tolist()
        if dead_stations:
            log.warning(f"Stations completely missing '{col}': {', '.join(dead_stations)}")
            
    print("----------------------------\n")

# ──────────────────────────────────────────────────────────────────────────────
# 5.  VISUALIZATION
# ──────────────────────────────────────────────────────────────────────────────

def plot_dlr_summary(df: pd.DataFrame, static_rating: float = 900.0, output_dir: str=".", file_prefix: str="dlr"):
    """
    4-panel summary plot:
      1. DLR time series vs static rating
      2. Wind speed & perpendicular component
      3. Ambient temperature
      4. DLR headroom distribution (histogram)
    """
    stations = df["stid"].unique()

    for stid in stations:
        sub = df[df["stid"] == stid].copy()
        sub = sub.set_index("datetime_utc")

        fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=False)
        fig.suptitle(
            f"DLR Analysis — WTM Station: {stid}\n"
            f"IEEE 738 | Conductor max {sub['dlr_amps'].max():.0f} A",
            fontsize=13, fontweight="bold",
        )

        # Panel 1 — DLR vs Static
        ax1 = axes[0]
        ax1.plot(sub.index, sub["dlr_amps"], lw=0.7, color="steelblue", label="DLR (IEEE 738)")
        ax1.axhline(static_rating, color="red", ls="--", lw=1.5, label=f"Static Rating ({static_rating:.0f} A)")
        ax1.fill_between(sub.index, static_rating, sub["dlr_amps"],
                         where=(sub["dlr_amps"] > static_rating),
                         alpha=0.2, color="green", label="Uplift headroom")
        ax1.set_ylabel("Ampacity (A)")
        ax1.legend(fontsize=8, loc="upper right")
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax1.grid(alpha=0.3)

        # Panel 2 — Wind
        ax2 = axes[1]
        ax2.plot(sub.index, sub["wind_speed"],    lw=0.6, color="gray",   label="Total wind (m/s)")
        ax2.plot(sub.index, sub["wind_perp_ms"],  lw=0.7, color="orange", label="Perpendicular wind (m/s)")
        ax2.set_ylabel("Wind Speed (m/s)")
        ax2.legend(fontsize=8)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax2.grid(alpha=0.3)

        # Panel 3 — Temperature
        ax3 = axes[2]
        ax3.plot(sub.index, sub["air_temp"], lw=0.7, color="tomato")
        ax3.set_ylabel("Ambient Temp (°C)")
        ax3.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax3.grid(alpha=0.3)

        # Panel 4 — Headroom histogram
        ax4 = axes[3]
        headroom = sub["dlr_headroom_pct"].dropna()
        ax4.hist(headroom, bins=60, color="steelblue", edgecolor="white", linewidth=0.3)
        ax4.axvline(0, color="red", ls="--", lw=1.5, label="Static rating = 0%")
        ax4.set_xlabel("DLR Headroom vs Static Rating (%)")
        ax4.set_ylabel("Frequency")
        ax4.legend(fontsize=8)
        ax4.grid(alpha=0.3)

        plt.tight_layout()
        filename = f"{file_prefix}_{stid}.png"
        out = os.path.join(output_dir, filename)
        
        plt.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"  Plot saved → {out}")
        plt.close()


def export_results(df: pd.DataFrame, output_path: str = ".", file_prefix: str="."):
    """Export pipeline output to CSV."""
    cols = [
        "stid", "datetime_utc",
        "air_temp", "wind_speed", "wind_direction", "wind_perp_ms",
        "solar_radiation", "relative_humidity",
        "dlr_amps", "dlr_headroom_pct", "dlr_uplift_flag",
    ]
    out = df[[c for c in cols if c in df.columns]]
    stations = out["stid"].unique()
    
    for stid in stations:
        # Isolate the data for just this one station
        sub = out[out["stid"] == stid]
        
        # Create a dynamic file name (e.g., dlr_results_AP140.csv)
        filename = f"{file_prefix}_{stid}.csv"
        filepath = os.path.join(output_path, filename)
        
        # Export
        sub.to_csv(filepath, index=False)
        log.info(f"  Results exported → {filepath}  ({len(sub):,} rows)")


# ──────────────────────────────────────────────────────────────────────────────
# 6.  ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── Transmission line config ──────────────────────────────────────────────
    # Example: West Texas 345 kV line running roughly E–W (azimuth ~90°)
    # through the Permian Basin wind corridor
    conductor = ConductorConfig(
        diameter_m    = 0.02814,   # 795 kcmil Drake ACSR
        resistance_ac = 0.0726,    # Ω/km at 25°C
        emissivity    = 0.8,
        absorptivity  = 0.8,
        max_temp_c    = 75.0,
        line_azimuth  = 90.0,      # ← set to actual line bearing
        elevation_m   = 900.0,     # West Texas Permian Basin avg elevation
    )

    # ── Target stations ───────────────────────────────────────────────────────
    # WTM stations near high-wind West Texas corridors.
    # You can pull full list via:  get_wtm_stations()
    #TARGET_STATIONS = [
    #    "MRST2",   # Midland/Odessa area
    #    "ABLT2",   # Abilene
    #    "LMST2",   # Lubbock metro south
    #    "ANNT2",   # Andrews (Permian Basin)
    #    "SVNT2",   # Sweetwater (large wind farm area)
    #]
    OUTPUT_CSV = "outputs/station_data"
    os.makedirs(OUTPUT_CSV, exist_ok=True)
    OUTPUT_PLOTS = "outputs/station_plots"
    STATIC_RATINGS = {
        "AUSTIN": None,
        "EL_PASO": None,
        "MIDLAND": None
    }
    stations_df = pd.read_csv("data/wtm_stations_austin.csv")
    
    TARGET_STATIONS = stations_df["stid"].tolist()
    # ── Time window ───────────────────────────────────────────────────────────
    START = "2025-07-01T00:00:00Z"
    END   = "2025-07-04T23:55:00Z"

    # ── Run ───────────────────────────────────────────────────────────────────
    results = run_pipeline(
        stids          = TARGET_STATIONS,
        start          = START,
        end            = END,
        conductor      = conductor,
        static_rating  = 900.0,
        solar_alt_deg  = 72.0,   # July midday sun in West Texas
    )

    if not results.empty:
        #csv_path = os.path.join(OUTPUT_CSV)
        export_results(results, OUTPUT_CSV, file_prefix=f"{START.split('T')[0]}_{END.split('T')[0]}")
        plot_dlr_summary(results, static_rating=900.0, output_dir=OUTPUT_PLOTS, file_prefix=f"{START.split('T')[0]}_{END.split('T')[0]}")
