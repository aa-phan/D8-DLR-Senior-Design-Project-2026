---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
plan: 11
subsystem: exposure
tags: [day-ahead, supabase, postgrest, expose-migration, live-verification, sha256-pin, consumer-examples]

requires:
  - phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
    provides: "08-07 store migration and first issue run; 08-09 expose migration 20261108120100; 08-10 day_ahead_verify.py and verify_exposure.sql; 08-12 consumer examples and handoff docs"
provides:
  - "Live read-only exposure of day_ahead_forecast (full history), day_ahead_upcoming and day_ahead_status to anon/authenticated"
  - "Extended public.assert_fresh(integer) alarm armed on the day-ahead feed"
  - "Published contract docs and three extended examples on origin/main (4008477)"
  - "08-11-live-checks.json and 08-11-examples.json (redacted live evidence)"
  - "_APPLIED_EXPOSE_MIGRATION_SHA256 pin and test_expose_migration_is_unchanged_after_apply"
affects: [phase-08-verification]

actuals:
  tokens: 5100
  tasks: 3
  commits: 2
plan_head_before: cd68184202e547197e50484490e891a27a00e40a
plan_head_after: 5cf9f8c

tech-stack:
  added: []
  patterns:
    - "Applied-migration sha256 pin test, same shape as the store and Phase 6 pins"
    - "Evidence JSON built from redacted captures by a script outside the repository, then secret-scanned"

key-files:
  created:
    - .planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-11-PREFLIGHT.md
    - .planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-11-live-checks.json
    - .planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-11-examples.json
  modified:
    - backend/tests/day_ahead_expose_test.py

key-decisions:
  - "Owner chose expose-and-publish (D-17 go, D-09 one-way door): the day-ahead column names are now a consumer contract"
  - "The applied expose migration is pinned by sha256 253a539ec0dc41c47f31ec596855e8852769ce6993d587ebdf6e406aedcab816; any later edit fails the default suite"

requirements-completed: [DAY-06, DAY-07, DAY-08, DAY-09]

status: complete
---

# Phase 8 Plan 11: Day-Ahead Exposure, Live Summary

The day-ahead forecast table and its two views are now readable by anyone with the publishable key, the alarm covers the feed, the docs and three examples are on origin/main, and the applied expose migration is sha256-pinned.

## Owner decision (Task 2), verbatim

`expose and publish` (the `expose-and-publish` option).

## Tasks

| Task | Name | Commit |
|---|---|---|
| 1 | Pre-flight for the expose step | 4008477 |
| 2 | Owner decides to expose and publish | none (decision checkpoint) |
| 3 | Apply, verify, run the examples, publish, pin | evidence and pin 5cf9f8c; apply and push were live actions |

## Task 3 live results (2026-11-09 UTC)

Precondition: the latest hourly run before the apply, id 42554392916 (03:05Z, headSha 1088392, success), showed day-ahead outcome `none_due` for all four cities, so arming the alarm did not start with a late feed.

**Steps 1-2 (dry run and push, by the owner).** The dry run listed exactly `20261108120100_expose_day_ahead_forecast.sql`; the push applied it. The owner stated "i've run steps 1 and 2"; the command outputs were not pasted.

**Step 3 (SQL checks, run by the orchestrator).**
- `supabase/ops/verify_exposure.sql`: 29 rows, all ok = true (select grants on the five published objects 10 of 10; anon can select day_ahead_forecast, day_ahead_status and day_ahead_upcoming; assert_fresh has one signature; day_ahead_forecast RLS on; day_ahead_status shows four cities; both views security_invoker; day_ahead_upcoming has 26 columns with column 26 `lead_minutes`; every view column commented; `read_policy_day_ahead_forecast_public_read` = `day_ahead_forecast_public_read` SELECT plus `dlr_writer_all` ALL; pipeline_run not readable by anon).
- `supabase/ops/verify_monitoring.sql`: 7 rows, all ok = true.

**Step 4 (REST check).** `day_ahead_verify.py --check-rest --json-out .../08-11-live-checks.json`: exit 0, "DAY-AHEAD REST OK", 8 PASS.

