---
phase: 03-ampacity-forecast-correction-experiment-compare-persistence
plan: 01
subsystem: ml-modeling
tags: [open-meteo, forecast-archive, calibration-gate, ecmwf_ifs, requests]

# Dependency graph
requires: []
provides:
  - "backend/open_meteo_forecast_provider.py: bulk Historical Forecast + Single-Runs fetch adapters, pinned to models=ecmwf_ifs, importing the Archive adapter's mapping/units tables by identity"
  - "backend/forecast_leadtime_calibration.py: the D-01 hard gate (measure_lead_alignment / assert_supports_horizon), unit-tested in both directions"
  - "backend/experiment_splits.py: calendar_split, a three-way calendar train/val/test splitter generalizing anomaly_training.chronological_split (written, tested, NOT wired into a completed experiment run -- see Known Stubs / Issues)"
  - "backend/forecast_experiment.py: the anchored-pair-frame assembly and arm-scoring machinery (written, tested against synthetic data, NOT run against the real archive -- see Known Stubs / Issues)"
  - "A measured, load-bearing finding: the bulk/single-run bit-identical lead rule does NOT hold across this phase's intended 2023-2025 experiment window -- only for very recent months relative to 'now'"
affects: [03-02, 03-03, 03-04, 03-05, 03-06, 03-07]

# Actuals (#2632)
actuals:
  tokens: 92000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Forecast-archive provider adapter as a fifth sibling in the provider-adapter tier, importing shared mapping tables by identity from the Archive adapter"
    - "Null-completeness gate ahead of range-check, since range-check drops nulls before comparing"
    - "Archive-boundary vs. malformed-request 400 distinction (SingleRunUnavailable vs. propagated HTTPError), extended to a fully-null HTTP 200 boundary case discovered live"

key-files:
  created:
    - backend/open_meteo_forecast_provider.py
    - backend/forecast_leadtime_calibration.py
    - backend/experiment_splits.py
    - backend/forecast_experiment.py
    - backend/tests/open_meteo_forecast_provider_test.py
    - backend/tests/forecast_leadtime_calibration_test.py
    - backend/tests/experiment_splits_test.py
    - backend/tests/forecast_experiment_test.py
    - .planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/deferred-items.md
  modified:
    - backend/config.py
    - .gitignore

key-decisions:
  - "HALTED at the Task 2/3 boundary checkpoint: the live 30-day, 4-city calibration run measured a fifth-percentile lead of 0h on the unfiltered series (expected, correct) AND ALSO failed the filtered (hour%6==1) gate -- the plan expected the filtered gate to PASS. Root-caused via direct diagnostic (not a code bug): match rate between the bulk product and exact single runs is ~100% for dates within the last few months relative to 'now' (2026-09-29) but degrades to 0% for dates in 2024 -- squarely inside this phase's intended 2023-2025 primary window. RESEARCH.md's live probe only tested three very-recent 2026 dates, which is why it did not surface this."
  - "Did not proceed to Task 3 (precondition explicitly requires the calibration checkpoint's approval). Task 3's code (experiment_splits.py, forecast_experiment.py, and both test files) was drafted and is fully passing against synthetic/mocked data, but is uncommitted -- left in the worktree for inspection, not committed as done work, per the executor's precondition-unmet protocol."
  - "Two genuine bugs/gaps were found and fixed (committed) independently of the design-premise question: (1) fetch_single_run's full 168-hour response null-pads past a variable's real forecast depth even for in-archive-depth runs -- now scoped to only the needed variable plus an optional forecast_days truncation; (2) a well-formed, in-range run can return HTTP 200 with EVERY requested variable's array fully null (an archive gap Open-Meteo does not surface as the documented 'not available' 400) -- now detected and raised as SingleRunUnavailable, same as the 400 path."
  - "Added /data/experiment/ to .gitignore -- config.py already documented FORECAST_EXPERIMENT_CACHE_DIR as git-ignored generated data, but the .gitignore entry itself was missing."

