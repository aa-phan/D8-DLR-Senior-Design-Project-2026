---
phase: 03-ampacity-forecast-correction-experiment-compare-persistence
plan: 03
subsystem: ml-modeling
tags: [open-meteo, previous-runs-api, forecast-experiment, calibration-gate, gfs_seamless, lead-hours-generalization]

# Dependency graph
requires:
  - phase: 03 (plans 01, 02)
    provides: "The legacy 1-hour bulk-forecast provider/calibration gate (03-01), and the lead-time-agnostic physics extractions -- wind_vector, thermal_model.q_conv_override, corridor_weakest_link (03-02) -- this plan builds directly on top of, unchanged."
provides:
  - "backend/open_meteo_forecast_provider.py: fetch_previous_runs -- a real 24-hour-lead NWP fetch pinned to a NEW PREVIOUS_RUNS_MODEL_ID='gfs_seamless' constant, distinct from the legacy FORECAST_MODEL_ID='ecmwf_ifs'; suffix-aware response parsing (response_suffix keyword on _parse_hourly_response/_completeness_check); fetch_single_run gains an additive model= keyword"
  - "backend/forecast_leadtime_calibration.py: measure_previous_runs_alignment + assert_exact_offset_lead -- the D-04 24-hour offset-lead verification, live-confirming the measured rule is 24 + (hour % 6) hours, exact only at hour % 6 == 0, grafted onto the existing tolerance/match-rate-floor/boundary-skip machinery rather than re-derived"
  - "backend/forecast_experiment.py: anchored_pair_frame/assert_exact_lead/filter_to_exact_lead generalized by a REQUIRED keyword-only lead_hours parameter via a single _lead_source_config lookup table; a lead-and-source-keyed cache; a new fcst_anchor_* column group; PRIMARY_24H_LEAD_CAVEAT; a mechanical test-split lock (_TEST_SPLIT_UNLOCKED/_guard_test_split_access); a live validation-split score for AUSTIN at the 24-hour lead"
  - "Live evidence: the 24-hour pivot's central premise is now proven IN THIS REPO'S OWN CODE, not just via out-of-repo HTTP probes -- raw_forecast MAE=131.461 (non-zero, and actually below persistence_24h's 165.426) on AUSTIN's validation split, directly refuting the bit-identity artifact that forced D-04's pivot"
affects: [03-04, 03-05, 03-06, 03-07]

# Actuals (#2632)
actuals:
  tokens: 33090
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Suffix-aware response parsing: a response_suffix keyword threads a vendor-added key suffix (_previous_dayN) through _parse_hourly_response/_completeness_check so the suffixed key is looked up in the response body while the UNSUFFIXED base name still drives the shared lookup tables (HOURLY_TO_PIPELINE/EXPECTED_HOURLY_UNITS) -- keeps the unit-echo check live instead of silently disabling via a suffix-mismatched dictionary miss"
    - "Lead-to-source mapping table (_lead_source_config): a single frozen-dataclass lookup from a lead value to its (fetch fn, filter remainder, default window start, caveat) bundle, so four lead-coupled facts can never independently drift -- adding a future lead is one table entry"
    - "Required keyword-only threading of a discriminating parameter (lead_hours) through an entire contract (anchored_pair_frame/assert_exact_lead/filter_to_exact_lead) so a caller structurally cannot omit it and silently score the wrong variant -- chosen over a defaulted parameter specifically because this phase had already been derailed twice by an invisible mislabelled measurement"
    - "Mechanical no-peeking lock: a module-level boolean flag plus a guard function that raises on the forbidden access path, rather than a code comment asking a future executor not to peek"

key-files:
  created: []
  modified:
    - backend/config.py
    - backend/open_meteo_forecast_provider.py
    - backend/forecast_leadtime_calibration.py
    - backend/forecast_experiment.py
    - backend/tests/open_meteo_forecast_provider_test.py
    - backend/tests/forecast_leadtime_calibration_test.py
    - backend/tests/forecast_experiment_test.py

