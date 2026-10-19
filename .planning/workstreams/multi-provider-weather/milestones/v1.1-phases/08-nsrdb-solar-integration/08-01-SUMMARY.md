---
phase: 08-nsrdb-solar-integration
plan: 01
subsystem: api
tags: [weather-ingestion, nsrdb, solar-irradiance, pandas, requests, grid-provider, provenance, credentials]

# Dependency graph
requires:
  - phase: 06-multi-provider-adapter-foundation
    provides: "_fetch_grid dispatch stub, attach_provenance/attach_city/merge_observations seams, PIPELINE_SCHEMA v3 provenance columns, KNOWN_PROVIDER_NAMES already containing 'nsrdb'"
  - phase: 07-trivial-integration-providers
    provides: "open_meteo_provider.py as the fetch-and-normalize module shape this plan mirrors (fixed-constant base URL, _range_check pattern, no-side-effects-on-import contract, _fetch_grid's provider== branch shape)"
provides:
  - "backend/nsrdb_provider.py: fetch_nsrdb(lat, lon, start, end) -> ['datetime_utc', 'solar_radiation'] frame for a window inside one calendar year, credential lookup (NREL_API_KEY/NREL_API_EMAIL) fails loud with EnvironmentError before any network call"
  - "weather_provider._fetch_grid's provider=='nsrdb' branch -- the grid path's second real implementation (WX-03), alongside open_meteo"
  - "The longitude-first _wkt_point coordinate swap, isolated in one named function and pinned by a literal-string test plus a four-city sign test"
affects: [08-02-nsrdb-year-chunking-and-error-handling, 08-03-live-credential-verification, 10-fallback-wiring]

# Actuals (#2632) -- pairs with the plan's estimate to calibrate future estimates.
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 7917
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "NSRDB module mirrors open_meteo_provider.py's shape (fixed-constant base URL, _range_check reading units_def.PIPELINE_SCHEMA, no-side-effects-on-import), but keeps both credential lookups as the first two statements inside the fetch function rather than at module level, so the module stays importable on a machine with no key (D-01's structural requirement)."
    - "The one lat/lon-swap defect this phase exists to prevent is isolated in a single named function (_wkt_point) rather than inline in the parameter dict, so there is exactly one place in the codebase where the order is decided and exactly one place a test has to pin."
    - "_parse_psm4_csv checks the literal data-column header against the expected column list before ever calling pd.read_csv, so a non-CSV body (HTML error page, redirect) cannot silently 'look parseable' -- generalizable to any future CSV-returning provider."
    - "No .raise_for_status() call on the NSRDB response: requests' HTTPError embeds the full request URL (which carries api_key and email as query parameters) in its exception message, so calling it would leak both credentials into any uncaught-exception log. The response body is handed straight to the parse guard instead."

key-files:
  created:
    - backend/nsrdb_provider.py
    - backend/tests/nsrdb_provider_test.py
  modified:
    - backend/weather_provider.py
    - backend/tests/weather_provider_test.py
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "Credential-absent exception type is EnvironmentError, never ValueError -- matches dlr_pipeline._token()'s actual (research-verified) exception type and keeps 'this machine is misconfigured' on a different branch from 'this provider sent something wrong', per 08-CONTEXT.md's discretion note as corrected by 08-RESEARCH.md."
  - "No .raise_for_status() call on the NSRDB response -- deliberately, since the HTTPError it would raise embeds the full request URL (api_key and email as query parameters) in its own message. The response body is parsed directly instead, and _parse_psm4_csv's error messages only ever quote the (credential-free) response body, never the request."
  - "Task 2's 8 new tests all passed against Task 1's already-committed implementation with zero further production-code change, since Task 1's tracer was written to full production quality (per its own instruction) rather than a partial happy-path stub. Each assertion was individually re-verified against the underlying guard it claims to pin before accepting the pass as genuine, per this project's TDD fail-fast convention."

patterns-established:
  - "Grid-path credential provider pattern: env-var-or-raise helpers run as the first statements of the fetch function (before date parsing, before the parameter dict), so a missing credential is provably a zero-network-call failure rather than an accident of dict-literal evaluation order. Reusable for TCEQ (Phase 9) if it ever needs a credential."

