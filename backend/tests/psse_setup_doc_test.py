"""
DOC-01 drift gates for the laptop setup guide and runbook (pss-e-integration Phase 3, plan 03-06).

`docs/data-science/decisions/psse_laptop_setup.md` (the guide) and `psse_laptop_runbook.md` (the
runbook) say how to install and prove the hourly PSS/E job on the licensed laptop. These tests keep
them equal to the code they describe: the guide's configuration-key table equals
`launcher.CONFIG_KEYS`, its exit-code table equals `launcher.EXIT_CODES` (and the gaps and credcheck
constants), its Task Scheduler settings table equals the values in the XML template, its psycopg pins
equal `requirements.txt`, every command block parses with the launcher's own parser and every SQL
block runs on a local database. They also hold the documents to the rules of a public repository: no
secret, host, user path, case name or stray number, every claim about the laptop tagged
`[UNVERIFIED until step N]` with a step that exists, and the prohibitions stated in words.

The documents are read as UTF-8 from the repository root. The study-definitions note is read and never
changed. The Postgres-backed tests are skipped unless `DLR_TEST_PG_AUTOSTART=1` or
`DLR_TEST_DATABASE_URL` names a local throwaway database (host 127.0.0.1, localhost or ::1); with
`PSSE_REQUIRE_PG=1` a missing database, driver or binary fails instead of skipping.

Honest scope: these tests prove that the documents match the code and that every documented command
and statement parses or runs on fakes and a local database. They prove nothing about real PSS/E,
Windows Task Scheduler, the licence, the laptop or the live database; the documents say so with their
tags, and nobody other than the author has followed them yet.

Follows backend/tests/psse_schema_doc_test.py and psse_study_doc_test.py (module-level imports, plain
asserts, no test classes).
"""

import datetime
import os
import re
import sys
import xml.etree.ElementTree as ET

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_local_pg as pg_helper  # noqa: E402
import secret_scan_test  # noqa: E402
from psse_rehearsal_test import (  # noqa: E402
    COMMAND_NAMES, LAUNCHER_NAMES, MANUAL, RENDER_NAMES, RENDER_SHAPES, SHAPES, command_blocks,
    launcher_arguments, render_arguments,
)
from psse_job import credcheck, gaps, launcher  # noqa: E402

_DECISIONS = os.path.join(_ROOT, "docs", "data-science", "decisions")
GUIDE = os.path.join(_DECISIONS, "psse_laptop_setup.md")
RUNBOOK = os.path.join(_DECISIONS, "psse_laptop_runbook.md")
STUDY_NOTE = os.path.join(_DECISIONS, "psse_study_definitions.md")
TEMPLATE = os.path.join(_ROOT, "docs", "data-science", "ops", "psse_hourly_task.xml")
REQUIREMENTS = os.path.join(_ROOT, "requirements.txt")
WRITER_ROLE = "dlr_psse_writer"

GUIDE_HEADINGS = (
    "## Purpose and scope",
    "## Prerequisites and how to read each",
    "## Interpreter and psycopg decision table",
    "## Install",
    "## Configuration file",
    "## First checks, in order",
    "## Task Scheduler",
    "## Reading results and the gap check",
    "## Exit codes and where to look",
    "## Troubleshooting",
    "## Credential hygiene",
    "## Uninstall",
    "## Hand-over record",
    "## Questions for the user, the teammate and the owner",
)
QUESTIONS_HEADING = GUIDE_HEADINGS[-1]

# Whole numbers of five or six digits the documents may quote, none a bus number of Power Systems'
# case. 10000 is the transfer.max_mw ceiling of the study note; 20000 is the default bus limit the
# launcher passes to psseinit (PSSE_MAX_BUSES); 65536 is the byte cap of the configuration file and of
# the mapping file; 90000 and 99999 are the bounds of the placeholder bus range of the example
# mapping; 999999 is the largest bus number the mapping accepts. A number added here needs a comment
# saying why.
ALLOWED_FIVE_OR_SIX_DIGITS = frozenset(["10000", "20000", "65536", "90000", "99999", "999999"])

# The only web hosts the documents may link to: the package index and Microsoft's documentation.
ALLOWED_URL_PREFIXES = ("https://pypi.org/", "https://learn.microsoft.com/")


