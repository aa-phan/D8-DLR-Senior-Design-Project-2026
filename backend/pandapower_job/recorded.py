"""
The recorded PSS/E runs as the replay reads them (pandapower-solver Phase 4, plan 04-01: AGR-01,
AGR-04, owner decision D-01).

The route. Nothing in this phase connects to a database. The owner of the Supabase project runs one
read-only SQL export (`supabase/ops/export_psse_runs_for_replay.sql`) in the SQL editor and sends
the file. `ingest_export` validates the file and writes a private snapshot under `data/private/`;
the replay of the later plans reads only that snapshot, through `load_snapshot`. A direct read-only
connection or a SELECT-only role can replace the export step later without changing the snapshot
format or anything that reads it (D-01 is reversible). This module imports no database driver, no
network module and no writer-side module of the PSS/E job (`psse_job.writer`, `job`, `gaps`,
`credcheck`, `launcher`, `probe`); a test walks every import to pin that.

What is trusted. Nothing. The export file travels outside git and is untrusted input, and so is a
snapshot read back from disk. Both go through the same `validate`: exactly the five top-level keys,
exactly the pinned columns of each row, a rule per column (closed vocabularies from
`psse_job.constants`, finite numbers, lowercase 64-character hashes, timestamps with an offset), the
uniqueness and orphan rules, and the database-computed `counts` equal to the parsed row counts (so a
truncated file is refused). One damaged run is not a damaged file: `complete` tells the replay to
exclude a run whose own rows are not a full result set.

What is refused, and how. Every refusal is an `ExportRefused` whose `reason` is one word from
`EXPORT_REFUSAL_REASONS`. The message is `export refused: REASON` and never carries a cell, a key,
an id, a hash or a path; the exception is raised outside any except block, so no earlier error is
chained to it. `hint` is a fixed sentence for the two reasons the owner can act on (a file that is
too large or was cut short: narrow the run-id prefix and run the export again) and None otherwise.
A refused ingest writes nothing, and it checks everything before it creates a folder or a file.

Where files go. The snapshot is written only through `pandapower_job.private` (inside the
git-ignored `data/private/`, owner-only, never overwritten) and carries the report marker key, so
the leak guard's shape layer flags a stray copy. `repo_root` is a parameter everywhere so a test can
point the guard at a throwaway git repository.

The two size caps. One stored run is tens of kilobytes (about 60 to 80 violation rows and eight
detail objects on the public fixture; an estimate for the real corpus, which held 19 runs when this
was written) and at most about 100 KB, so `MAX_EXPORT_BYTES`, 32 MiB, admits roughly 300 or more
runs, which is weeks of hourly runs (24 a day). The snapshot is written with indentation and is
about one and a half to two times the export, so `MAX_SNAPSHOT_BYTES` is twice as large, 64 MiB; it
equals the leak scanner's per-file limit for deriving needles (`private_leak_scan.MAX_PRIVATE_BYTES`),
so a snapshot at the cap is still fully scanned. A larger file is refused as `too_large` rather
than read.

What is printed. `profile_lines` prints counts through a closed vocabulary (`PROFILE_LINE_PATTERNS`):
runs by outcome, rows per table, how many distinct mapping hashes, case hashes and job versions the
runs carry, and how many runs match a given mapping hash and case hash. It cannot carry an id, a
hash or a figure.

Python 3.12 only (`datetime.fromisoformat` accepts an offset and a trailing Z); the laptop-side
`psse_job` package keeps its own rules.
"""

import collections
import csv
import datetime
import io
import json
import math
import os
import re

from psse_job import constants
from pandapower_job import private

# The same literal as pandapower_job.cli.REPORT_MARKER, built from two pieces so this source never
# holds it whole (a test asserts the two are equal).
REPORT_MARKER = "pandapower_job_" + "report"
SNAPSHOT_KIND = "recorded_runs"
SNAPSHOT_VERSION = 1

MAX_EXPORT_BYTES = 33554432      # 32 MiB, see the module docstring
MAX_SNAPSHOT_BYTES = 67108864    # 64 MiB, equal to private_leak_scan.MAX_PRIVATE_BYTES

# The five columns of the one exported row, in order.
EXPORT_COLUMNS = ("counts", "runs", "dispatch", "margins", "contingencies")
COUNT_KEYS = ("runs", "usable_runs", "dispatch", "margins", "contingencies")

