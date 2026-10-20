---
phase: 02-data-cleaning
plan: 01
subsystem: data-cleaning
tags: [pandas, data-cleaning, archive, idempotent-append, tracer, offline-tests]

requires:
  - phase: 01-land-pr-7
    provides: "city_pipeline, dlr_orchestrator, historical_archive and the offline test fixtures (_no_network, _offline_env)"
provides:
  - "backend/data_cleaning.py: clean_history(history, as_of) -> CleanedHistory(frame, usable, report) with bad_timestamp, duplicate and fallback rules, FLAG_ORDER, EXCLUDING_FLAGS, MARKER_COLUMNS, CLEANING_POLICY_VERSION"
  - "city_pipeline cleans between read_history and the forecast/detector; a cleaning exception degrades to a cold start"
  - "historical_archive.append_observation refuses a second row for a (city, UTC instant) slot in any ISO-8601 spelling (CSV-only first-write-wins); read_history sorts by parsed UTC time, stable"
  - "Offline end-to-end tracer through dlr_orchestrator -> city_pipeline -> data_cleaning -> rate_city -> append guard"
affects: [02-02-append-guard-hardening, 02-03-stuck-spike-slot-rules, 02-04-forecast-gap-guard, 03-real-data-validation, 04-postgres-writer]

actuals:
  tokens: 9400
  tasks: 2
  commits: 2
plan_head_before: 90aaacf2ca1d0f641e51d89fb31d8711363c2e16
plan_head_after: e33196bb7c9e02be689b2349685ef03aa9afeed9

tech-stack:
  added: []
  patterns:
    - "Cleaning is a read-time view: marker columns live on the cleaned frame only, nothing is written back (CLEAN-04)"
    - "pd.to_datetime(..., utc=True, errors='coerce', format='ISO8601') plus a mergesort for stable, spelling-independent time order"
    - "Best-effort cleaning: a cleaning exception logs one WARNING and rates the city with empty history"

key-files:
  created:
    - backend/data_cleaning.py
    - backend/tests/cleaning_pipeline_test.py
    - backend/tests/data_cleaning_test.py
  modified:
    - backend/city_pipeline.py
    - backend/historical_archive.py
    - backend/tests/predictive_tracer_test.py

key-decisions:
  - "Cleaning never writes and never changes a cell; the marker (clean_flags, clean_excluded) is on the cleaned frame only, because ARCHIVE_COLUMNS is imported by forecast_training and the shadow collection"
  - "CSV append is first-write-wins on the exact (city, UTC instant); this is CSV-only and differs on purpose from OD-7 (Postgres: hour-truncated run slot, same-slot retry overwrites)"
  - "A clean_history exception gives the forecast and detector an empty history (cold start) instead of unvetted history"
  - "The fallback-row filter moved from city_pipeline into data_cleaning with the same meaning (any-case text or bool true)"

patterns-established:
  - "clean_history(read_history(path, city=c), as_of=end) per city; read frame['clean_flags'] and report['flag_counts']"
  - "Write-side twin _parse_utc in historical_archive so its imports stay unchanged"

requirements-completed: [CLEAN-03, CLEAN-04]

