---
phase: 02-pandapowerapi-and-study-engine
plan: 04
subsystem: study-engine
tags: [pandapower, engine, preflight, solve-settings, placeholder, fail-closed-loader, run-record]

requires:
  - phase: 01 (pandapower-solver)
    provides: solve.SolveSettings, scaling.ScalingDetails and the check command's report.json and scaling_details.json shapes
  - phase: 02 plan 01
    provides: study.register_solver, study.API_FACTORIES and make_study(..., solver=)
  - phase: 02 plans 02 and 03
    provides: PandapowerApi, PandapowerBackend, SOLVER_NAME and the registered "pandapower" factory
provides:
  - backend/pandapower_job/engine.py - prepare_run, preflight, PLACEHOLDER_BACKEND, is_placeholder, settings_record, backend_from_records, load_recorded_backend, RecordsRefused
  - the dispatch-row details key solve_settings on every pandapower run (solver, solver version, placeholder flag, settings, sources, deviations, the three scaling details)
  - the in-memory four-city tier of ENG-06 (case39 fixture, placeholder mapping, no live data, sockets blocked)
  - the owner-local test of the recorded PSE-02 settings (skips here, fails under DLR_PANDAPOWER_REQUIRE_RECORDS=1)
affects: [02-06 prepare_run on pandapower (database tier of ENG-06), 02-07 recorded settings wiring (ENG-05), Phase 3 solver column, Phase 5 hourly workflow]

actuals:
  tokens: 10088
  tasks: 3
  commits: 3
plan_head_before: 476009ed5ac571596acc8d5f3593da6777b2c359
plan_head_after: 351b8fd008bbac8c8ab7be49c6506791b363680c

tech-stack:
  added: []
  patterns:
    - "Settings reach the adapter only through the injected backend; the engine owns the named placeholders and the adapter never imports it (checked by an AST test of api.py)"
    - "Fail-closed record loader: exact keys, finite typed values, strict JSON (no NaN, no duplicate key), size cap, marker key, reason-only exception"
    - "Preflight refusals become failing_study('mapping', 'pandapower: <reason>') before any case load or adapter build"

key-files:
  created:
    - backend/pandapower_job/engine.py
    - backend/tests/pandapower_engine_test.py
    - backend/tests/pandapower_engine_recorded_test.py
  modified: []

key-decisions:
  - "Q1 (owner to confirm at plan 02-07, reversible): a backend whose enforce_q_lims is None is refused at stage mapping; the engine never picks a value (D-14)."
  - "Q4 (owner to confirm, reversible): voltage.source case is refused because the builder does not carry PSS/E's emergency voltage limits; extending the builder would change Phase 1 code."
  - "Q6 (owner to confirm, reversible): 'stored with each run' is a solve_settings record in every dispatch row's details (free JSON, no schema change); a run-level column would be Phase 3's migration."
  - "A3 (owner to confirm): the real private mapping uses the defaults (thermal.basis current, voltage.source config, solve.options null); if not, the preflight refuses it on first use, loudly."
  - "Hand-off to Phase 5: refuse a live write when engine.is_placeholder(backend) is True, and add the public-log filter (RESEARCH Pitfall 10)."
  - "psse_version is None for a pandapower run; the pandapower version lives in solve_settings.solver_version until Phase 3 adds the solver and solver_version columns (RESEARCH Pitfall 9)."
  - "A recorded scaling document whose evidence says placeholder true is refused as placeholder_source, and a source is read as a placeholder after trimming and lower-casing, so a placeholder cannot pass as recorded by spelling."

requirements-completed: [ENG-02]

