---
phase: 02-study-on-power-systems-case
plan: 03
subsystem: psse-job-study-base
tags: [pss-e, study, mapping-check, ratings, load-flow, temp-file, budget, stdlib, python37]
requires:
  - phase: 01
    provides: "constants.CITIES and FAILED_STAGES, units.circuit_mva, run_record.case_label and file_sha256, contract.StudyFailed, the 3.7 syntax and import gate"
  - phase: 02
    provides: "plan 02-01 mapping and settings; plan 02-02 PsseApi, the SURFACE table and the fake psspy"
provides:
  - "psse_job.study (base part): Budget, ResolvedBranch, CityBase, StudyArea, BaseCase, check_mapping, study_area, apply_ratings, solve_base, prepare_base, cleanup_base"
  - "backend/tests/psse_study_test.py: 36 tests (IN-02, IN-03, STU-01 at the study level against the fake psspy)"
  - "Phase 1 import allow-list deliberately extended with tempfile (psse_contract_test.py)"
affects: [02-04, 02-05, 02-06, 02-07]
tech-stack:
  added: []
  patterns:
    - "check the whole mapping against the loaded case's index before the first write; all problems in one StudyFailed message"
    - "rating = units.circuit_mva of selection.choices[city] at the case's own base kV, written to every listed rate set and read back to 1e-6 relative"
    - "solve once, save once to a private mkdtemp directory, reload before every later evaluation; the directory is removed on every exit path"
key-files:
  created:
    - backend/psse_job/study.py
    - backend/tests/psse_study_test.py
  modified:
    - backend/tests/psse_contract_test.py
key-decisions:
  - "study_area takes an optional fifth argument sinks (city -> sink buses), because the plan's four-argument signature carries no sink buses yet 'sinks always included' needs them; prepare_base passes it, a call without it simply omits sinks"
  - "check_mapping returns resolved as a dict city -> tuple of ResolvedBranch (the kV of a city is branches[0].base_kv once the mapping check has passed)"
  - "A PsseCallError or ValueError while reading the solved base (bus_table, branch_loading) is stage load_flow; CaseProtected on the temp save is not caught (a bug, not a case problem) but still removes the temp directory"
  - "NaN is treated as a failure by the mismatch and collapse guards (the comparisons are written 'not x <= limit' and 'not pu >= collapse')"
requirements-completed: [IN-02, IN-03, STU-01]
duration: 1h
completed: 2026-10-28
status: complete
commits: 3
plan_head_before: be8a4aeeb18e2ea4216ffd689565722df367e060
plan_head_after: 9775c8b7ee9937e63eb91fe399f8b2683fec6c88
actuals:
  tokens: 9700
  tasks: 3
  commits: 3
---

# Phase 2 Plan 03: Study base - mapping check, rating write, strict base load flow Summary

**`prepare_base` loads Power Systems' case through the adapter, refuses a wrong mapping before anything is written, writes each city's selected rating as read-back per-circuit MVA at the branch's own base kV, solves the base under the strict convergence rule, and saves it to a private temp file that `cleanup_base` removes.**

## Accomplishments
- `prepare_base(psspy_module, case_path, mapping, selection, budget=None)` runs in the plan's order: adapter built with `protected_path=case_path`, load, branch and bus index, `check_mapping`, `study_area`, `apply_ratings`, `solve_base`, post-solve reads, save to `<mkdtemp>/base.sav`. Nothing before `apply_ratings` writes to the case; the failure matrix asserts the fake saw no `branch_chng_3`, `fnsl`, `save`, `bsys` or `scal_2` call.
- `check_mapping` (pure) reports every problem at once: missing branch, transformer, out of service, endpoints of different base kV, a city whose branches differ in base kV, a missing or isolated sink bus, an extra outage that is not a line. A reversed entry resolves to the case's orientation.
- `apply_ratings`: MVA only from `units.circuit_mva(choice.amps_per_conductor, choice.subconductors_per_phase, kv)`, no power factor, every parallel circuit gets the full per-circuit value, every listed rate set is written and read back (`abs(read - mva) > 1e-6 x mva` is StudyFailed `apply_ratings`); the first rate set's earlier value is kept as `rate_before_mva`.
- `solve_base`: only fnsl 0 with solved() 0 passes; a mismatch above `max_mismatch_mva` and a bus below `collapse_voltage_pu` are stage `load_flow`; fnsl ierr 2 adds the converted-generators remedy. A save failure is stage `contingency` and removes the temp directory; `cleanup_base` uses `os` only.
- `Budget` with an injected clock (strictly greater than the maximum fails); `StudyArea` is computed once by breadth-first search (hops, `min_monitor_kv`, scope "all").

