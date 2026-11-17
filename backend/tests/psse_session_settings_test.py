"""
PSE-02 proofs of the settings and scaling sections of the laptop session (pandapower-solver
Phase 1, plan 01-04) on a fake psspy: `psse_session.settings_probe.run` and
`psse_session.scaling_probe.run` driven through `session.main`, reading the zip they leave.

Honest scope: the fake (backend/tests/psse_session_fake.py) shows call order and bookkeeping only.
That real PSS/E 36.4 has the readers `prmint` and `prmdat` under these names, that the eight-option
`fnsl` list means what research assumption A6 says, and that whole-case scaling clamps or ties Q to
P as the experiments suppose, are all UNVERIFIED until the session of plan 01-10. Every test uses
the committed 9xxxx placeholder series and the committed placeholder mapping; nothing here holds a
real bus number, path or name. Scenario solvers and fake subclasses live in this file. Plain
asserts, no classes of tests, no network.
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import pytest  # noqa: E402

import psse_session_fake  # noqa: E402
from psse_fake_psspy import FakePsspy, placeholder_case  # noqa: E402
from psse_job import constants, study  # noqa: E402
from psse_job import mapping as mapping_module  # noqa: E402
from psse_session import bundle, scaling_probe, session, settings_probe  # noqa: E402
from psse_session_test import (  # noqa: E402
    EXAMPLE_MAPPING, FAKE_PATH_TEXT, World, _read_zip, _run, _summary_lines_match)

PRM = {"ITMXN": 20, "TOLN": 0.0001}
CITY_COUNT = len(constants.CITIES)
VARIANT_NAMES = ["default", "forum", "var_limits_immediate", "var_limits_ignore"]


def _json(members, name):
    return json.loads(members[name].decode("ascii"))


def _section(manifest, name):
    return dict((item["name"], item) for item in manifest["sections"])[name]


def _folder(tmp_path, name):
    """A new empty folder `name` inside tmp_path (a test that runs several worlds needs one each)."""
    path = tmp_path / name
    path.mkdir()
    return path


def _settings_run(tmp_path, monkeypatch, sections=("network", "settings"), fake=None, **fake_options):
    """(world, code, out, err, manifest, members) of a session limited to `sections`.

    `fake` is a FakeSessionPsspy subclass instance that replaces the world's own fake."""
    monkeypatch.setattr(session, "SECTIONS", tuple(sections))
    world = World(tmp_path, **fake_options)
    if fake is not None:
        fake.fake_register_case(str(world.case), placeholder_case())
        world.fake = fake
    code, out, err = _run(world, monkeypatch)
    manifest, members = _read_zip(world.zip_path())
    return world, code, out, err, manifest, members


def _case_and_fnsl(world):
    """The fake's calls to `case` and `fnsl`, in order, as (name, args, kwargs)."""
    return [call for call in world.fake.fake_calls if call[0] in ("case", "fnsl")]


