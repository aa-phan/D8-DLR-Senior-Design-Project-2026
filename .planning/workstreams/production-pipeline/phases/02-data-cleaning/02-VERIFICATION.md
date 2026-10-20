---
phase: 02-data-cleaning
verified: 2026-10-20T00:00:00Z
status: human_needed
score: 9/10 must-haves verified
covered_files:
  - ".planning/workstreams/production-pipeline/phases/02-data-cleaning/02-01-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/02-data-cleaning/02-01-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/02-data-cleaning/02-02-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/02-data-cleaning/02-02-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/02-data-cleaning/02-03-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/02-data-cleaning/02-03-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/02-data-cleaning/02-04-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/02-data-cleaning/02-04-SUMMARY.md"
  - "backend/city_pipeline.py"
  - "backend/data_cleaning.py"
  - "backend/historical_archive.py"
  - "backend/tests/city_pipeline_test.py"
  - "backend/tests/cleaning_pipeline_test.py"
  - "backend/tests/data_cleaning_test.py"
  - "backend/tests/historical_archive_test.py"
  - "backend/tests/predictive_tracer_test.py"
  - "docs/data-science/decisions/data_cleaning.md"
covered_digest: "v3:sha256:2c228b1a96c760e61a191d145e569791d02cdca46fda367bff05aa228400aaac"
behavior_unverified: 0
overrides_applied: 0
coincidental_reliance_items:
  - truth: "SC2 / gap guard: a skipped cycle is handled and the forecast is withheld only when the gap is real"
    reason: undeclared-precondition
    harden: "The gap tests use hour-aligned archive stamps. Production stamps each row with the run's `end`, floored to 5 minutes (`dlr_orchestrator._default_window`), not to the hour. Nothing enforces hour alignment, so run-time jitter across an hour boundary reads as a missing slot (review WR-04). Either enforce or document hour alignment of `end`, or measure gaps in elapsed time."
human_verification:
  - test: "Phase 3 (VAL-01/VAL-02) measures per-city flag rates for the provisional thresholds (STUCK_MIN_RUN_ROWS 6; SPIKE_MAX_STEP 10 degC, 10 m/s, 700 W/m2 per hour; MAX_TRAILING_GAP_SLOTS 1) on a backfilled real-data window. A reviewer should read those rates before anyone relies on the thresholds."
    expected: "Flag rates are plausible per city. In particular, wind stuck runs on calm nights (El Paso, Midland) are not removing legitimate calm hours in bulk (review WR-02), and run-time jitter is not producing spurious trailing gaps (WR-04)."
    why_human: "The plan tagged this truth `verification: backstop`. 'Physically reasonable for hourly Texas station data' cannot be shown by presence or wiring, and no held-out or property-based test exists. The thresholds were deliberately not fitted in Phase 2 (a prohibition), so the evidence is by design a Phase 3 deliverable."
---

# Phase 2: Data Cleaning Verification Report

**Phase Goal:** The history the forecast and detector consume is checked across rows and kept to one row per slot.
**Verified:** 2026-10-20
**Status:** human_needed
**Re-verification:** No, initial verification

## Verdict

The goal is achieved in code. Cleaning sits on the live path, the rules fire as documented, the archive cannot take a second row for a (city, instant), and cleaned rows are distinguishable from raw rows. Every roadmap success criterion is verified against the code, a direct probe and a mutation check, not against the SUMMARY claims. No blockers.

