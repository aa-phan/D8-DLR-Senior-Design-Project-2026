---
phase: 05-scheduled-live-runs
plan: 08
subsystem: infra
tags: [github-actions, cron-job.org, actions-minutes, window-check, supabase, owner-signoff]

requires:
  - phase: 05-scheduled-live-runs
    provides: "Hourly cron-job.org trigger and window start 2026-10-25T00:05:05Z (05-07), dlr_live_window_check.py (05-05), runbook section 12 quota (05-06)"
provides:
  - "24 h window report: 24 of 24 hourly slots ok, checker exit 0, every successful run wrote one city_rating row per city (96 rows)"
  - "Measured Actions minutes in runbook section 12: live median 4 / max 8 billed min per run, 103 min/day, about 2,880 per 30 days; shadow 19 min/day, about 600 per 30 days"
  - "Owner sign-off (approve-push) and the fast-forward push of main to origin (702a833..d71c501)"
  - "First scheduled run on the pushed workflow: 40272358123, green, environment production, head SHA d71c501"
affects: [06-freshness-check, 07-shadow-refit-and-early-model-selection]

actuals:
  tokens: 6000
  tasks: 2
  commits: 1
  plan_head_before: a65aa089c02154b9126ad4654d341cd1276168b9
  plan_head_after: fb79b8c2aa4a36f266bfb23012f9e83805243d01

tech-stack:
  added: []
  patterns:
    - "Window evidence taken from the checker's own output; verdicts never edited"
    - "Push gated on the owner's sign-off and followed by the next scheduled run as the verification run (no extra dispatch)"

key-files:
  created: []
  modified:
    - docs/data-science/decisions/dlr_live_runbook.md

key-decisions:
  - "Owner signed off the 24 h window and the budget with approve-push"
  - "Measured total (about 3,500 min per 30 days) exceeds the 2,000 included minutes on a private basis; moot while the repository is public, so no lever was needed at sign-off"
  - "The post-push verification run is the next scheduled hh:05 run, not an extra dispatch"

requirements-completed: [SCHED-01, SCHED-02, PIPE-02]

coverage:
  - id: D1
    description: "ROADMAP SC 2: dlr_live_window_check.py --start 2026-10-25T00:00:00Z --hours 24 exits 0; 24 of 24 slots ok; 96 city_rating rows; 25 pipeline_run rows, none unfinished"
    requirement: SCHED-01
    verification:
      - kind: integration
        ref: "PYTHONPATH=backend .venv/bin/python backend/dlr_live_window_check.py --start 2026-10-25T00:00:00Z --hours 24 -> exit 0, passed true"
        status: pass
    human_judgment: false
  - id: D2
    description: "Runbook section 12 holds measured live and shadow Actions minutes for the window and states plainly that the total does not fit the 2,000 included minutes on a private basis"
    requirement: SCHED-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_runbook_test.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "The pushed workflow runs green in environment production on the pushed SHA: run 40272358123, four cities in cities_ok, finished_at set, deployment created 05:05:06Z for sha d71c501"
    requirement: PIPE-02
    verification:
      - kind: integration
        ref: "gh run view 40272358123; gh api repos/.../deployments?environment=production; read-only pipeline_run and city_rating check for run 40272358123"
        status: pass
    human_judgment: false
  - id: D4
    description: "Billed minutes are an approximation and the Billing page confirmation that usage stopped growing after going public is not recorded"
    requirement: SCHED-02
    verification: []
    human_judgment: true
    rationale: "gh could not read billing without the user scope; the owner must read Settings, Billing and plans to confirm Actions usage is flat"

duration: about 1h 15m (Task 1 about 25 min, continuation about 50 min mostly waiting on the 05:05Z slot)
completed: 2026-10-26
status: complete
---

# Phase 5 Plan 08: 24 h window evidence, measured Actions minutes and owner sign-off Summary

**The 24 h window (2026-10-25 00:00Z to 26 00:00Z) passed with 24 of 24 slots ok and 96 city_rating rows, measured live usage is about 2,880 Actions minutes per 30 days (median 4, max 8 per run), the owner signed off with approve-push, main was pushed fast-forward (702a833..d71c501), and the next scheduled run (40272358123, 05:05Z) ran green in environment production on the pushed SHA with four cities.**

## Performance

- **Duration:** about 1h 15m
- **Started:** 2026-10-26T04:00Z (Task 1); continuation 2026-10-26T04:17Z
- **Completed:** 2026-10-26T05:20Z
- **Tasks:** 2 (Task 1 auto, Task 2 owner decision checkpoint, resolved approve-push)
- **Files modified:** 1 (`docs/data-science/decisions/dlr_live_runbook.md`)

## Task 1: window check (SC 2)

