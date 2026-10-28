"""
End-to-end proofs of one whole PSS/E job run (pss-e-integration Phase 1: IN-01, WB-01, WB-02,
D-02, D-04).

`psse_job.job.run_once` reads the ratings, runs an injected fake study, validates the results
and records the run exactly once, at the end, through the atomic writer. The tracer goes from
an HTTP read (FakeLatestRatingServer) through a fake study to rows in a throwaway local
Postgres; the rest prove that every way a run can fail still leaves exactly one honest record
(or an explicit exit 3 when nothing could be recorded) and that nothing is written early.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's
tmp dir and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway
database (host 127.0.0.1, localhost or ::1; anything else fails the test). With
`PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping. They
never touch Supabase. Every planted secret is assembled from pieces so
backend/tests/secret_scan_test.py never matches this file.

Follows backend/tests/psse_writer_test.py (module-level imports, plain asserts, no test
classes).
"""

import contextlib
import copy
import datetime
import functools
import logging
import urllib.parse

import pytest

import psse_fakes
import psse_local_pg as pg_helper
from psse_job import constants, contract, job, ratings, writer

WRITER_ROLE = "dlr_psse_writer"
STARTED = datetime.datetime(2026, 10, 28, 14, 7, 30, tzinfo=datetime.timezone.utc)
CASE_PATH = "C:\\cases\\ercot_2026.sav"


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


def _checks(admin_url):
    return pg_helper.admin_rows(admin_url, pg_helper._read(pg_helper.CHECKS_SQL))


def test_tracer_run_once_http_to_postgres(clean_pg):
    """HTTP read of today's provisional ratings, a fake study, one complete fallback run in Postgres."""
    rows = psse_fakes.latest_rows(STARTED, provisional=True)
    key = psse_fakes.fake_publishable_key()
    study = psse_fakes.FakeStudy()
    with psse_fakes.FakeLatestRatingServer(rows=rows, key=key) as server:
        env = {constants.ENV_SUPABASE_URL: server.url, constants.ENV_PUBLISHABLE_KEY: key}
        outcome = job.run_once(
            fetch=functools.partial(ratings.fetch_latest_rating, env=env),
            study=study,
            connect=_connect(clean_pg),
            case_id=CASE_PATH,
            clock=_clock(datetime.timedelta(0), datetime.timedelta(minutes=3)),
        )
        assert len(server.requests) == 1

    assert outcome.outcome == "fallback"
    assert outcome.status == "written"
    assert outcome.failed_stage is None
    assert outcome.exit_code == 0

    assert len(study.calls) == 1
    selection, context = study.calls[0]
    assert [selection.choices[city].source for city in constants.CITIES] == ["static_fallback"] * 4
    assert [selection.choices[city].fallback_reason for city in constants.CITIES] == ["provisional"] * 4
    assert context.run_id == outcome.run_id

    assert _counts(clean_pg, outcome.run_id) == [1, 4, 4, 2]
    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["case_id"] == "ercot_2026.sav"
    assert stored["outcome"] == "fallback"
    assert stored["finished_at"] - stored["started_at"] == datetime.timedelta(minutes=3)
    problems = [row for row in _checks(clean_pg) if not row["ok"]]
    assert problems == [], problems


# --------------------------------------------------------------------------- helpers

def _rows(provisional=True):
    return psse_fakes.latest_rows(STARTED, provisional=provisional)


def _selection():
    """The selection run_once makes from today's provisional rows at STARTED."""
    return ratings.select_ratings(psse_fakes.fake_fetch(_rows()), STARTED)


def _run(admin_url, study, fetch=None, clock=None, connect=None, case_id=CASE_PATH):
    """run_once with fakes; defaults: today's provisional rows, a clock 1 minute apart."""
    return job.run_once(
        fetch=psse_fakes.fake_fetch(_rows()) if fetch is None else fetch,
        study=study,
        connect=_connect(admin_url) if connect is None else connect,
        case_id=case_id,
        clock=_clock(datetime.timedelta(0), datetime.timedelta(minutes=1)) if clock is None else clock,
        env={"PSSE_JOB_VERSION": "test-version"},
    )


