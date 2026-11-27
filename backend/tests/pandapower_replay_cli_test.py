"""
The owner's two replay commands (pandapower-solver Phase 4, plan 04-03: AGR-04; decisions D-03 and
D-04; threats T-04-13 and T-04-14).

`main` runs in-process in a throwaway git repository under tmp_path, with the files the commands
read laid out by `pandapower_replay_fixture.private_layout`. Most tests replace the replay with a
stub built from `agree.gate`, so only two tests run the real solver. Nothing here reads the real
`data/private/`, and no test asserts a file mode (Windows has none).
"""

import collections
import datetime
import io
import json
import os
import re

import pytest

pytest.importorskip("pandapower")

import pandapower_replay_fixture as fixture  # noqa: E402
import private_leak_scan  # noqa: E402
from psse_job import constants, contract  # noqa: E402
from pandapower_job import agree, engine, private, recorded, replay, replay_cli  # noqa: E402

NOW = fixture.FIXED_NOW + datetime.timedelta(hours=2)

World = collections.namedtuple("World", ["repo", "stand", "layout", "snapshot_path"])


def _world(tmp_path, ingest=True):
    repo = fixture.make_repo(tmp_path / "repo")
    files = tmp_path / "files"
    files.mkdir()
    stand = fixture.light_standin(files)
    layout = fixture.private_layout(repo, stand)
    path = fixture.ingest_standins_result(repo, [stand]).path if ingest else None
    return World(repo, stand, layout, path)


def _run(argv, world, now=NOW, environ=None, replay_fn=None, repo=None):
    out, err = io.StringIO(), io.StringIO()
    code = replay_cli.main(
        argv, out=out, err=err, repo_root=repo or world.repo, now=now,
        environ={} if environ is None else environ, replay_fn=replay_fn)
    return code, out.getvalue(), err.getvalue()


def _files(repo):
    found = []
    for folder, names, names_in in os.walk(repo):
        names[:] = [name for name in names if name != ".git"]
        found += [os.path.relpath(os.path.join(folder, name), repo) for name in names_in]
    return sorted(found)


def _comparison(findings=(), nonempty=True):
    """A RunComparison with one voltage pair (deviation 0.003 pu of 0.01) and the given findings."""
    counts = dict.fromkeys(agree.COMPARE_COUNT_KEYS, 0)
    worst = {}
    if nonempty:
        counts.update(outages_voltage_high=1, pairs_compared=1, agreeing_keys=1)
        worst = {"voltage_pu": agree.Deviation("voltage_pu", 0.003, 0.01, 0.3, ("cid", "voltage_high", "7"))}
    return agree.RunComparison(tuple(findings), counts, dict.fromkeys(agree.NOTE_WORDS, 0), worst)


def _result(world, kind):
    """A ReplayResult built from agree.gate over a synthetic comparison of the world's run."""
    run_id = world.stand.bundle["run"]["run_id"]
    if kind == "pass":
        comparison = _comparison()
    elif kind == "incomplete":
        comparison = _comparison(nonempty=False)
    elif kind == "mapping":
        comparison = agree.replay_failed("mapping")
    elif kind == "fail":
        comparison = agree.replay_failed("load_flow")
    elif kind == "data":
        comparison = _comparison([agree.Finding(
            agree.FAILURE, "rating_data", ("dispatch", "AUSTIN"), ["applied_amps_per_conductor"])])
    else:
        raise AssertionError(kind)
    gate = agree.gate([(run_id, comparison)], [], 1, 1)
    status = "passed" if comparison.passed else "failed"
    return replay.ReplayResult(gate, [replay.RunOutcome(run_id, status, None, comparison)], 1)


def _stub(world, kind):
    result = _result(world, kind)
    calls = []

    def replay_fn(snapshot, backend, network, mapping, session_case):
        calls.append((network, mapping, session_case))
        return result

    replay_fn.calls = calls
    return replay_fn


# -- the closed vocabulary -------------------------------------------------------------------------


def _accepted(line):
    printer = replay_cli._Printer(io.StringIO(), io.StringIO())
    printer.say(line)
    return True


def _refused(line):
    printer = replay_cli._Printer(io.StringIO(), io.StringIO())
    with pytest.raises(ValueError):
        printer.say(line)


