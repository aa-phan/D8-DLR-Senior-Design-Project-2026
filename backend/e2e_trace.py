"""
End-to-end trace: cron-job.org execution -> Actions run -> database rows -> REST response
(production-pipeline Phase 6: E2E-01, ROADMAP success criterion 3)
=======================================================================================
In plain English: one scheduled trigger produced one run, the run wrote one row per city, and
the public interface returns exactly those values. This command proves or refutes each link of
that chain for all four cities and writes the result as a four-way table.

The chain, and what each link means:

    cron-job.org execution   the hourly job fired and GitHub answered with a 2xx (204). The owner
                             reads the execution's actual UTC time and HTTP status from the job
                             history in the cron-job.org console and passes them in; the job
                             itself is never changed (COVERAGE.md opt-outs).
    Actions run              exactly ONE `workflow_dispatch` run of dlr_live.yml was created from
                             60 s before to 300 s after that execution (both ends inclusive), and
                             `gh run view` shows it concluded `success` in the workflow
                             "DLR Live Ratings". Zero or several candidates fail loudly: the time
                             correlation is the only link between the console and GitHub.
    SQL rows                 `city_rating` holds one row per city for that run id, and
                             `pipeline_run.cities_ok` lists all four cities. Read through Phase 4's
                             connection, in a session set read-only before the first statement,
                             with bound parameters.
    REST rows                `city_rating?run_id=eq.<id>` answered through the publishable key
                             returns the same four rows. The trace reads by run id, not from
                             `latest_rating` alone, so an hourly run landing during the trace
                             cannot cause a false mismatch.
    match                    the 31 stored columns of latest_rating_contract.STORED_COLUMNS are
                             equal per city: floats exactly, timestamps as aware UTC instants
                             (`...Z` and `...+00:00` are the same instant), arrays element by
                             element, null only against null. `age_minutes` and `is_stale` change
                             with the clock and are never compared (D-01, D-02).
    current or superseded    `latest_rating` is read for the four cities: the word rule behind
                             `is_provisional` is checked against the labels (D-03), and the column
                             says whether the run's row is still the newest ("current") or a later
                             hourly slot has replaced it ("superseded by a later slot", only
                             informational). Rows a later run overwrote in the SAME slot (OD-7
                             rewrites run_id) are reported "superseded by run <id>" and fail: they
                             are never a match.

Usage (from the owner's main checkout; needs SUPABASE_DB_URL, SUPABASE_URL,
SUPABASE_PUBLISHABLE_KEY and an authenticated `gh`; a `.env` is loaded when run as a script):

    python backend/e2e_trace.py --execution-time 2026-10-19T14:05:02Z --execution-status 204 \\
        [--run-id 123456789] [--out trace.md] [--json-out trace.json]

`--execution-time` needs an explicit UTC offset (`Z` or `+00:00`): a time without one could be
the owner's local time. `--run-id` is optional; when given it must agree with the correlated run.

Exit codes: 0 traced and every link matched, 1 a link failed (each is printed as PASS or FAIL with
its reason), 2 usage or configuration (a missing variable, a bad argument).

The trace only reads, so it can be re-run any number of times. It never prints or stores the
database URL, the project URL or a key (D-10): every printed line and every file passes through
`supabase_rest.redact_rest` and `supabase_store.redact`, and the evidence holds run ids, times and
values only. The result depends only on its inputs, so the same inputs give identical files.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import namedtuple
from datetime import datetime, timedelta, timezone

import config
import dlr_live_window_check
import latest_rating_contract
import supabase_rest
import supabase_store

WORKFLOW_FILE = "dlr_live.yml"
WORKFLOW_NAME = "DLR Live Ratings"
WINDOW_BEFORE_S = 60
WINDOW_AFTER_S = 300
GH_VIEW_FIELDS = "databaseId,event,status,conclusion,createdAt,startedAt,updatedAt,headSha,workflowName"
GH_TIMEOUT_S = 120
REPO_ROOT = dlr_live_window_check.REPO_ROOT

READ_ONLY_SQL = "set default_transaction_read_only = on"
CITY_RATING_SQL = (
    "select " + ", ".join(latest_rating_contract.STORED_COLUMNS) + " "
    "from public.city_rating "
    "where run_id = %(run_id)s "
    "order by city"
)
PIPELINE_RUN_SQL = (
    "select run_id, cities_ok, cities_failed, window_end, finished_at "
    "from public.pipeline_run "
    "where run_id = %(run_id)s"
)
SLOT_SQL = (
    "select city, run_id "
    "from public.city_rating "
    "where valid_time = %(valid_time)s "
    "order by city"
)
LATEST_SELECT = "city,valid_time,run_id,rating_basis,config_version,is_provisional"

# the stored columns that are instants; everything else compares as the value it is
TIMESTAMP_COLUMNS = frozenset({"valid_time", "observation_time", "computed_at"})
_MISSING = object()
_RUN_ID_RE = re.compile(r"^[0-9]{1,20}$")
_OFFSET_RE = re.compile(r"(Z|[+-]\d{2}(?::?\d{2})?)$")

Mismatch = namedtuple("Mismatch", ["city", "column", "sql", "rest", "reason"])


class TraceError(RuntimeError):
    """A link could not be read. The message is already redacted."""


# ──────────────────────────────────────────────────────────────────────────────
# Time and value helpers
# ──────────────────────────────────────────────────────────────────────────────

def _aware(value):
    """An aware UTC datetime from a datetime or a PostgREST/ISO string; ValueError on anything else."""
    if isinstance(value, datetime):
        stamp = value
    else:
        stamp = supabase_rest.parse_ts(value)
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _iso(dt) -> str:
    dt = _aware(dt)
    if dt.microsecond:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _canon(column, value):
    """The comparable form of one stored value: instants as aware UTC, arrays element-wise."""
    if value is _MISSING or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_canon(column, item) for item in value]
    if column in TIMESTAMP_COLUMNS:
        try:
            return _aware(value)
        except (ValueError, TypeError):
            return value  # unparseable: stays a string, so it can never equal an instant
    return value


def _equal(a, b) -> bool:
    """Exact equality: null only with null, a boolean only with a boolean, arrays element by element."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, list) or isinstance(b, list):
        return (isinstance(a, list) and isinstance(b, list) and len(a) == len(b)
                and all(_equal(x, y) for x, y in zip(a, b)))
    return a == b


