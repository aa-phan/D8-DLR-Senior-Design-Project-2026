---
phase: 04-supabase-store-writer
verified: 2026-10-23T23:59:00Z
status: passed
score: 6/6 must-haves verified
covered_files:
  - ".github/workflows/supabase_smoke.yml"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-01-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-01-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-02-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-02-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-03-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-03-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-04-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-04-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-05-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-05-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-06-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-06-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-07-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-07-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-08-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-08-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-09-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-09-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-10-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-10-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-11-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-11-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-12-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-12-SUMMARY.md"
  - "backend/city_pipeline.py"
  - "backend/config.py"
  - "backend/dlr_orchestrator.py"
  - "backend/historical_archive.py"
  - "backend/rating_identity.py"
  - "backend/supabase_load_backfill.py"
  - "backend/supabase_smoke.py"
  - "backend/supabase_store.py"
  - "backend/tests/city_pipeline_test.py"
  - "backend/tests/rating_identity_test.py"
  - "backend/tests/secret_scan_test.py"
  - "backend/tests/supabase_live_test.py"
  - "backend/tests/supabase_load_backfill_test.py"
  - "backend/tests/supabase_migration_test.py"
  - "backend/tests/supabase_orchestrator_test.py"
  - "backend/tests/supabase_run_log_test.py"
  - "backend/tests/supabase_schema_doc_test.py"
  - "backend/tests/supabase_smoke_test.py"
  - "backend/tests/supabase_store_test.py"
  - "docs/data-science/decisions/pss_e_handoff.md"
  - "docs/data-science/decisions/supabase_store/backfill_parity.json"
  - "docs/data-science/decisions/supabase_store/smoke_actions.json"
  - "docs/data-science/decisions/supabase_store/smoke_actions_review_fixes.json"
  - "docs/data-science/decisions/supabase_store/smoke_after_backfill.json"
  - "docs/data-science/decisions/supabase_store/smoke_local.json"
  - "docs/data-science/decisions/supabase_store/smoke_review_fixes.json"
  - "docs/data-science/schema/city_rating_v1.md"
  - "docs/frontend/specs/api-contract.md"
  - "requirements.txt"
  - "supabase/migrations/20261019000000_create_city_rating.sql"
  - "supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql"
covered_digest: "v3:sha256:80a07bee52e6f96fb00957e0981c3a449525caae57511b1573489fb61e6f02d9"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 5/6
  gaps_closed:
    - "G-04-2: every finding in the first 04-REVIEW.md (CR-01, WR-01..WR-05, IN-01..IN-06) is fixed in Phase 4 before Phase 5"
    - "SC2 behavior-unverified item: the live-Postgres tests were run (1686 passed, 0 skipped, DLR_TEST_PG_AUTOSTART=1)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Acknowledge the judgment-tier prohibition verdicts added by gap plans 04-07..04-12 (16 items, table below, all judged held)"
    expected: "Owner accepts the non-authoritative verdicts (the 23 from plans 04-01..04-06 were accepted in 04-UAT.md test 4)"
    why_human: "Every must_haves prohibition is verification: judgment. Verdicts are an LLM judgment, not an authoritative check, so they are flagged unverified-prohibition, human review recommended. Nothing is silently passed."
---

# Phase 4: Supabase Store & Writer Verification Report

**Phase Goal:** Postgres on Supabase is the production system of record for per-city ratings.
**Verified:** 2026-10-23T23:59:00Z
**Status:** human_needed
**Re-verification:** Yes. After gap closure (plans 04-07..04-12, UAT gap G-04-2)

## Goal Achievement

