---
phase: 07-trivial-integration-providers
plan: 01
subsystem: api
tags: [weather-ingestion, asos, pandas, requests, unit-conversion, provenance]

# Dependency graph
requires:
  - phase: 06-multi-provider-adapter-foundation
    provides: "attach_provenance/attach_city/merge_observations/resolve_station_city seams, PIPELINE_SCHEMA v3 provenance columns, KNOWN_PROVIDER_NAMES already containing 'asos'"
provides:
  - "config.ASOS_STATIONS: 3-letter IEM FAA station codes per config.CITY_COORDINATES city"
  - "backend/asos_provider.py: fetch_asos_1min(station, start, end) -> PIPELINE_SCHEMA-shaped frame, no-side-effects-on-import"
  - "weather_provider._supplement_with_asos wired into _fetch_station's provider='synoptic' branch -- automatic, transparent ASOS supplement (D-01..D-03)"
affects: [07-02-open-meteo-backfill, 09-tceq-primary-wiring]

# Actuals (#2632)
actuals:
  tokens: 9171
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "New provider module mirrors dlr_pipeline.fetch_timeseries's HTTP-fetch-and-normalize shape (requests.get -> raise_for_status -> explicit body-shape checks -> pd.read_csv/pd.to_numeric -> units_def.Q conversion)"
    - "merge_observations (Phase 6) reused unmodified for a union-of-timestamps merge by passing a non-grid second frame -- it only cares that both sides are (city, datetime_utc)-indexed"
    - "Skip-not-raise guard ladder in _supplement_with_asos: every non-failure absence (no lat, unresolvable city, duplicate keys, empty ASOS window) returns the primary frame unchanged and logs at INFO; only genuine ASOS failures raise"

key-files:
  created:
    - backend/asos_provider.py
    - backend/tests/asos_provider_test.py
  modified:
    - backend/config.py
    - backend/weather_provider.py
    - backend/tests/weather_provider_test.py
    - backend/units_def.py

key-decisions:
  - "Q1-A (Task 1 checkpoint, user-approved default): a well-formed, zero-row ASOS response is non-fatal -- returns the Synoptic frame unchanged, logged at INFO. Raising is reserved for HTTP errors, unknown-station bodies, and unrecognised headers."
  - "Q2-A (Task 1 checkpoint, user-approved default): the merged frame re-keys to (city, datetime_utc) with stid demoted to a nullable column ONLY when ASOS actually supplies rows for the call; when it supplies nothing, the frame stays (stid, datetime_utc)-indexed, byte-identical to pre-Phase-7."
  - "Fixed a latent bug in units_def.validate_pipeline_row: it recognized Python None as 'missing' but not pandas' NaN, so a legitimately-absent required:False field (exactly D-02's design) was misreported as NON-FINITE or UNKNOWN PROVIDER. Broadened the missing-check to treat NaN identically to None."

patterns-established:
  - "Skip-ladder logging convention for a supplement seam: every non-failure absence logs at INFO with a specific reason, distinguishing 'never asked' from 'had nothing' from 'broke' -- reusable for Phase 9's TCEQ-as-primary wiring."

requirements-completed: [WX-02]

coverage:
  - id: D1
    description: "ASOS 1-minute wind/temp rows are unioned into the Synoptic series with converted units (degF->degC, knots->m/s), Synoptic winning at overlapping timestamps"
    requirement: "WX-02"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_asos_supplement_adds_rows_at_timestamps_synoptic_does_not_have"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_asos_supplement_leaves_synoptic_winning_at_a_shared_timestamp"
        status: pass
      - kind: unit
        ref: "backend/tests/asos_provider_test.py#test_fetch_asos_1min_converts_temperature_to_degc"
        status: pass
      - kind: unit
        ref: "backend/tests/asos_provider_test.py#test_fetch_asos_1min_converts_wind_speed_to_metres_per_second"
        status: pass
    human_judgment: false
  - id: D2
    description: "ASOS-only rows carry 'asos' provenance; unmeasured fields (relative_humidity, solar_radiation) stay null, never backfilled or derived (D-02)"
    requirement: "WX-02"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_asos_only_rows_are_attributed_to_asos"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_asos_only_rows_leave_unmeasured_fields_null"
        status: pass
    human_judgment: false
  - id: D3
    description: "No caller of fetch_weather changed -- corridor_discretization.rate_corridor's existing positional call is unchanged and its result is still consumable by _usable_observation (D-03)"
    requirement: "WX-02"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_corridor_usable_observation_reads_an_asos_supplemented_frame"
        status: pass
      - kind: integration
        ref: "backend/tests/corridor_discretization_test.py (68 tests, zero edits to corridor_discretization.py or its test file)"
        status: pass
    human_judgment: false
  - id: D4
    description: "ASOS fails loud: HTTP errors, unknown-station bodies, and unrecognised headers raise; a well-formed empty response (real sensor outage) is non-fatal and never reported as a successful supplement"
    requirement: "WX-02"
    verification:
      - kind: unit
        ref: "backend/tests/asos_provider_test.py#test_fetch_asos_1min_raises_on_an_unknown_station_body"
        status: pass
      - kind: unit
        ref: "backend/tests/asos_provider_test.py#test_fetch_asos_1min_raises_on_an_unrecognised_response_header"
        status: pass
      - kind: unit
        ref: "backend/tests/asos_provider_test.py#test_fetch_asos_1min_propagates_an_http_error"
        status: pass
      - kind: unit
        ref: "backend/tests/asos_provider_test.py#test_fetch_asos_1min_returns_an_empty_frame_for_a_header_only_response"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_asos_failure_propagates_out_of_fetch_weather"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_asos_empty_window_returns_the_synoptic_frame_unchanged"
        status: pass
    human_judgment: false
  - id: D5
    description: "The supplement never removes, replaces, reorders, or fabricates a primary row -- skips cleanly on no lat column, unresolvable city, or duplicate (city, datetime_utc) keys"
    requirement: "WX-02"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_asos_supplement_is_skipped_when_a_synoptic_row_has_no_resolvable_city"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_asos_supplement_is_skipped_when_the_synoptic_frame_has_duplicate_city_timestamp_keys"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_asos_supplement_never_drops_a_synoptic_row"
        status: pass
    human_judgment: false
  - id: D6
    description: "config.ASOS_STATIONS maps each of the four CITY_COORDINATES keys to a 3-letter IEM ASOS identifier; importing asos_provider has no side effects and needs no token"
    requirement: "WX-02"
    verification:
      - kind: unit
        ref: "asos station map probe (Task 2 verify) -- printed 'asos station map OK'"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_all_four_cities_resolve_to_a_three_letter_asos_station"
        status: pass
      - kind: unit
        ref: "backend/tests/asos_provider_test.py#test_module_import_has_no_side_effects"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-09-12
