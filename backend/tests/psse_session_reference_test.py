"""
PSE-03 proofs of the reference section of the laptop session (pandapower-solver Phase 1, plan
01-03) on a fake psspy: `psse_session.reference.run` driven through `session.main` with the
sections narrowed to network and reference, reading the zip it leaves.

Honest scope: the fake (backend/tests/psse_session_fake.py) proves call order and bookkeeping, not
PSS/E's numbers. That real PSS/E 36.4 answers the extended reads (all-branch P, Q and MAXMVA, the
machine reads) and the RAW snapshots as the fake does is UNVERIFIED until the session of plan
01-10. Every test uses the committed 9xxxx placeholder series and the committed placeholder
mapping; nothing here holds a real bus number, path or name. Scenario solvers and patched job
functions live in this file. Plain asserts, no classes of tests, no network.
"""

import json
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_session_fake  # noqa: E402
from psse_fake_psspy import SWING_BUS, SolveOutcome, placeholder_case, radial_solver  # noqa: E402
from psse_job import constants, contingency, psse_api, ratings, study  # noqa: E402
from psse_job import mapping as mapping_module  # noqa: E402
from psse_session import bundle, reference, session  # noqa: E402
from psse_session_test import (  # noqa: E402
    EXAMPLE_MAPPING, FIXED_NOW, STAMP, World, _read_zip, _run, _summary_lines_match)


def _narrow(monkeypatch, cities):
    """Run only the network and reference sections, and only for `cities` in the reference."""
    monkeypatch.setattr(session, "SECTIONS", ("network", "reference"))
    monkeypatch.setattr(reference, "constants", types.SimpleNamespace(CITIES=tuple(cities)))


def _reference_run(tmp_path, monkeypatch, cities=("AUSTIN",), world=None, **fake_options):
    """(world, code, out, err, manifest, members) of a session limited to network and reference."""
    _narrow(monkeypatch, cities)
    world = World(tmp_path, **fake_options) if world is None else world
    code, out, err = _run(world, monkeypatch)
    manifest, members = _read_zip(world.zip_path())
    return world, code, out, err, manifest, members


def _json(members, name):
    return json.loads(members[name].decode("ascii"))


def _section(manifest, name):
    return dict((item["name"], item) for item in manifest["sections"])[name]


def _independent_base(tmp_path, case_path, city, solver=None):
    """The job's own prepare_city_base for `city` on a second fake with the same case and mapping."""
    fake = psse_session_fake.FakeSessionPsspy(solver=solver)
    fake.fake_register_case(str(case_path), placeholder_case())
    loaded = mapping_module.load_mapping(EXAMPLE_MAPPING, allow_placeholder=True)
    index = study.index_case(fake, str(case_path), loaded)
    selection = ratings.select_ratings(lambda: [], FIXED_NOW)
    folder = tmp_path / ("independent_" + city.lower())
    folder.mkdir()
    base = study.prepare_city_base(
        index, loaded, selection, city, study.Budget(max_seconds=1.0e9), str(folder))
    return base


def island_when_tie_two_is_out(case):
    """The radial solver, except that tripping the second tie of the first source islands it."""
    tie = case.branches.get((SWING_BUS, 90001, "2"))
    if tie is not None and tie["status"] != 1:
        return SolveOutcome(ierr=3, solved=None, iterations=0, mismatch=0.0)
    return radial_solver(case)


