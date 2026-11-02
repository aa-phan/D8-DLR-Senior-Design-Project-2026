"""
Tests of the Phase 6 exposure migration, `public.latest_rating` (production-pipeline,
API-01, OD-6; D-01..D-05).

Two kinds of test live here:

* Offline tests read the migration as text and the Python contract module. They need no
  database and run in the default suite, so a column drift, a wording change that drops the
  word "provisional" or a grant that is not SELECT fails every run.
* Local-Postgres tests start a private throwaway cluster on 127.0.0.1 under pytest's tmp
  dir, only when `DLR_TEST_PG_AUTOSTART=1` (or a local `DLR_TEST_DATABASE_URL` is given),
  apply every migration to a database that begins with Supabase's legacy default grants,
  and read the view as the `anon` role the way the public API does. They skip otherwise,
  never touch Supabase, and always stop the cluster (backend/tests/local_pg.py).

Follows backend/tests/supabase_migration_test.py's conventions: module-level imports,
plain asserts, no test classes, no network.
"""

import contextlib
import glob
import hashlib
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

import config
import latest_rating_contract as contract
import local_pg

_MIGRATIONS_DIR = local_pg.MIGRATIONS_DIR
# SHA-256 of the two Phase 6 migrations as applied to the live project (plan 06-09, 2026-10-26).
# Both files are live: a fix goes in a new additive migration, never an edit here.
_APPLIED_PHASE6_MIGRATION_SHA256 = {
    "20261026195124_expose_latest_rating.sql": "7e2d5f0192e4eab126f66a703ac31d69504c463885e34f764ff78eb465dea0cb",
    "20261026204258_soak_freshness_log.sql": "246da223294c58809e03743abb62f6fa0107015488af631b0cf64fbffa8c8552",
}
_PHASE4_MIGRATIONS = (
    os.path.join(_MIGRATIONS_DIR, "20261019000000_create_city_rating.sql"),
    os.path.join(_MIGRATIONS_DIR, "20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql"),
)

# Comment bodies are blanked before keyword checks, so a word inside a comment never counts.
_COMMENT_RE = re.compile(
    r"(comment\s+on\s+(?:table|column|view|function)\s+[\w.]+(?:\([^)]*\))?\s+is\s+)'(?:[^']|'')*'", re.IGNORECASE
)


def _expose_path():
    paths = glob.glob(os.path.join(_MIGRATIONS_DIR, "*_expose_latest_rating.sql"))
    assert len(paths) == 1, paths
    return paths[0]


def _raw(path=None):
    with open(path or _expose_path(), encoding="utf-8") as handle:
        return handle.read()


def _code(path=None):
    """The migration with comment bodies blanked and `--` comments removed."""
    text = _COMMENT_RE.sub(r"\1''", _raw(path))
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def _statements(path=None):
    """Statements of `_code()`, splitting only on `;` outside `$$ ... $$`."""
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


def _top_level_items(text):
    """Split `text` on commas that are not inside parentheses."""
    items, depth, current = [], 0, []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return [" ".join(item.split()) for item in items if item.strip()]


def _view_select_items():
    match = re.search(
        r"create or replace view public\.latest_rating\b.*?\bas\s+select distinct on \(city\)(.*?)\bfrom public\.city_rating\b",
        _code(), re.DOTALL,
    )
    assert match, "the migration has no latest_rating select list"
    return _top_level_items(match.group(1))


def _view_columns():
    names = []
    for item in _view_select_items():
        alias = re.search(r"\bas (\w+)$", item)
        names.append(alias.group(1) if alias else item)
    return names


def _city_rating_columns():
    text = open(_PHASE4_MIGRATIONS[0], encoding="utf-8").read()
    match = re.search(r"create table if not exists public\.city_rating \(\n(.*?)\n\);", text, re.DOTALL)
    assert match, "no create table block for city_rating"
    names = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("constraint "):
            names.append(stripped.split()[0])
    return names


# ---------------------------------------------------------------------------
# Offline tests: the migration as text, the Python contract.
# ---------------------------------------------------------------------------


