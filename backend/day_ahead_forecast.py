"""
The day-ahead cooling forecast: which targets are due, the value, the row (production-pipeline
Phase 8, DAY-01, DAY-02, DAY-05; D-01..D-04, D-13, D-14, D-16).

For each city and each 00/06/12/18 UTC target hour T this module computes ONE value: the
`ml_cooling_corrected` prediction from the Open-Meteo run initialised exactly 24 h before T. The
value is computed only through the frozen shadow functions, called unchanged (D-03):

    shadow.fetch_live_forecast_for_valid_time   the forecast row of the 24 h-old run
    shadow.validate_and_prepare_shadow_row      input validation
    shadow.fetch_live_anchor_observation        the "now" station reading (see `read_anchor`)
    shadow._enrich_city_frame_for_correction    the feature columns
    shadow.CoolingCorrectionShadowMethod        the prediction itself

Each is called under the city's PRODUCTION conductor point (`city_point.production_city_point`,
D-14), with the model from `forecast_conductor_refit.make_headline_loader` pinned to
`DAY_AHEAD_REFIT_VERSION`: it checks the model file's sha256 against its manifest before anything is
unpickled (T-08-01), and records which file it served. For a city whose production conductor equals
the shadow's frozen conductor the value equals the shadow path's own; for the city that differs
(today AUSTIN) it differs only through the final heat balance. The frame's own geometry attribute is
left by the shadow code as the frozen conductor's: it is never read here, `predict` takes the point
as an argument.

No substitute method (D-16): a missing anchor reading, a missing or unpublished weather run, a hash
or load refusal, or a non-finite or non-positive value raises `DayAheadNotIssued` with a short named
reason, and no row exists for that target. Nothing else is ever computed for publication, and no
exception text or provider message is ever placed in a row (OD-6).

The runner process that calls this module lives in a later plan; this module opens no connection of
its own. `insert_row` and `existing_targets` take one.
"""

from __future__ import annotations

import logging

import pandas as pd

import city_point
import config
import day_ahead_contract as contract
import forecast_conductor_refit as fcr
import forecast_shadow_pipeline as shadow
import supabase_store

logger = logging.getLogger(__name__)

# Pinned here, never read from config.RATING_CONFIG_VERSION: that label is also the refit directory
# name only by coincidence of the Phase 7 refit. The next conductor change bumps the label, and the
# loader would then look for a directory that does not exist. Bump this together with a new refit,
# through the normal promotion step (D-13).
DAY_AHEAD_REFIT_VERSION = "v3-powersystems-2026-11-02"

_REASON_LIMIT = 200


class DayAheadNotIssued(Exception):
    """No value is published for this target (D-16). `.reason` names the step and the exception type."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _python_datetime(value):
    """A timezone-aware python datetime (UTC) for a database parameter; None stays None."""
    if value is None:
        return None
    return _utc(value).to_pydatetime()


def _not_issued(step: str, exc: BaseException) -> DayAheadNotIssued:
    """The named, redacted reason for a failed step. Exception text goes through the store's redaction."""
    detail = supabase_store.redact(str(exc), limit=_REASON_LIMIT)
    return DayAheadNotIssued(f"{step}: {type(exc).__name__}: {detail}" if detail else f"{step}: {type(exc).__name__}")


def _step(name: str, function, *args, **kwargs):
    """Run one step; any failure becomes a DayAheadNotIssued naming the step (D-16)."""
    try:
        return function(*args, **kwargs)
    except DayAheadNotIssued:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure is a named no-row reason
        raise _not_issued(name, exc) from exc


# --------------------------------------------------------------------------------------------------
# The serving model (D-13, D-14)
# --------------------------------------------------------------------------------------------------

def refit_cities() -> frozenset:
    """The cities whose production conductor differs from the frozen shadow's (today AUSTIN)."""
    return frozenset(city for city in config.LOCATIONS if fcr.production_differs(city))


