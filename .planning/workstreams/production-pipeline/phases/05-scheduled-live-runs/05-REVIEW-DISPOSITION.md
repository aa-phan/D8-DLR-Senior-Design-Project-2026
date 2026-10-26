---
phase: 05
review: 05-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: open
    title: "Step-summary error cell shows the head of a crash traceback and drops the exception"
  - id: WR-02
    severity: warning
    disposition: open
    title: "A red fault-drill (or any red manual run) satisfies \"visible failed run\" for a slot that was never scheduled"
  - id: WR-03
    severity: warning
    disposition: open
    title: "Child stdout and stderr are re-emitted to the Actions log outside `redact()`"
  - id: IN-01
    severity: info
    disposition: open
    title: "A child that fails after its row was written is recorded as \"no rating row\""
  - id: IN-02
    severity: info
    disposition: open
    title: "Provider errors and sources of a failed city are dropped"
  - id: IN-03
    severity: info
    disposition: open
    title: "The health predicate and run constants are duplicated across modules"
  - id: IN-04
    severity: info
    disposition: open
    title: "`--end` accepts a future slot, and `--timeout-s` is unchecked"
  - id: IN-05
    severity: info
    disposition: open
    title: "`--start \"\"` in the window check raises AttributeError instead of a usage error"
  - id: IN-06
    severity: info
    disposition: open
    title: "Step-summary cell escaping can be defeated, and child stdout can carry workflow commands"
  - id: IN-07
    severity: info
    disposition: open
    title: "`RED_CONCLUSIONS` omits `startup_failure`, `action_required` and `stale`"
  - id: IN-08
    severity: info
    disposition: open
    title: "Skipped runs are counted as billed minutes"
  - id: IN-09
    severity: info
    disposition: open
    title: "The model manifest has no repo-level guard, and `--write-manifest` drops the header comment"
open: 12
total: 12
recorded: 2026-10-26T05:20:40.754Z
---

# Phase 05: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |
| IN-07 | info | open | - |
| IN-08 | info | open | - |
| IN-09 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
