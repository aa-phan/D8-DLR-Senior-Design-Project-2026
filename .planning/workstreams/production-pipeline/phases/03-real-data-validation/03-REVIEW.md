---
phase: 03-real-data-validation
reviewed: 2026-10-23T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/backfill_archive.py
  - backend/real_data_validation.py
  - backend/tests/backfill_trace_test.py
  - backend/tests/real_data_validation_test.py
  - backend/tests/real_data_validation_val02_test.py
  - backend/tests/backfill_archive_test.py
findings:
  critical: 0
  warning: 3
  info: 7
  total: 10
status: issues_found
---

# Phase 3: Code Review Report (re-review after fix pass 2)

**Reviewed:** 2026-10-23
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Re-reviewed the six files after commits 103d236, 31cc279 and 7d0e0e8. I checked each earlier warning against the actual source and probed `_redact` with about 130 inputs of my own. I loaded `backfill_archive` with its heavy imports stubbed, because the sandbox has no project venv. I also ran the log-row expression through `pd.read_csv`.

Earlier findings, verified against source:

- Pass-2 WR-01 (whole `Authorization` values, escaped-quote JSON values, more names): fixed for the cases reported. `Authorization: Basic|Token|Bearer|Digest|Negotiate <cred>` is now fully masked, `{"token": "ab\"cd"}` becomes `{"token": REDACTED}`, and `pwd=`, `passwd=`, `auth=`, `sig=` and `credential=` are masked. Residual gaps are WR-01 and WR-02 below.
- Pass-2 WR-02 (diagnostic prose that mentions a key): fixed. `missing key: temp`, `hotkey: F5 failed`, `Max key: 5 reached` and `no data for key: wind_speed in window` all survive unchanged. The tests pin that behaviour.
- Pass-2 WR-03 (multi-line error in the log): fixed. `" ".join(... .split())` collapses `\n`, `\r` and the Unicode line separators before the cut. A related quoting hole remains, listed as WR-03.
- Catastrophic backtracking: none found. I ran `_redact` on 100,000-character adversarial inputs: runs of spaces after `token`/`authorization`/`Bearer`, `key: ` followed by 100k alphabet characters, 20,000 repeated `key: `, 50,000 `token=`, 50,000 `\a` pairs inside an unterminated quote, 100k-dash prefixes, and 100k-character names. Every case finished in 0.05 s or less. The quoted-value alternatives `(?:[^"\\]|\\.)*` are unambiguous, the `\s{0,4}` quantifiers are bounded, and the `_BARE_KEY_COLON` lookaheads are linear.

The pass-2 split of `key` into assignment-only matching did open credential-shaped leaks, and two shapes outside it leak too. They are the three warnings. No critical issue remains. The seven Info findings from earlier passes were deliberately left untouched and are all still present (IN-01 to IN-07). No structural (fallow) findings or external reviewer evidence were provided.

## Warnings

### WR-01: Dropping bare `key` from the name list leaks camelCase and concatenated key names (regression from pass 1)

**File:** `backend/backfill_archive.py:71-79`
**Issue:** The pass-1 pattern matched any `[\w-]*key`, so `accessKey=...` and `secretKey=...` were masked. The pass-2 pattern now requires the compound form `[_-]key` or `api[_-]?key`, and bare `key` only as a whole name. The run of `_redact` on my inputs:

```
'accessKey=AKIA123'  -> 'accessKey=AKIA123'
'accesskey=abcdefg'  -> 'accesskey=abcdefg'
'secretkey=abc'      -> 'secretkey=abc'
'SecretKey: abc'     -> 'SecretKey: abc'
'privatekey=abc'     -> 'privatekey=abc'
'X-Api-Key abc123'   -> 'X-Api-Key abc123'
```

