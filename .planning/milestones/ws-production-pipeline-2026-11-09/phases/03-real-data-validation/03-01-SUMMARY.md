---
phase: 03-real-data-validation
plan: 01
subsystem: testing
tags: [validation, backfill, trace, pandas, ieee738, val-01, offline-analysis]

requires:
  - phase: 01-historical-pipeline
    provides: backfill_archive.py, the composed fetcher with .provenance/.errors, backfill_archive_test.py offline fixtures
  - phase: 02-data-cleaning
    provides: data_cleaning.clean_history, FLAG_ORDER, the seven-key pipeline dict
provides:
  - "backfill_archive --trace-path / backfill(trace_path=): one backfill_trace/1 JSON line per city per executed step, credentials redacted"
  - "backend/real_data_validation.py: completeness, manifest and report (VAL-01) subcommands, offline and deterministic"
  - "VAL-01 tables: ratings vs static and bounds, outcomes per gate and period, fallback direction, outliers, drivers, report_meta.json, tables.md"
affects: [03-02 real run, 03-03 VAL-02, 03-04 report, 03-05 decision, 04 production pipeline]

actuals:
  tokens: 22200
  tasks: 3
  commits: 5

plan_head_before: 01f46c122a9cc4f94fc56ed436f075ae9827b9b5
plan_head_after: 9ff8c07677aab1e3b3bbbd5036d61069e4488d94

tech-stack:
  added: []
  patterns:
    - "Measurement path reads the live pipeline's own return (run_city_pipeline dicts) instead of reconstructing it"
    - "Every expected (city, step) lands in exactly one outcome so denominators never shrink"
    - "Self-check counts in report_meta.json (keys ending in mismatches) drive a non-zero exit after the files are written"

key-files:
  created:
    - backend/real_data_validation.py
    - backend/tests/backfill_trace_test.py
    - backend/tests/real_data_validation_test.py
  modified:
    - backend/backfill_archive.py

key-decisions:
  - "Fractions and rates use the expected steps of the period as denominator (not the count of steps that have a value), so exhausted, errored, untraced and missing steps stay in every rate"
  - "A G4 fallback whose recomputed ampacity is inside the bounds contradicts its own gate: classed ERROR and counted in computed_vs_reported_mismatches"
  - "Redaction runs before truncation to 200 characters so a cut can never leave half a secret"
  - "Archive rows with no trace record are not archive-vs-trace mismatches; they are NO_TRACE in the outcome and completeness tables"

patterns-established:
  - "Trace flattening: nested observation/sources/pipeline dicts become obs_*, *_source, fc_*, and pipeline_<key> columns so new pipeline keys flow through"
  - "Deterministic output: no timestamps, sorted keys, fixed row order (config.LOCATIONS, OUTCOMES), lineterminator LF"

requirements-completed: [VAL-01]

coverage:
  - id: D1
    description: "backfill --trace-path writes one backfill_trace/1 record per city per step (rated station, reported and static rating, gates, alerts, rated observation, providers, aligned hour, whole pipeline dict); default path unchanged"
    requirement: "VAL-01"
    verification:
      - kind: integration
        ref: "backend/tests/backfill_trace_test.py#test_backfill_trace_feeds_the_completeness_table_end_to_end"
        status: pass
      - kind: unit
        ref: "backend/tests/backfill_trace_test.py#test_backfill_without_trace_path_writes_no_trace_file"
        status: pass
      - kind: unit
        ref: "backend/tests/backfill_archive_test.py (Phase 1, unchanged)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Trace hardening: error records, credential redaction in errors and alerts, last provenance record of the rated station, resumed step keeps the last record"
    requirement: "VAL-01"
    verification:
      - kind: unit
        ref: "backend/tests/backfill_trace_test.py#test_trace_records_errors_with_credentials_redacted"
        status: pass
      - kind: unit
        ref: "backend/tests/backfill_trace_test.py#test_alert_text_is_redacted_before_it_reaches_the_trace"
        status: pass
      - kind: unit
        ref: "backend/tests/backfill_trace_test.py#test_trace_takes_the_last_provenance_record_of_the_rated_station"
        status: pass
      - kind: unit
        ref: "backend/tests/backfill_trace_test.py#test_resumed_step_keeps_the_last_trace_record"
        status: pass
    human_judgment: false
  - id: D3
    description: "completeness and manifest subcommands: per-city step counts (no_trace never counted as missing); deterministic manifest of window, argv, owner command, file and model hashes, git HEAD"
    requirement: "VAL-01"
    verification:
      - kind: unit
        ref: "backend/tests/real_data_validation_test.py#test_completeness_counts_archive_rows_without_trace_as_no_trace"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_test.py#test_manifest_is_deterministic_and_flags_missing_models"
        status: pass
    human_judgment: false
  - id: D4
    description: "report subcommand: VAL-01 tables with inclusive bounds, warm-up/scored boundary, one outcome per expected step, fallback direction, empty-city rows, byte-identical ordered output, rounding, and self-checks that exit 1"
    requirement: "VAL-01"
    verification:
      - kind: unit
        ref: "backend/tests/real_data_validation_test.py (18 tests, incl. test_bound_class_is_inclusive_at_both_bounds, test_classify_steps_counts_every_expected_step_once, test_report_is_byte_identical_across_runs_and_ordered_by_locations, test_report_exits_one_on_archive_trace_mismatch)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The tables are a faithful, useful view of REAL data (the synthetic tests prove the arithmetic, not that real traces look as the analysis expects)"
    requirement: "VAL-01"
    verification: []
    human_judgment: true
    rationale: "Plan 03-02 produces the first real trace; whether the tables answer the owner's question can only be judged on that run"

