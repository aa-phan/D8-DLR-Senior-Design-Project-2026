"""
The only module of the PSS/E job that writes to the database (pss-e-integration Phase 1:
WB-01, WB-02, D-03, D-04). It connects as `dlr_psse_writer`, a role that holds INSERT and
SELECT on the four result tables and nothing else, so this module has no UPDATE or DELETE
path at all: a rerun can never overwrite a stored run.

`write_run` inserts the run row and every result row in ONE transaction, run row first (the
composite foreign key needs it). If anything fails, the transaction has rolled back, so no row
of the attempt remains; a second, separate transaction then records the run as `failed`
(failed_stage 'write'). `record_failure` writes a failed run alone. The run record is written
once, at the end of a run: there is no 'running' row (D-04).

psycopg is imported inside `connect` only, so importing this module needs no driver. Every
message raised or stored here is redacted (psse_job.redaction); the exceptions are raised
outside any `except` block, so no original exception (and no part of its message) is chained.
Standard library only, Python 3.7 syntax (D-05).
"""

import json
import os
import urllib.parse

from psse_job import constants, contract, run_record
from psse_job.redaction import connection_identifiers, env_secrets, redact

WRITTEN = "written"
ALREADY_RECORDED = "already_recorded"


class WriteFailed(RuntimeError):
    """The result write failed and was rolled back; the message is always redacted."""


class RecordFailed(RuntimeError):
    """
    Not even the failed-run record could be written, so nothing exists for this run_id and
    the run must not look successful; the message is always redacted.
    """


def _url_secrets(url):
    """The URL, its password (raw and percent-decoded), user, project reference and host."""
    found = [url]
    try:
        password = urllib.parse.urlsplit(url).password
    except ValueError:
        password = None
    if password:
        found.extend([password, urllib.parse.unquote(password)])
    found.extend(connection_identifiers(url))
    return found


def connect(url=None, env=None):
    """
    Open the writer connection (autocommit; each write opens its own transaction). `url`
    defaults to the SUPABASE_PSSE_DB_URL variable of `env` (default os.environ). A missing or
    blank URL raises WriteFailed before any driver import; a failed connection raises
    WriteFailed with the redacted driver message and no chained exception.
    """
    env = os.environ if env is None else env
    if url is None:
        url = env.get(constants.ENV_PSSE_DB_URL)
    if url is None or not str(url).strip():
        raise WriteFailed("%s is not set" % constants.ENV_PSSE_DB_URL)
    # A secret pasted with a trailing newline must connect: the stripped URL is the one that
    # is redacted and the one handed to libpq.
    url = str(url).strip()
    secrets = _url_secrets(url) + env_secrets(env)

    failure = None
    conn = None
    try:
        import psycopg  # imported here so importing this module needs no driver

        # prepare_threshold=None keeps a pasted transaction-pooler URL (port 6543) working.
        conn = psycopg.connect(url, connect_timeout=10, prepare_threshold=None, autocommit=True)
        conn.execute("set statement_timeout = '30s'")
        conn.execute("set timezone = 'UTC'")
    except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted WriteFailed
        failure = redact(str(exc), secrets, constants.LOG_MAX_CHARS)
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    # Raised outside the except block so no exception context is attached.
    if failure is not None:
        raise WriteFailed("database connection failed: " + failure)
    return conn


def _params(columns, row):
    """
    The bound parameters of one row: exactly `columns` (ValueError naming a missing or an
    unexpected key); JSONB columns as strict JSON text (None stays None).
    """
    for key in row:
        if key not in columns:
            raise ValueError("%r is not a column of the insert" % (key,))
    params = {}
    for column in columns:
        if column not in row:
            raise ValueError("row has no value for %r" % (column,))
        value = row[column]
        if column in contract.JSONB_COLUMNS and value is not None:
            value = json.dumps(value, allow_nan=False)
        params[column] = value
    return params


def _failure_text(exc):
    """A redacted, non-empty description of `exc`, at most ERROR_MAX_CHARS long."""
    return redact(str(exc), limit=constants.ERROR_MAX_CHARS) or type(exc).__name__


def _insert_run(conn, record):
    """Insert the run row in its own transaction: WRITTEN, or ALREADY_RECORDED when it exists."""
    params = _params(contract.PSSE_RUN_COLUMNS, record)
    with conn.transaction():
        inserted = conn.execute(contract.INSERT_RUN_SQL, params).fetchone()
    return WRITTEN if inserted is not None else ALREADY_RECORDED


def write_run(conn, record, rows):
    """
    Write a completed run (outcome 'ok' or 'fallback'): the run row and every row of `rows`
    (a dict keyed by the three result table names) in one transaction. Returns 'written', or
    'already_recorded' when this run_id was committed by an earlier attempt (nothing else is
    inserted). Any failure rolls the transaction back, records the run as failed with
    failed_stage 'write' in a new transaction and raises WriteFailed; when that record cannot
    be written either, RecordFailed is raised instead and no row exists for the run_id.
    ValueError (nothing written) for a record that is not ok or fallback.
    """
    if record.get("outcome") not in ("ok", "fallback"):
        raise ValueError("write_run takes an ok or fallback record; use record_failure for a failed run")

    result = None
    failure = None
    try:
        run_params = _params(contract.PSSE_RUN_COLUMNS, record)
        with conn.transaction():
            inserted = conn.execute(contract.INSERT_RUN_SQL, run_params).fetchone()
            if inserted is None:
                result = ALREADY_RECORDED
            else:
                for table in contract.RESULT_TABLES:
                    sql = contract.INSERT_RESULT_SQL[table]
                    columns = contract.TABLE_COLUMNS[table]
                    for row in rows.get(table, ()):
                        conn.execute(sql, _params(columns, row))
                result = WRITTEN
    except Exception as exc:  # noqa: BLE001 - the transaction has rolled back; handled below
        failure = _failure_text(exc)
    if failure is None:
        return result

    # Outside the except block: a new transaction records the failure (never an UPDATE).
    failed = run_record.as_failed(record, "write", "result write failed: " + failure)
    recorded = None
    second = None
    try:
        record_failure(conn, failed)
        recorded = True
    except RecordFailed as exc:
        second = str(exc)
    if recorded:
        raise WriteFailed(failure)
    raise RecordFailed(redact(
        "result write failed: %s; the failure record could not be written either: %s"
        % (failure[:450], second[:450]),
        limit=constants.ERROR_MAX_CHARS,
    ))


def record_failure(conn, record):
    """
    Write a failed run's record alone: the run row, no result rows, in one transaction.
    Returns 'written' or 'already_recorded'. ValueError unless the outcome is 'failed';
    RecordFailed (redacted, not chained) when the row cannot be written.
    """
    if record.get("outcome") != "failed":
        raise ValueError("record_failure takes a failed record")
    result = None
    failure = None
    try:
        result = _insert_run(conn, record)
    except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted RecordFailed
        failure = _failure_text(exc)
    if failure is not None:
        raise RecordFailed("the failed-run record could not be written: " + failure)
    return result
