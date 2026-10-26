---
phase: 05-scheduled-live-runs
verified: 2026-10-26T05:40:00Z
status: human_needed
score: 4/4 must-haves verified
covered_files:
  - ".github/workflows/dlr_live.yml"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-01-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-01-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-02-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-02-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-03-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-03-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-04-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-04-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-05-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-05-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-06-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-06-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-07-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-07-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-08-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-08-SUMMARY.md"
  - "backend/city_pipeline.py"
  - "backend/dlr_live_check_models.py"
  - "backend/dlr_live_run.py"
  - "backend/dlr_live_window_check.py"
  - "backend/dlr_orchestrator.py"
  - "backend/live_run_log.py"
  - "backend/observation_composer.py"
  - "data/models/LIVE_ARTIFACT_HASHES.sha256"
  - "docs/data-science/decisions/dlr_live_runbook.md"
covered_digest: "v3:sha256:b7b96a13250f71beec651098b2eda27d0838d21369999f32a9cfe36240bd9c2f"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Open GitHub Settings, Billing and plans for account aa-phan and read Actions usage for the current cycle."
    expected: "Usage has stopped growing since the repository became public on 2026-10-24 (hosted-runner minutes free for public repositories)."
    why_human: "gh cannot read billing without the user scope; 05-08 recorded this check as owner-only. Measured usage (about 2,880 live plus about 600 shadow min per 30 days) exceeds the 2,000 included minutes on a private basis, so the budget claim is moot only while the repository stays public."
  - test: "Open the cron-job.org job for dlr_live.yml and confirm failure notifications are on, the schedule is `5 * * * *` in UTC, and the token is the repository-scoped Actions read/write fine-grained token."
    expected: "Settings match runbook section 2. (Run history already shows hh:05 UTC dispatches, which proves schedule and token work.)"
    why_human: "The cron-job.org account and the token scope are not visible to the codebase or gh. 05-07 recorded token scope and expiry (mid-December 2026) as owner-reported only."
---

# Phase 5: Scheduled Live Runs Verification Report

**Phase Goal:** Ratings accrue in Supabase on a fixed cadence with no human involved.
**Verified:** 2026-10-26T05:40:00Z
**Status:** human_needed
**Re-verification:** No, initial verification