# The columns of each row type, in the order the export statement selects them; each tuple is a
# subset of the matching psse_job.contract tuple, in the same relative order. `error`,
# `ratings_read_error` and `case_id` are never read.
RUN_COLUMNS = (
    "run_id", "slot_time", "outcome", "failed_stage", "case_sha256", "mapping_sha256", "rate_set",
    "ratings_used", "n_contingencies", "n_contingencies_with_results", "job_version",
)
DISPATCH_COLUMNS = (
    "run_id", "city", "rating_source", "fallback_reason", "applied_amps_per_conductor",
    "subconductors_per_phase", "applied_amps_circuit", "line_voltage_kv", "applied_mva",
    "voltage_limit_mva", "dispatched_mva", "limiting_factor", "details",
)
MARGIN_COLUMNS = (
    "run_id", "city", "method", "base_transfer_mw", "limit_transfer_mw", "margin_mw",
    "voltage_limit_mva", "critical_bus", "min_voltage_pu", "details",
)
CONTINGENCY_COLUMNS = (
    "run_id", "contingency_id", "violation_kind", "element_type", "element_id", "city",
    "limit_value", "observed_value", "exceeded_by", "unit",
)

# Every reason a file can be refused for. bad_marker belongs to the snapshot loader only.
EXPORT_REFUSAL_REASONS = (
    "unreadable", "too_large", "not_json", "not_csv", "wrong_shape", "missing_column",
    "unknown_column", "bad_value", "duplicate_run", "duplicate_row", "orphan_row",
    "counts_mismatch", "bad_marker",
)

_NARROW_HINT = (
    "narrow the run-id pattern psse-% in the export file to a date prefix such as psse-202611% "
    "and run the export again")
# Fixed sentences, no value: the two reasons the owner can act on.
EXPORT_REFUSAL_HINTS = {"too_large": _NARROW_HINT, "counts_mismatch": _NARROW_HINT}

_NUMBER = r"[0-9]{1,9}"
# The only lines profile_lines prints: words from fixed sets, numbers of one to nine digits.
PROFILE_LINE_PATTERNS = (
    re.compile(r"snapshot runs: " + _NUMBER + r"\Z"),
    re.compile(r"snapshot runs (?:ok|fallback|failed): " + _NUMBER + r"\Z"),
    re.compile(r"snapshot rows (?:dispatch|margins|contingencies): " + _NUMBER + r"\Z"),
    re.compile(r"snapshot distinct (?:mapping hashes|case hashes|job versions): " + _NUMBER + r"\Z"),
    re.compile(r"snapshot runs matching local mapping: (?:" + _NUMBER + r"|not checked)\Z"),
    re.compile(r"snapshot runs matching session case: (?:" + _NUMBER + r"|not checked)\Z"),
)


class ExportRefused(ValueError):
    """An export or snapshot file is refused. `reason` is one of EXPORT_REFUSAL_REASONS; `hint` is a
    fixed sentence for too_large and counts_mismatch and None otherwise. The message holds the
    reason word only."""

    def __init__(self, reason):
        if reason not in EXPORT_REFUSAL_REASONS:
            raise ValueError("not a refusal reason")
        self.reason = reason
        self.hint = EXPORT_REFUSAL_HINTS.get(reason)
        ValueError.__init__(self, "export refused: %s" % reason)


Snapshot = collections.namedtuple("Snapshot", ["runs", "dispatch", "margins", "contingencies", "counts"])
RecordedRun = collections.namedtuple("RecordedRun", ["run", "dispatch", "margins", "contingencies"])
IngestResult = collections.namedtuple("IngestResult", ["path", "snapshot"])
Profile = collections.namedtuple(
    "Profile",
    ["runs", "ok_runs", "fallback_runs", "failed_runs", "dispatch_rows", "margin_rows",
     "contingency_rows", "distinct_mappings", "distinct_cases", "distinct_job_versions",
     "matching_mapping", "matching_case"])

_TABLES = (
    ("runs", RUN_COLUMNS), ("dispatch", DISPATCH_COLUMNS), ("margins", MARGIN_COLUMNS),
    ("contingencies", CONTINGENCY_COLUMNS))


# -- strict JSON ------------------------------------------------------------------------------------


