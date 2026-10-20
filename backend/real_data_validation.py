"""
Real-data validation analysis (Phase 3, offline)
=================================================
Turns the files a real backfill run leaves behind into the tables the owner
reads. VAL-01 (what the pipeline reports against the static rating, the rating
bounds and its own gates) is implemented here; VAL-02 (forecast and detector
behaviour) is implemented below the VAL-01 code.

Inputs, all named on the command line and read only:
  * the archive CSV the backfill wrote (`historical_archive` format)
  * the trace JSONL the backfill wrote with `--trace-path` (schema
    `backfill_trace/1`: what `run_city_pipeline` returned for every city and
    step, including the observation it rated and the provider of each input)
  * the backfill log CSV (`backfill_archive._LOG_HEADER`)

This module is offline: it never touches the network or the .env file, and it
never modifies an input. Every number it reports is PROVISIONAL (OD-5): the
static ratings, plausibility bounds and line bearings are assumptions the owner
has not yet confirmed. The module measures and reports; it changes no rating
policy.

Subcommands (run from the repository root with PYTHONPATH=backend):
  completeness  per-city step counts: trace records, archive rows, log rows,
                exhausted, errors, no_trace, missing
  manifest      deterministic JSON record of the validated run (window, backfill
                argv after a literal `--`, file and model hashes, git HEAD)
  report        VAL-01 and VAL-02 tables, report_meta.json and tables.md; exits 1
                when a self-check counts a disagreement between trace, archive
                and the recomputed ampacity

    python backend/real_data_validation.py completeness --archive A --trace T \\
        --log L --start 2026-09-07T00:00:00Z --end 2026-09-27T23:00:00Z --out OUT.csv
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

import ampacity_forecast
import anomaly_detector
import city_point
import config
import data_cleaning
import historical_archive
import thermal_model
from DLRSafetyMonitor import DLRSafetyMonitor

TRACE_SCHEMA = "backfill_trace/1"
MANIFEST_SCHEMA = "real_data_validation_manifest/1"
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The command the owner runs for the real backfill. The .env file uses
# `KEY = value` spacing a shell cannot source, so it goes through python-dotenv
# inside the child interpreter. This is only text: this module never imports
# python-dotenv and never reads the env file.
OWNER_COMMAND_TEMPLATE = (
    "cd /Users/aphan/Senior_Design && PYTHONPATH=backend "
    "/Users/aphan/Senior_Design/.venv/bin/python -c "
    "\"from dotenv import load_dotenv; load_dotenv('/Users/aphan/Senior_Design/.env'); "
    "import sys, backfill_archive; sys.exit(backfill_archive.main({argv}))\""
)

COMPLETENESS_COLUMNS = [
    "city", "expected_steps", "trace_records", "archive_rows", "log_rows",
    "exhausted", "errors", "no_trace", "missing",
]


# ──────────────────────────────────────────────────────────────────────────────
# Window and loading
# ──────────────────────────────────────────────────────────────────────────────

def _utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def expected_steps(start, end, step_hours: float = 1.0) -> pd.DatetimeIndex:
    """
    The UTC steps a backfill over [start, end] attempts, inclusive of both ends,
    built exactly the way `backfill_archive.backfill` builds its `times`.
    """
    return pd.date_range(_utc(start), _utc(end), freq=pd.Timedelta(hours=step_hours))


_PIPELINE_COLUMNS = {
    "history_rows": "history_rows",
    "usable_history_rows": "usable_history_rows",
    "forecast_used_by_g6": "forecast_used_by_g6",
    "detector_signal": "detector_signal",
    "detector_model": "detector_model",
}
_FORECAST_COLUMNS = {
    "amps": "fc_amps", "ci_lower_amps": "fc_ci_lower", "ci_upper_amps": "fc_ci_upper",
    "n_observations": "fc_n_observations", "horizon_min": "fc_horizon_min",
}
_OBSERVATION_COLUMNS = {
    "temp": "obs_temp", "wind": "obs_wind", "wind_raw": "obs_wind_raw",
    "wind_direction": "obs_wind_direction", "solar": "obs_solar",
}
_SOURCE_COLUMNS = {
    "air_temp": "temp_source", "wind_speed": "wind_source", "solar_radiation": "solar_source",
}


def _flatten_record(record: dict) -> dict:
    """A trace record with its nested dicts spread into flat columns."""
    flat = {k: v for k, v in record.items()
            if k not in ("observation", "sources", "pipeline")}
    obs = record.get("observation") or {}
    for key, column in _OBSERVATION_COLUMNS.items():
        flat[column] = obs.get(key)
    sources = record.get("sources") or {}
    for key, column in _SOURCE_COLUMNS.items():
        flat[column] = sources.get(key)
    pipeline = record.get("pipeline") or {}
    forecast = pipeline.get("forecast") or {}
    for key, column in _FORECAST_COLUMNS.items():
        flat[column] = forecast.get(key)
    for key, column in _PIPELINE_COLUMNS.items():
        flat[column] = pipeline.get(key)
    for key, value in pipeline.items():
        if key != "forecast" and key not in _PIPELINE_COLUMNS:
            flat[f"pipeline_{key}"] = value
    return flat


def load_trace(path) -> pd.DataFrame:
    """
    One row per (city, run_end_utc) of the trace, flattened to columns, with
    `run_end_utc` parsed to UTC Timestamps. A resumed backfill re-rates steps
    that errored or were exhausted, so the same (city, step) can appear more
    than once; the LAST record in file order wins. `DataFrame.attrs` carries
    `{"duplicates": n, "records": n}` (records read, records dropped as
    superseded).
    """
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(_flatten_record(json.loads(line)))
    frame = pd.DataFrame(records)
    if "run_end_utc" not in frame.columns:
        frame["run_end_utc"] = pd.Series(dtype="datetime64[ns, UTC]")
    if "city" not in frame.columns:
        frame["city"] = pd.Series(dtype=object)
    frame["run_end_utc"] = pd.to_datetime(frame["run_end_utc"], utc=True)
    before = len(frame)
    frame = frame.drop_duplicates(subset=["city", "run_end_utc"], keep="last").reset_index(drop=True)
    frame.attrs = {"duplicates": before - len(frame), "records": before}
    return frame


def count_out_of_window(trace: pd.DataFrame, steps) -> int:
    """Trace records whose step is not one of the expected `steps`."""
    if len(trace) == 0:
        return 0
    return int((~trace["run_end_utc"].isin(pd.DatetimeIndex(steps))).sum())


def _read_log(path) -> pd.DataFrame:
    log = pd.read_csv(path, dtype=str)
    log["run_end_utc"] = pd.to_datetime(log["run_end_utc"], utc=True)
    return log


def _slots(frame: pd.DataFrame, city: str, time_col: str, steps) -> pd.Series:
    """The `time_col` instants of `city`'s rows that are expected steps."""
    if len(frame) == 0 or "city" not in frame.columns:
        return pd.Series([], dtype="datetime64[ns, UTC]")
    times = frame.loc[frame["city"] == city, time_col]
    return times[times.isin(steps)]


def _archive_instants(archive: pd.DataFrame) -> pd.DataFrame:
    out = archive.copy()
    out["_instant"] = pd.to_datetime(out["datetime_utc"], utc=True, format="ISO8601", errors="coerce")
    return out


def completeness_table(trace, archive, log, cities, steps) -> pd.DataFrame:
    """
    One row per city (in `cities` order), counted over the expected `steps` only:
    how many steps have a trace record, an archive row and a log row, how many
    traced steps were exhausted or errored, how many archived steps have no trace
    record (`no_trace`) and how many have neither trace nor archive row (`missing`).
    """
    steps = pd.DatetimeIndex(steps)
    archive = _archive_instants(archive)
    log = log.copy()
    rows = []
    for city in cities:
        trace_city = trace[trace["city"] == city] if len(trace) and "city" in trace.columns else trace.iloc[0:0]
        in_window = trace_city[trace_city["run_end_utc"].isin(steps)]
        traced = set(in_window["run_end_utc"])
        archived = set(_slots(archive, city, "_instant", steps))
        n_exhausted = int(in_window["exhausted"].fillna(False).astype(bool).sum()) if "exhausted" in in_window else 0
        n_errors = int(in_window["error"].notna().sum()) if "error" in in_window else 0
        rows.append({
            "city": city,
            "expected_steps": int(len(steps)),
            "trace_records": int(len(in_window)),
            "archive_rows": int(len(_slots(archive, city, "_instant", steps))),
            "log_rows": int(len(_slots(log, city, "run_end_utc", steps))),
            "exhausted": n_exhausted,
            "errors": n_errors,
            "no_trace": len(archived - traced),
            "missing": int(len(steps)) - len(archived | traced),
        })
    return pd.DataFrame(rows, columns=COMPLETENESS_COLUMNS)