FIXED_LINES = [
    "ingest: ok", "snapshot: written", "ingest: refused (not_json)", "snapshot: refused (bad_marker)",
    "records: refused (not_json)", "private path: refused (exists)", "replay: pass",
    "replay: fail", "replay: incomplete", "replay: refused (placeholder_settings)",
    "replay: refused (snapshot_missing)", "runs in snapshot: 19", "runs replayed: 0",
    "runs passed: 1", "runs failed: 2", "runs excluded mapping_hash_differs: 3",
    "distinct configurations: 4", "pairs compared: 123456789", "margin comparisons: 5",
    "dispatch comparisons: 6", "borderline: 7", "runs with disagreeing results: 8",
    "runs failed at stage mapping: 1", "runs failed at stage validate_results: 12",
    "runs with differing data rating_data: 1", "runs with differing data sink_buses: 2",
    "non-empty comparisons voltage_high: 4", "not exercised: thermal_overload", "report: written",
    "usage: pandapower_replay.py {ingest,replay} ...", "usage error: bad or missing arguments",
    "usage error: unknown command", "error: unexpected (ValueError)",
    "snapshot runs: 3", "snapshot runs matching local mapping: not checked",
    "snapshot runs matching session case: 2",
    "ingest hint: " + recorded.EXPORT_REFUSAL_HINTS["too_large"],
]

OUT_OF_VOCABULARY = [
    "runs replayed: psse-20261120T103000Z-965d18f2",            # an id
    "runs replayed: " + "ab" * 32,                              # a hash
    "runs replayed: 1.5", "borderline: 0.01", "runs passed: 1234567890",    # a decimal, too long
    "runs passed: -1", "runs passed: ",
    "private path: refused (C:\\Users\\someone\\data\\private\\x.json)",    # a path
    "private path: refused (/home/someone/data/private/x.json)",
    "largest deviation: 0.0123", "deviation: 0.5 pu",                       # a deviation
    "runs failed at stage 90002-90003-1: 1",                                # an element
    "runs failed at stage banana: 1", "runs failed at stage mapping: one",
    "runs failed at stage mapping: 1 extra", "runs failed at stage mapping",
    "runs with differing data banana: 1", "runs with differing data rating_data: 0.5",
    "runs with differing data 90002-90003-1: 1",
    "runs with disagreeing results: abc", "runs with disagreeing results: 1.0",
    "runs excluded banana: 1", "runs excluded mapping_hash_differs: x",
    "non-empty comparisons banana: 1", "not exercised: banana", "not exercised: AUSTIN",
    "replay: pass with 3 findings", "replay: PASS", "replay: refused (some message)",
    "ingest: refused (a message with a value 12.5)", "records: refused (/some/path)",
    "ingest hint: " + recorded.EXPORT_REFUSAL_HINTS["too_large"] + " 12.5",
    "ingest hint: narrow it to psse-20261120%", "ingest hint: ",
    "error: unexpected (RuntimeError: secret)", "error: unexpected (runtime)",
    "usage: pandapower_net_check.py {ingest,check} ...", "", " replay: pass",
    "replay: pass\nrun id: x",
]


@pytest.mark.parametrize("line", FIXED_LINES)
def test_every_fixed_line_is_accepted(line):
    assert _accepted(line)


@pytest.mark.parametrize("line", OUT_OF_VOCABULARY)
def test_an_out_of_vocabulary_line_raises(line):
    _refused(line)


def test_the_printer_writes_to_the_chosen_stream():
    out, err = io.StringIO(), io.StringIO()
    printer = replay_cli._Printer(out, err)
    printer.say("ingest: ok")
    printer.problem("usage error: unknown command")
    assert out.getvalue() == "ingest: ok\n" and err.getvalue() == "usage error: unknown command\n"


def test_every_summary_line_matches_for_every_verdict(tmp_path):
    world = _world(tmp_path)
    for kind in ("pass", "fail", "incomplete", "mapping", "data"):
        lines = replay_cli.render_summary_lines(_result(world, kind).gate.summary)
        assert lines[0].startswith("replay: ")
        for line in lines:
            assert any(pattern.match(line) for pattern in replay_cli.CLI_LINE_PATTERNS), line


