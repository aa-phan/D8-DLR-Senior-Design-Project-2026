"""
PSE-01 proofs of the laptop session spine (pandapower-solver Phase 1, plan 01-02) on a fake psspy:
`psse_session.session.main` from argv through the call gate to one verified zip and a masked
summary, the output bundle (`psse_session.bundle`), the entry script
`backend/psse_pandapower_session.py` in a real `python -I` subprocess, the import and syntax
gates, and the edge cases (isolation, interrupt, collision, errors).

Honest scope: the fake (backend/tests/psse_session_fake.py) models call shapes, return shapes and
failure handling only. That real PSS/E 36.4 has the SESSION_SURFACE functions with these parameter
names, that any RAW export form writes a RAW file, and which revision it writes, are all UNVERIFIED
until the session of plan 01-10. Every test uses the committed 9xxxx placeholder series and the
committed placeholder mapping; nothing here holds a real bus number, path or name. Plain asserts,
no classes, no network. Section terminators of RAW text are assembled by the fake from pieces.
"""

import ast
import datetime
import glob
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import zipfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_session_fake  # noqa: E402
from psse_contract_test import (  # noqa: E402
    _collect_imports, _generic_annotation_problems, _new_feature_problems)
from psse_fake_launch import STUB_PSSPY_SOURCE  # noqa: E402
from psse_fake_psspy import FakePsspy, placeholder_case  # noqa: E402
from psse_job import launcher, psse_api  # noqa: E402
from psse_session import bundle, session  # noqa: E402

ENTRY = os.path.join(_BACKEND, "psse_pandapower_session.py")
SESSION_DIR = os.path.join(_BACKEND, "psse_session")
TIMEOUT = 60
# The standard-library modules the laptop session may import: no socket, urllib, http, ssl or
# subprocess (the session opens no connection and starts no process).
SESSION_STDLIB_ALLOWED = frozenset([
    "__future__", "argparse", "collections", "datetime", "functools", "hashlib", "inspect", "io",
    "json", "math", "os", "re", "shutil", "sys", "time", "zipfile",
])
FAKE_PATH_TEXT = "C:/Users/fakeuser/fakehost/private"
EXAMPLE_MAPPING = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
FIXED_NOW = datetime.datetime(2026, 11, 16, 15, 0, 0, tzinfo=datetime.timezone.utc)
STAMP = "20261116T150000Z"
CASE_NAME = "zz_case_file.sav"
MAP_NAME = "zz_mapping_file.json"
PLACEHOLDER_BUS_TEXT = ("90000", "90001", "90002")


def _fixed_clock():
    return FIXED_NOW


