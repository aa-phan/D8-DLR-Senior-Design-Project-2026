---
phase: 07-trivial-integration-providers
plan: 03
subsystem: api
tags: [weather-ingestion, asos, open-meteo, synoptic, provenance, testing, documentation]

# Dependency graph
requires:
  - phase: 07-trivial-integration-providers (plan 01)
    provides: "ASOS 1-minute station-path supplement (_supplement_with_asos), asos_provider.fetch_asos_1min, config.ASOS_STATIONS"
  - phase: 07-trivial-integration-providers (plan 02)
    provides: "Open-Meteo grid-path implementation (_fetch_grid's provider=='open_meteo' branch), open_meteo_provider.fetch_open_meteo"
provides:
  - "Cross-provider proof that a single merged frame carrying Synoptic, ASOS, and Open-Meteo rows names the correct actual supplier in every non-null provenance cell (ROADMAP SC3 for WX-02 and WX-04 at once)"
  - "Source-level no-secrets gate over both new provider modules (ROADMAP SC4, asserted rather than inferred)"
  - "C4-weather-ingestion.md spec brought current for both Phase 7 providers"
  - "Phase 7 ECE 464 AI-use disclosure entry in ACKNOWLEDGEMENTS.md"
  - "Human-confirmed live-endpoint check for both providers, closing the one gap mocked tests structurally cannot cover"
affects: [08-nsrdb-primary-solar, 09-tceq-primary-wiring, 10-synoptic-fallback-and-ratification]

# Actuals (#2632)
actuals:
  tokens: 6016
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cross-provider provenance proof pattern: obtain each side of a merge through the real fetch_weather dispatch (never a hand-built tagged frame), then iterate PROVENANCE_FIELD_MAP generically to assert provenance non-null exactly where a mapped source column is non-null -- reusable for Phase 8/9's NSRDB and TCEQ integrations when they join the same merged frame."
    - "Source-level secrets gate: read a provider module as text (comment-stripped) from a __file__-derived path and assert absence of os.environ/os.getenv/getpass/_TOKEN/_KEY/_SECRET substrings and os/dotenv imports -- a stronger claim than 'tests pass without a token', reusable for any future no-auth provider module."

key-files:
  created: []
  modified:
    - backend/tests/weather_provider_test.py
    - docs/data-science/specs/C4-weather-ingestion.md
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "Open-Meteo mock fixture in _three_provider_frame carries the full 5-column set fetch_open_meteo always returns in production, not the solar-only shape the plan's <behavior> text literally specified -- a solar-only row can never satisfy PIPELINE_SCHEMA's required air_temp/wind_speed/wind_direction fields, so the literal fixture as written would make must_haves.truths (every row validates cleanly) unsatisfiable by construction. Resolved as a test-construction fix, not a production-code change (git diff --name-only confirms no file under backend/ other than the test module was touched)."
  - "Task 3's live-endpoint check confirmed ASOS's 10-minute Austin window returning 0 rows is a real narrow sensor gap, not a failure: widening to a 6-hour window on the same day returned 311 rows, and re-running the identical 10-minute window one year earlier (2024-07-01) returned 10 plausible rows. Open-Meteo returned 24 rows for the single-day window with all 5 weather columns populated. Neither call required a credential, token, or .env entry."

patterns-established:
  - "Live-endpoint human-verify checkpoint as the closing task of a mocked-provider phase: every automated test mocks requests.get, so a single human-run, read-only, unauthenticated live check against the real endpoint is the only thing that would catch upstream station-ID/endpoint/parameter drift. Standing procedure for future provider phases (Phase 8 NSRDB, Phase 9 TCEQ)."

requirements-completed: [WX-02, WX-04]

