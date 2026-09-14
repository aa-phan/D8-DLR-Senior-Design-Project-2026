---
phase: 08-nsrdb-solar-integration
verified: 2026-09-13T00:00:00Z
status: passed
score: 9/9 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 8: NSRDB Solar Integration Verification Report

**Phase Goal:** NREL NSRDB (PSM v4) becomes the primary solar-irradiance source for all four cities.
**Verified:** 2026-09-13T00:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria + WX-03)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Given a target city and time window, the system fetches solar irradiance (GHI) from NSRDB for that city's lat/lon coordinates, for all four cities (ROADMAP SC1) | ✓ VERIFIED | `weather_provider._fetch_grid`'s `provider == "nsrdb"` branch (weather_provider.py:470-482) is a real, non-stub call into `nsrdb_provider.fetch_nsrdb`, reached through `fetch_weather(config.CITY_COORDINATES[city], start, end, provider="nsrdb")` — the public entrypoint, not a test-only shim. Independently confirmed the longitude-first WKT swap is correct and distinct for all four `config.CITY_COORDINATES` cities (`_wkt_point` re-run this session, all four negative-longitude/positive-latitude). 08-03-SUMMARY.md records a live pull (not mocked) returning 24 real hourly rows for Austin 2023-07-01 with a genuine diurnal curve (0 W/m² overnight, peak 886 W/m² mid-afternoon UTC), `solar_source="nsrdb"`, `city="AUSTIN"` on every row. |
| 2 | The NREL developer API key is read only from `.env`/environment — never hardcoded or committed, matching `SYNOPTIC_TOKEN` (ROADMAP SC2) | ✓ VERIFIED | Independently re-ran `env -u NREL_API_KEY -u NREL_API_EMAIL .venv/bin/python -c "import nsrdb_provider"` — imports cleanly, no credential read at import time. Re-ran the missing-key case directly: `fetch_nsrdb(...)` without env vars raises `EnvironmentError: Set NREL_API_KEY env var...` before any network call. `git grep` across tracked files for a quoted literal assigned to `NREL_API_KEY`/`NREL_API_EMAIL` found none. `git check-ignore .env` prints `.env`; `git ls-files -- .env` is empty (0 tracked). `backend/nsrdb_provider.py` contains no line assigning a quoted string literal to a KEY/EMAIL-named variable (confirmed by direct grep, matching the source-gate test `test_no_nsrdb_credential_value_is_tracked_in_the_repository`). |
| 3 | NSRDB-sourced solar rows are tagged with the correct provenance value and pass `PIPELINE_SCHEMA` range validation for `solar_radiation` (ROADMAP SC3) | ✓ VERIFIED | `_fetch_grid`'s nsrdb branch calls `attach_provenance(frame, "nsrdb")`; `"nsrdb"` is a member of `units_def.KNOWN_PROVIDER_NAMES` (units_def.py:333). `nsrdb_provider._range_check` gates every `solar_radiation` value against `PIPELINE_SCHEMA["solar_radiation"]["range"]` before `fetch_nsrdb` returns. `backend/tests/weather_provider_test.py::test_nsrdb_row_validates_against_the_schema_once_merged_with_a_station_row` and `test_nsrdb_solar_merges_with_a_station_row_at_an_exactly_equal_key` prove this holds through a real `merge_observations` call against a station frame, not just on the bare NSRDB frame. |
| 4 | If the API key is absent or the NSRDB request fails, the adapter raises/surfaces a clear error rather than silently returning fabricated data (e.g. the legacy hardcoded 1000 W/m² constant) (ROADMAP SC4) | ✓ VERIFIED | No fallback, default, or demo-key path exists anywhere in `nsrdb_provider.py` (confirmed by reading the full file — both credential helpers are the first two statements of `fetch_nsrdb`, unconditionally raising `EnvironmentError` on empty). `_raise_for_nsrdb_error` raises `ValueError` for any non-2xx response, handling both the JSON `errors`-array shape and the raw CSV `Error Code,Error Message` shape, with credentials redacted before the message is built (`_redact`). No `raise_for_status()` call and no `fillna`/`interpolate`/`reindex` call exists in the module (confirmed by grep — 0 matches for both). 08-03-SUMMARY.md's live check (Task 3, step 3) recorded a real out-of-range-year (2035) request raising `ValueError: nsrdb_provider: request for year 2035 failed with HTTP 400: ['Invalid value(s)']`, containing neither credential. |
| 5 | Credential-source proof is real: module imports without credentials, raises `EnvironmentError` with none set, no credential literal in source | ✓ VERIFIED | See truth 2's evidence — re-executed directly this session, not taken from SUMMARY claims. |
| 6 | Documentation (C4 spec, README, ACKNOWLEDGEMENTS.md) was actually updated | ✓ VERIFIED | `docs/data-science/specs/C4-weather-ingestion.md` contains a full Phase 8 additions paragraph (line 22) naming `nsrdb_provider.fetch_nsrdb`, both env vars, the year-scoped decomposition, the 2018 coverage floor, and the `developer.nlr.gov` rename, plus two new verification bullets. `README.md` documents `NREL_API_KEY`/`NREL_API_EMAIL` and `developer.nlr.gov` alongside the existing `SYNOPTIC_TOKEN` step. `ACKNOWLEDGEMENTS.md` carries 4 Phase 8 `### Session:` entries (planning + 08-01/08-02/08-03 execution), all positioned before `## Keeping This Updated`. |
| 7 | The live verification in 08-03 Task 3 genuinely happened against a real NSRDB endpoint with a real key | ✓ VERIFIED (human-attested, not independently re-executable by this verifier without the developer's registered key) | 08-03-SUMMARY.md records concrete, specific, non-generic evidence consistent with a real third-party response rather than a fabricated one: 24 rows with a plausible diurnal GHI curve (`00:30→158`, `05:30→0`, `11:30→0`, `12:30→99`, `15:30→728`, `20:30→886`, `23:30→221`), a verbatim `GHI Units` value of `"w/m2"` (a spelling already inside `NSRDB_ACCEPTED_GHI_UNITS`, so there was no incentive to fabricate it matching), echoed coordinates `Latitude 30.28, Longitude -97.75` (NSRDB's snapped grid-cell value, not identical to `config.CITY_COORDINATES["AUSTIN"]`'s `30.2711, -97.7437` — the kind of small discrepancy a live snapped-to-grid response produces and a fabricated answer would be unlikely to introduce), and a genuinely generic real-world rejection message (`HTTP 400: ['Invalid value(s)']`) that explicitly does *not* match the phase's own guessed "out of range year" wording — the SUMMARY explicitly notes this refutes rather than confirms the phase's own assumption, which is not the behavior of a fabricated result. This item is inherently something a static code verifier cannot re-run (it requires a registered developer key held by the human), so it is accepted on the strength of this internal-consistency evidence rather than independently reproduced. |
| 8 | `docs/data-science/PRD.md` and `docs/data-science/decisions/data_provider.md` were NOT touched by this phase (WX-08/Phase 10 scope) | ✓ VERIFIED | `git log -1 -- docs/data-science/PRD.md` → `16d6921` (pre-Phase-6). `git log -1 -- docs/data-science/decisions/data_provider.md` → `0558357` (pre-Phase-6). Neither file appears in any Phase 8 commit's diff. |
| 9 | `.venv/bin/python -m pytest -q` reports 0 failed | ✓ VERIFIED | Independently re-ran: **296 passed, 0 failed**, matching 08-03-SUMMARY.md's claimed final count exactly (up from Phase 7's 250-passed baseline). |

