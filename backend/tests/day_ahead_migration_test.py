"""
Tests of the day-ahead write-side migration and the owner's store check (production-pipeline
Phase 8, plan 08-04: DAY-05, D-09, D-11; threats T-08-10, T-08-13).

`supabase/migrations/20261108120000_day_ahead_forecast_store.sql` is read as text (its column
list, constraints, grants and comments are compared with `day_ahead_contract`), then applied to a
throwaway local Postgres and exercised as the roles that matter: `dlr_writer` (select and insert
only), `anon` and `authenticated` (nothing). The local database is migrated only through the
write-side file, because the expose migration 08-09 adds later grants anon SELECT and these tests
must keep proving the state the owner applies in 08-07.

`supabase/ops/verify_day_ahead_store.sql` is the one read-only SELECT the owner runs after that
apply; it is run here on the same database. Nothing here touches the live Supabase project, a
remote or the network.

The local-Postgres tests need `DLR_TEST_PG_AUTOSTART=1` (backend/tests/local_pg.py). A skip proves
nothing, so the plan's verify command treats a skip as a failure.
"""

import glob
import hashlib
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

import day_ahead_contract as contract
import local_pg
import supabase_store

_MIGRATIONS_DIR = local_pg.MIGRATIONS_DIR
_STORE_MIGRATION = "20261108120000_day_ahead_forecast_store.sql"
_STORE_PATH = os.path.join(_MIGRATIONS_DIR, _STORE_MIGRATION)
_VERIFY_SQL = os.path.join(local_pg.REPO_ROOT, "supabase", "ops", "verify_day_ahead_store.sql")

# Applied to the live project by the owner on 2026-11-08 (plan 08-07); the file may not be edited afterwards.
_APPLIED_STORE_MIGRATION_SHA256 = {
    "20261108120000_day_ahead_forecast_store.sql": "fb5337a64318259320990fa7b7b19c32d584bcdefef24fad8b1855f0e21bf8f1",
}

# The check names the owner sees after the apply (08-07), pinned so a removed check is a test failure.
_STORE_VERIFY_CHECKS = (
    "day_ahead_forecast_columns_all_commented",
    "day_ahead_forecast_exists",
    "day_ahead_forecast_has_25_columns",
    "day_ahead_forecast_not_readable_by_anon_or_authenticated",
    "day_ahead_forecast_primary_key_city_valid_time",
    "day_ahead_forecast_rls_enabled",
    "dlr_writer_can_select_and_insert_day_ahead_forecast",
    "dlr_writer_cannot_update_delete_or_truncate_day_ahead_forecast",
    "pipeline_run_has_day_ahead_jsonb",
    "pipeline_run_not_readable_by_anon",
)

# Comment bodies are blanked before keyword checks, so a word inside a comment never counts.
_COMMENT_RE = re.compile(
    r"(comment\s+on\s+(?:table|column|view|function)\s+[\w.]+(?:\([^)]*\))?\s+is\s+)'(?:[^']|'')*'", re.IGNORECASE
)
_COMMENT_BODY_RE = re.compile(r"comment on (table|column) ([\w.]+) is '((?:[^']|'')*)'", re.IGNORECASE)


def _raw(path=_STORE_PATH):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _code(path=_STORE_PATH):
    """The file with comment bodies blanked and `--` comments removed."""
    text = _COMMENT_RE.sub(r"\1''", _raw(path))
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def _statements(path=_STORE_PATH):
    """Statements of `_code()`, whitespace-normalised, split on `;` outside `$$ ... $$`."""
    code = _code(path)
    out, buffer, in_dollar, i = [], [], False, 0
    while i < len(code):
        if code.startswith("$$", i):
            in_dollar = not in_dollar
            buffer.append("$$")
            i += 2
            continue
        char = code[i]
        if char == ";" and not in_dollar:
            statement = " ".join("".join(buffer).split())
            if statement:
                out.append(statement)
            buffer = []
        else:
            buffer.append(char)
        i += 1
    tail = " ".join("".join(buffer).split())
    if tail:
        out.append(tail)
    return out


def _table_block():
    match = re.search(r"create table if not exists public\.day_ahead_forecast \(\n(.*?)\n\);", _code(), re.DOTALL)
    assert match, "no create table block for day_ahead_forecast"
    return match.group(1)


_COLUMN_RE = re.compile(r"^\s*(\w+)\s+(double precision|text|timestamptz|integer|boolean|jsonb)(?=\s|,|$)")


def _table_columns():
    columns = []
    for line in _table_block().splitlines():
        if not line.strip() or line.strip().startswith("constraint "):
            continue
        match = _COLUMN_RE.match(line)
        assert match, f"cannot parse column line: {line!r}"
        columns.append(match.group(1))
    return columns


