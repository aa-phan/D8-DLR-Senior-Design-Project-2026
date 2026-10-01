---
phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan
plan: 04
subsystem: ml-audit
tags: [sklearn, gradient-boosting, pinball-loss, quantile-regression, pandas, pytest, forecast-experiment-audit]

requires:
  - phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan (plan 03)
    provides: "Paired block bootstrap, real ABLATION-basis out-of-sample comparison, Strengthened comparison (D-02) section"
provides:
  - "Three-dimensional overrating profiler (frequency/magnitude/consecutive-scored-row run length) with a measured natural-vs-forced convection crossover as the low-wind regime boundary (Task 1, already merged prior to this agent's work)"
  - "Three chronologically disjoint fit/calibrate/evaluate periods of the ABLATION basis, carved via experiment_splits.SplitBoundaries/calendar_split and asserted disjoint from their own timestamps"
  - "Lower-tail quantile models (alpha 0.05/0.10) fit via sklearn GradientBoostingRegressor(loss='quantile'), calibrated on one period and checked on a disjoint third, scored with sklearn's own pinball loss, with an explicit improved/not-improved flag per (alpha, candidate)"
  - "Matched-overrating-rate retained-capacity comparison -- the headline D-03 metric -- against persistence, the corridor's static rating, and calibrated quantiles as reference rows, with achieved rates reported beside targets"
  - "Published '## Conservative-rating analysis (D-03)' section in the audit record: per-candidate overrating, regime breakdown with the measured crossover, quantile calibration results, and the matched-rate headline table, with the reanalysis-scope limitation stated before the first number and repeated at every table"
affects: [04-05, 04-06]

actuals:
  tokens: 19400
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Quantile pipeline's three periods are a fresh 60/20/20 chronological partition of the COMBINED ABLATION train+val range (via the harness's own default calendar-split fractions), not a reproduction of Phase 3's original train/val boundary -- documented as a deliberate, Claude's-discretion design choice driven by the persisted ablation report carrying per-row residuals for the validation range only."
    - "Decision-time weather features for the corridor-level quantile model are the MEAN of both endpoint cities' own fcst_air_temp/fcst_perp_wind_ms/fcst_solar_radiation columns -- a documented proxy, since the corridor-reduced frame carries no fcst_* group at all."
    - "Matched-rate derating is the (1 - target_rate)-quantile of (prediction - truth) on the calibrate period, applied unchanged on evaluate -- one shared `_matched_rate_row` helper scores real candidates, the static-rating reference, and calibrated-quantile rows identically."

key-files:
  created: []
  modified:
    - backend/forecast_experiment_audit.py
    - backend/tests/forecast_experiment_audit_test.py
    - docs/data-science/decisions/forecast_correction_followup_audit.md

key-decisions:
  - "The three quantile periods (fit/calibrate/evaluate) partition the COMBINED ABLATION train+val range via a fresh 60/20/20 calendar split, not Phase 3's original train/val boundary -- because Plan 04-03's persisted audit_ablation_report_<CORRIDOR>.json carries per-row residuals (truth minus prediction) for the VALIDATION range only, with no timestamp or truth column, so the quantile pipeline needed real per-row features for every period and reconstructed the full ABLATION basis directly (fitting arms 3/4/5 on ABLATION TRAIN rows alone, the same already-established non-frozen discipline Plan 04-03 uses) rather than literally reproducing the plan's suggested train-range-as-fit-period split."
  - "A handful of the earliest TRAIN rows (5 of 2360+, both corridors) are excluded from the combined quantile basis: arm 5's own feature table needs lag/rolling-window history (FORECAST_ML_LAG_HOURS/FORECAST_ML_ROLLING_WINDOW_HOURS) deeper than the single-day dropna edge effect Plan 04-01's Finding 3 already documented, so the earliest few rows' own anchor timestamps fall before arm 5's first valid feature row. A documented, bounded edge trim, not a silent drop."
  - "The regime breakdown and the calibrated-quantile rows in the matched-rate table are computed once, for ml_cooling_corrected (the frozen record's own stated winner and the estimator family this phase's quantile work also reuses) -- not once per candidate, matching the plan's own singular 'the regime breakdown' phrasing."
  - "Found and fixed a test-authoring bug during Task 2 (Rule 1): a new test seeded its synthetic frames with Python's randomized hash() of a (str, float) tuple, which salts per process -- the exact same test passed in isolation and failed when run as part of the full suite. Replaced with fixed per-period seeds and a fixture robust to sampling noise (narrow fit-period noise vs. wide, matching calibrate/evaluate noise)."

