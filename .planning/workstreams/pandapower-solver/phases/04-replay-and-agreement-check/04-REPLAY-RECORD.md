# Phase 4 replay record (counts and words only)

Recorded 2026-11-21. Source: the owner's read-only export of recorded PSS/E runs, ingested and replayed on the pandapower solver on the owner's machine. No private value appears here; the export, snapshot and detailed report stay under `data/private/pandapower/` (git-ignored).

Verdict: pass

## Ingest

- ingest: ok, snapshot written
- runs: 19 (ok 19, fallback 0, failed 0)
- rows: dispatch 76, margins 76, contingencies 3895
- distinct mapping hashes 1, case hashes 1, job versions 1
- runs matching the local mapping: 19 of 19
- runs matching the session case: 19 of 19

## Replay

- runs replayed 19; passed 19; failed 0
- distinct configurations: 18
- pairs compared: 3895
- margin comparisons: 362; dispatch comparisons: 76
- borderline: 0
- runs with disagreeing results: 0
- non-empty comparisons: thermal_overload 114, voltage_high 608, voltage_low 0, non_convergence 0
- not exercised: voltage_low, non_convergence

The owner-local test (`pandapower_replay_owner_test.py`, records required) ran with 1 passed and nothing skipped.

## What this does and does not show

- The pandapower solver reproduced the recorded PSS/E results for all 19 recorded runs under the agreement rules as built; no rule was changed to reach this.
- Thermal overload and high-voltage agreement are exercised by real comparisons. Low-voltage and non-convergence agreement are not: the recorded runs never produced those cases, so no claim is made for them.
- All 19 runs share one mapping, one case and one job version, so this is agreement on one configuration family over one recorded period, not across mappings.
- This is not an hourly cloud run. Phase 5 (workflow, dry run, soak) is not built.
