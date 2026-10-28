"""
One run of the hourly PSS/E job (pss-e-integration Phase 1: IN-01, WB-01, WB-02, D-02, D-04).

`run_once` takes the start time once, selects each city's rating (a failed ratings read is a
fallback run, never a failed one, D-02), calls the injected study once, validates what it
returned and records the run exactly once, at the end, through the atomic writer. The
database is not touched before the study has returned or failed, so no 'running' row ever
exists (D-04); a run that dies mid-way leaves a gap that SCH-02 detects.

Phase 2 injects the real `psspy` study (`study(selection, context)` returning
contract.StudyResults, or raising contract.StudyFailed(stage, message)) and Phase 3 the
launcher that turns the returned exit code into something Task Scheduler and the operator see:

  EXIT_OK (0)               an ok or fallback run was written, or was already recorded
  EXIT_FAILED_RECORDED (1)  the run failed and a failed record exists
  EXIT_NOT_RECORDED (3)     no record could be written (database unreachable): the gap SCH-02
                            will detect

Every logged and stored message is redacted (psse_job.redaction). Standard library and
psse_job only, Python 3.7 syntax (D-05).
"""

import collections
import datetime
import logging

from psse_job import constants, contract, run_record, writer
from psse_job.ratings import select_ratings
from psse_job.redaction import env_secrets, redact

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILED_RECORDED = 1
EXIT_NOT_RECORDED = 3

# status: "written" | "already_recorded" | "failure_recorded" | "not_recorded"
RunOutcome = collections.namedtuple(
    "RunOutcome", ["run_id", "outcome", "status", "failed_stage", "exit_code"]
)


def _is_aware(value):
    return (
        isinstance(value, datetime.datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _redacted_failure(failure, env):
    """`failure` with its message also redacted against the secrets of `env`."""
    message = redact(failure.message, env_secrets(env), constants.ERROR_MAX_CHARS)
    return contract.Failure(failure.stage, message)


def _cities_text(selection):
    parts = []
    for city in constants.CITIES:
        choice = selection.choices[city]
        parts.append("%s:%s/%s" % (city, choice.source, choice.fallback_reason or "-"))
    return ",".join(parts)


def _log_run(run_id, outcome, status, stage, selection, error):
    """Exactly one INFO summary line, plus one WARNING line when there is an error."""
    log.info(
        "psse run %s outcome=%s status=%s stage=%s cities=%s",
        run_id, outcome, status, stage or "-", _cities_text(selection),
    )
    if error:
        log.warning(
            "psse job error for run %s: %s", run_id, error[:constants.LOG_MAX_CHARS]
        )


def run_once(fetch, study, connect, case_id, case_sha256=None, mapping_sha256=None,
             clock=None, env=None):
    """
    Run the job once and return a RunOutcome (see the module docstring for the exit codes).

    `fetch()` reads the latest_rating rows, `study(selection, context)` runs the study,
    `connect()` returns the writer connection and is called only after the study. `clock()`
    returns an aware datetime (default: now in UTC); the first value is the start time used
    for every city's age check and for slot_time, a later value that is earlier than the
    start is clamped to it. A naive start raises ValueError before anything else happens.
    """
    clock = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))
    started_at = clock()
    run_id = run_record.new_run_id(started_at)  # ValueError for a naive start
    context = contract.RunContext(
        run_id, started_at, run_record.case_label(case_id), case_sha256, mapping_sha256,
        run_record.job_version(env),
    )

    # Never raises for a failed read: the run continues on static ratings (D-02).
    selection = select_ratings(fetch, started_at)

    results = None
    failure = None
    try:
        results = study(selection, context)
    except Exception as exc:  # noqa: BLE001 - every study failure becomes one failed record
        failure = run_record.failure_from_exception("internal", exc)
        results = None

    finished_at = clock()
    if not _is_aware(finished_at) or finished_at < started_at:
        finished_at = started_at

    record = None
    rows = None
    if failure is None:
        try:
            run_record.validate_results(results, selection)
            record = run_record.build_run_record(context, selection, finished_at, results=results)
            rows = run_record.result_rows(record, results)
        except Exception as exc:  # noqa: BLE001 - an invalid set is never written
            failure = run_record.failure_from_exception("validate_results", exc)
            record = None
            rows = None
    if failure is not None:
        failure = _redacted_failure(failure, env)
        record = run_record.build_run_record(context, selection, finished_at, failure=failure)

    outcome = record["outcome"]
    stage = record["failed_stage"]
    error = record["error"]

    # D-04: nothing touches the database before this point.
    conn = None
    connect_error = None
    try:
        conn = connect()
    except Exception as exc:  # noqa: BLE001 - reported as an unrecorded run
        connect_error = redact(str(exc), env_secrets(env), constants.LOG_MAX_CHARS) or type(exc).__name__
    if connect_error is not None:
        if failure is None:
            outcome, stage = "failed", "write"
        result = RunOutcome(run_id, outcome, "not_recorded", stage, EXIT_NOT_RECORDED)
        _log_run(run_id, outcome, result.status, stage, selection, connect_error)
        return result

    status = None
    exit_code = None
    try:
        if failure is not None:
            try:
                recorded = writer.record_failure(conn, record)
                status = "failure_recorded" if recorded == writer.WRITTEN else writer.ALREADY_RECORDED
                exit_code = EXIT_FAILED_RECORDED
            except writer.RecordFailed as exc:
                status, exit_code, error = "not_recorded", EXIT_NOT_RECORDED, str(exc)
        else:
            try:
                status = writer.write_run(conn, record, rows)
                exit_code = EXIT_OK
            except writer.WriteFailed as exc:
                outcome, stage, error = "failed", "write", str(exc)
                status, exit_code = "failure_recorded", EXIT_FAILED_RECORDED
            except writer.RecordFailed as exc:
                outcome, stage, error = "failed", "write", str(exc)
                status, exit_code = "not_recorded", EXIT_NOT_RECORDED
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 - a close error never changes the outcome
            pass

    error = redact(error, env_secrets(env), constants.LOG_MAX_CHARS) if error else None
    _log_run(run_id, outcome, status, stage, selection, error)
    return RunOutcome(run_id, outcome, status, stage, exit_code)
