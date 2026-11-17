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

import datetime
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_session_fake  # noqa: E402
from psse_fake_psspy import FakePsspy, placeholder_case  # noqa: E402
from psse_job import psse_api  # noqa: E402
from psse_session import bundle, session  # noqa: E402

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
