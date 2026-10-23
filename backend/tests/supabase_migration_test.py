"""
Offline contract tests of the Postgres migration and the writer's upsert
(production-pipeline Phase 4, DB-01, DB-04, DB-06).

The migration is parsed as text: columns and types in order, keys, CHECKs,
row-level security, the least-privilege writer role, re-apply safety and the
column comments. Nothing connects to a database (the live behavior is proven in
supabase_live_test.py). Follows backend/tests/city_rating_test.py's conventions
(module-level imports, plain asserts, no test classes, no network).
"""

import hashlib
import os
import re

import config
import supabase_store

_MIGRATION = os.path.join(
    os.path.dirname(__file__), "..", "..", "supabase", "migrations",
    "20261019000000_create_city_rating.sql",
)
# The additive follow-up of the Phase 4 code review (IN-06 hour CHECK, IN-03 run-log comments).
_FIX_MIGRATION = os.path.join(
    os.path.dirname(__file__), "..", "..", "supabase", "migrations",
    "20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql",
)
# sha256 of the original migration as applied to the live project (plan 04-05). It is never edited.
_MIGRATIONS_DIR = os.path.dirname(_MIGRATION)
_SCHEMA_DOC = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "data-science", "schema", "city_rating_v1.md")
_ORIGINAL_MIGRATION_SHA256 = "7fbf1423e0b8ccf0eee6f79e502036e11c8f3c4c9d54f6badddda0473f76129d"

_CITY_RATING_COLUMNS = [
    ("city", "text"),
    ("valid_time", "timestamptz"),
    ("observation_time", "timestamptz"),
    ("rating_amps", "double precision"),
    ("rating_mw", "double precision"),
    ("static_rating_amps", "double precision"),
    ("static_rating_mw", "double precision"),
    ("line_voltage_kv", "double precision"),
    ("power_factor", "double precision"),
    ("status", "text"),
    ("fallback", "boolean"),
    ("fallback_gates", "text[]"),
    ("alerts", "text[]"),
    ("exhausted", "boolean"),
    ("station_id", "text"),
    ("candidates_probed", "integer"),
    ("probe_trail", "jsonb"),
    ("air_temp_c", "double precision"),
    ("wind_perp_ms", "double precision"),
    ("wind_speed_ms", "double precision"),
    ("wind_direction_deg", "double precision"),
    ("solar_radiation_wm2", "double precision"),
    ("temp_source", "text"),
    ("wind_source", "text"),
    ("solar_source", "text"),
    ("forecast_method", "text"),
    ("forecast_status", "text"),
    ("forecast_amps", "double precision"),
    ("forecast_ci_lower_amps", "double precision"),
    ("forecast_ci_upper_amps", "double precision"),
    ("forecast_horizon_min", "double precision"),
    ("forecast_n_observations", "integer"),
    ("forecast_used_by_g6", "boolean"),
    ("detector_signal", "text"),
    ("detector_model_loaded", "boolean"),
    ("history_rows", "integer"),
    ("usable_history_rows", "integer"),
    ("rating_basis", "text"),
    ("config_version", "text"),
    ("config_fingerprint", "text"),
    ("forecast_model_sha256", "text"),
    ("anomaly_model_sha256", "text"),
    ("origin", "text"),
    ("run_id", "text"),
    ("run_attempt", "integer"),
    ("pipeline_version", "text"),
    ("schema_version", "integer"),
    ("first_written_at", "timestamptz"),
    ("computed_at", "timestamptz"),
]

_PIPELINE_RUN_COLUMNS = [
    ("run_id", "text"),
    ("run_attempt", "integer"),
    ("started_at", "timestamptz"),
    ("finished_at", "timestamptz"),
    ("window_end", "timestamptz"),
    ("provider", "text"),
    ("forecast_method", "text"),
    ("pipeline_version", "text"),
    ("cities_ok", "text[]"),
    ("cities_failed", "jsonb"),
    ("provider_errors", "jsonb"),
    ("sources", "jsonb"),
]

_NOT_NULL = {
    "city", "valid_time", "rating_amps", "rating_mw", "static_rating_amps", "static_rating_mw",
    "line_voltage_kv", "power_factor", "status", "fallback", "fallback_gates", "alerts",
    "exhausted", "rating_basis", "config_version", "config_fingerprint", "origin",
    "schema_version", "first_written_at", "computed_at",
}

_COMMENT_RE = re.compile(r"(comment\s+on\s+(?:table|column)\s+[\w.]+\s+is\s+)'(?:[^']|'')*'", re.IGNORECASE)