# ──────────────────────────────────────────────────────────────────────────────
# VAL-01: computed vs reported ratings, bounds and gate outcomes
# ──────────────────────────────────────────────────────────────────────────────

OUTCOMES = ("ok", "G1", "G2", "G3", "G4_low", "G4_high", "G5", "G6", "EXHAUSTED", "ERROR", "NO_TRACE", "MISSING")
PERIODS = ("warmup", "scored")
FALLBACK_OUTCOMES = ("G1", "G2", "G3", "G4_low", "G4_high", "G5", "G6", "EXHAUSTED")
_GATE_ORDER = ("G1", "G2", "G3", "G4", "G5", "G6", "EXHAUSTED")
_NO_COMPUTED_GATES = ("G1", "G2", "G3")  # the observation never reached the ampacity formula
TOLERANCE_A = 1e-6
_AMP_DECIMALS, _RATE_DECIMALS, _INPUT_DECIMALS = 1, 4, 3
_QUANTILES = (("min", 0.0), ("p05", 0.05), ("p25", 0.25), ("p50", 0.5), ("p75", 0.75),
              ("p95", 0.95), ("max", 1.0))
_PASS_THROUGH_PREFIXES = ("fc_", "detector_", "pipeline_")
_PASS_THROUGH_NAMES = ("history_rows", "usable_history_rows", "forecast_used_by_g6")
_OBS_COLUMNS = ("obs_temp", "obs_wind", "obs_wind_raw", "obs_wind_direction", "obs_solar")
_LABEL = ("PROVISIONAL (OD-5): static ratings, rating bounds and line bearings are unconfirmed "
          "assumptions; these tables measure, they do not decide.")


def bound_class(value, lower, upper):
    """'within' (inclusive at both bounds, as `DLRSafetyMonitor._gate_plausible`), 'below', 'above'; None for NaN."""
    if value is None or pd.isna(value):
        return None
    if value < lower:
        return "below"
    if value > upper:
        return "above"
    return "within"


def period_of(ts, start, warmup_hours) -> str:
    """'scored' when `ts >= start + warmup_hours`, else 'warmup'."""
    return "scored" if _utc(ts) >= _utc(start) + pd.Timedelta(hours=warmup_hours) else "warmup"


def _solar_altitude_deg(point) -> float:
    """The solar altitude G4 judged with: the monitor's own default."""
    return DLRSafetyMonitor(
        static_rating=point.static_rating, conductor=point.conductor).solar_altitude_deg


def computed_amps(city, temp, wind_perp, solar) -> np.ndarray:
    """
    The pre-gate ampacity of an observation: `thermal_model.ieee738_ampacity`
    with the city's own conductor at the safety monitor's solar altitude, i.e.
    the figure gate G4 judged. `wind_perp` is the projected (line-perpendicular)
    component, as stored in the trace and the archive.
    """
    point = city_point.city_point(city)
    return np.asarray(thermal_model.ieee738_ampacity(
        T_amb_c=np.asarray(temp, dtype=float), wind_perp_ms=np.asarray(wind_perp, dtype=float),
        ghi_wm2=np.asarray(solar, dtype=float), conductor=point.conductor,
        solar_altitude_deg=_solar_altitude_deg(point)), dtype=float)


def _num(value) -> float:
    try:
        return float("nan") if value is None else float(value)
    except (TypeError, ValueError):
        return float("nan")


def _truthy(value) -> bool:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    return bool(value)


def _text(value):
    return None if value is None or (isinstance(value, float) and np.isnan(value)) else value


def _gates_of(record: dict) -> list:
    """Gate names of a fallback record: `fallback_gates`, else each alert's first token."""
    gates = record.get("fallback_gates")
    if not isinstance(gates, (list, tuple, np.ndarray)) or len(gates) == 0:
        alerts = record.get("alerts")
        alerts = alerts if isinstance(alerts, (list, tuple, np.ndarray)) else []
        gates = [str(a).split()[0] for a in alerts if str(a).strip()]
    return [str(g) for g in gates]


def _first_gate(gates):
    known = [g for g in _GATE_ORDER if g in gates]
    return known[0] if known else None


def classify_steps(trace, archive, cities, steps, start, warmup_hours) -> pd.DataFrame:
    """
    One row per (city, step) of the window: its period, exactly one outcome from
    OUTCOMES, the reported and recomputed ampacity, the static rating and bounds,
    the bound class of the computed value, the fallback direction and the traced
    inputs. Nothing is dropped: a step with no trace record is NO_TRACE when the
    archive holds a row for it and MISSING otherwise, so an unfavourable step
    cannot vanish from a denominator.

    The computed value is recomputed from the traced observation with the city's
    own conductor (`computed_amps`); it is NaN for G1-G3 (the observation never
    reached the formula) and when the step has no observation. A G4 record whose
    recomputed value is inside the bounds contradicts its own gate and is
    classed ERROR (and counted by `computed_vs_reported_mismatches`).
    """
    steps = pd.DatetimeIndex(steps)
    start = _utc(start)
    archived = set()
    if archive is not None and len(archive):
        instants = _archive_instants(archive)
        archived = set(zip(instants["city"], instants["_instant"]))
    records = {}
    if len(trace):
        for rec in trace.to_dict("records"):  # file order; the last record of a slot wins
            records[(rec["city"], rec["run_end_utc"])] = rec
    carried = [c for c in (trace.columns if len(trace) else [])
               if c.startswith(_PASS_THROUGH_PREFIXES) or c in _PASS_THROUGH_NAMES]

    rows = []
    for city in cities:
        point = city_point.city_point(city)
        lower, upper = point.rating_bounds
        for ts in steps:
            rec = records.get((city, ts))
            row = {"city": city, "run_end_utc": ts, "period": period_of(ts, start, warmup_hours),
                   "kind": None, "gate": None, "reported_a": float("nan"),
                   "computed_a": float("nan"), "static_a": float(point.static_rating),
                   "lower_a": float(lower), "upper_a": float(upper)}
            for col in _OBS_COLUMNS:
                row[col] = float("nan")
            row.update(temp_source=None, wind_source=None, solar_source=None,
                       observation_hour=None, alerts="")
            for col in carried:
                row[col] = None
            if rec is None:
                row["kind"] = "no_trace" if (city, ts) in archived else "missing"
            else:
                static = _num(rec.get("static_rating_a"))
                if not np.isnan(static):
                    row["static_a"] = static
                row["reported_a"] = _num(rec.get("rating_a"))
                for col in _OBS_COLUMNS:
                    row[col] = _num(rec.get(col))
                for col in ("temp_source", "wind_source", "solar_source", "observation_hour"):
                    row[col] = _text(rec.get(col))
                for col in carried:
                    row[col] = rec.get(col)
                alerts = rec.get("alerts")
                row["alerts"] = " | ".join(str(a) for a in alerts) if isinstance(
                    alerts, (list, tuple, np.ndarray)) else ""
                if _text(rec.get("error")) is not None:
                    row["kind"] = "error"
                elif _truthy(rec.get("exhausted")):
                    row["kind"] = "exhausted"
                elif not _truthy(rec.get("fallback")):
                    row["kind"] = "ok"
                else:
                    row["kind"] = "fallback"
                    row["gate"] = _first_gate(_gates_of(rec))
            rows.append(row)

    frame = pd.DataFrame(rows)
    _fill_computed(frame)
    outcomes, classes, directions, overstatements = [], [], [], []
    for row in frame.itertuples(index=False):
        outcome, klass, direction, over = _outcome_of(row)
        outcomes.append(outcome)
        classes.append(klass)
        directions.append(direction)
        overstatements.append(over)
    frame["outcome"], frame["bound_class"] = outcomes, classes
    frame["direction"], frame["overstatement_a"] = directions, overstatements
    wind_raw = frame["obs_wind_raw"]
    frame["perp_fraction"] = np.where(wind_raw > 0, frame["obs_wind"] / wind_raw.where(wind_raw > 0), np.nan)
    hours = pd.to_datetime(frame["observation_hour"], utc=True, errors="coerce")
    frame["observation_lag_h"] = (frame["run_end_utc"] - hours).dt.total_seconds() / 3600.0
    first = ["city", "run_end_utc", "period", "outcome", "reported_a", "computed_a", "static_a",
             "lower_a", "upper_a", "bound_class", "direction", "overstatement_a", *_OBS_COLUMNS,
             "perp_fraction", "observation_lag_h", "temp_source", "wind_source", "solar_source",
             "observation_hour", "alerts"]
    return frame[first + carried]