All six ROADMAP success criteria hold against the current code. The one item the first pass could not prove (SC2, the orchestrator-level rerun on Postgres) is now proven: I ran the full suite with `DLR_TEST_PG_AUTOSTART=1` (throwaway local Postgres, never Supabase) and got `1686 passed, 0 skipped`, so the 43 previously skipped live tests actually ran. G-04-2 ("fix all 12 code-review findings") is closed: each of the 12 findings is fixed in source, has a named failing-first test that exists in the tree, and the two that change live infrastructure (IN-03/IN-06 migration, IN-05 workflow) are on the real project and on GitHub. The only remaining item is the mandatory acknowledgement of the new judgment-tier prohibition verdicts. A fresh code review found five new advisory findings (WR-06, IN-07..IN-10); none breaks a must-have (see Advisory Notes).

Evidence classes: (a) read by me from the repository, (b) re-computed or re-run by me, (c) read-only GitHub state via `gh`, (d) owner-run output committed as JSON (reported, not re-observable by me; I did not read `.env` or connect to any real database).

### Observable Truths (ROADMAP Success Criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Applying the committed migration to an empty Supabase project creates the schema; re-applying is a no-op or fails safely | VERIFIED | (a) `supabase/migrations/` holds exactly two files. The original `20261019000000_create_city_rating.sql` sha256 is `7fbf1423...6129d`, equal to the value pinned by `test_original_migration_is_unchanged` (never edited). The additive `20261023000000_...sql` drops its CHECK `if exists` before re-adding it and only replaces two comments, so it re-applies cleanly; it adds no column, grant, policy, role or credential (read in full). (d) `smoke_review_fixes.json`: `tables_exist`, `rls_enabled`, `writer_policies_exist`, `writer_privileges_exact`, `delete_denied`, `consumers_cannot_write` all true on the real project; the executor's 04-12 summary records a second push reporting "Remote database is up to date". (b) Migration tests are part of the 1686-pass run. |
| SC2 | A pipeline run pointed at Supabase reads history from Postgres and upserts one row per city; re-running the same window changes no row count | VERIFIED | (a) `dlr_orchestrator._run_cities_with_store` passes `history_reader=store.read_history`, calls `store.write_rating` per city and `record_run` once; upsert is `ON CONFLICT (city, valid_time) DO UPDATE`. (b) Behavioral proof, previously missing: `DLR_TEST_PG_AUTOSTART=1 pytest -q -p no:cacheprovider` over the whole suite, `1686 passed, 78 warnings in 147.31s`, no skips, which includes `supabase_live_test.py` and `supabase_orchestrator_test.py` (orchestrator rerun keeps one row per city and one run row; history read from Postgres; 30-day window boundary; reconnect after `pg_terminate_backend`). (d) On the real project the upsert path ran twice in the smoke (`rating_upsert_idempotent`, `run_row_idempotent` true). A whole orchestrator run against Supabase is not claimed here; it is Phase 5 plan 05-06. |
| SC3 | The Phase 3 backfill archive is loaded, labelled provisional, per-city row counts match the Phase 3 archive | VERIFIED | (b) Recomputed archive sha256 `18f999aa...25cf` equals both `manifest.json files.archive.sha256` and `backfill_parity.json`. The merge `fb28232` changed `manifest.json` only in the `command` string and dropped `working_directory` (path-stable), not the archive hash, git head (`175b32b`) or row counts, so the loader's manifest check is unaffected. (a) `backfill_parity.json`: AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO each manifest 504 = csv 504 = db 504, `all_match` true, 0 duplicates dropped. (d) `smoke_review_fixes.json` independently shows 504 rows per city, newest 2026-09-28T23:00:00Z on the real project after the review-fix migration. WR-04 and WR-05 fixes to the loader apply to future loads only; the committed archive had 0 duplicates and the pinned Phase 3 fingerprints are tested to be unchanged (see SC6). |
| SC4 | A GitHub-hosted runner connects using only repository secrets; a secret scan finds no keys | VERIFIED | (c) `gh run view 40035268724`: workflow "Supabase Smoke", `status completed`, `conclusion success`, `event workflow_dispatch`, `headSha fb28232ebe1984a8a5eddbbce4a39cfd81cdbc59`, which is `origin/main`. (a) The workflow maps `SUPABASE_DB_URL` into the one run step's env only, `permissions: contents: read`, dispatch-only, job guarded by `github.ref == 'refs/heads/main'`, both actions pinned by 40-hex SHA, `persist-credentials: false`. (b) Tracked-file greps: no credentialed Postgres URL, no `sb_secret_`, no tracked `.env`; `secret_scan_test.py` is in the passing run. (d) `smoke_actions_review_fixes.json` holds only booleans, run id, SHA and time. I did not re-resolve the action SHAs (the re-review did, via `git ls-remote`) and did not read the Actions log text, so "log has no connection details" rests on the owner-recorded JSON. |
| SC5 | Consumer schema doc under `docs/`; `api-contract.md` / `pss_e_handoff.md` point to it | VERIFIED | (a) `docs/data-science/schema/city_rating_v1.md` names both migrations (line 6) and the evidence files (line 188); WR-02's meaning of `forecast_status = failed` after a cleaning failure and the degraded run-log meaning are documented; run-log comments in migration 2 match doc lines 176-177 (`test_run_log_comments_match_the_schema_doc`). Pointers from `api-contract.md` and `pss_e_handoff.md` are covered by `supabase_schema_doc_test.py`, which passed. One sentence at line 35 is imprecise (IN-10, advisory). |
| SC6 | Every row names what produced it: config version that changes with any per-city conductor parameter, static ratings, bounds, bearings, plus forecast and anomaly model hashes; a conductor or model change alters values only, never schema | VERIFIED | (a) `backend/rating_identity.py` (standard library, `config`, `city_point` only) now owns the recipe and `supabase_store` re-exports it (`from rating_identity import`, line 57), so `build_rating_row` still fills `config_version`, `config_fingerprint`, model hashes and `rating_basis`. (b) `rating_identity_test.py` (per-city sensitivity, hash-seed stability, AST drift guard, schema stability) passed in the full run, and the loader test that recomputes the Phase 3 fingerprints from the manifest's git head and compares them to the four values in `backfill_parity.json` passed, so the WR-05 refactor changed no fingerprint value. Schema stability is guarded by the pinned original migration and the additive-only second migration. |

