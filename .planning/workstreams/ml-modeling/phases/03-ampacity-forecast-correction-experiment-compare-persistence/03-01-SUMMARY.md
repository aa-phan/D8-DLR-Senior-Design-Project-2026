---
phase: 03-ampacity-forecast-correction-experiment-compare-persistence
plan: 01
subsystem: ml-modeling
tags: [open-meteo, forecast-archive, calibration-gate, ecmwf_ifs, requests, experiment-splits]

# Dependency graph
requires: []
provides:
  - "backend/open_meteo_forecast_provider.py: bulk Historical Forecast + Single-Runs fetch adapters, pinned to models=ecmwf_ifs (unchanged this session; landed in the halted prior session)"
  - "backend/forecast_leadtime_calibration.py: the D-01 hard gate, now measurement-corrected (tolerance-based match) and verified to PASS live on the empirically-corrected window"
  - "backend/config.py: FORECAST_EXPERIMENT_WINDOW_START corrected twice this session (2024-11-13, then 2025-10-01) to the actual empirically-verified bulk/single-run alignment boundary across ALL four six-hourly runs"
  - "backend/experiment_splits.py: calendar_split, a three-way calendar train/val/test splitter, provably agreeing with anomaly_training.chronological_split"
  - "backend/forecast_experiment.py: the anchored-pair-frame contract, assert_exact_lead/filter_to_exact_lead, score_arms, and a live-verified tracer scoring persistence (arm 0) vs raw-forecast-through-IEEE-738 (arm 2) for AUSTIN"
  - "A second, independent, load-bearing finding (NOT anticipated by any prior document in this phase): Open-Meteo's bulk historical-forecast-api response is empirically bit-identical to archive-api's reanalysis 'truth' at this lead, across all four project cities and the full corrected window -- confirmed via raw wrapper-free HTTP requests, not just this repo's code"
affects: [03-02, 03-03, 03-04, 03-05, 03-06, 03-07]

# Actuals (#2632)
actuals:
  tokens: 15528
  tasks: 1
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A numeric tolerance (not exact float equality) when comparing values sourced from two independently-serialized, decimal-rounded JSON API responses -- exact equality mistook two-decimal rounding noise for a mismatch"
    - "A design-premise checkpoint that fails on live re-verification is investigated further (not silently narrowed to the first plausible date) when the failure mode itself is diagnostic -- the second, later boundary was invisible to the original 00Z-only investigation and only surfaced by running the actual multi-run gate"
    - "Anchored-pair-frame contract: anchor_/truth_/fcst_ column groups, anchor built from the FULL unfiltered hourly series before any scoring filter is applied -- the filter selects which rows are scored, never the source of a lagged value"

