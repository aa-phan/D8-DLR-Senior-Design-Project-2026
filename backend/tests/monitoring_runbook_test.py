"""
The runbook's Phase 6 sections stay true to the tools they describe (production-pipeline Phase 6,
E2E-02, E2E-03; D-09, D-13, D-14, D-15; threats T-06-25, T-06-26).

docs/data-science/decisions/dlr_live_runbook.md is where an operator learns to run, read, pause and
answer the freshness alarm, to run and tear down the soak and to run the permission re-check after
2026-10-30. Those instructions name scripts, flags, a job and thresholds that live elsewhere, so
they can rot silently. These tests read the runbook as text and fail when a name, flag, job name or
threshold drifts from the code or the owner SQL files, and when a line of the runbook looks like a
secret or a project address (placeholders only, D-10).

Nothing here touches the network, a database or a `.env` file. The flag check runs each script's
own `--help` in a subprocess.
"""

import os
import re
import subprocess
import sys

import e2e_soak_report
import latest_rating_contract
import secret_scan_test as scan

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_RUNBOOK = os.path.join(_REPO, "docs", "data-science", "decisions", "dlr_live_runbook.md")
_OPS = os.path.join(_REPO, "supabase", "ops")

SECTION_14 = "## 14. Freshness alarm (permanent)"
SECTION_15 = "## 15. Soak monitoring (Phase 6)"
SECTION_16 = "## 16. Permission re-check after 2026-10-30"

OWNER_SQL = ("soak_cron_schedule.sql", "soak_cron_unschedule.sql", "soak_probe_smoke.sql",
             "verify_monitoring.sql", "verify_exposure.sql")


def _runbook() -> str:
    with open(_RUNBOOK, encoding="utf-8") as fh:
        return fh.read()


def _section(fragment: str) -> str:
    """The body of the `## ` section whose heading contains `fragment`."""
    for part in re.split(r"(?m)^## ", _runbook())[1:]:
        if fragment in part.splitlines()[0]:
            return part
    raise AssertionError(f"no '## ' section with {fragment!r} in its heading")


def _flat(text: str) -> str:
    """The text on one line, so a phrase the runbook wraps across two lines is still found."""
    return " ".join(text.split())


def _owner_sql(name: str) -> str:
    with open(os.path.join(_OPS, name), encoding="utf-8") as fh:
        return fh.read()


def test_runbook_has_the_phase6_sections():
    text = _runbook()
    positions = []
    for heading in (SECTION_14, SECTION_15, SECTION_16):
        assert len(re.findall("(?m)^" + re.escape(heading) + "$", text)) == 1, heading
        positions.append(text.index(heading))
    assert positions == sorted(positions)
    assert text.index("## 13. Checking a window") < positions[0]
    for name in OWNER_SQL:
        assert os.path.isfile(os.path.join(_OPS, name)), name


def test_alarm_section_states_the_rule_and_the_response():
    section = _flat(_section("14. Freshness alarm"))
    lowered = section.lower()

    for needle in ("rpc/assert_fresh", "apikey", "every 15 minutes", "2 failures", "recovery", "disabled", "25",
                   "owner's cron-job.org account", "pipeline_run", "gh run list", "is_stale",
                   "DLR freshness alarm", "GET", "UTC", "30 s", "never the secret key", "105-120 minutes"):
        assert needle in section, needle
    assert f"{latest_rating_contract.STALE_AFTER_MINUTES} minutes" in section
    # permanent, and how to pause it (D-13)
    assert "stays on after the soak" in lowered
    assert "to pause" in lowered or "pause the alarm" in lowered
    assert "resume" in lowered
    # what to do when it fires, in order (D-15): the run log, then Actions, then the consumer flag
    fires = lowered.index("when it fires")
    order = [lowered.index(text, fires) for text in ("pipeline_run", "gh run list", "is_stale")]
    assert order == sorted(order)
    assert "e2e_verify_readonly.py --check-read" in section
    assert "section 11" in lowered
    # the auto-disable and its recovery step (Pitfall 13)
    assert "more than 25" in section and "re-enable" in lowered
    # the two existing jobs are never touched
    assert "never changed" in lowered or "never modified" in lowered


def test_pause_section_pauses_the_alarm_too():
    text = _runbook()
    section = _flat(_section("6. Pause and resume")).lower()

    assert "pausing the pipeline also pauses the freshness alarm (section 14)" in section
    assert "more than 25" in section
    assert "resuming re-enables both" in section
    assert "alarm job is enabled" in section
    assert "Disable workflow" in _flat(_section("6. Pause and resume"))
    # section 11 and section 6 point at the alarm, not at an unwritten "Phase 6 check"
    assert "Phase 6's freshness check" not in text
    assert "the freshness alarm (section 14)" in _flat(_section("11. Failure modes"))


def test_soak_section_names_the_scripts_and_teardown():
    section = _flat(_section("15. Soak monitoring"))
    lowered = section.lower()

    for name in OWNER_SQL[:4]:
        assert name in section, name
    for needle in ("dlr-soak-freshness", "Cron", "e2e_soak_report.py", "--mode dry", "--mode soak",
                   "annotations.json", "--check-writes", "backfill", "--annotations", "ops.freshness_log",
                   "git fetch"):
        assert needle in section, needle
    assert "no backfill load and no past-slot re-run" in lowered
    # teardown: the log job goes, the alarm stays, the log rows stay
    teardown = lowered.index("teardown")
    assert section.index("soak_cron_unschedule.sql", teardown) > teardown
    after = lowered[teardown:]
    assert "the alarm stays" in after
    assert "remaining_jobs" in after
    assert "no retention" in after
    # D-08: a deploy is derived, shown as context and never excuses a breach; the soak is not restarted
    assert "never excuses" in lowered
    assert "not paused or restarted" in lowered
    # the thresholds the report applies
    assert f"{e2e_soak_report.SOAK_MIN_HOURS} h" in section
    assert f"{2 * e2e_soak_report.PROBE_INTERVAL_MIN + 1} minutes" in section
    assert f"{e2e_soak_report.LATE_RUN_MIN} minutes" in section