def test_tracer_reference_one_city_base_outages_and_margin_in_the_zip(tmp_path, monkeypatch):
    """PSE-03 on the fake: one city's pre-solve snapshot, solved base, outages and margin point reach the zip."""
    world, code, out, err, manifest, members = _reference_run(tmp_path, monkeypatch)
    assert code == 0, out + err
    prefix = "reference/austin/"
    for name in ("presolve.raw", "solved.raw", "base.json", "outages.json", "margin.json",
                 "margin_last_good.raw"):
        assert prefix + name in members, name
        assert members[prefix + name], name
    for name in ("presolve.raw", "solved.raw", "margin_last_good.raw"):
        assert session._header_revision(members[prefix + name]) == 33
    base = _json(members, prefix + "base.json")
    assert base["city"] == "AUSTIN" and base["rating_source"] == "static"
    assert base["snapshot"] == prefix + "solved.raw" and base["solve"]["converged"] is True
    assert base["branch_flows"]["status"] == "ok" and base["machine_outputs"]["status"] == "ok"
    assert base["branch_flows"]["rows"] and base["machine_outputs"]["rows"]
    assert bundle.MEMBER_MARKER in base
    outages = _json(members, prefix + "outages.json")
    assert outages["status"] == "ok" and outages["count"] == len(outages["outages"]) > 0
    assert [record["position"] for record in outages["outages"]] == list(range(outages["count"]))
    for record in outages["outages"]:
        member = "%soutage_%03d.raw" % (prefix, record["position"])
        assert (member in members) == record["converged"], member
        assert record["snapshot"] == (member if record["converged"] else None)
    margin_json = _json(members, prefix + "margin.json")
    assert margin_json["status"] == "ok" and margin_json["details"]["sink_buses"]
    assert margin_json["last_good"]["snapshot"] == prefix + "margin_last_good.raw"
    assert margin_json["last_good"]["increment_mw"] == margin_json["details"]["increment_mw"]
    # a city that ends on the voltage criterion has a first bad point; its solve is on record
    assert margin_json["details"]["first_bad_mw"] is not None
    assert margin_json["first_bad"]["increment_mw"] == margin_json["details"]["first_bad_mw"]
    assert margin_json["first_bad"]["solve"] is not None
    # no copy of the case enters the zip, and the section is ok with integer counts only
    assert not [name for name in members if name.endswith(".sav")]
    section = _section(manifest, "reference")
    assert section["status"] == "ok" and section["detail"] == []
    assert section["counts"]["cities"] == 1 and section["counts"]["cities_ok"] == 1
    assert section["counts"]["outages"] == outages["count"]
    _summary_lines_match(out)
    # the extended reads went through the call gate to the fake
    names = [name for name, _args, _kwargs in world.fake.fake_calls]
    assert "amachreal" in names and "abrnreal" in names


def test_outage_list_equals_the_jobs_own_selection(tmp_path, monkeypatch):
    """T-01-10: the keys and order in outages.json are contingency.select_outages(base) on an independent run."""
    world, code, out, err, manifest, members = _reference_run(tmp_path, monkeypatch)
    assert code == 0, out + err
    prefix = "reference/austin/"
    independent = _independent_base(tmp_path, world.case, "AUSTIN")
    try:
        expected = [ref.key for ref in contingency.select_outages(independent)]
        outages = _json(members, prefix + "outages.json")
        assert [record["key"] for record in outages["outages"]] == expected
        assert len(set(expected)) == len(expected)
        # the base answer is the job's own base answer
        base = _json(members, prefix + "base.json")
        assert [(row["number"], row["pu"]) for row in base["buses"]] == [
            (number, independent.base_buses[number].pu) for number in sorted(independent.base_buses)]
        assert [(row["key"], row["pct"], row["p_mw"], row["max_mva"], row["rate_mva"])
                for row in base["line_flows"]] == [
            (flow.key, flow.pct, flow.p_mw, flow.max_mva, flow.rate_mva)
            for flow in independent.base_flows]
        assert base["rate_set"] == independent.settings.rate_sets[0]
        assert base["thermal_basis"] == independent.settings.thermal_basis
        assert base["solve"]["converged"] is True
    finally:
        study.cleanup_base(independent)