def test_tracer_settings_section_reads_and_fingerprints_into_the_zip(tmp_path, monkeypatch):
    """PSE-02 on the fake: every setting key is read, measured or unavailable with a reason, and
    every city and variant leaves a fingerprint solved from a fresh load."""
    world, code, out, err, manifest, members = _settings_run(tmp_path, monkeypatch, prm=PRM)
    assert code == 0, out + err
    document = _json(members, "settings/settings.json")
    assert bundle.MEMBER_MARKER in document
    settings = document["settings"]
    assert sorted(settings) == sorted(settings_probe.SETTING_KEYS)
    assert len(settings_probe.SETTING_KEYS) == 10
    for key, entry in settings.items():
        assert entry["status"] in ("read", "measured", "unavailable"), key
        if entry["status"] == "unavailable":
            assert entry["reason"], key
    # the two named readers
    assert settings["iteration_limit"]["status"] == "read"
    assert settings["iteration_limit"]["value"] == 20
    assert settings["mismatch_tolerance_mva"]["status"] == "read"
    assert settings["mismatch_tolerance_mva"]["value"] == 0.0001
    # var_limits is measured by the fingerprints
    var_limits = settings["var_limits"]
    assert var_limits["status"] == "measured" and var_limits["source"] == "fingerprint"
    assert var_limits["members"]
    # the three counted settings come from the network section's counts
    assert settings["tap_adjustment"]["status"] == "measured"
    assert settings["tap_adjustment"]["value"] == "no controlling transformers"
    assert settings["switched_shunt_adjustment"]["status"] == "measured"
    assert settings["switched_shunt_adjustment"]["value"] == "no switched shunts"
    assert settings["area_interchange"]["status"] == "measured"
    assert settings["area_interchange"]["value"] == "one area"
    for key in ("flat_start", "non_divergent", "dc_tap_adjustment"):
        assert settings[key]["status"] == "unavailable" and settings[key]["reason"], key
    # every candidate read is on record, one by one, in the table's order
    assert [(item["function"], item["name"]) for item in document["reads"]] == [
        (row[0], row[1]) for row in settings_probe.SETTINGS_READS]
    by_name = dict((item["name"], item) for item in document["reads"])
    assert by_name["ITMXN"]["ierr"] == 0 and by_name["ITMXN"]["value"] == 20
    assert by_name["PFCODE"]["ierr"] == 1 and by_name["PFCODE"]["value"] is None
    # the signature and the doc text of both readers are members
    assert "settings/docs/prmint.txt" in members and "settings/docs/prmdat.txt" in members
    # 4 cities x 4 variants at the base point, each with JSON, RAW and the call form
    fingerprints = document["fingerprints"]
    assert len(fingerprints) == CITY_COUNT * 4
    assert [(item["city"], item["variant"]) for item in fingerprints] == [
        (city, name) for city in constants.CITIES for name in VARIANT_NAMES]
    for item in fingerprints:
        assert item["point"] == "base"
        stem = "settings/fingerprint_%s_base_%s" % (item["city"].lower(), item["variant"])
        assert item["member"] == stem + ".json" and item["snapshot"] == stem + ".raw"
        assert members[stem + ".raw"] and session._header_revision(members[stem + ".raw"]) == 33
        body = _json(members, stem + ".json")
        assert body["solve"] == item["solve"] and body["solve"]["converged"] is True
        assert body["buses"] and all("pu" in row for row in body["buses"])
        assert item["call_form"] == ("job_default" if item["variant"] == "default" else "positional")
    assert [item["options"] for item in fingerprints[:4]] == [
        None, [1, 0, 0, 1, 1, 0, 99, 0], [1, 0, 0, 1, 1, 0, 0, 0], [1, 0, 0, 1, 1, 0, -1, 0]]
    # every fingerprint starts from a fresh load of the case: case, fnsl, case, fnsl, ...
    names = [call[0] for call in _case_and_fnsl(world)]
    tail = names[-2 * len(fingerprints):]
    assert tail == ["case", "fnsl"] * len(fingerprints)
    assert "fnsl" not in names[:-2 * len(fingerprints)]
    # the default variant is the job's own no-argument fnsl, the others pass the list positionally
    solves = [call for call in _case_and_fnsl(world) if call[0] == "fnsl"][-len(fingerprints):]
    for item, call in zip(fingerprints, solves):
        if item["variant"] == "default":
            assert call[1] == () and call[2] == {}
        else:
            assert call[1] == (item["options"],) and call[2] == {}
    # nothing was saved by the settings section, and the section counts are integers
    assert "save" not in [call[0] for call in world.fake.fake_calls]
    section = _section(manifest, "settings")
    assert section["status"] == "ok" and section["detail"] == []
    assert section["counts"] == {
        "read": 2, "measured": 5, "unavailable": 3,
        "fingerprints": CITY_COUNT * 4, "fingerprints_ok": CITY_COUNT * 4}
    _summary_lines_match(out)
    assert not [name for name in members if name.endswith(".sav")]


