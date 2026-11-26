"""
OPS-02, the owner commands of the hourly runner (pandapower-solver Phase 5, plan 05-05; decisions
D-08 and D-11): `bundle` turns the private tree into the four base64 secret files, and `scan-log`
scans a downloaded Actions log. Both run on the owner's machine against `data/private`, never on a
runner.

Every private-looking file here is synthetic and lives in a throwaway git repository under the
test's `tmp_path` (whose `.gitignore` holds the private-data rule); nothing here opens this
checkout's `data/private`. The planted values (session hashes, NET-03, parity and evidence text)
come from `pandapower_hourly_fixture.PLANTED`, assembled from pieces. Honest scope: the tests show
what the bundle keeps and drops, that the four files drive a dry run on the real engine, and that
the commands print only vocabulary lines; they do not prove the owner's real files are shaped like
the synthetic ones. No test asserts a file mode or pins file bytes (Windows).
"""

import os
import sys
import tempfile

import pytest

pandapower = pytest.importorskip("pandapower")

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import base64  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402

import pandapower_hourly_fixture as fixture  # noqa: E402
import pandapower_replay_fixture as replay_fixture  # noqa: E402
import pandapower_study_fixture as study_fixture  # noqa: E402
from pandapower_job import cli, convert, engine, hourly  # noqa: E402

WORDS = ("network", "mapping", "settings", "scaling")
SIZE_LINE = re.compile(r"bundle: (network|mapping|settings|scaling) bytes=([0-9]+) base64=([0-9]+) "
                       r"(fits|does not fit)\Z")


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _clock():
    return lambda: fixture.FIXED_NOW


def _vocabulary_ok(lines):
    return all(any(pattern.match(line) for pattern in hourly.HOURLY_LINE_PATTERNS) for line in lines)


def _world(tmp_path, name="repo", **options):
    repo = replay_fixture.make_repo(tmp_path / name)
    return repo, fixture.private_tree(repo, **options)


def _secrets_root(repo):
    return os.path.join(repo, "data", "private", "pandapower", hourly.BUNDLE_DIR)


def _owner(argv, repo, environ=None, **seams):
    """(exit code, printed lines) of one owner command on the throwaway repository; every printed
    line is asserted to be in the vocabulary."""
    buffer = io.StringIO()
    options = dict(clock=_clock(), sink=False)
    options.update(seams)
    code = hourly.main(list(argv), out=buffer, environ={} if environ is None else environ,
                       repo_root=repo, **options)
    lines = buffer.getvalue().splitlines()
    assert _vocabulary_ok(lines)
    return code, lines


def _bundle_folder(repo):
    root = _secrets_root(repo)
    names = sorted(os.listdir(root))
    assert len(names) == 1 and names[0].startswith(hourly.BUNDLE_PREFIX)
    return os.path.join(root, names[0])


def _file_names():
    return sorted(name + ".txt" for _word, name, _file, _cap in hourly.SECRET_ENV)


def _read_text(path):
    with open(path, "r", encoding="ascii", newline="") as handle:
        return handle.read()


def _decoded(folder):
    """word -> decoded bytes of the bundle file of that word."""
    found = {}
    for word, name, _file, _cap in hourly.SECRET_ENV:
        found[word] = base64.b64decode(_read_text(os.path.join(folder, name + ".txt")),
                                       validate=True)
    return found