Command: `PYTHONPATH=backend .venv/bin/python backend/dlr_live_window_check.py --start 2026-10-25T00:00:00Z --hours 24` exit 0, `passed: true`. Checker output copied verbatim; no verdict edited or slot re-run (T-05-33).

| Slot (UTC, 2026-10-25) | Verdict | Run id(s) | Conclusion(s) |
|---|---|---|---|
| 00:00 | ok | 40145300072, 40146481713 | success, failure (drill) |
| 01:00 | ok | 40149224957 | success |
| 02:00 | ok | 40153094724 | success |
| 03:00 | ok | 40156888768 | success |
| 04:00 | ok | 40160579131 | success |
| 05:00 | ok | 40164234698 | success |
| 06:00 | ok | 40167843477 | success |
| 07:00 | ok | 40171448029 | success |
| 08:00 | ok | 40175233252 | success |
| 09:00 | ok | 40179188388 | success |
| 10:00 | ok | 40183301436 | success |
| 11:00 | ok | 40187388549 | success |
| 12:00 | ok | 40191572824 | success |
| 13:00 | ok | 40195996660 | success |
| 14:00 | ok | 40200573392 | success |
| 15:00 | ok | 40205253236 | success |
| 16:00 | ok | 40209980259 | success |
| 17:00 | ok | 40214743173 | success |
| 18:00 | ok | 40219548556 | success |
| 19:00 | ok | 40224320021 | success |
| 20:00 | ok | 40229082246 | success |
| 21:00 | ok | 40233793751 | success |
| 22:00 | ok | 40238508680 | success |
| 23:00 | ok | 40243136280 | success |

**Red runs in the window:** exactly one, 40146481713 (slot 00:00), the deliberate MIDLAND fault drill from 05-07 (cause: drill, `DLR_LIVE_FAULT_CITY=MIDLAND`; recorded in 05-07-SUMMARY). The slot's scheduled run 40145300072 succeeded. No provider outage, timeout or other red run occurred.

**Database (read-only):** `city_rating` 96 rows (24 per city); `pipeline_run` 25 rows, none with `finished_at` null.

**Fallback ratings (not a red run, recorded for the evidence):** AUSTIN 9 of 24 slots are `fallback` (accepted open issue, pending Austin conductor data, STATE.md); MIDLAND 1 fallback at 22:00 (MAF ASOS returned no data that hour).

**Minutes line:** `count 25, median 4, max 8, projected_30d 2880`.

| Source | Runs | Billed min per run | Day total | 30-day projection |
|---|---|---|---|---|
| dlr_live (measured) | 25 (24 scheduled + 1 drill) | median 4, max 8 | 103 | about 2,880 (median basis); about 3,060 at the mean of the 24 scheduled |
| shadow_collect (measured, same 24 h) | 4 | median 5, max 6 | 19 | about 600 |
| Total | | | | about 3,500 (about 3,600 at the means) |

Against the quota recorded at 05-06 (2,000 included minutes): does not fit on a private-repository basis (about 1,500 to 1,600 over, roughly $9 to $10 per month at $0.006). Moot while the repository is public (hosted-runner minutes free since 2026-10-24); it binds again if the repository is made private. The runbook states this with the date. The Billing page confirmation that usage stopped growing is **not recorded**: `gh` cannot read billing without the `user` scope, so it remains the owner's check.

Commit: `fb79b8c` (runbook only, `git show --stat` lists only `docs/data-science/decisions/dlr_live_runbook.md`).

## Task 2: owner sign-off (blocking-human)

- **Decision: approve-push.** The owner signed off the window and the budget.
- Budget lever: none recorded; the measured total does not fit the private-repository quota, and the owner accepted it as moot while public.

### Push range

- `git fetch origin`; `git merge-base --is-ancestor origin/main main` true (fast-forward). Never forced.
- Pushed `702a833..d71c501` to `origin/main`, 18 commits, at 2026-10-26T04:17:33Z. The owner reviewed 17 commits (fb79b8c 549c371 0e94ee3 9179a6b ba9d554 49f0090 1f94535 105adac 44b1033 8dc5448 d000656 482db68 cc9ae7b 8d29dd6 888f0ea 1aff179 a65aa08); the 18th, `d71c501` "docs(phase-06): refresh research, revise D-03 provisional rule, add validation strategy" (3 files, all under `.planning/phases/06-exposure-e2e-verification/`), was committed by another session after the review. It is planning-only, so the push proceeded.
- Code and workflow files in the range all came from the reviewed 17: `.github/workflows/dlr_live.yml`, `.github/workflows/supabase_smoke.yml`, `backend/dlr_live_run.py`, `backend/dlr_orchestrator.py`, `backend/live_run_log.py` and their tests.
- Two more docs-only commits by another session landed locally after the push (`4966948`, `97c005b`); they are **not pushed**.

### Verification run (no extra dispatch)