def _fill_computed(frame: pd.DataFrame) -> None:
    """Recompute the pre-gate ampacity, per city and vectorised, for every step that reached G4."""
    for city, part in frame.groupby("city", sort=False):
        usable = part["kind"].isin(("ok", "fallback")) & ~part["gate"].isin(_NO_COMPUTED_GATES)
        inputs = part[["obs_temp", "obs_wind", "obs_solar"]]
        usable &= inputs.notna().all(axis=1)
        if usable.any():
            frame.loc[part.index[usable.values], "computed_a"] = computed_amps(
                city, inputs.loc[usable, "obs_temp"].to_numpy(), inputs.loc[usable, "obs_wind"].to_numpy(),
                inputs.loc[usable, "obs_solar"].to_numpy())


def _outcome_of(row):
    """(outcome, bound_class, direction, overstatement_a) of one classified step."""
    klass = bound_class(row.computed_a, row.lower_a, row.upper_a)
    simple = {"missing": "MISSING", "no_trace": "NO_TRACE", "error": "ERROR", "exhausted": "EXHAUSTED"}
    if row.kind in simple:
        return simple[row.kind], klass, "unknown", float("nan")
    if row.kind == "ok":
        return "ok", klass, "none", float("nan")
    gate = row.gate
    if gate == "G4":
        outcome = {"below": "G4_low", "above": "G4_high"}.get(klass, "ERROR")
    elif gate in ("G1", "G2", "G3", "G5", "G6", "EXHAUSTED"):
        outcome = gate
    else:
        outcome = "ERROR"  # a fallback whose gate cannot be named
    if gate in _NO_COMPUTED_GATES or gate == "EXHAUSTED" or outcome == "ERROR" or np.isnan(row.computed_a):
        return outcome, klass, "unknown", float("nan")
    if row.static_a > row.computed_a:
        return outcome, klass, "upward", float(row.static_a - row.computed_a)
    if row.static_a < row.computed_a:
        return outcome, klass, "downward", float("nan")
    return outcome, klass, "none", float("nan")


# ── tables ────────────────────────────────────────────────────────────────────

def _share(count, total) -> float:
    return float(count) / total if total else float("nan")


def _quantile_cells(prefix: str, values: pd.Series) -> dict:
    finite = values.dropna().to_numpy(dtype=float)
    cells = {f"{prefix}_n": int(len(finite))}
    for name, q in _QUANTILES:
        cells[f"{prefix}_{name}"] = float(np.quantile(finite, q)) if len(finite) else float("nan")
    cells[f"{prefix}_mean"] = float(finite.mean()) if len(finite) else float("nan")
    return cells


def _ratings_table(frame, cities) -> pd.DataFrame:
    rows = []
    for city in cities:
        point = city_point.city_point(city)
        part = frame[(frame["city"] == city) & (frame["period"] == "scored")]
        n = len(part)
        reported, computed = part["reported_a"], part["computed_a"]
        row = {"city": city, "expected_steps": n, "static_a": float(point.static_rating),
               "lower_a": float(point.rating_bounds[0]), "upper_a": float(point.rating_bounds[1])}
        row.update(_quantile_cells("reported", reported))
        row["frac_reported_above_static"] = _share((reported > part["static_a"]).sum(), n)
        row["frac_reported_equal_static"] = _share((reported == part["static_a"]).sum(), n)
        row["frac_reported_below_static"] = _share((reported < part["static_a"]).sum(), n)
        row.update(_quantile_cells("computed", computed))
        classes = part["bound_class"]
        row["frac_computed_below_lower"] = _share((classes == "below").sum(), n)
        row["frac_computed_within"] = _share((classes == "within").sum(), n)
        row["frac_computed_above_upper"] = _share((classes == "above").sum(), n)
        row["frac_computed_below_static"] = _share((computed < part["static_a"]).sum(), n)
        rows.append(row)
    return pd.DataFrame(rows)


def _outcomes_table(frame, cities) -> pd.DataFrame:
    rows = []
    for city in cities:
        for period in PERIODS:
            part = frame[(frame["city"] == city) & (frame["period"] == period)]
            for outcome in OUTCOMES:
                count = int((part["outcome"] == outcome).sum())
                rows.append({"city": city, "period": period, "outcome": outcome, "count": count,
                             "rate": _share(count, len(part))})
    return pd.DataFrame(rows)


def _direction_table(frame, cities) -> pd.DataFrame:
    gates = {"G4_low": ("G4_low",), "G4_high": ("G4_high",), "G6": ("G6",), "all": FALLBACK_OUTCOMES}
    rows = []
    for city in cities:
        scored = frame[(frame["city"] == city) & (frame["period"] == "scored")]
        for gate, outcomes in gates.items():
            part = scored[scored["outcome"].isin(outcomes)]
            over = part.loc[part["direction"] == "upward", "overstatement_a"].dropna().to_numpy(dtype=float)
            rows.append({
                "city": city, "gate": gate, "fallback_steps": int(len(part)),
                "upward": int((part["direction"] == "upward").sum()),
                "downward": int((part["direction"] == "downward").sum()),
                "none": int((part["direction"] == "none").sum()),
                "unknown": int((part["direction"] == "unknown").sum()),
                "upward_rate": _share((part["direction"] == "upward").sum(), len(scored)),
                "overstatement_median": float(np.median(over)) if len(over) else float("nan"),
                "overstatement_p95": float(np.quantile(over, 0.95)) if len(over) else float("nan"),
                "overstatement_max": float(over.max()) if len(over) else float("nan")})
    return pd.DataFrame(rows)


_OUTLIER_COLUMNS = ["city", "rank_kind", "rank", "run_end_utc", "outcome", "reported_a", "computed_a",
                    *_OBS_COLUMNS, "temp_source", "wind_source", "solar_source", "observation_hour"]


def _outliers_table(frame, cities, per_side: int = 5) -> pd.DataFrame:
    rows = []
    for city in cities:
        part = frame[(frame["city"] == city) & (frame["period"] == "scored")
                     & frame["computed_a"].notna()]
        if part.empty:
            rows.append({"city": city, "rank_kind": "none"})
            continue
        lowest = part.sort_values(["computed_a", "run_end_utc"], ascending=[True, True], kind="mergesort")
        highest = part.sort_values(["computed_a", "run_end_utc"], ascending=[False, True], kind="mergesort")
        for kind, ordered in (("lowest", lowest), ("highest", highest)):
            for rank, rec in enumerate(ordered.head(per_side).to_dict("records"), start=1):
                row = {col: rec.get(col) for col in _OUTLIER_COLUMNS}
                row.update(city=city, rank_kind=kind, rank=rank,
                           run_end_utc=rec["run_end_utc"].strftime(_TS_FMT))
                rows.append(row)
    table = pd.DataFrame(rows, columns=_OUTLIER_COLUMNS)
    table["rank"] = table["rank"].astype("Int64")  # whole numbers even beside the empty placeholder row
    return table


_DRIVER_GROUPS = (("below_lower", "below"), ("within", "within"), ("above_upper", "above"))


def _median(values: pd.Series) -> float:
    finite = values.dropna().to_numpy(dtype=float)
    return float(np.median(finite)) if len(finite) else float("nan")