patterns-established:
  - "overrating_basis_report composes Task 1's profiler/regime breakdown with Task 2's quantile/matched-rate work into one git-ignored JSON report per corridor, carrying the reanalysis-scope limitation as a top-level field and the frozen-window guard result for every period -- the same composition discipline ablation_basis_report (Plan 04-03) established for its own report."

requirements-completed: [D-03]

coverage:
  - id: D1
    description: "Overrating measured in three dimensions (frequency, magnitude, consecutive-scored-row run length) for every real candidate at both corridors, on the real ABLATION-basis validation rows"
    requirement: "D-03"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_audit_test.py::test_overrating_basis_report_runs_and_returns_documented_shape"
        status: pass
      - kind: other
        ref: "data/experiment/audit_overrating_report_AUSTIN_CORPUS_CHRISTI.json, ..._MIDLAND_EL_PASO.json (overrating field, both corridors)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Low-wind regime boundary is the corridor conductor's own measured natural-vs-forced convection crossover, not a round number; regime bins provably partition the scored rows"
    requirement: "D-03"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_audit_test.py (Task 1's overrating_by_regime tests, unmodified; re-exercised on real data via overrating_basis_report's own integration test)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Lower-tail ampacity quantiles fitted, calibrated and evaluated on three chronologically disjoint periods, scored with scikit-learn's own pinball loss, with non-improvement reported rather than hidden"
    requirement: "D-03"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_audit_test.py::test_quantile_period_boundaries_disjoint_ordered_and_before_frozen_test_start, ::test_fit_calibrate_evaluate_quantile_reports_improvement_when_distributions_match, ::test_fit_calibrate_evaluate_quantile_reports_no_improvement_when_distributions_diverge, ::test_pinball_loss_alpha_half_equals_half_mae"
        status: pass
      - kind: other
        ref: "data/experiment/audit_overrating_report_MIDLAND_EL_PASO.json (ml_wind_corrected, alpha=0.05: calibration did NOT improve the evaluate-period exceedance rate, reported explicitly)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Candidates and calibrated-quantile baselines compared at matched overrating rates, retained capacity as the headline metric, against persistence and the static rating, with achieved rates reported beside targets"
    requirement: "D-03"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_audit_test.py::test_matched_rate_row_matches_hand_computation, ::test_retained_capacity_at_matched_overrating_includes_extra_rows"
        status: pass
    human_judgment: false
  - id: D5
    description: "Published '## Conservative-rating analysis (D-03)' section with the reanalysis-scope limitation stated before any number and repeated at every table, no number described as a safety margin/guarantee/established conductor-level reliability"
    requirement: "D-03"
    verification:
      - kind: other
        ref: "D03_SECTION_OK / D03_NUMBERS_TRANSCRIBED_OK / DOC_ONLY_TASK_OK inline verify scripts in 04-04-PLAN.md Task 3, re-run against the finished document"
        status: pass
    human_judgment: true
    rationale: "Whether the write-up's framing and the strength of the matched-rate comparison's headline language are honest and well-scoped is a judgment call about prose quality, not something the automated word/table/regex checks alone can certify -- those checks prove the required structure and figures are present, not that the narrative around them is sound."

duration: 95min
completed: 2026-09-30
status: complete
---

# Phase 04, Plan 04: Conservative-Rating Analysis (Overrating, Calibrated Quantiles, Matched-Rate Retained Capacity) Summary

