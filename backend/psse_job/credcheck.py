"""
The DBX-02 credential proof of the PSS/E job (pss-e-integration Phase 3, plan 03-03).

DBX-02 says the job writes only to the PSS/E result tables and cannot change `city_rating`. The
role leg, `role_checks`, shows with the job's own database credential that `dlr_psse_writer` can
insert into and select from the four result tables and holds nothing else: six catalog checks
(role attributes, role memberships, INSERT and SELECT on the four tables, nothing more on them,
nothing on any other relation of schema public, no executable SECURITY DEFINER function in
public) and seven statements that must be refused with SQLSTATE 42501.

The REST leg, `rest_checks`, is the other half of DBX-02: the publishable key reads ratings through
the job's own fetch_latest_rating, and a PATCH and a DELETE of city_rating with a filter that
matches no row are refused with 401 or 403 (a 2xx fails, any other status fails as inconclusive,
and no write attempt is sent unless the read succeeded).

Safe by construction. The catalog checks only read. Every active statement is a where-false
statement run inside a transaction that is forced to roll back, so a credential that is too
powerful still changes no row. Only SQLSTATE 42501 counts as a refusal: any other error (a
missing relation, a read-only session, a timeout) is a FAIL as inconclusive, and success is a FAIL
because the statement was allowed. The session is deliberately NOT read-only: PostgreSQL checks
a read-only transaction before it checks privileges, so every INSERT, UPDATE and DELETE would be
refused with 25006 (read_only_sql_transaction) whatever the role may do, which is not a refusal
here and would hide a planted grant (verified on PostgreSQL 18.6 in a scratch run: update and
delete as the writer gave 25006 in a read-only transaction, not 42501).

The sqlstate attribute of the driver's exception is enough to recognise a refusal, so this
module imports no psycopg. Details hold relation names, privilege names, SQLSTATE codes and
counts: never a URL, user, host, password or key. Standard library and psse_job only, Python 3.7
syntax.

UNVERIFIED until runbook step 8 (plan 03-08): that Phase 6's live migration applied the same
grants, that Supabase's session pooler accepts the custom role, that role memberships and
function privileges on the live project are clean, and that a where-false statement is refused
the same way there (verified for PostgreSQL 18.6 only).
"""

import collections
import datetime
import http.client
import json
import os
import sys
import urllib.error
import urllib.request

from psse_job import constants, contract, dispatch, ratings, run_record, units, writer
from psse_job.redaction import env_secrets, redact

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

EXIT_OK = 0
EXIT_CHECK_FAILED = 6

CheckRow = collections.namedtuple("CheckRow", ["check", "status", "detail"])

# The four tables the writer may insert into and select from, and nothing else.
RESULT_TABLES = ("psse_run", "psse_dispatched_capacity", "psse_voltage_margin", "psse_contingency_result")

