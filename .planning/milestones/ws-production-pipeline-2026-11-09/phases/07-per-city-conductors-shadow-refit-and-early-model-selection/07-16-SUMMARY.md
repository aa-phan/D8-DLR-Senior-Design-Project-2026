---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 16
subsystem: early-model-selection-final-record
tags: [confirmation-protocol, v4-read2, sel-04, decision-record, owner-decision]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: plan 07-15 read-2 evidence (headline and live-system check) and the no-winner outcome; plan 07-13 read-1 decision record
provides:
  - read2_results.md (plain-English read-2 results for the owner)
  - decision_record.md Read 2 (2026-11-08) section with the owner's final SEL-04 decision verbatim
  - final v4 outcome recorded in ml-modeling and production-pipeline STATE.md
affects: [07-17, Phase 8]

requirements-completed: [SEL-04]

actuals:
  tokens: 9000
  tasks: 3
  commits: 2
plan_head_before: a6776ba4d67b537689e771563a3f0ffa5e6b27cf
plan_head_after: 8016f2a18bbc76fdf4e221637016a29ecf410fa8

tech-stack:
  added: []
  patterns:
    - "Owner decisions recorded verbatim with name as typed and UTC date; departures from the signed rule labelled, never entered as a rule pick"

key-files:
  created:
    - docs/data-science/decisions/v4_selection/read2_results.md
  modified:
    - docs/data-science/decisions/v4_selection/decision_record.md
    - .planning/workstreams/ml-modeling/STATE.md
    - .planning/workstreams/production-pipeline/STATE.md

key-decisions:
  - "Owner replied `rule-outcome-keep-cooling, aaphan` (2026-11-08T01:29Z): accepts the signed O3 outcome after read 2 (no shadow model, no day-ahead pick under the rule, interim G6 `ml` keeps running, 2026-11-24 stays retired, any later evaluation needs a new signed protocol) and keeps the labelled engineering selection of `ml_cooling_corrected` for the day-ahead output in Phase 8"
  - "The `ml_cooling_corrected` selection is recorded as a continuing labelled departure from the rule's outcome, never as a rule pick or validated"

patterns-established: []

coverage:
  - id: D1
    description: "Read-2 results written in plain English from the committed read-2 reports only, stating read 2 re-grades read 1's rows and is not independent"
    requirement: SEL-04
    verification:
      - kind: command
        ref: "test -s read2_results.md; grep -c 'In plain English' prints 1 or more; grep -c 'not independent' prints 1 or more"
        status: pass
    human_judgment: false
  - id: D2
    description: "Owner's final SEL-04 decision recorded verbatim with name and UTC date, as a labelled departure"
    requirement: SEL-04
    verification:
      - kind: command
        ref: "grep -c 'Recorded by: the executor (07-16)' decision_record.md prints 1; grep -c 'Read 2' prints 1 or more"
        status: pass
    human_judgment: true
  - id: D3
    description: "ml-modeling and production STATE.md record the final v4 outcome; the evaluation item is closed"
    requirement: SEL-04
    verification:
      - kind: command
        ref: "git show --stat 8016f2a lists both STATE.md files and decision_record.md"
        status: pass
    human_judgment: false

duration: 2 sessions (results write-up, then the owner's decision)
completed: 2026-11-08
status: complete
---

# Phase 7 Plan 16: Final SEL-04 Decision Under Protocol v4 Summary

**Read 2 also named no winner, so the signed O3 outcome applies (no shadow model; interim G6 `ml` keeps running; 2026-11-24 stays retired), and the owner recorded it while keeping `ml_cooling_corrected` as the labelled engineering selection for the day-ahead output in Phase 8.**

## Performance

- **Tasks:** 3 (Task 1 results in plain English, Task 2 the blocking-human decision, Task 3 the record)
- **Completed:** 2026-11-08
- **Commits:** 2 (measured: `git rev-list --count a6776ba..HEAD` at the time of the last task commit)

## Accomplishments

- **Task 1 (`182f260`).** `read2_results.md` opens in plain English and copies every figure from the committed read-2 reports: pooled bar 28.01 A; `ml_cooling_corrected` 12.12 A (Holm-adjusted p 0.2930), `ml_wind_corrected` 3.97 A (0.7643), `reference_ml_refit_24h` -24.19 A (0.7643); no veto; no candidate qualifies. It states plainly that read 2 re-grades read 1's rows (100 of 128 slots per city already scored) and is not an independent test, and keeps the live-system check separate.
- **Task 2 (checkpoint, resolved).** The owner replied `rule-outcome-keep-cooling, aaphan` at 2026-11-08T01:29Z (UTC), no further wording.
- **Task 3 (`8016f2a`).** The Read 2 (2026-11-08) section of `decision_record.md` records the chosen option, the final rule outcome (no shadow model; O3 applies), the continuing labelled engineering selection of `ml_cooling_corrected` for Phase 8, the owner's words verbatim, "Signed by: aaphan, 2026-11-08" and "Recorded by: the executor (07-16)". A factual note from the read-2 report (not the owner's words) records the live-system check, which never decides: `ml_cooling_corrected` -0.01 A vs the plain forecast (2 of 4 cities), `ml_wind_corrected` +0.85 A. Dated lines were added to ml-modeling STATE.md (final v4 outcome; the evaluation item is closed) and production STATE.md Decisions.
- No FRESH read was run, no further read was scheduled, nothing was pushed and no Supabase call was made.

## Task Commits

1. **Task 1: read-2 results in plain English** - `182f260` (docs)
2. **Task 2: owner records the final decision** - checkpoint, no commit (reply recorded in Task 3)
3. **Task 3: final decision in the record and both STATE files** - `8016f2a` (docs)

## Deviations from Plan

None - plan executed exactly as written. The owner's reply fell on the plan's "other / different decision" path (a labelled departure), as the plan anticipated.

## Issues Encountered

None. Commits were made on `main`, which the project config allows (`git.allow_default_branch_commits: true`), matching earlier Phase 7 plans.

## Known Stubs

None.

## Threat Flags

None. Documentation-only changes. T-07-32 mitigated: verbatim words, name and UTC date recorded, departure labelled.

## Notes for Later Plans

- Phase 8 serves `ml_cooling_corrected` as the day-ahead output on the owner's engineering selection, which is not a rule pick and is not "validated". Any later evaluation needs a new signed protocol.
- Plan 07-17 (go/no-go) keeps the interim G6 method `ml` under D-15.

## Self-Check: PASSED

- Files found: `read2_results.md`, `decision_record.md` (Read 2 section), both STATE.md files.
- Commits found in history: `182f260`, `8016f2a`.
