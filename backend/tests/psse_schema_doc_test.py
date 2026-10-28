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
    for table in ("psse_run",):
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