def test_values_are_stored_exactly_as_returned(tmp_path, monkeypatch):
    """Edge PSE-02 precision: a float read from the engine round-trips bit for bit, never rounded."""
    odd = 0.1 + 0.2
    assert odd != 0.3
    world, code, out, err, manifest, members = _settings_run(
        tmp_path, monkeypatch, prm={"ITMXN": 20, "TOLN": odd})
    assert code == 0, out + err
    document = _json(members, "settings/settings.json")
    assert document["settings"]["mismatch_tolerance_mva"]["value"] == odd
    assert document["settings"]["mismatch_tolerance_mva"]["value"] != 0.3
    by_name = dict((item["name"], item) for item in document["reads"])
    assert by_name["TOLN"]["value"] == odd and isinstance(by_name["TOLN"]["value"], float)
    assert by_name["ITMXN"]["value"] == 20 and isinstance(by_name["ITMXN"]["value"], int)
    assert repr(odd) in members["settings/settings.json"].decode("ascii")
    # the same holds for bus voltages: the fingerprint keeps floats, not rounded text
    body = _json(members, "settings/fingerprint_austin_base_default.json")
    assert all(isinstance(row["pu"], float) for row in body["buses"])


# ──────────────────────────────────────────────────────────────────────────────
# Stressed fingerprints and refusals of the settings section
# ──────────────────────────────────────────────────────────────────────────────

MARGIN_INCREMENT_MW = 40.0
FORUM_OPTIONS = [1, 0, 0, 1, 1, 0, 99, 0]


class PositionalRejectingPsspy(psse_session_fake.FakeSessionPsspy):
    """A fake whose fnsl refuses a positional option list with TypeError and accepts the keyword form."""

    def fnsl(self, *args, **kwargs):
        if args:
            raise TypeError("fnsl rejected a positional list for " + FAKE_PATH_TEXT)
        return FakePsspy.fnsl(self, **kwargs)


class OneVariantRefusedPsspy(psse_session_fake.FakeSessionPsspy):
    """A fake whose fnsl returns ierr 1 for the forum option list only."""

    def fnsl(self, options=None):
        if options == FORUM_OPTIONS:
            self.fake_calls.append(("fnsl", (options,), {}))
            return 1
        return FakePsspy.fnsl(self, options)


def _sink_buses(city):
    loaded = mapping_module.load_mapping(EXAMPLE_MAPPING, allow_placeholder=True)
    return list(loaded.cities[city].sink_buses)


def _reference_stub(entries):
    """A reference section that only publishes `entries` (city -> (margin_increments, sink_buses))."""
    def run(ctx):
        results = {}
        for city, (increments, sink) in entries.items():
            results[city] = {"status": "ok", "detail": (), "notes": [],
                             "margin_increments": increments, "sink_buses": sink}
        ctx.results["reference"] = results
        return session.SectionResult("ok", (), {})
    return run


def _sav_files(root):
    found = []
    for folder, _dirs, files in os.walk(str(root)):
        found.extend(os.path.join(folder, name) for name in files if name.endswith(".sav"))
    return found


