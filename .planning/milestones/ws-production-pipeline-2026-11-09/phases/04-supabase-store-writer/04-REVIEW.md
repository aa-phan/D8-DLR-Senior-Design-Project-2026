---
phase: 04-supabase-store-writer
reviewed: 2026-10-24T12:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - backend/city_pipeline.py
  - backend/dlr_orchestrator.py
  - backend/supabase_load_backfill.py
  - backend/supabase_store.py
  - backend/tests/city_pipeline_test.py
  - backend/tests/dlr_orchestrator_test.py
  - backend/tests/supabase_load_backfill_test.py
  - backend/tests/supabase_orchestrator_test.py
  - backend/tests/supabase_run_log_test.py
  - docs/data-science/schema/city_rating_v1.md
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: issues_found
---

# Phase 4: Code Review Report (re-review after fix commits b532c00, 9c5b6f3, 1ef738d, d3d59dc, c9b13f5)

**Reviewed:** 2026-10-24
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Re-review of the five fix commits since `defa76d` (`git diff defa76d HEAD` over the ten listed files). All five prior findings (WR-06, IN-07, IN-08, IN-09, IN-10) are resolved in the current source. The five fixes introduced no regression I could demonstrate.

Checks beyond reading the diff:

- The related test files (`city_pipeline_test`, `dlr_orchestrator_test`, `supabase_load_backfill_test`, `supabase_orchestrator_test`, `supabase_run_log_test`, `supabase_schema_doc_test`) pass with the Supabase URL variables unset. The live-Postgres tests skipped, as expected. No database or `.env` was touched.
- IN-08 would have made every cold start degraded if `clean_history` raised on an empty history. It does not. `store.read_history` returns `pd.DataFrame(columns=ARCHIVE_COLUMNS)` for no rows (`supabase_store.py:806`), and `data_cleaning.clean_history` on that frame returns 0 usable rows without raising. A healthy cold start therefore stays in `cities_ok`.
- The committed manifest `docs/data-science/decisions/real_data_validation/manifest.json` holds a 40-character lowercase `git.head`, so IN-09 does not reject the real input. `real_data_validation.py:1600` writes `git rev-parse HEAD`, which is the same shape.
- `redact` cannot raise on a malformed `SUPABASE_DB_URL` (`_url_secrets` catches the `urlsplit` `ValueError`). Calling it from an `except` handler is therefore safe.
- `write_rating` returns True or raises (`supabase_store.py:891-895`), so a city that was not written always has an entry in `errors`. The postgres exit-1 rule cannot miss an unwritten city.

No critical issue and no warning. Two info items remain: one stale database column comment that the IN-08 semantic change made incomplete, and one message-quality gap on the lines the WR-06 fix touched.

## Prior Findings Verification

