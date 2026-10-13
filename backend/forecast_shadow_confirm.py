"""
Per-city point-metrics port of the frozen FRESH harness on reconstructed
frames: the HEADLINE source for "which candidate to ship" (quick task
261013-285, amendment decision 9). The shadow-log scorer
(`forecast_shadow_score.py`) is the live-system check; the two are reported
separately and NEVER pooled.

What is ported from the frozen harness's FRESH confirmation:
  * FRESH-only rows built at the evaluation instant through
    `forecast_experiment.anchored_pair_frame(city, ..., lead_hours=24)`;
  * the exact 24 h lead (`assert_exact_lead`, hour % 6 == 0);
  * the leakage probe with its positive control (the oracle arm);
  * the five candidate definitions, with the DEVELOPMENT persistence (archive
    truth weather 24 h earlier, run through IEEE 738, so V3 does not apply).

What is NOT ported, and why:
  * the corridor `min()` (decision 4A: per-city only);
  * the train-only refit: PD-01 scores the 12 FROZEN per-city artifacts under
    data/shadow/models/{method}_{CITY}.joblib, which are the objects the
    2026-11-01 freeze is defined over and the objects that ship;
  * the 590-row gate (decision 3A): this module neither calls nor names the
    frozen gate machinery (an AST test pins that);
  * calibrated overrating risk and retained capacity (decision 1C): candidates
    are ranked on point error only, with the 5 A three-level ship rule;
  * the network basis manifest (the HTTP evidence recorder replaces it).

Two correctness points (planner findings F4 and F5):
  * F4. `anchored_pair_frame` computes `truth_dlr_amps` / `anchor_dlr_amps`
    with the corridor geometry (bearing 173.1471 vs 173.15 etc.), while the
    per-city fit and the live collector use `city_point.city_point(city)`.
    Truth, raw_forecast and persistence are therefore recomputed from the
    weather columns with city_point geometry; no `*_dlr_amps` column is read.
  * F5. The frozen FRESH window began 2026-09-30, so the join on the 24 h
    anchor lost the first FRESH day. The fetch window here is
    2026-09-28..2026-11-16 (PD-02), giving 192 scored rows per city
    (2026-09-30T00Z..2026-11-16T18Z, hour % 6 == 0).

Anti-peeking. Nothing here builds a FRESH frame, opens a FRESH cache file or
fetches FRESH truth unless `forecast_shadow_eval_core.check_guard` passed
first (clock at or after 2026-11-24T00:00:00Z, or an explicit override that is
recorded). The frame cache is redirected into this run's evidence directory,
so the real data/experiment FRESH caches are never opened. `--dry-run` makes
no network call and reads no FRESH file.

Operator command (one shot, at or after 2026-11-24T00:00:00Z)::

    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_confirm.py \\
        --evidence-root data/shadow/evaluation --out confirm.json

    # any time, no network, evidence root not created:
    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_confirm.py \\
        --dry-run --out dry_run.json

Truth is reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738),
never sensor-validated.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd

import ampacity_forecast
import city_point
import config
import forecast_experiment
import forecast_shadow_decision as decision
import forecast_shadow_eval_core as core
import forecast_shadow_fit_models
import forecast_shadow_pipeline
import forecast_shadow_score as score_mod
import forecast_shadow_score_stats as stats
import open_meteo_forecast_provider
import open_meteo_provider

ROW_SOURCE = core.HEADLINE_ROW_SOURCE

WIND = forecast_shadow_fit_models.WIND_METHOD
COOLING = forecast_shadow_fit_models.COOLING_METHOD
REFERENCE = forecast_shadow_fit_models.REFERENCE_METHOD
MODEL_METHODS = (WIND, COOLING, REFERENCE)

_WEATHER_FIELDS = ("air_temp", "wind_speed", "wind_direction", "solar_radiation")
_USED_PREFIXES = ("truth_", "fcst_", "anchor_")
_TRUTH_CROSS_CHECK_FIELDS = _WEATHER_FIELDS + ("relative_humidity",)
# Exact equality is required: the frame's truth columns and the recorded
# archive body are the same bytes parsed by the same code.
ARCHIVE_TRUTH_TOLERANCE = 0.0
AMPS_CROSS_CHECK_TOLERANCE = 1e-9

REASON_UNAVAILABLE = "candidate_unavailable"
REASON_FAILED = "candidate_failed"
REASON_REFERENCE_FEATURES = "reference_features_missing"
MODEL_SOURCE_TEXT = (
    "the 12 frozen per-city artifacts (PD-01); not a train-only refit, so the development "
    "(train-only) numbers are not directly comparable"
)


class FrameFetchError(RuntimeError):
    """The city's reconstructed frame could not be fetched or built (recorded, never retried)."""


class ReconstructionError(ValueError):
    """A reconstructed frame failed a structural check (recorded per city)."""


@dataclass(frozen=True)
class ScoredWindow:
    """Half-open window of scored valid times: start <= valid_time < end."""
    start: pd.Timestamp
    end: pd.Timestamp

    def slots(self) -> pd.DatetimeIndex:
        return pd.date_range(self.start, self.end - pd.Timedelta(hours=core.SLOT_HOURS),
                             freq=f"{core.SLOT_HOURS}h")