**Score:** 9/9 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/nsrdb_provider.py` | `NSRDB_BASE`, `NSRDB_ATTRIBUTES`, `NSRDB_INTERVAL_MINUTES`, `NSRDB_REQUEST_METADATA`, `NSRDB_FIRST_COVERED_YEAR`, `NSRDB_ACCEPTED_GHI_UNITS`, credential helpers, `_wkt_point`, `_parse_psm4_csv`, `_range_check`, `_redact`, `_raise_for_nsrdb_error`, `_window_bounds`, `_years_spanned`, `fetch_nsrdb` | ✓ VERIFIED | All present; read the full 500-line file directly. Substantive implementation (real credential-first ordering, real dual-shape error handling, real year decomposition), no debt markers (`TBD`/`FIXME`/`XXX`/`TODO`/`HACK` all absent). |
| `backend/tests/nsrdb_provider_test.py` | Happy-path, WKT-order, request-contract, credential-fail-loud, year-chunking, dual-shape error, redaction, units-metadata tests | ✓ VERIFIED | 36 tests present, all passing (independently re-run) |
| `backend/weather_provider.py` | `import nsrdb_provider`; `_fetch_grid`'s `provider == "nsrdb"` branch | ✓ VERIFIED | Present at weather_provider.py:470-482; mirrors the `open_meteo` branch's `attach_provenance`/`attach_city`/null-city-guard sequence exactly |
| `backend/tests/weather_provider_test.py` | `test_nsrdb_*` dispatch, provenance, merge, and credential-source-gate groups | ✓ VERIFIED | 9 nsrdb-named tests, all passing (independently re-run) |
| `docs/data-science/specs/C4-weather-ingestion.md` | Phase 8 additions paragraph and verification bullets | ✓ VERIFIED | Present at line 22 and lines 57-58; header status line updated to "four" real providers |
| `README.md` | NREL credential setup step | ✓ VERIFIED | Present (lines 46, 54-55), alongside existing `SYNOPTIC_TOKEN` step, with that step's content intact |
| `ACKNOWLEDGEMENTS.md` | Phase 8 session entries before `## Keeping This Updated` | ✓ VERIFIED | 4 entries present (planning + 08-01/08-02/08-03), correctly positioned |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `fetch_weather(location, ..., provider="nsrdb")` | `nsrdb_provider.fetch_nsrdb` | `_fetch_grid`'s `provider == "nsrdb"` branch | ✓ WIRED | Not test-only — the same public `fetch_weather` entrypoint every caller (including `corridor_discretization`) uses. Confirmed by reading `weather_provider.py:490-536` directly: `fetch_weather` → `_fetch_grid` → `nsrdb_provider.fetch_nsrdb` is a real, unconditional call chain. |
| `config.CITY_COORDINATES[city]` (lat, lon) | `_wkt_point(lat, lon)` → `POINT(lon lat)` | the single coordinate swap | ✓ WIRED | Re-executed `_wkt_point` against all four `config.CITY_COORDINATES` entries this session: 4 distinct strings, each with negative longitude first and positive latitude second — correct order, not transposed. Live check (08-03-SUMMARY) additionally confirmed the *response's own* echoed coordinates (30.28, -97.75) matched Austin, closing the one failure mode research flagged as undetectable by any mocked test. |
| `os.getenv("NREL_API_KEY"/"NREL_API_EMAIL")` | `EnvironmentError` | `fetch_nsrdb`'s first two statements | ✓ WIRED | Re-executed directly: both credential lookups run before any `requests.get`, confirmed by reading the source (lines 444-445 precede the request loop) and by the missing-key re-run above raising immediately. |
| `units_def.KNOWN_PROVIDER_NAMES` | `attach_provenance`'s membership check | `"nsrdb"` seed value | ✓ WIRED | Confirmed `"nsrdb"` present in `units_def.py:333`. |
| NSRDB error body (`inputs` object echoing `api_key`/`email`) | exception message | `_redact` | ✓ WIRED | Read `_raise_for_nsrdb_error`'s source directly: every extracted detail string passes through `_redact(*secrets)` before reaching the raised `ValueError`. Live check confirmed neither credential appeared in the real out-of-range-year error message. |

