"""
Task Scheduler template renderer (pss-e-integration Phase 3, plan 03-05, SCH-01).

Fills docs/data-science/ops/psse_hourly_task.xml from paths the person installing the job gives:
text only, standard library only, Python 3.7 syntax. The XML is not parsed here (the tests parse it).
The renderer refuses what it cannot quote or what is unsafe (see _check_text and _check_path); a
refusal names the argument and never repeats the value.

Honest scope: nothing here was registered with Windows Task Scheduler and Microsoft's schema was
not run against the output, so every behaviour of the real scheduler (accepting the file, repeating
indefinitely, a quoted Command with spaces, whether a percent sign would be expanded, UTF-8 import,
wake, battery flags, exit code in LastTaskResult, registration by a standard user) is UNVERIFIED
until runbook step 6 (plan 03-07).
"""

import datetime
import os
import re

PLACEHOLDERS = ("PYTHON_EXE", "ARGUMENTS", "WORK_DIR", "START_BOUNDARY")

_TOKEN = re.compile(r"@@([A-Z_]+)@@")
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
_TIME_SHAPE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\Z")


class TaskXmlError(ValueError):
    """A value the renderer refuses. The message names the argument, never the value; `argument` holds the name."""

    def __init__(self, message, argument=None):
        ValueError.__init__(self, message)
        self.argument = argument


def _escape(text):
    """XML escaping for element text: ampersand first, then the angle brackets and the quotation mark."""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _check_text(argument, value):
    """
    Refuse a value that is empty, not text, or holds a character that cannot be double-quoted safely
    or that the scheduler might expand: a line break or other control character, a double quote, an
    angle bracket, a percent sign (UNVERIFIED whether the scheduler expands it), a pair of at-signs
    (it would look like a placeholder) or `://` (a value that looks like a URL). An ampersand is allowed.
    """
    if not isinstance(value, str) or not value:
        raise TaskXmlError("%s is empty or not text" % argument, argument)
    if "\n" in value or "\r" in value:
        raise TaskXmlError("%s contains a line break, which cannot be quoted safely" % argument, argument)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise TaskXmlError("%s contains a control character, which cannot be quoted safely" % argument, argument)
    if '"' in value:
        raise TaskXmlError("%s contains a double quote, which cannot be quoted safely" % argument, argument)
    if "<" in value or ">" in value:
        raise TaskXmlError("%s contains an angle bracket, which cannot be quoted safely" % argument, argument)
    if "%" in value:
        raise TaskXmlError("%s contains a percent sign, which the scheduler might expand" % argument, argument)
    if "@@" in value:
        raise TaskXmlError("%s contains an at-sign pair, which would look like a placeholder" % argument, argument)
    if "://" in value:
        raise TaskXmlError("%s looks like a URL, not a local path" % argument, argument)


def _check_path(argument, value, kind, check_exists):
    """
    The text rules plus: absolute, no trailing backslash for a file (a backslash before the closing
    double quote would escape it), and, when check_exists, an existing file or folder (kind is
    "file" or "dir").
    """
    _check_text(argument, value)
    if kind == "file" and value.endswith("\\"):
        raise TaskXmlError("%s ends with a backslash, which would escape its closing quote" % argument, argument)
    if not os.path.isabs(value):
        raise TaskXmlError("%s must be an absolute path" % argument, argument)
    if check_exists:
        found = os.path.isfile(value) if kind == "file" else os.path.isdir(value)
        if not found:
            raise TaskXmlError("%s does not exist as %s" % (argument, "a file" if kind == "file" else "a folder"),
                               argument)


def _check_flags(dry_run, allow_placeholder):
    if allow_placeholder and not dry_run:
        raise TaskXmlError("allow_placeholder is accepted only together with dry_run", "allow_placeholder")


def build_arguments(entry_script, config_file, dry_run=False, allow_placeholder=False):
    """
    The Arguments text of the task: `-X utf8 "ENTRY" run --config "CONFIG"` (UTF-8 mode because the
    Windows default encoding is not UTF-8), plus `--dry-run` and, with it, `--allow-placeholder`
    when asked. The entry script and the config file are double-quoted so a path with a space stays
    one token (UNVERIFIED on the real scheduler). Only paths, never a credential. The form of both
    paths is checked here (existence is checked by render); --allow-placeholder without --dry-run
    is refused.
    """
    _check_path("entry_script", entry_script, "file", False)
    _check_path("config_file", config_file, "file", False)
    _check_flags(dry_run, allow_placeholder)
    parts = ["-X", "utf8", '"%s"' % entry_script, "run", "--config", '"%s"' % config_file]
    if dry_run:
        parts.append("--dry-run")
    if allow_placeholder:
        parts.append("--allow-placeholder")
    return " ".join(parts)


def next_start_boundary(now, minute=15):
    """
    The next time the local clock reads `minute` past the hour, strictly after `now` (a naive local
    datetime), as YYYY-MM-DDTHH:MM:SS. `minute` is a whole number from 0 to 59.
    """
    if not isinstance(minute, int) or isinstance(minute, bool) or not 0 <= minute <= 59:
        raise TaskXmlError("minute must be a whole number from 0 to 59", "minute")
    candidate = now.replace(minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + datetime.timedelta(hours=1)
    return candidate.strftime(_TIME_FORMAT)


def _check_start(value):
    ok = isinstance(value, str) and _TIME_SHAPE.match(value) is not None
    if ok:
        try:
            datetime.datetime.strptime(value, _TIME_FORMAT)
        except ValueError:
            ok = False
    if not ok:
        raise TaskXmlError("start_boundary must be a local time written YYYY-MM-DDTHH:MM:SS", "start_boundary")


def render(template_text, python_exe, entry_script, config_file, work_dir, start_boundary,
           dry_run=False, allow_placeholder=False, check_exists=True):
    """
    The template with its four placeholders replaced: PYTHON_EXE (double-quoted when it holds a
    space), ARGUMENTS (build_arguments), WORK_DIR and START_BOUNDARY, each XML-escaped. Line ends
    of the template are normalised to LF, so a Windows checkout renders the same text.

    Raises TaskXmlError, naming the argument, for a relative path, a path that does not exist
    (unless check_exists is False), a value with a double quote, a line break, an angle bracket or a
    percent sign, a value that looks like a URL, a start boundary that is not YYYY-MM-DDTHH:MM:SS,
    --allow-placeholder without --dry-run, and a template whose tokens are not exactly the four
    placeholders.
    """
    template_text = template_text.replace("\r\n", "\n")
    tokens = set(_TOKEN.findall(template_text))
    if tokens != set(PLACEHOLDERS) or "@@" in _TOKEN.sub("", template_text):
        raise TaskXmlError("template does not hold exactly the four placeholders", "template")
    _check_path("python_exe", python_exe, "file", check_exists)
    _check_path("entry_script", entry_script, "file", check_exists)
    _check_path("config_file", config_file, "file", check_exists)
    _check_path("work_dir", work_dir, "dir", check_exists)
    _check_start(start_boundary)
    values = {
        "PYTHON_EXE": '"%s"' % python_exe if " " in python_exe else python_exe,
        "ARGUMENTS": build_arguments(entry_script, config_file, dry_run, allow_placeholder),
        "WORK_DIR": work_dir,
        "START_BOUNDARY": start_boundary,
    }
    text = _TOKEN.sub(lambda match: _escape(values[match.group(1)]), template_text)
    if "@@" in text:
        raise TaskXmlError("a placeholder was left after rendering", "template")
    return text
