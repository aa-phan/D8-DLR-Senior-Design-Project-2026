---
phase: 02-data-cleaning
verified: 2026-10-20T23:00:00Z
status: passed
score: 9/10 must-haves verified (the 10th, a backstop truth, is deferred to Phase 3 by owner disposition)
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
covered_digest: "v3:sha256:f48a7c180daa59ea3b6b50c7703f2b3e58fdff1f3cd0ce150b98af07b7639887"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 9/10
  gaps_closed:
    - "Coincidental reliance: hour alignment of archive stamps (WR-04) is now a declared precondition with a pinning test"
    - "Review WR-01..WR-05 and IN-01..IN-03 fixed in 88e3229 and verified independently below"
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "The provisional thresholds (6 rows; 10 degC, 10 m/s, 700 W/m2 per hour) are physically reasonable for hourly Texas station data"
    addressed_in: "Phase 3 (VAL-01/VAL-02), by owner disposition in 02-UAT.md (test 1, skipped with a 'Deferred follow-up:' reason, 2026-10-20)"
    evidence: "02-UAT.md: 'Carry to Phase 3: measure per-city flag rates for policy v2 thresholds on the 2026-09-08..09-28 backfill (VAL-01/VAL-02) and adjust thresholds there'. Caveat: no Phase 3 plan names cleaning flag rates yet, see Advisory."
advisory:
  - finding: "No Phase 3 plan (03-01..03-05) names per-city cleaning flag rates (stuck_*, spike_*, after_gap) as a deliverable. The deferral rests on the owner's UAT note and the policy doc's own 'Phase 3 is expected to look first at...' line, not on a Phase 3 success criterion."
    category: other
    reason: "Owner-deferred truth needs a carrier or it can be lost. Suggest adding a flag-rate table from clean_history(...).report['flag_counts'] to the 03-04 validation doc, or a line to 03-01's analysis CLI."
    evidence_status: "grep of phases/03-real-data-validation/*-PLAN.md finds clean_history API references only, no flag-rate measurement task"
  - finding: "Hour alignment (WR-04) is documented and pinned, not enforced. The hh:05 UTC live dispatch the doc relies on is a Phase 5 matter and is not yet stated in any Phase 5 requirement or plan."
    category: other
    reason: "A run that slips past the next hour boundary still reads as a missing slot (conservative: the forecast is withheld from G6, never an overstated rating). Phase 5 should carry the dispatch-minute constraint."
    evidence_status: "grep for hh:05 / dispatch minute in ROADMAP.md, REQUIREMENTS.md and phases/05*/ finds nothing"
---

# Phase 2: Data Cleaning Verification Report

**Phase Goal:** The history the forecast and detector consume is checked across rows and kept to one row per slot.
**Verified:** 2026-10-20
**Status:** passed
**Re-verification:** Yes, after commit 88e3229 (review fixes WR-01..WR-05, IN-01..IN-03, cleaning policy v2), 47da432 (UAT disposition) and 09541aa (CLEAN-03 and SC3 owner exception)

## Verdict

The goal is achieved in code and the review fixes hold. I read the changed code and tests, ran the five phase test files (103 passed, up from 96) and the full workspace suite once (1356 passed, 0 failed), ran a direct probe of the new behavior, and ran ten mutation checks in a scratch copy under `/tmp` (no source file was edited). Every mutation that should be caught by a test was caught.