def _shown(value):
    """A JSON-safe, deterministic form of a compared value."""
    if value is _MISSING:
        return "<missing>"
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, (list, tuple)):
        return [_shown(item) for item in value]
    return value


def compare_rows(sql, rest) -> list:
    """
    Per-city differences between the SQL rows and the REST rows (lists of row dicts), as
    `Mismatch(city, column, sql, rest, reason)` in config.LOCATIONS order, then column order. Rows are
    matched by city, so the order of either list does not matter. A city with no row on a side, or with
    two rows on one, is a mismatch with a named reason; empty against empty is four such mismatches, so
    nothing ever matches by being absent. The 31 stored columns are compared: floats by exact equality,
    timestamps as aware UTC instants, arrays element by element, null only with null.
    """
    sql_by, rest_by, duplicated = {}, {}, set()
    for side, rows in (("SQL", sql), ("REST", rest)):
        target = sql_by if side == "SQL" else rest_by
        for row in rows or []:
            city = row.get("city")
            if city in target:
                duplicated.add((side, city))
            target[city] = row
    extra = sorted((c for c in set(sql_by) | set(rest_by) if c not in config.LOCATIONS), key=str)
    found = []
    for city in list(config.LOCATIONS) + extra:
        for side in ("SQL", "REST"):
            if (side, city) in duplicated:
                found.append(Mismatch(city, None, None, None, "more than one %s row for the run" % side))
        s, r = sql_by.get(city), rest_by.get(city)
        if s is None and r is None:
            found.append(Mismatch(city, None, None, None, "no SQL row and no REST row"))
        elif s is None:
            found.append(Mismatch(city, None, None, None, "no SQL row"))
        elif r is None:
            found.append(Mismatch(city, None, None, None, "no REST row"))
        else:
            for column in latest_rating_contract.STORED_COLUMNS:
                a = _canon(column, s.get(column, _MISSING))
                b = _canon(column, r.get(column, _MISSING))
                if a is _MISSING or b is _MISSING:
                    side = "SQL" if a is _MISSING else "REST"
                    found.append(Mismatch(city, column, _shown(a), _shown(b), "column missing from the %s row" % side))
                elif not _equal(a, b):
                    found.append(Mismatch(city, column, _shown(a), _shown(b), "values differ"))
    return found


