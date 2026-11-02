"""
Part 1 -- exploratory, not pre-registered; does not change signed protocol v4 or read 1.
Paired ml vs naive on the p7 Sep 2026 offline replays. Reads only; writes only into this folder.
Run: PYTHONPATH=backend:docs/data-science/exploratory/2026-11-02_ml_vs_naive .venv/bin/python <this file>
"""
import json
import os

import numpy as np
import pandas as pd

import historical_archive
import real_data_validation as rdv
import stats_lib as L

HERE = os.path.dirname(os.path.abspath(__file__))
P = "data/historical/real_data_validation_2026-09-08_2026-09-28_replay_{m}_p7{s}"
START, END, WARM = "2026-09-08T00:00:00Z", "2026-09-28T23:00:00Z", 168.0
CITIES = ["AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"]


def load(method):
    steps = rdv.expected_steps(START, END, 1.0)
    trace = rdv.load_trace(P.format(m=method, s="_trace.jsonl"))
    L.assert_before_cutoff(trace["run_end_utc"])
    archive = historical_archive.read_history(path=P.format(m=method, s=".csv"), validate=True)
    frame = rdv.classify_steps(trace, archive, CITIES, steps, rdv._utc(START), WARM)
    L.assert_before_cutoff(frame["run_end_utc"])
    frame = frame[frame["period"] == "scored"].copy()
    for c in ("computed_a", "fc_amps", "fc_ci_lower", "fc_ci_upper", "g6_amps", "g6_ci_lower", "g6_ci_upper"):
        frame[c] = pd.to_numeric(frame.get(c), errors="coerce")
    frame["g6_eval"] = frame["outcome"].isin(("ok", "G6"))
    return frame.set_index(["city", "run_end_utc"])


