"""
Offline per-city refit of the three shadow ML candidates
(`ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h`).

**Run by a human, offline -- never by the scheduled collector.** Command:
`PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_fit_models.py
[--city CITY]` (default: every city in `config.LOCATIONS`). Each city writes
three artifacts, `data/shadow/models/{method}_{CITY}.joblib`, via
`forecast_shadow_pipeline.save_correction_model`.

Recipe (the frozen experiment's `forecast_experiment.fit_fitted_arms`,
re-run for ONE city instead of a two-city corridor):

* Arms 3/4 (`ml_wind_corrected`, `ml_cooling_corrected`) fit on the
  exact-24h-lead subset of that city's anchored pair frame, with
  `WIND_CONFIGURATION` (LinearRegression) but `pooling="per_city"` (a single
  city has no endpoint pair to pool; the frame carries a `city` column) and
  `COOLING_CONFIGURATION` (GradientBoostingRegressor, log_ratio target).
  Geometry is `city_point.city_point(city)`.
* Arm 5 (`reference_ml_refit_24h`) fits `MLPRegressor` on
  `build_training_matrix(truth_frame, horizon_minutes=1440)` where the truth
  frame is that city's OWN truth series and `dlr_amps` is that city's own
  IEEE 738 ampacity -- never a minimum across cities.

Data: the cached anchored pair frames under `config.
FORECAST_EXPERIMENT_CACHE_DIR` (git-ignored). If the cache file is missing
this module REFUSES to continue rather than let `anchored_pair_frame` issue
network calls.

Window: only rows strictly before `forecast_experiment_audit.
FROZEN_TEST_SPLIT_START` are ever used (asserted in `assert_no_test_leak`).

Fit window is TRAIN + VALIDATION (decision recorded 2026-10-12; full
rationale in `docs/data-science/decisions/shadow_collection_runbook.md`,
"Fit-window decision"). The original wind and cooling artifacts were fit on
the experiment's train split only (rows up to 2025-09-01T18:00Z, 2,360 per
city); the validation split (2025-09-02 .. 2026-03-16) was used to SELECT the
frozen `WIND_CONFIGURATION` / `COOLING_CONFIGURATION`, and selection is
finished, so the final fit uses the chosen configurations on train +
validation. The test split (2026-03-17 onward) is never read. Consequence:
the frozen experiment's validation/test numbers describe the train-only fits
and must not be quoted for these artifacts, which must not be scored on the
validation period.

Frozen helpers imported (unavoidable): from `forecast_experiment`:
`anchored_pair_frame`, `filter_to_exact_lead`, `_add_correction_columns`,
`_cache_path_for`, `WIND_CONFIGURATION`, `COOLING_CONFIGURATION`; from
`forecast_experiment_audit`: `FROZEN_WINDOW_START`, `FROZEN_WINDOW_END`,
`FROZEN_TEST_SPLIT_START`.

`forecast_shadow_fit_reference_refit.py` delegates its window rule, truth
frame construction and arm-5 fit to the shared functions here.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

import city_point
import config
import forecast_correction_models
import forecast_experiment
import forecast_experiment_audit
import forecast_shadow_pipeline
import forecast_training
import thermal_model

WIND_METHOD = "ml_wind_corrected"
COOLING_METHOD = "ml_cooling_corrected"
REFERENCE_METHOD = "reference_ml_refit_24h"
FIT_METHODS: tuple[str, ...] = (WIND_METHOD, COOLING_METHOD, REFERENCE_METHOD)

_LEAD_HOURS = 24
# Per-city wind: same estimator as the frozen WIND_CONFIGURATION, but there
# is no endpoint pair to pool over.
WIND_CONFIGURATION: dict = {**forecast_experiment.WIND_CONFIGURATION, "pooling": "per_city"}
COOLING_CONFIGURATION: dict = dict(forecast_experiment.COOLING_CONFIGURATION)


def train_val_window_end() -> str:
    """The calendar day before `FROZEN_TEST_SPLIT_START`, ISO date (D-09)."""
    split = pd.Timestamp(forecast_experiment_audit.FROZEN_TEST_SPLIT_START)
    return (split - pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def weather_to_arm5_frame(truth: pd.DataFrame, city: str, *, prefix: str = "") -> pd.DataFrame:
    """
    Shape one city's truth weather for `forecast_training.build_training_matrix`:
    `datetime_utc`, `dlr_amps` (that city's OWN IEEE 738 ampacity via
    `city_point.city_point(city)`), `air_temp`, `wind_speed`,
    `solar_radiation`. `prefix` is "truth_" for anchored-pair-frame columns.
    """
    point = city_point.city_point(city)
    truth = truth.sort_values("datetime_utc").reset_index(drop=True)
    air = truth[f"{prefix}air_temp"].to_numpy(dtype=float)
    wind = truth[f"{prefix}wind_speed"].to_numpy(dtype=float)
    solar = truth[f"{prefix}solar_radiation"].to_numpy(dtype=float)
    perp = thermal_model.perpendicular_wind(
        wind, truth[f"{prefix}wind_direction"].to_numpy(dtype=float), point.bearing_deg,
    )
    dlr_amps = np.asarray(thermal_model.ieee738_ampacity(air, perp, solar, point.conductor), dtype=float)
    return pd.DataFrame({
        "datetime_utc": truth["datetime_utc"], "dlr_amps": dlr_amps,
        "air_temp": air, "wind_speed": wind, "solar_radiation": solar,
    })


def fit_reference_estimator(arm5_frame: pd.DataFrame):
    """Arm 5: MLPRegressor on the 24h-ahead matrix. Returns (estimator, n_rows)."""
    X5, y5 = forecast_training.build_training_matrix(arm5_frame, horizon_minutes=1440)
    estimator = forecast_training.fit_model(
        X5, y5, forecast_training.CANDIDATE_ESTIMATORS["MLPRegressor"]()
    )
    return estimator, len(X5)


def assert_no_test_leak(frame: pd.DataFrame) -> None:
    """Raise AssertionError if any timestamp is on/after the frozen test split."""
    split = pd.Timestamp(forecast_experiment_audit.FROZEN_TEST_SPLIT_START, tz="UTC")
    for col in ("datetime_utc", "anchor_datetime_utc"):
        if col in frame.columns and len(frame):
            latest = pd.to_datetime(frame[col], utc=True).max()
            assert latest < split, (
                f"test-period leak: max {col} {latest} >= FROZEN_TEST_SPLIT_START {split}"
            )


def load_city_frame(city: str) -> pd.DataFrame:
    """
    The city's cached anchored pair frame over the frozen window, restricted
    to rows strictly before the test split. Refuses (no network) if the
    cache file is absent.
    """
    start = forecast_experiment_audit.FROZEN_WINDOW_START
    end = forecast_experiment_audit.FROZEN_WINDOW_END
    path = forecast_experiment._cache_path_for(city, start, end, lead_hours=_LEAD_HOURS)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"forecast_shadow_fit_models: cached frame for {city} missing at {path!r}; "
            f"refusing to call anchored_pair_frame (it would hit the network). "
            f"Rebuild the cache deliberately first (see shadow_collection_runbook.md)."
        )
    frame = forecast_experiment.anchored_pair_frame(city, start, end, lead_hours=_LEAD_HOURS)
    return restrict_to_train_val(frame)


def restrict_to_train_val(frame: pd.DataFrame) -> pd.DataFrame:
    split = pd.Timestamp(forecast_experiment_audit.FROZEN_TEST_SPLIT_START, tz="UTC")
    out = frame[pd.to_datetime(frame["datetime_utc"], utc=True) < split].reset_index(drop=True)
    return out


def fit_from_frame(city: str, frame: pd.DataFrame) -> dict:
    """
    Fit all three models for `city` from an (unfiltered) anchored pair
    frame. Returns `{"models": {method: model}, "n_rows_fit": {method: int}}`.
    Network-free; no artifact written.
    """
    frame = restrict_to_train_val(frame)
    assert_no_test_leak(frame)
    point = city_point.city_point(city)

    # Same city's own ampacity as the truth target everywhere.
    frame = frame.sort_values("datetime_utc").reset_index(drop=True)
    frame["truth_dlr_amps"] = weather_to_arm5_frame(frame, city, prefix="truth_")["dlr_amps"].to_numpy()
    frame["city"] = city

    exact = forecast_experiment.filter_to_exact_lead(frame, lead_hours=_LEAD_HOURS)
    exact = forecast_experiment._add_correction_columns(exact, point)
    assert_no_test_leak(exact)

    wind_model = forecast_correction_models.fit_wind_correction(
        exact,
        forecast_correction_models.WIND_CORRECTION_ESTIMATORS[WIND_CONFIGURATION["estimator"]],
        pooling=WIND_CONFIGURATION["pooling"],
    )
    cooling_model = forecast_correction_models.fit_cooling_correction(
        exact,
        forecast_correction_models.COOLING_CORRECTION_ESTIMATORS[COOLING_CONFIGURATION["estimator"]],
        target=COOLING_CONFIGURATION["target"], conductor=point.conductor,
    )

    arm5_frame = weather_to_arm5_frame(frame, city, prefix="truth_")
    assert_no_test_leak(arm5_frame)
    reference, n_ref = fit_reference_estimator(arm5_frame)

    return {
        "models": {WIND_METHOD: wind_model, COOLING_METHOD: cooling_model, REFERENCE_METHOD: reference},
        "n_rows_fit": {
            WIND_METHOD: int(wind_model.n_rows_fit),
            COOLING_METHOD: int(cooling_model.n_rows_fit),
            REFERENCE_METHOD: int(n_ref),
        },
    }


def fit_city(city: str, frame: pd.DataFrame | None = None) -> dict:
    """
    Fit and persist all three artifacts for `city`. `frame` defaults to the
    city's cached frame (`load_city_frame`). Returns `{"paths": {method:
    path}, "n_rows_fit": {method: int}}`.
    """
    city_point.city_point(city)  # closed-set guard: KeyError on an unknown city
    if frame is None:
        frame = load_city_frame(city)
    result = fit_from_frame(city, frame)
    paths = {
        method: forecast_shadow_pipeline.save_correction_model(model, city, method)
        for method, model in result["models"].items()
    }
    return {"paths": paths, "n_rows_fit": result["n_rows_fit"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Refit the three shadow ML candidates per city.")
    parser.add_argument("--city", choices=sorted(config.LOCATIONS), default=None,
                        help="one city (default: every city in config.LOCATIONS)")
    args = parser.parse_args(argv)
    cities = [args.city] if args.city else list(config.LOCATIONS)
    for city in cities:
        out = fit_city(city)
        for method in FIT_METHODS:
            print(f"{city} {method}: n_rows_fit={out['n_rows_fit'][method]} -> {out['paths'][method]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
