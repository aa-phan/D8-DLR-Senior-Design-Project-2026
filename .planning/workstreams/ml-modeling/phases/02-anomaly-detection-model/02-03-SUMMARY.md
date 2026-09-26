---
phase: 02-anomaly-detection-model
plan: 03
subsystem: ml-anomaly-detection
tags: [gridstatus, ercot, load-characterization, pearson-correlation, anomaly-detection]

# Dependency graph
requires:
  - phase: 02-anomaly-detection-model
    provides: "Plan 02-01/02-02's corridor_observation_frame/build_feature_matrix, AnomalyDetector.check's model branch, and the persisted per-corridor observation CSVs"
provides:
  - "ercot_data_retriever.pull_ercot_data: additive return value, explicit zone_substrings selection, per-calendar-year download loop, frame .attrs exposing the resolved column name and matched zone columns"
  - "config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CORRIDOR/ANOMALY_ML_LOAD_YEARS/ANOMALY_ML_LOAD_REPORT_NAME"
  - "anomaly_training.characterize_load and the --characterize-load CLI entry point"
  - "data/models/anomaly_load_characterization.json -- real, executed per-corridor load-vs-weather evidence"
  - "D-02 boundary test proving load stays training-time-only and never reaches check()"
affects: [02-04-validation-record]

# Actuals (#2632)
actuals:
  tokens: 12750
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-calendar-year download loop working around a third-party client's single-year-only date-range behavior (mirrors forecast_training.fetch_city_weather's own per-year Open-Meteo loop)"
    - "Frame .attrs used to hand a caller resolved metadata (matched zone columns, output column name) without forcing it to re-derive or guess selection logic"
    - "Training-time-only characterization: only the network pull is wrapped in a failure path, never the whole function, so a network hiccup degrades to recorded unavailability rather than blocking the phase"

key-files:
  created:
    - backend/tests/ercot_data_retriever_test.py
  modified:
    - backend/config.py
    - backend/ercot_data_retriever.py
    - backend/anomaly_training.py
    - backend/tests/anomaly_training_test.py

key-decisions:
  - "The load-characterization report's per-zone-columns key is named zone_columns (matching the plan's literal verify script), distinct from the internal frame-attribute name zone_columns_matched"
  - "characterize_load always resolves years from config.ANOMALY_ML_LOAD_YEARS regardless of the shared --years CLI flag (which governs the unrelated weather-training window depth), since the plan's own action text scopes load-window depth to its own dedicated config constant"
  - "The pooled two-cities-per-timestamp weather observation frame is collapsed to one row per timestamp by averaging, strictly for this correlation summary (A-10) -- the fitted feature matrix elsewhere in this codebase still uses each city's own unaveraged reading"

patterns-established:
  - "anomaly_training.py's --characterize-load CLI entry point mirrors --validate/--bakeoff's own shape: per-corridor try-and-continue-on-failure-to-assemble handling is replaced here with per-corridor available/unavailable recording, since D-02 scopes this pull as non-blocking rather than phase-failing"

requirements-completed: [ANOM-01]

coverage:
  - id: D1
    description: "ercot_data_retriever.pull_ercot_data becomes usable in process: returns its assembled frame, accepts an explicit per-corridor zone_substrings selection, and assembles a multi-year window one calendar year per download, with today's call signature and output preserved exactly"
    requirement: ANOM-01
    verification:
      - kind: unit
        ref: "backend/tests/ercot_data_retriever_test.py::test_default_call_returns_frame_with_datetime_utc_and_west_column"
        status: pass
      - kind: unit
        ref: "backend/tests/ercot_data_retriever_test.py::test_zone_substrings_south_selects_south_and_south_central_only"
        status: pass
      - kind: unit
        ref: "backend/tests/ercot_data_retriever_test.py::test_span_crossing_year_boundary_issues_one_call_per_spanned_year"
        status: pass
      - kind: unit
        ref: "backend/tests/ercot_data_retriever_test.py::test_every_corridor_has_an_explicit_zone_substring_selection"
        status: pass
    human_judgment: false
  - id: D2
    description: "ANOM-01's load baseline is discharged with real, executed evidence: per-corridor ERCOT zone load pulled for the corridor's own region, joined to its weather observations, and correlated against each fitted variable, with the true retrieved window recorded rather than the requested one"
    requirement: ANOM-01
    verification:
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_characterize_load_reports_the_retrieved_window_not_the_requested_one"
        status: pass
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_characterize_load_records_unavailability_without_raising"
        status: pass
      - kind: integration
        ref: ".venv/bin/python3 backend/anomaly_training.py --characterize-load (live gridstatus ERCOT client, both corridors, exit 0)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The D-02 boundary is enforced by a named test asserting all four of its halves together: no source-level import of ercot_data_retriever/gridstatus in anomaly_detector.py, no load name in either config feature tuple, a fresh import leaves gridstatus out of sys.modules, and check() still succeeds on a raw_data carrying exactly wind/temp/solar"
    requirement: ANOM-01
    verification:
      - kind: unit
        ref: "backend/tests/anomaly_training_test.py::test_load_is_training_time_only_and_never_reaches_check"
        status: pass
    human_judgment: false

