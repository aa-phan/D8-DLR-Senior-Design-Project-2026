---
phase: 02-pandapowerapi-and-study-engine
plan: 03
subsystem: study-engine
tags: [pandapower, adapter, scaling, solver-registry, contract-test, signature-pin]

requires:
  - phase: 01 (pandapower-solver)
    provides: scaling.scale_city, ScalingDetails and the refusal classes
  - phase: 02 plan 01
    provides: study.register_solver and study.API_FACTORIES
  - phase: 02 plan 02
    provides: PandapowerApi core, PandapowerBackend, PandapowerCallError and the state machine
provides:
  - scaling.case_totals(net, details), the one totals definition shared by scale_city and the adapter
  - PandapowerApi.read_totals, scale_case, define_subsystem, scale_load (the 14-method surface is complete)
  - api.SOLVER_NAME, api.factory and the import-time registration under "pandapower"
  - backend/tests/pandapower_api_contract_test.py (16 tests) and the placeholder mapping helpers in pandapower_study_fixture.py
affects: [02-04 engine entry point, 02-05 study-level island and stale-result proof, 02-06 prepare_run on pandapower]

actuals:
  tokens: 9000
  tasks: 3
  commits: 3
plan_head_before: 207b2f54490586d9bca2687ed43c3a2152944117
plan_head_after: 5445e5619dfccf940c0dc356f6d2741f55b203b6

tech-stack:
  added: []
  patterns:
    - "One shared totals definition: the read-back and the scaling factor cannot disagree about what a total is"
    - "Surface pin by inspect.signature plus an AST walk of the study modules, so a new adapter call without a pin fails a test"
    - "Behavioural contract: the same call script on both adapters compares types, order and refusals, never numbers"

key-files:
  created:
    - backend/tests/pandapower_api_contract_test.py
  modified:
    - backend/pandapower_job/api.py
    - backend/pandapower_job/scaling.py
    - backend/tests/pandapower_study_fixture.py

key-decisions:
  - "scale_load shares the increment over the subsystem's in-service loads in proportion to P (research assumption A2, settles when PSE-02 records the detail); Q follows only when q_scales_with_p is yes, and an inconclusive detail is refused."
  - "A subsystem with no in-service load, or only zero-P loads, is a no-op (so margin._check_loads_mapped_branches fires as on PSS/E); a negative subsystem total is refused rather than guessed."
  - "scale_load changes the state to STALE only when it changed a load; define_subsystem and scale_case always set STALE."
  - "ENG-04 stays Pending in REQUIREMENTS.md: this plan delivers the scaling half (fresh copy per city and step); the study-level proof for outages and no read after a failed solve is plan 02-05. ENG-01 was already Complete from plan 02-01."

requirements-completed: [ENG-01]

coverage:
  - id: D1
    description: "importing pandapower_job.api registers the factory under pandapower; the unchanged study code prepares a scaled, rated, solved city base on it"
    requirement: "ENG-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_tracer_one_city_base_through_the_registry"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_registry_holds_the_pandapower_factory"
        status: pass
    human_judgment: false
  - id: D2
    description: "read_totals, scale_case and Phase 1's scale_city share scaling.case_totals; scaling refusals reach the study as apply_ratings with no figure in the message; the master is untouched"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_read_totals_matches_case_totals_and_fixture"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_scale_case_reads_back_and_leaves_master"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_scale_case_refusal_reaches_the_study_as_apply_ratings"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_scale_case_bad_targets"
        status: pass
    human_judgment: false
  - id: D3
    description: "the margin's subsystem increment: proportional to P, Q rule by detail, no-op without load, PsseApi's refusal texts, and a reloaded snapshot returns the base loads and flows"
    requirement: "ENG-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_scale_load_q_rules"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_scale_load_subsystem_without_load_is_a_no_op"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_scale_load_and_subsystem_refusals"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_margin_step_reloads_a_fresh_copy"
        status: pass
    human_judgment: false
  - id: D4
    description: "the adapter's surface is pinned to PsseApi by name, signature, return type, ordering and refusal, and the study code can call only the pinned 14 methods"
    requirement: "ENG-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_public_surface_equals_psse_api"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_constructor_matches_psse_api"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_study_code_calls_only_the_pinned_surface"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_contract_return_types_and_order"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_contract_refusals_match"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_api_contract_test.py#test_contract_unknown_branch_is_a_call_error"
        status: pass
    human_judgment: false

duration: 30min
completed: 2026-11-18
status: complete
---

# Phase 2 Plan 03: Scaling, Registration and the PsseApi Pin Summary

**PandapowerApi now has all 14 PsseApi methods, registers itself as "pandapower", reuses Phase 1's scale_city through one shared totals definition, and a test fails if its surface or behaviour ever drifts from PsseApi's.**

## Performance

- **Duration:** about 30 min
- **Tasks:** 3 (one tracer, two TDD)
- **Files:** 1 created (the contract test module), 3 modified
- **Runtime of `pandapower_api_contract_test.py`:** 16 tests in about 11 s

## Accomplishments

