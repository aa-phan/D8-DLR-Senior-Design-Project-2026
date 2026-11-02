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
    are ranked on point error only, with the signed protocol-v4 ship rule
    (`forecast_shadow_decision_v4`: 2% of mean truth ampacity as the bar, ABLATION
    and TEST vetoes, a single pick or no pick);
  * the network basis manifest (the HTTP evidence recorder replaces it).

Two correctness points (planner findings F4 and F5):
  * F4. `anchored_pair_frame` computes `truth_dlr_amps` / `anchor_dlr_amps`
    with the corridor geometry (bearing 173.1471 vs 173.15 etc.), while the
    per-city fit and the live collector use `city_point.city_point(city)`.
    Truth, raw_forecast and persistence are therefore recomputed from the
    weather columns with city_point geometry; no `*_dlr_amps` column is read.
  * F5. The frozen FRESH window began 2026-09-30, so the join on the 24 h
    anchor lost the first FRESH day. The fetch window is the selected round's:
    v4-read1 2026-09-28..2026-10-24 (100 scored rows per city,
    2026-09-30T00Z..2026-10-24T18Z, hour % 6 == 0) and v4-read2 2026-09-28..2026-10-31
    (128 scored rows per city, to 2026-10-31T18Z); v4-late-descriptive reuses read 1's.

Anti-peeking. Nothing here builds a FRESH frame, opens a FRESH cache file or
fetches FRESH truth unless `forecast_shadow_eval_core.check_guard` passed
first (clock at or after the selected round's instant; a FRESH run takes no
override). The frame cache is redirected into this run's evidence directory,
so the real data/experiment FRESH caches are never opened. `--dry-run` makes
no network call and reads no FRESH file.

The veto record (SEL-03, D-02). A deciding round (v4-read1, v4-read2) refuses to
start unless `--vetoes` names a record whose ABLATION and TEST source-report
sha256 values equal the files on disk and `--protocol-status signed` is given;
both checks run before `run_confirmation`, and `run_confirmation` itself refuses
a FRESH decision read without a record before its guard, so the one-shot read
is never spent on a run that could not decide. The record's path and hash are
written into the report and `run_started.json`.

Conductor basis (D-01, D-03, D-10; 07-09). `conductor_basis()` decides, per run, which configuration the headline is
scored under. While every city's production point equals the frozen Drake point the run is the default path above and the
secondary is "identical to the headline by construction; not computed separately". When a city differs (the signed O4 case:
AUSTIN at Drake 100 C), the CLI refuses with exit 2, before any network call, unless that city's refit cooling and
reference artifacts for the current RATING_CONFIG_VERSION verify against their manifest (and the frozen artifacts verify
against theirs); it then scores the headline under `city_point.production_city_point` with the refit models for those
cities and, in the same read, the frozen Drake artifacts under the Drake configuration as a labelled secondary that never
decides (`report["secondary"]`). Every artifact either loaded is listed in `report["scored_artifacts"]`; every report and
dry run records `rating_config_version` and `conductor_basis`. The round `v4-late-descriptive` is accepted only when the
current RATING_CONFIG_VERSION differs from the one recorded in the newest v4-read1 headline report ("nothing to re-score
descriptively (D-03)" otherwise); the instant and one-shot guards still apply after that.

Operator commands (one shot per round; evidence lands in
data/shadow/evaluation/<round>)::

    # read 1, at or after 2026-11-01T00:00:00Z, after the ABLATION and TEST vetoes exist:
    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_confirm.py \\
        --round v4-read1 --vetoes <vetoes.json> --protocol-status signed --out confirm.json
    # the conditional re-test, only if read 1 names no winner, at or after 2026-11-08T00:00:00Z:
    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_confirm.py \\
        --round v4-read2 --vetoes <vetoes.json> --protocol-status signed --out confirm_read2.json

    # any time, no network, evidence root not created:
    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_confirm.py \\
        --dry-run --round v4-read1 --out dry_run.json

The 2026-11-24 evaluation of protocol v3 is retired by signed v4 and is refused.

Truth is reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738),
never sensor-validated.
"""

from __future__ import annotations

import argparse
import functools
import glob
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
import forecast_conductor_refit
import forecast_experiment
import forecast_shadow_decision_v4 as decision_v4
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
SECONDARY_LABEL = decision_v4.LABELS["secondary"]
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


def production_frame_provider(city: str, *, evidence_dir: str, window=None, round_name: Optional[str] = None):
    """
    Build one city's reconstructed frame through the frozen
    `forecast_experiment.anchored_pair_frame(city, <round fetch start>, <round fetch end>,
    lead_hours=24)` (read 1: 2026-09-28..2026-10-24, read 2: 2026-09-28..2026-10-31),
    inside the HTTP evidence recorder and with the frame cache
    redirected into `evidence_dir/frames` (restored in a finally block).

    Refuses any window other than the selected round's fetch window (default
    round v4-read1), and
    refuses (before `anchored_pair_frame` is called) if the redirected cache
    path already exists. Returns (frame, archive_weather, evidence_meta), where
    `archive_weather` is the recorded archive body re-parsed with
    `core.parse_archive_payload` (the full hourly truth weather of the fetch
    window).

    Raises:
        ValueError: a window other than the round's pre-registered fetch window.
        EvaluationGuardError: a pre-existing cache file in the redirected directory.
        FrameFetchError: any failure of the two HTTP fetches or the frame build.
    """
    rnd = core.round_named(core.DEFAULT_ROUND.name if round_name is None else round_name)
    start, end = (rnd.fetch_start, rnd.fetch_end) if window is None else window
    if (str(start), str(end)) != (rnd.fetch_start, rnd.fetch_end):
        raise ValueError(
            f"production_frame_provider: window {start}..{end} is not the pre-registered fetch window "
            f"{rnd.fetch_start}..{rnd.fetch_end} of round {rnd.name!r} (PD-02)"
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

def prepare_city_frame(frame: pd.DataFrame, city: str, *, window: Optional[ScoredWindow] = None, point=None):
    """
    Mirror `forecast_shadow_fit_models.fit_from_frame`'s preparation with
    city_point geometry: sort, recompute `truth_dlr_amps` from the truth weather
    (F4: no `*_dlr_amps` column is read), tag the city, keep the exact-lead rows
    inside `window` and add the perpendicular-wind correction columns.

    Rows with a null in any weather field a candidate reads are dropped (never
    imputed) and counted; their slots are reported as missing_from_reconstruction.
    Returns (prepared, diagnostics).

    `point` (D-01, opt-in) is a `CityPoint` to score under instead of the frozen Drake
    `city_point.city_point(city)`: truth is recomputed with that point's bearing and
    conductor through `forecast_conductor_refit.arm5_frame_for_point`. With no point
    every call is exactly the frozen path.

    Raises:
        ReconstructionError: duplicate valid times, a non-24 h anchor gap, or an
            anchor inside the artifacts' fit window.
    """
    window = default_window() if window is None else window
    explicit_point = point is not None
    if point is None:
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
        if explicit_point:
            truth_arm5 = forecast_conductor_refit.arm5_frame_for_point(work, point, prefix="truth_")
        else:
            truth_arm5 = forecast_shadow_fit_models.weather_to_arm5_frame(work, city, prefix="truth_")
        work["truth_dlr_amps"] = truth_arm5["dlr_amps"].to_numpy(dtype=float)
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

def _arm5_from_weather(weather: pd.DataFrame, city: str, *, point=None):
    """Archive weather to the arm-5 frame; null-weather hours are dropped, never imputed.
    With a `point` the ampacity is computed under it (arm5_frame_for_point), otherwise under the frozen Drake point."""
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
    if point is not None:
        return forecast_conductor_refit.arm5_frame_for_point(clean, point), dropped
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
                          *, unavailable: Optional[dict] = None, point=None):
    """
    The five candidates and the truth for one city on its prepared rows.

    `point` (opt-in, D-01) replaces the frozen Drake `city_point.city_point(city)` for every ampacity
    computation here (truth cross-check, raw forecast, persistence, the corrected arms' conductor and the
    reference history); it must be the point the frame was prepared with.

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
    explicit_point = point is not None
    if point is None:
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
    arm5, dropped_hours = _arm5_from_weather(archive_weather, city, point=point if explicit_point else None)
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


