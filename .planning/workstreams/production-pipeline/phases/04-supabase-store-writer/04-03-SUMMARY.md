---
phase: 04-supabase-store-writer
plan: 03
subsystem: database
tags: [postgres, supabase, backfill, smoke-test, secret-scan, github-actions, config-fingerprint]

requires:
  - phase: 04-supabase-store-writer
    provides: "04-01: supabase_store (connect, redact, rating_config_fingerprint, RATING_CONFIG_SOURCE_FILES, FORECAST_ARTIFACT_PATHS, upsert_rating), the migration and the throwaway-Postgres fixture; 04-02: upsert_run"
  - phase: 03-real-data-validation
    provides: "the backfill archive, its committed manifest (sha256, window, models, git head); NO-GO does not block this load (owner re-sequencing 2026-10-21)"
provides:
  - "backend/supabase_load_backfill.py: DB-03 loader, manifest-checked, DO NOTHING, provisional labels, Phase 3 identity, per-city parity report"
  - "backend/supabase_smoke.py: DB-04 one-command live check that rolls back and prints no secret"
  - "backend/tests/secret_scan_test.py: repository secret scan with a planted positive control"
  - ".github/workflows/supabase_smoke.yml: dispatch-only Actions probe for SC4 (committed, not pushed)"
  - "supabase_store.connect(): failure text also drops host, user, project reference and resolved address"
affects: [04-04 consumer doc, 04-05 owner migration push, 04-06 owner load and Actions smoke, 06 read view, 07 per-city conductors]

actuals:
  tokens: 24900
  tasks: 3
  commits: 3
plan_head_before: c26d0a6752e14cc766f4b382072f5e889a98ec27
plan_head_after: 2493c8aad94200ce8406dcbcf2409b02ac55f0de

tech-stack:
  added: []
  patterns:
    - "Backfill identity from the manifest's commit: git show of the three rating sources, evaluated by the live fingerprint recipe in a `python -I` child that exits non-zero unless config, city_point and thermal_model were imported from the materialized copy"
    - "Smoke writes only inside conn.transaction(force_rollback=True); the sentinel's first_written_at is moved to a known past value before the second upsert so an overwrite of it would show inside one transaction"
    - "Secret scan reports path:line:pattern only; pattern strings assembled from pieces so the scanner never matches its own source"
    - "Workflow checked with text and regex tests (no YAML library)"

key-files:
  created:
    - backend/supabase_load_backfill.py
    - backend/supabase_smoke.py
    - backend/tests/supabase_load_backfill_test.py
    - backend/tests/supabase_smoke_test.py
    - backend/tests/secret_scan_test.py
    - .github/workflows/supabase_smoke.yml
  modified:
    - backend/supabase_store.py
    - .gitignore

key-decisions:
  - "Backfill rows carry PHASE3_CONFIG_VERSION (v1-provisional-2026-10-13) and a rating_basis built from the manifest that starts 'PROVISIONAL (OD-5)' and names REVAL-01; neither is read from the live config"
  - "Phase 3 config fingerprints are the live recipe evaluated on the manifest commit's sources in an isolated child, so a Phase 7 config change before the load cannot relabel Phase 3 rows"
  - "A dry run still connects (it needs the database counts) but sends no insert; its report leaves inserted, skipped_existing, match and all_match null"
  - "Archive rows with a non-finite or non-positive dlr_amps or static_rating stop the load before any insert (the table CHECK would otherwise abort the whole transaction late)"
  - "Connection-failure text is scrubbed of host, user, project reference and resolved address inside connect(), so the loader, smoke test and orchestrator all print nothing that names the project"

patterns-established:
  - "Owner tools run through a python-dotenv wrapper that loads .env and calls main(argv)"
  - "Parity: match only when db_rows_at_csv_slots == csv_rows == manifest_rows; any mismatch exits 1"

requirements-completed: [DB-03, DB-04, DB-06]

