---
phase: 06-exposure-e2e-verification
plan: 05
subsystem: database
tags: [postgres, supabase, pg_cron, soak, freshness-log, ops-schema, pytest, psycopg]

requires:
  - phase: 06-exposure-e2e-verification
    provides: "public.latest_rating (is_stale, age_minutes), public.assert_fresh, supabase/ops/verify_exposure.sql style, backend/tests/local_pg.py harness (plan 06-01)"
  - phase: 04-supabase-store-writer
    provides: "role dlr_writer, public.city_rating"
provides:
  - "Unapplied migration 20261026204258_soak_freshness_log.sql: schema ops, table ops.freshness_log, index freshness_log_probed_at_idx, function ops.log_freshness() (returns rows written), nothing granted to public/anon/authenticated, dlr_writer USAGE + SELECT only"
  - "supabase/ops/soak_cron_schedule.sql and soak_cron_unschedule.sql: owner one-shots for the pg_cron job dlr-soak-freshness (*/5 * * * *), outside migration history"
  - "supabase/ops/soak_probe_smoke.sql: read-only 4-check smoke test before the 72 h clock (D-07)"
  - "supabase/ops/verify_monitoring.sql: read-only 7-check privilege and presence test for the ops objects"
  - "backend/tests/soak_log_migration_test.py: 24 collected tests (15 functions, one parametrized x10) incl. a stub cron schema"
affects: [06-06, 06-07, 06-09, 06-10, 06-12, 06-13]

# Actuals (#2632): same estimateTokens scale (chars/4 over the realized diff)
actuals:
  tokens: 12250
  tasks: 2
  commits: 2
plan_head_before: ee1a731e8605e6e5ed9e1f9041b92963db93d334
plan_head_after: 53e17c9a8177a59781f71499af0658e2ef34e50c

tech-stack:
  added: []
  patterns:
    - "Soak log reads the consumer view's own is_stale and the exact age, so the record, the consumer flag and the alarm share one 90-minute rule"
    - "Scheduling kept out of migration history: owner SQL under supabase/ops, tested against a stub cron schema"
    - "Fault-injection parametrized test for a read-only smoke check (each check proven able to fail, evidence outside the last-three window proven ignored)"
    - "Exact-age proofs by dropping the whole-hour CHECK inside a rolled-back transaction (now() is fixed per transaction)"

key-files:
  created:
    - supabase/migrations/20261026204258_soak_freshness_log.sql
    - supabase/ops/verify_monitoring.sql
    - supabase/ops/soak_cron_schedule.sql
    - supabase/ops/soak_cron_unschedule.sql
    - supabase/ops/soak_probe_smoke.sql
    - backend/tests/soak_log_migration_test.py
  modified: []

key-decisions:
  - "age_seconds is numeric holding extract(epoch ...) unrounded, so breach equals age_seconds > 5400 for every row, including exactly 90 minutes (fresh) and 90 minutes plus one microsecond (breach)"
  - "ops.log_freshness() returns integer (rows written) rather than void, as the plan's behavior section requires; it is plpgsql with an empty search_path and runs as the caller (no security definer)"
  - "verify_monitoring.sql reports the not-readable / not-executable checks as false when the object is missing, since a privilege cannot be confirmed on something that does not exist"
  - "dlr_writer check is true only with schema USAGE and table SELECT and none of insert, update, delete, truncate (read-only, not just able to read)"
  - "Smoke check requires exactly three runs and three probes of four rows to pass; fewer is a failure with the count in the detail"

patterns-established:
  - "Owner SQL files are plain SQL for the editor (no psql meta-commands, no transaction control); a header states when to run it and what each check means in plain English"

requirements-completed: [E2E-02]

