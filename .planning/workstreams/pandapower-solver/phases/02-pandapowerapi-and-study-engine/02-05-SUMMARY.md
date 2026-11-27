---
phase: 02-pandapowerapi-and-study-engine
plan: 05
subsystem: study-engine
tags: [pandapower, study-level-proof, island, non-convergence, fresh-copy, call-sequence, determinism]

requires:
  - phase: 02 plan 01
    provides: study.register_solver, study.API_FACTORIES and the solver= keyword on prepare_base and make_study
  - phase: 02 plans 02 and 03
    provides: PandapowerApi, the registered "pandapower" factory, the 14 study-facing methods and the state machine
provides:
  - backend/tests/pandapower_study_behaviour_test.py - ENG-03 and ENG-04 proven through the unchanged contingency.screen, margin and make_study loops on the real solver
  - _RecordingApi, a PandapowerApi subclass that logs every public call (and each solve's converged flag and network object), usable by later study-level tests
affects: [02-06 database tier of ENG-06, 02-07 recorded settings wiring, Phase 3 solver column, Phase 5 hourly workflow]

actuals:
  tokens: 3412
  tasks: 2
  commits: 2
plan_head_before: b900bfb89956be0149f8c47d36289cf9c1bcedc6
plan_head_after: 6aea55116f4b05c2bcebea43bd2f5e8a75774a08

tech-stack:
  added: []
  patterns:
    - "A recording subclass of the adapter registered through monkeypatch.setitem(study.API_FACTORIES, ...) shows the study's call sequence without touching psse_job"
    - "Network objects are kept by reference and compared by identity, so a reused id() cannot hide a shared copy"
    - "One module-scoped full four-city study feeds four log-reading tests; the equality test runs a second one"

key-files:
  created:
    - backend/tests/pandapower_study_behaviour_test.py
  modified: []

key-decisions:
  - "No production change: every new assertion held on the first run, so the adapter and the study needed no fix and the frozen-file gate stays clean."
  - "The 'at least one other outage screened' check of the tracer is asserted as more than one selected outage with n_contingencies equal to the outage count, because a clean outage leaves no row to count."
  - "ENG-03 and ENG-04 marked complete: the adapter half was proven in 02-02 and the scaling half in 02-03; this plan proves the study half the plan's success criteria name."

requirements-completed: [ENG-03, ENG-04]

coverage:
  - id: D1
    description: "an outage that islands part of the grid becomes exactly one non_convergence row (ierr 3, solved None, collapsed False) through the unchanged contingency.screen, while pandapower's own converged flag is True for the same solve"
    requirement: "ENG-03"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_study_behaviour_test.py#test_tracer_island_is_one_non_convergence_row"
        status: pass
    human_judgment: false
  - id: D2
    description: "reversing the outage order, or adding a failing outage, changes no other screened row"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_study_behaviour_test.py#test_order_does_not_change_the_screen"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_study_behaviour_test.py#test_a_failed_outage_does_not_change_the_others"
        status: pass
    human_judgment: false
  - id: D3
    description: "in a full four-city study no bus or branch reading follows a non-converged solve before the next load_case, and every solve runs on a network object that no earlier solve used and that is not the master"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_study_behaviour_test.py#test_recorded_calls_never_read_after_a_failed_solve"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_study_behaviour_test.py#test_every_solve_runs_on_a_freshly_loaded_copy"
        status: pass
    human_judgment: false
  - id: D4
    description: "the case file is loaded exactly five times (the index plus one fresh load per city), the islanding outage's solve is non-converged in all four cities, the master network equals a fresh build after the study, and two runs give equal StudyResults"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_study_behaviour_test.py#test_each_city_loads_the_case_afresh"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_study_behaviour_test.py#test_master_unchanged_after_a_full_study"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_study_behaviour_test.py#test_two_runs_give_equal_results"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-11-18
status: complete
---

# Phase 2 Plan 05: Study-Level Proof of Island Handling and Fresh Copies Summary

**The unchanged `psse_job` study loops, run on the real pandapower adapter, turn an islanding outage into one `non_convergence` row, give the same rows in any outage order, never read after a failed solve, solve a fresh copy every time, leave the master untouched and repeat exactly.**

## Performance

- **Duration:** about 20 min
- **Tasks:** 2 (one tracer, one TDD task whose tests all held on the first run)
- **Files:** 1 created (the test module), none modified
- **Runtime of `pandapower_study_behaviour_test.py`:** 9 tests in 41.7 s (last run, with `--durations`); the shared four-city study takes 14.7 s and the second one in the equality test 14.6 s. Under the 120 s limit.

## Accomplishments

- Tracer: `study.prepare_base(..., solver="pandapower")` then `contingency.screen(base, id_prefix="ALL:")` gives exactly one row for the islanding outage, kind `non_convergence`, ierr 3, solved None, collapsed False, meaning starting "fnsl ierr 3: buses in island without swing bus". A separate adapter run shows `api._net.converged is True` for the same outage, so the row comes from the adapter's explicit rule and not from pandapower's flag (T-02-18).
- Order and failure independence: the screen with `select_outages` reversed returns the same rows as the default order (compared as lists sorted by a JSON key); adding the islanding outage through `contingency.extra` adds one outage and leaves every other outage's rows equal to the screen without it (T-02-19).
- `_RecordingApi` wraps all 14 public methods (a test checks that none was missed) and logs name, first argument and an extra (converged for `solve`, in_service for `set_status`).
- In one full four-city study: no `bus_table` or `branch_loading` call follows a non-converged solve before the next `load_case` (the log holds non-converged solves, so the check is not vacuous, and more reads than failures); every solve follows a `load_case`; the solved network objects are all distinct and none is the master; the case path is loaded exactly 5 times and every other load is a city's `.sav` copy; the islanding outage's solve is non-converged in all four cities.
- After the study the adapter's single master has equal bus, line, trafo, load, gen, ext_grid and shunt tables to a fresh `network.build_network(raw.parse_raw(...))` of the case bytes, and a second study with the plain registered factory returns an equal `StudyResults`.

## Task Commits

1. **Task 1 (tracer): an islanding outage is one non_convergence row through the unchanged screen** - `8cfe867` (test)
2. **Task 2: order, a failed solve and stale results change no answer; every solve runs on a fresh copy** - `6aea551` (test)

## Verification

- Task 1 command (`-k tracer`): **1 passed**, nothing skipped.
- Whole module: **9 passed, 0 skipped** (tracer 1, wrapper-coverage check 1, Task 2's seven).
- Plan verification set (`pandapower_study_behaviour_test.py`, `pandapower_api_test.py`, `pandapower_api_contract_test.py`): **50 passed, 0 skipped** in 52.6 s.
- Frozen-file gate (PLAN=02-05) prints PASS after both commits; the staged leak scan exited 0 before each commit; neither commit deletes a file.
- Commits measured from the ledger: `b900bfb..HEAD` is 2, matching the two task commits.
- Commands ran with `.venv/Scripts/python.exe` in place of `.venv/bin/python`; the pandapower 3.5.6 import check passed.
- No mutation checks were run. Non-vacuity rests on the counters inside the tests (a non-converged solve exists, reads outnumber failures, the island solve is found in each city, the failed-outage test checks the island row exists and the without-island screen has rows).

## Deviations from Plan

### Auto-fixed Issues

None. No defect appeared in `api.py` or the study code; no production file was changed.

### Notes (no code deviation)

**1. Commit ledger collision (process, as in plans 02-01 to 02-04)**
- `.git/gsd-plan-head-before-02-05` held a stale base (`e4331b0`) from the old pss-e-integration workstream's own plan 02-05. It was overwritten with this plan's true base (`b900bfb`) before the first commit.

**2. One extra test**
- `test_recording_api_wraps_every_public_method` was added beyond the seven the plan names. It fails if the adapter gains a public method that `_RecordingApi` does not log, so the call-sequence tests cannot silently miss a call.

**3. Log entries carry a third element**
- The plan says each log entry is `(name, first argument)` plus `converged` for a solve. Entries are `(name, first argument, extra)`, where `extra` is `converged` for a solve and `in_service` for `set_status`, so the island solve can be identified in the log.

**4. Heredoc edit**
- A first attempt to append the Task 2 code through a shell heredoc failed to parse and wrote nothing; the code was added with the Edit tool instead. No effect on the result.

**5. ENG-03 and ENG-04 marked complete**
- Both requirements were left Pending by plans 02-02 and 02-03 until this study-level proof. The plan's success criteria name exactly this proof, so both are marked complete.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-02-18 is mitigated by the tracer (row from the explicit rule while pandapower says converged); T-02-19 by the reversed-order, added-failure, call-sequence, master-equality and two-run tests; T-02-SC met (nothing installed, requirements files untouched).

## Self-Check: PASSED

- FOUND: backend/tests/pandapower_study_behaviour_test.py (343 lines, 9 tests)
- FOUND commits 8cfe867 and 6aea551 (ancestors of HEAD)