coverage:
  - id: D1
    description: "Loader accepts only the archive whose sha256 and byte size equal the Phase 3 manifest; missing archive or manifest exits 2 naming the path; no connection is opened on refusal"
    requirement: DB-03
    verification:
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_loader_refuses_an_archive_that_does_not_match_the_manifest"
        status: pass
    human_judgment: false
  - id: D2
    description: "Insert is ON CONFLICT (city, valid_time) DO NOTHING in one transaction with values only in params; second load inserts 0; a live row at a backfill slot keeps its values and origin"
    requirement: DB-03
    verification:
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_insert_is_do_nothing_with_bound_parameters_in_one_transaction"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_load_backfill_test.py#test_loading_twice_inserts_nothing_the_second_time"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_load_backfill_test.py#test_backfill_never_overwrites_a_live_row"
        status: pass
    human_judgment: false
  - id: D3
    description: "Backfill rows are provisional (PHASE3_CONFIG_VERSION, backfill_rating_basis) and carry the manifest's model hashes and the Phase 3 config fingerprints from the manifest commit, not the live labels"
    requirement: DB-06
    verification:
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_backfill_rows_carry_provisional_labels_and_phase3_model_hashes"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_phase3_fingerprints_come_from_the_manifest_commit"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_load_backfill_test.py#test_db_counts_match_the_csv_per_city"
        status: pass
    human_judgment: false
  - id: D4
    description: "Same-hour duplicates keep the first row and are counted; off-hour and out-of-window rows stop the load before any insert; parity report is deterministic and any mismatch exits 1"
    requirement: DB-03
    verification:
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_same_hour_duplicates_keep_the_first_row_and_are_counted"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_off_hour_or_out_of_window_rows_stop_the_load"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_parity_report_is_deterministic_and_flags_any_mismatch"
        status: pass
    human_judgment: false
  - id: D5
    description: "Smoke test proves connection, role, TLS, version, RLS, policy, exact privileges and idempotent writes inside a rolled-back transaction, leaves no row and prints no URL, host or credential"
    requirement: DB-04
    verification:
      - kind: integration
        ref: "backend/tests/supabase_smoke_test.py#test_smoke_passes_on_a_fresh_migration_and_leaves_no_rows"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_smoke_test.py#test_smoke_fails_when_the_writer_policy_is_missing"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_smoke_test.py#test_connection_failure_prints_no_part_of_the_url"
        status: pass
    human_judgment: false
  - id: D6
    description: "Blank SUPABASE_DB_URL exits 2 naming the variable with no connection; --expect-rows fails and names empty cities"
    requirement: DB-04
    verification:
      - kind: unit
        ref: "backend/tests/supabase_smoke_test.py#test_missing_url_exits_two_and_prints_no_value"
        status: pass
      - kind: integration
        ref: "backend/tests/supabase_smoke_test.py#test_expect_rows_fails_on_an_empty_city"
        status: pass
    human_judgment: false
  - id: D7
    description: "Secret scan over git ls-files finds no credential-shaped text, fires on every planted pattern (including a percent-encoded credential) and ignores placeholders; .env is ignored and untracked"
    requirement: DB-04
    verification:
      - kind: unit
        ref: "backend/tests/secret_scan_test.py#test_tracked_files_hold_no_credentials"
        status: pass
      - kind: unit
        ref: "backend/tests/secret_scan_test.py#test_the_scanner_flags_planted_credentials_and_ignores_placeholders"
        status: pass
    human_judgment: false
  - id: D8
    description: "Actions workflow is workflow_dispatch only, contents: read, the secret only in the run step's env, no expression in run, no tracing, no admin URL"
    requirement: DB-04
    verification:
      - kind: unit
        ref: "backend/tests/supabase_smoke_test.py#test_smoke_workflow_is_dispatch_only_and_passes_the_secret_by_env"
        status: pass
    human_judgment: false
  - id: D9
    description: "A GitHub-hosted runner reaches the session pooler as dlr_writer with only the repository secret (ROADMAP SC4)"
    requirement: DB-04
    verification: []
    human_judgment: true
    rationale: "Needs the real project and a pushed workflow; the owner dispatches it in plan 04-06. Offline and on a throwaway Postgres this plan proves the tool and the workflow text only."

duration: "about 75 min of active work, interrupted once by an API rate limit"
completed: 2026-10-23
status: complete
---

# Phase 4 Plan 03: Backfill loader, database smoke test and secret scan Summary

**A manifest-checked, never-overwriting backfill loader that labels the Phase 3 rows provisional with their own commit's config fingerprints and model hashes and proves per-city parity (4 x 504 rows loaded on a throwaway Postgres), a rolled-back one-command smoke test for the writer role, a repository secret scan, and a dispatch-only Actions probe, all proven offline**

## Performance

- **Duration:** about 75 min of active work (an API rate limit interrupted the run once; Task 1 was already committed when it resumed)
- **Started:** 2026-10-21T23:11:47Z
- **Completed:** 2026-10-23T05:50Z (wall clock includes the interruption)
- **Tasks:** 3
- **Files modified:** 8 (6 created, 2 modified)