requirements-completed: [WX-03]

coverage:
  - id: D1
    description: "fetch_weather(config.CITY_COORDINATES[city], start, end, provider='nsrdb') returns a frame carrying GHI as solar_radiation, tagged solar_source='nsrdb' and a literal city key, and the merged row validates against PIPELINE_SCHEMA"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_returns_solar_radiation_for_a_known_city"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_grid_fetch_returns_a_solar_only_provenanced_frame"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_row_validates_against_the_schema_once_merged_with_a_station_row"
        status: pass
    human_judgment: false
  - id: D2
    description: "The wkt request parameter is built longitude-first (POINT(lon lat)), opposite CITY_COORDINATES' (lat, lon) order, pinned by a literal string for Austin and a sign test across all four cities"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_wkt_is_longitude_first"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_builds_a_distinct_longitude_first_wkt_for_all_four_cities"
        status: pass
    human_judgment: false
  - id: D3
    description: "The request asks for exactly GHI at a 60-minute interval in UTC for one calendar year in exactly one HTTP call; the returned frame carries no wind/temperature/humidity column and every optional request-metadata key is sent"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_requests_only_ghi_at_sixty_minute_interval"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_returns_no_wind_temperature_or_humidity_columns"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_issues_exactly_one_request_for_a_single_year_window"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_sends_the_optional_request_metadata_parameters"
        status: pass
    human_judgment: false
  - id: D4
    description: "datetime_utc is tz-aware UTC, built from separate Year/Month/Day/Hour/Minute columns, and monotonically increasing"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_timestamps_are_tz_aware_utc"
        status: pass
    human_judgment: false
  - id: D5
    description: "A missing NREL_API_KEY or NREL_API_EMAIL raises EnvironmentError naming the variable (never ValueError) before any network call, never echoes a credential value in an exception message, and importing the module performs no credential lookup"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_raises_when_api_key_is_unset"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_raises_when_contact_email_is_unset"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_credential_errors_are_not_value_errors"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_error_message_never_echoes_the_credential_values"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_module_import_has_no_side_effects"
        status: pass
    human_judgment: false
  - id: D6
    description: "The grid path is reachable only with provider='nsrdb' or 'open_meteo'; the station path never reaches nsrdb_provider; unresolvable coordinates raise; the widened trailing raise still contains 'grid' and names both grid providers; a malformed response body or an out-of-range GHI value raises instead of parsing/passing through"
    requirement: "WX-03"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_is_not_reachable_from_the_station_path"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_nsrdb_grid_fetch_raises_on_unresolvable_coordinates"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_grid_path_still_rejects_unknown_provider_names"
        status: pass
      - kind: integration
        ref: "backend/tests/weather_provider_test.py -k \"dispatch or mock_grid or open_meteo\" (14 tests, zero edits to Phase 6/7 dispatch tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_raises_when_the_response_is_not_a_psm4_csv"
        status: pass
      - kind: unit
        ref: "backend/tests/nsrdb_provider_test.py#test_fetch_nsrdb_raises_when_a_ghi_value_is_out_of_schema_range"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-09-13
status: complete
---

# Phase 8 Plan 1: NSRDB Solar Fetch Tracer Summary

**Phase 6/7's grid path gets its second real implementation: `fetch_weather(config.CITY_COORDINATES[city], start, end, provider="nsrdb")` returns NSRDB PSM v4 GHI as `solar_radiation` with `nsrdb` provenance, a literal city key, and a longitude-first WKT request pinned against every silent-corruption failure mode the phase's own threat model flagged, closing the tracer half of WX-03.**

## Performance

- **Duration:** ~6 min (first RED commit to last test commit)
- **Started:** 2026-09-13T07:13:11Z
- **Completed:** 2026-09-13T07:18:59Z
- **Tasks:** 2 (both TDD; Task 1 a tracer)
- **Files modified:** 5 (2 created, 3 modified, including ACKNOWLEDGEMENTS.md)

