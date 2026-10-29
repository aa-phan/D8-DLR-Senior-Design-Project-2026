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

import secret_scan_test  # noqa: E402
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


# ---------------------------------------------------------------------------
# The template's policy, as functions over text so planted variants prove each gate fires.
# ---------------------------------------------------------------------------

_KNOWN_TOKEN = re.compile("@@(?:%s)@@" % "|".join(taskxml.PLACEHOLDERS))
_DRIVE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")
_PROFILE_PATH = re.compile(r"(?i)[\\/](?:users|home)[\\/]|%(?:userprofile|appdata|localappdata|homepath|username)%")
_NETWORK_PATH = re.compile(r"(?<!\\)\\\\[A-Za-z0-9_.-]")
_DURATION = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")

# Settings pinned to an exact value (ExecutionTimeLimit is a range rule, see _settings_problems).
_EXPECTED_SETTINGS = {
    "MultipleInstancesPolicy": "IgnoreNew",
    "DisallowStartIfOnBatteries": "false",
    "StopIfGoingOnBatteries": "false",
    "AllowHardTerminate": "true",
    "StartWhenAvailable": "false",
    "RunOnlyIfNetworkAvailable": "false",
    "WakeToRun": "true",
    "Enabled": "true",
    "Hidden": "false",
}
# Elements that must appear nowhere in the template (anywhere in the tree).
_BANNED_ELEMENTS = {
    "RestartOnFailure": "RestartOnFailure element present (a restart would duplicate a slot)",
    "UserId": "UserId element present (the task must run for whoever registers it)",
    "GroupId": "GroupId element present",
    "Password": "Password element present (no stored password)",
    "Duration": "Repetition Duration present (the repetition must have no end)",
    "StopAtDurationEnd": "StopAtDurationEnd present (the repetition must have no end)",
    "EndBoundary": "EndBoundary present (the trigger must have no end)",
}


def _local(tag):
    return tag.split("}")[-1]


def _duration_seconds(text):
    """Seconds of a PTnHnMnS duration, or None when the text is not of that form."""
    match = _DURATION.match(text or "")
    if match is None or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _text_problems(text):
    """Problems found by plain text scans: encoding declaration, tokens, paths, URLs, credential shapes."""
    problems = []
    declaration = re.match(r'<\?xml[^>]*?encoding="([^"]*)"', text)
    if declaration is None or declaration.group(1).upper() != "UTF-8":
        problems.append("the encoding declaration is missing or is not UTF-8")
    if "@@" in _KNOWN_TOKEN.sub("", text):
        problems.append("a placeholder token that is not one of the four (or a stray at-sign pair)")
    body = text.replace(NS, "")
    if _DRIVE_PATH.search(body):
        problems.append("a drive-letter path")
    if _PROFILE_PATH.search(body):
        problems.append("a user-profile path")
    if _NETWORK_PATH.search(body):
        problems.append("a network path")
    if "://" in body:
        problems.append("a URL or host")
    for number, line in enumerate(text.splitlines(), start=1):
        for name in secret_scan_test._scan_line(line):
            problems.append("credential-shaped text (%s) on line %d" % (name, number))
    return problems


def _child_texts(node):
    return {_local(child.tag): (child.text or "").strip() for child in node}