## Task Commits
1. Task 1 (tracer): `75121cf` feat(02-03): tracer - the placeholder case loaded, mapping resolved, four DLR ratings written in MVA and read back, base solved and saved to a private temp file (also carries the `tempfile` allow-list line, reason in the message body)
2. Task 2: `02def2b` feat(02-03): mapping check before any write and read-back ratings in the units PSS/E expects
3. Task 3: `9775c8b` feat(02-03): base load flow under the strict rule, study area, private temp file and run-time budget

## Verification
- `psse_study_test.py -k tracer`: 1 passed. `-k "check or units or static"`: 19 passed. `-k missing_branch_fails_before_any_write`: 1 passed. `-k "load_flow or base"`: 20 passed (plan minimum 16; 6 parametrized plus 14, including the tracer and one extra area test).
- `psse_contract_test.py psse_mapping_test.py psse_api_test.py psse_study_test.py`: 191 passed. Wider psse suite (`+ psse_job_test psse_ratings_test psse_writer_test psse_run_record_test`): 328 passed, 28 skipped (Postgres-backed; no Postgres needed by this plan).
- The `python -I` namedtuple check prints `True`; `grep -c '"tempfile"'` on the contract test prints 1; the contract test change was 2 added and 1 removed lines (the comment and the one allow-list line) before the task commit; the own-changes gate over the protected paths exits 0.
- Mutation checks (each turned the named test red; study.py restored byte-for-byte, verified by byte comparison and an empty `git diff` afterwards): skip read-back (test_units_read_back_enforced), ratings written before the mapping check (test_check_missing_branch_fails_before_any_write), LINE_VOLTAGE_KV_DEFAULT instead of the case kV (test_units_follow_case_base_kv_138), MVA divided over parallel circuits (test_units_parallel_circuits_each_get_the_circuit_mva), mismatch guard dropped (test_load_flow_mismatch_guard), base saved to the case path (test_base_saved_to_temp_never_case_path, through CaseProtected). Harness: `scratchpad/mutate_0203.py`, run with `-B` and PYTHONDONTWRITEBYTECODE=1.

## Deviations from Plan

### Auto-fixed Issues
None.

### Notes (choices inside the plan's latitude, not deviations of behaviour)
- **`study_area` has an optional fifth parameter `sinks`.** The plan's signature `study_area(lines, buses, resolved, settings)` has no source for sink buses, yet the monitored set must always include them. The extra argument defaults to none; the plan's four-argument call still works. Plans 02-04 and 02-05 use `base.area`, not this function, so nothing downstream depends on the call form.
- **Task 1 test not run red first.** `study.py` and the tracer test were written together and first run green (same as plans 02-01 and 02-02); the mutation checks above are the evidence the tests can fail. Task 1's `study_area` is already the full breadth-first search rather than a happy-path stub, and Task 3 only added the mismatch and collapse guards and the ierr-2 remedy.
- **Extra test beyond the plan's list:** `test_base_area_all_scope_counts_every_line` (16 lines in scope "all", the full ten-line AUSTIN neighbourhood at 2 hops). The tests also set `tempfile.tempdir` to a per-test scratch directory (autouse fixture), so any leaked temp directory shows as a non-empty listing.
- **`solved=<code>` in a failed-fnsl message shows fake/stale `solved()`** (for example `ierr=2 solved=9` or `solved=0`), because the plan fixes that message format; the meaning text that follows says `solved() is not trusted after a failed fnsl`. Plan 02-06 may want the run record to omit the number for a non-zero ierr.
- Bash heredoc was attempted once by mistake for a no-op; no file was written through it. All file content went through Write/Edit.

## Known Stubs
None.

## Threat Flags
None. The only new filesystem surface is the per-run `tempfile.mkdtemp` directory already covered by T-02-14 (private, removed on every path, never the case path); no network or auth surface.

## Hand-off notes for later plans
- `BaseCase` field order is exactly as in the plan's interface block; `ResolvedBranch`, `CityBase`, `StudyArea` and `BaseCase` are namedtuples (`_replace` works). `base.cities` is an `OrderedDict` in `constants.CITIES` order; `base.lines` and `base.transformers` are tuples of `BranchRow`; `base.buses` is the pre-write index (`base.base_buses` is after the solve).
- `base.saved_path` is the file to reload with `base.api.load_case(base.saved_path)` before every outage and every transfer step; `cleanup_base(base)` must run on every exit path of the later stages (prepare_base itself only cleans up when it fails).
- After a failed `fnsl`, `SolveResult.iterations` and `mismatch_mva` are None and `solved_code` is stale; later stages must classify outages from `converged`, not from `solved_code`.
- The mapped branches' rating in the case after `prepare_base` is the DLR value; `rate_before_mva` holds the case's own previous value for the first rate set (research open question 5, not resolved here).

## Self-Check: PASSED
- FOUND: backend/psse_job/study.py, backend/tests/psse_study_test.py, backend/tests/psse_contract_test.py
- FOUND commits: 75121cf, 02def2b, 9775c8b (each an ancestor of HEAD); measured `git rev-list --count` from the ledger base is 3