def _drivers_table(frame, cities) -> pd.DataFrame:
    rows = []
    for city in cities:
        scored = frame[(frame["city"] == city) & (frame["period"] == "scored")]
        for name, klass in _DRIVER_GROUPS:
            part = scored[scored["bound_class"] == klass]
            n = len(part)
            rows.append({
                "city": city, "group": name, "n": int(n),
                "temp_median": _median(part["obs_temp"]), "solar_median": _median(part["obs_solar"]),
                "wind_raw_median": _median(part["obs_wind_raw"]),
                "wind_proj_median": _median(part["obs_wind"]),
                "perp_fraction_median": _median(part["perp_fraction"]),
                "wind_open_meteo_share": _share((part["wind_source"] == "open_meteo").sum(), n),
                "solar_open_meteo_share": _share((part["solar_source"] == "open_meteo").sum(), n),
                "lag_over_1h_share": _share((part["observation_lag_h"] > 1).sum(), n)})
    return pd.DataFrame(rows)


def _round(table: pd.DataFrame) -> pd.DataFrame:
    """amp columns to 1 decimal, fractions/rates to 4, weather inputs to 3."""
    table = table.copy()
    for col in table.columns:
        if table[col].dtype.kind != "f":
            continue
        if col.endswith("_a") or any(col.endswith(s) for s in (
                "_min", "_p05", "_p25", "_p50", "_p75", "_p95", "_max", "_mean")) \
                or col.startswith("overstatement_") or col == "fc_amps":
            table[col] = table[col].round(_AMP_DECIMALS)
        elif col.startswith(("frac_", "coverage_", "trip_rate", "nominal_")) \
                or col.endswith(("_rate", "_share", "_fraction_median")) or col == "rate":
            table[col] = table[col].round(_RATE_DECIMALS)
        else:
            table[col] = table[col].round(_INPUT_DECIMALS)
    return table


# ── self-checks ───────────────────────────────────────────────────────────────

def computed_vs_reported_mismatches(frame: pd.DataFrame) -> int:
    """
    Non-fallback steps whose recomputed ampacity differs from the reported rating
    by more than 1e-6 A (or cannot be recomputed), plus G4 fallbacks whose
    recomputed value is inside the bounds.
    """
    ok = frame[frame["outcome"] == "ok"]
    diff = (ok["computed_a"] - ok["reported_a"]).abs()
    bad_ok = int((~(diff <= TOLERANCE_A)).sum())
    contradicting = frame[(frame["outcome"] == "ERROR") & (frame["bound_class"] == "within")]
    return bad_ok + int(len(contradicting))


def archive_checks(archive, trace, cities, steps) -> dict:
    """
    Compare EVERY archive row of the window with its trace record (the archive
    holds rows as written; Phase 2's markers are never persisted) and count any
    (city, datetime_utc) slot holding more than one row (CLEAN-03).
    """
    steps = pd.DatetimeIndex(steps)
    out = {"archive_vs_trace_mismatches": 0, "archive_duplicate_slot_mismatches": 0,
           "archive_rows_outside_window": 0}
    if archive is None or len(archive) == 0:
        return out
    rows = _archive_instants(archive)
    rows = rows[rows["city"].isin(list(cities))]
    inside = rows["_instant"].isin(steps)
    out["archive_rows_outside_window"] = int((~inside).sum())
    rows = rows[inside]
    slot_sizes = rows.groupby(["city", "_instant"]).size()
    out["archive_duplicate_slot_mismatches"] = int((slot_sizes > 1).sum())
    records = {}
    if len(trace):
        for rec in trace.to_dict("records"):
            records[(rec["city"], rec["run_end_utc"])] = rec
    pairs = (("air_temp", "obs_temp"), ("wind_speed", "obs_wind"), ("solar_radiation", "obs_solar"),
             ("dlr_amps", "rating_a"))
    for row in rows.to_dict("records"):
        rec = records.get((row["city"], row["_instant"]))
        if rec is None:
            continue  # NO_TRACE: visible in the outcome tables, nothing to compare
        for archive_col, trace_col in pairs:
            a, t = _num(row.get(archive_col)), _num(rec.get(trace_col))
            if np.isnan(a) or np.isnan(t) or abs(a - t) > TOLERANCE_A:
                out["archive_vs_trace_mismatches"] += 1
                break
    return out


def cleaning_summary(archive_path, trace, cities) -> dict:
    """
    Per-city Phase 2 cleaning summary of the archive as written: ONE
    `clean_history` call per city (a multi-city frame raises ValueError), with
    every flag counted, plus the median and max rows the live run excluded per
    step (`history_rows - usable_history_rows`, cleaned with `as_of=end` then).
    """
    summary = {}
    for city in cities:
        history = historical_archive.read_history(path=archive_path, city=city)
        report = data_cleaning.clean_history(history, as_of=None).report
        block = {"rows_in": int(report["rows_in"]), "rows_usable": int(report["rows_usable"]),
                 "rows_excluded": int(report["rows_excluded"]),
                 "flag_counts": {f: int(report["flag_counts"].get(f, 0)) for f in data_cleaning.FLAG_ORDER},
                 "missing_slots": int(report["missing_slots"])}
        excluded = pd.Series(dtype=float)
        if len(trace) and {"history_rows", "usable_history_rows"} <= set(trace.columns):
            part = trace[trace["city"] == city]
            excluded = (pd.to_numeric(part["history_rows"], errors="coerce")
                        - pd.to_numeric(part["usable_history_rows"], errors="coerce")).dropna()
        block["live_excluded_rows_median"] = float(excluded.median()) if len(excluded) else None
        block["live_excluded_rows_max"] = int(excluded.max()) if len(excluded) else None
        summary[city] = block
    return summary


# ──────────────────────────────────────────────────────────────────────────────
# VAL-02: forecast-band coverage and detector (G6) behaviour
# ──────────────────────────────────────────────────────────────────────────────
#
# Everything below measures the CURRENT city pipeline (`city_pipeline`) from the
# per-step trace. It scores a forecast against the rating the pipeline computed
# for the same step (the forecast at step t is built from history strictly before
# t, so it targets the computed rating at t). It changes no forecast method,
# quantile, control limit or model, and loads no model of its own.

NOMINAL_COVERAGE = float(config.FORECAST_BACKTEST_QUANTILES[1] - config.FORECAST_BACKTEST_QUANTILES[0])
BOOTSTRAP_SEED = 20261019
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_CONF = 0.95
RESIDUAL_BUCKETS = ("0", "1-47", "48-167", "168+")
# Phrases of the real detector and monitor messages (anomaly_detector._check_against_*,
# DLRSafetyMonitor G6). `test_g6_vote_markers_match_real_detector_reasons` runs the
# real branches and fails if one of them is reworded.
G6_VOTE_MARKERS = {
    "forecast": "from forecast center",
    "rolling": "from rolling baseline mean",
    "model": "model flagged reading",
    "error": "detector error (",
}
_G6_EVALUATED = ("ok", "G6")  # outcomes of steps that passed G1-G5, so G6 ran on them
_VOTE_ORDER = ("forecast", "rolling", "model", "error")
G6_TRIPS_PER_CITY = 50

_FORECAST_COLUMNS_OUT = [
    "city", "method", "n_warmup", "n_scored", "n_not_g6", "n_g6_evaluated", "n_with_forecast",
    "n_cold_start", "n_silent_forecast_failure", "n_cleaning_failure_suspect",
    "n_degenerate_band", "n_no_computed", "n_band", "n_withheld_gap", "n_used_by_g6",
    "coverage_nominal", "nominal_target", "coverage_ci_lo", "coverage_ci_hi", "coverage_widened",
    "width_mean_a", "width_median_a", "mae_a", "bias_a", "n_all_computed", "coverage_all_computed"]
_RESIDUAL_COLUMNS_OUT = ["city", "method", "period", "bucket", "n", "coverage_nominal", "n_zero_width"]
_DETECTOR_COLUMNS_OUT = [
    "city", "method", "n_g6_evaluated", "n_g6_trips", "trip_rate", "trip_rate_ci_lo",
    "trip_rate_ci_hi", "forecast_runs", "rolling_runs", "model_runs", "cold_start_runs",
    "forecast_votes", "rolling_votes", "model_votes", "detector_errors", "n_g6_trips_unattributed",
    "model_trip_rate", "n_detector_model_missing", "anomaly_ml_max_false_positive_rate"]