# Privileges that may be held on a column and so are tested with has_any_column_privilege (which is
# also true for a table-level grant); the rest exist only at table level.
_COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")
_TABLE_PRIVILEGES = ("DELETE", "TRUNCATE", "TRIGGER")
_NOTHING_ELSE_ON_RESULTS = ("UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
_MAINTAIN_FROM_VERSION = 170000

_HELD = (
    "case when p.privilege in ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES') "
    "then has_any_column_privilege(current_user, c.oid, p.privilege) "
    "else has_table_privilege(current_user, c.oid, p.privilege) end"
)
_RELATION_KINDS = "('r', 'p', 'v', 'm', 'f')"

_ATTRIBUTES_SQL = (
    "select rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication "
    "from pg_roles where rolname = current_user"
)
_ATTRIBUTE_NAMES = ("superuser", "createrole", "createdb", "bypassrls", "replication")
_MEMBERSHIPS_SQL = (
    "select count(*) from pg_auth_members m join pg_roles u on u.oid = m.member "
    "where u.rolname = current_user"
)
_INSERT_SELECT_SQL = (
    "select c.relname, has_table_privilege(current_user, c.oid, 'INSERT'), "
    "has_table_privilege(current_user, c.oid, 'SELECT') "
    "from pg_class c join pg_namespace n on n.oid = c.relnamespace "
    "where n.nspname = 'public' and c.relkind in ('r', 'p') and c.relname = any(%s::text[]) "
    "order by c.relname"
)
_ON_RESULTS_SQL = (
    "select c.relname, p.privilege from pg_class c join pg_namespace n on n.oid = c.relnamespace "
    "cross join unnest(%s::text[]) as p(privilege) "
    "where n.nspname = 'public' and c.relkind in " + _RELATION_KINDS + " and c.relname = any(%s::text[]) and "
    + _HELD + " order by c.relname, p.privilege"
)
_ON_OTHERS_SQL = (
    "select c.relname, p.privilege from pg_class c join pg_namespace n on n.oid = c.relnamespace "
    "cross join unnest(%s::text[]) as p(privilege) "
    "where n.nspname = 'public' and c.relkind in " + _RELATION_KINDS + " and c.relname <> all(%s::text[]) and "
    + _HELD + " order by c.relname, p.privilege"
)
_OTHERS_COUNT_SQL = (
    "select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace "
    "where n.nspname = 'public' and c.relkind in " + _RELATION_KINDS + " and c.relname <> all(%s::text[])"
)
_DEFINER_SQL = (
    "select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
    "where n.nspname = 'public' and p.prosecdef and has_function_privilege(current_user, p.oid, 'EXECUTE')"
)
_VERSION_SQL = "select current_setting('server_version_num')::int"

# Statement checks: each must be refused with 42501. All are where-false, so even a credential that
# is allowed to run them changes no row, and each runs in a transaction forced to roll back. Each
# statement needs exactly ONE privilege: an UPDATE that read a column (`set c = c`) or an
# insert-select would also need SELECT, and a role lacking that SELECT would be refused with 42501
# for the wrong reason, hiding a planted UPDATE or INSERT grant.
REFUSED_STATEMENTS = (
    ("refused:select_city_rating", "select 1 from public.city_rating where false"),
    ("refused:insert_city_rating", "insert into public.city_rating (city) select 'AUSTIN' where false"),
    ("refused:update_city_rating", "update public.city_rating set rating_amps = 1 where false"),
    ("refused:delete_city_rating", "delete from public.city_rating where false"),
    ("refused:select_pipeline_run", "select 1 from public.pipeline_run where false"),
    ("refused:update_psse_run", "update public.psse_run set job_version = 'credcheck' where false"),
    ("refused:delete_psse_run", "delete from public.psse_run where false"),
)

_REFUSAL = "42501"


def checks_ok(rows):
    """True when no row is a FAIL (a SKIP is not a failure here; run decides what a skip means)."""
    return not any(row.status == FAIL for row in rows)


def format_report(rows):
    """One line per row, then a final 'N PASS, M FAIL, K SKIP' line (no trailing newline)."""
    lines = []
    for row in rows:
        lines.append("%-4s  %-44s  %s" % (row.status, row.check, row.detail))
    counts = dict((status, 0) for status in (PASS, FAIL, SKIP))
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    lines.append("%d PASS, %d FAIL, %d SKIP" % (counts[PASS], counts[FAIL], counts[SKIP]))
    return "\n".join(lines)


def _row(check, ok, passed, failed):
    return CheckRow(check, PASS if ok else FAIL, passed if ok else failed)


def _held_list(pairs):
    """'relation PRIVILEGE, ...' of (relation, privilege) pairs, cut to a readable length."""
    items = ["%s %s" % (name, privilege) for name, privilege in pairs]
    shown = ", ".join(items[:12])
    if len(items) > 12:
        shown += ", and %d more" % (len(items) - 12)
    return shown


def _role_attributes(conn):
    row = conn.execute(_ATTRIBUTES_SQL).fetchone()
    if row is None:
        return CheckRow("role_attributes", FAIL, "the current role was not found in pg_roles")
    held = [name for name, value in zip(_ATTRIBUTE_NAMES, row) if value]
    return _row(
        "role_attributes", not held,
        "none of superuser, createrole, createdb, bypassrls, replication",
        "the role holds: " + ", ".join(held),
    )


def _role_memberships(conn):
    count = conn.execute(_MEMBERSHIPS_SQL).fetchone()[0]
    return _row(
        "role_memberships", count == 0,
        "the role is a member of no other role",
        "the role is a member of %d other role(s)" % count,
    )


def _insert_select(conn):
    rows = conn.execute(_INSERT_SELECT_SQL, [list(RESULT_TABLES)]).fetchall()
    found = dict((row[0], (bool(row[1]), bool(row[2]))) for row in rows)
    problems = []
    for table in RESULT_TABLES:
        if table not in found:
            problems.append("%s does not exist" % table)
            continue
        can_insert, can_select = found[table]
        if not can_insert:
            problems.append("%s: no INSERT" % table)
        if not can_select:
            problems.append("%s: no SELECT" % table)
    return _row(
        "result_tables_insert_select", not problems,
        "INSERT and SELECT held on all %d result tables" % len(RESULT_TABLES),
        "; ".join(problems),
    )


def _privileges(conn, names):
    """`names` as a list, plus MAINTAIN when the server is new enough to know it."""
    found = list(names)
    if conn.execute(_VERSION_SQL).fetchone()[0] >= _MAINTAIN_FROM_VERSION:
        found.append("MAINTAIN")
    return found


def _nothing_else_on_results(conn):
    privileges = _privileges(conn, _NOTHING_ELSE_ON_RESULTS)
    held = conn.execute(_ON_RESULTS_SQL, [privileges, list(RESULT_TABLES)]).fetchall()
    return _row(
        "result_tables_nothing_else", not held,
        "no %s on the result tables" % "/".join(privileges),
        "held: " + _held_list(held),
    )


def _nothing_on_other_relations(conn):
    privileges = _privileges(conn, _COLUMN_PRIVILEGES + _TABLE_PRIVILEGES)
    held = conn.execute(_ON_OTHERS_SQL, [privileges, list(RESULT_TABLES)]).fetchall()
    checked = conn.execute(_OTHERS_COUNT_SQL, [list(RESULT_TABLES)]).fetchone()[0]
    return _row(
        "nothing_on_other_relations", not held,
        "no privilege on any of the %d other relations of schema public" % checked,
        "held: " + _held_list(held),
    )


def _no_security_definer(conn):
    count = conn.execute(_DEFINER_SQL).fetchone()[0]
    return _row(
        "no_executable_security_definer_in_public", count == 0,
        "no executable SECURITY DEFINER function in schema public",
        "%d executable SECURITY DEFINER function(s) in schema public" % count,
    )


def _refusal(conn, check, statement):
    """Run `statement` in a transaction forced to roll back; PASS only when it raised 42501."""
    code = None
    allowed = False
    try:
        with conn.transaction(force_rollback=True):
            conn.execute(statement)
        allowed = True
    except Exception as exc:  # noqa: BLE001 - only the SQLSTATE is read; the text is never kept
        code = getattr(exc, "sqlstate", None) or type(exc).__name__
    if allowed:
        return CheckRow(check, FAIL, "the statement was allowed")
    if code == _REFUSAL:
        return CheckRow(check, PASS, "refused with SQLSTATE %s" % _REFUSAL)
    return CheckRow(check, FAIL, "inconclusive: SQLSTATE %s" % code)


def role_checks(conn):
    """
    The role leg: the six catalog checks, then the seven refused statements, as a list of
    CheckRow (13 rows, in that order). `conn` is the connection under test (the job's own,
    from writer.connect). Changes no row of any table.
    """
    rows = [
        _role_attributes(conn),
        _role_memberships(conn),
        _insert_select(conn),
        _nothing_else_on_results(conn),
        _nothing_on_other_relations(conn),
        _no_security_definer(conn),
    ]
    for check, statement in REFUSED_STATEMENTS:
        rows.append(_refusal(conn, check, statement))
    return rows


# --------------------------------------------------------------------------- REST leg

# A filter no row matches (city_rating.city has a CHECK that allows four values only), so even a key
# that is wrongly allowed to write changes no row.
_ZERO_MATCH = "/rest/v1/city_rating?city=eq.__no_such_city__"
_ZERO_MATCH_BODY = {"rating_amps": 1}
_WRITE_CHECKS = (
    ("rest:patch_city_rating_refused", "PATCH", _ZERO_MATCH_BODY),
    ("rest:delete_city_rating_refused", "DELETE", None),
)
_REST_TIMEOUT = 30


def _send_write(method, url, key, body, opener):
    """
    Send one write attempt with the publishable key in the apikey header only. Returns
    (HTTP status, None), or (None, exception class name) when no status came back.
    """
    headers = {"apikey": key, "Accept": "application/json", "User-Agent": constants.USER_AGENT}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.urlopen if opener is None else opener
    status = None
    failure = None
    try:
        response = opener(request, timeout=_REST_TIMEOUT)
        try:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
        finally:
            closer = getattr(response, "close", None)
            if closer is not None:
                closer()
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as exc:
        failure = type(exc).__name__
    return status, failure


def _judge_write(check, status, failure):
    """401 or 403 passes; a 2xx means the key may write; anything else proves nothing."""
    if status in (401, 403):
        return CheckRow(check, PASS, "refused with HTTP %d" % status)
    if status is not None and 200 <= status < 300:
        return CheckRow(check, FAIL, "the key was allowed to change city_rating (HTTP %d)" % status)
    if status is not None:
        return CheckRow(check, FAIL, "inconclusive: HTTP %d" % status)
    return CheckRow(check, FAIL, "inconclusive: no HTTP status (%s)" % failure)


def rest_checks(env, opener=None):
    """
    The REST leg: the publishable key reads ratings through the job's own fetch_latest_rating (so its
    key and URL guards apply: no secret or service_role key, https or loopback), then a PATCH and a
    DELETE of city_rating with a filter that matches no row must be refused with 401 or 403. No write
    attempt is sent unless the read succeeded. Returns three CheckRow: rest:read_ratings and the two
    write checks (SKIP when not sent). `env` holds SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY; `opener`
    is the urlopen seam. Neither value is ever returned.
    """
    env = os.environ if env is None else env
    count = None
    failure = None
    try:
        count = len(ratings.fetch_latest_rating(env, opener=opener))
    except Exception as exc:  # noqa: BLE001 - reported below as redacted text
        failure = redact(str(exc), env_secrets(env), constants.ERROR_MAX_CHARS) or type(exc).__name__
    if failure is not None:
        rows = [CheckRow("rest:read_ratings", FAIL, failure)]
        for check, _method, _body in _WRITE_CHECKS:
            rows.append(CheckRow(check, SKIP, "not sent: the ratings read did not succeed"))
        return rows

    rows = [CheckRow("rest:read_ratings", PASS, "%d rows read through latest_rating" % count)]
    base = str(env.get(constants.ENV_SUPABASE_URL)).strip().rstrip("/")
    key = str(env.get(constants.ENV_PUBLISHABLE_KEY)).strip()
    for check, method, body in _WRITE_CHECKS:
        status, failed = _send_write(method, base + _ZERO_MATCH, key, body, opener)
        rows.append(_judge_write(check, status, failed))
    return rows


# --------------------------------------------------------------------------- write proof

SYNTHETIC_CASE_ID = "credcheck-synthetic"
SYNTHETIC_JOB_VERSION = "credcheck"
_SYNTHETIC_KV = 345.0
_SYNTHETIC_LIMIT_FACTOR = 1.2
_WRITE_PROOF_INSIDE = "write_proof:insert_and_read_back_inside_rollback"
_WRITE_PROOF_AFTER = "write_proof:nothing_survives"
_PROOF_TABLES = (contract.PSSE_RUN_TABLE,) + contract.RESULT_TABLES
_PROOF_LABELS = ("run", "dispatch", "margin", "contingency")


def synthetic_run(now):
    """
    A complete synthetic fallback run built only from the job's own functions, needing no
    database: every city on the static rating (ratings.select_ratings with a read that returns no
    rows, so reason missing), dispatch rows from dispatch.build_dispatch_row at 345 kV with a voltage
    limit 1.2 times the applied MVA, four margin rows of method credcheck_synthetic and two
    contingency rows (one thermal on AUSTIN, one voltage_low), shaped like the study's results.
    The results pass run_record.validate_results before this returns. Returns (selection, run
    record, rows keyed by result table): 1, 4, 4 and 2 rows. `now` must be timezone-aware.
    """
    selection = ratings.select_ratings(lambda: [], now)
    dispatch_rows = []
    margin_rows = []
    applied = {}
    for city in constants.CITIES:
        choice = selection.choices[city]
        applied[city] = units.circuit_mva(choice.amps_per_conductor, choice.subconductors_per_phase, _SYNTHETIC_KV)
        limit = _SYNTHETIC_LIMIT_FACTOR * applied[city]
        dispatch_rows.append(dispatch.build_dispatch_row(choice, _SYNTHETIC_KV, limit))
        margin_rows.append({
            "city": city,
            "method": "credcheck_synthetic",
            "base_transfer_mw": 1000.0,
            "limit_transfer_mw": 1120.0,
            "margin_mw": 120.0,
            "margin_pct": 12.0,
            "voltage_limit_mva": limit,
            "critical_bus": "1001",
            "min_voltage_pu": 0.93,
            "details": None,
        })
    limit_value = applied["AUSTIN"]
    observed = 1.05 * limit_value
    contingency_rows = [
        {
            "contingency_id": "1003-1004-1",
            "violation_kind": "thermal_overload",
            "element_type": "branch",
            "element_id": "1001-1002-1",
            "city": "AUSTIN",
            "limit_value": limit_value,
            "observed_value": observed,
            "exceeded_by": observed - limit_value,
            "unit": "MVA",
            "details": None,
        },
        {
            "contingency_id": "1005-1006-1",
            "violation_kind": "voltage_low",
            "element_type": "bus",
            "element_id": "2001",
            "city": None,
            "limit_value": 0.95,
            "observed_value": 0.92,
            "exceeded_by": 0.03,
            "unit": "pu",
            "details": None,
        },
    ]
    results = contract.StudyResults(
        dispatch=dispatch_rows, margins=margin_rows, contingencies=contingency_rows,
        n_contingencies=3, rate_set="RATEA", psse_version=SYNTHETIC_JOB_VERSION,
    )
    run_record.validate_results(results, selection)
    context = contract.RunContext(
        run_id=run_record.new_run_id(now), started_at=now, case_id=SYNTHETIC_CASE_ID,
        case_sha256=None, mapping_sha256=None, job_version=SYNTHETIC_JOB_VERSION,
    )
    record = run_record.build_run_record(context, selection, now + datetime.timedelta(seconds=1), results=results)
    return selection, record, run_record.result_rows(record, results)


def _count_run(conn, run_id):
    """(rows of the run in psse_run, dispatch, margin, contingency); the table names are constants."""
    counts = []
    for table in _PROOF_TABLES:
        counts.append(conn.execute("select count(*) from %s where run_id = %%s" % table, [run_id]).fetchone()[0])
    return tuple(counts)


def _describe(counts):
    return ", ".join("%s %d" % (label, count) for label, count in zip(_PROOF_LABELS, counts))


def write_proof(conn, now=None, env=None):
    """
    The opt-in write proof: write a complete synthetic run (synthetic_run) with writer.write_run
    inside a transaction forced to roll back, count its rows inside the block, leave the block and
    count them again. Two rows: the inside counts must equal the run's 1, 4, 4 and 2 rows, and no
    row may survive. A failure of the write (a redacted message) is a FAIL row, and the count after
    the block is taken anyway. `env` names the secrets to redact (default: the process environment).
    """
    now = datetime.datetime.now(datetime.timezone.utc) if now is None else now
    _selection, record, rows = synthetic_run(now)
    run_id = record["run_id"]
    expected = (1,) + tuple(len(rows[table]) for table in contract.RESULT_TABLES)
    secrets = None if env is None else env_secrets(env)

    inside = None
    failure = None
    try:
        with conn.transaction(force_rollback=True):
            writer.write_run(conn, record, rows)
            inside = _count_run(conn, run_id)
    except Exception as exc:  # noqa: BLE001 - reported below as redacted text
        failure = "%s: %s" % (type(exc).__name__, redact(str(exc), secrets, constants.ERROR_MAX_CHARS))
    result = []
    if failure is not None:
        result.append(CheckRow(_WRITE_PROOF_INSIDE, FAIL, "the synthetic run could not be written: " + failure))
    elif inside == expected:
        result.append(CheckRow(
            _WRITE_PROOF_INSIDE, PASS, "inside the rolled-back transaction: " + _describe(inside)))
    else:
        result.append(CheckRow(
            _WRITE_PROOF_INSIDE, FAIL,
            "inside the transaction: " + _describe(inside) + "; expected: " + _describe(expected)))

    after = None
    after_failure = None
    try:
        after = _count_run(conn, run_id)
    except Exception as exc:  # noqa: BLE001 - only the class is kept
        after_failure = type(exc).__name__
    if after_failure is not None:
        result.append(CheckRow(_WRITE_PROOF_AFTER, FAIL, "the rows could not be counted after the rollback (%s)" % after_failure))
    elif any(after):
        result.append(CheckRow(_WRITE_PROOF_AFTER, FAIL, "rows survived the rollback: " + _describe(after)))
    else:
        result.append(CheckRow(_WRITE_PROOF_AFTER, PASS, "after the rollback: " + _describe(after)))
    return result


# Kept under another name because `run` has a parameter called write_proof.
_run_write_proof = write_proof


# --------------------------------------------------------------------------- run


def run(env, skip_rest=False, write_proof=False, out=None, connect=None, opener=None):
    """
    Run the credential proof and print the report; return 0 when no row is a FAIL, else 6. Order:
    the role leg on the job's own connection, the REST leg (one `rest:skipped` SKIP row when
    `skip_rest`; a missing SUPABASE_URL or key is a FAIL, not a skip), and the write proof only when
    `write_proof` is true. A connection that cannot be made, or an error while running, prints one
    redacted line ("credential check could not run: ...") and returns 6. `env` is the configuration
    dict; `connect` and `opener` are test seams (defaults writer.connect(env=env) and urlopen); `out`
    defaults to sys.stdout. The connection is closed in a finally block.
    """
    env = os.environ if env is None else env
    out = sys.stdout if out is None else out
    if connect is None:
        def connect():
            return writer.connect(env=env)

    conn = None
    failure = None
    rows = []
    try:
        conn = connect()
        rows.extend(role_checks(conn))
        if skip_rest:
            rows.append(CheckRow("rest:skipped", SKIP, "skip_rest was requested"))
        else:
            rows.extend(rest_checks(env, opener=opener))
        if write_proof:
            rows.extend(_run_write_proof(conn, env=env))
    except Exception as exc:  # noqa: BLE001 - reported below as one redacted line
        failure = redact(str(exc), env_secrets(env), constants.ERROR_MAX_CHARS) or type(exc).__name__
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    if failure is not None:
        out.write("credential check could not run: %s\n" % failure)
        return EXIT_CHECK_FAILED
    out.write(format_report(rows) + "\n")
    return EXIT_OK if checks_ok(rows) else EXIT_CHECK_FAILED
