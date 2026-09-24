"""
Offline Forecasting Model Training (v1.3 Phase 1 Plan 01-01, FCST-01/FCST-02)
==============================================================================
Standalone entry point -- NOT imported by the runtime pipeline, mirroring
`ercot_data_retriever.py`'s own `__main__`-driven, offline-data-pull
convention. It imports `ampacity_forecast` for `build_ml_features` so
exactly one feature-engineering implementation exists (dependency points
training -> runtime, never the reverse).

Assembles a real, non-synthetic per-corridor `dlr_amps` training series
from Open-Meteo Archive backfill run through `thermal_model.ieee738_
ampacity` for the corridor's two endpoint cities, reduces it to one
corridor-level series via the codebase's established weakest-link `min()`
convention (mirroring `corridor_discretization.rate_corridor`), fits a
`scikit-learn` estimator on it, and persists the result atomically for
`ampacity_forecast.forecast_ampacity(..., method="ml")` to load.

Run directly:
    .venv/bin/python3 backend/forecast_training.py --corridor AUSTIN_CORPUS_CHRISTI --years 1
"""

import argparse
import json
import logging
import math
import os
import tempfile

import numpy as np
import pandas as pd

import ampacity_forecast
import config
import corridor_discretization
import historical_archive
import open_meteo_provider
import thermal_model
import units_def

logger = logging.getLogger(__name__)


def _make_regression_candidate():
    """Regression arm of D-01's bake-off. Fixed `random_state` so a
    bake-off run is reproducible. Lazy `sklearn` import, matching this
    module's other estimator-touching functions (`fit_corridor_model`) --
    importing `forecast_training` stays free of a hard `sklearn` import."""
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(random_state=20260924)


def _make_neural_network_candidate():
    """
    Neural-network arm of D-01's bake-off. `MLPRegressor` is scale-sensitive
    in a way the tree candidate is not -- the raw features span amps in the
    thousands, degrees Celsius, and unit-interval sine/cosine terms -- so it
    is wrapped in `make_pipeline(StandardScaler(), MLPRegressor(...))`. This
    measures the architecture rather than a missing scaling step; without it
    the neural-network arm would lose for a reason that has nothing to do
    with D-01's question (RESEARCH.md Pattern, `01-02-PLAN.md` Task 1).
    """
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(
        StandardScaler(),
        MLPRegressor(
            hidden_layer_sizes=(32, 16),
            max_iter=2000,
            random_state=20260924,
            early_stopping=False,
        ),
    )


# D-01's evidence-based bake-off: exactly two entries, one per arm of
# "regression or neural network" -- a zero-argument factory per entry (not
# a shared instance), since each `TimeSeriesSplit` fold must fit a FRESH,
# never-before-fit estimator. Order is significant: `select_winner`'s
# deterministic tiebreak falls back to this order as its last resort.
CANDIDATE_ESTIMATORS: dict = {
    "HistGradientBoostingRegressor": _make_regression_candidate,
    "MLPRegressor": _make_neural_network_candidate,
}


def fetch_city_weather(city: str, years: int) -> pd.DataFrame:
    """
    Fetch `years` complete calendar years of hourly Open-Meteo weather for
    `city` (a key in `config.CITY_COORDINATES`), ending with the most
    recent complete calendar year (the current, still-in-progress year is
    never included). One `open_meteo_provider.fetch_open_meteo` call per
    calendar year -- per-year chunking lives here, in the caller, since
    `fetch_open_meteo`'s documented contract is exactly one HTTP request
    per call (RESEARCH.md Assumption A5).
    """
    lat, lon = config.CITY_COORDINATES[city]
    last_complete_year = pd.Timestamp.now(tz="UTC").year - 1

    frames = []
    for year in range(last_complete_year - years + 1, last_complete_year + 1):
        start = f"{year}-01-01T00:00:00Z"
        end = f"{year}-12-31T23:59:59Z"
        frames.append(open_meteo_provider.fetch_open_meteo(lat, lon, start, end))

    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values("datetime_utc").reset_index(drop=True)


