---
phase: 06-multi-provider-adapter-foundation
plan: 02
subsystem: data-contract
tags: [pandas, pytest, weather-adapter, tdd, dispatch]

# Dependency graph
requires:
  - phase: 06-multi-provider-adapter-foundation
    provides: "PIPELINE_SCHEMA v3 provenance columns and weather_provider.attach_provenance (Plan 06-01)"
provides:
  - "fetch_weather's type-dispatched location parameter (list[str] station path | (lat, lon) grid path), with an explicit shape guard rejecting every ambiguous input"
  - "weather_provider.resolve_station_city(lat, lon) -> str | None — internal station-to-city resolution via haversine distance to config.CITY_COORDINATES, never a default or nearest-guess fallback"
  - "dlr_pipeline.fetch_timeseries's returned frame carries lat/lon columns parsed from each STATION object, null-tolerant"
affects: [06-03-city-keyed-merge, 07-trivial-providers, 08-nsrdb, 09-tceq, 10-synoptic-fallback]

# Actuals (#2632)
actuals:
  tokens: 3716
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Type-dispatch via an explicit shape guard (_validate_location_shape) returning a literal classification string or raising ValueError naming the received type/length — never inferring intent from a structurally-similar-but-wrong shape (a 2-element list of numbers is rejected, not silently read as coordinates)"
    - "Internal city resolution kept out of the public call surface: resolve_station_city exists but is not called from fetch_weather's station path in this plan — it is wired in only where a city key is actually consumed (Plan 06-03's merge)"
    - "TDD RED/GREEN as two separate git commits per task: tests written and run to confirm real failures (for the right reasons, not just 'undefined'), committed, then implementation added and re-verified before the GREEN commit"

key-files:
  created: []
  modified:
    - backend/weather_provider.py
    - backend/dlr_pipeline.py
    - backend/tests/weather_provider_test.py

key-decisions:
  - "Renamed fetch_weather's first parameter from stids to location (widened to list[str] | tuple[float, float]) after confirming via repo-wide grep that corridor_discretization.py:439 is the only call site and passes positionally — zero call-site edits required, matching D-02's premise."
  - "A list of two numbers (e.g. [30.27, -97.74]) is rejected by _validate_location_shape rather than accepted as an alternate grid syntax — the list/tuple distinction is the whole dispatch, and a typo'd station-id list must not be silently misread as coordinates."
  - "_fetch_grid raises ValueError naming that no grid provider is registered yet (Phase 7) rather than returning an empty/zero-filled/placeholder frame — matches this project's fail-safe commitment that a caller must never receive fabricated weather data."
  - "resolve_station_city implemented but not wired into fetch_weather's station path in this plan (per the plan's explicit instruction) — keeps the station-only return shape byte-compatible until Plan 06-03's merge is the actual consumer."

patterns-established:
  - "Ambiguous-shape ValueError messages carry only type(location).__name__ and length — never station IDs, coordinates, or request parameters (T-06-09, mirrors T-03-02's message-text-only convention)."

requirements-completed: [WX-05]

coverage:
  - id: D1
    description: "fetch_weather's location parameter dispatches a station-ID list to the existing Synoptic path and a (lat, lon) tuple to a not-yet-implemented grid path, rejecting every other shape (numeric list, string tuple, empty, 3-tuple) with a ValueError naming the received type/length"
    requirement: "WX-05"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_dispatch_station_list_routes_to_the_station_path"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_dispatch_latlon_tuple_routes_to_the_grid_path"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_dispatch_rejects_a_two_element_list_of_numbers"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_dispatch_rejects_a_two_element_tuple_of_strings"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_dispatch_rejects_empty_location"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_dispatch_rejects_a_three_element_tuple"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_dispatch_existing_positional_call_shape_still_works"
        status: pass
    human_judgment: false
  - id: D2
    description: "Zero call-site edits to corridor_discretization.py or its test file; both pass unchanged after the fetch_weather rename (ROADMAP SC2)"
    requirement: "WX-05"
    verification:
      - kind: unit
        ref: "backend/tests/corridor_discretization_test.py (52 tests, full file)"
        status: pass
    human_judgment: false
  - id: D3
    description: "resolve_station_city(lat, lon) returns a literal config.CITY_COORDINATES key for all four cities and None for any unresolvable/non-numeric/boolean/non-finite input, never a default or nearest-guess fallback"
    requirement: "WX-05"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_city_resolution_returns_a_literal_config_key"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_city_resolution_covers_all_four_cities"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_city_resolution_returns_none_for_missing_coordinates"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_city_resolution_never_defaults_to_a_city"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_city_resolution_is_deterministic_for_an_equidistant_point"
        status: pass
    human_judgment: false
  - id: D4
    description: "dlr_pipeline.fetch_timeseries's returned frame gains lat/lon columns from each STATION object's LATITUDE/LONGITUDE, null-tolerant on absent/non-numeric values, with index names and DLR_VARS columns unchanged"
    requirement: "WX-05"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_fetch_timeseries_frame_carries_lat_and_lon"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_fetch_timeseries_tolerates_a_station_object_without_coordinates"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_pipeline_test.py (regression, unchanged)"
        status: pass

