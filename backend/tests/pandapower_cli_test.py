"""
Tests of the owner's two commands (pandapower-solver Phase 1, plan 01-09: NET-02, NET-03, PSE-04):
`pandapower_job.cli.main` with `ingest` and `check`, run in-process on synthetic and fake-session
data inside a throwaway git repository (a `.gitignore` holding `/data/private/`) that is passed as
`repo_root`, so nothing is ever written into this checkout's real data folder.

Honest scope. The synthetic references are circular: they are made by pandapower from the 39-bus
public case with every bus number offset by 90000, so they prove wiring, the private-path rules,
the counts-only output and failure detection, never agreement with PSS/E. The seam test runs the
real session code (plans 01-02 to 01-04) against the fake psspy and proves that the member names
and JSON shapes the laptop writes are the ones the Mac side reads; the fake's numbers are not
physics, so that run's NET-03 verdict is a fail by design.

No test here holds a real bus number, path or name. The marker keys are taken from the modules, so
this file does not match the leak guard's shape layer.
"""

import copy
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import types
import zipfile

import pytest

pandapower = pytest.importorskip("pandapower")

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import pandapower_fixture as fixture  # noqa: E402
from psse_job import constants, mapping as mapping_module  # noqa: E402
from psse_session import bundle  # noqa: E402
from pandapower_job import cli, compare, convert, ingest, network, raw, scaling, solve  # noqa: E402

ENTRY = os.path.join(_BACKEND, "pandapower_net_check.py")
EXAMPLE_MAPPING = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
FIXED_NOW = datetime.datetime(2026, 11, 16, 15, 0, 0, tzinfo=datetime.timezone.utc)
STAMP = "20261116T150000Z"
CHECK_STAMP = "20261116T160000Z"
CHECK_NOW = datetime.datetime(2026, 11, 16, 16, 0, 0, tzinfo=datetime.timezone.utc)
CITY_FACTORS = {"AUSTIN": 1.04, "CORPUS_CHRISTI": 1.08, "MIDLAND": 1.12, "EL_PASO": 1.16}
ROOMY_PT_MW = 5000.0
SWING_PG_MW = 500.0
SOLVE_SETTINGS = solve.SolveSettings(True, 1e-8, 30, 0.5, {}, ())
OUTPUT_NAMES = ("report.json", "converted_network.json", "d06_evidence.json",
                "scaling_details.json")


# -- the throwaway repository ---------------------------------------------------------------------


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo)] + list(args), check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def make_repo(path):
    """A git repository at `path` whose .gitignore holds the private-data rule."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / ".gitignore").write_text("/data/private/\n", encoding="utf-8")
    return str(path)


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


def run_cli(argv, repo, now=CHECK_NOW):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(argv, out=out, err=err, repo_root=repo, now=now)
    return code, out.getvalue(), err.getvalue()


def assert_counts_only(*texts):
    for text in texts:
        for line in text.splitlines():
            assert any(pattern.match(line) for pattern in cli.CLI_LINE_PATTERNS), (
                "a printed line is outside the command vocabulary")


# -- a synthetic session (case39, offset 90000, circular references) ------------------------------


def _roomy_records():
    """Records of the synthetic case with every machine's P maximum raised, so scaling factors
    above one never pass a limit; the swing machine is left at zero output."""
    records = fixture.case39_records(fixture.OFFSET)
    for machine in records["generator"]:
        machine["PT"] = ROOMY_PT_MW
    return records


def _reference(solved, city):
    """`fixture.reference_from_solved` of a solved net. The fixture reads a transformer's flows
    from line column names (it is frozen for this plan), so the transformer results get the line
    names on a copy first: the same numbers, hv end as the from end."""
    aliased = copy.deepcopy(solved)
    for line_name, trafo_name in zip(("p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar"),
                                     ("p_hv_mw", "q_hv_mvar", "p_lv_mw", "q_lv_mvar")):
        aliased.res_trafo[line_name] = aliased.res_trafo[trafo_name]
    return fixture.reference_from_solved(aliased, city)


def _by_name(table, column):
    return dict((table.at[index, "name"], float(table.at[index, column])) for index in table.index)


def _with_values(records, scaled, swing_pg=None):
    """A copy of `records` carrying the machine output and load values of the scaled net."""
    copied = copy.deepcopy(records)
    gen = _by_name(scaled.gen, "p_mw")
    load_p, load_q = _by_name(scaled.load, "p_mw"), _by_name(scaled.load, "q_mvar")
    for machine in copied["generator"]:
        key = "%d-%s" % (machine["I"], machine["ID"])
        if key in gen:
            machine["PG"] = gen[key]
        elif swing_pg is not None:
            machine["PG"] = swing_pg
    for load in copied["load"]:
        key = "%d-%s" % (load["I"], load["ID"])
        load["PL"], load["QL"] = load_p[key], load_q[key]
    return copied


_PARTS = {}


def _parts():
    """The case's RAW text and, per city, targets, pre-solve RAW text, reference and voltages."""
    if "parts" not in _PARTS:
        records = _roomy_records()
        text = fixture.raw_text(records)
        net = network.build_network(raw.parse_raw(text.encode("utf-8")))
        load_total = float(net.load.p_mw.sum())
        gen_total = float(net.gen.p_mw.sum())
        details = scaling.ScalingDetails("no", "inconclusive", "inconclusive", {})
        cities = {}
        for city in constants.CITIES:
            factor = CITY_FACTORS[city]
            targets = (load_total * factor, gen_total * factor)
            scaled = scaling.scale_city(
                net, mapping_module.Scaling(targets[0], targets[1], "average"), details)
            assert solve.run_load_flow(scaled, SOLVE_SETTINGS, True).converged
            cities[city] = {
                "targets": targets, "reference": _reference(scaled, city),
                "presolve": fixture.raw_text(_with_values(records, scaled)),
                "voltages": [(int(i), float(scaled.res_bus.at[i, "vm_pu"]))
                             for i in sorted(scaled.bus.index)]}
        _PARTS["parts"] = {"records": records, "text": text, "cities": cities,
                           "gen_total": gen_total}
    return copy.deepcopy(_PARTS["parts"])


