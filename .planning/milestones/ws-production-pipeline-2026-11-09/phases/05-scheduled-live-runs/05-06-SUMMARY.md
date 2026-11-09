---
phase: 05-scheduled-live-runs
plan: 06
subsystem: infra
tags: [github-actions, workflow_dispatch, supabase, go-live, billing, public-repo]

requires:
  - phase: 05-scheduled-live-runs
    provides: "dlr_live.yml, runner, pipeline_run log, model pre-flight and runbook (05-01..05-05)"
provides:
  - "dlr_live.yml and the eight committed models on origin/main (fast-forward push, 702a833)"
  - "One verified live run (40141557468): four city_rating rows and one complete pipeline_run row in Supabase"
  - "Runbook section 12 with the owner's real Actions figures, the public-visibility decision and the first-run minutes"
affects: [05-07, 05-08, 06-freshness-check]

actuals:
  tokens: 4000
  tasks: 3
  commits: 3
  plan_head_before: 9441c56f0a344b00dcaca885f791ffb47df710d1
  plan_head_after: 49f0090913830f99671b7164ea18161dcbec7b5b

tech-stack:
  added: []
  patterns:
    - "Go-live through a fast-forward-only push, then exactly one manual dispatch verified read-only against Supabase"

key-files:
  created: []
  modified:
    - docs/data-science/decisions/dlr_live_runbook.md

key-decisions:
  - "Owner chose go-live at Task 2, after first making the repository public so Actions minutes are free"
  - "The anon-refusal check (T-05-29) is recorded as skipped, not passed"

requirements-completed: [PIPE-02, SCHED-02]

coverage:
  - id: D1
    description: "All four required repository secrets are present (names only)"
    requirement: SCHED-02
    verification:
      - kind: other
        ref: "gh secret list --json name --jq '.[].name' (Task 1, commit 9d4ba23)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Runbook section 12 holds the owner's real quota figures, the projection and the public-visibility update"
    requirement: SCHED-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py"
        status: pass
    human_judgment: true
    rationale: "The figures are the owner's own reading of the Billing page, derived from dollar amounts; only the owner can confirm they are right"
  - id: D3
    description: "dlr_live.yml is on origin/main by fast-forward push and lists only workflow_dispatch"
    requirement: PIPE-02
    verification:
      - kind: other
        ref: "git merge-base --is-ancestor 702a833 origin/main; gh workflow view dlr_live.yml --yaml | grep -cE '^\\s*(schedule|push|pull_request):' prints 0"
        status: pass
    human_judgment: false
  - id: D4
    description: "One manual dispatch rated all four cities into Supabase with a complete pipeline_run row"
    requirement: PIPE-02
    verification:
      - kind: integration
        ref: "gh run list --workflow dlr_live.yml --limit 1 --json conclusion -> success; read-only Supabase check for run 40141557468"
        status: pass
    human_judgment: false
  - id: D5
    description: "The run log (pipeline_run) is refused to the anon key"
    requirement: PIPE-02
    verification: []
    human_judgment: true
    rationale: "Not verified: the owner's .env has no SUPABASE_URL or publishable key, so no anon request was made. Owner to run it, or accept the Phase 4 grant review as the evidence"

duration: 40min
completed: 2026-10-24
status: complete
---

# Phase 5 Plan 06: Go-live and first verified live run Summary

**dlr_live.yml and the eight committed models are on origin/main by fast-forward push, and the first manual dispatch (run 40141557468) rated all four cities into Supabase with a complete pipeline_run row, after the owner made the repository public so Actions minutes cost nothing.**

## Performance

