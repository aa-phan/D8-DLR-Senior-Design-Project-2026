"""
Task Scheduler template renderer (pss-e-integration Phase 3, plan 03-05, SCH-01).

Fills docs/data-science/ops/psse_hourly_task.xml from paths the person installing the job gives:
text only, standard library only, Python 3.7 syntax. The XML is not parsed here (the tests parse it).

Honest scope: nothing here was registered with Windows Task Scheduler and Microsoft's schema was
not run against the output, so every behaviour of the real scheduler (accepting the file, repeating
indefinitely, a quoted Command with spaces, UTF-8 import, wake, battery flags, exit code in
LastTaskResult, registration by a standard user) is UNVERIFIED until runbook step 6 (plan 03-07).
"""

import datetime
import os
import re

PLACEHOLDERS = ("PYTHON_EXE", "ARGUMENTS", "WORK_DIR", "START_BOUNDARY")

_TOKEN = re.compile(r"@@([A-Z_]+)@@")
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


class TaskXmlError(ValueError):
    """A value the renderer refuses. The message names the argument, never the value."""


def _escape(text):
    """XML escaping for element text: ampersand first, then the angle brackets and the quotation mark."""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_arguments(entry_script, config_file, dry_run=False, allow_placeholder=False):
    """
    The Arguments text of the task: `-X utf8 "ENTRY" run --config "CONFIG"` (UTF-8 mode because the
    Windows default encoding is not UTF-8), plus `--dry-run` and, with it, `--allow-placeholder`
    when asked. The entry script and the config file are double-quoted so a path with a space stays
    one token. Only paths, never a credential.
    """
    parts = ["-X", "utf8", '"%s"' % entry_script, "run", "--config", '"%s"' % config_file]
    if dry_run:
        parts.append("--dry-run")
    if allow_placeholder:
        parts.append("--allow-placeholder")
    return " ".join(parts)


def next_start_boundary(now, minute=15):
    """
    The next time the local clock reads `minute` past the hour, strictly after `now` (a naive local
    datetime), as YYYY-MM-DDTHH:MM:SS.
    """
    candidate = now.replace(minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + datetime.timedelta(hours=1)
    return candidate.strftime(_TIME_FORMAT)


def render(template_text, python_exe, entry_script, config_file, work_dir, start_boundary,
           dry_run=False, allow_placeholder=False, check_exists=True):
    """
    The template with its four placeholders replaced: PYTHON_EXE (double-quoted when it holds a
    space), ARGUMENTS (build_arguments), WORK_DIR and START_BOUNDARY, each XML-escaped.
    """
    values = {
        "PYTHON_EXE": '"%s"' % python_exe if " " in python_exe else python_exe,
        "ARGUMENTS": build_arguments(entry_script, config_file, dry_run, allow_placeholder),
        "WORK_DIR": work_dir,
        "START_BOUNDARY": start_boundary,
    }
    return _TOKEN.sub(lambda match: _escape(values[match.group(1)]), template_text)