def test_stressed_fingerprints_at_the_margin_point(tmp_path, monkeypatch):
    """The settings section adds four fingerprints at the recorded last-good transfer of a city, from
    the saved base, and leaves no saved copy; cities without a recorded increment get none."""
    monkeypatch.setattr(bundle.WorkFolder, "remove", lambda self: 0)
    monkeypatch.setitem(session.SECTION_FUNCTIONS, "reference", _reference_stub({
        "AUSTIN": ((MARGIN_INCREMENT_MW, 60.0), _sink_buses("AUSTIN")),
        "MIDLAND": (None, None)}))
    world, code, out, err, manifest, members = _settings_run(
        tmp_path, monkeypatch, sections=("network", "reference", "settings"), prm=PRM)
    assert code == 0, out + err
    document = _json(members, "settings/settings.json")
    stressed = [item for item in document["fingerprints"] if item["point"] == "margin_last_good"]
    assert [(item["city"], item["variant"]) for item in stressed] == [
        ("AUSTIN", name) for name in VARIANT_NAMES]
    assert len(document["fingerprints"]) == CITY_COUNT * 4 + 4
    for item in stressed:
        stem = "settings/fingerprint_austin_margin_last_good_%s" % item["variant"]
        assert item["member"] == stem + ".json" and item["snapshot"] == stem + ".raw"
        assert item["increment_mw"] == MARGIN_INCREMENT_MW
        assert members[stem + ".raw"] and _json(members, stem + ".json")["solve"]["converged"] is True
    assert not [item for item in document["fingerprints"]
                if item["city"] == "MIDLAND" and item["point"] != "base"]
    # the case was rebuilt four times from the saved base, with the sink subsystem and the increment
    calls = world.fake.fake_calls
    increments = [kwargs["scalval"][0] for name, _a, kwargs in calls
                  if name == "scal_2" and kwargs.get("all") == 0]
    assert increments == [MARGIN_INCREMENT_MW] * 4
    subsystems = [kwargs["buses"] for name, _a, kwargs in calls if name == "bsys"]
    assert subsystems == [_sink_buses("AUSTIN")] * 4
    saved = list(world.fake.fake_saved_paths)
    assert len(saved) == 1 and os.sep + "tmp_sav_settings" + os.sep in saved[0]
    assert saved[0].startswith(str(world.out))
    loaded_paths = [args[0] for name, args, _kwargs in calls if name == "case"]
    assert loaded_paths.count(saved[0]) == 4
    # no saved copy is left behind (the work folder was kept on purpose), none is a member
    assert _sav_files(tmp_path) == [str(world.case)]
    assert not [name for name in members if name.endswith(".sav")]
    section = _section(manifest, "settings")
    assert section["counts"]["fingerprints"] == CITY_COUNT * 4 + 4
    assert section["counts"]["fingerprints_ok"] == CITY_COUNT * 4 + 4


def test_refused_reads_and_variants_are_recorded(tmp_path, monkeypatch):
    """A refused reader, a rejected positional list, an ierr 1 variant and a total failure are all
    recorded with their cause; the other readers and fingerprints still run."""
    # 1. prmint raises: the setting names the call and the class, nothing else is lost
    world, code, out, err, manifest, members = _settings_run(
        _folder(tmp_path, "a"), monkeypatch, prm=PRM, fail={"prmint": "raise"})
    assert code == 0, out + err
    document = _json(members, "settings/settings.json")
    refused = document["settings"]["iteration_limit"]
    assert refused["status"] == "unavailable"
    assert "prmint" in refused["reason"] and "RuntimeError" in refused["reason"]
    assert document["settings"]["mismatch_tolerance_mva"]["status"] == "read"
    assert document["counts"]["fingerprints_ok"] == CITY_COUNT * 4
    assert b"fakeuser" not in b"".join(members.values())
    assert "fakeuser" not in out + err
    # 2. a fnsl that rejects the positional list with TypeError: the keyword form is recorded
    world, code, out, err, manifest, members = _settings_run(
        _folder(tmp_path, "b"), monkeypatch, fake=PositionalRejectingPsspy())
    assert code == 0, out + err
    forms = dict(((item["city"], item["variant"]), item["call_form"])
                 for item in _json(members, "settings/settings.json")["fingerprints"])
    assert set(forms[(city, "default")] for city in constants.CITIES) == {"job_default"}
    for variant in VARIANT_NAMES[1:]:
        assert set(forms[(city, variant)] for city in constants.CITIES) == {"keywords"}
    keyword_calls = [call for call in world.fake.fake_calls
                     if call[0] == "fnsl" and "options" in call[2]]
    assert len(keyword_calls) == CITY_COUNT * 3
    assert b"fakeuser" not in b"".join(members.values()) and "fakeuser" not in out + err
    # 3. one variant returns ierr 1: recorded with its meaning, no member, the rest unaffected
    world, code, out, err, manifest, members = _settings_run(
        _folder(tmp_path, "c"), monkeypatch, fake=OneVariantRefusedPsspy())
    assert code == 0, out + err
    document = _json(members, "settings/settings.json")
    refused = [item for item in document["fingerprints"] if item["variant"] == "forum"]
    assert len(refused) == CITY_COUNT
    for item in refused:
        assert item["member"] is None and item["snapshot"] is None
        assert item["solve"]["converged"] is False and item["solve"]["ierr"] == 1
        assert "fnsl ierr 1" in item["solve"]["meaning"]
        assert "settings/fingerprint_%s_base_forum.json" % item["city"].lower() not in members
    assert document["counts"]["fingerprints_ok"] == CITY_COUNT * 3
    assert len(document["settings"]["var_limits"]["members"]) == CITY_COUNT * 3
    assert _section(manifest, "settings")["status"] == "ok"
    # 4. every solve refused: var_limits is unavailable with a reason and the section is failed
    world, code, out, err, manifest, members = _settings_run(
        _folder(tmp_path, "d"), monkeypatch, fail={"fnsl": 1})
    assert code == 1
    document = _json(members, "settings/settings.json")
    assert document["settings"]["var_limits"]["status"] == "unavailable"
    assert document["settings"]["var_limits"]["reason"]
    assert document["counts"]["fingerprints_ok"] == 0
    section = _section(manifest, "settings")
    assert section["status"] == "failed" and section["detail"] == ["unavailable"]
    _summary_lines_match(out)


