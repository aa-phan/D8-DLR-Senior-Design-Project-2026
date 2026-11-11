"""
Phase 4 Nyquist audit additions (SCL-04, SCL-05), no database needed.

The Postgres-backed tests prove the same two behaviours against a real database; these prove them
on the whole path (real study, fake psspy, job.run_once, real writer) with a recording connection,
so they run in the quick suite:

- a refused scaling of one city still writes NO result row for any city (only the one failed run
  row), and the stored error names every city (SCL-04);
- a converged run's log lines and every parameter handed to the database hold none of the eight
  synthetic scaling targets, in any text form (SCL-05, the success path; the failure path is
  pinned in psse_study_job_test.py).

Only synthetic targets appear here; no real city figure belongs in a public repository.
"""

import contextlib
import datetime
import json
import logging
import os
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
import psse_fakes  # noqa: E402
from psse_job import contract, job, study  # noqa: E402

EXAMPLE = os.path.abspath(os.path.join(
    _HERE, "..", "..", "docs", "data-science", "schema", "psse_mapping_example.json"))
STARTED = datetime.datetime(2026, 10, 28, 14, 7, 30, tzinfo=datetime.timezone.utc)
TARGETS = (2430.5, 2467.25, 2455.75, 2492.5, 2504.25, 2541.75, 2529.5, 2566.25)


def _figure_texts():
    texts = set()
    for value in TARGETS:
        texts.update((repr(value), "%g" % value, "%.1f" % value))
    return sorted(texts)


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


class _RefusesOneCityScale(fake_module.FakePsspy):
    def __init__(self, refused_load, **kwargs):
        super().__init__(**kwargs)
        self._refused_load = refused_load

    def scal_2(self, sid, all, apiopt, status, scalval):  # noqa: A002 - the manual's name
        if all == 1 and apiopt == 0 and scalval[0] == self._refused_load:
            return (6, [], [])
        return super().scal_2(sid=sid, all=all, apiopt=apiopt, status=status, scalval=scalval)


def _run(tmp_path, fake):
    path = str(tmp_path / "PLACEHOLDER_CASE.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER")
    fake.fake_register_case(path, fake_module.placeholder_case())
    prepared = study.prepare_run(fake, path, EXAMPLE, allow_placeholder=True)
    conn = _RecordingConnection()
    clock_values = iter([STARTED, STARTED + datetime.timedelta(minutes=4)])
    outcome = job.run_once(
        fetch=psse_fakes.fake_fetch(psse_fakes.latest_rows(STARTED, provisional=True)),
        study=prepared.study,
        connect=lambda: conn,
        case_id=prepared.case_id,
        case_sha256=prepared.case_sha256,
        mapping_sha256=prepared.mapping_sha256,
        clock=lambda: next(clock_values, STARTED + datetime.timedelta(minutes=4)),
        env={"PSSE_JOB_VERSION": "test-version"},
    )
    return outcome, conn


def _result_inserts(conn):
    result_sql = set(contract.INSERT_RESULT_SQL.values())
    return [call for call in conn.calls if call[0] in result_sql]


def test_one_refused_city_writes_no_result_row_for_any_city(tmp_path):
    outcome, conn = _run(tmp_path, _RefusesOneCityScale(2455.75))

    assert outcome.outcome == "failed"
    assert outcome.failed_stage == "apply_ratings"
    assert _result_inserts(conn) == []
    run_inserts = [call for call in conn.calls if call[0] == contract.INSERT_RUN_SQL]
    assert len(run_inserts) == 1
    error = run_inserts[0][1]["error"]
    assert error.startswith("1 of 4 cities failed; "), error
    for city in ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"):
        assert city + ": " in error, error
    for text in _figure_texts():
        assert text not in json.dumps(conn.calls, default=str), text


def test_converged_run_logs_and_stores_no_scaling_figure(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    outcome, conn = _run(tmp_path, fake_module.FakePsspy())

    assert outcome.status == "written", outcome
    assert _result_inserts(conn), "a converged run must write result rows"
    stored = json.dumps(conn.calls, default=str)
    for text in _figure_texts():
        assert text not in stored, text
        assert text not in caplog.text, text
