"""
Exploratory, not pre-registered; does not change signed protocol v4 or read 1.
Renders markdown tables from results_<basis>.json / descriptive_<basis>.csv into tables_<basis>.md.
    .venv/bin/python docs/data-science/exploratory/2026-11-02_horizon_comparison/tables.py
"""
import json
import os

import pandas as pd

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
SHORT = {"ml_cooling_corrected": "cooling", "ml_wind_corrected": "wind", "reference_ml_refit_24h": "reference",
         "raw_forecast": "raw", "persistence_24h": "persist24", "ml_60min": "ml60", "naive_60min": "naive60"}


def f(x, d=1):
    return "n/a" if x is None else f"{x:.{d}f}"


def fp(p):
    return "n/a" if p is None else (f"{p:.4f}" if p >= 0.0001 else "<0.0001")


def render(basis: str) -> str:
    res = json.load(open(os.path.join(OUT_DIR, f"results_{basis}.json")))
    desc = pd.read_csv(os.path.join(OUT_DIR, f"descriptive_{basis}.csv"))
    lines = [f"## Basis: {basis}", "", "### MAE per arm (amps; n = 784 per city, 3136 pooled)", ""]
    cities = list(dict.fromkeys(desc["city"]))
    arms = list(dict.fromkeys(desc["arm"]))
    lines.append("| arm | " + " | ".join(cities) + " |")
    lines.append("|---|" + "---|" * len(cities))
    for arm in arms:
        cells = []
        for c in cities:
            r = desc[(desc.city == c) & (desc.arm == arm)].iloc[0]
            cells.append(f"{r.mae:.1f} ({r.mae_pct_of_mean_truth:.1f}%)")
        lines.append(f"| {SHORT[arm]} | " + " | ".join(cells) + " |")
    lines += ["", "(MAE as % of the city's mean truth ampacity in brackets.)", "",
              "### Other descriptive metrics, pooled (amps)", "",
              "| arm | n | bias | RMSE | p95 abs err | over-prediction rate |", "|---|---|---|---|---|---|"]
    for arm in arms:
        r = desc[(desc.city == "POOLED") & (desc.arm == arm)].iloc[0]
        lines.append(f"| {SHORT[arm]} | {int(r.n)} | {r.bias:+.1f} | {r.rmse:.1f} | {r.p95_abs:.1f} | {r.overpred_rate:.3f} |")
    for fam, comps in res["families"].items():
        lines += ["", f"### Family {fam}: paired differences (margin = MAE_B − MAE_A; > 0 means A is better)", "",
                  "| A vs B | scope | n | MAE A | MAE B | margin (A) | 95% CI | % of mean truth | p | Holm p |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for cmp in comps:
            name = f"{SHORT[cmp['a']]} vs {SHORT[cmp['b']]}"
            p = cmp["pooled"]
            lines.append(f"| **{name}** | **pooled** | {p['n_paired']} | {f(p['mae_a'])} | {f(p['mae_b'])} | "
                         f"**{p['point_margin']:+.1f}** | [{f(p['ci95_widest'][0])}, {f(p['ci95_widest'][1])}] | "
                         f"{p['margin_pct_of_mean_truth']:+.1f}% | {fp(p['p_headline'])} | **{fp(p['p_holm'])}** |")
            for city, r in cmp["per_city"].items():
                lines.append(f"| {name} | {city} | {r['n_paired']} | {f(r['mae_a'])} | {f(r['mae_b'])} | "
                             f"{r['point_margin']:+.1f} | [{f(r['ci95_widest'][0])}, {f(r['ci95_widest'][1])}] | "
                             f"{r['margin_pct_of_mean_truth']:+.1f}% | {fp(r['p_max_over_L'])} | "
                             f"{fp(r['p_holm_within_city'])} |")
        lines += ["", "Pooled CI = widest 95% over both schemes and block lengths 1/4/8/28; pooled p = max over the same "
                  "(PD-04 style); Holm across the family's pooled tests. Per-city: 1-D moving-block bootstrap, CI widest "
                  "and p max over L; 'Holm p' for a city row is Holm within (family × city), descriptive.", "",
                  "Pooled by scheme (city-clustered two-stage is the conservative one with 4 cities):", "",
                  "| A vs B | joint-time p max | joint-time 95% CI | city-cluster p max | city-cluster 95% CI |",
                  "|---|---|---|---|---|"]
        for cmp in comps:
            p = cmp["pooled"]
            jc, cc = p.get("joint_time_block_ci95_widest", [None, None]), p.get("city_cluster_two_stage_ci95_widest", [None, None])
            lines.append(f"| {SHORT[cmp['a']]} vs {SHORT[cmp['b']]} | {fp(p.get('joint_time_block_p_max'))} | "
                         f"[{f(jc[0])}, {f(jc[1])}] | {fp(p.get('city_cluster_two_stage_p_max'))} | [{f(cc[0])}, {f(cc[1])}] |")
    return "\n".join(lines) + "\n"


for basis in ("production", "frozen-drake"):
    with open(os.path.join(OUT_DIR, f"tables_{basis}.md"), "w") as fh:
        fh.write("Exploratory, not pre-registered; does not change signed protocol v4 or read 1.\n\n" + render(basis))
print("ok")
