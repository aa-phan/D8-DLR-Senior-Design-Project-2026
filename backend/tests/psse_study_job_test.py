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
import math
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


# --------------------------------------------------------------------------- helpers


def _mapping_copy(tmp_path, edit=None, name="mapping.json"):
    """A temp copy of the example mapping (placeholder true) after `edit(data)`; returns its path."""
    with open(EXAMPLE, encoding="utf-8") as handle:
        data = copy.deepcopy(json.load(handle))
    if edit is not None:
        edit(data)
    path = str(tmp_path / name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    return path


def _prepare(fake, path, mapping_path=EXAMPLE, allow_placeholder=True):
    return study.prepare_run(fake, path, mapping_path, allow_placeholder=allow_placeholder)


def _seen(fake, *names):
    return [call[0] for call in fake.fake_calls if call[0] in names]


def _assert_failed(admin_url, outcome, stage, fragment, case_path=None, case_hash=None):
    """One failed psse_run row with `stage`, no result rows, exit 1, the case file untouched."""
    assert outcome.outcome == "failed"
    assert outcome.failed_stage == stage
    assert outcome.status == "failure_recorded"
    assert outcome.exit_code == 1
    assert _counts(admin_url, outcome.run_id) == [1, 0, 0, 0]
    stored = _run_row(admin_url, outcome.run_id)
    assert stored["outcome"] == "failed"
    assert stored["failed_stage"] == stage
    assert fragment in stored["error"], stored["error"]
    assert [row for row in _checks(admin_url) if not row["ok"]] == []
    if case_path is not None:
        assert run_record.file_sha256(case_path) == case_hash
    return stored


def _failed_run(admin_url, tmp_path, mapping_path=EXAMPLE, case=None, solver=None, rows=None,
                allow_placeholder=True):
    """Prepare and run once; returns (fake, case path, case hash, outcome)."""
    fake, path = _registered(tmp_path, case=case, solver=solver)
    case_hash = run_record.file_sha256(path)
    prepared = _prepare(fake, path, mapping_path, allow_placeholder)
    outcome = _run(admin_url, prepared, rows=rows)
    return fake, path, case_hash, outcome


def _flat_solver(case):
    """The radial solver on a case whose loads are frozen: extra sink load never changes anything."""
    frozen = copy.deepcopy(case)
    for bus in frozen.loads:
        frozen.loads[bus] = [620.0, 620.0 * math.tan(math.acos(0.95))]
    return fake_module.radial_solver(frozen)


# --------------------------------------------------------------------------- recorded failures


def test_recorded_mapping_missing_branch(clean_pg, tmp_path):
    """A mapped branch the case does not have: stage mapping, nothing written to the case, no results."""
    def edit(data):
        data["cities"]["AUSTIN"]["branches"] = [{"from_bus": 90001, "to_bus": 90099, "ckt": "1"}]

    mapping_path = _mapping_copy(tmp_path, edit)
    fake, path, case_hash, outcome = _failed_run(clean_pg, tmp_path, mapping_path)
    stored = _assert_failed(clean_pg, outcome, "mapping", "not in the case", path, case_hash)
    assert "90001-90099-1" in stored["error"]
    assert stored["mapping_sha256"] == run_record.file_sha256(mapping_path)
    assert stored["case_sha256"] == case_hash
    assert _seen(fake, "branch_chng_3", "fnsl", "save") == []


def test_recorded_non_converging_load_flow(clean_pg, tmp_path):
    """A base load flow that stops at its iteration limit is a recorded failure, never results."""
    solver = lambda case: fake_module.SolveOutcome(ierr=0, solved=1)  # noqa: E731
    fake, path, case_hash, outcome = _failed_run(clean_pg, tmp_path, solver=solver)
    stored = _assert_failed(clean_pg, outcome, "load_flow", "did not converge", path, case_hash)
    assert "iteration limit exceeded" in stored["error"]
    assert _seen(fake, "save") == []
    assert fake.fake_saved_paths == []


def test_recorded_placeholder_refused(clean_pg, tmp_path):
    """The placeholder example without allow_placeholder: stage mapping, mapping hash NULL, no psspy call."""
    fake, path = _registered(tmp_path)
    case_hash = run_record.file_sha256(path)
    prepared = _prepare(fake, path, EXAMPLE, allow_placeholder=False)
    assert prepared.mapping_sha256 is None
    assert "placeholder" in prepared.mapping_error
    outcome = _run(clean_pg, prepared)
    stored = _assert_failed(clean_pg, outcome, "mapping", "placeholder", path, case_hash)
    assert stored["mapping_sha256"] is None
    assert stored["case_sha256"] == case_hash
    assert fake.fake_calls == []


def test_recorded_unreadable_mapping(clean_pg, tmp_path):
    """A mapping path that does not exist is the same recorded failure, with mapping hash NULL."""
    fake, path = _registered(tmp_path)
    case_hash = run_record.file_sha256(path)
    missing = str(tmp_path / "private_dir" / "no_such_mapping.json")
    prepared = _prepare(fake, path, missing)
    assert prepared.mapping_sha256 is None
    outcome = _run(clean_pg, prepared)
    stored = _assert_failed(clean_pg, outcome, "mapping", "mapping file not usable", path, case_hash)
    assert "no_such_mapping.json" in stored["error"]
    assert "private_dir" not in stored["error"]
    assert stored["mapping_sha256"] is None
    assert fake.fake_calls == []


def test_recorded_case_not_loadable(clean_pg, tmp_path):
    """A case file the fake cannot load: stage load_case, the error names the base name only."""
    fake = fake_module.FakePsspy()
    path = str(tmp_path / "private_dir" / "missing_case.sav")
    prepared = _prepare(fake, path)
    assert prepared.case_id == "missing_case.sav"
    assert prepared.case_sha256 is None
    outcome = _run(clean_pg, prepared)
    stored = _assert_failed(clean_pg, outcome, "load_case", "missing_case.sav")
    assert "private_dir" not in stored["error"]
    assert str(tmp_path) not in stored["error"]
    assert _seen(fake, "branch_chng_3", "fnsl", "save") == []


def test_recorded_contingency_cap(clean_pg, tmp_path):
    """More outages than study.contingency.max: stage contingency, no truncated screen is written."""
    def edit(data):
        data["study"] = {"contingency": {"max": 3}}

    fake, path, case_hash, outcome = _failed_run(clean_pg, tmp_path, _mapping_copy(tmp_path, edit))
    _assert_failed(clean_pg, outcome, "contingency", "exceed contingency.max 3", path, case_hash)


def test_recorded_flat_transfer(clean_pg, tmp_path):
    """A solver that ignores the extra sink load gives no margin: stage voltage_margin, no rows."""
    def edit(data):
        data["study"] = {"transfer": {"extra_steps": 3}}

    fake, path, case_hash, outcome = _failed_run(
        clean_pg, tmp_path, _mapping_copy(tmp_path, edit), solver=_flat_solver)
    _assert_failed(clean_pg, outcome, "voltage_margin", "does not load the mapped branches", path,
                   case_hash)


def test_recorded_transfer_not_bounded(clean_pg, tmp_path):
    """A fresh EL_PASO rating that the search never bounds inside the starting cap and zero extra steps."""
    def edit(data):
        data["study"] = {"transfer": {"extra_steps": 0}}

    fake, path, case_hash, outcome = _failed_run(
        clean_pg, tmp_path, _mapping_copy(tmp_path, edit), rows=_rows(provisional=False))
    stored = _assert_failed(clean_pg, outcome, "voltage_margin", "transfer.max_mw", path, case_hash)
    assert "transfer.extra_steps" in stored["error"]
    assert "EL_PASO" in stored["error"]


# --------------------------------------------------------------------------- written runs


def test_written_fresh_rows_are_ok_with_link(clean_pg, tmp_path):
    """Fresh rows: an ok run linked to the city_rating rows; EL_PASO dispatched in full as dlr_rating."""
    fake, path = _registered(tmp_path)
    case_hash = run_record.file_sha256(path)
    rows = _rows(provisional=False)
    outcome = _run(clean_pg, _prepare(fake, path), rows=rows)
    assert (outcome.outcome, outcome.status, outcome.exit_code) == ("ok", "written", 0)
    assert _counts(clean_pg, outcome.run_id) == [1, 4, 4, 10]

    valid = STARTED - datetime.timedelta(minutes=10)
    dispatch = dict((row["city"], row) for row in
                    _table_rows(clean_pg, "psse_dispatched_capacity", outcome.run_id))
    for city in constants.CITIES:
        row = dispatch[city]
        static = constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city]
        assert row["rating_source"] == "city_rating"
        assert row["fallback_reason"] is None
        assert row["city_rating_valid_time"] == valid
        assert row["city_rating_computed_at"] == valid + datetime.timedelta(minutes=6)
        assert row["applied_amps_per_conductor"] == pytest.approx(1.1 * static)
    el_paso = dispatch["EL_PASO"]
    assert el_paso["applied_mva"] == pytest.approx(867.65, abs=0.01)
    assert el_paso["dispatched_mva"] == el_paso["applied_mva"]
    assert el_paso["limiting_factor"] == "dlr_rating"
    assert dispatch["AUSTIN"]["limiting_factor"] == "voltage_stability"
    margins = dict((row["city"], row) for row in
                   _table_rows(clean_pg, "psse_voltage_margin", outcome.run_id))
    assert margins["EL_PASO"]["details"]["bounded_by"] == "dlr_rating"
    assert margins["EL_PASO"]["details"]["extended_past_cap"] is True
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []
    assert run_record.file_sha256(path) == case_hash


