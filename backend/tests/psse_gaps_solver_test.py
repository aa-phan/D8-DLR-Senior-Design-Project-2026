"""
DB-03 proofs of the per-solver gap check `psse_job.gaps.run_by_solver` (pandapower-solver
workstream, phase 3, plan 03-03, decision D-06).

Once two solvers write to public.psse_run the legacy pooled check (`gaps.run`) lets one solver's
row fill the other's hour. The per-solver check reads (slot_time, solver, outcome) on one
read-only statement, takes the database's current UTC hour from a second one, and computes each
solver's missing hours in plain Python from that solver's own first slot.

Pure Python: a fake connection stands in for the database, so every test but the last runs
everywhere and nothing is skipped. The last test (`test_db_*`) runs the two statements on a
throwaway local Postgres; it is skipped unless `DLR_TEST_PG_AUTOSTART=1` or a local
`DLR_TEST_DATABASE_URL` is set, and FAILS under `PSSE_REQUIRE_PG=1` when no database is available.
A skip proves nothing about Postgres. It never touches Supabase.

Honest scope: the laptop `gaps` command keeps the legacy pooled check (assumption A6); this file
proves the library-level per-solver check only.

Follows backend/tests/psse_gaps_pg_test.py (module-level functions, plain asserts, no classes).
"""

import datetime
import inspect
import io
import os
import random
import re
import sys

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_local_pg as pg_helper  # noqa: E402
from psse_job import contract, gaps, writer  # noqa: E402

HOUR = datetime.timedelta(hours=1)
UTC = datetime.timezone.utc
H = datetime.datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)  # the database's current hour in these tests
PSSE = contract.SOLVER_PSSE
PP = "pandapower"
ISO = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"


def _iso(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class _Result:
    def __init__(self, rows=None, one=None):
        self._rows = rows
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _FakeConnection:
    """
    A connection that records `("set", name, value)` for the autocommit / read_only assignments and
    `("execute", sql)` for each statement, answers the two statements of the per-solver check and
    refuses any other. `fail_on` is an exception raised by the first `execute`.
    """

    def __init__(self, rows, current_slot, fail_on=None):
        object.__setattr__(self, "events", [])
        object.__setattr__(self, "_rows", rows)
        object.__setattr__(self, "_current", current_slot)
        object.__setattr__(self, "_fail_on", fail_on)

    def __setattr__(self, name, value):
        self.events.append(("set", name, value))

    def execute(self, sql, params=None):
        self.events.append(("execute", sql))
        if self._fail_on is not None:
            raise self._fail_on
        if sql == gaps.RUNS_SQL:
            return _Result(rows=list(self._rows))
        if sql == gaps.CURRENT_HOUR_SQL:
            return _Result(one=(self._current,))
        raise AssertionError("unexpected statement: " + sql)

    def close(self):
        self.events.append(("close",))


def _check(rows, current=H, **kwargs):
    """Run run_by_solver on a fake connection: (exit code, printed text, the connection)."""
    conn = _FakeConnection(rows, current)
    buffer = io.StringIO()
    code = gaps.run_by_solver({}, connect=lambda: conn, out=buffer, **kwargs)
    return code, buffer.getvalue(), conn


def _section(text, name):
    """The lines of one solver's section (from its `solver <name>:` line to the next solver line)."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("solver %s:" % name))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("solver ")), len(lines))
    return lines[start:end]


def _gap_lines(section):
    return [line for line in section if re.match(r"^" + ISO + r"  ", line)]


def test_tracer_a_psse_hour_does_not_hide_a_missing_pandapower_hour():
    rows = [
        (H - 3 * HOUR, PSSE, "ok"), (H - 2 * HOUR, PSSE, "ok"), (H - 1 * HOUR, PSSE, "ok"),
        (H - 3 * HOUR, PP, "ok"), (H - 1 * HOUR, PP, "ok"),
    ]
    code, text, conn = _check(rows, fail_on_gaps=True)
    assert code == 5
    assert _gap_lines(_section(text, PP)) == ["%s  no_run      runs=0 failed=0" % _iso(H - 2 * HOUR)]
    assert "no gaps" in _section(text, PSSE)
    assert _gap_lines(_section(text, PSSE)) == []

    code_tolerant, _, _ = _check(rows)
    assert code_tolerant == 0

    assert conn.events == [
        ("set", "autocommit", False),
        ("set", "read_only", True),
        ("execute", gaps.RUNS_SQL),
        ("execute", gaps.CURRENT_HOUR_SQL),
        ("close",),
    ]
