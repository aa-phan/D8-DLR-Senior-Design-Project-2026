"""
Tests for `backend/forecast_shadow_score_stats.py` (quick task 261013-285,
Task 2). Synthetic series only. The frozen
`forecast_experiment_audit.paired_block_bootstrap_margin` is imported here, and
only here, as the exact-equivalence oracle; runtime code never imports it.

LONG STEP: the pooled and family tests resample thousands of times (a few
seconds each).
"""

from __future__ import annotations

import ast
import math
import os

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

import forecast_experiment_audit
import forecast_shadow_eval_core as core
import forecast_shadow_score_stats as st

SEED = core.SEED
CITIES = ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")


def ar1(n, phi, seed, scale=1.0):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    eps = rng.normal(size=n) * scale
    for t in range(1, n):
        x[t] = phi * x[t - 1] + eps[t]
    return x


def small_params(**kw):
    p = {**core.default_params(), "n_resamples": 1000}
    p.update(kw)
    return p


# --------------------------------------------------------------------------
# Exact equivalence with the frozen bootstrap
# --------------------------------------------------------------------------

@pytest.mark.parametrize("L", [1, 4, 8, 28])
def test_moving_block_bootstrap_equals_the_frozen_function_exactly(L):
    n = 120
    e_a = 50.0 + ar1(n, 0.6, 1)
    e_b = 50.0 + 2.0 + ar1(n, 0.6, 2)
    frozen = forecast_experiment_audit.paired_block_bootstrap_margin(
        errors_arm=e_a, errors_baseline=e_b, block_length=L, method="moving", n_resamples=2000,
        confidence_level=0.95, random_state=SEED)
    diff = np.abs(e_b) - np.abs(e_a)
    means = st.moving_block_bootstrap_means(diff, L, 2000, SEED)
    lo, hi = st.percentile_interval(means, 0.95)
    assert float(np.mean(diff)) == frozen["point"]
    assert lo == frozen["ci_low"] and hi == frozen["ci_high"]


def test_zero_ptp_series_is_a_point_mass_like_the_frozen_function():
    e = np.full(30, 40.0)
    frozen = forecast_experiment_audit.paired_block_bootstrap_margin(
        errors_arm=e, errors_baseline=e + 3.0, block_length=4, method="moving", n_resamples=500,
        confidence_level=0.95, random_state=SEED)
    diff = np.abs(e + 3.0) - np.abs(e)
    means = st.moving_block_bootstrap_means(diff, 4, 500, SEED)
    assert np.all(means == means[0]) and st.percentile_interval(means) == (frozen["ci_low"], frozen["ci_high"]) == (3.0, 3.0)
    assert st.bootstrap_p_two_sided(means) == pytest.approx(2 / 501)           # a constant positive margin
    assert st.bootstrap_p_two_sided(np.zeros(500)) == 1.0


def test_block_length_longer_than_the_series_is_refused():
    with pytest.raises(ValueError):
        st.moving_block_bootstrap_means(np.arange(5.0), 6, 100, SEED)
    with pytest.raises(ValueError):
        st.moving_block_bootstrap_means(np.arange(5.0), 0, 100, SEED)


def test_bootstrap_p_two_sided_formula():
    means = np.array([-1.0, 0.5, 1.0, 2.0, 3.0])
    assert st.bootstrap_p_two_sided(means) == pytest.approx(min(1.0, 2 * min((1 + 1) / 6, (4 + 1) / 6)))
    assert st.bootstrap_p_two_sided(np.array([1.0, 2.0, 3.0])) == pytest.approx(2 * (0 + 1) / 4)
    assert st.bootstrap_p_two_sided(np.array([-1.0, 1.0])) == 1.0


# --------------------------------------------------------------------------
# ACF effective n, MDD
# --------------------------------------------------------------------------

def test_acf_effective_n_iid_and_ar1():
    iid = np.random.default_rng(3).normal(size=2000)
    assert 0.85 <= st.acf_effective_n(iid) / 2000 <= 1.15
    phi = 0.6
    ratio = st.acf_effective_n(ar1(4000, phi, 4)) / 4000
    assert abs(ratio - (1 - phi) / (1 + phi)) < 0.07


