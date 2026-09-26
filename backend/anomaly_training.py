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

v1.3 Phase 2 (02-03, ANOM-01/D-02) also imports `ercot_data_retriever` at
module scope: `characterize_load` runs D-02's training-time-only ERCOT
load characterization here, in the offline trainer, where this import is
legal. `anomaly_detector.py` must never import `ercot_data_retriever` or
`gridstatus` -- a test in `backend/tests/anomaly_training_test.py` asserts
this boundary holds, since `raw_data` carries no load value at the live
`check()` call site and wiring one in is Track 1's scope, not this
workstream's.

Run directly:
    .venv/bin/python3 backend/anomaly_training.py --corridor AUSTIN_CORPUS_CHRISTI --years 1
"""

import argparse
import json
import logging
import math
import os
import tempfile

import numpy as np
import pandas as pd

import anomaly_detector
import config
import corridor_discretization
import ercot_data_retriever
import forecast_training
import thermal_model
from DLRSafetyMonitor import DLRSafetyMonitor

logger = logging.getLogger(__name__)

# Plan 02-02 (ANOM-02): fixed margin by which _out_of_range_value pushes a
# feature outside its DLRSafetyMonitor bound -- comfortably beyond the
# gate so the injected value is unambiguously physically impossible
# rather than marginal.
_OUT_OF_RANGE_MARGINS: dict = {
    "wind_speed": 30.0,
    "air_temp": 35.0,
    "solar_radiation": 600.0,
}

# Column -> DLRSafetyMonitor bound, shared by _out_of_range_value and
# inject_anomalies' in-range-implausible bounds assertions.
_COLUMN_BOUNDS: dict = {
    "wind_speed": DLRSafetyMonitor.WIND_BOUNDS,
    "air_temp": DLRSafetyMonitor.TEMP_BOUNDS,
    "solar_radiation": DLRSafetyMonitor.SOLAR_BOUNDS,
}

# The extreme quantiles _implausible_combination draws each component
# from -- high for solar (bright), low for temp and wind (cold, still) --
# the classic "clear cold night" combination that is individually
# plausible on each axis but implausible jointly (02-RESEARCH.md Open
# Question 2).
_IMPLAUSIBLE_QUANTILE_HIGH: float = 0.97
_IMPLAUSIBLE_QUANTILE_LOW: float = 0.03


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


# ──────────────────────────────────────────────────────────────────────────────
# ANOM-02 measurement machinery (v1.3 Phase 2 Plan 02-02)
# ──────────────────────────────────────────────────────────────────────────────


def chronological_split(
    frame: pd.DataFrame, holdout_fraction: float = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split `frame` (any `datetime_utc`-bearing frame this module produces)
    into a strictly time-ordered (fit, holdout) pair for ROADMAP SC4's
    false-positive/recall measurement: sorts by `datetime_utc`, splits at
    `int(len(frame) * (1 - holdout_fraction))`, and resets both sides'
    indexes. Every fit-slice timestamp is <= the holdout slice's minimum
    timestamp -- the estimator is measured only against rows strictly
    later than anything it was fitted on (T-02-08). Called twice on the
    same frame returns identical slices (pure function of the input).

    Defaults `holdout_fraction` from `config.ANOMALY_ML_VALIDATION_
    HOLDOUT_FRACTION`. Raises `ValueError` naming the row counts when
    either resulting side would be empty, or when the fit side would hold
    fewer rows than `anomaly_detector.ROLLING_BASELINE_MIN_ROWS` -- below
    that floor the rolling-baseline arm this measurement also scores
    cannot even be constructed.
    """
    if holdout_fraction is None:
        holdout_fraction = config.ANOMALY_ML_VALIDATION_HOLDOUT_FRACTION

    sorted_frame = frame.sort_values("datetime_utc").reset_index(drop=True)
    split_index = int(len(sorted_frame) * (1 - holdout_fraction))

    fit = sorted_frame.iloc[:split_index].reset_index(drop=True)
    holdout = sorted_frame.iloc[split_index:].reset_index(drop=True)

    if len(fit) == 0 or len(holdout) == 0:
        raise ValueError(
            f"chronological_split: split produced an empty side "
            f"(fit={len(fit)}, holdout={len(holdout)}) from "
            f"{len(sorted_frame)} total row(s) at holdout_fraction="
            f"{holdout_fraction}"
        )
    if len(fit) < anomaly_detector.ROLLING_BASELINE_MIN_ROWS:
        raise ValueError(
            f"chronological_split: fit slice has {len(fit)} row(s), below "
            f"anomaly_detector.ROLLING_BASELINE_MIN_ROWS "
            f"({anomaly_detector.ROLLING_BASELINE_MIN_ROWS}) -- the "
            f"rolling-baseline arm cannot be constructed from it"
        )

    return fit, holdout


def _out_of_range_value(column: str) -> float:
    """
    A value outside `column`'s `DLRSafetyMonitor` bound by
    `_OUT_OF_RANGE_MARGINS[column]` -- comfortably beyond the physical
    gate (never a marginal, borderline value) so the "out_of_range"
    injection category is unambiguous.
    """
    lo, hi = _COLUMN_BOUNDS[column]
    return hi + _OUT_OF_RANGE_MARGINS[column]


