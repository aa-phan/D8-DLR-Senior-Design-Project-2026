---
phase: 03-real-data-validation
reviewed: 2026-10-21T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - backend/backfill_archive.py
  - backend/real_data_validation.py
  - backend/tests/backfill_trace_test.py
  - backend/tests/real_data_validation_test.py
  - backend/tests/real_data_validation_val02_test.py
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-10-21
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed the `--trace-path` diff in `backfill_archive.py` (since 01f46c1) and the four new files. The 47 tests in the four relevant modules pass. The analysis math (classification, coverage populations, bootstrap, fidelity) read as consistent with its documented definitions, and no correctness defect was found in the VAL-01/VAL-02 tables themselves. The main concern is the credential redaction, which is a denylist regex that demonstrably misses common value shapes, while the same error text goes unredacted into the backfill log. The remaining findings are robustness gaps around interrupted/resumed runs (torn trace lines, Ctrl-C during replay, trace written after the archive row), an uncaught `git` failure, and a manifest that does not meet its own determinism claim.

No structural (fallow) findings or external reviewer evidence were provided.

## Critical Issues

### CR-01: Credential redaction misses quoted, JSON/dict-style, header and encoded forms, and leaks the tail of values containing separators

**File:** `backend/backfill_archive.py:51-60, 91-99`
**Issue:** The stated requirement is that credentials are never written to the trace, but `_SECRET_PAIR` only matches `name=value` where the value starts with a character outside `[^&\s,;)"']`. Verified by running `_redact`:

```
"params={'token': 'abc123', 'a':1}"  -> unchanged   (dict/repr form)
'url?token="abc123"'                 -> unchanged   (quoted value: the first char after = is a quote, so no match)
'{"api_key": "abc123"}'              -> unchanged   (JSON form)
'Authorization: Bearer abc123'       -> unchanged   (header form)
'X-Api-Key: abc123'                  -> unchanged
'token%3Dabc123'                     -> unchanged   (URL-encoded =)
'url?api_key=abc,123&x'              -> 'url?api_key=REDACTED,123&x'  (tail of value leaked)
'url?token=a)bc'                     -> 'url?token=REDACTED)bc'       (tail leaked)
```

Today the providers scrub their own messages (nsrdb_provider documents this), so the realistic exposure is a defense-in-depth failure rather than a live leak. But `_redact` is the only guard on `error` and every `alert` string persisted to a shareable, hashed artifact, and any future exception that stringifies a kwargs dict, a quoted URL or a header will be written verbatim.
**Fix:** Redact by known secret value as well as by shape. Collect the actual secret values at backfill start (`os.environ` values of `SYNOPTIC_TOKEN`, `NREL_API_KEY`, `NREL_API_EMAIL`, when set and non-empty) and replace every occurrence (plain and `urllib.parse.quote`d) before the regex pass. Also widen the regex:

```python
_SECRET_PAIR = re.compile(
    r"""([\w-]*(?:token|api[_-]?key|key|email|password|secret|authorization|bearer)\W{0,4}?)"""
    r"""(?:=|:|%3D)\s*["']?(?:Bearer\s+)?[^&\s"']+""", re.IGNORECASE)
```

and add tests for the quoted, dict, header and comma-containing forms.

## Warnings

### WR-01: The same error text is written unredacted to the backfill log

**File:** `backend/backfill_archive.py:208`
**Issue:** `log_fh.write(f"...{msg.replace(',', ';')[:120]}\n")` writes the raw exception string, while the trace gets `_redact(message)`. The log is one of the three artifacts the manifest hashes and the owner hands around, so the redaction work in the trace is bypassed one line above it. The raw 120-character cut can also leave a partial secret. (The line predates this phase, but this phase introduces the "credentials never persisted" requirement.)
**Fix:** `msg_safe = _redact(msg)` once and use it for both the log and the trace; keep the comma replacement after redaction.

### WR-02: A torn last line in the trace makes the whole analysis crash

**File:** `backend/real_data_validation.py:155-159`
**Issue:** `load_trace` calls `json.loads` on every non-empty line with no handling. The backfill is explicitly designed to be killed and resumed (it appends, flushes per step), so a `kill -9`, power loss or disk-full mid-write can leave a partial final line. `completeness`, `manifest` (no, it only hashes), `report` and `replay` then die with a `JSONDecodeError` traceback and no indication of which line. Worse, the resumed backfill appends the next record onto the unterminated partial line, corrupting a good record as well.
**Fix:** In `load_trace`, catch `json.JSONDecodeError`, count the bad lines (expose via `frame.attrs["unparseable"]` and `report_meta`, and make it a failing self-check) and skip them; in `backfill`, before appending, ensure the existing trace ends in a newline.

### WR-03: Ctrl-C during `replay` silently continues with the next city and produces a partial replay that cannot be resumed

