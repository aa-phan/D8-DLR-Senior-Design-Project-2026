"""
Guards for the day-ahead handoff text in the four consumer docs (production-pipeline Phase 8, 08-12,
D-18, DAY-06, DAY-08, DAY-09): the Software team's handoff, the frontend api-contract, the PSS/E note
and the Examples section of the REST contract. Offline and text only: every check reads a committed
markdown file, compares column names with day_ahead_contract and runs the repository's secret scan
over each line. Planted strings are assembled from pieces so secret_scan_test.py never matches this
file, and no project value appears anywhere.
"""

import re
from pathlib import Path

import day_ahead_contract as contract
import secret_scan_test as scan

REPO = Path(__file__).resolve().parents[2]
SOFTWARE = REPO / "docs" / "integration" / "software-team-handoff.md"
API_CONTRACT = REPO / "docs" / "frontend" / "specs" / "api-contract.md"
PSS_E = REPO / "docs" / "data-science" / "decisions" / "pss_e_handoff.md"
REST_API = REPO / "docs" / "integration" / "rest-api.md"
SCHEMA_DOC = REPO / "docs" / "data-science" / "schema" / "day_ahead_forecast_v1.md"
CITY_SCHEMA = REPO / "docs" / "data-science" / "schema" / "city_rating_v1.md"
DOCS = (SOFTWARE, API_CONTRACT, PSS_E, REST_API)

_ALL_COLUMNS = set(contract.UPCOMING_COLUMNS) | set(contract.STATUS_COLUMNS)


def _lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def _section(path, heading):
    """The text under a '## ' heading, up to the next '## ' heading."""
    lines = _lines(path)
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start + 1:end])


def _table_rows(text):
    """Cells of every pipe-table row in `text` (separator rows skipped)."""
    rows = []
    for line in text.splitlines():
        if line.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


# ---------------------------------------------------------------------------
# Software team handoff
# ---------------------------------------------------------------------------


def test_software_handoff_has_one_day_ahead_section_between_the_rules_and_the_cadence():
    lines = _lines(SOFTWARE)
    assert lines.count("## Day-ahead forecast") == 1
    position = lines.index("## Day-ahead forecast")
    assert lines.index("## Rules that are easy to get wrong") < position < lines.index("## Cadence and polling")
    section = _section(SOFTWARE, "## Day-ahead forecast")
    for name in ("day_ahead_upcoming", "day_ahead_status", "day_ahead_forecast"):
        assert name in section, name
    assert contract.DAY_AHEAD_LABEL in section
    assert "](rest-api.md)" in section
    assert "](../data-science/schema/day_ahead_forecast_v1.md)" in section


def test_software_handoff_dashboard_table_uses_only_contract_columns():
    section = _section(SOFTWARE, "## Day-ahead forecast")
    rows = _table_rows(section)
    assert rows[0] == ["Dashboard view", "Read from", "Columns"]
    body = rows[1:]
    assert len(body) >= 2
    used = set()
    for cells in body:
        assert len(cells) == 3, cells
        assert cells[1].strip("`") in ("day_ahead_upcoming", "day_ahead_status") or "day_ahead_" in cells[1]
        names = re.findall(r"`([a-z_0-9]+)`", cells[2])
        assert names, cells
        assert set(names) <= _ALL_COLUMNS, sorted(set(names) - _ALL_COLUMNS)
        used.update(names)
    for needed in ("city", "valid_time", "forecast_amps", "forecast_ci_lower_amps", "forecast_ci_upper_amps",
                   "lead_minutes", "issued_at", "band_source", "label", "is_late", "missing_targets",
                   "next_target_time"):
        assert needed in used, needed


def test_software_handoff_lists_the_easy_mistakes_in_plain_words():
    section = _section(SOFTWARE, "## Day-ahead forecast")
    mistakes = section.lower()
    for phrase in ("not the live rating", "never gates", "band", "label", "weather run", "is_late",
                   "00/06/12/18 utc", "from another hour or city"):
        assert phrase in mistakes, phrase
    assert "24 h" in section and "0-18 h" in section
    assert "hourly polling is enough" in section


def test_software_handoff_tables_list_the_three_day_ahead_objects_and_the_alarm():
    text = SOFTWARE.read_text(encoding="utf-8")
    key_rows = [line for line in text.splitlines() if line.startswith("| Reads `day_ahead_upcoming`")]
    assert len(key_rows) == 1
    assert "`day_ahead_status`" in key_rows[0] and "`day_ahead_forecast`" in key_rows[0]
    assert key_rows[0].rstrip().endswith("| Allowed |")
    readable = _section(SOFTWARE, "## What you can read")
    for name in ("day_ahead_upcoming", "day_ahead_status", "day_ahead_forecast"):
        rows = [line for line in readable.splitlines() if line.startswith("| `%s`" % name)]
        assert len(rows) == 1, name
    pt503 = next(line for line in text.splitlines() if line.startswith("| 503 | `PT503`"))
    assert "day_ahead_late" in pt503
    # the older rows are still there
    assert any(line.startswith("| `latest_rating` |") for line in readable.splitlines())
    assert any(line.startswith("| `rpc/assert_fresh` |") for line in readable.splitlines())


# ---------------------------------------------------------------------------
# frontend api-contract
# ---------------------------------------------------------------------------


