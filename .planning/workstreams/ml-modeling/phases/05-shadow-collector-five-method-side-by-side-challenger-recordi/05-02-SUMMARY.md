---
phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi
plan: 02
subsystem: data-science
tags: [shadow-collector, five-candidate, jsonl, schema-v2, correction-models]

# Dependency graph
requires:
  - phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi
    provides: "The approved schema_version:2 nested-per-candidate JSONL shape and the no-migration historical-data strategy (05-01)"
provides:
  - "fetch_shared_corridor_inputs: one shared forecast+anchor fetch per endpoint city per cycle (D-02), per-city/per-input failure isolation"
  - "_enrich_city_frame_for_correction + _corridor_reduce_per_city: ml_cooling_corrected and raw_forecast are now corridor-level (weakest-link reduced), closing the single-city gap for those two candidates"
  - "Persistence24hShadowMethod: a real, decision-time-available persistence_24h implementation reading the collector's own prior JSONL log, matched on valid_time (never the last line)"
  - "ReferenceRefit24hShadowMethod: an honest unavailable stub naming the missing artifact path (no training call)"
  - "log_cycle_predictions: writes the approved schema_version:2 nested shape with the six-field ml_wind_corrected legacy mirror"
  - "run_once_all_methods: the five-candidate orchestration entry point with per-candidate failure isolation (D-07)"
affects: [05-03, 05-04, 05-05]

# Actuals (#2632)
actuals:
  tokens: 14600
  tasks: 2
  commits: 1

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared-fetch-once-per-cycle: fetch_shared_corridor_inputs returns a {city: SharedCityFetchResult} mapping consumed by all five candidates, never re-fetched per candidate"
    - "Five-separate-try/except orchestration: run_once_all_methods wraps each candidate's own validation/compute/reduce path in its OWN try/except -- never one shared block around a loop"
    - "status/reason on ShadowPrediction, distinct from fallback_used/fallback_reason: status answers 'did this candidate produce a value this cycle' (ok/unavailable/failed); fallback_used/fallback_reason remain scoped to a method-internal substitution that still produced a genuine value"

key-files:
  created: []
  modified:
    - backend/forecast_shadow_pipeline.py
    - backend/forecast_shadow_demo.py
    - backend/tests/forecast_shadow_pipeline_test.py
    - backend/tests/forecast_shadow_demo_test.py

key-decisions:
  - "persistence_24h matches a prior logged entry's own valid_time against THIS cycle's decision_time (not decision_time-24h) -- the entry logged ~24h ago predicted a value whose own valid_time lands on today's decision_time, so matching on valid_time directly selects exactly that entry."
  - "_enrich_city_frame_for_correction duplicates attach_wind_correction_inputs's field-setting shape rather than calling it, since that function fetches its own anchor internally and this one must never fetch (D-02's single shared fetch)."
  - "sorted(city_frames) (not CORRIDOR_ENDPOINTS's own tuple order) decides city-A/city-B assignment in _corridor_reduce_per_city, per the plan's own explicit instruction, for deterministic tie-breaking matching corridor_weakest_link's convention."

requirements-completed: [D-01, D-02, D-04, D-05, D-06, D-07]