# ──────────────────────────────────────────────────────────────────────────────
# Link 1-2: the Actions run
# ──────────────────────────────────────────────────────────────────────────────

def find_run(execution_time, runs):
    """
    `(run, None)` when exactly one workflow_dispatch run was created in
    [execution - WINDOW_BEFORE_S, execution + WINDOW_AFTER_S] (both ends inclusive); otherwise
    `(None, reason)` for zero or several candidates. `runs` are `gh run list --json` dicts.
    """
    execution_time = _aware(execution_time)
    low = execution_time - timedelta(seconds=WINDOW_BEFORE_S)
    high = execution_time + timedelta(seconds=WINDOW_AFTER_S)
    window = "%s to %s" % (_iso(low), _iso(high))
    candidates = []
    for run in runs or []:
        if run.get("event") != "workflow_dispatch" or not run.get("createdAt"):
            continue
        try:
            created = _aware(run["createdAt"])
        except ValueError:
            continue
        if low <= created <= high:
            candidates.append(run)
    if not candidates:
        return None, "no workflow_dispatch run of %s was created from %s" % (WORKFLOW_FILE, window)
    if len(candidates) > 1:
        ids = ", ".join(sorted(str(c.get("databaseId")) for c in candidates))
        return None, ("%d workflow_dispatch runs of %s were created from %s (%s); "
                      "the correlation needs exactly one" % (len(candidates), WORKFLOW_FILE, window, ids))
    return candidates[0], None


def view_run(run_id, run_cmd=subprocess.run) -> dict:
    """`gh run view <id> --json GH_VIEW_FIELDS` (an argv list, no shell) as a dict. TraceError on a failure."""
    argv = ["gh", "run", "view", str(run_id), "--json", GH_VIEW_FIELDS]
    done = run_cmd(argv, capture_output=True, text=True, timeout=GH_TIMEOUT_S, cwd=REPO_ROOT)
    if done.returncode != 0:
        raise TraceError("gh run view failed (exit %s): %s" % (done.returncode, (done.stderr or "").strip()[:300]))
    try:
        data = json.loads(done.stdout or "{}")
    except ValueError:
        raise TraceError("gh run view did not answer with JSON") from None
    if not isinstance(data, dict):
        raise TraceError("gh run view did not answer with an object")
    return data


# ──────────────────────────────────────────────────────────────────────────────
# Link 3: SQL rows (owner connection, read-only)
# ──────────────────────────────────────────────────────────────────────────────

