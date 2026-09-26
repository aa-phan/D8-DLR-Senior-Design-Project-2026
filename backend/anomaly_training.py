"""
Offline Anomaly Model Training (v1.3 Phase 2 Plan 02-01, ANOM-01)
==============================================================================
Standalone entry point -- NOT imported by the runtime pipeline, mirroring
`forecast_training.py`'s own offline-data-pull convention. It imports
`anomaly_detector` for `_model_path_for`, so training and runtime cannot
disagree on where a corridor's artifact lives, and `forecast_training` for
`fetch_city_weather`, so exactly one per-calendar-year Open-Meteo loop
exists in this repo. It also imports `DLRSafetyMonitor` solely to read its
`WIND_BOUNDS`/`TEMP_BOUNDS`/`SOLAR_BOUNDS` class attributes -- this import
is legal here, in the offline trainer, and remains forbidden inside
`anomaly_detector.py` itself (that module must never import
`DLRSafetyMonitor`).

Assembles a real, non-synthetic per-corridor raw-weather observation frame
by POOLING (not weakest-link-reducing) both endpoint cities' Open-Meteo
Archive backfill, drops rows outside `DLRSafetyMonitor`'s G3 physical
bounds or carrying a null/non-finite feature value, fits a `scikit-learn`
outlier estimator on the survivors, and persists the result atomically for
`anomaly_detector._load_corridor_model` to load.

Run directly:
    .venv/bin/python3 backend/anomaly_training.py --corridor AUSTIN_CORPUS_CHRISTI --years 1
"""

import argparse
import logging
import os
import tempfile

import numpy as np
import pandas as pd

import anomaly_detector
import config
import forecast_training
from DLRSafetyMonitor import DLRSafetyMonitor

logger = logging.getLogger(__name__)


def _make_isolation_forest_candidate(contamination):
    """
    Unfitted `IsolationForest` factory, parameterized by `contamination`
    (Plan 02-02 sweeps it across a measured false-positive evaluation, so
    this factory is parameterized from the start rather than reshaped
    later). Lazy `sklearn` import, matching `anomaly_detector.py`'s and
    `forecast_training.py`'s own estimator-touching functions -- importing
    this module stays free of a hard `sklearn` import.
    """
    from sklearn.ensemble import IsolationForest

    return IsolationForest(
        n_estimators=100,
        contamination=contamination,
        random_state=config.ANOMALY_ML_RANDOM_SEED,
    )


def corridor_observation_frame(corridor: str, years: int) -> pd.DataFrame:
    """
    The phase's real-data spine. For each of `corridor`'s two endpoint
    cities in `config.CORRIDOR_ENDPOINTS`, calls
    `forecast_training.fetch_city_weather(city, years)` and POOLS the two
    cities' rows by concatenation -- deliberately NOT the weakest-link
    `min()` reduction `forecast_training.corridor_training_frame`
    performs, because D-01 judges each city's own raw sensor reading
    against a plausible envelope, so both cities' readings are training
    examples in their own right and reducing them would discard half the
    envelope.

    Returns a frame with columns `datetime_utc`, `corridor`, `city`, and
    the three `config.ANOMALY_ML_FEATURE_COLUMNS`, sorted by
    `datetime_utc` then `city`.

    Before returning, drops two row classes and emits one aggregated
    warning line per class naming the dropped count: rows where any of
    the three feature values is null or not finite, and rows where any
    value falls outside the corresponding `DLRSafetyMonitor` bound. The
    bounds filter is what makes the learned envelope describe only
    readings that actually reach G6 in the live pipeline (G3 rejects the
    rest upstream), and it is also the mitigation for a poisoned or
    malformed backfill row skewing the envelope (T-02-01). Never imputes
    and never clips a value into range -- a dropped row is the only
    correct response.
    """
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]

    frames = []
    for city in (city_a, city_b):
        weather = forecast_training.fetch_city_weather(city, years)
        frames.append(pd.DataFrame({
            "datetime_utc": weather["datetime_utc"],
            "corridor": corridor,
            "city": city,
            "air_temp": weather["air_temp"],
            "wind_speed": weather["wind_speed"],
            "solar_radiation": weather["solar_radiation"],
        }))

    pooled = pd.concat(frames, ignore_index=True)
    feature_cols = list(config.ANOMALY_ML_FEATURE_COLUMNS)

    finite_mask = pd.Series(True, index=pooled.index)
    for column in feature_cols:
        finite_mask &= np.isfinite(pd.to_numeric(pooled[column], errors="coerce"))
    null_or_nonfinite_dropped = int((~finite_mask).sum())

    bound_pairs = (
        ("wind_speed", DLRSafetyMonitor.WIND_BOUNDS),
        ("air_temp", DLRSafetyMonitor.TEMP_BOUNDS),
        ("solar_radiation", DLRSafetyMonitor.SOLAR_BOUNDS),
    )
    bounds_mask = pd.Series(True, index=pooled.index)
    for column, (lo, hi) in bound_pairs:
        bounds_mask &= pooled[column].between(lo, hi)

    # Only count out-of-bounds drops among rows that already passed the
    # finite check, so the two logged counts partition the dropped rows
    # rather than double-counting a row that is both null and out of range.
    out_of_bounds_dropped = int((finite_mask & ~bounds_mask).sum())

    if null_or_nonfinite_dropped:
        logger.warning(
            "corridor_observation_frame: dropped %d row(s) for %s with a "
            "null or non-finite feature value",
            null_or_nonfinite_dropped, corridor,
        )
    if out_of_bounds_dropped:
        logger.warning(
            "corridor_observation_frame: dropped %d row(s) for %s outside "
            "DLRSafetyMonitor's G3 physical bounds",
            out_of_bounds_dropped, corridor,
        )

    keep = finite_mask & bounds_mask
    result = pooled.loc[keep, ["datetime_utc", "corridor", "city"] + feature_cols]
    return result.sort_values(["datetime_utc", "city"]).reset_index(drop=True)


