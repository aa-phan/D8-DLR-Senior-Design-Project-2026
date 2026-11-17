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
    EXAMPLE_MAPPING, FIXED_NOW, World, _read_zip, _run, _summary_lines_match)


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