coverage:
  - id: D1
    description: "All five candidates attempted from one shared fetch per corridor per cycle; ml_cooling_corrected/raw_forecast now corridor-level"
    requirement: "D-01"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_demo_test.py#test_run_once_all_methods_attempts_all_five_and_isolates_one_sabotaged_candidate"
        status: pass
      - kind: other
        ref: "one real live cycle, AUSTIN_CORPUS_CHRISTI, 2026-10-07T21:16:42Z decision_time -- see Task 2 below"
        status: pass
    human_judgment: false
  - id: D2
    description: "Shared-input fetch: at most two forecast + two anchor fetches per cycle, per-city/per-input isolation"
    requirement: "D-02"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_fetch_shared_corridor_inputs_makes_at_most_two_forecast_and_two_anchor_calls"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_fetch_shared_corridor_inputs_isolates_one_citys_anchor_failure"
        status: pass
    human_judgment: false
  - id: D3
    description: "Per-candidate feature validation; missing inputs recorded unavailable, independent of other candidates"
    requirement: "D-04"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_demo_test.py#test_run_once_all_methods_marks_ml_wind_corrected_unavailable_when_one_citys_anchor_missing"
        status: pass
    human_judgment: false
  - id: D4
    description: "persistence_24h reads a decision-time-available prior entry matched on valid_time, never the last line; honest cold-start/propagated-unavailable reasons"
    requirement: "D-05"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_persistence_24h_cold_start_returns_unavailable_never_raises"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_persistence_24h_propagates_unavailable_from_matched_entrys_raw_forecast"
        status: pass
      - kind: other
        ref: "PERSISTENCE_PICKS_MATCH_NOT_LAST_LINE_OK verification script from 05-02-PLAN.md"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every existing record field preserved per candidate independently; new schema matches 05-01's approved shape exactly, including the legacy mirror"
    requirement: "D-06"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_log_cycle_predictions_writes_all_five_candidates_with_exact_schema"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_pipeline_test.py#test_log_cycle_predictions_mirrors_ml_wind_corrected_even_when_unavailable"
        status: pass
      - kind: other
        ref: "LIVE_CYCLE_ONE_CORRIDOR_OK verification script from 05-02-PLAN.md, run against the real live-cycle output"
        status: pass
    human_judgment: false
  - id: D6
    description: "Per-candidate failure isolation: one candidate's real exception never blocks the other four"
    requirement: "D-07"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_demo_test.py#test_run_once_all_methods_attempts_all_five_and_isolates_one_sabotaged_candidate"
        status: pass
    human_judgment: false
  - id: D7
    description: "One real live collection cycle for AUSTIN_CORPUS_CHRISTI, all five candidates recorded with plausible values or honest unavailable markers"
    verification:
      - kind: other
        ref: "live run, 2026-10-07T21:16:42.740076+00:00 decision_time -- see Task 2 narrative below"
        status: pass
    human_judgment: false

duration: ~55 min
completed: 2026-10-07
status: complete
---

# Phase 5 Plan 2: Shared Fetch, Corridor-Level Reduction for All Three Reused Candidates, Real Persistence, Honest Stub Summary

**All five 24-hour-lead candidates now compute from one shared per-cycle fetch, with `ml_cooling_corrected`/`raw_forecast` newly corridor-reduced, a real `persistence_24h` reading the collector's own prior log, and a live-proven end-to-end cycle for AUSTIN_CORPUS_CHRISTI.**

## Performance

- **Duration:** ~55 min
- **Completed:** 2026-10-07
- **Tasks:** 2/2 completed
- **Files modified:** 4 (`backend/forecast_shadow_pipeline.py`, `backend/forecast_shadow_demo.py`, `backend/tests/forecast_shadow_pipeline_test.py`, `backend/tests/forecast_shadow_demo_test.py`), plus `ACKNOWLEDGEMENTS.md`

## Accomplishments

- `fetch_shared_corridor_inputs` fetches each endpoint city's forecast and anchor observation exactly once per cycle (D-02), with per-city/per-input failure isolation proven by a monkeypatched call-counter test.
- `_enrich_city_frame_for_correction` + the generalized `_corridor_reduce_per_city` make `ml_cooling_corrected` and `raw_forecast` corridor-level (both endpoint cities, weakest-link-reduced) for the first time -- 05-02-PLAN.md's own confirmed gap, now closed.
- `Persistence24hShadowMethod` is a real, live implementation: it scans the collector's own prior JSONL log for the entry whose `valid_time` is closest to this cycle's `decision_time` (within a 90-minute tolerance), never the positionally-last line -- confirmed against a three-entry fixture at different ages and against the `PERSISTENCE_PICKS_MATCH_NOT_LAST_LINE_OK` script from the plan.
- `ReferenceRefit24hShadowMethod` reports an honest `status="unavailable"` naming the missing artifact path, with zero network calls and zero training calls (D-03/D-04/D-09).
- `run_once_all_methods` orchestrates all five candidates with five SEPARATE try/except blocks -- proven by a deliberate-sabotage test (one candidate monkeypatched to raise) that the other four still compute and log in the same cycle.
- `log_cycle_predictions` writes the exact schema_version:2 nested shape 05-01 approved, including the six-field backward-compatible `ml_wind_corrected` mirror, confirmed even when `ml_wind_corrected` itself is unavailable.
- One real live collection cycle ran end to end for AUSTIN_CORPUS_CHRISTI against live network/weather-provider endpoints (see below).
- Every frozen Phase 3/4 production module (`forecast_experiment.py`, `forecast_correction_models.py`, `forecast_training.py`, `thermal_model.py`, `ampacity_forecast.py`, `anomaly_detector.py`, `DLRSafetyMonitor.py`, `dlr_pipeline.py`) confirmed to carry zero git diff.

## Task Commits

