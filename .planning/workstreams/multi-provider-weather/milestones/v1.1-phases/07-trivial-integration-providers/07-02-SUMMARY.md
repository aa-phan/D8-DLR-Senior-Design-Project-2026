---
phase: 07-trivial-integration-providers
plan: 02
subsystem: api
tags: [weather-ingestion, open-meteo, pandas, requests, grid-provider, provenance]

# Dependency graph
requires:
  - phase: 06-multi-provider-adapter-foundation
    provides: "_fetch_grid dispatch stub, attach_provenance/attach_city/merge_observations seams, PIPELINE_SCHEMA v3 provenance columns, KNOWN_PROVIDER_NAMES already containing 'open_meteo'"
  - phase: 07-trivial-integration-providers (plan 01)
    provides: "confirmation that weather_provider.py's Phase 6 seams (merge_observations, attach_provenance, attach_city, resolve_station_city) are byte-unchanged and ready for the grid-side provider"
provides:
  - "backend/open_meteo_provider.py: fetch_open_meteo(lat, lon, start, end) -> PIPELINE_SCHEMA-shaped frame (all 5 weather columns), no-side-effects-on-import"
  - "weather_provider._fetch_grid's provider=='open_meteo' branch -- Phase 6's grid path gets its first real implementation (WX-04)"
affects: [07-03-phase-verification, 09-tceq-primary-wiring]

# Actuals (#2632)
actuals:
  tokens: 7455
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Grid provider module mirrors asos_provider.py's fetch-and-normalize shape (requests.get -> raise_for_status -> JSON-parse guard -> ordered explicit body-shape checks -> pd.to_datetime(utc=True) -> units_def.PIPELINE_SCHEMA range gate), but with no well-formed-empty carve-out: every absence is a failure on this standalone backfill path (D-04/D-05), unlike ASOS's real-outage non-fatal case."
    - "HOURLY_TO_PIPELINE dict is the single source of truth for both the requested `hourly` parameter (via tuple(HOURLY_TO_PIPELINE)) and the response-column mapping, so the request and the parsing cannot drift apart."
    - "_fetch_grid's open_meteo branch performs no merge -- returns the tagged frame directly, since the grid path stands alone as a backfill source (D-04), unlike the station path's transparent ASOS supplement."

key-files:
  created:
    - backend/open_meteo_provider.py
    - backend/tests/open_meteo_provider_test.py
  modified:
    - backend/weather_provider.py
    - backend/tests/weather_provider_test.py
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "Archive API (not Historical Forecast API) selected for the base URL, per 07-RESEARCH.md's discretion-item recommendation (A1) -- 1940-present depth matches WX-04's stated training-volume purpose. Isolated in one module constant (OPEN_METEO_ARCHIVE_BASE) so reversing this is a one-constant change, not a redesign."
  - "Front-loaded Task 2's full ordered body-shape validation, hourly_units echo check, and _fetch_grid null-city raise into Task 1's implementation, since Task 1's own <action> text already specified them in detail. Task 2's tests were then written and all 18 (open_meteo_provider) + 2 (weather_provider) passed with zero further production-code change -- documented as a deviation below, not silently skipped."

patterns-established:
  - "Standalone-backfill fail-loud convention: a grid-only provider with no primary to fall back on treats every absence (missing hourly, empty time, missing/short variable array) as a failure, distinct from a supplement provider's (ASOS) well-formed-empty carve-out. Reusable for any future standalone grid provider."

requirements-completed: [WX-04]

