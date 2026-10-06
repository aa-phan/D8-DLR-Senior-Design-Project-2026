"""
Demo/integration entry point for the experimental shadow prototype
(pre-confirmation readiness pass, 2026-10-05 -- "start integration now").

Runs the full pipeline end to end against LIVE data: fetch -> validate ->
predict -> log -> print. Never invoked by `dlr_pipeline.py` or any other
production caller -- run it directly:

    PYTHONPATH=backend .venv/bin/python3 backend/forecast_shadow_demo.py

Requires a persisted correction model for the requested corridor/method
(see `forecast_shadow_pipeline.save_correction_model`; fit one with
`forecast_experiment.fit_fitted_arms` on the existing ABLATION-basis
cached data under `data/experiment/` -- no network needed to fit).

This script demonstrates PIPELINE PLUMBING working today. It does NOT
freeze the model artifact, preprocessing, or calibration -- those stay
open to revision until the 2026-11-01 freeze point per the project-pivot
protocol in `docs/data-science/decisions/forecast_correction_followup_audit.md`.
"""
from __future__ import annotations

import sys

import config
import forecast_shadow_pipeline as shadow
import pandas as pd


def run_once(corridor: str, method_name: str = "ml_wind_corrected", *, horizon_minutes: int = 1440) -> shadow.ShadowPrediction:
    city_a = config.CORRIDOR_ENDPOINTS[corridor][0]
    lat, lon = config.CITY_COORDINATES[city_a]

    # Request a valid_time far enough out that the model run it needs is
    # already past its own publication-lag availability window -- see
    # ShadowTimestamps' docstring for why this isn't "now + horizon".
    valid_time = pd.Timestamp.utcnow().floor("h") + pd.Timedelta(hours=12)

    row, timestamps = shadow.fetch_live_forecast_for_valid_time(
        corridor, valid_time, horizon_minutes=horizon_minutes, lat=lat, lon=lon,
    )
    frame = shadow.validate_and_prepare_shadow_row(row, corridor=corridor)

    if method_name == "raw_forecast":
        primary = shadow.RawForecastShadowMethod()
    else:
        try:
            model = shadow.load_correction_model(corridor, method_name)
            primary = (
                shadow.WindCorrectionShadowMethod(model) if method_name == "ml_wind_corrected"
                else shadow.CoolingCorrectionShadowMethod(model)
            )
        except FileNotFoundError:
            print(f"no persisted {method_name!r} model for {corridor!r} -- demoing raw_forecast only", file=sys.stderr)
            primary = shadow.RawForecastShadowMethod()

    pipeline = shadow.ShadowPipeline(corridor, primary)
    prediction = pipeline.predict(frame, timestamps)
    log_path = pipeline.log_prediction(prediction)
    print(f"[{corridor}] method={prediction.method} fallback_used={prediction.fallback_used} "
          f"ampacity={prediction.ampacity_amps:.1f}A -> logged at {log_path}")
    if prediction.fallback_used:
        print(f"  fallback_reason: {prediction.fallback_reason}")
    return prediction


if __name__ == "__main__":
    corridor = sys.argv[1] if len(sys.argv) > 1 else "AUSTIN_CORPUS_CHRISTI"
    method = sys.argv[2] if len(sys.argv) > 2 else "ml_wind_corrected"
    run_once(corridor, method)
