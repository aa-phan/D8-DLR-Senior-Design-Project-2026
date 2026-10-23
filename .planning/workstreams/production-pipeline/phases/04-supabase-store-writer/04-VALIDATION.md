---
phase: "04"
slug: "supabase-store-writer"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-23"
validated: "2026-10-23"
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Reconstructed retroactively (State B) from 04-01..04-12 PLAN/SUMMARY, 04-RESEARCH.md
> "Validation Architecture" and 04-VERIFICATION.md.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`) |
| **Quick run command** | `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/supabase_store_test.py backend/tests/supabase_migration_test.py backend/tests/secret_scan_test.py backend/tests/supabase_schema_doc_test.py backend/tests/rating_identity_test.py backend/tests/supabase_load_backfill_test.py backend/tests/supabase_smoke_test.py backend/tests/supabase_run_log_test.py backend/tests/supabase_orchestrator_test.py backend/tests/supabase_live_test.py backend/tests/city_pipeline_test.py` |
| **Live-local command** | `DLR_TEST_PG_AUTOSTART=1` prefixed to the quick command (fixture runs `initdb`/`pg_ctl` on 127.0.0.1; any non-local host fails the test; never Supabase) |
| **Full suite command** | `.venv/bin/python -m pytest -q -p no:cacheprovider` (add `DLR_TEST_PG_AUTOSTART=1` for the gated live tests) |
| **Estimated runtime** | quick ~3 s offline, ~6 s live-local; full suite ~150 s |

Audit run (2026-10-23, SUPABASE_DB_URL unset):

- Quick command offline: 158 passed, 48 skipped (the live-gated tests).
- Quick command with `DLR_TEST_PG_AUTOSTART=1`: 206 passed, 0 skipped (live, orchestrator, migration, smoke and loader subset: 103 passed).
- Full suite with `DLR_TEST_PG_AUTOSTART=1`: **1686 passed, 0 skipped, 0 failed** (default, gate off: 1638 passed, 48 skipped).

---

## Sampling Rate

- **After every task commit:** quick run command (offline).
- **After every plan wave:** full suite, plus the live-local command for any plan touching the store, migrations, loader, smoke or orchestrator.
- **Before `/gsd-verify-work`:** full suite green with `DLR_TEST_PG_AUTOSTART=1` (0 skipped).
- **Max feedback latency:** ~10 seconds (quick + live-local).

---

## Per-Task Verification Map

Commands are relative to `backend/tests/`; prefix with `.venv/bin/python -m pytest -q -p no:cacheprovider`. "live" means the test needs `DLR_TEST_PG_AUTOSTART=1` (local throwaway Postgres).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | DB-04 | T-04-26 | Exact pins for psycopg 3.3.6 after legitimacy gate | manual gate | — (see Manual-Only) | n/a | ✅ green (checkpoint passed) |
| 04-01-02 | 01 | 1 | DB-01, DB-02 | T-04-01..03 | One city-hour round-trips migration, writer, history read | live | `supabase_live_test.py::test_tracer_one_city_hour_round_trips_through_postgres` | ✅ | ✅ green |
| 04-01-03 | 01 | 1 | DB-01, DB-02, DB-04, DB-06 | T-04-01..06 | Schema columns/units/PK/CHECKs, RLS, least-privilege writer without credential, reapply-safe; CHECKs reject NaN/inf/off-hour/bad city; writer cannot DELETE/TRUNCATE/DDL; consumers have no privileges; identity columns hex-checked | unit + live | `supabase_migration_test.py supabase_store_test.py rating_identity_test.py supabase_live_test.py::test_checks_reject_bad_rows supabase_live_test.py::test_writer_cannot_delete_truncate_or_create supabase_live_test.py::test_consumer_roles_have_no_privileges supabase_live_test.py::test_dropping_the_policy_hides_rows_without_an_error` | ✅ | ✅ green |
| 04-02-01 | 02 | 2 | DB-02 | T-04-07 | Pipeline takes a history reader; forecast_status ok/cold_start/failed | unit | `city_pipeline_test.py::test_forecast_status_reports_ok_cold_start_and_failed` | ✅ | ✅ green |
| 04-02-02 | 02 | 2 | DB-02, DB-06 | T-04-08..10 | Orchestrator reads/writes through the store, no CSV written; failing city writes no row (OD-9) and others still write; run row recorded; rerun keeps one row per city and one run row | unit + live | `supabase_orchestrator_test.py` (incl. `::test_orchestrator_rerun_against_postgres_keeps_one_row_per_city_and_one_run_row`, `::test_orchestrator_reads_its_history_from_postgres`) `supabase_run_log_test.py` | ✅ | ✅ green |
| 04-02-03 | 02 | 2 | DB-02 | T-04-11 | Postgres history validated like the CSV archive, excludes current slot, 30-day boundary, empty-history warning | unit + live | `supabase_store_test.py::test_read_history_excludes_the_current_slot_and_bounds_the_window ::test_db_history_is_validated_like_the_csv_archive ::test_history_window_starts_exactly_thirty_days_before_the_slot ::test_history_frame_matches_the_csv_reader_for_the_same_rows` `supabase_orchestrator_test.py::test_history_window_boundary_against_postgres` | ✅ | ✅ green |
| 04-03-01 | 03 | 2 | DB-03, DB-06 | T-04-12..14 | Loader refuses mismatched archive, DO NOTHING, never overwrites live rows, provisional labels + Phase 3 identity, per-city parity | unit + live | `supabase_load_backfill_test.py` | ✅ | ✅ green |
| 04-03-02 | 03 | 2 | DB-04 | T-04-15, T-04-16 | Smoke prints no URL on missing URL / connection failure; secret scan finds no credentials in tracked files; `.env` ignored | unit + live | `supabase_smoke_test.py secret_scan_test.py` | ✅ | ✅ green |
| 04-03-03 | 03 | 2 | DB-04 | T-04-17, T-04-27 | Smoke workflow dispatch-only, secret passed by env only | unit | `supabase_smoke_test.py::test_smoke_workflow_is_dispatch_only_and_passes_the_secret_by_env` | ✅ | ✅ green |
| 04-04-01 | 04 | 3 | DB-05, DB-06 | T-04-18, T-04-19 | Schema doc lists every column with type/unit, required sections, provisional labels, row identity, no connection details | unit (doc check) | `supabase_schema_doc_test.py` | ✅ | ✅ green |
| 04-04-02 | 04 | 3 | DB-05 | T-04-28 | api-contract.md and pss_e_handoff.md point to the contract | unit (doc check) | `supabase_schema_doc_test.py::test_consumer_docs_point_to_the_schema_doc ::test_pss_e_note_lists_what_the_store_fixes_and_what_stays_open` | ✅ | ✅ green |
| 04-05-01 | 05 | 4 | DB-04 | T-04-20 | Supabase CLI legitimacy gate | manual gate | — (see Manual-Only) | n/a | ✅ green (checkpoint passed) |
| 04-05-02 | 05 | 4 | DB-01 | T-04-21 | Owner approves schema contract | manual gate | — (see Manual-Only) | n/a | ✅ green (checkpoint passed) |
| 04-05-03 | 05 | 4 | DB-01, DB-04 | T-04-22 | Migration applied to real project, second push no-op, local smoke green | manual (owner, live) | evidence `docs/data-science/decisions/supabase_store/smoke_local.json`; local equivalent `supabase_smoke_test.py::test_smoke_passes_on_a_fresh_migration_and_leaves_no_rows` + `supabase_migration_test.py::test_migration_is_reapply_safe` | ✅ | ✅ green (local); live = Manual-Only |
| 04-06-01 | 06 | 5 | DB-04 | T-04-23 | GitHub runner reaches pooler with repo secret only | manual (owner, CI) | evidence `smoke_actions.json` (run 40010766903) | n/a | Manual-Only |
| 04-06-02 | 06 | 5 | DB-03, DB-06 | T-04-24 | Backfill loaded on real project, per-city parity 504/504 | manual (owner, live) | evidence `backfill_parity.json`, `smoke_after_backfill.json`; local equivalent `supabase_load_backfill_test.py::test_db_counts_match_the_csv_per_city` | ✅ | ✅ green (local); live = Manual-Only |
| 04-06-03 | 06 | 5 | DB-04, DB-06 | T-04-25 | Committed evidence holds no connection details; backfill identity equals manifest | unit | `secret_scan_test.py supabase_load_backfill_test.py::test_phase3_fingerprints_at_the_manifest_commit_equal_the_loaded_backfill` | ✅ | ✅ green |
| 04-07-01 | 07 | 1 (gap) | DB-04 | T-04-29, T-04-30 | CR-01: `--store postgres` run logs server role, never project reference | unit + live | `supabase_store_test.py::test_tracer_postgres_run_logs_the_server_role_not_the_project_reference` `supabase_live_test.py::test_connect_logs_the_role_the_server_reports` | ✅ | ✅ green |
| 04-07-02 | 07 | 1 (gap) | DB-04 | T-04-31 | IN-02: URL stripped before connect | unit + live | `supabase_store_test.py::test_connect_strips_whitespace_around_the_url_before_connecting` `supabase_live_test.py::test_a_url_with_a_trailing_newline_connects` | ✅ | ✅ green |
| 04-07-03 | 07 | 1 (gap) | DB-02 | T-04-32 | WR-03: reconnect once on lost connection, never on healthy failure, redacted error on failed reconnect | unit + live | `supabase_store_test.py -k reconnect or probe or healthy` `supabase_live_test.py::test_store_recovers_from_a_terminated_backend` | ✅ | ✅ green |
| 04-08-01 | 08 | 1 (gap) | DB-02 | T-04-33 | WR-01: postgres store run exits 1 if any city failed; CSV exit policy unchanged | unit | `supabase_orchestrator_test.py::test_main_with_postgres_exits_one_when_any_city_failed ::test_main_store_flags_extend_the_pinned_arguments_only_for_postgres` | ✅ | ✅ green |
| 04-08-02 | 08 | 1 (gap) | DB-02, DB-05 | T-04-34, T-04-35 | WR-02: cleaning failure on real history is `failed` and a degraded city with redacted error | unit | `city_pipeline_test.py::test_cleaning_failure_on_existing_history_reports_forecast_failed ::test_cleaning_failure_on_empty_history_stays_cold_start` `supabase_orchestrator_test.py::test_a_cleaning_failure_is_a_degraded_city_with_its_error_in_the_run_row` | ✅ | ✅ green |
| 04-09-01 | 09 | 1 (gap) | DB-01, DB-04 | T-04-36, T-04-37 | IN-06: zone-independent hour CHECK in additive migration; original migration byte-pinned; smoke zone checks | unit + live | `supabase_migration_test.py::test_original_migration_is_unchanged ::test_review_fix_migration_makes_the_hour_check_zone_independent ::test_review_fix_migration_is_reapply_safe_and_grants_nothing` `supabase_smoke_test.py::test_hour_check_accepts_utc_hours_in_a_half_hour_offset_session ::test_zone_check_fails_against_the_original_constraint` | ✅ | ✅ green |
| 04-09-02 | 09 | 1 (gap) | DB-05 | — | IN-03: run-log comments match code and schema doc | unit | `supabase_migration_test.py::test_run_log_comments_match_the_schema_doc` | ✅ | ✅ green |
| 04-09-03 | 09 | 1 (gap) | DB-04 | T-04-38, T-04-39 | IN-05: actions SHA-pinned, persist-credentials false, main only | unit | `supabase_smoke_test.py::test_smoke_workflow_pins_actions_by_sha_and_runs_only_on_main` | ✅ | ✅ green |
| 04-10-01 | 10 | 2 (gap) | DB-02, DB-04 | T-04-40, T-04-41 | IN-01: redacted error text up to 1000 chars; colliding provider-error keys keep totals | unit | `supabase_run_log_test.py::test_redact_limit_defaults_to_300_and_can_be_raised ::test_run_row_error_text_keeps_up_to_1000_characters ::test_provider_error_keys_that_collide_after_redaction_keep_their_total` `supabase_orchestrator_test.py::test_orchestrator_keeps_every_provider_error_count_for_a_city` | ✅ | ✅ green |
| 04-10-02 | 10 | 2 (gap) | DB-03 | T-04-42 | IN-04: loader uses store public helpers | unit | `supabase_load_backfill_test.py::test_loader_reuses_the_store_helpers_instead_of_copies` | ✅ | ✅ green |
| 04-11-01 | 11 | 3 (gap) | DB-03 | T-04-43 | WR-04: same-slot de-dup keeps first computed row, matching cleaning | unit | `supabase_load_backfill_test.py::test_same_slot_keeps_the_first_computed_row_before_any_fallback_row ::test_backfill_keeps_the_row_the_cleaning_step_keeps_usable ::test_same_hour_duplicates_keep_the_first_row_and_are_counted` | ✅ | ✅ green |
| 04-11-02 | 11 | 3 (gap) | DB-06 | T-04-44..46 | WR-05: identity recipe in rating_identity.py; fingerprint child isolated, redacted stderr; Phase 3 fingerprints equal backfill parity | unit | `rating_identity_test.py::test_store_reexports_the_identity_recipe` `supabase_load_backfill_test.py -k fingerprint` | ✅ | ✅ green |
| 04-12-01 | 12 | 4 (gap) | DB-01, DB-04 | T-04-47, T-04-48 | Review-fix migration pushed to real project; owner smoke green | manual (owner, live) | evidence `smoke_review_fixes.json` | n/a | Manual-Only |
| 04-12-02 | 12 | 4 (gap) | DB-04 | T-04-49 | Hardened smoke workflow green on main | manual (owner, CI) | evidence `smoke_actions_review_fixes.json` | n/a | Manual-Only |
| 04-12-03 | 12 | 4 (gap) | DB-05 | T-04-50 | Contract names both migrations; evidence files clean | unit | `supabase_schema_doc_test.py secret_scan_test.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Requirement coverage