def _mapping_document(parts):
    records = parts["records"]
    cities = {}
    for position, city in enumerate(constants.CITIES):
        line = records["branch"][position]
        load_bus = records["load"][position]["I"]
        load_target, gen_target = parts["cities"][city]["targets"]
        cities[city] = {
            "branches": [{"from_bus": line["I"], "to_bus": line["J"], "ckt": line["CKT"]}],
            "sink_buses": [load_bus],
            "scaling": {"load_mw": load_target, "gen_mw": gen_target, "basis": "average"}}
    return {"schema_version": 2, "cities": cities, "study": {}}


def _settings_document(parts):
    """settings.json with decisive fingerprints: the default solve equals the immediate-limits
    variant and differs from the ignore-limits variant, so var limits classify as applied."""
    voltages = parts["cities"]["AUSTIN"]["voltages"]

    def payload(variant, shift):
        buses = [{"number": number, "type_code": 1, "base_kv": 345.0,
                  "pu": pu + (shift if position == 0 else 0.0)}
                 for position, (number, pu) in enumerate(voltages)]
        return {"city": "AUSTIN", "point": "base", "variant": variant,
                "solve": {"converged": True, "ierr": 0}, "buses": buses}

    members = {}
    for variant, shift in (("default", 0.0), ("var_limits_immediate", 0.0),
                           ("var_limits_ignore", 0.02)):
        members["settings/fingerprint_austin_base_%s.json" % variant] = payload(variant, shift)
    document = {
        "settings": {
            "mismatch_tolerance_mva": {"status": "read", "value": 1e-8, "source": "synthetic"},
            "iteration_limit": {"status": "read", "value": 30, "source": "synthetic"}},
        "fingerprints": [{"member": name, "city": "AUSTIN", "point": "base",
                          "variant": item["variant"]} for name, item in sorted(members.items())]}
    return document, members


def _experiments_document(parts):
    """swing_in_total classifies as "no": the pre-solve snapshot's swing machine has output and the
    total PSS/E reported excludes it."""
    records = copy.deepcopy(parts["records"])
    swing_buses = {bus["I"] for bus in records["bus"] if bus["IDE"] == 3}
    for machine in records["generator"]:
        if machine["I"] in swing_buses:
            machine["PG"] = SWING_PG_MW
    experiment = {
        "name": "swing_in_total", "status": "ok", "detail": [], "increment_mw": None,
        "before": "scaling/swing_in_total_before.raw", "after": "scaling/swing_in_total_after.raw",
        "sink_buses": None, "targets": None, "totals_after": None,
        "totals_before": {"gen_mw": parts["gen_total"], "load_mw": 1.0}}
    return {"experiments": [experiment], "no_raw_export": False}, fixture.raw_text(records)