def default_window(guard_cfg: Optional[core.GuardConfig] = None) -> ScoredWindow:
    cutoff = core.VALID_TIME_CUTOFF_DEFAULT if guard_cfg is None else guard_cfg.valid_time_cutoff
    return ScoredWindow(core.FRESH_BASIS_START, core.to_utc(cutoff))


def _resolve_window(window, guard_cfg: core.GuardConfig) -> ScoredWindow:
    if window is None:
        return default_window(guard_cfg)
    if isinstance(window, ScoredWindow):
        return ScoredWindow(core.to_utc(window.start), core.to_utc(window.end))
    start, end = window
    return ScoredWindow(core.to_utc(start), core.to_utc(end))


# --------------------------------------------------------------------------
# Requests and the production frame provider
# --------------------------------------------------------------------------

def build_previous_runs_request(city: str, start_date: str, end_date: str) -> tuple[str, dict]:
    """The URL and params `open_meteo_forecast_provider.fetch_previous_runs` sends."""
    lat, lon = config.CITY_COORDINATES[city]
    suffix = f"_previous_day{config.FORECAST_EXPERIMENT_PREVIOUS_DAY}"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": open_meteo_provider._to_archive_date(start_date),
        "end_date": open_meteo_provider._to_archive_date(end_date),
        "hourly": ",".join(f"{var}{suffix}" for var in open_meteo_provider.OPEN_METEO_HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "models": open_meteo_forecast_provider.PREVIOUS_RUNS_MODEL_ID,
    }
    return open_meteo_forecast_provider.OPEN_METEO_PREVIOUS_RUNS_BASE, params


def _inside(path: str, directory: str) -> bool:
    real_dir = os.path.realpath(directory)
    real_path = os.path.realpath(path)
    return real_path == real_dir or real_path.startswith(real_dir + os.sep)


def production_frame_provider(city: str, *, evidence_dir: str, window=None):
    """
    Build one city's reconstructed frame through the frozen
    `forecast_experiment.anchored_pair_frame(city, 2026-09-28, 2026-11-16,
    lead_hours=24)`, inside the HTTP evidence recorder and with the frame cache
    redirected into `evidence_dir/frames` (restored in a finally block).

    Refuses any window other than RECON_FETCH_START..RECON_FETCH_END, and
    refuses (before `anchored_pair_frame` is called) if the redirected cache
    path already exists. Returns (frame, archive_weather, evidence_meta), where
    `archive_weather` is the recorded archive body re-parsed with
    `core.parse_archive_payload` (the full hourly truth weather of the fetch
    window).

    Raises:
        ValueError: a window other than the pre-registered fetch window.
        EvaluationGuardError: a pre-existing cache file in the redirected directory.
        FrameFetchError: any failure of the two HTTP fetches or the frame build.
    """
    start, end = (core.RECON_FETCH_START, core.RECON_FETCH_END) if window is None else window
    if (str(start), str(end)) != (core.RECON_FETCH_START, core.RECON_FETCH_END):
        raise ValueError(
            f"production_frame_provider: window {start}..{end} is not the pre-registered fetch window "
            f"{core.RECON_FETCH_START}..{core.RECON_FETCH_END} (PD-02)"
        )
    frames_dir = os.path.join(evidence_dir, "frames")
    original_dir = config.FORECAST_EXPERIMENT_CACHE_DIR
    config.FORECAST_EXPERIMENT_CACHE_DIR = frames_dir
    try:
        cache_path = forecast_experiment._cache_path_for(city, start, end, lead_hours=core.LEAD_HOURS)
        core.assert_not_fresh_experiment_cache(cache_path, allow_dir=evidence_dir)
        if not _inside(cache_path, evidence_dir):
            raise core.EvaluationGuardError(
                f"refusing to build the frame: cache path {cache_path!r} is outside the evidence directory"
            )
        if os.path.exists(cache_path):
            raise core.EvaluationGuardError(
                f"refusing to build the frame: {cache_path!r} already exists in this run's redirected "
                f"cache directory (it would be read instead of fetched)"
            )
        with core.record_http(evidence_dir, city) as recorder:
            try:
                frame = forecast_experiment.anchored_pair_frame(city, start, end, lead_hours=core.LEAD_HOURS)
            except Exception as exc:  # recorded by the recorder, never retried
                raise FrameFetchError(f"{city}: {type(exc).__name__}: {exc}") from exc
    finally:
        config.FORECAST_EXPERIMENT_CACHE_DIR = original_dir

    archive_url = open_meteo_provider.OPEN_METEO_ARCHIVE_BASE
    archive_record = next((r for r in recorder.records
                           if r.get("url") == archive_url and r.get("body_file")), None)
    if archive_record is None:
        raise FrameFetchError(f"{city}: no archive response was recorded for the frame build")
    with open(os.path.join(evidence_dir, "http", archive_record["body_file"]), "rb") as fh:
        payload = json.loads(fh.read().decode("utf-8"))
    archive_weather = core.parse_archive_payload(payload)
    meta = {
        "city": city, "fetch_window": [str(start), str(end)], "cache_path": cache_path,
        "http_records": [{k: r.get(k) for k in ("meta_file", "body_file", "url", "status_code", "sha256",
                                                "byte_length", "retrieval_started_at_utc",
                                                "retrieval_completed_at_utc", "error")}
                         for r in recorder.records],
    }
    return frame, archive_weather, meta


