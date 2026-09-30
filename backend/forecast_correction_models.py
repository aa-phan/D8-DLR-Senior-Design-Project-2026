"""
ML Correction Families for the Ampacity Forecast Experiment (Phase 3 Plan 05, D-02)
====================================================================================
Standalone offline unit, the same tier as `forecast_training.py`: it imports
`config`, `thermal_model`, and `wind_vector`; nothing in the runtime pipeline
imports this module. Importing it performs no network call, no file I/O, and
no environment-variable read.

Two correction families live here, and they are genuinely different
approaches -- not two spellings of one idea:

- **Arm 3, wind correction** (`fit_wind_correction`/`predict_wind_correction`):
  corrects the forecast's WIND before the physics runs. Learned and
  predicted entirely in u/v vector space via `wind_vector.to_uv`/`from_uv`
  -- never on a direction in degrees, which wraps discontinuously at the
  0/360 boundary and would make both a linear model and a tree learn
  nonsense at that seam. See `wind_vector.py`'s own module docstring for
  the full rationale; this module relies on it rather than re-deriving it.
- **Arm 4, cooling correction** (`fit_cooling_correction`/`predict_cooling_correction`):
  corrects the physics' convective heat-loss TERM after the wind has
  already been projected, substituting the corrected term back through
  `thermal_model.ieee738_ampacity`'s `q_conv_override` seam. Correcting
  the physics term rather than the final ampacity is what makes this arm a
  distinct approach from arm 3 rather than a reparameterization of it.

Both families follow the same shape: a module-level estimator registry
(`WIND_CORRECTION_ESTIMATORS`/`COOLING_CORRECTION_ESTIMATORS`) of
zero-argument factories (never a shared instance -- every fit starts from a
fresh, never-before-fit estimator, mirroring
`forecast_training.CANDIDATE_ESTIMATORS`'s own convention), a `fit_*`/
`predict_*` pair whose fitted-model object carries its own ordered
feature-name list (so prediction can never silently reorder columns), and a
`select_*` function that fits every open combination on TRAIN rows and
scores each on VALIDATION rows by ampacity mean absolute error -- never on
wind or on the convective term directly, because ampacity is the quantity
this phase is actually comparing.
"""

import numpy as np
import pandas as pd

import config
import thermal_model
import wind_vector

# ──────────────────────────────────────────────────────────────────────────────
# Arm 3: wind correction, learned entirely in u/v space
# ──────────────────────────────────────────────────────────────────────────────

_VALID_WIND_POOLING = ("pooled", "per_city")


def _make_wind_linear_regression():
    """
    `LinearRegression` has no stochastic component and therefore no
    `random_state` argument -- the config-backed random state is reserved
    for the estimator that actually needs one below, mirroring
    `forecast_training.CANDIDATE_ESTIMATORS`'s own convention of seeding
    only its stochastic entries. Lazy `sklearn` import, matching this
    module's no-side-effects-on-import contract.
    """
    from sklearn.linear_model import LinearRegression

    return LinearRegression()


def _make_wind_gradient_boosting():
    """Gradient-boosted-tree arm of D-02 approach 3's pairing. Lazy
    `sklearn` import; fixed random state from the constant Plan 03-03
    landed, so a bake-off run is reproducible."""
    from sklearn.ensemble import GradientBoostingRegressor

    return GradientBoostingRegressor(
        random_state=config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE
    )


# D-02 approach 3's two-estimator pairing ("linear regression, then
# gradient boosting"): a zero-argument factory per entry, never a shared
# instance -- every fit starts from a fresh, never-before-fit estimator.
# Order is significant only as a deterministic last-resort tie-break,
# mirroring forecast_training.CANDIDATE_ESTIMATORS's own convention.
WIND_CORRECTION_ESTIMATORS: dict = {
    "LinearRegression": _make_wind_linear_regression,
    "GradientBoostingRegressor": _make_wind_gradient_boosting,
}


def _hour_encoding(frame: pd.DataFrame) -> tuple:
    """Cyclical hour-of-day encoding from `frame["datetime_utc"]`, matching
    `ampacity_forecast.build_ml_features`'s own `hour_sin`/`hour_cos`
    convention."""
    hours = pd.to_datetime(frame["datetime_utc"]).dt.hour.to_numpy(dtype=float)
    return np.sin(2 * np.pi * hours / 24.0), np.cos(2 * np.pi * hours / 24.0)


