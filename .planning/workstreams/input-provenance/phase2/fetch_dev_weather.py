"""Fetch 2025 hourly Open-Meteo archive weather for the four city points (development window only).

Usage (repo root): py -I .planning/workstreams/input-provenance/phase2/fetch_dev_weather.py
2025 is before the 2026-09-29 anti-peeking cutoff and inside the models' 2023-2025 training years.
Writes dev_weather_2025_<CITY>.json beside this script. Network; read-only on the repo.
"""
import json, pathlib, sys, time, urllib.parse, urllib.request
sys.path.insert(0, "backend")
import config

BASE = "https://archive-api.open-meteo.com/v1/archive"  # same constant as backend/open_meteo_provider.py
HOURLY = "temperature_2m,wind_speed_10m,wind_direction_10m,shortwave_radiation,relative_humidity_2m"
out = pathlib.Path(__file__).parent
for city, (lat, lon) in config.CITY_COORDINATES.items():
    q = {"latitude": lat, "longitude": lon, "start_date": "2025-01-01", "end_date": "2025-12-31",
         "hourly": HOURLY, "wind_speed_unit": "ms", "timezone": "UTC"}
    with urllib.request.urlopen(BASE + "?" + urllib.parse.urlencode(q), timeout=90) as r:
        body = json.load(r)
    (out / f"dev_weather_2025_{city}.json").write_text(json.dumps({"params": q, "response": body}))
    print(city, len(body["hourly"]["time"]), "hours")
    time.sleep(5)
