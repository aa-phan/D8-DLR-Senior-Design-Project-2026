---
phase: 05
review: 05-REVIEW.md
titles: json
findings:
  - id: IN-01
    severity: info
    disposition: fixed
    title: "A child that fails after its row was written is recorded as \"no rating row\""
  - id: IN-02
    severity: info
    disposition: fixed
    title: "Provider errors and sources of a failed city are dropped"
  - id: IN-03
    severity: info
    disposition: skipped
    title: "The health predicate and run constants are duplicated across modules"
  - id: IN-04
    severity: info
    disposition: fixed
    title: "`--end` accepts a future slot, and `--timeout-s` is unchecked"
  - id: IN-05
    severity: info
    disposition: fixed
    title: "`--start \"\"` in the window check raises AttributeError instead of a usage error"
  - id: IN-06
    severity: info
    disposition: fixed
    title: "Step-summary cell escaping can be defeated, and child stdout can carry workflow commands"
  - id: IN-07
    severity: info
    disposition: fixed
    title: "`RED_CONCLUSIONS` omits `startup_failure`, `action_required` and `stale`"
  - id: IN-08
    severity: info
    disposition: skipped
    title: "Skipped runs are counted as billed minutes"
  - id: IN-09
    severity: info
    disposition: fixed
    title: "The model manifest has no repo-level guard, and `--write-manifest` drops the header comment"
  - id: IN-10
    severity: info
    disposition: fixed
    title: "The WR-03 redaction masks ordinary child log text (`cache_key=`, `monkey=`)"
  - id: IN-11
    severity: info
    disposition: fixed
    title: "Drill detection depends on a saved `cities_failed` entry, and the runbook still describes the old semantics"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "Step-summary error cell shows the head of a crash traceback and drops the exception"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "A red fault-drill (or any red manual run) satisfies \"visible failed run\" for a slot that was never scheduled"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "Child stdout and stderr are re-emitted to the Actions log outside `redact()`"
open: 0
total: 14
recorded: 2026-10-26T17:52:39.632Z
---

# Phase 05: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| IN-01 | info | fixed | 05-REVIEW-FIX.md |
| IN-02 | info | fixed | 05-REVIEW-FIX.md |
| IN-03 | info | skipped | 05-REVIEW-FIX.md |
| IN-04 | info | fixed | 05-REVIEW-FIX.md |
| IN-05 | info | fixed | 05-REVIEW-FIX.md |
| IN-06 | info | fixed | 05-REVIEW-FIX.md |
| IN-07 | info | fixed | 05-REVIEW-FIX.md |
| IN-08 | info | skipped | 05-REVIEW-FIX.md |
| IN-09 | info | fixed | 05-REVIEW-FIX.md |
| IN-10 | info | fixed | 05-REVIEW-FIX.md |
| IN-11 | info | fixed | 05-REVIEW-FIX.md |
| WR-01 | warning | fixed | 05-REVIEW-FIX.md (not in the current review) |
| WR-02 | warning | fixed | 05-REVIEW-FIX.md (not in the current review) |
| WR-03 | warning | fixed | 05-REVIEW-FIX.md (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
