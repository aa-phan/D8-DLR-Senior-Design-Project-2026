"""
One-time offline fit+commit script for the `reference_ml_refit_24h` shadow
candidate's persisted MLP artifact (Phase 5 Plan 04, D-03/D-04/D-09),
fitted PER CITY since 2026-10-12 (`docs/data-science/decisions/
point_scope.md`).

**Run once per city, offline -- never by the scheduled collector.** This
script is not imported by `forecast_shadow_pipeline.py`,
`forecast_shadow_collect.py`, or any other runtime path; it is invoked
directly (`python forecast_shadow_fit_reference_refit.py`) by a human, once
per city in `config.LOCATIONS` (or re-run only if the pinned
train-plus-validation window ever needs to be extended). The scheduled
cycle never calls anything in this module -- it only ever loads the
`.joblib` artifact this script writes, via `forecast_shadow_pipeline.
load_correction_model`. All four cities were fit on 2026-10-13 and the
artifacts are committed and hashed in `data/shadow/models/
ARTIFACT_HASHES.sha256`; nothing is refit after the 2026-11-01 model freeze.
A city with no artifact reports `status="unavailable"` with a named reason
(the `FileNotFoundError` path) for `reference_ml_refit_24h`, never a crash.

**Target: that city's own ampacity.** The training series is one city's
own archived truth weather (`open_meteo_provider.fetch_open_meteo`, the
same Archive API source the frozen experiment's truth side used) run
through `thermal_model.ieee738_ampacity` with `city_point.city_point(city)`'s
bearing and conductor -- never a minimum over two cities. The recipe is
otherwise arm 5's: `forecast_training.build_training_matrix(horizon_minutes
=1440)` -> `forecast_training.fit_model(..., CANDIDATE_ESTIMATORS[
"MLPRegressor"]())`.

**Pinned window.** Starts at `forecast_experiment_audit.FROZEN_WINDOW_START`
and ends the day before `forecast_experiment_audit.FROZEN_TEST_SPLIT_START`
(never the frozen test split itself -- D-09). Those two CONSTANTS are the
only things imported from the frozen audit module; no corridor builder
(`_stacked_pair_frame`, `_arm5_truth_frame`, `legacy_corridor`) is used.

**Sole output: one `.joblib` artifact per city, committed.**
`data/shadow/models/` is the one directory this project deliberately
carved out of `.gitignore` for exactly this purpose -- `.gitignore`'s own
comment: "`/data/shadow/models/` is DELIBERATELY NOT ignored (2026-10-06):
the trained .joblib artifacts there must reach the GitHub Actions runner,
which has no other way to obtain them (no network access to retrain...)".
Each output file is `reference_ml_refit_24h_<CITY>.joblib`, alongside the
per-city `ml_wind_corrected_*`/`ml_cooling_corrected_*` artifacts. Legacy
corridor-named artifacts there are not loaded and not touched.

**Never touches `ampacity_forecast`'s production model/cache (D-03).**
`forecast_training.fit_model` only ever calls `estimator.fit(...)` -- it
never calls `forecast_training.persist_model` (that function targets
`ampacity_forecast`'s own 60-minute production artifact path) and never
imports or touches `ampacity_forecast._load_model` or its process-global
per-city model cache.
"""

from __future__ import annotations

import config
import city_point
import forecast_experiment_audit
import forecast_shadow_fit_models
import forecast_shadow_pipeline
import open_meteo_provider

_METHOD_NAME = forecast_shadow_fit_models.REFERENCE_METHOD


def _train_val_window_end() -> str:
    """Delegates to `forecast_shadow_fit_models.train_val_window_end` (day before the test split)."""
    return forecast_shadow_fit_models.train_val_window_end()


def _city_truth_frame(city: str, start: str, end: str):
    """
    `city`'s own hourly archive truth over `[start, end]` (network), shaped
    by the shared `forecast_shadow_fit_models.weather_to_arm5_frame`.
    """
    lat, lon = city_point.city_point(city).coord
    truth = open_meteo_provider.fetch_open_meteo(lat, lon, start, end)
    return forecast_shadow_fit_models.weather_to_arm5_frame(truth, city)


def fit_and_save(city: str) -> str:
    """
    Fit ONLY `reference_ml_refit_24h` for `city` from live Archive-API truth
    (network) and persist it. The offline, cache-based refit of all three
    candidates is `forecast_shadow_fit_models.fit_city`; both share the same
    arm-5 fit (`fit_reference_estimator`). Returns the path written.
    """
    arm5_frame = _city_truth_frame(
        city, forecast_experiment_audit.FROZEN_WINDOW_START, _train_val_window_end(),
    )
    estimator, n_rows = forecast_shadow_fit_models.fit_reference_estimator(arm5_frame)
    path = forecast_shadow_pipeline.save_correction_model(estimator, city, _METHOD_NAME)
    print(f"fit_and_save({city!r}): fit on {n_rows} row(s) -- wrote {path!r}")
    return path


def main() -> None:
    for city in config.LOCATIONS:
        path = fit_and_save(city)
        print(f"{city}: {path}")


if __name__ == "__main__":
    main()
