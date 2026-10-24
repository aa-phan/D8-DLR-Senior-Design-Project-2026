"""
Runbook consistency and secret hygiene for the live workflow (production-pipeline
Phase 5, SCHED-02, threats T-05-21 and T-05-25).

The runbook (docs/data-science/decisions/dlr_live_runbook.md) is the only record of the
cron-job.org job, its token scope and the minutes budget, which live outside the repo.
These tests read the runbook, the workflow and the modules as text (PyYAML is not
installed), and fail when a constant the runbook quotes drifts from the code. The last
test scans every text file the phase created or edited for secret-shaped values; it
reports the path, line number and pattern name only, never the matched text.

The secret patterns are assembled from string pieces so this file does not match its
own scan.
"""

import os
import re

import config
import dlr_live_check_models
import dlr_live_run
import observation_composer

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_RUNBOOK = os.path.join("docs", "data-science", "decisions", "dlr_live_runbook.md")
_WORKFLOW = os.path.join(".github", "workflows", "dlr_live.yml")

# Every text file this phase creates or edits. The eight .joblib model files are binary
# weights and are not scanned. A file listed here that does not exist fails the test, so
# renaming one cannot silently drop it from the scan.
PHASE5_TEXT_FILES = (
    _WORKFLOW,
    os.path.join("backend", "dlr_live_run.py"),
    os.path.join("backend", "live_run_log.py"),
    os.path.join("backend", "dlr_live_check_models.py"),
    os.path.join("backend", "dlr_live_window_check.py"),
    _RUNBOOK,
    os.path.join("data", "models", "LIVE_ARTIFACT_HASHES.sha256"),
    ".gitignore",
    # modules edited by 05-02
    os.path.join("backend", "city_pipeline.py"),
    os.path.join("backend", "dlr_orchestrator.py"),
    os.path.join("backend", "observation_composer.py"),
    os.path.join("backend", "dlr_pipeline.py"),
    os.path.join("backend", "DLRSafetyMonitor.py"),
    os.path.join("backend", "backfill_archive.py"),
    # the phase's own tests
    os.path.join("backend", "tests", "dlr_live_run_test.py"),
    os.path.join("backend", "tests", "dlr_live_workflow_test.py"),
    os.path.join("backend", "tests", "live_run_log_test.py"),
    os.path.join("backend", "tests", "dlr_live_check_models_test.py"),
    os.path.join("backend", "tests", "dlr_live_window_check_test.py"),
    os.path.join("backend", "tests", "live_log_hygiene_test.py"),
    os.path.join("backend", "tests", "dlr_live_runbook_test.py"),
)

_SCHEME = "postgres" + "(?:ql)?://"
_SECRET_PATTERNS = {
    "github_classic_token": re.compile("gh" + "p_" + r"[A-Za-z0-9]{20,}"),
    "github_fine_grained_token": re.compile("github" + "_pat_" + r"[A-Za-z0-9_]{20,}"),
    "supabase_secret_key": re.compile("sb" + "_secret_"),
    "supabase_publishable_key": re.compile("sb" + "_publishable_" + r"[A-Za-z0-9_-]{10,}"),
    "jwt_like": re.compile("ey" + "J" + r"[A-Za-z0-9_-]{20,}"),
    "credentialed_database_url": re.compile(_SCHEME + r"[^\s:@/'\"]+:[^\s@/'\"]+@"),
    # Phase 4's secret scan (secret_scan_test.py) also flags a literal role password
    "alter_role_literal": re.compile(
        r"(?i)\balter\s+role\s+\S+(?:\s+with)?\s+(?:encrypted\s+)?" + "pass" + r"word\s+'[^'<>]+'"
    ),
}


def _read(relative: str) -> str:
    with open(os.path.join(_REPO, relative), encoding="utf-8") as fh:
        return fh.read()


def _scan_line(line: str) -> list:
    return [name for name, pattern in _SECRET_PATTERNS.items() if pattern.search(line)]


def _runbook() -> str:
    return _read(_RUNBOOK)


