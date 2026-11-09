---
phase: 04-supabase-store-writer
plan: 12
subsystem: database
tags: [postgres, supabase, migration, github-actions, smoke-test, review-ledger, gap-closure]
gap_closure: true
gap_ids: [G-04-2]
status: complete

requires:
  - phase: 04-supabase-store-writer
    provides: "04-07..04-11: every review fix in code, the 20261023000000 migration and the hardened supabase_smoke.yml"
provides:
  - "Migration 20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql applied to the real project (owner, 2026-10-23)"
  - "docs/data-science/decisions/supabase_store/smoke_review_fixes.json: owner-machine smoke after the migration, all checks true"
  - "docs/data-science/decisions/supabase_store/smoke_actions_review_fixes.json: GitHub-hosted runner smoke, run 40035268724, success"
  - "city_rating_v1.md names both migrations and the new evidence files"
  - "04-REVIEW-DISPOSITION.md: 12 of 12 findings fixed with plan, task, commit, failing-first test and live evidence"
affects: [04-UAT.md test 2 re-verification, 05 scheduled runner]

actuals:
  tokens: 1900
  tasks: 3
  commits: 1
plan_head_before: fb28232ebe1984a8a5eddbbce4a39cfd81cdbc59
plan_head_after: 825e81d

key-files:
  created:
    - docs/data-science/decisions/supabase_store/smoke_review_fixes.json
    - docs/data-science/decisions/supabase_store/smoke_actions_review_fixes.json
  modified:
    - docs/data-science/schema/city_rating_v1.md
    - .planning/workstreams/production-pipeline/phases/04-supabase-store-writer/04-REVIEW-DISPOSITION.md

key-decisions:
  - "No schema or column change in the consumer doc: only the Scope line (two migrations) and the Versioning evidence sentence changed"

requirements-completed: [DB-01, DB-04, DB-05]

duration: "owner steps 2026-10-23; executor Task 3 about 15 minutes"
completed: 2026-10-23
---

# Phase 4 Plan 12: Review fixes live, G-04-2 closed Summary

**The additive migration is on the real project, the hardened smoke workflow passed on a GitHub-hosted runner at origin/main's head, and all 12 review findings are recorded as fixed with commit, failing-first test and live evidence.**

## Performance

- Tasks 1 and 2 were owner actions (verified by the orchestrator); Task 3 was executed here.
- Commit: `825e81d` `docs(04-12): review fixes live - migration pushed, smoke evidence, disposition ledger` (not pushed).

## Live evidence

**Task 1: schema push (owner, 2026-10-23).**
- Pre-check (rows off a whole UTC hour): `0`.
- Dry run listed only `20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql`.
- Apply: "Applying migration 20261023000000_... Finished supabase db push."
- Second push ("Remote database is up to date."): not run by the owner, see Discrepancies.
- Smoke (`--expect-rows`) printed `SMOKE OK`, all 14 checks ok, including `check session_timezone_utc: ok` and `check utc_hour_check_zone_independent: ok`; 504 rows per city for AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO. Report `smoke_review_fixes.json`: `all_passed` true, `ssl_in_use`, `role_is_dlr_writer`, `consumers_cannot_write`, `rows_visible` true. The orchestrator's verification printed `SMOKE_REVIEW_FIXES_OK`.

**Task 2: push and dispatch.**
- Precondition exited 0 (`TASK2_PRECONDITION_OK`); the CI diff was only `supabase_smoke.yml` (SHA pins matching 04-09, `persist-credentials: false`, main-only `if`). `shadow_collect.yml` and `requirements.txt` unchanged.
- Owner-authorized `git push origin main` (405ba23..fb28232) and `gh workflow run supabase_smoke.yml --ref main`: run `40035268724`, conclusion `success`, event `workflow_dispatch`, head `fb28232ebe1984a8a5eddbbce4a39cfd81cdbc59` equal to origin/main.

