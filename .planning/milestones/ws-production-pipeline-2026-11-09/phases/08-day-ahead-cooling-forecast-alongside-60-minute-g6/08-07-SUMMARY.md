---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
plan: 07
subsystem: database
tags: [day-ahead, supabase, migration, owner-gate, sha256-pin, postgres, pytest]

requires:
  - phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
    provides: "08-04 write-side migration 20261108120000_day_ahead_forecast_store.sql and verify_day_ahead_store.sql; 08-01..08-06 contract, stage and verifier code"
  - phase: 06-exposure-e2e-verification
    provides: "the owner's apply procedure (dry run, push, verify SQL, second dry run) and the sha256 pin pattern"
provides:
  - "Live write-side schema on the shared project: private public.day_ahead_forecast (25 columns, RLS on, insert-only writer) and pipeline_run.day_ahead jsonb, nothing exposed"
  - "Owner confirmation of the one-way day-ahead contract (D-09), recorded verbatim with the commit holding the contract file"
  - "08-07-PREFLIGHT.md: plain-English contract summary, discretion choices, owner commands"
  - "_APPLIED_STORE_MIGRATION_SHA256 and test_store_migration_is_unchanged_after_apply pinning the applied file"
affects: [08-08, 08-09, 08-10, 08-11, 08-12]

actuals:
  tokens: 9000
  tasks: 3
  commits: 2
plan_head_before: e6cda24cc37e191ba8b74f8410dfb5cb6ab928cc
plan_head_after: b8db2cb6df1bccf25e462bd06de477291577d254

tech-stack:
  added: []
  patterns:
    - "Applied migrations are pinned by sha256 in the default suite; fixes go in a new additive migration"
    - "Read-only store check (verify_day_ahead_store.sql) and exposure check (verify_exposure.sql) both run after the apply; a second dry run proves nothing is pending"

key-files:
  created:
    - .planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-07-PREFLIGHT.md
  modified:
    - backend/tests/day_ahead_migration_test.py

key-decisions:
  - "Owner confirmed the day-ahead contract as built (reply: confirm); table, view and status column names plus every discretion choice are now a coordinated-change contract"
  - "Applied migration pinned at sha256 fb5337a64318259320990fa7b7b19c32d584bcdefef24fad8b1855f0e21bf8f1; never edited again"

patterns-established:
  - "Owner live gate: preflight note, decision checkpoint, owner apply, read-only checks, sha256 pin commit"

requirements-completed: [DAY-05]

duration: "about 13h elapsed, dominated by the owner gates"
completed: 2026-11-08
status: complete
---

# Phase 8 Plan 07: Day-Ahead Write-Side Schema Applied Summary

**The private day-ahead forecast table and run-log column are live on the shared project (exactly one migration applied, all 28 store and exposure checks ok, nothing exposed), the contract is owner-confirmed, and the applied file is sha256-pinned in the default suite.**

## Performance

- **Duration:** about 13 h elapsed across the owner gates (active executor time is small)
- **Started:** 2026-11-08 (UTC)
- **Completed:** 2026-11-08
- **Tasks:** 3 (1 auto, 1 owner decision, 1 owner live apply with executor post-steps)
- **Files modified:** 2 (one created, one edited)

## Accomplishments

- Local rehearsal and a plain-English pre-flight note for the owner (commit ca352ed): contract as built, the numbered discretion choices, the owner's command lines with stand-ins only.
- D-09 one-way contract confirmed by the owner before the table existed on the live project.
- The owner applied only `20261108120000_day_ahead_forecast_store.sql`; both read-only check files returned every row ok; a second dry run showed nothing pending.
- The applied file's sha256 is pinned by `test_store_migration_is_unchanged_after_apply` (commit b8db2cb), so a later edit fails the default suite (T-08-21).

## Task Commits

1. **Task 1: Local rehearsal and pre-flight note** - `ca352ed` (docs)
2. **Task 2: Owner confirms day-ahead contract (D-09)** - no commit; the decision is recorded below
3. **Task 3: Owner live apply, then the sha256 pin** - `b8db2cb` (test)

## Owner Decision (Task 2, D-09)

Owner reply, verbatim: `confirm` ("Confirm as built").

Commit holding `backend/day_ahead_contract.py` at the time of the decision: `14eb365` (HEAD was ca352ed, the file was clean). 08-11 checks the file is unchanged since that commit.

## Live Results (Task 3, run 2026-11-08 UTC)