coverage:
  - id: D1
    description: "Cleaning step between read_history and the forecast/detector in run_city_pipeline; the forecast and detector receive one cleaned frame; pipeline keeps its seven keys"
    requirement: CLEAN-03
    verification:
      - kind: integration
        ref: "backend/tests/cleaning_pipeline_test.py#test_rerunning_one_window_keeps_one_row_per_city_and_the_forecast_sees_cleaned_history"
        status: pass
      - kind: unit
        ref: "backend/tests/city_pipeline_test.py (Phase 1 pins, unchanged)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Rerunning one window through the orchestrator leaves one archive row per (city, datetime_utc); append_observation returns False for a taken slot in any ISO-8601 spelling"
    requirement: CLEAN-03
    verification:
      - kind: integration
        ref: "backend/tests/cleaning_pipeline_test.py#test_rerunning_one_window_keeps_one_row_per_city_and_the_forecast_sees_cleaned_history"
        status: pass
      - kind: unit
        ref: "backend/tests/predictive_tracer_test.py (two double-append tests, second row one hour later)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Cleaned rows carry clean_flags and clean_excluded; clean_history never changes a cell, adds or drops a row, or writes"
    requirement: CLEAN-04
    verification:
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py#test_cleaning_never_changes_a_cell_and_never_mutates_its_input"
        status: pass
      - kind: unit
        ref: "backend/tests/cleaning_pipeline_test.py#test_a_pipeline_run_never_rewrites_the_archive"
        status: pass
    human_judgment: false
  - id: D4
    description: "Rules for unparseable timestamp, duplicate instant and fallback row, multi-flag ordering, empty edge, ValueError cases and the report shape"
    requirement: CLEAN-03
    verification:
      - kind: unit
        ref: "backend/tests/data_cleaning_test.py (8 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "A clean_history exception never takes the rating down: one WARNING naming the city and 'cold start', city rated, empty history to forecast and detector"
    requirement: CLEAN-03
    verification:
      - kind: unit
        ref: "backend/tests/cleaning_pipeline_test.py#test_cleaning_failure_rates_the_city_with_no_history"
        status: pass
    human_judgment: false
  - id: D6
    description: "ARCHIVE_COLUMNS, ARCHIVE_SCHEMA_VERSION and _validation_row are AST-identical to 5efe97d and the frozen shadow-read modules are untouched"
    requirement: CLEAN-03
    verification:
      - kind: other
        ref: "AST comparison against git show 5efe97d:backend/historical_archive.py; git diff --quiet 5efe97d over the frozen modules"
        status: pass
    human_judgment: false

duration: 22min
completed: 2026-10-20
status: complete
---

# Phase 2 Plan 01: Cleaning Tracer Summary

**A read-time `data_cleaning.clean_history` (bad timestamp, duplicate instant, fallback row, marker columns) now sits between `read_history` and the forecast/detector in `city_pipeline`, and `append_observation` refuses a second CSV row for a (city, UTC instant) slot in any ISO-8601 spelling.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-10-20T05:08:00Z (approx.; plan ledger written 05:12:56Z)
- **Completed:** 2026-10-20T05:31:00Z
- **Tasks:** 2
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments

- `backend/data_cleaning.py` (168 lines): `clean_history(history, as_of=None)` returns `CleanedHistory` with `frame` (every input row, stable-sorted by parsed UTC time, `clean_flags` and `clean_excluded` appended), `usable` and a `report` (policy version, row counts, a count per flag, canonical `as_of`). It raises `ValueError` for a multi-city frame or an unparseable `as_of`.
- `city_pipeline.run_city_pipeline` cleans after `read_history`, logs one INFO line per city, and on a cleaning exception logs one WARNING ("cold start") and rates the city with empty history. The `pipeline` dict keeps its seven keys.
- `historical_archive`: `_slot_archived` guards `append_observation` (first write wins, returns False); `read_history` uses a stable sort on parsed time (unparseable last); the module docstring marks first-write-wins as CSV-only and names OD-7 as the Postgres rule.
- 11 new offline tests (tracer, 8 rule/invariant tests, cold-start fallback, archive-never-rewritten). Full suite: 1297 passed (1286 Phase 1 baseline + 11), 0 failed, nothing written under `data/` or `outputs/`.

## Task Commits

1. **Task 1: Tracer - rerun one window through the orchestrator; one row per slot, forecast sees cleaned, marked history** - `3a15fb9` (feat)
2. **Task 2: Unit tests for the three tracer rules and the CLEAN-04 invariant; cleaning failure degrades to cold start** - `e33196b` (test)

**Plan metadata:** committed separately (docs: complete cleaning tracer plan)

## Files Created/Modified

- `backend/data_cleaning.py` - the cleaning step: rules, marker columns, report
- `backend/city_pipeline.py` - calls `data_cleaning.clean_history(history, as_of=end)`; cold-start fallback on failure
- `backend/historical_archive.py` - `_parse_utc`, `_slot_archived`, slot guard in `append_observation`, stable parsed-time sort in `read_history`, docstrings
- `backend/tests/cleaning_pipeline_test.py` - tracer, cold-start fallback and read-only tests (3 tests)
- `backend/tests/data_cleaning_test.py` - 8 unit tests
- `backend/tests/predictive_tracer_test.py` - second append of two double-append tests moved one hour later

## Fixture reconciliations

