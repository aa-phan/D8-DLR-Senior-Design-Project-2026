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


# --------------------------------------------------------------------------- compute_gaps vs the oracle


def reference_gaps(runs, current_slot):
    """
    The independent oracle: `runs` is a list of (slot, outcome); returns the gaps as
    (slot, kind, runs, failed_runs) tuples. Plain loops, no SQL concepts: group the outcomes by
    slot, walk the hours from the first slot up to the hour before `current_slot`, list a slot
    with no outcome at all as no_run and a slot whose outcomes are all failed as failed_only.
    """
    by_slot = {}
    for slot, outcome in runs:
        by_slot.setdefault(slot, []).append(outcome)
    if not by_slot:
        return []
    found = []
    hour = min(by_slot)
    while hour < current_slot:
        outcomes = by_slot.get(hour)
        if outcomes is None:
            found.append((hour, "no_run", 0, 0))
        elif all(outcome == "failed" for outcome in outcomes):
            found.append((hour, "failed_only", len(outcomes), len(outcomes)))
        hour += HOUR
    return found


def _tuples(rows):
    return [(r.slot_time, r.gap_kind, r.runs, r.failed_runs) for r in rows]


def _random_rows(rng):
    """0 to 40 rows over the two solvers, each solver with its own first slot within 72 hours before H."""
    rows = []
    for solver in (PSSE, PP):
        if rng.random() < 0.15:
            continue  # this solver has no rows at all in this history
        first_back = rng.randint(1, 72)
        for _ in range(rng.randint(0, 20)):
            back = rng.randint(0, first_back)
            outcome = rng.choice(["ok", "fallback", "failed"])
            rows.append((H - back * HOUR, solver, outcome))
            if rng.random() < 0.2:  # several rows in one hour
                rows.append((H - back * HOUR, solver, rng.choice(["ok", "fallback", "failed"])))
        # the solver's own first slot always carries a row so its walk really starts there
        rows.append((H - first_back * HOUR, solver, rng.choice(["ok", "fallback", "failed"])))
    rng.shuffle(rows)
    return rows[:40]


def test_compute_gaps_matches_the_oracle_per_solver():
    rng = random.Random(20261118)
    with_gaps = 0
    for _ in range(300):
        rows = _random_rows(rng)
        result = gaps.compute_gaps(rows, H)
        for solver in (PSSE, PP):
            mine = [(slot, outcome) for slot, name, outcome in rows if name == solver]
            if not mine:
                assert solver not in result
                continue
            expected = reference_gaps(mine, H)
            assert _tuples(result[solver]) == expected
            with_gaps += bool(expected)
    assert with_gaps > 50  # the histories really do contain gaps, so the comparison is not vacuous


def test_hours_before_a_solvers_first_slot_are_not_its_gaps():
    rows = [(H - n * HOUR, PSSE, "ok") for n in range(1, 11)]
    rows += [(H - n * HOUR, PP, "ok") for n in range(1, 4)]
    result = gaps.compute_gaps(rows, H)
    assert result[PP] == []
    assert result[PSSE] == []


def test_pss_e_offline_is_listed_separately():
    rows = [(H - n * HOUR, PP, "ok") for n in range(1, 7)]
    rows += [(H - 6 * HOUR, PSSE, "ok"), (H - 1 * HOUR, PSSE, "ok")]
    result = gaps.compute_gaps(rows, H)
    assert _tuples(result[PSSE]) == [(H - n * HOUR, "no_run", 0, 0) for n in (5, 4, 3, 2)]
    assert result[PP] == []


def test_failed_only_is_per_solver():
    rows = [
        (H - 3 * HOUR, PSSE, "ok"), (H - 3 * HOUR, PP, "ok"),
        (H - 2 * HOUR, PSSE, "ok"), (H - 2 * HOUR, PP, "failed"), (H - 2 * HOUR, PP, "failed"),
        (H - 1 * HOUR, PSSE, "ok"), (H - 1 * HOUR, PP, "ok"),
    ]
    result = gaps.compute_gaps(rows, H)
    assert result[PP] == [gaps.GapRow(H - 2 * HOUR, "failed_only", 2, 2)]
    assert result[PSSE] == []


def test_only_the_current_hour_and_later_rows():
    assert gaps.compute_gaps([(H, PSSE, "failed")], H) == {PSSE: []}
    # A row at H+1h (a clock ahead of the database) is not walked and creates no gap.
    result = gaps.compute_gaps([(H - 2 * HOUR, PSSE, "ok"), (H - 1 * HOUR, PSSE, "ok"), (H + HOUR, PSSE, "ok")], H)
    assert result == {PSSE: []}
    assert gaps.compute_gaps([(H + HOUR, PP, "failed")], H) == {PP: []}


def test_unknown_solver_label():
    rows = [(H - 2 * HOUR, "Bad Label!", "ok"), (H - 1 * HOUR, "Bad Label!", "ok"), (H - 1 * HOUR, PSSE, "ok")]
    result = gaps.compute_gaps(rows, H)
    assert set(result) == {"unknown", PSSE}
    summaries = gaps.summarize(rows)
    assert summaries["unknown"].runs == 2
    assert "Bad Label!" not in gaps.format_solver_report(summaries, result)
    # A value that is not even text, and an over-long tag, are grouped the same way.
    assert set(gaps.summarize([(H, None, "ok"), (H, "a" * 33, "ok")])) == {"unknown"}