def test_islanded_outage_is_recorded_not_dropped(tmp_path, monkeypatch):
    """T-01-12: an islanded outage is a record with ierr 3 and null states; the others are converged."""
    world = World(tmp_path, solver=island_when_tie_two_is_out)
    world, code, out, err, manifest, members = _reference_run(tmp_path, monkeypatch, world=world)
    assert code == 0, out + err
    prefix = "reference/austin/"
    outages = _json(members, prefix + "outages.json")
    by_key = dict((record["key"], record) for record in outages["outages"])
    islanded = by_key["90000-90001-2"]
    assert islanded["converged"] is False and islanded["ierr"] == 3
    # solved() describes an older attempt after a failed fnsl; the record keeps it and the meaning
    # says it is not trusted
    assert psse_api.FNSL_ERRORS[3] in islanded["meaning"] and "not trusted" in islanded["meaning"]
    assert islanded["solve"]["converged"] is False and islanded["call_failed"] is None
    for field in ("buses", "line_flows", "branch_flows", "machine_outputs", "snapshot"):
        assert islanded[field] is None, field
    assert "%soutage_%03d.raw" % (prefix, islanded["position"]) not in members
    others = [record for record in outages["outages"] if record is not islanded]
    assert others and all(record["converged"] for record in others)
    assert all(record["buses"] and record["snapshot"] in members for record in others)
    section = _section(manifest, "reference")
    assert section["counts"]["outages"] == outages["count"]
    assert section["counts"]["not_converged"] == 1
    assert section["counts"]["converged"] == outages["count"] - 1


# ──────────────────────────────────────────────────────────────────────────────
# All four cities, the edges, isolation, refusals, cleanup and the counts
# ──────────────────────────────────────────────────────────────────────────────

FAKE_LEAK_BRANCH = "90021-90022-9"
CITY_MEMBERS = ("presolve.raw", "solved.raw", "base.json", "outages.json", "margin.json",
                "margin_last_good.raw")


def _capture_results(monkeypatch):
    """A list that receives ctx.results["reference"] when the reference section returns."""
    captured = []
    original = session.SECTION_FUNCTIONS["reference"]

    def wrapper(ctx):
        result = original(ctx)
        captured.append(ctx.results["reference"])
        return result

    monkeypatch.setitem(session.SECTION_FUNCTIONS, "reference", wrapper)
    return captured


def _all_bytes(manifest, members, out, err):
    manifest_bytes = json.dumps(manifest).encode("ascii")
    return b"".join(list(members.values()) + [manifest_bytes, out.encode("ascii"),
                                              err.encode("ascii")])


class RefusesTheAllBranchRead(psse_session_fake.FakeSessionPsspy):
    """The fake, except that the all-branch P, Q and MAXMVA read (abrn flag 4) is refused with ierr 1."""

    def abrnreal(self, sid, owner, ties, flag, entry, string):
        if flag == 4 and "Q" in string:
            self.fake_calls.append(("abrnreal", (), {"flag": flag, "string": list(string)}))
            return (1, [])
        return psse_session_fake.FakeSessionPsspy.abrnreal(
            self, sid, owner, ties, flag, entry, string)


def test_four_cities_in_order_with_integer_summary_counts(tmp_path, monkeypatch):
    """PSE-03: members for all four cities, cities in CITIES order, counts are integers only."""
    order = []
    original = reference._run_city

    def recorder(ctx, reader, tally, tmp_root, city):
        order.append(city)
        return original(ctx, reader, tally, tmp_root, city)

    monkeypatch.setattr(reference, "_run_city", recorder)
    captured = _capture_results(monkeypatch)
    world, code, out, err, manifest, members = _reference_run(
        tmp_path, monkeypatch, cities=constants.CITIES)
    assert code == 0, out + err
    assert order == list(constants.CITIES)
    assert list(captured[0]) == list(constants.CITIES)
    expected_outages = expected_converged = expected_margin_points = 0
    for city in constants.CITIES:
        prefix = "reference/%s/" % city.lower()
        for name in CITY_MEMBERS:
            assert prefix + name in members, prefix + name
        outages = _json(members, prefix + "outages.json")
        expected_outages += outages["count"]
        expected_converged += sum(1 for record in outages["outages"] if record["converged"])
        margin_json = _json(members, prefix + "margin.json")
        points = [margin_json[name] for name in ("last_good", "first_bad") if margin_json[name]]
        expected_margin_points += len(points)
        assert captured[0][city]["status"] == "ok"
        assert captured[0][city]["sink_buses"] == margin_json["details"]["sink_buses"]
        assert captured[0][city]["margin_increments"] == (
            margin_json["details"]["increment_mw"], margin_json["details"]["first_bad_mw"])
    # EL_PASO of the placeholder case is bounded by the rating, so it has no first bad point
    assert _json(members, "reference/el_paso/margin.json")["first_bad"] is None
    assert not os.path.exists(str(world.out / "tmp_sav"))
    section = _section(manifest, "reference")
    assert section["status"] == "ok" and section["detail"] == []
    assert section["counts"] == {
        "cities": 4, "cities_ok": 4, "outages": expected_outages,
        "converged": expected_converged, "not_converged": expected_outages - expected_converged,
        "margin_points": expected_margin_points, "extended_reads_unavailable": 0}
    assert all(type(value) is int for value in section["counts"].values())
    line = [text for text in out.splitlines() if text.startswith("section reference counts:")]
    assert line == ["section reference counts: cities 4 cities_ok 4 converged %d "
                    "extended_reads_unavailable 0 margin_points %d not_converged %d outages %d" % (
                        expected_converged, expected_margin_points,
                        expected_outages - expected_converged, expected_outages)]
    _summary_lines_match(out)