Status is `human_needed` for one reason only. The plan declared one truth as `verification: backstop` (the provisional thresholds are physically reasonable), which a presence check cannot establish. Phase 3 owns that evidence. The five review warnings are weighed below. None breaks a must-have, but WR-02 and WR-04 are real risks to carry into Phase 3.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1: A cleaning step sits between `read_history` and `forecast_ampacity` / `AnomalyDetector.for_city` in `city_pipeline`, and flags stuck runs and spikes under a written policy | VERIFIED | `city_pipeline.py:45-67` reads history, calls `data_cleaning.clean_history(history, as_of=end)`, reassigns `history = cleaned.usable`, and that one object feeds `forecast_ampacity` (line 75) and `AnomalyDetector.for_city` (line 99). `city_pipeline` is the only live consumer of `read_history` (grep: `backfill_archive` uses it only for resume). Probe: 6 identical `air_temp` rows flagged `stuck_air_temp` and excluded, a run of 5 not flagged, a 50 degC one-hour excursion flagged `spike_air_temp` and excluded. Policy is `docs/data-science/decisions/data_cleaning.md` (147 lines, every flag, constant, reasoning). |
| 2 | SC2: Missing hourly slots are handled by the documented strategy, and tests cover a skipped-cycle gap | VERIFIED | Strategy is mark-never-fill (doc `## Missing hourly slots`). Probe: hourly rows 00:00-09:00 minus 05:00 gives 9 rows kept, 06:00 row `after_gap` with `gap_slots` 1, `missing_slots` 1, nothing invented. End-to-end tests `test_one_skipped_cycle_inside_the_history_keeps_the_forecast_for_g6`, `test_the_previous_cycle_skipped_still_uses_the_forecast`, `test_two_skipped_cycles_before_the_run_withhold_the_forecast_from_g6`, `test_ml_forecast_across_a_gap_in_its_lookback_is_withheld` pass. Mutation check: making `forecast_gap_reason` always return None fails 4 tests, so the guard tests discriminate. Coincidental-reliance caveat on hour alignment, see frontmatter. |
| 3 | SC3: Appending an already-present (`city`, `datetime_utc`) never creates a second row, for `append_observation` and the orchestrator path | VERIFIED | `historical_archive.append_observation` calls `_slot_archived` before writing (lines 233-239) and returns False. Spellings Z, +00:00, naive, and an offset spelling are matched as parsed instants. Every archive write goes through `append_observation` (`city_rating.py:316`, the only caller). The orchestrator rerun test `test_rerunning_one_window_keeps_one_row_per_city_and_the_forecast_sees_cleaned_history` calls the real `dlr_orchestrator.run_dlr_pipeline` twice: second run reports `archived False` for every city and the 12:00 instant appears once. Mutation check: stubbing `_slot_archived` to False fails `test_append_refuses_a_second_row_for_the_same_city_and_instant_in_any_iso_spelling`. The read side also flags a duplicate instant (`duplicate`, probe shows 1 flagged). |
| 4 | SC4: Cleaned rows carry a marker that tells them apart from raw rows | VERIFIED | `MARKER_COLUMNS = (clean_flags, clean_excluded, gap_slots)` appended to the frame. Probe: after cleaning, all original columns are equal to the input (`frame[orig_columns].equals(orig)` is True), the input frame is unchanged, row count in equals row count out, and the three marker columns are last. Flags join with `\|` in `FLAG_ORDER`; `""` means untouched. |
| 5 | CLEAN-04 invariant: cleaning never changes a cell, adds or drops a row, or writes to any store | VERIFIED | Probe above. `clean_history` calls `history.copy()` and does no I/O. `test_a_pipeline_run_never_rewrites_the_archive` and the cell-invariance test pass. The only archive write is the pre-existing `rate_city` append. |
| 6 | A cleaning exception never takes the rating down (cold start, one WARNING) | VERIFIED | `city_pipeline.py:56-67` try/except sets empty history and `cleaned = None`; `test_cleaning_failure_rates_the_city_with_no_history` passes. |
| 7 | Forecast gap guard: a forecast built across too large a gap is computed and reported but not given to G6, with no new result keys | VERIFIED | `city_pipeline.py:88-99`: `forecast_gap_reason(cleaned.report, forecast_method)` sets `forecast_for_detector = None`, `pipeline["forecast"]` still reported, INFO line logged. `result["pipeline"]` keeps its seven keys. Boundary tests (trailing gap 1 used, 2 withheld; ml lookback 7) pass. Zero-width-band handling preserved (`test_zero_width_band_keeps_its_own_handling_when_the_history_is_also_stale`). |
| 8 | Frozen/contract files unchanged: `ARCHIVE_COLUMNS`, `ARCHIVE_SCHEMA_VERSION`, `_validation_row`, `ampacity_forecast.py`, `anomaly_detector.py`, `forecast_training.py`, `config.py`, `shadow_collect.yml` | VERIFIED | `git diff 5efe97d HEAD --stat` over those files is empty. The `historical_archive.py` diff touches only docstrings, the new `_parse_utc` / `_slot_archived`, the guard, and the read sort; none of the three protected names appear in a changed hunk except as context. `git diff main...HEAD --name-only` lists only the nine expected files (no `data/` or `outputs/`). |
| 9 | Written policy is pinned to the code (doc names every flag and constant; a test fails on disagreement) | VERIFIED | `test_policy_doc_names_every_flag_and_threshold` exists and passes; doc constants match the code (version 1, 6, 10/10/700, 1, 7). Weakness: single-digit numeric values are matched by substring (review WR-05), so the test would not catch every wrong value. The doc currently agrees with the code, so the truth holds today. |
| 10 | The provisional thresholds (6 rows; 10 degC, 10 m/s, 700 W/m2 per hour) are physically reasonable for hourly Texas station data | UNCERTAIN (insufficient_spec, backstop) | No held-out or property-based test and no real-data evidence. By design: the plan prohibits fitting thresholds in Phase 2, and Phase 3 (VAL-01/02) measures flag rates. Routed to human verification. |

