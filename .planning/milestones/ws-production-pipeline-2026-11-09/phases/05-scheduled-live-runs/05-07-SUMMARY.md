---
phase: 05-scheduled-live-runs
plan: 07
subsystem: infra
tags: [cron-job.org, github-actions, workflow_dispatch, fault-drill, supabase, failure-isolation]

requires:
  - phase: 05-scheduled-live-runs
    provides: "dlr_live.yml on origin/main, fault_city drill input, pipeline_run log, runbook sections 2 and 8 (05-01..05-06)"
provides:
  - "Hourly cron-job.org trigger of dlr_live.yml (owner-created), verified: first scheduled run 40145300072 at 00:05:05Z"
  - "Start of the 24 h window for 05-08: run 40145300072, created 2026-10-25T00:05:05Z, slot 2026-10-25 00:00 UTC"
  - "Fault-drill evidence (SC 3): MIDLAND drill run 40146481713 red, three cities written, MIDLAND in cities_failed; next scheduled run 40149224957 green with four cities"
affects: [05-08, 06-freshness-check]

actuals:
  tokens: 0
  tasks: 2
  commits: 0
  plan_head_before: 9179a6bda237c3a6d99bfd0f16686dd4c7b25ddb
  plan_head_after: 9179a6bda237c3a6d99bfd0f16686dd4c7b25ddb

tech-stack:
  added: []
  patterns:
    - "External hourly dispatch (cron-job.org -> workflow_dispatch) at minute 05 UTC, window end floored to 5 min, slot = hour floor"
    - "Production fault drill with one city's credentials blanked; failure isolated and recorded in pipeline_run.cities_failed"

key-files:
  created: []
  modified: []

key-decisions:
  - "A run created by the owner's cron-job.org test (40144431987, 23:51:40Z) is counted as a manual run, not the window start"
  - "Window start is the first dispatch created within 5 min after an hh:05 boundary: 40145300072 (00:05:05Z)"

requirements-completed: [PIPE-02, SCHED-01, SCHED-02]

coverage:
  - id: D1
    description: "cron-job.org dispatches dlr_live.yml hourly; the first scheduled run is workflow_dispatch, created 5 s after the 00:05 UTC boundary, and succeeded with four cities in cities_ok"
    requirement: SCHED-02
    verification:
      - kind: integration
        ref: "gh run view 40145300072 --json event,createdAt,conclusion; read-only pipeline_run check (cities_ok = 4, finished_at set)"
        status: pass
    human_judgment: false
  - id: D2
    description: "MIDLAND fault drill: run red, AUSTIN, CORPUS_CHRISTI and EL_PASO written with the drill run_id, MIDLAND absent, MIDLAND in cities_failed with outcome error, written false, fault_injected true"
    requirement: SCHED-01
    verification:
      - kind: integration
        ref: "gh run view 40146481713 --json conclusion -> failure; read-only city_rating and pipeline_run checks for run 40146481713"
        status: pass
    human_judgment: false
  - id: D3
    description: "The next scheduled run after the drill (40149224957, 01:05:04Z) succeeded with four cities in cities_ok"
    requirement: SCHED-01
    verification:
      - kind: integration
        ref: "gh run list --workflow dlr_live.yml --limit 5 -> success,failure,success,success,success; read-only pipeline_run check for run 40149224957"
        status: pass
    human_judgment: false
  - id: D4
    description: "The dispatch token is held only by cron-job.org, is scoped to this repository, and expires after the project ends"
    requirement: SCHED-02
    verification: []
    human_judgment: true
    rationale: "Token scope and expiry are owner-reported; the executor cannot see the token or the cron-job.org account. Enable time was not provided"

duration: about 2h 10m (mostly waiting on hh:05 slots)
completed: 2026-10-25
status: complete
---

# Phase 5 Plan 07: Hourly trigger live and one-city fault drill Summary

**The owner's hourly cron-job.org job dispatched dlr_live.yml at 00:05:05Z (first scheduled run, 40145300072, all four cities ok, start of the 24 h window), a MIDLAND fault drill (40146481713) went red while AUSTIN, CORPUS_CHRISTI and EL_PASO still wrote and MIDLAND was recorded in cities_failed, and the 01:05 scheduled run (40149224957) was green with four cities.**

