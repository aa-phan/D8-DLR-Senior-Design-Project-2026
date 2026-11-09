---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 08
subsystem: testing
tags: [anomaly-detector, g6, forecast-fallback, revalidation, pandas, pytest]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: "07-04 production callers (incl. real_data_validation) on city_point.production_city_point"
provides:
  - "data_cleaning.forecast_gap_kind and GAP_KIND_TRAILING / GAP_KIND_ML_LOOKBACK"
  - "naive band for G6 when the ml forecast is withheld only by the lookback rule (B5, D-17)"
  - "result['pipeline']['g6_forecast_method'] and ['g6_forecast'] (trace-only, no city_rating column)"
  - "real_data_validation g6_* flattened columns, g6_band_table and val02_g6_band_by_city.csv (D-18)"
affects: [07-11, 07-18, revalidation, shadow-refit]

actuals:
  tokens: 56000
  tasks: 2
  commits: 2

plan_head_before: ad342fceb9af7c92d183d8b60b550cb2a875206d
plan_head_after: 03188a48a5bf161985d95b462cb836cdcd0bc92f

tech-stack:
  added: []
  patterns:
    - "Withheld-forecast classification by kind constants instead of parsing reason text"
    - "Trace-only pipeline keys: absent column = not recorded, present-and-null = recorded, no band"

key-files:
  created: []
  modified:
    - backend/data_cleaning.py
    - backend/city_pipeline.py
    - backend/real_data_validation.py
    - backend/tests/data_cleaning_test.py
    - backend/tests/city_pipeline_test.py
    - backend/tests/cleaning_pipeline_test.py
    - backend/tests/real_data_validation_val02_test.py
    - backend/tests/real_data_validation_test.py
    - docs/data-science/decisions/data_cleaning.md

key-decisions:
  - "forecast_used_by_g6 is tracked with an explicit primary_fed_g6 flag, not object identity, so a naive fallback never reads as the stored forecast"
  - "g6_method_recorded is read from column presence in the trace; a trace mixing pre-B5 and post-B5 records counts the pre-B5 ones as no band"
  - "val02_g6_band_by_city is computed on the live run only, not the naive replay"

patterns-established:
  - "A pre-B5 trace is detected by the absent g6_forecast_method column and reports NA counts, never zeros"

requirements-completed: [REVAL-01]

coverage:
  - id: D1
    description: "forecast_gap_kind returns trailing_gap / ml_lookback / None by exactly forecast_gap_reason's conditions and order"
    requirement: REVAL-01
    verification:
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_gap_kind_is_none_exactly_when_gap_reason_is_none"
        status: pass
    human_judgment: false
  - id: D2
    description: "An ml lookback gap gives G6 the naive band; ml stays primary and its stored forecast is unchanged; trailing gap, cold-start, zero-width or raising naive leave G6 unbanded and the city still rates"
    requirement: REVAL-01
    verification:
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_ml_lookback_gap_gives_g6_the_naive_band_and_keeps_ml_as_the_stored_forecast"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_no_usable_naive_band_leaves_g6_without_a_band_and_the_city_still_rates"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_trailing_gap_limit_is_one_missing_slot_for_every_band"
        status: pass
    human_judgment: false
  - id: D3
    description: "pipeline gains g6_forecast_method and g6_forecast; forecast_used_by_g6 is False when the naive fallback fed G6; no stored column changes"
    requirement: REVAL-01
    verification:
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py#test_pipeline_key_reports_history_forecast_and_detector"
        status: pass
      - kind: other
        ref: "git diff --quiet db1a4bc^ db1a4bc -- backend/supabase_store.py docs/data-science/schema/city_rating_v1.md"
        status: pass
    human_judgment: false
  - id: D4
    description: "The re-validation report writes val02_g6_band_by_city.csv per city (counts by method, band_share, g6_method_recorded), NA for a pre-B5 trace, and lists it in tables.md"
    requirement: REVAL-01
    verification:
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_g6_band_table_counts_each_method_exactly"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_report_writes_the_g6_band_table_and_lists_it_in_tables_md"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py#test_report_on_a_trace_without_g6_method_leaves_the_counts_empty"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-11-02
status: complete
---

