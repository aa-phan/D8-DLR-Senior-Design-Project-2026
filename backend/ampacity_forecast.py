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
"""

import logging

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)

# The one definition of the valid forecast methods (D-10, Tier 1 only this
# phase). `_point_forecast` and `forecast_ampacity` both raise ValueError
# naming this tuple for anything else, rather than silently falling through
# to a default.
FORECAST_METHODS: tuple[str, ...] = ("naive", "ewm")


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


def _point_forecast(series: pd.Series, method: str, halflife_min=None) -> float:
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

    Raises `ValueError` naming `FORECAST_METHODS` for anything else.
    """
    if method not in FORECAST_METHODS:
        raise ValueError(
            f"Unknown forecast method {method!r}; FORECAST_METHODS is {FORECAST_METHODS}"
        )

    if method == "naive":
        return float(series.iloc[-1])

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
                        halflife_min=None) -> np.ndarray:
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

    residuals = np.empty(n - min_train_rows, dtype=float)
    for offset, i in enumerate(range(min_train_rows, n)):
        prefix = series.iloc[:i]
        prediction = _point_forecast(prefix, method, halflife_min)
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

    series = _extract_series(history)

    if len(series) < min_rows:
        return None

    halflife_min = config.FORECAST_EWM_HALFLIFE_MIN
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