# ──────────────────────────────────────────────────────────────────────────────
# The scaling section
# ──────────────────────────────────────────────────────────────────────────────


def _experiments(members):
    document = _json(members, "scaling/experiments.json")
    assert bundle.MEMBER_MARKER in document
    return document["experiments"]


def test_tracer_scaling_experiments_in_order_with_snapshots(tmp_path, monkeypatch):
    """PSE-02: the four experiments run in order, each from a fresh load, with before and after snapshots."""
    low, high = study.SCALE_FACTOR_BOUNDS
    assert all(low <= factor <= high for factor in scaling_probe.CLAMP_FACTORS.values())
    assert scaling_probe.CLAMP_FACTORS == {"clamp_at_limits_x1_5": 1.5, "clamp_at_limits_x3": 3.0}
    assert scaling_probe.Q_WITH_P_INCREMENT_MW == 10.0
    # the baseline: how many case loads the network section alone makes
    base_world, code, out, err, _manifest, _members = _settings_run(
        _folder(tmp_path, "base"), monkeypatch, sections=("network",))
    assert code == 0, out + err
    base_loads = [call[0] for call in base_world.fake.fake_calls].count("case")
    world, code, out, err, manifest, members = _settings_run(
        _folder(tmp_path, "scaling"), monkeypatch, sections=("network", "scaling"))
    assert code == 0, out + err
    experiments = _experiments(members)
    assert [item["name"] for item in experiments] == list(scaling_probe.EXPERIMENTS)
    assert list(scaling_probe.EXPERIMENTS) == [
        "swing_in_total", "clamp_at_limits_x1_5", "clamp_at_limits_x3", "q_with_p"]
    for item in experiments:
        assert item["status"] == "ok" and item["detail"] == []
        assert item["before"] == "scaling/%s_before.raw" % item["name"]
        assert item["after"] == "scaling/%s_after.raw" % item["name"]
        for member in (item["before"], item["after"]):
            assert members[member] and session._header_revision(members[member]) == 33
    by_name = dict((item["name"], item) for item in experiments)
    swing = by_name["swing_in_total"]
    assert swing["totals_before"]["load_mw"] > 0 and swing["totals_before"]["gen_mw"] > 0
    assert swing["totals_after"] is None and swing["targets"] is None
    assert members[swing["before"]] == members[swing["after"]]
    for name, factor in scaling_probe.CLAMP_FACTORS.items():
        item = by_name[name]
        before = item["totals_before"]
        assert item["targets"] == {"load_mw": before["load_mw"] * factor,
                                   "gen_mw": before["gen_mw"] * factor}
        assert item["totals_after"]["load_mw"] == pytest.approx(item["targets"]["load_mw"], rel=1e-9)
        assert item["totals_after"]["gen_mw"] == pytest.approx(item["targets"]["gen_mw"], rel=1e-9)
        assert members[item["before"]] != members[item["after"]]
    # the first city's sink buses, the increment form and the Q-with-P snapshots
    q_with_p = by_name["q_with_p"]
    assert q_with_p["sink_buses"] == _sink_buses(constants.CITIES[0])
    assert q_with_p["increment_mw"] == 10.0 and q_with_p["totals_before"] is None
    assert members[q_with_p["before"]] != members[q_with_p["after"]]
    # a case load starts every experiment
    loads = [call[0] for call in world.fake.fake_calls].count("case")
    assert loads == base_loads + len(scaling_probe.EXPERIMENTS)
    section = _section(manifest, "scaling")
    assert section["status"] == "ok" and section["detail"] == []
    assert section["counts"] == {"experiments": 4, "experiments_ok": 4}
    _summary_lines_match(out)