- `backend/tests/predictive_tracer_test.py`: `test_two_appends_produce_one_header_line_and_two_data_lines` and `test_two_appends_read_history_returns_two_rows` appended the same `datetime_utc` twice; CLEAN-03 now refuses that. The second append uses `datetime_utc="2026-01-01T01:00:00"` (fixture data only, as the plan specified). The asserted outcomes (`is True`, 3 lines, 2 rows) are unchanged.
- `backend/tests/city_pipeline_test.py`: none needed. Its stand-in frame already has distinct hourly timestamps. A diff of its `assert` lines against the last `test(01-03)` commit is empty.

## Decisions Made

- Cleaning is read-time only; the marker is not persisted (see key-decisions).
- First-write-wins is a CSV-only rule; Phase 4 follows OD-7.
- A failed cleaning step feeds empty history to G6, not unvetted history.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_parse_utc` index argument for list input**
- **Found during:** Task 1 (first run of the tracer test, before the commit)
- **Issue:** `index=getattr(values, "index", None)` returned the bound `list.index` method when `_slot_archived` passed a one-element list, so every append raised inside the best-effort try and returned False.
- **Fix:** `index=values.index if isinstance(values, pd.Series) else None` in both `data_cleaning._parse_utc` and `historical_archive._parse_utc`.
- **Files modified:** `backend/data_cleaning.py`, `backend/historical_archive.py`
- **Verification:** tracer test passes; fixed before the Task 1 commit
- **Commit:** `3a15fb9`

**2. [Rule 2 - Robustness] Slot guard reads `datetime_utc` with `.get`**
- **Found during:** Task 1
- **Issue:** A row without `datetime_utc` would raise `KeyError` in the new guard and stop being written, a behavior change the plan did not ask for.
- **Fix:** `_slot_archived` and the skip log line use `row.get("datetime_utc")`; such a row matches no slot and is written as before.
- **Commit:** `3a15fb9`

**Total deviations:** 2 auto-fixed (1 bug, 1 robustness), both inside Task 1 before its commit. **Impact:** none on scope.

### Discrepancies

- **Branch:** the working tree was on `main`, which the pre-commit protected-branch assertion refuses (`gsd query git.base-branch --is-protected main` returned true; `git.allow_default_branch_commits` is not set). I did not change config. Instead I created and committed on `gsd/production-pipeline-phase-02` (from `90aaacf`). The orchestrator needs to fast-forward `main` to it, or set `git.allow_default_branch_commits: true` for the sequential run.
- **Co-author trailer:** commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (the harness attribution line) rather than the `Claude Opus 5.5` text in the plan.
- **Task 2 TDD order:** the plan's Task 2 is `tdd="true"` but is specified as tests after the Task 1 code, so there is no RED commit and the new tests passed on first run. As a check that they discriminate, flipping the duplicate rule to `keep="last"` made 2 of the 8 unit tests fail; it was reverted before the commit. The plan is `type: execute`, so no plan-level TDD gate applies.
- **Full-suite runtime:** about 6.5 min (`test_city_isolation_never_serves_wrong_city_in_any_call_order` alone takes about 2 min). Two concurrent full runs stall on CPU contention; run one at a time.

## Issues Encountered

None beyond the items above.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or schema at a trust boundary; the threat register items T-02-01..05 are covered by the rules, the slot guard, the cold-start fallback, the AST and frozen-module checks, and the tmp_path-only tests.

## User Setup Required

None.

## Next Phase Readiness

Ready for 02-02 (append guard and read-order hardening tests) and 02-03 (stuck, spike and hourly-slot rules, the policy doc). `clean_history` already takes `as_of` from `city_pipeline`, so 02-03 needs no wiring change. The 12:00 row a pipeline run archives will be flagged by 02-03's gap rule; tests here deliberately do not assert on it.

## Self-Check: PASSED

- Created files exist: `backend/data_cleaning.py`, `backend/tests/cleaning_pipeline_test.py`, `backend/tests/data_cleaning_test.py` (FOUND).
- Commits `3a15fb9` and `e33196b` are ancestors of HEAD.
- Full suite: 1297 passed, 0 failed; `find data outputs -newer` empty.
- AST check, frozen-module diff and Phase 1 assert-line diff all pass.
