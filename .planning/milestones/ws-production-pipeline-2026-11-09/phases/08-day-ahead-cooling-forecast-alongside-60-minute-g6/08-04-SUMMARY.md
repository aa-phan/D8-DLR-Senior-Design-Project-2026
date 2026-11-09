---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
plan: 04
subsystem: infra
tags: [day-ahead, child-process, catch-up, redaction, postgres, rls, privileges, verify-sql, pytest]

requires:
  - phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
    provides: "08-01 day_ahead_forecast/day_ahead_band/day_ahead_contract and the write-side migration; 08-02 runner stage and the child contract; 08-03 band_for live-rolling branch"
  - phase: 04-supabase-store-and-writer
    provides: "supabase_store.connect/redact/run_context/upsert_run and the dlr_writer role"
provides:
  - "backend/dlr_day_ahead.py: the per-city child the runner starts (--city, --output, --no-store), catch-up from the table, refusal paths, redacted output JSON"
  - "backend/tests/dlr_day_ahead_test.py: 18 tests (contract, none_due, catchup, idempotent, no_substitute, redaction, no_store, out_of_bounds, output)"
  - "backend/tests/day_ahead_migration_test.py: 24 tests proving the write-side schema offline (text) and on local Postgres (privileges, CHECKs, run log, re-apply, store check)"
  - "supabase/ops/verify_day_ahead_store.sql: the owner's one-SELECT, 10-check read-only verification for after the 08-07 apply"
affects: [08-05, 08-06, 08-07, 08-08, 08-09, 08-10, 08-12]

actuals:
  tokens: 16600
  tasks: 2
  commits: 3
plan_head_before: e8ac7349165e8cf12adb62c6b5856931f75d603e
plan_head_after: 3013e23b9b66154c017a9c3a6f9becb697a73abd

tech-stack:
  added: []
  patterns:
    - "The table is the only state: a child computes due minus existing from the database on every run, so a missed run is repaired by the next one with no marker file"
    - "Trust before compute: band hash, model hash and the anchor reading are each verified or fetched once per run, and a refusal gives every missing target a named redacted reason and no row"
    - "Output document always written in a finally path, atomically (temp file then rename), exit 0 whatever the outcome"
    - "Privilege and constraint tests run as the real roles on a throwaway cluster migrated only through the write-side file; the owner's verify SQL is run on the same database and each check is shown to fail by a rolled-back wrong state"

key-files:
  created:
    - backend/dlr_day_ahead.py
    - backend/tests/dlr_day_ahead_test.py
    - backend/tests/day_ahead_migration_test.py
    - supabase/ops/verify_day_ahead_store.sql
  modified: []

key-decisions:
  - "The child calls day_ahead_band.load_verified_band() with its defaults, so until 08-05 pins the band artifact in the live manifest a real run refuses every target with 'no entry in the manifest' (outcome error, no row, exit 0). This is D-13a working as designed; tests use temporary manifests by wrapping the loader"
  - "With --no-store the outcome counts computed targets like issued ones, and the output carries dry_run true and a computed map; issued stays empty so a dry run can never be mistaken for rows written"
  - "A target whose key was stored by another run after this run read the table goes to already_present (first write wins) and does not count as a failure; if only such targets remain the outcome is none_due"
  - "Redaction replaces provider credential values from the environment itself and leaves database URLs to supabase_store.redact's default secrets, so the child reads no private name of supabase_store"
  - "Output is written to a temp file in the same directory and renamed, so a child killed mid-write leaves either the previous file or none, never half a JSON document"

patterns-established:
  - "Output-key contract tested both ways: the child's own keys equal the runner's required set, and dlr_live_run.classify_day_ahead on the real output returns the expected record"
  - "A mutation check by hand on the redaction test: emptying the credential list makes both redaction tests fail"

requirements-completed: [DAY-01, DAY-02, DAY-05]