def test_written_static_fallback_records_reason(clean_pg, tmp_path):
    """Today's provisional rows: every city static_fallback / provisional in the dispatch rows and ratings_used."""
    fake, path = _registered(tmp_path)
    outcome = _run(clean_pg, _prepare(fake, path), rows=_rows(provisional=True))
    assert (outcome.outcome, outcome.status, outcome.exit_code) == ("fallback", "written", 0)
    assert _counts(clean_pg, outcome.run_id) == [1, 4, 4, 10]
    dispatch = _table_rows(clean_pg, "psse_dispatched_capacity", outcome.run_id)
    assert [(row["rating_source"], row["fallback_reason"]) for row in dispatch] == [
        ("static_fallback", "provisional")] * 4
    assert all(row["city_rating_valid_time"] is None for row in dispatch)
    stored = _run_row(clean_pg, outcome.run_id)
    assert [(stored["ratings_used"][city]["source"], stored["ratings_used"][city]["fallback_reason"])
            for city in constants.CITIES] == [("static_fallback", "provisional")] * 4
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []


def test_written_read_failure_still_studies_static(clean_pg, tmp_path):
    """A failed ratings read: the study still runs on static ratings, four read_failed cities, fallback."""
    def broken():
        raise RuntimeError("ratings read failed in test")

    fake, path = _registered(tmp_path)
    outcome = _run(clean_pg, _prepare(fake, path), fetch=broken)
    assert (outcome.outcome, outcome.status, outcome.exit_code) == ("fallback", "written", 0)
    assert _counts(clean_pg, outcome.run_id) == [1, 4, 4, 10]
    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["ratings_read_error"]
    assert [(stored["ratings_used"][city]["source"], stored["ratings_used"][city]["fallback_reason"])
            for city in constants.CITIES] == [("static_fallback", "read_failed")] * 4
    dispatch = _table_rows(clean_pg, "psse_dispatched_capacity", outcome.run_id)
    assert [row["fallback_reason"] for row in dispatch] == ["read_failed"] * 4
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []


