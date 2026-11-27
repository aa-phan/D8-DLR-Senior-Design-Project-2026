"""
The replay's plan, failure semantics, refusals and session hashes (pandapower-solver Phase 4, plan
04-03: AGR-01, AGR-02; threats T-04-10 to T-04-12).

Everything here runs without a solve: runners are recorders or raise, and the stored ratings come
from the public fixture's rating selection. The recorded rows are the public synthetic rows of
`psse_local_pg`, and every file that looks private lives in a throwaway repository under tmp_path.
The real-solver matrix is in `pandapower_replay_study_test.py`.
"""

import copy
import datetime
import json
import os

import pytest

pytest.importorskip("pandapower")

import pandapower_replay_fixture as fixture  # noqa: E402
import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import constants, contract, ratings  # noqa: E402
from pandapower_job import agree, engine, recorded, replay  # noqa: E402

USED = ratings.ratings_used(study_fixture.selection())
HEX_C = "12" * 32


def _scaled(used, city, factor):
    """A copy of ratings_used with one city's amps and circuit amps multiplied by `factor`."""
    other = copy.deepcopy(used)
    other[city]["rating_amps_per_conductor"] *= factor
    other[city]["rating_amps_circuit"] *= factor
    return other


def _bundle(n, mapping_sha256, case_sha256=fixture.CASE_SHA, outcome="fallback", used=None):
    started = fixture.FIXED_NOW + datetime.timedelta(hours=n)
    bundle = fixture.run_bundle(n, started, outcome, mapping_sha256, case_sha256)
    if outcome != "failed":
        bundle["run"]["ratings_used"] = copy.deepcopy(USED if used is None else used)
    return bundle


def _item(bundle):
    return recorded.RecordedRun(bundle["run"], bundle["dispatch"], bundle["margins"],
                                bundle["contingencies"])


def _reason(bundle, local=fixture.HEX_A, session=fixture.CASE_SHA):
    planned = replay.plan([_item(bundle)], local, session)
    return planned.exclusions[0][1] if planned.exclusions else None


# -- selection_from_ratings_used -------------------------------------------------------------------


@pytest.mark.parametrize("stress", [False, True])
def test_the_selection_is_rebuilt_exactly_from_the_stored_ratings(stress):
    selection = study_fixture.selection()
    if stress:
        selection = fixture.stress_selection(selection)
    rebuilt = replay.selection_from_ratings_used(ratings.ratings_used(selection))
    assert rebuilt is not None
    for city in constants.CITIES:
        original, got = selection.choices[city], rebuilt.choices[city]
        for name in ("source", "fallback_reason", "amps_per_conductor", "subconductors_per_phase",
                     "amps_circuit", "static_amps_per_conductor", "row_valid_time",
                     "row_computed_at"):
            assert getattr(got, name) == getattr(original, name), name


def test_a_city_rating_entry_with_times_is_rebuilt_with_aware_times():
    used = copy.deepcopy(USED)
    used["AUSTIN"].update(source="city_rating", fallback_reason=None,
                          city_rating_valid_time="2026-11-20T10:00:00+00:00",
                          city_rating_computed_at="2026-11-20T10:05:00+00:00")
    got = replay.selection_from_ratings_used(used).choices["AUSTIN"]
    assert got.row_valid_time == datetime.datetime(2026, 11, 20, 10, 0, tzinfo=datetime.timezone.utc)
    assert got.row_computed_at.utcoffset() == datetime.timedelta(0)


def _drop(key):
    def change(item):
        del item[key]
    return change


def _set(key, value):
    def change(item):
        item[key] = value
    return change