def leakage_probe(prepared: pd.DataFrame, city: str, models: dict, *, extra_arms: Optional[dict] = None,
                  point=None) -> dict:
    """
    Recompute raw, persistence, wind and cooling (and any `extra_arms`, a
    test-injection hook) on a copy with sabotaged truth columns and require
    identical output; require the oracle arm (it reads truth wind) to change. `point` (opt-in) is the
    point the arms are built over, as in `candidate_predictions`.

    Raises:
        LeakageProbeError: a genuine candidate changed, or the oracle did not.
    """
    if len(prepared) == 0:
        return {"status": "skipped_no_rows", "passed": True}
    if point is None:
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


def _recording_loader(loader: Callable[[str, str], object], source: str, records: Optional[list] = None):
    """
    Wrap a `(city, method)` model loader so every artifact it serves is recorded (research Pitfall 7).

    A loader that keeps its own `served` list (`forecast_conductor_refit.make_headline_loader`) is the
    authority for the path, sha256 and `source` ("refit" or "frozen") of what it served. For any other
    loader the path is the frozen artifact path `forecast_shadow_pipeline._model_path_for(city, method)`,
    its sha256 is `core.sha256_file` of that file (None when no such file exists, e.g. an injected stub
    loader) and the source is `source`. A repeat is recorded once. Errors from the wrapped loader
    (FileNotFoundError, ArtifactIntegrityError, ...) propagate unchanged. The records list is exposed as
    `.records`.
    """
    records = [] if records is None else records

    def wrapped(city: str, method: str):
        model = loader(city, method)
        served = getattr(loader, "served", None)
        entry = None
        if served is not None:
            entry = next((dict(s) for s in reversed(served) if s["city"] == city and s["method"] == method), None)
        if entry is None:
            path = forecast_shadow_pipeline._model_path_for(city, method)
            entry = {"city": city, "method": method, "path": path.replace(os.sep, "/"),
                     "sha256": core.sha256_file(path) if os.path.isfile(path) else None, "source": source}
        if entry not in records:
            records.append(entry)
        return model

    wrapped.records = records
    wrapped.source = source
    return wrapped


# --------------------------------------------------------------------------
# Conductor basis (D-01, D-10) and the D-03 late-descriptive gate
# --------------------------------------------------------------------------

PARITY_HEADLINE_TEXT = (
    "production configuration equals the frozen Drake configuration for every city asked for; the 12 frozen "
    "artifacts are the production-conductor models (D-10) and the default headline path is used"
)
PARITY_SECONDARY_TEXT = "identical to the headline by construction; not computed separately"
NOTHING_TO_RESCORE = "nothing to re-score descriptively (D-03)"
LATE_ROUND = "v4-late-descriptive"
_FROZEN_REFUSED_STATUSES = ("hash_mismatch", "not_in_manifest", "manifest_unreadable")


def _artifact_status(path: str, manifest_path: str, entries: dict, manifest_error: Optional[str]) -> dict:
    """Status of one model file against a sha256 manifest, without deserializing it (the pickle is never loaded)."""
    key = forecast_conductor_refit._manifest_key(path)
    out = {"path": path.replace(os.sep, "/"), "manifest": manifest_path.replace(os.sep, "/"), "manifest_key": key,
           "exists": os.path.isfile(path), "expected_sha256": None, "actual_sha256": None}
    if manifest_error is not None:
        out.update(status="manifest_unreadable", error=manifest_error)
    elif key not in entries:
        out["status"] = "not_in_manifest"
    else:
        out["expected_sha256"] = entries[key]
        if not out["exists"]:
            out["status"] = "missing_file"
        else:
            out["actual_sha256"] = core.sha256_file(path)
            out["status"] = "verified" if out["actual_sha256"] == out["expected_sha256"] else "hash_mismatch"
    out["verified"] = out["status"] == "verified"
    return out