| Check | Result |
|---|---|
| rest_upcoming_rows_are_future_and_ordered | PASS, 12 rows |
| rest_upcoming_columns_match_the_contract | PASS, 26 columns |
| rest_status_has_four_cities_none_late | PASS |
| rest_table_is_readable | PASS, 25 columns, newest target 2026-11-09T18:00:00+00:00 |
| rest_assert_fresh_ok_and_armed | PASS, HTTP 200, ok true, day_ahead_armed true |
| rest_anon_insert_into_table_refused | PASS, 401 42501 |
| rest_anon_write_to_upcoming_view_refused | PASS, 401 42501 |
| rest_pipeline_run_hidden | PASS, 401 42501 |

**Step 5 (D-18 example runs).** All exit 0, from `08-11-examples.json`.

| Example | Runtime | Exit | Ratings | History line | Label | Upcoming rows | Status rows (late) |
|---|---|---|---|---|---|---|---|
| curl.sh | bash, curl | 0 | 4 | total rows: 167 | seen | 12 | 4 (none) |
| read_ratings.py | /usr/bin/python3 3.9.6, -I | 0 | 4 | AUSTIN 168 rows, 2026-11-02 to 2026-11-09 | seen | 12 | 4 (none) |
| read_ratings.py --city AUSTIN | .venv Python 3.12.13, -I | 0 | 4 | AUSTIN 168 rows, 2026-11-02 to 2026-11-09 | seen | 12 | 4 (none) |
| supabase_js.mjs | Node v26.9.0, supabase-js 2.117.3 in ~/dlr-js-check (nothing installed; package.json pin checked) | 0 | 4 | AUSTIN 167 rows, 2026-10-25 to 2026-11-01 | seen | 12 | 4 (none) |

Current ratings seen: AUSTIN 1533.6 A ok, CORPUS_CHRISTI 1766.3 A ok, MIDLAND 1875.0 A fallback (G4), EL_PASO 1205.6 A ok, all 46 minutes old and not stale. The label `day-ahead-24h; engineering-selection; not-validated` was printed by every run.

**Step 6 (second dry run).** "Remote database is up to date.", exit 0.

**Step 7 (publishing push).** 2026-11-09T05:45:25Z `1088392..4008477 main -> main`, fast-forward, 23 commits, no `.github` changes. This published rest-api.md, day_ahead_forecast_v1.md, pss_e_handoff.md, software-team-handoff.md, api-contract.md, the three extended examples and the expose migration file. `git fetch origin` after the work confirms origin/main = 4008477781a9ec26e456554553ede703ec95a63e.

## Verification run

- live-checks verify: `all ok`, exit 0.
- `pytest backend/tests/day_ahead_expose_test.py -k unchanged_after_apply`: 1 passed. Whole expose test file with local Postgres: 24 passed.
- examples verify: names `['curl.sh', 'read_ratings.py', 'supabase_js.mjs']`, four runs, none failing.
- `backend/tests/secret_scan_test.py`: 5 passed, 1 skipped (the owner-local live scan needs SUPABASE_* env vars, which this run must not load). Compensating check: a grep of both evidence JSON files for the project host, JWT prefix, publishable/secret key prefixes, `apikey` and connection-string schemes found nothing.

## Deviations from Plan

None to the code. The live steps differed in who ran them: see Discrepancies.

## Discrepancies

- Steps 1-2 (dry run and push of the expose migration) were run by the owner; the owner confirmed them verbally ("i've run steps 1 and 2") and did not paste the outputs. The applied state is established by step 3's SQL checks and step 6's "up to date", not by the pasted push output.
- Steps 3-7, including the publishing push, were run by the orchestrator at the owner's request ("continue from there") instead of by the owner. URL and key were read from `.env` by the orchestrator and never printed.
- The evidence JSON, the pin and this SUMMARY are committed after the publishing push, so they are local commits (5cf9f8c and the docs commit) and wait for the owner's next approved push. They change no live behaviour.
- The plan's example entries asked for `first_lines`; the curl.sh and supabase_js.mjs entries keep section headers and counts rather than data rows, to stay short and free of host text.

## Known Stubs

None.

## Threat Flags

None. The exposure is the surface the plan's threat model covers (T-08-34 to T-08-38, T-08-45); no new endpoint, auth path or schema change beyond the planned migration.

## Self-Check: PASSED

- 08-11-PREFLIGHT.md, 08-11-live-checks.json, 08-11-examples.json: present.
- Commits 4008477 and 5cf9f8c are ancestors of HEAD; origin/main = 4008477.
- Pin test passes; no stubs.