UNUSABLE = [
    ("missing source", _drop("source")),
    ("missing fallback", _drop("fallback_reason")),
    ("missing amps", _drop("rating_amps_per_conductor")),
    ("missing count", _drop("subconductors_per_phase")),
    ("missing circuit", _drop("rating_amps_circuit")),
    ("zero amps", _set("rating_amps_per_conductor", 0)),
    ("negative amps", _set("rating_amps_per_conductor", -5.0)),
    ("nan amps", _set("rating_amps_per_conductor", float("nan"))),
    ("infinite amps", _set("rating_amps_per_conductor", float("inf"))),
    ("text amps", _set("rating_amps_per_conductor", "182.5")),
    ("boolean amps", _set("rating_amps_per_conductor", True)),
    ("zero count", _set("subconductors_per_phase", 0)),
    ("float count", _set("subconductors_per_phase", 2.0)),
    ("boolean count", _set("subconductors_per_phase", True)),
    ("unknown source", _set("source", "guess")),
    ("circuit differs", _set("rating_amps_circuit", 1.001 * USED["AUSTIN"]["rating_amps_circuit"])),
    ("bad time", _set("city_rating_valid_time", "not a time")),
]


@pytest.mark.parametrize("name,change", UNUSABLE, ids=[name for name, _ in UNUSABLE])
def test_an_unusable_entry_is_none(name, change):
    used = copy.deepcopy(USED)
    change(used["MIDLAND"])
    assert replay.selection_from_ratings_used(used) is None


def test_a_missing_city_or_a_wrong_type_is_none():
    used = copy.deepcopy(USED)
    del used["EL_PASO"]
    assert replay.selection_from_ratings_used(used) is None
    assert replay.selection_from_ratings_used(None) is None
    assert replay.selection_from_ratings_used([]) is None


def test_a_circuit_within_the_relative_tolerance_is_usable():
    used = copy.deepcopy(USED)
    used["AUSTIN"]["rating_amps_circuit"] *= 1 + 5e-7
    assert replay.selection_from_ratings_used(used) is not None


# -- the plan stage: every reason once, and their order -------------------------------------------


def test_a_clean_run_has_no_reason():
    assert _reason(_bundle(1, fixture.HEX_A)) is None


def test_failed_run_is_a_reason():
    assert _reason(_bundle(1, fixture.HEX_A, outcome="failed")) == "failed_run"


def test_no_mapping_hash_is_a_reason():
    bundle = _bundle(1, None)
    assert _reason(bundle) == "mapping_hash_missing"


def test_a_different_mapping_hash_is_a_reason():
    assert _reason(_bundle(1, fixture.HEX_B)) == "mapping_hash_differs"


def test_no_case_hash_is_a_reason():
    assert _reason(_bundle(1, fixture.HEX_A, case_sha256=None)) == "case_hash_missing"


def test_no_session_case_hash_is_a_reason():
    assert _reason(_bundle(1, fixture.HEX_A), session=None) == "case_hash_missing"


def test_a_different_case_hash_is_a_reason():
    assert _reason(_bundle(1, fixture.HEX_A, case_sha256=HEX_C)) == "case_hash_differs"


def test_unusable_ratings_are_a_reason():
    used = copy.deepcopy(USED)
    used["AUSTIN"]["rating_amps_per_conductor"] = -1
    assert _reason(_bundle(1, fixture.HEX_A, used=used)) == "ratings_unusable"
    assert _reason(_bundle(1, fixture.HEX_A, used={})) == "ratings_unusable"


def test_incomplete_rows_are_a_reason():
    bundle = _bundle(1, fixture.HEX_A)
    del bundle["dispatch"][0]
    assert _reason(bundle) == "rows_incomplete"


def test_the_precedence_is_the_order_of_the_closed_list():
    assert agree.EXCLUSION_REASONS == (
        "failed_run", "mapping_hash_missing", "mapping_hash_differs", "case_hash_missing",
        "case_hash_differs", "ratings_unusable", "rows_incomplete")
    bundle = _bundle(1, None, case_sha256=None, used={})
    bundle["run"]["outcome"] = "failed"
    dropped = bundle["dispatch"].pop(0)
    steps = [
        ("failed_run", lambda: bundle["run"].update(outcome="fallback")),
        ("mapping_hash_missing", lambda: bundle["run"].update(mapping_sha256=fixture.HEX_B)),
        ("mapping_hash_differs", lambda: bundle["run"].update(mapping_sha256=fixture.HEX_A)),
        ("case_hash_missing", lambda: bundle["run"].update(case_sha256=HEX_C)),
        ("case_hash_differs", lambda: bundle["run"].update(case_sha256=fixture.CASE_SHA)),
        ("ratings_unusable", lambda: bundle["run"].update(ratings_used=copy.deepcopy(USED))),
        ("rows_incomplete", lambda: bundle["dispatch"].insert(0, dropped)),
    ]
    for expected, repair in steps:
        assert _reason(bundle) == expected
        repair()
    assert _reason(bundle) is None