def _manifest_entries(manifest_path: str):
    try:
        return forecast_conductor_refit._entries(manifest_path), None
    except forecast_conductor_refit.ArtifactIntegrityError as exc:
        return {}, str(exc)


def conductor_basis(cities, config_version: Optional[str] = None, refit_root: Optional[str] = None,
                    frozen_manifest: Optional[str] = None) -> dict:
    """
    Which conductor configuration the headline is scored under (D-01) and whether the artifacts that would be served
    are sound. A city differs when its production point (`city_point.production_city_point`) differs from the frozen
    Drake point (`forecast_conductor_refit.production_differs`).

    With no differing city the headline is the default path (the 12 frozen artifacts serve as the production models,
    D-10) and the secondary is "identical to the headline by construction; not computed separately".

    With differing cities: for each differing city the two refit artifacts (`REFIT_METHODS`) under
    `<refit_root>/<config_version>/` are checked against that directory's manifest, and every frozen artifact of the
    cities asked for against the frozen manifest. Files are hashed, never deserialized. `problems` lists every reason
    the CLI refuses before any network call: any refit artifact that is not `verified`, and any frozen artifact whose
    status is hash_mismatch, not_in_manifest or manifest_unreadable (an absent frozen file stays candidate_unavailable,
    as in the default path). `refit_root` / `frozen_manifest` default (at call time) to the refit module's constants.
    """
    cities = list(cities)
    version = config.RATING_CONFIG_VERSION if config_version is None else config_version
    differing = [c for c in cities if forecast_conductor_refit.production_differs(c)]
    basis: dict = {
        "config_version": version, "cities": cities, "differing": differing,
        "parity_cities": [c for c in cities if c not in differing],
        "refit_artifacts": [], "frozen_artifacts": [], "problems": [], "refit_verified": True,
    }
    if not differing:
        basis["headline"] = PARITY_HEADLINE_TEXT
        basis["secondary"] = PARITY_SECONDARY_TEXT
        return basis

    refit_root = forecast_conductor_refit.REFIT_ROOT if refit_root is None else refit_root
    frozen_manifest = forecast_conductor_refit.FROZEN_MANIFEST if frozen_manifest is None else frozen_manifest
    basis["headline"] = (
        f"production per-city conductors (D-01): {', '.join(differing)} scored under the production configuration with "
        f"the refit ml_cooling_corrected and reference_ml_refit_24h for config version {version}; every other "
        f"city and ml_wind_corrected use the frozen artifacts")
    basis["secondary"] = (
        f"{SECONDARY_LABEL}: the 12 frozen Drake artifacts scored under the Drake configuration on the same fetched frames")

    directory = forecast_conductor_refit.refit_dir(version, refit_root)
    refit_manifest = os.path.join(directory, forecast_conductor_refit.MANIFEST_NAME)
    entries, error = _manifest_entries(refit_manifest)
    for city in differing:
        for method in forecast_conductor_refit.REFIT_METHODS:
            path = forecast_conductor_refit._artifact_path(directory, city, method)
            entry = {"city": city, "method": method, **_artifact_status(path, refit_manifest, entries, error)}
            basis["refit_artifacts"].append(entry)
            if not entry["verified"]:
                basis["problems"].append(f"refit artifact {entry['path']}: {entry['status']}"
                                         + (f" ({entry['error']})" if entry.get("error") else ""))
    basis["refit_verified"] = all(a["verified"] for a in basis["refit_artifacts"])

    entries, error = _manifest_entries(frozen_manifest)
    for city in cities:
        for method in MODEL_METHODS:
            path = forecast_shadow_pipeline._model_path_for(city, method)
            entry = {"city": city, "method": method, **_artifact_status(path, frozen_manifest, entries, error)}
            basis["frozen_artifacts"].append(entry)
            if entry["status"] in _FROZEN_REFUSED_STATUSES:
                basis["problems"].append(f"frozen artifact {entry['path']}: {entry['status']}"
                                         + (f" ({entry['error']})" if entry.get("error") else ""))
    return basis


def late_descriptive_status(base_evidence_root: str, current_version: Optional[str] = None) -> dict:
    """
    D-03 gate for round `v4-late-descriptive`: the descriptive re-score exists to describe a conductor change after
    read 1, so it is allowed only when the current RATING_CONFIG_VERSION differs from the one recorded in the newest
    v4-read1 headline report (`<base>/v4-read1/reconstructed_frames_*/report.json`, newest directory name).
    Only the `rating_config_version` key of that report is read. Returns {"allowed", "reason", "read1_report",
    "read1_rating_config_version", "current_rating_config_version"}; `reason` starts with
    "nothing to re-score descriptively (D-03)" whenever it is not allowed.
    """
    current = config.RATING_CONFIG_VERSION if current_version is None else current_version
    read1_root = core.round_evidence_root(base_evidence_root, core.V4_READ1)
    status = {"allowed": False, "reason": None, "read1_report": None, "read1_rating_config_version": None,
              "current_rating_config_version": current}
    found = sorted(glob.glob(os.path.join(read1_root, f"{ROW_SOURCE}_*", "report.json")))
    if not found:
        status["reason"] = f"{NOTHING_TO_RESCORE}: no v4-read1 headline report exists under {read1_root!r}"
        return status
    newest = found[-1]
    status["read1_report"] = newest
    try:
        with open(newest, "r", encoding="utf-8") as fh:
            recorded = json.load(fh).get("rating_config_version")
    except (OSError, ValueError, AttributeError) as exc:
        status["reason"] = f"{NOTHING_TO_RESCORE}: the read-1 report {newest!r} cannot be read ({type(exc).__name__}: {exc})"
        return status
    status["read1_rating_config_version"] = recorded
    if not isinstance(recorded, str) or not recorded:
        status["reason"] = (f"{NOTHING_TO_RESCORE}: the read-1 report {newest!r} records no rating_config_version, so a "
                            f"conductor change after read 1 cannot be established")
    elif recorded == current:
        status["reason"] = (f"{NOTHING_TO_RESCORE}: the current rating config version {current!r} equals the one recorded "
                            f"in the read-1 report, so the conductor did not change after read 1")
    else:
        status["allowed"] = True
        status["reason"] = f"rating config version changed after read 1 ({recorded!r} -> {current!r})"
    return status


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _error_frame(preds: pd.DataFrame) -> pd.DataFrame:
    """Signed errors (prediction - truth), one column per candidate, indexed by valid_time."""
    if preds is None or len(preds) == 0:
        empty = pd.DataFrame({name: pd.Series(dtype=float) for name in core.CANDIDATES})
        empty.attrs["row_source"] = ROW_SOURCE
        return empty
    frame = pd.DataFrame({name: preds[name] - preds["truth_amps"] for name in core.CANDIDATES}, index=preds.index)
    frame["slot"] = preds["slot"]
    frame.attrs["row_source"] = ROW_SOURCE
    return frame


