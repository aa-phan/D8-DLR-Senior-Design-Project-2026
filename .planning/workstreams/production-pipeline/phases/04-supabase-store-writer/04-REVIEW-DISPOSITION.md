---
phase: 04-supabase-store-writer
review: 04-REVIEW.md
review_status: issues_found
recorded: 2026-10-23
counts:
  open: 0
  fixed: 12
  accepted: 0
  deferred: 0
---

# Phase 04 code review: disposition

Owner decision 2026-10-23 (04-UAT.md gap G-04-2): fix all twelve findings in Phase 4, before Phase 5.

One row per finding in `04-REVIEW.md`. Each Note gives the plan and task, the fix commit and the failing-first test (RED commit in parentheses where the plan split it); "live" marks the findings that touch the real project or CI.

| ID | Severity | Finding | Disposition | Note |
|----|----------|---------|-------------|------|
| CR-01 | critical | `connect()` logs the pooler user, which carries the Supabase project reference | fixed | 04-07 Task 1. `20b6010`. Failing first: `test_tracer_postgres_run_logs_the_server_role_not_the_project_reference`; live-local `test_connect_logs_the_role_the_server_reports`. |
| WR-01 | warning | A run that fails to write some cities exits 0 | fixed | 04-08 Task 1. `b63b564` (RED `2148f98`). Failing first: `test_main_with_postgres_exits_one_when_any_city_failed`. |
| WR-02 | warning | A data-cleaning failure is reported as a healthy `cold_start` | fixed | 04-08 Task 2. `200710f` (RED `c2d78f7`). Failing first: `test_cleaning_failure_on_existing_history_reports_forecast_failed`, `test_a_cleaning_failure_is_a_degraded_city_with_its_error_in_the_run_row`. |
| WR-03 | warning | No reconnect or retry on the long-lived connection | fixed | 04-07 Task 3. `74b6794` (RED `484fad1`). Failing first: `test_store_reconnects_once_when_the_connection_was_lost`; live-local `test_store_recovers_from_a_terminated_backend`. |
| WR-04 | warning | Backfill de-duplication keeps the first row, the opposite of the CSV rule it cites | fixed | 04-11 Task 1. `1cdaa2a` (RED `db8ca5c`). Failing first: `test_same_slot_keeps_the_first_computed_row_before_any_fallback_row[fallback_then_computed]`, `test_backfill_keeps_the_row_the_cleaning_step_keeps_usable`. |
| WR-05 | warning | Backfill identity child is coupled to every module-level config read in live code | fixed | 04-11 Task 2. `85996bd` (RED `2f27cd1`). Failing first: `test_fingerprint_child_imports_only_the_identity_module_from_live_code`, `test_phase3_fingerprints_survive_a_config_missing_names_live_modules_read_at_import`. |
| IN-01 | info | `_RUN_ERROR_MAX_CHARS = 1000` is dead; error text is cut to 300 characters | fixed | 04-10 Task 1. `6a53ae2` (RED `1748e4f`). Failing first: `test_run_row_error_text_keeps_up_to_1000_characters`, `test_redact_limit_defaults_to_300_and_can_be_raised`. |
| IN-02 | info | `connect()` validates the stripped URL but connects with the unstripped one | fixed | 04-07 Task 2. `1fce522` (RED `b612a22`). Failing first: `test_connect_strips_whitespace_around_the_url_before_connecting`; live-local `test_a_url_with_a_trailing_newline_connects`. |
| IN-03 | info | Column comments in the migration disagree with the code and the schema doc | fixed | 04-09 Task 2. `32cd1eb` (RED `8dd91be`). Failing first: `test_run_log_comments_match_the_schema_doc`. Live: migration 20261023000000 pushed 2026-10-23, `smoke_review_fixes.json`. |
| IN-04 | info | Duplicated and cross-module private helpers | fixed | 04-10 Task 2. `d9a0d31` (RED `b302d70`). Failing first: `test_loader_reuses_the_store_helpers_instead_of_copies`. |
| IN-05 | info | Workflow hardening | fixed | 04-09 Task 3. `79b8476` (RED `e23a2aa`). Failing first: `test_smoke_workflow_pins_actions_by_sha_and_runs_only_on_main`. Live: pushed, Actions run 40035268724 (success, `smoke_actions_review_fixes.json`). |
| IN-06 | info | `valid_time` CHECK depends on the session time zone | fixed | 04-09 Task 1. `655646d` (RED `3c24882`). Failing first: `test_review_fix_migration_makes_the_hour_check_zone_independent`, `test_hour_check_accepts_utc_hours_in_a_half_hour_offset_session`. Live: migration 20261023000000 pushed 2026-10-23, `smoke_review_fixes.json` (`session_timezone_utc`, `utc_hour_check_zone_independent` ok). |
