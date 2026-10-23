---
phase: 04-supabase-store-writer
verified: 2026-10-23T21:00:00Z
status: human_needed
score: 5/6 must-haves verified
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
  - "backend/city_pipeline.py"
  - "backend/config.py"
  - "backend/dlr_orchestrator.py"
  - "backend/historical_archive.py"
  - "backend/supabase_load_backfill.py"
  - "backend/supabase_smoke.py"
  - "backend/supabase_store.py"
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
  - "docs/data-science/decisions/supabase_store/smoke_after_backfill.json"
  - "docs/data-science/decisions/supabase_store/smoke_local.json"
  - "docs/data-science/schema/city_rating_v1.md"
  - "docs/frontend/specs/api-contract.md"
  - "requirements.txt"
  - "supabase/migrations/20261019000000_create_city_rating.sql"
covered_digest: "v3:sha256:42affc67c51c7eaa2aec0d06d0dc31dacb8a39bbacca961f7115faf2aaf2e569"
behavior_unverified: 1
overrides_applied: 0
behavior_unverified_items:
  - truth: "SC2: a pipeline run pointed at Supabase reads history from Postgres and upserts one row per city; re-running the same window changes no row count"
    test: "Run `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest backend/tests/supabase_live_test.py backend/tests/supabase_orchestrator_test.py -q` (throwaway local Postgres via initdb, never Supabase)"
    expected: "All live tests pass, in particular test_orchestrator_rerun_against_postgres_keeps_one_row_per_city_and_one_run_row, test_orchestrator_reads_its_history_from_postgres and test_history_window_boundary_against_postgres"
    why_human: "The orchestrator-level rerun and the 30-day history window run only in the 43 live-Postgres tests, which the full suite skips. The verifier's attempt to run them was refused by the permission classifier. The executor summaries record them passing (45 and 34 and 11 passed with the gate on), but that is narration, not verifier evidence. On the real project only the upsert path (sentinel upsert twice) and writer row visibility were exercised, never a whole orchestrator run."
human_verification:
  - test: "Run the live-Postgres tests (see behavior_unverified_items)"
    expected: "0 failures, 0 skips"
    why_human: "Verifier could not execute them; they are the only runtime proof of SC2."
  - test: "Owner decision on CR-01 (and WR-01..WR-05, IN-01..IN-06): fix, accept or defer each in 04-REVIEW-DISPOSITION.md"
    expected: "CR-01 fixed before any `--store postgres` run executes in GitHub Actions (Phase 5), per the ledger note. Suggested path: /gsd-code-review-fix 4"
    why_human: "All 12 review findings are open. I confirmed CR-01 at backend/supabase_store.py:297. It does not fail a Phase 4 must-have (see Anti-Patterns), so I did not mark the phase gaps_found, but it is a confirmed defect against the module's own DB-04 contract and the owner must dispose of it."
  - test: "Confirm the owner reset the Supabase database (postgres) password after it appeared in chat during 04-05 debugging, and that .env and the password manager hold the new value"
    expected: "Old password no longer valid"
    why_human: "Cannot be observed from the repository, and verifier may not read .env or connect to the database."
  - test: "Judgment-tier prohibitions: unverified-prohibition, human review recommended"
    expected: "Owner acknowledges the non-authoritative verdicts listed under Prohibitions (all judged held)"
    why_human: "All 23 must_haves prohibitions are verification: judgment. Verdicts below are an LLM judgment, not an authoritative check."
---

# Phase 4: Supabase Store & Writer Verification Report

**Phase Goal:** Postgres on Supabase is the production system of record for per-city ratings.
**Verified:** 2026-10-23T21:00:00Z
**Status:** human_needed
**Re-verification:** No, initial verification

## Goal Achievement

The store exists on a real Supabase project, is written to by the real code path, holds the Phase 3 backfill with per-city parity, is reachable from a GitHub-hosted runner with only a repository secret, and has a published consumer contract. What is not yet proven by this verifier is the orchestrator-level rerun on Postgres (SC2): its tests exist but are gated off in the suite and I was refused permission to run them. One confirmed critical review finding (CR-01) is open and needs an owner decision.

Evidence classes used: (a) read by me from the repository, (b) re-computed by me (archive sha256, manifest cross-check, tracked-file secret greps, 43 offline contract tests), (c) read-only GitHub state (`gh`), (d) owner-run output committed as JSON (reported, not re-observable by me; I never connect to the database).