| Prior ID | Verdict | Evidence file:line |
|----------|---------|--------------------|
| WR-06 | resolved | `backend/dlr_orchestrator.py:206-208` (CSV path: `_redacted(exc)` feeds the log line and `out["errors"][name]`), `:287-289` (store path: `supabase_store.redact(exc)` feeds the log line and `out["errors"][name]`), `:52-61` (`_redacted` helper, lazy import). `_print_report` (`:336-337`) and the `--output` JSON (`:382-384`) now read only redacted text. `record["error"] = str(exc)` at `:293` stays raw by design. It never reaches stdout or `--output`, and `build_run_row` redacts it at `supabase_store.py:706`. Tests: `dlr_orchestrator_test.py` `test_a_failing_city_error_is_redacted_on_the_csv_path`, `supabase_orchestrator_test.py` `test_a_failing_city_error_is_redacted_in_the_run_summary_and_the_printed_report`. |
| IN-07 | resolved | `backend/city_pipeline.py:88,93` set `forecast_error = "forecast failed: <exc>"`, `:151` exposes it in the `pipeline` block. `backend/dlr_orchestrator.py:274` stores `cleaning_error or forecast_error` in the city record. `supabase_store.py:698-706` redacts it into `cities_failed`. Tests: `city_pipeline_test.py` `test_a_forecast_failure_reports_its_reason`, `supabase_orchestrator_test.py` `test_a_forecast_failure_is_a_degraded_city_with_its_error_in_the_run_row` and `test_a_cleaning_error_wins_over_a_forecast_error_in_the_run_row`. |
| IN-08 | resolved | `backend/supabase_store.py:697-698` take `error` before the healthy test and require `error is None` for `cities_ok`, so an error on a written city is `degraded` even with `forecast_status == "cold_start"`. The `build_run_row` docstring (`:673-684`) and `docs/data-science/schema/city_rating_v1.md:181` state the rule. Tests: `supabase_run_log_test.py` `test_a_written_city_with_an_error_is_degraded_even_with_a_healthy_status`, `supabase_orchestrator_test.py` `test_a_cleaning_failure_on_empty_history_is_degraded_with_its_error`. The stale database comment is IN-11 below. |
| IN-09 | resolved | `backend/supabase_load_backfill.py:137-139` raise `ValueError` unless `git.head` is a string that `re.fullmatch`es `[0-9a-f]{40}`. This runs inside `load_manifest`, before `phase3_config_fingerprints` reads `manifest["git"]["head"]` (`:259`) and `_git_show` builds `f"{commit}:{path}"` (`:222-229`). `fullmatch` rejects the trailing-newline case. The one non-test caller of `load_manifest` is `:511` in `main`. Test: `supabase_load_backfill_test.py` `test_load_manifest_refuses_a_git_head_that_is_not_a_full_commit_id` (9 cases) and `test_load_manifest_accepts_a_full_commit_id`. |
| IN-10 | resolved | `docs/data-science/schema/city_rating_v1.md:35` now reads "keeps the first computed write for an exact instant (a computed row may follow fallback rows and then owns the slot; otherwise the first write wins)". That matches `historical_archive._slot_archived` (`backend/historical_archive.py:178-203`): a computed row is blocked only by an existing computed row, and a fallback row is blocked by any row. |

## Info

### IN-11: The live `pipeline_run.cities_ok` column comment omits the "no error" criterion that IN-08 added

**File:** `supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql:26` (code at `backend/supabase_store.py:698`)
**Issue:** The applied column comment defines `cities_ok` as "cities whose rating row was written healthily (forecast ok or cold_start and an anomaly model loaded)". After the IN-08 commit a written city is also excluded from `cities_ok` whenever it carries an error. Someone reading the column comment in the Supabase dashboard (or a Phase 5 consumer trusting it) would expect a cold-start city with a cleaning failure to be in `cities_ok`, but it is in `cities_failed` as `degraded`. The schema doc and the `build_run_row` docstring were updated; the comment stored in the database was not. Editing the 20261023 migration in place is not safe if it has been applied (IN-03's fix used an additive migration for the same reason, and the original is hash-pinned).
**Fix:** Add a later additive migration that re-issues the comment, for example:
```sql
comment on column public.pipeline_run.cities_ok is
  'none (labels): cities whose rating row was written healthily (forecast ok or cold_start, an anomaly model loaded and no cleaning or forecast error); a city that was written but degraded is in cities_failed, not here.';
```
Then align `docs/data-science/schema/city_rating_v1.md:176` and any test that pins the comment text with it.

### IN-12: A per-city exception with an empty message is recorded and printed as an empty string

**File:** `backend/dlr_orchestrator.py:206-208` and `:287-289` (printed at `:337`; run row at `:293`)
**Issue:** The handlers store `redact(exc)`, which is `str(exc)` after redaction. For an exception raised without a message (`AssertionError()`, `RuntimeError()`, a bare `raise KeyError`-style failure that stringifies to an empty or near-empty text), `out["errors"][name]` is `""`. `_print_report` then prints `ERROR AUSTIN: ` with no cause. On the store path `record["error"]` is `""`, so the run row stores `"error": ""`, which still says "outcome error" but gives no reason. The WR-06 change rewrote exactly these lines, so this is the natural place to fix it. The behavior predates the fix (it was `str(exc)` before).
**Fix:** Build the stored text from the type name as well:
```python
text = supabase_store.redact(f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__)
```
(and the same in `_redacted`, which would keep the redaction in one place). Update the two redaction tests only if they assert the exact string; the expected `"MIDLAND: GET /x?token=REDACTED failed"` would gain a `RuntimeError: ` prefix.

---

_Reviewed: 2026-10-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