# Phase 07 Plan 08: Naive G6 band on an ml lookback gap, and its report Summary

**When the ml forecast is withheld from G6 only by the 7-row lookback rule, G6 now gets the naive band from the same cleaned history, and the pipeline output, trace and re-validation report show which method gated each hour.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-11-02T07:50:50Z
- **Completed:** 2026-11-02T07:59:43Z (full suite run included)
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- `data_cleaning.forecast_gap_kind` classifies a withheld forecast as `trailing_gap` or `ml_lookback` by the same conditions and order as `forecast_gap_reason`, which is left unchanged along with its messages.
- `city_pipeline` falls back to `forecast_ampacity(history, method="naive")` for G6 on an `ml_lookback` gap, inside try/except. A trailing gap withholds every band; a naive cold start, zero or negative width, or exception leaves G6 unbanded, logs the reason, and the city still rates. Exactly one missing trailing slot still allows a band, two do not (tested at the edge).
- `result["pipeline"]` gains `g6_forecast_method` (`"ml"`, `"naive"`, `"ewm"` or None) and `g6_forecast`. `forecast_used_by_g6` now means the stored (primary) forecast fed G6, so it is False on the naive fallback. `forecast_method`, `forecast_status` and the stored `forecast` block keep their meaning, and `supabase_store.py` and the `city_rating` schema doc are byte-identical across the commit.
- `real_data_validation` flattens the new keys to `g6_forecast_method`, `g6_amps`, `g6_ci_lower`, `g6_ci_upper`, adds `g6_band_table` and writes `val02_g6_band_by_city.csv` with a "G6 band engagement (B5)" section in `tables.md`. AUSTIN is included like every other city (D-18).
- A trace recorded before B5 reads as `g6_method_recorded` False with NA counts, not zeros; a city with no G6-evaluated step reports 0 evaluated and an empty share.

## Task Commits

1. **Task 1: Naive band for G6 when the ml lookback withholds the forecast (B5, D-17)** - `db1a4bc` (feat)
2. **Task 2: G6 method in the flattened trace and the per-city band-engagement table** - `03188a4` (feat)

**Plan metadata:** recorded in the docs(07-08) commit that follows this file.

_Note: both tasks are `tdd="true"`. The plan specified one `feat` commit per task with tests written first, so there is no separate `test(...)` RED commit; RED was run before each implementation (Task 1: 66 failed, all on the missing `forecast_gap_kind` or the missing naive call and new keys; Task 2: 10 failed, all on missing g6 columns, `g6_band_table` and the report file)._

## Files Created/Modified

- `backend/data_cleaning.py` - `GAP_KIND_TRAILING`, `GAP_KIND_ML_LOOKBACK`, `forecast_gap_kind`
- `backend/city_pipeline.py` - naive fallback selection for the detector's band, `g6_forecast_method`, `g6_forecast`, narrowed `forecast_used_by_g6`
- `backend/real_data_validation.py` - `_G6_FORECAST_COLUMNS`, flatten and pass-through changes, `G6_BAND_COLUMNS`, `g6_band_table`, report file and markdown section
- `backend/tests/data_cleaning_test.py`, `backend/tests/city_pipeline_test.py`, `backend/tests/real_data_validation_val02_test.py` - new cases
- `backend/tests/cleaning_pipeline_test.py`, `backend/tests/real_data_validation_test.py` - updated for the new behavior and the new report file (see deviations)
- `docs/data-science/decisions/data_cleaning.md` - names the two kind constants and describes the fallback (see deviations)

## Decisions Made