# --------------------------------------------------------------------------- reading the documents


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _section(text, heading):
    """The text of one `## ` section: from its heading line to the next `## ` heading."""
    start = text.index("\n" + heading + "\n") + 1
    end = text.find("\n## ", start + len(heading))
    return text[start:end if end != -1 else len(text)]


def _tables(section):
    """[(header cells, [row cells, ...])] for every Markdown table of `section`."""
    tables = []
    current = []
    for line in section.splitlines() + [""]:
        if line.startswith("|"):
            current.append([cell.strip() for cell in line.strip().strip("|").split("|")])
            continue
        if current:
            rows = [cells for cells in current if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)]
            tables.append((rows[0], rows[1:]))
            current = []
    return tables


def _table(section, first_header):
    """The table of `section` whose first header cell is `first_header` (exactly one must exist)."""
    found = [table for table in _tables(section) if table[0][0] == first_header]
    assert len(found) == 1, "%d tables start with %r" % (len(found), first_header)
    return found[0]


def _backticked(cell):
    match = re.fullmatch(r"`([^`]+)`", cell)
    assert match is not None, "not a single backticked value: %r" % cell
    return match.group(1)


def _fenced_blocks(text):
    """[(info string, body)] for every fenced code block of `text`."""
    return re.findall(r"^```([a-z]*)\n(.*?)\n```$", text, re.M | re.S)


# --------------------------------------------------------------------------- the sections


def test_guide_has_required_sections_in_order():
    text = _read(GUIDE)
    lines = text.splitlines()
    positions = []
    for heading in GUIDE_HEADINGS:
        assert lines.count(heading) == 1, heading
        positions.append(lines.index(heading))
    assert positions == sorted(positions)
    last = _section(text, QUESTIONS_HEADING)
    assert text.rstrip().endswith(last.rstrip())  # the questions are the last section
    assert "](psse_laptop_runbook.md)" in text


# --------------------------------------------------------------------------- tables equal to the code


def _modes_cell(key):
    """How the guide writes the modes that need a key (the launcher's pseudo-modes in words)."""
    words = {"dry-run": "run --dry-run", "credcheck-rest": "credcheck (REST leg)"}
    return ", ".join(words.get(mode, mode) for mode in key.required_for) or "none"


def test_guide_config_key_table_equals_launcher_config_keys(tmp_path):
    section = _section(_read(GUIDE), "## Configuration file")
    header, rows = _table(section, "Key")
    assert header == ["Key", "Required for", "Secret", "Default", "Meaning"]
    assert len(launcher.CONFIG_KEYS) == 14
    names = [_backticked(cells[0]) for cells in rows]
    assert names == [key.name for key in launcher.CONFIG_KEYS]  # same keys, same order, none missing or extra

    # The defaults come from running the reader on a file with no keys, so the table follows the code.
    empty = tmp_path / "empty.env"
    empty.write_text("# no keys\n", encoding="utf-8")
    defaults = launcher.read_config(str(empty))
    assert set(defaults) == {"PSSE_LOG_DIR", "PSSE_LOCK_PATH", "PSSE_MAX_BUSES", "PSSE_PREFLIGHT"}

    for key, cells in zip(launcher.CONFIG_KEYS, rows):
        assert cells[1] == _modes_cell(key), key.name
        assert cells[2] == ("yes" if key.secret else "no"), key.name
        assert cells[4], key.name  # a meaning is written
        if key.name not in defaults:
            assert cells[3] == "none", key.name
        elif key.name in ("PSSE_LOG_DIR", "PSSE_LOCK_PATH"):
            assert "`%s`" % os.path.basename(defaults[key.name]) in cells[3] and "next to" in cells[3], key.name
        else:
            assert cells[3] == "`%s`" % defaults[key.name], key.name