def _sha256_of(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


# -- the tracer ------------------------------------------------------------------------------------


def test_tracer_bundle_secrets_drive_a_dry_run_end_to_end(tmp_path):
    repo, layout = _world(tmp_path)
    code, lines = _owner(["bundle"], repo)
    assert code == 0
    assert len(lines) == 6
    for line, word in zip(lines[:4], WORDS):
        match = SIZE_LINE.match(line)
        assert match is not None and match.group(1) == word and match.group(4) == "fits"
    assert lines[4:] == ["bundle: verified", "bundle: written"]
    assert os.listdir(tempfile.gettempdir()) == []

    folder = _bundle_folder(repo)
    assert os.path.basename(folder) == hourly.BUNDLE_PREFIX + fixture.FIXED_NOW.strftime(
        "%Y%m%dT%H%M%SZ")
    assert sorted(os.listdir(folder)) == _file_names()
    environ = {}
    for _word, name, _file, _cap in hourly.SECRET_ENV:
        text = _read_text(os.path.join(folder, name + ".txt"))
        assert text and "\n" not in text and "\r" not in text and text == text.strip()
        base64.b64decode(text, validate=True)
        environ[name] = text
    environ.update(fixture.read_env())

    # the four files, as the workflow would hand them over, drive a dry run on the real engine
    captured = []

    def prepare(backend, case_path, mapping_path, allow_placeholder=False, clock=None):
        prepared = engine.prepare_run(backend, case_path, mapping_path, allow_placeholder, clock)
        captured.append(prepared)
        return prepared

    buffer = io.StringIO()
    run_code = hourly.main(["run"], out=buffer, environ=environ, prepare=prepare,
                           fetch=fixture.fake_fetch_for(fixture.FIXED_NOW), clock=_clock(),
                           sink=False)
    run_lines = buffer.getvalue().splitlines()
    assert run_code == 0
    assert _vocabulary_ok(run_lines)
    assert run_lines[0] == "mode: dry" and run_lines[1] == "inputs: ok"
    assert "study: ok" in run_lines
    assert run_lines[-1] == "dry run: nothing was written to the database"
    assert len(captured) == 1
    assert captured[0].case_sha256 == _sha256_of(layout.network)
    assert captured[0].mapping_sha256 == _sha256_of(layout.mapping)
    assert os.listdir(tempfile.gettempdir()) == []


# -- what the bundle keeps -------------------------------------------------------------------------


def test_bundle_keeps_only_the_settings_and_detail_keys(tmp_path):
    repo, layout = _world(tmp_path)
    code, _lines = _owner(["bundle"], repo)
    assert code == 0
    decoded = _decoded(_bundle_folder(repo))

    settings = json.loads(decoded["settings"].decode("ascii"))
    scaling = json.loads(decoded["scaling"].decode("ascii"))
    assert set(settings) == {"settings", cli.REPORT_MARKER}
    assert set(settings["settings"]) == set(engine._SETTINGS_FIELDS)
    assert set(scaling) == set(engine._DETAIL_FIELDS) | {cli.REPORT_MARKER}
    with open(layout.report, "r", encoding="utf-8") as handle:
        assert settings["settings"] == json.load(handle)["settings"]

    # the network and the mapping travel exactly as the owner's files are
    with open(layout.network, "rb") as handle:
        assert decoded["network"] == handle.read()
    with open(layout.mapping, "rb") as handle:
        assert decoded["mapping"] == handle.read()

    # none of the check report's other keys reaches a secret (T-05-19)
    planted = [fixture.PLANTED[key] for key in (
        "session_case_sha256", "session_mapping_sha256", "net03_text", "evidence_text")]
    planted.append(repr(fixture.PLANTED["parity_value"]))
    planted.extend(("session", "net03", "parity", "evidence"))
    for word in WORDS:
        text = decoded[word].decode("ascii")
        for value in planted:
            assert value not in text, "the %s bundle holds a planted report value" % word
    for name in _file_names():
        raw = _read_text(os.path.join(_bundle_folder(repo), name))
        for value in planted:
            assert value not in raw


# -- refusals --------------------------------------------------------------------------------------


def _mapping_placeholder(layout):
    study_fixture.write_placeholder_mapping(os.path.dirname(layout.mapping))


def _settings_placeholder(layout):
    with open(layout.report, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    document["settings"]["sources"]["enforce_q_lims"] = "placeholder: not decided"
    with open(layout.report, "w", encoding="utf-8") as handle:
        json.dump(document, handle)


def _network_garbage(layout):
    with open(layout.network, "wb") as handle:
        handle.write(b"{}")


@pytest.mark.parametrize("name, prepare, options, environ, argv, expected", [
    ("in_ci", None, {}, {"GITHUB_ACTIONS": "true"}, ["bundle"], "bundle: refused (in_ci)"),
    ("records_missing", lambda layout: shutil.rmtree(layout.check_dir), {}, None, ["bundle"],
     "bundle: refused (records_missing)"),
    ("mapping_missing", lambda layout: os.remove(layout.mapping), {}, None, ["bundle"],
     "bundle: refused (mapping_missing)"),
    ("mapping_refused", _mapping_placeholder, {}, None, ["bundle"],
     "bundle: refused (mapping_refused)"),
    ("placeholder_source", _settings_placeholder, {}, None, ["bundle"],
     "records: refused (placeholder_source)"),
    ("preflight_refused", None, {"study": {"thermal": {"basis": "mva"}}}, None, ["bundle"],
     "bundle: refused (preflight_refused)"),
    ("network_refused", _network_garbage, {}, None, ["bundle"], "bundle: refused (network_refused)"),
    ("private_path", None, {}, None, "OUTSIDE", "bundle: refused (private_path)"),
])
def test_bundle_refusals_write_nothing(tmp_path, name, prepare, options, environ, argv, expected):
    repo, layout = _world(tmp_path, name, **options)
    if prepare is not None:
        prepare(layout)
    if argv == "OUTSIDE":
        outside = str(tmp_path / "outside" / "check_20261120T000000Z")
        shutil.copytree(layout.check_dir, outside)
        argv = ["bundle", "--check-dir", outside]
    code, lines = _owner(argv, repo, environ=environ)
    assert code == 2, "%s: exit %d" % (name, code)
    assert lines == [expected], "%s: wrong lines" % name
    assert not os.path.exists(_secrets_root(repo)), "%s: something was written" % name
    assert os.listdir(tempfile.gettempdir()) == []


def test_bundle_second_run_in_the_same_second_is_refused_as_existing(tmp_path):
    repo, _layout = _world(tmp_path)
    assert _owner(["bundle"], repo)[0] == 0
    folder = _bundle_folder(repo)
    before = sorted((name, _read_text(os.path.join(folder, name))) for name in os.listdir(folder))
    code, lines = _owner(["bundle"], repo)
    assert code == 2
    assert lines[-1] == "bundle: refused (exists)" and "bundle: written" not in lines
    assert _bundle_folder(repo) == folder
    assert before == sorted((name, _read_text(os.path.join(folder, name)))
                            for name in os.listdir(folder))


# -- the secret limit ------------------------------------------------------------------------------


def test_bundle_secret_limit_boundary(tmp_path, monkeypatch):
    repo, layout = _world(tmp_path)
    length = os.path.getsize(layout.network)
    longest = 4 * ((length + 2) // 3)
    assert longest > 30000, "precondition not reached: the fixture network is a realistic size"

    # exactly at the limit: every value fits and the bundle is written
    monkeypatch.setattr(convert, "SECRET_LIMIT_BYTES", longest)
    code, lines = _owner(["bundle"], repo)
    assert code == 0
    sizes = [SIZE_LINE.match(line) for line in lines[:4]]
    assert all(match is not None and match.group(4) == "fits" for match in sizes)
    assert int(sizes[0].group(3)) == longest
    assert lines[4:] == ["bundle: verified", "bundle: written"]
    assert os.path.isdir(_bundle_folder(repo))

    # one character over: the whole bundle is refused and nothing new is written
    other, _ = _world(tmp_path, "other")
    monkeypatch.setattr(convert, "SECRET_LIMIT_BYTES", longest - 1)
    code, lines = _owner(["bundle"], other)
    assert code == 2
    first = SIZE_LINE.match(lines[0])
    assert first is not None and first.group(1) == "network" and first.group(4) == "does not fit"
    assert all(SIZE_LINE.match(line).group(4) == "fits" for line in lines[1:4])
    assert lines[4:] == ["bundle: refused (too_large)"]
    assert not os.path.exists(_secrets_root(other))