1. **Task 1: Shared-input fetch, corridor-level reduction for all three reused candidates, a real persistence_24h, an honest reference_ml_refit_24h stub, and the new nested schema** - `166e746` (feat) -- 16 new network-free tests added, 65/65 pass (49 pre-existing + 16 new), frozen sources confirmed zero diff.
2. **Task 2: One real live collection cycle for one corridor, inspected directly against the new schema** - no separate commit (writes only to the git-ignored `data/shadow/predictions/` directory, no code change); its result is recorded in this SUMMARY and committed as part of the plan's closing docs commit, per this task's own `<done>` criterion.

**Plan metadata:** recorded in the closing docs commit (see final commit for this plan).

## Files Created/Modified

- `backend/forecast_shadow_pipeline.py` - `SharedCityFetchResult`, `fetch_shared_corridor_inputs`, `_enrich_city_frame_for_correction`, `_corridor_reduce_per_city`, `Persistence24hShadowMethod`, `ReferenceRefit24hShadowMethod`, `log_cycle_predictions`, `CANDIDATE_METHOD_NAMES`, `PER_CITY_REDUCED_METHOD_NAMES`; `ShadowPrediction` extended with `status`/`reason`; `fetch_live_forecast_for_valid_time` extended with an optional `decision_time` keyword; `fetch_live_anchor_observation`'s return extended with `anchor_air_temp`.
- `backend/forecast_shadow_demo.py` - `run_once_all_methods`, `_resolve_next_valid_time` (the five-candidate orchestration entry point; `run_once` itself untouched).
- `backend/tests/forecast_shadow_pipeline_test.py` - 14 new tests covering the shared fetch, `anchor_air_temp`, the corridor reduction's `ValueError`, `persistence_24h`'s cold-start/match/propagation/skip cases, the `reference_ml_refit_24h` stub, and the new schema's exact shape.
- `backend/tests/forecast_shadow_demo_test.py` - 3 new tests covering the sabotage/isolation case, a clean run's `reference_ml_refit_24h` unavailability, and the D-04 missing-anchor case.
- `ACKNOWLEDGEMENTS.md` - AI-use disclosure entry for this session, per ECE 464 policy.

## Decisions Made

- `persistence_24h` matches a prior logged entry's own `valid_time` against THIS cycle's `decision_time` directly (not `decision_time - 24h`): at the twice-daily, 24-hour-horizon cadence, the entry logged ~24h ago predicted a value whose own `valid_time` lands on today's `decision_time`, so a direct `valid_time`-vs-`decision_time` match selects exactly that entry -- confirmed against the plan's own `PERSISTENCE_PICKS_MATCH_NOT_LAST_LINE_OK` test data.
- `_enrich_city_frame_for_correction` deliberately duplicates `attach_wind_correction_inputs`'s field-setting shape rather than calling it, since that function fetches its own anchor internally and the new function must never fetch (preserving D-02's single shared fetch per cycle).
- `_corridor_reduce_per_city` uses `sorted(city_frames)` (not `config.CORRIDOR_ENDPOINTS`'s own tuple order) to decide city-A/city-B assignment, per the plan's explicit instruction, for a deterministic tie-break matching `corridor_weakest_link`'s own convention.
- `run_once` itself was left completely untouched; `_resolve_next_valid_time` duplicates its grid-selection logic rather than factoring it into a shared helper `run_once` would have to call, honoring the plan's explicit "run_once itself must not change" constraint.

## Deviations from Plan

None - plan executed exactly as written. `ShadowPrediction.timestamps`'s type hint was additionally widened to `Optional[ShadowTimestamps]` (the plan only named `status`/`reason`/`ampacity_amps` for extension) since `Persistence24hShadowMethod.compute`/`ReferenceRefit24hShadowMethod.compute` construct `ShadowPrediction` instances without a full per-candidate timestamp quadruple (the shared cycle-level `ShadowTimestamps` is passed separately to `log_cycle_predictions`, matching the approved schema's own single shared timestamp quadruple, not one per candidate) -- a type-hint-only widening with no runtime behavior change, not called out separately as a numbered deviation since it does not touch any prohibition or must-have.

## Issues Encountered