def test_view_columns_equal_the_contract():
    # The columns the dashboard and PSS/E code against are exactly the documented list, in order.
    assert _view_columns() == list(contract.LATEST_COLUMNS)
    assert len(contract.LATEST_COLUMNS) == 34
    assert contract.LATEST_COLUMNS[:27] == contract.STORED_COLUMNS[:27]
    assert contract.LATEST_COLUMNS[27:31] == (
        "config_fingerprint", "forecast_model_sha256", "anomaly_model_sha256", "solar_source")
    assert contract.LATEST_COLUMNS[-3:] == ("age_minutes", "is_stale", "is_provisional")
    # Stored columns are written out by name, never with a star.
    assert all("*" not in item for item in _view_select_items())


def test_stored_view_columns_exist_in_city_rating():
    table_columns = set(_city_rating_columns())
    assert len(table_columns) == 49
    missing = [name for name in contract.STORED_COLUMNS if name not in table_columns]
    assert missing == []
    assert len(contract.STORED_COLUMNS) == 31


def test_expose_migration_sorts_after_phase4():
    name = os.path.basename(_expose_path())
    for phase4 in _PHASE4_MIGRATIONS:
        assert name > os.path.basename(phase4)
    assert re.fullmatch(r"\d{14}_expose_latest_rating\.sql", name)


def test_view_runs_as_the_caller_and_grants_are_select_only():
    code = _code()
    assert "security_invoker = true" in code
    statements = _statements()
    grants = [s for s in statements if s.startswith("grant ")]
    assert grants, "the migration grants nothing"
    for statement in grants:
        assert statement.startswith(("grant select ", "grant execute ")), statement
    select_grants = [s for s in grants if s.startswith("grant select ")]
    assert select_grants == [
        "grant select on public.city_rating, public.latest_rating to anon, authenticated"
    ]
    policies = [s for s in statements if s.startswith("create policy ")]
    assert len(policies) == 1
    assert re.match(r"create policy city_rating_public_read on public\.city_rating for select to anon, authenticated using \(true\)$",
                    policies[0])
    # The policy is dropped before it is created, so re-applying leaves exactly one.
    assert statements[statements.index(policies[0]) - 1] == "drop policy if exists city_rating_public_read on public.city_rating"
    # The run log is never granted.
    assert not any("pipeline_run" in s for s in grants)


def test_contract_age_and_stale_rules():
    valid = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)
    cases = [
        # (elapsed, age_minutes, is_stale)
        (timedelta(minutes=89, seconds=59, microseconds=999999), 90, False),
        (timedelta(minutes=90), 90, False),          # exactly 90 minutes is fresh
        (timedelta(minutes=90, microseconds=1), 91, True),
        (timedelta(minutes=90, seconds=59), 91, True),
        (timedelta(0), 0, False),
        (timedelta(minutes=1), 1, False),
    ]
    for elapsed, age, stale in cases:
        now = valid + elapsed
        assert contract.age_minutes(valid, now) == age, elapsed
        assert contract.is_stale(valid, now) is stale, elapsed
        # age_minutes > 90 is exactly is_stale: the number shown never contradicts the flag.
        assert (contract.age_minutes(valid, now) > contract.STALE_AFTER_MINUTES) is stale, elapsed
    assert contract.STALE_AFTER_MINUTES == 90


# ---------------------------------------------------------------------------
# Local-Postgres tests: the view read as anon on a database that starts with every
# legacy default grant.
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _session(url, role=None):
    """A connection that is always rolled back; optionally acting as `role`."""
    import psycopg
    from psycopg import sql

    conn = psycopg.connect(url)
    try:
        if role:
            conn.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    """A migrated throwaway database holding three hourly slots for each of the four cities."""
    local_pg.require_local_pg()
    import psycopg

    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url)
        newest = local_pg.current_utc_hour()
        rows = [local_pg.rating_row(city, newest - timedelta(hours=back),
                                    rating_amps=1000.0 + 10 * index + back)
                for index, city in enumerate(config.LOCATIONS) for back in (2, 1, 0)]
        with psycopg.connect(url) as conn:
            local_pg.insert_rows(conn, rows)
        yield url