coverage:
  - id: D1
    description: "fetch_weather((lat, lon), start, end, provider='open_meteo') returns a frame carrying all five weather variables from exactly one HTTP request, standardized to PIPELINE_SCHEMA units and tz-aware UTC timestamps"
    requirement: "WX-04"
    verification:
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_returns_all_five_pipeline_columns"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_maps_each_provider_variable_to_its_pipeline_column"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_timestamps_are_tz_aware_utc"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_requests_metres_per_second_wind"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_issues_exactly_one_request"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_open_meteo_grid_fetch_returns_a_validated_provenanced_frame"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every returned row carries open_meteo provenance per field family and a literal city key resolved from the caller's own coordinates, never the provider's snapped grid-cell centre"
    requirement: "WX-04"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_open_meteo_grid_fetch_returns_a_validated_provenanced_frame"
        status: pass
    human_judgment: false
  - id: D3
    description: "The grid path is reachable only with provider='open_meteo'; a grid-shaped location with any other provider (including default 'synoptic') still raises with 'grid' in the message, and the station path never triggers open_meteo_provider"
    requirement: "WX-04"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_open_meteo_is_not_reachable_from_the_station_path"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_open_meteo_grid_path_still_rejects_other_provider_names"
        status: pass
      - kind: integration
        ref: "backend/tests/weather_provider_test.py -k \"dispatch or mock_grid\" (9 tests, zero edits to Phase 6 dispatch tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every Open-Meteo failure mode (missing hourly, empty time, non-JSON body, missing/short variable array, wrong echoed unit, out-of-range value) raises ValueError naming the specific problem -- never padded, truncated, or null-columned"
    requirement: "WX-04"
    verification:
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_raises_when_hourly_is_missing"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_raises_when_the_time_array_is_empty"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_raises_when_the_body_is_not_json"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_raises_when_a_variable_array_is_missing"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_raises_when_a_variable_array_is_short"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_raises_when_the_echoed_wind_unit_is_wrong"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_raises_when_a_value_is_out_of_schema_range"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_propagates_an_http_error"
        status: pass
    human_judgment: false
  - id: D5
    description: "Ordering, adjacency, and concurrency guarantees hold: single-hour window returns one row, output is monotonic and reproducible, an exactly-equal (city, datetime_utc) key merges with the station side winning, no module-level mutable state or input mutation"
    requirement: "WX-04"
    verification:
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_returns_one_row_for_a_single_hour_window"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_output_is_ordered_and_reproducible"
        status: pass
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_fetch_open_meteo_does_not_mutate_module_state"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_open_meteo_row_merges_with_a_station_row_at_an_exactly_equal_key"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_open_meteo_grid_fetch_raises_on_unresolvable_coordinates"
        status: pass
    human_judgment: false
  - id: D6
    description: "Importing open_meteo_provider.py performs no network call and reads no environment variable -- no API key, no token, no new .env entry"
    requirement: "WX-04"
    verification:
      - kind: unit
        ref: "backend/tests/open_meteo_provider_test.py#test_module_import_has_no_side_effects"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-09-12
status: complete
---

# Phase 7 Plan 2: Open-Meteo Historical Backfill Summary

**Phase 6's grid path (`_fetch_grid`) gets its first real implementation: `fetch_weather((lat, lon), start, end, provider="open_meteo")` now returns all five weather variables from a single Archive API request, standardized to `PIPELINE_SCHEMA` units with tz-aware UTC timestamps and `open_meteo` provenance, closing WX-04.**

## Performance

