"""
TST-01 write-back proofs of the whole PSS/E study (pss-e-integration Phase 2, plan 02-06): the
real study (psse_job.study.prepare_run), driven by the fake psspy, goes through Phase 1's
unchanged `job.run_once` and the real writer into a throwaway local Postgres. A converged run
writes 1 + 4 + 4 + N rows with every completeness check ok; every way the study can fail
(mapping, load case, load flow, N-1 cap, margin) leaves exactly one failed run row and no
result rows (ROADMAP Phase 2 criteria 1 to 4).

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's
tmp dir and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway
database (host 127.0.0.1, localhost or ::1; anything else fails the test). With
`PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping. They
never touch Supabase.

Honest scope: these tests prove arithmetic, control flow, failure handling and row shape
against a fake; they do not prove that the units or margins make engineering sense on Power
Systems' network (the Phase 3 probe and real run check the engine).

Follows backend/tests/psse_job_test.py (module-level imports, plain asserts, no test classes).
"""

import copy
import datetime
import functools
import json
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
import psse_fakes  # noqa: E402
import psse_local_pg as pg_helper  # noqa: E402
from psse_job import constants, job, run_record, study, writer  # noqa: E402

WRITER_ROLE = "dlr_psse_writer"
STARTED = datetime.datetime(2026, 10, 28, 14, 7, 30, tzinfo=datetime.timezone.utc)
EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a database that already carries the Phase 4 migrations and the reference DDL."""
    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_schema(admin_url)
        yield admin_url


@pytest.fixture
def clean_pg(pg):
    """The same database with the four result tables empty."""
    pg_helper.reset(pg)
    return pg


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


def _connect(admin_url):
    return functools.partial(writer.connect, pg_helper.role_url(admin_url, WRITER_ROLE))


def _counts(admin_url, run_id):
    """(psse_run, dispatch, margin, contingency) row counts for `run_id`, read as the superuser."""
    return [
        pg_helper.admin_rows(
            admin_url, "select count(*) as n from public." + table + " where run_id = %s", (run_id,)
        )[0]["n"]
        for table in pg_helper.RESULT_TABLES
    ]


def _run_row(admin_url, run_id):
    rows = pg_helper.admin_rows(admin_url, "select * from public.psse_run where run_id = %s", (run_id,))
    return rows[0] if rows else None


def _table_rows(admin_url, table, run_id):
    return pg_helper.admin_rows(
        admin_url, "select * from public." + table + " where run_id = %s order by 1, 2, 3, 4",
        (run_id,))


def _checks(admin_url):
    return pg_helper.admin_rows(admin_url, pg_helper._read(pg_helper.CHECKS_SQL))


def _rows(provisional=True):
    return psse_fakes.latest_rows(STARTED, provisional=provisional)


def _registered(tmp_path, case=None, solver=None, fake=None):
    """(fake, case path): the case registered under a path whose file holds a marker."""
    fake = fake_module.FakePsspy(solver=solver) if fake is None else fake
    path = str(tmp_path / "PLACEHOLDER_CASE.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(path, fake_module.placeholder_case() if case is None else case)
    return fake, path


def _run(admin_url, prepared, rows=None, fetch=None):
    """run_once through prepared.study; defaults: today's provisional rows, a 4-minute clock."""
    return job.run_once(
        fetch=psse_fakes.fake_fetch(_rows() if rows is None else rows) if fetch is None else fetch,
        study=prepared.study,
        connect=_connect(admin_url),
        case_id=prepared.case_id,
        case_sha256=prepared.case_sha256,
        mapping_sha256=prepared.mapping_sha256,
        clock=_clock(datetime.timedelta(0), datetime.timedelta(minutes=4)),
        env={"PSSE_JOB_VERSION": "test-version"},
    )


def test_tracer_prepare_run_fake_psspy_to_postgres(clean_pg, tmp_path):
    """The real study with the fake psspy through run_once into Postgres: one complete fallback run."""
    fake, path = _registered(tmp_path)
    case_hash = run_record.file_sha256(path)
    prepared = study.prepare_run(fake, path, EXAMPLE, allow_placeholder=True)
    assert prepared.case_id == "PLACEHOLDER_CASE.sav"
    assert prepared.case_sha256 == case_hash
    assert prepared.mapping_sha256 == run_record.file_sha256(EXAMPLE)
    assert prepared.mapping_error is None

    outcome = _run(clean_pg, prepared, rows=_rows(provisional=True))
    assert outcome.outcome == "fallback"
    assert outcome.status == "written"
    assert outcome.failed_stage is None
    assert outcome.exit_code == 0

    assert _counts(clean_pg, outcome.run_id) == [1, 4, 4, 10]
    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["rate_set"] == "RATEA"
    assert stored["psse_version"] == "35.6.0"
    assert stored["n_contingencies"] == 16
    assert stored["n_contingencies_with_results"] == 7
    assert stored["case_sha256"] == case_hash
    assert stored["mapping_sha256"] == run_record.file_sha256(EXAMPLE)
    austin = stored["ratings_used"]["AUSTIN"]
    assert austin["line_voltage_kv"] == 345.0
    assert round(austin["rating_mva"], 1) == 2181.1

    dispatch = dict((row["city"], row) for row in
                    _table_rows(clean_pg, "psse_dispatched_capacity", outcome.run_id))
    assert dispatch["AUSTIN"]["limiting_factor"] == "voltage_stability"
    assert dispatch["EL_PASO"]["limiting_factor"] == "dlr_rating"
    assert [row["rating_source"] for row in dispatch.values()] == ["static_fallback"] * 4
    margins = _table_rows(clean_pg, "psse_voltage_margin", outcome.run_id)
    assert [row["method"] for row in margins] == ["pv_curve"] * 4
    kinds = set(row["violation_kind"] for row in
                _table_rows(clean_pg, "psse_contingency_result", outcome.run_id))
    assert {"thermal_overload", "voltage_low"} <= kinds

    problems = [row for row in _checks(clean_pg) if not row["ok"]]
    assert problems == [], problems
    assert run_record.file_sha256(path) == case_hash
    assert fake.fake_saved_paths
    assert not any(os.path.exists(saved) for saved in fake.fake_saved_paths)