def corridor_training_frame(corridor: str, years: int) -> pd.DataFrame:
    """
    Assemble a real, `historical_archive.ARCHIVE_COLUMNS`-shaped training
    frame for `corridor` from `years` complete calendar years of
    Open-Meteo backfill for its two endpoint cities.

    Each endpoint city's ampacity is computed independently via
    `thermal_model.perpendicular_wind` + `ieee738_ampacity` (using the
    corridor's own bearing and `ConductorConfig` from `corridor_
    discretization.corridor_geometry` -- never recomputed here). The
    corridor-level `dlr_amps` at each timestamp is the elementwise
    `min()` of the two cities' ampacities (the codebase's established
    weakest-link reduction, mirroring `corridor_discretization.rate_
    corridor`); that row's weather is the *winning* (lower-ampacity)
    city's own observation, never the other city's and never an average
    -- "the archived weather is always the weather that produced the
    archived rating."

    Every assembled row is validated through `units_def.validate_
    pipeline_row(historical_archive._validation_row(row), strict=False)`
    before it reaches the estimator (T-01-01); failures are dropped with
    one aggregated warning line naming the count and the first offending
    message, mirroring `historical_archive.read_history`'s own
    validate-before-training behavior.
    """
    geometry = corridor_discretization.corridor_geometry(corridor)
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]

    weather_a = fetch_city_weather(city_a, years)
    weather_b = fetch_city_weather(city_b, years)

    merged = weather_a.merge(
        weather_b, on="datetime_utc", how="inner", suffixes=("_a", "_b")
    )

    perp_a = thermal_model.perpendicular_wind(
        merged["wind_speed_a"].to_numpy(dtype=float),
        merged["wind_direction_a"].to_numpy(dtype=float),
        geometry.bearing_deg,
    )
    perp_b = thermal_model.perpendicular_wind(
        merged["wind_speed_b"].to_numpy(dtype=float),
        merged["wind_direction_b"].to_numpy(dtype=float),
        geometry.bearing_deg,
    )

    # RESEARCH.md Pitfall 2: ieee738_ampacity returns np.ndarray even for
    # scalar input -- explicit float64 cast at this boundary.
    amps_a = np.asarray(
        thermal_model.ieee738_ampacity(
            merged["air_temp_a"].to_numpy(dtype=float), perp_a,
            merged["solar_radiation_a"].to_numpy(dtype=float), geometry.conductor,
        ),
        dtype=float,
    )
    amps_b = np.asarray(
        thermal_model.ieee738_ampacity(
            merged["air_temp_b"].to_numpy(dtype=float), perp_b,
            merged["solar_radiation_b"].to_numpy(dtype=float), geometry.conductor,
        ),
        dtype=float,
    )

    dlr_amps = np.minimum(amps_a, amps_b)
    # Tie-break toward the lower index (city A), matching corridor_
    # discretization.rate_corridor's own `ratings.index(min_rating)`
    # first-match convention.
    bottleneck_index = np.where(amps_a <= amps_b, 0, 1)

    winning_a = bottleneck_index == 0
    air_temp = np.where(winning_a, merged["air_temp_a"].to_numpy(dtype=float),
                         merged["air_temp_b"].to_numpy(dtype=float))
    wind_speed = np.where(winning_a, merged["wind_speed_a"].to_numpy(dtype=float),
                           merged["wind_speed_b"].to_numpy(dtype=float))
    solar_radiation = np.where(
        winning_a, merged["solar_radiation_a"].to_numpy(dtype=float),
        merged["solar_radiation_b"].to_numpy(dtype=float),
    )

    frame = pd.DataFrame({
        "datetime_utc": merged["datetime_utc"],
        "corridor": corridor,
        "air_temp": air_temp,
        "wind_speed": wind_speed,
        "solar_radiation": solar_radiation,
        "dlr_amps": dlr_amps,
        "static_rating": float(geometry.static_rating),
        "status": "ok",
        "fallback": False,
        "bottleneck_index": bottleneck_index.astype(int),
        "schema_version": historical_archive.ARCHIVE_SCHEMA_VERSION,
    })[historical_archive.ARCHIVE_COLUMNS]

    keep_mask = []
    first_bad_message = None
    for row in frame.to_dict(orient="records"):
        errors = units_def.validate_pipeline_row(
            historical_archive._validation_row(row), strict=False
        )
        keep_mask.append(len(errors) == 0)
        if errors and first_bad_message is None:
            first_bad_message = errors[0]

    keep_mask = pd.Series(keep_mask, index=frame.index)
    dropped = int((~keep_mask).sum())
    if dropped:
        logger.warning(
            "corridor_training_frame: dropped %d invalid row(s) for %s: %s",
            dropped, corridor, first_bad_message,
        )

    return frame[keep_mask].reset_index(drop=True)


