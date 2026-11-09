import json, sys, statistics as st
sys.path.insert(0, "/Users/aphan/Senior_Design/backend")
import config, thermal_model as tm
TRACE = "/Users/aphan/Senior_Design/data/historical/real_data_validation_2026-09-08_2026-09-28_trace.jsonl"
obs = []
for line in open(TRACE):
    r = json.loads(line)
    if r["city"] == "AUSTIN" and r["observation"] and r["observation_hour"] >= "2026-09-15":
        obs.append(r)
base = dict(config.conductor_kwargs_for(config.CITY_LINE_BEARING_DEG["AUSTIN"]))
# approximate catalogue values (Southwire-style ACSR tables), Rac at 25C in ohm/km
COND = {"Suwannee 959.6 ACSS/TW": (0.02819, 0.0597), "Drake 795": (0.02814, 0.0726), "Rail 954": (0.02959, 0.0612), "Falcon 1590": (0.03924, 0.0371)}
lo, hi = config.RATING_BOUNDS_BY_LOCATION["AUSTIN"]
def run(name, tmax, elev):
    d, r = COND[name]
    c = tm.ConductorConfig(**{**base, "diameter_m": d, "resistance_ac": r, "max_temp_c": tmax, "elevation_m": elev})
    vals = [float(tm.ieee738_ampacity(o["observation"]["temp"], o["observation"]["wind"], o["observation"]["solar"], c, 45.0)) for o in obs]
    below = sum(v < lo for v in vals) / len(vals)
    return st.median(vals), min(vals), below
# sanity: reproduce live-path ok ratings
c0 = tm.ConductorConfig(**base)
ok = [o for o in obs if o["status"] == "ok"]
err = max(abs(float(tm.ieee738_ampacity(o["observation"]["temp"], o["observation"]["wind"], o["observation"]["solar"], c0, 45.0)) - o["rating_a"]) for o in ok)
print(f"steps={len(obs)} ok_steps={len(ok)} max_repro_err_A={err:.6f} bounds={lo}-{hi}")
print(f"{"conductor":24} {'MOT':>4} {'elev':>5} {'median':>7} {'min':>6} {'%<1150':>7}")
for name in COND:
    for tmax in ((75, 100, 150, 200) if name.startswith("Suw") else (75, 90, 100)):
        for elev in (163,):
            m, mn, b = run(name, tmax, elev)
            print(f"{name:24} {tmax:>4} {elev:>5} {m:7.0f} {mn:6.0f} {b*100:6.1f}%")