## Accomplishments
- New `backend/nsrdb_provider.py`: `fetch_nsrdb(lat, lon, start, end)` issues exactly one `requests.get` against NSRDB's PSM v4 GOES CONUS CSV endpoint, with both credential lookups (`_nrel_api_key`, `_nrel_contact_email`) running before any request is built so a missing env var fails with zero network calls.
- `_wkt_point(lat, lon)` isolates the one longitude-first coordinate swap this phase exists to get right, pinned by a literal-string test for Austin and a parse-back-and-check-sign test across all four `config.CITY_COORDINATES` cities.
- `_parse_psm4_csv` checks the literal `Year,Month,Day,Hour,Minute,GHI` data-column header before ever calling `pd.read_csv`, so an HTML error page or a redirect cannot silently "look parseable" the way a bare `str.split(",")` guard would miss.
- `weather_provider._fetch_grid`'s `provider == "nsrdb"` branch mirrors the existing `open_meteo` branch (`attach_provenance`, `attach_city` from the caller's own coordinates, a null-city raise); the trailing "unknown grid provider" raise now names both implemented grid providers while keeping the literal word `grid` three Phase 6/7 regression tests assert on.
- No credential value ever reaches an exception message or a log line: the parameter dict is never logged, and `requests.get`'s result is never passed through `.raise_for_status()` (whose own exception message embeds the full request URL, including `api_key` and `email` as query parameters).

## Tracer Feedback Gate (Task 1 -> Task 2)

