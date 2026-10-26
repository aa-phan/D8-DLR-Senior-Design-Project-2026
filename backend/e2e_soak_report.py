"""
Dry-soak export and report (production-pipeline Phase 6: E2E-02, D-07)
======================================================================
E2E-02's 72 h soak fails structurally if the real write lag does not fit the 90-minute
freshness budget (06-RESEARCH Pitfall 9). The dry soak answers that BEFORE the 72 h clock
starts, from live rows Phase 5 has already written, so nobody waits a fresh 12-24 h.

Two subcommands:

    export  --mode dry --since ISO --until ISO --out-dir DIR
        Owner-run, read-only. Reads the live city_rating rows, the matching pipeline_run rows
        and `gh run list` for dlr_live.yml, and writes writes.csv, runs.csv, gh_runs.json and
        export_meta.json into DIR. It runs from the owner's main checkout (Phase 4's
        `supabase_store.connect()` reads SUPABASE_DB_URL; `gh` must be authenticated). The
        session is set read-only before the first query, every SELECT binds its parameters,
        and no URL, host or credential is written to any file or stream.

    report  --mode dry --in-dir DIR [--min-hours 12] [--max-age-min 90] --out FILE.md [--json-out FILE]
        Offline, no network and no wall clock: the same files give byte-identical output. Per
        city and overall it states the write lag (count, median, p95, max), the peak age (the
        oldest the "current" rating ever got), the age at --until, the fallback share
        (informational) and, reusing Phase 5's `evaluate_window`, a verdict for every hourly slot.

What counts as a breach: a "current" rating whose age is STRICTLY over --max-age-min (90 by
default, OD-4: the same rule as latest_rating.is_stale and assert_fresh; exactly 90 is fresh).
The comparison is made on the exact timedelta, never on the rounded minutes shown.

Why first_written_at and not computed_at: an OD-7 same-hour retry rewrites computed_at (and the
values) but never first_written_at, so computed_at would blame the pipeline for a retry the owner
ran on purpose (06-RESEARCH Pitfall 14). The moment a consumer stops seeing the previous row as
"latest" is the FIRST time the next slot's row was inserted. Walking live rows in first_written_at
order with a running per-city maximum valid_time gives the exact age a consumer saw just before
each advancing write; a late-filled older slot never advances the maximum, so it never creates a
breach. Backfill rows (origin backfill) are excluded: their first_written_at is the load time.

Exit codes (report): 0 when the window passes, 1 when it does not, 2 on missing or malformed
input (the message names the file or column). export returns 1 on a failure, printed as the
exception type plus redacted text.

The module never writes to the database, data/shadow or any shadow file.
"""

import argparse
import csv
import json
import math
import os
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import config
import dlr_live_window_check

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BACKEND_DIR)

DEFAULT_MAX_AGE_MIN = 90   # OD-4: the same rule as latest_rating.is_stale and assert_fresh
WARN_PEAK_MIN = 75         # above this a single slow hour would breach (06-RESEARCH Pitfall 9)
DRY_MIN_HOURS = 12

_ONE_HOUR = timedelta(hours=1)

WRITES_FILE = "writes.csv"
RUNS_FILE = "runs.csv"
GH_RUNS_FILE = "gh_runs.json"
META_FILE = "export_meta.json"

WRITES_COLUMNS = (
    "city", "valid_time", "first_written_at", "computed_at", "run_id", "origin", "status", "fallback",
    "pipeline_version", "config_fingerprint", "forecast_model_sha256", "anomaly_model_sha256",
    "forecast_method", "config_version",
)
RUNS_COLUMNS = ("run_id", "run_attempt", "started_at", "finished_at", "window_end", "cities_ok", "cities_failed")

