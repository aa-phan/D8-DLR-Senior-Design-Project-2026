---
phase: 03
review: 03-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "Dropping bare `key` from the name list leaks camelCase and concatenated key names (regression from pass 1)"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "Quoted, escaped, unterminated and `auth:`/`sig:` colon-form credentials still pass through"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "The backfill log row is built by string formatting, so an error message that starts with an unbalanced `\"` makes `_read_log` (and `completeness`) fail"
  - id: IN-01
    severity: info
    disposition: open
    title: "`TRACE_SCHEMA` is never checked on read (still present)"
  - id: IN-02
    severity: info
    disposition: open
    title: "`zip(run[\"results\"], run[\"summary\"])` silently truncates (still present)"
  - id: IN-03
    severity: info
    disposition: open
    title: "Duplicated helpers and constants (still present)"
  - id: IN-04
    severity: info
    disposition: open
    title: "Trace file handle can leak; replay output paths are not cross-checked (still present)"
  - id: IN-05
    severity: info
    disposition: open
    title: "The manifest is still tied to the checkout location (still present)"
  - id: IN-06
    severity: info
    disposition: open
    title: "`_terminate_last_line` covers only the trace; the log can still get a row glued onto a torn line (still present)"
  - id: IN-07
    severity: info
    disposition: open
    title: "A torn line in the replay trace is silently dropped by the fidelity check and the replay-side report (still present)"
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "Credential redaction misses quoted, JSON/dict-style, header and encoded forms, and leaks the tail of values containing separators"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "The trace record is written after the archive row and the log row, so an interrupt leaves a step archived with no trace forever"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "`_git` raises when git is not installed"
  - id: WR-06
    severity: warning
    disposition: fixed
    title: "The manifest is not deterministic as documented, and its `command` is not shell-safe"
open: 7
total: 14
recorded: 2026-10-23T19:24:32.452Z
---

# Phase 03: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-01 | warning | fixed | 03-REVIEW-FIX.md (pass 3, 17c436b; hand-set, id reused across passes) |
| WR-02 | warning | fixed | 03-REVIEW-FIX.md |
| WR-03 | warning | fixed | 03-REVIEW-FIX.md (pass 3, 8a9ab91; hand-set, id reused across passes) |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |
| IN-07 | info | open | - |
| CR-01 | critical | fixed | 03-REVIEW-FIX.iter2.md (not in the current review) |
| WR-04 | warning | fixed | 03-REVIEW-FIX.iter2.md (not in the current review) |
| WR-05 | warning | fixed | 03-REVIEW-FIX.iter2.md (not in the current review) |
| WR-06 | warning | fixed | 03-REVIEW-FIX.iter2.md (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
