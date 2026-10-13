"""
Statistics layer for the per-city evaluation (quick task 261013-285, S3):
frozen-equivalent moving-block bootstrap, ACF effective n, minimum detectable
difference, Holm step-down, the pooled joint-time-block and two-stage
city-cluster resamples on the six-hourly slot grid, and `build_family_report`
for the fixed 9-test headline family (amendment decision 2E).

Pure numpy/scipy: no file or network I/O. The 1-D moving-block bootstrap is
REIMPLEMENTED here, not imported, because the pooled slot-grid resamples need
index construction the frozen 1-D function cannot do, MDD and ESS need the
resample distribution, and runtime code must not import
`forecast_experiment_audit`. Exactness with the frozen
`paired_block_bootstrap_margin` (same RNG draws, same percentile interval) is
proven by a test-only equivalence in `forecast_shadow_score_stats_test.py`.

Conventions. A comparison is an ordered pair (A, B); the paired series is
`diff = |e_B| - |e_A|`, so a positive margin means A has the lower MAE. Pairing
is complete case per pair (a row needs both candidates scored and truth).
Headline pooled results are row-weighted (each scored (city, valid_time) counts
once). Per-city results are descriptive and uncorrected. Every figure is
reanalysis-derived, never sensor-validated.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as sps

import forecast_shadow_eval_core as core

SCHEME_JOINT = "joint_time_block"
SCHEME_CLUSTER = "city_cluster_two_stage"
_CLUSTER_CHUNK = 1000
LABEL_PER_CITY = "descriptive, uncorrected"


# --------------------------------------------------------------------------
# 1-D bootstrap primitives (frozen-equivalent)
# --------------------------------------------------------------------------

def moving_block_bootstrap_means(diff, block_length: int, n_resamples: int, seed: int) -> np.ndarray:
    """
    Resample means of a moving-block bootstrap over `diff`, drawing the SAME
    random numbers as `forecast_experiment_audit.paired_block_bootstrap_margin`
    (method="moving"): `rng = default_rng(seed)`; starts =
    `rng.integers(0, n - L + 1, size=(B, ceil(n / L)))`; indices = starts +
    arange(L), truncated to n. A zero-ptp (or empty) series is a point mass.
    """
    diff = np.asarray(diff, dtype=float)
    n = diff.size
    if not isinstance(block_length, (int, np.integer)) or isinstance(block_length, bool) or block_length < 1 or block_length > max(n, 1):
        raise ValueError(f"moving_block_bootstrap_means: block_length must be a positive integer no larger than the series length ({n}), got {block_length!r}")
    if n == 0 or np.ptp(diff) == 0.0:
        return np.full(int(n_resamples), float(np.mean(diff)) if n else 0.0)
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block_length))
    starts = rng.integers(0, n - block_length + 1, size=(n_resamples, n_blocks))
    idx = starts[:, :, None] + np.arange(block_length)[None, None, :]
    idx = idx.reshape(n_resamples, n_blocks * block_length)[:, :n]
    return diff[idx].mean(axis=1)


def percentile_interval(means, confidence: float = 0.95) -> tuple[float, float]:
    """Percentile interval at alpha/2 and 1 - alpha/2 (the frozen expression)."""
    means = np.asarray(means, dtype=float)
    alpha = 1.0 - confidence
    return (float(np.percentile(means, 100.0 * (alpha / 2.0))),
            float(np.percentile(means, 100.0 * (1.0 - alpha / 2.0))))


def bootstrap_p_two_sided(means) -> float:
    """min(1, 2 * min((#means <= 0 + 1)/(B + 1), (#means >= 0 + 1)/(B + 1)))."""
    means = np.asarray(means, dtype=float)
    b = means.size
    le = (int(np.sum(means <= 0.0)) + 1) / (b + 1)
    ge = (int(np.sum(means >= 0.0)) + 1) / (b + 1)
    return float(min(1.0, 2.0 * min(le, ge)))


def acf_effective_n(series) -> float:
    """
    ACF-based effective n of an ordered series: n / (1 + 2 * sum rho_k),
    summing from lag 1 and truncating at the first non-positive lag, capped at
    n/4 lags, clipped to [1, n]. Approximate for irregular spacing (log rows).
    """
    x = np.asarray(series, dtype=float)
    n = x.size
    if n < 2:
        return float(max(n, 1)) if n else 1.0
    x = x - x.mean()
    denom = float(np.sum(x * x))
    if denom == 0.0:
        return float(n)
    total = 0.0
    for k in range(1, max(1, n // 4) + 1):
        rho = float(np.sum(x[:-k] * x[k:])) / denom
        if rho <= 0.0:
            break
        total += rho
    return float(min(max(n / (1.0 + 2.0 * total), 1.0), float(n)))


def minimum_detectable_difference(se: float, alpha: float, power: float = core.POWER) -> float:
    """(z(1 - alpha/2) + z(power)) * SE."""
    return float((sps.norm.ppf(1.0 - alpha / 2.0) + sps.norm.ppf(power)) * se)


def rows_needed_for_margin(n: int, mdd: float, margin: float = core.DECISION_MARGIN_AMPS) -> int:
    """ceil(n * (mdd / margin)^2): the rows a margin-sized difference would need."""
    return int(math.ceil(n * (mdd / margin) ** 2))


def holm(pvalues, alpha: float = core.FAMILY_ALPHA) -> dict:
    """
    Holm step-down. Sorted ascending p(i) is rejected while p(i) <= alpha /
    (m - i + 1) (1-based i), stopping at the first failure. Adjusted p(i) =
    max over j <= i of min(1, (m - j + 1) * p(j)). A None or NaN p is 1.0.
    Results are returned in the input order.
    """
    p = np.array([1.0 if (v is None or not np.isfinite(v)) else float(v) for v in pvalues], dtype=float)
    m = p.size
    order = np.argsort(p, kind="stable")
    rejected = np.zeros(m, dtype=bool)
    adjusted = np.zeros(m, dtype=float)
    running = 0.0
    stopped = False
    for rank, idx in enumerate(order):
        scale = m - rank
        running = max(running, min(1.0, scale * p[idx]))
        adjusted[idx] = running
        if not stopped and p[idx] <= alpha / scale:
            rejected[idx] = True
        else:
            stopped = True
    return {"rejected": [bool(v) for v in rejected], "adjusted": [float(v) for v in adjusted],
            "alpha": float(alpha), "m": int(m)}


# --------------------------------------------------------------------------
# Per-city (descriptive, uncorrected)
# --------------------------------------------------------------------------

def _runnable(block_lengths, span: float):
    run = [int(L) for L in block_lengths if L <= span / 2.0]
    skipped = [int(L) for L in block_lengths if L > span / 2.0]
    return run, skipped


def per_city_comparison(diff, *, params: dict, alpha: float = core.FAMILY_ALPHA) -> dict:
    """
    One city's paired result over `diff = |e_B| - |e_A|` ordered by valid_time.
    1-D moving-block bootstrap at every runnable L (L <= n/2); 95% intervals,
    unadjusted. Labelled descriptive, uncorrected.
    """
    diff = np.asarray(diff, dtype=float)
    n = int(diff.size)
    out = {"n_paired": n, "label": LABEL_PER_CITY, "point_margin": float(np.mean(diff)) if n else None,
           "outcome": "insufficient_data", "reason": None, "block_lengths_run": [], "block_lengths_skipped": [],
           "ci95_by_block_length": {}, "se_boot": None, "mdd": None, "rows_needed_for_5A": None,
           "n_eff_acf": acf_effective_n(diff) if n else None}
    run, skipped = _runnable(params["block_lengths"], n)
    out["block_lengths_run"], out["block_lengths_skipped"] = run, skipped
    if n < params["min_paired_rows"]:
        out["reason"] = "fewer_than_min_paired_rows"
        return out
    if not any(L > 1 for L in run):
        out["reason"] = "no_block_length_above_1_runnable"
        return out
    sds = []
    favors_a, favors_b, any_excl = [], [], []
    for L in run:
        means = moving_block_bootstrap_means(diff, L, params["n_resamples"], params["seed"])
        lo, hi = percentile_interval(means, 0.95)
        out["ci95_by_block_length"][L] = [lo, hi]
        sds.append(float(np.std(means, ddof=1)))
        favors_a.append(lo > 0.0)
        favors_b.append(hi < 0.0)
        any_excl.append(lo > 0.0 or hi < 0.0)
    if all(favors_a):
        out["outcome"] = "favors_A"
    elif all(favors_b):
        out["outcome"] = "favors_B"
    else:
        out["outcome"] = "inconclusive"
        out["reason"] = "block_length_sensitive" if any(any_excl) else "crosses_zero"
    se = max(sds)
    out["se_boot"] = se
    out["mdd"] = minimum_detectable_difference(se, alpha, params["power"])
    out["rows_needed_for_5A"] = rows_needed_for_margin(n, out["mdd"], params.get("decision_margin_amps", core.DECISION_MARGIN_AMPS))
    return out


# --------------------------------------------------------------------------
# Pooled (headline)
# --------------------------------------------------------------------------

def _gather_means_joint(slot_sum, slot_cnt, L, n_resamples, seed):
    s = slot_sum.size
    n_blocks = int(np.ceil(s / L))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, s - L + 1, size=(n_resamples, n_blocks))
    idx = (starts[:, :, None] + np.arange(L)[None, None, :]).reshape(n_resamples, n_blocks * L)[:, :s]
    num = slot_sum[idx].sum(axis=1)
    den = slot_cnt[idx].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return num / den


def _gather_means_cluster(city_sum, city_cnt, L, n_resamples, seed):
    m, s = city_sum.shape
    n_blocks = int(np.ceil(s / L))
    rng = np.random.default_rng(seed)
    drawn = rng.integers(0, m, size=(n_resamples, m))
    starts = rng.integers(0, s - L + 1, size=(n_resamples, m, n_blocks))
    out = np.empty(n_resamples, dtype=float)
    for lo in range(0, n_resamples, _CLUSTER_CHUNK):
        hi = min(n_resamples, lo + _CLUSTER_CHUNK)
        idx = (starts[lo:hi, :, :, None] + np.arange(L)[None, None, None, :]).reshape(hi - lo, m, n_blocks * L)[:, :, :s]
        cd = drawn[lo:hi][:, :, None]
        num = city_sum[cd, idx].sum(axis=(1, 2))
        den = city_cnt[cd, idx].sum(axis=(1, 2))
        with np.errstate(invalid="ignore", divide="ignore"):
            out[lo:hi] = num / den
    return out


def _mean_cross_city_correlation(city_slot_diffs: dict) -> Optional[float]:
    names = list(city_slot_diffs)
    rhos = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = city_slot_diffs[names[i]], city_slot_diffs[names[j]]
            common = sorted(set(a) & set(b))
            if len(common) < 3:
                continue
            x = np.array([a[s] for s in common])
            y = np.array([b[s] for s in common])
            if np.ptp(x) == 0 or np.ptp(y) == 0:
                continue
            rhos.append(float(np.corrcoef(x, y)[0, 1]))
    return float(np.mean(rhos)) if rhos else None


def pooled_comparison(city_data: dict, *, params: dict, family_size: int = core.FAMILY_SIZE,
                      family_alpha: float = core.FAMILY_ALPHA) -> dict:
    """
    The pooled headline for one pair. `city_data[city] = (slot_idx, diff)`:
    integer slot positions on the six-hourly grid and the paired differences.
    The grid spans every slot from the earliest to the latest paired valid time
    across cities, empty slots included. Two schemes (S3): joint_time_block and
    city_cluster_two_stage, each at every L <= S/2. The headline p is the
    maximum over both schemes and every runnable L (PD-04).
    """
    names = [c for c in city_data if len(city_data[c][1])]
    all_diff = np.concatenate([np.asarray(city_data[c][1], dtype=float) for c in names]) if names else np.array([])
    n = int(all_diff.size)
    out = {"n_paired": n, "cities_with_data": len(names), "point_margin": float(all_diff.mean()) if n else None,
           "outcome": "insufficient_data", "reason": None, "p_headline": None, "ci95_widest": [None, None],
           "ci_bonferroni_widest": [None, None], "block_lengths_run": [], "block_lengths_skipped": [],
           "schemes": {SCHEME_JOINT: {}, SCHEME_CLUSTER: {}}, "se_boot": None, "mdd": None, "rows_needed_for_5A": None,
           "n_eff_bootstrap": None, "rho_bar": None, "analytic_design_effect_n": None, "n_degenerate_resamples": 0}
    if n == 0:
        out["reason"] = "no_paired_rows"
        return out
    slots_all = np.concatenate([np.asarray(city_data[c][0], dtype=int) for c in names])
    lo_slot, hi_slot = int(slots_all.min()), int(slots_all.max())
    s = hi_slot - lo_slot + 1
    run, skipped = _runnable(params["block_lengths"], s)
    out["block_lengths_run"], out["block_lengths_skipped"] = run, skipped
    out["n_slots"] = int(s)
    if n < params["min_paired_rows"]:
        out["reason"] = "fewer_than_min_paired_rows"
        return out
    if not any(L > 1 for L in run):
        out["reason"] = "no_block_length_above_1_runnable"
        return out

    city_sum = np.zeros((len(names), s))
    city_cnt = np.zeros((len(names), s))
    city_slot_diffs = {}
    for k, c in enumerate(names):
        sl = np.asarray(city_data[c][0], dtype=int) - lo_slot
        df = np.asarray(city_data[c][1], dtype=float)
        np.add.at(city_sum[k], sl, df)
        np.add.at(city_cnt[k], sl, 1.0)
        city_slot_diffs[c] = {int(a): float(b) for a, b in zip(sl, df)}
    slot_sum, slot_cnt = city_sum.sum(axis=0), city_cnt.sum(axis=0)

    bonf_conf = 1.0 - family_alpha / family_size
    ps, lows95, highs95, lowsb, highsb, sds, variances = [], [], [], [], [], [], []
    degenerate = 0
    for scheme in (SCHEME_JOINT, SCHEME_CLUSTER):
        for L in run:
            if scheme == SCHEME_JOINT:
                means = _gather_means_joint(slot_sum, slot_cnt, L, params["n_resamples"], params["seed"])
            else:
                means = _gather_means_cluster(city_sum, city_cnt, L, params["n_resamples"], params["seed"])
            finite = means[np.isfinite(means)]
            degenerate += int(means.size - finite.size)
            if finite.size == 0:
                continue
            ci95 = percentile_interval(finite, 0.95)
            cib = percentile_interval(finite, bonf_conf)
            p = bootstrap_p_two_sided(finite)
            sd = float(np.std(finite, ddof=1)) if finite.size > 1 else 0.0
            out["schemes"][scheme][L] = {"ci95": list(ci95), "ci_bonferroni": list(cib), "p": p, "sd": sd,
                                         "n_finite_resamples": int(finite.size)}
            ps.append(p); lows95.append(ci95[0]); highs95.append(ci95[1])
            lowsb.append(cib[0]); highsb.append(cib[1]); sds.append(sd); variances.append(sd ** 2)
    out["n_degenerate_resamples"] = degenerate
    if not ps:
        out["reason"] = "no_finite_resamples"
        return out
    out["p_headline"] = float(max(ps))
    out["p_min_over_runs"] = float(min(ps))
    out["ci95_widest"] = [float(min(lows95)), float(max(highs95))]
    out["ci_bonferroni_widest"] = [float(min(lowsb)), float(max(highsb))]
    out["se_boot"] = float(max(sds))
    out["mdd"] = minimum_detectable_difference(out["se_boot"], family_alpha / family_size, params["power"])
    out["rows_needed_for_5A"] = rows_needed_for_margin(n, out["mdd"], params.get("decision_margin_amps", core.DECISION_MARGIN_AMPS))
    var_max = max(variances)
    sample_var = float(np.var(all_diff, ddof=1)) if n > 1 else 0.0
    out["n_eff_bootstrap"] = float(sample_var / var_max) if var_max > 0 else None
    rho = _mean_cross_city_correlation(city_slot_diffs)
    out["rho_bar"] = rho
    if rho is not None and len(names) > 1:
        out["analytic_design_effect_n"] = float(n / (1.0 + (len(names) - 1) * rho))
    out["outcome"] = "pending_holm"
    return out


# --------------------------------------------------------------------------
# Family report
# --------------------------------------------------------------------------

def comparison_flags(a: str, b: str, row_source: str) -> list[str]:
    flags = []
    if row_source == core.LIVE_ROW_SOURCE:
        if a in ("ml_wind_corrected", "ml_cooling_corrected") or b in ("ml_wind_corrected", "ml_cooling_corrected"):
            flags.append(core.FLAG_V1)
        if "reference_ml_refit_24h" in (a, b):
            flags.append(core.FLAG_V2)
        if "persistence_24h" in (a, b):
            flags.append(core.FLAG_V3)
    flags.append(core.FLAG_V4)
    return flags


def _merge_params(params: Optional[dict]) -> dict:
    merged = core.default_params()
    if params:
        merged.update({k: v for k, v in params.items() if k in merged})
    merged["block_lengths"] = tuple(int(v) for v in merged["block_lengths"])
    return merged


def build_family_report(errors_by_city: dict, *, row_source: str, params: Optional[dict] = None) -> dict:
    """
    The fixed 9-test family for one row source. `errors_by_city[city]` is a
    DataFrame indexed by valid_time with one error column per candidate (NaN
    where not scored; signed or absolute, absolute values are taken here) and
    an optional `slot` column (default: the index). Complete case per pair.
    """
    if row_source not in core.ROW_SOURCES:
        raise ValueError(f"build_family_report: unknown row_source {row_source!r}")
    p = _merge_params(params)
    cities = list(errors_by_city)
    slot_hours = pd.Timedelta(hours=core.SLOT_HOURS)
    comparisons = []
    for a, b in core.HEADLINE_FAMILY:
        per_city, city_data, margins = {}, {}, {}
        n_total, sum_a, sum_b = 0, 0.0, 0.0
        for city in cities:
            frame = errors_by_city[city]
            if frame is None or len(frame) == 0 or a not in frame.columns or b not in frame.columns:
                sub = pd.DataFrame({a: [], b: []})
                slots = pd.DatetimeIndex([])
            else:
                sub = frame[[a, b]].dropna().sort_index()
                slot_col = frame["slot"] if "slot" in frame.columns else pd.Series(frame.index, index=frame.index)
                slots = pd.DatetimeIndex(slot_col.loc[sub.index])
            abs_a = np.abs(sub[a].to_numpy(dtype=float))
            abs_b = np.abs(sub[b].to_numpy(dtype=float))
            diff = abs_b - abs_a
            res = per_city_comparison(diff, params=p)
            res["mae_a"] = float(abs_a.mean()) if abs_a.size else None
            res["mae_b"] = float(abs_b.mean()) if abs_b.size else None
            per_city[city] = res
            margins[city] = res["point_margin"]
            city_data[city] = (slots, diff)
            n_total += int(diff.size)
            sum_a += float(abs_a.sum()); sum_b += float(abs_b.sum())
        all_slots = [s for sl, _ in city_data.values() for s in sl]
        if all_slots:
            t0 = min(all_slots)
            grid = {c: (np.array([int(round((s - t0) / slot_hours)) for s in sl], dtype=int), d)
                    for c, (sl, d) in city_data.items()}
        else:
            grid = {c: (np.array([], dtype=int), d) for c, (_, d) in city_data.items()}
        pooled = pooled_comparison(grid, params=p)
        with_data = [c for c in cities if margins[c] is not None]
        favoring = [c for c in with_data if margins[c] > 0.0]
        mae_a = sum_a / n_total if n_total else None
        mae_b = sum_b / n_total if n_total else None
        comparisons.append({
            "id": f"{a}__vs__{b}", "a": a, "b": b, "row_source": row_source,
            "flags": comparison_flags(a, b, row_source), "n_paired": n_total, "n_nominal": n_total,
            "point_margin": pooled["point_margin"], "mae_a": mae_a, "mae_b": mae_b,
            "relative_mae_reduction": (1.0 - mae_a / mae_b) if (mae_b not in (None, 0.0) and mae_a is not None) else None,
            "per_city_margins": margins, "cities_favoring_a": len(favoring), "cities_with_data": len(with_data),
            "headline": pooled, "per_city": per_city,
        })

    h = holm([c["headline"]["p_headline"] if c["headline"]["outcome"] != "insufficient_data" else None for c in comparisons],
             alpha=core.FAMILY_ALPHA)
    for c, rej, adj in zip(comparisons, h["rejected"], h["adjusted"]):
        head = c["headline"]
        head["p_holm_adjusted"] = adj
        head["holm_rejected"] = bool(rej and head["outcome"] != "insufficient_data")
        if head["outcome"] == "insufficient_data":
            continue
        if head["holm_rejected"]:
            head["outcome"] = "favors_A" if (head["point_margin"] or 0.0) > 0 else "favors_B"
            head["reason"] = None
        else:
            head["outcome"] = "inconclusive"
            head["reason"] = ("block_length_sensitive"
                              if head.get("p_min_over_runs") is not None and head["p_min_over_runs"] <= core.FAMILY_ALPHA / core.FAMILY_SIZE
                              else "crosses_zero")

    n_scored = {city: {name: int(errors_by_city[city][name].notna().sum()) if (errors_by_city[city] is not None and len(errors_by_city[city]) and name in errors_by_city[city].columns) else 0
                       for name in core.CANDIDATES} for city in cities}
    pairs = []
    for c in comparisons:
        h_ = c["headline"]
        pairs.append({
            "a": c["a"], "b": c["b"], "n_paired": c["n_paired"], "n_eff_bootstrap": h_["n_eff_bootstrap"],
            "n_eff_acf_by_city": {city: c["per_city"][city]["n_eff_acf"] for city in cities},
            "rho_bar": h_["rho_bar"], "analytic_design_effect_n": h_["analytic_design_effect_n"],
            "mdd": h_["mdd"], "rows_needed_for_5A": h_["rows_needed_for_5A"],
            "per_city_n_paired": {city: c["per_city"][city]["n_paired"] for city in cities},
            "targets": core.precision_targets(c["n_paired"]),
        })
    return {
        "row_source": row_source,
        "family_size": core.FAMILY_SIZE,
        "params": {**{k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()}, "family_alpha": core.FAMILY_ALPHA},
        "comparisons": comparisons,
        "holm": h,
        "per_city_label": LABEL_PER_CITY,
        "sample_size": {"n_scored": n_scored, "pairs": pairs,
                        "targets_met": {"tail_rate_590": [f"{x['a']} vs {x['b']}" for x in pairs if x["targets"]["tail_rate_target_met"]],
                                        "mdd_1575": [f"{x['a']} vs {x['b']}" for x in pairs if x["targets"]["mdd_target_met"]]}},
    }
