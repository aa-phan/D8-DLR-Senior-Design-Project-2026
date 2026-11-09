---
phase: 02-data-cleaning
plan: 02
subsystem: data-cleaning
tags: [pandas, archive, idempotent-append, csv, offline-tests, iso8601]

requires:
  - phase: 02-data-cleaning
    provides: "02-01: append_observation slot guard, read_history stable time sort, historical_archive._parse_utc"
provides:
  - "16 new tests (30 collected in the file) pinning the CSV one-row-per-(city, UTC instant) rule and read_history's stable UTC order"
  - "historical_archive._parse_utc parses explicit-offset and naive timestamps in separate batches, so mixed spellings sort and match correctly"
affects: [02-03-stuck-spike-slot-rules, 03-real-data-validation, 04-postgres-writer]

actuals:
  tokens: 2700
  tasks: 2
  commits: 2
plan_head_before: 9257fb5318023def09e39f99ae8279450e7a04ea
plan_head_after: 7bf8d10e7eeea6e184d2aab776f0c734bb671c2f

tech-stack:
  added: []
  patterns:
    - "Parse mixed-spelling ISO-8601 columns in two batches (explicit offset / naive) because pandas 2.3 carries an earlier value's offset into a later naive one"

key-files:
  created: []
  modified:
    - backend/tests/historical_archive_test.py
    - backend/historical_archive.py

key-decisions:
  - "The CSV first-write-wins rule stays CSV-only; test names and comments do not present it as the store-wide contract (OD-7 governs Postgres)"
  - "_parse_utc fix stays inside historical_archive.py; the same defect in data_cleaning._parse_utc is deferred to 02-03 (outside this plan's files)"

requirements-completed: [CLEAN-03]

coverage:
  - id: D1
    description: "append_observation refuses a second row for a (city, UTC instant) slot in Z, naive, +00:00 and +06:00 spellings; first write wins; other city or other instant is appended"
    requirement: CLEAN-03
    verification:
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_append_refuses_a_second_row_for_the_same_city_and_instant_in_any_iso_spelling"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_append_accepts_another_city_or_another_instant"
        status: pass
    human_judgment: false
  - id: D2
    description: "A refused slot logs one INFO line ('already archived') and no WARNING"
    requirement: CLEAN-03
    verification:
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_a_refused_slot_logs_one_info_line_and_no_warning"
        status: pass
    human_judgment: false
  - id: D3
    description: "Guard edges: corridor-era file, unparseable timestamps, pre-existing duplicates, missing/zero-byte file, unreadable slot check (False, one WARNING, file unchanged, no raise)"
    requirement: CLEAN-03
    verification:
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_slot_guard_matches_the_corridor_column_of_a_corridor_era_file"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_unparseable_timestamps_match_only_the_identical_string"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_a_file_that_already_holds_duplicates_still_refuses_a_third"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_first_append_to_a_missing_or_empty_file_writes_one_header"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_unreadable_slot_check_is_not_archived_and_does_not_raise"
        status: pass
    human_judgment: false
  - id: D4
    description: "read_history order: stable within an instant over 24 tied rows, by UTC instant across spellings, unparseable last; city filter and missing-file frame unchanged; a naive row after an offset row reads as UTC"
    requirement: CLEAN-03
    verification:
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_read_history_keeps_file_order_within_one_instant"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_read_history_orders_spellings_by_their_utc_instant"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_read_history_puts_unparseable_timestamps_last"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_read_history_city_filter_and_empty_file_keep_working"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_a_naive_timestamp_after_an_offset_timestamp_still_reads_as_utc"
        status: pass
    human_judgment: false
  - id: D5
    description: "ARCHIVE_COLUMNS, ARCHIVE_SCHEMA_VERSION and _validation_row are AST-identical to 5efe97d"
    requirement: CLEAN-03
    verification:
      - kind: other
        ref: "AST comparison against git show 5efe97d:backend/historical_archive.py (prints 'shadow-facing definitions unchanged')"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-10-20
status: complete
---

# Phase 2 Plan 02: Archive Guard Hardening Summary

**Sixteen offline tests pin the CSV one-row-per-(city, UTC instant) rule and `read_history`'s stable UTC order, and they exposed one real defect: pandas 2.3 applied an earlier row's `+06:00` to a later naive timestamp, which `historical_archive._parse_utc` now avoids by parsing explicit-offset and naive values in separate batches.**

## Performance

- **Duration:** 9 min (about 6 of them the full suite)
- **Completed:** 2026-10-20T05:41:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Task 1: eight tests (eleven collected) for `append_observation`: four ISO spellings of one instant refused with the first row kept, other city / other instant accepted, one INFO and no WARNING on a refusal, corridor-era files matched on `corridor`, unparseable timestamps matched by identical string only, a file with two existing duplicates still refuses a third, missing and zero-byte files get one header, an unreadable slot check returns False with one `append failed (non-fatal)` WARNING and an untouched file.
- Task 2: four `read_history` order tests (24 tied rows keep file order, spellings sort by UTC instant, unparseable last, city filter and missing-file frame) plus one regression test for the defect below.
- Discrimination checks (reverted before commit): comparing the slot by string made 4 Task 1 tests fail; a quicksort without the parsed key made the tie-order, spelling-order and city-filter tests fail.
- Full suite: 1314 passed, 0 failed (6 min); nothing written under `data/` or `outputs/`.