# --------------------------------------------------------------------------
# Frame preparation
# --------------------------------------------------------------------------

def prepare_city_frame(frame: pd.DataFrame, city: str, *, window: Optional[ScoredWindow] = None):
    """
    Mirror `forecast_shadow_fit_models.fit_from_frame`'s preparation with
    city_point geometry: sort, recompute `truth_dlr_amps` from the truth weather
    (F4: no `*_dlr_amps` column is read), tag the city, keep the exact-lead rows
    inside `window` and add the perpendicular-wind correction columns.

    Rows with a null in any weather field a candidate reads are dropped (never
    imputed) and counted; their slots are reported as missing_from_reconstruction.
    Returns (prepared, diagnostics).

    Raises:
        ReconstructionError: duplicate valid times, a non-24 h anchor gap, or an
            anchor inside the artifacts' fit window.
    """
    window = default_window() if window is None else window
    point = city_point.city_point(city)
    work = frame.copy()
    work["datetime_utc"] = pd.to_datetime(work["datetime_utc"], utc=True)
    work["anchor_datetime_utc"] = pd.to_datetime(work["anchor_datetime_utc"], utc=True)
    work = work.sort_values("datetime_utc").reset_index(drop=True)
    if work["datetime_utc"].duplicated().any():
        raise ReconstructionError(f"{city}: the frame has duplicate valid times")

    required = [f"{p}{f}" for p in _USED_PREFIXES for f in _WEATHER_FIELDS]
    missing_cols = [c for c in required if c not in work.columns]
    if missing_cols:
        raise ReconstructionError(f"{city}: the frame lacks required column(s) {missing_cols}")
    numeric = work[required].apply(pd.to_numeric, errors="coerce")
    bad = numeric.isnull().any(axis=1) | ~np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
    work = work.loc[~bad].reset_index(drop=True)
    n_null_rows = int(bad.sum())

    if len(work):
        work["truth_dlr_amps"] = forecast_shadow_fit_models.weather_to_arm5_frame(
            work, city, prefix="truth_")["dlr_amps"].to_numpy(dtype=float)
    else:
        work["truth_dlr_amps"] = pd.Series(dtype=float)
    work["city"] = city

    exact = forecast_experiment.filter_to_exact_lead(work, lead_hours=core.LEAD_HOURS)
    in_window = (exact["datetime_utc"] >= window.start) & (exact["datetime_utc"] < window.end)
    exact = exact.loc[in_window].reset_index(drop=True)
    forecast_experiment.assert_exact_lead(exact, lead_hours=core.LEAD_HOURS)

    fit_end = forecast_shadow_fit_models.train_val_window_end()
    split_start = pd.Timestamp(fit_end, tz="UTC") + pd.Timedelta(days=1)
    min_anchor = exact["anchor_datetime_utc"].min() if len(exact) else None
    if min_anchor is not None and min_anchor < split_start:
        raise ReconstructionError(
            f"{city}: anchor {min_anchor.isoformat()} is inside the artifacts' fit window "
            f"(train_val_window_end {fit_end})"
        )

    prepared = forecast_experiment._add_correction_columns(exact, point) if len(exact) else exact
    expected = window.slots()
    present = pd.DatetimeIndex(prepared["datetime_utc"]) if len(prepared) else pd.DatetimeIndex([], tz="UTC")
    missing = expected.difference(present)
    diagnostics = {
        "n_frame_rows": int(len(frame)),
        "n_rows_dropped_null_weather": n_null_rows,
        "n_expected_slots": int(len(expected)),
        "n_scored_slots": int(len(prepared)),
        "missing_from_reconstruction": [t.isoformat() for t in missing],
        "n_missing_from_reconstruction": int(len(missing)),
        "min_anchor_datetime_utc": None if min_anchor is None else min_anchor.isoformat(),
        "artifact_fit_window_end": fit_end,
        "anchor_after_fit_end": True,
        "window": [window.start.isoformat(), window.end.isoformat()],
    }
    return prepared, diagnostics


# --------------------------------------------------------------------------
# Candidate predictions
# --------------------------------------------------------------------------

def _arm5_from_weather(weather: pd.DataFrame, city: str):
    """Archive weather to the arm-5 frame; null-weather hours are dropped, never imputed."""
    frame = weather.copy()
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], utc=True)
    numeric = frame[list(_WEATHER_FIELDS)].apply(pd.to_numeric, errors="coerce")
    bad = numeric.isnull().any(axis=1) | ~np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
    dropped = [t.isoformat() for t in frame.loc[bad, "datetime_utc"]]
    clean = frame.loc[~bad].copy()
    for col in _WEATHER_FIELDS:
        clean[col] = numeric.loc[~bad, col].to_numpy(dtype=float)
    if clean.empty:
        raise ReconstructionError(f"{city}: the archive weather has no usable hour")
    return forecast_shadow_fit_models.weather_to_arm5_frame(clean, city), dropped


