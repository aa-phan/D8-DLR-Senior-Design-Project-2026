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
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

import config
import latest_rating_contract as contract
import local_pg

_MIGRATIONS_DIR = local_pg.MIGRATIONS_DIR
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
