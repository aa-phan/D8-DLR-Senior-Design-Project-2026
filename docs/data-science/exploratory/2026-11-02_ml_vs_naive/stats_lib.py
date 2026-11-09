"""
Exploratory, not pre-registered; does not change signed protocol v4 or read 1.

Paired ml-vs-naive tests on an HOURLY grid, reusing the primitives of
backend/forecast_shadow_score_stats.py (imported, never modified).
d = |e_naive| - |e_ml|; positive = ml better.
"""
import numpy as np
import pandas as pd
from scipy import stats as sps

import config
import forecast_shadow_score_stats as S

CUTOFF = pd.Timestamp("2026-09-30T00:00:00Z")
BLOCKS = (6, 24, 72)
PRIMARY_L = 24
N_RESAMPLES = 10000
SEED = int(config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE)
ALPHA = 0.05
POWER = 0.8
LABEL = "exploratory, not pre-registered; does not change signed protocol v4 or read 1"


def assert_before_cutoff(times):
    t = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    if len(t):
        assert t.max() < CUTOFF, f"timestamp {t.max()} >= {CUTOFF}"


def _grid(times, diff, t0, t1):
    times = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    slots = np.rint(np.asarray((times - t0) / pd.Timedelta(hours=1), dtype=float)).astype(int)
    s = int(np.rint((t1 - t0) / pd.Timedelta(hours=1))) + 1
    ssum = np.zeros(s)
    scnt = np.zeros(s)
    np.add.at(ssum, slots, diff)
    np.add.at(scnt, slots, 1.0)
    return ssum, scnt


def newey_west_dm(diff, lag=24):
    d = np.asarray(diff, float)
    n = d.size
    if n < 3:
        return float("nan")
    x = d - d.mean()
    gamma0 = np.dot(x, x) / n
    v = gamma0
    for k in range(1, min(lag, n - 1) + 1):
        w = 1.0 - k / (lag + 1.0)
        v += 2.0 * w * np.dot(x[:-k], x[k:]) / n
    if v <= 0:
        return float("nan")
    z = d.mean() / np.sqrt(v / n)
    return float(2.0 * (1.0 - sps.norm.cdf(abs(z))))


def per_city(times, diff, alpha_mdd=ALPHA / 4):
    """Moving-block bootstrap on the city's own hourly grid (gaps kept as empty slots)."""
    order = np.argsort(pd.DatetimeIndex(pd.to_datetime(times, utc=True)).asi8)
    times = pd.DatetimeIndex(pd.to_datetime(times, utc=True))[order]
    diff = np.asarray(diff, float)[order]
    n = diff.size
    out = {"n": n, "mean_d": float(diff.mean()) if n else np.nan}
    if n < 8:
        out.update(ci_lo=np.nan, ci_hi=np.nan, p=np.nan, p_by_L={}, ci_by_L={})
        return out
    t0, t1 = times.min(), times.max()
    ssum, scnt = _grid(times, diff, t0, t1)
    span = ssum.size
    p_by_L, ci_by_L, sds = {}, {}, []
    for L in BLOCKS:
        if L > span / 2:
            continue
        means = S._gather_means_joint(ssum, scnt, L, N_RESAMPLES, SEED)
        means = means[np.isfinite(means)]
        p_by_L[L] = S.bootstrap_p_two_sided(means)
        ci_by_L[L] = S.percentile_interval(means, 0.95)
        sds.append(float(np.std(means, ddof=1)))
    se = max(sds)
    out.update(
        ci_lo=ci_by_L.get(PRIMARY_L, (np.nan, np.nan))[0],
        ci_hi=ci_by_L.get(PRIMARY_L, (np.nan, np.nan))[1],
        p_by_L=p_by_L, ci_by_L=ci_by_L, p=max(p_by_L.values()),
        se_boot=se, mdd=S.minimum_detectable_difference(se, alpha_mdd, POWER),
        n_eff_acf=S.acf_effective_n(diff),
        n_eff_boot=float(np.var(diff, ddof=1) / se ** 2) if se > 0 else np.nan,
        p_dm_nw24=newey_west_dm(diff, 24),
        span_h=int(span),
    )
    return out


def pooled(city_frames, alpha_mdd=ALPHA):
    """city_frames: {city: (times, diff)}. Two schemes x BLOCKS, headline p = max."""
    names = [c for c, (t, d) in city_frames.items() if len(d)]
    allt = pd.DatetimeIndex(np.concatenate([pd.DatetimeIndex(pd.to_datetime(city_frames[c][0], utc=True)).asi8 for c in names])).tz_localize("UTC")
    t0, t1 = allt.min(), allt.max()
    sums, cnts = [], []
    all_d = []
    for c in names:
        t, d = city_frames[c]
        a, b = _grid(t, np.asarray(d, float), t0, t1)
        sums.append(a); cnts.append(b); all_d.append(np.asarray(d, float))
    city_sum, city_cnt = np.vstack(sums), np.vstack(cnts)
    all_d = np.concatenate(all_d)
    span = city_sum.shape[1]
    res = {"n": int(all_d.size), "mean_d": float(all_d.mean()), "runs": {}}
    ps, los, his, sds = [], [], [], []
    for scheme in ("cluster", "joint"):
        for L in BLOCKS:
            if L > span / 2:
                continue
            if scheme == "joint":
                means = S._gather_means_joint(city_sum.sum(0), city_cnt.sum(0), L, N_RESAMPLES, SEED)
            else:
                means = S._gather_means_cluster(city_sum, city_cnt, L, N_RESAMPLES, SEED)
            means = means[np.isfinite(means)]
            p = S.bootstrap_p_two_sided(means)
            ci = S.percentile_interval(means, 0.95)
            sd = float(np.std(means, ddof=1))
            res["runs"][f"{scheme}_L{L}"] = {"p": p, "ci": ci, "sd": sd}
            ps.append(p); los.append(ci[0]); his.append(ci[1]); sds.append(sd)
    se = max(sds)
    res.update(p=max(ps), p_min=min(ps), ci_lo=min(los), ci_hi=max(his),
               ci_cluster24=res["runs"].get("cluster_L24", {}).get("ci"),
               se_boot=se, mdd=S.minimum_detectable_difference(se, alpha_mdd, POWER),
               n_eff_boot=float(np.var(all_d, ddof=1) / se ** 2) if se > 0 else np.nan)
    return res


def holm_adjust(pvals):
    return S.holm(pvals, alpha=ALPHA)
