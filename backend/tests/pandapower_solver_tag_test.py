"""
DB-02, pandapower half (pandapower-solver Phase 3, plan 03-04, decisions D-04, D-05, D-07): the
pandapower engine's runs carry their solver tag end to end.

What is proven, by tier:

  recording connection (`test_tracer_*`, `test_refused_*`) run everywhere pandapower is installed:
        a real four-city study, prepared by `engine.prepare_run` and run through the unchanged
        `job.run_once(solver=engine.SOLVER)`, reaches the writer as one `pp-` run tagged
        `pandapower` with the installed pandapower version and a NULL `psse_version`; the same
        study run with the default tag is never stored as PSS/E results; a refused preflight is
        stored tagged. The connection only records the statements it is given.
  parity (`test_parity_*`) run everywhere pandapower is installed:
        the Python tag vocabulary and the run ids the job builds equal what the solver-tag
        migration's check constraints accept, so the job never builds a run the database refuses.
  database (`test_db_*`) the real writer as `dlr_psse_writer` on a throwaway local Postgres with
        the solver-tag migration applied. They are SKIPPED unless `DLR_TEST_PG_AUTOSTART=1` or a
        local `DLR_TEST_DATABASE_URL` is set, and FAIL under `PSSE_REQUIRE_PG=1` when no database
        is available. A skip proves nothing about the database.

They never touch Supabase: the ratings come from a fake fetch, the writer role is the local
cluster's own, and no live host is named in this file. The case is the public 39-bus fixture, so
these tests do not prove engineering agreement with PSS/E.

Follows backend/tests/pandapower_study_job_test.py (module-level imports, plain asserts, no classes).
"""

import contextlib
import datetime
import os
import re
import sys
import tempfile

import pytest

pandapower = pytest.importorskip("pandapower")

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import pandapower_study_fixture as study_fixture  # noqa: E402
import psse_fakes  # noqa: E402
from pandapower_job import api, engine  # noqa: E402
from psse_job import contract, job, run_record  # noqa: E402

STARTED = datetime.datetime(2026, 10, 28, 14, 7, 30, tzinfo=datetime.timezone.utc)
_PP_RUN_ID = re.compile(r"^pp-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


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


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _clock(*offsets):
    """A clock returning STARTED plus each offset (a timedelta) in turn, then the last one again."""
    values = [STARTED + offset for offset in offsets]
    state = {"i": 0}

    def clock():
        value = values[min(state["i"], len(values) - 1)]
        state["i"] += 1
        return value

    return clock


def _rows(provisional=True):
    return psse_fakes.latest_rows(STARTED, provisional=provisional)


def _prepared(tmp_path, study=None):
    """The fixture case and the placeholder mapping (with `study` overrides) written into tmp_path,
    then engine.prepare_run on them. Returns the study.PreparedRun."""
    case_path = study_fixture.write_case(tmp_path)
    mapping_path = study_fixture.write_placeholder_mapping(tmp_path, study=study)
    return engine.prepare_run(engine.PLACEHOLDER_BACKEND, case_path, mapping_path,
                              allow_placeholder=True)


def _run_recorded(prepared, **extra):
    """job.run_once through prepared.study into a recording connection. Returns (outcome, conn)."""
    conn = _RecordingConnection()
    outcome = job.run_once(
        fetch=psse_fakes.fake_fetch(_rows()),
        study=prepared.study,
        connect=lambda: conn,
        case_id=prepared.case_id,
        case_sha256=prepared.case_sha256,
        mapping_sha256=prepared.mapping_sha256,
        clock=_clock(datetime.timedelta(0), datetime.timedelta(minutes=4)),
        env={"PSSE_JOB_VERSION": "test-version"},
        **extra
    )
    return outcome, conn


def _calls_with(conn, sql):
    return [params for call_sql, params in conn.calls if call_sql == sql]


# --------------------------------------------------------------------------- tracer


def test_tracer_engine_run_is_written_tagged(tmp_path, _private_temp):
    prepared = _prepared(tmp_path)
    outcome, conn = _run_recorded(prepared, solver=engine.SOLVER)

    assert outcome.status == "written"
    assert outcome.exit_code == 0
    assert outcome.failed_stage is None
    assert outcome.outcome == "fallback"

    tagged = _calls_with(conn, contract.INSERT_RUN_TAGGED_SQL)
    assert len(tagged) == 1
    assert _calls_with(conn, contract.INSERT_RUN_SQL) == []
    params = tagged[0]
    assert _PP_RUN_ID.fullmatch(params["run_id"]), params["run_id"]
    assert params["run_id"] == outcome.run_id
    assert params["solver"] == "pandapower"
    assert params["solver_version"] == pandapower.__version__
    assert params["psse_version"] is None

    dispatch = _calls_with(conn, contract.INSERT_RESULT_SQL[contract.DISPATCH_TABLE])
    assert len(dispatch) == 4
    assert all(row["run_id"] == outcome.run_id for row in dispatch)
    assert os.listdir(str(_private_temp)) == []
