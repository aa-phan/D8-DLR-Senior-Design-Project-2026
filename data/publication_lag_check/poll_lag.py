"""Measure when a gfs_seamless single run first becomes fetchable. Weather fetches only.
Usage (repo root): python -I poll_lag.py OUT_JSONL CITY INIT_ISO [INIT_ISO ...]
Polls each init every 5 min (one city) until a non-empty, non-null response, up to 10 h after init."""
import sys, json, time, datetime as dt, pathlib
sys.path.insert(0, "backend")
import pandas as pd, config, open_meteo_forecast_provider as p
out, city, inits = pathlib.Path(sys.argv[1]), sys.argv[2], [pd.Timestamp(x, tz="UTC") for x in sys.argv[3:]]
lat, lon = config.CITY_COORDINATES[city]
pending = set(inits)
def log(rec):
    with out.open("a") as f: f.write(json.dumps(rec) + "\n")
while pending:
    now = pd.Timestamp.now(tz="UTC")
    for init in sorted(pending):
        if now < init: continue
        try:
            fr = p.fetch_single_run(lat, lon, init, forecast_days=1, model=config.SHADOW_LIVE_FORECAST_MODEL, timeout=30)
            core = ["air_temp", "wind_speed", "wind_direction", "relative_humidity"]  # solar is NaN at the init hour
            ok = (not fr.empty) and bool(fr[core].notna().all().all())
            status = "ok" if ok else "empty_or_null"
        except p.SingleRunUnavailable as e:
            ok, status = False, "unavailable"
        except Exception as e:
            ok, status = False, f"error:{type(e).__name__}"
        log({"city": city, "init": str(init), "polled_at": str(now.floor("s")), "status": status,
             "age_h": round((now - init).total_seconds() / 3600, 3)})
        if ok or (now - init) > pd.Timedelta(hours=10):
            pending.discard(init)
    if pending: time.sleep(300)
