"""
VIEW-03 (and VIEW-01 reader documentation): the DEF-01 hand-over text of the pandapower-solver
workstream, phase 6, plan 06-03; decisions D-04, D-06, D-07, D-08.

`docs/data-science/decisions/grid_study_def01_replacement.md` holds three blocks of text for the dashboard
owner to commit on branch `feature/dashboard`: each block quotes the current text of that branch and gives
its replacement. This file pins the tracked copy, never the `.planning` pointer, so the checks survive a
clean branch that filters `.planning` commits. The branch check reads the local ref
`origin/feature/dashboard` only: it never fetches, checks out or writes.

The branch check couples this repository to another team's branch, so it is skipped unless the environment
asks for it: set `DEF01_EXPECT` to `current` or `committed`, or `DEF01_REQUIRE_BRANCH=1` (which also turns a
missing ref into a failure instead of a skip). Files are opened in text mode and never pinned by their
bytes (the checkout has core.autocrlf true). Nothing here reads `data/private`.
"""

import datetime
import os
import re
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_REPO = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import grid_study_contract as contract  # noqa: E402

PLACEHOLDER = "{{APPLY_DATE}}"
MIGRATION = "20261126200000_latest_grid_study_per_solver.sql"
BRANCH_REF = "origin/feature/dashboard"
_DASHBOARD = ".planning/workstreams/software-dashboard"
BLOCK_PATHS = {
    "A": _DASHBOARD + "/REQUIREMENTS.md",
    "B": _DASHBOARD + "/STATE.md",
    "C": _DASHBOARD + "/docs/DASHBOARD-REQUIREMENTS.md",
}

_FENCE = re.compile(r"^```text[ \t]*\n(.*?)^```[ \t]*$", re.M | re.S)
_BLOCK_HEAD = re.compile(r"^## Block ([ABC])\b.*$", re.M)
_HEADER_ROW = re.compile(r"^\| \*\*([^*|]+)\*\* \| (.*) \|[ \t]*$", re.M)


