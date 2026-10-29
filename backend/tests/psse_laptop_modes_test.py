"""
TST-02 / SCH-01 proofs of the laptop's own launcher commands (pss-e-integration Phase 3, plan 03-04):
`selftest`, `probe`, `hold-lock` and the dispatch of `gaps` and `credcheck`, run in process through
`launcher.main` against the fake psspy (backend/tests/psse_fake_launch.py).

Honest scope: the fake proves call shapes, row and exit-code rules and failure handling, not real
PSS/E. That real psspy has `psseinit` and the four output-control functions with these parameter
names, that `report_output(2, file, [0, 0])` redirects anything, and that `os.add_dll_directory`
is needed or enough are UNVERIFIED until runbook step 2 (plan 03-07); the probe on a real case is
UNVERIFIED until runbook steps 3 and 4. The entry script itself is proved in real `-I` processes by
backend/tests/psse_entry_test.py.

Follows backend/tests/psse_launcher_test.py (module-level imports, plain asserts, no test classes;
sys.path is restored through monkeypatch because the launcher appends the PSS/E folders to it).
"""

import io
import os
import re
import sys
import tempfile
import threading
import time
import types

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_launch  # noqa: E402
import psse_fake_psspy as fake_module  # noqa: E402
from psse_lock_test import Holder, probe as lock_probe  # noqa: E402
from psse_job import launcher, lock, probe, psse_api, run_record  # noqa: E402

EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
LAUNCH_ROWS = ["launch:" + row.name for row in launcher.LAUNCH_SURFACE]
SIX_ROWS = ["version"] + LAUNCH_ROWS
FIVE_DIGITS = re.compile(r"(?<![0-9])[0-9]{5}(?![0-9])")


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
    monkeypatch.setattr(launcher, "LAST_START_NOTES", [])


# --------------------------------------------------------------------------- helpers


def _config(tmp_path, values=None, name="job.env"):
    """Write a small config file (every path inside tmp_path); `values` override, None removes a key."""
    merged = {
        "PSSE_PSSPY_DIR": str(tmp_path / "psspy"),
        "PSSE_LOG_DIR": str(tmp_path / "logs"),
        "PSSE_LOCK_PATH": str(tmp_path / "locks" / "psse_job.lock"),
    }
    merged.update(values or {})
    path = tmp_path / name
    path.write_text(
        "\n".join("%s=%s" % (key, value) for key, value in merged.items() if value is not None) + "\n",
        encoding="utf-8")
    return str(path)


def _loader(fake, calls=None):
    """The loader the entry script's load_psspy stands for: start_psspy on `fake`, then return it."""
    def load(cfg):
        if calls is not None:
            calls.append(cfg)
        launcher.start_psspy(fake, int(cfg["PSSE_MAX_BUSES"]),
                             os.path.join(cfg["PSSE_LOG_DIR"], "psse_output.log"))
        return fake
    return load


def _namespace(fake, remove=(), **replace):
    """A module-like object over the fake's bound SURFACE and launch functions, some removed or replaced."""
    names = [surface.name for surface in psse_api.SURFACE] + list(psse_fake_launch.LAUNCH_NAMES)
    members = dict((name, getattr(fake, name)) for name in names)
    for name in remove:
        del members[name]
    members.update(replace)
    return types.SimpleNamespace(**members)


def _call(argv, loader, **kwargs):
    """(exit code, stdout text, stderr text) of one launcher.main call."""
    out, err = io.StringIO(), io.StringIO()
    code = launcher.main(argv, loader, out=out, err=err, **kwargs)
    return code, out.getvalue(), err.getvalue()


def _rows_of(text):
    """{check: (status, detail)} of the report rows in `text` (lines that start with a status word)."""
    table = {}
    for line in text.splitlines():
        match = re.match(r"^(PASS|FAIL|SKIP)\s+(\S+)\s+(.*)$", line)
        if match:
            table[match.group(2)] = (match.group(1), match.group(3))
    return table


def _launch_names(fake):
    return [call[0] for call in fake.fake_launch_calls]


# --------------------------------------------------------------------------- the launch surface


def test_launch_surface_functions_recorded_by_start_psspy(tmp_path):
    """psseinit once with the bus limit, each output function once with (2, log file, [0, 0])."""
    fake = psse_fake_launch.FakeLaunchPsspy()
    log_path = str(tmp_path / "psse_output.log")
    notes = launcher.start_psspy(fake, 20000, log_path)
    assert fake.fake_launch_calls == [
        ("psseinit", (20000,), {}),
        ("report_output", (2, log_path, [0, 0]), {}),
        ("progress_output", (2, log_path, [0, 0]), {}),
        ("alert_output", (2, log_path, [0, 0]), {}),
        ("prompt_output", (2, log_path, [0, 0]), {}),
    ]
    assert len(notes) == 4
    for name, note in zip(psse_fake_launch.OUTPUT_FUNCTIONS, notes):
        assert name in note and "redirected" in note
        assert str(tmp_path) not in note
    assert launcher.LAST_START_NOTES == notes
    # a second call replaces the notes
    other = launcher.start_psspy(psse_fake_launch.FakeLaunchPsspy(), 5, log_path)
    assert launcher.LAST_START_NOTES == other and launcher.LAST_START_NOTES is not notes

    # a missing function and one that raises are notes naming the function (and the class), never fatal
    broken = psse_fake_launch.FakeLaunchPsspy()
    broken.fake_output_error = {"prompt_output"}
    module = _namespace(broken, remove=("alert_output",))
    notes = launcher.start_psspy(module, 20000, "C:\\secret_folder\\psse_output.log")
    joined = "\n".join(notes)
    assert len(notes) == 4
    assert "alert_output" in joined and "missing" in joined
    assert "prompt_output" in joined and "RuntimeError" in joined
    assert "secret_folder" not in joined and "fake output function failure" not in joined
    assert "redirected" in notes[0] and "redirected" in notes[1]