def predict_arm(fn: Callable[[pd.DataFrame], np.ndarray], frame: pd.DataFrame):
    """
    Run one arm over `frame`. If the vectorized call raises ValueError (a
    physically meaningless convective term for some row), retry row by row so
    only the failing rows are lost. Returns (values, failed_mask); failed rows are
    NaN, never imputed.
    """
    n = len(frame)
    try:
        values = np.asarray(fn(frame), dtype=float)
        return values, np.zeros(n, dtype=bool)
    except ValueError:
        values = np.full(n, np.nan)
        failed = np.zeros(n, dtype=bool)
        for i in range(n):
            try:
                values[i] = float(np.asarray(fn(frame.iloc[[i]]), dtype=float)[0])
            except ValueError:
                failed[i] = True
        return values, failed


def _arms(point, models: dict) -> dict:
    """The four non-reference arms as callables of a prepared frame."""
    arms = {
        "raw_forecast": lambda f: forecast_experiment._city_ampacity(
            f["fcst_air_temp"], f["fcst_wind_speed"], f["fcst_wind_direction"], f["fcst_solar_radiation"], point),
        "persistence_24h": lambda f: forecast_experiment._city_ampacity(
            f["anchor_air_temp"], f["anchor_wind_speed"], f["anchor_wind_direction"], f["anchor_solar_radiation"], point),
    }
    if models.get(WIND) is not None:
        arms[WIND] = lambda f: forecast_experiment._wind_corrected_ampacity(models[WIND], f, point)
    if models.get(COOLING) is not None:
        arms[COOLING] = lambda f: forecast_experiment._cooling_corrected_ampacity(models[COOLING], f, point)
    return arms


def candidate_predictions(prepared: pd.DataFrame, archive_weather: pd.DataFrame, city: str, models: dict,
                          *, unavailable: Optional[dict] = None):
    """
    The five candidates and the truth for one city on its prepared rows.

    `models` maps method name to a fitted model (None when its artifact is
    unavailable). Returns (DataFrame indexed by valid_time with `valid_time`,
    `slot`, `anchor_time`, `truth_amps`, the five candidate columns (NaN where not
    scored) and one `<candidate>__excl` reason column each, diagnostics).

    Truth, raw_forecast and persistence come from the weather columns with
    city_point geometry (F4). The reference candidate predicts from the archive
    truth ampacity history at the row's anchor (valid - 24 h), reindexed onto the
    complete hourly grid so row shifts equal hour shifts; a row whose feature
    window touches a missing hour is `reference_features_missing`.

    Raises:
        ReconstructionError: the frame's truth weather differs from the recorded
            archive weather at any shared hour, or a prepared hour is absent
            from the archive weather.
    """
    unavailable = dict(unavailable or {})
    point = city_point.city_point(city)
    n = len(prepared)
    vt = pd.DatetimeIndex(prepared["datetime_utc"]) if n else pd.DatetimeIndex([], tz="UTC")
    out = pd.DataFrame(index=vt)
    out["valid_time"] = vt
    out["slot"] = vt
    out["anchor_time"] = pd.DatetimeIndex(prepared["anchor_datetime_utc"]) if n else pd.DatetimeIndex([], tz="UTC")
    out["truth_amps"] = prepared["truth_dlr_amps"].to_numpy(dtype=float) if n else np.array([], dtype=float)
    diag: dict = {"unavailable_reasons": unavailable}

    # Cross-check against the recorded archive weather (the reconstruction's own truth source).
    weather = archive_weather.copy()
    weather["datetime_utc"] = pd.to_datetime(weather["datetime_utc"], utc=True)
    weather = weather.drop_duplicates("datetime_utc").set_index("datetime_utc")
    max_diff = 0.0
    if n:
        absent = vt.difference(weather.index)
        if len(absent):
            raise ReconstructionError(f"{city}: {len(absent)} prepared hour(s) are absent from the archive weather, "
                                      f"first {absent[0].isoformat()}")
        for field in _TRUTH_CROSS_CHECK_FIELDS:
            col = f"truth_{field}"
            if col not in prepared.columns or field not in weather.columns:
                continue
            a = prepared[col].to_numpy(dtype=float)
            b = weather.loc[vt, field].to_numpy(dtype=float)
            both = np.isfinite(a) & np.isfinite(b)
            if (np.isfinite(a) != np.isfinite(b)).any():
                raise ReconstructionError(f"{city}: {col} and the archive weather disagree on missing hours")
            if both.any():
                max_diff = max(max_diff, float(np.max(np.abs(a[both] - b[both]))))
    if max_diff > ARCHIVE_TRUTH_TOLERANCE:
        raise ReconstructionError(
            f"{city}: the frame's truth weather differs from the recorded archive weather "
            f"(max abs difference {max_diff}); refusing to score"
        )
    arm5, dropped_hours = _arm5_from_weather(archive_weather, city)
    amps_diff = None
    if n:
        archive_amps = arm5.set_index("datetime_utc")["dlr_amps"].reindex(vt).to_numpy(dtype=float)
        finite = np.isfinite(archive_amps)
        amps_diff = float(np.max(np.abs(archive_amps[finite] - out["truth_amps"].to_numpy()[finite]))) if finite.any() else 0.0
        if amps_diff > AMPS_CROSS_CHECK_TOLERANCE:
            raise ReconstructionError(f"{city}: truth ampacity from the frame and from the archive differ by {amps_diff}")
    diag["archive_vs_frame_truth"] = {
        "max_abs_diff_weather": max_diff, "tolerance": ARCHIVE_TRUTH_TOLERANCE,
        "max_abs_diff_truth_amps": amps_diff, "n_hours_compared": int(n),
        "archive_null_hours_dropped": dropped_hours,
    }

    arms = _arms(point, models)
    failed_counts = {}
    for name in core.CANDIDATES:
        out[name] = np.nan
        out[f"{name}__excl"] = None
    for name, fn in arms.items():
        if n == 0:
            continue
        values, failed = predict_arm(fn, prepared)
        out[name] = values
        out.loc[failed, f"{name}__excl"] = REASON_FAILED
        failed_counts[name] = int(failed.sum())
    for method in (WIND, COOLING):
        if models.get(method) is None:
            out[f"{method}__excl"] = REASON_UNAVAILABLE if n else None

    # Reference candidate: features from the archive truth history at the anchor.
    estimator = models.get(REFERENCE)
    ref_gaps: list[str] = []
    if estimator is None:
        out[f"{REFERENCE}__excl"] = REASON_UNAVAILABLE if n else None
    elif n:
        indexed = arm5.set_index("datetime_utc").sort_index()
        grid = pd.date_range(indexed.index.min(), indexed.index.max(), freq="h")
        indexed = indexed.reindex(grid)
        features = ampacity_forecast.build_ml_features(indexed)
        at_anchor = features.reindex(pd.DatetimeIndex(out["anchor_time"]))
        ok = ~at_anchor.isnull().any(axis=1).to_numpy()
        values = np.full(n, np.nan)
        if ok.any():
            values[ok] = np.asarray(estimator.predict(at_anchor.to_numpy(dtype=float)[ok]), dtype=float)
        out[REFERENCE] = values
        out.loc[~ok, f"{REFERENCE}__excl"] = REASON_REFERENCE_FEATURES
        ref_gaps = [t.isoformat() for t in vt[~ok]]
    diag["reference_feature_gaps"] = {"n_rows": len(ref_gaps), "valid_times": ref_gaps}
    diag["candidate_failed_rows"] = failed_counts
    return out, diag


