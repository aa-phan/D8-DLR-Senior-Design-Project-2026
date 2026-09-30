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


# ──────────────────────────────────────────────────────────────────────────────
# Arm 4: cooling correction, through the q_conv_override substitution seam
# ──────────────────────────────────────────────────────────────────────────────

_VALID_COOLING_TARGETS = ("level", "log_ratio")


def _make_cooling_linear_regression():
    """Deterministic; no `random_state` argument, mirroring the wind
    family's own `_make_wind_linear_regression`."""
    from sklearn.linear_model import LinearRegression

    return LinearRegression()


def _make_cooling_gradient_boosting():
    """Gradient-boosted-tree arm, same fixed random state as the wind
    family's tree entry, reused for reproducibility across both families."""
    from sklearn.ensemble import GradientBoostingRegressor

    return GradientBoostingRegressor(
        random_state=config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE
    )


# Same registry shape and the same two estimator families as
# WIND_CORRECTION_ESTIMATORS -- a zero-argument factory per entry, never a
# shared instance.
COOLING_CORRECTION_ESTIMATORS: dict = {
    "LinearRegression": _make_cooling_linear_regression,
    "GradientBoostingRegressor": _make_cooling_gradient_boosting,
}


def _cooling_feature_frame(
    frame: pd.DataFrame, fcst_q_conv: np.ndarray, anchor_q_conv: np.ndarray,
) -> pd.DataFrame:
    """
    Build the cooling-correction feature frame: the forecast's own
    convective term, the forecast air temperature and perpendicular wind,
    the anchor observation's own convective term, and a cyclical
    hour-of-day encoding. Never includes the truth of any variable and
    never a value timestamped after the issue time.
    """
    hour_sin, hour_cos = _hour_encoding(frame)
    return pd.DataFrame(
        {
            "fcst_q_conv": fcst_q_conv,
            "fcst_air_temp": frame["fcst_air_temp"].to_numpy(dtype=float),
            "fcst_perp_wind_ms": frame["fcst_perp_wind_ms"].to_numpy(dtype=float),
            "anchor_q_conv": anchor_q_conv,
            "hour_sin": hour_sin,
            "hour_cos": hour_cos,
        },
        index=frame.index,
    )


class CoolingCorrectionModel:
    """
    Fitted cooling-correction model. Carries its own ordered
    `feature_names` list (so `predict_cooling_correction` can never
    silently reorder columns), its `target` parameterization ("level" or
    "log_ratio"), and the `conductor` it was fitted with (so prediction
    recomputes the forecast's own convective term the SAME way, through
    the same extracted physics function, rather than trusting a caller to
    pass a matching conductor at predict time).
    """

    def __init__(self, target, feature_names, estimator, conductor, n_rows_fit):
        self.target = target
        self.feature_names = feature_names
        self.estimator = estimator
        self.conductor = conductor
        self.n_rows_fit = n_rows_fit


def fit_cooling_correction(
    train_frame: pd.DataFrame, estimator_factory, *, target: str, conductor,
) -> CoolingCorrectionModel:
    """
    Fit the cooling correction (D-02 approach 4): predict the convective
    heat-loss term through the SAME extracted `thermal_model.
    convective_heat_loss` function the physics core uses -- never a second
    inline copy of the heat-balance arithmetic.

    `target="level"` predicts the observed (truth) convective term
    directly, computed from the truth air temperature and the truth
    perpendicular wind. `target="log_ratio"` predicts
    `log(truth_term / forecast_term)`, a scale-free parameterization
    insensitive to the convective term's absolute magnitude, which varies
    by more than an order of magnitude between a calm summer night and a
    windy winter afternoon. Both options are implemented;
    `select_cooling_configuration` decides between them on the validation
    set.

    Both parameterizations compute the forecast's own convective term the
    same way -- from the forecast air temperature and the forecast
    perpendicular wind, through `convective_heat_loss`. A non-positive
    forecast term makes the log-ratio undefined, so those rows raise
    naming the count rather than being quietly dropped or clamped. This
    function never sees a test frame -- it fits whatever frame it is
    given.
    """
    if target not in _VALID_COOLING_TARGETS:
        raise ValueError(
            f"fit_cooling_correction: target must be one of "
            f"{_VALID_COOLING_TARGETS}, got {target!r}"
        )

    fcst_q_conv = thermal_model.convective_heat_loss(
        train_frame["fcst_air_temp"].to_numpy(dtype=float),
        train_frame["fcst_perp_wind_ms"].to_numpy(dtype=float),
        conductor,
    )
    anchor_q_conv = thermal_model.convective_heat_loss(
        train_frame["anchor_air_temp"].to_numpy(dtype=float),
        train_frame["anchor_perp_wind_ms"].to_numpy(dtype=float),
        conductor,
    )
    truth_q_conv = thermal_model.convective_heat_loss(
        train_frame["truth_air_temp"].to_numpy(dtype=float),
        train_frame["truth_perp_wind_ms"].to_numpy(dtype=float),
        conductor,
    )

    features = _cooling_feature_frame(train_frame, fcst_q_conv, anchor_q_conv)

    if target == "level":
        y = truth_q_conv
    else:
        non_positive = fcst_q_conv <= 0
        if non_positive.any():
            raise ValueError(
                f"fit_cooling_correction: log_ratio target is undefined for "
                f"{int(non_positive.sum())} row(s) with a non-positive "
                f"forecast convective term"
            )
        y = np.log(truth_q_conv / fcst_q_conv)

    estimator = estimator_factory()
    estimator.fit(features.to_numpy(dtype=float), y)

    return CoolingCorrectionModel(
        target=target,
        feature_names=list(features.columns),
        estimator=estimator,
        conductor=conductor,
        n_rows_fit=len(train_frame),
    )


