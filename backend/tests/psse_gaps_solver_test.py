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


# --------------------------------------------------------------------------- report, exit codes, failures


def _mixed_rows():
    return [
        (H - 8 * HOUR, PSSE, "ok"), (H - 6 * HOUR, PSSE, "failed"), (H - 6 * HOUR, PSSE, "failed"),
        (H - 1 * HOUR, PSSE, "fallback"),
        (H - 5 * HOUR, PP, "ok"), (H - 2 * HOUR, PP, "ok"),
        (H - 4 * HOUR, "zeta", "ok"), (H - 1 * HOUR, "zeta", "ok"),
    ]


def test_report_lines_hold_only_times_tags_kinds_and_counts():
    allowed = [
        re.compile(r"^gap check per solver \(UTC\): \d+ runs recorded$"),
        re.compile(r"^solver [a-z][a-z0-9_]*: \d+ runs recorded$"),
        re.compile(r"^solver [a-z][a-z0-9_]*: no runs recorded$"),
        re.compile(r"^first run slot: " + ISO + "$"),
        re.compile(r"^latest run slot: " + ISO + "$"),
        re.compile(r"^(\d+ gaps|no gaps)( \(window: from (" + ISO + r"|the start), up to (" + ISO + r"|now)\))?$"),
        re.compile(r"^" + ISO + r"  (no_run|failed_only)\s+runs=\d+ failed=\d+$"),
        re.compile(r"^no runs recorded$"),
    ]
    outputs = []
    for kwargs in (
        {},
        {"since": H - 7 * HOUR, "until": H - 1 * HOUR},
        {"since": H - 3 * HOUR},
        {"until": H - 4 * HOUR},
        {"expected": (PP, "never_seen")},
    ):
        _, text, _ = _check(_mixed_rows(), fail_on_gaps=True, **kwargs)
        outputs.append(text)
    outputs.append(_check([])[1])
    outputs.append(_check([], expected=("never_seen",))[1])
    for text in outputs:
        assert text.endswith("\n")
        for line in text.splitlines():
            assert any(pattern.match(line) for pattern in allowed), line
            assert not re.search(r"(psse|pp)-\d{8}T", line), line
    # The unfiltered report really does list gap lines of more than one solver.
    assert len(_gap_lines(_section(outputs[0], PSSE))) > 0
    assert len(_gap_lines(_section(outputs[0], PP))) > 0
    assert "(window: from the start, up to " + _iso(H - 4 * HOUR) + ")" in outputs[3]


def test_sections_are_psse_first_then_by_name():
    rows = [(H - HOUR, "zeta", "ok"), (H - HOUR, PP, "ok"), (H - HOUR, PSSE, "ok")]
    _, text, _ = _check(rows)
    headers = [line.split(":")[0] for line in text.splitlines() if line.startswith("solver ")]
    assert headers == ["solver psse", "solver pandapower", "solver zeta"]
    # An expected solver with no rows takes its place in the same order.
    _, text, _ = _check([(H - HOUR, PSSE, "ok")], expected=("zeta", PP))
    headers = [line.split(":")[0] for line in text.splitlines() if line.startswith("solver ")]
    assert headers == ["solver psse", "solver pandapower", "solver zeta"]
    assert gaps.solver_order(["b", PSSE, "a"]) == [PSSE, "a", "b"]


def test_window_filters_gap_lines_not_summaries():
    rows = [(H - 6 * HOUR, PSSE, "ok"), (H - 1 * HOUR, PSSE, "ok")]  # gaps at H-5h .. H-2h
    _, text, _ = _check(rows, since=H - 4 * HOUR, until=H - 2 * HOUR)
    section = _section(text, PSSE)
    assert [line.split()[0] for line in _gap_lines(section)] == [_iso(H - 4 * HOUR), _iso(H - 3 * HOUR)]
    assert "2 gaps (window: from %s, up to %s)" % (_iso(H - 4 * HOUR), _iso(H - 2 * HOUR)) in section
    assert "solver psse: 2 runs recorded" in section
    assert "first run slot: " + _iso(H - 6 * HOUR) in section
    assert "latest run slot: " + _iso(H - 1 * HOUR) in section
    assert text.splitlines()[0] == "gap check per solver (UTC): 2 runs recorded"
    # Since is inclusive and until is exclusive: a one-hour window holds exactly that hour.
    _, text, _ = _check(rows, since=H - 5 * HOUR, until=H - 4 * HOUR)
    assert [line.split()[0] for line in _gap_lines(_section(text, PSSE))] == [_iso(H - 5 * HOUR)]
    _, text, _ = _check(rows, since=H - 1 * HOUR)
    assert "no gaps (window: from %s, up to now)" % _iso(H - 1 * HOUR) in _section(text, PSSE)