## Accomplishments

- Loader: refuses an archive whose sha256 or byte size differs from the manifest (exit 1, before any connection), exits 2 naming a missing path, inserts with `ON CONFLICT (city, valid_time) DO NOTHING` in one transaction, and reports per city `manifest_rows`, `csv_rows`, `duplicates_dropped`, `db_rows_at_csv_slots`, `inserted`, `skipped_existing` and `match`. Run against the real manifest and real archive on a throwaway Postgres 16 (not committed): dry run, first load (504 inserted per city, every city matches), second load (0 inserted, still matches); the loaded rows hold one `config_version` (`v1-provisional-2026-10-13`), one `run_id` (`backfill-18f999aac445`), `pipeline_version` `175b32b`, `forecast_method` `ml`, and one fingerprint and one forecast model hash per city.
- DB-06 for backfill rows: fingerprints come from `config.py`, `city_point.py` and `thermal_model.py` at the manifest's commit, evaluated in a `python -I` child that exits non-zero unless it imported those copies (mutating the import order to prefer the live code kills 4 tests); model hashes come only from the manifest.
- Smoke test: 11 checks plus optional `rows_visible`, every write inside `force_rollback=True` (removing it fails 3 tests), prints booleans, counts, the role, the server version and UTC times only.
- Secret scan in the suite: four patterns, planted control proves each fires (each pattern disabled in turn fails the control), placeholders and binary files ignored.
- Workflow `supabase_smoke.yml` exists, dispatch-only, secret in the step `env:` only; not pushed.
- Full suite with the live tests gated off: 1498 passed, 43 skipped, 0 failed (baseline 1484 passed, 37 skipped; +14 passed, +6 skipped live); no path under `data/` or `outputs/` changed during the run. With `DLR_TEST_PG_AUTOSTART=1` the loader file gives 11 passed and the smoke and scan files 8 passed, none skipped.

## Task Commits

1. **Task 1: DB-03 backfill loader** - `abb1d5a` (feat)
2. **Task 2: DB-04 smoke test and repository secret scan** - `221cd6e` (feat)
3. **Task 3: dispatch-only Actions smoke workflow and ignored CLI scratch paths** - `2493c8a` (ci, not pushed)

**Plan metadata:** the `docs(04-03)` commit that adds this SUMMARY and the STATE/ROADMAP/REQUIREMENTS updates.

## Owner commands (run from the main checkout, repository root)

Loader dry run (counts only, inserts nothing; still needs `SUPABASE_DB_URL` for the database counts):

```
PYTHONPATH=backend .venv/bin/python -c "from dotenv import load_dotenv; load_dotenv('.env'); import sys, supabase_load_backfill; sys.exit(supabase_load_backfill.main(['--dry-run']))"
```

Loader (writes the parity report; exits 0 only when every city matches):

```
PYTHONPATH=backend .venv/bin/python -c "from dotenv import load_dotenv; load_dotenv('.env'); import sys, supabase_load_backfill; sys.exit(supabase_load_backfill.main(['--report', 'outputs/supabase_backfill_parity.json']))"
```

Smoke test (add `'--expect-rows'` after the backfill load; never pass `--allow-no-ssl` against the real project):

```
PYTHONPATH=backend .venv/bin/python -c "from dotenv import load_dotenv; load_dotenv('.env'); import sys, supabase_smoke; sys.exit(supabase_smoke.main(['--report', 'outputs/supabase_smoke.json']))"
```

Actions probe (after the owner pushes the workflow in 04-06): `gh workflow run supabase_smoke.yml --ref main`.

## Report schemas

- `supabase_backfill_parity/1`: `schema`, `archive {path, sha256, bytes}`, `window`, `rows_read`, `rows_dropped_by_validation`, `per_city {CITY: {manifest_rows, csv_rows, duplicates_dropped, db_rows_at_csv_slots, inserted, skipped_existing, match}}`, `identity {config_commit, config_version, forecast_method, per_city {CITY: {config_fingerprint, forecast_model_sha256, anomaly_model_sha256}}}`, `all_match`. No timestamp, so equal inputs give identical bytes. A dry run leaves `inserted`, `skipped_existing`, `match` and `all_match` null.
- `supabase_smoke/1`: `schema`, `checks {name: true | false | "skipped"}`, `info {role, server_version_num, anon_can_select, city_rows {CITY: {rows, newest}}}`, `all_passed`, `checked_at`.

