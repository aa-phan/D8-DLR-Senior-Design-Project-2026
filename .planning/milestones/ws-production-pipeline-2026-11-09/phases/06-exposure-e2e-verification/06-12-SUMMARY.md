---
phase: 06-exposure-e2e-verification
plan: 12
subsystem: testing
tags: [soak, freshness, e2e, supabase, pg_cron, cron-job-org, owner-run]

requires:
  - phase: 06-exposure-e2e-verification
    provides: "72 h soak clock started by 06-10 (G = 2026-10-27T03:35:00Z); soak export and report tooling from 06-07; 06-09 live checks to compare against"
provides:
  - "06-SOAK-REPORT.md: 72 h verdict PASS, 0 breaches, 864 of 864 probes, deploys and events, lag statistics, end-of-soak checks, sign-off (E2E-02)"
  - "soak-data/final/: writes.csv, runs.csv, gh_runs.json, probes.csv, export_meta.json, report.json"
  - "06-12-live-checks.json: second live public-key check, 20 of 20 ok, write verdicts identical to 06-09 (E2E-03)"
  - "06-12-PREFLIGHT.md: window facts and the end-of-soak command sheet"
  - "Soak pg_cron job dlr-soak-freshness removed (0 remaining); permanent cron-job.org freshness alarm stays on (D-13)"
affects: [06-13, 07-reval]

# Actuals (#2632): same estimateTokens scale (chars/4 over the realized diff)
actuals:
  tokens: 60000
  tasks: 3
  commits: 3
plan_head_before: c3ea81e4ccedae528f36bce144c18d58bb9f4b34
plan_head_after: 632ed2e

tech-stack:
  added: []
  patterns:
    - "Owner-run live steps with executor-side evidence checks: the executor never contacted the project; relayed output is recorded without URL, reference or key"
    - "Sign-off signalled by running the accept-only teardown command"

key-files:
  created:
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-12-PREFLIGHT.md
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-SOAK-REPORT.md
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-12-live-checks.json
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/soak-data/final/
  modified: []

key-decisions:
  - "Owner decision recorded as accept, signalled by the owner running the accept-only teardown soak_cron_unschedule.sql (the owner did not type the word separately)"
  - "No annotations.json written: there is no breach, gap or owner event to annotate, and the executor writes no explanation on the owner's behalf (T-06-41)"
  - "The window was not lengthened or shortened to meet the D-09 timeline; it ended 3 h 35 min after the target and the end-of-soak checks (taken after the change date) still pass"

patterns-established:
  - "Generated report body kept verbatim; Context, lag statistics, end-of-soak checks and sign-off are hand-added sections around it"

requirements-completed: [E2E-02]

coverage:
  - id: D1
    description: "Over exactly 72 h from G, each city's current rating was never more than 90 minutes old at any probe or any write instant; the probe log has no gap longer than 11 minutes"
    requirement: E2E-02
    verification:
      - kind: other
        ref: "e2e_soak_report.py report --mode soak --min-hours 72: exit 0, verdict pass, 0 breaches, 864 of 864 probes, max spacing 5.005 min; re-run at sign-off gives a byte-identical report.json"
        status: pass
    human_judgment: false
  - id: D2
    description: "Deploys during the window are listed from the data; none changed runtime behaviour and the soak was not paused or restarted"
    requirement: E2E-02
    verification:
      - kind: other
        ref: "06-SOAK-REPORT.md Deploys section: three pipeline-version changes, all no runtime change (only .planning/workstreams/input-provenance/ files); no owner events"
        status: pass
    human_judgment: true
    rationale: "Events the data cannot show (cron-job.org edits, pauses, incidents) are reported only by the owner, who reported none"
  - id: D3
    description: "At soak end verify_exposure.sql (17 of 17) and verify_monitoring.sql (7 of 7) report every check ok, and a second --check-read --check-hidden --check-writes run exits 0 with all seven write verdicts identical to 06-09"
    requirement: E2E-03
    verification:
      - kind: other
        ref: "owner SQL editor output relayed 2026-10-30; 06-12-live-checks.json 20 of 20 ok, exit 0, per-attempt comparison table in 06-SOAK-REPORT.md"
        status: pass
    human_judgment: false
  - id: D4
    description: "Owner sign-off and teardown: dlr-soak-freshness removed with 0 remaining; the permanent cron-job.org alarm stays on"
    requirement: E2E-02
    verification:
      - kind: manual_procedural
        ref: "owner terminal output relayed 2026-10-30: ['unschedule'] (True,) then ['remaining_jobs'] (0,)"
        status: pass
    human_judgment: true
    rationale: "Sign-off and removing the soak job are the owner's decisions and actions; the executor only records them"
  - id: D5
    description: "No committed evidence contains the project URL, reference, key or database URL"
    requirement: E2E-02
    verification:
      - kind: test
        ref: "backend/tests/secret_scan_test.py with the evidence staged: 5 passed, 1 skipped (owner-local live check), at both the export commit and the sign-off commit"
        status: pass
    human_judgment: false

