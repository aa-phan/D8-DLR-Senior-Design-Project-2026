"""
TST-02 / SCH-01 proofs of the entry script backend/psse_run_hourly.py (pss-e-integration Phase 3,
plan 03-04) in REAL `python -I` subprocesses: the script Task Scheduler runs, started from another
working directory, finds a `psspy` module in the configured folder, starts it, and reports.

The stub `psspy.py` is written by each test into a tmp folder, never committed. It has the module
level functions the adapter reads (getdefault*, psseversion) plus psseinit and the four
output-control functions, so it proves that the script finds a module in the configured folder,
that the start calls are made as designed and that a missing module gives the right exit code.

Honest scope: a stub is not PSS/E. That real psspy accepts psseinit and the output calls with these
parameter names, that redirecting the output to a file works and that os.add_dll_directory suffices
are UNVERIFIED until runbook step 2 (plan 03-07).

Every subprocess runs with `sys.executable -I -B`, a timeout and a finally block that kills it.
"""

import ast
import os
import socket
import subprocess
import sys
import threading
import time

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fakes  # noqa: E402
from psse_lock_test import probe as lock_probe  # noqa: E402

ENTRY = os.path.join(_BACKEND, "psse_run_hourly.py")
TIMEOUT = 60

STUB_PSSPY = (
    "def getdefaultint():\n"
    "    return 100000000\n"
    "def getdefaultreal():\n"
    "    return 1.0e20\n"
    "def getdefaultchar():\n"
    "    return '\\x01'\n"
    "def psseversion():\n"
    "    return ('PSS(R)E stub', 35, 6, 0, 'date', 0)\n"
    "def psseinit(buses=None):\n"
    "    return 0\n"
    "def report_output(islct, filarg, options):\n"
    "    return 0\n"
    "def progress_output(islct, filarg, options):\n"
    "    return 0\n"
    "def alert_output(islct, filarg, options):\n"
    "    return 0\n"
    "def prompt_output(islct, filarg, options):\n"
    "    return 0\n"
)


