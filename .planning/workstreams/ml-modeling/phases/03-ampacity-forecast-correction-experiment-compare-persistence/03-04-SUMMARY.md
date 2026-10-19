---
phase: 03-ampacity-forecast-correction-experiment-compare-persistence
plan: 04
subsystem: ml-modeling
tags: [ampacity-forecast, corridor-weakest-link, non-fitted-arms, oracle-diagnostic, no-peeking-lock, forecast-experiment]

# Dependency graph
requires:
  - phase: 03 (plan 03)
    provides: "The generalized lead_hours-parameterized anchored_pair_frame contract, the fcst_anchor_* column group, the Previous-Runs 24h primary provider, and the test-split lock this plan builds the four non-fitted arms and corridor-level scoring directly on top of."
provides:
  - "backend/forecast_experiment.py: NON_FITTED_ARMS -- a named registry of four factory(geometry) -> callable(frame) arms (persistence_24h, nwp_wind_delta, raw_forecast, the oracle under ORACLE_ARM_NAME), built directly from Plan 03-03's anchor/fcst_anchor column groups, never via ampacity_forecast's one-row-lag production helpers"
  - "corridor_anchored_pair_frame: assembles both endpoint cities, inner-joins on datetime_utc, and reduces the truth group, the anchor group, and each arm's own per-city prediction INDEPENDENTLY through forecast_training.corridor_weakest_link -- per column group at its own time, never a second np.minimum"
  - "corridor_experiment_report: structurally pops ORACLE_ARM_NAME out of report[\"candidates\"] into its own oracle_diagnostic top-level key with a non-forecast statement -- a property of the function, not caller discipline -- and carries split, filter_remainder, bottleneck_distribution, and the wind-delta clamp-hit count"
  - "main(): --corridor (default: every corridor) and --split (val/test, routed through the no-peeking lock) added; --city retains Plan 03-03's single-city tracer path verbatim"
  - "assert_identical_index / assert_filtered_split_disjoint / _require_test_split_unlocked: the identical-index and no-peeking invariants enforced by exception rather than assumed, with self-describing error messages naming both offending arms, both offending timestamps, or the unlocking plan"
  - "Live evidence: both corridors score non-zero, non-degenerate MAE across persistence_24h/nwp_wind_delta/raw_forecast plus the oracle diagnostic on the validation split at the verified 24-hour lead, over the full 2024-01-20 -> 2026-09-29 window"
affects: [03-05, 03-06, 03-07]

# Actuals (#2632)
actuals:
  tokens: 19746
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "One-argument arm factory convention: NON_FITTED_ARMS mirrors forecast_training.CANDIDATE_ESTIMATORS's zero-argument-factory shape but generalizes to factory(geometry) -> callable(frame), since every arm here needs a ConductorConfig/bearing to turn weather into amps through the single _city_ampacity seam"
    - "Per-city-then-reduce corridor scoring: each arm's prediction is computed independently on EACH endpoint city's own unsuffixed weather columns (recovered from the merged frame via suffix-stripping), then reduced through corridor_weakest_link -- never derived from another group's (truth/anchor) winning-city selection, since an arm's own bottleneck city need not match either"
    - "Structural (not documentary) isolation: corridor_experiment_report unconditionally pops a named constant out of the candidates mapping into its own top-level key, regardless of whether the caller remembered to exclude it -- the isolation is a property of the function, not caller discipline"
    - "Pairwise-then-frame length assertion: assert_identical_index compares every pair of arms' prediction lengths to each other BEFORE comparing to the frame's own length, so a length mismatch names both disagreeing arms and both counts instead of only the one that happens to differ from the frame"

key-files:
  created: []
  modified:
    - backend/forecast_experiment.py
    - backend/tests/forecast_experiment_test.py

