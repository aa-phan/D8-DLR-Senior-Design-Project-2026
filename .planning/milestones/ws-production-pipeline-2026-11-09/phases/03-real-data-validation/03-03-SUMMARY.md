---
phase: 03-real-data-validation
plan: 03
subsystem: testing
tags: [validation, forecast-coverage, anomaly-detector, g6, bootstrap, replay, val-02, offline-analysis]

requires:
  - phase: 03-real-data-validation
    provides: "03-01: backfill trace, load_trace/classify_steps, report/completeness/manifest, _markdown_table and CSV/JSON conventions"
  - phase: 02-data-cleaning
    provides: "data_cleaning.clean_history and the seven-key pipeline dict (usable_history_rows, forecast_used_by_g6)"
provides:
  - "VAL-02 tables in `report`: ml forecast-band coverage vs the nominal 90% (day-block bootstrap 95% interval), widened-band coverage, band width, MAE, bias; coverage by backtest-residual bucket; detector G6 trip rate by voting branch; capped G6 trip list"
  - "`replay` subcommand: the real per-city pipeline re-run offline on the traced observations with another forecast method (default naive), into new files, with a fidelity check against the original run"
  - "`report --replay-archive --replay-trace --replay-label`: naive_replay rows beside the original rows, replay_fidelity.json, exit 1 on drift"
affects: [03-04 real-data report, 03-05 go/no-go decision]

actuals:
  tokens: 21100
  tasks: 2
  commits: 4

plan_head_before: f420e7a9cfa8d89c5c8aa2b91bf8ba6962195eb4
plan_head_after: 0bdd782f2d66f90f398b6e4fe4f62d8a91a7229a

tech-stack:
  added: []
  patterns:
    - "Every exclusion from a rate population has its own count column, so a denominator is always reconstructible from the table"
    - "Parse the detector's reason text with markers pinned by a test that runs the REAL detector branches behind the REAL DLRSafetyMonitor"
    - "Seeded whole-day block bootstrap; an interval needs at least two UTC days, otherwise the cell is empty"
    - "Replay serves traced observations through a fetcher with the composed fetcher's call shape, so backfill/city_rating/the trace need no change"

key-files:
  created:
    - backend/tests/real_data_validation_val02_test.py
  modified:
    - backend/real_data_validation.py
    - backend/tests/real_data_validation_test.py

key-decisions:
  - "Coverage population n_band = scored steps that reached G6 (ok or G6) with a positive-width forecast band and a computed rating, whether or not G6 used the forecast; forecasts withheld across a gap stay in it and are counted in n_withheld_gap, so n_band = n_used_by_g6 + n_withheld_gap"
  - "n_cleaning_failure_suspect is a subset of n_cold_start (usable rows 0 is also below 12); the other split counts partition n_g6_evaluated into with-forecast, cold-start and silent-failure"
  - "A detector error is a G6 trip (it fails the step to G6) and is also counted in detector_errors; it is an exclusive vote"
  - "replay_fidelity `mismatches` is the sum of the three kind counts (a step can count in more than one kind)"
  - "The replay also requires the forecast model file when method is ml, not only the anomaly model, so it can never silently drop the forecast"

patterns-established:
  - "Replay stations are one row per city (stid REPLAY_<city>) at the city's own coordinates, one backfill call per city"
  - "Replay outputs are new files; any existing output (including the fidelity JSON) is a refusal, exit 2"

requirements-completed: [VAL-02]