def test_acf_effective_n_is_clipped_and_handles_degenerate_input():
    assert st.acf_effective_n(np.arange(200.0)) >= 1.0                       # strong trend
    assert st.acf_effective_n(np.arange(200.0)) <= 200.0
    assert st.acf_effective_n(np.ones(10)) == 10.0                            # zero variance
    assert st.acf_effective_n([]) == 1.0
    assert st.acf_effective_n([3.0]) == 1.0
    alt = np.array([1.0, -1.0] * 50)
    assert st.acf_effective_n(alt) == 100.0                                   # negative lag 1: no inflation


def test_mdd_and_rows_needed():
    se = 3.2
    for alpha in (0.05, 0.05 / 9):
        assert st.minimum_detectable_difference(se, alpha) == pytest.approx((sps.norm.ppf(1 - alpha / 2) + sps.norm.ppf(0.8)) * se)
    mdd = st.minimum_detectable_difference(se, 0.05)
    assert mdd == pytest.approx((1.959964 + 0.841621) * se, rel=1e-5)
    assert st.rows_needed_for_margin(100, mdd) == math.ceil(100 * (mdd / 5.0) ** 2)
    assert st.rows_needed_for_margin(100, 5.0) == 100
    assert st.rows_needed_for_margin(100, 5.0000001) == 101                  # ceil


# --------------------------------------------------------------------------
# Holm
# --------------------------------------------------------------------------

def test_holm_matches_a_hand_step_down():
    p = [0.0004, 0.2, 0.004, 0.0061, 0.03, 0.9, 0.0057, 0.5, 0.012]
    res = st.holm(p)
    # sorted: .0004 .004 .0057 .0061 .012 .03 .2 .5 .9 ; thresholds .05/9 .05/8 .05/7 .05/6 .05/5 ...
    #   .0004<=.00556 yes; .004<=.00625 yes; .0057<=.00714 yes; .0061<=.00833 yes; .012<=.01 no -> stop
    assert [p[i] for i in range(9) if res["rejected"][i]] == [0.0004, 0.004, 0.0061, 0.0057]
    adj_sorted = []
    running = 0.0
    for rank, v in enumerate(sorted(p)):
        running = max(running, min(1.0, (9 - rank) * v))
        adj_sorted.append(running)
    by_p = {pv: a for pv, a in zip(sorted(p), adj_sorted)}
    assert res["adjusted"] == pytest.approx([by_p[v] for v in p])
    assert all(a2 >= a1 for a1, a2 in zip(adj_sorted, adj_sorted[1:]))           # monotone
    assert res["m"] == 9


def test_holm_none_is_one_and_equal_p_values_step_by_step():
    res = st.holm([None, 0.001, float("nan")] + [0.004] * 6)
    assert res["rejected"][1] is True and res["rejected"][0] is False and res["rejected"][2] is False
    assert res["adjusted"][0] == 1.0 and res["adjusted"][2] == 1.0
    res = st.holm([0.004] * 9)
    # first threshold 0.05/9 = 0.00556 passes, the next 0.05/8 = 0.00625 passes ... all pass 0.004 <= 0.05/(9-i)
    assert all(res["rejected"])
    res = st.holm([0.006] * 9)
    # 0.006 > 0.05/9 = 0.00556: the first step fails, so nothing is rejected
    assert not any(res["rejected"])
    mixed = st.holm([0.004] * 3 + [0.0075] * 6)
    # steps: .004<=.00556, .004<=.00625, .004<=.00714, then .0075 > .05/6=.00833? no: .0075<=.00833 yes; .0075<=.01 ...
    assert all(mixed["rejected"])
    stop = st.holm([0.004] * 3 + [0.0084] + [0.5] * 5)
    assert stop["rejected"] == [True] * 3 + [False] * 6


# --------------------------------------------------------------------------
# Per-city and pooled
# --------------------------------------------------------------------------