def _failed_city_block(city: str, stage: str, error: str) -> dict:
    return {
        "n_in_scope": 0, "n_with_truth": 0, "n_scored": {n: 0 for n in core.CANDIDATES},
        "excluded_by_reason": {f"city_failed:{stage}": 1}, "candidate_exclusions": {},
        "metrics": {n: core.descriptive_metrics([], []) for n in core.CANDIDATES},
        "truth_label": core.TRUTH_LABEL, "failed": {"stage": stage, "error": error},
    }


VETO_BASES = ("ablation", "test")
VETO_RECORD_PROTOCOL = "v4"


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def validate_veto_record(record) -> dict:
    """
    The structural checks of a veto record, shared by `load_vetoes` and `run_confirmation` so a malformed record
    given directly is refused before the guard too. Candidate names are matched as exact strings against
    `core.REAL_CANDIDATES`: every one must be present in both sections and no other key is allowed, so an
    edited or truncated record can never un-veto a candidate by omission. Returns `record`.

    Raises:
        ValueError: not an object, a missing section, a wrong or missing candidate key, a vetoed flag that is
            not a bool (0, 1 and strings are refused).
    """
    if not isinstance(record, dict):
        raise ValueError("veto record: expected a JSON object with 'ablation' and 'test' sections")
    for basis in VETO_BASES:
        section = record.get(basis)
        if not isinstance(section, dict):
            raise ValueError(f"veto record: the {basis!r} section is missing (SEL-03 needs both ABLATION and TEST)")
        vetoes = section.get("vetoes")
        if not isinstance(vetoes, dict):
            raise ValueError(f"veto record: {basis!r} has no 'vetoes' object")
        unknown = sorted(k for k in vetoes if k not in core.REAL_CANDIDATES)
        absent = [c for c in core.REAL_CANDIDATES if c not in vetoes]
        if unknown:
            raise ValueError(f"veto record: {basis!r} names unknown candidate(s) {unknown}; candidates are matched as "
                             f"exact strings, valid: {list(core.REAL_CANDIDATES)}")
        if absent:
            raise ValueError(f"veto record: {basis!r} is missing candidate(s) {absent}; every candidate needs a "
                             f"vetoed flag so none is un-vetoed by omission")
        for cand, entry in vetoes.items():
            flag = entry.get("vetoed") if isinstance(entry, dict) else None
            if not isinstance(flag, bool):
                raise ValueError(f"veto record: {basis!r} candidate {cand!r} needs a 'vetoed' flag that is a bool, "
                                 f"got {flag!r}")
    return record


def load_vetoes(path: str, *, base_dir: Optional[str] = None) -> dict:
    """
    Read and verify the ABLATION and TEST veto record (07-11 writes it; SEL-03, T-07-15).

    Shape: {"protocol": "v4", "ablation": {"report": <path>, "sha256": <hex>, "vetoes": {candidate:
    {"vetoed": bool, "reasons": [..]}}, ...}, "test": {... same ...}, "created_at_utc": <iso>}. Every
    referenced report must exist and its sha256 must equal the recorded value; a relative `report` path is
    resolved against `base_dir` (default the repository root).

    Returns the parsed record plus `"file": {"path": <absolute path>, "sha256": <sha256 of the record file>}`,
    which is what the run records in its config and report.

    Raises:
        ValueError: unreadable or non-JSON file, not v4, a structural fault (see `validate_veto_record`), a
            missing source report, or a sha256 that does not match the report on disk.
    """
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise ValueError(f"load_vetoes: cannot read {path!r}: {exc}") from exc
    try:
        record = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise ValueError(f"load_vetoes: {path!r} is not valid JSON: {exc}") from exc
    validate_veto_record(record)
    if record.get("protocol") != VETO_RECORD_PROTOCOL:
        raise ValueError(f"load_vetoes: the record's protocol is {record.get('protocol')!r}, expected {VETO_RECORD_PROTOCOL!r}")
    base = _repo_root() if base_dir is None else base_dir
    for basis in VETO_BASES:
        section = record[basis]
        report_path, recorded = section.get("report"), section.get("sha256")
        if not isinstance(report_path, str) or not report_path.strip() or not isinstance(recorded, str) or not recorded.strip():
            raise ValueError(f"load_vetoes: {basis!r} must name its source 'report' path and its 'sha256'")
        full = os.path.join(base, report_path)
        if not os.path.isfile(full):
            raise ValueError(f"load_vetoes: the {basis!r} source report {report_path!r} does not exist (looked at {full!r})")
        actual = core.sha256_file(full)
        if actual != recorded.strip().lower():
            raise ValueError(f"load_vetoes: the {basis!r} source report {report_path!r} has sha256 {actual}, but the "
                             f"veto record says {recorded} (T-07-15: the report changed after the record was written)")
    return {**record, "file": {"path": os.path.abspath(path), "sha256": core.sha256_bytes(raw)}}


def _rule_vetoes(vetoes: Optional[dict]) -> Optional[dict]:
    """The veto record in the shape `apply_ship_rule_v4` takes: {"ablation": {cand: {...}}, "test": {...}}."""
    if vetoes is None:
        return None
    return {basis: vetoes[basis]["vetoes"] for basis in VETO_BASES}


