---
phase: "04"
slug: "supabase-store-writer"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
block_on: high
register_authored_at_plan_time: true
created: "2026-10-23"
---

# Phase 04 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register built from the `<threat_model>` blocks of 04-01..04-12 PLAN.md and the `## Threat Flags` sections of every SUMMARY.md (all report no new surface). Verified at ASVS L1 (grep-level evidence in code, tests, migrations, workflow and committed evidence files). Short-circuit applied: threats_open 0, register authored at plan time, ASVS 1, so no auditor subagent was spawned.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| pipeline result -> SQL statement | Alert text, station ids and probe data reach the database | untrusted strings into SQL |
| writer role -> database | CI credential privileges bound what a leak can do | writer credential (secret) |
| base table -> anon (Phase 6) | Every `city_rating` column becomes publicly readable | rating rows (public) |
| test process -> database server | DDL in tests must reach only a throwaway local cluster | DDL |
| Postgres rows -> forecast/detector | Shared history trains the band and detector that gate the rating | history rows (integrity) |
| exception text -> pipeline_run | Provider/driver errors can echo URLs or keys | error text (may hold secrets) |
| owner machine / Actions runner -> production DB | Loader, smoke test and CI run with the writer credential; admin URL only on the owner machine | DB URLs (secret) |
| repository / Actions log -> readers | Every tracked file and log line is visible to collaborators | docs, evidence, logs |
| archive CSV / git history -> city_rating | Phase 3 archive and sources become shared history via an isolated child | backfill rows, child stderr |
| PyPI / npm / GitHub Actions -> runner | Third-party packages and actions execute | code (supply chain) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation (evidence) | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-04-01 | Tampering | `upsert_rating` / `read_history` SQL | high | mitigate | Bound `%(name)s` params; identifiers only from module constants (`backend/supabase_store.py:156-185`); `test_upsert_sends_one_parameterized_statement` (`supabase_store_test.py:304`) | closed |
| T-04-02 | Elevation of privilege | role `dlr_writer` | high | mitigate | `grant select, insert, update` on two tables only, `revoke all ... from anon, authenticated`, one policy per table, RLS on (`20261019000000_create_city_rating.sql:99-116`); `test_writer_cannot_delete_truncate_or_create` (`supabase_live_test.py:391`) | closed |
| T-04-03 | Information disclosure | `city_rating` columns | high | mitigate | `detector_model_loaded` boolean; explicit column mapping; `test_detector_path_is_stored_only_as_a_boolean` (`supabase_store_test.py:289`) | closed |
| T-04-04 | Tampering | NaN/Inf/off-hour rows | medium | mitigate | `math.isfinite` -> NULL (`supabase_store.py:426`); 12 CHECK constraints in migration | closed |
| T-04-05 | Tampering | live tests' DDL target | high | mitigate | `_LOCAL_HOSTS = ("127.0.0.1","localhost","::1")`, any other host fails (`supabase_live_test.py:7-8,43`) | closed |
| T-04-06 | Information disclosure | connection errors and logs | high | mitigate | `redact()` (`supabase_store.py:274`); StoreError raised outside the except block (no chain, `:338-341`); `test_connection_failure_does_not_leak_the_password`, `test_redact_removes_urls_key_values_and_env_secrets` | closed |
| T-04-26 | Repudiation | row traceability (DB-06) | high | mitigate | `config_fingerprint text not null ... check (~ '^[0-9a-f]{64}$')` (migration:65); `rating_identity_test.py` stability/sensitivity/drift/forecast-method/model-hash tests (lines 112-292) | closed |
| T-04-07 | Tampering | Postgres history frame reaching G6 | high | mitigate | `historical_archive.validate_history_frame` applied to Postgres reads (`supabase_store.py:800`), then `clean_history` | closed |
| T-04-08 | Information disclosure | `pipeline_run` error text / provider keys | high | mitigate | `build_run_row` redacts every error and key (`supabase_store.py:659,703`); `token=abc123` test (`supabase_run_log_test.py:164`); no anon grant | closed |
| T-04-09 | Tampering / Repudiation | same-window re-runs | medium | mitigate | `on conflict (city, valid_time) do update` and `on conflict (run_id)` (`supabase_store.py:169,746`); `test_orchestrator_rerun_against_postgres_keeps_one_row_per_city_and_one_run_row` | closed |
| T-04-10 | Repudiation | failed city disguised by a row | medium | mitigate | Not-written city -> outcome `error` (`supabase_store.py:699`); `test_a_failing_city_writes_no_rating_row_and_is_recorded_in_the_run_row` | closed |
| T-04-11 | Denial of service | RLS hiding rows (silent cold start) | medium | mitigate | Per-city WARNING on empty history (`supabase_store.py:805`); smoke `writer_policies_exist`, `test_smoke_fails_when_the_writer_policy_is_missing` | closed |
| T-04-12 | Tampering | backfill over live rows | high | mitigate | `on conflict (city, valid_time) do nothing`, no UPDATE/DELETE (`supabase_load_backfill.py:98`); `test_backfill_never_overwrites_a_live_row` | closed |
| T-04-13 | Tampering | edited / foreign archive | medium | mitigate | sha256 + byte size vs Phase 3 manifest before connect; `test_loader_refuses_an_archive_that_does_not_match_the_manifest`, `test_off_hour_or_out_of_window_rows_stop_the_load` | closed |
| T-04-27 | Repudiation | backfill labelled with live config/models | medium | mitigate | `PHASE3_CONFIG_VERSION`, PROVISIONAL/REVAL-01 basis, `python -I` child (`supabase_load_backfill.py:62,144-150,267`); `test_phase3_fingerprints_come_from_the_manifest_commit`, `test_backfill_rows_carry_provisional_labels_and_phase3_model_hashes` | closed |
| T-04-14 | Information disclosure | smoke/loader output, reports, Actions log | high | mitigate | `test_connection_failure_prints_no_part_of_the_url`, `test_missing_url_exits_two_and_prints_no_value` (`supabase_smoke_test.py`); evidence files contain no connection strings (grep of `docs/data-science/decisions/supabase_store/`: 0 hits) | closed |
| T-04-15 | Information disclosure | committed credential | high | mitigate | `secret_scan_test.py`: `git ls-files` scan, planted positive control, `test_env_file_is_ignored_and_untracked` | closed |
| T-04-16 | Info disclosure / EoP | workflow triggers & secret exposure | high | mitigate | `.github/workflows/supabase_smoke.yml`: `workflow_dispatch` only, `permissions: contents: read`, secret only in `env:`, no `${{ }}` in `run:`; `test_smoke_workflow_is_dispatch_only_and_passes_the_secret_by_env` | closed |
| T-04-17 | Repudiation | parity hidden by dropped rows | medium | mitigate | `dropped_by_validation` and duplicate counts in report, non-zero exit on mismatch (`supabase_load_backfill.py:29,321`); `test_parity_report_is_deterministic_and_flags_any_mismatch` | closed |
| T-04-18 | Tampering (meaning) | contract drift from schema/labels | medium | mitigate | `supabase_schema_doc_test.py` column/section/label tests | closed |
| T-04-19 | Information disclosure | connection details in docs | high | mitigate | `test_doc_contains_no_connection_details` + repository secret scan | closed |
| T-04-28 | Repudiation (meaning) | provisional rows read as validated | medium | mitigate | `test_doc_explains_row_identity_and_keeps_rows_provisional` | closed |
| T-04-20 | Information disclosure | admin URL / writer credential during setup | high | mitigate | dotenv wrappers (`supabase_smoke.py`, `supabase_load_backfill.py`), smoke output holds no URL; credential set via psql `\password` (owner-reported, 04-05-SUMMARY:103). Note: admin password was pasted in chat once by the owner and was then reset (04-05 Threat Flags) | closed |
| T-04-21 | Tampering | migration to wrong project / twice | medium | mitigate | Dry run listed the one file; idempotent migration; second push "Remote database is up to date." (04-05-SUMMARY:68,132) | closed |
| T-04-22 | Elevation of privilege | Supabase default grants change 2026-10-30 | medium | mitigate | Explicit `revoke all ... from anon, authenticated` (migration:99); smoke `consumers_cannot_write` (`supabase_smoke.py:271`). Follow-up: re-run smoke after 2026-10-30 | closed |
| T-04-23 | Information disclosure | secret in Actions log / evidence | high | mitigate | Secret via `env:` only; log grep for URL/host fragments 0 hits, secret masked `***` (04-06-SUMMARY:44); `EVIDENCE_OK`, secret scan passed with files staged | closed |
| T-04-24 | Denial of service | push changing Shadow Collection install set | medium | mitigate | Runner-wheel precondition passed (04-06-SUMMARY:44); `shadow_collect.yml` unchanged; prior shadow runs green. Follow-up: owner confirms next scheduled shadow run | closed |
| T-04-25 | Repudiation | parity/identity claimed without proof | medium | mitigate | `backfill_parity.json` `all_match: true`, `config_commit` 175b32b, per-city `match: true`; `EVIDENCE_OK` | closed |
| T-04-29 | Information disclosure | `connect()` success log | high | mitigate | Logs server `current_user` redacted against `_project_identifiers(url)` (`supabase_store.py:246,342`); `test_tracer_postgres_run_logs_the_server_role_not_the_project_reference` | closed |
| T-04-30 | Information disclosure | reconnect path | medium | mitigate | Reconnect via `connect()`; `test_a_failed_reconnect_raises_a_redacted_store_error_and_the_next_call_tries_again`; WARNING names only the operation (`supabase_store.py:856`) | closed |
| T-04-31 | Denial of service | dropped long-lived connection | medium | mitigate | `test_store_reconnects_once_when_the_connection_was_lost`, `test_store_does_not_retry_a_failure_on_a_healthy_connection`, probe test | closed |
| T-04-32 | Tampering | retry duplicating writes | low | accept | Retried writes are idempotent upserts (OD-7 key, run_id key) — see Accepted Risks | closed |
| T-04-33 | Repudiation | partial postgres run reported green | medium | mitigate | `if args.store == "postgres" and run["errors"]: return 1` (`dlr_orchestrator.py:372-373`); `test_main_with_postgres_exits_one_when_any_city_failed` | closed |
| T-04-34 | Information disclosure | cleaning error text | medium | mitigate | Text only in pipeline dict and redacted run row (`supabase_store.py:703`); `build_rating_row` maps explicit columns | closed |
| T-04-35 | Tampering | unvetted history after cleaning failure | medium | mitigate | History emptied on cleaning failure (`city_pipeline.py:75-82`) | closed |
| T-04-36 | Tampering | hour CHECK in non-UTC session | low | mitigate | `check ((valid_time at time zone 'UTC') = date_trunc('hour', ...))` (`20261023000000_...sql:20`); `test_hour_check_accepts_utc_hours_in_a_half_hour_offset_session`; live smoke `utc_hour_check_zone_independent: ok` | closed |
| T-04-37 | Tampering | editing the applied migration | medium | mitigate | New additive migration; `_ORIGINAL_MIGRATION_SHA256` pin (`supabase_migration_test.py:32`) | closed |
| T-04-38 | Elevation of privilege | branch dispatch with writer secret | low | mitigate | `if: github.ref == 'refs/heads/main'`; `test_smoke_workflow_pins_actions_by_sha_and_runs_only_on_main`; residual (branch editing the workflow) documented with protected-environment option | closed |
| T-04-39 | Information disclosure | checkout token in .git/config | low | mitigate | `persist-credentials: false` | closed |
| T-04-40 | Information disclosure | longer run-log error text | medium | mitigate | `redact()` cuts after redaction (`supabase_store.py:293`); secret-at-char-600 test `test_run_row_error_text_keeps_up_to_1000_characters` | closed |
| T-04-41 | Information disclosure | provider-error keys | medium | mitigate | `build_run_row` / `_redact_keys` redacts every key (`supabase_store.py:659`) | closed |
| T-04-42 | Repudiation | lost provider-error counts | low | mitigate | Colliding keys summed; `test_provider_error_keys_that_collide_after_redaction_keep_their_total` | closed |
| T-04-43 | Tampering | fallback row kept over computed row | medium | mitigate | `test_same_slot_keeps_the_first_computed_row_before_any_fallback_row` (four orders) + `data_cleaning.clean_history` cross-check | closed |
| T-04-44 | Repudiation | DB-06 fingerprint drift from move | high | mitigate | Byte-identical move to `backend/rating_identity.py`; `test_phase3_fingerprints_at_the_manifest_commit_equal_the_loaded_backfill`, `test_store_reexports_the_identity_recipe`, stability/sensitivity tests | closed |
| T-04-45 | Information disclosure | child stderr surfaced | low | mitigate | Whole stderr redacted; `test_a_failing_fingerprint_child_surfaces_its_whole_redacted_stderr` | closed |
| T-04-46 | Elevation of privilege | child executing unexpected live modules | low | mitigate | `python -I`; `test_the_fingerprint_child_refuses_another_live_backend_module`, `test_fingerprint_child_imports_only_the_identity_module_from_live_code` | closed |
| T-04-47 | Information disclosure | admin URL during push; evidence & log | high | mitigate | dotenv-loaded URL; Actions log 0 hits for URL/host fragments (04-12-SUMMARY Task 3); `smoke_actions_review_fixes.json` `no_connection_details_in_log: true`; secret scan passed with files staged | closed |
| T-04-48 | Tampering | constraint replacement refused by off-hour row | medium | mitigate | Read-only pre-check = 0 rows; migration applied in one push transaction (04-12-SUMMARY) | closed |
| T-04-49 | Denial of service | push changing Shadow Collection | medium | mitigate | `TASK2_PRECONDITION_OK`; `shadow_collect.yml` and `requirements.txt` unchanged (04-12-SUMMARY) | closed |
| T-04-50 | Repudiation | finding marked fixed without proof | medium | mitigate | `04-REVIEW-DISPOSITION.md` 12/12 rows with commit, failing-first test, live evidence; `CLOSURE_OK` | closed |
| T-04-SC (04-01) | Tampering | pip install psycopg / psycopg-binary | high | mitigate | Owner legitimacy gate 2026-10-21; exact pins `psycopg==3.3.6`, `psycopg-binary==3.3.6`; `pip check` clean (`requirements.txt:36-39`) | closed |
| T-04-SC (04-05) | Tampering | npm install `supabase` CLI | high | mitigate | Legitimacy gate; exact 2.121.0; `--ignore-scripts`; installed outside repo (`~/tools/supabase-cli`) (04-05-SUMMARY) | closed |
| T-04-SC (04-09) | Tampering | GitHub Actions third-party code | low | mitigate | `actions/checkout@11d5960...` (v4.4.0), `actions/setup-python@a26af69...` (v5.6.0) pinned by full SHA | closed |
| T-04-SC (04-02,03,04,06,07,08,10,11,12) | Tampering | package installs | low | accept | No new packages in these plans — see Accepted Risks | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-04-01 | T-04-32 | A retried write is an idempotent upsert keyed by (city, valid_time) or run_id, so a retry cannot add a row | Plan 04-07 threat model (planner, owner-approved plan) | 2026-10-23 |
| AR-04-02 | T-04-SC (no-install plans) | Plans 04-02, 04-03, 04-04, 04-06, 04-07, 04-08, 04-10, 04-11, 04-12 install no new package; psycopg and the Supabase CLI were gated in 04-01 / 04-05 | Plan threat models (planner, owner-approved plans) | 2026-10-23 |

*Accepted risks do not resurface in future audit runs.*

### Follow-ups (non-blocking, owner actions)

- T-04-22: re-run the smoke (`consumers_cannot_write`) after Supabase's 2026-10-30 default-grant change.
- T-04-24: confirm the next scheduled Shadow Collection run still succeeds.
- T-04-38: residual — a branch that edits the workflow itself can still dispatch with the secret; the protected-environment (main-only deployment branch) control is documented, not configured.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-23 | 54 | 54 | 0 | gsd-secure-phase (orchestrator, ASVS L1 grep-level, auditor short-circuited) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-23
