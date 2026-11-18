"""
ENG-06 database tier of the pandapower study (pandapower-solver Phase 2, plan 02-06): the full
four-city pandapower study, prepared by `engine.prepare_run`, goes through Phase 1's unchanged
`job.run_once` and the real writer into a throwaway local Postgres, exactly as
`psse_study_job_test.py` does for PSS/E. A converged run writes 1 + 4 + 4 + N rows with every
completeness check ok; a refused preflight, a refused one-city scaling and an islanding outage are
stored the way the PSS/E job stores them.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's tmp
dir and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway database
(host 127.0.0.1, localhost or ::1; anything else fails the test). With `PSSE_REQUIRE_PG=1` a
missing database, driver or binary fails instead of skipping. They never touch Supabase: the
ratings come from a fake fetch, the writer role is the local cluster's own, and no live host is
named in this file.

Honest scope: these tests prove that the pandapower run flows through the unchanged job and writer
and stores valid rows on the public 39-bus fixture. They do not prove engineering agreement with
PSS/E, and they assert nothing about a `solver` or `solver_version` column (Phase 3 owns that
schema change, so these tests still pass after its migration and can be extended there). Until that
migration exists the run id carries the `psse-` prefix, which is one more reason these tests write
only to a throwaway local database.

Only `test_prepared_run_is_ready_for_the_writer` needs no database. The in-memory tier of ENG-06 is
`pandapower_engine_test.py` and always runs.

Follows backend/tests/psse_study_job_test.py (module-level imports, plain asserts, no test classes).
"""

import datetime
import functools
import json
import logging
import os
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
import psse_local_pg as pg_helper  # noqa: E402
from pandapower_job import engine  # noqa: E402
from psse_job import job, run_record, writer  # noqa: E402

WRITER_ROLE = "dlr_psse_writer"
STARTED = datetime.datetime(2026, 10, 28, 14, 7, 30, tzinfo=datetime.timezone.utc)


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


def _prepared(tmp_path, study=None, backend=None):
    """The fixture case and the placeholder mapping (with `study` overrides) written into tmp_path,
    then engine.prepare_run on them. Returns the study.PreparedRun."""
    case_path = study_fixture.write_case(tmp_path)
    mapping_path = study_fixture.write_placeholder_mapping(tmp_path, study=study)
    return engine.prepare_run(engine.PLACEHOLDER_BACKEND if backend is None else backend,
                              case_path, mapping_path, allow_placeholder=True)


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


def test_prepared_run_is_ready_for_the_writer(tmp_path):
    """No database and no study run: the PreparedRun carries what run_once passes to the writer."""
    case_path = study_fixture.write_case(tmp_path)
    mapping_path = study_fixture.write_placeholder_mapping(tmp_path)
    prepared = engine.prepare_run(engine.PLACEHOLDER_BACKEND, case_path, mapping_path,
                                  allow_placeholder=True)
    assert prepared.case_id == "CASE39_FIXTURE.raw"
    assert prepared.case_sha256 == run_record.file_sha256(case_path)
    assert prepared.mapping_sha256 == run_record.file_sha256(mapping_path)
    assert prepared.mapping_error is None


def test_tracer_engine_run_written_to_local_postgres(clean_pg, tmp_path):
    """A full four-city pandapower run through engine.prepare_run, the unchanged job.run_once and the
    real writer: one complete fallback run, every completeness check ok."""
    case_path = study_fixture.write_case(tmp_path)
    mapping_path = study_fixture.write_placeholder_mapping(tmp_path)
    case_hash = run_record.file_sha256(case_path)
    prepared = engine.prepare_run(engine.PLACEHOLDER_BACKEND, case_path, mapping_path,
                                  allow_placeholder=True)

    outcome = _run(clean_pg, prepared)
    assert outcome.status == "written"
    assert outcome.exit_code == 0
    assert outcome.failed_stage is None
    assert outcome.outcome == "fallback"

    counts = _counts(clean_pg, outcome.run_id)
    assert counts[:3] == [1, 4, 4]
    assert counts[3] >= 1

    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["psse_version"] is None
    assert stored["case_sha256"] == case_hash
    assert stored["mapping_sha256"] == run_record.file_sha256(mapping_path)
    assert stored["rate_set"] == "RATEA"
    contingency_rows = _table_rows(clean_pg, "psse_contingency_result", outcome.run_id)
    assert stored["n_contingencies_with_results"] == len(
        set(row["contingency_id"] for row in contingency_rows))

    dispatch = _table_rows(clean_pg, "psse_dispatched_capacity", outcome.run_id)
    assert len(dispatch) == 4
    for row in dispatch:
        record = row["details"]["solve_settings"]
        assert record["solver"] == "pandapower"
        assert record["placeholder"] is True

    problems = [row for row in _checks(clean_pg) if not row["ok"]]
    assert problems == [], problems
    assert os.listdir(tempfile.gettempdir()) == []
    assert run_record.file_sha256(case_path) == case_hash