def serving_model_path(city: str) -> str:
    """The cooling model file served for `city`: the refit artifact where the conductor differs, else the frozen one."""
    if fcr.production_differs(city):
        directory = fcr.refit_dir(DAY_AHEAD_REFIT_VERSION, fcr.REFIT_ROOT)
        return fcr._artifact_path(directory, city, contract.FORECAST_METHOD)
    return shadow._model_path_for(city, contract.FORECAST_METHOD)


def make_model_loader():
    """The hash-verified headline loader for the serving models. It never calls joblib.load on a mismatch."""
    return fcr.make_headline_loader(
        DAY_AHEAD_REFIT_VERSION, refit_cities(), root=fcr.REFIT_ROOT, frozen_manifest=fcr.FROZEN_MANIFEST,
    )


def served_entry(loader, city: str) -> dict:
    """The loader.served record (path, sha256, source) for the city's cooling model; it must have been loaded."""
    for entry in loader.served:
        if entry["city"] == city and entry["method"] == contract.FORECAST_METHOD:
            return entry
    raise DayAheadNotIssued(f"model: no served {contract.FORECAST_METHOD} entry for {city}")


# --------------------------------------------------------------------------------------------------
# Which targets are due (D-01, D-02, D-04)
# --------------------------------------------------------------------------------------------------

def due_targets(now) -> list:
    """
    The grid targets T with now < T <= now + (24 h - publication lag), earliest first, as UTC
    timestamps. The lag is read from the shadow code (6 h today), so a target becomes issuable at
    T - 18 h and stays issuable until T itself; T equal to now is excluded (strictly future). Every
    one of them can be fetched without tripping the shadow fetch's own decision-time check, and every
    row's weather run is the one initialised exactly 24 h before T.
    """
    now = _utc(now)
    step = pd.Timedelta(hours=contract.GRID_HOURS)
    first = now.ceil(f"{contract.GRID_HOURS}h")
    if first == now:
        first += step
    horizon = now + pd.Timedelta(minutes=contract.HORIZON_MINUTES) - pd.Timedelta(
        hours=shadow._resolve_publication_lag_hours()
    )
    targets = []
    target = first
    while target <= horizon:
        targets.append(target)
        target += step
    return targets


def existing_targets(conn, city: str, now) -> set:
    """The valid_time keys already stored for `city` that are still in the future, as UTC timestamps."""
    rows = conn.execute(
        f"select valid_time from {contract.TABLE} where city = %(city)s and valid_time > %(now)s",
        {"city": city, "now": _python_datetime(now)},
    ).fetchall()
    return {_utc(valid_time) for (valid_time,) in rows}


# --------------------------------------------------------------------------------------------------
# The value (D-03, D-14, D-16)
# --------------------------------------------------------------------------------------------------

def read_anchor(city: str, decision_time) -> pd.Series:
    """
    The "now" station reading, through the shadow's own `fetch_live_anchor_observation`. One reading
    serves every target a run issues for the city. A missing reading is a named no-row reason.
    """
    anchor = _step("anchor", shadow.fetch_live_anchor_observation, city, _utc(decision_time))
    if anchor is None:
        raise DayAheadNotIssued("anchor: no anchor reading")
    return anchor


