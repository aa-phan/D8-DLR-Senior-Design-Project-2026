---
phase: 06-exposure-e2e-verification
reviewed: 2026-11-01T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - backend/e2e_verify_readonly.py
  - backend/supabase_store.py
  - backend/tests/e2e_readonly_test.py
  - backend/tests/supabase_store_test.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-11-01
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Incremental review of commits efca90c, 6d2dafc and 4e9b2d0 (changes since 2eb2f8c), plus a scan of the full listed files.
Both test files pass using `backend/../.venv` (125 passed).

- `_safe_alert` is correct on the cases I tried. It redacts before cutting, keeps the output at or under 300 characters, and keeps the `— fallback rating N A` suffix whole. It falls back to a plain cut when there is no suffix, when the tail does not start with the prefix, or when the tail is too long. The `gates` value is still derived correctly because the head of the text is preserved. I found no secret leak and no off-by-one.
- The stricter `_classify_view_write` accepts the live answers recorded in the committed evidence (HTTP 500 with 55000). The remaining weaknesses are an inconsistency with the table classifier and a skipped regression guard.
- No project CLAUDE.md exists in the repo. Only the user's global instructions apply, and they do not bear on this review.

## Warnings

### WR-01: View-write classifier treats an RLS-only 42501 as a privilege refusal, unlike the table classifier

**File:** `backend/e2e_verify_readonly.py:439-441`
**Issue:** `_classify_table_write` deliberately fails an RLS-only rejection. It checks the message for "row-level security" and reports "a write grant is still present". `_classify_view_write` passes any `42501` on 401/403/5xx without looking at the message. If the view were ever made auto-updatable (for example `security_invoker` over `city_rating`), an anon INSERT would be refused only by RLS (`new row violates row-level security policy`, 42501). That would be recorded as a pass, although the view still holds a write grant. This is the exact failure mode the table check was written to catch. The commit's own docstring says the rule is "the answer names the cause", but this branch accepts the code alone. The `5xx` leg of the 42501 rule also has no live evidence and no test.
**Fix:**
```python
message = str(body.get("message") or "").lower()
if code in VIEW_WRITE_PRIVILEGE_CODES and (status in (401, 403) or status >= 500):
    if "row-level security" in message:
        return False, "RLS-only rejection: a write grant is still present (HTTP %d 42501)" % status, code
    if "permission denied" in message:
        return True, "refused by privilege (HTTP %d, code %s)" % (status, code), code
```
Add a parametrized case such as `(403, {"code": "42501", "message": "new row violates row-level security policy for table ..."}, False)`.

### WR-02: Committed live-evidence regression test skips silently when the evidence is absent

**File:** `backend/tests/e2e_readonly_test.py:600-626`
**Issue:** `test_committed_live_view_answers_are_still_classified_as_refused` reads three JSON files under `.planning/.../06-exposure-e2e-verification` and calls `pytest.skip` if any is missing. `.planning/` is excluded from PR branches by `gsd-pr-branch` and may be archived or moved after the phase. In those cases the guard that stops the strict rule from rejecting the real 500/55000 answer vanishes without notice, and the suite stays green. This is the one regression the new rule is most likely to cause: a too-strict classifier makes the live verification fail. The test also hardcodes `assert len(attempts) == 3` and discards the recorded message.
**Fix:** Keep a small copy of the recorded answers inside `backend/tests/` (a fixture constant or JSON) and assert on it unconditionally. `(500, {"code": "55000", "message": "cannot change view"})` is already covered by `test_view_write_verdicts`, so the minimum change is to turn the skip into a visible failure in CI, or to drop the dependency on `.planning/`.

## Info

### IN-01: 55000 is accepted on code alone, at any status of 400 or above

**File:** `backend/e2e_verify_readonly.py:435`
**Issue:** `55000` (`object_not_in_prerequisite_state`) has many causes besides "cannot change view". The docstring and comment name the message, but the message is never checked. The `snapshot_unchanged` check remains the backstop, so impact is low. Matching the message (`"cannot change view"` in the lowercased message) would make this rule as strict as the stated "names the cause" policy. The live evidence records only the code, so confirm the message first; a message check could turn the live run inconclusive if the real text differs.
**Fix:** Require `"cannot change view" in message` in addition to the code, after confirming the live message text.

### IN-02: Shortened alert can leave an unbalanced parenthesis

**File:** `backend/supabase_store.py:314-315`
**Issue:** When the middle is cut, the head (`G6 FAIL (detector error (boom …`) loses its closing parentheses, so the stored text reads as truncated mid-expression. This is cosmetic only. `fallback_gates` is unaffected because it takes the first token.
**Fix:** Optional. Append `")"` after the ellipsis, taking one more character out of `room`, or leave as is.

---

_Reviewed: 2026-11-01_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