def test_an_excluded_run_is_listed_and_the_eligible_ones_are_grouped():
    bundles = [_bundle(1, fixture.HEX_A), _bundle(2, fixture.HEX_A),
               _bundle(3, fixture.HEX_A, used=_scaled(USED, "AUSTIN", 0.5)),
               _bundle(4, fixture.HEX_B)]
    planned = replay.plan([_item(bundle) for bundle in bundles], fixture.HEX_A, fixture.CASE_SHA)
    assert [len(group) for group in planned.groups.values()] == [2, 1]
    assert planned.exclusions == [(bundles[3]["run"]["run_id"], "mapping_hash_differs")]


def test_the_configuration_key_ignores_times_and_depends_on_ratings_and_mapping():
    first = replay.selection_from_ratings_used(USED)
    timed = copy.deepcopy(USED)
    timed["AUSTIN"]["city_rating_valid_time"] = "2026-11-20T10:00:00+00:00"
    assert replay.configuration_key("a", first) == replay.configuration_key(
        "a", replay.selection_from_ratings_used(timed))
    assert replay.configuration_key("a", first) != replay.configuration_key("b", first)
    other = replay.selection_from_ratings_used(_scaled(USED, "EL_PASO", 0.9))
    assert replay.configuration_key("a", first) != replay.configuration_key("a", other)


# -- replay_snapshot without a solve ---------------------------------------------------------------


@pytest.fixture()
def files(tmp_path):
    """A repository, a mapping, a converted network (never solved here) and the mapping's hash."""
    repo = fixture.make_repo(tmp_path / "repo")
    network = study_fixture.write_converted(tmp_path)
    mapping = fixture.write_mapping(tmp_path)
    sha = engine.prepare_run(study_fixture.fixture_backend(), network, mapping).mapping_sha256
    return repo, network, mapping, sha


class _Recorder(object):
    """A runner that records every selection and raises StudyFailed at a chosen stage."""

    def __init__(self, stage="load_flow"):
        self.stage = stage
        self.calls = []

    def __call__(self, selection):
        self.calls.append(selection)
        raise contract.StudyFailed(self.stage, "a message that must never be kept")


def _replay(files, bundles, runner, backend=None, session=fixture.CASE_SHA):
    repo, network, mapping, _ = files
    snapshot = fixture.snapshot_of_bundles(repo, bundles)
    return replay.replay_snapshot(
        snapshot, backend or study_fixture.fixture_backend(), network, mapping, session,
        runner=runner)


def test_the_runner_is_called_once_per_distinct_configuration(files):
    sha = files[3]
    bundles = [_bundle(1, sha), _bundle(2, sha), _bundle(3, sha),
               _bundle(4, sha, used=_scaled(USED, "AUSTIN", 0.5)),
               _bundle(5, sha, used=_scaled(USED, "AUSTIN", 0.5))]
    runner = _Recorder()
    result = _replay(files, bundles, runner)
    assert len(runner.calls) == 2
    assert result.configurations == 2
    assert result.gate.summary.configurations == 2
    assert result.gate.summary.runs_replayed == 5


def test_every_exclusion_reason_is_produced_and_never_replayed(files):
    sha = files[3]
    used_bad = copy.deepcopy(USED)
    used_bad["AUSTIN"]["rating_amps_per_conductor"] = -1
    short = _bundle(8, sha)
    del short["dispatch"][0]
    bundles = [
        _bundle(1, sha), _bundle(2, sha, outcome="failed"), _bundle(3, None),
        _bundle(4, fixture.HEX_B), _bundle(5, sha, case_sha256=None),
        _bundle(6, sha, case_sha256=HEX_C), _bundle(7, sha, used=used_bad), short]
    runner = _Recorder()
    result = _replay(files, bundles, runner)
    excluded = result.gate.summary.excluded
    assert [reason for reason in agree.EXCLUSION_REASONS if excluded[reason] != 1] == []
    assert len(runner.calls) == 1
    assert result.gate.summary.runs_replayed == 1
    assert result.gate.summary.runs_in_snapshot == 8
    statuses = [(outcome.status, outcome.reason) for outcome in result.outcomes]
    assert statuses.count(("excluded", "mapping_hash_differs")) == 1
    assert [status for status, _ in statuses].count("excluded") == 7
    assert len(result.outcomes) == 8