def test_written_zero_violations_complete(clean_pg, tmp_path):
    """200 MW sink loads: no violation rows is a complete run (1 + 4 + 4 + 0), EL_PASO still dlr_rating."""
    case = fake_module.placeholder_case()
    for sink in case.loads:
        case.loads[sink] = [200.0, 200.0 * math.tan(math.acos(0.95))]
    fake, path = _registered(tmp_path, case=case)
    outcome = _run(clean_pg, _prepare(fake, path), rows=_rows(provisional=True))
    assert (outcome.outcome, outcome.status, outcome.exit_code) == ("fallback", "written", 0)
    assert _counts(clean_pg, outcome.run_id) == [1, 4, 4, 0]
    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["n_contingencies"] == 16
    assert stored["n_contingencies_with_results"] == 0
    dispatch = dict((row["city"], row) for row in
                    _table_rows(clean_pg, "psse_dispatched_capacity", outcome.run_id))
    assert dispatch["EL_PASO"]["limiting_factor"] == "dlr_rating"
    assert round(dispatch["EL_PASO"]["dispatched_mva"], 1) == 788.8
    margins = dict((row["city"], row) for row in
                   _table_rows(clean_pg, "psse_voltage_margin", outcome.run_id))
    assert margins["EL_PASO"]["details"]["extended_past_cap"] is True
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []
