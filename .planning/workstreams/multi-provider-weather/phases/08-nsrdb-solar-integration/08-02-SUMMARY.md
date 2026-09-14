---
phase: 08-nsrdb-solar-integration
plan: 02
subsystem: api
tags: [weather-ingestion, nsrdb, solar-irradiance, pandas, requests, grid-provider, provenance, credentials, error-handling]

# Dependency graph
requires:
  - phase: 08-nsrdb-solar-integration
    provides: "08-01: backend/nsrdb_provider.py's single-year fetch_nsrdb tracer, the longitude-first _wkt_point swap, credential fail-loud helpers, and the provider='nsrdb' branch in weather_provider._fetch_grid"
provides:
  - "backend/nsrdb_provider.py: fetch_nsrdb(lat, lon, start, end) now decomposes an arbitrary window (including one crossing a calendar-year boundary) into one request per spanned year, concatenates/filters/de-duplicates the result, and raises on a window that selects zero rows"
  - "NSRDB_FIRST_COVERED_YEAR (local lower-bound guard, no matching upper bound) and NSRDB_ACCEPTED_GHI_UNITS (a normalized, permissive accepted-spelling set for the unresolved GHI-units assumption)"
  - "_raise_for_nsrdb_error: dual-shape (JSON errors-array / raw CSV) non-2xx handler with _redact-based credential redaction, wired into the year loop immediately after each request"
  - "Cross-provider proof that D-02's solar-only provenance guarantee (null wind/temp/humidity, solar_source='nsrdb') holds through a real merge_observations call against a station frame"
affects: [08-03-live-credential-verification, 10-fallback-wiring]

# Actuals (#2632) -- pairs with the plan's estimate to calibrate future estimates.
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 9455
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Year-scoped endpoint decomposition: _window_bounds resolves the caller's [start, end] into UTC timestamps (bare-date end widened to the whole day, mirroring open_meteo_provider._to_archive_date's tz coercion), _years_spanned turns that into the request-year list with a local lower-bound-only guard, and fetch_nsrdb loops one request per year, concatenating/filtering/de-duplicating afterward. Generalizable to any future year-scoped (rather than range-scoped) endpoint."
    - "Dual-shape error dispatch: _raise_for_nsrdb_error attempts response.json() and catches ValueError (json.JSONDecodeError's base class) to fall back to the raw body, so a non-JSON error shape never surfaces a confusing decode error in place of the real provider text. Only the extracted 'errors' entry is quoted into the exception message, never the whole echoed-request object, and every extracted fragment passes through _redact before reaching the message."
    - "Permissive-but-present unit checks for an unverified assumption: NSRDB_ACCEPTED_GHI_UNITS is normalized (stripped/lower-cased/space-collapsed) and compared to a normalized echoed value, skipped entirely (not failed) when the metadata field is absent -- matching open_meteo_provider's established skip-when-omitted convention for an echoed unit check that live verification could not fully pin down."

key-files:
  created: []
  modified:
    - backend/nsrdb_provider.py
    - backend/tests/nsrdb_provider_test.py
    - backend/tests/weather_provider_test.py
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "_raise_for_nsrdb_error extracts only the JSON body's 'errors' entry, never the whole parsed object, before it is quoted (redacted) into an exception message -- the rest of NSRDB's live-documented error body is the echoed request 'inputs' object, which itself contains api_key/email, so quoting the whole object would multiply the redaction surface for no diagnostic gain."
  - "No raise_for_status() call anywhere in the module (carried forward from Plan 08-01, re-enforced here by a source gate): its HTTPError embeds the full request URL, and api_key/email are query parameters on every NSRDB request."
  - "The units-metadata check is deliberately permissive on casing/spacing rather than pinned to one literal spelling, because 08-RESEARCH.md's Assumption A2 could not be confirmed without a real key -- a real success body was never obtained live. _range_check remains the independent backstop that would still catch a magnitude-scale unit error even if this check is wrong or absent."
  - "Test-file split: split what would have been one interleaved edit into two clean RED/GREEN commit pairs per task by reverting and reapplying test-file changes incrementally, so each commit's diff matches exactly one task's scope rather than mixing Task 1 and Task 2 test additions in a single commit."

