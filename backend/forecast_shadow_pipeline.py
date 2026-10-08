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
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Protocol

import numpy as np
import pandas as pd
from dotenv import load_dotenv

import ampacity_forecast
import config
import corridor_discretization
import forecast_correction_models
import forecast_training
import open_meteo_forecast_provider
import thermal_model
import weather_provider
import wind_vector

# Every other credential read in this repo (`dlr_pipeline.py`, `smoke_test.py`,
# `station_explorer.py`) is a bare `os.getenv("SYNOPTIC_TOKEN")` with a
# shell-export instruction in a comment -- there is no existing `.env`-loading
# convention to extend. This call is new and scoped deliberately to this
# shadow-pipeline module alone, never to `config.py` (whose own docstring
# promises import has no side effects -- a dotenv load would break that
# contract for every other caller of `config`). `load_dotenv()`'s default
# behavior never overrides a variable already present in the environment, so
# a shell-exported `SYNOPTIC_TOKEN` still takes precedence over a `.env` file
# if both exist. This module itself never reads the token's value -- only
# `dlr_pipeline.fetch_timeseries` (via `weather_provider`) does, and it reads
# it from `os.environ`, same as before; this just ensures `.env`'s contents
# have reached `os.environ` by the time that call happens.
load_dotenv()

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
    decision_time=None,
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

    `decision_time` (Plan 05-02, D-02): keyword-only, defaults to `None`,
    in which case `decision_time` is computed internally exactly as
    before (`pd.Timestamp.now(tz="UTC")`) -- byte-identical behavior for
    every existing caller. When provided, that exact value is used
    instead of calling `pd.Timestamp.now()`, so one shared `decision_time`
    can be pinned across both endpoint cities' fetches in the same cycle
    (`fetch_shared_corridor_inputs`) rather than each city's fetch
    independently computing its own microseconds-apart "now."

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
    decision_time = pd.Timestamp.now(tz="UTC") if decision_time is None else decision_time

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


_ANCHOR_LOOKBACK_HOURS_DEFAULT = 6.0


def fetch_live_anchor_observation(
    city: str, decision_time, *, lookback_hours: float = _ANCHOR_LOOKBACK_HOURS_DEFAULT,
) -> pd.Series:
    """
    Fetch the most recent REAL (near-real-time station) observation for
    `city` at or before `decision_time`, through
    `weather_provider.fetch_weather`'s REAL ratified composition --
    `provider="tceq"` (the project's primary for wind/temp/RH, WX-01),
    which `fetch_weather`'s own `fallback=True` default automatically
    retries against Synoptic (`FALLBACK_PROVIDER`) on a `ValueError`-shaped
    primary failure -- never Synoptic requested directly. (An earlier
    version of this function called `provider="synoptic"` directly,
    bypassing the ratified primary entirely; fixed 2026-10-06.)

    This is the live equivalent of `forecast_experiment.anchored_pair_
    frame`'s anchor group (the last real observation a forecaster would
    have had at the anchor time) -- except that frame's anchor is itself
    built from the Open-Meteo Archive API reanalysis, because at TRAINING
    time the anchor moment was already historical and the archive had
    settled. At LIVE decision time the anchor moment is effectively "now",
    where only a station observation actually exists yet. **Matching
    PIPELINE_SCHEMA units/columns does not establish that the live-station
    anchor and the archive-derived training anchor behave statistically
    equivalently** -- that empirical question is open and explicitly not
    answered here (see module docstring).

    **The ASOS-supplement asymmetry, by design, not an oversight.**
    `weather_provider._supplement_with_asos` is wired only into the
    Synoptic branch of `_fetch_station` (its own module docstring: "mixing
    it into the TCEQ branch is not in WX-01's scope") -- so a TCEQ-primary
    success here never gets ASOS's finer-grained supplement, while a
    Synoptic fallback does (inherited automatically through
    `_attempt_fallback` -> `_fetch_station`, same as every other
    `fetch_weather` caller). For this function's single
    most-recent-reading lookup (not a bulk historical fetch), ASOS's
    sub-hourly resolution is not required to answer "what was the last
    valid hourly reading" -- TCEQ's own hourly cadence is sufficient when
    it succeeds.

    **TCEQ's own freshness characteristic, confirmed empirically this
    session:** `daily_summary.pl` returns a full 24-local-hour skeleton for
    the current day with trailing NaN rows for hours not yet reported --
    NOT a provider error, just an honest "not reported yet." The existing
    at-or-before-decision_time filter plus the latest-row null check below
    already treats an unreported trailing hour exactly like Synoptic's own
    null-wind-field case (confirmed live: Corpus Christi's `KCRP` station,
    2026-10-06) -- same established fallback policy, reused rather than
    special-cased per provider.

    Returns a one-row Series with `anchor_wind_speed`, `anchor_wind_
    direction`, `anchor_observation_time` (the observation's own
    timestamp -- may be up to `lookback_hours` before `decision_time` if
    the station's most recent report is not instantaneous), `anchor_
    source` (the ACTUAL provider that supplied the row -- "tceq" or
    "synoptic", read from the frame's own `wind_source` provenance column,
    never just "whichever was requested"), and `anchor_station` (the CAMS
    ID when `anchor_source="tceq"`, the Synoptic station ID when a
    fallback fired).

    Raises:
        StaleOrMissingDataError: no known CAMS site for `city`
            (`config.TCEQ_STATIONS`), the fetch itself fails (including
            both primary and fallback exhausted), or no observation row
            exists at/before `decision_time` within the lookback window,
            or the latest such row has a null required wind field.
    """
    cams_id = config.TCEQ_STATIONS.get(city)
    if cams_id is None:
        raise StaleOrMissingDataError(
            f"fetch_live_anchor_observation: no known TCEQ CAMS site for city {city!r}"
        )
    decision_time = pd.Timestamp(decision_time)
    if decision_time.tzinfo is None:
        decision_time = decision_time.tz_localize("UTC")
    window_start = (decision_time - pd.Timedelta(hours=lookback_hours)).isoformat()
    window_end = decision_time.isoformat()

    def _latest_usable_row(location, provider, label):
        """
        One fetch-and-validate attempt. Returns `(row, None)` if the
        latest at-or-before-decision_time row has non-null required wind
        fields, else `(None, reason)` where `reason` names exactly which
        of the four distinct failure shapes occurred -- a MECHANICALLY
        SUCCESSFUL but UNUSABLE response (e.g. TCEQ's own trailing
        not-yet-reported hour, confirmed live this session:
        `daily_summary.pl` returns a full 24-local-hour skeleton with NaN
        for hours not yet published) is distinct from a raised exception,
        an empty response, and a response with no row in the lookback
        window -- the caller needs to know WHICH shape occurred per
        attempt to build a precise combined failure message, not just
        that *an* attempt failed.
        """
        try:
            frame = weather_provider.fetch_weather(location, window_start, window_end, provider=provider)
        except Exception as exc:
            reason = f"fetch raised ({exc})"
            logger.info("%s: %s -- trying next source if any", label, reason)
            return None, reason
        if frame.empty:
            reason = "empty response"
            logger.info("%s: %s -- trying next source if any", label, reason)
            return None, reason
        frame = frame.reset_index()
        frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], utc=True)
        frame = frame[frame["datetime_utc"] <= decision_time].sort_values("datetime_utc")
        if frame.empty:
            reason = f"no row at/before decision_time {decision_time}"
            logger.info("%s: %s -- trying next source if any", label, reason)
            return None, reason
        row = frame.iloc[-1]
        if pd.isnull(row.get("wind_speed")) or pd.isnull(row.get("wind_direction")):
            reason = f"latest row at {row['datetime_utc']} has a null wind field"
            logger.info("%s: %s -- trying next source if any", label, reason)
            return None, reason
        return row, None

    # Primary: TCEQ. `fetch_weather`'s own `fallback=True` already retries
    # Synoptic automatically on a RAISED exception or an empty response --
    # but NOT on a mechanically successful response whose specific latest
    # row is unusable (TCEQ's trailing-NaN-hour case), since weather_
    # provider has no notion of "the one row this caller cares about."
    # That gap is this function's job to close, by explicitly trying the
    # same Synoptic fallback target a second time, at the row level.
    latest, tceq_reason = _latest_usable_row(
        [cams_id], "tceq", f"fetch_live_anchor_observation({city!r}, tceq CAMS {cams_id!r})"
    )
    actual_source = "tceq"
    actual_station = cams_id
    synoptic_station = config.SYNOPTIC_FALLBACK_STATIONS.get(city)
    synoptic_reason = None

    if latest is None:
        if synoptic_station is not None:
            latest, synoptic_reason = _latest_usable_row(
                [synoptic_station], "synoptic",
                f"fetch_live_anchor_observation({city!r}, explicit Synoptic retry, station {synoptic_station!r})",
            )
            actual_source = "synoptic"
            actual_station = synoptic_station
        else:
            synoptic_reason = "no Synoptic fallback station configured for this city"

    if latest is None:
        # Precise, per-provider attribution -- not a single message that
        # could describe any of several different failure combinations
        # ambiguously. Each half names its own provider and its own one
        # of the four distinct failure shapes `_latest_usable_row` can
        # report (raised, empty, no row in window, null wind field).
        raise StaleOrMissingDataError(
            f"fetch_live_anchor_observation: no usable wind observation for {city!r} "
            f"at/before decision_time {decision_time} within the {lookback_hours}h lookback "
            f"window -- TCEQ CAMS {cams_id!r}: {tceq_reason}; "
            f"Synoptic {synoptic_station!r}: {synoptic_reason}"
        )

    # `wind_source` (units_def.PIPELINE_SCHEMA provenance column, set by
    # `weather_provider.attach_provenance`) independently confirms which
    # provider actually supplied the row -- cross-checked against
    # `actual_source` (which attempt succeeded) rather than trusted alone,
    # since `attach_provenance` is applied inside `_fetch_station` either way.
    provenance_source = latest.get("wind_source")
    if pd.notna(provenance_source) and provenance_source != actual_source:
        logger.warning(
            "fetch_live_anchor_observation(%r): attempt-tracked source %r disagrees with "
            "wind_source provenance %r -- trusting provenance",
            city, actual_source, provenance_source,
        )
        actual_source = provenance_source

    # Plan 05-02 (D-01/D-06): `ml_cooling_corrected`'s feature build needs
    # `anchor_air_temp` alongside the wind fields -- read from the SAME
    # already-fetched `latest` row, no new network call. A null/missing
    # `air_temp` on an otherwise-usable (valid wind) row is passed through
    # as NaN rather than validated here a second time; the downstream
    # cooling-correction feature build already handles a null feature.
    raw_air_temp = latest.get("air_temp")
    anchor_air_temp = float(raw_air_temp) if pd.notna(raw_air_temp) else float("nan")

    return pd.Series({
        "anchor_wind_speed": float(latest["wind_speed"]),
        "anchor_wind_direction": float(latest["wind_direction"]),
        "anchor_air_temp": anchor_air_temp,
        "anchor_observation_time": latest["datetime_utc"],
        "anchor_source": actual_source if pd.notna(actual_source) else "unknown",
        "anchor_station": actual_station,
    })