def test_scaling_refusals_are_recorded(tmp_path, monkeypatch):
    """A refused scal_2 fails the experiments that need it and keeps what was written before; with no
    RAW export the totals are still recorded and the section says so."""
    world, code, out, err, manifest, members = _settings_run(
        _folder(tmp_path, "a"), monkeypatch, sections=("network", "scaling"), fail={"scal_2": 1})
    assert code == 1
    by_name = dict((item["name"], item) for item in _experiments(members))
    for name in ("clamp_at_limits_x1_5", "clamp_at_limits_x3", "q_with_p"):
        assert by_name[name]["status"] == "failed" and by_name[name]["detail"] == ["PsseCallError"], name
        assert by_name[name]["after"] is None
    assert "scaling/swing_in_total_before.raw" in members
    assert by_name["swing_in_total"]["before"] == "scaling/swing_in_total_before.raw"
    section = _section(manifest, "scaling")
    assert section["status"] == "failed" and section["detail"] == ["PsseCallError"]
    assert section["counts"] == {"experiments": 4, "experiments_ok": 0}
    assert "fakeuser" not in out + err
    _summary_lines_match(out)
    # every RAW export form refused: no snapshots, the totals are recorded, the section is failed
    world, code, out, err, manifest, members = _settings_run(
        _folder(tmp_path, "b"), monkeypatch, sections=("network", "scaling"), raw_forms=())
    assert code == 1
    experiments = _experiments(members)
    assert [item["name"] for item in experiments] == list(scaling_probe.EXPERIMENTS)
    for item in experiments:
        assert item["status"] == "ok" and item["before"] is None and item["after"] is None
    assert experiments[0]["totals_before"]["load_mw"] > 0
    assert experiments[1]["totals_after"]["gen_mw"] > 0
    section = _section(manifest, "scaling")
    assert section["status"] == "failed" and section["detail"] == ["no raw export"]
    _summary_lines_match(out)


def test_scaling_section_never_solves_or_saves(tmp_path, monkeypatch):
    """T-01-14: the scaling section makes no fnsl and no save call, and writes no case copy."""
    monkeypatch.setattr(bundle.WorkFolder, "remove", lambda self: 0)
    world, code, out, err, manifest, members = _settings_run(
        tmp_path, monkeypatch, sections=("network", "scaling"))
    assert code == 0, out + err
    names = [call[0] for call in world.fake.fake_calls]
    assert "fnsl" not in names and "save" not in names
    assert names.count("scal_2") > 0 and names.count("bsys") == 1
    assert world.fake.fake_saved_paths == []
    assert _sav_files(tmp_path) == [str(world.case)]