Applied by the owner; the admin connection string was read from the owner's git-ignored `.env` and is not recorded here.

| Step | Result |
|---|---|
| 1. Dry run (owner) | Pending listed exactly `20261108120000_day_ahead_forecast_store.sql` |
| 2. Push (owner) | Applied exactly `20261108120000_day_ahead_forecast_store.sql` |
| 3a. `verify_day_ahead_store.sql` | 10 rows, every `ok = true` (table below) |
| 3b. `verify_exposure.sql` | 18 rows, every `ok = true` (detail below) |
| 4. Optional AUSTIN `--no-store` check | Not run (optional); skipped |
| 5. Second dry run | `upToDate: true`, `dryRun: true`, `migrations: []`, "Remote database is up to date.", exit 0 |

`verify_day_ahead_store.sql` (all ok):

| check_name | detail |
|---|---|
| day_ahead_forecast_columns_all_commented | none uncommented |
| day_ahead_forecast_exists | ok |
| day_ahead_forecast_has_25_columns | 25 |
| day_ahead_forecast_not_readable_by_anon_or_authenticated | anon and authenticated select = false |
| day_ahead_forecast_primary_key_city_valid_time | (city, valid_time) |
| day_ahead_forecast_rls_enabled | ok |
| dlr_writer_can_select_and_insert_day_ahead_forecast | select = true, insert = true |
| dlr_writer_cannot_update_delete_or_truncate_day_ahead_forecast | all false |
| pipeline_run_has_day_ahead_jsonb | jsonb |
| pipeline_run_not_readable_by_anon | ok |

`verify_exposure.sql` (all 18 ok, nothing new exposed): anon and authenticated hold SELECT on the two existing exposed objects only (4 of 4 grants); no write or column privileges; `latest_rating` has 34 columns, 4 cities, one row per city, security_invoker; no write policy for public roles; `pipeline_run` not readable by anon; `city_rating` policies are `city_rating_public_read` (SELECT) and `dlr_writer_all` (ALL).

## Post-Apply Pin (executor)

- `shasum -a 256` of the migration file: `fb5337a64318259320990fa7b7b19c32d584bcdefef24fad8b1855f0e21bf8f1`.
- Added `_APPLIED_STORE_MIGRATION_SHA256` and `test_store_migration_is_unchanged_after_apply` to `backend/tests/day_ahead_migration_test.py`, following the 06-09 pattern.
- `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/day_ahead_migration_test.py backend/tests/secret_scan_test.py`: 30 passed, 1 skipped. The one skip is the secret-scan owner-local check (needs `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_DB_URL` exported in a shell); no DLR_TEST_PG_AUTOSTART or initdb skip.
- `-k unchanged_after_apply`: 1 passed.

## Deviations from Plan

None - the plan executed as written (the discrepancies below concern who ran which owner step, not the executor's code).

## Discrepancies

- Steps 1 and 2 (dry run and push) were run by the owner, who confirmed verbally that the dry run listed exactly `20261108120000_day_ahead_forecast_store.sql` ("that's what it showed") and that the push applied exactly that file. The outputs were not pasted.
- Steps 3 (both SQL check files) and 5 (second dry run) were run by the orchestrator at the owner's explicit request, not by the owner. They were read-only; the admin URL was read from `.env` and never printed. The plan's resume signal asked the owner for both result tables; the results above are from the orchestrator's runs.
- Step 4 (optional no-store check of AUSTIN) was skipped.
- DAY-08 is only partly met by this plan (steps 1-2 of the go-live: contract confirmed, write-side migration applied), so only DAY-05 is listed as completed here.

## Known Stubs

None.

## Threat Flags

None. The live change is the planned private table and run-log column; nothing was exposed (confirmed by `verify_exposure.sql`). No URL, host, project reference or key appears in this summary or the pre-flight note (T-08-22).

## Issues Encountered

None.

## Next Phase Readiness

- The write-side schema exists, so the code that writes it can be pushed (08-08) without a missing-column failure.
- Nothing is exposed or written yet; the expose migration (08-09) and the first live slot (08-10) follow, with 08-11 checking the contract file is unchanged since `14eb365`.
- Nothing was pushed by this plan.

## Self-Check: PASSED

- FOUND: backend/tests/day_ahead_migration_test.py (contains `_APPLIED_STORE_MIGRATION_SHA256`)
- FOUND: 08-07-PREFLIGHT.md
- FOUND commits: ca352ed, b8db2cb
