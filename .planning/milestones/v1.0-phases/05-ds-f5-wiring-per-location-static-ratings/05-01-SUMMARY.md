---
phase: 05-ds-f5-wiring-per-location-static-ratings
plan: 01
subsystem: data-science
tags: [dlr-pipeline, ercot-merger, config, static-rating, pandas, pytest]

# Dependency graph
requires:
  - phase: 03-safety-spatial
    provides: "config.STATIC_RATINGS / config.DEFAULT_STATIC_RATING (per-city rating table, already correctly consumed by corridor_discretization.py)"
provides:
  - "process_dlr_to_hourly(dlr_csv_path, city=None) — per-location static_capacity_mw resolution"
  - "run_pipeline(..., city=None, ...) — per-location dlr_headroom_pct / dlr_uplift_flag resolution"
  - "plot_dlr_summary(df, city=None, ...) — per-location reference-line label/position"
  - "README.md Key Parameters table documents the city parameter"
affects: []

# Actuals (#2632)
actuals:
  tokens: 5546
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Explicit city-key rating resolution with silent .get()-with-default fallback (mirrors corridor_discretization.py's corridor_geometry pattern, minus its KeyError validation, since these two functions don't validate city first)"

key-files:
  created:
    - backend/tests/dlr_pipeline_test.py
  modified:
    - backend/ercot_dlr_merger.py
    - backend/tests/ercot_dlr_merger_test.py
    - backend/dlr_pipeline.py
    - README.md

key-decisions:
  - "D-01/D-02/D-04: city: str = None parameter, resolved via config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING), replacing static_rating on run_pipeline/plot_dlr_summary and added fresh to process_dlr_to_hourly."
  - "D-06/D-07: both files' __main__ blocks wired to city=\"AUSTIN\" (Austin-network TARGET_STATION in the merger, Austin-only DEFAULT_STATION_SOURCE in the pipeline)."
  - "Deviation: fixed profile_missing_data's pre-existing pandas FutureWarning (include_groups=False) because it violated this plan's own must-have that no warning be logged in any of the three wired functions."

patterns-established:
  - "Rating resolution is a one-line, per-call local (`static_rating = config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)`), never a bracket index and never a loop over cities."

requirements-completed: [DS-F5]

coverage:
  - id: D1
    description: "process_dlr_to_hourly(csv, city=\"AUSTIN\") produces static_capacity_mw from Austin's 1900 A rating (1078.5913391433292 MW), not the 900 A default (510.91168696262963 MW); omitted/None/unknown city reproduces pre-phase behavior silently."
    requirement: "DS-F5"
    verification:
      - kind: unit
        ref: "backend/tests/ercot_dlr_merger_test.py#test_city_austin_uses_per_location_static_rating"
        status: pass
      - kind: unit
        ref: "backend/tests/ercot_dlr_merger_test.py#test_omitted_city_preserves_default_static_rating"
        status: pass
      - kind: unit
        ref: "backend/tests/ercot_dlr_merger_test.py#test_unknown_city_falls_back_silently"
        status: pass
    human_judgment: false
  - id: D2
    description: "run_pipeline's dlr_uplift_flag flips from True (fallback rating) to False (Austin rating) for the same synthetic weather — the phase's central DS-F5 observable."
    requirement: "DS-F5"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_pipeline_test.py#test_city_choice_flips_the_uplift_flag"
        status: pass
    human_judgment: false
  - id: D3
    description: "plot_dlr_summary's reference line is labelled \"Static Rating (1900 A)\" for city=\"AUSTIN\" and \"Static Rating (900 A)\" when city is omitted."
    requirement: "DS-F5"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_pipeline_test.py#test_plot_labels_the_resolved_city_rating"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_pipeline_test.py#test_plot_without_city_labels_the_fallback_rating"
        status: pass
    human_judgment: false
  - id: D4
    description: "Both __main__ entry points (ercot_dlr_merger.py, dlr_pipeline.py) pass city=\"AUSTIN\" at their actual execution points; README.md documents the new city parameter and no longer documents static_rating."
    requirement: "DS-F5"
    verification:
      - kind: unit
        ref: "grep -v '^[[:space:]]*#' backend/ercot_dlr_merger.py | grep -cE 'process_dlr_to_hourly\\(DLR_FILE, city=\"AUSTIN\"\\)' => 1"
        status: pass
      - kind: unit
        ref: "grep -v '^[[:space:]]*#' backend/dlr_pipeline.py | grep -cE 'city[[:space:]]*=[[:space:]]*\"AUSTIN\"' => 2"
        status: pass
      - kind: unit
        ref: "grep -c '| \\`city\\` |' README.md => 1; grep -c '| \\`static_rating\\` |' README.md => 0"
        status: pass
    human_judgment: false
  - id: D5
    description: "Real DLR CSV run through process_dlr_to_hourly with city=\"AUSTIN\" reports static_capacity_mw ~1078.6 MW (the one property the plan states no automated test can prove, since it depends on a real, non-fixture input file)."
    verification: []
    human_judgment: true
    rationale: "The referenced input file (outputs/station_data/2025-07-01_2025-07-04_AN489.csv) does not exist in this environment — no prior pipeline run has produced it. Confirmed absent by direct filesystem check. The automated tests above cover the identical resolution logic on synthetic data; this deliverable requires a human to run the pipeline against a real file once one exists, or to accept the synthetic-data coverage as sufficient."

