---
phase: 05-scheduled-live-runs
verified: 2026-10-26T18:36:00Z
status: passed
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
  - "docs/data-science/schema/city_rating_v1.md"
covered_digest: "v3:sha256:dfe0cd2e24681333cb5dfbad9b2df052a23c2ff69c537fffd5ef76e4ef6de51f"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 4/4
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 5: Scheduled Live Runs Verification Report

**Phase Goal:** Ratings accrue in Supabase on a fixed cadence with no human involved.
**Verified:** 2026-10-26T18:36:00Z
**Status:** passed
**Re-verification:** Yes. The previous report (human_needed, 4/4) went stale when the code-review fixes landed. This run re-reads the changed code, re-runs the checks, and takes the two former human items from 05-UAT.md.

All four ROADMAP success criteria still hold after the review fixes. The fixes did not break any must-have. The dispositions in 05-REVIEW-DISPOSITION.md are accurate. One point is a warning rather than a gap: the review-fix commits are on local `main` only and have not been pushed to `origin/main`, so GitHub is still running the pre-fix code (see Warnings).

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A new workflow file, separate from `shadow_collect.yml`, has a `workflow_dispatch` trigger only, and cron-job.org calls it at the decided cadence (OD-1, hourly) | VERIFIED | `.github/workflows/dlr_live.yml` re-read: `on: workflow_dispatch` only, `concurrency: dlr-live` with `cancel-in-progress: false`, `timeout-minutes: 30`, inputs only through the `DLR_LIVE_FAULT_CITY` env mapping, `environment: production`. The file is unchanged by the review fixes (empty diff since f083519). `git diff --stat fde51cd..HEAD` on `shadow_collect.yml`, `backend/forecast_shadow_*.py` and `data/shadow` is empty. `gh run list --workflow dlr_live.yml` returns 46 runs, all `workflow_dispatch` (45 success, 1 failure, the deliberate drill), the newest created 2026-10-26T18:05:05Z (hh:05 UTC). The cron-job.org job settings are human-verified in 05-UAT.md test 2 (pass). |
| 2 | Over 24 h, every scheduled slot has a successful run or a visible failed run, and each successful run wrote one row per city | VERIFIED | Re-ran the post-fix checker: `dlr_live_window_check.py --start 2026-10-25T00:00:00Z --hours 24` gives 24 of 24 slots `ok`, "window: PASSED". Slot 2026-10-25T00:00Z notes "fault-drill run 40146481713 not counted" and is still `ok` through its own scheduled run, so the WR-02 drill exclusion changed nothing for this window. A second window, `--start 2026-10-25T18:00:00Z --hours 25` (to 2026-10-26T18:00Z), is also 25 of 25 `ok`, PASSED. Read-only SQL as role dlr_writer (transaction rolled back): each of the four cities has latest `valid_time` 2026-10-26 18:00Z and 24 rows in the last 24 h; 0 duplicate (city, valid_time); 0 null `run_id`; `pipeline_run` has 46 rows, 0 unfinished. Accrual has continued with no human involvement since the previous report. |
| 3 | Forcing one city's provider to fail still lets the other three write, and the failure is recorded | VERIFIED | Drill run 40146481713 (`fault_city=MIDLAND`) is the single red run in history; its `pipeline_run` row shows the other three cities ok and MIDLAND in `cities_failed` (recorded in the prior report from SQL, and the checker still recognises it as a drill via `fault_injected`). The next scheduled run was green with four cities. Code path re-read after the fixes: `run_live` still runs each city in its own subprocess with a timeout, blanks provider credentials for the fault city only, saves `pipeline_run` after each city, and now sets the exit code with `live_run_log.is_healthy` (IN-03). Behavior-dependent, so exercised by tests: `test_a_hung_city_is_killed_at_the_timeout_and_the_rest_still_run` and `test_fault_city_blanks_provider_credentials_for_that_child_only` pass (6 passed with the exit-code tests in `dlr_live_run_test.py`). |
| 4 | The runbook covers the cron-job.org setup, pausing, changing cadence, and Actions-minute budget | VERIFIED | `docs/data-science/decisions/dlr_live_runbook.md` (447 lines): section 2 Trigger, 6 Pause and resume, 7 Change cadence, 11 Failure modes and alerting, 12 GitHub Actions minutes (SCHED-02, measured live median 4, max 8 or 9 billed min per run, about 2,880 per 30 days), 13 Checking a window. The review-fix edits (IN-01 "none confirmed", IN-04 future `--end` refused, IN-07 `startup_failure`, IN-11 drill exclusion paragraph) match the code. `dlr_live_runbook_test.py` (pins constants to code, scans for secret values) passes. 05-UAT.md test 1 (pass) confirms GitHub Billing shows Actions usage flat since the repo went public, which backs the budget claim in section 12. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Plan-level must-haves (spot re-check after the fixes)