def test_exit_codes():
    code, text, _ = _check([], fail_on_gaps=True)
    assert (code, text) == (5, "no runs recorded\n")
    assert _check([])[0] == 0

    psse_gap = [(H - 3 * HOUR, PSSE, "ok"), (H - 1 * HOUR, PSSE, "ok")]
    pp_gap = [(H - 3 * HOUR, PP, "ok"), (H - 1 * HOUR, PP, "ok")]
    assert _check(psse_gap, fail_on_gaps=True)[0] == 0           # PSS/E gaps are listed, not failing
    assert "1 gaps" in _check(psse_gap, fail_on_gaps=True)[1]
    assert _check(pp_gap, fail_on_gaps=True)[0] == 5
    assert _check(pp_gap)[0] == 0                                 # without fail_on_gaps nothing fails

    only_psse = [(H - 2 * HOUR, PSSE, "ok"), (H - 1 * HOUR, PSSE, "ok")]
    code, text, _ = _check(only_psse, fail_on_gaps=True, expected=(PP,))
    assert code == 5
    assert "solver pandapower: no runs recorded" in text.splitlines()
    assert _check(only_psse, fail_on_gaps=True)[0] == 0           # not expected, so not missing
    assert _check(only_psse, expected=(PP,))[0] == 0

    only_pp = [(H - 2 * HOUR, PP, "ok"), (H - 1 * HOUR, PP, "ok")]
    assert _check(only_pp, fail_on_gaps=True, expected=(PSSE,))[0] == 0   # PSS/E offline is the known state

    assert _check(psse_gap, fail_on_gaps=True, failing=(PSSE,))[0] == 5
    assert _check(pp_gap, fail_on_gaps=True, failing=(PSSE,))[0] == 0     # only the named solvers fail
    assert _check(only_psse, fail_on_gaps=True, expected=(PP,), failing=(PSSE,))[0] == 0

    # A gap outside the window does not fail; since is inclusive and until exclusive.
    gap_at = H - 2 * HOUR
    assert _check(pp_gap, fail_on_gaps=True, since=H - 1 * HOUR)[0] == 0
    assert _check(pp_gap, fail_on_gaps=True, until=gap_at)[0] == 0
    assert _check(pp_gap, fail_on_gaps=True, since=gap_at)[0] == 5
    assert _check(pp_gap, fail_on_gaps=True, until=gap_at + HOUR)[0] == 5


def test_failure_is_one_redacted_line():
    password = "pw" + "-" + "Zk93Xr"
    url = "postgresql://gapuser_zq:" + password + "@127.0.0.1:5999/somedb"
    env = {"SUPABASE_PSSE_DB_URL": url}

    def refuse():
        raise RuntimeError("could not connect to " + url + " with " + password)

    buffer = io.StringIO()
    assert gaps.run_by_solver(env, connect=refuse, out=buffer) == 6
    text = buffer.getvalue()
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 1 and lines[0].startswith("gap check could not run: ")
    for secret in (password, url, "gapuser_zq", "127.0.0.1", "somedb"):
        assert secret not in text

    conn = _FakeConnection([], H, fail_on=RuntimeError("statement failed for " + url + " " + password))
    buffer = io.StringIO()
    assert gaps.run_by_solver(env, connect=lambda: conn, out=buffer, fail_on_gaps=True) == 6
    text = buffer.getvalue()
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 1 and lines[0].startswith("gap check could not run: ")
    for secret in (password, url, "gapuser_zq", "127.0.0.1", "somedb"):
        assert secret not in text
    assert ("close",) in conn.events

    # A missing URL is a failed check too, in one line.
    blank = io.StringIO()
    assert gaps.run_by_solver({}, out=blank) == 6
    assert blank.getvalue().startswith("gap check could not run: ")
    assert len([line for line in blank.getvalue().splitlines() if line.strip()]) == 1