| Item | Result |
|---|---|
| Run id | 40272358123 (next scheduled run, created 2026-10-26T05:05:05Z, workflow_dispatch from cron-job.org) |
| Head SHA | d71c501109549ba6e5b283b0131f7a15b5b46d2e (= pushed HEAD, so new workflow and cleaning_error code) |
| Conclusion | success (05:05:05Z to 05:09:28Z); all steps success including pre-flight and "Run live pipeline" |
| Environment | production: deployment for ref main, sha d71c501, created 2026-10-26T05:05:06Z |
| `pipeline_run` | 1 row, attempt 1, window_end 05:05, started 05:05:52, finished_at set 05:09:23, cities_ok = [AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO], cities_failed = {} |
| `city_rating` | 4 rows with this run_id, slot 05:00, all status ok, no fallbacks (AUSTIN 1361.4, CORPUS_CHRISTI 1665.1, EL_PASO 1470.3, MIDLAND 1880.7 A) |

Because the run used the `production` environment secret and succeeded, the repository-level `SUPABASE_DB_URL` secret was not what it read. **It is now safe for the owner to delete the repository-level `SUPABASE_DB_URL` secret.** It was not deleted by the executor.

## Task Commits

1. **Task 1: Run the 24 h window check and record measured minutes** - `fb79b8c` (docs)
2. **Task 2: owner decision (approve-push)** - no commit; the push itself moved `702a833..d71c501`

**Plan metadata:** the commit following this SUMMARY (docs: complete plan), kept local.

`commits: 1` is measured over `plan_head_before..plan_head_after` (a65aa08..fb79b8c). The raw range `a65aa08..HEAD` also counts three docs commits from other sessions (d71c501, 4966948, 97c005b), which are not this plan's work.

## Files Created/Modified

- `docs/data-science/decisions/dlr_live_runbook.md` - section 12 now holds measured live and shadow minutes, the quota comparison with date, and the unconfirmed Billing-page note

## Decisions Made

- Owner sign-off: approve-push; no budget lever, since the over-quota projection is private-basis only.
- Verification run is the next scheduled run, which avoids a billed extra dispatch and exercises the real cron path.

## Deviations from Plan

None - plan executed exactly as written. (The plan expected the push range to hold only runbook commits; it held the reviewed code and workflow commits as well, which the owner approved at sign-off. See Discrepancies.)

## Discrepancies

- **17 reviewed commits became 18 pushed.** `d71c501` (Phase 6 research and validation docs) landed after the owner's review; planning-only, pushed and listed above. Two further docs commits (4966948, 97c005b) landed after the push and remain local.
- **Push range was not "only the 05-06 and 05-08 runbook commits"** as the plan's Task 2 context said. It contained the earlier plans' code, tests and workflow changes (including the history-cleaning failure fix 105adac and the production-environment CI change 44b1033) that were still unpushed. The owner reviewed the 17-commit, 21-file list before approving.
- **Billing page unconfirmed.** `gh` cannot read billing without the `user` scope; the check that Actions usage stopped growing stays with the owner.
- **Billed minutes are approximate**: the checker rounds `updatedAt - startedAt` up to whole minutes per run; GitHub bills per job.
- **Window's 00:00 slot is drill-affected** (05-07): `city_rating.run_id` for AUSTIN, CORPUS_CHRISTI and EL_PASO is the drill run; MIDLAND's carries the scheduled run. The checker still counts one row per city.
- **Commit trailer model name**: the plan text named "Claude Opus 5.5"; the commits carry the session's attribution (Claude Sonnet 5.5) as instructed by the run.
- The anon-refusal check (T-05-29) from 05-06 remains open and was out of scope here.

## Issues Encountered

- The 05:05Z wait exceeded the tool timeout several times; polling loops were re-issued. A first `gh run watch` call failed because `timeout` is not installed on macOS, and the run was polled with `gh run view` instead. No effect on results.

## User Setup Required

None. Owner-side: optionally delete the repository-level `SUPABASE_DB_URL` secret (safe now), and confirm on Settings, Billing and plans that Actions usage is flat.

## Next Phase Readiness

Phase 5 has 8 of 8 plans with summaries; ROADMAP SC 1 to 4 are recorded (SC 1 and 3 in 05-06 and 05-07, SC 2 and 4 here). Ready for Phase 6. Open items carried: AUSTIN fallback rate (9 of 24) pending Austin conductor data, T-05-29 anon check, Billing confirmation.

## Known Stubs

None.

## Threat Flags

None. No new network endpoints, auth paths or schema changes in this plan; the only repository change is a documentation edit.

## Self-Check: PASSED

- `docs/data-science/decisions/dlr_live_runbook.md` exists; commit `fb79b8c` is an ancestor of HEAD.
- `origin/main` contains `d71c501` (push succeeded, fast-forward).
- Run 40272358123 exists, conclusion success, head SHA d71c501.
- No secret value appears in this file.
