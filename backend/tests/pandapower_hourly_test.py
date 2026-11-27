"""
OPS-02 and OPS-03, pure tier (pandapower-solver Phase 5, plan 05-01): the hourly runner's `run`
command (`pandapower_job.hourly`, entry script `backend/pandapower_hourly.py`).

What is proven here, with no database and no network: four base64 secrets become private files in
a temporary folder that is removed however the run ends; the run is live only for the exact text
`true`; a live run on a placeholder is refused before the ratings are read, before the study and
before any connection; a dry run loads no writer-side module; a live run is tagged pandapower; and
everything printed is a line of the closed vocabulary, with the study's own output, logging and
warnings kept off every channel. The tracer runs the real four-city study on the public 39-bus
fixture; the other tests use a fast stand-in study.

What the database tier of plan 05-04 adds: that a dry run leaves the four result tables unchanged
and that a live run stores a run set with solver pandapower, on a throwaway local Postgres.

Plan 05-04 also adds the `soak` command, tested here on a fake connection (the last tests of this
file): the per-solver gap check with pandapower expected, the counts-only lines, the trailing 24-slot
count and the exit rules.

Synthetic data only; nothing here reads `data/private`. No test asserts a file mode or pins file
bytes (Windows).
"""

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

import ast  # noqa: E402
import base64  # noqa: E402
import datetime  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import subprocess  # noqa: E402
import warnings  # noqa: E402

import pandapower_hourly_fixture as fixture  # noqa: E402
from pandapower_job import cli, engine, hourly  # noqa: E402
from psse_job import contract, gaps, job, ratings  # noqa: E402


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _vocabulary_ok(lines):
    return all(any(pattern.match(line) for pattern in hourly.HOURLY_LINE_PATTERNS) for line in lines)


def _clock():
    return lambda: fixture.FIXED_NOW


@pytest.fixture(scope="module")
def base_env(tmp_path_factory):
    """The dry environment of the public fixture, built once; a test copies it."""
    return fixture.hourly_env(tmp_path_factory.mktemp("hourly_env"))


def _run(environ, **seams):
    """(exit code, printed lines) of one `run` call with the fast stand-in study unless a seam
    replaces it; every printed line is asserted to be in the vocabulary."""
    buffer = io.StringIO()
    options = dict(fetch=fixture.fake_fetch_for(fixture.FIXED_NOW), clock=_clock(),
                   prepare=fixture.fast_prepare, sink=False)
    options.update(seams)
    code = hourly.main(["run"], out=buffer, environ=environ, **options)
    lines = buffer.getvalue().splitlines()
    assert _vocabulary_ok(lines)
    return code, lines