def test_the_summary_prints_a_count_per_kind_and_a_not_exercised_line_per_empty_kind(tmp_path):
    world = _world(tmp_path)
    summary = _result(world, "pass").gate.summary
    lines = replay_cli.render_summary_lines(summary)
    for kind in agree.KINDS:
        assert any(line.startswith("non-empty comparisons %s: " % kind) for line in lines)
        assert ("not exercised: %s" % kind in lines) == (kind in summary.not_exercised)


# -- ingest ----------------------------------------------------------------------------------------


def _export(world, name="export.json", document=None):
    path = os.path.join(world.repo, "data", "private", "pandapower", "incoming", name)
    return fixture.write_export_json(path, document or fixture.export_document([world.stand.bundle]))


def test_ingest_writes_the_snapshot_and_prints_counts_only(tmp_path):
    world = _world(tmp_path, ingest=False)
    path = _export(world)
    code, out, err = _run(["ingest", "--export", path], world, now=fixture.FIXED_NOW)
    assert code == 0 and err == ""
    lines = out.splitlines()
    assert lines[:2] == ["ingest: ok", "snapshot: written"]
    assert "snapshot runs: 1" in lines
    assert "snapshot runs matching local mapping: 1" in lines
    assert "snapshot runs matching session case: 1" in lines
    assert all(any(p.match(line) for p in replay_cli.CLI_LINE_PATTERNS) for line in lines)
    run_id = world.stand.bundle["run"]["run_id"]
    assert run_id not in out and fixture.CASE_SHA not in out and world.stand.mapping_sha256 not in out
    snapshots = os.path.join(world.repo, "data", "private", "pandapower", "snapshots")
    assert len(os.listdir(snapshots)) == 1


