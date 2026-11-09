---
phase: 08
review: 08-REVIEW.md
titles: json
findings:
  - id: WR-06
    severity: warning
    disposition: open
    title: "The CI guard is described as running \"before it reaches main\", but it also triggers on direct pushes to main, and nothing blocks a merge"
  - id: IN-01
    severity: info
    disposition: open
    title: "`missing` is reported as empty for timeout, no-output and crash records"
  - id: IN-02
    severity: info
    disposition: open
    title: "The summary reason cell shows only the tail of the joined reasons"
  - id: IN-03
    severity: info
    disposition: open
    title: "The `supabase_js.mjs` header omits Part 3"
  - id: IN-04
    severity: info
    disposition: open
    title: "The schema doc overstates the issue rate"
  - id: IN-05
    severity: info
    disposition: open
    title: "Constants are hard-coded where code derives them"
  - id: IN-06
    severity: info
    disposition: open
    title: "Dead and duplicated code"
  - id: IN-07
    severity: info
    disposition: open
    title: "`verify_exposure.sql` raises instead of returning false when a day-ahead object is missing"
  - id: IN-08
    severity: info
    disposition: open
    title: "`apply_band` discards a valid edge when only one edge is bad"
  - id: IN-09
    severity: info
    disposition: open
    title: "`build_band_artifact` ignores minutes and seconds in `valid_time`"
  - id: IN-10
    severity: info
    disposition: open
    title: "A test fixture and a doc anecdote are inconsistent with the contract"
  - id: IN-11
    severity: info
    disposition: open
    title: "The TEST-band fallback is silent in the stored data and the run log"
  - id: IN-12
    severity: info
    disposition: open
    title: "Consumer docs still call the feed \"next-day\" next to an 18 h lookahead"
  - id: IN-13
    severity: info
    disposition: open
    title: "`curl.sh` hard-codes the label that `read_ratings.py` reads from the data"
  - id: IN-14
    severity: info
    disposition: open
    title: "Actions in the new workflow are pinned by tag, while `supabase_smoke.yml` pins by SHA"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "A failing live-band query blocks publication; it does not fall back to the TEST band"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "Consumer docs describe a \"next-day\" horizon the data does not have, and conflate \"not yet issued\" with \"late\""
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "The standing runbook says `verify_day_ahead_store.sql` must be all-true, but one check is false by design after the exposure"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "The permanent freshness alarm is coupled to the day-ahead feed, and its 503 message changed"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "The \"fails hard before a push\" safety net is not enforced anywhere"
open: 15
total: 20
recorded: 2026-11-09T09:48:09.043Z
---

# Phase 08: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-06 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| IN-04 | info | open | - |
| IN-05 | info | open | - |
| IN-06 | info | open | - |
| IN-07 | info | open | - |
| IN-08 | info | open | - |
| IN-09 | info | open | - |
| IN-10 | info | open | - |
| IN-11 | info | open | - |
| IN-12 | info | open | - |
| IN-13 | info | open | - |
| IN-14 | info | open | - |
| WR-01 | warning | fixed | 08-REVIEW-FIX.md (not in the current review) |
| WR-02 | warning | fixed | 08-REVIEW-FIX.md (not in the current review) |
| WR-03 | warning | fixed | 08-REVIEW-FIX.md (not in the current review) |
| WR-04 | warning | fixed | 08-REVIEW-FIX.md (not in the current review) |
| WR-05 | warning | fixed | 08-REVIEW-FIX.md (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