class _FailOnNth(object):
    """
    Wraps a real writer connection: delegates everything (including `transaction()`), counts
    `execute` calls and raises RuntimeError exactly once, on call number `n`.
    """

    def __init__(self, conn, n):
        self._conn = conn
        self.n = n
        self.calls = 0

    def transaction(self, *args, **kwargs):
        return self._conn.transaction(*args, **kwargs)

    def execute(self, *args, **kwargs):
        self.calls += 1
        if self.calls == self.n:
            raise RuntimeError("injected failure at statement %s" % self.n)
        return self._conn.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)


# --------------------------------------------------------------------------- record

@pytest.mark.parametrize("stage", [
    "load_case", "mapping", "apply_ratings", "load_flow", "contingency", "voltage_margin", "dispatch",
])
def test_record_failed_study_each_stage(clean_pg, stage):
    """A StudyFailed at any stage leaves one failed row with that stage, no results, exit 1 (ROADMAP criterion 3)."""
    message = "%s failed in test" % stage
    study = psse_fakes.FakeStudy(raises=contract.StudyFailed(stage, message))
    outcome = _run(clean_pg, study)

    assert (outcome.outcome, outcome.failed_stage) == ("failed", stage)
    assert outcome.status == "failure_recorded"
    assert outcome.exit_code == 1
    assert len(study.calls) == 1
    assert _counts(clean_pg, outcome.run_id) == [1, 0, 0, 0]
    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["outcome"] == "failed"
    assert stored["failed_stage"] == stage
    assert stored["error"] == message
    assert sorted(stored["ratings_used"]) == sorted(constants.CITIES)
    assert stored["finished_at"] >= stored["started_at"]
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []


def test_record_unexpected_exception_is_internal(clean_pg):
    """Any other exception is recorded as stage internal, named by its class."""
    outcome = _run(clean_pg, psse_fakes.FakeStudy(raises=KeyError("bus 9999")))
    assert (outcome.outcome, outcome.failed_stage, outcome.exit_code) == ("failed", "internal", 1)
    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["failed_stage"] == "internal"
    assert stored["error"].startswith("KeyError")
    assert _counts(clean_pg, outcome.run_id) == [1, 0, 0, 0]


def test_record_read_failure_continues_as_fallback(clean_pg):
    """D-02: a failed ratings read does not stop the run; four static read_failed cities, fallback, exit 0."""
    study = psse_fakes.FakeStudy()
    key = psse_fakes.fake_publishable_key()
    with psse_fakes.FakeLatestRatingServer(rows=[], status=503, key=key) as server:
        env = {constants.ENV_SUPABASE_URL: server.url, constants.ENV_PUBLISHABLE_KEY: key}
        outcome = _run(clean_pg, study, fetch=functools.partial(ratings.fetch_latest_rating, env=env))

    assert len(study.calls) == 1
    selection = study.calls[0][0]
    assert [(selection.choices[c].source, selection.choices[c].fallback_reason) for c in constants.CITIES] == [
        ("static_fallback", "read_failed")
    ] * 4
    assert (outcome.outcome, outcome.status, outcome.exit_code) == ("fallback", "written", 0)
    assert _counts(clean_pg, outcome.run_id) == [1, 4, 4, 2]
    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["outcome"] == "fallback"
    assert stored["ratings_read_error"] and "HTTP 503" in stored["ratings_read_error"]
    assert all(stored["ratings_used"][city]["fallback_reason"] == "read_failed" for city in constants.CITIES)


def test_record_incomplete_results_fail_validation(clean_pg):
    """A study with a city missing, or applying a rating other than the selected one, is refused before any insert."""
    results = psse_fakes.fake_results(_selection())

    missing = results._replace(dispatch=[row for row in results.dispatch if row["city"] != "EL_PASO"])
    outcome = _run(clean_pg, psse_fakes.FakeStudy(results=missing))
    assert (outcome.outcome, outcome.failed_stage, outcome.exit_code) == ("failed", "validate_results", 1)
    assert _counts(clean_pg, outcome.run_id) == [1, 0, 0, 0]
    assert _run_row(clean_pg, outcome.run_id)["failed_stage"] == "validate_results"

    claims = copy.deepcopy(results)
    claims.dispatch[0]["rating_source"] = "city_rating"
    assert claims.dispatch[0]["city"] == "AUSTIN"
    outcome = _run(clean_pg, psse_fakes.FakeStudy(results=claims))
    assert (outcome.outcome, outcome.failed_stage, outcome.exit_code) == ("failed", "validate_results", 1)
    assert _counts(clean_pg, outcome.run_id) == [1, 0, 0, 0]