def test_read_only_before_any_statement():
    _, _, conn = _check([(H - HOUR, PSSE, "ok")], fail_on_gaps=True)
    kinds = [event[0] for event in conn.events]
    assert kinds[:2] == ["set", "set"]
    assert conn.events[0] == ("set", "autocommit", False)
    assert conn.events[1] == ("set", "read_only", True)
    statements = [event[1] for event in conn.events if event[0] == "execute"]
    assert statements == [gaps.RUNS_SQL, gaps.CURRENT_HOUR_SQL]
    assert kinds.index("execute") > 1
    for sql in statements:
        assert re.match(r"(?i)^select\b", sql)
        assert ";" not in sql
        for word in ("insert", "update", "delete", "alter", "drop", "grant", "truncate", "create"):
            assert not re.search(r"(?i)\b" + word + r"\b", sql), word
    # The source holds no hour-series function of its own (the legacy SQL file is the only one).
    with open(gaps.__file__, encoding="utf-8") as handle:
        assert "generate_series" not in handle.read()


def test_legacy_path_is_unchanged():
    names = list(inspect.signature(gaps.run).parameters)
    assert names == ["env", "since", "until", "fail_on_gaps", "out", "connect"]
    assert gaps.SUMMARY_SQL == "select count(*), min(slot_time), max(slot_time) from public.psse_run"
    assert gaps.GapRow._fields == ("slot_time", "gap_kind", "runs", "failed_runs")
    assert gaps.GAP_SQL_PATH.replace("\\", "/").endswith("docs/data-science/schema/psse_run_gaps.sql")
    assert os.path.isfile(gaps.GAP_SQL_PATH)
    assert callable(gaps.fetch_gaps) and callable(gaps.format_report) and callable(gaps.fetch_summary)
    # The pooled legacy report keeps its own header: it is the laptop command's, not the per-solver one.
    pooled = gaps.format_report((5, H - 3 * HOUR, H - 1 * HOUR), [])
    assert pooled.splitlines()[0] == "gap check (UTC): 5 runs recorded"


# --------------------------------------------------------------------------- database tier (skips here)


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a database with the Phase 4 migrations, the reference DDL and the solver-tag migration."""
    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_solver_schema(admin_url)
        yield admin_url


def _db_hour(admin_url):
    rows = pg_helper.admin_rows(
        admin_url, "select (date_trunc('hour', now() at time zone 'UTC') at time zone 'UTC') as slot")
    return rows[0]["slot"].astimezone(UTC)


def test_db_run_by_solver_on_the_migrated_schema(pg):
    import psycopg
    import psycopg.errors

    writer_url = pg_helper.role_url(pg, "dlr_psse_writer")

    def seed(hour):
        n = 0
        with psycopg.connect(pg, autocommit=True) as admin:
            for solver, prefix, backs in ((PSSE, "psse", (3, 2, 1)), (PP, "pp", (3, 1))):
                for back in backs:
                    n += 1
                    started = hour - back * HOUR + datetime.timedelta(minutes=15)
                    run_id = pg_helper.make_run_id(n, started, prefix=prefix)
                    row = pg_helper.valid_run_rows(run_id, started, outcome="ok")["psse_run"][0]
                    if solver != PSSE:
                        row = dict(row, solver=solver, solver_version="test-1")
                    pg_helper.insert_rows(admin, "psse_run", [row])

    # The database's hour must not roll while the check runs: up to three attempts, then fail.
    for _ in range(3):
        pg_helper.reset(pg)
        before = _db_hour(pg)
        seed(before)
        buffer = io.StringIO()
        code = gaps.run_by_solver(
            {}, connect=lambda: writer.connect(writer_url), out=buffer, fail_on_gaps=True)
        probe = writer.connect(writer_url)
        try:
            probe.autocommit = False
            probe.read_only = True
            fetched = gaps.fetch_current_slot(probe)
            probe.rollback()
        finally:
            probe.close()
        if _db_hour(pg) == before and fetched == before:
            break
    else:
        pytest.fail("the database's hour rolled during all three attempts")
    text = buffer.getvalue()
    assert code == 5
    assert _gap_lines(_section(text, PP)) == ["%s  no_run      runs=0 failed=0" % _iso(before - 2 * HOUR)]
    assert _gap_lines(_section(text, PSSE)) == []
    assert fetched == before

    # The session set up exactly as run_by_solver does refuses a write.
    row = pg_helper.valid_run_rows(pg_helper.make_run_id(99, before, prefix="psse"), before)["psse_run"][0]
    conn = writer.connect(writer_url)
    try:
        conn.autocommit = False
        conn.read_only = True
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            pg_helper.insert_rows(conn, "psse_run", [row])
        conn.rollback()
    finally:
        conn.close()
