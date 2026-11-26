"""
OPS-01, OPS-02, OPS-03 agreement of the hourly runbook, the workflow and the runner
(pandapower-solver Phase 5, plan 05-06; decisions D-07, D-11).

Text checks only. `docs/data-science/decisions/pandapower_hourly_runbook.md`,
`.github/workflows/pandapower_hourly.yml` and `pandapower_job.hourly` each name the secrets, the live
variable, the commands and their flags, the temporary-folder prefix and the exit codes; a rename in one
that is not followed in the others fails here, which is the failure the older runbook of the other
hourly workflow already shows (a stale table). Files are opened in text mode and never pinned by their
bytes (the checkout has core.autocrlf true). Nothing here reads `data/private`.
"""

import os
import re
import sys

import pytest

pandapower = pytest.importorskip("pandapower")

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_REPO = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from psse_job import constants  # noqa: E402
from pandapower_job import hourly  # noqa: E402

_B64_NAME = re.compile(r"PANDAPOWER_[A-Z]+_B64")
_COMMAND = re.compile(r"pandapower_hourly\.py ([A-Za-z][A-Za-z-]*)")
_FLAG = re.compile(r"(?<![\w-])--[a-z][a-z-]*")
_SECTION = re.compile(r"^## ([0-9]+)\. (.*)$", re.M)

# credential-shaped text (each is assembled from pieces in the teeth below, never written whole)
_CREDENTIAL_SHAPES = {
    "url with a password": re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@"),
    "supabase secret key": re.compile(r"sb_secret_"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    "github token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "64 hex characters": re.compile(r"\b[0-9a-fA-F]{64}\b"),
    "long base64 run": re.compile(r"[A-Za-z0-9+/]{100,}={0,2}"),
}


def _read(*parts):
    with open(os.path.join(_REPO, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


def _runbook():
    return _read("docs", "data-science", "decisions", "pandapower_hourly_runbook.md")


def _workflow():
    return _read(".github", "workflows", "pandapower_hourly.yml")


def _section(text, number):
    """The text of section `number` (heading to the next heading of the same level)."""
    matches = list(_SECTION.finditer(text))
    for index, match in enumerate(matches):
        if int(match.group(1)) == number:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return text[match.start():end]
    raise AssertionError("section %d is missing" % number)


def test_runbook_names_every_secret_the_workflow_and_runner_use():
    expected = set(name for _word, name, _file, _cap in hourly.SECRET_ENV)
    assert len(expected) == 4
    assert all(_B64_NAME.fullmatch(name) for name in expected)
    runbook = _runbook()
    workflow = _workflow()

    assert set(_B64_NAME.findall(runbook)) == expected
    assert set(_B64_NAME.findall(workflow)) == expected

    # the three settings of the read side and the writer, and the live variable
    others = set(hourly.READ_ENV) | {constants.ENV_PSSE_DB_URL, hourly.LIVE_VARIABLE}
    assert others == {"SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_PSSE_DB_URL",
                      "PANDAPOWER_LIVE"}
    for name in others:
        assert name in runbook, name
        assert name in workflow, name

    # the seven secrets are all explained in section 3, in the production environment
    section = _section(runbook, 3)
    for name in sorted(expected | set(hourly.READ_ENV) | {constants.ENV_PSSE_DB_URL}):
        assert "`%s`" % name in section, name
    assert "production" in section


def test_runbook_commands_and_flags_match_the_runner():
    runbook = _runbook()
    seen = set()
    for line in runbook.splitlines():
        for match in _COMMAND.finditer(line):
            word = match.group(1)
            assert word in hourly.COMMAND_FLAGS, (word, line)
            seen.add(word)
            for flag in _FLAG.findall(line[match.end():]):
                assert flag in hourly.COMMAND_FLAGS[word], (word, flag)
    assert seen == set(hourly.COMMAND_FLAGS)

    # the flags the runbook shows on their own lines are flags of some command
    known = set(flag for flags in hourly.COMMAND_FLAGS.values() for flag in flags)
    for flag in ("--since", "--check-dir", "--mapping", "--log"):
        assert flag in known
        assert flag in runbook


def test_workflow_run_lines_and_removal_step_match_the_runner():
    workflow = _workflow()
    found = re.findall(
        r"^\s*run:\s*python -I -B backend/pandapower_hourly\.py ([A-Za-z][A-Za-z-]*)(.*)$",
        workflow, flags=re.M)
    assert [command for command, _rest in found] == ["run", "soak"]
    for command, rest in found:
        assert command in hourly.COMMAND_FLAGS
        # neither workflow command takes a flag the runner does not know
        assert all(flag in hourly.COMMAND_FLAGS[command] for flag in _FLAG.findall(rest))

    removal = re.search(r"^\s*run:\s*rm -rf (.*)$", workflow, flags=re.M)
    assert removal is not None
    assert "$RUNNER_TEMP" in removal.group(1)
    assert hourly.TEMP_PREFIX in removal.group(1)
    assert hourly.TEMP_PREFIX == "pandapower_hourly_"


def test_runbook_cron_settings():
    runbook = _runbook()
    section = _section(runbook, 5)
    assert "`20 * * * *`" in section
    assert "actions/workflows/pandapower_hourly.yml/dispatches" in section
    assert '{"ref":"main"}' in section
    assert "2022-11-28" in section
    assert "25 failures in a row" in section
    assert "HTTP 204" in section
    assert "fine-grained" in section
    assert "workflow_dispatch" in _workflow()


def test_runbook_exit_codes_match_the_runner():
    constants_by_name = dict((name, value) for name, value in vars(hourly).items()
                             if name.startswith("EXIT_") and isinstance(value, int))
    assert sorted(constants_by_name.values()) == [0, 1, 2, 3, 5, 6]
    section = _section(_runbook(), 6)
    rows = set(int(code) for code in re.findall(r"^\| ([0-9]+) \|", section, flags=re.M))
    assert rows == set(constants_by_name.values())
    # the lines the runbook explains are lines the runner can print
    for line in ("mode: dry", "mode: live", "inputs: ok", "ratings: city_rating=1 static=1",
                 "study: ok", "outcome: ok", "rows: run=1 dispatch=1 margin=1 contingency=1",
                 "dry run: nothing was written to the database", "run status: written",
                 "gap check: solver pandapower runs=1 gaps=0",
                 "soak: consecutive_slots=1 of 24 fallback_slots=0", "soak: pass", "soak: not yet"):
        assert any(pattern.match(line) for pattern in hourly.HOURLY_LINE_PATTERNS), line
    assert len(_SECTION.findall(_runbook())) == 14


def test_runbook_holds_no_credential_shaped_value():
    text = _runbook()
    for name, shape in _CREDENTIAL_SHAPES.items():
        assert shape.search(text) is None, name

    # teeth: each shape fires on a sample assembled from pieces
    samples = {
        "url with a password": "postgres" + "ql://" + "user" + ":" + "pw" + "@" + "host",
        "supabase secret key": "sb_" + "secret_" + "abc",
        "jwt": "ey" + "J" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12,
        "github token": "gh" + "p_" + "A" * 24,
        "64 hex characters": "ab" * 32,
        "long base64 run": "QUJD" * 30,
    }
    assert set(samples) == set(_CREDENTIAL_SHAPES)
    for name, sample in samples.items():
        assert _CREDENTIAL_SHAPES[name].search("x " + sample + " y") is not None, name
