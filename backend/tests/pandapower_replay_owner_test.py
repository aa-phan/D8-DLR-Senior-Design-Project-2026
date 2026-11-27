"""
Owner-local test of the real snapshot's replay output (pandapower-solver Phase 4, plan 04-04:
AGR-04; threat T-04-15).

This reads the recorded-runs snapshot the owner's `ingest` command wrote on this machine, under
`data/private/pandapower/snapshots/` (or the folder named by the environment variable
DLR_PANDAPOWER_SNAPSHOT_DIR, a test seam in the manner of DLR_PANDAPOWER_CHECK_DIR for the engine's
recorded test; a named folder that does not exist or holds no snapshot counts as none). When no
snapshot exists the test skips with an owner-local reason, as the engine's recorded test does; with
DLR_PANDAPOWER_REQUIRE_RECORDS set to "1" it fails with the same text instead.

It runs the replay in CI mode in process against this checkout (CI mode writes nothing), asserts
every printed line is in the command vocabulary, and scans the printed text with the needles of the
real private folder and with the snapshot's own run ids, contingency ids, element ids and hashes.
It does NOT assert the verdict word: the real verdict is recorded in the replay record, never
pinned by a test. Assertion messages hold counts and reason words only, never a value or a path.
"""

import glob
import io
import os
import re

import pytest

pytest.importorskip("pandapower")

import private_leak_scan  # noqa: E402
from pandapower_job import recorded, replay_cli  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NO_SNAPSHOT = "owner-local replay: no recorded-runs snapshot on this machine"
_VERDICT = re.compile(r"replay: (?:pass|fail|incomplete)\Z")


def _snapshot_path():
    """The newest snapshot_*.json of the named folder, else of this checkout's folder, or None."""
    named = os.environ.get("DLR_PANDAPOWER_SNAPSHOT_DIR")
    folder = named if named else os.path.join(_REPO_ROOT, "data", "private", "pandapower", "snapshots")
    if not os.path.isdir(folder):
        return None
    found = sorted(glob.glob(os.path.join(folder, "snapshot_*.json")))
    return found[-1] if found else None


def _need_snapshot():
    path = _snapshot_path()
    if path is None:
        if os.environ.get("DLR_PANDAPOWER_REQUIRE_RECORDS") == "1":
            pytest.fail(_NO_SNAPSHOT)
        pytest.skip(_NO_SNAPSHOT)
    return path


def _snapshot_needles(snapshot):
    """Run ids, contingency ids, element ids and hashes of the snapshot's own rows, at least five
    characters each."""
    found = set()
    for run in snapshot.runs:
        for column in ("run_id", "mapping_sha256", "case_sha256"):
            found.add(run.get(column))
    for row in snapshot.contingencies:
        found.add(row.get("contingency_id"))
        found.add(row.get("element_id"))
    return set(text for text in found if isinstance(text, str) and len(text) >= 5)


def test_owner_local_snapshot_replays_with_counts_only_output(tmp_path):
    path = _need_snapshot()
    out, err = io.StringIO(), io.StringIO()
    code = replay_cli.main(["replay", "--ci", "--snapshot", path], out, err, repo_root=_REPO_ROOT,
                           environ={})
    text = out.getvalue() + err.getvalue()
    lines = text.splitlines()
    assert code in (0, 1), "the replay command exited %d" % code
    assert lines and _VERDICT.match(lines[0]), "the command did not print a verdict line"
    for position, line in enumerate(lines, start=1):
        assert any(pattern.match(line) for pattern in replay_cli.CLI_LINE_PATTERNS), (
            "line %d is outside the command vocabulary" % position)

    snapshot = recorded.load_snapshot(path, repo_root=_REPO_ROOT)
    needles_b = _snapshot_needles(snapshot)
    needles_a = private_leak_scan.derive_needles(os.path.join(_REPO_ROOT, "data", "private"))
    assert len(needles_b) > 0, "the snapshot gave no needles"

    from_snapshot = [token for token in re.findall(r"[A-Za-z0-9._+\-]+", text) if token in needles_b]
    assert from_snapshot == [], "%d printed tokens are values of the snapshot" % len(from_snapshot)
    assert not any(token in needles_a for token in re.findall(r"[A-Za-z0-9._+\-]+", text)), (
        "a printed token is a value derived from the private folder")

    printed = tmp_path / "printed_output.txt"
    printed.write_text(text, encoding="utf-8")
    found = private_leak_scan.scan_paths([str(printed)], needles=needles_a, root=_REPO_ROOT)
    assert found == [], "the scan with the private folder's needles found %d things" % len(found)
    found = private_leak_scan.scan_paths([str(printed)], needles=needles_b, root=_REPO_ROOT)
    assert found == [], "the scan with the snapshot's values found %d things" % len(found)