# --------------------------------------------------------------------------
# Leakage probe
# --------------------------------------------------------------------------

def _sabotage_truth(prepared: pd.DataFrame) -> pd.DataFrame:
    """A copy whose truth columns are altered and every `*_dlr_amps` column is NaN."""
    s = prepared.copy()
    s["truth_air_temp"] = s["truth_air_temp"].to_numpy(dtype=float) + 10.0
    s["truth_wind_speed"] = s["truth_wind_speed"].to_numpy(dtype=float) + 5.0
    s["truth_wind_direction"] = (s["truth_wind_direction"].to_numpy(dtype=float) + 90.0) % 360.0
    s["truth_solar_radiation"] = s["truth_solar_radiation"].to_numpy(dtype=float) + 100.0
    for col in list(s.columns):
        if col.endswith("_dlr_amps") or col in ("truth_ampacity", "truth_perp_wind_ms"):
            s[col] = np.nan
    return s


def leakage_probe(prepared: pd.DataFrame, city: str, models: dict, *, extra_arms: Optional[dict] = None) -> dict:
    """
    Recompute raw, persistence, wind and cooling (and any `extra_arms`, a
    test-injection hook) on a copy with sabotaged truth columns and require
    identical output; require the oracle arm (it reads truth wind) to change.

    Raises:
        LeakageProbeError: a genuine candidate changed, or the oracle did not.
    """
    if len(prepared) == 0:
        return {"status": "skipped_no_rows", "passed": True}
    point = city_point.city_point(city)
    sabotaged = _sabotage_truth(prepared)
    arms = {**_arms(point, models), **dict(extra_arms or {})}
    checked, max_diff = [], 0.0
    for name, fn in arms.items():
        base, base_failed = predict_arm(fn, prepared)
        sab, sab_failed = predict_arm(fn, sabotaged)
        same = np.array_equal(base_failed, sab_failed) and np.array_equal(base, sab, equal_nan=True)
        if not same:
            raise core.LeakageProbeError(
                f"leakage probe failed for {city}: candidate {name!r} changed when truth columns were sabotaged"
            )
        checked.append(name)
    oracle = forecast_experiment.NON_FITTED_ARMS[forecast_experiment.ORACLE_ARM_NAME](point)
    o_base = np.asarray(oracle(prepared), dtype=float)
    o_sab = np.asarray(oracle(sabotaged), dtype=float)
    if np.array_equal(o_base, o_sab, equal_nan=True):
        raise core.LeakageProbeError(
            f"leakage probe failed for {city}: the oracle positive control did not change under truth sabotage, "
            f"so the probe has no power"
        )
    max_diff = float(np.nanmax(np.abs(o_base - o_sab)))
    return {
        "status": "passed", "passed": True, "arms_checked": checked,
        "oracle_changed": True, "oracle_max_abs_change_amps": max_diff,
        "sabotage": "truth_air_temp +10, truth_wind_speed +5, truth_wind_direction +90 mod 360, "
                    "truth_solar_radiation +100, every *_dlr_amps column NaN",
    }


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