def test_ingest_without_a_mapping_or_a_check_folder_prints_not_checked(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    stand = fixture.light_standin(tmp_path)
    world = World(repo, stand, None, None)
    path = _export(world)
    code, out, err = _run(["ingest", "--export", path], world, now=fixture.FIXED_NOW)
    assert code == 0
    assert "snapshot runs matching local mapping: not checked" in out.splitlines()
    assert "snapshot runs matching session case: not checked" in out.splitlines()


def test_ingest_with_explicit_mapping_and_check_folder(tmp_path):
    world = _world(tmp_path, ingest=False)
    path = _export(world)
    code, out, _ = _run(["ingest", "--export", path, "--mapping", world.layout.mapping,
                         "--check-dir", world.layout.check_dir], world, now=fixture.FIXED_NOW)
    assert code == 0 and "snapshot runs matching local mapping: 1" in out.splitlines()


def test_ingest_a_different_mapping_counts_zero_matches(tmp_path):
    world = _world(tmp_path, ingest=False)
    other = os.path.join(world.repo, "data", "private", "pandapower", "other_mapping.json")
    with open(other, "w", encoding="utf-8") as handle:
        handle.write("{}")
    code, out, _ = _run(["ingest", "--export", _export(world), "--mapping", other], world,
                        now=fixture.FIXED_NOW)
    assert code == 0 and "snapshot runs matching local mapping: 0" in out.splitlines()


def test_ingest_refusal_prints_one_reason_and_writes_nothing(tmp_path):
    world = _world(tmp_path, ingest=False)
    bad = os.path.join(world.repo, "data", "private", "pandapower", "incoming", "bad.json")
    os.makedirs(os.path.dirname(bad), exist_ok=True)
    with open(bad, "w", encoding="utf-8") as handle:
        handle.write("{ not json")
    before = _files(world.repo)
    code, out, err = _run(["ingest", "--export", bad], world, now=fixture.FIXED_NOW)
    assert code == 2 and out == ""
    assert err == "ingest: refused (not_json)\n"
    assert _files(world.repo) == before


def test_ingest_counts_mismatch_adds_the_one_fixed_hint(tmp_path):
    world = _world(tmp_path, ingest=False)
    document = fixture.export_document([world.stand.bundle])
    document["counts"]["runs"] = 99
    path = _export(world, document=document)
    code, out, err = _run(["ingest", "--export", path], world, now=fixture.FIXED_NOW)
    assert code == 2 and out == ""
    assert err.splitlines() == [
        "ingest: refused (counts_mismatch)",
        "ingest hint: " + recorded.EXPORT_REFUSAL_HINTS["counts_mismatch"]]


def test_ingest_outside_the_private_folder_is_refused(tmp_path):
    world = _world(tmp_path, ingest=False)
    outside = tmp_path / "export_elsewhere.json"
    fixture.write_export_json(str(outside), fixture.export_document([world.stand.bundle]))
    code, out, err = _run(["ingest", "--export", str(outside)], world, now=fixture.FIXED_NOW)
    assert code == 2 and out == ""
    assert err == "private path: refused (outside_private_root)\n"


def test_ingest_in_the_same_second_twice_is_refused_as_existing(tmp_path):
    world = _world(tmp_path, ingest=False)
    path = _export(world)
    assert _run(["ingest", "--export", path], world, now=fixture.FIXED_NOW)[0] == 0
    code, _, err = _run(["ingest", "--export", path], world, now=fixture.FIXED_NOW)
    assert code == 2 and err == "private path: refused (exists)\n"


# -- replay: verdicts, exit codes, the report ------------------------------------------------------


def _report_paths(world):
    folder = os.path.join(world.repo, "data", "private", "pandapower", "replays")
    return sorted(os.path.join(folder, name, "report.json") for name in os.listdir(folder)) \
        if os.path.isdir(folder) else []


def test_a_local_pass_writes_the_report_and_prints_counts_only(tmp_path):
    world = _world(tmp_path)
    stub = _stub(world, "pass")
    code, out, err = _run(["replay"], world, replay_fn=stub)
    assert code == 0 and err == ""
    lines = out.splitlines()
    assert lines[0] == "replay: pass" and lines[-1] == "report: written"
    assert all(any(p.match(line) for p in replay_cli.CLI_LINE_PATTERNS) for line in lines)
    assert len(_report_paths(world)) == 1
    assert len(stub.calls) == 1
    network, mapping, session_case = stub.calls[0]
    assert network == world.layout.network or os.path.samefile(network, world.layout.network)
    assert session_case == fixture.CASE_SHA


@pytest.mark.parametrize("kind,word,code", [
    ("pass", "pass", 0), ("fail", "fail", 1), ("incomplete", "incomplete", 1),
    ("mapping", "fail", 1), ("data", "fail", 1)])
def test_the_exit_code_follows_the_verdict(tmp_path, kind, word, code):
    world = _world(tmp_path)
    got, out, _ = _run(["replay"], world, replay_fn=_stub(world, kind))
    assert got == code and out.splitlines()[0] == "replay: " + word


def test_a_stage_mapping_failure_reads_differently_from_a_disagreement(tmp_path):
    world = _world(tmp_path)
    code, out, _ = _run(["replay"], world, replay_fn=_stub(world, "mapping"))
    lines = out.splitlines()
    assert code == 1
    assert "runs failed at stage mapping: 1" in lines
    assert "runs with disagreeing results: 0" in lines
    assert not any(line.startswith("runs with differing data") for line in lines)
    assert not any(line.startswith("runs excluded") for line in lines)


def test_stored_input_data_that_differ_read_differently_from_a_disagreement(tmp_path):
    world = _world(tmp_path)
    code, out, _ = _run(["replay"], world, replay_fn=_stub(world, "data"))
    lines = out.splitlines()
    assert code == 1
    assert "runs with differing data rating_data: 1" in lines
    assert not any(line.startswith("runs failed at stage") for line in lines)


def test_the_report_holds_the_detail_and_the_terminal_holds_none_of_it(tmp_path):
    world = _world(tmp_path)
    code, out, _ = _run(["replay"], world, replay_fn=_stub(world, "data"))
    (path,) = _report_paths(world)
    with open(path, "r", encoding="ascii") as handle:
        report = json.load(handle)
    assert report[recorded.REPORT_MARKER] == 1
    assert report["verdict"] == "fail"
    assert report["header"]["tolerances"]["voltage_tolerance_pu"] == 0.01
    assert report["header"]["settings"]["placeholder"] is False
    assert report["findings"] and report["outcomes"][0]["status"] == "failed"
    run_id = world.stand.bundle["run"]["run_id"]
    assert run_id in json.dumps(report) and run_id not in out
    assert report["largest_deviation"] is not None
    values = [report["largest_deviation"][name] for name in ("deviation", "allowance", "utilisation")]
    for value in values:
        for text in (repr(value), "%g" % value, "%.4f" % value):
            if len(text) > 3:
                assert text not in out
    assert all("." not in line for line in out.splitlines())


def test_the_report_is_flagged_by_the_leak_guard_shape_layer(tmp_path):
    world = _world(tmp_path)
    _run(["replay"], world, replay_fn=_stub(world, "pass"))
    (path,) = _report_paths(world)
    findings = private_leak_scan.scan_paths([os.path.realpath(path)], root=world.repo)
    assert any(item.layer == "shape" and item.pattern == "pandapower_marker" for item in findings)


def test_a_second_replay_in_the_same_second_is_refused(tmp_path):
    world = _world(tmp_path)
    stub = _stub(world, "pass")
    assert _run(["replay"], world, replay_fn=stub)[0] == 0
    code, out, err = _run(["replay"], world, replay_fn=stub)
    assert code == 2 and out == ""
    assert err == "private path: refused (exists)\n"
    assert len(_report_paths(world)) == 1


# -- CI mode ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("argv,environ", [
    (["replay", "--ci"], {}),
    (["replay"], {"GITHUB_ACTIONS": "true"}),
    (["replay", "--ci"], {"GITHUB_ACTIONS": "true"}),
])
def test_ci_mode_writes_no_file_and_no_folder(tmp_path, argv, environ):
    world = _world(tmp_path)
    before = _files(world.repo)
    folders = sorted(folder for folder, _, _ in os.walk(world.repo) if ".git" not in folder)
    code, out, _ = _run(argv, world, environ=environ, replay_fn=_stub(world, "pass"))
    assert code == 0
    assert _files(world.repo) == before
    assert sorted(folder for folder, _, _ in os.walk(world.repo) if ".git" not in folder) == folders
    assert "report: written" not in out