| Plan truth | Status | Evidence |
|-----------|--------|----------|
| 05-01: dispatch-only workflow, non-cancelling concurrency, 30 min timeout | VERIFIED | Workflow read; `test_workflow_is_dispatch_only_and_separate_from_shadow_collection` and `test_timeout_fits_the_cities_and_the_cadence` pass (9 passed with the runbook test). |
| 05-01/05-03: exit policy; one `pipeline_run` row written before, during and after | VERIFIED | `run_live` (`dlr_live_run.py` lines ~380-430) calls `save_run_row()` per city and at the end; DB shows 0 unfinished rows. Exit code uses the shared `live_run_log.is_healthy`; no stale `_healthy` reference remains in `backend/*.py`. |
| 05-04: eight models tracked with a SHA-256 manifest, pre-flight before the run step | VERIFIED | `git ls-files data/models` lists the eight joblib files plus the manifest. The manifest now starts with a dated `#` header (IN-09); `PYTHONPATH=backend python backend/dlr_live_check_models.py` run today prints "OK: all 8 live model artifacts present and match data/models/LIVE_ARTIFACT_HASHES.sha256" (exit 0), so the parser tolerates the header. The workflow runs the pre-flight before "Run live pipeline". |
| 05-06: secrets in place; `SUPABASE_DB_URL` only in environment `production`; anon refusal | VERIFIED | Unchanged since the prior report. Re-ran read-only `has_table_privilege` for `anon` and `authenticated` on `city_rating` and `pipeline_run` (select, insert, update, delete): all false. |
| 05-07/05-08: hourly job live, drill red, next run green, 24 h window passes | VERIFIED | Truths 1 to 3. |

### Review fixes did not break the must-haves

| Check | Result |
|-------|--------|
| WR-01 `_cell` keeps the END of a long error behind `...`, escapes backslash then pipe | Present in `dlr_live_run.py`; tests pass |
| WR-02 `_is_drill` routes fault-drill runs to a separate list in `evaluate_window`; their rating rows and minutes still count | Present; the real 24 h window still passes (24 ok) and notes the drill |
| WR-03 `_emit` passes both child streams through `redact(..., limit=None)` then `_defang` | Present. Run today: `NREL_API_KEY=zzz9` becomes `NREL_API_KEY=***`, `cache_key=ok` is left alone (IN-10 plus its 00299e6 follow-up), `?token=abc&api_key=def` becomes `?token=***&api_key=***`, an exact secret value and a postgres URL are masked, `::add-mask::x` becomes `[child] ::add-mask::x` |
| IN-04 future `--end` and `--timeout-s` below 1 rejected | The workflow passes neither flag, and argparse leaves the integer default 300 unconverted, so the scheduled path is unaffected |
| IN-02 provider errors and sources of a failed city kept in the run record | Present in `classify`; does not change the outcome logic |
| IN-03 one health rule | `live_run_log.is_healthy` is used by both `build_run_row` (`cities_ok`) and the runner exit code; `PROVIDER` and `FORECAST_METHOD` are imported from `live_run_log`. `supabase_store` keeps its own `_HEALTHY_FORECAST_STATUSES` copy, as the disposition says |
| Targeted suites | `dlr_live_run_test`, `dlr_live_workflow_test`, `live_run_log_test`, `dlr_live_check_models_test`, `dlr_live_window_check_test`, `dlr_live_runbook_test`: 70 passed in 7.6 s |
| Full suite (orchestrator run, not repeated here) | 1746 passed, 48 skipped, 0 failed |

