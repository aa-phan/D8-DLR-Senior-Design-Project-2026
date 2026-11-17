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

import json
import os
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
