---
phase: 06-multi-provider-adapter-foundation
plan: 03
subsystem: data-contract
tags: [pandas, pytest, weather-adapter, tdd, merge]

# Dependency graph
requires:
  - phase: 06-multi-provider-adapter-foundation
    provides: "PIPELINE_SCHEMA v3 provenance columns and weather_provider.attach_provenance (Plan 06-01); fetch_weather's type-dispatched location parameter and resolve_station_city (Plan 06-02)"
provides:
  - "weather_provider.MERGE_KEY = (\"city\", \"datetime_utc\") -- the literal key every Phase 7-10 provider merges through"
  - "weather_provider.attach_city(frame, *, lat=None, lon=None) -> pd.DataFrame -- resolves a city column via resolve_station_city, never defaulting"
  - "weather_provider.merge_observations(station_frame, grid_frame) -> pd.DataFrame -- combines a station and a grid frame into one row per (city, datetime_utc), station values winning ties, provenance travelling with its value"
  - "A test-only mock grid provider (_mock_grid_provider) and full end-to-end merge test group proving WX-05 against PIPELINE_SCHEMA v3"
  - "C4-weather-ingestion.md brought current to describe the merge seam"
affects: [07-trivial-providers, 08-nsrdb, 09-tceq, 10-synoptic-fallback]

# Actuals (#2632)
actuals:
  tokens: 7499
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "combine_first as the merge primitive: fills nulls column-by-column from the other frame and unions both indexes, so a provenance cell's non-null/null state stays paired with its data cell's non-null/null state automatically -- no post-merge provenance rewriting needed"
    - "Null-city rows raise ValueError naming the count rather than silently grouping under a shared null key -- prevents pandas from stitching unrelated stations into one fabricated row"
    - "Test-only provider scaffolding (D-07) lives entirely in the test module, proven absent from the production module via an importlib.reload + hasattr probe"

key-files:
  created: []
  modified:
    - backend/weather_provider.py
    - backend/tests/weather_provider_test.py
    - docs/data-science/specs/C4-weather-ingestion.md
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "relative_humidity is passed as an explicit null column (not omitted) in the 'field neither side supplied' test, matching the real shape dlr_pipeline.fetch_timeseries always returns (DLR_VARS columns exist even when a sensor is fully dead) -- a column neither frame ever creates doesn't exist post-merge, so testing 'stays null' requires the column to exist going in."
  - "attach_city's per-row lat/lon derivation tolerates a frame with no 'lon' column by substituting an all-None Series, rather than raising -- only a missing 'lat' column is treated as the caller-bug case per the plan's explicit instruction."

patterns-established:
  - "merge_observations's _prepare_merge_side helper: normalizes a MERGE_KEY-bearing frame (reset_index if the key is partly in the index, validate presence, validate no null city, then set_index+sort) -- the single seam a Phase 7-10 provider's output flows through before merging."

requirements-completed: [WX-05, WX-07]

coverage:
  - id: D1
    description: "merge_observations combines a station and grid frame into exactly one row per (city, datetime_utc), with the station's non-null value winning where both sides supply a field and each field's provenance naming the provider that actually supplied it"
    requirement: "WX-05"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merge_combines_station_and_grid_into_one_row_per_timestamp"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merge_provenance_names_the_actual_supplier_per_field"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merge_station_value_wins_when_both_sides_supply_a_field"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merge_leaves_a_field_neither_side_supplied_null_with_null_provenance"
        status: pass
    human_judgment: false
  - id: D2
    description: "Empty, single-row, and null-city inputs to merge_observations each behave exactly as specified: empty/empty returns empty, one-empty returns the other side unchanged, single-row needs no special case, and a null city raises ValueError naming the count"
    requirement: "WX-07"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merge_with_an_empty_station_frame_returns_the_grid_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merge_with_an_empty_grid_frame_returns_the_station_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merge_of_two_empty_frames_returns_an_empty_frame"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merge_of_single_row_frames_needs_no_special_case"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merge_raises_when_a_row_has_no_resolvable_city"
        status: pass
    human_judgment: false
  - id: D3
    description: "Merged output is sorted ascending by (city, datetime_utc) and reproducible regardless of input row order; attach_city yields only literal config.CITY_COORDINATES keys and never mutates its argument"
    requirement: "WX-07"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merge_output_is_sorted_and_reproducible"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_attach_city_returns_literal_config_keys"
        status: pass
    human_judgment: false
  - id: D4
    description: "A synthetic station provider and a synthetic grid provider (_mock_grid_provider, D-07 test-only) combine end to end into one PIPELINE_SCHEMA-v3-valid row per timestamp, and the mock provider never leaks into the real fetch_weather dispatch"
    requirement: "WX-05"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_end_to_end_station_plus_mock_grid_produces_one_validated_row"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_mock_grid_provider_is_not_registered_in_the_real_dispatch"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_merged_row_provenance_matches_its_values"
        status: pass
    human_judgment: false
  - id: D5
    description: "C4-weather-ingestion.md describes the current adapter (type-dispatched fetch_weather, merge_observations, PIPELINE_SCHEMA v3) rather than the pre-Phase-6 single-provider description; PRD.md and data_provider.md remain untouched (WX-08/Phase 10 scope); the ECE 464 AI-use disclosure lands before the phase's final commit"
    verification:
      - kind: other
        ref: "python -c check for 'fetch_weather(location', 'merge_observations', 'v3' substrings -> printed 'C4 spec current'"
        status: pass
      - kind: other
        ref: "PRD.md SHA-256 prefix f513077ba722 unchanged; git diff --stat empty for PRD.md and data_provider.md"
        status: pass
      - kind: other
        ref: "ACKNOWLEDGEMENTS.md Phase 6 Plan 06-03 session entry present above '## Keeping This Updated'"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-09-11