## Task Commits

1. **Task 1: Append guard edges** - `40409f9` (test)
2. **Task 2: read_history order, plus the `_parse_utc` fix** - `7bf8d10` (test)

**Plan metadata:** committed separately (docs: complete archive guard hardening plan)

## Files Created/Modified

- `backend/tests/historical_archive_test.py` - 16 new tests under two section headers (253 to 472 lines)
- `backend/historical_archive.py` - `_parse_utc` split into explicit-offset and naive batches; new `_EXPLICIT_OFFSET` pattern

## Decisions Made

- The fix lives in `_parse_utc`, so `_slot_archived` and `read_history` both pick it up; the single-try shape of `append_observation` and the log wording are unchanged.
- The explicit-offset pattern requires a time of day before the offset, so a date-only value like `2026-01-02` is never mistaken for one carrying `-02`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Mixed offset and naive timestamps misparsed by `_parse_utc`**
- **Found during:** Task 2 (`test_read_history_orders_spellings_by_their_utc_instant`)
- **Issue:** `pd.to_datetime(series, utc=True, format="ISO8601")` on pandas 2.3.3 applies the offset of an earlier value to a later naive (or date-only) value in the same call: `["...06:00:00+06:00", "...00:30:00"]` gave 00:00 and 18:30 the previous day. `read_history` then sorted the naive row first, and `_slot_archived` could miss a duplicate whose existing row was naive and followed an offset row.
- **Fix:** `_parse_utc` classifies each value with a regex for a time of day plus explicit offset and parses the two groups in separate calls, then reassembles by position. A 20k-row column parses in about 6 ms (a per-value loop took about 1 s).
- **Files modified:** `backend/historical_archive.py`
- **Verification:** the spelling-order test and the new `test_a_naive_timestamp_after_an_offset_timestamp_still_reads_as_utc` fail on the 02-01 code and pass now; AST check passes.
- **Commit:** `7bf8d10`

**2. [Rule 1 - Test data] City-filter test used out-of-range `dlr_amps`**
- **Found during:** Task 2, first run
- **Issue:** My draft rows used `dlr_amps` 1.0 to 9.0, which `read_history`'s default validation drops (range 100-4000 A).
- **Fix:** values 1101, 1102, 1900. Test-only, before the commit.

**Total deviations:** 2 auto-fixed (1 code bug, 1 test-data slip). **Impact:** one code change in `_parse_utc`, inside the files and the "fix only where a test exposes a defect" allowance.

### Discrepancies

- **Code fix to 02-01's code:** `historical_archive._parse_utc` (described above). No change to `ARCHIVE_COLUMNS`, `ARCHIVE_SCHEMA_VERSION`, `_validation_row` or `build_archive_row`.
- **Same defect left in `backend/data_cleaning.py::_parse_utc`:** confirmed (`["2026-01-01T06:00:00+06:00", "2026-01-01T00:00:00"]` parses to 00:00 and 2025-12-31 18:00). It is outside this plan's `files_modified`, so it is logged in `deferred-items.md` for 02-03, which edits `data_cleaning.py`.
- **Regression test placement:** the guard-level regression test for the fix was added in the Task 2 commit (with the fix), not the Task 1 commit, so the fix and its test land together.
- **Task order / TDD:** both tasks are `tdd="true"` but specified as tests over existing 02-01 code; all Task 1 tests passed on first run and only Task 2's spelling test failed, which is the defect above. The plan is `type: execute`, so no plan-level RED/GREEN gate applies.
- **Co-author trailer:** `Claude Sonnet 5.5` (harness attribution) rather than the `Claude Opus 5.5` text in the plan, as in 02-01.
- **Test count:** the plan counts 12 test functions / 15 collected; this plan added 13 functions / 16 collected (the extra one is the `_parse_utc` regression test). The file now collects 30 tests.

## Issues Encountered

None beyond the items above.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema; T-02-06 (re-spelled timestamp) and T-02-07 (malformed archive) are covered by the spelling and unreadable-file tests, and tests write only under pytest `tmp_path`.

## User Setup Required

None.

## Next Phase Readiness

Ready for 02-03. Pick up the `data_cleaning._parse_utc` fix from `deferred-items.md` while editing that module.

## Self-Check: PASSED

- `backend/tests/historical_archive_test.py` and `backend/historical_archive.py` exist; the 13 named test functions are present once each.
- Commits `40409f9` and `7bf8d10` are ancestors of HEAD; `git rev-list --count` from the ledger base reports 2.
- Verify commands exit 0; AST check prints "shadow-facing definitions unchanged"; full suite 1314 passed.