- **Duration:** about 40 min across two executor sessions plus the owner's decision
- **Completed:** 2026-10-24T23:14Z
- **Tasks:** 3 (Task 2 was the owner's decision, executed as go-live)
- **Files modified:** 1 (`docs/data-science/decisions/dlr_live_runbook.md`)

## Accomplishments

- Secrets confirmed by name with `gh secret list`: SYNOPTIC_TOKEN, NREL_API_KEY, NREL_API_EMAIL and SUPABASE_DB_URL are all present. No value was read or printed.
- Owner's billing figures and the projection recorded in runbook section 12: 2,000 included minutes already used (about 3,028 used, about 1,028 billed overage minutes, $6.17), reset 2026-11-01, projection about 4,148 minutes this cycle.
- Task 2 decision: **go-live**, taken after the owner made the repository public (2026-10-24) to remove the minutes cost. Section 12 now records that hosted-runner minutes are free for public repositories, keeps the measured figures as history, and lists the public-repo security posture.
- Fast-forward push `fde51cd..702a833` of exactly the 32 reviewed commits (05-01 to 05-06; origin/main was `fde51cd`) (`git log origin/main..main`, 40 files, 5,243 insertions; nine files under `data/models`: the eight models plus the manifest). `shadow_collect.yml` and `backend/forecast_shadow_*.py` were unchanged in the range (`git diff --quiet` exit 0) and `git merge-base --is-ancestor origin/main main` exited 0 immediately before the push. No force.
- `gh workflow view dlr_live.yml` resolves (workflow id 395493847); its YAML has only `workflow_dispatch` (0 matches for `schedule|push|pull_request`).
- One dispatch, verified end to end (below). Runbook live row updated with the first-run minutes.

## First live run (run 40141557468)

| Item | Result |
|---|---|
| Run id / event | 40141557468, `workflow_dispatch`, created 2026-10-24T23:09:24Z |
| Conclusion | success (job `rate`, 3 min 6 s) |
| Pre-flight step | success: "OK: all 8 live model artifacts present and match data/models/LIVE_ARTIFACT_HASHES.sha256" |
| Live step | success; runner log ends "live run 40141557468 attempt 1 finished, exit code 0" |
| Window / slot | window 2026-10-24T22:05Z to 23:05Z; slot (valid_time) 2026-10-24 23:00:00+00 |
| `city_rating` rows with this run_id | 4, one per city, all at valid_time 23:00:00+00 (1 distinct), run_attempt 1 |
| Per-city rows | AUSTIN 1825.0 A status fallback; CORPUS_CHRISTI 1465.26 A ok; EL_PASO 1320.0 A status fallback (126 s); MIDLAND 1849.61 A ok |
| `pipeline_run` row | 1 row: window_end 23:05:00+00, started_at 23:09:59, finished_at 23:12:28 (not null), cities_ok = [AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO], cities_failed = {} |
| Anon HTTP code (T-05-29) | **Not checked** (see Discrepancies) |
| Billed minutes | 4 (job 23:09:27 to 23:12:33 = 3 min 6 s, rounded up; run-level 190 s also rounds to 4). Free going forward: the repository is public |

Checked with a read-only script outside the repository (counts and column values only; the database URL is never printed), run from the main checkout against `SUPABASE_DB_URL` loaded from `.env`.

## Task Commits

1. **Task 1: secrets confirmed; billing figures and projection recorded** - `9d4ba23` (docs)
2. **Task 2: owner decision, go-live** - no code commit. Related docs commit: `702a833` (docs: record public visibility and free Actions minutes). The push of local main at `702a833` is the Task 3 outward action.
3. **Task 3: push, dispatch once, verify** - `49f0090` (docs: first live run measured); the push itself is origin/main `702a833`.

`actuals.commits` (3) is measured from the ledger base and excludes this SUMMARY and the state commit. Commits made after the push (`49f0090`, the SUMMARY and state commit) are local only; 05-08 pushes the final runbook with approval.

## Files Created/Modified

- `docs/data-science/decisions/dlr_live_runbook.md` - section 12: owner's billing figures and projection, the public-visibility update with the security posture, first-run minutes; section 11 and the header note adjusted for the public repository.

## Decisions Made

- Go-live chosen at Task 2, with the repository made public first. The prohibition "MUST NOT go live when the projection exhausts the quota with no spending allowance unless the owner chose that explicitly" was satisfied: the owner chose, and chose a route that removes the cost.
- The measured private-repository figures stay in the runbook as history rather than being deleted.

## Deviations from Plan

### Owner decision, not in the plan

**1. [Owner decision] Repository made public before go-live**
- **Found during:** Task 2
- **Issue:** The projection showed the account already past its 2,000 included minutes, so hourly runs would be billed overage (about $6 for the rest of the cycle, about $9 to $18 per month).
- **Action:** The owner chose to make the repository public (the orchestrator ran `gh repo edit --visibility public` on the owner's explicit instruction; `gh repo view` reports PUBLIC). Before that, all 904 commits of history were scanned for credential patterns (database URLs with passwords, Supabase and JWT keys, GitHub tokens, AWS and OpenAI keys, NREL and Synoptic token assignments) and for committed `.env` files: none found.
- **Executor work:** Runbook section 12, section 11 and the header updated; tests pass (`dlr_live_runbook_test.py`, `dlr_live_workflow_test.py`: 8 passed).
- **Files modified:** `docs/data-science/decisions/dlr_live_runbook.md`
- **Committed in:** `702a833`

**Total deviations:** 1 (owner decision). **Impact:** Removes the Actions-minutes cost (SCHED-02) but makes the eight model binaries, the data and the planning files public. The binaries were already accepted as permanent in history (OD-10); the wider exposure was an owner choice.

## Discrepancies

- **Anon-refusal check (T-05-29) skipped.** The owner's `.env` has no SUPABASE_URL and no publishable key, so the `curl` against `/rest/v1/pipeline_run` was not run. The truth "an anon-key request for pipeline_run is refused" is unverified. Because the repository is now public and `pipeline_run` is meant to be private, the owner should run this check (project URL plus publishable key) before Phase 6 consumers read the data.
- **Step summary not inspected directly.** `gh` exposes no step-summary content. The run's log lines, the green `Run live pipeline` step and the database rows were used instead.
- **Two of four cities are `fallback` ratings** (AUSTIN, EL_PASO), not failures: AUSTIN's fallback cause was not inspected (1825 A); EL_PASO failed gate G6 (rating 1690.9 A against a rolling baseline of 1118.2 A, band 590.3 to 1646.2 A) and fell back to 1320 A, with the forecast not used for G6 because of 623 missing hourly history slots. The pipeline_run row counts them as `cities_ok` because the ML path was healthy. This is data-quality behavior, not a workflow fault, but it means "four rows written" does not mean "four live ratings from the model".
- **Open-Meteo ReadTimeout (x2)** was logged for EL_PASO's solar provider; the run still succeeded. EL_PASO took 126 s against the 300 s per-city budget.

## Issues Encountered

- `timeout` is not available on this macOS shell; `gh run watch --exit-status` was run directly. No effect on the plan.
- `city_rating.run_id` is text, so the first verification query failed on a bigint bind. Fixed in the scratch script (bound the run id as a string); no repository change.

## User Setup Required

None beyond the checks above. Owner to run the anon-key request against `pipeline_run` (needs the project URL and publishable key) and to re-read the Billing page after a full day of live runs to confirm Actions usage stopped growing.

## Next Phase Readiness

- Ready for 05-07 and 05-08. cron-job.org setup and the 24-hour window check can proceed; the workflow is on main.
- Concern: the anon check is still open (above). The first run's rating quality (two fallbacks) is worth a look in the 05-08 window check.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: public-repo-exposure | repository | Repository visibility changed to public; models, data and planning files are now world-readable and history is public. Credential scan of all 904 commits found nothing |

## Self-Check: PASSED

- `docs/data-science/decisions/dlr_live_runbook.md`: FOUND
- Commits `9d4ba23`, `702a833`, `49f0090`: all ancestors of HEAD
- `702a833` is an ancestor of origin/main