def test_launch_start_failure_is_psse_unavailable(tmp_path):
    """psseinit failing (an exception, or no psseinit at all) is PsseUnavailable naming the class only."""
    fake = psse_fake_launch.FakeLaunchPsspy()
    fake.fake_init_error = RuntimeError("licence file C:\\Program Files\\PTI\\lic.dat is missing")
    with pytest.raises(launcher.PsseUnavailable) as raised:
        launcher.start_psspy(fake, 20000, str(tmp_path / "psse_output.log"))
    assert "RuntimeError" in str(raised.value)
    assert "lic.dat" not in str(raised.value) and "Program Files" not in str(raised.value)
    assert [call[0] for call in fake.fake_launch_calls] == ["psseinit"]  # no output call after a failed start

    module = _namespace(psse_fake_launch.FakeLaunchPsspy(), remove=("psseinit",))
    with pytest.raises(launcher.PsseUnavailable) as missing:
        launcher.start_psspy(module, 20000, str(tmp_path / "psse_output.log"))
    assert "psseinit" in str(missing.value)


def test_launch_check_signatures_rows(tmp_path):
    """Five PASS rows for the fake; FAIL for a missing function or parameter; SKIP when uninspectable."""
    fake = psse_fake_launch.FakeLaunchPsspy()
    rows = launcher.check_launch_signatures(fake)
    assert [row.check for row in rows] == LAUNCH_ROWS
    assert len(rows) == 5 and set(row.status for row in rows) == {"PASS"}
    assert all(isinstance(row, probe.ProbeRow) for row in rows)

    missing = launcher.check_launch_signatures(_namespace(fake, remove=("alert_output",)))
    table = dict((row.check, row) for row in missing)
    assert table["launch:alert_output"].status == "FAIL" and table["launch:alert_output"].detail == "missing"
    assert table["launch:report_output"].status == "PASS"

    class Renamed(psse_fake_launch.FakeLaunchPsspy):
        def report_output(self, islct, filename, options):
            return 0

    renamed = dict((row.check, row) for row in launcher.check_launch_signatures(Renamed()))
    assert renamed["launch:report_output"].status == "FAIL"
    assert "filarg" in renamed["launch:report_output"].detail
    assert renamed["launch:progress_output"].status == "PASS"

    class Uninspectable(object):
        __signature__ = "not a signature"

        def __call__(self, islct, filarg, options):
            return 0

    skipped = dict((row.check, row) for row in launcher.check_launch_signatures(
        _namespace(fake, prompt_output=Uninspectable())))
    assert skipped["launch:prompt_output"].status == "SKIP"

    def catch_all(**kwargs):
        return 0

    keywords = dict((row.check, row) for row in launcher.check_launch_signatures(
        _namespace(fake, psseinit=catch_all)))
    assert keywords["launch:psseinit"].status == "SKIP"
    assert all(row.confidence == "UNVERIFIED" for row in launcher.LAUNCH_SURFACE)


# --------------------------------------------------------------------------- selftest


def test_selftest_reports_version_and_surface(tmp_path):
    """Python line, started line, notes, then exactly six rows and a count line over them; exit 0."""
    fake = psse_fake_launch.FakeLaunchPsspy()
    calls = []
    code, out, err = _call(["selftest", "--config", _config(tmp_path)], _loader(fake, calls))
    assert code == 0, out + err
    assert err == ""
    assert len(calls) == 1
    lines = out.splitlines()
    bits = 64 if sys.maxsize > 2 ** 32 else 32
    assert lines[0] == "Python %s, %d-bit" % (sys.version.split()[0], bits)
    assert lines[1] == "PSS/E started"
    notes = lines[2:6]
    assert len(notes) == 4 and all("redirected" in note for note in notes)
    rows = lines[6:-1]
    assert [line.split()[1] for line in rows] == SIX_ROWS
    assert all(line.startswith("PASS") for line in rows)
    assert "PSS/E 35.6.0" in rows[0]
    assert lines[-1] == "6 PASS, 0 FAIL, 0 SKIP"
    assert len(lines) == 2 + 4 + 6 + 1
    assert _launch_names(fake) == ["psseinit"] + list(psse_fake_launch.OUTPUT_FUNCTIONS)
    assert fake.fake_launch_calls[0][1] == (20000,)
    assert str(tmp_path) not in out
    # the notes are replaced by every selftest, never carried over from an earlier call
    assert launcher.LAST_START_NOTES == notes
