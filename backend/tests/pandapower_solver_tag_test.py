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
import functools
import json
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
import psse_local_pg as pg_helper  # noqa: E402
from pandapower_job import api, engine  # noqa: E402
from psse_job import contract, job, ratings, run_record, writer  # noqa: E402

WRITER_ROLE = "dlr_psse_writer"
STARTED = datetime.datetime(2026, 10, 28, 14, 7, 30, tzinfo=datetime.timezone.utc)
_MIGRATION = os.path.join(
    _BACKEND, "..", "supabase", "migrations", "20261118200000_psse_run_solver_tag.sql")
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


# --------------------------------------------------------------------------- parity with the migration


def _statements():
    """The migration without `--` comment lines, split on a semicolon at line end and whitespace
    normalised (letter case kept: the run id pattern has a capital T and Z), as
    solver_tag_migration_test.py reads it."""
    with open(_MIGRATION, encoding="utf-8") as handle:
        text = handle.read()
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    parts = re.split(r";[ \t]*(?:\n|$)", body)
    return [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]


def _constraint_text(name):
    found = [s for s in _statements() if "add constraint " + name in s]
    assert len(found) == 1, name
    return found[0]


def _migration_vocabulary():
    members = re.search(r"solver in \(([^)]*)\)", _constraint_text("psse_run_solver_ck"))
    assert members is not None
    return re.findall(r"'([a-z]+)'", members.group(1))


def _migration_tie():
    """{solver: prefix} named by the tie expression, the trailing dash removed."""
    expression = _constraint_text("psse_run_solver_run_id_ck")
    pairs = re.findall(r"solver = '([a-z]+)' and left\(run_id, ([0-9]+)\) = '([a-z-]+)'", expression)
    assert pairs
    for _solver, count, prefix in pairs:
        assert int(count) == len(prefix)
    return dict((solver, prefix[:-1]) for solver, _count, prefix in pairs)


def _migration_run_id_pattern():
    literals = re.findall(r"run_id ~ '([^']*)'", "\n".join(_statements()))
    assert len(literals) == 1, len(literals)
    return literals[0]


def test_parity_tag_vocabulary_equals_the_migration():
    assert api.SOLVER_NAME in contract.RUN_ID_PREFIXES  # importing the solver package registered it
    assert engine.SOLVER == api.SOLVER_NAME
    listed = _migration_vocabulary()
    assert set(contract.RUN_ID_PREFIXES) == set(listed)
    assert engine.SOLVER in listed
    assert dict(contract.RUN_ID_PREFIXES) == _migration_tie()
    assert dict(contract.RUN_ID_PREFIXES) == {"psse": "psse", "pandapower": "pp"}


def test_parity_built_run_ids_match_the_migration_pattern():
    literal = _migration_run_id_pattern()
    pattern = re.compile(literal)
    assert pattern.fullmatch(run_record.new_run_id(STARTED))
    assert pattern.fullmatch(run_record.new_run_id(STARTED, engine.SOLVER))
    alternation = re.match(r"\^\(([a-z|]+)\)-", literal)
    assert alternation is not None, "the pattern does not start with a prefix alternation"
    assert set(alternation.group(1).split("|")) == set(contract.RUN_ID_PREFIXES.values())


def test_parity_registration_is_idempotent_and_fixed():
    before = dict(contract.RUN_ID_PREFIXES)
    contract.register_solver_tag(api.SOLVER_NAME, "pp")
    assert dict(contract.RUN_ID_PREFIXES) == before
    with pytest.raises(ValueError):
        contract.register_solver_tag(api.SOLVER_NAME, "px")
    assert contract.RUN_ID_PREFIXES[api.SOLVER_NAME] == "pp"
    assert dict(contract.RUN_ID_PREFIXES) == before


# --------------------------------------------------------------------------- runs that must not be stored as PSS/E