**Score:** 6/6 truths verified (0 present, behavior-unverified)

### G-04-2 closure check (every review finding, against the code, not the summaries)

| ID | Fix located in current code | Failing-first test exists in tree | Live / CI evidence | Status |
|----|-----------------------------|-----------------------------------|--------------------|--------|
| CR-01 | `supabase_store.py:328` reads `select current_user`; `:342` logs `redact(role, secrets + _project_identifiers(url))`; `conn.info.user` unreferenced | `test_tracer_postgres_run_logs_the_server_role_not_the_project_reference` (supabase_store_test.py) | n/a | Closed |
| WR-01 | `dlr_orchestrator.py:372-373` returns 1 for any city error when `--store postgres`; CSV rule on `:374` unchanged | `test_main_with_postgres_exits_one_when_any_city_failed` (supabase_orchestrator_test.py) | n/a | Closed |
| WR-02 | `city_pipeline.py:62-83,101-102`: `cleaning_error`, `forecast_status = "failed"` when cleaning failed on non-empty history, history emptied (never unvetted); orchestrator copies it to the run record (`dlr_orchestrator.py:259`); `build_run_row` classifies `degraded` | `test_cleaning_failure_on_existing_history_reports_forecast_failed` (city_pipeline_test.py) | n/a | Closed |
| WR-03 | `supabase_store.py:842-896`: `_with_reconnect` reconnects once only when the session is lost, retries once, never retries a healthy-connection error | `test_store_reconnects_once_when_the_connection_was_lost`; live `test_store_recovers_from_a_terminated_backend` | live test ran in the 1686 pass | Closed |
| WR-04 | `supabase_load_backfill.py:~350-357` ranks computed rows ahead of fallback rows, keep-first, mapped back by index | `test_backfill_keeps_the_row_the_cleaning_step_keeps_usable` and parametrized same-slot test | n/a (committed archive has 0 duplicates) | Closed |
| WR-05 | Fingerprint child imports only `config, city_point, thermal_model, rating_identity`, refuses any other live backend module (exit 3), surfaces redacted head/tail stderr | `test_fingerprint_child_imports_only_the_identity_module_from_live_code`, `test_phase3_fingerprints_survive_a_config_missing_names_live_modules_read_at_import` | Phase 3 fingerprints equal `backfill_parity.json` | Closed |
| IN-01 | `redact(..., limit=300)` default; `build_run_row` uses `limit=_RUN_ERROR_MAX_CHARS` (1000) at lines 659, 703; key collisions sum counts | `test_run_row_error_text_keeps_up_to_1000_characters` (supabase_run_log_test.py) | n/a | Closed |
| IN-02 | `connect()` assigns `url = str(url).strip()` (line 310) before redaction and `psycopg.connect` | `test_connect_strips_whitespace_around_the_url_before_connecting` | live `test_a_url_with_a_trailing_newline_connects` ran | Closed |
| IN-03 | Migration 2 replaces both run-log comments; text matches the schema doc | `test_run_log_comments_match_the_schema_doc` (supabase_migration_test.py) | (d) pushed 2026-10-23, `smoke_review_fixes.json` all_passed true | Closed |
| IN-04 | Loader uses `supabase_store.finite` and `supabase_store.file_sha256` (public); no private-attribute access | `test_loader_reuses_the_store_helpers_instead_of_copies` | archive sha unchanged | Closed |
| IN-05 | Workflow pinned by SHA, `persist-credentials: false`, job guarded to `refs/heads/main` | `test_smoke_workflow_pins_actions_by_sha_and_runs_only_on_main` (supabase_smoke_test.py) | (c) Actions run 40035268724 success on `fb28232` | Closed |
| IN-06 | Migration 2 rebuilds the CHECK as `(valid_time at time zone 'UTC') = date_trunc('hour', valid_time at time zone 'UTC')`; `connect()` pins `set timezone = 'UTC'`; smoke adds `session_timezone_utc` and `utc_hour_check_zone_independent` | `test_review_fix_migration_makes_the_hour_check_zone_independent`; `test_hour_check_accepts_utc_hours_in_a_half_hour_offset_session` | (d) both checks true on the real project in `smoke_review_fixes.json`; (c) both ok in the Actions run per `zone_checks_ok` | Closed |

