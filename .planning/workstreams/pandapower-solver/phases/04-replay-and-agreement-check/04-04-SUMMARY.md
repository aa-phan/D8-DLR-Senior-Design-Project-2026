---
phase: 04-replay-and-agreement-check
plan: 04
subsystem: real-corpus-replay
tags: [pandapower, replay, agreement-check, owner-export, ci-leak-scan]
status: complete

requires:
  - phase: 04 plans 01 to 03 (pandapower-solver)
    provides: the owner's export SQL, strict ingest, agreement rules and gate, the ingest and replay commands
provides:
  - backend/tests/pandapower_replay_output_test.py - the replay command's CI output scanned for planted private-looking values, the scan shown to fire (task 1, commit c3b109f)
  - backend/tests/pandapower_replay_owner_test.py - owner-local test of the real snapshot's replay (skips without private data; fails instead when DLR_PANDAPOWER_REQUIRE_RECORDS=1)
  - 04-REPLAY-RECORD.md - the counts-only record of the real export and replay (commit 72ea91a)
affects: [Phase 5 (OPS-03 owner decision: AGR-02 evidence now exists), Phase 4 verification]

requirements-completed: [AGR-01, AGR-03, AGR-04]
---

# Phase 4 Plan 04: Real-corpus replay Summary

The owner's read-only export (recorded PSS/E runs, pattern `psse-202611%`) was ingested and replayed on pandapower on 2026-11-21. Verdict: **pass**. The record is `04-REPLAY-RECORD.md`; nothing private is in it.

## Result (counts only)

- 19 recorded runs ingested (ok 19, fallback 0, failed 0); all 19 match the local mapping hash and the session case hash.
- 19 replayed, 19 passed, 0 failed, 0 borderline, 0 runs with disagreeing results.
- 3895 pairs, 362 margin comparisons and 76 dispatch comparisons compared.
- Non-empty comparisons: thermal_overload 114, voltage_high 608, voltage_low 0, non_convergence 0.
- Not exercised by the recorded runs: voltage_low, non_convergence.
- Owner-local test: 1 passed, 0 skipped (672 s).
- `backend/private_leak_scan.py` exit 0 with no finding lines.

## Tasks

1. CI output leak test with planted identifiers (done 2026-11-20, `c3b109f`).
2. Owner action: Aaron ran the export SQL and sent the CSV (done; file received 2026-11-21, stored git-ignored under `data/private/pandapower/incoming/`).
3. Ingest, replay, owner-local test, record (done 2026-11-21, `72ea91a`).

## Limits to keep in the wording

- All 19 runs share one mapping, one case and one job version: agreement on one configuration family over one recorded period.
- Low-voltage and non-convergence agreement is untested on real data (the recorded runs never produced those cases). The deliberate-mismatch matrix covers that the check can fail, not that real runs agree.
- The export file is named `psse_runs_202611.csv`, not the name the plan assumed; the ingest command takes the path as an argument, so nothing depended on the name.
- Not an hourly cloud run. Phase 5 is unbuilt.

## Deviations

None to code or rules. No rule was changed to reach the verdict.

## Self-check

Record has exactly one `Verdict:` line (`pass`); only the record file was committed for task 3; the export, snapshot and detailed report stay under the git-ignored `data/private/`.
