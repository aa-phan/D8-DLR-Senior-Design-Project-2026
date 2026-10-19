---
phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan
plan: 03
subsystem: ml-audit
tags: [scipy, bootstrap, block-bootstrap, pandas, pytest, forecast-experiment-audit]

requires:
  - phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan (plan 01)
    provides: "Measured ABLATION (784 val rows/corridor) and FRESH (0 rows/corridor) bases"
provides:
  - "Paired block bootstrap reducing to i.i.d. at block length one, with a method-matched percentile comparator and a block-length sensitivity sweep (1/4/8/28)"
  - "Real ABLATION-basis out-of-sample comparison for both corridors, fitted arms refit on TRAIN rows alone"
  - "Published `## Strengthened comparison (D-02)` section: Austin-Corpus Christi replicates the frozen verdict; Midland-El Paso CONTRADICTS it (different winner, cooling-vs-refit margin no longer distinguishable from zero, wind-vs-refit margin fragile across block lengths)"
  - "Fresh chronological period formally reserved (starts 2026-09-30, 56-row/14-day minimum) for any future confirmation claim"
affects: [04-04, 04-05, 04-06]

actuals:
  tokens: 68000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Block bootstrap at block length 1 is required to reduce to the harness's own i.i.d. method, proving the stricter method is a strict generalization rather than a different comparator"

key-files:
  created: []
  modified:
    - backend/forecast_experiment_audit.py
    - backend/tests/forecast_experiment_audit_test.py
    - docs/data-science/decisions/forecast_correction_followup_audit.md

key-decisions:
  - "Human checkpoint (Task 2.5) approved the strongest framing for Midland: 'contradicted,' not 'unresolved.' The frozen record's winner (ml_cooling_corrected) does not replicate — a different candidate (ml_wind_corrected) now leads, and cooling's margin over the refit model is statistically indistinguishable from zero where the frozen record reported a distinguishable edge."
  - "Fitted arms (wind/cooling/refit) refit on ABLATION TRAIN rows alone, not train+val as the frozen harness's own test-scoring convention does — the deliberate difference that makes this a genuinely out-of-sample replication for exactly the three candidates under audit, at the cost of a smaller fit sample."
  - "The wind-vs-refit margin at Midland is reported as fragile, not just 'excludes zero': it flips from excluding zero (block length 1, CI [0.254, 16.641]) to not excluding zero (block lengths 4/8/28) — the frozen record's own BCa interval for this margin was already barely excluding zero (CI low 0.036) before accounting for serial correlation."

patterns-established:
  - "Dispositions table pattern (one row per locked-decision bullet, disposition + citation) carried forward from Plan 04-02's D-01 table into D-02 -- future plans (04-04/04-05) should use the same closing-table shape for their own CONTEXT bullets."

requirements-completed: [D-02]