`04-REVIEW-DISPOSITION.md` records these 12 as `fixed` (each with plan, task, commit; IN-03/IN-06/IN-05 with the live evidence) and the 5 new review findings as `open` (17 total). 04-UAT.md test 2 expected "every row has a disposition other than open, or the owner accepts them as open"; the 5 remaining are new advisory findings from the re-review, not the 12 that G-04-2 named. G-04-2 is closed.

### Deferred Items

None filed as deferred. Overlap with later phases, noted but not used to excuse anything: Phase 5 05-01's runner exit policy builds on the WR-01 exit status fixed here; WR-06 and IN-07 touch the Phase 5 runner's log and run-log surface.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `supabase/migrations/20261019000000_create_city_rating.sql` | DB-01 schema | VERIFIED | Hash-pinned unchanged, applied to the real project |
| `supabase/migrations/20261023000000_...utc_hour_check_and_run_log_comments.sql` | IN-06/IN-03 additive | VERIFIED | Read in full; applied to the real project (owner) |
| `backend/supabase_store.py` | writer, reader, reconnect, identity re-export | VERIFIED | Substantive and wired (orchestrator, smoke, loader) |
| `backend/rating_identity.py` | DB-06 recipe, minimal import set | VERIFIED | Imported by `supabase_store` and by the fingerprint child |
| `backend/supabase_load_backfill.py` | DB-03 loader | VERIFIED | Manifest sha check, DO NOTHING, computed-first dedup, isolated child |
| `backend/supabase_smoke.py` | DB-04 live check incl. zone checks | VERIFIED | Run locally and in Actions with both zone checks true |
| `.github/workflows/supabase_smoke.yml` | hardened dispatch-only smoke | VERIFIED | SHA-pinned, main-only, run 40035268724 success |
| `docs/data-science/schema/city_rating_v1.md` | DB-05 contract | VERIFIED | Tested against both migrations |
| `docs/data-science/decisions/supabase_store/*.json` (6) | live evidence | VERIFIED | Tracked; only booleans, counts, hashes, role, run id, times |
| `backend/tests/*` (supabase_*, rating_identity, secret_scan, city_pipeline) | tests | VERIFIED | All 15 named failing-first tests exist; all pass |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `dlr_orchestrator.py` | `supabase_store.py` | `SupabaseStore.from_env()`, `read_history`, `write_rating`, `record_run` | WIRED |
| `dlr_orchestrator.py` | `city_pipeline.py` | `history_reader=store.read_history`; `cleaning_error` -> `record["error"]` -> `build_run_row` | WIRED |
| `supabase_store.py` | `rating_identity.py` | `from rating_identity import (...)` re-export, used by `build_rating_row` | WIRED |
| `supabase_load_backfill.py` | `rating_identity.py` | child evaluates `rating_identity.rating_config_fingerprint` on Phase 3 sources | WIRED |
| `supabase_load_backfill.py` | `supabase_store.py` | public `file_sha256`, `finite`, `redact` | WIRED |
| `supabase_smoke.py` | migration 2 | Kolkata-session accept/refuse probe passes only with the UTC CHECK | WIRED (true on real project) |
| `supabase_store.connect` | server | `select current_user` after `set timezone = 'UTC'`, inside the redacted try block | WIRED |
| consumer docs | `city_rating_v1.md` | relative links | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `city_rating` rows | live row | `build_rating_row` from real `run_city_pipeline` result | Yes (live-local tests; real project holds 2016 backfill rows) | FLOWING |
| `read_history` frame | forecast/detector history | `HISTORY_SQL` on `public.city_rating`, validated | Yes; exercised by the live orchestrator tests | FLOWING |
| `pipeline_run` row | per-city outcome, error | `record["error"]` from `cleaning_error`, redacted with 1000-char limit | Yes (WR-02 test) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Whole suite incl. live-Postgres tests | `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider` (run once, throwaway local cluster) | `1686 passed, 78 warnings in 147.31s`, 0 failed, 0 skipped | PASS |
| Original migration unchanged | `sha256sum supabase/migrations/20261019000000_create_city_rating.sql` | `7fbf1423e0b8ccf0eee6f79e502036e11c8f3c4c9d54f6badddda0473f76129d` (equals the pinned value) | PASS |
| Archive integrity | recomputed sha256 of the Phase 3 archive | equals manifest and `backfill_parity.json` | PASS |
| Actions run is on the pushed head | `gh run view 40035268724 --json conclusion,event,headSha` | success, workflow_dispatch, `fb28232` = `origin/main` | PASS |

