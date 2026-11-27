---
phase: 06-dashboard-read-access-and-def-01
plan: 03
subsystem: docs
tags: [def-01, hand-over, dashboard, rest-api, text-pins, pytest]
status: complete

requires:
  - phase: 06-dashboard-read-access-and-def-01
    provides: plan 06-01's per-solver latest_grid_study view, migration 20261126200000_latest_grid_study_per_solver.sql and grid_study_contract.SOLVERS and MAX_ROWS
provides:
  - tracked DEF-01 hand-over document with three blocks (current text quoted verbatim, replacement text) for the dashboard owner
  - text and branch-state tests of that document, checked against the 20-column contract
  - REST reference describing latest_grid_study as one row per city per solver
affects: [06-04 owner runbook and live apply (fills the apply-date placeholder), 06-05 hand-over to the dashboard owner]

actuals:
  tokens: 7400
  tasks: 2
  commits: 4
plan_head_before: 8fdee6dfe75431a5ca799450d287e73b268398e0
plan_head_after: 1603291bca14056064384c43c40eebefea7514b9

tech-stack:
  added: []
  patterns:
    - "hand-over text pinned against the code contract (Block A must contain contract.COLUMNS as one ordered backticked list) and against the other team's branch read with git show of a local ref"
    - "apply-date state machine tested by a helper that returns problems, with teeth run on edited copies of the real document"

key-files:
  created:
    - docs/data-science/decisions/grid_study_def01_replacement.md
    - backend/tests/grid_study_def01_text_test.py
    - .planning/workstreams/pandapower-solver/phases/06-dashboard-read-access-and-def-01/06-DEF01-REPLACEMENT.md
  modified:
    - docs/integration/rest-api.md

key-decisions:
  - "Branch-state test is skipped by default and runs only with DEF01_EXPECT or DEF01_REQUIRE_BRANCH=1 (orchestrator requirement; see Deviations)"
  - "Blocks quote the current branch text verbatim and the test compares whitespace-normalised, so a re-wrapped line on the branch does not matter but an edit does"
  - "Every pandapower-is-running statement in the replacements is tied to {{APPLY_DATE}} (since then / since); no date is written before the apply"

requirements-completed: []  # VIEW-03 stays Pending until the dashboard owner commits the text (plan 06-05); VIEW-01 untouched (orchestrator instruction)

duration: about 30 min
completed: 2026-11-26
---

# Phase 6 Plan 03: DEF-01 hand-over text and REST reference Summary

**A tracked, tested hand-over document gives the dashboard owner an exact replacement for the three DEF-01 statements (REQUIREMENTS.md bullet, STATE.md line, chapter 10 of DASHBOARD-REQUIREMENTS.md), listing all 20 `latest_grid_study` columns in contract order and carrying an apply-date placeholder until the owner's live apply; `docs/integration/rest-api.md` now describes one row per city per solver.**

## What was built

- **`docs/data-science/decisions/grid_study_def01_replacement.md`**: header table (Status `Not handed over yet`, Applied live `{{APPLY_DATE}}`, From, To, Hand over after, Written against `origin/feature/dashboard` at 1f531f8), "How to apply", Block A, Block B, Block C, "Confirmation" (git fetch, three `git show | grep` commands, the branch test with `DEF01_REQUIRE_BRANCH=1 DEF01_EXPECT=committed`), and "Why the text says what it says" (each fact with its source). The placeholder `{{APPLY_DATE}}` occurs 6 times. Block A's replacement names the view, the migration, one row per city per solver, "filter on `solver`", the 20 columns in contract order, preliminary values on the IEEE 39-bus case, the 90 minute rule and the paused PSS/E job, and ends "(ch. 10)". Block B adds one dated bullet after the kept 2026-11-16 line. Block C replaces the two paragraphs of chapter 10 and keeps the link to `rest-api.md`.
- **`06-DEF01-REPLACEMENT.md`** in the phase directory: the one-line pointer.
- **`backend/tests/grid_study_def01_text_test.py`** (320 lines, 6 tests): tracer (blocks parsed, migration file exists, Block A holds `contract.COLUMNS` as one ordered list and the reading rules, Blocks B and C hold theirs); branch state; apply date is the placeholder or one real date not before 2026-11-26 and not after today, with the Status lifecycle (teeth on seven edited copies); no new date before the apply (only 2026-11-11, 2026-11-12, 2026-11-16 allowed); no credential shape, 64-hex string or `data/private` path (six shapes, each with a sample assembled from pieces); the REST doc pins.
- **`docs/integration/rest-api.md`**: endpoint row, the intro sentence, the "Where the numbers come from", "How often" and "Solvers" bullets, and the `solver` row of the columns table; prose only, 21 `## ` headings kept, line 137 untouched, the three sentences that said "every row today is psse" / "a later release adds pandapower" / "in a later release" removed. No date is stated for the pandapower switch.