## Performance

- **Duration:** about 2 h 10 min wall clock for this continuation (waiting on hh:05 slots); no repository changes
- **Started:** 2026-10-24T23:52Z (continuation after Task 1)
- **Completed:** 2026-10-25T01:10Z
- **Tasks:** 2 (Task 1 owner action, Task 2 drill)
- **Files modified:** 0 (evidence only)

## Task 1: owner action (cron-job.org job and token)

- Owner replied "job created".
- **Enable time (UTC): not provided by owner.**
- **Token expiry: mid-December 2026 (owner-stated, after project end).** The owner considers expiry not a concern and wants no reminder, so the runbook reminder is intentionally not set. The token value was never seen or recorded.
- A run at 23:51:40Z (40144431987, workflow_dispatch, not an hh:05 slot) is the owner's cron-job.org test run: it proves the token and the dispatch path work. It is counted as a **manual** run, not the window start. It succeeded in 62 s; `pipeline_run` shows four cities in cities_ok, finished_at set, window_end 23:50, slot 23:00. It overwrote the 23:00 slot rows written by the 05-06 manual run (OD-7 same-slot overwrite).

## SC 1: first scheduled run = start of the 24 h window

| Item | Result |
|---|---|
| Run id | 40145300072 |
| Event | workflow_dispatch (cron-job.org) |
| createdAt | 2026-10-25T00:05:05Z (5 s after the 00:05 UTC boundary; limit was 5 min) |
| Slot / window end | slot 2026-10-25 00:00:00+00; window_end 00:05:00+00 |
| Conclusion | success (00:05:05Z to 00:12:16Z, about 7 min) |
| `pipeline_run` | 1 row, started_at 00:05:48, finished_at 00:12:14 (not null), cities_ok = [AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO], cities_failed = {} |
| `city_rating` | 4 rows with this run_id, one distinct valid_time, all status ok (no fallbacks): AUSTIN 1302.9, CORPUS_CHRISTI 1717.1, EL_PASO 1534.8, MIDLAND 1828.6 A |

**24 h window start for 05-08: run 40145300072, created 2026-10-25T00:05:05Z, slot 00:00 UTC (first expected scheduled slots thereafter 01:00, 02:00, ...).**

## SC 3: MIDLAND fault drill

Dispatched 2026-10-25T00:23:07Z with `gh workflow run dlr_live.yml --ref main -f fault_city=MIDLAND` (once only), 11 min after the 00:05 run finished and 42 min before the 01:05 boundary.

| Item | Result |
|---|---|
| Run id / conclusion | 40146481713, **failure** (red); step "Run live pipeline" failed, pre-flight passed; 47 s |
| Log | `DLR_LIVE_FAULT_CITY: MIDLAND`; "MIDLAND: fault drill, provider credentials blanked for this child"; "MIDLAND: error in 0.5s" |
| `city_rating` with the drill run_id | 3 rows: AUSTIN (fallback 1825.0), CORPUS_CHRISTI (ok 1474.6), EL_PASO (ok 1552.7); none for MIDLAND (count with this run_id = 0) |
| MIDLAND slot 00:00 row | still present with the earlier scheduled run's run_id 40145300072 (OD-9: drill wrote no MIDLAND row) |
| `pipeline_run` | 1 row, window_end 00:20:00+00, finished_at set; cities_ok = [AUSTIN, CORPUS_CHRISTI, EL_PASO]; cities_failed = {MIDLAND: outcome "error", written false, exit_code 1, fault_injected true, duration_s 0.5, forecast_status not_run} (raised `EnvironmentError` "Set SYNOPTIC_TOKEN" in `_discover_stations`, as designed) |

## Next scheduled run after the drill

| Item | Result |
|---|---|
| Run id | 40149224957, workflow_dispatch, created 2026-10-25T01:05:04Z (4 s after the boundary) |
| Conclusion | success (01:05:04Z to 01:07:38Z) |
| `pipeline_run` | cities_ok = [AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO], cities_failed = {}, finished_at set |
| `city_rating` | 4 rows, slot 01:00: AUSTIN 1825.0 (fallback), CORPUS_CHRISTI 1488.9, EL_PASO 1124.8, MIDLAND 1851.6 |

