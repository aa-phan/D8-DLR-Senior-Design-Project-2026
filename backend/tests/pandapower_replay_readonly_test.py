"""
The replay writes nothing and connects to nothing (pandapower-solver Phase 4, plan 04-03: AGR-01;
decision D-01; threat T-04-11).

Four layers, cheapest first: an import walk of every module of the phase (in functions and handlers
too, both import forms), a fresh interpreter that must load no writer-side module, a planted-import
check that shows the walk can fire, and a full replay on the real solver with socket and psycopg
connections made to raise and the writer and job entry points replaced by recorders, which must
finish with the pass word and zero recorder calls.
"""

import ast
import io
import os
import socket
import subprocess
import sys

import pytest

pytest.importorskip("pandapower")

import pandapower_replay_fixture as fixture  # noqa: E402
from pandapower_job import replay_cli  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))

MODULES = (
    os.path.join(_BACKEND, "pandapower_job", "recorded.py"),
    os.path.join(_BACKEND, "pandapower_job", "agree.py"),
    os.path.join(_BACKEND, "pandapower_job", "replay.py"),
    os.path.join(_BACKEND, "pandapower_job", "replay_cli.py"),
    os.path.join(_BACKEND, "pandapower_replay.py"),
)

FORBIDDEN_ROOTS = ("psycopg", "psycopg2", "sqlalchemy", "socket", "http", "urllib", "requests")
FORBIDDEN_WRITER_SIDE = ("writer", "job", "gaps", "credcheck", "launcher", "probe")


def _imports(source):
    """Every module name an import statement of `source` could load, anywhere in the tree, in both
    forms: `import a.b` gives a.b; `from a import b` gives a and a.b."""
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names.append(base)
            names += ["%s.%s" % (base, alias.name) if base else alias.name for alias in node.names]
    return names


def _violations(source):
    found = []
    for name in _imports(source):
        parts = name.split(".")
        if parts[0] in FORBIDDEN_ROOTS:
            found.append(name)
        elif parts[0] == "psse_job" and len(parts) > 1 and parts[1] in FORBIDDEN_WRITER_SIDE:
            found.append(name)
        elif parts[0] in FORBIDDEN_WRITER_SIDE:      # a bare `import writer` style import
            found.append(name)
    return found


@pytest.mark.parametrize("path", MODULES, ids=[os.path.basename(path) for path in MODULES])
def test_no_module_of_the_phase_imports_a_driver_a_network_module_or_a_writer_side_module(path):
    with open(path, "r", encoding="utf-8") as handle:
        assert _violations(handle.read()) == []


PLANTED = [
    "import psycopg",
    "import psycopg2.extras",
    "from psycopg import connect",
    "import sqlalchemy",
    "import socket",
    "import http.client",
    "from urllib import request",
    "import urllib.request",
    "import requests",
    "import psse_job.writer",
    "import psse_job.job as j",
    "from psse_job import writer",
    "from psse_job import gaps, credcheck",
    "from psse_job.job import run_once",
    "from psse_job.launcher import x",
    "from psse_job.probe import y",
    "def f():\n    import psycopg",
    "def f():\n    from psse_job import writer",
    "try:\n    pass\nexcept Exception:\n    import socket",
    "class C:\n    def g(self):\n        if True:\n            import psse_job.credcheck",
]


@pytest.mark.parametrize("source", PLANTED, ids=[str(index) for index in range(len(PLANTED))])
def test_the_import_walk_fires_on_a_planted_import(source):
    assert _violations(source) != []


def test_the_import_walk_stays_quiet_on_the_imports_the_phase_does_use():
    allowed = ("from psse_job import constants, contract, ratings, run_record\n"
               "from pandapower_job import agree, engine, recorded\n"
               "import collections, os, json\n")
    assert _violations(allowed) == []


_FRESH = """
import sys
sys.path.insert(0, {backend!r})
import importlib.util
from pandapower_job import recorded, agree, replay, replay_cli
spec = importlib.util.spec_from_file_location("entry_script", {entry!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
banned = ("psse_job.writer", "psse_job.job", "psse_job.gaps", "psse_job.credcheck",
          "psse_job.launcher", "psse_job.probe")
print(",".join(name for name in banned if name in sys.modules) or "none")
"""


def test_a_fresh_interpreter_importing_the_phase_loads_no_writer_side_module():
    code = _FRESH.format(backend=_BACKEND, entry=os.path.join(_BACKEND, "pandapower_replay.py"))
    done = subprocess.run([sys.executable, "-I", "-B", "-c", code], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True, timeout=300)
    assert done.returncode == 0, "the fresh interpreter failed to import the phase"
    assert done.stdout.strip().splitlines()[-1] == "none"


def test_the_entry_script_with_no_arguments_prints_the_usage_and_exits_2():
    done = subprocess.run(
        [sys.executable, "-I", "-B", os.path.join(_BACKEND, "pandapower_replay.py")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=300)
    assert done.returncode == 2
    assert done.stdout == ""
    assert done.stderr.splitlines()[-2:] == [
        "usage: pandapower_replay.py {ingest,replay} ...", "usage error: bad or missing arguments"]


# -- a full replay with every connection blocked and every writer entry point recorded ------------


class _Recorder(object):
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("a writer-side entry point was called during a replay")


def _blocked(*args, **kwargs):
    raise AssertionError("a connection was attempted during a replay")


def test_a_full_real_replay_makes_no_connection_and_calls_no_writer(tmp_path, monkeypatch):
    import psycopg
    from psse_job import job, writer

    recorders = dict((name, _Recorder()) for name in ("connect", "write_run", "record_failure",
                                                      "run_once"))
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(psycopg, "connect", _blocked)
    monkeypatch.setattr(writer, "connect", recorders["connect"])
    monkeypatch.setattr(writer, "write_run", recorders["write_run"])
    monkeypatch.setattr(writer, "record_failure", recorders["record_failure"])
    monkeypatch.setattr(job, "run_once", recorders["run_once"])

    files = tmp_path / "files"
    files.mkdir()
    stand = fixture.standin(files, stress=True)
    repo = fixture.make_repo(tmp_path / "repo")
    fixture.private_layout(repo, stand)
    fixture.ingest_standins_result(repo, [stand])

    out, err = io.StringIO(), io.StringIO()
    code = replay_cli.main(["replay"], out=out, err=err, repo_root=repo, now=fixture.FIXED_NOW,
                           environ={})
    assert code == 0 and err.getvalue() == ""
    assert out.getvalue().splitlines()[0] == "replay: pass"
    assert [name for name, recorder in recorders.items() if recorder.calls] == []


def test_the_recorders_and_blocks_are_able_to_fire(monkeypatch):
    import psycopg
    from psse_job import writer

    monkeypatch.setattr(psycopg, "connect", _blocked)
    with pytest.raises(AssertionError):
        psycopg.connect("anything")
    recorder = _Recorder()
    monkeypatch.setattr(writer, "write_run", recorder)
    with pytest.raises(AssertionError):
        writer.write_run()
    assert len(recorder.calls) == 1