coverage:
  - id: D1
    description: "A single frame assembled from Synoptic, ASOS, and Open-Meteo carries exactly one row per (city, datetime_utc)/(stid, datetime_utc) key, and every non-null provenance cell names the provider that actually supplied that row's value"
    requirement: "WX-02"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_three_provider_frame_has_one_row_per_distinct_timestamp"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_three_provider_frame_names_the_actual_supplier_per_field"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_three_provider_frame_provenance_matches_its_values"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every provenance value produced by the three-provider frame is a member of units_def.KNOWN_PROVIDER_NAMES (synoptic, asos, open_meteo), with no schema edit needed or made"
    requirement: "WX-04"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_three_provider_frame_uses_only_registered_provider_names"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every row of the three-provider frame satisfies units_def.validate_pipeline_row(row, strict=False) == []"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_three_provider_frame_rows_validate_against_pipeline_schema"
        status: pass
    human_judgment: false
  - id: D4
    description: "Neither asos_provider.py nor open_meteo_provider.py reads an environment variable, imports os/dotenv, or references a token/key/secret -- ROADMAP SC4 asserted at the source level"
    requirement: "WX-02"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_new_providers_read_no_secret"
        status: pass
    human_judgment: false
  - id: D5
    description: "docs/data-science/specs/C4-weather-ingestion.md names both new providers and no longer claims no grid provider is registered; PRD.md and data_provider.md remain untouched (WX-08/Phase 10 scope)"
    verification:
      - kind: unit
        ref: "python -c substring probe: asos_provider/open_meteo_provider/ASOS_STATIONS all present in C4 spec"
        status: pass
      - kind: other
        ref: "git diff --name-only HEAD -- docs/data-science/PRD.md docs/data-science/decisions/data_provider.md (empty output)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Both ASOS and Open-Meteo endpoints answer a real unauthenticated request from this repository's environment, with plausible units and no credential required"
    verification:
      - kind: manual_procedural
        ref: ".venv/bin/python -c ... asos_provider.fetch_asos_1min(...) and open_meteo_provider.fetch_open_meteo(...) -- run twice (checkpoint author, then this executor)"
        status: pass
    human_judgment: true
    rationale: "Every automated test in this phase mocks requests.get; only a human-observed live run against the real upstream endpoint can confirm the station IDs, endpoint URLs, and parameter names research found still hold. Developer approved with 'approved' after reviewing both row counts and unit plausibility."

duration: 20min
completed: 2026-09-12
status: complete
---

# Phase 7 Plan 3: Cross-Provider Provenance Proof, No-Secrets Gate, and Phase Wrap-Up Summary

**One merged frame carrying Synoptic, ASOS, and Open-Meteo rows proves ROADMAP Success Criteria 3 and 4 for WX-02 and WX-04 simultaneously; a source-level gate confirms neither new provider module reads a secret; and a human-confirmed live check against both real endpoints closes the phase's one mocked-test blind spot.**

## Performance

- **Duration:** ~20 min (Task 1 RED start to Task 3 checkpoint resolution)
- **Started:** 2026-09-12T07:56:34Z
- **Completed:** 2026-09-12T08:30:00Z
- **Tasks:** 3 (2 auto/TDD + 1 checkpoint:human-verify)
- **Files modified:** 3 (`backend/tests/weather_provider_test.py`, `docs/data-science/specs/C4-weather-ingestion.md`, `ACKNOWLEDGEMENTS.md`)

## Accomplishments