def build_feature_matrix(frame: pd.DataFrame) -> np.ndarray:
    """
    Raises `ValueError` naming the missing column(s) when any of
    `config.ANOMALY_ML_FEATURE_COLUMNS` is absent from `frame`, then
    returns that column subset, in exactly that tuple's order, as a
    float64 two-dimensional array. One implementation; the runtime's
    single-row construction in `anomaly_detector._check_against_model`
    reads the same two config tuples, so column order cannot drift
    between training and inference.
    """
    feature_cols = list(config.ANOMALY_ML_FEATURE_COLUMNS)
    missing = [c for c in feature_cols if c not in frame.columns]
    if missing:
        raise ValueError(
            f"build_feature_matrix: frame is missing required column(s) {missing}"
        )
    return frame[feature_cols].to_numpy(dtype=float)


def fit_corridor_model(X: np.ndarray, estimator):
    """
    Invoke `estimator`'s (already-constructed, unfitted) training entry
    point on `X` and return it fitted. This module is the only place in
    the repo where an anomaly estimator is trained.
    """
    estimator.fit(X)
    return estimator


def persist_corridor_model(model, corridor: str) -> str:
    """
    Persist `model` for `corridor` atomically: create
    `config.ANOMALY_ML_MODEL_DIR` if absent, resolve the final path
    through `anomaly_detector._model_path_for` (so training and runtime
    agree on one path convention), `joblib.dump` to a temp file in that
    same directory with a `.joblib.tmp` suffix, then `os.replace` it onto
    the final path. On any failure, removes the temp file and re-raises.
    Returns the final path.

    The temp-then-replace is the interruption/concurrency guarantee -- a
    killed or racing training run can never leave a torn `.joblib` for the
    runtime loader to deserialize (T-02-06).
    """
    import joblib

    os.makedirs(config.ANOMALY_ML_MODEL_DIR, exist_ok=True)
    final_path = anomaly_detector._model_path_for(corridor)

    fd, tmp_path = tempfile.mkstemp(
        dir=config.ANOMALY_ML_MODEL_DIR, suffix=".joblib.tmp"
    )
    os.close(fd)
    try:
        joblib.dump(model, tmp_path)
        os.replace(tmp_path, final_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return final_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Assemble a real, Open-Meteo-derived pooled per-corridor raw "
            "weather observation frame, fit, and atomically persist an "
            "anomaly-detection outlier estimator."
        )
    )
    parser.add_argument(
        "--corridor",
        choices=sorted(config.CORRIDOR_ENDPOINTS),
        default=None,
        help="Corridor to train. Default: every corridor in config.CORRIDOR_ENDPOINTS.",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=config.ANOMALY_ML_TRAINING_YEARS,
        help="Complete calendar years of Open-Meteo backfill per endpoint "
             "city (default: config.ANOMALY_ML_TRAINING_YEARS).",
    )
    args = parser.parse_args(argv)

    corridors = [args.corridor] if args.corridor else sorted(config.CORRIDOR_ENDPOINTS)

    for corridor in corridors:
        try:
            frame = corridor_observation_frame(corridor, args.years)
        except Exception:
            logger.exception(
                "anomaly_training: failed assembling corridor %s -- "
                "continuing to the next corridor", corridor,
            )
            print(f"{corridor}: FAILED to assemble observation frame -- see log")
            continue

        os.makedirs(config.ANOMALY_ML_MODEL_DIR, exist_ok=True)
        frame_path = os.path.join(
            config.ANOMALY_ML_MODEL_DIR,
            config.ANOMALY_ML_OBSERVATION_FRAME_TEMPLATE.format(corridor=corridor),
        )
        frame.to_csv(frame_path, index=False)

        X = build_feature_matrix(frame)
        model = fit_corridor_model(
            X, _make_isolation_forest_candidate(config.ANOMALY_ML_CONTAMINATION)
        )
        model_path = persist_corridor_model(model, corridor)

        start = frame["datetime_utc"].min()
        end = frame["datetime_utc"].max()
        print(
            f"{corridor}: {len(frame)} rows, {start} -> {end}, "
            f"model persisted to {model_path}"
        )


if __name__ == "__main__":
    main()