def _constraints():
    """{constraint name: its definition text} for every named constraint in the create table block."""
    block = " ".join(_table_block().split())
    found = {}
    for match in re.finditer(r"constraint (\w+) (check \(.*?\)|primary key \(.*?\))(?=,? constraint |,? \w+ (?:text|timestamptz|integer|double)|$)", block):
        found[match.group(1)] = match.group(2)
    return found


def _comments():
    return {m.group(2): m.group(3) for m in _COMMENT_BODY_RE.finditer(_raw())}


# --------------------------------------------------------------------------------------------------
# text: what the file says
# --------------------------------------------------------------------------------------------------

def test_text_the_create_table_lists_exactly_the_contract_columns_in_order():
    assert tuple(_table_columns()) == contract.TABLE_COLUMNS
    assert len(contract.TABLE_COLUMNS) == 25


def test_text_the_named_checks_exist_for_every_rule_of_the_row():
    names = set(_constraints())
    expected = {
        "day_ahead_forecast_city_ck",
        "day_ahead_forecast_valid_time_hour_ck",
        "day_ahead_forecast_valid_time_grid_ck",
        "day_ahead_forecast_horizon_ck",
        "day_ahead_forecast_method_ck",
        "day_ahead_forecast_band_source_ck",
        "day_ahead_forecast_band_pairs_through_ck",
        "day_ahead_forecast_band_artifact_sha256_ck",
        "day_ahead_forecast_cooling_model_sha256_ck",
        "day_ahead_forecast_config_fingerprint_ck",
        "day_ahead_forecast_label_ck",
        "day_ahead_forecast_issued_before_valid_ck",
        "day_ahead_forecast_band_contains_point_ck",
        "day_ahead_forecast_pk",
    }
    assert expected <= names, sorted(expected - names)

    checks = _constraints()
    for city in ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"):
        assert f"'{city}'" in checks["day_ahead_forecast_city_ck"]
    assert "% 6 = 0" in checks["day_ahead_forecast_valid_time_grid_ck"]
    assert "1440" in checks["day_ahead_forecast_horizon_ck"]
    assert "'ml_cooling_corrected'" in checks["day_ahead_forecast_method_ck"]
    for source in contract.BAND_SOURCES:
        assert f"'{source}'" in checks["day_ahead_forecast_band_source_ck"]
    assert "band_pairs_through is not null" in checks["day_ahead_forecast_band_pairs_through_ck"]
    for name in ("band_artifact_sha256", "cooling_model_sha256", "config_fingerprint"):
        assert "[0-9a-f]{64}" in checks[f"day_ahead_forecast_{name}_ck"]
    assert "<> ''" in checks["day_ahead_forecast_label_ck"]
    assert "issued_at < valid_time" in checks["day_ahead_forecast_issued_before_valid_ck"]
    assert "forecast_ci_lower_amps <= forecast_amps" in checks["day_ahead_forecast_band_contains_point_ck"]
    assert "forecast_amps <= forecast_ci_upper_amps" in checks["day_ahead_forecast_band_contains_point_ck"]
    assert checks["day_ahead_forecast_pk"] == "primary key (city, valid_time)"


def test_text_the_statements_carry_exactly_the_planned_security_model():
    statements = _statements()
    lowered = [s.lower() for s in statements]
    assert "alter table public.day_ahead_forecast enable row level security" in lowered
    assert "revoke all on public.day_ahead_forecast from anon, authenticated" in lowered
    grants = [s for s in lowered if s.startswith("grant")]
    assert grants == ["grant usage on schema public to dlr_writer",
                      "grant select, insert on public.day_ahead_forecast to dlr_writer"]
    drop = lowered.index("drop policy if exists dlr_writer_all on public.day_ahead_forecast")
    create = next(i for i, s in enumerate(lowered) if s.startswith("create policy dlr_writer_all on public.day_ahead_forecast"))
    assert drop < create
    assert "alter table public.pipeline_run add column if not exists day_ahead jsonb" in lowered
    policies = [s for s in lowered if s.startswith("create policy")]
    assert len(policies) == 1 and " to dlr_writer " in policies[0] + " "


def test_text_the_file_grants_no_update_delete_truncate_and_holds_no_credential():
    code = _code().lower()
    for word in ("update", "delete", "truncate", "password", "bypassrls", "superuser", "service_role"):
        assert not re.search(rf"\b{word}\b", code), word
    assert not re.search(r"postgres(?:ql)?://", _raw(), re.IGNORECASE)
    assert " anon" not in " ".join(s for s in _statements() if s.lower().startswith(("grant", "create policy")))
    assert not re.search(r"\bto (?:anon|authenticated|public)\b", code)


