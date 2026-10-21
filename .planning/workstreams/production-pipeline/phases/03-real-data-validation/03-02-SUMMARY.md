---
phase: 03-real-data-validation
plan: 02
subsystem: testing
tags: [validation, backfill, real-data, manifest, completeness, ml-forecast, val-01, val-02]

requires:
  - phase: 03-real-data-validation
    provides: "03-01: backfill_trace/1 trace (--trace-path), completeness and manifest subcommands of real_data_validation.py"
  - phase: 02-data-cleaning
    provides: "data_cleaning.clean_history(history, as_of=end) in city_pipeline between read_history and forecast_ampacity"
provides:
  - "A complete real backfill 2026-09-08T00:00Z..2026-09-28T23:00Z (504 hourly steps x 4 cities, forecast method ml, composed providers) through the Phase 2 cleaned pipeline, held as git-ignored files in the main checkout"
  - "manifest.json: window, warm-up, exact backfill argv and owner command, sha256/size of archive, trace, log and console, archive rows per city, sha256 of the 8 model files, main checkout HEAD"
  - "run_completeness.csv: per-city step completeness (expected 504, missing 0 for every city)"
affects: [03-04 real-data report, 03-05 go/no-go decision, 04 DB-03 archive load]

actuals:
  tokens: 950
  tasks: 3
  commits: 1

plan_head_before: 175b32bc443b4128195dcac70b3d96a60c653a1a
plan_head_after: fadf9b0fca7bf6d853dafaf5fbec46c4cf7ce5f8

tech-stack:
  added: []
  patterns:
    - "Raw run data stays git-ignored under data/historical/; only a hash/count manifest and a completeness table cross into git"
    - "The owner loads provider keys via python-dotenv in a python -c wrapper; the executor never reads or loads the key file and proves readiness offline (find_spec, model loads, pytest)"

key-files:
  created:
    - docs/data-science/decisions/real_data_validation/manifest.json
    - docs/data-science/decisions/real_data_validation/run_completeness.csv
  modified: []

key-decisions:
  - "Window kept exactly as planned (2026-09-08..09-28, 21 days): 168 h warm-up, scored window 2026-09-15T00:00Z..2026-09-28T23:00Z (14 days)"
  - "Smoke completeness is printed and checked but not committed (written to a temp directory); only the full-run table is committed"

requirements-completed: [VAL-01, VAL-02]

coverage:
  - id: D1
    description: "A real 21-day backfill (14 scored days after a 7-day warm-up), all four cities, ml forecast, run through the cleaned pipeline, complete for every (city, step)"
    requirement: "VAL-01"
    verification:
      - kind: other
        ref: "python backend/real_data_validation.py completeness (full run): expected_steps 504, missing 0 for AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO; COMPLETE_OK"
        status: pass
    human_judgment: false
  - id: D2
    description: "Committed manifest pinning window, argv, owner command, file hashes and sizes, per-city row counts, model hashes and HEAD for Phase 4's DB-03 load"
    requirement: "VAL-01"
    verification:
      - kind: other
        ref: "plan Task 3 verify command: MANIFEST_OK (schema, non-null model hashes, 504 steps, method ml)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The run actually used the cleaned pipeline with the ml forecast and a loaded anomaly model on every step (trace sanity)"
    requirement: "VAL-02"
    verification:
      - kind: other
        ref: "trace scan of 2016 records: 0 with forecast_method other than ml, 0 with null pipeline.detector_model, 0 exhausted, 0 errors"
        status: pass
    human_judgment: false