duration: 45min
completed: 2026-09-10
status: complete
---

# Phase 6 Plan 02: Location Dispatch + Station-to-City Resolution Summary

**`fetch_weather` now accepts either a station-ID list or a `(lat, lon)` grid tuple through one type-dispatched `location` parameter with an explicit shape guard, and the adapter gained an internal `resolve_station_city` helper (haversine to `config.CITY_COORDINATES`) that Plan 06-03's city-keyed merge will consume — with zero edits to any existing caller.**

## Performance

- **Duration:** ~45 min
- **Tasks:** 2 (both TDD-gated, RED then GREEN commits each)
- **Files modified:** 3 (`backend/weather_provider.py`, `backend/dlr_pipeline.py`, `backend/tests/weather_provider_test.py`)

## Accomplishments

- `fetch_weather`'s first parameter renamed `stids` → `location`, widened to `list[str] | tuple[float, float]`. Confirmed via repo-wide grep that `corridor_discretization.py:439` is the only call site and passes positionally — the rename required zero call-site edits.
- `_validate_location_shape(location)` — an exact structural-match guard returning the literal `"station"` or `"grid"`, raising `ValueError` naming the received type and length for every other shape, including a two-number list (which must not be silently read as coordinates) and a three-element tuple.
- `_fetch_station` (existing Synoptic delegation + Plan 06-01's provenance wrapping) and `_fetch_grid` (raises `ValueError` naming that no grid provider is registered yet — Phase 7 lands the first one — never returns an empty/placeholder frame).
- `weather_provider.resolve_station_city(lat, lon) -> str | None` — returns the nearest `config.CITY_COORDINATES` key via the existing `station_explorer.haversine_km` (not reimplemented), or `None` for any non-finite/non-numeric/boolean coordinate. Not wired into `fetch_weather`'s station path in this plan, per its own instruction — Plan 06-03's merge is the first real consumer.
- `dlr_pipeline.fetch_timeseries`'s per-STATION parse loop now emits `lat`/`lon` columns from `LATITUDE`/`LONGITUDE`, coerced through a `float(...)` guard so an absent/null/non-numeric value degrades to `None` rather than raising mid-parse. Purely additive: index names (`stid`, `datetime_utc`) and `DLR_VARS` columns are unchanged.
- `backend/tests/weather_provider_test.py` gained 14 new tests (7 dispatch, 5 city-resolution, 2 fetch_timeseries lat/lon) across two RED→GREEN TDD cycles.
- Full suite: **181 passed, 0 failed** (up from a 167-passed pre-plan baseline).

## Task Commits

Each task followed the plan's TDD RED/GREEN structure as two separate commits:

1. **Task 1 (RED): failing tests for location dispatch** — `931dfb9` (test)
2. **Task 1 (GREEN): type-dispatch fetch_weather's location parameter** — `d964079` (feat)
3. **Task 2 (RED): failing tests for station-to-city resolution** — `2d36605` (test)
4. **Task 2 (GREEN): resolve a station to its city with no extra network call** — `58edbe4` (feat)

**Plan metadata:** committed separately (SUMMARY.md + ACKNOWLEDGEMENTS.md), per the parallel-execution contract — STATE.md/ROADMAP.md are NOT touched here; the orchestrator owns those writes after merge.

## Files Created/Modified

- `backend/weather_provider.py` — `fetch_weather`'s `location` parameter, `_validate_location_shape`, `_fetch_station`, `_fetch_grid`, `resolve_station_city`, `import config`/`import station_explorer`/`import math`
- `backend/dlr_pipeline.py` — `fetch_timeseries`'s per-STATION parse loop gains null-tolerant `lat`/`lon` columns
- `backend/tests/weather_provider_test.py` — 14 new tests across two Task-scoped groups (`test_dispatch_*`, `test_city_resolution_*` + `test_fetch_timeseries_*`)

## Decisions Made

See "Key Decisions" in frontmatter above. No architectural (Rule 4) decisions were required this session — every deviation below is a mechanical Rule 3 fix to match the plan's own machine-checked verify gate.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Renamed a test so the plan's own `-k dispatch` verify gate actually selects it**
- **Found during:** Task 1 (writing the RED tests)
- **Issue:** The plan's Task 1 behavior list specifies 7 tests, the 7th being `test_existing_positional_call_shape_still_works`. The plan's own `<verify>` block runs `pytest ... -q -k dispatch` and states it fails when "fewer than 7 tests selected." Since the 7th test's name doesn't contain the substring "dispatch", `-k dispatch` only ever selects 6 — the gate as written could never pass with the literally-named test.
- **Fix:** Renamed the test to `test_dispatch_existing_positional_call_shape_still_works` (same body, same assertion) so it is both correctly grouped with the other dispatch tests and satisfies the plan's stated 7-selected threshold.
- **Files modified:** `backend/tests/weather_provider_test.py`
- **Verification:** `pytest backend/tests/weather_provider_test.py -q -k dispatch` selects exactly 7, all pass after Task 1's GREEN commit.
- **Committed in:** `931dfb9` (Task 1 RED commit)

---

**Total deviations:** 1 auto-fixed (1 blocking, test-naming only — no production behavior affected)
**Impact on plan:** Necessary for the plan's own verify gate to pass as written; no scope creep. All other behavior (7 dispatch tests, 5 city-resolution tests, 2 fetch_timeseries tests) implemented exactly as specified.

## Issues Encountered

**Worktree branch was stale at spawn time (same pattern as every prior worktree-executor session in this project).** The assigned worktree's branch (`worktree-agent-a7ecf6121674765ba`) was based on a point on `main` that predated Plan 06-01's execution entirely — `.planning/phases/06-multi-provider-adapter-foundation/06-01-SUMMARY.md`, `06-02-PLAN.md`, and the provenance-schema changes to `backend/units_def.py`/`backend/weather_provider.py` did not exist in the worktree. Verified the worktree tip was a strict ancestor of `main`'s tip (`git merge-base --is-ancestor HEAD main`, true) before running `git merge --ff-only main` — the same non-destructive recovery used by every prior worktree-executor session (see `ACKNOWLEDGEMENTS.md`).

**No `.venv` in the worktree.** Python virtualenvs are gitignored and not shared across git worktrees. Every `pytest`/`python` invocation in this session used the shared `.venv` at the main checkout's absolute path (`/Users/aphan/Documents/Senior_Design/.venv/bin/python`), matching the plan's own `<verify>` command convention and the pattern Plan 06-01's executor used.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `fetch_weather`'s `location` dispatch and `resolve_station_city` are the two pieces Plan 06-03's city-keyed merge builds directly on top of.
- `resolve_station_city` is implemented and tested but intentionally unwired from `fetch_weather`'s return path — Plan 06-03 is expected to call it from the merge layer, not from this plan's functions.
- The grid path (`_fetch_grid`) is a deliberate dead end today — it exists solely to fail loudly with a named reason. Phase 7's first grid provider (NSRDB or Open-Meteo) is expected to replace its body, not its signature.
- No blockers identified for Plan 06-03.

---
*Phase: 06-multi-provider-adapter-foundation*
*Completed: 2026-09-10*

## Self-Check: PASSED

- FOUND: backend/weather_provider.py
- FOUND: backend/dlr_pipeline.py
- FOUND: backend/tests/weather_provider_test.py
- FOUND: .planning/phases/06-multi-provider-adapter-foundation/06-02-SUMMARY.md
- FOUND: 931dfb9, d964079, 2d36605, 58edbe4