coverage:
  - id: D1
    description: "Paired block bootstrap reduces to i.i.d. at block length 1 and produces a block-length sensitivity sweep with a stability verdict per margin"
    requirement: "D-02"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_audit_test.py (block-bootstrap reduction + sensitivity tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Real ABLATION-basis comparison measured for both corridors, fitted arms genuinely held out (fit timestamp strictly before scored timestamp, assertion-enforced)"
    requirement: "D-02"
    verification:
      - kind: integration
        ref: "data/experiment/audit_ablation_report_AUSTIN_CORPUS_CHRISTI.json, audit_ablation_report_MIDLAND_EL_PASO.json (ablation_guard_passed_fit/scored: true, max_fit_timestamp < min_scored_timestamp)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Strengthened comparison section published with the human-approved framing: Austin replicates, Midland contradicted"
    verification:
      - kind: other
        ref: "D02_SECTION_OK / D02_NUMBERS_TRANSCRIBED_OK / DOC_ONLY_TASK_OK verify scripts in 04-03-PLAN.md Task 3"
        status: pass
    human_judgment: true
    rationale: "The framing of how strongly to state Midland's disagreement was explicitly reserved for human judgment by the plan's checkpoint, not an executor's call — now resolved by the approved checkpoint decision."

duration: 195min
completed: 2026-09-30
status: complete
---

# Phase 04, Plan 03: Strengthened Statistical Comparison Summary

**Block-bootstrap comparison with block-length sensitivity on real ABLATION data reveals the frozen record's verdict replicates at Austin-Corpus Christi but is CONTRADICTED at Midland-El Paso — a different winner, a statistically indistinguishable margin where the frozen record claimed one, and a fragile wind-vs-refit result that flips across block lengths.**

## Performance

- **Duration:** 195 min (includes a human-verify checkpoint pause)
- **Started:** 2026-09-30
- **Completed:** 2026-09-30
- **Tasks:** 3 (2 auto + 1 checkpoint-gated write-up)
- **Files modified:** 3

## Accomplishments
- Built a paired block bootstrap (moving blocks, lengths 1/4/8/28) proven to reduce exactly to the harness's own i.i.d. percentile method at block length 1, plus a method-matched percentile comparator distinct from the frozen record's BCa method.
- Measured the full pairwise comparison (every real candidate against persistence, raw_forecast, ml_wind_corrected, and reference_ml_refit_24h) on real ABLATION-basis out-of-sample rows at both corridors, with fitted arms refit on TRAIN rows alone and genuinely held out (assertion-enforced).
- Human checkpoint reviewed the measured numbers and approved the strongest framing: Austin-Corpus Christi **replicates** the frozen verdict (ml_cooling_corrected wins, stable across all block lengths); Midland-El Paso **contradicts** it — ml_wind_corrected now leads, cooling's margin over the refit model is no longer distinguishable from zero, and the wind-vs-refit margin itself is fragile (excludes zero only at block length 1).
- Published the full `## Strengthened comparison (D-02)` section (1,770 words, 4 tables, 7 subsections) with every number transcribed from the measured JSON reports, passing all three of the plan's verify scripts.
- Formally reserved a fresh chronological period (starts 2026-09-30, minimum 56 rows / 14 days) for any future confirmation claim, disjoint from Phase 3's train/val/test ranges by the Plan 04-01 frozen-window guard.

## Task Commits

Each task was committed atomically:

1. **Task 1: Paired block bootstrap, method-matched comparator, block-length sensitivity sweep** - `a805abe` (feat)
2. **Task 2: Measure the comparison on real ABLATION-basis out-of-sample rows** - `88e4b4d` (feat)
3. **Task 2.5 (checkpoint): Read the replication's numbers before its framing is written** - human-verify, approved framing: "contradicted" for Midland
4. **Task 3: Publish the strengthened comparison, including the parts that weaken the frozen verdict** - `549d789` (docs)

## Files Created/Modified
- `backend/forecast_experiment_audit.py` - `paired_block_bootstrap_margin`, `block_length_sensitivity`, `pairwise_margin_table`, `ablation_basis_report`
- `backend/tests/forecast_experiment_audit_test.py` - Tests for block-bootstrap reduction to i.i.d., sensitivity sweep shape, and report structure
- `docs/data-science/decisions/forecast_correction_followup_audit.md` - `## Strengthened comparison (D-02)` section fully written

## Decisions Made
- Framing for Midland: "contradicted," per explicit human approval at the Task 2.5 checkpoint — the strongest, most direct statement the measured numbers support, not a softer "unresolved."
- Fitted arms refit on TRAIN rows alone (not train+val) — the plan's deliberate, documented difference from the frozen harness's test-scoring convention, trading fit-sample size for genuine held-out-ness.
- The wind-vs-refit margin fragility is reported by name and by the exact block lengths at which it flips, not folded silently into the stability verdict.

## Deviations from Plan

None - plan executed exactly as written. (The executor that ran Tasks 1-2 halted correctly at the Task 2.5 checkpoint per its non-autonomous frontmatter; Task 3's write-up was completed by the orchestrator after the checkpoint was approved, since the worktree-isolated executor agent could not be resumed programmatically — see Issues Encountered.)

## Issues Encountered
- The executor agent's isolated worktree could not be resumed programmatically after the Task 2.5 checkpoint (harness safety guard: "pin-is-protected-checkout"), the same limitation encountered at Plan 04-01's checkpoint. Task 3 (the write-up) was completed directly in the worktree by the orchestrator after receiving the user's approved framing, verified against all three of the plan's own verify scripts, then merged back to `main` in the normal post-wave flow.
- Confirmed the plan's own `##+ ` section-boundary regex in its verify scripts is unsatisfiable as literally written for a document with `###` subsections (same defect Plan 04-02 already flagged in `.planning/WINDOWS.md`, phase 04, open). Used the evidently-intended corrected boundary regex (`##(?!#) `) to verify substantive intent; all three checks (`D02_SECTION_OK`, `D02_NUMBERS_TRANSCRIBED_OK`, `DOC_ONLY_TASK_OK`) pass under the corrected regex. No PLAN.md edit made (out of this plan's file scope).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
Plan 04-04 can read the `## Strengthened comparison (D-02)` section directly: Austin-Corpus Christi's comparison is corroborated and stable; Midland-El Paso's result is contradicted and should be treated with that caveat when computing overrating/conservative-rating statistics in 04-04. No blockers.

---
*Phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan*
*Completed: 2026-09-30*