- `forecast_used_by_g6` comes from an explicit `primary_fed_g6` flag, not `g6_forecast is forecast`. An identity check first broke an existing test whose fake returns one object for every method, and it would also be fragile in general.
- `g6_method_recorded` is a column-presence flag for the whole trace. A trace that mixes pre-B5 and post-B5 records (a backfill resumed after this change) counts the pre-B5 hours as no band. This is stated in the `g6_band_table` docstring.
- The band table is built from the live run only; the naive replay rows are not counted, since a replay's G6 method is the replay's own.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Phase 3 lookback test asserted the pre-D-17 behavior**
- **Found during:** Task 1 (verify run)
- **Issue:** `cleaning_pipeline_test.py::test_ml_forecast_across_a_gap_in_its_lookback_is_withheld` asserted the detector gets None across an ml lookback gap, which is exactly what D-17 changes.
- **Fix:** Updated that test to use a per-method fake: ml stays withheld (`forecast_used_by_g6` False, stored forecast intact), the detector receives the naive band, `g6_forecast_method` is `"naive"`, no "not used for G6" note is logged. The complete-history half is unchanged.
- **Files modified:** backend/tests/cleaning_pipeline_test.py
- **Committed in:** db1a4bc

**2. [Rule 3 - Blocking] Policy-doc test requires every public constant named in the doc**
- **Found during:** Task 1
- **Issue:** `data_cleaning_test.py::test_policy_doc_names_every_flag_and_threshold` fails for any new uppercase constant not in backticks in `docs/data-science/decisions/data_cleaning.md`.
- **Fix:** Added a short table for the two kind constants and a paragraph on the naive fallback to the "Forecast use across gaps" section, and corrected the sentence that said G6 runs without a forecast for up to seven hours after a skipped cycle.
- **Files modified:** docs/data-science/decisions/data_cleaning.md
- **Committed in:** db1a4bc

**3. [Rule 3 - Blocking] Report file-list test pins the exact output files**
- **Found during:** Task 2
- **Issue:** `real_data_validation_test.py::test_report_is_byte_identical_across_runs_and_ordered_by_locations` lists every file `build_report` writes.
- **Fix:** Added `val02_g6_band_by_city.csv` to that list.
- **Files modified:** backend/tests/real_data_validation_test.py
- **Committed in:** 03188a4

**4. [Rule 2 - Missing critical] Pre-B5 trace must not read as zero band hours**
- **Found during:** Task 2
- **Issue:** The plan's flatten rule as written would set `g6_forecast_method` to None for a pre-B5 record, making "not recorded" indistinguishable from "no band", which would report a false 0% band share for the Phase 3 trace.
- **Fix:** `_flatten_record` leaves `g6_forecast_method`, `g6_amps`, `g6_ci_lower`, `g6_ci_upper` out of a record whose pipeline has no such key; a recorded null stays a present, null column.
- **Files modified:** backend/real_data_validation.py
- **Committed in:** 03188a4

---

**Total deviations:** 4 auto-fixed (1 bug, 2 blocking, 1 missing critical)
**Impact on plan:** All necessary for correctness or to keep existing pinned tests honest. No scope creep; `PRODUCTION_CONDUCTORS` and the store are untouched.

## Issues Encountered

None beyond the deviations above. Full suite: 2412 passed, 82 skipped (previous 2335 passed), run once before this summary.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. Mitigations T-07-17 (trace-only keys, `forecast_used_by_g6` never set by the fallback, no store column change, verified by diff) and T-07-18 (try/except around the naive call, tested for the raising and cold-start cases) are in place. The safety prohibition holds: fallback rows stay out of both the primary and the naive call's history (tested), and a naive band is never reported as the stored ml forecast.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Nothing changes live until the owner-approved promotion (07-18). Nothing was pushed, no Supabase write, no deploy, and no forecast_shadow script was run.
- The committed Phase 3 report outputs under `docs/data-science/decisions/real_data_validation/` were not regenerated; `val02_g6_band_by_city.csv` appears the next time `report` runs, and a Phase 3 trace will show NA counts with `g6_method_recorded` False.
- `PRODUCTION_CONDUCTORS` untouched (O4, AUSTIN to Drake at 100 C, belongs to 07-11).

---
*Phase: 07-per-city-conductors-shadow-refit-and-early-model-selection*
*Completed: 2026-11-02*

## Self-Check: PASSED

- Modified files exist on disk; commits `db1a4bc` and `03188a4` are ancestors of HEAD.
- Acceptance: `forecast_ampacity(history, method="naive")` appears once in city_pipeline.py; `supabase_store.py` and `city_rating_v1.md` unchanged across the Task 1 commit; `val02_g6_band_by_city.csv` named in real_data_validation.py; full suite green (2412 passed, 82 skipped).
