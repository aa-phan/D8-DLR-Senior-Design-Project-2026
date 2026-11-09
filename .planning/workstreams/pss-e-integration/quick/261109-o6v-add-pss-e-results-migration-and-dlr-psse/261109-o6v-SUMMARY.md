---
phase: 261109-o6v-add-pss-e-results-migration-and-dlr-psse
plan: 01
subsystem: database
tags: [supabase, postgres, rls, pss-e, migration]
requires:
  - phase: production-pipeline (archived)
    provides: dlr_writer pattern, verify_exposure.sql, the migration and apply workflow
provides:
  - four private PSS/E result tables and role dlr_psse_writer (INSERT and SELECT only), applied live
  - supabase/ops/verify_psse_results.sql, the read-only checker (7 pinned checks)
  - a session-pooler credential for dlr_psse_writer in an owner-only file outside the repo
affects: [pss-e-integration Phase 3 real run, PSS/E job write step]
tech-stack:
  added: []
  patterns:
    - verbatim marked-region copy of a reviewed DDL, pinned by sha256
    - client-side SCRAM verifier for ALTER ROLE so the password never reaches the server
key-files:
  created:
    - supabase/migrations/20261109233541_psse_results.sql
    - supabase/ops/verify_psse_results.sql
    - backend/tests/psse_results_migration_test.py
    - .planning/workstreams/pss-e-integration/quick/261109-o6v-add-pss-e-results-migration-and-dlr-psse/261109-o6v-live-checks.json
  modified:
    - backend/tests/day_ahead_expose_test.py
key-decisions:
  - "Ship the tables as a standalone owner migration on main, because production-pipeline Phase 6 is archived"
  - "Results stay private (teammate D-03): anon and authenticated get nothing, so verify_exposure.sql is unchanged"
requirements-completed: [DBX-01, DBX-02]
duration: about 1 hour
completed: 2026-11-09
status: complete
commits: 3
plan_head_before: e90e12c1f34ef2ae47924e1e437996708f2447c5
plan_head_after: edbb2fd1d01f21dbcd3e5cb1cafbef2f57c9b313
actuals:
  tokens: 16000
  tasks: 3
  commits: 3
---

# Quick 261109-o6v: PSS/E results migration and dlr_psse_writer Summary

The teammate's four PSS/E result tables and the `dlr_psse_writer` role are live on Supabase, nothing new is exposed to the public keys, and the role has a password that exists only in `~/.dlr_psse_writer_conn.txt` (mode 600).

## What shipped

- **Migration** `supabase/migrations/20261109233541_psse_results.sql`, file sha256 `08e7e103eda9a77653d482ba67aea4844641d0d77f1e6d6f97213b83ccc13bd7`. The marked region (243 lines) is a verbatim copy of the reference DDL at commit 30ec2d6 of `origin/feature/pss-e-integration`, built by script from `git show` and pinned to region sha256 `955f349d2df66394dbec4378ddcc2d9eb61f7e37bd4eda8de4b70de16c3a6643`. Every line outside the region is a comment. It sorts last of 7 migrations.
- **Checker** `supabase/ops/verify_psse_results.sql`: one read-only SELECT, 7 checks in a pinned order (tables exist, RLS on, public roles hold nothing, writer holds exactly INSERT and SELECT, writer holds nothing elsewhere, policies are insert and select only, role attributes).
- **Tests** `backend/tests/psse_results_migration_test.py` (25 tests): region hash, ordering, comment-only header, checker shape, local-Postgres privilege tests for the writer, anon and authenticated, re-apply twice, exposure checker unchanged by the migration, one negative per check, and the applied-file pin. `day_ahead_expose_test.py` had its one ordering assertion relaxed to allow the psse_results migration after the expose migration; the test name and every other line are unchanged.

## Comparison with the dlr_writer pattern

| | dlr_writer (20261019000000) | dlr_psse_writer (this migration) |
|---|---|---|
| Role creation | inside a pg_roles guard, no credential | same |
| Row-level security | enabled | enabled |
| Schema usage | granted on public | granted on public |
| Policies | named per role | named per role |
| Privileges | one for-all policy | INSERT and SELECT only, separate insert and select policies (append-only; a run is never rewritten) |
| Role scope | the pipeline | separate role, because the job runs on another team's laptop |
| Revoke | anon, authenticated | also PUBLIC |

