---
phase: 04-supabase-store-writer
reviewed: 2026-10-23T00:00:00Z
depth: standard
files_reviewed: 29
files_reviewed_list:
  - .github/workflows/supabase_smoke.yml
  - .gitignore
  - backend/city_pipeline.py
  - backend/config.py
  - backend/dlr_orchestrator.py
  - backend/historical_archive.py
  - backend/supabase_load_backfill.py
  - backend/supabase_smoke.py
  - backend/supabase_store.py
  - backend/tests/city_pipeline_test.py
  - backend/tests/rating_identity_test.py
  - backend/tests/secret_scan_test.py
  - backend/tests/supabase_live_test.py
  - backend/tests/supabase_load_backfill_test.py
  - backend/tests/supabase_migration_test.py
  - backend/tests/supabase_orchestrator_test.py
  - backend/tests/supabase_run_log_test.py
  - backend/tests/supabase_schema_doc_test.py
  - backend/tests/supabase_smoke_test.py
  - backend/tests/supabase_store_test.py
  - docs/data-science/decisions/pss_e_handoff.md
  - docs/data-science/decisions/supabase_store/backfill_parity.json
  - docs/data-science/decisions/supabase_store/smoke_actions.json
  - docs/data-science/decisions/supabase_store/smoke_after_backfill.json
  - docs/data-science/decisions/supabase_store/smoke_local.json
  - docs/data-science/schema/city_rating_v1.md
  - docs/frontend/specs/api-contract.md
  - requirements.txt
  - supabase/migrations/20261019000000_create_city_rating.sql
findings:
  critical: 1
  warning: 5
  info: 6
  total: 12
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-10-23
**Depth:** standard
**Files Reviewed:** 29
**Status:** issues_found

## Summary

Reviewed the Supabase store, writer, backfill loader, smoke test, migration, workflow and the orchestrator / pipeline / archive changes. The local test set for this phase passes (114 passed, 43 skipped; the skips are the live-Postgres tests that need `DLR_TEST_PG_AUTOSTART=1`). The store is generally careful: parameterized SQL with identifiers taken only from fixed tuples, redaction on every error path, a transactional smoke test, and a backfill that is all-or-nothing. The committed evidence JSON files hold no host, URL, project reference or credential.

The main concern is a secret-hygiene (DB-04) hole on the success path: `connect()` logs the client-side connection user, which for the Supabase session pooler is `dlr_writer.<project_ref>`. Every other path is redacted and tested; this one is not. The warnings are about run-health reporting (partial failures exit 0, a cleaning failure is counted as a healthy cold start), no reconnect on a long-lived connection, and a latent backfill/clean-up inconsistency.

## Critical Issues

### CR-01: `connect()` logs the pooler user, which carries the Supabase project reference

**File:** `backend/supabase_store.py:297`
**Issue:** `log.info("connected to Postgres as %s", conn.info.user)`. `ConnectionInfo.user` is libpq's `PQuser`, the user name the client supplied in the URL, not the server's `current_user`. For the Supabase session pooler (the only supported connection form, see the module docstring) that is `dlr_writer.<project_ref>`. The module docstring and DB-04 state that the project reference must never reach a log or message, and `_connection_identifiers` deliberately strips exactly that suffix from failure text. `dlr_orchestrator.main` calls `logging.basicConfig(level=logging.INFO)`, so `--store postgres` runs (including the scheduled GitHub Actions runner in Phase 5) will print `connected to Postgres as dlr_writer.<ref>` into the Actions log. The smoke workflow does not show it only because `supabase_smoke.py` never configures logging (the INFO record is dropped). The failure-path test (`test_connection_failure_does_not_leak_the_password`) and the smoke evidence (`no_connection_details_in_log`) do not cover the success path, so the leak is untested.
**Fix:** Log the role the server reports, or nothing:
```python
role = conn.execute("select current_user").fetchone()[0]   # 'dlr_writer', no project ref
log.info("connected to Postgres as %s", role)
```
Add a test that connects (or uses a fake connection whose `info.user` is `dlr_writer.projref`) with `caplog` at INFO and asserts the project reference is absent from `caplog.text`.

## Warnings

### WR-01: A run that fails to write some cities exits 0

