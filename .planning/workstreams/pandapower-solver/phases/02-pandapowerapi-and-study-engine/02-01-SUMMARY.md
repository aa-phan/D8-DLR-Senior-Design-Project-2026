---
phase: 02-pandapowerapi-and-study-engine
plan: 01
subsystem: study-engine
tags: [solver-seam, registry, import-boundary, psse_job, python37]

requires:
  - phase: pss-e-integration (v1.6)
    provides: psse_job.study with the solver-neutral four-city study and PsseApi
provides:
  - study.API_FACTORIES, study._psse_factory and study.register_solver (the solver registry)
  - a last keyword solver="psse" on _open_case, index_case, prepare_base, make_study and prepare_run
  - psse_study_solver_test.py (seam behaviour) and pandapower_import_gate_test.py (one-way import boundary)
affects: [02-03 pandapower_job.api registers its factory under "pandapower", 02-04 and later study runs on the second solver]

actuals:
  tokens: 3727
  tasks: 2
  commits: 2
plan_head_before: 9100fb109aa9be776ce3fca6cfbdb2a320b2c63c
plan_head_after: 62b290a8be52005b05288e6c5d43841276726770

tech-stack:
  added: []
  patterns:
    - "Solver chosen by one plain string, resolved through a module-level registry instead of an import"
    - "Boundary gate in three forms: text scan, AST import walk, fresh python -I subprocess"

key-files:
  created:
    - backend/tests/psse_study_solver_test.py
    - backend/tests/pandapower_import_gate_test.py
  modified:
    - backend/psse_job/study.py

key-decisions:
  - "D-02 deviation in form (owner to confirm, not blocking): the solver string is resolved through API_FACTORIES instead of a literal mapping to the second solver's module, because the existing gate test_imports_stay_inside_the_laptop_boundary flags any non-allow-listed import even inside a function. The caller still passes one plain string and the default is still psse."
  - "register_solver never replaces an existing name with a different factory (the PSS/E factory cannot be replaced); re-registering the same factory is a no-op."
  - "An unknown or unregistered solver fails at stage load_case before any adapter call, with a message that holds the solver word only."

requirements-completed: [ENG-01]

coverage:
  - id: D1
    description: "study entry points take a last keyword solver (default psse) and a registered factory runs the full four-city study unchanged"
    requirement: "ENG-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_study_solver_test.py#test_tracer_registered_solver_runs_the_whole_study"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_study_solver_test.py#test_solver_defaults_to_psse_on_every_entry_point"
        status: pass
    human_judgment: false
  - id: D2
    description: "unknown, unregistered, non-string solver and factory errors fail at load_case; registrations cannot be replaced; a mapping failure builds no adapter"
    requirement: "ENG-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_study_solver_test.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "psse_job never names or loads the second solver (text, AST and fresh-interpreter checks)"
    requirement: "ENG-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_import_gate_test.py"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-11-18
status: complete
---

# Phase 2 Plan 01: Solver Seam Summary

**A solver-by-name seam in psse_job.study (API_FACTORIES, register_solver and a last keyword solver="psse" on five entry points), with a three-form gate that keeps the laptop job free of the second solver.**

## Performance

- **Duration:** about 5 min
- **Started:** 2026-11-18T18:29:40Z
- **Completed:** 2026-11-18T18:34Z
- **Tasks:** 2
- **Files modified:** 3 (1 edited, 2 created)

## Accomplishments

- `study._open_case`, `index_case`, `prepare_base`, `make_study` and `prepare_run` each take `solver="psse"` as their last parameter; it flows prepare_run -> make_study -> index_case -> _open_case, where the factory is looked up and called as `factory(backend, case_path)` inside the existing `load_case` try block.
- A solver that is not a `str` fails with `StudyFailed("load_case", "solver must be given by name")`; a name missing from `API_FACTORIES` fails with `"solver <name> is not registered"`; both happen before any adapter call.
- `register_solver` refuses a different factory under an existing name (including `psse`), accepts a repeat of the same factory silently, and rejects an empty name or a non-callable.
- A tracer test shows a recording factory receives the backend and case path exactly once and the unchanged study code produces the same four-city `StudyResults` as the default path.
- `pandapower_import_gate_test.py` enforces D-01: no `psse_job/*.py` text names the second solver in any letter case, no import (functions and handlers included) names it, and a fresh `python -I` interpreter importing `psse_job.study` registers only `psse` and loads neither solver module.

## Task Commits

1. **Task 1 (tracer): seam and tracer test** - `6110997` (feat)
2. **Task 2: refusals, defaults and import boundary** - `62b290a` (test)

## Verification

- Eleven-file PSS/E regression set plus the two new files: **361 passed, 0 skipped, 0 failed** (baseline measured at HEAD before the edit: 349 passed; 12 new tests: 8 in `psse_study_solver_test.py`, 4 in `pandapower_import_gate_test.py`).
- `test_imports_stay_inside_the_laptop_boundary`, `test_syntax_parses_as_python37` and `test_importing_psse_job_loads_no_heavy_module` still pass.
- Frozen-file gate (PLAN=02-01) exits 0 after each commit; staged leak scan exited 0 before each commit; full leak scan exits 0.
- Commands ran as written with `.venv/Scripts/python.exe` (the plan's `PY=` fallback line selects it); nothing needed an equivalent substitute.

## Deviations from Plan

### Notes (no code deviation)

**1. TDD red phase not observed separately for Task 2**
- The behaviours in Task 2 (`<behavior>`) were already delivered by Task 1's implementation (the plan allows "the smallest change, if any is needed"), so the eight new seam tests and four gate tests passed on first run and no `study.py` change was needed in Task 2 beyond a docstring sentence on `prepare_run`. The gate's planted-violation test shows the checks can fail.

**2. Commit ledger collision (process, not product)**
- The per-plan ledger file `gsd-plan-head-before-02-01` already existed from the earlier pss-e-integration workstream's own plan 02-01 (Oct 28), so the "write only if absent" step kept a stale base and the first measurement read 441 commits. The ledger was corrected to this plan's true base (`9100fb1`, the parent of the first task commit) and re-measured: 2 commits, matching the two task commits. The stale file belonged to a completed plan and was overwritten. Future plans with the same phase-plan number in another workstream will hit the same collision.

**3. D-02 deviation in form** is recorded under Decisions above for owner confirmation (declared in the plan itself, not discovered during execution).

Otherwise: none - plan executed as written.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or trust-boundary file access; T-02-01 to T-02-03 are mitigated by the new tests, and T-02-SC is met (nothing installed; requirements files untouched).

## Self-Check: PASSED

- FOUND: backend/psse_job/study.py (API_FACTORIES, register_solver, _psse_factory present)
- FOUND: backend/tests/psse_study_solver_test.py
- FOUND: backend/tests/pandapower_import_gate_test.py
- FOUND commit 6110997 and 62b290a (ancestors of HEAD)
