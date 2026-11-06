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
import importlib
import os
import socket
import subprocess
import sys
import threading
import time

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fakes  # noqa: E402
from psse_fake_launch import (  # noqa: E402
    DLL_FAILURE_TEXT, ENV_READY_VARIABLE, STUB_PSSPY_SOURCE, write_env_gated_psspy_folder)
from psse_job import launcher  # noqa: E402
from psse_lock_test import probe as lock_probe  # noqa: E402

ENTRY = os.path.join(_BACKEND, "psse_run_hourly.py")
TIMEOUT = 60

STUB_PSSPY = STUB_PSSPY_SOURCE


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


def _write_gated_folder(tmp_path, env_module="psse3604"):
    """(folder, import log path) of a gated fake psspy folder; the name shows a leaked path."""
    folder = tmp_path / "gated psspy folder"
    folder.mkdir()
    return folder, write_env_gated_psspy_folder(folder, env_module)


def _log_lines(log_path):
    """The lines of the import log; empty when no import happened (the file is absent)."""
    if not os.path.exists(log_path):
        return []
    with open(log_path, encoding="utf-8") as handle:
        return handle.read().splitlines()


def test_tracer_env_module_closes_the_dll_load_gap(tmp_path):
    """
    The laptop failure on a gated fake psspy, through real -I processes: without PSSE_ENV_MODULE the
    DLL-load ImportError becomes exit 6 (class only); with it the helper runs first and selftest
    passes; a name that is not a plain module name is exit 2 before anything is imported.
    """
    folder, log_path = _write_gated_folder(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    # (1) no key: today's behaviour, the laptop's failure, class only, with the pointer
    config = _write_config(tmp_path, folder, name="nokey.env")
    code, out, err = _run_entry(["selftest", "--config", config], elsewhere)
    assert code == 6, out + err
    assert "PSS/E could not be started: PsseUnavailable: psspy could not be imported (ImportError)" in out
    assert "PSSE_ENV_MODULE is not set" in out
    assert "PSS/E started" not in out
    assert _log_lines(log_path) == []
    for text in (out, err):
        assert str(tmp_path) not in text
        assert "gated psspy folder" not in text
        assert "DLL load failed" not in text and DLL_FAILURE_TEXT not in text
    assert err == ""

    # (2) the key names the helper: helper first, then psspy, six PASS rows
    config = _write_config(tmp_path, folder, {"PSSE_ENV_MODULE": "psse3604"}, name="key.env")
    code, out, err = _run_entry(["selftest", "--config", config], elsewhere)
    assert code == 0, out + err
    lines = out.splitlines()
    assert lines[0].startswith("Python ") and lines[0].endswith(("64-bit", "32-bit"))
    assert lines[1] == "PSS/E started"
    assert len(lines) == 2 + 4 + 6 + 1, out
    assert all("redirected" in note for note in lines[2:6])
    assert all(line.startswith("PASS") for line in lines[6:-1])
    assert lines[-1] == "6 PASS, 0 FAIL, 0 SKIP"
    assert _log_lines(log_path) == ["helper", "psspy"]
    for text in (out, err):
        assert str(tmp_path) not in text
        assert "gated psspy folder" not in text
    assert err == ""

    # (3) a dotted name with .py: refused at configuration reading, nothing imported, no lock file
    os.remove(log_path)
    lock = tmp_path / "bad locks" / "psse_job.lock"
    config = _write_config(
        tmp_path, folder, {"PSSE_ENV_MODULE": "psse3604.py", "PSSE_LOCK_PATH": str(lock)}, name="bad.env")
    code, out, err = _run_entry(["selftest", "--config", config], elsewhere)
    assert code == 2, out + err
    assert "key PSSE_ENV_MODULE" in err
    assert "psse3604.py" not in err  # the value is never echoed (the rule's own example is psse3604, no .py)
    assert out == ""
    assert _log_lines(log_path) == []
    assert not lock.exists()


def test_entry_helper_that_exits_is_reported_by_class_only(tmp_path):
    """A vendor helper that calls sys.exit() (a BaseException) is a start failure naming only SystemExit."""
    folder = tmp_path / "exiting psspy folder"
    folder.mkdir()
    (folder / "psspy.py").write_text(STUB_PSSPY, encoding="utf-8")
    (folder / "exit_helper.py").write_text(
        "import sys\nsys.exit('licence server lic-host-marker unreachable at C:\\\\Program Files\\\\PTI\\\\lic.dat')\n",
        encoding="utf-8")
    config = _write_config(tmp_path, folder, {"PSSE_ENV_MODULE": "exit_helper"})
    code, out, err = _run_entry(["selftest", "--config", config], tmp_path)
    assert code == 6, out + err
    assert "PSS/E could not be started: PsseUnavailable: the module named by PSSE_ENV_MODULE could not be imported (SystemExit)" in out
    assert "PSS/E started" not in out
    for text in (out, err):
        assert "lic-host-marker" not in text and "Program Files" not in text and "lic.dat" not in text
        assert "exit_helper" not in text and str(tmp_path) not in text
    assert err == ""


def test_entry_refuses_an_invalid_env_module_before_any_import(tmp_path):
    """A value that is not a plain module name is exit 2: the key is named, the value is not, nothing is imported or locked."""
    folder, log_path = _write_gated_folder(tmp_path)
    for index, value in enumerate(("psse3604.py", "psse\\3604", "psse 3604", "psse360\u00e9")):
        lock = tmp_path / ("locks%d" % index) / "psse_job.lock"
        config = _write_config(
            tmp_path, folder, {"PSSE_ENV_MODULE": value, "PSSE_LOCK_PATH": str(lock)}, name="bad%d.env" % index)
        code, out, err = _run_entry(["selftest", "--config", config], tmp_path)
        assert code == 2, (value, out, err)
        assert "key PSSE_ENV_MODULE" in err
        assert value not in err and value not in out
        assert out == ""
        assert _log_lines(log_path) == []
        assert not lock.exists()


@pytest.fixture
def _import_sandbox(monkeypatch):
    """In-process proofs: a sys.path copy, the ready variable at 0, psspy and the helper out of sys.modules before and after."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setenv(ENV_READY_VARIABLE, "0")
    monkeypatch.setattr(launcher, "DLL_DIRECTORY_HANDLES", [])
    names = ("psspy", "psse3604")
    for name in names:
        monkeypatch.delitem(sys.modules, name, raising=False)
    importlib.invalidate_caches()
    yield
    for name in names:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


def test_load_psspy_rechecks_the_name_and_imports_the_helper_after_the_search_dirs(tmp_path, _import_sandbox):
    """load_psspy appends no folder itself, re-checks the name before importing it, then imports helper then psspy."""
    import psse_run_hourly

    folder, log_path = _write_gated_folder(tmp_path)
    config = _write_config(tmp_path, folder, {"PSSE_ENV_MODULE": "psse3604"})
    cfg = launcher.read_config(config, "selftest")
    os.makedirs(cfg["PSSE_LOG_DIR"])

    # (a) before the search folders are appended the helper cannot be found
    with pytest.raises(launcher.PsseUnavailable) as excinfo:
        psse_run_hourly.load_psspy(cfg)
    message = str(excinfo.value)
    assert message == "the module named by PSSE_ENV_MODULE could not be imported (ModuleNotFoundError)"
    assert _log_lines(log_path) == [] and "psspy" not in sys.modules

    # (b) a dotted name is refused before any import, although the folder is on the path now
    launcher.add_search_dirs(cfg)
    with pytest.raises(launcher.PsseUnavailable) as excinfo:
        psse_run_hourly.load_psspy(dict(cfg, PSSE_ENV_MODULE="psse3604.py"))
    assert str(excinfo.value) == "PSSE_ENV_MODULE is not a plain module name"
    assert "psse3604.py" not in str(excinfo.value)
    assert _log_lines(log_path) == [] and "psse3604" not in sys.modules and "psspy" not in sys.modules

    # (c) the valid name: the helper first, then psspy
    module = psse_run_hourly.load_psspy(cfg)
    assert module is sys.modules["psspy"]
    assert _log_lines(log_path) == ["helper", "psspy"]


def test_entry_env_module_failures_name_only_the_class(tmp_path):
    """A helper that is missing, raises with a path in its text, or does not make psspy loadable: exit 6, class only."""
    folder, log_path = _write_gated_folder(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    # (i) a name that is not in the folder
    config = _write_config(tmp_path, folder, {"PSSE_ENV_MODULE": "no_such_helper"}, name="missing.env")
    code, out, err = _run_entry(["selftest", "--config", config], elsewhere)
    assert code == 6, out + err
    assert "the module named by PSSE_ENV_MODULE could not be imported (ModuleNotFoundError)" in out
    assert "no_such_helper" not in out and "no_such_helper" not in err
    assert "PSS/E started" not in out and err == ""

    # (ii) a helper that raises RuntimeError whose text names its own file and a licence path
    (folder / "raising_helper.py").write_text(
        "raise RuntimeError('cannot initialise from ' + __file__ + ' with licence C:\\\\Program Files\\\\PTI\\\\lic.dat')\n",
        encoding="utf-8")
    config = _write_config(tmp_path, folder, {"PSSE_ENV_MODULE": "raising_helper"}, name="raising.env")
    code, out, err = _run_entry(["selftest", "--config", config], elsewhere)
    assert code == 6, out + err
    assert "(RuntimeError)" in out
    for text in (out, err):
        assert "cannot initialise" not in text and "raising_helper" not in text
        assert str(tmp_path) not in text and "gated psspy folder" not in text
        assert "Program Files" not in text and "lic.dat" not in text
    assert err == ""

    # (iii) a helper that imports but leaves the gate closed: psspy still fails, and the key is set
    (folder / "noop_helper.py").write_text("pass\n", encoding="utf-8")
    config = _write_config(tmp_path, folder, {"PSSE_ENV_MODULE": "noop_helper"}, name="noop.env")
    code, out, err = _run_entry(["selftest", "--config", config], elsewhere)
    assert code == 6, out + err
    assert "psspy could not be imported (ImportError)" in out
    assert "PSSE_ENV_MODULE is not set" not in out
    assert "DLL load failed" not in out and "DLL load failed" not in err
    assert err == ""
    assert _log_lines(log_path) == []


def test_entry_helper_import_is_configured_and_never_at_import_time(tmp_path):
    """No helper is imported at module level or by a literal name; importing the entry module imports no helper or psspy."""
    with open(ENTRY, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), ENTRY)
    module_level = sorted(
        node.names[0].name if isinstance(node, ast.Import) else node.module
        for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)))
    assert module_level == ["importlib", "os", "psse_job", "sys"], module_level

    sites = sorted(_psspy_import_sites(tree))
    dynamic = [site for site in sites if site[2] == "dynamic"]
    static = [site for site in sites if site[2] == "static"]
    assert len(dynamic) == 1 and len(static) == 1, sites
    assert dynamic[0][1] == static[0][1] == "load_psspy"
    assert dynamic[0][0] < static[0][0]  # the helper is imported before psspy
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "import_module"]
    assert len(calls) == 1 and len(calls[0].args) == 1
    argument = calls[0].args[0]
    assert not (isinstance(argument, ast.Constant) and isinstance(argument.value, str)), "a hard-coded name"

    folder, log_path = _write_gated_folder(tmp_path)
    code = (
        "import importlib.util, os, sys\n"
        "sys.path.append(sys.argv[2])\n"
        "spec = importlib.util.spec_from_file_location('psse_run_hourly', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "print(sorted(name for name in ('psspy', 'psse3604') if name in sys.modules))\n"
        "print(os.path.exists(sys.argv[3]))\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, ENTRY, str(folder), log_path], cwd=str(tmp_path),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT,
        universal_newlines=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["[]", "False"]


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

    # a psspy that fails at import with something other than ImportError, naming its own file: the
    # text reaches the start failure line only with the absolute path replaced
    broken = tmp_path / "broken psspy folder"
    broken.mkdir()
    (broken / "psspy.py").write_text(
        "raise RuntimeError('cannot initialise from ' + __file__ + ' with licence C:\\\\Program Files\\\\PTI\\\\lic.dat')\n",
        encoding="utf-8")
    config = _write_config(tmp_path, broken, name="broken.env")
    code, out, err = _run_entry(["selftest", "--config", config], tmp_path)
    assert code == 6, out + err
    assert "PSS/E could not be started: RuntimeError: cannot initialise from <path>" in out
    for text in (out, err):
        assert str(tmp_path) not in text and "broken psspy folder" not in text
        assert "Program Files" not in text and "lic.dat" not in text
    assert err == ""


def _psspy_import_sites(tree):
    """
    [(line, enclosing function name or None, kind)] of every import of psspy in the syntax tree and
    every dynamic import (a call of __import__ or an import_module): kind is `static` for an import
    statement and `dynamic` for a call.
    """
    found = []

    def visit(node, function):
        for child in ast.iter_child_nodes(node):
            scope = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            if isinstance(child, ast.Import) and any(
                    alias.name.split(".")[0] == "psspy" for alias in child.names):
                found.append((child.lineno, function, "static"))
            if isinstance(child, ast.ImportFrom) and (child.module or "").split(".")[0] == "psspy":
                found.append((child.lineno, function, "static"))
            if isinstance(child, ast.Call) and getattr(child.func, "id", "") in ("__import__", "import_module"):
                found.append((child.lineno, function, "dynamic"))
            if isinstance(child, ast.Call) and getattr(child.func, "attr", "") == "import_module":
                found.append((child.lineno, function, "dynamic"))
            visit(child, scope)

    visit(tree, None)
    return found


def test_entry_imports_psspy_only_in_load_psspy(tmp_path):
    """The imports of psspy and of the configured helper are inside load_psspy, the helper's first; importing the entry module runs none."""
    with open(ENTRY, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), ENTRY)
    sites = _psspy_import_sites(tree)
    assert [(function, kind) for _line, function, kind in sorted(sites)] == [
        ("load_psspy", "dynamic"), ("load_psspy", "static")], sites
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
