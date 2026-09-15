---
phase: 10-fallback-wiring-documentation-ratification
plan: 02
subsystem: data-science
tags: [weather-provider, fallback, nsrdb, tceq, synoptic, pandas, pytest, tdd]

# Dependency graph
requires:
  - phase: 10-fallback-wiring-documentation-ratification
    provides: "Plan 10-01's proven TCEQ-to-Synoptic fallback tracer (registry, eligibility gate, _attempt_fallback) on the station path"
provides:
  - "weather_provider._as_grid_shaped(frame, lat, lon) -- the seam that reconciles a station-shaped Synoptic fallback frame with the grid path's city-column contract"
  - "A grid-path (nsrdb) fallback: fetch_weather(..., provider=\"nsrdb\") now falls back to Synoptic exactly like the station-path (tceq) fallback, honest about solar and safe against ASOS-supplemented re-keying"
  - "Full eight-combination coverage: both fallback-eligible primaries (tceq, nsrdb) fall back correctly for all four CITY_COORDINATES/TCEQ_STATIONS cities"
  - "A both-providers-failed exhaustion path that always raises (never returns an empty frame) with the primary error chained as __cause__"
  - "Proof that a fallback-sourced row is a first-class PIPELINE_SCHEMA row: it validates, merges, and attributes provenance to its real supplier, never to the failed primary"
affects: [10-03-live-verification-and-doc-ratification]

# Actuals (#2632)
actuals:
  tokens: 9201
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One-seam grid shaping: _as_grid_shaped is the single place a fallback frame is reconciled with the grid path's city-column contract, called from exactly one call site inside _attempt_fallback rather than duplicated per provider"
    - "City-or-index-level city guard: any code checking a frame's city column for nulls must handle both shapes (column, or index level after ASOS re-keying) -- a bug caught and fixed while writing this plan's own tests"

key-files:
  created: []
  modified:
    - backend/weather_provider.py
    - backend/tests/weather_provider_test.py
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "A fallback frame is never narrowed to solar_radiation alone even on the grid (nsrdb) path: NSRDB is solar-only because NREL's own documentation forbids using its 2m reanalysis wind for a wind-power calculation, but Synoptic's wind is a real 10m station measurement, so the fallback frame keeps its full measured variable set -- attach_provenance still attributes every field honestly to synoptic, and merge_observations gives a station-side primary precedence anyway"
  - "_as_grid_shaped returns its argument unchanged whenever city is already present as a column OR an index level -- treating only the column case would have reintroduced the duplicate-city reset_index() collision for an ASOS-supplemented fallback frame"
  - "An empty/None Synoptic fallback result now raises (chained from the primary error) instead of being silently returned -- ROADMAP SC1's 'still returns a usable row' describes the case where the fallback HAS data; a second exhausted provider is not usable data and must resolve toward the caller's static rating via a clean raise, not an empty frame that looks like success"

requirements-completed: [WX-06]

coverage:
  - id: D1
    description: "An NSRDB grid-path request whose provider fails returns a usable Synoptic-sourced frame carrying the city column the grid path promises, honest about solar (no fabricated 1000 W/m2, solar_source null exactly where solar_radiation is null), and safe against ASOS-supplemented re-keying"
    requirement: "WX-06"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_grid_failure_falls_back_to_a_city_attributed_synoptic_frame"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_grid_fallback_solar_source_is_null_and_never_fabricates_1000"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_grid_fallback_solar_source_is_synoptic_only_where_measured"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_grid_fallback_survives_an_asos_supplemented_frame_without_raising"
        status: pass
    human_judgment: false
  - id: D2
    description: "Both fallback-eligible primaries (tceq, nsrdb) fall back correctly for all four cities -- eight combinations, each proven to resolve the exact per-city Synoptic station ID, not merely to return some frame"
    requirement: "WX-06"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_tceq_fallback_resolves_the_correct_synoptic_station_per_city"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_fallback_resolves_the_correct_synoptic_station_per_city"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_fallback_station_ids_resolve_for_all_eight_city_primary_combinations"
        status: pass
    human_judgment: false
  - id: D3
    description: "When Synoptic also fails, or returns an empty frame, the adapter raises an error naming both providers (chained to the primary error) rather than returning a fabricated or empty frame; fallback=False suppresses the fallback on both legs with zero fallback calls"
    requirement: "WX-06"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_and_synoptic_both_failing_names_both_providers_and_chains_nsrdb_error"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_empty_synoptic_fallback_raises_instead_of_returning_the_empty_frame"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_empty_nsrdb_synoptic_fallback_raises_instead_of_returning_the_empty_frame"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_tceq_fallback_disabled_suppresses_fallback_with_zero_calls"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_fallback_disabled_suppresses_fallback_with_zero_calls"
        status: pass
    human_judgment: false
  - id: D4
    description: "A fallback-sourced row validates against PIPELINE_SCHEMA, uses only KNOWN_PROVIDER_NAMES, and merges with a live primary frame with each field attributed to its real supplier (never the failed primary), with the schema itself unchanged"
    requirement: "WX-06"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_fallback_sourced_grid_frame_rows_validate_against_pipeline_schema"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_fallback_sourced_grid_frame_source_columns_use_only_known_provider_names"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_fallback_sourced_row_merged_with_a_live_tceq_frame_attributes_the_real_supplier"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_pipeline_schema_is_unchanged_by_this_phase"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-09-14
