---
phase: 05-scheduled-live-runs
fixed_at: 2026-10-26T00:00:00Z
review_path: .planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-REVIEW.md
iteration: 1
findings_in_scope: 11
fixed: 9
skipped: 2
status: partial
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-10-26
**Source review:** .planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 11 (IN-01 to IN-11, scope `all`; the review had no critical or warning items left)
- Fixed: 9 (IN-11 only in part, see below)
- Skipped: 2 (IN-03, IN-08)

This report replaces the earlier one, which recorded the WR-01 to WR-03 pass.

**Verification** ran in the isolated review-fix worktree (`.claude/worktrees/rf-05-...`), using the main
checkout's `.venv` Python with `PYTHONPATH=backend`. Targeted tests ran after every fix. The full
`backend/tests` suite ran once at the end, on the final commit: 1746 passed, 48 skipped, 0 failed. The
worktree was fast-forwarded into `main` afterwards, so the same commits are on `main`.

## Fixed Issues

### IN-01: A child that fails after its row was written is recorded as "no rating row"

**Files modified:** `docs/data-science/decisions/dlr_live_runbook.md`, `docs/data-science/schema/city_rating_v1.md`
**Commit:** 1d40308
**Applied fix:** Took the doc-wording option. The runbook's outcome table now says "none confirmed" for `error` and `timeout`, with a paragraph explaining that a child can exit non-zero after it stored its row and that the slot is red either way. The schema doc's `cities_failed` and `timeout` text says "no confirmed row" and states the same caveat. No code change.

### IN-02: Provider errors and sources of a failed city are dropped

**Files modified:** `backend/dlr_live_run.py`, `backend/tests/dlr_live_run_test.py`
**Commit:** ecc7bec
**Applied fix:** `classify` now reads `provider_errors` (through `_redact_counts`) and `sources` from any `--output` file the child left, before the failure branches, so a failed city's `pipeline_run` entry keeps them. Non-dict values are ignored so classification cannot raise. The `ok` branch no longer sets them separately. New test covers a failed city with output (redacted counts kept), no output and a timeout (nothing invented), and malformed fields.

### IN-04: `--end` accepts a future slot, and `--timeout-s` is unchecked

**Files modified:** `backend/dlr_live_run.py`, `backend/tests/dlr_live_run_test.py`, `docs/data-science/decisions/dlr_live_runbook.md`
**Commit:** e3731fd
**Applied fix:** `_end_arg` rejects an end later than now (UTC) and `--timeout-s` takes a new `_positive_int` type; both are argparse usage errors (exit 2). The runbook's manual-run paragraph notes that a future end is refused. New test covers the boundary (now itself is allowed), a future value, a bad format, and `--timeout-s` of 0, -5 and text.

### IN-05: `--start ""` in the window check raises AttributeError instead of a usage error

**Files modified:** `backend/dlr_live_window_check.py`, `backend/tests/dlr_live_window_check_test.py`
**Commit:** 6340c32
**Applied fix:** `_hour_arg` raises `ArgumentTypeError("--start is required, e.g. ...")` when `_ts` returns None. New parametrized test checks that `""`, whitespace, garbage and an off-the-hour value all exit with code 2 and name `--start`.

### IN-06: Step-summary cell escaping can be defeated, and child stdout can carry workflow commands

**Files modified:** `backend/dlr_live_run.py`, `backend/tests/dlr_live_run_test.py`
**Commit:** 5b5f93e
**Applied fix:** `_cell` escapes backslashes before pipes. `_emit` passes both redacted child streams through a new `_defang`, which prefixes any line starting with `::` (also when indented) with `[child] `, so remote text cannot issue `::add-mask::`, `::stop-commands::` or `::endgroup::`. The runner's own `::group::` and `::endgroup::` lines are unchanged. Two new tests.

### IN-07: `RED_CONCLUSIONS` omits `startup_failure`, `action_required` and `stale`

**Files modified:** `backend/dlr_live_window_check.py`, `backend/tests/dlr_live_window_check_test.py`, `docs/data-science/decisions/dlr_live_runbook.md`
**Commit:** 0a496c2
**Applied fix:** Added `startup_failure` to `RED_CONCLUSIONS` (a run that cannot start shows red in the Actions UI), to the module docstring and to the runbook verdict table; the red-run test is parametrized over it. `action_required` and `stale` were left out on purpose: they are waiting or expired states, not failures, so they stay `missing`, which fails the window (the safe direction).