def _implausible_combination(fit_frame: pd.DataFrame) -> dict:
    """
    The "in_range_implausible" injection category's three-value triple:
    the high quantile of `solar_radiation`, the low quantile of
    `air_temp`, and the low quantile of `wind_speed`, each computed from
    `fit_frame`'s own OBSERVED column values (the nearest-rank quantile,
    never pandas' default linearly-INTERPOLATED quantile) -- so each
    component is a value the real data actually contains, and only the
    simultaneous combination (bright + cold + still) is jointly novel.
    This is what makes this category test G6's unique multivariate
    contribution rather than re-testing G3's per-variable range gate
    (02-RESEARCH.md Open Question 2): every component individually passes
    the range gate and individually occurs in the record; only the
    combination does not.
    """

    def _observed_quantile(series: pd.Series, quantile: float) -> float:
        sorted_vals = series.sort_values().reset_index(drop=True)
        idx = int(round(quantile * (len(sorted_vals) - 1)))
        return float(sorted_vals.iloc[idx])

    return {
        "solar_radiation": _observed_quantile(
            fit_frame["solar_radiation"], _IMPLAUSIBLE_QUANTILE_HIGH
        ),
        "air_temp": _observed_quantile(
            fit_frame["air_temp"], _IMPLAUSIBLE_QUANTILE_LOW
        ),
        "wind_speed": _observed_quantile(
            fit_frame["wind_speed"], _IMPLAUSIBLE_QUANTILE_LOW
        ),
    }


