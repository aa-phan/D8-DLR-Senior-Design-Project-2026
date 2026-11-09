---
phase: 04-supabase-store-writer
fixed_at: 2026-10-24T00:00:00Z
review_path: /Users/aphan/Senior_Design/.planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-10-24
**Source review:** /Users/aphan/Senior_Design/.planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (WR-06, IN-07, IN-08, IN-09, IN-10; the 12 prior findings were already resolved and were not touched)
- Fixed: 5
- Skipped: 0

**Verification ran in:** the isolated worktree (`.claude/worktrees/rf-04-...`) using the main checkout's `.venv`, with `DLR_TEST_PG_AUTOSTART=1` (throwaway local Postgres, never Supabase). Full suite after all fixes: 1703 passed, 0 skipped (the 48 live-Postgres tests that were skipped at baseline ran). The numbers are reproducible from the main checkout once the commits are fast-forwarded onto `main`.

## Fixed Issues

### WR-06: Per-city exception text is redacted for the log and run row but printed and written to `--output` raw

**Files modified:** `backend/dlr_orchestrator.py`, `backend/tests/dlr_orchestrator_test.py`, `backend/tests/supabase_orchestrator_test.py`
**Commit:** b532c00
**Applied fix:** `out["errors"][name]` now holds `supabase_store.redact(exc)` on both the postgres path and the CSV path, so the printed report and the `--output` JSON carry only redacted text; the CSV-path log line is redacted too. The CSV path reaches `redact` through a small `_redacted()` helper that imports `supabase_store` lazily, so a clean CSV run still never loads the store module. `record["error"]` (internal, never printed) keeps the raw text so `build_run_row` can still redact and keep up to 1000 characters; passing the 300-character redacted text would have shortened stored run-row errors. Failing-first tests: a `token=s3cr3tv` exception yields `token=REDACTED` in `run["errors"]` and in `_print_report` output (store path) and in `run["errors"]` and the log (CSV path).

### IN-07: A failed forecast is recorded as a degraded city with no reason

**Files modified:** `backend/city_pipeline.py`, `backend/dlr_orchestrator.py`, `backend/tests/city_pipeline_test.py`, `backend/tests/supabase_orchestrator_test.py`, `docs/data-science/schema/city_rating_v1.md`
**Commit:** 9c5b6f3
**Applied fix:** `run_city_pipeline` adds `forecast_error` (`"forecast failed: <exc>"`, else None) to the `pipeline` block. The orchestrator stores `cleaning_error or forecast_error` in the city record, so a degraded city from a failed forecast carries a redacted reason in `pipeline_run.cities_failed`. A cleaning error is reported first because it is the root cause when both occur. The schema doc's run-log paragraph now covers forecast failures and the precedence. No column or migration change. Not done: the review's optional "consider exiting non-zero when every written city is degraded". That changes documented exit semantics beyond the finding and was left for an owner decision.

### IN-08: A cleaning failure on an empty history is dropped from the run row

**Files modified:** `backend/supabase_store.py`, `backend/tests/supabase_orchestrator_test.py`, `backend/tests/supabase_run_log_test.py`, `docs/data-science/schema/city_rating_v1.md`
**Commit:** 1ef738d
**Applied fix:** Took the review's first option. `build_run_row` now treats any non-None error on a written city as `degraded` (a city is in `cities_ok` only when written, forecast status healthy, detector model loaded, and no error), so the redacted cleaning error survives on a cold start. The `build_run_row` docstring and the schema doc state the rule. Tests: unit test on `build_run_row` and an orchestrator test where `forecast_status` stays `cold_start` and the city is degraded with its error. Status: fixed, requires human verification (a classification-logic change; the semantic choice is that a stored error on a written city always means degraded).

### IN-09: The manifest commit is passed to `git show` without validation

**Files modified:** `backend/supabase_load_backfill.py`, `backend/tests/supabase_load_backfill_test.py`
**Commit:** d3d59dc
**Applied fix:** `load_manifest` raises `ValueError` ("manifest git.head is not a 40-character lowercase commit id") unless `git.head` is a string that `re.fullmatch`es `[0-9a-f]{40}`. Parametrized test covers an option-like value, short id, empty, uppercase, trailing newline, ref name, int and null; a positive test covers a valid id. The test fixture `_HEAD` changed from a 13-character placeholder to a 40-character hex string; the committed real manifest already holds a 40-character head.

### IN-10: Schema doc states the CSV archive keeps "the first write for an exact instant"

**Files modified:** `docs/data-science/schema/city_rating_v1.md`
**Commit:** c9b13f5
**Applied fix:** The sentence now reads "keeps the first computed write for an exact instant (a computed row may follow fallback rows and then owns the slot; otherwise the first write wins)". Doc-only; `supabase_schema_doc_test.py` and `supabase_migration_test.py` pass.

---

_Fixed: 2026-10-24_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