# Live rows only (a backfill row's first_written_at is the load time, not an arrival), plus one day
# before --since so the newest row a consumer already saw at the window start seeds the walk.
WRITES_SQL = (
    "select city, valid_time, first_written_at, computed_at, run_id, origin, status, fallback, "
    "pipeline_version, config_fingerprint, forecast_model_sha256, anomaly_model_sha256, "
    "forecast_method, config_version "
    "from public.city_rating "
    "where origin = 'live' and first_written_at < %(until)s "
    "and valid_time >= %(since)s - interval '1 day' "
    "order by first_written_at, valid_time, city"
)
RUNS_SQL = (
    "select run_id, run_attempt, started_at, finished_at, window_end, cities_ok, cities_failed "
    "from public.pipeline_run "
    "where window_end >= %(since)s - interval '2 hours' and window_end < %(until)s "
    "order by window_end, run_id"
)
READ_ONLY_SQL = "set default_transaction_read_only = on"

CITY_INDEX = {city: i for i, city in enumerate(config.LOCATIONS)}


class InputError(Exception):
    """Missing or malformed report input; the message names the file or column (exit 2)."""


# ──────────────────────────────────────────────────────────────────────────────
# Time helpers
# ──────────────────────────────────────────────────────────────────────────────

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
    """ISO 8601 UTC with a Z; fractional seconds only when the value has them."""
    dt = _ts(dt)
    if dt.microsecond:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _minutes(delta) -> float:
    return round(delta.total_seconds() / 60, 1)


def _city_order(city):
    return (CITY_INDEX.get(city, len(CITY_INDEX)), city)


# ──────────────────────────────────────────────────────────────────────────────
# export (owner, read-only)
# ──────────────────────────────────────────────────────────────────────────────

def _rows(conn, sql, params) -> list:
    cursor = conn.execute(sql, params)
    names = [d.name for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _write_csv(path, columns, rows) -> None:
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_cell(row.get(c)) for c in columns])


def _git_head() -> str:
    try:
        done = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=10, cwd=REPO_ROOT)
        return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else "unknown"
    except Exception:  # noqa: BLE001 - the head is a label, never a reason to fail an export
        return "unknown"