def _raw(path=_MIGRATION):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _code(path=_MIGRATION):
    """The migration with comment bodies blanked and `--` comments removed."""
    text = _COMMENT_RE.sub(r"\1''", _raw(path))
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def _statements(path=_MIGRATION):
    """Statements of `_code()` (keyword checks), splitting only on `;` outside `$$ ... $$`."""
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


def _table_block(table):
    match = re.search(
        rf"create table if not exists public\.{table} \(\n(.*?)\n\);", _code(), re.DOTALL
    )
    assert match, f"no create table block for {table}"
    return match.group(1)


_COLUMN_RE = re.compile(
    r"^\s*(\w+)\s+(double precision|text\[\]|text|timestamptz|integer|boolean|jsonb)(?=\s|,|$)(.*?),?\s*$"
)


def _columns(table):
    """[(name, type, attributes)] in declaration order, one column per line."""
    columns = []
    for line in _table_block(table).splitlines():
        if not line.strip() or line.strip().startswith("constraint "):
            continue
        match = _COLUMN_RE.match(line)
        assert match, f"cannot parse column line: {line!r}"
        columns.append((match.group(1), match.group(2), match.group(3).strip()))
    return columns


def _comments(path=_MIGRATION):
    pattern = re.compile(
        r"comment on (table|column) ([\w.]+) is '((?:[^']|'')*)'", re.IGNORECASE
    )
    return {m.group(2): m.group(3) for m in pattern.finditer(_raw(path))}


def _effective_comments():
    """Comments as the live database holds them: every migration in name order, a later one wins."""
    effective = {}
    for name in sorted(os.listdir(_MIGRATIONS_DIR)):
        if name.endswith(".sql"):
            effective.update(_comments(os.path.join(_MIGRATIONS_DIR, name)))
    return effective


def test_city_rating_has_every_db01_column_with_its_type():
    columns = _columns("city_rating")
    assert [(n, t) for n, t, _ in columns] == _CITY_RATING_COLUMNS
    assert len(columns) == 49
    not_null = {n for n, _, attrs in columns if "not null" in attrs}
    assert not_null == _NOT_NULL
    attrs = {n: a for n, _, a in columns}
    assert "default '{}'" in attrs["fallback_gates"]
    assert "default '{}'" in attrs["alerts"]
    assert "default false" in attrs["exhausted"]
    assert "default 'live'" in attrs["origin"]
    assert "default 1" in attrs["schema_version"]
    for name in ("first_written_at", "computed_at"):
        assert "default date_trunc('second', now())" in attrs[name]


def test_pipeline_run_matches_the_run_log_contract():
    columns = _columns("pipeline_run")
    assert [(n, t) for n, t, _ in columns] == _PIPELINE_RUN_COLUMNS
    assert len(columns) == 12
    attrs = {n: a for n, _, a in columns}
    assert "default date_trunc('second', now())" in attrs["started_at"]
    assert "not null" in attrs["started_at"]
    assert "default '{}'" in attrs["cities_ok"] and "not null" in attrs["cities_ok"]
    assert "default '{}'::jsonb" in attrs["cities_failed"] and "not null" in attrs["cities_failed"]


def test_primary_keys():
    assert "constraint city_rating_pk primary key (city, valid_time)" in _table_block("city_rating")
    run_id_line = [n for n in _table_block("pipeline_run").splitlines() if n.strip().startswith("run_id ")]
    assert len(run_id_line) == 1
    assert "constraint pipeline_run_pk primary key" in run_id_line[0]


def test_city_check_lists_exactly_config_locations():
    match = re.search(r"constraint city_rating_city_ck check \(city in \(([^)]*)\)\)", _code())
    assert match
    assert set(re.findall(r"'([A-Z_]+)'", match.group(1))) == set(config.LOCATIONS)


def test_hour_finite_positive_status_and_origin_checks():
    code = _code()
    assert "constraint city_rating_valid_time_hour_ck check (valid_time = date_trunc('hour', valid_time))" in code
    for column in ("rating_amps", "rating_mw"):
        assert (f"constraint city_rating_{column}_ck check ({column} > 0 and {column} < 'Infinity'::float8)"
                in code)
    assert "constraint city_rating_status_ck check (status in ('ok', 'fallback'))" in code
    assert ("constraint city_rating_forecast_status_ck check "
            "(forecast_status in ('ok', 'cold_start', 'failed'))") in code
    assert "constraint city_rating_origin_ck check (origin in ('live', 'backfill'))" in code


