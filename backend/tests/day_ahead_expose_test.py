"""
Tests of the day-ahead expose migration (production-pipeline Phase 8, plan 08-09: DAY-06, DAY-07,
D-09, D-10, D-12; threats T-08-26..T-08-29).

`supabase/migrations/20261108120100_expose_day_ahead_forecast.sql` is read as text (its view
select lists are compared with `day_ahead_contract`, its grants, policy and function header are
checked), then applied, with every earlier migration, to a throwaway local Postgres and exercised
as `anon` and `authenticated`: the upcoming-targets view, the per-city status view with the
late flag, the extended `public.assert_fresh` alarm function, and the refusal of every write.

The local-Postgres tests need `DLR_TEST_PG_AUTOSTART=1` (backend/tests/local_pg.py). A skip
proves nothing, so the plan's verify command treats a skip as a failure. Nothing here touches the
live Supabase project, a remote or the network.
"""

import contextlib
import glob
import hashlib
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

import config
import day_ahead_contract as contract
import local_pg

_MIGRATIONS_DIR = local_pg.MIGRATIONS_DIR
_STORE_MIGRATION = "20261108120000_day_ahead_forecast_store.sql"
_EXPOSE_MIGRATION = "20261108120100_expose_day_ahead_forecast.sql"
_EXPOSE_PATH = os.path.join(_MIGRATIONS_DIR, _EXPOSE_MIGRATION)

# Applied to the live project by the owner on 2026-11-09 (plan 08-11); the file may not be edited afterwards.
_APPLIED_EXPOSE_MIGRATION_SHA256 = {
    "20261108120100_expose_day_ahead_forecast.sql": "253a539ec0dc41c47f31ec596855e8852769ce6993d587ebdf6e406aedcab816",
}

_PUBLISHED = ("day_ahead_forecast", "day_ahead_upcoming", "day_ahead_status")

_COMMENT_RE = re.compile(
    r"(comment\s+on\s+(?:table|column|view|function)\s+[\w.]+(?:\([^)]*\))?\s+is\s+)'(?:[^']|'')*'", re.IGNORECASE
)
_COMMENT_BODY_RE = re.compile(r"comment on (view|column) ([\w.]+) is '((?:[^']|'')*)'", re.IGNORECASE)


def _raw(path=_EXPOSE_PATH):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _code(path=_EXPOSE_PATH):
    """The file with comment bodies blanked and `--` comments removed."""
    text = _COMMENT_RE.sub(r"\1''", _raw(path))
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def _statements(path=_EXPOSE_PATH):
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


def _names(items):
    names = []
    for item in items:
        alias = re.search(r"\bas (\w+)$", item)
        names.append(alias.group(1) if alias else item)
    return names


def _view_statement(name):
    return next(s for s in _statements() if s.startswith(f"create or replace view public.{name} "))


def _function_statement():
    return next(s for s in _statements() if s.startswith("create or replace function public.assert_fresh"))


# --------------------------------------------------------------------------------------------------
# text: what the file says
# --------------------------------------------------------------------------------------------------

def test_expose_migration_is_unchanged_after_apply():
    # The file is applied to the live project; a later edit would make the repo disagree with it.
    for name, expected in _APPLIED_EXPOSE_MIGRATION_SHA256.items():
        with open(os.path.join(_MIGRATIONS_DIR, name), "rb") as handle:
            assert hashlib.sha256(handle.read()).hexdigest() == expected, name


def test_text_the_file_sorts_after_the_write_side_migration_and_is_the_only_expose_file():
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(_MIGRATIONS_DIR, "*.sql")))
    assert names.index(_EXPOSE_MIGRATION) == names.index(_STORE_MIGRATION) + 1
    assert names[-1] == _EXPOSE_MIGRATION
    assert len(glob.glob(os.path.join(_MIGRATIONS_DIR, "*_expose_day_ahead_forecast.sql"))) == 1


