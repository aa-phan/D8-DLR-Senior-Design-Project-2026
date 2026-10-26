---
phase: "05"
slug: "scheduled-live-runs"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-26"
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Reconstructed after execution (State B) from the 05-01 to 05-08 PLAN and SUMMARY files and
> 05-VERIFICATION.md. All named test files were re-run green on 2026-10-26 against the tree that
> includes the code-review fixes (05-REVIEW-FIX.md, 872d282).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pytest.ini` |
| **Quick run command** | `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/dlr_live_run_test.py backend/tests/dlr_live_workflow_test.py backend/tests/live_run_log_test.py backend/tests/dlr_live_check_models_test.py backend/tests/dlr_live_window_check_test.py backend/tests/dlr_live_runbook_test.py` |
| **Full suite command** | `.venv/bin/python -m pytest -q -p no:cacheprovider` |
| **Estimated runtime** | ~10 seconds (phase files); full suite a few minutes |

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | PIPE-02, SCHED-01 | — | Workflow is `workflow_dispatch` only; inputs reach the script only through the env mapping | unit | `pytest backend/tests/dlr_live_run_test.py backend/tests/dlr_live_workflow_test.py` | ✅ | ✅ green |
| 05-01-02 | 01 | 1 | SCHED-01 | — | Child output is redacted before it reaches logs and the step summary; the fault drill blanks credentials for one child only | unit | `pytest backend/tests/dlr_live_run_test.py backend/tests/dlr_live_workflow_test.py` | ✅ | ✅ green |
| 05-02-01 | 02 | 1 | PIPE-02 | — | N/A | unit | `pytest backend/tests/city_pipeline_test.py backend/tests/dlr_orchestrator_test.py` | ✅ | ✅ green |
| 05-02-02 | 02 | 1 | PIPE-02 | — | N/A | unit | `pytest backend/tests/observation_composer_test.py backend/tests/backfill_archive_test.py` | ✅ | ✅ green |
| 05-02-03 | 02 | 1 | PIPE-02 | — | Diagnostics go to logging, not stdout | unit | `pytest backend/tests/live_log_hygiene_test.py backend/tests/backfill_archive_test.py backend/tests/SafetyMonitor_TestSuite.py backend/tests/dlr_pipeline_test.py backend/tests/weather_provider_test.py` | ✅ | ✅ green |
| 05-03-01 | 03 | 2 | SCHED-01 | — | Provider errors stored redacted | unit | `pytest backend/tests/live_run_log_test.py` | ✅ | ✅ green |
| 05-03-02 | 03 | 2 | SCHED-01 | — | Only the runner writes the run row | unit | `pytest backend/tests/dlr_live_run_test.py backend/tests/live_run_log_test.py backend/tests/dlr_orchestrator_test.py backend/tests/dlr_live_workflow_test.py` | ✅ | ✅ green |
| 05-04-01 | 04 | 2 | PIPE-02 | — | Models that fail the SHA-256 manifest stop the run before rating | unit | `pytest backend/tests/dlr_live_check_models_test.py` | ✅ | ✅ green |
| 05-04-02 | 04 | 2 | PIPE-02 | — | Only the eight live models are tracked; training frames stay ignored | integration | `git ls-files data/models && shasum -a 256 -c data/models/LIVE_ARTIFACT_HASHES.sha256 && git check-ignore -q data/models/training_frame_AUSTIN.csv` | ✅ | ✅ green |
| 05-04-03 | 04 | 2 | PIPE-02 | — | Pre-flight step runs before the run step | unit | `pytest backend/tests/dlr_live_workflow_test.py backend/tests/dlr_live_check_models_test.py backend/tests/dlr_live_run_test.py` | ✅ | ✅ green |
| 05-05-01 | 05 | 3 | SCHED-01 | — | N/A | unit | `pytest backend/tests/dlr_live_window_check_test.py` | ✅ | ✅ green |
| 05-05-02 | 05 | 3 | SCHED-02 | — | Runbook and phase files contain no secret values | unit | `pytest backend/tests/dlr_live_runbook_test.py backend/tests/dlr_live_workflow_test.py backend/tests/forecast_shadow_collect_test.py` | ✅ | ✅ green |
| 05-06-01 | 06 | 4 | PIPE-02 | — | Secrets added by the owner; `SUPABASE_DB_URL` scoped to environment `production` | manual | — (owner action, see Manual-Only) | n/a | ✅ green |
| 05-06-02 | 06 | 4 | PIPE-02 | — | Push only on owner approval | manual | — (owner decision) | n/a | ✅ green |
| 05-06-03 | 06 | 4 | PIPE-02 | T-05-29 | anon and authenticated have no privileges on `pipeline_run`/`city_rating` | production | `gh run list --workflow dlr_live.yml --limit 1 --json conclusion --jq '.[0].conclusion'` | n/a | ✅ green |
| 05-07-01 | 07 | 5 | PIPE-02 | — | Fine-grained token, repo-scoped, Actions read/write | manual | — (owner action, see Manual-Only) | n/a | ✅ green |
| 05-07-02 | 07 | 5 | SCHED-01 | — | N/A | production | `gh run list --workflow dlr_live.yml --limit 5 --json event,conclusion,createdAt` | n/a | ✅ green |
| 05-08-01 | 08 | 6 | SCHED-01, SCHED-02 | — | N/A | production | `PYTHONPATH=backend .venv/bin/python backend/dlr_live_window_check.py --start 2026-10-25T00:00:00Z --hours 24` and `pytest backend/tests/dlr_live_runbook_test.py` | ✅ | ✅ green |
| 05-08-02 | 08 | 6 | SCHED-02 | — | N/A | manual | — (owner sign-off) | n/a | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Code-review fixes (IN-01, IN-02, IN-04 to IN-07, IN-09 to IN-11, WR-01 to WR-03, IN-03 in 872d282) each added or extended tests in `dlr_live_run_test.py`, `dlr_live_window_check_test.py` or `dlr_live_check_models_test.py`. All are inside the commands above and pass.

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Actions minutes are flat since the repo went public | SCHED-02 | `gh` has no `user` scope to read billing | Settings → Billing and plans (aa-phan): usage not growing since 2026-10-24. Passed in 05-UAT.md test 1. |
| cron-job.org job settings | PIPE-02 | The cron-job.org account and token scope are outside the repo and `gh` | Dashboard shows `5 * * * *` UTC, failure notifications on, repo-scoped Actions read/write token. Passed in 05-UAT.md test 2. |
| Owner checkpoints (secrets, go-live, token creation, sign-off) | PIPE-02, SCHED-02 | Owner decisions and account actions | Recorded in 05-06, 05-07 and 05-08 SUMMARY files. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-10-26