def test_a_raising_study_is_a_failed_run_never_an_exclusion(files):
    sha = files[3]
    result = _replay(files, [_bundle(1, sha), _bundle(2, sha)], _Recorder("load_flow"))
    summary = result.gate.summary
    assert result.gate.word == "fail"
    assert summary.runs_replayed == 2 and summary.runs_failed == 2 and summary.runs_passed == 0
    assert sum(summary.excluded.values()) == 0
    assert summary.failed_stages["load_flow"] == 2
    assert summary.runs_disagreeing == 0
    assert [(o.status, o.reason) for o in result.outcomes] == [("failed", "load_flow")] * 2
    assert "must never be kept" not in repr(result.outcomes)


def test_an_unknown_stage_is_stored_as_internal(files):
    result = _replay(files, [_bundle(1, files[3])], _Recorder("not_a_stage"))
    assert result.gate.summary.failed_stages["internal"] == 1


def test_results_that_fail_the_validator_are_a_failed_run(files):
    def runner(selection):
        return contract.StudyResults([], [], [], 0, "all", "test")

    result = _replay(files, [_bundle(1, files[3])], runner)
    assert result.gate.word == "fail"
    assert result.gate.summary.failed_stages["validate_results"] == 1
    assert result.outcomes[0].reason == "validate_results"
    assert sum(result.gate.summary.excluded.values()) == 0


def test_any_other_exception_propagates(files):
    def runner(selection):
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        _replay(files, [_bundle(1, files[3])], runner)


def test_a_mapping_the_engine_cannot_run_is_a_stage_mapping_failure_not_a_disagreement(files):
    sha = files[3]
    backend = study_fixture.fixture_backend(enforce_q_lims=None)
    result = _replay(files, [_bundle(1, sha)], None, backend=backend)
    summary = result.gate.summary
    assert result.gate.word == "fail"
    assert summary.failed_stages["mapping"] == 1
    assert summary.runs_disagreeing == 0
    assert sum(summary.excluded.values()) == 0
    assert summary.runs_failed == 1


# -- refusals --------------------------------------------------------------------------------------


class _Never(object):
    def __call__(self, selection):
        raise AssertionError("no study may be run on a refusal")


def _refusal(files, **changes):
    repo, network, mapping, _ = files
    _refusal.count += 1
    snapshot = fixture.snapshot_of_bundles(
        repo, [_bundle(1, files[3])], now=fixture.FIXED_NOW + datetime.timedelta(seconds=_refusal.count))
    arguments = dict(backend=study_fixture.fixture_backend(), network=network, mapping=mapping)
    arguments.update(changes)
    with pytest.raises(replay.ReplayRefused) as caught:
        replay.replay_snapshot(snapshot, arguments["backend"], arguments["network"],
                               arguments["mapping"], fixture.CASE_SHA, runner=_Never())
    return caught.value


_refusal.count = 0


def test_placeholder_settings_are_refused_before_any_study(files):
    problem = _refusal(files, backend=engine.PLACEHOLDER_BACKEND)
    assert problem.reason == "placeholder_settings"
    assert str(problem) == "replay refused: placeholder_settings"


def test_an_unusable_mapping_is_refused(files, tmp_path):
    broken = tmp_path / "broken_mapping.json"
    broken.write_text("{ not json", encoding="utf-8")
    assert _refusal(files, mapping=str(broken)).reason == "mapping_unusable"


def test_a_placeholder_flagged_mapping_file_is_refused(files, tmp_path):
    flagged = study_fixture.write_placeholder_mapping(tmp_path, name="flagged.json")
    assert _refusal(files, mapping=flagged).reason == "mapping_unusable"