patterns-established:
  - "A live calibration/verification checkpoint that fails is a valid, protocol-anticipated outcome -- not an executor error -- and halts the plan at that gate rather than being silently worked around."

requirements-completed: []  # D-01/D-02 are NOT complete -- the calibration gate itself is built and tested, but the live measurement it exists to make invalidates the phase's current window assumption. See Deviations/Issues.

coverage:
  - id: D1
    description: "A real, null-free, schema-validated NWP forecast frame is fetched from a pinned-model bulk request (fetch_historical_forecast)"
    requirement: D-01
    verification:
      - kind: unit
        ref: "backend/tests/open_meteo_forecast_provider_test.py (20 tests)"
        status: pass
      - kind: integration
        ref: "live fetch_historical_forecast(AUSTIN, 2025-07-01, 2025-07-01) -- 24 rows, zero nulls"
        status: pass
    human_judgment: false
  - id: D2
    description: "Single-Runs fetch with strict run-timestamp formatting and the archive-boundary/malformed-request 400 distinction, extended to a fully-null-200 boundary case discovered live"
    requirement: D-01
    verification:
      - kind: unit
        ref: "backend/tests/open_meteo_forecast_provider_test.py (12 additional tests covering run formatting, both boundary conditions, partial-null-still-raises)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The lead-time calibration gate correctly verifies a deterministic rule (fails unfiltered, passes filtered) against MOCKED data in both directions"
    requirement: D-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast_leadtime_calibration_test.py (8 tests, both gate directions + unhealthy-lead detection)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The lead-time calibration gate's LIVE measurement against the real archive over the phase's intended 2023-2025 window confirms the deterministic bit-identical rule"
    requirement: D-01
    verification: []
    human_judgment: true
    rationale: "This is the load-bearing finding that did NOT hold: the live 30-day/4-city run measured near-0% match rate for dates in 2024-2025 against exact single runs, contradicting the plan's expectation that the filtered (hour%6==1) gate would pass. A human/design decision is required before this requirement can be marked complete -- see Deviations and CHECKPOINT report."
  - id: D5
    description: "A three-way calendar splitter and the anchored-pair-frame/arm-scoring harness (Task 3)"
    requirement: D-02
    verification: []
    human_judgment: true
    rationale: "Task 3 was drafted and its own unit tests pass against synthetic data, but it was never run against the real archive and its precondition (checkpoint approval) was not met -- not committed. Coverage cannot be claimed until the design question above is resolved and Task 3 is formally executed."

duration: 88min
completed: 2026-09-29
status: halted
---

# Phase 3 Plan 01: Forecast-Archive Provider + Calibration Gate (HALTED before Task 3)

**Provider adapter and calibration gate built and fully tested; the gate's live measurement against the real archive contradicts the plan's design premise for the 2023-2025 window, so the plan halts before scoring any arm.**

## Performance