def load_models(city: str, loader: Callable[[str, str], object]):
    """(models, unavailable). A missing artifact (FileNotFoundError) is candidate_unavailable."""
    models, unavailable = {}, {}
    for method in MODEL_METHODS:
        try:
            models[method] = loader(city, method)
        except FileNotFoundError as exc:
            models[method] = None
            unavailable[method] = str(exc)
    return models, unavailable


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _error_frame(preds: pd.DataFrame) -> pd.DataFrame:
    """Signed errors (prediction - truth), one column per candidate, indexed by valid_time."""
    if preds is None or len(preds) == 0:
        return pd.DataFrame({name: pd.Series(dtype=float) for name in core.CANDIDATES})
    frame = pd.DataFrame({name: preds[name] - preds["truth_amps"] for name in core.CANDIDATES}, index=preds.index)
    frame["slot"] = preds["slot"]
    return frame


def _failed_city_block(city: str, stage: str, error: str) -> dict:
    return {
        "n_in_scope": 0, "n_with_truth": 0, "n_scored": {n: 0 for n in core.CANDIDATES},
        "excluded_by_reason": {f"city_failed:{stage}": 1}, "candidate_exclusions": {},
        "metrics": {n: core.descriptive_metrics([], []) for n in core.CANDIDATES},
        "truth_label": core.TRUTH_LABEL, "failed": {"stage": stage, "error": error},
    }


def _attach_family_and_decision(report: dict, error_frames: dict, params: dict, protocol_status: str) -> dict:
    family = stats.build_family_report(error_frames, row_source=ROW_SOURCE, params=params)
    report["family"] = family
    report["sample_size"]["pairs"] = family["sample_size"]["pairs"]
    report["sample_size"]["targets_met"] = family["sample_size"]["targets_met"]
    report["sample_size"]["nominal_vs_effective"] = (
        "n is nominal; effective sample sizes (ACF per city, bootstrap pooled) are in `pairs` and are smaller")
    report["decision"] = decision.apply_ship_rule(
        family, protocol_status=protocol_status, margin=params["decision_margin_amps"],
        min_cities=params["consistency_min_cities"])
    return report


