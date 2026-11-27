"""
What the owner's replay commands may print, rehearsed on public data (pandapower-solver Phase 4,
plan 04-04, task 1: AGR-04; decision D-03; threat T-04-15).

Everything the commands print, to a terminal or a CI log, must be counts and words of the closed
vocabulary (`replay_cli.CLI_LINE_PATTERNS`). This file checks it two ways, and shows that the
checks can fire:

  scan A   `private_leak_scan.derive_needles` of the throwaway repository's `data/private` folder:
           the mapping's branch keys, the scaling targets, the sha256 of every private file and the
           long decimals. This is the scan the owner's real tree gets, run on a tree shaped like it.
  scan B   a needle set built from this test's own data: every run id, contingency id and element
           id of the stand-in's recorded rows, every number of the mapping, the recorded rows and
           the replayed rows in its `repr`, `%g` and `%.1f` forms (kept when at least five
           characters long, as the scanner's own needles are), the mapping hash and the case hash.

Every private-looking file here is synthetic and lives in a throwaway git repository under
`tmp_path`; nothing here reads the real `data/private/`. Honest scope: this proves that the
commands' output cannot carry what these scans know to look for, and that the scans are able to
find it; it does not prove that no other secret exists. A clean scan means something only because
each scan is shown to fire on a planted value (the five teeth of the tracer test).
"""

import io
import json
import math
import os
import pytest

pytest.importorskip("pandapower")

import pandapower_replay_fixture as fixture  # noqa: E402
import private_leak_scan  # noqa: E402
from pandapower_job import recorded, replay, replay_cli  # noqa: E402

_PATTERNS = replay_cli.CLI_LINE_PATTERNS
_TOKEN = private_leak_scan._TOKEN


@pytest.fixture(scope="module")
def stress_standin(tmp_path_factory):
    return fixture.standin(tmp_path_factory.mktemp("output_stress"), stress=True)


# -- needle sets -----------------------------------------------------------------------------------


def _collect_numbers(node, found):
    """Every number anywhere in `node` (dicts, lists, tuples, namedtuples) in three text forms."""
    if node is None or isinstance(node, (bool, str, bytes)):
        return
    if isinstance(node, (int, float)):
        if isinstance(node, float) and not math.isfinite(node):
            return
        found.update((repr(node), "%g" % node, "%.1f" % node))
    elif isinstance(node, dict):
        for value in node.values():
            _collect_numbers(value, found)
    elif hasattr(node, "_asdict"):
        _collect_numbers(node._asdict(), found)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _collect_numbers(value, found)


def _set_b(stand):
    """Needle set B from the stand-in's own recorded and replayed data (see the module header)."""
    found = set()
    run = stand.bundle["run"]
    found.add(run["run_id"])
    for row in stand.bundle["contingencies"]:
        found.add(row["contingency_id"])
        found.add(row["element_id"])
    for row in stand.results.contingencies:
        found.add(row["contingency_id"])
        found.add(row["element_id"])
    with open(stand.mapping_path, "r", encoding="utf-8") as handle:
        mapping_document = json.load(handle)
    numbers = set()
    for part in (mapping_document, stand.bundle["run"], stand.bundle["dispatch"],
                 stand.bundle["margins"], stand.bundle["contingencies"], stand.results):
        _collect_numbers(part, numbers)
    found.update(numbers)
    found.update((stand.mapping_sha256, stand.case_sha256, fixture.CASE_SHA))
    return set(text for text in found if isinstance(text, str) and len(text) >= 5)


def _set_a(repo):
    return private_leak_scan.derive_needles(os.path.join(repo, "data", "private"))