def test_per_city_comparison_outcomes_and_skipped_block_lengths():
    rng = np.random.default_rng(5)
    diff = 8.0 + rng.normal(size=60)
    res = st.per_city_comparison(diff, params=small_params())
    assert res["outcome"] == "favors_A" and res["block_lengths_run"] == [1, 4, 8, 28] and res["label"] == "descriptive, uncorrected"
    res = st.per_city_comparison(-diff, params=small_params())
    assert res["outcome"] == "favors_B"
    res = st.per_city_comparison(rng.normal(size=60), params=small_params())
    assert res["outcome"] == "inconclusive" and res["reason"] in ("crosses_zero", "block_length_sensitive")
    short = st.per_city_comparison(8.0 + rng.normal(size=20), params=small_params())
    assert short["block_lengths_run"] == [1, 4, 8] and short["block_lengths_skipped"] == [28]
    tiny = st.per_city_comparison(8.0 + rng.normal(size=7), params=small_params())
    assert tiny["outcome"] == "insufficient_data" and tiny["reason"] == "fewer_than_min_paired_rows"
    only_one = st.per_city_comparison(8.0 + rng.normal(size=10), params=small_params(block_lengths=(1, 28)))
    assert only_one["outcome"] == "insufficient_data" and only_one["reason"] == "no_block_length_above_1_runnable"
    assert res["mdd"] > 0 and res["rows_needed_for_5A"] >= 1 and res["n_eff_acf"] <= 60


def test_per_city_block_length_sensitivity_is_named():
    n = 120
    d = 2.5 + 10.0 * np.sin(2 * np.pi * np.arange(n) / 60.0)
    res = st.per_city_comparison(d, params=small_params(n_resamples=2000))
    lo1, hi1 = res["ci95_by_block_length"][1]
    lo28, _ = res["ci95_by_block_length"][28]
    assert lo1 > 0 and lo28 < 0
    assert res["outcome"] == "inconclusive" and res["reason"] == "block_length_sensitive"


def _pooled(diffs_by_city, **kw):
    data = {c: (np.arange(len(d)), np.asarray(d, dtype=float)) for c, d in diffs_by_city.items()}
    return st.pooled_comparison(data, params=small_params(**kw))


def test_pooled_identical_cities_do_not_count_four_times():
    d = 3.0 + ar1(120, 0.3, 11, scale=6.0)
    one = _pooled({"A": d})
    four = _pooled({c: d for c in CITIES})
    assert four["n_paired"] == 480
    assert abs(four["n_eff_bootstrap"] / one["n_eff_bootstrap"] - 1.0) < 0.15
    assert four["n_eff_bootstrap"] < 1.5 * one["n_eff_bootstrap"]               # never about 4x
    assert four["rho_bar"] == pytest.approx(1.0)
    assert four["analytic_design_effect_n"] == pytest.approx(480 / 4.0)


def test_pooled_independent_cities_count_about_four_times():
    base = 1.0 + np.random.default_rng(21).normal(size=150) * 5.0
    one = _pooled({"A": base})
    four = _pooled({c: 1.0 + np.random.default_rng(30 + k).normal(size=150) * 5.0 for k, c in enumerate(CITIES)})
    ratio = four["n_eff_bootstrap"] / one["n_eff_bootstrap"]
    assert 3.0 <= ratio <= 5.0                                                   # about 4x, within 25%
    assert abs(four["rho_bar"]) < 0.15 and four["analytic_design_effect_n"] == pytest.approx(600 / (1 + 3 * four["rho_bar"]))


def test_pooled_opposite_city_effects_are_inconclusive():
    rng = np.random.default_rng(8)
    data = {"AUSTIN": 20.0 + rng.normal(size=60), "CORPUS_CHRISTI": 20.0 + rng.normal(size=60),
            "MIDLAND": -20.0 + rng.normal(size=60), "EL_PASO": -20.0 + rng.normal(size=60)}
    res = _pooled(data)
    assert abs(res["point_margin"]) < 1.0
    assert res["p_headline"] > 0.2


def test_pooled_handles_empty_slots_and_skips_long_blocks():
    slots = np.array([0, 1, 2, 3, 20, 21, 22, 23, 24, 25])                       # a 16-slot gap of empty slots
    d = np.array([5.0, 6, 4, 5, 6, 5, 4, 6, 5, 5]) + np.arange(10) * 0.1
    res = st.pooled_comparison({"A": (slots, d), "B": (slots + 1, d + 1.0)}, params=small_params())
    assert res["n_slots"] == 27 and res["block_lengths_run"] == [1, 4, 8] and res["block_lengths_skipped"] == [28]
    assert res["outcome"] == "pending_holm" and np.isfinite(res["p_headline"])
    assert set(res["schemes"][st.SCHEME_JOINT]) == {1, 4, 8} and set(res["schemes"][st.SCHEME_CLUSTER]) == {1, 4, 8}
    assert res["n_degenerate_resamples"] >= 0