def compute_value(city: str, valid_time, *, decision_time, anchor, model) -> float:
    """
    The `ml_cooling_corrected` amperes for (city, valid_time), through the unchanged shadow functions
    under the production point. Raises DayAheadNotIssued, naming the step, for any failure and for a
    non-finite or non-positive value. No other method is called to produce a value.
    """
    valid_ts = _utc(valid_time)
    decision = _utc(decision_time)
    if anchor is None:
        raise DayAheadNotIssued("anchor: no anchor reading")
    lat, lon = config.CITY_COORDINATES[city]
    point = _step("point", city_point.production_city_point, city)

    row, _ = _step(
        "forecast", shadow.fetch_live_forecast_for_valid_time,
        city, valid_ts, contract.HORIZON_MINUTES, lat=lat, lon=lon, decision_time=decision,
    )
    frame = _step("validate", shadow.validate_and_prepare_shadow_row, row, city=city)
    frame = _step(
        "enrich", shadow._enrich_city_frame_for_correction,
        frame, anchor=anchor, city=city, valid_time=valid_ts, geometry=point,
    )
    amps = _step("predict", lambda: float(shadow.CoolingCorrectionShadowMethod(model).predict(frame, point)))
    if not supabase_store.finite(amps) or amps <= 0:
        raise DayAheadNotIssued(f"value: the prediction is not a finite positive number ({amps!r})")
    return amps


# --------------------------------------------------------------------------------------------------
# The row and the insert (D-04, D-09)
# --------------------------------------------------------------------------------------------------

def build_row(city: str, valid_time, *, issued_at, amps: float, band, model_entry: dict, anchor,
              run_ctx: dict) -> dict:
    """
    One row with exactly `contract.INSERT_COLUMNS`, in that order. Identity comes from the loader's
    served entry, the band and the rating config; the label is the contract constant. No exception
    text or provider message is ever put in a row.
    """
    point_amps = supabase_store.finite(amps)
    if point_amps is None or point_amps <= 0:
        raise DayAheadNotIssued(f"value: the amperes are not a finite positive number ({amps!r})")
    valid_ts = _utc(valid_time)
    row = {
        "city": city,
        "valid_time": _python_datetime(valid_ts),
        "issued_at": _python_datetime(issued_at),
        "forecast_run_init_time": _python_datetime(valid_ts - pd.Timedelta(minutes=contract.HORIZON_MINUTES)),
        "horizon_minutes": contract.HORIZON_MINUTES,
        "forecast_amps": point_amps,
        "forecast_ci_lower_amps": float(band.lower_amps),
        "forecast_ci_upper_amps": float(band.upper_amps),
        "band_source": band.source,
        "band_n": int(band.n),
        "band_pairs_through": _python_datetime(band.pairs_through),
        "band_artifact_sha256": band.artifact_sha256,
        "forecast_method": contract.FORECAST_METHOD,
        "cooling_model_sha256": model_entry["sha256"],
        "cooling_model_source": model_entry["source"],
        "anchor_observation_time": _python_datetime(anchor["anchor_observation_time"]),
        "anchor_source": str(anchor["anchor_source"]),
        "label": contract.DAY_AHEAD_LABEL,
        "config_version": config.RATING_CONFIG_VERSION,
        "config_fingerprint": supabase_store.rating_config_fingerprint(city),
        "run_id": str(run_ctx["run_id"]),
        "run_attempt": int(run_ctx["run_attempt"]),
        "pipeline_version": str(run_ctx["pipeline_version"]),
        "schema_version": 1,
    }
    if tuple(row) != contract.INSERT_COLUMNS:
        raise ValueError("build_row: the row keys differ from day_ahead_contract.INSERT_COLUMNS")
    return row


# Built once from fixed identifiers (the contract's column names), never from data. First write wins
# (D-04): a key that exists is left exactly as it is, issued_at included.
INSERT_SQL = (
    f"insert into {contract.TABLE} ("
    + ", ".join(contract.INSERT_COLUMNS)
    + ") values ("
    + ", ".join(f"%({column})s" for column in contract.INSERT_COLUMNS)
    + ") on conflict (city, valid_time) do nothing"
)


def insert_row(conn, row: dict) -> bool:
    """Insert one row with bound parameters only. True when a row was inserted, False when the key existed."""
    if tuple(row) != contract.INSERT_COLUMNS:
        raise ValueError("insert_row: the row keys differ from day_ahead_contract.INSERT_COLUMNS")
    cursor = conn.execute(INSERT_SQL, row)
    return cursor.rowcount == 1
