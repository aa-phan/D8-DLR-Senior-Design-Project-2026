"""
Shared helper for the replay-phase tests (pandapower-solver Phase 4, plan 04-01, D-01). Not collected
by pytest (the file name does not match `*_test.py`, and nothing here has a `test_` prefix), and
follows `pandapower_study_fixture.py`'s conventions.

Nothing here is Power Systems data. Every row comes from `psse_local_pg.valid_run_rows` and
`failed_run_row` (the public, synthetic rows the PSS/E database tests use), projected to the columns
the export statement selects, and every file a test writes with these helpers goes into a throwaway
git repository under the test's `tmp_path`, never into this checkout.
"""

import collections
import copy
import csv
import datetime
import json
import os
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import psse_local_pg  # noqa: E402
import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import contract, ratings, run_record  # noqa: E402
from pandapower_job import engine, recorded  # noqa: E402

# Two distinct 64-character lowercase hex strings (synthetic).
HEX_A = "ab" * 32
HEX_B = "cd" * 32


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo)] + list(args), check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def make_repo(path):
    """A git repository at `path` whose .gitignore holds the private-data rule; returns the path as text."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / ".gitignore").write_text("/data/private/\n", encoding="utf-8")
    return str(path)


def run_bundle(n, started_at, outcome="fallback", mapping_sha256=HEX_A, case_sha256=HEX_B, violations=2):
    """
    One recorded run as DB-shaped rows: a dict with the keys `run`, `dispatch`, `margins` and
    `contingencies`. `started_at` is an aware datetime; run id number `n`. A failed run has no
    result rows.
    """
    run_id = psse_local_pg.make_run_id(n, started_at)
    if outcome == "failed":
        run = psse_local_pg.failed_run_row(run_id, started_at)
        rows = {"psse_dispatched_capacity": [], "psse_voltage_margin": [], "psse_contingency_result": []}
    else:
        rows = psse_local_pg.valid_run_rows(run_id, started_at, outcome=outcome, violations=violations)
        run = dict(rows["psse_run"][0])
    run["case_sha256"] = case_sha256
    run["mapping_sha256"] = mapping_sha256
    return {
        "run": run,
        "dispatch": [dict(row) for row in rows["psse_dispatched_capacity"]],
        "margins": [dict(row) for row in rows["psse_voltage_margin"]],
        "contingencies": [dict(row) for row in rows["psse_contingency_result"]],
    }


def _cell(value):
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return value


def _project(row, columns):
    return dict((column, _cell(row.get(column))) for column in columns)


def export_document(bundles, counts=None):
    """
    The one row the export statement returns, as a dict with the five `EXPORT_COLUMNS`: every row
    projected to exactly the pinned columns (a missing key becomes None, a datetime becomes ISO
    text), runs ordered by slot, result rows only for runs whose outcome is not failed. `counts` is
    filled from the projected lists unless a dict is passed (so a test can lie about it).
    """
    runs = sorted((_project(bundle["run"], recorded.RUN_COLUMNS) for bundle in bundles),
                  key=lambda row: (row["slot_time"], row["run_id"]))
    usable = [bundle for bundle in bundles if bundle["run"]["outcome"] != "failed"]
    dispatch = sorted(
        (_project(row, recorded.DISPATCH_COLUMNS) for bundle in usable for row in bundle["dispatch"]),
        key=lambda row: (row["run_id"], row["city"]))
    margins = sorted(
        (_project(row, recorded.MARGIN_COLUMNS) for bundle in usable for row in bundle["margins"]),
        key=lambda row: (row["run_id"], row["city"]))
    contingencies = sorted(
        (_project(row, recorded.CONTINGENCY_COLUMNS) for bundle in usable for row in bundle["contingencies"]),
        key=lambda row: (row["run_id"], row["contingency_id"], row["violation_kind"], row["element_id"]))
    if counts is None:
        counts = {
            "runs": len(runs),
            "usable_runs": sum(1 for row in runs if row["outcome"] != "failed"),
            "dispatch": len(dispatch),
            "margins": len(margins),
            "contingencies": len(contingencies),
        }
    return {"counts": counts, "runs": runs, "dispatch": dispatch, "margins": margins,
            "contingencies": contingencies}


def _prepare(path):
    os.makedirs(os.path.dirname(os.fspath(path)), exist_ok=True)


def write_export_json(path, document, as_list=True):
    """The export as JSON: a one-element list holding the document, or the bare object."""
    _prepare(path)
    payload = [document] if as_list else document
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


def write_export_csv(path, document):
    """The export as CSV: a header of the five column names and one data row, each cell the JSON text."""
    _prepare(path)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(recorded.EXPORT_COLUMNS))
        writer.writerow([json.dumps(document[name]) for name in recorded.EXPORT_COLUMNS])
    return path


# -- the solver stand-in (plan 04-03) ----------------------------------------------------------------
#
# A "recorded PSS/E run" built from the public 39-bus fixture on the real solver: the unchanged
# study runs on the fixture, and its results are presented as a PSS/E run through the very functions
# the PSS/E job uses to build its rows. It proves the wiring and the failure detection of the replay,
# never agreement between PSS/E and pandapower.

FIXED_NOW = datetime.datetime(2026, 11, 20, 10, 30, tzinfo=datetime.timezone.utc)
CASE_SHA = "ef" * 32
STAMP = "20261120T000000Z"

StandIn = collections.namedtuple(
    "StandIn", ["network_path", "mapping_path", "backend", "selection", "results", "bundle",
                "mapping_sha256", "case_sha256"])
Layout = collections.namedtuple(
    "Layout", ["repo", "mapping", "check_dir", "network", "report", "scaling"])


def write_mapping(tmp_path, island=True):
    """The fixture's placeholder mapping, with the islanding outage as `contingency.extra` when
    asked, rewritten with the placeholder flag false (the loader refuses a placeholder). Returns
    the path."""
    study = None
    if island:
        ref = study_fixture.ISLANDING_OUTAGE
        study = {"contingency": {"extra": [
            {"from_bus": ref.from_bus, "to_bus": ref.to_bus, "ckt": ref.ckt}]}}
    path = study_fixture.write_placeholder_mapping(tmp_path, study=study)
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    document["placeholder"] = False
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
    return path


def stress_selection(selection):
    """`selection` with every choice's amps and circuit amps at 10 percent (the "stress" ratings)."""
    choices = dict(
        (city, choice._replace(amps_per_conductor=choice.amps_per_conductor * 0.1,
                               amps_circuit=choice.amps_circuit * 0.1))
        for city, choice in selection.choices.items())
    return ratings.Selection(choices, selection.read_error, selection.ignored_rows)


