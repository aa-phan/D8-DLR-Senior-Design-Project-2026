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
import logging
import os
import re
import socket
import subprocess
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
from psse_lock_test import Holder, probe  # noqa: E402
from psse_job import constants, launcher, lock, ratings, run_record, writer  # noqa: E402

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


# --------------------------------------------------------------------------- exit 2: configuration

# Credential-shaped values are assembled from pieces (backend/tests/secret_scan_test.py scans files).
PW = "hunter2" + "-pw-" + "q8z"
REMOTE_HOST = "db.projref.example.invalid"


def _remote_url(password=PW, query="?sslmode=require", host=REMOTE_HOST):
    return "postgresql://" + "svc.projref" + ":" + password + "@" + host + ":5432/postgres" + query


def _assert_clean(box, secrets):
    """None of `secrets` is in what the launcher printed or logged."""
    for label, text in (("out", box.out.getvalue()), ("err", box.err.getvalue()), ("log", box.log_text())):
        for secret in secrets:
            assert secret not in text, "%s holds %r" % (label, secret[:6])


def _exit2(tmp_path, values=None, raw=None, extra=(), secrets=()):
    """One run that must stop with exit 2 before the loader: returns the box (streams to inspect)."""
    box = Sandbox(tmp_path, values=values)
    if raw is not None:
        box.config = _write_config(tmp_path, raw=raw)
    code = box.main(["run"] + list(extra) + ["--config", box.config])
    assert code == 2, (code, box.err.getvalue())
    assert box.loader_calls == []
    assert box.out.getvalue() == ""
    _assert_clean(box, secrets)
    return box


def test_exit2_unreadable_config(tmp_path):
    """A missing file, a folder, a file over 64 KiB and a file that is not UTF-8: exit 2, nothing ran."""
    box = Sandbox(tmp_path)
    for target in (str(tmp_path / "nothing.env"), str(tmp_path)):
        assert box.main(["run", "--config", target]) == 2
    big = _write_config(tmp_path, raw=b"# " + b"A" * 65536 + b"\n", name="big.env")
    assert box.main(["run", "--config", big]) == 2
    assert "larger than" in box.err.getvalue()
    odd = _write_config(tmp_path, raw=b"\xff\xfe\x00 not text \xc3\x28\n", name="odd.env")
    assert box.main(["run", "--config", odd]) == 2
    assert "UTF-8" in box.err.getvalue()
    assert box.loader_calls == []
    assert box.out.getvalue() == ""
    assert not os.path.exists(os.path.join(str(tmp_path), "logs"))


def test_exit2_malformed_lines_name_no_value(tmp_path):
    """A bad line is named by its number, an unknown or repeated key by its name: never a value."""
    sentinel = "s3cr3t" + "-marker-" + "7f3a"
    long_key = "K" * 41
    lines = [
        "PSSE_JOB_VERSION=one",            # 1
        "bare " + sentinel,                # 2: no KEY=VALUE
        "password: " + sentinel,           # 3: lower case, colon
        "FOO_KEY=" + sentinel,             # 4: unknown key
        "PSSE_JOB_VERSION=two" + sentinel,  # 5: repeated key
        long_key + "=" + sentinel,         # 6: unknown key, too long to name
        "postgresql://" + "u" + ":" + sentinel + "@127.0.0.1/db",  # 7: a URL pasted without KEY=
    ]
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    box = _exit2(tmp_path, raw=raw, secrets=[sentinel])
    err = box.err.getvalue()
    for needle in ("line 2", "line 3", "line 7", "FOO_KEY", "line 4", "PSSE_JOB_VERSION", "line 5", "line 6"):
        assert needle in err, (needle, err)
    assert long_key not in err