def attach_wind_correction_inputs(
    frame: pd.DataFrame, *, endpoint_city: str, valid_time, decision_time,
) -> pd.DataFrame:
    """
    Enrich a `validate_and_prepare_shadow_row`-prepared frame with the
    live anchor observation and the remaining columns
    `forecast_correction_models._wind_feature_frame` requires:
    `anchor_wind_speed`/`anchor_wind_direction` (from
    `fetch_live_anchor_observation`), `datetime_utc` (set to `valid_time`,
    for the hour-of-day encoding -- matches training's convention of
    `datetime_utc` = the valid time T), and `endpoint_city` (for the
    pooled model's endpoint indicator / the per_city model's grouping).

    **Single-city by design here.** This function attaches ONE city's
    (`endpoint_city`) live anchor observation -- it is the per-city
    building block `CorridorWindCorrectionMethod` (2026-10-06) calls
    once per endpoint city before reducing both cities' resulting
    AMPACITIES through `forecast_training.corridor_weakest_link`, the
    same two-stage per-city-then-minimum reduction
    `forecast_experiment.corridor_anchored_pair_frame` uses for training.
    Callers wanting the corridor-correct (both-cities, weakest-link)
    prediction should use `CorridorWindCorrectionMethod`, not call this
    function directly expecting a corridor-level answer.

    **Archive-derived training anchor vs. live-station runtime anchor --
    a named data-source change, not assumed interchangeable.** Training's
    own anchor (`forecast_experiment.anchored_pair_frame`) comes from
    Open-Meteo's Archive API, settled and historical by the time training
    ran. This function's anchor comes from a live Synoptic station
    report instead, because at genuine live decision time the anchor
    moment is "now," where only a station observation exists yet -- the
    Archive API's own ~1-day publication lag (see `forecast_experiment.
    _resolve_window_end`) cannot serve a live "most recent observation"
    request. Both paths ultimately populate the SAME `anchor_wind_speed`/
    `anchor_wind_direction` columns in the SAME units (`PIPELINE_SCHEMA`'s
    m/s and degrees, enforced by `weather_provider.fetch_weather`
    regardless of provider), so the feature CONTRACT matches. What could
    NOT be checked empirically in this pass: Synoptic's station path is
    documented (`weather_provider.py`, "standalone 1940-present
    historical-backfill source Synoptic cannot serve") as a recent-window
    source, not a multi-year historical one, so there is no overlapping
    date on which to directly compare an archive-derived anchor value
    against a live-station anchor value for the SAME historical moment
    this phase's training window covers (2024-01-20 through 2026-03-16).
    This is a stated limitation, not an assumption of interchangeability
    -- a sensor-grounded validation (see the data-team handoff request)
    would be the way to actually check this empirically.

    Raises:
        StaleOrMissingDataError: propagated from
            `fetch_live_anchor_observation` if no live anchor observation
            can be retrieved.
    """
    valid_time = pd.Timestamp(valid_time)
    if valid_time.tzinfo is None:
        valid_time = valid_time.tz_localize("UTC")

    anchor = fetch_live_anchor_observation(endpoint_city, decision_time)

    enriched = frame.copy()
    enriched["anchor_wind_speed"] = anchor["anchor_wind_speed"]
    enriched["anchor_wind_direction"] = anchor["anchor_wind_direction"]
    enriched["datetime_utc"] = valid_time
    enriched["endpoint_city"] = endpoint_city
    enriched.attrs["geometry"] = frame.attrs.get("geometry")
    enriched.attrs["anchor_observation_time"] = anchor["anchor_observation_time"].isoformat()
    enriched.attrs["anchor_source"] = anchor["anchor_source"]
    enriched.attrs["anchor_station"] = anchor["anchor_station"]
    return enriched


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
class SharedCityFetchResult:
    """
    Plan 05-02 (D-02): one endpoint city's own forecast-fetch outcome and
    anchor-fetch outcome, captured INDEPENDENTLY -- a failed anchor fetch
    for this city does not prevent its forecast fetch from being recorded
    (and vice versa), and this city's own pair of outcomes never affects
    the other city's. `forecast_frame`/`anchor` are `None` exactly when
    the corresponding `*_error` is set (a successful fetch always pairs
    with a `None` error, a failed one always pairs with a `None` result).
    """

    city: str
    forecast_frame: Optional[pd.DataFrame]
    forecast_error: Optional[str]
    anchor: Optional[pd.Series]
    anchor_error: Optional[str]


def fetch_shared_corridor_inputs(
    corridor: str, *, valid_time, decision_time, horizon_minutes: int,
) -> dict:
    """
    Plan 05-02 (D-02): fetch each endpoint city's live forecast row and
    live anchor observation EXACTLY ONCE per cycle -- at most two forecast
    fetches and two anchor fetches total for a two-city corridor -- so
    every candidate computed from this cycle's result shares the exact
    same forecast row, the exact same anchor observation, and the exact
    same `decision_time`, rather than each candidate (or each city) make
    its own independent network call.

    Each city's forecast attempt and anchor attempt are isolated in their
    own try/except; a failure in one never prevents the other three
    attempts (this city's other input, or either of the other city's
    inputs) from being made. A candidate that discovers one of its
    required inputs is `None` on the returned result reports itself
    `status="unavailable"` (D-04) -- this function itself never raises
    for a single city's fetch failure.

    Returns a `{city: SharedCityFetchResult}` mapping, one entry per city
    in `config.CORRIDOR_ENDPOINTS[corridor]`.
    """
    results: dict = {}
    for city in config.CORRIDOR_ENDPOINTS[corridor]:
        lat, lon = config.CITY_COORDINATES[city]

        forecast_frame: Optional[pd.DataFrame] = None
        forecast_error: Optional[str] = None
        try:
            row, _ = fetch_live_forecast_for_valid_time(
                corridor, valid_time, horizon_minutes=horizon_minutes,
                lat=lat, lon=lon, decision_time=decision_time,
            )
            forecast_frame = validate_and_prepare_shadow_row(row, corridor=corridor)
        except (StaleOrMissingDataError, ValueError, KeyError) as exc:
            forecast_error = str(exc)

        anchor: Optional[pd.Series] = None
        anchor_error: Optional[str] = None
        try:
            anchor = fetch_live_anchor_observation(city, decision_time)
        except StaleOrMissingDataError as exc:
            anchor_error = str(exc)

        results[city] = SharedCityFetchResult(
            city=city, forecast_frame=forecast_frame, forecast_error=forecast_error,
            anchor=anchor, anchor_error=anchor_error,
        )
    return results