coverage:
  - id: D1
    description: "VAL-02 forecast-band coverage table: nominal and widened coverage, day-block bootstrap interval, width/MAE/bias, secondary all-computed coverage, every exclusion counted in its own column"
    requirement: "VAL-02"
    verification:
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_coverage_population_excludes_cold_degenerate_and_non_g6_steps"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_band_hit_is_inclusive_at_both_edges"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_widened_band_agrees_with_the_detector"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_day_block_bootstrap_is_seeded_and_needs_two_days"
        status: pass
    human_judgment: false
  - id: D2
    description: "Silent degradation counts: forecast silently absent with enough usable history, suspected cleaning failure, withheld-for-gap, unloaded anomaly model; empty cells when the trace lacks usable_history_rows"
    requirement: "VAL-02"
    verification:
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_silent_forecast_failure_is_counted"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_detector_table_counts_trips_by_branch_and_missing_models"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_report_notes_a_trace_without_usable_history_rows"
        status: pass
    human_judgment: false
  - id: D3
    description: "Detector G6 trip rate by voting branch, parsed from the traced alert text; markers verified against the real AnomalyDetector branches and DLRSafetyMonitor; capped, ordered trip list"
    requirement: "VAL-02"
    verification:
      - kind: integration
        ref: "backend/tests/real_data_validation_val02_test.py#test_g6_vote_markers_match_real_detector_reasons"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_g6_trips_are_ordered_by_deviation_and_capped_per_city"
        status: pass
    human_judgment: false
  - id: D4
    description: "report writes the four val02_*.csv files, a VAL-02 section in tables.md and bootstrap/target metadata, byte-identically across runs"
    requirement: "VAL-02"
    verification:
      - kind: integration
        ref: "backend/tests/real_data_validation_val02_test.py#test_report_writes_val02_tables_deterministically"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_test.py#test_report_is_byte_identical_across_runs_and_ordered_by_locations"
        status: pass
    human_judgment: false
  - id: D5
    description: "Offline replay through the real pipeline: reproduces the original trace exactly with the same method, flags changed inputs, refuses without anomaly models or over existing outputs, makes no network or provider call"
    requirement: "VAL-02"
    verification:
      - kind: integration
        ref: "backend/tests/real_data_validation_val02_test.py#test_replay_with_the_same_method_reproduces_the_original_trace"
        status: pass
      - kind: integration
        ref: "backend/tests/real_data_validation_val02_test.py#test_replay_fidelity_flags_a_changed_observation"
        status: pass
      - kind: integration
        ref: "backend/tests/real_data_validation_val02_test.py#test_replay_refuses_without_anomaly_models_or_over_existing_outputs"
        status: pass
      - kind: integration
        ref: "backend/tests/real_data_validation_val02_test.py#test_replay_never_touches_the_network"
        status: pass
      - kind: integration
        ref: "backend/tests/real_data_validation_val02_test.py#test_report_shows_the_naive_replay_beside_the_original_and_fails_on_drift"
        status: pass
    human_judgment: false
  - id: D6
    description: "The VAL-02 tables are a meaningful view of REAL data (synthetic tests prove the arithmetic and the markers, not that real traces look as the analysis expects)"
    requirement: "VAL-02"
    verification: []
    human_judgment: true
    rationale: "Plan 03-04 produces the first VAL-02 numbers on the real run; whether coverage, trip rates and the naive reference answer the owner's question can only be judged there"

duration: 12min
completed: 2026-10-20
status: complete
---

# Phase 3 Plan 03: VAL-02 forecast-band coverage, detector trips and offline naive replay Summary