def test_parallel_circuits_are_separate_records(tmp_path, monkeypatch):
    """Edge PSE-03 adjacency: both circuits between one pair of buses are two records, no key repeats."""
    world, code, out, err, manifest, members = _reference_run(
        tmp_path, monkeypatch, cities=constants.CITIES)
    assert code == 0, out + err
    pairs = {"austin": "90001-90002", "corpus_christi": "90011-90012", "midland": "90021-90022",
             "el_paso": "90031-90032"}
    for city in constants.CITIES:
        outages = _json(members, "reference/%s/outages.json" % city.lower())
        keys = [record["key"] for record in outages["outages"]]
        assert len(set(keys)) == len(keys), city
        pair = pairs[city.lower()]
        parallel = [key for key in keys if key.startswith(pair + "-")]
        assert parallel == [pair + "-1", pair + "-2"], city
        by_key = dict((record["key"], record) for record in outages["outages"])
        first, second = by_key[pair + "-1"], by_key[pair + "-2"]
        assert (first["from_bus"], first["to_bus"]) == (second["from_bus"], second["to_bus"])
        assert (first["ckt"], second["ckt"]) == ("1", "2")
        assert first["position"] != second["position"]


def test_none_selected_is_written_as_an_empty_list(tmp_path, monkeypatch):
    """Edge PSE-03 empty: select_outages refusing for nothing selected gives an empty list, the base stays."""
    original = contingency.select_outages

    def select(base):
        if "MIDLAND" in base.cities:
            raise study.StudyFailed("contingency", "no branch outage was selected; a screen that "
                                                   "screens nothing is not a result")
        return original(base)

    monkeypatch.setattr(contingency, "select_outages", select)
    world, code, out, err, manifest, members = _reference_run(
        tmp_path, monkeypatch, cities=constants.CITIES)
    assert code == 0, out + err
    empty = _json(members, "reference/midland/outages.json")
    assert (empty["status"], empty["count"], empty["outages"]) == ("none_selected", 0, [])
    base = _json(members, "reference/midland/base.json")
    assert base["status"] == "ok" and base["solve"]["converged"] is True
    assert "reference/midland/solved.raw" in members
    for city in ("austin", "corpus_christi", "el_paso"):
        other = _json(members, "reference/%s/outages.json" % city)
        assert other["status"] == "ok" and other["count"] > 0
    section = _section(manifest, "reference")
    assert section["status"] == "ok" and section["detail"] == ["none selected"]
    assert section["counts"]["cities_ok"] == 4
    assert "section reference detail: none selected" in out
    _summary_lines_match(out)

    # more outages than contingency.max is a failure of the city, not an empty list
    def too_many(base):
        if "MIDLAND" in base.cities:
            raise study.StudyFailed("contingency", "11 branch outages exceed contingency.max 10")
        return original(base)

    monkeypatch.setattr(contingency, "select_outages", too_many)
    other_folder = tmp_path / "second"
    other_folder.mkdir()
    world, code, out, err, manifest, members = _reference_run(
        other_folder, monkeypatch, cities=constants.CITIES)
    assert code == 1
    assert _json(members, "reference/midland/outages.json")["status"] == "failed"
    assert "reference/midland/margin.json" not in members
    section = _section(manifest, "reference")
    assert section["status"] == "failed" and section["detail"] == ["contingency"]