def _settings_problems(root):
    """Problems found by reading the parsed task: every setting and every ban of the policy."""
    if root.tag != _ns("Task"):
        return ["the root element is not Task in the task namespace"]
    problems = []
    if root.get("version") != "1.2":
        problems.append("Task version is not 1.2")
    present = set(_local(node.tag) for node in root.iter())
    for name, message in sorted(_BANNED_ELEMENTS.items()):
        if name in present:
            problems.append(message)

    triggers = root.find(_ns("Triggers"))
    children = list(triggers) if triggers is not None else []
    if len(children) != 1 or children[0].tag != _ns("TimeTrigger"):
        problems.append("Triggers must hold exactly one TimeTrigger (found %d element(s))" % len(children))
    else:
        trigger = _child_texts(children[0])
        if trigger.get("Enabled") != "true":
            problems.append("TimeTrigger Enabled is not true")
        if trigger.get("StartBoundary") != "@@START_BOUNDARY@@":
            problems.append("StartBoundary is not the START_BOUNDARY placeholder")
        repetition = children[0].find(_ns("Repetition"))
        if repetition is None or _child_texts(repetition).get("Interval") != "PT1H":
            problems.append("Repetition Interval is not PT1H")

    principals = root.findall(_ns("Principals") + "/" + _ns("Principal"))
    if len(principals) != 1:
        problems.append("Principals must hold exactly one Principal (found %d)" % len(principals))
    else:
        principal = _child_texts(principals[0])
        if principals[0].get("id") != "Author":
            problems.append("Principal id is not Author")
        if principal.get("LogonType") != "InteractiveToken":
            problems.append("LogonType is not InteractiveToken")
        if principal.get("RunLevel") != "LeastPrivilege":
            problems.append("RunLevel is not LeastPrivilege")

    settings = root.find(_ns("Settings"))
    if settings is None:
        problems.append("Settings element missing")
    else:
        found = _child_texts(settings)
        for name, expected in sorted(_EXPECTED_SETTINGS.items()):
            if name not in found:
                problems.append("Settings: %s is missing" % name)
            elif found[name] != expected:
                problems.append("Settings: %s is %r, expected %r" % (name, found[name], expected))
        limit = _duration_seconds(found.get("ExecutionTimeLimit"))
        if limit is None or not 25 * 60 < limit < 60 * 60:
            problems.append("Settings: ExecutionTimeLimit must be a PTnHnMnS duration above 25 and below 60 minutes")
        extra = sorted(set(found) - set(_EXPECTED_SETTINGS) - set(["ExecutionTimeLimit"]) - set(_BANNED_ELEMENTS))
        for name in extra:
            problems.append("Settings: unexpected element %s" % name)

    actions = root.find(_ns("Actions"))
    execs = list(actions) if actions is not None else []
    if actions is None or actions.get("Context") != "Author" or len(execs) != 1 or execs[0].tag != _ns("Exec"):
        problems.append("Actions must hold exactly one Exec with Context Author")
    else:
        action = _child_texts(execs[0])
        wanted = {"Command": "@@PYTHON_EXE@@", "Arguments": "@@ARGUMENTS@@", "WorkingDirectory": "@@WORK_DIR@@"}
        if action != wanted:
            problems.append("Exec must hold exactly Command, Arguments and WorkingDirectory as placeholders")
    return problems


def _problems(xml_text):
    """Every policy problem of a template text (empty for the committed template)."""
    problems = _text_problems(xml_text)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return problems + ["not well-formed XML (%s)" % exc]
    return problems + _settings_problems(root)


def _credential_shapes():
    """Credential-shaped strings assembled from pieces (the scan of tracked files must not see them here)."""
    scheme = "postgres" + "ql://"
    url = (scheme + "dlr_writer." + "abcdefghijklmnop" + ":" + "Zx9" + "Qw7" + "Lk2"
           + "@aws-0-us-east-1.pooler.example.invalid:5432/postgres")
    key = "sb_" + "secret_" + "A1b2C3d4E5f6G7h8I9j0"
    return url, key


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------

def test_template_settings_are_the_researched_ones():
    """Every setting of the policy has its pinned value, read straight from the parsed template."""
    text = _template_text()
    root = ET.fromstring(text)
    settings = _child_texts(root.find(_ns("Settings")))
    assert settings == dict(_EXPECTED_SETTINGS, ExecutionTimeLimit="PT45M")
    assert _duration_seconds("PT45M") == 2700
    assert 25 * 60 < _duration_seconds(settings["ExecutionTimeLimit"]) < 60 * 60

    trigger = root.find(_ns("Triggers") + "/" + _ns("TimeTrigger"))
    assert len(list(root.find(_ns("Triggers")))) == 1
    assert _child_texts(trigger) == {"StartBoundary": "@@START_BOUNDARY@@", "Enabled": "true", "Repetition": ""}
    assert _child_texts(trigger.find(_ns("Repetition"))) == {"Interval": "PT1H"}

    principal = root.find(_ns("Principals") + "/" + _ns("Principal"))
    assert _child_texts(principal) == {"LogonType": "InteractiveToken", "RunLevel": "LeastPrivilege"}
    names = set(_local(node.tag) for node in root.iter())
    assert not names & set(_BANNED_ELEMENTS)

    execs = root.findall(_ns("Actions") + "/" + _ns("Exec"))
    assert len(execs) == 1
    assert _child_texts(execs[0]) == {
        "Command": "@@PYTHON_EXE@@", "Arguments": "@@ARGUMENTS@@", "WorkingDirectory": "@@WORK_DIR@@"}
    assert _settings_problems(root) == []


def test_template_holds_only_known_placeholders_no_secret_no_path():
    """The template holds the four placeholders and nothing else that is machine, person or secret specific."""
    text = _template_text()
    tokens = re.findall(r"@@[^@\s]*@@", text)
    assert sorted(set(tokens)) == sorted("@@%s@@" % name for name in taskxml.PLACEHOLDERS)
    assert _text_problems(text) == []
    # The comments say what the placeholders are without writing the token pairs themselves.
    assert text.count("@@") == len(tokens) * 2
    for name in taskxml.PLACEHOLDERS:
        assert "@@%s@@" % name in text


def test_template_gate_flags_planted_violations():
    """Each planted fault of the policy is named by a check; the committed template and the allowed variants pass."""
    template = _template_text()
    assert _problems(template) == []
    url, key = _credential_shapes()
    description = "<Description>DLR PSS/E hourly study job. No secrets in this file.</Description>"
    trigger_start = template.index("<TimeTrigger>")
    trigger_end = template.index("</TimeTrigger>") + len("</TimeTrigger>")
    second_trigger = template[trigger_start:trigger_end]
    before_principal = '<Principal id="Author">'
    before_settings_end = "</Settings>"
    interval = "<Interval>PT1H</Interval>"

    plants = [
        ("Parallel", ">IgnoreNew<", ">Parallel<", "MultipleInstancesPolicy"),
        ("Queue", ">IgnoreNew<", ">Queue<", "MultipleInstancesPolicy"),
        ("StopExisting", ">IgnoreNew<", ">StopExisting<", "MultipleInstancesPolicy"),
        ("RestartOnFailure", before_settings_end,
         "<RestartOnFailure><Interval>PT5M</Interval><Count>3</Count></RestartOnFailure>" + before_settings_end,
         "RestartOnFailure"),
        ("unbounded time limit", ">PT45M<", ">PT0S<", "ExecutionTimeLimit"),
        ("two hour time limit", ">PT45M<", ">PT2H<", "ExecutionTimeLimit"),
        ("61 minute time limit", ">PT45M<", ">PT61M<", "ExecutionTimeLimit"),
        ("one hour time limit", ">PT45M<", ">PT1H<", "ExecutionTimeLimit"),
        ("25 minute time limit", ">PT45M<", ">PT25M<", "ExecutionTimeLimit"),
        ("day time limit", ">PT45M<", ">P1D<", "ExecutionTimeLimit"),
        ("no start on battery", "<DisallowStartIfOnBatteries>false<", "<DisallowStartIfOnBatteries>true<",
         "DisallowStartIfOnBatteries"),
        ("stop on battery", "<StopIfGoingOnBatteries>false<", "<StopIfGoingOnBatteries>true<",
         "StopIfGoingOnBatteries"),
        ("catch-up run", "<StartWhenAvailable>false<", "<StartWhenAvailable>true<", "StartWhenAvailable"),
        ("no wake", "<WakeToRun>true<", "<WakeToRun>false<", "WakeToRun"),
        ("password logon", ">InteractiveToken<", ">Password<", "LogonType"),
        ("S4U logon", ">InteractiveToken<", ">S4U<", "LogonType"),
        ("service account logon", ">InteractiveToken<", ">ServiceAccount<", "LogonType"),
        ("highest privilege", ">LeastPrivilege<", ">HighestAvailable<", "RunLevel"),
        ("UserId element", before_principal, before_principal + "<UserId>placeholder-user</UserId>", "UserId"),
        ("Password element", before_principal, before_principal + "<Password>placeholder</Password>", "Password"),
        ("second trigger", "</Triggers>", second_trigger + "</Triggers>", "exactly one TimeTrigger"),
        ("Repetition Duration", interval, interval + "<Duration>P1D</Duration>", "Duration"),
        ("StopAtDurationEnd", interval, interval + "<StopAtDurationEnd>true</StopAtDurationEnd>", "StopAtDurationEnd"),
        ("end boundary", "<Enabled>true</Enabled>\n      <Repetition>",
         "<EndBoundary>2030-01-01T00:00:00</EndBoundary><Enabled>true</Enabled>\n      <Repetition>", "EndBoundary"),
        ("hard-coded start", "@@START_BOUNDARY@@", "2026-11-02T10:15:00", "StartBoundary"),
        ("UTF-16 declaration", 'encoding="UTF-8"', 'encoding="UTF-16"', "encoding declaration"),
        ("unknown token", "@@WORK_DIR@@", "@@SECRET_DIR@@", "placeholder token"),
        ("drive-letter path", description, description.replace("</Description>", " at C:" + "\\work</Description>"),
         "drive-letter path"),
        ("user-profile path", description, description.replace("</Description>", " in /Users/someone/job</Description>"),
         "user-profile path"),
        ("environment profile path", description, description.replace("</Description>", " %USERPROFILE%</Description>"),
         "user-profile path"),
        ("network path", description, description.replace("</Description>", " \\\\host\\share</Description>"),
         "network path"),
        ("URL", description, description.replace("</Description>", " http://example.invalid/x</Description>"),
         "URL or host"),
        ("connection string", description, description.replace("</Description>", " " + url + "</Description>"),
         "credential-shaped"),
        ("service key", description, description.replace("</Description>", " " + key + "</Description>"),
         "credential-shaped"),
        ("broken XML", "</Settings>", "</Setting>", "not well-formed"),
    ]
    for name, old, new, expected in plants:
        assert old in template, name
        planted = template.replace(old, new, 1)
        assert planted != template, name
        problems = _problems(planted)
        assert any(expected in problem for problem in problems), (name, problems)

    for allowed in (">PT30M<", ">PT59M<", ">PT26M<"):
        assert _problems(template.replace(">PT45M<", allowed, 1)) == [], allowed


def test_template_is_utf8_without_bom_and_declares_utf8():
    """The file is UTF-8 with no byte-order mark and says so on its first line."""
    with open(TEMPLATE, "rb") as handle:
        data = handle.read()
    assert not data.startswith(b"\xef\xbb\xbf")
    assert not data.startswith(b"\xff\xfe") and not data.startswith(b"\xfe\xff")
    assert b"\x00" not in data
    text = data.decode("utf-8")
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>')


def test_template_secret_scan_is_clean(tmp_path):
    """The template passes the repository's own credential scan; a credential-shaped plant in an XML file does not."""
    assert secret_scan_test._scan([TEMPLATE]) == []
    url, _ = _credential_shapes()
    planted_file = tmp_path / "planted.xml"
    planted_file.write_text(_template_text().replace("@@ARGUMENTS@@", url), encoding="utf-8")
    assert [name for _, _, name in secret_scan_test._scan([str(planted_file)])] == ["pg_url_credential"]