### Review disposition accuracy (05-REVIEW-DISPOSITION.md)

| Finding | Recorded | Verified in code |
|---------|----------|------------------|
| WR-01, WR-02, WR-03 | fixed | Yes (above) |
| IN-01, 02, 04, 05, 06, 07, 09, 10, 11 | fixed | Yes. IN-11 is fixed in part by design: the runbook documents the one remaining case (a drill killed before its city finished still counts as red), and 05-REVIEW-FIX.md records the code part as not done. |
| IN-03 | fixed (872d282) | Yes. 05-REVIEW-FIX.md still lists IN-03 as skipped because it predates 872d282; the disposition file is the accurate one. |
| IN-08 | skipped, won't fix | Yes. `_minutes_summary` carries a comment that `skipped` runs are counted on purpose (decided 2026-10-26); no code change. |

Disposition counts: 14 findings, 0 open. Accurate.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.github/workflows/dlr_live.yml` | dispatch-only live workflow | VERIFIED | Exists, substantive, wired (46 runs on GitHub). |
| `backend/dlr_live_run.py` | per-city child runner, exit policy | VERIFIED | Wired from the workflow; writes `pipeline_run`. |
| `backend/live_run_log.py` | `pipeline_run` builder and upsert, shared health rule | VERIFIED | Called by the runner; 46 rows in Postgres. |
| `backend/dlr_live_check_models.py` | model pre-flight | VERIFIED | Runs OK against the committed manifest today. |
| `backend/dlr_live_window_check.py` | window verdict | VERIFIED | Ran twice today, exit 0. |
| `docs/data-science/decisions/dlr_live_runbook.md` | runbook | VERIFIED | Covers SC 4. |
| `data/models/LIVE_ARTIFACT_HASHES.sha256` | manifest | VERIFIED | Eight tracked artifacts match. |
| `docs/data-science/schema/city_rating_v1.md` | schema doc for the run log | VERIFIED | Wording updated by IN-01. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `dlr_live.yml` | `dlr_live_run.py` | run step, four secrets mapped | WIRED | Read in the workflow file. |
| `dlr_live_run.py` | `dlr_orchestrator.py` | `subprocess.run(child_argv(...))` | WIRED | Unchanged. |
| `dlr_live_run.py` | `live_run_log.py` | `build_run_row`, `upsert_run_row`, now also `is_healthy`, `PROVIDER`, `FORECAST_METHOD` | WIRED | Grep and tests. |
| `dlr_live.yml` | `dlr_live_check_models.py` | pre-flight step before run | WIRED | Step order confirmed. |
| cron-job.org | `dlr_live.yml` | `dispatches` POST | WIRED | Hourly runs at hh:05 UTC; settings confirmed in 05-UAT.md. |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Produces Real Data | Status |
|----------|------|--------|--------------------|--------|
| `city_rating` rows | rating, status, forecast | composed providers, ML forecast, Postgres history | Yes: 24 rows per city in the last 24 h, newest valid_time 2026-10-26 18:00Z for all four | FLOWING |
| `pipeline_run` rows | cities_ok / cities_failed | runner records per child | Yes: 46 rows, 0 unfinished | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 24 h window verdict | `dlr_live_window_check.py --start 2026-10-25T00:00:00Z --hours 24` | 24 ok, PASSED | PASS |
| Latest window | `--start 2026-10-25T18:00:00Z --hours 25` | 25 ok, PASSED | PASS |
| Model pre-flight | `dlr_live_check_models.py` | OK, 8 artifacts, exit 0 | PASS |
| Redaction and defang | python snippet against `redact` and `_defang` | masks real secrets, leaves `cache_key=`, defangs `::` lines | PASS |
| Phase test files | pytest on six phase test modules | 70 passed | PASS |
| Run history | `gh run list --workflow dlr_live.yml --limit 100` | 46 runs: 45 success, 1 failure (drill) | PASS |
| Anon and authenticated privileges | `has_table_privilege` (read-only) | all false | PASS |

### Probe Execution

Step 7c: SKIPPED. No `probe-*.sh` is declared by this phase's plans.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| PIPE-02 | 05-01, 05-02, 05-04, 05-06, 05-07, 05-08 | `dlr_live.yml` runs the pipeline for all four cities on `workflow_dispatch`, triggered by cron-job.org hourly, upserts into Supabase | SATISFIED | Truths 1 and 2. |
| SCHED-01 | 05-01, 05-02, 05-03, 05-05, 05-07, 05-08 | A failed city or provider is recorded and does not stop the other cities or the next run; a failed run is visible in Actions | SATISFIED | Truth 3. |
| SCHED-02 | 05-05, 05-06, 05-07, 05-08 | Runbook documents the cron-job.org job, pause, cadence change, and estimates Actions minutes alongside shadow usage | SATISFIED | Truth 4, plus 05-UAT.md tests 1 and 2. |

All three IDs in the PLAN frontmatter (PIPE-02, SCHED-01, SCHED-02) appear in REQUIREMENTS.md mapped to Phase 5 (all `[x]`, traceability "Complete"). No requirement mapped to Phase 5 is missing from every plan, so there are no orphans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| phase files | - | `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, `PLACEHOLDER` grep over the runner, run-log, pre-flight and window-check modules, workflow, and runbook | none | No debt markers. |
| `backend/supabase_store.py` | 94 | third copy of the healthy forecast statuses, kept on purpose (Phase 4 module) | Info | The two Phase 5 copies are now one; noted in the IN-03 disposition. |