def _newest_slot():
    # The fixture seeds up to the current UTC hour, so every seeded row is at most 59 minutes
    # old and fresh at any minute of the hour. valid_time is never in the future.
    return local_pg.current_utc_hour()


def test_tracer_anon_reads_the_newest_row_per_city(pg_url):
    with _session(pg_url, "anon") as conn:
        cur = conn.execute("select * from public.latest_rating order by city")
        names = [column.name for column in cur.description]
        rows = cur.fetchall()
        total = conn.execute("select count(*) from public.city_rating").fetchone()[0]
    assert names == list(contract.LATEST_COLUMNS)
    assert len(rows) == 4
    by_city = {row[names.index("city")]: row for row in rows}
    assert sorted(by_city) == sorted(config.LOCATIONS)
    # Each row is the newest slot (the current UTC hour, or the one before if the hour just turned).
    for row in rows:
        valid_time = row[names.index("valid_time")]
        assert valid_time == _newest_slot() or valid_time == _newest_slot() - timedelta(hours=1)
        assert row[names.index("origin")] == "live"
    assert total == 12  # anon reads the full history through the table


def test_newest_row_wins_even_when_it_is_a_fallback(pg_url):
    # D-04: a newer fallback row is the value the system published, so it wins over an older computed row.
    newer = _newest_slot() + timedelta(hours=1)
    fallback = local_pg.rating_row(
        "AUSTIN", newer, status="fallback", fallback=True, fallback_gates=["G4"],
        alerts=["G4: stale observation"], rating_amps=900.0, rating_mw=511.0)
    with _session(pg_url) as conn:
        local_pg.insert_rows(conn, [fallback])
        conn.execute("set role anon")
        cur = conn.execute(
            "select valid_time, status, fallback, fallback_gates from public.latest_rating where city = 'AUSTIN'")
        rows = cur.fetchall()
    assert rows == [(newer, "fallback", True, ["G4"])]


# ---------------------------------------------------------------------------
# Phase 6 plan 06-01 task 2: assert_fresh, the 90-minute boundary, the real provisional labels,
# write denial, invoker RLS, idempotency and the shared verification query.
# ---------------------------------------------------------------------------

_VERIFY_SQL = os.path.join(local_pg.REPO_ROOT, "supabase", "ops", "verify_exposure.sql")
_MANIFEST = os.path.join(local_pg.REPO_ROOT, "docs", "data-science", "decisions", "real_data_validation",
                         "manifest.json")

_VERIFY_CHECKS = (
    "anon_authenticated_grants_are_select_on_two_objects_only",
    "anon_authenticated_hold_no_write_or_column_privilege_in_public",
    "anon_can_select_city_rating",
    "anon_can_select_latest_rating",
    "anon_executable_public_functions_are_assert_fresh_only",
    "city_rating_rls_enabled",
    "index_city_rating_city_valid_desc_present",
    "is_provisional_matches_the_labels",
    "is_stale_matches_age_minutes",
    "latest_rating_columns_all_commented",
    "latest_rating_ends_with_the_computed_columns",
    "latest_rating_has_34_columns",
    "latest_rating_has_the_four_cities",
    "latest_rating_is_security_invoker",
    "latest_rating_one_row_per_city",
    "no_write_policy_for_anon_or_authenticated",
    "pipeline_run_not_readable_by_anon",
    "read_policy_city_rating_public_read",
)


def _sqlstate(error):
    return getattr(error.value, "sqlstate", None)


def _replace_city_rows(conn, rows):
    """As the superuser inside the open transaction: empty city_rating, then insert `rows`."""
    conn.execute("delete from public.city_rating")
    local_pg.insert_rows(conn, rows)