def _enrich_city_frame_for_correction(
    forecast_frame: pd.DataFrame, *, anchor: pd.Series, endpoint_city: str, valid_time, geometry,
) -> pd.DataFrame:
    """
    Plan 05-02 (D-01/D-06): a PURE, no-fetch enrichment -- given an
    already-validated forecast frame (from `fetch_shared_corridor_
    inputs`'s own result, never re-fetched here) and an already-fetched
    anchor `Series`, returns a frame carrying every column
    `forecast_correction_models._wind_feature_frame` AND
    `_cooling_feature_frame` need: `anchor_wind_speed`/`anchor_wind_
    direction`/`anchor_air_temp`, `datetime_utc=valid_time`,
    `endpoint_city`, and the two perpendicular-wind columns
    (`fcst_perp_wind_ms`/`anchor_perp_wind_ms`) via the SAME
    `thermal_model.perpendicular_wind` function `forecast_experiment.
    _add_correction_columns` uses -- never a second wind-projection
    implementation.

    Deliberately duplicates `attach_wind_correction_inputs`'s field-
    setting shape rather than calling that function, which fetches its
    own anchor internally -- this function must never fetch, so the
    orchestrator's one shared fetch per cycle (D-02) is never silently
    doubled.
    """
    valid_ts = pd.Timestamp(valid_time)
    if valid_ts.tzinfo is None:
        valid_ts = valid_ts.tz_localize("UTC")

    anchor_wind_speed = float(anchor["anchor_wind_speed"])
    anchor_wind_direction = float(anchor["anchor_wind_direction"])

    enriched = forecast_frame.copy()
    enriched["anchor_wind_speed"] = anchor_wind_speed
    enriched["anchor_wind_direction"] = anchor_wind_direction
    enriched["anchor_air_temp"] = float(anchor["anchor_air_temp"])
    enriched["datetime_utc"] = valid_ts
    enriched["endpoint_city"] = endpoint_city

    enriched["fcst_perp_wind_ms"] = thermal_model.perpendicular_wind(
        enriched["fcst_wind_speed"].to_numpy(dtype=float),
        enriched["fcst_wind_direction"].to_numpy(dtype=float),
        geometry.bearing_deg,
    )
    anchor_perp = thermal_model.perpendicular_wind(
        anchor_wind_speed, anchor_wind_direction, geometry.bearing_deg,
    )
    enriched["anchor_perp_wind_ms"] = float(np.asarray(anchor_perp))

    enriched.attrs["geometry"] = forecast_frame.attrs.get("geometry", geometry)
    anchor_observation_time = anchor["anchor_observation_time"]
    enriched.attrs["anchor_observation_time"] = (
        anchor_observation_time.isoformat()
        if hasattr(anchor_observation_time, "isoformat")
        else anchor_observation_time
    )
    enriched.attrs["anchor_source"] = anchor["anchor_source"]
    enriched.attrs["anchor_station"] = anchor["anchor_station"]
    return enriched


def _corridor_reduce_per_city(method: "CorrectionMethod", city_frames: dict, geometry) -> tuple:
    """
    Plan 05-02 (D-01/D-06): generalizes `CorridorWindCorrectionMethod`'s
    own two-stage per-city-then-weakest-link reduction to ANY
    `CorrectionMethod`, driven by the orchestrator's already-fetched,
    already-enriched per-city frames rather than a self-fetching method.

    Calls `method.predict(frame, geometry)` once per city in
    `sorted(city_frames)`'s own order (a deterministic city-A/city-B
    assignment, matching `forecast_training.corridor_weakest_link`'s own
    tie-break-to-lower-index convention), reduces the two resulting
    ampacities via that same function, and returns
    `(dlr_amps, per_city_ampacity_amps, bottleneck_city)`.

    Raises:
        ValueError: naming the found city count, if `city_frames` does
            not carry exactly two entries.
    """
    if len(city_frames) != 2:
        raise ValueError(
            f"_corridor_reduce_per_city: expected exactly two cities, found "
            f"{len(city_frames)} ({sorted(city_frames)!r})"
        )

    cities = sorted(city_frames)
    per_city_amps: dict = {}
    for city in cities:
        per_city_amps[city] = float(method.predict(city_frames[city], geometry))

    amps_a = np.array([per_city_amps[cities[0]]])
    amps_b = np.array([per_city_amps[cities[1]]])
    dlr_amps, bottleneck_index, _ = forecast_training.corridor_weakest_link(amps_a, amps_b, {}, {})
    bottleneck_city = cities[int(bottleneck_index[0])]
    return float(dlr_amps[0]), per_city_amps, bottleneck_city


# 2026-10-08 ("bundle-level ampacity"): the reason this function takes
# ALREADY-PER-CONDUCTOR, ALREADY-PER-ENDPOINT values (never the corridor-
# reduced `dlr_amps` `_corridor_reduce_per_city` also returns) is D-01's own
# scaling order -- subconductor scaling must happen BEFORE the weakest-link
# corridor reduction, never after, because the two endpoints can carry
# different bundle counts (confirmed live: AUSTIN=2, CORPUS_CHRISTI=2,
# MIDLAND=2, EL_PASO=1, per `config.SUBCONDUCTORS_PER_PHASE`). Scaling an
# already-corridor-reduced single value by one bundle count would silently
# assume both endpoints share that count, which this corridor pair's own
# MIDLAND_EL_PASO case (2 vs. 1) falsifies.
def compute_endpoint_bundle_ampacity(per_city_ampacity_amps: Optional[dict]) -> dict:
    """
    Scales each city's own single-conductor ampacity by
    `config.SUBCONDUCTORS_PER_PHASE[city]` (never by 3 for three phases --
    a subconductor bundle is a PER-PHASE parallel-conductor count, entirely
    unrelated to the three independent phases of a three-phase circuit),
    then reduces the two endpoints' own bundle ampacities via a corridor-
    level MINIMUM -- a SEPARATE weakest-link reduction from the one
    `_corridor_reduce_per_city` already applied to the per-conductor values,
    never a re-scaling of that function's own `dlr_amps` return.

    Returns a dict, always one of two shapes:

    - Unavailable (`per_city_ampacity_amps` is falsy, or names a city not in
      `config.SUBCONDUCTORS_PER_PHASE`): `{"status": "unavailable", "reason":
      <str>, "config_version": config.BUNDLE_CONFIG_VERSION}`. Never raises,
      never invents a value -- the caller's own candidate keeps its existing
      per-conductor result regardless of this function's outcome.
    - Ok: `{"status": "ok", "endpoint_bundle_ampacity_amps": {city: float},
      "corridor_bundle_ampacity_amps": float, "bundle_bottleneck_city": str,
      "subconductors_per_phase": {city: int}, "config_version":
      config.BUNDLE_CONFIG_VERSION, "rating_basis":
      config.BUNDLE_RATING_BASIS, "reason": None}`. `bundle_bottleneck_city`
      is computed independently of whatever `bottleneck_city` the caller's
      own per-conductor reduction found -- the two identities may differ
      (exactly MIDLAND_EL_PASO's own mixed-count case can produce), and
      this function never assumes they match.
    """
    if not per_city_ampacity_amps:
        return {
            "status": "unavailable",
            "reason": "no per-city (endpoint) ampacity available for this candidate",
            "config_version": config.BUNDLE_CONFIG_VERSION,
        }

    missing = [c for c in per_city_ampacity_amps if c not in config.SUBCONDUCTORS_PER_PHASE]
    if missing:
        return {
            "status": "unavailable",
            "reason": (
                f"no configured SUBCONDUCTORS_PER_PHASE entry for city(ies) {missing!r}"
            ),
            "config_version": config.BUNDLE_CONFIG_VERSION,
        }

    endpoint_bundle_ampacity_amps = {
        city: config.SUBCONDUCTORS_PER_PHASE[city] * float(amps)
        for city, amps in per_city_ampacity_amps.items()
    }
    bundle_bottleneck_city = min(
        endpoint_bundle_ampacity_amps, key=endpoint_bundle_ampacity_amps.get
    )
    return {
        "status": "ok",
        "endpoint_bundle_ampacity_amps": endpoint_bundle_ampacity_amps,
        "corridor_bundle_ampacity_amps": endpoint_bundle_ampacity_amps[bundle_bottleneck_city],
        "bundle_bottleneck_city": bundle_bottleneck_city,
        "subconductors_per_phase": {
            city: config.SUBCONDUCTORS_PER_PHASE[city] for city in per_city_ampacity_amps
        },
        "config_version": config.BUNDLE_CONFIG_VERSION,
        "rating_basis": config.BUNDLE_RATING_BASIS,
        "reason": None,
    }


