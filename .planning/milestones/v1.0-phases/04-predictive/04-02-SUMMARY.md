---
phase: 04-predictive
plan: 02
subsystem: data-science
tags: [pandas, numpy, forecasting, backtesting, schema-versioning, ewm]

requires:
  - phase: 04-predictive (Plan 04-01)
    provides: "historical_archive.py's locked 11-column ARCHIVE_COLUMNS schema, ampacity_forecast.py's naive-only tracer forecast, and ForecastResult/forecast_ampacity signatures anomaly_detector.py and the G6 gate already build against"
provides:
  - "backend/ampacity_forecast.py — backtest_residuals (expanding-window walk-forward, out-of-sample), _point_forecast (naive/ewm), forecast_ampacity(method=...), forecast_columns(result)"
  - "backend/units_def.py — PIPELINE_SCHEMA_VERSION=2, five additive optional forecast/anomaly columns"
  - "backend/historical_archive.py — read_history(validate=True), shared _validation_row helper"
affects: [04-03-anomaly-wiring]

actuals:
  tokens: 10936
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Expanding-window walk-forward backtest (strict-prefix, never a shuffled split) as the sole source of a confidence band's width — RESEARCH.md's Don't-Hand-Roll time-series split, applied literally"
    - "Additive PIPELINE_SCHEMA versioning: PIPELINE_SCHEMA_VERSION bump + append-only new entries, all required=False, proven by a frozen v1-snapshot regression test rather than trusted by inspection"
    - "One private helper (_validation_row) shared between the write path (append_observation) and the read path (read_history) for a schema-mismatch placeholder, instead of two independently-editable copies of the same workaround"

key-files:
  created:
    - backend/tests/ampacity_forecast_test.py
    - backend/tests/historical_archive_test.py
  modified:
    - backend/ampacity_forecast.py
    - backend/historical_archive.py
    - backend/units_def.py
    - backend/tests/units_def_test.py
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "Worktree was stale (created before Plan 04-01's commits landed on main): verified zero divergence, then `git merge --ff-only fa2d7f3` — non-destructive, matches the established pattern from every prior Phase 3 executor session."
  - "Task 1's forecast_columns function and Task 2's schema-agreement tests were written together with Task 1's other changes (same file), then temporarily removed and re-added in Task 2's commit to keep each task's commit scope limited to its own stated files — same technique the 03-02 executor used for a shared-file split."
  - "backend/tests/units_def_test.py's pre-existing 31-case harness is confirmed (again) to be uncollected by pytest; rather than perpetuating the gap for the new schema-version tests, added 5 real top-level test_* functions after the existing standalone-harness code so this plan's own coverage is actually exercised by `pytest`."

patterns-established:
  - "A confidence band's width comes from one function only (backtest_residuals) and nothing else computes it — the point forecast and the band cannot disagree because both trace to the same walk-forward loop."
  - "Forecast output reaches a pipeline row through exactly one function (forecast_columns); the schema and the mapping are tested against each other, not merely each tested independently."

requirements-completed: [DS-F11]

coverage:
  - id: D1
    description: "backtest_residuals is a true out-of-sample walk-forward backtest: each prediction uses a strict prefix, and a flat series collapses to zero residuals while a trending series' residuals center on the trend step rather than zero"
    requirement: "DS-F11"
    verification:
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_backtest_residuals_all_zero_on_flat_series"
        status: pass
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_backtest_residuals_centered_on_constant_step_for_trend"
        status: pass
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_backtest_residuals_order_dependent_on_reversed_tail"
        status: pass
    human_judgment: false
  - id: D2
    description: "The confidence band widens with residual dispersion: two 672-row synthetic series differing only in noise amplitude (25.0 A vs 200.0 A) produce strictly different band widths (117.67 A vs 941.39 A observed)"
    requirement: "DS-F11"
    verification:
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_band_widens_with_noise"
        status: pass
    human_judgment: false
  - id: D3
    description: "Both Tier-1 methods (naive, ewm) share one signature and return type; an unknown method raises ValueError naming the valid set instead of silently defaulting"
    requirement: "DS-F11"
    verification:
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_ewm_and_naive_agree_on_flat_series"
        status: pass
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_ewm_has_smaller_deviation_from_mean_than_naive_on_noisy_series"
        status: pass
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_forecast_ampacity_unknown_method_raises_value_error_naming_valid_methods"
        status: pass
    human_judgment: false
  - id: D4
    description: "forecast_ampacity returns None below config.FORECAST_MIN_HISTORY_ROWS and a ForecastResult at exactly that floor; every returned number is a native Python float/int and the band always contains the point forecast"
    requirement: "DS-F11"
    verification:
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_forecast_returns_none_below_min_history_rows_and_result_at_exactly_min_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_band_contains_point_forecast_and_types_are_native"
        status: pass
    human_judgment: false
  - id: D5
    description: "PIPELINE_SCHEMA_VERSION is 2; every pre-Phase-4 entry is byte-identical to a frozen snapshot; all five new columns are required=False; forecast_columns' keys are all present in PIPELINE_SCHEMA and round-trip-validate against it"
    requirement: "DS-F11"
    verification:
      - kind: unit
        ref: "backend/tests/units_def_test.py#test_schema_version_bumped_and_v1_columns_are_byte_identical"
        status: pass
      - kind: unit
        ref: "backend/tests/units_def_test.py#test_v2_columns_are_all_optional"
        status: pass
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_forecast_columns_keys_all_exist_in_pipeline_schema"
        status: pass
      - kind: unit
        ref: "backend/tests/ampacity_forecast_test.py#test_forecast_columns_round_trip_validates"
        status: pass
    human_judgment: false
  - id: D6
    description: "read_history drops any archived row failing validate_pipeline_row before it can influence a forecast, logging the drop count once per call (not once per row); validate=False preserves an escape hatch"
    requirement: "DS-F11"
    verification:
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_read_history_drops_row_failing_validation_and_keeps_the_rest"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_read_history_logs_drop_count_once"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_read_history_does_not_log_when_nothing_dropped"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_read_history_validate_false_returns_every_row"
        status: pass
    human_judgment: false
  - id: D7
    description: "build_archive_row's output has exactly ARCHIVE_COLUMNS' keys, carries ARCHIVE_SCHEMA_VERSION, is all-Python-float numerically, validates for both normal and fallback readings, and a dlr_amps value round-trips through append+read at full float precision"
    requirement: "DS-F11"
    verification:
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_build_archive_row_keys_and_schema_version"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_build_archive_row_validates_for_normal_and_fallback_readings"
        status: pass
      - kind: unit
        ref: "backend/tests/historical_archive_test.py#test_append_then_read_round_trips_dlr_amps_at_full_float_precision"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-09-09
