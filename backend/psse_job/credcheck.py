"""
The DBX-02 credential proof of the PSS/E job (pss-e-integration Phase 3, plan 03-03).

DBX-02 says the job writes only to the PSS/E result tables and cannot change `city_rating`. The
role leg, `role_checks`, shows with the job's own database credential that `dlr_psse_writer` can
insert into and select from the four result tables and holds nothing else: six catalog checks
(role attributes, role memberships, INSERT and SELECT on the four tables, nothing more on them,
nothing on any other relation of schema public, no executable SECURITY DEFINER function in
public) and seven statements that must be refused with SQLSTATE 42501.

Safe by construction. The catalog checks only read. Every active statement is a where-false
statement run inside a transaction that is forced to roll back, so a credential that is too
powerful still changes no row. Only SQLSTATE 42501 counts as a refusal: any other error (a
missing relation, a read-only session, a timeout) is a FAIL as inconclusive, and success is a FAIL
because the statement was allowed. The session is deliberately NOT read-only: PostgreSQL checks
a read-only transaction before it checks privileges, so every statement would be refused with
25006 whatever the role may do, and the proof would pass for the wrong reason.

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
# is allowed to run them changes no row, and each runs in a transaction forced to roll back.
REFUSED_STATEMENTS = (
    ("refused:select_city_rating", "select * from public.city_rating where false"),
    ("refused:insert_city_rating",
     "insert into public.city_rating (city) select city from public.city_rating where false"),
    ("refused:update_city_rating", "update public.city_rating set rating_amps = rating_amps where false"),
    ("refused:delete_city_rating", "delete from public.city_rating where false"),
    ("refused:select_pipeline_run", "select * from public.pipeline_run where false"),
    ("refused:update_psse_run", "update public.psse_run set job_version = job_version where false"),
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