key-files:
  created:
    - backend/experiment_splits.py
    - backend/forecast_experiment.py
    - backend/tests/experiment_splits_test.py
    - backend/tests/forecast_experiment_test.py
  modified:
    - backend/config.py
    - backend/forecast_leadtime_calibration.py
    - backend/tests/forecast_leadtime_calibration_test.py
    - .planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/03-01-BOUNDARY-INVESTIGATION.md
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "User's design-premise decision (resolving the prior session's halt): narrow FORECAST_EXPERIMENT_WINDOW_START to the empirically-verified bulk/single-run alignment boundary and run through 'today' rather than the original 2025-12-31 cap -- this session's job was to apply that decision and re-verify, per the explicit instruction to confirm the gate agrees rather than trust the investigation doc's dates alone."
  - "Live re-verification found the investigation doc's 2024-11-13 boundary INCOMPLETE: it was derived by comparing bulk against the 00Z single run only, but forecast_leadtime_calibration.measure_lead_alignment samples all four six-hourly runs (00Z/06Z/12Z/18Z), and all four supply one of the four daily hour%6==1 scored rows. A live run at 2024-11-13 still failed. A follow-up daily-resolution sweep (AUSTIN, EL_PASO) found the 06Z/18Z runs carry their own separate, later, equally sharp cutover at 2025-09-30 -> 2025-10-01 (00Z/12Z were already reliable throughout the gap). FORECAST_EXPERIMENT_WINDOW_START was corrected a second time to 2025-10-01 -- the later of the two boundaries, since all four must hold simultaneously. This is treated as a Rule 1 correction (completing an already-approved verification methodology with more complete data), not a new architectural decision -- the row volume remains non-degenerate (~1,440 scored rows/city vs. the investigation's own ~2,740 estimate) and the underlying methodology (narrow the window to where the verified-deterministic-lead rule provably holds) is unchanged."
  - "Fixed a genuine measurement bug in forecast_leadtime_calibration.measure_lead_alignment, surfaced by the live re-verification: it compared wind_speed floats with exact equality across two independently-serialized, decimal-rounded JSON responses, so ordinary two-decimal rounding noise (empirically 0.01-0.06 m/s in a targeted 38-mismatch sample) was miscounted as a rule violation. Added a small, evidence-bounded tolerance (_MATCH_TOLERANCE_MS = 0.1 m/s -- above the observed rounding ceiling, below the smallest genuine mismatch of ~0.2 m/s observed in the same sample). This does NOT touch assert_supports_horizon's threshold or its p05-lead logic; it corrects how two floats are determined to represent the same value."
  - "CRITICAL, newly-discovered finding (not addressed by any decision made before this session, and outside CONTEXT.md's three scoped contingencies): Open-Meteo's bulk historical-forecast-api response, in bulk/date-range mode with models=ecmwf_ifs, is empirically BIT-IDENTICAL to archive-api's reanalysis output for every hour tested -- confirmed for AUSTIN, EL_PASO, and MIDLAND, across 9+ dates spanning the full corrected window (2025-10-01 through 2026-09-27), and independently reproduced via raw, wrapper-free `requests.get` calls bypassing this repo's code entirely (ruling out a code-level bug). Task 3's arm 2 (raw_forecast) consequently scored an exact 0.0 MAE against truth for AUSTIN's 145 test rows -- not because 1-hour-lead physics-plus-forecast is a genuinely skillful predictor, but because the 'forecast' data at this lead already equals the eventual observation in this data source. Documented prominently in `EXPERIMENT_LEAD_REALIZABILITY_CAVEAT` (extended this session) and flagged here for explicit review before Plans 03-02+ build further arms on this data source -- see 'Critical Finding' section below."
  - "Kept Task 3's implementation scope exactly as specified in 03-01-PLAN.md (experiment_splits.py, the anchored-pair-frame contract, arms 0/2 for one city) despite the data-source finding above -- the code correctly implements the specified contract and the 0.0 MAE is the honest, correctly-measured result of that data, not a code defect. Refusing to report it, or silently 'fixing' it by picking a different data source unilaterally, would have been the wrong call for an executor; surfacing it with full evidence for the next planning session is the right one."

patterns-established:
  - "A calibration/verification gate that still fails after applying an approved correction is investigated further, not treated as a blocker requiring a fresh checkpoint, IF the further investigation stays within the same approved methodology and does not change its fundamental approach -- distinguishing this from a genuine Rule-4 architectural question."
  - "When a live result looks 'too good' (an exact 0.0 MAE), verify the underlying inputs directly (raw HTTP requests bypassing all wrapper code) before either trusting or dismissing the number."

requirements-completed: [D-01, D-02]