**File:** `backend/real_data_validation.py:1251-1255` (interacts with `backend/backfill_archive.py:221-222`)
**Issue:** `backfill` swallows `KeyboardInterrupt` and returns normally, printing "rerun the same command to continue". `replay` loops over cities, so the interrupt only stops the current city; the loop starts the next one. The fidelity step in `_cmd_replay` then runs on a partial replay (missing steps classed MISSING, reported as fidelity mismatches). The advertised "rerun the same command" is impossible because `_refuse_existing` rejects the existing outputs.
**Fix:** Have `backfill` return/record that it was interrupted (for example `totals["interrupted"] = True`) and let `replay` stop and return a non-zero status when set, with a message that the outputs are incomplete and must be deleted before retrying.

### WR-04: The trace record is written after the archive row and the log row, so an interrupt leaves a step archived with no trace forever

**File:** `backend/backfill_archive.py:198-213`
**Issue:** `run_dlr_pipeline` appends the archive row inside the step, the log row follows, and the trace is written last. A `KeyboardInterrupt` (or an `OSError` from the trace write) between them leaves the step archived and logged but untraced. On resume `todo` is computed from the archive, so that step is skipped and never traced. It surfaces as `no_trace` and its VAL-01/VAL-02 contribution is lost, with no way to recover it short of deleting the archive row. The validation depends on trace completeness.
**Fix:** Write the trace record before the log/summary lines (it only depends on `run`), and consider flushing it before returning from the step. Document that `no_trace > 0` after an interrupted run requires re-running the affected step.

### WR-05: `_git` raises when git is not installed

**File:** `backend/real_data_validation.py:1461-1464`
**Issue:** `subprocess.run(["git", ...], check=False)` only guards a non-zero exit; a missing `git` binary raises `FileNotFoundError`, so `manifest` crashes after the inputs were already hashed (and `report` is unaffected, but the manifest is the Phase 4 handoff).
**Fix:** Wrap in `try/except (OSError, subprocess.SubprocessError): return ""` (the existing callers already tolerate an empty string).

### WR-06: The manifest is not deterministic as documented, and its `command` is not shell-safe

**File:** `backend/real_data_validation.py:73-78, 1482-1508`
**Issue:** The docstring promises "equal inputs give equal bytes", but the manifest embeds `os.getcwd()` (`working_directory`) and each file's `path` exactly as typed (relative vs absolute), so the same run produces different bytes from a different directory or with a differently written path. Separately, `OWNER_COMMAND_TEMPLATE` splices `repr(argv)` into a double-quoted shell string: an argument containing `"`, `$` or a backtick, or a single quote (which makes `repr` choose double quotes), yields a command that breaks or expands on paste. The template also hard-codes `/Users/aphan/...` absolute paths.
**Fix:** Drop `working_directory` and record repo-relative/`os.path.abspath`-normalized paths (or exclude them from the determinism claim and say so). Build the command with `shlex.quote` around the whole `-c` program, or emit the argv as a JSON list and a separate runner script instead of an inline `-c`. Derive the repo root from `_REPO_ROOT` instead of the literal home directory.

## Info

### IN-01: `TRACE_SCHEMA` is never checked on read

**File:** `backend/real_data_validation.py:64, 145-169`
**Issue:** The constant is defined (and duplicated in `backfill_archive.py:52`) but `load_trace` accepts records of any `schema`. A `backfill_trace/2` file would be analysed silently with possibly wrong column semantics. The duplicate is guarded only by an equality assertion in a test.
**Fix:** `from backfill_archive import TRACE_SCHEMA` instead of redefining, and fail (or count) records whose `schema` differs.

### IN-02: `zip(run["results"], run["summary"])` silently truncates

**File:** `backend/backfill_archive.py:110`
**Issue:** If the two lists ever differ in length, records are dropped without notice, and the missing ones then look like `no_trace`.
**Fix:** `zip(..., strict=True)` (Python 3.10+) or assert equal lengths.

### IN-03: Duplicated helpers and constants

**File:** `backend/real_data_validation.py:111-117, 246, 294-297, 808-814`
**Issue:** `_OBSERVATION_COLUMNS` and `_OBS_COLUMNS` carry the same column names in two forms, and `_truthy` and `_flag` are two implementations of "None/NaN is False" (`_flag` also handles `pd.NA`, `_truthy` does not and would raise on `pd.NA`). Divergence between the two is a latent bug.
**Fix:** Keep one `_flag`, derive `_OBS_COLUMNS` from `_OBSERVATION_COLUMNS.values()`.

### IN-04: Trace file handle can leak and `replay` output paths are not cross-checked

**File:** `backend/backfill_archive.py:172-176`; `backend/real_data_validation.py:1214-1218`
**Issue:** `open(trace_path, "a")` runs before the `with`; if `open(log_path, ...)` then raises, the trace handle is never closed (use `contextlib.ExitStack`). In `replay`, `_refuse_existing` checks each output but not that the four output paths are distinct, so `--trace-out` equal to `--log-out` (neither existing) interleaves two formats in one file.
**Fix:** Use `ExitStack`; reject duplicate output paths in `_cmd_replay`/`replay`.

---

_Reviewed: 2026-10-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
