import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import config

# ──────────────────────────────────────────────────────────────────────────────
# 1. CONFIG & CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
LINE_VOLTAGE_KV = config.LINE_VOLTAGE_KV  # ERCOT West Texas standard backbone
POWER_FACTOR = config.POWER_FACTOR        # Standard conservative assumption for grid power

def amps_to_mw(amps: float, voltage_kv: float, pf: float) -> float:
    """
    Convert Line Current (Amps) to 3-Phase Real Power (Megawatts).
    Formula: P = sqrt(3) * V * I * PowerFactor
    """
    return (np.sqrt(3) * voltage_kv * amps * pf) / 1000.0

# ──────────────────────────────────────────────────────────────────────────────
# 2. DATA PROCESSING
# ──────────────────────────────────────────────────────────────────────────────
def process_dlr_to_hourly(dlr_csv_path: str, city: str = None) -> pd.DataFrame:
    """Loads 5-min DLR data and resamples to Hourly worst-case.

    Args:
        dlr_csv_path: Path to the 5-minute DLR CSV to load.
        city: Selects the per-location static rating from
            `config.STATIC_RATINGS` (e.g. `"AUSTIN"`). An unrecognised or
            omitted city falls back to `config.DEFAULT_STATIC_RATING`. One
            call covers one station's CSV — one city, one resolved rating
            per call.
    """
    df = pd.read_csv(dlr_csv_path)
    
    # Convert string to true datetime and set as the dataframe index
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"])
    df = df.set_index("datetime_utc")
    
    # RESAMPLING: We use .min() for ampacity. 
    # Why? If the wind dies for 15 mins, the line capacity plummets. 
    # The hourly rating MUST reflect the weakest/safest link in that hour.
    hourly = df.resample("1h").agg({
        "dlr_amps": "min",         # Safety first: worst-case capacity
        "wind_speed": "mean",      # Averages for context
        "air_temp": "mean"
    }).dropna()
    
    # Convert Amps to MW for ERCOT comparison
    hourly["dlr_capacity_mw"] = amps_to_mw(hourly["dlr_amps"], LINE_VOLTAGE_KV, POWER_FACTOR)
    # Resolve the per-location static rating once per call. An unrecognised
    # or omitted city falls back to DEFAULT_STATIC_RATING, which is
    # conservative by construction: it is strictly lower than every
    # configured city rating, so a typo understates capacity rather than
    # overstating it.
    static_rating = config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)
    hourly["static_capacity_mw"] = amps_to_mw(static_rating, LINE_VOLTAGE_KV, POWER_FACTOR)
    
    return hourly.reset_index()