# Metrics
duration: 23min
completed: 2026-09-26
status: complete
---

# Phase 2 Plan 03: D-02 ERCOT Load Characterization Summary

**Real, executed per-corridor ERCOT load pulled from each corridor's own weather zone (South/South Central for Austin-Corpus Christi, Far West/West for Midland-El Paso), joined to that corridor's pooled weather observations, and correlated against wind/temp/solar -- discharging ANOM-01's load baseline at training time only, with a named test proving it never reaches the live `check()` path.**

## Performance

- **Duration:** ~23 min
- **Started:** 2026-09-26T22:50:00Z (approx.)
- **Completed:** 2026-09-26T23:13:00Z (approx.)
- **Tasks:** 2 completed
- **Files modified:** 6 (1 new, 5 modified)

## Accomplishments

- `ercot_data_retriever.pull_ercot_data` is now usable in process: returns its assembled frame (previously `None`), accepts an explicit `zone_substrings` selection (default `("WEST",)`, reproducing today's filter exactly for an unchanged call), assembles a multi-year window with one download call per calendar year (working around the installed `gridstatus` client's single-year-only post-settlements load download), sorts and deduplicates the concatenation, and exposes the resolved output column name plus the real matched zone columns via frame `.attrs` so a caller never has to guess either.
- `config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CORRIDOR` maps `AUSTIN_CORPUS_CHRISTI` to `("SOUTH",)` and `MIDLAND_EL_PASO` to `("WEST",)` -- a test asserts every corridor in `config.CORRIDOR_ENDPOINTS` has an explicit entry and the two selections differ, so neither corridor can silently fall back to the wrong region's load.
- `anomaly_training.characterize_load(corridor, years=None)` pulls the corridor's own zone load for `config.ANOMALY_ML_LOAD_YEARS` complete calendar years (matching `forecast_training.fetch_city_weather`'s "never the current in-progress year" rule), joins it to the corridor's pooled weather observation frame (collapsed to one row per timestamp by averaging across the two endpoint cities, strictly for this correlation summary), and reports the Pearson correlation against each of `config.ANOMALY_ML_FEATURE_COLUMNS`. The reported window/row counts always come from the frame that actually came back, never the requested range. Only the load pull itself is wrapped in a failure path -- a network hiccup records `available: False` plus the exception text and the run still exits 0, never blocking the phase.
- `--characterize-load` writes `data/models/anomaly_load_characterization.json`, one entry per corridor, exiting 0 regardless of ERCOT reachability.
- **Live, honest evidence from the real ERCOT archive:** `AUSTIN_CORPUS_CHRISTI` matched `['South', 'South Central']` and `MIDLAND_EL_PASO` matched `['Far West', 'West']` -- two genuinely different ERCOT regions, proving the zone-aware selection actually fires rather than reusing one filter for both corridors. Both corridors retrieved 8,731 hourly load rows for 2025, joined against that corridor's own 2025 pooled weather observations with a full 8,731-row inner-join match. Correlations against `air_temp`/`solar_radiation` were moderate and positive (~0.47-0.51, physically sensible -- hotter/sunnier conditions drive higher grid load) while `wind_speed`'s correlation was much weaker (0.14 and -0.11 respectively) -- reported plainly per D-07's honesty precedent, neither smoothed nor over-interpreted (a weak linear correlation is evidence of a weak *linear* association only, per A-09).
- `test_load_is_training_time_only_and_never_reaches_check` asserts all four D-02 boundary halves together in one test: `anomaly_detector.py`'s own file source contains no import of `ercot_data_retriever` or `gridstatus`; no name in `config.ANOMALY_ML_FEATURE_COLUMNS`/`config.ANOMALY_ML_RAW_DATA_KEYS` contains "load"; freshly re-importing `anomaly_detector` after evicting `gridstatus` from `sys.modules` leaves it absent (immune to `ercot_data_retriever_test.py`'s own module-level `gridstatus` import polluting the shared test session); and a fitted three-feature model still returns a normal `(bool, str)` for a `raw_data` carrying exactly `wind`/`temp`/`solar`.
- Full test suite: 467 passed (up from the 451-test pre-phase baseline), 0 failed. `backend/anomaly_detector.py` carries zero diff. `git status --porcelain data/models` stays empty.