### Human Verification Required

None outstanding. The two items from the previous report are human-verified in 05-UAT.md (status complete, 2 of 2 passed): the GitHub Billing page shows Actions usage flat since the repo went public, and the cron-job.org job matches runbook section 2.

### Warnings (not gaps)

1. **Review fixes are not deployed.** `origin/main` is at f820dc6; local `main` (b99abbb) is 24 commits ahead, including every WR and IN fix. The 46 production runs, and so all the live evidence above, ran the pre-fix code (head SHAs 702a833, d71c501, f820dc6). The fixes are hardening (redaction of child logs on a public repo, a stricter checker, summary cells), not goal-critical, and the targeted and full suites pass on the post-fix tree, but the post-fix runner has not yet run in Actions. Pushing needs the owner's approval, as in plan 05-06. After the push, check that the first hourly run is green with four cities and that its log shows `***` masking instead of raw child output.
2. **Stale doc.** 05-REVIEW-FIX.md still lists IN-03 as skipped (2 skipped, status partial) and 05-REVIEW.md still shows `issues_found`; 05-REVIEW-DISPOSITION.md (0 open) is the accurate record. No action needed beyond optional tidying.

### Deferred and carried items (not gaps)

- AUSTIN static-rating fallback (about 9 of 24 slots with `status=fallback`): designed safe behavior, owner-accepted, waits on Phase 7 (COND-01).
- Rows carry `config_version = v1-provisional-2026-10-13` (OD-5) until Phase 7's go.
- The dispatch token expires mid-December 2026 (owner-accepted). If it lapses, runs stop and nothing in the repo reports it; Phase 6's freshness alarm is the planned backstop.
- IN-11 code part (record the drilled city in the first `pipeline_run` save) not done by decision; documented in the runbook.

### Gaps Summary

No gaps. Ratings are accruing in Supabase hourly with no human involved: 46 dispatched runs, two passing 24 h and 25 h windows with all four cities in every slot, a recorded and isolated fault drill, and a runbook covering the operator tasks. The review fixes are present, tested, and do not disturb any must-have. Phase 5 can proceed to Phase 6; push the review-fix commits with the owner's approval when convenient.

---

_Verified: 2026-10-26T18:36:00Z_
_Verifier: Claude (gsd-verifier)_
