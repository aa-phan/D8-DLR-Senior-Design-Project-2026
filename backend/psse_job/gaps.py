"""
The SCH-02 gap check of the hourly PSS/E job (pss-e-integration Phase 3, plan 03-02).

`run` executes docs/data-science/schema/psse_run_gaps.sql as the writer credential (the job's own
dlr_psse_writer holds SELECT on public.psse_run) on a READ-ONLY session and prints one line per UTC
hour that has no complete result set, with a header (runs recorded, first and latest run slot).
The SQL file is the only gap logic: this module loads it, filters its rows by `since` and `until`
in Python (so there is no second gap query to drift), and formats them. The one other statement is
the summary behind the header and the "no runs recorded" case; it is not gap logic.

Exit codes (equal to the launcher's table, plan 03-01 D-03): 0 ok, 5 gaps found with `fail_on_gaps`
(an empty table counts as a gap there), 6 the check could not run. Every time is printed as an ISO
UTC instant ending in Z. The output holds slot times, kinds and counts only: no connection detail,
no case label and no run identifier, and a failure prints one redacted line.

psycopg is imported by writer.connect only. Standard library and psse_job only, Python 3.7 syntax.
UNVERIFIED until the laptop session: that the live table shows the real laptop's hours, that the
laptop clock agrees with the database, and daylight-saving effects.

The legacy `run` counts every run regardless of which solver wrote it, so once the second solver
writes, it can hide one solver's missing hour behind the other's. `run_by_solver` is the per-solver
check (second-solver workstream Phase 3, DB-03): one read-only statement returns (slot_time, solver,
outcome) for every run, the database supplies its own current UTC hour, and each solver's missing
hours are computed in Python from THAT solver's first recorded slot, with the same five rules as
above. It needs the `solver` column of migration 20261118200000 (on an older schema it fails with
one redacted line). The laptop `gaps` command keeps the legacy check for now (assumption A6);
only times, solver tags, kinds and counts are printed.
"""

import collections
import datetime
import os
import re
import sys

from psse_job import contract
from psse_job import writer
from psse_job.redaction import env_secrets, redact

EXIT_OK = 0
EXIT_GAPS = 5
EXIT_CHECK_FAILED = 6

# backend/psse_job/gaps.py -> three directories up is the repository root.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir))
GAP_SQL_PATH = os.path.join(_REPO_ROOT, "docs", "data-science", "schema", "psse_run_gaps.sql")

SUMMARY_SQL = "select count(*), min(slot_time), max(slot_time) from public.psse_run"

GapRow = collections.namedtuple("GapRow", ["slot_time", "gap_kind", "runs", "failed_runs"])


class GapCheckError(RuntimeError):
    """The check could not run; the message is fixed text and never names a path."""