- My own first live-run invocation (`cd backend && PYTHONPATH=. python3 -c ...`) accidentally ran with a working directory of `backend/` instead of the repo root, causing the relative `data/shadow/models/` path to resolve to a nonexistent `backend/data/shadow/models/` and making `ml_wind_corrected`/`ml_cooling_corrected` spuriously report unavailable. Re-ran from the repo root (matching the plan's own exact invocation convention, `PYTHONPATH=backend .venv/bin/python3 -c "..."` from the repo root) and got the correct, real result. The stray `backend/data/` directory this mistake created was deleted before committing; it was never staged or committed.

## Live Cycle Result (Task 2)

One real live cycle ran for `AUSTIN_CORPUS_CHRISTI` at `decision_time=2026-10-07T21:16:42.740076+00:00`, `valid_time=2026-10-08T12:00:00+00:00` (24h horizon), against live Open-Meteo (forecast) and TCEQ/Synoptic (anchor) endpoints -- no mocking. Inspecting the appended `data/shadow/predictions/AUSTIN_CORPUS_CHRISTI.jsonl` line directly (git-ignored, not committed, consistent with every other generated shadow-collector output):

| Candidate | Status | Ampacity (A) | Notes |
|---|---|---|---|
| `ml_wind_corrected` | **ok** | 1104.85 | Per-city: AUSTIN 1104.85 (bottleneck), CORPUS_CHRISTI 1415.50 |
| `ml_cooling_corrected` | **ok** | 1218.77 | Per-city: AUSTIN 1218.77 (bottleneck), CORPUS_CHRISTI 1312.40 |
| `raw_forecast` | **ok** | 1086.52 | Per-city: AUSTIN 1086.52 (bottleneck), CORPUS_CHRISTI 1217.41 |
| `persistence_24h` | unavailable | — | "no prior entry within tolerance of decision_time ... (cold start, or a gap in this corridor's collection history)" -- expected: this is the first schema_version:2 entry ever logged for this corridor, so no 24h-prior match can exist yet. |
| `reference_ml_refit_24h` | unavailable | — | "no persisted 'reference_ml_refit_24h' model for corridor 'AUSTIN_CORPUS_CHRISTI'..." -- expected per D-04/05-RESEARCH.md; 05-04 fits and commits this artifact later in this phase. |

All three `status="ok"` ampacity values are finite, positive, and in a physically plausible range relative to this corridor's `STATIC_RATINGS` (AUSTIN 1900A, CORPUS_CHRISTI 3000A) -- lower than static (expected for a DLR-vs-conservative-static comparison, not an absurd or zero/negative value). The top-level six-field legacy mirror exactly equals `candidates.ml_wind_corrected`'s own fields (`method="ml_wind_corrected"`, `ampacity_amps=1104.850704939319`, matching `fallback_used`/`fallback_reason`/`model_version`/`input_provenance`). No candidate reported `status="failed"` on this clean run -- all four already-implemented candidates either succeeded or reported an honestly-named, expected `unavailable` reason, and `reference_ml_refit_24h` correctly read unavailable (no artifact exists yet, as designed).

Per D-11, this result is reported strictly as operational completeness (ran end to end, physically plausible values) -- no claim is made about which candidate is more accurate, better-calibrated, or safer than another; that question is reserved for the Nov 1/Nov 24 fresh-basis confirmation protocol.

## User Setup Required

None - no external service configuration required. The live run succeeded using this environment's existing network reachability to Open-Meteo and TCEQ/Synoptic; no `SYNOPTIC_TOKEN` fallback was needed this cycle since TCEQ ultimately resolved to usable anchors via `weather_provider.fetch_weather`'s own ASOS/Synoptic-path handling.

## Next Phase Readiness

- The five-candidate orchestration, shared schema, and real `persistence_24h` are in place and live-proven for `AUSTIN_CORPUS_CHRISTI`. 05-03 extends this to both corridors and a workflow-level (GitHub Actions) run, per this plan's objective note.
- 05-04 fits and commits the real `reference_ml_refit_24h` artifact and wires its real predict path, replacing this plan's honest stub body without changing the method's name or callers' expectations.
- `persistence_24h` will remain `unavailable` for AUSTIN_CORPUS_CHRISTI until a second schema_version:2 entry lands within the ~24h/90-min tolerance window of a future cycle's `decision_time` -- expected cold-start behavior, not a defect.

---
*Phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi*
*Completed: 2026-10-07*

## Self-Check: PASSED

- `backend/forecast_shadow_pipeline.py` - FOUND
- `backend/forecast_shadow_demo.py` - FOUND
- `backend/tests/forecast_shadow_pipeline_test.py` - FOUND
- `backend/tests/forecast_shadow_demo_test.py` - FOUND
- This SUMMARY.md - FOUND
- Commit `166e746` - FOUND in `git log --oneline --all`