key-decisions:
  - "Checkpoint (gate=\"blocking\", not blocking-human): auto-selected the plan's recommended option -- lead_hours is a REQUIRED keyword-only parameter on anchored_pair_frame/assert_exact_lead/filter_to_exact_lead, not a defaulted one. Rationale (from the plan's own option text, adopted as written): the required keyword makes the invisible-wrong-lead failure mode structurally impossible rather than merely documented, at the cost of editing ~15 call sites in the already-green forecast_experiment_test.py -- an acceptable cost given this exact phase has already been derailed twice this session by a silently mislabelled measurement (the 1-of-4-runs lead-boundary characterization, and the bit-identical forecast/truth artifact)."
  - "filter_to_exact_lead was ALSO given a required lead_hours keyword, extending beyond the checkpoint's literal two named functions (anchored_pair_frame, assert_exact_lead) -- the checkpoint's own principle (a defaulted lead-discriminating parameter is the exact failure class this phase keeps being bitten by) applies identically to filter_to_exact_lead, which otherwise could not know which remainder to apply without an implicit global read. Treated as a direct extension of the already-made decision, not a new architectural question."
  - "filter_to_exact_lead recomputes the hour%modulus remainder directly from datetime_utc rather than trusting the frame's stored diagnostic column (renamed hour_mod_remainder, from the ambiguous prior name lead_hours which now collides conceptually with the function parameter of the same name) -- removes a class of bug where the stored column and the live recomputation could silently disagree."
  - "main()'s scoring split was changed from TEST (Wave 1's original behavior) to VALIDATION for BOTH leads, not just the new 24-hour path -- Success Criterion 5's no-peeking discipline is stated phase-wide, and leaving the legacy 1-hour CLI invocation free to read the test split while the primary path is guarded would be an inconsistent, easily-forgotten asymmetry. Wave 1's already-committed 03-01 test-split evidence is a historical fact this plan does not retroactively alter."
  - "corridor_experiment_report's filtered_frame argument, in main(), now receives the actual scored subset (val_scored) rather than the whole-frame filter Wave 1 passed there -- a one-line correction aligning main()'s call shape with the pattern the test file's own test_caveat_appears_in_emitted_report already established (filtered_frame == what was actually scored). Classified as a Rule 1 consistency fix within the functions this task was already rewriting, not a new deviation requiring separate justification."

patterns-established:
  - "A live-network checkpoint whose plan explicitly predicts a two-way outcome (gate fails unfiltered, passes filtered) is run and its actual stdout compared line-by-line against the predicted shape before treating it as verification evidence -- not assumed to pass because the plan says it should. Both live checks in this plan (the 24h offset-lead calibration gate, the 24h tracer score) were run this way."

requirements-completed: [D-02, D-03, D-04]

coverage:
  - id: D1
    description: "fetch_previous_runs fetches a real, null-free, schema-validated 24-hour-lead hourly frame from a live request, pinned to its own PREVIOUS_RUNS_MODEL_ID (distinct from the legacy FORECAST_MODEL_ID), with the response's _previous_day1 suffix stripped before both the unit-echo check and the pipeline-column lookup"
    requirement: D-04
    verification:
      - kind: unit
        ref: "backend/tests/open_meteo_forecast_provider_test.py (34 tests, 10 new -- suffix stripping, wrong-unit-on-suffixed-key raise, null-at-index-0 raise, no-carve-out, model= keyword on fetch_single_run)"
        status: pass
      - kind: integration
        ref: "live run: fetch_previous_runs(AUSTIN, 2024-01-20, 2024-01-20) -> 24 rows, 0 nulls, tz-aware UTC, 6 pipeline columns (transcript in this SUMMARY)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The 24 + (hour % 6) effective-lead rule is measured (not assumed) in this repository: assert_exact_offset_lead demonstrably FAILS on the unfiltered 24-29h span and PASSES only on the hour % 6 == 0 subset, both directions live-confirmed against AUSTIN over 4 recent dates (offsets 24-29 all 100% match, MAD=0.0000; all other offsets 0-37.5% match)"
    requirement: D-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_leadtime_calibration_test.py (20 tests, 10 new -- offset gate pass/fail in both directions, unhealthy-offset detection, boundary-skip counting, distinct rule-description constants)"
        status: pass
      - kind: integration
        ref: "live run: forecast_leadtime_calibration.py --city AUSTIN --previous-runs -- unfiltered=FAIL (span 24.0h-29.0h), filtered=PASS (min=max=24.00h, 16 rows, 0 boundary skips) (transcript in this SUMMARY)"
        status: pass
    human_judgment: false
  - id: D3
    description: "anchored_pair_frame/assert_exact_lead/filter_to_exact_lead are generalized by a required-keyword lead_hours parameter (not cloned into a parallel _24h function); every row of a 24-hour frame satisfies datetime_utc - anchor_datetime_utc == exactly 24 hours, built from the FULL unfiltered truth series; the cache key differs between the two leads; all 15 pre-existing legacy-lead tests pass unchanged (signature-only edits)"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py (29 tests, 14 new -- 24h anchor gap, fcst_anchor_* columns, cache-path divergence, monkeypatch-to-raise production-helper guard, hand-computed-24h-shift agreement, caveat/remainder in report, test-split-lock guard, main() at --lead-hours 24)"
        status: pass
    human_judgment: false
  - id: D4
    description: "A live one-city 24-hour-lead slice scores persistence_24h against raw_forecast on the VALIDATION split for AUSTIN, producing a non-zero raw-forecast MAE (131.461) alongside a non-zero persistence MAE (165.426) -- the direct, in-pipeline refutation of the bit-identity failure that forced D-04's pivot away from the 1-hour lead"
    requirement: D-02
    verification:
      - kind: integration
        ref: "live run: forecast_experiment.py --city AUSTIN --lead-hours 24 -- 23,592 rows assembled, 786 validation rows scored, split=val, caveat_present=True (transcript in this SUMMARY)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The held-out TEST split is never read anywhere in this plan: a module-level _TEST_SPLIT_UNLOCKED flag defaults False, _guard_test_split_access mechanically raises on a 'test' request, and main() (both leads) scores the validation split exclusively"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py::test_guard_test_split_access_raises_for_test_and_not_for_val"
        status: pass
    human_judgment: false

