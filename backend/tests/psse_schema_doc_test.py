"""
The PSS/E result-table spec stays in step with the reference DDL and psse_job
(pss-e-integration Phase 1, plan 01-03, DBX-01).

`docs/data-science/schema/psse_results_v1.md` is handed to production-pipeline Phase 6.
These tests parse the reference DDL `docs/data-science/schema/psse_results_v1.sql`, the
job-side constants and backend/config.py, so a column added, renamed or retyped, a CHECK
vocabulary changed or a rating unit changed in one place without the other fails here.
They are offline: no database, no network.

Follows backend/tests/supabase_schema_doc_test.py's conventions (module-level imports,
plain asserts, no test classes).
"""

import math
import os
import re
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import config  # noqa: E402
from psse_job import constants, units  # noqa: E402

_SCHEMA_DIR = os.path.join(_ROOT, "docs", "data-science", "schema")
DOC_PATH = os.path.join(_SCHEMA_DIR, "psse_results_v1.md")
DDL_PATH = os.path.join(_SCHEMA_DIR, "psse_results_v1.sql")
CHECKS_PATH = os.path.join(_SCHEMA_DIR, "psse_results_v1_checks.sql")
HANDOFF_PATH = os.path.join(_ROOT, "docs", "data-science", "decisions", "psse_results_phase6_handoff.md")

REQUIRED_HEADINGS = (
    "## Phase 6 intake",
    "## Where the data lives",
    "## Keys, links and time semantics",
    "## Columns: public.psse_run",
    "## Columns: public.psse_dispatched_capacity",
    "## Columns: public.psse_voltage_margin",
    "## Columns: public.psse_contingency_result",
    "## ratings_used: the per-city rating record",
    "## Rating selection and static fallback (IN-01)",
    "## Units: amps per conductor to MVA per circuit",
    "## All-or-nothing write and failed runs (WB-02)",
    "## Completeness checks",
    "## Access: role dlr_psse_writer and grants",
    "## Reading rules",
    "## Open questions for Power Systems and Phase 6",
    "## Versioning",
)

TABLES = ("psse_run", "psse_dispatched_capacity", "psse_voltage_margin", "psse_contingency_result")

_SQL_TYPES = r"(text\[\]|double precision|timestamptz|integer|boolean|jsonb|text)"
_COLUMN_LINE = re.compile(r"^\s+([a-z_0-9]+)\s+" + _SQL_TYPES + r"(?=[\s,]|$)")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _ddl_columns(table):
    """[(name, sql type)] of one create-table block of the reference DDL, in order (one column per line)."""
    lines = _read(DDL_PATH).splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"create table if not exists public.{table} ("))
    columns = []
    for line in lines[start + 1:]:
        if line.startswith(");"):
            break
        match = _COLUMN_LINE.match(line)
        if match:
            columns.append((match.group(1), match.group(2)))
    return columns


def _section(doc, heading):
    """The text of one `## ` section, from its heading to the next `## ` heading."""
    lines = doc.splitlines()
    start = lines.index(heading)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start + 1:end])


def _table_rows(section):
    """{backticked first-cell name: [cells]} for each markdown table row of a section."""
    rows = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        match = re.fullmatch(r"`([a-z_0-9]+)`", cells[0])
        if match:
            rows[match.group(1)] = cells
    return rows


def _squash(text):
    """Whitespace-collapsed text with blockquote markers removed."""
    return re.sub(r"\s+", " ", text.replace("\n>", "\n")).strip()


_COMMENT_RE = re.compile(r"(comment\s+on\s+(?:table|column)\s+[\w.]+\s+is\s+)'(?:[^']|'')*'", re.IGNORECASE)
_COMMENT_BODY_RE = re.compile(r"comment\s+on\s+(?:table|column)\s+([\w.]+)\s+is\s+'((?:[^']|'')*)'", re.IGNORECASE)


def _code(path=None):
    """The DDL with comment bodies blanked and `--` comments removed."""
    text = _COMMENT_RE.sub(r"\1''", _read(path or DDL_PATH))
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def _statements(path=None):
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


def _comments():
    """{'public.psse_run.run_id': comment text} for every `comment on` entry of the DDL."""
    return {target: text for target, text in _COMMENT_BODY_RE.findall(_read(DDL_PATH))}


def _assert_no_connection_details(text):
    assert not re.search(r"postgres(?:ql)?://", text, re.IGNORECASE)
    assert "pooler." + "supabase.com" not in text
    assert "supabase" + ".co" not in text
    assert not re.search("sb_" + r"[a-z]+_[A-Za-z0-9_-]{8,}", text)
    assert not re.search(r"eyJ[A-Za-z0-9_-]{7,}", text)
    assert not re.search(r"https?://[^\s)]*@", text)


def test_doc_has_every_required_section_once():
    doc = _read(DOC_PATH)
    headings = [line for line in doc.splitlines() if line.startswith("## ")]
    assert headings == list(REQUIRED_HEADINGS)
    for heading in REQUIRED_HEADINGS:
        assert doc.splitlines().count(heading) == 1


