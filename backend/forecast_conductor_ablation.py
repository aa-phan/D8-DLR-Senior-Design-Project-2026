"""
ABLATION conductor-invariance re-score and veto evaluation (SEL-03, D-02).

What this is. The conductor on the production lines is not yet known (Power Systems has not answered), so the
selection needs to know whether a candidate's STANDING depends on the conductor. This module refits the two
conductor-dependent candidates (`ml_cooling_corrected`, `reference_ml_refit_24h`) on TRAIN only under each
conductor in a bracketing set, scores every candidate on VALIDATION under that same conductor, and compares each
variant with the control (Drake-75, the frozen configuration). It is a relative-ordering finding on rows the
configurations were selected on, so it is never a confirmation: by D-02 it can only VETO, never name a winner.
The veto criteria are the v4 draft's ("ABLATION design and veto criteria") and are checked against the signed
registry in plan 07-10; this module only computes them.

Split (rows strictly before 2026-03-17, asserted; exact-lead rows only):
train is `valid_time <= 2025-09-01T18:00:00Z` (2,360 rows per city) and validation is
`2025-09-02T00:00:00Z <= valid_time < 2026-03-17T00:00:00Z` (784 rows per city). On the real cached frames the
driver asserts both counts per city and names the city and both counts when either differs.

Fits. `ml_wind_corrected` does not depend on the conductor: it is fit once per city on train under the control
point (`forecast_conductor_refit.fit_for_point(methods=("ml_wind_corrected",), fit_end=TRAIN_END)`). Cooling and
reference are fit on train under each variant, in memory only: nothing is written anywhere (no joblib.dump, never
under data/shadow/models; the 12 frozen artifacts are untouched and are not scored here, which would be in-sample).
Truth, raw_forecast and persistence are recomputed under each variant's conductor. Emissivity and absorptivity
are 0.8, `resist_temp_coef` 0.00404 and each city's line bearing is held fixed, so only the conductor moves.

Precision. Margins, relative metrics and Kendall tau come from unrounded float64 values. A margin of exactly 0.0
has sign 0, so a change from a positive control margin to 0.0 is a sign change for the veto.

Veto rule (`VETO_RULE`). A candidate (ml_wind_corrected, ml_cooling_corrected, reference_ml_refit_24h) is vetoed
if under any variant (a) the sign of its pooled margin over `raw_forecast` differs from the control's, or (b)
(cooling and reference only) the sign of its pooled margin over `ml_wind_corrected` differs from the control's,
or (c) (cooling and reference only) whether it is favoured over `ml_wind_corrected` in at least 3 cities differs
from the control. A margin that cannot be computed under a variant also vetoes (the claim cannot be shown).
`ranking_invariant` is true only when nothing is vetoed and every variant's Kendall tau against the control is
1.0. The AUSTIN-only variant (Drake-75-AUSTIN-163m) is compared with the control restricted to the same cities,
because a one-city pooled margin cannot be compared with a four-city one; the draft does not say how, so that
choice is recorded in the report and flagged for the signing review.

Run by a human offline: `PYTHONPATH=backend .venv/bin/python backend/forecast_conductor_ablation.py`. Cached
frames only (the `_2024-01-20_2026-09-29_` files restricted to rows before 2026-03-17); the FRESH-dated
experiment caches are never opened.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

import ampacity_forecast
import city_point
import config
import forecast_conductor_refit as refit
import forecast_experiment
import forecast_experiment_audit
import forecast_shadow_confirm as confirm
import forecast_shadow_eval_core as core
import forecast_shadow_fit_models
import forecast_shadow_pipeline
import forecast_shadow_score_stats as stats
import thermal_model

TRAIN_END = pd.Timestamp("2025-09-01T18:00:00Z")
VALIDATION_START = pd.Timestamp("2025-09-02T00:00:00Z")
VALIDATION_END_EXCLUSIVE = pd.Timestamp("2026-03-17T00:00:00Z")
TRAIN_ROWS_PER_CITY = 2360
VALIDATION_ROWS_PER_CITY = 784
CONTROL = "Drake-75"
EMISSIVITY = ABSORPTIVITY = 0.8
RESIST_TEMP_COEF = 0.00404
VETO_RULE = "sign_flip_vs_raw_or_default"
ROW_SOURCE = "reconstructed_frames"
BASIS = "ABLATION (train <= 2025-09-01T18:00Z, validation 2025-09-02..2026-03-16)"

_WIND = forecast_shadow_fit_models.WIND_METHOD
_COOLING = forecast_shadow_fit_models.COOLING_METHOD
_REFERENCE = forecast_shadow_fit_models.REFERENCE_METHOD
_RAW = "raw_forecast"
_DRAKE = "795 kcmil ACSR Drake"
_DRAKE_D, _DRAKE_R, _ELEVATION = 0.02814, 0.0726, 900.0


def _variant(name, conductor_type, diameter_m, resistance_ac, max_temp_c, elevation_m=_ELEVATION,
             cities="all", approximate_resistance=False) -> dict:
    return {"name": name, "conductor_type": conductor_type, "diameter_m": diameter_m,
            "resistance_ac": resistance_ac, "max_temp_c": max_temp_c, "elevation_m": elevation_m,
            "cities": cities, "approximate_resistance": approximate_resistance}


# Catalogue values (research script 03-05-conductor_sensitivity.py): outer diameter in m, AC resistance at 25 C in
# ohm/km. Elevation is the production default (900 m) except for the one variant that tests Austin's measured 163 m.
BRACKETING_SET: tuple[dict, ...] = (
    _variant("Drake-75", _DRAKE, _DRAKE_D, _DRAKE_R, 75.0),
    _variant("Drake-100", _DRAKE, _DRAKE_D, _DRAKE_R, 100.0),
    _variant("Falcon-90", "1590 kcmil ACSR Falcon", 0.03924, 0.0371, 90.0),
    _variant("Suwannee-150", "959.6 kcmil ACSS/TW Suwannee", 0.02819, 0.0597, 150.0, approximate_resistance=True),
    _variant("Suwannee-200", "959.6 kcmil ACSS/TW Suwannee", 0.02819, 0.0597, 200.0, approximate_resistance=True),
    _variant("Drake-75-AUSTIN-163m", _DRAKE, _DRAKE_D, _DRAKE_R, 75.0, elevation_m=163.0, cities=("AUSTIN",)),
)

SUWANNEE_CAVEAT = (
    "Suwannee-150 and Suwannee-200 use the catalogue ACSS/TW resistance (0.0597 ohm/km at 25 C) in the repo's "
    "linear resistance model; that model's accuracy for ACSS/TW at 150-200 C is unverified "
    "(shadow_early_decision_options.md, 'Items I could not verify')."
)
SELECTION_CAVEAT = (
    "ABLATION is a relative-ordering finding on rows the configurations were selected on; it can veto a candidate "
    "and can never confirm one or name a winner (D-02)."
)


# --------------------------------------------------------------------------
# Variants and the split
# --------------------------------------------------------------------------

def _resolve_variant(variant) -> dict:
    if isinstance(variant, dict):
        return variant
    for entry in BRACKETING_SET:
        if entry["name"] == variant:
            return entry
    raise KeyError(f"Unknown ABLATION variant {variant!r}. Valid names: {[v['name'] for v in BRACKETING_SET]}")


def variant_point(city: str, variant):
    """
    (CityPoint, applies) for `variant` (a BRACKETING_SET entry or its name) at `city`: the city's coordinate,
    static rating, bounds and line bearing, with the variant's conductor and emissivity / absorptivity /
    resist_temp_coef held at the ABLATION constants. `(None, False)` when the variant does not apply to the city.
    """
    if city not in config.LOCATIONS:
        raise KeyError(f"Unknown city {city!r}. Valid cities: {sorted(config.LOCATIONS)}")
    v = _resolve_variant(variant)
    if v["cities"] != "all" and city not in v["cities"]:
        return None, False
    bearing = config.CITY_LINE_BEARING_DEG[city]
    conductor = thermal_model.ConductorConfig(
        diameter_m=v["diameter_m"], resistance_ac=v["resistance_ac"], resist_temp_coef=RESIST_TEMP_COEF,
        emissivity=EMISSIVITY, absorptivity=ABSORPTIVITY, max_temp_c=v["max_temp_c"],
        line_azimuth=bearing, elevation_m=v["elevation_m"],
    )
    point = city_point.CityPoint(
        name=city, coord=config.CITY_COORDINATES[city], bearing_deg=bearing, conductor=conductor,
        static_rating=config.STATIC_RATINGS[city], rating_bounds=config.RATING_BOUNDS_BY_LOCATION[city],
    )
    return point, True


def split(exact: pd.DataFrame, expected_counts: bool = True):
    """
    (train, validation) from exact-lead rows: train is `valid_time <= TRAIN_END`, validation is
    `VALIDATION_START <= valid_time < VALIDATION_END_EXCLUSIVE`. A row at or after the frozen test split raises
    AssertionError. With `expected_counts`, the per-city counts must equal TRAIN_ROWS_PER_CITY and
    VALIDATION_ROWS_PER_CITY, else AssertionError naming the city and both counts.
    """
    valid_time = pd.to_datetime(exact["datetime_utc"], utc=True)
    if len(valid_time) and valid_time.max() >= VALIDATION_END_EXCLUSIVE:
        raise AssertionError(
            f"ablation split: a row at {valid_time.max()} is on or after {VALIDATION_END_EXCLUSIVE} "
            f"(2026-03-17, the frozen test split); the load restriction failed"
        )
    train = exact[valid_time <= TRAIN_END]
    validation = exact[(valid_time >= VALIDATION_START) & (valid_time < VALIDATION_END_EXCLUSIVE)]
    if expected_counts and (len(train) != TRAIN_ROWS_PER_CITY or len(validation) != VALIDATION_ROWS_PER_CITY):
        city = exact["city"].iloc[0] if "city" in exact.columns and len(exact) else "<unknown city>"
        raise AssertionError(
            f"ablation split for {city}: {len(train)} train and {len(validation)} validation exact-lead rows, "
            f"expected {TRAIN_ROWS_PER_CITY} train and {VALIDATION_ROWS_PER_CITY} validation"
        )
    return train, validation


# --------------------------------------------------------------------------
# Candidate errors
# --------------------------------------------------------------------------

def candidate_errors(validation: pd.DataFrame, hourly_frame: pd.DataFrame, point, models: dict):
    """
    Signed prediction-minus-truth per candidate on the validation rows, under `point`, built the way
    `forecast_shadow_confirm.candidate_predictions` builds them: raw and persistence through the experiment's
    `_city_ampacity`, wind and cooling through the experiment helpers, and the reference from
    `build_ml_features` of the point's own truth ampacity over the complete hourly grid, read at each anchor.
    `hourly_frame` is the whole prepared frame (its truth columns give the hourly history). A model that is
    None leaves its column NaN. Returns (errors, mean_truth); `errors` is indexed by valid_time, has one column
    per `core.CANDIDATES` then `slot`, and carries `attrs["row_source"]`.
    """
    n = len(validation)
    valid_time = pd.DatetimeIndex(validation["datetime_utc"]) if n else pd.DatetimeIndex([], tz="UTC")
    truth = validation["truth_dlr_amps"].to_numpy(dtype=float) if n else np.array([], dtype=float)
    out = pd.DataFrame(index=valid_time)
    for name in core.CANDIDATES:
        out[name] = np.nan

    arms = {
        _RAW: lambda f: forecast_experiment._city_ampacity(
            f["fcst_air_temp"], f["fcst_wind_speed"], f["fcst_wind_direction"], f["fcst_solar_radiation"], point),
        "persistence_24h": lambda f: forecast_experiment._city_ampacity(
            f["anchor_air_temp"], f["anchor_wind_speed"], f["anchor_wind_direction"],
            f["anchor_solar_radiation"], point),
    }
    if models.get(_WIND) is not None:
        arms[_WIND] = lambda f: forecast_experiment._wind_corrected_ampacity(models[_WIND], f, point)
    if models.get(_COOLING) is not None:
        arms[_COOLING] = lambda f: forecast_experiment._cooling_corrected_ampacity(models[_COOLING], f, point)
    if n:
        for name, fn in arms.items():
            values, _failed = confirm.predict_arm(fn, validation)  # a failing row is NaN, never imputed
            out[name] = values - truth

        estimator = models.get(_REFERENCE)
        if estimator is not None:
            arm5 = refit.arm5_frame_for_point(hourly_frame, point, prefix="truth_")
            indexed = arm5.set_index("datetime_utc").sort_index()
            grid = pd.date_range(indexed.index.min(), indexed.index.max(), freq="h")
            features = ampacity_forecast.build_ml_features(indexed.reindex(grid))
            at_anchor = features.reindex(pd.DatetimeIndex(validation["anchor_datetime_utc"]))
            ok = ~at_anchor.isnull().any(axis=1).to_numpy()
            predicted = np.full(n, np.nan)
            if ok.any():
                predicted[ok] = np.asarray(estimator.predict(at_anchor.to_numpy(dtype=float)[ok]), dtype=float)
            out[_REFERENCE] = predicted - truth
    out["slot"] = valid_time
    out.attrs["row_source"] = ROW_SOURCE
    return out, (float(truth.mean()) if n else None)


# --------------------------------------------------------------------------
# Per-variant blocks
# --------------------------------------------------------------------------

def _plain(value):
    return None if value is None or not np.isfinite(value) else float(value)


def _errors_of(errors_by_city: dict, name: str, cities) -> np.ndarray:
    parts = [errors_by_city[c][name].dropna().to_numpy(dtype=float) for c in cities]
    return np.concatenate(parts) if parts else np.array([], dtype=float)


def _find_pair(family: dict, a: str, b: str):
    """(comparison, flipped): the family entry for (a, b), or for (b, a) with flipped=True; (None, False) if absent."""
    for comparison in family["comparisons"]:
        if (comparison["a"], comparison["b"]) == (a, b):
            return comparison, False
    for comparison in family["comparisons"]:
        if (comparison["a"], comparison["b"]) == (b, a):
            return comparison, True
    return None, False


def _margin_over(family: dict, candidate: str, other: str):
    """Pooled margin of `candidate` over `other` in amps (positive: candidate has the lower MAE), or None."""
    comparison, flipped = _find_pair(family, candidate, other)
    if comparison is None:
        return None
    margin = comparison.get("point_margin")
    if margin is None or not np.isfinite(margin):
        return None
    return (-margin if flipped else margin) + 0.0  # + 0.0 turns -0.0 into 0.0


def _cities_favoring(family: dict, candidate: str, other: str):
    """(cities where `candidate` strictly beats `other`, cities with a margin), or (None, 0) if absent."""
    comparison, flipped = _find_pair(family, candidate, other)
    if comparison is None:
        return None, 0
    favoured = with_margin = 0
    for margin in comparison.get("per_city_margins", {}).values():
        if margin is None or not np.isfinite(margin):
            continue
        with_margin += 1
        if (margin < 0.0) if flipped else (margin > 0.0):
            favoured += 1
    return favoured, with_margin


def _rank_order(errors_by_city: dict, cities) -> tuple[list[str], str, int]:
    """Candidates by pooled MAE (ties by name) on rows where every candidate is scored: (order, basis, n)."""
    names = list(core.CANDIDATES)
    frames = [errors_by_city[c][names].dropna() for c in cities if len(errors_by_city[c])]
    common = pd.concat(frames) if frames else pd.DataFrame({n: [] for n in names})
    if len(common):
        maes = {n: float(np.mean(np.abs(common[n].to_numpy(dtype=float)))) for n in names}
        basis, n_rows = "rows where every candidate is scored", int(len(common))
    else:
        maes = {n: (float(np.mean(np.abs(_errors_of(errors_by_city, n, cities))))
                    if len(_errors_of(errors_by_city, n, cities)) else float("inf")) for n in names}
        basis, n_rows = "each candidate's own rows (no row is scored by all)", 0
    return sorted(names, key=lambda n: (maes[n], n)), basis, n_rows


def _kendall_tau(order: list[str], control_order: list[str]):
    if order == control_order:
        return 1.0  # identical orders are exactly 1.0, not a rounded 0.9999999999999999
    names = list(core.CANDIDATES)
    rank = {n: i for i, n in enumerate(order)}
    control_rank = {n: i for i, n in enumerate(control_order)}
    tau = scipy_stats.kendalltau([control_rank[n] for n in names], [rank[n] for n in names]).statistic
    return _plain(tau)


def _block(errors_by_city: dict, mean_truth_by_city: dict, cities: list[str], params) -> dict:
    """Family report, metrics, relative metrics, pooled metrics, rank order and margins for one variant."""
    family = stats.build_family_report({c: errors_by_city[c] for c in cities}, row_source=ROW_SOURCE, params=params)
    metrics: dict = {}
    relative: dict = {}
    pooled: dict = {}
    n_rows = {c: int(len(errors_by_city[c])) for c in cities}
    total_rows = sum(n_rows.values())
    pooled_truth = (sum(mean_truth_by_city[c] * n_rows[c] for c in cities if mean_truth_by_city[c] is not None)
                    / total_rows) if total_rows else None
    for name in core.CANDIDATES:
        metrics[name], relative[name] = {}, {}
        for city in cities:
            col = errors_by_city[city][name].dropna().to_numpy(dtype=float)
            # descriptive_metrics takes error = pred - truth; with truth 0 the signed error passes through unchanged
            m = core.descriptive_metrics(col, np.zeros_like(col))
            metrics[name][city] = m
            truth = mean_truth_by_city[city]
            relative[name][city] = {
                key: (m[key] / truth if m[key] is not None and truth else None) for key in ("mae", "rmse", "bias")}
        allv = _errors_of(errors_by_city, name, cities)
        p = core.descriptive_metrics(allv, np.zeros_like(allv))
        pooled[name] = {
            "n": p["n"], "mae": p["mae"], "rmse": p["rmse"], "bias": p["bias"],
            "relative_mae": p["mae"] / pooled_truth if p["mae"] is not None and pooled_truth else None,
            "relative_rmse": p["rmse"] / pooled_truth if p["rmse"] is not None and pooled_truth else None,
            "relative_bias": p["bias"] / pooled_truth if p["bias"] is not None and pooled_truth else None,
        }
    order, basis, n_common = _rank_order(errors_by_city, cities)

    margins_over_raw = {}
    for candidate in core.REAL_CANDIDATES:
        comparison, _ = _find_pair(family, candidate, _RAW)
        reduction = comparison.get("relative_mae_reduction") if comparison else None
        margins_over_raw[candidate] = {
            "amps": _margin_over(family, candidate, _RAW),
            "pct": None if reduction is None else 100.0 * reduction,
        }
    margins_over_wind, cities_over_wind = {}, {}
    for candidate in (_COOLING, _REFERENCE):
        margins_over_wind[candidate] = _margin_over(family, candidate, _WIND)
        favoured, with_margin = _cities_favoring(family, candidate, _WIND)
        cities_over_wind[candidate] = {"favoured": favoured, "of": with_margin,
                                       "at_least_3": None if favoured is None else favoured >= core.CONSISTENCY_MIN_CITIES}
    return {
        "family": family, "metrics": metrics, "relative_metrics": relative, "pooled": pooled,
        "pooled_mean_truth": pooled_truth, "mean_truth_by_city": dict(mean_truth_by_city),
        "rank_order": order, "rank_basis": basis, "rank_n_rows": n_common,
        "margins_over_raw": margins_over_raw, "margins_over_wind": margins_over_wind,
        "cities_favoured_over_wind": cities_over_wind,
    }


def run_ablation(cities, frame_loader=forecast_shadow_fit_models.load_city_frame, variants=BRACKETING_SET,
                 params=None, expected_counts=True) -> dict:
    """
    Refit on train and score on validation under each bracketing conductor, in memory only. `frame_loader(city)`
    returns the city's cached anchored pair frame (rows before 2026-03-17 only; asserted). Returns a JSON-ready
    report: the basis, the variant table (per variant: family report, metrics, relative metrics, pooled metrics,
    rank order, Kendall tau against the control, margins) and the caveats. Evaluate it with `veto(report)`.
    """
    cities = list(cities)
    variants = [_resolve_variant(v) for v in variants]
    if CONTROL not in [v["name"] for v in variants]:
        raise ValueError(f"run_ablation: the control variant {CONTROL} must be in `variants`")
    errors: dict = {v["name"]: {} for v in variants}
    mean_truth: dict = {v["name"]: {} for v in variants}
    n_rows: dict = {}
    skipped: dict = {}
    for v in variants:
        if v["cities"] != "all" and not [c for c in cities if c in v["cities"]]:
            skipped[v["name"]] = f"applies to {', '.join(v['cities'])} only; no requested city applies"

    for city in cities:
        frame = frame_loader(city)
        forecast_shadow_fit_models.assert_no_test_leak(frame)
        control_point, _ = variant_point(city, CONTROL)
        wind = refit.fit_for_point(city, frame, control_point, methods=(_WIND,), fit_end=TRAIN_END)["models"]
        for v in variants:
            if v["name"] in skipped:
                continue
            point, applies = variant_point(city, v)
            if not applies:
                continue
            full, exact = refit.prepare_fit_frame(frame, point, city)
            train, validation = split(exact, expected_counts=expected_counts)
            fitted = refit.fit_for_point(city, frame, point, methods=refit.REFIT_METHODS, fit_end=TRAIN_END)
            if fitted["n_rows_fit"][_COOLING] != len(train):
                raise AssertionError(
                    f"ablation {v['name']} {city}: cooling was fit on {fitted['n_rows_fit'][_COOLING]} rows but the "
                    f"train split has {len(train)}"
                )
            models = {**wind, **fitted["models"]}
            errors[v["name"]][city], mean_truth[v["name"]][city] = candidate_errors(validation, full, point, models)
            if v["name"] == CONTROL:
                n_rows[city] = {"train": int(len(train)), "validation": int(len(validation))}

    blocks: dict = {}
    for v in variants:
        name = v["name"]
        if name in skipped:
            continue
        applicable = [c for c in cities if c in errors[name]]
        block = _block(errors[name], mean_truth[name], applicable, params)
        block["variant"] = dict(v, cities=v["cities"] if v["cities"] == "all" else list(v["cities"]))
        block["cities"] = applicable
        if v["approximate_resistance"]:
            block["caveat"] = SUWANNEE_CAVEAT
        blocks[name] = block

    control_block = blocks[CONTROL]
    for name, block in blocks.items():
        if name == CONTROL:
            block["kendall_tau_vs_control"] = 1.0
            continue
        if block["cities"] == control_block["cities"]:
            block["kendall_tau_vs_control"] = _kendall_tau(block["rank_order"], control_block["rank_order"])
        else:
            matched = _block(errors[CONTROL], mean_truth[CONTROL], block["cities"], params)
            block["matched_control"] = {
                "cities": block["cities"], "family": matched["family"], "rank_order": matched["rank_order"],
                "note": "the control restricted to this variant's cities (a pooled margin over fewer cities "
                        "cannot be compared with the all-city control)",
            }
            block["kendall_tau_vs_control"] = _kendall_tau(block["rank_order"], matched["rank_order"])

    return {
        "basis": BASIS, "veto_rule": VETO_RULE, "control": CONTROL, "cities": cities,
        "n_rows": n_rows, "variants": blocks, "skipped_variants": skipped,
        "fixed": {"emissivity": EMISSIVITY, "absorptivity": ABSORPTIVITY, "resist_temp_coef": RESIST_TEMP_COEF,
                  "bearing_deg": {c: config.CITY_LINE_BEARING_DEG[c] for c in cities}},
        "caveats": [SELECTION_CAVEAT, SUWANNEE_CAVEAT],
    }


# --------------------------------------------------------------------------
# The veto
# --------------------------------------------------------------------------

def _sign(value):
    if value is None or not np.isfinite(value):
        return None
    return float(np.sign(value))


def veto(report: dict) -> dict:
    """
    Apply the pre-registered ABLATION veto rule (see the module docstring) to a `run_ablation` report (or any
    report with `control` and per-variant `family` and `kendall_tau_vs_control`). Signs come from the unrounded
    pooled margins; a margin of exactly 0.0 has sign 0. Returns
    `{"vetoes": {candidate: {"vetoed": bool, "reasons": [str]}}, "ranking_invariant": bool, "rule": VETO_RULE}`.
    """
    control_name = report.get("control", CONTROL)
    variants = report["variants"]
    control_family = variants[control_name]["family"]
    vetoes = {c: {"vetoed": False, "reasons": []} for c in core.REAL_CANDIDATES}
    taus_ok = True

    def flag(candidate: str, reason: str) -> None:
        vetoes[candidate]["vetoed"] = True
        vetoes[candidate]["reasons"].append(reason)

    for name, block in variants.items():
        if name == control_name:
            continue
        tau = block.get("kendall_tau_vs_control")
        if tau is None or not np.isfinite(tau) or tau != 1.0:
            taus_ok = False
        base = (block.get("matched_control") or {}).get("family") or control_family
        family = block["family"]
        for candidate in core.REAL_CANDIDATES:
            others = [_RAW] + ([_WIND] if candidate != _WIND else [])
            for other in others:
                c_margin = _margin_over(base, candidate, other)
                v_margin = _margin_over(family, candidate, other)
                clause = "a" if other == _RAW else "b"
                if _sign(c_margin) is None or _sign(v_margin) is None:
                    flag(candidate, f"{name}: pooled margin over {other} is unavailable (control {c_margin!r}, "
                                    f"variant {v_margin!r}); clause ({clause}) cannot be shown to hold")
                elif _sign(c_margin) != _sign(v_margin):
                    flag(candidate, f"{name}: pooled margin over {other} changes sign versus {control_name} "
                                    f"({c_margin!r} -> {v_margin!r}), clause ({clause})")
            if candidate != _WIND:
                c_fav, c_n = _cities_favoring(base, candidate, _WIND)
                v_fav, v_n = _cities_favoring(family, candidate, _WIND)
                if c_fav is None or v_fav is None:
                    flag(candidate, f"{name}: the per-city comparison with {_WIND} is unavailable, clause (c)")
                else:
                    c_hold = c_fav >= core.CONSISTENCY_MIN_CITIES
                    v_hold = v_fav >= core.CONSISTENCY_MIN_CITIES
                    if c_hold != v_hold:
                        flag(candidate, f"{name}: favoured over {_WIND} in {v_fav} of {v_n} cities versus {c_fav} of "
                                        f"{c_n} under {control_name}; whether that is at least 3 cities changes, "
                                        f"clause (c)")
    invariant = bool(taus_ok and not any(v["vetoed"] for v in vetoes.values()))
    return {"vetoes": vetoes, "ranking_invariant": invariant, "rule": VETO_RULE}


# --------------------------------------------------------------------------
# Report files and the CLI
# --------------------------------------------------------------------------

def _summary_markdown(report: dict, result: dict) -> str:
    lines = [
        "# ABLATION conductor-invariance re-score (SEL-03)", "",
        "## Summary (plain English)", "",
        f"Basis: {report['basis']}. Cooling and reference were refit on the early rows only and every method was "
        f"scored on the validation rows, once under each bracketing conductor. This can only disqualify a "
        f"method (a veto); it can never pick one or confirm one.", "",
    ]
    variants = report["variants"]
    others = [n for n in variants if n != report["control"]]
    lines.append(f"Conductors tried besides the control ({report['control']}): "
                 f"{', '.join(others) if others else 'none'}.")
    changed = [n for n in others if variants[n].get("kendall_tau_vs_control") != 1.0]
    if result["ranking_invariant"]:
        lines.append("Ranking: the order of the five methods is identical under every bracketing conductor, and "
                     "nothing is vetoed, so the ranking is invariant to the conductor.")
    else:
        why = []
        if changed:
            why.append("the order of the five methods changes under " + ", ".join(changed))
        if any(v["vetoed"] for v in result["vetoes"].values()):
            why.append("at least one method is vetoed")
        lines.append("Ranking: NOT invariant to the conductor (" + "; ".join(why) + ").")
    lines.append("")
    for candidate, verdict in result["vetoes"].items():
        if verdict["vetoed"]:
            lines.append(f"- {candidate}: WOULD BE VETOED.")
            lines.extend(f"  - {reason}" for reason in verdict["reasons"])
        else:
            lines.append(f"- {candidate}: keeps its standing under every bracketing conductor (no veto).")
    lines += ["", f"Veto rule: `{result['rule']}` (the v4 draft's three clauses; see the module docstring).", "",
              "## Variants", "",
              "| variant | cities | max temp C | Kendall tau vs control | order, best first |",
              "|---|---|---|---|---|"]
    for name, block in variants.items():
        v = block["variant"]
        flag = " (resistance unverified at this temperature)" if v["approximate_resistance"] else ""
        lines.append(f"| {name}{flag} | {', '.join(block['cities'])} | {v['max_temp_c']} | "
                     f"{block['kendall_tau_vs_control']} | {' > '.join(block['rank_order'])} |")
    lines += ["", "## Margins over raw_forecast and over ml_wind_corrected", "",
              "A positive margin means the candidate has the lower MAE. Amps are pooled over the variant's cities.", ""]
    for name, block in variants.items():
        lines.append(f"### {name}")
        for candidate, m in block["margins_over_raw"].items():
            pct = "n/a" if m["pct"] is None else f"{m['pct']:.3f} %"
            lines.append(f"- {candidate} over raw_forecast: {m['amps']!r} A ({pct})")
        for candidate, m in block["margins_over_wind"].items():
            cw = block["cities_favoured_over_wind"][candidate]
            lines.append(f"- {candidate} over ml_wind_corrected: {m!r} A; favoured in {cw['favoured']} of {cw['of']} cities")
        if "matched_control" in block:
            lines.append(f"- compared with the control restricted to {', '.join(block['cities'])} (matched control)")
        if "caveat" in block:
            lines.append(f"- Caveat: {block['caveat']}")
        lines.append("")
    if report["skipped_variants"]:
        lines += ["## Skipped variants", ""] + [f"- {n}: {why}" for n, why in report["skipped_variants"].items()] + [""]
    lines += ["## Caveats", ""] + [f"- {text}" for text in report["caveats"]] + [""]
    return "\n".join(lines)


def write_report(report: dict, out_dir: str) -> dict:
    """
    Write `ablation.json` (the report plus its veto evaluation) and `ablation.md` (a plain-English summary first)
    into a NEW directory. Refuses an existing `out_dir` (FileExistsError) and any directory that is or lies
    inside `data/shadow/models` (ValueError). Returns the two paths.
    """
    frozen = os.path.realpath(forecast_shadow_pipeline.SHADOW_MODEL_DIR)
    target = os.path.realpath(out_dir)
    if target == frozen or target.startswith(frozen + os.sep):
        raise ValueError(f"refusing to write the ABLATION report inside the frozen directory {frozen}")
    if os.path.lexists(out_dir):
        raise FileExistsError(f"refusing to overwrite the existing ABLATION report directory {out_dir}")
    result = veto(report)
    os.makedirs(out_dir)
    json_path = os.path.join(out_dir, "ablation.json")
    md_path = os.path.join(out_dir, "ablation.md")
    with open(json_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(core.dumps({**report, "veto": result}, indent=2) + "\n")
    with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_summary_markdown(report, result))
    return {"json": json_path, "markdown": md_path}


def _default_out_dir() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(core.EVIDENCE_ROOT_DEFAULT, "v4-ablation", stamp)


def _guarded_load_city_frame(city: str) -> pd.DataFrame:
    """The shadow cached-frame loader, after refusing any FRESH-dated experiment cache path."""
    path = forecast_experiment._cache_path_for(
        city, forecast_experiment_audit.FROZEN_WINDOW_START, forecast_experiment_audit.FROZEN_WINDOW_END,
        lead_hours=refit.LEAD_HOURS)
    core.assert_not_fresh_experiment_cache(path)
    return forecast_shadow_fit_models.load_city_frame(city)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="ABLATION conductor-invariance re-score (SEL-03): train-only refits in memory, validation scoring, veto.")
    parser.add_argument("--cities", nargs="+", choices=sorted(config.LOCATIONS), default=list(config.LOCATIONS),
                        metavar="CITY")
    parser.add_argument("--out-dir", default=None,
                        help="new directory (default: data/shadow/evaluation/v4-ablation/<UTC yyyymmddTHHMMSSZ>)")
    parser.add_argument("--n-resamples", type=int, default=core.N_RESAMPLES)
    args = parser.parse_args(argv)
    out_dir = args.out_dir or _default_out_dir()

    report = run_ablation(args.cities, frame_loader=_guarded_load_city_frame, variants=BRACKETING_SET,
                          params={"n_resamples": args.n_resamples}, expected_counts=True)
    paths = write_report(report, out_dir)
    result = veto(report)
    print(f"ABLATION report written to {out_dir} ({paths['json']}, {paths['markdown']})")
    print(f"veto rule {result['rule']}; ranking_invariant={result['ranking_invariant']}")
    for candidate, verdict in result["vetoes"].items():
        print(f"  {candidate}: {'VETOED' if verdict['vetoed'] else 'not vetoed'}")
        for reason in verdict["reasons"]:
            print(f"    - {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
