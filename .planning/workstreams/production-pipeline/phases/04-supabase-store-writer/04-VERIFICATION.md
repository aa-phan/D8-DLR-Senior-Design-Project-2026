---
phase: 04-supabase-store-writer
verified: 2026-10-24T08:10:00Z
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
  - "backend/tests/dlr_orchestrator_test.py"
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
covered_digest: "v3:sha256:845b82dc517fba02d3a03ba97d1a4b1d8e725d8a3002f31109946728a1b336eb"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 6/6
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 4: Supabase Store & Writer Verification Report

**Phase Goal:** Postgres on Supabase is the production system of record for per-city ratings.
**Verified:** 2026-10-24T08:10:00Z
**Status:** passed
**Re-verification:** Yes. The prior report went stale when five code-review fix commits landed after it (b532c00 WR-06, 9c5b6f3 IN-07, 1ef738d IN-08, d3d59dc IN-09, c9b13f5 IN-10). This pass regenerates the report against current code.

## Goal Achievement

All six ROADMAP success criteria still hold against current code. The five fix commits touch only `city_pipeline.py`, `dlr_orchestrator.py`, `supabase_store.py` (`build_run_row`), `supabase_load_backfill.py` (`load_manifest`), their tests and one schema-doc paragraph. They change no migration, workflow, evidence file, identity recipe, archive or frozen module. The full suite, run once by me with a throwaway local Postgres, gives `1703 passed, 0 skipped` (prior pass: 1686; the +17 are the tests the fix commits added).

Evidence classes: (a) read by me from the repository, (b) re-computed or re-run by me, (c) read-only GitHub state, (d) owner-run output committed as JSON (reported, not re-observable by me; I did not read `.env` or connect to any real database).

### Observable Truths (ROADMAP Success Criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Applying the committed migration to an empty Supabase project creates the schema; re-applying is a no-op or fails safely | VERIFIED | (b) `sha256sum` of `20261019000000_create_city_rating.sql` is `7fbf1423e0b8ccf0eee6f79e502036e11c8f3c4c9d54f6badddda0473f76129d`, the value pinned by `test_original_migration_is_unchanged`. `supabase/migrations/` still holds exactly two files. `git diff fb28232 HEAD -- supabase` is empty, so the applied migrations are unchanged since the pushed head. (d) `smoke_review_fixes.json` records schema, RLS, privilege and delete-denied checks true on the real project. Migration tests are in the 1703-pass run. |
| SC2 | A pipeline run pointed at Supabase reads history from Postgres and upserts one row per city; re-running the same window changes no row count | VERIFIED | (a) `_run_cities_with_store` still passes `history_reader=store.read_history`, calls `store.write_rating` per city and `record_run` once; upsert is `ON CONFLICT (city, valid_time) DO UPDATE`. (b) Behavioral proof: `DLR_TEST_PG_AUTOSTART=1 pytest -q -p no:cacheprovider`, `1703 passed, 78 warnings in 152.80s`, no skips, so `supabase_live_test.py` and `supabase_orchestrator_test.py` (rerun keeps one row per city and one run row, 30-day window, reconnect) ran against a real Postgres after the fix commits. (d) The upsert path ran twice on the real project (`rating_upsert_idempotent`, `run_row_idempotent`). A whole orchestrator run against Supabase is Phase 5 plan 05-06, not claimed here. |
| SC3 | The Phase 3 backfill archive is loaded, labelled provisional, per-city row counts match the Phase 3 archive | VERIFIED | (b) `manifest.json` archive sha256 `18f999aa...25cf` equals `backfill_parity.json`; `all_match` is true (504 per city). `manifest.json git.head` is `175b32bc443b4128195dcac70b3d96a60c653a1a`, a 40-character lowercase id, so the new IN-09 guard in `load_manifest` accepts the real input (and the loader test that recomputes the Phase 3 fingerprints from that head is in the passing run). `backend/backfill_archive.py` and `real_data_validation.py` are unchanged since `fa24ce8`. |
| SC4 | A GitHub-hosted runner connects using only repository secrets; a secret scan finds no keys | VERIFIED | (a) `git diff fb28232 HEAD -- .github` is empty: the SHA-pinned, main-only, `contents: read`, dispatch-only workflow is the one that ran. (c)/(d) Actions run 40035268724, success on `fb28232`, recorded in `smoke_actions_review_fixes.json` (carried from the prior pass; the workflow file has not changed). (b) `git grep` for credentialed Postgres URLs and `sb_secret_` over tracked files outside tests finds only prose in `.planning` plan/research text describing the patterns, no values; no tracked `.env`-style file; `secret_scan_test.py` is in the passing run. I did not read Actions log text; "log has no connection details" rests on the owner-recorded JSON, as before. |
| SC5 | Consumer schema doc under `docs/`; `api-contract.md` / `pss_e_handoff.md` point to it | VERIFIED | (a) `docs/data-science/schema/city_rating_v1.md` exists and was updated by IN-07/08/10 (lines 35, 181). `supabase_schema_doc_test.py` and `supabase_migration_test.py` (`test_run_log_comments_match_the_schema_doc`) pass in the full run, so doc and migration comments stay in agreement as pinned. The line-35 imprecision noted last time (IN-10) is fixed and matches `historical_archive._slot_archived`. One stored comment is now narrower than the doc (IN-11, below). |
| SC6 | Every row names what produced it: config version that changes with any per-city conductor parameter, static ratings, bounds, bearings, plus forecast and anomaly model hashes; a conductor or model change alters values only, never schema | VERIFIED | (a) `backend/rating_identity.py`, `backend/config.py` and `historical_archive.py` are unchanged by the fix commits (`git diff fa24ce8 HEAD` over them is empty). (b) `rating_identity_test.py` (per-city sensitivity, hash-seed stability, AST drift guard, schema stability) and the loader test comparing recomputed Phase 3 fingerprints with `backfill_parity.json` pass in the 1703-pass run. No column was added: the fix commits touch no migration. |