duration: 1 session across the pre-flight (2026-10-30) and two owner checkpoints
completed: 2026-10-30
status: complete
---

# Phase 6 Plan 12: Close the 72 h soak Summary

**The 72 h soak passed with no breach at all: every city's current rating stayed under 90 minutes old across 864 of 864 probes (oldest seen 70 minutes), the public key still cannot change anything, and the owner accepted and removed the 5-minute soak job while the permanent alarm stays on.**

## Performance

- **Window (G):** 2026-10-27T03:35:00Z to 2026-10-30T03:35:00Z, exactly 72 h (G is the owner's go reply at 03:34:58Z rounded up to the next 5-minute boundary, from 06-10)
- **Export:** run by the owner at 2026-10-30T06:09:19Z: 384 live rows, 74 pipeline runs, 77 GitHub run records, 3456 probe rows
- **Tasks:** 3 (tracer pre-flight, owner export and checks, owner sign-off and teardown)
- **Files created:** pre-flight sheet, soak report, live-checks JSON, six export files in `soak-data/final/`

## Verdict (E2E-02)

`report --mode soak --min-hours 72` exits 0, verdict **pass**: no breach, 864 of 864 expected probes logged, no gap longer than 11 minutes (largest spacing 5.005 minutes). Re-run at sign-off (no annotations) gives exit 0 and a `report.json` byte-identical to the committed one.

| Measure | Dry soak (50 slots) | 72 h soak (72 slots) |
|---|---|---|
| Write lag median / p95 / max (min) | 7.0 / 9.7 / 13.3 | 7.1 / 9.4 / 12.3 |
| Peak age max (min) | 73.3 | 72.3 |
| Peak age above 75 / above 90 | 0 / 0 | 0 / 0 |

In plain English: for three days each city's rating landed about 7 minutes after its hour, at worst about 12, and was never close to the 90-minute limit.

## Breaches and annotations

None. No breach, no unexplained probe gap, so `annotations.json` does not exist and the executor wrote no explanation (T-06-41).

## Deploys and events (D-08)

Three pipeline-version changes were found in the rows (82c0332 to acbfe3a at the 2026-10-28T22:00Z slot, acbfe3a to aad82c2 at 2026-10-29T19:00Z, aad82c2 to e970549 at 2026-10-29T21:00Z). After a read-only `git fetch origin` all three were classifiable and are **no runtime change** (only files under `.planning/workstreams/input-provenance/`). No model, config, workflow or code deploy happened. The owner reported no events and no freshness-alarm emails (failure or recovery) in the window. The soak was not paused or restarted.

## End-of-soak checks (E2E-03)

- `verify_exposure.sql` 17 of 17 ok and `verify_monitoring.sql` 7 of 7 ok on the live project, details identical to 06-09 (relayed by the owner).
- `06-12-live-checks.json`: 20 of 20 ok, exit 0, "E2E READONLY OK". Seven write attempts compared one by one with 06-09: table insert, upsert, patch and delete all HTTP 401 code 42501; view insert, patch and delete all HTTP 500 code 55000; every verdict, status and code identical.
- Anonymous reads: four cities, valid_time 2026-10-30T06:00Z, age 11 minutes, all fresh, `is_provisional` true; keyless request 401; `assert_fresh` 200; `pipeline_run` 401; `ops.freshness_log` 406.

## Sign-off and teardown (D-13)

Owner decision: **accept**, signalled by running the accept-only teardown `supabase/ops/soak_cron_unschedule.sql`, which printed `['unschedule'] (True,)` then `['remaining_jobs'] (0,)`. `ops.freshness_log` keeps its rows as the frozen record with no new probes, and the permanent cron-job.org "DLR freshness alarm" was not touched and stays on.

## Task Commits

1. **Task 1 (tracer): pre-flight for closing the 72 h soak** - `3fa8baa` (docs)
2. **Task 2: 72 h soak export, report and end-of-soak checks** - `f629f32` (docs)
3. **Task 3: soak sign-off, annotations and teardown** - `632ed2e` (docs)

**Plan metadata:** the final docs commit (this SUMMARY plus state files).

## Deviations from Plan

1. **Window ended after the D-09 target.** D-09 wanted the clock started by 2026-10-27T00:00Z so the window would end before 2026-10-30. 06-10 started it at 03:35Z, so the window ended 3 h 35 min after that date. As D-09 requires, it was not lengthened, shortened or restarted. The end-of-soak checks ran after the change date and still pass; 06-13 repeats the permission re-check on or after 2026-10-31.
2. **Sign-off by action, not by word.** The owner did not type "accept"; running the accept-only teardown is the signal, recorded as such in the report.
3. **No annotations.json.** The plan lists it among the artifacts, but with zero breaches, gaps and events there is nothing to annotate; creating one on the owner's behalf is prohibited.
4. **Co-Authored-By line.** The plan text names Claude Opus 5.5; commits carry the runtime's configured attribution line (Claude Sonnet 5.5).

## Discrepancies

- **Write verdicts: none.** All seven attempts are identical to 06-09 in verdict, HTTP status and error code.
- **Snapshot count changed 2212 to 2520 (expected).** The snapshot checks differ only because the cutoff moved forward and about three more days of history exist: 06-09 saw 2212 rows (sha256 ea66a80f7b53), 06-12 saw 2520 rows (sha256 ab03ca91fd63). Each run found its own snapshot identical before and after its write attempts, so the attempted writes changed nothing. Reported, not assumed equivalent.
- **AUSTIN fallback share 65.3 % (47 of 72 rows), informational.** Up from 50.0 % in the dry soak. A fallback row is fresh and never a breach; the underlying cause is for a later review (Phase 7), not this plan. CORPUS_CHRISTI 1.4 %, MIDLAND 6.9 %, EL_PASO 0.0 %.
- **Window ended 3 h 35 min after the D-09 target** (Deviation 1).
- **Recovery-email gap from 06-10 carried.** The "success after failure" notification on the permanent alarm was never confirmed to deliver (06-10). The soak produced no failure, so this window could not test it. Failure alerting is proven; recovery notification stays an open owner follow-up.
- **Owner-side facts are relayed.** The export, the SQL editor tables, the live-check run, the alarm-email answer and the unschedule output are the owner's; the executor verified only what is in the committed files and the repository and never contacted the live project.

## Issues Encountered

None.

## Self-Check: PASSED

Verified before commit: the six export files, the report, the live-checks JSON and the pre-flight sheet exist; commits `3fa8baa`, `f629f32` and `632ed2e` are ancestors of HEAD.
