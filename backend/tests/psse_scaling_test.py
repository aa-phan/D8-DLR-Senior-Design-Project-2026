"""
Tests for Phase 4's per-city scaling of the study (pss-e-integration Phase 4, plan 04-03: SCL-02
to SCL-05) at the study level against the fake psspy: every city is studied on its own freshly
loaded copy of the case, scaled to that city's targets with the job's own whole-case scal_2 call
before its rating is written and its load flow solved.

Follows backend/tests/psse_study_test.py's conventions (module-level imports, plain asserts, no
test classes, no network). Honest scope: the fake proves call order, isolation between copies and
failure handling, not how real PSS/E reads the scaling arguments or whether reloading undoes a
scaling; plan 04-06 checks that on the laptop.

Only synthetic targets appear here (plan 04-01's table, the same ones as the committed example
mapping); no real city figure belongs in a public repository.
"""

import collections
import copy
import datetime
import itertools
import json
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
import psse_fakes  # noqa: E402
from psse_job import (  # noqa: E402
    constants, contingency, contract, mapping, ratings, run_record, study, violations,
)

EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
NOW = datetime.datetime(2026, 10, 28, 12, 20, 0, tzinfo=datetime.timezone.utc)

# city -> (load_mw, gen_mw), basis "average": plan 04-01's synthetic table.
TARGETS = {
    "AUSTIN": (2430.5, 2467.25),
    "CORPUS_CHRISTI": (2455.75, 2492.5),
    "MIDLAND": (2504.25, 2541.75),
    "EL_PASO": (2529.5, 2566.25),
}
MAPPED_LINE = {
    "AUSTIN": (90001, 90002, "1"),
    "CORPUS_CHRISTI": (90011, 90012, "1"),
    "MIDLAND": (90021, 90022, "1"),
    "EL_PASO": (90031, 90032, "1"),
}


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _registered(tmp_path, case=None, solver=None, fake=None):
    """(fake, case path): the case registered under a path whose file holds a marker."""
    fake = fake_module.FakePsspy(solver=solver) if fake is None else fake
    path = str(tmp_path / "PLACEHOLDER_CASE.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(path, fake_module.placeholder_case() if case is None else case)
    return fake, path


def _mapping(cities=None, **changes):
    """The example mapping (placeholder allowed); `cities` maps a city to CityMapping field
    replacements and `changes` replace study settings."""
    loaded = mapping.load_mapping(EXAMPLE, allow_placeholder=True)
    table = dict(loaded.cities)
    for city, fields in (cities or {}).items():
        table[city] = table[city]._replace(**fields)
    return loaded._replace(cities=table, settings=loaded.settings._replace(**changes))


def _selection(provisional=True):
    rows = psse_fakes.latest_rows(NOW, provisional=provisional)
    return ratings.select_ratings(psse_fakes.fake_fetch(rows), NOW)


def _same_file(left, right):
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def _case_loads(fake, path):
    """The recorded case() calls that load Power Systems' case file itself."""
    return [call for call in fake.fake_calls if call[0] == "case" and _same_file(call[1][0], path)]


def _city_blocks(fake, path):
    """The recorded calls after the indexing load, one list per city: each starts at a load of
    Power Systems' case file and runs to the next one (or the end)."""
    positions = [position for position, call in enumerate(fake.fake_calls)
                 if call[0] == "case" and _same_file(call[1][0], path)]
    ends = positions[1:] + [len(fake.fake_calls)]
    return [fake.fake_calls[start:end] for start, end in list(zip(positions, ends))[1:]]


def _expected_outage_counts(path, mapping_=None):
    """city -> how many in-service branch outages that city's own study area selects, worked
    out from the index and the study area alone (no screen is run)."""
    mapping_ = _mapping() if mapping_ is None else mapping_
    reference = fake_module.FakePsspy()
    reference.fake_register_case(path, fake_module.placeholder_case())
    index = study.index_case(reference, path, mapping_)
    in_service = set(row.key for row in index.lines if row.in_service)
    assert not mapping_.settings.contingency_extra
    counts = {}
    for city in constants.CITIES:
        area = study.study_area(
            index.lines, index.buses, {city: index.resolved[city]}, mapping_.settings,
            {city: mapping_.cities[city].sink_buses})
        counts[city] = len(area.branch_keys & in_service)
    return counts


def test_tracer_four_cities_each_on_its_own_scaled_copy(tmp_path):
    fake, path = _registered(tmp_path)
    sha_before = run_record.file_sha256(path)
    selection = _selection()
    prepared = study.prepare_run(fake, path, EXAMPLE, allow_placeholder=True)
    results = prepared.study(selection, None)

    run_record.validate_results(results, selection)
    assert [row["city"] for row in results.dispatch] == list(constants.CITIES)
    assert [row["city"] for row in results.margins] == list(constants.CITIES)
    prefixes = tuple(city + ":" for city in constants.CITIES)
    assert results.contingencies
    assert all(row["contingency_id"].startswith(prefixes) for row in results.contingencies)
    assert os.listdir(tempfile.gettempdir()) == []

    reference = fake_module.FakePsspy()
    reference.fake_register_case(path, fake_module.placeholder_case())
    index = study.index_case(reference, path, _mapping())
    case_keys = set(row.key for row in index.lines)
    for row in results.contingencies:
        city, _, key = row["contingency_id"].partition(":")
        assert city in constants.CITIES
        assert key in case_keys
    counts = _expected_outage_counts(path)
    assert results.n_contingencies == sum(counts.values())

    # four fresh loads after the one indexing load, each city's block in the planned order
    assert len(_case_loads(fake, path)) == 5
    blocks = _city_blocks(fake, path)
    assert len(blocks) == len(constants.CITIES)
    for city, block in zip(constants.CITIES, blocks):
        assert block[0][0] == "case" and _same_file(block[0][1][0], path)
        upto_save = []
        for call in block:
            upto_save.append(call)
            if call[0] == "save":
                break
        assert upto_save[-1][0] == "save"
        writes = [call for call in upto_save if call[0] in ("scal_2", "branch_chng_3", "fnsl", "save")]
        names = [call[0] for call in writes]
        assert names[:3] == ["scal_2", "scal_2", "scal_2"], city
        assert names[-2:] == ["fnsl", "save"], city
        middle = names[3:-2]
        assert middle and set(middle) == {"branch_chng_3"}, city
        assert [call[2]["apiopt"] for call in writes[:3]] == [1, 0, 1], city
        assert all(call[2]["all"] == 1 for call in writes[:3]), city
        scale = writes[1][2]
        assert scale["scalval"][:2] == list(TARGETS[city]), city
        line = MAPPED_LINE[city]
        for call in writes[3:-2]:
            assert (call[2]["ibus"], call[2]["jbus"], call[2]["ckt"]) == line, city
        saved = writes[-1][1][0]
        assert os.path.basename(saved) == city + ".sav"
    directories = set(os.path.dirname(os.path.abspath(saved)) for saved in fake.fake_saved_paths
                      if os.path.basename(saved) in [city + ".sav" for city in constants.CITIES])
    assert len(directories) == 1
    assert not any(os.path.exists(saved) for saved in fake.fake_saved_paths)
    assert run_record.file_sha256(path) == sha_before

    expected = {"basis": "average", "method": study.SCALING_METHOD}
    for row in results.dispatch + results.margins:
        assert row["details"]["scaling"] == expected


# ──────────────────────────────────────────────────────────────────────────────
# Isolation between the four copies, and a scaling that fails stops that city
# ──────────────────────────────────────────────────────────────────────────────


class _ScaleIgnored(fake_module.FakePsspy):
    """A psspy whose whole-case scaling call reports success and changes nothing."""

    def scal_2(self, sid, all, apiopt, status, scalval):  # noqa: A002 - the manual's name
        if all == 1 and apiopt == 0:
            before = copy.deepcopy(self.fake_state)
            result = super().scal_2(sid, all, apiopt, status, scalval)
            self.fake_state = before
            return result
        return super().scal_2(sid, all, apiopt, status, scalval)


class _ScaleRefused(fake_module.FakePsspy):
    """A psspy whose whole-case scaling call returns an error code and changes nothing."""

    def scal_2(self, sid, all, apiopt, status, scalval):  # noqa: A002 - the manual's name
        if all == 1 and apiopt == 0:
            self.fake_calls.append(("scal_2", (), dict(
                sid=sid, all=all, apiopt=apiopt, status=status, scalval=scalval)))
            return (6, [], [])
        return super().scal_2(sid, all, apiopt, status, scalval)


def _figure_texts():
    """Every text form of the eight synthetic targets (repr, %g and %.1f)."""
    texts = set()
    for pair in TARGETS.values():
        for value in pair:
            texts.update((repr(value), "%g" % value, "%.1f" % value))
    return sorted(texts)


def _assert_no_figure(message):
    for text in _figure_texts():
        assert text not in message, text


def _study_failure(tmp_path, stage, case=None, solver=None, fake=None, mapping_=None):
    """Run the whole study expecting StudyFailed at `stage`; returns (fake, case path, failure)."""
    fake, path = _registered(tmp_path, case=case, solver=solver, fake=fake)
    callable_ = study.make_study(fake, path, _mapping() if mapping_ is None else mapping_)
    with pytest.raises(contract.StudyFailed) as caught:
        callable_(_selection(), None)
    assert caught.value.stage == stage
    return fake, path, caught.value


def _scale_calls(fake, apiopt):
    return [call for call in fake.fake_calls
            if call[0] == "scal_2" and call[2].get("all") == 1 and call[2].get("apiopt") == apiopt]


def test_independent_each_solve_sees_only_its_own_city(tmp_path):
    placeholder = fake_module.placeholder_case()
    own_rate = dict((line, placeholder.branch(*line)["rates"][0]) for line in MAPPED_LINE.values())
    records = []

    def watching(case):
        rerated = frozenset(
            "%d-%d-%s" % line for line in MAPPED_LINE.values()
            if case.branch(*line)["rates"][0] != own_rate[line])
        records.append((sum(case.gens.values()), rerated))
        return fake_module.radial_solver(case)

    fake, path = _registered(tmp_path, solver=watching)
    sha_before = run_record.file_sha256(path)
    study.make_study(fake, path, _mapping())(_selection(), None)

    blocks = [(key, len(list(group))) for key, group in itertools.groupby(records)]
    assert len(blocks) == len(constants.CITIES)
    for city, ((gen_total, rerated), _) in zip(constants.CITIES, blocks):
        assert gen_total == pytest.approx(TARGETS[city][1], rel=1e-9), city
        assert rerated == frozenset(["%d-%d-%s" % MAPPED_LINE[city]]), city
    assert len(_case_loads(fake, path)) == 5
    assert not any(_same_file(saved, path) for saved in fake.fake_saved_paths)
    assert run_record.file_sha256(path) == sha_before


def test_readback_miss_fails_city_at_apply_ratings(tmp_path):
    fake, _, failure = _study_failure(tmp_path, "apply_ratings", fake=_ScaleIgnored())
    assert failure.message.startswith("scaling: AUSTIN")
    assert "load" in failure.message
    assert not [call for call in fake.fake_calls if call[0] == "fnsl"]
    assert os.listdir(tempfile.gettempdir()) == []
    _assert_no_figure(failure.message)


def test_scale_error_fails_city_at_apply_ratings(tmp_path):
    fake, _, failure = _study_failure(tmp_path, "apply_ratings", fake=_ScaleRefused())
    assert failure.message.startswith("scaling: AUSTIN")
    assert "scal_2" in failure.message
    assert not [call for call in fake.fake_calls if call[0] == "fnsl"]
    assert os.listdir(tempfile.gettempdir()) == []
    _assert_no_figure(failure.message)


def test_factor_bound_catches_a_kilowatt_typo(tmp_path):
    typo = mapping.Scaling(2430500.0, TARGETS["AUSTIN"][1], "average")
    fake, _, failure = _study_failure(
        tmp_path, "apply_ratings", mapping_=_mapping(cities={"AUSTIN": {"scaling": typo}}))
    assert failure.message.startswith("scaling: AUSTIN")
    assert "outside" in failure.message
    assert not _scale_calls(fake, 0)
    assert "2430500" not in failure.message
    _assert_no_figure(failure.message)


def test_case_without_generation_is_refused(tmp_path):
    case = fake_module.placeholder_case()
    case.gens = {}
    fake, _, failure = _study_failure(tmp_path, "apply_ratings", case=case)
    assert "no generation to scale" in failure.message
    assert failure.message.startswith("scaling: AUSTIN")
    assert not _scale_calls(fake, 0)
    _assert_no_figure(failure.message)


def test_scaled_case_not_converging_is_load_flow(tmp_path):
    def solver(case):
        if sum(case.gens.values()) == pytest.approx(TARGETS["MIDLAND"][1], rel=1e-9):
            return fake_module.SolveOutcome(ierr=3, solved=None, iterations=0, mismatch=0.0)
        return fake_module.radial_solver(case)

    fake, _, failure = _study_failure(tmp_path, "load_flow", solver=solver)
    saved = [os.path.basename(path) for path in fake.fake_saved_paths]
    assert saved == ["AUSTIN.sav", "CORPUS_CHRISTI.sav"]
    assert os.listdir(tempfile.gettempdir()) == []
    _assert_no_figure(failure.message)


def test_basis_label_reaches_details(tmp_path):
    peak = mapping.Scaling(TARGETS["MIDLAND"][0], TARGETS["MIDLAND"][1], "peak")
    fake, path = _registered(tmp_path)
    results = study.make_study(fake, path, _mapping(cities={"MIDLAND": {"scaling": peak}}))(
        _selection(), None)
    for rows in (results.dispatch, results.margins):
        for city, row in zip(constants.CITIES, rows):
            assert row["city"] == city
            expected = "peak" if city == "MIDLAND" else "average"
            assert row["details"]["scaling"] == {"basis": expected, "method": study.SCALING_METHOD}


def test_run_wide_row_cap(tmp_path, monkeypatch):
    fake, path = _registered(tmp_path)
    first = study.make_study(fake, path, _mapping())(_selection(), None)
    counts = collections.Counter(
        row["contingency_id"].partition(":")[0] for row in first.contingencies)
    cap = max(counts.values())
    assert cap < sum(counts.values())
    monkeypatch.setattr(run_record, "MAX_CONTINGENCY_ROWS", cap)
    _, _, failure = _study_failure(tmp_path, "contingency")
    assert "across the four cities" in failure.message
    assert os.listdir(tempfile.gettempdir()) == []


def test_screen_prefixes_the_id_but_skips_the_outaged_line_by_its_raw_key(tmp_path, monkeypatch):
    seen = []
    real = violations.thermal_violations

    def spy(flows, monitored_keys, settings_, contingency_id, city_of_branch, base_flows_by_key,
            skip_key=None):
        seen.append((contingency_id, skip_key))
        return real(flows, monitored_keys, settings_, contingency_id, city_of_branch,
                    base_flows_by_key, skip_key=skip_key)

    monkeypatch.setattr(violations, "thermal_violations", spy)
    fake, path = _registered(tmp_path)
    base = study.prepare_base(fake, path, _mapping(), _selection())
    try:
        screened = contingency.screen(base, id_prefix="AUSTIN:")
    finally:
        study.cleanup_base(base)
    assert seen
    for contingency_id, skip_key in seen:
        assert contingency_id == "AUSTIN:" + skip_key
    assert all(row["contingency_id"].startswith("AUSTIN:") for row in screened.rows)


def _shared_line_mapping(tmp_path):
    """A copy of the example in which CORPUS_CHRISTI maps AUSTIN's line and sink bus."""
    with open(EXAMPLE, encoding="utf-8") as handle:
        raw = json.load(handle)
    raw["cities"]["CORPUS_CHRISTI"]["branches"] = list(raw["cities"]["AUSTIN"]["branches"])
    raw["cities"]["CORPUS_CHRISTI"]["sink_buses"] = list(raw["cities"]["AUSTIN"]["sink_buses"])
    path = str(tmp_path / "shared_line_mapping.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(raw, handle)
    return path


def _context():
    return contract.RunContext(
        run_id="psse-20261028T122000Z-00000001", started_at=NOW, case_id="PLACEHOLDER_CASE.sav",
        case_sha256="ab" * 32, mapping_sha256="cd" * 32, job_version="abc1234")


def test_rows_same_line_in_two_cities_unique_and_attributable(tmp_path):
    fake, path = _registered(tmp_path)
    selection = _selection()
    prepared = study.prepare_run(fake, path, _shared_line_mapping(tmp_path), allow_placeholder=True)
    results = prepared.study(selection, None)
    run_record.validate_results(results, selection)

    ids = [row["contingency_id"] for row in results.contingencies]
    by_city = dict((city, set(item.partition(":")[2] for item in ids if item.startswith(city + ":")))
                   for city in ("AUSTIN", "CORPUS_CHRISTI"))
    shared = by_city["AUSTIN"] & by_city["CORPUS_CHRISTI"]
    assert shared
    for key in shared:
        assert "AUSTIN:" + key in ids
        assert "CORPUS_CHRISTI:" + key in ids
    keys = [(row["contingency_id"], row["violation_kind"], row["element_id"])
            for row in results.contingencies]
    assert len(set(keys)) == len(keys)

    record = run_record.build_run_record(
        _context(), selection, NOW + datetime.timedelta(minutes=1), results=results)
    assert record["n_contingencies_with_results"] == len(set(ids))
    assert record["n_contingencies"] == results.n_contingencies


def test_rows_and_record_hold_no_target_figure(tmp_path):
    fake, path = _registered(tmp_path)
    selection = _selection()
    results = study.prepare_run(fake, path, EXAMPLE, allow_placeholder=True).study(selection, None)
    record = run_record.build_run_record(
        _context(), selection, NOW + datetime.timedelta(minutes=1), results=results)
    rows = run_record.result_rows(record, results)
    assert rows
    text = json.dumps([rows, record], sort_keys=True, default=str)
    for figure in _figure_texts():
        assert figure not in text, figure
    for row in results.dispatch + results.margins:
        assert sorted(row["details"]["scaling"]) == ["basis", "method"]


def test_apply_ratings_one_city_view(tmp_path):
    fake, path = _registered(tmp_path)
    mapping_ = _mapping()
    index = study.index_case(fake, path, mapping_)
    before = len(fake.fake_calls)
    applied = study.apply_ratings(
        index.api, {"MIDLAND": index.resolved["MIDLAND"]}, mapping_, _selection(),
        cities=("MIDLAND",))
    assert isinstance(applied, collections.OrderedDict)
    assert list(applied) == ["MIDLAND"]
    changes = [call for call in fake.fake_calls[before:] if call[0] == "branch_chng_3"]
    assert changes
    assert all((call[2]["ibus"], call[2]["jbus"], call[2]["ckt"]) == MAPPED_LINE["MIDLAND"]
               for call in changes)