def test_members_are_sorted_inside(tmp_path, monkeypatch):
    """Edge PSE-03 ordering: buses by number, flows by key, outages in list order, in every member."""
    world, code, out, err, manifest, members = _reference_run(
        tmp_path, monkeypatch, cities=constants.CITIES)
    assert code == 0, out + err

    def check(state, label):
        numbers = [row["number"] for row in state["buses"]]
        assert numbers == sorted(numbers) and len(set(numbers)) == len(numbers), label
        keys = [row["key"] for row in state["line_flows"]]
        assert keys == sorted(keys) and len(set(keys)) == len(keys), label
        keys = [row["key"] for row in state["branch_flows"]["rows"]]
        assert keys == sorted(keys) and len(set(keys)) == len(keys), label
        machines = [(row["bus"], row["id"]) for row in state["machine_outputs"]["rows"]]
        assert machines == sorted(machines), label

    for city in constants.CITIES:
        prefix = "reference/%s/" % city.lower()
        check(_json(members, prefix + "base.json"), prefix + "base")
        outages = _json(members, prefix + "outages.json")
        assert [record["position"] for record in outages["outages"]] == list(range(outages["count"]))
        keys = [record["key"] for record in outages["outages"]]
        assert keys == sorted(keys)
        for record in outages["outages"]:
            if record["converged"]:
                check(record, prefix + record["key"])
        margin_json = _json(members, prefix + "margin.json")
        for name in ("last_good", "first_bad"):
            if margin_json[name] is not None and margin_json[name]["buses"] is not None:
                check(margin_json[name], prefix + name)
    # the extended branch read covers lines and transformers alike and marks transformers by key
    base = _json(members, "reference/austin/base.json")
    assert len(base["branch_flows"]["rows"]) == len(base["line_flows"])
    assert not any(row["is_transformer"] for row in base["branch_flows"]["rows"])


def test_a_failing_city_is_isolated_and_named_by_stage_only(tmp_path, monkeypatch):
    """T-01-13: a failed preparation is recorded by stage only, the other cities still run, exit 1."""
    original = study.prepare_city_base

    def prepare(index, mapping, selection, city, budget, temp_dir):
        if city == "MIDLAND":
            raise study.StudyFailed("apply_ratings", "branch %s could not be rated" % FAKE_LEAK_BRANCH)
        return original(index, mapping, selection, city, budget, temp_dir)

    monkeypatch.setattr(study, "prepare_city_base", prepare)
    captured = _capture_results(monkeypatch)
    world, code, out, err, manifest, members = _reference_run(
        tmp_path, monkeypatch, cities=constants.CITIES)
    assert code == 1, out + err
    results = captured[0]
    assert results["MIDLAND"]["status"] == "failed" and results["MIDLAND"]["detail"] == ("apply_ratings",)
    assert [city for city in constants.CITIES if results[city]["status"] == "ok"] == [
        "AUSTIN", "CORPUS_CHRISTI", "EL_PASO"]
    failed_base = _json(members, "reference/midland/base.json")
    assert failed_base["status"] == "failed" and failed_base["failed_stage"] == "apply_ratings"
    assert "solve" not in failed_base
    assert "reference/midland/outages.json" not in members
    for city in ("austin", "corpus_christi", "el_paso"):
        for name in CITY_MEMBERS:
            assert "reference/%s/%s" % (city, name) in members
    section = _section(manifest, "reference")
    assert section["status"] == "failed" and section["detail"] == ["apply_ratings"]
    assert section["counts"]["cities"] == 4 and section["counts"]["cities_ok"] == 3
    assert "section reference: failed" in out and "section reference detail: apply_ratings" in out
    _summary_lines_match(out)
    assert FAKE_LEAK_BRANCH.encode("ascii") not in _all_bytes(manifest, members, out, err)

    # a failure that is not a StudyFailed is named by its class
    def explode(index, mapping, selection, city, budget, temp_dir):
        raise KeyError(FAKE_LEAK_BRANCH)

    monkeypatch.setattr(study, "prepare_city_base", explode)
    other_folder = tmp_path / "second"
    other_folder.mkdir()
    captured[:] = []
    world, code, out, err, manifest, members = _reference_run(
        other_folder, monkeypatch, cities=("AUSTIN",))
    assert code == 1
    assert captured[0]["AUSTIN"]["detail"] == ("KeyError",)
    assert _section(manifest, "reference")["detail"] == ["KeyError"]
    assert FAKE_LEAK_BRANCH.encode("ascii") not in _all_bytes(manifest, members, out, err)


