"""
Corridor Pipeline Orchestrator (Track 1)
==========================================
The missing integration piece: reads archived history for a corridor,
forecasts ahead, builds an anomaly detector from that forecast, then runs
rate_corridor with the detector wired in as G6.
"""

import ampacity_forecast
import historical_archive
from anomaly_detector import AnomalyDetector
import corridor_discretization


def run_corridor_pipeline(
    corridor_name: str,
    start: str,
    end: str,
    stations,
    provider: str = "synoptic",
    archive_path: str = None,
) -> dict:
    """
    Full Track 1 integration for one corridor, one run:
      1. read archived history for this corridor
      2. forecast ahead from that history (None if cold start)
      3. build an anomaly detector from the forecast + history
      4. rate the corridor with that detector wired into G6

    Returns whatever rate_corridor returns.
    """
    history = historical_archive.read_history(path=archive_path, corridor=corridor_name)
    forecast = ampacity_forecast.forecast_ampacity(history)

    detector = AnomalyDetector.for_corridor(
        corridor_name, forecast=forecast, history=history,
    )

    return corridor_discretization.rate_corridor(
        corridor_name, start, end, stations,
        anomaly_detector=detector,
        archive=True,
        archive_path=archive_path,
        provider=provider,
    )