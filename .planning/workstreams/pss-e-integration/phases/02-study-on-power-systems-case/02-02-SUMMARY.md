---
phase: 02-study-on-power-systems-case
plan: 02
subsystem: psse-job-adapter
tags: [pss-e, psspy, adapter, fake, convergence, surface-table, stdlib, python37]
requires:
  - phase: 01
    provides: "the 3.7 syntax and import gate (psse_contract_test), the psse_job package conventions"
  - phase: 02
    provides: "plan 02-01: settings.BranchRef, the placeholder mapping's 9xxxx buses"
provides:
  - "psse_job.psse_api: SURFACE (19 rows), SURFACE_NAMES, SURFACE_BY_NAME, SurfaceRow, classify_solve, SolveResult, BranchRow, BusRow, BranchFlow, PsseCallError, CaseProtected, PsseApi, pct_string, SOLVED_MEANING, FNSL_ERRORS, CASE_ERRORS, SAVE_ERRORS, BRNDAT_ERRORS, BRANCH_CHNG_ERRORS, RATE_INDEX"
  - "backend/tests/psse_fake_psspy.py: FakePsspy (19 SURFACE methods), FakeCase, SolveOutcome, placeholder_case, radial_solver, apply_outcome, PLACEHOLDER_CITY_BUSES, SWING_BUS (helper, not collected)"
  - "backend/tests/psse_api_test.py: 44 tests (adapter, convergence matrix, SURFACE drift)"
affects: [02-03, 02-04, 02-05, 02-06, 02-07]
tech-stack:
  added: []
  patterns:
    - "injected psspy module behind one gate (_call) that refuses any name or keyword outside the SURFACE table"
    - "fail closed: every psspy failure is a PsseCallError naming function, ierr and the manual's meaning, never arguments or paths"
    - "fake psspy with exact manual signatures; a recording wrapper (functools.wraps) keeps inspect.signature exact while capturing the keywords actually passed"
key-files:
  created:
    - backend/psse_job/psse_api.py
    - backend/tests/psse_fake_psspy.py
    - backend/tests/psse_api_test.py
  modified: []
key-decisions:
  - "SolveResult.iterations and mismatch_mva are None unless fnsl itself returned 0, because after a failed fnsl iterat() and sysmsm() describe an older attempt (research Pitfall 1 warning sign)"
  - "The case-file guard protects only the path given to PsseApi(protected_path=...); with protected_path=None nothing is protected, so plan 02-03 must always pass the case path"
  - "A duplicate branch or bus key in a bulk read is a PsseCallError rather than a silently overwritten index entry"
  - "FakePsspy records calls through a functools.wraps wrapper so the keyword names actually passed are captured while inspect.signature still reports each method's exact parameters (no catch-all keyword parameter in any fake method)"
requirements-completed: [STU-01, TST-01]
duration: 1h 15m
completed: 2026-10-28
status: complete
commits: 3
plan_head_before: 248e870e130b48c11cf465e8426930b7612e5010
plan_head_after: ec2b0fedc12a762fb198f83d2f42e1d46a49e12f
actuals:
  tokens: 16900
  tasks: 3
  commits: 3
---

# Phase 2 Plan 02: PSS/E adapter, SURFACE table and fake psspy Summary

**`PsseApi` wraps an injected psspy module behind a 19-row SURFACE table, decides convergence once (fnsl ierr 0 and solved() 0, both plain ints), never writes a non-positive or non-finite rating, refuses to save onto the loaded case, and has a fake psspy that implements exactly that table with drift tests.**

## Accomplishments
- `backend/psse_job/psse_api.py` (stdlib only, no psspy import; the Phase 1 import gate and 3.7 gate pass): the SURFACE table with parameter names, return shape, evidence and confidence per row (`branch_chng_3` is the single UNVERIFIED row, research A1); `_call` refuses an unlisted name, an unlisted keyword, a keyword given twice and too many arguments before psspy is touched, records every call, and turns any psspy exception into `PsseCallError(name, None, <exception class>)`.
- `classify_solve`: only `(0, 0)` converges. A bool, None or any other value for either code is not converged; `(2, 0)` reads "fnsl ierr 2: generators are converted; solved() is not trusted after a failed fnsl"; an unknown solved code reads "unknown solved code N".
- `PsseApi` methods: `load_case`, `save_case` (CaseProtected for the protected path under normcase/realpath/abspath, so a different letter case, mixed slashes, `..` segments and a relative form are all refused), `version`, `solve`, `branch_table`, `bus_table`, `branch_loading`, `read_rate`, `set_rate`, `set_status`, `define_subsystem`, `scale_load`. `set_rate` refuses 0, negatives, NaN, infinity, bools, strings and huge ints with ValueError and no psspy call, and fills only the chosen rate set's slot; every other slot and every realar slot is the sentinel.
- `backend/tests/psse_fake_psspy.py`: FakePsspy with the manual's parameter names, the stale `solved()` after a failed fnsl, two-character circuit-id padding, and the placeholder case (the 9xxxx buses of the committed example mapping) on a radial solver whose base values are pinned: AUSTIN sink 0.934737 pu, EL_PASO sink 0.983684 pu, 326.315789 MVA per city-line circuit, both city lines out gives fnsl ierr 3.
- Drift guards: fake public callables equal SURFACE_NAMES; `inspect.signature` of each fake method equals the row's parameters with no var-positional or var-keyword; exercising every PsseApi method uses all 19 rows, keeps every recorded call inside the table, and the adapter's `calls` equal the fake's recorded calls by name, argument count and keyword names, in order.

