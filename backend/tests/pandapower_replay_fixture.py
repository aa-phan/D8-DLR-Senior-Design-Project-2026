"""
Shared helper for the replay-phase tests (pandapower-solver Phase 4, plan 04-01, D-01). Not collected
by pytest (the file name does not match `*_test.py`, and nothing here has a `test_` prefix), and
follows `pandapower_study_fixture.py`'s conventions.

Nothing here is Power Systems data. Every row comes from `psse_local_pg.valid_run_rows` and
`failed_run_row` (the public, synthetic rows the PSS/E database tests use), projected to the columns
the export statement selects, and every file a test writes with these helpers goes into a throwaway
git repository under the test's `tmp_path`, never into this checkout.
"""

import csv
import datetime
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import psse_local_pg  # noqa: E402
from pandapower_job import recorded  # noqa: E402

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