def synthetic_session(tmp_path, reference_edit=None, network_records=None, edit_settings=None):
    """
    A throwaway repository holding a schema-2 mapping and a session zip written with the real
    `bundle.WorkFolder` into `data/private/pandapower/incoming/`. `reference_edit` maps a city to
    a function that edits that city's base.json dict in place (or to None to leave the city's
    reference out of the zip); `network_records` replaces the network's RAW records;
    `edit_settings(document, members)` edits the settings members. Returns a namespace with the
    repository, the zip, the mapping path and the session folder `ingest` will create.
    """
    repo = make_repo(tmp_path / "repo")
    parts = _parts()
    private_dir = os.path.join(repo, "data", "private", "pandapower")
    incoming = os.path.join(private_dir, "incoming")
    os.makedirs(incoming)
    mapping_path = os.path.join(private_dir, "mapping.json")
    with open(mapping_path, "wb") as handle:
        handle.write((json.dumps(_mapping_document(parts), indent=1) + "\n").encode("ascii"))
    with open(mapping_path, "rb") as handle:
        mapping_sha = hashlib.sha256(handle.read()).hexdigest()

    work = bundle.WorkFolder(incoming, STAMP)
    network_text = parts["text"] if network_records is None else fixture.raw_text(network_records)
    work.add_bytes("network/network.raw", network_text.encode("utf-8"), "network")
    settings_document, fingerprints = _settings_document(parts)
    if edit_settings is not None:
        edit_settings(settings_document, fingerprints)
    work.add_json("settings/settings.json", settings_document, "settings")
    for name, payload in sorted(fingerprints.items()):
        work.add_json(name, payload, "settings")
    experiments, snapshot = _experiments_document(parts)
    work.add_json("scaling/experiments.json", experiments, "scaling")
    work.add_bytes("scaling/swing_in_total_before.raw", snapshot.encode("utf-8"), "network")
    work.add_bytes("scaling/swing_in_total_after.raw", snapshot.encode("utf-8"), "network")
    for city in constants.CITIES:
        base = copy.deepcopy(parts["cities"][city]["reference"])
        edit = (reference_edit or {}).get(city, "keep")
        if edit is None:
            base = None
        elif edit != "keep":
            edit(base)
        prefix = "reference/%s/" % city.lower()
        if base is not None:
            work.add_json(prefix + "base.json", base, "reference")
        work.add_bytes(prefix + "presolve.raw", parts["cities"][city]["presolve"].encode("utf-8"),
                       "network")
    names = [("network", {"buses": 39}), ("reference", {"cities": 4}), ("settings", {}),
             ("scaling", {"experiments": 1})]
    work.write_manifest(
        {"created_utc": "2026-11-16T15:00:00Z", "mode": "run", "python_version": "3.12.0",
         "psse_version": "36.4.0", "case_sha256": "0" * 64, "mapping_sha256": mapping_sha,
         "mapping_placeholder": False},
        [{"name": name, "status": "ok", "detail": [], "counts": {}} for name, _c in names])
    zip_path = work.zip_and_verify()
    assert work.remove() == 0
    stem = bundle.SESSION_PREFIX + STAMP
    return types.SimpleNamespace(
        repo=repo, zip=zip_path, mapping=mapping_path, stem=stem,
        sessions=os.path.join(private_dir, "sessions"),
        session=os.path.join(private_dir, "sessions", stem))


def ingest_session(world):
    code, out, err = run_cli(["ingest", "--zip", world.zip], world.repo)
    assert code == 0, "ingest of the synthetic zip failed"
    return out, err


def check_session(world, *extra):
    return run_cli(["check", "--session", world.session, "--mapping", world.mapping] + list(extra),
                   world.repo)


# -- Task 1: the tracer ---------------------------------------------------------------------------


def test_tracer_ingest_and_check_a_synthetic_session_to_a_pass(tmp_path):
    world = synthetic_session(tmp_path)
    before = _outside_private(world.repo)

    out, err = ingest_session(world)
    lines = out.splitlines()
    assert lines[0] == "ingest: ok" and err == ""
    assert re.match(r"members verified: [0-9]+\Z", lines[1])
    assert [line for line in lines if line.startswith("section ")] == [
        "section network: ok", "section reference: ok", "section settings: ok",
        "section scaling: ok"]
    assert os.path.isdir(world.session)
    assert not os.path.exists(world.session + ".partial")
    assert_counts_only(out, err)

    code, out, err = check_session(world)
    lines = out.splitlines()
    assert code == 0 and err == "", out
    assert "parity: pass" in lines
    for city in constants.CITIES:
        assert "net03 %s algorithm: pass" % city in lines
    assert "net03: pass (4 of 4 cities)" in lines
    assert "check: pass" in lines
    assert_counts_only(out, err)

    check_dir = os.path.join(world.session, "check_" + CHECK_STAMP)
    assert sorted(os.listdir(check_dir)) == sorted(OUTPUT_NAMES)
    assert _outside_private(world.repo) == before
    # the converted copy is the one convert.case_to_json writes
    parts = _parts()
    case = raw.parse_raw(parts["text"].encode("utf-8"))
    with open(os.path.join(check_dir, "converted_network.json"), "rb") as handle:
        assert handle.read() == convert.case_to_json(case)

    # nothing printed names one of the network's bus numbers (the size line aside)
    printed = "\n".join(line for line in out.splitlines() if not line.startswith("converted copy"))
    assert not re.search(r"\b900[0-3][0-9]\b", printed)


def test_entry_script_without_arguments_is_a_usage_error():
    completed = subprocess.run(
        [sys.executable, "-I", "-B", ENTRY], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=120)
    assert completed.returncode == 2
    assert b"Traceback" not in completed.stderr