coverage:
  - id: D1
    description: "Catch-up from the table (D-04): only due-minus-existing targets are fetched and inserted, earliest first, each with issued_at equal to the run's decision time; a second run is none_due with no fetch and no model load and leaves the first row unchanged"
    requirement: "DAY-01"
    verification:
      - kind: integration
        ref: "backend/tests/dlr_day_ahead_test.py -k 'none_due or catchup or idempotent'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Contract with the runner (D-02, D-15): the argv from dlr_live_run.day_ahead_child_argv is accepted, the output has exactly the runner's 11 keys, exit 0 whatever the outcome, classify_day_ahead returns issued; a bad city or missing argument is a usage error (2); an unwritable output is exit 1"
    requirement: "DAY-01"
    verification:
      - kind: integration
        ref: "backend/tests/dlr_day_ahead_test.py -k 'contract or output_path'"
        status: pass
    human_judgment: false
  - id: D3
    description: "No substitute (D-16, D-13a): a missing anchor, a band artifact that does not match the manifest (before any model loads), a manifest with no entry, a cooling model hash refusal, an unreachable database and one unavailable weather run each publish nothing for the affected targets with a named reason and use no other method"
    requirement: "DAY-02"
    verification:
      - kind: integration
        ref: "backend/tests/dlr_day_ahead_test.py -k 'no_substitute or database_that_cannot'"
        status: pass
    human_judgment: false
  - id: D4
    description: "Redaction (OD-6, T-08-11): a database URL, its password and host, and a provider token planted in a provider message never appear in the output file, the log or the table; unexpected errors are named by type and redacted; no table column can hold free text"
    requirement: "DAY-05"
    verification:
      - kind: integration
        ref: "backend/tests/dlr_day_ahead_test.py -k redaction"
        status: pass
    human_judgment: false
  - id: D5
    description: "--no-store never calls supabase_store.connect, uses the TEST band, inserts nothing and marks dry_run; an out-of-bounds value is still inserted and listed"
    requirement: "DAY-02"
    verification:
      - kind: integration
        ref: "backend/tests/dlr_day_ahead_test.py -k 'no_store or out_of_bounds'"
        status: pass
    human_judgment: false
  - id: D6
    description: "Write-side privileges and constraints on local Postgres (D-09, T-08-10, T-08-13): dlr_writer inserts and selects, a repeated key keeps the first write, update/delete/truncate fail with 42501; anon and authenticated cannot read (42501); eight bad rows each fail with 23514 on the named constraint; pipeline_run accepts a {run_id, day_ahead} upsert; every migration applies twice"
    requirement: "DAY-05"
    verification:
      - kind: integration
        ref: "backend/tests/day_ahead_migration_test.py -k 'writer or checks or anon or run_log or reapply'"
        status: pass
    human_judgment: false
  - id: D7
    description: "Text contract of the migration: exactly the 25 contract columns in order, the named CHECKs, RLS, revoke from anon and authenticated, exactly two grants, drop-before-create policy, no update/delete/truncate/password/URL, unit-first comment on every column and pipeline_run.day_ahead, sorts after the soak migration, adds every optional run-log column the writer names"
    requirement: "DAY-05"
    verification:
      - kind: unit
        ref: "backend/tests/day_ahead_migration_test.py -k text"
        status: pass
    human_judgment: false
  - id: D8
    description: "Owner's store check: verify_day_ahead_store.sql is one read-only SELECT of the 10 pinned checks, all ok on the write-side state; thirteen wrong states (public select grant, column grant, writer update/delete/truncate grant, missing insert, RLS off, empty comment, extra column, dropped key, dropped or retyped run-log column, dropped table) each turn exactly the matching checks false; Phase 6 verify_exposure.sql stays all ok"
    requirement: "DAY-05"
    verification:
      - kind: integration
        ref: "backend/tests/day_ahead_migration_test.py -k store_sql"
        status: pass
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_verify_exposure_sql_reports_every_check_ok"
        status: pass
    human_judgment: false

duration: 30min
completed: 2026-11-08
status: complete
---

# Phase 8 Plan 04: Per-City Day-Ahead Child and Write-Side Proof Summary

**`backend/dlr_day_ahead.py` turns the 08-01 functions into the catch-up child the runner starts: the table is its only state, a band file, cooling model or anchor it cannot trust gives no row and a redacted reason, and the write-side migration's privileges are proven on local Postgres with a one-query check for the owner.**

## Performance

- **Duration:** about 30 min (finished 2026-11-08T10:12Z)
- **Tasks:** 2 (both TDD-marked)
- **Files modified:** 4 (all created)

## Accomplishments