**Score:** 9/10 truths verified (0 present-but-behavior-unverified; 1 backstop truth routed to human verification).

All behavior-dependent truths (rerun leaves one row, cleaning failure degrades to cold start, gap guard withholds only past the limit) are backed by tests that I ran and by mutation checks showing the tests fail when the behavior is removed.

### Prohibitions (judgment tier)

Plan frontmatter marks all as `resolved`. I checked each against the code rather than accepting that.

| Prohibition | Result |
|-------------|--------|
| Cleaning must not write back, change a cell or invent a row (CLEAN-04) | Held. Probe and `clean_history` read-only; no store import in `data_cleaning`. |
| Must not change `ARCHIVE_COLUMNS`, schema version, `_validation_row`, or frozen modules (CLEAN-03, CLEAN-01) | Held. Empty diff against 5efe97d. |
| Must not edit a pre-existing assert to pass, and no cleaning opt-out on the production path | Held with one noted change. `city_pipeline_test.py` changes fixture data only. `predictive_tracer_test.py` rewrites two double-append assert lines to use a second row one hour later; this was the planned fixture resolution (the old fixture contradicted CLEAN-03) and the assertion semantics (`is True`, 3 lines, 2 rows) are unchanged. No switch to disable cleaning exists in `run_city_pipeline`. |
| Must not overwrite or delete the stored CSV row on a slot conflict | Held. Append-only; OD-7 named in the module docstring as the Postgres rule only. |
| Must not tune thresholds on real archives | Held. Thresholds are stated judgments with reasoning in the doc; no read of `data/historical` or `outputs/`. |
| Must not fill a missing slot or impute | Held. Probe: no row invented, row counts equal. |
| Must not add result/pipeline keys, or write outside `tmp_path` | Held. Seven pipeline keys kept; tests use `tmp_path` and a no-network fixture. |

