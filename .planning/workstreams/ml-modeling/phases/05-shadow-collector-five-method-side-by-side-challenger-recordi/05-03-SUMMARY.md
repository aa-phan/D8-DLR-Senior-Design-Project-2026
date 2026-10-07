---
phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi
plan: 03
subsystem: data-science
tags: [shadow-collector, five-candidate, scheduled-entry-point, live-cycle]

# Dependency graph
requires:
  - phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi
    provides: "run_once_all_methods, the five-candidate orchestration entry point (05-02)"
provides:
  - "collect_once (the real cron-triggered scheduled entry point) now drives every corridor through run_once_all_methods, not the old one-candidate literal"
  - "A real two-corridor live cycle proving schema_version:2 output and per-candidate isolation hold at the actual scheduled-job scale"
affects: [05-05]

# Actuals (#2632)
actuals:
  tokens: 1700
  tasks: 2
  commits: 1

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One-line call-site generalization: collect_once's existing per-corridor loop, lock, delay, and exit-code logic were already corridor-agnostic; only the method call inside the loop changed"

key-files:
  created: []
  modified:
    - backend/forecast_shadow_collect.py
    - backend/tests/forecast_shadow_collect_test.py

key-decisions:
  - "No code commit for Task 2 (the real live cycle) — it writes only to the git-ignored data/shadow/predictions/ directory, same precedent as 05-02 Task 2; its result is recorded here and committed as part of this plan's closing docs commit."

requirements-completed: [D-01, D-02, D-07, D-10]

coverage:
  - id: D1
    description: "collect_once calls run_once_all_methods for every corridor in config.CORRIDOR_ENDPOINTS, not just one hardcoded method"
    requirement: "D-01"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_collect_test.py (all 5 tests, updated monkeypatch target)"
        status: pass
      - kind: other
        ref: "grep confirms run_once_all_methods present, \"ml_wind_corrected\" literal absent from forecast_shadow_collect.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Real two-corridor live cycle produces schema_version-2 records with all five candidates attempted at each corridor"
    requirement: "D-02"
    verification:
      - kind: other
        ref: "live run, both corridors, 2026-10-07 ~21:32 UTC decision_time -- see Live Cycle Result below"
        status: pass
    human_judgment: false
  - id: D3
    description: "hard_failure stays scoped to a genuine exception escaping run_once_all_methods itself, never an individually unavailable/failed candidate"
    requirement: "D-07"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_collect_test.py::test_collect_once_returns_one_on_a_hard_failure_but_still_tries_every_corridor (unchanged assertion intent, now against run_once_all_methods)"
        status: pass
      - kind: other
        ref: "live run: 4 of 5 candidates per corridor reported ok/unavailable, zero hard failures, exit=0"
        status: pass
    human_judgment: false
  - id: D4
    description: "Verification includes targeted tests, one real live cycle, and wall-clock duration measured against the workflow's 15-minute budget"
    requirement: "D-10"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_collect_test.py (5/5 pass)"
        status: pass
      - kind: other
        ref: "real two-corridor live cycle, ~32s wall-clock, well under the 15-minute (900s) GitHub Actions timeout-minutes budget"
        status: pass
    human_judgment: false

duration: ~20 min
completed: 2026-10-07
status: complete
---

# Phase 5 Plan 3: Wire the Scheduled Collector to the Five-Candidate Orchestrator, Live-Proven at Both Corridors Summary

**`collect_once` (the real cron-triggered entry point) now drives all five candidates per corridor via `run_once_all_methods`, proven by one real two-corridor live cycle completing in ~32 seconds with zero hard failures.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-10-07
- **Tasks:** 2/2 completed
- **Files modified:** 2 (`backend/forecast_shadow_collect.py`, `backend/tests/forecast_shadow_collect_test.py`), plus `ACKNOWLEDGEMENTS.md`

## Accomplishments

- `collect_once`'s per-corridor loop now calls `forecast_shadow_demo.run_once_all_methods(corridor)` instead of the old hardcoded `run_once(corridor, "ml_wind_corrected")` — the single literal 05-RESEARCH.md identified as the entire gap this phase exists to close, now gone from the scheduled entry point.
- All 5 existing tests in `forecast_shadow_collect_test.py` updated to monkeypatch `run_once_all_methods` with a one-argument callable, preserving each test's own assertion intent (corridor coverage, sleep timing, hard-failure propagation, lock contention, lock release) unchanged.
- The module docstring and inline comments updated to name `run_once_all_methods`; the lock (`_acquire_lock`/`_LOCK_PATH`), `INTER_CORRIDOR_DELAY_S`'s value, and the exit-code contract (0/1/2) are byte-for-byte unchanged.
- One real live collection cycle ran end to end for **both** corridors (`AUSTIN_CORPUS_CHRISTI`, `MIDLAND_EL_PASO`) against live Open-Meteo/TCEQ/Synoptic endpoints, exactly as the GitHub Actions workflow invokes the script, exiting 0.

## Task Commits

1. **Task 1: Wire collect_once to the five-candidate orchestrator for every corridor** - `df67281` (feat) -- 5/5 tests pass against the new monkeypatch target; `CALL_SITE_SWITCHED_OK` confirmed by grep.
2. **Task 2: One real live collection cycle across both corridors, measured for timing and inspected for isolation at scale** - no separate commit (writes only to the git-ignored `data/shadow/predictions/` directory, no code change); its result is recorded in this SUMMARY and committed as part of this plan's closing docs commit, per this task's own `<done>` criterion (same precedent as 05-02 Task 2).

## Files Created/Modified

- `backend/forecast_shadow_collect.py` — `collect_once`'s single call site generalized from `run_once(corridor, "ml_wind_corrected")` to `run_once_all_methods(corridor)`; module docstring and the per-corridor `except Exception` comment updated to describe the five-candidate orchestrator's failure semantics; lock/delay/exit-code logic untouched.
- `backend/tests/forecast_shadow_collect_test.py` — every `monkeypatch.setattr(forecast_shadow_demo, "run_once", ...)` call retargeted to `run_once_all_methods` with a one-argument lambda/function; module docstring updated to name the new monkeypatch target.
- `ACKNOWLEDGEMENTS.md` — AI-use disclosure entry for this session, per ECE 464 policy.

## Decisions Made

- Task 2 (the live cycle) produced no code commit, matching 05-02 Task 2's own precedent: it writes only to the git-ignored `data/shadow/predictions/` JSONL files, with zero source changes to inspect or commit — its result is narrated here and folded into the plan's closing docs commit.

## Deviations from Plan

None — plan executed exactly as written. The one-line call-site change, the test-file monkeypatch retarget, and the two-corridor live cycle all matched the plan's own description of scope with no additional fixes, architectural changes, or scope expansion required.

## Issues Encountered

None. Network reachability to Open-Meteo was confirmed before the live run (precondition met); no `SYNOPTIC_TOKEN` was required since TCEQ's own ASOS/Synoptic-fallback path inside `weather_provider.fetch_weather` resolved usable anchors for all four endpoint cities, same as 05-02's single-corridor run.

## Live Cycle Result (Task 2)

One real live cycle ran `backend/forecast_shadow_collect.py` end to end exactly as the scheduled GitHub Actions workflow invokes it (`PYTHONPATH=backend .venv/bin/python3 backend/forecast_shadow_collect.py`), covering both corridors in a single invocation, against live Open-Meteo (forecast) and TCEQ/Synoptic (anchor) endpoints — no mocking. Exit code: **0**. Measured wall-clock duration: **~32 seconds** (well under the GitHub Actions workflow's 15-minute/900-second `timeout-minutes` budget — no headroom concern at the current two-corridor scale, even with 5x the per-corridor in-process compute of the old single-method collector; no new network calls were added per D-02's shared-fetch design).

Both corridors' freshly appended JSONL lines (`data/shadow/predictions/AUSTIN_CORPUS_CHRISTI.jsonl`, `data/shadow/predictions/MIDLAND_EL_PASO.jsonl`, both git-ignored) were parsed directly and confirmed to carry `schema_version: 2` with all five candidate names present:

| Corridor | `ml_wind_corrected` | `ml_cooling_corrected` | `raw_forecast` | `persistence_24h` | `reference_ml_refit_24h` |
|---|---|---|---|---|---|
| AUSTIN_CORPUS_CHRISTI | **ok** (1074.24 A) | **ok** (1186.68 A) | **ok** (1086.52 A) | unavailable — cold start/gap, no prior entry within tolerance | unavailable — no persisted artifact yet |
| MIDLAND_EL_PASO | **ok** (1206.81 A) | **ok** (1078.37 A) | **ok** (1082.84 A) | unavailable — cold start/gap, no prior entry within tolerance | unavailable — no persisted artifact yet |

No candidate reported `status="failed"` at either corridor — the three already-implemented live candidates succeeded at both corridors, and `persistence_24h`/`reference_ml_refit_24h` each reported an honestly-named, expected `unavailable` reason (cold start for persistence since this run landed close in time to 05-02's own first-ever schema_version:2 entry for AUSTIN_CORPUS_CHRISTI and the first-ever entry for MIDLAND_EL_PASO; missing artifact for the refit candidate, expected per D-04 until 05-04 fits and commits it).

Per D-11, this result is reported strictly as operational completeness (ran end to end at both corridors, exit 0, physically plausible values, honest unavailable markers where expected) — no claim is made about which candidate is more accurate or better-calibrated than another.

## User Setup Required

None — no external service configuration required. The live run succeeded using this environment's existing network reachability to Open-Meteo and TCEQ/Synoptic.

## Next Phase Readiness

- The scheduled entry point now drives all five candidates at both corridors; the remaining D-10 verification item this phase still owes — confirmation that the **next scheduled (cron-triggered)** GitHub Actions run (not a manual/local one) persists the expanded five-candidate shape to `shadow-collection-data` — is explicitly deferred to 05-05 per this plan's own scope boundary (05-03 proves the call-site change and a real live cycle; it does not itself wait for or dispatch the next cron tick).
- `reference_ml_refit_24h` remains `unavailable` at both corridors until 05-04 fits and commits the real 24-hour refit artifact.
- `persistence_24h` will begin resolving to real values once each corridor has a second schema_version:2 entry landing within the ~24h/90-minute tolerance window of a future cycle's `decision_time` — expected cold-start behavior at both corridors now, not a defect.

---
*Phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi*
*Completed: 2026-10-07*

## Self-Check: PASSED

- `backend/forecast_shadow_collect.py` - FOUND
- `backend/tests/forecast_shadow_collect_test.py` - FOUND
- This SUMMARY.md - FOUND
- Commit `df67281` - FOUND in `git log --oneline --all`