def test_a_missing_network_or_mapping_is_refused(files, tmp_path):
    missing = str(tmp_path / "nowhere.json")
    assert _refusal(files, network=missing).reason == "network_missing"
    assert _refusal(files, mapping=missing).reason == "mapping_missing"
    assert _refusal(files, network=None).reason == "network_missing"


def test_no_override_exists():
    import inspect
    names = set(inspect.signature(replay.replay_snapshot).parameters)
    assert names == {"snapshot", "backend", "network_path", "mapping_path", "session_case_sha256",
                     "allow_placeholder", "runner"}
    assert all(reason in replay.REFUSAL_REASONS for reason in (
        "snapshot_missing", "records_missing", "mapping_missing", "network_missing",
        "mapping_unusable", "placeholder_settings"))
    with pytest.raises(ValueError):
        replay.ReplayRefused("something_else")


# -- engine.load_session_hashes --------------------------------------------------------------------


def _report(tmp_path, document, marker=True):
    folder = tmp_path / "check"
    folder.mkdir(exist_ok=True)
    body = dict(document)
    if marker:
        body[recorded.REPORT_MARKER] = 1
    (folder / "report.json").write_text(json.dumps(body), encoding="utf-8")
    return str(folder)


def test_session_hashes_are_read(tmp_path):
    folder = _report(tmp_path, {"session": {"case_sha256": fixture.CASE_SHA,
                                            "mapping_sha256": fixture.HEX_A}})
    assert engine.load_session_hashes(folder) == (fixture.CASE_SHA, fixture.HEX_A)


def test_an_absent_hash_is_none(tmp_path):
    folder = _report(tmp_path, {"session": {"case_sha256": fixture.CASE_SHA}})
    assert engine.load_session_hashes(folder) == (fixture.CASE_SHA, None)
    folder = _report(tmp_path, {"session": {"case_sha256": None, "mapping_sha256": None}})
    assert engine.load_session_hashes(folder) == (None, None)


@pytest.mark.parametrize("session", [None, [], "text", 5])
def test_a_missing_or_wrong_session_is_missing_field(tmp_path, session):
    document = {} if session is None else {"session": session}
    with pytest.raises(engine.RecordsRefused) as caught:
        engine.load_session_hashes(_report(tmp_path, document))
    assert caught.value.reason == "missing_field"


@pytest.mark.parametrize("value", ["AB" * 32, "ab" * 31, "ab" * 33, "zz" * 32, 5, True, [], ""])
def test_a_hash_of_the_wrong_shape_is_bad_value(tmp_path, value):
    folder = _report(tmp_path, {"session": {"case_sha256": value}})
    with pytest.raises(engine.RecordsRefused) as caught:
        engine.load_session_hashes(folder)
    assert caught.value.reason == "bad_value"
    assert str(caught.value) == "recorded settings refused: bad_value"


def test_a_missing_unreadable_or_unmarked_report_keeps_its_reason(tmp_path):
    with pytest.raises(engine.RecordsRefused) as caught:
        engine.load_session_hashes(str(tmp_path / "nowhere"))
    assert caught.value.reason == "unreadable"
    folder = tmp_path / "bad"
    folder.mkdir()
    (folder / "report.json").write_text("{ nope", encoding="utf-8")
    with pytest.raises(engine.RecordsRefused) as caught:
        engine.load_session_hashes(str(folder))
    assert caught.value.reason == "not_json"
    unmarked = _report(tmp_path, {"session": {}}, marker=False)
    with pytest.raises(engine.RecordsRefused) as caught:
        engine.load_session_hashes(unmarked)
    assert caught.value.reason == "bad_marker"
    with pytest.raises(engine.RecordsRefused) as caught:
        engine.load_session_hashes(None)
    assert caught.value.reason in ("unreadable",)


def test_a_non_object_report_is_refused(tmp_path):
    folder = tmp_path / "list"
    folder.mkdir()
    (folder / "report.json").write_text("[1]", encoding="utf-8")
    with pytest.raises(engine.RecordsRefused) as caught:
        engine.load_session_hashes(str(folder))
    assert caught.value.reason == "not_a_dict"
    assert os.path.isdir(str(folder))