patterns-established:
  - "Year-boundary test fixtures with rows deliberately outside the requested window on both sides (_year_boundary_fixtures), so a filtering assertion (len(frame) < total_rows_supplied) proves the filter actually ran rather than trivially holding on an all-inside fixture. Reusable for any future window-filtering test in this codebase."

requirements-completed: [WX-03]

coverage:
  - id: D1
    description: "A window crossing a calendar-year boundary issues one request per spanned year (recorded names values in ascending order), concatenates the per-year frames into one monotonically increasing, duplicate-free frame, and filters it down to the caller's actual [start, end] window; a window inside one calendar year still issues exactly one request"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_issues_one_request_per_calendar_year"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_still_issues_one_request_for_a_single_year_window"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_concatenates_year_chunks_into_one_ordered_frame"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_filters_the_concatenated_frame_to_the_requested_window"
        status: pass
    human_judgment: false
  - id: D2
    description: "A bare calendar-date end argument covers that whole day (24 hourly rows), while the same date written as an explicit midnight instant selects only that one row"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_treats_a_bare_date_end_as_the_whole_day"
        status: pass
    human_judgment: false
  - id: D3
    description: "A request for a year before NSRDB_FIRST_COVERED_YEAR (2018) raises ValueError naming both years with zero network calls; a future year is never rejected locally; a window selecting zero rows after filtering raises rather than returning an empty frame"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_raises_for_a_year_before_the_products_first_covered_year"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_does_not_locally_reject_a_future_year"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_raises_when_the_window_selects_no_rows"
        status: pass
    human_judgment: false
  - id: D4
    description: "Both NSRDB error-body shapes (JSON errors-array, raw CSV Error Code/Error Message) raise a clear ValueError rather than a JSON-decode error, detection depends only on status + generic shape (never a specific NREL wording), and a 429 raises naming the status"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_raises_on_json_error_body"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_raises_on_csv_error_body"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_error_detection_does_not_depend_on_a_specific_wording"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_raises_on_a_rate_limited_response"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_stops_at_the_first_failing_year"
        status: pass
    human_judgment: false
  - id: D5
    description: "No credential value (API key or contact email) ever appears in a raised error message, even when the response body echoes both back; the redaction placeholder appears in its place"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_error_message_redacts_the_api_key_and_email"
        status: pass
    human_judgment: false
  - id: D6
    description: "The response's GHI Units metadata field is checked against a normalized accepted set when present (an unexpected value raises naming the echoed value; every documented spelling plus casing/spacing variants parse cleanly) and skipped entirely when absent"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_raises_when_the_ghi_units_metadata_is_unexpected"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_accepts_the_documented_ghi_unit_spellings"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_skips_the_units_check_when_the_metadata_field_is_absent"
        status: pass
    human_judgment: false
  - id: D7
    description: "An NSRDB-sourced row's wind_source, temp_source, and humidity_source are null while solar_source reads 'nsrdb', and merging an NSRDB solar row with a station wind/temp row at an exactly equal (city, datetime_utc) key produces one row with each field attributed to its actual supplier"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_row_leaves_wind_temp_and_humidity_provenance_null"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_solar_merges_with_a_station_row_at_an_exactly_equal_key"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-09-13
status: complete
---

# Phase 8 Plan 2: NSRDB Year-Chunking and Error Handling Summary

**`fetch_nsrdb` now decomposes any `[start, end]` window — including one crossing a calendar-year boundary — into per-year requests, reassembles them into one ordered/de-duplicated frame, and raises a credential-redacted `ValueError` for either of NSRDB's two structurally different error-body shapes, closing the general-case half of WX-03.**

## Performance

- **Duration:** ~6 min (first RED commit to last GREEN commit)
- **Started:** 2026-09-13T02:33:22-05:00
- **Completed:** 2026-09-13T02:38:50-05:00
- **Tasks:** 2 (both TDD)
- **Files modified:** 4 (3 source/test files + ACKNOWLEDGEMENTS.md)

