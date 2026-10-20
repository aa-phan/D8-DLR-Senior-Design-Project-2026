"""
Real-data validation analysis (Phase 3, offline)
=================================================
Turns the files a real backfill run leaves behind into the tables the owner
reads. VAL-01 (what the pipeline reports against the static rating, the rating
bounds and its own gates) is implemented here; VAL-02 (forecast and detector
behaviour) is added later in the same phase.

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

    python backend/real_data_validation.py completeness --archive A --trace T \\
        --log L --start 2026-09-07T00:00:00Z --end 2026-09-27T23:00:00Z --out OUT.csv
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

import pandas as pd

import ampacity_forecast
import anomaly_detector
import config
import historical_archive

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