**File:** `backend/dlr_orchestrator.py:351` (and `_run_cities_with_store`, lines 354-358)
**Issue:** `return 1 if run["errors"] and not run["summary"] else 0`. With a store, a city whose rating row could not be written (or that failed outright) is recorded in `errors` and has no row (OD-9), but the process still exits 0 as long as at least one other city succeeded. A scheduled CI job therefore stays green while a city silently has no row for the hour. The only trace is the `pipeline_run` row and log text. The condition was acceptable for the CSV archive (nothing downstream depended on a row), but the store makes a missing row a data gap for the public consumer table. `--no-run-row` children make it worse: the runner has no signal except the exit code.
**Fix:** With `--store postgres`, return non-zero when any city failed to write:
```python
if run.get("run_log_error"):
    return 1
if args.store == "postgres" and run["errors"]:
    return 1
return 1 if run["errors"] and not run["summary"] else 0
```
(or return a distinct exit code for "partial") and update `supabase_orchestrator_test.py` line 475-495 accordingly.

### WR-02: A data-cleaning failure is reported as a healthy `cold_start`

**File:** `backend/city_pipeline.py:83-89`, `backend/supabase_store.py:79,748`
**Issue:** When `clean_history` raises, the history is replaced by an empty frame, the forecast sees zero rows and returns `None`, and `forecast_status` becomes `"cold_start"`. `_HEALTHY_FORECAST_STATUSES = ("ok", "cold_start")` then puts the city in `cities_ok` (provided a detector model loaded). A cleaning bug that discards all 30 days of history is thus indistinguishable from a legitimately new city in both `city_rating.forecast_status` and the run log; only `usable_history_rows = 0` against a non-zero `history_rows` hints at it. This is the failure the run log exists to surface.
**Fix:** Mark the cleaning failure explicitly, e.g. set `forecast_status = "failed"` (the table CHECK already allows it) when `cleaned is None` and `total_rows > 0`, or add a `cleaning_failed` flag to `pipeline` and treat it as `degraded` in `build_run_row`.

### WR-03: No reconnect or retry on the long-lived connection

**File:** `backend/supabase_store.py:256-298`, `backend/dlr_orchestrator.py:308-384`
**Issue:** One connection is opened before the per-city loop and held while each city does weather probing (Synoptic probes include sleeps and retries). The pooler or the network can drop an idle session; the first `read_history` then raises `OperationalError` (wrapped as `StoreError`), and every remaining city fails the same way because nothing reopens the connection. The final `record_run` fails on the same dead connection, so the run leaves no row at all, not even the failure record (OD-9 says that row is the only record for a city without a rating row).
**Fix:** In `SupabaseStore`, detect `conn.closed`/`conn.broken` (or catch `psycopg.OperationalError`) in `read_history`, `write_rating` and `record_run`, reconnect once with the stored URL, and retry the operation; or open a fresh connection for `record_run`.

### WR-04: Backfill de-duplication keeps the first row, the opposite of the CSV rule it cites

