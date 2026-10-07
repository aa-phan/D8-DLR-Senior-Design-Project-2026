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

import dataclasses
import sys
from typing import Optional

import config
import corridor_discretization
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

    try:
        row, timestamps = shadow.fetch_live_forecast_for_valid_time(
            corridor, valid_time, horizon_minutes=horizon_minutes, lat=lat, lon=lon,
        )
    except shadow.StaleOrMissingDataError as exc:
        # Found live on GitHub Actions (2026-10-06): this call sat outside
        # any try/except, so a forecast-provider timeout (seen hitting BOTH
        # Open-Meteo and, separately, TCEQ across different runs -- not one
        # flaky provider) escaped all the way to forecast_shadow_collect.py's
        # broad `except Exception`, which logs it as a HARD FAILURE (exit
        # code 1) rather than the graceful, logged fallback collect_once's
        # own comment already promises for "a missing anchor/model/forecast
        # source". Without a forecast row there is no data to compute even
        # `raw_forecast`'s ampacity from (both need the same fetched row) --
        # so the fallback here is the project's established total-
        # unavailability discipline (DLRSafetyMonitor's G6 gate: on total
        # failure, report the known-conservative STATIC_RATINGS value, never
        # silently crash or guess), applied per endpoint city and reduced by
        # the same weakest-link principle `forecast_training.
        # corridor_weakest_link` applies elsewhere in this module, just
        # without that function's array machinery, which this scalar case
        # doesn't need.
        city_b = config.CORRIDOR_ENDPOINTS[corridor][1]
        static_fallback_amps = min(
            config.STATIC_RATINGS[city_a], config.STATIC_RATINGS[city_b],
        )
        horizon = pd.Timedelta(minutes=horizon_minutes)
        initialization_time = valid_time - horizon
        availability_time = initialization_time + pd.Timedelta(
            hours=shadow._resolve_publication_lag_hours()
        )
        timestamps = shadow.ShadowTimestamps(
            initialization_time=initialization_time,
            availability_time=availability_time,
            decision_time=pd.Timestamp.now(tz="UTC"),
            valid_time=valid_time,
            horizon_minutes=horizon_minutes,
        )
        prediction = shadow.ShadowPrediction(
            corridor=corridor, method="static_rating_fallback",
            ampacity_amps=static_fallback_amps, timestamps=timestamps,
            fallback_used=True, fallback_reason=str(exc), model_version=None,
            input_provenance={"static_ratings_amps": {
                city_a: config.STATIC_RATINGS[city_a],
                city_b: config.STATIC_RATINGS[city_b],
            }},
        )
        log_path = shadow.ShadowPipeline(corridor, shadow.RawForecastShadowMethod()).log_prediction(prediction)
        print(f"[{corridor}] requested={method_name} actual=static_rating_fallback "
              f"fallback_used=True ampacity={prediction.ampacity_amps:.1f}A "
              f"model_version=None -> logged at {log_path}")
        print(f"  fallback_reason: {prediction.fallback_reason}")
        return prediction

    frame = shadow.validate_and_prepare_shadow_row(row, corridor=corridor)

    # Tracks a substitution made HERE, at the script level, before ShadowPipeline
    # ever sees a method -- distinct from a fallback ShadowPipeline.predict
    # performs internally (a bad/missing weather input). Without this, a missing
    # model artifact silently became a "successful raw_forecast prediction, no
    # fallback" in both the printed line and the persisted log entry, because
    # `primary` was already swapped to RawForecastShadowMethod by the time
    # ShadowPipeline ever ran -- it had no way to know a substitution occurred.
    # Conflating this with "no fallback happened" is exactly the failure mode
    # this project's fallback-reporting discipline exists to prevent elsewhere
    # (see ShadowPipeline.predict's own fallback_used/fallback_reason fields).
    model_missing_reason: Optional[str] = None

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
            model_missing_reason = (
                f"no persisted {method_name!r} model artifact found for {corridor!r} "
                "(demo-script substitution to raw_forecast, not a ShadowPipeline-level "
                "data/provider fallback)"
            )
            print(model_missing_reason, file=sys.stderr)
            primary = shadow.RawForecastShadowMethod()

    pipeline = shadow.ShadowPipeline(corridor, primary)
    prediction = pipeline.predict(frame, timestamps)
    if model_missing_reason is not None:
        # Make the substitution visible in BOTH the printed line and the
        # persisted log entry -- log_prediction below writes this exact
        # object, so fixing only the print would leave the on-disk record
        # just as misleading as before.
        prediction = dataclasses.replace(
            prediction, fallback_used=True, fallback_reason=model_missing_reason,
        )
    log_path = pipeline.log_prediction(prediction)
    print(f"[{corridor}] requested={method_name} actual={prediction.method} "
          f"fallback_used={prediction.fallback_used} ampacity={prediction.ampacity_amps:.1f}A "
          f"model_version={prediction.model_version} -> logged at {log_path}")
    if prediction.fallback_used:
        print(f"  fallback_reason: {prediction.fallback_reason}")
    if prediction.input_provenance:
        print(f"  input_provenance: {prediction.input_provenance}")
    return prediction


