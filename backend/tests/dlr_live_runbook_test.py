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

import glob
import os
import re
import subprocess
import sys

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


def test_runbook_section_17_matches_the_day_ahead_stage_constants_and_tools():
    # Phase 8 (08-06, T-08-19): the day-ahead section quotes the stage's constants, flags and tool
    # names, so a change in the code that the runbook does not follow fails here.
    section = _section(_runbook(), "Day-ahead forecast stage")

    assert f"`DAY_AHEAD_CITY_TIMEOUT_S` = {dlr_live_run.DAY_AHEAD_CITY_TIMEOUT_S} s" in section
    assert f"`DAY_AHEAD_MIN_START_S` = {dlr_live_run.DAY_AHEAD_MIN_START_S} s" in section
    assert f"{dlr_live_run.DAY_AHEAD_SHARED_BUDGET_S} s" in section
    for needle in (
        "--no-day-ahead",
        "pipeline_run.day_ahead",
        "day_ahead_verify.py",
        "DAY_AHEAD_REFIT_VERSION",
        "weather run's age",
    ):
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


def test_runbook_section_14_states_the_day_ahead_alarm_clause():
    # Phase 8 (08-10, D-12): the same alarm URL also fails for a stalled day-ahead feed.
    section = " ".join(_section(_runbook(), "Freshness alarm").split())

    for needle in (
        "day_ahead_late",
        "day_ahead_armed",
        "armed by the first value",
        "12 hours",
        "pipeline_run.day_ahead",
        "no new cron job",
        "pausing the pipeline pauses both",
        "hourly catch-up",
    ):
        assert needle in section, needle


def _bash_commands(text: str) -> list:
    """Every command in a fenced bash block, with its backslash continuations joined."""
    commands, current, language = [], None, None
    for line in text.splitlines():
        if line.startswith("```"):
            if current is None:
                current, language = [], line[3:].strip()
            else:
                if language in ("bash", "sh"):
                    joined = re.sub(r"\\\n\s*", " ", "\n".join(current))
                    commands += [row.strip() for row in joined.splitlines() if row.strip()]
                current = None
        elif current is not None:
            current.append(line)
    return commands


def test_permission_recheck_states_the_day_ahead_surface():
    # Phase 8 (08-10, D-09, D-17): section 16 describes the public surface that exists after the expose
    # migration, so the owner compares like with like.
    section = _section(_runbook(), "Permission re-check")
    flat = " ".join(section.split())
    rows = [line for line in section.splitlines() if line.startswith("|") and not set(line) <= set("|- ")]
    body = {}
    for row in rows[1:]:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        body[cells[0]] = cells
    assert len(rows[1:]) == 5, "the table keeps exactly five rows"

    permission_list = " ".join(body["Database permission list"])
    for name in ("city_rating", "latest_rating", "day_ahead_forecast", "day_ahead_upcoming", "day_ahead_status"):
        assert name in permission_list, name
    assert "29" in permission_list and "assert_fresh" in permission_list

    writes = " ".join(body["Writes"])
    assert "city_rating" in writes and "latest_rating" in writes and "day-ahead check" in writes
    assert "day_ahead" not in writes.replace("day-ahead", "")  # --check-writes does not probe the day-ahead objects

    smoke = " ".join(body["Writer smoke"])
    assert "run log" in smoke and "pipeline_run" in smoke and "city_rating" in smoke
    assert "verify_exposure.sql" in smoke and "day-ahead" in smoke

    for needle in ("day_ahead_verify.py --check-rest", "08-11", "06-09", "Since Phase 8",
                   "expected since 08-11", "not a discrepancy", "08-11-live-checks.json", "08-11-SUMMARY.md"):
        assert needle in flat, needle
    assert "either table" not in flat

    commands = [c for c in _bash_commands(section) if "day_ahead_verify.py" in c]
    assert len(commands) == 1 and "--check-rest" in commands[0] and "<RECHECK_DAY_AHEAD_FILE>" in commands[0]
    done = subprocess.run(
        [sys.executable, os.path.join(_REPO, "backend", "day_ahead_verify.py"), "--help"],
        capture_output=True, text=True, timeout=120, cwd=_REPO,
        env=dict(os.environ, PYTHONPATH=os.path.join(_REPO, "backend")))
    assert done.returncode == 0, done.stderr[-300:]
    allowed = set(re.findall(r"--[a-z][a-z0-9-]*", done.stdout))
    flags = re.findall(r"--[a-z][a-z0-9-]*", commands[0])
    assert flags and set(flags) <= allowed, set(flags) - allowed


