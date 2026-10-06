"""
Experimental/shadow forecast-correction prototype (project pivot, 2026-10-05).

**This module is INERT with respect to production.** Nothing in
`dlr_pipeline.py`, `DLRSafetyMonitor.py`, or any other production caller
imports or invokes anything here. It runs only when a script, a notebook,
or a test explicitly calls it -- the same inertness discipline
`forecast_experiment_audit.py`'s `confirm_fresh_run` gate uses for the
FRESH basis. It exists to demonstrate an end-to-end shadow path around the
project's provisional engineering choice (ML wind correction -> existing
IEEE 738), with a common interface so cooling correction or the plain
uncorrected forecast can be substituted without rebuilding the pipeline.

**Provisional choice, not a superiority claim.** `backend/forecast_
experiment_audit.py`'s own block-bootstrap comparisons find neither wind
nor cooling correction statistically distinguishable from the other at
either corridor on development data (see `docs/data-science/decisions/
forecast_correction_followup_audit.md`, "One bounded development
comparison" and "Corrected verdict"). Wind correction is the working
choice here because the comparison is inconclusive and it is the
simpler, easier-to-integrate option -- an engineering tie-break, not a
statistical finding.

**Horizon-independent by construction.** This phase's evidence base is
exclusively 24-hour-ahead; the project's own requirements
(`.planning/workstreams/ml-modeling/REQUIREMENTS.md`) never specify
whether production needs a 60-minute or a 24-hour horizon. Every function
here takes `horizon_minutes` as a required, explicit argument -- never a
default -- so this module never silently resolves that open question.

**Reanalysis-derived, not sensor-validated.** Every number this phase has
produced validates self-consistency against reanalysis-derived truth
(Open-Meteo's Archive API), never an independent sensor measurement. This
module inherits that same limitation; nothing it logs or predicts is
field-validated operational safety.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Protocol

import numpy as np
import pandas as pd

import config
import corridor_discretization
import forecast_correction_models
import open_meteo_forecast_provider
import thermal_model
import wind_vector

logger = logging.getLogger(__name__)

SHADOW_DATA_DIR = os.path.join("data", "shadow")
SHADOW_MODEL_DIR = os.path.join(SHADOW_DATA_DIR, "models")
SHADOW_PREDICTIONS_DIR = os.path.join(SHADOW_DATA_DIR, "predictions")


class StaleOrMissingDataError(Exception):
    """
    Raised by `fetch_live_forecast_for_valid_time` when no model run
    actually covers the requested valid time (network failure, the
    endpoint's own `SingleRunUnavailable`, or a completeness gap), or
    when the retrieved row has a null required field. `ShadowPipeline.
    predict` catches this specifically and routes to the explicit
    fallback method rather than letting a bare `Exception` swallow it
    silently -- matching `DLRSafetyMonitor`'s own "fail safe, not fail
    open" discipline for its G6 gate.
    """


@dataclass(frozen=True)
class ShadowTimestamps:
    """
    The four timestamps a live forecast carries, kept distinct rather
    than conflated -- directly answering Plan 04-01's open question
    about whether live retrieval actually selects a model run that
    covers the requested valid time.

    initialization_time: when the weather model run itself was
        initialized (the run's own `run` parameter to `fetch_single_run`).
    availability_time: when that run's output became queryable via the
        provider API (modeled here as `initialization_time` plus the
        provider's documented publication lag,
        `config.FORECAST_EXPERIMENT_PREVIOUS_RUNS_PUBLICATION_LAG_HOURS`
        if present, else a conservative 6-hour default stated explicitly).
    decision_time: when THIS prediction is actually being made -- must be
        >= availability_time, or the row is rejected as unavailable at
        decision time (the same decision-time-availability discipline
        `forecast_experiment_audit.py`'s leak fixes enforce).
    valid_time: the timestamp the forecast is FOR -- must be
        decision_time + horizon_minutes.
    """

    initialization_time: pd.Timestamp
    availability_time: pd.Timestamp
    decision_time: pd.Timestamp
    valid_time: pd.Timestamp
    horizon_minutes: int

    def as_dict(self) -> dict:
        return {
            "initialization_time": self.initialization_time.isoformat(),
            "availability_time": self.availability_time.isoformat(),
            "decision_time": self.decision_time.isoformat(),
            "valid_time": self.valid_time.isoformat(),
            "horizon_minutes": self.horizon_minutes,
        }


_DEFAULT_PUBLICATION_LAG_HOURS = 6.0


def _resolve_publication_lag_hours() -> float:
    return float(
        getattr(config, "FORECAST_EXPERIMENT_PREVIOUS_RUNS_PUBLICATION_LAG_HOURS", _DEFAULT_PUBLICATION_LAG_HOURS)
    )


def fetch_live_forecast_for_valid_time(
    corridor: str, valid_time, horizon_minutes: int, *, lat: float, lon: float,
) -> tuple[pd.Series, ShadowTimestamps]:
    """
    Retrieve ONE live forecast row whose model run genuinely covers
    `valid_time`, and return it alongside its own `ShadowTimestamps`.

    The model run selected is `valid_time - horizon_minutes` (the run
    whose initialization sits exactly one horizon before the target --
    the run this prediction is ACTUALLY entitled to use if horizon_minutes
    is the real decision-to-valid lead), fetched via `open_meteo_forecast_
    provider.fetch_single_run` under the provider's own pinned
    `FORECAST_MODEL_ID`. This is the concrete answer to whether live
    retrieval selects a run that covers the requested valid time: it is
    constructed to, by always deriving the run from valid_time and
    horizon_minutes rather than always reusing "the latest run" or a
    fixed lookback regardless of how far out valid_time is.

    Raises:
        StaleOrMissingDataError: on any network failure, `SingleRunUnavailable`,
            an empty/null response row, or a decision_time that falls
            before the run's own modeled availability_time (data that
            would not actually have existed yet).
    """
    valid_ts = pd.Timestamp(valid_time, tz="UTC") if pd.Timestamp(valid_time).tzinfo is None else pd.Timestamp(valid_time)
    horizon = pd.Timedelta(minutes=horizon_minutes)
    initialization_time = valid_ts - horizon
    availability_time = initialization_time + pd.Timedelta(hours=_resolve_publication_lag_hours())
    decision_time = pd.Timestamp.now(tz="UTC")

    if decision_time < availability_time:
        raise StaleOrMissingDataError(
            f"fetch_live_forecast_for_valid_time: decision_time {decision_time} "
            f"precedes the selected run's own modeled availability_time "
            f"{availability_time} -- this run would not actually have "
            f"existed yet at decision time"
        )

    try:
        frame = open_meteo_forecast_provider.fetch_single_run(
            lat, lon, initialization_time, forecast_days=1,
        )
    except open_meteo_forecast_provider.SingleRunUnavailable as exc:
        raise StaleOrMissingDataError(
            f"fetch_live_forecast_for_valid_time: run {initialization_time} "
            f"unavailable for corridor {corridor!r}: {exc}"
        ) from exc
    except Exception as exc:  # network/transport failure of any kind
        raise StaleOrMissingDataError(
            f"fetch_live_forecast_for_valid_time: retrieval failed for "
            f"corridor {corridor!r}, run {initialization_time}: {exc}"
        ) from exc

    if frame.empty:
        raise StaleOrMissingDataError(
            f"fetch_live_forecast_for_valid_time: empty response for "
            f"corridor {corridor!r}, run {initialization_time}"
        )

    frame = frame.set_index("datetime_utc") if "datetime_utc" in frame.columns else frame
    try:
        row = frame.loc[frame.index.asof(valid_ts)]
    except (KeyError, ValueError) as exc:
        raise StaleOrMissingDataError(
            f"fetch_live_forecast_for_valid_time: no row near valid_time "
            f"{valid_ts} in run {initialization_time}'s response: {exc}"
        ) from exc

    # `fetch_single_run` returns the provider's own plain column names
    # (air_temp, wind_speed, ...) -- apply the SAME "fcst_" rename
    # `forecast_experiment.py`'s `_stacked_pair_frame` uses when building
    # its own forecast-side columns (lines ~645-651), so this live row is
    # shaped identically to what `validate_and_prepare_shadow_row` and the
    # correction models' feature builders already expect. A real end-to-end
    # run surfaced this mismatch (the raw provider never carried the
    # "fcst_" prefix) -- caught by actually exercising this path, not by
    # the synthetic-fixture unit tests, which always passed pre-prefixed rows.
    row = row.rename({
        "air_temp": "fcst_air_temp",
        "wind_speed": "fcst_wind_speed",
        "wind_direction": "fcst_wind_direction",
        "solar_radiation": "fcst_solar_radiation",
        "relative_humidity": "fcst_relative_humidity",
    })

    if row.isnull().any():
        raise StaleOrMissingDataError(
            f"fetch_live_forecast_for_valid_time: null field(s) in the "
            f"retrieved row for corridor {corridor!r}, valid_time {valid_ts}: "
            f"{row[row.isnull()].index.tolist()}"
        )

    timestamps = ShadowTimestamps(
        initialization_time=initialization_time,
        availability_time=availability_time,
        decision_time=decision_time,
        valid_time=valid_ts,
        horizon_minutes=horizon_minutes,
    )
    return row, timestamps


_REQUIRED_SHADOW_COLUMNS = ("fcst_air_temp", "fcst_wind_speed", "fcst_wind_direction", "fcst_solar_radiation")


def validate_and_prepare_shadow_row(row: pd.Series, *, corridor: str) -> pd.DataFrame:
    """
    Input validation for one retrieved row: required columns present and
    non-null, units sane (temperature in a physically plausible range,
    wind speed non-negative, solar radiation non-negative), and the
    corridor's conductor metadata resolvable via `corridor_discretization.
    corridor_geometry` (raises `KeyError` naming the corridor if not --
    never silently proceeds without conductor metadata).

    Converts wind speed/direction to u/v via `wind_vector.to_uv` and
    attaches both representations, since `forecast_correction_models`'
    own feature builders consume u/v while `thermal_model.ieee738_
    ampacity`'s wind-correction path consumes speed/direction.

    Returns a one-row DataFrame shaped for `forecast_correction_models.
    predict_wind_correction` (needs `fcst_wind_speed`, `fcst_wind_
    direction`, `fcst_air_temp`, `fcst_solar_radiation`, and whatever
    anchor/hour columns `_wind_feature_frame` requires -- callers should
    pass the real `anchor_*` columns through from the retrieved row
    where available).

    Raises:
        ValueError: naming the missing/invalid field(s).
        KeyError: if `corridor` is not a resolvable corridor.
    """
    geometry = corridor_discretization.corridor_geometry(corridor)  # raises KeyError if unknown

    missing = [c for c in _REQUIRED_SHADOW_COLUMNS if c not in row.index or pd.isnull(row[c])]
    if missing:
        raise ValueError(f"validate_and_prepare_shadow_row: missing/null required field(s) {missing}")

    air_temp = float(row["fcst_air_temp"])
    wind_speed = float(row["fcst_wind_speed"])
    solar = float(row["fcst_solar_radiation"])
    if not (-60.0 <= air_temp <= 60.0):
        raise ValueError(f"validate_and_prepare_shadow_row: fcst_air_temp {air_temp} outside [-60, 60] C")
    if wind_speed < 0.0:
        raise ValueError(f"validate_and_prepare_shadow_row: fcst_wind_speed {wind_speed} is negative")
    if solar < 0.0:
        raise ValueError(f"validate_and_prepare_shadow_row: fcst_solar_radiation {solar} is negative")

    u, v = wind_vector.to_uv(np.array([wind_speed]), np.array([float(row["fcst_wind_direction"])]))

    frame = pd.DataFrame([row])
    frame["fcst_wind_u"] = u
    frame["fcst_wind_v"] = v
    frame.attrs["geometry"] = geometry
    return frame


@dataclass(frozen=True)
class ShadowPrediction:
    """One method's output: the corrected ampacity, the method name, and whether a fallback was used."""

    corridor: str
    method: str
    ampacity_amps: float
    timestamps: ShadowTimestamps
    fallback_used: bool
    fallback_reason: Optional[str] = None


class CorrectionMethod(Protocol):
    """
    Common interface every correction method implements, so `ShadowPipeline`
    can substitute wind correction, cooling correction, or the plain
    uncorrected forecast without any change to retrieval, validation,
    logging, or fallback handling.
    """

    name: str

    def predict(self, frame: pd.DataFrame, geometry) -> float:
        """Return a single corrected ampacity value in Amperes for `frame`'s one row."""
        ...


class WindCorrectionShadowMethod:
    """
    The prototype's working choice. Wraps a persisted `forecast_correction_
    models.WindCorrectionModel` and the same `predict_wind_correction` ->
    `perpendicular_wind` -> `ieee738_ampacity` chain `forecast_experiment.
    _wind_corrected_ampacity` already uses for the audit's own ABLATION-basis
    scoring -- read-only reuse of that frozen wiring, not a reimplementation.
    """

    name = "ml_wind_corrected"

    def __init__(self, model: "forecast_correction_models.WindCorrectionModel"):
        self.model = model

    def predict(self, frame: pd.DataFrame, geometry) -> float:
        prediction = forecast_correction_models.predict_wind_correction(self.model, frame)
        perp = thermal_model.perpendicular_wind(prediction.speed, prediction.direction, geometry.bearing_deg)
        ampacity = thermal_model.ieee738_ampacity(
            frame["fcst_air_temp"].to_numpy(dtype=float), perp,
            frame["fcst_solar_radiation"].to_numpy(dtype=float), geometry.conductor,
        )
        return float(np.asarray(ampacity)[0])


class CoolingCorrectionShadowMethod:
    """
    The main challenger, lightly implemented to demonstrate the interface's
    substitutability -- not the prototype's working choice. Wraps a
    persisted `forecast_correction_models.CoolingCorrectionModel`.
    """

    name = "ml_cooling_corrected"

    def __init__(self, model: "forecast_correction_models.CoolingCorrectionModel"):
        self.model = model

    def predict(self, frame: pd.DataFrame, geometry) -> float:
        prediction = forecast_correction_models.predict_cooling_correction(self.model, frame)
        ampacity = forecast_correction_models.apply_cooling_correction(frame, prediction.q_conv, geometry)
        return float(np.asarray(ampacity)[0])


class RawForecastShadowMethod:
    """
    The uncorrected baseline: the forecast's own weather run straight
    through IEEE 738, no correction model, no persistence needed. Also
    the pipeline's own fallback target when a correction method's
    prediction cannot be trusted (stale/missing live data, or a failed
    model load).
    """

    name = "raw_forecast"

    def predict(self, frame: pd.DataFrame, geometry) -> float:
        perp = thermal_model.perpendicular_wind(
            frame["fcst_wind_speed"].to_numpy(dtype=float),
            frame["fcst_wind_direction"].to_numpy(dtype=float),
            geometry.bearing_deg,
        )
        ampacity = thermal_model.ieee738_ampacity(
            frame["fcst_air_temp"].to_numpy(dtype=float), perp,
            frame["fcst_solar_radiation"].to_numpy(dtype=float), geometry.conductor,
        )
        return float(np.asarray(ampacity)[0])


def _model_path_for(corridor: str, method_name: str) -> str:
    return os.path.join(SHADOW_MODEL_DIR, f"{method_name}_{corridor}.joblib")


def save_correction_model(model, corridor: str, method_name: str) -> str:
    """Persist a fitted correction model via joblib, mirroring `ampacity_forecast._load_corridor_model`'s own convention."""
    import joblib  # lazy -- keeps this module importable without sklearn/joblib installed

    os.makedirs(SHADOW_MODEL_DIR, exist_ok=True)
    path = _model_path_for(corridor, method_name)
    joblib.dump(model, path)
    return path


def load_correction_model(corridor: str, method_name: str):
    """
    Load a persisted correction model.

    Raises:
        FileNotFoundError: naming the corridor, method, expected path, and
            that no training command exists yet for this prototype module
            (fit directly via `forecast_correction_models.fit_wind_correction`/
            `fit_cooling_correction` and call `save_correction_model`).
    """
    path = _model_path_for(corridor, method_name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"load_correction_model: no persisted {method_name!r} model for "
            f"corridor {corridor!r} at {path!r}. Fit one with "
            f"forecast_correction_models.fit_wind_correction/fit_cooling_correction "
            f"and persist it with forecast_shadow_pipeline.save_correction_model."
        )
    import joblib  # lazy

    return joblib.load(path)


class UnsupportedHorizonError(ValueError):
    """
    Raised by `ShadowPipeline.predict` when `timestamps.horizon_minutes`
    is not one this phase's evidence base has actually evaluated for the
    requested method. This phase's entire evidence base
    (`docs/data-science/decisions/forecast_correction_followup_audit.md`)
    is exclusively the 24-hour (1440-minute) horizon -- no number in that
    document, and no fitted model this module loads, has ever been
    checked against a 60-minute or any other horizon. A model/horizon
    combination outside `EVALUATED_HORIZONS_MINUTES` is a REJECTION, not a
    fallback-worthy runtime failure: it is checked and raised BEFORE the
    primary-method try/except below, so it can never be silently absorbed
    into a raw_forecast fallback the caller might mistake for "the
    correction model ran and this is its answer."
    """


# This phase's entire evidence base is 24-hour-ahead only (see this
# module's own docstring, "Horizon-independent by construction"). Every
# `CorrectionMethod` this module ships is therefore only evaluated at
# 1440 minutes -- stated here as one shared tuple, not per-method, because
# there is currently exactly one evaluated horizon for the whole module,
# not because future methods are assumed to share it.
EVALUATED_HORIZONS_MINUTES: tuple[int, ...] = (1440,)


class ShadowPipeline:
    """
    Ties retrieval -> validation -> correction -> logging -> fallback
    together behind one call. Never invoked by production code.
    """

    def __init__(self, corridor: str, primary_method: CorrectionMethod, *, fallback_method: Optional[CorrectionMethod] = None):
        self.corridor = corridor
        self.primary_method = primary_method
        self.fallback_method = fallback_method or RawForecastShadowMethod()
        self.geometry = corridor_discretization.corridor_geometry(corridor)

    def predict(self, frame: pd.DataFrame, timestamps: ShadowTimestamps) -> ShadowPrediction:
        """
        Run the primary method; on ANY exception (a stale/missing-data
        signal already raised by the caller before this point, or a
        model-prediction failure here), fall back to `self.fallback_method`
        and report `fallback_used=True` with the reason -- never silently
        swallowed, matching `DLRSafetyMonitor`'s fail-safe-not-fail-open
        discipline for its own G6 gate.

        Raises:
            UnsupportedHorizonError: if `timestamps.horizon_minutes` is not
                in `EVALUATED_HORIZONS_MINUTES` -- checked first, before
                the fallback machinery below, so an unsupported horizon is
                a hard rejection rather than something that could resolve
                to a fallback prediction.
        """
        if timestamps.horizon_minutes not in EVALUATED_HORIZONS_MINUTES:
            raise UnsupportedHorizonError(
                f"ShadowPipeline.predict: horizon_minutes={timestamps.horizon_minutes} "
                f"has no evaluated evidence behind it (evaluated: "
                f"{EVALUATED_HORIZONS_MINUTES}) -- this phase's evidence base is "
                f"24-hour-ahead only; do not call predict at an unevaluated horizon"
            )
        try:
            amps = self.primary_method.predict(frame, self.geometry)
            return ShadowPrediction(
                corridor=self.corridor, method=self.primary_method.name,
                ampacity_amps=amps, timestamps=timestamps, fallback_used=False,
            )
        except Exception as exc:
            logger.warning(
                "ShadowPipeline.predict: primary method %r failed (%s) -- falling back to %r",
                self.primary_method.name, exc, self.fallback_method.name,
            )
            amps = self.fallback_method.predict(frame, self.geometry)
            return ShadowPrediction(
                corridor=self.corridor, method=self.fallback_method.name,
                ampacity_amps=amps, timestamps=timestamps, fallback_used=True,
                fallback_reason=str(exc),
            )

    def log_prediction(self, prediction: ShadowPrediction) -> str:
        """
        Append one prediction record as a JSON line under
        `data/shadow/predictions/<corridor>.jsonl` (git-ignored, same
        generated-evidence convention as every other report this phase
        has produced under `data/`). Returns the path written to.
        """
        os.makedirs(SHADOW_PREDICTIONS_DIR, exist_ok=True)
        path = os.path.join(SHADOW_PREDICTIONS_DIR, f"{self.corridor}.jsonl")
        record = {
            "corridor": prediction.corridor,
            "method": prediction.method,
            "ampacity_amps": prediction.ampacity_amps,
            "fallback_used": prediction.fallback_used,
            "fallback_reason": prediction.fallback_reason,
            "logged_at": datetime.now(timezone.utc).isoformat(),
            **prediction.timestamps.as_dict(),
            "basis_caveat": (
                "Reanalysis-derived development comparison; this live prediction's "
                "quality is not independently sensor-validated."
            ),
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return path