No prohibition is flagged unresolved.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/data_cleaning.py` | clean_history, CleanedHistory, FLAG_ORDER, EXCLUDING_FLAGS, MARKER_COLUMNS, forecast_gap_reason, constants | VERIFIED | 435 lines, all symbols present, no stubs. WIRED from `city_pipeline`. |
| `backend/city_pipeline.py` | cleaning call and gap guard | VERIFIED | `data_cleaning.clean_history(history, as_of=end)` and `data_cleaning.forecast_gap_reason(cleaned.report, forecast_method)` both present. |
| `backend/historical_archive.py` | slot guard and stable read order | VERIFIED | `_slot_archived`, `_parse_utc`, stable mergesort on parsed instant. |
| `backend/tests/data_cleaning_test.py` | rule boundary and doc tests | VERIFIED | 597 lines. |
| `backend/tests/cleaning_pipeline_test.py` | orchestrator tracer and skipped-cycle tests | VERIFIED | 425 lines, exercises real `run_dlr_pipeline`. |
| `backend/tests/historical_archive_test.py` | one-row-per-slot and ordering tests | VERIFIED | 239 lines added. |
| `docs/data-science/decisions/data_cleaning.md` | written policy and gap strategy | VERIFIED | 147 lines; contains `## Missing hourly slots` and `## Forecast use across gaps`. |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `city_pipeline.py` | `data_cleaning.py` | `data_cleaning.clean_history(history, as_of=end)` | WIRED |
| `city_pipeline.py` | `data_cleaning.py` | `data_cleaning.forecast_gap_reason(cleaned.report, forecast_method)` | WIRED |
| `historical_archive.append_observation` | archive CSV | `_slot_archived(...)` before write | WIRED |
| `city_rating._archive_city_result` | `append_observation` | single archive writer for orchestrator and backfill paths | WIRED |
| `data_cleaning.ML_LOOKBACK_ROWS` | `config.FORECAST_ML_LAG_HOURS` / `FORECAST_ML_ROLLING_WINDOW_HOURS` | read-only derivation, value 7 | WIRED |
| `data_cleaning_test.py` | `data_cleaning.md` | doc agreement test | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Real Data | Status |
|----------|---------------|--------|-----------|--------|
| `city_pipeline` forecast input | `history` (= `cleaned.usable`) | `read_history` on the archive CSV, then `clean_history` | Yes. The orchestrator tracer shows the forecast receives 1 of 3 archive rows with the cleaned markers. | FLOWING |
| `AnomalyDetector.for_city` | `history` | same object | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 5 phase test files | `pytest tests/data_cleaning_test.py tests/cleaning_pipeline_test.py tests/historical_archive_test.py tests/city_pipeline_test.py tests/predictive_tracer_test.py -q` | 96 passed | PASS |
| Stuck/spike/gap/duplicate/no-mutation probe | scratch script calling `clean_history` | stuck 6 flagged, run-of-5 not, spike flagged, gap marked, cells unchanged | PASS |
| Mutation: disable slot guard | stub `_slot_archived` to False, rerun archive tests | fails (spelling test) | PASS (tests discriminate) |
| Mutation: disable gap guard | stub `forecast_gap_reason` to None | 4 tests fail | PASS (tests discriminate) |
| Full suite | not re-run, per instruction | orchestrator reported 1349 passed, 0 failed on final HEAD | accepted |

### Probe Execution

Step 7c: SKIPPED. No probe scripts are declared in the plans or summaries.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CLEAN-01 | 02-03 | Cross-row flagging of stuck runs and spikes under a written policy | SATISFIED | Rules 6 and 7 in `clean_history`; policy doc; probe and boundary tests. Thresholds provisional (human item). |
| CLEAN-02 | 02-03, 02-04 | Documented gap strategy before forecast/detector consume history | SATISFIED | Mark-never-fill strategy, `after_gap` / `gap_slots`, report gap fields, `forecast_gap_reason`; skipped-cycle tests. |
| CLEAN-03 | 02-01, 02-02 | At most one row per (`city`, `datetime_utc`); rerun never appends a duplicate or conflicting row | SATISFIED | Append guard plus read-side `duplicate` rule; orchestrator rerun test; mutation check. |
| CLEAN-04 | 02-01, 02-03 | Cleaned rows stay distinguishable from raw rows | SATISFIED | `clean_flags`, `clean_excluded`, `gap_slots` markers; cells never changed. |