## Task Commits

Each task was committed atomically:

1. **Task 1: Make the ERCOT load retriever usable in process** - `aa241f4` (feat)
2. **Task 2: Run the D-02 load characterization and install the boundary guard** - `ed28241` (feat)

**Plan metadata:** committed alongside this SUMMARY (see final commit below).

_Note: Both tasks (`tdd="true"`) wrote their named invariant test suites alongside the implementation and ran them together; no separate RED-then-GREEN commit split applied, mirroring Plans 02-01/02-02's own documented precedent for this pattern._

## Files Created/Modified

- `backend/config.py` - New `ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CORRIDOR`/`ANOMALY_ML_LOAD_YEARS`/`ANOMALY_ML_LOAD_REPORT_NAME` constants
- `backend/ercot_data_retriever.py` - `pull_ercot_data` gains `zone_substrings`/`save` parameters, a per-calendar-year download loop, a selection-derived output column name, a return value, and two new frame `.attrs`
- `backend/anomaly_training.py` - `characterize_load`, `_run_characterize_load`, `--characterize-load` CLI flag; imports `ercot_data_retriever` at module scope (legal here, forbidden in `anomaly_detector.py`)
- `backend/tests/ercot_data_retriever_test.py` (new) - 13 offline tests covering the additive return value, zone selection, per-calendar-year loop, sort/dedup, frame `.attrs`, and corridor coverage
- `backend/tests/anomaly_training_test.py` - 3 new tests: the D-02 four-halves boundary guard, window-reflects-what-came-back, and unavailability-without-raising

## Decisions Made

- Renamed the load-characterization report's per-zone-columns key to `zone_columns` (matching the plan's literal verify script) rather than the internal frame-attribute name `zone_columns_matched` this implementation also uses -- the public report shape and the internal metadata-carrying mechanism are deliberately named differently.
- `characterize_load` always resolves its window depth from `config.ANOMALY_ML_LOAD_YEARS`, ignoring the shared `--years` CLI flag (which governs the separate weather-training window depth for `--validate`/`--bakeoff`/the plain training loop) -- the plan's action text scopes load-window depth to its own dedicated config constant, and conflating the two would have silently deepened the load window to 3 years by default instead of the intended 1.
- The pooled two-cities-per-timestamp weather observation frame is collapsed to one row per timestamp by averaging, strictly for this correlation summary (A-10) -- the fitted feature matrix everywhere else in this codebase still uses each city's own unaveraged reading, so this averaging never touches what the model actually learns.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 2's verify script expects the report key `zone_columns`, not `zone_columns_matched`**
- **Found during:** Task 2, live `--characterize-load` verification
- **Issue:** An earlier implementation pass named the load-characterization report's per-zone-columns field `zone_columns_matched` (matching the internal frame `.attrs` name carrying the same information out of `pull_ercot_data`). The plan's own literal Task 2 verify script checks for the key `zone_columns`, so the live verify command failed with `an available entry hides its retrieved window or row counts`.
- **Fix:** Renamed the PUBLIC report/return-mapping key to `zone_columns` to match the plan's literal verify script exactly, while keeping the internal frame-attribute name (`zone_columns_matched`) unchanged as an implementation detail.
- **Files modified:** `backend/anomaly_training.py`, `backend/tests/anomaly_training_test.py`
- **Verification:** Re-ran the plan's exact `LOAD_CHAR_OK` verify command against the live-generated report -- passed.
- **Committed in:** `ed28241` (Task 2 commit)