## Accomplishments
- `_window_bounds(start, end)` resolves a caller's window to tz-aware UTC timestamps, widening a bare-date `end` (no `T`, no `:`) to the last microsecond of that calendar day so a single-day window returns the same 24 hourly rows Phase 7 confirmed live for Open-Meteo — while `start` is never widened this way.
- `_years_spanned(start_ts, end_ts)` turns a resolved window into the ascending list of calendar years to request, raising `ValueError` naming both the offending year and `NSRDB_FIRST_COVERED_YEAR` (2018) before any network call when a spanned year precedes the product's coverage — and deliberately carries no matching upper-bound constant, since NREL/NLR's most recently covered year advances over time and a local ceiling would reject a year that now exists.
- `fetch_nsrdb`'s body is now a loop over `_years_spanned`, building the same per-request parameter dict Plan 08-01 established (credentials looked up once outside the loop), concatenating the per-year frames, filtering to the resolved bounds inclusive, sorting by `datetime_utc`, and dropping any duplicate timestamp at a year seam (first occurrence wins). A filtered result of zero rows raises `ValueError` naming both bounds rather than returning a well-formed emptiness a caller could mistake for night-time (07-CONTEXT.md D-05).
- `_raise_for_nsrdb_error(response, year, *secrets)` handles both of NSRDB's live-documented error-body shapes: a JSON object carrying `status`/`errors` for a parameter-validation failure, and a raw `Error Code,Error Message` CSV body for a missing/invalid key. It attempts `response.json()` and falls back to the raw body on the resulting `ValueError` (`json.JSONDecodeError`'s base class), extracts only the `errors` entry — never the whole echoed-request object — and passes every extracted fragment through `_redact` before it reaches the exception message. Detection matches on status + the generic shape only, never a specific NREL wording, since the exact out-of-range-year text could not be isolated without a real key.
- `_redact(text, *secrets)` replaces every non-empty credential value with a fixed placeholder; wired into `_raise_for_nsrdb_error` with both `api_key` and the contact email as secrets, so neither ever reaches a log line or a traceback even though NSRDB's JSON error body echoes both back in its `inputs` object.
- `NSRDB_ACCEPTED_GHI_UNITS` (a normalized, casing/spacing-permissive set) and a new check inside `_parse_psm4_csv` validate the response's echoed `GHI Units` metadata field when present and skip the check entirely when absent — matching `open_meteo_provider`'s established skip-when-omitted convention for an echoed unit check research could not fully confirm (Assumption A2). `_range_check` remains the independent magnitude-scale backstop regardless.
- Two new `weather_provider_test.py` tests prove D-02's solar-only provenance guarantee holds through `fetch_weather` and through a real `merge_observations` call against a station frame — with zero production change to `weather_provider.py`, confirming Phase 6's existing `attach_provenance`/`merge_observations` mechanism already provides this guarantee for a solar-only frame.

## Task Commits

Each task was committed as a RED/GREEN pair:

1. **Task 1: Decompose the window into per-year requests and reassemble it** — `4c642ab` (test: RED), `061f1a2` (feat: GREEN)
2. **Task 2: Handle both error-body shapes without leaking the credential, and prove the solar-only provenance holds through a merge** — `90f5e88` (test: RED), `bbae88c` (feat: GREEN)

**Plan metadata:** committed alongside this SUMMARY (see final commit).

## Files Created/Modified
- `backend/nsrdb_provider.py` — added `NSRDB_FIRST_COVERED_YEAR`, `NSRDB_ACCEPTED_GHI_UNITS`, `_REDACTED_PLACEHOLDER`, `_window_bounds`, `_years_spanned`, `_redact`, `_raise_for_nsrdb_error`; rewrote `fetch_nsrdb`'s body into the year-loop/concatenate/filter/de-duplicate shape; extended `_parse_psm4_csv` with the GHI-units metadata check
- `backend/tests/nsrdb_provider_test.py` — extended `_mock_get`/`_psm4_csv`/`_FakeResponse` fixtures (per-year response dispatch, `ok`/`status_code`, a `json()` method); added 16 new tests across the year-chunking and error-handling groups (36 total in the file, up from 20)
- `backend/tests/weather_provider_test.py` — added 2 new `test_nsrdb_*` tests proving D-02's provenance guarantee through `fetch_weather` and a real cross-provider merge (6 nsrdb-named tests total in the file, up from 4)
- `ACKNOWLEDGEMENTS.md` — disclosed this session's AI-assisted work per ECE 464 policy

