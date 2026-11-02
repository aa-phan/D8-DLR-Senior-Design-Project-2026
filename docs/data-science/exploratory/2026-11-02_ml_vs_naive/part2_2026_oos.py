"""
Part 2 -- exploratory, not pre-registered; does not change signed protocol v4 or read 1.
2026-01-01T00Z .. 2026-09-29T23Z out-of-sample ml vs naive on Open-Meteo reanalysis
(city_training_frame, production conductor, projected wind). Reads data/models read-only;
writes only into this folder. Open-Meteo request end date is 2026-09-29.
Run: PYTHONPATH=backend:docs/data-science/exploratory/2026-11-02_ml_vs_naive .venv/bin/python <this file>
"""
import json
import os

import numpy as np
import pandas as pd

import ampacity_forecast
import config
import forecast_training
import open_meteo_provider
import stats_lib as L

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
CITIES = ["AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"]
FETCH_START, FETCH_END = "2025-12-25", "2026-09-29"
SCORE_START = pd.Timestamp("2026-01-01T00:00:00Z")
SCORE_END = pd.Timestamp("2026-09-29T23:00:00Z")
assert pd.Timestamp(FETCH_END + "T23:00:00Z") < L.CUTOFF
LOOKBACK = 7  # rows t-7..t-1 feed the ml features of target t (lag 6 + rolling 6 shifted 1)


def weather(city):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"open_meteo_{city}_{FETCH_START}_{FETCH_END}.csv")
    if os.path.exists(path):
        w = pd.read_csv(path)
        w["datetime_utc"] = pd.to_datetime(w["datetime_utc"], utc=True)
    else:
        lat, lon = config.CITY_COORDINATES[city]
        w = open_meteo_provider.fetch_open_meteo(lat, lon, FETCH_START, FETCH_END)
        w = w[w["datetime_utc"] < L.CUTOFF]
        w.to_csv(path, index=False)
    w = w[w["datetime_utc"] < L.CUTOFF].reset_index(drop=True)
    L.assert_before_cutoff(w["datetime_utc"])
    return w


def city_frame(city):
    w = weather(city)
    original = forecast_training.fetch_city_weather
    forecast_training.fetch_city_weather = lambda c, years: w  # in-process only
    try:
        frame = forecast_training.city_training_frame(city, 1)
    finally:
        forecast_training.fetch_city_weather = original
    L.assert_before_cutoff(frame["datetime_utc"])
    return frame


def errors(city):
    frame = city_frame(city)
    idx = frame.copy()
    idx.index = pd.to_datetime(idx["datetime_utc"], utc=True)
    idx = idx.sort_index()
    feats = ampacity_forecast.build_ml_features(idx)
    model = ampacity_forecast._load_model(city)
    ok = feats.notna().all(axis=1)
    pred = pd.Series(np.nan, index=idx.index)
    pred[ok] = model.predict(feats[ok].to_numpy(dtype=float))
    # history row t-1 -> target t
    tgt = pd.DataFrame({
        "feature_time": idx.index[:-1],
        "ml": pred.to_numpy()[:-1],
        "naive": idx["dlr_amps"].to_numpy()[:-1],
    }, index=idx.index[1:])
    tgt["truth"] = idx["dlr_amps"].to_numpy()[1:]
    # live lookback rule: rows t-7..t-1 all present and consecutive; target exactly 1 h after t-1
    times = idx.index
    pos = np.arange(len(times))
    contiguous = np.zeros(len(times), dtype=bool)
    for i in pos[LOOKBACK:]:
        contiguous[i] = (times[i] - times[i - LOOKBACK]) == pd.Timedelta(hours=LOOKBACK)
    tgt["lookback_ok"] = contiguous[1:]
    window = (tgt.index >= SCORE_START) & (tgt.index <= SCORE_END)
    tgt = tgt[window]
    expected = pd.date_range(SCORE_START, SCORE_END, freq="h")
    n_missing_target = int(len(expected.difference(tgt.index)))
    n_lookback_bad = int((~tgt["lookback_ok"]).sum() + (~np.isfinite(tgt["ml"])).sum())
    tgt = tgt[tgt["lookback_ok"] & np.isfinite(tgt["ml"])]
    L.assert_before_cutoff(tgt.index)
    # spot check against the live entry point on short prefixes
    rng = np.random.default_rng(1)
    checks = []
    for t in rng.choice(tgt.index, size=8, replace=False):
        t = pd.Timestamp(t)
        hist = frame[pd.to_datetime(frame["datetime_utc"], utc=True) < t].tail(30)
        r_ml = ampacity_forecast.forecast_ampacity(hist, method="ml")
        r_nv = ampacity_forecast.forecast_ampacity(hist, method="naive")
        checks.append(max(abs(r_ml.amps - tgt.loc[t, "ml"]), abs(r_nv.amps - tgt.loc[t, "naive"])))
    meta = {"rows_frame": int(len(frame)), "n_expected_targets": int(len(expected)),
            "n_missing_target": n_missing_target, "n_excluded_lookback_or_feature": n_lookback_bad,
            "spot_check_max_abs_diff_a": float(max(checks)),
            "truth_mean_a": float(tgt["truth"].mean()),
            "frame_first": str(frame["datetime_utc"].min()), "frame_last": str(frame["datetime_utc"].max())}
    return tgt, meta