def test_text_both_views_are_security_invoker_and_the_select_lists_equal_the_contract():
    for name in ("day_ahead_upcoming", "day_ahead_status"):
        assert f"create or replace view public.{name} with (security_invoker = true) as" in _view_statement(name)

    upcoming = _view_statement("day_ahead_upcoming")
    match = re.search(r" as select (.*?) from public\.day_ahead_forecast where ", upcoming)
    assert match, "no upcoming select list"
    assert tuple(_names(_top_level_items(match.group(1)))) == contract.UPCOMING_COLUMNS
    assert "where valid_time > now()" in upcoming and upcoming.endswith("order by city, valid_time")

    status = _view_statement("day_ahead_status")
    match = re.search(r" as select (.*?) from \( select c\.city", status)
    assert match, "no status select list"
    assert tuple(_names(_top_level_items(match.group(1)))) == contract.STATUS_COLUMNS
    # The rule's constants are the contract's, not literals invented here.
    assert f"interval '{contract.GRID_HOURS} hours'" in status
    assert f"make_interval(hours => {contract.LATE_WINDOW_HOURS})" in status
    assert "exists (select 1 from public.day_ahead_forecast)" in status and "cardinality(missing_targets) > 0" in status
    cities = re.findall(r"\('([A-Z_]+)'\)", re.search(r"from \(values (.*?)\) as c\(city\)", status).group(1))
    assert sorted(cities) == sorted(config.LOCATIONS)


def test_text_the_only_privileges_are_select_on_the_three_objects_and_one_read_policy():
    statements = _statements()
    objects = ", ".join(f"public.{n}" for n in _PUBLISHED)
    assert f"revoke all on {objects} from anon, authenticated" in statements
    assert f"grant select on {objects} to anon, authenticated" in statements
    grants = [s for s in statements if s.startswith(("grant ", "revoke "))]
    assert sorted(grants) == sorted([
        f"revoke all on {objects} from anon, authenticated",
        f"grant select on {objects} to anon, authenticated",
        "revoke all on function public.assert_fresh(integer) from public, anon, authenticated",
        "grant execute on function public.assert_fresh(integer) to anon, authenticated",
    ])
    policies = [s for s in statements if "policy" in s]
    assert policies == [
        "drop policy if exists day_ahead_forecast_public_read on public.day_ahead_forecast",
        "create policy day_ahead_forecast_public_read on public.day_ahead_forecast "
        "for select to anon, authenticated using (true)",
    ]
    assert statements[-1] == "notify pgrst, 'reload schema'"


def test_text_the_alarm_function_keeps_its_signature_and_names_every_object_with_its_schema():
    statement = _function_statement()
    assert statement.startswith("create or replace function public.assert_fresh(max_age_minutes integer default 90) returns jsonb")
    for fragment in ("security invoker", "stable", "set search_path = ''", "language plpgsql",
                     "sqlstate '22023'", "sqlstate 'PT503'", "day_ahead_late=", "'day_ahead_armed'",
                     "public.day_ahead_status", "public.latest_rating"):
        assert fragment in statement, fragment
    assert "security definer" not in statement
    # Every table or view the body reads is schema-qualified (the search path is empty).
    sources = re.findall(r"\b(?:from|join)\s+(?!\()(?!lateral\b)([\w.]+)", statement)
    assert sources and all(source.startswith("public.") for source in sources), sources
    match = re.search(r"from \(values (.*?)\) as c\(city\)", statement, re.DOTALL)
    assert match, "assert_fresh has no city list"
    assert sorted(re.findall(r"\('([A-Z_]+)'\)", match.group(1))) == sorted(config.LOCATIONS)
    assert len([s for s in _statements() if s.startswith("create or replace function")]) == 1


def test_text_no_write_privilege_credential_or_connection_string():
    code = _code()
    assert not re.search(r"\bgrant\b[^;]*\b(insert|update|delete|truncate|references|trigger|all)\b[^;]*\bto\b[^;]*\b(anon|authenticated)\b",
                         code, re.IGNORECASE)
    for forbidden in ("password", "postgresql://", "postgres://", "service_role", "security definer", "alter default privileges"):
        assert forbidden not in code.lower(), forbidden
    raw = _raw().lower()
    assert "postgresql://" not in raw and "postgres://" not in raw and "password" not in raw


def test_text_every_view_column_has_a_unit_first_comment_and_the_views_are_commented():
    comments = {m.group(2): m.group(3) for m in _COMMENT_BODY_RE.finditer(_raw())}
    assert comments.get("public.day_ahead_upcoming") and comments.get("public.day_ahead_status")
    for view, columns in (("day_ahead_upcoming", contract.UPCOMING_COLUMNS), ("day_ahead_status", contract.STATUS_COLUMNS)):
        for name in columns:
            text = comments.get(f"public.{view}.{name}")
            assert text and text.strip(), (view, name)
            if name.endswith("_amps"):
                assert text.startswith("amperes (A)"), (view, name)
    assert set(comments) == (
        {"public.day_ahead_upcoming", "public.day_ahead_status"}
        | {f"public.day_ahead_upcoming.{n}" for n in contract.UPCOMING_COLUMNS}
        | {f"public.day_ahead_status.{n}" for n in contract.STATUS_COLUMNS})
    assert "started minutes" in comments["public.day_ahead_upcoming.lead_minutes"]
    for name in ("missing_targets", "is_late"):
        assert "12" in comments[f"public.day_ahead_status.{name}"], name
    assert "at least one row" in comments["public.day_ahead_status.is_late"]