**Score:** 6/6 truths verified (0 present, behavior-unverified)

### Review-fix commit check (b532c00, 9c5b6f3, 1ef738d, d3d59dc, c9b13f5), against code, not summaries

I read `git diff fa24ce8 HEAD` over the four source files and the schema doc in full, and confirmed each fix and its named test.

| Finding | In current code | Test exists in tree (and passes in the full run) | Effect on a must-have |
|---------|-----------------|--------------------------------------------------|-----------------------|
| WR-06 | `dlr_orchestrator.py`: `_redacted()` (lazy `supabase_store` import) feeds the CSV-path log line and `out["errors"][name]`; store path uses `supabase_store.redact(exc)` for log line and `out["errors"][name]`. `record["error"] = str(exc)` stays raw, is never printed or written to `--output`, and reaches only `build_run_row`, which calls `redact(error, limit=1000)` (`supabase_store.py` line ~706). | `test_a_failing_city_error_is_redacted_on_the_csv_path`; `test_a_failing_city_error_is_redacted_in_the_run_summary_and_the_printed_report` | Strengthens DB-04 (nothing secret reaches a log or consumer). The raw `record["error"]` does not leak: I traced its only consumer. |
| IN-07 | `city_pipeline.py` sets `forecast_error = f"forecast failed: {exc}"` and exposes it in the `pipeline` block; orchestrator stores `cleaning_error or forecast_error`. | `test_a_forecast_failure_reports_its_reason`; `test_a_forecast_failure_is_a_degraded_city_with_its_error_in_the_run_row`; `test_a_cleaning_error_wins_over_a_forecast_error_in_the_run_row` | Strengthens OD-3's "the live run must detect and record" a degraded forecast. No schema change. |
| IN-08 | `build_run_row`: `error = rec.get("error")` read first; `cities_ok` requires `error is None`. A healthy cold start still has `error None`, so it stays in `cities_ok` (the re-review confirmed `read_history` returns an empty frame and `clean_history` does not raise on it). | `test_a_written_city_with_an_error_is_degraded_even_with_a_healthy_status`; `test_a_cleaning_failure_on_empty_history_is_degraded_with_its_error` | Run-log classification only. No rating row, key, or column affected. |
| IN-09 | `load_manifest` raises `ValueError` unless `git.head` is a string matching `[0-9a-f]{40}` (`re.fullmatch`). | `test_load_manifest_refuses_a_git_head_that_is_not_a_full_commit_id` (parametrized), `test_load_manifest_accepts_a_full_commit_id` | The committed manifest head is 40-hex, so DB-03's loader still accepts the real input. |
| IN-10 | `city_rating_v1.md:35` states the computed-first rule. | `supabase_schema_doc_test.py` | Doc accuracy only. |

### Deferred Items

