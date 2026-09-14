---
phase: 09-tceq-cams-integration
plan: 02
subsystem: weather-ingestion
tags: [tceq, weather-provider, html-scraping, multi-day-decomposition, fail-loud, tdd]

# Dependency graph
requires:
  - phase: 09-tceq-cams-integration
    provides: "Plan 09-01's tracer: TCEQ_BASE, TARGET_LABELS, TCEQ_FIXED_UTC_OFFSET_HOURS, _RETURN_COLUMNS, _fetch_one_day, _validate_response, _hour_labels, _extract_row_values, _range_check, fetch_tceq (single-day), and provider=\"tceq\" wired into weather_provider._fetch_station"
provides:
  - "fetch_tceq serving any window up to 31 calendar days over any of the four config.TCEQ_STATIONS cities, one request per LOCAL calendar day, concatenated/sorted/de-duplicated/reproducible"
  - "TCEQ_MAX_DAYS_PER_FETCH, _to_utc_timestamp, _window_bounds, _days_spanned (local-offset-aware day decomposition, D-09)"
  - "Austin/Midland (no RH row) returning a present, entirely-null relative_humidity column with null humidity_source and no raise (D-04/D-05)"
  - "El Paso's -7 MST offset converting separately from the three -6 CST sites"
  - "The complete fail-loud suite: generic site-selection page, wrong-site <h1>, absent required row (per label), truncated row all raise; RH-only absence and placeholder cells do not"
  - "weather_provider._fetch_station's tceq branch raising on more than one CAMS ID instead of silently taking stids[0]"
affects: [10-synoptic-fallback-and-doc-ratification]

# Actuals (#2632)
actuals:
  tokens: 10212
  tasks: 3
  commits: 6

tech-stack:
  added: []
  patterns:
    - "Local-calendar-day window decomposition: shift each UTC window bound by the site's fixed offset BEFORE taking the date component (_days_spanned), so a window is decomposed by the local day a report actually represents, not by the UTC day the caller happened to write -- a UTC-day-aligned window can legitimately span 2 local calendar days for a non-zero-offset site."
    - "Stable sort (kind=\"stable\") before drop_duplicates(keep=\"first\") wherever \"first wins\" must be deterministic, not merely typical -- pandas' default quicksort is not a stable sort."
    - "Two-branch missing-row disposition: an entirely absent parameter row is either a null column (relative_humidity, D-04) or a raise (the three required fields, D-07) -- implemented and tested as explicitly pinned-against-each-other pairs, never as one collapsed check."
    - "Raise-over-truncate for ambiguous multi-value station requests: a station-path provider whose returned frame carries no per-station discriminator column must reject more than one requested ID rather than silently service only the first."

key-files:
  created: []
  modified:
    - backend/tceq_provider.py
    - backend/tests/tceq_provider_test.py
    - backend/weather_provider.py
    - backend/tests/weather_provider_test.py
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "Used kind=\"stable\" in fetch_tceq's sort_values call (not specified verbatim in the plan's action text, but required for the plan's own reproducibility/dedup-keeps-first must_haves to hold deterministically, since pandas' default quicksort is not stable across ties)."
  - "Updated Plan 09-01's single-day tracer test (test_fetch_tceq_single_day_window_issues_exactly_one_request) rather than deleting it: its premise (one UTC calendar day == one local calendar day) no longer holds once local-offset-aware day decomposition is correct -- CAMS 83's -6 offset means that specific UTC-day window actually spans 2 local days. Renamed and re-asserted to expect 2 requests, with an explanatory comment."
  - "_fetch_station's tceq branch raises on len(stids) != 1 rather than taking stids[0], reversing 09-RESEARCH.md Open Question 1's original recommendation (already flagged as reversed during planning) -- daily_summary.pl serves one site per request and the returned frame carries no station discriminator column."

patterns-established:
  - "_days_spanned(start_ts, end_ts, offset_hours) takes the offset as an argument rather than reaching into the module constant, keeping it a pure date computation any site's offset can drive."

requirements-completed: [WX-01]

