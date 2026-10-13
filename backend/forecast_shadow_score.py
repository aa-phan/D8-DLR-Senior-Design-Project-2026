"""
Per-city shadow-log scorer: the LIVE-SYSTEM CHECK (quick task 261013-285).

Row source `shadow_logs`. Per amendment decision 9 this source is reported
separately from, and never pooled with, the reconstructed-frame port
(`forecast_shadow_confirm.py`), which is the headline for "which candidate to
ship". This scorer reads `data/shadow/predictions/{CITY}.jsonl` (schema_version
3 only; corridor files are never opened) and scores only rows tagged
`forecast_model: gfs_seamless` (V6, decision 11).

Operator commands (the logs live on the data branch, so export them first;
nothing here fetches them)::

    git fetch origin shadow-collection-data
    D=$(mktemp -d)
    for c in AUSTIN CORPUS_CHRISTI MIDLAND EL_PASO; do
      git show origin/shadow-collection-data:data/shadow/predictions/$c.jsonl > $D/$c.jsonl
    done
    # any time (status-only counts, no truth, no ampacity-derived number):
    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_score.py \\
        --count-only --predictions-dir $D --out $D/counts.json
    # one-shot evaluation, at or after 2026-11-24T00:00:00Z only:
    PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_score.py \\
        --predictions-dir $D --source-commit $(git rev-parse origin/shadow-collection-data)

Before the evaluation instant a FRESH-dated scoring run is refused before any
network call (`forecast_shadow_eval_core.check_guard`). `--count-only` is the
mechanical-health-check carve-out: it never fetches truth and never uses a
logged ampacity.

Validity threats V1 to V6 (amendment): V6 rows (no `forecast_model`) and rows
of any other model are excluded and counted, never pooled (PD-13). V2:
`reference_ml_refit_24h` is scored at its own target hour (decision time + 24 h
rounded to the nearest whole hour, PD-11) as the headline, with the
logged-valid_time reading alongside and flagged. V3 and V1 are flagged on every
pair that involves persistence_24h or the anchored corrections, and the
realized anchor source and age are reported (exploratory, descriptive). V4 and
V5 are carried as flags. Truth is
reanalysis-derived, never sensor-validated.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

import config
import forecast_shadow_decision as decision
import forecast_shadow_eval_core as core
import forecast_shadow_score_stats as stats

ROW_SOURCE = core.LIVE_ROW_SOURCE

READER_COUNTER_KEYS = (
    "lines_total", "blank", "malformed", "legacy_v1_flat", "legacy_v2_corridor",
    "other_city_or_schema", "accepted_rows",
)
ROW_EXCLUSION_KEYS = (
    "bad_timestamps", "missing_forecast_model", "other_forecast_model",
    "lead_structure_mismatch", "at_or_after_cutoff", "duplicate_valid_time",
)
TRUTH_EXCLUSION_KEYS = ("truth_fetch_failed", "truth_missing")
CANDIDATE_EXCLUSION_KEYS = (
    "candidate_missing", "candidate_unavailable", "candidate_failed",
    "candidate_fallback_used", "candidate_null_or_nonfinite_value",
)
REFERENCE_EXTRA_EXCLUSION_KEYS = ("reference_target_at_or_after_cutoff", "reference_target_truth_missing")
REFERENCE = "reference_ml_refit_24h"
ANCHORED = ("ml_wind_corrected", "ml_cooling_corrected")
STATUS_LABELS = ("ok", "unavailable", "failed", "missing", "other")
_MISSING_MODEL_KEY = "<missing>"


# --------------------------------------------------------------------------
# Reader
# --------------------------------------------------------------------------

def read_scorable_log(path: str, city: str):
    """
    Entries (with 1-based line numbers) accepted by exactly the predicate of
    `forecast_shadow_pipeline.read_city_log_entries`, plus counters for what
    was skipped. Returns ([(line_no, entry)], counters).
    """
    counters = {k: 0 for k in READER_COUNTER_KEYS}
    entries: list[tuple[int, dict]] = []
    if not os.path.exists(path):
        counters["file_missing"] = True
        return entries, counters
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            counters["lines_total"] += 1
            line = raw.strip()
            if not line:
                counters["blank"] += 1
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                counters["malformed"] += 1
                continue
            if not isinstance(entry, dict):
                counters["malformed"] += 1
                continue
            version = entry.get("schema_version", 1)
            if isinstance(version, bool) or not isinstance(version, int):
                counters["malformed"] += 1
                continue
            if version < 2:
                counters["legacy_v1_flat"] += 1
                continue
            if version < 3 or ("city" not in entry and "corridor" in entry):
                counters["legacy_v2_corridor"] += 1
                continue
            if entry.get("city") != city:
                counters["other_city_or_schema"] += 1
                continue
            counters["accepted_rows"] += 1
            entries.append((line_no, entry))
    return entries, counters


# --------------------------------------------------------------------------
# Row-level selection
# --------------------------------------------------------------------------

def _parse_ts(value) -> Optional[pd.Timestamp]:
    if value is None or isinstance(value, bool):
        return None
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return None
    if pd.isna(ts):
        return None
    return core.to_utc(ts)


def _raw_forecast_model(entry: dict):
    """The RAW field: absent or empty (V6) is None, never the legacy default."""
    if "forecast_model" not in entry:
        return None
    model = entry["forecast_model"]
    return model if isinstance(model, str) and model else None


def _lead_structure_failures(valid, decision, init, horizon) -> list[str]:
    failures = []
    if horizon != 1440 or isinstance(horizon, bool):
        failures.append("horizon_not_1440")
    if valid != valid.floor(f"{core.SLOT_HOURS}h"):
        failures.append("valid_time_off_6h_grid")
    if init != valid - pd.Timedelta(hours=core.LEAD_HOURS):
        failures.append("init_not_valid_minus_24h")
    gap_h = (valid - decision) / pd.Timedelta(hours=1)
    lo, hi = core.DECISION_GAP_HOURS
    if not (lo < gap_h <= hi):
        failures.append("decision_gap_outside_11_17h")
    return failures


def _select_row_level(entries, guard_cfg: core.GuardConfig):
    """Row-level exclusion order: bad_timestamps, missing_forecast_model,
    other_forecast_model, lead_structure_mismatch, at_or_after_cutoff,
    duplicate_valid_time. Reads no ampacity value."""
    cutoff = core.to_utc(guard_cfg.valid_time_cutoff)
    counters: dict = {k: 0 for k in ROW_EXCLUSION_KEYS}
    counters["forecast_model_counts"] = {}
    counters["other_forecast_model_by_model"] = {}
    counters["lead_structure_detail"] = {}
    counters["logged_at_inversions"] = 0
    kept: list[dict] = []
    duplicates: list[dict] = []
    by_valid: dict = {}

    for line_no, entry in entries:
        model = _raw_forecast_model(entry)
        key = model if model is not None else _MISSING_MODEL_KEY
        counters["forecast_model_counts"][key] = counters["forecast_model_counts"].get(key, 0) + 1

        valid = _parse_ts(entry.get("valid_time"))
        decision = _parse_ts(entry.get("decision_time"))
        init = _parse_ts(entry.get("initialization_time"))
        if valid is None or decision is None or init is None:
            counters["bad_timestamps"] += 1
            continue
        if model is None:
            counters["missing_forecast_model"] += 1
            continue
        if model != core.SCORED_FORECAST_MODEL:
            counters["other_forecast_model"] += 1
            counters["other_forecast_model_by_model"][model] = counters["other_forecast_model_by_model"].get(model, 0) + 1
            continue
        failures = _lead_structure_failures(valid, decision, init, entry.get("horizon_minutes"))
        if failures:
            counters["lead_structure_mismatch"] += 1
            for f in failures:
                counters["lead_structure_detail"][f] = counters["lead_structure_detail"].get(f, 0) + 1
            continue
        if valid >= cutoff:
            counters["at_or_after_cutoff"] += 1
            continue
        logged_at = _parse_ts(entry.get("logged_at"))
        if valid in by_valid:
            first = by_valid[valid]
            counters["duplicate_valid_time"] += 1
            if logged_at is not None and first["logged_at"] is not None and logged_at < first["logged_at"]:
                counters["logged_at_inversions"] += 1
            duplicates.append({
                "line_no": line_no, "valid_time": valid.isoformat(),
                "logged_at": logged_at.isoformat() if logged_at is not None else None,
                "decision_time": decision.isoformat(), "kept_line_no": first["line_no"],
            })
            continue
        rec = {"line_no": line_no, "entry": entry, "valid_time": valid, "decision_time": decision,
               "initialization_time": init, "logged_at": logged_at}
        by_valid[valid] = rec
        kept.append(rec)

    counters["in_scope_rows"] = len(kept)
    return kept, counters, duplicates


def _candidate(entry: dict, name: str) -> Optional[dict]:
    cands = entry.get("candidates")
    cand = cands.get(name) if isinstance(cands, dict) else None
    return cand if isinstance(cand, dict) else None


def _classify_candidate(cand: Optional[dict]):
    """(status_label, exclusion_reason, value). The value is withheld whenever
    the candidate is not cleanly usable."""
    if cand is None:
        return "missing", "candidate_missing", float("nan")
    status = cand.get("status")
    if status == "unavailable":
        return "unavailable", "candidate_unavailable", float("nan")
    if status == "failed":
        return "failed", "candidate_failed", float("nan")
    if status != "ok":
        return "other", "candidate_failed", float("nan")
    if cand.get("fallback_used"):
        return "ok", "candidate_fallback_used", float("nan")
    value = cand.get("ampacity_amps")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return "ok", "candidate_null_or_nonfinite_value", float("nan")
    return "ok", None, float(value)


def _anchor_info(cand: Optional[dict]):
    ip = cand.get("input_provenance") if cand else None
    ap = ip.get("anchor_provenance") if isinstance(ip, dict) else None
    if not isinstance(ap, dict):
        return None, None, None
    return ap.get("anchor_source"), ap.get("anchor_station"), _parse_ts(ap.get("anchor_observation_time"))


def _reference_window_end(cand: Optional[dict]) -> Optional[pd.Timestamp]:
    ip = cand.get("input_provenance") if cand else None
    return _parse_ts(ip.get("truth_proxy_window_end")) if isinstance(ip, dict) else None


def select_rows(entries, city: str, guard_cfg: core.GuardConfig):
    """
    Row-level selection (see `_select_row_level`) and candidate-level
    classification. Returns (frame, counters, duplicates). One frame row per
    in-scope (city, valid_time); per candidate: `{name}__status`,
    `{name}__pred` (NaN unless cleanly usable), `{name}__excl`.
    """
    kept, counters, duplicates = _select_row_level(entries, guard_cfg)
    rows = []
    cand_excl = {name: {k: 0 for k in CANDIDATE_EXCLUSION_KEYS} for name in core.CANDIDATES}
    for rec in kept:
        entry = rec["entry"]
        row = {"city": city, "line_no": rec["line_no"], "valid_time": rec["valid_time"],
               "decision_time": rec["decision_time"], "initialization_time": rec["initialization_time"],
               "logged_at": rec["logged_at"]}
        for name in core.CANDIDATES:
            cand = _candidate(entry, name)
            status, reason, value = _classify_candidate(cand)
            row[f"{name}__status"] = status
            row[f"{name}__pred"] = value
            row[f"{name}__excl"] = reason
            if reason:
                cand_excl[name][reason] += 1
            if name in ANCHORED:
                src, station, obs = _anchor_info(cand)
                row[f"{name}__anchor_source"] = src
                row[f"{name}__anchor_station"] = station
                row[f"{name}__anchor_observation_time"] = obs
        row[f"{REFERENCE}__window_end"] = _reference_window_end(_candidate(entry, REFERENCE))
        rows.append(row)
    counters["candidate_exclusions_in_scope"] = cand_excl
    columns = ["city", "line_no", "valid_time", "decision_time", "initialization_time", "logged_at"]
    frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=columns)
    return frame, counters, duplicates


# --------------------------------------------------------------------------
# Reference own target hour and anchor breakdown
# --------------------------------------------------------------------------

def reference_target_hours(frame: pd.DataFrame) -> pd.DataFrame:
    """
    PD-11: target = round_half_up_to_hour(decision_time + 24 h), never
    interpolated. Returns a frame indexed like `frame` with `target`,
    `rounding_offset_s` (target minus the unrounded decision + 24 h) and
    `window_end_discrepancy_s` (target minus truth_proxy_window_end + 24 h,
    NaN when the provenance is absent).
    """
    out = []
    for _, row in frame.iterrows():
        raw = row["decision_time"] + pd.Timedelta(hours=core.LEAD_HOURS)
        target = core.round_half_up_to_hour(raw)
        end = row.get(f"{REFERENCE}__window_end")
        disc = float("nan")
        if end is not None and not pd.isna(end):
            disc = float((target - (end + pd.Timedelta(hours=core.LEAD_HOURS))).total_seconds())
        out.append({"target": target, "rounding_offset_s": float((target - raw).total_seconds()),
                    "window_end_discrepancy_s": disc})
    if not out:
        return pd.DataFrame({"target": pd.Series(dtype="datetime64[ns, UTC]"),
                             "rounding_offset_s": pd.Series(dtype=float),
                             "window_end_discrepancy_s": pd.Series(dtype=float)}, index=frame.index)
    return pd.DataFrame(out, index=frame.index)


def _summary(values) -> dict:
    arr = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if arr.size == 0:
        return {"n": 0, "min": None, "median": None, "mean": None, "max": None}
    return {"n": int(arr.size), "min": float(arr.min()), "median": float(np.median(arr)),
            "mean": float(arr.mean()), "max": float(arr.max())}


def anchor_breakdown(frame: pd.DataFrame, errors: dict) -> dict:
    """
    V1, exploratory and descriptive. Per anchored candidate: the realized
    anchor source/station mix, the distribution of anchor_age_h (decision -
    observation) and anchor_to_valid_h (valid - observation) per source, and
    that candidate's n, bias and MAE split by anchor_source over scored rows.
    `errors[cand]` is a Series of signed errors indexed by valid_time.
    """
    result = {"label": "exploratory; descriptive only; not a hypothesis test; no adjustment or reweighting",
              "candidates": {}}
    for cand in ANCHORED:
        col = f"{cand}__anchor_source"
        if frame.empty or col not in frame.columns:
            result["candidates"][cand] = {"by_source": {}}
            continue
        err = errors.get(cand)
        by_source: dict = {}
        sources = frame[col].where(frame[col].notna(), "unknown")
        for src in sorted(set(sources)):
            sub = frame.loc[sources == src]
            age = [(r["decision_time"] - r[f"{cand}__anchor_observation_time"]) / pd.Timedelta(hours=1)
                   if r[f"{cand}__anchor_observation_time"] is not None and not pd.isna(r[f"{cand}__anchor_observation_time"]) else None
                   for _, r in sub.iterrows()]
            to_valid = [(r["valid_time"] - r[f"{cand}__anchor_observation_time"]) / pd.Timedelta(hours=1)
                        if r[f"{cand}__anchor_observation_time"] is not None and not pd.isna(r[f"{cand}__anchor_observation_time"]) else None
                        for _, r in sub.iterrows()]
            stations = sub[f"{cand}__anchor_station"].where(sub[f"{cand}__anchor_station"].notna(), "unknown")
            entry = {"n_rows": int(len(sub)), "stations": {s: int((stations == s).sum()) for s in sorted(set(stations))},
                     "anchor_age_h": _summary(age), "anchor_to_valid_h": _summary(to_valid)}
            if err is not None and len(err):
                e = err.reindex(sub["valid_time"]).dropna()
                entry["scored"] = {k: v for k, v in core.descriptive_metrics(e.to_numpy(), np.zeros(len(e))).items()
                                   if k in ("n", "bias", "mae")}
            else:
                entry["scored"] = {"n": 0, "bias": None, "mae": None}
            by_source[src] = entry
        result["candidates"][cand] = {"by_source": by_source}
    return result


# --------------------------------------------------------------------------
# Count-only (mechanical health check)
# --------------------------------------------------------------------------

def _status_label(cand: Optional[dict]) -> str:
    if cand is None:
        return "missing"
    status = cand.get("status")
    return status if status in ("ok", "unavailable", "failed") else "other"


def count_only_report(predictions_dir: str, cities, guard_cfg: core.GuardConfig) -> dict:
    """
    Status, timestamps and counts only. Never consults the instant gate, never
    fetches truth, never uses `ampacity_amps`, and lists every non-selected
    .jsonl file (the legacy corridor logs) as not read.
    """
    out_cities = {}
    pooled_rows = 0
    pooled_status = {name: {s: 0 for s in STATUS_LABELS} for name in core.CANDIDATES}
    wanted = {f"{c}.jsonl" for c in cities}
    not_read = []
    if os.path.isdir(predictions_dir):
        not_read = sorted(f for f in os.listdir(predictions_dir) if f.endswith(".jsonl") and f not in wanted)
    for city in cities:
        path = os.path.join(predictions_dir, f"{city}.jsonl")
        entries, reader = read_scorable_log(path, city)
        kept, sel, dups = _select_row_level(entries, guard_cfg)
        counters = {**{k: reader.get(k, 0) for k in READER_COUNTER_KEYS}, **{k: sel[k] for k in ROW_EXCLUSION_KEYS},
                    "in_scope_rows": sel["in_scope_rows"], "logged_at_inversions": sel["logged_at_inversions"]}
        if reader.get("file_missing"):
            counters["file_missing"] = True
        hours = {}
        gaps = []
        status_counts = {name: {s: 0 for s in STATUS_LABELS} for name in core.CANDIDATES}
        for rec in kept:
            hours[f"{rec['valid_time'].hour:02d}"] = hours.get(f"{rec['valid_time'].hour:02d}", 0) + 1
            gaps.append((rec["valid_time"] - rec["decision_time"]) / pd.Timedelta(hours=1))
            for name in core.CANDIDATES:
                label = _status_label(_candidate(rec["entry"], name))
                status_counts[name][label] += 1
                pooled_status[name][label] += 1
        pooled_rows += len(kept)
        n = len(kept)
        out_cities[city] = {
            "counters": counters,
            "forecast_model_counts": sel["forecast_model_counts"],
            "other_forecast_model_by_model": sel["other_forecast_model_by_model"],
            "lead_structure_detail": sel["lead_structure_detail"],
            "valid_hour_histogram": dict(sorted(hours.items())),
            "decision_to_valid_gap_hours": {
                "min": float(min(gaps)) if gaps else None,
                "median": float(np.median(gaps)) if gaps else None,
                "max": float(max(gaps)) if gaps else None,
            },
            "candidate_status_counts": status_counts,
            "duplicates_excluded": dups,
            "progress": {
                "in_scope_rows": n,
                "tail_rate_target": {"rows": core.TAIL_RATE_TARGET_ROWS, "fraction": n / core.TAIL_RATE_TARGET_ROWS},
                "mdd_target": {"rows": core.MDD_TARGET_ROWS, "fraction": n / core.MDD_TARGET_ROWS},
            },
        }
    return {
        "mode": "count_only",
        "row_source": ROW_SOURCE,
        "note": "status, timestamps and counts only; no truth fetched; no logged ampacity read or summarized",
        "valid_time_cutoff": core.iso(guard_cfg.valid_time_cutoff),
        "cities": out_cities,
        "pooled_nominal": {
            "label": "nominal, not effective",
            "in_scope_rows": pooled_rows,
            "candidate_status_counts": pooled_status,
            "tail_rate_target": {"rows": core.TAIL_RATE_TARGET_ROWS},
            "mdd_target": {"rows": core.MDD_TARGET_ROWS},
        },
        "not_read_files": not_read,
    }


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def _fetch_window(times, cutoff: pd.Timestamp):
    start = min(times).floor("D")
    end = max(times).floor("D")
    last_allowed = (cutoff - pd.Timedelta(days=1)).floor("D")
    end = min(end, last_allowed)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _join_and_score(frame: pd.DataFrame, targets: pd.DataFrame, truth: Optional[pd.Series],
                    fetch_failed: bool, cutoff: pd.Timestamp):
    """Join truth on the exact hour only; classify row-level truth exclusions
    and candidate-level exclusions among rows with truth. Returns
    (scored frame of rows with truth, counters)."""
    counters = {k: 0 for k in TRUTH_EXCLUSION_KEYS}
    cand_excl = {name: {k: 0 for k in CANDIDATE_EXCLUSION_KEYS} for name in core.CANDIDATES}
    cand_excl[REFERENCE].update({k: 0 for k in REFERENCE_EXTRA_EXCLUSION_KEYS})
    rows = []
    for idx, row in frame.iterrows():
        if fetch_failed or truth is None:
            counters["truth_fetch_failed"] += 1
            continue
        valid = row["valid_time"]
        if valid not in truth.index:
            counters["truth_missing"] += 1
            continue
        t_valid = float(truth.loc[valid])
        out = {"valid_time": valid, "truth_valid": t_valid}
        for name in core.CANDIDATES:
            reason = row[f"{name}__excl"]
            if isinstance(reason, float) and np.isnan(reason):
                reason = None
            pred = row[f"{name}__pred"]
            scored_truth = t_valid
            if name == REFERENCE:
                target = targets.loc[idx, "target"]
                out["reference_target"] = target
                if reason is None:
                    if target >= cutoff:
                        reason = "reference_target_at_or_after_cutoff"
                    elif target not in truth.index:
                        reason = "reference_target_truth_missing"
                    else:
                        scored_truth = float(truth.loc[target])
                        out["reference_logged_hour_pred"] = pred
                        out["reference_logged_hour_truth"] = t_valid
            if reason is not None:
                cand_excl[name][reason] += 1
                pred = float("nan")
            out[f"{name}__pred"] = pred
            out[f"{name}__truth"] = scored_truth if reason is None else float("nan")
        rows.append(out)
    counters["candidate_exclusions"] = cand_excl
    scored = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["valid_time"])
    if not scored.empty:
        scored = scored.set_index("valid_time", drop=False)
    return scored, counters


def _city_error_frame(scored: pd.DataFrame) -> pd.DataFrame:
    """Signed errors (prediction - truth), one column per candidate, indexed by
    valid_time (NaN where not scored). The reference column is its own-target-hour error."""
    cols = {}
    for name in core.CANDIDATES:
        if scored.empty:
            cols[name] = pd.Series(dtype=float)
        else:
            cols[name] = scored[f"{name}__pred"] - scored[f"{name}__truth"]
    frame = pd.DataFrame(cols)
    if not scored.empty:
        frame["slot"] = scored["valid_time"]
    return frame


def score(predictions_dir: str, *, cities, guard_cfg: core.GuardConfig, evidence_root: str,
          protocol_status: str = "unsigned", now=None, source_commit: Optional[str] = None,
          params: Optional[dict] = None, repo_root: Optional[str] = None) -> dict:
    """
    Order: read and select; compute the scope valid times (valid times plus the
    reference's own target hours); `check_guard`; create the evidence
    directory; one archive fetch per city; exact-hour truth join; descriptive
    metrics; diagnostics; report. Corridor files are never opened.
    """
    params = core.default_params() if params is None else {**core.default_params(), **params}
    now_ts = core.utc_now_or(now)
    cutoff = core.to_utc(guard_cfg.valid_time_cutoff)
    cities = list(cities)

    per_city_inputs = {}
    scope_times: list[pd.Timestamp] = []
    for city in cities:
        entries, reader = read_scorable_log(os.path.join(predictions_dir, f"{city}.jsonl"), city)
        frame, sel, dups = select_rows(entries, city, guard_cfg)
        targets = reference_target_hours(frame) if not frame.empty else pd.DataFrame(index=frame.index)
        city_times = list(frame["valid_time"]) if not frame.empty else []
        if not frame.empty:
            for idx in frame.index:
                if frame.loc[idx, f"{REFERENCE}__excl"] is None and targets.loc[idx, "target"] < cutoff:
                    city_times.append(targets.loc[idx, "target"])
        scope_times.extend(city_times)
        per_city_inputs[city] = {"reader": reader, "frame": frame, "sel": sel, "dups": dups,
                                 "targets": targets, "times": city_times}

    nd = core.nondefault_params(params)
    guard_record = core.check_guard(guard_cfg, valid_times=scope_times, row_source=ROW_SOURCE, now=now_ts,
                                    evidence_root=evidence_root, nondefault_params=nd)
    config_record = {
        "predictions_dir": predictions_dir, "cities": cities, "protocol_status": protocol_status,
        "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in params.items()},
        "evidence_root": evidence_root, "source_commit": source_commit,
    }
    evidence_dir = core.new_evidence_dir(evidence_root, ROW_SOURCE, now_ts, guard_record, config_record)
    root = repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prov = core.provenance(root, cities, source_commit)
    report = core.new_report(row_source=ROW_SOURCE, basis=guard_record["basis"], protocol_status=protocol_status,
                             guard=guard_record, config_record=config_record, prov=prov, params=params)

    error_frames: dict = {}
    logged_reading_frames: dict = {}
    scored_by_city: dict = {}
    for city in cities:
        inp = per_city_inputs[city]
        frame, targets, sel = inp["frame"], inp["targets"], inp["sel"]
        truth_series = None
        fetch_meta = None
        dropped = []
        fetch_failed = False
        if inp["times"]:
            start, end = _fetch_window(inp["times"], cutoff)
            weather, fetch_meta = core.fetch_archive_truth(city, start, end, evidence_dir=evidence_dir)
            if weather is None:
                fetch_failed = True
            else:
                truth_df, dropped = core.truth_ampacity(weather, city)
                truth_series = truth_df.set_index("datetime_utc")["truth_amps"]
        scored, tcount = _join_and_score(frame, targets, truth_series, fetch_failed, cutoff) if not frame.empty else (
            pd.DataFrame(columns=["valid_time"]), {**{k: 0 for k in TRUTH_EXCLUSION_KEYS},
                                                   "candidate_exclusions": {n: {} for n in core.CANDIDATES}})
        scored_by_city[city] = scored
        error_frames[city] = _city_error_frame(scored)

        metrics = {}
        n_scored = {}
        for name in core.CANDIDATES:
            if scored.empty:
                metrics[name] = core.descriptive_metrics([], [])
            else:
                mask = scored[f"{name}__pred"].notna()
                metrics[name] = core.descriptive_metrics(scored.loc[mask, f"{name}__pred"].to_numpy(),
                                                         scored.loc[mask, f"{name}__truth"].to_numpy())
            n_scored[name] = metrics[name]["n"]
        logged_reading = None
        if not scored.empty and "reference_logged_hour_pred" in scored.columns:
            mask = scored["reference_logged_hour_pred"].notna() & scored[f"{REFERENCE}__pred"].notna()
            logged_reading = {**core.descriptive_metrics(scored.loc[mask, "reference_logged_hour_pred"].to_numpy(),
                                                         scored.loc[mask, "reference_logged_hour_truth"].to_numpy()),
                              "flag": core.FLAG_V2_LOGGED}
        logged_reading = logged_reading or {**core.descriptive_metrics([], []), "flag": core.FLAG_V2_LOGGED}
        row_excl = {k: sel[k] for k in ROW_EXCLUSION_KEYS}
        row_excl.update({k: tcount[k] for k in TRUTH_EXCLUSION_KEYS})
        n_in_scope = int(sel["in_scope_rows"])
        n_with_truth = int(len(scored))
        accounting = {
            "lines_accepted_equals_exclusions_plus_in_scope":
                inp["reader"]["accepted_rows"] == sum(sel[k] for k in ROW_EXCLUSION_KEYS) + n_in_scope,
            "in_scope_equals_truth_exclusions_plus_with_truth":
                n_in_scope == sum(tcount[k] for k in TRUTH_EXCLUSION_KEYS) + n_with_truth,
            "per_candidate_with_truth_equals_scored_plus_exclusions": {
                name: n_with_truth == n_scored[name] + sum(tcount["candidate_exclusions"].get(name, {}).values())
                for name in core.CANDIDATES} if n_with_truth else {},
        }
        report["per_city"][city] = {
            "n_in_scope": n_in_scope, "n_with_truth": n_with_truth, "n_scored": n_scored,
            "excluded_by_reason": {k: v for k, v in row_excl.items() if v},
            "candidate_exclusions": {n: {k: v for k, v in d.items() if v}
                                     for n, d in tcount["candidate_exclusions"].items()},
            "metrics": metrics, "reference_logged_hour_reading": logged_reading,
            "truth_label": core.TRUTH_LABEL,
        }
        report["exclusions"][city] = {
            "reader": {k: inp["reader"].get(k, 0) for k in READER_COUNTER_KEYS},
            "row_level": {k: sel[k] for k in ROW_EXCLUSION_KEYS},
            "truth": {k: tcount[k] for k in TRUTH_EXCLUSION_KEYS},
            "candidate_level": tcount["candidate_exclusions"],
            "other_forecast_model_by_model": sel["other_forecast_model_by_model"],
            "lead_structure_detail": sel["lead_structure_detail"],
            "duplicates_excluded": inp["dups"],
            "accounting": accounting,
        }
        errs = {name: error_frames[city][name].dropna() for name in ANCHORED if name in error_frames[city]}
        tgt = {}
        if not targets.empty:
            tgt = {
                "rounding_offset_s_max_abs": float(targets["rounding_offset_s"].abs().max()),
                "window_end_discrepancy_s": _summary(targets["window_end_discrepancy_s"].tolist()),
            }
        hours = {}
        gaps = []
        if not frame.empty:
            for _, r in frame.iterrows():
                hours[f"{r['valid_time'].hour:02d}"] = hours.get(f"{r['valid_time'].hour:02d}", 0) + 1
                gaps.append((r["valid_time"] - r["decision_time"]) / pd.Timedelta(hours=1))
        report["diagnostics"][city] = {
            "forecast_model_counts": sel["forecast_model_counts"],
            "valid_hour_histogram": dict(sorted(hours.items())),
            "decision_to_valid_gap_hours": _summary(gaps),
            "logged_at_inversions": sel["logged_at_inversions"],
            "reference_target_hour": tgt,
            "reference_headline": "own target hour (decision_time + 24 h, nearest whole hour)",
            "anchor_breakdown": anchor_breakdown(frame, errs),
            "truth_fetch": ({k: fetch_meta[k] for k in ("url", "params", "start_date", "end_date", "error", "n_hours")}
                            if fetch_meta else None),
            "truth_dropped_null_hours": dropped,
        }

    pooled = {name: int(sum(report["per_city"][c]["n_scored"][name] for c in cities)) for name in core.CANDIDATES}
    report["sample_size"] = {
        "per_city": {c: {"n_in_scope": report["per_city"][c]["n_in_scope"],
                         "n_scored": report["per_city"][c]["n_scored"],
                         "targets": core.precision_targets(max(report["per_city"][c]["n_scored"].values(), default=0))}
                     for c in cities},
        "pooled_nominal": {"label": "nominal, not effective", "n_scored": pooled,
                           "targets": core.precision_targets(max(pooled.values(), default=0))},
    }
    report = _attach_family_and_decision(report, error_frames, params, protocol_status)
    report["evidence"] = core.collect_evidence(evidence_dir)
    report["evidence_dir"] = evidence_dir
    paths = core.write_report(report, evidence_dir)
    report["report_paths"] = paths
    return report


def _attach_family_and_decision(report: dict, error_frames: dict, params: dict, protocol_status: str) -> dict:
    """The 9-test pooled Holm family, the sample-size block and the ship rule
    (live-system check: this report never changes the headline decision)."""
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


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="forecast_shadow_score", description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--predictions-dir", default=os.path.join("data", "shadow", "predictions"))
    p.add_argument("--cities", nargs="+", default=list(config.LOCATIONS))
    p.add_argument("--count-only", action="store_true",
                   help="status-only counts; no truth fetched, no ampacity read; allowed at any time")
    p.add_argument("--out", default=None, help="write the count-only JSON (or a copy of report.json) here")
    p.add_argument("--evidence-root", default=core.EVIDENCE_ROOT_DEFAULT)
    p.add_argument("--source-commit", default=None, help="commit of the exported logs (git rev-parse origin/shadow-collection-data)")
    p.add_argument("--evaluation-instant", default=None)
    p.add_argument("--valid-time-cutoff", default=None)
    p.add_argument("--override-reason", default=None)
    p.add_argument("--protocol-status", choices=("signed", "unsigned"), default="unsigned")
    # Pre-registered statistical parameters. Any non-default value in a FRESH run needs --override-reason.
    # There is deliberately no --row-gate and no --family-size (decisions 2 and 3).
    p.add_argument("--block-lengths", type=int, nargs="+", default=None, help="six-hourly slot block lengths (default 1 4 8 28)")
    p.add_argument("--n-resamples", type=int, default=None)
    p.add_argument("--decision-margin-amps", type=float, default=None)
    p.add_argument("--consistency-min-cities", type=int, default=None)
    p.add_argument("--min-paired-rows", type=int, default=None)
    p.add_argument("--power", type=float, default=None)
    p.add_argument("--seed", type=int, default=None)
    return p


def _guard_from_args(args) -> core.GuardConfig:
    kwargs = {}
    if args.evaluation_instant:
        kwargs["evaluation_instant"] = core.to_utc(args.evaluation_instant)
    if args.valid_time_cutoff:
        kwargs["valid_time_cutoff"] = core.to_utc(args.valid_time_cutoff)
    return core.GuardConfig(override_reason=args.override_reason, **kwargs)


def _params_from_args(args) -> Optional[dict]:
    mapping = {"block_lengths": args.block_lengths, "n_resamples": args.n_resamples,
               "decision_margin_amps": args.decision_margin_amps, "consistency_min_cities": args.consistency_min_cities,
               "min_paired_rows": args.min_paired_rows, "power": args.power, "seed": args.seed}
    given = {k: (tuple(v) if k == "block_lengths" else v) for k, v in mapping.items() if v is not None}
    return given or None


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    bad = [c for c in args.cities if c not in config.LOCATIONS]
    if bad:
        print(f"error: unknown cities {bad}; valid: {list(config.LOCATIONS)}", file=sys.stderr)
        return 2
    try:
        guard_cfg = _guard_from_args(args)
        if args.count_only:
            report = count_only_report(args.predictions_dir, args.cities, guard_cfg)
            text = core.dumps(report, indent=2)
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    fh.write(text)
            else:
                print(text)
            for city, block in report["cities"].items():
                c = block["counters"]
                print(f"{city}: accepted {c['accepted_rows']}, in scope {c['in_scope_rows']}, "
                      f"missing_forecast_model {c['missing_forecast_model']}, "
                      f"other_forecast_model {c['other_forecast_model']}", file=sys.stderr)
            return 0
        report = score(args.predictions_dir, cities=args.cities, guard_cfg=guard_cfg,
                       evidence_root=args.evidence_root, protocol_status=args.protocol_status,
                       source_commit=args.source_commit, params=_params_from_args(args))
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(core.dumps(report, indent=2))
        print(f"evidence directory: {report['evidence_dir']}")
        return 0
    except (core.EvaluationGuardError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