def row(label, city, r, extra=None):
    out = {"scope": label, "city": city, "n": r["n"], "mae_naive": r.get("mae_naive"), "mae_ml": r.get("mae_ml"),
           "mean_d": r["mean_d"], "ci95_lo": r["ci_lo"], "ci95_hi": r["ci_hi"], "p_headline": r["p"]}
    if "p_by_L" in r:
        out.update({f"p_L{k}": v for k, v in r["p_by_L"].items()})
        out.update(p_dm_nw24=r.get("p_dm_nw24"), n_eff_acf=r.get("n_eff_acf"))
    else:
        out.update({f"p_L{k}": r["runs"].get(f"cluster_L{k}", {}).get("p") for k in L.BLOCKS})
    out.update(n_eff_boot=r.get("n_eff_boot"), mdd_a=r.get("mdd"))
    if extra:
        out.update(extra)
    return out


def main():
    data, meta = {}, {}
    for c in CITIES:
        data[c], meta[c] = errors(c)
        print(c, meta[c])
    for c in CITIES:
        t = data[c]
        t["e_ml"] = t["truth"] - t["ml"]
        t["e_naive"] = t["truth"] - t["naive"]
        t["d"] = t["e_naive"].abs() - t["e_ml"].abs()
        t.to_csv(os.path.join(HERE, f"part2_errors_{c}.csv"), index_label="target_time")

    rows = []
    res = {}
    for c in CITIES:
        t = data[c]
        r = L.per_city(t.index, t["d"].to_numpy())
        r["mae_ml"], r["mae_naive"] = float(t["e_ml"].abs().mean()), float(t["e_naive"].abs().mean())
        res[c] = r
    h = L.holm_adjust([res[c]["p"] for c in CITIES])
    for c, adj in zip(CITIES, h["adjusted"]):
        res[c]["p_holm"] = adj
        rows.append(row("full_2026-01-01_2026-09-29", c, res[c], {"p_holm": adj}))
    pool = L.pooled({c: (data[c].index, data[c]["d"].to_numpy()) for c in CITIES})
    pool["mae_ml"] = float(np.mean(np.concatenate([data[c]["e_ml"].abs() for c in CITIES])))
    pool["mae_naive"] = float(np.mean(np.concatenate([data[c]["e_naive"].abs() for c in CITIES])))
    rows.append(row("full_2026-01-01_2026-09-29", "POOLED", pool,
                    {"p_min_over_runs": pool["p_min"], "ci95_cluster_L24": pool["ci_cluster24"]}))
    pd.DataFrame(rows).round(4).to_csv(os.path.join(HERE, "part2_paired_tests.csv"), index=False)

    # per month
    mrows, mp = [], []
    for month in range(1, 10):
        frames = {}
        for c in CITIES:
            t = data[c][data[c].index.month == month]
            r = L.per_city(t.index, t["d"].to_numpy())
            r["mae_ml"], r["mae_naive"] = float(t["e_ml"].abs().mean()), float(t["e_naive"].abs().mean())
            mrows.append(row(f"2026-{month:02d}", c, r))
            mp.append(r["p"])
            frames[c] = (t.index, t["d"].to_numpy())
        pr = L.pooled(frames)
        pr["mae_ml"] = float(np.mean(np.concatenate([data[c][data[c].index.month == month]["e_ml"].abs() for c in CITIES])))
        pr["mae_naive"] = float(np.mean(np.concatenate([data[c][data[c].index.month == month]["e_naive"].abs() for c in CITIES])))
        mrows.append(row(f"2026-{month:02d}", "POOLED", pr))
    hm = L.holm_adjust(mp)
    k = 0
    for r in mrows:
        if r["city"] != "POOLED":
            r["p_holm_36"] = hm["adjusted"][k]
            k += 1
    pd.DataFrame(mrows).round(4).to_csv(os.path.join(HERE, "part2_monthly.csv"), index=False)

    with open(os.path.join(HERE, "part2_meta.json"), "w") as fh:
        json.dump({"label": L.LABEL, "fetch": [FETCH_START, FETCH_END], "score": [str(SCORE_START), str(SCORE_END)],
                   "cities": meta, "pooled_runs": {k2: {"p": v["p"], "ci": list(v["ci"])} for k2, v in pool["runs"].items()}},
                  fh, indent=2)
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).round(3).to_string())
    print(pd.DataFrame(mrows).round(3).to_string())


if __name__ == "__main__":
    main()