## Verification (Windows, Git Bash, .venv)

- `DEF01_REQUIRE_BRANCH=1 DEF01_EXPECT=current` on `grid_study_def01_text_test.py` and `rest_api_doc_test.py`: 25 passed, nothing skipped (6 + 19). The quoted current texts match `origin/feature/dashboard` at 1f531f80854c8ea20feb72eb7b420749766091ac today.
- Default run (no environment variables): 24 passed, 1 skipped (the branch-state test, with its reason printed).
- `DEF01_EXPECT=committed` fails as it should today, naming Blocks A, B and C and the unfilled placeholder.
- `day_ahead_consumer_docs_test.py` (reads the same REST doc): 10 passed.
- Acceptance: `grep -c "{{APPLY_DATE}}"` 6 (>= 4); pointer holds `grid_study_def01_replacement.md`; migration name in `rest-api.md` 1 line (baseline 0); `^## ` count 21 (baseline 21); 64-hex matches in the document 0.
- `git log origin/feature/dashboard -1 --format=%H` printed 1f531f80854c8ea20feb72eb7b420749766091ac before and after; this checkout made no commit, push or edit on that branch and never fetched.
- File-scope gate for 06-03 exits 0 after the commits; `private_leak_scan --staged` exited 0 before all four commits.

## TDD gates

RED `b440ea4` (tracer and branch-state tests fail: document missing), GREEN `1682e3d` (document and pointer); RED `ed2b70a` (REST pin fails on the old prose; the other three new tests pass at once because the Task 1 document already satisfied them), GREEN `1603291` (REST prose). Commits measured from the plan ledger base 8fdee6d: 4.

## Deviations from Plan

**1. [Orchestrator requirement] The branch-state test skips by default.** The plan's default is to run the branch check whenever the local ref exists (and to fail on a missing ref only with `DEF01_REQUIRE_BRANCH=1`). Because the test would turn this repository's default suite red whenever the dashboard owner edits their branch, it now skips unless `DEF01_EXPECT` (`current` or `committed`) or `DEF01_REQUIRE_BRANCH=1` is set; when set, the plan's behaviours hold unchanged (`DEF01_EXPECT` demands the state; unset accepts either; a missing ref skips, or fails with `DEF01_REQUIRE_BRANCH=1`). Consequences for the acceptance criteria: a default run is "24 passed, 1 skipped" (not 25 passed); the plan's strict verify, which sets both variables, still gives 25 passed with nothing skipped. A default skip is expected, not a failure. The hand-over document's "Confirmation" section names the variables to set.

**2. [Acceptance count] No other difference.** Placeholder count is 6 (plan: at least 4).

Otherwise the plan was executed as written. No auto-fixes were needed.

## Known issues not touched

- The Windows-only failures named by the orchestrator (three CRLF byte-hash tests, `test_is_provisional_reads_the_real_labels`, and `pandapower_cli_test` and `pandapower_ingest_test`) were not run or changed.
- `.planning/workstreams/pandapower-solver/state.json` is modified and `milestone.lock` is untracked from before this plan; both left uncommitted as instructed.
- The Status row of the hand-over document stays `Not handed over yet`; plan 06-04 fills the placeholder after the owner's live apply, and plan 06-05 covers the hand-over. VIEW-03 stays Pending.

## Known Stubs

The `{{APPLY_DATE}}` placeholder is intentional (decision D-08): it must not be replaced before the owner applies the migration live. Resolved by plan 06-04. No other stubs.

## Threat Flags

None. The two documents and the test hold names and commands only; the test reads the local ref with `git show` and never fetches or writes.

## Self-Check: PASSED

- FOUND: docs/data-science/decisions/grid_study_def01_replacement.md, backend/tests/grid_study_def01_text_test.py, 06-DEF01-REPLACEMENT.md, docs/integration/rest-api.md
- FOUND commits b440ea4, 1682e3d, ed2b70a and 1603291 on feature/pandapower-solver (4 commits measured from the plan ledger base 8fdee6d)