status: complete
---

# Phase 4 Plan 2: Real Forecasting Backtest & Schema v2 Summary

**Replaced the tracer's in-sample residual band with a true out-of-sample expanding-window walk-forward backtest, added an EWM forecast method behind the same signature, and published forecast output through `PIPELINE_SCHEMA` v2's five additive optional columns.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-09-09T17:25:18-05:00 (worktree fast-forward merge to pick up Plan 04-01)
- **Completed:** 2026-09-09T17:50:07-05:00
- **Tasks:** 3 (all `type="auto" tdd="true"`, no checkpoints)
- **Files modified:** 7 (2 created, 5 modified, including ACKNOWLEDGEMENTS.md)

## Accomplishments
- Replaced Plan 04-01's in-sample `series.diff()` residual band with `backtest_residuals`, an explicit expanding-window walk-forward loop where each residual is computed from a strict prefix of the series — proven order-dependent (reversing the tail changes the residuals) and proven to widen with noise (117.67 A band at noise=25.0 A vs. 941.39 A band at noise=200.0 A, same 672-row synthetic series otherwise)
- Added `method="ewm"` behind `forecast_ampacity`'s existing signature (`method="naive"` stays the default, every existing argument name/position preserved), with a time-aware half-life when the archive frame carries a usable `datetime_utc` index
- Bumped `units_def.PIPELINE_SCHEMA_VERSION` to 2 and appended five additive, all-optional columns (`forecast_horizon_min`, `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps`, `anomaly_score`) — a frozen v1-snapshot regression test proves every pre-Phase-4 entry is untouched
- Added `ampacity_forecast.forecast_columns(result)` as the one function mapping a `ForecastResult` onto pipeline output, deliberately not importing `units_def` so a dedicated cross-module test (not a shared import) is what proves the two stay in agreement
- Closed the training-side half of the archive-poisoning threat (T-04-07): `read_history(validate=True)` now drops any row failing `validate_pipeline_row` before it can influence a forecast, logging the drop count once per call
- Discovered (again) that `backend/tests/units_def_test.py`'s pre-existing 31-case harness is never collected by `pytest`; added 5 new top-level `test_*` functions so this plan's own schema-version coverage is actually exercised by the real suite, not silently dead code

## Task Commits

Each task was committed atomically:

1. **Task 1: Expanding-window walk-forward backtest + EWM method** — `743c8e2` (feat)
2. **Task 2: Extend PIPELINE_SCHEMA to v2, publish forecast_columns** — `c0a4623` (feat)
3. **Task 3: Validate archived rows before training, cover archive round trip** — `7b393a7` (test)

**Plan metadata / AI-disclosure:** `45b4826` (docs: ACKNOWLEDGEMENTS.md update per ECE 464 policy)

## Files Created/Modified
- `backend/ampacity_forecast.py` - `FORECAST_METHODS`, `_point_forecast`, `backtest_residuals`, `forecast_ampacity(method=...)`, `forecast_columns`
- `backend/units_def.py` - `PIPELINE_SCHEMA_VERSION`, five v2 schema entries
- `backend/historical_archive.py` - `read_history(validate=True)`, `_validation_row` shared helper
- `backend/tests/ampacity_forecast_test.py` - new file, 13 tests (`_synthetic_history` deterministic fixture, backtest behavior, EWM/naive agreement, cold-start floor, band-ordering/type discipline, `forecast_columns` <-> schema agreement)
- `backend/tests/historical_archive_test.py` - new file, 9 tests (validate-before-training drop/log behavior, `build_archive_row` shape/schema-version/float discipline, full-precision round trip)
- `backend/tests/units_def_test.py` - 5 new top-level pytest `test_*` functions (frozen v1 snapshot, v2-columns-optional, pre/post-Phase-4 row validation)
- `ACKNOWLEDGEMENTS.md` - AI-use disclosure for this session (ECE 464 policy)