coverage:
  - id: D1
    description: "ops.log_freshness() writes one row per config.LOCATIONS city; breach is latest_rating's is_stale and equals age_seconds > 5400, to the microsecond at the 90-minute boundary"
    requirement: E2E-02
    verification:
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_tracer_log_freshness_matches_the_view"
        status: pass
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_two_hour_old_rows_are_breaches_and_one_hour_old_are_not"
        status: pass
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_exactly_90_minutes_is_fresh_in_the_log_and_one_microsecond_more_is_a_breach"
        status: pass
    human_judgment: false
  - id: D2
    description: "A city with no rating is logged with null valid time, null age and breach true"
    requirement: E2E-02
    verification:
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_missing_city_is_a_breach_with_null_age"
        status: pass
    human_judgment: false
  - id: D3
    description: "ops is unreachable for anon, authenticated and PUBLIC (schema, table, sequence, function); dlr_writer can read the log and cannot write or call the function"
    requirement: E2E-02
    verification:
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_anon_and_authenticated_cannot_reach_ops"
        status: pass
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_dlr_writer_can_read_but_not_write_the_log"
        status: pass
    human_judgment: false
  - id: D4
    description: "The migration schedules nothing (no pg_cron reference in code), sorts after the expose migration, grants only the two dlr_writer read rights, and its city list equals config.LOCATIONS"
    requirement: E2E-02
    verification:
      - kind: unit
        ref: "backend/tests/soak_log_migration_test.py#test_soak_migration_schedules_nothing_and_sorts_after_expose"
        status: pass
      - kind: unit
        ref: "backend/tests/soak_log_migration_test.py#test_soak_city_list_matches_config_locations"
        status: pass
    human_judgment: false
  - id: D5
    description: "verify_monitoring.sql is one read-only SELECT of 7 checks, all true locally, and each check can fail"
    requirement: E2E-02
    verification:
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_verify_monitoring_sql_reports_every_check_ok"
        status: pass
    human_judgment: false
  - id: D6
    description: "Re-applying the soak migration succeeds, changes no grant, definition, comment or logged row; the expose migration's tests still pass with it present"
    requirement: E2E-02
    verification:
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_soak_migration_reapplies_cleanly"
        status: pass
      - kind: integration
        ref: "backend/tests/expose_migration_test.py (21 tests)"
        status: pass
    human_judgment: false
  - id: D7
    description: "The schedule file creates one named job and is repeatable; the unschedule file removes it, touches no other job and is a no-op when absent (against a stub cron schema)"
    requirement: E2E-02
    verification:
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_schedule_file_creates_one_job_and_is_repeatable"
        status: pass
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_unschedule_file_removes_the_job_and_is_a_no_op_after"
        status: pass
      - kind: unit
        ref: "backend/tests/soak_log_migration_test.py#test_owner_sql_files_name_the_job_and_command"
        status: pass
    human_judgment: false
  - id: D8
    description: "soak_probe_smoke.sql passes on healthy probes and flags a failed run, a missing run, a short probe, a breach, a paused or re-scheduled or re-pointed job, an unscheduled job and an empty log; evidence older than the last three is ignored"
    requirement: E2E-02
    verification:
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_probe_smoke_passes_on_healthy_probes"
        status: pass
      - kind: integration
        ref: "backend/tests/soak_log_migration_test.py#test_probe_smoke_fails_on_a_failed_run_a_short_probe_or_a_breach (10 cases)"
        status: pass
    human_judgment: false
  - id: D9
    description: "The live half of E2E-02 (migration applied, real pg_cron job scheduled, probes written by the real scheduler on Supabase, the 72 h record) is NOT done here; it is plans 06-09, 06-10 and 06-12"
    requirement: E2E-02
    verification: []
    human_judgment: true
    rationale: "Per D-06 this plan is offline: pg_cron is not installed locally (a stub stands in), the grants and cron privileges of the real Supabase project and the real scheduler's behaviour can only be seen at the live run, and the soak itself takes 72 h"

# Metrics
duration: 7min
completed: 2026-10-26
status: complete
---

# Phase 6 Plan 05: Soak Freshness Log Summary

**A consumer-invisible `ops.freshness_log` written by `ops.log_freshness()` from `latest_rating`'s own `is_stale` flag and the exact age in seconds, three owner SQL scripts (start the `dlr-soak-freshness` pg_cron job, stop it, smoke-check it) and a read-only privilege check, all proven on a local Postgres with a stub pg_cron; nothing applied or scheduled on Supabase.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-10-26T20:43:26Z
- **Completed:** 2026-10-26T20:50:00Z
- **Tasks:** 2 (1 tracer, 1 auto/tdd)
- **Files modified:** 6 (6 created)

## Accomplishments

