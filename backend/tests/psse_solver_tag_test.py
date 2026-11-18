"""
The solver tag carried through the PSS/E job package (DB-02, Phase 3 plan 03-02).

Pure Python: no database and no solver package. A recording connection stands in for the
writer's connection. The second solver's real tag and prefix are used only through
`monkeypatch.setitem(contract.RUN_ID_PREFIXES, ...)`, so nothing leaks into other tests, and
this file never imports the second solver.
"""

import contextlib
import datetime
import os
import re
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fakes  # noqa: E402
from psse_job import contract, job, ratings, run_record, writer  # noqa: E402

NOW = datetime.datetime(2026, 11, 18, 14, 7, 30, tzinfo=datetime.timezone.utc)
LATER = NOW + datetime.timedelta(minutes=4)

SECOND_SOLVER = "pandapower"
SECOND_PREFIX = "pp"
PP_ID = re.compile(r"^pp-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
PSSE_ID = re.compile(r"^psse-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


class _RecordingConnection(object):
    """Keeps every (sql, params) it is asked to execute; no database."""

    def __init__(self):
        self.calls = []

    def transaction(self):
        return contextlib.nullcontext()

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return ("inserted",)

    def close(self):
        pass


def _clock():
    values = iter([NOW, LATER])
    return lambda: next(values, LATER)


def _fetch():
    return psse_fakes.fake_fetch(psse_fakes.latest_rows(NOW))


def _tagged_study(selection, context):
    return psse_fakes.fake_results(selection)._replace(
        solver=SECOND_SOLVER, solver_version="3.5.6", psse_version=None)


def _psse_study(selection, context):
    return psse_fakes.fake_results(selection)


def _register(monkeypatch):
    monkeypatch.setitem(contract.RUN_ID_PREFIXES, SECOND_SOLVER, SECOND_PREFIX)


def _run(study, conn, solver=None):
    kwargs = {} if solver is None else {"solver": solver}
    return job.run_once(
        fetch=_fetch(), study=study, connect=lambda: conn, case_id="CASE", clock=_clock(),
        env={"PSSE_JOB_VERSION": "t"}, **kwargs)


def test_tracer_tagged_run_is_written_with_the_tagged_insert(monkeypatch):
    _register(monkeypatch)
    conn = _RecordingConnection()
    outcome = _run(_tagged_study, conn, solver=SECOND_SOLVER)

    assert outcome.status == "written", outcome
    assert outcome.exit_code == 0
    run_calls = [c for c in conn.calls if c[0] == contract.INSERT_RUN_TAGGED_SQL]
    assert len(run_calls) == 1
    assert [c for c in conn.calls if c[0] == contract.INSERT_RUN_SQL] == []
    params = run_calls[0][1]
    assert tuple(params) == contract.TAGGED_RUN_COLUMNS
    assert PP_ID.match(params["run_id"]), params["run_id"]
    assert params["solver"] == SECOND_SOLVER
    assert params["solver_version"] == "3.5.6"
    assert params["psse_version"] is None
    result_calls = [c for c in conn.calls if c[0] in set(contract.INSERT_RESULT_SQL.values())]
    assert result_calls, "the result rows follow the run row"
    assert all(c[1]["run_id"] == params["run_id"] for c in result_calls)

    # The same study through the default solver stays on the 17-column PSS/E insert.
    default_conn = _RecordingConnection()
    default = _run(_psse_study, default_conn)
    assert default.status == "written", default
    plain = [c for c in default_conn.calls if c[0] == contract.INSERT_RUN_SQL]
    assert len(plain) == 1
    assert [c for c in default_conn.calls if c[0] == contract.INSERT_RUN_TAGGED_SQL] == []
    assert tuple(plain[0][1]) == contract.PSSE_RUN_COLUMNS
    assert PSSE_ID.match(plain[0][1]["run_id"]), plain[0][1]["run_id"]


# --------------------------------------------------------------------------- the writer


class _ForbiddenConnection(object):
    """A connection that fails the test when anything is executed on it."""

    def execute(self, *args, **kwargs):
        raise AssertionError("nothing may be executed")

    def transaction(self, *args, **kwargs):
        raise AssertionError("no transaction may be opened")


class _FailsOnDispatchInsert(_RecordingConnection):
    """Records like the recording connection but raises on the first dispatch insert."""

    def execute(self, sql, params=None):
        if sql == contract.INSERT_RESULT_SQL[contract.DISPATCH_TABLE]:
            raise RuntimeError("injected failure")
        return _RecordingConnection.execute(self, sql, params)


def _ok_record(solver=None, solver_version="3.5.6"):
    """(record, rows) of an ok run for the default solver, or for the registered `solver`."""
    selection = ratings.select_ratings(_fetch(), NOW)
    tag = contract.SOLVER_PSSE if solver is None else solver
    prefix = contract.RUN_ID_PREFIXES[tag]
    context = contract.RunContext(
        "%s-20261118T140730Z-0123abcd" % prefix, NOW, "CASE", None, None, "t", tag)
    results = psse_fakes.fake_results(selection)
    if solver is not None:
        results = results._replace(solver=solver, solver_version=solver_version, psse_version=None)
    record = run_record.build_run_record(context, selection, LATER, results=results)
    return record, run_record.result_rows(record, results)


def _write_both_ways(record, rows):
    """Run write_run on the record and record_failure on its failed copy; yield the errors."""
    failed = run_record.as_failed(record, "write", "x")
    for call in (lambda: writer.write_run(_ForbiddenConnection(), record, rows),
                 lambda: writer.record_failure(_ForbiddenConnection(), failed)):
        try:
            call()
        except ValueError as exc:
            yield str(exc)
        else:
            raise AssertionError("the writer accepted a record it must refuse")


def test_writer_refuses_a_mismatched_tag_before_any_statement(monkeypatch):
    _register(monkeypatch)
    cases = []

    record, rows = _ok_record()
    wrong_id = dict(record, run_id="pp-20261118T140730Z-0123abcd")
    cases.append((wrong_id, rows))

    record, rows = _ok_record(SECOND_SOLVER)
    cases.append((dict(record, solver=contract.SOLVER_PSSE, run_id="psse-20261118T140730Z-0123abcd"), rows))
    no_version = dict(record)
    del no_version["solver_version"]
    cases.append((no_version, rows))
    no_solver = dict(record)
    del no_solver["solver"]
    cases.append((no_solver, rows))
    cases.append((dict(record, solver="zz-unregistered"), rows))
    cases.append((dict(record, run_id="psse-20261118T140730Z-0123abcd"), rows))
    for bad_version in (7, "", "v" * 101):
        cases.append((dict(record, solver_version=bad_version), rows))

    for bad, bad_rows in cases:
        for message in _write_both_ways(bad, bad_rows):
            assert bad["run_id"] not in message, message
            assert "zz-unregistered" not in message, message
            assert SECOND_SOLVER not in message, message
            assert "v" * 101 not in message, message


def test_writer_accepts_a_100_character_solver_version_and_none(monkeypatch):
    _register(monkeypatch)
    for version in ("v" * 100, None):
        record, rows = _ok_record(SECOND_SOLVER, solver_version=version)
        conn = _RecordingConnection()
        assert writer.write_run(conn, record, rows) == writer.WRITTEN
        assert conn.calls[0][0] == contract.INSERT_RUN_TAGGED_SQL
        assert conn.calls[0][1]["solver_version"] == version


def test_tagged_write_failure_records_a_tagged_failed_run(monkeypatch):
    _register(monkeypatch)
    record, rows = _ok_record(SECOND_SOLVER)
    conn = _FailsOnDispatchInsert()
    try:
        writer.write_run(conn, record, rows)
    except writer.WriteFailed:
        pass
    else:
        raise AssertionError("the injected failure must raise WriteFailed")
    run_calls = [c for c in conn.calls if c[0] in (contract.INSERT_RUN_SQL, contract.INSERT_RUN_TAGGED_SQL)]
    assert [c[0] for c in run_calls] == [contract.INSERT_RUN_TAGGED_SQL] * 2
    stored = run_calls[-1][1]
    assert stored["outcome"] == "failed"
    assert stored["failed_stage"] == "write"
    assert stored["solver"] == SECOND_SOLVER
    assert stored["solver_version"] == "3.5.6"
    assert stored["run_id"] == record["run_id"]


def test_tagged_record_failure_uses_the_tagged_insert(monkeypatch):
    _register(monkeypatch)
    record, _rows = _ok_record(SECOND_SOLVER)
    failed = run_record.as_failed(record, "mapping", "refused")
    conn = _RecordingConnection()
    assert writer.record_failure(conn, failed) == writer.WRITTEN
    assert [c[0] for c in conn.calls] == [contract.INSERT_RUN_TAGGED_SQL]
    assert conn.calls[0][1]["solver"] == SECOND_SOLVER


def test_insert_texts():
    conflict = "on conflict (run_id) do nothing returning run_id"
    assert contract.INSERT_RUN_SQL == contract.insert_sql(contract.PSSE_RUN_TABLE, conflict)
    expected = contract.INSERT_RUN_SQL.replace(
        "psse_version)", "psse_version, solver, solver_version)", 1).replace(
        "%(psse_version)s)", "%(psse_version)s, %(solver)s, %(solver_version)s)", 1)
    assert contract.INSERT_RUN_TAGGED_SQL == expected
    assert contract.INSERT_RUN_TAGGED_SQL != contract.INSERT_RUN_SQL
    assert contract.INSERT_RUN_SQL.endswith(conflict)
    assert contract.INSERT_RUN_TAGGED_SQL.endswith(conflict)
    for table in contract.RESULT_TABLES:
        assert contract.INSERT_RESULT_SQL[table] == contract.insert_sql(table, "", None)
