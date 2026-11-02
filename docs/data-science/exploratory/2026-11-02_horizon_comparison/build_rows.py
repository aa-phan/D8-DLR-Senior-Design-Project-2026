"""
Exploratory, not pre-registered; does not change signed protocol v4 or read 1.

Builds the per-row prediction table for the horizon comparison (see PLAN.md):
the five 24 h shadow candidates on the non-FRESH TEST split, reproduced in memory with the TEST scorer's own
building blocks (cached frames only, no evidence directory, nothing written under data/), plus the live
60-minute `ml` model and a 60-minute naive forecast on the same valid times and the same truth.

Run from the repository root (REFIT_ROOT is cwd-relative):
    PYTHONPATH=backend .venv/bin/python docs/data-science/exploratory/2026-11-02_horizon_comparison/build_rows.py

Writes only into this script's directory: rows_<basis>.csv, checks.json.
"""

from __future__ import annotations

import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

import ampacity_forecast
import city_point
import config
import forecast_conductor_refit
import forecast_shadow_confirm as confirm
import forecast_test_split_score as tss
import thermal_model

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
CUTOFF = pd.Timestamp("2026-09-30T00:00:00Z")
CITIES = list(config.LOCATIONS)
BASES = ("production", "frozen-drake")


def assert_before_cutoff(times, what: str) -> None:
    t = pd.to_datetime(pd.Series(times), utc=True).dropna()
    if len(t):
        assert t.max() < CUTOFF, f"{what}: max timestamp {t.max()} is not before {CUTOFF}"


def loader_and_resolver(basis: str):
    if basis == "production":
        b = tss._production_basis(CITIES)
        loader = forecast_conductor_refit.make_headline_loader(
            b["config_version"], set(b["differing"]), root=forecast_conductor_refit.REFIT_ROOT,
            frozen_manifest=forecast_conductor_refit.FROZEN_MANIFEST)
        return loader, city_point.production_city_point, b
    loader = forecast_conductor_refit.make_headline_loader(
        config.RATING_CONFIG_VERSION, frozenset(), root=forecast_conductor_refit.REFIT_ROOT,
        frozen_manifest=forecast_conductor_refit.FROZEN_MANIFEST)
    return loader, None, {"name": "frozen-drake"}


def hourly_amps(weather: pd.DataFrame, point) -> pd.DataFrame:
    """Hourly frame on a complete grid: dlr_amps under `point`, perpendicular wind, air temp, solar."""
    w = weather.copy()
    w["datetime_utc"] = pd.to_datetime(w["datetime_utc"], utc=True)
    w = w.drop_duplicates("datetime_utc").set_index("datetime_utc").sort_index()
    cols = ["air_temp", "wind_speed", "wind_direction", "solar_radiation"]
    num = w[cols].apply(pd.to_numeric, errors="coerce")
    ok = num.notna().all(axis=1) & np.isfinite(num.to_numpy(dtype=float)).all(axis=1)
    num = num.loc[ok]
    perp = thermal_model.perpendicular_wind(num["wind_speed"].to_numpy(float), num["wind_direction"].to_numpy(float),
                                            point.bearing_deg)
    dlr = np.asarray(thermal_model.ieee738_ampacity(num["air_temp"].to_numpy(float), perp,
                                                    num["solar_radiation"].to_numpy(float), point.conductor), dtype=float)
    out = pd.DataFrame({"air_temp": num["air_temp"].to_numpy(float), "wind_speed": np.asarray(perp, dtype=float),
                        "solar_radiation": num["solar_radiation"].to_numpy(float), "dlr_amps": dlr}, index=num.index)
    grid = pd.date_range(out.index.min(), out.index.max(), freq="h")
    return out.reindex(grid)


def training_frame_check(city: str, hourly_prod: pd.DataFrame) -> dict:
    """Compare the reconstructed hourly production series with the live model's own training frame on shared hours."""
    path = os.path.join(config.FORECAST_ML_MODEL_DIR, config.FORECAST_ML_TRAINING_FRAME_TEMPLATE.format(city=city))
    tf = pd.read_csv(path)
    tf["datetime_utc"] = pd.to_datetime(tf["datetime_utc"], utc=True)
    assert_before_cutoff(tf["datetime_utc"], f"training frame {city}")
    tf = tf.set_index("datetime_utc")
    common = tf.index.intersection(hourly_prod.dropna().index)
    res = {"n_common_hours": int(len(common)),
           "first": common.min().isoformat() if len(common) else None,
           "last": common.max().isoformat() if len(common) else None}
    for col in ("air_temp", "wind_speed", "solar_radiation", "dlr_amps"):
        d = np.abs(tf.loc[common, col].to_numpy(float) - hourly_prod.loc[common, col].to_numpy(float))
        res[f"max_abs_diff_{col}"] = float(d.max()) if d.size else None
        res[f"mean_abs_diff_{col}"] = float(d.mean()) if d.size else None
        res[f"share_exact_{col}"] = float(np.mean(d < 1e-6)) if d.size else None
    return res