def _read(*parts):
    with open(os.path.join(_REPO, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


def _doc():
    return _read("docs", "data-science", "decisions", "grid_study_def01_replacement.md")


def _norm(text):
    """Collapse every run of whitespace to one space (the branch wraps lines; the document may not)."""
    return " ".join(text.split())


def _header(text=None):
    """The rows of the header table as a dict of label to value."""
    return {m.group(1).strip(): m.group(2).strip() for m in _HEADER_ROW.finditer(text or _doc())}


def _blocks(text=None):
    """Dict of 'A', 'B', 'C' to (current text, replacement text): the first and second fenced text block
    of each `## Block` section."""
    text = text or _doc()
    heads = list(_BLOCK_HEAD.finditer(text))
    assert [h.group(1) for h in heads] == ["A", "B", "C"], "the document needs Block A, B and C in order"
    out = {}
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        fences = _FENCE.findall(text[head.end():end])
        assert len(fences) >= 2, "Block %s needs a current-text and a replacement-text block" % head.group(1)
        out[head.group(1)] = (fences[0].strip("\n"), fences[1].strip("\n"))
    return out


def _branch_file(path):
    """The text of `path` on the local ref origin/feature/dashboard, or None when the ref is missing."""
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", BRANCH_REF + "^{commit}"],
        cwd=_REPO, capture_output=True, text=True, encoding="utf-8")
    if probe.returncode != 0:
        return None
    shown = subprocess.run(
        ["git", "show", BRANCH_REF + ":" + path],
        cwd=_REPO, capture_output=True, text=True, encoding="utf-8")
    assert shown.returncode == 0, "git show %s:%s failed: %s" % (BRANCH_REF, path, shown.stderr.strip())
    return shown.stdout


def test_tracer_the_replacement_names_the_view_every_column_and_the_reading_rules():
    blocks = _blocks()
    assert os.path.isfile(os.path.join(_REPO, "supabase", "migrations", MIGRATION)), MIGRATION

    # every current text is quoted, and starts where the branch text starts
    starts = {"A": "- **DEF-01**:", "B": "- 2026-11-16: DEF-01 unblocked.", "C": "**Unblocked on 2026-11-16.**"}
    for key, (current, replacement) in blocks.items():
        assert current.strip(), "Block %s: the current text is empty" % key
        assert current.startswith(starts[key]), "Block %s: the current text starts elsewhere" % key
        assert "latest_grid_study" in replacement, "Block %s: the view is not named" % key
        assert MIGRATION in replacement, "Block %s: the migration is not named" % key

    # Block A: all 20 columns, in contract order, as one backticked list
    a = _norm(blocks["A"][1])
    assert len(contract.COLUMNS) == 20
    column_list = ", ".join("`%s`" % name for name in contract.COLUMNS)
    assert column_list in a, "Block A: the 20 columns are not listed in contract order"
    for solver in contract.SOLVERS:
        assert "`%s`" % solver in a, "Block A: solver %s is not named" % solver
    assert "one row per city per solver" in a
    assert re.search(r"filter on\s+`solver`", a, re.I), "Block A: it must say to filter on `solver`"
    assert "preliminary" in a.lower()
    for phrase in ("IEEE 39-bus", "not a utility network", "90 minutes", "paused", "Blockers cleared", "(ch. 10)"):
        assert phrase in a, "Block A lacks %r" % phrase
    assert str(contract.STALE_AFTER_MINUTES) + " minutes" in a

    # Block B: a dated bullet, the date a placeholder or a real date
    b_first = blocks["B"][1].splitlines()[0]
    assert re.match(r"^- (?:\{\{APPLY_DATE\}\}|\d{4}-\d\d-\d\d): ", b_first), b_first
    b = _norm(blocks["B"][1])
    assert "filter" in b and "`solver`" in b and "preliminary" in b.lower() and "paused" in b

    # Block C
    c = _norm(blocks["C"][1])
    for phrase in ("one row per city per solver", "solver", "pandapower", "90 minutes", "paused", "rest-api.md"):
        assert phrase in c, "Block C lacks %r" % phrase
    assert "preliminary" in c.lower()


def test_dashboard_branch_holds_the_current_or_the_replacement_text():
    expect = os.environ.get("DEF01_EXPECT", "").strip().lower()
    require = os.environ.get("DEF01_REQUIRE_BRANCH", "") == "1"
    if not expect and not require:
        pytest.skip("branch-state check is off by default: it reads another team's branch; "
                    "set DEF01_EXPECT=current|committed or DEF01_REQUIRE_BRANCH=1 to run it")
    assert expect in ("", "current", "committed"), "DEF01_EXPECT must be current or committed"

    files = {key: _branch_file(path) for key, path in BLOCK_PATHS.items()}
    if any(text is None for text in files.values()):
        if require:
            pytest.fail("DEF01_REQUIRE_BRANCH=1 but the local ref %s is missing" % BRANCH_REF)
        pytest.skip("the local ref %s is missing; run `git fetch origin feature/dashboard` (read-only)" % BRANCH_REF)

    doc = _doc()
    blocks = _blocks(doc)
    found = {}
    for key, (current, replacement) in blocks.items():
        haystack = _norm(files[key])
        found[key] = (_norm(current) in haystack, _norm(replacement) in haystack)

    def problems(state):
        out = []
        for key, (has_current, has_replacement) in found.items():
            if state == "current":
                if not has_current:
                    out.append("Block %s: the current text is no longer on the branch" % key)
                if has_replacement:
                    out.append("Block %s: the replacement is already on the branch" % key)
            else:
                if not has_replacement:
                    out.append("Block %s: the replacement is not on the branch" % key)
                if key != "B" and has_current:
                    out.append("Block %s: the old text is still on the branch" % key)
                if key == "B" and not has_current:
                    out.append("Block B: the kept 2026-11-16 line is gone from the branch")
        if state == "committed" and PLACEHOLDER in doc:
            out.append("the document still holds %s; fill the apply date first" % PLACEHOLDER)
        return out

    state_problems = {state: problems(state) for state in ("current", "committed")}
    actual = [state for state, found_problems in state_problems.items() if not found_problems]
    if expect:
        assert not state_problems[expect], "branch is not in state %s: %s" % (expect, "; ".join(state_problems[expect]))
    else:
        assert actual, "the branch is in neither state: current (%s) / committed (%s)" % (
            "; ".join(state_problems["current"]), "; ".join(state_problems["committed"]))