def load_sql():
    """The statement text of the SQL file. GapCheckError (no path in the message) when unreadable."""
    failure = None
    text = None
    try:
        with open(GAP_SQL_PATH, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        failure = "the gap statement file could not be read"
    # Raised outside the except block so no exception context (and no path) is attached.
    if failure is not None:
        raise GapCheckError(failure)
    return text


def fetch_gaps(conn):
    """Run the SQL file on `conn`; one GapRow per row, oldest slot first."""
    rows = conn.execute(load_sql()).fetchall()
    return [GapRow(*tuple(row)) for row in rows]


def fetch_summary(conn):
    """(number of runs, first slot, latest slot) of public.psse_run; the slots are None when empty."""
    row = conn.execute(SUMMARY_SQL).fetchone()
    return (row[0], row[1], row[2])


def _utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _iso(value):
    return _utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _in_window(slot, since, until):
    slot = _utc(slot)
    if since is not None and slot < _utc(since):
        return False
    if until is not None and slot >= _utc(until):
        return False
    return True


def format_report(summary, gaps, since=None, until=None):
    """
    The printed report (no trailing newline). `gaps` is filtered by `since` (inclusive) and `until`
    (exclusive) here. An empty table gives "no runs recorded".
    """
    n_runs, first_slot, latest_slot = summary
    if not n_runs:
        return "no runs recorded"
    shown = [gap for gap in gaps if _in_window(gap.slot_time, since, until)]
    lines = [
        "gap check (UTC): %d runs recorded" % n_runs,
        "first run slot: %s" % _iso(first_slot),
        "latest run slot: %s" % _iso(latest_slot),
    ]
    window = ""
    if since is not None or until is not None:
        window = " (window: from %s, up to %s)" % (
            _iso(since) if since is not None else "the start",
            _iso(until) if until is not None else "now",
        )
    if shown:
        lines.append("%d gaps%s" % (len(shown), window))
    else:
        lines.append("no gaps%s" % window)
    for gap in shown:
        lines.append("%s  %-11s runs=%d failed=%d" % (_iso(gap.slot_time), gap.gap_kind, gap.runs, gap.failed_runs))
    return "\n".join(lines)


def run(env, since=None, until=None, fail_on_gaps=False, out=None, connect=None):
    """
    Print the gap report and return an exit code: 0 ok; 5 gaps found (or no runs recorded) with
    `fail_on_gaps`; 6 the check could not run (one redacted line, nothing else). `env` is the
    configuration dict (SUPABASE_PSSE_DB_URL); `since` (inclusive) and `until` (exclusive) are aware
    UTC datetimes or None; `connect` is a test seam defaulting to writer.connect(env=env).
    """
    out = sys.stdout if out is None else out
    if connect is None:
        def connect():
            return writer.connect(env=env)

    conn = None
    failure = None
    code = EXIT_OK
    try:
        conn = connect()
        # Before any statement. psycopg applies `read_only` only to the transactions it opens
        # itself (BEGIN READ ONLY) and never to autocommit statements, and writer.connect returns an
        # autocommit connection; so leave autocommit first, or the flag would do nothing.
        conn.autocommit = False
        conn.read_only = True
        gap_rows = fetch_gaps(conn)
        summary = fetch_summary(conn)
        shown = [gap for gap in gap_rows if _in_window(gap.slot_time, since, until)]
        report = format_report(summary, gap_rows, since, until)
        if fail_on_gaps and (not summary[0] or shown):
            code = EXIT_GAPS
    except Exception as exc:  # noqa: BLE001 - reported below as one redacted line
        failure = redact(str(exc), env_secrets(env)) or type(exc).__name__
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    if failure is not None:
        out.write("gap check could not run: %s\n" % failure)
        return EXIT_CHECK_FAILED
    out.write(report + "\n")
    return code


# --------------------------------------------------------------------------- per-solver check (DB-03)

RUNS_SQL = "select slot_time, solver, outcome from public.psse_run"
# The current hour comes from the database, on the same read-only connection, so the runner's clock
# and the database's clock can never disagree.
CURRENT_HOUR_SQL = "select (date_trunc('hour', now() at time zone 'UTC') at time zone 'UTC')"

SolverSummary = collections.namedtuple("SolverSummary", ["runs", "first_slot", "latest_slot"])

_HOUR = datetime.timedelta(hours=1)
_SOLVER_LABEL = re.compile(r"[a-z][a-z0-9_]{0,31}")
_UNKNOWN_SOLVER = "unknown"


def _solver_label(value):
    """The solver tag as printed: a plain tag unchanged, anything else the label `unknown`."""
    if isinstance(value, str) and _SOLVER_LABEL.fullmatch(value):
        return value
    return _UNKNOWN_SOLVER


def fetch_runs(conn):
    """Every run as (slot_time, solver, outcome) on `conn`, from the one read-only statement."""
    rows = conn.execute(RUNS_SQL).fetchall()
    return [tuple(row) for row in rows]


def fetch_current_slot(conn):
    """The database's current UTC hour as an aware UTC datetime."""
    row = conn.execute(CURRENT_HOUR_SQL).fetchone()
    return _utc(row[0])


def _group(runs):
    """{solver label: {aware UTC slot: [outcome, ...]}} for (slot_time, solver, outcome) tuples."""
    grouped = {}
    for slot, solver, outcome in runs:
        by_slot = grouped.setdefault(_solver_label(solver), {})
        by_slot.setdefault(_utc(slot), []).append(outcome)
    return grouped


def summarize(runs):
    """{solver: SolverSummary(runs, first_slot, latest_slot)} for every solver present in `runs`."""
    summaries = {}
    for solver, by_slot in _group(runs).items():
        count = sum(len(outcomes) for outcomes in by_slot.values())
        summaries[solver] = SolverSummary(count, min(by_slot), max(by_slot))
    return summaries


def compute_gaps(runs, current_slot):
    """
    {solver: [GapRow, ...]}, oldest first, one entry per solver present in `runs`. Each solver is
    walked on its own: whole hours from THAT solver's first slot while the hour is before
    `current_slot` (the current hour and later rows are never walked). An hour with no row of the
    solver is `no_run`; an hour whose rows of the solver are all `failed` is `failed_only`. Another
    solver's rows never fill an hour.
    """
    current = _utc(current_slot)
    result = {}
    for solver, by_slot in _group(runs).items():
        found = []
        hour = min(by_slot)
        while hour < current:
            outcomes = by_slot.get(hour)
            if outcomes is None:
                found.append(GapRow(hour, "no_run", 0, 0))
            elif all(outcome == "failed" for outcome in outcomes):
                found.append(GapRow(hour, "failed_only", len(outcomes), len(outcomes)))
            hour += _HOUR
        result[solver] = found
    return result


def solver_order(names):
    """The PSS/E tag first when present, then the other tags sorted."""
    names = set(names)
    ordered = [contract.SOLVER_PSSE] if contract.SOLVER_PSSE in names else []
    return ordered + sorted(names - set(ordered))


def format_solver_report(summaries, gaps_by_solver, since=None, until=None, expected=()):
    """
    The printed per-solver report (no trailing newline). One section per solver present in
    `summaries` or named in `expected`, the PSS/E section first. `gaps_by_solver` is filtered by
    `since` (inclusive) and `until` (exclusive) here; the counts and slots cover every row.
    """
    expected = [_solver_label(name) for name in expected]
    if not summaries and not expected:
        return "no runs recorded"
    total = sum(summary.runs for summary in summaries.values())
    lines = ["gap check per solver (UTC): %d runs recorded" % total]
    window = ""
    if since is not None or until is not None:
        window = " (window: from %s, up to %s)" % (
            _iso(since) if since is not None else "the start",
            _iso(until) if until is not None else "now",
        )
    for name in solver_order(list(summaries) + expected):
        summary = summaries.get(name)
        if summary is None:
            lines.append("solver %s: no runs recorded" % name)
            continue
        shown = [gap for gap in gaps_by_solver.get(name, []) if _in_window(gap.slot_time, since, until)]
        lines.append("solver %s: %d runs recorded" % (name, summary.runs))
        lines.append("first run slot: %s" % _iso(summary.first_slot))
        lines.append("latest run slot: %s" % _iso(summary.latest_slot))
        if shown:
            lines.append("%d gaps%s" % (len(shown), window))
        else:
            lines.append("no gaps%s" % window)
        for gap in shown:
            lines.append("%s  %-11s runs=%d failed=%d" % (_iso(gap.slot_time), gap.gap_kind, gap.runs, gap.failed_runs))
    return "\n".join(lines)


def run_by_solver(env, since=None, until=None, fail_on_gaps=False, out=None, connect=None, expected=(), failing=None):
    """
    The per-solver gap check. Prints the report and returns an exit code: 0 ok; 5 with
    `fail_on_gaps` when the table has no rows, or when a solver in `failing` has a gap in the window
    or is expected but has no rows; 6 the check could not run (one redacted line, nothing else).
    `failing` None means every present or expected solver except PSS/E: its gaps are listed but do
    not fail by default, because its machine being offline is the known state. `expected` names
    solvers that must appear in the report even with no rows. `env`, `since`, `until`, `connect` and
    `out` are as in `run`.
    """
    out = sys.stdout if out is None else out
    if connect is None:
        def connect():
            return writer.connect(env=env)

    conn = None
    failure = None
    code = EXIT_OK
    try:
        conn = connect()
        # Before any statement, and leave autocommit first: see `run`.
        conn.autocommit = False
        conn.read_only = True
        runs = fetch_runs(conn)
        current_slot = fetch_current_slot(conn)
        summaries = summarize(runs)
        gaps_by_solver = compute_gaps(runs, current_slot)
        report = format_solver_report(summaries, gaps_by_solver, since, until, expected)
        if fail_on_gaps:
            if not runs:
                code = EXIT_GAPS
            else:
                present = set(summaries) | set(_solver_label(name) for name in expected)
                watched = [name for name in present if name != contract.SOLVER_PSSE] if failing is None else list(failing)
                for name in watched:
                    shown = [gap for gap in gaps_by_solver.get(name, []) if _in_window(gap.slot_time, since, until)]
                    missing = name in present and name not in summaries
                    if shown or missing:
                        code = EXIT_GAPS
    except Exception as exc:  # noqa: BLE001 - reported below as one redacted line
        failure = redact(str(exc), env_secrets(env)) or type(exc).__name__
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    if failure is not None:
        out.write("gap check could not run: %s\n" % failure)
        return EXIT_CHECK_FAILED
    out.write(report + "\n")
    return code
