---
phase: 09-tceq-cams-integration
plan: 01
subsystem: weather-ingestion
tags: [bs4, beautifulsoup4, html-scraping, tceq, weather-provider, units_def, tdd]

# Dependency graph
requires:
  - phase: 06-multi-provider-adapter-foundation
    provides: "PIPELINE_SCHEMA v3 provenance columns, attach_provenance, KNOWN_PROVIDER_NAMES (tceq already seeded), fetch_weather's provider-agnostic dispatch shape"
  - phase: 07-asos-open-meteo-integration
    provides: "asos_provider.py as the primary module-shape/range-check analog for a new station-path provider"
provides:
  - "provider=\"tceq\" as a real, working station-path choice on weather_provider._fetch_station, proven end-to-end for Corpus Christi CAMS 83 across one calendar day"
  - "backend/tceq_provider.py: TCEQ_BASE, TARGET_LABELS, TCEQ_FIXED_UTC_OFFSET_HOURS, _RETURN_COLUMNS, _fetch_one_day, _validate_response, _hour_labels, _extract_row_values, _range_check, fetch_tceq"
  - "config.TCEQ_STATIONS: dict[str, str] mapping the four CITY_COORDINATES keys to their research-confirmed CAMS IDs"
  - "beautifulsoup4==4.14.3 pinned in requirements.txt, approved at a blocking human legitimacy checkpoint"
affects: [09-02-tceq-multi-day-and-error-handling]

# Actuals (#2632)
actuals:
  tokens: 8059
  tasks: 3
  commits: 3

tech-stack:
  added: ["beautifulsoup4==4.14.3 (bs4, html.parser backend)"]
  patterns:
    - "HTML-report scraping: _validate_response requires BOTH a site-specific <h1><a href=...CAMS=id> AND a <table border='1'> -- the endpoint answers HTTP 200 for a nonexistent CAMS ID with the generic site-selection form, so status alone is not a trust signal"
    - "Exact (==) row-label matching, never substring, to avoid a table row-collision (\"Wind Direction\" vs \"Resultant Wind Direction\" vs \"Std. Dev. Wind Direction\")"
    - "Fixed-integer (never DST-aware) per-site UTC offset table for timestamp construction"
    - "Header-row-derived hour count (not a hardcoded 24) so a partial-day report's shorter column count aligns correctly"

key-files:
  created:
    - backend/tceq_provider.py
    - backend/tests/tceq_provider_test.py
  modified:
    - backend/config.py
    - backend/weather_provider.py
    - backend/tests/weather_provider_test.py
    - requirements.txt

key-decisions:
  - "Task 1's blocking human legitimacy checkpoint for the bs4/beautifulsoup4 package was pre-resolved by the human before this dispatch: pin beautifulsoup4==4.14.3 (not bs4), since bs4's pypi.org page presents it as a thin alias for the canonical beautifulsoup4 distribution."
  - "Corrected the plan's own Pitfall 8 premise during Task 2: requirements.txt did NOT already contain an unpinned bs4 line (confirmed by reading the file directly) -- the beautifulsoup4 pin is a genuinely new dependency declaration, not a formatting fix."
  - "fetch_tceq's tracer scope resolves the window to exactly one calendar day (UTC-normalized) and raises ValueError naming Plan 09-02 if start/end span more than one day, rather than silently truncating or fetching multiple days."

patterns-established:
  - "tceq_provider.py mirrors asos_provider.py's module shape (docstring contract, import order, fixed constants, _range_check) and nsrdb_provider.py's per-period-loop-then-concat/filter/sort/dedupe/reset_index shape, adapted from per-year to per-calendar-day."

requirements-completed: [WX-01]