## Locked Signatures (for downstream consumers)

**`ampacity_forecast.py`:**
```python
FORECAST_METHODS: tuple[str, ...] = ("naive", "ewm")

def forecast_ampacity(history: pd.DataFrame, horizon_min=None, method="naive",
                       quantiles=None, min_rows=None) -> ForecastResult | None

def backtest_residuals(series: pd.Series, method: str, min_train_rows=None,
                        halflife_min=None) -> np.ndarray

def forecast_columns(result) -> dict  # {} when result is None

class ForecastResult:
    # horizon_min, amps, ci_lower_amps, ci_upper_amps (float),
    # n_observations, n_residuals (int), method (str)
```

**`units_def.py`:**
```python
PIPELINE_SCHEMA_VERSION: int = 2

# v2 additions, all required=False:
#   forecast_horizon_min    unit="min"  range=(0.0, 1440.0)
#   forecast_amps           unit="A"    range=(100.0, 4000.0)
#   forecast_ci_lower_amps  unit="A"    range=(0.0, 4000.0)
#   forecast_ci_upper_amps  unit="A"    range=(0.0, 8000.0)
#   anomaly_score           unit="pu"   range=(0.0, 1000.0)
```

**`historical_archive.py`:**
```python
def read_history(path: str = None, corridor: str = None, validate: bool = True) -> pd.DataFrame
```

**Observed band widths (four-week, 672-row hourly synthetic series, `method="naive"`):**
- `noise_amps=25.0`: `amps=1171.76`, band `[1113.78, 1231.45]`, width **117.67 A**, `n_residuals=660`
- `noise_amps=200.0`: `amps=974.12`, band `[510.24, 1451.63]`, width **941.39 A**, `n_residuals=660`

## Decisions Made
- Worktree fast-forward merge (`git merge --ff-only fa2d7f3`) to pick up Plan 04-01's tracer-slice work, which had landed on `main` after this worktree branch was created — non-destructive, zero divergence confirmed first.
- Task 1's `forecast_columns` function (and Task 2's schema-agreement tests) were written alongside Task 1's other changes since they share the same files, then temporarily held aside and re-applied in Task 2's own commit — keeps each task's commit scope limited to what that task's `<files>` list actually names, following the 03-02 executor's established precedent for the same class of shared-file situation.
- Added real top-level `test_*` functions to `units_def_test.py` rather than perpetuating its pre-existing standalone-harness-only convention (confirmed uncollected by `pytest` again this session) — this plan's own new coverage needed to actually run under `pytest -q`.

## Deviations from Plan

None — plan executed exactly as written. The temporary hold-aside-and-reapply technique for `forecast_columns` (noted above) is a commit-scoping mechanic, not a deviation from the plan's specified behavior or architecture.

## Issues Encountered
None beyond the pre-existing worktree staleness (resolved via fast-forward merge, documented above) and the already-known `units_def_test.py` pytest-collection gap (worked around, not a regression introduced by this plan).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 04-03 (C10 anomaly detection + real wiring into `corridor_discretization.rate_corridor`) can build directly against this plan's locked signatures — `forecast_ampacity`'s new `method` keyword and `ForecastResult.n_residuals` are both additive and do not change any existing call site's behavior.
- `anomaly_detector.py`'s existing `AnomalyDetector.check` (Plan 04-01) reads `forecast.amps`/`forecast.ci_lower_amps`/`forecast.ci_upper_amps` — all three attributes are unchanged in name, type and meaning by this plan, so no update is required there.
- Full suite green: 118 passed, 0 failed (up from Plan 04-01's ending baseline of 91). No Tier-2 package (`scikit-learn`/`statsmodels`) installed — `pip freeze` gate confirms this; `sklearn`/`statsmodels` import grep against `ampacity_forecast.py` returns 0.
- `git status --porcelain data/historical` prints nothing — no test wrote to the real archive path.

## Self-Check: PASSED

- FOUND: backend/ampacity_forecast.py
- FOUND: backend/units_def.py
- FOUND: backend/historical_archive.py
- FOUND: backend/tests/ampacity_forecast_test.py
- FOUND: backend/tests/historical_archive_test.py
- FOUND: backend/tests/units_def_test.py
- FOUND commit: 743c8e2 (Task 1)
- FOUND commit: c0a4623 (Task 2)
- FOUND commit: 7b393a7 (Task 3)
- FOUND commit: 45b4826 (ACKNOWLEDGEMENTS.md docs commit)

---
*Phase: 04-predictive*
*Completed: 2026-09-09*