def ml60_predictions(city: str, hourly_prod: pd.DataFrame, valid_times: pd.DatetimeIndex):
    model = ampacity_forecast._load_model(city)
    feats = ampacity_forecast.build_ml_features(hourly_prod)
    issue = valid_times - pd.Timedelta(minutes=config.FORECAST_HORIZON_MINUTES)
    assert_before_cutoff(issue, "ml issue times")
    at = feats.reindex(issue)
    ok = ~at.isnull().any(axis=1).to_numpy()
    vals = np.full(len(valid_times), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if ok.any():
            vals[ok] = np.asarray(model.predict(at.to_numpy(dtype=float)[ok]), dtype=float)
    return vals, ok, model


def spot_check_forecast_ampacity(city: str, hourly_prod: pd.DataFrame, valid_times, vals, n=5) -> list:
    """Call the real live entry point forecast_ampacity(method='ml') on a history ending at v-60 min."""
    out = []
    picks = np.linspace(0, len(valid_times) - 1, n).astype(int)
    for i in picks:
        v = valid_times[i]
        t = v - pd.Timedelta(hours=1)
        hist = hourly_prod.loc[t - pd.Timedelta(hours=23):t].dropna().copy()
        hist["datetime_utc"] = hist.index
        hist["city"] = city
        hist = hist.reset_index(drop=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = ampacity_forecast.forecast_ampacity(hist, method="ml")
        out.append({"valid_time": v.isoformat(), "forecast_ampacity_amps": None if r is None else r.amps,
                    "vectorised_amps": float(vals[i]),
                    "abs_diff": None if r is None else abs(r.amps - float(vals[i]))})
    return out


def main() -> int:
    assert os.path.isdir(os.path.join("data", "models", "conductor_refit")), "run from the repository root"
    window = confirm.ScoredWindow(tss.TEST_WINDOW_START, tss.TEST_WINDOW_END_EXCLUSIVE)
    checks = {"label": "exploratory, not pre-registered; does not change signed protocol v4 or read 1",
              "cutoff_exclusive": CUTOFF.isoformat(), "per_basis": {}}
    frames = {}
    for city in CITIES:
        frame, weather, meta = tss.cached_test_provider(city, evidence_dir=None)
        assert_before_cutoff(frame["datetime_utc"], f"{city} frame")
        assert_before_cutoff(frame["anchor_datetime_utc"], f"{city} frame anchors")
        assert_before_cutoff(weather["datetime_utc"], f"{city} weather")
        frames[city] = (frame, weather, meta)

    for basis in BASES:
        loader, resolver, binfo = loader_and_resolver(basis)
        rows = []
        bchecks = {}
        for city in CITIES:
            frame, weather, meta = frames[city]
            point = resolver(city) if resolver is not None else None
            stage = ["prepare"]
            prep_diag, preds, pred_diag, probe = confirm._score_city(
                frame, weather, city, window=window, point=point, model_loader=loader,
                extra_probe_arms=None, stage=stage)
            vt = pd.DatetimeIndex(preds["valid_time"])
            assert_before_cutoff(vt, f"{city} valid times")
            assert len(vt) == tss.TEST_SLOTS_PER_CITY, (city, len(vt))

            prod_point = city_point.production_city_point(city)
            hourly_prod = hourly_amps(weather, prod_point)
            assert_before_cutoff(hourly_prod.index, f"{city} hourly")
            truth_point = prod_point if basis == "production" else city_point.city_point(city)
            hourly_truth = hourly_amps(weather, truth_point)

            ml_vals, ml_ok, _ = ml60_predictions(city, hourly_prod, vt)
            naive = hourly_truth["dlr_amps"].reindex(vt - pd.Timedelta(hours=1)).to_numpy(float)

            # Same-truth check: the scorer's truth equals our hourly truth at the valid time.
            our_truth = hourly_truth["dlr_amps"].reindex(vt).to_numpy(float)
            truth_diff = float(np.nanmax(np.abs(our_truth - preds["truth_amps"].to_numpy(float))))

            df = pd.DataFrame({
                "city": city, "valid_time": vt, "anchor_time": pd.DatetimeIndex(preds["anchor_time"]),
                "truth_amps": preds["truth_amps"].to_numpy(float),
            })
            for name in ("ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h", "raw_forecast",
                         "persistence_24h"):
                df[name] = preds[name].to_numpy(float)
            df["ml_60min"] = ml_vals
            df["naive_60min"] = naive
            rows.append(df)

            cc = {
                "n_rows": int(len(df)),
                "scorer_mae": {n: float(np.nanmean(np.abs(df[n] - df["truth_amps"]))) for n in
                               ("ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h",
                                "raw_forecast", "persistence_24h")},
                "n_ml60_scored": int(np.isfinite(ml_vals).sum()),
                "n_naive60_scored": int(np.isfinite(naive).sum()),
                "max_abs_diff_scorer_truth_vs_hourly_truth": truth_diff,
                "leakage_probe_passed": bool(probe.get("passed")),
                "n_missing_from_reconstruction": prep_diag["n_missing_from_reconstruction"],
                "valid_time_hours_utc": sorted({int(h) for h in vt.hour}),
                "production_point_equals_drake_truth": bool(np.allclose(
                    hourly_amps(weather, prod_point)["dlr_amps"].dropna().to_numpy(),
                    hourly_amps(weather, city_point.city_point(city))["dlr_amps"].dropna().to_numpy())),
            }
            if basis == "production":
                cc["training_frame_check"] = training_frame_check(city, hourly_prod)
                cc["forecast_ampacity_spot_check"] = spot_check_forecast_ampacity(city, hourly_prod, vt, ml_vals)
            bchecks[city] = cc
        out = pd.concat(rows, ignore_index=True)
        assert_before_cutoff(out["valid_time"], "output")
        out.to_csv(os.path.join(OUT_DIR, f"rows_{basis}.csv"), index=False)
        checks["per_basis"][basis] = {"basis": {k: v for k, v in binfo.items() if k in ("name", "config_version",
                                                                                        "differing", "headline")},
                                      "served_artifacts": list(getattr(loader, "served", [])),
                                      "cities": bchecks}
    with open(os.path.join(OUT_DIR, "checks.json"), "w") as fh:
        json.dump(checks, fh, indent=2, default=str)
    print(json.dumps(checks, indent=1, default=str)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
