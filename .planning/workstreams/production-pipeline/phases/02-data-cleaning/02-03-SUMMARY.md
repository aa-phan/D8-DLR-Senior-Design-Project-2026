---
phase: 02-data-cleaning
plan: 03
subsystem: data-cleaning
tags: [pandas, data-cleaning, stuck-sensor, spike, hourly-slots, gap-marking, policy-doc]

requires:
  - phase: 02-data-cleaning
    provides: "02-01: clean_history with bad_timestamp, duplicate, fallback; MARKER_COLUMNS; city_pipeline wiring"
provides:
  - "backend/data_cleaning.py: at_or_after_run, same_hour, stuck_<field>, spike_<field>, after_gap rules; gap_slots marker column; report fields missing_slots, trailing_gap_slots, contiguous_tail_rows; STUCK_* / SPIKE_* constants; stuck_min_run_rows and spike_max_step overrides"
  - "docs/data-science/decisions/data_cleaning.md: the written cleaning policy and the mark-never-fill gap strategy, pinned to the code by a test"
  - "Mixed-spelling timestamp parse fix in data_cleaning._parse_utc"
affects: [02-04-forecast-gap-guard, 03-real-data-validation, 04-postgres-writer]

actuals:
  tokens: 10747
  tasks: 3
  commits: 4
plan_head_before: 44cda9f643cc367b6f79ceb54fd4cd8ec49724f8
plan_head_after: 4efdfd8e2a63d05858a0c78d53cb694d138b8fd1

tech-stack:
  added: []
  patterns:
    - "Cross-row rules run in FLAG_ORDER over the rows earlier rules left usable; each rule family (stuck, spike) judges all its fields against one shared row set"
    - "Mark, never fill: gaps are measured (gap_slots, report fields) and never imputed"
    - "A doc/code agreement test reads the policy doc and fails when any public upper-case constant or flag is not stated"
    - "Explicit-offset and naive timestamps are parsed in separate batches (pandas 2.3.3 carries an offset into later naive values)"

key-files:
  created:
    - docs/data-science/decisions/data_cleaning.md
  modified:
    - backend/data_cleaning.py
    - backend/tests/data_cleaning_test.py
    - backend/tests/city_pipeline_test.py
    - .planning/workstreams/production-pipeline/phases/02-data-cleaning/deferred-items.md

key-decisions:
  - "Mark, never fill: a missing hourly slot is never imputed; the next usable row carries after_gap and gap_slots, and the report measures missing, trailing and contiguous-tail slots for plan 02-04"
  - "at_or_after_run excludes every row whose slot is at or after as_of's slot, so a rerun or out-of-order backfill never learns from its own slot or later"
  - "Stuck thresholds (6 rows; solar 0.0 exempt) and spike steps (10 degC, 10 m/s, 700 W/m2 per hour) are provisional and not fitted to data; Phase 3 measures their flag rates"
  - "The three stuck rules share one row set (usable after same_hour) and the three spike rules share one (usable after the stuck rules), so field order never changes a verdict"
  - "An excluded row, including a spike, leaves its hour missing, so the next usable row is marked after_gap"

requirements-completed: [CLEAN-01, CLEAN-02, CLEAN-04]

coverage:
  - id: D1
    description: "Hourly-slot rules: rows at or after the rated slot excluded, latest row per hour kept, fallback never displaces a computed row, no look-ahead on rerun"
    requirement: CLEAN-02
    verification:
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_rows_at_or_after_the_rated_slot_are_excluded"
        status: pass
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_rows_sharing_an_hour_keep_the_latest"
        status: pass
    human_judgment: false
  - id: D2
    description: "A skipped cycle is marked on the next row (after_gap, gap_slots) and measured (missing_slots, trailing_gap_slots, contiguous_tail_rows); nothing is filled"
    requirement: CLEAN-02
    verification:
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_skipped_cycle_leaves_one_missing_slot_marked_on_the_next_row"
        status: pass
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_trailing_gap_is_measured_against_as_of"
        status: pass
    human_judgment: false
  - id: D3
    description: "Stuck-sensor runs flagged at the 6-row boundary (5 not flagged), night solar 0.0 exempt, NaN never forms a run, runs span excluded rows"
    requirement: CLEAN-01
    verification:
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_six_identical_readings_are_a_stuck_run_and_five_are_not"
        status: pass
    human_judgment: false
  - id: D4
    description: "Spikes flagged beyond the per-field step on both adjacent hourly neighbors; a difference equal to the step, steps, ramps, gaps and end rows are not spikes"
    requirement: CLEAN-01
    verification:
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_a_difference_equal_to_the_step_is_not_a_spike"
        status: pass
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_spike_thresholds_per_field"
        status: pass
    human_judgment: false
  - id: D5
    description: "Written policy states every flag, constant, the policy version and the gap strategy; a test fails if doc and code disagree"
    requirement: CLEAN-04
    verification:
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_policy_doc_names_every_flag_and_threshold"
        status: pass
    human_judgment: false
  - id: D6
    description: "The provisional thresholds are physically reasonable for hourly Texas station data"
    requirement: CLEAN-01
    verification: []
    human_judgment: true
    rationale: "Backstop truth: nothing here can assert physical reasonableness; Phase 3 measures per-city flag rates on real data"

