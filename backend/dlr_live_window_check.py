"""
Window check for hourly live slots (production-pipeline Phase 5: SCHED-01, SCHED-02)
=================================================================================
Turns ROADMAP Phase 5 success criterion 2 -- "over 24 h, every scheduled slot has
either a successful run or a visible failed run, and each successful run wrote one
row per city" -- into one command, and reports the Actions minutes the window used.

Each of the N hourly slots in the window gets one verdict:

    ok              a run finished with conclusion 'success', its pipeline_run row
                    lists every city of config.LOCATIONS in cities_ok, and
                    city_rating has a row for every city at the slot's valid_time
                    written by a run of that slot
    incomplete      a successful run exists but one of those conditions fails
    failed-visible  no successful run, but at least one run is visibly red
                    (conclusion failure, timed_out, cancelled or startup_failure); a fault-drill run
                    (a pipeline_run city with fault_injected) never counts, so a
                    drill cannot stand in for a dispatch that never happened
    missing         no run at all, or only runs that are unfinished or have another
                    conclusion (skipped, ...): nothing shows the slot was attempted

The window passes when no slot is 'missing' or 'incomplete'. A red run counts as
visible: it is a failure someone can see, not a silent gap.

A run belongs to the slot of its pipeline_run `window_end` truncated to the hour (the
OD-7 valid_time); a run with no pipeline_run row (it died before the runner started)
is placed by its start time. Rating rows count when their run_id belongs to ANY run
of the slot, so a later drill or re-run that overwrote some cities' rows in the same
hour (OD-7) does not turn an earlier good run into a failure.

The module is read-only: `gh run list` and two SELECTs with bound parameters. It runs
from the owner's main checkout and needs `gh` authentication and SUPABASE_DB_URL
(through Phase 4's `supabase_store.connect()`; `.env` is loaded when run as a script).
`evaluate_window` is pure, so everything but the two fetchers is testable offline.
"""

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import config

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BACKEND_DIR)

WORKFLOW_FILE = "dlr_live.yml"
GH_RUN_FIELDS = "databaseId,createdAt,startedAt,updatedAt,status,conclusion,event,attempt"
GH_RUN_LIMIT = 400
GH_TIMEOUT_S = 120

SUCCESS = "success"
# startup_failure: the run could not start (broken workflow file); the Actions UI shows it red
RED_CONCLUSIONS = ("failure", "timed_out", "cancelled", "startup_failure")
RUNS_PER_DAY = 24
DAYS_PER_MONTH = 30

_ONE_HOUR = timedelta(hours=1)

PIPELINE_RUN_SQL = (
    "select run_id, run_attempt, window_end, cities_ok, cities_failed, finished_at "
    "from public.pipeline_run "
    "where window_end >= %(start)s and window_end < %(end)s "
    "order by window_end, run_id"
)
CITY_RATING_SQL = (
    "select city, valid_time, run_id "
    "from public.city_rating "
    "where valid_time >= %(start)s and valid_time < %(end)s "
    "order by valid_time, city"
)


def _ts(value):
    """An aware UTC datetime from a datetime or an ISO-8601 string ('Z' allowed); None stays None."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def billed_minutes(run) -> int:
    """
    Minutes GitHub bills for a run, approximated from the run itself:
    ceil((updatedAt - startedAt) / 60 s), at least 1 (a job bills a whole minute).
    GitHub rounds each job up, so a one-job run is exact; this is the figure the
    runbook's minutes table is measured with.
    """
    started = _ts(run.get("startedAt"))
    updated = _ts(run.get("updatedAt"))
    seconds = (updated - started).total_seconds()
    return max(1, math.ceil(seconds / 60))


def _cities_listed(row) -> set:
    cities = (row or {}).get("cities_ok")
    if isinstance(cities, (list, tuple, set)):
        return set(cities)
    return set()


def _is_drill(row) -> bool:
    """True when the pipeline_run row records a city failed on purpose (the SCHED-01 fault drill)."""
    failed = (row or {}).get("cities_failed")
    if not isinstance(failed, dict):
        return False
    return any(isinstance(v, dict) and v.get("fault_injected") for v in failed.values())


def _run_slot_time(run, row):
    """The instant that decides a run's slot: its pipeline_run window_end, else its start."""
    window_end = _ts((row or {}).get("window_end"))
    if window_end is not None:
        return window_end
    return _ts(run.get("startedAt")) or _ts(run.get("createdAt"))


def _minutes_summary(placed_runs) -> dict:
    minutes = [billed_minutes(r) for r in placed_runs
               if r.get("conclusion") and r.get("startedAt") and r.get("updatedAt")]
    if not minutes:
        return {"count": 0, "median": None, "max": None, "projected_30d": None}
    median = statistics.median(minutes)
    return {
        "count": len(minutes),
        "median": median,
        "max": max(minutes),
        "projected_30d": median * RUNS_PER_DAY * DAYS_PER_MONTH,
    }


