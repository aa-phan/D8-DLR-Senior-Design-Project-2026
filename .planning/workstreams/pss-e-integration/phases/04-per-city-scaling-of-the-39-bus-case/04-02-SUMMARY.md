---
phase: 04-per-city-scaling-of-the-39-bus-case
plan: 02
subsystem: psse-adapter
tags: [psse, psspy, scal_2, adapter, fake-psspy, tdd, python37]

requires:
  - phase: 02-psse-job-core
    provides: PsseApi adapter, SURFACE table, FakePsspy and the increment form of scal_2
provides:
  - "psse_api.ScaleLayout, psse_api.SCALE_LAYOUT (UNVERIFIED), psse_api.CaseTotals"
  - "PsseApi.read_totals(): whole-case total load and generation in MW"
  - "PsseApi.scale_case(load_mw, gen_mw): one scal_2 call on all buses in new-total mode"
  - "FakePsspy whole-case scal_2 (new total, totals read), FakeCase.gens, generation in placeholder_case"
affects: [04-03-study-per-city-scaling, 04-05-probe-row, 04-06-laptop-check]

actuals:
  tokens: 4344
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "One UNVERIFIED layout table (SCALE_LAYOUT) for an argument layout that only community evidence supports; a test ties the fake's slots to it"
    - "Target validation before any psspy call with parameter-named ValueError and no value in any message"

key-files:
  created: []
  modified:
    - backend/psse_job/psse_api.py
    - backend/tests/psse_fake_psspy.py
    - backend/tests/psse_api_test.py

key-decisions:
  - "read_totals sends status as five int sentinels and scalval as seven real sentinels; the fake demands exactly that for apiopt 1 and requires new-total status only for apiopt 0"
  - "The _positive_target helper is a staticmethod on PsseApi, shared by both targets, so the message names the parameter and never the value"
  - "scale_case does not inspect the returned totals (PD-3); only read_totals validates them, and the study (plan 04-03) is the reader that checks every scaling"

patterns-established:
  - "Layout table plus fake slots tied by one test, so a laptop-check correction is one deliberate edit in two places"

requirements-completed: [SCL-02]

coverage:
  - id: D1
    description: "PsseApi.read_totals and PsseApi.scale_case set and read the whole case's load and generation totals with one scal_2 call, and a fresh load_case restores the base totals"
    requirement: "SCL-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_api_test.py#test_tracer_scale_case_sets_and_reads_back_whole_case_totals"
        status: pass
    human_judgment: false
  - id: D2
    description: "The argument layout lives in psse_api.SCALE_LAYOUT, marked UNVERIFIED with its evidence, and the fake's slots are tied to it"
    requirement: "SCL-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_api_test.py#test_scale_layout_matches_the_fake"
        status: pass
    human_judgment: false
  - id: D3
    description: "A bad target never reaches psspy and no message holds a target; a non-zero ierr or an odd return is PsseCallError naming function and ierr only"
    requirement: "SCL-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_api_test.py#test_scale_case_refuses_bad_targets_before_any_call"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_api_test.py#test_scale_case_maps_ierr_without_figures"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_api_test.py#test_read_totals_rejects_bad_returns"
        status: pass
    human_judgment: false
  - id: D4
    description: "The SURFACE has no function that runs a script or response file, the scal_2 row stays HIGH, and the increment form behaves as before"
    requirement: "SCL-02"
    verification:
      - kind: unit
        ref: "backend/tests/psse_api_test.py#test_surface_cannot_run_a_script"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_api_test.py#test_io_subsystem_and_scale_load"
        status: pass
    human_judgment: false
  - id: D5
    description: "Whether PSS/E 36.4 reads the SCALE_LAYOUT slots this way (new-total mode, slot positions of the totals array, power factor kept)"
    requirement: "SCL-02"
    verification: []
    human_judgment: true
    rationale: "The fake is built from the same layout the adapter sends, so its tests cannot show what the real engine accepts; plan 04-05 (probe row) and plan 04-06 (laptop check, runbook step 4) settle it"