The one prior human-verification item (provisional thresholds physically reasonable on real data) is a `backstop` truth. I accept the owner's deferral to Phase 3 as its disposition and did not re-route it to human verification. Reasons it is legitimate: the owner holds that authority; Phase 2 is forbidden from fitting thresholds on real archives, so the evidence cannot exist before Phase 3's backfill; the UAT file is `status: complete` with the test `skipped` and a `Deferred follow-up:` reason; and the thresholds are labeled provisional in code and in the policy doc, with `CLEANING_POLICY_VERSION` there to record any change. I found one reason to qualify it, which is not a blocker: no Phase 3 plan yet carries the flag-rate measurement (see Advisory in the frontmatter).

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1: A cleaning step sits between `read_history` and `forecast_ampacity` / `AnomalyDetector.for_city`, flagging stuck runs and spikes under a written policy | VERIFIED | Unchanged since the prior report except rule bodies. `city_pipeline` calls `data_cleaning.clean_history(history, as_of=end)` and feeds `cleaned.usable` to both consumers. Policy doc `docs/data-science/decisions/data_cleaning.md` is version 2 and agrees with the code (pinning test, mutation-checked, see below). Probe: 6 identical `air_temp` on consecutive hours flag `stuck_air_temp`, 5 do not. |
| 2 | SC2: Missing hourly slots handled by the documented strategy, with a skipped-cycle test | VERIFIED | Mark-never-fill unchanged. Probe: a stuck run split by a missing hour gives `after_gap` and no stuck flag; no row invented. The four skipped-cycle gap-guard tests in `cleaning_pipeline_test.py` still pass. Hour-alignment precondition now declared, see the coincidental-reliance check below. |
| 3 | SC3: Appending an already-present (`city`, `datetime_utc`) never creates a second row for `append_observation` and the orchestrator path, with the owner exception that a computed row may follow a fallback row | VERIFIED | Probe against the real `append_observation` on a tmp CSV, each result as expected: fallback first then computed (any spelling) appends; computed after computed refused; fallback after any row refused; a new slot appends. Resulting file holds fallback 1825.0 and computed 1300.0 for the repaired instant. `read_history` then `clean_history` flags the fallback row `fallback` and keeps the computed row; the second computed row is the only `duplicate`. ROADMAP SC3 and REQUIREMENTS CLEAN-03 both carry the dated exception (commit 09541aa), so the code and the contract agree. Orchestrator rerun test (`cleaning_pipeline_test.py`) still passes. |
| 4 | SC4: Cleaned rows carry a marker distinguishing them from raw rows | VERIFIED | `clean_flags`, `clean_excluded`, `gap_slots` appended; probe output shows the three columns and the original columns unchanged. Unchanged by 88e3229. |
| 5 | CLEAN-04 invariant: cleaning never changes a cell, adds or drops a row, or writes to any store | VERIFIED | `frame = history.copy().reset_index(drop=True)`, no I/O in `data_cleaning`. Cell-invariance and no-archive-rewrite tests pass. `git status` shows no change under `data/` or `outputs/`. |
| 6 | A cleaning exception never takes the rating down | VERIFIED | `city_pipeline_test` cleaning-failure test passes (unchanged file). |
| 7 | Forecast gap guard withholds a gap-built forecast from G6 only past the limit, with no new result keys | VERIFIED | `city_pipeline.py` unchanged in 88e3229; boundary tests pass. |
| 8 | Frozen and contract files unchanged | VERIFIED | `git diff 5efe97d HEAD` over `ampacity_forecast.py`, `anomaly_detector.py`, `forecast_training.py`, `config.py`, `shadow_collect.yml` is empty. No changed hunk in `historical_archive.py` touches `ARCHIVE_COLUMNS`, `ARCHIVE_SCHEMA_VERSION` or `_validation_row`. `git diff main...HEAD --name-only` outside `.planning` lists only the nine expected files. |
| 9 | Written policy is pinned to the code (a test fails on disagreement) | VERIFIED | WR-05 fixed: `line_has(..., cells=[...])` matches values as whole table cells. Mutation: setting the doc's `MAX_TRAILING_GAP_SLOTS` cells to 10 (both tables) fails `test_policy_doc_names_every_flag_and_threshold`; setting `ML_LOOKBACK_ROWS` 7 to 17 fails it. (A first attempt that changed only one of the two doc tables survived, because the constant is stated in two tables and either line satisfies the test. That is a narrow remaining softness, noted, not a failure: any single wrong table row still has to be accompanied by a correct one.) |
| 10 | The provisional thresholds are physically reasonable for hourly Texas station data | DEFERRED (backstop, owner disposition) | No real-data evidence is possible in Phase 2. Owner deferred it to Phase 3 in 02-UAT.md. Not counted as verified; not routed to human verification; see Verdict and Advisory. |

**Score:** 9/10 truths verified; 1 backstop truth deferred by the owner; 0 present-but-behavior-unverified.

### Re-verification of the Review Fixes (independent of commit messages)

