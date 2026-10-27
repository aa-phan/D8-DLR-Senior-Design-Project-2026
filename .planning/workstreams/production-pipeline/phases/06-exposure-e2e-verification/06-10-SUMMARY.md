---
phase: 06-exposure-e2e-verification
plan: 10
subsystem: infra
tags: [pg_cron, cron-job.org, freshness-alarm, dry-soak, supabase, e2e, owner-run]

requires:
  - phase: 06-exposure-e2e-verification
    provides: "ops.freshness_log, ops.log_freshness(), assert_fresh live (06-09); soak_cron_schedule.sql and soak_probe_smoke.sql (06-05); e2e_soak_report.py export and report (06-03); runbook sections 14 and 15 (06-07)"
  - phase: 05-hourly-live-run
    provides: "hourly dispatch job and the live city_rating rows since 2026-10-25T00:00Z"
provides:
  - "Live: pg_cron job dlr-soak-freshness (every 5 minutes) writing four rows per probe; smoke check all ok"
  - "Live: permanent cron-job.org alarm 'DLR freshness alarm' (every 15 minutes, GET on the freshness assertion, owner-only emails); failure email path proven by a drill"
  - "Committed dry-soak evidence (soak-data/dry/) and 06-DRY-SOAK-REPORT.md: PASS, 50 of 50 slots, peak age 73.3 min against the 90 min limit"
  - "Owner decision GO and the 72 h window start G = 2026-10-27T03:35:00Z, planned end 2026-10-30T03:35:00Z"
affects: [06-11, 06-12, 06-13]

# Actuals (#2632): same estimateTokens scale (chars/4 over the realized diff)
actuals:
  tokens: 45000
  tasks: 3
  commits: 3
plan_head_before: 1f8d51d6401b12cbe6ed66141b0c6fe3f0b136c9
plan_head_after: 36c95220ab3d5d660f973053383ebd1bb3d27972

tech-stack:
  added: []
  patterns:
    - "Owner-run live step with executor-side evidence parsing: the executor never contacts the project; the owner's relayed output is recorded without URL, reference or key"
    - "Dry soak computed from rows already written (D-07), reviewed before the 72 h clock; G fixed by the go reply, never chosen after seeing later data"

key-files:
  created:
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-10-PREFLIGHT.md
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-DRY-SOAK-REPORT.md
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/soak-data/dry/
  modified: []

key-decisions:
  - "Owner replied \"go\" after reviewing the committed dry-soak report: the 72 h soak starts at G = 2026-10-27T03:35:00Z (reply 03:34:58Z rounded up to the next 5-minute UTC boundary)"
  - "The window is not lengthened or shortened to hit D-09: it ends 2026-10-30T03:35:00Z, 3 h 35 min after the 2026-10-30T00:00Z target; the permission re-check (06-13) follows the window"
  - "The missing recovery email does not block the soak: failure alerting, the purpose of the alarm, is proven; recovery notification stays an open follow-up for the owner"

patterns-established:
  - "Smoke-check timing: run soak_probe_smoke.sql only after three probes exist (about 15 minutes after the first run); an earlier run returns false for the probe and run checks by design"

requirements-completed: []  # E2E-02 stays open: the 72 h soak has only just started (06-12 closes it)

coverage:
  - id: D1
    description: "pg_cron job dlr-soak-freshness is active every 5 minutes and the probe smoke check returned every check ok with 4 rows per probe and no breach"
    requirement: E2E-02
    verification:
      - kind: manual_procedural
        ref: "owner terminal output relayed 2026-10-27 (cron.job row; soak_probe_smoke.sql re-run, 4 of 4 ok)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Permanent alarm 'DLR freshness alarm' executed at least twice with HTTP 200 and the failure-email path was proven by the drill (503 then email at 03:24Z)"
    requirement: E2E-02
    verification:
      - kind: manual_procedural
        ref: "owner cron-job.org history and mailbox, relayed 2026-10-27"
        status: pass
    human_judgment: false
  - id: D3
    description: "The recovery (success after failure) email arrived after the drill job was flipped to a 90 minute limit"
    requirement: E2E-02
    verification:
      - kind: manual_procedural
        ref: "owner checked mailbox, relayed 2026-10-27: no recovery email arrived"
        status: fail
    human_judgment: true
    rationale: "Recovery notification is a cron-job.org setting and mail-delivery behaviour only the owner can confirm; unproven, tracked as a deviation"
  - id: D4
    description: "Dry soak over 2026-10-25T00:00Z to 2026-10-27T02:00Z passes: 50 of 50 slots, peak age 73.3 min, no rating older than 90 min"
    requirement: E2E-02
    verification:
      - kind: other
        ref: "backend/e2e_soak_report.py report --mode dry --min-hours 12 (exit 0), 06-DRY-SOAK-REPORT.md"
        status: pass
    human_judgment: false
  - id: D5
    description: "Owner go decision with G recorded from the reply time"
    requirement: E2E-02
    verification: []
    human_judgment: true
    rationale: "Go or no-go is a blocking owner decision (D-07); the evidence supports it but only the owner decides"

