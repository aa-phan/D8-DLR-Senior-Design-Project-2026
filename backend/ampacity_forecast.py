"""
Ampacity Forecasting (C9)
==================================================
This module is C9 per `docs/data-science/specs/C9-ampacity-forecasting.md`.

Per D-02, this module projects the archived `dlr_amps` series forward
directly — it does not re-run weather through IEEE 738. The point
forecast is the last observed value (`method="naive"`, the honest Tier-1
baseline per D-10), and the confidence band is an empirical residual
quantile band (D-03), not a normal-distribution (mean ± k*std) band.

Plan 04-02 replaces the in-sample residual difference used here with a
true expanding-window walk-forward backtest and adds an EWM method;
neither changes `forecast_ampacity`'s signature or `ForecastResult`'s
attributes.
"""

import numpy as np
import pandas as pd

import config


class ForecastResult:
    """
    Plain result object for one `forecast_ampacity` call. Every numeric
    attribute is `float(...)`-wrapped at assignment (RESEARCH.md
    Pitfall 2's boundary discipline, applied here since this class is the
    public boundary of the forecast module).
    """

    def __init__(self, horizon_min, amps, ci_lower_amps, ci_upper_amps, n_observations, method):
        self.horizon_min = float(horizon_min)
        self.amps = float(amps)
        self.ci_lower_amps = float(ci_lower_amps)
        self.ci_upper_amps = float(ci_upper_amps)
        self.n_observations = int(n_observations)
        self.method = str(method)

    def __repr__(self):
        return (
            f"ForecastResult(horizon_min={self.horizon_min!r}, amps={self.amps!r}, "
            f"ci_lower_amps={self.ci_lower_amps!r}, ci_upper_amps={self.ci_upper_amps!r}, "
            f"n_observations={self.n_observations!r}, method={self.method!r})"
        )


def forecast_ampacity(history: pd.DataFrame, horizon_min=None, quantiles=None, min_rows=None):
    """
    Forecast ampacity `horizon_min` minutes ahead from an archive frame
    (the shape `historical_archive.read_history` returns).

    Returns `None` — an explicit, documented cold start — when fewer than
    `min_rows` non-null `dlr_amps` observations are available, rather than
    a confidently wrong band on a handful of rows (RESEARCH.md Pitfall 1).

    Otherwise returns a `ForecastResult`: the point forecast is the last
    observed `dlr_amps` value (`method="naive"`); the residual sample is
    the series of one-step-ahead naive residuals (successive differences,
    nulls dropped); the band is the point forecast plus
    `np.quantile(residuals, q)` for each of the two `quantiles`, lower
    edge first.
    """
    if horizon_min is None:
        horizon_min = config.FORECAST_HORIZON_MINUTES
    if quantiles is None:
        quantiles = config.FORECAST_BACKTEST_QUANTILES
    if min_rows is None:
        min_rows = config.FORECAST_MIN_HISTORY_ROWS

    series = history["dlr_amps"].dropna() if "dlr_amps" in history.columns else pd.Series(dtype=float)

    if len(series) < min_rows:
        return None

    point_forecast = float(series.iloc[-1])

    residuals = series.diff().dropna()
    q_lo, q_hi = quantiles
    ci_lower = point_forecast + float(np.quantile(residuals, q_lo))
    ci_upper = point_forecast + float(np.quantile(residuals, q_hi))

    return ForecastResult(
        horizon_min=horizon_min,
        amps=point_forecast,
        ci_lower_amps=ci_lower,
        ci_upper_amps=ci_upper,
        n_observations=len(series),
        method="naive",
    )
