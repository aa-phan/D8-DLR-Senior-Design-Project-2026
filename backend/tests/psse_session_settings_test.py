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

from psse_job import constants  # noqa: E402
from psse_session import bundle, session, settings_probe  # noqa: E402
from psse_session_test import World, _read_zip, _run, _summary_lines_match  # noqa: E402

PRM = {"ITMXN": 20, "TOLN": 0.0001}
CITY_COUNT = len(constants.CITIES)
VARIANT_NAMES = ["default", "forum", "var_limits_immediate", "var_limits_ignore"]


def _json(members, name):
    return json.loads(members[name].decode("ascii"))


def _section(manifest, name):
    return dict((item["name"], item) for item in manifest["sections"])[name]


def _settings_run(tmp_path, monkeypatch, sections=("network", "settings"), **fake_options):
    """(world, code, out, err, manifest, members) of a session limited to `sections`."""
    monkeypatch.setattr(session, "SECTIONS", tuple(sections))
    world = World(tmp_path, **fake_options)
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