| Requirement | Status | Automated evidence |
|-------------|--------|--------------------|
| DB-01 | COVERED | `supabase_migration_test.py`, `supabase_live_test.py` (CHECKs, privileges, RLS), `supabase_smoke_test.py` |
| DB-02 | COVERED | `supabase_store_test.py`, `supabase_orchestrator_test.py` (incl. live rerun / history / window), `supabase_run_log_test.py`, `city_pipeline_test.py` |
| DB-03 | COVERED | `supabase_load_backfill_test.py` (incl. live parity, DO NOTHING, no overwrite) |
| DB-04 | COVERED | `secret_scan_test.py`, `supabase_smoke_test.py`, `supabase_store_test.py` (no password/project-ref leak), `supabase_live_test.py` |
| DB-05 | COVERED | `supabase_schema_doc_test.py`, `supabase_migration_test.py::test_run_log_comments_match_the_schema_doc` |
| DB-06 | COVERED | `rating_identity_test.py`, `supabase_store_test.py`, `supabase_load_backfill_test.py` |

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements (all Wave 0 files listed in 04-RESEARCH.md exist and run green).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Package legitimacy gates (psycopg 3.3.6, Supabase CLI 2.121.0) and owner approval of the schema contract | DB-04, DB-01 | Human judgment checkpoints by design | Recorded in 04-01 / 04-05 SUMMARY |
| Migrations applied to the real Supabase project; second push reports "Remote database is up to date" | DB-01 | Requires owner credentials and the real database | `supabase db push --db-url ...` (owner); evidence `smoke_local.json`, `smoke_review_fixes.json` |
| Owner-laptop smoke through the session pooler as `dlr_writer` | DB-04 | Real database | `python backend/supabase_smoke.py [--expect-rows]`; all checks true in committed JSON |
| GitHub-hosted runner smoke using only repository secrets | DB-04 | Needs push and workflow dispatch on GitHub | `gh workflow run supabase_smoke.yml` on main; evidence `smoke_actions.json`, `smoke_actions_review_fixes.json` |
| Phase 3 backfill loaded on the real project, per-city counts equal the archive | DB-03 | Real database | `python backend/supabase_load_backfill.py ... --verify`; evidence `backfill_parity.json` (504/504 per city) |
| Database password reset after exposure in 04-05 | DB-04 | Not observable from the repository | Owner confirms old password invalid |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or are manual-only by nature (owner/live/CI checkpoints)
- [x] Sampling continuity: no 3 consecutive automatable tasks without automated verify
- [x] Wave 0 covers all MISSING references (none missing)
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-10-23

---

## Validation Audit 2026-10-23

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Note: 04-VERIFICATION.md listed SC2 (orchestrator rerun and history read against Postgres) as present but behavior-unverified because the live tests are gated off in the default suite. This audit ran them on a throwaway local Postgres (`DLR_TEST_PG_AUTOSTART=1`): all 48 previously skipped tests pass, including `test_orchestrator_rerun_against_postgres_keeps_one_row_per_city_and_one_run_row`, `test_orchestrator_reads_its_history_from_postgres` and `test_history_window_boundary_against_postgres`. No new tests were needed.
