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
import json
import os
import sys

import pandas as pd

import config
import historical_archive

TRACE_SCHEMA = "backfill_trace/1"

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


def load_trace(path) -> pd.DataFrame:
    """One row per JSON line of the trace, `run_end_utc` parsed to UTC Timestamps."""
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    frame = pd.DataFrame(records)
    if "run_end_utc" not in frame.columns:
        frame["run_end_utc"] = pd.Series(dtype="datetime64[ns, UTC]")
    frame["run_end_utc"] = pd.to_datetime(frame["run_end_utc"], utc=True)
    return frame


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
    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
