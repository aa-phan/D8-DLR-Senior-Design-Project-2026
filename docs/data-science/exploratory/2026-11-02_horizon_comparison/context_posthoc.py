"""
Exploratory, not pre-registered; does not change signed protocol v4 or read 1.
POST-HOC descriptive context added after seeing the planned results (not in PLAN.md; no tests):
  1. ml_60min / naive_60min MAE over EVERY hour of the TEST window (not only the 00/06/12/18 UTC slots).
  2. Production basis: MAE of ml_60min, naive_60min, ml_cooling_corrected and raw_forecast by UTC slot hour.
Writes context_posthoc.md here.
    PYTHONPATH=backend .venv/bin/python docs/data-science/exploratory/2026-11-02_horizon_comparison/context_posthoc.py
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ampacity_forecast  # noqa: E402
import city_point  # noqa: E402
import config  # noqa: E402
import forecast_test_split_score as tss  # noqa: E402
from build_rows import CUTOFF, assert_before_cutoff, hourly_amps  # noqa: E402

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
lines = ["Exploratory, not pre-registered; does not change signed protocol v4 or read 1. **Post-hoc, descriptive "
         "only** (added after seeing the planned results).", "",
         "## 1. 60-minute arms over every hour of the TEST window (production basis)", "",
         "| city | n hours | ml60 MAE | naive60 MAE | ml60 MAE at the 4 slot hours only |", "|---|---|---|---|---|"]
rows = pd.read_csv(os.path.join(OUT_DIR, "rows_production.csv"))
rows["valid_time"] = pd.to_datetime(rows["valid_time"], utc=True)
assert rows["valid_time"].max() < CUTOFF
for city in config.LOCATIONS:
    frame, weather, _ = tss.cached_test_provider(city, evidence_dir=None)
    assert_before_cutoff(weather["datetime_utc"], city)
    h = hourly_amps(weather, city_point.production_city_point(city))
    feats = ampacity_forecast.build_ml_features(h)
    vt = h.index[(h.index >= tss.TEST_WINDOW_START) & (h.index < tss.TEST_WINDOW_END_EXCLUSIVE)]
    issue = vt - pd.Timedelta(hours=1)
    X = feats.reindex(issue)
    truth = h["dlr_amps"].reindex(vt).to_numpy()
    naive = h["dlr_amps"].reindex(issue).to_numpy()
    ok = ~X.isnull().any(axis=1).to_numpy() & np.isfinite(truth)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pred = ampacity_forecast._load_model(city).predict(X.to_numpy(float)[ok])
    slot = rows[rows.city == city]
    lines.append(f"| {city} | {int(ok.sum())} | {np.mean(np.abs(pred - truth[ok])):.1f} | "
                 f"{np.nanmean(np.abs(naive[ok] - truth[ok])):.1f} | "
                 f"{np.mean(np.abs(slot.ml_60min - slot.truth_amps)):.1f} |")

lines += ["", "## 2. MAE by UTC slot hour, production basis, pooled over cities (n = 784 per hour)", "",
          "| UTC hour (CDT = UTC−5) | ml60 | naive60 | cooling (24 h) | raw (24 h) | cooling − ml60 |", "|---|---|---|---|---|---|"]
rows["hour"] = rows["valid_time"].dt.hour
for hr, g in rows.groupby("hour"):
    m = {a: np.mean(np.abs(g[a] - g.truth_amps)) for a in ("ml_60min", "naive_60min", "ml_cooling_corrected", "raw_forecast")}
    lines.append(f"| {hr:02d} | {m['ml_60min']:.1f} | {m['naive_60min']:.1f} | {m['ml_cooling_corrected']:.1f} | "
                 f"{m['raw_forecast']:.1f} | {m['ml_cooling_corrected'] - m['ml_60min']:+.1f} |")
with open(os.path.join(OUT_DIR, "context_posthoc.md"), "w") as fh:
    fh.write("\n".join(lines) + "\n")
print("\n".join(lines))