duration: 336min wall (includes the owner's smoke and full backfill; executor-active time is a few minutes)
completed: 2026-10-21
status: complete
---

# Phase 3 Plan 02: Real-data backfill record Summary

**A complete 21-day, four-city real backfill (504 hourly steps per city, ml forecast, composed providers, Phase 2 cleaning) is proven gap-free (missing 0 everywhere) and pinned for Phase 4 by a committed manifest of sha256 hashes, row counts, model hashes and the exact owner command.**

## Performance

- **Duration:** about 5 h 36 min wall clock, dominated by the owner running the backfill
- **Started:** 2026-10-20T23:28Z
- **Completed:** 2026-10-21T05:04Z
- **Tasks:** 3 (Task 1 read-only preflight, Task 2 owner action, Task 3 committed)
- **Files modified:** 2 committed (manifest.json, run_completeness.csv)

## Window

- Start 2026-09-08T00:00:00Z, end 2026-09-28T23:00:00Z, step 1 h: 504 steps per city, 2016 city-steps.
- Warm-up 168 h (archive starts empty). Scored window: 2026-09-15T00:00:00Z to 2026-09-28T23:00:00Z (14 days).
- Entirely before 2026-09-29T00:00Z (anti-peeking cutoff) and after the models' 2023-2025 training years.
- Forecast method ml; providers composed (TCEQ, ASOS, Synoptic for air temperature; TCEQ for wind; Open-Meteo for solar).
- Run in `/Users/aphan/Senior_Design` at main HEAD `175b32bc443b4128195dcac70b3d96a60c653a1a`, `backend/` clean.
- The window was not changed by the owner and the full run was not interrupted or resumed (console: steps already archived (skipped): 0).

Exact full argv (also in manifest.json):

```
['--start', '2026-09-08T00:00:00Z', '--end', '2026-09-28T23:00:00Z', '--step-hours', '1', '--forecast-method', 'ml', '--archive-path', 'data/historical/real_data_validation_2026-09-08_2026-09-28.csv', '--log-path', 'data/historical/real_data_validation_2026-09-08_2026-09-28_log.csv', '--trace-path', 'data/historical/real_data_validation_2026-09-08_2026-09-28_trace.jsonl']
```

## Console summary (full run, last summary block of the console file)

```
=== Backfill summary ===
runs executed: 504   steps already archived (skipped): 0
  AUSTIN: archived 504, not archived 0, fallback runs 353, exhausted runs 0, errors 0
  CORPUS_CHRISTI: archived 504, not archived 0, fallback runs 98, exhausted runs 0, errors 0
  EL_PASO: archived 504, not archived 0, fallback runs 3, exhausted runs 0, errors 0
  MIDLAND: archived 504, not archived 0, fallback runs 79, exhausted runs 0, errors 0
  safety gates that fired (point-level counts): {'G4': 422, 'G6': 111}
  sources[air_temp]: {'tceq': 1512, 'asos': 384, 'synoptic': 120}
  sources[wind_speed]: {'tceq': 2016}
  sources[solar_radiation]: {'open_meteo': 2016}
  provider issue: nsrdb: ValueError: nsrdb_provider: request for year 2026 failed with HTTP 400: ['Invalid value(s)'] x3
  provider issue: nsrdb: skipped after 3 consecutive failures x2013
archive rows now: {'AUSTIN': 504, 'CORPUS_CHRISTI': 504, 'EL_PASO': 504, 'MIDLAND': 504}
```

Smoke run (2 steps): all four cities archived 2, errors 0; AUSTIN fallback 2, CORPUS_CHRISTI fallback 1; gates {'G4': 2, 'G6': 1}; NSRDB HTTP 400 for 2026 then skipped (expected, STATE.md integration item 3).

## Completeness (committed: run_completeness.csv)

| city | expected_steps | trace_records | archive_rows | log_rows | exhausted | errors | no_trace | missing |
|---|---|---|---|---|---|---|---|---|
| AUSTIN | 504 | 504 | 504 | 504 | 0 | 0 | 0 | 0 |
| CORPUS_CHRISTI | 504 | 504 | 504 | 504 | 0 | 0 | 0 | 0 |
| MIDLAND | 504 | 504 | 504 | 504 | 0 | 0 | 0 | 0 |
| EL_PASO | 504 | 504 | 504 | 504 | 0 | 0 | 0 | 0 |

The smoke check (not committed) showed expected_steps 2, missing 0 for all four cities.

## Trace sanity (read-only, 2016 records)

| Check | Count |
|---|---|
| records with forecast_method other than ml (top-level) | 0 |
| records with pipeline.forecast_method other than ml | 0 |
| records with no pipeline block | 0 |
| non-exhausted, non-error records with null pipeline.detector_model | 0 (all 2016 name data/models/anomaly_{CITY}.joblib, 504 each) |
| exhausted / error / not archived | 0 / 0 / 0 |
| status ok / fallback | 1483 / 533 (353 + 98 + 3 + 79, matches the console) |

## Archive record (manifest.json)

| File | Bytes | sha256 |
|---|---|---|
| archive (.csv) | 212702 | `18f999aac44540138cfb2a2d1c7f624688e66d261e391a01b036970b8bfa25cf` |
| trace (.jsonl) | 1988914 | `4999c5cf2aa4b58b77f05b1a537c917e4c8a9487cd6a31fe2bf25f17630d781d` |
| log (.csv) | 114390 | `a9662fb795fc09d33d79490f43c1c8b6889138993be217f35d33835b22716180` |
| console (.txt) | 984282 | `113d25fc718547e4c85db0feb9fae1722f16787613bd50dfed9c3fa025857cf8` |

Archive rows per city: 504 each. Manifest git head `175b32bc443b4128195dcac70b3d96a60c653a1a`, `backend_dirty: false`. All 8 model files hashed (non-null). Phase 4 (DB-03) must match the archive hash and the 504-per-city counts. Note the OD-8 window age: the live path reads the last 30 days, so this archive's read window lapses on 2026-10-28; a Phase 4 top-up backfill to go-live is a Phase 4 input.

## Task Commits

1. **Task 1: Offline preflight of the main checkout** - no commit (read-only by design); PREFLIGHT_OK at HEAD 175b32b
2. **Task 2: Owner runs smoke + full backfill** - no commit (owner action, git-ignored outputs)
3. **Task 3: Prove the run complete, commit manifest and completeness table** - `fadf9b0` (docs)

**Plan metadata:** the SUMMARY commit and the state/roadmap commit follow this file.

## Files Created/Modified
- `docs/data-science/decisions/real_data_validation/manifest.json` - backfill record for the validation window and the Phase 4 load
- `docs/data-science/decisions/real_data_validation/run_completeness.csv` - per-city step completeness of the real run

## Decisions Made
- Window kept as the planner chose; no owner change.
- Smoke completeness printed and checked but not committed.

## Deviations from Plan

None - plan executed exactly as written.

## Discrepancies

- Manifest git head equals the HEAD recorded by Task 1 (`175b32b`); `git diff --stat 175b32b..HEAD -- backend` is empty. No difference to note.
- The plan's commit trailer names Claude Opus 5.5; the commit carries the trailer this environment's attribution instruction specifies (Claude Sonnet 5.5), as directed by the orchestrator.
- The wall-clock duration above includes the owner's multi-hour backfill; it is not executor effort.
- No window change, no interruption or resume, all trace sanity counts zero.

## Findings carried to 03-04 (recorded, not acted on here)

- Fallback load is heavy and uneven: AUSTIN 353 of 504 steps (70%) fell back, CORPUS_CHRISTI 98 (19%), MIDLAND 79 (16%), EL_PASO 3 (0.6%). Gates fired: G4 422, G6 111 (point-level counts). The first trace record shows the pattern: `G4 FAIL (implausible (938 A)) - fallback rating 1825 A` for AUSTIN, i.e. the AUSTIN fallback rating equals its static rating. The report plan (03-04) should characterize this by city and gate before any go/no-go reading.
- Solar came from Open-Meteo for every point (NSRDB has no 2026 data); air temperature came mostly from TCEQ (1512), then ASOS (384) and Synoptic (120).

## Issues Encountered
None

## Known Stubs

None. This plan created no source file; the only committed files are a derived JSON manifest and a CSV table.

## User Setup Required

None - the owner's provider keys (Synoptic, NREL) were already in place and the owner ran the backfill.

## Next Phase Readiness
- 03-04 can run `report` against the archive and trace; 03-03 (offline replay) already exists.
- Phase 4 holds the exact archive path, sha256 and per-city row counts it must load.

## Self-Check: PASSED

- manifest.json and run_completeness.csv exist; commit `fadf9b0` is an ancestor of HEAD and lists exactly those two files.
- COMPLETE_OK and MANIFEST_OK printed; no raw data tracked; no credential-shaped strings in the committed files.

---
*Phase: 03-real-data-validation*
*Completed: 2026-10-21*