- `scaling.case_totals(net, details)` is the single definition of a case's load and generation total (in-service load P; in-service machine P plus the swing's `psse_pg_mw` when `swing_in_total` is yes; `ScalingUndetermined` when that detail is inconclusive). `scale_city` now calls it, with every other line and refusal order unchanged; Phase 1's scaling users still pass.
- `read_totals` and `scale_case` use it. `scale_case` validates both targets with PsseApi's own `_positive_target` (same texts) and replaces the working network with `scale_city`'s deep copy, so the master and every snapshot stay untouched. Scaling refusals reach `study.scale_city_case` as ValueErrors and come out as `StudyFailed("apply_ratings", "scaling: ...")` with no figure in the message.
- `define_subsystem` and `scale_load` implement the margin's increment: the increment is spread over the subsystem's in-service loads in proportion to P, Q follows only when `q_scales_with_p` is yes, an inconclusive detail is refused, and a subsystem with no load is a no-op.
- `import pandapower_job.api` runs `study.register_solver("pandapower", factory)`. `study.index_case(..., solver="pandapower")` then builds a `PandapowerApi`, and `study.prepare_city_base` scales, rates, solves, reads and saves one city on the unchanged study code (the tracer).
- The pin: sorted public method names and `inspect.signature` of each equal PsseApi's (14); the constructor tail is `protected_path=None`; an AST walk of `study.py`, `contingency.py`, `margin.py`, `violations.py` and `dispatch.py` finds exactly those 14 names called on `api`.
- The behavioural contract runs one script on `PsseApi(FakePsspy)` and on `PandapowerApi`: return types and ordering match, 16 bad calls are refused with the same class (and the same text wherever PsseApi validates before psspy), and an unknown branch is a `PsseCallError` from both.

## Task Commits

1. **Task 1 (tracer): one city's base through the registry and the shared totals definition** - `3198a70` (feat)
2. **Task 2: subsystem increment, scaling refusals, fresh copy per step** - `819c5cb` (test)
3. **Task 3: signature pin, study-call pin, behavioural contract** - `5445e56` (test)

## Verification

- `pandapower_api_contract_test.py` alone: **16 passed, 0 skipped, 0 failed**.
- Task 3's command (contract, `pandapower_api_test.py`, `psse_study_solver_test.py`, `pandapower_import_gate_test.py`, `psse_api_test.py`, `psse_contract_test.py`): **131 passed, 0 skipped, 0 failed**.
- Task 2's command (contract, `pandapower_api_test.py`, `pandapower_compare_test.py`): **56 passed, 0 skipped**.
- The eleven-file PSS/E regression set of plan 02-01: **349 passed**, equal to the baseline at HEAD.
- Verification-section set (contract, api, compare, cli): **71 passed, 1 failed**. The one failure is a Windows-only environment issue, see Deviations.
- Frozen-file gate (PLAN=02-03) exits 0 after each commit; the staged leak scan exited 0 before each commit; the full leak scan exits 0 (36 binary or oversized files not scanned, as before).
- Mutation checks: ignoring the Q rule, renaming a `scale_load` parameter, changing a refusal class, and dropping the zero-P no-op each turned a named test red.
- Commands ran with `.venv/Scripts/python.exe`; the pandapower 3.5.6 import check passed. Cosmetic warning seen: "numba cannot be imported".

## Deviations from Plan

### Notes (no code deviation)

**1. [Environment] One Phase 1 test fails on Windows, unrelated to this plan**
- `pandapower_cli_test.py::test_private_outputs_are_ignored_and_flagged_by_the_leak_guard` asserts a POSIX file mode of 0o600 (`os.stat` reads 0o666 on Windows). The plan's acceptance line "compare and cli tests report no failure" therefore cannot be met on this machine; the other 30 tests of those two files pass. The test and code are plan 01-09's and do not touch the adapter, scaling or the study. Logged in `deferred-items.md`, not fixed (out of scope).

**2. Order of implementation inside the tasks**
- `define_subsystem` and `scale_load` (planned for Task 2) were written in Task 1's commit together with `read_totals` and `scale_case`, so Task 2's tests did not start red against a missing method. To check the tests are not vacuous, four mutations of the finished code were run and each failed a named test (see Verification). This is the same kind of note as plan 02-02's.

**3. Commit ledger collision (process, same as plans 02-01 and 02-02)**
- `.git/gsd-plan-head-before-02-03` held a stale base (`be8a4ae`) from the old pss-e-integration workstream's own plan 02-03. It was overwritten with this plan's true base (`207b2f5`) before the first commit; the measured count is 3 commits, matching the three task commits.

**4. Test-side adjustments**
- The module shares one adapter per case file, and a defined subsystem outlives `load_case` by design, so `test_scale_load_and_subsystem_refusals` clears `_subsystems` first. The planned "factor 1.5 with `("yes", "inconclusive", "yes")`" refusal check uses a `Target` namedtuple at the `study.scale_city_case` level and also checks that the targets' own text forms (as well as the synthetic ones) are absent from the message.

Otherwise: none - plan executed as written.

## Known Stubs

None.

## Threat Flags

None. T-02-09 is mitigated by `test_scale_case_reads_back_and_leaves_master` and `test_margin_step_reloads_a_fresh_copy`; T-02-10 by `test_registry_holds_the_pandapower_factory`; T-02-11 by the signature pin, the study-call pin and the behavioural contract; T-02-SC met (nothing installed, requirements files untouched).

## Self-Check: PASSED

- FOUND: backend/pandapower_job/api.py (read_totals, scale_case, define_subsystem, scale_load, SOLVER_NAME, `register_solver(SOLVER_NAME, factory)`)
- FOUND: backend/pandapower_job/scaling.py (`def case_totals`)
- FOUND: backend/tests/pandapower_api_contract_test.py (16 tests)
- FOUND: backend/tests/pandapower_study_fixture.py (`def write_placeholder_mapping`)
- FOUND commits 3198a70, 819c5cb and 5445e56 (ancestors of HEAD)