def test_pooled_insufficient_data_cases():
    assert st.pooled_comparison({}, params=small_params())["reason"] == "no_paired_rows"
    res = _pooled({"A": np.arange(7.0)})
    assert res["outcome"] == "insufficient_data" and res["reason"] == "fewer_than_min_paired_rows" and res["p_headline"] is None
    res = st.pooled_comparison({"A": (np.arange(10), np.arange(10.0))}, params=small_params(block_lengths=(1, 40)))
    assert res["reason"] == "no_block_length_above_1_runnable"


def test_pooled_same_seed_gives_byte_identical_json():
    d = 2.0 + ar1(80, 0.4, 5, scale=4.0)
    a = core.dumps(_pooled({c: d + k for k, c in enumerate(CITIES)}))
    b = core.dumps(_pooled({c: d + k for k, c in enumerate(CITIES)}))
    assert a == b
    c = core.dumps(_pooled({c: d + k for k, c in enumerate(CITIES)}, seed=SEED + 1))
    assert a != c


def test_pooled_headline_p_is_the_maximum_over_schemes_and_block_lengths():
    n = 120
    d = 5.0 + 10.0 * np.sin(2 * np.pi * np.arange(n) / 60.0)                   # significant at L=1 only
    res = _pooled({"A": d}, n_resamples=2000)
    ps = [v["p"] for scheme in res["schemes"].values() for v in scheme.values()]
    assert res["p_headline"] == max(ps) and res["p_min_over_runs"] == min(ps)
    assert res["schemes"][st.SCHEME_JOINT][1]["p"] < core.FAMILY_ALPHA / core.FAMILY_SIZE
    assert res["p_headline"] > core.FAMILY_ALPHA / core.FAMILY_SIZE
    widths = [v["ci95"][1] - v["ci95"][0] for scheme in res["schemes"].values() for v in scheme.values()]
    assert res["ci95_widest"][1] - res["ci95_widest"][0] >= max(widths) - 1e-12
    assert res["mdd"] == pytest.approx(st.minimum_detectable_difference(res["se_boot"], 0.05 / 9, 0.8))
    assert res["se_boot"] == max(v["sd"] for scheme in res["schemes"].values() for v in scheme.values())


# --------------------------------------------------------------------------
# Family report
# --------------------------------------------------------------------------

def make_frames(n=100, seed=0, scales=None, cities=CITIES, start="2026-04-01T00:00:00Z", nan_rules=None):
    scales = scales or {"ml_wind_corrected": 20.0, "ml_cooling_corrected": 25.0, "reference_ml_refit_24h": 30.0,
                        "raw_forecast": 40.0, "persistence_24h": 60.0}
    frames = {}
    for k, city in enumerate(cities):
        rng = np.random.default_rng(seed + k)
        idx = pd.date_range(start, periods=n, freq="6h")
        frame = pd.DataFrame({name: rng.normal(size=n) * s for name, s in scales.items()}, index=idx)
        frame["slot"] = idx
        for (c, col), keep in (nan_rules or {}).items():
            if c == city:
                frame.loc[frame.index[keep:], col] = np.nan
        frames[city] = frame
    return frames


def test_build_family_report_has_exactly_the_nine_pairs_with_row_source_and_flags():
    rep = st.build_family_report(make_frames(), row_source="shadow_logs", params=small_params())
    comps = rep["comparisons"]
    assert [(c["a"], c["b"]) for c in comps] == list(core.HEADLINE_FAMILY) and rep["family_size"] == 9
    assert all(c["row_source"] == "shadow_logs" for c in comps)
    by = {(c["a"], c["b"]): c for c in comps}
    assert by[("ml_wind_corrected", "ml_cooling_corrected")]["flags"] == [core.FLAG_V1, core.FLAG_V4]
    assert by[("ml_wind_corrected", "reference_ml_refit_24h")]["flags"] == [core.FLAG_V1, core.FLAG_V2, core.FLAG_V4]
    assert by[("reference_ml_refit_24h", "raw_forecast")]["flags"] == [core.FLAG_V2, core.FLAG_V4]
    assert by[("ml_wind_corrected", "persistence_24h")]["flags"] == [core.FLAG_V1, core.FLAG_V3, core.FLAG_V4]
    assert by[("reference_ml_refit_24h", "persistence_24h")]["flags"] == [core.FLAG_V2, core.FLAG_V3, core.FLAG_V4]
    rec = st.build_family_report(make_frames(), row_source="reconstructed_frames", params=small_params())
    assert all(c["flags"] == [core.FLAG_V4] and c["row_source"] == "reconstructed_frames" for c in rec["comparisons"])
    assert rep["holm"]["m"] == 9 and len(rep["holm"]["adjusted"]) == 9


