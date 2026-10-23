---
phase: 04
review: 04-REVIEW.md
titles: json
findings:
  - id: WR-06
    severity: warning
    disposition: open
    title: "Per-city exception text is redacted for the log and run row but printed and written to `--output` raw"
  - id: IN-07
    severity: info
    disposition: open
    title: "A failed forecast is recorded as a degraded city with no reason"
  - id: IN-08
    severity: info
    disposition: open
    title: "A cleaning failure on an empty history is dropped from the run row"
  - id: IN-09
    severity: info
    disposition: open
    title: "The manifest commit is passed to `git show` without validation"
  - id: IN-10
    severity: info
    disposition: open
    title: "Schema doc states the CSV archive keeps \"the first write for an exact instant\""
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "`connect()` logs the pooler user, which carries the Supabase project reference"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "A run that fails to write some cities exits 0"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "A data-cleaning failure is reported as a healthy `cold_start`"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "No reconnect or retry on the long-lived connection"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "Backfill de-duplication keeps the first row, the opposite of the CSV rule it cites"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "Backfill identity child is coupled to every module-level config read in live code"
  - id: IN-01
    severity: info
    disposition: fixed
    title: "`_RUN_ERROR_MAX_CHARS = 1000` is dead; error text is cut to 300 characters"
  - id: IN-02
    severity: info
    disposition: fixed
    title: "`connect()` validates the stripped URL but connects with the unstripped one"
  - id: IN-03
    severity: info
    disposition: fixed
    title: "Column comments in the migration disagree with the code and the schema doc"
  - id: IN-04
    severity: info
    disposition: fixed
    title: "Duplicated and cross-module private helpers"
  - id: IN-05
    severity: info
    disposition: fixed
    title: "Workflow hardening"
  - id: IN-06
    severity: info
    disposition: fixed
    title: "`valid_time` CHECK depends on the session time zone"
open: 5
total: 17
recorded: 2026-10-23T22:54:10.280Z
---

# Phase 04: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-06 | warning | open | - |
| IN-07 | info | open | - |
| IN-08 | info | open | - |
| IN-09 | info | open | - |
| IN-10 | info | open | - |
| CR-01 | critical | fixed | Owner decision G-04-2 (04-UAT.md). 04-07 Task 1. `20b6010`. Failing first: `test_tracer_postgres_run_logs_the_server_role_not_the_project_reference`; live-local `test_connect_logs_the_role_the_server_reports`. (not in the current review) |
| WR-01 | warning | fixed | Owner decision G-04-2 (04-UAT.md). 04-08 Task 1. `b63b564` (RED `2148f98`). Failing first: `test_main_with_postgres_exits_one_when_any_city_failed`. (not in the current review) |
| WR-02 | warning | fixed | Owner decision G-04-2 (04-UAT.md). 04-08 Task 2. `200710f` (RED `c2d78f7`). Failing first: `test_cleaning_failure_on_existing_history_reports_forecast_failed`, `test_a_cleaning_failure_is_a_degraded_city_with_its_error_in_the_run_row`. (not in the current review) |
| WR-03 | warning | fixed | Owner decision G-04-2 (04-UAT.md). 04-07 Task 3. `74b6794` (RED `484fad1`). Failing first: `test_store_reconnects_once_when_the_connection_was_lost`; live-local `test_store_recovers_from_a_terminated_backend`. (not in the current review) |
| WR-04 | warning | fixed | Owner decision G-04-2 (04-UAT.md). 04-11 Task 1. `1cdaa2a` (RED `db8ca5c`). Failing first: `test_same_slot_keeps_the_first_computed_row_before_any_fallback_row[fallback_then_computed]`, `test_backfill_keeps_the_row_the_cleaning_step_keeps_usable`. (not in the current review) |
| WR-05 | warning | fixed | Owner decision G-04-2 (04-UAT.md). 04-11 Task 2. `85996bd` (RED `2f27cd1`). Failing first: `test_fingerprint_child_imports_only_the_identity_module_from_live_code`, `test_phase3_fingerprints_survive_a_config_missing_names_live_modules_read_at_import`. (not in the current review) |
| IN-01 | info | fixed | Owner decision G-04-2 (04-UAT.md). 04-10 Task 1. `6a53ae2` (RED `1748e4f`). Failing first: `test_run_row_error_text_keeps_up_to_1000_characters`, `test_redact_limit_defaults_to_300_and_can_be_raised`. (not in the current review) |
| IN-02 | info | fixed | Owner decision G-04-2 (04-UAT.md). 04-07 Task 2. `1fce522` (RED `b612a22`). Failing first: `test_connect_strips_whitespace_around_the_url_before_connecting`; live-local `test_a_url_with_a_trailing_newline_connects`. (not in the current review) |
| IN-03 | info | fixed | Owner decision G-04-2 (04-UAT.md). 04-09 Task 2. `32cd1eb` (RED `8dd91be`). Failing first: `test_run_log_comments_match_the_schema_doc`. Live: migration 20261023000000 pushed 2026-10-23, `smoke_review_fixes.json`. (not in the current review) |
| IN-04 | info | fixed | Owner decision G-04-2 (04-UAT.md). 04-10 Task 2. `d9a0d31` (RED `b302d70`). Failing first: `test_loader_reuses_the_store_helpers_instead_of_copies`. (not in the current review) |
| IN-05 | info | fixed | Owner decision G-04-2 (04-UAT.md). 04-09 Task 3. `79b8476` (RED `e23a2aa`). Failing first: `test_smoke_workflow_pins_actions_by_sha_and_runs_only_on_main`. Live: pushed, Actions run 40035268724 (success, `smoke_actions_review_fixes.json`). (not in the current review) |
| IN-06 | info | fixed | Owner decision G-04-2 (04-UAT.md). 04-09 Task 1. `655646d` (RED `3c24882`). Failing first: `test_review_fix_migration_makes_the_hour_check_zone_independent`, `test_hour_check_accepts_utc_hours_in_a_half_hour_offset_session`. Live: migration 20261023000000 pushed 2026-10-23, `smoke_review_fixes.json` (`session_timezone_utc`, `utc_hour_check_zone_independent` ok). (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
