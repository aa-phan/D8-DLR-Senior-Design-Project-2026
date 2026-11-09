---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
plan: 09
subsystem: database
tags: [day-ahead, supabase, migration, postgres, views, security-invoker, assert-fresh, alarm, verify-exposure, tdd]

requires:
  - phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
    provides: "08-07 live private day_ahead_forecast table; 08-08 pushed write side and verified first slot (D-17 precondition)"
provides:
  - "public.day_ahead_upcoming (26 columns incl. lead_minutes) and public.day_ahead_status (7 columns, always four rows, 12 h late rule), both security_invoker"
  - "SELECT-only access for anon and authenticated on the day-ahead table and both views, policy day_ahead_forecast_public_read"
  - "public.assert_fresh(integer) with the same signature plus the armed day_ahead_late clause and day_ahead_armed in the 200 body"
  - "verify_exposure.sql generalised to the five published objects with eleven day-ahead checks (29 checks)"
affects: [08-10, 08-11, 08-12]

key-files:
  created:
    - supabase/migrations/20261108120100_expose_day_ahead_forecast.sql
    - backend/tests/day_ahead_expose_test.py
  modified:
    - supabase/ops/verify_exposure.sql
    - backend/tests/expose_migration_test.py

key-decisions:
  - "One late rule lives in public.day_ahead_status and the alarm reads it, so the consumer flag and the alarm cannot disagree"
  - "The status grid is date_bin over a fixed UTC origin (2000-01-01), so targets are exactly 00/06/12/18 UTC with no time-zone dependence"
  - "The day-ahead part of the alarm is armed by any row in the table (a past row also arms it), as D-12 states; a never-written table cannot raise a false alarm"

requirements-completed: [DAY-06, DAY-07]

actuals:
  tokens: 17000
  tasks: 2
  commits: 4
plan_head_before: a68027a4b9d8a5cd61f1efdca7850a7b07425d1d
plan_head_after: 3f75e7f1b3a7f1950f52a2d64dd9b64c3d8747d7

coverage:
  - id: D1
    description: "day_ahead_upcoming returns only future targets, ordered by city then valid_time, with exactly the 26 contract columns and lead_minutes equal to the ceiling of minutes to the target; past values stay readable in the table"
    requirement: DAY-06
    verification:
      - kind: integration
        ref: "backend/tests/day_ahead_expose_test.py#test_upcoming_shows_only_future_targets_ordered_with_a_positive_lead"
        status: pass
      - kind: unit
        ref: "backend/tests/day_ahead_expose_test.py#test_text_both_views_are_security_invoker_and_the_select_lists_equal_the_contract"
        status: pass
    human_judgment: false
  - id: D2
    description: "day_ahead_status always returns four rows with the 7 contract columns; missing_targets lists exactly the unfilled 00/06/12/18 UTC targets within 12 h; is_late is armed by the first row"
    requirement: DAY-06
    verification:
      - kind: integration
        ref: "backend/tests/day_ahead_expose_test.py#test_status_a_city_missing_one_due_target_is_late_with_that_exact_timestamp"
        status: pass
      - kind: integration
        ref: "backend/tests/day_ahead_expose_test.py#test_status_with_an_empty_table_has_four_rows_not_late_and_lists_the_due_targets"
        status: pass
    human_judgment: false
  - id: D3
    description: "anon and authenticated hold SELECT only on the three day-ahead objects; every write is refused; one read policy and no write policy; every view column commented"
    requirement: DAY-06
    verification:
      - kind: integration
        ref: "backend/tests/day_ahead_expose_test.py#test_the_public_roles_can_read_the_table_but_every_write_is_refused"
        status: pass
      - kind: unit
        ref: "backend/tests/day_ahead_expose_test.py#test_text_the_only_privileges_are_select_on_the_three_objects_and_one_read_policy"
        status: pass
    human_judgment: false
  - id: D4
    description: "assert_fresh keeps one signature, its 90-minute rule, 22023 and PT503, and raises PT503 with day_ahead_late= when an armed city is late; 200 body gains day_ahead_armed"
    requirement: DAY-07
    verification:
      - kind: integration
        ref: "backend/tests/day_ahead_expose_test.py#test_alarm_armed_with_a_late_city_raises_pt503_naming_the_city_and_target"
        status: pass
      - kind: integration
        ref: "backend/tests/day_ahead_expose_test.py#test_alarm_there_is_exactly_one_assert_fresh_and_it_keeps_its_attributes"
        status: pass
    human_judgment: false
  - id: D5
    description: "verify_exposure.sql covers the five published objects with 29 checks, all ok on local Postgres after all six migrations, and each new check turns false under its sabotage"
    requirement: DAY-06
    verification:
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_verify_exposure_sql_reports_every_check_ok"
        status: pass
      - kind: integration
        ref: "backend/tests/expose_migration_test.py#test_verify_exposure_sql_catches_each_day_ahead_sabotage"
        status: pass
    human_judgment: false
  - id: D6
    description: "The migration is applied live and consumers can read the views through the REST API"
    requirement: DAY-06
    verification: []
    human_judgment: true
    rationale: "Written, not applied: 08-11 applies it and 08-10 documents and checks it over REST. Nothing in this plan touches the live project."

