---
status: testing
phase: 05-scheduled-live-runs
source: [05-VERIFICATION.md]
started: 2026-10-26T06:00:00Z
updated: 2026-10-26T06:00:00Z
---

## Current Test

number: 1
name: GitHub Billing page shows Actions usage stopped growing after the repo went public
expected: |
  Settings → Billing and plans (account aa-phan): Actions minutes used this cycle have not grown
  since 2026-10-24 (when the repository was made public), even though hourly live runs and four
  daily Shadow Collection runs continued. Public-repo minutes on GitHub-hosted runners are free.
awaiting: user response

## Tests

### 1. GitHub Billing page shows Actions usage stopped growing after the repo went public
expected: Actions minutes used this cycle are flat since 2026-10-24 despite continued hourly live runs (measured ~2,880 live + ~600 shadow min per 30 days, which would exceed the 2,000 included minutes on a private repo).
result: [pending]

### 2. cron-job.org live job settings match the runbook
expected: The dlr_live job in the cron-job.org dashboard has schedule `5 * * * *` in UTC, failure notifications ON, and its token is a fine-grained token limited to D8-DLR-Senior-Design-Project-2026 with Actions read/write only (dlr_live_runbook.md section 2). Dispatch history already shows the schedule and token working.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