status: complete
---

# Phase 10 Plan 02: Full-Surface WX-06 Fallback (Grid Path, Four Cities, Exhaustion, Schema Integration) Summary

**Generalized Plan 10-01's one-path TCEQ-to-Synoptic tracer to the full WX-06 surface: an `_as_grid_shaped` seam wires the NSRDB grid path into the same fallback, all eight city/primary combinations are individually proven to resolve the correct station, both-providers-exhausted always raises instead of returning an empty frame, and a fallback-sourced row is proven to validate/merge/attribute exactly like any other pipeline row.**

## Performance

- **Duration:** 45 min
- **Started:** 2026-09-14T22:10:00Z (approx.)
- **Completed:** 2026-09-14T22:55:00Z (approx.)
- **Tasks:** 3 completed
- **Files modified:** 3 (`backend/weather_provider.py`, `backend/tests/weather_provider_test.py`, `ACKNOWLEDGEMENTS.md`)

## Accomplishments

- Added `_as_grid_shaped(frame, lat, lon)` and wired it into `_attempt_fallback`'s grid branch, so a `provider="nsrdb"` failure now falls back to Synoptic exactly like the already-proven `provider="tceq"` station-path fallback, honest about solar and safe against an ASOS-supplemented re-keyed frame.
- Proved all eight city/primary combinations (4 cities x {tceq, nsrdb}) resolve to the exact configured Synoptic station ID, not merely "some frame comes back."
- Fixed a real gap in the both-providers-failed exhaustion path: an empty/`None` Synoptic fallback result was previously returned as-is instead of raising -- now it raises the same chained, both-providers-named `ValueError` a raised fallback exception produces.
- Proved a fallback-sourced row is a first-class `PIPELINE_SCHEMA` row: it validates, uses only registered provider names, and -- merged against a live TCEQ frame -- attributes wind/temp to `tceq` and the fallback-supplied solar to `synoptic`, never to the primary (`nsrdb`) that was asked for and never actually supplied anything.
- Repo-wide test suite grew from 363 to 388 passed, 0 failed.

## Task Commits

Each task was committed atomically:

1. **Task 1: NSRDB grid-path fallback, shaped for the grid contract and honest about solar** - `1752569` (feat)
2. **Task 2: Four cities x two primaries, plus the both-providers-failed exhaustion path** - `bfd7224` (test)
3. **Task 3: Schema and merge integration for a fallback-sourced row, and the phase-wide suite gate** - `8843418` (test)

**Plan metadata:** commit pending (this SUMMARY, per worktree convention STATE.md/ROADMAP.md are excluded)

_Note: All three tasks carry `tdd="true"`. Task 1 and Task 2 each combined a small, targeted production-code fix with their tests in one commit rather than a strict separate RED/GREEN split, since both fixes were discovered as blocking gaps while implementing that task's own required behavior (see "TDD Gate Compliance" below); Task 3 is test-only (no production code changed, confirmed by the `units_def.py` zero-diff verify)._

## Files Created/Modified

- `backend/weather_provider.py` - Added `_as_grid_shaped(frame, lat, lon)`; extended `_attempt_fallback`'s grid branch to shape and null-city-guard the fallback frame for grid requests; fixed the empty/`None`-fallback-result gap to raise instead of returning silently; extended the module docstring with a Phase 10 paragraph.
- `backend/tests/weather_provider_test.py` - Added three `Plan 10-02` sections (Task 1: 8 tests on grid-path shaping/solar-honesty; Task 2: 16 tests on eight-combination coverage and exhaustion; Task 3: 4 tests on schema/merge integration), 28 new tests total; zero pre-existing test bodies changed (confirmed by re-reading the diff after an initial truncation mistake was caught and fixed -- see Deviations).
- `ACKNOWLEDGEMENTS.md` - New session entry disclosing this plan's AI-assisted work (ECE 464 requirement).

