---
phase: 03-real-data-validation
fixed_at: 2026-10-23T00:00:00Z
review_path: .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-REVIEW.md
iteration: 3
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-10-23
**Source review:** .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-REVIEW.md
**Iteration:** 3

**Summary:**
- Findings in scope: 3
- Fixed: 3
- Skipped: 0

Verification ran in the isolated worktree `/Users/aphan/Senior_Design/.claude/worktrees/review-fix-03` (branch `worktree-review-fix-03`), using the main checkout's interpreter `/Users/aphan/Senior_Design/.venv/bin/python` (Python 3.12.13), because the worktree has no venv. Modules run before each commit: `backfill_trace_test.py`, `backfill_archive_test.py`, `real_data_validation_test.py` and `real_data_validation_val02_test.py` (final run: 118 passed). Info findings were left untouched, as scoped.

## Fixed Issues

### WR-01: Dropping bare `key` from the name list leaks camelCase and concatenated key names

**Files modified:** `backend/backfill_archive.py`, `backend/tests/backfill_trace_test.py`
**Commit:** 17c436b
**Applied fix:** Added one alternation to the name list in `_SECRET_PAIR`: `(?:access|secret|private|signing|subscription|client|auth|encryption|master)key`. This masks `accessKey`, `accesskey`, `SecretKey`, `privatekey`, `signingKey` and `subscriptionKey`. Bare `key` still counts only as a whole name, so `hotkey`, `monkey`, `turkey` and `keyboard` pass through. Tests: six new credential shapes and `monkey`, `turkey`, `hotkey` and `keyboard=us` added to the no-over-redaction test.
**Not covered:** `X-Api-Key abc123` (a header name followed by a space with no `:` or `=`). It has no separator to anchor on, so masking it would also mask ordinary prose such as "api key abc". It is not a real header form (headers use `:`), and `X-Api-Key: abc123` is masked.

### WR-02: Quoted, escaped, unterminated and `auth:`/`sig:` colon-form credentials still pass through

**Files modified:** `backend/backfill_archive.py`, `backend/tests/backfill_trace_test.py`
**Commit:** 191c93a
**Applied fix:** Reworked the pattern into named, commented parts instead of adding more special cases.
- Name tail: `(?:\\?["'])?\s*` replaces `["']?\s{0,4}`, so `token\":` (JSON inside a JSON string) matches and spacing around the separator is no longer capped.
- Value: new alternatives for escaped-quote strings (`\"abc\"` and `\'abc\'`). The ordinary quoted alternatives accept a missing closing quote (end of text) and a trailing lone backslash. Because the quoted body can only stop at an unescaped quote or the end of the text, there is no backtracking.
- `_BARE_KEY_COLON` became `_bare_colon(names, min_length)`. It now covers `key` (20+ characters, as before), plus `auth` and `sig` (8+ characters). The value must contain a digit and may sit in quotes, which stay.
- Tests: ten new credential shapes (quoted bare `key:`, `auth:`, `sig:`, nested JSON, escaped-quote value, both unterminated quotes, trailing backslash, wide spacing). `missing key: 'temp'`, `auth: 401` and `sig: ok` were added to the no-over-redaction test. `missing key: temp`, `hotkey: F5 failed`, `author: bob`, `auth: failed` and `Max key: 5 reached` still pass unchanged.
- Performance: I ran 100,000-character adversarial inputs (space runs, unterminated quotes, repeated `key:`/`auth:`/`sig:`, repeated escaped names). Every one finished in 0.04 s or less, and a 900,000-character case finished in 0.16 s.
**Skipped shape:** `key: abcdefghijklmnopqrstuvwxyz` (20+ letters, no digit) is still unchanged. I did not close it because a letters-only value is indistinguishable from an identifier or word in diagnostic prose ("missing key: temperature_at_rating_point"). Dropping the digit requirement would over-redact the `missing key: ...` family that pass 2 deliberately protected. The configured env secrets are still scrubbed by value, and the `key=` / `"key":` forms are masked whatever the value looks like.
**Status note:** The `auth`/`sig` 8-character threshold is a judgement call (`auth: abc123secret` is 12 characters). A prose value of 8+ credential characters with a digit, such as `auth: error401`, will now be masked. Please confirm the threshold if it matters.

### WR-03: The backfill log row is built by string formatting, so an error message that starts with an unbalanced `"` makes `_read_log` fail

**Files modified:** `backend/backfill_archive.py`, `backend/tests/backfill_trace_test.py`
**Commit:** 8a9ab91
**Applied fix:** The error row is now written with `csv.writer(log_fh, lineterminator="\n").writerow([...])`, so quotes are escaped properly. I kept the comma-to-`;` replacement so naive `split(",")` readers still see the same columns. Characters that are not printable (NUL, control characters, Unicode line separators) become spaces before the whitespace collapse. This is needed because pandas silently truncates a field at a NUL byte. I also fuzzed 5,000 random messages built from quotes, commas, newlines, NUL and control characters through the writer and `pd.read_csv(dtype=str)`, and every one round-tripped exactly. Test: a parametrized round-trip through `real_data_validation._read_log` for `"boom`, `"`, `'"x" ' * 100`, mixed quotes, single quotes, NUL/control/line-separator characters, a run of commas and quotes, and an empty message.

---

_Fixed: 2026-10-23_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 3_