duration: 12min
completed: 2026-11-09
status: complete
---

# Phase 8 Plan 09: Day-Ahead Expose Migration and Alarm Clause Summary

**An additive, re-apply-safe expose migration (written, not applied) publishes `day_ahead_upcoming` and `day_ahead_status` read-only with SELECT-only grants, extends `assert_fresh` under the same signature to raise PT503 `day_ahead_late=` for a stalled day-ahead feed once the first row arms it, and the privilege sweep now proves all five published objects (29 checks).**

## Performance

- **Duration:** about 12 min (2026-11-09T01:15:52Z to about 01:27Z)
- **Tasks:** 2 (both TDD: a failing-test commit then an implementation commit each)
- **Files:** 2 created, 2 modified

## Accomplishments

- `supabase/migrations/20261108120100_expose_day_ahead_forecast.sql`: the upcoming view (the 25 table columns plus `lead_minutes`, the ceiling of minutes to the target), the status view (always four rows; `missing_targets` from a UTC `date_bin` grid over `now() < T <= now() + 12 h`; `is_late` only when the table holds a row), SELECT-only grants, the `day_ahead_forecast_public_read` policy, a unit-first comment on every view column, and `assert_fresh` replaced under its exact signature. It sorts last, is idempotent, and was not applied anywhere.
- `assert_fresh`: the Phase 6 rating rule, the `22023` range check and the `PT503` code are unchanged; it now also reads `public.day_ahead_status` (the one late rule), raises `PT503` with detail `missing=... stale=... day_ahead_late={CITY@UTC-time,...}` when an armed city is late, and its 200 body gains `day_ahead_armed`. With no day-ahead row it behaves as in Phase 6 (200, `day_ahead_armed` false).
- `supabase/ops/verify_exposure.sql`: the published set is a single `published` CTE of five objects (10 SELECT grants), the grants check is renamed `anon_authenticated_grants_are_select_on_published_objects_only`, and eleven day-ahead checks are added. Still one read-only SELECT.
- 23 new tests in `day_ahead_expose_test.py` (text, upcoming, status, alarm, grants and policy, writes refused for anon and authenticated on the table and both views, reapply of the whole chain) and 15 new/changed cases in `expose_migration_test.py` (29 check names, 14 parametrised sabotage cases plus a lost-city case, the reapply test widened to the five-object set and the full chain).

## Task Commits

| Task | Phase | Commit | Message |
|---|---|---|---|
| 1 | RED | `0c6d147` | test(08-09): add failing tests for the day-ahead expose migration |
| 1 | GREEN | `421d67d` | feat(08-09): expose the day-ahead views and alarm clause |
| 2 | RED | `fd56e4d` | test(08-09): add failing tests for the day-ahead privilege sweep |
| 2 | GREEN | `3f75e7f` | feat(08-09): privilege sweep covers the day-ahead objects |

## TDD Gate Compliance

RED then GREEN for both tasks; no refactor commit was needed.

- **Task 1 RED (`0c6d147`):** `day_ahead_expose_test.py` run with the migration absent: 20 failed, 3 passed. The 20 failures are assertion or missing-object failures for the planned behavior (no migration file, `relation "public.day_ahead_upcoming" does not exist`, anon refused on the table). The 3 passes are preserved-behavior guards (alarm range check and `missing=`/`stale=` detail, one-function and attribute check, run log and writer unchanged), which are correct to pass before the change. Semantic assessment: every target test executed and failed on the planned assertion, not on an import, fixture or syntax fault.
- **Task 2 RED (`fd56e4d`):** `expose_migration_test.py` run with the old SQL: 18 failed, 20 passed. Failures are the 29-name list mismatch (`..._two_objects_only` vs `..._published_objects_only`, 11 missing names) and the sabotage cases returning the wrong bad-check sets. The widened reapply test already passed because the whole chain in order is correct without a SQL change. Semantic assessment: valid RED on the planned assertions.
- The `gsd check tdd-red-evidence` classifier was not run: pytest's console output is not one of its supported report formats and the orchestrator did not enable `TDD_MODE`. The RED evidence above is from the real pytest runs.