def test_guide_exit_code_table_equals_launcher_exit_codes():
    section = _section(_read(GUIDE), "## Exit codes and where to look")
    header, rows = _table(section, "Code")
    assert header == ["Code", "Name", "Meaning"]
    assert [(int(cells[0]), _backticked(cells[1]), cells[2]) for cells in rows] == [
        (code, name, meaning) for name, code, meaning in launcher.EXIT_CODES]
    assert [code for _, code, _ in launcher.EXIT_CODES] == list(range(8))
    # the other modules return the launcher's codes: a mode's own constant is its exit code
    by_name = dict((name, code) for name, code, _ in launcher.EXIT_CODES)
    assert gaps.EXIT_OK == credcheck.EXIT_OK == by_name["ok"] == 0
    assert gaps.EXIT_GAPS == by_name["gaps"] == 5
    assert gaps.EXIT_CHECK_FAILED == by_name["check_failed"] == 6
    assert credcheck.EXIT_CHECK_FAILED == by_name["check_failed"]
    # a second table says where to look first for each code
    where_header, where_rows = _table(section, "Exit code")
    assert where_header[:2] == ["Exit code", "Look first at"]
    assert [int(cells[0]) for cells in where_rows] == list(range(8))
    assert all(cells[1] for cells in where_rows)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def test_guide_xml_settings_table_equals_template_values():
    section = _section(_read(GUIDE), "## Task Scheduler")
    header, rows = _table(section, "Element")
    assert header == ["Element", "Value", "What it does"]
    root = ET.fromstring(_read(TEMPLATE).encode("utf-8"))
    documented = {}
    for cells in rows:
        documented[_backticked(cells[0])] = _backticked(cells[1])
        assert cells[2], cells[0]
    assert len(documented) == len(rows)
    for element, value in documented.items():
        found = [node for node in root.iter() if _local(node.tag) == element]
        assert found, "the template has no element %s" % element
        assert all((node.text or "").strip() == value for node in found), (element, value)
    # every entry of the template's Settings is documented, so a new setting forces a new row
    settings = [node for node in root.iter() if _local(node.tag) == "Settings"]
    assert len(settings) == 1
    assert {_local(node.tag) for node in settings[0]} <= set(documented)
    assert len(list(settings[0])) == 10  # the ten researched settings
    for element in ("Interval", "LogonType", "RunLevel"):
        assert element in documented


def _repository_pins():
    pins = {}
    for line in _read(REQUIREMENTS).splitlines():
        match = re.match(r"^(psycopg|psycopg-binary)==([0-9][0-9A-Za-z.]*)\s*$", line)
        if match:
            pins[match.group(1)] = match.group(2)
    return pins


def test_guide_psycopg_matrix_pins():
    section = _section(_read(GUIDE), "## Interpreter and psycopg decision table")
    header, rows = _table(section, "Interpreter")
    assert header == ["Interpreter", "Pin", "Wheel", "Note"]
    by_interpreter = dict((cells[0], cells) for cells in rows)
    assert list(by_interpreter) == ["3.7", "3.8", "3.9", "3.10 to 3.12", "3.13 to 3.14", "32-bit (any version)"]

    pins = _repository_pins()
    assert set(pins) == {"psycopg", "psycopg-binary"}
    assert pins["psycopg"] == pins["psycopg-binary"], "psycopg-binary must equal psycopg in requirements.txt"
    repository = pins["psycopg"]

    expected = {
        "3.7": ("psycopg[binary]==3.1.20", ["cp37"]),
        "3.8": ("psycopg[binary]==3.2.13", ["cp38"]),
        "3.9": ("psycopg[binary]==3.2.13", ["cp39"]),
        "3.10 to 3.12": ("psycopg[binary]==%s" % repository, ["cp310", "cp311", "cp312"]),
        "3.13 to 3.14": ("psycopg[binary]==%s" % repository, ["cp313", "cp314"]),
    }
    for interpreter, (pin, wheels) in expected.items():
        assert _backticked(by_interpreter[interpreter][1]) == pin, interpreter
        for wheel in wheels:
            assert wheel in by_interpreter[interpreter][2], (interpreter, wheel)
    thirty_two = by_interpreter["32-bit (any version)"]
    assert thirty_two[1] == "none" and "not supported" in thirty_two[3]
    assert "no win32 wheel" in thirty_two[3].lower() or "no wheel" in thirty_two[3].lower()
    assert "psycopg-binary" in section and "equal" in section.lower()


# --------------------------------------------------------------------------- what the guide forbids


def _paragraphs(text):
    return [part for part in re.split(r"\n\s*\n", text) if part.strip()]