def evaluate_window(runs, run_rows, rating_rows, start, hours=24) -> dict:
    """
    Slot-by-slot verdict for `hours` hourly slots from `start` (pure, no I/O).

    `runs` are `gh run list --json` dicts, `run_rows` are pipeline_run dicts and
    `rating_rows` are `{city, valid_time, run_id}` dicts. Returns
    `{"slots": [{slot, verdict, run_ids, conclusions, note}], "minutes": {count,
    median, max, projected_30d}, "passed": bool}`; see the module docstring for the
    verdicts. `minutes` covers every finished run placed in the window, red ones
    included (a fault-drill run too), because a red run still bills.
    """
    start = _ts(start)
    cities = list(config.LOCATIONS)
    rows_by_id = {str(r["run_id"]): r for r in run_rows}

    placed = [[] for _ in range(hours)]  # per slot: (run id, run, pipeline_run row)
    drills = [[] for _ in range(hours)]  # per slot: drill runs, billed but never evidence for the slot
    for run in runs:
        run_id = str(run["databaseId"])
        row = rows_by_id.get(run_id)
        when = _run_slot_time(run, row)
        if when is None:
            continue
        index = math.floor((when - start) / _ONE_HOUR)
        if 0 <= index < hours:
            # A drill always ends red; counting it would let a missed dispatch pass as failed-visible.
            (drills if _is_drill(row) else placed)[index].append((run_id, run, row))

    rated = {}  # (city, valid_time) -> set of run ids that wrote it
    for rating in rating_rows:
        rated.setdefault((rating["city"], _ts(rating["valid_time"])), set()).add(str(rating["run_id"]))

    slots = []
    for index in range(hours):
        slot_time = start + index * _ONE_HOUR
        entries = sorted(placed[index], key=lambda e: (str(e[1].get("startedAt") or ""), e[0]))
        run_ids = [e[0] for e in entries]
        conclusions = [e[1].get("conclusion") or e[1].get("status") or "unknown" for e in entries]
        # a drill's rating rows still count: it may have overwritten a good run's rows in the same hour (OD-7)
        slot_run_ids = set(run_ids) | {e[0] for e in drills[index]}
        successful = [e for e in entries if e[1].get("conclusion") == SUCCESS]

        if successful:
            absent_rows = [e[0] for e in successful if e[2] is None]
            full_run = any(set(cities) <= _cities_listed(e[2]) for e in successful)
            no_rating = [c for c in cities if not (rated.get((c, slot_time), set()) & slot_run_ids)]
            if full_run and not no_rating:
                verdict, note = "ok", ""
            else:
                verdict = "incomplete"
                reasons = []
                if absent_rows:
                    reasons.append("no pipeline_run row for run " + ", ".join(absent_rows))
                if not full_run:
                    listed = set().union(*(_cities_listed(e[2]) for e in successful))
                    short = [c for c in cities if c not in listed]
                    reasons.append("cities_ok lacks " + (", ".join(short) if short else "a city in every successful run"))
                if no_rating:
                    reasons.append("no city_rating row from this slot's runs for " + ", ".join(no_rating))
                note = "; ".join(reasons)
        elif any(e[1].get("conclusion") in RED_CONCLUSIONS for e in entries):
            verdict = "failed-visible"
            note = "red run: " + ", ".join(c for c in conclusions if c in RED_CONCLUSIONS)
        elif entries:
            verdict = "missing"
            note = "only unfinished or inconclusive runs: " + ", ".join(conclusions)
        else:
            verdict, note = "missing", "no run"

        if drills[index]:
            drill_ids = ", ".join(sorted(e[0] for e in drills[index]))
            note = "; ".join(filter(None, [note, f"fault-drill run {drill_ids} not counted"]))

        slots.append({
            "slot": _iso(slot_time),
            "verdict": verdict,
            "run_ids": run_ids,
            "conclusions": conclusions,
            "note": note,
        })

    return {
        "slots": slots,
        "minutes": _minutes_summary([e[1] for group in (placed, drills) for entries in group for e in entries]),
        "passed": all(s["verdict"] not in ("missing", "incomplete") for s in slots),
    }