None. Overlap with Phase 5 (runner exit policy, log hygiene) is noted, not used to excuse anything.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `supabase/migrations/20261019000000_create_city_rating.sql` | DB-01 schema | VERIFIED | Hash-pinned unchanged |
| `supabase/migrations/20261023000000_...utc_hour_check_and_run_log_comments.sql` | IN-06/IN-03 additive | VERIFIED | Unchanged since `fb28232`; applied per owner evidence |
| `backend/supabase_store.py` | writer, reader, reconnect, redact, run row | VERIFIED | Substantive; wired from orchestrator, smoke, loader |
| `backend/rating_identity.py` | DB-06 recipe | VERIFIED | Unchanged; imported by store and fingerprint child |
| `backend/supabase_load_backfill.py` | DB-03 loader | VERIFIED | Manifest sha and now head-format validation |
| `backend/dlr_orchestrator.py`, `backend/city_pipeline.py` | seam to Postgres | VERIFIED | Redaction, forecast reason, history reader wired |
| `backend/supabase_smoke.py`, `.github/workflows/supabase_smoke.yml` | DB-04 live check | VERIFIED | Unchanged since the successful Actions run |
| `docs/data-science/schema/city_rating_v1.md` | DB-05 contract | VERIFIED | Matches code after IN-07/08/10 |
| `docs/data-science/decisions/supabase_store/*.json` (6) | live evidence | VERIFIED | Tracked, unchanged since `825e81d`; only booleans, counts, hashes, role, run id, times |
| `backend/tests/*` for this phase | tests | VERIFIED | Pass in the full run |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `dlr_orchestrator.py` | `supabase_store.py` | `SupabaseStore.from_env()`, `read_history`, `write_rating`, `record_run`, `redact` | WIRED |
| `dlr_orchestrator.py` | `city_pipeline.py` | `history_reader=store.read_history`; `cleaning_error or forecast_error` -> `record["error"]` -> `build_run_row` | WIRED |
| `dlr_orchestrator.py` (CSV path) | `supabase_store.redact` | `_redacted()` lazy import on failure only | WIRED |
| `supabase_store.py` | `rating_identity.py` | re-export used by `build_rating_row` | WIRED |
| `supabase_load_backfill.py` | `load_manifest` guard | `main` calls `load_manifest` before `phase3_config_fingerprints` reads `git.head` | WIRED |
| consumer docs | `city_rating_v1.md` | relative links, covered by `supabase_schema_doc_test.py` | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `city_rating` rows | live row | `build_rating_row` from `run_city_pipeline` result | Yes (live-local tests; real project holds the 2016 backfill rows per owner JSON) | FLOWING |
| `read_history` frame | forecast/detector history | `HISTORY_SQL` on `public.city_rating` | Yes (live orchestrator tests) | FLOWING |
| `pipeline_run.cities_failed` | per-city outcome and error | `record["error"]` from `cleaning_error`/`forecast_error`/exception, redacted with the 1000-char limit | Yes (IN-07/IN-08 tests) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Whole suite incl. live-Postgres tests (run once) | `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider` | `1703 passed, 78 warnings in 152.80s`, 0 failed, 0 skipped | PASS |
| Original migration unchanged | `sha256sum supabase/migrations/20261019000000_create_city_rating.sql` | equals the pinned `7fbf1423...6129d` | PASS |
| Archive and manifest consistency | manifest sha vs `backfill_parity.json`; `git.head` format | `18f999aa...25cf` both; `all_match` true; head 40-hex | PASS |
| Live-infrastructure files unchanged since the verified push | `git diff fb28232 HEAD -- supabase .github` | empty | PASS |

### Probe Execution

No `probe-*.sh` is declared by any plan; step skipped.

### Requirements Coverage

All six IDs appear in the `requirements:` frontmatter of at least one PLAN (DB-01: 04-01, 04-05, 04-09, 04-12; DB-02: 04-01, 04-02, 04-07, 04-08, 04-10; DB-03: 04-03, 04-06, 04-10, 04-11; DB-04: 04-01, 04-03, 04-05, 04-06, 04-07, 04-09, 04-10, 04-12; DB-05: 04-04, 04-08, 04-09, 04-12; DB-06: 04-01..04-04, 04-06, 04-11) and in REQUIREMENTS.md, where all six are marked Complete and mapped to Phase 4. REQUIREMENTS.md maps no other ID to Phase 4: no orphans.

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| DB-01 | Versioned migration, per-city table keyed (city, valid_time) | SATISFIED | SC1 |
| DB-02 | Pipeline reads history from and writes to Postgres; idempotent upserts; CSV path kept | SATISFIED | SC2; WR-06 keeps the CSV path usable (lazy import, only on failure) |
| DB-03 | Phase 3 backfill loaded | SATISFIED | SC3; IN-09 does not reject the real manifest |
| DB-04 | Secret only in Actions secrets; nothing committed; works from runners | SATISFIED | SC4; WR-06 closes the printed-report path |
| DB-05 | Consumer schema contract doc | SATISFIED | SC5 |
| DB-06 | Row provenance, schema stable | SATISFIED | SC6 |