- **Duration:** 88 min
- **Started:** 2026-09-29T18:46:00Z
- **Completed:** 2026-09-29T19:14:35Z
- **Tasks:** 2 of 3 completed and committed (Task 3 drafted but not committed; checkpoint task's precondition for Task 3 was not satisfied)
- **Files modified:** 6 committed (2 new modules, 2 new test files, config.py, .gitignore) + 4 uncommitted Task 3 files

## Accomplishments

- `open_meteo_forecast_provider.py`: real, null-free, schema-validated bulk forecast fetch pinned to `ecmwf_ifs`, plus a Single-Runs fetch with strict run-timestamp formatting and an archive-boundary/malformed-request HTTP 400 distinction -- extended live to also catch a fully-null HTTP 200 archive gap.
- `forecast_leadtime_calibration.py`: the D-01 hard gate, correctly implementing and unit-testing both directions of `assert_supports_horizon` (fails unfiltered, passes on the exact-lead subset against mocked data) and `measure_lead_alignment`'s boundary-skip counting.
- Two genuine live bugs found and fixed during the checkpoint's real-network run (see Deviations).
- **The load-bearing negative result**: ran the live 30-day, 4-city calibration three times (fixing two real bugs between runs) and confirmed a genuine measured finding, not a code defect -- the bulk product is bit-identical to the exact single run only for dates within roughly the last few months relative to "now," and diverges substantially (differences of 0.1-1.6 m/s on wind_speed, every hour) for dates in 2024, which is squarely inside this phase's intended 2023-2025 primary experiment window.

## Task Commits

Each task was committed atomically:

1. **Task 1: The forecast-archive provider** - `1c60934` (feat)
2. **Task 2: The hard gate** - `1a43c84` (feat)
3. **Checkpoint live-run bug fixes** - `fcaf180` (fix)
4. **`.gitignore` fix for generated experiment cache** - `5c98e05` (fix)

**Task 3 was NOT executed** (precondition unmet -- see below). No commit for Task 3's code.

_Note: this plan is `type: execute`, not `type: tdd`; commits above are feat/fix, not RED/GREEN/REFACTOR._

## Files Created/Modified

- `backend/open_meteo_forecast_provider.py` - bulk + single-run forecast-archive fetch adapters, pinned to `ecmwf_ifs`
- `backend/forecast_leadtime_calibration.py` - the D-01 hard gate
- `backend/tests/open_meteo_forecast_provider_test.py` - 32 tests (network-free)
- `backend/tests/forecast_leadtime_calibration_test.py` - 8 tests (network-free)
- `backend/config.py` - new `FORECAST_EXPERIMENT_*` config block
- `.gitignore` - added `/data/experiment/`
- `backend/experiment_splits.py` (uncommitted) - `calendar_split`/`SplitBoundaries`, tested, agrees with `anomaly_training.chronological_split`
- `backend/forecast_experiment.py` (uncommitted) - anchored-pair-frame assembly, `score_arms`, persistence/raw-forecast arms, tested against synthetic/mocked data only
- `backend/tests/experiment_splits_test.py` (uncommitted) - 6 tests
- `backend/tests/forecast_experiment_test.py` (uncommitted) - 17 tests, including the persistence-vs-`backtest_residuals` agreement regression (passes against synthetic data)
- `.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/deferred-items.md` - logs a pre-existing, out-of-scope `corridor_discretization_test.py` failure (23 tests) discovered during full-suite verification, unrelated to this plan's files

## Decisions Made

- Halted at the checkpoint rather than proceeding to Task 3, per the plan's own explicit resume-signal instructions ("if check 1 or check 3 fails... the fallback is CONTEXT.md's option (a)... needs a design conversation rather than an executor decision").
- Left Task 3's code uncommitted rather than deleted -- it is fully written and unit-tested against synthetic data, and may be reusable once the window/data-source question is resolved (whichever of CONTEXT.md's options (a)/(b)/(c) is chosen), but committing it as "done" would misrepresent an unmet precondition.
- Root-caused the calibration failure via direct diagnostic queries against the live API (comparing bulk vs. single-run values hour-by-hour across a spread of dates from 2024 through 2026) before concluding this was a genuine measured finding rather than a bug in the calibration code -- confirmed the exact same-date comparison RESEARCH.md used (2026-09-20) reproduces its 100%-match finding perfectly, ruling out a code defect and isolating the variable to date age.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `fetch_single_run` requested unnecessary variables and could not truncate response length**
- **Found during:** Task 2's live checkpoint run (first live attempt, crashed)
- **Issue:** A single run's fixed-length 168-hour response array is null-padded past a given variable's real forecast depth even for a run well within the archive's nominal window -- live-observed 23/168 null on `temperature_2m`, and separately on `wind_speed_10m`, for run `2024-08-20T06:00`. The calibration gate requested all 5 pipeline variables and the full response length, tripping the null-completeness gate on tail data it never used.
- **Fix:** `measure_lead_alignment` now requests only `wind_speed_10m` (the variable RESEARCH.md specifies) and passes a new `forecast_days=1` truncation parameter to `fetch_single_run`.
- **Files modified:** `backend/open_meteo_forecast_provider.py`, `backend/forecast_leadtime_calibration.py`, `backend/tests/open_meteo_forecast_provider_test.py`
- **Verification:** Live re-run progressed past this failure; unit tests for the new `forecast_days` param pass.
- **Committed in:** `fcaf180`

