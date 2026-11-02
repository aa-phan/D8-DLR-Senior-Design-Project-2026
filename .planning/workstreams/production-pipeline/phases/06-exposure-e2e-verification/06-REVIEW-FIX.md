---
phase: 06-exposure-e2e-verification
fixed_at: 2026-11-01T00:00:00Z
review_path: .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 6: Code Review Fix Report (round 2)

**Fixed at:** 2026-11-01
**Source review:** .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-REVIEW.md
**Iteration:** 1

This report replaces the round-1 report, which is preserved in git at 3764910.

**Summary:**
- Findings in scope: 2 (WR-01, WR-02; scope is critical and warning only)
- Fixed: 2
- Skipped: 0
- Not in scope: IN-01, IN-02, IN-03 (info findings)

## Fixed Issues

### WR-02: Any 4xx on a view write counts as a refusal (fixed: requires human verification)

**Files modified:** `backend/e2e_verify_readonly.py`, `backend/tests/e2e_readonly_test.py`
**Commit:** efca90c
**Applied fix:** `_classify_view_write` no longer passes every 4xx. A view write counts as refused only when the answer names the cause:
- code `55000` at any status of 400 or above. This is the live answer (HTTP 500, `55000`).
- code `42501` with HTTP 401 or 403, or a 5xx.
- code `PGRST117` or `42809` with a 4xx. Either code proves the view is not writable.

Every other answer is inconclusive: a bare 401 or 403, a 400 (including PGRST102), a 404 (including PGRST125), 408, 429, and a 5xx with no code. A 2xx is still "write accepted".

`VIEW_WRITE_DB_REFUSAL_CODES` is now `("55000",)`, with two new constants for the privilege and not-writable codes.

I did not add `PGRST205` for views, unlike the review's example. A "not in the schema cache" answer for the view would pass vacuously if the view were ever renamed, which is the same weakness IN-03 describes for the hidden table.

Tests, in `backend/tests/e2e_readonly_test.py`:
- `test_view_write_verdicts` is rewritten. It passes 55000/500, 42501/401, 42501/403, PGRST117/405 and 42809/404. It requires inconclusive for a bare 401 "Invalid API key", a bare 403, a bare 405, a 400 PGRST102, a 404 PGRST125, a bare 404, 408, 429, a codeless 500, 504, and 2xx. The old case `(401, {"message": "x"}) -> True` and `(405, ...) -> True` were the loose behaviour and now expect inconclusive.
- New test `test_committed_live_view_answers_are_still_classified_as_refused` replays the `view_insert`, `view_patch` and `view_delete` attempts recorded in `06-09-live-checks.json`, `06-12-live-checks.json` and `06-13-live-checks.json`. All nine are HTTP 500 with code 55000 and still classify as refused, so a live run stays green.

Because this is classifier logic, a human should confirm the accepted code and status pairs match what the live project returns for other cases. The recorded live answers are covered.

### WR-01: The 300-character cap on stored alerts cuts off the fallback rating (fixed: requires human verification)

**Files modified:** `backend/supabase_store.py`, `backend/tests/supabase_store_test.py`
**Commit:** 6d2dafc
**Applied fix:** A new `_safe_alert` helper redacts the whole alert uncapped, then shortens it to 300 characters. If the text is too long and ends in ` — fallback rating N A`, it cuts the middle (the reason) with an ellipsis and keeps that suffix whole. Without such a suffix it cuts at the cap as before. Redaction still runs first, so a secret near the cut cannot survive. `build_rating_row` uses `_safe_alert`. `fallback_gates` is still derived from the first token of each alert.

Tests, in `backend/tests/supabase_store_test.py`:
- The existing `len == 300` assertion is kept for an alert with no fallback suffix.
- New `test_a_long_alert_keeps_its_fallback_rating_suffix_when_it_is_shortened`. A long G6 alert with an embedded connection URL and `password=` must end in `— fallback rating 1825 A`, be at most 300 characters long, contain an ellipsis, and carry no secret. A second case puts a `password=` secret near the cut and requires the suffix to survive and the secret to be gone.

## Verification

Run from the repo root `/Users/aphan/Senior_Design`, on main, after both commits:

```
DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider \
  backend/tests/e2e_readonly_test.py backend/tests/supabase_store_test.py \
  backend/tests/secret_scan_test.py backend/tests/expose_migration_test.py \
  backend/tests/e2e_soak_report_test.py backend/tests/e2e_trace_test.py
=> 234 passed, 1 skipped
```

The one skip is the owner-local check in `secret_scan_test.py:316`, which needs live environment variables. The same run in the isolated worktree gave the same result (234 passed, 1 skipped). The secret scan passes, so the committed text carries no project URL, reference or key.

## Not addressed (out of scope for `critical_warning`)

- IN-01 (`begin_read_only` cannot prove the guard took effect)
- IN-02 (`public_role_privileges` ignores sequences)
- IN-03 (vacuous PGRST205 pass if `pipeline_run` is renamed; import-time opener ignores `.env` proxy settings)

---

_Fixed: 2026-11-01_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