coverage:
  - id: D1
    description: "engine.prepare_run runs all four cities on pandapower through the unchanged study with no network and no file left behind; the existing validator accepts the results; psse_version is None; every dispatch row carries the solve_settings record"
    requirement: "ENG-06"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_tracer_four_cities_in_memory"
        status: pass
    human_judgment: false
  - id: D2
    description: "an MVA thermal basis, fnsl solve options, case voltage limits or an undecided reactive-limit setting fail at stage mapping with a figure-free one-line reason, build no adapter and keep the mapping hash"
    requirement: "ENG-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_preflight_refuses_mva_basis"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_preflight_refuses_fnsl_options"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_preflight_refuses_case_voltage_source"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_preflight_refuses_undecided_reactive_limits"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_preflight_refusal_builds_no_adapter_and_keeps_the_hash"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_preflight_messages_are_figure_free"
        status: pass
    human_judgment: false
  - id: D3
    description: "recorded PSE-02 settings load through fail-closed validation; placeholders stay detectable and cannot pass as recorded; the adapter solves with the settings object of the backend it was given"
    requirement: "ENG-05"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_records_refusals"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_load_recorded_backend_refusals"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_adapter_solves_with_the_backend_settings"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_engine_test.py#test_placeholder_is_detectable"
        status: pass
    human_judgment: false
  - id: D4
    description: "owner-local test of the real recorded settings: skips without records, fails under DLR_PANDAPOWER_REQUIRE_RECORDS=1, runs four cities on the recorded backend when records exist"
    requirement: "ENG-05"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_engine_recorded_test.py#test_owner_local_recorded_settings_run_four_cities"
        status: unknown
    human_judgment: false

duration: 35min
completed: 2026-11-18
status: complete
---

# Phase 2 Plan 04: Engine Entry Point, Preflight and Settings Provenance Summary

**`engine.prepare_run` runs the unchanged four-city study on pandapower, refuses at stage mapping anything pandapower cannot reproduce, stamps every dispatch row with the solver and settings that produced it (placeholders labelled until PSE-02 is recorded), and loads recorded PSE-02 values through a fail-closed loader.**

## Performance

- **Duration:** about 35 min
- **Tasks:** 3 (one tracer, two TDD)
- **Files:** 3 created (engine.py, two test modules), none modified
- **Runtime of `pandapower_engine_test.py`:** 21 tests in about 26 s (one shared four-city run of about 20 s)

## Accomplishments

- `prepare_run(backend, case_path, mapping_path, allow_placeholder, clock)` mirrors `study.prepare_run` (case label and hash, one `load_mapping` call, the same MappingError study), then runs the study through `study.make_study(..., solver="pandapower")`. The returned study adds `solve_settings` to a copy of every dispatch row's `details` and sets `psse_version` to None. The mapping's collapse voltage replaces the backend's, so the study's own guards and the solve use one limit.
- `preflight` (stage `mapping`, before any case load or adapter build): thermal basis other than current, fnsl solve options, `voltage.source` other than config, and an undecided reactive-limit setting each give a one-line reason prefixed `pandapower: `. The mapping hash is kept; no message holds a figure or a bus number.
- Named placeholders (`PLACEHOLDER_SOLVE`, `PLACEHOLDER_DETAILS`, `PLACEHOLDER_BACKEND`) with `is_placeholder`; every stored row says `placeholder: true` until recorded values replace them.
- `backend_from_records` and `load_recorded_backend` read the Phase 1 check output (`report.json` key `settings`, `scaling_details.json`, each with the `cli.REPORT_MARKER` key) and refuse with a reason-only `RecordsRefused` (11 reasons). The adapter test shows `solve.run_load_flow` receives the backend's own `SolveSettings` object.
- The in-memory tier of ENG-06 runs the case39 fixture with the placeholder mapping, four cities, sockets blocked and `tempfile.tempdir` redirected; `run_record.validate_results` accepts it, `build_run_record` and `result_rows` give 4, 4 and `len(contingencies)` rows, and the scratch folder is empty afterwards.

## Task Commits

1. **Task 1 (tracer): four cities in memory through engine.prepare_run, settings stored on every dispatch row** - `6ff32d5` (feat)
2. **Task 2: refuse settings pandapower cannot reproduce at stage mapping** - `ab0bde1` (feat)
3. **Task 3: recorded PSE-02 settings through a fail-closed loader** - `351b8fd` (feat)

## Verification