def _resolve_next_valid_time(horizon_minutes: int) -> pd.Timestamp:
    """
    Plan 05-02: the SAME 6-hourly-UTC-grid `valid_time` selection
    `run_once` already uses (see that function's own comment for the live
    run that found this constraint) -- duplicated here, rather than
    factored into a shared helper `run_once` itself calls, so `run_once`
    stays byte-for-byte unchanged per this plan's own constraint.
    """
    now = pd.Timestamp.utcnow()
    candidate = (now + pd.Timedelta(hours=12)).floor("6h")
    while candidate <= now + pd.Timedelta(hours=11):
        candidate += pd.Timedelta(hours=6)
    return candidate


def run_once_all_methods(corridor: str, *, horizon_minutes: int = 1440) -> dict:
    """
    Plan 05-02 (D-01/D-02/D-04/D-07): the five-candidate orchestration
    entry point. Resolves ONE `valid_time`/`decision_time` pair, calls
    `shadow.fetch_shared_corridor_inputs` exactly ONCE (D-02), then
    attempts each of the five `shadow.CANDIDATE_METHOD_NAMES` in its own
    try/except (D-07) -- five SEPARATE try/except blocks, never one
    shared block around a loop, so one candidate's real exception can
    never prevent the other four from computing and logging in the same
    cycle. Validates each candidate's own required inputs before
    attempting anything (D-04): a candidate whose inputs are missing for
    this cycle is recorded `status="unavailable"` with a named reason,
    computed independently of every other candidate's own availability.

    Calls `shadow.log_cycle_predictions` once with all five results,
    prints one summary line per candidate, and returns the
    `{name: ShadowPrediction}` mapping.
    """
    cities = config.CORRIDOR_ENDPOINTS[corridor]
    geometry = corridor_discretization.corridor_geometry(corridor)

    valid_time = _resolve_next_valid_time(horizon_minutes)
    decision_time = pd.Timestamp.now(tz="UTC")

    shared = shadow.fetch_shared_corridor_inputs(
        corridor, valid_time=valid_time, decision_time=decision_time,
        horizon_minutes=horizon_minutes,
    )

    horizon = pd.Timedelta(minutes=horizon_minutes)
    initialization_time = valid_time - horizon
    availability_time = initialization_time + pd.Timedelta(
        hours=shadow._resolve_publication_lag_hours()
    )
    timestamps = shadow.ShadowTimestamps(
        initialization_time=initialization_time,
        availability_time=availability_time,
        decision_time=decision_time,
        valid_time=valid_time,
        horizon_minutes=horizon_minutes,
    )

    results: dict = {}

    for candidate_name in shadow.PER_CITY_REDUCED_METHOD_NAMES:
        try:
            missing_forecast = [c for c in cities if shared[c].forecast_frame is None]
            if missing_forecast:
                reasons = "; ".join(f"{c}: {shared[c].forecast_error}" for c in missing_forecast)
                results[candidate_name] = shadow.ShadowPrediction(
                    corridor=corridor, method=candidate_name, ampacity_amps=None,
                    timestamps=timestamps, fallback_used=False, status="unavailable",
                    reason=f"forecast unavailable for {missing_forecast}: {reasons}",
                )
                continue

            # raw_forecast needs only the forecast; ml_wind_corrected/
            # ml_cooling_corrected additionally need both cities' anchor
            # (D-04 -- each candidate's own required-input footprint).
            if candidate_name != "raw_forecast":
                missing_anchor = [c for c in cities if shared[c].anchor is None]
                if missing_anchor:
                    reasons = "; ".join(f"{c}: {shared[c].anchor_error}" for c in missing_anchor)
                    results[candidate_name] = shadow.ShadowPrediction(
                        corridor=corridor, method=candidate_name, ampacity_amps=None,
                        timestamps=timestamps, fallback_used=False, status="unavailable",
                        reason=f"anchor unavailable for {missing_anchor}: {reasons}",
                    )
                    continue

            model_version = None
            if candidate_name == "raw_forecast":
                method = shadow.RawForecastShadowMethod()
                city_frames = {c: shared[c].forecast_frame for c in cities}
            else:
                try:
                    model = shadow.load_correction_model(corridor, candidate_name)
                except FileNotFoundError as exc:
                    results[candidate_name] = shadow.ShadowPrediction(
                        corridor=corridor, method=candidate_name, ampacity_amps=None,
                        timestamps=timestamps, fallback_used=False, status="unavailable",
                        reason=str(exc),
                    )
                    continue
                model_version = shadow.model_version_for(corridor, candidate_name)
                city_frames = {
                    c: shadow._enrich_city_frame_for_correction(
                        shared[c].forecast_frame, anchor=shared[c].anchor,
                        endpoint_city=c, valid_time=valid_time, geometry=geometry,
                    )
                    for c in cities
                }
                if candidate_name == "ml_wind_corrected":
                    method = shadow.WindCorrectionShadowMethod(model, model_version=model_version)
                else:
                    method = shadow.CoolingCorrectionShadowMethod(model, model_version=model_version)

            dlr_amps, per_city_amps, bottleneck_city = shadow._corridor_reduce_per_city(
                method, city_frames, geometry,
            )
            results[candidate_name] = shadow.ShadowPrediction(
                corridor=corridor, method=candidate_name, ampacity_amps=dlr_amps,
                timestamps=timestamps, fallback_used=False, model_version=model_version,
                input_provenance={
                    "per_city_ampacity_amps": per_city_amps,
                    "bottleneck_city": bottleneck_city,
                },
                status="ok",
            )
        except Exception as exc:
            # D-07: a REAL code-level failure escaping this candidate's own
            # validation/compute/reduce path -- caught HERE, by THIS
            # candidate's own try/except, never a shared one around the
            # whole five-candidate loop.
            results[candidate_name] = shadow.ShadowPrediction(
                corridor=corridor, method=candidate_name, ampacity_amps=None,
                timestamps=timestamps, fallback_used=False, status="failed",
                reason=str(exc),
            )

    try:
        results["persistence_24h"] = shadow.Persistence24hShadowMethod().compute(corridor, decision_time)
    except Exception as exc:
        results["persistence_24h"] = shadow.ShadowPrediction(
            corridor=corridor, method="persistence_24h", ampacity_amps=None,
            timestamps=timestamps, fallback_used=False, status="failed", reason=str(exc),
        )

    try:
        results["reference_ml_refit_24h"] = shadow.ReferenceRefit24hShadowMethod().compute(corridor, decision_time)
    except Exception as exc:
        results["reference_ml_refit_24h"] = shadow.ShadowPrediction(
            corridor=corridor, method="reference_ml_refit_24h", ampacity_amps=None,
            timestamps=timestamps, fallback_used=False, status="failed", reason=str(exc),
        )

    shadow.log_cycle_predictions(corridor, results, timestamps)
    for name in shadow.CANDIDATE_METHOD_NAMES:
        r = results[name]
        print(
            f"[{corridor}] {name}: status={r.status} ampacity_amps={r.ampacity_amps} "
            f"reason={r.reason}"
        )
    return results


if __name__ == "__main__":
    corridor = sys.argv[1] if len(sys.argv) > 1 else "AUSTIN_CORPUS_CHRISTI"
    method = sys.argv[2] if len(sys.argv) > 2 else "ml_wind_corrected"
    run_once(corridor, method)