def build_training_matrix(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Build the (X, y) training matrix from a `corridor_training_frame`-
    shaped frame: index by `datetime_utc`, build `ampacity_forecast.
    build_ml_features` for X, and set the target `y` to `dlr_amps`
    shifted FORWARD by exactly `config.FORECAST_HORIZON_MINUTES` worth of
    rows (1 row at this project's hourly cadence).

    `X.index` carries each row's FEATURE timestamp; `y.index` carries
    that same row's TARGET timestamp (`feature_timestamp +
    FORECAST_HORIZON_MINUTES`), so the feature/target time relationship
    is inspectable by a test directly from the returned index values
    rather than only asserted in prose (RESEARCH.md Pitfall 4). Rows
    where any feature or the target is null are dropped.
    """
    indexed = frame.copy()
    indexed.index = pd.to_datetime(indexed["datetime_utc"])
    indexed = indexed.sort_index()

    X = ampacity_forecast.build_ml_features(indexed)

    horizon = pd.Timedelta(minutes=config.FORECAST_HORIZON_MINUTES)
    # This project's only supported cadence is hourly, so the horizon
    # (60 min) is exactly 1 row -- asserted, not silently assumed, so a
    # future sub-hourly cadence change fails loudly here instead of
    # quietly leaking or misaligning the target.
    cadence = pd.Timedelta(hours=1)
    horizon_rows = horizon / cadence
    if horizon_rows != int(horizon_rows):
        raise ValueError(
            f"build_training_matrix: FORECAST_HORIZON_MINUTES "
            f"({config.FORECAST_HORIZON_MINUTES}) is not a whole multiple "
            f"of the assumed hourly cadence"
        )
    horizon_rows = int(horizon_rows)

    target_values = indexed["dlr_amps"].shift(-horizon_rows).to_numpy()
    y = pd.Series(target_values, index=indexed.index + horizon, name="dlr_amps_target")

    valid = X.notna().all(axis=1).to_numpy() & ~pd.isna(target_values)

    X_clean = X.iloc[valid]
    y_clean = y.iloc[valid]
    return X_clean, y_clean


def bakeoff_corridor(X: pd.DataFrame, y: pd.Series) -> dict:
    """
    D-01's two-candidate comparison: for each entry in `CANDIDATE_
    ESTIMATORS`, fit a FRESH (never-before-fit) estimator on each
    `sklearn.model_selection.TimeSeriesSplit(n_splits=config.FORECAST_ML_
    BAKEOFF_SPLITS)` fold's train rows, predict the fold's test rows, and
    pool the absolute/squared errors across all folds. `TimeSeriesSplit`
    is the only fold source -- no hand-rolled `.iloc[:i]`/`.iloc[i:]`
    slicing loop (RESEARCH.md "Don't Hand-Roll") -- so every fold's train
    index maxima are strictly below its test index minima.

    Returns a mapping keyed by `CANDIDATE_ESTIMATORS` name, each with a
    finite `mae`, a finite `rmse`, and the total number of held-out rows
    scored across all folds.
    """
    from sklearn.model_selection import TimeSeriesSplit

    X_arr = X.to_numpy(dtype=float)
    y_arr = y.to_numpy(dtype=float)
    splitter = TimeSeriesSplit(n_splits=config.FORECAST_ML_BAKEOFF_SPLITS)

    report = {}
    for name, factory in CANDIDATE_ESTIMATORS.items():
        abs_errors = []
        sq_errors = []
        for train_idx, test_idx in splitter.split(X_arr):
            estimator = factory()
            estimator.fit(X_arr[train_idx], y_arr[train_idx])
            predictions = estimator.predict(X_arr[test_idx])
            residual = y_arr[test_idx] - predictions
            abs_errors.append(np.abs(residual))
            sq_errors.append(residual ** 2)

        abs_errors = np.concatenate(abs_errors)
        sq_errors = np.concatenate(sq_errors)
        report[name] = {
            "mae": float(np.mean(abs_errors)),
            "rmse": float(np.sqrt(np.mean(sq_errors))),
            "rows": int(abs_errors.size),
        }

    return report


def baseline_scores(frame: pd.DataFrame) -> dict:
    """
    Score `"naive"` and `"ewm"` on the SAME assembled corridor `frame` by
    calling `ampacity_forecast.backtest_residuals` -- the apples-to-apples
    requirement in ROADMAP SC3/SC4: the baselines come from the module's
    own walk-forward function, never a second error computation written
    here. The residual count is recorded as that candidate's held-out row
    count.
    """
    indexed = frame.copy()
    indexed.index = pd.to_datetime(indexed["datetime_utc"])
    indexed = indexed.sort_index()
    series = indexed["dlr_amps"]

    scores = {}
    for method in ("naive", "ewm"):
        residuals = ampacity_forecast.backtest_residuals(
            series, method,
            min_train_rows=config.FORECAST_MIN_HISTORY_ROWS,
            halflife_min=config.FORECAST_EWM_HALFLIFE_MIN,
        )
        scores[method] = {
            "mae": float(np.mean(np.abs(residuals))),
            "rmse": float(np.sqrt(np.mean(residuals ** 2))),
            "rows": int(residuals.size),
        }

    return scores


def corridor_report(corridor: str, frame: pd.DataFrame, X: pd.DataFrame,
                     y: pd.Series) -> dict:
    """
    Merge `bakeoff_corridor` and `baseline_scores` into one mapping for
    `corridor`: a `candidates` sub-mapping holding all four entries (the
    two `CANDIDATE_ESTIMATORS` plus `"naive"` and `"ewm"`), plus the
    assembled row count and the window (`window_start`/`window_end`, ISO
    strings) the score was measured on -- so a shortened run is visible in
    the evidence rather than hidden behind a score (this plan's first
    prohibition).
    """
    candidates = bakeoff_corridor(X, y)
    candidates.update(baseline_scores(frame))

    return {
        "corridor": corridor,
        "rows": int(len(frame)),
        "window_start": pd.Timestamp(frame["datetime_utc"].min()).isoformat(),
        "window_end": pd.Timestamp(frame["datetime_utc"].max()).isoformat(),
        "feature_columns": list(ampacity_forecast.ML_FEATURE_COLUMNS),
        "horizon_min": float(config.FORECAST_HORIZON_MINUTES),
        "candidates": candidates,
    }


def select_winner(report: dict) -> str:
    """
    Over the two `CANDIDATE_ESTIMATORS` names only (never `"naive"`/
    `"ewm"`), return the one with the strictly lowest `mae` in `report`.

    Raises `ValueError` naming the problem when a candidate entry is
    missing from the report or its `mae` is not a finite number -- a
    winner chosen despite a missing measurement is exactly the default
    lean D-01 forbids.

    On an exact MAE tie, breaks deterministically by `rmse`, then by
    `CANDIDATE_ESTIMATORS` order; which tiebreak fired (if any) is logged
    at INFO for the record.
    """
    candidates = report.get("candidates", {})
    ml_names = list(CANDIDATE_ESTIMATORS)

    scored = []
    for name in ml_names:
        entry = candidates.get(name)
        if entry is None:
            raise ValueError(
                f"select_winner: report is missing candidate {name!r}; "
                f"present candidates: {sorted(candidates)}"
            )
        mae = entry.get("mae")
        try:
            mae = float(mae)
        except (TypeError, ValueError):
            mae = math.nan
        if not math.isfinite(mae):
            raise ValueError(
                f"select_winner: candidate {name!r} has non-finite mae "
                f"{entry.get('mae')!r} -- refusing to pick a winner on a "
                f"missing measurement"
            )
        rmse = float(entry.get("rmse", math.inf))
        scored.append((name, mae, rmse))

    best_mae = min(s[1] for s in scored)
    mae_tied = [s for s in scored if s[1] == best_mae]
    if len(mae_tied) == 1:
        return mae_tied[0][0]

    best_rmse = min(s[2] for s in mae_tied)
    rmse_tied = [s for s in mae_tied if s[2] == best_rmse]
    if len(rmse_tied) == 1:
        logger.info(
            "select_winner: MAE tie between %s broken by rmse -> %r",
            [s[0] for s in mae_tied], rmse_tied[0][0],
        )
        return rmse_tied[0][0]

    winner = rmse_tied[0][0]  # CANDIDATE_ESTIMATORS order, preserved above
    logger.info(
        "select_winner: MAE and rmse tie between %s broken by "
        "CANDIDATE_ESTIMATORS order -> %r",
        [s[0] for s in rmse_tied], winner,
    )
    return winner


def fit_corridor_model(X: pd.DataFrame, y: pd.Series, estimator):
    """
    Fit `estimator` (already constructed, unfitted) on (X, y) and return
    it fitted. The same function serves the tracer's single fit (Plan
    01-01) and the bake-off winner's full-window refit (this plan) --
    never a second, parallel fit path.
    """
    estimator.fit(X.to_numpy(dtype=float), y.to_numpy(dtype=float))
    return estimator


def persist_corridor_model(model, corridor: str) -> str:
    """
    Persist `model` for `corridor` atomically: `joblib.dump` to a temp
    file in `config.FORECAST_ML_MODEL_DIR`, then `os.replace` onto
    `ampacity_forecast._model_path_for(corridor)`. The temp-then-replace
    is the concurrency/interruption guarantee -- a run killed mid-write,
    or two runs racing on one corridor, can never leave a torn `.joblib`
    for `ampacity_forecast._load_corridor_model` to deserialize (last
    writer wins, never a partially-written file). Returns the final path.
    """
    import joblib

    os.makedirs(config.FORECAST_ML_MODEL_DIR, exist_ok=True)
    final_path = ampacity_forecast._model_path_for(corridor)

    fd, tmp_path = tempfile.mkstemp(
        dir=config.FORECAST_ML_MODEL_DIR, suffix=".joblib.tmp"
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
            "Assemble real Open-Meteo-derived per-corridor training data, "
            "fit, and atomically persist an 'ml' forecasting model."
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
        default=config.FORECAST_ML_TRAINING_YEARS,
        help="Complete calendar years of Open-Meteo backfill per city "
             "(default: config.FORECAST_ML_TRAINING_YEARS).",
    )
    parser.add_argument(
        "--bakeoff",
        action="store_true",
        help="Run D-01's two-candidate bake-off (regression vs. neural "
             "network) against the naive/ewm baselines, per corridor, "
             "select each corridor's own measured winner by MAE, persist "
             "it, and write the accumulated comparison to "
             "config.FORECAST_ML_BAKEOFF_REPORT_NAME.",
    )
    args = parser.parse_args(argv)

    corridors = [args.corridor] if args.corridor else sorted(config.CORRIDOR_ENDPOINTS)

    if args.bakeoff:
        _run_bakeoff(corridors, args.years)
        return

    for corridor in corridors:
        try:
            frame = corridor_training_frame(corridor, args.years)
        except Exception:
            logger.exception(
                "forecast_training: failed assembling corridor %s -- "
                "continuing to the next corridor", corridor,
            )
            print(f"{corridor}: FAILED to assemble training frame -- see log")
            continue

        os.makedirs(config.FORECAST_ML_MODEL_DIR, exist_ok=True)
        frame_path = os.path.join(
            config.FORECAST_ML_MODEL_DIR,
            config.FORECAST_ML_TRAINING_FRAME_TEMPLATE.format(corridor=corridor),
        )
        frame.to_csv(frame_path, index=False)

        X, y = build_training_matrix(frame)
        model = fit_corridor_model(X, y, _make_regression_candidate())
        model_path = persist_corridor_model(model, corridor)

        start = frame["datetime_utc"].min()
        end = frame["datetime_utc"].max()
        print(
            f"{corridor}: {len(frame)} rows, {start} -> {end}, "
            f"model persisted to {model_path}"
        )


def _run_bakeoff(corridors, years):
    """
    D-01's bake-off entry point, one corridor at a time: assemble, build
    the comparison report, select the winner by measured MAE, refit it
    ONCE on the full matrix, persist it, and accumulate the report. A
    failure assembling one corridor is reported by name and the run
    continues to the next corridor rather than aborting silently
    (`01-02-PLAN.md` Task 2). Each corridor also gets one final `SUMMARY:`
    line (corridor, rows, window span, winner, persisted path) so a single
    invocation's stdout is a complete, greppable record of what was
    trained.
    """
    reports = {}
    summary_lines = []

    for corridor in corridors:
        try:
            frame = corridor_training_frame(corridor, years)
        except Exception:
            logger.exception(
                "forecast_training --bakeoff: failed assembling corridor "
                "%s -- continuing to the next corridor", corridor,
            )
            print(f"{corridor}: FAILED to assemble training frame -- see log")
            continue

        os.makedirs(config.FORECAST_ML_MODEL_DIR, exist_ok=True)
        frame_path = os.path.join(
            config.FORECAST_ML_MODEL_DIR,
            config.FORECAST_ML_TRAINING_FRAME_TEMPLATE.format(corridor=corridor),
        )
        frame.to_csv(frame_path, index=False)

        X, y = build_training_matrix(frame)
        report = corridor_report(corridor, frame, X, y)
        winner_name = select_winner(report)
        winner_estimator = fit_corridor_model(
            X, y, CANDIDATE_ESTIMATORS[winner_name]()
        )
        model_path = persist_corridor_model(winner_estimator, corridor)

        reports[corridor] = report

        start = frame["datetime_utc"].min()
        end = frame["datetime_utc"].max()
        print(f"\n{corridor}: {len(frame)} rows, {start} -> {end}")
        print(f"{'candidate':<32}{'mae':>12}{'rmse':>12}{'rows':>10}")
        for name, scores in report["candidates"].items():
            print(
                f"{name:<32}{scores['mae']:>12.3f}{scores['rmse']:>12.3f}"
                f"{scores['rows']:>10d}"
            )
        print(f"winner: {winner_name} -> persisted to {model_path}")
        summary_lines.append(
            f"SUMMARY: {corridor} rows={len(frame)} window={start}->{end} "
            f"winner={winner_name} path={model_path}"
        )

    os.makedirs(config.FORECAST_ML_MODEL_DIR, exist_ok=True)
    report_path = os.path.join(
        config.FORECAST_ML_MODEL_DIR, config.FORECAST_ML_BAKEOFF_REPORT_NAME
    )
    with open(report_path, "w") as fh:
        json.dump(reports, fh, indent=2)
    print(f"\nbake-off report written to {report_path}")

    if summary_lines:
        print()
        for line in summary_lines:
            print(line)


if __name__ == "__main__":
    main()