- **The child.** `main(argv=None, now=None)` computes the due grid targets, reads the city's future keys from `public.day_ahead_forecast` as `dlr_writer`, and issues only the missing ones, earliest first, each with `issued_at` equal to the run's decision time. Nothing missing is `none_due`: no model is loaded and nothing is fetched. A second run changes no stored row.
- **Trust before compute.** Order of refusal: database, band artifact (hashed against the manifest before it is parsed), cooling model (hash-verified loader), anchor reading (once per run). Each failure gives every missing target a named reason, publishes no row and uses no other method. One unavailable weather run gives `partial` and the other targets are still issued.
- **Contract with the runner.** The argv from `dlr_live_run.day_ahead_child_argv` parses unchanged, the output has exactly the runner's 11 keys (plus `dry_run` and `computed` only with `--no-store`), `classify_day_ahead` reads it as `issued`, and the exit code is 0 whenever the output was written.
- **Redaction.** Reasons go through the environment's provider credentials and the store's URL and key=value redaction, then a 300-character cut, before they are written or logged. The test plants a database URL (password and project host) and a token in a provider message and finds neither in the output file, the log or the table.
- **Write-side proof (D-09).** On a throwaway cluster migrated only through the write-side file: the writer inserts and selects, a repeated key keeps the first write, update, delete and truncate fail with 42501, anon and authenticated cannot read, eight bad rows fail with 23514 on the exact constraint, and `pipeline_run` takes a `{run_id, day_ahead}` upsert. The text tests compare the file with `day_ahead_contract` (columns, order, constraint names, grants, comments).
- **Owner's check.** `supabase/ops/verify_day_ahead_store.sql` is one read-only SELECT with 10 checks; privilege checks use the database's own privilege functions (so column-level and inherited privileges show) and a missing table or role turns a check false instead of raising. Thirteen deliberately wrong states each trip exactly the matching checks. The migration file was not edited.
- Full suite with local Postgres: **2830 passed, 0 failed, 0 skipped**. The Phase 4 and Phase 6 migration tests and `verify_exposure.sql` stay green with the new table present. Band artifact sha256 is still `19b9c522bea11862c6edb97085d5f121d3c389e2420500a5e50b4ec004a747ec` and `data/day_ahead` has no diff.

## Task Commits

1. **Task 1: per-city day-ahead child** - `0f7c0fc` (feat)
2. **Task 2: write-side migration and store check** - `847044f` (test)
3. **Fix found by the full suite: child redaction without a private store helper** - `3013e23` (fix)

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Notes

Both tasks carry `tdd="true"`; the plan is `type: execute` and prescribes one commit per task, so there is no separate RED commit.

- **Task 1 RED:** the test file was written first and run: collection stopped with `ModuleNotFoundError: No module named 'dlr_day_ahead'`. This is an import-level failure, not an assertion on planned behaviour (same note as 08-01). GREEN: 18 of 18 passed on the first run. A by-hand mutation (emptying the credential list in `_redact`) made both redaction tests fail, so they discriminate.
- **Task 2 RED:** the migration already existed (08-01), so the offline and privilege tests pinned existing behaviour and passed at once. The store-check tests were the new behaviour; the first run had one failure of the test itself (the read-only keyword scan matched the privilege names `'insert'` and `'update'` inside string literals), fixed by blanking literals before scanning. The "wrong state trips the matching check" cases are the discriminating tests for the SQL.

## Files Created/Modified

- `backend/dlr_day_ahead.py` - child CLI and `main`; `_Run` result holder, `_execute` flow, `_issue` per target, atomic `_write_output`, `_redact`
- `backend/tests/dlr_day_ahead_test.py` - 18 tests on local Postgres as `dlr_writer`, weather and anchor stubbed at the shadow leaves, the real hash-verified MIDLAND model
- `backend/tests/day_ahead_migration_test.py` - 24 tests: 8 text, 16 local Postgres (re-apply, writer, 8 constraint cases, valid variants, anon, run log, store check ok, store check failing states)
- `supabase/ops/verify_day_ahead_store.sql` - the owner's read-only check

## Decisions Made