def _write(path, text):
    os.makedirs(os.path.dirname(os.fspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return str(path)


def _first(needles, kind):
    chosen = sorted(text for text, name in needles.kinds.items() if name == kind)
    assert chosen, "precondition not reached: no needle of kind %s in scan set A" % kind
    return chosen[0]


def _in_vocabulary(text, where):
    for position, line in enumerate(text.splitlines(), start=1):
        assert any(pattern.match(line) for pattern in _PATTERNS), (
            "%s: line %d is outside the command vocabulary" % (where, position))


def _tokens_of(text):
    return set(_TOKEN.findall(text))


def _scans_clean(path, repo, needles_a, needles_b, where):
    assert len(needles_a) > 0 and len(needles_b) > 0, "%s: an empty needle set proves nothing" % where
    found_a = private_leak_scan.scan_paths([path], needles=needles_a, root=repo)
    assert found_a == [], "%s: scan A reports %d findings" % (where, len(found_a))
    found_b = private_leak_scan.scan_paths([path], needles=needles_b, root=repo)
    assert found_b == [], "%s: scan B reports %d findings" % (where, len(found_b))
    with open(path, "r", encoding="utf-8") as handle:
        shared = _tokens_of(handle.read()) & needles_b
    assert not shared, "%s: %d printed tokens are known values" % (where, len(shared))


# -- the tracer ------------------------------------------------------------------------------------


def test_tracer_ci_output_is_counts_only_and_the_scan_can_fire(tmp_path, stress_standin):
    stand = stress_standin
    repo = fixture.make_repo(tmp_path / "repo")
    fixture.private_layout(repo, stand)
    fixture.ingest_standins(repo, [stand])

    out, err = io.StringIO(), io.StringIO()
    code = replay_cli.main(["replay", "--ci"], out, err, repo_root=repo, now=fixture.FIXED_NOW,
                           environ={})
    assert code == 0, "the stand-in replay exits %d" % code
    text = out.getvalue() + err.getvalue()
    assert text.splitlines()[0] == "replay: pass"
    assert "runs replayed: 1" in text.splitlines()
    for line in text.splitlines():
        assert any(pattern.match(line) for pattern in _PATTERNS), "a printed line is outside the vocabulary"

    # CI mode writes nothing: no replays folder, no report anywhere in the throwaway repository.
    replays = os.path.join(repo, "data", "private", "pandapower", "replays")
    assert not os.path.exists(replays)
    assert "report: written" not in text

    printed = _write(tmp_path / "outputs" / "ci_output.txt", text)
    needles_a = _set_a(repo)
    needles_b = _set_b(stand)
    _scans_clean(printed, repo, needles_a, needles_b, "ci output")

    # Teeth. Each planted value is appended to a copy of the clean output, and the scan or the token
    # check that should catch it must report a hit. The clean output is never touched.
    def planted(name, value):
        return _write(tmp_path / "planted" / (name + ".txt"), text + "note %s\n" % value)

    branch_key = _first(needles_a, "mapping_key")
    hits = private_leak_scan.scan_paths([planted("branch_key", branch_key)], needles=needles_a, root=repo)
    assert [item.pattern for item in hits] == ["mapping_key"], "tooth 1 (branch key) did not fire"

    decimal = _first(needles_a, "decimal")
    hits = private_leak_scan.scan_paths([planted("decimal", decimal)], needles=needles_a, root=repo)
    assert any(item.pattern == "decimal" for item in hits), "tooth 2 (long decimal) did not fire"

    run_id = stand.bundle["run"]["run_id"]
    assert run_id in needles_b
    hits = private_leak_scan.scan_paths([planted("run_id", run_id)], needles=needles_b, root=repo)
    assert hits != [], "tooth 3 (run id) did not fire in the scan"
    assert run_id in _tokens_of(text + "note %s\n" % run_id) & needles_b, (
        "tooth 3 (run id) did not fire in the token check")

    assert stand.mapping_sha256 in needles_b
    hits = private_leak_scan.scan_paths(
        [planted("mapping_hash", stand.mapping_sha256)], needles=needles_b, root=repo)
    assert hits != [], "tooth 4 (mapping hash) did not fire in scan B"
    assert stand.mapping_sha256 in _tokens_of(text + "note %s\n" % stand.mapping_sha256) & needles_b
    hits = private_leak_scan.scan_paths(
        [planted("mapping_hash_a", stand.mapping_sha256)], needles=needles_a, root=repo)
    assert any(item.pattern == "file_hash" for item in hits), (
        "tooth 4 (mapping hash) did not fire in scan A: the private mapping copy is a hashed file")

    marked = _write(tmp_path / "planted" / "marker.txt",
                    text + json.dumps({recorded.REPORT_MARKER: 1}) + "\n")
    hits = private_leak_scan.scan_paths([marked], needles=needles_a, root=repo)
    assert any(item.layer == "shape" and item.pattern == "pandapower_marker" for item in hits), (
        "tooth 5 (a file carrying the report marker) did not fire")

    # Without a plant the same scans stay clean: the teeth are not an artefact of the scan settings.
    _scans_clean(printed, repo, needles_a, needles_b, "ci output after the teeth")


# -- every output the commands can produce ---------------------------------------------------------


def _thermal_plus_three_percent(bundle):
    rows = [row for row in bundle["contingencies"] if row["violation_kind"] == "thermal_overload"]
    assert rows, "precondition not reached: the stress stand-in has thermal rows"
    max(rows, key=lambda row: row["exceeded_by"])["observed_value"] *= 1.03


def _cached(stand):
    def replay_fn(snapshot, backend, network, mapping, session_case):
        return replay.replay_snapshot(snapshot, backend, network, mapping, session_case,
                                      runner=lambda selection: stand.results)
    return replay_fn


def _never_studied(stand):
    def replay_fn(snapshot, backend, network, mapping, session_case):
        return replay.replay_snapshot(
            snapshot, backend, network, mapping, session_case,
            runner=lambda selection: pytest.fail("a study ran for a case that must exclude every run"))
    return replay_fn


def _cases(tmp_path, stand):
    """(name, argv, repo, replay_fn) for every output the commands can produce. Each case has its own
    throwaway repository so no output depends on another case's files."""
    cases = []

    def world(name, layout=True, snapshot="standin"):
        repo = fixture.make_repo(tmp_path / name)
        made = fixture.private_layout(repo, stand) if layout else None
        if snapshot == "standin":
            fixture.ingest_standins(repo, [stand])
        elif snapshot == "perturbed":
            fixture.perturbed_snapshot(repo, stand, _thermal_plus_three_percent)
        elif snapshot == "failed_only":
            fixture.snapshot_of_bundles(
                repo, [fixture.run_bundle(1, fixture.FIXED_NOW, outcome="failed")])
        return repo, made

    for mode, flags in (("ci", ["--ci"]), ("local", [])):
        repo, _ = world("pass_" + mode)
        cases.append(("verdict pass, %s" % mode, ["replay"] + flags, repo, _cached(stand)))
        repo, _ = world("fail_" + mode, snapshot="perturbed")
        cases.append(("verdict fail, %s" % mode, ["replay"] + flags, repo, _cached(stand)))
        repo, _ = world("incomplete_" + mode, snapshot="failed_only")
        cases.append(("verdict incomplete, %s" % mode, ["replay"] + flags, repo, _never_studied(stand)))

    repo, _ = world("snapshot_missing", snapshot=None)
    cases.append(("refusal snapshot_missing", ["replay", "--ci"], repo, None))
    repo, _ = world("records_missing", layout=False)
    cases.append(("refusal records_missing", ["replay", "--ci"], repo, None))
    repo, made = world("mapping_missing")
    os.remove(made.mapping)
    cases.append(("refusal mapping_missing", ["replay", "--ci"], repo, None))

    repo, made = world("refused_record")
    with open(made.report, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    document["settings"]["sources"]["enforce_q_lims"] = "placeholder: not decided"
    _write(made.report, json.dumps(document))
    cases.append(("refused record", ["replay", "--ci"], repo, None))

    repo, _ = world("ingest_ok", snapshot=None)
    export = fixture.export_document([stand.bundle])
    path = fixture.write_export_json(
        os.path.join(repo, "data", "private", "pandapower", "incoming", "export.json"), export)
    cases.append(("ingest ok", ["ingest", "--export", path], repo, None))

    repo, _ = world("ingest_truncated", snapshot=None)
    text = json.dumps([fixture.export_document([stand.bundle])])
    path = _write(os.path.join(repo, "data", "private", "pandapower", "incoming", "cut.json"),
                  text[:len(text) // 2])
    cases.append(("refused ingest, truncated", ["ingest", "--export", path], repo, None))

    repo, _ = world("ingest_counts", snapshot=None)
    counts = dict(fixture.export_document([stand.bundle])["counts"])
    counts["runs"] += 1
    path = fixture.write_export_json(
        os.path.join(repo, "data", "private", "pandapower", "incoming", "lie.json"),
        fixture.export_document([stand.bundle], counts=counts))
    cases.append(("refused ingest, counts differ", ["ingest", "--export", path], repo, None))

    for index, argv in enumerate(([], ["bogus"], ["replay", "--verbose"], ["ingest"])):
        repo, _ = world("usage_%d" % index)
        cases.append(("usage %d" % index, argv, repo, None))
    return cases


def test_every_verdict_and_refusal_output_is_in_the_vocabulary_and_scans_clean(tmp_path, stress_standin):
    stand = stress_standin
    needles_b = _set_b(stand)
    seen = set()
    for number, (name, argv, repo, replay_fn) in enumerate(_cases(tmp_path, stand)):
        out, err = io.StringIO(), io.StringIO()
        code = replay_cli.main(argv, out, err, repo_root=repo, now=fixture.FIXED_NOW, environ={},
                               replay_fn=replay_fn)
        text = out.getvalue() + err.getvalue()
        assert text.strip() != "", "%s: nothing was printed" % name
        _in_vocabulary(text, name)
        printed = _write(tmp_path / "outputs" / ("case_%d.txt" % number), text)
        _scans_clean(printed, repo, _set_a(repo), needles_b, name)
        seen.add(name.split(",")[0])
        if name.startswith("verdict"):
            word = name.split(",")[0].split()[1]
            assert text.splitlines()[0] == "replay: " + word, "%s: wrong verdict line" % name
            assert code == (0 if word == "pass" else 1), "%s: exit code %d" % (name, code)
            assert ("report: written" in text.splitlines()) == name.endswith("local"), (
                "%s: the report line follows the mode" % name)
        elif name == "ingest ok":
            assert code == 0 and text.splitlines()[0] == "ingest: ok", "ingest ok: exit code %d" % code
        else:
            assert code == 2, "%s: exit code %d" % (name, code)
    assert seen >= {
        "verdict pass", "verdict fail", "verdict incomplete", "refusal snapshot_missing",
        "refusal records_missing", "refusal mapping_missing", "refused record", "ingest ok",
        "refused ingest", "usage 0", "usage 1", "usage 2", "usage 3"}, "a case did not run"