def load_ercot_west_data(start: pd.Timestamp, end: pd.Timestamp, csv_path: str=".") -> pd.DataFrame:
    """
    Loads real ERCOT hourly load data for the West zones and filters it 
    to match the exact time window of our DLR data.
    """
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Could not find ERCOT data at {csv_path}. Run the retriever script first.")
        
    print(f"Loading real ERCOT data from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # Convert string to timezone-aware datetime so it matches the DLR dataframe
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"])
    
    # Filter the massive ERCOT dataset down to exactly the hours we have DLR data for
    mask = (df["datetime_utc"] >= start) & (df["datetime_utc"] <= end)
    filtered_df = df.loc[mask].copy()
    
    return filtered_df

# ──────────────────────────────────────────────────────────────────────────────
# 3. VISUALIZATION
# ──────────────────────────────────────────────────────────────────────────────
def plot_holistic_grid_view(merged_df: pd.DataFrame, stid: str):
    """Plots the merged Capacity vs. Demand."""
    
    # Convert UTC to US/Central for plotting so the peaks align with local afternoon
    merged_df["datetime_local"] = merged_df["datetime_utc"].dt.tz_convert("US/Central")
    merged_df = merged_df.set_index("datetime_local")
    
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    fig.suptitle(f"Holistic Grid View: ERCOT West Demand vs. WTM Station {stid} Capacity", fontsize=14, fontweight="bold")
    
    # Panel 1: Megawatts (Capacity vs Demand)
    ax1 = axes[0]
    ax1.plot(merged_df.index, merged_df["dlr_capacity_mw"], color="steelblue", lw=2, label="Dynamic Line Capacity (MW)")
    static_capacity_mw = merged_df["static_capacity_mw"].iloc[0]
    ax1.axhline(static_capacity_mw, color="red", ls="--", lw=2, label=f"Static Limit (~{static_capacity_mw:.0f} MW)")
    
    # Plot ERCOT Load. We fill the area underneath to show the "volume" of demand
    ax1.plot(merged_df.index, merged_df["ercot_west_load_mw"], color="darkorange", lw=2, label="ERCOT West Load Demand (MW)")
    ax1.fill_between(merged_df.index, 0, merged_df["ercot_west_load_mw"], color="darkorange", alpha=0.1)
    
    ax1.set_ylabel("Power (Megawatts)")
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.3)
    
    # Panel 2: Congestion / Utilization Risk
    ax2 = axes[1]
    # Calculate what % of the line's capacity the total regional load represents 
    # (Simplified metric for visual correlation)
    utilization_dlr = (merged_df["ercot_west_load_mw"] / merged_df["dlr_capacity_mw"]) * 100
    utilization_static = (merged_df["ercot_west_load_mw"] / merged_df["static_capacity_mw"]) * 100
    
    ax2.plot(merged_df.index, utilization_static, color="red", ls="--", alpha=0.6, label="Stress % (if using Static)")
    ax2.plot(merged_df.index, utilization_dlr, color="steelblue", lw=1.5, label="Stress % (Actual with DLR)")
    
    ax2.set_ylabel("Proxy System Stress (%)")
    ax2.legend(loc="upper left")
    ax2.grid(alpha=0.3)
    
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
    plt.xticks(rotation=45)
    
    plt.tight_layout()
    plt.savefig(f"holistic_view_{stid}.png", dpi=150, bbox_inches="tight")
    print(f"Plot saved to holistic_view_{stid}.png")

# ──────────────────────────────────────────────────────────────────────────────
# 4. EXECUTION
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 1. Point this to one of the CSVs generated by your previous script
    TARGET_STATION = "AN489"
    DLR_FILE = f"outputs/station_data/2025-07-01_2025-07-04_{TARGET_STATION}.csv"
    ERCOT_START = "2025-07-01"
    ERCOT_END = "2025-07-05"
    CSV_PATH = f"outputs/ercot_data/ercot_west_load_{ERCOT_START}_{ERCOT_END}.csv"
    # Ensure the file exists before running
    if os.path.exists(DLR_FILE):
        print(f"Loading DLR Data for {TARGET_STATION}...")
        # TARGET_STATION "AN489" is an Austin-network WTM station (D-07).
        dlr_hourly = process_dlr_to_hourly(DLR_FILE, city="AUSTIN")
        
        print("Loading ERCOT Data...")
        # Get start/end bounds from the actual DLR data to pull exact ERCOT matches
        start_bound = dlr_hourly["datetime_utc"].min()
        end_bound = dlr_hourly["datetime_utc"].max()
        ercot_data = load_ercot_west_data(start=start_bound, end=end_bound, csv_path=CSV_PATH)
        
        print("Merging datasets...")
        # Merge on the UTC hour
        merged = pd.merge(dlr_hourly, ercot_data, on="datetime_utc", how="inner")
        
        print("Generating Holistic Plot...")
        plot_holistic_grid_view(merged, TARGET_STATION)
        
        # Save the merged dataset
        merged.to_csv(f"merged_ercot_dlr_{TARGET_STATION}.csv", index=False)
    else:
        print(f"ERROR: Could not find {DLR_FILE}. Did you run the pipeline script first?")