def _wind_feature_frame(
    frame: pd.DataFrame, *, pooling: str, endpoint_cities: tuple | None = None,
) -> pd.DataFrame:
    """
    Build the wind-correction feature frame: the forecast's own u/v, the
    forecast air temperature and solar radiation, the anchor observation's
    u/v (the last real observation a forecaster would have had), and a
    cyclical hour-of-day encoding. Never includes the truth of any
    variable and never a value timestamped after the issue time.

    `pooling="pooled"` additionally appends a binary `endpoint_indicator`
    feature (1.0 for `endpoint_cities[1]`, 0.0 otherwise) so one model can
    learn a per-city offset without a separate fit; `endpoint_cities` must
    be the SAME two-city tuple at fit and predict time, which is why it
    travels inside the fitted model object rather than being recomputed
    from whatever frame happens to be passed to `predict_wind_correction`.
    """
    fcst_u, fcst_v = wind_vector.to_uv(
        frame["fcst_wind_speed"].to_numpy(dtype=float),
        frame["fcst_wind_direction"].to_numpy(dtype=float),
    )
    anchor_u, anchor_v = wind_vector.to_uv(
        frame["anchor_wind_speed"].to_numpy(dtype=float),
        frame["anchor_wind_direction"].to_numpy(dtype=float),
    )
    hour_sin, hour_cos = _hour_encoding(frame)

    features = pd.DataFrame(
        {
            "fcst_u": fcst_u,
            "fcst_v": fcst_v,
            "fcst_air_temp": frame["fcst_air_temp"].to_numpy(dtype=float),
            "fcst_solar_radiation": frame["fcst_solar_radiation"].to_numpy(dtype=float),
            "anchor_u": anchor_u,
            "anchor_v": anchor_v,
            "hour_sin": hour_sin,
            "hour_cos": hour_cos,
        },
        index=frame.index,
    )

    if pooling == "pooled":
        if endpoint_cities is None or len(endpoint_cities) != 2:
            raise ValueError(
                "_wind_feature_frame: pooling='pooled' requires a "
                f"two-city endpoint_cities tuple, got {endpoint_cities!r}"
            )
        features["endpoint_indicator"] = (
            frame["endpoint_city"].to_numpy() == endpoint_cities[1]
        ).astype(float)

    return features


class WindCorrectionModel:
    """
    Fitted wind-correction model. Carries its own ordered feature-name
    list (`feature_names`) so `predict_wind_correction` can never silently
    reorder columns, and its own `endpoint_cities` tuple (when pooled) so
    the SAME two-city ordering used at fit time is reused at predict time.
    """

    def __init__(self, pooling, feature_names, models, endpoint_cities, n_rows_fit):
        self.pooling = pooling
        self.feature_names = feature_names
        self.models = models
        self.endpoint_cities = endpoint_cities
        self.n_rows_fit = n_rows_fit


def fit_wind_correction(
    train_frame: pd.DataFrame, estimator_factory, *, pooling: str,
) -> WindCorrectionModel:
    """
    Fit the wind correction (D-02 approach 3): decompose both the forecast
    and truth wind into u/v via `wind_vector.to_uv`, then fit one estimator
    per component predicting the TRUTH component directly from features.

    Predicting the truth component directly, rather than predicting the
    error and adding it, is a deliberate choice: the two are algebraically
    equivalent for a linear model but not for a tree, and predicting the
    level keeps a single consistent target convention across both
    estimator families in `WIND_CORRECTION_ESTIMATORS`.

    `pooling="pooled"` fits ONE model per component over both endpoint
    cities' rows stacked, with a binary endpoint indicator feature.
    `pooling="per_city"` fits one model per component PER CITY. Both are
    implemented; `select_wind_configuration` decides between them on the
    validation set. This function never sees a test frame -- it fits
    whatever frame it is given.
    """
    if pooling not in _VALID_WIND_POOLING:
        raise ValueError(
            f"fit_wind_correction: pooling must be one of "
            f"{_VALID_WIND_POOLING}, got {pooling!r}"
        )

    if pooling == "pooled":
        endpoint_cities = tuple(sorted(train_frame["endpoint_city"].unique()))
        if len(endpoint_cities) != 2:
            raise ValueError(
                "fit_wind_correction: pooling='pooled' requires exactly "
                f"two distinct endpoint cities, found {endpoint_cities!r}"
            )
        features = _wind_feature_frame(
            train_frame, pooling="pooled", endpoint_cities=endpoint_cities
        )
        truth_u, truth_v = wind_vector.to_uv(
            train_frame["truth_wind_speed"].to_numpy(dtype=float),
            train_frame["truth_wind_direction"].to_numpy(dtype=float),
        )
        u_estimator = estimator_factory()
        v_estimator = estimator_factory()
        u_estimator.fit(features.to_numpy(dtype=float), truth_u)
        v_estimator.fit(features.to_numpy(dtype=float), truth_v)
        return WindCorrectionModel(
            pooling="pooled",
            feature_names=list(features.columns),
            models={"pooled": (u_estimator, v_estimator)},
            endpoint_cities=endpoint_cities,
            n_rows_fit=len(train_frame),
        )

    # pooling == "per_city"
    models = {}
    feature_names = None
    total_rows = 0
    for city, group in train_frame.groupby("endpoint_city"):
        features = _wind_feature_frame(group, pooling="per_city")
        if feature_names is None:
            feature_names = list(features.columns)
        truth_u, truth_v = wind_vector.to_uv(
            group["truth_wind_speed"].to_numpy(dtype=float),
            group["truth_wind_direction"].to_numpy(dtype=float),
        )
        u_estimator = estimator_factory()
        v_estimator = estimator_factory()
        u_estimator.fit(features.to_numpy(dtype=float), truth_u)
        v_estimator.fit(features.to_numpy(dtype=float), truth_v)
        models[city] = (u_estimator, v_estimator)
        total_rows += len(group)

    return WindCorrectionModel(
        pooling="per_city",
        feature_names=feature_names,
        models=models,
        endpoint_cities=None,
        n_rows_fit=total_rows,
    )