def _sha256_file(path):
    with open(str(path), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class World(object):
    """A configuration, a case, a mapping copy, an output folder and a fake psspy in tmp_path."""

    def __init__(self, tmp_path, **fake_options):
        self.tmp_path = tmp_path
        psspy_dir = tmp_path / "psspy dir"
        psspy_dir.mkdir()
        case_dir = tmp_path / "case dir"
        case_dir.mkdir()
        self.case = case_dir / CASE_NAME
        self.case.write_bytes(b"fake case bytes")
        self.fake = psse_session_fake.FakeSessionPsspy(**fake_options)
        self.fake.fake_register_case(str(self.case), placeholder_case())
        self.config = tmp_path / "session.env"
        self.config.write_text(
            "PSSE_PSSPY_DIR=%s\nPSSE_CASE_PATH=%s\nPSSE_LOG_DIR=%s\n" % (
                psspy_dir, self.case, tmp_path / "console logs"), encoding="utf-8")
        map_dir = tmp_path / "map dir"
        map_dir.mkdir()
        self.mapping = map_dir / MAP_NAME
        shutil.copy(EXAMPLE_MAPPING, str(self.mapping))
        self.out = tmp_path / "out"
        self.out.mkdir()
        self.loaded_cfgs = []

    def loader(self, cfg):
        self.loaded_cfgs.append(dict(cfg))
        return self.fake

    def argv(self, mode="run", *extra):
        return [mode, "--config", str(self.config), "--mapping", str(self.mapping),
                "--out-dir", str(self.out), "--allow-placeholder"] + list(extra)

    def zip_path(self):
        return self.out / (bundle.SESSION_PREFIX + STAMP + ".zip")


def _run(world, monkeypatch, *extra, **kwargs):
    """(code, stdout, stderr) of session.main on the world; sys.path is restored afterwards."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    out, err = io.StringIO(), io.StringIO()
    mode = kwargs.pop("mode", "run")
    code = session.main(world.argv(mode, *extra), kwargs.pop("loader", world.loader),
                        out=out, err=err, clock=kwargs.pop("clock", _fixed_clock))
    assert not kwargs
    return code, out.getvalue(), err.getvalue()


def _read_zip(path):
    """(manifest dict, {member: bytes}) of the zip at `path`."""
    with zipfile.ZipFile(str(path)) as archive:
        contents = dict((name, archive.read(name)) for name in archive.namelist())
    manifest = bundle.read_manifest(contents.pop(bundle.MANIFEST_NAME))
    return manifest, contents


def _summary_lines_match(text):
    for line in text.splitlines():
        assert any(pattern.match(line) for pattern in bundle.SUMMARY_LINE_PATTERNS), line


def test_fake_session_surface_matches_session_surface():
    """The fake has exactly the SESSION_SURFACE calls on top of FakePsspy's, with the same parameter names."""
    import inspect
    base = set(name for name in dir(FakePsspy) if not name.startswith("_") and callable(
        getattr(FakePsspy, name)))
    extra = set(name for name in dir(psse_session_fake.FakeSessionPsspy)
                if not name.startswith(("_", "fake_")) and callable(
                    getattr(psse_session_fake.FakeSessionPsspy, name))) - base
    assert extra == set(session.SESSION_SURFACE_NAMES)
    assert len(session.SESSION_SURFACE) == 7
    for row in session.SESSION_SURFACE:
        function = getattr(psse_session_fake.FakeSessionPsspy, row.name)
        parameters = tuple(inspect.signature(function).parameters)[1:]
        assert parameters == row.parameters, row.name
        assert row.confidence in ("LOW", "MEDIUM")
        assert row.evidence
    assert session.ALLOWED_NAMES == psse_api.SURFACE_NAMES | session.SESSION_SURFACE_NAMES


def test_fake_raw_counts(tmp_path):
    """count_raw on the fake RAW returns the fake case's counts; the file is a revision 33 header first."""
    case = placeholder_case()
    path = tmp_path / "fake.raw"
    assert psse_session_fake.write_fake_raw(case, str(path)) > 0
    data = path.read_bytes()
    assert session._header_revision(data) == 33
    assert session.count_raw(data) == {
        "buses": len(case.buses), "loads": len(case.loads), "fixed_shunts": 0,
        "machines": 1 + len(case.gens), "lines": len(case.branches), "transformers": 0,
        "three_winding": 0, "switched_shunts": 0, "areas": 1, "controlling_transformers": 0}


def test_count_raw_transformers_and_unknowns():
    """Two- and three-winding transformer records and controlling windings are counted; the rest fails soft."""
    transformer_lines = [
        "90001,90002,0,'1 ',1,1,1,0.0,0.0,2,'XFA',1,1,1.0",
        "0.001,0.05,100.0",
        "1.0,345.0,0.0,100.0,100.0,100.0,1,0,1.1,0.9,1.1,0.9,33,0,0.0,0.0,0.0",
        "1.0,345.0",
        "90001,90002,90003,'2 ',1,1,1,0.0,0.0,2,'XFB',1,1,1.0",
        "0.001,0.05,100.0,0.001,0.05,100.0,0.001,0.05,100.0,1.0,0.0",
        "1.0,345.0,0.0,100.0,100.0,100.0,0,0,1.1,0.9,1.1,0.9,33,0,0.0,0.0,0.0",
        "1.0,345.0,0.0,100.0,100.0,100.0,0,0,1.1,0.9,1.1,0.9,33,0,0.0,0.0,0.0",
        "1.0,345.0,0.0,100.0,100.0,100.0,0,0,1.1,0.9,1.1,0.9,33,0,0.0,0.0,0.0",
    ]
    case = placeholder_case()
    data = psse_session_fake.fake_raw_bytes(case, 33, transformer_lines)
    counts = session.count_raw(data)
    assert (counts["transformers"], counts["three_winding"], counts["controlling_transformers"]) == (2, 1, 1)
    assert counts["buses"] == len(case.buses)
    # a file cut inside the area section: the unterminated section is not counted
    cut = data[:data.index(b"AREA1")]
    cut_counts = session.count_raw(cut)
    assert cut_counts["areas"] is None and cut_counts["buses"] == len(case.buses)
    # a transformer record that runs past the end of its section
    broken = psse_session_fake.fake_raw_bytes(case, 33, transformer_lines[:3])
    broken_counts = session.count_raw(broken)
    assert broken_counts["transformers"] is None and broken_counts["three_winding"] is None
    assert broken_counts["lines"] == len(case.branches)
    # revision 35: sections are named by their begin phrase, the unnamed first one is not guessed
    newer = session.count_raw(psse_session_fake.fake_raw_bytes(case, 35))
    assert newer["buses"] is None and newer["loads"] == len(case.loads)
    assert all(value is None for value in session.count_raw(b"not a raw file").values())
    assert all(value is None for value in session.count_raw(b"").values())


def test_tracer_session_run_network_section_to_zip_and_masked_summary(tmp_path, monkeypatch):
    """argv to the gate, the fake psspy and its own RAW export, into one verified zip and a masked summary."""
    monkeypatch.setattr(session, "SECTIONS", ("network",))
    world = World(tmp_path)
    case_hash = _sha256_file(world.case)
    code, out, err = _run(world, monkeypatch)
    assert code == 0, out + err
    # the one file in OUT is the zip
    assert sorted(os.listdir(str(world.out))) == [bundle.SESSION_PREFIX + STAMP + ".zip"]
    manifest, members = _read_zip(world.zip_path())
    assert sorted(members) == sorted(manifest["members"])
    assert "network/network.raw" in members and "network/export_attempts.json" in members
    for name, entry in manifest["members"].items():
        assert hashlib.sha256(members[name]).hexdigest() == entry["sha256"], name
        assert len(members[name]) == entry["bytes"]
    raw = members["network/network.raw"]
    assert raw and session._header_revision(raw) == 33
    attempts = json.loads(members["network/export_attempts.json"].decode("ascii"))
    assert attempts["selected"] == "rawd_2_forum_positional"
    assert [item["status"] for item in attempts["attempts"]] == ["failed", "failed", "ok"]
    # the manifest's network section
    (network,) = manifest["sections"]
    case = placeholder_case()
    assert network["name"] == "network" and network["status"] == "ok"
    assert network["counts"]["buses"] == len(case.buses)
    assert network["counts"]["lines"] == len(case.branches)
    assert network["counts"]["transformers"] == 0
    assert manifest["case_sha256"] == case_hash and manifest["mapping_placeholder"] is True
    # nothing else is left: mapping copy, work folder; the case file is unchanged
    assert not world.mapping.exists()
    assert [name for name in os.listdir(str(world.out)) if name.startswith(bundle.SESSION_PREFIX)
            ] == [bundle.SESSION_PREFIX + STAMP + ".zip"]
    assert _sha256_file(world.case) == case_hash
    # the console log went into the work folder, not the configured log folder
    assert world.loaded_cfgs[0]["PSSE_LOG_DIR"].endswith(bundle.SESSION_PREFIX + STAMP)
    # the summary: fixed lines only, ASCII, no identifier, no path
    _summary_lines_match(out)
    out.encode("ascii")
    assert "mapping copy: deleted" in out and "work folder: deleted" in out and "zip: written" in out
    for needle in PLACEHOLDER_BUS_TEXT + (str(tmp_path), CASE_NAME, MAP_NAME):
        assert needle not in out and needle not in err
    # every psspy call went through the allow-list
    assert set(name for name, _a, _k in world.fake.fake_calls) <= session.ALLOWED_NAMES


# ──────────────────────────────────────────────────────────────────────────────
# The entry script in a real `python -I` subprocess
# ──────────────────────────────────────────────────────────────────────────────

def _run_entry(args, cwd, timeout=TIMEOUT):
    """(code, stdout, stderr) of `python -I -B backend/psse_pandapower_session.py ARGS` run in `cwd`."""
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


def test_entry_script_runs_under_isolated_mode_with_a_stub_psspy(tmp_path):
    """PSS/E starts (stub), every section fails (the stub has no case function), one zip is left."""
    stub = tmp_path / "stub psspy folder"
    stub.mkdir()
    (stub / "psspy.py").write_text(STUB_PSSPY_SOURCE, encoding="utf-8")
    case = tmp_path / "case dir"
    case.mkdir()
    case_file = case / CASE_NAME
    case_file.write_bytes(b"stub case bytes")
    config = tmp_path / "session.env"
    config.write_text("PSSE_PSSPY_DIR=%s\nPSSE_CASE_PATH=%s\n" % (stub, case_file), encoding="utf-8")
    mapping = tmp_path / MAP_NAME
    shutil.copy(EXAMPLE_MAPPING, str(mapping))
    out_dir = tmp_path / "desktop"
    out_dir.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    code, out, err = _run_entry(
        ["run", "--config", str(config), "--mapping", str(mapping), "--out-dir", str(out_dir),
         "--allow-placeholder"], elsewhere)
    assert code == 1, out + err
    zips = [name for name in os.listdir(str(out_dir)) if name.endswith(".zip")]
    assert len(zips) == 1 and sorted(os.listdir(str(out_dir))) == zips
    manifest, members = _read_zip(out_dir / zips[0])
    assert [item["name"] for item in manifest["sections"]] == list(session.SECTIONS)
    for item in manifest["sections"]:
        assert item["status"] == "failed" and item["detail"], item["name"]
    assert "network/network.raw" not in members
    assert not mapping.exists()
    _summary_lines_match(out)
    for text in (out, err):
        assert str(tmp_path) not in text and "stub psspy folder" not in text
        assert CASE_NAME not in text and MAP_NAME not in text


def test_entry_usage_error_exit2(tmp_path):
    """No arguments: usage on stderr, exit 2; the file is short and reaches psspy only through the loader."""
    code, out, err = _run_entry([], tmp_path)
    assert code == 2 and "usage" in err and out == ""
    code, out, err = _run_entry(["run", "--bogus-flag"], tmp_path)
    assert code == 2 and "usage" in err
    with open(ENTRY, encoding="utf-8") as handle:
        text = handle.read()
    assert len(text.splitlines()) < 60
    assert "psse_run_hourly.load_psspy" in text


# ──────────────────────────────────────────────────────────────────────────────
# Syntax, import and psspy gates (written over source text so a planted violation proves each)
# ──────────────────────────────────────────────────────────────────────────────

def _session_files():
    return sorted(glob.glob(os.path.join(SESSION_DIR, "*.py"))) + [ENTRY]


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _session_import_problems(source, filename, entry=False):
    allowed = set(SESSION_STDLIB_ALLOWED) | {"psse_job", "psse_session"}
    if entry:
        allowed.add("psse_run_hourly")
    problems = []
    for name, relative, _in_function, line in _collect_imports(
            ast.parse(source, filename).body, False, []):
        if not relative and name not in allowed:
            problems.append("%s:%d imports %s, outside the session allow-list" % (filename, line, name))
    return problems


def _psspy_import_sites(tree):
    """[(line, enclosing function or None, kind)] of every psspy import and dynamic import."""
    found = []

    def visit(node, function):
        for child in ast.iter_child_nodes(node):
            scope = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            if isinstance(child, ast.Import) and any(
                    alias.name.split(".")[0] == "psspy" for alias in child.names):
                found.append((child.lineno, function, "static"))
            if isinstance(child, ast.ImportFrom) and (child.module or "").split(".")[0] == "psspy":
                found.append((child.lineno, function, "static"))
            if isinstance(child, ast.Call) and getattr(child.func, "id", "") in (
                    "__import__", "import_module"):
                found.append((child.lineno, function, "dynamic"))
            if isinstance(child, ast.Call) and getattr(child.func, "attr", "") == "import_module":
                found.append((child.lineno, function, "dynamic"))
            visit(child, scope)

    visit(tree, None)
    return found


def test_session_files_parse_as_python37_and_import_only_the_allow_list():
    files = _session_files()
    assert len(files) >= 4
    problems = []
    for path in files:
        source = _read(path)
        name = os.path.relpath(path, _ROOT).replace(os.sep, "/")
        try:
            ast.parse(source, name, feature_version=(3, 7))
        except SyntaxError as exc:
            problems.append("%s does not parse as Python 3.7: %s" % (name, exc))
        problems += _generic_annotation_problems(source, name)
        problems += _new_feature_problems(source, name)
        problems += _session_import_problems(source, name, entry=(path == ENTRY))
    assert problems == []


def test_session_import_gate_flags_planted_violations():
    for text in ("import socket\n", "import urllib.request\n", "from http import client\n",
                 "import subprocess\n", "import psycopg\n", "import pandapower\n",
                 "import pandapower_job\n", "def f():\n    import psspy\n", "import ssl\n",
                 "import tempfile\n"):
        assert len(_session_import_problems(text, "planted.py")) == 1, text
    assert len(_session_import_problems("import psse_run_hourly\n", "planted.py")) == 1
    assert _session_import_problems("import psse_run_hourly\n", "planted.py", entry=True) == []
    allowed = ("from __future__ import annotations\nimport json, os, zipfile\n"
               "from psse_job import constants\nfrom psse_session import bundle\nfrom . import x\n")
    assert _session_import_problems(allowed, "planted.py") == []


def test_session_never_imports_psspy(tmp_path):
    """No file of the session imports psspy; importing the entry module in -I leaves none in sys.modules."""
    for path in _session_files():
        assert _psspy_import_sites(ast.parse(_read(path), path)) == [], path
    code = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('psse_pandapower_session', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "print(sorted(name for name in sys.modules if name.split('.')[0] == 'psspy'))\n"
        "print(callable(module.main))\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, ENTRY], cwd=str(tmp_path), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT, universal_newlines=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["[]", "True"]


# ──────────────────────────────────────────────────────────────────────────────
# Read-only, network-free, gated
# ──────────────────────────────────────────────────────────────────────────────

def _snapshot(root):
    """{relative path: (size, sha256)} of every file under `root`."""
    found = {}
    for folder, _dirs, files in os.walk(str(root)):
        for name in files:
            path = os.path.join(folder, name)
            found[os.path.relpath(path, str(root))] = (os.path.getsize(path), _sha256_file(path))
    return found


def test_no_network_during_a_session(tmp_path, monkeypatch):
    """With every connect patched to raise, a full fake run of the network section still exits 0."""
    def refuse(*args, **kwargs):
        raise AssertionError("the session opened a connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(session, "SECTIONS", ("network",))
    world = World(tmp_path)
    code, out, err = _run(world, monkeypatch)
    assert code == 0, out + err


def test_session_writes_only_its_zip_and_removes_only_the_mapping_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "SECTIONS", ("network",))
    world = World(tmp_path)
    before = _snapshot(tmp_path)
    code, out, err = _run(world, monkeypatch)
    assert code == 0, out + err
    after = _snapshot(tmp_path)
    added = set(after) - set(before)
    removed = set(before) - set(after)
    assert added == {os.path.join("out", bundle.SESSION_PREFIX + STAMP + ".zip")}
    assert removed == {os.path.join("map dir", MAP_NAME)}
    for name in set(before) & set(after):
        assert before[name] == after[name], "a file changed"
    assert world.fake.fake_saved_paths == []


def test_gate_refuses_unlisted_calls_and_outside_paths(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    case = tmp_path / CASE_NAME
    case.write_bytes(b"x")
    other = tmp_path / "other.sav"
    other.write_bytes(b"x")
    fake = psse_session_fake.FakeSessionPsspy(raw_forms=("rawd_2_forum_positional",))
    fake.fake_register_case(str(case), placeholder_case())
    fake.fake_register_case(str(other), placeholder_case())
    gated = session.GatedPsspy(fake, str(work), str(case))
    with pytest.raises(session.SessionRefused):
        gated.fnsl_typo
    with pytest.raises(session.SessionRefused) as refused:
        gated.psseinit
    assert "psseinit" in str(refused.value) and str(tmp_path) not in str(refused.value)
    sibling = tmp_path / "work_evil"
    sibling.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    os.symlink(str(outside_dir), str(work / "link"))
    forum = [1, 1, 1, 0, 0, 0, 0]
    outside_paths = [str(tmp_path / "outside.sav"), str(sibling / "x.raw"),
                     str(work / ".." / "escape.raw"), str(work / "link" / "x.raw"), str(work)]
    before = len(fake.fake_calls)
    for path in outside_paths:
        for call in (
                lambda: gated.save(path),
                lambda: gated.save(sfile=path),
                lambda: gated.rawd_2(0, 1, forum, 0, path),
                lambda: gated.rawd_2(sid=0, all=1, status=forum, out=0, ofile=path),
                lambda: gated.writerawversion(33, 0, path),
                lambda: gated.writerawversion(vernum=33, out=0, ofile=path)):
            with pytest.raises(session.SessionRefused):
                call()
    for call in (lambda: gated.save(), lambda: gated.rawd_2(0, 1, forum, 0),
                 lambda: gated.save(None), lambda: gated.case(str(other)),
                 lambda: gated.case(str(work / ".." / "other.sav")), lambda: gated.case()):
        with pytest.raises(session.SessionRefused):
            call()
    assert len(fake.fake_calls) == before, "a refused call reached the fake"
    # what is allowed: the configured case, and files inside the work folder
    assert gated.case(str(case)) == 0
    inside = str(work / "inside.raw")
    assert gated.rawd_2(0, 1, forum, 0, inside) == 0 and os.path.getsize(inside) > 0
    assert gated.save(str(work / "inside.sav")) == 0
    assert gated.calls == ["case", "rawd_2", "save"]
    assert "sid" in gated.signature_text("rawd_2")
    assert gated.signature_text("amachint") == "(sid, flag, string)"
    assert isinstance(gated.doc_text("rawd_2"), str)
    with pytest.raises(session.SessionRefused):
        gated.signature_text("fnsl_typo")
    with pytest.raises(session.SessionRefused):
        gated.doc_text("psseinit")


# ──────────────────────────────────────────────────────────────────────────────
# Isolation, export forms and --only
# ──────────────────────────────────────────────────────────────────────────────

def test_a_failing_section_is_isolated_and_named_by_class_only(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "SECTIONS", ("network", "reference", "settings", "scaling"))

    def boom(ctx):
        raise RuntimeError("failed while reading %s/secret.raw" % FAKE_PATH_TEXT)

    def fine(ctx):
        ctx.work.add_bytes("settings/extra.txt", b"extra", "settings")
        return session.SectionResult("ok", (), {"read": 2})

    def wrong_type(ctx):
        return {"status": "ok"}

    monkeypatch.setitem(session.SECTION_FUNCTIONS, "reference", boom)
    monkeypatch.setitem(session.SECTION_FUNCTIONS, "settings", fine)
    monkeypatch.setitem(session.SECTION_FUNCTIONS, "scaling", wrong_type)
    world = World(tmp_path)
    code, out, err = _run(world, monkeypatch)
    assert code == 1
    manifest, members = _read_zip(world.zip_path())
    by_name = dict((item["name"], item) for item in manifest["sections"])
    assert [item["name"] for item in manifest["sections"]] == list(session.SECTIONS)
    assert by_name["network"]["status"] == "ok"
    assert by_name["reference"]["status"] == "failed" and by_name["reference"]["detail"] == ["RuntimeError"]
    assert by_name["settings"]["status"] == "ok" and by_name["settings"]["counts"] == {"read": 2}
    assert by_name["scaling"]["status"] == "failed" and by_name["scaling"]["detail"] == ["TypeError"]
    assert members["settings/extra.txt"] == b"extra"
    assert by_name["settings"]["members"] == ["settings/extra.txt"]
    assert "section reference detail: RuntimeError" in out
    _summary_lines_match(out)
    for text in (out, err):
        assert "fakeuser" not in text and "secret" not in text and str(tmp_path) not in text
    assert b"fakeuser" not in b"".join(members.values())
    # a psspy call that raises with a path in its text: the job's own wrapper keeps the class only
    other = tmp_path / "second"
    other.mkdir()
    second = World(other, fail={"case": "raise"})
    code, out, err = _run(second, monkeypatch)
    assert code == 1
    manifest, _members = _read_zip(second.zip_path())
    network = manifest["sections"][0]
    assert network["status"] == "failed" and network["detail"] == ["no case index", "load_case"]
    for text in (out, err):
        assert "fakeuser" not in text and str(other) not in text
    _summary_lines_match(out)


ALL_FORMS = ("writerawversion_33_positional", "writerawversion_33_keywords",
             "rawd_2_forum_positional", "rawd_2_forum_keywords")


def _network_run(tmp_path, monkeypatch, **fake_options):
    monkeypatch.setattr(session, "SECTIONS", ("network",))
    world = World(tmp_path, **fake_options)
    code, out, err = _run(world, monkeypatch)
    manifest, members = _read_zip(world.zip_path())
    attempts = json.loads(members["network/export_attempts.json"].decode("ascii"))
    return code, out, err, manifest, members, attempts


def test_each_raw_export_form_failing_in_turn(tmp_path, monkeypatch):
    cases = (
        # (fake options, selected form, attempt statuses in order)
        (dict(raw_forms=ALL_FORMS), "writerawversion_33_positional", ["ok"]),
        (dict(raw_forms=ALL_FORMS[1:]), "writerawversion_33_keywords", ["failed", "ok"]),
        (dict(raw_forms=ALL_FORMS[2:]), "rawd_2_forum_positional", ["failed", "failed", "ok"]),
        (dict(raw_forms=ALL_FORMS[3:]), "rawd_2_forum_keywords", ["failed", "failed", "failed", "ok"]),
        # an exception, an ierr and a zero-byte file each make the next form the selected one
        (dict(raw_forms=ALL_FORMS, fail={"writerawversion": "raise"}), "rawd_2_forum_positional",
         ["failed", "failed", "ok"]),
        (dict(raw_forms=ALL_FORMS, fail={"writerawversion": 7}), "rawd_2_forum_positional",
         ["failed", "failed", "ok"]),
        (dict(raw_forms=ALL_FORMS, fail={"writerawversion": "empty"}), "rawd_2_forum_positional",
         ["failed", "failed", "ok"]),
    )
    for number, (options, selected, statuses) in enumerate(cases):
        folder = tmp_path / ("case%d" % number)
        folder.mkdir()
        code, out, err, manifest, members, attempts = _network_run(folder, monkeypatch, **options)
        assert code == 0, (number, out + err)
        assert attempts["selected"] == selected, number
        assert [item["status"] for item in attempts["attempts"]] == statuses, number
        assert members["network/network.raw"] and session._header_revision(members["network/network.raw"]) == 33
        for item in attempts["attempts"]:
            if item["member"] in members:
                assert len(members[item["member"]]) == item["bytes"]
        for text in (out, err):
            assert "fakeuser" not in text
    # the failure kinds are recorded as ierr, class or zero bytes, never as text
    folder = tmp_path / "kinds"
    folder.mkdir()
    _code, _out, _err, manifest, members, attempts = _network_run(
        folder, monkeypatch, raw_forms=ALL_FORMS, fail={"writerawversion": "raise"})
    first = attempts["attempts"][0]
    assert first["error_class"] == "RuntimeError" and first["ierr"] is None
    assert "network/attempt_1_writerawversion_33_positional.raw" not in members
    assert b"fakeuser" not in b"".join(members.values())
    folder = tmp_path / "zero"
    folder.mkdir()
    _code, _out, _err, manifest, members, attempts = _network_run(
        folder, monkeypatch, raw_forms=ALL_FORMS, fail={"writerawversion": "empty"})
    first = attempts["attempts"][0]
    assert first["ierr"] == 0 and first["bytes"] == 0 and first["status"] == "failed"
    assert manifest["members"][first["member"]]["bytes"] == 0
    assert attempts["selected"] != first["form_id"]
    folder = tmp_path / "ierr"
    folder.mkdir()
    _code, _out, _err, manifest, members, attempts = _network_run(
        folder, monkeypatch, raw_forms=ALL_FORMS, fail={"writerawversion": 7})
    assert attempts["attempts"][0]["ierr"] == 7


def test_no_form_working_is_a_named_failure_not_a_selected_export(tmp_path, monkeypatch):
    code, out, err, manifest, members, attempts = _network_run(tmp_path, monkeypatch, raw_forms=())
    assert code == 1
    assert attempts["selected"] is None and len(attempts["attempts"]) == 4
    assert "network/network.raw" not in members
    network = manifest["sections"][0]
    assert network["status"] == "failed" and network["detail"] == ["no raw export"]
    assert "section network detail: no raw export" in out
    _summary_lines_match(out)


def test_only_runs_network_plus_the_named_sections(tmp_path, monkeypatch):
    ran = []

    def recorder(name):
        def run(ctx):
            ran.append(name)
            return session.SectionResult("ok", (), {})
        return run

    for name in ("reference", "settings", "scaling"):
        monkeypatch.setitem(session.SECTION_FUNCTIONS, name, recorder(name))
    world = World(tmp_path)
    code, out, err = _run(world, monkeypatch, "--only", "settings")
    assert code == 0, out + err
    assert ran == ["settings"]
    manifest, _members = _read_zip(world.zip_path())
    assert [(item["name"], item["status"]) for item in manifest["sections"]] == [
        ("network", "ok"), ("reference", "skipped"), ("settings", "ok"), ("scaling", "skipped")]
    assert "section reference: skipped" in out and "section reference detail: not run" in out
    _summary_lines_match(out)
    # two sections, and network alone
    ran[:] = []
    other = tmp_path / "again"
    other.mkdir()
    code, out, err = _run(World(other), monkeypatch, "--only", "scaling, reference")
    assert code == 0 and ran == ["reference", "scaling"]
    ran[:] = []
    third = tmp_path / "third"
    third.mkdir()
    code, out, err = _run(World(third), monkeypatch, "--only", "network")
    assert code == 0 and ran == []
    # an unknown or empty section name is a usage error and nothing runs
    for bad in ("bogus", "settings,,scaling", ""):
        folder = tmp_path / ("bad%d" % len(bad))
        folder.mkdir()
        bad_world = World(folder)
        code, out, err = _run(bad_world, monkeypatch, "--only", bad)
        assert code == 2 and "--only" in err
        assert bad_world.loaded_cfgs == [] and os.listdir(str(bad_world.out)) == []
        assert bad_world.mapping.exists()


def test_check_mode_writes_no_zip_and_keeps_the_mapping(tmp_path, monkeypatch):
    world = World(tmp_path)
    code, out, err = _run(world, monkeypatch, mode="check")
    assert code == 0, out + err
    assert os.listdir(str(world.out)) == []
    assert world.mapping.exists()
    for line in ("session: checked", "mode: check", "check case index: ok", "check base solve: ok",
                 "mapping copy: kept", "work folder: deleted", "zip: not written"):
        assert line in out.splitlines(), line
    _summary_lines_match(out)
    names = [name for name, _a, _k in world.fake.fake_calls]
    assert "fnsl" in names and "save" in names
    assert all(bundle.SESSION_PREFIX in path for path in world.fake.fake_saved_paths)
    assert not any(os.path.exists(path) for path in world.fake.fake_saved_paths)
    # a case that cannot be loaded fails the first check and skips the second
    other = tmp_path / "broken"
    other.mkdir()
    broken = World(other, fail={"case": 3})
    code, out, err = _run(broken, monkeypatch, mode="check")
    assert code == 1
    assert "check case index: failed" in out and "check case index detail: load_case" in out
    assert "check base solve detail: not run" in out
    assert os.listdir(str(broken.out)) == [] and broken.mapping.exists()
    _summary_lines_match(out)


# ──────────────────────────────────────────────────────────────────────────────
# Interrupt, collision and the error exits
# ──────────────────────────────────────────────────────────────────────────────

def test_interrupt_leaves_no_zip_and_deletes_the_mapping_copy(tmp_path, monkeypatch):
    world = World(tmp_path, fail={"abrnchar": "interrupt"})
    code, out, err = _run(world, monkeypatch)
    assert code == 130
    assert os.listdir(str(world.out)) == []
    assert not world.mapping.exists()
    assert "session: interrupted" in out.splitlines() and "mapping copy: deleted" in out
    assert "zip: not written" in out
    _summary_lines_match(out)
    # an interrupt inside a section
    other = tmp_path / "second"
    other.mkdir()

    def interrupt(ctx):
        raise KeyboardInterrupt()

    monkeypatch.setitem(session.SECTION_FUNCTIONS, "reference", interrupt)
    second = World(other)
    code, out, err = _run(second, monkeypatch)
    assert code == 130 and os.listdir(str(second.out)) == [] and not second.mapping.exists()
    # an interrupt while the archive is being verified leaves no zip and no .partial file
    monkeypatch.setitem(session.SECTION_FUNCTIONS, "reference", lambda ctx: session.SectionResult("ok", (), {}))
    third_dir = tmp_path / "third"
    third_dir.mkdir()

    def killed(path, manifest, manifest_bytes):
        raise KeyboardInterrupt()

    monkeypatch.setattr(bundle.WorkFolder, "_verify_archive", staticmethod(killed))
    third = World(third_dir)
    code, out, err = _run(third, monkeypatch)
    assert code == 130 and os.listdir(str(third.out)) == [] and not third.mapping.exists()


def test_existing_session_folder_or_zip_is_never_overwritten(tmp_path, monkeypatch):
    name = bundle.SESSION_PREFIX + STAMP
    for kind in ("folder", "zip", "partial"):
        folder = tmp_path / kind
        folder.mkdir()
        world = World(folder)
        if kind == "folder":
            (world.out / name).mkdir()
            (world.out / name / "keep.txt").write_bytes(b"earlier session")
        else:
            suffix = ".zip" if kind == "zip" else ".zip.partial"
            (world.out / (name + suffix)).write_bytes(b"earlier session")
        before = _snapshot(world.out)
        code, out, err = _run(world, monkeypatch)
        assert code == 2, kind
        assert world.loaded_cfgs == [], kind
        assert _snapshot(world.out) == before, kind
        assert "already exists" in err and str(folder) not in err


def test_member_names_are_unique_and_shaped(tmp_path):
    work = bundle.WorkFolder(str(tmp_path), STAMP)
    work.add_bytes("network/network.raw", b"data", "network")
    with pytest.raises(bundle.BundleRefused):
        work.add_bytes("network/network.raw", b"other", "network")
    for bad in ("Network/x.txt", "../x.txt", "a//b.txt", "a/b.exe", "a\\b.txt", "/abs.txt", "a/b",
                bundle.MANIFEST_NAME, "", "a b.txt", "a/b.TXT", "caf\u00e9/x.txt", ".hidden/x.txt"):
        with pytest.raises(bundle.BundleRefused):
            work.add_bytes(bad, b"", "network")
        with pytest.raises(bundle.BundleRefused):
            work.member_path(bad)
    for good in ("network/attempt_1_rawd_2_forum_positional.raw", "network/docs/rawd_2.txt",
                 "logs/psse_output.txt", "network/export_attempts.json"):
        assert bundle.MEMBER_NAME_RE.match(good), good
    # a file PSS/E wrote is registered; a missing one and a repeat are refused
    path = work.member_path("network/attempt_1_x.raw")
    with pytest.raises(bundle.BundleRefused):
        work.register("network/attempt_1_x.raw", "network")
    with open(path, "wb") as handle:
        handle.write(b"written by psspy")
    work.register("network/attempt_1_x.raw", "network")
    with pytest.raises(bundle.BundleRefused):
        work.register("network/attempt_1_x.raw", "network")
    # JSON members carry the member marker; non-objects and NaN are refused
    work.add_json("network/info.json", {"b": 1, "a": [1, 2]}, "network")
    with open(os.path.join(work.path, "network", "info.json"), encoding="ascii") as handle:
        document = json.load(handle)
    assert document[bundle.MEMBER_MARKER] == 1 and document["a"] == [1, 2]
    with pytest.raises(bundle.BundleRefused):
        work.add_json("network/list.json", [1], "network")
    with pytest.raises(ValueError):
        work.add_json("network/nan.json", {"x": float("nan")}, "network")
    assert work.members() == sorted(work.members()) and len(work.members()) == 3
    # a malformed stamp and a malformed section name
    with pytest.raises(bundle.BundleRefused):
        bundle.WorkFolder(str(tmp_path), "../escape")
    with pytest.raises(bundle.BundleRefused):
        work.add_bytes("network/z.txt", b"", "Bad Section")


def test_zip_is_verified_before_it_gets_its_name(tmp_path):
    work = bundle.WorkFolder(str(tmp_path), STAMP)
    work.add_bytes("network/a.txt", b"first", "network")
    meta = {"created_utc": "2026-11-16T15:00:00Z", "mode": "run", "python_version": "3.7.0",
            "psse_version": "36.4.0", "case_sha256": None, "mapping_sha256": "0" * 64,
            "mapping_placeholder": True}
    work.write_manifest(meta, [{"name": "network", "status": "ok", "detail": [], "counts": {}}])
    # a member changed after the manifest was written: the archive does not verify, no zip appears
    with open(os.path.join(work.path, "network", "a.txt"), "wb") as handle:
        handle.write(b"changed")
    with pytest.raises(bundle.BundleRefused):
        work.zip_and_verify()
    assert not os.path.exists(work.zip_path) and not os.path.exists(work.partial_path)
    # restored: the zip is written, named only after verification, and a second zip is refused
    with open(os.path.join(work.path, "network", "a.txt"), "wb") as handle:
        handle.write(b"first")
    path = work.zip_and_verify()
    assert path == work.zip_path and os.path.isfile(path) and not os.path.exists(work.partial_path)
    with pytest.raises(bundle.BundleRefused):
        work.zip_and_verify()
    manifest, members = _read_zip(path)
    assert members == {"network/a.txt": b"first"}
    assert manifest["sections"][0]["members"] == ["network/a.txt"]
    # removal is best effort and counts what it could not delete
    assert work.remove() == 0 and not os.path.exists(work.path) and os.path.isfile(path)


def test_remove_counts_what_it_could_not_delete(tmp_path, monkeypatch):
    work = bundle.WorkFolder(str(tmp_path), STAMP)
    work.add_bytes("network/a.txt", b"x", "network")
    work.add_bytes("network/b.txt", b"y", "network")
    real_remove = os.remove

    def locked(path):
        if path.endswith("a.txt"):
            raise PermissionError("in use")
        real_remove(path)

    monkeypatch.setattr(os, "remove", locked)
    failures = work.remove()
    assert failures >= 1
    monkeypatch.undo()
    assert work.remove() == 0 and not os.path.exists(work.path)


def test_manifest_reader_fails_closed(tmp_path):
    work = bundle.WorkFolder(str(tmp_path), STAMP)
    work.add_bytes("network/a.txt", b"x", "network")
    meta = {"created_utc": "2026-11-16T15:00:00Z", "mode": "run", "python_version": "3.7.0",
            "psse_version": "unknown", "case_sha256": "a" * 64, "mapping_sha256": "b" * 64,
            "mapping_placeholder": False}
    work.write_manifest(meta, [{"name": "network", "status": "ok", "detail": [], "counts": {"buses": 1}}])
    with open(os.path.join(work.path, bundle.MANIFEST_NAME), "rb") as handle:
        good = handle.read()
    manifest = bundle.read_manifest(good)
    assert manifest[bundle.MANIFEST_MARKER] == 1 and list(manifest["members"]) == ["network/a.txt"]
    mutations = [
        lambda m: m.pop(bundle.MANIFEST_MARKER),
        lambda m: m.update(bundle_format=2),
        lambda m: m.pop("members"),
        lambda m: m.update(case_sha256="XYZ"),
        lambda m: m["members"].update({"../escape.txt": m["members"]["network/a.txt"]}),
        lambda m: m["members"]["network/a.txt"].update(sha256="short"),
        lambda m: m["members"]["network/a.txt"].update(bytes=-1),
        lambda m: m.update(sections={}),
        lambda m: m["sections"][0].update(status="maybe"),
    ]
    for mutate in mutations:
        document = json.loads(good.decode("ascii"))
        mutate(document)
        with pytest.raises(bundle.BundleRefused):
            bundle.read_manifest(json.dumps(document))
    for bad in (b"not json", b"[]", b"\xff\xfe", b"{}"):
        with pytest.raises(bundle.BundleRefused):
            bundle.read_manifest(bad)


def test_summary_renderer_refuses_free_text():
    report = bundle.SummaryReport(
        "run", "complete", "3.12.1", "35.6.0",
        (("network", "ok", (), {"buses": 9, "lines": None}),
         ("reference", "failed", ("RuntimeError", "load_case"), {})),
        (), ("log unreadable",), 3, "written", "deleted", "deleted")
    text = bundle.render_summary(report, {})
    _summary_lines_match(text)
    assert "section network counts: buses 9 lines unknown" in text
    assert "section reference detail: RuntimeError; load_case" in text
    assert text.splitlines()[-1] == bundle.CLOSING_WITH_ZIP
    unzipped = report._replace(zip_state="not written")
    assert bundle.render_summary(unzipped, {}).splitlines()[-1] == bundle.CLOSING_WITHOUT_ZIP
    # a version that is not digits and dots is replaced, never printed
    odd = report._replace(psse_version="36.4; alice")
    assert "psse: unknown" in bundle.render_summary(odd, {})
    # anything outside the vocabulary raises, and the message holds no text of the input
    bad_sections = (
        (("network", "ok", ("90001-90002-1",), {}),),
        (("network", "ok", ("a path /x/y",), {}),),
        (("network", "ok", ("Runtime_Error",), {}),),
        (("network", "ok", ("R" * 41,), {}),),
        (("90001", "ok", (), {}),),
        (("network", "maybe", (), {}),),
        (("network", "ok", (), {"buses": "90001"}),),
        (("network", "ok", (), {"bus 90001": 1}),),
        (("network", "ok", (), {"buses": True}),),
        (("network", "ok", (), {"buses": 10 ** 10}),),
    )
    for sections in bad_sections:
        with pytest.raises(ValueError) as refused:
            bundle.render_summary(report._replace(sections=sections), {})
        assert "90001" not in str(refused.value)
    for field, value in (("outcome", "complete; rm"), ("mode", "debug"), ("notes", ("free text here",)),
                         ("mapping_state", "C:/Users/x"), ("work_state", "gone"), ("zip_state", "ok"),
                         ("members", -1), ("members", True), ("checks", (("base solve", "ok", ("x y",)),))):
        with pytest.raises(ValueError):
            bundle.render_summary(report._replace(**{field: value}), {})
    # identity masking: values of at least 3 characters, the output folder, longest first
    environ = {"USERNAME": "alice01", "COMPUTERNAME": "LAPTOP-7", "HOME": "/home/alice01", "USERDOMAIN": "ab"}
    masked = bundle.mask_identity("x alice01 LAPTOP-7 /home/alice01 ab /tmp/out_folder", environ, ("/tmp/out_folder",))
    assert "alice01" not in masked and "LAPTOP-7" not in masked and "/tmp/out_folder" not in masked
    assert " ab " in masked
    masked_summary = bundle.render_summary(report, {"USERNAME": "RuntimeError"})
    assert "RuntimeError" not in masked_summary
    assert bundle.class_word(RuntimeError("x")) == "RuntimeError"
    assert bundle.safe_item("90001-90002-1") == "unknown" and bundle.safe_item("load_case") == "load_case"


def test_mapping_refusal_exit2_before_psse_starts(tmp_path, monkeypatch):
    world = World(tmp_path)
    world.mapping.write_text("{not json", encoding="utf-8")
    code, out, err = _run(world, monkeypatch)
    assert code == 2 and world.loaded_cfgs == [] and os.listdir(str(world.out)) == []
    assert re.search(r"mapping refused: \d+ problem", err)
    assert MAP_NAME not in err and str(tmp_path) not in err and out == ""
    # the committed example is marked placeholder: refused without the flag
    other = tmp_path / "second"
    other.mkdir()
    second = World(other)
    argv = [item for item in second.argv() if item != "--allow-placeholder"]
    monkeypatch.setattr(sys, "path", list(sys.path))
    err_buffer = io.StringIO()
    code = session.main(argv, second.loader, out=io.StringIO(), err=err_buffer, clock=_fixed_clock)
    assert code == 2 and second.loaded_cfgs == [] and "mapping refused" in err_buffer.getvalue()
    # configuration problems name the key only
    third_dir = tmp_path / "third"
    third_dir.mkdir()
    third = World(third_dir)
    third.config.write_text("PSSE_PSSPY_DIR=%s\n" % (third_dir / "psspy dir"), encoding="utf-8")
    code, out, err = _run(third, monkeypatch)
    assert code == 2 and "PSSE_CASE_PATH" in err and third.loaded_cfgs == []
    assert str(third_dir) not in err
    fourth_dir = tmp_path / "fourth"
    fourth_dir.mkdir()
    fourth = World(fourth_dir)
    shutil.rmtree(str(fourth.out))
    code, out, err = _run(fourth, monkeypatch)
    assert code == 2 and "out folder" in err and fourth.loaded_cfgs == []


def test_psse_unavailable_exit6_class_only(tmp_path, monkeypatch):
    world = World(tmp_path)

    def failing_loader(cfg):
        raise launcher.PsseUnavailable("psspy could not be imported from %s/psspy" % FAKE_PATH_TEXT)

    code, out, err = _run(world, monkeypatch, loader=failing_loader)
    assert code == 6
    assert "PsseUnavailable" in err
    for text in (out, err):
        assert "fakeuser" not in text and str(tmp_path) not in text
    assert os.listdir(str(world.out)) == [] and not world.mapping.exists()
    assert "session: failed" in out.splitlines() and "zip: not written" in out
    _summary_lines_match(out)


def test_unexpected_error_exit7_redacted(tmp_path, monkeypatch):
    world = World(tmp_path)

    def broken(*args, **kwargs):
        raise ValueError("internal failure at %s/secret.raw" % FAKE_PATH_TEXT)

    monkeypatch.setattr(session, "_do_run", broken)
    code, out, err = _run(world, monkeypatch)
    assert code == 7
    assert err.strip().splitlines() == ["unexpected session error (ValueError)"]
    assert "fakeuser" not in err + out and str(tmp_path) not in err + out
    # the cleanup still ran: the mapping copy and the work folder are gone
    assert os.listdir(str(world.out)) == [] and not world.mapping.exists()


def test_header_revision_and_counts_skip_leading_comment_lines():
    """The real 36.4 export starts with an @! comment line; the revision is on the first other line."""
    body = psse_session_fake.fake_raw_bytes(placeholder_case())
    commented = b"@!IC,SBASE,REV,XFRRAT,NXFRAT,BASFRQ\n" + body
    assert session._header_revision(commented) == 33
    assert session.count_raw(commented) == session.count_raw(body)


def test_writerawversion_forms_pass_the_version_as_text_and_an_int_is_refused_by_the_fake(tmp_path):
    forms = [item for item in session.RAW_EXPORT_FORMS if item[1] == "writerawversion"]
    assert len(forms) == 2
    path = str(tmp_path / "x.raw")
    assert forms[0][2](path)[0] == "33" and forms[1][3](path)["vernum"] == "33"
    fake = psse_session_fake.FakeSessionPsspy(raw_forms=("writerawversion_33_positional",))
    with pytest.raises(TypeError):
        fake.writerawversion(33, 0, path)