def test_guide_states_prohibitions():
    text = _read(GUIDE)
    flags = re.I | re.S
    required = {
        "no service_role or secret key on the laptop": r"service_role.{0,120}never|never.{0,120}service_role",
        "no setx for secrets": r"do not use `?setx`?",
        "no SYSTEM account": r"SYSTEM",
        "no run whether logged on or not": r"logged on or not",
        "allow-placeholder only with dry-run": r"`?--allow-placeholder`?.{0,160}`?--dry-run`?",
        "never commit the case or mapping": r"never commit",
        "never paste output made with identifiers shown": r"never paste.{0,200}identifiers",
        "sslmode require or stronger": r"sslmode=require.{0,200}(verify-ca|verify-full)",
        "verify-full recommended with a CA certificate": r"verify-full.{0,200}(CA certificate|root certificate)",
        "icacls on the configuration file": r"icacls.{0,200}configuration file|configuration file.{0,200}icacls",
        "a user-only folder, not Downloads": r"Downloads",
        "only while the laptop is on": r"only while the laptop is on",
        "libpq environment variables are not isolated": r"PGSSLMODE.{0,200}not isolated|not isolated.{0,200}PGSSLMODE",
        "the preflight timeout does not bound name resolution": r"does not bound.{0,60}(DNS|name resolution)",
    }
    for label, pattern in required.items():
        assert re.search(pattern, text, flags), label

    # each prohibition sits in a sentence that forbids it, not one that advises it
    setx_paragraphs = [p for p in _paragraphs(text) if "setx" in p]
    assert setx_paragraphs and all(re.search(r"do not|never|not\b", p, re.I) for p in setx_paragraphs)
    system_paragraphs = [p for p in _paragraphs(text) if "SYSTEM" in p]
    assert system_paragraphs and all(re.search(r"do not|never|not\b", p, re.I) for p in system_paragraphs)

    # nothing in any command block of either document does what the guide forbids
    for path in (GUIDE, RUNBOOK):
        for info, body in _fenced_blocks(_read(path)):
            for line in body.splitlines():
                assert not re.search(r"\bsetx\b", line), line
                assert "service_role" not in line, line
                if "--allow-placeholder" in line:
                    assert "--dry-run" in line or re.search(r"\bprobe\b", line), line
                if "psse_run_hourly.py" in line and re.search(r"\brun\b", line) and "--dry-run" not in line:
                    assert "--allow-placeholder" not in line, line
    # the claim that nothing has been shown on the laptop is not worded as a fact
    for phrase in ("verified on the laptop", "tested on the laptop", "confirmed on the laptop"):
        assert phrase not in text.lower() and phrase not in _read(RUNBOOK).lower(), phrase


# --------------------------------------------------------------------------- secrets and identifiers


def _documents():
    return {"guide": _read(GUIDE), "runbook": _read(RUNBOOK)}


def test_docs_hold_no_secret_identifier_or_real_path():
    assert secret_scan_test._scan([GUIDE, RUNBOOK]) == []
    for name, text in _documents().items():
        # integers of five or six digits are limits and ranges only, never a bus number
        quoted = set(re.findall(r"(?<![\w.])\d{5,6}\b", text))
        assert quoted - ALLOWED_FIVE_OR_SIX_DIGITS == set(), (name, quoted - ALLOWED_FIVE_OR_SIX_DIGITS)
        assert re.search(r"\b\d{3,6}-\d{3,6}-\w{1,2}\b", text) is None, name  # a branch key
        # no literal user-profile path (a placeholder such as <user> is fine)
        assert re.search(r"(?i)[a-z]:\\users\\(?!<)", text) is None, name
        assert re.search(r"(?i)[a-z]:\\documents and settings", text) is None, name
        assert re.search(r"(?:^|[\s`(\"'])/(?:Users|home)/[A-Za-z]", text) is None, name
        # no host, address or project-reference shape
        assert re.search(r"\.supabase\.(co|com|net|io)\b", text) is None, name
        assert re.search(r"pooler\.[a-z0-9-]+\.", text) is None, name
        assert re.search(r"\baws-[0-9]-[a-z0-9-]+", text) is None, name
        assert re.search(r"\b[a-z]{20}\b", text) is None, name  # a project reference is 20 lowercase letters
        assert re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) is None, name  # an IPv4 address
        # no 32 or more hex digits (a hash or key)
        assert re.search(r"\b[0-9a-fA-F]{32,}\b", text) is None, name
        # links go only to the repository, PyPI and Microsoft's documentation
        for url in re.findall(r"https?://[^\s)>`\"']+", text):
            assert url.startswith(ALLOWED_URL_PREFIXES), (name, url)
        # a database URL is shown only with a placeholder host and password
        for url in re.findall(r"postgres(?:ql)?://\S+", text):
            assert re.search(r"@<[a-z-]+>", url), (name, "a database URL without a placeholder host")
        # no case, raw or dynamics file name (a bare extension such as `.sav` is fine)
        assert re.search(r"\b[\w-]+\.(?:sav|raw|dyr)\b", text, re.I) is None, name