def test_refused_default_tag_never_stores_results(tmp_path):
    """The engine's study run with the default (PSS/E) tag: its results claim another solver, so the
    run loop refuses them at validate_results and one failed psse- run with no figures is stored."""
    prepared = _prepared(tmp_path)
    outcome, conn = _run_recorded(prepared)

    assert outcome.outcome == "failed"
    assert outcome.failed_stage == "validate_results"
    assert outcome.status == "failure_recorded"
    assert outcome.exit_code == 1
    run_inserts = _calls_with(conn, contract.INSERT_RUN_SQL)
    assert len(run_inserts) == 1
    assert run_inserts[0]["outcome"] == "failed"
    assert run_inserts[0]["failed_stage"] == "validate_results"
    assert run_inserts[0]["run_id"].startswith("psse-")
    assert run_inserts[0]["run_id"] == outcome.run_id
    assert _calls_with(conn, contract.INSERT_RUN_TAGGED_SQL) == []
    result_sql = set(contract.INSERT_RESULT_SQL.values())
    assert [sql for sql, _params in conn.calls if sql in result_sql] == []
    assert len(conn.calls) == 1


def test_refused_preflight_is_stored_tagged(tmp_path):
    """A thermal basis pandapower cannot reproduce, run as a pandapower run: one failed run at stage
    mapping, stored with the tagged insert and a pp- id, no version (nothing was solved)."""
    prepared = _prepared(tmp_path, {"thermal": {"basis": "mva"}})
    outcome, conn = _run_recorded(prepared, solver=engine.SOLVER)

    assert (outcome.outcome, outcome.failed_stage, outcome.exit_code) == ("failed", "mapping", 1)
    tagged = _calls_with(conn, contract.INSERT_RUN_TAGGED_SQL)
    assert len(tagged) == 1
    assert _calls_with(conn, contract.INSERT_RUN_SQL) == []
    params = tagged[0]
    assert params["outcome"] == "failed"
    assert params["failed_stage"] == "mapping"
    assert params["solver"] == "pandapower"
    assert params["solver_version"] is None
    assert _PP_RUN_ID.fullmatch(params["run_id"]), params["run_id"]
    assert params["error"].startswith("pandapower: "), params["error"]
    assert len(conn.calls) == 1