# Metrics
duration: 8min
completed: 2026-09-10
status: complete
---

# Phase 5 Plan 01: DS-F5 Per-Location Static Rating Wiring Summary

**`process_dlr_to_hourly`, `run_pipeline`, and `plot_dlr_summary` now resolve `config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)` instead of unconditionally reading the 900 A default — closing the last open v1.0 milestone requirement (DS-F5).**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-09-10T04:46:00Z (approx.)
- **Completed:** 2026-09-10T04:54:13Z
- **Tasks:** 2/2
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- `backend/ercot_dlr_merger.py::process_dlr_to_hourly` gained a `city: str = None` parameter; `static_capacity_mw` is now computed from the resolved per-city rating instead of the unconditional `config.DEFAULT_STATIC_RATING` read the milestone audit flagged.
- `backend/dlr_pipeline.py::run_pipeline` and `::plot_dlr_summary` each replaced their `static_rating: float` parameter with the same `city: str = None` pattern; `dlr_headroom_pct`, `dlr_uplift_flag`, and the plot's reference-line label/position all now derive from the resolved city rating.
- Both files' `__main__` demo blocks now pass `city="AUSTIN"`, so both audit-flagged files are fixed at their own execution points, not merely made fixable.
- Added a module-top `import config` to `dlr_pipeline.py` (previously only imported inside `__main__`), so both functions are safely importable and testable without running the script.
- 17 new tests across both test files prove the resolution end to end, including the flagship DS-F5 observable: the same synthetic weather flips `dlr_uplift_flag` from `True` (fallback rating) to `False` (Austin rating) purely because `city="AUSTIN"` was supplied.
- `README.md`'s "Key Parameters to Tune" table now documents `city` in place of the removed `static_rating` row.

## Task Commits

Each task was committed atomically:

1. **Task 1: One CSV, one city, end to end — a per-location rating reaches static_capacity_mw** - `d3d002e` (feat)
2. **Task 2: Expand the same resolution into dlr_pipeline, its two entry-point call sites, and the README** - `81725d8` (feat)

_Note: both tasks were `tdd="true"`; tests were written and run alongside the implementation within each task's single commit rather than as separate RED/GREEN commits, since both tasks' `<action>` text interleaves test and production code as one described unit of work._

## Files Created/Modified

- `backend/ercot_dlr_merger.py` - `process_dlr_to_hourly` gains `city` param + resolution; `__main__` passes `city="AUSTIN"`
- `backend/tests/ercot_dlr_merger_test.py` - 10 new tests appended (source of pre-existing tests unmodified)
- `backend/dlr_pipeline.py` - `run_pipeline`/`plot_dlr_summary` gain `city` param + resolution; module-top `import config`; `__main__` passes `city="AUSTIN"` at both call sites; `profile_missing_data` warning fix
- `backend/tests/dlr_pipeline_test.py` - new file, 7 tests (this module had no test coverage before this phase)
- `README.md` - "Key Parameters to Tune" table row replaced (`static_rating` → `city`)

## Decisions Made