coverage:
  - id: D1
    description: "A multi-calendar-day window issues exactly one daily_summary.pl request per calendar day, each carrying that day's own distinct user_month/user_day/user_year, and select_date=user on every call"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_multi_day_window_issues_one_request_per_day"
        status: pass
    human_judgment: false
  - id: D2
    description: "Day-boundary hours are distinct, adjacent (exactly 1 hour apart), never merged or duplicated; the concatenated result is sorted ascending with no duplicate datetime_utc"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_concatenates_days_in_order"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_day_boundary_rows_are_distinct_and_adjacent"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_drops_duplicate_timestamps_keeping_first"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_is_reproducible_for_the_same_window"
        status: pass
    human_judgment: false
  - id: D3
    description: "A window selecting zero rows raises naming the window; a window exceeding TCEQ_MAX_DAYS_PER_FETCH (31) raises naming the day count and cap before any request is issued"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_raises_when_the_window_selects_zero_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_raises_when_the_window_exceeds_the_day_cap"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_accepts_iso_and_bare_date_windows"
        status: pass
    human_judgment: false
  - id: D4
    description: "All four config.TCEQ_STATIONS cities (CAMS 38, 83, 1095, 41) fetch successfully, each returning a frame with the full _RETURN_COLUMNS"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_serves_every_configured_city"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_rejects_a_cams_id_with_no_known_offset"
        status: pass
    human_judgment: false
  - id: D5
    description: "Austin/Midland's absent Relative Humidity row nulls the column without raising; humidity_source stays null on that row via unmodified attach_provenance while wind_source/temp_source read \"tceq\" (D-04/D-05)"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_leaves_rh_null_when_the_site_has_no_rh_row"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_tceq_null_rh_row_has_null_humidity_source"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_tceq_provenance_holds_for_every_configured_city"
        status: pass
    human_judgment: false
  - id: D6
    description: "El Paso's -7 MST offset converts the identical local hour/date one hour later in UTC than the three -6 CST sites"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_applies_the_el_paso_offset_separately"
        status: pass
    human_judgment: false
  - id: D7
    description: "A malformed/unreachable report (generic site-selection form, or a well-formed report whose <h1> names a different CAMS ID than requested) raises rather than parsing to an empty or fabricated frame"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_raises_on_the_generic_site_selection_page"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_raises_when_the_h1_names_a_different_site"
        status: pass
    human_judgment: false
  - id: D8
    description: "Each of Wind Speed/Wind Direction/Outdoor Temperature absent raises naming the CAMS ID and label; Relative-Humidity-only absence does not raise (pinned in the same test group); placeholder (FEW/NA) cells null a value without dropping its row; a row shorter than the header raises"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_raises_when_a_required_row_is_absent"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_omitting_only_relative_humidity_does_not_raise"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_treats_placeholder_cells_as_null"
        status: pass
      - kind: unit
        ref: "backend/tests/tceq_provider_test.py#test_fetch_tceq_raises_when_a_row_is_shorter_than_the_header"
        status: pass
    human_judgment: false
  - id: D9
    description: "fetch_weather with more than one CAMS ID and provider=\"tceq\" raises naming every supplied ID before calling tceq_provider.fetch_tceq; a single-ID call still works"
    requirement: "WX-01"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_tceq_rejects_multiple_cams_ids"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_tceq_accepts_a_single_cams_id_list"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-09-14
status: complete
---

# Phase 9 Plan 2: TCEQ Multi-Day Decomposition, All Four Cities, Fail-Loud Suite Summary

**`fetch_tceq` now serves any window up to 31 days over any of the four CAMS cities via real per-local-calendar-day decomposition, with Austin/Midland's absent humidity nulling cleanly and every unreachable/malformed/missing-field condition raising a specific, named error instead of returning data.**

## Performance

- **Duration:** ~45 min
- **Tasks:** 3 (multi-day decomposition, four-city/offset coverage, fail-loud suite)
- **Files modified:** 5 (`tceq_provider.py`, `weather_provider.py`, two test files, `ACKNOWLEDGEMENTS.md`)

## Accomplishments

- Replaced Plan 09-01's single-UTC-day tracer restriction with real multi-day decomposition: `_to_utc_timestamp`/`_window_bounds` (ported from `nsrdb_provider`) and `_days_spanned`, which shifts each window bound by the site's fixed offset *before* taking the local calendar-date component — so a window is decomposed by the local day a report actually represents, correctly handling the case where a UTC-aligned window spans two local calendar days for a non-zero-offset site.
- Added `TCEQ_MAX_DAYS_PER_FETCH = 31` as a self-imposed pre-request cap (no documented rate limit exists for `daily_summary.pl`), raising before any network call and pointing callers at Open-Meteo (WX-04) for bulk historical backfill.
- Proved all four `config.TCEQ_STATIONS` cities fetch correctly, including Austin/Midland's null-RH handling (D-04) and El Paso's -7 MST offset converting separately from the three -6 CST sites — all already correctly implemented by Plan 09-01's per-day construction logic, confirmed here by dedicated per-city tests rather than assumed.
- Built the complete fail-loud suite required by ROADMAP Success Criterion 4: malformed/wrong-site reports, each of the three required-row absences (pinned against RH-only-absence not raising), placeholder-cell handling, and truncated-row detection.
- Closed 09-RESEARCH.md Open Question 1 in the direction planning committed to: `weather_provider._fetch_station`'s `tceq` branch now raises on more than one requested CAMS ID instead of silently taking `stids[0]`.
- Full suite: 296 → 338 passed (0 failed) across the three tasks, with zero regressions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Multi-day window decomposition, deterministic ordering, and the two window-level raises** — `f97ae6f` (test, RED), `0602404` (feat, GREEN)
2. **Task 2: All four cities, the null-RH sites, and the MST-versus-CST offset split** — `71b9d0d` (test — all behavior already implemented by Task 1, zero further production changes beyond a documentation comment)
3. **Task 3: The fail-loud suite — malformed reports, absent required rows, placeholder cells, and multi-site requests** — `637f424` (test, RED for the multi-ID guard), `5224d87` (feat, GREEN)

