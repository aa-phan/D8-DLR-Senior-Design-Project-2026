"""
Shared core of the per-city 2026-11-24 evaluation tooling (quick task
261013-285): constants, the anti-peeking guard, the HTTP evidence recorder,
archive truth, descriptive metrics, provenance and the report writer.

What this is. Two evaluators share this module: the shadow-log scorer
(`forecast_shadow_score.py`, the LIVE-SYSTEM CHECK) and the reconstructed-frame
port (`forecast_shadow_confirm.py`, the HEADLINE for "which candidate to
ship"). They report separately and are NEVER pooled (amendment decision 9).
The rules come from the v2 confirmation protocol plus the v3 per-city
amendment's owner selections
(`docs/data-science/decisions/confirmation_protocol_v3_per_city.md`,
"Owner selections recorded in review (2026-10-13)").

Truth label. Every number here is
"reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never
sensor-validated" (`TRUTH_LABEL`).

Anti-peeking. No predicted-versus-truth outcome may be computed, read or
printed for any FRESH row (valid_time on or after `FRESH_BASIS_START`) before
2026-11-24T00:00:00Z. `check_guard` enforces this before any network call and
before any FRESH-dated file is read, and it enforces the one-shot rule (a
second FRESH run of the same row source into the same evidence root is refused
even if the first run crashed). The only real-data runs permitted before the
instant are the scorer's `--count-only` (status fields, timestamps and counts;
no truth, no ampacity-derived number) and the port's `--dry-run` (no network).

Pre-registration. The instant, the cutoff and every pre-registered statistical
parameter have defaults here. In a FRESH run, any non-default value needs an
explicit `--override-reason`, which is recorded in report.json and report.md.

This module must not import `forecast_experiment_audit` (the frozen harness
with the 590-row gate). It imports `forecast_shadow_fit_models` only for
`weather_to_arm5_frame`, the one truth-ampacity construction (city_point
geometry); that module's own dependencies are outside this file's control.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import requests

import config
import forecast_shadow_fit_models
import forecast_shadow_pipeline
import open_meteo_provider

# --------------------------------------------------------------------------
# S1. Constants (each one is pinned by a test)
# --------------------------------------------------------------------------

EVALUATION_INSTANT_DEFAULT = pd.Timestamp("2026-11-24T00:00:00Z")
VALID_TIME_CUTOFF_DEFAULT = pd.Timestamp("2026-11-17T00:00:00Z")
MODEL_FREEZE = pd.Timestamp("2026-11-01T00:00:00Z")
# The frozen window ends 2026-09-29 (forecast_experiment_audit.FROZEN_WINDOW_END,
# test-pinned, never imported here); the FRESH basis starts the next day.
FROZEN_WINDOW_END_DATE = "2026-09-29"
FRESH_BASIS_START = pd.Timestamp("2026-09-30T00:00:00Z")
RECON_FETCH_START = "2026-09-28"
RECON_FETCH_END = "2026-11-16"

LEAD_HOURS = 24
SLOT_HOURS = 6
# The half-open interval (11, 17] hours: decision time to valid time.
DECISION_GAP_HOURS = (11, 17)
SCORED_FORECAST_MODEL = "gfs_seamless"
TAIL_RATE_TARGET_ROWS = 590
MDD_TARGET_ROWS = 1575

CANDIDATES = tuple(forecast_shadow_pipeline.CANDIDATE_METHOD_NAMES)
REAL_CANDIDATES = ("ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h")
DEFAULT_CHOICE = "ml_wind_corrected"
FALLBACK_CHOICE = "raw_forecast"
ROW_SOURCES = ("reconstructed_frames", "shadow_logs")
HEADLINE_ROW_SOURCE = "reconstructed_frames"
LIVE_ROW_SOURCE = "shadow_logs"

TRUTH_LABEL = (
    "reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), "
    "never sensor-validated"
)
NOT_MEASURED_STATEMENT = (
    "Calibrated overrating risk (the overrating rate at the nominal 5% target) "
    "and retained capacity were not measured. No 8% ceiling was applied. "
    "Candidates are ranked on point error only, which is a weaker standard than v1."
)
EXPLORATORY_STATEMENT = "exploratory: thresholds not pre-registered in a signed protocol"
OWNER_PENDING = [
    "sign confirmation_protocol_v3_per_city.md; until signed, results are "
    "exploratory (amendment, unsigned-default item 5)"
]

# S2. The fixed headline family (decision 2E). Each entry is an ordered pair
# (A, B); its margin is mean|e_B| - mean|e_A|, so a positive margin means A has
# the lower MAE. Not configurable.
HEADLINE_FAMILY: tuple[tuple[str, str], ...] = (
    ("ml_wind_corrected", "ml_cooling_corrected"),
    ("ml_wind_corrected", "reference_ml_refit_24h"),
    ("ml_cooling_corrected", "reference_ml_refit_24h"),
    ("ml_wind_corrected", "raw_forecast"),
    ("ml_cooling_corrected", "raw_forecast"),
    ("reference_ml_refit_24h", "raw_forecast"),
    ("ml_wind_corrected", "persistence_24h"),
    ("ml_cooling_corrected", "persistence_24h"),
    ("reference_ml_refit_24h", "persistence_24h"),
)
FAMILY_SIZE = len(HEADLINE_FAMILY)

# Pre-registered statistical defaults (S1). Changing any of them in a FRESH run
# needs --override-reason (PD-15).
BLOCK_LENGTHS_SLOTS = (1, 4, 8, 28)
N_RESAMPLES = 10000
SEED = config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE
MIN_PAIRED_ROWS = 8
POWER = 0.8
FAMILY_ALPHA = 0.05
DECISION_MARGIN_AMPS = 5.0
CONSISTENCY_MIN_CITIES = 3

PRE_REGISTERED_PARAM_DEFAULTS: dict = {
    "block_lengths": BLOCK_LENGTHS_SLOTS,
    "n_resamples": N_RESAMPLES,
    "seed": SEED,
    "min_paired_rows": MIN_PAIRED_ROWS,
    "power": POWER,
    "decision_margin_amps": DECISION_MARGIN_AMPS,
    "consistency_min_cities": CONSISTENCY_MIN_CITIES,
}

# S1 VALIDITY_FLAGS: each flag has text, the row sources it applies to, and the
# reason it does not apply elsewhere.
VALIDITY_FLAGS: dict[str, dict] = {
    "V1": {
        "text": "The live correction anchor is a station observation (TCEQ, falling back to "
                "Synoptic) taken 11 to 23 h before valid time; the models were trained with an "
                "archive anchor at exactly valid - 24 h.",
        "applies_to": ["shadow_logs"],
        "not_applicable_reason": "The reconstructed frames use the archive anchor at valid - 24 h, "
                                 "which is the development configuration.",
    },
    "V2": {
        "text": "reference_ml_refit_24h predicts about decision time + 24 h, which is 7 to 13 h "
                "after the logged valid time. Its headline is scored at its own target hour; the "
                "logged-valid_time reading is reported alongside and flagged.",
        "applies_to": ["shadow_logs"],
        "not_applicable_reason": "In the reconstructed frames the reference features sit at the "
                                 "anchor (valid - 24 h), so its target is the valid time by construction.",
    },
    "V3": {
        "text": "The logged persistence_24h is the previous same-model cycle's raw_forecast (an hour "
                "about 11 to 17 h before the scored valid time), not the 24 h persistence of the "
                "development record. It is unavailable on a cold start.",
        "applies_to": ["shadow_logs"],
        "not_applicable_reason": "The port uses the development persistence: archive truth weather "
                                 "24 h earlier, run through IEEE 738.",
    },
    "V4": {
        "text": "Truth is reanalysis shared with the training data, and the four cities share "
                "weather, so a pooled comparison has far fewer effective samples than rows.",
        "applies_to": ["shadow_logs", "reconstructed_frames"],
        "not_applicable_reason": None,
    },
    "V5": {
        "text": "The live underlying weather model must match the one the corrections were trained "
                "on (gfs_seamless). Only rows tagged forecast_model == gfs_seamless are scored.",
        "applies_to": ["shadow_logs"],
        "not_applicable_reason": "The reconstructed frames use GFS Previous-Runs forecasts, the "
                                 "training source.",
    },
    "V6": {
        "text": "Rows without a forecast_model field were logged before the 2026-10-13 fix and "
                "predict the hour before the scored hour; they are excluded and never pooled.",
        "applies_to": ["shadow_logs"],
        "not_applicable_reason": "The reconstructed frames contain no logged rows.",
    },
}

# S7. Comparison flags.
FLAG_V1 = "V1_live_anchor"
FLAG_V2 = "V2_reference_target_hour"
FLAG_V2_LOGGED = "V2_logged_hour_reading_compares_a_different_hour"
FLAG_V3 = "V3_live_persistence_definition"
FLAG_V4 = "V4_reanalysis_truth_shared_weather"

# PD-01..PD-17: id -> (title, default text). Parameters that can change at run
# time are overlaid by `planner_defaults_in_force`.
PLANNER_DEFAULTS: dict[str, dict] = {
    "PD-01": {"title": "port model source", "default": "the 12 frozen per-city artifacts (not a train-only refit)"},
    "PD-02": {"title": "port fetch window", "default": f"{RECON_FETCH_START}..{RECON_FETCH_END}"},
    "PD-03": {"title": "block lengths (six-hourly slots)", "default": list(BLOCK_LENGTHS_SLOTS)},
    "PD-04": {"title": "headline p-value per test", "default": "largest two-sided bootstrap p over both pooled schemes and every runnable block length"},
    "PD-05": {"title": "interval excludes 0 in the ship rule", "default": "Holm rejection at family alpha 0.05 with the margin favouring the candidate"},
    "PD-06": {"title": "pooled statistic", "default": "row-weighted"},
    "PD-07": {"title": "minimum paired rows", "default": MIN_PAIRED_ROWS},
    "PD-08": {"title": "MDD power", "default": POWER},
    "PD-09": {"title": "resampling", "default": f"{N_RESAMPLES} resamples, seed {SEED}"},
    "PD-10": {"title": "ship-rule readings", "default": f"margin {DECISION_MARGIN_AMPS} A, consistency {CONSISTENCY_MIN_CITIES} cities"},
    "PD-11": {"title": "logs: reference own target hour", "default": "decision_time + 24 h rounded to the nearest whole UTC hour (half past rounds up)"},
    "PD-12": {"title": "first-logged", "default": "first eligible line in file order"},
    "PD-13": {"title": "underlying weather model", "default": SCORED_FORECAST_MODEL},
    "PD-14": {"title": "bundle ampacity", "default": "not scored"},
    "PD-15": {"title": "parameter changes", "default": "any non-default value in a FRESH run requires --override-reason"},
    "PD-16": {"title": "freeze check", "default": "artifact commits at or after 2026-11-01T00:00Z are flagged, not refused"},
    "PD-17": {"title": "evidence root", "default": "data/shadow/evaluation"},
}
_PD_PARAM_MAP = {
    "block_lengths": "PD-03", "min_paired_rows": "PD-07", "power": "PD-08",
    "n_resamples": "PD-09", "seed": "PD-09",
    "decision_margin_amps": "PD-10", "consistency_min_cities": "PD-10",
}

EVIDENCE_ROOT_DEFAULT = os.path.join("data", "shadow", "evaluation")
_ARCHIVE_TIMEOUT_S = 60
_TRUTH_REQUIRED_FIELDS = ("air_temp", "wind_speed", "wind_direction", "solar_radiation")


class EvaluationGuardError(RuntimeError):
    """Raised when an evaluation would peek at FRESH outcomes early or run twice."""


class LeakageProbeError(RuntimeError):
    """Raised by the port when a candidate reads truth it must not see."""


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def utcnow() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def utc_now_or(now) -> pd.Timestamp:
    """`now` as a UTC timestamp, or the real clock when None."""
    return utcnow() if now is None else to_utc(now)


def to_utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def iso(value) -> Optional[str]:
    if value is None:
        return None
    return to_utc(value).isoformat()


def _json_default(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    if isinstance(obj, pd.Timedelta):
        return obj.total_seconds()
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    return str(obj)


def dumps(obj, **kwargs) -> str:
    """JSON with deterministic key order and NaN/inf mapped to null."""
    return json.dumps(_clean(obj), default=_json_default, sort_keys=kwargs.pop("sort_keys", True),
                      allow_nan=False, **kwargs)


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return None if not np.isfinite(obj) else float(obj)
    return obj


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def round_half_up_to_hour(value) -> pd.Timestamp:
    """Nearest whole UTC hour, half past rounding up. Never interpolates (PD-11)."""
    return (to_utc(value) + pd.Timedelta(minutes=30)).floor("h")


# --------------------------------------------------------------------------
# Guard (anti-peeking + one-shot)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class GuardConfig:
    evaluation_instant: pd.Timestamp = EVALUATION_INSTANT_DEFAULT
    valid_time_cutoff: pd.Timestamp = VALID_TIME_CUTOFF_DEFAULT
    override_reason: Optional[str] = None


def nondefault_params(params: Optional[dict]) -> dict:
    """The pre-registered parameters that differ from their defaults."""
    if not params:
        return {}
    out = {}
    for key, default in PRE_REGISTERED_PARAM_DEFAULTS.items():
        if key not in params:
            continue
        value = params[key]
        if isinstance(default, tuple):
            value = tuple(int(v) for v in value)
        if value != default:
            out[key] = list(value) if isinstance(value, tuple) else value
    return out


def default_params() -> dict:
    return dict(PRE_REGISTERED_PARAM_DEFAULTS)


def _prior_fresh_runs(evidence_root: str, row_source: str) -> list[str]:
    prior = []
    if not evidence_root or not os.path.isdir(evidence_root):
        return prior
    for name in sorted(os.listdir(evidence_root)):
        marker = os.path.join(evidence_root, name, "run_started.json")
        if not os.path.isfile(marker):
            continue
        try:
            with open(marker, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            # An unreadable marker is treated as a prior run of unknown kind:
            # refusing is the safe direction for a one-shot evaluation.
            prior.append(name + " (unreadable marker)")
            continue
        if data.get("basis") == "FRESH" and data.get("row_source") == row_source:
            prior.append(name)
    return prior


def check_guard(guard: GuardConfig, *, valid_times, row_source: str, now, evidence_root: str,
                nondefault_params: Optional[dict] = None) -> dict:
    """
    Validate that this run may proceed and return the guard record. Called
    BEFORE any network call and before any FRESH-dated file is read.

    Raises:
        ValueError: a cutoff at or after the instant, or a non-default instant /
            cutoff (any basis) or non-default pre-registered parameter (FRESH
            runs, PD-15) without an override reason.
        EvaluationGuardError: a FRESH run before the instant without an
            override, or a second FRESH run of the same row source into the
            same evidence root without an override.
    """
    if row_source not in ROW_SOURCES:
        raise ValueError(f"check_guard: unknown row_source {row_source!r}")
    instant = to_utc(guard.evaluation_instant)
    cutoff = to_utc(guard.valid_time_cutoff)
    now_ts = to_utc(now)
    override = guard.override_reason.strip() if isinstance(guard.override_reason, str) and guard.override_reason.strip() else None
    nd_params = dict(nondefault_params or {})

    if cutoff >= instant:
        raise ValueError(
            f"check_guard: valid_time_cutoff {cutoff.isoformat()} must be strictly before "
            f"the evaluation instant {instant.isoformat()}"
        )

    times = [to_utc(v) for v in valid_times]
    basis = "FRESH" if any(t >= FRESH_BASIS_START for t in times) else "development"

    nd_dates = {}
    if instant != EVALUATION_INSTANT_DEFAULT:
        nd_dates["evaluation_instant"] = instant.isoformat()
    if cutoff != VALID_TIME_CUTOFF_DEFAULT:
        nd_dates["valid_time_cutoff"] = cutoff.isoformat()
    if nd_dates and override is None:
        raise ValueError(
            f"check_guard: non-default pre-registered dates {nd_dates} require --override-reason"
        )
    if basis == "FRESH" and nd_params and override is None:
        raise ValueError(
            f"check_guard: non-default pre-registered parameters {nd_params} in a FRESH run "
            f"require --override-reason (PD-15)"
        )

    prior = _prior_fresh_runs(evidence_root, row_source) if basis == "FRESH" else []
    if basis == "FRESH":
        if now_ts < instant and override is None:
            raise EvaluationGuardError(
                f"refusing to evaluate FRESH rows (valid_time on or after {FRESH_BASIS_START.isoformat()}) "
                f"at {now_ts.isoformat()}: the evaluation instant is {instant.isoformat()}. "
                f"No outcome-based figure for a FRESH row may be produced before then."
            )
        if prior and override is None:
            raise EvaluationGuardError(
                f"refusing a second FRESH run of row source {row_source!r}: prior run(s) {prior} "
                f"already exist under {evidence_root!r} (one-shot evaluation, even if that run crashed). "
                f"Pass --override-reason to override."
            )

    return {
        "evaluation_instant": instant.isoformat(),
        "valid_time_cutoff": cutoff.isoformat(),
        "fresh_basis_start": FRESH_BASIS_START.isoformat(),
        "now_evaluated": now_ts.isoformat(),
        "defaults_used": not nd_dates and not nd_params,
        "nondefault_params": {**nd_dates, **nd_params},
        "override_reason": override,
        "prior_fresh_runs": prior,
        "basis": basis,
        "row_source": row_source,
    }


def new_evidence_dir(evidence_root: str, row_source: str, now, guard_record: dict, config_record: dict) -> str:
    """
    Create `evidence_root/{row_source}_{YYYYmmddTHHMMSSZ}/` and write
    run_started.json (guard record and config) as its first file. Call only
    after `check_guard` passed.
    """
    stamp = to_utc(now).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(evidence_root, f"{row_source}_{stamp}")
    os.makedirs(evidence_root, exist_ok=True)
    os.makedirs(path)  # FileExistsError: two runs in one second are refused, not merged
    marker = {
        "row_source": row_source,
        "basis": guard_record.get("basis"),
        "started_at_utc": to_utc(now).isoformat(),
        "guard": guard_record,
        "config": config_record,
    }
    _atomic_write(os.path.join(path, "run_started.json"), dumps(marker, indent=2))
    return path


def _atomic_write(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


_CACHE_NAME = re.compile(
    r"^anchored_pair_frame_(?P<city>.+?)_(?P<start>\d{4}-\d{2}-\d{2})_(?P<end>\d{4}-\d{2}-\d{2})_lead(?P<lead>\d+)_.*\.csv$"
)


def assert_not_fresh_experiment_cache(path: str, allow_dir: Optional[str] = None) -> None:
    """
    Raise EvaluationGuardError if `path` is an anchored_pair_frame cache file
    whose window ends after the frozen window (a FRESH-truth cache), unless the
    path lies inside `allow_dir` (the current run's own evidence directory).
    """
    match = _CACHE_NAME.match(os.path.basename(str(path)))
    if not match:
        return
    if pd.Timestamp(match.group("end")) <= pd.Timestamp(FROZEN_WINDOW_END_DATE):
        return
    if allow_dir is not None:
        real_dir = os.path.realpath(allow_dir)
        real_path = os.path.realpath(str(path))
        if real_path == real_dir or real_path.startswith(real_dir + os.sep):
            return
    raise EvaluationGuardError(
        f"refusing to open FRESH experiment cache {path!r}: reading it would show FRESH truth"
    )


# --------------------------------------------------------------------------
# HTTP evidence recorder
# --------------------------------------------------------------------------

class HttpRecorder:
    def __init__(self, evidence_dir: str, label: str):
        self.http_dir = os.path.join(evidence_dir, "http")
        self.label = label
        self.records: list[dict] = []

    def _next_index(self) -> int:
        os.makedirs(self.http_dir, exist_ok=True)
        existing = [f for f in os.listdir(self.http_dir) if f.endswith(".meta.json")]
        return len(existing) + 1

    def wrap(self, original):
        def recorded_get(url, params=None, **kwargs):
            started = utcnow().isoformat()
            idx = self._next_index()
            stem = f"{idx:02d}_{self.label}"
            meta = {
                "url": url,
                "params": _clean(dict(params)) if isinstance(params, dict) else params,
                "status_code": None, "date_header": None, "content_type": None,
                "byte_length": None, "sha256": None, "body_file": None,
                "retrieval_started_at_utc": started, "retrieval_completed_at_utc": None,
                "error": None,
            }
            try:
                resp = original(url, params=params, **kwargs) if params is not None else original(url, **kwargs)
            except BaseException as exc:
                meta["retrieval_completed_at_utc"] = utcnow().isoformat()
                meta["error"] = f"{type(exc).__name__}: {exc}"
                self._write_meta(stem, meta)
                raise
            meta["retrieval_completed_at_utc"] = utcnow().isoformat()
            content = getattr(resp, "content", b"")
            if not isinstance(content, (bytes, bytearray)):
                content = str(content).encode("utf-8")
            content = bytes(content)
            headers = getattr(resp, "headers", None) or {}
            meta["status_code"] = getattr(resp, "status_code", None)
            meta["date_header"] = headers.get("Date") if hasattr(headers, "get") else None
            meta["content_type"] = headers.get("Content-Type") if hasattr(headers, "get") else None
            meta["byte_length"] = len(content)
            meta["sha256"] = sha256_bytes(content)
            meta["body_file"] = stem + ".body"
            with open(os.path.join(self.http_dir, stem + ".body"), "wb") as fh:
                fh.write(content)
            self._write_meta(stem, meta)
            return resp
        return recorded_get

    def _write_meta(self, stem: str, meta: dict) -> None:
        path = os.path.join(self.http_dir, stem + ".meta.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(dumps(meta, indent=2))
        self.records.append({**meta, "meta_file": stem + ".meta.json"})


@contextmanager
def record_http(evidence_dir: str, label: str):
    """
    Capture every `requests.get` made inside the context: the verbatim body
    (NN_{label}.body) and a meta file (url, params, status, Date and
    Content-Type headers, byte length, sha256, retrieval start/end timestamps,
    error). Both Open-Meteo providers call `requests.get` through the module
    attribute, so this needs no change to them. The original is always restored.
    """
    recorder = HttpRecorder(evidence_dir, label)
    original = requests.get
    requests.get = recorder.wrap(original)
    try:
        yield recorder
    finally:
        requests.get = original


def collect_evidence(evidence_dir: str) -> list[dict]:
    """All recorded HTTP evidence in an evidence directory (sorted)."""
    http_dir = os.path.join(evidence_dir, "http")
    out = []
    if os.path.isdir(http_dir):
        for name in sorted(os.listdir(http_dir)):
            if name.endswith(".meta.json"):
                with open(os.path.join(http_dir, name), "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
                out.append({
                    "meta_file": name, "body_file": meta.get("body_file"), "url": meta.get("url"),
                    "status_code": meta.get("status_code"), "sha256": meta.get("sha256"),
                    "byte_length": meta.get("byte_length"), "error": meta.get("error"),
                    "retrieval_started_at_utc": meta.get("retrieval_started_at_utc"),
                    "retrieval_completed_at_utc": meta.get("retrieval_completed_at_utc"),
                })
    return out


# --------------------------------------------------------------------------
# Archive truth
# --------------------------------------------------------------------------

def build_archive_request(city: str, start_date: str, end_date: str) -> tuple[str, dict]:
    """The same URL and params `open_meteo_provider.fetch_open_meteo` sends."""
    lat, lon = config.CITY_COORDINATES[city]
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": open_meteo_provider._to_archive_date(start_date),
        "end_date": open_meteo_provider._to_archive_date(end_date),
        "hourly": ",".join(open_meteo_provider.OPEN_METEO_HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }
    return open_meteo_provider.OPEN_METEO_ARCHIVE_BASE, params


def parse_archive_payload(data) -> pd.DataFrame:
    """
    The parse and checks of `fetch_open_meteo` applied to an already-decoded
    payload: same frame, same ValueError types on a missing hourly object,
    missing or short arrays, unit-echo mismatch or out-of-range value.
    """
    hourly = data.get("hourly") if isinstance(data, dict) else None
    if not isinstance(hourly, dict):
        raise ValueError(
            "open_meteo_provider: response is missing a valid 'hourly' "
            f"object, got {type(hourly).__name__}"
        )
    time = hourly.get("time")
    if not isinstance(time, list) or len(time) == 0:
        raise ValueError(
            "open_meteo_provider: response's 'hourly.time' array is "
            f"missing, not a list, or empty (got {time!r})"
        )
    n = len(time)
    for provider_key in open_meteo_provider.HOURLY_TO_PIPELINE:
        if provider_key not in hourly:
            raise ValueError(
                f"open_meteo_provider: response is missing the {provider_key!r} variable array "
                "under 'hourly' -- a missing variable is a failed fetch, never substituted with a null column."
            )
        values = hourly[provider_key]
        if not isinstance(values, list) or len(values) != n:
            got_len = len(values) if isinstance(values, list) else type(values).__name__
            raise ValueError(
                f"open_meteo_provider: {provider_key!r} array length ({got_len}) does not match "
                f"'hourly.time' length ({n}) -- never padded or truncated to fit."
            )
    hourly_units = data.get("hourly_units")
    if isinstance(hourly_units, dict):
        for provider_key, expected_unit in open_meteo_provider.EXPECTED_HOURLY_UNITS.items():
            echoed = hourly_units.get(provider_key)
            if echoed is None:
                continue
            if echoed != expected_unit:
                raise ValueError(
                    f"open_meteo_provider: response echoed unit {echoed!r} for {provider_key!r}, "
                    f"expected {expected_unit!r} -- check the request parameter for a dropped or ignored unit override."
                )
    frame = pd.DataFrame({"datetime_utc": pd.to_datetime(time, utc=True)})
    for provider_key, pipeline_col in open_meteo_provider.HOURLY_TO_PIPELINE.items():
        frame[pipeline_col] = hourly[provider_key]
    open_meteo_provider._range_check(frame)
    return frame


def fetch_archive_truth(city: str, start_date: str, end_date: str, *, evidence_dir: str):
    """
    One `requests.get` to the Archive API inside `record_http`, timeout 60, no
    retry. Any failure is recorded in `meta["error"]` and returns (None, meta).
    """
    url, params = build_archive_request(city, start_date, end_date)
    meta = {"city": city, "url": url, "params": params, "start_date": start_date,
            "end_date": end_date, "error": None, "n_hours": None}
    frame = None
    with record_http(evidence_dir, f"archive_{city}") as recorder:
        try:
            response = requests.get(url, params=params, timeout=_ARCHIVE_TIMEOUT_S)
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                raise ValueError(
                    f"open_meteo_provider: response body could not be parsed as JSON: {exc}"
                ) from exc
            frame = parse_archive_payload(payload)
            meta["n_hours"] = int(len(frame))
        except Exception as exc:  # recorded, never retried
            meta["error"] = f"{type(exc).__name__}: {exc}"
            frame = None
    meta["http_records"] = [
        {k: r.get(k) for k in ("meta_file", "body_file", "status_code", "sha256", "byte_length",
                               "retrieval_started_at_utc", "retrieval_completed_at_utc", "error")}
        for r in recorder.records
    ]
    return frame, meta


def truth_ampacity(weather_frame: pd.DataFrame, city: str):
    """
    Truth ampacity for one city: hours with a null in any of the four required
    weather fields are dropped BEFORE the thermal model runs (never imputed),
    then `forecast_shadow_fit_models.weather_to_arm5_frame` (city_point
    geometry) gives the amps.

    Returns (DataFrame[datetime_utc, truth_amps], dropped_null_hours).
    """
    frame = weather_frame.copy()
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], utc=True)
    numeric = frame[list(_TRUTH_REQUIRED_FIELDS)].apply(pd.to_numeric, errors="coerce")
    bad = numeric.isnull().any(axis=1) | ~np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
    dropped = [ts.isoformat() for ts in frame.loc[bad, "datetime_utc"]]
    clean = frame.loc[~bad].copy()
    for col in _TRUTH_REQUIRED_FIELDS:
        clean[col] = numeric.loc[~bad, col].to_numpy(dtype=float)
    if clean.empty:
        return pd.DataFrame({"datetime_utc": pd.to_datetime([], utc=True), "truth_amps": []}), dropped
    arm5 = forecast_shadow_fit_models.weather_to_arm5_frame(clean, city)
    out = pd.DataFrame({"datetime_utc": arm5["datetime_utc"], "truth_amps": arm5["dlr_amps"].to_numpy(dtype=float)})
    return out, dropped


# --------------------------------------------------------------------------
# Descriptive metrics
# --------------------------------------------------------------------------

DESCRIPTIVE_LABEL = "descriptive; not the calibrated 5%-target rate; not compared with 8%"


def descriptive_metrics(pred, truth) -> dict:
    """error = pred - truth. Positive bias means capacity overstated."""
    pred = np.asarray(pred, dtype=float)
    truth = np.asarray(truth, dtype=float)
    err = pred - truth
    n = int(err.size)
    if n == 0:
        return {"n": 0, "bias": None, "mae": None, "rmse": None, "median_abs_error": None,
                "overprediction_rate": None, "overshoot_mean": None, "overshoot_p95": None,
                "overshoot_max": None, "overprediction_label": DESCRIPTIVE_LABEL}
    over = err[err > 0]
    return {
        "n": n,
        "bias": float(np.mean(err)),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "median_abs_error": float(np.median(np.abs(err))),
        "overprediction_rate": float(np.mean(err > 0)),
        "overshoot_mean": float(np.mean(over)) if over.size else None,
        "overshoot_p95": float(np.percentile(over, 95)) if over.size else None,
        "overshoot_max": float(np.max(over)) if over.size else None,
        "overprediction_label": DESCRIPTIVE_LABEL,
    }


def precision_targets(n: int) -> dict:
    return {
        "n": int(n),
        "tail_rate_target_rows": TAIL_RATE_TARGET_ROWS,
        "tail_rate_target_met": bool(n >= TAIL_RATE_TARGET_ROWS),
        "mdd_target_rows": MDD_TARGET_ROWS,
        "mdd_target_met": bool(n >= MDD_TARGET_ROWS),
    }


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

def _run_git(repo_root: str, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", repo_root, *args], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def artifact_paths(cities) -> list[tuple[str, str, str]]:
    """(method, city, path) for the per-city artifacts, resolved at call time."""
    model_dir = forecast_shadow_pipeline.SHADOW_MODEL_DIR
    return [(m, c, os.path.join(model_dir, f"{m}_{c}.joblib"))
            for c in cities for m in forecast_shadow_fit_models.FIT_METHODS]


def provenance(repo_root: str, cities, source_commit: Optional[str] = None) -> dict:
    sha = _run_git(repo_root, "rev-parse", "HEAD")
    sha = sha.strip() if sha and re.fullmatch(r"[0-9a-f]{40}", sha.strip()) else "unknown"
    porcelain = _run_git(repo_root, "status", "--porcelain")
    dirty = None if porcelain is None else bool(porcelain.strip())

    artifacts = []
    flagged = []
    for method, city, path in artifact_paths(cities):
        digest = sha256_file(path) if os.path.isfile(path) else "missing"
        entry = {"method": method, "city": city, "path": path.replace(os.sep, "/"), "sha256": digest, "commits": []}
        log = _run_git(repo_root, "log", "--format=%H %cI", "--", path)
        if log is None:
            entry["commits"] = "unknown"
        else:
            for line in log.splitlines():
                parts = line.strip().split(" ", 1)
                if len(parts) != 2:
                    continue
                commit, when = parts
                entry["commits"].append({"commit": commit, "committed_at": when})
                try:
                    if to_utc(when) >= MODEL_FREEZE:
                        flagged.append({"artifact": entry["path"], "commit": commit, "committed_at": when})
                except (ValueError, TypeError):
                    pass
        artifacts.append(entry)

    versions = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}
    for mod in ("scipy", "sklearn"):
        try:
            versions[mod] = __import__(mod).__version__
        except ImportError:
            versions[mod] = "unavailable"
    return {
        "git_sha": sha,
        "git_dirty": dirty,
        "logs_source_commit": source_commit,
        "artifacts": artifacts,
        "freeze_check": {
            "model_freeze": MODEL_FREEZE.isoformat(),
            "flagged": flagged,
            "note": "artifact commits dated at or after the freeze are flagged, not refused (PD-16)",
        },
        "versions": versions,
    }


# --------------------------------------------------------------------------
# Report skeleton, planner defaults and rendering
# --------------------------------------------------------------------------

def validity_flags_for(row_source: str) -> list[dict]:
    out = []
    for fid, spec in VALIDITY_FLAGS.items():
        applies = row_source in spec["applies_to"]
        out.append({
            "id": fid, "text": spec["text"], "applies": applies,
            "not_applicable_reason": None if applies else spec["not_applicable_reason"],
        })
    return out


def planner_defaults_in_force(params: Optional[dict] = None) -> dict:
    nd = nondefault_params(params or {})
    out = {}
    for pid, spec in PLANNER_DEFAULTS.items():
        out[pid] = {"title": spec["title"], "default": spec["default"], "value": spec["default"],
                    "non_default": False, "note": "owner may override"}
    for key, value in nd.items():
        pid = _PD_PARAM_MAP.get(key)
        if pid:
            out[pid]["non_default"] = True
            out[pid].setdefault("changed", {})[key] = value
            out[pid]["value"] = out[pid]["changed"]
    return out


def new_report(*, row_source: str, basis: str, protocol_status: str, guard: dict, config_record: dict,
               prov: dict, params: Optional[dict] = None) -> dict:
    return {
        "row_source": row_source,
        "basis": basis,
        "protocol_status": protocol_status,
        "truth_label": TRUTH_LABEL,
        "guard": guard,
        "config": config_record,
        "provenance": prov,
        "sample_size": {},
        "family": None,
        "decision": None,
        "per_city": {},
        "exclusions": {},
        "validity_flags": validity_flags_for(row_source),
        "diagnostics": {},
        "not_measured": NOT_MEASURED_STATEMENT,
        "planner_defaults": planner_defaults_in_force(params),
        "owner_pending": list(OWNER_PENDING),
        "evidence": [],
    }


def _f(x, nd: int = 2) -> str:
    if x is None:
        return "n/a"
    try:
        if isinstance(x, (float, np.floating)) and not np.isfinite(x):
            return "n/a"
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def _source_title(row_source: str) -> str:
    return {"reconstructed_frames": "reconstructed frames (headline source)",
            "shadow_logs": "shadow logs (live-system check)"}.get(row_source, row_source)


def render_header(report: dict) -> str:
    guard = report.get("guard") or {}
    prov = report.get("provenance") or {}
    status = report.get("protocol_status", "unsigned")
    lines = [f"# Per-city shadow evaluation - row source: {_source_title(report['row_source'])}", "",
             f"Truth: {TRUTH_LABEL}", f"Basis: {report.get('basis')}"]
    if report.get("basis") == "development":
        lines += ["", "**DEVELOPMENT DATA - not a confirmation result**", ""]
    lines.append(f"Protocol status: {status}" + (f" ({EXPLORATORY_STATEMENT})" if status != "signed" else ""))
    lines += [
        f"Evaluation instant: {guard.get('evaluation_instant')}",
        f"Valid-time cutoff (strict, valid_time < cutoff): {guard.get('valid_time_cutoff')}",
        f"Now evaluated: {guard.get('now_evaluated')}",
        f"Override: {guard.get('override_reason') or 'none'}",
        f"Non-default pre-registered values: {guard.get('nondefault_params') or 'none'}",
        f"Git SHA: {prov.get('git_sha', 'unknown')} (dirty: {prov.get('git_dirty')})",
    ]
    fc = prov.get("freeze_check") or {}
    flagged = fc.get("flagged") or []
    lines.append("Freeze check: " + ("all artifact commits are before the 2026-11-01 freeze" if not flagged else
                 "FLAGGED artifact commits at or after the freeze: " + ", ".join(
                     f"{x['artifact']}@{x['commit'][:8]}" for x in flagged)))
    return "\n".join(lines) + "\n"


def render_sample_size(report: dict) -> str:
    ss = report.get("sample_size") or {}
    lines = ["## Sample size (read this first)", ""]
    pooled = ss.get("pooled_nominal") or {}
    lines.append(f"Precision targets: about {TAIL_RATE_TARGET_ROWS} rows for tail-rate precision and about "
                 f"{MDD_TARGET_ROWS} rows for a 5 A minimum detectable difference.")
    pt = pooled.get("targets")
    if pt:
        lines.append(f"- Pooled nominal n (max over candidates) = {pt['n']}: ~{TAIL_RATE_TARGET_ROWS} target "
                     f"{'met' if pt['tail_rate_target_met'] else 'not met'}; ~{MDD_TARGET_ROWS} target "
                     f"{'met' if pt['mdd_target_met'] else 'not met'} (nominal, not effective).")
    for city, block in (ss.get("per_city") or {}).items():
        t = block.get("targets") or {}
        ns = ", ".join(f"{c}={n}" for c, n in (block.get("n_scored") or {}).items())
        lines.append(f"- {city}: n scored per candidate: {ns}; ~{TAIL_RATE_TARGET_ROWS} "
                     f"{'met' if t.get('tail_rate_target_met') else 'not met'}; ~{MDD_TARGET_ROWS} "
                     f"{'met' if t.get('mdd_target_met') else 'not met'}.")
    pairs = ss.get("pairs") or []
    if pairs:
        lines += ["", "| pair (A vs B) | n paired (pooled) | n_eff (bootstrap) | n_eff (ACF, per city) | MDD (A) | rows needed for 5 A | ~590 | ~1,575 |",
                  "|---|---|---|---|---|---|---|---|"]
        for p in pairs:
            lines.append(
                f"| {p['a']} vs {p['b']} | {p['n_paired']} | {_f(p.get('n_eff_bootstrap'), 1)} | "
                f"{', '.join(f'{c}:{_f(v, 1)}' for c, v in (p.get('n_eff_acf_by_city') or {}).items())} | "
                f"{_f(p.get('mdd'))} | {p.get('rows_needed_for_5A', 'n/a')} | "
                f"{'met' if p['targets']['tail_rate_target_met'] else 'not met'} | "
                f"{'met' if p['targets']['mdd_target_met'] else 'not met'} |")
    elif not ss.get("per_city"):
        lines.append("- (no scored rows)")
    return "\n".join(lines) + "\n"


def render_family(report: dict) -> str:
    fam = report.get("family")
    lines = ["## Headline family: 9 tests, pooled, city-clustered, Holm at 0.05", ""]
    if not fam:
        return "\n".join(lines + ["(not computed)"]) + "\n"
    lines.append("Margin = mean|e_B| - mean|e_A| in amps, so a positive margin means A has the lower MAE. "
                 "Reanalysis-derived, never sensor-validated.")
    lines += ["", "| A vs B | n | margin (A) | rel. MAE reduction | cities favouring A | headline p | Holm-adj. p | outcome | flags |",
              "|---|---|---|---|---|---|---|---|---|"]
    for c in fam.get("comparisons", []):
        h = c.get("headline") or {}
        lines.append(
            f"| {c['a']} vs {c['b']} | {c.get('n_paired')} | {_f(c.get('point_margin'))} | "
            f"{_f(c.get('relative_mae_reduction'), 3)} | {c.get('cities_favoring_a')} of {c.get('cities_with_data')} | "
            f"{_f(h.get('p_headline'), 4)} | {_f(h.get('p_holm_adjusted'), 4)} | {h.get('outcome')} | "
            f"{', '.join(c.get('flags') or [])} |")
    lines += ["", "Headline intervals (widest 95% and widest Bonferroni (1 - 0.05/9) over both pooled schemes and every runnable block length):", ""]
    for c in fam.get("comparisons", []):
        h = c.get("headline") or {}
        lines.append(f"- {c['a']} vs {c['b']}: 95% [{_f(h.get('ci95_widest', [None, None])[0])}, {_f(h.get('ci95_widest', [None, None])[1])}]; "
                     f"Bonferroni [{_f(h.get('ci_bonferroni_widest', [None, None])[0])}, {_f(h.get('ci_bonferroni_widest', [None, None])[1])}]; "
                     f"block lengths run {h.get('block_lengths_run')}, skipped {h.get('block_lengths_skipped')}")
    return "\n".join(lines) + "\n"


def render_decision(report: dict) -> str:
    dec = report.get("decision")
    label = "headline decision" if report["row_source"] == HEADLINE_ROW_SOURCE else "live-system check"
    lines = [f"## Decision ({label})", ""]
    if not dec:
        return "\n".join(lines + ["(not computed)"]) + "\n"
    for cand, lv in (dec.get("levels") or {}).items():
        lines.append(f"- {cand} vs raw_forecast: **{lv['level']}** (benefit {_f(lv.get('benefit_amps'))} A, "
                     f"Holm rejected: {lv.get('holm_rejected')}, favoured in {lv.get('cities_favoring')} of {lv.get('cities_with_data')} cities)")
    lines.append("")
    for alt, d in (dec.get("alternatives_vs_default") or {}).items():
        lines.append(f"- {alt} vs {DEFAULT_CHOICE}: pooled margin {_f(d.get('margin_over_default_amps'))} A, favoured in "
                     f"{d.get('cities_favoring')} of {d.get('cities_with_data')} cities, consistently better: {d.get('consistently_better')}")
    lines += ["", f"Working choice: {dec.get('working_choice')}",
              f"Default action: ship {(dec.get('action') or {}).get('ship')} ({(dec.get('action') or {}).get('level')})", ""]
    for s in dec.get("statements") or []:
        lines.append(f"- {s}")
    return "\n".join(lines) + "\n"


def render_per_city(report: dict) -> str:
    lines = ["## Per-city descriptive metrics (reanalysis-derived, never sensor-validated)", "",
             "bias = prediction - truth (positive means capacity overstated). "
             f"Over-prediction rate and overshoot are {DESCRIPTIVE_LABEL}.", ""]
    for city, block in (report.get("per_city") or {}).items():
        lines.append(f"### {city}")
        excl = block.get("excluded_by_reason") or {}
        lines.append(f"Rows in scope: {block.get('n_in_scope')}; excluded by reason: {excl if excl else 'none'}")
        lines += ["", "| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |",
                  "|---|---|---|---|---|---|---|---|"]
        for cand, m in (block.get("metrics") or {}).items():
            lines.append(
                f"| {cand} | {m['n']} | {_f(m['bias'])} | {_f(m['mae'])} | {_f(m['rmse'])} | {_f(m['median_abs_error'])} | "
                f"{_f(m['overprediction_rate'], 3)} | {_f(m['overshoot_mean'])} / {_f(m['overshoot_p95'])} / {_f(m['overshoot_max'])} |")
        extra = block.get("reference_logged_hour_reading")
        if extra:
            m = extra
            lines.append(f"| reference_ml_refit_24h (logged valid_time reading; flagged {FLAG_V2_LOGGED}) | {m['n']} | "
                         f"{_f(m['bias'])} | {_f(m['mae'])} | {_f(m['rmse'])} | {_f(m['median_abs_error'])} | "
                         f"{_f(m['overprediction_rate'], 3)} | {_f(m['overshoot_mean'])} / {_f(m['overshoot_p95'])} / {_f(m['overshoot_max'])} |")
        cand_excl = block.get("candidate_exclusions") or {}
        if cand_excl:
            lines += ["", "Candidate-level exclusions: " + "; ".join(f"{c}: {v}" for c, v in cand_excl.items() if v)]
        lines.append("")
    return "\n".join(lines) + "\n"


def render_city_comparisons(report: dict) -> str:
    lines = ["## Per-city comparisons (descriptive, uncorrected)", ""]
    fam = report.get("family")
    if not fam:
        return "\n".join(lines + ["(not computed)"]) + "\n"
    for c in fam.get("comparisons", []):
        lines.append(f"- {c['a']} vs {c['b']}:")
        for city, e in (c.get("per_city") or {}).items():
            iv = e.get("ci95_by_block_length") or {}
            ivs = "; ".join(f"L={L}: [{_f(v[0])}, {_f(v[1])}]" for L, v in iv.items())
            lines.append(f"  - {city}: n={e.get('n_paired')} margin={_f(e.get('point_margin'))} outcome={e.get('outcome')}"
                         f"{' (' + e['reason'] + ')' if e.get('reason') else ''} {ivs} - descriptive, uncorrected")
    return "\n".join(lines) + "\n"


def render_common_tail(report: dict) -> str:
    lines = ["## Validity flags and source-specific diagnostics", ""]
    for f in report.get("validity_flags") or []:
        if f["applies"]:
            lines.append(f"- {f['id']} (applies): {f['text']}")
        else:
            lines.append(f"- {f['id']} (does not apply to this source): {f['not_applicable_reason']}")
    diag = report.get("diagnostics") or {}
    if diag:
        lines += ["", "```json", dumps(diag, indent=1), "```"]
    lines += ["", "## Scope and exclusions", ""]
    lines.append("Scored unit: one (city, valid_time) pair; single-conductor ampacity_amps only (bundle not scored, PD-14). "
                 "Corridor-era rows are never counted. Nothing is imputed, retried or backfilled.")
    excl = report.get("exclusions") or {}
    if excl:
        lines += ["", "```json", dumps(excl, indent=1), "```"]
    lines += ["", "## Not measured", "", report.get("not_measured") or NOT_MEASURED_STATEMENT, ""]
    lines += ["## Planner defaults in force (owner may override)", ""]
    for pid, spec in (report.get("planner_defaults") or {}).items():
        mark = " **NON-DEFAULT**" if spec.get("non_default") else ""
        lines.append(f"- {pid} {spec['title']}: {spec['value']}{mark}")
    lines += ["", "Owner-pending items:", ""] + [f"- {s}" for s in (report.get("owner_pending") or [])]
    lines += ["", "## Evidence files", ""]
    ev = report.get("evidence") or []
    if not ev:
        lines.append("(no HTTP evidence recorded)")
    for e in ev:
        lines.append(f"- {e.get('body_file')}: sha256 {e.get('sha256')}, {e.get('byte_length')} bytes, "
                     f"status {e.get('status_code')}, retrieved {e.get('retrieval_started_at_utc')} .. "
                     f"{e.get('retrieval_completed_at_utc')}{', error ' + str(e['error']) if e.get('error') else ''}")
    return "\n".join(lines) + "\n"


def render_markdown(report: dict) -> str:
    """S6 order: header, sample size, family, decision, per-city, comparisons, flags/diagnostics, scope, not measured, defaults, evidence."""
    return "\n".join([
        render_header(report), render_sample_size(report), render_family(report), render_decision(report),
        render_per_city(report), render_city_comparisons(report), render_common_tail(report),
    ])


def write_report(report: dict, evidence_dir: str) -> dict:
    """Write report.json and report.md via tmp file + os.replace."""
    json_path = os.path.join(evidence_dir, "report.json")
    md_path = os.path.join(evidence_dir, "report.md")
    _atomic_write(json_path, dumps(report, indent=2))
    _atomic_write(md_path, render_markdown(report))
    return {"report_json": json_path, "report_md": md_path}


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