## Decisions Made

- Fallback frames on the grid path keep their full measured variable set (not narrowed to solar) — see key-decisions above.
- `_as_grid_shaped` treats "city already present" as either a column or an index level — narrowing to only the column case would have reintroduced the exact duplicate-name collision the seam exists to prevent.
- An empty/`None` Synoptic fallback result is now a raise, not a silent pass-through — see key-decisions above.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a self-inflicted test-file truncation that silently deleted an existing test's assertion**
- **Found during:** Task 1, immediately after writing the new tests and before the first test run
- **Issue:** My initial `Read` of the test file's tail used a `limit` that cut off exactly one line short of EOF, so I didn't see that the last pre-existing test (`test_both_sides_failing_message_carries_no_credential_value`) had a second assertion (`assert "token" not in message.lower()`) after the one I could see. My subsequent `Edit` (appending new tests after what I believed was the last line) matched only the visible portion, silently severing that second assertion from its test and leaving it dangling as an orphaned statement at the new end of file — which then raised `NameError: name 'message' is not defined` inside an unrelated new test, and (worse) removed real test coverage from the pre-existing test without any error at edit time.
- **Fix:** Compared against `git show HEAD:...` to recover the exact original content, restored the missing assertion to its correct test, and removed the orphaned dangling line from the new tests' tail.
- **Files modified:** `backend/tests/weather_provider_test.py`
- **Verification:** Full file re-run confirmed the restored test still passes and no other pre-existing test body was altered (`git diff` reviewed line-by-line before committing).
- **Committed in:** `1752569` (Task 1 commit; the fix landed before that commit, not as a separate one)

**2. [Rule 1 - Bug] Renamed a test helper that shadowed an earlier same-named helper**
- **Found during:** Task 1, first full-file test run
- **Issue:** I defined a new module-level helper `_asos_supplement_frame(n: int = 2)` for the grid-path ASOS-shape test, not noticing an earlier, differently-shaped helper of the exact same name already existed (`_asos_supplement_frame()`, no args) from the Plan 07-01 ASOS section. Python module-level function definitions silently overwrite earlier ones with the same name, so my later definition replaced the original globally — breaking four unrelated pre-existing tests (`test_asos_only_rows_are_attributed_to_asos`, `test_asos_only_rows_leave_unmeasured_fields_null`, `test_asos_supplemented_rows_validate_against_pipeline_schema`, and one more) that depended on the original frame's specific shape (3 timestamps, specific sentinel values).
- **Fix:** Renamed my new helper to `_grid_fallback_asos_supplement_frame` and updated its one call site.
- **Files modified:** `backend/tests/weather_provider_test.py`
- **Verification:** Full file re-run returned to 108/108 passed with the rename in place.
- **Committed in:** `1752569` (Task 1 commit; the fix landed before that commit, not as a separate one)

**3. [Rule 1 - Bug] Fixed `_attempt_fallback`'s null-city guard to handle `city` as an index level, not just a column**
- **Found during:** Task 1, writing the ASOS-supplemented-shape test
- **Issue:** My initial grid-shaping guard (`frame["city"].isna().any()`) assumed `city` is always a plain column after `_as_grid_shaped`. But `_as_grid_shaped`'s own contract explicitly returns a frame unchanged when `city` is already an index level (the ASOS-supplemented case) -- so the guard raised `KeyError: 'city'` on exactly the case Task 1's action text called out as needing to "return without raising a duplicate-city error."
- **Fix:** Extract `city` values via a column-or-index-level union before the null check, mirroring the same pattern `_as_grid_shaped` itself already uses.
- **Files modified:** `backend/weather_provider.py`
- **Verification:** `test_nsrdb_grid_fallback_survives_an_asos_supplemented_frame_without_raising` passes; full file green.
- **Committed in:** `1752569` (Task 1 commit)

