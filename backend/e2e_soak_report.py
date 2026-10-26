"""
Dry-soak and 72 h soak export and report (production-pipeline Phase 6: E2E-02, D-07, D-08)
==========================================================================================
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

Soak mode (06-07, the 72 h window). The same two subcommands take `--mode soak`:

    export  --mode soak --since G --until U --out-dir DIR
        Everything the dry export writes, plus probes.csv from `ops.freshness_log` (the five-minute
        probe log pg_cron fills; one read-only SELECT with bound parameters).

    report  --mode soak --in-dir DIR [--min-hours 72] [--probe-interval-min 5] [--max-age-min 90]
            [--annotations FILE] --out FILE.md [--json-out FILE]
        Turns the window into a breach list. A WRITE breach is an exact interval in which a city's
        current rating was strictly older than --max-age-min, found from the writes themselves
        (running maximum valid_time from first_written_at, seeded from the newest live row first
        written before G). The probe log adds coverage (distinct probe times against the expected
        count, gaps longer than two intervals plus one minute including at both window edges,
        incomplete probes) and any probe breach no write interval explains. Every breach is sorted by
        start time, then config.LOCATIONS order, then kind, with the id `<kind>:<city>:<start ISO>`
        (kinds write, probe, probe-gap).

        A breach is explained only by a rule-derived cause (Phase 5's slot verdicts and pipeline_run)
        or an owner annotation, printed verbatim with its author and date. A deploy during the
        window is derived from the data and shown as context; it never excuses a breach (D-08).
        Exit 0 only when the window is at least --min-hours, probes are present and every breach and
        probe gap is explained; 1 otherwise; 2 on missing or malformed input or annotations.

The module never writes to the database, data/shadow or any shadow file.
"""

import argparse
import csv
import json
import math
import os
import re
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import config
import dlr_live_window_check
import latest_rating_contract

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BACKEND_DIR)

DEFAULT_MAX_AGE_MIN = latest_rating_contract.STALE_AFTER_MINUTES  # OD-4: 90, the rule of latest_rating.is_stale
WARN_PEAK_MIN = 75         # above this a single slow hour would breach (06-RESEARCH Pitfall 9)
DRY_MIN_HOURS = 12
SOAK_MIN_HOURS = 72        # ROADMAP Phase 6 success criterion 4
PROBE_INTERVAL_MIN = 5     # supabase/ops/soak_cron_schedule.sql runs every five minutes

_ONE_HOUR = timedelta(hours=1)

WRITES_FILE = "writes.csv"
RUNS_FILE = "runs.csv"
GH_RUNS_FILE = "gh_runs.json"
META_FILE = "export_meta.json"
PROBES_FILE = "probes.csv"

WRITES_COLUMNS = (
    "city", "valid_time", "first_written_at", "computed_at", "run_id", "origin", "status", "fallback",
    "pipeline_version", "config_fingerprint", "forecast_model_sha256", "anomaly_model_sha256",
    "forecast_method", "config_version",
)
RUNS_COLUMNS = ("run_id", "run_attempt", "started_at", "finished_at", "window_end", "cities_ok", "cities_failed")
PROBES_COLUMNS = ("probed_at", "city", "latest_valid_time", "age_seconds", "breach")

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
# The soak's own record (D-14): one row per city per five-minute probe, written by ops.log_freshness().
PROBES_SQL = (
    "select probed_at, city, latest_valid_time, age_seconds, breach "
    "from ops.freshness_log "
    "where probed_at >= %(since)s and probed_at < %(until)s "
    "order by probed_at, city"
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


def export_window(since, until, out_dir, mode="dry", connect_fn=None, fetch_runs_fn=None, now_fn=None) -> dict:
    """
    Read the live window read-only and write writes.csv, runs.csv, gh_runs.json and export_meta.json
    into `out_dir`; in `soak` mode also probes.csv from ops.freshness_log. Returns the export_meta
    dict. Nothing is written when any read fails.

    `connect_fn` defaults to Phase 4's `supabase_store.connect`, `fetch_runs_fn(start, hours)` to
    `dlr_live_window_check.fetch_runs`; a failure other than a StoreError is re-raised as a
    StoreError carrying the exception type and redacted text. Soak mode fetches the Actions runs
    from two hours before the first slot, so the slots a breach at the window start points to are
    covered (cause attribution).
    """
    import supabase_store

    since, until = _ts(since), _ts(until)
    if connect_fn is None:
        connect_fn = supabase_store.connect
    if fetch_runs_fn is None:
        fetch_runs_fn = dlr_live_window_check.fetch_runs
    params = {"since": since, "until": until}
    slot_start = since.replace(minute=0, second=0, microsecond=0)
    if mode == "soak":
        slot_start = slot_start - 2 * _ONE_HOUR
    gh_hours = max(1, math.ceil((until - slot_start) / _ONE_HOUR))

    conn = None
    failure = None
    writes = run_rows = gh_runs = probes = None
    try:
        conn = connect_fn()
        conn.execute(READ_ONLY_SQL)  # before the first query: this session can no longer write
        writes = _rows(conn, WRITES_SQL, params)
        run_rows = _rows(conn, RUNS_SQL, params)
        if mode == "soak":
            probes = _rows(conn, PROBES_SQL, params)
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
        "mode": mode,
        "since": _iso(since),
        "until": _iso(until),
        "exported_at": _iso(now),
        "rows": {"writes": len(writes), "runs": len(run_rows), "gh_runs": len(gh_runs)},
        "git_head": _git_head(),
    }
    if mode == "soak":
        meta["rows"]["probes"] = len(probes)
    os.makedirs(out_dir, exist_ok=True)
    _write_csv(os.path.join(out_dir, WRITES_FILE), WRITES_COLUMNS, writes)
    _write_csv(os.path.join(out_dir, RUNS_FILE), RUNS_COLUMNS, run_rows)
    if mode == "soak":
        _write_csv(os.path.join(out_dir, PROBES_FILE), PROBES_COLUMNS, probes)
    with open(os.path.join(out_dir, GH_RUNS_FILE), "w") as fh:
        json.dump(gh_runs, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(out_dir, META_FILE), "w") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    return meta


