"""
Tests of the recorded-runs route of the replay (pandapower-solver Phase 4, plan 04-01: AGR-01, AGR-04,
owner decision D-01): `pandapower_job.recorded` validates an export file that the owner of the
Supabase project produced with one read-only SQL statement, writes a private snapshot, loads it back
and prints a counts-only profile.

No database, no pandapower, no network. Every file is written inside a throwaway git repository
under `tmp_path` (a `.gitignore` holding `/data/private/`) that is passed as `repo_root`, so nothing
is ever written into this checkout's real data folder. The rows are the synthetic public rows of the
PSS/E database tests (`psse_local_pg.valid_run_rows`); no test here holds a value from
`data/private/`, and the marker key is taken from the module, so this file does not match the leak
guard's shape layer.

Follows backend/tests/psse_study_job_test.py: module-level imports, plain asserts, no classes.
"""

import ast
import copy
import csv
import datetime
import io
import json
import os
import re
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
for _folder in (_BACKEND, _HERE):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

import pandapower_replay_fixture as fixture  # noqa: E402
import private_leak_scan  # noqa: E402
from pandapower_job import private, recorded  # noqa: E402

UTC = datetime.timezone.utc
FIXED_NOW = datetime.datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
HOUR_ONE = datetime.datetime(2026, 11, 18, 9, 7, 30, tzinfo=UTC)
HOUR_TWO = datetime.datetime(2026, 11, 18, 10, 7, 30, tzinfo=UTC)
HOUR_THREE = datetime.datetime(2026, 11, 18, 11, 7, 30, tzinfo=UTC)


def _incoming(repo, name="export.json"):
    return os.path.join(repo, "data", "private", "pandapower", "incoming", name)


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


