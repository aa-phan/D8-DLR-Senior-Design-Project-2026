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

import os
import subprocess
import sys
import threading

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

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
