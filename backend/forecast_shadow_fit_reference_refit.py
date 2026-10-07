"""
One-time offline fit+commit script for the `reference_ml_refit_24h` shadow
candidate's persisted MLP artifact (Phase 5 Plan 04, D-03/D-04/D-09).

**Run once, offline -- never by the scheduled collector.** This script is
not imported by `forecast_shadow_pipeline.py`, `forecast_shadow_collect.py`,
or any other runtime path; it is invoked directly (`python
forecast_shadow_fit_reference_refit.py`) by a human, exactly once per
corridor (or re-run only if the pinned train-plus-validation window ever
needs to be extended). `forecast_shadow_collect.py`'s scheduled cycle never
calls anything in this module -- it only ever loads the `.joblib` artifact
this script writes, via `forecast_shadow_pipeline.load_correction_model`.

**Reuses, never reimplements.** Every step below calls an existing,
already-tested `forecast_experiment`/`forecast_training` function verbatim
-- the exact arm-5 recipe `forecast_experiment.fit_fitted_arms` already
runs (`backend/forecast_experiment.py` lines 1063-1140): `_stacked_pair_
frame` -> `_arm5_truth_frame` -> `forecast_training.build_training_matrix
(horizon_minutes=1440)` -> `forecast_training.fit_corridor_model(...,
CANDIDATE_ESTIMATORS["MLPRegressor"]())`. This script adds no new training
logic of its own; it only adds the "persist to `data/shadow/models/`"
step `fit_fitted_arms` itself never performs (that function returns the
fitted estimator in-memory for the audit harness, it never writes it to
disk).

**Sole output: one `.joblib` artifact per corridor, committed.**
`data/shadow/models/` is the one directory this project deliberately
carved out of `.gitignore` for exactly this purpose -- `.gitignore`'s own
comment: "`/data/shadow/models/` is DELIBERATELY NOT ignored (2026-10-06):
the trained .joblib artifacts there must reach the GitHub Actions runner,
which has no other way to obtain them (no network access to retrain...)".
This script's two output files (`reference_ml_refit_24h_<corridor>.joblib`)
land in that same carve-out, alongside the existing `ml_wind_corrected_*`/
`ml_cooling_corrected_*` artifacts.

**Never touches `ampacity_forecast`'s production model/cache (D-03).**
`forecast_training.fit_corridor_model` only ever calls `estimator.fit(...)`
-- it never calls `forecast_training.persist_corridor_model` (that
function targets `ampacity_forecast`'s own 60-minute production artifact
path) and never imports or touches `ampacity_forecast._load_corridor_model`
or its process-global per-corridor model cache.
"""

from __future__ import annotations

import config
import forecast_experiment
import forecast_experiment_audit
import forecast_shadow_pipeline
import forecast_training

_METHOD_NAME = "reference_ml_refit_24h"


def _train_val_window_end() -> str:
    """
    The calendar day immediately before `FROZEN_TEST_SPLIT_START`, as an
    ISO date string -- never the frozen test split itself (D-09: this
    offline fit must never read a FRESH-basis/test-split row).
    """
    import pandas as pd

    test_split_start = pd.Timestamp(forecast_experiment_audit.FROZEN_TEST_SPLIT_START)
    day_before = test_split_start - pd.Timedelta(days=1)
    return day_before.strftime("%Y-%m-%d")


def fit_and_save(corridor: str) -> str:
    """
    Fit `reference_ml_refit_24h`'s MLP estimator for `corridor` on the
    pinned train-plus-validation window, via arm 5's exact recipe, and
    persist it under `data/shadow/models/` via `forecast_shadow_pipeline.
    save_correction_model`.

    Calls, in this exact order, the three functions this task's `<action>`
    names: `forecast_experiment._arm5_truth_frame`, `forecast_training.
    build_training_matrix(horizon_minutes=1440)`, `forecast_training.
    fit_corridor_model(..., CANDIDATE_ESTIMATORS["MLPRegressor"]())`.

    Returns the path `save_correction_model` wrote to. Prints the row
    count the estimator was fit on (`len(X5)`) and the written path --
    this script's one piece of operational honesty: a reader running it
    later should see how much data the artifact was fit on without
    re-deriving it.
    """
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]

    train_val_frame = forecast_experiment._stacked_pair_frame(
        corridor,
        forecast_experiment_audit.FROZEN_WINDOW_START,
        _train_val_window_end(),
        lead_hours=config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS,
    )

    arm5_frame = forecast_experiment._arm5_truth_frame(train_val_frame, city_a, city_b)
    X5, y5 = forecast_training.build_training_matrix(arm5_frame, horizon_minutes=1440)
    estimator = forecast_training.fit_corridor_model(
        X5, y5, forecast_training.CANDIDATE_ESTIMATORS["MLPRegressor"]()
    )

    path = forecast_shadow_pipeline.save_correction_model(estimator, corridor, _METHOD_NAME)
    print(f"fit_and_save({corridor!r}): fit on {len(X5)} row(s) -- wrote {path!r}")
    return path


def main() -> None:
    for corridor in config.CORRIDOR_ENDPOINTS:
        path = fit_and_save(corridor)
        print(f"{corridor}: {path}")


if __name__ == "__main__":
    main()