Task 1 is `type="tracer"` with no `gate` attribute. This session ran under auto mode (`AUTO_CHAIN`/`AUTO_CFG` treated as active per the orchestrator's system context). Per the gate's auto-mode branch, `<verify>` was re-run end-to-end after Task 1's GREEN commit before starting Task 2: `backend/tests/nsrdb_provider_test.py` (7/7), the `-k nsrdb` selection in `weather_provider_test.py` (4/4), the request-contract probe, the credential-less import probe, and the full suite (262 passed) all passed, so the gate resolved to "verified end-to-end -- expanding" with no checkpoint raised.

## Task Commits

1. **Task 1: End-to-end NSRDB solar fetch** — `176b80f` (test: RED), `8fdcac1` (feat: GREEN)
2. **Task 2: Credential fail-loud path and four-city request contract** — `10365e0` (test: RED and GREEN combined — see Deviations)

**Plan metadata:** committed alongside this SUMMARY (see final commit).

## Files Created/Modified
- `backend/nsrdb_provider.py` — new module: `NSRDB_BASE`, `NSRDB_ATTRIBUTES`, `NSRDB_INTERVAL_MINUTES`, `NSRDB_REQUEST_METADATA`, `_nrel_api_key`, `_nrel_contact_email`, `_wkt_point`, `_parse_psm4_csv`, `_range_check`, `_to_utc_timestamp`, `fetch_nsrdb`
- `backend/tests/nsrdb_provider_test.py` — new file, 15 tests (happy path/columns/tz/wkt/request-contract/single-request/no-side-effects-on-import + credential fail-loud/four-city wkt/optional metadata/malformed-body/out-of-range)
- `backend/weather_provider.py` — added `import nsrdb_provider`, `_fetch_grid`'s `provider == "nsrdb"` branch, updated module and `fetch_weather` docstrings
- `backend/tests/weather_provider_test.py` — new `test_nsrdb_*` / `test_grid_path_still_rejects_unknown_provider_names` dispatch group (5 tests: solar-only provenanced fetch, schema validation once merged, station-path isolation, unresolvable-coordinate raise, widened unknown-provider raise)
- `ACKNOWLEDGEMENTS.md` — disclosed this session's AI-assisted work per ECE 464 policy

## Decisions Made
- `EnvironmentError`, not `ValueError`, for both credential-absent cases — already settled at plan time (08-CONTEXT.md corrected by 08-RESEARCH.md against `dlr_pipeline._token()`'s actual source); confirmed unchanged during execution.
- No `.raise_for_status()` call on the NSRDB response — the plan's `<action>` text didn't call this out explicitly as a "never do this," but the module docstring for `open_meteo_provider` and this phase's own T-08-02 threat entry ("API key in exception messages and logs") made clear that `requests.HTTPError`'s message embeds the full request URL. Since `api_key` and `email` are query parameters on this request (unlike Open-Meteo, which has none), calling `.raise_for_status()` here would leak both into any uncaught-exception traceback. Documented as a one-line comment at the call site rather than left implicit.

## Deviations from Plan

### Notable: Task 2 required no new production code

**What happened:** Task 1's `<action>` text specified, in full, the credential-first ordering, the `_parse_psm4_csv` data-column-header guard, and the `_range_check` gate — these were implemented during Task 1 rather than deferred, since Task 1's own acceptance criteria (`.venv/bin/python -m pytest -q` reporting 0 failed) required a real parse guard to exist for the suite to be safe against any malformed input already present in the test file. When Task 2's 8 new tests (credential fail-loud, four-city wkt order, optional metadata, malformed body, out-of-range GHI) were written and run to confirm RED, all 15 tests in the file already passed with zero further production-code change.

**Consequence:** Per this project's TDD fail-fast convention (a test passing unexpectedly during RED must be investigated, not silently accepted), each of the 8 new assertions was individually re-checked against the underlying guard it claims to pin before accepting the pass as genuine — e.g., confirming the malformed-body test actually reaches the `len(lines) < 3` branch of `_parse_psm4_csv` (not vacuously passing due to a fixture bug), and that `EnvironmentError`/`ValueError` really are unrelated exception types in this codebase's usage (not one subclassing the other). No plan acceptance criterion was left unimplemented.

**Files affected:** `backend/tests/nsrdb_provider_test.py` (test-only; no production file touched by "Task 2").

**Committed in:** `10365e0` (a single `test(...)` commit, since there was no separate GREEN state to reach).

---

**Total deviations:** 1 (process note — no Rule 1/2/3/4 auto-fix was needed; documented for transparency about the RED/GREEN split not landing in the expected two-commit shape for Task 2).
**Impact on plan:** None on scope or correctness — every stated acceptance criterion for both tasks is met, verified against actual code and re-run test output, not accepted on faith from a passing count.

## TDD Gate Compliance

Task 1: RED (`176b80f`, `test(...)`) precedes GREEN (`8fdcac1`, `feat(...)`) — gate sequence satisfied. Task 2: a single `test(...)` commit (`10365e0`) with no companion `feat(...)` — expected given the Deviations note above (production code already satisfied every new assertion); no REFACTOR commit was needed.

## Issues Encountered

Two test-fixture bugs of the executor's own making (not production-code defects), both caught by the production code's own gates behaving correctly against a badly-constructed fixture, then fixed in the test file:
- Two tests supplied a same-day `start == end` window while asserting on multiple hourly rows; `fetch_nsrdb`'s inclusive `[start, end]` timestamp filter (bare dates both resolving to midnight UTC) correctly dropped every row after `00:00` — fixed by widening the window to span a full day.
- The merge-with-a-station-row test paired a `_station_frame` fixture on a 5-minute cadence with a hand-rolled NSRDB fixture on a 1-hour cadence, so `merge_observations`'s union-of-timestamps path (not the exactly-equal-key path the test meant to exercise) produced spurious `MISSING required` errors on rows the other side never supplied for that timestamp — fixed by aligning both fixtures to the same 5-minute cadence.

## User Setup Required

None for this plan — every test mocks `requests.get`, so no `NREL_API_KEY`/`NREL_API_EMAIL` value was needed to execute or verify this plan. Both env vars remain required before Plan 08-03's live-credential checkpoint can run; per `.planning/STATE.md`'s carried blocker, the key registration itself is still not confirmed complete as of this plan's execution.

## Next Phase Readiness
- Plan 08-02 (year-chunking and the remaining NSRDB failure modes) can build directly on `fetch_nsrdb`'s single-year happy path without a rewrite — the year computation already carries a one-line comment marking the seam.
- Plan 08-03's live credential checkpoints are unaffected and still open; this plan changed no `.env` handling and required no live network call.
- No blockers introduced by this plan. The carried blocker (NREL key registration status) remains open and is Plan 08-03's concern, not this one's.

---
*Phase: 08-nsrdb-solar-integration*
*Completed: 2026-09-13*