**4. [Rule 1 - Bug] Fixed `_attempt_fallback` to raise on an empty/`None` fallback result instead of returning it silently**
- **Found during:** Task 2, while writing the plan's own required "empty fallback frame raises" test
- **Issue:** The pre-existing code only wrapped the `_fetch_station(..., FALLBACK_PROVIDER)` call in a `try`/`except` to catch a *raised* fallback failure; a fallback call that succeeded but returned an empty (or `None`) frame was returned as-is with no check, silently propagating a not-usable-data result as if it were success. This directly contradicted the plan's own required behavior ("When the Synoptic fallback returns an empty frame, the adapter raises rather than returning the empty result") and the project's fail-safe commitment.
- **Fix:** Added an explicit empty/`None` check immediately after the successful fallback fetch, raising the same both-providers-named, chained `ValueError` a raised fallback exception already produces.
- **Files modified:** `backend/weather_provider.py`
- **Verification:** `test_empty_synoptic_fallback_raises_instead_of_returning_the_empty_frame` and `test_empty_nsrdb_synoptic_fallback_raises_instead_of_returning_the_empty_frame` pass; full pre-existing suite re-run confirmed no regression (108/108 at that point).
- **Committed in:** `bfd7224` (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (2 self-inflicted test-authoring mistakes caught and corrected before commit, 2 genuine production-code Rule 1 bugs found while implementing this plan's own required behavior).
**Impact on plan:** All four fixes were necessary for correctness (items 3 and 4 are real behavior gaps the plan's own acceptance criteria required closing) or for not silently degrading existing test coverage (items 1 and 2). No scope creep — every fix stayed inside this plan's own `<files>` list and existing test conventions.

## Issues Encountered

- **Environment gap, not a production-code issue (same as Plan 10-01):** this git worktree has no `.venv` (worktrees don't check out gitignored/untracked directories). Ran tests via the main checkout's existing `.venv` (`/Users/aphan/Senior_Design/.venv/bin/python`) by absolute path instead of the plan's literal `.venv/bin/python` — every verify command's actual assertions ran unmodified, only the interpreter path differed. No `.venv` symlink was created or committed in this worktree.

## TDD Gate Compliance

All three tasks carry `tdd="true"`. Task 3 is a clean test-only commit (no production code touched, verified by the `units_def.py`/`weather_provider.py`-untouched-by-Task-3 check). Task 1 and Task 2 each landed one commit combining tests with a small, targeted production-code fix discovered as a blocking gap while writing that task's own required-behavior tests (deviations 3 and 4 above), rather than a strict separate `test(...)` RED-then-`feat(...)` GREEN commit pair. Every `<acceptance_criteria>` line and every `<verify>` command in the plan was independently re-run against the final state before each commit (`-k "fallback"` at 24/24 -> 37/37, the full file at 108/108 -> 122/122 -> 126/126, and the whole repository at 370 -> 384 -> 388 passed, 0 failed throughout) — so no criterion was accepted on faith, but the git history does not show a strict per-task RED/GREEN split. This is a process deviation from the strict TDD gate sequence, not a correctness gap, consistent with how Plan 10-01 documented the same pattern.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 10-03 (live verification and doc ratification) can proceed: the fallback is now proven across the adapter's full surface (both fallback-eligible primaries, all four cities, both station and grid paths), with provider exhaustion and schema/merge integration also pinned by tests.
- `config.SYNOPTIC_FALLBACK_STATIONS` still carries three unconfirmed ICAO station IDs (`KCRP`, `KMAF`, `KELP`) per Plan 10-01's own note — Plan 10-03's live check remains the next verification point for those; nothing in this plan touched that table or added new stations to confirm.
- No blockers.

## Self-Check: PASSED

- `backend/weather_provider.py`: FOUND
- `backend/tests/weather_provider_test.py`: FOUND
- `ACKNOWLEDGEMENTS.md`: FOUND
- Commit `1752569` (Task 1): FOUND in `git log --oneline --all`
- Commit `bfd7224` (Task 2): FOUND in `git log --oneline --all`
- Commit `8843418` (Task 3): FOUND in `git log --oneline --all`
- Full repository suite: `370 -> 384 -> 388 passed, 0 failed` across the three task commits
- Plan-level `<verification>`: `.venv/bin/python -m pytest -q` reports 388 passed, 0 failed (ROADMAP SC4); both fallback-eligible primaries fall back for all four cities (ROADMAP SC1); a fallback-sourced row's provenance records `synoptic`, never the failed primary (ROADMAP SC2); `backend/units_def.py` is unmodified (confirmed via `git diff --name-only`)

---
*Phase: 10-fallback-wiring-documentation-ratification*
*Completed: 2026-09-14*