@dataclass(frozen=True)
class ShadowPrediction:
    """One method's output: the corrected ampacity, the method name, and whether a fallback was used."""

    corridor: str
    method: str
    ampacity_amps: Optional[float]
    timestamps: Optional[ShadowTimestamps]
    fallback_used: bool
    fallback_reason: Optional[str] = None
    model_version: Optional[str] = None
    input_provenance: Optional[dict] = None
    # Plan 05-02 (D-01/D-04/D-07): per-candidate outcome, distinct from
    # `fallback_used`/`fallback_reason` (a method-internal fallback that
    # still produced a genuine value). `status="ok"` by default so every
    # existing call site (this file, forecast_shadow_demo.py, every test)
    # keeps constructing a ShadowPrediction unmodified. `reason` names WHY
    # no value exists this cycle when status is "unavailable" or "failed".
    status: str = "ok"
    reason: Optional[str] = None
    # 2026-10-08 ("bundle-level ampacity"): a candidate's own per-conductor
    # fields above (`ampacity_amps`, `input_provenance.per_city_ampacity_amps`)
    # are NEVER modified by this field's presence -- bundle output is a
    # strictly additive, separately-labeled reporting basis (see
    # `compute_endpoint_bundle_ampacity`'s own docstring). `None` only for
    # legacy/pre-feature call sites that never set it; every call site this
    # phase touches sets an explicit dict (status "ok" or "unavailable").
    bundle: Optional[dict] = None


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

    def __init__(
        self, model: "forecast_correction_models.WindCorrectionModel", *,
        model_version: Optional[str] = None,
        endpoint_city: Optional[str] = None, valid_time=None, decision_time=None,
    ):
        """
        `endpoint_city`/`valid_time`/`decision_time`, when all three are
        supplied, make this method fetch its own live anchor observation
        via `attach_wind_correction_inputs` inside `predict` -- so a
        missing/failed anchor source (e.g. no `SYNOPTIC_TOKEN`) raises
        from WITHIN `predict`, where `ShadowPipeline.predict`'s existing
        try/except routes it to the fallback method with a proper
        `fallback_reason`, rather than crashing the caller before the
        pipeline's fail-safe machinery ever runs. When any of the three is
        omitted, `frame` is used as-is (the pre-existing, synthetic-test
        contract: the caller already attached everything `_wind_feature_
        frame` needs).
        """
        self.model = model
        self.model_version = model_version
        self.endpoint_city = endpoint_city
        self.valid_time = valid_time
        self.decision_time = decision_time

    def predict(self, frame: pd.DataFrame, geometry) -> float:
        if self.endpoint_city is not None and self.valid_time is not None and self.decision_time is not None:
            enriched = attach_wind_correction_inputs(
                frame, endpoint_city=self.endpoint_city,
                valid_time=self.valid_time, decision_time=self.decision_time,
            )
            # Propagate the anchor provenance onto the CALLER's frame
            # object (attrs is a mutable dict on the DataFrame itself) so
            # `ShadowPipeline.predict` -- which reads `frame.attrs` from
            # its own local reference after this call returns -- actually
            # sees it; `enriched` is a fresh copy, not an alias.
            frame.attrs.update(enriched.attrs)
            frame = enriched
        prediction = forecast_correction_models.predict_wind_correction(self.model, frame)
        perp = thermal_model.perpendicular_wind(prediction.speed, prediction.direction, geometry.bearing_deg)
        ampacity = thermal_model.ieee738_ampacity(
            frame["fcst_air_temp"].to_numpy(dtype=float), perp,
            frame["fcst_solar_radiation"].to_numpy(dtype=float), geometry.conductor,
        )
        return float(np.asarray(ampacity)[0])


class CorridorWindCorrectionMethod:
    """
    The CORRIDOR-correct form of wind correction (2026-10-06 pass) --
    closes the single-city simplification `WindCorrectionShadowMethod`/
    `attach_wind_correction_inputs` named as a remaining gap.

    Training's own convention (`forecast_experiment._wind_corrected_
    ampacity`, called once per endpoint city, then reduced through
    `forecast_training.corridor_weakest_link`) applies the weakest-link
    MINIMUM to each city's own CORRECTED AMPACITY -- never to a raw
    weather variable. This class reproduces that exact two-stage
    reduction live: fetch both endpoint cities' own live forecast +
    live anchor observation independently, correct each city's own
    wind and run it through the same `predict_wind_correction` ->
    `perpendicular_wind` -> `ieee738_ampacity` chain
    `WindCorrectionShadowMethod` uses for one city, then take the
    elementwise minimum of the two cities' resulting ampacities via
    `forecast_training.corridor_weakest_link` -- the repository's one
    weakest-link reduction, never a second copy of the rule.

    `predict(frame, geometry)` IGNORES the single-city `frame` passed by
    `ShadowPipeline.predict` for its own correction math -- it exists
    only so this class satisfies the `CorrectionMethod` protocol
    `ShadowPipeline` expects, so `ShadowPipeline` itself needs no change.
    Both cities' live data is fetched internally. Provenance (per-city
    ampacity, the winning/bottleneck city, and each city's anchor
    provenance) is written onto the PASSED-IN `frame`'s own `.attrs`
    (mutated in place, the same pattern `WindCorrectionShadowMethod.
    predict` already uses), so `ShadowPipeline.predict`'s existing
    provenance-reading code (`frame.attrs.items()`) picks it up with no
    change there either.

    Raises:
        StaleOrMissingDataError: propagated from either city's forecast
            or anchor fetch -- EITHER city failing fails the whole
            corridor prediction (a corridor rating with only one city's
            real data is not the weakest-link reduction training used,
            and must not be silently reported as though it were).
    """

    name = "ml_wind_corrected"

    def __init__(
        self, model: "forecast_correction_models.WindCorrectionModel", *,
        corridor: str, model_version: Optional[str] = None,
        valid_time, decision_time, horizon_minutes: int,
    ):
        self.model = model
        self.model_version = model_version
        self.corridor = corridor
        self.valid_time = valid_time
        self.decision_time = decision_time
        self.horizon_minutes = horizon_minutes

    def predict(self, frame: pd.DataFrame, geometry) -> float:
        cities = config.CORRIDOR_ENDPOINTS[self.corridor]
        per_city_amps: dict = {}
        per_city_provenance: dict = {}
        for city in cities:
            lat, lon = config.CITY_COORDINATES[city]
            row, _ = fetch_live_forecast_for_valid_time(
                self.corridor, self.valid_time, horizon_minutes=self.horizon_minutes,
                lat=lat, lon=lon,
            )
            city_frame = validate_and_prepare_shadow_row(row, corridor=self.corridor)
            city_frame = attach_wind_correction_inputs(
                city_frame, endpoint_city=city,
                valid_time=self.valid_time, decision_time=self.decision_time,
            )
            prediction = forecast_correction_models.predict_wind_correction(self.model, city_frame)
            perp = thermal_model.perpendicular_wind(prediction.speed, prediction.direction, geometry.bearing_deg)
            amps = thermal_model.ieee738_ampacity(
                city_frame["fcst_air_temp"].to_numpy(dtype=float), perp,
                city_frame["fcst_solar_radiation"].to_numpy(dtype=float), geometry.conductor,
            )
            per_city_amps[city] = float(np.asarray(amps)[0])
            per_city_provenance[city] = {
                "anchor_observation_time": city_frame.attrs.get("anchor_observation_time"),
                "anchor_source": city_frame.attrs.get("anchor_source"),
                "anchor_station": city_frame.attrs.get("anchor_station"),
            }

        amps_a = np.array([per_city_amps[cities[0]]])
        amps_b = np.array([per_city_amps[cities[1]]])
        dlr_amps, bottleneck_index, _ = forecast_training.corridor_weakest_link(amps_a, amps_b, {}, {})
        bottleneck_city = cities[int(bottleneck_index[0])]

        frame.attrs["per_city_ampacity_amps"] = per_city_amps
        frame.attrs["bottleneck_city"] = bottleneck_city
        frame.attrs["anchor_provenance"] = per_city_provenance
        return float(dlr_amps[0])


class CoolingCorrectionShadowMethod:
    """
    The main challenger, lightly implemented to demonstrate the interface's
    substitutability -- not the prototype's working choice. Wraps a
    persisted `forecast_correction_models.CoolingCorrectionModel`.
    """

    name = "ml_cooling_corrected"

    def __init__(self, model: "forecast_correction_models.CoolingCorrectionModel", *, model_version: Optional[str] = None):
        self.model = model
        self.model_version = model_version

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


def model_version_for(corridor: str, method_name: str) -> str:
    """
    A version identifier for the persisted model at `_model_path_for`:
    `<method>_<corridor>@<file mtime ISO-8601>`. Not a content hash --
    cheap and sufficient to tell two log entries apart if the underlying
    file is ever retrained and re-saved, which is all this prototype's
    logging needs it for.
    """
    path = _model_path_for(corridor, method_name)
    mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    return f"{method_name}_{corridor}@{mtime.isoformat()}"


# Plan 05-02 (D-05, Pitfall 3): how close a prior logged entry's own
# `valid_time` must land to this cycle's `decision_time` to count as "the"
# 24h-ago anchor. Generous for the twice-daily (not exactly-24h-apart)
# collection cadence -- named here as a module constant, not a magic
# number inline, so the tolerance is visible and changeable in one place.
_PERSISTENCE_VALID_TIME_TOLERANCE = pd.Timedelta(minutes=90)