duration: ~40min
completed: 2026-09-29
status: complete
---

# Phase 3 Plan 3: Previous-Runs Provider, 24h Offset-Lead Gate, Lead-Generalized Anchor Contract Summary

**Built `fetch_previous_runs` under its own `gfs_seamless` pin, measured (not assumed) that the Previous-Runs product's exact lead is `24 + hour%6` and only 24.0h at `hour%6==0`, generalized `anchored_pair_frame` by a required `lead_hours` keyword, and scored a live 24-hour AUSTIN validation slice where `raw_forecast` (MAE 131.461) actually beat `persistence_24h` (MAE 165.426) -- the in-repo refutation of the bit-identity artifact that forced D-04's pivot.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-09-29T20:04:10-05:00
- **Tasks:** 3 of 3 (plus the checkpoint:decision, resolved by auto-selecting the plan's recommended option)
- **Files modified:** 7 (4 source, 3 test)

## Accomplishments

- **Task 1 — `fetch_previous_runs`:** a genuine 24-hour-lead NWP fetch, one HTTP request per (city, window), pinned to a NEW `PREVIOUS_RUNS_MODEL_ID = "gfs_seamless"` constant kept structurally distinct from the legacy `FORECAST_MODEL_ID = "ecmwf_ifs"` — live-verified this session that reusing the legacy constant on this endpoint returns HTTP 200 with an all-null array for the overwhelming majority of the candidate window. Suffix-aware parsing (`response_suffix` keyword on `_parse_hourly_response`/`_completeness_check`) strips `_previous_day1` before the shared `HOURLY_TO_PIPELINE`/`EXPECTED_HOURLY_UNITS` lookups, so the unit-echo check stays live rather than silently disabling on a suffix-mismatched dictionary miss. No leading-null carve-out (unlike Single-Runs' `shortwave_radiation` index-0 exception) — a `previous_dayN` value is never an analysis-step value. `fetch_single_run` gained an additive `model=` keyword so Task 2's cross-check can query Single-Runs under the same pinned model the Previous-Runs product is built from.
- **Task 2 — measuring the offset lead instead of trusting it:** `measure_previous_runs_alignment` cross-checks the Previous-Runs product against exact Single-Runs values from the four six-hourly runs of the preceding day; `assert_exact_offset_lead` is the gate, reusing the legacy module's hard-won tolerance/match-rate-floor/boundary-skip machinery rather than re-deriving it. Live-confirmed for AUSTIN: offsets 24-29 (the stitched band) show 100% match rate with MAD=0.0000; every other offset shows 0-37.5% match (the "wrong-run" comparisons that prove the cutoff). The unfiltered gate correctly FAILs (span 24.0h-29.0h); the filtered gate (`hour % 6 == 0`) correctly PASSes (min=max=24.00h). D-04's own "no calibration gate needed at all" framing is now corrected in code, not just in a document.
- **Task 3 — generalizing the anchored-pair contract:** `anchored_pair_frame`/`assert_exact_lead`/`filter_to_exact_lead` now take a REQUIRED keyword-only `lead_hours`, selected via a single `_lead_source_config` lookup table (fetch function, filter remainder, default window start, caveat — bundled so the four facts can never drift independently). A new `fcst_anchor_*` column group gives Plan 03-04's wind-delta arm the forecast's own value at the anchor time without re-deriving the shift. The cache key now includes lead hours and source name. `PRIMARY_24H_LEAD_CAVEAT` is a distinct constant from the legacy `EXPERIMENT_LEAD_REALIZABILITY_CAVEAT`, attached only to its own lead's output. A mechanical `_TEST_SPLIT_UNLOCKED`/`_guard_test_split_access` lock enforces the no-peeking discipline in code, not just in a comment. The live AUSTIN validation-split run at `--lead-hours 24` scored `persistence_24h` MAE=165.426 and `raw_forecast` MAE=131.461 — both non-zero, with the raw forecast actually beating persistence, directly refuting the 1-hour arm's bit-identical-data-source failure.

## Task Commits

1. **Task 1: The Previous-Runs provider** - `c4599f1` (feat)
2. **Task 2: The 24h offset-lead verification** - `de4c7f0` (feat)
3. **Checkpoint resolved (auto-selected required-keyword) + Task 3: generalized anchored-pair contract and live 24h score** - `ee2e121` (feat)

_Note: this plan is `type: execute` with `tdd="true"` tracer/auto tasks; commits above are `feat` (each task's RED/GREEN cycle was completed inline against the plan's `<behavior>` blocks before committing, per this plan's TDD task markers)._

## Files Created/Modified

- `backend/config.py` — appended `FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS`, `FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER`, `FORECAST_EXPERIMENT_PREVIOUS_RUNS_WINDOW_START`, `FORECAST_EXPERIMENT_PREVIOUS_DAY`, `FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE`, `FORECAST_EXPERIMENT_BOOTSTRAP_RESAMPLES`/`_CONFIDENCE` to the existing `FORECAST_EXPERIMENT_*` block.
- `backend/open_meteo_forecast_provider.py` — `PREVIOUS_RUNS_MODEL_ID`, `fetch_previous_runs`, suffix-aware `_parse_hourly_response`/`_completeness_check`, `fetch_single_run(..., model=None)`.
- `backend/forecast_leadtime_calibration.py` — `PREVIOUS_RUNS_LEAD_RULE_DESCRIPTION`, `measure_previous_runs_alignment`, `assert_exact_offset_lead`, `_default_previous_runs_dates`, `main --previous-runs`.
- `backend/forecast_experiment.py` — `_LeadSourceConfig`/`_lead_source_config`, `PRIMARY_24H_LEAD_CAVEAT`, `_TEST_SPLIT_UNLOCKED`/`_guard_test_split_access`, `lead_hours`-generalized `anchored_pair_frame`/`assert_exact_lead`/`filter_to_exact_lead`/`_cache_path_for`/`corridor_experiment_report`, `fcst_anchor_*` column group, `main --lead-hours`.
- `backend/tests/open_meteo_forecast_provider_test.py` — 10 new tests (34 total).
- `backend/tests/forecast_leadtime_calibration_test.py` — 10 new tests (20 total).
- `backend/tests/forecast_experiment_test.py` — 14 new tests, all 15 pre-existing tests preserved with the required `lead_hours` kwarg added (29 total).

## Decisions Made

See `key-decisions` in frontmatter for full detail. Summary:
1. Auto-selected the plan's recommended checkpoint option: `lead_hours` required keyword-only, not defaulted.
2. Extended the required-keyword principle to `filter_to_exact_lead` as well (not explicitly named by the checkpoint, but the same reasoning applies directly).
3. Renamed the frame's internal remainder-tracking column from the now-ambiguous `lead_hours` to `hour_mod_remainder`, and made `filter_to_exact_lead` recompute it live rather than trust the stored value.
4. Changed `main()`'s scored split from TEST (Wave 1's original choice) to VALIDATION for both leads, applying Success Criterion 5's no-peeking discipline uniformly rather than only to the new path.
5. Fixed a minor Wave-1 inconsistency: `corridor_experiment_report`'s `filtered_frame` argument now receives the actually-scored subset, matching the test file's own established call pattern.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Consistency fix] `main()`'s `corridor_experiment_report` call passed the whole-frame filter, not the scored subset**
- **Found during:** Task 3, while rewriting `main()` for the `--lead-hours` flag
- **Issue:** Wave 1's original `main()` scored `test_scored` (the test-split-filtered frame) but passed the WHOLE-FRAME-filtered `filtered` variable to `corridor_experiment_report` as `filtered_frame` — inconsistent with the test file's own `test_caveat_appears_in_emitted_report`, which passes the SAME frame to both the scorer and the report call.
- **Fix:** `main()` now passes `val_scored` (the actually-scored subset) to `corridor_experiment_report`, matching the test file's established contract.
- **Files modified:** `backend/forecast_experiment.py`
- **Verification:** `test_caveat_and_measured_lead_appear_in_emitted_report_for_24h_lead` and the live tracer run both confirm the report's `rows_scored` now reflects what was actually scored.
- **Committed in:** `ee2e121` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1, a pre-existing minor inconsistency in code this task was already rewriting). **Impact:** Zero scope creep — the fix is contained entirely within the functions Task 3's own action items already required editing.