status: complete
---

# Phase 6 Plan 03: City-Keyed Merge Summary

**A station-sourced frame and a grid-sourced frame now combine into exactly one row per (city, datetime_utc) via `merge_observations`'s `combine_first`, with per-field provenance travelling with its value, proven end-to-end through a synthetic grid provider against `PIPELINE_SCHEMA` v3.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3 (1 TDD-gated with RED/GREEN split, 2 executed)
- **Files modified:** 4 (`backend/weather_provider.py`, `backend/tests/weather_provider_test.py`, `docs/data-science/specs/C4-weather-ingestion.md`, `ACKNOWLEDGEMENTS.md`)

## Accomplishments

- `weather_provider.MERGE_KEY = ("city", "datetime_utc")` — the literal key every future Phase 7-10 provider merges through.
- `weather_provider.attach_city(frame, *, lat=None, lon=None)` — attaches a `city` column via `resolve_station_city`, either from a single caller-supplied coordinate pair (the grid case) or per-row from the frame's own `lat`/`lon` columns (the station case), never defaulting or inferring. Copies the frame; the caller's argument is left unchanged.
- `weather_provider.merge_observations(station_frame, grid_frame)` — normalizes each non-empty side onto `MERGE_KEY` (validating both key members are present as a column or index level, and that no row has a null city), then combines via `station_frame.combine_first(grid_frame).sort_index()`. Empty/empty returns an empty frame; one-empty returns the other side re-indexed and sorted; a null city raises `ValueError` naming the count of unresolvable rows rather than letting pandas silently fabricate a shared-key row from unrelated stations.
- `backend/tests/weather_provider_test.py` gained 15 new tests: 11 for `merge_observations`/`attach_city` directly (Task 1), plus `_mock_grid_provider` (D-07 test scaffolding) and 3 end-to-end tests proving the whole merge path, including `validate_pipeline_row(...) == []` on every merged row (Task 2).
- `docs/data-science/specs/C4-weather-ingestion.md` rewritten to describe `fetch_weather(location, ...)`'s type dispatch, provenance tagging, the grid path's Phase 7 placeholder, and `merge_observations` as the combination seam — replacing the now-false "deliberately does not accommodate a second provider" claim. `PRD.md` and `data_provider.md` (WX-08/Phase 10 scope) left byte-identical.
- `ACKNOWLEDGEMENTS.md` gained the Phase 6 Plan 06-03 session entry per the standing ECE 464 AI-use disclosure requirement, landed before this phase's final commit.
- Full suite: **195 passed, 0 failed** (up from a 181-passed pre-plan baseline) — closes ROADMAP Success Criteria #5.

## Task Commits

Each task was committed atomically. Task 1 (TDD) produced two commits (RED, then GREEN):

1. **Task 1 (RED): failing tests for city-keyed merge and attach_city** — `5d88543` (test)
2. **Task 1 (GREEN): MERGE_KEY, attach_city, merge_observations implementation** — `b380578` (feat)
3. **Task 2: end-to-end merge proof through a synthetic grid provider** — `e8c2426` (test)
4. **Task 3: C4 spec current + Phase 6 ACKNOWLEDGEMENTS.md entry** — `4d0872e` (docs)

**Plan metadata:** committed separately (this SUMMARY.md) per the parallel-execution contract — STATE.md/ROADMAP.md are NOT touched here; the orchestrator owns those writes after merge.

## Files Created/Modified