_TRIP_COLUMNS_OUT = ["city", "method", "run_end_utc", "votes", "computed_a", "fc_amps",
                     "widened_lower_a", "widened_upper_a", "reason"]


def band_hit(value, lo, hi):
    """
    True where `lo <= value <= hi` (inclusive at both edges, like
    `AnomalyDetector._check_against_forecast`); vectorised, False for NaN.
    """
    value = np.asarray(value, dtype=float)
    return (value >= lo) & (value <= hi)


def widened_band(center, lo, hi, k):
    """
    The detector's own widened band, with its expression and operation order:
    `center + k * (edge - center)` for each edge.
    """
    return center + k * (lo - center), center + k * (hi - center)


def k_for(city) -> float:
    """The control-limit multiplier the detector uses for `city`."""
    return float(config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION.get(
        city, config.DEFAULT_ANOMALY_CONTROL_LIMIT_K))


def residual_bucket(n_observations):
    """
    The backtest-residual stratum of a forecast built from `n_observations`
    usable rows: residuals = `max(n_observations - FORECAST_MIN_HISTORY_ROWS, 0)`,
    bucketed as RESIDUAL_BUCKETS. None when the count is unknown.
    """
    if n_observations is None or pd.isna(n_observations):
        return None
    residuals = max(int(n_observations) - int(config.FORECAST_MIN_HISTORY_ROWS), 0)
    if residuals == 0:
        return "0"
    if residuals < 48:
        return "1-47"
    if residuals < 168:
        return "48-167"
    return "168+"


def _alert_texts(alerts) -> list:
    """Alert strings from a list (the trace) or the ' | '-joined text `classify_steps` stores."""
    if alerts is None or (isinstance(alerts, float) and np.isnan(alerts)):
        return []
    if isinstance(alerts, str):
        return [part for part in alerts.split(" | ") if part.strip()]
    return [str(a) for a in alerts]


def g6_votes(alerts) -> set:
    """
    Which G6 branches voted, from the traced alert text: a subset of
    {"forecast", "rolling", "model", "error"}. Only alerts that start with
    `G6 FAIL` are read. A detector error is exclusive (the detector raised, no
    branch voted). The trace keeps the first 200 characters of each alert; every
    marker sits well inside that, so a combined forecast+model reason keeps both.
    """
    votes = set()
    for text in _alert_texts(alerts):
        if not text.lstrip().startswith("G6 FAIL"):
            continue
        if G6_VOTE_MARKERS["error"] in text:
            votes.add("error")
            continue
        votes.update(name for name, marker in G6_VOTE_MARKERS.items() if marker in text)
    return votes


def day_block_bootstrap_ci(hits, days, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED,
                           conf=BOOTSTRAP_CONF):
    """
    Percentile interval of a pooled hit rate, resampling WHOLE UTC days (a block
    per day, because consecutive hours share weather and errors) with
    replacement. Seeded, so equal inputs give equal intervals. Returns
    (nan, nan) for no observations or fewer than two distinct days: a single
    block cannot show how the rate varies from day to day.
    """
    hits = np.asarray(hits, dtype=float)
    days = np.asarray(days)
    if hits.size == 0:
        return float("nan"), float("nan")
    _, inverse = np.unique(days, return_inverse=True)
    n_days = int(inverse.max()) + 1
    if n_days < 2:
        return float("nan"), float("nan")
    day_hits = np.bincount(inverse, weights=hits, minlength=n_days)
    day_counts = np.bincount(inverse, minlength=n_days).astype(float)
    picks = np.random.default_rng(seed).integers(0, n_days, size=(int(n_resamples), n_days))
    rates = day_hits[picks].sum(axis=1) / day_counts[picks].sum(axis=1)
    tail = (1.0 - conf) / 2.0
    lo, hi = np.quantile(rates, [tail, 1.0 - tail])
    return float(lo), float(hi)


def _flag(value) -> bool:
    """A traced boolean that may be None, NaN or pd.NA (missing counts as False)."""
    if value is None or value is pd.NA:
        return False
    if isinstance(value, float) and np.isnan(value):
        return False
    return bool(value)


def _numeric(frame, name) -> pd.Series:
    """Column `name` as floats; NaN throughout when the trace has no such column."""
    if name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[name], errors="coerce")


def usable_history_known(steps) -> bool:
    """True when the trace carries `usable_history_rows` for at least one step."""
    return "usable_history_rows" in steps.columns and bool(_numeric(steps, "usable_history_rows").notna().any())


def _scored_city(steps, city) -> pd.DataFrame:
    """A copy of one city's rows with the numeric helpers the VAL-02 tables share."""
    part = steps[steps["city"] == city].copy()
    part["_scored"] = part["period"] == "scored"
    part["_g6"] = part["outcome"].isin(_G6_EVALUATED)
    for name in ("computed_a", "fc_amps", "fc_ci_lower", "fc_ci_upper", "fc_n_observations",
                 "history_rows", "usable_history_rows"):
        part["_" + name] = _numeric(part, name)
    part["_width"] = part["_fc_ci_upper"] - part["_fc_ci_lower"]
    part["_used"] = (part["forecast_used_by_g6"].map(_flag) if "forecast_used_by_g6" in part.columns
                     else pd.Series(False, index=part.index))
    part["_day"] = part["run_end_utc"].dt.strftime("%Y-%m-%d")
    return part


def _count_or_na(known, mask):
    return int(mask.sum()) if known else pd.NA


def _city_forecast_row(steps, city, method, usable_known) -> dict:
    part = _scored_city(steps, city)
    scored = part[part["_scored"]]
    g6 = scored[scored["_g6"]]
    has_fc = g6["_fc_amps"].notna()
    positive = has_fc & (g6["_width"] > 0)
    no_fc = ~has_fc
    usable = g6["_usable_history_rows"]
    min_rows = config.FORECAST_MIN_HISTORY_ROWS
    band = g6[positive & g6["_computed_a"].notna()]
    used = band[band["_used"]]
    k = k_for(city)

    row = {
        "city": city, "method": method,
        "n_warmup": int((~part["_scored"]).sum()), "n_scored": int(len(scored)),
        "n_not_g6": int((~scored["_g6"]).sum()), "n_g6_evaluated": int(len(g6)),
        "n_with_forecast": int(has_fc.sum()),
        "n_cold_start": _count_or_na(usable_known, no_fc & (usable < min_rows)),
        "n_silent_forecast_failure": _count_or_na(usable_known, no_fc & (usable >= min_rows)),
        "n_cleaning_failure_suspect": _count_or_na(
            usable_known, (g6["_history_rows"] >= min_rows) & (usable == 0)),
        "n_degenerate_band": int((has_fc & (g6["_width"] <= 0)).sum()),
        "n_no_computed": int((positive & g6["_computed_a"].isna()).sum()),
        "n_band": int(len(band)), "n_withheld_gap": int((~band["_used"]).sum()),
        "n_used_by_g6": int(len(used)), "nominal_target": NOMINAL_COVERAGE,
    }
    nan = float("nan")
    hits = band_hit(band["_computed_a"], band["_fc_ci_lower"], band["_fc_ci_upper"])
    row["coverage_nominal"] = _share(hits.sum(), len(band))
    row["coverage_ci_lo"], row["coverage_ci_hi"] = day_block_bootstrap_ci(hits, band["_day"].to_numpy())
    wide_lo, wide_hi = widened_band(used["_fc_amps"], used["_fc_ci_lower"], used["_fc_ci_upper"], k)
    row["coverage_widened"] = _share(band_hit(used["_computed_a"], wide_lo, wide_hi).sum(), len(used))
    row["width_mean_a"] = float(band["_width"].mean()) if len(band) else nan
    row["width_median_a"] = float(band["_width"].median()) if len(band) else nan
    error = band["_computed_a"] - band["_fc_amps"]
    row["mae_a"] = float(error.abs().mean()) if len(band) else nan
    row["bias_a"] = float(error.mean()) if len(band) else nan
    everything = scored[scored["_computed_a"].notna() & scored["_fc_amps"].notna() & (scored["_width"] > 0)]
    row["n_all_computed"] = int(len(everything))
    row["coverage_all_computed"] = _share(band_hit(
        everything["_computed_a"], everything["_fc_ci_lower"], everything["_fc_ci_upper"]).sum(),
        len(everything))
    return row