duration: approx. 40 min of active work (session spanned two rate-limit pauses)
completed: 2026-10-20
status: complete
---

# Phase 2 Plan 03: Stuck, Spike and Hourly-Slot Rules Summary

**`clean_history` now excludes rows at or after the rated slot, extra rows in an hour, stuck-sensor runs and one-hour spikes, marks missing hourly slots with `after_gap`/`gap_slots` without ever filling them, and the policy is written in `docs/data-science/decisions/data_cleaning.md` and pinned to the code by a test.**

## Performance

- **Duration:** about 40 min active (the wall clock includes two rate-limit pauses)
- **Tasks:** 3 (plus one deviation fix committed first)
- **Files:** 5 touched (1 created, 4 modified including `deferred-items.md`)
- **Commits:** 4 (measured from the plan ledger, `44cda9f..4efdfd8`)

## Accomplishments

- CLEAN-02: `at_or_after_run` (no look-ahead; a rerun sees what the first in-order run saw), `same_hour` (latest timestamp per slot; a fallback row is excluded first and never displaces a computed row), `after_gap` + integer `gap_slots` (marks, does not exclude), and report fields `missing_slots`, `trailing_gap_slots`, `contiguous_tail_rows` for plan 02-04. The skipped-cycle test (hourly 00:00-09:00 without 05:00) shows 06:00 with `after_gap`, `gap_slots` 1, all nine rows usable, `missing_slots` 1.
- CLEAN-01: `stuck_<field>` (6 identical consecutive usable readings; solar 0.0 exempt; NaN never forms a run; runs span excluded rows) and `spike_<field>` (both adjacent hourly neighbors differ by more than the step, same direction), with `stuck_min_run_rows` and `spike_max_step` overrides. Boundary tests sit on both sides of each threshold.
- CLEAN-04: `gap_slots` joins `MARKER_COLUMNS`; every flag is distinguishable through `clean_flags`.
- Policy doc (130 lines, nine sections) with the `test_policy_doc_names_every_flag_and_threshold` agreement test; I corrupted a threshold in a scratch edit and confirmed the test fails, then restored the doc.
- Full suite: 1340 passed, 0 failed; nothing written under `data/` or `outputs/`.

## Task Commits

0. **Deviation fix: separate-batch timestamp parse in `data_cleaning._parse_utc`** - `36dc2f2` (fix)
1. **Task 1: hourly-slot rules and gap marking (CLEAN-02)** - `64256c5` (feat)
2. **Task 2: stuck-sensor runs and spikes (CLEAN-01)** - `992fe32` (feat)
3. **Task 3: written policy and doc/code agreement test** - `4efdfd8` (docs)

**Plan metadata:** committed separately (docs: complete stuck/spike/slot rules plan).

## Files Created/Modified

- `backend/data_cleaning.py` - rules, constants, gap marker and report fields (385 lines)
- `backend/tests/data_cleaning_test.py` - 34 tests (597 lines)
- `backend/tests/city_pipeline_test.py` - fixture data only (see below)
- `docs/data-science/decisions/data_cleaning.md` - the written policy (new)
- `.planning/workstreams/production-pipeline/phases/02-data-cleaning/deferred-items.md` - 02-02's `_parse_utc` item marked resolved

## Fixture reconciliations