### Observable Truths (ROADMAP Success Criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Applying the committed migration to an empty Supabase project creates the schema; re-applying is a no-op or fails safely | VERIFIED | Migration (182 lines) creates `city_rating` (PK `city_rating_pk (city, valid_time)`) and `pipeline_run`, RLS on both, `revoke all` from anon/authenticated, `dlr_writer` with SELECT/INSERT/UPDATE only; every statement is idempotent (`if not exists`, drop-then-create policy, guarded role). Real project: 04-05 CLI output shows one migration applied, second push "Remote database is up to date" (owner-run output). `smoke_local.json`: `tables_exist`, `rls_enabled`, `writer_policies_exist`, `writer_privileges_exact`, `delete_denied`, `consumers_cannot_write` all true. `supabase_migration_test.py` passes (43 offline tests re-run by me: 43 passed). |
| SC2 | A pipeline run pointed at Supabase reads history from Postgres and upserts one row per city; re-running the same window changes no row count | PRESENT_BEHAVIOR_UNVERIFIED | Wired: `dlr_orchestrator._run_cities_with_store` passes `history_reader=store.read_history`, `archive=False`, calls `store.write_rating` per city and `record_run` once; `UPSERT_RATING_SQL` is `ON CONFLICT (city, valid_time) DO UPDATE` with `first_written_at` in neither list; `read_history` is parameterised 30-day, `valid_time < slot`, `not exhausted`. On the real project the same `upsert_rating` path was exercised by the smoke test (`rating_upsert_idempotent`, `run_row_idempotent` true in `smoke_local.json`, `smoke_after_backfill.json`) and the writer sees rows (`rows_visible`). Not demonstrated: a whole orchestrator run, or `read_history` itself, against Supabase (the smoke's `rows_visible` is a direct select), and the local live tests were not re-run by me. Routed to human verification. The first real orchestrator run against Supabase is Phase 5 plan 05-06. |
| SC3 | The Phase 3 backfill archive is loaded, labelled provisional, per-city row counts match the Phase 3 archive | VERIFIED | I recomputed the archive sha256: equals `backfill_parity.json` and `manifest.json files.archive.sha256` (`18f999aa...25cf`). Parity: AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO each manifest 504 = csv 504 = db 504, `all_match` true, 0 duplicates, 0 dropped. `smoke_after_backfill.json`: 504 rows per city, newest 2026-09-28T23:00:00Z (independent second owner-run observation). Loader: `config_version` `v1-provisional-2026-10-13`, `rating_basis` starts "PROVISIONAL (OD-5)", `origin` backfill, `on conflict ... do nothing`. DB contents are owner-reported (class d). |
| SC4 | A GitHub-hosted runner connects using only repository secrets; a secret scan finds no keys | VERIFIED | `gh run view 40010766903`: workflow "Supabase Smoke", `conclusion: success`, `event: workflow_dispatch`, head `74946e6`, completed. `gh secret list`: NREL_API_EMAIL, NREL_API_KEY, SUPABASE_DB_URL, SYNOPTIC_TOKEN (no SUPABASE_ADMIN*). Workflow maps the secret into the run step's env only, `permissions: contents: read`, dispatch-only. My `git grep` over tracked files for credentialed Postgres URLs, `sb_secret_`, JWT-shaped tokens, `password '...'` literals: none outside descriptive plan text with placeholders; no `.env` tracked, `.env` is git-ignored. `secret_scan_test.py` passes. |
| SC5 | Consumer schema doc under `docs/`; `api-contract.md` / `pss_e_handoff.md` point to it | VERIFIED | `docs/data-science/schema/city_rating_v1.md` (186 lines) with the required sections (key and time semantics, columns, fallback, provisional label, "What produced each row (DB-06)", freshness, backfill, reading rules, run log). `city_rating_v1.md` referenced 5 times in `api-contract.md`, 2 in `pss_e_handoff.md`. `supabase_schema_doc_test.py` (doc vs migration columns, config labels, no connection details, links) passes. |
| SC6 | Every row names what produced it: config version that changes with any per-city conductor parameter, static ratings, bounds, bearings, plus forecast and anomaly model hashes; a conductor or model change alters values only, never schema | VERIFIED | Migration columns `config_version`, `config_fingerprint` (NOT NULL, 64-hex CHECK), `forecast_model_sha256`, `anomaly_model_sha256`, `rating_basis` NOT NULL. `build_rating_row` fills them from `rating_config_fingerprint(city)` (sha256 of canonical snapshot: every `vars(point.conductor)` attribute, coordinate, bearing, static rating, bounds, 19 fingerprinted config names reduced per city) and `file_sha256` of the loaded model files; keys asserted equal to `CITY_RATING_COLUMNS`. `rating_identity_test.py` (per-city sensitivity, hash-seed stability, AST drift guard, schema stability) passes. Backfill rows: `backfill_parity.json` identity block equals the manifest (git head `175b32b`, config_version, per-city forecast/anomaly hashes all re-checked equal to `manifest.json models`). |

**Score:** 5/6 truths verified (1 present, behavior-unverified)

### Deferred Items

None filed as deferred. Relevant overlaps with later phases, noted for the owner but not used to excuse anything: Phase 5 05-01 lists a runner "exit policy" (bears on WR-01) and Phase 5 SC3 requires a failed city to be recorded.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `supabase/migrations/20261019000000_create_city_rating.sql` | DB-01 schema | VERIFIED | Exists, substantive, applied to the real project (04-05 output; smoke checks) |
| `backend/supabase_store.py` (903 lines) | writer, reader, identity | VERIFIED | Substantive and wired (orchestrator, smoke, loader import it) |
| `backend/supabase_load_backfill.py` (535) | DB-03 loader | VERIFIED | Manifest sha check, DO NOTHING, parity; run by owner |
| `backend/supabase_smoke.py` (295) | DB-04 live check | VERIFIED | `force_rollback=True`, run locally and in Actions |
| `.github/workflows/supabase_smoke.yml` | dispatch-only smoke | VERIFIED | Run 40010766903 succeeded |
| `docs/data-science/schema/city_rating_v1.md` | DB-05 contract | VERIFIED | Tested against migration |
| `backend/tests/*` (supabase_*, rating_identity, secret_scan) | tests | VERIFIED | 43 offline re-run by me: pass; live-gated file exists (see SC2) |
| `docs/data-science/decisions/supabase_store/*.json` (4) | live evidence | VERIFIED | Present, tracked, hold only booleans/counts/hashes/times, no host or URL |
| `api-contract.md`, `pss_e_handoff.md` | pointers | VERIFIED | Links present |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `dlr_orchestrator.py` | `supabase_store.py` | `SupabaseStore.from_env()`, `read_history`, `write_rating`, `record_run` (lines 215-291) | WIRED |
| `dlr_orchestrator.py` | `city_pipeline.py` | `history_reader=store.read_history`, `archive=False` | WIRED |
| `supabase_store.py` | `historical_archive.py` | `validate_history_frame`, `ARCHIVE_COLUMNS` in `read_history` | WIRED |
| `supabase_store.py` | `ercot_dlr_merger.amps_to_mw` | `rating_mw`, `static_rating_mw` | WIRED |
| `supabase_store.py` | `city_point` / `ampacity_forecast._model_path_for` | fingerprint snapshot, `FORECAST_ARTIFACT_PATHS` | WIRED |
| `supabase_smoke.py` | `supabase_store.upsert_rating` | sentinel upserts (lines 113, 120) | WIRED |
| `supabase_load_backfill.py` | `manifest.json` | sha256, window, rows by city, models, git head | WIRED |
| consumer docs | `city_rating_v1.md` | relative links | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `city_rating` rows | live row | `build_rating_row` from real `run_city_pipeline` result | Yes (local live tracer; real project holds 2016 backfill rows from the archive) | FLOWING |
| `read_history` frame | forecast/detector history | `HISTORY_SQL` on `public.city_rating` | Yes (query; validated through `validate_history_frame`) | FLOWING (SC2 caveat) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Migration, schema doc, secret scan, DB-06 identity contract | `pytest backend/tests/supabase_migration_test.py supabase_schema_doc_test.py secret_scan_test.py rating_identity_test.py` (SUPABASE_DB_URL unset) | 43 passed | PASS |
| Live-Postgres tests (SC2) | `DLR_TEST_PG_AUTOSTART=1 pytest supabase_live_test.py ...` | refused by permission classifier; not run | SKIP (human item) |
| Full suite | run by orchestrator before this verification | 1505 passed, 43 skipped, 0 failed (the 43 are the gated live tests) | NOT re-run by me |

### Probe Execution

No `probe-*.sh` declared by any plan; step skipped.

### Requirements Coverage

All six IDs appear in PLAN frontmatter (`requirements:`) and in REQUIREMENTS.md (Phase 4, marked Complete). No orphaned Phase 4 requirement: REQUIREMENTS.md maps exactly DB-01..DB-06 to Phase 4 and every one is claimed by at least one plan.

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| DB-01 | 04-01, 04-05 | Versioned migration, per-city table keyed (city, valid_time), units in names/doc | SATISFIED | Migration applied to real project; column units in names and comments; `rating_mw` via `amps_to_mw` |
| DB-02 | 04-01, 04-02 | Pipeline reads history from and writes to Postgres; idempotent upserts; CSV path kept | SATISFIED in code; runtime rerun = human item | Wiring verified; CSV default untouched (frozen files unmodified in phase commits); orchestrator-level rerun is SC2 |
| DB-03 | 04-03, 04-06 | Phase 3 backfill loaded so forecast/detector do not cold-start | SATISFIED | SC3 evidence; archive hash recomputed |
| DB-04 | 04-01, 04-03, 04-05, 04-06 | Writer secret only in Actions secrets; nothing secret committed; works from GitHub runners via pooler | SATISFIED, with CR-01 open | SC4 evidence; CR-01 is a log-hygiene defect on the success path, not a committed or consumer-visible secret |
| DB-05 | 04-04 | Consumer schema contract doc; replaces open items in api-contract and pss_e_handoff | SATISFIED | SC5 evidence |
| DB-06 | 04-01..04-04, 04-06 | Row provenance: config version/fingerprint, model hashes, schema stable | SATISFIED | SC6 evidence |

### Prohibitions (must_haves.prohibitions, all `verification: judgment`)

Non-authoritative LLM-judge verdicts. Flag: unverified-prohibition, human review recommended (see human_verification item 4).

| Prohibition (abridged) | Verdict | Basis |
|------------------------|---------|-------|
| No sensitive data in `city_rating` (path, error text, token, host, project ref) | Held | `build_rating_row` stores only `detector_model_loaded` boolean; no error text; errors go only to `pipeline_run` via `redact()` |
| No row without provisional labels | Held | `rating_basis`, `config_version` NOT NULL; writer fills from config; loader uses Phase 3 label |
| No credential in migration/code/tests/committed file; no DELETE/TRUNCATE/DDL/BYPASSRLS for writer; no anon/authenticated privilege | Held | Migration reviewed; my tracked-file greps clean; smoke `writer_privileges_exact`, `anon_can_select` false on the real project |
| No live DDL against non-local DB; no migration applied from plan 04-01 | Held | Fixture refuses non-local hosts (read); migration applied only in owner plan 04-05 |
| No edits to frozen shadow/experiment files, shadow_collect.yml, data/shadow, archive schema constants | Held | `git diff d7f680a^..HEAD` over the shadow workflow and `ampacity_forecast`, `anomaly_detector`, `city_point`, `thermal_model` is empty; `git log` for the others shows only pre-phase commits |
| No placeholder row for an outright-failed city (OD-9) | Held | `_run_cities_with_store` writes nothing on exception; failure recorded in run row |
| No error text or paths in `city_rating` | Held | as above |
| No live row without `config_fingerprint`; no model hash from anywhere but the loaded file | Held | `build_rating_row` always computes it; `model_identity` hashes the loaded files |
| No overwrite/delete during backfill; no mismatched archive | Held | `do nothing`; sha256 and size checked against manifest |
| No backfill labelled with live config; no go/no-go claim | Held | Loader pins `PHASE3_CONFIG_VERSION`; docs state NO-GO |
| No parity from counts that hide drops | Held | Report carries `rows_dropped_by_validation`, `duplicates_dropped`, per-city `match` |
| No connection details printed/logged/committed by smoke, loader, workflow; no admin URL on GitHub | Held for those three; see CR-01 for `connect()` under `--store postgres` | Evidence JSON and Actions log clean per 04-06 and my greps |
| No push / secret / write dispatch by the executor | Held per summaries and `gh` (read-only use) | The owner performed those steps |
| No docs presenting ratings as verified limits; no connection details; no Phase 5/6 claims | Held | Provisional banner in `city_rating_v1.md`; reviewed |

### Anti-Patterns Found

Debt-marker scan (TBD, FIXME, XXX, TODO, HACK) over the ten phase source/doc files: none.

Code review (`04-REVIEW.md`, 12 findings, all `open` in `04-REVIEW-DISPOSITION.md`). I confirmed the following against the code:

| File | Line | Finding | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/supabase_store.py` | 297 | CR-01 confirmed: `log.info("connected to Postgres as %s", conn.info.user)`; `dlr_orchestrator.main` sets `logging.basicConfig(level=INFO)` (line 333). For the pooler the user is `dlr_writer.<project_ref>`. The smoke test and loader configure no logging (INFO dropped), which is why the Actions smoke log was clean. | Critical per review; WARNING for this verification | Contradicts the module docstring's own rule that the project reference never reaches a log. Not a credential, repo is PRIVATE (`gh repo view`), no CI job runs `--store postgres` yet, so nothing has leaked. Would print in Phase 5's scheduled runner. Does not fail a Phase 4 must-have (the plan's failure-path password and smoke/loader/workflow prohibitions hold), so I did not mark the phase gaps_found. Fix before Phase 5. |
| `backend/dlr_orchestrator.py` | 351 | WR-01 (per review; line seen, not re-derived): exit 0 when some cities fail to write but one succeeds | Warning | Scheduled job stays green with a data gap; Phase 5 05-01 "exit policy" is the natural home |
| `backend/city_pipeline.py` | 83-89 | WR-02 confirmed: a `clean_history` exception empties history, forecast returns None, `forecast_status` becomes `cold_start`, counted healthy in `cities_ok` | Warning | Cleaning failure indistinguishable from a new city in the run log |
| `backend/supabase_store.py` | 256-298 | WR-03 (per review): no reconnect on a long-lived connection | Warning | Phase 5 per-city children reduce, not remove, the exposure |
| `backend/supabase_load_backfill.py` | 315-319 | WR-04 confirmed: `duplicated(keep="first")` contradicts the computed-after-fallback rule; committed archive has 0 duplicates | Warning | No effect on loaded rows today; wrong for a different archive |
| `backend/supabase_load_backfill.py` | 189-245 | WR-05 (per review): identity child coupled to live module imports | Warning | Breaks backfill re-run after Phase 7 config changes |
| various | | IN-01..IN-06 (dead constant, unstripped URL, migration comment wording, private-helper reuse, workflow pinning, tz-dependent CHECK) | Info | Not goal-blocking; IN-03 and IN-06 need a new additive migration |

### Human Verification Required

1. **Run the live-Postgres tests.**
   **Test:** `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest backend/tests/supabase_live_test.py backend/tests/supabase_orchestrator_test.py -q` (local throwaway cluster, never Supabase).
   **Expected:** all pass, none skipped, including the orchestrator rerun, history-from-Postgres and 30-day-boundary tests.
   **Why human:** only runtime proof of SC2; the full suite skips them and my run was refused.

2. **Dispose of the 12 open review findings, CR-01 first.**
   **Test:** edit `04-REVIEW-DISPOSITION.md` or run `/gsd-code-review-fix 4`.
   **Expected:** CR-01 fixed (log `select current_user`, or nothing, plus a `caplog` test) before Phase 5 runs `--store postgres` in Actions; WR-01, WR-02, WR-03 decided before Phase 5.
   **Why human:** owner decides fix/accept/defer; if the owner wants zero open critical findings on a verified phase, route CR-01 through the fix first and re-verify.

3. **Confirm the database password reset.**
   **Test:** owner confirms the postgres password that appeared in chat in 04-05 was reset and `.env` updated.
   **Expected:** old value invalid.
   **Why human:** unobservable to the verifier. Related 04-05 deviation (orchestrator read `.env` structure once at the owner's request) is recorded and was owner-authorised; it does not affect the goal.

4. **Acknowledge the judgment-tier prohibition verdicts** (table above, all judged held).

### Gaps Summary

No must-have failed. No FAILED truth, MISSING or STUB artifact, NOT_WIRED link or unreferenced debt marker. Status is `human_needed` because (a) SC2's runtime behavior is evidenced only by gated live tests I could not run, (b) there are owner decisions that cannot be made programmatically (open critical review finding, password reset, judgment-tier prohibitions). Caveats the owner should know: DB contents (504 rows per city, schema state, secret set-up via `\password`) are owner-reported evidence in committed JSON, cross-checked for internal and manifest consistency but not independently observable; the 2026-10-30 Supabase auto-grant change requires re-running the local smoke afterwards (04-05/04-06 User Setup).

---

_Verified: 2026-10-23T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