def test_family_per_city_entries_are_labelled_uncorrected_and_margins_match_numpy():
    frames = make_frames(n=80, seed=3)
    rep = st.build_family_report(frames, row_source="reconstructed_frames", params=small_params())
    entry = next(c for c in rep["comparisons"] if (c["a"], c["b"]) == ("ml_wind_corrected", "raw_forecast"))
    assert all(v["label"] == "descriptive, uncorrected" for v in entry["per_city"].values())
    expected = {c: float(np.mean(np.abs(f["raw_forecast"]) - np.abs(f["ml_wind_corrected"]))) for c, f in frames.items()}
    for c in CITIES:
        assert entry["per_city_margins"][c] == pytest.approx(expected[c], abs=1e-9)
        assert entry["per_city"][c]["point_margin"] == pytest.approx(expected[c], abs=1e-9)
    pooled_expected = np.mean(np.concatenate([np.abs(f["raw_forecast"]) - np.abs(f["ml_wind_corrected"]) for f in frames.values()]))
    assert entry["point_margin"] == pytest.approx(pooled_expected, abs=1e-9)           # row-weighted
    mae_a = np.mean(np.concatenate([np.abs(f["ml_wind_corrected"]) for f in frames.values()]))
    mae_b = np.mean(np.concatenate([np.abs(f["raw_forecast"]) for f in frames.values()]))
    assert entry["relative_mae_reduction"] == pytest.approx(1 - mae_a / mae_b, abs=1e-12)
    assert entry["cities_favoring_a"] == sum(v > 0 for v in expected.values()) and entry["cities_with_data"] == 4
    assert entry["n_paired"] == entry["n_nominal"] == 320
    assert entry["headline"]["outcome"] == "favors_A" and entry["headline"]["holm_rejected"] is True
    assert entry["headline"]["p_holm_adjusted"] <= core.FAMILY_ALPHA


def test_family_complete_case_pairing_drops_rows_per_pair_only():
    frames = make_frames(n=60, seed=7, nan_rules={("AUSTIN", "persistence_24h"): 20, ("MIDLAND", "ml_cooling_corrected"): 30})
    rep = st.build_family_report(frames, row_source="shadow_logs", params=small_params())
    by = {(c["a"], c["b"]): c for c in rep["comparisons"]}
    assert by[("ml_wind_corrected", "raw_forecast")]["n_paired"] == 240
    assert by[("ml_wind_corrected", "persistence_24h")]["n_paired"] == 240 - 40
    assert by[("ml_wind_corrected", "persistence_24h")]["per_city"]["AUSTIN"]["n_paired"] == 20
    assert by[("ml_wind_corrected", "ml_cooling_corrected")]["n_paired"] == 240 - 30
    assert by[("ml_cooling_corrected", "raw_forecast")]["per_city"]["MIDLAND"]["n_paired"] == 30
    ss = rep["sample_size"]
    assert ss["n_scored"]["AUSTIN"]["persistence_24h"] == 20 and ss["n_scored"]["AUSTIN"]["raw_forecast"] == 60
    assert all(not p["targets"]["tail_rate_target_met"] and not p["targets"]["mdd_target_met"] for p in ss["pairs"])
    assert ss["targets_met"] == {"tail_rate_590": [], "mdd_1575": []}


def test_family_insufficient_data_enters_holm_as_one_and_keeps_the_family_at_nine():
    frames = make_frames(n=60, seed=9, nan_rules={(c, "persistence_24h"): 5 for c in CITIES})
    rep = st.build_family_report(frames, row_source="reconstructed_frames", params=small_params())
    idx = [i for i, c in enumerate(rep["comparisons"]) if c["b"] == "persistence_24h"]
    assert len(idx) == 3
    for i in idx:
        c = rep["comparisons"][i]
        assert c["headline"]["outcome"] == "insufficient_data" and c["n_paired"] == 20
        assert c["headline"]["p_holm_adjusted"] == 1.0 and c["headline"]["holm_rejected"] is False
    assert rep["holm"]["m"] == 9
    # the other six are tested at m = 9, not m = 6: the smallest unadjusted p is scaled by 9
    others = [rep["comparisons"][i]["headline"] for i in range(9) if i not in idx]
    pmin = min(h["p_headline"] for h in others)
    assert min(h["p_holm_adjusted"] for h in others) == pytest.approx(min(1.0, 9 * pmin))