def test_live_label_is_provisional_offline():
    # D-03 drift guard, no database: the real labels the live runner writes must still read provisional.
    assert contract.is_provisional(config.RATING_BASIS, config.RATING_CONFIG_VERSION), (
        "config.RATING_BASIS / RATING_CONFIG_VERSION no longer contain the word provisional: if Phase 7's "
        "REVAL-01 go lifted the label, update this expectation; otherwise latest_rating.is_provisional "
        "would tell consumers that provisional rows are final")
    # Either label alone is enough, and a lifted pair is final.
    assert contract.is_provisional(config.RATING_BASIS, "v2-2026-11-01")
    assert contract.is_provisional("Per-conductor amperes.", config.RATING_CONFIG_VERSION)
    assert contract.is_provisional("PROVISIONAL (OD-5). Phase 3 backfill", "v2")
    assert not contract.is_provisional("Per-conductor amperes; values confirmed by Phase 7 re-validation.", "v2-2026-11-01")
    assert not contract.is_provisional(None, None)
    # The migration's expression tests both columns for the same word the contract names.
    expression = next(item for item in _view_select_items() if item.endswith("as is_provisional"))
    tested = set(re.findall(r"position\('([^']+)' in lower\((\w+)\)\) > 0", expression))
    assert tested == {(contract.PROVISIONAL_WORD, "rating_basis"), (contract.PROVISIONAL_WORD, "config_version")}
    assert " or " in expression


def test_view_comment_statements_cover_every_column():
    comments = {m.group(1): m.group(2) for m in re.finditer(
        r"comment on (?:view|column) ([\w.]+) is '((?:[^']|'')*)'", _raw(), re.IGNORECASE)}
    assert "public.latest_rating" in comments
    for name in contract.LATEST_COLUMNS:
        text = comments.get(f"public.latest_rating.{name}")
        assert text and text.strip(), name
        if name.endswith(("_amps", "_mw")):
            assert "PROVISIONAL" in text, name
    assert set(comments) == {"public.latest_rating"} | {f"public.latest_rating.{n}" for n in contract.LATEST_COLUMNS}


def test_assert_fresh_city_list_matches_config_locations():
    match = re.search(r"from \(values (.*?)\) as c\(city\)", _code(), re.DOTALL)
    assert match, "assert_fresh has no city list"
    cities = re.findall(r"\('([A-Z_]+)'\)", match.group(1))
    assert sorted(cities) == sorted(config.LOCATIONS)
    # The function runs as the caller, with an empty search path, and only a reader may call it.
    statement = next(s for s in _statements() if s.startswith("create or replace function public.assert_fresh"))
    for fragment in ("security invoker", "stable", "set search_path = ''", "returns jsonb",
                     "sqlstate '22023'", "sqlstate 'PT503'"):
        assert fragment in statement, fragment
    assert "security definer" not in statement
    statements = _statements()
    assert "revoke all on function public.assert_fresh(integer) from public, anon, authenticated" in statements
    assert "grant execute on function public.assert_fresh(integer) to anon, authenticated" in statements


def test_verify_exposure_sql_is_one_read_only_select():
    with open(_VERIFY_SQL, encoding="utf-8") as handle:
        raw = handle.read()
    code = "\n".join(line.split("--", 1)[0] for line in raw.splitlines())
    bare = re.sub(r"'(?:[^']|'')*'", "''", code)  # string literals may hold a semicolon or a keyword
    statements = [s.strip() for s in bare.split(";") if s.strip()]
    assert len(statements) == 1
    assert re.match(r"(select|with)\b", statements[0], re.IGNORECASE)
    for forbidden in ("insert ", "update ", "delete ", "drop ", "alter ", "create ", "grant ", "revoke ",
                      "truncate ", "set role", "pg_sleep"):
        assert forbidden not in statements[0].lower(), forbidden
    for name in _VERIFY_CHECKS:
        assert f"'{name}'" in code, name
    assert "check_name" in code and "detail" in code