def run_confirmation(*, cities, guard_cfg: core.GuardConfig, evidence_root: str, protocol_status: str = "unsigned",
                     now=None, params: Optional[dict] = None, frame_provider: Optional[Callable] = None,
                     model_loader: Optional[Callable] = None, window=None, repo_root: Optional[str] = None,
                     extra_probe_arms: Optional[dict] = None) -> dict:
    """
    Order: scope valid times from the window; `check_guard`; refuse a
    development-basis run without an injected `model_loader`; create the
    evidence directory; per city: frame provider, prepare, load models, candidate
    predictions, leakage probe; absolute errors; descriptive metrics; the 9-test
    family; the ship rule; provenance; report.

    `window` is (scored_start, scored_end_exclusive) or a ScoredWindow; the default
    is the FRESH window 2026-09-30T00Z .. the valid-time cutoff. A custom window is
    only for development rehearsals and needs an injected `frame_provider`.
    `frame_provider(city, *, evidence_dir)` returns (frame, archive_weather, meta).
    `model_loader(city, method)` defaults to `load_correction_model` in a FRESH run.
    `extra_probe_arms` is a test hook: extra arms the leakage probe must also clear.

    A per-city failure (fetch, structure, prediction) is recorded and that city
    is excluded and named in the report. EvaluationGuardError and
    LeakageProbeError are never swallowed.
    """
    cities = list(cities)
    bad = [c for c in cities if c not in config.LOCATIONS]
    if bad:
        raise ValueError(f"run_confirmation: unknown cities {bad}; valid: {list(config.LOCATIONS)}")
    params = core.default_params() if params is None else {**core.default_params(), **params}
    now_ts = core.utc_now_or(now)
    win = _resolve_window(window, guard_cfg)
    if frame_provider is None and (win.start, win.end) != (default_window(guard_cfg).start, default_window(guard_cfg).end):
        raise ValueError("run_confirmation: the production frame provider supports only the default window; "
                         "inject a frame_provider for a development window")
    scope_times = list(win.slots())

    nd = core.nondefault_params(params)
    guard_record = core.check_guard(guard_cfg, valid_times=scope_times, row_source=ROW_SOURCE, now=now_ts,
                                    evidence_root=evidence_root, nondefault_params=nd)
    basis = guard_record["basis"]
    if model_loader is None:
        if basis != "FRESH":
            raise ValueError(
                "run_confirmation: the per-city artifacts must not be scored on frozen periods "
                "(runbook 'Fit-window decision'); inject a model_loader for a development-basis run"
            )
        model_loader = forecast_shadow_pipeline.load_correction_model
    provider = frame_provider or production_frame_provider

    config_record = {
        "cities": cities, "protocol_status": protocol_status, "evidence_root": evidence_root,
        "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in params.items()},
        "scored_window": [win.start.isoformat(), win.end.isoformat()],
        "fetch_window": [core.RECON_FETCH_START, core.RECON_FETCH_END],
        "model_source": MODEL_SOURCE_TEXT,
        "frame_provider": "production" if frame_provider is None else "injected",
        "model_loader": "load_correction_model" if model_loader is forecast_shadow_pipeline.load_correction_model else "injected",
    }
    evidence_dir = core.new_evidence_dir(evidence_root, ROW_SOURCE, now_ts, guard_record, config_record)
    root = repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prov = core.provenance(root, cities)
    report = core.new_report(row_source=ROW_SOURCE, basis=basis, protocol_status=protocol_status,
                             guard=guard_record, config_record=config_record, prov=prov, params=params)
    report["scored_window"] = [win.start.isoformat(), win.end.isoformat()]
    report["failed_cities"] = {}

    error_frames: dict = {}
    for city in cities:
        stage = "frame_fetch"
        try:
            frame, archive_weather, fetch_meta = provider(city, evidence_dir=evidence_dir)
            stage = "prepare"
            prepared, prep_diag = prepare_city_frame(frame, city, window=win)
            stage = "models"
            models, unavailable = load_models(city, model_loader)
            stage = "predict"
            preds, pred_diag = candidate_predictions(prepared, archive_weather, city, models, unavailable=unavailable)
            stage = "leakage_probe"
            probe = leakage_probe(prepared, city, models, extra_arms=extra_probe_arms)
        except (FrameFetchError, ValueError, KeyError) as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            stage_name = "frame_fetch_failed" if isinstance(exc, FrameFetchError) else stage
            report["failed_cities"][city] = {"stage": stage_name, "error": error_text}
            error_frames[city] = _error_frame(None)
            report["per_city"][city] = _failed_city_block(city, stage_name, error_text)
            report["exclusions"][city] = {"city_failed": {"stage": stage_name, "error": error_text}}
            report["diagnostics"][city] = {"failed": {"stage": stage_name, "error": error_text}}
            continue

        error_frames[city] = _error_frame(preds)
        metrics, n_scored, cand_excl = {}, {}, {}
        for name in core.CANDIDATES:
            mask = preds[name].notna().to_numpy() if len(preds) else np.array([], dtype=bool)
            metrics[name] = core.descriptive_metrics(preds.loc[mask, name].to_numpy() if len(preds) else [],
                                                     preds.loc[mask, "truth_amps"].to_numpy() if len(preds) else [])
            n_scored[name] = metrics[name]["n"]
            reasons = preds[f"{name}__excl"].dropna().value_counts().to_dict() if len(preds) else {}
            cand_excl[name] = {str(k): int(v) for k, v in reasons.items()}
        n_with_truth = int(len(preds))
        n_missing = prep_diag["n_missing_from_reconstruction"]
        row_excl = {"missing_from_reconstruction": n_missing}
        report["per_city"][city] = {
            "n_in_scope": prep_diag["n_expected_slots"], "n_with_truth": n_with_truth, "n_scored": n_scored,
            "excluded_by_reason": {k: v for k, v in row_excl.items() if v},
            "candidate_exclusions": cand_excl, "metrics": metrics, "truth_label": core.TRUTH_LABEL,
        }
        report["exclusions"][city] = {
            "row_level": row_excl,
            "rows_dropped_null_weather": prep_diag["n_rows_dropped_null_weather"],
            "candidate_level": cand_excl,
            "accounting": {
                "expected_slots_equals_scored_plus_missing": prep_diag["n_expected_slots"] == n_with_truth + n_missing,
                "per_candidate_scored_plus_exclusions_equals_rows": {
                    name: n_with_truth == n_scored[name] + sum(cand_excl[name].values()) for name in core.CANDIDATES},
            },
        }
        report["diagnostics"][city] = {
            "leakage_probe": probe,
            "missing_slots": prep_diag["missing_from_reconstruction"],
            "reference_feature_gaps": pred_diag["reference_feature_gaps"],
            "archive_vs_frame_truth": pred_diag["archive_vs_frame_truth"],
            "unavailable_reasons": pred_diag["unavailable_reasons"],
            "candidate_failed_rows": pred_diag["candidate_failed_rows"],
            "preparation": {k: v for k, v in prep_diag.items() if k != "missing_from_reconstruction"},
            "frame_fetch": fetch_meta,
            "reference_target": "the valid time by construction (features at anchor = valid - 24 h)",
        }

    pooled = {name: int(sum(report["per_city"][c]["n_scored"][name] for c in cities)) for name in core.CANDIDATES}
    report["sample_size"] = {
        "per_city": {c: {"n_in_scope": report["per_city"][c]["n_in_scope"], "n_scored": report["per_city"][c]["n_scored"],
                         "targets": core.precision_targets(max(report["per_city"][c]["n_scored"].values(), default=0))}
                     for c in cities},
        "pooled_nominal": {"label": "nominal, not effective", "n_scored": pooled,
                           "targets": core.pooled_nominal_targets(max(pooled.values(), default=0))},
    }
    report = _attach_family_and_decision(report, error_frames, params, protocol_status)
    report["evidence"] = core.collect_evidence(evidence_dir)
    report["evidence_dir"] = evidence_dir
    report["report_paths"] = core.write_report(report, evidence_dir)
    return report