### Probe Execution

No `probe-*.sh` declared by any plan; step skipped.

### Requirements Coverage

All six IDs appear in the `requirements:` frontmatter of at least one PLAN and in REQUIREMENTS.md (Phase 4, marked Complete). REQUIREMENTS.md maps exactly DB-01..DB-06 to Phase 4; there are no orphaned requirements.

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| DB-01 | 04-01, 04-05, 04-09, 04-12 | Versioned migration, per-city table keyed (city, valid_time) | SATISFIED | SC1; both migrations applied to the real project |
| DB-02 | 04-01, 04-02, 04-07, 04-08, 04-10 | Pipeline reads history from and writes to Postgres; idempotent upserts; CSV path kept | SATISFIED | SC2; live suite passed; WR-01 exit policy and WR-02 status; CSV exit rule unchanged |
| DB-03 | 04-03, 04-06, 04-10, 04-11 | Phase 3 backfill loaded so forecast/detector do not cold-start | SATISFIED | SC3 |
| DB-04 | 04-01, 04-03, 04-05, 04-06, 04-07, 04-09, 04-10, 04-12 | Writer secret only in Actions secrets; nothing secret committed; works from GitHub runners via pooler | SATISFIED | SC4; CR-01 (the one confirmed leak of the project reference to a log) is fixed and tested end to end |
| DB-05 | 04-04, 04-08, 04-09, 04-12 | Consumer schema contract doc | SATISFIED | SC5 |
| DB-06 | 04-01..04-04, 04-06, 04-11 | Row provenance: config version/fingerprint, model hashes, schema stable | SATISFIED | SC6 |