## Decisions Made
- `_raise_for_nsrdb_error` extracts only the JSON body's `errors` entry, never the whole parsed object, before redaction — the rest of the live-documented error body is the echoed request `inputs` object, which itself contains `api_key`/`email`, so quoting the whole object would multiply the redaction surface for no diagnostic gain.
- The GHI-units check is deliberately permissive on casing/spacing rather than pinned to one literal spelling, since 08-RESEARCH.md's Assumption A2 (exact response unit spelling) could not be confirmed without a real key — a real success body was never obtained live during research. `_range_check` remains the independent backstop.
- No `raise_for_status()` call anywhere in the module (carried forward from Plan 08-01, re-enforced here by a source gate in the verify step): its `HTTPError` embeds the full request URL, and `api_key`/`email` are query parameters on every NSRDB request.
- Split what would have been one interleaved test-file edit into two clean RED/GREEN commit pairs per task, by reverting and reapplying the test-file changes incrementally, so each task's commits carry exactly that task's diff rather than mixing Task 1 and Task 2 additions together.

## Deviations from Plan

### Notable: two verify-script test-count floors did not exactly match, without indicating a defect

**1. [Process note] `weather_provider_test.py -k nsrdb` selected 6 tests, one short of the plan's stated 7-test floor**
- **Found during:** Task 2 verification
- **Issue:** The plan's `<verify>` block states `fewer than 7 tests selected` as the failure condition for `pytest backend/tests/weather_provider_test.py -q -k nsrdb`. The plan's own `<behavior>` section for this task specifies exactly 2 new `weather_provider_test.py` tests (`test_nsrdb_row_leaves_wind_temp_and_humidity_provenance_null`, `test_nsrdb_solar_merges_with_a_station_row_at_an_exactly_equal_key`), both of which were written and pass. Combined with the 4 nsrdb-named tests already present from Plan 08-01, the file has exactly 6 tests whose name contains "nsrdb" — one short of the stated floor.
- **Investigation:** Re-read the plan's `<behavior>` text twice to confirm no third `weather_provider_test.py` test was specified for this task, and re-ran `-k nsrdb` after GREEN to confirm the count is stable at 6, not a collection artifact. All 6 pass; no test was skipped or silently dropped.
- **Assessment:** This reads as a planning-time overcount (the planner's estimate of "7" does not match its own itemized `<behavior>` list), not a missing test. Every acceptance criterion and coverage item this plan specifies for D-02's provenance guarantee is met and verified (see coverage D7 above). No production or test-authoring gap was found.
- **Files affected:** None — no fix applied, since there was nothing to fix; documented here per this project's TDD fail-fast convention of investigating rather than silently reconciling an unexpected number.
- **Committed in:** Not applicable (investigation only, no code change).

**2. [Process note] Several new assertions coincidentally passed before their task's GREEN implementation**
- **Found during:** RED confirmation for both Task 1 and Task 2
- **Issue:** Task 1's `test_fetch_nsrdb_still_issues_one_request_for_a_single_year_window`, `test_fetch_nsrdb_filters_the_concatenated_frame_to_the_requested_window`, and `test_fetch_nsrdb_does_not_locally_reject_a_future_year` passed against Plan 08-01's pre-existing single-year implementation (which already issued one request and never checked an upper year bound). Task 2's `test_fetch_nsrdb_raises_on_csv_error_body`, `test_fetch_nsrdb_error_detection_does_not_depend_on_a_specific_wording`, `test_fetch_nsrdb_accepts_the_documented_ghi_unit_spellings`, and `test_fetch_nsrdb_skips_the_units_check_when_the_metadata_field_is_absent` passed because the pre-existing `_parse_psm4_csv`'s "fewer than 3 lines" guard happened to also raise `ValueError` on a single-line JSON error body, and because no units check existed yet to reject anything.
- **Consequence:** Per this project's TDD fail-fast convention (a test passing unexpectedly during RED must be investigated, not silently accepted), each was individually re-checked after GREEN to confirm it now exercises the intended production code path (e.g., confirming the CSV-error-body test now raises from `_raise_for_nsrdb_error`'s CSV fallback branch rather than coincidentally from `_parse_psm4_csv`'s line-count guard) rather than continuing to pass for the wrong reason. All were confirmed correct post-GREEN.
- **Files affected:** None — no production or test change resulted from this investigation; documented for transparency.
- **Committed in:** Not applicable (investigation only).

---

**Total deviations:** 2 process notes (no Rule 1/2/3/4 auto-fix was needed — both plan acceptance criteria and every coverage item are met as specified).
**Impact on plan:** None on scope or correctness. Both notes are transparency records of verification discrepancies investigated and resolved as non-issues, not defects requiring a fix.

## Issues Encountered

One executor-side test-organization issue, not a production-code defect: the first draft of the test-file edits interleaved Task 1 and Task 2 additions into a single `Write`/`Edit` pass per file, which would have produced commits that did not cleanly separate each task's RED/GREEN diff. Resolved by reverting both test files to their pre-plan state (`git checkout --`) and reapplying the changes incrementally — Task 1's helper extensions and tests first, confirmed RED, implemented, confirmed GREEN, committed; then Task 2's additions on top, following the same RED/GREEN sequence — so each of the four commits in this plan carries exactly one task's scope.

## User Setup Required

None for this plan — every new test mocks `requests.get`, so no `NREL_API_KEY`/`NREL_API_EMAIL` value was needed to execute or verify this plan. Both env vars remain required before Plan 08-03's live-credential checkpoint can run; per `.planning/STATE.md`'s carried blocker, the key registration itself is still not confirmed complete as of this plan's execution.

## Next Phase Readiness
- Plan 08-03 (live credential verification) can proceed directly against this plan's `fetch_nsrdb`: the full window contract (year-chunking, bare-date handling, coverage guard, dual-shape error handling, redaction, units check) is now implemented and tested with mocks. Plan 08-03's live checkpoint is the point at which the two genuinely unresolved research assumptions (exact `GHI Units` spelling, exact out-of-range-year error wording) get their first real-key confirmation.
- The plan's own `must_haves.prohibitions` entries (multi-year silent truncation, unredacted credential in an exception message, wording-coupled error detection) are all `status: unverified` / `verification: flagged-unverified` in the plan frontmatter — meaning the plan author flagged them as needing confirmation beyond automated test coverage. This plan's test suite (`test_fetch_nsrdb_filters_the_concatenated_frame_to_the_requested_window`, `test_fetch_nsrdb_error_message_redacts_the_api_key_and_email`, `test_fetch_nsrdb_error_detection_does_not_depend_on_a_specific_wording`) directly exercises all three, so the automated half of that verification is in place; only the "confirmed against a real key/live response" half remains, and that is explicitly Plan 08-03's scope.
- No blockers introduced by this plan. The carried blocker (NREL key registration status) remains open and is Plan 08-03's concern, not this one's.

---
*Phase: 08-nsrdb-solar-integration*
*Completed: 2026-09-13*

## Self-Check: PASSED

- FOUND: backend/nsrdb_provider.py
- FOUND: backend/tests/nsrdb_provider_test.py
- FOUND: backend/tests/weather_provider_test.py
- FOUND: .planning/phases/08-nsrdb-solar-integration/08-02-SUMMARY.md
- FOUND: ACKNOWLEDGEMENTS.md
- FOUND commit: 4c642ab (test: Task 1 RED)
- FOUND commit: 061f1a2 (feat: Task 1 GREEN)
- FOUND commit: 90f5e88 (test: Task 2 RED)
- FOUND commit: bbae88c (feat: Task 2 GREEN)
- FOUND commit: b79565e (docs: SUMMARY + ACKNOWLEDGEMENTS)
