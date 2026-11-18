---
phase: 02-pandapowerapi-and-study-engine
plan: 02
subsystem: study-engine
tags: [pandapower, adapter, state-machine, outcome-mapping, current-basis]

requires:
  - phase: 01 (pandapower-solver)
    provides: raw.parse_raw, convert.case_from_json, network.build_network, solve.run_load_flow and SolveSettings
  - phase: 02 plan 01
    provides: the solver registry the adapter will register into in plan 02-03
provides:
  - pandapower_job.api.PandapowerApi (load_case, branch_table, bus_table, read_rate, set_rate, set_status, solve, branch_loading, save_case, version), PandapowerBackend, PandapowerCallError and the states FRESH, SOLVED, FAILED, STALE
  - backend/tests/pandapower_study_fixture.py (OFFSET, RAISED_PT_MW, fixture_records, write_case, write_converted, fixture_backend, ISLANDING_OUTAGE)
  - backend/tests/pandapower_api_test.py (25 tests on the real solver)
affects: [02-03 scaling methods, registration and signature pin, 02-04 engine entry point, 02-05 study-level island and stale-result proof]

actuals:
  tokens: 9500
  tasks: 3
  commits: 3
plan_head_before: 5540b8634625a79ae1903028a97d36ae1ea74c82
plan_head_after: f3f7640901c0af3de9775f57ccff46c8c6841a46

tech-stack:
  added: []
  patterns:
    - "Adapter state machine: every mutation sets STALE, every solved read requires SOLVED, FRESH reads NaN voltages"
    - "Outcome mapping onto the existing psse_api.SolveResult, never pandapower's own converged flag"
    - "Snapshots are in-memory deep copies; a reload is the only way back from a mutation"

key-files:
  created:
    - backend/pandapower_job/api.py
    - backend/tests/pandapower_api_test.py
    - backend/tests/pandapower_study_fixture.py
  modified: []

key-decisions:
  - "Assumption Q2 (owner, not blocking, reversible): the adapter accepts the RAW file and the project's converted network JSON, chosen by the .json suffix; plan 01-11 decides which one the hourly job uses."
  - "A failed or stale state is never restored from a snapshot: a snapshot saved solved reloads SOLVED, anything else reloads FRESH."
  - "ENG-02 to ENG-04 are NOT marked complete in REQUIREMENTS.md: this plan delivers the adapter half (the plan's own success criteria say so); the study-level halves land in 02-04 and 02-05."

requirements-completed: []

coverage:
  - id: D1
    description: "a case file loads once into a master; every load_case is a fresh deep copy; the master is unchanged after status, rating and solve mutations"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_master_unchanged_after_mutations"
        status: pass
    human_judgment: false
  - id: D2
    description: "a rating is a per-circuit current limit (max_i_ka * 1000 equals circuit_amps), read back as MVA for every rate set; loading is on the current basis; the mva basis and unknown names are refused"
    requirement: "ENG-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_rating_is_a_current_limit_per_circuit"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_tracer_case_file_to_current_basis_loading"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_refuse_mva_basis_and_unknown_names"
        status: pass
    human_judgment: false
  - id: D3
    description: "an island is converged False with ierr 3 while net.converged is True; iteration limit and collapse are non-converged results"
    requirement: "ENG-03"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_island_is_not_converged_while_pandapower_says_converged"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_nonconv_iteration_limit"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_collapse_voltage"
        status: pass
    human_judgment: false
  - id: D4
    description: "no branch_loading or bus_table result after a failed solve, a status or rating change, or before any solve; order and a prior failed solve change no result"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_state_stale_after_status_or_rating_change"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_state_failed_after_non_converged_solve"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_order_and_a_failed_solve_do_not_change_results"
        status: pass
    human_judgment: false
  - id: D5
    description: "every refusal is a ValueError, CaseProtected or a PsseCallError subclass whose text holds no bus number, branch key or path; derating and parallel count are pinned to 1"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_messages_are_figure_free"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_test.py#test_line_derating_and_parallel_are_pinned"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-11-18
status: complete
---

# Phase 2 Plan 02: PandapowerApi Core Summary

**A pandapower adapter with PsseApi's method names that turns each pandapower trap (islands reported as converged, stale result tables after a change, a 0.0 loading on a tripped line, an MVA figure under a current label) into a tested refusal or a non-converged result, proven on the real solver.**

## Performance

- **Duration:** about 25 min
- **Tasks:** 3 (one tracer, two TDD)
- **Files:** 3 created (one adapter, one test module, one shared test helper)
- **Runtime of `pandapower_api_test.py`:** 25 tests in about 9.4 s (one adapter per backend setting is shared across the module, so the master is built once)

