"""
Proofs for the private-data guard (pandapower-solver Phase 1, PSE-04, D-07, success criterion 1):
the PSS/E reference session's export, reference answers, settings, mapping copies and converted
network never reach this public repository.

Three layers, all implemented in backend/private_leak_scan.py:

  path    the ignore rule for data/private/ and the session artefacts, and no private path in the tree
  shape   RAW-file structure and the marker keys every private JSON file carries
  needle  owner-local exact values derived from the files under data/private/ (skipped when absent)

Every test reports paths, line numbers, layers and pattern names only, never the matched text, so a
failure message cannot itself leak what it found. Plants are assembled from pieces at run time and
use the 8xxxx series, never the committed 9xxxx example, so this file never matches itself and a
planted value is never allow-listed by accident. Tests that read the real private folder carry
owner_local in their name and are skipped when data/private/ is absent.

Follows backend/tests/secret_scan_test.py's conventions (module-level imports, plain asserts, no
test classes, no network).
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

import private_leak_scan as scanner
from private_leak_scan import Finding

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SCRIPT = os.path.join(_REPO_ROOT, "backend", "private_leak_scan.py")

# Planted identifiers: 8xxxx buses built from pieces (never the committed 9xxxx example).
_FROM_BUS = int("8" + "1234")
_TO_BUS = int("8" + "1235")
_KEY = "%d-%d-%s" % (_FROM_BUS, _TO_BUS, "1")
_REVERSE_KEY = "%d-%d-%s" % (_TO_BUS, _FROM_BUS, "1")

# RAW and marker plants, assembled from pieces so this file never matches itself.
_END_OF = "END" + " OF "
_BEGIN = "BEG" + "IN"
_SHAPE_PLANTS = [
    ("terminator", "0 / " + _END_OF + "BUS DATA", "raw_terminator"),
    ("begin", "0 / " + _END_OF + "BUS DATA, " + _BEGIN + " LOAD DATA", "raw_begin"),
    ("header", "0, 100.00, 33, 0, 1, 60.00", "raw_header"),
    ("session_manifest", '{"psse_pp_' + 'session_' + 'manifest": 1}', "session_marker"),
    ("session_member", '"psse_pp_' + 'session_' + 'member": "x"', "session_marker"),
    ("pp_network", '{"pandapower_' + 'job_' + 'network": 1}', "pandapower_marker"),
    ("pp_report", '"pandapower_' + 'job_' + 'report": {}', "pandapower_marker"),
    ("pp_registry", '"pandapower_' + 'job_' + 'registry": []', "pandapower_marker"),
]


def _git(*args):
    return subprocess.run(["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True)


def _write_private_mapping(private_root):
    """A schema-2 mapping with one 8xxxx branch, written under the given private root."""
    private_root.mkdir(parents=True, exist_ok=True)
    mapping = {
        "schema_version": 2,
        "placeholder": False,
        "cities": {
            "CITY_A": {
                "branches": [{"from_bus": _FROM_BUS, "to_bus": _TO_BUS, "ckt": "1"}],
                "sink_buses": [_TO_BUS],
                "scaling": {"load_mw": 2111.5, "gen_mw": 2222.25, "basis": "average"},
            }
        },
        "study": {},
    }
    (private_root / "mapping.json").write_text(json.dumps(mapping), encoding="utf-8")


def test_tracer_ignore_rule_clean_tree_and_planted_identifier(tmp_path):
    # Path layer: the ignore rule is in place before any private file exists.
    for name in (
        "data/private/pandapower/x.json",
        "psse_pp_session_20261116T000000Z.zip",
        "some/folder/psse_pp_session_20261116T000000Z/manifest.json",
    ):
        ignored = _git("check-ignore", "-q", name)
        assert ignored.returncode == 0, "a private path is not git-ignored (%s)" % name.split("/")[0]
    assert _git("ls-files", "--", "data/private").stdout.strip() == ""

    # Clean tree: tracked files plus untracked files that are not ignored hold nothing.
    working_tree = scanner.working_tree_files(scanner.repo_root())
    assert scanner.scan_paths(working_tree, needles=set()) == []

    # Planted identifier: needles come from a private folder, and one planted key is flagged by
    # path and line only.
    private_root = tmp_path / "private"
    _write_private_mapping(private_root)
    needles = scanner.derive_needles(str(private_root))
    key = "%d-%d-%s" % (_FROM_BUS, _TO_BUS, "1")
    reverse = "%d-%d-%s" % (_TO_BUS, _FROM_BUS, "1")
    assert key in needles and reverse in needles

    planted = tmp_path / "planted.txt"
    planted.write_text("first line\nsecond line\nsee branch " + key + " here\nlast line\n", encoding="utf-8")
    clean = tmp_path / "clean.txt"
    clean.write_text("first line\nnothing private here\n", encoding="utf-8")
    found = scanner.scan_paths([str(planted), str(clean)], needles=needles)
    assert found == [Finding(str(planted), 3, "needle", "mapping_key")]
    assert key not in repr(found) and reverse not in repr(found)

    # The command line on the clean tree: exit 0 and nothing on stdout.
    run = subprocess.run([sys.executable, "-I", "-B", _SCRIPT], cwd=_REPO_ROOT,
                         capture_output=True, text=True)
    assert run.returncode == 0, "the scanner flagged the clean tree (exit %d)" % run.returncode
    assert run.stdout == ""


# ---------------------------------------------------------------------------
# Helpers for the full proofs
# ---------------------------------------------------------------------------

_REFERENCE_TEXT = (
    "a 1.047523 b\n"
    "c 0.00350 d\n"
    "e -0.987654 f\n"
    "g 12.34500 h\n"
    "i 1.5 j\n"
    "k 3.1415920 l\n"
    "m 0.012340 n\n"
)


def _write_private_reference(private_root):
    private_root.mkdir(parents=True, exist_ok=True)
    (private_root / "reference.txt").write_text(_REFERENCE_TEXT, encoding="utf-8")


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_repo(tmp_path, monkeypatch, ignore_rules=True):
    """A throwaway git repository whose behaviour the user's git configuration cannot change."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if ignore_rules:
        # The rule block is copied from this repository's own .gitignore, so the test fails if
        # the real rules disappear.
        with open(os.path.join(_REPO_ROOT, ".gitignore"), encoding="utf-8") as handle:
            real_rules = [line.strip() for line in handle]
        rules = [rule for rule in ("/data/private/", "psse_pp_session*") if rule in real_rules]
        assert len(rules) == 2, "the real .gitignore lacks the private-data rules"
        (repo / ".gitignore").write_text("\n".join(rules) + "\n", encoding="utf-8")
    return repo


