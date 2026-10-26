"""
Offline guard for the consumer REST contract docs/integration/rest-api.md
(production-pipeline Phase 6, API-01 "units documented", API-02, D-05, D-10).

The doc is the only contract the Software and Power Systems teams get (the publishable key can no
longer read PostgREST's OpenAPI), so its `latest_rating` column table is compared with
`latest_rating_contract.LATEST_COLUMNS` and fails the moment the two drift apart. Nothing here
touches the network. Planted strings are assembled from pieces so
backend/tests/secret_scan_test.py never matches this file.
"""

import re
from pathlib import Path

import pytest

import secret_scan_test as scan
from latest_rating_contract import LATEST_COLUMNS

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "integration" / "rest-api.md"
COLUMNS_HEADING = "## `latest_rating` columns"
ALLOWED_TYPES = {"text", "timestamptz", "double precision", "boolean", "text[]", "integer"}


def _text():
    return DOC.read_text(encoding="utf-8")


def _column_rows():
    """(name, type, unit, meaning) for every row of the table under the `latest_rating` columns heading."""
    lines = _text().splitlines()
    start = lines.index(COLUMNS_HEADING)
    rows = []
    in_table = False
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells[0] == "Column":
                assert cells == ["Column", "Type", "Unit", "Meaning"]
                in_table = True
                continue
            if in_table and not set(cells[0]) <= set("-: "):
                rows.append(tuple(cells))
        elif in_table and line.strip():
            break
    return rows


# ---------------------------------------------------------------------------
# D-05: the column table is the contract module, column for column
# ---------------------------------------------------------------------------


def test_doc_column_table_matches_the_contract():
    rows = _column_rows()
    names = [re.fullmatch(r"`([a-z_0-9]+)`", row[0]).group(1) for row in rows]
    assert names == list(LATEST_COLUMNS)
    assert len(rows) == 34
    for name, kind, unit, meaning in rows:
        assert unit and meaning
        assert kind in ALLOWED_TYPES, (name, kind)
    types = {re.sub("`", "", row[0]): row[1] for row in rows}
    assert types["age_minutes"] == "integer"
    assert types["is_stale"] == "boolean" and types["is_provisional"] == "boolean"
    assert types["valid_time"] == "timestamptz" and types["fallback_gates"] == "text[]"


def test_doc_rating_columns_are_labelled_provisional():
    rows = {row[0].strip("`"): row for row in _column_rows()}
    rated = [name for name in rows if name.endswith("_amps") or name.endswith("_mw")]
    assert sorted(rated) == sorted([
        "rating_amps", "rating_mw", "static_rating_amps", "static_rating_mw",
        "forecast_amps", "forecast_ci_lower_amps", "forecast_ci_upper_amps"])
    for name in rated:
        assert "PROVISIONAL" in " ".join(rows[name]), name
    for name in ("config_fingerprint", "forecast_model_sha256", "anomaly_model_sha256"):
        assert "marks a conductor or model change" in rows[name][3], name
    stale = rows["is_stale"][3]
    assert "90 minutes" in stale and "Exactly 90 minutes is fresh" in stale
    assert "rounded up" in rows["age_minutes"][3]
    assert "provisional" in rows["is_provisional"][3] and "rating_basis" in rows["is_provisional"][3]
    assert sum(1 for line in _text().splitlines() if "PROVISIONAL" in line) >= 10


# ---------------------------------------------------------------------------
# The terms the contract must state
# ---------------------------------------------------------------------------

_REQUIRED_TERMS = [
    "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "apikey", "rpc/assert_fresh", "503", "PT503", "22023",
    "1000", "90 minutes", "OD-1", "OD-4", "OD-5", "OD-6", "OD-7", "OD-9", "REVAL-01", "fallback_gates",
    "@supabase/supabase-js@2", "Python 3.7", "Node 22", "60 seconds", "sys.version", "ssl.OPENSSL_VERSION",
    "14:07", "14:12", "count=exact", "gives both values to each team directly", "never written into this repository",
    "newest row", "not an error", "valid, safe, published", "OpenAPI", "never reduce across cities",
]


def test_doc_states_the_contract_terms():
    text = _text()
    lowered = text.lower()
    missing = [term for term in _REQUIRED_TERMS if term.lower() not in lowered]
    assert missing == []
    # each decision is stated where it applies, not just named
    freshness = text.split("## Freshness", 1)[1].split("\n## ", 1)[0]
    for needle in ("OD-1", "OD-7", "OD-4", "OD-9", "is_stale", "14:12", "Exactly 90 minutes is fresh",
                   "more than 90 minutes is stale", "reads `is_stale` true", "started minute"):
        assert needle in freshness, needle
    fallback = text.split("## Fallback rows", 1)[1].split("\n## ", 1)[0]
    for needle in ("D-04", "status", "fallback_gates", "safe", "not an error"):
        assert needle in fallback, needle
    for heading in ("## Connecting", "## Endpoints", COLUMNS_HEADING, "## Freshness", "## Fallback rows",
                    "## Provisional values", "## What produced each row", "## Timestamps", "## Status codes",
                    "## Write protection and visibility", "## Limits and polling", "## Examples",
                    "## PSS/E environment", "## OpenAPI", "## Compatibility", "## Monitoring"):
        assert heading in text.splitlines(), heading
    order = [text.index(h) for h in ("## Connecting", "## Endpoints", COLUMNS_HEADING, "## Freshness", "## Monitoring")]
    assert order == sorted(order)


def test_doc_states_the_provisional_hand_off():
    section = _text().split("## Provisional values", 1)[1].split("\n## ", 1)[0]
    for needle in ("REVAL-01", "rating_basis", "config_version", "both", "no longer provisional",
                   "any capitalisation", "OR in"):
        assert needle in section, needle
    assert "remove the word" in section


# ---------------------------------------------------------------------------
# D-10, T-06-19, T-06-20
# ---------------------------------------------------------------------------


def test_doc_contains_no_connection_details():
    host_marker = "." + "supa" + "base" + "."
    for number, line in enumerate(_text().splitlines(), start=1):
        assert scan._scan_line(line) == [], number
        assert host_marker not in line.lower(), number
        assert not re.search(r"https?://[A-Za-z0-9-]{20}\.", line), number
        assert not re.search(r"\beyJ[A-Za-z0-9_-]{7,}\.", line), number
        assert not re.search(r"authorization\s*:", line, re.IGNORECASE), number
    lowered = _text().lower()
    assert "bearer" not in lowered  # the key goes in apikey only; nothing here may suggest a bearer token
    assert "never in an `authorization` header" in lowered
    assert "sb_" + "secret_" in _text()  # named only to say consumers never use one
    assert "postgres" + "://" not in lowered


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


def test_doc_links_resolve():
    text = _text()
    targets = re.findall(r"\]\(([^)\s]+)\)", text)
    assert targets
    for target in targets:
        if target.startswith(("http://", "https://", "#")):
            continue
        path = (DOC.parent / target.split("#", 1)[0]).resolve()
        assert path.is_file(), target
    for needle in ("examples/read_ratings.py", "examples/curl.sh", "examples/supabase_js.mjs",
                   "../data-science/schema/city_rating_v1.md", "../data-science/decisions/dlr_live_runbook.md"):
        assert "](%s)" % needle in text, needle
