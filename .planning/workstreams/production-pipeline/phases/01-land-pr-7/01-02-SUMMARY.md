---
phase: 01-land-pr-7
plan: 02
subsystem: testing
tags: [pytest, offline-tests, observation-composer, circuit-breaker, provenance]

requires:
  - phase: 01-land-pr-7
    provides: "01-01 offline fixtures (_no_network, _offline_env, _station_at, _hourly/_install_providers style)"
provides:
  - "backend/tests/observation_composer_test.py: 15 test functions (16 collected) for make_composed_fetcher and summarize_sources"
affects: [01-03, 01-04, 02-data-cleaning]

actuals:
  tokens: 6900
  tasks: 2
  commits: 2
plan_head_before: d86a8355d93de7bcecae979743049fb96a7bf877
plan_head_after: 90f9ce5e1b0ea880c024dd7572c5029b14cd36a9

tech-stack:
  added: []
  patterns:
    - "_install(monkeypatch, calls, synoptic=, tceq=, nsrdb=, open_meteo=): each argument is a frame, an exception to raise, or a callable; every stub records its provider name in calls"
    - "Fixed-timestamp stub frames (2025-06-01) because runs older than 2 days ask for whole UTC days"

key-files:
  created:
    - backend/tests/observation_composer_test.py
  modified: []

key-decisions:
  - "No backend module, frozen module or workflow was touched; the plan adds one test file"
  - "Fixtures copied from backfill_archive_test.py (no conftest.py), per repo convention"

requirements-completed: []

coverage:
  - id: D1
    description: "Composer priority per field, same-UTC-hour alignment, end boundary, last-row-in-hour, hour-by-hour fallback pass and its ordering, wind speed/direction pairing, empty result, pinned constants"
    requirement: "LAND-03"
    verification:
      - kind: unit
        ref: "backend/tests/observation_composer_test.py (9 tests of Task 1)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Provenance records and summarize_sources, circuit breaker (consecutive-only, nsrdb and open_meteo), synoptic/tceq failures never open a circuit, error-key redaction, TCEQ/grid applicability"
    requirement: "LAND-03"
    verification:
      - kind: unit
        ref: "backend/tests/observation_composer_test.py (6 tests of Task 2)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-10-20
status: complete
---

# Phase 1 Plan 02: Observation Composer Offline Tests Summary

**Fifteen offline tests (16 collected) pinning observation_composer's provider priority, same-UTC-hour alignment, fallback pass, wind pairing, circuit breaker, error-key redaction and provenance, using stub providers only.**

## Accomplishments

- Pinned FIELD_PRIORITY, LOOKBACK_HOURS, CIRCUIT_BREAKER_FAILURES, HISTORICAL_AFTER_DAYS, TCEQ_MAX_KM, `_BREAKER_PROVIDERS` and `_OUT_COLUMNS`.
- With all providers present: air_temp from synoptic, wind from tceq, solar from nsrdb, each `*_source` naming the provider.
- Reading is built at the latest hour the chosen providers share (an older provider is not skipped); a row exactly at `end` counts, a later row is ignored, the last non-null row in an hour wins.
- Fallback pass fills hour by hour only when the chosen providers share no hour (open_meteo is never called otherwise), and an earlier-ranked provider keeps an hour a later one also offers.
- Wind speed needs a direction from the same provider and hour; empty result keeps `_OUT_COLUMNS` and records no provenance.
- Circuit breaker: nsrdb and open_meteo are skipped after 3 consecutive failures (5 fetches: 3 calls, 2 skipped), a success resets the count (fail, fail, success, fail, fail, fail opens on the sixth call), synoptic and tceq failures never open a circuit, and a failed TCEQ window is fetched once and re-raised from the cache.
- Error keys carry a message only for non-synoptic ValueError / non-requests OSError; Synoptic and requests exception text (a token, a URL) never appears.
- Provenance: one record per completed reading, provider-supplied `temp_source` ("asos") passes through, `summarize_sources` counts per field; TCEQ is skipped for a station more than 50 km from any city, and a station with no coordinates gets only the synoptic provider.
- Every test runs with `requests.get` guarded (attempts asserted empty at teardown), credentials unset, the anomaly model loader patched to None, and writes nothing outside tmp_path.

## Task Commits

1. **Task 1: composer provider priority, same-hour alignment and fallback pass** - `dd52209`
2. **Task 2: composer provenance, circuit breaker and error-key redaction** - `90f9ce5`

## Verification

- `pytest backend/tests/observation_composer_test.py`: 16 passed (collect-only: 16 tests collected); 15 `def test_` functions; 484 lines.
- Full suite at 90f9ce5: 1258 passed, 0 failed (baseline 1242 plus 16).
- `find data outputs -newer <marker>` after the run: nothing changed.
- `git diff --quiet 5efe97d HEAD -- backend ':(exclude)backend/tests'` exits 0 (no backend module changed).

## Deviations from Plan

None - plan executed exactly as written.

## Discrepancies

none

## Known Stubs

None. The stub providers are test doubles by design.

## Threat Flags

None. T-01-05 (error keys never carry a token or URL) is pinned by `test_error_keys_never_echo_synoptic_or_request_messages`; T-01-06 and T-01-07 are mitigated by the copied network guard and credential deletion and by exact assertions on `fetcher.errors` and stub call counts.

## Requirements

LAND-03 and PIPE-01 are shared with later plans; `requirements.ready-ids` reported LAND-03 as blocked, so it was not marked complete.

## Next Phase Readiness

Ready for 01-03 (city_pipeline tests) and 01-04 (dlr_orchestrator tests).

## Self-Check: PASSED

- backend/tests/observation_composer_test.py: FOUND
- dd52209, 90f9ce5: FOUND in HEAD history