## Live results

| Step | Result |
|---|---|
| Baseline `verify_exposure.sql` | 29 checks, all ok |
| Dry run before push | exactly one pending file, the psse_results migration |
| `db push` | exit 0, migration applied |
| Dry run after push | up to date, nothing pending |
| `verify_exposure.sql` after | 29 checks, all ok, same names and order, detail identical on every check (no detail differences) |
| `verify_psse_results.sql` | 7 checks, all ok |
| dlr_psse_writer login through the session pooler | connected on attempt 1; reads psse_run (0 rows); INSERT on all four tables; no UPDATE, DELETE or TRUNCATE; refused on city_rating |
| Rows inserted into live psse tables | none |

Redacted evidence: `261109-o6v-live-checks.json` (redaction scan clean, no `://` in it).

## Connection string

Format: session pooler; user `dlr_psse_writer.<project_ref>`; host = the project's pooler host (same as `SUPABASE_DB_URL`); port 5432; database postgres; sslmode=require.

The string is in `~/.dlr_psse_writer_conn.txt` (mode 600), outside the repo. Next steps for the user:

1. Send the string to the teammate directly, not through git or a chat channel. The teammate keeps it as `SUPABASE_PSSE_DB_URL`.
2. Delete the file after sending. Re-running `psse_live.py set-password` rotates the password.
3. Push `main` when ready. `origin/main` does not have the migration until then (this task did not push).

The password was generated in-process, handed to the server only as a client-side SCRAM-SHA-256 verifier, and never printed. The leak check (git history, diffs, every tracked and untracked file under 20 MB, the helper directory, the evidence file) was clean before and after the last commit.

## Scope decision

The tables shipped as a standalone owner migration on `main` because production-pipeline Phase 6, the planned vehicle, is archived. This is the owner step the teammate asked for in `psse_message_to_aaron.md`, items 1 to 3, plus the `verify_psse_results.sql` checker.

## service_role note

`service_role` keeps Supabase's normal admin access to these tables. The DDL does not revoke it, and `verify_exposure.sql` does not cover it. That is the standard Supabase arrangement and the key is server-side only; it is noted here so it is a known fact rather than a surprise.

## Deviations from Plan

None in the migration, checker or live steps; all ran as planned. Notes on execution:

- **[Rule 3 - Blocking] Fixture needs rating rows.** The exposure checker returns four false checks on an empty `latest_rating`, so the new test module's Postgres fixture seeds one fresh rating row per city, the same way `day_ahead_expose_test.py` does. Test-only. Found during Task 1.
- **[Rule 1 - Bug] Semicolons inside the checker's detail strings.** The one-statement test splits on `;`, and my first draft had `; ` inside string literals. Replaced them with commas in `verify_psse_results.sql`. Found during Task 1, before the first commit.
- Task 1 was written test and implementation together rather than as a separate failing run first.

## Deferred Issues

One full-suite failure, not caused by this task: `backend/tests/forecast_shadow_demo_test.py::test_run_once_all_methods_ok_with_per_city_artifacts_and_a_complete_truth_proxy_window`. It fails at about 23:50 UTC (reason: no usable solar row within 35 minutes for the truth-proxy window) and looks time-of-day dependent. Details in `deferred-items.md`. Full suite: 3023 passed, 3 skipped, 1 failed. The 3 skips are `e2e_readonly_test.py` live-evidence skips for earlier plans; none comes from `psse_results_migration_test.py`. The plan's migration-related verify set passed with 217 tests and no skips.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or trust boundary beyond the planned role and tables.

## Commits

- fbd3e22: feat(quick-261109-o6v): add psse_results migration, verify_psse_results.sql and tests
- 8d23624: test(quick-261109-o6v): pin the applied psse_results migration and record live checks
- edbb2fd: docs(quick-261109-o6v): record dlr_psse_writer login check

## Self-Check: PASSED

Files found: the migration, `verify_psse_results.sql`, the test file, the evidence JSON. Commits fbd3e22, 8d23624 and edbb2fd are on `main`. No helper script is in the repo.