def test_assert_fresh_contract(pg_url):
    import psycopg

    with _session(pg_url, "anon") as conn:
        result = conn.execute("select public.assert_fresh()").fetchone()[0]
        assert result["ok"] is True and result["cities"] == 4 and result["max_age_minutes"] == 90
        assert result["oldest_valid_time"]
        with pytest.raises(psycopg.Error) as stale, conn.transaction():
            conn.execute("select public.assert_fresh(0)")
        assert _sqlstate(stale) == "PT503"
        for bad in ("-1", "10081", "null"):
            with pytest.raises(psycopg.Error) as out_of_range, conn.transaction():
                conn.execute(f"select public.assert_fresh({bad})")
            assert _sqlstate(out_of_range) == "22023", bad
    with _session(pg_url, "authenticated") as conn:
        assert conn.execute("select public.assert_fresh(120)").fetchone()[0]["ok"] is True

    # A city with no rating row is named in the error detail.
    with _session(pg_url) as conn:
        conn.execute("delete from public.city_rating where city = 'EL_PASO'")
        conn.execute("set role anon")
        with pytest.raises(psycopg.Error) as missing, conn.transaction():
            conn.execute("select public.assert_fresh()")
        assert _sqlstate(missing) == "PT503"
        assert "EL_PASO" in missing.value.diag.message_detail
        assert "missing=" in missing.value.diag.message_detail

    # The function is invoker, stable, with an empty search path; PUBLIC cannot execute it.
    with _session(pg_url) as conn:
        secdef, volatility, config_, acl = conn.execute(
            "select prosecdef, provolatile, proconfig, proacl::text from pg_proc "
            "where oid = 'public.assert_fresh(integer)'::regprocedure").fetchone()
    assert secdef is False and volatility == "s" and config_ == ['search_path=""']
    assert not re.search(r"(^\{|,)=X/", acl), acl  # no PUBLIC execute entry (an empty grantee name)


def test_age_and_stale_agree_with_assert_fresh_at_the_boundary(pg_url):
    # Inside one transaction now() is fixed, so the 90-minute rule can be pinned for any age a:
    # is_stale equals (a > 90), assert_fresh(a) passes and assert_fresh(a - 1) is refused.
    import psycopg

    for back in (1, 2):
        slot = local_pg.current_utc_hour() - timedelta(hours=back)
        with _session(pg_url) as conn:
            _replace_city_rows(conn, [local_pg.rating_row(city, slot) for city in config.LOCATIONS])
            conn.execute("set role anon")
            rows = conn.execute("select age_minutes, is_stale from public.latest_rating").fetchall()
            assert len(rows) == 4 and len({tuple(r) for r in rows}) == 1
            age, stale = rows[0]
            assert 60 * back <= age <= 60 * back + 60
            assert stale is (age > 90)
            assert conn.execute("select public.assert_fresh(%s)", [age]).fetchone()[0]["ok"] is True
            with pytest.raises(psycopg.Error) as refused, conn.transaction():
                conn.execute("select public.assert_fresh(%s)", [age - 1])
            assert _sqlstate(refused) == "PT503"


def test_exactly_90_minutes_is_fresh_and_one_microsecond_more_is_stale(pg_url):
    # The whole-hour CHECK is dropped inside this rolled-back transaction only, so a row can sit exactly
    # 90 minutes (and 90 minutes plus one microsecond) before the transaction's fixed now().
    import psycopg

    with _session(pg_url) as conn:
        now = conn.execute("select now()").fetchone()[0]
        conn.execute("alter table public.city_rating drop constraint city_rating_valid_time_hour_ck")
        for extra, age, stale in ((timedelta(0), 90, False), (timedelta(microseconds=1), 91, True)):
            slot = now - timedelta(minutes=90) - extra
            _replace_city_rows(conn, [local_pg.rating_row(city, slot) for city in config.LOCATIONS])
            conn.execute("set role anon")
            rows = conn.execute("select age_minutes, is_stale from public.latest_rating").fetchall()
            assert {tuple(r) for r in rows} == {(age, stale)}
            assert contract.age_minutes(slot, now) == age and contract.is_stale(slot, now) is stale
            if stale:
                with pytest.raises(psycopg.Error) as refused, conn.transaction():
                    conn.execute("select public.assert_fresh(90)")
                assert _sqlstate(refused) == "PT503"
            else:
                assert conn.execute("select public.assert_fresh(90)").fetchone()[0]["ok"] is True
            conn.execute("reset role")


