"""
SCH-01 proofs of the Task Scheduler template docs/data-science/ops/psse_hourly_task.xml and of its
renderer (pss-e-integration Phase 3, plan 03-05), text level only: the template is parsed as XML,
held to its stated policy, filled from tmp paths, and the arguments it would give the launcher are
parsed by the launcher's own argument parser.

Honest scope: nothing was registered with Windows Task Scheduler on any machine and Microsoft's
schema was not run against the file, so every real-scheduler behaviour is UNVERIFIED until runbook
step 6 (plan 03-07): that Task Scheduler accepts this XML, that a Repetition with an Interval and
no Duration repeats indefinitely, that a quoted Command with spaces works, that UTF-8 import
through Register-ScheduledTask works, that a standard user can register it, that WakeToRun wakes
the laptop and that the exit code reaches LastTaskResult.

Every path used here is a pytest tmp path or a placeholder; test strings that look like
credentials are assembled from pieces because secret_scan_test scans tracked files.
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from psse_job import launcher, taskxml  # noqa: E402

_REPO_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
TEMPLATE = os.path.join(_REPO_ROOT, "docs", "data-science", "ops", "psse_hourly_task.xml")
NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def _ns(name):
    """The namespaced tag of a Task Scheduler element."""
    return "{%s}%s" % (NS, name)


def _template_text():
    with open(TEMPLATE, "rb") as handle:
        return handle.read().decode("utf-8")


def _split_arguments(text):
    """Windows-style splitting: double quotes group a token and are dropped, spaces separate tokens."""
    tokens = []
    current = []
    started = False
    quoted = False
    for char in text:
        if char == '"':
            quoted = not quoted
            started = True
        elif char == " " and not quoted:
            if started:
                tokens.append("".join(current))
                current = []
                started = False
        else:
            current.append(char)
            started = True
    assert not quoted, "unbalanced double quote in the arguments"
    if started:
        tokens.append("".join(current))
    return tokens


def test_tracer_render_parses_and_arguments_reach_the_launcher_parser(tmp_path):
    """The template fills from tmp paths into well-formed XML whose Arguments the launcher's own parser reads as `run --config FILE`."""
    raw = _template_text()
    root_template = ET.fromstring(raw)
    assert root_template.tag == _ns("Task")
    found = set(re.findall(r"@@([A-Z_]+)@@", raw))
    assert found == set(taskxml.PLACEHOLDERS)

    entry = tmp_path / "entry.py"
    entry.write_text("print('entry')\n", encoding="utf-8")
    config = tmp_path / "job.conf"
    config.write_text("# placeholder config\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    start = "2026-11-02T10:15:00"

    text = taskxml.render(raw, sys.executable, str(entry), str(config), str(work), start)

    assert "@@" not in text
    root = ET.fromstring(text)
    exec_node = root.find(_ns("Actions") + "/" + _ns("Exec"))
    command = exec_node.find(_ns("Command")).text
    expected_command = '"%s"' % sys.executable if " " in sys.executable else sys.executable
    assert command == expected_command
    assert exec_node.find(_ns("WorkingDirectory")).text == str(work)
    assert root.find(_ns("Triggers") + "/" + _ns("TimeTrigger") + "/" + _ns("StartBoundary")).text == start

    arguments = exec_node.find(_ns("Arguments")).text
    # The quoting is part of the contract (a path with a space must stay one token), so the raw text is pinned too.
    assert arguments == '-X utf8 "%s" run --config "%s"' % (entry, config)
    tokens = _split_arguments(arguments)
    assert tokens[:3] == ["-X", "utf8", str(entry)]
    parsed = launcher.build_parser().parse_args(tokens[3:])
    assert parsed.mode == "run"
    assert parsed.config == str(config)
    assert parsed.dry_run is False
    assert parsed.allow_placeholder is False