def _solved_states(members, prefix):
    """Every solved state of one city: the base, the converged outages and the margin points."""
    states = [_json(members, prefix + "base.json")]
    states += [record for record in _json(members, prefix + "outages.json")["outages"]
               if record["converged"]]
    margin_json = _json(members, prefix + "margin.json")
    states += [margin_json[name] for name in ("last_good", "first_bad")
               if margin_json[name] and margin_json[name]["buses"] is not None]
    return states


def test_extended_read_refusals_are_recorded_as_unavailable(tmp_path, monkeypatch):
    """An extended read the engine refuses is status unavailable with function and class, never missing."""
    world, code, out, err, manifest, members = _reference_run(
        tmp_path, monkeypatch, fail={"amachreal": "raise"})
    assert code == 0, out + err
    prefix = "reference/austin/"
    states = _solved_states(members, prefix)
    assert len(states) > 3
    for state in states:
        machines = state["machine_outputs"]
        assert machines["status"] == "unavailable" and machines["rows"] == []
        assert "amachreal" in machines["reason"] and "RuntimeError" in machines["reason"]
        assert state["branch_flows"]["status"] == "ok" and state["buses"] and state["line_flows"]
    section = _section(manifest, "reference")
    assert section["status"] == "ok"
    assert section["counts"]["extended_reads_unavailable"] == len(states)
    assert b"fakeuser" not in _all_bytes(manifest, members, out, err)
    # the all-branch read refused by ierr, the job's own branch_loading still works
    folder = tmp_path / "branch"
    folder.mkdir()
    refusing = World(folder)
    fake = RefusesTheAllBranchRead()
    fake.fake_register_case(str(refusing.case), placeholder_case())
    refusing.fake = fake
    refusing, code, out, err, manifest, members = _reference_run(
        folder, monkeypatch, world=refusing)
    assert code == 0, out + err
    base = _json(members, prefix + "base.json")
    assert base["branch_flows"]["status"] == "unavailable"
    assert base["branch_flows"]["reason"] == "abrnreal: ierr 1" and base["branch_flows"]["rows"] == []
    assert base["line_flows"] and base["buses"]
    assert base["machine_outputs"]["status"] == "ok"
    section = _section(manifest, "reference")
    assert section["status"] == "ok" and section["counts"]["extended_reads_unavailable"] > 0
    assert section["counts"]["converged"] == section["counts"]["outages"]
    _summary_lines_match(out)


def test_machine_flag_falls_back_and_is_recorded(tmp_path, monkeypatch):
    """The machine selection flag is unverified on real PSS/E: the one that works is on record."""
    world, code, out, err, manifest, members = _reference_run(tmp_path, monkeypatch)
    assert code == 0, out + err
    base = _json(members, "reference/austin/base.json")
    assert base["machine_outputs"]["flag"] in reference.MACHINE_FLAGS
    assert base["machine_outputs"]["flag"] == 2 and base["branch_flows"]["flag"] == 4
    rows = base["machine_outputs"]["rows"]
    assert [row["bus"] for row in rows] == sorted(row["bus"] for row in rows)
    assert all(row["in_service"] for row in rows)


