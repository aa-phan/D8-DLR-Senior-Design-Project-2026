"""
Ampacity Forecasting (C9)
==================================================
This module is C9 per `docs/data-science/specs/C9-ampacity-forecasting.md`.

Per D-02, this module projects the archived `dlr_amps` series forward
directly — it does not re-run weather through IEEE 738. Two Tier-1 methods
(D-10) are supported behind one signature: `method="naive"` (the last
observed value) and `method="ewm"` (an exponentially-weighted moving
average). The confidence band is an empirical residual quantile band
(D-03) derived from a true expanding-window walk-forward backtest, never a
normal-distribution (mean ± k*std) band and never an in-sample fit —
`backtest_residuals` is the only source of the band's width, and it is
strictly out-of-sample: each prediction is made using only observations
strictly earlier than the value it predicts (RESEARCH.md "Don't Hand-Roll"
— a randomized/shuffled train/validation split leaks future values into
training and produces a falsely optimistic band).

Plan 04-01's original in-sample residual difference (naive-only,
`series.diff()`) has been replaced by Plan 04-02 with this true
walk-forward backtest; `forecast_ampacity`'s signature is extended (a new
`method` keyword) but no existing argument name or position changed, and
`ForecastResult` gained a new trailing `n_residuals` attribute with a
default of 0 so Plan 04-03's construction sites are unaffected.

v1.3 Phase 1 (01-01) adds a third, Tier-2 method: `method="ml"`, a real
fitted `scikit-learn` estimator trained offline (`forecast_training.py`)
on a real, Open-Meteo-backfill-derived per-corridor series and persisted
per corridor under `config.FORECAST_ML_MODEL_DIR`. Unlike `"naive"`/
`"ewm"`, `"ml"` is multivariate (D-04): it builds lagged-`dlr_amps` +
weather features (`build_ml_features`) and selects its fitted model from
`history["corridor"]` alone (D-05) -- no change to this module's public
`forecast_ampacity` signature. `_point_forecast` and `backtest_residuals`
both gained optional `history`/`model` parameters so `"ml"` can see the
weather columns naive/EWM never needed; those parameters are internal-only
extensions (RESEARCH.md Pattern 1) and are inert for `"naive"`/`"ewm"`.
Importing this module still performs no file I/O, no network call, and no
`sklearn`/`joblib` import -- `joblib` is imported lazily inside
`_load_corridor_model`, so naive/EWM keep working with `scikit-learn`
absent.
"""

import logging
import os

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)

# The one definition of the valid forecast methods. `_point_forecast` and
# `forecast_ampacity` both raise ValueError naming this tuple for anything
# else, rather than silently falling through to a default. "ml" (v1.3
# Phase 1) is the first Tier-2, fitted-model method alongside the original
# Tier-1 "naive"/"ewm" pair (D-10).
FORECAST_METHODS: tuple[str, ...] = ("naive", "ewm", "ml")

# The single ordered feature-name tuple the "ml" estimator is fitted on and
# predicted from (D-04): lagged dlr_amps offsets, then the rolling mean,
# then the multivariate weather columns, then a cyclical hour-of-day
# encoding. `build_ml_features` returns exactly these columns, in this
# order -- the one feature-engineering implementation both the runtime
# module and `forecast_training.py` share (the latter imports the former).
ML_FEATURE_COLUMNS: tuple[str, ...] = (
    tuple(f"dlr_amps_lag_{h}h" for h in config.FORECAST_ML_LAG_HOURS)
    + (f"dlr_amps_roll_mean_{config.FORECAST_ML_ROLLING_WINDOW_HOURS}h",)
    + tuple(config.FORECAST_ML_FEATURE_WEATHER_COLUMNS)
    + ("hour_sin", "hour_cos")
)


class ForecastResult:
    """
    Plain result object for one `forecast_ampacity` call. Every numeric
    attribute is `float(...)`-wrapped at assignment (RESEARCH.md
    Pitfall 2's boundary discipline, applied here since this class is the
    public boundary of the forecast module).
    """

    def __init__(self, horizon_min, amps, ci_lower_amps, ci_upper_amps,
                 n_observations, method, n_residuals=0):
        self.horizon_min = float(horizon_min)
        self.amps = float(amps)
        self.ci_lower_amps = float(ci_lower_amps)
        self.ci_upper_amps = float(ci_upper_amps)
        self.n_observations = int(n_observations)
        self.method = str(method)
        self.n_residuals = int(n_residuals)

    def __repr__(self):
        return (
            f"ForecastResult(horizon_min={self.horizon_min!r}, amps={self.amps!r}, "
            f"ci_lower_amps={self.ci_lower_amps!r}, ci_upper_amps={self.ci_upper_amps!r}, "
            f"n_observations={self.n_observations!r}, method={self.method!r}, "
            f"n_residuals={self.n_residuals!r})"
        )