def test_rls_enabled_and_consumers_revoked_on_both_tables():
    statements = _statements()
    for table in ("city_rating", "pipeline_run"):
        assert f"alter table public.{table} enable row level security" in statements
    assert "revoke all on public.city_rating, public.pipeline_run from anon, authenticated" in statements
    # Phase 6 grants SELECT, not this phase (OD-6): no grant reaches a consumer role.
    for statement in statements:
        if statement.startswith("grant "):
            assert not re.search(r"\bto\b.*\b(anon|authenticated|public)\b", statement), statement


def test_writer_role_is_least_privilege_and_has_no_credential():
    statements = _statements()
    raw = _raw().lower()

    role_blocks = [s for s in statements if "create role" in s]
    assert len(role_blocks) == 1
    block = role_blocks[0]
    assert block.startswith("do $$")
    assert "pg_roles" in block and "rolname = 'dlr_writer'" in block
    assert "create role dlr_writer login;" in block

    grants = [s for s in statements if s.startswith("grant ")]
    assert grants == [
        "grant usage on schema public to dlr_writer",
        "grant select, insert, update on public.city_rating, public.pipeline_run to dlr_writer",
    ]

    policies = [s for s in statements if s.startswith("create policy ")]
    assert policies == [
        "create policy dlr_writer_all on public.city_rating for all to dlr_writer using (true) with check (true)",
        "create policy dlr_writer_all on public.pipeline_run for all to dlr_writer using (true) with check (true)",
    ]

    for statement in statements:
        lowered = statement.lower()
        for forbidden in ("password", "bypassrls", "superuser", "createrole", "createdb", "truncate", "delete"):
            assert forbidden not in lowered, (forbidden, statement)
    # No credential or connection string anywhere in the file, comments included.
    assert "password" not in raw
    assert not re.search(r"postgres(ql)?://", raw)


def test_migration_is_reapply_safe():
    statements = _statements()
    creates = [s for s in statements if s.startswith("create table")]
    assert len(creates) == 2
    assert all(s.startswith("create table if not exists ") for s in creates)

    for index, statement in enumerate(statements):
        if statement.startswith("create policy "):
            name, table = re.match(r"create policy (\w+) on ([\w.]+)", statement).groups()
            assert statements[index - 1] == f"drop policy if exists {name} on {table}"

    for statement in statements:
        assert not statement.startswith("create index"), statement
        assert not statement.startswith("create unique index"), statement
        assert not statement.startswith("drop table"), statement
        if "create role" in statement:
            assert statement.startswith("do $$") and "if not exists" in statement


def test_every_column_has_a_comment_and_every_value_a_unit():
    comments = _comments()
    expected = {f"public.city_rating.{n}" for n, _ in _CITY_RATING_COLUMNS}
    expected |= {f"public.pipeline_run.{n}" for n, _ in _PIPELINE_RUN_COLUMNS}
    expected |= {"public.city_rating", "public.pipeline_run"}
    assert set(comments) == expected
    assert all(text.strip() for text in comments.values())

    unit_suffixes = ("_amps", "_mw", "_kv", "_c", "_ms", "_deg", "_wm2", "_min")
    unit_words = ("amperes", "megawatts", "kilovolts", "dimensionless", "degrees", "metres", "watts", "minutes")
    for name, kind in _CITY_RATING_COLUMNS:
        if kind != "double precision":
            continue
        text = comments[f"public.city_rating.{name}"].lower()
        assert name.endswith(unit_suffixes) or text.startswith("dimensionless"), name
        assert text.startswith(unit_words), (name, text)
    assert comments["public.city_rating.power_factor"].lower().startswith("dimensionless")
    assert comments["public.city_rating.air_temp_c"].startswith("degrees Celsius")
    assert comments["public.city_rating.wind_perp_ms"].startswith("metres per second, component perpendicular")
    assert comments["public.city_rating.solar_radiation_wm2"].startswith("watts per square metre")
    assert comments["public.city_rating.forecast_horizon_min"].startswith("minutes")
    for name in ("valid_time", "observation_time", "first_written_at", "computed_at"):
        assert comments[f"public.city_rating.{name}"].startswith("UTC instant")

    assert "hour-truncated" in comments["public.city_rating.valid_time"]
    assert "never changes" in comments["public.city_rating.first_written_at"].lower()
    assert "updated on every rewrite" in comments["public.city_rating.computed_at"]
    assert "aligned" in comments["public.city_rating.observation_time"]