duration: 1 session (owner steps spanned 2026-10-27T02:50Z to 03:35Z)
completed: 2026-10-27
status: complete
---

# Phase 6 Plan 10: Soak instruments live, dry soak reviewed, 72 h window started Summary

**The five-minute freshness log and the permanent 15-minute REST alarm are live and proven (smoke check 4 of 4 ok, failure-email drill worked), a dry soak from existing rows passed with a worst rating age of 73.3 min against the 90 min limit, and the owner said "go": the 72 h window runs from 2026-10-27T03:35:00Z to 2026-10-30T03:35:00Z.**

## Performance

- **Duration:** one session; owner steps ran from about 2026-10-27T02:50Z (T0 of the log) to the go reply at 03:34:58Z
- **Tasks:** 3 (1 tracer, 1 owner monitoring plus dry export, 1 owner decision)
- **Files created:** 3 evidence artifacts (pre-flight, dry-soak report, `soak-data/dry/` with five files)

## Decision and window (T-06-37)

| Item | Value |
|---|---|
| Owner reply (verbatim) | "go" |
| Reply time (orchestrator system clock) | 2026-10-27T03:34:58Z |
| **G (reply time rounded up to the next 5-minute UTC boundary)** | **2026-10-27T03:35:00Z** |
| Planned end, G + 72 h | 2026-10-30T03:35:00Z |
| Ends before 2026-10-30T00:00Z (D-09)? | **No**: 3 h 35 min after it |
| Dry-soak export `--until` | 2026-10-27T02:00:00Z (before G, so no overlap) |
| Smoke check passed | before G (re-run, all ok) |

G is after the dry-soak export's `--until` (02:00Z) and after the smoke check, so the window never overlaps the dry-soak data. The 2026-10-27T00:00Z D-09 start target was missed (the log was only switched on at about 02:50Z), so the end falls after 2026-10-30. D-09 allows this: the window is neither lengthened nor shortened, and the permission re-check (06-13) follows the window. 06-12 must read G from this file and check that the final export's `since` equals `2026-10-27T03:35:00Z` exactly.

## Job row and smoke check

- **pg_cron job:** one row, name `dlr-soak-freshness`, schedule `*/5 * * * *`, active, command `select ops.log_freshness()`. First run 2026-10-27T02:55:00Z succeeded (one row, four log rows).
- **Smoke check (re-run once three probes existed):**

| check | result | detail |
|---|---|---|
| last_three_probes_wrote_four_rows | ok | 3 of 3 probes; 4, 4, 4 rows |
| last_three_runs_succeeded | ok | 3 of 3 runs succeeded |
| no_breach_in_the_last_three_probes | ok | 0, 0, 0 breach rows |
| soak_job_active_every_5_minutes | ok | 1 job, active, every 5 minutes |

## Alarm settings and statuses (no URL, no key)

- **Job:** "DLR freshness alarm" (new job; the hourly dispatch job and the shadow job were not touched).
- **Request:** GET on the freshness assertion function with the publishable key in the apikey header only (no secret key, no database URL).
- **Schedule:** every 15 minutes UTC. **Notifications (D-14, D-15):** failure after 2, success after failure, job disabled; emails to the owner's account only.
- **First two executions:** 200, 200.
- **Failure drill (limit 0 minutes, every minute):** runs returned 503; the failure email arrived 2026-10-27T03:24Z (10:24 PM CDT). Failure alerting is proven, which also confirms that cron-job.org counts 503 as a failed execution (assumption A17).
- **Recovery drill:** the same job was flipped to a 90 minute limit and returned 200, but **no recovery email arrived**. An earlier separate always-succeeding job produced none either, which is expected (a job that never failed cannot recover). Recovery notification is unproven.
- The owner deletes the drill jobs (owner action; not verifiable here).