def _cities_in(steps, cities):
    if cities is not None:
        return list(cities)
    present = set(steps["city"]) if len(steps) else set()
    return [c for c in config.LOCATIONS if c in present]


def forecast_table(steps, method_label, cities=None) -> pd.DataFrame:
    """
    VAL-02 forecast-band coverage, one row per city (scored period).

    Coverage population `n_band`: scored steps that reached G6 (outcome `ok` or
    `G6`), had a forecast with a band wider than zero, and have a computed
    rating, whether or not G6 used that forecast. `coverage_nominal` is the share
    of those whose computed rating lies inside the nominal band (the 5-95%
    backtest quantiles, nominal 90%), with a day-block bootstrap 95% interval.
    `coverage_widened` is the share inside the detector's widened band
    (center + k*(edge - center)), on `n_used_by_g6` only: the steps whose
    forecast G6 actually used. Everything left out is counted in its own column:
    warm-up, steps that never reached G6, cold starts, silent forecast failures
    (usable history met the minimum but there is no forecast: the OD-3
    degradation to the rolling baseline), suspected cleaning failures (rows read
    but none usable; also counted in `n_cold_start`), zero-width bands, steps
    with no computed rating, and forecasts withheld across a gap
    (`n_withheld_gap`, which stay in `n_band`). `coverage_all_computed` is the
    secondary figure over EVERY scored step with a computed rating and a
    non-zero band, G4 fallbacks included. `mae_a`/`bias_a` are computed minus
    forecast centre over `n_band`. When the trace has no `usable_history_rows`
    the cold-start split cannot be made and those three counts are empty.
    """
    known = usable_history_known(steps)
    rows = [_city_forecast_row(steps, city, method_label, known) for city in _cities_in(steps, cities)]
    table = pd.DataFrame(rows, columns=_FORECAST_COLUMNS_OUT)
    for column in ("n_cold_start", "n_silent_forecast_failure", "n_cleaning_failure_suspect"):
        table[column] = table[column].astype("Int64")
    return table


def coverage_by_residuals_table(steps, method_label, cities=None) -> pd.DataFrame:
    """
    Nominal-band coverage by backtest-residual count (`RESIDUAL_BUCKETS`), for
    both periods, same population as `forecast_table`'s `n_band`. Every bucket is
    listed, with n 0 allowed. A forecast with 0 residuals has a zero-width band,
    so its bucket is empty by definition; `n_zero_width` counts the G6-evaluated
    steps that were left out for that reason.
    """
    rows = []
    for city in _cities_in(steps, cities):
        part = _scored_city(steps, city)
        part["_bucket"] = [residual_bucket(n) for n in part["_fc_n_observations"]]
        has_fc = part["_g6"] & part["_fc_amps"].notna()
        for period in PERIODS:
            in_period = part["period"] == period
            for bucket in RESIDUAL_BUCKETS:
                here = in_period & (part["_bucket"] == bucket)
                band = part[here & has_fc & (part["_width"] > 0) & part["_computed_a"].notna()]
                hits = band_hit(band["_computed_a"], band["_fc_ci_lower"], band["_fc_ci_upper"])
                rows.append({
                    "city": city, "method": method_label, "period": period, "bucket": bucket,
                    "n": int(len(band)), "coverage_nominal": _share(hits.sum(), len(band)),
                    "n_zero_width": int((here & has_fc & (part["_width"] <= 0)).sum())})
    return pd.DataFrame(rows, columns=_RESIDUAL_COLUMNS_OUT)


def _signal_has(signals: pd.Series, needle: str) -> int:
    return int(signals.map(lambda s: isinstance(s, str) and needle in s).sum())


def detector_table(steps, method_label, cities=None) -> pd.DataFrame:
    """
    VAL-02 detector (G6) behaviour, one row per city (scored period).

    Population `n_g6_evaluated`: scored steps that reached G6 (outcome `ok` or
    `G6`). `trip_rate` is `n_g6_trips / n_g6_evaluated`, with a day-block
    bootstrap interval; a detector error also fails the step to G6, so it is a
    trip here and is counted again in `detector_errors`. The `*_runs` columns say
    which branches ran (from `detector_signal`; a detector that raised keeps the
    signal of the branches that finished). The `*_votes` columns say which
    branches voted anomalous, read from the traced G6 alert text; one trip can
    carry several votes, and `n_g6_trips_unattributed` counts trips whose text
    matched no marker. `model_trip_rate` is `model_votes / model_runs`;
    `n_detector_model_missing` counts G6-evaluated steps whose detector had no
    anomaly model loaded. The design false-positive rate of the learned model is
    shown for reference only.
    """
    rows = []
    for city in _cities_in(steps, cities):
        part = _scored_city(steps, city)
        g6 = part[part["_scored"] & part["_g6"]]
        trips = g6[g6["outcome"] == "G6"]
        votes = [g6_votes(a) for a in trips["alerts"]] if "alerts" in trips.columns else []
        signals = g6["detector_signal"] if "detector_signal" in g6.columns else pd.Series(
            [None] * len(g6), index=g6.index, dtype=object)
        model_runs = _signal_has(signals, "model_")
        model_votes = sum("model" in v for v in votes)
        interval = day_block_bootstrap_ci((g6["outcome"] == "G6").to_numpy(), g6["_day"].to_numpy())
        if "detector_model" in g6.columns:
            missing = int(g6["detector_model"].map(
                lambda m: m is None or m is pd.NA or (isinstance(m, float) and np.isnan(m)) or m == "").sum())
        else:
            missing = pd.NA
        rows.append({
            "city": city, "method": method_label, "n_g6_evaluated": int(len(g6)),
            "n_g6_trips": int(len(trips)), "trip_rate": _share(len(trips), len(g6)),
            "trip_rate_ci_lo": interval[0], "trip_rate_ci_hi": interval[1],
            "forecast_runs": _signal_has(signals, "forecast_residual"),
            "rolling_runs": _signal_has(signals, "rolling_baseline"),
            "model_runs": model_runs, "cold_start_runs": _signal_has(signals, "cold_start"),
            "forecast_votes": sum("forecast" in v for v in votes),
            "rolling_votes": sum("rolling" in v for v in votes),
            "model_votes": model_votes, "detector_errors": sum("error" in v for v in votes),
            "n_g6_trips_unattributed": sum(not v for v in votes),
            "model_trip_rate": _share(model_votes, model_runs),
            "n_detector_model_missing": missing,
            "anomaly_ml_max_false_positive_rate": float(config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE)})
    table = pd.DataFrame(rows, columns=_DETECTOR_COLUMNS_OUT)
    table["n_detector_model_missing"] = table["n_detector_model_missing"].astype("Int64")
    return table


def g6_trips_table(steps, method_label, cities=None, per_city=G6_TRIPS_PER_CITY) -> pd.DataFrame:
    """
    The scored G6 trips, at most `per_city` per city, ordered by the absolute
    deviation of the computed rating from the forecast centre (largest first,
    trips with no forecast last), then by time. `votes` is the "|"-joined sorted
    branch list; the widened band is shown only for a step whose forecast G6 used.
    `reason` is the alert text as traced (at most 200 characters).
    """
    rows = []
    for city in _cities_in(steps, cities):
        part = _scored_city(steps, city)
        trips = part[part["_scored"] & (part["outcome"] == "G6")].copy()
        trips["_deviation"] = (trips["_computed_a"] - trips["_fc_amps"]).abs()
        trips = trips.sort_values(["_deviation", "run_end_utc"], ascending=[False, True],
                                  na_position="last", kind="mergesort").head(per_city)
        k = k_for(city)
        for rec in trips.to_dict("records"):
            usable_band = rec["_used"] and rec["_width"] > 0
            lo, hi = (widened_band(rec["_fc_amps"], rec["_fc_ci_lower"], rec["_fc_ci_upper"], k)
                      if usable_band else (float("nan"), float("nan")))
            alerts = rec.get("alerts")
            rows.append({
                "city": city, "method": method_label,
                "run_end_utc": rec["run_end_utc"].strftime(_TS_FMT),
                "votes": "|".join(v for v in _VOTE_ORDER if v in g6_votes(alerts)),
                "computed_a": rec["_computed_a"], "fc_amps": rec["_fc_amps"],
                "widened_lower_a": lo, "widened_upper_a": hi,
                "reason": alerts if isinstance(alerts, str) else ""})
    return pd.DataFrame(rows, columns=_TRIP_COLUMNS_OUT)