def _strict_pairs(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate key")
        seen[key] = value
    return seen


def _refuse_constant(name):
    raise ValueError("non-finite number")


def _parse_json(text):
    """(True, value) for strict JSON (no NaN, no infinity, no duplicate key), else (False, None)."""
    try:
        return True, json.loads(text, parse_constant=_refuse_constant, object_pairs_hook=_strict_pairs)
    except (ValueError, RecursionError):
        return False, None


def _read_bytes(path, cap):
    """(None, bytes) or (reason, None); at most `cap` bytes are accepted."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(cap + 1)
    except (OSError, TypeError, ValueError):
        return "unreadable", None
    if len(data) > cap:
        return "too_large", None
    return None, data


# -- reading the export -----------------------------------------------------------------------------


def _json_parts(text):
    """(None, parts) or (reason, None) for the text of a JSON export."""
    ok, value = _parse_json(text)
    if not ok:
        return "not_json", None
    if isinstance(value, list):
        if len(value) == 1 and isinstance(value[0], dict):
            return None, value[0]
        return "wrong_shape", None
    if isinstance(value, dict):
        return None, value
    return "wrong_shape", None


def _csv_rows(text):
    """The non-blank rows of CSV text, or None when the text is not well-formed CSV. The csv field
    size limit is raised for the call and restored afterwards."""
    previous = csv.field_size_limit(MAX_EXPORT_BYTES + 1)
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        return [row for row in reader if any(cell.strip() for cell in row)]
    except csv.Error:
        return None
    finally:
        csv.field_size_limit(previous)


def _csv_cell(cell):
    """(True, value) for one cell of JSON text; a cell that is a JSON string holding JSON text (a
    value that was serialised twice) is unwrapped once."""
    ok, value = _parse_json(cell)
    if ok and isinstance(value, str):
        ok, value = _parse_json(value)
    return ok, value


def _csv_parts(text):
    """(None, parts) or (reason, None) for the text of a CSV export: a header of the five column
    names in any order and exactly one data row whose cells are JSON text."""
    rows = _csv_rows(text)
    if rows is None or len(rows) != 2:
        return "not_csv", None
    names = [cell.strip() for cell in rows[0]]
    if len(set(names)) != len(names):
        return "not_csv", None
    if any(column not in names for column in EXPORT_COLUMNS):
        return "missing_column", None
    if any(name not in EXPORT_COLUMNS for name in names):
        return "unknown_column", None
    if len(rows[1]) != len(names):
        return "not_csv", None
    parts = {}
    for name, cell in zip(names, rows[1]):
        ok, value = _csv_cell(cell)
        if not ok:
            return "not_json", None
        parts[name] = value
    return None, parts


def _read_export(path):
    reason, data = _read_bytes(path, MAX_EXPORT_BYTES)
    if reason is not None:
        return reason, None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "not_json", None
    if text.lstrip()[:1] in ("[", "{"):
        return _json_parts(text)
    return _csv_parts(text)


def read_export(path):
    """
    The parsed content of an export file (the parts, not yet validated). Two forms, told apart by
    the first non-blank character (an opening bracket or brace means JSON, anything else CSV): JSON
    is a one-element list holding the object, or the bare object; CSV is a header of the five column
    names in any order and exactly one data row, each cell JSON text. A byte-order mark and CRLF
    line ends are tolerated. Strict parsing (no NaN, infinity or duplicate key), at most
    MAX_EXPORT_BYTES. ExportRefused otherwise (reasons unreadable, too_large, not_json, not_csv,
    wrong_shape, missing_column, unknown_column).
    """
    reason, parts = _read_export(path)
    if reason is not None:
        raise ExportRefused(reason)
    return parts


# -- validating -------------------------------------------------------------------------------------


# One rule per column. A rule returns the normalised value, or _BAD. The rules are functions of the
# value alone; the closed lists come from psse_job.constants, which the schema's CHECK lists equal.
_BAD = object()
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RUN_ID = re.compile(r"psse-[0-9A-Za-z._-]{1,100}\Z")
_MAX_TEXT = 1000
_MAX_INTEGER = 2 ** 63 - 1
_MAX_MAGNITUDE = 10 ** 300


def _is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_count(value):
    return _is_integer(value) and 0 <= value <= _MAX_INTEGER


def _is_number(value):
    """A finite number that is not a boolean (an integer is a number: 1825.0 may be stored as 1825)."""
    if _is_integer(value):
        return abs(value) < _MAX_MAGNITUDE
    return isinstance(value, float) and math.isfinite(value)


def _finite_tree(value):
    """True when a JSON value holds no non-finite number (iterative: no recursion limit)."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, float):
            if not math.isfinite(item):
                return False
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return True


def _rule_text(value):
    return value if isinstance(value, str) and 0 < len(value) <= _MAX_TEXT else _BAD


def _rule_nullable_text(value):
    return value if value is None or (isinstance(value, str) and len(value) <= _MAX_TEXT) else _BAD


def _rule_run_id(value):
    return value if isinstance(value, str) and _RUN_ID.match(value) else _BAD


def _rule_hash(value):
    return value if value is None or (isinstance(value, str) and _HEX.match(value)) else _BAD


def _rule_time(value):
    """An ISO timestamp with an offset, normalised to `datetime.isoformat()` text."""
    if not isinstance(value, str):
        return _BAD
    try:
        moment = datetime.datetime.fromisoformat(value)
    except ValueError:
        return _BAD
    if moment.tzinfo is None or moment.utcoffset() is None:
        return _BAD
    return moment.isoformat()


def _rule_count(value):
    return value if _is_count(value) else _BAD


def _rule_nullable_count(value):
    return value if value is None or _is_count(value) else _BAD


def _rule_number(value):
    return value if _is_number(value) else _BAD


def _rule_nullable_number(value):
    return value if value is None or _is_number(value) else _BAD


def _rule_object(value):
    """A JSON object or None, without a non-finite number inside."""
    if value is None or (isinstance(value, dict) and _finite_tree(value)):
        return value
    return _BAD


def _rule_member(allowed, nullable=False):
    def rule(value):
        if value is None:
            return None if nullable else _BAD
        return value if isinstance(value, str) and value in allowed else _BAD
    return rule


_RULES = {
    "runs": {
        "run_id": _rule_run_id,
        "slot_time": _rule_time,
        "outcome": _rule_member(constants.OUTCOMES),
        "failed_stage": _rule_member(constants.FAILED_STAGES, True),
        "case_sha256": _rule_hash,
        "mapping_sha256": _rule_hash,
        "rate_set": _rule_nullable_text,
        "ratings_used": _rule_object,
        "n_contingencies": _rule_nullable_count,
        "n_contingencies_with_results": _rule_nullable_count,
        "job_version": _rule_text,
    },
    "dispatch": {
        "run_id": _rule_run_id,
        "city": _rule_member(constants.CITIES),
        "rating_source": _rule_member(constants.SOURCES),
        "fallback_reason": _rule_member(constants.FALLBACK_REASONS, True),
        "applied_amps_per_conductor": _rule_number,
        "subconductors_per_phase": _rule_count,
        "applied_amps_circuit": _rule_number,
        "line_voltage_kv": _rule_number,
        "applied_mva": _rule_number,
        "voltage_limit_mva": _rule_number,
        "dispatched_mva": _rule_number,
        "limiting_factor": _rule_member(constants.LIMITING_FACTORS),
        "details": _rule_object,
    },
    "margins": {
        "run_id": _rule_run_id,
        "city": _rule_member(constants.CITIES),
        "method": _rule_text,
        "base_transfer_mw": _rule_nullable_number,
        "limit_transfer_mw": _rule_nullable_number,
        "margin_mw": _rule_number,
        "voltage_limit_mva": _rule_number,
        "critical_bus": _rule_nullable_text,
        "min_voltage_pu": _rule_nullable_number,
        "details": _rule_object,
    },
    "contingencies": {
        "run_id": _rule_run_id,
        "contingency_id": _rule_text,
        "violation_kind": _rule_member(constants.VIOLATION_KINDS),
        "element_type": _rule_member(constants.ELEMENT_TYPES),
        "element_id": _rule_text,
        "city": _rule_member(constants.CITIES, True),
        "limit_value": _rule_nullable_number,
        "observed_value": _rule_nullable_number,
        "exceeded_by": _rule_nullable_number,
        "unit": _rule_member(constants.RESULT_UNITS, True),
    },
}


def _first_duplicate(tables):
    """The refusal reason of the first duplicate (a run twice, a row twice), else None."""
    seen = set()
    for row in tables["runs"]:
        if row["run_id"] in seen:
            return "duplicate_run"
        seen.add(row["run_id"])
    for name in ("dispatch", "margins"):
        seen = set()
        for row in tables[name]:
            key = (row["run_id"], row["city"])
            if key in seen:
                return "duplicate_row"
            seen.add(key)
    seen = set()
    for row in tables["contingencies"]:
        key = (row["run_id"], row["contingency_id"], row["violation_kind"], row["element_id"])
        if key in seen:
            return "duplicate_row"
        seen.add(key)
    return None


def _validate(parts):
    """(None, Snapshot) or (reason, None)."""
    if not isinstance(parts, dict):
        return "wrong_shape", None
    if any(name not in parts for name in EXPORT_COLUMNS):
        return "missing_column", None
    if any(name not in EXPORT_COLUMNS for name in parts):
        return "unknown_column", None
    counts = parts["counts"]
    if not isinstance(counts, dict):
        return "wrong_shape", None
    if any(name not in counts for name in COUNT_KEYS):
        return "missing_column", None
    if any(name not in COUNT_KEYS for name in counts):
        return "unknown_column", None
    if not all(_is_count(counts[name]) for name in COUNT_KEYS):
        return "bad_value", None
    tables = {}
    for name, columns in _TABLES:
        rows = parts[name]
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            return "wrong_shape", None
        rules = _RULES[name]
        clean_rows = []
        for row in rows:
            if any(column not in row for column in columns):
                return "missing_column", None
            if any(column not in columns for column in row):
                return "unknown_column", None
            clean = {}
            for column in columns:
                value = rules[column](row[column])
                if value is _BAD:
                    return "bad_value", None
                clean[column] = value
            clean_rows.append(clean)
        tables[name] = clean_rows
    reason = _first_duplicate(tables)
    if reason is not None:
        return reason, None
    usable_ids = set(row["run_id"] for row in tables["runs"] if row["outcome"] != "failed")
    for name in ("dispatch", "margins", "contingencies"):
        if any(row["run_id"] not in usable_ids for row in tables[name]):
            return "orphan_row", None
    expected = {
        "runs": len(tables["runs"]), "usable_runs": len(usable_ids),
        "dispatch": len(tables["dispatch"]), "margins": len(tables["margins"]),
        "contingencies": len(tables["contingencies"])}
    if dict(counts) != expected:
        return "counts_mismatch", None
    return None, Snapshot(
        tables["runs"], tables["dispatch"], tables["margins"], tables["contingencies"], expected)


def validate(parts):
    """
    A Snapshot from the five parts of an export (or of a snapshot file), or ExportRefused with one
    reason word. See the module docstring for what is checked.
    """
    reason, snapshot = _validate(parts)
    if reason is not None:
        raise ExportRefused(reason)
    return snapshot


# -- the snapshot -----------------------------------------------------------------------------------


def _snapshot_document(snapshot):
    return {
        "kind": SNAPSHOT_KIND, "snapshot_version": SNAPSHOT_VERSION, "counts": dict(snapshot.counts),
        "runs": snapshot.runs, "dispatch": snapshot.dispatch, "margins": snapshot.margins,
        "contingencies": snapshot.contingencies}


def _stamp(now):
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is not None:
        now = now.astimezone(datetime.timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ")


def ingest_export(export_path, repo_root=None, snapshots_dir=None, now=None):
    """
    Validate the export file at `export_path` (which must be inside the git-ignored `data/private/`)
    and write `snapshot_STAMP.json` into `snapshots_dir` (default
    `<repo>/data/private/pandapower/snapshots`) through the private-path guard. Returns
    IngestResult(path, snapshot). Every check runs before a folder or a file is created; a refusal
    (ExportRefused, or private.PrivatePathRefused for a bad path or an existing snapshot) writes
    nothing.
    """
    source = private.require_private(export_path, repo_root)
    snapshot = validate(read_export(source))
    if snapshots_dir is None:
        snapshots_dir = os.path.join(private.private_root(repo_root), "pandapower", "snapshots")
    target = os.path.join(snapshots_dir, "snapshot_%s.json" % _stamp(now))
    private.require_private(target, repo_root)
    document = _snapshot_document(snapshot)
    size = len(json.dumps(
        dict(document, **{REPORT_MARKER: 1}), sort_keys=True, allow_nan=False, indent=1)) + 1
    if size > MAX_SNAPSHOT_BYTES:
        raise ExportRefused("too_large")
    written = private.write_private_json(target, document, REPORT_MARKER, repo_root)
    return IngestResult(written, snapshot)


def load_snapshot(path, repo_root=None):
    """
    The Snapshot in the private file at `path`, validated again: the report marker key must be the
    integer 1 and `kind` and `snapshot_version` must match (reason bad_marker), then the same rules
    as an export. ExportRefused otherwise; private.PrivatePathRefused for a path outside
    `data/private/`.
    """
    resolved = private.require_private(path, repo_root)
    reason, data = _read_bytes(resolved, MAX_SNAPSHOT_BYTES)
    if reason is None:
        ok, document = _parse_json(data.decode("utf-8", "replace"))
        reason = None if ok else "not_json"
    if reason is not None:
        raise ExportRefused(reason)
    if not isinstance(document, dict):
        raise ExportRefused("wrong_shape")
    marker = document.get(REPORT_MARKER)
    if (not isinstance(marker, int) or isinstance(marker, bool) or marker != 1
            or document.get("kind") != SNAPSHOT_KIND
            or document.get("snapshot_version") != SNAPSHOT_VERSION):
        raise ExportRefused("bad_marker")
    parts = dict((key, value) for key, value in document.items()
                 if key not in (REPORT_MARKER, "kind", "snapshot_version"))
    return validate(parts)


def complete(recorded_run):
    """
    True when a run's own rows are a full result set: a usable run (outcome ok or fallback) with
    exactly one dispatch row and one margin row per city, and as many distinct contingency ids among
    its contingency rows as `n_contingencies_with_results` says. A per-run fact, so one damaged run
    excludes itself (the replay's rows_incomplete) instead of refusing the whole file. False for a
    failed run.
    """
    run = recorded_run.run
    if run["outcome"] == "failed":
        return False
    expected = run["n_contingencies_with_results"]
    if expected is None:
        return False
    cities = sorted(constants.CITIES)
    for rows in (recorded_run.dispatch, recorded_run.margins):
        if sorted(row["city"] for row in rows) != cities:
            return False
    return len(set(row["contingency_id"] for row in recorded_run.contingencies)) == expected


def _slot_key(run):
    return (datetime.datetime.fromisoformat(run["slot_time"]), run["run_id"])


def by_run(snapshot):
    """A list of RecordedRun in slot order (ties by run id), each with its own rows."""
    grouped = {}
    for name in ("dispatch", "margins", "contingencies"):
        for row in getattr(snapshot, name):
            grouped.setdefault((name, row["run_id"]), []).append(row)
    ordered = sorted(snapshot.runs, key=_slot_key)
    return [
        RecordedRun(
            run, grouped.get(("dispatch", run["run_id"]), []),
            grouped.get(("margins", run["run_id"]), []),
            grouped.get(("contingencies", run["run_id"]), []))
        for run in ordered]


# -- the counts-only profile ------------------------------------------------------------------------


def profile(snapshot, mapping_sha256=None, case_sha256=None):
    """The counts of a snapshot as a Profile; the two matching counts are None when no hash is given."""
    runs = snapshot.runs
    outcomes = collections.Counter(run["outcome"] for run in runs)

    def distinct(column):
        return len(set(run[column] for run in runs if run[column] is not None))

    def matching(given, column):
        if given is None:
            return None
        return sum(1 for run in runs if run[column] == given)

    return Profile(
        len(runs), outcomes.get("ok", 0), outcomes.get("fallback", 0), outcomes.get("failed", 0),
        len(snapshot.dispatch), len(snapshot.margins), len(snapshot.contingencies),
        distinct("mapping_sha256"), distinct("case_sha256"), distinct("job_version"),
        matching(mapping_sha256, "mapping_sha256"), matching(case_sha256, "case_sha256"))


def profile_lines(profile_value):
    """The printed lines of a Profile, one fact each; every line matches PROFILE_LINE_PATTERNS."""
    p = profile_value

    def checked(count):
        return "not checked" if count is None else "%d" % count

    lines = [
        "snapshot runs: %d" % p.runs,
        "snapshot runs ok: %d" % p.ok_runs,
        "snapshot runs fallback: %d" % p.fallback_runs,
        "snapshot runs failed: %d" % p.failed_runs,
        "snapshot rows dispatch: %d" % p.dispatch_rows,
        "snapshot rows margins: %d" % p.margin_rows,
        "snapshot rows contingencies: %d" % p.contingency_rows,
        "snapshot distinct mapping hashes: %d" % p.distinct_mappings,
        "snapshot distinct case hashes: %d" % p.distinct_cases,
        "snapshot distinct job versions: %d" % p.distinct_job_versions,
        "snapshot runs matching local mapping: %s" % checked(p.matching_mapping),
        "snapshot runs matching session case: %s" % checked(p.matching_case),
    ]
    for line in lines:
        if not any(pattern.match(line) for pattern in PROFILE_LINE_PATTERNS):
            raise ValueError("a profile line is outside the closed vocabulary")
    return lines
