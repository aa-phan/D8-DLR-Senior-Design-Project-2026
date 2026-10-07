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
from dotenv import load_dotenv

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
            )

        provenance = None
        if raw_candidate.get("per_city_ampacity_amps") is not None or raw_candidate.get("bottleneck_city") is not None:
            provenance = {
                "per_city_ampacity_amps": raw_candidate.get("per_city_ampacity_amps"),
                "bottleneck_city": raw_candidate.get("bottleneck_city"),
            }
        elif isinstance(raw_candidate.get("input_provenance"), dict):
            provenance = raw_candidate.get("input_provenance")

        return ShadowPrediction(
            corridor=corridor, method=self.name,
            ampacity_amps=raw_candidate.get("ampacity_amps"),
            timestamps=None, fallback_used=False, status="ok",
            input_provenance=provenance,
        )


class ReferenceRefit24hShadowMethod:
    """
    Plan 05-02 (D-03/D-04): an HONEST stub. `data/shadow/models/` holds no
    `reference_ml_refit_24h_*.joblib` artifact yet (05-RESEARCH.md,
    confirmed via `git ls-files`) -- this method's one job this plan is to
    exist, be wired into the five-candidate loop, and report
    `status="unavailable"` with a reason naming the missing path, exactly
    like any other missing-input case (D-04), never a fallback
    substitution and never an inline training/refit call (D-09's "no
    silent protocol changes", this plan's own prohibitions). 05-04
    replaces this body with the real predict path once the artifact
    exists, without changing this method's name or its callers'
    expectations of its return shape.
    """

    name = "reference_ml_refit_24h"

    def compute(self, corridor: str) -> "ShadowPrediction":
        try:
            load_correction_model(corridor, self.name)
        except FileNotFoundError as exc:
            return ShadowPrediction(
                corridor=corridor, method=self.name, ampacity_amps=None,
                timestamps=None, fallback_used=False, status="unavailable",
                reason=str(exc),
            )
        # Not reachable in this plan -- no artifact exists yet to load
        # successfully. 05-04 replaces this stub body with the real
        # 24h-refit-MLP predict path once it does.
        raise NotImplementedError(
            f"ReferenceRefit24hShadowMethod.compute({corridor!r}): a "
            f"persisted artifact loaded successfully, but this plan's stub "
            f"has no predict path yet -- 05-04 implements it."
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