- `_three_provider_frame(monkeypatch)` helper obtains the station side through the real `weather_provider.fetch_weather(["KAUS"], ...)` (Synoptic, transparently ASOS-supplemented per 07-01) and the grid side through the real `weather_provider.fetch_weather(config.CITY_COORDINATES["AUSTIN"], ..., provider="open_meteo")` (07-02), then combines both with the real `merge_observations` — never a hand-built tagged frame.
- Six new tests added to `backend/tests/weather_provider_test.py`: one-row-per-distinct-timestamp (5, the union of Synoptic's 2 + ASOS's 2 + Open-Meteo's 2, with one shared timestamp), per-field supplier naming, a generic `PROVENANCE_FIELD_MAP`-iterating pairing test (Phase 6's provenance invariant re-asserted with three providers present), `KNOWN_PROVIDER_NAMES` membership (proving the registry needed no schema edit), full-row `PIPELINE_SCHEMA` validation, and a source-level no-secrets gate (`test_new_providers_read_no_secret`) over `asos_provider.py`/`open_meteo_provider.py`.
- `docs/data-science/specs/C4-weather-ingestion.md` extended with a Phase 7 subsection naming `asos_provider.fetch_asos_1min`/`config.ASOS_STATIONS`/`weather_provider._supplement_with_asos` and `open_meteo_provider.fetch_open_meteo`, removing the stale claim that no grid provider is registered, and recording the `(city, datetime_utc)`-vs-`(stid, datetime_utc)` return-shape distinction.
- `ACKNOWLEDGEMENTS.md` carries a Phase 7 Plan 07-03 session entry, written and committed before this plan's final commit, per the standing ECE 464 disclosure requirement.
- Task 3's live-endpoint check confirmed both providers answer real unauthenticated requests from this environment (see Task 3 Results below).
- Full suite: **250 passed, 0 failed** — up from Plan 07-02's 244-passed baseline (6 new tests), comfortably above the 195-passed Phase 6 baseline this phase's `<verification>` block requires.

## Task 3 Results: Live Endpoint Confirmation

Both commands were run twice against this repository's own code (once by the prior executor at the checkpoint, once independently by this continuation executor before finalizing) with consistent results:

**ASOS** (`asos_provider.fetch_asos_1min(config.ASOS_STATIONS['AUSTIN'], '2025-07-01T00:00:00Z', '2025-07-01T00:10:00Z')`):
- 10-minute window: **0 rows** — an empty `DataFrame` with the expected columns, no exception.
- Diagnostic widen to a 6-hour window on the same day (`2025-07-01T00:00:00Z` to `06:00:00Z`): **311 rows**, first observation at `00:38:00Z`, plausible Celsius `air_temp` (~25.6-26.1°C).
- Diagnostic re-run of the identical 10-minute window one year earlier (`2024-07-01T00:00:00Z` to `00:10:00Z`): **10 rows**, plausible Celsius `air_temp` (35.0°C) and metres-per-second `wind_speed` (~3.6-4.1 m/s).
- Conclusion: the 2025-07-01 10-minute window is a real narrow sensor-reporting gap at station `AUS`, not a code defect — the station has data both immediately before and after this window and one year prior at the same window. No exception was raised at any point; the well-formed-empty-response carve-out (D-02/07-01) behaved as designed.

**Open-Meteo** (`open_meteo_provider.fetch_open_meteo(*config.CITY_COORDINATES['AUSTIN'], '2025-07-01', '2025-07-01')`):
- Single-day window: **24 rows**, all 5 weather columns (`air_temp`, `wind_speed`, `wind_direction`, `solar_radiation`, `relative_humidity`) populated with plausible values (e.g. `air_temp` 25.3-29.9°C, `wind_speed` 2.4-4.1 m/s, `solar_radiation` 12-291 W/m²). Closes Plan 07-02's carried backstop marker for the `start_date == end_date` single-day adjacency edge.

**Credentials:** Neither command required a token, API key, or `.env` entry — ROADMAP Success Criterion 4 observed directly, not inferred from tests passing without one.

**Developer resolution:** "approved" — both row counts and unit magnitudes reviewed and confirmed correct.

## Task Commits

Each task was committed atomically (checkpoint tasks that make no production/test edits are recorded here without a separate commit):

1. **Task 1: One frame, three providers, honest provenance + no-secrets gate** — `753dd4d` (test)
2. **Task 2: Bring C4 spec current + Phase 7 AI-use disclosure entry** — `63f640c` (docs)
3. **Task 3: Confirm both endpoints answer a real unauthenticated request** — checkpoint:human-verify, no file changes; results recorded above and confirmed independently by this continuation executor.

**Plan metadata:** committed alongside this SUMMARY (see final commit).

## Files Created/Modified