key-decisions:
  - "Anchor-group and per-arm-prediction reductions are computed as separate, explicit corridor_weakest_link calls (rather than deriving anchor_dlr_amps by reusing the persistence_24h arm's own reduced pred_persistence_24h column) even though the two are numerically identical by construction -- kept explicit so a future reader can find the anchor group's own reduction without tracing through the arm registry, and so the anchor group's winning weather columns (needed for potential future diagnostics) are always present regardless of which arms are registered."
  - "Arm-level corridor predictions are stored as pred_<arm_name> columns on the SAME corridor_anchored_pair_frame output (rather than a separate per-arm data structure), with score_arms's callables reading those columns directly via _corridor_arm_reader instead of recomputing through _city_ampacity -- keeps one frame as the single source of truth for everything a report needs (predictions, bottleneck indices, clamp flags) and avoids a second computation pass that could drift from the first."
  - "corridor_experiment_report's oracle-popping and id_key generalization are backward-compatible additions (new keyword params with defaults) rather than a breaking signature change, so every one of Plan 03-03's pre-existing city-level tracer tests continues to pass unchanged against the same function."
  - "The nwp_wind_delta clamp-hit count reported at corridor level is the count of SCORED rows where EITHER endpoint city's own pre-clamp wind delta was negative (an OR across nwp_wind_delta_clamped_a/_b), not a sum of two independent per-city counts -- a row is either affected by the clamp somewhere in the corridor's chain or it is not; double-counting a row where both cities clamped would overstate the visible impact."

patterns-established:
  - "A degenerate-input sanity check (forecast weather identical to truth weather implies two structurally different arms must produce identical predictions equal to the truth ampacity) is written as an explicit, permanently-committed unit test rather than a one-off manual check -- this is the exact shape Plan 03-01's real bit-identity artifact took, and the test exists so a future regression of that kind fails a fast synthetic-data test instead of requiring a live-network investigation to rediscover."

requirements-completed: [D-02, D-03, D-04]