plan_head_before: 4faab3a47c04e68e97f60c32d54d35445d0ccf4e
plan_head_after: f5351212a211d50e9034b3b6f74f41d3115e7323

duration: 8min
completed: 2026-11-11
status: complete
---

# Phase 4 Plan 02: Whole-case scaling call in the PSS/E adapter Summary

**One documented `scal_2` call that reads and sets a case's total load and generation, with the unproven argument layout kept in a single UNVERIFIED table (`SCALE_LAYOUT`), a fake psspy that models it, and a SURFACE that still cannot run any script.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-11-11T03:23:33Z
- **Completed:** 2026-11-11T03:31Z
- **Tasks:** 2
- **Files modified:** 3 (344 insertions, 1 deletion)

## Accomplishments

- `PsseApi.read_totals()` returns `psse_api.CaseTotals(load_mw, gen_mw)` from the totals array of one `scal_2` call over all buses; `PsseApi.scale_case(load_mw, gen_mw)` sets both totals with one call in new-total mode, every other scaled quantity left at the sentinel and the constant P/Q setting keeping each load's power factor (CD-2, CD-9).
- `ScaleLayout` and `SCALE_LAYOUT` hold sid, the all-buses flag, both apiopt values, the status array, the scalval slots and the totals slots in one place, marked UNVERIFIED with the forum evidence and a pointer to the laptop check; the module docstring names it as the second unverified item next to `branch_chng_3`.
- Targets that are not a finite number above 0 (NaN, infinity, 0, negatives, booleans, text, ints too large for a float) are a `ValueError` naming only the parameter before any psspy call. A non-zero ierr is `PsseCallError("scal_2", ierr, ...)`; a malformed return, or a totals array without finite numbers at the layout's slots, is `PsseCallError` with the shape meaning. No message holds a target or a total.
- The fake psspy gained `FakeCase.gens`, 630 MW per source bus in `placeholder_case` (the fake network's own totals are 2480 MW load and 2520 MW generation), and an `all == 1` branch in `scal_2` that models new totals and the totals read. The increment branch is untouched.
- SURFACE, the `scal_2` row (HIGH), the SURFACE name list and `scale_load` are unchanged; `test_surface_cannot_run_a_script` pins that no `run*` function (no response-file or IPLAN runner) can exist (CD-2, T-04-04).

## TDD record

Task 1 is `type="tracer"` with `tdd="true"`; the plan specifies one `feat` commit for it, so tests and implementation were committed together, after a real RED run.

- **RED (Task 1):** with only the tests written, `-k "tracer_scale_case or scale_layout_matches or recorded_calls_stay"` gave 3 failed, 43 deselected: `AttributeError: module 'psse_job.psse_api' has no attribute 'SCALE_LAYOUT'` and `'PsseApi' object has no attribute 'read_totals'`. Semantic assessment: each target test executed and failed because the planned symbols did not exist, not on a collection, syntax, import or fixture fault; the third failure is the existing recorded-calls test, to which the plan adds the two new methods. The machine classifier `gsd_run check tdd-red-evidence` has no pytest report adapter, so no record was submitted to it; this assessment is by inspection of the real output.
- **GREEN (Task 1):** the three tests plus the 43 existing ones pass; the plan's combined command gave 137 passed (`psse_api_test.py` alone: 46 passed, the two named tests 2 passed).
- **Task 2:** the new tests were written after Task 1's code, which already validated strictly, so the Task 2 tests passed on first run and there was no separate RED. That is a plan-ordering fact, not a defect, and it is why the mutation checks below matter: they show each new test fails when its guarded behavior is broken.
- No REFACTOR commit.
- Gate commits: `1ed707c` is the `feat(04-02)` commit and `f535121` the `test(04-02)` commit. The plan puts the `feat` commit first and the `test` commit second; the TDD gate scan by commit type will therefore see GREEN before RED. This follows the plan's two-commit layout and is recorded here rather than rewritten.

## Task Commits

1. **Task 1: Tracer - scale the whole fake case to new load and generation totals, read them back, reload to restore** - `1ed707c` (feat)
2. **Task 2: Bad targets never reach psspy, PSS/E errors and odd returns become PsseCallError without figures, nothing can run a script** - `f535121` (test)

**Plan metadata:** the commit holding this SUMMARY (docs). STATE.md, ROADMAP.md and REQUIREMENTS.md are not edited here (rule C-4; the orchestrator owns them).

## Files Created/Modified

- `backend/psse_job/psse_api.py` - `ScaleLayout`, `SCALE_LAYOUT`, `CaseTotals`, `PsseApi._scale_status`, `read_totals`, `_positive_target`, `scale_case`, one docstring sentence
- `backend/tests/psse_fake_psspy.py` - `FakeCase.gens`, generation in `placeholder_case`, `FAKE_TOTALS_LENGTH/LOAD/GEN`, `_GEN_MW_PER_SOURCE`, `_whole_case_totals`, `_scal_2_whole_case` and the `all == 1` branch of `scal_2`, docstring
- `backend/tests/psse_api_test.py` - tracer, layout tie, bad-target, ierr-mapping, bad-return (13 cases), integer-totals, fake-array and no-script tests; `read_totals` and `scale_case` added to the recorded-calls test

## Final SCALE_LAYOUT values (handed to plan 04-06)

| Field | Value |
|-------|-------|
| sid | 0 (ignored with all buses, research A10) |
| all_flag | 1 |
| apiopt_scale | 0 |
| apiopt_totals | 1 |
| status | (None, 1, 0, 1, 0); None is the int sentinel; index 1 value 1 is new-total mode, index 3 value 1 is constant P/Q |
| scalval_load / scalval_gen / scalval_slots | 0 / 1 / 7 (the other five are the real sentinel) |
| totals_load / totals_gen | 1 / 2 (indices into the totals array) |
| evidence | FORUM questions 1720, 2551, 4673 and 6830 (community, not the manual); increment form proven on PSS/E 36.4 (U11); laptop check pending (runbook step 4) |
| confidence | UNVERIFIED |

The read call sends `status` as five int sentinels and `scalval` as seven real sentinels with `apiopt=1`. Plan 04-06 should confirm or correct: the new-total mode value, which `status` slot selects it, the totals array indices, whether a read with all-sentinel arguments is accepted, and whether `scal_4` exists with a different layout (CD-11). A correction is one edit to `SCALE_LAYOUT` plus the matching `FAKE_TOTALS_*` constants in the fake; `test_scale_layout_matches_the_fake` fails if only one side is changed.

## Mutation checks (plant, see red, restore byte for byte)

Each was applied to `backend/psse_job/psse_api.py` and run against `psse_api_test.py`; the file was restored from a copy and its SHA-256 checked equal to the original after the set.

| Mutation | Result |
|----------|--------|
| `scale_case` sends `all=0` | red: 2 failed (the tracer, through the fake's ierr 1; the recorded-calls test) |
| load and generation slots swapped (`scalval_load=1, scalval_gen=0`) | red: 1 failed (the tracer) |
| `read_totals` accepts a non-finite total | red: 2 failed (`test_read_totals_rejects_bad_returns` NaN and infinity cases) |
| the ValueError text holds the value | red: 1 failed (`test_scale_case_refuses_bad_targets_before_any_call`) |
| a `runrspnsfile` SURFACE row added | red: 5 failed (`test_surface_cannot_run_a_script` plus four drift guards) |

The first attempt at the `all=0` mutation did not apply (a malformed here-document in my own script) and showed 64 passed; it was redone with an assertion that the replaced text exists, and then failed as listed. The earlier "64 passed" was not a pass of the mutated code.

## Verification results

- Task 1 automated command (api, margin, probe, study, contract tests): 137 passed.
- Task 2 automated commands: `psse_api_test.py` 64 passed (floor 51); margin, probe, study, contract 91 passed.
- Plan-level verification command (adds `psse_contingency_test.py`): 178 passed.
- Acceptance `-k` selections: 2 passed (tracer and layout tie), 3 passed (increment form, rows with evidence, cannot run a script). `grep -c "def scale_case"` is 1 and `grep -c "^SCALE_LAYOUT = "` is 1 (baselines 0).
- Own-changes gate (PLAN=04-02): exits 0 after each task commit.
- Wider run, `backend/tests/psse_*_test.py backend/tests/secret_scan_test.py`: 574 passed, 152 skipped, 1 failed in 122.68 s. The one failure is `psse_results_migration_test.py::test_psse_migration_is_unchanged_after_apply`, the known unrelated failure (core.autocrlf rewrites the migration to CRLF, so its pinned SHA-256 differs; the committed blob is correct). The 152 skips were already there (they are not from this plan's tests, none of which skip); the plan's wave-end "no skipped test" gate is the orchestrator's to evaluate against that baseline.

## Decisions Made

- `read_totals` demands `len(result) >= 2` only after the ierr check, so `(6,)` reports ierr 6 and `(0,)` reports the shape meaning.
- Integer totals from psspy are accepted and returned as floats (`test_read_totals_accepts_integer_totals`); booleans, strings and huge ints are the shape error.
- The fake rejects, beyond PD-4, a non-finite or non-numeric load or generation target (ierr 4) and requires all-sentinel arrays for the totals read. Only the numbers the adapter sends are accepted.

## Deviations from Plan

None - plan executed exactly as written. Two points worth stating plainly: the plan's Task 2 text speaks of a FakePsspy subclass for the error-returning `scal_2`; I used the replaced bound method with a five-keyword lambda, which the same plan text names as the pattern for bad returns, because it needs no extra class. The behavior tested is identical. And the Task 2 tests needed no change to Task 1's adapter or fake code, so Task 2's commit holds only the test file.

**Total deviations:** 0 auto-fixed.

## Issues Encountered

- A malformed mutation script produced a false "64 passed" for the `all=0` check; found at once by reading the output against the other four, redone with an assertion on the replaced text. No code was affected; the original file was restored byte for byte.
- The `backend/tests/psse_*_test.py` wider run takes about two minutes and was backgrounded by the shell timeout; it completed normally.

## Known Stubs

None. No placeholder values flow into any output; `FAKE_TOTALS_*` and the 630 MW per source bus are the fake network's own synthetic values, as the plan specifies.

## Threat Flags

None. The change adds no endpoint, auth path, file access or schema; `scale_case` takes numbers only and SURFACE gained no row (T-04-04), messages carry no figure (T-04-05), and the layout is one UNVERIFIED table with a totals read for the study to check against (T-04-06).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 04-03 can call `api.read_totals()` and `api.scale_case(load_mw, gen_mw)` once per city after a fresh `load_case`, against the fake.
- Open until plans 04-05 and 04-06 run on the PSS/E laptop: the real engine's reading of `SCALE_LAYOUT`. Nothing here proves it; the SUMMARY of 04-06 should record the result and, if needed, the corrected slots.

## Self-Check: PASSED

- Modified files exist: `backend/psse_job/psse_api.py`, `backend/tests/psse_fake_psspy.py`, `backend/tests/psse_api_test.py`.
- Commits `1ed707c` and `f535121` are on `feature/pss-e-integration`; `git rev-list --count 4faab3a..HEAD` was 2 when measured (plan_head_before is the ledger base).
- No deleted files in either commit; STATE.md, ROADMAP.md, REQUIREMENTS.md, milestone.lock and `.planning/config.json` untouched by this plan.

---
*Phase: 04-per-city-scaling-of-the-39-bus-case*
*Completed: 2026-11-11*