## Verification

| Command | Result |
|---|---|
| Task 1 verify 1 (`day_ahead_expose_test`, `day_ahead_migration_test`, `soak_log_migration_test`) | 72 passed, 0 skipped (23 from the new file; at least 8 required) |
| Task 1 verify 2 (`expose_migration_test` with the three named tests deselected) | 20 passed, "3 deselected" |
| Task 2 verify (`expose_migration_test`, `day_ahead_expose_test`, `e2e_readonly_test`, `secret_scan_test`) | 152 passed, 1 skipped (the owner-local `secret_scan_test.py:316` check that needs keys exported in a shell, as in 08-08; not a local-Postgres test) |
| The three Task 1 break-window tests together | 3 passed after Task 2 |
| `verify_exposure.sql` check names on the migrated database | 29, all ok |
| Full suite (`DLR_TEST_PG_AUTOSTART=1 pytest`) | 2933 passed, 0 failed, 0 skipped (2895 at 38f438f plus 23 and 15 new) |
| `git diff` of the five applied migrations | clean (exit 0); `grep -c` of the assert_fresh header prints 1 |

## Decisions Made

- The late rule is written once, in `public.day_ahead_status`; `assert_fresh` reads that view for the late cities and reads the table only for the arming flag.
- The grid uses `date_bin(interval '6 hours', now(), timestamptz '2000-01-01 00:00:00+00')`, so the 00/06/12/18 UTC instants do not depend on the session time zone. Because `now() < T <= now() + 12 h` covers a 12 h span of a 6 h grid, a city has at most two due targets at any moment.
- The check set uses a `published` CTE rather than repeating the five names in three CTEs, so the published set has one place to change.

## Deviations from Plan

None - plan executed exactly as written.

Observations that are not deviations:

- **Break window in full-file order:** the plan says three tests in `expose_migration_test.py` fail between the Task 1 and Task 2 commits. Run as one file, only `test_expose_migration_reapplies_cleanly` is reported, because it fails first and its re-apply of the Phase 6 file on its own resets the module database to the Phase 6 state, which lets the two verify tests pass. Run alone, `test_verify_exposure_sql_reports_every_check_ok` and `test_verify_exposure_sql_sees_column_level_and_inherited_privileges` fail as planned. The Task 1 verify command deselects all three, as the plan says. After Task 2 all three pass in any order.
- **TDD commits:** the plan's done lines name one `feat` commit per task; the tasks are `tdd="true"`, so each also has a preceding `test` commit. `commits: 4` is measured from the ledger.
- **`verify_exposure.sql` before the apply:** until 08-11 applies the expose migration, the new checks (and the 10-of-10 grants count) read false against the live project. That is expected and is what the file is for; the file runs clean only after the apply.

## Known Stubs

None.

## Threat Flags

None. The new readable objects and the alarm change are exactly the planned T-08-26 to T-08-29 surfaces: both views are `security_invoker`, the grants are explicit revoke-then-SELECT, the function keeps one signature, and the day-ahead alarm clause is armed only by a row.

## Issues Encountered

None.

## Next Phase Readiness

The expose migration and the generalised sweep are committed and tested on local Postgres. Nothing is applied and nothing is pushed: local `main` is ahead of `origin/main` (1088392) by docs commits, the 08-09 commits, and this summary. 08-10 can write the consumer documentation and the REST check against `day_ahead_contract` constants, and 08-11 applies this migration and runs `verify_exposure.sql` live.

## Self-Check: PASSED

- Files found: `supabase/migrations/20261108120100_expose_day_ahead_forecast.sql`, `backend/tests/day_ahead_expose_test.py`, `supabase/ops/verify_exposure.sql`, `backend/tests/expose_migration_test.py`.
- Commits found as ancestors of HEAD: `0c6d147`, `421d67d`, `fd56e4d`, `3f75e7f`.
- Applied migrations (Phase 4, Phase 6, 20261108120000) unchanged; their sha256 pins pass.