duration: 15min
completed: 2026-10-20
status: complete
---

# Phase 3 Plan 01: Validation trace and VAL-01 report Summary

**Backfill now writes a redacted per-step trace of what the live per-city pipeline did, and an offline `real_data_validation.py` turns trace plus archive into deterministic VAL-01 tables (computed vs reported ampacity, bound class, gate outcomes, fallback direction, outliers, drivers) with self-checks that fail the run on any disagreement.**

## Performance

- **Duration:** about 15 min for this continuation (Task 1 was implemented by the halted predecessor and committed here)
- **Started:** 2026-10-20T22:55Z (continuation; Task 1 work pre-dated it)
- **Completed:** 2026-10-20T23:12Z
- **Tasks:** 3 of 3
- **Files modified:** 4 (1 modified, 3 created)

## Accomplishments

- `backfill_archive.backfill(..., trace_path=None)` and `--trace-path`: one `backfill_trace/1` line per city per executed step holding the rated station, reported and static rating, fallback flag and gates, redacted alerts, the observation actually rated, the provider of each input, the aligned observation hour and the whole seven-key `pipeline` dict; a city that raises gets a record with its redacted error. Without the flag nothing extra is opened (Phase 1's `backfill_archive_test.py` passes unchanged).
- `real_data_validation.py completeness | manifest | report`: completeness table (`no_trace` kept apart from `missing`), a deterministic run manifest (window, argv, owner command, sha256 of archive/trace/log and the 8 model files, git HEAD; exits 1 after writing when a model is missing), and the VAL-01 report.
- VAL-01 report recomputes the pre-gate ampacity from the traced observation with each city's own conductor at the monitor's solar altitude. Non-fallback steps match the reported rating within 1e-6 A; `report` exits 1 on any computed-vs-reported, archive-vs-trace or duplicate-slot disagreement, after writing every file.
- Full suite: 1380 passed, 0 failed (baseline 1356; +24 tests). `git status -- data outputs` shows nothing new; no rating-policy file was touched.

## Task Commits

1. **Task 1: Tracer - trace writer and completeness table** - `847c7d6` (feat)
2. **Task 2: Trace hardening and run manifest (TDD)** - `7a9c2d7` (test, RED), `8ea004f` (feat, GREEN)
3. **Task 3: VAL-01 report (TDD)** - `6b4ceae` (test, RED), `9ff8c07` (feat, GREEN)

**Plan metadata:** committed separately after this file (docs: complete plan).

## TDD Gate Compliance

Plan type is `execute` with `tdd="true"` on Tasks 2 and 3; both followed RED then GREEN, no REFACTOR commits were needed.

- **Task 2 RED (`7a9c2d7`):** 4 of the 6 new tests failed on the planned assertions (error record absent; alert text not redacted; resume gave 2 records instead of 4; `manifest` subcommand unknown). Two (`test_trace_takes_the_last_provenance_record_of_the_rated_station`, `test_completeness_counts_archive_rows_without_trace_as_no_trace`) passed at RED because Task 1's implementation already satisfied those behaviours; they pin that behaviour rather than drive new code. Classifier: `gsd check tdd-red-evidence` returned `RED_EVIDENCE_OK` (JUnit report, target `test_manifest_is_deterministic_and_flags_missing_models`). semanticAssessment: the target executed and failed with `SystemExit: 2` from argparse `invalid choice: 'manifest'`, the exact missing feature.
- **Task 3 RED (`6b4ceae`):** 16 of 18 tests failed (the other 2 were Task 2's), all on `AttributeError`/argparse for symbols that did not exist yet (`classify_steps`, `OUTCOMES`, `bound_class`, `report`). Classifier: `RED_EVIDENCE_OK` for target `test_classify_steps_counts_every_expected_step_once`. semanticAssessment: the target ran and failed on `module has no attribute 'classify_steps'`, the planned missing feature, not on a setup or import fault.
- **GREEN:** `8ea004f` and `9ff8c07`; each followed by a passing run of the touched test files, and the full suite after Task 3.

## Files Created/Modified

- `backend/backfill_archive.py` - `TRACE_SCHEMA`, `_redact`, `_trace_records`, `trace_path` parameter, `--trace-path`
- `backend/real_data_validation.py` - offline analysis module and CLI (completeness, manifest, report)
- `backend/tests/backfill_trace_test.py` - offline tracer test and trace hardening tests
- `backend/tests/real_data_validation_test.py` - completeness, manifest and VAL-01 tests

## Decisions Made

- Rate denominators are the expected steps of the period, so every non-measured outcome stays visible in each rate (VAL-01 transparency prohibition).
- G4 fallback with a within-bounds recomputed value is classed ERROR and counted as a mismatch rather than silently assigned to G4_low/G4_high.
- Redact before truncating; alert and error text only (the CSV log keeps its Phase 1 format, as the plan stated).
- Archive rows without a trace record are NO_TRACE (visible in outcomes and completeness), not archive-vs-trace mismatches.

## Phase 2 names the module relies on

`data_cleaning.clean_history(history, as_of=None)` with `.report` keys `rows_in`, `rows_usable`, `rows_excluded`, `flag_counts` (every `FLAG_ORDER` name), `missing_slots`; `data_cleaning.FLAG_ORDER`; one city per call. Cross-checked against the code and a live call: all names match the plan's interfaces. An empty city frame returns a zero report without error. The pipeline dict keeps its seven keys (`history_rows`, `usable_history_rows`, `forecast_method`, `forecast_used_by_g6`, `forecast`, `detector_signal`, `detector_model`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Manifest test could not exercise the missing-model path**
- **Found during:** Task 2 (GREEN run)
- **Issue:** My RED test ran the manifest with `--cities AUSTIN` only, and models existed for AUSTIN, so no model was missing and the expected exit 1 never happened.
- **Fix:** Test now uses `--cities AUSTIN MIDLAND` (MIDLAND has no model files), with matching expectations.
- **Files modified:** backend/tests/real_data_validation_test.py
- **Verification:** test passes; manifest bytes identical across two runs.
- **Committed in:** `8ea004f`

**2. [Rule 2 - Missing critical] Self-check coverage beyond the plan's wording**
- **Found during:** Task 3
- **Issue:** a G4 fallback whose recomputed value lies inside the bounds had no outcome; an unparseable fallback gate likewise.
- **Fix:** both classed `ERROR`; the G4 case also counts in `computed_vs_reported_mismatches`.
- **Files modified:** backend/real_data_validation.py
- **Committed in:** `9ff8c07`

---

**Total deviations:** 2 auto-fixed (1 bug in my own test, 1 missing-correctness edge). **Impact on plan:** none on scope.

## Discrepancies

- **Commit trailer:** commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`, the trailer this environment's attribution instructions specify, not the plan's `Claude Opus 5.5` text (orchestrator-approved).
- **Task 3 acceptance (git-log policy check) cannot pass as written:** `git log --format=%s -- <policy files> | grep '(03-0[1-5])'` matches 12 commits of an earlier, different milestone whose scopes were also `03-0x` (e.g. `bb5f6f9 feat(03-01): wire safety monitor to real IEEE 738 thermal model`). The intent (this plan touches none of those files) was verified instead by `git log 01f46c1..HEAD -- <same files>`, which lists 0 commits; `git diff --name-only` over this plan's five commits lists only the four `files_modified`.
- **Baseline count:** the plan cites 1236 tests; the pre-edit baseline was 1356 passed (Phases 1-2 added tests). Final: 1380 passed.
- **Extras beyond the plan's list:** `test_alert_text_is_redacted_before_it_reaches_the_trace`, `test_report_exits_one_when_a_reported_rating_disagrees_with_physics`, `test_duplicate_archive_slot_counts_as_a_mismatch`, `test_missing_input_exits_two_naming_the_path`, `computed_amps` parametrised over the four cities; `expected_steps` column in the ratings table; a `none` column (static equals computed) in the fallback-direction table; an empty-city placeholder row (`rank_kind=none`) in the outliers table.
- **Pre-commit branch assertion:** commits were made on `main` under the owner's explicit decision and `git.allow_default_branch_commits: true`.

## Issues Encountered

- The first executor halted at the protected-branch commit guard on `main`; resolved by the owner's decision above. No other problems.

## Known Stubs

None.

## Threat Flags

None. The only new process execution is `subprocess.run(["git", ...])` with fixed argv and no shell (acceptance-checked). Mitigations T-03-01 (redaction), T-03-02 (self-checks, manifest hashes), T-03-03 (no shadow/experiment names, grep-verified), T-03-04 (no policy-file edits) and T-03-05 (copied `_no_network`/`_offline_env` fixtures, tmp_path only) are implemented.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 03-02 can run the owner's real backfill with `--trace-path` and use `completeness` and `manifest` (the module holds the owner command template).
- Plans 03-03/03-04 read the trace through `load_trace`/`classify_steps`, which carry every `fc_*`, `detector_*` and `pipeline_*` column through.
- Values remain provisional (OD-5); nothing here changes a rating policy.

## Self-Check: PASSED

All four files exist; commits `847c7d6`, `7a9c2d7`, `8ea004f`, `6b4ceae`, `9ff8c07` are ancestors of HEAD; the plan's automated verification and acceptance greps pass (policy-log check satisfied by the range form noted above); full suite 1380 passed.

---
*Phase: 03-real-data-validation*
*Completed: 2026-10-20*