def test_is_provisional_reads_the_real_labels(pg_url):
    import json

    import supabase_load_backfill

    with open(_MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)
    backfill_basis = supabase_load_backfill.backfill_rating_basis(manifest)
    lifted_basis = "Per-conductor amperes; values confirmed by Phase 7 re-validation."
    lifted_version = "v2-2026-11-01"
    slot = local_pg.current_utc_hour()
    cases = {  # city -> (rating_basis, config_version)
        "AUSTIN": (config.RATING_BASIS, config.RATING_CONFIG_VERSION),          # what the live runner writes
        "CORPUS_CHRISTI": (backfill_basis, lifted_version),                     # what the backfill writes
        "MIDLAND": (lifted_basis, config.RATING_CONFIG_VERSION),                # the word in config_version only
        "EL_PASO": (lifted_basis, lifted_version),                              # a lifted pair
    }
    expected = {"AUSTIN": True, "CORPUS_CHRISTI": True, "MIDLAND": True, "EL_PASO": False}
    with _session(pg_url) as conn:
        _replace_city_rows(conn, [
            local_pg.rating_row(city, slot, rating_basis=basis, config_version=version)
            for city, (basis, version) in cases.items()])
        conn.execute("set role anon")
        got = dict(conn.execute("select city, is_provisional from public.latest_rating").fetchall())
    assert got == expected
    for city, (basis, version) in cases.items():
        assert contract.is_provisional(basis, version) is expected[city], city  # the Python twin agrees


def test_writes_are_denied_by_privilege(pg_url):
    import psycopg

    far = datetime(2031, 1, 1, tzinfo=timezone.utc)
    new_row = local_pg.rating_row("AUSTIN", far)
    insert_sql = ("insert into public.city_rating (city, valid_time, rating_amps, rating_mw, static_rating_amps, "
                  "static_rating_mw, line_voltage_kv, power_factor, status, fallback, rating_basis, "
                  "config_version, config_fingerprint) values (%s, %s, 1, 1, 1, 1, 345, 0.95, 'ok', false, 'x', 'x', %s)")
    insert_args = [new_row["city"], far, new_row["config_fingerprint"]]
    table_writes = [
        (insert_sql, insert_args),
        ("update public.city_rating set rating_amps = 1 where city = 'AUSTIN'", None),
        ("delete from public.city_rating where city = 'AUSTIN'", None),
        ("truncate public.city_rating", None),
    ]
    view_writes = [
        ("insert into public.latest_rating (city) values ('AUSTIN')", None),
        ("update public.latest_rating set rating_amps = 1", None),
        ("delete from public.latest_rating", None),
    ]
    for role in ("anon", "authenticated"):
        with _session(pg_url, role) as conn:
            for statement, args in table_writes:
                with pytest.raises(psycopg.Error) as denied, conn.transaction():
                    conn.execute(statement, args)
                assert _sqlstate(denied) == "42501", (role, statement)
                assert "permission denied" in str(denied.value), (role, statement)
            for statement, args in view_writes:
                with pytest.raises(psycopg.Error) as refused, conn.transaction():
                    conn.execute(statement, args)
                assert _sqlstate(refused) in ("42501", "55000", "0A000"), (role, statement, _sqlstate(refused))
            with pytest.raises(psycopg.Error) as hidden, conn.transaction():
                conn.execute("select 1 from public.pipeline_run")
            assert _sqlstate(hidden) == "42501", role
    with _session(pg_url) as conn:
        assert conn.execute("select count(*) from public.city_rating").fetchone()[0] == 12