def test_api_contract_lists_the_three_day_ahead_objects_after_latest_rating():
    lines = _lines(API_CONTRACT)
    expected = {
        "| `public.day_ahead_forecast`": ("day_ahead_forecast_v1.md",),
        "| `public.day_ahead_upcoming`": ("rest-api.md",),
        "| `public.day_ahead_status`": ("rest-api.md",),
    }
    latest = next(i for i, line in enumerate(lines) if line.startswith("| `public.latest_rating`"))
    for offset, (prefix, targets) in enumerate(expected.items(), start=1):
        found = [i for i, line in enumerate(lines) if line.startswith(prefix)]
        assert len(found) == 1, prefix
        assert found[0] == latest + offset, prefix  # right after the latest_rating row, in this order
        row = lines[found[0]]
        assert any(target in row for target in targets), prefix
        assert len(_table_rows(row)[0]) == 5, prefix  # the same five-column format
        assert "Versioned contract (v1, additive-only)" in row, prefix
    assert len([line for line in lines if line.startswith("| `public.city_rating`")]) == 1
    assert len([line for line in lines if line.startswith("| `public.latest_rating`")]) == 1
    assert "Phase 8" in lines[latest + 1]


# ---------------------------------------------------------------------------
# PSS/E handoff
# ---------------------------------------------------------------------------


def test_pss_e_handoff_explains_next_day_study_use():
    heading = "## Day-ahead forecast (2026-11)"
    lines = _lines(PSS_E)
    assert heading in lines
    section = _section(PSS_E, heading)
    text = section.lower()
    # the four target hours with their Central times (CST and CDT)
    table = _table_rows(section)
    assert table, "no UTC to Central table"
    flat = " ".join(" ".join(row) for row in table)
    for needle in ("00:00 UTC", "06:00 UTC", "12:00 UTC", "18:00 UTC", "CST", "CDT"):
        assert needle in flat, needle
    for central in ("18:00 (previous day)", "06:00", "12:00", "19:00 (previous day)", "07:00", "13:00"):
        assert central in flat, central
    for phrase in ("closest", "no interpolation", "forecast_ci_lower_amps", "forecast_ci_upper_amps",
                   "not only", "band_source", "band_n", "no safety role", "not validated", "not the live rating",
                   "never sets or checks", "is_late", "missing_targets", "another city", "read_ratings.py",
                   "megawatt", "rest-api.md", "day_ahead_forecast_v1.md"):
        assert phrase in text, phrase
    assert contract.DAY_AHEAD_LABEL in section
    assert "python read_ratings.py" in section
    # the subsections are "###" headings inside the section
    subsections = [line for line in lines[lines.index(heading):] if line.startswith("### ")]
    assert len(subsections) >= 4


def test_pss_e_handoff_keeps_its_original_headings_and_footer():
    lines = _lines(PSS_E)
    original = ["## The understanding", "## What DS actually produces today that would feed this",
                "## What the production store fixes (2026-10)", "## Still open with Power Systems"]
    assert [line for line in lines if line in original] == original
    assert lines.index("## Still open with Power Systems") < lines.index("## Day-ahead forecast (2026-11)") < lines.index("---")
    assert PSS_E.read_text(encoding="utf-8").rstrip().endswith("recorded as a standalone note per the user's request.*")


# ---------------------------------------------------------------------------
# REST contract Examples section
# ---------------------------------------------------------------------------


def test_rest_api_examples_section_names_the_day_ahead_part():
    section = _section(REST_API, "## Examples")
    first = section.strip().splitlines()[0]
    for needle in ("(3)", "day_ahead_upcoming", "day_ahead_status", "upcoming day-ahead targets",
                   "per-city day-ahead status"):
        assert needle in first, needle
    assert "(1) the current row of every city from `latest_rating`" in first
    assert "(2) one city's rows over a date range from `city_rating`" in first


# ---------------------------------------------------------------------------
# Hygiene
# ---------------------------------------------------------------------------


def test_the_four_docs_hold_no_secret_and_no_project_host_or_url():
    host_marker = "." + "supa" + "base" + "."
    for path in DOCS:
        for number, line in enumerate(_lines(path), start=1):
            assert scan._scan_line(line) == [], (path.name, number)
            assert host_marker not in line.lower(), (path.name, number)
            assert not re.search(r"https?://[A-Za-z0-9-]{20}\.", line), (path.name, number)
            assert not re.search(r"\beyJ[A-Za-z0-9_-]{7,}\.", line), (path.name, number)
            assert not re.search(r"\b[0-9a-f]{40,}\b", line), (path.name, number)
        assert "postgres" + "://" not in path.read_text(encoding="utf-8").lower(), path.name


def test_the_hygiene_check_would_catch_a_planted_value_and_the_schema_doc_is_untouched():
    planted_host = "a" * 20 + "." + "supa" + "base" + ".co"
    planted_key = "sb_" + "publishable_" + "Planted0123456789abcdef"
    assert scan._scan_line("see " + planted_host) == ["supabase_project_host"]
    assert scan._scan_line("key " + planted_key) == ["supabase_publishable_key"]
    # the REST column tables and the schema doc have no new "## " heading from this plan
    assert SCHEMA_DOC.exists() and CITY_SCHEMA.exists()
    city_headings = [line for line in _lines(CITY_SCHEMA) if line.startswith("## ")]
    assert not any("ay-ahead" in heading for heading in city_headings)
