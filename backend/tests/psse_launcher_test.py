"""
SCH-01 / TST-02 proofs of the PSS/E launcher core (pss-e-integration Phase 3, plan 03-01): one
config file, through the run lock, the launcher, the FAKE psspy and Phase 1's unchanged
`job.run_once`, into a throwaway local Postgres. A converged run writes 1 + 4 + 4 + 10 rows with
every completeness check ok; every way the launcher can stop before or around the study has one
documented exit code and leaks no secret.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's tmp dir
and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local throwaway database (host
127.0.0.1, localhost or ::1; anything else fails the test); only the tests that read the database
need it. With `PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping.
They never touch Supabase; the ratings server is a loopback stand-in and every "remote" URL uses a
reserved .invalid host.

Honest scope: these tests prove launcher logic, lock semantics, exit codes and secret hygiene against
a fake psspy. They do not prove that the lock behaves identically on the laptop's Python and
filesystem, that `os.add_dll_directory` is needed or enough, that Task Scheduler passes the exit
code through, or anything about real PSS/E (all UNVERIFIED until runbook steps in plans 03-07 and
03-08).

Follows backend/tests/psse_study_job_test.py (module-level imports, plain asserts, no test classes).
"""

import copy
import datetime
import io
import json
import os
import re
import socket
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
from psse_job import constants, launcher, lock, run_record  # noqa: E402

WRITER_ROLE = "dlr_psse_writer"
STARTED = datetime.datetime(2026, 10, 28, 14, 7, 30, tzinfo=datetime.timezone.utc)
EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
SUMMARY_LINE = re.compile(r"^run_id=(\S+) outcome=(\S+) status=(\S+) exit=(\d+)\n$")


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


@pytest.fixture(autouse=True)
def _restore_search_path(monkeypatch):
    """add_search_dirs changes sys.path: every test works on a copy that is put back afterwards."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(launcher, "DLL_DIRECTORY_HANDLES", [])


# --------------------------------------------------------------------------- helpers


def _clock(*offsets):
    """A clock returning STARTED plus each offset (a timedelta) in turn, then the last one again."""
    values = [STARTED + offset for offset in offsets]
    state = {"i": 0}

    def clock():
        value = values[min(state["i"], len(values) - 1)]
        state["i"] += 1
        return value

    return clock


def _standard_clock():
    return _clock(datetime.timedelta(0), datetime.timedelta(minutes=4))


def _counts(admin_url, run_id=None):
    """(psse_run, dispatch, margin, contingency) row counts for `run_id`, or of whole tables."""
    counts = []
    for table in pg_helper.RESULT_TABLES:
        if run_id is None:
            sql, params = "select count(*) as n from public." + table, None
        else:
            sql, params = "select count(*) as n from public." + table + " where run_id = %s", (run_id,)
        counts.append(pg_helper.admin_rows(admin_url, sql, params)[0]["n"])
    return counts


def _run_row(admin_url, run_id):
    rows = pg_helper.admin_rows(admin_url, "select * from public.psse_run where run_id = %s", (run_id,))
    return rows[0] if rows else None


def _checks(admin_url):
    return pg_helper.admin_rows(admin_url, pg_helper._read(pg_helper.CHECKS_SQL))


def _mapping_file(tmp_path, placeholder=False, name="mapping.json"):
    """A temp copy of the example mapping, with or without its placeholder marker; returns its path."""
    with open(EXAMPLE, encoding="utf-8") as handle:
        data = copy.deepcopy(json.load(handle))
    data["placeholder"] = placeholder
    path = str(tmp_path / name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    return path


def _registered(tmp_path, case=None, solver=None):
    """(fake, case path): the case registered under a path whose file holds a marker."""
    fake = fake_module.FakePsspy(solver=solver)
    path = str(tmp_path / "PLACEHOLDER_CASE.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(path, fake_module.placeholder_case() if case is None else case)
    return fake, path


def _closed_port():
    """A loopback port nobody listens on (bound, read and released)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _local_url(port=5432, user=WRITER_ROLE, db="psse_test"):
    return "postgresql://%s@127.0.0.1:%d/%s" % (user, port, db)


def _write_config(tmp_path, values=None, name="job.env", raw=None):
    """Write a config file; `values` override the defaults (None removes a key). Returns its path."""
    path = tmp_path / name
    if raw is not None:
        path.write_bytes(raw)
        return str(path)
    merged = {
        "SUPABASE_PSSE_DB_URL": _local_url(),
        "SUPABASE_URL": "http://127.0.0.1:1",
        "SUPABASE_PUBLISHABLE_KEY": psse_fakes.fake_publishable_key(),
        "PSSE_CASE_PATH": str(tmp_path / "PLACEHOLDER_CASE.sav"),
        "PSSE_MAPPING_PATH": str(tmp_path / "mapping.json"),
        "PSSE_PSSPY_DIR": str(tmp_path / "psspy"),
        "PSSE_JOB_VERSION": "test-launcher",
        "PSSE_LOG_DIR": str(tmp_path / "logs"),
        "PSSE_LOCK_PATH": str(tmp_path / "locks" / "psse_job.lock"),
    }
    merged.update(values or {})
    lines = ["%s=%s" % (key, value) for key, value in merged.items() if value is not None]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