def format_report(result) -> str:
    """A markdown table (slot, verdict, runs, note), the minutes line and the verdict line."""
    lines = ["| slot (UTC) | verdict | runs | note |", "|---|---|---|---|"]
    for s in result["slots"]:
        runs = ", ".join(f"{rid} ({c})" for rid, c in zip(s["run_ids"], s["conclusions"])) or "-"
        note = (s["note"] or "").replace("|", "/")
        lines.append(f"| {s['slot']} | {s['verdict']} | {runs} | {note} |")
    counts = {}
    for s in result["slots"]:
        counts[s["verdict"]] = counts.get(s["verdict"], 0) + 1
    lines.append("")
    lines.append("verdicts: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    m = result["minutes"]
    if m["count"]:
        lines.append(
            f"billed minutes: {m['count']} runs, median {m['median']}, max {m['max']}; "
            f"projected {m['projected_30d']:g} min per 30 days at {RUNS_PER_DAY} runs/day"
        )
    else:
        lines.append("billed minutes: no finished runs in the window")
    lines.append("window: " + ("PASSED" if result["passed"] else "FAILED"))
    return "\n".join(lines)


def fetch_runs(start, hours) -> list:
    """
    `gh run list` for the live workflow (argv list, no shell), filtered to the window
    plus one hour of slack either side. Needs `gh` authenticated for the repository
    the working copy belongs to.
    """
    start = _ts(start)
    argv = ["gh", "run", "list", "--workflow", WORKFLOW_FILE, "--limit", str(GH_RUN_LIMIT),
            "--json", GH_RUN_FIELDS]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=GH_TIMEOUT_S, cwd=REPO_ROOT)
    if done.returncode != 0:
        raise RuntimeError(f"gh run list failed (exit {done.returncode}): {done.stderr.strip()[:500]}")
    everything = json.loads(done.stdout or "[]")
    low = start - _ONE_HOUR
    high = start + timedelta(hours=hours) + _ONE_HOUR
    kept = [r for r in everything if r.get("createdAt") and low <= _ts(r["createdAt"]) <= high]
    if len(everything) >= GH_RUN_LIMIT:
        oldest = min(_ts(r["createdAt"]) for r in everything if r.get("createdAt"))
        if oldest > low:
            print(f"warning: gh returned its limit of {GH_RUN_LIMIT} runs and the oldest is "
                  f"{_iso(oldest)}, after the window start; earlier slots may be cut off", file=sys.stderr)
    return kept


def _rows(conn, sql, params) -> list:
    cursor = conn.execute(sql, params)
    names = [d.name for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def fetch_rows(start, hours, conn=None):
    """
    `(run_rows, rating_rows)` for the window: the pipeline_run rows whose window_end,
    and the city_rating rows whose valid_time, fall in [start, start + hours).

    Two SELECTs with bound parameters (`%(start)s`, `%(end)s`); no value is ever
    formatted into the SQL text. `conn` defaults to a new connection through Phase 4's
    `supabase_store.connect()` (SUPABASE_DB_URL), closed here; a connection passed in
    stays the caller's. A database error is re-raised as a redacted `StoreError`.
    """
    import supabase_store

    start = _ts(start)
    params = {"start": start, "end": start + timedelta(hours=hours)}
    own = conn is None
    failure = None
    run_rows = rating_rows = None
    try:
        if own:
            conn = supabase_store.connect()
        run_rows = _rows(conn, PIPELINE_RUN_SQL, params)
        rating_rows = _rows(conn, CITY_RATING_SQL, params)
    except supabase_store.StoreError:
        raise
    except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted StoreError
        failure = supabase_store.redact(str(exc))
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    if failure is not None:
        raise supabase_store.StoreError(f"could not read the window: {failure}")
    return run_rows, rating_rows


def _hour_arg(value):
    try:
        parsed = _ts(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an ISO timestamp: {value!r}") from None
    if parsed is None:
        raise argparse.ArgumentTypeError("--start is required, e.g. 2026-10-25T00:00:00Z")
    if parsed.minute or parsed.second or parsed.microsecond:
        raise argparse.ArgumentTypeError(f"--start must be on the hour, got {value!r}")
    return parsed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Slot-by-slot check of a window of hourly live runs (read-only).")
    parser.add_argument("--start", required=True, type=_hour_arg,
                        help="first slot, an ISO hour in UTC, e.g. 2026-10-25T00:00:00Z")
    parser.add_argument("--hours", type=int, default=24, help="number of hourly slots (default 24)")
    parser.add_argument("--json", metavar="PATH", help="also write the full result as JSON to PATH")
    args = parser.parse_args(argv)
    if args.hours < 1:
        parser.error("--hours must be at least 1")

    runs = fetch_runs(args.start, args.hours)
    run_rows, rating_rows = fetch_rows(args.start, args.hours)
    result = evaluate_window(runs, run_rows, rating_rows, args.start, args.hours)

    print(format_report(result))
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(result, fh, indent=2)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    sys.exit(main())
