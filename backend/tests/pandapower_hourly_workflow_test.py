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


# ---------------------------------------------------------------------------
# What each step receives (OPS-02; D-02, D-08, D-10, D-13)
# ---------------------------------------------------------------------------

_B64_SECRETS = (
    "PANDAPOWER_NETWORK_B64",
    "PANDAPOWER_MAPPING_B64",
    "PANDAPOWER_SETTINGS_B64",
    "PANDAPOWER_SCALING_B64",
)
_WRITER_PLAIN = "${{ secrets.SUPABASE_PSSE_DB_URL }}"
_WRITER_WHEN_LIVE = "${{ vars.PANDAPOWER_LIVE == 'true' && secrets.SUPABASE_PSSE_DB_URL || '' }}"


def _env(step: str) -> dict:
    """The `env:` mapping of one step as {name: value}; comment lines are skipped."""
    match = re.search(r"^        env:\s*\n((?:          .*\n|\s*\n)*)", step, flags=re.M)
    if not match:
        return {}
    mapping = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        entry = re.match(r"^          ([A-Z][A-Z0-9_]*):\s*(.*?)\s*$", line)
        assert entry, line
        mapping[entry.group(1)] = entry.group(2)
    return mapping


def _code_lines(text: str) -> list:
    """Every line that is not a whole-line comment."""
    return [line for line in text.splitlines() if not re.match(r"^\s*#", line)]


def _run_bodies(text: str) -> list:
    """The body of every `run:` key: its own line plus the deeper-indented lines after it."""
    lines = text.splitlines()
    bodies = []
    for i, line in enumerate(lines):
        run = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", line)
        if not run:
            continue
        body = [run.group(2)]
        indent = len(run.group(1))
        for following in lines[i + 1:]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        bodies.append("\n".join(body))
    return bodies


def test_study_step_receives_the_secrets_and_the_switch():
    step = _step(_workflow(), "Run study")
    env = _env(step)

    expected = {
        "PANDAPOWER_LIVE": "${{ vars.PANDAPOWER_LIVE }}",
        "SUPABASE_URL": "${{ secrets.SUPABASE_URL }}",
        "SUPABASE_PUBLISHABLE_KEY": "${{ secrets.SUPABASE_PUBLISHABLE_KEY }}",
        "SUPABASE_PSSE_DB_URL": _WRITER_WHEN_LIVE,
    }
    for name in _B64_SECRETS:
        expected[name] = "${{ secrets.%s }}" % name
    assert env == expected


def test_writer_value_reaches_the_study_step_only_when_live():
    text = _workflow()
    study = _env(_step(text, "Run study"))

    # Handed over only when the repository variable is exactly the text true.
    assert study["SUPABASE_PSSE_DB_URL"] == _WRITER_WHEN_LIVE
    assert study["SUPABASE_PSSE_DB_URL"] != _WRITER_PLAIN

    # The switch is the repository variable and nothing else: two code lines name it (the
    # env mapping and the writer condition), and no other context ever supplies it.
    code = "\n".join(_code_lines(text))
    assert len(re.findall(r"vars\.PANDAPOWER_LIVE", code)) == 2
    assert not re.search(r"(secrets|env|inputs|github\.event)\.PANDAPOWER_LIVE", code)

    # The plain writer secret appears twice only: the conditional above and the soak step.
    assert len(re.findall(r"secrets\.SUPABASE_PSSE_DB_URL", code)) == 2


def test_soak_step_receives_only_the_writer_value():
    env = _env(_step(_workflow(), "Gap and soak check"))

    assert env == {"SUPABASE_PSSE_DB_URL": _WRITER_PLAIN}


def test_no_other_step_receives_anything():
    text = _workflow()

    for name in (
        "Checkout code (main)",
        "Set up Python 3.12",
        "Install dependencies",
        "Remove private files",
    ):
        step = _step(text, name)
        assert not re.search(r"^\s*env:", step, flags=re.M), name
        assert "${{" not in step, name

    # Only the study and soak steps carry an env block at all.
    assert len(re.findall(r"^        env:\s*$", text, flags=re.M)) == 2


def test_no_expression_inside_a_run_body_and_no_secret_in_an_if():
    text = _workflow()

    bodies = _run_bodies(text)
    assert len(bodies) == 4  # install, study, soak, removal
    for body in bodies:
        assert "${{" not in body, body

    # `secrets` is not available in an `if`, and a condition must never name one.
    conditions = [line for line in _code_lines(text) if re.match(r"^\s*(-\s+)?if:", line)]
    assert len(conditions) == 3  # job guard, soak step, removal step
    for line in conditions:
        assert "secrets." not in line, line


def test_no_debug_or_echo_and_only_first_party_actions():
    text = _workflow()

    for body in _run_bodies(text):
        assert not re.search(r"\b(set -x|printenv|cat|echo)\b", body), body

    uses = re.findall(r"^\s*(?:-\s+)?uses:\s*(\S+)\s*$", text, flags=re.M)
    assert sorted(uses) == ["actions/checkout@v4", "actions/setup-python@v5"]

    assert re.search(r"^\s*persist-credentials:\s*false\b", text, flags=re.M)