All four IDs in REQUIREMENTS.md for this phase (CLEAN-01..04, already ticked) appear in a plan's `requirements` field. No orphaned requirements. VAL-01/02/03 are Phase 3 and not claimed here.

### Anti-Patterns Found

None blocking. No TBD/FIXME/XXX markers in the changed files, no stubs, no console-only handlers. `deferred-items.md` records one item (the `_parse_utc` mixed-batch defect), marked resolved in 02-03 with a regression test.

### Review Findings Weighed Against the Goal

The disposition file lists all eight as `open`. None is a must-have failure. My weighing:

| ID | Breaks a must-have or the goal? | Assessment |
|----|---------------------------------|------------|
| WR-01 fallback row first blocks the later real reading | No. Plan truth 02-02 explicitly states "first-written row stays", and the doc states the CSV-only divergence. The effect is conservative (the hour becomes a missing slot, which is excluded and marked, not a silent overstatement). | Real operational weakness: a rerun cannot repair the one case where a rerun matters, and an `ml` forecast can be withheld for up to 7 hours. Decide in Phase 4 (OD-7 overwrite semantics fix this in Postgres) or relax the CSV guard to skip only computed rows. The doc does not yet list this under Known limitations. |
| WR-02 calm wind 0.0 flagged stuck | No. The plan truth and doc specify exactly this rule (only solar 0.0 exempt). Provisional by declaration. | Carry to Phase 3. Biases the learned baseline toward windy hours and can open gaps that withhold the forecast. This is the first thing Phase 3 should measure, and the doc already says so. |
| WR-03 stuck rule counts rows, not hours | No. Plan and doc define the run in consecutive usable rows. | Minor. Only matters in gap-ridden archives. |
| WR-04 hour-floored slots vs 5-minute-stamped rows | No for the stated requirements (CLEAN-03 key is the exact instant). Yes for production robustness: confirmed `_default_window` stamps rows at a 5-minute floor, so jitter across an hour boundary reads as a missing slot. The failure direction is conservative (forecast withheld from G6 and falls back to rolling baseline or cold start), never an overstated rating. | The strongest of the five. Recorded as a coincidental-reliance item. Address before Phase 5's scheduled runs (enforce hour-aligned `end`, or measure gaps by elapsed time). |
| WR-05 doc test matches numbers by substring | No. Doc agrees with code today. | Test-strength gap; fix cheaply. |
| IN-01..03 | No. | Twin parser drift risk, strict fallback spelling (unreachable from the writer), non-atomic check-then-append (best effort; read-side `duplicate` limits harm). |

## Human Verification Required

### 1. Provisional thresholds on real data

**Test:** During Phase 3 (VAL-01/VAL-02), read the per-city flag rates from `clean_history(read_history(path, city=c), as_of=None)` (`report["flag_counts"]`) over the backfilled window.
**Expected:** Stuck and spike rates are plausible for each city. Calm-night wind runs (El Paso, Midland) are not being removed in bulk, and run-time jitter is not creating spurious trailing gaps. If either occurs, adjust the thresholds or rules and bump `CLEANING_POLICY_VERSION`.
**Why human:** The truth is a `backstop` judgment about physical reasonableness. No test or code inspection can establish it, and Phase 2 is forbidden from fitting thresholds on real archives.

## Gaps Summary

No gaps. The phase goal is met: the history the forecast and detector consume is cleaned across rows, gap-aware and one row per slot. Before Phase 3 sign-off, three follow-ups are worth tracking (none block the phase):

1. WR-04: enforce or document hour alignment of the run `end` (or measure gaps by elapsed time) before scheduled live runs in Phase 5.
2. WR-02 / WR-03: let Phase 3's measured flag rates decide the wind exemption and whether the stuck run should require consecutive hours.
3. WR-01: add the "fallback row blocks a later real reading" consequence to `data_cleaning.md` Known limitations, or relax the guard.

---

_Verified: 2026-10-20_
_Verifier: Claude (gsd-verifier)_