def _trace_methods(trace) -> str:
    """The forecast method(s) the trace records, '+'-joined; 'unknown' when none."""
    if "forecast_method" not in trace.columns:
        return "unknown"
    methods = sorted({str(m) for m in trace["forecast_method"].dropna()})
    return "+".join(methods) if methods else "unknown"


def val02_tables(method_frames, cities) -> dict:
    """
    The four VAL-02 tables for `method_frames`, a list of (method label, classified
    steps). Rows are city-major (config.LOCATIONS order), then in the order given.
    """
    def stack(builder, columns, **kwargs):
        parts = [builder(frame, label, [city], **kwargs)
                 for city in cities for label, frame in method_frames]
        return _round(pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns))

    return {
        "val02_forecast_by_city": stack(forecast_table, _FORECAST_COLUMNS_OUT),
        "val02_coverage_by_residuals": stack(coverage_by_residuals_table, _RESIDUAL_COLUMNS_OUT),
        "val02_detector_by_city": stack(detector_table, _DETECTOR_COLUMNS_OUT),
        "val02_g6_trips": stack(g6_trips_table, _TRIP_COLUMNS_OUT),
    }


_VAL02_DEFINITIONS = (
    "Populations. `n_g6_evaluated`: scored steps that passed G1-G5 (outcome ok or G6), so the detector "
    "ran on them. `n_band` (the coverage population): of those, steps with a forecast whose band is wider "
    "than zero and a computed rating, whether or not G6 used the forecast. `coverage_nominal` = computed "
    "rating inside the forecast's own 5-95% band (nominal target 0.90), with a day-block bootstrap 95% "
    "interval (whole UTC days, 2000 resamples, fixed seed); the interval is empty with fewer than two "
    "days. `coverage_widened` is inside the detector's widened band, on `n_used_by_g6` only. Warm-up, "
    "steps that fell back at G1-G5 or were exhausted, cold starts, silent forecast failures, zero-width "
    "bands and forecasts withheld across a gap are counted in their own columns, never mixed in. "
    "`trip_rate` = G6 trips / `n_g6_evaluated`. Rates are exact count ratios; read each with its n.")


def _val02_markdown(tables: dict, method_labels, notes) -> list:
    sections = ["# VAL-02 tables", "", _LABEL, "", _VAL02_DEFINITIONS, "",
                "Method label(s): " + ", ".join(method_labels) + ". A `naive_replay` row, when present, is a "
                "counterfactual reference (same observations, different forecast method), not what the "
                "live system did.", ""]
    for note in notes:
        sections += [f"Note: {note}", ""]
    for name in ("val02_forecast_by_city", "val02_coverage_by_residuals", "val02_detector_by_city"):
        sections += [f"## {name}", "", _markdown_table(tables[name]), ""]
    trips = tables["val02_g6_trips"]
    per_city = (trips.groupby(["city", "method"], sort=False).size().rename("trips_listed").reset_index()
                if len(trips) else pd.DataFrame({"city": [], "method": [], "trips_listed": []}))
    sections += ["## G6 trips", "",
                 f"The trip list can run to hundreds of rows, so it is CSV-only: `val02_g6_trips.csv` "
                 f"(at most {G6_TRIPS_PER_CITY} per city and method, ordered by deviation of the computed "
                 "rating from the forecast centre, then time; each row carries its votes, the widened band "
                 "and the traced reason).", "", _markdown_table(per_city), ""]
    return sections


# ── rendering ─────────────────────────────────────────────────────────────────

def _cell(value) -> str:
    if value is None or value is pd.NA or (isinstance(value, float) and np.isnan(value)):
        return ""
    if isinstance(value, (bool, np.bool_)):
        return str(bool(value))
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return str(float(value))
    return str(value)


def _markdown_table(table: pd.DataFrame) -> str:
    """A pipe table; NaN renders as an empty cell. No tabulate dependency."""
    header = "| " + " | ".join(str(c) for c in table.columns) + " |"
    rule = "| " + " | ".join("---" for _ in table.columns) + " |"
    body = ["| " + " | ".join(_cell(v) for v in row) + " |"
            for row in table.itertuples(index=False, name=None)]
    return "\n".join([header, rule, *body])


def _write_csv(table: pd.DataFrame, path) -> None:
    table.to_csv(path, index=False, lineterminator="\n")


def _requested_cities(requested):
    wanted = set(requested) if requested else set(config.LOCATIONS)
    unknown = sorted(wanted - set(config.LOCATIONS))
    if unknown:
        raise ValueError(f"unknown cities {unknown}; valid: {list(config.LOCATIONS)}")
    return [c for c in config.LOCATIONS if c in wanted]  # config.LOCATIONS order


