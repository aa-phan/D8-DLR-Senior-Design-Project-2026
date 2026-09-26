"""
Historical ERCOT Settlement Load Retriever
==================================================
Offline historical-load source for v1.3 Phase 2's D-02 training-time-only
load characterization (see `backend/anomaly_training.py::characterize_load`).
Nothing in the runtime decision path imports this module -- a test in
`backend/tests/anomaly_training_test.py` asserts `anomaly_detector.py`
never imports it or `gridstatus`. This module exists solely to pull
historical ERCOT settlement load for an offline sanity-check of a
corridor's fitted per-variable weather envelope against known
load-driven demand patterns; it never touches `AnomalyDetector.check`'s
live input (`raw_data` carries no load field, and adding one is Track 1's
scope, not this workstream's -- see D-02).
"""

import os

import pandas as pd
import gridstatus


def pull_ercot_data(
    start: str = ".", end: str = ".", zone_substrings=None, save: bool = True
):
    """
    Pull historical ERCOT settlement load for `[start, end]`, summed over
    the ERCOT weather-zone columns whose (uppercased) name contains any of
    `zone_substrings`, and return the assembled frame (`datetime_utc` plus
    one summed load column).

    `zone_substrings` defaults to `("WEST",)` -- reproducing today's
    west-zone filter exactly for an unchanged call -- and is matched,
    uppercased, against ERCOT's real weather-zone column names (`Coast`,
    `East`, `Far West`, `North`, `North Central`, `South`, `South
    Central`, `West`, `ERCOT`). When no column matches, falls back to the
    total `ERCOT` column and prints a warning rather than raising or
    silently returning an empty frame.

    The installed `gridstatus` client's post-settlements load download is
    only ever asked for one calendar year at a time here -- verified this
    session (02-RESEARCH.md Pitfall 2) that a single call cannot reliably
    be trusted to honor a multi-year `end` -- so a `[start, end]` span is
    assembled with one download call per spanned calendar year, sorted by
    time with duplicate timestamps dropped, before the existing
    start-to-end mask is applied.

    `save=True` (default) writes the assembled frame to the same CSV path
    this function has always written to, under `outputs/ercot_data/`.
    `save=False` returns the frame without writing anything, so an
    in-process caller (e.g. `anomaly_training.characterize_load`) does not
    litter `outputs/`.
    """
    print("Initializing gridstatus ERCOT client...")
    ercot = gridstatus.Ercot()

    if zone_substrings is None:
        zone_substrings = ("WEST",)
    upper_substrings = tuple(s.upper() for s in zone_substrings)
    is_default_west = upper_substrings == ("WEST",)

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    print("Downloading historical load archive from ERCOT (this takes a moment)...")
    # One download call per spanned calendar year -- see docstring/Pitfall 2.
    year_frames = []
    for year in range(start_ts.year, end_ts.year + 1):
        year_frames.append(
            ercot.get_hourly_load_post_settlements(f"{year}-01-01", f"{year}-12-31")
        )
    df = pd.concat(year_frames, ignore_index=True)

    # gridstatus usually normalizes the time column to 'Interval Start' or 'Time'
    time_col = "Interval Start" if "Interval Start" in df.columns else "Time"

    # Ensure it's in UTC so it merges perfectly with the weather data
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    df = (
        df.sort_values(time_col)
        .drop_duplicates(subset=[time_col])
        .reset_index(drop=True)
    )

    # Filter down to the specific analysis window
    mask = (df[time_col] >= f"{start}T00:00:00Z") & (df[time_col] <= f"{end}T00:00:00Z")
    summer_df = df.loc[mask].copy()

    # ERCOT splits Texas into 8 weather zones plus a total (ERCOT) column.
    # Print available columns just so you can see ERCOT's naming convention
    print(f"Available ERCOT Zones: {', '.join([c for c in summer_df.columns if c != time_col])}")

    # Find columns matching the requested zone selection (never the time column).
    zone_cols = [
        c for c in summer_df.columns
        if c != time_col and any(sub in c.upper() for sub in upper_substrings)
    ]

    out_col = (
        "ercot_west_load_mw"
        if is_default_west
        else "ercot_" + "_".join(s.lower() for s in zone_substrings) + "_load_mw"
    )

    if not zone_cols:
        print(
            f"Warning: Could not find columns matching {upper_substrings}. "
            "Using total ERCOT load instead."
        )
        summer_df[out_col] = summer_df["ERCOT"] if "ERCOT" in summer_df.columns else summer_df.iloc[:, 1]
    else:
        # Sum the matched zones to create the regional load proxy
        summer_df[out_col] = summer_df[zone_cols].sum(axis=1)

    # Clean up the final dataframe for the merger script
    final_df = summer_df[[time_col, out_col]].rename(columns={time_col: "datetime_utc"})

    # Expose the resolved output column name and the real zone columns
    # that were actually matched (empty when the no-match fallback fired)
    # as frame attributes -- so a caller (e.g.
    # anomaly_training.characterize_load) can report which zones a
    # corridor was actually characterized against without re-deriving or
    # guessing the selection logic itself.
    final_df.attrs["load_column"] = out_col
    final_df.attrs["zone_columns_matched"] = list(zone_cols)

    if save:
        os.makedirs("outputs/ercot_data", exist_ok=True)
        start_tag = str(start).replace(":", "").replace(" ", "_")
        end_tag = str(end).replace(":", "").replace(" ", "_")
        out_path = f"outputs/ercot_data/ercot_west_load_{start_tag}_{end_tag}.csv"
        final_df.to_csv(out_path, index=False)
        print(f"Success! Saved {len(final_df)} hourly records to {out_path}")

    return final_df


if __name__ == "__main__":
    START = "2025-07-01"
    END = "2025-07-05"
    pull_ercot_data(START, END)
