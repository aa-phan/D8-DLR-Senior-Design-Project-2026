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

from units_def import validate_pipeline_row
import thermal_model
import config

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
        try:
            lat = float(station.get("LATITUDE"))
        except (TypeError, ValueError):
            lat = None
        try:
            lon = float(station.get("LONGITUDE"))
        except (TypeError, ValueError):
            lon = None
        row["lat"] = lat
        row["lon"] = lon
        frames.append(pd.DataFrame(row))

    if not frames:
        log.warning("No data returned — check station IDs and date range.")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = df.set_index(["stid", "datetime_utc"]).sort_index()
    log.info(f"  Retrieved {len(df):,} observation rows")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# 2.  PERPENDICULAR WIND COMPONENT / 3. IEEE 738 THERMAL MODEL
# ──────────────────────────────────────────────────────────────────────────────
# ConductorConfig, perpendicular_wind, and ieee738_ampacity (C5) now live in
# thermal_model.py — a pure module with no ingestion dependencies and no
# __main__ side effects. See thermal_model.ConductorConfig,
# thermal_model.perpendicular_wind, thermal_model.ieee738_ampacity.


# ──────────────────────────────────────────────────────────────────────────────
# 4.  PIPELINE ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    stids:          list[str],
    start:          str,
    end:            str,
    conductor:      thermal_model.ConductorConfig,
    city:           str = None,      # e.g. "AUSTIN" — selects the per-city static rating
    solar_alt_deg:  float = 45.0,
) -> pd.DataFrame:
    """
    Full pipeline: fetch WTM data → compute perpendicular wind → IEEE 738 DLR.

    Args:
        stids:          List of WTM station IDs
        start / end:    ISO-8601 UTC strings
        conductor:      thermal_model.ConductorConfig instance
        city:           Selects this station's per-city static rating from
                        config.STATIC_RATINGS (e.g. "AUSTIN"); an
                        unrecognised or omitted city falls back to
                        config.DEFAULT_STATIC_RATING.
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
    obs["wind_perp_ms"] = thermal_model.perpendicular_wind(
        obs["wind_speed"].values,
        obs["wind_direction"].values,
        conductor.line_az,
    )

    # Step 4 — IEEE 738 dynamic rating
    obs["dlr_amps"] = thermal_model.ieee738_ampacity(
        T_amb_c      = obs["air_temp"].values,
        wind_perp_ms = obs["wind_perp_ms"].values,
        ghi_wm2      = obs["solar_radiation"].values,
        conductor    = conductor,
        solar_altitude_deg = solar_alt_deg,
    )

    # Step 5 — DLR headroom vs static rating
    static_rating = config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)
    obs["dlr_headroom_pct"] = (obs["dlr_amps"] - static_rating) / static_rating * 100
    obs["dlr_uplift_flag"]  = obs["dlr_amps"] > static_rating

    log.info(
        f"Pipeline complete. "
        f"Median DLR = {obs['dlr_amps'].median():.0f} A | "
        f"% time DLR > static = {obs['dlr_uplift_flag'].mean()*100:.1f}%"
    )

    # Step 6 — Data contract validation (C2). Detection/logging only — does
    # NOT modify, drop, or filter any rows. Non-strict so one bad row
    # (e.g. a unit mismatch) surfaces as a warning instead of aborting an
    # entire multi-station pipeline run.
    validate_pipeline_output(obs)

    return obs


def validate_pipeline_output(df: pd.DataFrame, max_examples: int = 10) -> int:
    """
    Validate every row of a pipeline output DataFrame against PIPELINE_SCHEMA
    (backend/units_def.py) in non-strict mode, and log a summary.

    Detection/logging only: never mutates or filters `df`.

    Returns:
        Number of rows with at least one violation.
    """
    total_rows = len(df)
    rows_with_violations = 0
    message_counts: dict[str, int] = {}

    for row in df.to_dict("records"):
        violations = validate_pipeline_row(row, strict=False)
        if violations:
            rows_with_violations += 1
            for msg in violations:
                message_counts[msg] = message_counts.get(msg, 0) + 1

    if rows_with_violations == 0:
        log.info(
            f"Data contract check: {total_rows:,} rows checked, "
            f"0 violations (PIPELINE_SCHEMA, backend/units_def.py)."
        )
    else:
        log.warning(
            f"Data contract check: {rows_with_violations:,}/{total_rows:,} rows "
            f"violated PIPELINE_SCHEMA — exported output may contain bad data."
        )
        unique_messages = sorted(message_counts.items(), key=lambda kv: -kv[1])
        for msg, count in unique_messages[:max_examples]:
            log.warning(f"  [{count}x] {msg}")
        if len(unique_messages) > max_examples:
            log.warning(
                f"  … {len(unique_messages) - max_examples} more distinct "
                f"violation message(s) not shown."
            )

    return rows_with_violations


def profile_missing_data(df: pd.DataFrame):
    """Analyzes and prints the percentage of missing values per station."""
    log.info("--- Missing Data Profile ---")
    
    # Check if the dataframe is completely empty first
    if df.empty:
        log.warning("Dataframe is empty. Cannot profile missing data.")
        return

    # Calculate the percentage of missing data for each variable, grouped by station
    # include_groups=False avoids a pandas FutureWarning (grouping columns
    # will be excluded from apply() in a future version) and keeps this
    # function warning-silent, which run_pipeline's callers rely on (D-02).
    missing_pct = df.groupby("stid").apply(lambda x: x.isna().mean() * 100, include_groups=False)
    
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

def plot_dlr_summary(df: pd.DataFrame, city: str = None, output_dir: str=".", file_prefix: str="dlr"):
    """
    4-panel summary plot:
      1. DLR time series vs static rating
      2. Wind speed & perpendicular component
      3. Ambient temperature
      4. DLR headroom distribution (histogram)

    Args:
        df:          Pipeline output DataFrame (see run_pipeline).
        city:        Selects this station's per-city static rating from
                     config.STATIC_RATINGS (e.g. "AUSTIN"); an
                     unrecognised or omitted city falls back to
                     config.DEFAULT_STATIC_RATING.
        output_dir:  Directory to write PNGs to.
        file_prefix: Filename prefix for each station's plot.
    """
    static_rating = config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)
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
    conductor = thermal_model.ConductorConfig(**config.DEFAULT_CONDUCTOR_CONFIG_KWARGS)

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
    stations_df = pd.read_csv(config.DEFAULT_STATION_SOURCE)

    TARGET_STATIONS = stations_df["stid"].tolist()
    # ── Time window ───────────────────────────────────────────────────────────
    START = config.DEFAULT_START
    END   = config.DEFAULT_END

    # ── Run ───────────────────────────────────────────────────────────────────
    # config.DEFAULT_STATION_SOURCE is "data/wtm_stations_austin.csv", so
    # this demo run is unambiguously Austin data (D-06).
    results = run_pipeline(
        stids          = TARGET_STATIONS,
        start          = START,
        end            = END,
        conductor      = conductor,
        city           = "AUSTIN",
        solar_alt_deg  = 72.0,   # July midday sun in West Texas
    )

    if not results.empty:
        #csv_path = os.path.join(OUTPUT_CSV)
        export_results(results, OUTPUT_CSV, file_prefix=f"{START.split('T')[0]}_{END.split('T')[0]}")
        plot_dlr_summary(results, city="AUSTIN", output_dir=OUTPUT_PLOTS, file_prefix=f"{START.split('T')[0]}_{END.split('T')[0]}")