# --------------------------------------------------------------------------------------------------
# Local Postgres: every migration applied, then read as the public roles
# --------------------------------------------------------------------------------------------------

@contextlib.contextmanager
def _session(url, role=None):
    """A connection that is always rolled back; optionally acting as `role`. Session time zone is UTC."""
    import psycopg
    from psycopg import sql

    conn = psycopg.connect(url)
    try:
        conn.execute("set timezone = 'UTC'")
        if role:
            conn.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    """A database with every migration applied and a fresh rating row for each of the four cities."""
    local_pg.require_local_pg()
    import psycopg

    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url)
        newest = local_pg.current_utc_hour()
        rows = [local_pg.rating_row(city, newest - timedelta(hours=back), rating_amps=1000.0 + 10 * index + back)
                for index, city in enumerate(config.LOCATIONS) for back in (1, 0)]
        with psycopg.connect(url) as conn:
            local_pg.insert_rows(conn, rows)
        yield url


def _sqlstate(error):
    return getattr(error.value, "sqlstate", None)


# The full PT503 message of the replaced assert_fresh. It was "stale or missing city rating" before
# the exposure; the day-ahead part was added to the same text (D-12).
_ALARM_MESSAGE = "stale or missing city rating or late day-ahead forecast"


def _row(city, valid_time, **overrides):
    """A complete valid day_ahead_forecast row, derived from `valid_time`."""
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


def _insert(conn, rows):
    for row in rows:
        conn.execute(_INSERT, row)


def _db_now(conn):
    return conn.execute("select now()").fetchone()[0]


def _grid_after(now, count):
    """The next `count` 6-hour UTC grid instants strictly after `now`."""
    base = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    base -= timedelta(hours=base.hour % contract.GRID_HOURS)
    first = base + timedelta(hours=contract.GRID_HOURS)
    return [first + timedelta(hours=contract.GRID_HOURS * i) for i in range(count)]


def _due(now):
    """The grid targets T with now < T <= now + 12 h."""
    return [t for t in _grid_after(now, 4) if t <= now + timedelta(hours=contract.LATE_WINDOW_HOURS)]


def _status(conn):
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from public.day_ahead_status order by city")
        return {row["city"]: row for row in cur.fetchall()}


def _complete_rows(now, cities=config.LOCATIONS, extra=1):
    """Rows for every due target of `cities`, plus `extra` more grid targets after them."""
    due = _due(now)
    targets = _grid_after(now, len(due) + extra)
    return [_row(city, t) for city in cities for t in targets]


# ---- upcoming ----

