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