# --------------------------------------------------------------------------- recorded refusals and an island


def _assert_failed(admin_url, outcome, stage):
    """One failed psse_run row with `stage`, no result rows, exit 1, every completeness check ok."""
    assert outcome.outcome == "failed"
    assert outcome.failed_stage == stage
    assert outcome.status == "failure_recorded"
    assert outcome.exit_code == 1
    assert _counts(admin_url, outcome.run_id) == [1, 0, 0, 0]
    stored = _run_row(admin_url, outcome.run_id)
    assert stored["outcome"] == "failed"
    assert stored["failed_stage"] == stage
    assert [row for row in _checks(admin_url) if not row["ok"]] == []
    return stored


def _target_texts(mapping_path):
    """Every text form (repr, %g, %.1f) of every scaling target written in the mapping file, sorted,
    so a leak of a target into a stored error or a log shows."""
    with open(mapping_path, encoding="utf-8") as handle:
        document = json.load(handle)
    texts = set()
    for city in document["cities"].values():
        for value in (city["scaling"]["load_mw"], city["scaling"]["gen_mw"]):
            texts.update((repr(value), "%g" % value, "%.1f" % value))
    return sorted(texts)


def test_recorded_preflight_refusal(clean_pg, tmp_path):
    """A thermal basis pandapower cannot reproduce: stage mapping, nothing solved, no result rows, and
    the stored mapping hash is the file's (a refused mapping keeps its hash)."""
    prepared = _prepared(tmp_path, {"thermal": {"basis": "mva"}})
    outcome = _run(clean_pg, prepared)
    stored = _assert_failed(clean_pg, outcome, "mapping")
    assert stored["error"].startswith("pandapower: "), stored["error"]
    assert stored["mapping_sha256"] == run_record.file_sha256(str(tmp_path / "mapping.json"))
    assert stored["case_sha256"] == run_record.file_sha256(str(tmp_path / "CASE39_FIXTURE.raw"))


def test_recorded_one_city_scaling_refused(clean_pg, tmp_path, caplog):
    """CORPUS_CHRISTI's load target is 25 times the case's own load, outside the scaling bounds: all four
    cities are still attempted, one failed run is stored naming each city's outcome, and no target
    value appears in the stored error or in any log line."""
    caplog.set_level(logging.INFO)
    records = study_fixture.fixture_records()
    case_path = study_fixture.write_case(tmp_path)
    mapping_path = study_fixture.write_placeholder_mapping(tmp_path)
    with open(mapping_path, encoding="utf-8") as handle:
        document = json.load(handle)
    load_total, _gen_total = study_fixture.fixture_totals(records)
    document["cities"]["CORPUS_CHRISTI"]["scaling"]["load_mw"] = 25 * load_total
    with open(mapping_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
    case_hash = run_record.file_sha256(case_path)

    prepared = engine.prepare_run(engine.PLACEHOLDER_BACKEND, case_path, mapping_path,
                                  allow_placeholder=True)
    outcome = _run(clean_pg, prepared)
    stored = _assert_failed(clean_pg, outcome, "apply_ratings")
    error = stored["error"]
    assert error.startswith("1 of 4 cities failed; AUSTIN: ok; "), error
    for fragment in ("CORPUS_CHRISTI: failed at apply_ratings: scaling:", "MIDLAND: ok",
                     "EL_PASO: ok"):
        assert fragment in error, error
    assert stored["mapping_sha256"] == run_record.file_sha256(mapping_path)
    assert run_record.file_sha256(case_path) == case_hash
    assert os.listdir(tempfile.gettempdir()) == []

    texts = _target_texts(mapping_path)
    assert texts
    for text in texts:
        assert text not in error, text
        assert text not in caplog.text, text


def test_written_island_row_is_stored(clean_pg, tmp_path):
    """An outage that islands buses is one non_convergence row per city (ierr 3), stored in a run that is
    otherwise written and complete; the screen does not stop at it."""
    island = study_fixture.ISLANDING_OUTAGE
    extra = {"from_bus": island.from_bus, "to_bus": island.to_bus, "ckt": island.ckt}
    prepared = _prepared(tmp_path, {"contingency": {"extra": [extra]}})
    outcome = _run(clean_pg, prepared)
    assert (outcome.outcome, outcome.status, outcome.exit_code) == ("fallback", "written", 0)
    assert _counts(clean_pg, outcome.run_id)[:3] == [1, 4, 4]

    rows = _table_rows(clean_pg, "psse_contingency_result", outcome.run_id)
    by_id = {}
    for row in rows:
        by_id.setdefault(row["contingency_id"], []).append(row)
    for city in ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"):
        stored = by_id.get(city + ":" + island.key)
        assert stored is not None, city
        assert len(stored) == 1, city
        assert stored[0]["violation_kind"] == "non_convergence", city
        assert stored[0]["details"]["ierr"] == 3, city
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []
