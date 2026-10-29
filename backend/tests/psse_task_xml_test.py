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

import datetime
import io
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import secret_scan_test  # noqa: E402
from psse_job import launcher, taskxml  # noqa: E402

_REPO_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
TEMPLATE = os.path.join(_REPO_ROOT, "docs", "data-science", "ops", "psse_hourly_task.xml")
NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
RENDER_SCRIPT = os.path.join(_BACKEND, "psse_render_task.py")
TIMEOUT = 60
START = "2026-11-02T10:15:00"


def _ns(name):
    """The namespaced tag of a Task Scheduler element."""
    return "{%s}%s" % (NS, name)


def _template_text():
    # A Windows checkout may hold the file with CRLF line ends; the checks below work on LF text.
    with open(TEMPLATE, "rb") as handle:
        return handle.read().decode("utf-8").replace("\r\n", "\n")


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


# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------

def _inputs(base, entry="entry.py", config="job.conf", work="work", python="python.exe"):
    """Existing tmp files and a folder for the four path arguments; names may hold spaces and an ampersand."""
    base.mkdir(parents=True, exist_ok=True)
    paths = {"entry_script": base / entry, "config_file": base / config, "python_exe": base / python}
    for key in ("entry_script", "config_file", "python_exe"):
        paths[key].write_text("placeholder\n", encoding="utf-8")
    paths["work_dir"] = base / work
    paths["work_dir"].mkdir(exist_ok=True)
    return dict((key, str(value)) for key, value in paths.items())


def _render(values, **flags):
    return taskxml.render(
        _template_text(), values["python_exe"], values["entry_script"], values["config_file"],
        values["work_dir"], flags.pop("start", START), **flags)


def test_render_escapes_xml_and_quotes_paths_with_spaces_and_ampersand(tmp_path):
    """A folder named with a space and an ampersand renders to well-formed XML; the parsed values equal the originals."""
    values = _inputs(tmp_path / "my dir & co", entry="run entry.py", config="job file.conf",
                     work="work dir", python="py thon.exe")
    text = _render(values)
    assert re.findall(r"&(?!amp;|lt;|gt;|quot;)", text) == []
    assert "&amp;" in text
    root = ET.fromstring(text)
    action = _child_texts(root.find(_ns("Actions") + "/" + _ns("Exec")))
    assert action["Command"] == '"%s"' % values["python_exe"]
    assert action["WorkingDirectory"] == values["work_dir"]
    assert action["Arguments"] == '-X utf8 "%s" run --config "%s"' % (values["entry_script"], values["config_file"])
    tokens = _split_arguments(action["Arguments"])
    assert tokens[:4] == ["-X", "utf8", values["entry_script"], "run"]
    parsed = launcher.build_parser().parse_args(tokens[3:])
    assert (parsed.mode, parsed.config) == ("run", values["config_file"])
    # An interpreter path without a space is not quoted.
    plain = _inputs(tmp_path / "plain")
    action = _child_texts(ET.fromstring(_render(plain)).find(_ns("Actions") + "/" + _ns("Exec")))
    assert action["Command"] == plain["python_exe"]


def test_render_refuses_unsafe_or_unquotable_values(tmp_path):
    """Relative, missing, unquotable, URL-shaped and badly timed values and a lone --allow-placeholder are refused."""
    good = _inputs(tmp_path / "zq_marker_dir")
    marker = "zq_marker_dir"
    arguments = ("python_exe", "entry_script", "config_file", "work_dir")

    def refused(bad, argument, word, **flags):
        values = dict(good, **bad)
        with pytest.raises(taskxml.TaskXmlError) as info:
            _render(values, **flags)
        message = str(info.value)
        assert info.value.argument == argument, (bad, message)
        assert word in message, (bad, message)
        assert marker not in message, "the message must not repeat the value"
        return message

    # Relative paths (also with check_exists False), and a missing or empty value.
    for argument in arguments:
        refused({argument: "rel/path"}, argument, "absolute", check_exists=False)
        refused({argument: "rel/path"}, argument, "absolute")
        refused({argument: ""}, argument, "empty")
        refused({argument: None}, argument, "empty")
        missing = os.path.join(good[argument], "nothing_here") if argument == "work_dir" else good[argument] + ".missing"
        refused({argument: missing}, argument, "exist")
        with_flag_off = _render(dict(good, **{argument: missing}), check_exists=False)
        assert "@@" not in with_flag_off

    # Characters that cannot be quoted safely or that the scheduler might expand.
    characters = [('"', "double quote"), ("\n", "line break"), ("\r", "line break"), ("<", "angle bracket"),
                  (">", "angle bracket"), ("%", "percent sign"), ("\t", "control character"),
                  ("@@", "at-sign pair")]
    for argument in arguments:
        for char, word in characters:
            refused({argument: good[argument] + char + "x"}, argument, word, check_exists=False)
        refused({argument: good[argument] + "x://y"}, argument, "URL", check_exists=False)
        refused({argument: "https://example.invalid/c.conf"}, argument, "URL")
    for argument in ("python_exe", "entry_script", "config_file"):
        refused({argument: good[argument] + "\\"}, argument, "backslash", check_exists=False)
    # A real file whose name holds a percent sign is refused with the file existing.
    pct = _inputs(tmp_path / "pct", config="a%b.conf")
    refused(dict(pct, work_dir=good["work_dir"]), "config_file", "percent sign")
    # An ampersand is allowed.
    assert "&amp;" in _render(_inputs(tmp_path / "x & y"))

    # Start boundary: exactly YYYY-MM-DDTHH:MM:SS and a real date.
    for bad in ("2026-11-02 10:15:00", "2026-11-02T10:15", "2026-13-02T10:15:00", "2026-11-02T25:15:00",
                "2026-11-02T10:15:00Z", "tomorrow", "", "2026-11-02T10:15:00<"):
        with pytest.raises(taskxml.TaskXmlError) as info:
            _render(good, start=bad)
        assert info.value.argument == "start_boundary" and "YYYY" in str(info.value)

    # --allow-placeholder only together with --dry-run, in the renderer and in build_arguments.
    with pytest.raises(taskxml.TaskXmlError) as info:
        _render(good, allow_placeholder=True)
    assert info.value.argument == "allow_placeholder" and "dry_run" in str(info.value)
    with pytest.raises(taskxml.TaskXmlError):
        taskxml.build_arguments(good["entry_script"], good["config_file"], allow_placeholder=True)
    assert "--allow-placeholder" in _render(good, dry_run=True, allow_placeholder=True)


def test_render_dry_run_arguments_parse_with_the_launcher(tmp_path):
    """--dry-run and --allow-placeholder reach the launcher's parser; a lone --allow-placeholder is refused at run time, not at parse time."""
    values = _inputs(tmp_path / "dry")
    for flags, expected in (({"dry_run": True}, (True, False)),
                            ({"dry_run": True, "allow_placeholder": True}, (True, True)),
                            ({}, (False, False))):
        root = ET.fromstring(_render(values, **flags))
        arguments = root.find(_ns("Actions") + "/" + _ns("Exec") + "/" + _ns("Arguments")).text
        tokens = _split_arguments(arguments)
        assert tokens[:3] == ["-X", "utf8", values["entry_script"]]
        parsed = launcher.build_parser().parse_args(tokens[3:])
        assert (parsed.mode, parsed.config) == ("run", values["config_file"])
        assert (parsed.dry_run, parsed.allow_placeholder) == expected
    assert taskxml.build_arguments(values["entry_script"], values["config_file"], True, True).endswith(
        " --dry-run --allow-placeholder")

    # The parser takes --allow-placeholder alone; the run refuses it with exit 2 before reading any config or loading psspy.
    parsed = launcher.build_parser().parse_args(["run", "--config", values["config_file"], "--allow-placeholder"])
    assert parsed.allow_placeholder is True and parsed.dry_run is False
    loaded = []
    err = io.StringIO()
    code = launcher.main(["run", "--config", values["config_file"], "--allow-placeholder"],
                         lambda cfg: loaded.append(cfg), out=io.StringIO(), err=err)
    assert code == 2 and loaded == []
    assert "--allow-placeholder" in err.getvalue()


def test_render_leaves_no_placeholder_and_is_deterministic(tmp_path):
    """No token is left, the same inputs give the same text, and a backslash in a value is copied literally."""
    values = _inputs(tmp_path / "det")
    first = _render(values)
    assert first == _render(values)
    assert "@@" not in first
    assert first != _render(values, start="2026-11-02T11:15:00")
    odd = os.path.join(str(tmp_path), "w\\1\\x41\\k")
    crlf = _template_text().replace("\n", "\r\n")
    assert taskxml.render(crlf, values["python_exe"], values["entry_script"], values["config_file"],
                          values["work_dir"], START) == first
    text = taskxml.render(_template_text(), values["python_exe"], values["entry_script"], values["config_file"],
                          odd, START, check_exists=False)
    assert "<WorkingDirectory>%s</WorkingDirectory>" % odd in text
    assert ET.fromstring(text) is not None
    assert not text.encode("utf-8").startswith(b"\xef\xbb\xbf")
    with pytest.raises(taskxml.TaskXmlError):
        taskxml.render("<Task>@@NOT_A_PLACEHOLDER@@</Task>", values["python_exe"], values["entry_script"],
                       values["config_file"], values["work_dir"], START)
    with pytest.raises(taskxml.TaskXmlError):
        taskxml.render("<Task>@@PYTHON_EXE@@</Task>", values["python_exe"], values["entry_script"],
                       values["config_file"], values["work_dir"], START)


def test_next_start_boundary_is_the_next_quarter_past():
    """The default start is the next time the local clock reads the minute, strictly after now; the minute is 0 to 59."""
    at = datetime.datetime
    assert taskxml.next_start_boundary(at(2026, 11, 2, 10, 20), 15) == "2026-11-02T11:15:00"
    assert taskxml.next_start_boundary(at(2026, 11, 2, 10, 10), 15) == "2026-11-02T10:15:00"
    assert taskxml.next_start_boundary(at(2026, 11, 2, 10, 15), 15) == "2026-11-02T11:15:00"
    assert taskxml.next_start_boundary(at(2026, 11, 2, 10, 14, 59), 15) == "2026-11-02T10:15:00"
    assert taskxml.next_start_boundary(at(2026, 11, 2, 10, 15, 0, 1), 15) == "2026-11-02T11:15:00"
    assert taskxml.next_start_boundary(at(2026, 11, 2, 23, 30), 15) == "2026-11-03T00:15:00"
    assert taskxml.next_start_boundary(at(2026, 12, 31, 23, 30), 15) == "2027-01-01T00:15:00"
    assert taskxml.next_start_boundary(at(2026, 11, 2, 10, 20), 0) == "2026-11-02T11:00:00"
    assert taskxml.next_start_boundary(at(2026, 11, 2, 10, 20), 59) == "2026-11-02T10:59:00"
    assert taskxml.next_start_boundary(at(2026, 11, 2, 10, 20)) == "2026-11-02T11:15:00"
    for bad in (-1, 60, 99, "15", None, 15.5, True):
        with pytest.raises(taskxml.TaskXmlError):
            taskxml.next_start_boundary(at(2026, 11, 2, 10, 20), bad)


def _run_script(arguments, cwd):
    return subprocess.run([sys.executable, "-I", "-B", RENDER_SCRIPT] + arguments, cwd=str(cwd),
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT)


def test_render_script_writes_utf8_and_refuses_overwrite(tmp_path):
    """The install command writes UTF-8 without a byte-order mark, refuses to overwrite without --force and names a refused option."""
    values = _inputs(tmp_path / "zq_marker_dir")
    out = tmp_path / "filled.xml"
    base = ["--config", values["config_file"], "--work-dir", values["work_dir"], "--entry", values["entry_script"],
            "--out", str(out), "--python", values["python_exe"]]

    done = _run_script(base + ["--start", START], tmp_path)
    assert done.returncode == 0, done.stderr
    data = out.read_bytes()
    assert data.startswith(b"<?xml") and not data.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in data
    text = data.decode("utf-8")
    assert "@@" not in text
    root = ET.fromstring(text)
    assert root.find(_ns("Triggers") + "/" + _ns("TimeTrigger") + "/" + _ns("StartBoundary")).text == START
    arguments = root.find(_ns("Actions") + "/" + _ns("Exec") + "/" + _ns("Arguments")).text
    assert arguments == '-X utf8 "%s" run --config "%s"' % (values["entry_script"], values["config_file"])

    # An existing output file is not overwritten without --force.
    again = _run_script(base + ["--start", "2026-11-03T10:15:00"], tmp_path)
    assert again.returncode == 2
    assert out.read_bytes() == data
    lines = [line for line in again.stderr.decode("utf-8").splitlines() if line.strip()]
    assert len(lines) == 1 and "--force" in lines[0]
    forced = _run_script(base + ["--start", "2026-11-03T10:15:00", "--force"], tmp_path)
    assert forced.returncode == 0, forced.stderr
    assert b"2026-11-03T10:15:00" in out.read_bytes() and out.read_bytes() != data

    # The smoke task: --dry-run with --allow-placeholder; the second flag alone is refused.
    smoke = _run_script(base[:-2] + ["--python", values["python_exe"], "--dry-run", "--allow-placeholder", "--force"],
                        tmp_path)
    assert smoke.returncode == 0, smoke.stderr
    assert out.read_text(encoding="utf-8").count("--allow-placeholder") == 1
    lone = _run_script(base + ["--allow-placeholder", "--force"], tmp_path)
    assert lone.returncode == 2 and "--allow-placeholder" in lone.stderr.decode("utf-8")

    # A relative path exits 2 with one line that names the option and not the value.
    fresh = tmp_path / "fresh.xml"
    relative = _run_script(["--config", "rel_marker.conf", "--work-dir", values["work_dir"], "--out", str(fresh),
                            "--entry", values["entry_script"], "--python", values["python_exe"]], tmp_path)
    assert relative.returncode == 2 and not fresh.exists()
    lines = [line for line in relative.stderr.decode("utf-8").splitlines() if line.strip()]
    assert len(lines) == 1 and "--config" in lines[0] and "rel_marker" not in lines[0]

    # The default interpreter and entry script are this one and the committed script; --start and --minute exclude each other.
    default = _run_script(["--config", values["config_file"], "--work-dir", values["work_dir"],
                           "--out", str(tmp_path / "default.xml"), "--minute", "30"], tmp_path)
    assert default.returncode == 0, default.stderr
    default_text = (tmp_path / "default.xml").read_text(encoding="utf-8")
    assert os.path.join(_BACKEND, "psse_run_hourly.py") in default_text.replace("&amp;", "&")
    assert re.search(r"<StartBoundary>\d{4}-\d\d-\d\dT\d\d:30:00</StartBoundary>", default_text)
    both = _run_script(base + ["--start", START, "--minute", "5", "--force"], tmp_path)
    assert both.returncode == 2