def test_record_zero_violations_is_complete(clean_pg):
    """No contingency violation is a complete run: 1 + 4 + 4 + 0 rows, every check ok."""
    results = psse_fakes.fake_results(_selection(), violations=0)
    outcome = _run(clean_pg, psse_fakes.FakeStudy(results=results))
    assert (outcome.outcome, outcome.status, outcome.exit_code) == ("fallback", "written", 0)
    assert _counts(clean_pg, outcome.run_id) == [1, 4, 4, 0]
    assert _run_row(clean_pg, outcome.run_id)["n_contingencies_with_results"] == 0
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []


def test_record_write_failure_is_recorded(clean_pg):
    """A failure on the 3rd statement rolls back; the run is a recorded failure at stage write, exit 1."""
    real = _connect(clean_pg)
    outcome = _run(clean_pg, psse_fakes.FakeStudy(), connect=lambda: _FailOnNth(real(), 3))
    assert (outcome.outcome, outcome.failed_stage) == ("failed", "write")
    assert (outcome.status, outcome.exit_code) == ("failure_recorded", 1)
    assert _counts(clean_pg, outcome.run_id) == [1, 0, 0, 0]
    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["outcome"] == "failed" and stored["failed_stage"] == "write"
    assert "injected failure at statement 3" in stored["error"]


def test_record_unreachable_database_exit_code_3(clean_pg):
    """When connect fails nothing can be recorded: status not_recorded, exit 3, no psse_run row."""
    def unreachable():
        raise writer.WriteFailed("database connection failed: refused")

    outcome = _run(clean_pg, psse_fakes.FakeStudy(), connect=unreachable)
    assert (outcome.status, outcome.exit_code) == ("not_recorded", 3)
    assert outcome.outcome == "failed" and outcome.failed_stage == "write"
    assert _run_row(clean_pg, outcome.run_id) is None
    assert _counts(clean_pg, outcome.run_id) == [0, 0, 0, 0]

    failing = _run(
        clean_pg, psse_fakes.FakeStudy(raises=contract.StudyFailed("load_flow", "x")), connect=unreachable
    )
    assert (failing.status, failing.exit_code, failing.failed_stage) == ("not_recorded", 3, "load_flow")
    assert _run_row(clean_pg, failing.run_id) is None


def test_record_clock_going_backwards_is_clamped(clean_pg):
    """A clock that steps back one minute stores finished_at equal to started_at."""
    clock = _clock(datetime.timedelta(0), datetime.timedelta(minutes=-1))
    outcome = _run(clean_pg, psse_fakes.FakeStudy(), clock=clock)
    assert outcome.exit_code == 0
    stored = _run_row(clean_pg, outcome.run_id)
    assert stored["finished_at"] == stored["started_at"] == STARTED


def test_record_empty_case_id_is_labelled_unknown(clean_pg):
    """An empty case id is stored as 'unknown', never as an empty or path-like string."""
    outcome = _run(clean_pg, psse_fakes.FakeStudy(), case_id="")
    assert _run_row(clean_pg, outcome.run_id)["case_id"] == "unknown"


def test_record_naive_start_raises_before_anything():
    """A naive clock is a programming error: ValueError before the ratings read, the study or connect."""
    calls = []
    study = psse_fakes.FakeStudy()

    def fetch():
        calls.append("fetch")
        return []

    def connect():
        calls.append("connect")

    with pytest.raises(ValueError):
        job.run_once(fetch, study, connect, CASE_PATH, clock=lambda: datetime.datetime(2026, 10, 28, 14, 0))
    assert calls == [] and study.calls == []


