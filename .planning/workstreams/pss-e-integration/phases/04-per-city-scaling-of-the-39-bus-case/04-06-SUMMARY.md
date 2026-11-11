---
phase: 04-per-city-scaling-of-the-39-bus-case
plan: 06
subsystem: psse-laptop-session
tags: [pss-e, laptop, scal_2, scale_to_target, four-city-dry-run, unverified-register, human-checkpoint]

requires:
  - phase: 04-per-city-scaling-of-the-39-bus-case
    provides: "the per-city study (04-03), the failure handling (04-04), the probe row scale_to_target, the runbook steps 4 and 5 and register rows U35 to U38 (04-05)"
provides:
  - "04-06-LAPTOP-RECORD.md: the scaling layout read against PSS/E 36.4's own documentation, the probe results before and after the fix, the four-city dry run, the claims cleared and the claims still UNVERIFIED"
  - "the finding that a totals read (APIOPT 1) stays open until an APIOPT 2 call closes it and that a second open read fails with ierr 5, and the fix (commit 5a30c63): read_totals closes every read, SCALE_LAYOUT.apiopt_close = 2, the fake models the open-read state"
  - "register rows U35, U36 and U38 seen on PSS/E 36.4 on 2026-11-11; U37 documented only"
affects: [phase-4-verification, plan-03-08]

actuals:
  tasks: 4
  commits: 2

key-files:
  created:
    - .planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/04-06-LAPTOP-RECORD.md
  modified:
    - docs/data-science/decisions/psse_laptop_runbook.md

key-decisions:
  - "The layout matched the documentation on every position; the one difference, the missing APIOPT 2 close, was found by the probe and fixed on the Mac, not on the laptop"
  - "U37 is recorded as documented but not measured; nothing was read before and after a scaling"
  - "The fix was made directly as a small change, not through a gap-closure plan, because the cause and the change were fully specified by three laptop experiments"

requirements-completed: [SCL-06]

duration: one laptop session (2026-11-10 to 2026-11-11)
completed: 2026-11-11
---

# Phase 4 Plan 06: Laptop session

## Outcome

The scaling layout was read from the installed documentation and matched. The first probe run with the write check failed `scale_to_target` with ierr 5 (30 PASS, 1 FAIL, exit 6). Three diagnostic scripts, run in memory on the example copy and never saved, showed the cause: a totals read stays open until an `APIOPT` 2 call closes it. The fix (commit 5a30c63) closes every read; the probe then ended with 0 FAIL and exit 0, and the four-city dry run on the version 2 placeholder mapping exited 0 with four dispatch rows, `validation: ok` and `study_seconds: 2.0`.

## Task results

1. Layout reading: done from `help(psspy.scal_2)` on the laptop; no identifier or figure in the reply.
2. Decision: the layout matches (every position the same).
3. Probe and dry run: done after the fix (the first probe run failed as described above).
4. Record: `04-06-LAPTOP-RECORD.md` and the runbook register annotations, committed as c1d7936.

## Deviations

- The plan's stop rule for a failed `scale_to_target` was to open a gap-closure plan. The cause was found the same night and the fix was small, so it was made directly (commit 5a30c63) with a mutation check (18 tests fail with the close removed) and the probe re-run on the laptop as the proof.
- The `--allow-placeholder` flag is needed on the probe once a placeholder mapping is in the configuration; the runbook's step 4 command omits it. Not yet corrected in the runbook.

## Known issues and next steps

- U37 is documented, not measured.
- Timing and behaviour on Power Systems' real case are unknown; the 2.0 s is the 39-bus example's.
- Open for Power Systems: the same lines in every city's copy, El Paso's basis, and whether the base power factor is intended.
- Runbook step 4 should mention `--allow-placeholder` for a placeholder mapping.

## Self-Check: PASSED

The record passes its safety check (no five or six digit number, branch key, case or script file name or user path), the doc and rehearsal tests pass (33 passed, 1 owner-local skip), and the register rows U35 to U38 are all still in place.