def standin(tmp_path, stress=False, island=True):
    """Build one stand-in recorded run on the real solver (seconds to a dozen seconds)."""
    network = study_fixture.write_converted(tmp_path)
    mapping = write_mapping(tmp_path, island=island)
    selection = study_fixture.selection()
    if stress:
        selection = stress_selection(selection)
    backend = study_fixture.fixture_backend()
    prepared = engine.prepare_run(backend, network, mapping)
    results = prepared.study(selection, None)
    results = results._replace(solver="psse", solver_version=None, psse_version="test")
    context = contract.RunContext(
        run_record.new_run_id(FIXED_NOW), FIXED_NOW, "case_label", CASE_SHA,
        prepared.mapping_sha256, "standin")
    record = run_record.build_run_record(
        context, selection, FIXED_NOW + datetime.timedelta(minutes=1), results=results)
    rows = run_record.result_rows(record, results)
    bundle = {
        "run": record,
        "dispatch": rows[contract.DISPATCH_TABLE],
        "margins": rows[contract.MARGIN_TABLE],
        "contingencies": rows[contract.CONTINGENCY_TABLE]}
    return StandIn(network, mapping, backend, selection, results, bundle,
                   prepared.mapping_sha256, CASE_SHA)


def _write_json(path, document):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    return path