### Behavioral Spot-Checks (independently re-run, not taken from SUMMARY)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite is green | `.venv/bin/python -m pytest -q` | 296 passed, 0 failed | ✓ PASS |
| NSRDB provider unit tests | `pytest backend/tests/nsrdb_provider_test.py -q` | 36 passed | ✓ PASS |
| NSRDB dispatch/provenance/credential-source group | `pytest backend/tests/weather_provider_test.py -q -k nsrdb` | 9 passed, 58 deselected | ✓ PASS |
| Credential-source gate (D1 of 08-03) | `pytest backend/tests/weather_provider_test.py -q -k "nsrdb_provider_reads or nsrdb_provider_imports or no_nsrdb_credential"` | 3 passed | ✓ PASS |
| Module importable with no credentials | `env -u NREL_API_KEY -u NREL_API_EMAIL .venv/bin/python -c "import nsrdb_provider"` | "import without credentials OK" | ✓ PASS |
| Missing-key fail-loud, zero network calls | direct `fetch_nsrdb(...)` call with both env vars unset | `EnvironmentError: Set NREL_API_KEY env var...` | ✓ PASS |
| Four-city WKT longitude-first order | direct `_wkt_point` call over all `config.CITY_COORDINATES` | 4 distinct strings, all lon-negative/lat-positive | ✓ PASS |
| No credential literal in tracked source | `git grep` for quoted-literal assignment to `NREL_API_KEY`/`NREL_API_EMAIL` | no matches | ✓ PASS |
| `.env` git-ignored and untracked | `git check-ignore .env && git ls-files -- .env` | `.env` printed; 0 tracked files | ✓ PASS |
| `PRD.md`/`data_provider.md` untouched by Phase 8 | `git log -1 -- <file>` for each | both last modified pre-Phase-6 (`16d6921`, `0558357`) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|--------------|--------|----------|
| WX-03 | 08-01, 08-02, 08-03 | Fetch solar irradiance (GHI) from NREL NSRDB as primary solar source, key from `.env` only | ✓ SATISFIED | All four ROADMAP Success Criteria independently verified above; `.planning/REQUIREMENTS.md` still shows WX-03 unchecked / "Pending" — this is expected pre-verification bookkeeping (Phase 7's WX-02/WX-04 rows show the same pattern was only flipped to "Complete" after their own verification pass) and is not itself evidence against the requirement; it should be updated to `[x]` / "Complete" as part of closing out this verification. |

No orphaned requirements — WX-03 maps to Phase 8 in REQUIREMENTS.md's traceability table and all three plans declare it in frontmatter `requirements:`.

### Anti-Patterns Found

None. Grep for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` (case-sensitive) across `backend/nsrdb_provider.py`, `backend/weather_provider.py`, `backend/tests/nsrdb_provider_test.py` found zero debt-marker matches (the only `PLACEHOLDER`-adjacent hits are the legitimate `_REDACTED_PLACEHOLDER` constant name, not a stub marker). No empty implementations, no hardcoded-empty stubs, no `raise_for_status()` calls, no `fillna`/`interpolate`/`reindex` calls that would silently substitute a value NSRDB never supplied.

### Human Verification Required

None outstanding. The phase's one genuinely un-automatable item — a live pull against the real NSRDB endpoint with a real, human-registered developer key — was already gated behind `checkpoint:human-verify` (08-03 Task 3) during execution and resolved with a developer-approved "approved" resume signal. This verifier cannot re-execute that live call (it requires the developer's own registered `NREL_API_KEY`/`NREL_API_EMAIL`, not present in this environment), but the SUMMARY's recorded evidence — a plausible non-round diurnal GHI curve, a snapped-grid-cell coordinate echo that differs slightly from the input (as a real remote service does and a fabrication would be unlikely to reproduce), and a genuinely generic real-world error message that explicitly contradicts rather than confirms the phase's own prior guess — is internally consistent with a genuine live call rather than a scripted or fabricated one. This is recorded as accepted-on-evidence rather than independently re-executed, per the phase's own design (Plan 08-03's Task 2 checkpoint exists precisely because the key is human-held).

### Gaps Summary

No gaps found. All four ROADMAP Phase 8 Success Criteria are independently verified against the actual codebase, not merely asserted by SUMMARY.md:

1. `provider="nsrdb"` is genuinely wired into the production grid-dispatch path (`fetch_weather` → `_fetch_grid` → `nsrdb_provider.fetch_nsrdb`), not merely exercised in isolated unit tests — confirmed by reading the dispatch chain directly.
2. The credential-source proof is real and was re-executed independently this session (import succeeds with no env vars, `EnvironmentError` is raised with the correct message, `.env` is git-ignored and untracked, no credential literal exists in tracked source).
3. Documentation (C4 spec, README, ACKNOWLEDGEMENTS.md) was genuinely updated — content read directly from each file, not taken from the SUMMARY's claims.
4. The 08-03 live verification carries specific, non-generic, internally-consistent evidence (exact row counts, a real diurnal curve, a snapped-coordinate discrepancy, a verbatim and self-contradicting-to-the-phase's-own-guess error message) that is far more consistent with a genuine live call than with fabrication.
5. `.venv/bin/python -m pytest -q` was re-run directly by this verifier: 296 passed, 0 failed.
6. `docs/data-science/PRD.md` and `docs/data-science/decisions/data_provider.md` are confirmed untouched since well before Phase 6 began — Phase 10/WX-08 scope is correctly preserved.

One bookkeeping item, not a gap: `.planning/REQUIREMENTS.md` still lists WX-03 as unchecked/"Pending". This mirrors the same pre-verification state Phase 7's WX-02/WX-04 rows carried before their own verification passed, and should be flipped to `[x]`/"Complete" as part of closing out this phase, alongside `.planning/ROADMAP.md`'s Phase 8 checkbox (line 44).

---

_Verified: 2026-09-13T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