# --------------------------------------------------------------------------- database tier (skips without Postgres)


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a throwaway database with the reference schema AND the solver-tag migration."""
    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_solver_schema(admin_url)
        yield admin_url


@pytest.fixture
def clean_pg(pg):
    """The same database with the four result tables empty."""
    pg_helper.reset(pg)
    return pg


def _connect(admin_url):
    return functools.partial(writer.connect, pg_helper.role_url(admin_url, WRITER_ROLE))


def _scalar(admin_url, sql, params=None):
    return pg_helper.admin_rows(admin_url, sql, params)[0]["n"]


def _counts(admin_url, run_id):
    """(psse_run, dispatch, margin, contingency) row counts for one run, read as the superuser."""
    return [
        _scalar(admin_url, "select count(*) as n from public." + table + " where run_id = %s", (run_id,))
        for table in pg_helper.RESULT_TABLES
    ]


def _rejected(url, sql, params, constraint):
    """Run one statement on its own connection; it must raise CheckViolation naming `constraint`."""
    import psycopg
    import psycopg.errors

    with psycopg.connect(url) as conn:
        with pytest.raises(psycopg.errors.CheckViolation) as caught:
            with conn.transaction():
                conn.execute(sql, params)
    assert caught.value.diag.constraint_name == constraint


def _bind(columns, row):
    """The bound parameters of `row` for an insert of exactly `columns`: a column the helper's row
    leaves out is NULL, a key outside `columns` fails, jsonb columns are bound as json text."""
    assert set(row) <= set(columns)
    params = {}
    for column in columns:
        value = row.get(column)
        if column in contract.JSONB_COLUMNS and value is not None:
            value = json.dumps(value)
        params[column] = value
    return params


def test_db_tagged_rehearsal_through_the_real_writer(clean_pg, tmp_path):
    """The engine's four-city study, started as a pandapower run, written by the real writer as
    dlr_psse_writer: 1 run, 4 dispatch and 4 margin rows, tagged, every completeness check ok."""
    prepared = _prepared(tmp_path)
    outcome = job.run_once(
        fetch=psse_fakes.fake_fetch(_rows()),
        study=prepared.study,
        connect=_connect(clean_pg),
        case_id=prepared.case_id,
        case_sha256=prepared.case_sha256,
        mapping_sha256=prepared.mapping_sha256,
        clock=_clock(datetime.timedelta(0), datetime.timedelta(minutes=4)),
        env={"PSSE_JOB_VERSION": "test-version"},
        solver=engine.SOLVER,
    )
    assert (outcome.status, outcome.exit_code, outcome.failed_stage) == ("written", 0, None)
    assert _PP_RUN_ID.fullmatch(outcome.run_id)

    counts = _counts(clean_pg, outcome.run_id)
    assert counts[:3] == [1, 4, 4]
    stored = pg_helper.admin_rows(
        clean_pg, "select solver, solver_version, psse_version from public.psse_run where run_id = %s",
        (outcome.run_id,))
    assert stored == [{"solver": "pandapower", "solver_version": pandapower.__version__,
                       "psse_version": None}]
    problems = [row for row in pg_helper.admin_rows(clean_pg, pg_helper._read(pg_helper.CHECKS_SQL))
                if not row["ok"]]
    assert problems == [], problems
    assert os.listdir(tempfile.gettempdir()) == []


def test_db_a_pandapower_run_cannot_be_stored_as_psse(clean_pg):
    """The writer's own tag check is bypassed: both run inserts, executed directly as the writer
    role, are refused by the database tie when a pp- id is sent as psse."""
    url = pg_helper.role_url(clean_pg, WRITER_ROLE)
    run_id = pg_helper.make_run_id(50, STARTED, prefix="pp")
    base = pg_helper.valid_run_rows(run_id, STARTED)["psse_run"][0]
    assert set(base) <= set(contract.PSSE_RUN_COLUMNS)

    untagged = _bind(contract.PSSE_RUN_COLUMNS, base)
    _rejected(url, contract.INSERT_RUN_SQL, untagged, "psse_run_solver_run_id_ck")

    as_psse = _bind(contract.TAGGED_RUN_COLUMNS, dict(base, solver="psse", solver_version=None))
    _rejected(url, contract.INSERT_RUN_TAGGED_SQL, as_psse, "psse_run_solver_run_id_ck")

    assert _scalar(clean_pg, "select count(*) as n from public.psse_run") == 0


def test_db_both_solvers_side_by_side_in_one_hour(clean_pg, tmp_path):
    """A PSS/E run and a pandapower run started in the same UTC hour are both stored, each with its
    own tag: one psse run with a psse- id and no solver version, one pandapower run with a pp- id."""
    selection = ratings.select_ratings(psse_fakes.fake_fetch(_rows()), STARTED)
    psse_outcome = job.run_once(
        fetch=psse_fakes.fake_fetch(_rows()),
        study=psse_fakes.FakeStudy(results=psse_fakes.fake_results(selection)),
        connect=_connect(clean_pg),
        case_id="summer_peak_case",
        case_sha256="ab" * 32,
        mapping_sha256="cd" * 32,
        clock=_clock(datetime.timedelta(0), datetime.timedelta(minutes=2)),
        env={"PSSE_JOB_VERSION": "test-version"},
    )
    assert psse_outcome.status == "written"

    prepared = _prepared(tmp_path)
    pp_outcome = job.run_once(
        fetch=psse_fakes.fake_fetch(_rows()),
        study=prepared.study,
        connect=_connect(clean_pg),
        case_id=prepared.case_id,
        case_sha256=prepared.case_sha256,
        mapping_sha256=prepared.mapping_sha256,
        clock=_clock(datetime.timedelta(minutes=5), datetime.timedelta(minutes=9)),
        env={"PSSE_JOB_VERSION": "test-version"},
        solver=engine.SOLVER,
    )
    assert pp_outcome.status == "written"

    stored = pg_helper.admin_rows(
        clean_pg,
        "select run_id, solver, solver_version from public.psse_run "
        "where slot_time = %s order by solver",
        (STARTED.replace(minute=0, second=0),))
    assert [row["solver"] for row in stored] == ["pandapower", "psse"]
    by_solver = dict((row["solver"], row) for row in stored)
    assert by_solver["psse"]["run_id"] == psse_outcome.run_id
    assert by_solver["psse"]["run_id"].startswith("psse-")
    assert by_solver["psse"]["solver_version"] is None
    assert by_solver["pandapower"]["run_id"] == pp_outcome.run_id
    assert by_solver["pandapower"]["run_id"].startswith("pp-")
    assert by_solver["pandapower"]["solver_version"] == pandapower.__version__