- **Migration** `supabase/migrations/20261026204258_soak_freshness_log.sql` (sorts after `20261026195124_expose_latest_rating.sql`; no earlier file touched). Plain English: every probe writes one row per city saying when the city's current rating is valid from, how many seconds old it is, and whether that is a breach. The breach flag is the very flag consumers see (`latest_rating.is_stale`), so the soak record, the dashboard flag and the alarm apply one 90-minute rule (D-02). It schedules nothing.
- **Proofs on the local cluster** (what each means for the owner): the log's flag equals the view's flag for every city and equals `age_seconds > 5400`; rows two hours old are all breaches and rows one hour old are not; at exactly 90 minutes the log says fresh and at 90 minutes plus one microsecond it says breach (the same boundary the view and `assert_fresh` use); a city with no rating is still logged, with null time, null age and breach true; the public key (anon and authenticated) cannot see the schema, read the log, write to it, use its sequence or run the function, with no grant to PUBLIC either; the writer role `dlr_writer` can read the log and cannot change it or call the function; re-applying the migration changes nothing, including logged rows.
- **Owner scripts**, all plain SQL for the SQL editor: `soak_cron_schedule.sql` (`cron.schedule('dlr-soak-freshness', '*/5 * * * *', 'select ops.log_freshness()')` then shows the job row), `soak_cron_unschedule.sql` (unschedules by selecting the jobid of that name, so no row means no call; reports `remaining_jobs` = 0), `soak_probe_smoke.sql` (D-07: job active on the 5-minute schedule, last three runs succeeded, last three probes wrote four rows each, no breach in them). Run against a stub `cron` schema (documented `job` and `job_run_details` tables plus `schedule` and `unschedule`): the schedule file is repeatable (one job, an altered job is restored, other jobs untouched), the unschedule file removes only that job and is a no-op the second time, and the smoke check passes on healthy probes and fails with a readable detail for ten injected faults (failed run, missing run, short probe, breach, missing city in an older probe, paused job, wrong schedule, wrong command, unscheduled job, empty log). An old failure and an old breach outside the last three do not trip it.
- **`verify_monitoring.sql`**: 7 checks (`ops_schema_not_usable_by_anon_or_authenticated`, `freshness_log_not_readable_by_anon_or_authenticated`, `log_freshness_not_executable_by_anon_or_authenticated`, `freshness_log_present`, `log_freshness_present`, `dlr_writer_can_read_freshness_log`, `assert_fresh_executable_by_anon`); every one true locally, and each turns false when the matching fault is injected (a stray grant, a stray execute, a dropped object, a lost or extra writer right, a revoked `assert_fresh` execute); with `dlr_writer` absent the writer check is true with detail "role absent".
- **Mutation spot-check** (SQL mutated, tests re-run, files restored byte-identical): a missing city treated as fresh fails 1 test; `floor` on the age fails 1; a private 89-minute rule in the log fails 3; dropping the function revoke fails 2; giving `dlr_writer` INSERT fails 3; an unschedule with no name filter fails 2; a loosened smoke row count fails 2; a 4-probe smoke window fails 11; a 6-minute schedule fails 13.

## Task Commits

1. **Task 1 (tracer): ops freshness log reading latest_rating is_stale, with its privilege checks, proven on a local Postgres** - `3601475` (feat)
2. **Task 2: owner pg_cron scripts and the probe smoke check, run against a stub cron schema** - `53e17c9` (feat)

**Plan metadata:** committed with this SUMMARY (docs: complete plan).

The tracer gate: `type="tracer"` without `gate="blocking-human"` and with an automated-only `<verify>`, so the tracer verify was re-run end to end (31 passed with the expose tests, nothing skipped) and expansion continued with no checkpoint.

## Files Created/Modified

- `supabase/migrations/20261026204258_soak_freshness_log.sql` - ops schema, `ops.freshness_log`, `ops.log_freshness()`, revokes, dlr_writer read grants, comments
- `supabase/ops/verify_monitoring.sql` - 7-check read-only SELECT (check_name, ok, detail)
- `supabase/ops/soak_cron_schedule.sql` - owner one-shot: register `dlr-soak-freshness`
- `supabase/ops/soak_cron_unschedule.sql` - owner one-shot: remove it, report 0 remaining
- `supabase/ops/soak_probe_smoke.sql` - read-only 4-check smoke test before the 72 h clock
- `backend/tests/soak_log_migration_test.py` - 15 test functions (24 collected), stub cron schema fixture

## Decisions Made

- Followed D-02, D-06, D-07, D-13 and D-14 and the plan's SQL. `age_seconds` is `numeric` (PostgreSQL's `extract(epoch ...)` on an interval is exact to the microsecond), not rounded.
- The function returns the number of rows written via `GET DIAGNOSTICS` (4 when every city is listed), as the plan specifies, instead of the `void` of 06-RESEARCH's older sketch.
- In `verify_monitoring.sql`, a missing object turns the "not readable" and "not executable" checks false, so a typo or a dropped table cannot read as "safe".

## Deviations from Plan

### Auto-fixed Issues

None for the SQL: the migration and scripts are as planned.

**1. [Rule 2 - Missing critical] Extra tests and checks beyond the plan's list**
- **Added:** `test_exactly_90_minutes_is_fresh_in_the_log_and_one_microsecond_more_is_a_breach` (the plan's two-hour and one-hour test cannot hit the exact tie, and the plan's OD-4 adjacency edge needs it), and a writer-is-read-only clause in the `dlr_writer_can_read_freshness_log` check plus the `insert` privilege in the anon/authenticated checks. The suite has 15 functions (the plan asks for at least 14).
- **Committed in:** 3601475