class WindCorrectionPrediction:
    """
    Small result object: corrected speed/direction plus the physical clamp
    count. The clamp count is reported rather than the clamp being applied
    silently, matching the visibility discipline Plan 03-04 applied to its
    delta arm.
    """

    def __init__(self, speed, direction, clamped_count):
        self.speed = speed
        self.direction = direction
        self.clamped_count = clamped_count


def predict_wind_correction(
    model: WindCorrectionModel, frame: pd.DataFrame,
) -> WindCorrectionPrediction:
    """
    Build the same features in the same order from `model.feature_names`,
    predict corrected u/v, and recompose with `wind_vector.from_uv`. The
    recomposed speed is clamped at zero as a physical bound (a negative
    speed is never physically meaningful); the clamp count is reported on
    the returned object rather than silently applied.
    """
    if model.pooling == "pooled":
        features = _wind_feature_frame(
            frame, pooling="pooled", endpoint_cities=model.endpoint_cities
        )[model.feature_names]
        u_estimator, v_estimator = model.models["pooled"]
        corrected_u = u_estimator.predict(features.to_numpy(dtype=float))
        corrected_v = v_estimator.predict(features.to_numpy(dtype=float))
    else:
        corrected_u = np.empty(len(frame), dtype=float)
        corrected_v = np.empty(len(frame), dtype=float)
        for city, group in frame.groupby("endpoint_city"):
            features = _wind_feature_frame(group, pooling="per_city")[model.feature_names]
            u_estimator, v_estimator = model.models[city]
            positions = frame.index.get_indexer(group.index)
            corrected_u[positions] = u_estimator.predict(features.to_numpy(dtype=float))
            corrected_v[positions] = v_estimator.predict(features.to_numpy(dtype=float))

    speed, direction = wind_vector.from_uv(corrected_u, corrected_v)
    clamped_count = int((speed < 0).sum())
    speed = np.maximum(speed, 0.0)

    return WindCorrectionPrediction(speed=speed, direction=direction, clamped_count=clamped_count)


def select_wind_configuration(
    train_frame: pd.DataFrame, val_frame: pd.DataFrame, geometry,
) -> dict:
    """
    Fit every (estimator, pooling) combination in `WIND_CORRECTION_
    ESTIMATORS` x {"pooled", "per_city"} on `train_frame`, score each on
    `val_frame` by the mean absolute error of the resulting AMPACITY (not
    the wind, not the u/v components) -- ampacity is the quantity this
    phase is actually comparing, and a correction that improves wind while
    worsening the projected perpendicular component is not an improvement.
    Returns the winning configuration together with the full
    per-configuration score table, so the decision record can report what
    was tried rather than only what won. This function's signature accepts
    only train and validation frames -- it never sees a test frame.
    """
    scores = {}
    for estimator_name, factory in WIND_CORRECTION_ESTIMATORS.items():
        for pooling in _VALID_WIND_POOLING:
            model = fit_wind_correction(train_frame, factory, pooling=pooling)
            prediction = predict_wind_correction(model, val_frame)
            perp = thermal_model.perpendicular_wind(
                prediction.speed, prediction.direction, geometry.bearing_deg
            )
            corrected_ampacity = thermal_model.ieee738_ampacity(
                val_frame["fcst_air_temp"].to_numpy(dtype=float),
                perp,
                val_frame["fcst_solar_radiation"].to_numpy(dtype=float),
                geometry.conductor,
            )
            mae = float(
                np.mean(
                    np.abs(
                        val_frame["truth_ampacity"].to_numpy(dtype=float)
                        - corrected_ampacity
                    )
                )
            )
            key = f"{estimator_name}__{pooling}"
            scores[key] = {
                "estimator": estimator_name,
                "pooling": pooling,
                "mae": mae,
                "clamped_count": prediction.clamped_count,
                "model": model,
            }

    winner_key = min(scores, key=lambda k: scores[k]["mae"])
    return {"winner": scores[winner_key], "winner_key": winner_key, "scores": scores}