def _slot_window(since, until):
    """`(first slot, whole hours)`: the hour-aligned slots whose valid_time lies in [since, until)."""
    slot_start = since.replace(minute=0, second=0, microsecond=0)
    hours = int((until - slot_start) // _ONE_HOUR)
    return slot_start, hours


def export_dry(since, until, out_dir, connect_fn=None, fetch_runs_fn=None, now_fn=None) -> dict:
    """
    Read the live window read-only and write writes.csv, runs.csv, gh_runs.json and export_meta.json
    into `out_dir`. Returns the export_meta dict. Nothing is written when any read fails.

    `connect_fn` defaults to Phase 4's `supabase_store.connect`, `fetch_runs_fn(start, hours)` to
    `dlr_live_window_check.fetch_runs`; a failure other than a StoreError is re-raised as a
    StoreError carrying the exception type and redacted text.
    """
    import supabase_store

    since, until = _ts(since), _ts(until)
    if connect_fn is None:
        connect_fn = supabase_store.connect
    if fetch_runs_fn is None:
        fetch_runs_fn = dlr_live_window_check.fetch_runs
    params = {"since": since, "until": until}
    slot_start = since.replace(minute=0, second=0, microsecond=0)
    gh_hours = max(1, math.ceil((until - slot_start) / _ONE_HOUR))

    conn = None
    failure = None
    writes = run_rows = gh_runs = None
    try:
        conn = connect_fn()
        conn.execute(READ_ONLY_SQL)  # before the first query: this session can no longer write
        writes = _rows(conn, WRITES_SQL, params)
        run_rows = _rows(conn, RUNS_SQL, params)
        gh_runs = fetch_runs_fn(slot_start, gh_hours)
    except supabase_store.StoreError:
        raise
    except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted StoreError
        failure = f"{type(exc).__name__}: {supabase_store.redact(str(exc))}"
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    if failure is not None:
        raise supabase_store.StoreError(f"could not export the window: {failure}")

    now = now_fn() if now_fn is not None else datetime.now(timezone.utc)
    meta = {
        "mode": "dry",
        "since": _iso(since),
        "until": _iso(until),
        "exported_at": _iso(now),
        "rows": {"writes": len(writes), "runs": len(run_rows), "gh_runs": len(gh_runs)},
        "git_head": _git_head(),
    }
    os.makedirs(out_dir, exist_ok=True)
    _write_csv(os.path.join(out_dir, WRITES_FILE), WRITES_COLUMNS, writes)
    _write_csv(os.path.join(out_dir, RUNS_FILE), RUNS_COLUMNS, run_rows)
    with open(os.path.join(out_dir, GH_RUNS_FILE), "w") as fh:
        json.dump(gh_runs, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(out_dir, META_FILE), "w") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    return meta


# ──────────────────────────────────────────────────────────────────────────────
# report (offline)
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_WRITES_COLUMNS = ("city", "valid_time", "first_written_at", "computed_at", "run_id", "origin", "fallback")
REQUIRED_RUNS_COLUMNS = ("run_id", "window_end", "cities_ok", "cities_failed")


def _read_csv(path, name, required) -> list:
    """The rows of a CSV as dicts; InputError naming the file and column when a column is absent."""
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise InputError(f"{name}: missing column {', '.join(missing)}")
        return list(reader)


def _parse(name, number, column, value, parser):
    try:
        return parser(value)
    except (ValueError, TypeError):
        raise InputError(f"{name} row {number}: column {column} has a malformed value {str(value)[:40]!r}") from None


def _json_cell(text, default):
    if text is None or text == "":
        return default
    return json.loads(text)


def _timestamp_cell(value):
    parsed = _ts(value)
    if parsed is None:
        raise ValueError("empty timestamp")
    return parsed


def load_inputs(in_dir) -> dict:
    """
    Read the four export files into `{writes, run_rows, runs, meta}` with timestamps parsed.
    Raises InputError naming the file (and the column) when a file is missing, a required column
    is absent or a value is malformed.
    """
    paths = {name: os.path.join(in_dir, name) for name in (WRITES_FILE, RUNS_FILE, GH_RUNS_FILE, META_FILE)}
    for name, path in paths.items():
        if not os.path.isfile(path):
            raise InputError(f"missing input file: {name}")

    writes = []
    for number, raw in enumerate(_read_csv(paths[WRITES_FILE], WRITES_FILE, REQUIRED_WRITES_COLUMNS), start=2):
        row = dict(raw)
        for column in ("valid_time", "first_written_at", "computed_at"):
            row[column] = _parse(WRITES_FILE, number, column, raw[column], _timestamp_cell)
        row["fallback"] = str(raw["fallback"]).strip().lower() in ("true", "t", "1")
        writes.append(row)

    run_rows = []
    for number, raw in enumerate(_read_csv(paths[RUNS_FILE], RUNS_FILE, REQUIRED_RUNS_COLUMNS), start=2):
        row = dict(raw)
        row["window_end"] = _parse(RUNS_FILE, number, "window_end", raw["window_end"], _timestamp_cell)
        for column in ("started_at", "finished_at"):
            row[column] = _parse(RUNS_FILE, number, column, raw.get(column), _ts)
        row["cities_ok"] = _parse(RUNS_FILE, number, "cities_ok", raw["cities_ok"], lambda v: _json_cell(v, []))
        row["cities_failed"] = _parse(RUNS_FILE, number, "cities_failed", raw["cities_failed"],
                                      lambda v: _json_cell(v, {}))
        run_rows.append(row)

    try:
        with open(paths[GH_RUNS_FILE]) as fh:
            runs = json.load(fh)
    except ValueError:
        raise InputError(f"{GH_RUNS_FILE}: not valid JSON") from None
    if not isinstance(runs, list):
        raise InputError(f"{GH_RUNS_FILE}: expected a JSON list of runs")
    try:
        with open(paths[META_FILE]) as fh:
            meta = json.load(fh)
    except ValueError:
        raise InputError(f"{META_FILE}: not valid JSON") from None
    for key in ("since", "until"):
        if not isinstance(meta, dict) or key not in meta:
            raise InputError(f"{META_FILE}: missing key {key}")
        _parse(META_FILE, 0, key, meta[key], _timestamp_cell)
    return {"writes": writes, "run_rows": run_rows, "runs": runs, "meta": meta}


def _walk(writes, since):
    """`(events, late_fills)`: see advance_events; a late fill is a live row first written inside the
    window whose valid_time does not pass the city's running maximum."""
    since = _ts(since)
    live = [w for w in writes if w["origin"] == "live"]
    running = {}
    for w in live:
        if w["first_written_at"] < since:
            current = running.get(w["city"])
            if current is None or w["valid_time"] > current:
                running[w["city"]] = w["valid_time"]

    inside = sorted((w for w in live if w["first_written_at"] >= since),
                    key=lambda w: (w["first_written_at"], w["valid_time"], _city_order(w["city"])))
    events, late_fills = [], []
    for w in inside:
        previous = running.get(w["city"])
        if previous is not None and w["valid_time"] <= previous:
            late_fills.append({
                "city": w["city"],
                "valid_time": w["valid_time"],
                "first_written_at": w["first_written_at"],
                "write_lag": w["first_written_at"] - w["valid_time"],
            })
            continue
        events.append({
            "city": w["city"],
            "valid_time": w["valid_time"],
            "first_written_at": w["first_written_at"],
            "previous_valid_time": previous,
            "peak_age": None if previous is None else w["first_written_at"] - previous,
            "write_lag": w["first_written_at"] - w["valid_time"],
            "last_write_lag": w["computed_at"] - w["valid_time"],
        })
        running[w["city"]] = w["valid_time"]
    return events, late_fills


def advance_events(writes, since) -> list:
    """
    The writes that moved a city's "current" rating forward, with the exact age the previous one
    had reached just before.

    Live rows are walked in (first_written_at, valid_time, city) order with a running per-city
    maximum valid_time, seeded from the newest live row first written before `since`. One event per
    write that advances the maximum: city, valid_time, first_written_at, previous valid_time,
    peak_age (first_written_at minus the previous maximum; None when the city had no earlier row),
    write_lag (first_written_at minus valid_time) and last_write_lag (computed_at minus valid_time,
    informational: a retry rewrites computed_at). A late-filled older slot never advances the
    maximum, so it is no event; backfill rows are ignored.
    """
    return _walk(writes, since)[0]


def _lag_stats(deltas) -> dict:
    if not deltas:
        return {"count": 0, "median_min": None, "p95_min": None, "max_min": None}
    seconds = sorted(d.total_seconds() for d in deltas)
    p95 = seconds[max(0, math.ceil(0.95 * len(seconds)) - 1)]  # nearest rank
    return {
        "count": len(seconds),
        "median_min": round(statistics.median(seconds) / 60, 1),
        "p95_min": round(p95 / 60, 1),
        "max_min": round(seconds[-1] / 60, 1),
    }


def _peak_stats(deltas, max_age_min) -> dict:
    limit = timedelta(minutes=max_age_min)
    warn = timedelta(minutes=WARN_PEAK_MIN)
    return {
        "count": len(deltas),
        "max_min": _minutes(max(deltas)) if deltas else None,
        "above_75": sum(1 for d in deltas if d > warn),
        "above_max": sum(1 for d in deltas if d > limit),  # exact timedelta, never the rounded minutes
    }


def evaluate_dry(inputs, since, until, max_age_min=DEFAULT_MAX_AGE_MIN, min_hours=DRY_MIN_HOURS) -> dict:
    """
    The dry-soak numbers for [since, until) from loaded inputs (pure, no I/O, no wall clock).

    Returns per-city and overall write lag and peak age, the trailing age at `until`, the fallback
    share, Phase 5's slot verdicts from `dlr_live_window_check.evaluate_window`, and a `verdict`
    of "pass" or "fail" with plain-English `lines`.
    """
    since, until = _ts(since), _ts(until)
    slot_start, hours = _slot_window(since, until)
    limit = timedelta(minutes=max_age_min)

    live = [w for w in inputs["writes"] if w["origin"] == "live" and w["first_written_at"] < until]
    events, late_fills = _walk(live, since)

    window_rows = [w for w in live if w["first_written_at"] >= since]
    running_max = {}
    for w in live:
        current = running_max.get(w["city"])
        if current is None or w["valid_time"] > current:
            running_max[w["city"]] = w["valid_time"]

    cities = sorted({w["city"] for w in live} | set(config.LOCATIONS), key=_city_order)
    city_entries = []
    for city in cities:
        mine = [e for e in events if e["city"] == city]
        peaks = [e["peak_age"] for e in mine if e["peak_age"] is not None]
        rows = [w for w in window_rows if w["city"] == city]
        newest = running_max.get(city)
        city_entries.append({
            "city": city,
            "status": "ok" if newest is not None else "missing",
            "lag": _lag_stats([e["write_lag"] for e in mine]),
            "last_write_lag_max_min": _minutes(max(e["last_write_lag"] for e in mine)) if mine else None,
            "peak": _peak_stats(peaks, max_age_min),
            "trailing_age_min": None if newest is None else _minutes(until - newest),
            "trailing_breach": newest is not None and (until - newest) > limit,
            "fallback": {
                "rows": len(rows),
                "fallback": sum(1 for w in rows if w["fallback"]),
                "share": round(sum(1 for w in rows if w["fallback"]) / len(rows), 3) if rows else None,
            },
        })

    all_peaks = [e["peak_age"] for e in events if e["peak_age"] is not None]
    overall = {
        "lag": _lag_stats([e["write_lag"] for e in events]),
        "peak": _peak_stats(all_peaks, max_age_min),
    }

    rating_rows = [{"city": w["city"], "valid_time": w["valid_time"], "run_id": w["run_id"]} for w in live]
    slots = dlr_live_window_check.evaluate_window(inputs["runs"], inputs["run_rows"], rating_rows, slot_start, hours)

    failures = []
    for entry in city_entries:
        if entry["status"] == "missing":
            failures.append(f"{entry['city']} has no live row at all")
        if entry["peak"]["above_max"]:
            failures.append(
                f"{entry['city']}: {entry['peak']['above_max']} write(s) arrived after the previous rating was "
                f"already older than {max_age_min:g} min (worst {entry['peak']['max_min']:.1f} min)")
        if entry["trailing_breach"]:
            failures.append(
                f"{entry['city']}: the newest rating is {entry['trailing_age_min']:.1f} min old at the end of the window")
    for s in slots["slots"]:
        if s["verdict"] in ("missing", "incomplete"):
            failures.append(f"slot {s['slot']} is {s['verdict']}" + (f" ({s['note']})" if s["note"] else ""))

    if hours < min_hours:
        failures.insert(0, f"window shorter than {min_hours:g} h ({hours} h between --since and --until)")
    if not window_rows:
        failures.insert(0, "no live rows in the window")

    warnings = []
    if overall["peak"]["above_75"]:
        warnings.append(
            f"the current rating reached {overall['peak']['max_min']:.1f} min old (above {WARN_PEAK_MIN} min): "
            f"a single slow hour would breach the {max_age_min:g} min limit")

    verdict = "fail" if failures else "pass"
    if verdict == "pass":
        lines = [
            f"PASS: all {hours} hourly slots landed; the current rating was never older than "
            f"{_fmt(overall['peak']['max_min'])} min (limit {max_age_min:g} min); a rating usually landed "
            f"{_fmt(overall['lag']['median_min'])} min after its hour and at worst "
            f"{_fmt(overall['lag']['max_min'])} min after."
        ]
    else:
        lines = ["FAIL: " + failure for failure in failures]

    return {
        "mode": "dry",
        "since": _iso(since),
        "until": _iso(until),
        "hours": hours,
        "max_age_min": max_age_min,
        "min_hours": min_hours,
        "cities": city_entries,
        "overall": overall,
        "events": [
            {
                "city": e["city"],
                "valid_time": _iso(e["valid_time"]),
                "first_written_at": _iso(e["first_written_at"]),
                "previous_valid_time": None if e["previous_valid_time"] is None else _iso(e["previous_valid_time"]),
                "peak_age_min": None if e["peak_age"] is None else _minutes(e["peak_age"]),
                "write_lag_min": _minutes(e["write_lag"]),
                "last_write_lag_min": _minutes(e["last_write_lag"]),
            }
            for e in events
        ],
        "late_fills": {
            "count": len(late_fills),
            "max_lag_min": _minutes(max(f["write_lag"] for f in late_fills)) if late_fills else None,
            "items": [
                {"city": f["city"], "valid_time": _iso(f["valid_time"]),
                 "first_written_at": _iso(f["first_written_at"]), "write_lag_min": _minutes(f["write_lag"])}
                for f in late_fills
            ],
        },
        "slots": slots,
        "warnings": warnings,
        "failures": failures,
        "verdict": verdict,
        "lines": lines,
    }


def _fmt(value) -> str:
    return "-" if value is None else f"{value:.1f}"


def render_markdown(result) -> str:
    limit = f"{result['max_age_min']:g}"
    out = [
        "# Dry soak report (E2E-02, D-07)",
        "",
        f"Window: {result['since']} to {result['until']} ({result['hours']} hourly slots). "
        f"A breach is a current rating strictly older than {limit} min.",
        "",
    ]
    out += [f"**{line}**" if i == 0 else line for i, line in enumerate(result["lines"])]
    for warning in result["warnings"]:
        out += ["", f"WARNING: {warning}"]
    missing = [c["city"] for c in result["cities"] if c["status"] == "missing"]
    if missing:
        out += ["", "Cities with no live row: " + ", ".join(missing)]

    out += ["", "## Write lag (first_written_at minus valid_time, minutes)", "",
            "| city | writes | median | p95 | max | last-write lag max (informational) |",
            "|---|---|---|---|---|---|"]
    for c in result["cities"]:
        lag = c["lag"]
        out.append(f"| {c['city']} | {lag['count']} | {_fmt(lag['median_min'])} | {_fmt(lag['p95_min'])} | "
                   f"{_fmt(lag['max_min'])} | {_fmt(c['last_write_lag_max_min'])} |")
    lag = result["overall"]["lag"]
    out.append(f"| overall | {lag['count']} | {_fmt(lag['median_min'])} | {_fmt(lag['p95_min'])} | "
               f"{_fmt(lag['max_min'])} | |")

    out += ["", "## Peak age (age of the previous rating just before the next one landed, minutes)", "",
            f"| city | peak max | above {WARN_PEAK_MIN} | above {limit} | age at end of window |",
            "|---|---|---|---|---|"]
    for c in result["cities"]:
        p = c["peak"]
        out.append(f"| {c['city']} | {_fmt(p['max_min'])} | {p['above_75']} | {p['above_max']} | "
                   f"{_fmt(c['trailing_age_min'])} |")
    p = result["overall"]["peak"]
    out.append(f"| overall | {_fmt(p['max_min'])} | {p['above_75']} | {p['above_max']} | |")

    out += ["", "## Fallback share (informational: a fallback row is a fresh row, not a breach)", "",
            "| city | rows | fallback | share |", "|---|---|---|---|"]
    for c in result["cities"]:
        f = c["fallback"]
        share = "-" if f["share"] is None else f"{100 * f['share']:.1f} %"
        out.append(f"| {c['city']} | {f['rows']} | {f['fallback']} | {share} |")

    late = result["late_fills"]
    out += ["", "## Late fills (an older slot first written inside the window; informational, never a breach)", ""]
    if late["count"]:
        out += ["| city | valid_time | first written | write lag |", "|---|---|---|---|"]
        out += [f"| {i['city']} | {i['valid_time']} | {i['first_written_at']} | {i['write_lag_min']:.1f} |"
                for i in late["items"]]
    else:
        out.append("No late fills.")

    out += ["", "## Slot verdicts (dlr_live_window_check.evaluate_window)", "",
            dlr_live_window_check.format_report(result["slots"])]

    slowest = sorted((e for e in result["events"] if e["peak_age_min"] is not None),
                     key=lambda e: -e["peak_age_min"])[:10]
    out += ["", "## Ten largest peak ages", "",
            "| city | valid_time | first written | peak age | write lag |", "|---|---|---|---|---|"]
    for e in slowest:
        out.append(f"| {e['city']} | {e['valid_time']} | {e['first_written_at']} | "
                   f"{e['peak_age_min']:.1f} | {e['write_lag_min']:.1f} |")
    return "\n".join(out) + "\n"


def render_json(result) -> str:
    return json.dumps(result, indent=2) + "\n"


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def _time_arg(value):
    try:
        parsed = _ts(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an ISO timestamp: {value!r}") from None
    if parsed is None:
        raise argparse.ArgumentTypeError("a timestamp is required, e.g. 2026-10-25T00:00:00Z")
    return parsed


def _build_parser():
    parser = argparse.ArgumentParser(description="Dry-soak export (read-only) and report (offline).")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="owner-run, read-only: copy the live window into files")
    export.add_argument("--mode", choices=["dry"], required=True)
    export.add_argument("--since", required=True, type=_time_arg, help="window start, ISO UTC")
    export.add_argument("--until", required=True, type=_time_arg, help="window end, ISO UTC")
    export.add_argument("--out-dir", required=True, help="directory for the four export files")

    rep = sub.add_parser("report", help="offline: compute the dry soak from the export files")
    rep.add_argument("--mode", choices=["dry"], required=True)
    rep.add_argument("--in-dir", required=True, help="directory written by export")
    rep.add_argument("--min-hours", type=float, default=DRY_MIN_HOURS)
    rep.add_argument("--max-age-min", type=float, default=DEFAULT_MAX_AGE_MIN)
    rep.add_argument("--out", required=True, help="markdown report path")
    rep.add_argument("--json-out", help="also write the full result as JSON")
    return parser


def main(argv=None, connect_fn=None, fetch_runs_fn=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "export":
        import supabase_store

        if args.until <= args.since:
            parser.error("--until must be after --since")
        try:
            meta = export_dry(args.since, args.until, args.out_dir,
                              connect_fn=connect_fn, fetch_runs_fn=fetch_runs_fn)
        except supabase_store.StoreError as exc:
            print(f"export failed: {supabase_store.redact(str(exc))}", file=sys.stderr)
            return 1
        print(f"exported {meta['rows']['writes']} live rows and {meta['rows']['runs']} pipeline runs "
              f"to {args.out_dir}")
        return 0

    try:
        inputs = load_inputs(args.in_dir)
        since, until = _ts(inputs["meta"]["since"]), _ts(inputs["meta"]["until"])
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    result = evaluate_dry(inputs, since, until, args.max_age_min, args.min_hours)
    with open(args.out, "w") as fh:
        fh.write(render_markdown(result))
    if args.json_out:
        with open(args.json_out, "w") as fh:
            fh.write(render_json(result))
    for line in result["lines"]:
        print(line)
    for warning in result["warnings"]:
        print(f"WARNING: {warning}")
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    sys.exit(main())