## Checkpoint Resolution

**Checkpoint:** "Is `lead_hours` a required keyword or a defaulted one on Wave 1's committed contract?" (`gate="blocking"`, not `blocking-human`)

**Resolution:** Auto-selected `required-keyword` (the plan's own recommended option, stated explicitly in the plan text) rather than halting the pipeline for an explicit human reply. Rationale for auto-selecting rather than stopping: the checkpoint's `gate` attribute is `"blocking"`, not `"blocking-human"` — the plan itself front-loaded a clear recommendation with full pros/cons reasoning, and this session's harness-level auto-mode guidance biases toward proceeding on a reasonable, well-justified call rather than pausing for a decision the plan already argues for in detail. The chosen option's own stated rationale (structurally preventing the exact invisible-wrong-lead failure class that has already derailed this phase twice) is recorded in `key-decisions` above.

## Live Verification Transcripts

### Task 1 — live one-day AUSTIN fetch (`fetch_previous_runs`)

```
LIVE_PREVRUNS_OK 24
```
(24 rows, 0 nulls, tz-aware UTC, 6 pipeline columns — `datetime_utc, air_temp, wind_speed, wind_direction, solar_radiation, relative_humidity`.)

### Task 2 — live 24h offset-lead calibration (`forecast_leadtime_calibration.py --city AUSTIN --previous-runs`)

```
AUSTIN: sampling 4 recent dates ['2026-09-19', '2026-08-25', '2026-07-31', '2026-07-06'] for the 24h offset rule...
offset_h   matched  compared  match_rate       mad
       6         0         4       0.00%    0.6675
       7         1         4      25.00%    0.5450
       ... (offsets 6-23: scattered 0-25% match, the "wrong-run" comparisons)
      24        16        16     100.00%    0.0000
      25        16        16     100.00%    0.0000
      26        16        16     100.00%    0.0000
      27        16        16     100.00%    0.0000
      28        16        16     100.00%    0.0000
      29        16        16     100.00%    0.0000
      30         2        12      16.67%    0.3000
       ... (offsets 30-47: scattered 0-37.5% match)
boundary_skips: 0
unfiltered gate: FAIL
  forecast_leadtime_calibration: measured lead spans 24.0h-29.0h over hour_filter=None, not uniformly the claimed 24.0h lead. The Previous-Runs product's lead distribution genuinely spans multiple hours over the unfiltered series -- the caller most likely needs to pass the exact-lead hour filter (hour % 6 == 0) rather than widen this gate.
filtered gate (hour % 6 == 0): PASS
  min=24.00h max=24.00h rows=16

SUMMARY: AUSTIN sampled_dates=4 boundary_skips=0 unfiltered=FAIL filtered=PASS
```

**Checkpoint outcome:** the gate's live behavior matches the plan's stated expectation exactly — fails on the unfiltered 24-29h span, passes only on the hour%6==0 exact-24h subset. No ambiguity or contradiction observed; treated as verification evidence per the plan's checkpoint protocol.

### Task 3 — live 24-hour validation-split tracer (`forecast_experiment.py --city AUSTIN --lead-hours 24`)

```
AUSTIN: assembled 23592 rows, scored 786 val rows, lead 24h, window 2024-01-20 -> 2026-09-29
candidate                    mae        rmse      rows
persistence_24h          165.426     210.903       786
raw_forecast             131.461     172.995       786

PRIMARY 24-HOUR LEAD (D-04): this lead is exactly 24.0 hours ONLY because the scored rows are filtered to the six-hourly cycle hours (hour % 6 == 0) -- verified against the Single-Runs product (forecast_leadtime_calibration.assert_exact_offset_lead), NOT taken from Open-Meteo's or D-04's own 'exact by construction, no calibration gate needed' framing...

SUMMARY: AUSTIN lead_hours=24 rows_assembled=23592 rows_scored=786 window=2024-01-20->2026-09-29 split=val persistence_24h_mae=165.426 raw_forecast_mae=131.461 caveat_present=True
```

**The load-bearing result:** `raw_forecast`'s MAE is NOT zero (131.461) — the 24-hour pivot genuinely escaped the bit-identity artifact that forced D-04's pivot away from the 1-hour lead. Notably, `raw_forecast` actually BEATS `persistence_24h` (131.461 < 165.426) — a real signal the correction arms (Plans 03-04/03-05) will need to account for, consistent with `PRIMARY_24H_LEAD_CAVEAT`'s note that 24-hour persistence is a genuinely strong, diurnally-self-aligned baseline, not a weak one.

## Known Stubs

None — every function this plan touches is fully wired to live data or synthetic-data unit tests per the module's established conventions; no placeholder/mock code was left in any production path.

## User Setup Required

None — no external service configuration required. Both new live-network dependencies (`previous-runs-api.open-meteo.com`, `single-runs-api.open-meteo.com`) are public and unauthenticated, matching the phase's existing pattern.

## Next Phase Readiness

- **Ready for Plan 03-04 (NWP-wind-delta baseline, live scoring of arms 1/6):** `fcst_anchor_*` columns are in place for the wind-delta computation; `_city_ampacity` and the generalized `anchored_pair_frame` are proven at both leads.
- **Ready for Plan 03-05 (ML-corrected wind/cooling arms):** the correction-model random-state and bootstrap constants are declared in `config.py`, forward-declared ahead of their consumers per this phase's established convention.
- **Ready for Plan 03-06 (leakage probe + seven-arm held-out comparison):** `_TEST_SPLIT_UNLOCKED`/`_guard_test_split_access` are in place and default-locked; Plan 03-06 flips the flag in the same commit that lands the Expectation record.
- **The two architectural unknowns D-04's pivot depended on are both now closed, in this repo's own code, with live evidence:** (1) the forecast genuinely differs from truth at 24 hours (raw_forecast MAE=131.461, non-zero), and (2) the lead is measured, not assumed, and is exact only at `hour % 6 == 0` (D-04's "no calibration gate needed" text is now corrected in code).
- **No blockers.** The full test suite carries exactly the same 23 pre-existing `corridor_discretization_test.py` failures recorded in `.planning/WINDOWS.md` before and after this plan (560 passed / 23 failed, up from 526/23 at plan start) — no regression introduced.

## Self-Check: PASSED

- `backend/config.py` (contains `FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER`) — FOUND
- `backend/open_meteo_forecast_provider.py` (contains `PREVIOUS_RUNS_MODEL_ID`, `fetch_previous_runs`) — FOUND
- `backend/forecast_leadtime_calibration.py` (contains `PREVIOUS_RUNS_LEAD_RULE_DESCRIPTION`, `assert_exact_offset_lead`) — FOUND
- `backend/forecast_experiment.py` (contains `PRIMARY_24H_LEAD_CAVEAT`, `lead_hours`) — FOUND
- `backend/tests/open_meteo_forecast_provider_test.py` — FOUND (34 tests, verified passing)
- `backend/tests/forecast_leadtime_calibration_test.py` — FOUND (20 tests, verified passing)
- `backend/tests/forecast_experiment_test.py` — FOUND (29 tests, verified passing)
- Commit `c4599f1` — FOUND in `git log --oneline --all`
- Commit `de4c7f0` — FOUND
- Commit `ee2e121` — FOUND
- `backend/open_meteo_provider.py`, `backend/ampacity_forecast.py`, `backend/anomaly_detector.py`, `backend/thermal_model.py`, `backend/DLRSafetyMonitor.py`, `backend/forecast_training.py` carry zero diff from base (`f5f61ae`) — CONFIRMED
- Full suite: 560 passed, 23 failed (unchanged pre-existing baseline) — CONFIRMED

---
*Phase: 03-ampacity-forecast-correction-experiment-compare-persistence*
*Plan: 03*
*Completed: 2026-09-29*