def main():
    ml, nv = load("ml"), load("naive")
    j = ml.join(nv, lsuffix="_ml", rsuffix="_nv", how="inner")
    assert len(j) == 4 * 336
    both_comp = j["computed_a_ml"].notna() & j["computed_a_nv"].notna()
    comp_mismatch = int((both_comp & ((j["computed_a_ml"] - j["computed_a_nv"]).abs() > 1e-6)).sum())
    g6 = j["g6_eval_ml"] & j["g6_eval_nv"] & j["computed_a_ml"].notna()
    truth = j["computed_a_ml"]
    pops = {}
    # (a) ml actually forecast
    ma = g6 & (j["g6_forecast_method_ml"] == "ml") & j["fc_amps_nv"].notna()
    pops["a_ml_actually_forecast"] = (ma, "fc_amps_ml", "fc_amps_nv",
                                      ("fc_ci_lower_ml", "fc_ci_upper_ml"), ("fc_ci_lower_nv", "fc_ci_upper_nv"))
    # (b) as deployed
    mb = g6 & j["g6_amps_ml"].notna() & j["g6_amps_nv"].notna()
    pops["b_as_deployed"] = (mb, "g6_amps_ml", "g6_amps_nv",
                             ("g6_ci_lower_ml", "g6_ci_upper_ml"), ("g6_ci_lower_nv", "g6_ci_upper_nv"))
    # (c) README n_band population
    wml = j["fc_ci_upper_ml"] - j["fc_ci_lower_ml"]
    wnv = j["fc_ci_upper_nv"] - j["fc_ci_lower_nv"]
    mc = g6 & j["fc_amps_ml"].notna() & (wml > 0) & j["fc_amps_nv"].notna() & (wnv > 0)
    pops["c_readme_population"] = (mc, "fc_amps_ml", "fc_amps_nv",
                                   ("fc_ci_lower_ml", "fc_ci_upper_ml"), ("fc_ci_lower_nv", "fc_ci_upper_nv"))

    results = {"label": L.LABEL, "computed_a_mismatch_between_replays": comp_mismatch,
               "g6_evaluated_both": {c: int(g6.xs(c).sum()) for c in CITIES},
               "g6_method_counts_ml_replay": {c: j.xs(c)[g6.xs(c)]["g6_forecast_method_ml"].fillna("none").value_counts().to_dict() for c in CITIES},
               "populations": {}}
    rows, bands = [], []
    for name, (mask, cml, cnv, bml, bnv) in pops.items():
        sub = j[mask]
        e_ml = truth[mask] - sub[cml]
        e_nv = truth[mask] - sub[cnv]
        d = (e_nv.abs() - e_ml.abs())
        city_res, city_frames = {}, {}
        for c in CITIES:
            dc = d.xs(c)
            r = L.per_city(dc.index, dc.to_numpy())
            r["mae_ml"] = float(e_ml.xs(c).abs().mean())
            r["mae_naive"] = float(e_nv.xs(c).abs().mean())
            r["n_identical_centre"] = int((sub.xs(c)[cml] - sub.xs(c)[cnv]).abs().lt(1e-9).sum())
            city_res[c] = r
            city_frames[c] = (dc.index, dc.to_numpy())
            t = truth[mask].xs(c)
            s = sub.xs(c)
            for meth, (lo, hi), cc in (("ml", bml, cml), ("naive", bnv, cnv)):
                bands.append({"population": name, "city": c, "method": meth, "n": len(s),
                              "coverage": float(((t >= s[lo]) & (t <= s[hi])).mean()),
                              "width_mean_a": float((s[hi] - s[lo]).mean()),
                              "mae_a": float((t - s[cc]).abs().mean()),
                              "bias_a": float((t - s[cc]).mean())})
        h = L.holm_adjust([city_res[c]["p"] for c in CITIES])
        for c, adj, rej in zip(CITIES, h["adjusted"], h["rejected"]):
            city_res[c]["p_holm"] = adj
            city_res[c]["holm_rejected"] = rej
        pool = L.pooled(city_frames)
        pool["mae_ml"] = float(e_ml.abs().mean()); pool["mae_naive"] = float(e_nv.abs().mean())
        results["populations"][name] = {"per_city": city_res, "pooled": pool}
        for c in CITIES + ["POOLED"]:
            r = city_res[c] if c != "POOLED" else pool
            rows.append({
                "population": name, "city": c, "n": r["n"],
                "mae_naive": round(r["mae_naive"], 2), "mae_ml": round(r["mae_ml"], 2),
                "mean_d": round(r["mean_d"], 2),
                "ci95_lo": round(r["ci_lo"], 2), "ci95_hi": round(r["ci_hi"], 2),
                "p_L6": round(r["p_by_L"][6], 4) if c != "POOLED" else round(r["runs"]["cluster_L6"]["p"], 4),
                "p_L24": round(r["p_by_L"][24], 4) if c != "POOLED" else round(r["runs"]["cluster_L24"]["p"], 4),
                "p_L72": round(r["p_by_L"][72], 4) if c != "POOLED" else round(r["runs"]["cluster_L72"]["p"], 4),
                "p_headline": round(r["p"], 4),
                "p_holm": round(r["p_holm"], 4) if c != "POOLED" else None,
                "p_dm_nw24": round(r["p_dm_nw24"], 4) if c != "POOLED" else None,
                "n_eff_acf": round(r["n_eff_acf"], 1) if c != "POOLED" else None,
                "n_eff_boot": round(r["n_eff_boot"], 1),
                "mdd_a": round(r["mdd"], 2),
                "n_identical_centre": r.get("n_identical_centre"),
            })
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "part1_paired_tests.csv"), index=False)
    pd.DataFrame(bands).round(4).to_csv(os.path.join(HERE, "part1_band_coverage.csv"), index=False)
    with open(os.path.join(HERE, "part1_results.json"), "w") as fh:
        json.dump(results, fh, indent=2, default=lambda o: o if not isinstance(o, (np.floating, np.integer)) else o.item())
    print(pd.DataFrame(rows).to_string())
    print(pd.DataFrame(bands).round(3).to_string())
    print(json.dumps({k: results[k] for k in ("computed_a_mismatch_between_replays", "g6_evaluated_both", "g6_method_counts_ml_replay")}, indent=1))


if __name__ == "__main__":
    main()