class Persistence24hShadowMethod:
    """
    Plan 05-02 (D-05): the live, decision-time-available form of
    `persistence_24h` -- reads THIS collector's own prior logged entry
    for the same corridor, never a reanalysis/archive backfill. Unlike
    `forecast_shadow_healthcheck._last_entry` (which correctly wants the
    positionally-LAST line for its own different purpose, freshness),
    this method must find the entry whose own `valid_time` is closest to
    `this_cycle_decision_time` -- at the twice-daily cadence, the
    immediately-preceding entry's `valid_time` is only ~12h old, not 24h
    (05-RESEARCH.md Pitfall 3).

    Reads the entry's own `candidates.raw_forecast` sub-object (not
    `ml_wind_corrected`'s) -- see 05-02-PLAN.md's objective for why
    `raw_forecast` is the least-processed, least-correction-model-
    derivative of the five candidates and therefore the right baseline
    anchor for a model-independent persistence arm.
    """

    name = "persistence_24h"

    def compute(self, corridor: str, this_cycle_decision_time) -> "ShadowPrediction":
        decision_ts = pd.Timestamp(this_cycle_decision_time)
        if decision_ts.tzinfo is None:
            decision_ts = decision_ts.tz_localize("UTC")

        path = os.path.join(SHADOW_PREDICTIONS_DIR, f"{corridor}.jsonl")
        best_entry: Optional[dict] = None
        best_delta: Optional[pd.Timedelta] = None

        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        # A malformed line is skipped, never raised on --
                        # this reader must never crash the collector.
                        continue
                    # A pre-cutover flat-shape row (no schema_version, or
                    # schema_version 1) is a normal, expected, skippable
                    # input here -- not a corruption (05-01-SUMMARY.md's
                    # own no-migration strategy).
                    if entry.get("schema_version", 1) < 2:
                        continue
                    raw_valid_time = entry.get("valid_time")
                    if raw_valid_time is None:
                        continue
                    try:
                        entry_valid_time = pd.Timestamp(raw_valid_time)
                    except (ValueError, TypeError):
                        continue
                    if entry_valid_time.tzinfo is None:
                        entry_valid_time = entry_valid_time.tz_localize("UTC")
                    delta = abs(entry_valid_time - decision_ts)
                    if delta <= _PERSISTENCE_VALID_TIME_TOLERANCE and (
                        best_delta is None or delta < best_delta
                    ):
                        best_entry = entry
                        best_delta = delta

        if best_entry is None:
            return ShadowPrediction(
                corridor=corridor, method=self.name, ampacity_amps=None,
                timestamps=None, fallback_used=False, status="unavailable",
                reason=(
                    "no prior entry within tolerance of decision_time "
                    f"{decision_ts.isoformat()} (cold start, or a gap in "
                    "this corridor's collection history)"
                ),
                bundle={
                    "status": "unavailable",
                    "reason": "no matched prior entry this cycle (see the candidate's own reason)",
                    "config_version": config.BUNDLE_CONFIG_VERSION,
                },
            )

        raw_candidate = (best_entry.get("candidates") or {}).get("raw_forecast") or {}
        raw_status = raw_candidate.get("status")
        if raw_status != "ok":
            return ShadowPrediction(
                corridor=corridor, method=self.name, ampacity_amps=None,
                timestamps=None, fallback_used=False, status="unavailable",
                reason=(
                    "the matched prior entry's own raw_forecast candidate "
                    f"was itself {raw_status!r}"
                ),
                bundle={
                    "status": "unavailable",
                    "reason": "the matched prior entry's own raw_forecast candidate was itself not ok",
                    "config_version": config.BUNDLE_CONFIG_VERSION,
                },
            )

        provenance = None
        if raw_candidate.get("per_city_ampacity_amps") is not None or raw_candidate.get("bottleneck_city") is not None:
            provenance = {
                "per_city_ampacity_amps": raw_candidate.get("per_city_ampacity_amps"),
                "bottleneck_city": raw_candidate.get("bottleneck_city"),
            }
        elif isinstance(raw_candidate.get("input_provenance"), dict):
            provenance = raw_candidate.get("input_provenance")

        # 2026-10-08 ("bundle-level ampacity"): D-05's own decision-time
        # discipline, extended to bundle output -- persistence must persist
        # the DECISION-TIME bundle rating the matched prior entry's own
        # raw_forecast candidate already computed from the endpoint values
        # available AT THAT TIME, never re-derive one now by re-scaling an
        # already-corridor-reduced ampacity under TODAY's bundle config
        # (which could silently diverge from what was true back then, and
        # would double-apply a reduction `compute_endpoint_bundle_ampacity`
        # already performed once). A matched entry logged before this
        # feature existed carries no "bundle" key at all -- unavailable,
        # never backfilled/invented.
        matched_bundle = raw_candidate.get("bundle")
        if isinstance(matched_bundle, dict):
            bundle = dict(matched_bundle)
        else:
            bundle = {
                "status": "unavailable",
                "reason": "the matched prior entry predates bundle reporting (no 'bundle' key)",
                "config_version": config.BUNDLE_CONFIG_VERSION,
            }

        return ShadowPrediction(
            corridor=corridor, method=self.name,
            ampacity_amps=raw_candidate.get("ampacity_amps"),
            timestamps=None, fallback_used=False, status="ok",
            input_provenance=provenance, bundle=bundle,
        )


# Plan 05-04: how close a live station row must land to one of the seven
# required hourly timestamps in `fetch_live_truth_proxy_series`'s window
# to count as that hour's own observation. Named module constant, not a
# magic number inline -- mirrors `_PERSISTENCE_VALID_TIME_TOLERANCE`'s own
# convention above.
_TRUTH_PROXY_HOUR_TOLERANCE = pd.Timedelta(minutes=20)

# 2026-10-08 ("investigate wiring NSRDB or forecast-API solar"): the
# station fields `fetch_live_truth_proxy_series` validates against
# `provider="tceq"` (Synoptic-fallback-eligible). `solar_radiation` is
# deliberately NOT in this tuple -- confirmed by direct read,
# `tceq_provider.fetch_tceq`'s own `_RETURN_COLUMNS` never includes it
# (that provider is wired for wind/temp/RH only, per this project's own
# WX-01 scope), and the Synoptic/ASOS airport stations this project's
# anchor-wind path already falls back to don't report it either (no
# `*_solar*` key ever appears in a live `fetch_weather(provider="synoptic")`
# OBS payload) -- so there is no live NEAR-REAL-TIME STATION solar source
# anywhere in this codebase to require it from. A null in ANY of these
# three at a required hour is the same "missing hour" failure as no row
# at all (Plan 05-04 action step 2, T-05-04-01): never silently passed
# through to the physics/weakest-link reduction below.
_TRUTH_PROXY_STATION_FIELDS = ("air_temp", "wind_speed", "wind_direction")

# 2026-10-08: `solar_radiation`'s own source and matching tolerance.
# `open_meteo_forecast_provider.fetch_historical_forecast` is a lat/lon
# bulk NWP-model HINDCAST (never a station observation) for a recent,
# already-past window -- the same "bit-identical to truth for a
# necessarily-recent window" product Phase 3 Wave 1 found for a 1-HOUR
# LEAD (03-01-SUMMARY.md's Critical Finding), but used here in the exact
# regime where that property is a feature, not a defect: every target
# hour below is already in the past relative to `anchor_time`, so there
# is no leakage risk, and a model hindcast is the closest thing to a real
# solar observation this project's live infrastructure can actually
# reach. Every `input_provenance` this function's caller attaches names
# this source explicitly (`solar_source`) -- never silently presented as
# a true station reading. Hourly-only data: the tolerance is wide enough
# (35 min) to always resolve to the nearest hour regardless of exactly
# where within that hour `anchor_time`/a target hour falls (max possible
# true distance to the nearest hour is 30 min) -- `_TRUTH_PROXY_HOUR_
# TOLERANCE`'s own 20-minute figure was tuned for continuous station
# data and would spuriously reject a correct hourly match here.
_TRUTH_PROXY_SOLAR_HOUR_TOLERANCE = pd.Timedelta(minutes=35)

# 2026-10-08: how many total attempts `_fetch_solar_proxy_hours` makes
# against Open-Meteo's historical-forecast endpoint, and how long it
# waits between attempts, before giving up. See that function's own
# comment for the live-data investigation that motivated this. Deliberately
# only ONE retry (2 attempts total), not more: each attempt can itself take
# up to `config.FORECAST_EXPERIMENT_HTTP_TIMEOUT_S` (60s) to time out, this
# function is called once per endpoint city (2x per corridor), and the
# scheduled workflow budgets 15 minutes for the ENTIRE two-corridor cycle --
# a worse-case 3-attempt retry chain here could alone approach that ceiling.
_SOLAR_PROXY_FETCH_ATTEMPTS = 2
_SOLAR_PROXY_RETRY_DELAY_S = 3


def _select_hour_row(frame: pd.DataFrame, target_ts: "pd.Timestamp", tolerance: "pd.Timedelta"):
    """
    Return the row in `frame` (carrying a `datetime_utc` column) closest
    to `target_ts`, or `None` if `frame` is empty or that closest row's
    own distance from `target_ts` exceeds `tolerance`. Never interpolates
    or invents a row -- only ever selects an actually-observed one.
    """
    if frame.empty:
        return None
    diffs = (frame["datetime_utc"] - target_ts).abs()
    idx = diffs.idxmin()
    if diffs.loc[idx] > tolerance:
        return None
    return frame.loc[idx]