### Prohibitions (must_haves.prohibitions, all `verification: judgment`)

The 23 verdicts of plans 04-01..04-06 were accepted in 04-UAT.md round 1 (test 4), and the 16 of plans 04-07..04-12 were accepted in 04-UAT.md round 2 (test 1, `result: pass`, commit 17976b7). That acknowledgement stands. The fix commits were code-review fixes, not plans, so they introduce no new judgment-tier prohibitions; none is re-raised as a human item. I checked whether any fix changes the basis of an accepted verdict:

| Accepted prohibition (abridged) | Basis changed by the fixes? |
|---------------------------------|------------------------------|
| 04-10: nothing stored or logged without `redact()`, and the longer limit does not skip redaction | No. WR-06 widens redaction (printed report and `--output` now redacted). The raw `record["error"]` is stored in memory only and redacted in `build_run_row` before it is written. |
| 04-07: no part of the connection URL, user, host or project reference logged or printed | No; strengthened. `connect()` is untouched, and exception text in the report is now redacted. |
| 04-08: no `city_rating` column added; cleaning error not stored in `city_rating` | No. No migration changed; `forecast_error` and `cleaning_error` reach only `pipeline_run`. |
| 04-09 / 04-12: original migration unedited; no new column, grant, policy, role or credential | No. `git diff fb28232 HEAD -- supabase` is empty. |
| 04-11: no fingerprint value changed; no edits to frozen modules | No. `rating_identity.py` and the frozen files are unchanged. |
| 04-08: CSV exit status unchanged | No. The CSV-path change is redaction of the error text only; the exit rule is untouched. |

### Anti-Patterns Found

Debt-marker scan (TBD, FIXME, XXX) over the phase's source, migrations, schema doc and workflow: 0 matches. No hardcoded-empty or stub path was introduced by the fix commits.

Code review state (`04-REVIEW.md` re-review at 4ffebd1): 0 critical, 0 warning, 2 info. WR-06, IN-07, IN-08, IN-09 and IN-10 are resolved, which I confirmed against the code above.

### Advisory Notes (not gaps; neither breaks a must-have)

- **IN-11 (open, info):** the stored `pipeline_run.cities_ok` column comment in migration `20261023000000` (line 26) lacks the "no cleaning or forecast error" criterion IN-08 added. The schema doc (line 181) and the `build_run_row` docstring state the rule, and `test_run_log_comments_match_the_schema_doc` still passes because the pinned doc line 176 is unchanged. The stored comment is a secondary description, not a schema or behavior change, so no success criterion fails. Fix is a later additive migration plus a doc and test alignment; editing the applied migration in place is not safe. Good candidate for the next migration Phase 5 or 6 pushes.
- **IN-12 (open, info):** an exception with an empty message prints `ERROR AUSTIN: ` and stores `"error": ""`. The behavior predates WR-06 (it was `str(exc)`), and the city is still recorded as `error` in `cities_failed`. A one-line fix in `_redacted` and the store-path handler would add the exception type name.
- IN-07's optional "exit non-zero when every written city is degraded" was left for an owner decision; it belongs with Phase 5's exit policy.
- Owner-reported evidence caveat (unchanged): live database contents (504 rows per city, schema state), the Actions run log and the `\password` setup are class (d): committed JSON cross-checked for internal and manifest consistency, not independently observable by me.
- The 2026-10-30 Supabase auto-grant change requires re-running the local smoke afterwards (04-05/04-06 User Setup); it does not affect today's result.

### Human Verification Required

None. The only item the prior pass raised (acknowledgement of the 16 judgment-tier prohibition verdicts) was accepted by the owner in 04-UAT.md round 2, the fix commits add no new judgment-tier prohibitions, and no behavior-dependent truth is left unexercised.

### Gaps Summary

No gaps. All six ROADMAP success criteria are verified against current code, and the five post-verification review-fix commits resolve their findings without regressing any must-have: the live-Postgres suite ran after them (1703 passed, 0 skipped), and the migrations, workflow, identity recipe, archive and evidence files they could have affected are byte-unchanged since the pushed head. Two info-level review notes (IN-11, IN-12) remain open as recorded in `04-REVIEW-DISPOSITION.md`; they are noted, not blocking.

---

_Verified: 2026-10-24T08:10:00Z_
_Verifier: Claude (gsd-verifier)_