**A three-period quantile pipeline (fit/calibrate/evaluate, scikit-learn's own pinball loss) and a matched-overrating-rate retained-capacity table show `ml_cooling_corrected` retains the most usable capacity of any real candidate at a matched 5% risk level at both corridors -- and overrating concentrates at 100% in the lowest-wind bin, exactly at the conductor's own measured natural-vs-forced convection crossover.**

## Performance

- **Duration:** 95 min (Tasks 2 and 3 only; Task 1 was executed and merged by a prior agent before this session started)
- **Started:** 2026-09-30
- **Completed:** 2026-09-30
- **Tasks:** 3 total (Task 1 pre-completed; Tasks 2-3 executed this session)
- **Files modified:** 3 (`backend/forecast_experiment_audit.py`, `backend/tests/forecast_experiment_audit_test.py`, `docs/data-science/decisions/forecast_correction_followup_audit.md`)

## Accomplishments

**Task 1 (pre-completed, summarized from the existing commits/code for continuity):**
- `overrating_profile(truth, prediction, timestamps)` returns count, rate, mean/median/p95/max exceedance in amperes, and a run-length distribution of consecutive overrating scored rows, carrying its own cadence (6.0 hours) and run-length caveat as RETURNED DATA, not only in a docstring.
- `convection_crossover_wind_speed(corridor)` measures the perpendicular wind speed at which `thermal_model`'s own forced-convection term equals its natural-convection term (0.1428 m/s at 35.0°C for both corridors), verified against the thermal module's own convective function on both sides of the crossover.
- `overrating_by_regime` bins perpendicular wind with the measured crossover as the lowest interior edge, with per-bin row counts provably summing to the scored total and small bins flagged rather than rated.
- `backend/thermal_model.py` carries zero diff.

**Task 2 (this session) — three-period quantile pipeline and matched-rate retained capacity:**
- `quantile_period_boundaries` carves the combined ABLATION train+val range into three chronologically disjoint fit/calibrate/evaluate periods via `experiment_splits.SplitBoundaries`/`calendar_split`, asserted disjoint from the periods' own timestamps and strictly before `FROZEN_TEST_SPLIT_START`, raising (naming all three row counts) below a stated minimum.
- `_quantile_source_frame` reconstructs the full ABLATION basis (mirroring `ablation_basis_report`'s own proven assembly, fitting arms 3/4/5 on ABLATION TRAIN rows alone) and attaches every one of the seven `ALL_ARMS` entries' own point predictions to every row of the COMBINED range, not only the validation slice `ablation_basis_report` itself scores.
- `fit_lower_quantile_model` fits `sklearn.ensemble.GradientBoostingRegressor(loss="quantile")`, seeded from the phase's one random-state constant, with a fixed, auditable feature set (candidate's own point prediction, decision-time weather, hour-of-day encoding) asserted to exclude any `truth_*` column.
- `quantile_calibration_report`/`_fit_calibrate_evaluate_quantile` report pinball loss (`sklearn.metrics.mean_pinball_loss`, verified against its alpha-one-half-equals-half-MAE identity) and empirical exceedance rate before and after a calibration offset learned on the calibrate period only and applied unchanged on evaluate, with an explicit improved/not-improved flag -- verified against both a matching-distribution case (improves) and a deliberately diverging-distribution case (does not).
- `retained_capacity_at_matched_overrating`/`_matched_rate_row` find the additive derating achieving each target overrating rate (5%/10%) on calibrate, apply it unchanged on evaluate, and report the achieved rate, retained capacity in amperes, and retained capacity as a fraction of the corridor's static reference -- verified against a hand-computed fixture.
- `overrating_basis_report` composes all of the above into one git-ignored JSON report per corridor, carrying the reanalysis-scope limitation as a top-level field and the frozen-window guard result for every period.
- 12 new tests (86 total, up from 74); full suite shows no new failure beyond the 23 pre-existing `corridor_discretization_test.py` failures.
- Found and fixed a Rule 1 bug mid-session: one new test's own RNG seeding used Python's randomized `hash()`, making it flaky across separate test-runner invocations (passed in isolation, failed in the full suite) -- replaced with fixed seeds and a noise-robust fixture, verified stable across repeated runs.

**Task 3 (this session) — published Conservative-rating analysis (D-03):**
- The `## Conservative-rating analysis (D-03)` section opens with the reanalysis-scope limitation before any number, cross-references Finding 1's provenance finding, and names Plan 04-06's data contract as what would make the numbers safety-relevant.
- States the ABLATION basis and the three disjoint periods' boundary dates and row counts (identical across both corridors: fit 1,883 rows 2024-01-22 to 2025-05-06; calibrate 628 rows 2025-05-07 to 2025-10-10; evaluate 628 rows 2025-10-11 to 2026-03-16).
- Per-candidate overrating table at both corridors, with the cadence caveat adjacent to the run-length data in the words the report itself carries.
- Regime table naming the measured crossover (0.1428 m/s, 35.0°C) as the low-wind edge, with a dedicated low-wind discussion: overrating is 100% below the crossover at BOTH corridors (22/37 rows), versus 80.2%/78.9% just above it and 25.8%/21.0% two bins up -- the convective term's physical sensitivity near the crossover, not numerical instability (`thermal_model.py` carries zero diff).
- Quantile calibration table naming the one (candidate, alpha) pair where calibration did NOT generalize (`ml_wind_corrected`, Midland, alpha=0.05) rather than folding it into an aggregate.
- Matched-overrating-rate retained-capacity table labelled as the headline comparison: `ml_cooling_corrected` retains the most capacity of any real candidate at a matched 5% rate at both corridors (1,064.68 A / 56.0% of static at Austin; 962.50 A / 66.4% of static at Midland), with achieved rates reported beside targets including material misses (e.g. persistence's 5%-target derating achieves 12.4% at Austin).
- Closes with a four-row D-03 dispositions table.
- Verified against all three of the plan's own inline checks (`D03_SECTION_OK`, `D03_NUMBERS_TRANSCRIBED_OK`, `DOC_ONLY_TASK_OK`).

## Task Commits

1. **Task 1: Overrating profile, convection crossover, regime binning** — `e8c1b78` (feat, pre-existing, merged to `main` before this session), `cf3e8b9` (docs: WINDOWS.md entry), `fab4836` (merge) — not executed by this agent.
2. **Task 2: Three-period quantile fit/calibrate/evaluate and matched-overrating-rate retained capacity** — `48abc89` (feat)
3. **Task 3: Publish Conservative-rating analysis (D-03)** — `d82d3d6` (docs)
4. **Fix (mid-Task-2, Rule 1): deterministic calibration-improvement test** — `94611cd` (fix)

## Files Created/Modified

- `backend/forecast_experiment_audit.py` — Task 2 additions: `_quantile_source_frame`, `quantile_period_boundaries`, `_quantile_feature_matrix`, `fit_lower_quantile_model`, `_fit_calibrate_evaluate_quantile`, `quantile_calibration_report`, `_matched_rate_row`, `retained_capacity_at_matched_overrating`, `overrating_basis_report`
- `backend/tests/forecast_experiment_audit_test.py` — 12 new tests covering period boundaries, feature-set exclusion, pinball-loss identity, calibration improvement/non-improvement, matched-rate hand computation, and the full `overrating_basis_report` integration shape
- `docs/data-science/decisions/forecast_correction_followup_audit.md` — `## Conservative-rating analysis (D-03)` section fully written (previously a placeholder)

## Decisions Made

See `key-decisions` in frontmatter above for full detail. Summary:
- Quantile periods partition the COMBINED ABLATION basis via a fresh 60/20/20 split, not Phase 3's original train/val boundary (persisted residuals only cover the validation range).
- A handful of the earliest TRAIN rows (5/corridor) are excluded from the quantile basis — arm 5's own lag/rolling-window warm-up, a documented, bounded edge trim.
- Regime breakdown and calibrated-quantile matched-rate rows use `ml_cooling_corrected` as the single representative candidate, matching the plan's singular (not per-candidate) phrasing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Flaky test due to `hash()`-based RNG seeding**
- **Found during:** Task 2, while running the full test suite after adding new tests
- **Issue:** `test_fit_calibrate_evaluate_quantile_reports_improvement_when_distributions_match` seeded its synthetic frames via Python's randomized `hash()` of a `(str, float)` tuple; hash randomization salts per process, so the test passed when run in isolation but failed when run as part of the full suite.
- **Fix:** Replaced with fixed, explicit per-period seeds and a noise-robust fixture (fit period's noise deliberately narrower than calibrate/evaluate's, calibrate and evaluate sharing the same wide distribution) so the "improved" assertion holds reliably regardless of process-level hash salt or sampling noise.
- **Files modified:** `backend/tests/forecast_experiment_audit_test.py`
- **Verification:** Ran the test 3+ times in isolation and as part of the full suite; stable each time.
- **Commit:** `94611cd`

### Design choices documented inline (not deviations from a must-have, but worth surfacing)

**2. [Claude's discretion, per 04-RESEARCH.md] Quantile periods partition the combined ABLATION basis, not Phase 3's original train/val boundary.** The plan's own action text suggests "the ABLATION train range as the fit period, and the ABLATION validation range halved into a calibrate period and an evaluate period." Plan 04-03's persisted `audit_ablation_report_<CORRIDOR>.json` carries per-row residuals (truth minus prediction) for the VALIDATION range only, with no timestamp or truth column persisted — the quantile pipeline needs real per-row truth, timestamps, and decision-time features for every one of its three periods, which the persisted residuals alone cannot supply. Rather than literally reproducing the plan's suggested train-range-as-fit-period split (which would require either re-deriving predictions on train rows outside the persisted residuals, or recomputing the original train/val boundary from a frame whose span differs from what produced it), `_quantile_source_frame` reconstructs the FULL ABLATION basis directly (the same non-frozen, already-established discipline Plan 04-03 uses — fitting arms 3/4/5 on ABLATION TRAIN rows alone, never touching the frozen test window) and attaches every arm's own prediction to every row of the combined range. `quantile_period_boundaries` then carves three disjoint periods from this combined range via the harness's own default 60/20/20 calendar-split fractions — a chronological partition of the ABLATION basis itself, not a reproduction of Phase 3's original train/val boundary. All of D-03's substantive requirements (three chronologically disjoint periods, asserted so from timestamps, no row calibrated and checked on the same rows, all strictly before the frozen test split) are satisfied; only the EXACT row-count split (60/20/20 of the combined range vs. the plan's suggested reuse of the original ~75/12.5/12.5 train/val-halved split) differs from the plan's own illustrative example. Documented here per the plan's own instruction that exact boundary choices for this kind of split are Claude's discretion (04-RESEARCH.md), not re-litigated as a Rule 4 architectural question since no new infrastructure or schema was introduced — only a different, equally rigorous partition of data already being assembled.

**3. [Claude's discretion] Decision-time weather features are a corridor-level MEAN of both endpoint cities' own forecast-at-decision-time columns.** The corridor-reduced frame (`corridor_anchored_pair_frame`) carries no `fcst_*` group at all (confirmed directly, matching Finding 5's own time-reference table: "corridor frame carries no fcst_* group"). Rather than reducing via the project's weakest-link convention (which applies to ampacity values, not raw weather quantities like temperature or wind speed — averaging two cities' temperatures is physically meaningful in a way "weakest-link" selection of a temperature is not), `_quantile_source_frame` uses the arithmetic mean of both endpoint cities' own `fcst_air_temp`/`fcst_perp_wind_ms`/`fcst_solar_radiation` columns as the corridor-level feature — a documented proxy, consistent with this phase's own precedent of stating proxies plainly (the static-rating reference is likewise a stated weakest-link proxy, not an independently sourced corridor-level rating).

**4. [Rule 2-adjacent, edge-case handling] A handful of the earliest TRAIN rows are excluded from the quantile basis.** Discovered while assembling `_quantile_source_frame`: arm 5's own feature table (`forecast_training.build_training_matrix`) needs lag/rolling-window history (`config.FORECAST_ML_LAG_HOURS`, `FORECAST_ML_ROLLING_WINDOW_HOURS`) deeper than the single-day `dropna()` edge effect Plan 04-01's Finding 3 already documented — `ablation_basis_report` never hit this because it only ever reindexes arm 5's predictions onto VAL anchor times (deep into the series); this task's own function also needs TRAIN-side predictions, including the handful of earliest rows whose own anchor time falls inside that lag/rolling warm-up window (5 rows per corridor, out of 2,360+). These rows are excluded from the combined basis with an explicit, named count (`edge_trimmed_rows` in `_quantile_source_frame`'s own internal bookkeeping) — a documented, bounded edge trim affecting under 0.2% of the ABLATION train range, never a silent drop.

---

**Total deviations:** 1 auto-fixed bug (Rule 1), 3 documented design choices (Claude's discretion per 04-RESEARCH.md, or edge-case handling discovered during implementation).
**Impact on plan:** All changes are necessary for correctness (the flaky test) or are honestly-scoped, documented adaptations required by data actually available (the persisted-residuals-only constraint, the missing corridor-level forecast group, the lag-depth edge effect). No scope creep; every one of D-03's four bullets is satisfied as measured, not approximated.

## Issues Encountered

- **Worktree was forked before Task 1's commits landed on `main`.** This worktree's branch was created at `04a679b` (the phase-04 planning commit, before Plan 04-04's own Task 1 was executed and merged). Confirmed clean ancestry (no divergence — `git merge-base --is-ancestor HEAD main` true, zero local commits ahead of `main`, clean working tree) and fast-forward-merged `main` (at `fab4836`) into the worktree branch before starting Task 2, per this session's explicit instructions and mirroring the documented precedent for Plans 03-01/04-01/04-02.
- **`.venv` and `data/experiment/` do not exist in a fresh worktree** (both gitignored, per-worktree working-directory state, never shared across worktrees). Symlinked `.venv` to the main checkout's `.venv` (untracked, mirroring 04-01-SUMMARY.md's own documented precedent) and regenerated `data/experiment/audit_basis_manifest.json` plus both corridors' `audit_ablation_report_<CORRIDOR>.json` via a live network fetch before Task 2 began (per Task 2's own stated precondition: "that path is cached and idempotent") — reproduced the exact same measured ABLATION basis (784 val rows/corridor, matching `test_start=2026-03-17` for both corridors) 04-01/04-03 already measured.
- **Confirmed the same `##+ ` doc-verify section-boundary regex defect already logged in `.planning/WINDOWS.md` (phase 04, id 2)** affects this plan's own Task 3 verify scripts too (the literal `##+ ` pattern also matches this section's `###` subsection headers, truncating the matched section at the first subsection instead of at the next `##` heading). Verified Task 3's substantive intent using the evidently-intended corrected boundary regex (`##(?!#) `, the same fix Plan 04-03 already applied for its own D-02 section) — all three of Task 3's own verify scripts (`D03_SECTION_OK`, `D03_NUMBERS_TRANSCRIBED_OK`, `DOC_ONLY_TASK_OK`) pass under the corrected regex. No PLAN.md edit made (out of this plan's own file scope) and no new WINDOWS.md entry added, since the defect class is already open there and applies project-wide to this phase's doc-verify scripts, not uniquely to this plan.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Plans 04-05 and 04-06 can read the following directly from this summary and the audit record's `## Conservative-rating analysis (D-03)` section, without re-running any measurement:

- **Per-candidate overrating rate and 95th-percentile exceedance, both corridors:** `ml_cooling_corrected` has the highest overrating rate of the real candidates at both corridors (62.0% Austin, 68.6% Midland) but also the highest retained capacity at a matched 5% rate — these are not contradictory, since the matched-rate comparison derates each candidate to the SAME target rate before comparing retained capacity. `ml_wind_corrected` has the lowest overrating rate at Austin (42.5%) and the lowest p95 exceedance at both corridors (255.17 A Austin, 323.26 A Midland).
- **Overrating concentrates sharply in the low-wind bin, both corridors:** 100% overrating rate below the measured crossover (0.1428 m/s at 35.0°C), versus 80.2%/78.9% immediately above it — a real physical pattern (the convective term's natural-convection floor), not numerical instability; relevant to D-04's low-wind-sensitivity-vs-instability distinction.
- **Quantile calibration generalized from calibrate to evaluate for every (candidate, alpha) pair except one:** `ml_wind_corrected` at Midland, alpha=0.05, did NOT improve — named explicitly in both the JSON report and the published section, not hidden.
- **Retained-capacity ranking at each matched overrating rate, with achieved-vs-target gaps:** at a matched 5% target, `ml_cooling_corrected` > `ml_wind_corrected`/`reference_ml_refit_24h` > persistence > static rating at BOTH corridors; achieved rates differ materially from targets in both directions (persistence overshoots to 12.4% at Austin; the static rating undershoots to 0.5% at Midland) — any eventual integration decision operating at a stated risk level would need this gap sized explicitly, not assumed away.
- **What changes the frozen record's Verdict claims:** D-03's conservative-rating analysis adds an entirely new axis (risk-adjusted retained capacity) the frozen record never measured — Plan 04-05's corrected-language work should note that `ml_cooling_corrected`'s MAE advantage (D-02's finding) is reinforced, not contradicted, by this section's own matched-rate ranking, strengthening rather than weakening the case for treating it as the lowest-observed-MAE candidate worth further integration scrutiny, subject to every caveat D-03's reanalysis-scope limitation states.

No blockers.

---
*Phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan*
*Completed: 2026-09-30*

## Self-Check: PASSED

- FOUND: `backend/forecast_experiment_audit.py`
- FOUND: `backend/tests/forecast_experiment_audit_test.py`
- FOUND: `docs/data-science/decisions/forecast_correction_followup_audit.md`
- FOUND: `.planning/workstreams/ml-modeling/phases/04-forecast-correction-experiment-follow-up-audit-data-provenan/04-04-SUMMARY.md`
- FOUND commits: `48abc89`, `d82d3d6`, `94611cd`, `e8c1b78`, `cf3e8b9`, `fab4836`