def _fetch_solar_proxy_hours(
    corridor: str, city: str, lat: float, lon: float,
    window_start: "pd.Timestamp", anchor_ts: "pd.Timestamp",
    target_times: list,
) -> list:
    """
    One city's `solar_radiation` values for `fetch_live_truth_proxy_series`'s
    `target_times`, sourced from `open_meteo_forecast_provider.
    fetch_historical_forecast(lat, lon, window_start, anchor_ts)` -- see
    `_TRUTH_PROXY_SOLAR_HOUR_TOLERANCE`'s own module-level comment for why
    this lat/lon NWP hindcast, not a station reading, is this project's
    only reachable near-real-time solar source. Returns one float per
    `target_times` entry, in the same order; never interpolates, pads, or
    backfills a missing/null hour (same discipline as the station path).
    """
    # 2026-10-08 ("why does reference_ml_refit only ever produce a value
    # once"): live investigation of the real `shadow-collection-data`
    # history found this exact call timing out (`Read timed out
    # (read_timeout=60)`) on 5 of 14 real cycles across both corridors --
    # the single current majority failure mode, now that the station
    # per-hour fallback (D-04/D-09's own fix) and the solar-source switch
    # (away from TCEQ, which never had it) are both already live. A
    # retry gets a FRESH connection attempt, which is the right response
    # to a stuck/slow read -- simply raising `config.FORECAST_EXPERIMENT_
    # HTTP_TIMEOUT_S` would not: that constant is also read by `fetch_
    # single_run`/`fetch_previous_runs`, which the FROZEN Phase 3/4
    # experiment harness still depends on for its own reproducibility, so
    # it is deliberately left untouched here rather than bumped globally.
    last_exc: Exception | None = None
    frame = None
    for attempt in range(_SOLAR_PROXY_FETCH_ATTEMPTS):
        try:
            frame = open_meteo_forecast_provider.fetch_historical_forecast(
                lat, lon, window_start.isoformat(), anchor_ts.isoformat(),
            )
            break
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < _SOLAR_PROXY_FETCH_ATTEMPTS:
                logger.info(
                    "fetch_live_truth_proxy_series(%r, %r): solar-proxy fetch "
                    "attempt %d/%d failed (%s) -- retrying",
                    corridor, city, attempt + 1, _SOLAR_PROXY_FETCH_ATTEMPTS, exc,
                )
                time.sleep(_SOLAR_PROXY_RETRY_DELAY_S)
    if frame is None:
        raise StaleOrMissingDataError(
            f"fetch_live_truth_proxy_series: corridor {corridor!r} city "
            f"{city!r}: solar-proxy (Open-Meteo historical forecast) window "
            f"fetch failed after {_SOLAR_PROXY_FETCH_ATTEMPTS} attempt(s): {last_exc}"
        ) from last_exc

    values = []
    for target_ts in target_times:
        row = _select_hour_row(frame, target_ts, _TRUTH_PROXY_SOLAR_HOUR_TOLERANCE)
        if row is None:
            raise StaleOrMissingDataError(
                f"fetch_live_truth_proxy_series: corridor {corridor!r} city "
                f"{city!r}: no usable Open-Meteo historical-forecast solar "
                f"row within {_TRUTH_PROXY_SOLAR_HOUR_TOLERANCE} of required "
                f"hour {target_ts.isoformat()}"
            )
        value = row.get("solar_radiation")
        if pd.isnull(value):
            raise StaleOrMissingDataError(
                f"fetch_live_truth_proxy_series: corridor {corridor!r} city "
                f"{city!r}: null 'solar_radiation' (Open-Meteo historical "
                f"forecast) at required hour {target_ts.isoformat()}"
            )
        values.append(float(value))
    return values


def _usable_station_row(frame: pd.DataFrame, target_ts: "pd.Timestamp"):
    """
    One hour's worth of `_latest_usable_row`'s own usability check
    (`fetch_live_anchor_observation`), generalized from "the latest row"
    to "the row matching one specific target hour": returns `(row, None)`
    if a row exists within `_TRUTH_PROXY_HOUR_TOLERANCE` of `target_ts`
    with every `_TRUTH_PROXY_STATION_FIELDS` field non-null, else
    `(None, reason)` naming which of the two failure shapes occurred
    (no row in tolerance, vs. a matched row with a null field) -- same
    "mechanically successful but unusable" distinction that function's
    own docstring draws, reused here rather than re-invented.
    """
    row = _select_hour_row(frame, target_ts, _TRUTH_PROXY_HOUR_TOLERANCE)
    if row is None:
        return None, "no usable station row within tolerance"
    for field in _TRUTH_PROXY_STATION_FIELDS:
        if pd.isnull(row.get(field)):
            return None, f"null {field!r}"
    return row, None


def _fetch_station_hours(
    corridor: str, city: str, cams_id: str,
    window_start: "pd.Timestamp", anchor_ts: "pd.Timestamp", target_times: list,
):
    """
    2026-10-08 ("what would the fix for that be"): fetches this city's
    TCEQ station window ONCE, matches each of `target_times` against it,
    and -- ONLY for the specific hours whose matched TCEQ row is missing
    or has a null required field (TCEQ's own trailing-not-yet-reported-
    hour case, `fetch_live_anchor_observation`'s own confirmed-live
    finding) -- makes ONE explicit retry fetch against this city's
    `config.SYNOPTIC_FALLBACK_STATIONS` entry and re-checks only those
    gap hours against it. This mirrors `fetch_live_anchor_observation`'s
    own explicit-retry-at-the-row-level pattern, generalized from one row
    to seven independent hours, rather than relying on `weather_
    provider.fetch_weather`'s own `fallback=True` default -- which only
    fires on a RAISED exception or an EMPTY response, never on a
    mechanically successful response whose one specific row is unusable
    (the exact gap this function exists to close).

    Returns `(fields, sources)`: `fields` maps each of
    `_TRUTH_PROXY_STATION_FIELDS` to a 7-element float list aligned to
    `target_times`; `sources` is a same-length list of `"tceq"` or
    `"synoptic"` naming which provider actually supplied each hour --
    never a single corridor-wide summary, since a real window can be
    genuinely mixed (some hours from each provider).

    Raises:
        StaleOrMissingDataError: the primary TCEQ window-fetch itself
            failed, or any required hour is still unusable after the
            Synoptic retry (naming the hour and BOTH providers' own
            specific failure reasons), or no Synoptic fallback station
            is configured for `city` at all and a gap hour exists.
    """
    try:
        tceq_frame = weather_provider.fetch_weather(
            [cams_id], window_start.isoformat(), anchor_ts.isoformat(), provider="tceq",
        )
    except Exception as exc:
        raise StaleOrMissingDataError(
            f"fetch_live_truth_proxy_series: corridor {corridor!r} city "
            f"{city!r}: window fetch failed: {exc}"
        ) from exc

    if tceq_frame.empty:
        tceq_frame = pd.DataFrame(columns=["datetime_utc", *_TRUTH_PROXY_STATION_FIELDS])
    else:
        tceq_frame = tceq_frame.reset_index()
        tceq_frame["datetime_utc"] = pd.to_datetime(tceq_frame["datetime_utc"], utc=True)

    resolved: dict = {}
    gap_reasons: dict = {}
    for target_ts in target_times:
        row, reason = _usable_station_row(tceq_frame, target_ts)
        if row is None:
            gap_reasons[target_ts] = reason
        else:
            resolved[target_ts] = ("tceq", row)

    synoptic_station = config.SYNOPTIC_FALLBACK_STATIONS.get(city)
    synoptic_frame = None
    if gap_reasons and synoptic_station is not None:
        logger.info(
            "fetch_live_truth_proxy_series(%r, %r): %d gap hour(s) at TCEQ CAMS "
            "%r -- retrying those hours against Synoptic station %r",
            corridor, city, len(gap_reasons), cams_id, synoptic_station,
        )
        try:
            synoptic_frame = weather_provider.fetch_weather(
                [synoptic_station], window_start.isoformat(), anchor_ts.isoformat(),
                provider="synoptic",
            )
        except Exception as exc:
            logger.info(
                "fetch_live_truth_proxy_series(%r, %r): Synoptic retry fetch "
                "raised (%s) -- gap hour(s) remain unresolved", corridor, city, exc,
            )
            synoptic_frame = pd.DataFrame(columns=["datetime_utc", *_TRUTH_PROXY_STATION_FIELDS])
        else:
            if synoptic_frame.empty:
                synoptic_frame = pd.DataFrame(columns=["datetime_utc", *_TRUTH_PROXY_STATION_FIELDS])
            else:
                synoptic_frame = synoptic_frame.reset_index()
                synoptic_frame["datetime_utc"] = pd.to_datetime(
                    synoptic_frame["datetime_utc"], utc=True,
                )

    still_missing = []
    for target_ts, tceq_reason in gap_reasons.items():
        if synoptic_frame is None:
            still_missing.append((target_ts, tceq_reason, "no Synoptic fallback station configured for this city"))
            continue
        row, synoptic_reason = _usable_station_row(synoptic_frame, target_ts)
        if row is None:
            still_missing.append((target_ts, tceq_reason, synoptic_reason))
        else:
            resolved[target_ts] = ("synoptic", row)

    if still_missing:
        target_ts, tceq_reason, synoptic_reason = sorted(still_missing, key=lambda t: t[0])[0]
        raise StaleOrMissingDataError(
            f"fetch_live_truth_proxy_series: corridor {corridor!r} city {city!r}: "
            f"required hour {target_ts.isoformat()} unusable at both providers "
            f"(tceq CAMS {cams_id!r}: {tceq_reason}; synoptic: {synoptic_reason})"
        )

    fields: dict = {field: [] for field in _TRUTH_PROXY_STATION_FIELDS}
    sources: list = []
    for target_ts in target_times:
        source, row = resolved[target_ts]
        sources.append(source)
        for field in _TRUTH_PROXY_STATION_FIELDS:
            fields[field].append(float(row[field]))

    return fields, sources