def test_upsert_columns_match_the_migration_and_keep_first_written_at():
    migration_columns = [n for n, _, _ in _columns("city_rating")]
    expected = [c for c in migration_columns if c not in ("first_written_at", "computed_at")]
    assert list(supabase_store.CITY_RATING_COLUMNS) == expected
    assert len(supabase_store.CITY_RATING_COLUMNS) == 47

    sql = " ".join(supabase_store.UPSERT_RATING_SQL.split())
    assert "on conflict (city, valid_time) do update set" in sql
    assert "computed_at = date_trunc('second', now())" in sql
    assert "first_written_at" not in sql
    assert set(re.findall(r"%\((\w+)\)s", sql)) == set(expected)
    set_clause = sql.split("do update set", 1)[1]
    assigned = re.findall(r"(\w+) = excluded\.\1", set_clause)
    assert assigned == [c for c in expected if c not in supabase_store.KEY_COLUMNS]
    assert "%(probe_trail)s::jsonb" in sql


def test_identity_columns_have_hex_checks_and_the_fingerprint_is_required():
    attrs = {n: a for n, _, a in _columns("city_rating")}
    assert "not null" in attrs["config_fingerprint"]
    for name in ("config_fingerprint", "forecast_model_sha256", "anomaly_model_sha256"):
        assert f"constraint city_rating_{name}_ck check ({name} ~ '^[0-9a-f]{{64}}$')" in attrs[name]
    for name in ("forecast_model_sha256", "anomaly_model_sha256"):
        assert "not null" not in attrs[name]
    comments = _comments()
    for name in ("config_fingerprint", "forecast_model_sha256", "anomaly_model_sha256"):
        assert comments[f"public.city_rating.{name}"].startswith("none (identifier)")
    assert "rating_config_snapshot" in comments["public.city_rating.config_fingerprint"]
    assert "NULL" in comments["public.city_rating.forecast_model_sha256"]
    assert "NULL" in comments["public.city_rating.anomaly_model_sha256"]


def test_original_migration_is_unchanged():
    # The original file is applied to the live project; fixes go in a new additive migration.
    with open(_MIGRATION, "rb") as handle:
        assert hashlib.sha256(handle.read()).hexdigest() == _ORIGINAL_MIGRATION_SHA256


def test_review_fix_migration_makes_the_hour_check_zone_independent():
    statements = _statements(_FIX_MIGRATION)
    assert os.path.basename(_FIX_MIGRATION) > os.path.basename(_MIGRATION)  # applies after the original
    assert statements[0] == "alter table public.city_rating drop constraint if exists city_rating_valid_time_hour_ck"
    assert statements[1] == (
        "alter table public.city_rating add constraint city_rating_valid_time_hour_ck check "
        "((valid_time at time zone 'UTC') = date_trunc('hour', valid_time at time zone 'UTC'))"
    )
    # The session-zone form must not come back.
    assert "check (valid_time = date_trunc('hour', valid_time))" not in " ".join(statements)


def test_review_fix_migration_is_reapply_safe_and_grants_nothing():
    statements = _statements(_FIX_MIGRATION)
    raw = _raw(_FIX_MIGRATION).lower()
    for statement in statements:
        assert statement.startswith(("alter table public.city_rating ", "comment on column public.pipeline_run.")), statement
        for forbidden in ("create ", "grant ", "revoke ", "policy", "role", "drop table", "add column",
                          "password", "truncate", "delete"):
            assert forbidden not in statement.lower(), (forbidden, statement)
    for statement in statements:
        if " add constraint " in statement:
            index = statements.index(statement)
            assert statements[index - 1] == statement.replace(" add constraint ", " drop constraint if exists ", 1).split(" check ")[0]
    assert "password" not in raw
    assert not re.search(r"postgres(ql)?://", raw)


def test_run_log_comments_match_the_schema_doc():
    comments = {name: text.replace("''", "'") for name, text in _effective_comments().items()}
    ok = comments["public.pipeline_run.cities_ok"]
    failed = comments["public.pipeline_run.cities_failed"]
    assert ok.startswith("none (labels)") and failed.startswith("none (json)")
    assert "healthily" in ok and "cities_failed" in ok and "degraded" in ok
    for word in ("outcome", "error", "degraded", "written", "forecast_status",
                 "detector_model_loaded", "redacted", "error text"):
        assert word in failed, word

    doc = {}
    with open(_SCHEMA_DOC, encoding="utf-8") as handle:
        for line in handle:
            match = re.match(r"^\| `(cities_ok|cities_failed)` \| `[^`]+` \| (.*) \|$", line.rstrip("\n"))
            if match:
                doc[match.group(1)] = match.group(2)
    assert set(doc) == {"cities_ok", "cities_failed"}
    assert "healthily" in doc["cities_ok"] and "healthily" in ok
    assert "outcome" in doc["cities_failed"] and "outcome" in failed
    assert "`error` or `degraded`" in doc["cities_failed"]
