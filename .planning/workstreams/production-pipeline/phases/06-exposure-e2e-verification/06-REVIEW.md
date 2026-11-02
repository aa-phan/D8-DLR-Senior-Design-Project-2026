---
phase: 06-exposure-e2e-verification
reviewed: 2026-11-01T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - backend/e2e_soak_report.py
  - backend/e2e_trace.py
  - backend/e2e_verify_readonly.py
  - backend/supabase_rest.py
  - backend/supabase_store.py
  - backend/tests/e2e_readonly_test.py
  - backend/tests/e2e_soak_report_test.py
  - backend/tests/e2e_trace_test.py
  - backend/tests/expose_migration_test.py
  - backend/tests/supabase_store_test.py
  - docs/data-science/decisions/dlr_live_runbook.md
  - docs/data-science/schema/city_rating_v1.md
  - docs/integration/rest-api.md
  - supabase/ops/verify_exposure.sql
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-11-01
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

This is an incremental review of the WR-01 to WR-06 fix commits (d5bddba..efe3fbd). Each fix does what it says. I traced:

- `begin_read_only` and its callers in the trace and soak export.
- The `_needs_annotation` path through `evaluate_soak`, the report cell and the JSON.
- `_hidden_cause` and the `key_sanity` pre-check.
- `_SameHostRedirects` and `_url_scheme_ok`, including the `localhost@evil` userinfo case, the IPv6 loopback and a refused 3xx.
- The new `public_role_privileges` CTE, whose multi-privilege `has_table_privilege` calls return true if any listed privilege is held.

I found no correctness or security defects that block shipping. The two warnings are weaknesses that remain in the hardened checks. The three info items are small gaps.

## Warnings

### WR-01: The 300-character cap on stored alerts cuts off the fallback rating

**File:** `backend/supabase_store.py:563-566`
**Issue:** `redact(str(a))` truncates to the default `_MAX_MESSAGE_CHARS` (300). Alerts are built as `"{gate} FAIL ({reason}) — fallback rating {rating:.0f} A"` (`DLRSafetyMonitor._fallback`). The G6 alert embeds the raw detector exception inside `reason`. A long exception message pushes the `— fallback rating N A` suffix past character 300, and the cut then removes exactly that suffix. The stored alert is then a dangling `... (detector error (...` with no closing parenthesis and no fallback value. Consumers parse the head of the string, so only the tail is lost. It is still a lossy, silent truncation of a published column, and the test (`len(row["alerts"][1]) == 300`) asserts the lossy behaviour rather than a preserved suffix.
**Fix:** Redact the whole alert, then shorten the middle (the reason) instead of the tail, for example:
```python
def _safe_alert(a, limit=300):
    text = redact(str(a), limit=10**6)          # redact first, uncapped
    if len(text) <= limit:
        return text
    head, sep, tail = text.rpartition(" — ")     # keep the "— fallback rating N A" suffix
    if not sep:
        return text[:limit]
    return head[: limit - len(sep) - len(tail) - 1] + "…" + sep + tail
```
Update the test to assert that the suffix survives.

### WR-02: Any 4xx on a view write counts as a refusal, including answers that never reached the privilege layer

**File:** `backend/e2e_verify_readonly.py:426-428`
**Issue:** The fix for WR-02 made the hidden-table check require a named cause (42501 or PGRST205/106/202). The view-write classifier still passes every 4xx with no code check. Examples are a 400 for a malformed body (PGRST102), a 404 for a mistyped path, a 408 or 429 from the gateway, and a bare 401 "Invalid API key". All of these say nothing about whether the view accepts writes. The `snapshot_unchanged` backstop cannot catch a writable view, because the view writes target the OLD row, which the view never shows (see the comment in `_write_specs`). A view that became writable would therefore pass `write:view_*` on a rate-limited or mis-shaped request. The table writes are strict (42501 plus "permission denied"). The view writes are the weaker half, and the check this fix just hardened is stricter than they are.
**Fix:** Pass only on a named cause, mirroring the table and hidden logic. For example:
```python
if status in (401, 403) and code == "42501":
    return True, "refused by privilege (HTTP %d 42501)" % status, code
if status in (404, 405) and code in ("PGRST205", "PGRST117", "42809", "55000"):
    return True, "refused (HTTP %d, %s)" % (status, code), code
if status >= 500 and code in VIEW_WRITE_DB_REFUSAL_CODES:
    return True, "refused by the database (HTTP %d, code %s)" % (status, code), code
return False, "inconclusive: HTTP %d, code %s" % (status, code), code
```
Confirm the exact code and status pairs the live service returns, then add parametrised cases for 400, 404, 429 and a bare 401, each expected to be inconclusive.

## Info

### IN-01: `begin_read_only` cannot tell whether the guard took effect

**File:** `backend/supabase_store.py:346-356`
**Issue:** The function only assigns `conn.autocommit = False` and `conn.read_only = True`. On a psycopg `Connection` that works. On any `connect_fn` that returns an object without those attributes, the assignments silently create plain attributes and nothing is read-only. The callers' fake connections do exactly that. The tests therefore prove that the attributes are set, not that the first statement runs under `BEGIN READ ONLY`. The old `set default_transaction_read_only` design had the same blind spot, but it is now the only thing standing behind "read-only".
**Fix:** After the assignments, optionally assert it with a statement the fake can answer, for example `conn.execute("show transaction_read_only").fetchone()[0] == "on"`, and raise `StoreError` if it is not. Alternatively, keep the code as it is and add one real-Postgres test, since `local_pg` already exists, that runs a `create table` inside `begin_read_only` and expects `ReadOnlySqlTransaction`. The fix report says this was checked by hand and not committed.

### IN-02: `public_role_privileges` ignores sequences

**File:** `supabase/ops/verify_exposure.sql:59-71`
**Issue:** The `relkind in ('r','p','v','m','f')` filter leaves out sequences (`'S'`). `has_sequence_privilege` is not consulted, so `anon` holding UPDATE or USAGE on a public sequence would not show up. The grants CTE reads `relacl` for all relations (including sequences) via the existing grants check. The new check, which claims to cover "write ... privileges", has this gap, and the only protection against it is the older relacl-based check. This is minor because the rating tables have no serial default.
**Fix:** Add `'S'` to the relkind list and test `has_sequence_privilege(r.rolname, c.oid, 'usage, update')` for those rows, or state in the comment that sequences are covered by the relacl check only.

### IN-03: Two small robustness gaps in the hardened checks

**File:** `backend/e2e_verify_readonly.py:322-327`, `backend/supabase_rest.py:241-243`
**Issue:**
1. A 404 with PGRST205 passes `hidden:public.pipeline_run`. That is also what a renamed or mistyped table would return, so the check passes vacuously if the table is ever renamed. The SQL check `pipeline_run_not_readable_by_anon` covers this, but only when it is run.
2. `_DEFAULT_OPENER = urllib.request.build_opener(_SameHostRedirects)` is built at import time. It reads the proxy environment once, before `load_dotenv()` runs under `__main__`. A proxy set in `.env` would be ignored, where `urlopen` read the environment lazily. This is a behaviour change from the `urlopen` default, with no security impact.
**Fix:** For (1), note in the runbook that the SQL check is the authority for "table exists and is private". For (2), build the opener lazily inside `request()`, or accept the change and document it.

---

_Reviewed: 2026-11-01_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
