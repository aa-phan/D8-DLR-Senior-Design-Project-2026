"""
Smoke test for Track 1: confirms everything imports and runs end to end
without crashing, before touching real historical data.
"""

import os
import station_explorer
from corridor_pipeline import run_corridor_pipeline

token = os.getenv("SYNOPTIC_TOKEN", "")
if not token:
    raise SystemExit("Set SYNOPTIC_TOKEN before running this smoke test.")

print("Discovering stations (unrestricted network)...")
stations = station_explorer.get_all_stations(token, network_id=None)
print(f"  Found {len(stations)} stations")

result = run_corridor_pipeline(
    corridor_name="AUSTIN_CORPUS_CHRISTI",
    start="2026-09-20T00:00:00Z",
    end="2026-09-23T23:55:00Z",
    stations=stations,
    provider="synoptic",
)

print("\n--- Result ---")
print("Corridor:", result["corridor"])
print("Rating (A):", result["rating"])
print("Bottleneck index:", result["bottleneck_index"])
print("Fallback:", result["fallback"])
print("Exhausted points:", result["exhausted_points"])
print("Archived:", result["archived"])

print("\n--- Per point ---")
for i, p in enumerate(result["points"]):
    print(i, p["stid"], round(p["rating"]), p["status"], p["fallback"])
    for alert in p["alerts"]:
        print("    ", alert)