## Dry-soak verdict and statistics

Window 2026-10-25T00:00:00Z to 2026-10-27T02:00:00Z, 50 hourly slots, run with `--min-hours 12`, 204 live rows and 53 pipeline runs exported.

**PASS.** All 50 slots landed (ok 50); the current rating was never older than 73.3 min (limit 90, OD-4 unchanged); write lag from first write: median 7.0 min, p95 9.7, max 13.3 (last-write lag up to 23.8 min, informational); age at end of window 60.0 min for every city; no late fills. Peak age by city: AUSTIN 69.9, CORPUS_CHRISTI 71.0, MIDLAND 72.2, EL_PASO 73.3; none above 75. Billed minutes: median 4, max 9 per run; projected 2880 min per 30 days. Full tables in `06-DRY-SOAK-REPORT.md`.

**Informational: fallback share.** AUSTIN 25 of 50 (50 %), MIDLAND 4 of 50 (8 %), CORPUS_CHRISTI and EL_PASO 0. A fallback is the static rating published when the computed rating fails a safety gate; the row is fresh, so it is not a breach. The high AUSTIN share is worth a look in a later review but does not affect the freshness verdict.

## Task Commits

1. **Task 1 (tracer): pre-flight and owner command sheet** - `45ea9e3` (docs)
2. **Task 2: owner monitoring, dry export, report and evidence** - `36c9522` (docs)
3. **Task 3: owner go/no-go** - no commit (decision recorded here)

**Plan metadata:** the final docs commit (this SUMMARY plus state files).

Note: `actuals.commits: 3` is measured from the ledger base to HEAD at write time and includes `71f2549` (06-11's pre-flight), which landed between this plan's two commits; this plan's own task commits are 2.

## Deviations from Plan

1. **Recovery email never arrived (D-14 recovery notification unproven).** Failure alerting is proven; recovery is not. Non-blocking for the soak because the alarm's purpose (warn when a rating goes stale) is proven. Follow-up for the owner: check the permanent alarm's "success after failure" notification setting. The plan's must-have "after switching to max_age_minutes=90, a recovery email" is therefore NOT met as written.
2. **D-09 start target missed.** The 72 h clock starts 2026-10-27T03:35:00Z instead of by 2026-10-27T00:00Z, so the window ends 2026-10-30T03:35:00Z (after 2026-10-30T00:00Z). Allowed by D-09; 06-13 follows the window.
3. **First smoke run was early.** It ran before three probes existed and returned false for the probe and run checks (0 of 3); it was re-run after three probes and all four checks were ok. Not a fault, but the pre-flight should say to wait for three probes.

## Discrepancies

- The recovery email absence above (plan truth not met; owner follow-up).
- The window ends after 2026-10-30T00:00Z (timeline, not a defect).
- Owner-side facts (cron.job row, smoke output, alarm executions, drill emails, drill job deletion) are relayed by the owner and were not independently checked by the executor, which never contacts the live project.

## Issues Encountered

None beyond the deviations above.

## User Setup Required

Done by the owner during this plan (pg_cron job, alarm job, drill). Open owner items: confirm the permanent alarm's "success after failure" notification, and confirm the drill jobs were deleted.

## Threat Flags

None. No URL, project reference, key or database URL is in the committed evidence (06-02 scan passed on the staged files in `36c9522`).

## Next Phase Readiness

- 06-12 can proceed once the window ends: earliest final export at G + 72 h = 2026-10-30T03:35:00Z; `since` must equal 2026-10-27T03:35:00Z.
- 06-13 runs after the window. During the window nothing is paused or restarted; deploys are recorded from the data (D-08); note any cron-job.org edit, pause or provider incident with its time.
- E2E-02 stays open until 06-12.

---
*Phase: 06-exposure-e2e-verification*
*Completed: 2026-10-27*
