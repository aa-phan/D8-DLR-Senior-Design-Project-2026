import os
import math
import requests
import pandas as pd
from typing import Union, Optional

SYNOPTIC_BASE = "https://api.synopticdata.com/v2"

CORRIDORS = {
    "Panhandle_Export": (34.5, -101.8),
    "Permian_Basin_345kV": (31.9, -102.3),
    "Sweetwater_Wind_Hub": (32.5, -100.4),
    "Big_Spring_Corridor": (32.2, -101.4),
    "West_TX_to_Hill_Country": (30.5, -99.0),
}

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def check_summary(data):
    summary = data.get("SUMMARY", {})
    code = str(summary.get("RESPONSE_CODE"))
    if code != "1":
        raise RuntimeError(f"Synoptic API error: {summary}")

def get_network_id(token: str, shortname: str) -> str:
    params = {
        "token": token.strip(),
        "shortname": shortname,
        "output": "json",
    }
    r = requests.get(f"{SYNOPTIC_BASE}/networks", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    check_summary(data)

    nets = data.get("MNET", [])
    if not nets:
        raise ValueError(f"No network found for shortname={shortname!r}")

    return nets[0]["ID"]

def get_all_stations(token: str, network_id: Optional[str] = None) -> pd.DataFrame:
    params = {
        "token": token.strip(),
        "state": "TX",
        "output": "json",
    }
    if network_id is not None:
        params["network"] = network_id

    r = requests.get(f"{SYNOPTIC_BASE}/stations/metadata", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    check_summary(data)

    rows = []
    for s in data.get("STATION", []):
        rows.append({
            "stid": s["STID"],
            "name": s["NAME"],
            "lat": float(s["LATITUDE"]),
            "lon": float(s["LONGITUDE"]),
            "elev_ft": float(s.get("ELEVATION", 0) or 0),
            "county": s.get("COUNTY", ""),
            "state": s.get("STATE", "TX"),
        })
    return pd.DataFrame(rows)

def nearest_stations(stations: pd.DataFrame, lat: float, lon: float, n: int = 5) -> pd.DataFrame:
    """
    Generalization of `rank_by_corridor` from the fixed five-point
    `CORRIDORS` dict to an arbitrary (lat, lon) point (D-07's station-
    resolution layer, consumed by `corridor_discretization.py`, C8).

    Returns at most `n` rows of `stations`, sorted ascending by a
    `km_to_point` column this function adds, with ties broken by `stid`
    ascending so equal-distance stations resolve deterministically and
    reproducibly (DS-NF2) rather than depending on Synoptic's row order.

    Unlike `rank_by_corridor`, this function does NOT mutate its argument:
    it copies `stations` before adding `km_to_point`, so the caller's frame
    is unchanged after the call.
    """
    if stations.empty:
        return stations

    stations = stations.copy()
    stations["km_to_point"] = stations.apply(
        lambda r: haversine_km(r["lat"], r["lon"], lat, lon),
        axis=1,
    )
    return stations.sort_values(["km_to_point", "stid"]).head(n).reset_index(drop=True)


def rank_by_corridor(stations: pd.DataFrame) -> pd.DataFrame:
    if stations.empty:
        return stations

    for name, (clat, clon) in CORRIDORS.items():
        stations[f"km_to_{name}"] = stations.apply(
            lambda r: haversine_km(r["lat"], r["lon"], clat, clon),
            axis=1,
        )

    dist_cols = [c for c in stations.columns if c.startswith("km_to_")]
    stations["nearest_corridor"] = stations[dist_cols].idxmin(axis=1).str.replace("km_to_", "", regex=False)
    stations["nearest_corridor_km"] = stations[dist_cols].min(axis=1)
    return stations.sort_values("nearest_corridor_km").reset_index(drop=True)

if __name__ == "__main__":
    token = os.environ.get("SYNOPTIC_TOKEN", "")
    if not token:
        print("ERROR: Set SYNOPTIC_TOKEN env var first.")
        raise SystemExit(1)

    # Comment this out if you want all Texas stations instead
    # network_id = get_network_id(token, "wtm")
    #network_id = get_network_id(token, "WTEXAS")
    network_id = 152
    # network_id = None
    print("Fetching stations in Texas …")
    stations = get_all_stations(token, network_id)
    print(f"  Found {len(stations)} stations")

    if stations.empty:
        print("No stations returned.")
        raise SystemExit(1)

    stations = rank_by_corridor(stations)
    stations.to_csv("data/wtm_stations_austin.csv", index=False)
    print("  → Saved to data/wtm_stations_austin.csv")

    print("\nTop 15 stations by proximity to DLR-relevant corridors:")
    print(
        stations[["stid", "name", "county", "nearest_corridor", "nearest_corridor_km"]]
        .head(15)
        .to_string(index=False)
    )