All four ROADMAP success criteria are met by evidence taken directly from GitHub and Postgres, not from the SUMMARY files. The status is `human_needed` only because two owner-side checks (Billing page, cron-job.org dashboard) cannot be observed from here. Neither is a ROADMAP success criterion and neither blocks the goal. Phase 5 can proceed to Phase 6 on the owner's acceptance of these two items.

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A new workflow file, separate from `shadow_collect.yml`, has a `workflow_dispatch` trigger only, and cron-job.org calls it at the decided cadence (OD-1, hourly) | VERIFIED | `.github/workflows/dlr_live.yml` has `on: workflow_dispatch` only (grep for `schedule`, `cron`, `push:`, `pull_request` in non-comment lines returns nothing). `git diff --stat fde51cd..HEAD` on `shadow_collect.yml`, `backend/forecast_shadow_*.py` and `data/shadow` is empty. `gh run list --workflow dlr_live.yml` returns 33 runs, all `event=workflow_dispatch`, created at hh:05 UTC from 2026-10-25T00:05:05Z through 2026-10-26T05:05:05Z (the owner's cron-job.org test at 23:51Z is the one off-boundary run). The pushed workflow is on `origin/main` (d71c501). The cron-job.org job itself is owner-reported (see human item 2); the hourly dispatch history is the independent proof. |
| 2 | Over 24 h, every scheduled slot has a successful run or a visible failed run, and each successful run wrote one row per city | VERIFIED | Re-ran `PYTHONPATH=backend .venv/bin/python backend/dlr_live_window_check.py --start 2026-10-25T00:00:00Z --hours 24` today: 24 of 24 slots `ok`, "window: PASSED". The checker's own WR-02 weakness does not apply: every one of the 24 slots has its own scheduled green run (created hh:05), so no slot is passed on a drill run alone. Independent SQL (read-only, role dlr_writer): `city_rating` in the window has 24 rows and 24 distinct `valid_time` per city for all four cities, no slot with a count other than 4, no duplicate (city, valid_time), no null `run_id`. `pipeline_run` has 31 runs with `window_end` since 2026-10-25T00:00Z, 0 unfinished (`finished_at` null), and 30 of 31 list 4 cities in `cities_ok` with none failed. The one exception is the deliberate drill (see truth 3). Runs have continued green through 05:05Z on 2026-10-26 (latest `valid_time` for every city is 2026-10-26 05:00Z). |
| 3 | Forcing one city's provider to fail still lets the other three write, and the failure is recorded | VERIFIED | Drill run 40146481713 (`fault_city=MIDLAND`): GitHub conclusion `failure` (visible red run). `pipeline_run` row for that run has `cities_ok = [AUSTIN, CORPUS_CHRISTI, EL_PASO]`, `cities_failed` key `MIDLAND`, `finished_at` set. Next scheduled run 40149224957 (01:05Z) was green with four cities. Code: `run_live` in `backend/dlr_live_run.py` runs each city in its own subprocess with a timeout, blanks `SYNOPTIC_TOKEN`/`NREL_API_KEY`/`NREL_API_EMAIL` for the fault city only, writes `pipeline_run` after every city, and exits 1 unless every record is healthy. Named tests pass: `test_a_hung_city_is_killed_at_the_timeout_and_the_rest_still_run`, `test_fault_city_blanks_provider_credentials_for_that_child_only` (3 passed). |
| 4 | The runbook covers the cron-job.org setup, pausing, changing cadence, and Actions-minute budget | VERIFIED | `docs/data-science/decisions/dlr_live_runbook.md` (433 lines): section 2 Trigger (dispatches URL, `5 * * * *` UTC, token scope), section 6 Pause and resume, section 7 Change cadence, section 11 Failure modes and alerting, section 12 GitHub Actions minutes with measured figures (live median 4 / max 8 billed min per run, about 2,880 per 30 days; shadow about 600), and section 13 Checking a window. `dlr_live_runbook_test.py` pins its constants to the code and scans the phase files for secret values (passes in the full suite). The runbook states that the total does not fit 2,000 minutes on a private basis and is moot while public. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Plan-level must-haves cross-checked

| Plan truth | Status | Evidence |
|-----------|--------|----------|
| 05-01: dispatch-only workflow, concurrency `dlr-live` not cancelling, `timeout-minutes: 30`, inputs only via env mapping | VERIFIED | Read the workflow: `concurrency: group: dlr-live, cancel-in-progress: false`, `timeout-minutes: 30`, `DLR_LIVE_FAULT_CITY: ${{ inputs.fault_city }}` is the only input use; `dlr_live_workflow_test.py` passes. |
| 05-01: exit policy and per-city timeout | VERIFIED | `run_live` and `_healthy` in `backend/dlr_live_run.py` (code read); tests pass. |
| 05-03: one `pipeline_run` row per run, written before, during, after; failed city carries outcome, written false | VERIFIED | `run_live` calls `save_run_row()` before the first child, after each city and at the end; DB shows 0 unfinished rows and the drill row's `cities_failed`. |
| 05-04: eight models tracked in git with a SHA-256 manifest, pre-flight before the run step | VERIFIED | `git ls-files data/models` lists the eight `forecast_*` and `anomaly_*` joblib files plus `LIVE_ARTIFACT_HASHES.sha256` (corridor-era `anomaly_AUSTIN_CORPUS_CHRISTI.joblib` and `anomaly_MIDLAND_EL_PASO.joblib` are not tracked). The workflow runs `dlr_live_check_models.py` before "Run live pipeline"; every production run since 2026-10-25 has passed that step. |
| 05-06: four REQUIRED_ENV names available; push only on owner approval | VERIFIED | `gh secret list` shows `NREL_API_EMAIL`, `NREL_API_KEY`, `SYNOPTIC_TOKEN` at repo level and `SUPABASE_DB_URL` only in environment `production` (deployment branch policy `custom_branch_policies: true`); the repo-level `SUPABASE_DB_URL` is gone, matching the owner's T-04-38 deletion. Push `702a833..d71c501` was a fast-forward after owner `approve-push`. |
| 05-06: anon refusal of `pipeline_run` (T-05-29, recorded unverified in 05-06) | VERIFIED (equivalent evidence) | No publishable key exists, so a literal anon HTTP request was not made. Re-ran the read-only privilege check: `has_table_privilege` for `anon` and `authenticated` is false for select, insert, update and delete on both `city_rating` and `pipeline_run`; RLS is on for both; the only policies are `dlr_writer_all` for role `dlr_writer`. A PostgREST request as anon is therefore refused at the privilege layer. Phase 6 plans 06-04 and 06-09 will exercise the live REST refusal. |
| 05-07: hourly job live, drill red, next run green | VERIFIED | See truths 1 and 3. |
| 05-08: window passes, measured minutes recorded, owner sign-off | VERIFIED | Checker re-run passes; runbook section 12 holds measured figures; push is on `origin/main`; the post-push run 40272358123 (sha d71c501, environment `production`) is success with four cities. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.github/workflows/dlr_live.yml` | dispatch-only live workflow | VERIFIED | Exists, substantive, wired (runs on GitHub, 33 runs). |
| `backend/dlr_live_run.py` (504 lines) | per-city child runner, exit policy | VERIFIED | Wired from the workflow, produces `pipeline_run` rows. |
| `backend/live_run_log.py` (161 lines) | `pipeline_run` builder and upsert | VERIFIED | Called by `run_live`; rows present in Postgres. |
| `backend/dlr_live_check_models.py` (216 lines) | model pre-flight | VERIFIED | Workflow step; manifest and files present. |
| `backend/dlr_live_window_check.py` (339 lines) | window verdict | VERIFIED | Run by the verifier, exit 0 and PASSED. |
| `docs/data-science/decisions/dlr_live_runbook.md` | runbook | VERIFIED | Covers SC 4. |
| `data/models/LIVE_ARTIFACT_HASHES.sha256` | manifest | VERIFIED | Eight tracked artifacts match (code review also confirmed). |
| `docs/data-science/schema/city_rating_v1.md` | schema doc updated for run log | VERIFIED | Present in the phase diff. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `dlr_live.yml` | `dlr_live_run.py` | run step | WIRED | `PYTHONPATH=backend python backend/dlr_live_run.py` with four secrets mapped. |
| `dlr_live_run.py` | `dlr_orchestrator.py` | `subprocess.run(child_argv(...))` | WIRED | Code read. |
| `dlr_live_run.py` | `live_run_log.py` | `build_run_row` / `upsert_run_row` | WIRED | Rows in `pipeline_run`. |
| `dlr_live.yml` | `dlr_live_check_models.py` | pre-flight step before run | WIRED | Step ordering confirmed in the file. |
| cron-job.org | `dlr_live.yml` | `dispatches` POST | WIRED | Hourly `workflow_dispatch` runs at hh:05 UTC. |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Produces Real Data | Status |
|----------|------|--------|--------------------|--------|
| `city_rating` rows | rating, status, forecast | composed providers, ML forecast, Postgres history via orchestrator | Yes, 96 rows in the window, latest valid_time 2026-10-26 05:00Z for all four cities | FLOWING |
| `pipeline_run` rows | cities_ok / cities_failed | runner records per child | Yes, 33 rows, 0 unfinished | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 24 h window verdict | `dlr_live_window_check.py --start 2026-10-25T00:00:00Z --hours 24` | 24 ok, PASSED | PASS |
| Timeout kill, fault drill, dispatch-only | three named pytest tests | 3 passed | PASS |
| Full backend suite | `.venv/bin/python -m pytest backend/tests -q` | 1730 passed, 48 skipped | PASS |
| Run history | `gh run list --workflow dlr_live.yml --limit 60` | 33 runs: 32 success, 1 failure (the drill) | PASS |
| Anon/authenticated privileges | `has_table_privilege`, `pg_policies` (read-only) | all false, RLS on, only `dlr_writer_all` | PASS |

### Probe Execution

Step 7c: SKIPPED. No `probe-*.sh` is declared by this phase's plans.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| PIPE-02 | 05-01, 05-02, 05-04, 05-06, 05-07, 05-08 | `dlr_live.yml` runs the pipeline for all four cities on `workflow_dispatch`, triggered by cron-job.org hourly, upserts into Supabase | SATISFIED | Truths 1 and 2; rows in `city_rating`. |
| SCHED-01 | 05-01, 05-02, 05-03, 05-05, 05-07, 05-08 | A failed city or provider is recorded and does not stop the other cities or the next run; a failed run is visible in Actions | SATISFIED | Truth 3; drill row, red run 40146481713, next run green. |
| SCHED-02 | 05-05, 05-06, 05-07, 05-08 | Runbook documents the cron-job.org job, pause, cadence change, and estimates Actions minutes alongside shadow usage | SATISFIED (documentation) | Truth 4. Live billing confirmation is human item 1. |

All three IDs in the plan frontmatter (PIPE-02, SCHED-01, SCHED-02) appear in REQUIREMENTS.md under Phase 5 and are accounted for. No requirement mapped to Phase 5 in REQUIREMENTS.md is missing from every plan, so there are no orphans. REQUIREMENTS.md already marks all three `[x]` / Complete.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (phase files) | - | `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, `PLACEHOLDER` scan of the runner, run-log, pre-flight, window-check modules, workflow, runbook and schema doc | none found | No debt markers. |
| `backend/dlr_live_run.py` | 417-420 | WR-01 step-summary cell keeps the head of a traceback | Warning | Operator-facing only; `pipeline_run.error` keeps the tail. Open in 05-REVIEW-DISPOSITION. |
| `backend/dlr_live_window_check.py` | 189-191 | WR-02 a red drill run can stand in for an unscheduled slot | Warning | Did not affect this window: every slot has its own green scheduled run (checked independently via `gh run list` and SQL). Hardens the checker for later windows. |
| `backend/dlr_live_run.py` | 265-277 | WR-03 child streams re-emitted outside `redact()` | Warning | Repository is public, so Actions logs are public. No leak observed; worth fixing before relying on public logs. |
| (nine items) | - | IN-01 to IN-09 | Info | Small robustness and duplication items, all `open`. |

The review has 0 critical, 3 warning and 9 info findings, all dispositioned `open` (not triaged). None is a gap against the roadmap success criteria. I am not treating them as blockers.

### Human Verification Required

#### 1. Billing page confirmation

**Test:** On GitHub, Settings, Billing and plans (account aa-phan), read Actions usage for the cycle.
**Expected:** Usage is flat since 2026-10-24, when the repository became public.
**Why human:** `gh` has no `user` scope; 05-08 left this to the owner. Matters because the measured total (about 3,500 min per 30 days) exceeds 2,000 included minutes if the repository ever goes private.

#### 2. cron-job.org job settings

**Test:** Check the cron-job.org dashboard for the dlr_live.yml job: schedule, failure notifications, token scope and expiry.
**Expected:** Matches runbook section 2 (`5 * * * *` UTC, notifications on, repository-scoped Actions read/write token, expiring mid-December 2026 per the owner).
**Why human:** Not observable from the codebase or `gh`. The dispatch history already proves the schedule and token work today.

### Deferred and carried items (not gaps)

- AUSTIN static-rating fallback: 9 of 24 slots in the window have `status=fallback` (MIDLAND 1 of 24). The runs are green because the safety fallback is the designed behavior, not a failure. The owner accepted this and it waits on Phase 7's Austin conductor data (COND-01).
- Rows carry `config_version = v1-provisional-2026-10-13` (2,140 rows), per OD-5, until Phase 7's go.
- Dispatch token expires mid-December 2026 (owner-accepted, no reminder set). If it lapses, runs stop and nothing in the repo reports it; Phase 6's freshness alarm is the planned backstop.

### Gaps Summary

No gaps. The goal, ratings accruing in Supabase hourly with no human involved, is demonstrably true: 33 hourly dispatches, a full 24 h window with all four cities in every slot, a recorded and isolated fault drill, and a runbook covering the operator tasks. The post-plan history-cleaning degradation fix (1f94535, 105adac) is present: `live_run_log.build_run_row` marks a city with a `cleaning_error` as `degraded`, and `_healthy` in the runner treats it as unhealthy so the run turns red.

---

_Verified: 2026-10-26T05:40:00Z_
_Verifier: Claude (gsd-verifier)_