coverage:
  - id: D1
    description: "fetch_weather([\"83\"], start, end, provider=\"tceq\") returns a real, unit-converted, fixed-offset, range-checked, \"tceq\"-provenanced Corpus Christi CAMS 83 frame for one calendar day"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_parses_into_pipeline_columns"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_converts_units"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_tceq_station_path_returns_a_provenanced_frame"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_tceq_row_validates_against_pipeline_schema"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every daily_summary.pl request carries select_date=user and a 0-indexed user_month -- the single highest-consequence line in the module"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_request_carries_select_date_user"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_single_day_window_issues_exactly_one_request"
        status: pass
    human_judgment: false
  - id: D3
    description: "datetime_utc is built from a fixed, never-DST-adjusted per-site UTC offset -- a July and a January hour 0000 convert identically"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_applies_fixed_utc_offset_not_dst"
        status: pass
    human_judgment: false
  - id: D4
    description: "Row labels matched exactly (==), never substring -- \"Wind Direction\" is not confused with \"Resultant Wind Direction\" or \"Std. Dev. Wind Direction\""
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_matches_row_labels_exactly"
        status: pass
    human_judgment: false
  - id: D5
    description: "_range_check rejects a converted value that falls outside PIPELINE_SCHEMA's declared range, naming the column and both bounds"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_range_check_rejects_an_unconverted_value"
        status: pass
    human_judgment: false
  - id: D6
    description: "TCEQ is a station provider only -- unreachable from the grid path and from an unknown-provider name on the station path"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_tceq_is_not_reachable_from_the_grid_path"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_tceq_station_path_still_rejects_an_unknown_provider_name"
        status: pass
    human_judgment: false
  - id: D7
    description: "Importing tceq_provider performs no network call, reads no environment variable, and touches no file"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_tceq_provider_import_has_no_side_effects"
        status: pass
    human_judgment: false
  - id: D8
    description: "requirements.txt carries a pinned beautifulsoup4==4.14.3 line, approved at a blocking human legitimacy checkpoint before the first import"
    requirement: "WX-01"
    verification:
      - kind: other
        ref: "grep -c '^beautifulsoup4==4.14.3$' requirements.txt"
        status: pass
    human_judgment: true
    rationale: "The package-legitimacy decision itself (Task 1) is a human judgment call made at a prior dispatch's pypi.org checkpoint, not something a test can re-derive -- recorded here for traceability, not to imply this dispatch performed the judgment."

duration: 20min
completed: 2026-09-14
status: complete
---

# Phase 9 Plan 1: TCEQ CAMS Integration Tracer Summary

**`provider="tceq"` scrapes TCEQ's `daily_summary.pl` HTML report via BeautifulSoup and returns a real, unit-converted, fixed-offset, range-checked, provenance-tagged Corpus Christi CAMS 83 weather frame through the actual `fetch_weather` dispatch.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3 (1 pre-resolved checkpoint, 1 config/pin task, 1 TDD tracer task)
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- Pinned `beautifulsoup4==4.14.3` in `requirements.txt` and added `config.TCEQ_STATIONS` (the four research-confirmed CAMS site IDs), clearing the ground for the first `import bs4` in this codebase.
- Built `backend/tceq_provider.py` end to end: HTML-report validation (rejecting the generic site-selection form TCEQ serves for an invalid CAMS ID at HTTP 200), exact-match row-label extraction, `"FEW"`/`"NA"` placeholder-to-null handling, a fixed never-DST UTC offset per site, `units_def.Q`-based unit conversion, and a range-check backstop.
- Wired `provider="tceq"` into `weather_provider._fetch_station` (no ASOS supplement — that mechanism is Synoptic-specific) and widened the trailing raise to name both implemented station providers.
- Proved the full vertical slice with a real TDD RED→GREEN cycle: 8 new `tceq_provider` tests plus 4 new `weather_provider` dispatch tests, full suite at 308 passed (up from the 296-passed pre-phase baseline), 0 failed.

## Task Commits

Each task was committed atomically:

1. **Task 1: Confirm bs4's legitimacy before the first import lands** — checkpoint pre-resolved by the human in a prior dispatch (approved `beautifulsoup4==4.14.3`); no code produced by this task itself.
2. **Task 2: Pin the HTML-parser dependency and hard-code the four CAMS site IDs** — `96804ce` (feat)
3. **Task 3: End-to-end "TCEQ gives me a real weather row"** — `eea5f63` (test, RED), `1b80bc5` (feat, GREEN)

**Plan metadata:** pending (this commit)

## Files Created/Modified