def _extract_series(history: pd.DataFrame) -> pd.Series:
    """
    Pull the `dlr_amps` series out of an archive frame, indexed by
    `datetime_utc` when that column is present and parseable so
    `method="ewm"` can use the time-aware smoothing form. Falls back to
    the frame's own (positional) index otherwise — `_point_forecast`
    documents the resulting approximation.
    """
    if "dlr_amps" not in history.columns:
        return pd.Series(dtype=float)

    series = history["dlr_amps"]

    if "datetime_utc" in history.columns:
        try:
            series = series.copy()
            series.index = pd.to_datetime(history["datetime_utc"])
        except (ValueError, TypeError):
            pass  # keep the frame's original index; time-aware EWM falls back

    return series.dropna()


def build_ml_features(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Build the `ML_FEATURE_COLUMNS` feature frame from a `DatetimeIndex`-ed
    frame carrying `dlr_amps` plus the `config.FORECAST_ML_FEATURE_WEATHER_
    COLUMNS` weather columns (the shape `_extract_ml_frame` returns).

    Lagged `dlr_amps` columns use `.shift(h)` for each
    `config.FORECAST_ML_LAG_HOURS` offset; the rolling-mean column uses
    `.rolling(window, min_periods=window).mean()` shifted by one row so
    the current row's own value never leaks into its own feature
    (RESEARCH.md Pitfall 4 — no feature may see its own or a later row).
    `hour_sin`/`hour_cos` come from `index.hour` as a cyclical encoding.
    Returned frame is indexed identically to `frame`; rows whose lag/
    rolling window is not yet fully determined (the leading
    `max(FORECAST_ML_LAG_HOURS)` rows) come back with nulls — this
    function never invents a value for a missing input, the caller drops
    incomplete rows.
    """
    features = pd.DataFrame(index=frame.index)

    for h in config.FORECAST_ML_LAG_HOURS:
        features[f"dlr_amps_lag_{h}h"] = frame["dlr_amps"].shift(h)

    window = config.FORECAST_ML_ROLLING_WINDOW_HOURS
    features[f"dlr_amps_roll_mean_{window}h"] = (
        frame["dlr_amps"].rolling(window, min_periods=window).mean().shift(1)
    )

    for column in config.FORECAST_ML_FEATURE_WEATHER_COLUMNS:
        features[column] = frame[column]

    hours = frame.index.hour.to_numpy(dtype=float)
    features["hour_sin"] = np.sin(2 * np.pi * hours / 24.0)
    features["hour_cos"] = np.cos(2 * np.pi * hours / 24.0)

    return features[list(ML_FEATURE_COLUMNS)]


def _extract_ml_frame(history: pd.DataFrame) -> pd.DataFrame:
    """
    Build the `"ml"` method's working frame from an archive-shaped
    `history`: requires `dlr_amps`, `corridor`, `datetime_utc` and every
    column in `config.FORECAST_ML_FEATURE_WEATHER_COLUMNS`, raising
    `ValueError` naming the missing column(s) otherwise.

    Parses `datetime_utc` into a `DatetimeIndex` (raises `ValueError`
    naming the parse failure if it cannot be parsed — unlike
    `_extract_series`'s silent positional-index fallback, the `"ml"` path
    needs real timestamps for lag ordering and hour-of-day, so a bad
    timestamp column here is a hard failure, not an approximation), sorts
    ascending, and drops rows with a null `dlr_amps`. The `"ml"` branch of
    `forecast_ampacity` derives its series as this frame's `dlr_amps`
    column rather than calling `_extract_series`, so the series and the
    feature frame built from this same frame are structurally the same
    rows and positional slicing in `backtest_residuals` cannot drift
    apart.
    """
    required = (
        {"dlr_amps", "corridor", "datetime_utc"}
        | set(config.FORECAST_ML_FEATURE_WEATHER_COLUMNS)
    )
    missing = sorted(required - set(history.columns))
    if missing:
        raise ValueError(
            f"_extract_ml_frame: history is missing required column(s) {missing}"
        )

    try:
        index = pd.to_datetime(history["datetime_utc"])
    except Exception as exc:
        raise ValueError(
            f"_extract_ml_frame: could not parse 'datetime_utc' into a "
            f"DatetimeIndex: {exc}"
        ) from exc

    frame = history.copy()
    frame.index = index
    frame = frame.sort_index()
    frame = frame[frame["dlr_amps"].notna()]
    return frame


def _corridor_of(frame: pd.DataFrame) -> str:
    """
    Return `frame`'s single `corridor` value.

    Raises `ValueError` naming both/all distinct values when `frame`
    carries more than one corridor (`historical_archive.read_history(
    corridor=...)` already filters to one corridor per call, so a mixed
    frame reaching here is a caller bug, not a case to average over), and
    raises naming the valid corridors when the single value is absent from
    `config.CORRIDOR_ENDPOINTS` -- this is also the path-traversal guard
    for `_model_path_for`: the corridor key is validated against a closed
    set before it is ever formatted into a filename (T-01-03).
    """
    corridors = frame["corridor"].unique().tolist()
    if len(corridors) != 1:
        raise ValueError(
            f"_corridor_of: expected exactly one corridor in `history`, "
            f"found {sorted(str(c) for c in corridors)}"
        )

    corridor = corridors[0]
    if corridor not in config.CORRIDOR_ENDPOINTS:
        raise ValueError(
            f"_corridor_of: unknown corridor {corridor!r}; valid corridors: "
            f"{sorted(config.CORRIDOR_ENDPOINTS)}"
        )
    return corridor


def _model_path_for(corridor: str) -> str:
    """
    Resolve a corridor's persisted model artifact path. Built only from
    `config.FORECAST_ML_MODEL_DIR` + `config.FORECAST_ML_MODEL_FILENAME_
    TEMPLATE` -- no function on the `"ml"` path accepts a caller-supplied
    path (T-01-03); callers must go through `_corridor_of` first so
    `corridor` is already validated against `config.CORRIDOR_ENDPOINTS`.
    """
    filename = config.FORECAST_ML_MODEL_FILENAME_TEMPLATE.format(corridor=corridor)
    return os.path.join(config.FORECAST_ML_MODEL_DIR, filename)


# Per-corridor fitted-model cache, populated by `_load_corridor_model`.
_MODEL_CACHE: dict = {}


def _load_corridor_model(corridor: str):
    """
    Load (and cache) the persisted fitted estimator for `corridor`.

    Imports `joblib` lazily, inside this function body, so `import
    ampacity_forecast` stays free of file I/O, network calls and any
    `sklearn`/`joblib` import -- naive/EWM keep working in an environment
    where `scikit-learn` is absent. Raises `FileNotFoundError` naming the
    corridor, the expected path, and the training command that produces
    it when the artifact does not exist -- this module never degrades to
    another method when a model is missing (see this plan's prohibitions).
    """
    if corridor in _MODEL_CACHE:
        return _MODEL_CACHE[corridor]

    path = _model_path_for(corridor)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"_load_corridor_model: no trained model for corridor "
            f"{corridor!r} at {path!r}. Train one with: "
            f".venv/bin/python3 backend/forecast_training.py "
            f"--corridor {corridor}"
        )

    import joblib  # lazy — keeps `import ampacity_forecast` sklearn-free

    model = joblib.load(path)
    _MODEL_CACHE[corridor] = model
    return model


def _point_forecast(series: pd.Series, method: str, halflife_min=None,
                     history=None, model=None) -> float:
    """
    One-step point forecast from `series` using `method`.

    `method="naive"` returns the last observed value. `method="ewm"`
    returns the last value of an exponentially-weighted moving average
    with half-life `halflife_min` minutes (defaults to
    `config.FORECAST_EWM_HALFLIFE_MIN`): if `series.index` is a
    `pd.DatetimeIndex` (the usual case — `_extract_series` sets one from
    `datetime_utc` whenever that column parses), the time-aware form
    (`times=series.index`) is used so unevenly-sampled data is weighted
    correctly. Otherwise, the half-life is approximated in observation
    counts (one observation ~= one row, the crudest possible span
    conversion) — this fallback only triggers when the caller hasn't
    supplied a `datetime_utc`-derived index, not on this module's normal
    archive-reading path.

    `method="ml"` (v1.3 Phase 1) requires `history` (raises `ValueError`
    otherwise) and an already-fitted `model` (raises `ValueError`
    otherwise — this module never calls an estimator's training entry
    point, only its `.predict()`). It builds `build_ml_features(history)`,
    takes the last feature row, raises `ValueError` naming the offending
    column if any value in that row is null (a missing weather reading on
    the inference row is a failed forecast, not a zero), and returns
    `float(model.predict(row_as_2d)[0])`.

    Raises `ValueError` naming `FORECAST_METHODS` for anything else.
    """
    if method not in FORECAST_METHODS:
        raise ValueError(
            f"Unknown forecast method {method!r}; FORECAST_METHODS is {FORECAST_METHODS}"
        )

    if method == "naive":
        return float(series.iloc[-1])

    if method == "ml":
        if history is None:
            raise ValueError(
                "_point_forecast: method='ml' requires the `history` frame"
            )
        if model is None:
            raise ValueError(
                "_point_forecast: method='ml' requires an already-fitted `model`"
            )

        features = build_ml_features(history)
        last_row = features.iloc[-1]
        null_columns = last_row[last_row.isna()].index.tolist()
        if null_columns:
            raise ValueError(
                f"_point_forecast: cannot produce an 'ml' point forecast -- "
                f"feature column(s) {null_columns} are null on the last row"
            )

        row_as_2d = last_row.to_numpy(dtype=float).reshape(1, -1)
        return float(model.predict(row_as_2d)[0])

    # method == "ewm"
    if halflife_min is None:
        halflife_min = config.FORECAST_EWM_HALFLIFE_MIN

    if isinstance(series.index, pd.DatetimeIndex):
        smoothed = series.ewm(
            halflife=pd.Timedelta(minutes=float(halflife_min)),
            times=series.index,
        ).mean()
    else:
        smoothed = series.ewm(halflife=max(float(halflife_min), 1.0)).mean()

    return float(smoothed.iloc[-1])


def backtest_residuals(series: pd.Series, method: str, min_train_rows=None,
                        halflife_min=None, history=None) -> np.ndarray:
    """
    Expanding-window walk-forward backtest residuals for `method` over
    `series`.

    Starting at index `min_train_rows` (defaults to
    `config.FORECAST_MIN_HISTORY_ROWS`), this walks forward one
    observation at a time: at each step `i`, `_point_forecast` is called
    on the STRICT PREFIX `series.iloc[:i]` (exclusive of `i`) and the
    residual is `series.iloc[i] - prediction`. That exclusivity is the
    whole point (RESEARCH.md "Don't Hand-Roll", time-series train/
    validation split row): a randomized/shuffled split leaks future
    values into training and produces a falsely optimistic (too-narrow)
    band, which is exactly the "too good to be true" signature
    RESEARCH.md Pitfall 1 warns about.

    `history` (v1.3 Phase 1) is required for `method="ml"`: the fitted
    model for `history`'s corridor is loaded ONCE, before the loop (never
    refit per step — RESEARCH.md Pattern 4), and each step calls
    `_point_forecast` with that same fixed model plus `history.iloc[:i]`
    (the identical strict-prefix slice applied to `series`, since
    `forecast_ampacity` builds both from the same `_extract_ml_frame`
    output, so positional slicing cannot drift the two apart). `"naive"`/
    `"ewm"` ignore `history` entirely and behave byte-identically to
    before this parameter existed.

    Returns a `numpy.ndarray` of the residuals, empty when the series has
    `min_train_rows` or fewer observations (not enough to produce even
    one out-of-sample prediction).
    """
    if min_train_rows is None:
        min_train_rows = config.FORECAST_MIN_HISTORY_ROWS
    if halflife_min is None:
        halflife_min = config.FORECAST_EWM_HALFLIFE_MIN

    n = len(series)
    if n <= min_train_rows:
        return np.array([], dtype=float)

    model = None
    if method == "ml":
        if history is None:
            raise ValueError(
                "backtest_residuals: method='ml' requires the `history` frame"
            )
        model = _load_corridor_model(_corridor_of(history))

    residuals = np.empty(n - min_train_rows, dtype=float)
    for offset, i in enumerate(range(min_train_rows, n)):
        prefix = series.iloc[:i]
        history_prefix = history.iloc[:i] if history is not None else None
        prediction = _point_forecast(
            prefix, method, halflife_min, history=history_prefix, model=model
        )
        residuals[offset] = float(series.iloc[i]) - prediction

    return residuals


def forecast_ampacity(history: pd.DataFrame, horizon_min=None, method="naive",
                       quantiles=None, min_rows=None):
    """
    Forecast ampacity `horizon_min` minutes ahead from an archive frame
    (the shape `historical_archive.read_history` returns), using
    `method` (`"naive"` or `"ewm"`, `FORECAST_METHODS`).

    Returns `None` — an explicit, documented cold start — when fewer than
    `min_rows` non-null `dlr_amps` observations are available, rather
    than a confidently wrong band on a handful of rows (RESEARCH.md
    Pitfall 1).

    Otherwise returns a `ForecastResult`: the point forecast comes from
    `_point_forecast`; the band comes from `backtest_residuals`'
    out-of-sample residuals — `np.quantile(residuals, q)` at each of the
    two `quantiles`, lower edge first, added to the point forecast. If
    the backtest cannot yet produce any residuals (exactly `min_rows`
    observations), the band collapses to the point forecast on both
    sides and `n_residuals` is 0 rather than inventing a width. If the
    computed band would exclude its own center (a defect — clamped, not
    silently shipped, since that would be exactly the overconfidence this
    module exists to prevent), both edges are clamped to the point
    forecast and a warning is logged.

    Raises `ValueError` naming `FORECAST_METHODS` for an unknown `method`,
    checked before any history is read so an invalid method never
    silently falls through to a default regardless of history length.
    """
    if method not in FORECAST_METHODS:
        raise ValueError(
            f"Unknown forecast method {method!r}; FORECAST_METHODS is {FORECAST_METHODS}"
        )

    if horizon_min is None:
        horizon_min = config.FORECAST_HORIZON_MINUTES
    if quantiles is None:
        quantiles = config.FORECAST_BACKTEST_QUANTILES
    if min_rows is None:
        min_rows = config.FORECAST_MIN_HISTORY_ROWS

    halflife_min = config.FORECAST_EWM_HALFLIFE_MIN

    if method == "ml":
        # _extract_ml_frame -> series from that frame -> same cold-start
        # return of None -> load the model via _corridor_of ->
        # _point_forecast(..., history=ml_frame, model=model) ->
        # backtest_residuals(..., history=ml_frame). No second path to
        # the four output columns; the quantile/clamp logic below is
        # reused verbatim for every method.
        ml_frame = _extract_ml_frame(history)
        series = ml_frame["dlr_amps"]

        if len(series) < min_rows:
            return None

        model = _load_corridor_model(_corridor_of(ml_frame))
        point_forecast = _point_forecast(
            series, method, halflife_min, history=ml_frame, model=model
        )
        residuals = backtest_residuals(
            series, method, min_train_rows=min_rows, halflife_min=halflife_min,
            history=ml_frame,
        )
    else:
        series = _extract_series(history)

        if len(series) < min_rows:
            return None

        point_forecast = _point_forecast(series, method, halflife_min)

        residuals = backtest_residuals(
            series, method, min_train_rows=min_rows, halflife_min=halflife_min
        )

    if residuals.size == 0:
        ci_lower = point_forecast
        ci_upper = point_forecast
        n_residuals = 0
    else:
        q_lo, q_hi = quantiles
        ci_lower = point_forecast + float(np.quantile(residuals, q_lo))
        ci_upper = point_forecast + float(np.quantile(residuals, q_hi))
        n_residuals = int(residuals.size)

    # A band that excludes its own center is a defect, not a valid (if
    # surprising) result — clamp and log rather than silently shipping the
    # exact overconfidence this task exists to prevent.
    if ci_lower > point_forecast or ci_upper < point_forecast:
        logger.warning(
            "forecast_ampacity: computed band [%.3f, %.3f] excluded its own "
            "center %.3f -- clamping both edges to the point forecast",
            ci_lower, ci_upper, point_forecast,
        )
        ci_lower = point_forecast
        ci_upper = point_forecast

    return ForecastResult(
        horizon_min=horizon_min,
        amps=point_forecast,
        ci_lower_amps=ci_lower,
        ci_upper_amps=ci_upper,
        n_observations=len(series),
        method=method,
        n_residuals=n_residuals,
    )


def forecast_columns(result) -> dict:
    """
    Map a `ForecastResult` onto exactly the four forecast
    `units_def.PIPELINE_SCHEMA` v2 keys. This is the ONLY place a
    `ForecastResult` becomes pipeline output — the key spellings are
    owned by `units_def.PIPELINE_SCHEMA`, not duplicated here as a second
    schema object (RESEARCH.md Pitfall 3); no caller may assemble these
    keys itself. `units_def` is deliberately not imported here — the
    mapping below is a literal dict of four key names, and
    `ampacity_forecast_test.py::test_forecast_columns_keys_all_exist_in_pipeline_schema`
    is what keeps it in agreement with the schema, catching a rename on
    either side.

    Returns `{}` when `result` is `None`, so a cold-start run (no
    forecast yet) emits no forecast columns at all rather than nulls or
    zeros that could be mistaken for a real forecast.
    """
    if result is None:
        return {}

    return {
        "forecast_horizon_min": float(result.horizon_min),
        "forecast_amps": float(result.amps),
        "forecast_ci_lower_amps": float(result.ci_lower_amps),
        "forecast_ci_upper_amps": float(result.ci_upper_amps),
    }
