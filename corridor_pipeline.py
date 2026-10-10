"""
Corridor Pipeline Orchestrator (Track 1)
==========================================
Reads archived history for a corridor, forecasts ahead, builds an anomaly
detector from that forecast, then runs rate_corridor with the detector wired
in as G6 (and archives the result so the next run has more history).
"""

import logging

import ampacity_forecast
import historical_archive
from anomaly_detector import AnomalyDetector
import corridor_discretization

log = logging.getLogger(__name__)


def run_corridor_pipeline(
    corridor_name: str,
    start: str,
    end: str,
    stations,
    provider: str = "synoptic",
    archive_path: str = None,
    forecast_method: str = "naive",
    archive: bool = True,
    fetch_weather=None,
) -> dict:
    """
    Full Track 1 integration for one corridor, one run:
      1. read archived history for this corridor
      2. forecast ahead from that history (None if cold start)
      3. build an anomaly detector from the forecast + history
      4. rate the corridor with that detector wired into G6

    Returns whatever rate_corridor returns, plus a `pipeline` key describing
    what steps 1-3 produced (history rows, forecast, detector signal).
    """
    history = historical_archive.read_history(path=archive_path, corridor=corridor_name)

    # Fallback cycles archive the *static* rating as dlr_amps. Feeding those
    # back in makes the naive forecast equal the static rating, so the next
    # real reading looks anomalous, falls back, and archives static again --
    # a self-sustaining latch. Forecast and detector only learn from cycles
    # that produced a computed rating.
    total_rows = int(len(history))
    if "fallback" in history.columns and total_rows:
        history = history[history["fallback"].astype(str).str.lower() != "true"].reset_index(drop=True)

    # A forecast failure (e.g. method="ml" with no trained artifact) must not
    # take the rating down: G6 degrades to the rolling baseline / cold start.
    try:
        forecast = ampacity_forecast.forecast_ampacity(history, method=forecast_method)
    except Exception as exc:
        log.warning(
            "forecast_ampacity(method=%r) failed for %s (%s) -- continuing without a forecast",
            forecast_method, corridor_name, exc,
        )
        forecast = None

    # A forecast whose band has zero width (too few backtest residuals to
    # span both signs) has no discriminating power: G6 would flag any
    # deviation from the last value. Same convention the rolling baseline
    # uses for a zero standard deviation -- don't gate on it. The detector
    # then runs on whatever else it has (cold start / rolling baseline).
    forecast_degenerate = (
        forecast is not None and forecast.ci_upper_amps - forecast.ci_lower_amps <= 0
    )
    if forecast_degenerate:
        log.info("%s: forecast band has zero width -- not used for G6 this run", corridor_name)
        forecast_for_detector = None
    else:
        forecast_for_detector = forecast

    detector = AnomalyDetector.for_corridor(
        corridor_name, forecast=forecast_for_detector, history=history,
    )

    result = corridor_discretization.rate_corridor(
        corridor_name, start, end, stations,
        anomaly_detector=detector,
        archive=archive,
        archive_path=archive_path,
        provider=provider,
        fetch_weather=fetch_weather,
    )

    result["pipeline"] = {
        "history_rows": total_rows,
        "usable_history_rows": int(len(history)),
        "forecast_method": forecast_method,
        "forecast_used_by_g6": forecast_for_detector is not None,
        "forecast": (
            None if forecast is None else {
                "amps": float(forecast.amps),
                "ci_lower_amps": float(forecast.ci_lower_amps),
                "ci_upper_amps": float(forecast.ci_upper_amps),
                "n_observations": int(forecast.n_observations),
                "horizon_min": forecast.horizon_min,
            }
        ),
        "detector_signal": getattr(detector, "signal", None),
        "detector_model": getattr(detector, "model_source", None),
    }
    return result
