"""
Demo/integration entry point for the experimental shadow prototype
(pre-confirmation readiness pass, 2026-10-05 -- "start integration now";
extended 2026-10-06 to complete the wind-corrected live path with no
fallback).

Runs the full pipeline end to end against LIVE data: fetch -> validate ->
attach live anchor observation -> predict -> log -> print. Never invoked
by `dlr_pipeline.py` or any other production caller -- run it directly:

    PYTHONPATH=backend .venv/bin/python3 backend/forecast_shadow_demo.py AUSTIN_CORPUS_CHRISTI ml_wind_corrected
    PYTHONPATH=backend .venv/bin/python3 backend/forecast_shadow_demo.py MIDLAND_EL_PASO ml_wind_corrected

Requires a persisted correction model for the requested corridor/method
(see `forecast_shadow_pipeline.save_correction_model`; fit one with
`forecast_correction_models.fit_wind_correction` on the existing
ABLATION-basis cached data under `data/experiment/` -- no network needed
to fit).

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
    # ShadowTimestamps' docstring for why this isn't "now + horizon". The
    # provider's Previous-Runs model only has runs at 6-hourly UTC
    # boundaries (hour % 6 == 0); since horizon_minutes is a 24h (multiple
    # of 6h) offset, valid_time must land on that same 6-hour grid or
    # `fetch_single_run` raises `SingleRunUnavailable` for a run that was
    # never going to exist -- found by actually running this live, not by
    # the synthetic-fixture tests (they never call the real provider).
    now = pd.Timestamp.utcnow()
    candidate = (now + pd.Timedelta(hours=12)).floor("6h")
    while candidate <= now + pd.Timedelta(hours=11):
        candidate += pd.Timedelta(hours=6)
    valid_time = candidate

    row, timestamps = shadow.fetch_live_forecast_for_valid_time(
        corridor, valid_time, horizon_minutes=horizon_minutes, lat=lat, lon=lon,
    )
    frame = shadow.validate_and_prepare_shadow_row(row, corridor=corridor)

    if method_name == "raw_forecast":
        primary = shadow.RawForecastShadowMethod()
    else:
        try:
            model = shadow.load_correction_model(corridor, method_name)
            version = shadow.model_version_for(corridor, method_name)
            if method_name == "ml_wind_corrected":
                # CorridorWindCorrectionMethod (2026-10-06) fetches BOTH
                # endpoint cities' own live forecast + anchor observation
                # and reduces through the same `corridor_weakest_link`
                # training uses -- the corridor-correct form, closing the
                # single-city (`WindCorrectionShadowMethod`) simplification
                # this module used before. A missing/failed anchor source
                # (e.g. no SYNOPTIC_TOKEN) for EITHER city is caught by the
                # pipeline's existing fail-safe fallback machinery with a
                # real `fallback_reason`, same as before.
                primary = shadow.CorridorWindCorrectionMethod(
                    model, corridor=corridor, model_version=version,
                    valid_time=valid_time, decision_time=timestamps.decision_time,
                    horizon_minutes=horizon_minutes,
                )
            else:
                primary = shadow.CoolingCorrectionShadowMethod(model, model_version=version)
        except FileNotFoundError:
            print(f"no persisted {method_name!r} model for {corridor!r} -- demoing raw_forecast only", file=sys.stderr)
            primary = shadow.RawForecastShadowMethod()

    pipeline = shadow.ShadowPipeline(corridor, primary)
    prediction = pipeline.predict(frame, timestamps)
    log_path = pipeline.log_prediction(prediction)
    print(f"[{corridor}] requested={method_name} actual={prediction.method} "
          f"fallback_used={prediction.fallback_used} ampacity={prediction.ampacity_amps:.1f}A "
          f"model_version={prediction.model_version} -> logged at {log_path}")
    if prediction.fallback_used:
        print(f"  fallback_reason: {prediction.fallback_reason}")
    if prediction.input_provenance:
        print(f"  input_provenance: {prediction.input_provenance}")
    return prediction


if __name__ == "__main__":
    corridor = sys.argv[1] if len(sys.argv) > 1 else "AUSTIN_CORPUS_CHRISTI"
    method = sys.argv[2] if len(sys.argv) > 2 else "ml_wind_corrected"
    run_once(corridor, method)