# --------------------------------------------------------------------------- the questions


def test_questions_section_lists_the_open_questions():
    section = _section(_read(GUIDE), QUESTIONS_HEADING)
    items = re.findall(r"^(\d+)\. (.+)$", section, re.M)
    numbers = [int(number) for number, _ in items]
    assert len(numbers) == 12
    assert numbers == list(range(1, 13))
    for number, text in items:
        assert re.search(r"teammate|owner|user|Power Systems", text), number  # who answers
        assert "Meanwhile" in text, number  # the default the guide assumes meanwhile
        assert len(text) > 60, number
    for needle in ("Phase 6", "licence", "IEEE 39-bus", "eight", "psse_study_definitions.md",
                   "dlr_psse_writer", "powercfg /a", "credcheck --write-proof", "exit code 5", "BitLocker"):
        assert needle in section, needle
    # none is answered here: the section says so
    assert "none is answered" in section.lower() or "none of these is answered" in section.lower()


def test_phase2_note_env_names_match_launcher_keys():
    note = _read(STUDY_NOTE)
    sentence = [line for line in note.splitlines() if "environment variables" in line and "PSSE_CASE_PATH" in line]
    assert len(sentence) == 1, "the note's sentence about the environment variables changed"
    assert "PSSE_MAPPING_PATH" in sentence[0]
    names = [key.name for key in launcher.CONFIG_KEYS]
    assert "PSSE_CASE_PATH" in names and "PSSE_MAPPING_PATH" in names
    # the guide calls that sentence superseded by the configuration file, in one paragraph
    section = _section(_read(GUIDE), "## Configuration file")
    superseding = [p for p in _paragraphs(section)
                   if "PSSE_CASE_PATH" in p and "PSSE_MAPPING_PATH" in p and "superseded" in p]
    assert len(superseding) == 1
    assert "psse_study_definitions.md" in superseding[0] and "configuration file" in superseding[0]
    assert "environment variable" in superseding[0]


# --------------------------------------------------------------------------- the UNVERIFIED tags


# A tag is `[UNVERIFIED until step N]` (written in backticks in the documents) followed by its claim id in
# parentheses, for example `[UNVERIFIED until step 2]` (U05).
_TAG = re.compile(r"\[UNVERIFIED until step (\d+)\]`?(?: \((U\d+)\))?")
_ANY_TAG = re.compile(r"\[UNVERIFIED until step ([^\]]*)\]")
MIN_GUIDE_TAGS = 12
MIN_REGISTER_ROWS = 27
RUN_ID_FOR_SQL = "psse-20261029T101500Z-0000abcd"  # a syntactically valid run id of the DDL's pattern


def _step_numbers(runbook):
    return [int(number) for number in re.findall(r"^### Step (\d+): ", runbook, re.M)]


def _register_rows(runbook):
    """{claim id: (step, evidence)} of the runbook's UNVERIFIED register (one row per distinct claim)."""
    section = _section(runbook, "## UNVERIFIED register")
    header, rows = _table(section, "Claim")
    assert header == ["Claim", "Tag step", "Evidence that clears it"]
    found = {}
    for cells in rows:
        match = re.match(r"(U\d+) \S", cells[0])
        assert match is not None, "a register row without a claim id: %r" % cells[0]
        assert match.group(1) not in found, "the claim id %s is used twice" % match.group(1)
        assert re.fullmatch(r"\d+", cells[1]), cells
        assert cells[2], cells[0]
        found[match.group(1)] = (int(cells[1]), cells[2])
    return found