# --------------------------------------------------------------------------
# Dry run
# --------------------------------------------------------------------------

def dry_run(*, cities, guard_cfg: core.GuardConfig, evidence_root: str, now=None,
            params: Optional[dict] = None, repo_root: Optional[str] = None) -> dict:
    """
    No network, no FRESH read, no directory created. Reports whether the guard
    would refuse now, the planned requests (archive and previous-runs per city),
    the 12 artifact hashes and the freeze check.
    """
    cities = list(cities)
    params = core.default_params() if params is None else {**core.default_params(), **params}
    now_ts = core.utc_now_or(now)
    win = default_window(guard_cfg)
    try:
        core.check_guard(guard_cfg, valid_times=list(win.slots()), row_source=ROW_SOURCE, now=now_ts,
                         evidence_root=evidence_root, nondefault_params=core.nondefault_params(params))
        guard = {"would_refuse": False, "reason": None}
    except (core.EvaluationGuardError, ValueError) as exc:
        guard = {"would_refuse": True, "reason": str(exc)}
    planned = []
    for city in cities:
        url, p = core.build_archive_request(city, core.RECON_FETCH_START, core.RECON_FETCH_END)
        planned.append({"city": city, "label": "archive", "url": url, "params": p})
        url, p = build_previous_runs_request(city, core.RECON_FETCH_START, core.RECON_FETCH_END)
        planned.append({"city": city, "label": "previous_runs", "url": url, "params": p})
    root = repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prov = core.provenance(root, cities)
    return {
        "guard": guard,
        "now_evaluated": now_ts.isoformat(),
        "protocol_status_note": "unsigned runs are exploratory",
        "scored_window": [win.start.isoformat(), win.end.isoformat()],
        "expected_slots_per_city": int(len(win.slots())),
        "planned_requests": planned,
        "artifacts": [{"path": a["path"], "sha256": a["sha256"], "method": a["method"], "city": a["city"]}
                      for a in prov["artifacts"]],
        "freeze_check": prov["freeze_check"],
        "evidence_root": evidence_root,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="forecast_shadow_confirm", description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--cities", nargs="+", default=list(config.LOCATIONS))
    p.add_argument("--dry-run", action="store_true",
                   help="no network, no FRESH read, evidence root not created; prints the plan")
    p.add_argument("--evidence-root", default=core.EVIDENCE_ROOT_DEFAULT)
    p.add_argument("--out", default=None, help="write the dry-run JSON (or a copy of report.json) here")
    p.add_argument("--evaluation-instant", default=None)
    p.add_argument("--valid-time-cutoff", default=None)
    p.add_argument("--override-reason", default=None)
    p.add_argument("--protocol-status", choices=("signed", "unsigned"), default="unsigned")
    # Pre-registered statistical parameters (no --row-gate, no --family-size: decisions 2 and 3).
    p.add_argument("--block-lengths", type=int, nargs="+", default=None)
    p.add_argument("--n-resamples", type=int, default=None)
    p.add_argument("--decision-margin-amps", type=float, default=None)
    p.add_argument("--consistency-min-cities", type=int, default=None)
    p.add_argument("--min-paired-rows", type=int, default=None)
    p.add_argument("--power", type=float, default=None)
    p.add_argument("--seed", type=int, default=None)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    bad = [c for c in args.cities if c not in config.LOCATIONS]
    if bad:
        print(f"error: unknown cities {bad}; valid: {list(config.LOCATIONS)}", file=sys.stderr)
        return 2
    try:
        guard_cfg = score_mod._guard_from_args(args)
        params = score_mod._params_from_args(args)
        if args.dry_run:
            result = dry_run(cities=args.cities, guard_cfg=guard_cfg, evidence_root=args.evidence_root, params=params)
            text = core.dumps(result, indent=2)
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    fh.write(text)
            else:
                print(text)
            return 0
        report = run_confirmation(cities=args.cities, guard_cfg=guard_cfg, evidence_root=args.evidence_root,
                                  protocol_status=args.protocol_status, params=params)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(core.dumps(report, indent=2))
        print(f"evidence directory: {report['evidence_dir']}")
        return 0
    except (core.EvaluationGuardError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except core.LeakageProbeError as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