- Followed the plan's specified resolution expression verbatim in both files: `config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)`.
- For the merger test file's required append-only diff, added `import config` and a second, separate `from ercot_dlr_merger import LINE_VOLTAGE_KV, POWER_FACTOR` import line rather than editing the existing import line the plan's prose suggested modifying — editing it would have produced a modified (non-appended) line and failed the plan's own machine-checked append-only gate (`git diff | grep -c '^-'` must print exactly 1). Same effect (test values derived from the module under test), gate-compliant form.
- Compared pandas `Series` values via `.to_numpy() == pytest.approx(...)` rather than the more naturally-reached `series == pytest.approx(scalar_or_series)` form, after discovering the latter silently returns all-`False` instead of doing an elementwise approximate comparison.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a pre-existing pandas FutureWarning in `profile_missing_data` that violated this plan's own "no warning logged" must-have**
- **Found during:** Task 2, while verifying `test_unknown_city_falls_back_silently` (`dlr_pipeline_test.py`)
- **Issue:** `profile_missing_data`'s `df.groupby("stid").apply(lambda x: x.isna().mean() * 100)` emits `FutureWarning: DataFrameGroupBy.apply operated on the grouping columns...` on every `run_pipeline` call, regardless of `city`. This is unrelated to the city-resolution change but directly violates the plan's must-have: "A city string absent from `config.STATIC_RATINGS`... resolves to `config.DEFAULT_STATIC_RATING` with no exception raised and no warning logged, in all three functions." Since `run_pipeline` calls `profile_missing_data` unconditionally, the required test (run under `warnings.simplefilter("error")`, per the plan's own action text) would fail on this pre-existing warning even with a correct city-resolution fix.
- **Fix:** Added `include_groups=False` to the `groupby(...).apply(...)` call — the exact remediation pandas' own deprecation message recommends. Behavior-preserving (confirmed via the full test suite and the specific new test).
- **Files modified:** `backend/dlr_pipeline.py`
- **Verification:** `test_unknown_city_falls_back_silently` passes under `warnings.simplefilter("error")`; full suite green.
- **Committed in:** `81725d8` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug fix)
**Impact on plan:** Necessary for the plan's own must-have to be satisfiable; no scope creep — the fix is a single keyword argument with no behavior change to the actual missing-data profiling logic.

## Issues Encountered

- The assigned worktree branch was several dozen commits stale (its tip predated this phase's own plan file, the entire Phase 4 predictive subsystem, and `requirements.txt`). Verified zero divergence (worktree tip was a strict ancestor of `main`'s tip) before a plain `git merge --ff-only main` — non-destructive, no worktree-local work existed yet to lose.
- No `.venv` existed in the worktree (venvs are gitignored and not shared by git across worktrees). Symlinked the worktree's `.venv` to the main checkout's existing, working virtualenv rather than reinstalling dependencies, since the plan pins every verify command to `.venv/bin/python`.
- Comparing a pandas `Series` to `pytest.approx(...)` via `==` silently returns all-`False` instead of an elementwise approximate comparison (confirmed by isolating the exact failure before fixing every affected assertion to compare `.to_numpy()` values instead). Not a plan defect — a pytest/pandas interaction gotcha discovered while writing the new tests.

## Human Check (from `<verification><human-check>`)

**Outcome: input CSV absent.** The plan's manual verification step asks to run `.venv/bin/python backend/ercot_dlr_merger.py` (or inspect its output CSV) and confirm `static_capacity_mw` reads ~1078.6 MW rather than ~510.9 MW against a real data file. Checked directly: `outputs/station_data/2025-07-01_2025-07-04_AN489.csv` does not exist in this environment (no prior pipeline run has produced it, and `outputs/` is gitignored). Per the plan's own instruction for this case, this is recorded rather than a fabricated run — the automated tests (both new test files, all passing) already cover the identical resolution logic against synthetic fixtures, including the exact numeric values (`amps_to_mw(1900.0, 345.0, 0.95)` = 1078.5913391433292) the human-check would have confirmed on real data.

## Next Phase Readiness

- DS-F5 in `.planning/REQUIREMENTS.md` can move from "In Progress (partial)" to **Complete** — this plan closes the gap `.planning/v1.0-MILESTONE-AUDIT.md` confirmed, and was the last open requirement on the v1.0 milestone.
- Full suite: 155 passed, 0 failed (up from a 138-passed pre-phase baseline: +10 tests in Task 1, +7 tests in Task 2).
- No blockers. No follow-on work identified by this plan (multi-city loops, station discovery, and coordinate-based resolution were explicitly deferred out of scope per D-03/D-08/D-09 and are not needed to close DS-F5).

## Self-Check: PASSED

All created/modified files confirmed present on disk (`backend/ercot_dlr_merger.py`, `backend/tests/ercot_dlr_merger_test.py`, `backend/dlr_pipeline.py`, `backend/tests/dlr_pipeline_test.py`, `README.md`), and both task commits (`d3d002e`, `81725d8`) confirmed present in `git log --oneline --all`.

---
*Phase: 05-ds-f5-wiring-per-location-static-ratings*
*Completed: 2026-09-10*