def test_unverified_tags_cite_existing_runbook_steps():
    guide, runbook = _read(GUIDE), _read(RUNBOOK)
    steps = _step_numbers(runbook)
    assert steps == list(range(11))  # "### Step 0:" to "### Step 10:", once each, in order
    register = _register_rows(runbook)
    assert len(register) >= MIN_REGISTER_ROWS
    for claim_id, (step, evidence) in register.items():
        assert step in steps, (claim_id, step)
        assert "[UNVERIFIED" not in evidence, claim_id  # the register holds claims, it does not tag itself

    outside_register = runbook.replace(_section(runbook, "## UNVERIFIED register"), "")
    cited = set()
    for name, text in (("guide", guide), ("runbook", outside_register)):
        # one tag format only: a bracket that starts like a tag is a well-formed one or the literal N
        for body in _ANY_TAG.findall(text):
            assert re.fullmatch(r"\d+|N", body), (name, "malformed tag: step %s" % body)
        for match in _TAG.finditer(text):
            step, claim_id = int(match.group(1)), match.group(2)
            assert step in steps, (name, "a tag names step %d, which has no heading" % step)
            assert claim_id is not None, (name, "a tag without its claim id near: %s" % text[match.start() - 40:match.end()])
            assert claim_id in register, (name, claim_id, "is not in the register")
            assert register[claim_id][0] == step, (name, claim_id, "the register says step %d" % register[claim_id][0])
            cited.add(claim_id)
    assert len(_TAG.findall(guide)) >= MIN_GUIDE_TAGS
    assert set(register) - cited == set(), "register rows no sentence cites: %s" % sorted(set(register) - cited)


def _runbook_step_text(runbook, number):
    """The text of one runbook step: from its `### Step N:` heading to the next step heading."""
    start = runbook.index("### Step %d: " % number)
    end = runbook.find("\n### Step ", start + 5)
    return runbook[start:end if end != -1 else len(runbook)]


def test_config_example_blocks_name_only_known_keys_and_the_env_module():
    """Plan 03-09: every KEY=VALUE line of a `text` block names a launcher key; the two examples hold PSSE_ENV_MODULE as a placeholder."""
    known = set(key.name for key in launcher.CONFIG_KEYS)
    examples = {}
    for name, path in (("guide", GUIDE), ("runbook", RUNBOOK)):
        for info, body in _fenced_blocks(_read(path)):
            if info != "text":
                continue
            for line in body.splitlines():
                match = re.match(r"([A-Z][A-Z0-9_]*)=(.*)$", line)
                if match:
                    assert match.group(1) in known, (name, match.group(1))
            examples[(name, "SUPABASE_PSSE_DB_URL" in body, "PSSE_CASE_PATH" in body)] = body
    guide_example = [body for (name, has_url, _case), body in examples.items() if name == "guide" and has_url]
    runbook_example = [body for (name, _url, has_case), body in examples.items() if name == "runbook" and has_case]
    assert len(guide_example) == 1 and len(runbook_example) == 1
    for body in guide_example + runbook_example:
        lines = [line for line in body.splitlines() if line.startswith("PSSE_ENV_MODULE=")]
        assert len(lines) == 1, body
        assert re.fullmatch(r"PSSE_ENV_MODULE=<[^<>]+>", lines[0]), lines[0]  # a placeholder, never a real name


def test_env_module_claims_are_registered_and_the_stale_36x_claim_is_gone():
    """Plan 03-09: U33 and U34 are registered, U01 and U07 keep their steps, the 36.x/3.11 claim is gone, the key is explained."""
    guide, runbook = _read(GUIDE), _read(RUNBOOK)
    register = _register_rows(runbook)
    assert register["U33"][0] == 2 and register["U34"][0] == 0
    assert register["U01"][0] == 0 and register["U07"][0] == 2
    for name, text in (("guide", guide), ("runbook", runbook)):
        assert re.search(r"36\.x[^|\n]{0,40}Python 3\.11", text) is None, name
        assert "PSSE_ENV_MODULE" in text and "Python 3.13 and 3.14" in text, name
    assert "PSSE_ENV_MODULE" in _section(guide, "## Troubleshooting")
    step2 = _runbook_step_text(runbook, 2)
    assert "PSSE_ENV_MODULE" in step2 and "(U33)" in step2
    assert "PSSE_ENV_MODULE" in _runbook_step_text(runbook, 1)


# --------------------------------------------------------------------------- the command and SQL blocks


def _placeholders():
    return {
        "PYTHON": sys.executable, "REPO": _ROOT, "CONFIG": os.path.join(_ROOT, "job.env"),
        "SITE": os.path.join(_ROOT, "site"), "WORKDIR": _ROOT, "OUT": os.path.join(_ROOT, "task.xml"),
    }


