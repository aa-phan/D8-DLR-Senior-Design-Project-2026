---
phase: 03-real-data-validation
fixed_at: 2026-10-23T00:00:00Z
review_path: .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 10
skipped: 0
status: all_fixed
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-10-23
**Source review:** .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 10 (3 warnings, 7 info; `fix_scope: all`)
- Fixed in this run: 7 (IN-01 to IN-07)
- Already fixed before this run: 3 (WR-01, WR-02, WR-03; see below)
- Skipped: 0

Verification ran in the isolated worktree `/Users/aphan/Senior_Design/.claude/worktrees/review-fix-03` (branch `worktree-review-fix-03`), using the main checkout's interpreter `/Users/aphan/Senior_Design/.venv/bin/python` (Python 3.12.13), because the worktree has no venv. The four touched test modules (`real_data_validation_test.py`, `real_data_validation_val02_test.py`, `backfill_trace_test.py`, `backfill_archive_test.py`) were run before each commit; the final run was 125 passed (baseline before this run: 118). `supabase_load_backfill_test.py` and `dlr_orchestrator_test.py`, which also import the touched modules, pass (26 passed, 3 skipped). This is not reproducible from the main checkout after the worktree is torn down, because the commits only land there on fast-forward.

## Already Fixed (stale in REVIEW.md, not re-fixed)

REVIEW.md predates these commits, which are on this branch. Each was checked against `git log` and the source and left alone.

### WR-01: Dropping bare `key` from the name list leaks camelCase and concatenated key names

**Commit:** 17c436b (`fix(03): WR-01 mask camelCase and concatenated credential key names`)

### WR-02: Quoted, escaped, unterminated and `auth:`/`sig:` colon-form credentials still pass through

**Commit:** 191c93a (`fix(03): WR-02 mask escaped, unterminated and colon-form credential values`)

### WR-03: The backfill log row is built by string formatting, so a leading `"` breaks `_read_log`

**Commit:** 8a9ab91 (`fix(03): WR-03 write the backfill error row with csv.writer so a quote cannot break the log`)

## Fixed Issues

### IN-01: `TRACE_SCHEMA` is never checked on read

**Files modified:** `backend/real_data_validation.py`, `backend/tests/real_data_validation_test.py`
**Commit:** 05814e6
**Applied fix:** `TRACE_SCHEMA` is now `backfill_archive.TRACE_SCHEMA` (one definition). `load_trace` counts a record whose `schema` differs, or is missing, in `attrs["unparseable"]`, so the existing self-check fails the report on it instead of reading it with the wrong column meanings. Regression test added with a `backfill_trace/2` record and a schema-less record.

### IN-02: `zip(run["results"], run["summary"])` silently truncates

**Files modified:** `backend/backfill_archive.py`, `backend/tests/backfill_trace_test.py`
**Commit:** 656d034
**Applied fix:** `_trace_records` raises `ValueError` when the two lists differ in length. I used an explicit length check rather than `zip(strict=True)` so the code does not depend on Python 3.10 or later, which the project does not state. Regression test added.

### IN-03: Duplicated helpers and constants

**Files modified:** `backend/real_data_validation.py`, `backend/tests/real_data_validation_test.py`
**Commit:** ddbf5f9
**Applied fix:** The smallest change that resolves it. `_truthy` is removed and its two call sites use `_flag`, which also handles `pd.NA`. `_OBS_COLUMNS` is now `tuple(_OBSERVATION_COLUMNS.values())`; the order is identical, so every use is unchanged. Test pins both. The status of this finding is "fixed" (a refactor, no logic change beyond `pd.NA` no longer raising).

### IN-04: Trace file handle can leak; replay output paths are not cross-checked

**Files modified:** `backend/backfill_archive.py`, `backend/real_data_validation.py`, `backend/tests/backfill_trace_test.py`, `backend/tests/real_data_validation_val02_test.py`
**Commit:** 202fb2d
**Applied fix:** `backfill` opens the trace and log through `contextlib.ExitStack`, so the trace handle is closed if the log open raises. New `_refuse_duplicate_paths` (compares `os.path.realpath`) runs in `replay` for the archive, trace and log outputs, and in `_cmd_replay` for those three plus `--fidelity-out`; it raises `ReplayRefused`, which the CLI maps to exit 2. Tests: the leak test fails against the old code (verified); the duplicate-path test covers both the API and the CLI.

### IN-05: The manifest is still tied to the checkout location

**Files modified:** `backend/real_data_validation.py`
**Commit:** 47954ff
**Applied fix:** Documentation only, the "say same checkout" option from the review. The `build_manifest` docstring now says equal bytes hold from any directory of the same checkout, and that `command` is the one field that differs between checkouts or a worktree. I did not add the `sys.executable` fallback: it would make the manifest bytes depend on the running interpreter, and `test_owner_command_survives_shell_metacharacters_in_the_argv` pins the `.venv/bin/python` path. No test changed, since behaviour is unchanged.

### IN-06: `_terminate_last_line` covers only the trace, not the log

**Files modified:** `backend/backfill_archive.py`, `backend/tests/backfill_trace_test.py`
**Commit:** feb4dbe
**Applied fix:** `backfill` calls `_terminate_last_line(log_path)` after `_retire_stale_log` and before the log is opened for append. Regression test writes a log with a torn last row and checks that the next row starts on its own line; it fails against the old code (verified).

### IN-07: A torn line in the replay trace is silently dropped

**Files modified:** `backend/real_data_validation.py`, `backend/tests/real_data_validation_val02_test.py`
**Commit:** f0af8be
**Applied fix:** `build_report` loads the replay trace once and records `replay_trace_unparseable_line_mismatches` in `report_meta.json`; the key ends in `mismatches`, so the existing self-check fails the report on it. `_cmd_replay` prints a warning to stderr and returns exit 1 when the replay trace has unreadable lines, even when the fidelity mismatches are zero. Test covers both the CLI and the report.

## Skipped Issues

None.

---

_Fixed: 2026-10-23_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
