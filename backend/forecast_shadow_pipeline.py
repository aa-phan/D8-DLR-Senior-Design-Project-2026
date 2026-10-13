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
either city on development data (see `docs/data-science/decisions/
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

**Per-city, not per-corridor (2026-10-12).** Each city in `config.LOCATIONS`
(AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO) is one independent rating point
(contract: `docs/data-science/decisions/point_scope.md`). Every candidate
computes ONE city's ampacity from that city's own forecast frame (and
anchor) through `city_point.city_point(city)`'s bearing and conductor.
Nothing here reduces across cities.

**Log schema, `schema_version: 3`** -- one JSON line per cycle in
`data/shadow/predictions/{CITY}.jsonl`::

    {
      "schema_version": 3,
      "city": "AUSTIN",
      "initialization_time", "availability_time", "decision_time",
      "valid_time": <ISO-8601>, "horizon_minutes": 1440,
      "forecast_model": <str>,   # NWP model that produced the forecast
                                 # (added 2026-10-13, additive; schema stays 3).
                                 # A row WITHOUT this field is a legacy
                                 # `config.SHADOW_LEGACY_FORECAST_MODEL`
                                 # ("ecmwf_ifs") row; readers must treat a
                                 # missing field that way, per line, forever.
                                 # Rows of different models must never be pooled.
      "logged_at": <ISO-8601>, "basis_caveat": <str>,
      "candidates": {<one entry per CANDIDATE_METHOD_NAMES>: {
          "status": "ok" | "unavailable" | "failed",
          "ampacity_amps": float | null,   # this city's single-conductor value
          "fallback_used": bool, "fallback_reason": str | null,
          "model_version": str | null,
          "input_provenance": dict | null, # anchored candidates carry
                                           # {"anchor_provenance": {"anchor_source",
                                           #  "anchor_station", "anchor_observation_time"}}
          "reason": str | null,
          "bundle": {"status": "ok", "bundle_ampacity_amps": float,
                     "subconductors_per_phase": int, "config_version": str,
                     "rating_basis": str, "reason": null}
                  | {"status": "unavailable", "reason": str, "config_version": str}
      }},
      # six-field top-level mirror of candidates["ml_wind_corrected"]:
      "method", "ampacity_amps", "fallback_used", "fallback_reason",
      "model_version", "input_provenance"
    }

v1 (flat, single method, `corridor` key, no `schema_version`) and v2
(nested `candidates`, `corridor` key) rows exist only in the legacy
corridor-named logs (`AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`).
This module never writes them; `read_city_log_entries` (and so
`Persistence24hShadowMethod`) only ever returns rows whose `schema_version`
is >= 3 AND whose `city` equals the requested city, so a legacy row can
never leak into a per-city result. The single-method demo
(`ShadowPipeline.log_prediction`) writes the flat layout keyed by `city`
with no `schema_version`; per-city readers skip it the same way.
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
import requests
from dotenv import load_dotenv

import ampacity_forecast
import config
import city_point
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


# 2026-10-13: retry policy for the live single-runs forecast fetch. On
# GitHub-hosted runners the 3rd/4th city's request to
# single-runs-api.open-meteo.com repeatedly hit a 60 s read timeout (first two
# cities fine), including from a fresh process per city, while the identical
# request from a developer machine answers in ~0.6 s. A transient stall is
# best met with a quick give-up-and-retry on a FRESH connection, the same
# remedy that fixed the solar-proxy fetch (`_SOLAR_PROXY_FETCH_ATTEMPTS`).
# Each attempt uses a short read timeout (healthy calls take under a second),
# so the worst case per city is ATTEMPTS x TIMEOUT + (ATTEMPTS - 1) x DELAY
# = 3 x 30 + 2 x 20 = 130 s. Only transport failures
# (`requests.exceptions.RequestException`) are retried: an unavailable run
# (`SingleRunUnavailable`) or a malformed/null response is not transient.
_FORECAST_FETCH_ATTEMPTS = 3

# 2026-10-13: how many forecast days the single-run request asks for. The run
# is initialized EXACTLY `horizon` (24 h) before the valid time, so the valid
# hour is init+24h. A single-run response with `forecast_days=1` covers only
# init..init+23h, so with the old value 1 the valid hour was never in the
# frame and the old `frame.index.asof(valid_ts)` lookup silently returned the
# hour BEFORE (init+23h): every forecast-based candidate (`raw_forecast`,
# `ml_wind_corrected`, `ml_cooling_corrected`, and `persistence_24h`, which
# copies `raw_forecast`) predicted the weather one hour earlier than the hour
# it was scored against. 2 days covers init..init+47h. Found 2026-10-13 by a
# read-only check; rows logged before this fix carry that one-hour offset
# and also lack the `forecast_model` field (both changes shipped together).
_FORECAST_FETCH_DAYS = 2
_FORECAST_FETCH_TIMEOUT_S = 30
_FORECAST_FETCH_RETRY_DELAY_S = 20


def fetch_live_forecast_for_valid_time(
    city: str, valid_time, horizon_minutes: int, *, lat: float, lon: float,
    decision_time=None,
) -> tuple[pd.Series, ShadowTimestamps]:
    """
    Retrieve ONE live forecast row whose model run genuinely covers
    `valid_time`, and return it alongside its own `ShadowTimestamps`.

    The model run selected is `valid_time - horizon_minutes` (the run
    whose initialization sits exactly one horizon before the target --
    the run this prediction is ACTUALLY entitled to use if horizon_minutes
    is the real decision-to-valid lead), fetched via `open_meteo_forecast_
    provider.fetch_single_run` under
    `config.SHADOW_LIVE_FORECAST_MODEL` ("gfs_seamless" since 2026-10-13,
    protocol v3 V5/decision 11B; before that the provider's own pinned
    `FORECAST_MODEL_ID` "ecmwf_ifs"). This is the concrete answer to whether live
    retrieval selects a run that covers the requested valid time: it is
    constructed to, by always deriving the run from valid_time and
    horizon_minutes rather than always reusing "the latest run" or a
    fixed lookback regardless of how far out valid_time is.

    `decision_time` (Plan 05-02, D-02): keyword-only, defaults to `None`,
    in which case `decision_time` is computed internally exactly as
    before (`pd.Timestamp.now(tz="UTC")`) -- byte-identical behavior for
    every existing caller. When provided, that exact value is used
    instead of calling `pd.Timestamp.now()`, so one shared `decision_time`
    can be pinned across the forecast and anchor fetches in the same cycle
    (`fetch_shared_city_inputs`) rather than each fetch independently
    computing its own microseconds-apart "now."

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

    frame = None
    for attempt in range(1, _FORECAST_FETCH_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            frame = open_meteo_forecast_provider.fetch_single_run(
                lat, lon, initialization_time, forecast_days=_FORECAST_FETCH_DAYS,
                model=config.SHADOW_LIVE_FORECAST_MODEL,
                timeout=_FORECAST_FETCH_TIMEOUT_S,
            )
            logger.info(
                "fetch_live_forecast_for_valid_time(%r): single-run fetch attempt "
                "%d/%d succeeded in %.1fs",
                city, attempt, _FORECAST_FETCH_ATTEMPTS, time.monotonic() - started,
            )
            break
        except open_meteo_forecast_provider.SingleRunUnavailable as exc:
            raise StaleOrMissingDataError(
                f"fetch_live_forecast_for_valid_time: run {initialization_time} "
                f"unavailable for city {city!r}: {exc}"
            ) from exc
        except requests.exceptions.RequestException as exc:  # transport failure
            logger.info(
                "fetch_live_forecast_for_valid_time(%r): single-run fetch attempt "
                "%d/%d failed after %.1fs (%s: %s)%s",
                city, attempt, _FORECAST_FETCH_ATTEMPTS, time.monotonic() - started,
                type(exc).__name__, exc,
                " -- retrying" if attempt < _FORECAST_FETCH_ATTEMPTS else "",
            )
            if attempt < _FORECAST_FETCH_ATTEMPTS:
                time.sleep(_FORECAST_FETCH_RETRY_DELAY_S)
                continue
            raise StaleOrMissingDataError(
                f"fetch_live_forecast_for_valid_time: retrieval failed for "
                f"city {city!r}, run {initialization_time} after "
                f"{_FORECAST_FETCH_ATTEMPTS} attempt(s): {exc}"
            ) from exc
        except Exception as exc:  # any other failure is not transient
            raise StaleOrMissingDataError(
                f"fetch_live_forecast_for_valid_time: retrieval failed for "
                f"city {city!r}, run {initialization_time}: {exc}"
            ) from exc

    if frame.empty:
        raise StaleOrMissingDataError(
            f"fetch_live_forecast_for_valid_time: empty response for "
            f"city {city!r}, run {initialization_time}"
        )

    frame = frame.set_index("datetime_utc") if "datetime_utc" in frame.columns else frame
    # STRICT lookup (2026-10-13): the row for exactly `valid_ts` or an error.
    # The earlier `frame.index.asof(valid_ts)` quietly fell back to the
    # nearest EARLIER hour when the exact hour was absent, which is how the
    # one-hour offset described at `_FORECAST_FETCH_DAYS` went unnoticed.
    if valid_ts not in frame.index:
        raise StaleOrMissingDataError(
            f"fetch_live_forecast_for_valid_time: run {initialization_time}'s response "
            f"has no row for exactly valid_time {valid_ts} (covers "
            f"{frame.index.min()} .. {frame.index.max()})"
        )
    row = frame.loc[valid_ts]

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
            f"retrieved row for city {city!r}, valid_time {valid_ts}: "
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
    frame: pd.DataFrame, *, city: str, valid_time, decision_time,
) -> pd.DataFrame:
    """
    Enrich a `validate_and_prepare_shadow_row`-prepared frame with the
    live anchor observation and the remaining columns
    `forecast_correction_models._wind_feature_frame` requires:
    `anchor_wind_speed`/`anchor_wind_direction` (from
    `fetch_live_anchor_observation`), `datetime_utc` (set to `valid_time`,
    for the hour-of-day encoding -- matches training's convention of
    `datetime_utc` = the valid time T), and `city` (the per_city
    correction model's grouping column, `forecast_correction_models.
    _city_column`).

    Each city is its own rating point: this attaches that one city's live
    anchor observation and nothing is combined across cities.

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

    anchor = fetch_live_anchor_observation(city, decision_time)

    enriched = frame.copy()
    enriched["anchor_wind_speed"] = anchor["anchor_wind_speed"]
    enriched["anchor_wind_direction"] = anchor["anchor_wind_direction"]
    enriched["datetime_utc"] = valid_time
    enriched["city"] = city
    enriched.attrs["geometry"] = frame.attrs.get("geometry")
    enriched.attrs["anchor_observation_time"] = anchor["anchor_observation_time"].isoformat()
    enriched.attrs["anchor_source"] = anchor["anchor_source"]
    enriched.attrs["anchor_station"] = anchor["anchor_station"]
    return enriched


_REQUIRED_SHADOW_COLUMNS = ("fcst_air_temp", "fcst_wind_speed", "fcst_wind_direction", "fcst_solar_radiation")


def validate_and_prepare_shadow_row(row: pd.Series, *, city: str) -> pd.DataFrame:
    """
    Input validation for one retrieved row: required columns present and
    non-null, units sane (temperature in a physically plausible range,
    wind speed non-negative, solar radiation non-negative), and the
    city's conductor metadata resolvable via `city_point.city_point`
    (raises `KeyError` naming the valid cities if not -- never silently
    proceeds without conductor metadata).

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
        KeyError: if `city` is not in `config.LOCATIONS`.
    """
    geometry = city_point.city_point(city)  # raises KeyError if unknown

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
    Plan 05-02 (D-02): one city's own forecast-fetch outcome and
    anchor-fetch outcome, captured INDEPENDENTLY -- a failed anchor fetch
    does not prevent the forecast fetch from being recorded (and vice
    versa). `forecast_frame`/`anchor` are `None` exactly when the
    corresponding `*_error` is set (a successful fetch always pairs with a
    `None` error, a failed one always pairs with a `None` result).
    """

    city: str
    forecast_frame: Optional[pd.DataFrame]
    forecast_error: Optional[str]
    anchor: Optional[pd.Series]
    anchor_error: Optional[str]


def fetch_shared_city_inputs(
    city: str, *, valid_time, decision_time, horizon_minutes: int,
) -> SharedCityFetchResult:
    """
    Plan 05-02 (D-02): fetch this city's live forecast row and live anchor
    observation EXACTLY ONCE per cycle -- one forecast fetch and one anchor
    fetch -- so every candidate computed from this cycle's result shares
    the exact same forecast row, the exact same anchor observation, and
    the exact same `decision_time`, rather than each candidate making its
    own independent network call.

    The forecast attempt and the anchor attempt are isolated in their own
    try/except; a failure in one never prevents the other from being made.
    A candidate that discovers one of its required inputs is `None` on the
    returned result reports itself `status="unavailable"` (D-04) -- this
    function itself never raises for a fetch failure.
    """
    lat, lon = config.CITY_COORDINATES[city]

    forecast_frame: Optional[pd.DataFrame] = None
    forecast_error: Optional[str] = None
    try:
        row, _ = fetch_live_forecast_for_valid_time(
            city, valid_time, horizon_minutes=horizon_minutes,
            lat=lat, lon=lon, decision_time=decision_time,
        )
        forecast_frame = validate_and_prepare_shadow_row(row, city=city)
    except (StaleOrMissingDataError, ValueError, KeyError) as exc:
        forecast_error = str(exc)

    anchor: Optional[pd.Series] = None
    anchor_error: Optional[str] = None
    try:
        anchor = fetch_live_anchor_observation(city, decision_time)
    except StaleOrMissingDataError as exc:
        anchor_error = str(exc)

    return SharedCityFetchResult(
        city=city, forecast_frame=forecast_frame, forecast_error=forecast_error,
        anchor=anchor, anchor_error=anchor_error,
    )


def _enrich_city_frame_for_correction(
    forecast_frame: pd.DataFrame, *, anchor: pd.Series, city: str, valid_time, geometry,
) -> pd.DataFrame:
    """
    Plan 05-02 (D-01/D-06): a PURE, no-fetch enrichment -- given an
    already-validated forecast frame (from `fetch_shared_city_inputs`'s own
    result, never re-fetched here) and an already-fetched anchor `Series`,
    returns a frame carrying every column
    `forecast_correction_models._wind_feature_frame` AND
    `_cooling_feature_frame` need: `anchor_wind_speed`/`anchor_wind_
    direction`/`anchor_air_temp`, `datetime_utc=valid_time`, `city` (the
    column `forecast_correction_models._city_column` groups `per_city`
    models by), and the two perpendicular-wind columns
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
    enriched["city"] = city

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


def anchor_provenance_for(anchor: pd.Series) -> dict:
    """
    The per-candidate `input_provenance` block for a candidate that used
    this city's live anchor: `{"anchor_provenance": {"anchor_source",
    "anchor_station", "anchor_observation_time"}}`. Visible provider
    fallback (TCEQ -> Synoptic) lives here, distinct from a
    prediction-method fallback.
    """
    observation_time = anchor["anchor_observation_time"]
    return {
        "anchor_provenance": {
            "anchor_source": anchor["anchor_source"],
            "anchor_station": anchor["anchor_station"],
            "anchor_observation_time": (
                observation_time.isoformat()
                if hasattr(observation_time, "isoformat") else observation_time
            ),
        }
    }


# 2026-10-08 ("bundle-level ampacity"): bundle output is a strictly
# additive, separately-labeled reporting basis -- the candidate's own
# single-conductor `ampacity_amps` is never modified by it. Per-city
# (2026-10-12): the city's own single-conductor ampacity is scaled by
# `config.SUBCONDUCTORS_PER_PHASE[city]`; there is no second endpoint and
# no reduction across cities.
def compute_city_bundle_ampacity(city: str, ampacity_amps: Optional[float]) -> dict:
    """
    Scales `city`'s own single-conductor ampacity by
    `config.SUBCONDUCTORS_PER_PHASE[city]` (never by 3 for three phases --
    a subconductor bundle is a PER-PHASE parallel-conductor count, entirely
    unrelated to the three independent phases of a three-phase circuit).

    Returns a dict, always one of two shapes:

    - Unavailable (`ampacity_amps` is `None`, or `city` has no
      `config.SUBCONDUCTORS_PER_PHASE` entry): `{"status": "unavailable",
      "reason": <str>, "config_version": config.BUNDLE_CONFIG_VERSION}`.
      Never raises, never invents a value -- the caller's own candidate
      keeps its existing per-conductor result regardless.
    - Ok: `{"status": "ok", "bundle_ampacity_amps": float,
      "subconductors_per_phase": int, "config_version":
      config.BUNDLE_CONFIG_VERSION, "rating_basis":
      config.BUNDLE_RATING_BASIS, "reason": None}`.
    """
    if ampacity_amps is None:
        return {
            "status": "unavailable",
            "reason": "no ampacity available for this candidate",
            "config_version": config.BUNDLE_CONFIG_VERSION,
        }

    count = config.SUBCONDUCTORS_PER_PHASE.get(city)
    if count is None:
        return {
            "status": "unavailable",
            "reason": f"no configured SUBCONDUCTORS_PER_PHASE entry for city {city!r}",
            "config_version": config.BUNDLE_CONFIG_VERSION,
        }

    return {
        "status": "ok",
        "bundle_ampacity_amps": count * float(ampacity_amps),
        "subconductors_per_phase": count,
        "config_version": config.BUNDLE_CONFIG_VERSION,
        "rating_basis": config.BUNDLE_RATING_BASIS,
        "reason": None,
    }


@dataclass(frozen=True)
class ShadowPrediction:
    """One method's output: the corrected ampacity, the method name, and whether a fallback was used."""

    city: str
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
    # field above (`ampacity_amps`) is NEVER modified by this field's
    # presence -- bundle output is a strictly additive, separately-labeled
    # reporting basis (see `compute_city_bundle_ampacity`'s own docstring). `None` only for
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
        city: Optional[str] = None, valid_time=None, decision_time=None,
    ):
        """
        `city`/`valid_time`/`decision_time`, when all three are
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
        self.city = city
        self.valid_time = valid_time
        self.decision_time = decision_time

    def predict(self, frame: pd.DataFrame, geometry) -> float:
        if self.city is not None and self.valid_time is not None and self.decision_time is not None:
            enriched = attach_wind_correction_inputs(
                frame, city=self.city,
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


def _model_path_for(city: str, method_name: str) -> str:
    return os.path.join(SHADOW_MODEL_DIR, f"{method_name}_{city}.joblib")


def save_correction_model(model, city: str, method_name: str) -> str:
    """Persist a fitted correction model via joblib, mirroring `ampacity_forecast._load_model`'s own convention."""
    import joblib  # lazy -- keeps this module importable without sklearn/joblib installed

    os.makedirs(SHADOW_MODEL_DIR, exist_ok=True)
    path = _model_path_for(city, method_name)
    joblib.dump(model, path)
    return path


def load_correction_model(city: str, method_name: str):
    """
    Load a persisted correction model.

    Raises:
        FileNotFoundError: naming the city, method, expected path, and
            that no training command exists yet for this prototype module
            (fit directly via `forecast_correction_models.fit_wind_correction`/
            `fit_cooling_correction` and call `save_correction_model`).
    """
    path = _model_path_for(city, method_name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"load_correction_model: no persisted {method_name!r} model for "
            f"city {city!r} at {path!r}. Fit one with "
            f"forecast_correction_models.fit_wind_correction/fit_cooling_correction "
            f"and persist it with forecast_shadow_pipeline.save_correction_model."
        )
    import joblib  # lazy

    return joblib.load(path)


def model_version_for(city: str, method_name: str) -> str:
    """
    A version identifier for the persisted model at `_model_path_for`:
    `<method>_<city>@<file mtime ISO-8601>`. Not a content hash --
    cheap and sufficient to tell two log entries apart if the underlying
    file is ever retrained and re-saved, which is all this prototype's
    logging needs it for.
    """
    path = _model_path_for(city, method_name)
    mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    return f"{method_name}_{city}@{mtime.isoformat()}"


# Plan 05-02 (D-05, Pitfall 3): how close a prior logged entry's own
# `valid_time` must land to this cycle's `decision_time` to count as "the"
# 24h-ago anchor. Generous for the twice-daily (not exactly-24h-apart)
# collection cadence -- named here as a module constant, not a magic
# number inline, so the tolerance is visible and changeable in one place.
_PERSISTENCE_VALID_TIME_TOLERANCE = pd.Timedelta(minutes=90)

# Oldest `schema_version` that is keyed by `city` and carries nested
# `candidates` -- everything older is the corridor-era layout (v1 flat,
# v2 corridor-keyed) and is never returned to a per-city reader.
_PER_CITY_SCHEMA_VERSION = 3


def read_city_log_entries(city: str) -> list[dict]:
    """
    Every usable schema_version-3 entry in `data/shadow/predictions/
    {CITY}.jsonl`, in file order. A usable entry is a JSON object whose
    integer `schema_version` is >= 3 and whose `city` equals `city`.

    Legacy and unreadable rows are SKIPPED, never raised on and never
    returned (this reader must never crash the collector, and a
    corridor-era row must never be mixed into a per-city result): a
    malformed line, a non-object line, a v1 flat row (no `schema_version`,
    or `< 2`), a v2 corridor row (`corridor` key, no `city`), or a row
    keyed by a different city. One log line per call names how many rows
    were skipped for each reason. A missing file returns `[]`.
    """
    path = os.path.join(SHADOW_PREDICTIONS_DIR, f"{city}.jsonl")
    if not os.path.exists(path):
        return []

    entries: list[dict] = []
    skipped = {"malformed": 0, "legacy_v1_flat": 0, "legacy_v2_corridor": 0, "other_city_or_schema": 0}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                skipped["malformed"] += 1
                continue
            if not isinstance(entry, dict):
                skipped["malformed"] += 1
                continue
            version = entry.get("schema_version", 1)
            if isinstance(version, bool) or not isinstance(version, int):
                skipped["malformed"] += 1
                continue
            if version < 2:
                skipped["legacy_v1_flat"] += 1
                continue
            if version < _PER_CITY_SCHEMA_VERSION or ("city" not in entry and "corridor" in entry):
                skipped["legacy_v2_corridor"] += 1
                continue
            if entry.get("city") != city:
                skipped["other_city_or_schema"] += 1
                continue
            entries.append(entry)

    if any(skipped.values()):
        logger.info(
            "read_city_log_entries(%r): skipped non-per-city rows in %s: %s",
            city, path, {k: v for k, v in skipped.items() if v},
        )
    return entries


def entry_forecast_model(entry) -> str:
    """
    The NWP model that produced a logged v3 row. A row without a
    `forecast_model` field (everything logged before 2026-10-13) is a legacy
    `config.SHADOW_LEGACY_FORECAST_MODEL` row. Applied per line, forever.
    """
    model = entry.get("forecast_model") if isinstance(entry, dict) else None
    if isinstance(model, str) and model:
        return model
    return config.SHADOW_LEGACY_FORECAST_MODEL


class Persistence24hShadowMethod:
    """
    Plan 05-02 (D-05): the live, decision-time-available form of
    `persistence_24h` -- reads THIS collector's own prior logged entry
    for the same city (`read_city_log_entries`), never a reanalysis/
    archive backfill. Unlike `forecast_shadow_healthcheck._last_entry`
    (which correctly wants the positionally-LAST line for its own
    different purpose, freshness), this method must find the entry whose
    own `valid_time` is closest to `this_cycle_decision_time` -- at the
    twice-daily cadence, the immediately-preceding entry's `valid_time`
    is only ~12h old, not 24h (05-RESEARCH.md Pitfall 3).

    Reads the entry's own `candidates.raw_forecast` sub-object (not
    `ml_wind_corrected`'s) -- see 05-02-PLAN.md's objective for why
    `raw_forecast` is the least-processed, least-correction-model-
    derivative of the five candidates and therefore the right baseline
    anchor for a model-independent persistence arm.
    """

    name = "persistence_24h"

    def compute(
        self, city: str, this_cycle_decision_time, forecast_model: Optional[str] = None,
    ) -> "ShadowPrediction":
        # 2026-10-13 (V5/decision 11B): only reuse a prior entry produced by the
        # SAME NWP model as this cycle (missing field = legacy ecmwf_ifs), so
        # persistence never mixes an ecmwf-era forecast with a gfs-era one.
        current_model = forecast_model or config.SHADOW_LIVE_FORECAST_MODEL
        other_model_seen = False
        decision_ts = pd.Timestamp(this_cycle_decision_time)
        if decision_ts.tzinfo is None:
            decision_ts = decision_ts.tz_localize("UTC")

        best_entry: Optional[dict] = None
        best_delta: Optional[pd.Timedelta] = None

        for entry in read_city_log_entries(city):
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
            if entry_forecast_model(entry) != current_model:
                if delta <= _PERSISTENCE_VALID_TIME_TOLERANCE:
                    other_model_seen = True
                continue
            if delta <= _PERSISTENCE_VALID_TIME_TOLERANCE and (
                best_delta is None or delta < best_delta
            ):
                best_entry = entry
                best_delta = delta

        if best_entry is None:
            return ShadowPrediction(
                city=city, method=self.name, ampacity_amps=None,
                timestamps=None, fallback_used=False, status="unavailable",
                reason=(
                    "no prior entry within tolerance of decision_time "
                    f"{decision_ts.isoformat()} produced by forecast model "
                    f"{current_model!r} (cold start, or a gap in this city's "
                    "collection history"
                    + (
                        "; a prior entry exists within tolerance but was produced "
                        "by a different forecast model and is deliberately not "
                        "reused -- after the 2026-10-13 switch to gfs_seamless, "
                        "persistence is unavailable until a gfs_seamless entry "
                        "falls within tolerance"
                        if other_model_seen else ""
                    )
                    + ")"
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
                city=city, method=self.name, ampacity_amps=None,
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

        provenance = raw_candidate.get("input_provenance")
        if not isinstance(provenance, dict):
            provenance = None

        # 2026-10-08 ("bundle-level ampacity"): D-05's own decision-time
        # discipline, extended to bundle output -- persistence must persist
        # the DECISION-TIME bundle rating the matched prior entry's own
        # raw_forecast candidate already computed, never re-derive one now
        # under TODAY's bundle config (which could silently diverge from
        # what was true back then). A matched entry carrying no "bundle"
        # key is unavailable, never backfilled/invented.
        matched_bundle = raw_candidate.get("bundle")
        if isinstance(matched_bundle, dict):
            bundle = dict(matched_bundle)
        else:
            bundle = {
                "status": "unavailable",
                "reason": "the matched prior entry carries no 'bundle' key",
                "config_version": config.BUNDLE_CONFIG_VERSION,
            }

        return ShadowPrediction(
            city=city, method=self.name,
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
# function is called once per city (4x per collector run), and the
# scheduled workflow budgets 30 minutes for the ENTIRE four-city cycle --
# a worse-case 3-attempt retry chain here would eat a large share of it.
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
    city: str, lat: float, lon: float,
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
                    "fetch_live_truth_proxy_series(%r): solar-proxy fetch "
                    "attempt %d/%d failed (%s) -- retrying",
                    city, attempt + 1, _SOLAR_PROXY_FETCH_ATTEMPTS, exc,
                )
                time.sleep(_SOLAR_PROXY_RETRY_DELAY_S)
    if frame is None:
        raise StaleOrMissingDataError(
            f"fetch_live_truth_proxy_series: city "
            f"{city!r}: solar-proxy (Open-Meteo historical forecast) window "
            f"fetch failed after {_SOLAR_PROXY_FETCH_ATTEMPTS} attempt(s): {last_exc}"
        ) from last_exc

    values = []
    for target_ts in target_times:
        row = _select_hour_row(frame, target_ts, _TRUTH_PROXY_SOLAR_HOUR_TOLERANCE)
        if row is None:
            raise StaleOrMissingDataError(
                f"fetch_live_truth_proxy_series: city "
                f"{city!r}: no usable Open-Meteo historical-forecast solar "
                f"row within {_TRUTH_PROXY_SOLAR_HOUR_TOLERANCE} of required "
                f"hour {target_ts.isoformat()}"
            )
        value = row.get("solar_radiation")
        if pd.isnull(value):
            raise StaleOrMissingDataError(
                f"fetch_live_truth_proxy_series: city "
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
    city: str, cams_id: str,
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
    never a single window-wide summary, since a real window can be
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
            f"fetch_live_truth_proxy_series: city "
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
            "fetch_live_truth_proxy_series(%r): %d gap hour(s) at TCEQ CAMS "
            "%r -- retrying those hours against Synoptic station %r",
            city, len(gap_reasons), cams_id, synoptic_station,
        )
        try:
            synoptic_frame = weather_provider.fetch_weather(
                [synoptic_station], window_start.isoformat(), anchor_ts.isoformat(),
                provider="synoptic",
            )
        except Exception as exc:
            logger.info(
                "fetch_live_truth_proxy_series(%r): Synoptic retry fetch "
                "raised (%s) -- gap hour(s) remain unresolved", city, exc,
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
            f"fetch_live_truth_proxy_series: city {city!r}: "
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
    city: str, anchor_time, *, lookback_hours: float = None,
):
    """
    Plan 05-04 (D-05's decision-time discipline, generalized for arm 5's
    own lagged/rolling feature needs): build a 7-row, hourly, per-city
    TRUTH-PROXY series -- `anchor_time - lookback_hours` through
    `anchor_time` inclusive -- from near-real-time station observations,
    shaped like the per-city truth frame `forecast_shadow_fit_reference_
    refit` fits on (`datetime_utc`, `dlr_amps`, `air_temp`, `wind_speed`,
    `solar_radiation`) so it can be fed straight into `ampacity_forecast.
    build_ml_features` -- the SAME feature builder the offline fit
    (`forecast_training.build_training_matrix`) already calls.

    Fetches ONE window of `provider="tceq"` station observations for
    `city` spanning `[anchor_time - lookback_hours, anchor_time]`, then
    selects, for each of the 7 target hourly timestamps, the closest row
    within `_TRUTH_PROXY_HOUR_TOLERANCE` (20 minutes). 2026-10-08: a
    missing/null hour no longer raises immediately -- `_fetch_station_
    hours` collects every such gap hour first, then makes ONE explicit
    retry fetch against this city's `config.SYNOPTIC_FALLBACK_STATIONS`
    entry and re-checks only those gap hours against it (the same
    explicit-row-level-retry pattern `fetch_live_anchor_observation`
    already uses for its own single-row lookup, since `fetch_weather`'s
    own `fallback=True` default only fires on a raised exception/empty
    response, never on a mechanically successful response whose one
    specific row is unusable -- TCEQ's own trailing not-yet-reported-hour
    case). Only a gap hour still unusable after that retry raises
    `StaleOrMissingDataError`, naming the hour and BOTH providers' own
    specific failure reasons. Never interpolates, pads, or backfills a
    missing hour at either provider (D-04/T-05-04-01).

    The city's own hourly ampacity (`dlr_amps`) is computed via the SAME
    `thermal_model.perpendicular_wind` + `thermal_model.ieee738_ampacity`
    chain every other method in this module uses, against
    `city_point.city_point(city)`'s own bearing/conductor. It is that
    city's value -- nothing is reduced across cities.

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
        `{"station_provenance": {"sources": [...], "fallback_hours":
        [...]}, "solar_source": "open_meteo_historical_forecast"}` --
        `sources` is a 7-element list of `"tceq"`/`"synoptic"` aligned to
        the series' own rows, and `fallback_hours` names (as ISO-8601
        strings) exactly which hours, if any, came from Synoptic rather
        than TCEQ -- never a single fallback flag, since one window can
        be genuinely mixed.

    Raises:
        StaleOrMissingDataError: on any window-fetch failure, or any
            required hour still unusable after the per-hour Synoptic
            retry, from either the station or the solar-proxy source.
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

    point = city_point.city_point(city)

    cams_id = config.TCEQ_STATIONS.get(city)
    if cams_id is None:
        raise StaleOrMissingDataError(
            f"fetch_live_truth_proxy_series: no known TCEQ CAMS site for city {city!r}"
        )

    fields, sources = _fetch_station_hours(
        city, cams_id, window_start, anchor_ts, target_times,
    )
    station_provenance = {
        "sources": sources,
        "fallback_hours": [
            target_times[i].isoformat()
            for i, source in enumerate(sources) if source == "synoptic"
        ],
    }

    lat, lon = config.CITY_COORDINATES[city]
    fields["solar_radiation"] = _fetch_solar_proxy_hours(
        city, lat, lon, window_start, anchor_ts, target_times,
    )

    perp = thermal_model.perpendicular_wind(
        np.array(fields["wind_speed"], dtype=float),
        np.array(fields["wind_direction"], dtype=float),
        point.bearing_deg,
    )
    dlr_amps = np.asarray(
        thermal_model.ieee738_ampacity(
            np.array(fields["air_temp"], dtype=float), perp,
            np.array(fields["solar_radiation"], dtype=float), point.conductor,
        ),
        dtype=float,
    )

    series = pd.DataFrame({
        "datetime_utc": target_times,
        "dlr_amps": dlr_amps,
        "air_temp": np.array(fields["air_temp"], dtype=float),
        "wind_speed": np.array(fields["wind_speed"], dtype=float),
        "solar_radiation": np.array(fields["solar_radiation"], dtype=float),
    }).sort_values("datetime_utc").reset_index(drop=True)

    provenance = {
        "station_provenance": station_provenance,
        "solar_source": "open_meteo_historical_forecast",
    }
    return series, provenance


class ReferenceRefit24hShadowMethod:
    """
    Plan 05-04 (D-03/D-04): the real predict path, replacing 05-02's
    honest `status="unavailable"` stub once a persisted arm-5 MLP artifact
    exists for the city (`backend/forecast_shadow_fit_reference_refit.py`,
    one artifact per city, fit on that city's OWN ampacity -- not a
    minimum). Loads the persisted estimator via `load_correction_model`
    (never fits/retrains it -- D-09, T-05-04-04), builds its live feature
    row from `fetch_live_truth_proxy_series`'s 7-hour truth-proxy window
    via `ampacity_forecast.build_ml_features` (the SAME feature builder
    the offline fit used), and predicts from the LAST row (the one
    anchored at `anchor_time`, the only row whose lag/rolling features
    are fully determined).

    A missing per-city artifact (the state until each city is refit) is
    `status="unavailable"` with the `FileNotFoundError`'s own named
    reason -- never a crash.
    """

    name = "reference_ml_refit_24h"

    def compute(self, city: str, anchor_time) -> "ShadowPrediction":
        try:
            estimator = load_correction_model(city, self.name)
        except FileNotFoundError as exc:
            return ShadowPrediction(
                city=city, method=self.name, ampacity_amps=None,
                timestamps=None, fallback_used=False, status="unavailable",
                reason=str(exc), bundle=compute_city_bundle_ampacity(city, None),
            )

        try:
            truth_proxy_series, truth_provenance = fetch_live_truth_proxy_series(city, anchor_time)
        except StaleOrMissingDataError as exc:
            return ShadowPrediction(
                city=city, method=self.name, ampacity_amps=None,
                timestamps=None, fallback_used=False, status="unavailable",
                reason=str(exc), bundle=compute_city_bundle_ampacity(city, None),
            )

        indexed = truth_proxy_series.set_index("datetime_utc").sort_index()
        features = ampacity_forecast.build_ml_features(indexed)
        last_row = features.iloc[[-1]]

        if bool(last_row.isnull().to_numpy().any()):
            # Structurally should be impossible given fetch_live_truth_proxy_
            # series's own per-hour validation above -- asserted, not merely
            # trusted, per this plan's own <behavior> spec.
            raise AssertionError(
                f"ReferenceRefit24hShadowMethod.compute({city!r}): the "
                f"live feature row built from a validated 7-hour truth-proxy "
                f"window still carries a null value -- refusing to predict "
                f"from it: {last_row.to_dict(orient='records')}"
            )

        prediction = float(np.asarray(estimator.predict(last_row.to_numpy(dtype=float)))[0])

        provenance = {
            "truth_proxy_window_start": truth_proxy_series["datetime_utc"].iloc[0].isoformat(),
            "truth_proxy_window_end": truth_proxy_series["datetime_utc"].iloc[-1].isoformat(),
            **truth_provenance,
        }
        return ShadowPrediction(
            city=city, method=self.name, ampacity_amps=prediction,
            timestamps=None, fallback_used=False, status="ok",
            model_version=model_version_for(city, self.name),
            input_provenance=provenance,
            bundle=compute_city_bundle_ampacity(city, prediction),
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

# The three candidates computed from the cycle's shared forecast frame
# (`fetch_shared_city_inputs`); `persistence_24h` and
# `reference_ml_refit_24h` are not -- one reads this collector's own prior
# log for the city, the other loads an artifact and fetches its own
# truth-proxy window.
FRAME_BASED_METHOD_NAMES: tuple[str, ...] = (
    "ml_wind_corrected", "ml_cooling_corrected", "raw_forecast",
)


class ShadowPipeline:
    """
    Ties retrieval -> validation -> correction -> logging -> fallback
    together behind one call. Never invoked by production code.
    """

    def __init__(self, city: str, primary_method: CorrectionMethod, *, fallback_method: Optional[CorrectionMethod] = None):
        self.city = city
        self.primary_method = primary_method
        self.fallback_method = fallback_method or RawForecastShadowMethod()
        self.geometry = city_point.city_point(city)

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
                city=self.city, method=self.primary_method.name,
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
                city=self.city, method=self.fallback_method.name,
                ampacity_amps=amps, timestamps=timestamps, fallback_used=True,
                fallback_reason=str(exc),
            )

    def log_prediction(self, prediction: ShadowPrediction) -> str:
        """
        Append one prediction record as a JSON line under
        `data/shadow/predictions/<CITY>.jsonl` (git-ignored, same
        generated-evidence convention as every other report this phase
        has produced under `data/`). Returns the path written to.
        """
        os.makedirs(SHADOW_PREDICTIONS_DIR, exist_ok=True)
        path = os.path.join(SHADOW_PREDICTIONS_DIR, f"{self.city}.jsonl")
        record = {
            "city": prediction.city,
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
    city: str, candidates: dict, timestamps: ShadowTimestamps,
    forecast_model: Optional[str] = None,
) -> str:
    """
    Plan 05-02 (D-06; schema_version 3 since 2026-10-12, keyed by `city` --
    see the module docstring for the full record shape):
    writes exactly ONE JSON line per cycle to the SAME `data/shadow/
    predictions/<CITY>.jsonl` path `ShadowPipeline.log_prediction`
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
    path = os.path.join(SHADOW_PREDICTIONS_DIR, f"{city}.jsonl")

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
        "schema_version": 3,
        "city": city,
        **timestamps.as_dict(),
        "forecast_model": forecast_model or config.SHADOW_LIVE_FORECAST_MODEL,
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
