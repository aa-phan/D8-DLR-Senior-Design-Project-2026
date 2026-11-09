---
phase: 02-data-cleaning
reviewed: 2026-10-20T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - backend/city_pipeline.py
  - backend/data_cleaning.py
  - backend/historical_archive.py
  - backend/tests/city_pipeline_test.py
  - backend/tests/cleaning_pipeline_test.py
  - backend/tests/data_cleaning_test.py
  - backend/tests/historical_archive_test.py
  - backend/tests/predictive_tracer_test.py
  - docs/data-science/decisions/data_cleaning.md
findings:
  critical: 0
  warning: 5
  info: 3
  total: 8
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-10-20
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the Phase 02 diff against `main`. The five phase test files (96 tests) pass. I probed `clean_history` and `append_observation` directly with edge cases: empty frame, all-bad timestamps, numeric timestamps, mixed offset and naive spellings, odd `as_of` values, non-default and duplicate index labels, and input mutation. They behaved as documented, and I found no crash, no look-ahead leak and no input mutation.

The findings below are all behavioral, not crashes. Four are rule or design choices that discard valid data or can wrongly withhold the forecast from G6, and each was confirmed by a repro. One is a weakly asserting test.

No structural (fallow) findings were supplied.

## Warnings

### WR-01: First-write-wins lets a fallback row permanently block the real reading for its slot

**File:** `backend/historical_archive.py:233-239`
**Issue:** A fallback cycle is exactly the case where a transient provider outage produced no usable reading. If the operator reruns the same window, `append_observation` refuses the good row because the fallback row already holds the (city, instant). Repro: append a row with `fallback=True`, then the same instant with `fallback=False`. The second call returns False and the file keeps only the fallback row. Cleaning then excludes that slot (`fallback`), so the hour is a permanent hole. A hole inside the lookback also withholds an `ml` forecast from G6 for up to 7 hours (`ML_LOOKBACK_ROWS`). The CSV guard is therefore inconsistent with its own stated purpose ("reruns and backfill resumes are safe"): a rerun can never repair the one case where a rerun matters.
The read side has the same inconsistency. `duplicate` runs before `fallback` and ignores fallback status, so if a fallback row precedes a computed row at one instant, the computed row is flagged `duplicate`. Repro: `['fallback', 'duplicate']`. Rule 5 (`same_hour`) was deliberately made fallback-aware, but rule 2 was not.
**Fix:** Make the slot guard skip only when the existing row at that instant is a computed (non-fallback) row. Then a computed row may be appended after a fallback row. In `data_cleaning`, evaluate `duplicate` over the non-fallback rows, or order `fallback` before `duplicate`, so a computed row can own the instant. If first-write-wins is intended regardless, state this consequence in `data_cleaning.md` under Known limitations.

### WR-02: Wind-speed stuck rule has no exemption for calm (0.0), so legitimate calm nights are excluded

**File:** `backend/data_cleaning.py:50-52` (`STUCK_EXEMPT_VALUES`)
**Issue:** Only `solar_radiation` has an exempt value. The archived `wind_speed` is the line-perpendicular component. It is 0.0 on any calm hour, and common station resolution makes calm reports exactly 0. Repro: 10 hourly rows with `wind_speed=0.0` give `stuck_wind_speed=10`, so all of them are excluded. Calm nights are the periods where a rating is least wind-cooled, so removing them from the forecast and detector baseline biases learning toward windy conditions. The policy doc admits Phase 3 is "expected to look first at wind stuck runs on calm nights", so the risk is known. It still ships active, and it affects what G6 learns from now.
**Fix:** Add `"wind_speed": (0.0,)` to `STUCK_EXEMPT_VALUES` (and bump `CLEANING_POLICY_VERSION`), or do not apply the stuck rule to `wind_speed` until Phase 3 has measured flag rates. Either way, update the policy doc table.

### WR-03: Stuck-run rule counts rows, not hours, so sparse data is judged stuck across days

**File:** `backend/data_cleaning.py:173-187`
**Issue:** `_stuck_mask` runs over the live row sequence and ignores `slot_hours`. The docstring, doc and constant reasoning all speak of "six identical hourly readings". Repro: 7 rows at one per day, all with `air_temp=20.0`, give `stuck_air_temp=7`. In a gap-ridden archive (the case `after_gap` exists for), six whole-degree-identical rows that are days apart are legitimately possible, and this rule excludes them. Row-based runs also let rows excluded by other rules bridge a run (documented, but combined with this they widen it).
**Fix:** Break a run where the hour difference between consecutive live rows is greater than 1. For example, start a new `run_id` when `hours.diff() != 1`, in addition to the value change, and pass `slot_hours` into `_stuck_mask`. Alternatively document explicitly that run length is measured in rows regardless of elapsed time.