def test_doc_lists_every_column_of_the_four_tables():
    doc = _read(DOC_PATH)
    for table in TABLES:
        columns = _ddl_columns(table)
        assert len(columns) >= 12, f"{table}: the DDL parser found only {len(columns)} columns"
        rows = _table_rows(_section(doc, f"## Columns: public.{table}"))
        assert [name for name, _ in columns] == list(rows), f"{table}: doc rows differ from the DDL, in names or order"
        for name, sql_type in columns:
            cells = rows[name]
            assert len(cells) == 5, f"{table}.{name}: expected Column | Type | Unit | NULL when | Meaning"
            assert cells[1] == f"`{sql_type}`", f"{table}.{name}: doc type {cells[1]} != DDL type {sql_type}"
            assert cells[2] != "", f"{table}.{name}: unit cell is empty (write 'none' for a unitless column)"
            assert cells[3] != "", f"{table}.{name}: the NULL-when cell is empty (write 'never')"
            assert cells[4] != "", f"{table}.{name}: no meaning"


def test_doc_contains_no_connection_details():
    _assert_no_connection_details(_read(DOC_PATH))


CHECK_NAMES = (
    "non_failed_runs_have_four_dispatch_rows",
    "non_failed_runs_have_four_margin_rows",
    "non_failed_runs_contingency_count_matches",
    "failed_runs_have_no_results",
    "dispatch_voltage_limit_matches_margin",
)


def test_doc_ratings_used_keys_match_constants():
    section = _section(_read(DOC_PATH), "## ratings_used: the per-city rating record")
    rows = _table_rows(section)
    assert list(rows) == list(constants.RATINGS_USED_KEYS), "doc keys differ from psse_job.constants.RATINGS_USED_KEYS"
    for key, cells in rows.items():
        assert len(cells) == 5, f"{key}: expected Key | JSON type | Unit | NULL when | Meaning"
        assert all(cell != "" for cell in cells), f"{key}: empty cell"


def test_doc_units_table_is_recomputed_from_config():
    section = _section(_read(DOC_PATH), "## Units: amps per conductor to MVA per circuit")
    rows = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if re.fullmatch(r"[A-Z_]+", cells[0]):
            rows[cells[0]] = cells
    assert list(rows) == list(constants.CITIES), "the units table must have exactly the four cities, in order"
    for city, cells in rows.items():
        assert len(cells) == 7, f"{city}: expected 7 cells"
        amps = config.STATIC_RATINGS[city]
        count = config.SUBCONDUCTORS_PER_PHASE[city]
        stored_mw = math.sqrt(3) * config.LINE_VOLTAGE_KV * amps * config.POWER_FACTOR / 1000
        mva = units.circuit_mva(amps, count, config.LINE_VOLTAGE_KV)
        assert float(cells[1]) == round(amps, 1), f"{city}: amps per conductor"
        assert int(cells[2]) == count, f"{city}: subconductors"
        assert float(cells[3]) == round(amps * count, 1), f"{city}: amps per circuit"
        assert float(cells[4]) == round(stored_mw, 1), f"{city}: stored rating_mw"
        assert float(cells[5]) == round(mva, 1), f"{city}: MVA per circuit"
        assert float(cells[6]) == round(mva / stored_mw, 3), f"{city}: ratio"


def test_doc_states_the_rules():
    doc = _read(DOC_PATH)
    needles = {
        "## Keys, links and time semantics": (
            "(run_id, run_outcome)", "(city, city_rating_valid_time)", "city_rating_computed_at",
            "not a foreign key", "hour floor", "only in `psse_run.ratings_used`",
        ),
        "## Rating selection and static fallback (IN-01)": tuple(
            f"`{reason}`" for reason in constants.FALLBACK_REASONS
        ) + ("90 minutes", "REVAL-01", "HH:30"),
        "## Units: amps per conductor to MVA per circuit": ("power factor", "`rating_mw`"),
        "## All-or-nothing write and failed runs (WB-02)": ("one transaction", "failed_stage", "SCH-02", "gap"),
        "## Completeness checks": (
            "docs/data-science/schema/psse_results_v1_checks.sql",
        ) + CHECK_NAMES,
        "## Access: role dlr_psse_writer and grants": (
            "INSERT", "SELECT", "UPDATE", "DELETE", "anon", "authenticated", "city_rating",
            "pipeline_run", "latest_rating", "SUPABASE_PSSE_DB_URL", "service_role",
        ),
        "## Reading rules": ("started_at desc, run_id desc",),
    }
    for heading, words in needles.items():
        section = _section(doc, heading)
        for word in words:
            assert word in section, f"{heading}: missing {word!r}"
    checks_sql = _read(CHECKS_PATH)
    for name in CHECK_NAMES:
        assert name in checks_sql, f"{name} is not in psse_results_v1_checks.sql"


def test_doc_has_no_unfilled_section():
    doc = _read(DOC_PATH)
    for heading in REQUIRED_HEADINGS:
        lines = [line for line in _section(doc, heading).splitlines() if line.strip()]
        assert len(lines) >= 2, f"{heading}: section is a placeholder"


