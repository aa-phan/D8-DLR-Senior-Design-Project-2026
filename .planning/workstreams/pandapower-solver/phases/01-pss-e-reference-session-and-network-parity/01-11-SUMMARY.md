---
phase: 01-pss-e-reference-session-and-network-parity
plan: 11
subsystem: decisions
tags: [pandapower, network-data, leak-guard, d-06]
status: complete

requires:
  - phase: 01-pss-e-reference-session-and-network-parity
    provides: the approved real session, parity with 0 differences, NET-03 passing for all four cities, and the D-06 evidence (01-07, 01-10)
provides:
  - the D-06 decision, recorded: the converted 39-bus network stays private (docs/data-science/decisions/pandapower_network_data_decision.md)
affects: [05]

key-decisions:
  - "D-06: keep the converted network private and give the hourly workflow a GitHub secret created from the private converted copy (owner, 2026-11-20 UTC)"
  - "No network file, pin or allow-list entry was committed; nothing private entered the repository"

requirements-completed: [PSE-04, NET-02]

coverage:
  - id: D1
    description: "The owner decided D-06 at a blocking checkpoint with the counts-only evidence in front of them"
    requirement: "PSE-04"
    verification:
      - kind: manual_procedural
        ref: "owner answer 'keep private' at the plan checkpoint, 2026-11-20"
        status: pass
    human_judgment: true
  - id: D2
    description: "The decision record states the evidence as counts only, the licence status (not established), that publication would be one-way, and what the hourly workflow does next"
    requirement: "NET-02"
    verification:
      - kind: manual_procedural
        ref: "docs/data-science/decisions/pandapower_network_data_decision.md"
        status: pass
  - id: D3
    description: "Nothing private is committed: the leak scan is clean on the staged record, and no data/pandapower files, .sha256 pin or private_leak_allow.json were created"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/private_leak_scan.py --staged exits 0"
        status: pass

completed: 2026-11-20
---

# Plan 01-11 summary: the network data decision

**The owner chose keep-private. The converted 39-bus network stays on the owner's machine and reaches the hourly workflow as a GitHub secret.**

## What was decided

At the blocking checkpoint the owner was shown the counts-only evidence: parity with 0 differences in 11 categories against the real export, a converted copy of 25,191 bytes (3,231 gzipped, under the 48 KB secret limit), the export differing from pandapower's public case (12 transformers and 34 lines against 11 and 35, 19 loads against 21), and an unestablished licence for the PSS/E example data. The owner answered `keep-private`. That is reversible; publication would not have been.

## What was written

`docs/data-science/decisions/pandapower_network_data_decision.md` records the decision, its date, the evidence, the licence status, the consequences (including the negative ones), the publication alternative and why it was not chosen, and what the hourly workflow does next.

Because the decision was keep-private, none of `data/pandapower/network_39bus.json`, its `.sha256` pin, `backend/private_leak_allow.json` or the guard test was created. The plan's own rule for this branch is that only the decision record is committed.

## Deviations from plan

None.

## Next

Phase 2 plan 02-07 and Phase 3 verification are the remaining items before the agreement check. Phase 1 has no plan left; its verification is the orchestrator's.