def test_no_write_before_the_study_finishes(clean_pg):
    """D-04: connect is called once, after the study, with no psse_run row yet, for a good and a failing study."""
    for study in (
        psse_fakes.FakeStudy(),
        psse_fakes.FakeStudy(raises=contract.StudyFailed("load_flow", "did not converge")),
    ):
        seen = []
        real = _connect(clean_pg)

        def connect(study=study, seen=seen, real=real):
            rows_now = pg_helper.admin_rows(clean_pg, "select count(*) as n from public.psse_run")[0]["n"]
            seen.append((len(study.calls), rows_now))
            return real()

        outcome = _run(clean_pg, study, connect=connect)
        assert seen == [(1, 0)]
        assert _counts(clean_pg, outcome.run_id)[0] == 1
        assert len(study.calls) == 1
        pg_helper.reset(clean_pg)


class _RecordingConnection(object):
    """A connection that keeps every parameter dict it is asked to insert (no database)."""

    def __init__(self):
        self.params = []

    def transaction(self):
        return contextlib.nullcontext()

    def execute(self, sql, params=None):
        self.params.append(params)
        return self

    def fetchone(self):
        return ("inserted",)

    def close(self):
        pass


def test_stored_error_never_carries_secrets():
    """The error text written to psse_run holds none of the environment's secrets, even split into pieces."""
    user = "dlr_psse_writer." + "abcdefghij" + "klmnopqrst"
    reference = user.split(".", 1)[1]
    password_raw = "p/ss:w@rd" + "#9?x"
    host = "db." + "example." + "invalid"
    url = "postgresql" + "://" + user + ":" + urllib.parse.quote(password_raw, safe="") + "@" + host + ":5432/postgres"
    key = psse_fakes.fake_publishable_key()
    env = {constants.ENV_PSSE_DB_URL: url, constants.ENV_PUBLISHABLE_KEY: key, "PSSE_JOB_VERSION": "test-version"}
    planted = "boom pw " + password_raw + " ref " + reference + " host " + host + " key " + key
    conn = _RecordingConnection()

    outcome = job.run_once(
        fetch=psse_fakes.fake_fetch(_rows()),
        study=psse_fakes.FakeStudy(raises=RuntimeError(planted)),
        connect=lambda: conn,
        case_id=CASE_PATH,
        clock=_clock(datetime.timedelta(0), datetime.timedelta(minutes=1)),
        env=env,
    )
    assert (outcome.failed_stage, outcome.status, outcome.exit_code) == ("internal", "failure_recorded", 1)
    assert len(conn.params) == 1
    stored = conn.params[0]["error"]
    assert stored.startswith("RuntimeError: boom")
    for secret in (password_raw, reference, host, key):
        assert secret not in stored


def test_logs_never_carry_secrets(caplog):
    """No log record holds the database URL, its password, user, project reference, host or the key."""
    user = "dlr_psse_writer." + "abcdefghij" + "klmnopqrst"
    reference = user.split(".", 1)[1]
    password_raw = "p/ss:w@rd" + "#9?x"
    password_encoded = urllib.parse.quote(password_raw, safe="")
    host = "127.0.0" + ".1"
    url = "postgresql" + "://" + user + ":" + password_encoded + "@" + host + ":1/postgres"
    key = psse_fakes.fake_publishable_key()
    env = {
        constants.ENV_PSSE_DB_URL: url,
        constants.ENV_PUBLISHABLE_KEY: key,
        "PSSE_JOB_VERSION": "test-version",
    }
    planted = "boom " + url + " key " + key + " pw " + password_raw + " ref " + reference
    study = psse_fakes.FakeStudy(raises=RuntimeError(planted))

    caplog.set_level(logging.DEBUG)
    outcome = job.run_once(
        fetch=psse_fakes.fake_fetch(_rows()),
        study=study,
        connect=lambda: writer.connect(url, env=env),
        case_id=CASE_PATH,
        clock=_clock(datetime.timedelta(0), datetime.timedelta(minutes=1)),
        env=env,
    )
    assert outcome.exit_code == 3 and outcome.status == "not_recorded"

    messages = [record.getMessage() for record in caplog.records]
    assert messages
    text = "\n".join(messages) + "\n" + caplog.text
    for secret in (url, password_raw, password_encoded, user, reference, key, host):
        assert secret not in text
    summaries = [m for m in messages if "psse run " in m and outcome.run_id in m]
    assert len(summaries) == 1
    assert [m for m in messages if "psse run " in m] == summaries
