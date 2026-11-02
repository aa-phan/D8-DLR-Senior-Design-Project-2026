---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 13
subsystem: model-selection
tags: [sel-04, v4-read1, decision-record, owner-decision, g6, day-ahead]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: 07-12 read-1 evidence (headline reconstructed frames and live-system check)
provides:
  - read1_results.md, the read-1 results in plain English for the owner
  - decision_record.md Read 1 section signed by the owner (aaphan, 2026-11-02 UTC)
  - dated Decisions lines in both ml-modeling and production-pipeline STATE.md
affects: [07-15 read 2, 07-16, 07-17 go/no-go, new day-ahead phase after Phase 7]

actuals:
  tokens: 5300
  tasks: 3
  commits: 2
plan_head_before: d0cd640f2e57b793541fdce363ce06bd3f9cd1e7
plan_head_after: 627b789

tech-stack:
  added: []
  patterns:
    - "Owner engineering choice recorded as a labelled departure, never as a rule pick (precedent: 2026-10-05 ml_wind_corrected tie-break)"

key-files:
  created:
    - docs/data-science/decisions/v4_selection/read1_results.md
    - docs/data-science/decisions/v4_selection/decision_record.md
  modified:
    - .planning/workstreams/ml-modeling/STATE.md
    - .planning/workstreams/production-pipeline/STATE.md

key-decisions:
  - "Rule's outcome accepted: no pick under signed v4 (best read-1 benefit 11.89 A vs the 27.86 A bar, Holm p 0.3624)"
  - "Interim G6 stays ml retrained on projected wind (B2, D-14, models commit e0a00a9), checked under D-15 at the go/no-go (07-17)"
  - "Owner selects ml_cooling_corrected for day-ahead as a labelled engineering choice, outside the signed rule's outcome (Departure: yes); not a rule pick"
  - "Read 2 (D-08) still runs at or after 2026-11-08T00:00:00Z (07-15) and is reported either way; a rule pick of cooling there would supersede the engineering label"
  - "Serving the day-ahead forecast is a new roadmap phase after Phase 7 (added by the orchestrator), not part of Phase 7"

patterns-established:
  - "Exploratory, non-FRESH evidence may support an owner engineering choice but is labelled as such and never enters the rule"

requirements-completed: []

coverage:
  - id: D1
    description: "Read-1 results document in plain English, figures copied from committed reports, live-system check never pooled"
    requirement: "SEL-04"
    verification:
      - kind: other
        ref: "grep -m1 '^## ' docs/data-science/decisions/v4_selection/read1_results.md; grep -c 'never pooled' (both met in Task 1, commit 27d7269)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Owner's SEL-04 decision recorded verbatim with name as typed, UTC date, departure labelled, executor as recorder only"
    requirement: "SEL-04"
    verification:
      - kind: other
        ref: "grep -c 'Signed by:' decision_record.md (1); grep -c 'Recorded by: the executor (07-13)' (1); grep -c 'read 1' ml-modeling/STATE.md (6)"
        status: pass
    human_judgment: true
    rationale: "The decision is the owner's; only the owner can confirm the record states it as intended"

duration: 2h (across the checkpoint)
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 13: Owner's SEL-04 decision after read 1 Summary

**Read 1 named no pick under the signed v4 rule; the owner accepted that outcome, kept `ml` (B2-fixed) as interim G6, and separately chose `ml_cooling_corrected` for a day-ahead output as a labelled engineering choice, not a rule pick.**

## Performance

- **Tasks:** 3 of 3 (Task 2 was the blocking-human decision checkpoint, answered by the owner)
- **Own commits:** 2 (`27d7269` results and draft, `627b789` decision). The measured range `d0cd640..HEAD` also holds six commits from other work (07-14, an orchestrator tracking commit, an exploratory-analysis commit), so `commits: 2` counts this plan's own commits only.

## Accomplishments

- `read1_results.md` opens with a plain-English section, then reports the headline, the secondary (or the equal-by-construction statement), the live-system check in its own section ("never pooled"), data gaps and provenance, with every figure copied from the committed reports.
- `decision_record.md` Read 1 section holds the owner's words verbatim, "Signed by: aaphan, 2026-11-02 (UTC)" and "Recorded by: the executor (07-13)".
- The departure is labelled verbatim: "Departure: yes — owner engineering selection outside the signed rule's outcome". The rule's outcome is accepted unchanged; the departure is only the owner's additional day-ahead selection.
- Supporting evidence is cited and labelled exploratory, not pre-registered, non-FRESH: the 24 h vs 60 min horizon comparison (cooling beats reference by +26.3 A and raw by +25.8 A, Holm p 0.001, in all 4 cities; cost of 24 h vs 60-minute `ml` +23.1 A [18.0, 28.3], about 1.7% of rating) and the `ml` vs naive comparison (+3.9 A pooled [3.1, 4.7], significant in all 4 cities over 2026-01-01..09-29; not significant on the 2-week September replay).
- Dated Decisions lines were added to ml-modeling STATE.md (contains "read 1") and production-pipeline STATE.md.

## Task Commits

1. **Task 1: Read-1 results and decision-record draft** - `27d7269`
2. **Task 2: Owner records the SEL-04 decision** - checkpoint, resolved by the owner's replies (no commit)
3. **Task 3: Record the decision in the record and both STATE files** - `627b789`

## Deviations from Plan

None in code or scope. Two points worth noting:

- The decision is richer than the plan's three options: the owner chose `rule-outcome-ml` and then added a labelled day-ahead engineering selection. The plan's "other" option covers a departure from the rule, so it was recorded as one and kept separate from the rule's no-pick outcome.
- The plan's blocker line ("Wiring <model> into the live path is a follow-on phase") applies when the rule picks a model. No model was picked, so no Blockers line was added; the day-ahead serving work is recorded in the Decisions lines and becomes a new roadmap phase added by the orchestrator (ROADMAP phases not edited here).

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None. T-07-28 (repudiation) is mitigated: words verbatim, name as typed, UTC date, executor as recorder only, departure labelled.

## Next

- 07-15: read 2 at or after 2026-11-08T00:00:00Z under the same rules, reported either way.
- 07-17: go/no-go, where interim G6 (`ml`, B2-fixed) is checked under D-15.
- SEL-04 stays open until read 2; it is not marked complete here.

## Self-Check: PASSED

- FOUND: read1_results.md, decision_record.md
- FOUND commits: 27d7269, 627b789