class _Recorder(object):
    """A stand-in that records every call and fails the test when it is called."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("a stand-in that must not be called was called")


def _base64_of(document):
    return base64.b64encode(json.dumps(document).encode("utf-8")).decode("ascii")


# -- the tracer ------------------------------------------------------------------------------------


def test_tracer_dry_run_end_to_end_prints_counts_and_writes_nothing(tmp_path):
    environ = fixture.hourly_env(tmp_path)
    buffer = io.StringIO()
    code = hourly.main(["run"], out=buffer, environ=environ,
                       fetch=fixture.fake_fetch_for(fixture.FIXED_NOW), clock=_clock(), sink=False)
    lines = buffer.getvalue().splitlines()
    assert code == 0
    assert lines[0] == "mode: dry"
    assert lines[1] == "inputs: ok"
    match = re.match(r"ratings: city_rating=([0-9]+) static=([0-9]+)\Z", lines[2])
    assert match is not None and int(match.group(1)) + int(match.group(2)) == 4
    assert lines[3] == "study: ok"
    assert lines[4] in ("outcome: ok", "outcome: fallback")
    assert re.match(r"rows: run=1 dispatch=4 margin=4 contingency=[0-9]+\Z", lines[5])
    assert lines[6] == "dry run: nothing was written to the database"
    assert len(lines) == 7
    assert _vocabulary_ok(lines)
    text = buffer.getvalue()
    assert "pp-" not in text
    assert re.search(r"[0-9a-f]{64}", text) is None
    assert os.listdir(tempfile.gettempdir()) == []


# -- the live switch (D-02, D-13) ------------------------------------------------------------------


@pytest.mark.parametrize("value, expected", [
    (None, "dry"), ("", "dry"), ("True", "dry"), ("TRUE", "dry"), ("1", "dry"), ("yes", "dry"),
    ("false", "dry"), (" true", "dry"), ("true ", "dry"), ("true\n", "dry"), ("true", "live")])
def test_mode_is_live_only_for_the_exact_text_true(value, expected):
    environ = {} if value is None else {hourly.LIVE_VARIABLE: value}
    assert hourly.decide_mode(environ) == expected


# -- the refusals of the inputs --------------------------------------------------------------------

_SECRET_NAMES = [name for _word, name, _file, _cap in hourly.SECRET_ENV]


@pytest.mark.parametrize("name, live", [(name, False) for name in _SECRET_NAMES]
                         + [("SUPABASE_URL", False), ("SUPABASE_PUBLISHABLE_KEY", False),
                            ("SUPABASE_PSSE_DB_URL", True)])
@pytest.mark.parametrize("blank", [None, "", "  \n"])
def test_missing_secret_is_refused_before_any_folder(base_env, monkeypatch, name, live, blank):
    made = []
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: made.append(1) or "unused")
    environ = dict(base_env, SUPABASE_PSSE_DB_URL="postgresql://writer.example/db")
    if live:
        environ[hourly.LIVE_VARIABLE] = "true"
    if blank is None:
        del environ[name]
    else:
        environ[name] = blank
    code, lines = _run(environ)
    assert code == 2
    assert lines == ["mode: %s" % ("live" if live else "dry"), "inputs: refused (missing_secret)"]
    assert made == []


def test_the_writer_value_is_not_needed_in_a_dry_run(base_env):
    environ = dict(base_env)
    environ.pop("SUPABASE_PSSE_DB_URL", None)
    code, lines = _run(environ)
    assert code == 0 and lines[-1] == "dry run: nothing was written to the database"


@pytest.mark.parametrize("name", _SECRET_NAMES)
@pytest.mark.parametrize("text", ["!!!!", "QUJDRA", "QUJD=", "QU JD", "===="])
def test_bad_base64_is_refused(base_env, name, text):
    code, lines = _run(dict(base_env, **{name: text}))
    assert code == 2
    assert lines == ["mode: dry", "inputs: refused (bad_base64)"]
    assert os.listdir(tempfile.gettempdir()) == []


def test_surrounding_whitespace_of_a_secret_is_ignored(base_env):
    padded = dict(base_env)
    padded[_SECRET_NAMES[1]] = "  " + base_env[_SECRET_NAMES[1]] + "\n"
    assert _run(padded)[0] == 0


def test_size_cap_boundary(base_env, monkeypatch):
    word, name, file_name, _cap = hourly.SECRET_ENV[0]
    size = len(base64.b64decode(base_env[name]))

    def capped(cap):
        monkeypatch.setattr(hourly, "SECRET_ENV", ((word, name, file_name, cap),)
                            + tuple(hourly.SECRET_ENV[1:]))

    capped(size)
    code, lines = _run(dict(base_env))
    assert code == 0 and lines[1] == "inputs: ok"
    capped(size - 1)
    code, lines = _run(dict(base_env))
    assert code == 2
    assert lines == ["mode: dry", "inputs: refused (too_large)"]
    assert os.listdir(tempfile.gettempdir()) == []


def _settings_document(**changes):
    values = fixture.study_fixture.fixture_backend().solve_settings
    settings = {
        "enforce_q_lims": values.enforce_q_lims, "tolerance_mva": values.tolerance_mva,
        "max_iteration": values.max_iteration, "collapse_voltage_pu": values.collapse_voltage_pu,
        "sources": dict(values.sources), "deviations": list(values.deviations)}
    settings.update(changes)
    return {"settings": settings, cli.REPORT_MARKER: 1}


def test_records_refused_prints_the_reason(base_env):
    placeholder = _settings_document(sources={
        "enforce_q_lims": "placeholder: not recorded", "tolerance_mva": "x", "max_iteration": "x",
        "collapse_voltage_pu": "x"})
    code, lines = _run(dict(base_env, PANDAPOWER_SETTINGS_B64=_base64_of(placeholder)))
    assert code == 2
    assert lines == ["mode: dry", "inputs: ok", "records: refused (placeholder_source)"]
    unmarked = {"settings": _settings_document()["settings"]}
    code, lines = _run(dict(base_env, PANDAPOWER_SETTINGS_B64=_base64_of(unmarked)))
    assert code == 2 and lines[-1] == "records: refused (bad_marker)"
    assert os.listdir(tempfile.gettempdir()) == []


# -- the placeholder refusal (D-03) ----------------------------------------------------------------


def test_live_with_a_placeholder_backend_is_refused_before_any_connect_or_study(base_env):
    environ = dict(base_env, PANDAPOWER_LIVE="true",
                   SUPABASE_PSSE_DB_URL="postgresql://writer.example/db")
    fetch, connect, prepare = _Recorder(), _Recorder(), _Recorder()
    code, lines = _run(environ, fetch=fetch, connect=connect, prepare=prepare,
                       backend_loader=lambda folder: engine.PLACEHOLDER_BACKEND)
    assert code == 2
    assert lines == ["mode: live", "inputs: ok", "placeholder: refused"]
    assert fetch.calls == [] and connect.calls == [] and prepare.calls == []
    assert os.listdir(tempfile.gettempdir()) == []


def test_the_placeholder_refusal_is_live_only(base_env):
    code, lines = _run(dict(base_env), backend_loader=lambda folder: engine.PLACEHOLDER_BACKEND)
    assert code == 0 and "placeholder: refused" not in lines


# -- the live call (D-04) --------------------------------------------------------------------------


class _RunOnce(object):
    """Replaces `psse_job.job.run_once`: records the call, runs the study it was given against the
    ratings it was given and returns `outcome`; it never touches `connect`."""

    def __init__(self, outcome, run_study=True):
        self.outcome = outcome
        self.run_study = run_study
        self.calls = []

    def __call__(self, fetch, study, connect, case_id, case_sha256=None, mapping_sha256=None,
                 clock=None, env=None, solver=contract.SOLVER_PSSE):
        self.calls.append(dict(connect=connect, case_id=case_id, env=env, solver=solver,
                               case_sha256=case_sha256, mapping_sha256=mapping_sha256))
        if self.run_study:
            study(ratings.select_ratings(fetch, clock()), None)
        return self.outcome


def _live_env(base_env):
    return dict(base_env, PANDAPOWER_LIVE="true",
                SUPABASE_PSSE_DB_URL="postgresql://writer.example/db")


def test_live_run_calls_run_once_with_the_pandapower_tag(base_env, monkeypatch):
    environ = _live_env(base_env)
    recorder = _RunOnce(job.RunOutcome("pp-20261028T122000Z-aaaaaaaa", "ok", "written", None, 0))
    monkeypatch.setattr(job, "run_once", recorder)
    code, lines = _run(environ)
    assert code == 0
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["solver"] == engine.SOLVER == "pandapower"
    assert call["env"] is environ
    assert call["case_id"] == "network.json"
    assert callable(call["connect"])
    assert lines[:2] == ["mode: live", "inputs: ok"]
    assert lines[2].startswith("ratings: city_rating=")
    assert lines[3:5] == ["study: ok", "outcome: ok"]
    assert re.match(r"rows: run=1 dispatch=4 margin=4 contingency=[0-9]+\Z", lines[5])
    assert lines[6:] == ["run status: written"]
    assert "pp-" not in "\n".join(lines)


def test_live_not_recorded_exits_3(base_env, monkeypatch):
    recorder = _RunOnce(job.RunOutcome("pp-x", "failed", "not_recorded", "write", 3))
    monkeypatch.setattr(job, "run_once", recorder)
    code, lines = _run(_live_env(base_env))
    assert code == 3
    assert "study: failed at stage write" in lines and "outcome: failed" in lines
    assert not any(line.startswith("rows:") for line in lines)
    assert lines[-1] == "run status: not_recorded"


def test_live_exit_code_is_the_outcomes(base_env, monkeypatch):
    recorder = _RunOnce(job.RunOutcome("pp-x", "failed", "failure_recorded", "load_flow", 1),
                        run_study=False)
    monkeypatch.setattr(job, "run_once", recorder)
    code, lines = _run(_live_env(base_env))
    assert code == 1
    assert lines[-3:] == ["study: failed at stage load_flow", "outcome: failed",
                          "run status: failure_recorded"]
    assert not any(line.startswith("ratings:") for line in lines)


# -- the temporary folder --------------------------------------------------------------------------


def _failing_prepare(exc):
    def prepare(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
        prepared = fixture.fast_prepare(backend, case_path, mapping_path)

        def study(selection, context):
            raise exc

        return prepared._replace(study=study)
    return prepare


def _raising_prepare(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
    raise RuntimeError("planted text with a branch key 9102-9101-1")


@pytest.mark.parametrize("seams, expected_code, expected_last", [
    ({}, 0, "dry run: nothing was written to the database"),
    ({"prepare": _failing_prepare(contract.StudyFailed("load_flow", "x"))}, 1,
     "dry run: nothing was written to the database"),
    ({"prepare": _raising_prepare}, 2, "error: unexpected (RuntimeError)"),
    ({"prepare": _failing_prepare(KeyboardInterrupt())}, 130, "inputs: ok"),
], ids=["success", "study_failure", "exception", "interrupt"])
def test_temp_folder_is_removed_on_success_failure_exception_and_interrupt(
        base_env, tmp_path, monkeypatch, seams, expected_code, expected_last):
    runner_temp = tmp_path / "runner_temp"
    runner_temp.mkdir()
    made = []
    real = tempfile.mkdtemp
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: made.append(real(*a, **k)) or made[-1])
    buffer = io.StringIO()
    options = dict(fetch=fixture.fake_fetch_for(fixture.FIXED_NOW), clock=_clock(), sink=False,
                   prepare=fixture.fast_prepare)
    options.update(seams)
    code = hourly.main(["run"], out=buffer, environ=dict(base_env, RUNNER_TEMP=str(runner_temp)),
                       **options)
    lines = buffer.getvalue().splitlines()
    assert _vocabulary_ok(lines)
    assert code == expected_code
    assert lines[-1] == expected_last
    assert len(made) == 1
    assert os.path.dirname(made[0]) == str(runner_temp)
    assert os.path.basename(made[0]).startswith("pandapower_hourly_")
    assert not os.path.exists(made[0])
    assert os.listdir(str(runner_temp)) == []
    assert "9102" not in buffer.getvalue()


# -- the public-log routes (D-05, D-14) ------------------------------------------------------------

NOISE = "NOISE-9102-9101-1"


def _noisy_prepare(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
    """A prepared run whose study writes the planted token on every route a library could use."""
    prepared = fixture.fast_prepare(backend, case_path, mapping_path)
    inner = prepared.study

    def study(selection, context):
        print(NOISE + " print out")
        print(NOISE + " print err", file=sys.stderr)
        os.write(1, (NOISE + " fd one\n").encode("ascii"))
        os.write(2, (NOISE + " fd two\n").encode("ascii"))
        warnings.warn(NOISE + " warning")
        logging.getLogger("pandapower").error(NOISE + " pandapower")
        logging.getLogger("psse_job.job").warning(NOISE + " job")
        return inner(selection, context)

    return prepared._replace(study=study)


def test_sinks_keep_descriptors_logging_and_warnings_out_of_the_output(
        base_env, capfd, caplog):
    caplog.set_level(logging.DEBUG)
    disabled = logging.root.manager.disable
    code = hourly.main(["run"], environ=dict(base_env), prepare=_noisy_prepare, sink=True,
                       fetch=fixture.fake_fetch_for(fixture.FIXED_NOW), clock=_clock())
    captured = capfd.readouterr()
    assert code == 0
    lines = captured.out.splitlines()
    assert lines and lines[0] == "mode: dry" and lines[-1].startswith("dry run:")
    assert _vocabulary_ok(lines)
    assert "NOISE" not in captured.out and "NOISE" not in captured.err
    assert captured.err == ""
    assert caplog.records == []
    # everything is put back: logging and warnings work again, and so do the streams
    assert logging.root.manager.disable == disabled
    logging.getLogger("after").warning("after the call")
    assert [record.getMessage() for record in caplog.records] == ["after the call"]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warnings.warn("after the call")
    assert len(caught) == 1
    print("stream after")
    os.write(1, b"descriptor after\n")
    assert capfd.readouterr().out.splitlines() == ["stream after", "descriptor after"]


@pytest.mark.filterwarnings("ignore:NOISE")
def test_without_the_sink_the_planted_noise_escapes(base_env, capfd, caplog):
    caplog.set_level(logging.DEBUG)
    buffer = io.StringIO()
    code = hourly.main(["run"], out=buffer, environ=dict(base_env), prepare=_noisy_prepare,
                       sink=False, fetch=fixture.fake_fetch_for(fixture.FIXED_NOW), clock=_clock())
    captured = capfd.readouterr()
    assert code == 0
    assert _vocabulary_ok(buffer.getvalue().splitlines())
    assert NOISE in captured.out + captured.err
    assert any(NOISE in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("line", ["::error::x", "::warning::x", "::add-mask::x", "::debug::x",
                                  "::stop-commands::x"])
def test_no_pattern_admits_a_workflow_command_line(line):
    assert not any(pattern.match(line) for pattern in hourly.HOURLY_LINE_PATTERNS)
    printer = hourly._Printer(io.StringIO())
    with pytest.raises(ValueError):
        printer.say(line)
    assert all(pattern.pattern[0].islower() for pattern in hourly.HOURLY_LINE_PATTERNS)


def test_no_pattern_admits_a_decimal_number():
    for line in ("rows: run=1 dispatch=4.5 margin=4 contingency=3",
                 "ratings: city_rating=1.0 static=3", "ratings: city_rating=1234567890 static=3",
                 "mode: dry\n", "mode: dry "):
        assert not any(pattern.match(line) for pattern in hourly.HOURLY_LINE_PATTERNS)


def test_unexpected_exception_prints_the_class_name_only(base_env, capfd):
    def prepare(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
        raise ValueError("planted branch key 9102-9101-1 and 3.14159")

    buffer = io.StringIO()
    code = hourly.main(["run"], out=buffer, environ=dict(base_env), prepare=prepare, sink=True)
    captured = capfd.readouterr()
    assert code == 2
    assert buffer.getvalue().splitlines() == ["mode: dry", "inputs: ok",
                                              "error: unexpected (ValueError)"]
    assert "9102" not in buffer.getvalue() + captured.out + captured.err
    assert "9101" not in buffer.getvalue() + captured.out + captured.err
    assert captured.err == ""


# pandapower itself imports psycopg when it is installed (its sql_io module), so "psycopg is not
# loaded" cannot be asserted as such. What D-10 needs is that the runner adds nothing: the writer-side
# modules of the PSS/E job stay unloaded, psycopg is loaded only if importing pandapower alone loads
# it, and no connection is opened (psycopg.connect is replaced by a stub that counts its calls).
_FRESH = """
import datetime, io, os, sys
sys.path.insert(0, {backend!r})
sys.path.insert(0, {tests!r})
import pandapower
baseline = "psycopg" in sys.modules
calls = []
if baseline:
    import psycopg
    def blocked(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("no connection in a dry run")
    psycopg.connect = blocked
import psse_fakes
from pandapower_job import engine, hourly

def fast_prepare(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
    prepared = engine.prepare_run(backend, case_path, mapping_path, allow_placeholder, clock)
    def study(selection, context):
        results = psse_fakes.fake_results(selection)
        return results._replace(solver=engine.SOLVER, solver_version=pandapower.__version__,
                                psse_version=None)
    return prepared._replace(study=study)

now = datetime.datetime(2026, 10, 28, 12, 20, tzinfo=datetime.timezone.utc)
rows = psse_fakes.latest_rows(now, provisional=False)
buffer = io.StringIO()
code = hourly.main(["run"], out=buffer, environ=dict(os.environ), fetch=psse_fakes.fake_fetch(rows),
                   clock=lambda: now, prepare=fast_prepare, sink=False)
banned = ("psse_job.writer", "psse_job.job", "psse_job.gaps")
print(code)
print(buffer.getvalue().splitlines()[-1])
print(",".join(name for name in banned if name in sys.modules) or "none")
print("psycopg unchanged" if ("psycopg" in sys.modules) == baseline else "psycopg loaded by the runner")
print("connect calls %d" % len(calls))
"""


def test_a_fresh_interpreter_dry_run_loads_no_writer_side_module(base_env):
    code = _FRESH.format(backend=_BACKEND, tests=_HERE)
    environ = dict(os.environ)
    environ.update(base_env)
    environ.pop(hourly.LIVE_VARIABLE, None)
    done = subprocess.run([sys.executable, "-I", "-B", "-c", code], env=environ, timeout=300,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert done.returncode == 0, "the fresh interpreter failed"
    lines = done.stdout.strip().splitlines()
    assert lines[-5:] == ["0", "dry run: nothing was written to the database", "none",
                          "psycopg unchanged", "connect calls 0"]


def test_the_runner_module_never_imports_a_database_driver():
    path = os.path.join(_BACKEND, "pandapower_job", "hourly.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append((node.module or "").split(".")[0])
    assert "psycopg" not in names and "psycopg2" not in names


def test_entry_script_without_arguments_prints_usage_and_exits_2():
    done = subprocess.run(
        [sys.executable, "-I", "-B", os.path.join(_BACKEND, "pandapower_hourly.py")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=300)
    assert done.returncode == 2
    assert done.stdout.splitlines() == [hourly.USAGE_LINE, "usage error: bad or missing arguments"]
    assert done.stderr == ""


# -- the soak command (D-04, D-09, D-12) -----------------------------------------------------------

HOUR = datetime.timedelta(hours=1)
UTC = datetime.timezone.utc
H = datetime.datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)  # the database's current hour here
PSSE = contract.SOLVER_PSSE
PP = engine.SOLVER
ISO = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
SINCE = "2026-11-24T10:00:00Z"
PLANTED = "planted-pw-4417 db-host-4417.invalid"
CHECK_FAILED_LINES = ["gap check: could not run"]
USAGE_LINES = [hourly.USAGE_LINE, "usage error: bad or missing arguments"]


class _Result(object):
    def __init__(self, rows=None, one=None):
        self._rows = rows
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _FakeConnection(object):
    """A connection that records `("set", name, value)` for the autocommit and read_only assignments
    and `("execute", sql)` for each statement, answers the two statements of the per-solver check and
    refuses any other (the same shape as `psse_gaps_solver_test._FakeConnection`)."""

    def __init__(self, rows, current_slot):
        object.__setattr__(self, "events", [])
        object.__setattr__(self, "_rows", rows)
        object.__setattr__(self, "_current", current_slot)

    def __setattr__(self, name, value):
        self.events.append(("set", name, value))

    def execute(self, sql, params=None):
        self.events.append(("execute", sql))
        if sql == gaps.RUNS_SQL:
            return _Result(rows=list(self._rows))
        if sql == gaps.CURRENT_HOUR_SQL:
            return _Result(one=(self._current,))
        raise AssertionError("unexpected statement: " + sql)

    def close(self):
        self.events.append(("close",))


READ_ONLY_EVENTS = [("set", "autocommit", False), ("set", "read_only", True),
                    ("execute", gaps.RUNS_SQL), ("execute", gaps.CURRENT_HOUR_SQL), ("close",)]


def _connector(rows, current=H):
    """(connect, made): `connect()` returns a new fake connection holding the same rows each call;
    `made` lists them."""
    made = []

    def connect():
        conn = _FakeConnection(rows, current)
        made.append(conn)
        return conn

    return connect, made


def _soak(argv, rows=(), environ=None, connect=None):
    """(exit code, printed lines, connections made) of one `soak` call on a fake connection; every
    printed line is asserted to be in the vocabulary."""
    made = []
    if connect is None:
        connect, made = _connector(list(rows))
    buffer = io.StringIO()
    code = hourly.main(["soak"] + list(argv), out=buffer, environ={} if environ is None else environ,
                       connect=connect, sink=False)
    lines = buffer.getvalue().splitlines()
    assert _vocabulary_ok(lines)
    return code, lines, made


def _consecutive(solver, count, first_back=1, fallback_every=None):
    """`count` hourly runs of `solver`, from `first_back` hours before H going back; every
    `fallback_every`-th one is a fallback run, the others are ok."""
    rows = []
    for k in range(first_back, first_back + count):
        fallback = fallback_every is not None and k % fallback_every == 0
        rows.append((H - k * HOUR, solver, "fallback" if fallback else "ok"))
    return rows


def _report(rows, current=H, since=None, expected=(PP,)):
    return gaps.format_solver_report(gaps.summarize(rows), gaps.compute_gaps(rows, current),
                                     since=since, expected=expected)


def test_gap_lines_turn_the_report_into_counts():
    psse_rows = [(H - 10 * HOUR, PSSE, "ok"), (H - 9 * HOUR, PSSE, "ok"), (H - 6 * HOUR, PSSE, "ok")]
    report = _report(psse_rows)
    assert gaps.compute_gaps(psse_rows, H)[PSSE]
    lines = hourly.gap_lines(report)
    assert lines == ["gap check: solver psse runs=3 gaps=7",
                     "gap check: solver pandapower no runs recorded"]
    assert re.search(ISO, "\n".join(lines)) is None
    assert re.search(ISO, report) is not None

    windowed = hourly.gap_lines(_report(psse_rows, since=H - 6 * HOUR))
    assert windowed == ["gap check: solver psse runs=3 gaps=5",
                        "gap check: solver pandapower no runs recorded"]

    both = psse_rows + _consecutive(PP, 24)
    assert hourly.gap_lines(_report(both)) == ["gap check: solver psse runs=3 gaps=7",
                                              "gap check: solver pandapower runs=24 gaps=0"]

    odd = [(H - 3 * HOUR, "Weird Tag!", "ok"), (H - 3 * HOUR, "zzz", "ok"), (H - 3 * HOUR, PP, "ok")]
    words = hourly.gap_lines(_report(odd))
    assert sorted(words) == sorted([
        "gap check: solver unknown runs=1 gaps=2", "gap check: solver other runs=1 gaps=2",
        "gap check: solver pandapower runs=1 gaps=2"])
    assert _vocabulary_ok(words)
    assert hourly.gap_lines("no runs recorded") == []
    assert hourly.gap_lines("") == []


def test_soak_calls_run_by_solver_with_the_pandapower_expectation(monkeypatch):
    calls = []

    def recorder(env, **kwargs):
        calls.append((env, kwargs))
        return 0

    monkeypatch.setattr(gaps, "run_by_solver", recorder)
    connect, made = _connector(_consecutive(PP, 24))
    environ = {"UNRELATED": "value"}

    code, lines, _ = _soak([], environ=environ, connect=connect)
    assert code == 0
    assert len(calls) == 1
    env, kwargs = calls[0]
    assert env is environ
    assert kwargs["expected"] == (PP,)
    assert kwargs["fail_on_gaps"] is False
    assert kwargs["since"] is None
    assert kwargs["connect"] is connect
    assert isinstance(kwargs["out"], io.StringIO)
    assert lines[-2:] == ["soak: consecutive_slots=24 of 24 fallback_slots=0", "soak: pass"]

    code, _, _ = _soak(["--since", SINCE], environ=environ, connect=connect)
    assert code == 0
    assert len(calls) == 2
    kwargs = calls[1][1]
    assert kwargs["fail_on_gaps"] is True
    assert kwargs["since"] == datetime.datetime(2026, 11, 24, 10, 0, 0, tzinfo=UTC)
    assert kwargs["expected"] == (PP,)


def test_soak_prints_the_trailing_count_and_exits_0_with_gaps():
    rows = _consecutive(PP, 24, fallback_every=6) + [(H - 30 * HOUR, PP, "ok")]
    code, lines, made = _soak([], rows)
    assert code == 0
    assert lines == ["gap check: solver pandapower runs=25 gaps=5",
                     "soak: consecutive_slots=24 of 24 fallback_slots=4", "soak: pass"]

    short = _consecutive(PP, 23) + [(H - 24 * HOUR - HOUR, PP, "ok")]
    code, lines, _ = _soak([], short)
    assert code == 0
    assert lines[-2:] == ["soak: consecutive_slots=23 of 24 fallback_slots=0", "soak: not yet"]
    assert lines[0] == "gap check: solver pandapower runs=24 gaps=1"

    none_yet = [(H - 2 * HOUR, PSSE, "ok"), (H - 1 * HOUR, PSSE, "ok")]
    code, lines, _ = _soak([], none_yet)
    assert code == 0
    assert lines == ["gap check: solver psse runs=2 gaps=0",
                     "gap check: solver pandapower no runs recorded",
                     "soak: consecutive_slots=0 of 24 fallback_slots=0", "soak: not yet"]


def test_soak_second_read_is_read_only():
    rows = _consecutive(PP, 24)
    code, _, made = _soak([], rows)
    assert code == 0
    assert len(made) == 2
    assert made[0].events == READ_ONLY_EVENTS
    assert made[1].events == READ_ONLY_EVENTS
    statements = [event[1] for conn in made for event in conn.events if event[0] == "execute"]
    assert statements == [gaps.RUNS_SQL, gaps.CURRENT_HOUR_SQL] * 2
    assert all(statement.lstrip().lower().startswith("select") for statement in statements)


def test_soak_exits_6_and_prints_no_error_text_when_the_check_cannot_run():
    environ = {"SUPABASE_PSSE_DB_URL": "postgresql://user:" + PLANTED + "@host/db"}

    def refusing():
        raise RuntimeError("connection failed for " + PLANTED)

    code, lines, _ = _soak([], environ=environ, connect=refusing)
    assert code == 6
    assert lines == CHECK_FAILED_LINES

    # the first read works and the second does not: still one line, still exit 6
    good, made = _connector(_consecutive(PP, 24))
    state = {"n": 0}

    def second_fails():
        state["n"] += 1
        if state["n"] > 1:
            raise RuntimeError("second read failed for " + PLANTED)
        return good()

    code, lines, _ = _soak([], environ=environ, connect=second_fails)
    assert code == 6
    assert lines == CHECK_FAILED_LINES

    # the same with --since: the closing check cannot run either
    code, lines, _ = _soak(["--since", SINCE], environ=environ, connect=refusing)
    assert code == 6
    assert lines == CHECK_FAILED_LINES

    # no writer value at all: the real connection factory refuses before any driver import, and the
    # variable's name (part of that error text) is not printed either
    buffer = io.StringIO()
    code = hourly.main(["soak"], out=buffer, environ={}, sink=False)
    assert code == 6
    assert buffer.getvalue().splitlines() == CHECK_FAILED_LINES
    assert "SUPABASE" not in buffer.getvalue()


def test_soak_since_closing_check_exit_rule():
    # 24 consecutive hours, no gap in the window: exit 0
    code, lines, _ = _soak(["--since", SINCE], _consecutive(PP, 24))
    assert code == 0
    assert lines[-1] == "soak: pass"

    # a gap older than the window does not count against the closing check
    older = _consecutive(PP, 24) + [(H - 30 * HOUR, PP, "ok")]
    code, lines, _ = _soak(["--since", SINCE], older)
    assert code == 0
    # the window filters the gaps shown (the five older ones are outside it); the run count is not
    assert lines[0] == "gap check: solver pandapower runs=25 gaps=0"
    assert lines[-1] == "soak: pass"

    # the hour before the current one is missing: a gap in the window, so exit 5
    gap_in_window = _consecutive(PP, 24, first_back=2)
    code, lines, _ = _soak(["--since", SINCE], gap_in_window)
    assert code == 5
    assert lines[-2:] == ["soak: consecutive_slots=0 of 24 fallback_slots=0", "soak: not yet"]

    # no gap at all, but only 12 consecutive hours: the count is below 24, exit 5
    code, lines, _ = _soak(["--since", SINCE], _consecutive(PP, 12))
    assert code == 5
    assert lines[0] == "gap check: solver pandapower runs=12 gaps=0"
    assert lines[-2:] == ["soak: consecutive_slots=12 of 24 fallback_slots=0", "soak: not yet"]

    # pandapower expected but absent: the check fails (exit 5) and prints it
    code, lines, _ = _soak(["--since", SINCE], [(H - 1 * HOUR, PSSE, "ok")])
    assert code == 5
    assert "gap check: solver pandapower no runs recorded" in lines

    # the same histories without --since all exit 0
    for rows in (older, gap_in_window, _consecutive(PP, 12)):
        assert _soak([], rows)[0] == 0


def test_soak_since_must_be_a_whole_hour():
    assert hourly.parse_since(SINCE) == datetime.datetime(2026, 11, 24, 10, 0, 0, tzinfo=UTC)
    refused = ["2026-11-24T10:30:00Z", "2026-11-24T10:00:01Z", "2026-11-24T10:00:00",
               "2026-11-24T10:00:00+00:00", "2026-11-24", "2026-11-24T10:00Z",
               "2026-13-24T10:00:00Z", "2026-11-24T24:00:00Z", "2026-11-24T10:00:00Z\n",
               " 2026-11-24T10:00:00Z", "2026-11-24t10:00:00z", "", "now", "-1"]
    for text in refused:
        connect, made = _connector(_consecutive(PP, 24))
        code, lines, _ = _soak(["--since=" + text], connect=connect)
        assert code == 2, repr(text)
        assert lines == USAGE_LINES, repr(text)
        assert made == [], repr(text)
        with pytest.raises(hourly._UsageError):
            hourly.parse_since(text)
    code, lines, _ = _soak(["--since"])
    assert (code, lines) == (2, USAGE_LINES)