| ID | Owner decision / fix | Evidence | Mutation check (scratch copy) |
|----|----------------------|----------|-------------------------------|
| WR-01 | A computed row may follow a fallback row for its instant, on the write guard and the read-side `duplicate` rule | Probe above. Code: `_slot_archived` ignores fallback rows when the new row is computed, blocks everything when the new row is fallback; `duplicate` is `parsed[computed].duplicated(keep="first")` reindexed to the frame (index is reset first, so duplicate labels cannot break the reindex). Docs and docstrings state it. | Guard stops considering fallback (computed-after-fallback refused): `test_a_computed_row_may_follow_a_fallback_row_for_its_instant` fails. Guard lets a fallback follow a computed row: both new archive tests fail. Read-side `duplicate` over all rows: `test_a_computed_row_owns_its_instant_even_after_a_fallback_row` fails. |
| WR-02 | Calm wind 0.0 exempt from the stuck rule | Probe: 12 hours of `wind_speed` 0.0 unflagged; 6 of 3.0 flagged; 0.0 x3 then 3.0 x6 flags only the six 3.0 rows. Solar 0.0 still exempt. | Removing the `wind_speed` exemption fails `test_calm_wind_is_not_a_stuck_run`. |
| WR-03 | A missing hour ends a stuck run; excluded rows still bridge | Probe: same value on 7 days at one hour per day is unflagged; 6 identical with a middle hour missing is unflagged; a run bridged by a fallback row still flags 6. | Ignoring contiguity fails `test_a_missing_hour_ends_a_stuck_run`; breaking the held-hour bridge (requiring a 1-hour step) fails `test_a_stuck_run_spans_rows_already_excluded`. |
| WR-04 | Documented hour alignment (slot is the run end's own hour, OD-7) plus a pinning test, no logic change | See coincidental-reliance check below. Confirmed no logic change: slots are still `parsed.dt.floor("h")`. | Replacing `floor("h")` with `round("h")` fails `test_a_row_belongs_to_its_run_ends_own_hour` and `test_rows_sharing_an_hour_keep_the_latest`. |
| WR-05 | Doc test matches values as whole table cells | Truth 9 above. | Two doc mutations caught. |
| IN-01 | Parity test across the two `_parse_utc` twins | `test_read_and_write_side_parsers_agree` runs ten spellings (Z, +00:00, +06:00, naive, fractional, -0600, date only, garbage, empty, NaN) through both and compares series. | A write-side parser that strips offsets fails the parity test and two archive tests. (A first divergent parser using `format="mixed"` produced identical output on these inputs and survived; it was not a real divergence.) |
| IN-02 | Strict "true" contract documented | Doc rule 3 and the `fallback` table row state it; code comment matches. | n/a (documentation) |
| IN-03 | Guard described as best effort | Module docstring, `append_observation` docstring and doc "Best effort" bullet say so. | n/a (documentation) |

### Coincidental-Reliance Check (hour alignment)

The previous report's item was an undeclared precondition: the gap tests used hour-aligned stamps while production stamps rows with a 5-minute-floored `end`. It is now declared, not removed:

- `docs/data-science/decisions/data_cleaning.md` has a new `## Hour alignment` section stating that a row's slot is the run end's own hour (the same rule as OD-7's `valid_time`), that gaps are counted in slots rather than elapsed time, that the live schedule is expected to dispatch at hh:05 UTC, and exactly what happens when a run slips past an hour boundary (next row `after_gap`, `ml` forecast withheld from G6 until the lookback is unbroken; two runs in one hour leave one row via `same_hour`). It is also listed under Known limitations.
- `test_a_row_belongs_to_its_run_ends_own_hour` pins it: stamps at 10:05, 11:40, 12:55, 13:10 with `as_of` 14:05 give no flags, `trailing_gap_slots` 0 and 4 contiguous tail rows; stamps at 10:55 and 12:00 give `after_gap`. It fails under `round("h")` (mutation M7), so it discriminates.
- I confirmed the premise against the code: `dlr_orchestrator._default_window` floors now to 5 minutes, and OD-7 in REQUIREMENTS.md defines `valid_time` as the hour-truncated UTC run slot.

Because the precondition is now stated, tested and consistent with the owner's OD-7, it no longer qualifies as coincidental reliance under the "undeclared" criterion. It is still not enforced in code, and the hh:05 dispatch is not yet written into any Phase 5 requirement or plan. Recorded as an advisory, not a gap: the failure direction is conservative (the forecast is withheld, never overstated).

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|--------------|----------|
| 1 | Provisional thresholds physically reasonable on real data (truth 10) | Phase 3 (VAL-01/VAL-02), owner disposition | 02-UAT.md `Deferred follow-up:` entry, 2026-10-20 |

### Advisory (New Scope, Unevidenced)

| # | Finding | Category | Why Advisory |
|---|---------|----------|--------------|
| 1 | No Phase 3 plan names per-city cleaning flag rates as a deliverable; the deferral has no carrier yet | other | Planning gap, not a Phase 2 code defect |
| 2 | Hour alignment documented and pinned but not enforced; the hh:05 dispatch is not yet in a Phase 5 requirement | other | Conservative failure direction; belongs to Phase 5 scheduling |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/data_cleaning.py` | `clean_history`, rules, constants, policy version 2 | VERIFIED | Substantive, wired from `city_pipeline`. |
| `backend/city_pipeline.py` | Cleaning call and gap guard | VERIFIED | Unchanged in 88e3229. |
| `backend/historical_archive.py` | Slot guard with computed-after-fallback rule, stable read order | VERIFIED | `_slot_archived` and `_is_fallback` present; sole writer path via `append_observation`. |
| `backend/tests/data_cleaning_test.py`, `historical_archive_test.py`, `cleaning_pipeline_test.py` | Rule, archive and tracer tests | VERIFIED | 103 tests across the five phase files pass. |
| `docs/data-science/decisions/data_cleaning.md` | Written policy v2 | VERIFIED | Names every flag and constant; new Hour alignment section. |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `city_pipeline.py` | `data_cleaning.py` | `clean_history(history, as_of=end)`; `forecast_gap_reason(...)` | WIRED |
| `historical_archive.append_observation` | archive CSV | `_slot_archived` before write | WIRED |
| `city_rating._archive_city_result` | `append_observation` | row built with `fallback` from the check result | WIRED |
| `data_cleaning_test.py` | `data_cleaning.md` | doc agreement test | WIRED |
| `data_cleaning._parse_utc` | `historical_archive._parse_utc` | parity test | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Real Data | Status |
|----------|---------------|--------|-----------|--------|
| Forecast and detector input | `history` = `cleaned.usable` | `read_history` on the CSV, then `clean_history` | Yes (probe: file with a fallback and two computed rows yields the two computed rows) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 5 phase test files | `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/{data_cleaning,cleaning_pipeline,historical_archive,city_pipeline,predictive_tracer}_test.py` | 103 passed | PASS |
| Full workspace suite, run once | `.venv/bin/python -m pytest -q -p no:cacheprovider` | 1356 passed, 0 failed | PASS |
| WR-01 write guard and read-side duplicate | scratch probe on a tmp CSV | True, True, False, False, True, False, False; computed row kept | PASS |
| WR-02 / WR-03 stuck rule | scratch probe | calm wind and night solar unflagged; consecutive 3.0 and 20.0 flagged; hour gap and daily readings unflagged | PASS |
| Ten mutations (scratch copy in /tmp) | per table above | each caught by a named test (the two that first survived were my own non-equivalent mutations, redone correctly) | PASS |

### Probe Execution

Step 7c: SKIPPED. No probe scripts are declared in the plans or summaries.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CLEAN-01 | 02-03 | Cross-row stuck and spike flagging under a written policy | SATISFIED | Rules 6 and 7, policy v2, tests and probe. Thresholds provisional, measurement deferred by owner. |
| CLEAN-02 | 02-03, 02-04 | Documented gap strategy before forecast and detector consume history | SATISFIED | Mark-never-fill, `after_gap` / `gap_slots`, gap guard, skipped-cycle tests, Hour alignment section. |
| CLEAN-03 | 02-01, 02-02 | At most one row per (`city`, `datetime_utc`); rerun never appends a duplicate or conflicting row | SATISFIED | Write guard and read-side rule, with the dated owner exception (computed may follow fallback) now present in REQUIREMENTS.md and ROADMAP SC3. |
| CLEAN-04 | 02-01, 02-03 | Cleaned rows stay distinguishable from raw rows | SATISFIED | Marker columns; cells never changed. |

All four phase IDs in REQUIREMENTS.md (CLEAN-01..04, ticked and marked Complete in the traceability table) appear in a plan's `requirements` field. No orphaned requirements.

### Anti-Patterns Found

None blocking. No TBD, FIXME or XXX in the changed source, test or doc files. No stubs. One cosmetic note: a comment line above `STUCK_MIN_RUN_ROWS` in `data_cleaning.py` was extended without rewrapping, so it exceeds the surrounding line width. Info only.

## Human Verification Required

None. The sole prior item is deferred to Phase 3 by the owner (see Deferred Items).

## Gaps Summary

No gaps. The goal holds: the history the forecast and detector consume is checked across rows and kept to one row per slot, with the owner-approved exception that a computed row may replace a fallback cycle's slot. Two carry-forward notes for Phase 3 and Phase 5 are in the Advisory section; neither blocks Phase 2.

---

_Verified: 2026-10-20_
_Verifier: Claude (gsd-verifier)_
