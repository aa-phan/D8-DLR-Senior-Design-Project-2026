"""
The study-definitions note stays equal to the code (pss-e-integration Phase 2, plan 02-07).

`docs/data-science/decisions/psse_study_definitions.md` states every definition the PSS/E study
implements, what the fake psspy proves and does not, the assumptions behind each default and
the open questions for the user and Power Systems. These tests read the note and compare it
with `psse_job`: the section list, every study setting with its default, the worked rating
conversion, the failure stages, the questions, the honest-scope sentences and the rule that no
real identifier is written in it. They are offline: no database, no network, no psspy.

Follows backend/tests/psse_schema_doc_test.py's conventions (module-level imports, plain
asserts, no test classes).
"""

import json
import os
import re
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from psse_job import constants, settings, units  # noqa: E402

DOC_PATH = os.path.join(
    _ROOT, "docs", "data-science", "decisions", "psse_study_definitions.md")
EXAMPLE_LINK = "../schema/psse_mapping_example.json"

REQUIRED_HEADINGS = (
    "## Scope and where the code lives",
    "## Rating conversion (IN-03)",
    "## Convergence (STU-01)",
    "## N-1 screening (STU-02)",
    "## Voltage-stability margin (STU-03)",
    "## Dispatched capacity (STU-04)",
    "## Failure stages",
    "## Configuration",
    "## Private inputs",
    "## What the fake proves and what it does not",
    "## Phase 3 confirmations",
    "## Assumptions",
    "## Representability notes (no DDL change)",
    "## Questions for the user / Power Systems",
)

STUDY_STAGES = (
    "load_case", "mapping", "apply_ratings", "load_flow", "contingency", "voltage_margin",
    "dispatch",
)

# Whole numbers of five or six digits the note may quote, each a range bound or a cap and none a
# bus number of Power Systems' case: 10000 is the transfer.max_mw ceiling; 65536 is the mapping
# file size cap in bytes; 90000 and 99999 are the bounds of the placeholder bus range; 999999 is
# the largest bus number the mapping accepts. A number added here needs a comment saying why.
ALLOWED_FIVE_OR_SIX_DIGITS = frozenset(["10000", "65536", "90000", "99999", "999999"])


def _read():
    with open(DOC_PATH, encoding="utf-8") as handle:
        return handle.read()


def _section(text, heading):
    """The text of one `## ` section: from its heading line to the next `## ` heading."""
    start = text.index("\n" + heading + "\n") + 1
    end = text.find("\n## ", start + len(heading))
    return text[start:end if end != -1 else len(text)]


def test_doc_has_required_sections():
    text = _read()
    lines = text.splitlines()
    positions = []
    for heading in REQUIRED_HEADINGS:
        assert lines.count(heading) == 1, heading
        positions.append(lines.index(heading))
    assert positions == sorted(positions)
    last = _section(text, REQUIRED_HEADINGS[-1])
    assert text.rstrip().endswith(last.rstrip())  # the questions are the last section


def test_doc_configuration_table_lists_every_setting_with_its_default():
    section = _section(_read(), "## Configuration")
    lines = section.splitlines()
    for field in settings.Settings._fields:
        default = "`%s`" % json.dumps(getattr(settings.DEFAULT_SETTINGS, field))
        matching = [line for line in lines if "`%s`" % field in line and default in line]
        assert matching, "%s with default %s" % (field, default)
    for name in ("PSSE_CASE_PATH", "PSSE_MAPPING_PATH"):
        assert name in section


def test_doc_conversion_numbers_match_units():
    section = _section(_read(), "## Rating conversion (IN-03)")
    assert "sqrt(3) x kV x amps per conductor x subconductors / 1000" in section
    for city in constants.CITIES:
        mva = units.circuit_mva(
            constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city],
            constants.SUBCONDUCTORS_PER_PHASE[city], 345.0)
        lines = [line for line in section.splitlines() if city in line]
        assert any("%.1f" % mva in line for line in lines), (city, "%.1f" % mva)
    for expected in ("2181.1", "1792.7", "2240.8", "788.8"):
        assert expected in section


def test_doc_failure_stage_table_names_every_study_stage():
    section = _section(_read(), "## Failure stages")
    for stage in STUDY_STAGES:
        assert stage in constants.FAILED_STAGES
        assert "`%s`" % stage in section, stage


def test_doc_questions_section_has_five_to_eight_items():
    section = _section(_read(), "## Questions for the user / Power Systems")
    numbers = [int(match.group(1)) for match in re.finditer(r"^(\d+)\. ", section, re.M)]
    assert 5 <= len(numbers) <= 8
    assert numbers == list(range(1, len(numbers) + 1))


def test_doc_links_placeholder_and_has_no_identifiers():
    text = _read()
    assert "(%s)" % EXAMPLE_LINK in text
    assert os.path.isfile(os.path.normpath(os.path.join(os.path.dirname(DOC_PATH), EXAMPLE_LINK)))
    quoted = set(re.findall(r"(?<![\w.])\d{5,6}\b", text))
    assert quoted - ALLOWED_FIVE_OR_SIX_DIGITS == set()
    assert re.search(r"\b\d{3,6}-\d{3,6}-\w{1,2}\b", text) is None
    assert "90000-99999" in text


def test_doc_states_honest_scope():
    text = _read()
    scope = _section(text, "## What the fake proves and what it does not")
    assert "does not prove" in scope
    assert "Phase 3" in scope
    margin = _section(text, "## Voltage-stability margin (STU-03)")
    assert "pv_curve" in margin
    assert "not a PSS/E PV-curve analysis" in margin
    assert "starting cap" in margin
    assert "never a limit" in margin
    n1 = _section(text, "## N-1 screening (STU-02)")
    assert "full N-1" in n1
