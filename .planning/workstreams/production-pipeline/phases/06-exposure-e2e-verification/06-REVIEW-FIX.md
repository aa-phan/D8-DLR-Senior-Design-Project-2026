---
phase: 06-exposure-e2e-verification
fixed_at: 2026-11-01T00:00:00Z
review_path: .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 6: Code Review Fix Report

**Fixed at:** 2026-11-01
**Source review:** .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (critical 0, warning 6; the 6 Info findings are out of scope for `critical_warning`)
- Fixed: 6
- Skipped: 0

Neither applied migration was touched (their SHA-256 pins in `expose_migration_test.py` still pass). No new migration was added. Nothing was applied to or run against the live project, no `.env` was read, and nothing was pushed. Commits are local on `main`.

## Fixed Issues

### WR-01: `verify_exposure.sql` cannot see column-level grants or inherited privileges

**Files modified:** `supabase/ops/verify_exposure.sql`, `backend/tests/expose_migration_test.py`
**Commit:** d5bddba
**Applied fix:** Added a CTE `public_role_privileges` and a new check row `anon_authenticated_hold_no_write_or_column_privilege_in_public`. It asks `has_table_privilege` and `has_any_column_privilege` for `anon` and `authenticated` on every relation in `public`, so column-level grants and privileges inherited through role membership are caught. Write, truncate, references and trigger are refused everywhere. Column-level SELECT is refused on everything except the two published objects. The file is still one read-only SELECT. A new test plants a column-level update, a column-level insert, a column-level select on `pipeline_run` and a write privilege inherited through a role. In each case exactly the new check goes false while the old grants check stays true. The two existing "checks can fail" expectations now include the new check name.

Owner note: `verify_exposure.sql` now returns 18 rows, not 17. The phase 06-09 and 06-13 docs say "17 checks"; those are history and were not edited. On the live database the new check should come back `ok = true` if the privilege list is as pinned. The owner should confirm that on the next run.

### WR-02: Refusal checks can pass for the wrong reason (invalid key, missing table, 5xx)

**Files modified:** `backend/e2e_verify_readonly.py`, `backend/tests/e2e_readonly_test.py`
**Commit:** 99674cd
**Status:** fixed: requires human verification (logic change in a verification tool)
**Applied fix:**
- `check_hidden` first reads `latest_rating` (limit 1) with the same key. If that is not a 200, it returns one `key_sanity` failure and trusts no refusal.
- A hidden answer now passes only as 401 or 403 with code `42501`, or as 404 or 406 with `PGRST205`, `PGRST106` or `PGRST202`. A bare 401 "Invalid API key", a code-less 404 and any 5xx are inconclusive and fail. The detail now shows the status and code.
- `_classify_view_write` passes only on a 4xx, and also on HTTP 500 carrying the database's own `55000` or `42501`. Any other 5xx (a gateway timeout, say) is inconclusive and fails.
- `--check-writes` needed no extra sanity read: its `snapshot_before` already fails on a bad key.
- The module docstring is updated and the tests are extended. The old `500 -> pass` expectation is replaced.

Deviation from the review's suggested fix: the review said "only a 4xx refuses" a view write. The live evidence in `06-13-SUMMARY.md` and `06-SOAK-REPORT.md` shows the real service refuses `view_insert` and `view_patch` with HTTP 500 and code `55000` (the view is not updatable). A pure 4xx rule would turn every live run red, so a 5xx is accepted only when it carries `55000` or `42501`. Please confirm that reading of the live behaviour.

### WR-03: Detector exception text is published to `anon`, and the docs say none is stored

**Files modified:** `backend/supabase_store.py`, `backend/tests/supabase_store_test.py`, `docs/integration/rest-api.md`, `docs/data-science/schema/city_rating_v1.md`
**Commit:** 29aa85c
**Applied fix:** Kept minimal, as instructed. `build_rating_row` (the review calls it `build_city_row`) now runs each alert through `supabase_store.redact` (the default 300-character cap) before it is stored. Gate names are taken from the redacted list, and the first token of an alert is unchanged. `DLRSafetyMonitor.py` was NOT changed, so a G6 alert can still carry a short raw exception message, minus credentials and URLs. Redaction removes credentials, `postgres://` URLs and `key=value` secrets. It does not remove file paths. Because of that, the two doc sentences claiming "no file path, no credential, no error text" were softened to say what is true: no credential, each `alerts` entry redacted and cut to 300 characters, and a detector failure can still carry a short error message. A new test plants a URL and a password in an alert and checks they are removed, that a long alert is cut to 300, and that the gates are still correct. The planted URL is built from pieces so `secret_scan_test.py` passes.