**2. [Rule 1/2 - Bug/missing handling] A well-formed run can return HTTP 200 with every variable fully null**
- **Found during:** Task 2's live checkpoint run (second live attempt, crashed)
- **Issue:** Open-Meteo's documented archive-boundary signal is an HTTP 400 naming an unavailable model run, but live-observed run `2025-08-07T06:00` returned HTTP 200 with `wind_speed_10m` 24/24 null -- an archive gap surfaced differently than documented.
- **Fix:** `fetch_single_run` now checks, before the completeness gate, whether EVERY requested variable's entire array is null; if so it raises `SingleRunUnavailable` (the same exception the 400 path raises), so the calibration gate counts and continues past it exactly as it does the documented case. A partial null (some but not all variables/rows) is unaffected and still raises `ValueError` via `_completeness_check`.
- **Files modified:** `backend/open_meteo_forecast_provider.py`, `backend/tests/open_meteo_forecast_provider_test.py`
- **Verification:** Live re-run (third attempt) completed successfully end-to-end for all four cities; two new unit tests (fully-null-200 raises `SingleRunUnavailable`, partial-null-200 still raises `ValueError`) pass.
- **Committed in:** `fcaf180`

**3. [Rule 2 - Missing critical] `/data/experiment/` was undocumented-but-missing from `.gitignore`**
- **Found during:** Post-live-run `git status` check
- **Issue:** `config.py`'s own comment documents `FORECAST_EXPERIMENT_CACHE_DIR` as "git-ignored generated data," mirroring `/data/models/`'s existing pattern, but the `.gitignore` entry itself was never added -- the live calibration run's JSON report would have been an untracked file eligible for accidental commit.
- **Fix:** Added `/data/experiment/` to `.gitignore` alongside the existing `/data/historical/` and `/data/models/` entries.
- **Files modified:** `.gitignore`
- **Verification:** `git check-ignore -v data/experiment/leadtime_calibration_report.json` confirms the new rule matches.
- **Committed in:** `5c98e05`

---

**Total deviations:** 3 auto-fixed (2 bugs found during live verification, 1 missing-critical gitignore gap). **Impact:** All three were necessary to complete Task 2's own live checkpoint honestly; none touched Task 1/2's tested logic paths, and the full unit suite (minus the pre-existing, unrelated `corridor_discretization_test.py` failures logged in `deferred-items.md`) stayed green throughout.

## Issues Encountered

**The calibration gate's live measurement contradicts the plan's expectation, and this is the primary finding of this session.**

