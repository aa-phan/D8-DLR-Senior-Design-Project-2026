---
phase: 04-supabase-store-writer
plan: 05
subsystem: database
tags: [supabase, migration, schema-push, dlr-writer, smoke-test, owner-steps]

requires:
  - phase: 04-supabase-store-writer
    provides: "04-01: the migration and the dlr_writer role design; 04-03: supabase_smoke.py; 04-04: the consumer contract the owner approved"
provides:
  - "Live Supabase project (Free plan, us-east-1) with public.city_rating, public.pipeline_run and role dlr_writer, applied by `supabase db push` (migration history recorded)"
  - "SUPABASE_ADMIN_DB_URL and SUPABASE_DB_URL in the owner's git-ignored .env (session pooler, port 5432)"
  - "docs/data-science/decisions/supabase_store/smoke_local.json: SMOKE OK from the owner's machine (committed by 04-06)"
affects: [04-06 Actions smoke and backfill load, 05 scheduled runs, 06 read view]

actuals:
  tasks: 3
  commits: 0
plan_head_before: a628639
plan_head_after: a628639

key-files:
  created: []
  modified: []

key-decisions:
  - "Schema contract approved as written (owner, 2026-10-23): migration 20261019000000_create_city_rating.sql, the dlr_writer role design and city_rating_v1.md"
  - "Migration path: Supabase CLI 2.121.0 (npm, installed with --ignore-scripts under ~/tools/supabase-cli), not psql; Phases 5 and 6 push later migrations the same way"
  - "CLI kept at the verified 2.121.0 although it reports 2.122.0 available; moving needs the Task 1 check again"

requirements-completed: [DB-01, DB-04]
---

# 04-05 Summary: schema pushed to the live Supabase project

The owner verified and installed the Supabase CLI, approved the schema contract, created the project, pushed the committed migration, set the `dlr_writer` credential and ran the smoke test from their machine. The smoke test passed all 12 checks against the live project.

## Task outcomes

1. **Task 1, CLI package gate:** owner checked the npm `supabase` package and installed it outside the repository with `--ignore-scripts`. Resume signal "cli approved"; `~/tools/supabase-cli/node_modules/.bin/supabase --version` prints `2.121.0`.
2. **Task 2, schema approval:** owner answered "approve". Migration, role design and `city_rating_v1.md` go out unchanged.
3. **Task 3, schema push:** CLI path. Project region `us-east-1` (session pooler, port 5432).

## Push output (no URL in any of it)

Dry run:
```
DRY RUN: migrations will *not* be pushed to the database.
Connecting to remote database...
Would push these migrations:
 • 20261019000000_create_city_rating.sql
Finished supabase db push.
```

Apply:
```
Connecting to remote database...
Do you want to push these migrations to the remote database?
 • 20261019000000_create_city_rating.sql
Yes
Applying migration 20261019000000_create_city_rating.sql...
Finished supabase db push.
```

Second push (SC1, re-applying is a no-op):
```
Connecting to remote database...
Remote database is up to date.
```

## Smoke check lines (smoke_local.json, checked_at 2026-10-23T19:14:09Z)

`all_passed: true`; checks: connected, consumers_cannot_write, delete_denied, rating_upsert_idempotent, rls_enabled, role_is_dlr_writer, run_row_idempotent, server_version_ge_15, ssl_in_use, tables_exist, writer_policies_exist, writer_privileges_exact, all true. Info: role `dlr_writer`, `server_version_num` 170011 (Postgres 17), `anon_can_select` false, `city_rows` empty (no rows before the 04-06 backfill).

The plan's verification command printed `SMOKE_LOCAL_OK` (schema `supabase_smoke/1`, required checks true, no `pooler.supabase.com`, `postgresql://` or `supabase.co` in the file).

## Owner commands as run (for Phases 5 and 6)

All from `/Users/aphan/Senior_Design`; `.env` is loaded through python-dotenv because its `KEY = value` spacing cannot be sourced by a shell.

Migration push (add `'--dry-run'` after `u` for a dry run):
```
.venv/bin/python -c "from dotenv import dotenv_values; import os, subprocess, sys; u=dotenv_values('/Users/aphan/Senior_Design/.env')['SUPABASE_ADMIN_DB_URL']; sys.exit(subprocess.run([os.path.expanduser('~/tools/supabase-cli/node_modules/.bin/supabase'), 'db', 'push', '--db-url', u]).returncode)"
```

Connection check:
```
.venv/bin/python -c "from dotenv import dotenv_values; import subprocess; subprocess.run(['psql', dotenv_values('/Users/aphan/Senior_Design/.env')['SUPABASE_ADMIN_DB_URL'], '-c', 'select 1'])"
```

Smoke test:
```
PYTHONPATH=backend .venv/bin/python -c "from dotenv import load_dotenv; load_dotenv('/Users/aphan/Senior_Design/.env'); import sys, supabase_smoke; sys.exit(supabase_smoke.main(['--report', 'docs/data-science/decisions/supabase_store/smoke_local.json']))"
```

## Deviations from Plan

- **The executor read `.env` once, at the owner's request.** The admin login failed repeatedly (`password authentication failed`), including through psql. The owner gave the password in chat and asked for the cause. A script loaded `SUPABASE_ADMIN_DB_URL` through python-dotenv and printed only structure (lengths, bracket and equality checks, never the value). Cause: the password was wrapped in the `[ ]` of the dashboard's `[YOUR-PASSWORD]` placeholder. This crosses the plan's prohibition that the executor not read `.env`; the owner authorized it and planned to reset the database password afterwards because it appeared in chat.
- No executor subagent was spawned: every task is an owner checkpoint, so the orchestrator presented them directly.

## Discrepancies

- That `dlr_writer`'s credential was set with psql's `\password` (step 6) is owner-reported, not observed. The smoke result (`role_is_dlr_writer`, `writer_privileges_exact`) confirms the role logs in through the pooler as `dlr_writer.<project-ref>` with the expected privileges.
- `.env` also holds a `SUPABASE_DB_PASSWORD` entry that no plan uses; the owner was told to delete it or keep it current.

## Issues Encountered

- First dry run: `failed to parse connection string`; the password needed percent-encoding (`#` as `%23`), later replaced by a password without special characters.
- Then `password authentication failed for user "postgres"`, from both the CLI and psql: the brackets above.

## User Setup Required

- Reset the database (postgres) password, since it appeared in chat; update `.env` and the password manager.
- Re-run the smoke test once after 2026-10-30 (the platform stops auto-granting new tables that day) and keep the newer `smoke_local.json`; `consumers_cannot_write` must still pass.
- 04-06: add `SUPABASE_DB_URL` as a GitHub secret, push the CI changes, dispatch the Actions smoke test, load the backfill.

## Known Stubs

None.

## Threat Flags

None new. The admin password appeared in chat once (owner's choice, for debugging); mitigated by the reset above.

## Next Phase Readiness

- Ready for 04-06: the live schema, the writer credential and a passing local smoke test exist. `smoke_local.json` is untracked and is committed by 04-06 Task 3.

## Self-Check: PASSED

- FOUND: docs/data-science/decisions/supabase_store/smoke_local.json; verification printed SMOKE_LOCAL_OK
- CLI output shows the one migration in the dry run and "Remote database is up to date." on the second push
- No commits expected (files_modified is empty)