camelCase names (`accessKey`, `secretKey`, `privateKey`, `signingKey`, `subscriptionKey`) are common in JSON and SDK error text. The by-value pass still covers the three configured env secrets, but any other credential echoed in an error string is written to the trace and log verbatim. The tests only cover `secret_key:` and `access-key=`, so the regression is untested. The `(?<![\w-])` lookbehind is why `[\w-]*` cannot simply be widened to match `hotkey`.
**Fix:** Allow `key` as a suffix of a known credential prefix without a separator, and leave `hotkey`, `monkey` and `turkey` alone:

```python
r"""(?:[\w-]*(?:token|api[_-]?key|(?:access|secret|private|signing|subscription|client|auth|encryption)[_-]?key|[_-]key|email|..."""
```

Add `accessKey=abc123`, `SecretKey: abc123` and `privatekey=abc123` to `test_redact_masks_every_credential_shape`, and `hotkey=F5` to the diagnostic-prose test if assignment form should stay masked.

### WR-02: Quoted, escaped, unterminated and `auth:`/`sig:` colon-form credentials still pass through

**File:** `backend/backfill_archive.py:71-84`
**Issue:** Several credential shapes survive `_redact`:

```
'key: "abcdefghij0123456789"'                 -> unchanged   (quoted value after a bare `key:`)
'key: abcdefghijklmnopqrstuvwxyz'             -> unchanged   (no digit, so the heuristic skips it)
'auth: abc123secret'                          -> unchanged
'sig: abcdef0123456789abcdef'                 -> unchanged   (the heuristic covers `key:` only)
'{"body": "{\"token\": \"abc123\"}"}'         -> unchanged   (JSON nested in a JSON string)
'token=\"abc\"'                               -> 'token=REDACTED"abc\"'   (abc leaks)
'token="abc'  /  "token='abc"                 -> unchanged   (unterminated quote, e.g. a pre-truncated message)
'api_key          =    abc'                   -> unchanged   (more than four spaces around the separator)
```

The escaped-quote cases matter most: an HTTP error body that is itself serialised JSON (`\"token\": \"...\"`) is exactly what a `requests` error with an embedded body looks like, and the `\"` after the name stops the name alternation from matching at all. `_BARE_KEY_COLON` is the only colon-form heuristic and it covers `key` alone, although `auth` and `sig` were split out the same way.
**Fix:** Allow an optional backslash before the quote in the name tail and the value opener, and let the quoted-value alternatives accept an unterminated quote running to the end of the text:

```python
r"""["']?\\?["']?\s{0,8}(?:=|:|%3D)"""          # name tail: `token\":`, `token":`, `token':`
r"""(?:\\?"(?:[^"\\]|\\.)*(?:\\?"|$)|\\?'(?:[^'\\]|\\.)*(?:\\?'|$)|..."""
```

Apply `_BARE_KEY_COLON` to `(key|auth|sig)` and let it accept a quoted value. Add each shape above to the credential-shape test.

### WR-03: The backfill log row is built by string formatting, so an error message that starts with an unbalanced `"` makes `_read_log` (and `completeness`) fail

**File:** `backend/backfill_archive.py:285-286`; read side `backend/real_data_validation.py:206-209`
**Issue:** Pass 2 collapsed whitespace and replaced `,` with `;`, but a double quote in the message is written raw into the last CSV field. A field that begins with `"` is parsed by pandas as a quoted field, and if the closing quote is missing the read fails. I reproduced it with `pd.read_csv(..., dtype=str)`:

```
error field '"unterminated'  -> ParserError: EOF inside string starting at row 1
error field '"'              -> ParserError: EOF inside string starting at row 1
```

A message that starts with a quote and has no matching one inside the first 120 characters hits this. That includes a long message of the form `"<text>"` that the `[:120]` cut slices before the closing quote. One such step then makes `completeness` fail and takes the whole run's validation tables down, the same failure class as the pass-2 WR-03 newline case.
**Fix:** Write the row with the `csv` module so quoting is handled, or neutralise the quote character:

```python
msg_safe = " ".join(_redact(msg, limit=None).split()).replace(",", ";").replace('"', "'")[:120]
log_fh.write(f"{ts_text},{c},,,,,,{msg_safe}\n")
```

Add a test that a message of `'"boom'` and one of `'"x" ' * 100` round-trips through `real_data_validation._read_log`.

## Info

### IN-01: `TRACE_SCHEMA` is never checked on read (still present)

**File:** `backend/real_data_validation.py:65, 159-196`
**Issue:** The constant is defined here and in `backfill_archive.py:53`; `load_trace` accepts any `schema`.
**Fix:** `from backfill_archive import TRACE_SCHEMA` and count records with a different `schema` the same way as `unparseable`.

### IN-02: `zip(run["results"], run["summary"])` silently truncates (still present)

**File:** `backend/backfill_archive.py:175`
**Issue:** A length mismatch drops records without notice; the missing ones then show up as `no_trace`.
**Fix:** `zip(..., strict=True)` (Python 3.10+) or assert equal lengths.

### IN-03: Duplicated helpers and constants (still present)

**File:** `backend/real_data_validation.py:128, 273, 321, 835`
**Issue:** `_OBSERVATION_COLUMNS` and `_OBS_COLUMNS` carry the same names in two forms. `_truthy` (line 321) and `_flag` (line 835) both implement "None/NaN is False", and only `_flag` handles `pd.NA`.
**Fix:** Keep `_flag`, derive `_OBS_COLUMNS` from `_OBSERVATION_COLUMNS.values()`.

### IN-04: Trace file handle can leak; replay output paths are not cross-checked (still present)

**File:** `backend/backfill_archive.py:237-243`; `backend/real_data_validation.py:1282`
**Issue:** `trace_cm = open(trace_path, "a")` runs before the `with`; if `open(log_path, "a")` then raises, the trace handle is never closed. In `replay`, `_refuse_existing` checks that each output is absent but not that the paths are distinct, so `--trace-out` equal to `--log-out` would interleave two formats in one file.
**Fix:** Use `contextlib.ExitStack` for both files; reject duplicate output paths in `replay` and `_cmd_replay`.

### IN-05: The manifest is still tied to the checkout location (still present)

**File:** `backend/real_data_validation.py:68, 80-91`
**Issue:** `owner_command` embeds `_REPO_ROOT` and `<repo>/.venv/bin/python` as absolute paths, so the manifest's `command` differs per checkout (and per worktree, where `.venv` does not exist), while the docstring says equal inputs give equal bytes from any directory.
**Fix:** Say "same checkout" in the `build_manifest` docstring, or emit `python` plus a repo-relative `cd` placeholder; at minimum fall back to `sys.executable` when the interpreter path does not exist.

### IN-06: `_terminate_last_line` covers only the trace; the log can still get a row glued onto a torn line (still present)

**File:** `backend/backfill_archive.py:229-243`
**Issue:** A killed run can leave the log without a trailing newline. The next resumed run appends its first row onto the fragment. `_retire_stale_log` only checks the header.
**Fix:** Call `_terminate_last_line(log_path)` before `open(log_path, "a")` when the log already exists.

### IN-07: A torn line in the replay trace is silently dropped by the fidelity check and the replay-side report (still present)

**File:** `backend/real_data_validation.py:1432-1435, 1684-1685`
**Issue:** `load_trace` counts `unparseable`, but only the original trace's count reaches `report_meta` (line 1455). `build_report` (replay trace) and `_cmd_replay` (`load_trace(args.trace_out)`) discard the count, so a damaged replay trace silently shrinks the comparison instead of failing the self-check.
**Fix:** Record `replay_trace_unparseable_line_mismatches` in `meta` from `load_trace(replay_trace).attrs` (the key ends in `mismatches`, so the existing self-check picks it up), and print a warning in `_cmd_replay`.

---

_Reviewed: 2026-10-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
