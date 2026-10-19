"""Fetch the Open-Meteo archive window for the 4 cities, truth only. Usage: fetch_truth.py OUTDIR START END"""
import sys, json, time, datetime as dt, pathlib
sys.path.insert(0, "backend")
import requests, config, open_meteo_provider as p
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
start, end = sys.argv[2], sys.argv[3]
stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
for city, (lat, lon) in config.CITY_COORDINATES.items():
    params = {"latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
              "hourly": ",".join(p.OPEN_METEO_HOURLY_VARS), "wind_speed_unit": "ms", "timezone": "UTC"}
    r = requests.get(p.OPEN_METEO_ARCHIVE_BASE, params=params, timeout=60); r.raise_for_status()
    (out / f"{city}_{start}_{end}_fetched_{stamp}.json").write_text(json.dumps(
        {"fetched_at_utc": stamp, "params": params, "response": r.json()}))
    print(city, len(r.json()["hourly"]["time"]), "hours")
    time.sleep(3)