**`real_data_validation.py report` now measures the live ml forecast band's empirical coverage against its nominal 90% (seeded day-block bootstrap interval) and the detector's G6 trip rate by voting branch with every excluded step counted apart, and a new `replay` subcommand re-runs the real per-city pipeline offline on the same observations with the naive forecast, proven faithful by a fidelity check.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-10-20T23:13:33Z
- **Completed:** 2026-10-20T23:25:29Z
- **Tasks:** 2 of 2 (each as a RED commit then a GREEN commit)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- **Forecast-band coverage (`val02_forecast_by_city.csv`):** per city, the share of computed ratings inside the forecast's own 5-95% band against the nominal 0.90, with a 2000-resample, fixed-seed (20261019), whole-UTC-day bootstrap 95% interval (empty with fewer than two days); coverage inside the detector's widened band on the steps whose forecast G6 used; band width, MAE, bias; a secondary coverage over every scored step with a computed rating and a non-zero band (G4 fallbacks included). Warm-up, steps that never reached G6, cold starts, silent forecast failures, suspected cleaning failures, zero-width bands, steps with no computed rating and forecasts withheld across a gap each have their own count column.
- **Coverage by backtest residuals (`val02_coverage_by_residuals.csv`):** buckets 0 / 1-47 / 48-167 / 168+ for both periods, every bucket always present; a `n_zero_width` column explains why bucket 0 is empty (a forecast with 0 residuals has a zero-width band).
- **Detector table (`val02_detector_by_city.csv`):** G6 trip rate with n and interval, which branches ran (from `detector_signal`) and which voted (parsed from the traced alert text), detector errors, unattributed trips, learned-model trip rate, steps with no anomaly model loaded, and the design false-positive rate for reference. **`val02_g6_trips.csv`:** at most 50 trips per city ordered by deviation from the forecast centre, with votes, widened band and the traced reason; `tables.md` summarizes and links it.
- **`replay`:** feeds each step exactly the traced observation (measured wind speed, direction, solar, sources, observation hour) through the real pipeline (Phase 2 cleaning, forecast, G1-G6, archive) with the chosen forecast method, one city per `backfill` call with a one-row `REPLAY_<city>` station. With the same method as the original it reproduces rating, fallback, gates, forecast, band, detector signal and observations for all 16 steps of the test run exactly.
- **Fidelity and reporting:** `replay_fidelity` compares G1-G5/EXHAUSTED outcomes, computed ratings (1e-9 A) and G6 reach; `replay` and `report` exit 1 on any mismatch after writing `replay_fidelity.json`. `report --replay-archive --replay-trace` adds `naive_replay` rows beside the original rows; VAL-01 stays on the original run.
- Full suite: 1397 passed, 0 failed (baseline 1380; +17 tests). No file outside `backend/real_data_validation.py` and its tests was touched.

## Task Commits

1. **Task 1: VAL-02 tables (TDD)** - `7f03276` (test, RED), `01091b7` (feat, GREEN)
2. **Task 2: Offline naive replay with fidelity check (TDD)** - `1c28bab` (test, RED), `0bdd782` (feat, GREEN)

**Plan metadata:** committed separately after this file (docs: complete plan).

## TDD Gate Compliance

Plan type is `execute` with `tdd="true"` on both tasks; each followed RED then GREEN, no REFACTOR commits were needed.

- **Task 1 RED (`7f03276`):** all 12 new tests failed on the planned missing symbols (`band_hit`, `k_for`, `RESIDUAL_BUCKETS`, `day_block_bootstrap_ci`, `forecast_table`, `coverage_by_residuals_table`, `g6_votes`, `detector_table`, `g6_trips_table`) or on the missing `val02_*` files / `val02_notes` key of the report. Classifier: `gsd check tdd-red-evidence` returned `RED_EVIDENCE_OK` (JUnit report, target `test_band_hit_is_inclusive_at_both_edges`). semanticAssessment: the target ran and failed with `AttributeError: module 'real_data_validation' has no attribute 'band_hit'`, the planned missing feature, not a setup, import or fixture fault; the report tests ran the full stub setup and only the VAL-02 outputs were absent.
- **Task 2 RED (`1c28bab`):** the 4 replay tests failed (`AttributeError: no attribute 'replay'`; argparse `invalid choice: 'replay'`) after their offline original run completed; the 12 Task 1 tests still passed. Classifier: `RED_EVIDENCE_OK` for target `test_replay_with_the_same_method_reproduces_the_original_trace`. semanticAssessment: the target executed and failed on the missing `replay` function, the planned feature. The Task 2 implementation had been drafted before its tests; it was moved out of the tree (`git checkout` of that one file) so RED was observed against the real pre-implementation code, then restored for GREEN.
- **GREEN:** `01091b7` and `0bdd782`, each followed by a passing run of the touched test files; the full suite ran after Task 2.