def test_view_obeys_the_callers_rls(pg_url):
    # With the read policy gone, anon sees nothing through the view: it applies the caller's RLS.
    with _session(pg_url) as conn:
        conn.execute("drop policy city_rating_public_read on public.city_rating")
        conn.execute("set role anon")
        assert conn.execute("select count(*) from public.latest_rating").fetchone()[0] == 0
        assert conn.execute("select count(*) from public.city_rating").fetchone()[0] == 0
    with _session(pg_url, "anon") as conn:
        assert conn.execute("select count(*) from public.latest_rating").fetchone()[0] == 4
    with _session(pg_url) as conn:
        flags = conn.execute(
            "select reloptions::text[] @> array['security_invoker=true'] from pg_class "
            "where oid = 'public.latest_rating'::regclass").fetchone()[0]
        assert flags is True


def test_same_key_upsert_keeps_one_row_per_city(pg_url):
    # OD-7: Phase 4's writer re-upserts an existing (city, valid_time) key; a read is one statement
    # over one snapshot, so it still sees exactly one row per city, carrying the new value.
    with _session(pg_url) as conn:
        newest = conn.execute("select max(valid_time) from public.city_rating where city = 'AUSTIN'").fetchone()[0]
        conn.execute("set role dlr_writer")  # the writer still works after the revoke sweep
        local_pg.insert_rows(conn, [local_pg.rating_row("AUSTIN", newest, rating_amps=4321.0)],
                             update_on_conflict=("rating_amps",))
        conn.execute("reset role")
        conn.execute("set role anon")
        rows = dict(conn.execute("select city, rating_amps from public.latest_rating").fetchall())
        assert len(rows) == 4 and rows["AUSTIN"] == 4321.0
        assert conn.execute("select count(*) from public.city_rating where city = 'AUSTIN'").fetchone()[0] == 3
        assert all(value != 4321.0 for city, value in rows.items() if city != "AUSTIN")


def _exposure_snapshot(conn):
    """Everything the migration decides, as plain values."""
    grants = conn.execute(
        "select c.relname, c.relkind::text, "
        "case when a.grantee = 0 then 'public' else a.grantee::regrole::text end, a.privilege_type "
        "from pg_class c join pg_namespace n on n.oid = c.relnamespace, "
        "lateral aclexplode(c.relacl) a "
        "where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f', 'S') "
        "and (a.grantee = 0 or a.grantee::regrole::text in ('anon', 'authenticated')) "
        "order by 1, 3, 4").fetchall()
    policies = conn.execute(
        "select policyname, cmd, roles::text from pg_policies where schemaname = 'public' order by 1").fetchall()
    view = conn.execute("select pg_get_viewdef('public.latest_rating'::regclass), "
                        "(select reloptions::text from pg_class where oid = 'public.latest_rating'::regclass)").fetchone()
    function = conn.execute("select pg_get_functiondef('public.assert_fresh(integer)'::regprocedure), "
                            "(select proacl::text from pg_proc where oid = 'public.assert_fresh(integer)'::regprocedure)"
                            ).fetchone()
    comments = conn.execute(
        "select a.attname, col_description(a.attrelid, a.attnum) from pg_attribute a "
        "where a.attrelid = 'public.latest_rating'::regclass and a.attnum > 0 order by a.attnum").fetchall()
    return grants, policies, view, function, comments


def test_expose_migration_reapplies_cleanly(pg_url):
    import psycopg

    with _session(pg_url) as conn:
        before = _exposure_snapshot(conn)
    with open(_expose_path(), encoding="utf-8") as handle:
        sql_text = handle.read()
    with psycopg.connect(pg_url) as conn:
        conn.execute(sql_text)  # the second (and a third) apply of an already-applied migration
        conn.execute(sql_text)
    with _session(pg_url) as conn:
        after = _exposure_snapshot(conn)
    assert after == before
    grants, policies, _, _, _ = after
    # anon and authenticated hold SELECT on exactly the two objects, nothing else.
    assert sorted({(r[0], r[2], r[3]) for r in grants}) == sorted(
        (relation, role, "SELECT") for relation in ("city_rating", "latest_rating") for role in ("anon", "authenticated"))
    assert [p for p in policies if p[0] == "city_rating_public_read"] == [
        ("city_rating_public_read", "SELECT", "{anon,authenticated}")]