def fetch_live_truth_proxy_series(
    corridor: str, anchor_time, *, lookback_hours: float = None,
):
    """
    Plan 05-04 (D-05's decision-time discipline, generalized for arm 5's
    own lagged/rolling feature needs): build a 7-row, hourly, corridor-
    level TRUTH-PROXY series -- `anchor_time - lookback_hours` through
    `anchor_time` inclusive -- from near-real-time station observations,
    shaped EXACTLY like `forecast_experiment._arm5_truth_frame`'s own
    output (`datetime_utc`, `dlr_amps`, `air_temp`, `wind_speed`,
    `solar_radiation`) so it can be fed straight into `ampacity_forecast.
    build_ml_features` -- the SAME feature builder arm 5's own offline fit
    (`forecast_training.build_training_matrix`) already calls.

    For EACH endpoint city, fetches ONE window of `provider="tceq"`
    station observations spanning `[anchor_time - lookback_hours,
    anchor_time]`, then selects, for each of the 7 target hourly
    timestamps, the closest row within `_TRUTH_PROXY_HOUR_TOLERANCE` (20
    minutes). 2026-10-08: a missing/null hour no longer raises
    immediately -- `_fetch_station_hours` collects every such gap hour
    first, then makes ONE explicit retry fetch against this city's
    `config.SYNOPTIC_FALLBACK_STATIONS` entry and re-checks only those
    gap hours against it (the same explicit-row-level-retry pattern
    `fetch_live_anchor_observation` already uses for its own single-row
    lookup, generalized to seven independent hours here, since `fetch_
    weather`'s own `fallback=True` default only fires on a raised
    exception/empty response, never on a mechanically successful
    response whose one specific row is unusable -- TCEQ's own trailing
    not-yet-reported-hour case). Only a gap hour still unusable after
    that retry raises `StaleOrMissingDataError`, naming the hour and
    BOTH providers' own specific failure reasons. Never interpolates,
    pads, or backfills a missing hour at either provider (D-04/
    T-05-04-01).

    Once both cities' 7-hour windows are fully validated, each city's own
    hourly ampacity is computed via the SAME `thermal_model.
    perpendicular_wind` + `thermal_model.ieee738_ampacity` chain every
    other method in this module uses, against the corridor's own
    `geometry.bearing_deg`/`conductor` (`corridor_discretization.
    corridor_geometry`); the two cities' 7-element ampacity arrays are
    reduced via ONE call to `forecast_training.corridor_weakest_link` --
    the repository's one weakest-link reduction, never a second copy of
    the rule, and never one call per hour.

    `lookback_hours` defaults to `config.FORECAST_ML_ROLLING_WINDOW_HOURS`
    (6) -- the exact depth arm 5's own lag/rolling features need
    (`config.FORECAST_ML_LAG_HOURS`'s max of 6h, `FORECAST_ML_ROLLING_
    WINDOW_HOURS`), looked up at call time rather than bound as a mutable
    default so a test's `config` monkeypatch is honored.

    `solar_radiation` is sourced separately from `air_temp`/`wind_speed`/
    `wind_direction`: neither TCEQ nor this project's Synoptic fallback
    reports it, so it comes from `open_meteo_forecast_provider.
    fetch_historical_forecast` (a lat/lon bulk NWP-model hindcast for this
    SAME already-past window, never a station reading -- see
    `_TRUTH_PROXY_SOLAR_HOUR_TOLERANCE`'s own comment for why this is
    safe here despite Phase 3's "bit-identical to truth" 1-hour-lead
    finding about the same product family). Every caller's own
    `input_provenance` names this source explicitly as `solar_source`.

    Returns:
        A `(series, provenance)` tuple. `series` is a `pd.DataFrame` with
        exactly 7 rows, columns `datetime_utc`, `dlr_amps`, `air_temp`,
        `wind_speed`, `solar_radiation`, sorted ascending by
        `datetime_utc`, whose LAST row's `datetime_utc` equals
        `anchor_time`. `provenance` is
        `{"station_provenance": {city: {"sources": [...], "fallback_hours":
        [...]}, ...}, "solar_source": "open_meteo_historical_forecast"}` --
        `sources` is a 7-element list of `"tceq"`/`"synoptic"` aligned to
        the series' own rows for that city, and `fallback_hours` names
        (as ISO-8601 strings) exactly which hours, if any, came from
        Synoptic rather than TCEQ -- never a single corridor-wide
        fallback flag, since one city's window can be genuinely mixed.
        Never silently omitted or defaulted: a caller that needs to know
        exactly what supplied this series' inputs always can.

    Raises:
        StaleOrMissingDataError: on any window-fetch failure, or any
            required hour still unusable after the per-hour Synoptic
            retry, for either endpoint city, from either the station or
            the solar-proxy source.
    """
    if lookback_hours is None:
        lookback_hours = config.FORECAST_ML_ROLLING_WINDOW_HOURS
    lookback_hours = int(lookback_hours)

    anchor_ts = pd.Timestamp(anchor_time)
    if anchor_ts.tzinfo is None:
        anchor_ts = anchor_ts.tz_localize("UTC")
    window_start = anchor_ts - pd.Timedelta(hours=lookback_hours)
    # Ascending: anchor_time - lookback_hours, ..., anchor_time - 1h, anchor_time.
    target_times = [anchor_ts - pd.Timedelta(hours=h) for h in range(lookback_hours, -1, -1)]

    geometry = corridor_discretization.corridor_geometry(corridor)
    city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor]

    per_city_fields: dict = {}
    station_provenance: dict = {}
    for city in (city_a, city_b):
        cams_id = config.TCEQ_STATIONS.get(city)
        if cams_id is None:
            raise StaleOrMissingDataError(
                f"fetch_live_truth_proxy_series: corridor {corridor!r}: no "
                f"known TCEQ CAMS site for city {city!r}"
            )

        fields, sources = _fetch_station_hours(
            corridor, city, cams_id, window_start, anchor_ts, target_times,
        )
        station_provenance[city] = {
            "sources": sources,
            "fallback_hours": [
                target_times[i].isoformat()
                for i, source in enumerate(sources) if source == "synoptic"
            ],
        }

        lat, lon = config.CITY_COORDINATES[city]
        fields["solar_radiation"] = _fetch_solar_proxy_hours(
            corridor, city, lat, lon, window_start, anchor_ts, target_times,
        )
        per_city_fields[city] = fields

    perp_a = thermal_model.perpendicular_wind(
        np.array(per_city_fields[city_a]["wind_speed"], dtype=float),
        np.array(per_city_fields[city_a]["wind_direction"], dtype=float),
        geometry.bearing_deg,
    )
    amps_a = np.asarray(
        thermal_model.ieee738_ampacity(
            np.array(per_city_fields[city_a]["air_temp"], dtype=float), perp_a,
            np.array(per_city_fields[city_a]["solar_radiation"], dtype=float), geometry.conductor,
        ),
        dtype=float,
    )
    perp_b = thermal_model.perpendicular_wind(
        np.array(per_city_fields[city_b]["wind_speed"], dtype=float),
        np.array(per_city_fields[city_b]["wind_direction"], dtype=float),
        geometry.bearing_deg,
    )
    amps_b = np.asarray(
        thermal_model.ieee738_ampacity(
            np.array(per_city_fields[city_b]["air_temp"], dtype=float), perp_b,
            np.array(per_city_fields[city_b]["solar_radiation"], dtype=float), geometry.conductor,
        ),
        dtype=float,
    )

    dlr_amps, _, winning_columns = forecast_training.corridor_weakest_link(
        amps_a, amps_b,
        {
            "air_temp": np.array(per_city_fields[city_a]["air_temp"], dtype=float),
            "wind_speed": np.array(per_city_fields[city_a]["wind_speed"], dtype=float),
            "solar_radiation": np.array(per_city_fields[city_a]["solar_radiation"], dtype=float),
        },
        {
            "air_temp": np.array(per_city_fields[city_b]["air_temp"], dtype=float),
            "wind_speed": np.array(per_city_fields[city_b]["wind_speed"], dtype=float),
            "solar_radiation": np.array(per_city_fields[city_b]["solar_radiation"], dtype=float),
        },
    )

    series = pd.DataFrame({
        "datetime_utc": target_times,
        "dlr_amps": dlr_amps,
        "air_temp": winning_columns["air_temp"],
        "wind_speed": winning_columns["wind_speed"],
        "solar_radiation": winning_columns["solar_radiation"],
    }).sort_values("datetime_utc").reset_index(drop=True)

    provenance = {
        "station_provenance": station_provenance,
        "solar_source": "open_meteo_historical_forecast",
    }
    return series, provenance