## Phase 3 config fingerprints (computed from manifest commit 175b32bc443b4128195dcac70b3d96a60c653a1a)

| City | Fingerprint | Equals the live one at execution time |
|---|---|---|
| AUSTIN | `a47b92e4a1f405fd2f8bd752539c371c0d7a1f3cc8cbed2cfd3c4843bb5b9c26` | yes |
| CORPUS_CHRISTI | `33de6fc4270e45df4248eeec936f0f0f5509ee86759f31cad167c8455f975267` | yes |
| MIDLAND | `deaf07335fabf7456607b004f0222c26d1eb6d5d9a561a3c12fde95f70091c7e` | yes |
| EL_PASO | `9a064f9cc0b96e5f6cfb1d98ffbe8567a0fcad4fd3b5cfc8918b6700e9750d02` | yes |

They equal the live fingerprints because the rating config is unchanged since Phase 3 (they are the same four values 04-01 recorded). Once Phase 7 changes a conductor value the live fingerprints will differ and these will not: 04-06 should check the report's `identity.per_city` against this table.

## Decisions Made

See `key-decisions`. The `config.LINE_VOLTAGE_KV` and `POWER_FACTOR` used for `rating_mw` and the two columns follow the plan (read from the live config); both are in the fingerprint recipe and equal Phase 3's today. If Phase 7 changes either before 04-06, the loaded `rating_mw` would use the new value while the fingerprint (from the old commit) names the old one; the 04-06 check of the fingerprints against the live ones above would show the difference first.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Connection-failure text named the host and project**
- **Found during:** Task 2 (smoke test design, against the "prints no host or project reference" truth)
- **Issue:** `supabase_store.connect()` redacted only the URL and the password. libpq's failure text names the server, its resolved address and, on authentication failure, the user, and a Supabase pooler user is `dlr_writer.<project ref>`. The loader, the smoke test and the orchestrator all print that text.
- **Fix:** `connect()` also redacts the URL's host, user and project reference and replaces a parenthesized resolved address with `(REDACTED)`. No other behavior changes.
- **Files modified:** `backend/supabase_store.py`
- **Verification:** `test_connection_failure_prints_no_part_of_the_url` (marker user, project reference and host over two URLs, one with a percent-encoded credential; removing the fix fails it); `supabase_store_test.py` and `rating_identity_test.py` (45 tests) still pass.
- **Committed in:** `221cd6e`

**2. [Rule 2 - Missing critical] Loader stops on rows whose rating cannot be stored**
- **Found during:** Task 1
- **Issue:** the archive's row check treats `dlr_amps` as optional, so a NaN or non-positive rating passes it, and the table CHECK would then abort the whole transaction at the insert.
- **Fix:** `prepare_rows` raises `ValueError` naming the count of rows with a non-finite or non-positive `dlr_amps` or `static_rating`, before any statement is sent. Rows outside `config.LOCATIONS` stop the load the same way.
- **Files modified:** `backend/supabase_load_backfill.py`
- **Committed in:** `abb1d5a`

**3. [Rule 1 - Test strength] Smoke idempotence check needed a known-past `first_written_at`**
- **Found during:** Task 2
- **Issue:** inside one transaction `now()` is constant, so `first_written_at` is trivially unchanged by a second upsert and the check as the plan words it could not fail.
- **Fix:** after the first upsert the smoke test sets the sentinel's `first_written_at` to a known past value (the writer holds UPDATE; the transaction rolls back) and requires it unchanged after the second upsert. Adding `first_written_at` to the store's SET list fails 3 tests.
- **Files modified:** `backend/supabase_smoke.py`
- **Committed in:** `221cd6e`

---

**Total deviations:** 3 auto-fixed (2 missing critical, 1 test strength). **Impact on plan:** deviation 1 touches `supabase_store.py`, which is not in the plan's file list; it is additive to the failure path of `connect()` only.

## Discrepancies