_UNIT_FIRST = ("amperes", "UTC timestamp", "minutes", "count", "none (")


def test_text_every_column_and_the_run_log_column_have_a_non_empty_unit_first_comment():
    comments = _comments()
    expected = [f"public.day_ahead_forecast.{name}" for name in contract.TABLE_COLUMNS]
    expected.append("public.pipeline_run.day_ahead")
    for key in expected:
        text = comments.get(key, "")
        assert text.strip(), f"no comment for {key}"
        assert text.startswith(_UNIT_FIRST), (key, text)
    assert comments.get("public.day_ahead_forecast", "").strip()


def test_store_migration_is_unchanged_after_apply():
    # The file is applied to the live project; a later edit would make the repo disagree with it.
    for name, expected in _APPLIED_STORE_MIGRATION_SHA256.items():
        with open(os.path.join(_MIGRATIONS_DIR, name), "rb") as handle:
            assert hashlib.sha256(handle.read()).hexdigest() == expected, name


def test_text_the_file_sorts_after_the_soak_freshness_migration():
    assert _STORE_MIGRATION > "20261026204258_soak_freshness_log.sql"
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(_MIGRATIONS_DIR, "*.sql")))
    assert names.index(_STORE_MIGRATION) > names.index("20261026204258_soak_freshness_log.sql")


def test_text_every_optional_run_log_column_the_writer_names_is_added_by_a_migration():
    added = set()
    for path in glob.glob(os.path.join(_MIGRATIONS_DIR, "*.sql")):
        for statement in _statements(path):
            match = re.match(r"alter table public\.pipeline_run add column if not exists (\w+) ", statement.lower())
            if match:
                added.add(match.group(1))
    assert set(supabase_store.PIPELINE_RUN_OPTIONAL_COLUMNS) <= added


def test_text_the_store_check_is_one_read_only_select_with_the_pinned_check_names():
    raw = _raw(_VERIFY_SQL)
    code = "\n".join(line.split("--", 1)[0] for line in raw.splitlines())
    statements = [s.strip() for s in code.split(";") if s.strip()]
    assert len(statements) == 1
    statement = statements[0].lower()
    assert statement.startswith("with") and "select check_name, ok, detail" in statement
    # String literals are blanked first: the privilege names 'insert' and 'update' are arguments there.
    bare = re.sub(r"'(?:[^']|'')*'", "''", statement)
    for word in ("insert", "update", "delete", "truncate", "drop", "alter", "create", "grant", "revoke"):
        assert not re.search(rf"\b{word}\b", bare), word
    assert "check_name" in raw
    for name in _STORE_VERIFY_CHECKS:
        assert f"'{name}'" in raw, name


# --------------------------------------------------------------------------------------------------
# Local Postgres: the write-side migration only
# --------------------------------------------------------------------------------------------------

def _through_store(paths=None):
    paths = local_pg.migration_files() if paths is None else paths
    chosen = [p for p in paths if os.path.basename(p) <= _STORE_MIGRATION]
    assert os.path.basename(chosen[-1]) == _STORE_MIGRATION, [os.path.basename(p) for p in chosen]
    return chosen


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    local_pg.require_local_pg()
    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url, paths=_through_store())
        yield url


def _session(url, role=None):
    import psycopg

    conn = psycopg.connect(url, autocommit=True)
    conn.execute("set timezone = 'UTC'")
    if role:
        conn.execute(f"set role {role}")
    return conn


@pytest.fixture
def clean(pg_url):
    """An empty table and run log before the test."""
    with _session(pg_url) as admin:
        admin.execute("truncate public.day_ahead_forecast")
        admin.execute("delete from public.pipeline_run")
    return pg_url


_TARGET = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)


def _row(city="AUSTIN", valid_time=_TARGET, **overrides):
    """A complete valid row for the INSERT columns, derived from `valid_time`."""
    row = {
        "city": city,
        "valid_time": valid_time,
        "issued_at": valid_time - timedelta(hours=17),
        "forecast_run_init_time": valid_time - timedelta(hours=24),
        "horizon_minutes": 1440,
        "forecast_amps": 1700.0,
        "forecast_ci_lower_amps": 1500.0,
        "forecast_ci_upper_amps": 1850.0,
        "band_source": "test-split",
        "band_n": 196,
        "band_pairs_through": None,
        "band_artifact_sha256": "ab" * 32,
        "forecast_method": "ml_cooling_corrected",
        "cooling_model_sha256": "cd" * 32,
        "cooling_model_source": "refit",
        "anchor_observation_time": valid_time - timedelta(hours=17, minutes=5),
        "anchor_source": "tceq",
        "label": contract.DAY_AHEAD_LABEL,
        "config_version": "test-config",
        "config_fingerprint": "ef" * 32,
        "run_id": "run-1",
        "run_attempt": 1,
        "pipeline_version": "abc1234",
        "schema_version": 1,
    }
    row.update(overrides)
    assert tuple(row) == contract.INSERT_COLUMNS
    return row


