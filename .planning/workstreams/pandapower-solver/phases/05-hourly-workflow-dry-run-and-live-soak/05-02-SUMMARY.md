---
phase: 05-hourly-workflow-dry-run-and-live-soak
plan: 02
subsystem: ops
tags: [soak, retention, gap-check, oracle-test, read-only-sql]
status: complete

requires:
  - phase: 03-solver-tag-migration-and-per-solver-gaps
    provides: gaps.compute_gaps, gaps.fetch_runs, gaps.fetch_current_slot, the per-solver gap rules the soak count is checked against
provides:
  - "backend/pandapower_job/soak.py: SOAK_SLOTS, SoakCount, trailing_slots, soak_passed (pure, standard library only)"
  - "backend/tests/pandapower_soak_test.py: hand cases, a 300-seed independent oracle, a cross-check with gaps.compute_gaps, an import check"
  - "supabase/ops/psse_result_size.sql: the owner's read-only size query (one SELECT, six rows)"
  - "05-RETENTION-DECISION.md: keep every row, about 5,100 rows a day, size-based review trigger"
affects: [05-04, 05-07, 05-08, soak-command, go-live-decision]

actuals:
  tokens: 5500
  tasks: 2
  commits: 2
plan_head_before: c7e10248f96f09f3dcc7470a50f4bb21d1305341
plan_head_after: 062b409ed7dc36943cd5bc73087de2cf1aa5a692

tech-stack:
  added: []
  patterns:
    - "soak state is derived from stored rows on every call, nothing persisted"
    - "oracle written differently from the module (rescan the whole row list per hour) plus a cross-check against the existing gap function"

key-files:
  created:
    - backend/pandapower_job/soak.py
    - backend/tests/pandapower_soak_test.py
    - supabase/ops/psse_result_size.sql
    - .planning/workstreams/pandapower-solver/phases/05-hourly-workflow-dry-run-and-live-soak/05-RETENTION-DECISION.md
  modified: []

key-decisions:
  - "The soak walk starts at the hour before the database's current hour, the same rule as compute_gaps, so the 24th slot first shows on the 25th run"
  - "Any outcome other than failed counts toward an hour; fallback-only hours are counted separately in fallback_slots"
  - "Retention: keep every row, no pruning; the 100,000-row trigger is replaced by a size reading with a limit the owner names (a reading equal to the limit counts as reached)"

requirements-completed: [OPS-04, OPS-05]

coverage:
  - id: D1
    description: "24 consecutive complete UTC hours pass; a missed hour restarts the count; failed-only hours, PSS/E rows and the current hour never count"
    requirement: OPS-05
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_soak_test.py#test_tracer_exactly_24_consecutive_slots_pass"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_soak_test.py#test_hand_cases"
        status: pass
    human_judgment: false
  - id: D2
    description: "the count equals an independent oracle on 300 seeded histories and agrees with gaps.compute_gaps (counted hours are not gaps, the hour before them is)"
    requirement: OPS-05
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_soak_test.py#test_matches_the_oracle_on_300_histories"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_soak_test.py#test_agrees_with_the_per_solver_gap_check"
        status: pass
    human_judgment: false
  - id: D3
    description: "fallback-only hours inside the counted run are reported; naive and other-zone datetimes are normalised like the gap check; soak.py imports only the standard library"
    requirement: OPS-05
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_soak_test.py#test_fallback_slots_are_counted"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_soak_test.py#test_timezone_normalisation_matches_the_gap_check"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_soak_test.py#test_soak_module_imports_only_the_standard_library"
        status: pass
    human_judgment: false
  - id: D4
    description: "a written retention decision with the corrected rate and a size-based review trigger exists before any live write; the size query runs on a throwaway local database and returns six rows"
    requirement: OPS-04
    verification:
      - kind: command
        ref: "grep of the five phrases in 05-RETENTION-DECISION.md and the structural check of psse_result_size.sql (both exit 0); one-off run of the query on a throwaway local Postgres returned the six named rows"
        status: pass
    human_judgment: true
---

# Phase 5 Plan 02: Soak count and retention decision Summary

**A pure 24-slot soak count that agrees with an independent oracle on 300 seeded histories and with the per-solver gap check, plus the retention decision (keep every row, about 5,100 rows a day) with the owner's read-only size query.**

## Performance

- **Duration:** about 10 minutes
- **Completed:** 2026-11-26
- **Tasks:** 2 of 2
- **Files created:** 4

## Accomplishments

- `trailing_slots(runs, current_slot, solver)` returns `SoakCount(slots, fallback_slots)`. It walks back from the hour before the current hour and stops at the first hour with no non-failed run of that solver. Another solver's rows, rows in the current or a later hour, and rows with a non-plain label (`Pandapower`, None, over-long) never fill a pandapower hour.
- The test file has 7 tests: the tracer (24 passes, 23 does not), hand cases, fallback counting, timezone normalisation compared with `gaps._utc`, the 300-seed oracle with non-vacuity assertions (at least 30 histories at 24 or more, at least 50 between 1 and 23, at least 20 with a fallback hour), the cross-check with `gaps.compute_gaps` (at least 100 histories where the hour before the run is a gap the solver's own walk reaches), and an AST check that `soak.py` imports only `collections`, `datetime` and `re`.
- `05-RETENTION-DECISION.md` records the arithmetic: 19 runs hold 76 + 76 + 3,895 rows, about 205 contingency rows a run, about 214 rows a run, about 5,100 rows a day, about 36,000 a week, about 154,000 in 30 days, worst case about 120,000 a day. It replaces the 100,000-row trigger (reached in about 20 days) with a size reading and carries the two lines (review limit, size before the first live write) that plan 05-08 Task 1 fills.
- `psse_result_size.sql` is one read-only SELECT. I ran it once on a throwaway local database with the schema applied (scratchpad script, not committed): it returned the six rows with the four named columns, zero counts and a database size.

## Task Commits

1. **Task 1: trailing 24-slot soak count and its tests** - `b29d851` (feat)
2. **Task 2: retention decision and size query** - `062b409` (docs)

## Deviations from Plan

None - plan executed exactly as written. The tests passed on the first run, so no RED commit was made separately; the tracer is one commit with the module and its tests.

## Known Stubs

None.

## Threat Flags

None. The size query reads counts and sizes only.

## Issues Encountered

None. `git` printed LF-to-CRLF warnings on the new files; no test pins file bytes.

## Next Phase Readiness

- Plan 05-04 can import `pandapower_job.soak` into the hourly `soak` command and feed it `gaps.fetch_runs` and `gaps.fetch_current_slot`.
- Plan 05-07 Task 3 must get the review limit and the size reading from the owner, and plan 05-08 Task 1 writes both into `05-RETENTION-DECISION.md` before the variable is set.

## Self-Check: PASSED

- FOUND: backend/pandapower_job/soak.py
- FOUND: backend/tests/pandapower_soak_test.py
- FOUND: supabase/ops/psse_result_size.sql
- FOUND: 05-RETENTION-DECISION.md
- FOUND commits: b29d851, 062b409
- 21 passed, 1 skipped (the gap test's database case) over the soak and gap tests; file-scope gate exit 0; leak scan exit 0; no change under backend/psse_job
