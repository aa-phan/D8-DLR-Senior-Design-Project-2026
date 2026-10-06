"""
DLR Pipeline Entry Point (Track 1)
==================================================
One call runs the whole integrated pipeline for every configured corridor:

    archive history -> forecast -> anomaly detector (G6)
        -> corridor discretization / rate_corridor -> archive append

Lives in its own module (not dlr_pipeline.py) because weather_provider
imports dlr_pipeline, and corridor_discretization imports weather_provider;
importing the corridor stack from dlr_pipeline would be circular.

CLI:
    python dlr_orchestrator.py                      # all corridors, last hour, synoptic
    python dlr_orchestrator.py --corridors MIDLAND_EL_PASO --window-hours 2
    python dlr_orchestrator.py --provider open_meteo --start 2025-07-01 --end 2025-07-02
    python dlr_orchestrator.py --forecast-method ewm --output outputs/run.json
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

import ampacity_forecast
import config
import corridor_discretization
import station_explorer
from corridor_pipeline import run_corridor_pipeline

log = logging.getLogger(__name__)

PROVIDERS = ("synoptic", "open_meteo", "nsrdb")
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _default_window(window_hours: float, end: str = None, start: str = None):
    """Resolve (start, end) ISO strings; end defaults to now (UTC, 5-min floor)."""
    if end is None:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        now = now.replace(minute=now.minute - now.minute % 5)
        end = now.strftime(_TS_FMT)
    if start is None:
        end_ts = pd.Timestamp(end)
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize("UTC")
        start = (end_ts - timedelta(hours=window_hours)).strftime(_TS_FMT)
    return start, end


def _discover_stations(provider: str, token: str = None) -> pd.DataFrame:
    """Station metadata for the station path; grid providers need none."""
    if provider != "synoptic":
        return pd.DataFrame(columns=["stid", "name", "lat", "lon"])
    token = token or os.getenv("SYNOPTIC_TOKEN", "")
    if not token:
        raise EnvironmentError("Set SYNOPTIC_TOKEN (or pass token=) for provider='synoptic'.")
    stations = station_explorer.get_all_stations(token, network_id=None)
    log.info("Discovered %d Texas stations", len(stations))
    return stations


def summarize(result: dict) -> dict:
    """Flatten one run_corridor_pipeline result into a report row."""
    pipe = result.get("pipeline", {})
    fc = pipe.get("forecast")
    static = corridor_discretization.corridor_geometry(result["corridor"]).static_rating
    gates = [a.split(" ")[0] for p in result["points"] for a in p["alerts"]]
    return {
        "corridor": result["corridor"],
        "rating_a": result["rating"],
        "static_rating_a": static,
        "bottleneck_index": result["bottleneck_index"],
        "fallback": result["fallback"],
        "exhausted_points": result["exhausted_points"],
        "fallback_gates": sorted(set(gates)),
        "archived": result["archived"],
        "history_rows": pipe.get("history_rows"),
        "forecast_amps": None if fc is None else fc["amps"],
        "detector_signal": pipe.get("detector_signal"),
    }


def run_dlr_pipeline(
    corridors=None,
    start: str = None,
    end: str = None,
    window_hours: float = 1.0,
    provider: str = "synoptic",
    forecast_method: str = "naive",
    archive: bool = True,
    archive_path: str = None,
    stations: pd.DataFrame = None,
    token: str = None,
) -> dict:
    """
    Run the integrated pipeline for each corridor (default: every key of
    config.CORRIDOR_ENDPOINTS). A failure in one corridor is recorded under
    `errors` and does not stop the others.

    Returns {"start", "end", "provider", "forecast_method", "results": [raw
    run_corridor_pipeline dicts], "summary": [report rows], "errors": {}}.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {PROVIDERS}, got {provider!r}")
    if forecast_method not in ampacity_forecast.FORECAST_METHODS:
        raise ValueError(
            f"forecast_method must be one of {ampacity_forecast.FORECAST_METHODS}, "
            f"got {forecast_method!r}"
        )

    corridors = list(corridors) if corridors else sorted(config.CORRIDOR_ENDPOINTS)
    unknown = [c for c in corridors if c not in config.CORRIDOR_ENDPOINTS]
    if unknown:
        raise KeyError(f"Unknown corridor(s) {unknown}. Valid: {sorted(config.CORRIDOR_ENDPOINTS)}")

    start, end = _default_window(window_hours, end=end, start=start)
    if stations is None:
        stations = _discover_stations(provider, token)

    out = {
        "start": start, "end": end, "provider": provider,
        "forecast_method": forecast_method,
        "results": [], "summary": [], "errors": {},
    }
    for name in corridors:
        try:
            result = run_corridor_pipeline(
                name, start, end, stations,
                provider=provider,
                archive_path=archive_path,
                forecast_method=forecast_method,
                archive=archive,
            )
            out["results"].append(result)
            out["summary"].append(summarize(result))
            log.info("%s: rating=%.0f A fallback=%s archived=%s",
                     name, result["rating"], result["fallback"], result["archived"])
        except Exception as exc:
            log.error("corridor %s failed: %s", name, exc)
            out["errors"][name] = str(exc)
    return out


def _print_report(run: dict) -> None:
    print(f"\nDLR run  {run['start']} -> {run['end']}  provider={run['provider']}  "
          f"forecast={run['forecast_method']}")
    if run["summary"]:
        df = pd.DataFrame(run["summary"])
        cols = ["corridor", "rating_a", "static_rating_a", "bottleneck_index", "fallback",
                "exhausted_points", "archived", "history_rows", "forecast_amps", "detector_signal"]
        print(df[cols].round(1).to_string(index=False))
    for name, msg in run["errors"].items():
        print(f"  ERROR {name}: {msg}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run the integrated DLR corridor pipeline.")
    p.add_argument("--corridors", nargs="*", help="Corridor names (default: all in config)")
    p.add_argument("--start", help="ISO start (default: end - window-hours)")
    p.add_argument("--end", help="ISO end (default: now, UTC)")
    p.add_argument("--window-hours", type=float, default=1.0)
    p.add_argument("--provider", choices=PROVIDERS, default="synoptic")
    p.add_argument("--forecast-method", choices=ampacity_forecast.FORECAST_METHODS, default="naive")
    p.add_argument("--archive-path", help=f"default: {config.HISTORICAL_ARCHIVE_PATH}")
    p.add_argument("--no-archive", action="store_true", help="Do not append to the archive")
    p.add_argument("--output", help="Write the run summary as JSON to this path")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    run = run_dlr_pipeline(
        corridors=args.corridors, start=args.start, end=args.end,
        window_hours=args.window_hours, provider=args.provider,
        forecast_method=args.forecast_method, archive=not args.no_archive,
        archive_path=args.archive_path,
    )
    _print_report(run)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as fh:
            json.dump({k: run[k] for k in ("start", "end", "provider", "forecast_method",
                                           "summary", "errors")}, fh, indent=2, default=str)
        print(f"Summary written to {args.output}")
    return 1 if run["errors"] and not run["summary"] else 0


if __name__ == "__main__":
    sys.exit(main())