## Accomplishments

- `PandapowerApi(backend, protected_path=None)` loads a RAW file or the converted JSON (by suffix) through `raw.parse_raw` or `convert.case_from_json` and `network.build_network`, bounded by 5 MiB and 1 MiB, once per path; every `load_case` is a deep copy and the master is never handed out. Nothing in the module reads a file any other way (grep gate: 0 matches).
- `set_rate` writes `max_i_ka = MVA / (sqrt(3) x from-bus kV)`; `read_rate` returns it back as MVA for every rate set; `branch_loading` returns pandapower's own `loading_percent` (the current basis) and refuses the `mva` basis, a derated line (`df` not 1) and a parallel count other than 1.
- The state machine refuses `bus_table` (after FRESH) and `branch_loading` unless the last solve converged and nothing changed since. FRESH `bus_table` returns NaN voltages so `study._read_solved_base` would fail closed on a skipped solve.
- `solve` maps `run_load_flow` onto `classify_solve`: an island (pandapower says converged, leaves NaN voltages) is converged False with ierr 3 and the PSS/E island meaning; non-convergence and collapse are results, never exceptions.
- `save_case` keeps an in-memory deep copy (no file) and refuses the protected path; `load_case` of a saved path restores it (SOLVED only if saved solved).

## Task Commits

1. **Task 1 (tracer): case file to current-basis loading** - `b294efa` (feat)
2. **Task 2: no read after a failed or stale solve; snapshots, islands, order independence** - `bdba103` (feat)
3. **Task 3: refusals, per-circuit current limit, figure-free messages, converted JSON** - `f3f7640` (feat)

## Verification

- `pandapower_api_test.py`: **25 passed, 0 skipped, 0 failed**.
- With the three Phase 1 pandapower files (network, raw, parity): **149 passed, 0 skipped, 0 failed**, run as the Task 3 command specifies.
- Import gate, solver seam and PSS/E contract files (`pandapower_import_gate_test.py`, `psse_study_solver_test.py`, `psse_contract_test.py`): **22 passed**.
- Frozen-file gate (PLAN=02-02) exits 0 after each commit; the staged leak scan exited 0 before each commit; the full leak scan exits 0.
- Commands ran as written with `.venv/Scripts/python.exe`; pandapower 3.5.6 import check passed.
- Warnings seen (cosmetic): "numba cannot be imported" at import, and pandapower's `tap_dependency_table is missing in net` DeprecationWarning in the Phase 1 network tests.
- Order test: forward, reverse and islanding-outage-first runs over five line outages plus the islanding outage give equal `(converged, ierr, BranchFlow list, BusRow dict)` with plain `==` (a probe showed no NaN occurs in converged outage reads, so no NaN normalisation is needed).

## Deviations from Plan

### Notes (no code deviation)

**1. Test-first order inside the shared fixture**
- `ISLANDING_OUTAGE` was written into `pandapower_study_fixture.py` in Task 1's commit (the plan places it in Task 2). It is a constant only; Task 2's tests were still written and run red (11 failed, 4 passed) before the adapter reads and writes were added, and Task 3's two df/parallel tests were red before the check was added.

**2. Commit ledger collision (process, same as plan 02-01)**
- `.git/gsd-plan-head-before-02-02` held a stale base from the old pss-e-integration workstream's own plan 02-02. It was overwritten with this plan's true base (`5540b86`, the parent of the first task commit) before the first commit; the measured count is 3 commits, matching the three task commits.

**3. ENG-02 to ENG-04 left Pending in REQUIREMENTS.md**
- The plan frontmatter lists ENG-01 to ENG-04, but its own success criteria name only the "API half" of ENG-02 to ENG-04, and the engine and study-level halves belong to plans 02-04 and 02-05. `requirements.mark-complete` was not run for them. ENG-01 is already complete from plan 02-01.

Otherwise: none - plan executed as written.

## Known Stubs

None.

## Threat Flags

None. The only new file read is the case file, bounded and parsed by the Phase 1 fail-closed parsers (T-02-04); T-02-05 to T-02-08 are mitigated by the tests named under coverage; T-02-SC met (nothing installed, requirements files untouched).

## Self-Check: PASSED

- FOUND: backend/pandapower_job/api.py (class PandapowerApi, class PandapowerCallError, solve.run_load_flow call)
- FOUND: backend/tests/pandapower_api_test.py
- FOUND: backend/tests/pandapower_study_fixture.py
- FOUND commits b294efa, bdba103 and f3f7640 (ancestors of HEAD)