- `backend/tests/weather_provider_test.py` — new cross-provider provenance test group (6 tests) and `_three_provider_frame` helper
- `docs/data-science/specs/C4-weather-ingestion.md` — Phase 7 subsection naming both new providers, stale "no grid provider" claim removed
- `ACKNOWLEDGEMENTS.md` — Phase 7 Plan 07-03 session entry, positioned before `## Keeping This Updated`

## Decisions Made

- Open-Meteo mock fixture in `_three_provider_frame` was changed from the plan's literally-specified solar-only shape to the full 5-column set `fetch_open_meteo` always returns in production. The solar-only shape as written would make a row at `00:10` (no Synoptic/ASOS coverage) permanently unable to satisfy `PIPELINE_SCHEMA`'s required `air_temp`/`wind_speed`/`wind_direction` fields — a self-contradiction between the plan's literal fixture prose and its own `must_haves.truths` requirement that every row validates. This is the more faithful test of real behavior regardless, since `fetch_open_meteo` never returns a partial variable set in production. Test-only change; no file under `backend/` other than the test module was touched (verified by `git diff --name-only HEAD`).
- Task 3's ASOS narrow-window empty result was diagnosed rather than treated as a failure: widening the window (311 rows) and shifting the year (10 rows) both confirmed real upstream data availability, ruling out a code defect.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug/test-construction] Open-Meteo mock fixture changed from solar-only to full 5-column shape**
- **Found during:** Task 1
- **Issue:** The plan's `<behavior>` text specified an Open-Meteo mock carrying only `solar_radiation` at two timestamps, one of which (`00:10`) has no Synoptic or ASOS coverage. `PIPELINE_SCHEMA` requires `air_temp`/`wind_speed`/`wind_direction`, so a row built solely from that mock could never validate — contradicting the plan's own acceptance criteria and `must_haves.truths`.
- **Fix:** Mock returns the full 5-column set `fetch_open_meteo` always returns in production (confirmed by re-reading its own body-shape validation, which never emits a partial variable set).
- **Files modified:** `backend/tests/weather_provider_test.py` (test-only)
- **Verification:** `git diff --name-only HEAD` confirms no file under `backend/` other than the test module changed; full suite 250 passed, 0 failed.
- **Committed in:** `753dd4d` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 test-construction bug fix)
**Impact on plan:** Necessary for the plan's own must_haves.truths to be satisfiable; no scope creep, no production-code change.

## Issues Encountered

None beyond the deviation above. Task 3's ASOS empty-window result was investigated as designed by the plan's own `<how-to-verify>` instructions and resolved as expected sensor-gap behavior, not a bug.

## User Setup Required

None — no external service configuration required. Both providers are unauthenticated and no new `.env` entry was added (ROADMAP Success Criterion 4, confirmed at both the source level and by live endpoint check).

## Next Phase Readiness

- WX-02 and WX-04 are both demonstrably closed: ASOS supplements the station path with converted units and honest provenance, and one Open-Meteo request backfills the full variable set — proven together in one merged frame, not just in isolation.
- ROADMAP Phase 7 Success Criteria 3 and 4 are both satisfied and asserted at the source/test level, with Criterion 4's no-credential claim additionally confirmed by a live human check.
- The C4 spec describes the module as it now is; the ECE 464 disclosure is current.
- The weather-provider decision (`PRD.md` §7.1) remains formally open — `git diff --name-only HEAD` confirms neither `PRD.md` nor `data_provider.md` was touched anywhere in this phase. Phase 10 (WX-08) still owns ratifying it.
- Phase 7 (Trivial-Integration Providers) is complete. Phase 8 (NSRDB, gated on a registered NREL developer API key per STATE.md Blockers/Concerns) is next per the v1.1 roadmap sequencing.

---
*Phase: 07-trivial-integration-providers*
*Completed: 2026-09-12*

## Self-Check: PASSED

All 3 modified files (`backend/tests/weather_provider_test.py`, `docs/data-science/specs/C4-weather-ingestion.md`, `ACKNOWLEDGEMENTS.md`) and this SUMMARY confirmed present on disk; both task commits (`753dd4d`, `63f640c`) confirmed present in `git log`.