def _veto_source(vetoes: Optional[dict]) -> Optional[dict]:
    """What the config and report say about where the veto record came from (path and hashes), or None."""
    if vetoes is None:
        return None
    file_info = vetoes.get("file") or {}
    return {
        "path": file_info.get("path"), "sha256": file_info.get("sha256"), "injected": not file_info,
        "ablation_report": {k: vetoes["ablation"].get(k) for k in ("report", "sha256")},
        "test_report": {k: vetoes["test"].get(k) for k in ("report", "sha256")},
    }


def _resolve_round(round_name: Optional[str], guard_cfg: core.GuardConfig) -> core.ProtocolRound:
    """The signed round of a run: `round_name`, else the guard's. The two must agree."""
    name = guard_cfg.round_name if round_name is None else round_name
    if name != guard_cfg.round_name:
        raise ValueError(f"run_confirmation: round_name {name!r} disagrees with the guard's round "
                         f"{guard_cfg.round_name!r}; build the guard with core.guard_for_round({name!r})")
    return core.round_named(name)


def _truth_stats(preds: pd.DataFrame) -> Optional[dict]:
    """Per-city mean truth ampacity and its row count over the prepared rows (None when the city has no rows)."""
    if preds is None or len(preds) == 0:
        return None
    return {"mean_truth_amps": float(np.mean(preds["truth_amps"].to_numpy(dtype=float))), "n_truth_rows": int(len(preds))}


def _attach_family_and_decision(report: dict, error_frames: dict, params: dict, protocol_status: str, *,
                                truth_stats: dict, round_name: str, vetoes: Optional[dict], basis: str,
                                label: Optional[str] = None) -> dict:
    """The 9-test family and the signed v4 decision. Headline label for a deciding round, descriptive label for
    the late descriptive round, or the explicit `label` ("secondary"); the veto record is required only for a
    FRESH headline run."""
    family = stats.build_family_report(error_frames, row_source=ROW_SOURCE, params=params)
    report["family"] = family
    report["sample_size"]["pairs"] = family["sample_size"]["pairs"]
    report["sample_size"]["targets_met"] = family["sample_size"]["targets_met"]
    report["sample_size"]["nominal_vs_effective"] = (
        "n is nominal; effective sample sizes (ACF per city, bootstrap pooled) are in `pairs` and are smaller")
    descriptive = core.round_named(round_name).descriptive_only
    if label is None:
        label = "descriptive" if descriptive else "headline"
    report["decision"] = decision_v4.apply_ship_rule_v4(
        family, truth_stats=truth_stats, round_name=round_name, label=label,
        vetoes=_rule_vetoes(vetoes), require_vetoes=(label == "headline" and basis == "FRESH" and not descriptive),
        protocol_status=protocol_status, fraction=params["relative_margin_fraction"],
        min_cities=params["consistency_min_cities"])
    return report


def _score_city(frame, archive_weather, city, *, window, point, model_loader, extra_probe_arms, stage: list):
    """One city, one configuration: prepare, load models, predict, probe. `stage[0]` names the step in flight so a
    failure can be recorded against it. Returns (prep_diag, preds, pred_diag, probe)."""
    stage[0] = "prepare"
    prepared, prep_diag = prepare_city_frame(frame, city, window=window, point=point)
    stage[0] = "models"
    models, unavailable = load_models(city, model_loader)
    stage[0] = "predict"
    preds, pred_diag = candidate_predictions(prepared, archive_weather, city, models, unavailable=unavailable, point=point)
    stage[0] = "leakage_probe"
    probe = leakage_probe(prepared, city, models, extra_arms=extra_probe_arms, point=point)
    return prep_diag, preds, pred_diag, probe