class CoolingCorrectionPrediction:
    """Small result object: the corrected convective term (W/m)."""

    def __init__(self, q_conv):
        self.q_conv = q_conv


def predict_cooling_correction(
    model: CoolingCorrectionModel, frame: pd.DataFrame,
) -> CoolingCorrectionPrediction:
    """
    Build the same features in the same order from `model.feature_names`,
    predict, and recover the corrected convective term. For `target=
    "level"` the prediction IS the corrected term; for `target=
    "log_ratio"` the corrected term is the forecast's own term multiplied
    by the exponential of the prediction.

    A predicted (or recovered) term at or below zero is rejected rather
    than passed into the physics, naming the offending row count: a
    non-positive convective term is physically meaningless, and feeding
    one into the heat balance would produce an inflated ampacity -- in
    this project's domain, the failure direction that can get someone
    hurt, not merely the direction that scores badly.
    """
    fcst_q_conv = thermal_model.convective_heat_loss(
        frame["fcst_air_temp"].to_numpy(dtype=float),
        frame["fcst_perp_wind_ms"].to_numpy(dtype=float),
        model.conductor,
    )
    anchor_q_conv = thermal_model.convective_heat_loss(
        frame["anchor_air_temp"].to_numpy(dtype=float),
        frame["anchor_perp_wind_ms"].to_numpy(dtype=float),
        model.conductor,
    )
    features = _cooling_feature_frame(frame, fcst_q_conv, anchor_q_conv)[model.feature_names]
    prediction = model.estimator.predict(features.to_numpy(dtype=float))

    if model.target == "level":
        corrected_q_conv = np.asarray(prediction, dtype=float)
    else:
        non_positive = fcst_q_conv <= 0
        if non_positive.any():
            raise ValueError(
                f"predict_cooling_correction: log_ratio target is "
                f"undefined for {int(non_positive.sum())} row(s) with a "
                f"non-positive forecast convective term"
            )
        corrected_q_conv = fcst_q_conv * np.exp(prediction)

    bad = corrected_q_conv <= 0
    if bad.any():
        raise ValueError(
            f"predict_cooling_correction: predicted a non-positive "
            f"convective term for {int(bad.sum())} row(s) -- refusing to "
            f"feed a physically meaningless value into the heat balance"
        )

    return CoolingCorrectionPrediction(q_conv=corrected_q_conv)


def apply_cooling_correction(frame: pd.DataFrame, corrected_q_conv, geometry) -> np.ndarray:
    """
    Push `corrected_q_conv` into `thermal_model.ieee738_ampacity` via its
    `q_conv_override` keyword, with every other argument taken from the
    FORECAST group. Does NOT reimplement any part of the heat balance --
    the override seam exists precisely so this arm can substitute one term
    without forking the physics, and Plan 03-02 proved the seam is a
    bit-exact no-op when unused.
    """
    return thermal_model.ieee738_ampacity(
        frame["fcst_air_temp"].to_numpy(dtype=float),
        frame["fcst_perp_wind_ms"].to_numpy(dtype=float),
        frame["fcst_solar_radiation"].to_numpy(dtype=float),
        geometry.conductor,
        q_conv_override=np.asarray(corrected_q_conv, dtype=float),
    )


def select_cooling_configuration(
    train_frame: pd.DataFrame, val_frame: pd.DataFrame, geometry,
) -> dict:
    """
    Fit every (estimator, target) combination in `COOLING_CORRECTION_
    ESTIMATORS` x {"level", "log_ratio"} on `train_frame`, score each on
    `val_frame` by the mean absolute error of the resulting AMPACITY
    (pushed through `apply_cooling_correction`'s `q_conv_override` seam),
    and return the winner together with the full per-configuration score
    table. This function's signature accepts only train and validation
    frames -- it never sees a test frame.
    """
    scores = {}
    for estimator_name, factory in COOLING_CORRECTION_ESTIMATORS.items():
        for target in _VALID_COOLING_TARGETS:
            model = fit_cooling_correction(
                train_frame, factory, target=target, conductor=geometry.conductor
            )
            prediction = predict_cooling_correction(model, val_frame)
            corrected_ampacity = apply_cooling_correction(
                val_frame, prediction.q_conv, geometry
            )
            mae = float(
                np.mean(
                    np.abs(
                        val_frame["truth_ampacity"].to_numpy(dtype=float)
                        - corrected_ampacity
                    )
                )
            )
            key = f"{estimator_name}__{target}"
            scores[key] = {
                "estimator": estimator_name,
                "target": target,
                "mae": mae,
                "model": model,
            }

    winner_key = min(scores, key=lambda k: scores[k]["mae"])
    return {"winner": scores[winner_key], "winner_key": winner_key, "scores": scores}