### Prohibitions (must_haves.prohibitions, all `verification: judgment`)

Non-authoritative LLM-judge verdicts. Flag: unverified-prohibition, human review recommended. The 23 prohibitions of plans 04-01..04-06 were judged held in the first pass and accepted by the owner in 04-UAT.md test 4; I re-checked the highest-risk ones (no credential committed, original migration unedited, no edits to frozen/shadow files, no anon/authenticated grants) against current state and they still hold. The 16 from the gap plans are new:

| Plan | Prohibition (abridged) | Verdict | Basis |
|------|------------------------|---------|-------|
| 04-07 | No part of the connection URL, user, host or project reference logged, printed or raised; only the server-reported role | Held | `connect()` logs `redact(role, ...)` from `select current_user`; failure path redacts with connection identifiers; end-to-end tracer test. WR-06 concerns provider exception text, not the DB URL (see notes) |
| 04-07 | At most one retry per call; never retry a healthy-connection failure | Held | `_with_reconnect` retries once, only when `_lost()` confirms the session is gone; CHECK-failure test |
| 04-07 | No connection to the real project, no `.env` read, no printed connection string by the executor | Held | Tests use fakes or the local throwaway Postgres; I did the same |
| 04-08 | No change to the CSV path's exit status or Phase 1 pinned assertions | Held | Line 374 keeps the CSV rule; Phase 1 tests are in the passing run |
| 04-08 | No unvetted history after a cleaning failure; cleaning error not stored in `city_rating` | Held | `history.iloc[0:0]` on failure; `cleaning_error` reaches only `pipeline_run` via `redact` |
| 04-08 | No `city_rating` column added or renamed | Held | Migration 2 changes one CHECK and two comments |
| 04-09 | Original migration not edited; no non-local migration applied by the executor | Held | Hash equals the pinned value; the push was the owner's 04-12 step |
| 04-09 | New migration adds no column, grant, policy, role or credential | Held | Read in full |
| 04-09 | Executor does not push the workflow, set a secret or dispatch; actions pinned from official repos | Held | Pins named `actions/*`; re-review resolved them; push and dispatch by owner (04-12) |
| 04-10 | Nothing stored or logged without `redact()`; the longer limit does not skip redaction | Held | Cut is applied after redaction (`redact` docstring and code, line 293) |
| 04-10 | Loader hashing/checking/labelling unchanged by IN-04 | Held | Archive sha identical to manifest |
| 04-11 | No fingerprint value changed | Held | Phase 3 fingerprints equal `backfill_parity.json` in a passing test |
| 04-11 | Loader not run against a real database; no rewrite of loaded rows | Held | No loader run after the refactor per the summaries and git history; the parity JSON is the original owner run |
| 04-11 | No edits to `backfill_archive.py`, `real_data_validation.py` or the frozen forecast modules | Held | Those two files changed in this window only through the owner's merge `fb28232` bringing in the Phase 3 PR #9 review fixes; no Phase 4 plan commit touches them (`git log --first-parent` shows only the merge) |
| 04-12 | Executor does not push, set secrets, dispatch, read `.env` or connect to the real database | Held | Per summary and `gh` read-only use; evidence is the owner's |
| 04-12 | No finding marked fixed without commit, passing test and (for IN-03/06/05) live evidence | Held | Ledger rows cite commits and failing-first tests; I confirmed the tests exist and the evidence files and Actions run |