_PER_CITY_NOT_APPLICABLE_REASON = (
    "reference_ml_refit_24h is architecturally corridor-level-native with no "
    "per-city decomposition at inference time, exactly as at training time: "
    "the estimator is fit on forecast_experiment._arm5_truth_frame's own "
    "weakest-link-reduced corridor series and never sees a per-city value, "
    "so there is no per-city ampacity to report here either."
)

# 2026-10-08 ("bundle-level ampacity"): reference_ml_refit_24h can NEVER
# produce a bundle estimate, regardless of whether the prediction itself
# succeeds this cycle -- a corridor-only prediction has no per-endpoint
# value to scale by a (possibly different) per-city subconductor count, so
# there is no honest way to derive one. Never invented, never silently
# approximated from the corridor value under one assumed bundle count.
_BUNDLE_NOT_APPLICABLE = {
    "status": "unavailable",
    "reason": (
        "reference_ml_refit_24h produces only a corridor-level prediction "
        "(see per_city_not_applicable_reason) -- a corridor-only value "
        "cannot generally be converted to a bundle estimate when endpoint "
        "cities carry different subconductors-per-phase counts, so no "
        "bundle output is computed for this candidate."
    ),
    "config_version": config.BUNDLE_CONFIG_VERSION,
}


class ReferenceRefit24hShadowMethod:
    """
    Plan 05-04 (D-03/D-04): the real predict path, replacing 05-02's
    honest `status="unavailable"` stub now that a persisted arm-5 MLP
    artifact exists for both corridors (`backend/forecast_shadow_fit_
    reference_refit.py`). Loads the persisted estimator via `load_
    correction_model` (never fits/retrains it -- D-09, T-05-04-04), builds
    its live feature row from `fetch_live_truth_proxy_series`'s 7-hour
    truth-proxy window via `ampacity_forecast.build_ml_features` (the SAME
    feature builder the offline fit used), and predicts from the LAST row
    (the one anchored at `anchor_time`, the only row whose lag/rolling
    features are fully determined).
    """

    name = "reference_ml_refit_24h"

    def compute(self, corridor: str, anchor_time) -> "ShadowPrediction":
        try:
            estimator = load_correction_model(corridor, self.name)
        except FileNotFoundError as exc:
            return ShadowPrediction(
                corridor=corridor, method=self.name, ampacity_amps=None,
                timestamps=None, fallback_used=False, status="unavailable",
                reason=str(exc), bundle=dict(_BUNDLE_NOT_APPLICABLE),
            )

        try:
            truth_proxy_series, truth_provenance = fetch_live_truth_proxy_series(corridor, anchor_time)
        except StaleOrMissingDataError as exc:
            return ShadowPrediction(
                corridor=corridor, method=self.name, ampacity_amps=None,
                timestamps=None, fallback_used=False, status="unavailable",
                reason=str(exc), bundle=dict(_BUNDLE_NOT_APPLICABLE),
            )

        indexed = truth_proxy_series.set_index("datetime_utc").sort_index()
        features = ampacity_forecast.build_ml_features(indexed)
        last_row = features.iloc[[-1]]

        if bool(last_row.isnull().to_numpy().any()):
            # Structurally should be impossible given fetch_live_truth_proxy_
            # series's own per-hour validation above -- asserted, not merely
            # trusted, per this plan's own <behavior> spec.
            raise AssertionError(
                f"ReferenceRefit24hShadowMethod.compute({corridor!r}): the "
                f"live feature row built from a validated 7-hour truth-proxy "
                f"window still carries a null value -- refusing to predict "
                f"from it: {last_row.to_dict(orient='records')}"
            )

        prediction = float(np.asarray(estimator.predict(last_row.to_numpy(dtype=float)))[0])

        provenance = {
            "truth_proxy_window_start": truth_proxy_series["datetime_utc"].iloc[0].isoformat(),
            "truth_proxy_window_end": truth_proxy_series["datetime_utc"].iloc[-1].isoformat(),
            "per_city_ampacity_amps": None,
            "per_city_not_applicable_reason": _PER_CITY_NOT_APPLICABLE_REASON,
            **truth_provenance,
        }
        return ShadowPrediction(
            corridor=corridor, method=self.name, ampacity_amps=prediction,
            timestamps=None, fallback_used=False, status="ok",
            model_version=model_version_for(corridor, self.name),
            input_provenance=provenance, bundle=dict(_BUNDLE_NOT_APPLICABLE),
        )


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

# Plan 05-02 (D-01): the five real (non-oracle) 24-hour-lead candidates
# this phase records side by side every cycle, in D-01's own order.
# `ml_wind_corrected` stays the provisional default (the legacy mirror
# target in `log_cycle_predictions`); the other four are additive
# recording only -- this phase declares no winner.
CANDIDATE_METHOD_NAMES: tuple[str, ...] = (
    "ml_wind_corrected", "ml_cooling_corrected", "raw_forecast",
    "persistence_24h", "reference_ml_refit_24h",
)

# The three candidates needing the per-city-then-weakest-link reduction
# `_corridor_reduce_per_city` performs; `persistence_24h` and
# `reference_ml_refit_24h` are corridor-level by construction (one read
# of this collector's own prior log, one artifact load) and never go
# through this reduction.
PER_CITY_REDUCED_METHOD_NAMES: tuple[str, ...] = (
    "ml_wind_corrected", "ml_cooling_corrected", "raw_forecast",
)


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
            provenance = {
                k: v for k, v in frame.attrs.items() if k != "geometry"
            } or None
            return ShadowPrediction(
                corridor=self.corridor, method=self.primary_method.name,
                ampacity_amps=amps, timestamps=timestamps, fallback_used=False,
                model_version=getattr(self.primary_method, "model_version", None),
                input_provenance=provenance,
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
            "model_version": prediction.model_version,
            "input_provenance": prediction.input_provenance,
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


def log_cycle_predictions(
    corridor: str, candidates: dict, timestamps: ShadowTimestamps,
) -> str:
    """
    Plan 05-02 (D-06, 05-01-SUMMARY.md's approved schema_version-2 shape):
    writes exactly ONE JSON line per cycle to the SAME `data/shadow/
    predictions/<corridor>.jsonl` path `ShadowPipeline.log_prediction`
    already writes (append mode, never a second file/directory), carrying
    all five candidates nested under their own names plus the six-field
    backward-compatible top-level mirror of `candidates["ml_wind_
    corrected"]` -- an EXACT, byte-for-byte copy of that one candidate's
    own fields, including when `ml_wind_corrected` itself is
    "unavailable" or "failed" that cycle (05-01-SUMMARY.md's own approved
    mirror rule, cited by name, not re-derived).

    `candidates` must carry every name in `CANDIDATE_METHOD_NAMES`;
    `timestamps` is the ONE shared quadruple fetched once for the whole
    cycle (D-02) -- not read per-candidate from each `ShadowPrediction`'s
    own (possibly `None`) `timestamps` field.
    """
    os.makedirs(SHADOW_PREDICTIONS_DIR, exist_ok=True)
    path = os.path.join(SHADOW_PREDICTIONS_DIR, f"{corridor}.jsonl")

    def _candidate_record(prediction: ShadowPrediction) -> dict:
        return {
            "status": prediction.status,
            "ampacity_amps": prediction.ampacity_amps,
            "fallback_used": prediction.fallback_used,
            "fallback_reason": prediction.fallback_reason,
            "model_version": prediction.model_version,
            "input_provenance": prediction.input_provenance,
            "reason": prediction.reason,
            # 2026-10-08: additive bundle-level reporting basis (D-01) --
            # never a top-level mirror field, since it is new, not part of
            # the pre-cutover schema any legacy reader depends on.
            "bundle": prediction.bundle,
        }

    candidate_records = {
        name: _candidate_record(candidates[name]) for name in CANDIDATE_METHOD_NAMES
    }
    mirror = candidate_records["ml_wind_corrected"]

    record = {
        "schema_version": 2,
        "corridor": corridor,
        **timestamps.as_dict(),
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "basis_caveat": (
            "Reanalysis-derived development comparison; this live prediction's "
            "quality is not independently sensor-validated."
        ),
        "candidates": candidate_records,
        "method": "ml_wind_corrected",
        "ampacity_amps": mirror["ampacity_amps"],
        "fallback_used": mirror["fallback_used"],
        "fallback_reason": mirror["fallback_reason"],
        "model_version": mirror["model_version"],
        "input_provenance": mirror["input_provenance"],
    }

    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return path