def test_exit2_required_keys_per_mode(tmp_path):
    """run needs six keys, run --dry-run three; each missing key is named, no other is."""
    run_keys = ["SUPABASE_PSSE_DB_URL", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY",
                "PSSE_CASE_PATH", "PSSE_MAPPING_PATH", "PSSE_PSSPY_DIR"]
    dry_keys = ["PSSE_CASE_PATH", "PSSE_MAPPING_PATH", "PSSE_PSSPY_DIR"]
    nothing = dict((key, None) for key in run_keys)
    err = _exit2(tmp_path, values=nothing).err.getvalue()
    for key in run_keys:
        assert key in err
    err = _exit2(tmp_path, values=nothing, extra=["--dry-run"]).err.getvalue()
    for key in dry_keys:
        assert key in err
    for key in ("SUPABASE_PSSE_DB_URL", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"):
        assert key not in err
    for key in run_keys:
        err = _exit2(tmp_path, values={key: None}).err.getvalue()
        assert "missing key %s" % key in err
        for other in run_keys:
            if other != key:
                assert "missing key %s" % other not in err


def test_exit2_relative_paths(tmp_path):
    """Every path key must be absolute (Task Scheduler's working directory is not the repository's)."""
    marker = "relative_marker"
    for key in ("PSSE_CASE_PATH", "PSSE_MAPPING_PATH", "PSSE_PSSPY_DIR", "PSSE_BIN_DIR",
                "PSSE_SITE_DIR", "PSSE_LOG_DIR", "PSSE_LOCK_PATH"):
        box = _exit2(tmp_path, values={key: marker + os.sep + "x"}, secrets=[marker])
        assert key in box.err.getvalue()
    box = _exit2(tmp_path, values={"PSSE_CASE_PATH": "~/case.sav"}, secrets=["~/case.sav"])
    assert "PSSE_CASE_PATH" in box.err.getvalue()


def test_exit2_bad_numbers(tmp_path):
    """PSSE_MAX_BUSES is a whole number from 1 to 2000000, PSSE_PREFLIGHT is 0 or 1."""
    for value in ("0", "abc", "2000001", "-5", "1.5", "20000x", "0x10"):
        box = _exit2(tmp_path, values={"PSSE_MAX_BUSES": value})
        assert "PSSE_MAX_BUSES" in box.err.getvalue()
    for value in ("2", "yes", "true", "-1"):
        box = _exit2(tmp_path, values={"PSSE_PREFLIGHT": value})
        assert "PSSE_PREFLIGHT" in box.err.getvalue()
    box = Sandbox(tmp_path, values={"PSSE_MAX_BUSES": "2000000", "PSSE_PREFLIGHT": "0"})
    cfg = launcher.read_config(box.config, "run")
    assert (cfg["PSSE_MAX_BUSES"], cfg["PSSE_PREFLIGHT"]) == ("2000000", "0")
    cfg = launcher.read_config(Sandbox(tmp_path, values={"PSSE_MAX_BUSES": "1"}).config, "run")
    assert cfg["PSSE_MAX_BUSES"] == "1"


def test_exit2_sslmode_rule(tmp_path, monkeypatch):
    """A non-local database host must say sslmode require, verify-ca or verify-full (D-08)."""
    for query in ("", "?sslmode=disable", "?sslmode=prefer", "?sslmode=allow", "?application_name=x"):
        url = _remote_url(query=query)
        box = _exit2(tmp_path, values={"SUPABASE_PSSE_DB_URL": url},
                     secrets=[PW, REMOTE_HOST, url])
        assert "SUPABASE_PSSE_DB_URL" in box.err.getvalue()
    for url in ("mysql://u@127.0.0.1/db", "postgresql:///db", "not a url", "postgresql://127.0.0.1:99999/db"):
        box = _exit2(tmp_path, values={"SUPABASE_PSSE_DB_URL": url})
        assert "SUPABASE_PSSE_DB_URL" in box.err.getvalue()
    # accepted by the reader: the three TLS modes, and a loopback host with no sslmode at all
    for mode in ("require", "verify-ca", "verify-full"):
        box = Sandbox(tmp_path, values={"SUPABASE_PSSE_DB_URL": _remote_url(query="?sslmode=" + mode)})
        launcher.read_config(box.config, "run")
    launcher.read_config(Sandbox(tmp_path, values={"SUPABASE_PSSE_DB_URL": _local_url()}).config, "run")

    # the same URL with sslmode=require is not refused here: it fails later, at the preflight
    def unreachable(address, timeout=None):
        raise OSError("no route")

    monkeypatch.setattr(launcher.socket, "create_connection", unreachable)
    box = Sandbox(tmp_path, values={"SUPABASE_PSSE_DB_URL": _remote_url()})
    assert box.main() == 3
    assert box.loader_calls == []


def test_exit2_allow_placeholder_needs_dry_run(tmp_path):
    """--allow-placeholder never reaches a run that writes: refused unless --dry-run is also given."""
    box = _exit2(tmp_path, extra=["--allow-placeholder"])
    assert "--allow-placeholder" in box.err.getvalue()
    assert not os.path.exists(os.path.join(str(tmp_path), "logs"))


def test_exit2_usage_error_is_redacted(tmp_path):
    """A usage error whose text holds a connection string is printed redacted; the verb is required."""
    url = _remote_url()
    box = Sandbox(tmp_path)
    assert box.main(["run", "--config", box.config, url]) == 2
    err = box.err.getvalue()
    assert "usage error" in err
    for secret in (PW, REMOTE_HOST, url):
        assert secret not in err
    assert box.main([]) == 2
    assert box.main(["run"]) == 2
    assert "--config" in box.err.getvalue()
    assert box.main(["frobnicate"]) == 2
    assert box.main(["run", "--config", box.config, "--bogus"]) == 2
    assert box.loader_calls == []
    assert box.out.getvalue() == ""


def test_config_accepts_bom_quotes_comments(tmp_path):
    """A Notepad BOM, comments, blank lines, quotes and Windows backslash paths are all harmless."""
    key = psse_fakes.fake_publishable_key()
    lines = [
        "# a comment line",
        "",
        '   PSSE_CASE_PATH = "C:\\Users\\tester\\Power Systems\\case file.sav"   ',
        "PSSE_MAPPING_PATH='D:\\data\\mapping.json'",
        "PSSE_PSSPY_DIR=C:\\Program Files\\PTI\\PSSE35\\PSSPY39",
        "SUPABASE_PSSE_DB_URL=" + _local_url(),
        "SUPABASE_URL=http://127.0.0.1:1",
        "SUPABASE_PUBLISHABLE_KEY=" + key,
        "PSSE_JOB_VERSION=v$HOME-%PATH%",
        "PSSE_SITE_DIR=",
    ]
    raw = b"\xef\xbb\xbf" + ("\r\n".join(lines) + "\r\n").encode("utf-8")
    path = _write_config(tmp_path, raw=raw)
    cfg = launcher.read_config(path, "run")
    assert cfg["PSSE_CASE_PATH"] == "C:\\Users\\tester\\Power Systems\\case file.sav"
    assert cfg["PSSE_MAPPING_PATH"] == "D:\\data\\mapping.json"
    assert cfg["PSSE_PSSPY_DIR"] == "C:\\Program Files\\PTI\\PSSE35\\PSSPY39"
    assert cfg["SUPABASE_PUBLISHABLE_KEY"] == key
    assert cfg["PSSE_JOB_VERSION"] == "v$HOME-%PATH%"  # no variable expansion
    assert "PSSE_SITE_DIR" not in cfg  # a blank value is no value
    folder = os.path.dirname(os.path.abspath(path))
    assert cfg["PSSE_LOG_DIR"] == os.path.join(folder, "logs")
    assert cfg["PSSE_LOCK_PATH"] == os.path.join(folder, "psse_job.lock")
    assert cfg["PSSE_MAX_BUSES"] == "20000"
    assert cfg["PSSE_PREFLIGHT"] == "1"
    assert list(cfg) == [key_def.name for key_def in launcher.CONFIG_KEYS if key_def.name in cfg]


# --------------------------------------------------------------------------- exit 3: no record


def test_exit3_unreachable_database_never_starts_psspy(clean_pg, tmp_path):
    """A closed database port is exit 3 at the preflight: the loader (a licence seat) is never called."""
    box = Sandbox(tmp_path, values={"SUPABASE_PSSE_DB_URL": _local_url(port=_closed_port())})
    code = box.main()
    assert code == 3, box.err.getvalue()
    assert box.loader_calls == []
    assert box.fake.fake_calls == []
    assert box.out.getvalue() == ""
    assert "database" in box.err.getvalue()
    assert _counts(clean_pg) == [0, 0, 0, 0]
    assert box.log_text()


def test_exit3_connect_failure_after_study(clean_pg, tmp_path):
    """Postgres up but the role does not exist: the preflight passes, the study runs, the write cannot start."""
    role = "no_such_role_" + "x7"
    rows = psse_fakes.latest_rows(STARTED, provisional=True)
    with psse_fakes.FakeLatestRatingServer(rows) as server:
        box = Sandbox(tmp_path, server=server, values={
            "SUPABASE_PSSE_DB_URL": pg_helper.role_url(clean_pg, role)})
        code = box.main()
    assert code == 3, box.err.getvalue()
    assert len(box.loader_calls) == 1
    assert _counts(clean_pg) == [0, 0, 0, 0]
    match = SUMMARY_LINE.match(box.out.getvalue())
    assert match is not None and match.group(3) == "not_recorded" and match.group(4) == "3"
    _assert_clean(box, [role, box.values["SUPABASE_PSSE_DB_URL"]])


# --------------------------------------------------------------------------- exit 4: locked


def test_exit4_second_instance_skipped_writes_nothing(clean_pg, tmp_path):
    """A real second process holds the lock: exit 4 at once, no PSS/E started, nothing recorded."""
    lock_path = str(tmp_path / "locks" / "psse_job.lock")
    holder = Holder(lock_path)
    try:
        assert holder.first_line == "acquired"
        box = Sandbox(tmp_path, admin_url=clean_pg)
        code = box.main()
    finally:
        holder.close()
    assert code == 4, box.err.getvalue()
    assert box.loader_calls == []
    assert box.fake.fake_calls == []
    assert box.out.getvalue() == ""
    assert "lock" in box.err.getvalue()
    assert _counts(clean_pg) == [0, 0, 0, 0]


def test_exit4_lock_held_during_start_and_write(clean_pg, tmp_path):
    """The lock is held while PSS/E starts and while the record is written, and free afterwards."""
    lock_path = str(tmp_path / "locks" / "psse_job.lock")
    seen = []
    rows = psse_fakes.latest_rows(STARTED, provisional=True)
    with psse_fakes.FakeLatestRatingServer(rows) as server:
        box = Sandbox(tmp_path, admin_url=clean_pg, server=server)
        url = box.values["SUPABASE_PSSE_DB_URL"]

        def loader(cfg):
            seen.append(("loader", probe(lock_path)))
            return box.fake

        def connect():
            seen.append(("connect", probe(lock_path)))
            return writer.connect(url)

        code = box.main(loader=loader, connect=connect)
    assert code == 0, box.err.getvalue()
    assert seen == [("loader", "locked"), ("connect", "locked")]
    assert probe(lock_path) == "acquired"
    assert _counts(clean_pg)[0] == 1


# --------------------------------------------------------------------------- failures around the study


def _recorded_load_case_failure(clean_pg, box, code):
    assert code == 1, box.err.getvalue()
    match = SUMMARY_LINE.match(box.out.getvalue())
    assert match is not None, box.out.getvalue()
    run_id, outcome, status, exit_text = match.groups()
    assert (outcome, status, exit_text) == ("failed", "failure_recorded", "1")
    assert _counts(clean_pg, run_id) == [1, 0, 0, 0]
    assert _counts(clean_pg) == [1, 0, 0, 0]
    stored = _run_row(clean_pg, run_id)
    assert stored["outcome"] == "failed"
    assert stored["failed_stage"] == "load_case"
    assert stored["case_id"] == "PLACEHOLDER_CASE.sav"
    assert stored["case_sha256"] == run_record.file_sha256(box.case_path)
    assert stored["mapping_sha256"] is None
    assert [row for row in _checks(clean_pg) if not row["ok"]] == []
    return stored


def test_failure_psse_unavailable_recorded_as_load_case(clean_pg, tmp_path):
    """PSS/E that cannot start is one recorded failed run at load_case, and its message names no path."""
    message = ("DLL load failed while importing psscommon: C:\\Program Files\\PTI\\PSSE35\\35.6\\"
               "PSSBIN\\psscommon.dll not found, also /opt/psse_marker/35/bin/libpsse.so")
    rows = psse_fakes.latest_rows(STARTED, provisional=True)
    with psse_fakes.FakeLatestRatingServer(rows) as server:
        box = Sandbox(tmp_path, admin_url=clean_pg, server=server)

        def loader(cfg):
            raise launcher.PsseUnavailable(message)

        code = box.main(loader=loader)
    stored = _recorded_load_case_failure(clean_pg, box, code)
    assert "PsseUnavailable" in stored["error"]
    assert "PSS/E could not be started" in stored["error"]
    assert "<path>" in stored["error"]
    for fragment in ("Program Files", "PTI", "PSSE35", "PSSBIN", "psscommon.dll", "psse_marker", "libpsse"):
        assert fragment not in stored["error"], stored["error"]
        assert fragment not in box.log_text()


def test_failure_any_loader_exception_recorded_as_load_case(clean_pg, tmp_path):
    """Any other exception of the loader is recorded the same way, with its class name."""
    rows = psse_fakes.latest_rows(STARTED, provisional=True)
    key = psse_fakes.fake_publishable_key()
    with psse_fakes.FakeLatestRatingServer(rows) as server:
        box = Sandbox(tmp_path, admin_url=clean_pg, server=server)

        def loader(cfg):
            raise ZeroDivisionError("licence server said " + key + " in D:\\psse\\licence.lic")

        code = box.main(loader=loader)
    stored = _recorded_load_case_failure(clean_pg, box, code)
    assert "ZeroDivisionError" in stored["error"]
    assert key not in stored["error"]
    assert "licence.lic" not in stored["error"]
    assert len(stored["error"]) <= 1000


def test_failure_unexpected_error_is_exit7(tmp_path, monkeypatch):
    """An unexpected launcher error is exit 7, one redacted log line, only the class name on stderr."""
    key = psse_fakes.fake_publishable_key()

    def broken(deps, cfg, allow_placeholder):
        raise RuntimeError("something failed with " + key)

    monkeypatch.setattr(launcher, "_prepare", broken)
    box = Sandbox(tmp_path, values={"SUPABASE_PUBLISHABLE_KEY": key, "PSSE_PREFLIGHT": "0"})
    code = box.main()
    assert code == 7
    assert "RuntimeError" in box.err.getvalue()
    assert "something failed" not in box.err.getvalue()
    assert box.out.getvalue() == ""
    log_lines = [line for line in box.log_text().splitlines() if "unexpected launcher error" in line]
    assert len(log_lines) == 1
    assert "RuntimeError" in log_lines[0]
    _assert_clean(box, [key])


# --------------------------------------------------------------------------- secret hygiene


def test_hygiene_secrets_never_reach_output_or_log(clean_pg, tmp_path):
    """A planted remote-looking URL, key and password never appear on stdout, stderr or in the log."""
    key = psse_fakes.fake_publishable_key()
    url = _remote_url()
    api = "https://projref.example.invalid"
    secrets = [PW, REMOTE_HOST, url, key, api, "projref"]

    def fetch():
        raise ratings.ReadFailed("latest_rating read failed: " + api + " apikey=" + key)

    def connect():
        raise RuntimeError("could not connect to " + url + " password=" + PW + " host " + REMOTE_HOST
                           + " key " + key)

    box = Sandbox(tmp_path, values={
        "SUPABASE_PSSE_DB_URL": url, "SUPABASE_URL": api, "SUPABASE_PUBLISHABLE_KEY": key,
        "PSSE_PREFLIGHT": "0"})

    def loader(cfg):
        # a record logged directly with every secret: only the redacting filter keeps it out
        logging.getLogger("psse_job.loader").warning("loader sees %s and %s and %s", url, key, PW)
        return box.fake

    code = box.main(loader=loader, fetch=fetch, connect=connect)
    assert code == 3, box.err.getvalue()
    assert "REDACTED" in box.log_text()
    _assert_clean(box, secrets)

    # the real writer against a closed loopback port, with a password in the URL
    closed = "postgresql://" + "svc" + ":" + PW + "@127.0.0.1:%d/postgres" % _closed_port()
    box = Sandbox(tmp_path, values={"SUPABASE_PSSE_DB_URL": closed, "PSSE_PREFLIGHT": "0"})
    code = box.main(fetch=fetch)
    assert code == 3, box.err.getvalue()
    _assert_clean(box, [PW, closed])


def test_hygiene_log_handlers_removed(tmp_path):
    """After every call the psse_job logger is as it was: no handler, so repeated calls never stack."""
    logger = logging.getLogger("psse_job")
    before = (list(logger.handlers), logger.level, logger.propagate)
    for _ in range(3):
        box = Sandbox(tmp_path, values={"SUPABASE_PSSE_DB_URL": _local_url(port=_closed_port())})
        assert box.main() == 3
        assert (list(logger.handlers), logger.level, logger.propagate) == before
    assert box.log_text().count("database host") == 3


# --------------------------------------------------------------------------- dry-run

_REPORT_PREFIXES = ("dry run:", "rows:", "contingencies:", "ratings:", "outcome:", "rate_set:",
                    "psse_version:", "study_seconds:", "validation:")


def _dry(box, *extra, **kwargs):
    return box.main(["run", "--dry-run"] + list(extra) + ["--config", box.config], **kwargs)


def _report_counts(text):
    """(psse_run, dispatch, margin, contingency) row counts of a dry-run report."""
    match = re.search(r"^rows: psse_run=(\d+) psse_dispatched_capacity=(\d+) "
                      r"psse_voltage_margin=(\d+) psse_contingency_result=(\d+)$", text, re.M)
    assert match is not None, text
    return [int(group) for group in match.groups()]


def test_dry_run_never_connects_and_prints_counts_only(clean_pg, tmp_path):
    """A dry run with an unreachable database and no ratings server: counts only, nothing connected."""
    connected = []

    def connect():
        connected.append(1)
        raise AssertionError("a dry run must never connect")

    for ratings_values in (
            {"SUPABASE_URL": None, "SUPABASE_PUBLISHABLE_KEY": None},
            {"SUPABASE_URL": "http://127.0.0.1:%d" % _closed_port()}):
        values = {"SUPABASE_PSSE_DB_URL": _local_url(port=_closed_port())}
        values.update(ratings_values)
        box = Sandbox(tmp_path, values=values)
        case_hash = run_record.file_sha256(box.case_path)
        mapping_hash = run_record.file_sha256(box.values["PSSE_MAPPING_PATH"])
        assert _dry(box, connect=connect) == 0, box.err.getvalue()
        assert connected == []
        assert box.err.getvalue() == ""
        out = box.out.getvalue()
        lines = out.splitlines()
        assert lines[0].startswith("dry run: nothing was written")
        assert all(line.startswith(_REPORT_PREFIXES) for line in lines), out
        assert _report_counts(out) == [1, 4, 4, 10]
        assert "contingencies: screened=16 with_results=7" in lines
        assert "outcome: fallback" in lines
        assert "rate_set: RATEA" in lines
        assert "psse_version: 35.6.0" in lines
        assert "validation: ok" in lines
        assert "ratings: city_rating=0 static=4" in lines
        # no bus number, branch key, path, case label or hash
        assert not re.search(r"\d{4,}", out), out
        for private in (str(tmp_path), "PLACEHOLDER_CASE", case_hash, mapping_hash):
            assert private not in out
        assert len(box.loader_calls) == 1
    assert _counts(clean_pg) == [0, 0, 0, 0]


def test_dry_run_counts_equal_a_real_run(clean_pg, tmp_path):
    """The counts a dry run prints are the rows the real run writes for the same case, mapping and ratings."""
    rows = psse_fakes.latest_rows(STARTED, provisional=True)
    with psse_fakes.FakeLatestRatingServer(rows) as server:
        real = Sandbox(tmp_path, admin_url=clean_pg, server=server)
        assert real.main() == 0, real.err.getvalue()
        run_id = SUMMARY_LINE.match(real.out.getvalue()).group(1)
        written = _counts(clean_pg, run_id)
        stored = _run_row(clean_pg, run_id)

        dry = Sandbox(tmp_path, server=server, values={
            "SUPABASE_PSSE_DB_URL": _local_url(port=_closed_port())})
        assert _dry(dry) == 0, dry.err.getvalue()
    out = dry.out.getvalue()
    assert _report_counts(out) == written == [1, 4, 4, 10]
    assert "outcome: %s" % stored["outcome"] in out
    assert "contingencies: screened=%d with_results=%d" % (
        stored["n_contingencies"], stored["n_contingencies_with_results"]) in out
    assert "rate_set: %s" % stored["rate_set"] in out
    assert _counts(clean_pg) == written


def test_dry_run_failed_study_exit1(tmp_path):
    """A study that raises StudyFailed is exit 1: the stage and the message are printed, nothing connected."""
    connected = []
    fake, path = _registered(
        tmp_path, solver=lambda case: fake_module.SolveOutcome(ierr=0, solved=1))
    box = Sandbox(tmp_path, fake=fake, case_path=path)
    assert _dry(box, connect=lambda: connected.append(1)) == 1
    out = box.out.getvalue()
    assert out.splitlines()[0].startswith("dry run: nothing was written")
    assert "load_flow" in out
    assert connected == []
    assert "rows:" not in out
    assert str(tmp_path) not in out

    # the committed example mapping is marked placeholder: refused by a dry run unless allowed
    box = Sandbox(tmp_path, values={"PSSE_MAPPING_PATH": EXAMPLE})
    assert _dry(box) == 1
    assert "mapping" in box.out.getvalue() and "placeholder" in box.out.getvalue()
    box = Sandbox(tmp_path, values={"PSSE_MAPPING_PATH": EXAMPLE})
    assert _dry(box, "--allow-placeholder") == 0, box.out.getvalue()
    assert "validation: ok" in box.out.getvalue()


def test_dry_run_validation_failure_exit1(tmp_path, monkeypatch):
    """A results object that fails validate_results is exit 1 naming the validation failure."""
    def bad_study(selection, context):
        good = psse_fakes.fake_results(selection)
        return good._replace(dispatch=good.dispatch[:3])  # one city has no dispatch row

    def fake_prepare(psspy, case_path, mapping_path, allow_placeholder=False, clock=None):
        return launcher.study.PreparedRun(bad_study, "case.sav", None, None, None)

    monkeypatch.setattr(launcher.study, "prepare_run", fake_prepare)
    connected = []
    box = Sandbox(tmp_path)
    assert _dry(box, connect=lambda: connected.append(1)) == 1
    out = box.out.getvalue()
    assert "validate_results" in out
    assert "validation: ok" not in out
    assert connected == []


def test_paths_dirs_appended_never_prepended(tmp_path):
    """A planted standard-library look-alike in a search folder is never found before the real one."""
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "colorsys.py").write_text("raise RuntimeError('planted module imported')\n", encoding="utf-8")
    (planted / "json.py").write_text("raise RuntimeError('planted module imported')\n", encoding="utf-8")
    (planted / "harmless_mod.py").write_text("VALUE = 42\n", encoding="utf-8")
    code = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from psse_job import launcher\n"
        "before = list(sys.path)\n"
        "launcher.add_search_dirs({'PSSE_SITE_DIR': sys.argv[2]})\n"
        "assert sys.path[:len(before)] == before, 'a folder was inserted before the existing ones'\n"
        "assert sys.path[-1] == sys.argv[2]\n"
        "import colorsys, json, harmless_mod\n"
        "assert not colorsys.__file__.startswith(sys.argv[2]), colorsys.__file__\n"
        "assert not json.__file__.startswith(sys.argv[2]), json.__file__\n"
        "print('ok', harmless_mod.VALUE)\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, _BACKEND, str(planted)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=30, universal_newlines=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok 42"