_PRIVILEGE_ORDER = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


def _writer_grants_from_the_migrations() -> dict:
    """{object: privileges} for every table-privilege grant to dlr_writer in supabase/migrations/*.sql.

    SQL `--` comments are removed first; the text inside `do $$ ... $$` blocks is read like any other
    statement. A schema, function or sequence grant is not a table grant and is skipped. Any revoke
    from dlr_writer fails the test, because the runbook would then state a privilege that is gone.
    """
    grants = {}
    files = sorted(glob.glob(os.path.join(_REPO, "supabase", "migrations", "*.sql")))
    assert files, "no migrations found"
    for path in files:
        with open(path, encoding="utf-8") as fh:
            text = re.sub(r"--[^\n]*", "", fh.read())
        assert not re.search(r"(?is)\brevoke\b[^;]*?\bfrom\b[^;]*\bdlr_writer\b", text), (
            f"{os.path.basename(path)} revokes from dlr_writer; update the runbook row and this test")
        for match in re.finditer(r"(?is)\bgrant\s+([^;]+?)\s+on\s+([^;]+?)\s+to\s+([^;]+?)\s*;", text):
            privileges, target, grantees = match.groups()
            if "dlr_writer" not in [g.split()[0].strip('"') for g in grantees.split(",") if g.split()]:
                continue
            target = " ".join(target.split())
            if re.match(r"(?i)(schema|function|procedure|sequence|database|type|domain|language)\b", target):
                continue
            target = re.sub(r"(?i)^table\s+", "", target)
            privs = {p.strip().upper() for p in privileges.split(",")}
            for obj in (o.strip() for o in target.split(",")):
                name = obj[len("public."):] if obj.startswith("public.") else obj
                grants.setdefault(name, set()).update(privs)
    return grants


def _privilege_phrase(privileges) -> str:
    ordered = [p for p in _PRIVILEGE_ORDER if p in privileges]
    assert set(ordered) == set(privileges), privileges
    if len(ordered) == 1:
        return ordered[0]
    return ", ".join(ordered[:-1]) + " and " + ordered[-1]


def test_secrets_section_states_the_writer_grants_from_the_migrations():
    # Phase 8 (08-10): the SUPABASE_DB_URL row says what dlr_writer can do, and a test reads the
    # migrations for the truth, so a later grant that the row does not mention fails here.
    grants = _writer_grants_from_the_migrations()
    assert grants == {
        "city_rating": {"SELECT", "INSERT", "UPDATE"},
        "pipeline_run": {"SELECT", "INSERT", "UPDATE"},
        "ops.freshness_log": {"SELECT"},
        "day_ahead_forecast": {"SELECT", "INSERT"},
    }, grants

    section = _section(_runbook(), "Secrets")
    rows = [line for line in section.splitlines() if line.startswith("| ") and "SUPABASE_DB_URL" in line.split("|")[1]]
    assert len(rows) == 1
    cells = [c.strip() for c in rows[0].strip().strip("|").split("|")]
    assert len(cells) == 2
    detail = cells[1]
    assert detail.startswith("Phase 4's writer connection: the session pooler URL (port 5432) for the `dlr_writer` role")
    assert "the two tables" not in detail and "nothing else" not in detail
    for name in grants:
        assert "`%s`" % name in detail, name
    # each clause starts with the privilege phrase and names the objects that hold exactly that set
    clauses = [c.strip() for c in detail.split("define them:", 1)[1].split(";")]
    by_phrase = {}
    for name, privileges in grants.items():
        by_phrase.setdefault(_privilege_phrase(privileges), []).append(name)
    for phrase, names in by_phrase.items():
        matching = [c for c in clauses if c.startswith(phrase + " on ")]
        assert len(matching) == 1, (phrase, clauses)
        for name in names:
            assert "`%s`" % name in matching[0], (phrase, name)
        for other in grants:
            if other not in names:
                assert "`%s`" % other not in matching[0], (phrase, other)
    assert "no UPDATE" in detail and "no DELETE" in detail
