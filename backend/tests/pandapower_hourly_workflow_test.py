"""
Text checks of .github/workflows/pandapower_hourly.yml (pandapower-solver Phase 5,
OPS-01 and OPS-02).

PyYAML is not installed in this project's .venv and must not be added, so these
tests read the workflow as text with `re`, the way dlr_live_workflow_test.py reads
dlr_live.yml. The file is opened in text mode (the checkout has core.autocrlf
true) and is never pinned by its bytes. Command lines are matched, not comments:
the header comment also names the entry script.
"""

import os
import re

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
_CADENCE_MINUTES = 60  # hourly

_RUN_LINE = r"^\s*run:\s*python -I -B backend/pandapower_hourly\.py {command}\s*$"
_INSTALL_LINE = (
    r"^\s*python -m pip install -r requirements-pandapower\.txt "
    r"psycopg==(\S+) psycopg-binary==(\S+)\s*$"
)


def _workflow() -> str:
    with open(os.path.join(_REPO, ".github", "workflows", "pandapower_hourly.yml")) as fh:
        return fh.read()


def _requirements() -> str:
    with open(os.path.join(_REPO, "requirements.txt")) as fh:
        return fh.read()


def _step(text: str, name: str) -> str:
    """The text of one step: from its `- name:` line to the next step (or the end)."""
    match = re.search(
        rf"^      - name: {re.escape(name)}\s*\n(.*?)(?=^      - name:|\Z)",
        text,
        flags=re.M | re.S,
    )
    assert match, name
    return match.group(0)


def test_tracer_workflow_is_dispatch_only_with_its_own_group():
    text = _workflow()

    assert re.search(r"^\s*workflow_dispatch:", text, flags=re.M)
    for trigger in ("schedule", "push", "pull_request"):
        assert not re.search(rf"^\s*{trigger}\s*:", text, flags=re.M), trigger
    assert not re.search(r"^\s*(-\s*)?cron\s*:", text, flags=re.M)

    # No workflow input at all: a person who dispatches cannot choose anything.
    assert not re.search(r"^\s*inputs\s*:", text, flags=re.M)
    assert not re.search(r"\$\{\{\s*inputs\.", text)

    assert re.search(r"^\s*group:\s*pandapower-hourly\s*(#.*)?$", text, flags=re.M)
    assert "group: dlr-live" not in text
    assert "group: shadow-collection" not in text
    assert re.search(r"^\s*cancel-in-progress:\s*false\b", text, flags=re.M)

    assert re.search(r"^permissions:\s*\n\s+contents:\s*read\b", text, flags=re.M)
    assert not re.search(r"^\s*[a-z-]+:\s*write\b", text, flags=re.M)


def test_job_runs_only_on_main_in_the_production_environment():
    text = _workflow()

    assert re.search(
        r"^  study:\s*\n(    .*\n|\s*\n)*?    if: github\.ref == 'refs/heads/main'\s*(#.*)?$",
        text,
        flags=re.M,
    )
    assert re.search(
        r"^  study:\s*\n(    .*\n|\s*\n)*?    environment: production\s*(#.*)?$", text, flags=re.M
    )
    assert re.search(
        r"^  study:\s*\n(    .*\n|\s*\n)*?    runs-on: ubuntu-latest\s*(#.*)?$", text, flags=re.M
    )


def test_timeout_is_30_minutes_and_below_the_cadence():
    text = _workflow()

    matches = re.findall(r"^\s*timeout-minutes:\s*(\d+)\s*(#.*)?$", text, flags=re.M)
    assert len(matches) == 1
    timeout = int(matches[0][0])
    assert timeout == 30
    assert timeout < _CADENCE_MINUTES  # a run cut off at its timeout never overlaps the next slot


def test_install_line_and_pins_match_requirements():
    text = _workflow()

    setup = _step(text, "Set up Python 3.12")
    assert re.search(r"^\s*python-version:\s*'3\.12'\s*$", setup, flags=re.M)
    assert re.search(r"^\s*cache:\s*'pip'", setup, flags=re.M)
    assert re.search(
        r"^\s*cache-dependency-path:\s*requirements-pandapower\.txt\s*(#.*)?$", setup, flags=re.M
    )

    install = re.search(_INSTALL_LINE, text, flags=re.M)
    assert install
    required = _requirements()
    psycopg = re.search(r"^psycopg==(\S+)\s*$", required, flags=re.M)
    binary = re.search(r"^psycopg-binary==(\S+)\s*$", required, flags=re.M)
    assert psycopg and binary
    assert install.group(1) == psycopg.group(1)
    assert install.group(2) == binary.group(1)
    assert install.group(1) == install.group(2)  # psycopg-binary must stay equal to psycopg


def test_steps_run_the_entry_script_in_order():
    text = _workflow()

    install = re.search(_INSTALL_LINE, text, flags=re.M)
    study = re.findall(_RUN_LINE.format(command="run"), text, flags=re.M)
    soak = re.findall(_RUN_LINE.format(command="soak"), text, flags=re.M)
    assert install and len(study) == 1 and len(soak) == 1

    study_at = re.search(_RUN_LINE.format(command="run"), text, flags=re.M).start()
    soak_at = re.search(_RUN_LINE.format(command="soak"), text, flags=re.M).start()
    removal = re.search(
        r"^\s*run:\s*rm -rf \"\$RUNNER_TEMP\"/pandapower_hourly_\*\s*$", text, flags=re.M
    )
    assert removal
    assert install.start() < study_at < soak_at < removal.start()

    # The step names this plan promises, in order.
    names = re.findall(r"^      - name: (.+?)\s*$", text, flags=re.M)
    assert names == [
        "Checkout code (main)",
        "Set up Python 3.12",
        "Install dependencies",
        "Run study",
        "Gap and soak check",
        "Remove private files",
    ]