Verify command output (`gh run list ... select(.event=="workflow_dispatch") | map(.conclusion)`): `success,failure,success,success,success` (newest first: the 01:05 run, the drill, then the 00:05 run, and the two earlier manual runs). Contains "failure" with a more recent "success".

Checks were made by a read-only scratch script outside the repository (counts, city names and columns only; database URL not printed; `.env` not read with the Read tool).

## Task Commits

No code or documentation commits for Tasks 1 and 2 (external state and evidence only). `commits: 0` is measured: `plan_head_before` equals `plan_head_after` (9179a6b). Plan metadata commit follows this SUMMARY.

## Files Created/Modified

None. `git status --porcelain -- backend .github docs data` lists only pre-existing items that predate this plan (two `.DS_Store` files modified and untracked `docs/data-science/decisions/shadow_early_decision_options.md`); no file in `backend`, `.github` or `data` changed.

## Decisions Made

- The cron-job.org test run (40144431987) is a manual run and not the window start, as the plan prescribes.
- Window start taken from the first run created within 5 minutes after an hh:05 boundary (00:05:05Z).

## Deviations from Plan

None - plan executed exactly as written. (The owner supplied the token expiry by a later message rather than with the "job created" reply.)

## Discrepancies

- **Enable time not provided.** The owner did not give the time the job was enabled. First observed dispatch was the owner's test run at 23:51:40Z; the first scheduled hh:05 dispatch was 00:05:05Z. Nothing was inferred beyond that.
- **Token expiry** is owner-stated (mid-December 2026, after project end); the owner declined a reminder. This is the owner's decision; it means the runbook's "calendar reminder before expiry" line is not followed, and an expiry before the project ends would make dispatches fail silently (runbook section 11).
- **Drill overwrote three scheduled ratings for slot 00:00.** Per OD-7 and T-05-32 (accepted), the drill's AUSTIN, CORPUS_CHRISTI and EL_PASO rows replaced the scheduled run's rows for the 00:00 slot (their `first_written_at` is retained from the scheduled run; `run_id` is now the drill's). Notably AUSTIN's 00:00 slot is now a fallback (1825.0 A) where the scheduled run had a live ok rating (1302.9 A). MIDLAND's 00:00 row still carries the scheduled run_id. A 24 h check by run_id should treat 00:00 as drill-affected: for that slot, `city_rating.run_id` is 40146481713 for three cities and 40145300072 for MIDLAND.
- **Run durations vary widely** (47 s drill, 62 s test run, 2.5 min at 01:05, 7 min at 00:05). Not a fault; EL_PASO and CORPUS_CHRISTI appear to take the longest. Worth a look in 05-08's minutes and duration summary.
- **AUSTIN is a `fallback` rating in the 01:05 run and the drill** (1825.0 A), while ok in the 00:05 run. Cause not inspected here; same pattern noted for AUSTIN in 05-06.
- **Step summary not read directly** (gh exposes no step-summary content); the run log lines, step conclusions and database rows were used instead, as in 05-06.
- The anon-refusal check (T-05-29) from 05-06 remains open and was not part of this plan.

## Issues Encountered

- Long waits for hh:05 slots exceeded the 10 minute tool timeout several times; loops were re-issued across calls. No effect on results.

## User Setup Required

None further. Owner-side items: the cron-job.org job and token exist (Task 1 done). Failure notifications on the job are owner-configured and were not checked by the executor.

## Next Phase Readiness

- Ready for 05-08: the 24 h window runs from 2026-10-25T00:05:05Z (run 40145300072); the earliest full 24 h check is after 2026-10-26T00:05Z. The 00:00 slot is drill-affected (see Discrepancies).

## Known Stubs

None.

## Threat Flags

None. No new network endpoints, auth paths or schema changes were added; the token (T-05-30) is held by cron-job.org and was never seen by the executor, and the drill (T-05-31/T-05-32) ran once, for MIDLAND only, outside the 15 min pre-boundary guard.

## Self-Check: PASSED

- Runs 40145300072, 40146481713 and 40149224957 exist (`gh run view` returned their records).
- `plan_head_before` equals HEAD (9179a6b): no commits for tasks, matching `commits: 0`; no file in `backend`, `.github` or `data` changed.
- No token value appears in this file.
