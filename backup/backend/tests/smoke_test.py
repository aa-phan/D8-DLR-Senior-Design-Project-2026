"""
Smoke test for Track 1: confirms everything imports and runs end to end
without crashing, before touching real historical data.
"""

import os
import station_explorer
from city_rating import rate_city

token = os.getenv("SYNOPTIC_TOKEN", "")
if not token:
    raise SystemExit("Set SYNOPTIC_TOKEN before running this smoke test.")

print("Discovering stations (unrestricted network)...")
stations = station_explorer.get_all_stations(token, network_id=None)
print(f"  Found {len(stations)} stations")

result = rate_city(
    city="AUSTIN",
    start="2026-09-20T00:00:00Z",
    end="2026-09-23T23:55:00Z",
    stations=stations,
    provider="synoptic",
)

print("\n--- Result ---")
print("City:", result["city"])
print("Point:", result["point"])
print("Station:", result["station_id"])
print("Rating (A):", round(result["rating"]))
print("Status:", result["status"])
print("Fallback:", result["fallback"])
print("Exhausted:", result["exhausted"])
print("Archived:", result["archived"])
for alert in result["alerts"]:
    print("    ", alert)