def test_every_command_block_parses_with_the_real_parser(tmp_path):
    import psse_render_task

    values = _placeholders()
    seen = {}
    for path in (GUIDE, RUNBOOK):
        for name, lines in command_blocks(path):
            if name == MANUAL:
                continue
            assert lines, (path, name)
            for line in lines:
                if name in LAUNCHER_NAMES:
                    parsed = launcher.build_parser().parse_args(launcher_arguments(line, values))
                    assert SHAPES[name](parsed), "%s does not parse to its own shape: %s" % (name, line)
                else:
                    assert name in RENDER_NAMES
                    parsed = psse_render_task._parser().parse_args(render_arguments(line, values))
                    assert RENDER_SHAPES[name](parsed), "%s does not parse to its own shape: %s" % (name, line)
                seen[name] = seen.get(name, 0) + 1
    assert set(seen) == set(COMMAND_NAMES)  # every documented command name appears somewhere

    # a flag the parser does not know, and a command that is not the launcher's, are both caught
    bad = '<PYTHON> -X utf8 "<REPO>\\backend\\psse_run_hourly.py" probe --config "<CONFIG>" --write-chek'
    with pytest.raises(Exception):
        launcher.build_parser().parse_args(launcher_arguments(bad, values))

    # a tag with a name outside the known set, or one not directly above a fence, fails
    typo = tmp_path / "typo.md"
    typo.write_text("<!-- cmd: dry_run_smok -->\n```\nx\n```\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        command_blocks(str(typo))
    detached = tmp_path / "detached.md"
    detached.write_text("<!-- cmd: selftest -->\n\n```\nx\n```\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        command_blocks(str(detached))


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    """Admin URL of a database that already carries the Phase 4 migrations and the reference DDL."""
    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_schema(admin_url)
        yield admin_url


@pytest.fixture
def clean_pg(pg):
    """The same database with the four result tables empty."""
    pg_helper.reset(pg)
    return pg


_WRITING_WORDS = re.compile(r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke|copy)\b", re.I)


def test_every_sql_block_runs_on_local_postgres(clean_pg):
    import psycopg

    counts = {}
    conn = psycopg.connect(pg_helper.role_url(clean_pg, WRITER_ROLE), autocommit=True)
    try:
        for name, path in (("guide", GUIDE), ("runbook", RUNBOOK)):
            for info, body in _fenced_blocks(_read(path)):
                if info != "sql":
                    continue
                sql = body.replace("<run_id>", RUN_ID_FOR_SQL)
                assert re.match(r"\s*(select|with)\b", sql, re.I), (name, "a statement that is not a read: " + body[:40])
                assert _WRITING_WORDS.search(sql) is None, (name, body)
                assert "<" not in sql and "%" not in sql, (name, "an unreplaced placeholder or a percent sign: " + body)
                conn.execute(sql).fetchall()  # runs as the job's own role, on empty tables, without an error
                counts[name] = counts.get(name, 0) + 1
    finally:
        conn.close()
    assert counts.get("runbook", 0) >= 4 and counts.get("guide", 0) >= 3, counts


def test_runbook_steps_table_covers_the_requirements():
    runbook = _read(RUNBOOK)
    header, rows = _table(_section(runbook, "## Steps"), "Step")
    assert header == ["Step", "What", "Needs", "Closes", "Mac-proven", "Laptop-proven"]
    assert [cells[0] for cells in rows] == [str(number) for number in range(11)]
    for cells in rows:
        assert len(cells) == 6 and all(cells), cells  # no empty Mac-proven or Laptop-proven cell
    closes = dict((int(cells[0]), cells[3]) for cells in rows)
    closing = {"SCH-01": [6, 10], "DBX-02": [8], "TST-02": [9], "SCH-02": [10]}
    for requirement, steps in closing.items():
        assert [step for step, cell in closes.items() if requirement in cell] == steps, requirement
    assert "confirms SCH-01" in closes[10] and "DOC-01" in closes[10]
    # step 9 and step 10 each begin with the human decision of plan 03-08
    details = _section(runbook, "## Step details")
    step9 = details[details.index("### Step 9:"):details.index("### Step 10:")]
    step10 = details[details.index("### Step 10:"):]
    assert "decision 1" in step9 and "exactly one" in step9
    assert "decision 2" in step10 and "Disable-ScheduledTask" in step10 and "Unregister-ScheduledTask" in step10
    assert "IgnoreNew" in step10 and "lock" in step10
    # every step section says what it needs and when to stop
    for number in range(11):
        start = details.index("### Step %d:" % number)
        end = details.find("\n### Step ", start + 5)
        section = details[start:end if end != -1 else len(details)]
        assert "**Needs:**" in section and "**Stop if:**" in section, number
        if number >= 2:
            assert "**Should show:**" in section, number


def test_doc_links_resolve():
    checked = 0
    for path in (GUIDE, RUNBOOK):
        for target in re.findall(r"\]\(([^)\s]+)\)", _read(path)):
            if re.match(r"[a-z]+:", target) or target.startswith("#"):
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target.split("#", 1)[0]))
            assert os.path.isfile(resolved), "%s: link %s does not resolve" % (path, target)
            checked += 1
    assert checked >= 10
    assert "](psse_laptop_setup.md)" in _read(RUNBOOK)
    assert "](psse_laptop_runbook.md)" in _read(GUIDE)
    assert "](../schema/psse_results_v1_checks.sql)" in _read(RUNBOOK)
    assert "](../ops/psse_hourly_task.xml)" in _read(GUIDE)