def private_layout(repo, stand):
    """Write into the throwaway repository `repo` the private files the owner commands read: the
    mapping (a byte-identical copy), and one check folder holding the converted network, the
    settings report (with the session's case hash) and the scaling details. Returns a Layout."""
    root = os.path.join(repo, "data", "private", "pandapower")
    os.makedirs(root, exist_ok=True)
    mapping = os.path.join(root, "mapping.json")
    shutil.copyfile(stand.mapping_path, mapping)
    check_dir = os.path.join(root, "sessions", "session_one", "check_" + STAMP)
    os.makedirs(check_dir, exist_ok=True)
    network = os.path.join(check_dir, "converted_network.json")
    shutil.copyfile(stand.network_path, network)
    values = stand.backend.solve_settings
    settings = {
        "enforce_q_lims": values.enforce_q_lims, "tolerance_mva": values.tolerance_mva,
        "max_iteration": values.max_iteration, "collapse_voltage_pu": values.collapse_voltage_pu,
        "sources": dict(values.sources), "deviations": list(values.deviations)}
    report = _write_json(os.path.join(check_dir, "report.json"), {
        "settings": settings,
        "session": {"case_sha256": stand.case_sha256, "mapping_sha256": stand.mapping_sha256},
        recorded.REPORT_MARKER: 1})
    details = stand.backend.scaling_details
    scaling = _write_json(os.path.join(check_dir, "scaling_details.json"), {
        "swing_in_total": details.swing_in_total, "clamped_at_limits": details.clamped_at_limits,
        "q_scales_with_p": details.q_scales_with_p, "evidence": {"fixture": True},
        recorded.REPORT_MARKER: 1})
    return Layout(repo, mapping, check_dir, network, report, scaling)


def ingest_standins_result(repo, standins, now=FIXED_NOW):
    """Write the stand-ins' export file into the repository's incoming folder, ingest it and
    return the IngestResult (path of the private snapshot, validated snapshot)."""
    export = export_document([item.bundle for item in standins])
    path = write_export_json(
        os.path.join(repo, "data", "private", "pandapower", "incoming", "export.json"), export)
    return recorded.ingest_export(path, repo_root=repo, now=now)


def ingest_standins(repo, standins, now=FIXED_NOW):
    """The snapshot of the stand-ins, read back from the private snapshot file ingest wrote: the
    rows reach the caller only through the export file, the ingest and the loader."""
    result = ingest_standins_result(repo, standins, now)
    return recorded.load_snapshot(result.path, repo_root=repo)


def snapshot_of_bundles(repo, bundles, now=FIXED_NOW, counts=None):
    """Write `bundles` as an export file into the repository, ingest it and load the snapshot back."""
    export = export_document(bundles, counts=counts)
    path = write_export_json(
        os.path.join(repo, "data", "private", "pandapower", "incoming", "export.json"), export)
    result = recorded.ingest_export(path, repo_root=repo, now=now)
    return recorded.load_snapshot(result.path, repo_root=repo)


def perturbed_bundle(stand, mutate, recount=True):
    """A deep copy of the stand-in's bundle changed by `mutate(bundle)`. When `recount` is true the
    run's n_contingencies_with_results is recomputed from the perturbed contingency rows, so a run
    with an added or removed row stays complete, as a real stored run would."""
    bundle = copy.deepcopy(stand.bundle)
    mutate(bundle)
    if recount:
        bundle["run"]["n_contingencies_with_results"] = len(
            set(row["contingency_id"] for row in bundle["contingencies"]))
    return bundle


def perturbed_snapshot(repo, stand, mutate, recount=True):
    """The snapshot of one perturbed copy of the stand-in's run (see perturbed_bundle), reached
    through an export file, the ingest and the loader."""
    return snapshot_of_bundles(repo, [perturbed_bundle(stand, mutate, recount)])
