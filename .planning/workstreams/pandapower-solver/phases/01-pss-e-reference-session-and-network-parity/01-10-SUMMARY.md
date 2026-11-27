---
phase: 01-pss-e-reference-session-and-network-parity
plan: 10
subsystem: testing
tags: [pandapower, psse, real-session, net-02, net-03, switched-shunt, leak-guard]
status: complete

requires:
  - phase: 01-pss-e-reference-session-and-network-parity
    provides: the session script and bundle (01-02 to 01-06), parity and convert (01-07), solve, scaling and compare (01-08), ingest and check commands (01-09)
provides:
  - the first real PSS/E 36.4 session, ingested and checked (01-SESSION-RECORD.md, counts only)
  - parity with 0 differences in all 11 categories on the real export
  - NET-03 passing for all four cities, in both the algorithm run and the injected-snapshot run
  - switched-shunt reading, building and step control; local voltage-control transformer building; orientation-aware branch join
affects: [01-11, 02-07, 04]

plan_head_before: 78b8c58
plan_head_after: 536a8a5
actuals:
  tasks: 3
  commits: 8

key-decisions:
  - "Switched shunts under discrete voltage control (MODSW 1, ADJM 0) are built at their initial setting and stepped by the solve until the bus is inside the band (owner approved step control after the fixed-setting comparison failed)"
  - "A local voltage-control transformer is built at its initial tap; other control modes and remote buses are refused (no tap moved in any city)"
  - "No tolerance, network parameter or registry entry was changed to reach the pass (R-3, D-12)"
  - "Leak-guard false positives were allow-listed by file path and hash only, in two owner-approved steps (17 files, then 4 files); no private value is in the list"

requirements-completed: [PSE-01, PSE-02, PSE-03, NET-01, NET-02, NET-03]

coverage:
  - id: D1
    description: "A real session on the licensed PSS/E laptop produced a complete zip (135 members) that ingests and verifies against its manifest"
    requirement: "PSE-01"
    verification:
      - kind: manual_procedural
        ref: "01-SESSION-RECORD.md, Session table"
        status: pass
    human_judgment: true
  - id: D2
    description: "The real export parses and builds, and parity against the converted network has 0 differences in all 11 categories"
    requirement: "NET-02"
    verification:
      - kind: manual_procedural
        ref: "01-SESSION-RECORD.md, Parity"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_raw_test.py, pandapower_network_test.py, pandapower_parity_test.py"
        status: pass
    human_judgment: true
  - id: D3
    description: "Pandapower agrees with PSS/E within 0.01 pu on voltage and max(2%, 2 MVA) on flow in all four cities, both runs, nothing failed, comparisons complete"
    requirement: "NET-03"
    verification:
      - kind: manual_procedural
        ref: "01-SESSION-RECORD.md, NET-03"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_shunt_control_test.py and pandapower_compare_test.py (synthetic cases for the step control and the orientation join)"
        status: pass
    human_judgment: true
  - id: D4
    description: "Owner decision on the parity and NET-03 verdicts"
    requirement: "NET-03"
    verification:
      - kind: manual_procedural
        ref: "Task 3 checkpoint, resume word"
        status: pass
    human_judgment: true
    rationale: "The owner typed approved after the final result (2026-11-20)."

completed: 2026-11-20
---

# Phase 1 Plan 10: First real PSS/E session Summary

**The real 39-bus network from PSS/E 36.4 now builds in pandapower with 0 parity differences, and pandapower agrees with PSS/E's own solved answers for all four cities once the two switched shunts step the way PSS/E steps them.**

Counts, versions and pass or fail only; the detail is in `01-SESSION-RECORD.md`.

## What happened

1. The teammate ran the laptop session three times. Run 1 was partial (the RAW export call failed), run 2 was a scaling-only rerun, run 3 was complete (135 members).
2. The real file needed fixes the synthetic data had not shown: the export call takes the version as text, the revision line sits after `@!` comment lines, and the file has switched shunts and a local voltage-control transformer.
3. The first comparison, with shunts held fixed (the owner's first choice), failed in every city on reactive power and voltage. PSS/E's own pre-solve and solved cases showed both shunts change step in all four cities and no tap moves.
4. The owner approved step control. A rule of one level per pass, repeated until nothing moves, reproduced PSS/E's final steps in all four cities.
5. Two transformers that PSS/E lists from the opposite end were joined by orientation, which made every comparison complete.
6. Three tests that only fail on Windows were made platform-aware.

## Verdicts

- Parity: 0 differences in 11 categories.
- NET-03: pass, 4 of 4 cities, both runs; buses 39 compared and 0 failed, flows 138 compared and 0 failed per city.
- `enforce_q_lims` is on; 0 deviations from D-14.

## Task Commits

`432bb24`, `fd83eec`, `fc1f1ec`, `fc7ee7a`, `264e700`, `ba65bfa`, `536a8a5`, plus this record.

## Verification

- Full test pass on the final tree before the last test-only commit: 303 passed, 4 failed. All 4 were Windows-only (path separator, 0o600 file mode twice, backslash zip member) and are fixed in `536a8a5`; the three affected files then passed (the ingest file as 28 passed, 1 skipped on Windows).
- The leak scan exits 0.
- The database tier was not part of this plan.

## Deviations from Plan

- The plan expected parser changes to be small; the real file needed the switched-shunt section, step control in the solve and an orientation join (Rule 2, all with synthetic tests, all recorded above).
- Plan 01-10 Task 3 asked for "approved"; an earlier message ("commit it after tests pass") was not taken as that. The word came on 2026-11-20 after the final test result.

## Open

- Teammate cleanup: delete all three session zips from the laptop Desktop, the mapping copy and empty the Recycle Bin.
- Owner cleanup: remove the mapping copies from Downloads and chat.
- The converted network's publication is the next plan (01-11, D-06).
