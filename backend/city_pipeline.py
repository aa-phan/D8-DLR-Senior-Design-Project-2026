"""
City Pipeline Orchestrator (Track 1)
==========================================
Per-city replacement for the retired corridor pipeline: reads one city's
archived history, cleans it (`data_cleaning.clean_history`), forecasts ahead,
builds that city's anomaly detector from the forecast + the cleaned history,
then runs `city_rating.rate_city` with the detector wired in as G6 (and
archives the result so the next run has more history).
"""

import logging

import ampacity_forecast
import city_rating
import data_cleaning
import historical_archive
from anomaly_detector import AnomalyDetector

log = logging.getLogger(__name__)

# Longest `pipeline["forecast_error"]` kept; an exception message can be a page.
FORECAST_ERROR_MAX_CHARS = 300


def run_city_pipeline(
    city: str,
    start: str,
    end: str,
    stations,
    provider: str = "synoptic",
    archive_path: str = None,
    forecast_method: str = "naive",
    archive: bool = True,
    fetch_weather=None,
    history_reader=None,
) -> dict:
    """
    Full Track 1 integration for one city, one run:
      1. read this city's archived history
      2. clean it (data_cleaning.clean_history): the forecast and detector
         see only the rows left usable
      3. forecast ahead from that history (None if cold start)
      4. build the city's anomaly detector from the forecast + history
      5. rate the city with that detector wired into G6

    `history_reader` is how the Postgres store (DB-02) supplies history: a
    callable `(city, end) -> frame` returning that city's rows before the
    run's slot, shaped like `historical_archive.ARCHIVE_COLUMNS`. None keeps
    the CSV archive (`archive_path`).

    Returns whatever `rate_city` returns, plus a `pipeline` key describing
    what steps 1-4 produced (history rows, forecast, detector signal).
    """
    if history_reader is not None:
        history = history_reader(city, end)
    else:
        history = historical_archive.read_history(path=archive_path, city=city)

    total_rows = int(len(history))

    # A cleaning failure must not take the rating down, and unvetted history
    # is not fed to G6: continue with an empty history (the detector's own
    # convention is no signal, no trips). The fallback-row rule that breaks
    # the static-rating latch lives in data_cleaning.
    cleaning_error = None
    try:
        cleaned = data_cleaning.clean_history(history, as_of=end)
        history = cleaned.usable
        flagged = ", ".join(
            f"{name}={count}"
            for name, count in cleaned.report["flag_counts"].items() if count
        ) or "no rows flagged"
        log.info(
            "%s: %d of %d history rows usable after cleaning (%s)",
            city, int(len(history)), total_rows, flagged,
        )
    except Exception as exc:
        cleaning_error = f"data cleaning failed: {exc}"
        log.warning(
            "data cleaning failed for %s (%s) -- continuing with no history (cold start); "
            "%d history rows discarded%s",
            city, str(exc), total_rows,
            ", forecast status is failed" if total_rows > 0 else "",
        )
        history = history.iloc[0:0]
        cleaned = None

    # A forecast failure (e.g. method="ml" with no trained artifact) must not
    # take the rating down: G6 degrades to the rolling baseline / cold start.
    forecast_status = "cold_start"
    forecast_error = None
    try:
        forecast = ampacity_forecast.forecast_ampacity(history, method=forecast_method)
        forecast_status = "ok" if forecast is not None else "cold_start"
    except Exception as exc:
        # Capped: the text goes to the orchestrator's --output and the private
        # pipeline_run log only, never to a city_rating column (OD-6).
        forecast_error = f"forecast failed: {exc}"[:FORECAST_ERROR_MAX_CHARS]
        log.warning(
            "forecast_ampacity(method=%r) failed for %s (%s) -- continuing without a forecast",
            forecast_method, city, exc,
        )
        forecast = None
        forecast_status = "failed"
    # WR-02: discarding real history is not "too little history". With no rows
    # to begin with the city really is a cold start; otherwise the forecast
    # ran on nothing because cleaning broke, which is a failed forecast.
    if cleaning_error is not None and total_rows > 0:
        forecast_status = "failed"

    # A forecast whose band has zero width (too few backtest residuals to
    # span both signs) has no discriminating power: G6 would flag any
    # deviation from the last value. Same convention the rolling baseline
    # uses for a zero standard deviation -- don't gate on it.
    forecast_degenerate = (
        forecast is not None and forecast.ci_upper_amps - forecast.ci_lower_amps <= 0
    )
    # A forecast built across too large a gap (stale newest row, or an ml
    # lookback that spans a missing hour) is handled the same way: G6 then uses
    # the rolling baseline or cold start, and the forecast is still reported.
    gap_reason = None
    if forecast is not None and cleaned is not None:
        gap_reason = data_cleaning.forecast_gap_reason(cleaned.report, forecast_method)
    if forecast_degenerate:
        log.info("%s: forecast band has zero width -- not used for G6 this run", city)
        forecast_for_detector = None
    elif gap_reason:
        log.info("%s: forecast not used for G6 this run -- %s", city, gap_reason)
        forecast_for_detector = None
    else:
        forecast_for_detector = forecast

    detector = AnomalyDetector.for_city(city, forecast=forecast_for_detector, history=history)

    result = city_rating.rate_city(
        city, start, end, stations,
        fetch_weather=fetch_weather,
        anomaly_detector=detector,
        archive=archive,
        archive_path=archive_path,
        provider=provider,
    )

    result["pipeline"] = {
        "history_rows": total_rows,
        "usable_history_rows": int(len(history)),
        "forecast_method": forecast_method,
        # OD-3: describes the forecast call, not whether G6 used it
        # (`forecast_used_by_g6` says that), so a forecast withheld by the gap
        # guard or a zero-width band is still "ok".
        "forecast_status": forecast_status,
        # Set when clean_history raised. It reaches the run log only:
        # build_rating_row maps explicit columns, so it never lands in city_rating.
        "cleaning_error": cleaning_error,
        # Set when the forecast call raised (IN-07); same route to the run log.
        "forecast_error": forecast_error,
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
