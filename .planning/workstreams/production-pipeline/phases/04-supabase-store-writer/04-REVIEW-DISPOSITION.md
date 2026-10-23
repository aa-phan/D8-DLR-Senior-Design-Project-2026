---
phase: 04-supabase-store-writer
review: 04-REVIEW.md
review_status: issues_found
recorded: 2026-10-23
counts:
  open: 12
  fixed: 0
  accepted: 0
  deferred: 0
---

# Phase 04 code review: disposition

One row per finding in `04-REVIEW.md`. Every finding starts `open`; the owner decides each one.

| ID | Severity | Finding | Disposition | Note |
|----|----------|---------|-------------|------|
| CR-01 | critical | `connect()` logs the pooler user, which carries the Supabase project reference | open | Confirmed at `backend/supabase_store.py:297`; `dlr_orchestrator` logs at INFO. No CI job runs `--store postgres` yet and the Actions smoke log was clean, so nothing has leaked; Phase 5's scheduled runner would print it. Fix before Phase 5. |
| WR-01 | warning | A run that fails to write some cities exits 0 | open | Relevant to Phase 5's scheduled runner (alerting). |
| WR-02 | warning | A data-cleaning failure is reported as a healthy `cold_start` | open | |
| WR-03 | warning | No reconnect or retry on the long-lived connection | open | Relevant to Phase 5. |
| WR-04 | warning | Backfill de-duplication keeps the first row, the opposite of the CSV rule it cites | open | Committed archive has 0 duplicates; no effect on the loaded rows. |
| WR-05 | warning | Backfill identity child is coupled to every module-level config read in live code | open | Matters only for a backfill re-run after Phase 7 config changes. |
| IN-01 | info | `_RUN_ERROR_MAX_CHARS = 1000` is dead; error text is cut to 300 characters | open | |
| IN-02 | info | `connect()` validates the stripped URL but connects with the unstripped one | open | |
| IN-03 | info | Column comments in the migration disagree with the code and the schema doc | open | Live schema is pushed; a fix is a new additive migration (comments only). |
| IN-04 | info | Duplicated and cross-module private helpers | open | |
| IN-05 | info | Workflow hardening | open | |
| IN-06 | info | `valid_time` CHECK depends on the session time zone | open | `connect()` pins UTC. |