def _scalars(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _scalars(item)
    elif isinstance(value, list):
        for item in value:
            yield from _scalars(item)
    elif value is not None:
        yield value


# -- tracer -----------------------------------------------------------------------------------------


def test_tracer_export_to_snapshot_to_counts(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    bundles = [
        fixture.run_bundle(1, HOUR_ONE, outcome="ok"),
        fixture.run_bundle(2, HOUR_TWO, outcome="fallback"),
        fixture.run_bundle(3, HOUR_THREE, outcome="failed"),
    ]
    document = fixture.export_document(bundles)
    export_path = fixture.write_export_json(_incoming(repo), document)

    result = recorded.ingest_export(export_path, repo_root=repo, now=FIXED_NOW)

    snapshot_path = result.path
    folder = os.path.join(repo, "data", "private", "pandapower", "snapshots")
    assert os.path.dirname(snapshot_path) == os.path.realpath(folder)
    assert os.path.isfile(snapshot_path)
    assert os.path.basename(snapshot_path) == "snapshot_20261120T120000Z.json"
    ignored = subprocess.run(
        ["git", "-C", repo, "check-ignore", "-q", "--", os.path.relpath(snapshot_path, repo)])
    assert ignored.returncode == 0

    findings = private_leak_scan.scan_paths([snapshot_path], root=repo)
    assert any(item.layer == "shape" and item.pattern == "pandapower_marker" for item in findings)

    loaded = recorded.load_snapshot(snapshot_path, repo_root=repo)
    assert loaded == result.snapshot

    ordered = recorded.by_run(loaded)
    assert [item.run["run_id"] for item in ordered] == [bundle["run"]["run_id"] for bundle in bundles]
    assert [item.run["outcome"] for item in ordered] == ["ok", "fallback", "failed"]
    assert [len(item.dispatch) for item in ordered] == [4, 4, 0]

    counted = recorded.profile(loaded, fixture.HEX_A, fixture.HEX_B)
    assert counted.runs == 3
    assert (counted.ok_runs, counted.fallback_runs, counted.failed_runs) == (1, 1, 1)
    assert counted.matching_mapping == 3 and counted.matching_case == 3
    lines = recorded.profile_lines(counted)
    assert lines
    for line in lines:
        assert any(pattern.match(line) for pattern in recorded.PROFILE_LINE_PATTERNS), line
    assert "snapshot runs: 3" in lines
    assert "snapshot runs ok: 1" in lines and "snapshot runs fallback: 1" in lines
    assert "snapshot runs failed: 1" in lines

    text = "\n".join(lines)
    for bundle in bundles:
        assert bundle["run"]["run_id"] not in text
    assert fixture.HEX_A not in text and fixture.HEX_B not in text
    for table in ("runs", "dispatch", "margins", "contingencies"):
        for row in document[table]:
            for scalar in _scalars(row):
                if isinstance(scalar, (int, float)) and not isinstance(scalar, bool):
                    assert len(str(scalar)) < 5 or str(scalar) not in text

    # Without a hash to compare the two matching lines say so, and the profile still prints.
    unchecked = recorded.profile_lines(recorded.profile(loaded))
    assert "snapshot runs matching local mapping: not checked" in unchecked
    assert "snapshot runs matching session case: not checked" in unchecked

    assert _outside_private(repo) == [".gitignore"]
    assert private.require_private(snapshot_path, repo) == snapshot_path


# -- helpers for the strict-validation matrix -------------------------------------------------------

OTHER_RUN_ID = "psse-20261118T120000Z-0000ffff"
COUNT_KEYS = recorded.COUNT_KEYS


def _bundles():
    return [
        fixture.run_bundle(1, HOUR_ONE, outcome="ok"),
        fixture.run_bundle(2, HOUR_TWO, outcome="fallback"),
        fixture.run_bundle(3, HOUR_THREE, outcome="failed"),
    ]


def _document():
    return fixture.export_document(_bundles())


def _recount(document):
    """The counts a correct export would carry for these lists."""
    document["counts"] = {
        "runs": len(document["runs"]),
        "usable_runs": sum(1 for row in document["runs"] if row["outcome"] != "failed"),
        "dispatch": len(document["dispatch"]),
        "margins": len(document["margins"]),
        "contingencies": len(document["contingencies"]),
    }
    return document


def _change(document, table, index, **changes):
    document = copy.deepcopy(document)
    document[table][index].update(changes)
    return document


def _without(document, table, index, column):
    document = copy.deepcopy(document)
    del document[table][index][column]
    return document


def _failed_run_id(document):
    return [row["run_id"] for row in document["runs"] if row["outcome"] == "failed"][0]


def _write_bytes(repo, data, name="export.json"):
    path = _incoming(repo, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def _write_json_document(repo, document, name="export.json", as_list=True):
    return fixture.write_export_json(_incoming(repo, name), document, as_list=as_list)


def _refused(callable_, *args, **kwargs):
    try:
        callable_(*args, **kwargs)
    except recorded.ExportRefused as error:
        return error
    raise AssertionError("the file was not refused")


def _ingest(repo, path):
    return recorded.ingest_export(path, repo_root=repo, now=FIXED_NOW)


def _csv_text(document, order=None, double=(), terminator="\r\n"):
    """A CSV export: the header and one row; `double` names the cells serialised twice."""
    names = list(order or recorded.EXPORT_COLUMNS)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator=terminator)
    writer.writerow(names)
    cells = []
    for name in names:
        text = json.dumps(document[name])
        cells.append(json.dumps(text) if name in double else text)
    writer.writerow(cells)
    return out.getvalue()


def _snapshot_files(repo):
    folder = os.path.join(repo, "data", "private", "pandapower", "snapshots")
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else None


# -- the input forms --------------------------------------------------------------------------------


def test_csv_export_ingests_to_the_same_snapshot_as_json(tmp_path):
    document = _document()
    json_repo = fixture.make_repo(tmp_path / "json")
    from_json = _ingest(json_repo, fixture.write_export_json(_incoming(json_repo), document))
    csv_repo = fixture.make_repo(tmp_path / "csv")
    from_csv = _ingest(csv_repo, fixture.write_export_csv(_incoming(csv_repo, "export.csv"), document))
    assert from_csv.snapshot == from_json.snapshot
    bare_repo = fixture.make_repo(tmp_path / "bare")
    from_bare = _ingest(bare_repo, fixture.write_export_json(_incoming(bare_repo), document, as_list=False))
    assert from_bare.snapshot == from_json.snapshot


def test_csv_header_order_double_serialised_cells_bom_and_crlf_are_tolerated(tmp_path):
    document = _document()
    expected = recorded.validate(document)
    order = ["contingencies", "margins", "counts", "dispatch", "runs"]
    for case, text in (
        ("order", _csv_text(document, order=order)),
        ("double", _csv_text(document, double=("runs", "counts"))),
        ("bom_and_crlf", "﻿" + _csv_text(document, terminator="\r\n") + "\r\n\r\n"),
        ("lf_and_blank_lines", _csv_text(document, terminator="\n") + "\n  \n"),
    ):
        repo = fixture.make_repo(tmp_path / case)
        path = _write_bytes(repo, text.encode("utf-8"), name="export.csv")
        assert _ingest(repo, path).snapshot == expected, case


def test_snapshot_round_trip_normalises_timestamps_once(tmp_path):
    document = _change(_document(), "runs", 0, slot_time="2026-11-18T09:00:00Z")
    repo = fixture.make_repo(tmp_path / "repo")
    result = _ingest(repo, _write_json_document(repo, document))
    assert result.snapshot.runs[0]["slot_time"] == "2026-11-18T09:00:00+00:00"
    assert recorded.load_snapshot(result.path, repo_root=repo) == result.snapshot


# -- each refusal reason, raised by a minimal bad file ----------------------------------------------


def _case_unreadable(repo, monkeypatch):
    return _refused(_ingest, repo, _incoming(repo, "missing.json"))


def _case_too_large(repo, monkeypatch):
    path = _write_json_document(repo, _document())
    monkeypatch.setattr(recorded, "MAX_EXPORT_BYTES", 10)
    return _refused(_ingest, repo, path)


def _case_not_json(repo, monkeypatch):
    return _refused(_ingest, repo, _write_bytes(repo, b"{not json"))


def _case_not_csv(repo, monkeypatch):
    header_only = ",".join(recorded.EXPORT_COLUMNS) + "\n"
    return _refused(_ingest, repo, _write_bytes(repo, header_only.encode(), name="export.csv"))


def _case_wrong_shape(repo, monkeypatch):
    document = _document()
    return _refused(_ingest, repo, _write_bytes(repo, json.dumps([document, document]).encode()))


def _case_missing_column(repo, monkeypatch):
    return _refused(_ingest, repo, _write_json_document(repo, _without(_document(), "runs", 0, "job_version")))


def _case_unknown_column(repo, monkeypatch):
    document = _document()
    document["extra"] = []
    return _refused(_ingest, repo, _write_json_document(repo, document))


def _case_bad_value(repo, monkeypatch):
    return _refused(_ingest, repo, _write_json_document(repo, _change(_document(), "runs", 0, outcome="weird")))


def _case_duplicate_run(repo, monkeypatch):
    document = _document()
    document["runs"].append(dict(document["runs"][0]))
    return _refused(_ingest, repo, _write_json_document(repo, _recount(document)))


def _case_duplicate_row(repo, monkeypatch):
    document = _document()
    document["dispatch"].append(dict(document["dispatch"][0]))
    return _refused(_ingest, repo, _write_json_document(repo, _recount(document)))


def _case_orphan_row(repo, monkeypatch):
    document = _change(_document(), "dispatch", 0, run_id=OTHER_RUN_ID)
    return _refused(_ingest, repo, _write_json_document(repo, document))


def _case_counts_mismatch(repo, monkeypatch):
    document = _document()
    del document["contingencies"][-1]
    return _refused(_ingest, repo, _write_json_document(repo, document))


def _case_bad_marker(repo, monkeypatch):
    good = _ingest(repo, _write_json_document(repo, _document()))
    with open(good.path, encoding="utf-8") as handle:
        broken = json.loads(handle.read())
    broken[recorded.REPORT_MARKER] = 2
    path = os.path.join(os.path.dirname(good.path), "snapshot_other.json")
    private.write_private_bytes(path, json.dumps(broken).encode("ascii"), repo)
    return _refused(recorded.load_snapshot, path, repo_root=repo)


REASON_CASES = {
    "unreadable": _case_unreadable,
    "too_large": _case_too_large,
    "not_json": _case_not_json,
    "not_csv": _case_not_csv,
    "wrong_shape": _case_wrong_shape,
    "missing_column": _case_missing_column,
    "unknown_column": _case_unknown_column,
    "bad_value": _case_bad_value,
    "duplicate_run": _case_duplicate_run,
    "duplicate_row": _case_duplicate_row,
    "orphan_row": _case_orphan_row,
    "counts_mismatch": _case_counts_mismatch,
    "bad_marker": _case_bad_marker,
}


def test_every_refusal_reason_has_a_minimal_bad_file():
    assert tuple(sorted(REASON_CASES)) == tuple(sorted(recorded.EXPORT_REFUSAL_REASONS))
    assert len(recorded.EXPORT_REFUSAL_REASONS) == 13


@pytest.mark.parametrize("reason", recorded.EXPORT_REFUSAL_REASONS)
def test_each_reason_is_raised_by_its_minimal_file_with_a_reason_only_message(
        reason, tmp_path, monkeypatch):
    repo = fixture.make_repo(tmp_path / "repo")
    error = REASON_CASES[reason](repo, monkeypatch)
    assert error.reason == reason
    assert str(error) == "export refused: " + reason
    assert error.args == ("export refused: " + reason,)
    assert error.__cause__ is None and error.__context__ is None
    if reason in ("too_large", "counts_mismatch"):
        assert error.hint == recorded.EXPORT_REFUSAL_HINTS[reason]
        assert "psse-%" in error.hint and "date prefix" in error.hint
        assert error.hint not in str(error)
    else:
        assert error.hint is None
    if reason != "bad_marker":
        # A refused ingest writes nothing: no snapshots folder and no file besides the export.
        assert _snapshot_files(repo) is None
        assert _outside_private(repo) == [".gitignore"]


def test_the_hints_are_two_fixed_texts_without_a_value():
    assert sorted(recorded.EXPORT_REFUSAL_HINTS) == ["counts_mismatch", "too_large"]
    for hint in recorded.EXPORT_REFUSAL_HINTS.values():
        assert isinstance(hint, str) and hint
        assert not re.search(r"[0-9a-f]{16}", hint)
        assert "data/private" not in hint


def test_a_planted_marker_in_a_cell_never_reaches_the_error(tmp_path):
    planted = "PLANTED-MARKER-q7x"
    document = _change(_document(), "runs", 0, outcome=planted, job_version=planted)
    document = _change(document, "dispatch", 0, city=planted)
    for as_list in (True, False):
        repo = fixture.make_repo(tmp_path / ("list" if as_list else "bare"))
        path = _write_json_document(repo, document, as_list=as_list)
        error = _refused(_ingest, repo, path)
        for text in (str(error), repr(error), " ".join(str(item) for item in error.args)):
            assert planted not in text
    # The same planted text as a key, as a column of a row and as a header name.
    key_document = _document()
    key_document[planted] = []
    assert planted not in str(_refused(recorded.validate, key_document))
    row_document = _document()
    row_document["runs"][0][planted] = 1
    assert planted not in str(_refused(recorded.validate, row_document))
    repo = fixture.make_repo(tmp_path / "csv")
    text = ",".join(list(recorded.EXPORT_COLUMNS) + [planted]) + "\n" + ",".join(["{}"] * 6) + "\n"
    error = _refused(_ingest, repo, _write_bytes(repo, text.encode(), name="export.csv"))
    assert planted not in str(error) and planted not in repr(error)
    # A path is not echoed either.
    missing = _refused(recorded.read_export, os.path.join(str(tmp_path), "no-such-folder-q7x", "x.json"))
    assert "no-such-folder-q7x" not in str(missing) + repr(missing)


# -- shapes -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("text, reason", [
    ("[]", "wrong_shape"),
    ("[5]", "wrong_shape"),
    ("[[1]]", "wrong_shape"),
    ('[{"counts": {}}, {"counts": {}}]', "wrong_shape"),
    ("{}", "missing_column"),
    ("{not json", "not_json"),
    ('{"counts": 1, "counts": 2}', "not_json"),
    ('[{"counts": NaN}]', "not_json"),
    ('[{"counts": Infinity}]', "not_json"),
    ("5", "not_csv"),
    ("", "not_csv"),
    ("counts,runs\n", "not_csv"),
])
def test_file_shapes(text, reason, tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    error = _refused(_ingest, repo, _write_bytes(repo, text.encode()))
    assert error.reason == reason


def test_a_hostile_nesting_depth_is_refused_as_not_json(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    assert _refused(_ingest, repo, _write_bytes(repo, b"[" * 200000)).reason == "not_json"


def test_a_file_that_is_not_utf8_is_refused_as_not_json(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    assert _refused(_ingest, repo, _write_bytes(repo, b"[\xff\xfe]")).reason == "not_json"


def test_csv_structure_refusals(tmp_path):
    document = _document()
    header = ",".join(recorded.EXPORT_COLUMNS)
    one = _csv_text(document)
    row = one.split("\r\n", 1)[1].rstrip("\r\n")
    cases = [
        ("two_rows", one + row + "\r\n", "not_csv"),
        ("duplicate_header", "counts,counts,dispatch,margins,contingencies\r\n" + row + "\r\n", "not_csv"),
        ("short_row", header + "\r\n{}\r\n", "not_csv"),
        ("cell_not_json", header + "\r\nx,x,x,x,x\r\n", "not_json"),
        ("missing_header_name", "counts,runs,dispatch,margins\r\n{},[],[],[]\r\n", "missing_column"),
        ("unknown_header_name", header + ",extra\r\n{},[],[],[],[],[]\r\n", "unknown_column"),
        ("cell_is_a_number", header + "\r\n5,5,5,5,5\r\n", "wrong_shape"),
        ("stray_quote", header + '\r\n"{"x"},[],[],[],[]\r\n', "not_csv"),
    ]
    for name, text, reason in cases:
        repo = fixture.make_repo(tmp_path / name)
        error = _refused(_ingest, repo, _write_bytes(repo, text.encode(), name="export.csv"))
        assert error.reason == reason, name


def test_the_csv_field_limit_is_restored_after_the_call(tmp_path):
    before = csv.field_size_limit()
    repo = fixture.make_repo(tmp_path / "repo")
    _ingest(repo, fixture.write_export_csv(_incoming(repo, "export.csv"), _document()))
    assert csv.field_size_limit() == before
    other = fixture.make_repo(tmp_path / "other")
    header_only = ",".join(recorded.EXPORT_COLUMNS) + "\n"
    _refused(_ingest, other, _write_bytes(other, header_only.encode(), name="export.csv"))
    assert csv.field_size_limit() == before


@pytest.mark.parametrize("mutate, reason", [
    (lambda d: d.pop("margins"), "missing_column"),
    (lambda d: d.update(extra=[]), "unknown_column"),
    (lambda d: d["counts"].pop("usable_runs"), "missing_column"),
    (lambda d: d["counts"].update(extra=1), "unknown_column"),
    (lambda d: d.update(counts=[]), "wrong_shape"),
    (lambda d: d.update(runs={}), "wrong_shape"),
    (lambda d: d.update(dispatch=[1]), "wrong_shape"),
    (lambda d: d.update(margins="none"), "wrong_shape"),
    (lambda d: d["runs"][0].pop("job_version"), "missing_column"),
    (lambda d: d["runs"][0].update(error="x"), "unknown_column"),
    (lambda d: d["dispatch"][0].pop("details"), "missing_column"),
    (lambda d: d["dispatch"][0].update(power_factor=0.9), "unknown_column"),
    (lambda d: d["margins"][0].pop("method"), "missing_column"),
    (lambda d: d["margins"][0].update(margin_pct=1.0), "unknown_column"),
    (lambda d: d["contingencies"][0].pop("unit"), "missing_column"),
    (lambda d: d["contingencies"][0].update(details={}), "unknown_column"),
])
def test_keys_must_be_exactly_the_pinned_columns(mutate, reason):
    document = _document()
    mutate(document)
    assert _refused(recorded.validate, document).reason == reason


# -- values -----------------------------------------------------------------------------------------

BAD_VALUES = [
    ("runs", "run_id", "pp-20261118T090000Z-00000001"),
    ("runs", "run_id", 5),
    ("runs", "run_id", None),
    ("runs", "slot_time", "2026-11-18T09:00:00"),
    ("runs", "slot_time", "not a time"),
    ("runs", "slot_time", 5),
    ("runs", "slot_time", None),
    ("runs", "outcome", "weird"),
    ("runs", "outcome", None),
    ("runs", "failed_stage", "weird"),
    ("runs", "failed_stage", 5),
    ("runs", "case_sha256", "AB" * 32),
    ("runs", "case_sha256", "ab" * 31),
    ("runs", "case_sha256", 5),
    ("runs", "mapping_sha256", "zz" * 32),
    ("runs", "rate_set", 5),
    ("runs", "ratings_used", []),
    ("runs", "ratings_used", "text"),
    ("runs", "n_contingencies", -1),
    ("runs", "n_contingencies", True),
    ("runs", "n_contingencies", 1.5),
    ("runs", "n_contingencies", "3"),
    ("runs", "n_contingencies_with_results", -2),
    ("runs", "job_version", None),
    ("runs", "job_version", 5),
    ("dispatch", "run_id", 5),
    ("dispatch", "city", "GOTHAM"),
    ("dispatch", "city", None),
    ("dispatch", "rating_source", "other"),
    ("dispatch", "fallback_reason", "other"),
    ("dispatch", "applied_mva", "1.5"),
    ("dispatch", "applied_mva", True),
    ("dispatch", "applied_mva", None),
    ("dispatch", "applied_amps_circuit", 1e999),
    ("dispatch", "subconductors_per_phase", -1),
    ("dispatch", "subconductors_per_phase", 1.5),
    ("dispatch", "limiting_factor", "other"),
    ("dispatch", "details", []),
    ("dispatch", "details", {"x": 1e999}),
    ("margins", "city", "GOTHAM"),
    ("margins", "method", None),
    ("margins", "min_voltage_pu", "0.9"),
    ("margins", "margin_mw", False),
    ("margins", "critical_bus", 5),
    ("margins", "details", "text"),
    ("contingencies", "contingency_id", None),
    ("contingencies", "violation_kind", "other"),
    ("contingencies", "element_type", "other"),
    ("contingencies", "element_id", None),
    ("contingencies", "city", "GOTHAM"),
    ("contingencies", "limit_value", "3"),
    ("contingencies", "observed_value", True),
    ("contingencies", "exceeded_by", 1e999),
    ("contingencies", "unit", "kV"),
]


@pytest.mark.parametrize("table, column, value", BAD_VALUES)
def test_a_bad_value_is_refused(table, column, value):
    document = _change(_document(), table, 0, **{column: value})
    assert _refused(recorded.validate, document).reason == "bad_value"


def test_nan_and_infinity_are_refused_wherever_they_arrive():
    # In a file the strict parser refuses the tokens (not_json); a value that reaches validate as a
    # Python float is refused as bad_value.
    for value in (float("nan"), float("inf"), float("-inf")):
        document = _change(_document(), "dispatch", 0, applied_mva=value)
        assert _refused(recorded.validate, document).reason == "bad_value"
        counts = _document()
        counts["counts"]["runs"] = value
        assert _refused(recorded.validate, counts).reason == "bad_value"


def test_a_bad_count_value_is_refused():
    for value in (-1, True, 1.5, "3", None):
        document = _document()
        document["counts"]["runs"] = value
        assert _refused(recorded.validate, document).reason == "bad_value"


def test_allowed_nulls_and_other_good_values_are_accepted():
    changed = _document()
    changed["runs"][0].update(
        failed_stage=None, case_sha256=None, mapping_sha256=None, rate_set=None, ratings_used=None,
        n_contingencies=None, n_contingencies_with_results=None, slot_time="2026-11-18T10:00:00+02:00")
    changed["dispatch"][0].update(fallback_reason=None, details={"note": [1, 2, {"x": None}]})
    changed["margins"][0].update(
        base_transfer_mw=None, limit_transfer_mw=None, critical_bus=None, min_voltage_pu=None, details=None)
    changed["contingencies"][0].update(
        city=None, limit_value=None, observed_value=None, exceeded_by=None, unit=None)
    snapshot = recorded.validate(changed)
    assert snapshot.runs[0]["slot_time"] == "2026-11-18T10:00:00+02:00"
    assert snapshot.contingencies[0]["unit"] is None
    # Integers are numbers too (a database writes 1825.0 as 1825).
    changed["dispatch"][0]["applied_mva"] = 1825
    assert recorded.validate(changed).dispatch[0]["applied_mva"] == 1825


# -- uniqueness, orphans, counts --------------------------------------------------------------------


def test_duplicate_runs_and_rows_are_refused():
    document = _document()
    document["runs"].append(dict(document["runs"][1]))
    assert _refused(recorded.validate, _recount(document)).reason == "duplicate_run"
    for table in ("dispatch", "margins", "contingencies"):
        document = _document()
        document[table].append(dict(document[table][0]))
        assert _refused(recorded.validate, _recount(document)).reason == "duplicate_row", table
    # Two contingency rows on one id are fine when the element differs.
    document = _document()
    document["contingencies"].append(dict(document["contingencies"][0], element_id="999-998-1"))
    assert recorded.validate(_recount(document)).counts["contingencies"] == 5


def test_orphan_rows_are_refused():
    failed = _failed_run_id(_document())
    for table in ("dispatch", "margins", "contingencies"):
        document = _change(_document(), table, 0, run_id=OTHER_RUN_ID)
        assert _refused(recorded.validate, document).reason == "orphan_row", table
        document = _change(_document(), table, 0, run_id=failed)
        assert _refused(recorded.validate, document).reason == "orphan_row", table


def test_a_truncated_export_is_refused_by_its_own_counts():
    for table in ("runs", "dispatch", "margins", "contingencies"):
        document = _document()
        del document[table][-1]
        reason = _refused(recorded.validate, document).reason
        # A run dropped from the list leaves its rows without a run; a row dropped leaves the counts.
        assert reason in ("counts_mismatch", "orphan_row"), table
    document = _document()
    del document["contingencies"][-1]
    assert _refused(recorded.validate, document).reason == "counts_mismatch"
    for key in COUNT_KEYS:
        document = _document()
        document["counts"][key] += 1
        assert _refused(recorded.validate, document).reason == "counts_mismatch", key


# -- the two caps -----------------------------------------------------------------------------------


def test_the_caps_have_their_stated_values():
    assert recorded.MAX_EXPORT_BYTES == 33554432
    assert recorded.MAX_SNAPSHOT_BYTES == 67108864
    assert recorded.MAX_SNAPSHOT_BYTES == private_leak_scan.MAX_PRIVATE_BYTES
    assert recorded.MAX_SNAPSHOT_BYTES == 2 * recorded.MAX_EXPORT_BYTES


def test_a_file_one_byte_over_the_export_cap_is_refused_and_one_at_the_cap_is_read(
        tmp_path, monkeypatch):
    repo = fixture.make_repo(tmp_path / "repo")
    path = _write_json_document(repo, _document())
    size = os.path.getsize(path)
    monkeypatch.setattr(recorded, "MAX_EXPORT_BYTES", size)
    assert recorded.read_export(path)["counts"]["runs"] == 3
    monkeypatch.setattr(recorded, "MAX_EXPORT_BYTES", size - 1)
    error = _refused(recorded.read_export, path)
    assert error.reason == "too_large" and error.hint == recorded.EXPORT_REFUSAL_HINTS["too_large"]


def test_a_snapshot_over_its_cap_is_refused_on_write_and_on_load(tmp_path, monkeypatch):
    repo = fixture.make_repo(tmp_path / "repo")
    good = _ingest(repo, _write_json_document(repo, _document()))
    size = os.path.getsize(good.path)
    monkeypatch.setattr(recorded, "MAX_SNAPSHOT_BYTES", size)
    assert recorded.load_snapshot(good.path, repo_root=repo) == good.snapshot
    monkeypatch.setattr(recorded, "MAX_SNAPSHOT_BYTES", size - 1)
    assert _refused(recorded.load_snapshot, good.path, repo_root=repo).reason == "too_large"
    other = fixture.make_repo(tmp_path / "other")
    other_path = _write_json_document(other, _document())
    assert _refused(_ingest, other, other_path).reason == "too_large"
    assert _snapshot_files(other) is None


# -- the snapshot loader re-validates ---------------------------------------------------------------


def _edited_snapshot(good, edit, name, repo):
    with open(good.path, encoding="utf-8") as handle:
        document = json.loads(handle.read())
    edit(document)
    path = os.path.join(os.path.dirname(good.path), name)
    private.write_private_bytes(path, json.dumps(document).encode("ascii"), repo)
    return path


def test_the_loader_checks_the_marker_the_kind_the_version_and_every_row(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    good = _ingest(repo, _write_json_document(repo, _document()))
    marker = recorded.REPORT_MARKER

    def drop_marker(d):
        del d[marker]

    cases = [
        ("no_marker", drop_marker, "bad_marker"),
        ("marker_two", lambda d: d.update({marker: 2}), "bad_marker"),
        ("marker_true", lambda d: d.update({marker: True}), "bad_marker"),
        ("kind", lambda d: d.update(kind="other"), "bad_marker"),
        ("version", lambda d: d.update(snapshot_version=2), "bad_marker"),
        ("bad_value", lambda d: d["runs"][0].update(outcome="weird"), "bad_value"),
        ("unknown_key", lambda d: d.update(extra=1), "unknown_column"),
        ("missing_part", lambda d: d.pop("margins"), "missing_column"),
        ("counts", lambda d: d["counts"].update(runs=9), "counts_mismatch"),
        ("orphan", lambda d: d["dispatch"][0].update(run_id=OTHER_RUN_ID), "orphan_row"),
    ]
    for name, edit, reason in cases:
        path = _edited_snapshot(good, edit, "snapshot_%s.json" % name, repo)
        assert _refused(recorded.load_snapshot, path, repo_root=repo).reason == reason, name
    folder = os.path.dirname(good.path)
    plain = os.path.join(folder, "snapshot_list.json")
    private.write_private_bytes(plain, b"[1]", repo)
    assert _refused(recorded.load_snapshot, plain, repo_root=repo).reason == "wrong_shape"
    broken = os.path.join(folder, "snapshot_broken.json")
    private.write_private_bytes(broken, b"{", repo)
    assert _refused(recorded.load_snapshot, broken, repo_root=repo).reason == "not_json"
    assert _refused(recorded.load_snapshot, os.path.join(folder, "gone.json"),
                    repo_root=repo).reason == "unreadable"


def test_the_loader_refuses_a_path_outside_the_private_folder(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    stray = os.path.join(repo, "stray.json")
    with open(stray, "w", encoding="utf-8") as handle:
        handle.write("{}")
    with pytest.raises(private.PrivatePathRefused) as info:
        recorded.load_snapshot(stray, repo_root=repo)
    assert info.value.reason == "outside_private_root"


# -- ingest never writes on a refusal ---------------------------------------------------------------


def test_two_ingests_in_the_same_second_are_refused_by_the_private_path_guard(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    path = _write_json_document(repo, _document())
    first = _ingest(repo, path)
    with open(first.path, "rb") as handle:
        before = handle.read()
    with pytest.raises(private.PrivatePathRefused) as info:
        _ingest(repo, path)
    assert info.value.reason == "exists"
    with open(first.path, "rb") as handle:
        assert handle.read() == before
    assert len(_snapshot_files(repo)) == 1
    later = recorded.ingest_export(path, repo_root=repo, now=FIXED_NOW + datetime.timedelta(seconds=1))
    assert later.snapshot == first.snapshot and len(_snapshot_files(repo)) == 2


def test_an_export_outside_the_private_folder_is_refused(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    stray = fixture.write_export_json(os.path.join(repo, "elsewhere", "export.json"), _document())
    with pytest.raises(private.PrivatePathRefused) as info:
        _ingest(repo, stray)
    assert info.value.reason == "outside_private_root"
    assert _snapshot_files(repo) is None


def test_a_snapshots_folder_outside_the_private_folder_is_refused_before_anything_is_created(tmp_path):
    repo = fixture.make_repo(tmp_path / "repo")
    path = _write_json_document(repo, _document())
    elsewhere = os.path.join(repo, "snapshots_here")
    with pytest.raises(private.PrivatePathRefused) as info:
        recorded.ingest_export(path, repo_root=repo, snapshots_dir=elsewhere, now=FIXED_NOW)
    assert info.value.reason == "outside_private_root"
    assert not os.path.exists(elsewhere)


# -- complete ---------------------------------------------------------------------------------------


def _recorded_runs(violations=2):
    bundles = [
        fixture.run_bundle(1, HOUR_ONE, outcome="ok", violations=violations),
        fixture.run_bundle(2, HOUR_TWO, outcome="failed"),
    ]
    return recorded.by_run(recorded.validate(fixture.export_document(bundles)))


def test_complete_is_true_for_a_full_usable_run():
    usable, failed = _recorded_runs()
    assert recorded.complete(usable) is True
    assert recorded.complete(failed) is False
    clean = _recorded_runs(violations=0)[0]
    assert clean.run["n_contingencies_with_results"] == 0 and recorded.complete(clean) is True


def test_complete_is_false_for_a_missing_city_a_wrong_count_and_a_failed_run():
    usable = _recorded_runs()[0]
    assert recorded.complete(usable._replace(dispatch=usable.dispatch[1:])) is False
    assert recorded.complete(usable._replace(margins=usable.margins[:-1])) is False
    assert recorded.complete(usable._replace(dispatch=usable.dispatch[:1] * 4)) is False
    assert recorded.complete(usable._replace(contingencies=usable.contingencies[:1])) is False
    assert recorded.complete(usable._replace(contingencies=[])) is False
    wrong = usable._replace(run=dict(usable.run, n_contingencies_with_results=5))
    assert recorded.complete(wrong) is False
    unknown = usable._replace(run=dict(usable.run, n_contingencies_with_results=None))
    assert recorded.complete(unknown) is False
    failed_outcome = usable._replace(run=dict(usable.run, outcome="failed"))
    assert recorded.complete(failed_outcome) is False


def test_distinct_contingency_ids_are_counted_not_rows():
    usable = _recorded_runs()[0]
    twin = dict(usable.contingencies[0], violation_kind="voltage_low", element_type="bus",
                element_id="777", unit="pu")
    # Three rows, two distinct ids, two recorded: complete.
    assert recorded.complete(usable._replace(contingencies=usable.contingencies + [twin])) is True


# -- constants and the import boundary --------------------------------------------------------------


def _assigned_text(path, name):
    """The text a module-level `NAME = "a" + "b"` assigns, read without importing the module."""
    def value(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return value(node.left) + value(node.right)
        raise AssertionError("not a text expression")

    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), path)
    for node in tree.body:
        if isinstance(node, ast.Assign) and [t.id for t in node.targets if isinstance(t, ast.Name)] == [name]:
            return value(node.value)
    raise AssertionError("no such assignment")


def test_the_report_marker_equals_the_one_the_owner_commands_use():
    cli_source = os.path.join(_BACKEND, "pandapower_job", "cli.py")
    assert recorded.REPORT_MARKER == _assigned_text(cli_source, "REPORT_MARKER")
    with open(recorded.__file__, encoding="utf-8") as handle:
        assert recorded.REPORT_MARKER not in handle.read()


def test_the_column_tuples_are_ordered_subsets_of_the_stored_columns():
    from psse_job import contract
    for mine, stored in (
        (recorded.RUN_COLUMNS, contract.PSSE_RUN_COLUMNS),
        (recorded.DISPATCH_COLUMNS, contract.DISPATCH_COLUMNS),
        (recorded.MARGIN_COLUMNS, contract.MARGIN_COLUMNS),
        (recorded.CONTINGENCY_COLUMNS, contract.CONTINGENCY_COLUMNS),
    ):
        assert all(column in stored for column in mine)
        assert [column for column in stored if column in mine] == list(mine)
    for never_read in ("error", "ratings_read_error", "case_id"):
        assert never_read not in recorded.RUN_COLUMNS


_FORBIDDEN_TOP = frozenset({
    "psycopg", "psycopg2", "psycopg_pool", "asyncpg", "pg8000", "sqlalchemy", "sqlite3", "supabase",
    "postgrest", "socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx", "aiohttp",
    "ftplib", "smtplib", "subprocess", "multiprocessing", "asyncio", "pandapower"})
_FORBIDDEN_WRITER_SIDE = frozenset({
    "psse_job.writer", "psse_job.job", "psse_job.gaps", "psse_job.credcheck", "psse_job.launcher",
    "psse_job.probe"})


def _import_problems(source, filename="planted.py"):
    """One problem per import of a database driver, a network or process module, or a PSS/E
    writer-side module, anywhere in the file (functions and handlers too)."""
    problems = []
    for node in ast.walk(ast.parse(source, filename)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names = [base] + [base + "." + alias.name for alias in node.names]
        for name in names:
            if name.split(".")[0] in _FORBIDDEN_TOP or name in _FORBIDDEN_WRITER_SIDE:
                problems.append("%s:%d imports %s" % (filename, node.lineno, name))
    return problems


def test_recorded_imports_no_driver_no_network_no_process_and_no_writer_side_module():
    with open(recorded.__file__, encoding="utf-8") as handle:
        assert _import_problems(handle.read(), "recorded.py") == []


def test_the_import_pin_flags_planted_imports():
    for text in (
        "import psycopg\n",
        "def f():\n    import psycopg2\n",
        "from psse_job import writer\n",
        "from psse_job.writer import connect\n",
        "import psse_job.job\n",
        "try:\n    pass\nexcept ImportError:\n    import socket\n",
        "from urllib import request\n",
        "import subprocess\n",
    ):
        assert _import_problems(text), text
    clean = "import json\nfrom psse_job import constants\nfrom pandapower_job import private\n"
    assert _import_problems(clean) == []


# -- the owner's export statement (text tier; the database tier is pandapower_replay_pg_test.py) -----

_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
EXPORT_SQL = os.path.join(_ROOT, "supabase", "ops", "export_psse_runs_for_replay.sql")
RESULT_TABLES = ("psse_contingency_result", "psse_dispatched_capacity", "psse_run", "psse_voltage_margin")


def _sql_raw():
    with open(EXPORT_SQL, encoding="utf-8") as handle:
        return handle.read()


def _sql_code():
    """The file with every `--` comment removed."""
    return "\n".join(line.split("--", 1)[0] for line in _sql_raw().splitlines())


def _sql_comments():
    return "\n".join(line.split("--", 1)[1] for line in _sql_raw().splitlines() if "--" in line)


def _squeeze(text):
    return re.sub(r"\s+", " ", text).strip()


def test_text_export_is_one_read_only_select():
    code = _sql_code()
    # String literals are blanked first: a pattern or a default may hold a word that is no keyword.
    bare = re.sub(r"'(?:[^']|'')*'", "''", code)
    statements = [part.strip() for part in bare.split(";") if part.strip()]
    assert len(statements) == 1
    assert bare.rstrip().endswith(";")
    statement = statements[0].lower()
    assert re.match(r"with\b", statement)
    for word in ("insert", "update", "delete", "alter", "drop", "create", "grant", "revoke",
                 "truncate", "copy", "call", "execute", "vacuum"):
        assert not re.search(r"\b%s\b" % word, statement), word


def test_text_export_reads_only_the_four_result_tables_without_a_solver_column():
    raw = _sql_raw()
    code = _sql_code()
    assert sorted(re.findall(r"\bfrom\s+public\.(\w+)", code)) == sorted(RESULT_TABLES)
    # The word solver appears nowhere, comments included: the file works before and after the
    # migration that adds the column.
    assert "solver" not in raw.lower()
    assert "like 'psse-%'" in code
    assert "outcome in ('ok', 'fallback')" in code
    assert code.count("where run_id in (select run_id from usable)") == 3
    for never_read in ("error", "ratings_read_error", "case_id", "started_at", "finished_at"):
        assert not re.search(r"\b%s\b" % never_read, code), never_read


def test_text_export_selects_exactly_the_pinned_columns():
    code = _squeeze(_sql_code())
    pinned = (
        ("runs", recorded.RUN_COLUMNS),
        ("dispatch", recorded.DISPATCH_COLUMNS),
        ("margins", recorded.MARGIN_COLUMNS),
        ("contingencies", recorded.CONTINGENCY_COLUMNS),
    )
    for name, columns in pinned:
        found = re.search(r"\b%s as \( select (.*?) from public\." % name, code)
        assert found, name
        assert tuple(part.strip() for part in found.group(1).split(",")) == columns, name
    final = code.split(") select ", 1)[1]
    assert tuple(re.findall(r"\bas (counts|runs|dispatch|margins|contingencies)\b", final)) == \
        recorded.EXPORT_COLUMNS
    assert final.count("jsonb_agg(") == 4
    assert final.count("jsonb_build_object(") == 1
    assert final.count("coalesce(") == 4
    assert final.count("'[]'::jsonb") == 4
    for key in recorded.COUNT_KEYS:
        assert "'%s'," % key in final
    # One jsonb_agg per line of the file (the acceptance check counts lines).
    assert sum(1 for line in _sql_raw().splitlines() if "jsonb_agg" in line) == 4


def test_text_export_header_tells_the_owner_what_to_do():
    header = _squeeze(_sql_comments()).lower()
    for phrase in (
        "read-only",
        "changes nothing",
        "never applied by the supabase cli",
        "sql editor",
        "private channel",
        "do not paste the result",
        "first export should be narrow",
        "date prefix",
        "'psse-%'",
        "data/private/pandapower/incoming/",
        "that migration may not be applied to the live project yet",
        "cut short",
    ):
        assert phrase in header, phrase
    assert "jsonb_agg" not in header