**AI-use disclosure:** `86e3f34` (docs — ACKNOWLEDGEMENTS.md, per ECE 464 requirement)

**Plan metadata:** pending (this commit)

## Files Created/Modified

- `backend/tceq_provider.py` — `TCEQ_MAX_DAYS_PER_FETCH`, `_to_utc_timestamp`, `_window_bounds`, `_days_spanned`, and `fetch_tceq` rewritten around a real per-local-calendar-day loop with a stable sort/dedupe sequence and the window-level empty/over-cap raises
- `backend/tests/tceq_provider_test.py` — 30 new tests across the three tasks (multi-day, four-city/offset, fail-loud groups) plus one updated Plan 09-01 tracer test
- `backend/weather_provider.py` — `_fetch_station`'s `tceq` branch now raises on more than one CAMS ID; docstring updates
- `backend/tests/weather_provider_test.py` — 6 new tests (null-RH provenance, four-city provenance parametrization, multi-ID raise, single-ID regression)
- `ACKNOWLEDGEMENTS.md` — session entry per ECE 464's AI-use disclosure requirement

## Decisions Made

- **Stable sort required, not just tidy:** `combined.sort_values("datetime_utc", kind="stable")` — pandas' default quicksort is not stable across ties, and the plan's own "duplicates dropped keep='first' means the earlier-fetched value wins" contract is only deterministic under a stable sort. Not spelled out verbatim in the plan's action text, but required for the plan's own must_haves (reproducibility, dedup-keeps-first) to actually hold rather than pass coincidentally on a given pandas build's tie-break behavior.
- **Local-day-aware `_days_spanned` supersedes a same-instant assumption:** a window naming one UTC calendar day (e.g. `T00:00Z`..`T23:59:59Z`) genuinely spans two local calendar days for any site whose offset is non-zero, since local midnight of the requested day lands at `06:00Z` (CST) or `07:00Z` (MST), not `00:00Z`. This is the intended consequence of D-09's own local-day framing, not a bug — Plan 09-01's single-day tracer test asserting "exactly 1 request" for that specific window was updated (renamed, re-asserted to 2, with an explanatory comment) rather than left contradicting the new correct behavior.
- **`_fetch_station`'s multi-ID guard reverses 09-RESEARCH.md's original recommendation**, per the direction already locked during planning: raising (naming every supplied ID) rather than taking `stids[0]`, since the returned frame carries no per-station discriminator and silently dropping every ID but the first would be undetectable by the caller.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Non-deterministic sort before dedup**
- **Found during:** Task 1 (writing the reproducibility and dedup-keeps-first tests)
- **Issue:** `sort_values("datetime_utc")` without `kind="stable"` uses pandas' default quicksort, which is not guaranteed stable across tied values — the exact case the dedup-keeps-first and reproducibility must_haves depend on.
- **Fix:** Added `kind="stable"` to the sort call in `fetch_tceq`.
- **Files modified:** `backend/tceq_provider.py`
- **Verification:** `test_fetch_tceq_drops_duplicate_timestamps_keeping_first` and `test_fetch_tceq_is_reproducible_for_the_same_window` both pass deterministically.
- **Committed in:** `0602404` (Task 1 GREEN commit)

**2. [Rule 1 - Bug] Superseded tracer test contradicted the new correct local-day decomposition**
- **Found during:** Task 1 (running the full test suite after implementing `_days_spanned`)
- **Issue:** Plan 09-01's `test_fetch_tceq_single_day_window_issues_exactly_one_request` asserted 1 request for a window that, under correct local-offset-aware day decomposition, genuinely spans 2 local calendar days for CAMS 83.
- **Fix:** Renamed the test to `test_fetch_tceq_utc_day_window_issues_one_request_per_spanned_local_day`, updated the assertion to 2, and added a comment explaining why the count changed (not a regression — the old test's premise no longer held).
- **Files modified:** `backend/tests/tceq_provider_test.py`
- **Verification:** Full suite green; the test now documents the correct behavior rather than pinning a since-superseded assumption.
- **Committed in:** `0602404` (Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — bug fixes required for the plan's own must_haves to hold correctly)
**Impact on plan:** Both fixes were necessary for correctness; neither expanded scope beyond what the plan's own must_haves already required.

## Issues Encountered

None beyond the two auto-fixed items above. The `.venv` symlink workaround from Plan 09-01 (worktrees don't check out gitignored directories) was already in place from this worktree's setup and needed no re-creation.

## User Setup Required

None — no external service configuration required. TCEQ's `daily_summary.pl` endpoint remains public and unauthenticated.

## Next Phase Readiness

- WX-01 is now fully proven: all four cities, multi-day windows, and the complete fail-loud surface ROADMAP Success Criterion 4 names.
- `provider="tceq"` is production-ready for Plan 09-03 (if any) or for Phase 10's Synoptic-fallback wiring, which can wrap this raise behavior without needing to change it (D-06's explicit design intent).
- No blockers.

---
*Phase: 09-tceq-cams-integration*
*Completed: 2026-09-14*