**Owner follow-up (not done here):** rows already stored in `public.city_rating.alerts` may still contain unredacted text. They need a one-off owner check, for example `alerts::text like '%detector error%'`, and an owner UPDATE if anything turns up. The reviewer's other suggestion, reporting only the exception type in `DLRSafetyMonitor.py` (`detector error (<TypeName>)`), was left out to keep the production change minimal. It is the only change that would also keep file paths out of the column.

### WR-04: The read-only session guard does not hold on a transaction-pooler URL

**Files modified:** `backend/supabase_store.py`, `backend/e2e_trace.py`, `backend/e2e_soak_report.py`, `backend/tests/supabase_store_test.py`, `backend/tests/e2e_trace_test.py`, `backend/tests/e2e_soak_report_test.py`
**Commit:** e8ab256
**Applied fix:** Added `supabase_store.begin_read_only(conn)` (sets `autocommit = False` and `read_only = True`, so every statement runs in `BEGIN READ ONLY`). Both tools call it instead of `set default_transaction_read_only = on`, run all their reads in that one transaction and `rollback()` afterwards. The soak export rolls back before the slow `gh` call so no transaction sits idle during it. The docstrings and comments now say "read-only transaction". The fake connections in the tests gained `autocommit`, `read_only` and `rollback`, and the tests assert those instead of a first `SET` statement. I also checked against a real local Postgres, with a throwaway test that was not committed: a `create table` inside `begin_read_only` raised `ReadOnlySqlTransaction`. The `set statement_timeout` and `set timezone` in `connect()` are session-level and were left alone, as the review noted they share the pooler issue.

### WR-05: The soak "late run" rule explains exactly the breach it detects

**Files modified:** `backend/e2e_soak_report.py`, `backend/tests/e2e_soak_report_test.py`, `docs/data-science/decisions/dlr_live_runbook.md`
**Commit:** f65062c
**Status:** fixed: requires human verification (changes a pass/fail rule)
**Applied fix:** A cause that starts with `late run:` is still computed and shown, but it no longer satisfies the pass condition. A new `_needs_annotation(b)` treats a breach as unexplained when it has no owner annotation and either no cause or a lateness-only cause. The failure line reads "explained only by lateness (...), which is the breach itself, so it needs an owner annotation". The report table marks such a breach "lateness only: needs an owner annotation". When the owner annotates it, the annotation counts and the cause stays visible beside it. The module docstring and the runbook "Reading the report" paragraph were updated. Tests: the 90 min + 2 s and 90 min + 6 s cases now exit 1 (they exited 0 before). The late-run case was removed from the "cause explains the breach" test and a new test covers both the failure and the annotated pass. The 72 h soak that already ran had 0 breaches, so its verdict is unaffected.

### WR-06: `http://` accepted for any host, the error message says https, and `apikey` follows redirects

**Files modified:** `backend/supabase_rest.py`, `backend/tests/e2e_readonly_test.py`
**Commit:** efe3fbd
**Applied fix:** `config_from_env` now accepts `https://` for any host and `http://` only for `127.0.0.1`, `localhost` or `::1` (the fake server the tests use), so the "must start with https://" message is now true. The default opener is built with a redirect handler that follows a redirect only within the same scheme, host and port. A refused redirect comes back as the 3xx answer itself, so the key never reaches another host. A caller-supplied `opener` is unchanged. New tests cover plain http to a remote host (including a look-alike `127.0.0.1.example.invalid`), accepted https and loopback URLs, and a real redirect to a different host name, which received zero requests.

## Verification

Ran in the isolated worktree under `.claude/worktrees/`, not the main checkout, with `/Users/aphan/Senior_Design/.venv/bin/python` from `backend/` and `DLR_TEST_PG_AUTOSTART=1` (a local throwaway Postgres; nothing live). After the fast-forward the commits are on `main` and the worktree was removed, so the figures can be reproduced from the main checkout.

Full Phase 6 set (`secret_scan_test`, `e2e_readonly_test`, `e2e_trace_test`, `e2e_soak_report_test`, `example_read_ratings_test`, `rest_api_doc_test`, `monitoring_runbook_test`, `expose_migration_test`, `soak_log_migration_test`, `supabase_smoke_test`) plus `supabase_store_test`: **285 passed, 1 skipped, 0 failed**. The one skip was not investigated; it is most likely a test that needs a live setting. Each finding's own tests were also run after its fix. Tier 1 (re-read) and the tests were the verification; no separate syntax checker was needed.

## Skipped Issues

None.

## Not in scope (Info findings, `fix_scope=critical_warning`)

IN-01 to IN-06 were not attempted. IN-01 would need a new additive migration or a runbook note. The `06-REVIEW-DISPOSITION.md` rows for WR-01 to WR-06 are still `open`; the orchestrator should move them to `fixed` with the commits above.

---

_Fixed: 2026-11-01_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