**File:** `backend/supabase_load_backfill.py:315-319`
**Issue:** The docstring says the first row in file order wins ("Phase 2's `duplicate` rule and the CSV's first-write-wins"). But `historical_archive` (this phase's own docstring change, lines 447-456) states that a computed row after a fallback row owns the instant, and `_slot_archived` implements it, so the read-side cleaning keeps the first *computed* row. If an archive holds a fallback row followed by a computed row for one slot, the loader stores the fallback row and drops the computed one, giving Postgres a different row than `clean_history` would have kept. The committed archive has `duplicates_dropped: 0` for every city so the data is unaffected today, but the rule is wrong for any re-run on a different archive and the docstring is misleading.
**Fix:** Sort so computed rows precede fallback rows within a (city, instant) group before `duplicated(keep="first")` (stable sort on `_parse_fallback(fallback)`), or reuse `data_cleaning`'s duplicate flag directly; update the docstring.

### WR-05: Backfill identity child is coupled to every module-level config read in live code

**File:** `backend/supabase_load_backfill.py:189-200, 242-245`
**Issue:** The child process imports `supabase_store` from the live `backend/` directory but `config`, `city_point` and `thermal_model` from the Phase 3 copies. `supabase_store` (and `ampacity_forecast`, `historical_archive`, `ercot_dlr_merger` which it imports) are evaluated against the old `config`. Any future live module that reads a new `config.<NAME>` at import time (the way `config.DB_HISTORY_WINDOW_DAYS` and `RATING_BASIS` are currently read only inside functions) makes the child exit non-zero, and the loader reports "could not evaluate the Phase 3 config fingerprints" with no hint why. Phase 7 is explicitly going to change config, so this is a near-term break of the backfill re-run path, and the failure shows only the last stderr line.
**Fix:** Add a test that runs `phase3_config_fingerprints` against a git-shown copy of an older `config.py` that lacks every constant added after the manifest head (not the working-tree copy the current test uses), and surface the full child stderr (redacted) on failure.

## Info

### IN-01: `_RUN_ERROR_MAX_CHARS = 1000` is dead; error text is cut to 300 characters

**File:** `backend/supabase_store.py:77,757`, docstring at 735-736
**Issue:** `redact()` truncates to `_MAX_MESSAGE_CHARS = 300` before `[:_RUN_ERROR_MAX_CHARS]` is applied, so the stored error is at most 300 characters while the docstring and the constant say 1000. `_redact_keys` has the same effect on provider-error keys (two distinct keys that share a 300-char prefix collapse into one dict entry and lose a count).
**Fix:** Give `redact` a `limit` parameter (default 300) and pass `limit=_RUN_ERROR_MAX_CHARS` here, or delete the constant and fix the docstring.

### IN-02: `connect()` validates the stripped URL but connects with the unstripped one

**File:** `backend/supabase_store.py:266,279`
**Issue:** `str(url).strip()` is only used for the emptiness check. A secret pasted with a trailing newline (common for GitHub secrets) is passed to libpq with the newline, which becomes part of the database name and fails with a confusing message.
**Fix:** `url = str(url).strip()` after the emptiness check, before `_url_secrets(url)`.

### IN-03: Column comments in the migration disagree with the code and the schema doc

**File:** `supabase/migrations/20261019000000_create_city_rating.sql:179-180`
**Issue:** `pipeline_run.cities_ok` is commented "cities whose rating row was written" but a written city that is degraded is in `cities_failed`; `cities_failed` is commented "city to error text" but the value is an object (`outcome`, `written`, `forecast_status`, `detector_model_loaded`, `error`). `docs/data-science/schema/city_rating_v1.md` lines 176-177 describe it correctly. The database comments are what Studio and `\d+` show.
**Fix:** Align the comments with the schema doc in a new migration (do not edit an applied one).

### IN-04: Duplicated and cross-module private helpers

**File:** `backend/supabase_load_backfill.py:106-112, 309-310, 349-352`; `backend/supabase_store.py:535-541`
**Issue:** `sha256_file` duplicates `supabase_store.file_sha256`; the loader reaches into `supabase_store._finite`, a private function.
**Fix:** Call `supabase_store.file_sha256` and make `_finite` public (`finite`).

### IN-05: Workflow hardening

**File:** `.github/workflows/supabase_smoke.yml:27-28`
**Issue:** Actions are pinned to mutable tags (`@v4`, `@v5`) in a job that holds the production writer secret; `actions/checkout` also keeps its token in `.git/config` (`persist-credentials` defaults to true). `workflow_dispatch` can be run against any branch, so a branch edit of `backend/supabase_smoke.py` by anyone with write access runs with `SUPABASE_DB_URL`. This is standard GitHub behaviour but is worth bounding for a production credential.
**Fix:** Pin by commit SHA, add `persist-credentials: false`, and consider an `if: github.ref == 'refs/heads/main'` guard or a protected environment holding the secret.

### IN-06: `valid_time` CHECK depends on the session time zone

**File:** `supabase/migrations/20261019000000_create_city_rating.sql:26`
**Issue:** `date_trunc('hour', valid_time)` on `timestamptz` is evaluated in the session time zone. `connect()` pins `timezone = 'UTC'`, which fixes the writer, but any other session (Studio SQL editor, a manual correction, a Phase 6 job) in a zone with a 30 or 45 minute offset (e.g. Asia/Kolkata, Asia/Kathmandu) will reject valid UTC-hour slots. The smoke test also does not assert the pinned zone.
**Fix:** Use `check ((valid_time at time zone 'UTC') = date_trunc('hour', valid_time at time zone 'UTC'))`, which is zone independent (in a follow-up migration).

---

_Reviewed: 2026-10-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