def test_family_opposite_city_effects_give_two_of_four_and_inconclusive():
    frames = {}
    for k, city in enumerate(CITIES):
        rng = np.random.default_rng(40 + k)
        idx = pd.date_range("2026-04-01", periods=60, freq="6h")
        sign = 1.0 if k < 2 else -1.0
        base = rng.normal(size=60) * 3.0
        frames[city] = pd.DataFrame({
            "ml_wind_corrected": 60.0 - sign * 10.0 + base, "ml_cooling_corrected": 60.0 + sign * 10.0 + base,
            "reference_ml_refit_24h": 50.0 + base, "raw_forecast": 70.0 + base, "persistence_24h": 90.0 + base,
        }, index=idx)
    rep = st.build_family_report(frames, row_source="reconstructed_frames", params=small_params())
    wc = next(c for c in rep["comparisons"] if (c["a"], c["b"]) == ("ml_wind_corrected", "ml_cooling_corrected"))
    assert (wc["cities_favoring_a"], wc["cities_with_data"]) == (2, 4)
    assert wc["headline"]["outcome"] == "inconclusive"
    assert abs(wc["point_margin"]) < 1.5


def test_family_report_is_deterministic_json_and_labels_flags_by_source():
    a = core.dumps(st.build_family_report(make_frames(n=40, seed=2), row_source="shadow_logs", params=small_params(n_resamples=300)))
    b = core.dumps(st.build_family_report(make_frames(n=40, seed=2), row_source="shadow_logs", params=small_params(n_resamples=300)))
    assert a == b


def test_family_accepts_missing_city_frames_and_unknown_row_source():
    frames = make_frames(n=40, seed=2)
    frames["EL_PASO"] = pd.DataFrame()
    rep = st.build_family_report(frames, row_source="shadow_logs", params=small_params(n_resamples=300))
    entry = rep["comparisons"][0]
    assert entry["cities_with_data"] == 3 and entry["per_city_margins"]["EL_PASO"] is None
    assert entry["per_city"]["EL_PASO"]["outcome"] == "insufficient_data"
    with pytest.raises(ValueError):
        st.build_family_report(frames, row_source="corridor", params=small_params())


def test_family_slot_column_pairs_rows_per_cycle_not_per_index():
    """The reference's own-target-hour error is paired with the other candidates by cycle (slot), while the
    index stays the cycle's valid_time; the slot grid drives the pooled resample."""
    frames = make_frames(n=40, seed=5)
    for f in frames.values():
        f["slot"] = f.index
    rep = st.build_family_report(frames, row_source="shadow_logs", params=small_params(n_resamples=300))
    assert rep["comparisons"][0]["headline"]["n_slots"] == 40


def test_runtime_stats_module_does_not_import_the_frozen_audit_module():
    path = os.path.join(os.path.dirname(st.__file__), "forecast_shadow_score_stats.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(a.name != "forecast_experiment_audit" for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "forecast_experiment_audit"


def test_build_family_report_refuses_error_frames_tagged_with_another_row_source():
    # Task 4 validation: frames may carry `attrs["row_source"]`; one tagged with a different source is refused.
    frames = make_frames(n=40, cities=["AUSTIN", "MIDLAND"])
    frames["AUSTIN"].attrs["row_source"] = "shadow_logs"
    frames["MIDLAND"].attrs["row_source"] = "reconstructed_frames"
    with pytest.raises(ValueError, match="row source"):
        st.build_family_report(frames, row_source="shadow_logs", params=small_params())
    with pytest.raises(ValueError, match="row source"):
        st.build_family_report(frames, row_source="reconstructed_frames", params=small_params())
    frames["MIDLAND"].attrs["row_source"] = "shadow_logs"
    assert st.build_family_report(frames, row_source="shadow_logs", params=small_params())["row_source"] == "shadow_logs"
    untagged = make_frames(n=40, cities=["AUSTIN"])           # untagged frames stay accepted (backwards compatible)
    assert st.build_family_report(untagged, row_source="reconstructed_frames", params=small_params())["row_source"] == "reconstructed_frames"