**Task 3 (this session).**
- Actions log fetched into a scratch directory outside the repository: `SMOKE OK` 1, `check session_timezone_utc: ok` 1, `check utc_hour_check_zone_independent: ok` 1; zero hits for `postgresql://`, `postgres://`, `pooler.supabase.com`, `supabase.co`, `SUPABASE_ADMIN`. Log deleted after the check.
- `smoke_actions_review_fixes.json` written (schema `supabase_smoke_actions/1`, `sort_keys`, indent 2): run_id 40035268724, success, workflow_dispatch, head_sha fb28232, created_at 2026-10-23T22:41:53Z, `smoke_ok`, `zone_checks_ok`, `no_connection_details_in_log` all true.
- Verification: `CLOSURE_OK`; secret scan and schema-doc tests 10 passed (re-run with the evidence files staged); full suite 1638 passed, 48 skipped, 0 failed.

## Final ledger (04-REVIEW-DISPOSITION.md: open 0, fixed 12)

| ID | Plan/Task | Fix commit | Failing-first test |
|----|-----------|-----------|--------------------|
| CR-01 | 04-07 T1 | `20b6010` | `test_tracer_postgres_run_logs_the_server_role_not_the_project_reference` |
| WR-01 | 04-08 T1 | `b63b564` | `test_main_with_postgres_exits_one_when_any_city_failed` |
| WR-02 | 04-08 T2 | `200710f` | `test_cleaning_failure_on_existing_history_reports_forecast_failed` |
| WR-03 | 04-07 T3 | `74b6794` | `test_store_reconnects_once_when_the_connection_was_lost` |
| WR-04 | 04-11 T1 | `1cdaa2a` | `test_same_slot_keeps_the_first_computed_row_before_any_fallback_row` |
| WR-05 | 04-11 T2 | `85996bd` | `test_fingerprint_child_imports_only_the_identity_module_from_live_code` |
| IN-01 | 04-10 T1 | `6a53ae2` | `test_run_row_error_text_keeps_up_to_1000_characters` |
| IN-02 | 04-07 T2 | `1fce522` | `test_connect_strips_whitespace_around_the_url_before_connecting` |
| IN-03 | 04-09 T2 | `32cd1eb` | `test_run_log_comments_match_the_schema_doc` (live: migration pushed 2026-10-23) |
| IN-04 | 04-10 T2 | `d9a0d31` | `test_loader_reuses_the_store_helpers_instead_of_copies` |
| IN-05 | 04-09 T3 | `79b8476` | `test_smoke_workflow_pins_actions_by_sha_and_runs_only_on_main` (live: run 40035268724) |
| IN-06 | 04-09 T1 | `655646d` | `test_review_fix_migration_makes_the_hour_check_zone_independent` (live: migration pushed 2026-10-23) |

Every finding had a fix commit and a passing test in its plan's SUMMARY; none was marked on narration.

## Deviations from Plan

### Discrepancies

1. **Second confirming push not run.** The plan asked for a second `supabase db push` expecting "Remote database is up to date." The owner did not run it, so that line was not captured. The live smoke's `utc_hour_check_zone_independent: ok` and `session_timezone_utc: ok` (and the pre-check, dry run and apply output) confirm the new constraint is live, so the migration state is established by other evidence. Minor.
2. **Executor did not run Tasks 1 and 2.** Both are owner actions; the orchestrator verified them and, with owner authorization, ran the push and the workflow dispatch. This executor pushed nothing.
3. **Task 3 was resumed in a continuation agent**, with the Actions run id and head SHA supplied by the orchestrator and re-read from `gh` here.
4. **Co-Authored-By line.** The plan text names Claude Opus 5.5 and the task commit carries that trailer as the plan and dispatch specified.

No auto-fix rules fired. No stubs created; no threat flags.

## Self-Check: PASSED

- Files exist: `smoke_review_fixes.json`, `smoke_actions_review_fixes.json`, `city_rating_v1.md`, `04-REVIEW-DISPOSITION.md`.
- Commit `825e81d` is an ancestor of HEAD; `git rev-list --count fb28232..825e81d` = 1 (matches `commits:`). Both evidence files are tracked.
