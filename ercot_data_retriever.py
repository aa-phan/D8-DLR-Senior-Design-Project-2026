import os
import pandas as pd
import gridstatus

def pull_ercot_data(start: str=".", end: str="."):
    print("Initializing gridstatus ERCOT client...")
    ercot = gridstatus.Ercot()
    
    print("Downloading 2025 historical load archive from ERCOT (this takes a moment)...")
    # ERCOT archives older data in yearly zips. gridstatus handles downloading and parsing this automatically.
    df = ercot.get_hourly_load_post_settlements(start, end)
    
    # gridstatus usually normalizes the time column to 'Interval Start' or 'Time'
    time_col = "Interval Start" if "Interval Start" in df.columns else "Time"
    
    # Ensure it's in UTC so it merges perfectly with your Synoptic weather data
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    
    # Filter down to your specific DLR analysis window (July 1 - July 5, 2025)
    # Adding July 5th as a buffer to ensure we capture the end of July 4th in UTC
    mask = (df[time_col] >= f"{start}T00:00:00Z") & (df[time_col] <= f"{end}T00:00:00Z")
    summer_df = df.loc[mask].copy()
    
    # ERCOT splits Texas into 8 weather zones. The Permian Basin and high-wind corridors 
    # sit cleanly inside the FAR_WEST and WEST zones. 
    
    # Print available columns just so you can see ERCOT's naming convention
    print(f"Available ERCOT Zones: {', '.join([c for c in summer_df.columns if c != time_col])}")
    
    # Find columns that represent the western zones
    zone_cols = [c for c in summer_df.columns if "WEST" in c.upper()]
    
    if not zone_cols:
        print("Warning: Could not find 'WEST' or 'FAR_WEST' columns. Using total ERCOT load instead.")
        summer_df["ercot_west_load_mw"] = summer_df["ERCOT"] if "ERCOT" in summer_df.columns else summer_df.iloc[:, 1]
    else:
        # Sum the western zones to create our regional load proxy
        summer_df["ercot_west_load_mw"] = summer_df[zone_cols].sum(axis=1)
        
    # Clean up the final dataframe for the merger script
    final_df = summer_df[[time_col, "ercot_west_load_mw"]].rename(columns={time_col: "datetime_utc"})
    
    # Save it 
    os.makedirs("outputs/ercot_data", exist_ok=True)
    out_path = "outputs/ercot_data/ercot_west_load_july2025.csv"
    final_df.to_csv(out_path, index=False)
    
    print(f"Success! Saved {len(final_df)} hourly records to {out_path}")

if __name__ == "__main__":
    START = "2025-07-01"
    END = "2025-07-05"
    pull_ercot_data(START, END)