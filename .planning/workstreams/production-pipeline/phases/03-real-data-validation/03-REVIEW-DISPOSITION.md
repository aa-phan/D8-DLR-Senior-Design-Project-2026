---
phase: 03
review: 03-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "Credential redaction misses quoted, JSON/dict-style, header and encoded forms, and leaks the tail of values containing separators"
  - id: WR-01
    severity: warning
    disposition: open
    title: "The same error text is written unredacted to the backfill log"
  - id: WR-02
    severity: warning
    disposition: open
    title: "A torn last line in the trace makes the whole analysis crash"
  - id: WR-03
    severity: warning
    disposition: open
    title: "Ctrl-C during `replay` silently continues with the next city and produces a partial replay that cannot be resumed"
  - id: WR-04
    severity: warning
    disposition: open
    title: "The trace record is written after the archive row and the log row, so an interrupt leaves a step archived with no trace forever"
  - id: WR-05
    severity: warning
    disposition: open
    title: "`_git` raises when git is not installed"
  - id: WR-06
    severity: warning
    disposition: open
    title: "The manifest is not deterministic as documented, and its `command` is not shell-safe"
  - id: IN-01
    severity: info
    disposition: open
    title: "`TRACE_SCHEMA` is never checked on read"
  - id: IN-02
    severity: info
    disposition: open
    title: "`zip(run[\"results\"], run[\"summary\"])` silently truncates"
  - id: IN-03
    severity: info
    disposition: open
    title: "Duplicated helpers and constants"
  - id: IN-04
    severity: info
    disposition: open
    title: "Trace file handle can leak and `replay` output paths are not cross-checked"
open: 11
total: 11
recorded: 2026-10-21T07:14:33.086Z
---

# Phase 03: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| CR-01 | critical | open | - |
| WR-01 | warning | open | - |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| WR-04 | warning | open | - |
| WR-05 | warning | open | - |
| WR-06 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
