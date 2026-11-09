"""Pick 5 sample hours per city for each Phase 2 sensitivity case from the 2025 development weather.

Usage (repo root): py -I .planning/workstreams/input-provenance/phase2/pick_samples.py
Deterministic. Cases: hot_calm, median_day, breezy_cool (coldest 10% of hours, wind above the median), perpendicular_wind, parallel_wind.
Line axis = config.CITY_LINE_BEARING_DEG (an assumption; PROV-03). Angle is the acute angle between the wind flow
and the line, computed as in thermal_model.perpendicular_wind (no 20-degree clamp applied here).
"""
import csv, datetime as dt, json, pathlib, statistics, sys
sys.path.insert(0, "backend")
import config

here = pathlib.Path(__file__).parent
MIN_SEP_DAYS = 14

def load(city):
    h = json.loads((here / f"dev_weather_2025_{city}.json").read_text())["response"]["hourly"]
    rows = []
    for i, t in enumerate(h["time"]):
        v = [h[k][i] for k in ("temperature_2m", "wind_speed_10m", "wind_direction_10m",
                               "shortwave_radiation", "relative_humidity_2m")]
        if None in v:
            continue
        rows.append(dict(time=t, temp=v[0], wind=v[1], wdir=v[2], ghi=v[3], rh=v[4]))
    return rows

def angle(wdir, az):
    d = abs(((wdir + 180) % 360) - az) % 180
    return 180 - d if d > 90 else d

def pct(xs, p):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(p * len(xs)))]

def greedy(cands, key, n=5):
    chosen = []
    for r in sorted(cands, key=key):
        d = dt.datetime.fromisoformat(r["time"])
        if all(abs((d - dt.datetime.fromisoformat(c["time"])).days) >= MIN_SEP_DAYS for c in chosen):
            chosen.append(r)
        if len(chosen) == n:
            break
    return chosen

out = []
for city in config.CITY_COORDINATES:
    az = config.CITY_LINE_BEARING_DEG[city]
    rows = load(city)
    for r in rows:
        r["angle"] = angle(r["wdir"], az)
    day = [r for r in rows if r["ghi"] >= 300]
    T = [r["temp"] for r in rows]; W = [r["wind"] for r in rows]
    t95 = pct(T, .95); t10 = pct(T, .10); w25 = pct(W, .25); w50 = pct(W, .50); w75 = pct(W, .75)
    mt = statistics.median([r["temp"] for r in day]); mw = statistics.median([r["wind"] for r in day])
    cases = {
        "hot_calm": greedy([r for r in day if r["temp"] >= t95 and r["wind"] <= w25 and r["ghi"] >= 600],
                           key=lambda r: (r["wind"], -r["temp"])),
        "median_day": greedy(day, key=lambda r: abs(r["temp"] - mt) / 5 + abs(r["wind"] - mw)),
        "breezy_cool": greedy([r for r in rows if r["temp"] <= t10 and r["wind"] >= w50],
                              key=lambda r: (-r["wind"])),
        "perpendicular_wind": greedy([r for r in day if r["wind"] >= 3 and r["angle"] >= 80],
                                     key=lambda r: (abs(r["wind"] - mw * 1.5), -r["angle"])),
        "parallel_wind": greedy([r for r in day if r["wind"] >= 3 and r["angle"] <= 10],
                                key=lambda r: (abs(r["wind"] - mw * 1.5), r["angle"])),
    }
    for case, picks in cases.items():
        for r in picks:
            out.append(dict(city=city, case=case, time_utc=r["time"], air_temp_c=r["temp"], wind_ms=r["wind"],
                            wind_dir_deg=r["wdir"], ghi_wm2=r["ghi"], rh_pct=r["rh"],
                            line_azimuth_deg=az, wind_angle_to_line_deg=round(r["angle"], 1)))
        print(f"{city:15s} {case:19s} n={len(picks)}")
    print(f"   {city} P10/P95 temp={t10}/{t95}  P25/P75 wind={w25}/{w75}  day-median temp/wind={mt}/{mw}")
with open(here / "samples_5_per_case.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
print("wrote", len(out), "rows")