Ran `.venv/bin/python3 backend/forecast_leadtime_calibration.py --days 30` against the real Open-Meteo archive for all four cities (Austin, Corpus Christi, El Paso, Midland). Full output transcribed below (Austin's block; all four cities showed the same pattern).

```
AUSTIN: sampling 30 days...
  lead_h   matched  compared  match_rate       mad
       0        42       106      39.62%    0.3422
       1        61       106      57.55%    0.2942
       2        62       106      58.49%    0.1999
       3        61       106      57.55%    0.2411
       4        64       106      60.38%    0.2393
       5        63       106      59.43%    0.2497
       6        21        82      25.61%    0.4123
       7        19        82      23.17%    0.3729
       8        22        82      26.83%    0.3568
       9        20        82      24.39%    0.3689
      10        19        82      23.17%    0.3956
      11        21        82      25.61%    0.3707
      ... (leads 12-23 similarly low or zero)
boundary_skips: 14
unfiltered gate: FAIL
  forecast_leadtime_calibration: the measured alignment does not exhibit the deterministic
  rule at: lead 0 (match rate 39.62%), lead 1 (match rate 57.55%), lead 2 (match rate
  58.49%), lead 3 (match rate 57.55%), lead 4 (match rate 60.38%), lead 5 (match rate
  59.43%). A gate that passes on data the rule does not hold for is worse than no gate --
  investigate the alignment before proceeding.
filtered gate (hour % 6 == 1): FAIL
  (same message -- the unhealthy-lead check fires before the hour_filter is even applied,
  correctly, since leads 0-5 do not meet the match-rate floor regardless of which hours
  are selected)
```

Corpus Christi, El Paso, and Midland all showed the same shape: leads 0-5 at 40-60% match rate (not the ~100% RESEARCH.md measured), a soft decline rather than a clean cutoff at lead 6, and 14/120 boundary skips per city.

**Root cause, confirmed by direct diagnostic (not a code defect):**

1. Re-ran the exact same-date, same-city comparison RESEARCH.md used (`AUSTIN`, `2026-09-20`) directly against the live API using this plan's own `fetch_historical_forecast`/`fetch_single_run` functions -- reproduced RESEARCH.md's finding EXACTLY: 100% match at leads 0-5 for all four run hours (00Z/06Z/12Z/18Z), clean divergence at lead 6+. This rules out a bug in the calibration/provider code.
2. Swept match rate across dates from 2024-03-20 through 2026-09-27 (same city, same method): 2026 dates (within the last several months of "now") matched 5/6 or 6/6; 2025 dates matched 5/6; **2024 dates matched 0/6**.
3. Inspected 2024-06-15 hour-by-hour: every single hour differs between the bulk product and the exact single run (differences of 0.1-1.57 m/s on wind_speed) -- not a boundary artifact, a genuinely different dataset for that period.

**Conclusion:** RESEARCH.md's live probe (three dates, all in 2026, all very recent relative to "now") correctly measured the rule for recent data, but did not test dates from earlier in the archive. The rule does NOT generalize to this phase's intended primary window (`config.FORECAST_EXPERIMENT_WINDOW_START = "2023-01-01"` through `"2025-12-31"`), which is predominantly OLDER than the regime where the bit-identical relationship holds. This invalidates the phase's design premise as currently scoped and requires a design decision before Task 3 (or any arm-scoring) proceeds -- see CHECKPOINT report returned alongside this summary for the three CONTEXT.md-scoped fallback options.

**Per the checkpoint task's own instructions, this plan halts here rather than proceeding to Task 3.**

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**NOT ready for Plan 03-02 or later plans to build on this plan's arm-scoring output** -- there is none; Task 3 did not run. Plans 03-02 through 03-07 should be re-evaluated once the design decision below is made, since several (03-06 in particular, "Plan 03-06 re-scores every arm on the subset at or after [the verified window]") may need to shift their own window assumptions too.

**Ready:** `open_meteo_forecast_provider.py` and `forecast_leadtime_calibration.py` are solid, real, tested infrastructure regardless of the outcome -- whichever fallback option is chosen, the fetch/parse/null-handling layer does not need to change.

**Blocker:** A human/design decision is needed among CONTEXT.md's three previously-scoped contingencies (none of which were "the rule holds everywhere," since that was assumed, not verified, until now):
  (a) Anchor pulls via the Single-Runs API directly on a stratified subsample -- exact lead by construction, but shrinks the test set and adds per-run request volume (no batching).
  (b) Relabel the horizon to whatever the bulk product's ACTUAL native lead is for the intended window (would require its own calibration/characterization of what that lead is for 2023-2025 data, since it is evidently not "0-5h bit-identical to floor('6h')" there).
  (c) Narrow the phase's primary window to the region where the rule DOES hold (recent months only) -- shrinks the available training/test data volume substantially and may be too short a window for a meaningful backtest.

---
*Phase: 03-ampacity-forecast-correction-experiment-compare-persistence*
*Plan: 01*
*Completed: 2026-09-29*
*Status: halted -- see Issues Encountered*