**2. [Rule 1 - Bug] Test fault injections hit the wrong probe**
- **Found during:** Task 2 (writing the smoke fault cases before the SQL)
- **Issue:** the first draft of the injections used `max(id)` / `max(runid)`, which selects the OLDEST seeded probe and the OLDEST of three runs (seeded newest first), so a fault would have landed outside the window or in the wrong place.
- **Fix:** the injections order by `probed_at desc` / `start_time desc` to hit the newest probe and newest run. Fixed in the test before any SQL existed, so no commit carries the wrong form.
- **Committed in:** 53e17c9

**3. Attribution line.** The plan asked for `Co-Authored-By: Claude Opus 5.5`; the commits carry the session's attribution lines (`Claude Sonnet 5.5` plus the session link) per the executor instructions.

### TDD note

Both tasks wrote tests first. Task 1: all 10 tests failed against the empty tree (no migration, no verify file) and all 10 passed once the migration and `verify_monitoring.sql` existed. Task 2: 14 of the 24 tests failed (five new test functions, one parametrized x10, minus none passing) before the three owner files existed, then all 24 passed.

---

**Total deviations:** 1 added coverage (Rule 2), 1 test-side bug caught before commit (Rule 1), 1 attribution wording note.
**Impact on plan:** no scope creep; migration, scripts and checks are as planned.

## Discrepancies

none. (The plan and the 06-RESEARCH sketch differ on `ops.log_freshness`'s return type and `age_seconds`'s type, `void`/`integer` versus the plan's `integer` rows count/`numeric`; the plan governs and was implemented. `soak_cron_schedule.sql` carries the `*/5 * * * *` literal on exactly one line, as the acceptance criterion counts lines, so the header prose says "every five minutes" instead.)

## Issues Encountered

None blocking. Pre-existing working-tree changes (.DS_Store files, `.planning/config.json`, untracked `.obsidian/`, `graphify-out/`, etc.) were left unstaged. pg_cron itself was not run locally (not installed): the owner scripts were proven against a stub whose tables and functions follow the documented shape, so the first scheduled run on Supabase (plan 06-10) remains the real test of the scheduling role's rights (06-RESEARCH assumption A20); the probe smoke check is the planned detector for that.

## Known Stubs

None. No placeholder text, empty-value paths or unwired data in the files this plan created. (The stub `cron` schema lives only inside the tests, by design.)

## Threat Flags

None. The `ops` schema, the pg_cron scripts and the grants are exactly the surface in the plan's threat model (T-06-16..T-06-18); T-06-SC stays accepted (no package installed).

## User Setup Required

None - no external service configuration required in this plan. Later, in plan 06-09 the owner applies the soak migration (`supabase db push`), in 06-10 the owner enables the Cron integration and runs `soak_cron_schedule.sql`, then `soak_probe_smoke.sql` before the 72 h clock, and in 06-12 runs `soak_cron_unschedule.sql`. Nothing was pushed and nothing was applied or scheduled on Supabase.

## Next Phase Readiness

- Ready for 06-06 onward and for 06-09/06-10/06-12. `ops.freshness_log` columns for the soak export: id, probed_at, city, latest_valid_time, age_seconds (numeric seconds), breach; the `dlr_writer` role can read it.
- E2E-02 stays open in REQUIREMENTS.md on purpose: later plans in this phase also declare it and its live half (the 72 h record) is 06-10 through 06-12.
- Carried note for 06-09: if the live project's Cron job role cannot read `public.latest_rating` (the job runs as the role that scheduled it), the first run fails and the smoke check's `last_three_runs_succeeded` shows the error text.

## Self-Check: PASSED

- Files present: migration, `verify_monitoring.sql`, `soak_cron_schedule.sql`, `soak_cron_unschedule.sql`, `soak_probe_smoke.sql`, `soak_log_migration_test.py` (all FOUND).
- Commits `3601475` and `53e17c9` are ancestors of HEAD; `git rev-list --count ee1a731..HEAD` measured 2 at SUMMARY time.
- Task acceptance criteria re-run: one soak migration sorting after the expose migration; `public.latest_rating` referenced 4 times; `check_name` present in `verify_monitoring.sql`; `dlr-soak-freshness` present 3 times in each of the three owner files; `*/5 * * * *` on exactly 1 line of the schedule file; 15 test functions (at least 14).
- Verify commands: `DLR_TEST_PG_AUTOSTART=1 ... soak_log_migration_test.py expose_migration_test.py` 31 passed, none skipped (Task 1); `DLR_TEST_PG_AUTOSTART=1 ... soak_log_migration_test.py` 24 passed, none skipped; default full suite 1833 passed, 81 skipped (the skips are the local-Postgres tests without the autostart flag), 0 failed.
- `git status --porcelain -- data/shadow .github/workflows/shadow_collect.yml` prints nothing; no `cron.` reference in any migration code.

---
*Phase: 06-exposure-e2e-verification*
*Completed: 2026-10-26*