def _section(text: str, heading_fragment: str) -> str:
    """The body of the `## ` section whose heading contains `heading_fragment`."""
    parts = re.split(r"(?m)^## ", text)
    for part in parts[1:]:
        title = part.splitlines()[0]
        if heading_fragment in title:
            return part
    raise AssertionError(f"no '## ' section with {heading_fragment!r} in its heading")


def test_runbook_constants_match_the_code_and_workflow():
    text = _runbook()
    workflow = _read(_WORKFLOW)

    assert f"{dlr_live_run.CITY_TIMEOUT_S} s" in text
    assert f"`CITY_TIMEOUT_S` = {dlr_live_run.CITY_TIMEOUT_S} s" in text
    assert f"{len(config.LOCATIONS)} cities x {dlr_live_run.CITY_TIMEOUT_S} s" in text
    for name in dlr_live_run.REQUIRED_ENV:
        assert name in text, name

    timeout = re.search(r"(?m)^\s*timeout-minutes:\s*(\d+)\s*(#.*)?$", workflow)
    assert timeout, "timeout-minutes not found in dlr_live.yml"
    assert f"timeout-minutes: {timeout.group(1)}" in text

    group = re.search(r"(?m)^\s*group:\s*(\S+)\s*(#.*)?$", workflow)
    assert group, "concurrency group not found in dlr_live.yml"
    assert f"`{group.group(1)}`" in text

    assert dlr_live_check_models.MANIFEST_PATH.replace(os.sep, "/") in text
    assert "NSRDB_SKIP_YEARS_BEFORE_CURRENT" in text
    assert f"NSRDB_SKIP_YEARS_BEFORE_CURRENT = {observation_composer.NSRDB_SKIP_YEARS_BEFORE_CURRENT}" in text
    assert "fault_city" in text
    assert "dlr_live_window_check.py" in text


def test_runbook_documents_the_external_trigger_pause_and_cadence():
    text = _runbook()

    for needle in (
        "actions/workflows/dlr_live.yml/dispatches",
        '{"ref":"main"}',
        "204",
        "5 * * * *",
        "UTC",
        "Disable workflow",
        "OD-1",
        "OD-4",
        "cron-job.org",
    ):
        assert needle in text, needle


def test_runbook_minutes_section_covers_both_workflows():
    section = _section(_runbook(), "Actions minutes")

    for needle in ("Shadow Collection", "DLR Live Ratings", "2026-11-24"):
        assert needle in section, needle


def test_phase5_files_contain_no_secret_values():
    # Control: each pattern fires on a planted line assembled at run time, so a pattern that
    # silently stopped matching cannot make the scan below pass vacuously.
    tail = "A1b2C3d4E5f6G7h8I9j0K1l2"
    planted = {
        "github_classic_token": "token " + "gh" + "p_" + tail,
        "github_fine_grained_token": "token " + "github" + "_pat_" + tail,
        "supabase_secret_key": "key " + "sb" + "_secret_" + "xyz",
        "supabase_publishable_key": "key " + "sb" + "_publishable_" + tail,
        "jwt_like": "Bearer " + "ey" + "J" + tail + "." + tail,
        "credentialed_database_url": "url " + "postgres" + "ql://" + "user:" + "hunter2" + "@host:5432/db",
        "alter_role_literal": "ALTER ROLE dlr_writer WITH " + "pass" + "word '" + "hunter2" + "';",
    }
    assert set(planted) == set(_SECRET_PATTERNS)
    for name, line in planted.items():
        assert name in _scan_line(line), name
    # a role-password placeholder is not a secret
    assert _scan_line("ALTER ROLE dlr_writer WITH " + "pass" + "word '<" + "pass" + "word>';") == []

    missing = [path for path in PHASE5_TEXT_FILES if not os.path.isfile(os.path.join(_REPO, path))]
    assert missing == [], "listed phase files are missing: " + ", ".join(missing)

    findings = []
    for path in PHASE5_TEXT_FILES:
        with open(os.path.join(_REPO, path), encoding="utf-8", errors="replace") as fh:
            for number, line in enumerate(fh, start=1):
                for name in _scan_line(line):
                    findings.append(f"{path}:{number}:{name}")
    assert findings == [], "secret-shaped text in phase files: " + ", ".join(findings)