class Sandbox(object):
    """One launcher call: config file, fake psspy, ratings server, captured streams."""

    def __init__(self, tmp_path, admin_url=None, server=None, values=None, fake=None, case_path=None):
        self.tmp_path = tmp_path
        self.fake, registered = _registered(tmp_path) if fake is None else (fake, case_path)
        self.case_path = registered
        mapping = _mapping_file(tmp_path)
        merged = {"PSSE_CASE_PATH": self.case_path, "PSSE_MAPPING_PATH": mapping}
        if admin_url is not None:
            merged["SUPABASE_PSSE_DB_URL"] = pg_helper.role_url(admin_url, WRITER_ROLE)
        if server is not None:
            merged["SUPABASE_URL"] = server.url
        merged.update(values or {})
        self.values = merged
        self.config = _write_config(tmp_path, merged)
        self.out = io.StringIO()
        self.err = io.StringIO()
        self.loader_calls = []

    def loader(self, cfg):
        self.loader_calls.append(cfg)
        return self.fake

    def log_text(self):
        path = os.path.join(self.tmp_path, "logs", "psse_job.log")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def main(self, argv=None, **kwargs):
        argv = ["run", "--config", self.config] if argv is None else argv
        kwargs.setdefault("clock", _standard_clock())
        return launcher.main(argv, kwargs.pop("loader", self.loader),
                             out=self.out, err=self.err, **kwargs)


# --------------------------------------------------------------------------- the tracer


def test_tracer_run_config_file_to_postgres(clean_pg, tmp_path):
    """A config file through the lock, the launcher and the fake psspy into Postgres: one complete run."""
    rows = psse_fakes.latest_rows(STARTED, provisional=True)
    with psse_fakes.FakeLatestRatingServer(rows, key=psse_fakes.fake_publishable_key()) as server:
        box = Sandbox(tmp_path, admin_url=clean_pg, server=server)
        case_hash = run_record.file_sha256(box.case_path)
        code = box.main()
        assert [request["path"] for request in server.requests] == ["/rest/v1/latest_rating"]
    assert code == 0, box.err.getvalue()
    assert box.err.getvalue() == ""
    match = SUMMARY_LINE.match(box.out.getvalue())
    assert match is not None, box.out.getvalue()
    run_id, outcome, status, exit_text = match.groups()
    assert (outcome, status, exit_text) == ("fallback", "written", "0")

    assert _counts(clean_pg, run_id) == [1, 4, 4, 10]
    stored = _run_row(clean_pg, run_id)
    assert stored["outcome"] == "fallback"
    assert stored["case_id"] == "PLACEHOLDER_CASE.sav"
    assert stored["job_version"] == "test-launcher"
    assert stored["case_sha256"] == run_record.file_sha256(box.case_path)
    assert stored["mapping_sha256"] == run_record.file_sha256(box.values["PSSE_MAPPING_PATH"])
    assert stored["n_contingencies"] == 16
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []

    assert run_id in box.log_text()
    lock_path = str(tmp_path / "locks" / "psse_job.lock")
    assert os.path.exists(lock_path)
    with lock.RunLock(lock_path) as again:
        assert again.acquired is True
    assert any(call[0] == "case" for call in box.fake.fake_calls)
    assert run_record.file_sha256(box.case_path) == case_hash
    assert box.fake.fake_saved_paths
    assert box.case_path not in box.fake.fake_saved_paths
    assert len(box.loader_calls) == 1


def test_tracer_environment_is_not_configuration(clean_pg, tmp_path, monkeypatch):
    """A different database URL in the process environment is ignored: the file is the configuration."""
    monkeypatch.setenv("SUPABASE_PSSE_DB_URL", _local_url(port=_closed_port()))
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:%d" % _closed_port())
    monkeypatch.setenv("PSSE_JOB_VERSION", "from-the-environment")
    monkeypatch.setenv("PSSE_CASE_PATH", str(tmp_path / "nowhere.sav"))
    rows = psse_fakes.latest_rows(STARTED, provisional=True)
    with psse_fakes.FakeLatestRatingServer(rows) as server:
        box = Sandbox(tmp_path, admin_url=clean_pg, server=server)
        code = box.main()
    assert code == 0, box.err.getvalue()
    run_id = SUMMARY_LINE.match(box.out.getvalue()).group(1)
    assert _counts(clean_pg, run_id) == [1, 4, 4, 10]
    assert _run_row(clean_pg, run_id)["job_version"] == "test-launcher"


def test_dll_directory_guarded_by_hasattr(tmp_path, monkeypatch):
    """os.add_dll_directory exists only on Windows with Python 3.8+: absent means nothing is registered."""
    folder = str(tmp_path / "bin")
    os.makedirs(folder)
    cfg = {"PSSE_BIN_DIR": folder}

    monkeypatch.delattr(os, "add_dll_directory", raising=False)
    assert not hasattr(os, "add_dll_directory")
    launcher.add_search_dirs(cfg)
    assert launcher.DLL_DIRECTORY_HANDLES == []

    registered = []
    handle = object()

    def recording(path):
        registered.append(path)
        return handle

    monkeypatch.setattr(os, "add_dll_directory", recording, raising=False)
    launcher.add_search_dirs(cfg)
    assert registered == [folder]
    assert launcher.DLL_DIRECTORY_HANDLES == [handle]