- The child uses `load_verified_band()` defaults, so the live manifest must name the band artifact; until 08-05 a real run refuses every target (see key-decisions). `--no-store` is subject to the same check.
- Dry-run outcome counts computed targets like issued ones, with `issued` kept empty and `dry_run` set.
- A key stored by a racing run is `already_present`, not a failure.
- Credential redaction is the child's own; database URLs are left to the store's default secrets so no private store name is read.
- Output written atomically (temp file and rename).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Child read a private name of supabase_store**
- **Found during:** full-suite run after Task 2
- **Issue:** `_redact` called `supabase_store._url_secrets`. `supabase_load_backfill_test.test_loader_reuses_the_store_helpers_instead_of_copies` (a standing project guard) forbids any production module reading a private store name, so the suite failed.
- **Fix:** `_redact` now replaces the provider credential values itself and passes the text to `supabase_store.redact`, whose default secrets already include the database URLs and their passwords from the environment.
- **Files modified:** backend/dlr_day_ahead.py
- **Verification:** `dlr_day_ahead_test.py` (including both redaction tests) and `supabase_load_backfill_test.py` pass; full suite 2830 passed
- **Committed in:** 3013e23

### Plan text notes (no code change)

- The plan says an anchor failure reason is "anchor unavailable: ...". The child uses `day_ahead_forecast.read_anchor`, whose reason is `anchor: <ExceptionType>: <redacted message>`. It starts with "anchor", which is what the behaviour list asserts, and avoids a doubled prefix.
- Task 2's behaviour list says "at least 8 passed tests"; the file has 24.

**Total deviations:** 1 auto-fixed (bug). **Impact:** none on the contract or any other plan.

## Issues Encountered

- A first sed-based mutation attempt failed on macOS (BSD sed); the file was restored from a backup and the mutation redone in Python. The file on disk equals the committed one.
- `pytest` from the repo root with `DLR_TEST_PG_AUTOSTART=1` takes about four minutes; a `-x` run stopped at the guard failure above, then the full run was repeated after the fix.

## Known Stubs

None. No hardcoded empty value, placeholder or unwired data source in the new files.

## Threat Flags

None. The new surface (a child process holding the database URL and provider tokens, the writer's insert path, the owner's SQL) is in the plan's threat model: T-08-10 (insert-only grants, tested 42501 and checked live by the new SQL), T-08-11 (redaction tested with a planted URL and token), T-08-12 (runner kill plus autocommit inserts and next-run catch-up; tested as the idempotent and catch-up cases), T-08-13 (anon and authenticated denied, tested and checked by the SQL).

## User Setup Required

None. Nothing here touched the live Supabase project, the live job or any remote, and nothing was pushed. After the owner applies the write-side migration in 08-07, run `supabase/ops/verify_day_ahead_store.sql` in the SQL editor: every `ok` must be true.

## Next Phase Readiness

- Ready for 08-05: add the band artifact's sha256 (`19b9c522...`) to `data/models/LIVE_ARTIFACT_HASHES.sha256` under the key `data/day_ahead/day_ahead_bands_v1.json`. Until then a real child run refuses every target with "no entry in the manifest" (outcome error, no row), which is the intended refusal, not a defect.
- 08-07 may add `_APPLIED_STORE_MIGRATION_SHA256` to `day_ahead_migration_test.py` after the owner applies the migration (deliberately not added now, the file is not applied yet). The migration file is unedited and still editable until then.
- `day_ahead_migration_test.py` applies migrations only through the write-side file, so 08-09's expose migration will not change what these tests prove.

## Self-Check: PASSED

- Files present: `backend/dlr_day_ahead.py`, `backend/tests/dlr_day_ahead_test.py`, `backend/tests/day_ahead_migration_test.py`, `supabase/ops/verify_day_ahead_store.sql`.
- Commits `0f7c0fc`, `847044f` and `3013e23` are ancestors of HEAD; `git rev-list --count e8ac734..HEAD` = 3 before this summary.
- Verify commands: Task 1 `dlr_day_ahead_test.py` + `dlr_live_day_ahead_stage_test.py` 52 passed, none skipped; `PYTHONPATH=backend .venv/bin/python backend/dlr_day_ahead.py --help` exits 0 and names `--city`, `--output`, `--no-store`; Task 2 six-file command 100 passed, 1 skipped (the env-gated exact-value secret scan); `grep -c check_name supabase/ops/verify_day_ahead_store.sql` prints 4; full suite 2830 passed.
- `git diff --quiet -- data/day_ahead/day_ahead_bands_v1.json` exits 0; its sha256 is `19b9c522bea11862c6edb97085d5f121d3c389e2420500a5e50b4ec004a747ec`.

---
*Phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6*
*Completed: 2026-11-08*
