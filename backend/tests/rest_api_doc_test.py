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
    # The 2026-11-02 go lifted the label going forward only: new rows lack the word, older rows keep it.
    assert "going forward only" in section
    assert "lacks the word" in section


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


# ---------------------------------------------------------------------------
# Pointers from the existing consumer docs (Task 3). The expected heading lists below were copied
# from the files as they stood before the edit (git HEAD of 2026-10-26), so a heading that is
# removed or renamed fails here.
# ---------------------------------------------------------------------------

API_CONTRACT = REPO / "docs" / "frontend" / "specs" / "api-contract.md"
F1_SPEC = REPO / "docs" / "frontend" / "specs" / "F1-data-access-api.md"
PSS_E = REPO / "docs" / "data-science" / "decisions" / "pss_e_handoff.md"
SCHEMA_DOC = REPO / "docs" / "data-science" / "schema" / "city_rating_v1.md"
CONSUMER_DOCS = (API_CONTRACT, F1_SPEC, PSS_E, SCHEMA_DOC)

EXPECTED_HEADINGS = {
    API_CONTRACT: [
        "## Authentication",
        "## Data sources overview",
        "## Request/response formats",
        "### 1. Station pipeline CSV (`pipeline_output_v1`)",
        "### 2. Merged ERCOT and DLR CSV",
        "### 3. Historical archive CSV",
        "### 4. City rating dict (`rate_city`)",
        "### 5. Shadow prediction JSONL",
        "### 6. Forecast result object (not exported)",
        "## Python entry points",
        "## Error codes",
        "## Rate limits",
        "## PROPOSED: HTTP surface",
        "## Open decisions on `api/` shape",
        "## Compatibility rules for consumers",
    ],
    F1_SPEC: [
        "## Current Implementation",
        "## Interface & Data Contract",
        "## Blocked by",
        "## Blocks",
        "## Parallel-safe with",
        "## Known Issues",
        "## Acceptance Criteria",
        "## Open Questions",
    ],
    PSS_E: [
        "## The understanding",
        "## What DS actually produces today that would feed this",
        "## What the production store fixes (2026-10)",
        "## Still open with Power Systems",
    ],
    SCHEMA_DOC: [
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
    ],
}


def _headings(path):
    return [line for line in path.read_text(encoding="utf-8").splitlines() if re.match(r"#{2,3} ", line)]


def _section(path, heading):
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start + 1:end])


def test_consumer_docs_link_to_the_rest_contract():
    for path in CONSUMER_DOCS:
        text = path.read_text(encoding="utf-8")
        targets = re.findall(r"\]\(([^)\s]*integration/rest-api\.md)\)", text)
        assert targets, "%s has no link to docs/integration/rest-api.md" % path.name
        for target in targets:
            assert (path.parent / target).resolve() == DOC.resolve(), (path.name, target)


def test_consumer_docs_keep_their_headings():
    for path, expected in EXPECTED_HEADINGS.items():
        found = _headings(path)
        assert [h for h in found if h in expected] == expected, path.name  # none lost, order kept
        if path == SCHEMA_DOC:
            # Phase 4's REQUIRED_HEADINGS: no new `## ` heading may be added to the schema doc
            assert [h for h in found if h.startswith("## ")] == expected, path.name


def test_city_rating_doc_states_the_view_and_the_word_rule():
    lives = _section(SCHEMA_DOC, "## Where the data lives")
    for needle in ("public.latest_rating", "age_minutes", "is_stale", "is_provisional", "rest-api.md",
                   "REST API", "OD-6", "when the owner applies Phase 6's migration"):
        assert needle in lives, needle
    assert "no consumer role has any access" not in lives
    provisional = _section(SCHEMA_DOC, "## Provisional label (OD-5)")
    for needle in ("latest_rating.is_provisional", "the word provisional", "rating_basis", "config_version",
                   "REVAL-01", "both lack the word", "(D-03)", "no longer provisional"):
        assert needle in provisional, needle
    fresh = _section(SCHEMA_DOC, "## Freshness and failures")
    for needle in ("is_stale", "age_minutes", "rpc/assert_fresh", "(D-02)"):
        assert needle in fresh, needle
    assert "supabase" + ".co" not in SCHEMA_DOC.read_text(encoding="utf-8")  # still no connection details


def test_consumer_docs_state_the_live_interface():
    api = API_CONTRACT.read_text(encoding="utf-8")
    auth = _section(API_CONTRACT, "## Authentication")
    for needle in ("rest-api.md", "publishable key", "apikey", "read-only", "DS owner"):
        assert needle in auth, needle
    rows = [line for line in api.splitlines() if line.startswith("| `public.latest_rating`")]
    assert len(rows) == 1 and "rest-api.md" in rows[0]
    assert len([line for line in api.splitlines() if line.startswith("| `public.city_rating`")]) == 1
    items = {m.group(1): m.group(0) for m in re.finditer(r"^(\d+)\. .*$", api, re.MULTILINE)}
    for number in ("4", "8"):
        assert "(live per-city ratings: Supabase REST, see rest-api.md)" in items[number], number

    f1 = _section(F1_SPEC, "## Interface & Data Contract")
    assert "rest-api.md" in f1
    for needle in ("latest_rating", "is_stale", "status", "fallback_gates", "static-fallback"):
        assert needle in f1, needle

    pss = PSS_E.read_text(encoding="utf-8")
    fixes = _section(PSS_E, "## What the production store fixes (2026-10)")
    for needle in ("rest-api.md", "docs/integration/examples/read_ratings.py", "Python 3.7", "sys.version",
                   "ssl.OPENSSL_VERSION", "when the owner applies Phase 6's migration"):
        assert needle in fixes, needle
    assert "a Python stdlib example is planned there" not in pss
    assert "no consumer has access" not in pss
    assert pss.rstrip().endswith("recorded as a standalone note per the user's request.*")