def _stage(repo, *names):
    subprocess.run(["git", "add", "--", *names], cwd=repo, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Shape layer
# ---------------------------------------------------------------------------

def test_shape_layer_flags_each_planted_pattern(tmp_path):
    for label, text, expected in _SHAPE_PLANTS:
        path = tmp_path / (label + ".txt")
        if expected == "raw_header":
            # The header is judged on the first non-empty line, after a blank one here.
            path.write_text("\n" + text + "\nalpha\n", encoding="utf-8")
            line = 2
        else:
            path.write_text("alpha\nbeta\n" + text + "\nomega\n", encoding="utf-8")
            line = 3
        found = scanner.scan_paths([str(path)], needles=set())
        assert found == [Finding(str(path), line, "shape", expected)], label
        assert text not in repr(found)

    # A clean sibling: prose that mentions the same words without the line shapes.
    clean = tmp_path / "clean.txt"
    clean.write_text(
        "A RAW file ends each section with a terminator line; the next section begins after it.\n"
        "The section list runs from bus data to the end of the case.\n"
        "the end of bus data is where a zero and a slash are written, but not as a line start\n"
        "see revision 33, 34, 35 and 36 for the header layout\n"
        "the manifest key and the member key are described in prose\n"
        'a quoted word like "network" is not a marker\n'
        "begin load data\n",
        encoding="utf-8",
    )
    assert scanner.scan_paths([str(clean)], needles=set()) == []

    # The five pattern names are all present, in order.
    assert list(scanner.SHAPE_PATTERNS) == [
        "raw_terminator", "raw_begin", "raw_header", "session_marker", "pandapower_marker"]


def test_shape_header_only_on_the_first_line(tmp_path):
    header = "0, 100.00, 33, 0, 1, 60.00"
    late = tmp_path / "late.txt"
    late.write_text("alpha\nbeta\ngamma\ndelta\n" + header + "\n", encoding="utf-8")
    assert scanner.scan_paths([str(late)], needles=set()) == []

    blank_first = tmp_path / "blank_first.txt"
    blank_first.write_text("\n\n" + header + "\nalpha\n", encoding="utf-8")
    assert scanner.scan_paths([str(blank_first)], needles=set()) == [
        Finding(str(blank_first), 3, "shape", "raw_header")]

    # IC must be 0 or 1 and the revision 33 to 36.
    variants = (("1, 50, 36, 0", True), ("2, 100.00, 33, 0", False),
                ("0, 100.00, 32, 0", False), ("0, 100.00, 37, 0", False))
    for index, (text, flagged) in enumerate(variants):
        path = tmp_path / ("variant%d.txt" % index)
        path.write_text(text + "\n", encoding="utf-8")
        found = scanner.scan_paths([str(path)], needles=set())
        expected = [Finding(str(path), 1, "shape", "raw_header")] if flagged else []
        assert found == expected, "variant %d" % index


# ---------------------------------------------------------------------------
# Needle layer
# ---------------------------------------------------------------------------

def test_needles_decimals_targets_and_hashes(tmp_path):
    private_root = tmp_path / "private"
    _write_private_mapping(private_root)
    _write_private_reference(private_root)
    needles = scanner.derive_needles(str(private_root))

    # Decimals with at least five fractional digits once trailing zeros are stripped.
    for text in ("1.047523", "0.987654", "3.141592", "3.1415920", "0.01234"):
        assert text in needles, "a decimal needle is missing"
        assert needles.kinds[text] == "decimal"
    for text in ("0.00350", "0.0035", "12.345", "12.34500", "1.5"):
        assert text not in needles, "a short decimal became a needle"

    # Scaling targets in the forms they would be typed.
    for text in ("2111.5", "2111.50", "2,111.5", "2,111.50", "2222.25", "2,222.25"):
        assert text in needles, "a scaling target form is missing"
        assert needles.kinds[text] == "scaling_target"

    # The sha256 of every private file.
    for name in ("mapping.json", "reference.txt"):
        digest = _sha256(private_root / name)
        assert digest in needles and needles.kinds[digest] == "file_hash"

    assert all(len(text) >= scanner.MIN_NEEDLE_CHARS for text in needles)

    # Each kind is flagged by line and kind name only.
    probe = tmp_path / "probe.txt"
    probe.write_text(
        "x 1.047523\n"
        "y -0.987654\n"
        "z 2,111.50\n"
        "w 2222.25\n"
        "h " + _sha256(private_root / "reference.txt") + "\n"
        "short 0.00350 and 12.34500 and 1.5\n",
        encoding="utf-8",
    )
    found = scanner.scan_paths([str(probe)], needles=needles)
    assert [(item.line, item.layer, item.pattern) for item in found] == [
        (1, "needle", "decimal"), (2, "needle", "decimal"), (3, "needle", "scaling_target"),
        (4, "needle", "scaling_target"), (5, "needle", "file_hash")]

    # An absent private folder gives no needles (the layer is skipped, never failed).
    assert len(scanner.derive_needles(str(tmp_path / "absent"))) == 0


def test_needles_match_whole_tokens_only(tmp_path):
    private_root = tmp_path / "private"
    _write_private_mapping(private_root)
    _write_private_reference(private_root)
    needles = scanner.derive_needles(str(private_root))
    probe = tmp_path / "probe.txt"
    probe.write_text(
        "ok " + _KEY + "\n"                      # 1 flagged
        + _REVERSE_KEY + "\n"                    # 2 flagged: the reversed orientation
        "(" + _KEY + ")\n"                       # 3 flagged: punctuation around the token
        + _KEY + ",\n"                           # 4 flagged
        "1" + _KEY + "\n"                        # 5 extra leading digit
        + _KEY + "2\n"                           # 6 two-character circuit
        + _KEY + "-3\n"                          # 7 longer chain
        "x" + _KEY + "\n"                        # 8 letter prefix
        "1.0475231\n",                           # 9 a longer decimal that merely contains a needle
        encoding="utf-8",
    )
    found = scanner.scan_paths([str(probe)], needles=needles)
    assert found == [Finding(str(probe), line, "needle", "mapping_key") for line in (1, 2, 3, 4)]


# ---------------------------------------------------------------------------
# Staged mode, size and the allow-list
# ---------------------------------------------------------------------------

def test_staged_mode_scans_the_index_not_the_working_tree(tmp_path, monkeypatch, capsys):
    repo = _make_repo(tmp_path, monkeypatch)
    private_root = tmp_path / "private"
    _write_private_mapping(private_root)

    (repo / "planted.txt").write_text("alpha\n" + _KEY + "\nomega\n", encoding="utf-8")
    (repo / "edited.txt").write_text(_REVERSE_KEY + "\nbeta\n", encoding="utf-8")
    (repo / "clean.txt").write_text("nothing private here\n", encoding="utf-8")
    _stage(repo, ".gitignore", "planted.txt", "edited.txt", "clean.txt")

    # After staging: one plant is deleted and one is edited clean in the working tree.
    os.remove(repo / "planted.txt")
    (repo / "edited.txt").write_text("edited clean\nbeta\n", encoding="utf-8")

    monkeypatch.chdir(repo)
    status = scanner.main(["--staged", "--private-root", str(private_root)])
    shown = capsys.readouterr()
    assert status == 1
    assert shown.out.splitlines() == ["edited.txt:1:needle:mapping_key", "planted.txt:2:needle:mapping_key"]
    assert _KEY not in shown.out and _REVERSE_KEY not in shown.out

    # The working tree alone looks clean, which is exactly why the index must be scanned.
    status = scanner.main(["--private-root", str(private_root)])
    shown = capsys.readouterr()
    assert status == 0 and shown.out == ""


def test_staged_oversize_file_fails_closed(tmp_path, monkeypatch, capsys):
    repo = _make_repo(tmp_path, monkeypatch)
    (repo / "big.txt").write_bytes(b"a" * (scanner.MAX_BYTES + 1))
    (repo / "big.png").write_bytes(b"a" * (scanner.MAX_BYTES + 1))
    _stage(repo, ".gitignore", "big.txt", "big.png")
    monkeypatch.chdir(repo)
    absent = str(tmp_path / "absent")

    status = scanner.main(["--staged", "--private-root", absent])
    shown = capsys.readouterr()
    assert status == 1
    assert shown.out.splitlines() == ["big.txt:0:size:oversize_unscanned"]

    # In working-tree mode the same file is only counted, as unscanned, on stderr.
    status = scanner.main(["--private-root", absent])
    shown = capsys.readouterr()
    assert status == 0 and shown.out == ""
    assert "2 file(s) not scanned" in shown.err


def test_allow_list_exempts_only_an_exact_sha256(tmp_path):
    root = str(tmp_path)
    private_root = tmp_path / "private"
    _write_private_mapping(private_root)
    needles = scanner.derive_needles(str(private_root))

    body = ("head\nsee " + _KEY + "\n").encode("utf-8")
    pinned = tmp_path / "pinned.txt"
    pinned.write_bytes(body)
    allow_file = tmp_path / "allow.json"
    allow_file.write_text(json.dumps([{"path": "pinned.txt", "sha256": hashlib.sha256(body).hexdigest()}]),
                          encoding="utf-8")
    allow = scanner.load_allow_list(root, path=str(allow_file))

    flagged = [Finding(str(pinned), 2, "needle", "mapping_key")]
    assert scanner.scan_paths([str(pinned)], needles=needles, root=root) == flagged
    assert scanner.scan_paths([str(pinned)], needles=needles, allow=allow, root=root) == []

    # Edited by one byte: back in the scan.
    pinned.write_bytes(body + b" ")
    assert scanner.scan_paths([str(pinned)], needles=needles, allow=allow, root=root) == flagged

    # The right content under another path is not exempt.
    other = tmp_path / "other.txt"
    other.write_bytes(body)
    assert scanner.scan_paths([str(other)], needles=needles, allow=allow, root=root) == [
        Finding(str(other), 2, "needle", "mapping_key")]

    # The shape layer is exempted the same way.
    marker = tmp_path / "marker.txt"
    marker_body = (_SHAPE_PLANTS[3][1] + "\n").encode("utf-8")
    marker.write_bytes(marker_body)
    marker_allow = {"marker.txt": {hashlib.sha256(marker_body).hexdigest()}}
    assert scanner.scan_paths([str(marker)], needles=set(), root=root) == [
        Finding(str(marker), 1, "shape", "session_marker")]
    assert scanner.scan_paths([str(marker)], needles=set(), allow=marker_allow, root=root) == []

    # A listed sha256 is not a needle.
    digest = _sha256(private_root / "mapping.json")
    assert digest in needles
    pin_file = tmp_path / "pin.json"
    pin_file.write_text(json.dumps([{"path": "docs/pinned_copy.json", "sha256": digest}]), encoding="utf-8")
    pins = scanner.load_allow_list(root, path=str(pin_file))
    assert digest not in scanner.derive_needles(str(private_root), allow=pins)

    # A missing file allows nothing; a malformed one is an error (fail closed).
    assert scanner.load_allow_list(root, path=str(tmp_path / "missing.json")) == {}
    for index, text in enumerate(("{not json", '{"path": "a"}', '[{"path": "a"}]',
                                  '[{"path": "a", "sha256": "zz"}]', '["a"]')):
        bad = tmp_path / ("bad%d.json" % index)
        bad.write_text(text, encoding="utf-8")
        with pytest.raises(scanner.AllowListError):
            scanner.load_allow_list(root, path=str(bad))


# ---------------------------------------------------------------------------
# Output and exit codes
# ---------------------------------------------------------------------------

def test_findings_never_hold_the_matched_text(tmp_path, monkeypatch, capsys):
    repo = _make_repo(tmp_path, monkeypatch)
    private_root = tmp_path / "private"
    _write_private_mapping(private_root)
    _write_private_reference(private_root)
    digest = _sha256(private_root / "reference.txt")

    lines = ["0, 100.00, 33, 0, 1, 60.00", _KEY, "1.047523", "2,111.50", digest,
             _SHAPE_PLANTS[0][1], _SHAPE_PLANTS[1][1], _SHAPE_PLANTS[3][1], _SHAPE_PLANTS[5][1]]
    (repo / "leak.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    expected = [
        "leak.txt:1:shape:raw_header",
        "leak.txt:2:needle:mapping_key",
        "leak.txt:3:needle:decimal",
        "leak.txt:4:needle:scaling_target",
        "leak.txt:5:needle:file_hash",
        "leak.txt:6:shape:raw_terminator",
        "leak.txt:7:shape:raw_begin",
        "leak.txt:8:shape:session_marker",
        "leak.txt:9:shape:pandapower_marker",
    ]
    secrets = [_KEY, "1.047523", "2,111.50", digest, "BUS DATA", "session_manifest", "job_network", "33, 0"]

    monkeypatch.chdir(repo)
    status = scanner.main(["--private-root", str(private_root)])
    shown = capsys.readouterr()
    assert status == 1
    assert shown.out.splitlines() == expected
    for text in secrets:
        assert text not in shown.out and text not in shown.err

    needles = scanner.derive_needles(str(private_root))
    found = scanner.scan_paths([str(repo / "leak.txt")], needles=needles, root=str(repo))
    assert len(found) == len(expected)
    for text in secrets:
        assert text not in repr(found)

    # Staged mode reports the same locations.
    _stage(repo, "leak.txt")
    status = scanner.main(["--staged", "--private-root", str(private_root)])
    shown = capsys.readouterr()
    assert status == 1 and shown.out.splitlines() == expected
    for text in secrets:
        assert text not in shown.out and text not in shown.err


def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    absent = str(tmp_path / "absent")

    # Usage errors and help, in process and as a subprocess.
    assert scanner.main(["--no-such-flag"]) == 2
    capsys.readouterr()
    assert scanner.main(["--help"]) == 0
    capsys.readouterr()
    flagged = subprocess.run([sys.executable, "-I", "-B", _SCRIPT, "--no-such-flag"], cwd=_REPO_ROOT,
                             capture_output=True, text=True)
    assert flagged.returncode == 2 and flagged.stdout == ""

    # Clean repository: 0. Missing ignore rule: 1, and a private folder in the tree is a path finding.
    repo = _make_repo(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)
    assert scanner.main(["--private-root", absent]) == 0
    assert capsys.readouterr().out == ""

    bare = tmp_path / "bare"
    bare.mkdir()
    subprocess.run(["git", "init", "-q", str(bare)], check=True)
    (bare / "data" / "private").mkdir(parents=True)
    (bare / "data" / "private" / "x.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.chdir(bare)
    assert scanner.main(["--private-root", absent]) == 1
    assert capsys.readouterr().out.replace("\\", "/").splitlines() == [
        "data/private:0:path:private_dir_not_ignored",
        "data/private/x.json:0:path:private_path_in_tree",
    ]

    # A malformed allow-list is a usage-class failure: exit 2, nothing on stdout.
    monkeypatch.chdir(repo)
    (repo / "backend").mkdir()
    (repo / "backend" / "private_leak_allow.json").write_text("{not json", encoding="utf-8")
    assert scanner.main(["--private-root", absent]) == 2
    shown = capsys.readouterr()
    assert shown.out == "" and "allow-list" in shown.err

    # Outside any git checkout: exit 2.
    loose = tmp_path / "loose"
    loose.mkdir()
    shutil.copy(_SCRIPT, loose / "private_leak_scan.py")
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path))
    outside = subprocess.run([sys.executable, "-I", "-B", str(loose / "private_leak_scan.py")], cwd=loose,
                             capture_output=True, text=True, env=env)
    assert outside.returncode == 2 and outside.stdout == ""


# ---------------------------------------------------------------------------
# Owner-local: the real private folder
# ---------------------------------------------------------------------------

def test_owner_local_working_tree_has_no_private_values():
    private_root = os.path.join(_REPO_ROOT, "data", "private")
    if not os.path.isdir(private_root):
        pytest.skip("owner-local check: data/private/ is absent on this machine")
    needles = scanner.derive_needles(private_root)
    allow = scanner.load_allow_list(_REPO_ROOT)
    findings = scanner.scan_paths(scanner.working_tree_files(_REPO_ROOT), needles=needles, allow=allow,
                                  root=_REPO_ROOT)
    shown = ["%s:%d:%s:%s" % (os.path.relpath(item.path, _REPO_ROOT), item.line, item.layer, item.pattern)
             for item in findings]
    assert findings == [], "%d private value(s) in the working tree (%d needles): %s" % (
        len(findings), len(needles), ", ".join(shown))
