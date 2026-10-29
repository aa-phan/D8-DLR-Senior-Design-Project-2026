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
from psse_job import launcher, lock, mapping as mapping_module, probe, psse_api, run_record  # noqa: E402

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


def test_selftest_failures_exit6(tmp_path):
    """A FAIL row, a failed start and a loader error each give exit 6 and print no absolute path."""
    config = _config(tmp_path)

    # a launch function missing: the row says so and the count line counts it
    fake = psse_fake_launch.FakeLaunchPsspy()
    module = _namespace(fake, remove=("report_output",))
    code, out, err = _call(["selftest", "--config", config], _loader(module))
    assert code == 6 and err == ""
    rows = _rows_of(out)
    assert rows["launch:report_output"] == ("FAIL", "missing")
    assert rows["launch:psseinit"][0] == "PASS" and rows["version"][0] == "PASS"
    assert out.splitlines()[-1] == "5 PASS, 1 FAIL, 0 SKIP"
    assert "report_output: missing" in out

    # the version cannot be read, or the adapter cannot be built: FAIL rows, never an exception
    unreadable = _namespace(fake, psseversion=lambda: "not a version")
    code, out, err = _call(["selftest", "--config", config], _loader(unreadable))
    assert code == 6 and _rows_of(out)["version"][0] == "FAIL"

    def no_sentinel():
        raise RuntimeError("no sentinel at C:\\Program Files\\PTI\\PSSE35\\x.dll")

    unbuildable = _namespace(fake, getdefaultint=no_sentinel)
    code, out, err = _call(["selftest", "--config", config], _loader(unbuildable))
    assert code == 6 and _rows_of(out)["version"][0] == "FAIL"
    assert "Program Files" not in out + err and "x.dll" not in out + err

    # psseinit raising: exit 6 and the message names the class, not the text
    broken = psse_fake_launch.FakeLaunchPsspy()
    broken.fake_init_error = RuntimeError("licence C:\\Program Files\\PTI\\lic.dat refused")
    code, out, err = _call(["selftest", "--config", config], _loader(broken))
    assert code == 6
    assert "PSS/E could not be started" in out and "PsseUnavailable" in out
    assert "Program Files" not in out + err and "lic.dat" not in out + err
    assert "PSS/E started" not in out

    # a loader that raises with absolute paths in its text: both paths are replaced, in either style
    def raising(cfg):
        raise RuntimeError(
            "cannot open C:\\Program Files\\PTI PSSE35\\PSSBIN\\license.dat; also /opt/psse/lib/engine.so")

    code, out, err = _call(["selftest", "--config", config], raising)
    assert code == 6
    assert "PSS/E could not be started: RuntimeError: cannot open <path>" in out
    assert out.count("<path>") == 2
    for text in (out, err):
        assert "Program Files" not in text and "license.dat" not in text
        assert "/opt/psse" not in text and "engine.so" not in text


def test_selftest_takes_the_lock(tmp_path):
    """The run lock is held while the loader runs (a second process is refused) and released after."""
    config = _config(tmp_path)
    lock_path = str(tmp_path / "locks" / "psse_job.lock")
    fake = psse_fake_launch.FakeLaunchPsspy()
    seen = []

    def loader(cfg):
        seen.append(lock_probe(cfg["PSSE_LOCK_PATH"]))
        return _loader(fake)(cfg)

    code, out, err = _call(["selftest", "--config", config], loader)
    assert code == 0, out + err
    assert seen == ["locked"]
    assert lock_probe(lock_path) == "acquired"

    # a held lock stops selftest before PSS/E starts: exit 4 and the loader is never called
    holder = Holder(lock_path)
    try:
        assert holder.first_line == "acquired"
        calls = []
        code, out, err = _call(["selftest", "--config", config], _loader(fake, calls))
    finally:
        holder.close()
    assert code == 4 and calls == []
    assert "another instance holds the run lock" in err


# --------------------------------------------------------------------------- probe