def test_without_a_raw_export_the_json_members_are_still_written(tmp_path, monkeypatch):
    """No RAW export form worked: every JSON member is written and every snapshot field is null."""
    world, code, out, err, manifest, members = _reference_run(
        tmp_path, monkeypatch, cities=("AUSTIN",), raw_forms=())
    assert code == 1
    assert _section(manifest, "network")["status"] == "failed"
    assert _section(manifest, "reference")["status"] == "ok"
    prefix = "reference/austin/"
    assert not [name for name in members if name.startswith("reference/") and name.endswith(".raw")]
    base = _json(members, prefix + "base.json")
    outages = _json(members, prefix + "outages.json")
    margin_json = _json(members, prefix + "margin.json")
    assert base["snapshot"] is None and base["buses"]
    assert outages["count"] > 0
    assert all(record["snapshot"] is None and record["buses"] for record in outages["outages"])
    assert margin_json["last_good"]["snapshot"] is None and margin_json["last_good"]["buses"]


def test_a_missing_case_index_is_a_failure_not_a_skip(tmp_path, monkeypatch):
    """The reference answer could not be produced when the case could not be indexed: failed, no members."""
    world, code, out, err, manifest, members = _reference_run(
        tmp_path, monkeypatch, fail={"case": "raise"})
    assert code == 1
    section = _section(manifest, "reference")
    assert section["status"] == "failed" and section["detail"] == ["no case index", "load_case"]
    assert not [name for name in members if name.startswith("reference/")]
    _summary_lines_match(out)


def test_no_saved_case_copy_is_left_or_zipped(tmp_path, monkeypatch):
    """T-01-11: no .sav copy is left (even with the work folder kept), none is a member, failed cities included."""
    monkeypatch.setattr(bundle.WorkFolder, "remove", lambda self: 0)
    original = study.prepare_city_base
    saved = []

    def prepare(index, mapping, selection, city, budget, temp_dir):
        base = original(index, mapping, selection, city, budget, temp_dir)
        if city == "MIDLAND":
            saved.append(os.path.isfile(base.saved_path))
            raise study.StudyFailed("contingency", "failed after the saved copy was written")
        return base

    monkeypatch.setattr(study, "prepare_city_base", prepare)
    world, code, out, err, manifest, members = _reference_run(
        tmp_path, monkeypatch, cities=constants.CITIES)
    assert code == 1
    assert saved == [True]
    found = []
    for root, _dirs, files in os.walk(str(tmp_path)):
        found.extend(os.path.join(root, name) for name in files if name.endswith(".sav"))
    assert found == [str(world.case)]
    assert not (world.out / (bundle.SESSION_PREFIX + STAMP) / "tmp_sav").exists()
    assert not [name for name in members if name.endswith(".sav")]
    assert not [name for name in manifest["members"] if name.endswith(".sav")]


def test_budget_exhaustion_keeps_the_records_so_far(tmp_path, monkeypatch):
    """The run-time budget running out mid-screen fails the city at stage contingency and keeps the outages done."""
    real_budget = study.Budget
    ticks = {"count": 0}

    def clock():
        ticks["count"] += 1
        return 0.0 if ticks["count"] <= 3 else 1.0e9

    monkeypatch.setattr(study, "Budget",
                        lambda max_seconds: real_budget(clock=clock, max_seconds=max_seconds))
    captured = _capture_results(monkeypatch)
    world, code, out, err, manifest, members = _reference_run(tmp_path, monkeypatch)
    assert code == 1, out + err
    prefix = "reference/austin/"
    outages = _json(members, prefix + "outages.json")
    assert outages["status"] == "failed" and outages["count"] == 2 == len(outages["outages"])
    assert [record["position"] for record in outages["outages"]] == [0, 1]
    assert captured[0]["AUSTIN"]["status"] == "failed"
    assert captured[0]["AUSTIN"]["detail"] == ("contingency",)
    assert prefix + "base.json" in members and prefix + "margin.json" not in members
    assert _json(members, prefix + "base.json")["status"] == "ok"
    section = _section(manifest, "reference")
    assert section["status"] == "failed" and section["detail"] == ["contingency"]
    assert section["counts"]["outages"] == 2
    _summary_lines_match(out)