- `backend/tceq_provider.py` — new module: HTML scraping, unit conversion, fixed-offset UTC timestamps, range check
- `backend/tests/tceq_provider_test.py` — new file: 8 tracer tests (fixture builder, happy path, request contract, offset, label-exactness, range-check backstop, no-side-effects)
- `backend/config.py` — new `TCEQ_STATIONS: dict[str, str]` constant
- `backend/weather_provider.py` — `import tceq_provider`, new `provider == "tceq"` branch in `_fetch_station`, widened trailing raise, docstring updates
- `backend/tests/weather_provider_test.py` — new `test_tceq_*` dispatch group (4 tests)
- `requirements.txt` — new `beautifulsoup4==4.14.3` pinned line

## Decisions Made

- **Task 1 checkpoint resolution (carried in from a prior dispatch):** pin `beautifulsoup4==4.14.3` rather than `bs4==4.14.3` — bs4's pypi.org page presents it as a thin alias for the canonical `beautifulsoup4` distribution, so the canonical name was chosen for the pin.
- **fetch_tceq's tracer scope:** resolves `start`/`end` to a single UTC-normalized calendar day and raises `ValueError` (naming Plan 09-02) if the window spans more than one day, rather than silently truncating to one day or fetching an unbounded range. This keeps the gap loud per the plan's own "no fake multi-day support" instruction.
- **Missing-required-row semantics implemented but not exercised this task:** `fetch_tceq` raises if `wind_speed`, `wind_direction`, or `air_temp`'s row is entirely absent from a report, but treats `relative_humidity`'s absence as an expected null column (D-04) — implemented per the plan's action text for Plan 09-02's Austin/Midland (no-RH) sites to build on, though CAMS 83's fixture always carries all four rows this task, so this branch has no dedicated test yet.

## Deviations from Plan

None — plan executed exactly as written, including the pre-resolved Task 1 checkpoint decision.

One test-naming adjustment made during Task 3 to satisfy the plan's own `<verify>` command: the plan's `<behavior>` section names a test `test_station_path_still_rejects_an_unknown_provider_name`, but the plan's own verify command selects tests with `-k tceq` and requires a floor of 4 passed. A test named without the substring `"tceq"` would not be selected by that filter (pytest's `-k` matches only test/module/class names, not docstring prose), so it was named `test_tceq_station_path_still_rejects_an_unknown_provider_name` instead — same behavior, same assertions, satisfying both the described intent and the literal verify command.

## Issues Encountered

- **No `.venv` present in this git worktree** (worktrees do not check out gitignored/untracked directories). Created a local `.venv` symlink at the worktree root pointing at the main checkout's `/Users/aphan/Documents/Senior_Design/.venv` so the plan's literal `.venv/bin/python ...` verify commands run unmodified. The symlink is itself gitignored (confirmed via `git check-ignore -v .venv`) and was never staged or committed.

## Backlog Observation (not fixed, out of scope per Task 2's own instruction)

`requests` is imported by `backend/asos_provider.py`, `backend/nsrdb_provider.py`, `backend/open_meteo_provider.py`, and now `backend/tceq_provider.py`, but remains undeclared in `requirements.txt`. Adding it would be a new pin requiring its own legitimacy checkpoint and is outside WX-01's scope — recorded here for a future pass, per the plan's own explicit instruction not to fold it into this phase.

## User Setup Required

None — no external service configuration required. TCEQ's `daily_summary.pl` endpoint is public and unauthenticated.

## Next Phase Readiness

- `provider="tceq"` is a working, tested station-path choice for Corpus Christi CAMS 83 across a single calendar day.
- Plan 09-02 can now build on this tracer: real multi-day decomposition (`TCEQ_MAX_DAYS_PER_FETCH`, `_window_bounds`, `_days_spanned`), the three remaining CAMS sites (Austin, Midland — both RH-absent; El Paso — MST offset), and the full fail-loud error-handling surface.
- No blockers. The `relative_humidity`-absent branch in `fetch_tceq` is implemented but untested by this plan — Plan 09-02's Austin/Midland fixtures are the first real exercise of it.

---
*Phase: 09-tceq-cams-integration*
*Completed: 2026-09-14*