def _probe_setup(tmp_path, fake=None, mapping=EXAMPLE, extra=None, name="job.env"):
    """(fake, config path, case path): the placeholder case registered in a folder with a telling name."""
    fake = psse_fake_launch.FakeLaunchPsspy() if fake is None else fake
    folder = tmp_path / "private_case_directory"
    folder.mkdir(exist_ok=True)
    case_path = str(folder / "PLACEHOLDER_CASE.sav")
    with open(case_path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(case_path, fake_module.placeholder_case())
    values = {"PSSE_CASE_PATH": case_path, "PSSE_MAPPING_PATH": mapping}
    values.update(extra or {})
    return fake, _config(tmp_path, values, name=name), case_path


def _spy_on_run_probe(monkeypatch):
    calls = []
    original = probe.run_probe

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(probe, "run_probe", spy)
    return calls


def test_probe_mode_hides_identifiers_by_default(tmp_path, monkeypatch):
    """The default report is probe.format_report as it stands: no bus number, circuit key or folder."""
    fake, config, case_path = _probe_setup(tmp_path)
    calls = _spy_on_run_probe(monkeypatch)
    code, out, err = _call(["probe", "--config", config, "--allow-placeholder"], _loader(fake))
    assert code == 0, out + err
    assert err == ""
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert (args[1], args[3], args[4]) == (case_path, False, False) and not kwargs
    assert args[0] is fake and args[2] is not None

    other = psse_fake_launch.FakeLaunchPsspy()
    other.fake_register_case(case_path, fake_module.placeholder_case())
    expected = probe.format_report(probe.run_probe(
        other, case_path, mapping_module.load_mapping(EXAMPLE, allow_placeholder=True)))
    assert out.strip() == expected
    assert FIVE_DIGITS.search(out) is None
    assert not re.search(r"[0-9]+-[0-9]+-", out)
    assert "private_case_directory" not in out and str(tmp_path) not in out
    assert "PLACEHOLDER_CASE" not in out
    assert "may hold" not in out and "must not be pasted" not in out
    assert out.splitlines()[-1].endswith(", 0 FAIL, 0 SKIP")

    # --show-identifiers is passed through as True and announces itself first
    del calls[:]
    other_fake = psse_fake_launch.FakeLaunchPsspy()
    other_fake.fake_register_case(case_path, fake_module.placeholder_case())
    code, out, err = _call(
        ["probe", "--config", config, "--allow-placeholder", "--show-identifiers"], _loader(other_fake))
    assert code == 0, out + err
    assert calls[0][0][4] is True
    assert "must not be pasted" in out.splitlines()[0]


def test_probe_mode_write_check_and_exit_codes(tmp_path, monkeypatch):
    """The write check is announced, saves nothing and leaves the case file alone; failures are exit 6."""
    fake, config, case_path = _probe_setup(tmp_path)
    before = run_record.file_sha256(case_path)
    calls = _spy_on_run_probe(monkeypatch)
    code, out, err = _call(["probe", "--config", config, "--allow-placeholder", "--write-check"], _loader(fake))
    assert code == 0, out + err
    assert calls[0][0][3] is True
    first = out.splitlines()[0]
    assert "in memory" in first and "never saved" in first and "copy" in first
    names = [call[0] for call in fake.fake_calls]
    assert "branch_chng_3" in names and "scal_2" in names
    assert names.count("case") >= 3  # the load and the two reloads that undo the write checks
    assert "save" not in names and fake.fake_saved_paths == []
    assert run_record.file_sha256(case_path) == before
    rows = _rows_of(out)
    assert rows["rating_write"][0] == "PASS" and rows["scale_load"][0] == "PASS"

    # a write that is not stored is a FAIL row and exit 6
    class WriteIgnored(psse_fake_launch.FakeLaunchPsspy):
        def branch_chng_3(self, ibus, jbus, ckt, intgar, realar, ratings, namear):
            return 0

    ignoring, config2, _case = _probe_setup(tmp_path, fake=WriteIgnored(), name="ignored.env")
    code, out, err = _call(["probe", "--config", config2, "--allow-placeholder", "--write-check"],
                           _loader(ignoring))
    assert code == 6
    assert _rows_of(out)["rating_write"][0] == "FAIL"

    # a mapping that does not exist: one line, no file name; the text only with --show-identifiers
    missing = str(tmp_path / "no_such_mapping_file.json")
    fresh = psse_fake_launch.FakeLaunchPsspy()
    fresh.fake_register_case(case_path, fake_module.placeholder_case())
    code, out, err = _call(
        ["probe", "--config", _config(tmp_path, {"PSSE_CASE_PATH": case_path, "PSSE_MAPPING_PATH": missing},
                                      name="missing.env"), "--allow-placeholder"], _loader(fresh))
    assert code == 6
    assert [line for line in out.splitlines() if "mapping file not usable" in line] == ["mapping file not usable"]
    assert "no_such_mapping_file" not in out + err and str(tmp_path) not in out + err
    code, out, err = _call(
        ["probe", "--config", _config(tmp_path, {"PSSE_CASE_PATH": case_path, "PSSE_MAPPING_PATH": missing},
                                      name="missing.env"), "--allow-placeholder", "--show-identifiers"],
        _loader(fresh))
    assert code == 6
    assert "mapping file not usable" in out and "no_such_mapping_file" in out

    # the committed example mapping is a placeholder: refused without --allow-placeholder
    code, out, err = _call(["probe", "--config", config], _loader(fresh))
    assert code == 6 and "mapping file not usable" in out
    assert "placeholder" not in out
    code, out, err = _call(["probe", "--config", config, "--show-identifiers"], _loader(fresh))
    assert code == 6 and "placeholder" in out

    # PSS/E that cannot start is exit 6 with the same path-free line as selftest
    def failing(cfg):
        raise launcher.PsseUnavailable("psspy could not be imported (ModuleNotFoundError)")

    code, out, err = _call(["probe", "--config", config, "--allow-placeholder"], failing)
    assert code == 6 and "PSS/E could not be started: PsseUnavailable" in out


# --------------------------------------------------------------------------- hold-lock


def _poll(predicate, seconds=15.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_hold_lock_blocks_a_second_run(tmp_path):
    """hold-lock prints locked, keeps the lock for the seconds asked, then releases it; a second start is 4."""
    config = _config(tmp_path)
    lock_path = str(tmp_path / "locks" / "psse_job.lock")
    out, err = io.StringIO(), io.StringIO()
    result = {}

    def hold():
        result["code"] = launcher.main(["hold-lock", "--config", config, "--seconds", "2"], None,
                                       out=out, err=err)

    started = time.monotonic()
    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert _poll(lambda: "locked" in out.getvalue()), err.getvalue()
        with lock.RunLock(lock_path) as meanwhile:
            assert meanwhile.acquired is False
        assert lock_probe(lock_path) == "locked"
    finally:
        thread.join(timeout=30)
    elapsed = time.monotonic() - started
    assert result["code"] == 0 and err.getvalue() == ""
    assert out.getvalue() == "locked\n"
    assert elapsed >= 1.8
    with lock.RunLock(lock_path) as after:
        assert after.acquired is True

    # a second hold-lock (or any start) while another process holds the lock is exit 4
    holder = Holder(lock_path)
    try:
        assert holder.first_line == "acquired"
        code, out2, err2 = _call(["hold-lock", "--config", config, "--seconds", "2"], None)
    finally:
        holder.close()
    assert code == 4 and out2 == ""
    assert "another instance holds the run lock" in err2


def test_hold_lock_seconds_are_capped(tmp_path, monkeypatch):
    """--seconds is a whole number from 1 to 600 (default 60); anything else is a usage error, exit 2."""
    config = _config(tmp_path)
    slept = []
    monkeypatch.setattr(time, "sleep", lambda seconds: slept.append(seconds))
    for bad in ("0", "-1", "abc", "1.5"):
        code, out, err = _call(["hold-lock", "--config", config, "--seconds", bad], None)
        assert code == 2 and out == "", bad
        assert "--seconds" in err
    # 601 would hold the lock for ten minutes if the cap were missing: the sleeps are faked, so the
    # fault shows as a wrong exit code and sleeps, never as a hang
    code, out, err = _call(["hold-lock", "--config", config, "--seconds", "601"], None)
    assert code == 2 and out == "" and slept == []
    parser = launcher.build_parser()
    for good, expected in (("1", 1), ("600", 600)):
        assert parser.parse_args(["hold-lock", "--config", "x", "--seconds", good]).seconds == expected
    assert parser.parse_args(["hold-lock", "--config", "x"]).seconds == 60
    with pytest.raises(Exception) as refused:
        parser.parse_args(["hold-lock", "--config", "x", "--seconds", "601"])
    assert type(refused.value).__name__ == "_UsageError"
    # an accepted value sleeps one second at a time and exits 0
    code, out, err = _call(["hold-lock", "--config", config, "--seconds", "3"], None)
    assert code == 0 and out == "locked\n" and slept == [1, 1, 1]
    # no key is needed: an empty but valid configuration file is accepted
    empty = tmp_path / "empty.env"
    empty.write_text("# nothing\n", encoding="utf-8")
    del slept[:]
    code, out, err = _call(["hold-lock", "--config", str(empty), "--seconds", "1"], None)
    assert code == 0 and slept == [1]