- `backend/weather_provider.py` — `MERGE_KEY`, `attach_city()`, `_prepare_merge_side()`, `merge_observations()`
- `backend/tests/weather_provider_test.py` — 15 new tests across two Task-scoped groups (`test_merge_*`/`test_attach_city_*`, and the Task 2 end-to-end group plus `_mock_grid_provider`/`_station_frame`/`_grid_frame`/`_end_to_end_merged_frame` builders)
- `docs/data-science/specs/C4-weather-ingestion.md` — implementation paragraph and `fetch_timeseries` reference brought current
- `ACKNOWLEDGEMENTS.md` — Phase 6 Plan 06-03 session entry

## Decisions Made

See "Key Decisions" in frontmatter above. No architectural (Rule 4) decisions were required — both deviations below are mechanical Rule 1/Rule 3 fixes to match the plan's own behavior and machine-checked verify gates.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a test-shape gap in the "field neither side supplied" test found during GREEN**
- **Found during:** Task 1, after implementing `merge_observations` and re-running the RED suite to confirm GREEN
- **Issue:** The plan's `test_merge_leaves_a_field_neither_side_supplied_null_with_null_provenance` behavior implies a `relative_humidity` column exists post-merge (null value, not a missing column). A column that neither input frame ever populates doesn't exist as a column in either frame, so `combine_first` correctly produces no such column in the merged output — the test's `merged["relative_humidity"]` assertion raised `KeyError` (a real bug in the test's own construction, not a merge_observations defect) rather than proving the intended "stays null" behavior.
- **Fix:** Passed `relative_humidity=[None, None]` as an explicit null column on the station side of that one test, matching the real shape `dlr_pipeline.fetch_timeseries` always returns (its `DLR_VARS` columns exist even when a sensor is fully dead). This makes the test prove "the merge leaves it null" rather than "the column never existed" — a stronger, more accurate assertion of the same underlying invariant. `merge_observations`'s implementation itself needed no change.
- **Files modified:** `backend/tests/weather_provider_test.py`
- **Verification:** `pytest backend/tests/weather_provider_test.py -q -k "merge or attach_city"` → 11 passed, 0 failed.
- **Committed in:** `b380578` (Task 1 GREEN commit, alongside the RED test file's one corrected test)

---

**Total deviations:** 1 auto-fixed (1 bug, test-only — no production behavior affected)
**Impact on plan:** Necessary for the test to actually exercise the behavior the plan's `<behavior>` text describes. No scope creep — the underlying `merge_observations` implementation is unchanged by this fix.

## Issues Encountered

**Worktree branch was stale at spawn time (same pattern as every prior worktree-executor session in this project).** The assigned worktree's branch (`worktree-agent-a2d752bbc22fe375a`) predated all of Phase 6's plan files and execution commits — Plans 06-01 and 06-02 did not exist in the worktree. Verified zero divergence (the worktree tip was a strict ancestor of `main`'s tip, no unique worktree commits) before a plain fast-forward merge (`git merge --ff-only main`) — the same non-destructive pattern used by every prior worktree-executor session in this log. `expected_base` for the orchestrator's merge-back is `1b3c899` (the commit `main` was at when task work started, immediately following the fast-forward).

**No `.venv` in the worktree.** Python virtualenvs are gitignored and not shared across git worktrees by git itself. Every `pytest`/`python` invocation in this session used the shared `.venv` at the main checkout's absolute path (`/Users/aphan/Documents/Senior_Design/.venv/bin/python`), matching every prior worktree-executor session's convention.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 6 (Multi-Provider Adapter Foundation) is now complete: `PIPELINE_SCHEMA` v3's provenance columns (06-01), `fetch_weather`'s type-dispatched `location` and `resolve_station_city` (06-02), and the city-keyed `merge_observations` seam (06-03) together give Phase 7-10 a tested, byte-compatible seam to plug a real grid provider (NSRDB or Open-Meteo) into.
- `merge_observations`'s signature (`station_frame`, `grid_frame`) and `MERGE_KEY` are now the stable contract those phases inherit — `_fetch_grid`'s `ValueError` is the only thing that needs replacing when the first real grid provider lands.
- `_mock_grid_provider` is test-only scaffolding (D-07) and is explicitly expected to be replaced, not extended, by Phase 7's real adapter.
- No blockers identified for Phase 7.

---
*Phase: 06-multi-provider-adapter-foundation*
*Completed: 2026-09-11*

## Self-Check: PASSED

- FOUND: backend/weather_provider.py
- FOUND: backend/tests/weather_provider_test.py
- FOUND: docs/data-science/specs/C4-weather-ingestion.md
- FOUND: ACKNOWLEDGEMENTS.md
- FOUND: .planning/phases/06-multi-provider-adapter-foundation/06-03-SUMMARY.md
- FOUND: 5d88543, b380578, e8c2426, 4d0872e, ce06455