def inject_anomalies(
    frame: pd.DataFrame,
    category: str,
    rng=None,
    rate: float = None,
    fit_frame: pd.DataFrame = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Returns a NEW, corrupted copy of `frame` (never mutates the input --
    T-02-07) plus a boolean `pd.Series` mask (indexed like `frame`) naming
    which rows were injected. `round(len(frame) * rate)` distinct row
    positions are selected via `rng.choice(..., replace=False)`.

    `category="out_of_range"`: each injected row has exactly ONE of
    `config.ANOMALY_ML_FEATURE_COLUMNS` (chosen per-row via `rng`)
    replaced by `_out_of_range_value` for that column -- a value
    `DLRSafetyMonitor`'s own G3 range gate would already reject.

    `category="in_range_implausible"`: every injected row has ALL THREE
    feature values replaced simultaneously by the SAME triple from
    `_implausible_combination(fit_frame)` -- requires `fit_frame` (raises
    `ValueError` naming the requirement when omitted for this category).

    `rng` defaults to `numpy.random.default_rng(config.ANOMALY_ML_
    RANDOM_SEED)`; `rate` defaults to `config.ANOMALY_ML_INJECTION_RATE`.
    Repeating the call with the same seed and rate reproduces an
    identical mask and an identical injected frame.

    Raises `ValueError` naming the valid categories for an unrecognized
    `category`.
    """
    valid_categories = ("out_of_range", "in_range_implausible")
    if category not in valid_categories:
        raise ValueError(
            f"inject_anomalies: unknown category {category!r}; valid "
            f"categories: {valid_categories}"
        )
    if category == "in_range_implausible" and fit_frame is None:
        raise ValueError(
            "inject_anomalies: category 'in_range_implausible' requires "
            "fit_frame (the triple is drawn from the FIT slice's own "
            "extreme quantiles, never the frame being injected into)"
        )

    if rng is None:
        rng = np.random.default_rng(config.ANOMALY_ML_RANDOM_SEED)
    if rate is None:
        rate = config.ANOMALY_ML_INJECTION_RATE

    n_inject = round(len(frame) * rate)
    positions = np.sort(rng.choice(len(frame), size=n_inject, replace=False))

    injected = frame.copy(deep=True)
    mask = pd.Series(False, index=frame.index)
    mask.iloc[positions] = True

    feature_cols = list(config.ANOMALY_ML_FEATURE_COLUMNS)

    if category == "out_of_range":
        chosen_cols = rng.choice(feature_cols, size=len(positions))
        for pos, column in zip(positions, chosen_cols):
            injected.iloc[
                pos, injected.columns.get_loc(column)
            ] = _out_of_range_value(column)
    else:
        triple = _implausible_combination(fit_frame)
        for column, value in triple.items():
            injected.iloc[positions, injected.columns.get_loc(column)] = value

    return injected, mask


def _dlr_amps_for(frame: pd.DataFrame, corridor: str) -> np.ndarray:
    """
    Converts `frame`'s three raw feature columns into a `dlr_amps` series
    using `corridor_discretization.corridor_geometry(corridor)`'s
    `ConductorConfig` and `thermal_model.ieee738_ampacity`, reproducing
    `DLRSafetyMonitor._compute_ampacity`'s exact call (`T_amb_c=air_temp`,
    `wind_perp_ms=wind_speed`, `ghi_wm2=solar_radiation`, default
    `solar_altitude_deg`) -- the raw `wind_speed` reading IS the value the
    live pipeline feeds as `wind_perp_ms` (`raw_data` carries no separate
    direction field, D-01), so this reproduces the monitor's real physics
    call rather than a separate perpendicular-wind computation. This is
    the one conversion both the baseline's history and the baseline's
    scored rows go through, so both sides of the comparison sit on the
    same physics. Explicit float cast -- `ieee738_ampacity` returns an
    array even for scalar input (RESEARCH.md Pitfall 2).
    """
    geometry = corridor_discretization.corridor_geometry(corridor)
    amps = thermal_model.ieee738_ampacity(
        T_amb_c=frame["air_temp"].to_numpy(dtype=float),
        wind_perp_ms=frame["wind_speed"].to_numpy(dtype=float),
        ghi_wm2=frame["solar_radiation"].to_numpy(dtype=float),
        conductor=geometry.conductor,
    )
    return np.asarray(amps, dtype=float)


def score_model(model, frame: pd.DataFrame) -> np.ndarray:
    """
    Boolean array, one entry per row of `frame`, true where `model`'s
    prediction entry point returns the scikit-learn outlier label (`-1`).
    Builds the feature matrix through the existing `build_feature_matrix`
    -- one call on the whole matrix, never a per-row loop.
    """
    X = build_feature_matrix(frame)
    predictions = model.predict(X)
    return predictions == -1


def score_rolling_baseline(
    corridor: str, fit_frame: pd.DataFrame, frame: pd.DataFrame
) -> np.ndarray:
    """
    Scores `frame` through the EXISTING `AnomalyDetector._check_against_
    rolling_baseline` branch -- never a reimplementation of its band
    arithmetic. Builds `AnomalyDetector.for_corridor(corridor, history=
    <fit_frame with its derived dlr_amps column>, load_model=False)` (so
    `self.model` stays `None` and only the heuristic baseline can fire),
    then for each row of `frame` converts that row's raw readings through
    `_dlr_amps_for` and calls `detector.check({}, rating)`. Passing an
    empty `raw_data` is correct and deliberate: this arm reads only
    `rating`, and `load_model=False` guarantees the (possibly-provisioned)
    model branch cannot contaminate the baseline's own numbers. Returns
    the boolean verdicts, one per row of `frame`.
    """
    history = fit_frame.copy()
    history["dlr_amps"] = _dlr_amps_for(fit_frame, corridor)

    detector = anomaly_detector.AnomalyDetector.for_corridor(
        corridor, history=history, load_model=False,
    )

    ratings = _dlr_amps_for(frame, corridor)
    verdicts = np.empty(len(frame), dtype=bool)
    for i, rating in enumerate(ratings):
        is_anomalous, _ = detector.check({}, float(rating))
        verdicts[i] = is_anomalous
    return verdicts


def validate_candidate(
    corridor: str,
    fit_frame: pd.DataFrame,
    holdout_frame: pd.DataFrame,
    name: str,
    factory,
    contamination: float,
) -> dict:
    """
    Measures both halves of ANOM-02's bar for one (candidate,
    contamination) pair, for the model AND for the existing rolling
    mean-and-standard-deviation baseline, on the IDENTICAL rows:

    - `false_positive_rate` / `baseline_false_positive_rate`: the
      fraction of the UN-INJECTED `holdout_frame` each detector flags.
      This is the clean false-positive denominator -- no injected row
      contributes to it (this plan's own second prohibition).
    - `recall_out_of_range` / `baseline_recall_out_of_range` and
      `recall_in_range_implausible` / `baseline_recall_in_range_
      implausible`: the fraction of each injection category's injected
      rows each detector flags, computed only over that category's
      injected mask positions.
    - `recall_pooled` / `baseline_recall_pooled`: the pooled recall
      across both injection categories.

    Fits a FRESH `factory(contamination)` estimator on `fit_frame`'s
    feature matrix. For `name == "OneClassSVM"` only, the training rows
    are capped at `config.ANOMALY_ML_SVM_MAX_TRAIN_ROWS`, taking the
    chronologically-earliest rows of `fit_frame` so the cap never
    reorders time; the actually-used row count is recorded so that arm's
    score is read with the cap in view.
    """
    fit_for_training = fit_frame
    if name == "OneClassSVM":
        cap = config.ANOMALY_ML_SVM_MAX_TRAIN_ROWS
        if len(fit_frame) > cap:
            fit_for_training = (
                fit_frame.sort_values("datetime_utc").iloc[:cap].reset_index(drop=True)
            )
    train_rows_used = len(fit_for_training)

    X_fit = build_feature_matrix(fit_for_training)
    estimator = fit_corridor_model(X_fit, factory(contamination))

    # Clean false-positive rate -- the un-injected holdout only.
    model_fp_flags = score_model(estimator, holdout_frame)
    baseline_fp_flags = score_rolling_baseline(corridor, fit_frame, holdout_frame)
    clean_rows = len(holdout_frame)

    seed_rng = np.random.default_rng(config.ANOMALY_ML_RANDOM_SEED)
    injected_out, mask_out = inject_anomalies(
        holdout_frame, "out_of_range", rng=seed_rng,
    )
    seed_rng_2 = np.random.default_rng(config.ANOMALY_ML_RANDOM_SEED)
    injected_implausible, mask_implausible = inject_anomalies(
        holdout_frame, "in_range_implausible", rng=seed_rng_2, fit_frame=fit_frame,
    )

    mask_out_np = mask_out.to_numpy()
    mask_implausible_np = mask_implausible.to_numpy()

    model_out_flags = score_model(estimator, injected_out)[mask_out_np]
    model_implausible_flags = score_model(estimator, injected_implausible)[
        mask_implausible_np
    ]
    baseline_out_flags = score_rolling_baseline(
        corridor, fit_frame, injected_out
    )[mask_out_np]
    baseline_implausible_flags = score_rolling_baseline(
        corridor, fit_frame, injected_implausible
    )[mask_implausible_np]

    pooled_model_flags = np.concatenate([model_out_flags, model_implausible_flags])
    pooled_baseline_flags = np.concatenate(
        [baseline_out_flags, baseline_implausible_flags]
    )

    return {
        "candidate": name,
        "contamination": float(contamination),
        "false_positive_rate": float(np.mean(model_fp_flags)),
        "baseline_false_positive_rate": float(np.mean(baseline_fp_flags)),
        "recall_out_of_range": float(np.mean(model_out_flags)),
        "recall_in_range_implausible": float(np.mean(model_implausible_flags)),
        "recall_pooled": float(np.mean(pooled_model_flags)),
        "baseline_recall_out_of_range": float(np.mean(baseline_out_flags)),
        "baseline_recall_in_range_implausible": float(
            np.mean(baseline_implausible_flags)
        ),
        "baseline_recall_pooled": float(np.mean(pooled_baseline_flags)),
        "fit_rows": int(len(fit_frame)),
        "holdout_rows": int(len(holdout_frame)),
        "clean_rows": int(clean_rows),
        "injected_rows_out_of_range": int(mask_out.sum()),
        "injected_rows_in_range_implausible": int(mask_implausible.sum()),
        "train_rows_used": int(train_rows_used),
    }


def _run_validate(corridors, years):
    """
    Task 1's single-candidate (`IsolationForest`) measurement loop across
    `config.ANOMALY_ML_CONTAMINATION_GRID` -- Task 2's `--bakeoff` extends
    this to the full three-candidate comparison via `corridor_report`/
    `select_winner`. For each corridor: assemble the real observation
    frame (written to disk exactly like `main`'s plain training loop),
    split it chronologically, measure every contamination grid point,
    print a fixed-width table, and accumulate one JSON report.
    """
    reports = {}

    for corridor in corridors:
        try:
            frame = corridor_observation_frame(corridor, years)
        except Exception:
            logger.exception(
                "anomaly_training --validate: failed assembling corridor "
                "%s -- continuing to the next corridor", corridor,
            )
            print(f"{corridor}: FAILED to assemble observation frame -- see log")
            continue

        os.makedirs(config.ANOMALY_ML_MODEL_DIR, exist_ok=True)
        frame_path = os.path.join(
            config.ANOMALY_ML_MODEL_DIR,
            config.ANOMALY_ML_OBSERVATION_FRAME_TEMPLATE.format(corridor=corridor),
        )
        frame.to_csv(frame_path, index=False)

        fit_frame, holdout_frame = chronological_split(frame)

        measurements = [
            validate_candidate(
                corridor, fit_frame, holdout_frame,
                "IsolationForest", _make_isolation_forest_candidate, contamination,
            )
            for contamination in config.ANOMALY_ML_CONTAMINATION_GRID
        ]

        reports[corridor] = {
            "corridor": corridor,
            "rows": int(len(frame)),
            "window_start": pd.Timestamp(frame["datetime_utc"].min()).isoformat(),
            "window_end": pd.Timestamp(frame["datetime_utc"].max()).isoformat(),
            "fit_rows": int(len(fit_frame)),
            "holdout_rows": int(len(holdout_frame)),
            "measurements": measurements,
        }

        print(f"\n{corridor}: {len(frame)} rows")
        print(
            f"{'contamination':<15}{'fp_rate':>10}{'baseline_fp':>13}"
            f"{'recall_oor':>12}{'recall_irp':>12}{'recall_pooled':>15}"
        )
        for m in measurements:
            print(
                f"{m['contamination']:<15.4f}{m['false_positive_rate']:>10.4f}"
                f"{m['baseline_false_positive_rate']:>13.4f}"
                f"{m['recall_out_of_range']:>12.4f}"
                f"{m['recall_in_range_implausible']:>12.4f}"
                f"{m['recall_pooled']:>15.4f}"
            )

    os.makedirs(config.ANOMALY_ML_MODEL_DIR, exist_ok=True)
    report_path = os.path.join(
        config.ANOMALY_ML_MODEL_DIR, config.ANOMALY_ML_VALIDATION_REPORT_NAME
    )
    with open(report_path, "w") as fh:
        json.dump(reports, fh, indent=2)
    print(f"\nvalidation report written to {report_path}")


# ──────────────────────────────────────────────────────────────────────────────
# D-03 three-candidate bake-off (v1.3 Phase 2 Plan 02-02, Task 2)
# ──────────────────────────────────────────────────────────────────────────────


def _make_elliptic_envelope_candidate(contamination):
    """
    Unfitted `EllipticEnvelope` factory, parameterized by `contamination`,
    mirroring `_make_isolation_forest_candidate`'s lazy-import discipline.
    This arm assumes an elliptical (Gaussian) joint distribution over the
    three variables, which irradiance's hard night-time zero floor
    plausibly violates -- 02-RESEARCH.md's own "Alternatives Considered"
    names this doubt explicitly. It is measured here rather than assumed
    away, per D-04's instruction to evaluate on real measured rates
    instead of defaulting out of caution.
    """
    from sklearn.covariance import EllipticEnvelope

    return EllipticEnvelope(
        contamination=contamination, random_state=config.ANOMALY_ML_RANDOM_SEED,
    )


def _make_one_class_svm_candidate(contamination):
    """
    Unfitted `OneClassSVM` factory (RBF kernel, `gamma="scale"`, `nu` set
    to `contamination`), wrapped in `make_pipeline(StandardScaler(),
    OneClassSVM(...))`. The scaler is present for the same reason Phase
    1's neural-network bake-off arm wrapped `MLPRegressor`: this estimator
    is scale-sensitive in a way the tree candidate is not, and the three
    raw features span metres per second, degrees Celsius, and watts per
    square metre -- an unscaled fit would measure a missing preprocessing
    step, not the architecture D-03 is actually asking about.
    """
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import OneClassSVM

    return make_pipeline(
        StandardScaler(),
        OneClassSVM(nu=contamination, kernel="rbf", gamma="scale"),
    )


# D-03's three candidates, in the order isolation forest, elliptic
# envelope, one-class SVM -- a zero-argument-except-contamination
# factory per entry (never a shared instance), since every contamination
# grid point must fit a FRESH, never-before-fitted estimator. Order is
# significant: it is `select_winner`'s last-resort deterministic
# tiebreak, mirroring `forecast_training.CANDIDATE_ESTIMATORS`'s own
# insertion-order convention.
CANDIDATE_ESTIMATORS: dict = {
    "IsolationForest": _make_isolation_forest_candidate,
    "EllipticEnvelope": _make_elliptic_envelope_candidate,
    "OneClassSVM": _make_one_class_svm_candidate,
}


def corridor_report(
    corridor: str, fit_frame: pd.DataFrame, holdout_frame: pd.DataFrame
) -> dict:
    """
    Runs `validate_candidate` for every (candidate, contamination) pair in
    the cross product of `CANDIDATE_ESTIMATORS` x `config.ANOMALY_ML_
    CONTAMINATION_GRID`, returning one mapping carrying the corridor name,
    the assembled row count, the window start/end (ISO strings), the fit/
    holdout row counts, the injection rate, the feature column list, and a
    `measurements` list holding every pair's FULL measurement -- losers
    included. Recording every attempted pair (and the window span
    alongside them) is what makes a shortened run or a dropped arm
    visible in the evidence rather than hidden behind a single score
    (T-02-09), exactly as `forecast_training.corridor_report` does.
    """
    combined = pd.concat([fit_frame, holdout_frame], ignore_index=True)

    measurements = []
    for name, factory in CANDIDATE_ESTIMATORS.items():
        for contamination in config.ANOMALY_ML_CONTAMINATION_GRID:
            measurements.append(
                validate_candidate(
                    corridor, fit_frame, holdout_frame, name, factory, contamination,
                )
            )

    return {
        "corridor": corridor,
        "rows": int(len(combined)),
        "window_start": pd.Timestamp(combined["datetime_utc"].min()).isoformat(),
        "window_end": pd.Timestamp(combined["datetime_utc"].max()).isoformat(),
        "fit_rows": int(len(fit_frame)),
        "holdout_rows": int(len(holdout_frame)),
        "injection_rate": float(config.ANOMALY_ML_INJECTION_RATE),
        "feature_columns": list(config.ANOMALY_ML_FEATURE_COLUMNS),
        "measurements": measurements,
    }


def select_winner(report: dict) -> tuple[str, float, bool]:
    """
    This plan's stated winner-selection rule, verbatim (see the plan's
    `<objective>`): among the (candidate, contamination) pairs whose
    measured false-positive rate on the clean holdout is at or below
    `config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE`, select the pair with the
    highest pooled recall across both injection categories; break a tie
    by the lower false-positive rate, then by `CANDIDATE_ESTIMATORS`
    insertion order. When NO pair meets the ceiling, select the pair with
    the lowest measured false-positive rate and mark the returned
    selection as not meeting the ceiling (D-07 -- shipped and stated
    plainly, never hidden; per D-05/D-06 the OR-combined branch only ever
    adds caution regardless of this outcome).

    Reads only `report["measurements"]`. Raises `ValueError` naming the
    candidate when any expected `CANDIDATE_ESTIMATORS` key is entirely
    absent from the measurements, or naming the candidate and the
    offending value when its pooled recall or false-positive rate is not
    a finite number -- selection never picks a winner on a missing or
    broken measurement (D-04), mirroring `forecast_training.select_
    winner`'s own refusal semantics.

    Returns `(winner_candidate_name, selected_contamination, ceiling_met)`.
    Logs at INFO which tiebreak fired, if one did.
    """
    measurements = report.get("measurements", [])
    candidate_names = list(CANDIDATE_ESTIMATORS)

    present_candidates = {m.get("candidate") for m in measurements}
    missing = [name for name in candidate_names if name not in present_candidates]
    if missing:
        raise ValueError(
            f"select_winner: report is missing candidate(s) {missing}; "
            f"present candidates: {sorted(c for c in present_candidates if c)}"
        )

    validated = []
    for m in measurements:
        name = m.get("candidate")
        contamination = m.get("contamination")
        recall_pooled = m.get("recall_pooled")
        fp_rate = m.get("false_positive_rate")
        try:
            recall_f = float(recall_pooled)
        except (TypeError, ValueError):
            recall_f = math.nan
        try:
            fp_f = float(fp_rate)
        except (TypeError, ValueError):
            fp_f = math.nan
        if not math.isfinite(recall_f) or not math.isfinite(fp_f):
            raise ValueError(
                f"select_winner: candidate {name!r} at contamination "
                f"{contamination!r} has a non-finite measurement "
                f"(recall_pooled={recall_pooled!r}, "
                f"false_positive_rate={fp_rate!r}) -- refusing to pick a "
                f"winner on a missing measurement"
            )
        validated.append({
            "candidate": name,
            "contamination": float(contamination),
            "recall_pooled": recall_f,
            "false_positive_rate": fp_f,
            "order": candidate_names.index(name),
        })

    eligible = [
        m for m in validated
        if m["false_positive_rate"] <= config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE
    ]

    if eligible:
        best_recall = max(m["recall_pooled"] for m in eligible)
        recall_tied = [m for m in eligible if m["recall_pooled"] == best_recall]
        if len(recall_tied) > 1:
            best_fp = min(m["false_positive_rate"] for m in recall_tied)
            fp_tied = [m for m in recall_tied if m["false_positive_rate"] == best_fp]
            if len(fp_tied) > 1:
                fp_tied.sort(key=lambda m: (m["order"], m["contamination"]))
                winner = fp_tied[0]
                logger.info(
                    "select_winner: pooled-recall and false-positive-rate "
                    "tie between %s broken by CANDIDATE_ESTIMATORS order "
                    "-> %r",
                    [(m["candidate"], m["contamination"]) for m in fp_tied],
                    (winner["candidate"], winner["contamination"]),
                )
            else:
                winner = fp_tied[0]
                logger.info(
                    "select_winner: pooled-recall tie between %s broken "
                    "by false-positive rate -> %r",
                    [(m["candidate"], m["contamination"]) for m in recall_tied],
                    (winner["candidate"], winner["contamination"]),
                )
        else:
            winner = recall_tied[0]
        return winner["candidate"], winner["contamination"], True

    best_fp = min(m["false_positive_rate"] for m in validated)
    fp_tied = [m for m in validated if m["false_positive_rate"] == best_fp]
    fp_tied.sort(key=lambda m: (m["order"], m["contamination"]))
    winner = fp_tied[0]
    logger.info(
        "select_winner: no candidate met the false-positive ceiling "
        "(%.4f); selecting lowest false-positive rate -> %r",
        config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE,
        (winner["candidate"], winner["contamination"]),
    )
    return winner["candidate"], winner["contamination"], False


def _run_bakeoff(corridors, years):
    """
    D-03/D-04's full bake-off entry point, one corridor at a time:
    assemble the real observation frame, split it chronologically, build
    the corridor report (every candidate x contamination pair, losers
    included), select the winner via `select_winner`, refit that winner's
    factory at its selected contamination on the FULL frame (fit slice
    plus holdout -- A-08: the persisted artifact uses every real row
    available, while the report's own scores remain the strictly
    out-of-sample ones the holdout produced), persist it, and accumulate
    the report. A failure assembling or scoring one corridor is reported
    by name and the run continues to the next corridor (mirrors
    `forecast_training._run_bakeoff`'s own try-and-continue handling).
    Each corridor also gets one final `SUMMARY:` line.
    """
    reports = {}
    summary_lines = []

    for corridor in corridors:
        try:
            frame = corridor_observation_frame(corridor, years)
        except Exception:
            logger.exception(
                "anomaly_training --bakeoff: failed assembling corridor "
                "%s -- continuing to the next corridor", corridor,
            )
            print(f"{corridor}: FAILED to assemble observation frame -- see log")
            continue

        os.makedirs(config.ANOMALY_ML_MODEL_DIR, exist_ok=True)
        frame_path = os.path.join(
            config.ANOMALY_ML_MODEL_DIR,
            config.ANOMALY_ML_OBSERVATION_FRAME_TEMPLATE.format(corridor=corridor),
        )
        frame.to_csv(frame_path, index=False)

        try:
            fit_frame, holdout_frame = chronological_split(frame)
            report = corridor_report(corridor, fit_frame, holdout_frame)
            winner_name, winner_contamination, ceiling_met = select_winner(report)

            X_full = build_feature_matrix(frame)
            winner_estimator = fit_corridor_model(
                X_full, CANDIDATE_ESTIMATORS[winner_name](winner_contamination),
            )
            model_path = persist_corridor_model(winner_estimator, corridor)
        except Exception:
            logger.exception(
                "anomaly_training --bakeoff: failed scoring/selecting for "
                "corridor %s -- continuing to the next corridor", corridor,
            )
            print(f"{corridor}: FAILED to score/select -- see log")
            continue

        report["winner"] = winner_name
        report["selected_contamination"] = winner_contamination
        report["ceiling_met"] = ceiling_met
        report["model_path"] = model_path
        reports[corridor] = report

        start = frame["datetime_utc"].min()
        end = frame["datetime_utc"].max()
        print(f"\n{corridor}: {len(frame)} rows, {start} -> {end}")
        print(
            f"{'candidate':<20}{'contamination':>14}{'fp_rate':>10}"
            f"{'baseline_fp':>13}{'recall_pooled':>15}"
        )
        for m in report["measurements"]:
            print(
                f"{m['candidate']:<20}{m['contamination']:>14.4f}"
                f"{m['false_positive_rate']:>10.4f}"
                f"{m['baseline_false_positive_rate']:>13.4f}"
                f"{m['recall_pooled']:>15.4f}"
            )
        print(
            f"winner: {winner_name} contamination={winner_contamination} "
            f"ceiling_met={ceiling_met} -> persisted to {model_path}"
        )
        summary_lines.append(
            f"SUMMARY: {corridor} rows={len(frame)} window={start}->{end} "
            f"winner={winner_name} contamination={winner_contamination} "
            f"ceiling_met={ceiling_met} path={model_path}"
        )

    os.makedirs(config.ANOMALY_ML_MODEL_DIR, exist_ok=True)
    report_path = os.path.join(
        config.ANOMALY_ML_MODEL_DIR, config.ANOMALY_ML_VALIDATION_REPORT_NAME
    )
    with open(report_path, "w") as fh:
        json.dump(reports, fh, indent=2)
    print(f"\nbake-off report written to {report_path}")

    if summary_lines:
        print()
        for line in summary_lines:
            print(line)


# ──────────────────────────────────────────────────────────────────────────────
# D-02 training-time-only load characterization (v1.3 Phase 2 Plan 02-03,
# ANOM-01)
# ──────────────────────────────────────────────────────────────────────────────


def characterize_load(corridor: str, years: int = None) -> dict:
    """
    D-02's training-time-only load characterization for one corridor:
    pulls `years` complete calendar years (default
    `config.ANOMALY_ML_LOAD_YEARS`) of the corridor's OWN ERCOT zone
    load -- resolved from `config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_
    CORRIDOR`, never a substring shared with the other corridor -- joins
    it to the corridor's pooled weather observation frame on
    `datetime_utc`, and reports the Pearson correlation between the load
    series and each of `config.ANOMALY_ML_FEATURE_COLUMNS`.

    The window ends with the most recent COMPLETE calendar year (the
    current, still-in-progress year is never included), matching
    `forecast_training.fetch_city_weather`'s own rule, so the load window
    and the weather window describe the same period.

    The observation frame is loaded from its CSV path
    (`config.ANOMALY_ML_OBSERVATION_FRAME_TEMPLATE`) when present,
    otherwise assembled fresh via `corridor_observation_frame`. Because
    that frame is POOLED over both endpoint cities, it is collapsed to
    one row per timestamp by AVERAGING the three feature columns across
    cities before the join -- this averaging exists ONLY for this
    correlation summary and never touches the fitted feature matrix
    (`build_feature_matrix`), which uses each city's own unaveraged
    reading per D-01.

    The reported window (`window_start`/`window_end`/`load_rows`) always
    comes from the RETURNED load frame's own extremes, never from the
    requested range -- a client that silently serves less than was asked
    for is visible in the evidence this way (T-02-12).

    Only the load pull itself is wrapped in a failure path: a raised
    exception there resolves to a mapping recording the corridor, the
    zone substrings that were about to be used, the exception text, and
    `available: False` -- never a bare `except` around the whole
    function, and never a silently empty result. D-02 scopes ERCOT
    network access as training-time-only and non-blocking
    (02-RESEARCH.md Environment Availability) -- ANOM-01's interface
    deliverable does not depend on this pull succeeding.
    """
    if years is None:
        years = config.ANOMALY_ML_LOAD_YEARS

    last_complete_year = pd.Timestamp.now(tz="UTC").year - 1
    start = f"{last_complete_year - years + 1}-01-01"
    end = f"{last_complete_year}-12-31"

    zone_substrings = config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CORRIDOR[corridor]

    try:
        load_frame = ercot_data_retriever.pull_ercot_data(
            start, end, zone_substrings=zone_substrings, save=False,
        )
    except Exception as exc:
        return {
            "corridor": corridor,
            "zone_substrings": list(zone_substrings),
            "available": False,
            "error": str(exc),
        }

    load_col = load_frame.attrs.get("load_column")
    zone_columns_matched = list(load_frame.attrs.get("zone_columns_matched", []))

    load_frame = load_frame.copy()
    load_frame["datetime_utc"] = pd.to_datetime(load_frame["datetime_utc"], utc=True)

    window_start = pd.Timestamp(load_frame["datetime_utc"].min()).isoformat()
    window_end = pd.Timestamp(load_frame["datetime_utc"].max()).isoformat()
    load_rows = int(len(load_frame))

    obs_path = os.path.join(
        config.ANOMALY_ML_MODEL_DIR,
        config.ANOMALY_ML_OBSERVATION_FRAME_TEMPLATE.format(corridor=corridor),
    )
    if os.path.exists(obs_path):
        obs_frame = pd.read_csv(obs_path)
    else:
        obs_frame = corridor_observation_frame(corridor, years)

    feature_cols = list(config.ANOMALY_ML_FEATURE_COLUMNS)
    # Collapse the pooled (two-cities-per-timestamp) observation frame to
    # one row per timestamp via averaging -- presentation-only for this
    # correlation summary (A-10), never used to fit the model.
    collapsed = obs_frame.groupby("datetime_utc", as_index=False)[feature_cols].mean()
    collapsed["datetime_utc"] = pd.to_datetime(collapsed["datetime_utc"], utc=True)

    joined = pd.merge(load_frame, collapsed, on="datetime_utc", how="inner")

    correlations = {
        feature: float(joined[load_col].corr(joined[feature]))
        for feature in feature_cols
    }

    return {
        "corridor": corridor,
        "zone_substrings": list(zone_substrings),
        "zone_columns": zone_columns_matched,
        "window_start": window_start,
        "window_end": window_end,
        "load_rows": load_rows,
        "joined_rows": int(len(joined)),
        "correlations": correlations,
        "available": True,
    }


def _run_characterize_load(corridors):
    """
    D-02's training-time-only load characterization entry point
    (`--characterize-load`): for each selected corridor, calls
    `characterize_load` (always with `years=None`, so the load window
    depth resolves from `config.ANOMALY_ML_LOAD_YEARS` rather than the
    shared `--years` flag, which governs the weather-training window
    depth instead), prints one summary line naming the matched zones,
    the true retrieved window, the joined row count, and the
    per-variable correlations (or the unavailability message), and
    writes the accumulated per-corridor mapping to
    `config.ANOMALY_ML_LOAD_REPORT_NAME` under `config.ANOMALY_ML_MODEL_
    DIR`. Exits 0 regardless of whether any corridor's load pull
    succeeded -- D-02 scopes ERCOT network access as training-time-only
    and non-blocking (02-RESEARCH.md Environment Availability); ANOM-01's
    interface deliverable does not depend on it.
    """
    reports = {}
    for corridor in corridors:
        result = characterize_load(corridor, years=None)
        reports[corridor] = result

        if result.get("available", False):
            print(
                f"{corridor}: zones={result['zone_columns']} "
                f"window={result['window_start']}->{result['window_end']} "
                f"load_rows={result['load_rows']} "
                f"joined_rows={result['joined_rows']} "
                f"correlations={result['correlations']}"
            )
        else:
            print(f"{corridor}: UNAVAILABLE -- {result.get('error')}")

    os.makedirs(config.ANOMALY_ML_MODEL_DIR, exist_ok=True)
    report_path = os.path.join(
        config.ANOMALY_ML_MODEL_DIR, config.ANOMALY_ML_LOAD_REPORT_NAME
    )
    with open(report_path, "w") as fh:
        json.dump(reports, fh, indent=2)
    print(f"\nload characterization report written to {report_path}")


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
    parser.add_argument(
        "--validate",
        action="store_true",
        help="For each selected corridor, chronologically split the "
             "observation frame and measure the default IsolationForest "
             "candidate's false-positive rate and per-category recall "
             "(against the rolling baseline) across "
             "config.ANOMALY_ML_CONTAMINATION_GRID, printing a table and "
             "writing config.ANOMALY_ML_VALIDATION_REPORT_NAME.",
    )
    parser.add_argument(
        "--bakeoff",
        action="store_true",
        help="Run the D-03 three-candidate, contamination-swept bake-off "
             "(IsolationForest/EllipticEnvelope/OneClassSVM) against the "
             "rolling baseline, per corridor, select each corridor's own "
             "measured winner per this plan's stated deterministic rule, "
             "persist it, and write the accumulated comparison -- losers "
             "included -- to config.ANOMALY_ML_VALIDATION_REPORT_NAME.",
    )
    parser.add_argument(
        "--characterize-load",
        action="store_true",
        help="For each selected corridor, run D-02's training-time-only "
             "ERCOT load characterization (zone-aware per corridor -- "
             "config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CORRIDOR), joined "
             "to the corridor's pooled weather observations, reporting the "
             "true retrieved window and the Pearson correlation between "
             "load and each fitted variable to "
             "config.ANOMALY_ML_LOAD_REPORT_NAME. Exits 0 whether or not "
             "the ERCOT pull succeeds -- this characterization never "
             "reaches the live check() path (D-02).",
    )
    args = parser.parse_args(argv)

    corridors = [args.corridor] if args.corridor else sorted(config.CORRIDOR_ENDPOINTS)

    if args.characterize_load:
        _run_characterize_load(corridors)
        return

    if args.bakeoff:
        _run_bakeoff(corridors, args.years)
        return

    if args.validate:
        _run_validate(corridors, args.years)
        return

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
