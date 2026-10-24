"""
Text checks of .github/workflows/dlr_live.yml (production-pipeline Phase 5, PIPE-02).

PyYAML is not installed in this project's .venv and must not be added, so these
tests read the workflow as text with `re`, the way
backend/tests/forecast_shadow_collect_test.py reads shadow_collect.yml. They pin
the properties the plan relies on: dispatch-only and separate from the shadow
collection, a job timeout that fits the cadence, every secret mapped, and no
workflow input ever reaching a `run:` script.
"""

import os
import re

import config
import dlr_live_run

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
_CADENCE_MINUTES = 60  # OD-1: hourly
_SETUP_MINUTES = 10  # setup, the model pre-flight and the run-log writes


def _workflow() -> str:
    with open(os.path.join(_REPO, ".github", "workflows", "dlr_live.yml")) as fh:
        return fh.read()


def test_workflow_is_dispatch_only_and_separate_from_shadow_collection():
    text = _workflow()

    assert re.search(r"^\s*workflow_dispatch:", text, flags=re.M)
    for trigger in ("schedule", "push", "pull_request"):
        assert not re.search(rf"^\s*{trigger}\s*:", text, flags=re.M), trigger
    assert not re.search(r"^\s*(-\s*)?cron\s*:", text, flags=re.M)

    assert re.search(r"^\s*group:\s*dlr-live\s*(#.*)?$", text, flags=re.M)
    assert "group: shadow-collection" not in text
    assert re.search(r"^\s*cancel-in-progress:\s*false\b", text, flags=re.M)

    assert re.search(r"^permissions:\s*\n\s+contents:\s*read\b", text, flags=re.M)
    assert not re.search(r"^\s*[a-z-]+:\s*write\b", text, flags=re.M)


def test_timeout_fits_the_cities_and_the_cadence():
    text = _workflow()

    match = re.search(r"^\s*timeout-minutes:\s*(\d+)\s*(#.*)?$", text, flags=re.M)
    assert match and int(match.group(1)) == 30
    timeout = int(match.group(1))

    child_seconds = len(config.LOCATIONS) * dlr_live_run.CITY_TIMEOUT_S
    assert child_seconds == 1200
    assert child_seconds <= (timeout - _SETUP_MINUTES) * 60
    assert timeout < _CADENCE_MINUTES  # a run cut off at its timeout never overlaps the next slot


def test_every_required_secret_is_mapped_and_inputs_never_reach_a_run_script():
    text = _workflow()

    for name in dlr_live_run.REQUIRED_ENV:
        assert re.search(rf"^\s*{name}:\s*\$\{{\{{\s*secrets\.{name}\s*\}}\}}\s*$", text, flags=re.M), name

    # The only workflow-input expression is the env mapping for the fault drill.
    expression = re.compile(r"\$\{\{\s*inputs\.")
    uses = [line for line in text.splitlines() if expression.search(line)]
    assert uses == ["          DLR_LIVE_FAULT_CITY: ${{ inputs.fault_city }}"]

    # No `${{ }}` expression of any kind sits inside a run: script.
    lines = text.splitlines()
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
        assert "${{" not in "\n".join(body), line

    assert re.search(r"^\s*run:\s*PYTHONPATH=backend python backend/dlr_live_run\.py\s*$", text, flags=re.M)
    assert re.search(r"python-version:\s*'3\.12'", text)


def test_models_are_verified_before_the_run():
    text = _workflow()

    # Match the steps' command lines, not comments: the file's header comment also names the runner.
    install = re.search(r"^\s*python -m pip install -r requirements\.txt\s*$", text, flags=re.M)
    preflight = re.search(
        r"^\s*run:\s*PYTHONPATH=backend python backend/dlr_live_check_models\.py\s*$", text, flags=re.M
    )
    run = re.search(r"^\s*run:\s*PYTHONPATH=backend python backend/dlr_live_run\.py\s*$", text, flags=re.M)

    assert install and preflight and run
    assert install.start() < preflight.start() < run.start()

    # Exactly one pre-flight step, and it is handed no secrets: it unpickles model files.
    assert len(re.findall(r"dlr_live_check_models\.py", text)) == 1
    step = re.search(
        r"^      - name: Pre-flight - live model artifacts present and verified\n(.*?)(?=^      - name:)",
        text,
        flags=re.M | re.S,
    )
    assert step
    assert "${{" not in step.group(1)
    assert not re.search(r"^\s*env:", step.group(1), flags=re.M)