def test_the_ci_lines_are_the_local_lines_without_the_report_line(tmp_path):
    world = _world(tmp_path)
    stub = _stub(world, "pass")
    _, ci_out, _ = _run(["replay", "--ci"], world, replay_fn=stub)
    _, local_out, _ = _run(["replay"], world, replay_fn=stub)
    assert local_out.splitlines() == ci_out.splitlines() + ["report: written"]


@pytest.mark.parametrize("value", ["false", "1", "True", "TRUE", "yes", ""])
def test_any_other_value_of_github_actions_leaves_local_mode_on(tmp_path, value):
    world = _world(tmp_path)
    code, out, _ = _run(["replay"], world, environ={"GITHUB_ACTIONS": value},
                        replay_fn=_stub(world, "pass"))
    assert code == 0 and out.splitlines()[-1] == "report: written"
    assert len(_report_paths(world)) == 1


# -- replay: refusals -------------------------------------------------------------------------------


def test_replay_without_a_snapshot_is_refused(tmp_path):
    world = _world(tmp_path, ingest=False)
    code, out, err = _run(["replay"], world, replay_fn=_stub(world, "pass"))
    assert (code, out, err) == (2, "", "replay: refused (snapshot_missing)\n")


def test_replay_without_a_check_folder_is_refused(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    stand = fixture.light_standin(tmp_path)
    fixture.ingest_standins_result(repo, [stand])
    world = World(repo, stand, None, None)
    code, out, err = _run(["replay"], world, replay_fn=lambda *args: pytest.fail("no replay"))
    assert (code, out, err) == (2, "", "replay: refused (records_missing)\n")


def test_replay_without_a_mapping_is_refused(tmp_path):
    world = _world(tmp_path)
    os.remove(world.layout.mapping)
    code, out, err = _run(["replay"], world, replay_fn=lambda *args: pytest.fail("no replay"))
    assert (code, out, err) == (2, "", "replay: refused (mapping_missing)\n")


def test_replay_without_the_converted_network_is_refused(tmp_path):
    world = _world(tmp_path)
    os.remove(world.layout.network)
    code, out, err = _run(["replay", "--check-dir", world.layout.check_dir], world,
                          replay_fn=lambda *args: pytest.fail("no replay"))
    assert (code, out, err) == (2, "", "replay: refused (network_missing)\n")


def test_a_refusal_of_the_replay_itself_is_printed_by_reason(tmp_path):
    world = _world(tmp_path)

    def refuse(*args):
        raise replay.ReplayRefused("placeholder_settings")

    code, out, err = _run(["replay"], world, replay_fn=refuse)
    assert (code, out, err) == (2, "", "replay: refused (placeholder_settings)\n")
    assert _report_paths(world) == []


def test_unusable_recorded_settings_are_refused(tmp_path):
    world = _world(tmp_path)
    with open(world.layout.report, "w", encoding="utf-8") as handle:
        handle.write("{ nope")
    code, out, err = _run(["replay"], world, replay_fn=lambda *args: pytest.fail("no replay"))
    assert (code, out, err) == (2, "", "records: refused (not_json)\n")


def test_a_placeholder_settings_record_never_reaches_a_replay(tmp_path):
    world = _world(tmp_path)
    with open(world.layout.report, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    document["settings"]["sources"]["enforce_q_lims"] = "placeholder: not decided"
    with open(world.layout.report, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    code, out, err = _run(["replay"], world, replay_fn=lambda *args: pytest.fail("no replay"))
    assert (code, out, err) == (2, "", "records: refused (placeholder_source)\n")


def test_a_bad_snapshot_is_refused_by_reason(tmp_path):
    world = _world(tmp_path)
    bad = os.path.join(world.repo, "data", "private", "pandapower", "snapshots", "snapshot_bad.json")
    with open(bad, "w", encoding="utf-8") as handle:
        handle.write("{}")
    code, out, err = _run(["replay", "--snapshot", bad], world,
                          replay_fn=lambda *args: pytest.fail("no replay"))
    assert (code, out, err) == (2, "", "snapshot: refused (bad_marker)\n")


@pytest.mark.parametrize("which", ["snapshot", "mapping"])
def test_an_input_outside_the_private_folder_is_refused(tmp_path, which):
    world = _world(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    code, out, err = _run(["replay", "--" + which, str(outside)], world,
                          replay_fn=lambda *args: pytest.fail("no replay"))
    assert (code, out, err) == (2, "", "private path: refused (outside_private_root)\n")


def test_the_newest_complete_check_folder_and_snapshot_are_the_defaults(tmp_path):
    world = _world(tmp_path)
    sessions = os.path.join(world.repo, "data", "private", "pandapower", "sessions")
    newer = os.path.join(sessions, "session_one", "check_29990101T000000Z")
    os.makedirs(newer)
    with open(os.path.join(newer, "report.json"), "w", encoding="utf-8") as handle:
        handle.write("{}")          # newest by name, but not complete: skipped
    stub = _stub(world, "pass")
    assert _run(["replay"], world, replay_fn=stub)[0] == 0
    network = stub.calls[0][0]
    assert os.path.samefile(network, world.layout.network)


def test_an_unexpected_error_prints_the_class_name_only(tmp_path):
    world = _world(tmp_path)

    def broken(*args):
        raise RuntimeError("secret text 12.5 psse-20261120")

    code, out, err = _run(["replay"], world, replay_fn=broken)
    assert (code, out, err) == (2, "", "error: unexpected (RuntimeError)\n")


# -- usage -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("argv", [
    [], ["bogus"], ["ingest"], ["replay", "--verbose"], ["replay", "--allow-placeholder"],
    ["replay", "--force"], ["replay", "--override-hash"], ["replay", "--snapshot"],
    ["ingest", "--export"], ["replay", "positional"], ["--help"], ["replay", "-h"],
    ["replay", "--ci=maybe"],
])
def test_a_bad_command_line_prints_the_two_usage_lines_and_echoes_nothing(tmp_path, argv):
    world = _world(tmp_path)
    code, out, err = _run(argv, world)
    assert code == 2 and out == ""
    assert err == ("usage: pandapower_replay.py {ingest,replay} ...\n"
                   "usage error: bad or missing arguments\n")


def test_no_flag_prints_a_figure_or_overrides_a_hash_or_a_placeholder():
    parser = replay_cli._build_parser()
    names = set()
    for action in parser._subparsers._group_actions[0].choices.values():
        for option in action._actions:
            names.update(option.option_strings)
    assert names == {"--export", "--mapping", "--check-dir", "--snapshot", "--ci"}


# -- real solver: the whole path in process, and the scan of its output ------------------------------


@pytest.fixture(scope="module")
def stress_standin(tmp_path_factory):
    return fixture.standin(tmp_path_factory.mktemp("cli_stress"), stress=True)


def test_a_real_local_replay_prints_counts_only_and_its_output_scans_clean(tmp_path, stress_standin):
    repo = fixture.make_repo(tmp_path / "repo")
    fixture.private_layout(repo, stress_standin)
    fixture.ingest_standins_result(repo, [stress_standin])
    world = World(repo, stress_standin, None, None)
    code, out, err = _run(["replay"], world)
    assert code == 0 and err == ""
    lines = out.splitlines()
    assert lines[0] == "replay: pass" and lines[-1] == "report: written"
    assert "runs replayed: 1" in lines and "runs passed: 1" in lines
    assert "distinct configurations: 1" in lines
    assert all(any(p.match(line) for p in replay_cli.CLI_LINE_PATTERNS) for line in lines)

    outside = tmp_path / "printed_output.txt"
    outside.write_text(out, encoding="utf-8")
    needles = private_leak_scan.derive_needles(os.path.join(repo, "data", "private"))
    assert private_leak_scan.scan_paths([str(outside)], needles=needles, root=repo) == []
    (path,) = _report_paths(World(repo, None, None, None))
    with open(path, "r", encoding="ascii") as handle:
        report = json.load(handle)
    assert report["verdict"] == "pass"
    assert report["largest_deviation"]["utilisation"] == 0
    assert report["summary"]["runs_replayed"] == 1
    assert report["header"]["settings"]["solver"] == "pandapower"
    assert stress_standin.bundle["run"]["run_id"] in json.dumps(report)


def test_a_real_replay_of_a_perturbed_run_reports_a_nonzero_deviation_only_in_the_report(
        tmp_path, stress_standin):
    repo = fixture.make_repo(tmp_path / "repo")
    fixture.private_layout(repo, stress_standin)

    def shift(bundle):
        row = max((r for r in bundle["contingencies"] if r["violation_kind"] == "thermal_overload"),
                  key=lambda r: r["exceeded_by"])
        row["observed_value"] *= 1.01

    fixture.perturbed_snapshot(repo, stress_standin, shift)
    world = World(repo, stress_standin, None, None)
    code, out, _ = _run(["replay"], world, replay_fn=lambda snapshot, backend, network, mapping, case:
                        replay.replay_snapshot(snapshot, backend, network, mapping, case,
                                               runner=lambda selection: stress_standin.results))
    assert code == 0 and out.splitlines()[0] == "replay: pass"
    (path,) = _report_paths(World(repo, None, None, None))
    with open(path, "r", encoding="ascii") as handle:
        report = json.load(handle)
    largest = report["largest_deviation"]
    assert 0 < largest["utilisation"] < 1 and largest["deviation"] > 0
    for name in ("deviation", "allowance", "utilisation"):
        value = largest[name]
        for text in (repr(value), "%g" % value, "%.3f" % value, "%.1f" % value):
            assert text not in re.split(r"[\s:]+", out)
    assert all("." not in line for line in out.splitlines())


def test_the_leak_scan_of_the_printed_output_can_fire(tmp_path, stress_standin):
    repo = fixture.make_repo(tmp_path / "repo")
    layout = fixture.private_layout(repo, stress_standin)
    needles = private_leak_scan.derive_needles(os.path.join(repo, "data", "private"))
    planted = tmp_path / "planted.txt"
    planted.write_text("replay: pass\nmapping " + stress_standin.mapping_sha256 + "\n", encoding="utf-8")
    assert private_leak_scan.scan_paths([str(planted)], needles=needles, root=repo) != []
    assert layout.report