coverage:
  - id: D1
    description: "The D-01 lead-time calibration gate, corrected to the empirically-verified two-boundary alignment window, PASSES live on the hour%6==1 filtered subset for all four cities (min=p05=max=1.0h) and FAILS correctly on the unfiltered series (p05=0h)"
    requirement: D-01
    verification:
      - kind: integration
        ref: "live run: .venv/bin/python3 backend/forecast_leadtime_calibration.py --days 30 (transcript in this SUMMARY)"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_leadtime_calibration_test.py (10 tests, including 2 new tolerance-behavior tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "experiment_splits.calendar_split: three-way calendar train/val/test split, provably agreeing with anomaly_training.chronological_split at equivalent boundaries"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/experiment_splits_test.py (9 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The anchored-pair-frame contract: every scored row's anchor is exactly one hour before its truth time, built from the FULL unfiltered series before filtering, live-verified for AUSTIN"
    requirement: D-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py::test_anchored_pair_frame_anchor_gap_is_exactly_one_hour, test_anchored_pair_frame_median_anchor_spacing_is_one_hour_before_filtering"
        status: pass
      - kind: integration
        ref: "live run: forecast_experiment.py --city AUSTIN --start 2025-10-01 --end 2026-03-31 -- all 145 scored rows carry a byte-identical 1h anchor gap"
        status: pass
    human_judgment: false
  - id: D4
    description: "Persistence (arm 0) and raw-forecast-through-IEEE-738 (arm 2) scored on a byte-identical test-timestamp index; arm 0's MAE agrees with ampacity_forecast.backtest_residuals over the same timestamps"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py::test_persistence_arm_agrees_with_backtest_residuals, test_score_arms_returns_identical_index_for_every_arm"
        status: pass
      - kind: integration
        ref: "live run: both arms report rows=145 (identical index), report JSON at data/experiment/experiment_report_AUSTIN.json"
        status: pass
    human_judgment: false
  - id: D5
    description: "CRITICAL FINDING: whether Open-Meteo's bulk historical-forecast-api genuinely differs from archive-api at a 1-hour lead (i.e. whether arm 2's near-zero MAE reflects real forecast skill or a data-source property) requires human/design review before Plans 03-02+ proceed"
    verification: []
    human_judgment: true
    rationale: "This is not a pass/fail test outcome -- it is a finding about the phase's chosen data source (D-01) that no prior document anticipated, confirmed independently via raw HTTP requests. A human must decide how Plans 03-02 onward should interpret or address this before more arms are built on the same data source."

duration: ~50min (approximate -- this was a continuation session resuming a prior halt; no explicit start timestamp was captured at spawn)
completed: 2026-09-29
status: complete
---

# Phase 3 Plan 01: Forecast-Archive Provider, Calibration Gate, and First Scored Slice Summary

**Corrected the experiment window to the true (two-boundary) empirically-verified alignment range, live-verified the calibration gate now passes, completed Task 3's anchored-pair-frame/arm-scoring tracer for Austin, and surfaced a second, more consequential data-source finding: Open-Meteo's bulk forecast archive is bit-identical to its reanalysis "truth" archive at this lead.**

## Performance

- **Duration:** ~50 min (approximate)
- **Completed:** 2026-09-29T20:20:00Z
- **Tasks:** Checkpoint resolved + Task 3 completed (1 of this plan's remaining tasks; Tasks 1-2 were already committed in the prior, halted session)
- **Files modified:** 4 created, 5 modified

## Accomplishments

- **Resolved the design-premise checkpoint** from the halted prior session: applied the user's decision to narrow `FORECAST_EXPERIMENT_WINDOW_START`, then discovered during live re-verification that the decision's basis (00Z-only investigation) was incomplete for the actual four-run calibration gate, and completed the characterization -- the true window start is **2025-10-01**, not 2024-11-13.
- **Fixed a genuine floating-point measurement bug** in the calibration gate (`measure_lead_alignment`'s exact-equality comparison mistook decimal-rounding noise for rule violations) with an evidence-bounded numeric tolerance.
- **Live-verified the calibration gate now PASSES** on the corrected window for all four project cities: unfiltered gate fails correctly (p05=0h), filtered gate (`hour % 6 == 1`) passes cleanly (min=p05=max=1.0h), zero boundary skips.
- **Completed Task 3**: `experiment_splits.calendar_split` (three-way calendar split, provably agreeing with the repo's existing `chronological_split`) and `forecast_experiment.py` (the anchored-pair-frame contract, `assert_exact_lead`, `filter_to_exact_lead`, `score_arms`), live-verified for AUSTIN scoring arms 0 (persistence) and 2 (raw forecast).
- **Discovered and documented a second, independent, more consequential finding**: Open-Meteo's bulk forecast-archive product is bit-identical to its reanalysis archive at this lead, across every city and date tested -- see "Critical Finding" below.

## Task Commits

1. **Checkpoint resolution: window correction + calibration gate measurement fix** - `eae00a2` (fix)
2. **Task 3: anchored pair frame, calendar split, first arm-scoring tracer** - `d6a7e5f` (feat)

**Documentation updates** (this SUMMARY, the investigation doc addendum, ACKNOWLEDGEMENTS.md) committed separately below.

_Note: this plan is `type: execute`, not `type: tdd`; commits above are feat/fix._

## Files Created/Modified

- `backend/config.py` - `FORECAST_EXPERIMENT_WINDOW_START` corrected twice (2024-11-13, then 2025-10-01) with full two-boundary history documented inline; `FORECAST_EXPERIMENT_WINDOW_END` changed to a `None` sentinel resolved to "yesterday UTC" at call time (never a stale hardcoded date); `FORECAST_EXPERIMENT_VERIFIED_WINDOW_START`'s comment corrected to clarify it marks Single-Runs archive reachability, not the alignment-rule boundary.
- `backend/forecast_leadtime_calibration.py` - `_stratified_sample_days` now bounds its sampling by `FORECAST_EXPERIMENT_WINDOW_START` (not the archive-reachability constant); `measure_lead_alignment` now compares within `_MATCH_TOLERANCE_MS` (0.1 m/s) rather than exact equality.
- `backend/tests/forecast_leadtime_calibration_test.py` - 2 new tests proving the tolerance absorbs rounding noise but still rejects genuinely different values.
- `backend/experiment_splits.py` (new) - `SplitBoundaries`, `calendar_split` (three-way calendar train/val/test split).
- `backend/forecast_experiment.py` (new) - `EXPERIMENT_LEAD_REALIZABILITY_CAVEAT` (extended this session with the data-source finding), `anchored_pair_frame`, `assert_exact_lead`, `filter_to_exact_lead`, `_city_ampacity`, `score_arms`, `corridor_experiment_report`, `main`.
- `backend/tests/experiment_splits_test.py` (new) - 9 tests, including the agreement test against `anomaly_training.chronological_split`.
- `backend/tests/forecast_experiment_test.py` (new) - 15 tests, including the persistence-vs-`backtest_residuals` agreement regression and the caveat-presence checks.
- `.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/03-01-BOUNDARY-INVESTIGATION.md` - addendum documenting that the original 2024-11-13 finding was incomplete (00Z-only), the corrected 2025-10-01 boundary, and the new bulk-vs-archive finding.
- `ACKNOWLEDGEMENTS.md` - updated per standing ECE 464 AI-use disclosure convention.

## Decisions Made

See `key-decisions` in frontmatter for full detail. Summary:
1. Applied the user's already-made decision to narrow the window per `03-01-BOUNDARY-INVESTIGATION.md`.
2. Discovered live that the applied decision's date (2024-11-13) did not actually make the real calibration gate pass, because the investigation only tested one of the four runs the gate samples. Completed the characterization (same methodology, more complete data) rather than treating this as requiring a fresh architectural checkpoint, since the row volume remained non-degenerate and the approach was unchanged.
3. Fixed a measurement-fidelity bug in the gate's comparison logic (tolerance vs. exact equality) with extensive empirical justification, without touching the gate's actual pass/fail thresholds.
4. Completed Task 3 exactly as specified, and reported its most striking result (0.0 MAE) honestly rather than treating it as suspicious-and-therefore-wrong.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Calibration gate still failed after the first window correction -- investigation was incomplete**
- **Found during:** Live re-verification of the calibration gate on the 2024-11-13 window (the user's decision, applied as instructed).
- **Issue:** `03-01-BOUNDARY-INVESTIGATION.md` characterized the bulk/single-run alignment boundary using only the 00Z single run. `forecast_leadtime_calibration.measure_lead_alignment` (the actual gate) samples all four six-hourly runs. A live run at 2024-11-13 still failed with 50-75% match rates for leads 0-5 across all four cities.
- **Fix:** Diagnosed via direct per-run comparison (raw diagnostic scripts, not committed) that 06Z/18Z runs carry their own separate, later cutover at 2025-09-30 -> 2025-10-01, while 00Z/12Z were already reliable from 2024-11-13. Corrected `FORECAST_EXPERIMENT_WINDOW_START` to 2025-10-01, the later of the two boundaries.
- **Files modified:** `backend/config.py`
- **Verification:** Live gate run now passes cleanly for all four cities (transcript below).
- **Committed in:** `eae00a2`

**2. [Rule 1 - Bug] `measure_lead_alignment` used exact float equality across independently-rounded API responses**
- **Found during:** Same live re-verification, second pass after the window correction above -- leads 0-5 showed 85-99% match rates (not the ~100% expected), tripping the `_MATCH_RATE_FLOOR` guard.
- **Issue:** A targeted inspection of 38 sampled mismatches found the overwhelming majority were 0.01-0.06 m/s apart (two-decimal rounding noise from independent JSON serialization), with a small number of genuinely different values (0.2-0.79 m/s, isolated to one anomalous run/date). Exact equality (`==`) miscounted the rounding noise as rule violations.
- **Fix:** Added `_MATCH_TOLERANCE_MS = 0.1` (m/s), chosen with a ~2x margin on both sides of the observed rounding-noise ceiling and the smallest genuine mismatch. Does not touch `assert_supports_horizon`'s threshold or logic.
- **Files modified:** `backend/forecast_leadtime_calibration.py`, `backend/tests/forecast_leadtime_calibration_test.py`
- **Verification:** Live gate run now shows 99-100% match rates for leads 0-5 (MAD 0.003-0.025) and correctly-low match rates for leads 6+ (MAD 0.37-0.83, well beyond the tolerance) -- the fix did not mask the genuine stitching-depth cutoff. Two new unit tests confirm both directions.
- **Committed in:** `eae00a2`

---

**Total deviations:** 2 auto-fixed (both Rule 1 bug fixes, both directly necessary to honestly complete this plan's own re-verification instruction). **Impact:** Both were required to get an honest, correct answer to "does the gate actually pass" rather than accepting the user's already-approved decision at face value; neither weakens the gate's actual claims, and both are extensively evidenced in code comments and this summary.

## Critical Finding (beyond the resolved checkpoint -- requires review before Plans 03-02+)

While completing Task 3's live verification (required by its own acceptance criteria), `raw_forecast` (arm 2) scored an **exact 0.0 MAE and 0.0 RMSE** against truth for AUSTIN's 145 test rows. Investigating why (rather than assuming a bug in my own new code) found:

1. **Direct comparison** of `open_meteo_provider.fetch_open_meteo` (archive-api, "truth") against `open_meteo_forecast_provider.fetch_historical_forecast` (historical-forecast-api, models=ecmwf_ifs, "forecast") for AUSTIN, 2025-10-01: **every one of the 24 hourly values across all 5 weather variables was bit-identical.**
2. Repeated across 9 dates spanning the full corrected window (2025-10-01 through 2026-09-27): **identical in every case.**
3. Repeated for EL_PASO and MIDLAND on different dates: **identical in both cases.**
4. **Reproduced independently via raw, wrapper-free `requests.get` calls** directly against both endpoints (bypassing every line of this repo's code) -- ruling out a code-level bug in either provider module. The two endpoints' `generationtime_ms` values differed (confirming two genuinely separate server-side queries), but the returned hourly data payloads were identical.
5. By contrast, `fetch_single_run` (the Single-Runs API, queried with an exact `run=` timestamp) DOES show small-but-real differences from truth when restricted to leads 0-5 (e.g. air_temp 0.1°C, wind_speed 0.01-0.05 m/s, wind_direction several degrees) -- non-zero, unlike the bulk product's exact-zero difference.

**Implication:** Open-Meteo's `historical-forecast-api` in bulk/date-range mode, for this model and these variables, is not distinguishable from `archive-api`'s reanalysis output -- it appears to have been reconciled with (or is otherwise identical to) the eventual observed truth. This means `raw_forecast`'s near-zero MAE in this and future reports does **not** demonstrate that a 1-hour-lead NWP forecast is a genuinely skillful predictor of the future; it demonstrates that, in this specific data source, the "forecast" at this lead already **is** the eventual observation. Documented in `EXPERIMENT_LEAD_REALIZABILITY_CAVEAT` (extended this session) so this cannot appear on any output surface without the qualifier attached.

**This was not anticipated by CONTEXT.md's three scoped contingencies** (all three concerned lead-TIME uncertainty, not forecast-CONTENT fidelity) **nor by 03-RESEARCH.md's Pitfall 6** (which addresses dissemination latency, a related but distinct idealization). It is a new finding this session, unrelated to the design-premise checkpoint this plan was dispatched to resolve.

**What this means for Plans 03-02 through 03-07:** any later plan that scores additional arms (ML-corrected wind, ML-corrected cooling, the reference "ml" model, the oracle) against this same bulk forecast data source should account for the fact that the "forecast" input is, at this lead, empirically equivalent to ground truth -- meaning correction models trained against it are learning to correct a signal that has no injected forecast error to correct, and any apparent "arm beats persistence" result at this lead may reflect the same property, not genuine forecast-correction skill. **This needs explicit review and a decision (likely during 03-02's own discuss/plan phase) before further arms are built on this data source** -- this executor's scope ends at Plan 03-01 and does not extend to redesigning the phase's data-source strategy.

## Live Verification Transcripts

### Calibration gate (`forecast_leadtime_calibration.py --days 30`), corrected window, final run

```
AUSTIN: sampling 30 days...
  lead_h   matched  compared  match_rate       mad
       0       119       120      99.17%    0.0041
       1       119       120      99.17%    0.0072
       2       119       120      99.17%    0.0047
       3       119       120      99.17%    0.0061
       4       119       120      99.17%    0.0052
       5       119       120      99.17%    0.0066
       6        20        90      22.22%    0.4827
       ... (leads 7-23 similarly low)
boundary_skips: 0
unfiltered gate: FAIL
  forecast_leadtime_calibration: measured fifth-percentile lead is 0.00 h (0.0 min), which does not
  support the claimed 60.0-minute horizon, over hour_filter=None. The bulk product's lead
  distribution genuinely spans multiple hours over the unfiltered series -- the caller most likely
  needs to pass the exact-lead hour filter (hour % 6 == 1) rather than widen this gate.
filtered gate (hour % 6 == 1): PASS
  min=1.00h p05=1.00h max=1.00h rows=120

CORPUS_CHRISTI: sampling 30 days...  [same shape: leads 0-5 ~99%, leads 6+ low, boundary_skips=0]
unfiltered gate: FAIL / filtered gate: PASS  min=1.00h p05=1.00h max=1.00h rows=120

EL_PASO: sampling 30 days...  [same shape]
unfiltered gate: FAIL / filtered gate: PASS  min=1.00h p05=1.00h max=1.00h rows=120

MIDLAND: sampling 30 days...  [same shape, lead 0 = 100.00% match]
unfiltered gate: FAIL / filtered gate: PASS  min=1.00h p05=1.00h max=1.00h rows=120

SUMMARY: AUSTIN sampled_days=30 boundary_skips=0 unfiltered=FAIL filtered=PASS
SUMMARY: CORPUS_CHRISTI sampled_days=30 boundary_skips=0 unfiltered=FAIL filtered=PASS
SUMMARY: EL_PASO sampled_days=30 boundary_skips=0 unfiltered=FAIL filtered=PASS
SUMMARY: MIDLAND sampled_days=30 boundary_skips=0 unfiltered=FAIL filtered=PASS
```

**All four checkpoint criteria met:** (1) leads 0-5 near-100% match / leads 6+ near-0% with a clean cut, (2) unfiltered gate fails with p05=0h, (3) filtered gate passes with min=p05=max=1h exactly, (4) boundary-skip count is zero (fully within archive reachability).

### Task 3 tracer (`forecast_experiment.py --city AUSTIN --start 2025-10-01 --end 2026-03-31`)

```
AUSTIN: assembled 4367 rows, scored 145 test rows, window 2025-10-01 -> 2026-03-31
candidate                mae        rmse      rows
persistence           54.985      90.270       145
raw_forecast           0.000       0.000       145

IDEALIZED LATENCY: [...caveat text, including the second data-source caveat...]
report written to data/experiment/experiment_report_AUSTIN.json

SUMMARY: AUSTIN rows_assembled=4367 rows_scored=145 window=2025-10-01->2026-03-31 persistence_mae=54.985 raw_forecast_mae=0.000 caveat_present=True
```

All plan-specified acceptance checks (`TRACER_OK`, `SPLIT_OK`) reproduced and passed against this live output.

## Known Stubs

None -- both new modules' machinery is fully wired to live data, not mocked/stubbed in production paths. Test files use synthetic data as designed (network-free per convention).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready:** `experiment_splits.calendar_split` and `forecast_experiment.py`'s anchored-pair-frame/scoring machinery are solid, tested, and live-verified. The calibration gate now genuinely passes as designed, and the corrected window (`config.FORECAST_EXPERIMENT_WINDOW_START = "2025-10-01"`, `WINDOW_END = None` resolving to "yesterday") is the authoritative window for every later plan in this phase.

**Needs review before proceeding:** the Critical Finding above (bulk forecast-archive data is bit-identical to reanalysis truth at this lead) should be explicitly discussed before Plan 03-02 scores additional arms on the same data source -- see that section for full detail and evidence.

---
*Phase: 03-ampacity-forecast-correction-experiment-compare-persistence*
*Plan: 01*
*Completed: 2026-09-29*
*Status: complete (design-premise checkpoint resolved; see Critical Finding for an unrelated, newly-discovered issue flagged for the next planning session)*