def _city_blocks(preds: pd.DataFrame, prep_diag: dict, pred_diag: dict, probe: dict, fetch_meta) -> dict:
    """The per-city report blocks (per_city, exclusions, diagnostics, truth) for one scored city."""
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
    per_city = {
        "n_in_scope": prep_diag["n_expected_slots"], "n_with_truth": n_with_truth, "n_scored": n_scored,
        "excluded_by_reason": {k: v for k, v in row_excl.items() if v},
        "candidate_exclusions": cand_excl, "metrics": metrics, "truth_label": core.TRUTH_LABEL,
    }
    city_truth = _truth_stats(preds)
    if city_truth is not None:
        per_city["truth_stats"] = city_truth
    exclusions = {
        "row_level": row_excl,
        "rows_dropped_null_weather": prep_diag["n_rows_dropped_null_weather"],
        "candidate_level": cand_excl,
        "accounting": {
            "expected_slots_equals_scored_plus_missing": prep_diag["n_expected_slots"] == n_with_truth + n_missing,
            "per_candidate_scored_plus_exclusions_equals_rows": {
                name: n_with_truth == n_scored[name] + sum(cand_excl[name].values()) for name in core.CANDIDATES},
        },
    }
    diagnostics = {
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
    return {"per_city": per_city, "exclusions": exclusions, "diagnostics": diagnostics, "truth": city_truth}


def _sample_size_block(per_city: dict, cities) -> dict:
    pooled = {name: int(sum(per_city[c]["n_scored"][name] for c in cities)) for name in core.CANDIDATES}
    return {
        "per_city": {c: {"n_in_scope": per_city[c]["n_in_scope"], "n_scored": per_city[c]["n_scored"],
                         "targets": core.precision_targets(max(per_city[c]["n_scored"].values(), default=0))}
                     for c in cities},
        "pooled_nominal": {"label": "nominal, not effective", "n_scored": pooled,
                           "targets": core.pooled_nominal_targets(max(pooled.values(), default=0))},
    }


def _validate_secondary(secondary) -> None:
    """A secondary spec is {"label": "secondary", "point_resolver": callable or None, "model_loader": callable}."""
    if (not isinstance(secondary, dict) or secondary.get("label") != "secondary"
            or not callable(secondary.get("model_loader"))
            or not (secondary.get("point_resolver") is None or callable(secondary.get("point_resolver")))):
        raise ValueError(
            "run_confirmation: the secondary spec must be a dict {'label': 'secondary', 'point_resolver': "
            "callable or None, 'model_loader': callable}; the labelled secondary never decides (D-01)")


def _resolver_name(resolver) -> str:
    if resolver is None:
        return "city_point (frozen Drake)"
    return getattr(resolver, "__name__", None) or repr(resolver)


def run_confirmation(*, cities, guard_cfg: core.GuardConfig, evidence_root: str, protocol_status: str = "unsigned",
                     now=None, params: Optional[dict] = None, frame_provider: Optional[Callable] = None,
                     model_loader: Optional[Callable] = None, window=None, repo_root: Optional[str] = None,
                     extra_probe_arms: Optional[dict] = None, round_name: Optional[str] = None,
                     vetoes: Optional[dict] = None, point_resolver: Optional[Callable] = None,
                     secondary: Optional[dict] = None, conductor_basis: Optional[dict] = None) -> dict:
    """
    Order: scope valid times from the window; require the veto record for a
    FRESH decision read (before the guard); `check_guard`; refuse a
    development-basis run without an injected `model_loader`; create the
    evidence directory; per city: frame provider, prepare, load models, candidate
    predictions, leakage probe; absolute errors; descriptive metrics; the 9-test
    family; the v4 ship rule; provenance; report.

    `window` is (scored_start, scored_end_exclusive) or a ScoredWindow; the default
    is the FRESH window 2026-09-30T00Z .. the valid-time cutoff. A custom window is
    only for development rehearsals and needs an injected `frame_provider`.
    `frame_provider(city, *, evidence_dir)` returns (frame, archive_weather, meta).
    `model_loader(city, method)` defaults to `load_correction_model` in a FRESH run.
    `extra_probe_arms` is a test hook: extra arms the leakage probe must also clear.

    `round_name` is the signed round (default: the guard's, which defaults to v4-read1); it fixes the
    fetch window of the production provider and the decision's round. `vetoes` is the record
    `load_vetoes` returns. A FRESH scope in a deciding (not descriptive-only) round needs it: without
    one this raises ValueError BEFORE the guard and before any directory exists, because a crash after
    the guard would spend the one-shot run (SEL-03). A supplied record is always validated and applied.

    `point_resolver(city)` (opt-in, D-01) returns the `CityPoint` the HEADLINE is scored under (the CLI
    passes `city_point.production_city_point` only when a city's production conductor differs from Drake);
    with None every call is the frozen Drake path, unchanged. `secondary` (opt-in) is {"label": "secondary",
    "point_resolver": callable or None, "model_loader": callable}: on the SAME fetched frames and archive
    weather it scores a second configuration (the CLI: the frozen Drake artifacts under the Drake point) into
    `report["secondary"]` with its own family and a decision labelled "secondary: frozen Drake artifacts, never
    decides" (pick None). The two are never pooled. A per-city failure in the secondary is recorded under
    `report["secondary"]["failed_cities"]` and never removes the headline's city. `report["scored_artifacts"]`
    lists every artifact the headline and the secondary loaded (city, method, path, sha256, source, role).
    `conductor_basis` (the dict `conductor_basis()` returns, or None) is recorded verbatim in the config and the
    report; every report also records `rating_config_version` (config.RATING_CONFIG_VERSION at run time).

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
    rnd = _resolve_round(round_name, guard_cfg)
    win = _resolve_window(window, guard_cfg)
    if frame_provider is None and (win.start, win.end) != (default_window(guard_cfg).start, default_window(guard_cfg).end):
        raise ValueError("run_confirmation: the production frame provider supports only the default window; "
                         "inject a frame_provider for a development window")
    scope_times = list(win.slots())

    if secondary is not None:
        _validate_secondary(secondary)
    if vetoes is not None:
        validate_veto_record(vetoes)
    if vetoes is None and not rnd.descriptive_only and any(t >= core.FRESH_BASIS_START for t in scope_times):
        raise ValueError(
            f"run_confirmation: a FRESH decision read in round {rnd.name!r} needs the ABLATION and TEST veto record "
            f"(SEL-03, --vetoes); refused before the guard so no one-shot run is spent"
        )

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
    provider = frame_provider or functools.partial(production_frame_provider, round_name=rnd.name)
    veto_source = _veto_source(vetoes)

    headline_is_frozen = model_loader is forecast_shadow_pipeline.load_correction_model
    headline_loader = _recording_loader(model_loader, "frozen" if headline_is_frozen else "injected")
    secondary_loader = None if secondary is None else _recording_loader(
        secondary["model_loader"],
        "frozen" if secondary["model_loader"] is forecast_shadow_pipeline.load_correction_model else "injected")

    config_record = {
        "cities": cities, "protocol_status": protocol_status, "evidence_root": evidence_root,
        "round": rnd.name, "vetoes": veto_source,
        "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in params.items()},
        "scored_window": [win.start.isoformat(), win.end.isoformat()],
        "fetch_window": [rnd.fetch_start, rnd.fetch_end],
        "model_source": MODEL_SOURCE_TEXT,
        "frame_provider": "production" if frame_provider is None else "injected",
        "model_loader": "load_correction_model" if headline_is_frozen else "injected",
        "point_resolver": _resolver_name(point_resolver),
        "rating_config_version": config.RATING_CONFIG_VERSION,
        "conductor_basis": conductor_basis,
        "secondary": None if secondary is None else {
            "label": SECONDARY_LABEL, "point_resolver": _resolver_name(secondary["point_resolver"]),
            "model_loader": "load_correction_model" if secondary_loader.source == "frozen" else "injected"},
    }
    evidence_dir = core.new_evidence_dir(evidence_root, ROW_SOURCE, now_ts, guard_record, config_record)
    root = repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prov = core.provenance(root, cities)
    report = core.new_report(row_source=ROW_SOURCE, basis=basis, protocol_status=protocol_status,
                             guard=guard_record, config_record=config_record, prov=prov, params=params)
    report["scored_window"] = [win.start.isoformat(), win.end.isoformat()]
    report["failed_cities"] = {}
    report["round"] = rnd.name
    report["vetoes"] = None if vetoes is None else {"source": veto_source, "record": vetoes}
    report["truth_stats"] = {}
    report["rating_config_version"] = config.RATING_CONFIG_VERSION
    report["conductor_basis"] = conductor_basis
    sec_report = None
    if secondary is not None:
        sec_report = {
            "label": SECONDARY_LABEL, "row_source": ROW_SOURCE, "round": rnd.name,
            "point_resolver": _resolver_name(secondary["point_resolver"]),
            "per_city": {}, "exclusions": {}, "diagnostics": {}, "failed_cities": {}, "truth_stats": {},
        }

    error_frames: dict = {}
    sec_error_frames: dict = {}
    for city in cities:
        stage = ["frame_fetch"]
        frame = archive_weather = fetch_meta = None
        try:
            frame, archive_weather, fetch_meta = provider(city, evidence_dir=evidence_dir)
            stage[0] = "prepare"
            head_point = point_resolver(city) if point_resolver is not None else None
            prep_diag, preds, pred_diag, probe = _score_city(
                frame, archive_weather, city, window=win, point=head_point, model_loader=headline_loader,
                extra_probe_arms=extra_probe_arms, stage=stage)
        except (FrameFetchError, ValueError, KeyError) as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            stage_name = "frame_fetch_failed" if isinstance(exc, FrameFetchError) else stage[0]
            report["failed_cities"][city] = {"stage": stage_name, "error": error_text}
            error_frames[city] = _error_frame(None)
            report["per_city"][city] = _failed_city_block(city, stage_name, error_text)
            report["exclusions"][city] = {"city_failed": {"stage": stage_name, "error": error_text}}
            report["diagnostics"][city] = {"failed": {"stage": stage_name, "error": error_text}}
        else:
            error_frames[city] = _error_frame(preds)
            blocks = _city_blocks(preds, prep_diag, pred_diag, probe, fetch_meta)
            report["per_city"][city] = blocks["per_city"]
            if blocks["truth"] is not None:
                report["truth_stats"][city] = blocks["truth"]
            report["exclusions"][city] = blocks["exclusions"]
            report["diagnostics"][city] = blocks["diagnostics"]

        if secondary is not None:
            _score_secondary_city(sec_report, sec_error_frames, city, secondary, secondary_loader, frame, archive_weather,
                                  fetch_meta, win, extra_probe_arms, frame_failed=frame is None)

    report["sample_size"] = _sample_size_block(report["per_city"], cities)
    report = _attach_family_and_decision(report, error_frames, params, protocol_status,
                                         truth_stats=report["truth_stats"], round_name=rnd.name, vetoes=vetoes, basis=basis)
    if sec_report is not None:
        sec_report["sample_size"] = _sample_size_block(sec_report["per_city"], cities)
        _attach_family_and_decision(sec_report, sec_error_frames, params, protocol_status,
                                    truth_stats=sec_report["truth_stats"], round_name=rnd.name, vetoes=vetoes,
                                    basis=basis, label="secondary")
    report["secondary"] = sec_report
    report["scored_artifacts"] = (
        [{**entry, "role": "headline"} for entry in headline_loader.records]
        + ([] if secondary_loader is None else [{**entry, "role": "secondary"} for entry in secondary_loader.records]))
    report["evidence"] = core.collect_evidence(evidence_dir)
    report["evidence_dir"] = evidence_dir
    report["report_paths"] = core.write_report(report, evidence_dir)
    return report


def _score_secondary_city(sec_report, sec_error_frames, city, secondary, secondary_loader, frame, archive_weather,
                          fetch_meta, win, extra_probe_arms, *, frame_failed: bool) -> None:
    """Score one city under the secondary configuration on the headline's own frame and archive weather. A failure is
    recorded in the secondary only (never retried, never touching the headline). LeakageProbeError propagates."""
    def fail(stage_name: str, error_text: str) -> None:
        sec_report["failed_cities"][city] = {"stage": stage_name, "error": error_text}
        sec_error_frames[city] = _error_frame(None)
        sec_report["per_city"][city] = _failed_city_block(city, stage_name, error_text)
        sec_report["exclusions"][city] = {"city_failed": {"stage": stage_name, "error": error_text}}
        sec_report["diagnostics"][city] = {"failed": {"stage": stage_name, "error": error_text}}

    if frame_failed:
        fail("frame_fetch_failed", "no frame: the headline's frame fetch for this city failed")
        return
    stage = ["prepare"]
    try:
        resolver = secondary["point_resolver"]
        point = resolver(city) if resolver is not None else None
        prep_diag, preds, pred_diag, probe = _score_city(
            frame, archive_weather, city, window=win, point=point, model_loader=secondary_loader,
            extra_probe_arms=extra_probe_arms, stage=stage)
    except (FrameFetchError, ValueError, KeyError) as exc:
        fail(stage[0], f"{type(exc).__name__}: {exc}")
        return
    sec_error_frames[city] = _error_frame(preds)
    blocks = _city_blocks(preds, prep_diag, pred_diag, probe, fetch_meta)
    sec_report["per_city"][city] = blocks["per_city"]
    if blocks["truth"] is not None:
        sec_report["truth_stats"][city] = blocks["truth"]
    sec_report["exclusions"][city] = blocks["exclusions"]
    sec_report["diagnostics"][city] = blocks["diagnostics"]


# --------------------------------------------------------------------------
# Dry run
# --------------------------------------------------------------------------

def dry_run(*, cities, guard_cfg: core.GuardConfig, evidence_root: str, now=None,
            params: Optional[dict] = None, repo_root: Optional[str] = None,
            round_name: Optional[str] = None, basis: Optional[dict] = None,
            late_gate: Optional[dict] = None) -> dict:
    """
    No network, no FRESH read, no directory created. Reports the round, whether the
    guard would refuse now, the planned requests (archive and previous-runs per city,
    over the round's fetch window), the 12 artifact hashes and the freeze check.

    Also reports the conductor basis (`basis`, default `conductor_basis(cities)`): which cities differ from Drake,
    which refit artifacts would be served and whether their hashes verify (files are hashed, never loaded), the
    `rating_config_version`, and, for the late descriptive round, the D-03 gate status (`late_gate`). A dry run
    reports a problem; it never refuses because of one.
    """
    cities = list(cities)
    rnd = _resolve_round(round_name, guard_cfg)
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
        url, p = core.build_archive_request(city, rnd.fetch_start, rnd.fetch_end)
        planned.append({"city": city, "label": "archive", "url": url, "params": p})
        url, p = build_previous_runs_request(city, rnd.fetch_start, rnd.fetch_end)
        planned.append({"city": city, "label": "previous_runs", "url": url, "params": p})
    root = repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prov = core.provenance(root, cities)
    result = {
        "round": rnd.name,
        "rating_config_version": config.RATING_CONFIG_VERSION,
        "conductor_basis": conductor_basis(cities) if basis is None else basis,
        "guard": guard,
        "now_evaluated": now_ts.isoformat(),
        "protocol_status_note": "unsigned runs are exploratory",
        "fetch_window": [rnd.fetch_start, rnd.fetch_end],
        "scored_window": [win.start.isoformat(), win.end.isoformat()],
        "expected_slots_per_city": int(len(win.slots())),
        "planned_requests": planned,
        "artifacts": [{"path": a["path"], "sha256": a["sha256"], "method": a["method"], "city": a["city"]}
                      for a in prov["artifacts"]],
        "freeze_check": prov["freeze_check"],
        "evidence_root": evidence_root,
    }
    if rnd.name == LATE_ROUND:
        result["late_descriptive_gate"] = late_gate
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="forecast_shadow_confirm", description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--cities", nargs="+", default=list(config.LOCATIONS))
    p.add_argument("--dry-run", action="store_true",
                   help="no network, no FRESH read, evidence root not created; prints the plan")
    p.add_argument("--round", choices=sorted(core.PROTOCOL_ROUNDS), default=core.DEFAULT_ROUND.name,
                   help="signed protocol v4 round to run under; its evidence goes to <evidence-root>/<round> "
                        "(default %(default)s)")
    p.add_argument("--vetoes", default=None, metavar="PATH",
                   help="the ABLATION and TEST veto record (JSON, sha256-checked against both source reports); "
                        "required for a deciding round (v4-read1, v4-read2) and refused unless "
                        "--protocol-status is signed (SEL-03)")
    p.add_argument("--evidence-root", default=core.EVIDENCE_ROOT_DEFAULT)
    p.add_argument("--out", default=None, help="write the dry-run JSON (or a copy of report.json) here")
    p.add_argument("--evaluation-instant", default=None)
    p.add_argument("--valid-time-cutoff", default=None)
    p.add_argument("--override-reason", default=None)
    p.add_argument("--protocol-status", choices=("signed", "unsigned"), default="unsigned")
    # Pre-registered statistical parameters (no --row-gate, no --family-size: decisions 2 and 3).
    p.add_argument("--block-lengths", type=int, nargs="+", default=None)
    p.add_argument("--n-resamples", type=int, default=None)
    p.add_argument("--decision-margin-amps", type=float, default=None,
                   help="retired v3 parameter: the v4 rule does not use it (it uses 2%% of mean truth); a non-default "
                        "value is still refused in a FRESH run (PD-15)")
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
        rnd = core.round_named(args.round)
        guard_cfg = score_mod._guard_from_args(args)
        params = score_mod._params_from_args(args)
        round_root = core.round_evidence_root(args.evidence_root, rnd)
        try:
            basis = conductor_basis(args.cities)
        except KeyError as exc:          # a city without a usable production table entry: refuse, nothing has run
            raise ValueError(f"conductor basis: {exc.args[0] if exc.args else exc}") from exc
        late_gate = late_descriptive_status(args.evidence_root) if rnd.name == LATE_ROUND else None
        if args.dry_run:
            result = dry_run(cities=args.cities, guard_cfg=guard_cfg, evidence_root=round_root, params=params,
                             round_name=rnd.name, basis=basis, late_gate=late_gate)
            text = core.dumps(result, indent=2)
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    fh.write(text)
            else:
                print(text)
            return 0
        vetoes = None
        if args.vetoes is not None:
            vetoes = load_vetoes(args.vetoes)
        if not rnd.descriptive_only:
            problems = []
            if vetoes is None:
                problems.append("--vetoes must name the ABLATION and TEST veto record (SEL-03: the vetoes exist "
                                "before the FRESH read)")
            if args.protocol_status != "signed":
                problems.append("--protocol-status signed is required")
            if problems:
                raise core.EvaluationGuardError(
                    f"a deciding round ({rnd.name}) cannot start: " + "; ".join(problems))
        if late_gate is not None and not late_gate["allowed"]:
            raise core.EvaluationGuardError(late_gate["reason"])
        if basis["problems"]:
            raise core.EvaluationGuardError(
                "conductor basis: a city's production conductor differs from Drake but its artifacts are not sound; "
                "refusing before any network call: " + "; ".join(basis["problems"]))
        run_kwargs: dict = {}
        if basis["differing"]:
            version, root_dir = basis["config_version"], forecast_conductor_refit.REFIT_ROOT
            frozen_manifest = forecast_conductor_refit.FROZEN_MANIFEST
            # Both loaders verify every artifact's sha256 against its manifest before it is deserialized (T-07-19);
            # the secondary serves only frozen Drake artifacts.
            run_kwargs = {
                "point_resolver": city_point.production_city_point,
                "model_loader": forecast_conductor_refit.make_headline_loader(
                    version, set(basis["differing"]), root=root_dir, frozen_manifest=frozen_manifest),
                "secondary": {"label": "secondary", "point_resolver": None,
                              "model_loader": forecast_conductor_refit.make_headline_loader(
                                  version, frozenset(), root=root_dir, frozen_manifest=frozen_manifest)},
            }
        report = run_confirmation(cities=args.cities, guard_cfg=guard_cfg, evidence_root=round_root,
                                  protocol_status=args.protocol_status, params=params, round_name=rnd.name,
                                  vetoes=vetoes, conductor_basis=basis, **run_kwargs)
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
    except forecast_conductor_refit.ArtifactIntegrityError as exc:
        print(f"failed: an artifact failed its hash check after the pre-check: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