### WR-04: Gap and trailing-gap logic uses hour-floored slots, so normal run-time jitter looks like a missing hour

**File:** `backend/data_cleaning.py:306, 362-367, 385-388`
**Issue:** The slot is `floor("h")` of `datetime_utc`. `dlr_orchestrator._default_window` sets `end` to now floored to 5 minutes, and the archive row is stamped with `end`. If a scheduled run lands at `18:58` one hour and `20:02` the next (ordinary scheduler or retry jitter, about 64 minutes apart), the slots are 18 and 20. The result is `gap_slots=1`, `trailing_gap_slots` may reach 1 or more, and for `ml` the contiguous tail resets. One late run can therefore withhold the forecast from G6 for 7 hours (`ML_LOOKBACK_ROWS`), though no hour of data is actually missing. The same jitter does the reverse and produces two rows in one slot, where `same_hour` silently drops one.
**Fix:** If runs are guaranteed hour-aligned, say so in `data_cleaning.md` and enforce it where `end` is built. Otherwise measure gaps in elapsed time. For example, treat consecutive usable rows as contiguous when their time difference is less than about 1.5 h, and derive `trailing_gap_slots` from `as_of - newest` in the same way.

### WR-05: Policy-doc pinning test matches numeric values by substring, so it passes with a wrong value

**File:** `backend/tests/data_cleaning_test.py:565-596` (`line_has`, used for int/float constants)
**Issue:** `line_has(f"`{name}`", str(value))` is a substring test. For `MAX_TRAILING_GAP_SLOTS = 1`, `CLEANING_POLICY_VERSION = 1` and `ML_LOOKBACK_ROWS = 7`, the string "1" or "7" appears in almost any line that names the constant (for example `| 10 |` or `| 17 |`). If the doc said 10 while the code said 1, the test would still pass. The test's stated purpose ("pinned to the code by a test") is not met for the single-digit constants.
**Fix:** Match the value as a whole table cell, for example `re.search(rf"\|\s*{re.escape(str(value))}\s*\|", line)`, or compare the parsed value in the doc's constants table.

## Info

### IN-01: `_parse_utc` and `_EXPLICIT_OFFSET` are duplicated verbatim in two modules

**File:** `backend/data_cleaning.py:112-141`, `backend/historical_archive.py:127-158`
**Issue:** The two copies are described as "twins". `data_cleaning` cannot import `historical_archive` because it is meant to be storage-agnostic. The twins will drift, and the offset-batching fix has already had to be applied to both (see `deferred-items.md`). A change to one that misses the other would make the write-side dedup and the read-side sort disagree on which rows share an instant.
**Fix:** Move the parser to a small shared module with no storage dependencies (for example `time_parse.py`). Import it from both modules. Alternatively, add a test that runs the same mixed-spelling inputs through both functions and asserts equal results.

### IN-02: `fallback` matching only recognises the text "true" (any case)

**File:** `backend/data_cleaning.py:314-318`
**Issue:** Values such as `"1"`, `"yes"` or `1` are not treated as fallback. Repro: `fallback=["1","yes"]` gives no `fallback` flag. The writer only emits a bool, so this is unreachable from the pipeline, but the rule guards a latch (the static rating learned as a real reading). A hand-edited or Postgres-exported archive could use another spelling.
**Fix:** Either accept `{"true", "1", "t", "yes"}`, or state the strict contract in the docstring and `data_cleaning.md`.

### IN-03: Slot-guard check-then-append is not atomic

**File:** `backend/historical_archive.py:233-253`
**Issue:** `_slot_archived` and the append are separate steps with no lock. Two concurrent writers for the same city and instant (a backfill alongside a live run) can both pass the check and both append. The read-side `duplicate` rule limits the damage, so this is not data corruption. It means "at most one row per (city, instant)" in the module docstring is a best-effort guarantee, not an invariant.
**Fix:** Soften the docstring wording to "best effort", or take an advisory file lock (for example `fcntl.flock`) around check and append.

---

_Reviewed: 2026-10-20_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