- **Duration:** ~15 min (first RED commit to last GREEN commit)
- **Started:** 2026-09-12T07:47:23Z
- **Completed:** 2026-09-12T08:02:00Z
- **Tasks:** 2 (both TDD, one a tracer)
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- New `backend/open_meteo_provider.py`: `fetch_open_meteo(lat, lon, start, end)` issues exactly one `requests.get` against Open-Meteo's Archive API (`archive-api.open-meteo.com/v1/archive`), requesting `wind_speed_unit=ms` so no wind conversion step is needed, and parses the response with `pd.to_datetime(..., utc=True)` explicitly since the provider's ISO strings carry no offset suffix even for a UTC request (RESEARCH.md Pitfall 3).
- `HOURLY_TO_PIPELINE` is the single source of truth for both the requested `hourly` parameter (`OPEN_METEO_HOURLY_VARS = tuple(HOURLY_TO_PIPELINE)`) and the response-to-column mapping, so the request and the parsing cannot silently drift apart.
- Full fail-loud body-shape validation, in order: `hourly` present and a dict; `time` present, a list, non-empty; each of the five mapped variable arrays present and length-matched to `time` — each check raises `ValueError` naming the specific key, never padding, truncating, or substituting a null column. A `hourly_units` echo check catches a dropped/ignored unit request parameter, and `_range_check` (mirroring `asos_provider._range_check`) reads bounds from `units_def.PIPELINE_SCHEMA` as the final gate.
- `weather_provider._fetch_grid`'s `provider == "open_meteo"` branch: `attach_provenance`/`attach_city` from the caller's own coordinates (never the provider's snapped grid-cell centre), no merge performed since the grid path stands alone as a backfill source (D-04), and a `ValueError` naming the coordinates when they don't resolve to a known city — an unmergeable row is never emitted.
- Every other provider name on the grid path still raises `ValueError` containing the literal word `grid` (the two Phase 6 tests this depends on pass unchanged), and the station path never reaches `open_meteo_provider`.

## Tracer Feedback Gate (Task 1 → Task 2)

Task 1 is `type="tracer"`. Per the workflow's tracer feedback gate, `<verify>` was re-run end-to-end before starting Task 2 rather than expanding on an unproven slice: `human_verify_mode` is `end-of-phase` (config default) and Task 1's `<verify>` block is fully automated (no manual step), so the gate resolved to "re-run, passes, continue" with no checkpoint raised. `AUTO_CHAIN`/`AUTO_CFG` were both `false` this session (interactive, not auto-mode) — the automated-only branch of the gate still applies since the verify block itself has no manual step.

## Task Commits

Each task's TDD RED/GREEN split was committed atomically:

1. **Task 1: End-to-end Open-Meteo grid fetch** — `dc32106` (test: RED), `3962427` (feat: GREEN)
2. **Task 2: Fail-loud, ordering, and adjacency guarantees** — `794151a` (test: RED/GREEN combined — see Deviations)

**Plan metadata:** committed alongside this SUMMARY (see final commit).

## Files Created/Modified
- `backend/open_meteo_provider.py` — new module: `OPEN_METEO_ARCHIVE_BASE`, `HOURLY_TO_PIPELINE`, `OPEN_METEO_HOURLY_VARS`, `EXPECTED_HOURLY_UNITS`, `fetch_open_meteo`, `_to_archive_date`, `_range_check`
- `backend/tests/open_meteo_provider_test.py` — new file, 18 tests (happy path/mapping/tz/units/single-request/ISO-date-window + fail-loud/ordering/adjacency/no-mutation)
- `backend/weather_provider.py` — added `import open_meteo_provider`, `_fetch_grid`'s `provider == "open_meteo"` branch, updated module and `fetch_weather` docstrings
- `backend/tests/weather_provider_test.py` — new `test_open_meteo_*` dispatch group (5 tests: provenanced fetch, station-path isolation, other-provider rejection, adjacency merge, unresolvable-coordinate raise)
- `ACKNOWLEDGEMENTS.md` — disclosed this session's AI-assisted work per ECE 464 policy

## Decisions Made
- Archive API selected over Historical Forecast API for `OPEN_METEO_ARCHIVE_BASE`, per `07-RESEARCH.md`'s discretion-item recommendation (A1) — 1940-present depth better matches WX-04's stated C9/C10 training-volume purpose. Isolated in one module constant so reversing this later is a one-line change, not a redesign.
- Reused `attach_provenance`/`attach_city` unmodified from Phase 6, per `07-RESEARCH.md` Pattern 2 — no new city-resolution or provenance-tagging logic was written.

## Deviations from Plan

### Notable: Task 2 required no new production code

**What happened:** Task 1's `<action>` text (as written in `07-02-PLAN.md`) already specified, in detail, the full ordered body-shape validation (missing/empty `hourly`, missing/short variable arrays), the `hourly_units` echo check, and the `_range_check` gate — these were implemented during Task 1 rather than deferred to Task 2, since Task 1's own action text required them for its acceptance criteria (`.venv/bin/python -m pytest -q` reporting 0 failed, which needs the JSON-parse guard and body-shape checks to exist for any malformed-response test in the suite to pass safely). `_fetch_grid`'s unresolvable-coordinate raise was likewise added during Task 1, since leaving a null-city row reachable would have violated Task 1's own "returns a validated provenanced frame" acceptance criterion the moment a real caller passed bad coordinates.

**Consequence:** When Task 2's 11 new `open_meteo_provider` tests and 2 new `weather_provider` tests were written and run to confirm RED, all 18 + 2 already passed with zero further production-code change. This was manually verified (not assumed) by reading each new test against the actual Task-1 implementation before committing — e.g., confirming `_range_check` genuinely raises for an out-of-schema wind value (not vacuously passing due to a fixture bug), and that the `_fetch_grid` null-city guard was real code, not a coincidentally-matching side effect. No plan acceptance criterion was left unimplemented; the plan's full acceptance-criteria list for both tasks was independently checked line-by-line against the final code, not just against test-pass/fail counts.

**Files affected:** `backend/tests/open_meteo_provider_test.py`, `backend/tests/weather_provider_test.py` (test-only; no production file touched by "Task 2").

**Committed in:** `794151a` (a single `test(...)` commit, since there was no GREEN state to reach separately).

---

**Total deviations:** 1 (process note — no Rule 1/2/3/4 auto-fix was needed; documented for transparency about the RED/GREEN split not landing in the expected two-commit shape).
**Impact on plan:** None on scope or correctness — every one of Task 2's stated acceptance criteria is met, verified against actual code rather than accepted on faith from a passing test count.

## Issues Encountered

Two test-fixture bugs of the executor's own making (not production-code defects), both caught and fixed by the production code's own gates behaving correctly against a badly-constructed fixture:
- `_archive_payload`'s synthetic `time` array generated an invalid `"...T24:00"` hour string once a test requested more than 24 rows (`n_hours=48`, for the single-request counting test) — fixed by building times via `pd.date_range(...).strftime(...)` instead of a raw `f"T{h:02d}:00"` format string that never wrapped past hour 23.
- The same fixture's monotonically-increasing synthetic `air_temp`/`wind_speed`/etc. values exceeded `PIPELINE_SCHEMA`'s declared range at `n_hours=48` — fixed by wrapping the synthetic per-hour offset with `% 10` so values cycle within range regardless of how many hours a given test requests.

## User Setup Required

None — no external service configuration required. Open-Meteo is unauthenticated and no new `.env` entry was added (ROADMAP Success Criterion 4).

## Next Phase Readiness

- WX-04 closed. `backend/weather_provider.py`'s grid path now has its first real implementation (`provider="open_meteo"`), returning the full temp/wind/solar/RH variable set standardized to `PIPELINE_SCHEMA`.
- `merge_observations`, `attach_provenance`, `attach_city`, and `resolve_station_city` remain byte-unchanged (confirmed by `git diff` scope: `backend/weather_provider.py`'s edits are confined to the import block, `_fetch_grid`, and the two docstrings) — Plan 07-03 (phase verification/wrap-up) can rely on both Phase 7 providers sitting on the same unmodified Phase 6 seams.
- Full suite: 244 passed, 0 failed (up from the 221-passed Plan 07-01 baseline — 23 new tests: 18 in `open_meteo_provider_test.py`, 5 in `weather_provider_test.py`).
- The Archive-vs-Historical-Forecast API discretion choice (Archive API) is recorded in `PROJECT.md`'s Key Decisions table implicitly via this SUMMARY and `07-RESEARCH.md` A1 — no separate ADR was requested by `07-CONTEXT.md` for this item.

---
*Phase: 07-trivial-integration-providers*
*Completed: 2026-09-12*

## Self-Check: PASSED

All 5 files (created/modified) confirmed present on disk; all 3 task commits (`dc32106`, `3962427`, `794151a`) confirmed present in `git log`.