def build_report(archive_path, trace_path, start, end, step_hours, warmup_hours, cities, out_dir,
                 method_label=None) -> int:
    """
    Write the VAL-01 and VAL-02 tables, report_meta.json and tables.md to
    `out_dir`, then return 1 if any self-check (a key of report_meta ending in
    `mismatches`) counted a disagreement, else 0. Files are written before the
    exit code is decided, so a failing run still leaves its evidence. The VAL-02
    method label defaults to the forecast method recorded in the trace.
    """
    steps = expected_steps(start, end, step_hours)
    start_ts = _utc(start)
    trace = load_trace(trace_path)
    archive = historical_archive.read_history(path=archive_path, validate=True)
    raw_rows = len(historical_archive.read_history(path=archive_path, validate=False))
    frame = classify_steps(trace, archive, cities, steps, start_ts, warmup_hours)

    tables = {
        "val01_ratings_by_city": _round(_ratings_table(frame, cities)),
        "val01_outcomes_by_city": _round(_outcomes_table(frame, cities)),
        "val01_fallback_direction_by_city": _round(_direction_table(frame, cities)),
        "val01_outliers": _round(_outliers_table(frame, cities)),
        "val01_drivers_by_city": _round(_drivers_table(frame, cities)),
    }
    label = method_label or _trace_methods(trace)
    val02 = val02_tables([(label, frame)], cities)
    notes = [] if usable_history_known(frame) else [
        "usable_history_rows is absent from the trace, so n_cold_start, n_silent_forecast_failure and "
        "n_cleaning_failure_suspect are left empty."]
    meta = {
        "label": _LABEL,
        "nominal_coverage_target": round(NOMINAL_COVERAGE, _RATE_DECIMALS),
        "bootstrap": {"n_resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED,
                      "conf": BOOTSTRAP_CONF, "block": "UTC day"},
        "val02_method_labels": [label],
        "val02_notes": notes,
        "window": {"start": start_ts.strftime(_TS_FMT), "end": _utc(end).strftime(_TS_FMT),
                   "step_hours": float(step_hours), "steps_per_city": int(len(steps))},
        "warmup_hours": float(warmup_hours),
        "scored_start": (start_ts + pd.Timedelta(hours=warmup_hours)).strftime(_TS_FMT),
        "cities": list(cities),
        "trace_records": int(trace.attrs.get("records", len(trace))),
        "trace_duplicates": int(trace.attrs.get("duplicates", 0)),
        "trace_records_out_of_window": count_out_of_window(trace, steps),
        "archive_rows_dropped_by_validation": int(raw_rows - len(archive)),
        "cleaning": cleaning_summary(archive_path, trace, cities),
        "computed_vs_reported_mismatches": computed_vs_reported_mismatches(frame),
    }
    meta.update(archive_checks(archive, trace, cities, steps))

    os.makedirs(out_dir, exist_ok=True)
    for name, table in {**tables, **val02}.items():
        _write_csv(table, os.path.join(out_dir, f"{name}.csv"))
    with open(os.path.join(out_dir, "report_meta.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    cleaning = pd.DataFrame([
        {"city": city, "rows_in": b["rows_in"], "rows_usable": b["rows_usable"],
         "rows_excluded": b["rows_excluded"], "missing_slots": b["missing_slots"],
         **b["flag_counts"]} for city, b in meta["cleaning"].items()])
    sections = ["# VAL-01 tables", "", _LABEL, "",
                "Fractions and rates use every expected step of the period as the denominator, "
                "so exhausted, errored, untraced and missing steps stay in the rates. Amps are "
                "rounded to 1 decimal, fractions to 4, weather inputs to 3. Empty cell = no value.", ""]
    for name, table in tables.items():
        sections += [f"## {name}", "", _markdown_table(table), ""]
    sections += ["## Cleaning activity", "", _markdown_table(cleaning), ""]
    sections += _val02_markdown(val02, [label], notes)
    with open(os.path.join(out_dir, "tables.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(sections))
    failed = sorted(k for k, v in meta.items() if k.endswith("mismatches") and v)
    if failed:
        print("self-check failed: " + ", ".join(f"{k}={meta[k]}" for k in failed), file=sys.stderr)
        return 1
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Run manifest
# ──────────────────────────────────────────────────────────────────────────────

def _file_record(path) -> dict:
    """Path, byte size and sha256 (1 MiB chunks) of one input file."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return {"path": str(path), "bytes": os.path.getsize(path), "sha256": digest.hexdigest()}


def _git(*args) -> str:
    """One fixed-argv git query in the repository this module lives in."""
    done = subprocess.run(["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else ""


def _model_hashes(cities) -> dict:
    """{model filename: sha256, or None when the file is missing} for both model kinds per city."""
    hashes = {}
    for city in cities:
        for path in (ampacity_forecast._model_path_for(city), anomaly_detector._model_path_for(city)):
            hashes[os.path.basename(path)] = (
                _file_record(path)["sha256"] if os.path.isfile(path) else None)
    return hashes


def build_manifest(archive, trace, log, start, end, step_hours=1.0, warmup_hours=168.0,
                   cities=None, forecast_method="naive", backfill_argv=(), console=None) -> dict:
    """
    A deterministic record of what was validated: the window, the exact backfill
    argv and owner command, sha256 + size of the archive, trace and log, archive
    rows per city, sha256 of the per-city model files and the git HEAD. No
    timestamp is written, so equal inputs give equal bytes. Phase 4 uses it to
    prove it loads the archive this phase validated.
    """
    cities = list(cities) if cities else list(config.LOCATIONS)
    steps = expected_steps(start, end, step_hours)
    start_ts = _utc(start)
    files = {"archive": _file_record(archive), "trace": _file_record(trace), "log": _file_record(log)}
    if console:
        files["console"] = _file_record(console)
    history = historical_archive.read_history(path=archive, validate=True)
    counts = history.groupby("city").size().to_dict() if len(history) else {}
    argv = list(backfill_argv)
    return {
        "schema": MANIFEST_SCHEMA,
        "window": {
            "start": start_ts.strftime(_TS_FMT), "end": _utc(end).strftime(_TS_FMT),
            "step_hours": float(step_hours), "steps_per_city": int(len(steps)),
            "warmup_hours": float(warmup_hours),
            "scored_start": (start_ts + pd.Timedelta(hours=warmup_hours)).strftime(_TS_FMT),
        },
        "cities": cities,
        "forecast_method": forecast_method,
        "backfill_argv": argv,
        "command": OWNER_COMMAND_TEMPLATE.replace("{argv}", repr(argv)),
        "working_directory": os.getcwd(),
        "files": files,
        "archive_rows_by_city": {c: int(counts.get(c, 0)) for c in cities},
        "models": _model_hashes(cities),
        "git": {"head": _git("rev-parse", "HEAD"),
                "backend_dirty": bool(_git("status", "--porcelain", "--", "backend"))},
        "label": ("PROVISIONAL (OD-5): static ratings, rating bounds and line bearings are "
                  "unconfirmed assumptions; this record measures, it does not decide."),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Command line
# ──────────────────────────────────────────────────────────────────────────────

def _missing_inputs(*paths) -> list:
    return [p for p in paths if not os.path.exists(p)]


def _cmd_completeness(args) -> int:
    missing = _missing_inputs(args.archive, args.trace, args.log)
    if missing:
        for path in missing:
            print(f"input file not found: {path}", file=sys.stderr)
        return 2
    cities = list(args.cities) if args.cities else list(config.LOCATIONS)
    steps = expected_steps(args.start, args.end, args.step_hours)
    table = completeness_table(
        load_trace(args.trace),
        historical_archive.read_history(path=args.archive, validate=True),
        _read_log(args.log), cities, steps)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    table.to_csv(args.out, index=False, lineterminator="\n")
    print(table.to_string(index=False))
    return 0


def _cmd_manifest(args) -> int:
    inputs = [args.archive, args.trace, args.log] + ([args.console] if args.console else [])
    missing = _missing_inputs(*inputs)
    if missing:
        for path in missing:
            print(f"input file not found: {path}", file=sys.stderr)
        return 2
    manifest = build_manifest(
        args.archive, args.trace, args.log, args.start, args.end, args.step_hours,
        args.warmup_hours, args.cities, args.forecast_method, args.backfill_argv, args.console)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    absent = sorted(name for name, digest in manifest["models"].items() if digest is None)
    if absent:
        print(f"model file missing: {', '.join(absent)}", file=sys.stderr)
        return 1
    return 0


def _cmd_report(args) -> int:
    missing = _missing_inputs(args.archive, args.trace)
    if missing:
        for path in missing:
            print(f"input file not found: {path}", file=sys.stderr)
        return 2
    try:
        cities = _requested_cities(args.cities)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return build_report(args.archive, args.trace, args.start, args.end, args.step_hours,
                        args.warmup_hours, cities, args.out_dir, method_label=args.method_label)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline analysis of a real backfill run (Phase 3 validation).")
    sub = parser.add_subparsers(dest="command", required=True)

    comp = sub.add_parser("completeness", help="per-city step counts for a backfill run")
    comp.add_argument("--archive", required=True)
    comp.add_argument("--trace", required=True)
    comp.add_argument("--log", required=True)
    comp.add_argument("--start", required=True)
    comp.add_argument("--end", required=True)
    comp.add_argument("--step-hours", type=float, default=1.0)
    comp.add_argument("--cities", nargs="*")
    comp.add_argument("--out", required=True, help="CSV path for the table")
    comp.set_defaults(func=_cmd_completeness)

    man = sub.add_parser(
        "manifest", help="deterministic JSON record of the validated run "
                         "(backfill argv goes after a literal `--`)")
    man.add_argument("--archive", required=True)
    man.add_argument("--trace", required=True)
    man.add_argument("--log", required=True)
    man.add_argument("--console", help="optional console log of the run")
    man.add_argument("--start", required=True)
    man.add_argument("--end", required=True)
    man.add_argument("--step-hours", type=float, default=1.0)
    man.add_argument("--warmup-hours", type=float, default=168.0)
    man.add_argument("--cities", nargs="*")
    man.add_argument("--forecast-method", default="naive")
    man.add_argument("--out", required=True, help="JSON path for the manifest")
    man.set_defaults(func=_cmd_manifest)

    rep = sub.add_parser("report", help="VAL-01 and VAL-02 tables from the trace and archive")
    rep.add_argument("--archive", required=True)
    rep.add_argument("--trace", required=True)
    rep.add_argument("--start", required=True)
    rep.add_argument("--end", required=True)
    rep.add_argument("--step-hours", type=float, default=1.0)
    rep.add_argument("--warmup-hours", type=float, default=168.0)
    rep.add_argument("--cities", nargs="*")
    rep.add_argument("--out-dir", required=True)
    rep.add_argument("--method-label",
                     help="VAL-02 method label (default: the forecast method recorded in the trace)")
    rep.set_defaults(func=_cmd_report)
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    backfill_argv = []
    if "--" in argv:  # everything after a literal `--` is the backfill argv, verbatim
        cut = argv.index("--")
        argv, backfill_argv = argv[:cut], argv[cut + 1:]
    args = _build_parser().parse_args(argv)
    args.backfill_argv = backfill_argv
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