## Task Commits
1. Task 1 (tracer): `25bfca8` feat(02-02): tracer - adapter over an injected psspy loads and solves the fake placeholder case
2. Task 2: `aa871d1` feat(02-02): reads, rating writes with read-back, outages, subsystems and the case-file guard
3. Task 3: `ec2b0fe` test(02-02): convergence rule matrix and SURFACE drift guards

## Verification
- `psse_api_test.py -k tracer`: 1 passed. `-k test_io_`: 15 passed. `-k "save_refuses or set_rate_refuses"`: 2 passed. `-k "test_solve_ or test_surface_"`: 28 passed (19 parametrized, 4 solve, 5 surface).
- `psse_api_test.py psse_contract_test.py`: 54 passed (44 + 10). Neighbouring suites `psse_mapping_test.py psse_job_test.py` with them: 158 passed, 17 skipped (Postgres-backed tests; PSSE_REQUIRE_PG not set, none needed by this plan).
- Own-changes gate (no staged or committed change to config.py, supabase/migrations, production-pipeline plans or the results DDL/spec) exits 0.
- Mutation checks, each restored byte-for-byte (verified by byte comparison in the harness and an empty `git diff` on all three files afterwards): `solved() == 1` counted as converged (test_solve_classification red); solved() trusted after a failed fnsl (test_solve_stale_solved_after_failed_fnsl red); CaseProtected check dropped (test_io_save_refuses_the_case_path red); set_rate allowed to send 0 (test_io_set_rate_refuses_bad_values red); a catch-all keyword on a fake method (test_surface_parameters_equal_fake_signatures red). Tests ran with PYTHONDONTWRITEBYTECODE=1 and `-B`.

## Deviations from Plan

### Auto-fixed Issues
None - no bug or blocker needed fixing outside the plan's scope.

### Notes (choices inside the plan's latitude, not deviations)
- **Extra tests beyond the plan's list:** `test_io_transformer_refuses_rating_write` (branch_chng_3 ierr 3 text) and `test_solve_not_converged_codes_are_results_not_exceptions` (solved 1 is a result, with its iteration count kept because fnsl returned 0). Counts therefore read 15 `test_io_` and 28 `test_solve_`/`test_surface_` tests against the plan's minimum of 14 and 27.
- **`SAVE_ERRORS` table added** (1 blank name, 2 and 3 file errors, 4 prerequisites, from REF34 p.4's wording) so a failed `save` carries a meaning like the other calls; the plan's interface block lists no such table.
- **Task 1 test was not run red first:** the fake, adapter and tracer test were written together and first run green; the later tasks' mutation checks are the evidence that the tests can fail.
- **A stale `backend/psse_job/__pycache__/psse_api.cpython-312.pyc` (git-ignored cache) appeared during the run, apparently from the contract test's import subprocess; it was deleted before the final verification run.**

## Known Stubs
None. No hardcoded empty values reach a result path; the fake's `fake_*` helpers are test scaffolding by design.

## Threat Flags
None. The adapter adds no network endpoint, auth path or file access beyond `case`/`save` calls on caller-supplied paths, which T-02-06 already covers; the fake writes a small marker file only where a test tells it to save.

## Hand-off notes for later plans
- Always construct `PsseApi(psspy, protected_path=<case path>)`; the guard does nothing without it (plan 02-03).
- `PsseCallError` carries `.function`, `.ierr`, `.meaning`; the study should map it to a `StudyFailed` stage without echoing arguments.
- `branch_chng_3` and the `scal_2` combined form remain assumptions until the plan 02-07 probe runs on the laptop; the fake proves call shapes only (C-8).
- `FakePsspy(solver=...)` takes any callable `solver(case) -> SolveOutcome`; `SolveOutcome(ierr=3, solved=None)` reproduces the stale-`solved()` situation.

## Self-Check: PASSED
- FOUND: backend/psse_job/psse_api.py, backend/tests/psse_fake_psspy.py, backend/tests/psse_api_test.py
- FOUND commits: 25bfca8, aa871d1, ec2b0fe (each an ancestor of HEAD)
