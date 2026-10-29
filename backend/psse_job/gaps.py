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
"""

import collections
import datetime
import os
import sys

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
        conn.read_only = True  # before any statement: the session cannot change data
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