**2. [Rule 3 - Blocking] Honest zone-column reporting required a small additive extension to `pull_ercot_data`, outside Task 2's own `<files>` list**
- **Found during:** Task 2, designing `characterize_load`
- **Issue:** "The zone column names actually matched" cannot be honestly recomputed by the caller from `zone_substrings` alone, since that cannot distinguish the no-match-fallback case (where the function falls back to the total `ERCOT` column but the caller's own substring guess would still claim a match). Task 2's `<files>` element lists only `backend/anomaly_training.py`/`backend/tests/anomaly_training_test.py`, not `backend/ercot_data_retriever.py`.
- **Fix:** Added two additive frame `.attrs` entries (`load_column`, `zone_columns_matched`) to `pull_ercot_data`'s return value -- a strictly additive, backward-compatible metadata addition, covered by Task 1's own test file, and consistent with the plan's top-level `files_modified` frontmatter for the whole plan (which already lists `backend/ercot_data_retriever.py`).
- **Files modified:** `backend/ercot_data_retriever.py`, `backend/tests/ercot_data_retriever_test.py`
- **Verification:** New tests `test_frame_attrs_expose_load_column_and_matched_zones`/`test_frame_attrs_record_empty_matched_zones_on_fallback` pass; full suite green.
- **Committed in:** `aa241f4` (Task 1 commit, since the extension lives in Task 1's file)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking, no production-path scope creep -- both are corrections needed for Task 2's own required output to be honest and to match the plan's literal verify script).
**Impact on plan:** Zero impact on scope or correctness. Both were necessary for Task 2's stated deliverable (a report a human/downstream plan can trust) to actually hold.

## Issues Encountered

None beyond the two deviations above. One notable non-issue worth recording: while reading `02-RESEARCH.md`'s Pitfall 2, independently re-derived the installed `gridstatus` client's actual chunking behavior by reading `.venv/lib/python3.12/site-packages/gridstatus/decorators.py` directly. The `@support_date_range(frequency="YEAR_START")` decorator wrapping `get_hourly_load_post_settlements` DOES perform its own year-boundary chunking when both `date` and `end` are supplied to the underlying client call -- a subtlety 02-RESEARCH.md's summary of the undecorated function body alone did not capture. This does not change what this plan needed to build: `pull_ercot_data`'s own explicit per-calendar-year loop (Task 1's required design) is independently correct regardless, since each of its per-year calls falls entirely within one calendar year and therefore triggers no further chunking inside the decorator either way. Recorded here for Plan 02-04's awareness, not as a defect.

## User Setup Required

None - no external service configuration required. `gridstatus` is a pre-existing, already-installed dependency (per this plan's own T-02-SC threat-register entry); this plan installs nothing new.

## Next Phase Readiness

- Plan 02-04 (validation record, C10 spec correction) can transcribe `data/models/anomaly_load_characterization.json`'s numbers directly: both corridors' matched zones, true retrieved window, row counts, joined row count, and per-variable Pearson correlations are all present and machine-readable, plus the honest note that a weak linear correlation is not evidence load is irrelevant (A-09).
- No blockers. ANOM-01's load baseline is discharged with real, executed evidence at training time only, and the D-02 boundary keeping it out of `check()` is locked by a named test.

---
*Phase: 02-anomaly-detection-model*
*Completed: 2026-09-26*

## Self-Check: PASSED

All created/modified files confirmed present on disk (`backend/config.py`, `backend/ercot_data_retriever.py`, `backend/anomaly_training.py`, `backend/tests/ercot_data_retriever_test.py`, `backend/tests/anomaly_training_test.py`, `ACKNOWLEDGEMENTS.md`, this SUMMARY.md). Both task commit hashes (`aa241f4`, `ed28241`) confirmed present in `git log --oneline --all`. Full test suite: 467 passed, 0 failed. `data/models/anomaly_load_characterization.json` confirmed present with real, distinct per-corridor zone matches.