def test_recheck_section_lists_the_five_checks():
    section = _section("16. Permission re-check")

    for needle in ("2026-10-31", "--check-read", "--check-hidden", "--check-writes", "verify_exposure.sql",
                   "consumers_cannot_write", "supabase_smoke.py", "--report", "06-09", "T-04-22", "discrepancy"):
        assert needle in section, needle
    rows = [line for line in section.splitlines() if line.startswith("|") and not set(line) <= set("|- ")]
    body = rows[1:]  # the header row names the columns
    assert len(body) == 5
    for row in body:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        assert len(cells) == 3, row
        assert all(cells), row
        assert len(cells[2].split()) >= 8, f"the meaning in {row!r} is not a plain-English sentence"


def _commands(text: str) -> list:
    """Every command in a fenced bash block, with its backslash continuations joined."""
    blocks, current, language = [], None, None
    for line in text.splitlines():
        if line.startswith("```"):
            if current is None:
                current, language = [], line[3:].strip()
            else:
                if language in ("bash", "sh"):
                    blocks.append("\n".join(current))
                current = None
        elif current is not None:
            current.append(line)
    commands = []
    for block in blocks:
        joined = re.sub(r"\\\n\s*", " ", block)
        commands += [line.strip() for line in joined.splitlines() if line.strip()]
    return commands


def _help_flags(script: str, *sub) -> set:
    env = dict(os.environ, PYTHONPATH=os.path.join(_REPO, "backend"))
    done = subprocess.run([sys.executable, os.path.join(_REPO, "backend", script), *sub, "--help"],
                          capture_output=True, text=True, timeout=120, cwd=_REPO, env=env)
    assert done.returncode == 0, done.stderr[-300:]
    return set(re.findall(r"--[a-z][a-z0-9-]*", done.stdout)) - {"--help"}


def test_runbook_names_match_the_tools():
    text = _runbook()

    # the job name and the schedule come from the owner SQL, not from memory
    job = re.search(r"cron\.schedule\('([^']+)',\s*'([^']+)'", _owner_sql("soak_cron_schedule.sql"))
    assert job, "soak_cron_schedule.sql no longer calls cron.schedule('<name>', '<cron>', ...)"
    name, cron = job.groups()
    assert name in _section("15. Soak monitoring")
    assert name in _owner_sql("soak_cron_unschedule.sql")
    assert cron == f"*/{e2e_soak_report.PROBE_INTERVAL_MIN} * * * *"
    assert "every five minutes" in _section("15. Soak monitoring")

    # every flag a command in the runbook passes exists in that script's own argparse parser
    seen = {"e2e_soak_report.py": set(), "e2e_verify_readonly.py": set(), "supabase_smoke.py": set()}
    for command in _commands(text):
        for script in seen:
            if script not in command and not (script == "supabase_smoke.py" and "supabase_smoke.main" in command):
                continue
            if script == "e2e_soak_report.py":
                sub = "export" if " export " in command else "report"
                allowed = _help_flags(script, sub)
            elif script == "e2e_verify_readonly.py":
                allowed = _help_flags(script)
            else:
                allowed = _help_flags(script)
            for flag in re.findall(r"--[a-z][a-z0-9-]*", command):
                assert flag in allowed, f"{script}: the runbook shows {flag}, which the script does not have"
                seen[script].add(flag)
    # the runbook really exercises each script (a test with nothing to check proves nothing)
    assert {"--mode", "--since", "--until", "--out-dir", "--in-dir", "--annotations", "--out"} <= seen["e2e_soak_report.py"]
    assert {"--check-read", "--check-hidden", "--check-writes"} <= seen["e2e_verify_readonly.py"]
    assert "--report" in seen["supabase_smoke.py"]

    # the numbers in the prose are the numbers in the code
    alarm = _section("14. Freshness alarm")
    assert str(latest_rating_contract.STALE_AFTER_MINUTES) in alarm
    assert e2e_soak_report.DEFAULT_MAX_AGE_MIN == latest_rating_contract.STALE_AFTER_MINUTES


def test_runbook_has_no_secret_shaped_lines():
    # control: the scan fires on lines assembled at run time, so it cannot pass by matching nothing
    tail = "A1b2C3d4E5f6G7h8I9j0K1l2"
    assert scan._scan_line("key " + "sb_" + "publishable_" + tail)
    assert scan._scan_line("url https://" + "a" * 20 + "." + "supa" + "base" + ".co/rest/v1")
    assert scan._scan_line("token " + "ey" + "J" + tail + "." + "ey" + "J" + tail + "." + tail)

    findings = []
    for number, line in enumerate(_runbook().splitlines(), start=1):
        for found in scan._scan_line(line):
            findings.append(f"{number}:{found}")
    assert findings == [], "secret-shaped text in the runbook: " + ", ".join(findings)
    # the alarm and re-check sections use placeholders for the two values (D-10)
    for heading in (SECTION_14, SECTION_16):
        body = _section(heading.removeprefix("## "))
        assert "<SUPABASE_URL>" in body or "SUPABASE_URL" in body
        assert "<SUPABASE_PUBLISHABLE_KEY>" in body or "SUPABASE_PUBLISHABLE_KEY" in body