# --------------------------------------------------------------------------- the read-back statement


def _newest_per_slot_statement():
    """The runbook's newest-complete-run-per-hour statement, found by its heading and used unchanged."""
    runbook = _read(RUNBOOK)
    start = runbook.index("#### Read back the newest complete run per hour")
    match = re.search(r"```sql\n(.*?)\n```", runbook[start:], re.S)
    assert match is not None
    return match.group(1)


def test_read_back_statement_returns_the_newest_complete_run_per_slot(clean_pg):
    """
    Research assumption A16 on local Postgres, as the writer role, with run rows seeded in three slots.
    Slot A (10:00): a failed run started latest (10:50), an ok run started at :40 and a fallback run
    started at :10 - the ok run started LATER than the fallback, so the ok run is the newest complete
    run. Slot B (09:00): two complete runs with equal started_at (09:15) and different run ids; the
    fallback run holds the larger id, so the rule is the run id and not the outcome. Slot C (08:00):
    one failed run only. Expected: A's ok run and then B's larger id, newest slot first, no row for C,
    and the planted failed run never returned.
    """
    import psycopg
    from psycopg.rows import dict_row

    utc = datetime.timezone.utc
    day = datetime.datetime(2026, 10, 20, tzinfo=utc)

    def at(hour, minute):
        return day + datetime.timedelta(hours=hour, minutes=minute)

    failed_a = pg_helper.make_run_id(1, at(10, 50))
    ok_a = pg_helper.make_run_id(2, at(10, 40))
    fallback_a = pg_helper.make_run_id(3, at(10, 10))
    ok_b = pg_helper.make_run_id(0x10, at(9, 15))
    fallback_b = pg_helper.make_run_id(0x20, at(9, 15))
    failed_c = pg_helper.make_run_id(5, at(8, 20))
    assert ok_b < fallback_b  # the larger id belongs to the fallback run

    runs = [
        pg_helper.failed_run_row(failed_a, at(10, 50)),
        pg_helper.valid_run_rows(ok_a, at(10, 40), outcome="ok")["psse_run"][0],
        pg_helper.valid_run_rows(fallback_a, at(10, 10), outcome="fallback")["psse_run"][0],
        pg_helper.valid_run_rows(ok_b, at(9, 15), outcome="ok")["psse_run"][0],
        pg_helper.valid_run_rows(fallback_b, at(9, 15), outcome="fallback")["psse_run"][0],
        pg_helper.failed_run_row(failed_c, at(8, 20)),
    ]
    with psycopg.connect(clean_pg, autocommit=True) as admin:
        pg_helper.insert_rows(admin, "psse_run", runs)

    statement = _newest_per_slot_statement()
    with psycopg.connect(pg_helper.role_url(clean_pg, WRITER_ROLE), autocommit=True, row_factory=dict_row) as conn:
        rows = conn.execute(statement).fetchall()
    assert [row["run_id"] for row in rows] == [ok_a, fallback_b]
    assert [row["slot_time"] for row in rows] == [at(10, 0), at(9, 0)]  # newest slot first
    assert [row["outcome"] for row in rows] == ["ok", "fallback"]
    assert rows[0]["started_at"] == at(10, 40)
    returned = {row["run_id"] for row in rows}
    assert failed_a not in returned and failed_c not in returned and fallback_a not in returned
    assert at(8, 0) not in [row["slot_time"] for row in rows]  # slot C has no complete run, so no row