def export_dry(since, until, out_dir, connect_fn=None, fetch_runs_fn=None, now_fn=None) -> dict:
    """The dry-soak export (see export_window)."""
    return export_window(since, until, out_dir, "dry", connect_fn, fetch_runs_fn, now_fn)


# ──────────────────────────────────────────────────────────────────────────────
# report (offline)
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_WRITES_COLUMNS = ("city", "valid_time", "first_written_at", "computed_at", "run_id", "origin", "fallback")
REQUIRED_RUNS_COLUMNS = ("run_id", "window_end", "cities_ok", "cities_failed")
REQUIRED_PROBES_COLUMNS = PROBES_COLUMNS


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


def _float_cell(value):
    if value is None or str(value).strip() == "":
        return None
    parsed = float(value)
    if math.isnan(parsed) or math.isinf(parsed):
        raise ValueError("not a finite number")
    return parsed


def _bool_cell(value):
    text = str(value).strip().lower()
    if text in ("true", "t", "1"):
        return True
    if text in ("false", "f", "0"):
        return False
    raise ValueError("not a boolean")


def load_inputs(in_dir, mode="dry") -> dict:
    """
    Read the export files into `{writes, run_rows, runs, meta}` (plus `probes` in soak mode) with
    timestamps parsed. Raises InputError naming the file (and the column) when a file is missing,
    a required column is absent or a value is malformed.
    """
    names = [WRITES_FILE, RUNS_FILE, GH_RUNS_FILE, META_FILE]
    if mode == "soak":
        names.append(PROBES_FILE)
    paths = {name: os.path.join(in_dir, name) for name in names}
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
    loaded = {"writes": writes, "run_rows": run_rows, "runs": runs, "meta": meta}

    if mode == "soak":
        probes = []
        for number, raw in enumerate(_read_csv(paths[PROBES_FILE], PROBES_FILE, REQUIRED_PROBES_COLUMNS), start=2):
            probes.append({
                "probed_at": _parse(PROBES_FILE, number, "probed_at", raw["probed_at"], _timestamp_cell),
                "city": raw["city"],
                "latest_valid_time": _parse(PROBES_FILE, number, "latest_valid_time", raw["latest_valid_time"], _ts),
                "age_seconds": _parse(PROBES_FILE, number, "age_seconds", raw["age_seconds"], _float_cell),
                "breach": _parse(PROBES_FILE, number, "breach", raw["breach"], _bool_cell),
            })
        loaded["probes"] = probes
    return loaded


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


# ──────────────────────────────────────────────────────────────────────────────
# soak mode (06-07, E2E-02): the 72 h window as a breach list
# ──────────────────────────────────────────────────────────────────────────────

ALL_CITIES = "ALL"  # the city of a probe gap: it belongs to the log, not to one city
KIND_ORDER = {"write": 0, "probe": 1, "probe-gap": 2}


def _new_breach(kind, city, start, end, peak_age=None, ended_by="", max_valid_time=None) -> dict:
    return {
        "kind": kind, "city": city, "start": start, "end": end, "peak_age": peak_age,
        "probe_count": 0, "ended_by": ended_by, "max_valid_time": max_valid_time,
        "cause": None, "context": [], "explanation": None,
    }


def _close_segment(city, current, started, ended, limit, ended_by):
    """
    The breach (or None) inside one stretch in which `current` was the city's newest valid_time,
    from `started` until `ended`. With no rating at all the whole stretch is a breach; otherwise
    the breach starts when the age reaches the limit (or at `started` when it already has) and
    exists only if the stretch ends STRICTLY after that, on the exact timedelta (OD-4).
    """
    if ended <= started:
        return None
    if current is None:
        return _new_breach("write", city, started, ended, None, ended_by)
    threshold = current + limit
    if ended <= threshold:
        return None
    return _new_breach("write", city, max(started, threshold), ended, ended - current, ended_by, current)


def write_breaches(writes, since, until, max_age_min=DEFAULT_MAX_AGE_MIN) -> list:
    """
    The exact intervals in which a city's current rating was strictly older than `max_age_min`,
    from the writes alone (06-RESEARCH Pattern 3).

    Per city the live rows first written before `until` are walked in (first_written_at,
    valid_time) order with a running maximum valid_time, seeded from the newest live row first
    written before `since`. The maximum is what a consumer sees as current. A breach interval
    starts where the age first exceeds the limit (or at `since` when it already does, or when the
    city had no rating at all) and ends at the next write that advances the maximum, or at
    `until`. peak_age is the end minus the maximum (None with no rating). A late-filled older
    slot never advances the maximum and a backfill row is ignored, so neither creates a breach.
    """
    since, until = _ts(since), _ts(until)
    limit = timedelta(minutes=max_age_min)
    live = [w for w in writes if w["origin"] == "live" and w["first_written_at"] < until]
    cities = sorted({w["city"] for w in live} | set(config.LOCATIONS), key=_city_order)

    found = []
    for city in cities:
        mine = [w for w in live if w["city"] == city]
        current = None
        for w in mine:
            if w["first_written_at"] < since and (current is None or w["valid_time"] > current):
                current = w["valid_time"]
        inside = sorted((w for w in mine if w["first_written_at"] >= since),
                        key=lambda w: (w["first_written_at"], w["valid_time"]))
        started = since
        for w in inside:
            if current is not None and w["valid_time"] <= current:
                continue  # a late fill or a same-slot rewrite: the maximum does not move
            breach = _close_segment(city, current, started, w["first_written_at"], limit, "write")
            if breach is not None:
                found.append(breach)
            current, started = w["valid_time"], w["first_written_at"]
        breach = _close_segment(city, current, started, until, limit, "window end")
        if breach is not None:
            found.append(breach)
    return found