def test_upcoming_shows_only_future_targets_ordered_with_a_positive_lead(pg_url):
    with _session(pg_url) as conn:
        now = _db_now(conn)
        future = _grid_after(now, 3)
        past = [future[0] - timedelta(hours=6 * k) for k in (1, 2)]
        rows = [_row(city, t) for city in ("MIDLAND", "AUSTIN") for t in (future[2], future[0], future[1], *past)]
        _insert(conn, rows)
        conn.execute("set role anon")
        cur = conn.execute("select * from public.day_ahead_upcoming")
        names = [c.name for c in cur.description]
        got = cur.fetchall()
        in_table = conn.execute("select count(*) from public.day_ahead_forecast").fetchone()[0]
        past_in_table = conn.execute(
            "select count(*) from public.day_ahead_forecast where valid_time <= %s", [now]).fetchone()[0]
    assert tuple(names) == contract.UPCOMING_COLUMNS
    keys = [(r[names.index("city")], r[names.index("valid_time")]) for r in got]
    assert keys == sorted(keys) and len(keys) == 6
    assert {k[1] for k in keys} == set(future)
    for r in got:
        delta = r[names.index("valid_time")] - now
        micro = (delta.days * 86400 + delta.seconds) * 10**6 + delta.microseconds
        assert r[names.index("lead_minutes")] == -(-micro // 60_000_000) > 0
        assert r[names.index("forecast_amps")] == 1700.0
    # OD-6: the past values stay readable in the table itself.
    assert in_table == 10 and past_in_table == 4


def test_upcoming_lead_counts_started_minutes(pg_url):
    # The lead is rounded up: a partly elapsed minute counts as started, so the value is the ceiling
    # of the exact minutes to the target (the transaction's now() carries microseconds).
    with _session(pg_url) as conn:
        now = _db_now(conn)
        target = _grid_after(now, 1)[0]
        _insert(conn, [_row("AUSTIN", target)])
        lead, = conn.execute("select lead_minutes from public.day_ahead_upcoming").fetchone()
        exact = (target - now).total_seconds() / 60
    assert lead == int(exact) + (0 if exact == int(exact) else 1)


def test_upcoming_is_empty_when_the_table_is_empty(pg_url):
    with _session(pg_url, "anon") as conn:
        assert conn.execute("select count(*) from public.day_ahead_upcoming").fetchone()[0] == 0


# ---- status ----

def test_status_with_an_empty_table_has_four_rows_not_late_and_lists_the_due_targets(pg_url):
    with _session(pg_url, "anon") as conn:
        now = _db_now(conn)
        cur = conn.execute("select * from public.day_ahead_status")
        names = [c.name for c in cur.description]
        assert len(cur.fetchall()) == 4
        status = _status(conn)
    assert tuple(names) == contract.STATUS_COLUMNS
    assert sorted(status) == sorted(config.LOCATIONS)
    first = _grid_after(now, 1)[0]
    for city, row in status.items():
        assert row["is_late"] is False, city  # not armed: no row exists yet
        assert row["missing_targets"] == _due(now), city
        assert row["upcoming_count"] == 0 and row["newest_issued_at"] is None
        assert row["next_target_time"] == first and row["checked_at"] == now


def test_status_complete_cities_are_not_late_and_report_counts(pg_url):
    with _session(pg_url) as conn:
        now = _db_now(conn)
        _insert(conn, _complete_rows(now, extra=1))
        conn.execute("set role anon")
        status = _status(conn)
    expected_count = len(_due(now)) + 1
    for city, row in status.items():
        assert row["missing_targets"] == [] and row["is_late"] is False, city
        assert row["upcoming_count"] == expected_count, city
        assert row["newest_issued_at"] == row["next_target_time"] + timedelta(
            hours=contract.GRID_HOURS * expected_count - contract.GRID_HOURS) - timedelta(hours=17)


def test_status_a_city_missing_one_due_target_is_late_with_that_exact_timestamp(pg_url):
    with _session(pg_url) as conn:
        now = _db_now(conn)
        due = _due(now)
        rows = [_row(city, t) for city in config.LOCATIONS for t in due if not (city == "MIDLAND" and t == due[-1])]
        _insert(conn, rows)
        conn.execute("set role anon")
        status = _status(conn)
    assert status["MIDLAND"]["is_late"] is True
    assert status["MIDLAND"]["missing_targets"] == [due[-1]]
    for city in ("AUSTIN", "CORPUS_CHRISTI", "EL_PASO"):
        assert status[city]["is_late"] is False and status[city]["missing_targets"] == [], city


def test_status_any_row_arms_the_flag_even_a_past_one(pg_url):
    with _session(pg_url) as conn:
        now = _db_now(conn)
        _insert(conn, [_row("EL_PASO", _grid_after(now, 1)[0] - timedelta(hours=12))])
        conn.execute("set role authenticated")
        status = _status(conn)
    assert all(row["is_late"] is True for row in status.values())
    assert all(row["missing_targets"] == _due(now) for row in status.values())


def test_status_a_target_beyond_the_window_is_not_listed(pg_url):
    with _session(pg_url) as conn:
        now = _db_now(conn)
        due = _due(now)
        beyond = _grid_after(now, len(due) + 1)[-1]
        assert beyond > now + timedelta(hours=contract.LATE_WINDOW_HOURS)
        _insert(conn, [_row("AUSTIN", t) for t in due])
        conn.execute("set role anon")
        row = _status(conn)["AUSTIN"]
    assert row["missing_targets"] == [] and beyond not in row["missing_targets"]


# ---- alarm ----

def test_alarm_without_a_day_ahead_row_behaves_as_in_phase_6(pg_url):
    with _session(pg_url, "anon") as conn:
        body = conn.execute("select public.assert_fresh()").fetchone()[0]
    assert body["ok"] is True and body["cities"] == 4 and body["max_age_minutes"] == 90
    assert body["oldest_valid_time"] and body["day_ahead_armed"] is False


def test_alarm_armed_and_complete_returns_ok_with_the_armed_flag(pg_url):
    with _session(pg_url) as conn:
        _insert(conn, _complete_rows(_db_now(conn)))
        conn.execute("set role anon")
        body = conn.execute("select public.assert_fresh()").fetchone()[0]
    assert body["ok"] is True and body["day_ahead_armed"] is True


def test_alarm_armed_with_a_late_city_raises_pt503_naming_the_city_and_target(pg_url):
    import psycopg

    with _session(pg_url) as conn:
        now = _db_now(conn)
        due = _due(now)
        _insert(conn, [_row(city, t) for city in config.LOCATIONS for t in due if not (city == "EL_PASO" and t == due[0])])
        for role in ("anon", "authenticated"):
            conn.execute(f"set role {role}")
            with pytest.raises(psycopg.Error) as late, conn.transaction():
                conn.execute("select public.assert_fresh()")
            assert _sqlstate(late) == "PT503", role
            detail = late.value.diag.message_detail
            assert "day_ahead_late=" in detail and "EL_PASO@" + due[0].strftime("%Y-%m-%dT%H:%M:%SZ") in detail, detail
            assert "AUSTIN" not in detail and "missing={}" in detail and "stale={}" in detail, detail
            # The whole message is pinned: monitors and consumers see this text (WR-04). A PT503 whose
            # missing= and stale= are both empty means the ratings are fine and only the feed is late.
            assert late.value.diag.message_primary == _ALARM_MESSAGE
            conn.execute("reset role")


def test_alarm_still_names_missing_and_stale_ratings_and_rejects_out_of_range(pg_url):
    import psycopg

    with _session(pg_url) as conn:
        conn.execute("set role anon")
        with pytest.raises(psycopg.Error) as stale, conn.transaction():
            conn.execute("select public.assert_fresh(0)")
        assert _sqlstate(stale) == "PT503"
        assert "stale=" in stale.value.diag.message_detail and "missing=" in stale.value.diag.message_detail
        assert stale.value.diag.message_primary == _ALARM_MESSAGE
        for bad in ("-1", "10081", "null"):
            with pytest.raises(psycopg.Error) as out_of_range, conn.transaction():
                conn.execute(f"select public.assert_fresh({bad})")
            assert _sqlstate(out_of_range) == "22023", bad
    with _session(pg_url) as conn:
        conn.execute("delete from public.city_rating where city = 'EL_PASO'")
        conn.execute("set role anon")
        with pytest.raises(psycopg.Error) as missing, conn.transaction():
            conn.execute("select public.assert_fresh()")
        assert _sqlstate(missing) == "PT503"
        assert "missing={EL_PASO}" in missing.value.diag.message_detail


def test_alarm_there_is_exactly_one_assert_fresh_and_it_keeps_its_attributes(pg_url):
    with _session(pg_url) as conn:
        rows = conn.execute(
            "select p.oid::regprocedure::text, p.prosecdef, p.provolatile, p.proconfig, p.proacl::text, "
            "pg_get_function_arguments(p.oid) from pg_proc p where p.pronamespace = 'public'::regnamespace "
            "and p.proname = 'assert_fresh'").fetchall()
    assert len(rows) == 1
    signature, secdef, volatility, config_, acl, arguments = rows[0]
    assert signature == "assert_fresh(integer)" and arguments == "max_age_minutes integer DEFAULT 90"
    assert secdef is False and volatility == "s" and config_ == ['search_path=""']
    assert not re.search(r"(^\{|,)=X/", acl), acl  # no PUBLIC execute entry


# ---- grants, policy and writes ----

def test_the_public_roles_hold_select_only_on_the_three_objects_and_the_policy_is_select_only(pg_url):
    with _session(pg_url) as conn:
        grants = conn.execute(
            "select c.relname, a.grantee::regrole::text, a.privilege_type "
            "from pg_class c join pg_namespace n on n.oid = c.relnamespace, lateral aclexplode(c.relacl) a "
            "where n.nspname = 'public' and c.relname = any(%s) and a.grantee::regrole::text in ('anon', 'authenticated')",
            [list(_PUBLISHED)]).fetchall()
        policies = conn.execute(
            "select policyname, cmd, roles::text from pg_policies where schemaname = 'public' "
            "and tablename = 'day_ahead_forecast' order by 1").fetchall()
        reloptions = dict(conn.execute(
            "select relname, reloptions::text from pg_class where oid = any(array['public.day_ahead_upcoming'::regclass, "
            "'public.day_ahead_status'::regclass])").fetchall())
    assert sorted(grants) == sorted((n, role, "SELECT") for n in _PUBLISHED for role in ("anon", "authenticated"))
    assert ("day_ahead_forecast_public_read", "SELECT", "{anon,authenticated}") in policies
    assert [p[0] for p in policies if p[1] != "SELECT"] == ["dlr_writer_all"]
    assert all(value == "{security_invoker=true}" for value in reloptions.values()), reloptions


def test_the_public_roles_can_read_the_table_but_every_write_is_refused(pg_url):
    import psycopg

    with _session(pg_url) as conn:
        now = _db_now(conn)
        target = _grid_after(now, 1)[0]
        _insert(conn, [_row("AUSTIN", target)])
        new_row = dict(_row("MIDLAND", target))
        writes = [
            (_INSERT, new_row, ("42501",)),
            ("update public.day_ahead_forecast set forecast_amps = 1", None, ("42501",)),
            ("delete from public.day_ahead_forecast", None, ("42501",)),
            ("truncate public.day_ahead_forecast", None, ("42501",)),
            ("insert into public.day_ahead_upcoming (city) values ('AUSTIN')", None, ("42501", "55000", "42809")),
            ("update public.day_ahead_upcoming set forecast_amps = 1", None, ("42501", "55000", "42809")),
            ("delete from public.day_ahead_upcoming", None, ("42501", "55000", "42809")),
            ("insert into public.day_ahead_status (city) values ('AUSTIN')", None, ("42501", "55000", "42809")),
            ("update public.day_ahead_status set is_late = true", None, ("42501", "55000", "42809")),
            ("delete from public.day_ahead_status", None, ("42501", "55000", "42809")),
        ]
        for role in ("anon", "authenticated"):
            conn.execute(f"set role {role}")
            assert conn.execute("select count(*) from public.day_ahead_forecast").fetchone()[0] == 1, role
            for statement, args, allowed in writes:
                with pytest.raises(psycopg.Error) as refused, conn.transaction():
                    conn.execute(statement, args)
                assert _sqlstate(refused) in allowed, (role, statement, _sqlstate(refused))
            conn.execute("reset role")
            assert conn.execute("select count(*) from public.day_ahead_forecast").fetchone()[0] == 1, role


def test_the_run_log_and_the_writer_role_are_unchanged(pg_url):
    with _session(pg_url) as conn:
        assert conn.execute("select has_table_privilege('anon', 'public.pipeline_run', 'select')").fetchone()[0] is False
        assert conn.execute(
            "select has_table_privilege('dlr_writer', 'public.day_ahead_forecast', 'insert'), "
            "has_table_privilege('dlr_writer', 'public.day_ahead_forecast', 'update'), "
            "has_table_privilege('dlr_writer', 'public.day_ahead_forecast', 'delete')").fetchone() == (True, False, False)


# ---- reapply ----

def _snapshot(conn):
    grants = conn.execute(
        "select c.relname, c.relkind::text, "
        "case when a.grantee = 0 then 'public' else a.grantee::regrole::text end, a.privilege_type "
        "from pg_class c join pg_namespace n on n.oid = c.relnamespace, lateral aclexplode(c.relacl) a "
        "where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f', 'S') "
        "and (a.grantee = 0 or a.grantee::regrole::text in ('anon', 'authenticated')) order by 1, 3, 4").fetchall()
    policies = conn.execute(
        "select tablename, policyname, cmd, roles::text from pg_policies where schemaname = 'public' order by 1, 2").fetchall()
    views = [conn.execute("select pg_get_viewdef(%s::regclass), (select reloptions::text from pg_class where oid = %s::regclass)",
                          [f"public.{v}", f"public.{v}"]).fetchone() for v in _PUBLISHED[1:]]
    function = conn.execute("select pg_get_functiondef('public.assert_fresh(integer)'::regprocedure), "
                            "(select proacl::text from pg_proc where oid = 'public.assert_fresh(integer)'::regprocedure)").fetchone()
    return grants, policies, views, function


def test_every_migration_applies_twice_and_leaves_the_exposure_unchanged(tmp_path_factory):
    local_pg.require_local_pg()
    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url)
        with _session(url) as conn:
            before = _snapshot(conn)
        local_pg.apply_migrations(url)
        with _session(url) as conn:
            after = _snapshot(conn)
    assert after == before
