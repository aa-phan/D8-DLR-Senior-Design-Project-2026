---
phase: 10-fallback-wiring-documentation-ratification
verified: 2026-09-15T00:00:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 10: Fallback Wiring & Documentation Ratification Verification Report

**Phase Goal:** Synoptic is wired as the fallback provider behind the same adapter for any
primary provider failure, and the ratified per-variable provider composition decision is
recorded in the project's canonical docs.
**Verified:** 2026-09-15
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria, WX-06/WX-08)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | If TCEQ or NSRDB fails or returns no usable data for a request, the adapter automatically falls back to Synoptic for that request and still returns a usable row, rather than raising or returning an empty result | ✓ VERIFIED | Read `backend/weather_provider.py` end to end (864 lines). `fetch_weather` computes a `fallback_eligible` flag before dispatch (lines 828-833); on `ValueError` or an empty/`None` result from a fallback-eligible primary (`tceq`, `nsrdb`), it calls `_attempt_fallback`, which re-enters `_fetch_station(station_ids, start, end, "synoptic")` (lines 690-756). Confirmed by running the single named test `test_tceq_failure_triggers_fallback_and_returns_a_usable_synoptic_frame` (1 passed) and by the 40/40 `-k "fallback"` subset. `10-03-SUMMARY.md`'s Checkpoint Resolution additionally records an independent **live, unmocked** confirmation: a real TCEQ 74-day-window failure fell back to Synoptic KAUS and returned 87,226 rows; a real NSRDB HTTP-400 (unpublished 2026 data year) fell back to Synoptic KAUS and returned 5,316 rows — both non-empty, both real network results, not mocked. Provider exhaustion (both TCEQ/NSRDB and Synoptic fail) raises rather than returning empty/fabricated data (`test_fallback_failure_after_tceq_failure_chains_the_original_tceq_error`, `test_empty_synoptic_fallback_raises_instead_of_returning_the_empty_frame`, both pass) — matching PROJECT.md's fail-safe commitment cited in the plan. |
| 2 | The fallback is observable in provenance — a fallback-sourced row's provenance column records "synoptic", not the failed primary | ✓ VERIFIED | `_attempt_fallback` routes through `_fetch_station(..., FALLBACK_PROVIDER)`, which calls `attach_provenance(..., "tceq")`'s Synoptic sibling branch (`attach_provenance(dlr_pipeline.fetch_timeseries(...), "synoptic")`, line 545) — the fallback inherits real provenance tagging rather than a special case. `test_tceq_failure_triggers_fallback_and_returns_a_usable_synoptic_frame` asserts every `wind_source`/`temp_source` reads `"synoptic"` and none reads `"tceq"`; `test_fallback_sourced_row_merged_with_a_live_tceq_frame_attributes_the_real_supplier` (Plan 10-02 Task 3) proves this holds even in a merged frame with a live TCEQ side (wind/temp → `tceq`, fallback-supplied fields → `synoptic`, never `nsrdb`). Live confirmation in `10-03-SUMMARY.md` corroborates: `wind_source`/`temp_source` read `synoptic`/`asos` (never `tceq`) on the real station-path fallback; `solar_source` was correctly null (not `nsrdb`, not fabricated) on the real grid-path fallback since the Synoptic station has no solar sensor. |
| 3 | `docs/data-science/PRD.md` §7.1 and `docs/data-science/decisions/data_provider.md`'s status line are updated from "Pending"/"Open — vetting in progress" to record the ratified per-variable composition, matching what's actually implemented | ✓ VERIFIED | `PRD.md` §7.1 heading now reads "Weather data provider — ratified" with a 2026-09-15 resolution date and a table naming all five shipped providers (TCEQ, ASOS, NSRDB, Open-Meteo, Synoptic), their roles, implementing modules, and provenance values (lines 82-126) — matching `backend/weather_provider.py`'s actual dispatch exactly (`STATION_PATH_PROVIDERS`, `GRID_PATH_PROVIDERS`, `FALLBACK_ELIGIBLE_PRIMARIES`, `FALLBACK_PROVIDER`). `data_provider.md` line 3 reads `**Status:** Ratified, 2026-09-15. Answers PRD.md §7.1...`; its "Adopted Composition (ratified 2026-09-15)" section (lines 213-226) names the same five providers and the fallback's exclusions, matching the code. `grep` confirms zero occurrences of `unresolved`, `vetting in progress`, `Explicitly not decided here`, `Decision needed`, `not actually settled`, `No NOAA or NSRDB integration exists`, and `Solar irradiance comes from Synoptic` across both files, and zero remaining occurrences of the stale `developer.nrel.gov` hostname (3 corrected occurrences of `developer.nlr.gov` in its place). `PRD.md` §10's two affected discrepancy rows are corrected in the document's existing RESOLVED style; the corridor-discretization and ML-anomaly rows are untouched. |
| 4 | `.venv/bin/python -m pytest -q` reports 0 failed with the full multi-provider adapter (all four providers + fallback) in place | ✓ VERIFIED | Ran `.venv/bin/python -m pytest -q` independently during this verification session: **388 passed, 1 warning (pre-existing, unrelated to this phase), 0 failed** — exactly matching all three SUMMARYs' claimed counts (338→363→388 across Plans 10-01/10-02, unchanged by 10-03's docs-only pass). Also independently ran `pytest backend/tests/weather_provider_test.py -q -k "fallback"`: 40 passed, 86 deselected. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/config.py::SYNOPTIC_FALLBACK_STATIONS` | four-city ICAO Synoptic station table | ✓ VERIFIED | Lines 285-290: `{"AUSTIN": "KAUS", "CORPUS_CHRISTI": "KCRP", "MIDLAND": "KMAF", "EL_PASO": "KELP"}` — matches plan spec exactly, keys match `CITY_COORDINATES` |
| `backend/weather_provider.py` fallback registry | `FALLBACK_PROVIDER`, `FALLBACK_ELIGIBLE_PRIMARIES`, `STATION_PATH_PROVIDERS`, `GRID_PATH_PROVIDERS`, `_fallback_city_for_request`, `_fallback_station_ids`, `_attempt_fallback`, `_as_grid_shaped`, `fetch_weather(..., fallback=True)` | ✓ VERIFIED | All symbols present and read end-to-end (864 lines total); `FALLBACK_ELIGIBLE_PRIMARIES == {"tceq", "nsrdb"}` (excludes `open_meteo` per design rationale); eligibility flag computed before any `try` (lines 828-839); `EnvironmentError` re-raised via its own `except` clause before the `ValueError` handler (lines 847-848), never routed to fallback; `_as_grid_shaped` correctly guards against the city-column/index-level duplicate-name collision (lines 247-286) |
| `backend/tests/weather_provider_test.py` | Plan 10-01 Task 1/2, Plan 10-02 Task 1/2/3 test sections | ✓ VERIFIED | 113 total `def test_` functions in the file; five `# Plan 10-0X` section banners confirmed at lines 1561, 1671, 1881, 2078, 2278; 40 tests match `-k "fallback"` |
| `docs/data-science/PRD.md` | §7.1 ratified, §10 discrepancy rows corrected, §5/§6 extended | ✓ VERIFIED | Confirmed by direct read (see Truth 3 evidence) |
| `docs/data-science/decisions/data_provider.md` | status line ratified, "Adopted Composition" section, NREL hostname corrected | ✓ VERIFIED | Confirmed by direct read (see Truth 3 evidence) |
| `docs/data-science/specs/C4-weather-ingestion.md` | "Phase 10 additions (WX-06)" paragraph, updated Status line, new acceptance-criteria bullets | ✓ VERIFIED | Line 3 Status line names the Synoptic fallback; line 26 contains a dense Phase 10 paragraph naming `SYNOPTIC_FALLBACK_STATIONS`, `_as_grid_shaped`, the `EnvironmentError` split, and the null-solar guarantee; lines 67-68 add two checked acceptance-criteria bullets for the fallback provenance and no-fallback-on-caller-error guarantees |
| `ACKNOWLEDGEMENTS.md` | session entries for 10-01, 10-02, 10-03 | ✓ VERIFIED | Three session entries confirmed present (lines 536, 546, 556) — ECE 464 AI-use disclosure requirement met per user's memory instruction |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `fetch_weather(["83"], ..., provider="tceq")` raising `ValueError` | `_attempt_fallback` → `_fetch_station(["KCRP"], ..., "synoptic")` | `except ValueError` clause in `fetch_weather` | ✓ WIRED | Confirmed by reading + `test_tceq_failure_triggers_fallback_and_returns_a_usable_synoptic_frame` passing |
| `fetch_weather(coords, ..., provider="nsrdb")` raising `ValueError`/empty | `_attempt_fallback` → `_as_grid_shaped` → grid-contract-shaped Synoptic frame | grid branch of `_attempt_fallback` (lines 721-756) | ✓ WIRED | Confirmed by reading + 8-test Plan 10-02 Task 1 section passing |
| `provider="nsrdb"` raising `EnvironmentError` | propagates unchanged, no fallback | dedicated `except EnvironmentError: raise` clause before `except ValueError` | ✓ WIRED | `test_nsrdb_environment_error_propagates_and_is_not_masked_by_fallback` passes; independently re-run in isolation (1 passed) |
| Both TCEQ/NSRDB and Synoptic failing | credential-free, chained `ValueError` naming both providers | `_attempt_fallback`'s `except Exception as fallback_error: raise ValueError(...) from primary_error` | ✓ WIRED | `test_fallback_failure_after_tceq_failure_chains_the_original_tceq_error` passes; `test_both_sides_failing_message_carries_no_credential_value` passes with a real `SYNOPTIC_TOKEN` env value monkeypatched in and asserted absent from the message |
| `PRD.md` §7.1 ratified text | `backend/weather_provider.py`'s actual dispatch | manual cross-check | ✓ WIRED | Every provider name, module reference, and fallback-exclusion claim in §7.1 and `data_provider.md`'s Adopted Composition matches the code read above — no overstated capability found |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full repository test suite | `.venv/bin/python -m pytest -q` | `388 passed, 1 warning (pre-existing/unrelated), 0 failed` | ✓ PASS (independently run, matches all three SUMMARYs' claims) |
| Fallback-scoped tests | `pytest backend/tests/weather_provider_test.py -q -k "fallback"` | `40 passed, 86 deselected` | ✓ PASS |
| EnvironmentError branch (isolated) | `pytest backend/tests/weather_provider_test.py::test_nsrdb_environment_error_propagates_and_is_not_masked_by_fallback -q` | `1 passed` | ✓ PASS |
| TCEQ→Synoptic tracer (isolated) | `pytest backend/tests/weather_provider_test.py::test_tceq_failure_triggers_fallback_and_returns_a_usable_synoptic_frame -q` | `1 passed` | ✓ PASS |
| No-open-decision-qualifier grep gate | `grep -c 'unresolved'/'vetting in progress'/'Decision needed'/etc. across PRD.md + data_provider.md` | all zero | ✓ PASS |
| NREL hostname correction | `grep -c 'developer\.nrel\.gov'` = 0, `grep -c 'developer\.nlr\.gov'` = 3 | confirmed | ✓ PASS |
| No `backend/` file touched by the docs commit | `git show --stat b761540` | only `ACKNOWLEDGEMENTS.md` + the three `docs/` files listed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| WX-06 | 10-01, 10-02, 10-03 | Primary provider (TCEQ/NSRDB) failure or empty result falls back to Synoptic behind the same adapter interface | ✓ SATISFIED | ROADMAP SC1/SC2 verified above with both mocked and live evidence; `.planning/REQUIREMENTS.md` already marks WX-06 `[x]`, mapped to Phase 10 "Complete" |
| WX-08 | 10-03 | `PRD.md` §7.1 and `data_provider.md` updated to record the ratified per-variable composition | ✓ SATISFIED | ROADMAP SC3 verified above; documents match implementation exactly, no overstated or understated capability found |

No orphaned requirements found for Phase 10 in `.planning/REQUIREMENTS.md`.

### Decision Coverage

No `10-0X-CONTEXT.md` file exists for this phase (this project's convention keeps `<decisions>` at the `checkpoint:decision` task level inside the PLAN itself, not a separate CONTEXT.md). Skipped cleanly per the gate's own instruction.

### Anti-Patterns Found

None. `grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|not yet implemented|coming soon"` across `backend/weather_provider.py`, `backend/config.py`, and `backend/tests/weather_provider_test.py` returned zero matches. The plan's own `<!-- planner-discipline-allow: ... -->` comments in `10-03-PLAN.md` (Task 2's action block) intentionally allowlist historical-context phrases like "unresolved" and "Decision needed" that describe the *pre-ratification* wording being replaced — those phrases do not appear in the final ratified documents, confirmed by the zero-count greps above.

### Human Verification Required

None. Plan 10-03's Task 3 `checkpoint:human-verify` (`gate="blocking-human"`) — the live Synoptic/NSRDB endpoint confirmation — was already resolved and explicitly approved by the human, recorded in `10-03-SUMMARY.md`'s "Checkpoint Resolution" section: all four `SYNOPTIC_FALLBACK_STATIONS` entries returned real, non-null data; one real station-path fallback and one real grid-path fallback were each observed end-to-end with correct provenance; the `EnvironmentError` branch was confirmed against reality. This verification session did not have live `SYNOPTIC_TOKEN`/`NREL_API_KEY` credentials available in its own environment and could not independently re-run that live check (unlike Phase 9's verification, which had live credentials available) — but the recorded evidence is specific (exact row counts per city, exact HTTP failure modes used to force each fallback branch, explicit non-fabrication checks on `solar_source`), internally consistent with the code read above, and was gathered and approved by the human per the plan's own blocking-gate design, not self-approved by an executor. This is treated as sufficient chain-of-custody for the live-endpoint claim rather than an outstanding human-verification item requiring a further gate here.

### Gaps Summary

No gaps. All four ROADMAP Success Criteria for Phase 10 are verified against the actual codebase and documentation, not merely against SUMMARY.md's claims: `backend/weather_provider.py` and `backend/config.py` were read end-to-end and independently cross-checked against every plan's `<action>` text; all three ratified documents (`PRD.md`, `data_provider.md`, `C4-weather-ingestion.md`) were read in full and their claims verified against the actual shipped code (no overstated capability found); the full repository test suite was independently re-run and reproduced the exact 388/388 count claimed by all three SUMMARYs; the fallback-scoped test subset (40/40) and two individually-named behavioral tests (EnvironmentError branch, TCEQ→Synoptic tracer) were independently re-run in isolation. No stub, orphaned artifact, unwired key link, or debt marker was found in any file this phase touched. The v1.1 milestone's central goal — resolving `PRD.md` §7.1 by implementing and recording the per-variable provider composition — is met.

---
*Verified: 2026-09-15*
*Verifier: Claude (gsd-verifier)*
