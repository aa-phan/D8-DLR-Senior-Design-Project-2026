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
import logging
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


def fit_corridor_model(X: pd.DataFrame, y: pd.Series):
    """
    Fit a `sklearn.ensemble.HistGradientBoostingRegressor` with a fixed
    `random_state` on (X, y). This plan fits one candidate so the "ml"
    path is proven end-to-end; Plan 01-02 turns this into D-01's
    evidence-based two-candidate bake-off.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    model = HistGradientBoostingRegressor(random_state=20260924)
    model.fit(X.to_numpy(dtype=float), y.to_numpy(dtype=float))
    return model


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
    args = parser.parse_args(argv)

    corridors = [args.corridor] if args.corridor else sorted(config.CORRIDOR_ENDPOINTS)

    for corridor in corridors:
        frame = corridor_training_frame(corridor, args.years)

        os.makedirs(config.FORECAST_ML_MODEL_DIR, exist_ok=True)
        frame_path = os.path.join(
            config.FORECAST_ML_MODEL_DIR,
            config.FORECAST_ML_TRAINING_FRAME_TEMPLATE.format(corridor=corridor),
        )
        frame.to_csv(frame_path, index=False)

        X, y = build_training_matrix(frame)
        model = fit_corridor_model(X, y)
        model_path = persist_corridor_model(model, corridor)

        start = frame["datetime_utc"].min()
        end = frame["datetime_utc"].max()
        print(
            f"{corridor}: {len(frame)} rows, {start} -> {end}, "
            f"model persisted to {model_path}"
        )


if __name__ == "__main__":
    main()