- `pandapower_engine_test.py`: **21 passed, 0 skipped** (tracer 1, Task 2 12 including four parametrized refusals, Task 3 8).
- Plan verification set (engine, recorded, contract, api tests): **62 passed, 2 skipped**; the two skips are the owner-local tests with the reason "owner-local check: no recorded PSE-02 check output on this machine".
- `DLR_PANDAPOWER_REQUIRE_RECORDS=1` with no check dir: both owner-local tests **fail** (2 failed), as required.
- Owner-local path exercised against synthetic check folders written outside the repo: a decided record runs four cities and passes (2 passed); a record with `enforce_q_lims` null fails with the counts-only "recorded settings are undecided" text.
- PSS/E regression set (the eleven files of plan 02-01 plus `psse_study_solver_test.py` and `pandapower_import_gate_test.py`): **361 passed**, equal to plan 02-01's measured count.
- Acceptance greps: `def prepare_run(` 1, `PLACEHOLDER_BACKEND = ` 1, `failing_study("mapping", "pandapower: "` 1, `def backend_from_records(` 1, `def load_recorded_backend(` 1; the AST check that `api.py` never imports `engine` exits 0.
- Frozen-file gate (PLAN=02-04) exits 0 after each commit; the staged leak scan exited 0 before each commit; the full leak scan exits 0 (36 binary or oversized files not scanned, as before).
- Commits measured from the ledger: `476009e..HEAD` is 3, matching the three task commits.
- Commands ran with `.venv/Scripts/python.exe`; the pandapower 3.5.6 import check passed. Cosmetic warning seen: "numba cannot be imported".
- No mutation checks were run for this plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Placeholder evidence and spelling in recorded settings**
- **Found during:** Task 3
- **Issue:** `is_placeholder` also treats a scaling evidence dict with `placeholder` true as a placeholder, so a recorded scaling document carrying that evidence would load and then be reported as a placeholder (or, worse, a placeholder source spelled with a capital or leading space would slip past a plain `startswith`).
- **Fix:** `backend_from_records` refuses such evidence as `placeholder_source`; `is_placeholder` and the loader share one `_says_placeholder` test that trims and lower-cases. Covered by `test_records_refusals` and `test_placeholder_is_detectable`.
- **Files modified:** backend/pandapower_job/engine.py, backend/tests/pandapower_engine_test.py
- **Commit:** 351b8fd

### Notes (no code deviation)

**2. Test-first order**
- Task 2 followed red then green (10 of 12 tests failed before `preflight` existed). In Task 3 the loader was written before its tests, then all eight passed except one test-side collision (a test directory named like a refusal reason, fixed by renaming the directory). The tests were run against both the decided and the undecided synthetic check folders to confirm the owner-local path.

**3. `pandapower_job.api` import**
- The plan asks for `import pandapower_job.api` at the top. `from pandapower_job import api` already imports it and registers the factory, so the redundant statement was left out and a comment says why.

**4. Commit ledger collision (process, as in plans 02-01 to 02-03)**
- `.git/gsd-plan-head-before-02-04` held a stale base (`7ff718f`) from the old pss-e-integration workstream's own plan 02-04. It was overwritten with this plan's true base (`476009e`) before the first commit.

**5. ENG-02 marked complete**
- The plan's `requirements` list ENG-02, ENG-05 and ENG-06, but its success criteria close only the refusal half of ENG-02 (the rating and read-back half came with plan 02-02, whose decision kept ENG-02 Pending until this plan). ENG-02 is marked complete. ENG-05 stays Pending (final wiring is plan 02-07) and ENG-06 stays Pending (database tier is plan 02-06).

Otherwise: none - plan executed as written.

## Known Stubs

None in the code. `PLACEHOLDER_SOLVE` and `PLACEHOLDER_DETAILS` are intentional, named, labelled placeholders (D-06) that every stored row flags; plan 02-07 replaces them with recorded PSE-02 values. They are not added to `.planning/WINDOWS.md`, which belongs to another workstream's ship gate.

## Threat Flags

None beyond the plan's register. T-02-12 is mitigated by the preflight tests with a counting factory; T-02-13 by the tracer's `psse_version is None` and `solver_version` assertions; T-02-14 by `is_placeholder`, the stored flag and the `placeholder_source` refusal; T-02-15 by the loader refusal tests; T-02-16 by the figure-free and path-free message assertions; T-02-17 by the blocked sockets and the `psse_fakes` ratings; T-02-SC met (nothing installed, requirements files untouched).

## Self-Check: PASSED

- FOUND: backend/pandapower_job/engine.py (`def prepare_run`, `def preflight`, `PLACEHOLDER_BACKEND`, `def backend_from_records`, `def load_recorded_backend`, `class RecordsRefused`)
- FOUND: backend/tests/pandapower_engine_test.py (21 tests), backend/tests/pandapower_engine_recorded_test.py (2 tests)
- FOUND commits 6ff32d5, ab0bde1 and 351b8fd (ancestors of HEAD)