_INSERT = (
    "insert into public.day_ahead_forecast (" + ", ".join(contract.INSERT_COLUMNS) + ") values ("
    + ", ".join(f"%({c})s" for c in contract.INSERT_COLUMNS) + ")"
)


def test_reapply_every_migration_twice_succeeds(tmp_path_factory):
    local_pg.require_local_pg()
    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url)
        local_pg.apply_migrations(url)
        with _session(url) as conn:
            assert conn.execute("select count(*) from information_schema.columns "
                                "where table_schema = 'public' and table_name = 'day_ahead_forecast'").fetchone()[0] == 25


def test_writer_can_insert_and_select_but_a_repeated_key_keeps_the_first_write(clean):
    with _session(clean, "dlr_writer") as writer:
        assert writer.execute(_INSERT + " on conflict (city, valid_time) do nothing", _row()).rowcount == 1
        second = _row(forecast_amps=1999.0, forecast_ci_upper_amps=2100.0, issued_at=_TARGET - timedelta(hours=1))
        assert writer.execute(_INSERT + " on conflict (city, valid_time) do nothing", second).rowcount == 0
        stored = writer.execute("select forecast_amps, issued_at, first_written_at is not null "
                                "from public.day_ahead_forecast").fetchall()
    assert stored == [(1700.0, _TARGET - timedelta(hours=17), True)]


def test_writer_cannot_update_or_delete_an_issued_row(clean):
    import psycopg

    with _session(clean, "dlr_writer") as writer:
        writer.execute(_INSERT, _row())
        for statement in ("update public.day_ahead_forecast set forecast_amps = 1.0",
                          "delete from public.day_ahead_forecast",
                          "truncate public.day_ahead_forecast"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege) as raised:
                writer.execute(statement)
            assert raised.value.sqlstate == "42501", statement
        assert writer.execute("select count(*) from public.day_ahead_forecast").fetchone()[0] == 1


_BAD_ROWS = [
    ("off the 6-hour grid (03:00Z)",
     lambda: _row(valid_time=datetime(2026, 11, 9, 3, 0, tzinfo=timezone.utc)),
     "day_ahead_forecast_valid_time_grid_ck"),
    ("not on the hour (06:30Z)",
     lambda: _row(valid_time=datetime(2026, 11, 9, 6, 30, tzinfo=timezone.utc)),
     "day_ahead_forecast_valid_time_hour_ck"),
    ("horizon 60", lambda: _row(horizon_minutes=60), "day_ahead_forecast_horizon_ck"),
    ("method raw_forecast", lambda: _row(forecast_method="raw_forecast"), "day_ahead_forecast_method_ck"),
    ("band source other", lambda: _row(band_source="other"), "day_ahead_forecast_band_source_ck"),
    ("empty label", lambda: _row(label=""), "day_ahead_forecast_label_ck"),
    ("lower above the point", lambda: _row(forecast_ci_lower_amps=1800.0),
     "day_ahead_forecast_band_contains_point_ck"),
    ("live-rolling without band_pairs_through",
     lambda: _row(band_source="live-rolling", band_pairs_through=None),
     "day_ahead_forecast_band_pairs_through_ck"),
]


@pytest.mark.parametrize("case, make_row, constraint", _BAD_ROWS, ids=[c[0] for c in _BAD_ROWS])
def test_checks_reject_a_row_that_breaks_a_rule_with_sqlstate_23514(clean, case, make_row, constraint):
    import psycopg

    with _session(clean, "dlr_writer") as writer:
        with pytest.raises(psycopg.errors.CheckViolation) as raised:
            writer.execute(_INSERT, make_row())
        assert raised.value.sqlstate == "23514", case
        assert raised.value.diag.constraint_name == constraint, case
        assert writer.execute("select count(*) from public.day_ahead_forecast").fetchone()[0] == 0