status: complete
---

# Phase 7 Plan 1: ASOS 1-minute Supplement Summary

**ASOS 1-minute wind/temp rows now transparently supplement every Synoptic station-path `fetch_weather` call, unit-converted via `units_def.Q`, provenance-tagged, and fail-loud on genuine failures while treating a real sensor outage as a non-event.**

## Performance

- **Duration:** ~9 min (first RED commit to last GREEN commit)
- **Started:** 2026-09-12T02:36:03-05:00
- **Completed:** 2026-09-12T02:45:04-05:00
- **Tasks:** 3 (1 checkpoint decision, 2 TDD implementation tasks)
- **Files modified:** 6 (2 created, 4 modified)

## Checkpoint Resolution (Task 1)

This plan's Task 1 was a blocking `checkpoint:decision` covering two boundary interpretations of locked decisions D-05 and D-03 that the plan's own planner explicitly declined authority to settle. The orchestrator's continuation context recorded the user's response as "approved," accepting both of the plan's recommended defaults:

- **Q1: A** (of A/B) — a well-formed, zero-row ASOS response (a real 1-minute-sensor outage window, live-confirmed during this phase's research against station `ELP`) is **non-fatal**: the Synoptic frame is returned unchanged, logged at INFO. Raising is reserved for HTTP errors, an unknown-station body, and an unrecognised header row.
- **Q2: A** (of A/B) — the merged frame **re-keys to `(city, datetime_utc)`** with `stid` demoted to a nullable column **only when ASOS actually supplies rows** for the call. When ASOS supplements nothing, the frame stays `(stid, datetime_utc)`-indexed exactly as pre-Phase-7 — byte-identical.

Both are the plan's recommended (non-`-B`) options, so no `must_haves.truths` entries were invalidated and Task 2/3 implemented the plan's `<action>` text as written.

## Accomplishments
- `config.ASOS_STATIONS` maps all four `CITY_COORDINATES` cities to their 3-letter IEM ASOS FAA station codes (not the 4-letter ICAO codes used elsewhere in the project's docs, per `07-RESEARCH.md` Pitfall 1).
- New `backend/asos_provider.py`: `fetch_asos_1min(station, start, end)` fetches the IEM ASOS 1-minute CGI endpoint, converts `tmpf`→`air_temp` (degC) and `sknt`→`wind_speed` (m/s) exclusively via `units_def.Q` (grep-gated against inline conversion formulas), passes `drct`→`wind_direction` through unconverted, and produces tz-aware UTC timestamps.
- `weather_provider._supplement_with_asos` wired into `_fetch_station`'s `provider="synoptic"` branch: automatic and transparent per D-03 — no caller passes a new argument or keyword. Reuses `merge_observations` unmodified for the union-of-timestamps merge (D-01/D-02), Synoptic winning at any shared timestamp.
- Fail-loud hardening: `fetch_asos_1min` raises `ValueError` on an unknown-station body (HTTP-200-with-error-text) and on an unrecognised response header, propagates `requests.HTTPError` unchanged, and `_range_check` raises on any converted value outside `units_def.PIPELINE_SCHEMA`'s declared range (the phase's V5 input-validation control).
- Primary-protection guard ladder in `_supplement_with_asos`: skips cleanly (logs at INFO, returns the Synoptic frame unchanged) when there's no `lat` column, an unresolvable city, duplicate `(city, datetime_utc)` keys, or no ASOS frame survives the fetch loop.

## Task Commits

Each task was committed atomically (TDD RED/GREEN split for Tasks 2 and 3):

1. **Task 1: Confirm two boundary interpretations of locked decisions D-05 and D-03** — no code changes; resolved via continuation context (see Checkpoint Resolution above), recorded here.
2. **Task 2: End-to-end ASOS supplement** — `ea79ba4` (test: RED), `37ce85c` (feat: GREEN)
3. **Task 3: Harden the ASOS path** — `d42a2eb` (test: RED), `74cd64d` (feat: GREEN)

**Plan metadata:** committed alongside this SUMMARY (see final commit).

_Note: both TDD tasks produced a test-only RED commit followed by an implementation GREEN commit, per this project's established TDD convention (no separate refactor commit was needed for either task)._

## Files Created/Modified
- `backend/config.py` — added `ASOS_STATIONS: dict[str, str]` (3-letter IEM FAA codes)
- `backend/asos_provider.py` — new module: `ASOS_BASE`, `ASOS_VARS`, `fetch_asos_1min`, `_to_asos_timestamp`, `_range_check`
- `backend/tests/asos_provider_test.py` — new file, 14 tests (parse/convert/tz/window-shape/import-safety + fail-loud/outage/range/mutation)
- `backend/weather_provider.py` — added `import logging`/`import asos_provider`, module-level `log`, `_supplement_with_asos`, wired into `_fetch_station`; updated module and `fetch_weather` docstrings
- `backend/tests/weather_provider_test.py` — new `test_asos_*` group (12 tests), `_end_to_end_merged_frame` updated to bypass the live ASOS path
- `backend/units_def.py` — fixed a latent NaN-handling bug in `validate_pipeline_row` (see Deviations)

## Decisions Made
- Q1-A / Q2-A (Task 1 checkpoint) — see Checkpoint Resolution above.
- Reused `merge_observations` unmodified for the ASOS union-of-timestamps merge, per `07-RESEARCH.md`'s empirically-verified Pattern 1 — no new merge function was written.
- Used `attach_city(frame, lat=lat, lon=lon)`'s two-keyword form for ASOS frames (the target city is always already known from the per-city fetch loop), rather than resolving from ASOS's own airport-coordinate response fields.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `units_def.validate_pipeline_row`'s NaN-vs-None missing-value check**
- **Found during:** Task 2 (confirming GREEN for `test_asos_supplemented_rows_validate_against_pipeline_schema`)
- **Issue:** The function's "is this field missing" check used Python identity (`value is None`). After a `combine_first` merge/reindex, a legitimately-absent `required: False` field (e.g. an ASOS-only row's `relative_humidity` or `humidity_source`) is pandas' `float('nan')`, not Python `None` — so it fell through to the range/categorical checks and was misreported as `NON-FINITE value` or `UNKNOWN PROVIDER`, even though the field is optional and genuinely absent by design (exactly D-02's intended behavior). This bug pre-dated this plan and had gone undetected through Phase 6, since no prior test exercised a merged row with a real (not just never-created) optional-column gap.
- **Fix:** Broadened the check to `value is None or (isinstance(value, float) and math.isnan(value))`, treating NaN identically to None. As a side effect, this also makes a NaN in a *required* field correctly raise "MISSING" rather than the more confusing "NON-FINITE".
- **Files modified:** `backend/units_def.py`
- **Verification:** Full suite (221 tests) green afterward; no other test relied on the old (incorrect) behavior.
- **Committed in:** `37ce85c` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug)
**Impact on plan:** Necessary for the plan's own explicit `PIPELINE_SCHEMA` validation acceptance criterion on ASOS-only rows. No scope creep — the fix is a one-line generalization that doesn't change behavior for any already-passing case.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None — no external service configuration required. ASOS is unauthenticated and no new `.env` entry was added.

## Next Phase Readiness
- WX-02 closed. `backend/weather_provider.py`'s station path now transparently supplements Synoptic with ASOS 1-minute data for all four project cities.
- `merge_observations`, `_prepare_merge_side`, `attach_provenance`, `attach_city`, and `resolve_station_city` remain byte-unchanged (verified via `git diff` against the pre-Task-2 commit) — Plan 07-02 (Open-Meteo) can build on the same seams with confidence they still behave as Phase 6 specified.
- Full suite: 221 passed, 0 failed (up from the 195-passed Phase 6 baseline — 26 new tests across both implementation tasks).
- Phase 9 (TCEQ-as-primary) will need to revisit `_supplement_with_asos`'s scoping, since it is currently wired only to `provider == "synoptic"` per this phase's locked decision — noted in `07-RESEARCH.md` Open Question 2, not addressed here.

---
*Phase: 07-trivial-integration-providers*
*Completed: 2026-09-12*

## Self-Check: PASSED

All 7 files (created/modified) confirmed present on disk; all 4 task commits (`ea79ba4`, `37ce85c`, `d42a2eb`, `74cd64d`) confirmed present in `git log`.