def _query(conn, sql, params) -> list:
    cursor = conn.execute(sql, params)
    names = [d.name for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _slot_of(rows, pipeline_row):
    """The run's hourly slot: the valid_time of any of its rows, else its window_end cut to the hour (OD-7)."""
    for row in rows:
        if row.get("valid_time") is not None:
            return _aware(row["valid_time"])
    if pipeline_row and pipeline_row.get("window_end") is not None:
        return _aware(pipeline_row["window_end"]).replace(minute=0, second=0, microsecond=0)
    return None


def sql_rows(run_id, connect_fn=None) -> dict:
    """
    `{"rows": [...], "pipeline_run": dict or None, "slot": datetime or None, "slot_holders": {city: run_id}}`:
    the run's city_rating rows (the stored columns, ordered by city), its pipeline_run row and, only when
    fewer than four cities came back, who holds the run's hourly slot now (a later run in the same slot
    rewrites run_id, OD-7), which names the run that overwrote the missing rows. The session is set
    read-only before the first statement and every SELECT binds its parameters (`run_id`, `valid_time`);
    no value is formatted into SQL text. `connect_fn`
    defaults to Phase 4's `supabase_store.connect`. Any failure other than a StoreError is re-raised as
    a StoreError carrying the exception type and redacted text, with no exception chained.
    """
    if connect_fn is None:
        connect_fn = supabase_store.connect
    params = {"run_id": str(run_id)}
    conn = None
    failure = None
    out = None
    try:
        conn = connect_fn()
        conn.execute(READ_ONLY_SQL)  # before the first query: this session can no longer write
        rows = _query(conn, CITY_RATING_SQL, params)
        pipeline = _query(conn, PIPELINE_RUN_SQL, params)
        pipeline_row = pipeline[0] if pipeline else None
        slot, holders = None, {}
        if len({r.get("city") for r in rows}) < len(config.LOCATIONS):
            slot = _slot_of(rows, pipeline_row)
            if slot is not None:
                holders = {r["city"]: str(r["run_id"]) for r in _query(conn, SLOT_SQL, {"valid_time": slot})}
        out = {"rows": rows, "pipeline_run": pipeline_row, "slot": slot, "slot_holders": holders}
    except supabase_store.StoreError:
        raise
    except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted StoreError
        failure = "%s: %s" % (type(exc).__name__, supabase_store.redact(str(exc)))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    if failure is not None:
        raise supabase_store.StoreError("could not read the run's rows: %s" % failure)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Link 4: REST rows (publishable key)
# ──────────────────────────────────────────────────────────────────────────────

def rest_rows(run_id, cfg, opener=None) -> dict:
    """
    `{"rows": [...], "latest": [...]}`: the run's city_rating rows through REST (the stored columns,
    `run_id=eq.<id>`, ordered by city) and the current latest_rating rows (city, valid_time, run_id,
    the two labels and is_provisional) for the current-or-superseded column. GET only.
    """
    columns = ",".join(latest_rating_contract.STORED_COLUMNS)
    rows = supabase_rest.get_all(
        cfg, "city_rating", [("select", columns), ("run_id", "eq.%s" % run_id)], "city.asc", opener=opener)
    latest = supabase_rest.get_all(cfg, "latest_rating", [("select", LATEST_SELECT)], "city.asc", opener=opener)
    return {"rows": rows, "latest": latest}


# ──────────────────────────────────────────────────────────────────────────────
# The trace
# ──────────────────────────────────────────────────────────────────────────────

def _currency(run_id, row, latest_row) -> str:
    """Whether the run's row is still what latest_rating shows for its city."""
    if row is None:
        return "no row"
    if latest_row is None:
        return "not in latest_rating"
    try:
        mine, theirs = _aware(row["valid_time"]), _aware(latest_row["valid_time"])
    except (ValueError, KeyError, TypeError):
        return "unknown"
    if theirs == mine:
        holder = str(latest_row.get("run_id"))
        return "current" if holder == str(run_id) else "superseded by run %s" % holder
    if theirs > mine:
        return "superseded by a later slot"
    return "latest_rating shows an older slot"


def _gone(run_id, holder) -> str:
    """The currency of a city whose row for this run is missing: who holds its slot now, if anyone."""
    if holder and str(holder) != str(run_id):
        return "superseded by run %s" % holder
    return "no row"


def _summary(row):
    return {c: _shown(_canon(c, row.get(c))) for c in latest_rating_contract.STORED_COLUMNS}


def _failure_text(exc, cfg) -> str:
    text = "%s: %s" % (type(exc).__name__, exc)
    return supabase_store.redact(supabase_rest.redact_rest(text, cfg, limit=None), limit=300)


def trace(execution_time, execution_status, cfg, run_id=None, fetch_runs_fn=None, run_cmd=None,
          connect_fn=None, opener=None) -> dict:
    """
    Walk the chain once and return the evidence: `{"ok", "execution", "run", "links", "pipeline_run",
    "cities"}`. Every link is `{"name", "ok", "detail"}`; `cities` always lists config.LOCATIONS in
    order with the SQL row, the REST row, `match`, `currency` and the `mismatches`. Reads only.
    """
    execution_time = _aware(execution_time)
    if fetch_runs_fn is None:
        fetch_runs_fn = dlr_live_window_check.fetch_runs
    if run_cmd is None:
        run_cmd = subprocess.run
    links = []

    def add(name, ok, detail):
        links.append({"name": name, "ok": bool(ok), "detail": detail})

    result = {
        "ok": False,
        "execution": {"time": _iso(execution_time), "status": int(execution_status)},
        "run": None,
        "links": links,
        "pipeline_run": None,
        "cities": [],
    }

    def finish(sql=None, rest=None, mismatches=(), latest=(), holders=None):
        holders = holders or {}
        latest_by = {r.get("city"): r for r in latest}
        sql_by = {r.get("city"): r for r in (sql or [])}
        rest_by = {r.get("city"): r for r in (rest or [])}
        by_city = {}
        for item in mismatches:
            by_city.setdefault(item.city, []).append(item)
        compared = sql is not None and rest is not None
        for city in config.LOCATIONS:
            s, r = sql_by.get(city), rest_by.get(city)
            mine = by_city.get(city, [])
            result["cities"].append({
                "city": city,
                "sql": _summary(s) if s is not None else None,
                "rest": _summary(r) if r is not None else None,
                "match": bool(compared and s is not None and r is not None and not mine),
                "currency": _currency(run_id_used, s or r, latest_by.get(city)) if (s or r) else _gone(
                    run_id_used, holders.get(city)),
                "mismatches": [
                    {"column": m.column, "sql": m.sql, "rest": m.rest, "reason": m.reason} for m in mine],
            })
        result["ok"] = all(item["ok"] for item in links) and all(c["match"] for c in result["cities"])
        return result

    run_id_used = None
    ok_status = 200 <= int(execution_status) < 300
    add("cron-job.org execution", ok_status,
        "%s answered HTTP %s" % (_iso(execution_time), execution_status) if ok_status else
        "%s answered HTTP %s, expected a 2xx" % (_iso(execution_time), execution_status))
    start = execution_time.replace(minute=0, second=0, microsecond=0)
    try:
        runs = fetch_runs_fn(start, 1)
    except Exception as exc:  # noqa: BLE001 - a link that could not be read
        add("Actions run", False, "could not list the runs: %s" % _failure_text(exc, cfg))
        return finish()
    run, reason = find_run(execution_time, runs)
    if run is None:
        add("Actions run", False, reason)
        return finish()
    run_id_used = str(run["databaseId"])
    if run_id is not None and str(run_id) != run_id_used:
        add("Actions run", False, "the explicit --run-id %s disagrees with the run %s that the execution time "
            "correlates to; nothing was traced for either" % (run_id, run_id_used))
        return finish()
    add("Actions run", True, "run %s created %s" % (run_id_used, _iso(run["createdAt"])))
    result["run"] = {"id": run_id_used, "event": run.get("event"), "conclusion": run.get("conclusion"),
                     "created_at": _iso(run["createdAt"])}
    _check_view(add, result, run_id_used, run_cmd, cfg)

    sql = rest = latest = None
    try:
        sql = sql_rows(run_id_used, connect_fn)
    except supabase_store.StoreError as exc:
        add("SQL rows", False, _failure_text(exc, cfg))
    else:
        _check_sql(add, result, run_id_used, sql)
    try:
        rest = rest_rows(run_id_used, cfg, opener)
    except supabase_rest.RestError as exc:
        add("REST rows", False, _failure_text(exc, cfg))
    else:
        _check_rest(add, run_id_used, rest)
        latest = rest["latest"]

    mismatches = []
    if sql is not None and rest is not None:
        mismatches = compare_rows(sql["rows"], rest["rows"])
        if mismatches:
            shown = "; ".join(
                "%s %s: %s" % (m.city, m.column, m.reason) if m.column is None else
                "%s %s: SQL %r, REST %r" % (m.city, m.column, m.sql, m.rest)
                for m in mismatches[:12])
            add("SQL equals REST", False, "%d differences: %s" % (len(mismatches), shown))
        else:
            add("SQL equals REST", True, "%d columns for each of %d cities are equal"
                % (len(latest_rating_contract.STORED_COLUMNS), len(config.LOCATIONS)))

    if rest is not None:
        _check_latest(add, run_id_used, sql, rest)
    return finish(sql["rows"] if sql else None, rest["rows"] if rest else None, mismatches, latest or (),
                  sql["slot_holders"] if sql else None)


def _check_view(add, result, run_id, run_cmd, cfg):
    """`gh run view`: the run is the one asked for, a workflow_dispatch, concluded success, in the live workflow."""
    try:
        view = view_run(run_id, run_cmd)
    except Exception as exc:  # noqa: BLE001 - a link that could not be read
        add("Actions run result", False, "could not read the run: %s" % _failure_text(exc, cfg))
        return
    problems = []
    if str(view.get("databaseId")) != str(run_id):
        problems.append("databaseId is %r, expected %s" % (view.get("databaseId"), run_id))
    if view.get("event") != "workflow_dispatch":
        problems.append("event is %r, expected 'workflow_dispatch'" % (view.get("event"),))
    if view.get("conclusion") != "success":
        problems.append("conclusion is %r, expected 'success'" % (view.get("conclusion"),))
    if view.get("workflowName") != WORKFLOW_NAME:
        problems.append("workflowName is %r, expected %r" % (view.get("workflowName"), WORKFLOW_NAME))
    result["run"].update({
        "event": view.get("event"), "conclusion": view.get("conclusion"), "status": view.get("status"),
        "workflow": view.get("workflowName"), "head_sha": view.get("headSha"),
    })
    add("Actions run result", not problems,
        "; ".join(problems) if problems else "concluded success in workflow %r as a workflow_dispatch" % WORKFLOW_NAME)


def _check_sql(add, result, run_id, sql):
    """One SQL row per city (naming who overwrote any missing one) and a pipeline_run row listing every city."""
    counts = {}
    for row in sql["rows"]:
        counts[row.get("city")] = counts.get(row.get("city"), 0) + 1
    problems = []
    for city in config.LOCATIONS:
        if counts.get(city, 0) == 0:
            holder = sql["slot_holders"].get(city)
            if holder and holder != str(run_id):
                problems.append("%s superseded by run %s" % (city, holder))
            else:
                problems.append("%s has no row for run %s" % (city, run_id))
        elif counts[city] > 1:
            problems.append("%s has %d rows for run %s" % (city, counts[city], run_id))
    add("SQL rows", not problems,
        "; ".join(problems) if problems else "%d rows for run %s, one per city" % (len(sql["rows"]), run_id))

    pipeline = sql["pipeline_run"]
    if pipeline is None:
        add("pipeline_run", False, "no pipeline_run row for run %s" % run_id)
        return
    listed = list(pipeline.get("cities_ok") or [])
    lacking = [c for c in config.LOCATIONS if c not in listed]
    result["pipeline_run"] = {
        "cities_ok": listed,
        "window_end": _iso(pipeline["window_end"]) if pipeline.get("window_end") else None,
    }
    add("pipeline_run", not lacking,
        "cities_ok lacks %s" % ", ".join(lacking) if lacking else "cities_ok lists all %d cities" % len(config.LOCATIONS))


def _check_rest(add, run_id, rest):
    """The REST service returns one row per city for the run id."""
    present = {row.get("city") for row in rest["rows"]}
    if not rest["rows"]:
        add("REST rows", False, "no REST rows for run %s" % run_id)
        return
    lacking = [c for c in config.LOCATIONS if c not in present]
    add("REST rows", not lacking,
        "no REST row for %s (run %s)" % (", ".join(lacking), run_id) if lacking
        else "%d rows for run %s" % (len(rest["rows"]), run_id))


def _check_latest(add, run_id, sql, rest):
    """The word rule behind is_provisional against the labels, and whether latest_rating shows the run."""
    run_rows = {r.get("city"): r for r in (sql["rows"] if sql else rest["rows"])}
    latest_by = {r.get("city"): r for r in rest["latest"]}
    bad = []
    for city in config.LOCATIONS:
        latest_row = latest_by.get(city)
        if latest_row is None:
            bad.append("%s has no latest_rating row" % city)
            continue
        row = run_rows.get(city)
        current = row is not None and _currency(run_id, row, latest_row) == "current"
        basis = row if current else latest_row  # the labels of the row the view is showing
        expected = latest_rating_contract.is_provisional(basis.get("rating_basis"), basis.get("config_version"))
        if latest_row.get("is_provisional") is not expected:
            bad.append("%s says is_provisional %r, its labels say %r"
                       % (city, latest_row.get("is_provisional"), expected))
    add("is_provisional", not bad,
        "; ".join(bad) if bad else "equals the word rule on rating_basis and config_version for all %d cities"
        % len(config.LOCATIONS))


# ──────────────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────────────

def _cell(text) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def _row_text(summary):
    if summary is None:
        return "missing"
    return "%s %s A" % (summary["valid_time"], summary["rating_amps"])


def render_table(result) -> str:
    """The four-way table (execution, Actions run, SQL row, REST row, match, current or superseded)."""
    execution = "%s HTTP %s" % (result["execution"]["time"], result["execution"]["status"])
    run = result["run"]
    run_text = "%s %s" % (run["id"], run["conclusion"]) if run else "none"
    lines = ["| city | cron-job.org execution | Actions run | SQL row | REST row | match | current or superseded |",
             "|---|---|---|---|---|---|---|"]
    for entry in result["cities"]:
        lines.append("| %s |" % " | ".join(_cell(x) for x in (
            entry["city"], execution, run_text, _row_text(entry["sql"]), _row_text(entry["rest"]),
            "yes" if entry["match"] else "NO", entry["currency"])))
    lines.append("")
    for item in result["links"]:
        lines.append("%s %s: %s" % ("PASS" if item["ok"] else "FAIL", item["name"], item["detail"]))
    lines.append("")
    failed = [item["name"] for item in result["links"] if not item["ok"]]
    if result["ok"]:
        lines.append("E2E TRACE OK")
    else:
        lines.append("E2E TRACE FAILED: " + (", ".join(failed) if failed else "a city did not match"))
    return "\n".join(lines)


def _clean(text, cfg) -> str:
    return supabase_store.redact(supabase_rest.redact_rest(text, cfg, limit=None), limit=None)


def _write(path, text, cfg) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(_clean(text, cfg))
        if not text.endswith("\n"):
            fh.write("\n")


# ──────────────────────────────────────────────────────────────────────────────
# Command line
# ──────────────────────────────────────────────────────────────────────────────

def _execution_time_arg(value):
    text = str(value).strip()
    if not _OFFSET_RE.search(text):
        raise argparse.ArgumentTypeError(
            "needs an explicit UTC offset (Z or +00:00), so a local time is never read as UTC: %r" % value)
    try:
        return _aware(text)
    except ValueError:
        raise argparse.ArgumentTypeError("not an ISO-8601 timestamp: %r" % value) from None


def _run_id_arg(value):
    if not _RUN_ID_RE.match(str(value).strip()):
        raise argparse.ArgumentTypeError("a run id is digits only: %r" % value)
    return str(value).strip()


def main(argv=None, fetch_runs_fn=None, run_cmd=None, connect_fn=None, opener=None) -> int:
    parser = argparse.ArgumentParser(
        description="Trace one cron-job.org execution to its Actions run, database rows and REST rows (read-only).")
    parser.add_argument("--execution-time", required=True, type=_execution_time_arg,
                        help="the execution's actual UTC time from the cron-job.org history, e.g. 2026-10-19T14:05:02Z")
    parser.add_argument("--execution-status", required=True, type=int,
                        help="the execution's HTTP status from the history (2xx; GitHub answers 204)")
    parser.add_argument("--run-id", type=_run_id_arg, default=None,
                        help="optional: the Actions run id; must agree with the correlated run")
    parser.add_argument("--out", metavar="FILE.md", help="write the table and the link results here")
    parser.add_argument("--json-out", metavar="FILE", help="write the evidence as JSON here")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    try:
        cfg = supabase_rest.config_from_env()
    except supabase_rest.ConfigError as exc:
        print(supabase_rest.redact_rest(str(exc)), file=sys.stderr)
        return 2
    if connect_fn is None and not os.environ.get("SUPABASE_DB_URL", "").strip():
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2

    result = trace(args.execution_time, args.execution_status, cfg, run_id=args.run_id,
                   fetch_runs_fn=fetch_runs_fn, run_cmd=run_cmd, connect_fn=connect_fn, opener=opener)
    text = render_table(result)
    print(_clean(text, cfg))
    if args.out:
        _write(args.out, text, cfg)
    if args.json_out:
        _write(args.json_out, json.dumps(result, indent=2, sort_keys=True), cfg)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    sys.exit(main())
