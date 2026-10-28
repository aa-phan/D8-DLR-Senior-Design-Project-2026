"""
The run record and the result rows of one PSS/E job run (pss-e-integration Phase 1: WB-01,
WB-02, D-02, D-04).

`build_run_record` turns a run's context, rating selection and study outcome into exactly
one psse_run row (a dict keyed by contract.PSSE_RUN_COLUMNS, in DDL order); `result_rows`
turns the study's rows into the parameter dicts of the three result tables. Nothing here
touches a database: psse_job.writer writes what this module builds.

The outcome rule: failed when a failure is given; fallback when any city used the static
rating (a failed ratings read included, D-02); ok only when all four cities used a
city_rating row. Every error text is redacted and cut to 1000 characters after redaction.

Standard library only, Python 3.7 syntax (D-05).
"""

import datetime
import hashlib
import math
import os
import subprocess
import uuid

from psse_job import constants, contract, ratings
from psse_job.redaction import redact

# A larger contingency result fails the run instead of being truncated or written whole
# to a hosted database (research Pitfall 10, T-01-26).
MAX_CONTINGENCY_ROWS = 5000

_JOB_VERSION_MAX_CHARS = 40
_CASE_LABEL_MAX_CHARS = 200


def _require_aware(name, value):
    if (
        not isinstance(value, datetime.datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("%s must be a timezone-aware datetime" % name)


def new_run_id(started_at):
    """`psse-<started_at in UTC as %Y%m%dT%H%M%SZ>-<8 hex>`, the idempotency key of one run."""
    _require_aware("started_at", started_at)
    stamp = started_at.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "psse-%s-%s" % (stamp, uuid.uuid4().hex[:8])


def slot_of(instant):
    """The aware UTC hour floor of `instant`; a naive datetime raises ValueError."""
    _require_aware("instant", instant)
    return instant.astimezone(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)


def finite(x):
    """
    A Python float, or None for None, for anything that is not a number, and for NaN and
    infinity. The same rule supabase_store.finite applies, without numpy.
    """
    if x is None:
        return None
    if hasattr(x, "item") and not isinstance(x, (int, float, str, bool)):
        x = x.item()
    if isinstance(x, bool):
        return float(x)
    try:
        value = float(x)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def outcome_for(selection, failed):
    """'failed' when `failed`, else 'fallback' when any choice is static, else 'ok'."""
    if failed:
        return "failed"
    for city in constants.CITIES:
        if selection.choices[city].source == constants.SOURCE_STATIC:
            return "fallback"
    return "ok"


def _error_text(message, stage):
    """A redacted, non-empty error text of at most ERROR_MAX_CHARS characters."""
    text = redact(message, limit=constants.ERROR_MAX_CHARS)
    return text if text.strip() else "%s failed" % stage


def _failure_fields(failure):
    """(failed_stage, error) of a failure; an unknown stage becomes 'internal'."""
    stage = failure.stage
    message = failure.message
    if stage not in constants.FAILED_STAGES:
        message = "stage %r: %s" % (stage, "" if message is None else message)
        stage = "internal"
    return stage, _error_text(message, stage)


def _ratings_used(selection, results):
    """ratings_used(selection), each city's kV and MVA filled from the study's dispatch row."""
    used = ratings.ratings_used(selection)
    if results is not None:
        for row in results.dispatch or []:
            city = row.get("city") if isinstance(row, dict) else None
            if city in used:
                used[city]["line_voltage_kv"] = finite(row.get("line_voltage_kv"))
                used[city]["rating_mva"] = finite(row.get("applied_mva"))
    return used


def build_run_record(context, selection, finished_at, results=None, failure=None):
    """
    The one psse_run row of a run: a dict whose keys are exactly contract.PSSE_RUN_COLUMNS in
    order. `results` (a contract.StudyResults) fills rate_set, psse_version, the contingency
    counts and each city's kV and MVA in ratings_used; `failure` (a contract.Failure) makes
    the run 'failed'. ValueError when `finished_at` or the start is naive, when `finished_at`
    is earlier than the start, or when a run that did not fail has no results.
    """
    _require_aware("finished_at", finished_at)
    slot = slot_of(context.started_at)
    if finished_at < context.started_at:
        raise ValueError("finished_at is earlier than started_at")
    if failure is None and results is None:
        raise ValueError("a run that did not fail needs study results")

    failed_stage = None
    error = None
    if failure is not None:
        failed_stage, error = _failure_fields(failure)

    n_contingencies = None
    n_with_results = None
    rate_set = None
    psse_version = None
    if results is not None:
        n_contingencies = results.n_contingencies
        n_with_results = len(set(row.get("contingency_id") for row in results.contingencies or []))
        rate_set = results.rate_set
        psse_version = results.psse_version

    read_error = None
    if selection.read_error:
        read_error = redact(selection.read_error, limit=constants.ERROR_MAX_CHARS) or None

    values = {
        "run_id": context.run_id,
        "slot_time": slot,
        "started_at": context.started_at,
        "finished_at": finished_at,
        "outcome": outcome_for(selection, failure is not None),
        "failed_stage": failed_stage,
        "error": error,
        "ratings_read_error": read_error,
        "case_id": context.case_id,
        "case_sha256": context.case_sha256,
        "mapping_sha256": context.mapping_sha256,
        "rate_set": rate_set,
        "ratings_used": _ratings_used(selection, results),
        "n_contingencies": n_contingencies,
        "n_contingencies_with_results": n_with_results,
        "job_version": context.job_version,
        "psse_version": psse_version,
    }
    return dict((column, values[column]) for column in contract.PSSE_RUN_COLUMNS)


def result_rows(record, results):
    """
    The parameter dicts of the three result tables, keyed by table name. Each row has exactly
    that table's column tuple: run_id and run_outcome come from `record`, every other key
    from the study row (a key outside the tuple raises ValueError naming it; a missing key
    becomes None). Double columns pass through finite().
    """
    sources = (
        (contract.DISPATCH_TABLE, results.dispatch),
        (contract.MARGIN_TABLE, results.margins),
        (contract.CONTINGENCY_TABLE, results.contingencies),
    )
    rows = {}
    for table, study_rows in sources:
        columns = contract.TABLE_COLUMNS[table]
        built = []
        for study_row in study_rows or []:
            for key in study_row:
                if key not in columns or key in ("run_id", "run_outcome"):
                    raise ValueError("%r is not a column of %s" % (key, table))
            params = {}
            for column in columns:
                if column == "run_id":
                    params[column] = record["run_id"]
                elif column == "run_outcome":
                    params[column] = record["outcome"]
                elif column in _DOUBLE_COLUMNS:
                    params[column] = finite(study_row.get(column))
                else:
                    params[column] = study_row.get(column)
            built.append(params)
        rows[table] = built
    return rows


# Columns typed double precision in the DDL.
_DOUBLE_COLUMNS = frozenset([
    "applied_amps_per_conductor", "applied_amps_circuit", "line_voltage_kv", "applied_mva",
    "voltage_limit_mva", "dispatched_mva", "dispatched_amps_circuit",
    "dispatched_amps_per_conductor", "power_factor", "dispatched_mw",
    "base_transfer_mw", "limit_transfer_mw", "margin_mw", "margin_pct", "min_voltage_pu",
    "limit_value", "observed_value", "exceeded_by",
])


def as_failed(record, stage, message):
    """
    A copy of `record` turned into a failed run: outcome 'failed', failed_stage `stage`,
    error = the redacted message cut to ERROR_MAX_CHARS ('<stage> failed' when it is empty).
    """
    failed = dict(record)
    failed["outcome"] = "failed"
    failed["failed_stage"], failed["error"] = _failure_fields(contract.Failure(stage, message))
    return failed


# --------------------------------------------------------------------------- labels

def case_label(value):
    """
    The case identifier: the part of `value` after the last forward or backward slash,
    stripped and cut to 200 characters; 'unknown' when empty. A label, never a path.
    """
    text = "" if value is None else str(value)
    text = text.replace("\\", "/").rsplit("/", 1)[-1].strip()[:_CASE_LABEL_MAX_CHARS].strip()
    return text or "unknown"


def file_sha256(path):
    """Lowercase hex sha256 of the file's bytes (read in chunks); None when it cannot be read."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _repository_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def job_version(env=None):
    """
    The job's version label: PSSE_JOB_VERSION (stripped, cut to 40 characters) when set, else
    the short git commit of the repository, else 'unknown'. Never raises: a version is a
    label, never a reason to fail a run.
    """
    env = os.environ if env is None else env
    try:
        configured = (env.get("PSSE_JOB_VERSION") or "").strip()
        if configured:
            return configured[:_JOB_VERSION_MAX_CHARS]
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_repository_root(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=5, check=True,
        )
        return out.stdout.strip()[:_JOB_VERSION_MAX_CHARS] or "unknown"
    except Exception:  # noqa: BLE001 - version is a label, never a reason to fail a run
        return "unknown"


def failure_from_exception(stage, exc):
    """
    A contract.Failure for an exception raised while running `stage`. A StudyFailed supplies
    its own stage (when it is a known one) and message; any other exception uses `stage`
    (or 'internal' when that is not a known stage) and '<ExceptionClass>: <text>'. The message
    is redacted and cut to ERROR_MAX_CHARS; an empty exception text becomes
    '<ExceptionClass> during <stage>'.
    """
    name = type(exc).__name__
    if isinstance(exc, contract.StudyFailed):
        given = exc.stage
        message = "" if exc.message is None else str(exc.message)
        if given in constants.FAILED_STAGES:
            use_stage = given
        else:
            use_stage = "internal"
            message = "stage %r: %s" % (given, message)
    else:
        use_stage = stage if stage in constants.FAILED_STAGES else "internal"
        text = str(exc)
        message = "%s: %s" % (name, text) if text.strip() else ""
    message = redact(message, limit=constants.ERROR_MAX_CHARS)
    if not message.strip():
        message = "%s during %s" % (name, use_stage)
    return contract.Failure(use_stage, message)


# --------------------------------------------------------------------------- validation

def _fail(message):
    raise contract.ResultsInvalid(message)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _number(where, row, key):
    """`row[key]` as a float; ResultsInvalid unless it is present and a finite number."""
    value = row.get(key)
    if not _is_number(value) or not math.isfinite(value):
        _fail("%s: %s is missing or not a finite number" % (where, key))
    return float(value)


def _close(a, b, relative):
    return abs(a - b) <= relative * max(abs(a), abs(b))


def _text(where, row, key):
    value = row.get(key)
    if not isinstance(value, str) or not 1 <= len(value) <= 200:
        _fail("%s: %s is missing, not text or not 1 to 200 characters" % (where, key))
    return value


def _rows_by_city(name, rows):
    """{city: row} of a list that must hold exactly one dict per city."""
    if not isinstance(rows, (list, tuple)):
        _fail("%s is not a list" % name)
    found = {}
    for row in rows:
        city = row.get("city") if isinstance(row, dict) else None
        if city not in constants.CITIES:
            _fail("%s has a row for an unknown city: %r" % (name, city))
        if city in found:
            _fail("%s has more than one row for %s" % (name, city))
        found[city] = row
    for city in constants.CITIES:
        if city not in found:
            _fail("%s has no row for %s" % (name, city))
    return found


def _check_dispatch(city, row, choice):
    where = "dispatch %s" % city
    if row.get("rating_source") != choice.source:
        _fail("%s: rating_source %r differs from the selected %r" % (where, row.get("rating_source"), choice.source))
    if row.get("fallback_reason") != choice.fallback_reason:
        _fail("%s: fallback_reason differs from the selection" % where)
    amps = _number(where, row, "applied_amps_per_conductor")
    if not _close(amps, choice.amps_per_conductor, 1e-9):
        _fail("%s: applied_amps_per_conductor differs from the selected rating" % where)
    count = row.get("subconductors_per_phase")
    if isinstance(count, bool) or count != choice.subconductors_per_phase:
        _fail("%s: subconductors_per_phase differs from the selection" % where)
    # The link to the newest city_rating row exists exactly for a city that used one.
    if choice.source == constants.SOURCE_CITY_RATING:
        if (row.get("city_rating_valid_time") != choice.row_valid_time
                or row.get("city_rating_computed_at") != choice.row_computed_at):
            _fail("%s: the city_rating link differs from the row that was read" % where)
    elif row.get("city_rating_valid_time") is not None or row.get("city_rating_computed_at") is not None:
        _fail("%s: a static rating must not carry a city_rating link" % where)

    circuit = _number(where, row, "applied_amps_circuit")
    kv = _number(where, row, "line_voltage_kv")
    applied = _number(where, row, "applied_mva")
    limit = _number(where, row, "voltage_limit_mva")
    dispatched = _number(where, row, "dispatched_mva")
    dispatched_circuit = _number(where, row, "dispatched_amps_circuit")
    dispatched_conductor = _number(where, row, "dispatched_amps_per_conductor")
    power_factor = _number(where, row, "power_factor")
    dispatched_mw = _number(where, row, "dispatched_mw")
    for name, value in (("line_voltage_kv", kv), ("applied_mva", applied), ("voltage_limit_mva", limit),
                        ("dispatched_mva", dispatched), ("dispatched_mw", dispatched_mw)):
        if value <= 0:
            _fail("%s: %s must be greater than 0" % (where, name))
    if not 0 < power_factor <= 1:
        _fail("%s: power_factor must be in (0, 1]" % where)
    if not _close(circuit, amps * choice.subconductors_per_phase, 1e-6):
        _fail("%s: applied_amps_circuit is not amps per conductor x subconductors" % where)
    if not _close(applied, math.sqrt(3.0) * kv * circuit / 1000.0, 1e-6):
        _fail("%s: applied_mva is not sqrt(3) x kV x circuit amps / 1000" % where)
    if not _close(dispatched, min(applied, limit), 1e-6):
        _fail("%s: dispatched_mva is not the least of applied_mva and voltage_limit_mva" % where)
    expected = "dlr_rating" if applied <= limit else "voltage_stability"
    if row.get("limiting_factor") != expected:
        _fail("%s: limiting_factor must be %s" % (where, expected))
    if not _close(dispatched_circuit, dispatched * 1000.0 / (math.sqrt(3.0) * kv), 1e-6):
        _fail("%s: dispatched_amps_circuit does not match dispatched_mva" % where)
    if not _close(dispatched_conductor * choice.subconductors_per_phase, dispatched_circuit, 1e-6):
        _fail("%s: dispatched_amps_per_conductor does not match dispatched_amps_circuit" % where)
    if not _close(dispatched_mw, dispatched * power_factor, 1e-6):
        _fail("%s: dispatched_mw is not dispatched_mva x power_factor" % where)
    return limit


def _check_margin(city, row, dispatch_limit):
    where = "margin %s" % city
    method = row.get("method")
    if not isinstance(method, str) or not 1 <= len(method) <= 100:
        _fail("%s: method is missing or not 1 to 100 characters" % where)
    _number(where, row, "margin_mw")
    limit = _number(where, row, "voltage_limit_mva")
    if limit <= 0:
        _fail("%s: voltage_limit_mva must be greater than 0" % where)
    if not _close(limit, dispatch_limit, 1e-6):
        _fail("%s: voltage_limit_mva differs from the dispatch row's" % where)
    for key in ("base_transfer_mw", "limit_transfer_mw", "margin_pct", "min_voltage_pu"):
        if row.get(key) is not None:
            _number(where, row, key)


def _check_contingency(index, row):
    where = "contingency row %d" % index
    if not isinstance(row, dict):
        _fail("%s is not a dict" % where)
    contingency_id = _text(where, row, "contingency_id")
    kind = row.get("violation_kind")
    if kind not in constants.VIOLATION_KINDS:
        _fail("%s: violation_kind %r is not allowed" % (where, kind))
    element_type = row.get("element_type")
    if element_type not in constants.ELEMENT_TYPES:
        _fail("%s: element_type %r is not allowed" % (where, element_type))
    element_id = _text(where, row, "element_id")
    unit = row.get("unit")
    if unit is not None and unit not in constants.RESULT_UNITS:
        _fail("%s: unit %r is not allowed" % (where, unit))
    if row.get("city") is not None and row.get("city") not in constants.CITIES:
        _fail("%s: city %r is not a project city" % (where, row.get("city")))
    if kind == "non_convergence":
        if element_type != "contingency" or element_id != contingency_id or unit is not None:
            _fail("%s: a non_convergence row names its contingency and has no unit" % where)
        for key in ("limit_value", "observed_value", "exceeded_by"):
            if row.get(key) is not None:
                _fail("%s: a non_convergence row has no %s" % (where, key))
    else:
        want_type, want_unit = ("branch", "MVA") if kind == "thermal_overload" else ("bus", "pu")
        if element_type != want_type or unit != want_unit:
            _fail("%s: %s belongs to a %s element in %s" % (where, kind, want_type, want_unit))
        limit = _number(where, row, "limit_value")
        observed = _number(where, row, "observed_value")
        exceeded = _number(where, row, "exceeded_by")
        if limit <= 0 or observed < 0 or exceeded <= 0:
            _fail("%s: limit_value and exceeded_by must be positive, observed_value not negative" % where)
        want = limit - observed if kind == "voltage_low" else observed - limit
        if abs(exceeded - want) > 1e-6 * max(abs(limit), 1.0):
            _fail("%s: exceeded_by is not the distance past the limit" % where)
    return contingency_id, kind, element_id


def validate_results(results, selection):
    """
    Refuse a malformed study result before anything is written: contract.ResultsInvalid naming
    the first problem. The study must apply exactly the selected rating (a study can never turn
    a static city into a DLR one), and every row must satisfy the DDL's identities and rules,
    so a violation is found here, as a validate_results failure, not at write time. A result
    with zero contingency rows is valid. Returns None.
    """
    if not isinstance(results, contract.StudyResults):
        _fail("results is not a StudyResults")
    dispatch = _rows_by_city("dispatch", results.dispatch)
    limits = {}
    for city in constants.CITIES:
        limits[city] = _check_dispatch(city, dispatch[city], selection.choices[city])
    margins = _rows_by_city("margins", results.margins)
    for city in constants.CITIES:
        _check_margin(city, margins[city], limits[city])

    rows = results.contingencies
    if not isinstance(rows, (list, tuple)):
        _fail("contingencies is not a list")
    if len(rows) > MAX_CONTINGENCY_ROWS:
        _fail("%d contingency rows exceed the limit of %d" % (len(rows), MAX_CONTINGENCY_ROWS))
    seen = set()
    ids = set()
    for index, row in enumerate(rows):
        key = _check_contingency(index, row)
        if key in seen:
            _fail("contingency row %d repeats the key %r" % (index, key))
        seen.add(key)
        ids.add(key[0])
    count = results.n_contingencies
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        _fail("n_contingencies is not a non-negative integer")
    if count < len(ids):
        _fail("n_contingencies %d is smaller than the %d contingencies with results" % (count, len(ids)))