## Files Created/Modified

- `backend/real_data_validation.py` - VAL-02 helpers and tables, day-block bootstrap, G6 vote parsing, replay fetcher/stations/`replay`/`replay_fidelity`, `report` VAL-02 + replay integration, `replay` subcommand
- `backend/tests/real_data_validation_val02_test.py` - 17 offline tests (new)
- `backend/tests/real_data_validation_test.py` - the report file-set assertion now lists the four new `val02_*.csv` files (03-01's test)

## Decisions Made

See `key-decisions` above. Besides those: the `*_runs` columns count from `detector_signal` among G6-evaluated steps, and a detector that raised keeps the signal of the branches that finished; votes come from the traced alert text, which the trace cuts at 200 characters (every marker sits well inside that, and a trip matching no marker is counted in `n_g6_trips_unattributed` instead of vanishing).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 03-01's report file-set assertion broke when `report` gained the VAL-02 files**
- **Found during:** Task 1 (GREEN run)
- **Issue:** `test_report_is_byte_identical_across_runs_and_ordered_by_locations` asserts the exact set of files `report` writes; the plan requires four new files.
- **Fix:** extended that expected list with the four `val02_*.csv` names.
- **Files modified:** backend/tests/real_data_validation_test.py
- **Verification:** all 41 tests of the three touched modules pass; byte-identical output still asserted for every file.
- **Committed in:** `01091b7`

**2. [Rule 1 - Bug] My first report-test fixture put the forecast centre outside its own band**
- **Found during:** Task 1 (inspecting generated output)
- **Issue:** the synthetic band was centred on the computed rating while the centre was offset, so the "widened" coverage came out below the nominal coverage, which cannot happen for a real forecast (the live code clamps such bands).
- **Fix:** band built around the forecast centre; the test now asserts nominal 5/6 and widened 1.0.
- **Files modified:** backend/tests/real_data_validation_val02_test.py
- **Committed in:** `01091b7`

**3. [Rule 3 - Blocking] First replay scenario never produced a forecast**
- **Found during:** Task 2 (GREEN run)
- **Issue:** the stub weather put 4-5 of 16 steps into G4 fallbacks, which Phase 2 cleaning excludes from history, so no step reached 12 usable rows and forecast equality was trivially None == None.
- **Fix:** stub wind speed and direction changed so all steps rate normally; the test now asserts at least two steps carry a forecast and G6 trips occur.
- **Files modified:** backend/tests/real_data_validation_val02_test.py
- **Committed in:** `0bdd782`

**4. [Rule 1 - Bug] Deprecated `pd.concat` of tables with empty/all-NaN columns**
- **Found during:** Task 2 (report-with-replay test)
- **Fix:** the VAL-02 stacker rebuilds the table from records and re-applies the nullable-integer columns.
- **Files modified:** backend/real_data_validation.py
- **Committed in:** `0bdd782`

---

**Total deviations:** 4 auto-fixed (3 bug, 1 blocking, all in tests or table assembly). **Impact on plan:** none on scope or behaviour.

## Discrepancies

- **Commit trailer:** commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (the trailer this environment's attribution instructions specify), not the plan's `Claude Opus 5.5` text (orchestrator-approved, as in 03-01).
- **Four commits, not two:** each TDD task is a RED test commit plus a GREEN feat commit, as in 03-01. The plan text expects one commit per task with the `feat(03-03)` messages; those messages are on the GREEN commits. Task 1's acceptance check "the task's own commit lists only `real_data_validation.py` and the val02 test" does not hold literally for `01091b7`, which also lists `backend/tests/real_data_validation_test.py` (deviation 1). Across all four commits only the three files above changed.
- **Task 2 policy-log acceptance cannot pass as written:** `git log --format=%s -- <policy files> | grep '(03-03)'` matches `feat(03-03): add Previous-Runs 24h-lead fetch adapter, pinned separately from legacy model`, a commit of an earlier milestone with the same scope. The intent (this plan touches none of those files) was verified with `git log f420e7a..HEAD -- <same files>`, which lists 0 commits.
- **`files_modified` and test count:** the plan lists two files and 11 tests; the work touches a third file (03-01's test, deviation 1) and adds 17 tests: beyond the 11 named, `test_residual_bucket_edges`, `test_coverage_by_residuals_lists_every_bucket_for_both_periods`, `test_detector_table_counts_trips_by_branch_and_missing_models`, `test_g6_trips_are_ordered_by_deviation_and_capped_per_city`, `test_report_notes_a_trace_without_usable_history_rows` and `test_report_shows_the_naive_replay_beside_the_original_and_fails_on_drift`.
- **Extras beyond the plan's lists:** columns `n_warmup`, `n_not_g6`, `n_no_computed`, `n_g6_trips_unattributed`, `n_zero_width`; `report --method-label`; `val02_method_labels` and `val02_notes` in `report_meta.json`; the `replay` fidelity-JSON path is also refused when it exists; a replay with method ml additionally requires the forecast model file. "usable_history_rows absent from the trace" is detected as absent or null for every step, because `load_trace` always creates the column.
- **Baseline:** the plan predates Phase 1-2 and 03-01 growth; the pre-edit suite was 1380 passed, final 1397.
- **Requirement wording:** VAL-02 in REQUIREMENTS.md says "naive/EWM forecast band"; this plan (following OD-3) measures the live ml band and shows naive only as a replay reference. The requirement is satisfied by the code and tests here; its numbers come from plan 03-04.
- **Pre-commit branch assertion:** commits were made on `main` under the owner's decision and `git.allow_default_branch_commits: true`, as in 03-01.

## Issues Encountered

None beyond the deviations above.

## Known Stubs

None.

## Threat Flags

None. The replay runs existing pipeline code with traced inputs and no network (asserted by test, with the providers, `requests.get` and the composed-fetcher factory all patched to fail); `real_data_validation.py` contains none of the shadow/experiment names (acceptance grep), loads no shadow candidate and scores no shadow prediction. Mitigations T-03-11 (refusal without anomaly models), T-03-12 (refusal over existing outputs), T-03-13 (`naive_replay` label on every replay row, counterfactual wording in docstrings and `tables.md`, fidelity check), T-03-14 and T-03-15 are implemented and tested.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 03-04 can run `report` (add `--replay-archive/--replay-trace` after `replay`) on the real trace, and assert `replay_fidelity.json` has `mismatches == 0`. Command shapes: `replay --archive A --trace T --start --end --cities --method naive --archive-out --trace-out --log-out --fidelity-out`; all four outputs must be new paths.
- The replay starts from an empty archive: if the real run began on a non-empty archive, the replay's early-step forecasts see less history than the original did. Fidelity (G1-G5, computed rating, G6 reach) does not depend on history, so it is unaffected, but the naive rows for those early steps are not like-for-like; 03-04 should replay a fresh-archive run or state this.
- A coverage or trip rate is only meaningful with its n and population definition; both are columns of the tables and spelled out in `tables.md`. Values remain provisional (OD-5); nothing here changes a rating policy, forecast method, quantile, control limit or model.

## Self-Check: PASSED

Both files exist; commits `7f03276`, `01091b7`, `1c28bab`, `0bdd782` are ancestors of HEAD; the 17 tests of `real_data_validation_val02_test.py` are collected and pass with `real_data_validation_test.py` and `backfill_trace_test.py` (41 passed); full suite 1397 passed; acceptance greps pass except the policy-log form noted under Discrepancies (range form: 0 commits); `replay --help` exits 0 and lists `--fidelity-out`.

---
*Phase: 03-real-data-validation*
*Completed: 2026-10-20*