### Anti-Patterns Found

Debt-marker scan (TBD, FIXME, XXX) over the phase's source, migration and doc files: none (0 matches in every file).

No blocker anti-pattern. Code-review state after the gap plans: `04-REVIEW.md` (re-review) reports 0 critical, 1 warning, 4 info, all prior 12 resolved (I independently confirmed each above). I confirmed WR-06 against the code:

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/dlr_orchestrator.py` | 273 (`out["errors"][name] = str(exc)`) | Per-city exception text redacted for the log (line 272) and the run row but raw in the printed report and the `--output` JSON | Warning (advisory) | A provider exception that echoes a URL or token would reach the Actions log through `_print_report`. Does not fail a Phase 4 must-have: DB errors are redacted at source (`StoreError`), no CI job runs `--store postgres` yet, and the repo is private. Fix before Phase 5's scheduled runner. |

### Advisory Notes (not gaps)

- **WR-06** (above): recommend fixing before Phase 5 plan 05-01 (suggested fix is three lines plus a test; same inconsistency on the CSV branch).
- **IN-07**: a failed forecast stores `degraded` with `error: null`; a run where every city's ML forecast failed exits 0 with no stored reason. Fits Phase 5's exit policy.
- **IN-08**: a cleaning failure on an empty history is not stored (latent: `clean_history` accepts an empty frame today).
- **IN-09**: the manifest's git head is passed to `git show` unvalidated; a leading `-` would be read as an option. Low exposure (committed owner-run input, fixed argv, no shell).
- **IN-10**: `city_rating_v1.md:35` says the CSV archive "keeps the first write for an exact instant"; a computed row may follow fallback rows and then owns the slot. Consumer-facing wording only; no behavior.
- Owner-reported evidence caveat (unchanged): live database contents (504 rows per city, schema state, `\password` setup) are class (d), committed JSON cross-checked for internal and manifest consistency but not independently observable by me.
- The 2026-10-30 Supabase auto-grant change requires re-running the local smoke afterwards (04-05/04-06 User Setup); it does not affect today's result.
- Local `main` is 4 commits ahead of `origin/main` (docs and planning commits after `fb28232`); the code, migration and workflow under test are all in `fb28232` and unchanged since.

### Human Verification Required

1. **Acknowledge the 16 new judgment-tier prohibition verdicts** (table above, all judged held).
   **Test:** read the table; accept or challenge any verdict.
   **Expected:** owner accepts, as was done for the first 23 in 04-UAT.md test 4.
   **Why human:** all prohibitions are `verification: judgment`; the verdicts are a non-authoritative LLM judgment and must not be silently absorbed into a passed verdict. This is the only open item; no must-have failed and no behavior is left unverified.

### Gaps Summary

No gaps. All six ROADMAP success criteria are verified against the current code, with SC2's runtime behavior now proven by the live-Postgres tests I ran (1686 passed, 0 skipped). G-04-2 is closed: all 12 prior findings are fixed in source with passing failing-first tests, and the live-infrastructure fixes (migration 20261023000000, hardened workflow) are on the real project and on GitHub (Actions run 40035268724, success, head `fb28232` = `origin/main`). Status is `human_needed` solely because judgment-tier prohibitions require human acknowledgement. The five new advisory findings (WR-06, IN-07..IN-10) are recorded `open` in 04-REVIEW-DISPOSITION.md and are notes, not gaps; WR-06 is worth fixing before Phase 5 runs `--store postgres` in GitHub Actions.

---

_Verified: 2026-10-23T23:59:00Z_
_Verifier: Claude (gsd-verifier)_