def probe_findings(probes, since, until, interval_min=PROBE_INTERVAL_MIN) -> dict:
    """
    What the probe log covers in [since, until): the distinct probe times against the expected
    count (whole intervals in the window), the gaps longer than two intervals plus one minute
    (the window edges count: a log that starts late or stops early has a gap), the incomplete
    probes (a city missing from the probe) and each city's probe rows in time order.
    """
    since, until = _ts(since), _ts(until)
    interval = timedelta(minutes=interval_min)
    allowed = 2 * interval + timedelta(minutes=1)
    by_time, by_city = {}, {}
    for row in probes:
        if since <= row["probed_at"] < until:
            by_time.setdefault(row["probed_at"], []).append(row)
            by_city.setdefault(row["city"], []).append(row)
    times = sorted(by_time)

    gaps = []
    if times:
        edges = [since] + times + [until]
        for before, after in zip(edges, edges[1:]):
            if after - before > allowed:
                gaps.append({"start": before, "end": after})

    incomplete = []
    for when in times:
        present = {row["city"] for row in by_time[when]}
        missing = [c for c in config.LOCATIONS if c not in present]
        if missing:
            incomplete.append({"probed_at": when, "rows": len(by_time[when]), "missing": missing})

    for rows in by_city.values():
        rows.sort(key=lambda row: row["probed_at"])
    return {
        "interval_min": interval_min,
        "expected": int((until - since) // interval),
        "found": len(times),
        "gaps": gaps,
        "incomplete": incomplete,
        "by_city": by_city,
    }


def merge_breaches(write_found, findings) -> list:
    """
    One sorted breach list from the write intervals and the probe log.

    A probe row with breach true that falls inside a write interval of its own city is counted on
    that interval. Consecutive uncovered breach rows of one city become a `probe` breach (the log
    saw a breach no write interval explains), and each probe gap becomes a `probe-gap` breach for
    city ALL. Ids are `<kind>:<city>:<start ISO>`; the order is start time, then
    config.LOCATIONS order, then kind (write, probe, probe-gap).
    """
    breaches = [dict(b, context=list(b["context"])) for b in write_found]

    for city in sorted(findings["by_city"], key=_city_order):
        mine = [b for b in breaches if b["kind"] == "write" and b["city"] == city]
        run = None
        for row in findings["by_city"][city]:
            if not row["breach"]:
                run = None
                continue
            cover = next((b for b in mine if b["start"] <= row["probed_at"] <= b["end"]), None)
            if cover is not None:
                cover["probe_count"] += 1
                run = None
                continue
            age = None if row["age_seconds"] is None else timedelta(seconds=row["age_seconds"])
            if run is None:
                run = _new_breach("probe", city, row["probed_at"], row["probed_at"], age, "probe")
                run["probe_count"] = 0
                breaches.append(run)
            run["end"] = row["probed_at"]
            run["probe_count"] += 1
            if age is not None and (run["peak_age"] is None or age > run["peak_age"]):
                run["peak_age"] = age

    for gap in findings["gaps"]:
        breaches.append(_new_breach("probe-gap", ALL_CITIES, gap["start"], gap["end"], None, "probe"))

    for b in breaches:
        b["id"] = f"{b['kind']}:{b['city']}:{_iso(b['start'])}"
    breaches.sort(key=lambda b: (b["start"], _city_order(b["city"]), KIND_ORDER[b["kind"]]))
    return breaches


def _breach_json(b) -> dict:
    return {
        "id": b["id"],
        "kind": b["kind"],
        "city": b["city"],
        "start": _iso(b["start"]),
        "end": _iso(b["end"]),
        "duration_min": _minutes(b["end"] - b["start"]),
        "peak_age_min": None if b["peak_age"] is None else _minutes(b["peak_age"]),
        "probe_count": b["probe_count"],
        "ended_by": b["ended_by"],
        "cause": b["cause"],
        "context": b["context"],
        "explanation": b["explanation"],
    }


def _breach_summary(b) -> str:
    """A plain-English line for one breach, used in the failure list."""
    span = f"from {_iso(b['start'])} to {_iso(b['end'])}"
    if b["kind"] == "write":
        what = (f"{b['city']}: the current rating was older than the limit {span}" +
                ("" if b["peak_age"] is None else f" (peak {_minutes(b['peak_age']):.1f} min)"))
        if b["peak_age"] is None:
            what = f"{b['city']}: no rating at all {span}"
    elif b["kind"] == "probe":
        what = f"{b['city']}: the probe log saw a breach {span} that no write interval explains"
    else:
        what = f"the probe log has a gap {span} ({_minutes(b['end'] - b['start']):.1f} min)"
    return f"{b['id']} has no cause or annotation: {what}"


# ── cause attribution (Phase 5's slot verdicts) ───────────────────────────────

LATE_RUN_MIN = 30       # a row first written more than this after its slot makes the next breach a "late run"
CONTEXT_WINDOW = timedelta(hours=2)   # a deploy this far before a breach (up to its end) is shown as its context
CAUSE_ERROR_CHARS = 200


def _plain(value) -> str:
    """A number without a trailing .0 (40.0 -> '40', 30.1 -> '30.1')."""
    return f"{round(value, 1):g}"


def _city_failure(city, run_ids, run_rows_by_id):
    """'city failure: <outcome> (<redacted error>)' when a run of the slot recorded the city as failed."""
    import supabase_store

    for run_id in run_ids:
        failed = (run_rows_by_id.get(run_id) or {}).get("cities_failed")
        if not isinstance(failed, dict) or city not in failed:
            continue
        entry = failed[city] if isinstance(failed[city], dict) else {}
        text = f"city failure: {entry.get('outcome') or 'unknown'}"
        error = entry.get("error")
        if error:
            text += f" ({supabase_store.redact(str(error), limit=CAUSE_ERROR_CHARS)})"
        return text
    return None


def attribute_causes(breaches, inputs, since, until) -> list:
    """
    Set `cause` on every write breach from Phase 5's records; a breach no rule explains keeps
    cause None (it then needs an owner annotation).

    `dlr_live_window_check.evaluate_window` runs once over the window plus two hours of lead-in
    with the Actions runs, pipeline_run rows and {city, valid_time, run_id} rows. For each write
    breach the first slot after the city's newest rating before the breach (for a city with no
    rating: the slot before its first row in the window) is inspected, and the rules apply in
    this order:

      missing         -> "no workflow run for slot <slot> (dispatch missing)"
      failed-visible  -> "workflow run <id> concluded <conclusion>"
      the city in that slot's cities_failed -> "city failure: <outcome>" with the redacted error
                        (appended after a red run's cause: both are true)
      the city's row first written more than LATE_RUN_MIN after the slot
                      -> "late run: written +<n> min after the slot"
    """
    since, until = _ts(since), _ts(until)
    lead_in = since.replace(minute=0, second=0, microsecond=0) - 2 * _ONE_HOUR
    hours = max(1, math.ceil((until - lead_in) / _ONE_HOUR))
    live = [w for w in inputs["writes"] if w["origin"] == "live" and w["first_written_at"] < until]
    rating_rows = [{"city": w["city"], "valid_time": w["valid_time"], "run_id": w["run_id"]} for w in live]
    window = dlr_live_window_check.evaluate_window(inputs["runs"], inputs["run_rows"], rating_rows, lead_in, hours)
    slots = {s["slot"]: s for s in window["slots"]}
    run_rows_by_id = {str(r["run_id"]): r for r in inputs["run_rows"]}

    first_written = {}   # (city, valid_time) -> earliest first_written_at
    first_in_window = {}  # city -> valid_time of its earliest row written inside the window
    for w in live:
        key = (w["city"], w["valid_time"])
        if key not in first_written or w["first_written_at"] < first_written[key]:
            first_written[key] = w["first_written_at"]
        if w["first_written_at"] >= since and (w["city"] not in first_in_window
                                               or w["valid_time"] < first_in_window[w["city"]]):
            first_in_window[w["city"]] = w["valid_time"]

    for b in breaches:
        if b["kind"] != "write":
            continue
        if b["max_valid_time"] is not None:
            slot_time = b["max_valid_time"].replace(minute=0, second=0, microsecond=0) + _ONE_HOUR
        elif b["city"] in first_in_window:
            slot_time = first_in_window[b["city"]] - _ONE_HOUR
        else:
            slot_time = since.replace(minute=0, second=0, microsecond=0)
        verdict = slots.get(_iso(slot_time))
        if verdict is None:
            continue

        parts = []
        if verdict["verdict"] == "missing":
            if verdict["run_ids"]:
                parts.append(f"workflow run {', '.join(verdict['run_ids'])} did not finish "
                             f"(slot {verdict['slot']}: {verdict['note']})")
            else:
                parts.append(f"no workflow run for slot {verdict['slot']} (dispatch missing)")
        elif verdict["verdict"] == "failed-visible":
            red = next((rid, c) for rid, c in zip(verdict["run_ids"], verdict["conclusions"])
                       if c in dlr_live_window_check.RED_CONCLUSIONS)
            parts.append(f"workflow run {red[0]} concluded {red[1]}")
        failure = _city_failure(b["city"], verdict["run_ids"], run_rows_by_id)
        if failure:
            parts.append(failure)
        if not parts:
            written = first_written.get((b["city"], slot_time))
            if written is not None and written - slot_time > timedelta(minutes=LATE_RUN_MIN):
                parts.append(f"late run: written +{_plain((written - slot_time).total_seconds() / 60)} min "
                             f"after the slot")
        b["cause"] = "; ".join(parts) or None
    return breaches


# ── deploys derived from the data (D-08) ─────────────────────────────────────

DEPLOY_COLUMNS = ("pipeline_version", "config_fingerprint", "forecast_model_sha256", "anomaly_model_sha256",
                  "forecast_method", "config_version")
CONFIG_PATHS = ("backend/config.py", "backend/city_point.py", "backend/rating_identity.py")
WORKFLOW_PATH = ".github/workflows/dlr_live.yml"
# paths that cannot change what a live run computes; anything else outside the runtime classes is "other"
NON_RUNTIME_PREFIXES = ("docs/", ".planning/", "data/shadow/", "backend/tests/", "supabase/", ".github/", ".gitignore")
_COMMIT_ID = re.compile(r"[0-9a-f]{7,40}")
GIT_TIMEOUT_S = 30

CLASS_NO_RUNTIME = "no runtime change"
CLASS_FETCH = "unknown: commit not available locally (run git fetch)"
CLASS_NOT_A_COMMIT = "unknown: pipeline_version is not a commit id"
CLASS_SAME_VERSION = "unknown: pipeline_version unchanged, no commits to compare"


def _run_git(argv, cwd):
    """`(returncode, stdout)` of a git command, run as an argv list (no shell) in `cwd`."""
    done = subprocess.run(argv, capture_output=True, text=True, timeout=GIT_TIMEOUT_S, cwd=cwd)
    return done.returncode, done.stdout


def _class_of_paths(paths) -> str:
    if any(p.startswith("data/models/") for p in paths):
        return "model"
    if any(p in CONFIG_PATHS for p in paths):
        return "config"
    if WORKFLOW_PATH in paths:
        return "workflow"
    if any((p.startswith("backend/") and not p.startswith("backend/tests/")) or p == "requirements.txt"
           for p in paths):
        return "code"
    if all(p.startswith(NON_RUNTIME_PREFIXES) for p in paths):
        return CLASS_NO_RUNTIME
    return "other"


def _classify_change(old, new, runner, repo_root) -> tuple:
    """`(class, files)`. Versions are validated as 7-40 lowercase hex before git is ever called."""
    if not (_COMMIT_ID.fullmatch(old or "") and _COMMIT_ID.fullmatch(new or "")):
        return CLASS_NOT_A_COMMIT, []
    if old == new:
        return CLASS_SAME_VERSION, []
    try:
        code, output = runner(["git", "diff", "--name-only", old, new], repo_root)
    except Exception:  # noqa: BLE001 - an unreadable repository is a flag, never a guess
        return CLASS_FETCH, []
    if code != 0:
        return CLASS_FETCH, []
    files = [line.strip() for line in output.splitlines() if line.strip()]
    return (_class_of_paths(files) if files else CLASS_NO_RUNTIME), files


def derive_deploys(writes, since, until, git_runner=None, repo_root=REPO_ROOT) -> list:
    """
    Every deploy inside [since, until), derived from the rows themselves (06-RESEARCH Pattern 6).

    Per city the live rows are ordered by valid_time; a row whose pipeline_version,
    config_fingerprint, forecast_model_sha256, anomaly_model_sha256, forecast_method or
    config_version differs from the city's previous row is a change point, and change points
    first written inside the window are grouped per (old version, new version). Each group gives
    {old, new, first_slot, first_written_at, cities, changed, class, files, is_event}.

    The class comes from `git diff --name-only <old> <new>` (argv list, cwd `repo_root`, through
    the injectable `git_runner(argv, cwd) -> (returncode, stdout)`): model, config, workflow, code,
    "no runtime change" (listed, `is_event` false) or other. A version that is not 7 to 40
    lowercase hex characters ('unknown' included) is flagged and never passed to git; a commit git
    cannot find is flagged "run git fetch"; nothing is guessed.
    """
    since, until = _ts(since), _ts(until)
    runner = git_runner or _run_git
    live = [w for w in writes if w["origin"] == "live" and w["first_written_at"] < until]

    groups = {}
    for city in sorted({w["city"] for w in live}, key=_city_order):
        rows = sorted((w for w in live if w["city"] == city), key=lambda w: (w["valid_time"], w["first_written_at"]))
        for before, row in zip(rows, rows[1:]):
            changed = [c for c in DEPLOY_COLUMNS if (before.get(c) or "") != (row.get(c) or "")]
            if not changed or not (since <= row["first_written_at"] < until):
                continue
            key = (before.get("pipeline_version") or "", row.get("pipeline_version") or "")
            group = groups.setdefault(key, {"first_slot": row["valid_time"], "first_written_at": row["first_written_at"],
                                            "cities": set(), "changed": set()})
            group["first_slot"] = min(group["first_slot"], row["valid_time"])
            group["first_written_at"] = min(group["first_written_at"], row["first_written_at"])
            group["cities"].add(city)
            group["changed"].update(changed)

    deploys = []
    for (old, new), group in groups.items():
        klass, files = _classify_change(old, new, runner, repo_root)
        deploys.append({
            "old": old,
            "new": new,
            "first_slot": _iso(group["first_slot"]),
            "first_written_at": _iso(group["first_written_at"]),
            "cities": sorted(group["cities"], key=_city_order),
            "changed": [c for c in DEPLOY_COLUMNS if c in group["changed"]],
            "class": klass,
            "files": files[:20],
            "is_event": klass != CLASS_NO_RUNTIME,
        })
    deploys.sort(key=lambda d: (d["first_written_at"], d["old"], d["new"]))
    return deploys


# ── owner annotations ────────────────────────────────────────────────────────

def _annotation_error(path, message):
    return InputError(f"annotations ({os.path.basename(str(path))}): {message}")


def _nonblank(path, where, value, key):
    if not isinstance(value, str) or not value.strip():
        raise _annotation_error(path, f"{where} needs a non-empty text value for '{key}'")
    return value


def load_annotations(path) -> dict:
    """
    The owner's annotations file: `{"breaches": {id: {explanation, by, date}}, "events":
    [{time, what, by}]}` (both keys optional). Returns it normalised: breach entries as written
    (printed verbatim), events sorted by time with `time` as ISO UTC. Raises InputError (exit 2)
    for a missing, unreadable or malformed file, an unknown key or a bad date or time. An id that
    matches no breach is not an error here; the report warns about it.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError:
        raise _annotation_error(path, "cannot be read") from None
    except ValueError:
        raise _annotation_error(path, "not valid JSON") from None
    if not isinstance(data, dict):
        raise _annotation_error(path, "expected a JSON object with 'breaches' and/or 'events'")
    unknown = sorted(set(data) - {"breaches", "events"})
    if unknown:
        raise _annotation_error(path, f"unknown key {unknown[0]!r} (allowed: breaches, events)")

    breaches = data.get("breaches", {})
    if not isinstance(breaches, dict):
        raise _annotation_error(path, "'breaches' must be an object keyed by breach id")
    notes = {}
    for breach_id, entry in breaches.items():
        where = f"breaches[{breach_id!r}]"
        if not isinstance(entry, dict):
            raise _annotation_error(path, f"{where} must be an object with explanation, by and date")
        extra = sorted(set(entry) - {"explanation", "by", "date"})
        if extra:
            raise _annotation_error(path, f"{where} has an unknown key {extra[0]!r}")
        note = {key: _nonblank(path, where, entry.get(key), key) for key in ("explanation", "by", "date")}
        try:
            datetime.fromisoformat(note["date"].strip().replace("Z", "+00:00"))
        except ValueError:
            raise _annotation_error(path, f"{where} has a date that is not ISO 8601 (YYYY-MM-DD)") from None
        notes[breach_id] = note

    raw_events = data.get("events", [])
    if not isinstance(raw_events, list):
        raise _annotation_error(path, "'events' must be a list of {time, what, by}")
    events = []
    for number, entry in enumerate(raw_events):
        where = f"events[{number}]"
        if not isinstance(entry, dict):
            raise _annotation_error(path, f"{where} must be an object with time, what and by")
        extra = sorted(set(entry) - {"time", "what", "by"})
        if extra:
            raise _annotation_error(path, f"{where} has an unknown key {extra[0]!r}")
        text = {key: _nonblank(path, where, entry.get(key), key) for key in ("time", "what", "by")}
        try:
            when = _ts(text["time"])
        except ValueError:
            raise _annotation_error(path, f"{where} has a time that is not ISO 8601") from None
        events.append({"time": _iso(when), "what": text["what"], "by": text["by"]})
    events.sort(key=lambda e: e["time"])  # stable: events at the same instant keep the owner's order
    return {"breaches": notes, "events": events}


def evaluate_soak(inputs, since, until, max_age_min=DEFAULT_MAX_AGE_MIN, min_hours=SOAK_MIN_HOURS,
                  interval_min=PROBE_INTERVAL_MIN, annotations=None, git_runner=None, repo_root=REPO_ROOT) -> dict:
    """
    The soak result for [since, until) from loaded soak inputs (pure, no I/O, no wall clock).

    It is the dry-mode statistics plus `breaches` (id, kind, city, start, end, peak_age_min,
    probe_count, cause, context, explanation), `probe_coverage`, `trailing_age` and a `verdict`.
    `annotations` is the parsed annotations file (see load_annotations). A breach is explained
    when it has a rule-derived cause (attribute_causes) or an annotation; the window passes only
    when it is at least `min_hours`, probes are present and every breach and probe gap is
    explained. Deploys are derived from the rows (derive_deploys, `git_runner` and `repo_root`
    for the classification) and listed beside the owner's events; a deploy within two hours
    before a breach, up to its end, is that breach's `context` and never its explanation (D-08).
    """
    since, until = _ts(since), _ts(until)
    annotations = annotations or {}
    notes = annotations.get("breaches") or {}

    # the dry statistics, without the dry verdict: a breach is judged below, not by the dry rule
    result = evaluate_dry(inputs, since, until, max_age_min, min_hours=0)
    live = [w for w in inputs["writes"] if w["origin"] == "live" and w["first_written_at"] < until]
    window_rows = [w for w in live if w["first_written_at"] >= since]

    findings = probe_findings(inputs["probes"], since, until, interval_min)
    breaches = merge_breaches(write_breaches(live, since, until, max_age_min), findings)

    attribute_causes(breaches, inputs, since, until)
    for b in breaches:
        note = notes.get(b["id"])
        if note is not None:
            b["explanation"] = {"explanation": note["explanation"], "by": note["by"], "date": note["date"]}
    known = {b["id"] for b in breaches}

    deploys = derive_deploys(live, since, until, git_runner, repo_root)
    events = sorted(annotations.get("events") or [], key=lambda e: _ts(e["time"]))
    for b in breaches:
        b["context"] = [
            {"old": d["old"], "new": d["new"], "class": d["class"], "first_written_at": d["first_written_at"]}
            for d in deploys
            if d["is_event"] and b["start"] - CONTEXT_WINDOW <= _ts(d["first_written_at"]) <= b["end"]
        ]

    window = until - since
    hours = int(window // _ONE_HOUR)
    failures = []
    if window < timedelta(hours=min_hours):
        failures.append(f"window shorter than {min_hours:g} h ({hours} h between the start and the end)")
    if not window_rows:
        failures.append("no live rows in the window")
    if findings["found"] == 0:
        failures.append("no probes in the window: the probe log recorded nothing")
    unexplained = [b for b in breaches if not (b["cause"] or b["explanation"])]
    failures += [_breach_summary(b) for b in unexplained]

    warnings = list(result["warnings"])
    for item in findings["incomplete"]:
        warnings.append(f"incomplete probe at {_iso(item['probed_at'])}: {item['rows']} rows, "
                        f"no row for {', '.join(item['missing'])}")
    for d in deploys:
        if d["class"].startswith("unknown"):
            warnings.append(f"deploy {d['old'] or '-'} to {d['new'] or '-'} first written {d['first_written_at']} "
                            f"is flagged, not classified: {d['class']}")
    for note_id in sorted(set(notes) - known):
        warnings.append(f"annotation for unknown breach id {note_id}: it matches no breach in this window")

    verdict = "fail" if failures else "pass"
    if verdict == "pass":
        explained = len(breaches)
        status = (f"every breach ({explained}) has a stated cause or an owner annotation" if explained
                  else "no breach at all")
        lines = [
            f"PASS: over {hours} h each city's current rating was never more than {max_age_min:g} min old "
            f"unless explained ({status}); {findings['found']} of {findings['expected']} expected probes were "
            f"logged with no gap longer than {2 * interval_min + 1:g} min."
        ]
    else:
        lines = ["FAIL: " + failure for failure in failures]

    result.update({
        "mode": "soak",
        "advances": result["events"],  # the dry statistics' list of advancing writes; `events` is the owner's
        "hours": hours,
        "min_hours": min_hours,
        "probe_interval_min": interval_min,
        "breaches": [_breach_json(b) for b in breaches],
        "probe_coverage": {
            "interval_min": interval_min,
            "expected": findings["expected"],
            "found": findings["found"],
            "gap_limit_min": 2 * interval_min + 1,
            "gaps": [{"start": _iso(g["start"]), "end": _iso(g["end"]), "duration_min": _minutes(g["end"] - g["start"])}
                     for g in findings["gaps"]],
            "incomplete": [{"probed_at": _iso(i["probed_at"]), "rows": i["rows"], "missing": i["missing"]}
                           for i in findings["incomplete"]],
        },
        "trailing_age": {c["city"]: c["trailing_age_min"] for c in result["cities"]},
        "deploys": deploys,
        "events": events,
        "warnings": warnings,
        "failures": failures,
        "verdict": verdict,
        "lines": lines,
    })
    return result


def _fmt(value) -> str:
    return "-" if value is None else f"{value:.1f}"


def render_markdown(result) -> str:
    if result.get("mode") == "soak":
        return _render_soak(result)
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

    out += _stat_sections(result)
    return "\n".join(out) + "\n"


def _stat_sections(result) -> list:
    """The write lag, peak age, fallback, late fill, slot verdict and largest-peak sections (both modes)."""
    limit = f"{result['max_age_min']:g}"
    out = []
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

    advances = result["advances"] if result.get("mode") == "soak" else result["events"]
    slowest = sorted((e for e in advances if e["peak_age_min"] is not None),
                     key=lambda e: -e["peak_age_min"])[:10]
    out += ["", "## Ten largest peak ages", "",
            "| city | valid_time | first written | peak age | write lag |", "|---|---|---|---|---|"]
    for e in slowest:
        out.append(f"| {e['city']} | {e['valid_time']} | {e['first_written_at']} | "
                   f"{e['peak_age_min']:.1f} | {e['write_lag_min']:.1f} |")
    return out


def _cell_text(text) -> str:
    """One markdown table cell: no pipes, no line breaks."""
    return str(text).replace("|", "/").replace("\r", " ").replace("\n", " ")


def _explanation_cell(b) -> str:
    if b["cause"]:
        return "cause: " + _cell_text(b["cause"])
    if b["explanation"]:
        note = b["explanation"]
        return f"owner annotation by {_cell_text(note['by'])} on {_cell_text(note['date'])} (verbatim below)"
    return "no cause or annotation"


def _render_soak(result) -> str:
    limit = f"{result['max_age_min']:g}"
    out = [
        "# Soak report (E2E-02)",
        "",
        f"Window: {result['since']} to {result['until']} ({result['hours']} h; at least "
        f"{result['min_hours']:g} h required). A breach is a current rating strictly older than {limit} min "
        f"(OD-4: exactly {limit} min is fresh), or a gap in the probe log longer than "
        f"{result['probe_coverage']['gap_limit_min']:g} min.",
        "",
    ]
    out += [f"**{line}**" if i == 0 else line for i, line in enumerate(result["lines"])]
    for warning in result["warnings"]:
        out += ["", f"WARNING: {warning}"]

    breaches = result["breaches"]
    out += ["", "## Breaches", ""]
    if breaches:
        out += ["| id | city | from | to | peak age (min) | probes | cause or annotation | deploy context |",
                "|---|---|---|---|---|---|---|---|"]
        for b in breaches:
            context = "; ".join(f"{c['old']} to {c['new']} ({c['class']}) first written {c['first_written_at']}"
                                for c in b["context"]) or "-"
            out.append(f"| {b['id']} | {b['city']} | {b['start']} | {b['end']} | {_fmt(b['peak_age_min'])} | "
                       f"{b['probe_count']} | {_explanation_cell(b)} | {_cell_text(context)} |")
    else:
        out.append("No breaches.")

    noted = [b for b in breaches if b["explanation"]]
    if noted:
        out += ["", "## Owner annotations (verbatim)", ""]
        for b in noted:
            note = b["explanation"]
            text = note["explanation"].replace("\n", "\n  ")
            out.append(f"- {b['id']} (by {note['by']}, {note['date']}): {text}")

    out += ["", "## Deploys and events during the window", "",
            "Deploys are derived from the rows (a change of pipeline_version, config_fingerprint, model hashes, "
            "forecast_method or config_version from a city's previous row). A deploy is context for a breach; "
            "it never excuses one (D-08). Events are the owner's own entries.", ""]
    listed = [(d["first_written_at"], "deploy",
               f"{d['old'] or '-'} to {d['new'] or '-'}: {d['class']}; changed {', '.join(d['changed'])}; "
               f"cities {', '.join(d['cities'])}") for d in result["deploys"] if d["is_event"]]
    listed += [(e["time"], "event", f"{e['what']} (by {e['by']})") for e in result["events"]]
    listed.sort(key=lambda row: row[0])  # stable: a deploy and an event at one instant keep derived-first order
    if listed:
        out += ["| time (UTC) | kind | detail |", "|---|---|---|"]
        out += [f"| {when} | {kind} | {_cell_text(detail)} |" for when, kind, detail in listed]
    else:
        out.append("No deploys and no owner events in the window.")
    quiet = [d for d in result["deploys"] if not d["is_event"]]
    if quiet:
        out += ["", "Commits with no runtime change (listed, not deploys):", ""]
        out += [f"- {d['old']} to {d['new']} first written {d['first_written_at']}" for d in quiet]

    cov = result["probe_coverage"]
    out += ["", "## Probe coverage", "",
            f"{cov['found']} of {cov['expected']} expected probes (one every {cov['interval_min']:g} min) "
            f"were logged; a gap longer than {cov['gap_limit_min']:g} min fails the soak unless annotated."]
    out += ["", "Gaps:", ""]
    if cov["gaps"]:
        out += ["| from | to | minutes |", "|---|---|---|"]
        out += [f"| {g['start']} | {g['end']} | {g['duration_min']:.1f} |" for g in cov["gaps"]]
    else:
        out.append("No probe gaps.")
    out += ["", "Incomplete probes (a city missing from the probe; listed, not a failure):", ""]
    if cov["incomplete"]:
        out += ["| probed at | rows | missing |", "|---|---|---|"]
        out += [f"| {i['probed_at']} | {i['rows']} | {', '.join(i['missing'])} |" for i in cov["incomplete"]]
    else:
        out.append("No incomplete probes.")
    out += ["", "Age of the newest rating at the end of the window (minutes):", "",
            "| city | age |", "|---|---|"]
    out += [f"| {city} | {_fmt(age)} |" for city, age in result["trailing_age"].items()]

    out += _stat_sections(result)
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
    parser = argparse.ArgumentParser(description="Dry-soak and 72 h soak export (read-only) and report (offline).")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="owner-run, read-only: copy the live window into files")
    export.add_argument("--mode", choices=["dry", "soak"], required=True,
                        help="soak also exports the probe log (probes.csv)")
    export.add_argument("--since", required=True, type=_time_arg, help="window start, ISO UTC")
    export.add_argument("--until", required=True, type=_time_arg, help="window end, ISO UTC")
    export.add_argument("--out-dir", required=True, help="directory for the export files")

    rep = sub.add_parser("report", help="offline: compute the dry soak or the 72 h soak from the export files")
    rep.add_argument("--mode", choices=["dry", "soak"], required=True)
    rep.add_argument("--in-dir", required=True, help="directory written by export")
    rep.add_argument("--min-hours", type=float, default=None,
                     help=f"shortest window that can pass (default {DRY_MIN_HOURS} dry, {SOAK_MIN_HOURS} soak)")
    rep.add_argument("--max-age-min", type=float, default=DEFAULT_MAX_AGE_MIN)
    rep.add_argument("--probe-interval-min", type=float, default=PROBE_INTERVAL_MIN,
                     help="soak: minutes between probes (the pg_cron schedule)")
    rep.add_argument("--annotations", default=None, help="soak: owner annotations.json")
    rep.add_argument("--out", required=True, help="markdown report path")
    rep.add_argument("--json-out", help="also write the full result as JSON")
    return parser


def main(argv=None, connect_fn=None, fetch_runs_fn=None, git_runner=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "export":
        import supabase_store

        if args.until <= args.since:
            parser.error("--until must be after --since")
        try:
            meta = export_window(args.since, args.until, args.out_dir, args.mode,
                                 connect_fn=connect_fn, fetch_runs_fn=fetch_runs_fn)
        except supabase_store.StoreError as exc:
            print(f"export failed: {supabase_store.redact(str(exc))}", file=sys.stderr)
            return 1
        extra = f" and {meta['rows']['probes']} probe rows" if args.mode == "soak" else ""
        print(f"exported {meta['rows']['writes']} live rows, {meta['rows']['runs']} pipeline runs{extra} "
              f"to {args.out_dir}")
        return 0

    soak_mode = args.mode == "soak"
    min_hours = args.min_hours if args.min_hours is not None else (SOAK_MIN_HOURS if soak_mode else DRY_MIN_HOURS)
    try:
        inputs = load_inputs(args.in_dir, args.mode)
        since, until = _ts(inputs["meta"]["since"]), _ts(inputs["meta"]["until"])
        annotations = load_annotations(args.annotations) if soak_mode and args.annotations else None
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if soak_mode:
        result = evaluate_soak(inputs, since, until, args.max_age_min, min_hours, args.probe_interval_min,
                               annotations, git_runner)
    else:
        result = evaluate_dry(inputs, since, until, args.max_age_min, min_hours)
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
