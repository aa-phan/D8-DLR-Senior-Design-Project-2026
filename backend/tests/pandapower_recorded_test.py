"""
Tests of the recorded-runs route of the replay (pandapower-solver Phase 4, plan 04-01: AGR-01, AGR-04,
owner decision D-01): `pandapower_job.recorded` validates an export file that the owner of the
Supabase project produced with one read-only SQL statement, writes a private snapshot, loads it back
and prints a counts-only profile.

No database, no pandapower, no network. Every file is written inside a throwaway git repository
under `tmp_path` (a `.gitignore` holding `/data/private/`) that is passed as `repo_root`, so nothing
is ever written into this checkout's real data folder. The rows are the synthetic public rows of the
PSS/E database tests (`psse_local_pg.valid_run_rows`); no test here holds a value from
`data/private/`, and the marker key is taken from the module, so this file does not match the leak
guard's shape layer.

Follows backend/tests/psse_study_job_test.py: module-level imports, plain asserts, no classes.
"""

import datetime
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import pandapower_replay_fixture as fixture  # noqa: E402
import private_leak_scan  # noqa: E402
from pandapower_job import private, recorded  # noqa: E402

UTC = datetime.timezone.utc
FIXED_NOW = datetime.datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
HOUR_ONE = datetime.datetime(2026, 11, 18, 9, 7, 30, tzinfo=UTC)
HOUR_TWO = datetime.datetime(2026, 11, 18, 10, 7, 30, tzinfo=UTC)
HOUR_THREE = datetime.datetime(2026, 11, 18, 11, 7, 30, tzinfo=UTC)


def _incoming(repo, name="export.json"):
    return os.path.join(repo, "data", "private", "pandapower", "incoming", name)


def _outside_private(repo):
    """Every file of the repository outside .git and data/private, as relative paths."""
    found = []
    for current, dirs, files in os.walk(repo):
        relative = os.path.relpath(current, repo)
        if relative == ".git" or relative.startswith(".git" + os.sep):
            dirs[:] = []
            continue
        if relative == os.path.join("data", "private"):
            dirs[:] = []
            continue
        found.extend(os.path.normpath(os.path.join(relative, name)) for name in files)
    return sorted(found)


def _scalars(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _scalars(item)
    elif isinstance(value, list):
        for item in value:
            yield from _scalars(item)
    elif value is not None:
        yield value


# -- tracer -----------------------------------------------------------------------------------------


def test_tracer_export_to_snapshot_to_counts(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    bundles = [
        fixture.run_bundle(1, HOUR_ONE, outcome="ok"),
        fixture.run_bundle(2, HOUR_TWO, outcome="fallback"),
        fixture.run_bundle(3, HOUR_THREE, outcome="failed"),
    ]
    document = fixture.export_document(bundles)
    export_path = fixture.write_export_json(_incoming(repo), document)

    result = recorded.ingest_export(export_path, repo_root=repo, now=FIXED_NOW)

    snapshot_path = result.path
    folder = os.path.join(repo, "data", "private", "pandapower", "snapshots")
    assert os.path.dirname(snapshot_path) == os.path.realpath(folder)
    assert os.path.isfile(snapshot_path)
    assert os.path.basename(snapshot_path) == "snapshot_20261120T120000Z.json"
    ignored = subprocess.run(
        ["git", "-C", repo, "check-ignore", "-q", "--", os.path.relpath(snapshot_path, repo)])
    assert ignored.returncode == 0

    findings = private_leak_scan.scan_paths([snapshot_path], root=repo)
    assert any(item.layer == "shape" and item.pattern == "pandapower_marker" for item in findings)

    loaded = recorded.load_snapshot(snapshot_path, repo_root=repo)
    assert loaded == result.snapshot

    ordered = recorded.by_run(loaded)
    assert [item.run["run_id"] for item in ordered] == [bundle["run"]["run_id"] for bundle in bundles]
    assert [item.run["outcome"] for item in ordered] == ["ok", "fallback", "failed"]
    assert [len(item.dispatch) for item in ordered] == [4, 4, 0]

    counted = recorded.profile(loaded, fixture.HEX_A, fixture.HEX_B)
    assert counted.runs == 3
    assert (counted.ok_runs, counted.fallback_runs, counted.failed_runs) == (1, 1, 1)
    assert counted.matching_mapping == 3 and counted.matching_case == 3
    lines = recorded.profile_lines(counted)
    assert lines
    for line in lines:
        assert any(pattern.match(line) for pattern in recorded.PROFILE_LINE_PATTERNS), line
    assert "snapshot runs: 3" in lines
    assert "snapshot runs ok: 1" in lines and "snapshot runs fallback: 1" in lines
    assert "snapshot runs failed: 1" in lines

    text = "\n".join(lines)
    for bundle in bundles:
        assert bundle["run"]["run_id"] not in text
    assert fixture.HEX_A not in text and fixture.HEX_B not in text
    for table in ("runs", "dispatch", "margins", "contingencies"):
        for row in document[table]:
            for scalar in _scalars(row):
                if isinstance(scalar, (int, float)) and not isinstance(scalar, bool):
                    assert len(str(scalar)) < 5 or str(scalar) not in text

    # Without a hash to compare the two matching lines say so, and the profile still prints.
    unchecked = recorded.profile_lines(recorded.profile(loaded))
    assert "snapshot runs matching local mapping: not checked" in unchecked
    assert "snapshot runs matching session case: not checked" in unchecked

    assert _outside_private(repo) == [".gitignore"]
    assert private.require_private(snapshot_path, repo) == snapshot_path