### IN-09: The model manifest has no repo-level guard, and `--write-manifest` drops the header comment

**Files modified:** `backend/dlr_live_check_models.py`, `backend/tests/dlr_live_check_models_test.py`
**Commit:** fa3b74c
**Applied fix:** `write_manifest` now writes a first line `# <UTC date> SHA-256 of the models promoted to the live workflow (regenerate with: ...)`, and the round-trip test checks it. New test `test_the_committed_models_match_the_committed_manifest` runs `check(MANIFEST_PATH, load=False)` from the repo root against the real tracked files (passes).

### IN-10: The WR-03 redaction masks ordinary child log text (`cache_key=`, `monkey=`)

**Files modified:** `backend/dlr_live_run.py`, `backend/tests/dlr_live_run_test.py`
**Commit:** 69caf82, 00299e6
**Follow-up (00299e6):** the boundary below stopped env-style names like `NREL_API_KEY=` from matching. Names ending in `_api_key`, `_apikey`, `_token`, `_password` or `_secret` are masked again (test extended); the consequence noted below no longer applies.
**Applied fix:** `_CREDENTIAL_PARAM_RE` now has the left boundary `(?<![A-Za-z0-9_])`. `cache_key=`, `max_key=`, `monkey=`, `turkey=` and `xtoken=` are left alone; `?token=`, `&api_key=`, a bare `key=`, `apikey=`, `email=`, `password=` and upper-case `KEY=` are still masked (new test checks both lists). The existing redaction test still passes. One consequence to be aware of: a name like `NREL_API_KEY=value` in a log is no longer masked by the pattern, because it is preceded by an underscore. The exact-value pass still removes the real values of the configured secrets.

### IN-11: Drill detection depends on a saved `cities_failed` entry, and the runbook still describes the old semantics

**Files modified:** `docs/data-science/decisions/dlr_live_runbook.md`
**Commit:** 1ce1cc1
**Applied fix:** Partial, as allowed. The runbook's `failed-visible` row now says "non-drill" and that a fault-drill run never counts. A new paragraph explains why drills are excluded, how one is recognised (`fault_injected` in the saved `cities_failed`), the remaining case (a drill killed before its city finished still counts as red), and that its rating rows and minutes still count. The code path was not changed, see below.

## Skipped Issues

### IN-03: The health predicate and run constants are duplicated across modules

**File:** `backend/dlr_live_run.py:46-47,258-263`, `backend/live_run_log.py:43-44,82-86`
**Reason:** Skipped on purpose. The fix means making `live_run_log._is_healthy` public, importing `PROVIDER` and `FORECAST_METHOD` from one place, and reconciling a third copy in `supabase_store`. That crosses three modules (one belongs to Phase 4) and drives the exit code and the run log, so it is a refactor rather than a low-risk Info fix. The two copies agree today. Better done as a deliberate change with its own tests.
**Original issue:** `_healthy` (runner exit code) and `live_run_log._is_healthy` (`cities_ok`/`cities_failed`) are two copies of one rule, `supabase_store` holds a third, and `PROVIDER`/`FORECAST_METHOD` are defined twice; drift would make the exit code and the run log disagree.

### IN-08: Skipped runs are counted as billed minutes

**File:** `backend/dlr_live_window_check.py:128-139`
**Reason:** Skipped on purpose, as a billing-semantics decision. Excluding `conclusion == "skipped"` changes the median that the runbook's 30-day projection and the SCHED-02 minutes evidence use. Whether a skipped run should count, and what the runbook's measured figures should then say, is a call for the owner. The change itself is one line if wanted.
**Original issue:** A `skipped` run (a non-main dispatch stopped by the `if:` guard) adds a one-minute sample, though it is not billed, which lowers the median used for the 30-day projection.

## Not done within a fixed finding

- IN-11, code part: recording the drilled city in the run row from the first `save_run_row` (so `_is_drill` would also recognise a drill killed before its city finished) was not done. It needs the first row to carry a new field or a pre-filled `cities_failed` entry, which changes the `pipeline_run` row shape and `live_run_log.build_run_row`. The case is remote (the drill normally ends in a few minutes) and is now documented.

---

_Fixed: 2026-10-26_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