- `backend/tests/city_pipeline_test.py` (Task 1, rule `at_or_after_run` and the Task 2 stuck rule): `_START`/`_END` moved from 10:00/11:00 to 17:00/18:00 so archive hours 0-17 all precede the rated slot (without it hours 11-17 are excluded and test 1's 14 usable rows become 10); `_archive_row` weather now varies per hour (`air_temp = 25.0 + 0.1 * hour`, `wind_speed = 5.0 + 0.05 * hour`, `solar_radiation = 500.0 + hour`) so the constant-weather rows are not a stuck run. No `assert` statement changed: the diff of assert lines against the last `test(01-03)` commit is empty.
- `dlr_orchestrator_test.py`, `backfill_archive_test.py`, `predictive_tracer_test.py`, `cleaning_pipeline_test.py`: none needed; all pass unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `data_cleaning._parse_utc` carried a UTC offset into later naive values**
- **Found during:** carried forward from 02-02 (`deferred-items.md`); fixed before Task 1
- **Issue:** on pandas 2.3.3 a single `to_datetime(..., format="ISO8601")` call applied an earlier value's explicit offset to a later naive or date-only value, misplacing the row in `clean_history`'s time sort and duplicate rule for archives that mix spellings.
- **Fix:** explicit-offset and naive values are parsed in separate batches (same approach as `historical_archive._parse_utc`, with a copy of its offset regex so this module still imports no storage module).
- **Files modified:** `backend/data_cleaning.py`, `backend/tests/data_cleaning_test.py` (regression test `test_offset_and_naive_spellings_in_one_frame_are_parsed_independently`, which failed before the fix)
- **Commit:** `36dc2f2`; deferred item marked resolved.

**2. [Rule 1 - Test expectation] Two 02-01 tests in `data_cleaning_test.py` changed expectations**
- **Found during:** Task 1
- **Issue:** `test_fallback_is_matched_as_bool_or_any_case_text` expected `""` for the hour-4 row, which now follows hours 2 and 3 (excluded) and correctly carries `after_gap`; `test_report_counts_rows_and_names_the_policy_version` compared `flag_counts` to a three-key dict, but `flag_counts` has one key per `FLAG_ORDER` name.
- **Fix:** expected values updated (hour 4 -> `"after_gap"`; counts built from `FLAG_ORDER` with zeros). The plan's "02-01's tests pass unchanged" could not hold for these two; neither is a Phase 1 test.
- **Commit:** `64256c5`

**Total deviations:** 2 auto-fixed (1 bug, 1 test expectation). **Impact:** none on scope.

### Discrepancies

- **Rule-family row sets (interpretation):** the plan says stuck rules run "over the rows still usable after `same_hour`" and spike rules "after the stuck rule". I implemented each family as one shared row set (all three stuck fields see the rows left by `same_hour`; all three spike fields see the rows left by the stuck rules), not field-by-field in `FLAG_ORDER`, so a verdict never depends on field order. Documented in the policy doc.
- **Spike leaves a gap:** a spike row is excluded and leaves its hour missing, so the next usable row is marked `after_gap` (my first expectations in four spike tests omitted this; the tests were corrected, the rule is as the plan specifies).
- **Key outside `SPIKE_FIELDS`:** an overriding `spike_max_step` key that is not in `SPIKE_FIELDS` is ignored, since no flag name exists for it; stated in the docstring and the doc.
- **Co-author trailer:** commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (the harness attribution), not the `Claude Opus 5.5` text in the plan.
- **TDD order:** tests were written and run RED before each implementation (Task 1: 11 failed; Task 2: 9 failed; regression test failed before its fix), but the plan specifies one `feat` commit per task, so there are no separate `test(...)` RED commits. The plan is `type: execute`, so no plan-level TDD gate applies.
- **Full-suite run:** the one full run (1340 passed) was started in the background and finished after a session pause; after it started, only `deferred-items.md` and this summary changed (neither read by any test). I did not repeat the 9-minute run.
- **Cross-plan note:** `cleaning_pipeline_test.py` still has a comment saying the 12:00 row "will be flagged by plan 02-03's gap rule"; it is untouched and still accurate (the 12:00 row is at or after a later run's slot).

## Issues Encountered

None beyond the items above.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path, file access or schema at a trust boundary. T-02-09 (stuck/spike rows) is mitigated by the stuck and spike rules and their boundary tests; T-02-10 (look-ahead) by `at_or_after_run` and `test_a_rerun_does_not_learn_from_its_own_slot`; T-02-11 (imputation) by the mark-never-fill strategy and the no-row-added invariant test from 02-01. No real archive under `data/` or `outputs/` was read to choose a threshold, and the frozen modules (`config.py`, `ampacity_forecast.py`, `anomaly_detector.py`, `forecast_training.py` and the rest of the list) are unchanged against `5efe97d`.

## User Setup Required

None.

## Next Phase Readiness

Ready for 02-04 (forecast gap guard): `report["trailing_gap_slots"]`, `report["contiguous_tail_rows"]` and `report["missing_slots"]` exist, and the policy doc ends its gap section with the sentence 02-04 continues from. 02-04 adds two public upper-case constants; `test_policy_doc_names_every_flag_and_threshold` will fail until the doc names them. Phase 3 must measure per-city flag rates (wind stuck runs on calm nights in El Paso and Midland, solar spikes on cloudy days) before the thresholds are relied on.

## Self-Check: PASSED

- Files exist: `backend/data_cleaning.py`, `backend/tests/data_cleaning_test.py`, `backend/tests/city_pipeline_test.py`, `docs/data-science/decisions/data_cleaning.md` (FOUND).
- Commits `36dc2f2`, `64256c5`, `992fe32`, `4efdfd8` are ancestors of HEAD.
- Full suite: 1340 passed, 0 failed; `find data outputs -newer` empty.
- Phase 1 assert lines unchanged; frozen-module diff against `5efe97d` empty; all acceptance greps pass.