def test_checks_accept_the_valid_variants_of_the_same_rules(clean):
    with _session(clean, "dlr_writer") as writer:
        for hour in (0, 6, 12, 18):
            assert writer.execute(
                _INSERT, _row(valid_time=datetime(2026, 11, 9, hour, 0, tzinfo=timezone.utc))).rowcount == 1
        live = _row(city="MIDLAND", band_source="live-rolling", band_n=60,
                    band_pairs_through=_TARGET - timedelta(days=1))
        assert writer.execute(_INSERT, live).rowcount == 1


def test_anon_and_authenticated_cannot_read_the_table(clean):
    import psycopg

    with _session(clean, "dlr_writer") as writer:
        writer.execute(_INSERT, _row())
    for role in ("anon", "authenticated"):
        with _session(clean, role) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege) as raised:
                conn.execute("select * from public.day_ahead_forecast").fetchall()
            assert raised.value.sqlstate == "42501", role


def test_run_log_accepts_a_run_id_and_day_ahead_upsert_as_the_writer(clean):
    payload = {"started_at": "2026-11-09T00:05:00Z", "cities": {"MIDLAND": {"outcome": "issued", "issued": ["x"]}}}
    with _session(clean, "dlr_writer") as writer:
        supabase_store.upsert_run(writer, {"run_id": "run-day-ahead", "day_ahead": payload})
        supabase_store.upsert_run(writer, {"run_id": "run-day-ahead", "day_ahead": dict(payload, budget_s=900)})
        rows = writer.execute("select run_id, day_ahead from public.pipeline_run").fetchall()
    assert rows == [("run-day-ahead", dict(payload, budget_s=900))]


def test_store_sql_reports_every_check_ok_on_the_write_side_state(pg_url):
    with _session(pg_url) as conn:
        rows = local_pg.run_select_file(conn, _VERIFY_SQL)
    assert [r["check_name"] for r in rows] == sorted(_STORE_VERIFY_CHECKS)
    assert all(set(r) == {"check_name", "ok", "detail"} for r in rows)
    assert [(r["check_name"], r["detail"]) for r in rows if r["ok"] is not True] == []


def test_store_sql_turns_exactly_the_matching_checks_false_when_the_schema_is_wrong(tmp_path_factory):
    """The checks can fail: each wrong state (made in a rolled-back transaction) trips the check that names it."""
    import psycopg

    local_pg.require_local_pg()
    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url, paths=_through_store())

        def failing(statement):
            with psycopg.connect(url) as conn:  # not autocommit: the change is rolled back on exit
                conn.execute("set timezone = 'UTC'")
                conn.execute(statement)
                rows = local_pg.run_select_file(conn, _VERIFY_SQL)
                conn.rollback()
            return {r["check_name"] for r in rows if r["ok"] is not True}

        not_readable = "day_ahead_forecast_not_readable_by_anon_or_authenticated"
        cannot_change = "dlr_writer_cannot_update_delete_or_truncate_day_ahead_forecast"
        assert failing("select 1") == set()
        assert failing("grant select on public.day_ahead_forecast to anon") == {not_readable}
        assert failing("grant select (city) on public.day_ahead_forecast to authenticated") == {not_readable}
        assert failing("grant update on public.day_ahead_forecast to dlr_writer") == {cannot_change}
        assert failing("grant delete on public.day_ahead_forecast to dlr_writer") == {cannot_change}
        assert failing("grant truncate on public.day_ahead_forecast to dlr_writer") == {cannot_change}
        assert failing("revoke insert on public.day_ahead_forecast from dlr_writer") == {
            "dlr_writer_can_select_and_insert_day_ahead_forecast"}
        assert failing("grant select on public.pipeline_run to anon") == {"pipeline_run_not_readable_by_anon"}
        assert failing("alter table public.day_ahead_forecast disable row level security") == {
            "day_ahead_forecast_rls_enabled"}
        assert failing("comment on column public.day_ahead_forecast.label is ''") == {
            "day_ahead_forecast_columns_all_commented"}
        assert failing("alter table public.day_ahead_forecast add column extra text") == {
            "day_ahead_forecast_has_25_columns", "day_ahead_forecast_columns_all_commented"}
        assert failing("alter table public.day_ahead_forecast drop constraint day_ahead_forecast_pk") == {
            "day_ahead_forecast_primary_key_city_valid_time"}
        assert failing("alter table public.pipeline_run drop column day_ahead") == {
            "pipeline_run_has_day_ahead_jsonb"}
        assert failing("alter table public.pipeline_run alter column day_ahead type text") == {
            "pipeline_run_has_day_ahead_jsonb"}
        assert failing("drop table public.day_ahead_forecast") == set(_STORE_VERIFY_CHECKS) - {
            "pipeline_run_has_day_ahead_jsonb", "pipeline_run_not_readable_by_anon"}