def test_ddl_header_says_not_a_migration_and_markers_once():
    raw = _read(DDL_PATH)
    lines = raw.splitlines()
    assert "NOT a migration" in raw
    assert lines.count("-- BEGIN psse_results_v1") == 1
    assert lines.count("-- END psse_results_v1") == 1
    assert lines.index("-- BEGIN psse_results_v1") < lines.index("-- END psse_results_v1")


def test_ddl_creates_four_tables_idempotently():
    statements = _statements()
    creates = [s for s in statements if s.startswith("create table")]
    assert len(creates) == 4
    assert [s for s in statements if s.startswith("create table if not exists public.psse_")] == creates

    policies = 0
    for index, statement in enumerate(statements):
        if statement.startswith("create policy "):
            policies += 1
            name, table = re.match(r"create policy (\w+) on ([\w.]+)", statement).groups()
            assert statements[index - 1] == f"drop policy if exists {name} on {table}"
    assert policies == 8

    role_blocks = [s for s in statements if "create role" in s]
    assert len(role_blocks) == 1
    assert role_blocks[0].startswith("do $$") and "if not exists" in role_blocks[0]
    assert "rolname = 'dlr_psse_writer'" in role_blocks[0]

    for statement in statements:
        if statement.startswith("create index") or statement.startswith("create unique index"):
            assert re.match(r"create (unique )?index if not exists ", statement), statement
        assert not statement.startswith("drop table"), statement


def test_ddl_grants_are_exactly_the_d03_grants():
    statements = _statements()
    tables = ", ".join(f"public.{t}" for t in TABLES)
    assert [s for s in statements if s.startswith("grant ")] == [
        "grant usage on schema public to dlr_psse_writer",
        f"grant select, insert on {tables} to dlr_psse_writer",
    ]
    assert [s for s in statements if s.startswith("revoke ")] == [
        f"revoke all on {tables} from public, anon, authenticated"
    ]
    policies = [s for s in statements if s.startswith("create policy ")]
    assert len(policies) == 8
    for statement in policies:
        assert " to dlr_psse_writer " in statement, statement
        assert not re.search(r"\b(anon|authenticated|public)\b", statement.split(" to ", 1)[1]), statement


def test_ddl_has_no_credential_function_view_or_sequence():
    raw = _read(DDL_PATH).lower()
    assert "password" not in raw
    assert not re.search(r"postgres(ql)?://", raw)
    forbidden_starts = (
        "create function", "create or replace function", "create view", "create or replace view",
        "create materialized view", "create sequence", "alter role", "alter default privileges",
    )
    for statement in _statements():
        lowered = statement.lower()
        assert not lowered.startswith(forbidden_starts), statement
        assert "security definer" not in lowered, statement


def test_ddl_every_column_has_a_unit_first_comment():
    comments = _comments()
    expected = {f"public.{table}" for table in TABLES}
    kinds = {}
    for table in TABLES:
        for name, sql_type in _ddl_columns(table):
            expected.add(f"public.{table}.{name}")
            kinds[f"public.{table}.{name}"] = sql_type
    assert set(comments) == expected
    assert all(text.strip() for text in comments.values())

    double_starts = ("amperes", "megavolt-amperes", "megawatts", "kilovolts", "dimensionless", "per unit", "percent")
    for target, sql_type in kinds.items():
        text = comments[target]
        if sql_type == "double precision":
            assert text.startswith(double_starts), (target, text)
        elif sql_type == "timestamptz":
            assert text.startswith("UTC instant"), (target, text)
        elif sql_type == "integer":
            assert text.startswith(("count", "none (version)")), (target, text)


def test_vocabularies_match_psse_job_constants():
    expected = {
        "outcome": list(constants.OUTCOMES),
        "failed_stage": list(constants.FAILED_STAGES),
        "rating_source": list(constants.SOURCES),
        "fallback_reason": list(constants.FALLBACK_REASONS),
        "limiting_factor": list(constants.LIMITING_FACTORS),
        "violation_kind": list(constants.VIOLATION_KINDS),
        "element_type": list(constants.ELEMENT_TYPES),
        "unit": list(constants.RESULT_UNITS),
        "run_outcome": ["ok", "fallback"],
        "city": list(constants.CITIES),
    }
    found = {}
    lines = _read(DDL_PATH).splitlines()
    for table in TABLES:
        start = next(i for i, line in enumerate(lines) if line.startswith(f"create table if not exists public.{table} ("))
        for line in lines[start + 1:]:
            if line.startswith(");"):
                break
            match = _COLUMN_LINE.match(line)
            if not match:
                continue
            check = re.search(r"check \((\w+) in \(([^)]*)\)\)", line)
            if check and check.group(1) == match.group(1):
                found.setdefault(match.group(1), []).append((table, re.findall(r"'([^']*)'", check.group(2))))
    for column, wanted in expected.items():
        assert column in found, f"no inline vocabulary CHECK found for {column}"
        for table, values in found[column]:
            assert values == wanted, f"{table}.{column}: DDL {values} != psse_job {wanted}"
    assert len(found["city"]) == 3 and "psse_run" not in [t for t, _ in found["city"]]
    assert len(found["run_outcome"]) == 3