def test_every_view_column_has_a_comment(pg_url):
    with _session(pg_url) as conn:
        rows = conn.execute(
            "select a.attname, col_description(a.attrelid, a.attnum) from pg_attribute a "
            "where a.attrelid = 'public.latest_rating'::regclass and a.attnum > 0 and not a.attisdropped "
            "order by a.attnum").fetchall()
        view_comment = conn.execute("select obj_description('public.latest_rating'::regclass, 'pg_class')").fetchone()[0]
    assert [name for name, _ in rows] == list(contract.LATEST_COLUMNS)
    for name, text in rows:
        assert text and text.strip(), name
        if name.endswith(("_amps", "_mw")):
            assert "PROVISIONAL" in text, name
    assert view_comment and "PROVISIONAL" in view_comment


def test_verify_exposure_sql_reports_every_check_ok(pg_url):
    with _session(pg_url) as conn:
        rows = local_pg.run_select_file(conn, _VERIFY_SQL)
        assert [r["check_name"] for r in rows] == sorted(_VERIFY_CHECKS)
        assert all(set(r) == {"check_name", "ok", "detail"} for r in rows)
        failing = [(r["check_name"], r["detail"]) for r in rows if r["ok"] is not True]
        assert failing == []

    # The checks can fail: a stray write grant, a second readable table and a second callable
    # function each turn exactly the matching rows false.
    with _session(pg_url) as conn:
        conn.execute("grant insert on public.city_rating to anon")
        conn.execute("grant select on public.pipeline_run to authenticated")
        conn.execute("create function public.sneaky() returns integer language sql as 'select 1'")
        bad = {r["check_name"] for r in local_pg.run_select_file(conn, _VERIFY_SQL) if r["ok"] is not True}
    assert bad == {"anon_authenticated_grants_are_select_on_two_objects_only",
                   "anon_authenticated_hold_no_write_or_column_privilege_in_public",
                   "anon_executable_public_functions_are_assert_fresh_only",
                   "pipeline_run_not_readable_by_anon"}
    with _session(pg_url) as conn:
        conn.execute("drop policy city_rating_public_read on public.city_rating")
        conn.execute("create policy sneaky_write on public.city_rating for insert to anon with check (true)")
        bad = {r["check_name"] for r in local_pg.run_select_file(conn, _VERIFY_SQL) if r["ok"] is not True}
    assert {"read_policy_city_rating_public_read", "no_write_policy_for_anon_or_authenticated"} <= bad


def test_verify_exposure_sql_sees_column_level_and_inherited_privileges(pg_url):
    # relacl never lists column-level grants, so the grants check alone stays green for these.
    # Only the has_*_privilege check can see them (review WR-01).
    only_hold_check = {"anon_authenticated_hold_no_write_or_column_privilege_in_public"}
    for statement in ("grant update (rating_amps) on public.city_rating to anon",
                      "grant insert (city) on public.city_rating to authenticated",
                      "grant select (run_id) on public.pipeline_run to anon"):
        with _session(pg_url) as conn:
            conn.execute(statement)
            bad = {r["check_name"] for r in local_pg.run_select_file(conn, _VERIFY_SQL) if r["ok"] is not True}
        assert bad == only_hold_check, statement

    # A write privilege inherited through role membership is seen too.
    with _session(pg_url) as conn:
        conn.execute("create role verify_writer nologin")
        conn.execute("grant insert on public.city_rating to verify_writer")
        conn.execute("grant verify_writer to anon")
        bad = {r["check_name"] for r in local_pg.run_select_file(conn, _VERIFY_SQL) if r["ok"] is not True}
    assert bad == only_hold_check


def test_phase6_migrations_are_unchanged_after_apply():
    # Both files are applied to the live project; neither may be edited afterwards (T-06-31).
    for name, expected in _APPLIED_PHASE6_MIGRATION_SHA256.items():
        with open(os.path.join(_MIGRATIONS_DIR, name), "rb") as handle:
            assert hashlib.sha256(handle.read()).hexdigest() == expected, name