- The Task 3 acceptance criterion `git diff --quiet 72832ee -- .github/workflows/shadow_collect.yml` exits 1, as noted in 04-01: commit `762a0cd` changed that file after 72832ee, outside this plan. Against HEAD the file is unchanged by this plan.
- The plan asks for `Co-Authored-By: Claude Opus 5.5`; the commits carry `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`, the attribution the harness specifies for this session (as in 04-01 and 04-02).
- The plan's verify text says the live tests need only `DLR_TEST_PG_AUTOSTART=1`; that works because `initdb` and `pg_ctl` are on this machine's PATH (`/opt/homebrew/bin`).
- The `.gitignore` edit hides no tracked file: `git ls-files -ci --exclude-standard` lists nothing.
- The plan's loader test list and the 11-test count are met; the fixture manifest uses a fake head, so the git-show step is replaced by a working-tree runner exactly as planned, and one test calls the real runner with the repository's HEAD.
- Status of the push: `git log origin/main..HEAD` listed only the `ci(04-03)` commit when checked after Task 3, so the two earlier plan commits are reachable from `origin/main` in this clone's refs. Nothing was pushed by this plan; the `ci(04-03)` commit and the workflow remain unpushed.

## TDD Gate Compliance

The plan is `type: execute` with `tdd="true"` tasks and one commit per task, so there are no separate failing-test commits (as in 04-01 and 04-02). For Task 1 the test file was written first and failed at collection (`ModuleNotFoundError`, which is not valid RED evidence under the #3770 rule); the tests then passed on the first full run apart from one wrong regex in the tests themselves. As substitute evidence the tests are not vacuous: nine loader mutants (DO UPDATE, live label for `config_version` and `rating_basis`, keep last, sha check removed, import order swapped, parity ignoring the manifest, window upper bound dropped, wind column nulled) and the sha-only tamper case were each killed after one test was strengthened; seven smoke and workflow mutants (no rollback, `rows_visible` always true, policy check always true, `first_written_at` overwritten by the store, host left in the connect failure text, `push` trigger, expression in `run`, write permission) and five scan mutants were each killed by at least one test, then reverted.

## Issues Encountered

- An API rate limit interrupted the run during the loader mutation checks. On resume the tree held no uncommitted plan changes and no throwaway Postgres process was running; the Homebrew `postgresql@16` service the owner runs was left alone.
- One mutant of the loader (sha256 check removed) first survived because the byte-size check also caught the tampering test; a same-size, one-character tamper case was added.

## User Setup Required

None for this plan. The owner's steps are 04-05 (apply the migration, set the `dlr_writer` credential, add `SUPABASE_DB_URL` to `.env` and to the repository secrets) and 04-06 (push the workflow, run the loader and the smoke test, dispatch the Actions probe).

## Known Stubs

None.

## Threat Flags

None. The surface added (a loader and smoke test using the writer credential, a dispatch-only workflow reading one secret) is the one in the plan's threat model (T-04-12 to T-04-17, T-04-27).

## Next Phase Readiness

- Ready for 04-04 (consumer doc) and 04-05/04-06 (owner steps): the loader, smoke test and workflow exist and are proven on a throwaway Postgres, including a full 2,016-row load of the real archive.
- 04-06 should confirm after the real load that the report's `identity` block holds the four fingerprints in the table above and that `db_rows_at_csv_slots` is 504 for every city.
- Nothing was applied to the real Supabase project and nothing was pushed.

## Self-Check: PASSED

- FOUND: backend/supabase_load_backfill.py, backend/supabase_smoke.py, backend/tests/supabase_load_backfill_test.py, backend/tests/supabase_smoke_test.py, backend/tests/secret_scan_test.py, .github/workflows/supabase_smoke.yml
- FOUND commits: abb1d5a, 221cd6e, 2493c8a (ancestors of HEAD)
- Plan checks: `on conflict (city, valid_time) do nothing`, `REPORT_SCHEMA = "supabase_backfill_parity/1"`, `PHASE3_CONFIG_VERSION = "v1-provisional-2026-10-13"`, `force_rollback=True`, `SMOKE OK` present; no `info.dsn` and no printed `SUPABASE_DB_URL` value; test function counts 11 (loader), 6 (smoke: 5 after Task 2, the workflow test added in Task 3) and 3 (scan); `grep -c "secrets.SUPABASE_DB_URL"` prints 1; `/supabase/.temp/` ignored.
- Verification: loader file `DLR_TEST_PG_AUTOSTART=1` 11 passed; smoke and scan files 8 passed (9 with the workflow test); `PHASE3_IDENTITY_OK` printed for the real manifest; full suite 1498 passed, 43 skipped, 0 failed; nothing under data/ or outputs/ changed.

---
*Phase: 04-supabase-store-writer*
*Completed: 2026-10-23*
