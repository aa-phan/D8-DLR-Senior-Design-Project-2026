"""
The consumer schema contract stays in step with the migration and the config
(production-pipeline Phase 4, plan 04-04, DB-05, DB-06, R3).

`docs/data-science/schema/city_rating_v1.md` is read by the Software and Power
Systems teams. These tests parse the migration and the config, so a column added,
renamed or retyped, or a provisional label changed, without the doc fails here.

Follows backend/tests/city_rating_test.py's conventions (module-level imports,
plain asserts, no test classes, no network).
"""

import os
import re
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import config  # noqa: E402

DOC_PATH = os.path.join(_ROOT, "docs", "data-science", "schema", "city_rating_v1.md")
MIGRATION_PATH = os.path.join(_ROOT, "supabase", "migrations", "20261019000000_create_city_rating.sql")
API_CONTRACT_PATH = os.path.join(_ROOT, "docs", "frontend", "specs", "api-contract.md")
PSS_E_PATH = os.path.join(_ROOT, "docs", "data-science", "decisions", "pss_e_handoff.md")

REQUIRED_HEADINGS = (
    "## Where the data lives",
    "## Key and time semantics",
    "## Columns: public.city_rating",
    "## What fallback means",
    "## Provisional label (OD-5)",
    "## What produced each row (DB-06)",
    "## Freshness and failures",
    "## Forecast fields",
    "## Backfill rows",
    "## Reading rules for consumers",
    "## Run log: public.pipeline_run (operational, not for consumers)",
    "## Versioning",
)

_SQL_TYPES = r"(text\[\]|double precision|timestamptz|integer|boolean|jsonb|text)"
_COLUMN_LINE = re.compile(r"^\s+([a-z_0-9]+)\s+" + _SQL_TYPES + r"(?=[\s,]|$)")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _migration_columns(table):
    """[(name, sql type)] of one create-table block, in order (one column per line)."""
    lines = _read(MIGRATION_PATH).splitlines()
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


def test_doc_lists_every_column_of_both_tables_with_type_and_unit():
    doc = _read(DOC_PATH)

    rating_columns = _migration_columns("city_rating")
    assert len(rating_columns) >= 40
    rows = _table_rows(_section(doc, "## Columns: public.city_rating"))
    assert [name for name, _ in rating_columns] == list(rows), "doc rows differ from the migration, in names or order"
    for name, sql_type in rating_columns:
        cells = rows[name]
        assert len(cells) == 5, f"{name}: expected Column | Type | Unit | NULL when | Meaning"
        assert cells[1] == f"`{sql_type}`", f"{name}: doc type {cells[1]} != migration type {sql_type}"
        assert cells[2] != "", f"{name}: unit cell is empty (write 'none' for a unitless column)"
        assert cells[3] != "", f"{name}: the NULL-when cell is empty (write 'never')"
        assert cells[4] != "", f"{name}: no meaning"

    run_columns = _migration_columns("pipeline_run")
    assert len(run_columns) == 12
    run_rows = _table_rows(_section(doc, "## Run log: public.pipeline_run (operational, not for consumers)"))
    assert [name for name, _ in run_columns] == list(run_rows)
    for name, sql_type in run_columns:
        cells = run_rows[name]
        assert len(cells) == 3, f"{name}: expected Column | Type | Meaning"
        assert cells[1] == f"`{sql_type}`", f"{name}: doc type {cells[1]} != migration type {sql_type}"
        assert cells[2] != ""


def test_doc_has_every_required_section_once():
    doc = _read(DOC_PATH)
    headings = [line for line in doc.splitlines() if line.startswith("## ")]
    assert headings == list(REQUIRED_HEADINGS)
    for heading in REQUIRED_HEADINGS:
        assert doc.splitlines().count(heading) == 1
    for needle in (
        "(city, valid_time)",
        "first_written_at",
        "computed_at",
        "observation_time",
        "no older than 90 minutes",
    ):
        assert needle in doc, f"missing statement: {needle}"


def test_doc_quotes_the_current_provisional_labels():
    doc = _read(DOC_PATH)
    section = _section(doc, "## Provisional label (OD-5)")
    assert _squash(config.RATING_BASIS) in _squash(section), (
        "config.RATING_BASIS changed: update the blockquote in the provisional label section"
    )
    assert f"`{config.RATING_CONFIG_VERSION}`" in section, (
        "config.RATING_CONFIG_VERSION changed: update the provisional label section"
    )


def test_doc_contains_no_connection_details():
    doc = _read(DOC_PATH)
    assert not re.search(r"postgres(?:ql)?://", doc, re.IGNORECASE)
    assert "pooler." + "supabase.com" not in doc
    assert "supabase" + ".co" not in doc
    assert not re.search("sb_" + r"[a-z]+_[A-Za-z0-9_-]{8,}", doc)
    assert not re.search(r"eyJ[A-Za-z0-9_-]{7,}", doc)
    assert not re.search(r"https?://[^\s)]*@", doc)


def test_doc_explains_row_identity_and_keeps_rows_provisional():
    doc = _read(DOC_PATH)
    identity = _section(doc, "## What produced each row (DB-06)")
    for needle in (
        "config_version",
        "config_fingerprint",
        "forecast_model_sha256",
        "anomaly_model_sha256",
        "diameter",
        "resistance",
        "emissivity",
        "absorptivity",
        "temperature",
        "elevation",
        "azimuth",
        "naive",
        "PSS/E",
    ):
        assert needle in identity, f"the DB-06 section does not mention {needle!r}"
    for heading in ("## Backfill rows", "## Provisional label (OD-5)"):
        section = _section(doc, heading)
        assert "provisional" in section.lower(), f"{heading}: no provisional label"
        assert "REVAL-01" in section, f"{heading}: does not say when the label is lifted"
    # R3: the NO-GO is stated and no row is described as having passed it.
    assert "NO-GO" in _section(doc, "## Provisional label (OD-5)")
    assert "2026-10-21" in _section(doc, "## Provisional label (OD-5)")
    for sentence in re.split(r"(?<=[.;])\s+", _squash(doc)):
        if re.search(r"passed (?:a|the) go/no-go", sentence, re.IGNORECASE):
            assert re.search(r"\bNo row\b|\bNever\b|\bnot\b", sentence), f"claims a go/no-go was passed: {sentence}"
