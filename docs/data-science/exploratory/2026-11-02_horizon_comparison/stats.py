"""
Exploratory, not pre-registered; does not change signed protocol v4 or read 1.

Paired statistics for the horizon comparison (PLAN.md), reusing forecast_shadow_score_stats (not modified).
Reads rows_<basis>.csv written by build_rows.py; writes results_<basis>.json and descriptive_<basis>.csv here.

    PYTHONPATH=backend .venv/bin/python docs/data-science/exploratory/2026-11-02_horizon_comparison/stats.py
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

import forecast_shadow_eval_core as core
import forecast_shadow_score_stats as st

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
CUTOFF = pd.Timestamp("2026-09-30T00:00:00Z")
PARAMS = core.default_params()          # block lengths 1/4/8/28, 10 000 resamples, seed 20260929, min rows 8
BLOCKS = tuple(int(x) for x in PARAMS["block_lengths"])

COOL, WIND, REF, RAW, PERS = ("ml_cooling_corrected", "ml_wind_corrected", "reference_ml_refit_24h",
                              "raw_forecast", "persistence_24h")
ML60, NAIVE60 = "ml_60min", "naive_60min"
ARMS = (ML60, NAIVE60, COOL, WIND, REF, RAW, PERS)
FAMILIES = {
    "A": [(COOL, REF), (WIND, REF), (COOL, RAW), (WIND, RAW), (COOL, PERS), (WIND, PERS)],
    "B": [(ML60, COOL), (ML60, WIND), (ML60, REF), (ML60, RAW), (ML60, PERS), (ML60, NAIVE60), (NAIVE60, COOL)],
}


def descriptive(rows: pd.DataFrame) -> pd.DataFrame:
    out = []
    for city, g in list(rows.groupby("city", sort=False)) + [("POOLED", rows)]:
        mean_truth = float(g["truth_amps"].mean())
        for arm in ARMS:
            sub = g[[arm, "truth_amps"]].dropna()
            e = sub[arm].to_numpy() - sub["truth_amps"].to_numpy()
            out.append({"city": city, "arm": arm, "n": len(e), "mae": np.mean(np.abs(e)), "bias": np.mean(e),
                        "rmse": np.sqrt(np.mean(e ** 2)), "p95_abs": np.percentile(np.abs(e), 95),
                        "overpred_rate": np.mean(e > 0), "mean_truth": mean_truth,
                        "mae_pct_of_mean_truth": 100 * np.mean(np.abs(e)) / mean_truth})
    return pd.DataFrame(out)


def per_city_test(diff: np.ndarray) -> dict:
    res = st.per_city_comparison(diff, params=PARAMS)
    ps, los, his = [], [], []
    for L in res["block_lengths_run"]:
        means = st.moving_block_bootstrap_means(diff, L, PARAMS["n_resamples"], PARAMS["seed"])
        ps.append(st.bootstrap_p_two_sided(means))
        lo, hi = st.percentile_interval(means, 0.95)
        los.append(lo); his.append(hi)
    res["p_max_over_L"] = float(max(ps)) if ps else None
    res["ci95_widest"] = [float(min(los)), float(max(his))] if los else [None, None]
    return res


def run_family(rows: pd.DataFrame, pairs, cities) -> list:
    slot_h = pd.Timedelta(hours=core.SLOT_HOURS)
    t0 = rows["valid_time"].min()
    results = []
    for a, b in pairs:
        per_city, grid = {}, {}
        all_a, all_b = [], []
        for city in cities:
            g = rows[rows["city"] == city].sort_values("valid_time")
            sub = g[["valid_time", "truth_amps", a, b]].dropna()
            ea = np.abs(sub[a].to_numpy() - sub["truth_amps"].to_numpy())
            eb = np.abs(sub[b].to_numpy() - sub["truth_amps"].to_numpy())
            diff = eb - ea
            r = per_city_test(diff)
            mt = float(sub["truth_amps"].mean())
            r.update({"mae_a": float(ea.mean()), "mae_b": float(eb.mean()), "mean_truth": mt,
                      "margin_pct_of_mean_truth": 100 * float(diff.mean()) / mt,
                      "ratio_mae_b_over_a": float(eb.mean() / ea.mean())})
            per_city[city] = r
            slots = np.array([int(round((t - t0) / slot_h)) for t in sub["valid_time"]], dtype=int)
            grid[city] = (slots, diff)
            all_a.append(ea); all_b.append(eb)
        pooled = st.pooled_comparison(grid, params=PARAMS, family_size=len(pairs))
        ea, eb = np.concatenate(all_a), np.concatenate(all_b)
        mt = float(rows["truth_amps"].mean())
        pooled.update({"mae_a": float(ea.mean()), "mae_b": float(eb.mean()),
                       "margin_pct_of_mean_truth": 100 * float((eb - ea).mean()) / mt,
                       "ratio_mae_b_over_a": float(eb.mean() / ea.mean())})
        # Scheme-specific widest CI / max p (cluster scheme reported separately as the conservative one).
        for scheme in (st.SCHEME_JOINT, st.SCHEME_CLUSTER):
            runs = pooled["schemes"][scheme]
            if runs:
                pooled[f"{scheme}_p_max"] = max(v["p"] for v in runs.values())
                pooled[f"{scheme}_ci95_widest"] = [min(v["ci95"][0] for v in runs.values()),
                                                   max(v["ci95"][1] for v in runs.values())]
        results.append({"a": a, "b": b, "pooled": pooled, "per_city": per_city})
    h = st.holm([r["pooled"]["p_headline"] for r in results])
    for r, rej, adj in zip(results, h["rejected"], h["adjusted"]):
        r["pooled"]["p_holm"] = adj
        r["pooled"]["holm_rejected"] = rej
    for city in cities:   # secondary: Holm within (family x city)
        hc = st.holm([r["per_city"][city]["p_max_over_L"] for r in results])
        for r, rej, adj in zip(results, hc["rejected"], hc["adjusted"]):
            r["per_city"][city]["p_holm_within_city"] = adj
            r["per_city"][city]["holm_rejected_within_city"] = rej
    return results


def main() -> int:
    for basis in ("production", "frozen-drake"):
        rows = pd.read_csv(os.path.join(OUT_DIR, f"rows_{basis}.csv"))
        for col in ("valid_time", "anchor_time"):
            rows[col] = pd.to_datetime(rows[col], utc=True)
            assert rows[col].max() < CUTOFF
        cities = list(dict.fromkeys(rows["city"]))
        desc = descriptive(rows)
        desc.to_csv(os.path.join(OUT_DIR, f"descriptive_{basis}.csv"), index=False)
        res = {"label": "exploratory, not pre-registered; does not change signed protocol v4 or read 1",
               "basis": basis, "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in PARAMS.items()},
               "families": {}}
        for fam, pairs in FAMILIES.items():
            res["families"][fam] = run_family(rows, pairs, cities)
        if basis == "frozen-drake":
            # AUSTIN is not comparable for B under frozen-drake (ml trained on the production conductor):
            # re-run family B on the three parity cities only.
            three = [c for c in cities if c != "AUSTIN"]
            res["families"]["B_three_parity_cities"] = run_family(rows[rows["city"].isin(three)], FAMILIES["B"], three)
        with open(os.path.join(OUT_DIR, f"results_{basis}.json"), "w") as fh:
            json.dump(res, fh, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
        print(f"done {basis}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
