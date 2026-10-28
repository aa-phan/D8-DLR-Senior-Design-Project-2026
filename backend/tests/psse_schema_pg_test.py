"""
Local-Postgres proofs of the reference DDL for the PSS/E result tables
(pss-e-integration Phase 1, DBX-01, WB-01, WB-02).

The reference DDL (docs/data-science/schema/psse_results_v1.sql) is applied, after the two
Phase 4 migrations, to a throwaway local Postgres that carries Supabase's legacy default
grants. The tests connect as the DDL's own `dlr_psse_writer` role and show what it can and
cannot do.

Skipped unless `DLR_TEST_PG_AUTOSTART=1` (the fixture runs initdb and pg_ctl under pytest's
tmp dir and stops the cluster afterwards) or `DLR_TEST_DATABASE_URL` names a local
throwaway database (host 127.0.0.1, localhost or ::1; anything else fails the test). With
`PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping. They
never touch Supabase.

Follows backend/tests/supabase_live_test.py's conventions (module-level imports, plain
asserts, no test classes, no network).
"""

import math
import re
from datetime import datetime, timezone

import pytest

import psse_local_pg as pg_helper

WRITER = "dlr_psse_writer"
STARTED = datetime(2026, 10, 28, 14, 7, 30, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a database that already carries the Phase 4 migrations and the reference DDL."""
    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_schema(admin_url)
        yield admin_url


@pytest.fixture
def clean_pg(pg):
    """The same database with the four result tables empty."""
    pg_helper.reset(pg)
    return pg


def _writer(admin_url, time_zone=None):
    """An autocommit connection as dlr_psse_writer (trust auth, no credential locally)."""
    import psycopg

    conn = psycopg.connect(pg_helper.role_url(admin_url, WRITER), autocommit=True)
    if time_zone:
        conn.execute("set time zone '" + time_zone + "'")
    return conn


def test_ddl_round_trip_one_complete_run(clean_pg):
    """One transaction writes a run plus 4 + 4 + 2 result rows; the same role reads them back."""
    run_id = pg_helper.make_run_id(1, STARTED)
    rows = pg_helper.valid_run_rows(run_id, STARTED, outcome="fallback", violations=2)
    with _writer(clean_pg) as conn:
        with conn.transaction():
            for table in pg_helper.RESULT_TABLES:
                pg_helper.insert_rows(conn, table, rows[table])
        counts = [
            conn.execute("select count(*) from public." + table + " where run_id = %s", (run_id,)).fetchone()[0]
            for table in pg_helper.RESULT_TABLES
        ]
        run = conn.execute(
            "select outcome, slot_time, started_at from public.psse_run where run_id = %s", (run_id,)
        ).fetchone()
    assert counts == [1, 4, 4, 2]
    assert run[0] == "fallback"
    assert run[1] == datetime(2026, 10, 28, 14, 0, 0, tzinfo=timezone.utc)
    assert run[2] == STARTED


# --------------------------------------------------------------------------- helpers

_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


def _error_class(name):
    import psycopg

    return getattr(psycopg.errors, name)


def _count(admin_url, table, run_id):
    return pg_helper.admin_rows(
        admin_url, "select count(*) as n from public." + table + " where run_id = %s", (run_id,)
    )[0]["n"]


def _insert_run(admin_url, run_row):
    """Commit one psse_run row as the writer (the parent every child row needs)."""
    with _writer(admin_url) as conn:
        with conn.transaction():
            pg_helper.insert_rows(conn, "psse_run", [run_row])


def _rejected(admin_url, table, row, error_name, constraint=None, time_zone=None):
    """Insert one row as the writer; it must raise `error_name` (and name `constraint` when given)."""
    with _writer(admin_url, time_zone) as conn:
        with pytest.raises(_error_class(error_name)) as caught:
            with conn.transaction():
                pg_helper.insert_rows(conn, table, [row])
    if constraint is not None:
        assert caught.value.diag.constraint_name == constraint


def _accepted(admin_url, table, row, time_zone=None):
    with _writer(admin_url, time_zone) as conn:
        with conn.transaction():
            pg_helper.insert_rows(conn, table, [row])


def _privilege_matrix(admin_url, role):
    """{table: sorted privileges `role` holds}, from has_table_privilege."""
    version = pg_helper.admin_rows(admin_url, "select current_setting('server_version_num')::int as v")[0]["v"]
    privileges = _PRIVILEGES + (("MAINTAIN",) if version >= 170000 else ())
    matrix = {}
    for table in pg_helper.RESULT_TABLES:
        held = []
        for privilege in privileges:
            row = pg_helper.admin_rows(
                admin_url, "select has_table_privilege(%s, %s, %s) as held",
                (role, "public." + table, privilege),
            )[0]
            if row["held"]:
                held.append(privilege)
        matrix[table] = sorted(held)
    return matrix


def _sample_run(admin_url, n, outcome="fallback", violations=2):
    """Commit one complete run as the writer; return its run_id."""
    run_id = pg_helper.make_run_id(n, STARTED)
    rows = pg_helper.valid_run_rows(run_id, STARTED, outcome=outcome, violations=violations)
    with _writer(admin_url) as conn:
        with conn.transaction():
            for table in pg_helper.RESULT_TABLES:
                pg_helper.insert_rows(conn, table, rows[table])
    return run_id


# --------------------------------------------------------------------------- privileges (D-03)


def test_privileges_writer_has_exactly_insert_and_select(clean_pg):
    matrix = _privilege_matrix(clean_pg, WRITER)
    assert matrix == {table: ["INSERT", "SELECT"] for table in pg_helper.RESULT_TABLES}
    for table in pg_helper.RESULT_TABLES:
        for privilege in ("UPDATE", "REFERENCES"):
            row = pg_helper.admin_rows(
                clean_pg, "select has_any_column_privilege(%s, %s, %s) as held",
                (WRITER, "public." + table, privilege),
            )[0]
            assert row["held"] is False, (table, privilege)


def test_privileges_writer_cannot_update_delete_or_truncate(clean_pg):
    run_id = _sample_run(clean_pg, 2)
    with _writer(clean_pg) as conn:
        for statement in (
            "update public.psse_run set job_version = 'changed'",
            "delete from public.psse_run",
            "truncate public.psse_contingency_result",
        ):
            with pytest.raises(_error_class("InsufficientPrivilege")):
                conn.execute(statement)
    runs = pg_helper.admin_rows(clean_pg, "select job_version from public.psse_run where run_id = %s", (run_id,))
    assert [row["job_version"] for row in runs] == ["abc1234"]
    assert _count(clean_pg, "psse_contingency_result", run_id) == 2


def test_privileges_writer_has_nothing_on_city_rating_pipeline_run_or_latest_rating(clean_pg):
    # Phase 6's real latest_rating view is not built yet; the point is that the writer has no grant on it.
    import psycopg

    with psycopg.connect(clean_pg, autocommit=True) as admin:
        admin.execute("drop view if exists public.latest_rating")
        admin.execute("create view public.latest_rating as select * from public.city_rating")
    try:
        with _writer(clean_pg) as conn:
            for statement in (
                "select * from public.city_rating",
                "select * from public.pipeline_run",
                "select * from public.latest_rating",
                "insert into public.city_rating (city) values ('AUSTIN')",
                "update public.city_rating set rating_amps = 1",
            ):
                with pytest.raises(_error_class("InsufficientPrivilege")):
                    conn.execute(statement)
    finally:
        with psycopg.connect(clean_pg, autocommit=True) as admin:
            admin.execute("drop view if exists public.latest_rating")


def test_privileges_anon_and_authenticated_have_nothing(clean_pg):
    import psycopg

    _sample_run(clean_pg, 3)
    for role in ("anon", "authenticated"):
        assert _privilege_matrix(clean_pg, role) == {table: [] for table in pg_helper.RESULT_TABLES}
        for table in pg_helper.RESULT_TABLES:
            row = pg_helper.admin_rows(
                clean_pg,
                "select has_any_column_privilege(%s, %s, 'SELECT') or has_any_column_privilege(%s, %s, 'INSERT') "
                "or has_any_column_privilege(%s, %s, 'UPDATE') as held",
                (role, "public." + table) * 3,
            )[0]
            assert row["held"] is False, (role, table)
        with psycopg.connect(clean_pg, autocommit=True) as conn:
            conn.execute("set role " + role)
            try:
                with pytest.raises(_error_class("InsufficientPrivilege")):
                    conn.execute("select * from public.psse_run")
            finally:
                conn.execute("reset role")


def test_privileges_role_attributes_and_no_functions(clean_pg):
    role = pg_helper.admin_rows(
        clean_pg,
        "select rolcanlogin, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication "
        "from pg_roles where rolname = %s",
        (WRITER,),
    )
    assert role == [{
        "rolcanlogin": True, "rolsuper": False, "rolcreaterole": False,
        "rolcreatedb": False, "rolbypassrls": False, "rolreplication": False,
    }]
    # Neither the Phase 4 migrations nor the reference DDL create a function, so nothing can
    # be auto-granted EXECUTE to the API roles.
    functions = pg_helper.admin_rows(
        clean_pg,
        "select count(*) as n from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'public'",
    )
    assert functions[0]["n"] == 0


# --------------------------------------------------------------------------- integrity (WB-01, WB-02, D-06)


def test_integrity_failed_run_cannot_carry_results(clean_pg):
    run_id = pg_helper.make_run_id(4, STARTED)
    _insert_run(clean_pg, pg_helper.failed_run_row(run_id, STARTED))
    dispatch = pg_helper.valid_run_rows(run_id, STARTED)["psse_dispatched_capacity"][0]
    _rejected(clean_pg, "psse_dispatched_capacity", dict(dispatch, run_outcome="failed"), "CheckViolation",
              "psse_dispatched_capacity_run_outcome_ck")
    _rejected(clean_pg, "psse_dispatched_capacity", dict(dispatch, run_outcome="ok"), "ForeignKeyViolation",
              "psse_dispatched_capacity_run_fk")
    for table in pg_helper.RESULT_TABLES[1:]:
        assert _count(clean_pg, table, run_id) == 0


_RUN_RECORD_CASES = [
    ("failed_without_error", {"outcome": "failed", "failed_stage": "load_flow", "error": None},
     "CheckViolation", "psse_run_failed_fields_ck"),
    ("failed_without_stage", {"outcome": "failed", "failed_stage": None, "error": "boom"},
     "CheckViolation", "psse_run_failed_fields_ck"),
    ("fallback_with_error", {"error": "boom"}, "CheckViolation", "psse_run_failed_fields_ck"),
    ("error_of_1001_characters", {"outcome": "failed", "failed_stage": "write", "error": "x" * 1001},
     "CheckViolation", "psse_run_error_ck"),
    ("ratings_used_missing_el_paso", {"ratings_used": {"AUSTIN": {}, "CORPUS_CHRISTI": {}, "MIDLAND": {}}},
     "CheckViolation", "psse_run_ratings_used_ck"),
    ("ratings_used_is_an_array", {"ratings_used": ["AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"]},
     "CheckViolation", "psse_run_ratings_used_ck"),
    ("finished_one_second_before_start", {"finished_at": STARTED.replace(second=29)},
     "CheckViolation", "psse_run_finished_ck"),
    ("slot_one_hour_after_the_floor", {"slot_time": STARTED.replace(hour=15, minute=0, second=0)},
     "CheckViolation", "psse_run_slot_matches_start_ck"),
    ("run_id_not_matching_pattern", {"run_id": "psse-20261028T140730Z-ABCDEF12"},
     "CheckViolation", "psse_run_run_id_ck"),
    ("case_id_with_slash", {"case_id": "cases/summer_peak"}, "CheckViolation", "psse_run_case_id_ck"),
    ("case_id_with_backslash", {"case_id": "cases" + chr(92) + "summer_peak"},
     "CheckViolation", "psse_run_case_id_ck"),
    ("case_sha256_upper_case", {"case_sha256": "ABCDEF0123456789" * 4},
     "CheckViolation", "psse_run_case_sha256_ck"),
    ("non_failed_without_n_contingencies", {"n_contingencies": None},
     "CheckViolation", "psse_run_counts_present_ck"),
    ("with_results_above_n_contingencies", {"n_contingencies": 3, "n_contingencies_with_results": 4},
     "CheckViolation", "psse_run_counts_order_ck"),
    ("case_id_missing", {"case_id": None}, "NotNullViolation", None),
]


@pytest.mark.parametrize(
    "changes, error_name, constraint",
    [case[1:] for case in _RUN_RECORD_CASES],
    ids=[case[0] for case in _RUN_RECORD_CASES],
)
def test_integrity_run_record_rules(clean_pg, changes, error_name, constraint):
    run_id = pg_helper.make_run_id(5, STARTED)
    row = dict(pg_helper.valid_run_rows(run_id, STARTED)["psse_run"][0], **changes)
    _rejected(clean_pg, "psse_run", row, error_name, constraint)
    assert _count(clean_pg, "psse_run", row["run_id"]) == 0


def test_integrity_slot_time_and_edges(clean_pg):
    """The UTC hour rule holds in a session at +05:30, on a whole-hour start and at the last microsecond."""
    zone = "+05:30"
    on_the_hour = datetime(2026, 10, 28, 14, 0, 0, tzinfo=timezone.utc)
    row = pg_helper.valid_run_rows(pg_helper.make_run_id(6, on_the_hour), on_the_hour)["psse_run"][0]
    row["finished_at"] = on_the_hour  # finished_at equal to started_at is accepted
    assert row["slot_time"] == on_the_hour
    _accepted(clean_pg, "psse_run", row, zone)

    half_hour = dict(row, run_id=pg_helper.make_run_id(7, on_the_hour), slot_time=on_the_hour.replace(minute=30))
    _rejected(clean_pg, "psse_run", half_hour, "CheckViolation", time_zone=zone)

    last_instant = datetime(2026, 10, 28, 14, 59, 59, 999999, tzinfo=timezone.utc)
    late = pg_helper.valid_run_rows(pg_helper.make_run_id(8, last_instant), last_instant)["psse_run"][0]
    assert late["slot_time"] == on_the_hour
    _accepted(clean_pg, "psse_run", late, zone)

    stored = pg_helper.admin_rows(clean_pg, "select run_id, slot_time from public.psse_run order by run_id")
    assert [r["slot_time"] for r in stored] == [on_the_hour, on_the_hour]


def _recompute(row, applied_mva, voltage_limit_mva, limiting_factor):
    """A dispatch row whose derived columns follow `applied_mva` and `voltage_limit_mva`."""
    dispatched = min(applied_mva, voltage_limit_mva)
    circuit = dispatched * 1000 / (math.sqrt(3) * row["line_voltage_kv"])
    return dict(
        row,
        applied_mva=applied_mva,
        voltage_limit_mva=voltage_limit_mva,
        dispatched_mva=dispatched,
        dispatched_amps_circuit=circuit,
        dispatched_amps_per_conductor=circuit / row["subconductors_per_phase"],
        dispatched_mw=dispatched * row["power_factor"],
        limiting_factor=limiting_factor,
    )


# (id, run outcome, row change, error name or None when accepted, constraint or None)
_DISPATCH_CASES = [
    ("power_factor_trap", "fallback",
     lambda r: _recompute(r, r["applied_mva"] * 0.95, r["voltage_limit_mva"], "dlr_rating"),
     "CheckViolation", "psse_dispatched_capacity_applied_mva_identity_ck"),
    ("circuit_amps_not_conductor_times_subconductors", "fallback",
     lambda r: dict(r, subconductors_per_phase=r["subconductors_per_phase"] + 1),
     "CheckViolation", None),
    ("dispatched_above_the_lower_limit", "fallback",
     lambda r: dict(r, dispatched_mva=r["applied_mva"] * 1.5),
     "CheckViolation", None),
    ("tie_labelled_voltage_stability", "fallback",
     lambda r: _recompute(r, r["applied_mva"], r["applied_mva"], "voltage_stability"),
     "CheckViolation", "psse_dispatched_capacity_limiting_factor_rule_ck"),
    ("tie_labelled_dlr_rating_is_accepted", "fallback",
     lambda r: _recompute(r, r["applied_mva"], r["applied_mva"], "dlr_rating"),
     None, None),
    ("nan_applied_mva", "fallback", lambda r: dict(r, applied_mva=float("nan")), "CheckViolation", None),
    ("infinite_applied_mva", "fallback", lambda r: dict(r, applied_mva=float("inf")), "CheckViolation", None),
    ("city_rating_without_link_time", "ok", lambda r: dict(r, city_rating_valid_time=None),
     "CheckViolation", "psse_dispatched_capacity_link_rule_ck"),
    ("static_fallback_without_reason", "fallback", lambda r: dict(r, fallback_reason=None),
     "CheckViolation", "psse_dispatched_capacity_source_reason_rule_ck"),
    ("power_factor_above_one", "fallback", lambda r: dict(r, power_factor=1.2), "CheckViolation", None),
    ("zero_subconductors", "fallback", lambda r: dict(r, subconductors_per_phase=0), "CheckViolation", None),
]


@pytest.mark.parametrize(
    "outcome, change, error_name, constraint",
    [case[1:] for case in _DISPATCH_CASES],
    ids=[case[0] for case in _DISPATCH_CASES],
)
def test_integrity_dispatch_rules(clean_pg, outcome, change, error_name, constraint):
    run_id = pg_helper.make_run_id(9, STARTED)
    rows = pg_helper.valid_run_rows(run_id, STARTED, outcome=outcome)
    _insert_run(clean_pg, rows["psse_run"][0])
    row = change(rows["psse_dispatched_capacity"][0])
    if error_name is None:
        _accepted(clean_pg, "psse_dispatched_capacity", row)
        assert _count(clean_pg, "psse_dispatched_capacity", run_id) == 1
    else:
        _rejected(clean_pg, "psse_dispatched_capacity", row, error_name, constraint)
        assert _count(clean_pg, "psse_dispatched_capacity", run_id) == 0


def _non_convergence(run_id, outcome, **changes):
    row = {
        "run_id": run_id, "run_outcome": outcome, "contingency_id": "BR-301-302-1",
        "violation_kind": "non_convergence", "element_type": "contingency",
        "element_id": "BR-301-302-1", "city": None, "limit_value": None,
        "observed_value": None, "exceeded_by": None, "unit": None,
    }
    row.update(changes)
    return row


# (id, builder(thermal row, voltage_low row, run_id) -> row, error name or None, constraint or None)
_CONTINGENCY_CASES = [
    ("exceeded_by_zero", lambda t, v, run_id: dict(t, exceeded_by=0.0), "CheckViolation", None),
    ("thermal_overload_in_per_unit", lambda t, v, run_id: dict(t, unit="pu"),
     "CheckViolation", "psse_contingency_result_kind_shape_rule_ck"),
    ("voltage_low_exceeded_by_wrong_sign",
     lambda t, v, run_id: dict(v, exceeded_by=v["observed_value"] - v["limit_value"]), "CheckViolation", None),
    ("non_convergence_with_a_limit",
     lambda t, v, run_id: _non_convergence(run_id, t["run_outcome"], limit_value=1.0),
     "CheckViolation", "psse_contingency_result_kind_shape_rule_ck"),
    ("non_convergence_element_differs_from_contingency",
     lambda t, v, run_id: _non_convergence(run_id, t["run_outcome"], element_id="BR-999-998-1"),
     "CheckViolation", "psse_contingency_result_kind_shape_rule_ck"),
    ("valid_non_convergence_is_accepted",
     lambda t, v, run_id: _non_convergence(run_id, t["run_outcome"]), None, None),
]


@pytest.mark.parametrize(
    "build, error_name, constraint",
    [case[1:] for case in _CONTINGENCY_CASES],
    ids=[case[0] for case in _CONTINGENCY_CASES],
)
def test_integrity_contingency_rules(clean_pg, build, error_name, constraint):
    run_id = pg_helper.make_run_id(10, STARTED)
    rows = pg_helper.valid_run_rows(run_id, STARTED, violations=2)
    _insert_run(clean_pg, rows["psse_run"][0])
    thermal, low = rows["psse_contingency_result"]
    row = build(thermal, low, run_id)
    if error_name is None:
        _accepted(clean_pg, "psse_contingency_result", row)
        assert _count(clean_pg, "psse_contingency_result", run_id) == 1
    else:
        _rejected(clean_pg, "psse_contingency_result", row, error_name, constraint)
        assert _count(clean_pg, "psse_contingency_result", run_id) == 0


def test_integrity_duplicate_result_key_is_rejected(clean_pg):
    run_id = pg_helper.make_run_id(11, STARTED)
    rows = pg_helper.valid_run_rows(run_id, STARTED, violations=1)
    _insert_run(clean_pg, rows["psse_run"][0])
    contingency = rows["psse_contingency_result"][0]
    _accepted(clean_pg, "psse_contingency_result", contingency)
    duplicate = dict(contingency, limit_value=2000.0, observed_value=2100.0, exceeded_by=100.0)
    _rejected(clean_pg, "psse_contingency_result", duplicate, "UniqueViolation", "psse_contingency_result_pk")
    margin = rows["psse_voltage_margin"][0]
    _accepted(clean_pg, "psse_voltage_margin", margin)
    _rejected(clean_pg, "psse_voltage_margin", dict(margin, margin_mw=1.0), "UniqueViolation",
              "psse_voltage_margin_pk")
    assert _count(clean_pg, "psse_contingency_result", run_id) == 1
    assert _count(clean_pg, "psse_voltage_margin", run_id) == 1


def test_ddl_is_reapply_safe(clean_pg):
    roles = (WRITER, "anon", "authenticated")
    before = {role: _privilege_matrix(clean_pg, role) for role in roles}
    pg_helper.apply_reference_ddl(clean_pg)
    after = {role: _privilege_matrix(clean_pg, role) for role in roles}
    assert before == after
    policies = pg_helper.admin_rows(
        clean_pg,
        "select tablename, policyname from pg_policies "
        "where schemaname = 'public' and tablename like 'psse%' order by tablename, policyname",
    )
    expected = []
    for table in sorted(pg_helper.RESULT_TABLES):
        expected.append({"tablename": table, "policyname": "dlr_psse_writer_insert"})
        expected.append({"tablename": table, "policyname": "dlr_psse_writer_select"})
    assert policies == expected


# --------------------------------------------------------------------------- completeness checks (WB-02)

_CHECK_NAMES = [
    "non_failed_runs_have_four_dispatch_rows",
    "non_failed_runs_have_four_margin_rows",
    "non_failed_runs_contingency_count_matches",
    "failed_runs_have_no_results",
    "dispatch_voltage_limit_matches_margin",
]


def _run_checks(conn):
    with open(pg_helper.CHECKS_SQL, encoding="utf-8") as handle:
        sql = handle.read()
    return [(row[0], row[1], row[2]) for row in conn.execute(sql).fetchall()]


def test_checks_pass_on_complete_runs(clean_pg):
    _sample_run(clean_pg, 12, outcome="fallback", violations=2)
    zero = _sample_run(clean_pg, 13, outcome="ok", violations=0)  # the zero-violation edge
    failed_id = pg_helper.make_run_id(14, STARTED)
    _insert_run(clean_pg, pg_helper.failed_run_row(failed_id, STARTED))
    stored = pg_helper.admin_rows(
        clean_pg, "select n_contingencies_with_results as n from public.psse_run where run_id = %s", (zero,)
    )
    assert stored == [{"n": 0}]
    assert _count(clean_pg, "psse_contingency_result", zero) == 0
    with _writer(clean_pg) as conn:
        results = _run_checks(conn)
    assert [name for name, _, _ in results] == _CHECK_NAMES
    assert all(ok is True for _, ok, _ in results), results
    assert all(detail == "offending runs: 0" for _, _, detail in results)


def test_checks_flag_a_partial_run(clean_pg):
    run_id = pg_helper.make_run_id(15, STARTED)
    rows = pg_helper.valid_run_rows(run_id, STARTED, violations=0)
    with _writer(clean_pg) as conn:
        with conn.transaction():
            pg_helper.insert_rows(conn, "psse_run", rows["psse_run"])
        with conn.transaction():
            pg_helper.insert_rows(conn, "psse_dispatched_capacity", rows["psse_dispatched_capacity"][:3])
            pg_helper.insert_rows(conn, "psse_voltage_margin", rows["psse_voltage_margin"])
        results = {name: (ok, detail) for name, ok, detail in _run_checks(conn)}
    ok, detail = results["non_failed_runs_have_four_dispatch_rows"]
    assert ok is False
    assert run_id in detail
    assert results["non_failed_runs_have_four_margin_rows"][0] is True
    assert results["failed_runs_have_no_results"][0] is True


def test_checks_sql_is_read_only():
    with open(pg_helper.CHECKS_SQL, encoding="utf-8") as handle:
        text = handle.read()
    body = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    # A semicolon inside a string literal (the detail text has one) is not a statement end.
    without_literals = re.sub(r"'[^']*'", "''", body)
    statements = [part.strip() for part in without_literals.split(";") if part.strip()]
    assert len(statements) == 1
    assert re.match(r"(?i)(with|select)\b", statements[0])
    forbidden = re.findall(r"(?i)\b(insert|update|delete|create|drop|grant|alter|truncate)\b", body)
    assert forbidden == []