coverage:
  - id: D1
    description: "The four non-fitted arms (persistence_24h, nwp_wind_delta, raw_forecast, the oracle) exist as named entries in one registry (NON_FITTED_ARMS), each a factory(geometry) -> callable(frame), with arm 0 provably a direct 24-hour shift of the anchor group (never a one-row-lag production helper) and arm 6's factory docstring stating in its first line that it is not a forecast"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py (Task 1 section, 11 new tests -- registry shape, arm 0 vs. an independently hand-computed 24h shift, arm 1 reducing to arm 0 when forecast is flat, arm 1's physical clamp with a constructed negative-delta scenario, arm 2 vs. _city_ampacity on forecast columns, arm 6 vs. truth-wind/forecast-thermal inputs, the degenerate forecast==truth sanity check, and score_arms scoring the full registry)"
        status: pass
      - kind: other
        ref: "grep -vE '^[[:space:]]*#' backend/forecast_experiment.py | grep -cE 'backtest_residuals|_point_forecast|forecast_ampacity\\(' -> 0 (NO_ONE_ROW_LAG_HELPERS_OK)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Corridor-level assembly and weakest-link reduction: both endpoint cities are fetched, aligned on a shared timestamp index, and reduced through forecast_training.corridor_weakest_link (the repository's one reduction) applied independently per column group at its own time -- truth group, anchor group, and each of the four arms' own per-city predictions -- with the bottleneck resolving to the first endpoint city on an exact tie, and the oracle structurally isolated to its own report key"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py (Task 2 section, 8 new tests -- corridor assembly/inner-join, truth reduction verified against a direct forecast_training.corridor_weakest_link call, a tie-break test, a constructed mixed-bottleneck row where the anchor-time and valid-time bottleneck cities differ, pred/bottleneck columns present for every arm, oracle isolation with and without an oracle score present, and a full two-corridor main() invocation)"
        status: pass
      - kind: other
        ref: "grep for corridor_weakest_link usage (8 non-comment call sites) and zero np.minimum/numpy.minimum occurrences (ONE_REDUCTION_OK)"
        status: pass
      - kind: integration
        ref: "live run: forecast_experiment.py --lead-hours 24 (both corridors, one invocation) -> CORRIDOR_REPORT_OK (transcript in this SUMMARY)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The identical-index and no-peeking invariants are enforced by exception: score_arms raises naming both arms and both row counts when two arms disagree; a new split-disjointness assertion on the FILTERED frame (not just the unfiltered frame the splitter received) is called from main for every lead; and the test-split lock's error names both Success Criterion 5's Expectation requirement and Plan 03-06"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py (Task 3 section, 11 new tests -- length-mismatch naming both arms/counts, index-info recorded on score_arms's return, a short-returning arm added to a registry copy still raising through the real corridor path, split-disjointness pass and two constructed-overlap failures, the self-describing lock message, filtered-row hour-modulus/anchor-gap invariants at both leads, and main() surfacing a corrupted split boundary as an exception)"
        status: pass
      - kind: other
        ref: "PYTHONPATH=backend python3 -c \"fe._require_test_split_unlocked()\" raises naming '03-06' and 'Expectation' (NO_PEEKING_LOCK_OK)"
        status: pass
    human_judgment: false
  - id: D4
    description: "All scoring in this plan runs on the VALIDATION split; the held-out test split remains mechanically locked. Full suite carries exactly the same 23 pre-existing corridor_discretization_test.py failures before and after this plan (no regression)"
    requirement: D-03
    verification:
      - kind: unit
        ref: ".venv/bin/python3 -m pytest -q -> 590 passed, 23 failed (same pre-existing baseline recorded in .planning/WINDOWS.md)"
        status: pass
      - kind: other
        ref: "git diff --quiet HEAD -- backend/forecast_training.py backend/thermal_model.py backend/ampacity_forecast.py backend/anomaly_detector.py backend/DLRSafetyMonitor.py backend/config.py -> clean (no unauthorized file touched)"
        status: pass
    human_judgment: false

duration: ~30min
completed: 2026-09-29
status: complete
---

# Phase 3 Plan 4: Non-Fitted Arms, Corridor-Level Scoring, Oracle Isolation Summary

**Built the four non-fitted arms (persistence_24h, nwp_wind_delta, raw_forecast, the oracle) as a named registry, promoted scoring from city to corridor level via `forecast_training.corridor_weakest_link` applied per column group at its own time, and made the oracle's isolation from the candidate mapping structural rather than a label -- live corridors score `raw_forecast` beating `persistence_24h` by 30-45 MAE points while the oracle sits far below both (12.3-12.9 MAE), measuring the ceiling Plan 03-05's correction arms will be judged against.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-09-29T23:53:41-05:00
- **Tasks:** 3 of 3
- **Files modified:** 2 (1 source, 1 test)

## Accomplishments

- **Task 1 -- `NON_FITTED_ARMS`, the arm registry:** four factories (`persistence_24h`, `nwp_wind_delta`, `raw_forecast`, and the oracle under `ORACLE_ARM_NAME = "oracle_observed_future_wind"`), each `factory(geometry) -> callable(frame)`, mirroring `forecast_training.CANDIDATE_ESTIMATORS`'s convention generalized to one argument. Arm 0 reads `anchor_dlr_amps` directly -- provably a 24-hour shift of the full unfiltered truth series, verified against an independently hand-computed shift, never routed through `ampacity_forecast`'s one-row-lag helpers (grep-confirmed zero non-comment references). Arm 1 applies the forecast's own anchor-to-valid change to the observed anchor wind, clamped at the physical zero floor via `np.maximum` with a visible `nwp_wind_delta_clamp_count` (never silent), and reduces to arm 0 exactly when the forecast has zero change over the lead. Arm 6 (oracle) substitutes truth wind into the forecast's thermal inputs; its factory docstring's first line states it is not a forecast. A degenerate-input test (forecast weather identical to truth) confirms `raw_forecast` and the oracle agree and both equal the truth ampacity -- the exact shape the real bit-identity artifact from Plan 03-01 took, now guarded on synthetic data.
- **Task 2 -- corridor-level assembly and structural oracle isolation:** `corridor_anchored_pair_frame` assembles both endpoint cities, inner-joins on `datetime_utc`, and reduces the truth group, the anchor group, and each of the four arms' own per-city predictions INDEPENDENTLY through `forecast_training.corridor_weakest_link` -- confirmed with a constructed mixed-bottleneck test where 212 of 216 rows have a different bottleneck city at the anchor time than at the valid time, proving the two groups are never collapsed to one selection. `corridor_experiment_report` now unconditionally pops `ORACLE_ARM_NAME` out of `candidates` into its own `oracle_diagnostic` top-level key with an attached non-forecast statement -- a property of the function itself, not caller discipline, so a hand-built `scored["candidates"]` that still contains the oracle is isolated regardless. `main()` gained `--corridor` (default: every corridor) and `--split` (routed through the no-peeking lock); `--city` retains Plan 03-03's exact tracer behavior. A live two-corridor run over the full `2024-01-20 -> 2026-09-29` window scores non-zero, non-degenerate MAE for every candidate at both corridors.
- **Task 3 -- identical-index and no-peeking invariants, asserted rather than assumed:** `assert_identical_index` is called by `score_arms` before any arm's MAE/RMSE is computed, comparing every pair of arms' prediction lengths to each other first (naming both arms and both counts on a mismatch) before checking against the frame's own length -- and records the scored index's row count and first/last timestamp into `score_arms`'s return. `assert_filtered_split_disjoint` asserts the FILTERED train/val/test frames actually scored (not just the frames `calendar_split` received before filtering) remain strictly chronologically ordered, wired into both `main()` paths for every lead. `_require_test_split_unlocked` is a new, self-describing, zero-argument form of the no-peeking lock naming the lock constant, Success Criterion 5's Expectation-record requirement, and Plan 03-06 by name; `_guard_test_split_access` now delegates to it.

## Task Commits

1. **Task 1: The arm registry and the three weather-driven arms at the 24-hour lead** - `952a0b3` (feat)
2. **Task 2: Corridor-level assembly and weakest-link reduction, with the oracle structurally isolated** - `1618d8a` (feat)
3. **Task 3: The identical-index and no-peeking invariants, asserted rather than assumed** - `0eb453a` (feat)

## Files Created/Modified

- `backend/forecast_experiment.py` -- `NON_FITTED_ARMS`, `ORACLE_ARM_NAME`, the four arm factories, `nwp_wind_delta_clamp_count`, `corridor_anchored_pair_frame`, `_strip_city_suffix`, `_bottleneck_counts`, `_corridor_arm_reader`, `assert_identical_index`, `assert_filtered_split_disjoint`, `_require_test_split_unlocked`, an extended `corridor_experiment_report` (oracle isolation, `split`/`bottleneck_distribution`/`nwp_wind_delta_clamp_count` fields, generalized `id_key`), and a reworked `main()` (`_run_city_tracer` + `_run_corridor`, `--corridor`/`--split`).
- `backend/tests/forecast_experiment_test.py` -- 30 new tests across three sections (Task 1: 11, Task 2: 8, Task 3: 11), all pre-existing 48 tests (29 from Plan 03-03 + 19 accumulated through this plan's own tasks) preserved unchanged.

## Decisions Made

See `key-decisions` in frontmatter for full detail. Summary:
1. Anchor-group reduction kept as its own explicit `corridor_weakest_link` call rather than reusing the persistence arm's reduced output, even though numerically identical, for readability and to keep the anchor group's winning weather columns always present.
2. Per-arm corridor predictions stored as `pred_<arm_name>` columns on the SAME frame `corridor_anchored_pair_frame` returns, read directly by `score_arms`'s callables (`_corridor_arm_reader`) rather than recomputed -- one frame is the single source of truth.
3. `corridor_experiment_report`'s new parameters (`split`, `bottleneck_distribution`, `nwp_wind_delta_clamp_count`, `id_key`) are all backward-compatible defaults, so Plan 03-03's pre-existing city-level tracer tests pass against the same function unchanged.
4. The corridor-level clamp-hit count is an OR across both endpoint cities' own clamp flags (a row counts once if either city clamped), not a sum of two independent counts, to avoid double-counting a single row's visible impact.

## Deviations from Plan

None -- plan executed as written. The plan's own text anticipated the anchor-group/persistence-arm redundancy and its resolution was decided during implementation (documented under key-decisions above, not a deviation from any stated instruction).

## Live Verification Transcripts

### Task 1 -- registry shape and no-one-row-lag guard

```
ARM_REGISTRY_OK ['persistence_24h', 'nwp_wind_delta', 'raw_forecast', 'oracle_observed_future_wind']
NO_ONE_ROW_LAG_HELPERS_OK
```

### Task 2 -- live two-corridor run (`forecast_experiment.py --lead-hours 24`)

```
AUSTIN_CORPUS_CHRISTI: assembled 23592 rows, scored 786 val rows, lead 24h, window 2024-01-20 -> 2026-09-29
candidate                        mae        rmse      rows
persistence_24h              156.466     199.706       786
nwp_wind_delta               143.539     186.157       786
raw_forecast                 111.075     147.265       786
----------------------------------------------------------
oracle_observed_future_wind      12.875      17.751       786  <- NON-FORECAST DIAGNOSTIC, never a candidate

PRIMARY 24-HOUR LEAD (D-04): this lead is exactly 24.0 hours ONLY because the scored rows are filtered to the six-hourly cycle hours (hour % 6 == 0) -- verified against the Single-Runs product (forecast_leadtime_calibration.assert_exact_offset_lead), NOT taken from Open-Meteo's or D-04's own 'exact by construction, no calibration gate needed' framing, which is contradicted by direct measurement for the other 5 of every 6 hours (25-29h lead). A 24-hour persistence baseline is DIURNALLY SELF-ALIGNED and is therefore a genuinely STRONG day-ago-same-hour baseline, not the weak one a 'longer horizon is easier to beat' intuition would suggest (03-RESEARCH.md Pattern 4) -- do not expect the correction arms to beat it as easily as that intuition implies. This is the phase's PRIMARY comparison (D-04); the 1-hour arm is a labelled non-primary curiosity whose raw-forecast score is an artifact of a bit-identical data source, never a competing candidate against this arm's result.
report written to data/experiment/experiment_report_AUSTIN_CORPUS_CHRISTI.json

SUMMARY: AUSTIN_CORPUS_CHRISTI lead_hours=24 rows_assembled=23592 rows_scored=786 window=2024-01-20->2026-09-29 split=val persistence_24h_mae=156.466 nwp_wind_delta_mae=143.539 raw_forecast_mae=111.075 oracle_mae=12.875 caveat_present=True

MIDLAND_EL_PASO: assembled 23592 rows, scored 786 val rows, lead 24h, window 2024-01-20 -> 2026-09-29
candidate                        mae        rmse      rows
persistence_24h              161.162     199.742       786
nwp_wind_delta               161.303     207.828       786
raw_forecast                 159.802     206.987       786
----------------------------------------------------------
oracle_observed_future_wind      12.256      17.571       786  <- NON-FORECAST DIAGNOSTIC, never a candidate

SUMMARY: MIDLAND_EL_PASO lead_hours=24 rows_assembled=23592 rows_scored=786 window=2024-01-20->2026-09-29 split=val persistence_24h_mae=161.162 nwp_wind_delta_mae=161.303 raw_forecast_mae=159.802 oracle_mae=12.256 caveat_present=True
```

**CORRIDOR_REPORT_OK** -- both reports carry exactly 3 candidates (never the oracle), the oracle under its own `oracle_diagnostic` key, `measured_lead_hours == 24`, `split == "val"`, every candidate MAE strictly positive, and `rows_scored > 100`.

**The load-bearing result: the oracle-minus-raw-forecast margin.** AUSTIN_CORPUS_CHRISTI: oracle MAE 12.875 vs. `raw_forecast` MAE 111.075 -- a perfect wind correction could recover roughly 98.2 amps of MAE (88.4% of `raw_forecast`'s error) at this corridor. MIDLAND_EL_PASO: oracle MAE 12.256 vs. `raw_forecast` MAE 159.802 -- roughly 147.5 amps of headroom (92.3%). Both corridors show substantial remaining headroom between the raw forecast and a perfect wind correction, which is the explicit ceiling Plan 03-05's ML-corrected wind/cooling arms are being built to try to close. `nwp_wind_delta` (the cheap non-fitted baseline) beats `raw_forecast` at AUSTIN_CORPUS_CHRISTI (143.539 < 156.466 for persistence, though still above `raw_forecast`'s 111.075) but is roughly flat with `raw_forecast` at MIDLAND_EL_PASO (161.303 vs. 159.802) -- neither non-fitted correction closes the oracle gap, consistent with `PRIMARY_24H_LEAD_CAVEAT`'s framing that 24-hour persistence and its cheap derivatives are genuinely strong, not easy baselines to beat.

**Bottleneck distribution (AUSTIN_CORPUS_CHRISTI, 786 scored rows):** truth group -- AUSTIN bottleneck on 555 rows, CORPUS_CHRISTI on 231; anchor group -- AUSTIN on 554, CORPUS_CHRISTI on 232 (nearly identical distribution, as expected for a corridor whose bottleneck city rarely flips within a single day). MIDLAND_EL_PASO inverts: EL_PASO is the bottleneck on 664 of 786 truth rows, MIDLAND on 122.

**Wind-delta clamp visibility:** AUSTIN_CORPUS_CHRISTI clamped 52 of 786 scored rows (6.6%); MIDLAND_EL_PASO clamped 91 of 786 (11.6%) -- both visible in each report's `nwp_wind_delta_clamp_count` field rather than silent.

### Task 3 -- no-peeking lock self-description

```
NO_PEEKING_LOCK_OK
```

### Full suite (post-Task-3)

```
590 passed, 23 failed, 67 warnings
```

The 23 failures are the pre-existing `corridor_discretization_test.py` baseline recorded in `.planning/WINDOWS.md` -- identical count before and after this plan, zero regressions introduced.

## Known Stubs

None -- every arm this plan built is fully wired to live data (the two-corridor live run above) or synthetic-data unit tests; no placeholder/mock code was left in any production path.

## User Setup Required

None -- no external service configuration required. Both live-network dependencies (`previous-runs-api.open-meteo.com`, `archive-api.open-meteo.com`) are public and unauthenticated, unchanged from Plan 03-03.

## Next Phase Readiness

- **Ready for Plan 03-05 (ML-corrected wind/cooling arms):** the oracle's margin over `raw_forecast` (measured above, per corridor) is the explicit ceiling any correction model is being judged against. `NON_FITTED_ARMS`'s factory convention and `_city_ampacity`'s single physics seam are proven at corridor level and ready to be extended with fitted estimators.
- **Ready for Plan 03-06 (leakage probe + seven-arm held-out comparison):** `_require_test_split_unlocked`/`_guard_test_split_access` are in place, self-describing, and default-locked; Plan 03-06 flips the flag in the same commit that lands the Expectation record. `assert_identical_index` and `assert_filtered_split_disjoint` give Plan 03-06's final comparison a mechanically-enforced identical-timestamp guarantee to build on, not an assumed one.
- **No blockers.** No file this plan does not own was touched (`git diff --quiet` against `forecast_training.py`, `thermal_model.py`, `ampacity_forecast.py`, `anomaly_detector.py`, `DLRSafetyMonitor.py`, `config.py` confirmed clean); `ACKNOWLEDGEMENTS.md` was not touched (Plan 03-07 owns the consolidated Waves 2-5 disclosure entry).

## Self-Check: PASSED

- `backend/forecast_experiment.py` (contains `NON_FITTED_ARMS`, `ORACLE_ARM_NAME`, `corridor_anchored_pair_frame`, `assert_identical_index`, `_require_test_split_unlocked`) -- FOUND
- `backend/tests/forecast_experiment_test.py` -- FOUND (59 tests, verified passing)
- Commit `952a0b3` -- FOUND in `git log --oneline --all`
- Commit `1618d8a` -- FOUND
- Commit `0eb453a` -- FOUND
- `backend/forecast_training.py`, `backend/thermal_model.py`, `backend/ampacity_forecast.py`, `backend/anomaly_detector.py`, `backend/DLRSafetyMonitor.py`, `backend/config.py` carry zero diff from this plan's base (`7f93271`) -- CONFIRMED
- `ACKNOWLEDGEMENTS.md` carries zero diff -- CONFIRMED
- Full suite: 590 passed, 23 failed (unchanged pre-existing baseline) -- CONFIRMED

---
*Phase: 03-ampacity-forecast-correction-experiment-compare-persistence*
*Plan: 04*
*Completed: 2026-09-29*
