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
import math
import uuid

from psse_job import constants, contract, ratings
from psse_job.redaction import redact


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