def _closed_port():
    """A loopback port nobody listens on (bound, read and released)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _write_stub_folder(tmp_path):
    folder = tmp_path / "stub psspy folder"
    folder.mkdir()
    (folder / "psspy.py").write_text(STUB_PSSPY, encoding="utf-8")
    return folder


def _write_config(tmp_path, psspy_dir, extra=None, name="job.env"):
    values = {
        "PSSE_PSSPY_DIR": str(psspy_dir),
        "PSSE_LOG_DIR": str(tmp_path / "logs"),
        "PSSE_LOCK_PATH": str(tmp_path / "locks" / "psse_job.lock"),
    }
    values.update(extra or {})
    path = tmp_path / name
    path.write_text("\n".join("%s=%s" % item for item in values.items()) + "\n", encoding="utf-8")
    return str(path)


def _run_entry(args, cwd, timeout=TIMEOUT):
    """(code, stdout, stderr) of `python -I -B backend/psse_run_hourly.py ARGS` run in `cwd`."""
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", ENTRY] + list(args), cwd=str(cwd),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True)
    try:
        out, err = process.communicate(timeout=timeout)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    return process.returncode, out, err


def test_tracer_entry_script_selftest_with_stub_psspy_folder(tmp_path):
    """The entry script under -I, from another folder: stub psspy found, started, six PASS rows, exit 0."""
    stub = _write_stub_folder(tmp_path)
    config = _write_config(tmp_path, stub)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    code, out, err = _run_entry(["selftest", "--config", config], elsewhere)
    assert code == 0, out + err
    lines = out.splitlines()
    assert lines[0].startswith("Python ") and lines[0].endswith(("64-bit", "32-bit"))
    assert lines[1] == "PSS/E started"
    assert len(lines) == 2 + 4 + 6 + 1, out
    notes, rows = lines[2:6], lines[6:-1]
    assert all("redirected" in note for note in notes)
    assert [line.split()[1] for line in rows] == [
        "version", "launch:psseinit", "launch:report_output", "launch:progress_output",
        "launch:alert_output", "launch:prompt_output"]
    assert all(line.startswith("PASS") for line in rows)
    assert "PSS/E 35.6.0" in rows[0]
    assert lines[-1] == "6 PASS, 0 FAIL, 0 SKIP"
    for text in (out, err):
        assert str(tmp_path) not in text
        assert "stub psspy folder" not in text
    assert err == ""


def test_entry_exit2_without_arguments_under_isolated_mode(tmp_path):
    """No arguments: usage error, exit 2, on stderr, from a different working directory."""
    code, out, err = _run_entry([], tmp_path)
    assert code == 2
    assert out == ""
    assert "usage error" in err
    assert str(tmp_path) not in err


def test_entry_selftest_without_psse_exit6_names_no_path(tmp_path):
    """The real load_psspy with no psspy in the folder: exit 6, PSS/E could not be started, no path."""
    empty = tmp_path / "empty psspy folder"
    empty.mkdir()
    config = _write_config(tmp_path, empty)
    code, out, err = _run_entry(["selftest", "--config", config], tmp_path)
    assert code == 6, out + err
    assert "PSS/E could not be started: PsseUnavailable" in out
    assert "psspy could not be imported" in out
    assert "PSS/E started" not in out
    for text in (out, err):
        assert str(tmp_path) not in text
        assert "empty psspy folder" not in text
        assert os.path.dirname(sys.executable) not in text
        assert _BACKEND not in text
    assert err == ""


def _psspy_import_sites(tree):
    """[(line, enclosing function name or None)] of every import of psspy in the syntax tree."""
    found = []

    def visit(node, function):
        for child in ast.iter_child_nodes(node):
            scope = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            if isinstance(child, ast.Import) and any(
                    alias.name.split(".")[0] == "psspy" for alias in child.names):
                found.append((child.lineno, function))
            if isinstance(child, ast.ImportFrom) and (child.module or "").split(".")[0] == "psspy":
                found.append((child.lineno, function))
            if isinstance(child, ast.Call) and getattr(child.func, "id", "") in ("__import__", "import_module"):
                found.append((child.lineno, function))
            if isinstance(child, ast.Call) and getattr(child.func, "attr", "") == "import_module":
                found.append((child.lineno, function))
            visit(child, scope)

    visit(tree, None)
    return found


def test_entry_imports_psspy_only_in_load_psspy(tmp_path):
    """The one import of psspy is inside load_psspy, and importing the entry module does not run it."""
    with open(ENTRY, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), ENTRY)
    sites = _psspy_import_sites(tree)
    assert [function for _line, function in sites] == ["load_psspy"], sites
    # no other file of the repository's code imports it either (psse_job is gated by the contract test)
    code = (
        "import importlib.util, sys\n"
        "path = sys.argv[1]\n"
        "spec = importlib.util.spec_from_file_location('psse_run_hourly', path)\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "print(sorted(name for name in sys.modules if name.split('.')[0] == 'psspy'))\n"
        "print(callable(module.load_psspy), callable(module.main))\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, ENTRY], cwd=str(tmp_path), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT, universal_newlines=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["[]", "True True"]


def test_entry_prepares_streams_that_pythonw_leaves_missing(monkeypatch):
    """pythonw.exe has no stdout or stderr: the script gives itself real ones instead of failing on print."""
    import psse_run_hourly
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    try:
        psse_run_hourly._prepare_streams()
        assert sys.stdout is not None and sys.stderr is not None
        sys.stdout.write("text\n")
        sys.stderr.write("text\n")
    finally:
        for stream in (sys.stdout, sys.stderr):
            if stream is not None:
                stream.close()


def test_entry_overlapping_start_exits_4_through_two_processes(tmp_path):
    """hold-lock in one entry process, a real start in another: the second exits 4 and ends quickly."""
    stub = _write_stub_folder(tmp_path)
    config = _write_config(tmp_path, stub, {
        "SUPABASE_PSSE_DB_URL": "postgresql://dlr_psse_writer@127.0.0.1:%d/psse_test" % _closed_port(),
        "SUPABASE_URL": "http://127.0.0.1:1",
        "SUPABASE_PUBLISHABLE_KEY": psse_fakes.fake_publishable_key(),
        "PSSE_CASE_PATH": str(tmp_path / "case.sav"),
        "PSSE_MAPPING_PATH": str(tmp_path / "mapping.json"),
    })
    lock_path = str(tmp_path / "locks" / "psse_job.lock")
    holder = subprocess.Popen(
        [sys.executable, "-I", "-B", ENTRY, "hold-lock", "--config", config, "--seconds", "20"],
        cwd=str(tmp_path), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True)
    guard = threading.Timer(TIMEOUT, holder.kill)
    guard.start()
    try:
        assert holder.stdout.readline().strip() == "locked"
        started = time.monotonic()
        code, out, err = _run_entry(["run", "--config", config], tmp_path, timeout=TIMEOUT)
        elapsed = time.monotonic() - started
        assert code == 4, out + err
        assert out == ""
        assert "another instance holds the run lock" in err
        assert elapsed < 30
        assert holder.poll() is None  # the holder is still running: the second start never took the lock
        assert lock_probe(lock_path) == "locked"
    finally:
        guard.cancel()
        if holder.poll() is None:
            holder.kill()
        holder.communicate()
    # the operating system released the killed holder's lock
    assert lock_probe(lock_path) == "acquired"
